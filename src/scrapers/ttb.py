"""
OenoBench — TTB (Tax and Trade Bureau) Scraper

Extracts US wine regulation data from the TTB:
  - AVA listings — name, state, establishment date, Federal Register citation
  - Approved grape variety names — the official TTB list per 27 CFR 4.91
  - Key labeling regulations from 27 CFR Part 4

Sources: https://www.ttb.gov (US Government, public domain)

Usage:
    python -m src.scrapers.ttb --all
    python -m src.scrapers.ttb --source ava
    python -m src.scrapers.ttb --source varieties
    python -m src.scrapers.ttb --source regulations
    python -m src.scrapers.ttb --dry-run
    python -m src.scrapers.ttb --validate
    python -m src.scrapers.ttb --list
    python -m src.scrapers.ttb --test-run
    python -m src.scrapers.ttb --test-run --cleanup
    python -m src.scrapers.ttb --test-run --source ava
"""

import random
import re
import time
from collections import defaultdict
from pathlib import Path
from typing import Optional

import click
import requests
from bs4 import BeautifulSoup
from loguru import logger

from src.utils.facts import ensure_source, insert_facts_batch, get_fact_count

# ─── Configuration ────────────────────────────────────────────────────────────

USER_AGENT = "OenoBench-Research/1.0 (academic wine benchmark)"
REQUEST_DELAY = 3.0  # seconds between requests — government site, be respectful

TTB_BASE = "https://www.ttb.gov"
ECFR_BASE = "https://www.ecfr.gov"

SOURCES_CONFIG = {
    "ava": {
        "description": "Established American Viticultural Areas (AVAs)",
        "urls": {
            "established": f"{TTB_BASE}/wine/established-avas",
            "by_date": (
                f"{TTB_BASE}/regulated-commodities/beverage-alcohol"
                "/wine/ava-establishment-dates"
            ),
        },
        "source_name": "TTB — Established AVAs",
        "source_url": f"{TTB_BASE}/wine/established-avas",
        "source_type": "government",
    },
    "varieties": {
        "description": "TTB-approved grape variety names for wine labels (27 CFR 4.91)",
        "urls": {
            "ecfr_html": f"{ECFR_BASE}/current/title-27/section-4.91",
            "ecfr_api": (
                f"{ECFR_BASE}/api/versioner/v1/full/current"
                "/title-27.xml?part=4&section=4.91"
            ),
        },
        "source_name": "TTB — Approved Grape Variety Names (27 CFR 4.91)",
        "source_url": f"{ECFR_BASE}/current/title-27/section-4.91",
        "source_type": "government",
    },
    "regulations": {
        "description": "Key US wine labeling regulations from 27 CFR Part 4",
        "urls": {},
        "source_name": "TTB — Wine Labeling Regulations (27 CFR Part 4)",
        "source_url": (
            f"{ECFR_BASE}/current/title-27/chapter-I/subchapter-A/part-4"
        ),
        "source_type": "government",
    },
}


# ─── HTTP Client ──────────────────────────────────────────────────────────────


def _create_session() -> requests.Session:
    """Create an HTTP session with proper headers for government sites."""
    session = requests.Session()
    session.headers.update({
        "User-Agent": USER_AGENT,
        "Accept": (
            "text/html,application/xhtml+xml,"
            "application/xml;q=0.9,*/*;q=0.8"
        ),
        "Accept-Language": "en-US,en;q=0.5",
    })
    return session


def _fetch_url(
    session: requests.Session, url: str, retries: int = 3
) -> Optional[str]:
    """Fetch a URL with retries and rate limiting. Returns text or None."""
    for attempt in range(retries):
        try:
            logger.info(f"Fetching: {url} (attempt {attempt + 1}/{retries})")
            resp = session.get(url, timeout=30)
            resp.raise_for_status()
            time.sleep(REQUEST_DELAY)
            return resp.text
        except requests.RequestException as e:
            logger.warning(f"Request failed for {url}: {e}")
            if attempt < retries - 1:
                wait = 2 ** (attempt + 1)
                logger.info(f"Retrying in {wait}s...")
                time.sleep(wait)

    logger.error(f"All {retries} attempts failed for {url}")
    return None


# ═════════════════════════════════════════════════════════════════════════════
#  AVA SCRAPER
# ═════════════════════════════════════════════════════════════════════════════


def _parse_ava_page(html: str) -> list[dict]:
    """Parse AVA data from a TTB HTML page.

    Tries multiple strategies to handle different TTB page layouts:
    1. Look for HTML tables with AVA rows
    2. Look for list items or links containing AVA names
    """
    soup = BeautifulSoup(html, "lxml")
    avas = []
    seen_names = set()

    # Strategy 1: Parse HTML tables
    tables = soup.find_all("table")
    for table in tables:
        rows = table.find_all("tr")
        for row in rows:
            cells = row.find_all(["td", "th"])
            if len(cells) < 2:
                continue

            texts = [c.get_text(strip=True) for c in cells]
            # Skip header rows
            if any(
                h in texts[0].lower()
                for h in ["ava name", "viticultural area", "name", "#"]
            ):
                continue

            name = texts[0].strip()
            if not name or name.lower() in ("", "ava name", "name"):
                continue

            ava = {"name": name}

            # Try to identify state, date, and citation from remaining cells
            for text in texts[1:]:
                text = text.strip()
                if not text:
                    continue

                # Check for state abbreviation or name
                if re.match(r"^[A-Z]{2}$", text) or _is_us_state(text):
                    ava.setdefault("state", text)
                # Check for date patterns (e.g., "01/01/1984" or "January 1, 1984")
                elif re.search(r"\d{1,2}/\d{1,2}/\d{4}", text):
                    ava.setdefault("date", text)
                elif re.search(r"\b(19|20)\d{2}\b", text):
                    year_match = re.search(r"\b(19|20)\d{2}\b", text)
                    if year_match:
                        ava.setdefault("year", year_match.group())
                    if "FR" in text or "Fed. Reg." in text or "T.D." in text:
                        ava.setdefault("fr_citation", text)
                # Check for CFR citations (e.g., "9.XXX")
                elif re.match(r"^§?\s*9\.\d+", text):
                    ava.setdefault("cfr_section", text)

            if name not in seen_names:
                seen_names.add(name)
                avas.append(ava)

    # Strategy 2: If no tables found, look for links in list items
    if not avas:
        logger.info("No tables found; trying list/link-based parsing")
        for link in soup.find_all("a"):
            text = link.get_text(strip=True)
            href = link.get("href", "")
            # AVA links often point to CFR Part 9 sections or AVA detail pages
            if (
                "part-9" in href
                or "ava" in href.lower()
                or "/wine/" in href
            ):
                if text and len(text) > 2 and text not in seen_names:
                    # Filter out navigation / generic links
                    if text.lower() not in (
                        "home", "wine", "avas", "back", "top",
                        "next", "previous",
                    ):
                        seen_names.add(text)
                        avas.append({"name": text})

    logger.info(f"Parsed {len(avas)} AVAs from page")
    return avas


def _parse_ava_dates_page(html: str) -> dict[str, dict]:
    """Parse the AVA establishment dates page.

    Returns a dict mapping AVA name -> {state, year, date, fr_citation}.
    """
    soup = BeautifulSoup(html, "lxml")
    date_info = {}

    tables = soup.find_all("table")
    for table in tables:
        rows = table.find_all("tr")
        for row in rows:
            cells = row.find_all(["td", "th"])
            if len(cells) < 2:
                continue

            texts = [c.get_text(strip=True) for c in cells]
            name = texts[0].strip()

            if not name or name.lower() in (
                "ava name", "name", "viticultural area", "#"
            ):
                continue

            info = {}
            for text in texts[1:]:
                text = text.strip()
                if not text:
                    continue
                if re.match(r"^[A-Z]{2}$", text) or _is_us_state(text):
                    info.setdefault("state", text)
                elif re.search(r"\d{1,2}/\d{1,2}/\d{4}", text):
                    info.setdefault("date", text)
                    year_match = re.search(r"\b(19|20)\d{2}\b", text)
                    if year_match:
                        info.setdefault("year", year_match.group())
                elif re.search(r"\b(19|20)\d{2}\b", text):
                    year_match = re.search(r"\b(19|20)\d{2}\b", text)
                    if year_match:
                        info.setdefault("year", year_match.group())
                    if "FR" in text or "Fed." in text or "T.D." in text:
                        info.setdefault("fr_citation", text)

            if name:
                date_info[name] = info

    logger.info(f"Parsed establishment dates for {len(date_info)} AVAs")
    return date_info


_US_STATES = {
    "Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado",
    "Connecticut", "Delaware", "Florida", "Georgia", "Hawaii", "Idaho",
    "Illinois", "Indiana", "Iowa", "Kansas", "Kentucky", "Louisiana",
    "Maine", "Maryland", "Massachusetts", "Michigan", "Minnesota",
    "Mississippi", "Missouri", "Montana", "Nebraska", "Nevada",
    "New Hampshire", "New Jersey", "New Mexico", "New York",
    "North Carolina", "North Dakota", "Ohio", "Oklahoma", "Oregon",
    "Pennsylvania", "Rhode Island", "South Carolina", "South Dakota",
    "Tennessee", "Texas", "Utah", "Vermont", "Virginia", "Washington",
    "West Virginia", "Wisconsin", "Wyoming",
}

_STATE_ABBREVS = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
}

_ABBREV_TO_STATE = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut",
    "DE": "Delaware", "FL": "Florida", "GA": "Georgia", "HI": "Hawaii",
    "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa",
    "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine",
    "MD": "Maryland", "MA": "Massachusetts", "MI": "Michigan",
    "MN": "Minnesota", "MS": "Mississippi", "MO": "Missouri",
    "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico",
    "NY": "New York", "NC": "North Carolina", "ND": "North Dakota",
    "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania",
    "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota",
    "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VT": "Vermont",
    "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
    "WI": "Wisconsin", "WY": "Wyoming",
}


