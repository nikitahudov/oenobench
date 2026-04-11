"""
OenoBench — European Wine Registries Scraper (Spain, Germany, Portugal)

Extracts wine data from genuine external sources:
  1. Wikipedia key articles — Spanish wine, Rioja wine, Sherry, Port wine, etc.
  2. Wikipedia category crawl — Wine regions of Spain/Portugal/Germany
  3. Wikidata SPARQL — country-scoped wine regions, wineries, appellations
  4. Official websites — mapa.gob.es, winesofportugal.info, deutscheweine.de

Every fact traces to a URL that was actually fetched and parsed.
No hardcoded wine knowledge.

Usage:
    python -m src.scrapers.europe --all
    python -m src.scrapers.europe --country spain
    python -m src.scrapers.europe --country germany
    python -m src.scrapers.europe --country portugal
    python -m src.scrapers.europe --dry-run
    python -m src.scrapers.europe --validate
    python -m src.scrapers.europe --list
    python -m src.scrapers.europe --test-run
    python -m src.scrapers.europe --test-run --country spain
    python -m src.scrapers.europe --test-run --cleanup
"""

import random
import re
import time
from collections import Counter, defaultdict
from datetime import datetime
from typing import Optional

import click
import requests
from loguru import logger

from src.utils.facts import (
    ensure_source,
    insert_facts_batch,
    get_fact_count,
)
from src.scrapers._fact_processing import (
    process_facts,
    classify_domain,
    validate_fact,
)
from src.scrapers._web_helpers import (
    create_session,
    fetch_page as web_fetch_page,
    extract_text_blocks as web_extract_text_blocks,
    scrape_site_texts,
)
import src.scrapers._wiki_helpers as _wiki_mod
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
    SPARQL_APPELLATIONS_BY_COUNTRY,
    SPARQL_GRAPE_VARIETIES_BY_COUNTRY,
)

# Override the wiki helpers' internal delay to avoid 429s on this VM
_wiki_mod.WIKI_REQUEST_DELAY = 8.0

# ─── Configuration ────────────────────────────────────────────────────────────

WIKI_REQUEST_DELAY = 5.0  # seconds — avoid 429s from Wikipedia API
WIKI_CATEGORY_DELAY = 8.0  # longer delay for category crawl (more requests)
TEST_RUN_LIMIT = 5
COUNTRIES = ["spain", "germany", "portugal"]

# Wikidata QIDs
COUNTRY_QIDS = {
    "spain": "Q29",
    "germany": "Q183",
    "portugal": "Q45",
}

# Region keywords for on-topic filtering (per country)
COUNTRY_KEYWORDS = {
    "spain": {
        "spain", "spanish", "rioja", "priorat", "ribera del duero", "sherry",
        "jerez", "cava", "penedès", "navarra", "galicia", "rías baixas",
        "la mancha", "jumilla", "somontano", "rueda", "toro", "bierzo",
        "calatayud", "cariñena", "aragón", "catalonia", "castilla",
        "andalusia", "valencia", "murcia", "extremadura", "canary",
        "tempranillo", "garnacha", "monastrell", "albariño", "verdejo",
        "mencía", "godello", "bobal", "graciano", "mazuelo", "viura",
        "denominación", "doca", "txakolí", "basque",
    },
    "germany": {
        "germany", "german", "mosel", "rheingau", "pfalz", "baden",
        "franken", "nahe", "rheinhessen", "württemberg", "ahr", "sachsen",
        "saale-unstrut", "mittelrhein", "hessische bergstraße",
        "riesling", "spätburgunder", "müller-thurgau", "silvaner",
        "gewürztraminer", "grauburgunder", "weißburgunder",
        "dornfelder", "lemberger", "trollinger",
        "prädikat", "qualitätswein", "kabinett", "spätlese", "auslese",
        "beerenauslese", "trockenbeerenauslese", "eiswein",
        "vdp", "große lage", "erste lage", "gutswein", "ortswein",
    },
    "portugal": {
        "portugal", "portuguese", "douro", "port", "alentejo", "dão",
        "bairrada", "vinho verde", "madeira", "colares", "setúbal",
        "tejo", "lisboa", "minho", "trás-os-montes", "algarve",
        "touriga nacional", "touriga franca", "tinta roriz", "baga",
        "arinto", "fernão pires", "encruzado", "alvarinho", "loureiro",
        "sercial", "verdelho", "boal", "malmsey",
        "doc", "igp", "ivdp", "ivv", "quinta",
    },
}

