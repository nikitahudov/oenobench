"""
OenoBench — South American Wine Scraper (Argentina & Chile) — genuine external data only

Extracts South American wine knowledge from:
  1. Wikipedia — key articles on Argentine wine, Chilean wine, Malbec, Carménère, etc.
  2. Wikipedia categories — "Wine regions of Argentina", "Wine regions of Chile"
  3. Wikidata SPARQL — wine regions with P17=Q414 (Argentina), P17=Q298 (Chile)
  4. Official sites — winesofargentina.org, winesofchile.org via _web_helpers.py

Every fact traces to a URL that was actually fetched and parsed.
No hardcoded wine knowledge.

Usage:
    python -m src.scrapers.south_america --all
    python -m src.scrapers.south_america --dry-run
    python -m src.scrapers.south_america --validate
    python -m src.scrapers.south_america --list
    python -m src.scrapers.south_america --test-run
    python -m src.scrapers.south_america --test-run --cleanup
"""

import random
import re
import time
from collections import Counter
from typing import Optional

import click
import requests
from loguru import logger

from src.utils.facts import ensure_source, insert_facts_batch, get_fact_count
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
from src.scrapers._wiki_helpers import (
    wiki_session,
    fetch_article,
    fetch_full_extract,
    crawl_category,
    parse_infobox,
    parse_wikitext_tables,
    extract_lead_sentences,
    extract_atomic_facts,
    run_sparql_filtered,
    ensure_wiki_source,
    ensure_wikidata_source,
    clean_wiki_value,
    is_wine_relevant,
    SPARQL_WINE_REGIONS_BY_COUNTRY,
    SPARQL_GRAPE_VARIETIES_BY_COUNTRY,
    SPARQL_WINERIES_BY_COUNTRY,
    SPARQL_APPELLATIONS_BY_COUNTRY,
    WIKI_REQUEST_DELAY,
)

# ─── Configuration ────────────────────────────────────────────────────────────

TEST_RUN_LIMIT = 5
OFFICIAL_REQUEST_DELAY = 5.0
REQUEST_TIMEOUT = 30

# Override wiki delay for rate limiting
WIKI_REQUEST_DELAY_OVERRIDE = 5.0

# Wikidata QIDs
ARGENTINA_QID = "Q414"
CHILE_QID = "Q298"

# Region keywords for on-topic filtering
ARGENTINA_KEYWORDS = {
    "argentina", "argentine", "mendoza", "malbec", "bonarda", "torrontés",
    "torrontes", "san juan", "salta", "patagonia", "río negro", "rio negro",
    "neuquén", "neuquen", "luján de cuyo", "lujan de cuyo", "valle de uco",
    "uco valley", "tupungato", "tunuyán", "tunuyan", "san carlos",
    "maipú", "maipu", "cafayate", "catamarca", "la rioja",
    "criolla", "cereza", "pedro giménez", "pedro gimenez",
    "bodega", "bodegas", "instituto nacional de vitivinicultura", "inv",
}

CHILE_KEYWORDS = {
    "chile", "chilean", "carménère", "carmenere", "país", "pais",
    "maipo", "maipo valley", "colchagua", "colchagua valley",
    "casablanca", "aconcagua", "rapel", "curicó", "curico",
    "maule", "bío-bío", "bio-bio", "itata", "malleco",
    "limarí", "limari", "elqui", "choapa", "cachapoal",
    "leyda", "san antonio", "central valley",
    "denominación de origen", "do chile",
    "viña", "vina", "concha y toro", "santa rita",
}

SOUTH_AMERICA_KEYWORDS = ARGENTINA_KEYWORDS | CHILE_KEYWORDS | {
    "south america", "south american", "andes", "altitude viticulture",
}


# ─── Wikipedia Scraping ──────────────────────────────────────────────────────