def _is_us_state(text: str) -> bool:
    """Check if text is a US state name."""
    return text.strip() in _US_STATES


def _normalize_state(state_text: str) -> str:
    """Normalize a state abbreviation or name to full state name."""
    text = state_text.strip()
    if text in _ABBREV_TO_STATE:
        return _ABBREV_TO_STATE[text]
    if text in _US_STATES:
        return text
    return text


def _scrape_avas(session: requests.Session) -> list[dict]:
    """Scrape AVA data from TTB. Returns list of AVA dicts."""
    urls = SOURCES_CONFIG["ava"]["urls"]
    avas = []

    # Fetch main established AVAs page
    html = _fetch_url(session, urls["established"])
    if html:
        avas = _parse_ava_page(html)

    # Fetch establishment dates page for supplemental data
    date_info = {}
    html2 = _fetch_url(session, urls["by_date"])
    if html2:
        date_info = _parse_ava_dates_page(html2)

    # Merge date info into AVA records
    if date_info:
        ava_by_name = {a["name"]: a for a in avas}
        for name, info in date_info.items():
            if name in ava_by_name:
                for key, val in info.items():
                    ava_by_name[name].setdefault(key, val)
            else:
                info["name"] = name
                avas.append(info)

    # If live scraping returned nothing, use fallback
    if not avas:
        logger.warning(
            "Live AVA scraping returned no results; using fallback data"
        )
        avas = _get_fallback_avas()

    logger.info(f"Total AVA records: {len(avas)}")
    return avas


def _build_ava_facts(avas: list[dict], source_id: str) -> list[dict]:
    """Convert AVA records to atomic facts."""
    facts = []
    seen = set()

    for ava in avas:
        name = ava.get("name", "").strip()
        if not name:
            continue

        state = ava.get("state", "")
        if state:
            state = _normalize_state(state)

        year = ava.get("year", "")
        date_str = ava.get("date", "")
        fr_citation = ava.get("fr_citation", "")
        cfr_section = ava.get("cfr_section", "")

        entities = [{"type": "ava", "name": name}]
        if state:
            entities.append({"type": "state", "name": state})

        # Fact: AVA establishment with location and date
        if state and year:
            key = f"ava_established:{name}"
            if key not in seen:
                seen.add(key)
                facts.append({
                    "fact_text": (
                        f"The {name} AVA was established in {year} "
                        f"in {state}."
                    ),
                    "domain": "wine_regions",
                    "subdomain": "us_avas",
                    "source_id": source_id,
                    "entities": entities,
                    "confidence": 1.0,
                    "tags": ["ava", "us", state.lower().replace(" ", "_")],
                })
        elif state:
            key = f"ava_location:{name}"
            if key not in seen:
                seen.add(key)
                facts.append({
                    "fact_text": (
                        f"The {name} AVA is located in {state}."
                    ),
                    "domain": "wine_regions",
                    "subdomain": "us_avas",
                    "source_id": source_id,
                    "entities": entities,
                    "confidence": 1.0,
                    "tags": ["ava", "us", state.lower().replace(" ", "_")],
                })
        elif year:
            key = f"ava_year:{name}"
            if key not in seen:
                seen.add(key)
                facts.append({
                    "fact_text": (
                        f"The {name} AVA was established in {year}."
                    ),
                    "domain": "wine_regions",
                    "subdomain": "us_avas",
                    "source_id": source_id,
                    "entities": entities,
                    "confidence": 1.0,
                    "tags": ["ava", "us"],
                })
        else:
            key = f"ava_exists:{name}"
            if key not in seen:
                seen.add(key)
                facts.append({
                    "fact_text": (
                        f"{name} is a federally recognized American "
                        f"Viticultural Area (AVA)."
                    ),
                    "domain": "wine_regions",
                    "subdomain": "us_avas",
                    "source_id": source_id,
                    "entities": entities,
                    "confidence": 1.0,
                    "tags": ["ava", "us"],
                })

        # Fact: Federal Register citation
        if fr_citation:
            key = f"ava_fr:{name}"
            if key not in seen:
                seen.add(key)
                facts.append({
                    "fact_text": (
                        f"The {name} AVA was established by "
                        f"{fr_citation}."
                    ),
                    "domain": "wine_regions",
                    "subdomain": "us_avas",
                    "source_id": source_id,
                    "entities": entities,
                    "confidence": 1.0,
                    "tags": ["ava", "us", "regulation"],
                })

        # Fact: CFR section
        if cfr_section:
            key = f"ava_cfr:{name}"
            if key not in seen:
                seen.add(key)
                section = cfr_section.lstrip("§ ")
                facts.append({
                    "fact_text": (
                        f"The boundaries of the {name} AVA are defined "
                        f"in 27 CFR {section}."
                    ),
                    "domain": "wine_regions",
                    "subdomain": "us_avas",
                    "source_id": source_id,
                    "entities": entities,
                    "confidence": 1.0,
                    "tags": ["ava", "us", "regulation", "boundaries"],
                })

    logger.info(f"Built {len(facts)} AVA facts from {len(avas)} records")
    return facts


# ═════════════════════════════════════════════════════════════════════════════
#  GRAPE VARIETY SCRAPER
# ═════════════════════════════════════════════════════════════════════════════


def _parse_ecfr_varieties_html(html: str) -> list[dict]:
    """Parse grape variety names from an eCFR HTML page for 27 CFR 4.91."""
    soup = BeautifulSoup(html, "lxml")
    varieties = []
    seen = set()

    # Strategy 1: Look for list items or paragraphs with variety names
    # The eCFR typically lists varieties in <p> tags within the section
    section_found = False
    for elem in soup.find_all(["p", "li", "div"]):
        text = elem.get_text(strip=True)

        # Detect start of variety list section
        if "approved" in text.lower() and "grape" in text.lower():
            section_found = True
            continue

        if not section_found:
            continue

        # Each variety entry is typically on its own line
        # Format: "Name" or "Name (Synonym)" or "(a) Name (Synonym)"
        # Remove leading lettering like "(a)", "(b)", etc.
        cleaned = re.sub(r"^\([a-z]\)\s*", "", text).strip()
        cleaned = re.sub(r"^\d+\.\s*", "", cleaned).strip()

        if not cleaned or len(cleaned) > 200:
            continue

        # Extract primary name and synonyms
        match = re.match(r"^([^(]+?)(?:\s*\(([^)]+)\))?\s*\.?\s*$", cleaned)
        if match:
            primary = match.group(1).strip().rstrip(".")
            synonyms_text = match.group(2)

            if not primary or len(primary) < 2:
                continue

            # Filter out non-variety text
            if any(
                w in primary.lower()
                for w in [
                    "the following", "approved", "variety names",
                    "administrator", "wine labels", "section",
                    "type designation", "shall",
                ]
            ):
                continue

            synonyms = []
            if synonyms_text:
                synonyms = [
                    s.strip() for s in synonyms_text.split(",")
                    if s.strip()
                ]

            if primary not in seen:
                seen.add(primary)
                varieties.append({
                    "name": primary,
                    "synonyms": synonyms,
                })

    logger.info(f"Parsed {len(varieties)} grape varieties from eCFR HTML")
    return varieties


def _parse_ecfr_varieties_xml(xml_text: str) -> list[dict]:
    """Parse grape variety names from eCFR XML for 27 CFR 4.91."""
    soup = BeautifulSoup(xml_text, "lxml-xml")
    varieties = []
    seen = set()

    # Find paragraphs within the section
    for p in soup.find_all(["P", "p", "FP"]):
        text = p.get_text(strip=True)
        cleaned = re.sub(r"^\([a-z]\)\s*", "", text).strip()
        cleaned = re.sub(r"^\d+\.\s*", "", cleaned).strip()

        if not cleaned or len(cleaned) > 200 or len(cleaned) < 3:
            continue

        match = re.match(r"^([^(]+?)(?:\s*\(([^)]+)\))?\s*\.?\s*$", cleaned)
        if match:
            primary = match.group(1).strip().rstrip(".")
            synonyms_text = match.group(2)

            if not primary or len(primary) < 2:
                continue

            if any(
                w in primary.lower()
                for w in [
                    "the following", "approved", "variety",
                    "administrator", "wine", "section", "designation",
                ]
            ):
                continue

            synonyms = []
            if synonyms_text:
                synonyms = [
                    s.strip() for s in synonyms_text.split(",")
                    if s.strip()
                ]

            if primary not in seen:
                seen.add(primary)
                varieties.append({
                    "name": primary,
                    "synonyms": synonyms,
                })

    logger.info(f"Parsed {len(varieties)} grape varieties from eCFR XML")
    return varieties


def _scrape_varieties(session: requests.Session) -> list[dict]:
    """Scrape approved grape variety names. Returns list of variety dicts."""
    urls = SOURCES_CONFIG["varieties"]["urls"]
    varieties = []

    # Try eCFR HTML page
    html = _fetch_url(session, urls["ecfr_html"])
    if html:
        varieties = _parse_ecfr_varieties_html(html)

    # If HTML parsing yielded nothing, try XML API
    if not varieties:
        xml_text = _fetch_url(session, urls["ecfr_api"])
        if xml_text:
            varieties = _parse_ecfr_varieties_xml(xml_text)

    # If live scraping returned nothing, use fallback
    if not varieties:
        logger.warning(
            "Live variety scraping returned no results; using fallback data"
        )
        varieties = _get_fallback_varieties()

    logger.info(f"Total variety records: {len(varieties)}")
    return varieties