# Key Wikipedia articles per country
WIKI_KEY_ARTICLES = {
    "spain": [
        "Spanish wine",
        "Rioja wine",
        "Sherry",
        "Ribera del Duero (DO)",
        "Priorat (DOQ)",
        "Rías Baixas (DO)",
        "Cava (DO)",
        "Navarra (DO)",
        "La Mancha (DO)",
        "Penedès (DO)",
        "Rueda (DO)",
        "Bierzo (DO)",
        "Jumilla (DO)",
        "Toro (DO)",
        "Somontano (DO)",
        "Txakoli",
    ],
    "germany": [
        "German wine",
        "Mosel (wine region)",
        "Rheingau (wine region)",
        "Pfalz (wine region)",
        "Baden (wine region)",
        "Franken (wine region)",
        "Nahe (wine region)",
        "Rheinhessen",
        "Württemberg (wine region)",
        "Ahr (wine region)",
        "German wine classification",
        "Riesling",
        "Prädikatswein",
        "Verband Deutscher Prädikatsweingüter",
        "Spätburgunder",
    ],
    "portugal": [
        "Portuguese wine",
        "Port wine",
        "Douro wine",
        "Vinho Verde",
        "Alentejo wine",
        "Dão (wine region)",
        "Bairrada DOC",
        "Madeira wine",
        "Colares DOC",
        "Setúbal DOC",
        "Moscatel de Setúbal",
        "Touriga Nacional",
        "Tinta Roriz",
        "Baga (grape)",
        "Arinto",
    ],
}

# Wikipedia categories per country
WIKI_CATEGORIES = {
    "spain": [
        "Category:Wine regions of Spain",
        "Category:Spanish wine",
    ],
    "germany": [
        "Category:Wine regions of Germany",
        "Category:German wine",
    ],
    "portugal": [
        "Category:Wine regions of Portugal",
        "Category:Portuguese wine",
    ],
}

# Official websites to try per country
OFFICIAL_SITES = {
    "spain": [
        {
            "name": "MAPA (Spain)",
            "base_url": "https://www.mapa.gob.es",
            "seed_paths": [
                "/es/alimentacion/temas/calidad-diferenciada/dop-igp/",
            ],
            "source_type": "government",
            "tier": "tier_1_official",
            "language": "es",
            "max_pages": 20,
        },
    ],
    "germany": [
        {
            "name": "Deutsches Weininstitut",
            "base_url": "https://www.deutscheweine.de",
            "seed_paths": [
                "/en/knowledge/wine-growing-regions/",
            ],
            "source_type": "trade_body",
            "tier": "tier_2_authoritative",
            "language": "de",
            "max_pages": 20,
        },
    ],
    "portugal": [
        {
            "name": "Wines of Portugal",
            "base_url": "https://www.winesofportugal.info",
            "seed_paths": [
                "/en/wine-regions/",
            ],
            "source_type": "trade_body",
            "tier": "tier_2_authoritative",
            "language": "en",
            "max_pages": 20,
        },
    ],
}


# ─── Wikipedia Scraping ──────────────────────────────────────────────────────


def _scrape_wikipedia_key_articles(
    session: requests.Session,
    country: str,
    source_id: str,
) -> list[dict]:
    """Scrape key Wikipedia articles for a given country."""
    facts = []
    seen: set[str] = set()
    articles = WIKI_KEY_ARTICLES.get(country, [])
    keywords = COUNTRY_KEYWORDS.get(country, set())

    for title in articles:
        logger.info(f"[{country}] Fetching Wikipedia article: {title}")
        # Use fetch_full_extract (1 API call) for article text
        time.sleep(WIKI_REQUEST_DELAY)
        full_extract = fetch_full_extract(session, title)

        if full_extract:
            atomic = extract_atomic_facts(
                full_extract, title,
                region_keywords=keywords,
            )
            for item in atomic:
                text = item["fact_text"]
                if text.lower() not in seen:
                    seen.add(text.lower())
                    facts.append({
                        "fact_text": text,
                        "domain": item["domain"],
                        "subdomain": country,
                        "source_id": source_id,
                        "entities": [{"type": "region", "name": title}],
                        "confidence": 0.9,
                        "tags": [country, "wikipedia", "key_article"],
                    })

        # Fetch wikitext for infobox parsing (separate API call)
        time.sleep(WIKI_REQUEST_DELAY)
        _, wikitext = fetch_article(session, title)
        if wikitext:
            _extract_infobox_facts(
                wikitext, title, country, source_id, facts, seen,
            )

    logger.info(f"[{country}] Wikipedia key articles: {len(facts)} facts")
    return facts


