"""
OenoBench — Italian Wine Central Scraper (genuine external data only)

Extracts Italian wine knowledge from:
  1. italianwinecentral.com — HTML tables of DOCG/DOC appellations with grapes, regions, types
  2. Wikipedia — Italian wine category articles, infoboxes
  3. Wikidata SPARQL — Italian wine appellations and grape varieties (country-scoped)

Every fact traces to a URL that was actually fetched and parsed.
No hardcoded wine knowledge.

Usage:
    python -m src.scrapers.italian_wine_central --all
    python -m src.scrapers.italian_wine_central --dry-run
    python -m src.scrapers.italian_wine_central --validate
    python -m src.scrapers.italian_wine_central --list
    python -m src.scrapers.italian_wine_central --test-run
    python -m src.scrapers.italian_wine_central --test-run --cleanup
"""

import random
import re
import time
from collections import Counter
from typing import Optional

import click
import requests
from bs4 import BeautifulSoup
from loguru import logger

from src.utils.facts import ensure_source, insert_facts_batch, get_fact_count
from src.scrapers._wiki_helpers import (
    wiki_session,
    fetch_article,
    fetch_full_extract,
    crawl_category,
    parse_infobox,
    parse_wikitext_tables,
    extract_lead_sentences,
    extract_atomic_facts,
    run_sparql,
    run_sparql_filtered,
    ensure_wiki_source,
    ensure_wikidata_source,
    clean_wiki_value,
    is_wine_relevant,
    SPARQL_WINE_REGIONS_BY_COUNTRY,
    SPARQL_GRAPE_VARIETIES_BY_COUNTRY,
    SPARQL_APPELLATIONS_BY_COUNTRY,
)
from src.scrapers._fact_processing import (
    process_facts,
    classify_domain,
    validate_fact,
    is_on_topic,
)
from src.scrapers._web_helpers import (
    create_session,
    fetch_page,
    discover_pages,
    extract_text_blocks,
    scrape_site_texts,
)

# ─── Configuration ────────────────────────────────────────────────────────────

TEST_RUN_LIMIT = 5
IWC_BASE_URL = "https://italianwinecentral.com"
IWC_REQUEST_DELAY = 5
REQUEST_TIMEOUT = 30
IWC_HEADERS = {
    "User-Agent": "OenoBench-Research/1.0 (academic wine benchmark)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,it;q=0.8",
}

# Region keywords for on-topic filtering (broad — Italy has many regions)
ITALY_KEYWORDS = {
    "italy", "italian", "italia",
    "piedmont", "piemonte", "tuscany", "toscana", "veneto",
    "lombardy", "lombardia", "friuli", "trentino", "alto adige",
    "emilia", "romagna", "campania", "sicily", "sicilia",
    "sardinia", "sardegna", "puglia", "apulia", "calabria",
    "liguria", "marche", "umbria", "abruzzo", "molise",
    "basilicata", "lazio", "valle d'aosta",
    "docg", "doc", "igt", "denominazione",
    "barolo", "chianti", "brunello", "amarone", "prosecco",
    "franciacorta", "soave", "valpolicella", "barbera",
    "sangiovese", "nebbiolo", "primitivo", "nero d'avola",
    "montepulciano", "trebbiano", "verdicchio", "vermentino",
    "corvina", "garganega", "glera", "aglianico",
}

# Key Wikipedia articles to scrape
KEY_ARTICLES = [
    "Italian wine",
    "Italian wine classification",
    "Barolo",
    "Chianti",
    "Brunello di Montalcino",
    "Amarone",
    "Prosecco",
    "Franciacorta DOCG",
    "Soave (wine)",
    "Valpolicella",
    "Barbera",
    "Sangiovese",
    "Nebbiolo",
    "Italian grape varieties",
]


# ─── Italian Wine Central Scraping ──────────────────────────────────────────


def _fetch_iwc_page(url: str) -> Optional[str]:
    """Fetch a page from italianwinecentral.com with rate limiting."""
    time.sleep(IWC_REQUEST_DELAY)
    try:
        resp = requests.get(url, headers=IWC_HEADERS, timeout=REQUEST_TIMEOUT)
        if resp.status_code != 200:
            logger.warning(f"HTTP {resp.status_code} for {url}")
            return None
        return resp.text
    except requests.RequestException as e:
        logger.warning(f"Failed to fetch {url}: {e}")
        return None