def _build_variety_facts(
    varieties: list[dict], source_id: str
) -> list[dict]:
    """Convert variety records to atomic facts."""
    facts = []
    seen = set()

    for var in varieties:
        name = var.get("name", "").strip()
        if not name:
            continue

        synonyms = var.get("synonyms", [])

        entities = [{"type": "grape", "name": name}]

        # Fact: Approved variety name
        key = f"variety_approved:{name}"
        if key not in seen:
            seen.add(key)
            facts.append({
                "fact_text": (
                    f"{name} is an approved grape variety name for "
                    f"use on US wine labels per TTB regulations."
                ),
                "domain": "grape_varieties",
                "subdomain": "us_labeling",
                "source_id": source_id,
                "entities": entities,
                "confidence": 1.0,
                "tags": ["grape", "us", "labeling", "ttb"],
            })

        # Fact: Synonym relationships
        for synonym in synonyms:
            synonym = synonym.strip()
            if not synonym:
                continue
            key = f"variety_synonym:{name}:{synonym}"
            if key not in seen:
                seen.add(key)
                facts.append({
                    "fact_text": (
                        f"{synonym} is an approved synonym for {name} "
                        f"on US wine labels."
                    ),
                    "domain": "grape_varieties",
                    "subdomain": "us_labeling",
                    "source_id": source_id,
                    "entities": [
                        {"type": "grape", "name": name},
                        {"type": "grape", "name": synonym},
                    ],
                    "confidence": 1.0,
                    "tags": ["grape", "us", "labeling", "synonym"],
                })

    logger.info(
        f"Built {len(facts)} variety facts from {len(varieties)} records"
    )
    return facts


# ═════════════════════════════════════════════════════════════════════════════
#  REGULATION FACTS (27 CFR Part 4)
# ═════════════════════════════════════════════════════════════════════════════

# These are stable, codified regulations from 27 CFR Part 4.
# They are US government public domain text, rephrased into atomic facts.

_REGULATION_FACTS = [
    # ── 27 CFR § 4.23 — Varietal (grape type) labeling ──
    {
        "text": (
            "US wine labeled with a single varietal name must contain at "
            "least 75% of that grape variety."
        ),
        "domain": "winemaking",
        "subdomain": "us_labeling",
        "section": "27 CFR 4.23",
        "tags": ["regulation", "us", "varietal", "labeling"],
    },
    {
        "text": (
            "The 75% varietal minimum for US wine labels applies to grapes "
            "grown in the labeled appellation of origin area."
        ),
        "domain": "winemaking",
        "subdomain": "us_labeling",
        "section": "27 CFR 4.23",
        "tags": ["regulation", "us", "varietal", "appellation"],
    },
    {
        "text": (
            "US wine made from Vitis labrusca varieties may use the variety "
            "name if at least 51% of the wine is from that grape."
        ),
        "domain": "winemaking",
        "subdomain": "us_labeling",
        "section": "27 CFR 4.23",
        "tags": ["regulation", "us", "varietal", "labrusca"],
    },
    {
        "text": (
            "A US wine label listing two or more grape varieties must state "
            "the percentage of each variety, with a tolerance of plus or "
            "minus 2%."
        ),
        "domain": "winemaking",
        "subdomain": "us_labeling",
        "section": "27 CFR 4.23",
        "tags": ["regulation", "us", "varietal", "labeling"],
    },
    {
        "text": (
            "A US wine labeled with multiple grape varieties must be made "
            "entirely from the listed varieties."
        ),
        "domain": "winemaking",
        "subdomain": "us_labeling",
        "section": "27 CFR 4.23",
        "tags": ["regulation", "us", "varietal", "labeling"],
    },
    {
        "text": (
            "A grape variety name may be used as a type designation for "
            "American wine only if that name has been approved by the "
            "TTB Administrator."
        ),
        "domain": "winemaking",
        "subdomain": "us_labeling",
        "section": "27 CFR 4.23",
        "tags": ["regulation", "us", "varietal", "approval"],
    },
    {
        "text": (
            "Varietal wine labeling in the US requires the wine to also "
            "carry an appellation of origin."
        ),
        "domain": "winemaking",
        "subdomain": "us_labeling",
        "section": "27 CFR 4.23",
        "tags": ["regulation", "us", "varietal", "appellation"],
    },

    # ── 27 CFR § 4.25 — Appellation of origin ──
    {
        "text": (
            "Wine labeled with an American Viticultural Area (AVA) must "
            "contain at least 85% grapes from that AVA."
        ),
        "domain": "wine_regions",
        "subdomain": "us_labeling",
        "section": "27 CFR 4.25",
        "tags": ["regulation", "us", "ava", "appellation"],
    },
    {
        "text": (
            "Wine labeled with a US state appellation must contain at "
            "least 75% grapes from that state."
        ),
        "domain": "wine_regions",
        "subdomain": "us_labeling",
        "section": "27 CFR 4.25",
        "tags": ["regulation", "us", "state", "appellation"],
    },
    {
        "text": (
            "Wine labeled with a US county appellation must contain at "
            "least 75% grapes from that county."
        ),
        "domain": "wine_regions",
        "subdomain": "us_labeling",
        "section": "27 CFR 4.25",
        "tags": ["regulation", "us", "county", "appellation"],
    },
    {
        "text": (
            "Wine labeled with a multi-state or multi-county appellation "
            "in the US must contain 100% grapes from the stated areas."
        ),
        "domain": "wine_regions",
        "subdomain": "us_labeling",
        "section": "27 CFR 4.25",
        "tags": ["regulation", "us", "multistate", "appellation"],
    },
    {
        "text": (
            "An American Viticultural Area (AVA) is a delimited grape-growing "
            "region with specific geographic or climatic features that "
            "distinguish it from surrounding regions."
        ),
        "domain": "wine_regions",
        "subdomain": "us_avas",
        "section": "27 CFR Part 9",
        "tags": ["regulation", "us", "ava", "definition"],
    },

    # ── 27 CFR § 4.25a — Estate bottled ──
    {
        "text": (
            "Estate Bottled wine in the US must be made entirely from grapes "
            "grown on land owned or controlled by the bottling winery."
        ),
        "domain": "winemaking",
        "subdomain": "us_labeling",
        "section": "27 CFR 4.25a",
        "tags": ["regulation", "us", "estate_bottled"],
    },
    {
        "text": (
            "Estate Bottled wine must be bottled at the winery premises and "
            "the winery must be located within the labeled viticultural area."
        ),
        "domain": "winemaking",
        "subdomain": "us_labeling",
        "section": "27 CFR 4.25a",
        "tags": ["regulation", "us", "estate_bottled"],
    },
    {
        "text": (
            "The Estate Bottled designation in the US requires the wine to "
            "be labeled with a viticultural area appellation of origin."
        ),
        "domain": "winemaking",
        "subdomain": "us_labeling",
        "section": "27 CFR 4.25a",
        "tags": ["regulation", "us", "estate_bottled", "ava"],
    },
    {
        "text": (
            "For Estate Bottled US wine, crushing, fermenting, finishing, "
            "aging, and bottling must all occur at the winery premises."
        ),
        "domain": "winemaking",
        "subdomain": "us_labeling",
        "section": "27 CFR 4.25a",
        "tags": ["regulation", "us", "estate_bottled", "production"],
    },

    # ── 27 CFR § 4.27 — Vintage date ──
    {
        "text": (
            "US wine labeled with a vintage date must contain at least 95% "
            "wine from grapes harvested in the stated year."
        ),
        "domain": "winemaking",
        "subdomain": "us_labeling",
        "section": "27 CFR 4.27",
        "tags": ["regulation", "us", "vintage", "labeling"],
    },
    {
        "text": (
            "A vintage date on US wine requires the wine to carry an "
            "appellation of origin other than a country."
        ),
        "domain": "winemaking",
        "subdomain": "us_labeling",
        "section": "27 CFR 4.27",
        "tags": ["regulation", "us", "vintage", "appellation"],
    },

    # ── 27 CFR § 4.36 — Alcohol content / tolerance ──
    {
        "text": (
            "US table wine with 14% alcohol or less has a labeling tolerance "
            "of plus or minus 1.5% actual alcohol by volume."
        ),
        "domain": "winemaking",
        "subdomain": "us_labeling",
        "section": "27 CFR 4.36",
        "tags": ["regulation", "us", "alcohol", "tolerance"],
    },
    {
        "text": (
            "US wine with more than 14% alcohol has a labeling tolerance "
            "of plus or minus 1.0% actual alcohol by volume."
        ),
        "domain": "winemaking",
        "subdomain": "us_labeling",
        "section": "27 CFR 4.36",
        "tags": ["regulation", "us", "alcohol", "tolerance"],
    },

    # ── 27 CFR § 4.21 — Wine classes and types ──
    {
        "text": (
            "US table wine (or light wine) is grape wine with an alcohol "
            "content not in excess of 14% by volume."
        ),
        "domain": "winemaking",
        "subdomain": "us_labeling",
        "section": "27 CFR 4.21",
        "tags": ["regulation", "us", "wine_class", "table_wine"],
    },
    {
        "text": (
            "US dessert wine is grape wine with an alcohol content in excess "
            "of 14% but not exceeding 24% by volume."
        ),
        "domain": "winemaking",
        "subdomain": "us_labeling",
        "section": "27 CFR 4.21",
        "tags": ["regulation", "us", "wine_class", "dessert_wine"],
    },

    # ── 27 CFR § 4.24 — Semi-generic designations ──
    {
        "text": (
            "Semi-generic wine names such as Burgundy, Chablis, Champagne, "
            "and Chianti may be used on US wine labels only with a geographic "
            "qualifier indicating true place of origin."
        ),
        "domain": "winemaking",
        "subdomain": "us_labeling",
        "section": "27 CFR 4.24",
        "tags": ["regulation", "us", "semi_generic", "labeling"],
    },
    {
        "text": (
            "Since 2006, new US wine producers may not use semi-generic "
            "wine type designations such as Champagne or Burgundy on labels."
        ),
        "domain": "winemaking",
        "subdomain": "us_labeling",
        "section": "27 CFR 4.24",
        "tags": ["regulation", "us", "semi_generic", "labeling"],
    },

    # ── General TTB / AVA facts ──
    {
        "text": (
            "The TTB (Alcohol and Tobacco Tax and Trade Bureau) is the US "
            "federal agency responsible for regulating wine labeling."
        ),
        "domain": "wine_business",
        "subdomain": "us_regulation",
        "section": "27 USC Chapter 8",
        "tags": ["regulation", "us", "ttb", "agency"],
    },
    {
        "text": (
            "AVA boundaries in the US are defined in 27 CFR Part 9 and "
            "established through the Federal Register rulemaking process."
        ),
        "domain": "wine_regions",
        "subdomain": "us_avas",
        "section": "27 CFR Part 9",
        "tags": ["regulation", "us", "ava", "boundaries"],
    },
    {
        "text": (
            "The Augusta AVA in Missouri was the first AVA established in "
            "the United States, on June 20, 1980."
        ),
        "domain": "wine_regions",
        "subdomain": "us_avas",
        "section": "27 CFR 9.18",
        "tags": ["ava", "us", "history", "missouri"],
    },
    {
        "text": (
            "California has the most American Viticultural Areas of any US "
            "state, with over 150 established AVAs."
        ),
        "domain": "wine_regions",
        "subdomain": "us_avas",
        "section": "27 CFR Part 9",
        "tags": ["ava", "us", "california", "statistics"],
    },
    {
        "text": (
            "The Upper Mississippi River Valley AVA spans four states and "
            "is the largest AVA by area in the United States."
        ),
        "domain": "wine_regions",
        "subdomain": "us_avas",
        "section": "27 CFR 9.226",
        "tags": ["ava", "us", "geography", "multistate"],
    },
    {
        "text": (
            "Cole Ranch AVA in Mendocino County, California, is one of "
            "the smallest AVAs in the United States at approximately "
            "60 acres."
        ),
        "domain": "wine_regions",
        "subdomain": "us_avas",
        "section": "27 CFR 9.60",
        "tags": ["ava", "us", "california", "geography"],
    },
    {
        "text": (
            "US wine labeled with a brand name that includes an AVA name "
            "must meet the 85% grape sourcing requirement for that AVA."
        ),
        "domain": "winemaking",
        "subdomain": "us_labeling",
        "section": "27 CFR 4.39",
        "tags": ["regulation", "us", "ava", "brand_name"],
    },
    {
        "text": (
            "Health warning statements are required on all US wine labels "
            "with alcohol content of 0.5% or more by volume."
        ),
        "domain": "winemaking",
        "subdomain": "us_labeling",
        "section": "27 CFR 16.21",
        "tags": ["regulation", "us", "health_warning", "labeling"],
    },
    {
        "text": (
            "US wine labels must include the name and address of the "
            "bottler, packer, or importer."
        ),
        "domain": "winemaking",
        "subdomain": "us_labeling",
        "section": "27 CFR 4.35",
        "tags": ["regulation", "us", "labeling", "bottler"],
    },
    {
        "text": (
            "US wine must display its alcohol content on the label, expressed "
            "as a percentage of alcohol by volume."
        ),
        "domain": "winemaking",
        "subdomain": "us_labeling",
        "section": "27 CFR 4.36",
        "tags": ["regulation", "us", "alcohol", "labeling"],
    },
    {
        "text": (
            "US wine labels must include a net contents statement showing "
            "the volume of wine in the container."
        ),
        "domain": "winemaking",
        "subdomain": "us_labeling",
        "section": "27 CFR 4.37",
        "tags": ["regulation", "us", "labeling", "volume"],
    },
    {
        "text": (
            "US wine containing sulfites above 10 parts per million must "
            "include a 'Contains Sulfites' declaration on the label."
        ),
        "domain": "winemaking",
        "subdomain": "us_labeling",
        "section": "27 CFR 4.32",
        "tags": ["regulation", "us", "sulfites", "labeling"],
    },
]