def _extract_infobox_facts(
    wikitext: str,
    title: str,
    country: str,
    source_id: str,
    facts: list[dict],
    seen: set[str],
) -> None:
    """Parse infobox from wikitext and add structured facts."""
    infobox = parse_infobox(wikitext)
    if not infobox:
        return

    grape = infobox.get("grapes", "") or infobox.get("grape", "")
    area = infobox.get("area", "") or infobox.get("size", "") or infobox.get("hectares", "")
    classification = infobox.get("classification", "") or infobox.get("appellation", "")
    region = infobox.get("region", "")
    year = infobox.get("year established", "") or infobox.get("established", "")
    soil = infobox.get("soil", "") or infobox.get("geology", "")

    if grape:
        grapes = [g.strip() for g in re.split(r"[,;]", grape) if g.strip()]
        for g in grapes[:8]:
            if 2 < len(g) < 50:
                text = f"{title} permits the {g} grape variety."
                if text.lower() not in seen:
                    seen.add(text.lower())
                    facts.append({
                        "fact_text": text,
                        "domain": "grape_varieties",
                        "subdomain": country,
                        "source_id": source_id,
                        "entities": [
                            {"type": "region", "name": title},
                            {"type": "grape", "name": g},
                        ],
                        "confidence": 0.9,
                        "tags": [country, "wikipedia", "grape"],
                    })

    if area and re.search(r"\d", area):
        area_clean = clean_wiki_value(area)
        if area_clean:
            text = f"{title} covers approximately {area_clean} hectares."
            if text.lower() not in seen:
                seen.add(text.lower())
                facts.append({
                    "fact_text": text,
                    "domain": classify_domain(text),
                    "subdomain": country,
                    "source_id": source_id,
                    "entities": [{"type": "region", "name": title}],
                    "confidence": 0.9,
                    "tags": [country, "wikipedia", "area"],
                })

    if classification:
        text = f"{title} holds {classification} classification."
        if text.lower() not in seen:
            seen.add(text.lower())
            facts.append({
                "fact_text": text,
                "domain": classify_domain(text),
                "subdomain": country,
                "source_id": source_id,
                "entities": [{"type": "region", "name": title}],
                "confidence": 0.9,
                "tags": [country, "wikipedia", "classification"],
            })

    if region and not region.startswith("Q"):
        text = f"{title} is a wine region in {region}."
        if text.lower() not in seen:
            seen.add(text.lower())
            facts.append({
                "fact_text": text,
                "domain": "wine_regions",
                "subdomain": country,
                "source_id": source_id,
                "entities": [{"type": "region", "name": title}],
                "confidence": 0.9,
                "tags": [country, "wikipedia", "region"],
            })

    if year and re.search(r"\d{4}", year):
        year_match = re.search(r"\d{4}", year)
        if year_match:
            text = f"{title} was established in {year_match.group()}."
            if text.lower() not in seen:
                seen.add(text.lower())
                facts.append({
                    "fact_text": text,
                    "domain": classify_domain(text),
                    "subdomain": country,
                    "source_id": source_id,
                    "entities": [{"type": "region", "name": title}],
                    "confidence": 0.9,
                    "tags": [country, "wikipedia", "history"],
                })

    if soil and not soil.startswith("Q"):
        text = f"{title} has soils predominantly composed of {soil}."
        if text.lower() not in seen:
            seen.add(text.lower())
            facts.append({
                "fact_text": text,
                "domain": "viticulture",
                "subdomain": country,
                "source_id": source_id,
                "entities": [{"type": "region", "name": title}],
                "confidence": 0.9,
                "tags": [country, "wikipedia", "soil"],
            })