def _parse_appellation_table(html: str, appellation_type: str) -> list[dict]:
    """Parse an IWC appellation table page into structured entries."""
    soup = BeautifulSoup(html, "html.parser")
    results = []

    tables = soup.find_all("table")
    for table in tables:
        header_row = table.find("tr")
        if not header_row:
            continue
        headers = [th.get_text(strip=True).lower() for th in header_row.find_all(["th", "td"])]

        rows = table.find_all("tr")
        for row in rows[1:]:
            cells = row.find_all(["td", "th"])
            if not cells:
                continue

            name = cells[0].get_text(strip=True)
            if not name or len(name) < 2:
                continue

            entry = {
                "name": name,
                "appellation_type": appellation_type.upper(),
            }

            link = cells[0].find("a")
            if link and link.get("href"):
                href = link["href"]
                if not href.startswith("http"):
                    href = IWC_BASE_URL + href
                entry["detail_url"] = href

            for i, cell in enumerate(cells[1:], 1):
                text = cell.get_text(strip=True)
                if not text:
                    continue
                if i < len(headers):
                    col = headers[i]
                    if "region" in col:
                        entry["region"] = text
                    elif "grape" in col or "variet" in col:
                        entry["grapes"] = text
                    elif "type" in col or "colour" in col or "color" in col:
                        entry["wine_type"] = text
                    elif "province" in col:
                        entry["province"] = text
                else:
                    if i == 1 and "region" not in entry:
                        entry["region"] = text
                    elif i == 2 and "grapes" not in entry:
                        entry["grapes"] = text
                    elif i == 3 and "wine_type" not in entry:
                        entry["wine_type"] = text

            results.append(entry)

    return results


def _build_iwc_facts(entries: list[dict], source_id: str) -> list[dict]:
    """Convert parsed IWC table entries into atomic facts with classify_domain."""
    facts = []
    seen = set()

    def _add(text, domain=None, entities=None, tags=None, confidence=0.95):
        key = text.lower()
        if key in seen:
            return
        seen.add(key)
        facts.append({
            "fact_text": text,
            "domain": domain or classify_domain(text),
            "subdomain": "italy",
            "source_id": source_id,
            "entities": entities or [],
            "confidence": confidence,
            "tags": tags or ["italy", "italian_wine_central"],
        })

    for entry in entries:
        name = entry["name"]
        app_type = entry.get("appellation_type", "")
        region = entry.get("region", "")
        grapes = entry.get("grapes", "")
        wine_type = entry.get("wine_type", "")

        # Fact: appellation classification
        if region:
            _add(
                f"{name} is a {app_type} appellation in {region}, Italy.",
                entities=[
                    {"type": "region", "name": name},
                    {"type": "region", "name": region},
                ],
                tags=["italy", "italian_wine_central", app_type.lower()],
            )
        else:
            _add(
                f"{name} is a {app_type} appellation in Italy.",
                entities=[{"type": "region", "name": name}],
                tags=["italy", "italian_wine_central", app_type.lower()],
            )

        # Fact: permitted grape varieties (individual atomic facts)
        if grapes:
            grape_list = re.split(r"[,;/]\s*|\s+and\s+", grapes)
            grape_list = [g.strip() for g in grape_list if g.strip() and len(g.strip()) > 1]

            for g in grape_list[:6]:
                if 2 < len(g) < 40:
                    _add(
                        f"{g} is a permitted grape variety in {name} {app_type}.",
                        domain="grape_varieties",
                        entities=[
                            {"type": "grape", "name": g},
                            {"type": "region", "name": name},
                        ],
                        tags=["italy", "italian_wine_central", "grape"],
                    )

        # Fact: wine type
        if wine_type:
            _add(
                f"{name} {app_type} produces {wine_type} wine.",
                entities=[{"type": "region", "name": name}],
                tags=["italy", "italian_wine_central", "wine_type"],
            )

    return facts