def _build_regulation_facts(source_id: str) -> list[dict]:
    """Build atomic facts from codified 27 CFR Part 4 regulations."""
    facts = []

    for reg in _REGULATION_FACTS:
        facts.append({
            "fact_text": reg["text"],
            "domain": reg["domain"],
            "subdomain": reg["subdomain"],
            "source_id": source_id,
            "entities": [
                {"type": "regulation", "name": reg["section"]},
            ],
            "confidence": 1.0,
            "tags": reg["tags"],
        })

    logger.info(f"Built {len(facts)} regulation facts")
    return facts


# ═════════════════════════════════════════════════════════════════════════════
#  FALLBACK DATA
# ═════════════════════════════════════════════════════════════════════════════

def _get_fallback_avas() -> list[dict]:
    """Comprehensive fallback list of established US AVAs.

    Used when the live TTB website scrape fails.
    Data sourced from TTB public records (US Government, public domain).
    """
    # fmt: off
    return [
        {"name": "Augusta", "state": "MO", "year": "1980"},
        {"name": "Napa Valley", "state": "CA", "year": "1981"},
        {"name": "Sonoma Valley", "state": "CA", "year": "1982"},
        {"name": "Alexander Valley", "state": "CA", "year": "1984"},
        {"name": "Dry Creek Valley", "state": "CA", "year": "1983"},
        {"name": "Russian River Valley", "state": "CA", "year": "1983"},
        {"name": "Willamette Valley", "state": "OR", "year": "1984"},
        {"name": "Paso Robles", "state": "CA", "year": "1983"},
        {"name": "Santa Maria Valley", "state": "CA", "year": "1981"},
        {"name": "Santa Ynez Valley", "state": "CA", "year": "1983"},
        {"name": "Edna Valley", "state": "CA", "year": "1982"},
        {"name": "Arroyo Seco", "state": "CA", "year": "1983"},
        {"name": "Chalk Hill", "state": "CA", "year": "1983"},
        {"name": "Knights Valley", "state": "CA", "year": "1983"},
        {"name": "Los Carneros", "state": "CA", "year": "1983"},
        {"name": "Anderson Valley", "state": "CA", "year": "1983"},
        {"name": "Mendocino", "state": "CA", "year": "1984"},
        {"name": "Sonoma County", "state": "CA", "year": "1982"},
        {"name": "Stags Leap District", "state": "CA", "year": "1989"},
        {"name": "Rutherford", "state": "CA", "year": "1993"},
        {"name": "Oakville", "state": "CA", "year": "1993"},
        {"name": "Spring Mountain District", "state": "CA", "year": "1993"},
        {"name": "Mount Veeder", "state": "CA", "year": "1990"},
        {"name": "Howell Mountain", "state": "CA", "year": "1984"},
        {"name": "Atlas Peak", "state": "CA", "year": "1992"},
        {"name": "Diamond Mountain District", "state": "CA", "year": "2001"},
        {"name": "Calistoga", "state": "CA", "year": "2010"},
        {"name": "Coombsville", "state": "CA", "year": "2011"},
        {"name": "Wild Horse Valley", "state": "CA", "year": "1988"},
        {"name": "Yountville", "state": "CA", "year": "1999"},
        {"name": "St. Helena", "state": "CA", "year": "1995"},
        {"name": "Chiles Valley", "state": "CA", "year": "1999"},
        {"name": "Oak Knoll District of Napa Valley", "state": "CA", "year": "2004"},
        {"name": "Sonoma Coast", "state": "CA", "year": "1987"},
        {"name": "Green Valley of Russian River Valley", "state": "CA", "year": "1983"},
        {"name": "Bennett Valley", "state": "CA", "year": "2003"},
        {"name": "Rockpile", "state": "CA", "year": "2002"},
        {"name": "Moon Mountain District Sonoma County", "state": "CA", "year": "2013"},
        {"name": "Fort Ross-Seaview", "state": "CA", "year": "2012"},
        {"name": "Petaluma Gap", "state": "CA", "year": "2017"},
        {"name": "Pine Mountain-Cloverdale Peak", "state": "CA", "year": "2011"},
        {"name": "Fountaingrove District", "state": "CA", "year": "2015"},
        {"name": "West Sonoma Coast", "state": "CA", "year": "2022"},
        {"name": "Livermore Valley", "state": "CA", "year": "1982"},
        {"name": "Santa Cruz Mountains", "state": "CA", "year": "1982"},
        {"name": "San Ysidro District", "state": "CA", "year": "1990"},
        {"name": "Ben Lomond Mountain", "state": "CA", "year": "1988"},
        {"name": "Pacheco Pass", "state": "CA", "year": "1984"},
        {"name": "Mount Harlan", "state": "CA", "year": "1990"},
        {"name": "Cienega Valley", "state": "CA", "year": "1982"},
        {"name": "Lime Kiln Valley", "state": "CA", "year": "1982"},
        {"name": "Carmel Valley", "state": "CA", "year": "1983"},
        {"name": "Monterey", "state": "CA", "year": "1984"},
        {"name": "Chalone", "state": "CA", "year": "1982"},
        {"name": "San Lucas", "state": "CA", "year": "1987"},
        {"name": "Hames Valley", "state": "CA", "year": "1994"},
        {"name": "San Bernabe", "state": "CA", "year": "2004"},
        {"name": "San Antonio Valley", "state": "CA", "year": "2006"},
        {"name": "Central Coast", "state": "CA", "year": "1985"},
        {"name": "South Coast", "state": "CA", "year": "1985"},
        {"name": "Temecula Valley", "state": "CA", "year": "1984"},
        {"name": "San Pasqual Valley", "state": "CA", "year": "1981"},
        {"name": "Ramona Valley", "state": "CA", "year": "2006"},
        {"name": "Malibu Coast", "state": "CA", "year": "2014"},
        {"name": "Leona Valley", "state": "CA", "year": "2009"},
        {"name": "Antelope Valley of the California High Desert", "state": "CA", "year": "2011"},
        {"name": "Cucamonga Valley", "state": "CA", "year": "1995"},
        {"name": "Sierra Foothills", "state": "CA", "year": "1987"},
        {"name": "El Dorado", "state": "CA", "year": "1983"},
        {"name": "Fiddletown", "state": "CA", "year": "1983"},
        {"name": "Shenandoah Valley of California", "state": "CA", "year": "1983"},
        {"name": "North Yuba", "state": "CA", "year": "1985"},
        {"name": "Fair Play", "state": "CA", "year": "2001"},
        {"name": "Lodi", "state": "CA", "year": "1986"},
        {"name": "Clarksburg", "state": "CA", "year": "1984"},
        {"name": "Merritt Island", "state": "CA", "year": "1983"},
        {"name": "Dunnigan Hills", "state": "CA", "year": "1993"},
        {"name": "Suisun Valley", "state": "CA", "year": "1982"},
        {"name": "Solano County Green Valley", "state": "CA", "year": "1983"},
        {"name": "Lake County", "state": "CA", "year": "2004"},
        {"name": "Clear Lake", "state": "CA", "year": "1984"},
        {"name": "Guenoc Valley", "state": "CA", "year": "1981"},
        {"name": "Benmore Valley", "state": "CA", "year": "1991"},
        {"name": "Red Hills Lake County", "state": "CA", "year": "2004"},
        {"name": "High Valley", "state": "CA", "year": "2005"},
        {"name": "Kelsey Bench-Lake County", "state": "CA", "year": "2014"},
        {"name": "Big Valley District-Lake County", "state": "CA", "year": "2014"},
        {"name": "Cole Ranch", "state": "CA", "year": "1983"},
        {"name": "McDowell Valley", "state": "CA", "year": "1982"},
        {"name": "Potter Valley", "state": "CA", "year": "1983"},
        {"name": "Redwood Valley", "state": "CA", "year": "1997"},
        {"name": "Mendocino Ridge", "state": "CA", "year": "1997"},
        {"name": "Yorkville Highlands", "state": "CA", "year": "1998"},
        {"name": "Dos Rios", "state": "CA", "year": "2005"},
        {"name": "Covelo", "state": "CA", "year": "2006"},
        {"name": "Eagle Peak Mendocino County", "state": "CA", "year": "2014"},
        {"name": "Comptche", "state": "CA", "year": "2024"},
        {"name": "Crystal Springs of Napa Valley", "state": "CA", "year": "2024"},
        {"name": "Happy Canyon of Santa Barbara", "state": "CA", "year": "2009"},
        {"name": "Sta. Rita Hills", "state": "CA", "year": "2001"},
        {"name": "Ballard Canyon", "state": "CA", "year": "2013"},
        {"name": "Los Olivos District", "state": "CA", "year": "2016"},
        {"name": "Alisos Canyon", "state": "CA", "year": "2020"},
        {"name": "Santa Barbara County", "state": "CA", "year": "2022"},
        {"name": "San Luis Obispo Coast", "state": "CA", "year": "2022"},
        {"name": "Adelaida District", "state": "CA", "year": "2014"},
        {"name": "Creston District", "state": "CA", "year": "2014"},
        {"name": "El Pomar District", "state": "CA", "year": "2014"},
        {"name": "Estrella District", "state": "CA", "year": "2014"},
        {"name": "Geneseo District", "state": "CA", "year": "2014"},
        {"name": "Highlands District", "state": "CA", "year": "2014"},
        {"name": "Nacimiento", "state": "CA", "year": "2014"},
        {"name": "Paso Robles Willow Creek District", "state": "CA", "year": "2014"},
        {"name": "San Juan Creek", "state": "CA", "year": "2014"},
        {"name": "San Miguel District", "state": "CA", "year": "2014"},
        {"name": "Santa Margarita Ranch", "state": "CA", "year": "2014"},
        {"name": "Templeton Gap District", "state": "CA", "year": "2014"},
        {"name": "York Mountain", "state": "CA", "year": "1983"},
        {"name": "Arroyo Grande Valley", "state": "CA", "year": "1990"},
        {"name": "Umpqua Valley", "state": "OR", "year": "1984"},
        {"name": "Rogue Valley", "state": "OR", "year": "1992"},
        {"name": "Applegate Valley", "state": "OR", "year": "2001"},
        {"name": "Columbia Valley", "state": "WA", "year": "1984"},
        {"name": "Yakima Valley", "state": "WA", "year": "1983"},
        {"name": "Walla Walla Valley", "state": "WA", "year": "1984"},
        {"name": "Red Mountain", "state": "WA", "year": "2001"},
        {"name": "Columbia Gorge", "state": "WA", "year": "2004"},
        {"name": "Horse Heaven Hills", "state": "WA", "year": "2005"},
        {"name": "Wahluke Slope", "state": "WA", "year": "2006"},
        {"name": "Rattlesnake Hills", "state": "WA", "year": "2006"},
        {"name": "Snipes Mountain", "state": "WA", "year": "2009"},
        {"name": "Lake Chelan", "state": "WA", "year": "2009"},
        {"name": "Naches Heights", "state": "WA", "year": "2012"},
        {"name": "Ancient Lakes of Columbia Valley", "state": "WA", "year": "2012"},
        {"name": "Lewis-Clark Valley", "state": "WA", "year": "2016"},
        {"name": "The Burn of Columbia Valley", "state": "WA", "year": "2019"},
        {"name": "White Bluffs", "state": "WA", "year": "2020"},
        {"name": "Royal Slope", "state": "WA", "year": "2020"},
        {"name": "Goose Gap", "state": "WA", "year": "2021"},
        {"name": "Candy Mountain", "state": "WA", "year": "2020"},
        {"name": "The Rocks District of Milton-Freewater", "state": "OR", "year": "2015"},
        {"name": "Ribbon Ridge", "state": "OR", "year": "2005"},
        {"name": "Dundee Hills", "state": "OR", "year": "2005"},
        {"name": "Yamhill-Carlton", "state": "OR", "year": "2004"},
        {"name": "McMinnville", "state": "OR", "year": "2005"},
        {"name": "Eola-Amity Hills", "state": "OR", "year": "2006"},
        {"name": "Chehalem Mountains", "state": "OR", "year": "2006"},
        {"name": "Van Duzer Corridor", "state": "OR", "year": "2019"},
        {"name": "Tualatin Hills", "state": "OR", "year": "2020"},
        {"name": "Laurelwood District", "state": "OR", "year": "2020"},
        {"name": "Lower Long Tom", "state": "OR", "year": "2021"},
        {"name": "Mount Pisgah", "state": "OR", "year": "2022"},
        {"name": "Elkton Oregon", "state": "OR", "year": "2013"},
        {"name": "Southern Oregon", "state": "OR", "year": "2004"},
        {"name": "Snake River Valley", "state": "ID", "year": "2007"},
        {"name": "Eagle Foothills", "state": "ID", "year": "2015"},
        {"name": "Finger Lakes", "state": "NY", "year": "1982"},
        {"name": "North Fork of Long Island", "state": "NY", "year": "1986"},
        {"name": "The Hamptons Long Island", "state": "NY", "year": "1985"},
        {"name": "Hudson River Region", "state": "NY", "year": "1982"},
        {"name": "Cayuga Lake", "state": "NY", "year": "1988"},
        {"name": "Seneca Lake", "state": "NY", "year": "2003"},
        {"name": "Long Island", "state": "NY", "year": "2001"},
        {"name": "Niagara Escarpment", "state": "NY", "year": "2005"},
        {"name": "Lake Erie", "state": "NY", "year": "1983"},
        {"name": "Monticello", "state": "VA", "year": "1984"},
        {"name": "North Fork of Roanoke", "state": "VA", "year": "1983"},
        {"name": "Rocky Knob", "state": "VA", "year": "1983"},
        {"name": "Shenandoah Valley", "state": "VA", "year": "1982"},
        {"name": "Virginia's Eastern Shore", "state": "VA", "year": "1991"},
        {"name": "Northern Neck George Washington Birthplace", "state": "VA", "year": "1987"},
        {"name": "Middleburg Virginia", "state": "VA", "year": "2012"},
        {"name": "North Georgia", "state": "GA", "year": "2018"},
        {"name": "Texas Hill Country", "state": "TX", "year": "1991"},
        {"name": "Texas High Plains", "state": "TX", "year": "1992"},
        {"name": "Bell Mountain", "state": "TX", "year": "1986"},
        {"name": "Fredericksburg in the Texas Hill Country", "state": "TX", "year": "1988"},
        {"name": "Escondido Valley", "state": "TX", "year": "1992"},
        {"name": "Mesilla Valley", "state": "NM", "year": "1985"},
        {"name": "Mimbres Valley", "state": "NM", "year": "1985"},
        {"name": "Middle Rio Grande Valley", "state": "NM", "year": "1988"},
        {"name": "Ozark Mountain", "state": "MO", "year": "1986"},
        {"name": "Hermann", "state": "MO", "year": "1983"},
        {"name": "Ozark Highlands", "state": "MO", "year": "1987"},
        {"name": "Kanawha River Valley", "state": "WV", "year": "1986"},
        {"name": "Ohio River Valley", "state": "OH", "year": "1983"},
        {"name": "Isle St. George", "state": "OH", "year": "1982"},
        {"name": "Grand River Valley", "state": "OH", "year": "1983"},
        {"name": "Loramie Creek", "state": "OH", "year": "1982"},
        {"name": "Old Mission Peninsula", "state": "MI", "year": "1987"},
        {"name": "Fennville", "state": "MI", "year": "1981"},
        {"name": "Leelanau Peninsula", "state": "MI", "year": "1982"},
        {"name": "Lake Michigan Shore", "state": "MI", "year": "1983"},
        {"name": "Tip of the Mitt", "state": "MI", "year": "2016"},
        {"name": "Upper Mississippi River Valley", "state": "MN", "year": "2009"},
        {"name": "Alexandria Lakes", "state": "MN", "year": "2018"},
        {"name": "Altus", "state": "AR", "year": "1984"},
        {"name": "Arkansas Mountain", "state": "AR", "year": "1986"},
        {"name": "Mississippi Delta", "state": "MS", "year": "1984"},
        {"name": "Central Delaware Valley", "state": "PA", "year": "1984"},
        {"name": "Lancaster Valley", "state": "PA", "year": "1982"},
        {"name": "Lehigh Valley", "state": "PA", "year": "2008"},
        {"name": "Cumberland Valley", "state": "PA", "year": "1985"},
        {"name": "Southeastern New England", "state": "CT", "year": "1984"},
        {"name": "Western Connecticut Highlands", "state": "CT", "year": "1988"},
        {"name": "Martha's Vineyard", "state": "MA", "year": "1985"},
        {"name": "Warren Hills", "state": "NJ", "year": "1988"},
        {"name": "Outer Coastal Plain", "state": "NJ", "year": "2007"},
        {"name": "Yadkin Valley", "state": "NC", "year": "2003"},
        {"name": "Swan Creek", "state": "NC", "year": "2008"},
        {"name": "Haw River Valley", "state": "NC", "year": "2009"},
        {"name": "Upper Hiwassee Highlands", "state": "NC", "year": "2014"},
        {"name": "Cane Creek Valley", "state": "NC", "year": "2020"},
        {"name": "Tryon Foothills", "state": "NC", "year": "2025"},
        {"name": "Puget Sound", "state": "WA", "year": "1995"},
        {"name": "Sonoita", "state": "AZ", "year": "1984"},
        {"name": "Willcox", "state": "AZ", "year": "2016"},
        {"name": "Verde Valley", "state": "AZ", "year": "2022"},
        {"name": "Grand Valley", "state": "CO", "year": "1991"},
        {"name": "West Elks", "state": "CO", "year": "2001"},
        {"name": "Hualapai Valley", "state": "AZ", "year": "2023"},
    ]
    # fmt: on