def _scrape_wikipedia_key_articles(session: requests.Session, source_id: str) -> list[dict]:
    """Scrape key South American wine articles from Wikipedia."""
    facts = []
    seen = set()

    key_articles = [
        "Argentine wine",
        "Malbec",
        "Mendoza wine",
        "Torrontés",
        "Bonarda",
        "Chilean wine",
        "Carménère",
        "Maipo Valley",
        "Colchagua Valley",
        "País (grape)",
    ]

    for title in key_articles:
        logger.info(f"Fetching Wikipedia article: {title}")
        time.sleep(WIKI_REQUEST_DELAY_OVERRIDE)
        extract, wikitext = fetch_article(session, title)

        if extract:
            full_ext = fetch_full_extract(session, title)
            text_to_process = full_ext if full_ext else extract

            atomic = extract_atomic_facts(
                text_to_process, title,
                region_keywords=SOUTH_AMERICA_KEYWORDS,
            )
            for item in atomic:
                text = item["fact_text"]
                if text.lower() not in seen:
                    seen.add(text.lower())
                    facts.append({
                        "fact_text": text,
                        "domain": item["domain"],
                        "subdomain": "south_america",
                        "source_id": source_id,
                        "entities": [{"type": "region", "name": title}],
                        "confidence": 0.9,
                        "tags": ["south_america", "wikipedia", "key_article"],
                    })

        if wikitext:
            infobox = parse_infobox(wikitext)
            if infobox:
                grape = infobox.get("grapes", "") or infobox.get("grape", "")
                area = infobox.get("area", "") or infobox.get("size", "") or infobox.get("hectares", "")
                classification = infobox.get("classification", "") or infobox.get("appellation", "")
                region = infobox.get("region", "")
                year = infobox.get("year established", "") or infobox.get("established", "")

                if grape:
                    grapes = [g.strip() for g in re.split(r"[,;]", grape) if g.strip()]
                    for g in grapes[:5]:
                        if 2 < len(g) < 50:
                            text = f"{title} permits the {g} grape variety."
                            if text.lower() not in seen:
                                seen.add(text.lower())
                                facts.append({
                                    "fact_text": text,
                                    "domain": "grape_varieties",
                                    "subdomain": "south_america",
                                    "source_id": source_id,
                                    "entities": [
                                        {"type": "region", "name": title},
                                        {"type": "grape", "name": g},
                                    ],
                                    "confidence": 0.9,
                                    "tags": ["south_america", "wikipedia", "grape"],
                                })

                if area and re.search(r"\d", area):
                    text = f"{title} covers approximately {area} hectares."
                    if text.lower() not in seen:
                        seen.add(text.lower())
                        facts.append({
                            "fact_text": text,
                            "domain": classify_domain(text),
                            "subdomain": "south_america",
                            "source_id": source_id,
                            "entities": [{"type": "region", "name": title}],
                            "confidence": 0.9,
                            "tags": ["south_america", "wikipedia", "area"],
                        })

                if classification:
                    text = f"{title} holds {classification} classification."
                    if text.lower() not in seen:
                        seen.add(text.lower())
                        facts.append({
                            "fact_text": text,
                            "domain": classify_domain(text),
                            "subdomain": "south_america",
                            "source_id": source_id,
                            "entities": [{"type": "region", "name": title}],
                            "confidence": 0.9,
                            "tags": ["south_america", "wikipedia", "classification"],
                        })

                if region and not region.startswith("Q"):
                    text = f"{title} is a wine region in {region}."
                    if text.lower() not in seen:
                        seen.add(text.lower())
                        facts.append({
                            "fact_text": text,
                            "domain": "wine_regions",
                            "subdomain": "south_america",
                            "source_id": source_id,
                            "entities": [{"type": "region", "name": title}],
                            "confidence": 0.9,
                            "tags": ["south_america", "wikipedia", "region"],
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
                                "subdomain": "south_america",
                                "source_id": source_id,
                                "entities": [{"type": "region", "name": title}],
                                "confidence": 0.9,
                                "tags": ["south_america", "wikipedia", "history"],
                            })

    return facts