def _scrape_iwc_detail_page(url: str, name: str, app_type: str, source_id: str) -> list[dict]:
    """Scrape an individual DOCG/DOC detail page for additional facts."""
    facts = []
    seen = set()

    def _add(text, domain=None, entities=None, tags=None, confidence=0.95):
        key = text.lower()
        if key in seen:
            return
        seen.add(key)
        facts.append({
            "fact_text": text,
            "domain": domain or classify_domain(text),
            "subdomain": "italy",
            "source_id": source_id,
            "entities": entities or [],
            "confidence": confidence,
            "tags": tags or ["italy", "italian_wine_central", "detail"],
        })

    html = _fetch_iwc_page(url)
    if not html:
        return facts

    soup = BeautifulSoup(html, "html.parser")

    # Extract text blocks and process through pipeline
    blocks = extract_text_blocks(soup, min_words=8, max_words=50)
    if blocks:
        processed = process_facts(
            raw_texts=blocks,
            subject=name,
            region_keywords=ITALY_KEYWORDS,
        )
        for item in processed:
            _add(
                item["fact_text"],
                domain=item["domain"],
                entities=[{"type": "region", "name": name}],
                tags=["italy", "italian_wine_central", "detail", app_type.lower()],
            )

    # Also look for structured tables with aging/production data
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        for row in rows:
            cells = row.find_all(["td", "th"])
            if len(cells) >= 2:
                label = cells[0].get_text(strip=True).lower()
                value = cells[1].get_text(strip=True)
                if not value or len(value) < 2:
                    continue

                if "aging" in label or "ageing" in label:
                    _add(
                        f"{name} {app_type} requires a minimum aging period of {value}.",
                        entities=[{"type": "region", "name": name}],
                        tags=["italy", "italian_wine_central", "detail", "aging"],
                    )
                elif "yield" in label:
                    _add(
                        f"{name} {app_type} has a maximum yield of {value}.",
                        entities=[{"type": "region", "name": name}],
                        tags=["italy", "italian_wine_central", "detail", "yield"],
                    )
                elif "alcohol" in label:
                    _add(
                        f"{name} {app_type} requires a minimum alcohol level of {value}.",
                        entities=[{"type": "region", "name": name}],
                        tags=["italy", "italian_wine_central", "detail", "alcohol"],
                    )
                elif "production" in label and "zone" in label:
                    _add(
                        f"The production zone for {name} {app_type} is {value}.",
                        entities=[{"type": "region", "name": name}],
                        tags=["italy", "italian_wine_central", "detail", "zone"],
                    )

    return facts


def _scrape_iwc_website(source_id: str) -> list[dict]:
    """Scrape additional pages from italianwinecentral.com using web helpers."""
    facts = []

    logger.info("Attempting IWC website discovery via web helpers...")
    try:
        page_texts = scrape_site_texts(
            base_url=IWC_BASE_URL,
            seed_paths=[
                "/wine-appellations/docg/",
                "/wine-appellations/doc/",
                "/italian-wine-regions/",
                "/native-grapes/",
            ],
            max_pages=30,
            delay=5.0,
            min_words=8,
            max_words=50,
            url_filter=re.compile(r"italianwinecentral\.com"),
        )

        if not page_texts:
            logger.warning("IWC website: no pages accessible via web helpers")
            return facts

        for url, blocks in page_texts:
            logger.info(f"IWC: processing {len(blocks)} blocks from {url}")
            processed = process_facts(
                raw_texts=blocks,
                subject="Italian wine",
                region_keywords=ITALY_KEYWORDS,
            )
            for item in processed:
                facts.append({
                    "fact_text": item["fact_text"],
                    "domain": item["domain"],
                    "subdomain": "italy",
                    "source_id": source_id,
                    "entities": [],
                    "confidence": 0.9,
                    "tags": ["italy", "italian_wine_central", "website"],
                })

    except Exception as e:
        logger.warning(f"IWC website discovery failed: {e}")

    logger.info(f"IWC website discovery yielded {len(facts)} additional facts")
    return facts


def _scrape_italian_wine_central(source_id: str, scrape_details: bool = True) -> list[dict]:
    """Scrape DOCG and DOC tables from italianwinecentral.com."""
    all_facts = []

    for app_type in ["docg", "doc"]:
        url = f"{IWC_BASE_URL}/wine-appellations/{app_type}/"
        logger.info(f"Fetching IWC {app_type.upper()} table: {url}")

        html = _fetch_iwc_page(url)
        if not html:
            logger.warning(f"Could not fetch IWC {app_type.upper()} page")
            continue

        entries = _parse_appellation_table(html, app_type)
        logger.info(f"IWC {app_type.upper()} table: {len(entries)} entries")

        facts = _build_iwc_facts(entries, source_id)
        logger.info(f"IWC {app_type.upper()} facts from table: {len(facts)}")
        all_facts.extend(facts)

        # Scrape individual detail pages (DOCG only to limit requests)
        if scrape_details and app_type == "docg":
            detail_entries = [e for e in entries if e.get("detail_url")]
            logger.info(f"Scraping {len(detail_entries)} DOCG detail pages...")
            for entry in detail_entries:
                detail_facts = _scrape_iwc_detail_page(
                    entry["detail_url"],
                    entry["name"],
                    app_type.upper(),
                    source_id,
                )
                if detail_facts:
                    logger.info(f"  {entry['name']}: {len(detail_facts)} detail facts")
                    all_facts.extend(detail_facts)

    # Also scrape additional pages via web discovery
    web_facts = _scrape_iwc_website(source_id)
    all_facts.extend(web_facts)

    return all_facts