def _get_fallback_varieties() -> list[dict]:
    """Comprehensive fallback list of TTB-approved grape variety names.

    From 27 CFR 4.91 (US Government, public domain).
    """
    # fmt: off
    return [
        {"name": "Aglianico", "synonyms": []},
        {"name": "Albariño", "synonyms": ["Alvarinho"]},
        {"name": "Aleatico", "synonyms": []},
        {"name": "Alicante Bouschet", "synonyms": []},
        {"name": "Aligoté", "synonyms": []},
        {"name": "Arneis", "synonyms": []},
        {"name": "Auxerrois", "synonyms": []},
        {"name": "Barbera", "synonyms": []},
        {"name": "Béclan", "synonyms": ["Beclan"]},
        {"name": "Blanc Du Bois", "synonyms": []},
        {"name": "Blaufränkisch", "synonyms": ["Lemberger"]},
        {"name": "Bourboulenc", "synonyms": []},
        {"name": "Brachetto", "synonyms": []},
        {"name": "Burger", "synonyms": []},
        {"name": "Cabernet Franc", "synonyms": []},
        {"name": "Cabernet Pfeffer", "synonyms": []},
        {"name": "Cabernet Sauvignon", "synonyms": []},
        {"name": "Carignan", "synonyms": ["Carignane"]},
        {"name": "Carménère", "synonyms": []},
        {"name": "Catawba", "synonyms": []},
        {"name": "Cayuga White", "synonyms": []},
        {"name": "Centurion", "synonyms": []},
        {"name": "Chambourcin", "synonyms": []},
        {"name": "Chancellor", "synonyms": []},
        {"name": "Charbono", "synonyms": []},
        {"name": "Chardonnay", "synonyms": []},
        {"name": "Chasselas Doré", "synonyms": ["Chasselas doré"]},
        {"name": "Chelois", "synonyms": []},
        {"name": "Chenin Blanc", "synonyms": []},
        {"name": "Cinsaut", "synonyms": ["Cinsault"]},
        {"name": "Colombard", "synonyms": ["French Colombard"]},
        {"name": "Concord", "synonyms": []},
        {"name": "Cortese", "synonyms": []},
        {"name": "Corvina", "synonyms": []},
        {"name": "Counoise", "synonyms": []},
        {"name": "Cynthiana", "synonyms": ["Norton"]},
        {"name": "De Chaunac", "synonyms": []},
        {"name": "Delaware", "synonyms": []},
        {"name": "Dolcetto", "synonyms": []},
        {"name": "Dornfelder", "synonyms": []},
        {"name": "Durif", "synonyms": ["Petite Sirah"]},
        {"name": "Ehrenfelser", "synonyms": []},
        {"name": "Elvira", "synonyms": []},
        {"name": "Emerald Riesling", "synonyms": []},
        {"name": "Fernão Pires", "synonyms": []},
        {"name": "Flora", "synonyms": []},
        {"name": "Folle Blanche", "synonyms": []},
        {"name": "Fredonia", "synonyms": []},
        {"name": "Freisa", "synonyms": []},
        {"name": "Fumé Blanc", "synonyms": ["Sauvignon Blanc"]},
        {"name": "Gamay Noir", "synonyms": ["Gamay"]},
        {"name": "Garganega", "synonyms": []},
        {"name": "Gewürztraminer", "synonyms": []},
        {"name": "Graciano", "synonyms": []},
        {"name": "Grand Noir", "synonyms": []},
        {"name": "Green Hungarian", "synonyms": []},
        {"name": "Grenache", "synonyms": ["Garnacha"]},
        {"name": "Grenache Blanc", "synonyms": []},
        {"name": "Grenache Gris", "synonyms": ["Garnacha Roja"]},
        {"name": "Grignolino", "synonyms": []},
        {"name": "Grüner Veltliner", "synonyms": []},
        {"name": "Ives", "synonyms": []},
        {"name": "Johannisberg Riesling", "synonyms": ["Riesling"]},
        {"name": "Kerner", "synonyms": []},
        {"name": "Lagrein", "synonyms": []},
        {"name": "Lambrusco", "synonyms": ["Colorino"]},
        {"name": "Landot Noir", "synonyms": []},
        {"name": "Léon Millot", "synonyms": []},
        {"name": "Loureiro", "synonyms": []},
        {"name": "Malbec", "synonyms": []},
        {"name": "Malvasia Bianca", "synonyms": []},
        {"name": "Maréchal Foch", "synonyms": ["Foch"]},
        {"name": "Marsanne", "synonyms": []},
        {"name": "Mataro", "synonyms": ["Mourvèdre", "Monastrell"]},
        {"name": "Melon", "synonyms": ["Melon de Bourgogne"]},
        {"name": "Merlot", "synonyms": []},
        {"name": "Mission", "synonyms": []},
        {"name": "Mondeuse Noire", "synonyms": []},
        {"name": "Montepulciano", "synonyms": []},
        {"name": "Moscato", "synonyms": ["Muscat Blanc", "Muscat Canelli"]},
        {"name": "Mourvèdre", "synonyms": ["Monastrell", "Mataro"]},
        {"name": "Müller-Thurgau", "synonyms": []},
        {"name": "Muscadelle", "synonyms": []},
        {"name": "Muscadine", "synonyms": []},
        {"name": "Muscat of Alexandria", "synonyms": []},
        {"name": "Muscat Ottonel", "synonyms": []},
        {"name": "Nebbiolo", "synonyms": []},
        {"name": "Négrette", "synonyms": []},
        {"name": "Nero d'Avola", "synonyms": []},
        {"name": "Niagara", "synonyms": []},
        {"name": "Noiret", "synonyms": []},
        {"name": "Orange Muscat", "synonyms": []},
        {"name": "Palomino", "synonyms": []},
        {"name": "Pecorino", "synonyms": []},
        {"name": "Pedro Ximénez", "synonyms": []},
        {"name": "Petit Manseng", "synonyms": []},
        {"name": "Petit Verdot", "synonyms": []},
        {"name": "Petite Sirah", "synonyms": ["Durif"]},
        {"name": "Picpoul Blanc", "synonyms": []},
        {"name": "Pinotage", "synonyms": []},
        {"name": "Pinot Blanc", "synonyms": []},
        {"name": "Pinot Gris", "synonyms": ["Pinot Grigio"]},
        {"name": "Pinot Meunier", "synonyms": []},
        {"name": "Pinot Noir", "synonyms": []},
        {"name": "Primitivo", "synonyms": ["Zinfandel"]},
        {"name": "Refosco", "synonyms": []},
        {"name": "Ribolla Gialla", "synonyms": []},
        {"name": "Riesling", "synonyms": ["Johannisberg Riesling"]},
        {"name": "Rkatsiteli", "synonyms": []},
        {"name": "Roussanne", "synonyms": []},
        {"name": "Royalty", "synonyms": []},
        {"name": "Rubired", "synonyms": []},
        {"name": "Ruby Cabernet", "synonyms": []},
        {"name": "Sangiovese", "synonyms": []},
        {"name": "Salvador", "synonyms": []},
        {"name": "Sauvignon Blanc", "synonyms": ["Fumé Blanc"]},
        {"name": "Sauvignon Vert", "synonyms": []},
        {"name": "Scheurebe", "synonyms": []},
        {"name": "Sémillon", "synonyms": []},
        {"name": "Seyval Blanc", "synonyms": ["Seyval"]},
        {"name": "Silvaner", "synonyms": ["Sylvaner"]},
        {"name": "Souzão", "synonyms": []},
        {"name": "St. Croix", "synonyms": []},
        {"name": "Steuben", "synonyms": []},
        {"name": "Sultanina", "synonyms": ["Thompson Seedless"]},
        {"name": "Swenson Red", "synonyms": []},
        {"name": "Symphony", "synonyms": []},
        {"name": "Syrah", "synonyms": ["Shiraz"]},
        {"name": "Tannat", "synonyms": []},
        {"name": "Tempranillo", "synonyms": []},
        {"name": "Teroldego", "synonyms": []},
        {"name": "Tinta Amarela", "synonyms": ["Trincadeira"]},
        {"name": "Tinta Madeira", "synonyms": []},
        {"name": "Tinto Cão", "synonyms": []},
        {"name": "Touriga Nacional", "synonyms": []},
        {"name": "Traminer", "synonyms": []},
        {"name": "Trebbiano", "synonyms": []},
        {"name": "Trousseau", "synonyms": ["Trousseau Gris"]},
        {"name": "Valdiguié", "synonyms": []},
        {"name": "Valvin Muscat", "synonyms": []},
        {"name": "Verdejo", "synonyms": []},
        {"name": "Verdelho", "synonyms": []},
        {"name": "Verdicchio", "synonyms": []},
        {"name": "Vermentino", "synonyms": []},
        {"name": "Vidal Blanc", "synonyms": ["Vidal"]},
        {"name": "Vignoles", "synonyms": ["Ravat"]},
        {"name": "Viognier", "synonyms": []},
        {"name": "Zinfandel", "synonyms": ["Primitivo"]},
        {"name": "Zweigelt", "synonyms": []},
        {"name": "Baco Noir", "synonyms": []},
        {"name": "Baga", "synonyms": []},
        {"name": "Courbu Blanc", "synonyms": []},
        {"name": "Criolla Grande", "synonyms": []},
        {"name": "Frontenac", "synonyms": []},
        {"name": "Frontenac Gris", "synonyms": []},
        {"name": "Greco Bianco", "synonyms": []},
        {"name": "Clarion", "synonyms": []},
        {"name": "La Crescent", "synonyms": []},
        {"name": "Marquette", "synonyms": []},
        {"name": "Marsala", "synonyms": []},
        {"name": "Traminette", "synonyms": []},
        {"name": "Verduzzo", "synonyms": []},
        {"name": "Vinhão", "synonyms": []},
    ]
    # fmt: on