def _scrape_wikipedia_categories(
    session: requests.Session,
    country: str,
    source_id: str,
) -> list[dict]:
    """Crawl Wikipedia categories for a country and extract facts from discovered articles."""
    facts = []
    seen: set[str] = set()
    categories = WIKI_CATEGORIES.get(country, [])
    keywords = COUNTRY_KEYWORDS.get(country, set())

    all_titles: set[str] = set()
    for cat in categories:
        logger.info(f"[{country}] Crawling category: {cat}")
        time.sleep(WIKI_REQUEST_DELAY)
        titles = crawl_category(session, cat, max_depth=2, max_articles=80)
        all_titles.update(titles)

    logger.info(f"[{country}] Found {len(all_titles)} articles from category crawl")

    for title in sorted(all_titles):
        logger.info(f"[{country}] Fetching category article: {title}")
        time.sleep(WIKI_CATEGORY_DELAY)
        # Use fetch_article to get both intro extract and wikitext in 1 call
        extract, wikitext = fetch_article(session, title)

        if extract:
            atomic = extract_atomic_facts(
                extract, title,
                region_keywords=keywords,
            )
            for item in atomic:
                text = item["fact_text"]
                if text.lower() not in seen:
                    seen.add(text.lower())
                    facts.append({
                        "fact_text": text,
                        "domain": item["domain"],
                        "subdomain": country,
                        "source_id": source_id,
                        "entities": [{"type": "region", "name": title}],
                        "confidence": 0.9,
                        "tags": [country, "wikipedia", "category"],
                    })

        if wikitext:
            _extract_infobox_facts(
                wikitext, title, country, source_id, facts, seen,
            )

    logger.info(f"[{country}] Wikipedia categories: {len(facts)} facts")
    return facts


# ─── Wikidata SPARQL ─────────────────────────────────────────────────────────