def _scrape_wikipedia_categories(session: requests.Session, source_id: str) -> list[dict]:
    """Scrape South American wine articles from Wikipedia category crawl."""
    facts = []
    seen = set()

    categories = [
        "Category:Wine regions of Argentina",
        "Category:Wine regions of Chile",
    ]

    all_titles = set()
    for cat in categories:
        logger.info(f"Crawling category: {cat}")
        titles = crawl_category(session, cat, max_depth=2, max_articles=150)
        all_titles.update(titles)

    logger.info(f"Found {len(all_titles)} South American wine articles from categories")

    for title in sorted(all_titles):
        logger.info(f"Fetching: {title}")
        time.sleep(WIKI_REQUEST_DELAY_OVERRIDE)
        extract, wikitext = fetch_article(session, title)

        if extract:
            atomic = extract_atomic_facts(
                extract, title,
                region_keywords=SOUTH_AMERICA_KEYWORDS,
            )
            for item in atomic:
                text = item["fact_text"]
                if text.lower() not in seen:
                    seen.add(text.lower())
                    facts.append({
                        "fact_text": text,
                        "domain": item["domain"],
                        "subdomain": "south_america",
                        "source_id": source_id,
                        "entities": [{"type": "region", "name": title}],
                        "confidence": 0.9,
                        "tags": ["south_america", "wikipedia", "category"],
                    })

        if wikitext:
            infobox = parse_infobox(wikitext)
            if infobox:
                region = infobox.get("region", "")
                grape = infobox.get("grapes", "") or infobox.get("grape", "")
                area = infobox.get("area", "") or infobox.get("size", "") or infobox.get("hectares", "")
                classification = infobox.get("classification", "") or infobox.get("appellation", "") or infobox.get("designation", "")

                if region and not region.startswith("Q"):
                    text = f"{title} is a wine region in {region}."
                    if text.lower() not in seen:
                        seen.add(text.lower())
                        facts.append({
                            "fact_text": text,
                            "domain": "wine_regions",
                            "subdomain": "south_america",
                            "source_id": source_id,
                            "entities": [{"type": "region", "name": title}],
                            "confidence": 0.9,
                            "tags": ["south_america", "wikipedia", "region"],
                        })

                if grape:
                    grapes = [g.strip() for g in re.split(r"[,;]", grape) if g.strip()]
                    for g in grapes[:5]:
                        if 2 < len(g) < 50:
                            text = f"{title} permits the {g} grape variety."
                            if text.lower() not in seen:
                                seen.add(text.lower())
                                facts.append({
                                    "fact_text": text,
                                    "domain": "grape_varieties",
                                    "subdomain": "south_america",
                                    "source_id": source_id,
                                    "entities": [
                                        {"type": "region", "name": title},
                                        {"type": "grape", "name": g},
                                    ],
                                    "confidence": 0.9,
                                    "tags": ["south_america", "wikipedia", "grape"],
                                })

                if area and re.search(r"\d", area):
                    area_clean = re.sub(r"[^\d.,]", " ", area).strip()
                    if area_clean:
                        text = f"{title} covers approximately {area_clean} hectares."
                        if text.lower() not in seen:
                            seen.add(text.lower())
                            facts.append({
                                "fact_text": text,
                                "domain": classify_domain(text),
                                "subdomain": "south_america",
                                "source_id": source_id,
                                "entities": [{"type": "region", "name": title}],
                                "confidence": 0.9,
                                "tags": ["south_america", "wikipedia", "area"],
                            })

                if classification:
                    text = f"{title} holds {classification} classification."
                    if text.lower() not in seen:
                        seen.add(text.lower())
                        facts.append({
                            "fact_text": text,
                            "domain": classify_domain(text),
                            "subdomain": "south_america",
                            "source_id": source_id,
                            "entities": [{"type": "region", "name": title}],
                            "confidence": 0.9,
                            "tags": ["south_america", "wikipedia", "classification"],
                        })

    return facts


# ─── Wikidata SPARQL ─────────────────────────────────────────────────────────