# ═════════════════════════════════════════════════════════════════════════════
#  CROSS-REFERENCE CHECK
# ═════════════════════════════════════════════════════════════════════════════


def _cross_reference_ava_count() -> None:
    """Compare TTB AVA count with any existing AVA/appellation data.

    Checks Wikidata-sourced or UC Davis-sourced US appellation data
    in the database for discrepancies.
    """
    try:
        from src.utils.db import get_pg

        conn = get_pg()
        cur = conn.cursor()

        # Count TTB AVA facts
        cur.execute(
            "SELECT count(*) AS cnt FROM facts "
            "WHERE subdomain = 'us_avas'"
        )
        ttb_count = cur.fetchone()["cnt"]

        # Count Wikidata US appellations
        cur.execute(
            "SELECT count(*) AS cnt FROM facts "
            "WHERE subdomain = 'appellations' "
            "AND fact_text LIKE '%%United States%%'"
        )
        wikidata_us_count = cur.fetchone()["cnt"]

        # Count any UC Davis AVA facts
        cur.execute(
            "SELECT count(*) AS cnt FROM facts "
            "WHERE tags @> ARRAY['uc_davis'] "
            "AND subdomain = 'us_avas'"
        )
        ucdavis_count = cur.fetchone()["cnt"]

        click.echo("\nAVA Cross-Reference:")
        click.echo(f"  TTB AVA facts:              {ttb_count}")
        if wikidata_us_count > 0:
            click.echo(f"  Wikidata US appellations:    {wikidata_us_count}")
            if ttb_count > 0 and wikidata_us_count > 0:
                diff = abs(ttb_count - wikidata_us_count)
                click.echo(
                    f"  Discrepancy:                 {diff} facts "
                    f"(TTB vs Wikidata)"
                )
        if ucdavis_count > 0:
            click.echo(f"  UC Davis AVA facts:          {ucdavis_count}")
        if wikidata_us_count == 0 and ucdavis_count == 0:
            click.echo("  No Wikidata or UC Davis AVA data loaded for comparison.")

    except Exception as e:
        logger.warning(f"Cross-reference check failed: {e}")
        click.echo(f"\nCross-reference check skipped (DB error: {e})")