def _scrape_wikidata(country: str, source_id: str) -> list[dict]:
    """Query Wikidata for wine entities scoped to a country."""
    facts = []
    seen: set[str] = set()
    qid = COUNTRY_QIDS[country]
    keywords = COUNTRY_KEYWORDS.get(country, set())
    country_name = country.capitalize()

    def _add(text, domain=None, entities=None, tags=None, confidence=0.85):
        if text.lower() in seen:
            return
        seen.add(text.lower())
        facts.append({
            "fact_text": text,
            "domain": domain or classify_domain(text),
            "subdomain": country,
            "source_id": source_id,
            "entities": entities or [],
            "confidence": confidence,
            "tags": tags or [country, "wikidata"],
        })

    # --- Wine regions ---
    logger.info(f"[{country}] SPARQL: wine regions")
    try:
        query = SPARQL_WINE_REGIONS_BY_COUNTRY.format(country_qid=qid)
        rows = run_sparql_filtered(query, expected_country=country_name, region_keywords=keywords)
        # Cap at 200 results to avoid parish-level over-generation (especially Portugal)
        if len(rows) > 200:
            logger.warning(f"[{country}] SPARQL returned {len(rows)} wine regions, capping at 200")
            rows = rows[:200]
        for row in rows:
            name = row.get("itemLabel", "")
            if not name or name.startswith("Q"):
                continue
            region = row.get("regionLabel", "")
            grape = row.get("grapeLabel", "")
            area = row.get("areaHa", "")

            _add(
                f"{name} is a wine-producing region in {country_name}.",
                domain="wine_regions",
                entities=[{"type": "region", "name": name}],
                tags=[country, "wikidata", "wine_region"],
            )
            if region and not region.startswith("Q") and region.lower() != country_name.lower():
                _add(
                    f"{name} wine region is located in {region}, {country_name}.",
                    domain="wine_regions",
                    entities=[{"type": "region", "name": name}],
                    tags=[country, "wikidata", "location"],
                )
            if grape and not grape.startswith("Q"):
                _add(
                    f"{grape} is grown in the {name} wine region of {country_name}.",
                    domain="grape_varieties",
                    entities=[
                        {"type": "region", "name": name},
                        {"type": "grape", "name": grape},
                    ],
                    tags=[country, "wikidata", "grape"],
                )
            if area:
                try:
                    area_val = float(area)
                    _add(
                        f"{name} wine region covers approximately {area_val:,.0f} hectares.",
                        domain="viticulture",
                        entities=[{"type": "region", "name": name}],
                        tags=[country, "wikidata", "area"],
                    )
                except (ValueError, TypeError):
                    pass
    except Exception as e:
        logger.warning(f"[{country}] SPARQL wine regions failed: {e}")

    # --- Wineries ---
    logger.info(f"[{country}] SPARQL: wineries")
    try:
        query = SPARQL_WINERIES_BY_COUNTRY.format(country_qid=qid)
        rows = run_sparql_filtered(query, expected_country=country_name, region_keywords=keywords)
        if len(rows) > 300:
            logger.warning(f"[{country}] SPARQL returned {len(rows)} wineries, capping at 300")
            rows = rows[:300]
        for row in rows:
            name = row.get("itemLabel", "")
            if not name or name.startswith("Q"):
                continue
            region = row.get("regionLabel", "")
            founded = row.get("founded", "")

            _add(
                f"{name} is a winery located in {country_name}.",
                domain="producers",
                entities=[{"type": "producer", "name": name}],
                tags=[country, "wikidata", "winery"],
            )
            if region and not region.startswith("Q"):
                _add(
                    f"{name} winery is located in {region}, {country_name}.",
                    domain="producers",
                    entities=[{"type": "producer", "name": name}],
                    tags=[country, "wikidata", "winery_location"],
                )
            if founded:
                year_match = re.search(r"\d{4}", founded)
                if year_match:
                    _add(
                        f"{name} winery was founded in {year_match.group()}.",
                        domain="producers",
                        entities=[{"type": "producer", "name": name}],
                        tags=[country, "wikidata", "winery_founded"],
                    )
    except Exception as e:
        logger.warning(f"[{country}] SPARQL wineries failed: {e}")

    # --- Appellations ---
    logger.info(f"[{country}] SPARQL: appellations")
    try:
        query = SPARQL_APPELLATIONS_BY_COUNTRY.format(country_qid=qid)
        rows = run_sparql_filtered(query, expected_country=country_name, region_keywords=keywords)
        for row in rows:
            name = row.get("itemLabel", "")
            if not name or name.startswith("Q"):
                continue
            region = row.get("regionLabel", "")

            _add(
                f"{name} is a protected wine appellation in {country_name}.",
                domain="wine_regions",
                entities=[{"type": "appellation", "name": name}],
                tags=[country, "wikidata", "appellation"],
            )
            if region and not region.startswith("Q"):
                _add(
                    f"{name} appellation is located in {region}, {country_name}.",
                    domain="wine_regions",
                    entities=[{"type": "appellation", "name": name}],
                    tags=[country, "wikidata", "appellation_location"],
                )
    except Exception as e:
        logger.warning(f"[{country}] SPARQL appellations failed: {e}")

    # --- Grape varieties (by country of origin) ---
    logger.info(f"[{country}] SPARQL: grape varieties")
    try:
        query = SPARQL_GRAPE_VARIETIES_BY_COUNTRY.format(country_qid=qid)
        rows = run_sparql_filtered(query, expected_country=country_name, region_keywords=keywords)
        for row in rows:
            name = row.get("itemLabel", "")
            if not name or name.startswith("Q"):
                continue
            color = row.get("colorLabel", "")

            _add(
                f"{name} is a grape variety originating from {country_name}.",
                domain="grape_varieties",
                entities=[{"type": "grape", "name": name}],
                tags=[country, "wikidata", "grape_origin"],
            )
            if color and not color.startswith("Q"):
                _add(
                    f"{name} is a {color} grape variety from {country_name}.",
                    domain="grape_varieties",
                    entities=[{"type": "grape", "name": name}],
                    tags=[country, "wikidata", "grape_color"],
                )
    except Exception as e:
        logger.warning(f"[{country}] SPARQL grape varieties failed: {e}")

    logger.info(f"[{country}] Wikidata: {len(facts)} facts")
    return facts


# ─── Official Website Scraping ───────────────────────────────────────────────