# ─── Wikipedia Scraping ──────────────────────────────────────────────────────


def _scrape_wikipedia_key_articles(session: requests.Session, source_id: str) -> list[dict]:
    """Scrape key Italian wine articles from Wikipedia using atomic fact extraction."""
    facts = []
    seen = set()

    for title in KEY_ARTICLES:
        logger.info(f"Fetching Wikipedia article: {title}")
        extract, wikitext = fetch_article(session, title)

        if extract:
            atomic = extract_atomic_facts(
                extract,
                article_title=title,
                region_keywords=ITALY_KEYWORDS,
            )
            for item in atomic:
                key = item["fact_text"].lower()
                if key not in seen:
                    seen.add(key)
                    facts.append({
                        "fact_text": item["fact_text"],
                        "domain": item["domain"],
                        "subdomain": "italy",
                        "source_id": source_id,
                        "entities": [{"type": "region", "name": title}],
                        "confidence": 0.9,
                        "tags": ["italy", "wikipedia", "key_article"],
                    })

        if wikitext:
            infobox = parse_infobox(wikitext)
            if infobox:
                region = infobox.get("region", "")
                grape = infobox.get("grapes", "") or infobox.get("grape", "")
                area = infobox.get("area", "") or infobox.get("size", "") or infobox.get("hectares", "")
                designation = infobox.get("appellation", "") or infobox.get("designation", "")
                year = infobox.get("year established", "") or infobox.get("established", "")

                if region and not region.startswith("Q"):
                    fact_text = f"{title} is a wine appellation in {region}, Italy."
                    key = fact_text.lower()
                    if key not in seen:
                        seen.add(key)
                        facts.append({
                            "fact_text": fact_text,
                            "domain": classify_domain(fact_text),
                            "subdomain": "italy",
                            "source_id": source_id,
                            "entities": [{"type": "region", "name": title}],
                            "confidence": 0.9,
                            "tags": ["italy", "wikipedia", "appellation"],
                        })

                if grape:
                    grapes = [g.strip() for g in re.split(r"[,;]", grape) if g.strip()]
                    for g in grapes[:5]:
                        if 2 < len(g) < 50:
                            fact_text = f"{title} permits the {g} grape variety."
                            key = fact_text.lower()
                            if key not in seen:
                                seen.add(key)
                                facts.append({
                                    "fact_text": fact_text,
                                    "domain": "grape_varieties",
                                    "subdomain": "italy",
                                    "source_id": source_id,
                                    "entities": [
                                        {"type": "region", "name": title},
                                        {"type": "grape", "name": g},
                                    ],
                                    "confidence": 0.9,
                                    "tags": ["italy", "wikipedia", "grape"],
                                })

                if area and re.search(r"\d", area):
                    area_clean = re.sub(r"[^\d.,]", " ", area).strip()
                    if area_clean:
                        fact_text = f"{title} covers approximately {area_clean} hectares."
                        key = fact_text.lower()
                        if key not in seen:
                            seen.add(key)
                            facts.append({
                                "fact_text": fact_text,
                                "domain": classify_domain(fact_text),
                                "subdomain": "italy",
                                "source_id": source_id,
                                "entities": [{"type": "region", "name": title}],
                                "confidence": 0.9,
                                "tags": ["italy", "wikipedia", "area"],
                            })

                if designation:
                    fact_text = f"{title} holds {designation} designation."
                    key = fact_text.lower()
                    if key not in seen:
                        seen.add(key)
                        facts.append({
                            "fact_text": fact_text,
                            "domain": classify_domain(fact_text),
                            "subdomain": "italy",
                            "source_id": source_id,
                            "entities": [{"type": "region", "name": title}],
                            "confidence": 0.9,
                            "tags": ["italy", "wikipedia", "designation"],
                        })

                if year and re.search(r"\d{4}", year):
                    year_match = re.search(r"\d{4}", year)
                    if year_match:
                        fact_text = f"{title} was established in {year_match.group()}."
                        key = fact_text.lower()
                        if key not in seen:
                            seen.add(key)
                            facts.append({
                                "fact_text": fact_text,
                                "domain": classify_domain(fact_text),
                                "subdomain": "italy",
                                "source_id": source_id,
                                "entities": [{"type": "region", "name": title}],
                                "confidence": 0.9,
                                "tags": ["italy", "wikipedia", "history"],
                            })

    return facts