# ═════════════════════════════════════════════════════════════════════════════
#  VALIDATION
# ═════════════════════════════════════════════════════════════════════════════


def validate_facts(facts: list[dict]) -> None:
    """Run quality checks on extracted facts and print a report."""
    if not facts:
        click.echo("No facts to validate.")
        return

    total = len(facts)

    # (a) Domain/subdomain distribution
    domain_counts: dict[str, int] = defaultdict(int)
    subdomain_counts: dict[str, int] = defaultdict(int)
    for f in facts:
        domain_counts[f["domain"]] += 1
        sub = f.get("subdomain") or "(none)"
        subdomain_counts[f"{f['domain']}/{sub}"] += 1

    click.echo("\nDomain distribution:")
    for domain, count in sorted(domain_counts.items()):
        click.echo(f"  {domain:25s}: {count} facts")

    click.echo("\nSubdomain distribution:")
    for sub, count in sorted(subdomain_counts.items()):
        click.echo(f"  {sub:45s}: {count} facts")

    # (b) Length checks
    too_short = [f for f in facts if len(f["fact_text"].split()) < 5]
    too_long = [f for f in facts if len(f["fact_text"].split()) > 50]
    click.echo(f"\nQuality:")
    click.echo(
        f"  Too short (<5 words):  {len(too_short)} "
        f"({100 * len(too_short) / total:.1f}%)"
    )
    click.echo(
        f"  Too long (>50 words):  {len(too_long)} "
        f"({100 * len(too_long) / total:.1f}%)"
    )
    if too_short:
        click.echo("    Short examples:")
        for f in too_short[:3]:
            click.echo(f'      "{f["fact_text"]}"')

    # (c) Entity-name-only facts (no predicate)
    no_predicate = [
        f for f in facts
        if len(f["fact_text"].rstrip(".").strip().split()) <= 2
    ]
    click.echo(
        f"  No-predicate facts:    {len(no_predicate)} "
        f"({100 * len(no_predicate) / total:.1f}%)"
    )

    # (d) Near-duplicate check (substring containment)
    near_dupes = 0
    fact_texts = [f["fact_text"] for f in facts]
    sample_size = min(len(fact_texts), 500)
    sampled = random.sample(fact_texts, sample_size)
    for i, a in enumerate(sampled):
        for b in sampled[i + 1:]:
            a_stripped = a.rstrip(".")
            b_stripped = b.rstrip(".")
            if len(a_stripped) > 20 and len(b_stripped) > 20:
                if a_stripped in b_stripped or b_stripped in a_stripped:
                    near_dupes += 1
    click.echo(
        f"  Possible near-dupes:   {near_dupes} "
        f"(sampled {sample_size} facts)"
    )

    # (e) Entity population rate
    with_entities = sum(
        1 for f in facts if f.get("entities") and len(f["entities"]) > 0
    )
    missing_entities = total - with_entities
    click.echo(
        f"  Missing entities:      {missing_entities} "
        f"({100 * missing_entities / total:.1f}%)"
    )

    # (f) Random samples
    n_samples = min(10, total)
    click.echo(f"\nSample facts ({n_samples} random):")
    samples = random.sample(facts, n_samples)
    for i, f in enumerate(samples, 1):
        click.echo(f'  {i:2d}. "{f["fact_text"]}"')


# ═════════════════════════════════════════════════════════════════════════════
#  TEST RUN
# ═════════════════════════════════════════════════════════════════════════════

TEST_RUN_ITEMS_PER_SOURCE = 5