def _scrape_wikidata_country(
    source_id: str, country_qid: str, country_name: str,
    region_keywords: set[str], subdomain_tag: str,
) -> list[dict]:
    """Query Wikidata for wine entities in a specific country."""
    facts = []
    seen = set()

    def _add(text, domain="wine_regions", entities=None, tags=None, confidence=0.85):
        if text.lower() in seen:
            return
        seen.add(text.lower())
        facts.append({
            "fact_text": text,
            "domain": domain,
            "subdomain": "south_america",
            "source_id": source_id,
            "entities": entities or [],
            "confidence": confidence,
            "tags": tags or ["south_america", "wikidata", subdomain_tag],
        })

    # Wine regions
    try:
        query = SPARQL_WINE_REGIONS_BY_COUNTRY.format(country_qid=country_qid)
        rows = run_sparql_filtered(
            query, expected_country=country_name, region_keywords=region_keywords,
        )
        for row in rows:
            name = row.get("itemLabel", "")
            region = row.get("regionLabel", "")
            area = row.get("areaHa", "")
            if not name or name.startswith("Q"):
                continue
            if region and not region.startswith("Q"):
                _add(
                    f"{name} is a wine region in {region}, {country_name}.",
                    entities=[{"type": "region", "name": name}],
                )
            else:
                _add(
                    f"{name} is a wine region in {country_name}.",
                    entities=[{"type": "region", "name": name}],
                )
            if area and re.search(r"\d", str(area)):
                _add(
                    f"{name} covers approximately {area} hectares.",
                    entities=[{"type": "region", "name": name}],
                    tags=["south_america", "wikidata", subdomain_tag, "area"],
                )
    except Exception as e:
        logger.warning(f"Wikidata {country_name} regions query failed: {e}")

    # Grape varieties
    try:
        query = SPARQL_GRAPE_VARIETIES_BY_COUNTRY.format(country_qid=country_qid)
        rows = run_sparql_filtered(
            query, expected_country=country_name, region_keywords=region_keywords,
        )
        for row in rows:
            name = row.get("itemLabel", "")
            color = row.get("colorLabel", "")
            if not name or name.startswith("Q"):
                continue
            if color and not color.startswith("Q"):
                _add(
                    f"{name} is a {country_name} {color} grape variety.",
                    domain="grape_varieties",
                    entities=[{"type": "grape", "name": name}],
                    tags=["south_america", "wikidata", subdomain_tag, "grape"],
                )
            else:
                _add(
                    f"{name} is a grape variety from {country_name}.",
                    domain="grape_varieties",
                    entities=[{"type": "grape", "name": name}],
                    tags=["south_america", "wikidata", subdomain_tag, "grape"],
                )
    except Exception as e:
        logger.warning(f"Wikidata {country_name} grapes query failed: {e}")

    # Wineries
    try:
        query = SPARQL_WINERIES_BY_COUNTRY.format(country_qid=country_qid)
        rows = run_sparql_filtered(
            query, expected_country=country_name, region_keywords=region_keywords,
        )
        for row in rows:
            name = row.get("itemLabel", "")
            location = row.get("regionLabel", "")
            founded = row.get("founded", "")
            if not name or name.startswith("Q"):
                continue
            if location and not location.startswith("Q"):
                _add(
                    f"{name} is a wine producer in {location}, {country_name}.",
                    domain="producers",
                    entities=[
                        {"type": "producer", "name": name},
                        {"type": "region", "name": location},
                    ],
                    tags=["south_america", "wikidata", subdomain_tag, "producer"],
                )
            else:
                _add(
                    f"{name} is a wine producer in {country_name}.",
                    domain="producers",
                    entities=[{"type": "producer", "name": name}],
                    tags=["south_america", "wikidata", subdomain_tag, "producer"],
                )
            if founded:
                year_match = re.search(r"\d{4}", str(founded))
                if year_match:
                    _add(
                        f"{name} was founded in {year_match.group()}.",
                        domain="producers",
                        entities=[{"type": "producer", "name": name}],
                        tags=["south_america", "wikidata", subdomain_tag, "producer", "history"],
                    )
    except Exception as e:
        logger.warning(f"Wikidata {country_name} producers query failed: {e}")

    # Appellations
    try:
        query = SPARQL_APPELLATIONS_BY_COUNTRY.format(country_qid=country_qid)
        rows = run_sparql_filtered(
            query, expected_country=country_name, region_keywords=region_keywords,
        )
        for row in rows:
            name = row.get("itemLabel", "")
            region = row.get("regionLabel", "")
            if not name or name.startswith("Q"):
                continue
            if region and not region.startswith("Q"):
                _add(
                    f"{name} is a wine appellation in {region}, {country_name}.",
                    domain="wine_regions",
                    entities=[{"type": "appellation", "name": name}],
                    tags=["south_america", "wikidata", subdomain_tag, "appellation"],
                )
            else:
                _add(
                    f"{name} is a wine appellation in {country_name}.",
                    domain="wine_regions",
                    entities=[{"type": "appellation", "name": name}],
                    tags=["south_america", "wikidata", subdomain_tag, "appellation"],
                )
    except Exception as e:
        logger.warning(f"Wikidata {country_name} appellations query failed: {e}")

    return facts