def _scrape_wikipedia_categories(session: requests.Session, source_id: str) -> list[dict]:
    """Scrape Italian wine articles from Wikipedia categories using atomic fact extraction."""
    facts = []
    seen = set()

    categories = [
        "Category:DOCG wine",
        "Category:DOC wine",
        "Category:Wine regions of Italy",
        "Category:Italian wine",
    ]

    all_titles = set()
    for cat in categories:
        logger.info(f"Crawling category: {cat}")
        titles = crawl_category(session, cat, max_depth=2, max_articles=150)
        all_titles.update(titles)

    # Remove articles already fetched as key articles
    all_titles -= set(KEY_ARTICLES)
    logger.info(f"Found {len(all_titles)} Italian wine articles from categories")

    for title in sorted(all_titles):
        logger.info(f"Fetching: {title}")
        extract, wikitext = fetch_article(session, title)

        if extract:
            atomic = extract_atomic_facts(
                extract,
                article_title=title,
                region_keywords=ITALY_KEYWORDS,
            )
            for item in atomic:
                key = item["fact_text"].lower()
                if key not in seen:
                    seen.add(key)
                    facts.append({
                        "fact_text": item["fact_text"],
                        "domain": item["domain"],
                        "subdomain": "italy",
                        "source_id": source_id,
                        "entities": [{"type": "region", "name": title}],
                        "confidence": 0.9,
                        "tags": ["italy", "wikipedia", "category"],
                    })

        if wikitext:
            infobox = parse_infobox(wikitext)
            if infobox:
                region = infobox.get("region", "")
                grape = infobox.get("grapes", "") or infobox.get("grape", "")
                area = infobox.get("area", "") or infobox.get("size", "") or infobox.get("hectares", "")
                designation = infobox.get("appellation", "") or infobox.get("designation", "")
                year = infobox.get("year established", "") or infobox.get("established", "")

                if region and not region.startswith("Q"):
                    fact_text = f"{title} is a wine appellation in {region}, Italy."
                    key = fact_text.lower()
                    if key not in seen:
                        seen.add(key)
                        facts.append({
                            "fact_text": fact_text,
                            "domain": classify_domain(fact_text),
                            "subdomain": "italy",
                            "source_id": source_id,
                            "entities": [{"type": "region", "name": title}],
                            "confidence": 0.9,
                            "tags": ["italy", "wikipedia", "appellation"],
                        })

                if grape:
                    grapes = [g.strip() for g in re.split(r"[,;]", grape) if g.strip()]
                    for g in grapes[:5]:
                        if 2 < len(g) < 50:
                            fact_text = f"{title} permits the {g} grape variety."
                            key = fact_text.lower()
                            if key not in seen:
                                seen.add(key)
                                facts.append({
                                    "fact_text": fact_text,
                                    "domain": "grape_varieties",
                                    "subdomain": "italy",
                                    "source_id": source_id,
                                    "entities": [
                                        {"type": "region", "name": title},
                                        {"type": "grape", "name": g},
                                    ],
                                    "confidence": 0.9,
                                    "tags": ["italy", "wikipedia", "grape"],
                                })

                if area and re.search(r"\d", area):
                    area_clean = re.sub(r"[^\d.,]", " ", area).strip()
                    if area_clean:
                        fact_text = f"{title} covers approximately {area_clean} hectares."
                        key = fact_text.lower()
                        if key not in seen:
                            seen.add(key)
                            facts.append({
                                "fact_text": fact_text,
                                "domain": classify_domain(fact_text),
                                "subdomain": "italy",
                                "source_id": source_id,
                                "entities": [{"type": "region", "name": title}],
                                "confidence": 0.9,
                                "tags": ["italy", "wikipedia", "area"],
                            })

                if year and re.search(r"\d{4}", year):
                    year_match = re.search(r"\d{4}", year)
                    if year_match:
                        fact_text = f"{title} was established in {year_match.group()}."
                        key = fact_text.lower()
                        if key not in seen:
                            seen.add(key)
                            facts.append({
                                "fact_text": fact_text,
                                "domain": classify_domain(fact_text),
                                "subdomain": "italy",
                                "source_id": source_id,
                                "entities": [{"type": "region", "name": title}],
                                "confidence": 0.9,
                                "tags": ["italy", "wikipedia", "history"],
                            })

    return facts


# ─── Wikidata SPARQL ─────────────────────────────────────────────────────────


