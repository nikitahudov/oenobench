"""
OenoBench — USA Wine Enrichment Scraper (genuine external data only)

Adds terroir, climate, and regional depth for US wine regions beyond the TTB
scraper's AVA names and regulatory data.

Extracts from:
  1. Wikipedia — key articles on US wine regions, grape varieties, appellations
  2. Wikidata SPARQL — wine regions with P17=Q30 (USA), grape varieties, wineries
  3. wineinstitute.org — supplementary scraping when accessible

Every fact traces to a URL that was actually fetched and parsed.
No hardcoded wine knowledge.

Usage:
    python -m src.scrapers.usa_enrichment --all
    python -m src.scrapers.usa_enrichment --dry-run
    python -m src.scrapers.usa_enrichment --validate
    python -m src.scrapers.usa_enrichment --list
    python -m src.scrapers.usa_enrichment --test-run
    python -m src.scrapers.usa_enrichment --test-run --cleanup
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
)

# ─── Configuration ────────────────────────────────────────────────────────────

TEST_RUN_LIMIT = 5
WINEINSTITUTE_BASE_URL = "https://www.wineinstitute.org"
WINEINSTITUTE_REQUEST_DELAY = 5
REQUEST_TIMEOUT = 30

# USA = Q30 on Wikidata
USA_QID = "Q30"

# Region keywords for on-topic filtering
USA_KEYWORDS = {
    "united states", "american", "usa", "u.s.",
    "california", "napa", "sonoma", "paso robles", "central coast",
    "santa barbara", "monterey", "lodi", "mendocino", "lake county",
    "livermore", "sierra foothills", "temecula", "san luis obispo",
    "alexander valley", "dry creek valley", "russian river valley",
    "carneros", "stags leap", "oakville", "rutherford", "howell mountain",
    "spring mountain", "diamond mountain", "atlas peak", "mount veeder",
    "calistoga", "st. helena", "yountville", "los olivos",
    "oregon", "willamette valley", "dundee hills", "eola-amity hills",
    "mcminnville", "ribbon ridge", "chehalem mountains", "umpqua valley",
    "rogue valley", "applegate valley", "van duzer corridor",
    "washington", "columbia valley", "walla walla", "yakima valley",
    "red mountain", "horse heaven hills", "wahluke slope",
    "rattlesnake hills", "snipes mountain", "columbia gorge",
    "new york", "finger lakes", "long island", "hudson valley", "north fork",
    "virginia", "texas", "michigan", "missouri", "arizona",
    "ava", "american viticultural area",
    "cabernet sauvignon", "pinot noir", "chardonnay", "zinfandel",
    "merlot", "sauvignon blanc", "petite sirah", "syrah",
}


# ─── Wikipedia Scraping ──────────────────────────────────────────────────────


def _scrape_wikipedia_key_articles(session: requests.Session, source_id: str) -> list[dict]:
    """Scrape key US wine articles from Wikipedia using atomic fact pipeline."""
    facts = []
    seen = set()

    key_articles = [
        "American wine",
        "California wine",
        "Napa Valley AVA",
        "Sonoma County wine",
        "Willamette Valley AVA",
        "Columbia Valley AVA",
        "Paso Robles AVA",
        "Finger Lakes AVA",
        "Walla Walla Valley AVA",
        "Oregon wine",
        "Washington wine",
        "Texas wine",
        "Virginia wine",
        "New York wine",
        "Zinfandel",
        "Judgment of Paris (wine)",
        "American Viticultural Area",
        "Stags Leap District AVA",
        "Russian River Valley AVA",
        "Santa Barbara County wine",
        "Central Coast AVA",
        "Lodi AVA",
    ]

    for title in key_articles:
        logger.info(f"Fetching Wikipedia article: {title}")
        extract, wikitext = fetch_article(session, title)

        if extract:
            atomic = extract_atomic_facts(
                extract, title,
                region_keywords=USA_KEYWORDS,
            )
            for item in atomic:
                text = item["fact_text"]
                if text.lower() not in seen:
                    seen.add(text.lower())
                    facts.append({
                        "fact_text": text,
                        "domain": item["domain"],
                        "subdomain": "usa",
                        "source_id": source_id,
                        "entities": [{"type": "region", "name": title}],
                        "confidence": 0.9,
                        "tags": ["usa", "wikipedia", "key_article"],
                    })

        if wikitext:
            infobox = parse_infobox(wikitext)
            if infobox:
                grape = infobox.get("grapes", "") or infobox.get("grape", "")
                area = infobox.get("area", "") or infobox.get("size", "") or infobox.get("hectares", "")
                classification = infobox.get("classification", "") or infobox.get("appellation", "")
                region = infobox.get("region", "") or infobox.get("sub-regions", "")
                year = infobox.get("year established", "") or infobox.get("established", "")
                soil = infobox.get("soil", "") or infobox.get("soil types", "")
                climate_info = infobox.get("climate", "")

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
                                    "subdomain": "usa",
                                    "source_id": source_id,
                                    "entities": [
                                        {"type": "region", "name": title},
                                        {"type": "grape", "name": g},
                                    ],
                                    "confidence": 0.9,
                                    "tags": ["usa", "wikipedia", "grape"],
                                })

                if area and re.search(r"\d", area):
                    text = f"{title} covers approximately {area} hectares."
                    if text.lower() not in seen:
                        seen.add(text.lower())
                        facts.append({
                            "fact_text": text,
                            "domain": classify_domain(text),
                            "subdomain": "usa",
                            "source_id": source_id,
                            "entities": [{"type": "region", "name": title}],
                            "confidence": 0.9,
                            "tags": ["usa", "wikipedia", "area"],
                        })

                if classification:
                    text = f"{title} holds {classification} classification."
                    if text.lower() not in seen:
                        seen.add(text.lower())
                        facts.append({
                            "fact_text": text,
                            "domain": classify_domain(text),
                            "subdomain": "usa",
                            "source_id": source_id,
                            "entities": [{"type": "region", "name": title}],
                            "confidence": 0.9,
                            "tags": ["usa", "wikipedia", "classification"],
                        })

                if region and not region.startswith("Q"):
                    text = f"{title} is a wine region in {region}."
                    if text.lower() not in seen:
                        seen.add(text.lower())
                        facts.append({
                            "fact_text": text,
                            "domain": "wine_regions",
                            "subdomain": "usa",
                            "source_id": source_id,
                            "entities": [{"type": "region", "name": title}],
                            "confidence": 0.9,
                            "tags": ["usa", "wikipedia", "region"],
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
                                "subdomain": "usa",
                                "source_id": source_id,
                                "entities": [{"type": "region", "name": title}],
                                "confidence": 0.9,
                                "tags": ["usa", "wikipedia", "history"],
                            })

                if soil:
                    text = f"{title} has soils characterized by {soil}."
                    valid, _ = validate_fact(text)
                    if valid and text.lower() not in seen:
                        seen.add(text.lower())
                        facts.append({
                            "fact_text": text,
                            "domain": "viticulture",
                            "subdomain": "usa",
                            "source_id": source_id,
                            "entities": [{"type": "region", "name": title}],
                            "confidence": 0.9,
                            "tags": ["usa", "wikipedia", "soil"],
                        })

                if climate_info:
                    text = f"{title} has a {climate_info} climate."
                    valid, _ = validate_fact(text)
                    if valid and text.lower() not in seen:
                        seen.add(text.lower())
                        facts.append({
                            "fact_text": text,
                            "domain": "viticulture",
                            "subdomain": "usa",
                            "source_id": source_id,
                            "entities": [{"type": "region", "name": title}],
                            "confidence": 0.9,
                            "tags": ["usa", "wikipedia", "climate"],
                        })

    return facts


def _scrape_wikipedia_categories(session: requests.Session, source_id: str) -> list[dict]:
    """Scrape US wine articles discovered via Wikipedia category crawl."""
    facts = []
    seen = set()

    categories = [
        "Category:American Viticultural Areas",
        "Category:Wine regions of California",
        "Category:Wine regions of Oregon",
        "Category:Wine regions of Washington (state)",
        "Category:American wine",
    ]

    all_titles = set()
    for cat in categories:
        logger.info(f"Crawling category: {cat}")
        titles = crawl_category(session, cat, max_depth=2, max_articles=150)
        all_titles.update(titles)

    logger.info(f"Found {len(all_titles)} US wine-related articles from categories")

    for title in sorted(all_titles):
        logger.info(f"Fetching: {title}")
        extract, wikitext = fetch_article(session, title)

        if extract:
            atomic = extract_atomic_facts(
                extract, title,
                region_keywords=USA_KEYWORDS,
            )
            for item in atomic:
                text = item["fact_text"]
                if text.lower() not in seen:
                    seen.add(text.lower())
                    facts.append({
                        "fact_text": text,
                        "domain": item["domain"],
                        "subdomain": "usa",
                        "source_id": source_id,
                        "entities": [{"type": "region", "name": title}],
                        "confidence": 0.9,
                        "tags": ["usa", "wikipedia", "category"],
                    })

        if wikitext:
            infobox = parse_infobox(wikitext)
            if infobox:
                region = infobox.get("region", "")
                grape = infobox.get("grapes", "") or infobox.get("grape", "")
                area = infobox.get("area", "") or infobox.get("size", "") or infobox.get("hectares", "")
                classification = infobox.get("classification", "") or infobox.get("appellation", "") or infobox.get("designation", "")
                year = infobox.get("year established", "") or infobox.get("established", "")

                if region and not region.startswith("Q"):
                    text = f"{title} is a wine region in {region}."
                    if text.lower() not in seen:
                        seen.add(text.lower())
                        facts.append({
                            "fact_text": text,
                            "domain": "wine_regions",
                            "subdomain": "usa",
                            "source_id": source_id,
                            "entities": [{"type": "region", "name": title}],
                            "confidence": 0.9,
                            "tags": ["usa", "wikipedia", "region"],
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
                                    "subdomain": "usa",
                                    "source_id": source_id,
                                    "entities": [
                                        {"type": "region", "name": title},
                                        {"type": "grape", "name": g},
                                    ],
                                    "confidence": 0.9,
                                    "tags": ["usa", "wikipedia", "grape"],
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
                                "subdomain": "usa",
                                "source_id": source_id,
                                "entities": [{"type": "region", "name": title}],
                                "confidence": 0.9,
                                "tags": ["usa", "wikipedia", "area"],
                            })

                if classification:
                    text = f"{title} holds {classification} classification."
                    if text.lower() not in seen:
                        seen.add(text.lower())
                        facts.append({
                            "fact_text": text,
                            "domain": classify_domain(text),
                            "subdomain": "usa",
                            "source_id": source_id,
                            "entities": [{"type": "region", "name": title}],
                            "confidence": 0.9,
                            "tags": ["usa", "wikipedia", "classification"],
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
                                "subdomain": "usa",
                                "source_id": source_id,
                                "entities": [{"type": "region", "name": title}],
                                "confidence": 0.9,
                                "tags": ["usa", "wikipedia", "history"],
                            })

    return facts


# ─── Wikidata SPARQL ─────────────────────────────────────────────────────────


def _scrape_wikidata(source_id: str) -> list[dict]:
    """Query Wikidata for US wine entities using country-scoped SPARQL."""
    facts = []
    seen = set()

    def _add(text, domain="wine_regions", entities=None, tags=None, confidence=0.85):
        if text.lower() in seen:
            return
        seen.add(text.lower())
        facts.append({
            "fact_text": text,
            "domain": domain,
            "subdomain": "usa",
            "source_id": source_id,
            "entities": entities or [],
            "confidence": confidence,
            "tags": tags or ["usa", "wikidata"],
        })

    # Query 1: Wine regions in the USA
    try:
        query = SPARQL_WINE_REGIONS_BY_COUNTRY.format(country_qid=USA_QID)
        rows = run_sparql_filtered(
            query,
            expected_country="United States",
            region_keywords=USA_KEYWORDS,
        )
        for row in rows:
            name = row.get("itemLabel", "")
            region = row.get("regionLabel", "")
            area = row.get("areaHa", "")
            if not name or name.startswith("Q"):
                continue
            if region and not region.startswith("Q"):
                _add(
                    f"{name} is a wine region in {region}, United States.",
                    entities=[{"type": "region", "name": name}],
                )
            else:
                _add(
                    f"{name} is a wine region in the United States.",
                    entities=[{"type": "region", "name": name}],
                )
            if area and re.search(r"\d", str(area)):
                _add(
                    f"{name} covers approximately {area} hectares.",
                    entities=[{"type": "region", "name": name}],
                    tags=["usa", "wikidata", "area"],
                )
    except Exception as e:
        logger.warning(f"Wikidata regions query failed: {e}")

    # Query 2: US grape varieties (origin = USA)
    try:
        query = SPARQL_GRAPE_VARIETIES_BY_COUNTRY.format(country_qid=USA_QID)
        rows = run_sparql_filtered(
            query,
            expected_country="United States",
            region_keywords=USA_KEYWORDS,
        )
        for row in rows:
            name = row.get("itemLabel", "")
            color = row.get("colorLabel", "")
            if not name or name.startswith("Q"):
                continue
            if color and not color.startswith("Q"):
                _add(
                    f"{name} is an American {color} grape variety.",
                    domain="grape_varieties",
                    entities=[{"type": "grape", "name": name}],
                    tags=["usa", "wikidata", "grape"],
                )
            else:
                _add(
                    f"{name} is an American grape variety.",
                    domain="grape_varieties",
                    entities=[{"type": "grape", "name": name}],
                    tags=["usa", "wikidata", "grape"],
                )
    except Exception as e:
        logger.warning(f"Wikidata grapes query failed: {e}")

    # Query 3: US wineries
    try:
        query = SPARQL_WINERIES_BY_COUNTRY.format(country_qid=USA_QID)
        rows = run_sparql_filtered(
            query,
            expected_country="United States",
            region_keywords=USA_KEYWORDS,
        )
        for row in rows:
            name = row.get("itemLabel", "")
            location = row.get("regionLabel", "")
            founded = row.get("founded", "")
            if not name or name.startswith("Q"):
                continue
            if location and not location.startswith("Q"):
                _add(
                    f"{name} is a wine producer in {location}, United States.",
                    domain="producers",
                    entities=[
                        {"type": "producer", "name": name},
                        {"type": "region", "name": location},
                    ],
                    tags=["usa", "wikidata", "producer"],
                )
            else:
                _add(
                    f"{name} is a wine producer in the United States.",
                    domain="producers",
                    entities=[{"type": "producer", "name": name}],
                    tags=["usa", "wikidata", "producer"],
                )
            if founded:
                year_match = re.search(r"\d{4}", str(founded))
                if year_match:
                    _add(
                        f"{name} was founded in {year_match.group()}.",
                        domain="producers",
                        entities=[{"type": "producer", "name": name}],
                        tags=["usa", "wikidata", "producer", "history"],
                    )
    except Exception as e:
        logger.warning(f"Wikidata producers query failed: {e}")

    # Query 4: US appellations
    try:
        query = SPARQL_APPELLATIONS_BY_COUNTRY.format(country_qid=USA_QID)
        rows = run_sparql_filtered(
            query,
            expected_country="United States",
            region_keywords=USA_KEYWORDS,
        )
        for row in rows:
            name = row.get("itemLabel", "")
            region = row.get("regionLabel", "")
            if not name or name.startswith("Q"):
                continue
            if region and not region.startswith("Q"):
                _add(
                    f"{name} is a designated appellation in {region}, United States.",
                    domain="wine_regions",
                    entities=[{"type": "region", "name": name}],
                    tags=["usa", "wikidata", "appellation"],
                )
            else:
                _add(
                    f"{name} is a designated appellation in the United States.",
                    domain="wine_regions",
                    entities=[{"type": "region", "name": name}],
                    tags=["usa", "wikidata", "appellation"],
                )
    except Exception as e:
        logger.warning(f"Wikidata appellations query failed: {e}")

    return facts


# ─── wineinstitute.org Scraping ──────────────────────────────────────────────


def _scrape_wineinstitute(source_id: str) -> list[dict]:
    """Scrape supplementary facts from wineinstitute.org using shared web helpers."""
    facts = []
    seen = set()

    seed_paths = [
        "/our-industry/statistics",
        "/our-industry",
        "/initiatives",
    ]

    try:
        page_results = scrape_site_texts(
            base_url=WINEINSTITUTE_BASE_URL,
            seed_paths=seed_paths,
            max_pages=20,
            delay=WINEINSTITUTE_REQUEST_DELAY,
            min_words=8,
            max_words=60,
        )

        all_texts = []
        for url, blocks in page_results:
            all_texts.extend(blocks)

        if not all_texts:
            logger.warning("wineinstitute.org returned no text blocks (may be blocked)")
            return facts

        processed = process_facts(
            raw_texts=all_texts,
            subject="American wine",
            region_keywords=USA_KEYWORDS,
        )

        for item in processed:
            text = item["fact_text"]
            if text.lower() not in seen:
                seen.add(text.lower())
                facts.append({
                    "fact_text": text,
                    "domain": item["domain"],
                    "subdomain": "usa",
                    "source_id": source_id,
                    "entities": [],
                    "confidence": 0.8,
                    "tags": ["usa", "wineinstitute", "scraped"],
                })

    except Exception as e:
        logger.warning(f"Failed to scrape wineinstitute.org: {e}")

    logger.info(f"wineinstitute.org scraping yielded {len(facts)} facts")
    return facts


# ─── Validation ───────────────────────────────────────────────────────────────


def validate_facts(facts: list[dict]) -> None:
    """Run quality checks on extracted facts."""
    logger.info(f"\n{'='*60}")
    logger.info(f"VALIDATION REPORT — USA Enrichment Scraper")
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

    # Near-duplicate check
    texts = [f["fact_text"].lower() for f in facts]
    dupes = 0
    sample = texts[:200]
    for i, t1 in enumerate(sample):
        for t2 in sample[i + 1:]:
            if t1 in t2 or t2 in t1:
                dupes += 1
    logger.info(f"\nNear-duplicate pairs (substring, sampled): {dupes}")

    # Entity coverage
    with_entities = sum(1 for f in facts if f.get("entities"))
    logger.info(f"\nFacts with entities: {with_entities}/{len(facts)} ({100*with_entities//max(len(facts),1)}%)")

    # Sample facts
    logger.info(f"\n10 random sample facts:")
    for f in random.sample(facts, min(10, len(facts))):
        logger.info(f"  [{f['domain']}] (conf={f.get('confidence', 1.0)}) {f['fact_text']}")


# ─── Main Collection ──────────────────────────────────────────────────────────


def collect_all_facts(
    wiki_source_id: str,
    wikidata_source_id: str,
    web_source_id: str,
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

    # wineinstitute.org
    if scrape_web:
        logger.info("--- wineinstitute.org ---")
        web_facts = _scrape_wineinstitute(web_source_id)
        logger.info(f"wineinstitute.org facts: {len(web_facts)}")
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

    logger.info("=== TEST RUN: USA Enrichment Scraper ===")
    wiki_sid = ensure_wiki_source("American wine")
    wikidata_sid = ensure_wikidata_source("American wine")
    web_sid = ensure_source(
        name="Wine Institute",
        url=WINEINSTITUTE_BASE_URL,
        source_type="industry_body",
        tier="tier_2_authoritative",
        language="en",
    )

    session = wiki_session()

    test_articles = ["American wine", "Napa Valley AVA", "Willamette Valley AVA",
                     "Zinfandel", "Columbia Valley AVA"]
    facts = []
    seen = set()
    for title in test_articles[:TEST_RUN_LIMIT]:
        extract, wikitext = fetch_article(session, title)
        if extract:
            atomic = extract_atomic_facts(
                extract, title,
                region_keywords=USA_KEYWORDS,
            )
            for item in atomic[:3]:
                text = item["fact_text"]
                if text.lower() not in seen:
                    seen.add(text.lower())
                    facts.append({
                        "fact_text": text,
                        "domain": item["domain"],
                        "subdomain": "usa",
                        "source_id": wiki_sid,
                        "entities": [{"type": "region", "name": title}],
                        "confidence": 0.9,
                        "tags": ["usa", "wikipedia", "test"],
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
    """USA wine enrichment scraper — genuine external data only."""

    if list_sections:
        click.echo("USA Enrichment Scraper — Data Sources:")
        click.echo("  1. Wikipedia: US wine key articles & category crawl")
        click.echo("     - Key articles: American wine, Napa Valley, Sonoma, Willamette Valley, etc.")
        click.echo("     - Categories: American Viticultural Areas, Wine regions of California/Oregon/Washington")
        click.echo("  2. Wikidata: US wine regions, grape varieties, wineries, appellations (SPARQL)")
        click.echo("     - Wine regions with P17=Q30 (country=United States)")
        click.echo("     - Grape varieties with P495=Q30 (origin=United States)")
        click.echo("     - Wineries with P17=Q30")
        click.echo("     - Appellations with P17=Q30")
        click.echo("  3. wineinstitute.org: Supplementary web scraping")
        return

    if test_run:
        run_test(cleanup=cleanup)
        return

    if not run_all and not dry_run and not validate:
        click.echo("Use --all, --dry-run, --validate, --test-run, or --list")
        return

    # Register sources
    wiki_sid = ensure_wiki_source("American wine")
    wikidata_sid = ensure_wikidata_source("American wine")
    web_sid = ensure_source(
        name="Wine Institute",
        url=WINEINSTITUTE_BASE_URL,
        source_type="industry_body",
        tier="tier_2_authoritative",
        language="en",
    )

    # Collect facts
    facts = collect_all_facts(wiki_sid, wikidata_sid, web_sid)

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