def _scrape_wikidata(wikidata_source_id: str) -> list[dict]:
    """Query Wikidata for both Argentina and Chile wine entities."""
    facts = []

    logger.info("--- Wikidata: Argentina ---")
    argentina_facts = _scrape_wikidata_country(
        wikidata_source_id, ARGENTINA_QID, "Argentina",
        ARGENTINA_KEYWORDS, "argentina",
    )
    logger.info(f"Argentina Wikidata facts: {len(argentina_facts)}")
    facts.extend(argentina_facts)

    logger.info("--- Wikidata: Chile ---")
    chile_facts = _scrape_wikidata_country(
        wikidata_source_id, CHILE_QID, "Chile",
        CHILE_KEYWORDS, "chile",
    )
    logger.info(f"Chile Wikidata facts: {len(chile_facts)}")
    facts.extend(chile_facts)

    return facts


# ─── Official Sites Scraping ────────────────────────────────────────────────


def _scrape_official_site(
    base_url: str, site_name: str, source_id: str,
    seed_paths: list[str], region_keywords: set[str],
    subject: str, subdomain_tag: str,
) -> list[dict]:
    """Scrape facts from an official wine organization site."""
    facts = []
    seen = set()

    try:
        page_results = scrape_site_texts(
            base_url=base_url,
            seed_paths=seed_paths,
            max_pages=30,
            delay=OFFICIAL_REQUEST_DELAY,
            min_words=8,
            max_words=60,
        )

        all_texts = []
        for url, blocks in page_results:
            all_texts.extend(blocks)

        if not all_texts:
            logger.warning(f"{site_name} returned no text blocks (may be blocked)")
            return facts

        processed = process_facts(
            raw_texts=all_texts,
            subject=subject,
            region_keywords=region_keywords,
        )

        for item in processed:
            text = item["fact_text"]
            if text.lower() not in seen:
                seen.add(text.lower())
                facts.append({
                    "fact_text": text,
                    "domain": item["domain"],
                    "subdomain": "south_america",
                    "source_id": source_id,
                    "entities": [],
                    "confidence": 0.8,
                    "tags": ["south_america", subdomain_tag, "official_site"],
                })

    except Exception as e:
        logger.warning(f"Failed to scrape {site_name}: {e}")

    logger.info(f"{site_name} scraping yielded {len(facts)} facts")
    return facts


def _scrape_official_sites(argentina_source_id: str, chile_source_id: str) -> list[dict]:
    """Scrape official wine organization websites."""
    facts = []

    logger.info("--- winesofargentina.org ---")
    argentina_facts = _scrape_official_site(
        base_url="https://www.winesofargentina.org",
        site_name="Wines of Argentina",
        source_id=argentina_source_id,
        seed_paths=["/en/regions/", "/en/grape-varieties/", "/en/"],
        region_keywords=ARGENTINA_KEYWORDS,
        subject="Argentine wine",
        subdomain_tag="argentina",
    )
    facts.extend(argentina_facts)

    logger.info("--- winesofchile.org ---")
    chile_facts = _scrape_official_site(
        base_url="https://www.winesofchile.org",
        site_name="Wines of Chile",
        source_id=chile_source_id,
        seed_paths=["/en/regions/", "/en/grape-varieties/", "/en/"],
        region_keywords=CHILE_KEYWORDS,
        subject="Chilean wine",
        subdomain_tag="chile",
    )
    facts.extend(chile_facts)

    return facts


# ─── Validation ───────────────────────────────────────────────────────────────


