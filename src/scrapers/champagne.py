"""
OenoBench — Champagne Wine Scraper (genuine external data only)

Extracts Champagne wine knowledge from:
  1. Wikipedia — Champagne articles, Echelle des Crus, methode champenoise, dosage
  2. Wikidata SPARQL — wine regions, grape varieties, producers (country-scoped)
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
    extract_atomic_facts,
    run_sparql,
    run_sparql_filtered,
    ensure_wiki_source,
    ensure_wikidata_source,
    clean_wiki_value,
    is_wine_relevant,
    SPARQL_WINE_REGIONS_BY_COUNTRY,
    SPARQL_WINERIES_BY_COUNTRY,
    SPARQL_GRAPE_VARIETIES_BY_COUNTRY,
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
    scrape_site_texts,
    extract_text_blocks,
)

# ─── Configuration ────────────────────────────────────────────────────────────

TEST_RUN_LIMIT = 5
REQUEST_TIMEOUT = 30

# Region keywords for on-topic filtering
CHAMPAGNE_KEYWORDS = {
    "champagne", "marne", "aube", "aisne", "épernay", "epernay",
    "reims", "côte des blancs", "cote des blancs",
    "montagne de reims", "vallée de la marne", "vallee de la marne",
    "côte des bar", "cote des bar",
    "méthode champenoise", "methode champenoise",
    "dosage", "brut", "blanc de blancs", "blanc de noirs",
    "grand cru", "premier cru", "échelle des crus", "echelle des crus",
    "sparkling", "cuvée", "cuvee",
}

# Key Wikipedia articles to scrape
KEY_ARTICLES = [
    "Champagne (wine)",
    "Champagne wine region",
    "Champagne production",
    "Champagne houses",
    "Grower Champagne",
    "Blanc de blancs",
    "Blanc de noirs",
    "Rosé champagne",
    "Échelle des Crus",
    "Méthode champenoise",
    "Dosage (wine)",
    "Veuve Clicquot",
    "Moët & Chandon",
    "Dom Pérignon",
    "Krug (Champagne)",
    "Bollinger",
]


# ─── Wikipedia Scraping ──────────────────────────────────────────────────────


def _scrape_wikipedia_key_articles(session: requests.Session, source_id: str) -> list[dict]:
    """Scrape key Champagne articles from Wikipedia using atomic fact extraction."""
    facts = []
    seen = set()

    for title in KEY_ARTICLES:
        logger.info(f"Fetching Wikipedia article: {title}")
        extract, wikitext = fetch_article(session, title)

        if extract:
            # Use full extract for producer/house articles (not just intro)
            full_extract = extract
            if any(kw in title.lower() for kw in ("clicquot", "moët", "chandon", "dom pérignon",
                                                     "krug", "bollinger", "houses", "grower")):
                full = fetch_full_extract(session, title)
                if full:
                    full_extract = full

            # Use extract_atomic_facts for proper decomposition + validation
            atomic = extract_atomic_facts(
                full_extract,
                article_title=title,
                region_keywords=CHAMPAGNE_KEYWORDS,
            )
            for item in atomic:
                key = item["fact_text"].lower()
                if key not in seen:
                    seen.add(key)
                    facts.append({
                        "fact_text": item["fact_text"],
                        "domain": item["domain"],
                        "subdomain": "champagne",
                        "source_id": source_id,
                        "entities": [{"type": "region", "name": title}],
                        "confidence": 0.9,
                        "tags": ["champagne", "wikipedia", "key_article"],
                    })

        if wikitext:
            # Parse infobox data
            infobox = parse_infobox(wikitext)
            if infobox:
                grape = infobox.get("grapes", "") or infobox.get("grape", "")
                area = infobox.get("area", "") or infobox.get("size", "") or infobox.get("hectares", "")
                year = infobox.get("year established", "") or infobox.get("established", "") or infobox.get("founded", "")
                founder = infobox.get("founder", "") or infobox.get("founded by", "")
                production = infobox.get("production", "") or infobox.get("annual production", "")

                if grape:
                    grapes = [g.strip() for g in re.split(r"[,;]", grape) if g.strip()]
                    for g in grapes[:8]:
                        if 2 < len(g) < 50:
                            fact_text = f"{title} permits the {g} grape variety."
                            key = fact_text.lower()
                            if key not in seen:
                                seen.add(key)
                                facts.append({
                                    "fact_text": fact_text,
                                    "domain": "grape_varieties",
                                    "subdomain": "champagne",
                                    "source_id": source_id,
                                    "entities": [
                                        {"type": "region", "name": title},
                                        {"type": "grape", "name": g},
                                    ],
                                    "confidence": 0.9,
                                    "tags": ["champagne", "wikipedia", "grape"],
                                })

                if area and re.search(r"\d", area):
                    fact_text = f"{title} covers approximately {area} hectares."
                    key = fact_text.lower()
                    if key not in seen:
                        seen.add(key)
                        facts.append({
                            "fact_text": fact_text,
                            "domain": classify_domain(fact_text),
                            "subdomain": "champagne",
                            "source_id": source_id,
                            "entities": [{"type": "region", "name": title}],
                            "confidence": 0.9,
                            "tags": ["champagne", "wikipedia", "area"],
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
                                "subdomain": "champagne",
                                "source_id": source_id,
                                "entities": [{"type": "region", "name": title}],
                                "confidence": 0.9,
                                "tags": ["champagne", "wikipedia", "history"],
                            })

                if founder and len(founder) < 60:
                    fact_text = f"{title} was founded by {founder}."
                    key = fact_text.lower()
                    if key not in seen:
                        seen.add(key)
                        facts.append({
                            "fact_text": fact_text,
                            "domain": "producers",
                            "subdomain": "champagne",
                            "source_id": source_id,
                            "entities": [
                                {"type": "producer", "name": title},
                                {"type": "person", "name": founder},
                            ],
                            "confidence": 0.9,
                            "tags": ["champagne", "wikipedia", "producer"],
                        })

                if production and re.search(r"\d", production):
                    fact_text = f"{title} has an annual production of {production}."
                    key = fact_text.lower()
                    if key not in seen:
                        seen.add(key)
                        facts.append({
                            "fact_text": fact_text,
                            "domain": "producers",
                            "subdomain": "champagne",
                            "source_id": source_id,
                            "entities": [{"type": "producer", "name": title}],
                            "confidence": 0.9,
                            "tags": ["champagne", "wikipedia", "production"],
                        })

    return facts


def _scrape_echelle_des_crus(session: requests.Session, source_id: str) -> list[dict]:
    """Parse the Echelle des Crus article for Grand Cru and Premier Cru village tables."""
    facts = []
    seen = set()

    def _add(text, domain=None, entities=None, tags=None, confidence=0.9):
        key = text.lower()
        if key in seen:
            return
        seen.add(key)
        facts.append({
            "fact_text": text,
            "domain": domain or classify_domain(text),
            "subdomain": "champagne",
            "source_id": source_id,
            "entities": entities or [],
            "confidence": confidence,
            "tags": tags or ["champagne", "wikipedia"],
        })

    # Fetch the Echelle des Crus article
    logger.info("Fetching Échelle des Crus article for village tables")
    extract, wikitext = fetch_article(session, "Échelle des Crus")

    if extract:
        atomic = extract_atomic_facts(extract, "Échelle des Crus",
                                       region_keywords=CHAMPAGNE_KEYWORDS)
        for item in atomic:
            _add(item["fact_text"], domain=item["domain"],
                 entities=[{"type": "region", "name": "Échelle des Crus"}],
                 tags=["champagne", "wikipedia", "echelle"])

    if not wikitext:
        logger.warning("No wikitext for Échelle des Crus, trying alternate titles")
        for alt_title in ["Échelle des crus", "Echelle des Crus", "Champagne (wine)"]:
            _, wikitext = fetch_article(session, alt_title)
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

            row_text = " ".join(row).lower()
            if "grand cru" in row_text:
                if re.match(r"^[A-ZÀ-Ü]", village):
                    _add(
                        f"{village} is a Grand Cru village in Champagne.",
                        entities=[
                            {"type": "region", "name": village},
                            {"type": "region", "name": "Champagne"},
                        ],
                        tags=["champagne", "wikipedia", "grand_cru"],
                    )
            elif "premier cru" in row_text:
                if re.match(r"^[A-ZÀ-Ü]", village):
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

    # Remove articles we already fetched as key articles
    all_titles -= set(KEY_ARTICLES)
    logger.info(f"Found {len(all_titles)} Champagne-related articles from categories")

    for title in sorted(all_titles):
        logger.info(f"Fetching: {title}")
        extract, wikitext = fetch_article(session, title)

        if extract:
            # Use full extract for producer articles to get more facts
            full_extract = extract
            if wikitext:
                infobox = parse_infobox(wikitext)
                # If it has founder/production fields, it's likely a producer - get full article
                if infobox and any(infobox.get(k) for k in ("founder", "founded", "founded by", "production")):
                    full = fetch_full_extract(session, title)
                    if full:
                        full_extract = full

            atomic = extract_atomic_facts(
                full_extract,
                article_title=title,
                region_keywords=CHAMPAGNE_KEYWORDS,
            )
            for item in atomic:
                key = item["fact_text"].lower()
                if key not in seen:
                    seen.add(key)
                    facts.append({
                        "fact_text": item["fact_text"],
                        "domain": item["domain"],
                        "subdomain": "champagne",
                        "source_id": source_id,
                        "entities": [{"type": "region", "name": title}],
                        "confidence": 0.9,
                        "tags": ["champagne", "wikipedia", "category"],
                    })

        if wikitext:
            infobox = parse_infobox(wikitext)
            if infobox:
                region = infobox.get("region", "")
                grape = infobox.get("grapes", "") or infobox.get("grape", "")
                year = (infobox.get("year established", "")
                        or infobox.get("established", "")
                        or infobox.get("founded", ""))
                founder = infobox.get("founder", "") or infobox.get("founded by", "")
                production = infobox.get("production", "") or infobox.get("annual production", "")

                if region and not region.startswith("Q"):
                    fact_text = f"{title} is located in {region}."
                    key = fact_text.lower()
                    if key not in seen:
                        seen.add(key)
                        facts.append({
                            "fact_text": fact_text,
                            "domain": classify_domain(fact_text),
                            "subdomain": "champagne",
                            "source_id": source_id,
                            "entities": [{"type": "region", "name": title}],
                            "confidence": 0.9,
                            "tags": ["champagne", "wikipedia", "location"],
                        })

                if grape:
                    grapes = [g.strip() for g in re.split(r"[,;]", grape) if g.strip()]
                    for g in grapes[:5]:
                        if 2 < len(g) < 50:
                            fact_text = f"{title} uses the {g} grape variety."
                            key = fact_text.lower()
                            if key not in seen:
                                seen.add(key)
                                facts.append({
                                    "fact_text": fact_text,
                                    "domain": "grape_varieties",
                                    "subdomain": "champagne",
                                    "source_id": source_id,
                                    "entities": [
                                        {"type": "region", "name": title},
                                        {"type": "grape", "name": g},
                                    ],
                                    "confidence": 0.9,
                                    "tags": ["champagne", "wikipedia", "grape"],
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
                                "subdomain": "champagne",
                                "source_id": source_id,
                                "entities": [{"type": "region", "name": title}],
                                "confidence": 0.9,
                                "tags": ["champagne", "wikipedia", "history"],
                            })

                if founder and len(founder) < 60:
                    fact_text = f"{title} was founded by {founder}."
                    key = fact_text.lower()
                    if key not in seen:
                        seen.add(key)
                        facts.append({
                            "fact_text": fact_text,
                            "domain": "producers",
                            "subdomain": "champagne",
                            "source_id": source_id,
                            "entities": [
                                {"type": "producer", "name": title},
                                {"type": "person", "name": founder},
                            ],
                            "confidence": 0.9,
                            "tags": ["champagne", "wikipedia", "producer"],
                        })

                if production and re.search(r"\d", production):
                    fact_text = f"{title} has an annual production of {production}."
                    key = fact_text.lower()
                    if key not in seen:
                        seen.add(key)
                        facts.append({
                            "fact_text": fact_text,
                            "domain": "producers",
                            "subdomain": "champagne",
                            "source_id": source_id,
                            "entities": [{"type": "producer", "name": title}],
                            "confidence": 0.9,
                            "tags": ["champagne", "wikipedia", "production"],
                        })

    return facts


# ─── Wikidata SPARQL ─────────────────────────────────────────────────────────


def _is_champagne_relevant(row: dict) -> bool:
    """Check if a SPARQL result row is actually about Champagne (not other French regions)."""
    labels = " ".join(
        v for k, v in row.items()
        if k.endswith("Label") and v and not v.startswith("Q")
    ).lower()
    # Must contain at least one Champagne-specific keyword
    champagne_strict = {
        "champagne", "marne", "aube", "aisne", "épernay", "epernay",
        "reims", "côte des blancs", "montagne de reims",
        "vallée de la marne", "côte des bar",
    }
    return any(kw in labels for kw in champagne_strict)


def _scrape_wikidata(source_id: str) -> list[dict]:
    """Query Wikidata for Champagne wine entities using country-scoped queries."""
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
            "subdomain": "champagne",
            "source_id": source_id,
            "entities": entities or [],
            "confidence": confidence,
            "tags": tags or ["champagne", "wikidata"],
        })

    # Query 1: Wine regions in France, strictly filtered to Champagne
    logger.info("SPARQL: Wine regions in France (Champagne-filtered)")
    try:
        query = SPARQL_WINE_REGIONS_BY_COUNTRY.format(country_qid="Q142")
        rows = run_sparql_filtered(
            query,
            expected_country="France",
            region_keywords=CHAMPAGNE_KEYWORDS,
        )
        # Additional strict filter: must mention Champagne-area terms
        rows = [r for r in rows if _is_champagne_relevant(r)]
        logger.info(f"After Champagne strict filter: {len(rows)} results")
        for row in rows:
            name = row.get("itemLabel", "")
            region = row.get("regionLabel", "")
            grape = row.get("grapeLabel", "")
            area = row.get("areaHa", "")
            if not name or name.startswith("Q"):
                continue

            if region and not region.startswith("Q"):
                _add(
                    f"{name} is a wine-producing area in {region}, Champagne.",
                    entities=[
                        {"type": "region", "name": name},
                        {"type": "region", "name": "Champagne"},
                    ],
                    tags=["champagne", "wikidata", "region"],
                )
            else:
                _add(
                    f"{name} is a wine-producing area in Champagne.",
                    entities=[
                        {"type": "region", "name": name},
                        {"type": "region", "name": "Champagne"},
                    ],
                    tags=["champagne", "wikidata", "region"],
                )

            if grape and not grape.startswith("Q"):
                _add(
                    f"{name} is associated with the {grape} grape variety.",
                    domain="grape_varieties",
                    entities=[
                        {"type": "region", "name": name},
                        {"type": "grape", "name": grape},
                    ],
                    tags=["champagne", "wikidata", "grape"],
                )

            if area and re.search(r"\d", str(area)):
                _add(
                    f"{name} covers approximately {area} hectares.",
                    entities=[{"type": "region", "name": name}],
                    tags=["champagne", "wikidata", "area"],
                )
    except Exception as e:
        logger.warning(f"Wikidata wine regions query failed: {e}")

    # Query 2: Champagne grape varieties — use Champagne-specific SPARQL
    # (The country-scoped grape query returns ALL French grapes, most aren't
    # Champagne-specific. Use a targeted query instead.)
    logger.info("SPARQL: Champagne grape varieties")
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

    # Query 3: Champagne producers / wineries in France (strict Champagne filter)
    logger.info("SPARQL: Wineries in France (Champagne-filtered)")
    try:
        query = SPARQL_WINERIES_BY_COUNTRY.format(country_qid="Q142")
        rows = run_sparql_filtered(
            query,
            expected_country="France",
            region_keywords=CHAMPAGNE_KEYWORDS,
        )
        rows = [r for r in rows if _is_champagne_relevant(r)]
        logger.info(f"After Champagne strict filter: {len(rows)} winery results")
        for row in rows:
            name = row.get("itemLabel", "")
            location = row.get("regionLabel", "")
            founded = row.get("founded", "")
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
    """Scrape supplementary facts from champagne.fr (CIVC) using shared web helpers."""
    facts = []

    base_url = "https://www.champagne.fr"
    seed_paths = [
        "/en/champagne-appellation",
        "/en/champagne-vineyards",
        "/en/grape-varieties",
        "/en/terroir",
        "/en/champagne-making",
    ]

    logger.info("Attempting to scrape champagne.fr...")
    try:
        page_texts = scrape_site_texts(
            base_url=base_url,
            seed_paths=seed_paths,
            max_pages=20,
            delay=5.0,
            min_words=8,
            max_words=50,
        )

        if not page_texts:
            logger.warning("champagne.fr: no pages accessible (site may block scraping)")
            return facts

        for url, blocks in page_texts:
            logger.info(f"champagne.fr: processing {len(blocks)} blocks from {url}")
            # Filter blocks to wine-relevant content before processing
            wine_blocks = [b for b in blocks if is_wine_relevant(b)]
            processed = process_facts(
                raw_texts=wine_blocks,
                subject="Champagne",
                region_keywords=CHAMPAGNE_KEYWORDS,
            )
            for item in processed:
                facts.append({
                    "fact_text": item["fact_text"],
                    "domain": item["domain"],
                    "subdomain": "champagne",
                    "source_id": source_id,
                    "entities": [],
                    "confidence": 0.8,
                    "tags": ["champagne", "champagne_fr", "scraped"],
                })

    except Exception as e:
        logger.warning(f"champagne.fr scraping failed: {e}")

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

    # Entity population
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
        extract, _ = fetch_article(session, title)
        if extract:
            atomic = extract_atomic_facts(extract, title, region_keywords=CHAMPAGNE_KEYWORDS)
            for item in atomic:
                key = item["fact_text"].lower()
                if key not in seen:
                    seen.add(key)
                    facts.append({
                        "fact_text": item["fact_text"],
                        "domain": item["domain"],
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
        click.echo("  3. Wikidata: Wine regions, grape varieties, producers (SPARQL, country-scoped)")
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