def _insert_facts_tracked(facts: list[dict]) -> tuple[int, list[str]]:
    """Insert facts and return (inserted_count, list_of_inserted_fact_ids).

    Wraps the standard insertion logic while tracking which fact IDs were
    actually inserted (not skipped as duplicates).
    """
    import uuid as _uuid
    import orjson

    from src.utils.db import get_pg

    conn = get_pg()
    cur = conn.cursor()
    inserted = 0
    fact_ids: list[str] = []

    for fact in facts:
        cur.execute(
            "SELECT 1 FROM facts WHERE fact_text = %s",
            (fact["fact_text"],),
        )
        if cur.fetchone():
            continue

        fact_id = str(_uuid.uuid4())
        cur.execute(
            """
            INSERT INTO facts
                (id, fact_text, domain, subdomain, entities,
                 source_id, confidence, tags)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                fact_id,
                fact["fact_text"],
                fact["domain"],
                fact.get("subdomain"),
                orjson.dumps(fact.get("entities", [])).decode(),
                fact["source_id"],
                fact.get("confidence", 1.0),
                fact.get("tags", []),
            ),
        )
        inserted += 1
        fact_ids.append(fact_id)

    conn.commit()
    return inserted, fact_ids


def _cleanup_facts(fact_ids: list[str]) -> int:
    """Delete facts by their IDs. Returns count deleted."""
    if not fact_ids:
        return 0

    from src.utils.db import get_pg

    conn = get_pg()
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM facts WHERE id = ANY(%s::uuid[])",
        (fact_ids,),
    )
    deleted = cur.rowcount
    conn.commit()
    return deleted


def _print_test_report(
    source_stats: dict[str, dict],
    all_facts: list[dict],
) -> None:
    """Print the structured test-run report with quality checks and warnings."""
    click.echo("\n=== TEST RUN REPORT ===")
    click.echo(
        f"{'Source/Category':<20s} {'Items Processed':>16s} "
        f"{'Facts Generated':>16s} {'Facts Inserted (new)':>21s}"
    )
    click.echo("─" * 75)

    total_items = 0
    total_generated = 0
    total_inserted = 0

    for name, stats in source_stats.items():
        items = stats["items"]
        generated = stats["generated"]
        inserted = stats["inserted"]
        total_items += items
        total_generated += generated
        total_inserted += inserted
        click.echo(
            f"{name:<20s} {items:>16d} {generated:>16d} {inserted:>21d}"
        )

    click.echo("─" * 75)
    click.echo(
        f"{'TOTAL':<20s} {total_items:>16d} "
        f"{total_generated:>16d} {total_inserted:>21d}"
    )

    # Quality checks
    if not all_facts:
        click.echo("\nNo facts generated.")
        return

    total = len(all_facts)
    too_short = [f for f in all_facts if len(f["fact_text"].split()) < 5]
    too_long = [f for f in all_facts if len(f["fact_text"].split()) > 50]
    missing_ent = [
        f for f in all_facts
        if not f.get("entities") or len(f["entities"]) == 0
    ]
    word_counts = [len(f["fact_text"].split()) for f in all_facts]
    avg_words = sum(word_counts) / total

    click.echo("\nQuality Checks:")
    click.echo(
        f"  Too short (<5 words):  {len(too_short)} "
        f"({100 * len(too_short) / total:.1f}%)"
    )
    click.echo(
        f"  Too long (>50 words):  {len(too_long)} "
        f"({100 * len(too_long) / total:.1f}%)"
    )
    click.echo(
        f"  Missing entities:      {len(missing_ent)} "
        f"({100 * len(missing_ent) / total:.1f}%)"
    )
    click.echo(f"  Avg words per fact:    {avg_words:.1f}")

    # Sample facts
    n_samples = min(10, total)
    click.echo(f"\nSample Facts ({n_samples} random from this run):")
    samples = random.sample(all_facts, n_samples)
    for i, f in enumerate(samples, 1):
        click.echo(f'  {i:2d}. "{f["fact_text"]}"')

    # Warnings
    warnings: list[str] = []

    for name, stats in source_stats.items():
        if stats["inserted"] == 0 and stats["generated"] > 0:
            warnings.append(f"ERROR: No facts from {name}")
        if stats["items"] > 0:
            rate = stats["generated"] / stats["items"]
            if rate < 2:
                warnings.append(
                    f"WARNING: Low extraction rate in {name} "
                    f"({rate:.1f} facts/item)"
                )
        if stats["generated"] > 0:
            skipped = stats["generated"] - stats["inserted"]
            if skipped / stats["generated"] > 0.5:
                warnings.append(
                    f"WARNING: High duplicate rate in {name} "
                    f"({skipped}/{stats['generated']} skipped)"
                )

    if total > 0 and len(too_short) / total > 0.10:
        warnings.append("WARNING: Too many trivial facts")
    if total > 0 and len(too_long) / total > 0.10:
        warnings.append("WARNING: Facts need better splitting")

    regarding_facts = [
        f for f in all_facts
        if f["fact_text"].startswith("Regarding")
    ]
    if regarding_facts:
        warnings.append("WARNING: Verbatim text detected")

    over_40 = [f for f in all_facts if len(f["fact_text"].split()) > 40]
    if over_40:
        warnings.append(
            f"WARNING: {len(over_40)} fact(s) over 40 words — "
            f"review for splitting:"
        )
        for f in over_40:
            warnings.append(f'    "{f["fact_text"]}"')

    if warnings:
        click.echo("\nWarnings:")
        for w in warnings:
            click.echo(f"  * {w}")
    else:
        click.echo("\nNo warnings.")


def run_test(
    source_filter: Optional[str] = None,
    cleanup: bool = False,
) -> None:
    """Run a limited test: 5 items per source, insert, report, optionally clean up."""
    sources_to_run = (
        [source_filter] if source_filter else list(SOURCES_CONFIG.keys())
    )

    session = _create_session()
    source_stats: dict[str, dict] = {}
    all_facts: list[dict] = []
    all_fact_ids: list[str] = []

    for source_name in sources_to_run:
        if source_name not in SOURCES_CONFIG:
            logger.error(f"Unknown source: {source_name}")
            continue

        cfg = SOURCES_CONFIG[source_name]
        logger.info(
            f"[TEST RUN] Processing source: {source_name} "
            f"(limit {TEST_RUN_ITEMS_PER_SOURCE} items)"
        )

        source_id = ensure_source(
            name=cfg["source_name"],
            url=cfg["source_url"],
            source_type=cfg["source_type"],
            tier="tier_1_official",
        )

        # Scrape raw data and limit to 5 items
        if source_name == "ava":
            raw = _scrape_avas(session)
            raw = raw[:TEST_RUN_ITEMS_PER_SOURCE]
            facts = _build_ava_facts(raw, source_id)
        elif source_name == "varieties":
            raw = _scrape_varieties(session)
            raw = raw[:TEST_RUN_ITEMS_PER_SOURCE]
            facts = _build_variety_facts(raw, source_id)
        elif source_name == "regulations":
            # Regulations are already a flat list; take first 5
            raw_count = min(
                TEST_RUN_ITEMS_PER_SOURCE, len(_REGULATION_FACTS)
            )
            facts = _build_regulation_facts(source_id)[:raw_count]
            raw = [None] * raw_count  # placeholder for item count
        else:
            continue

        items_processed = len(raw)
        generated = len(facts)
        inserted, fact_ids = _insert_facts_tracked(facts)

        source_stats[source_name] = {
            "items": items_processed,
            "generated": generated,
            "inserted": inserted,
        }
        all_facts.extend(facts)
        all_fact_ids.extend(fact_ids)

    _print_test_report(source_stats, all_facts)

    if cleanup and all_fact_ids:
        deleted = _cleanup_facts(all_fact_ids)
        click.echo(f"\nCleaned up {deleted} test facts from database.")
    elif cleanup:
        click.echo("\nNo test facts to clean up.")


# ═════════════════════════════════════════════════════════════════════════════
#  MAIN PIPELINE
# ═════════════════════════════════════════════════════════════════════════════


def run_source(source_name: str, dry_run: bool = False) -> int:
    """Run extraction for a single source. Returns count of facts."""
    if source_name not in SOURCES_CONFIG:
        logger.error(
            f"Unknown source: {source_name}. "
            f"Available: {list(SOURCES_CONFIG.keys())}"
        )
        return 0

    cfg = SOURCES_CONFIG[source_name]
    logger.info(f"Running source: {source_name} — {cfg['description']}")

    if not dry_run:
        source_id = ensure_source(
            name=cfg["source_name"],
            url=cfg["source_url"],
            source_type=cfg["source_type"],
            tier="tier_1_official",
        )
    else:
        source_id = "dry-run"

    session = _create_session()

    if source_name == "ava":
        raw = _scrape_avas(session)
        facts = _build_ava_facts(raw, source_id)
    elif source_name == "varieties":
        raw = _scrape_varieties(session)
        facts = _build_variety_facts(raw, source_id)
    elif source_name == "regulations":
        facts = _build_regulation_facts(source_id)
    else:
        return 0

    if dry_run:
        click.echo(
            f"\n[DRY RUN] Would insert {len(facts)} facts "
            f"from {source_name}"
        )
        validate_facts(facts)
        return len(facts)

    inserted = insert_facts_batch(facts)
    logger.info(
        f"Inserted {inserted} new facts from {source_name} "
        f"(duplicates skipped)"
    )
    return inserted


def run_all(dry_run: bool = False) -> dict:
    """Run all sources. Returns summary dict."""
    summary = {}
    total = 0

    for name in SOURCES_CONFIG:
        count = run_source(name, dry_run=dry_run)
        summary[name] = count
        total += count

    logger.info(f"TTB scraping complete. Total facts: {total}")
    if not dry_run:
        logger.info(f"Total facts in database: {get_fact_count()}")
    return summary


# ═════════════════════════════════════════════════════════════════════════════
#  CLI
# ═════════════════════════════════════════════════════════════════════════════


@click.command()
@click.option(
    "--source", "-s", type=str,
    help="Run a specific source (ava/varieties/regulations)",
)
@click.option("--all", "run_all_flag", is_flag=True, help="Run all sources")
@click.option(
    "--list", "list_sources", is_flag=True, help="List available sources",
)
@click.option(
    "--dry-run", "dry_run", is_flag=True,
    help="Extract facts but do not insert into DB",
)
@click.option(
    "--validate", "validate_flag", is_flag=True,
    help="Run quality checks on all extracted facts",
)
@click.option(
    "--test-run", "test_run", is_flag=True,
    help="Process first 5 items per source, insert, and print a report",
)
@click.option(
    "--cleanup", is_flag=True,
    help="When used with --test-run, delete inserted facts after report",
)
def main(
    source: Optional[str],
    run_all_flag: bool,
    list_sources: bool,
    dry_run: bool,
    validate_flag: bool,
    test_run: bool,
    cleanup: bool,
) -> None:
    """OenoBench TTB Scraper — Extract US wine regulation data from TTB."""
    Path("data/logs").mkdir(parents=True, exist_ok=True)
    logger.add("data/logs/ttb_{time}.log", rotation="10 MB")

    if list_sources:
        click.echo("\nAvailable sources:")
        for name, cfg in SOURCES_CONFIG.items():
            click.echo(f"  {name:20s} — {cfg['description']}")
        return

    if test_run:
        run_test(source_filter=source, cleanup=cleanup)
        return

    if cleanup:
        click.echo("--cleanup can only be used with --test-run.")
        return

    if validate_flag:
        click.echo("Running validation on all sources...")
        session = _create_session()
        all_facts: list[dict] = []

        # AVA
        raw_avas = _scrape_avas(session)
        all_facts.extend(_build_ava_facts(raw_avas, "validate"))

        # Varieties
        raw_vars = _scrape_varieties(session)
        all_facts.extend(_build_variety_facts(raw_vars, "validate"))

        # Regulations
        all_facts.extend(_build_regulation_facts("validate"))

        validate_facts(all_facts)
        _cross_reference_ava_count()
        return

    if run_all_flag:
        summary = run_all(dry_run=dry_run)
        click.echo("\nSummary:")
        for name, count in summary.items():
            label = f"{name} (dry-run)" if dry_run else name
            click.echo(f"  {label:30s}: {count} facts")
        click.echo(f"  {'TOTAL':30s}: {sum(summary.values())} facts")
        return

    if source:
        count = run_source(source, dry_run=dry_run)
        if dry_run:
            click.echo(
                f"\n[DRY RUN] {count} facts extracted from '{source}'."
            )
        else:
            click.echo(f"\nInserted {count} new facts from '{source}'.")
        return

    click.echo(
        "Use --all to run all sources, or --source <name> for a specific one."
    )
    click.echo("Use --list to see available sources.")
    click.echo("Use --dry-run to preview without inserting.")
    click.echo("Use --validate to run quality checks.")


if __name__ == "__main__":
    main()