def validate_facts(facts: list[dict]) -> None:
    """Run quality checks on extracted facts."""
    click.echo(f"\n{'='*60}")
    click.echo(f"VALIDATION REPORT — South America Scraper")
    click.echo(f"{'='*60}")
    click.echo(f"Total facts: {len(facts)}")

    # Domain breakdown
    domains = Counter(f["domain"] for f in facts)
    click.echo(f"\nDomain breakdown:")
    for domain, count in domains.most_common():
        click.echo(f"  {domain}: {count}")

    # Confidence breakdown
    confs = Counter(f.get("confidence", 1.0) for f in facts)
    click.echo(f"\nConfidence breakdown:")
    for conf, count in sorted(confs.items(), reverse=True):
        click.echo(f"  {conf}: {count}")

    # Source tag breakdown
    tag_counter = Counter()
    for f in facts:
        for t in f.get("tags", []):
            tag_counter[t] += 1
    click.echo(f"\nSource tags:")
    for tag, count in tag_counter.most_common(15):
        click.echo(f"  {tag}: {count}")

    # Length checks
    short = [f for f in facts if len(f["fact_text"].split()) < 5]
    long_facts = [f for f in facts if len(f["fact_text"].split()) > 50]
    click.echo(f"\nShort facts (<5 words): {len(short)}")
    click.echo(f"Long facts (>50 words): {len(long_facts)}")
    for f in short[:5]:
        click.echo(f"  SHORT: {f['fact_text']}")
    for f in long_facts[:5]:
        click.echo(f"  LONG: {f['fact_text']}")

    # Near-duplicate check
    texts = [f["fact_text"].lower() for f in facts]
    dupes = 0
    sample = texts[:200]
    for i, t1 in enumerate(sample):
        for t2 in sample[i + 1:]:
            if t1 in t2 or t2 in t1:
                dupes += 1
    click.echo(f"\nNear-duplicate pairs (substring, sampled): {dupes}")

    # Entity coverage
    with_entities = sum(1 for f in facts if f.get("entities"))
    click.echo(f"\nFacts with entities: {with_entities}/{len(facts)} ({100*with_entities//max(len(facts),1)}%)")

    # Sample facts
    click.echo(f"\n10 random sample facts:")
    for f in random.sample(facts, min(10, len(facts))):
        click.echo(f"  [{f['domain']}] (conf={f.get('confidence', 1.0)}) {f['fact_text']}")


# ─── Main Collection ──────────────────────────────────────────────────────────


def collect_all_facts(
    wiki_source_id: str,
    wikidata_source_id: str,
    argentina_web_source_id: str,
    chile_web_source_id: str,
    scrape_web: bool = True,
) -> list[dict]:
    """Collect all facts from all sources."""
    session = wiki_session()
    all_facts = []

    # Wikipedia key articles
    logger.info("--- Wikipedia: Key Articles ---")
    key_facts = _scrape_wikipedia_key_articles(session, wiki_source_id)
    logger.info(f"Key article facts: {len(key_facts)}")
    all_facts.extend(key_facts)

    # Wikipedia category crawl
    logger.info("--- Wikipedia: Category Crawl ---")
    category_facts = _scrape_wikipedia_categories(session, wiki_source_id)
    logger.info(f"Category facts: {len(category_facts)}")
    all_facts.extend(category_facts)

    # Wikidata
    logger.info("--- Wikidata SPARQL ---")
    wikidata_facts = _scrape_wikidata(wikidata_source_id)
    logger.info(f"Wikidata facts: {len(wikidata_facts)}")
    all_facts.extend(wikidata_facts)

    # Official sites
    if scrape_web:
        logger.info("--- Official Sites ---")
        web_facts = _scrape_official_sites(argentina_web_source_id, chile_web_source_id)
        logger.info(f"Official site facts: {len(web_facts)}")
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

    logger.info("=== TEST RUN: South America Scraper ===")
    wiki_sid = ensure_wiki_source("South American wine")
    wikidata_sid = ensure_wikidata_source("South American wine")

    session = wiki_session()

    test_articles = ["Argentine wine", "Malbec", "Chilean wine", "Carménère", "Mendoza wine"]
    facts = []
    seen = set()
    for title in test_articles[:TEST_RUN_LIMIT]:
        time.sleep(WIKI_REQUEST_DELAY_OVERRIDE)
        extract, wikitext = fetch_article(session, title)
        if extract:
            atomic = extract_atomic_facts(
                extract, title,
                region_keywords=SOUTH_AMERICA_KEYWORDS,
            )
            for item in atomic[:3]:
                text = item["fact_text"]
                if text.lower() not in seen:
                    seen.add(text.lower())
                    facts.append({
                        "fact_text": text,
                        "domain": item["domain"],
                        "subdomain": "south_america",
                        "source_id": wiki_sid,
                        "entities": [{"type": "region", "name": title}],
                        "confidence": 0.9,
                        "tags": ["south_america", "wikipedia", "test"],
                    })

    click.echo(f"Test run generated {len(facts)} facts")
    if facts:
        inserted = insert_facts_batch(facts)
        click.echo(f"Inserted: {inserted}")

    for f in facts[:10]:
        click.echo(f"  [{f['domain']}] {f['fact_text']}")

    if cleanup and facts:
        conn = get_pg()
        cur = conn.cursor()
        for f in facts:
            cur.execute("DELETE FROM facts WHERE fact_text = %s", (f["fact_text"],))
        conn.commit()
        click.echo(f"Cleaned up {len(facts)} test facts")


