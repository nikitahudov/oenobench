"""
OenoBench — Canadian Wine Scraper (genuine external data only)

Extracts Canadian wine knowledge from:
  1. Wikipedia — key articles on Canadian wine, icewine, VQA, regions
  2. Wikipedia categories — "Wine regions of Canada", "Canadian wine"
  3. Wikidata SPARQL — wine regions with P17=Q16 (Canada), grape varieties, wineries
  4. winesoontario.ca — supplementary scraping when accessible

Every fact traces to a URL that was actually fetched and parsed.
No hardcoded wine knowledge.

Usage:
    python -m src.scrapers.canada --all
    python -m src.scrapers.canada --dry-run
    python -m src.scrapers.canada --validate
    python -m src.scrapers.canada --list
    python -m src.scrapers.canada --test-run
    python -m src.scrapers.canada --test-run --cleanup
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
OFFICIAL_BASE_URL = "https://www.winesoontario.ca"
OFFICIAL_REQUEST_DELAY = 5.0
REQUEST_TIMEOUT = 30

# Override wiki delay for rate limiting
WIKI_REQUEST_DELAY_OVERRIDE = 5.0

# Canada = Q16 on Wikidata
CANADA_QID = "Q16"

# Region keywords for on-topic filtering
CANADA_KEYWORDS = {
    "canada", "canadian", "ontario", "british columbia", "niagara",
    "okanagan", "prince edward county", "nova scotia", "quebec",
    "icewine", "ice wine", "vqa", "dva", "niagara peninsula",
    "niagara-on-the-lake", "beamsville bench", "twenty mile bench",
    "similkameen", "fraser valley", "vancouver island", "gulf islands",
    "annapolis valley", "tidal bay", "lake erie north shore",
    "pelee island", "cowichan", "kelowna",
    "vidal", "riesling", "cabernet franc", "chardonnay", "pinot noir",
    "frontenac", "marquette", "seyval blanc", "l'acadie blanc",
    "inniskillin", "mission hill", "jackson-triggs",
}


# ─── Wikipedia Scraping ──────────────────────────────────────────────────────


def _scrape_wikipedia_key_articles(session: requests.Session, source_id: str) -> list[dict]:
    """Scrape key Canadian wine articles from Wikipedia using atomic fact pipeline."""
    facts = []
    seen = set()

    key_articles = [
        "Canadian wine",
        "Icewine",
        "Niagara Peninsula wine",
        "Okanagan wine",
        "VQA",
        "Niagara-on-the-Lake",
        "British Columbia wine",
        "Nova Scotia wine",
        "Vidal blanc",
        "Riesling",
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
                region_keywords=CANADA_KEYWORDS,
            )
            for item in atomic:
                text = item["fact_text"]
                if text.lower() not in seen:
                    seen.add(text.lower())
                    facts.append({
                        "fact_text": text,
                        "domain": item["domain"],
                        "subdomain": "canada",
                        "source_id": source_id,
                        "entities": [{"type": "region", "name": title}],
                        "confidence": 0.9,
                        "tags": ["canada", "wikipedia", "key_article"],
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
                                    "subdomain": "canada",
                                    "source_id": source_id,
                                    "entities": [
                                        {"type": "region", "name": title},
                                        {"type": "grape", "name": g},
                                    ],
                                    "confidence": 0.9,
                                    "tags": ["canada", "wikipedia", "grape"],
                                })

                if area and re.search(r"\d", area):
                    text = f"{title} covers approximately {area} hectares."
                    if text.lower() not in seen:
                        seen.add(text.lower())
                        facts.append({
                            "fact_text": text,
                            "domain": classify_domain(text),
                            "subdomain": "canada",
                            "source_id": source_id,
                            "entities": [{"type": "region", "name": title}],
                            "confidence": 0.9,
                            "tags": ["canada", "wikipedia", "area"],
                        })

                if classification:
                    text = f"{title} holds {classification} classification."
                    if text.lower() not in seen:
                        seen.add(text.lower())
                        facts.append({
                            "fact_text": text,
                            "domain": classify_domain(text),
                            "subdomain": "canada",
                            "source_id": source_id,
                            "entities": [{"type": "region", "name": title}],
                            "confidence": 0.9,
                            "tags": ["canada", "wikipedia", "classification"],
                        })

                if region and not region.startswith("Q"):
                    text = f"{title} is a wine region in {region}."
                    if text.lower() not in seen:
                        seen.add(text.lower())
                        facts.append({
                            "fact_text": text,
                            "domain": "wine_regions",
                            "subdomain": "canada",
                            "source_id": source_id,
                            "entities": [{"type": "region", "name": title}],
                            "confidence": 0.9,
                            "tags": ["canada", "wikipedia", "region"],
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
                                "subdomain": "canada",
                                "source_id": source_id,
                                "entities": [{"type": "region", "name": title}],
                                "confidence": 0.9,
                                "tags": ["canada", "wikipedia", "history"],
                            })

    return facts


def _scrape_wikipedia_categories(session: requests.Session, source_id: str) -> list[dict]:
    """Scrape Canadian wine articles discovered via Wikipedia category crawl."""
    facts = []
    seen = set()

    categories = [
        "Category:Wine regions of Canada",
        "Category:Canadian wine",
    ]

    all_titles = set()
    for cat in categories:
        logger.info(f"Crawling category: {cat}")
        titles = crawl_category(session, cat, max_depth=2, max_articles=150)
        all_titles.update(titles)

    logger.info(f"Found {len(all_titles)} Canadian wine-related articles from categories")

    for title in sorted(all_titles):
        logger.info(f"Fetching: {title}")
        time.sleep(WIKI_REQUEST_DELAY_OVERRIDE)
        extract, wikitext = fetch_article(session, title)

        if extract:
            atomic = extract_atomic_facts(
                extract, title,
                region_keywords=CANADA_KEYWORDS,
            )
            for item in atomic:
                text = item["fact_text"]
                if text.lower() not in seen:
                    seen.add(text.lower())
                    facts.append({
                        "fact_text": text,
                        "domain": item["domain"],
                        "subdomain": "canada",
                        "source_id": source_id,
                        "entities": [{"type": "region", "name": title}],
                        "confidence": 0.9,
                        "tags": ["canada", "wikipedia", "category"],
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
                            "subdomain": "canada",
                            "source_id": source_id,
                            "entities": [{"type": "region", "name": title}],
                            "confidence": 0.9,
                            "tags": ["canada", "wikipedia", "region"],
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
                                    "subdomain": "canada",
                                    "source_id": source_id,
                                    "entities": [
                                        {"type": "region", "name": title},
                                        {"type": "grape", "name": g},
                                    ],
                                    "confidence": 0.9,
                                    "tags": ["canada", "wikipedia", "grape"],
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
                                "subdomain": "canada",
                                "source_id": source_id,
                                "entities": [{"type": "region", "name": title}],
                                "confidence": 0.9,
                                "tags": ["canada", "wikipedia", "area"],
                            })

                if classification:
                    text = f"{title} holds {classification} classification."
                    if text.lower() not in seen:
                        seen.add(text.lower())
                        facts.append({
                            "fact_text": text,
                            "domain": classify_domain(text),
                            "subdomain": "canada",
                            "source_id": source_id,
                            "entities": [{"type": "region", "name": title}],
                            "confidence": 0.9,
                            "tags": ["canada", "wikipedia", "classification"],
                        })

    return facts


# ─── Wikidata SPARQL ─────────────────────────────────────────────────────────


def _scrape_wikidata(source_id: str) -> list[dict]:
    """Query Wikidata for Canadian wine entities using country-scoped SPARQL."""
    facts = []
    seen = set()

    def _add(text, domain="wine_regions", entities=None, tags=None, confidence=0.85):
        if text.lower() in seen:
            return
        seen.add(text.lower())
        facts.append({
            "fact_text": text,
            "domain": domain,
            "subdomain": "canada",
            "source_id": source_id,
            "entities": entities or [],
            "confidence": confidence,
            "tags": tags or ["canada", "wikidata"],
        })

    # Query 1: Wine regions in Canada
    try:
        query = SPARQL_WINE_REGIONS_BY_COUNTRY.format(country_qid=CANADA_QID)
        rows = run_sparql_filtered(
            query,
            expected_country="Canada",
            region_keywords=CANADA_KEYWORDS,
        )
        for row in rows:
            name = row.get("itemLabel", "")
            region = row.get("regionLabel", "")
            area = row.get("areaHa", "")
            if not name or name.startswith("Q"):
                continue
            if region and not region.startswith("Q"):
                _add(
                    f"{name} is a wine region in {region}, Canada.",
                    entities=[{"type": "region", "name": name}],
                )
            else:
                _add(
                    f"{name} is a wine region in Canada.",
                    entities=[{"type": "region", "name": name}],
                )
            if area and re.search(r"\d", str(area)):
                _add(
                    f"{name} covers approximately {area} hectares.",
                    entities=[{"type": "region", "name": name}],
                    tags=["canada", "wikidata", "area"],
                )
    except Exception as e:
        logger.warning(f"Wikidata regions query failed: {e}")

    # Query 2: Canadian grape varieties
    try:
        query = SPARQL_GRAPE_VARIETIES_BY_COUNTRY.format(country_qid=CANADA_QID)
        rows = run_sparql_filtered(
            query,
            expected_country="Canada",
            region_keywords=CANADA_KEYWORDS,
        )
        for row in rows:
            name = row.get("itemLabel", "")
            color = row.get("colorLabel", "")
            if not name or name.startswith("Q"):
                continue
            if color and not color.startswith("Q"):
                _add(
                    f"{name} is a Canadian {color} grape variety.",
                    domain="grape_varieties",
                    entities=[{"type": "grape", "name": name}],
                    tags=["canada", "wikidata", "grape"],
                )
            else:
                _add(
                    f"{name} is a Canadian grape variety.",
                    domain="grape_varieties",
                    entities=[{"type": "grape", "name": name}],
                    tags=["canada", "wikidata", "grape"],
                )
    except Exception as e:
        logger.warning(f"Wikidata grapes query failed: {e}")

    # Query 3: Canadian wineries
    try:
        query = SPARQL_WINERIES_BY_COUNTRY.format(country_qid=CANADA_QID)
        rows = run_sparql_filtered(
            query,
            expected_country="Canada",
            region_keywords=CANADA_KEYWORDS,
        )
        for row in rows:
            name = row.get("itemLabel", "")
            location = row.get("regionLabel", "")
            founded = row.get("founded", "")
            if not name or name.startswith("Q"):
                continue
            if location and not location.startswith("Q"):
                _add(
                    f"{name} is a wine producer in {location}, Canada.",
                    domain="producers",
                    entities=[
                        {"type": "producer", "name": name},
                        {"type": "region", "name": location},
                    ],
                    tags=["canada", "wikidata", "producer"],
                )
            else:
                _add(
                    f"{name} is a wine producer in Canada.",
                    domain="producers",
                    entities=[{"type": "producer", "name": name}],
                    tags=["canada", "wikidata", "producer"],
                )
            if founded:
                year_match = re.search(r"\d{4}", str(founded))
                if year_match:
                    _add(
                        f"{name} was founded in {year_match.group()}.",
                        domain="producers",
                        entities=[{"type": "producer", "name": name}],
                        tags=["canada", "wikidata", "producer", "history"],
                    )
    except Exception as e:
        logger.warning(f"Wikidata producers query failed: {e}")

    # Query 4: Canadian appellations
    try:
        query = SPARQL_APPELLATIONS_BY_COUNTRY.format(country_qid=CANADA_QID)
        rows = run_sparql_filtered(
            query,
            expected_country="Canada",
            region_keywords=CANADA_KEYWORDS,
        )
        for row in rows:
            name = row.get("itemLabel", "")
            region = row.get("regionLabel", "")
            if not name or name.startswith("Q"):
                continue
            if region and not region.startswith("Q"):
                _add(
                    f"{name} is a Canadian wine appellation in {region}.",
                    domain="wine_regions",
                    entities=[{"type": "appellation", "name": name}],
                    tags=["canada", "wikidata", "appellation"],
                )
            else:
                _add(
                    f"{name} is a Canadian wine appellation.",
                    domain="wine_regions",
                    entities=[{"type": "appellation", "name": name}],
                    tags=["canada", "wikidata", "appellation"],
                )
    except Exception as e:
        logger.warning(f"Wikidata appellations query failed: {e}")

    return facts


# ─── Official Site Scraping ─────────────────────────────────────────────────


def _scrape_official_site(source_id: str) -> list[dict]:
    """Scrape supplementary facts from winesoontario.ca using shared web helpers."""
    facts = []
    seen = set()

    seed_paths = [
        "/",
        "/wines/",
        "/wineries/",
        "/regions/",
        "/about/",
    ]

    try:
        page_results = scrape_site_texts(
            base_url=OFFICIAL_BASE_URL,
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
            logger.warning("winesoontario.ca returned no text blocks (may be blocked or different URL structure)")
            return facts

        processed = process_facts(
            raw_texts=all_texts,
            subject="Canadian wine",
            region_keywords=CANADA_KEYWORDS,
        )

        for item in processed:
            text = item["fact_text"]
            if text.lower() not in seen:
                seen.add(text.lower())
                facts.append({
                    "fact_text": text,
                    "domain": item["domain"],
                    "subdomain": "canada",
                    "source_id": source_id,
                    "entities": [],
                    "confidence": 0.8,
                    "tags": ["canada", "winesoontario", "scraped"],
                })

    except Exception as e:
        logger.warning(f"Failed to scrape winesoontario.ca: {e}")

    logger.info(f"winesoontario.ca scraping yielded {len(facts)} facts")
    return facts


# ─── Validation ───────────────────────────────────────────────────────────────


def validate_facts(facts: list[dict]) -> None:
    """Run quality checks on extracted facts."""
    click.echo(f"\n{'='*60}")
    click.echo(f"VALIDATION REPORT — Canada Scraper")
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
    for tag, count in tag_counter.most_common(10):
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

    # Official site
    if scrape_web:
        logger.info("--- winesoontario.ca ---")
        web_facts = _scrape_official_site(web_source_id)
        logger.info(f"winesoontario.ca facts: {len(web_facts)}")
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

    logger.info("=== TEST RUN: Canada Scraper ===")
    wiki_sid = ensure_wiki_source("Canadian wine")
    wikidata_sid = ensure_wikidata_source("Canadian wine")
    web_sid = ensure_source(
        name="Wines of Ontario",
        url=OFFICIAL_BASE_URL,
        source_type="official_body",
        tier="tier_2_authoritative",
        language="en",
    )

    session = wiki_session()

    test_articles = ["Canadian wine", "Icewine", "Niagara Peninsula wine",
                     "Okanagan wine", "VQA"]
    facts = []
    seen = set()
    for title in test_articles[:TEST_RUN_LIMIT]:
        time.sleep(WIKI_REQUEST_DELAY_OVERRIDE)
        extract, wikitext = fetch_article(session, title)
        if extract:
            atomic = extract_atomic_facts(
                extract, title,
                region_keywords=CANADA_KEYWORDS,
            )
            for item in atomic[:3]:
                text = item["fact_text"]
                if text.lower() not in seen:
                    seen.add(text.lower())
                    facts.append({
                        "fact_text": text,
                        "domain": item["domain"],
                        "subdomain": "canada",
                        "source_id": wiki_sid,
                        "entities": [{"type": "region", "name": title}],
                        "confidence": 0.9,
                        "tags": ["canada", "wikipedia", "test"],
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
    """Canadian wine scraper — genuine external data only."""
    logger.add("data/logs/canada_{time}.log", rotation="10 MB")

    if list_sections:
        click.echo("Canada Scraper — Data Sources:")
        click.echo("  1. Wikipedia: Canadian wine key articles & category crawl")
        click.echo("     - Key articles: Canadian wine, Icewine, Niagara Peninsula wine,")
        click.echo("       Okanagan wine, VQA, British Columbia wine, Nova Scotia wine, etc.")
        click.echo("     - Categories: Wine regions of Canada, Canadian wine")
        click.echo("  2. Wikidata: Canadian wine entities (SPARQL)")
        click.echo("     - Wine regions with P17=Q16 (country=Canada)")
        click.echo("     - Grape varieties with P495=Q16 (origin=Canada)")
        click.echo("     - Wineries with P17=Q16")
        click.echo("     - Appellations with P17=Q16")
        click.echo("  3. winesoontario.ca: Supplementary web scraping")
        return

    if test_run:
        run_test(cleanup=cleanup)
        return

    if not run_all and not dry_run and not validate:
        click.echo("Use --all, --dry-run, --validate, --test-run, or --list")
        return

    # Register sources
    wiki_sid = ensure_wiki_source("Canadian wine")
    wikidata_sid = ensure_wikidata_source("Canadian wine")
    web_sid = ensure_source(
        name="Wines of Ontario",
        url=OFFICIAL_BASE_URL,
        source_type="official_body",
        tier="tier_2_authoritative",
        language="en",
    )

    # Collect facts
    facts = collect_all_facts(wiki_sid, wikidata_sid, web_sid)

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
