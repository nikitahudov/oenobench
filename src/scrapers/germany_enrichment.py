"""
OenoBench — German Wine Enrichment Scraper (genuine external data only)

Extracts German wine knowledge from:
  1. Wikipedia — key articles on German wine, regions, grape varieties, classification
  2. Wikipedia categories — "Wine regions of Germany", "German wine"
  3. Wikidata SPARQL — wine regions with P17=Q183 (Germany), grape varieties, wineries
  4. deutscheweine.de — supplementary scraping when accessible

Every fact traces to a URL that was actually fetched and parsed.
No hardcoded wine knowledge.

Usage:
    python -m src.scrapers.germany_enrichment --all
    python -m src.scrapers.germany_enrichment --dry-run
    python -m src.scrapers.germany_enrichment --validate
    python -m src.scrapers.germany_enrichment --list
    python -m src.scrapers.germany_enrichment --test-run
    python -m src.scrapers.germany_enrichment --test-run --cleanup
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
DEUTSCHEWEINE_BASE_URL = "https://www.deutscheweine.de"
DEUTSCHEWEINE_REQUEST_DELAY = 5
REQUEST_TIMEOUT = 30

# Override wiki delay for rate limiting
WIKI_REQUEST_DELAY_OVERRIDE = 5.0

# Germany = Q183 on Wikidata
GERMANY_QID = "Q183"

# Region keywords for on-topic filtering
GERMANY_KEYWORDS = {
    "germany", "german", "mosel", "rheingau", "pfalz", "baden", "franken",
    "nahe", "rheinhessen", "württemberg", "ahr", "sachsen", "saale-unstrut",
    "mittelrhein", "hessische bergstraße", "anbaugebiet", "anbaugebiete",
    "riesling", "spätburgunder", "silvaner", "müller-thurgau", "dornfelder",
    "grauburgunder", "weißburgunder", "trollinger", "lemberger",
    "prädikatswein", "praedikat", "qualitätswein", "kabinett", "spätlese",
    "auslese", "beerenauslese", "trockenbeerenauslese", "eiswein",
    "vdp", "grosse lage", "grosses gewächs", "erste lage",
    "landwein", "deutscher wein", "oechsle",
    "trocken", "halbtrocken", "feinherb", "sekt",
}


# ─── Wikipedia Scraping ──────────────────────────────────────────────────────


def _scrape_wikipedia_key_articles(session: requests.Session, source_id: str) -> list[dict]:
    """Scrape key German wine articles from Wikipedia using atomic fact pipeline."""
    facts = []
    seen = set()

    key_articles = [
        "German wine",
        "German wine classification",
        "Mosel wine region",
        "Rheingau",
        "Pfalz (wine region)",
        "Riesling",
        "Spätburgunder",
        "Silvaner",
        "Prädikatswein",
        "VDP (wine)",
        "Baden (wine region)",
        "Franken (wine region)",
        "Nahe (wine region)",
        "Rheinhessen",
        "Württemberg (wine region)",
        "Ahr (wine region)",
        "Sachsen (wine region)",
        "Saale-Unstrut",
        "Mittelrhein (wine region)",
        "Müller-Thurgau",
        "Dornfelder",
        "Grauburgunder",
    ]

    for title in key_articles:
        logger.info(f"Fetching Wikipedia article: {title}")
        time.sleep(WIKI_REQUEST_DELAY_OVERRIDE)
        extract, wikitext = fetch_article(session, title)

        if extract:
            # Full extract for richer content
            full_ext = fetch_full_extract(session, title)
            text_to_process = full_ext if full_ext else extract

            atomic = extract_atomic_facts(
                text_to_process, title,
                region_keywords=GERMANY_KEYWORDS,
            )
            for item in atomic:
                text = item["fact_text"]
                if text.lower() not in seen:
                    seen.add(text.lower())
                    facts.append({
                        "fact_text": text,
                        "domain": item["domain"],
                        "subdomain": "germany",
                        "source_id": source_id,
                        "entities": [{"type": "region", "name": title}],
                        "confidence": 0.9,
                        "tags": ["germany", "wikipedia", "key_article"],
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
                                    "subdomain": "germany",
                                    "source_id": source_id,
                                    "entities": [
                                        {"type": "region", "name": title},
                                        {"type": "grape", "name": g},
                                    ],
                                    "confidence": 0.9,
                                    "tags": ["germany", "wikipedia", "grape"],
                                })

                if area and re.search(r"\d", area):
                    text = f"{title} covers approximately {area} hectares."
                    if text.lower() not in seen:
                        seen.add(text.lower())
                        facts.append({
                            "fact_text": text,
                            "domain": classify_domain(text),
                            "subdomain": "germany",
                            "source_id": source_id,
                            "entities": [{"type": "region", "name": title}],
                            "confidence": 0.9,
                            "tags": ["germany", "wikipedia", "area"],
                        })

                if classification:
                    text = f"{title} holds {classification} classification."
                    if text.lower() not in seen:
                        seen.add(text.lower())
                        facts.append({
                            "fact_text": text,
                            "domain": classify_domain(text),
                            "subdomain": "germany",
                            "source_id": source_id,
                            "entities": [{"type": "region", "name": title}],
                            "confidence": 0.9,
                            "tags": ["germany", "wikipedia", "classification"],
                        })

                if region and not region.startswith("Q"):
                    text = f"{title} is a wine region in {region}."
                    if text.lower() not in seen:
                        seen.add(text.lower())
                        facts.append({
                            "fact_text": text,
                            "domain": "wine_regions",
                            "subdomain": "germany",
                            "source_id": source_id,
                            "entities": [{"type": "region", "name": title}],
                            "confidence": 0.9,
                            "tags": ["germany", "wikipedia", "region"],
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
                                "subdomain": "germany",
                                "source_id": source_id,
                                "entities": [{"type": "region", "name": title}],
                                "confidence": 0.9,
                                "tags": ["germany", "wikipedia", "history"],
                            })

    return facts


def _scrape_wikipedia_categories(session: requests.Session, source_id: str) -> list[dict]:
    """Scrape German wine articles discovered via Wikipedia category crawl."""
    facts = []
    seen = set()

    categories = [
        "Category:Wine regions of Germany",
        "Category:German wine",
    ]

    all_titles = set()
    for cat in categories:
        logger.info(f"Crawling category: {cat}")
        titles = crawl_category(session, cat, max_depth=2, max_articles=150)
        all_titles.update(titles)

    logger.info(f"Found {len(all_titles)} German wine-related articles from categories")

    for title in sorted(all_titles):
        logger.info(f"Fetching: {title}")
        time.sleep(WIKI_REQUEST_DELAY_OVERRIDE)
        extract, wikitext = fetch_article(session, title)

        if extract:
            atomic = extract_atomic_facts(
                extract, title,
                region_keywords=GERMANY_KEYWORDS,
            )
            for item in atomic:
                text = item["fact_text"]
                if text.lower() not in seen:
                    seen.add(text.lower())
                    facts.append({
                        "fact_text": text,
                        "domain": item["domain"],
                        "subdomain": "germany",
                        "source_id": source_id,
                        "entities": [{"type": "region", "name": title}],
                        "confidence": 0.9,
                        "tags": ["germany", "wikipedia", "category"],
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
                            "subdomain": "germany",
                            "source_id": source_id,
                            "entities": [{"type": "region", "name": title}],
                            "confidence": 0.9,
                            "tags": ["germany", "wikipedia", "region"],
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
                                    "subdomain": "germany",
                                    "source_id": source_id,
                                    "entities": [
                                        {"type": "region", "name": title},
                                        {"type": "grape", "name": g},
                                    ],
                                    "confidence": 0.9,
                                    "tags": ["germany", "wikipedia", "grape"],
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
                                "subdomain": "germany",
                                "source_id": source_id,
                                "entities": [{"type": "region", "name": title}],
                                "confidence": 0.9,
                                "tags": ["germany", "wikipedia", "area"],
                            })

                if classification:
                    text = f"{title} holds {classification} classification."
                    if text.lower() not in seen:
                        seen.add(text.lower())
                        facts.append({
                            "fact_text": text,
                            "domain": classify_domain(text),
                            "subdomain": "germany",
                            "source_id": source_id,
                            "entities": [{"type": "region", "name": title}],
                            "confidence": 0.9,
                            "tags": ["germany", "wikipedia", "classification"],
                        })

    return facts


# ─── Wikidata SPARQL ─────────────────────────────────────────────────────────


def _scrape_wikidata(source_id: str) -> list[dict]:
    """Query Wikidata for German wine entities using country-scoped SPARQL."""
    facts = []
    seen = set()

    def _add(text, domain="wine_regions", entities=None, tags=None, confidence=0.85):
        if text.lower() in seen:
            return
        seen.add(text.lower())
        facts.append({
            "fact_text": text,
            "domain": domain,
            "subdomain": "germany",
            "source_id": source_id,
            "entities": entities or [],
            "confidence": confidence,
            "tags": tags or ["germany", "wikidata"],
        })

    # Query 1: Wine regions in Germany
    try:
        query = SPARQL_WINE_REGIONS_BY_COUNTRY.format(country_qid=GERMANY_QID)
        rows = run_sparql_filtered(
            query,
            expected_country="Germany",
            region_keywords=GERMANY_KEYWORDS,
        )
        for row in rows:
            name = row.get("itemLabel", "")
            region = row.get("regionLabel", "")
            area = row.get("areaHa", "")
            if not name or name.startswith("Q"):
                continue
            if region and not region.startswith("Q"):
                _add(
                    f"{name} is a wine region in {region}, Germany.",
                    entities=[{"type": "region", "name": name}],
                )
            else:
                _add(
                    f"{name} is a wine region in Germany.",
                    entities=[{"type": "region", "name": name}],
                )
            if area and re.search(r"\d", str(area)):
                _add(
                    f"{name} covers approximately {area} hectares.",
                    entities=[{"type": "region", "name": name}],
                    tags=["germany", "wikidata", "area"],
                )
    except Exception as e:
        logger.warning(f"Wikidata regions query failed: {e}")

    # Query 2: German grape varieties
    try:
        query = SPARQL_GRAPE_VARIETIES_BY_COUNTRY.format(country_qid=GERMANY_QID)
        rows = run_sparql_filtered(
            query,
            expected_country="Germany",
            region_keywords=GERMANY_KEYWORDS,
        )
        for row in rows:
            name = row.get("itemLabel", "")
            color = row.get("colorLabel", "")
            if not name or name.startswith("Q"):
                continue
            if color and not color.startswith("Q"):
                _add(
                    f"{name} is a German {color} grape variety.",
                    domain="grape_varieties",
                    entities=[{"type": "grape", "name": name}],
                    tags=["germany", "wikidata", "grape"],
                )
            else:
                _add(
                    f"{name} is a German grape variety.",
                    domain="grape_varieties",
                    entities=[{"type": "grape", "name": name}],
                    tags=["germany", "wikidata", "grape"],
                )
    except Exception as e:
        logger.warning(f"Wikidata grapes query failed: {e}")

    # Query 3: German wineries
    try:
        query = SPARQL_WINERIES_BY_COUNTRY.format(country_qid=GERMANY_QID)
        rows = run_sparql_filtered(
            query,
            expected_country="Germany",
            region_keywords=GERMANY_KEYWORDS,
        )
        for row in rows:
            name = row.get("itemLabel", "")
            location = row.get("regionLabel", "")
            founded = row.get("founded", "")
            if not name or name.startswith("Q"):
                continue
            if location and not location.startswith("Q"):
                _add(
                    f"{name} is a wine producer in {location}, Germany.",
                    domain="producers",
                    entities=[
                        {"type": "producer", "name": name},
                        {"type": "region", "name": location},
                    ],
                    tags=["germany", "wikidata", "producer"],
                )
            else:
                _add(
                    f"{name} is a wine producer in Germany.",
                    domain="producers",
                    entities=[{"type": "producer", "name": name}],
                    tags=["germany", "wikidata", "producer"],
                )
            if founded:
                year_match = re.search(r"\d{4}", str(founded))
                if year_match:
                    _add(
                        f"{name} was founded in {year_match.group()}.",
                        domain="producers",
                        entities=[{"type": "producer", "name": name}],
                        tags=["germany", "wikidata", "producer", "history"],
                    )
    except Exception as e:
        logger.warning(f"Wikidata producers query failed: {e}")

    # Query 4: German appellations
    try:
        query = SPARQL_APPELLATIONS_BY_COUNTRY.format(country_qid=GERMANY_QID)
        rows = run_sparql_filtered(
            query,
            expected_country="Germany",
            region_keywords=GERMANY_KEYWORDS,
        )
        for row in rows:
            name = row.get("itemLabel", "")
            region = row.get("regionLabel", "")
            if not name or name.startswith("Q"):
                continue
            if region and not region.startswith("Q"):
                _add(
                    f"{name} is a German wine appellation in {region}.",
                    domain="wine_regions",
                    entities=[{"type": "appellation", "name": name}],
                    tags=["germany", "wikidata", "appellation"],
                )
            else:
                _add(
                    f"{name} is a German wine appellation.",
                    domain="wine_regions",
                    entities=[{"type": "appellation", "name": name}],
                    tags=["germany", "wikidata", "appellation"],
                )
    except Exception as e:
        logger.warning(f"Wikidata appellations query failed: {e}")

    return facts


# ─── deutscheweine.de Scraping ───────────────────────────────────────────────


def _scrape_deutscheweine(source_id: str) -> list[dict]:
    """Scrape supplementary facts from deutscheweine.de using shared web helpers."""
    facts = []
    seen = set()

    seed_paths = [
        "/en/regions/",
        "/en/grapes/",
        "/en/quality-levels/",
        "/en/",
    ]

    try:
        page_results = scrape_site_texts(
            base_url=DEUTSCHEWEINE_BASE_URL,
            seed_paths=seed_paths,
            max_pages=30,
            delay=DEUTSCHEWEINE_REQUEST_DELAY,
            min_words=8,
            max_words=60,
        )

        all_texts = []
        for url, blocks in page_results:
            all_texts.extend(blocks)

        if not all_texts:
            logger.warning("deutscheweine.de returned no text blocks (may be blocked or different URL structure)")
            return facts

        processed = process_facts(
            raw_texts=all_texts,
            subject="German wine",
            region_keywords=GERMANY_KEYWORDS,
        )

        for item in processed:
            text = item["fact_text"]
            if text.lower() not in seen:
                seen.add(text.lower())
                facts.append({
                    "fact_text": text,
                    "domain": item["domain"],
                    "subdomain": "germany",
                    "source_id": source_id,
                    "entities": [],
                    "confidence": 0.8,
                    "tags": ["germany", "deutscheweine", "scraped"],
                })

    except Exception as e:
        logger.warning(f"Failed to scrape deutscheweine.de: {e}")

    logger.info(f"deutscheweine.de scraping yielded {len(facts)} facts")
    return facts


# ─── Validation ───────────────────────────────────────────────────────────────


def validate_facts(facts: list[dict]) -> None:
    """Run quality checks on extracted facts."""
    click.echo(f"\n{'='*60}")
    click.echo(f"VALIDATION REPORT — Germany Enrichment Scraper")
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

    # deutscheweine.de
    if scrape_web:
        logger.info("--- deutscheweine.de ---")
        web_facts = _scrape_deutscheweine(web_source_id)
        logger.info(f"deutscheweine.de facts: {len(web_facts)}")
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

    logger.info("=== TEST RUN: Germany Enrichment Scraper ===")
    wiki_sid = ensure_wiki_source("German wine")
    wikidata_sid = ensure_wikidata_source("German wine")
    web_sid = ensure_source(
        name="Deutsche Weine (German Wines)",
        url="https://www.deutscheweine.de",
        source_type="official_body",
        tier="tier_2_authoritative",
        language="en",
    )

    session = wiki_session()

    test_articles = ["German wine", "Riesling", "Mosel wine region",
                     "Rheingau", "Spätburgunder"]
    facts = []
    seen = set()
    for title in test_articles[:TEST_RUN_LIMIT]:
        time.sleep(WIKI_REQUEST_DELAY_OVERRIDE)
        extract, wikitext = fetch_article(session, title)
        if extract:
            atomic = extract_atomic_facts(
                extract, title,
                region_keywords=GERMANY_KEYWORDS,
            )
            for item in atomic[:3]:
                text = item["fact_text"]
                if text.lower() not in seen:
                    seen.add(text.lower())
                    facts.append({
                        "fact_text": text,
                        "domain": item["domain"],
                        "subdomain": "germany",
                        "source_id": wiki_sid,
                        "entities": [{"type": "region", "name": title}],
                        "confidence": 0.9,
                        "tags": ["germany", "wikipedia", "test"],
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
    """German wine enrichment scraper — genuine external data only."""
    logger.add("data/logs/germany_enrichment_{time}.log", rotation="10 MB")

    if list_sections:
        click.echo("Germany Enrichment Scraper — Data Sources:")
        click.echo("  1. Wikipedia: German wine key articles & category crawl")
        click.echo("     - Key articles: German wine, German wine classification, Riesling,")
        click.echo("       Mosel, Rheingau, Pfalz, Baden, Franken, Nahe, etc.")
        click.echo("     - Categories: Wine regions of Germany, German wine")
        click.echo("  2. Wikidata: German wine entities (SPARQL)")
        click.echo("     - Wine regions with P17=Q183 (country=Germany)")
        click.echo("     - Grape varieties with P495=Q183 (origin=Germany)")
        click.echo("     - Wineries with P17=Q183")
        click.echo("     - Appellations with P17=Q183")
        click.echo("  3. deutscheweine.de: Supplementary web scraping")
        return

    if test_run:
        run_test(cleanup=cleanup)
        return

    if not run_all and not dry_run and not validate:
        click.echo("Use --all, --dry-run, --validate, --test-run, or --list")
        return

    # Register sources
    wiki_sid = ensure_wiki_source("German wine")
    wikidata_sid = ensure_wikidata_source("German wine")
    web_sid = ensure_source(
        name="Deutsche Weine (German Wines)",
        url="https://www.deutscheweine.de",
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