# ─── CLI ──────────────────────────────────────────────────────────────────────


@click.command()
@click.option("--all", "run_all", is_flag=True, help="Run full extraction and insert into database")
@click.option("--list", "list_sections", is_flag=True, help="List available data sources")
@click.option("--dry-run", "dry_run", is_flag=True, help="Collect facts but don't insert into database")
@click.option("--validate", "validate", is_flag=True, help="Run quality checks on generated facts")
@click.option("--test-run", is_flag=True, help="Process a small sample, insert, and report")
@click.option("--cleanup", is_flag=True, help="With --test-run, delete inserted facts after reporting")
def main(run_all, list_sections, dry_run, validate, test_run, cleanup):
    """South American wine scraper — genuine external data only."""
    logger.add("data/logs/south_america_{time}.log", rotation="10 MB")

    if list_sections:
        click.echo("South America Scraper — Data Sources:")
        click.echo("  1. Wikipedia: South American wine key articles & category crawl")
        click.echo("     - Key articles: Argentine wine, Malbec, Mendoza wine, Torrontés,")
        click.echo("       Bonarda, Chilean wine, Carménère, Maipo Valley, Colchagua Valley, País")
        click.echo("     - Categories: Wine regions of Argentina, Wine regions of Chile")
        click.echo("  2. Wikidata: South American wine entities (SPARQL)")
        click.echo("     - Argentina: wine regions P17=Q414, grapes P495=Q414, wineries, appellations")
        click.echo("     - Chile: wine regions P17=Q298, grapes P495=Q298, wineries, appellations")
        click.echo("  3. Official sites: winesofargentina.org, winesofchile.org")
        return

    if test_run:
        run_test(cleanup=cleanup)
        return

    if not run_all and not dry_run and not validate:
        click.echo("Use --all, --dry-run, --validate, --test-run, or --list")
        return

    # Register sources
    wiki_sid = ensure_wiki_source("South American wine")
    wikidata_sid = ensure_wikidata_source("South American wine")
    argentina_web_sid = ensure_source(
        name="Wines of Argentina",
        url="https://www.winesofargentina.org",
        source_type="official_body",
        tier="tier_2_authoritative",
        language="en",
    )
    chile_web_sid = ensure_source(
        name="Wines of Chile",
        url="https://www.winesofchile.org",
        source_type="official_body",
        tier="tier_2_authoritative",
        language="en",
    )

    # Collect facts
    facts = collect_all_facts(wiki_sid, wikidata_sid, argentina_web_sid, chile_web_sid)

    if validate or dry_run:
        validate_facts(facts)

    if dry_run:
        click.echo(f"\nDRY RUN — {len(facts)} facts generated, not inserted")
        return

    if run_all:
        before = get_fact_count()
        inserted = insert_facts_batch(facts)
        after = get_fact_count()
        click.echo(f"Inserted {inserted} new facts (DB: {before} -> {after})")


if __name__ == "__main__":
    main()