def _scrape_official_sites(country: str, source_id: str) -> list[dict]:
    """Try scraping official wine websites for a country."""
    facts = []
    seen: set[str] = set()
    sites = OFFICIAL_SITES.get(country, [])
    keywords = COUNTRY_KEYWORDS.get(country, set())

    for site_cfg in sites:
        site_name = site_cfg["name"]
        base_url = site_cfg["base_url"]
        seed_paths = site_cfg["seed_paths"]
        max_pages = site_cfg.get("max_pages", 20)

        logger.info(f"[{country}] Attempting to scrape {site_name}: {base_url}")
        try:
            page_texts = scrape_site_texts(
                base_url=base_url,
                seed_paths=seed_paths,
                max_pages=max_pages,
                delay=5.0,
                min_words=8,
                max_words=60,
            )

            for url, text_blocks in page_texts:
                logger.info(f"[{country}] Processing {len(text_blocks)} text blocks from {url}")
                processed = process_facts(
                    raw_texts=text_blocks,
                    subject=site_name,
                    region_keywords=keywords,
                )
                for item in processed:
                    text = item["fact_text"]
                    if text.lower() not in seen:
                        seen.add(text.lower())
                        facts.append({
                            "fact_text": text,
                            "domain": item["domain"],
                            "subdomain": country,
                            "source_id": source_id,
                            "entities": [],
                            "confidence": 0.85,
                            "tags": [country, "official_site", site_name.lower().replace(" ", "_")],
                        })

            logger.info(f"[{country}] {site_name}: {len(facts)} facts extracted")

        except Exception as e:
            logger.warning(f"[{country}] Failed to scrape {site_name}: {e}")

    return facts


# ─── Per-Country Scraping ─────────────────────────────────────────────────────


def scrape_country(
    country: str,
    wiki_source_id: str,
    wikidata_source_id: str,
    official_source_id: str,
    test_run: bool = False,
) -> list[dict]:
    """Run all data sources for a single country. Returns list of fact dicts."""
    logger.info(f"=== Scraping {country.upper()} ===")
    all_facts: list[dict] = []

    session = wiki_session()

    # 1. Wikipedia key articles
    key_facts = _scrape_wikipedia_key_articles(session, country, wiki_source_id)
    all_facts.extend(key_facts)
    logger.info(f"[{country}] After key articles: {len(all_facts)} total facts")

    if test_run:
        return all_facts[:TEST_RUN_LIMIT * 10]

    # 2. Wikipedia category crawl
    cat_facts = _scrape_wikipedia_categories(session, country, wiki_source_id)
    # Dedup against existing facts
    seen = {f["fact_text"].lower() for f in all_facts}
    for f in cat_facts:
        if f["fact_text"].lower() not in seen:
            seen.add(f["fact_text"].lower())
            all_facts.append(f)
    logger.info(f"[{country}] After categories: {len(all_facts)} total facts")

    # 3. Wikidata SPARQL
    wd_facts = _scrape_wikidata(country, wikidata_source_id)
    for f in wd_facts:
        if f["fact_text"].lower() not in seen:
            seen.add(f["fact_text"].lower())
            all_facts.append(f)
    logger.info(f"[{country}] After Wikidata: {len(all_facts)} total facts")

    # 4. Official websites
    off_facts = _scrape_official_sites(country, official_source_id)
    for f in off_facts:
        if f["fact_text"].lower() not in seen:
            seen.add(f["fact_text"].lower())
            all_facts.append(f)
    logger.info(f"[{country}] After official sites: {len(all_facts)} total facts")

    logger.info(f"=== {country.upper()} COMPLETE: {len(all_facts)} facts ===")
    return all_facts


# ─── Source Registration ─────────────────────────────────────────────────────


def register_sources() -> dict[str, dict[str, str]]:
    """Register all sources and return nested dict: country -> source_type -> UUID."""
    sources: dict[str, dict[str, str]] = {}
    for country in COUNTRIES:
        country_cap = country.capitalize()
        sources[country] = {
            "wiki": ensure_wiki_source(f"{country_cap} wine"),
            "wikidata": ensure_wikidata_source(f"{country_cap} wine"),
            "official": ensure_source(
                name=f"Official {country_cap} wine sources",
                url=OFFICIAL_SITES[country][0]["base_url"] if OFFICIAL_SITES.get(country) else f"https://{country}.example.com",
                source_type=OFFICIAL_SITES[country][0]["source_type"] if OFFICIAL_SITES.get(country) else "government",
                tier=OFFICIAL_SITES[country][0]["tier"] if OFFICIAL_SITES.get(country) else "tier_2_authoritative",
                language=OFFICIAL_SITES[country][0]["language"] if OFFICIAL_SITES.get(country) else "en",
            ),
        }
    return sources