def _scrape_wikidata(source_id: str) -> list[dict]:
    """Query Wikidata for Italian wine data using country-scoped queries."""
    facts = []
    seen = set()

    def _add(text, domain=None, entities=None, tags=None, confidence=0.85):
        key = text.lower()
        if key in seen:
            return
        seen.add(key)
        facts.append({
            "fact_text": text,
            "domain": domain or classify_domain(text),
            "subdomain": "italy",
            "source_id": source_id,
            "entities": entities or [],
            "confidence": confidence,
            "tags": tags or ["italy", "wikidata"],
        })

    # Query 1: Wine regions in Italy
    logger.info("SPARQL: Wine regions in Italy")
    try:
        query = SPARQL_WINE_REGIONS_BY_COUNTRY.format(country_qid="Q38")
        rows = run_sparql_filtered(query, expected_country="Italy")
        logger.info(f"Wikidata: {len(rows)} Italian wine region results")
        for row in rows:
            name = row.get("itemLabel", "")
            region = row.get("regionLabel", "")
            grape = row.get("grapeLabel", "")
            area = row.get("areaHa", "")
            if not name or name.startswith("Q"):
                continue

            if region and not region.startswith("Q"):
                _add(
                    f"{name} is a wine-producing region in {region}, Italy.",
                    entities=[
                        {"type": "region", "name": name},
                        {"type": "region", "name": region},
                    ],
                    tags=["italy", "wikidata", "region"],
                )
            else:
                _add(
                    f"{name} is a wine-producing region in Italy.",
                    entities=[{"type": "region", "name": name}],
                    tags=["italy", "wikidata", "region"],
                )

            if grape and not grape.startswith("Q"):
                _add(
                    f"{name} is associated with the {grape} grape variety.",
                    domain="grape_varieties",
                    entities=[
                        {"type": "region", "name": name},
                        {"type": "grape", "name": grape},
                    ],
                    tags=["italy", "wikidata", "grape"],
                )

            if area and re.search(r"\d", str(area)):
                _add(
                    f"{name} covers approximately {area} hectares.",
                    entities=[{"type": "region", "name": name}],
                    tags=["italy", "wikidata", "area"],
                )
    except Exception as e:
        logger.warning(f"Wikidata wine regions query failed: {e}")

    # Query 2: Italian grape varieties
    logger.info("SPARQL: Grape varieties from Italy")
    try:
        query = SPARQL_GRAPE_VARIETIES_BY_COUNTRY.format(country_qid="Q38")
        rows = run_sparql_filtered(query, expected_country="Italy")
        logger.info(f"Wikidata: {len(rows)} Italian grape variety results")
        for row in rows:
            name = row.get("itemLabel", "")
            color = row.get("colorLabel", "")
            if not name or name.startswith("Q"):
                continue

            _add(
                f"{name} is a grape variety originating from Italy.",
                domain="grape_varieties",
                entities=[{"type": "grape", "name": name}],
                tags=["italy", "wikidata", "grape"],
            )

            if color and not color.startswith("Q"):
                _add(
                    f"{name} is a {color} grape variety.",
                    domain="grape_varieties",
                    entities=[{"type": "grape", "name": name}],
                    tags=["italy", "wikidata", "grape", "color"],
                )
    except Exception as e:
        logger.warning(f"Wikidata grape varieties query failed: {e}")

    # Query 3: Italian appellations
    logger.info("SPARQL: Appellations in Italy")
    try:
        query = SPARQL_APPELLATIONS_BY_COUNTRY.format(country_qid="Q38")
        rows = run_sparql_filtered(query, expected_country="Italy")
        logger.info(f"Wikidata: {len(rows)} Italian appellation results")
        for row in rows:
            name = row.get("itemLabel", "")
            region = row.get("regionLabel", "")
            if not name or name.startswith("Q"):
                continue

            if region and not region.startswith("Q"):
                _add(
                    f"{name} is an Italian wine appellation in {region}.",
                    entities=[
                        {"type": "region", "name": name},
                        {"type": "region", "name": region},
                    ],
                    tags=["italy", "wikidata", "appellation"],
                )
            else:
                _add(
                    f"{name} is an Italian wine appellation.",
                    entities=[{"type": "region", "name": name}],
                    tags=["italy", "wikidata", "appellation"],
                )
    except Exception as e:
        logger.warning(f"Wikidata appellations query failed: {e}")

    return facts


# ─── Validation ───────────────────────────────────────────────────────────────


