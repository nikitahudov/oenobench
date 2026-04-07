"""
OenoBench — Champagne Wine Scraper (genuine external data only)

Extracts Champagne wine knowledge from:
  1. Wikipedia — Champagne articles, Echelle des Crus, methode champenoise, dosage
  2. Wikidata SPARQL — Grand Cru villages, grape varieties, producers
  3. champagne.fr — supplementary scraping when accessible

Every fact traces to a URL that was actually fetched and parsed.
No hardcoded wine knowledge.

Usage:
    python -m src.scrapers.champagne --all
    python -m src.scrapers.champagne --dry-run
    python -m src.scrapers.champagne --validate
    python -m src.scrapers.champagne --list
    python -m src.scrapers.champagne --test-run
    python -m src.scrapers.champagne --test-run --cleanup
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
    run_sparql,
    ensure_wiki_source,
    ensure_wikidata_source,
    clean_wiki_value,
    is_wine_relevant,
)

# ─── Configuration ────────────────────────────────────────────────────────────

TEST_RUN_LIMIT = 5
CHAMPAGNE_FR_BASE_URL = "https://www.champagne.fr"
CHAMPAGNE_FR_REQUEST_DELAY = 5
REQUEST_TIMEOUT = 30
CHAMPAGNE_FR_HEADERS = {
    "User-Agent": "OenoBench-Research/1.0 (academic wine benchmark)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


# ─── Wikipedia Scraping ──────────────────────────────────────────────────────


def _scrape_wikipedia_key_articles(session: requests.Session, source_id: str) -> list[dict]:
    """Scrape key Champagne articles from Wikipedia for lead sentences and infoboxes."""
    facts = []
    seen = set()

    def _add(text, domain="wine_regions", subdomain="champagne", entities=None,
             tags=None, confidence=0.9):
        if text in seen:
            return
        seen.add(text)
        facts.append({
            "fact_text": text,
            "domain": domain,
            "subdomain": subdomain,
            "source_id": source_id,
            "entities": entities or [],
            "confidence": confidence,
            "tags": tags or ["champagne", "wikipedia"],
        })

    key_articles = [
        "Champagne (wine)",
        "Échelle des Crus",
        "Méthode champenoise",
        "Dosage (wine)",
        "Champagne wine region",
        "Champagne (wine region)",
        "Blanc de blancs",
        "Blanc de noirs",
        "Champagne producer",
        "Rosé Champagne",
    ]

    for title in key_articles:
        logger.info(f"Fetching Wikipedia article: {title}")
        extract, wikitext = fetch_article(session, title)

        if extract:
            sentences = extract_lead_sentences(extract)
            for s in sentences[:10]:
                _add(s, entities=[{"type": "region", "name": title}],
                     tags=["champagne", "wikipedia", "key_article"])

        if wikitext:
            # Parse infobox data
            infobox = parse_infobox(wikitext)
            if infobox:
                grape = infobox.get("grapes", "") or infobox.get("grape", "")
                area = infobox.get("area", "") or infobox.get("size", "") or infobox.get("hectares", "")
                region = infobox.get("region", "")
                year = infobox.get("year established", "") or infobox.get("established", "")
                classification = infobox.get("classification", "")

                if grape:
                    grapes = [g.strip() for g in re.split(r"[,;]", grape) if g.strip()]
                    for g in grapes[:8]:
                        if 2 < len(g) < 50:
                            _add(
                                f"{title} permits the {g} grape variety.",
                                domain="grape_varieties",
                                entities=[
                                    {"type": "region", "name": title},
                                    {"type": "grape", "name": g},
                                ],
                                tags=["champagne", "wikipedia", "grape"],
                            )

                if area and re.search(r"\d", area):
                    _add(
                        f"{title} covers approximately {area} hectares.",
                        entities=[{"type": "region", "name": title}],
                        tags=["champagne", "wikipedia", "area"],
                    )

                if classification:
                    _add(
                        f"{title} holds {classification} classification.",
                        entities=[{"type": "region", "name": title}],
                        tags=["champagne", "wikipedia", "classification"],
                    )

                if year and re.search(r"\d{4}", year):
                    year_match = re.search(r"\d{4}", year)
                    if year_match:
                        _add(
                            f"{title} was established in {year_match.group()}.",
                            entities=[{"type": "region", "name": title}],
                            tags=["champagne", "wikipedia", "history"],
                        )

    return facts


def _scrape_echelle_des_crus(session: requests.Session, source_id: str) -> list[dict]:
    """Parse the Echelle des Crus article for Grand Cru and Premier Cru village tables."""
    facts = []
    seen = set()

    def _add(text, domain="wine_regions", subdomain="champagne", entities=None,
             tags=None, confidence=0.9):
        if text in seen:
            return
        seen.add(text)
        facts.append({
            "fact_text": text,
            "domain": domain,
            "subdomain": subdomain,
            "source_id": source_id,
            "entities": entities or [],
            "confidence": confidence,
            "tags": tags or ["champagne", "wikipedia"],
        })

    # Fetch the Echelle des Crus article
    logger.info("Fetching Échelle des Crus article for village tables")
    extract, wikitext = fetch_article(session, "Échelle des Crus")

    if extract:
        sentences = extract_lead_sentences(extract)
        for s in sentences[:10]:
            _add(s, entities=[{"type": "region", "name": "Échelle des Crus"}],
                 tags=["champagne", "wikipedia", "echelle"])

    if not wikitext:
        logger.warning("No wikitext for Échelle des Crus, trying alternate titles")
        for alt_title in ["Échelle des crus", "Echelle des Crus", "Champagne (wine)"]:
            extract2, wikitext = fetch_article(session, alt_title)
            if wikitext:
                logger.info(f"Found wikitext via: {alt_title}")
                break

    if wikitext:
        rows = parse_wikitext_tables(wikitext)
        logger.info(f"Parsed {len(rows)} table rows from Échelle des Crus")

        for row in rows:
            if len(row) < 1:
                continue

            village = row[0].strip()

            # Skip headers and empty rows
            if not village or village.lower() in (
                "village", "commune", "name", "town", "location",
                "département", "department", "rating", "cru", "classification",
                "grand cru", "premier cru",
            ):
                continue
            if len(village) < 2 or len(village) > 60:
                continue

            # Try to extract the rating/percentage from subsequent columns
            rating = ""
            department = ""
            for cell in row[1:]:
                cell_stripped = cell.strip()
                if re.match(r"^\d{2,3}%?$", cell_stripped):
                    rating = cell_stripped
                elif len(cell_stripped) > 2 and not cell_stripped.startswith(("–", "—", "-")):
                    if not department:
                        department = cell_stripped

            # Determine cru level from rating or context
            cru_level = ""
            if rating:
                rating_num = re.sub(r"[^\d]", "", rating)
                if rating_num:
                    try:
                        pct = int(rating_num)
                        if pct == 100:
                            cru_level = "Grand Cru"
                        elif 90 <= pct <= 99:
                            cru_level = "Premier Cru"
                    except ValueError:
                        pass

            if cru_level:
                fact_text = f"{village} is a {cru_level} village in Champagne."
                if department and len(department) < 40:
                    fact_text = f"{village} is a {cru_level} village in Champagne, located in {department}."
                _add(
                    fact_text,
                    entities=[
                        {"type": "region", "name": village},
                        {"type": "region", "name": "Champagne"},
                    ],
                    tags=["champagne", "wikipedia", "echelle", cru_level.lower().replace(" ", "_")],
                )
                if rating:
                    _add(
                        f"{village} has an Échelle des Crus rating of {rating}.",
                        entities=[{"type": "region", "name": village}],
                        tags=["champagne", "wikipedia", "echelle", "rating"],
                    )
            elif village and len(village) < 40:
                # Row might be a village without a clear rating column
                if re.match(r"^[A-ZÀ-Ü]", village) and not re.search(r"\d", village):
                    _add(
                        f"{village} is a classified cru village in Champagne.",
                        entities=[
                            {"type": "region", "name": village},
                            {"type": "region", "name": "Champagne"},
                        ],
                        tags=["champagne", "wikipedia", "echelle", "cru"],
                    )

    # Also try the full Champagne (wine) article for cru tables
    logger.info("Checking Champagne (wine) article for cru village tables")
    _, champagne_wikitext = fetch_article(session, "Champagne (wine)")
    if champagne_wikitext:
        rows = parse_wikitext_tables(champagne_wikitext)
        logger.info(f"Parsed {len(rows)} table rows from Champagne (wine)")
        for row in rows:
            if len(row) < 1:
                continue
            village = row[0].strip()
            if not village or len(village) < 2 or len(village) > 60:
                continue
            if village.lower() in (
                "village", "commune", "name", "town", "cru",
                "classification", "department",
            ):
                continue

            # Check if any column mentions grand cru or premier cru
            row_text = " ".join(row).lower()
            if "grand cru" in row_text:
                if village not in seen and re.match(r"^[A-ZÀ-Ü]", village):
                    _add(
                        f"{village} is a Grand Cru village in Champagne.",
                        entities=[
                            {"type": "region", "name": village},
                            {"type": "region", "name": "Champagne"},
                        ],
                        tags=["champagne", "wikipedia", "grand_cru"],
                    )
            elif "premier cru" in row_text:
                if village not in seen and re.match(r"^[A-ZÀ-Ü]", village):
                    _add(
                        f"{village} is a Premier Cru village in Champagne.",
                        entities=[
                            {"type": "region", "name": village},
                            {"type": "region", "name": "Champagne"},
                        ],
                        tags=["champagne", "wikipedia", "premier_cru"],
                    )

    return facts


def _scrape_wikipedia_categories(session: requests.Session, source_id: str) -> list[dict]:
    """Scrape Champagne-related articles from Wikipedia categories."""
    facts = []
    seen = set()

    def _add(text, domain="wine_regions", subdomain="champagne", entities=None,
             tags=None, confidence=0.9):
        if text in seen:
            return
        seen.add(text)
        facts.append({
            "fact_text": text,
            "domain": domain,
            "subdomain": subdomain,
            "source_id": source_id,
            "entities": entities or [],
            "confidence": confidence,
            "tags": tags or ["champagne", "wikipedia"],
        })

    categories = [
        "Category:Champagne (wine)",
        "Category:Champagne producers",
        "Category:Champagne wine producers",
    ]

    all_titles = set()
    for cat in categories:
        logger.info(f"Crawling category: {cat}")
        titles = crawl_category(session, cat, max_depth=2, max_articles=100)
        all_titles.update(titles)

    logger.info(f"Found {len(all_titles)} Champagne-related articles from categories")

    for title in sorted(all_titles):
        logger.info(f"Fetching: {title}")
        extract, wikitext = fetch_article(session, title)

        if extract:
            sentences = extract_lead_sentences(extract)
            for s in sentences[:6]:
                _add(s, entities=[{"type": "region", "name": title}],
                     tags=["champagne", "wikipedia", "category"])

        if wikitext:
            infobox = parse_infobox(wikitext)
            if infobox:
                grape = infobox.get("grapes", "") or infobox.get("grape", "")
                area = infobox.get("area", "") or infobox.get("size", "") or infobox.get("hectares", "")
                region = infobox.get("region", "")
                year = (infobox.get("year established", "")
                        or infobox.get("established", "")
                        or infobox.get("founded", ""))
                classification = infobox.get("classification", "")
                founder = infobox.get("founder", "") or infobox.get("founded by", "")
                production = infobox.get("production", "") or infobox.get("annual production", "")

                if region and not region.startswith("Q"):
                    _add(
                        f"{title} is located in {region}.",
                        entities=[{"type": "region", "name": title}],
                        tags=["champagne", "wikipedia", "location"],
                    )

                if grape:
                    grapes = [g.strip() for g in re.split(r"[,;]", grape) if g.strip()]
                    for g in grapes[:5]:
                        if 2 < len(g) < 50:
                            _add(
                                f"{title} uses the {g} grape variety.",
                                domain="grape_varieties",
                                entities=[
                                    {"type": "region", "name": title},
                                    {"type": "grape", "name": g},
                                ],
                                tags=["champagne", "wikipedia", "grape"],
                            )

                if area and re.search(r"\d", area):
                    area_clean = re.sub(r"[^\d.,]", " ", area).strip()
                    if area_clean:
                        _add(
                            f"{title} covers approximately {area_clean} hectares.",
                            entities=[{"type": "region", "name": title}],
                            tags=["champagne", "wikipedia", "area"],
                        )

                if classification:
                    _add(
                        f"{title} holds {classification} classification.",
                        entities=[{"type": "region", "name": title}],
                        tags=["champagne", "wikipedia", "classification"],
                    )

                if year and re.search(r"\d{4}", year):
                    year_match = re.search(r"\d{4}", year)
                    if year_match:
                        _add(
                            f"{title} was established in {year_match.group()}.",
                            entities=[{"type": "region", "name": title}],
                            tags=["champagne", "wikipedia", "history"],
                        )

                if founder and len(founder) < 60:
                    _add(
                        f"{title} was founded by {founder}.",
                        domain="producers",
                        entities=[
                            {"type": "producer", "name": title},
                            {"type": "person", "name": founder},
                        ],
                        tags=["champagne", "wikipedia", "producer"],
                    )

                if production and re.search(r"\d", production):
                    _add(
                        f"{title} has an annual production of {production}.",
                        domain="producers",
                        entities=[{"type": "producer", "name": title}],
                        tags=["champagne", "wikipedia", "production"],
                    )

    return facts


# ─── Wikidata SPARQL ─────────────────────────────────────────────────────────


def _scrape_wikidata(source_id: str) -> list[dict]:
    """Query Wikidata for Champagne wine entities."""
    facts = []
    seen = set()

    def _add(text, domain="wine_regions", subdomain="champagne", entities=None,
             tags=None, confidence=0.85):
        if text in seen:
            return
        seen.add(text)
        facts.append({
            "fact_text": text,
            "domain": domain,
            "subdomain": subdomain,
            "source_id": source_id,
            "entities": entities or [],
            "confidence": confidence,
            "tags": tags or ["champagne", "wikidata"],
        })

    # Query 1: Champagne Grand Cru villages
    query_grand_cru = """
    SELECT DISTINCT ?item ?itemLabel ?departmentLabel WHERE {
        ?item wdt:P31 wd:Q484170 .
        ?item wdt:P131* ?champagne .
        VALUES ?champagne { wd:Q1129 wd:Q12761 wd:Q12549 wd:Q12588 }
        OPTIONAL { ?item wdt:P131 ?department }
        SERVICE wikibase:label { bd:serviceParam wikibase:language "en,fr" }
        FILTER EXISTS {
            ?item wdt:P31 wd:Q484170 .
        }
    }
    ORDER BY ?itemLabel
    LIMIT 100
    """

    try:
        rows = run_sparql(query_grand_cru)
        for row in rows:
            name = row.get("itemLabel", "")
            dept = row.get("departmentLabel", "")
            if not name or name.startswith("Q"):
                continue
            if dept and not dept.startswith("Q"):
                _add(
                    f"{name} is a wine-producing commune in {dept}, Champagne.",
                    entities=[
                        {"type": "region", "name": name},
                        {"type": "region", "name": "Champagne"},
                    ],
                    tags=["champagne", "wikidata", "commune"],
                )
    except Exception as e:
        logger.warning(f"Wikidata Grand Cru query failed: {e}")

    # Query 2: Champagne grape varieties
    query_grapes = """
    SELECT DISTINCT ?item ?itemLabel ?colorLabel WHERE {
        {
            ?item wdt:P31 wd:Q10978 .
            ?item wdt:P2614 ?region .
            VALUES ?region { wd:Q1129 wd:Q183459 }
        }
        UNION
        {
            wd:Q183459 wdt:P186 ?item .
            ?item wdt:P31 wd:Q10978 .
        }
        OPTIONAL { ?item wdt:P462 ?color }
        SERVICE wikibase:label { bd:serviceParam wikibase:language "en,fr" }
    }
    ORDER BY ?itemLabel
    LIMIT 50
    """

    try:
        rows = run_sparql(query_grapes)
        for row in rows:
            name = row.get("itemLabel", "")
            color = row.get("colorLabel", "")
            if not name or name.startswith("Q"):
                continue
            fact_text = f"{name} is a grape variety used in Champagne production."
            if color and not color.startswith("Q"):
                fact_text = f"{name} is a {color} grape variety used in Champagne production."
            _add(
                fact_text,
                domain="grape_varieties",
                entities=[
                    {"type": "grape", "name": name},
                    {"type": "region", "name": "Champagne"},
                ],
                tags=["champagne", "wikidata", "grape"],
            )
    except Exception as e:
        logger.warning(f"Wikidata grapes query failed: {e}")

    # Query 3: Champagne producers / houses
    query_producers = """
    SELECT DISTINCT ?item ?itemLabel ?locationLabel ?foundedLabel WHERE {
        {
            ?item wdt:P31 wd:Q4830453 .
            ?item wdt:P452 wd:Q183459 .
        }
        UNION
        {
            ?item wdt:P31 wd:Q156362 .
            ?item wdt:P131* ?champagne .
            VALUES ?champagne { wd:Q1129 wd:Q12761 }
        }
        OPTIONAL { ?item wdt:P131 ?location }
        OPTIONAL { ?item wdt:P571 ?founded }
        SERVICE wikibase:label { bd:serviceParam wikibase:language "en,fr" }
    }
    ORDER BY ?itemLabel
    LIMIT 200
    """

    try:
        rows = run_sparql(query_producers)
        for row in rows:
            name = row.get("itemLabel", "")
            location = row.get("locationLabel", "")
            founded = row.get("foundedLabel", "")
            if not name or name.startswith("Q"):
                continue
            if location and not location.startswith("Q"):
                _add(
                    f"{name} is a Champagne producer based in {location}.",
                    domain="producers",
                    entities=[
                        {"type": "producer", "name": name},
                        {"type": "region", "name": location},
                    ],
                    tags=["champagne", "wikidata", "producer"],
                )
            else:
                _add(
                    f"{name} is a Champagne producer.",
                    domain="producers",
                    entities=[{"type": "producer", "name": name}],
                    tags=["champagne", "wikidata", "producer"],
                )
            if founded and re.search(r"\d{4}", founded):
                year_match = re.search(r"\d{4}", founded)
                if year_match:
                    _add(
                        f"{name} was founded in {year_match.group()}.",
                        domain="producers",
                        entities=[{"type": "producer", "name": name}],
                        tags=["champagne", "wikidata", "history"],
                    )
    except Exception as e:
        logger.warning(f"Wikidata producers query failed: {e}")

    return facts


# ─── champagne.fr Website Scraping ──────────────────────────────────────────


def _scrape_champagne_fr(source_id: str) -> list[dict]:
    """Scrape supplementary facts from champagne.fr (CIVC)."""
    facts = []
    seen = set()

    paths = [
        "/en/champagne-appellation",
        "/en/champagne-vineyards",
        "/en/grape-varieties",
        "/en/terroir",
        "/en/champagne-making",
    ]

    session = requests.Session()
    session.headers.update(CHAMPAGNE_FR_HEADERS)

    champagne_keywords = re.compile(
        r"\b(?:appellation|vineyard|grape|wine|champagne|AOC|hectare|"
        r"terroir|chardonnay|pinot|meunier|noir|blanc|sparkling|"
        r"dosage|brut|vintage|cuvée|cuvee|cru|grand cru|premier cru|"
        r"assemblage|riddling|disgorgement|lees|fermentation|bottle|"
        r"tirage|remuage|dégorgement|degorgement|liqueur)\b",
        re.IGNORECASE,
    )

    for path in paths:
        url = f"{CHAMPAGNE_FR_BASE_URL}{path}"
        logger.info(f"Attempting to scrape: {url}")
        try:
            time.sleep(CHAMPAGNE_FR_REQUEST_DELAY)
            resp = session.get(url, timeout=REQUEST_TIMEOUT)
            if resp.status_code != 200:
                logger.warning(f"HTTP {resp.status_code} for {url}")
                continue

            soup = BeautifulSoup(resp.text, "html.parser")
            for tag in soup.find_all(["p", "li", "h2", "h3"]):
                text = tag.get_text(strip=True)
                if not text or len(text) < 30:
                    continue
                words = text.split()
                if len(words) < 6 or len(words) > 45:
                    continue
                if not champagne_keywords.search(text):
                    continue
                if text in seen:
                    continue
                seen.add(text)

                # Clean up
                text = text.strip().rstrip(".")
                if not text:
                    continue
                text += "."

                facts.append({
                    "fact_text": text,
                    "domain": "wine_regions",
                    "subdomain": "champagne",
                    "source_id": source_id,
                    "entities": [],
                    "confidence": 0.8,
                    "tags": ["champagne", "champagne_fr", "scraped"],
                })

        except requests.exceptions.RequestException as e:
            logger.warning(f"Failed to scrape {url}: {e}")

    logger.info(f"champagne.fr scraping yielded {len(facts)} facts")
    return facts


# ─── Validation ───────────────────────────────────────────────────────────────


def validate_facts(facts: list[dict]) -> None:
    """Run quality checks on extracted facts."""
    logger.info(f"\n{'='*60}")
    logger.info(f"VALIDATION REPORT — Champagne Scraper")
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
    for tag, count in tag_counter.most_common(10):
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

    # Entity population
    with_entities = sum(1 for f in facts if f.get("entities"))
    logger.info(f"\nFacts with entities: {with_entities}/{len(facts)} ({100*with_entities//max(len(facts),1)}%)")

    # Near-duplicate check
    texts = [f["fact_text"].lower() for f in facts]
    dupes = 0
    for i, t1 in enumerate(texts):
        for t2 in texts[i + 1:]:
            if t1 in t2 or t2 in t1:
                dupes += 1
    logger.info(f"\nNear-duplicate pairs (substring): {dupes}")

    # Sample facts
    logger.info(f"\n10 random sample facts:")
    for f in random.sample(facts, min(10, len(facts))):
        logger.info(f"  [{f['domain']}] (conf={f.get('confidence', 1.0)}) {f['fact_text']}")


# ─── Main Collection ──────────────────────────────────────────────────────────


def collect_all_facts(
    wiki_source_id: str,
    wikidata_source_id: str,
    champagne_fr_source_id: str,
    scrape_champagne_fr: bool = True,
) -> list[dict]:
    """Collect all facts from all sources."""
    session = wiki_session()
    all_facts = []

    # Wikipedia key articles
    logger.info("--- Wikipedia: Key Articles ---")
    key_facts = _scrape_wikipedia_key_articles(session, wiki_source_id)
    logger.info(f"Key article facts: {len(key_facts)}")
    all_facts.extend(key_facts)

    # Wikipedia Echelle des Crus tables
    logger.info("--- Wikipedia: Échelle des Crus ---")
    echelle_facts = _scrape_echelle_des_crus(session, wiki_source_id)
    logger.info(f"Échelle des Crus facts: {len(echelle_facts)}")
    all_facts.extend(echelle_facts)

    # Wikipedia categories
    logger.info("--- Wikipedia: Categories ---")
    category_facts = _scrape_wikipedia_categories(session, wiki_source_id)
    logger.info(f"Category facts: {len(category_facts)}")
    all_facts.extend(category_facts)

    # Wikidata
    logger.info("--- Wikidata SPARQL ---")
    wikidata_facts = _scrape_wikidata(wikidata_source_id)
    logger.info(f"Wikidata facts: {len(wikidata_facts)}")
    all_facts.extend(wikidata_facts)

    # champagne.fr website
    if scrape_champagne_fr:
        logger.info("--- champagne.fr website ---")
        web_facts = _scrape_champagne_fr(champagne_fr_source_id)
        logger.info(f"champagne.fr facts: {len(web_facts)}")
        all_facts.extend(web_facts)

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
    """Run a small test: fetch a few articles, insert, report, optionally clean up."""
    from src.utils.db import get_pg

    logger.info("=== TEST RUN: Champagne Scraper ===")
    wiki_sid = ensure_wiki_source("Champagne wine")
    wikidata_sid = ensure_wikidata_source("Champagne wine")
    champagne_fr_sid = ensure_source(
        name="CIVC (Champagne Bureau)",
        url="https://www.champagne.fr",
        source_type="official_body",
        tier="tier_2_authoritative",
        language="en",
    )

    session = wiki_session()

    # Just fetch a few specific articles
    test_articles = ["Champagne (wine)", "Moët & Chandon", "Veuve Clicquot",
                     "Échelle des Crus", "Méthode champenoise"]
    facts = []
    seen = set()
    for title in test_articles[:TEST_RUN_LIMIT]:
        extract, wikitext = fetch_article(session, title)
        if extract:
            for s in extract_lead_sentences(extract)[:3]:
                if s not in seen:
                    seen.add(s)
                    facts.append({
                        "fact_text": s,
                        "domain": "wine_regions",
                        "subdomain": "champagne",
                        "source_id": wiki_sid,
                        "entities": [{"type": "region", "name": title}],
                        "confidence": 0.9,
                        "tags": ["champagne", "wikipedia", "test"],
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
    """Champagne wine scraper — genuine external data only."""

    if list_sections:
        click.echo("Champagne Scraper — Data Sources:")
        click.echo("  1. Wikipedia: Champagne wine articles & Échelle des Crus tables")
        click.echo("  2. Wikipedia: Champagne category articles (producers, styles)")
        click.echo("  3. Wikidata: Grand Cru villages, grape varieties, producers (SPARQL)")
        click.echo("  4. champagne.fr (CIVC): Supplementary web scraping")
        return

    if test_run:
        run_test(cleanup=cleanup)
        return

    if not run_all and not dry_run and not validate:
        click.echo("Use --all, --dry-run, --validate, --test-run, or --list")
        return

    # Register sources
    wiki_sid = ensure_wiki_source("Champagne wine")
    wikidata_sid = ensure_wikidata_source("Champagne wine")
    champagne_fr_sid = ensure_source(
        name="CIVC (Champagne Bureau)",
        url="https://www.champagne.fr",
        source_type="official_body",
        tier="tier_2_authoritative",
        language="en",
    )

    # Collect facts
    facts = collect_all_facts(wiki_sid, wikidata_sid, champagne_fr_sid)

    if validate or dry_run:
        validate_facts(facts)

    if dry_run:
        logger.info(f"\nDRY RUN — {len(facts)} facts generated, not inserted")
        return

    if run_all:
        before = get_fact_count()
        inserted = insert_facts_batch(facts)
        after = get_fact_count()
        logger.info(f"Inserted {inserted} new facts (DB: {before} → {after})")


if __name__ == "__main__":
    main()