# ─── Validation ──────────────────────────────────────────────────────────────


def validate_facts(facts: list[dict]) -> None:
    """Run quality checks on generated facts and print a report."""
    domain_counts: dict[str, int] = defaultdict(int)
    subdomain_counts: dict[str, int] = defaultdict(int)
    tag_counts: dict[str, int] = defaultdict(int)

    for f in facts:
        domain_counts[f["domain"]] += 1
        sd = f.get("subdomain") or "(none)"
        subdomain_counts[sd] += 1
        for tag in f.get("tags", []):
            tag_counts[tag] += 1

    click.echo("\n" + "=" * 60)
    click.echo("VALIDATION REPORT — europe.py")
    click.echo("=" * 60)

    click.echo(f"\nTotal facts: {len(facts)}")

    click.echo("\nDomain distribution:")
    for d in sorted(domain_counts.keys()):
        click.echo(f"  {d:25s}: {domain_counts[d]:>5} facts")

    click.echo("\nCountry distribution:")
    for sd in sorted(subdomain_counts.keys()):
        click.echo(f"  {sd:25s}: {subdomain_counts[sd]:>5} facts")

    click.echo("\nSource type distribution:")
    source_tags = {t: c for t, c in tag_counts.items() if t in ("wikipedia", "wikidata", "official_site")}
    for t in sorted(source_tags.keys()):
        click.echo(f"  {t:25s}: {source_tags[t]:>5} facts")

    # Quality checks
    warnings = []
    short = [f for f in facts if len(f["fact_text"].split()) < 5]
    long_ = [f for f in facts if len(f["fact_text"].split()) > 50]
    no_verb = [f for f in facts if not validate_fact(f["fact_text"])[0]]

    if short:
        warnings.append(f"  * {len(short)} facts are suspiciously short (<5 words)")
    if long_:
        warnings.append(f"  * {len(long_)} facts exceed 50 words")
    if no_verb:
        warnings.append(f"  * {len(no_verb)} facts fail validation")

    # Entity coverage
    with_entities = sum(1 for f in facts if f.get("entities"))
    click.echo(f"\nEntity coverage: {with_entities}/{len(facts)} ({100*with_entities/max(len(facts),1):.0f}%)")

    if warnings:
        click.echo("\nWarnings:")
        for w in warnings:
            click.echo(w)

    # Sample facts
    click.echo("\nSample facts (10 random):")
    samples = random.sample(facts, min(10, len(facts)))
    for f in samples:
        click.echo(f"  [{f['domain']:20s}] {f['fact_text']}")

    click.echo()


# ─── Run Logic ───────────────────────────────────────────────────────────────


def run_country(
    country: str,
    sources: dict[str, dict[str, str]],
    dry_run: bool = False,
) -> list[dict]:
    """Scrape a single country and optionally insert into DB."""
    country = country.lower()
    if country not in COUNTRIES:
        logger.error(f"Unknown country: {country}")
        return []

    csrc = sources[country]
    facts = scrape_country(
        country,
        wiki_source_id=csrc["wiki"],
        wikidata_source_id=csrc["wikidata"],
        official_source_id=csrc["official"],
    )

    if dry_run:
        click.echo(f"\n[DRY RUN] {country}: {len(facts)} facts generated (not inserted)")
        domain_counts = Counter(f["domain"] for f in facts)
        for d, c in sorted(domain_counts.items()):
            click.echo(f"  {d:25s}: {c:>5}")
        return facts

    if facts:
        inserted = insert_facts_batch(facts)
        click.echo(f"\n{country}: {inserted} facts inserted into database (from {len(facts)} generated)")
    else:
        click.echo(f"\n{country}: No facts generated")

    return facts


def run_all(dry_run: bool = False) -> dict[str, list[dict]]:
    """Scrape all three countries."""
    sources = register_sources()
    results: dict[str, list[dict]] = {}
    total = 0

    for country in COUNTRIES:
        facts = run_country(country, sources, dry_run=dry_run)
        results[country] = facts
        total += len(facts)

    click.echo(f"\n{'=' * 60}")
    click.echo(f"TOTAL: {total} facts across {len(COUNTRIES)} countries")
    click.echo(f"{'=' * 60}")
    return results