def validate_facts(facts: list[dict]) -> None:
    """Run quality checks on extracted facts."""
    logger.info(f"\n{'='*60}")
    logger.info(f"VALIDATION REPORT — Italian Wine Central Scraper")
    logger.info(f"{'='*60}")
    logger.info(f"Total facts: {len(facts)}")

    # Domain breakdown
    domains = Counter(f["domain"] for f in facts)
    logger.info(f"\nDomain breakdown:")
    for domain, count in domains.most_common():
        logger.info(f"  {domain}: {count}")

    # Confidence breakdown
    confs = Counter(f.get("confidence", 1.0) for f in facts)
    logger.info(f"\nConfidence breakdown:")
    for conf, count in sorted(confs.items(), reverse=True):
        logger.info(f"  {conf}: {count}")

    # Source tag breakdown
    tag_counter = Counter()
    for f in facts:
        for t in f.get("tags", []):
            tag_counter[t] += 1
    logger.info(f"\nSource tags:")
    for tag, count in tag_counter.most_common(15):
        logger.info(f"  {tag}: {count}")

    # Length checks
    short = [f for f in facts if len(f["fact_text"].split()) < 5]
    long = [f for f in facts if len(f["fact_text"].split()) > 50]
    logger.info(f"\nShort facts (<5 words): {len(short)}")
    logger.info(f"Long facts (>50 words): {len(long)}")
    for f in short[:5]:
        logger.info(f"  SHORT: {f['fact_text']}")
    for f in long[:5]:
        logger.info(f"  LONG: {f['fact_text']}")

    # Entity coverage
    with_entities = sum(1 for f in facts if f.get("entities"))
    logger.info(f"\nFacts with entities: {with_entities}/{len(facts)} ({100*with_entities//max(len(facts),1)}%)")

    # Near-duplicate check (sample-based for performance)
    sample_size = min(200, len(facts))
    sample = random.sample(facts, sample_size) if len(facts) > sample_size else facts
    texts = [f["fact_text"].lower() for f in sample]
    dupes = 0
    for i, t1 in enumerate(texts):
        for t2 in texts[i + 1:]:
            if t1 in t2 or t2 in t1:
                dupes += 1
    logger.info(f"\nNear-duplicate pairs (substring, sample of {sample_size}): {dupes}")

    # Sample facts
    logger.info(f"\n10 random sample facts:")
    for f in random.sample(facts, min(10, len(facts))):
        logger.info(f"  [{f['domain']}] (conf={f.get('confidence', 1.0)}) {f['fact_text']}")


# ─── Main Collection ──────────────────────────────────────────────────────────


def collect_all_facts(
    iwc_source_id: str,
    wiki_source_id: str,
    wikidata_source_id: str,
    scrape_details: bool = True,
) -> list[dict]:
    """Collect all facts from all sources."""
    session = wiki_session()
    all_facts = []

    # Italian Wine Central (primary source)
    logger.info("--- Italian Wine Central: DOCG/DOC tables ---")
    iwc_facts = _scrape_italian_wine_central(iwc_source_id, scrape_details=scrape_details)
    logger.info(f"IWC facts: {len(iwc_facts)}")
    all_facts.extend(iwc_facts)

    # Wikipedia key articles
    logger.info("--- Wikipedia: Key Italian wine articles ---")
    key_facts = _scrape_wikipedia_key_articles(session, wiki_source_id)
    logger.info(f"Wikipedia key article facts: {len(key_facts)}")
    all_facts.extend(key_facts)

    # Wikipedia categories
    logger.info("--- Wikipedia: Italian wine categories ---")
    wiki_facts = _scrape_wikipedia_categories(session, wiki_source_id)
    logger.info(f"Wikipedia category facts: {len(wiki_facts)}")
    all_facts.extend(wiki_facts)

    # Wikidata
    logger.info("--- Wikidata SPARQL ---")
    wikidata_facts = _scrape_wikidata(wikidata_source_id)
    logger.info(f"Wikidata facts: {len(wikidata_facts)}")
    all_facts.extend(wikidata_facts)

    # Deduplicate across sources
    deduped = []
    seen_texts = set()
    for f in all_facts:
        key = f["fact_text"].lower().strip()
        if key not in seen_texts:
            seen_texts.add(key)
            deduped.append(f)

    logger.info(f"Total after dedup: {len(deduped)} (from {len(all_facts)} raw)")
    return deduped


# ─── Test Run ────────────────────────────────────────────────────────────────