def run_test(
    country: Optional[str] = None,
    cleanup: bool = False,
) -> None:
    """Execute a test run with limited scraping."""
    sources = register_sources()
    countries = [country.lower()] if country else COUNTRIES
    all_facts: list[dict] = []

    for c in countries:
        if c not in COUNTRIES:
            logger.error(f"Unknown country: {c}")
            continue
        csrc = sources[c]
        facts = scrape_country(
            c,
            wiki_source_id=csrc["wiki"],
            wikidata_source_id=csrc["wikidata"],
            official_source_id=csrc["official"],
            test_run=True,
        )
        all_facts.extend(facts)

    click.echo(f"\n[TEST RUN] Generated {len(all_facts)} facts")
    domain_counts = Counter(f["domain"] for f in all_facts)
    for d, c in sorted(domain_counts.items()):
        click.echo(f"  {d:25s}: {c:>5}")

    if all_facts:
        inserted = insert_facts_batch(all_facts)
        click.echo(f"\nInserted {inserted} facts")

    # Sample
    click.echo("\nSample facts:")
    for f in all_facts[:10]:
        click.echo(f"  [{f['domain']:20s}] {f['fact_text']}")

    click.echo()


# =============================================================================
# CLI
# =============================================================================

@click.command()
@click.option("--all", "run_all_flag", is_flag=True, help="Scrape all three countries")
@click.option("--country", type=click.Choice(COUNTRIES, case_sensitive=False), help="Scrape a specific country")
@click.option("--dry-run", is_flag=True, help="Generate facts without inserting into database")
@click.option("--validate", "validate_flag", is_flag=True, help="Run quality checks on generated facts")
@click.option("--list", "list_flag", is_flag=True, help="List available countries and sources")
@click.option("--test-run", "test_run_flag", is_flag=True, help="Quick test run with limited scraping")
@click.option("--cleanup", is_flag=True, help="(unused, kept for CLI compatibility)")
def main(
    run_all_flag: bool,
    country: Optional[str],
    dry_run: bool,
    validate_flag: bool,
    list_flag: bool,
    test_run_flag: bool,
    cleanup: bool,
):
    """OenoBench European Wine Registries Scraper — Spain, Germany, Portugal."""
    log_time = datetime.now().strftime("%Y%m%d_%H%M%S")
    logger.add(f"data/logs/europe_{log_time}.log", rotation="10 MB")

    if list_flag:
        click.echo("\nAvailable countries:")
        for c in COUNTRIES:
            click.echo(f"  {c}")
        click.echo("\nData sources per country:")
        for c in COUNTRIES:
            click.echo(f"\n  {c.upper()}:")
            click.echo(f"    Wikipedia articles: {len(WIKI_KEY_ARTICLES.get(c, []))}")
            click.echo(f"    Wikipedia categories: {len(WIKI_CATEGORIES.get(c, []))}")
            click.echo(f"    Wikidata QID: {COUNTRY_QIDS.get(c, 'N/A')}")
            sites = OFFICIAL_SITES.get(c, [])
            for s in sites:
                click.echo(f"    Official site: {s['name']} ({s['base_url']})")
        return

    if validate_flag:
        click.echo("Generating facts for validation (dry run)...")
        sources = register_sources()
        all_facts: list[dict] = []
        countries = [country] if country else COUNTRIES
        for c in countries:
            csrc = sources[c]
            facts = scrape_country(
                c,
                wiki_source_id=csrc["wiki"],
                wikidata_source_id=csrc["wikidata"],
                official_source_id=csrc["official"],
            )
            all_facts.extend(facts)
        validate_facts(all_facts)
        return

    if test_run_flag:
        run_test(country=country, cleanup=cleanup)
        return

    if run_all_flag:
        run_all(dry_run=dry_run)
        return

    if country:
        sources = register_sources()
        run_country(country, sources, dry_run=dry_run)
        return

    click.echo("Use --all to scrape all countries, or --country <name> for a specific one.")
    click.echo("Use --list to see available countries and sources.")
    click.echo("Use --validate to run quality checks.")
    click.echo("Use --dry-run to generate facts without database insertion.")
    click.echo("Use --test-run for a quick test with limited scraping.")


if __name__ == "__main__":
    main()