def run_test(cleanup: bool = False) -> None:
    """Run a small test: fetch IWC DOCG table + a few Wikipedia articles."""
    from src.utils.db import get_pg

    logger.info("=== TEST RUN: Italian Wine Central Scraper ===")
    iwc_sid = ensure_source(
        name="Italian Wine Central",
        url="https://italianwinecentral.com",
        source_type="reference",
        tier="tier_2_authoritative",
        language="en",
    )
    wiki_sid = ensure_wiki_source("Italian wine")
    wikidata_sid = ensure_wikidata_source("Italian wine")

    facts = []

    # Test IWC: just fetch the DOCG table
    logger.info("Test: fetching IWC DOCG table...")
    url = f"{IWC_BASE_URL}/wine-appellations/docg/"
    html = _fetch_iwc_page(url)
    if html:
        entries = _parse_appellation_table(html, "docg")
        logger.info(f"Parsed {len(entries)} DOCG entries")
        iwc_facts = _build_iwc_facts(entries[:TEST_RUN_LIMIT], iwc_sid)
        facts.extend(iwc_facts)
    else:
        logger.warning("Could not reach IWC - testing Wikipedia only")

    # Test Wikipedia: a few specific articles
    session = wiki_session()
    test_articles = ["Barolo", "Brunello di Montalcino", "Chianti Classico"]
    seen = set()
    for title in test_articles[:TEST_RUN_LIMIT]:
        extract, _ = fetch_article(session, title)
        if extract:
            atomic = extract_atomic_facts(extract, title, region_keywords=ITALY_KEYWORDS)
            for item in atomic:
                key = item["fact_text"].lower()
                if key not in seen:
                    seen.add(key)
                    facts.append({
                        "fact_text": item["fact_text"],
                        "domain": item["domain"],
                        "subdomain": "italy",
                        "source_id": wiki_sid,
                        "entities": [{"type": "region", "name": title}],
                        "confidence": 0.9,
                        "tags": ["italy", "wikipedia", "test"],
                    })

    logger.info(f"Test run generated {len(facts)} facts")
    if facts:
        inserted = insert_facts_batch(facts)
        logger.info(f"Inserted: {inserted}")

    for f in facts[:10]:
        logger.info(f"  [{f['domain']}] {f['fact_text']}")

    if cleanup and facts:
        conn = get_pg()
        cur = conn.cursor()
        for f in facts:
            cur.execute("DELETE FROM facts WHERE fact_text = %s", (f["fact_text"],))
        conn.commit()
        logger.info(f"Cleaned up {len(facts)} test facts")


# ─── CLI ──────────────────────────────────────────────────────────────────────


@click.command()
@click.option("--all", "run_all", is_flag=True, help="Run full extraction and insert into database")
@click.option("--list", "list_sections", is_flag=True, help="List available data sources")
@click.option("--dry-run", "dry_run", is_flag=True, help="Collect facts but don't insert into database")
@click.option("--validate", "validate", is_flag=True, help="Run quality checks on generated facts")
@click.option("--test-run", is_flag=True, help="Process a small sample, insert, and report")
@click.option("--cleanup", is_flag=True, help="With --test-run, delete inserted facts after reporting")
def main(run_all, list_sections, dry_run, validate, test_run, cleanup):
    """Italian Wine Central scraper — genuine external data only."""

    if list_sections:
        click.echo("Italian Wine Central Scraper — Data Sources:")
        click.echo("  1. italianwinecentral.com: DOCG/DOC appellation tables + detail pages")
        click.echo("  2. Wikipedia: Italian wine key articles & category articles")
        click.echo("  3. Wikidata: Italian wine regions, appellations & grape varieties (SPARQL)")
        return

    if test_run:
        run_test(cleanup=cleanup)
        return

    if not run_all and not dry_run and not validate:
        click.echo("Use --all, --dry-run, --validate, --test-run, or --list")
        return

    # Register sources
    iwc_sid = ensure_source(
        name="Italian Wine Central",
        url="https://italianwinecentral.com",
        source_type="reference",
        tier="tier_2_authoritative",
        language="en",
    )
    wiki_sid = ensure_wiki_source("Italian wine")
    wikidata_sid = ensure_wikidata_source("Italian wine")

    # Collect facts
    facts = collect_all_facts(iwc_sid, wiki_sid, wikidata_sid)

    if validate or dry_run:
        validate_facts(facts)

    if dry_run:
        logger.info(f"\nDRY RUN — {len(facts)} facts generated, not inserted")
        return

    if run_all:
        before = get_fact_count()
        inserted = insert_facts_batch(facts)
        after = get_fact_count()
        logger.info(f"Inserted {inserted} new facts (DB: {before} -> {after})")


if __name__ == "__main__":
    main()
