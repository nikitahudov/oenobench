"""
OenoBench — Greek Wine Scraper (genuine external data only)

Extracts Greek wine knowledge from:
  1. Wikipedia — key articles on Greek wine regions, grapes, styles
  2. Wikidata SPARQL — Greek wine regions, grape varieties, PDO/PGI appellations

Every fact traces to a URL that was actually fetched and parsed.
No hardcoded wine knowledge.

Note: The EU GIView/eAmbrosia API was found to be broken/unreliable and has
been removed. Focus is on Wikipedia + Wikidata.

Usage:
    python -m src.scrapers.greece --all
    python -m src.scrapers.greece --dry-run
    python -m src.scrapers.greece --validate
    python -m src.scrapers.greece --list
    python -m src.scrapers.greece --test-run
    python -m src.scrapers.greece --test-run --cleanup
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
    SPARQL_APPELLATIONS_BY_COUNTRY,
)

# ─── Configuration ────────────────────────────────────────────────────────────

TEST_RUN_LIMIT = 5

# Greece = Q41 on Wikidata
GREECE_QID = "Q41"

# Region keywords for on-topic filtering
GREECE_KEYWORDS = {
    "greece", "greek", "santorini", "crete", "naoussa", "nemea",
    "macedonia", "peloponnese", "aegean", "ionian", "thessaly", "attica",
    "cyclades", "dodecanese", "epirus", "thrace", "sterea ellada",
    "assyrtiko", "xinomavro", "agiorgitiko", "moschofilero", "roditis",
    "savatiano", "malagousia", "vidiano", "athiri", "robola",
    "mavrodaphne", "limnio", "mandilaria", "kotsifali", "liatiko",
    "retsina", "mavrodafni", "muscat", "samos",
    "pdo", "pgi", "opap", "ope",
}


# ─── Wikipedia Scraping ──────────────────────────────────────────────────────


def _scrape_wikipedia_key_articles(session: requests.Session, source_id: str) -> list[dict]:
    """Scrape key Wikipedia articles about Greek wine using atomic fact pipeline."""
    facts = []
    seen = set()

    key_articles = [
        "Greek wine",
        "Naoussa (wine)",
        "Nemea (wine region)",
        "Santorini (wine)",
        "Samos wine",
        "Retsina",
        "Assyrtiko",
        "Xinomavro",
        "Agiorgitiko",
        "Moschofilero",
        "Mantinia (wine region)",
        "Mavrodaphne",
        "Greek wine regions",
    ]

    for title in key_articles:
        logger.info(f"Fetching Wikipedia article: {title}")
        extract, wikitext = fetch_article(session, title)

        if extract:
            atomic = extract_atomic_facts(
                extract, title,
                region_keywords=GREECE_KEYWORDS,
            )
            for item in atomic:
                text = item["fact_text"]
                if text.lower() not in seen:
                    seen.add(text.lower())
                    facts.append({
                        "fact_text": text,
                        "domain": item["domain"],
                        "subdomain": "greece",
                        "source_id": source_id,
                        "entities": [{"type": "region", "name": title}],
                        "confidence": 0.9,
                        "tags": ["greece", "wikipedia", "key_article"],
                    })

        if wikitext:
            infobox = parse_infobox(wikitext)
            if infobox:
                grape = infobox.get("grapes", "") or infobox.get("grape", "")
                area = infobox.get("area", "") or infobox.get("size", "") or infobox.get("hectares", "")
                classification = infobox.get("classification", "") or infobox.get("appellation", "")
                region = infobox.get("region", "")
                year = infobox.get("year established", "") or infobox.get("established", "")
                colour = infobox.get("color", "") or infobox.get("colour", "")
                species = infobox.get("species", "")
                also_called = infobox.get("also called", "") or infobox.get("synonyms", "")

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
                                    "subdomain": "greece",
                                    "source_id": source_id,
                                    "entities": [
                                        {"type": "region", "name": title},
                                        {"type": "grape", "name": g},
                                    ],
                                    "confidence": 0.9,
                                    "tags": ["greece", "wikipedia", "grape"],
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
                                "subdomain": "greece",
                                "source_id": source_id,
                                "entities": [{"type": "region", "name": title}],
                                "confidence": 0.9,
                                "tags": ["greece", "wikipedia", "area"],
                            })

                if classification and not classification.startswith("Q"):
                    text = f"{title} holds {classification} classification."
                    if text.lower() not in seen:
                        seen.add(text.lower())
                        facts.append({
                            "fact_text": text,
                            "domain": classify_domain(text),
                            "subdomain": "greece",
                            "source_id": source_id,
                            "entities": [{"type": "region", "name": title}],
                            "confidence": 0.9,
                            "tags": ["greece", "wikipedia", "classification"],
                        })

                if region and not region.startswith("Q"):
                    text = f"{title} is located in the {region} wine region."
                    if text.lower() not in seen:
                        seen.add(text.lower())
                        facts.append({
                            "fact_text": text,
                            "domain": "wine_regions",
                            "subdomain": "greece",
                            "source_id": source_id,
                            "entities": [{"type": "region", "name": title}],
                            "confidence": 0.9,
                            "tags": ["greece", "wikipedia", "region"],
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
                                "subdomain": "greece",
                                "source_id": source_id,
                                "entities": [{"type": "region", "name": title}],
                                "confidence": 0.9,
                                "tags": ["greece", "wikipedia", "history"],
                            })

                if colour and len(colour) < 30:
                    text = f"{title} is a {colour} grape variety."
                    if text.lower() not in seen:
                        seen.add(text.lower())
                        facts.append({
                            "fact_text": text,
                            "domain": "grape_varieties",
                            "subdomain": "greece",
                            "source_id": source_id,
                            "entities": [{"type": "grape", "name": title}],
                            "confidence": 0.9,
                            "tags": ["greece", "wikipedia", "grape"],
                        })

                if species and "vinifera" in species.lower():
                    text = f"{title} is a Vitis vinifera grape variety."
                    if text.lower() not in seen:
                        seen.add(text.lower())
                        facts.append({
                            "fact_text": text,
                            "domain": "grape_varieties",
                            "subdomain": "greece",
                            "source_id": source_id,
                            "entities": [{"type": "grape", "name": title}],
                            "confidence": 0.9,
                            "tags": ["greece", "wikipedia", "grape"],
                        })

                if also_called and len(also_called) < 80:
                    text = f"{title} is also known as {also_called}."
                    if text.lower() not in seen:
                        seen.add(text.lower())
                        facts.append({
                            "fact_text": text,
                            "domain": "grape_varieties",
                            "subdomain": "greece",
                            "source_id": source_id,
                            "entities": [{"type": "grape", "name": title}],
                            "confidence": 0.9,
                            "tags": ["greece", "wikipedia", "synonym"],
                        })

    return facts


def _scrape_wikipedia_categories(session: requests.Session, source_id: str) -> list[dict]:
    """Scrape Greek wine articles discovered via Wikipedia category crawling."""
    facts = []
    seen = set()

    categories = [
        "Category:Wine regions of Greece",
        "Category:Greek wine",
        "Category:Greek grape varieties",
    ]

    all_titles = set()
    for cat in categories:
        logger.info(f"Crawling category: {cat}")
        titles = crawl_category(session, cat, max_depth=2, max_articles=100)
        all_titles.update(titles)

    logger.info(f"Found {len(all_titles)} Greek wine-related articles from categories")

    for title in sorted(all_titles):
        logger.info(f"Fetching: {title}")
        extract, wikitext = fetch_article(session, title)

        if extract:
            atomic = extract_atomic_facts(
                extract, title,
                region_keywords=GREECE_KEYWORDS,
            )
            for item in atomic:
                text = item["fact_text"]
                if text.lower() not in seen:
                    seen.add(text.lower())
                    facts.append({
                        "fact_text": text,
                        "domain": item["domain"],
                        "subdomain": "greece",
                        "source_id": source_id,
                        "entities": [{"type": "region", "name": title}],
                        "confidence": 0.9,
                        "tags": ["greece", "wikipedia", "category"],
                    })

        if wikitext:
            infobox = parse_infobox(wikitext)
            if infobox:
                region = infobox.get("region", "")
                grape = infobox.get("grapes", "") or infobox.get("grape", "")
                colour = infobox.get("color", "") or infobox.get("colour", "")
                species = infobox.get("species", "")
                also_called = infobox.get("also called", "") or infobox.get("synonyms", "")

                if region and not region.startswith("Q"):
                    text = f"{title} is a wine appellation in {region}."
                    if text.lower() not in seen:
                        seen.add(text.lower())
                        facts.append({
                            "fact_text": text,
                            "domain": "wine_regions",
                            "subdomain": "greece",
                            "source_id": source_id,
                            "entities": [{"type": "region", "name": title}],
                            "confidence": 0.9,
                            "tags": ["greece", "wikipedia", "appellation"],
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
                                    "subdomain": "greece",
                                    "source_id": source_id,
                                    "entities": [
                                        {"type": "region", "name": title},
                                        {"type": "grape", "name": g},
                                    ],
                                    "confidence": 0.9,
                                    "tags": ["greece", "wikipedia", "grape"],
                                })

                if colour and len(colour) < 30:
                    text = f"{title} is a {colour} grape variety."
                    if text.lower() not in seen:
                        seen.add(text.lower())
                        facts.append({
                            "fact_text": text,
                            "domain": "grape_varieties",
                            "subdomain": "greece",
                            "source_id": source_id,
                            "entities": [{"type": "grape", "name": title}],
                            "confidence": 0.9,
                            "tags": ["greece", "wikipedia", "grape"],
                        })

                if species and "vinifera" in species.lower():
                    text = f"{title} is a Vitis vinifera grape variety."
                    if text.lower() not in seen:
                        seen.add(text.lower())
                        facts.append({
                            "fact_text": text,
                            "domain": "grape_varieties",
                            "subdomain": "greece",
                            "source_id": source_id,
                            "entities": [{"type": "grape", "name": title}],
                            "confidence": 0.9,
                            "tags": ["greece", "wikipedia", "grape"],
                        })

                if also_called and len(also_called) < 80:
                    text = f"{title} is also known as {also_called}."
                    if text.lower() not in seen:
                        seen.add(text.lower())
                        facts.append({
                            "fact_text": text,
                            "domain": "grape_varieties",
                            "subdomain": "greece",
                            "source_id": source_id,
                            "entities": [{"type": "grape", "name": title}],
                            "confidence": 0.9,
                            "tags": ["greece", "wikipedia", "synonym"],
                        })

    return facts


# ─── Wikidata SPARQL ─────────────────────────────────────────────────────────


def _scrape_wikidata(source_id: str) -> list[dict]:
    """Query Wikidata for Greek wine entities using country-scoped SPARQL."""
    facts = []
    seen = set()

    def _add(text, domain="wine_regions", entities=None, tags=None, confidence=0.85):
        if text.lower() in seen:
            return
        seen.add(text.lower())
        facts.append({
            "fact_text": text,
            "domain": domain,
            "subdomain": "greece",
            "source_id": source_id,
            "entities": entities or [],
            "confidence": confidence,
            "tags": tags or ["greece", "wikidata"],
        })

    # Query 1: Wine regions in Greece using country-scoped template
    try:
        query = SPARQL_WINE_REGIONS_BY_COUNTRY.format(country_qid=GREECE_QID)
        rows = run_sparql_filtered(
            query,
            expected_country="Greece",
            region_keywords=GREECE_KEYWORDS,
        )
        for row in rows:
            name = row.get("itemLabel", "")
            region = row.get("regionLabel", "")
            if not name or name.startswith("Q"):
                continue
            if region and not region.startswith("Q"):
                _add(
                    f"{name} is a wine region in {region}, Greece.",
                    entities=[{"type": "region", "name": name}],
                )
            else:
                _add(
                    f"{name} is a wine region in Greece.",
                    entities=[{"type": "region", "name": name}],
                )
    except Exception as e:
        logger.warning(f"Wikidata regions query failed: {e}")

    # Query 2: Greek-origin grape varieties
    try:
        query = SPARQL_GRAPE_VARIETIES_BY_COUNTRY.format(country_qid=GREECE_QID)
        rows = run_sparql_filtered(
            query,
            expected_country="Greece",
            region_keywords=GREECE_KEYWORDS,
        )
        for row in rows:
            name = row.get("itemLabel", "")
            color = row.get("colorLabel", "")
            if not name or name.startswith("Q"):
                continue
            if color and not color.startswith("Q"):
                _add(
                    f"{name} is a {color} grape variety originating from Greece.",
                    domain="grape_varieties",
                    entities=[{"type": "grape", "name": name}],
                    tags=["greece", "wikidata", "grape"],
                )
            else:
                _add(
                    f"{name} is a grape variety originating from Greece.",
                    domain="grape_varieties",
                    entities=[{"type": "grape", "name": name}],
                    tags=["greece", "wikidata", "grape"],
                )
    except Exception as e:
        logger.warning(f"Wikidata grapes query failed: {e}")

    # Query 3: Greek PDO/PGI wine appellations
    try:
        query = SPARQL_APPELLATIONS_BY_COUNTRY.format(country_qid=GREECE_QID)
        rows = run_sparql_filtered(
            query,
            expected_country="Greece",
            region_keywords=GREECE_KEYWORDS,
        )
        for row in rows:
            name = row.get("itemLabel", "")
            region = row.get("regionLabel", "")
            if not name or name.startswith("Q"):
                continue
            if region and not region.startswith("Q"):
                _add(
                    f"{name} is a wine appellation in {region}, Greece.",
                    entities=[{"type": "region", "name": name}],
                    tags=["greece", "wikidata", "appellation"],
                )
            else:
                _add(
                    f"{name} is a wine appellation in Greece.",
                    entities=[{"type": "region", "name": name}],
                    tags=["greece", "wikidata", "appellation"],
                )
    except Exception as e:
        logger.warning(f"Wikidata appellations query failed: {e}")

    return facts


# ─── Validation ───────────────────────────────────────────────────────────────


def validate_facts(facts: list[dict]) -> None:
    """Run quality checks on extracted facts."""
    logger.info(f"\n{'='*60}")
    logger.info(f"VALIDATION REPORT — Greece Scraper")
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
    sample = texts[:200]
    for i, t1 in enumerate(sample):
        for t2 in sample[i + 1:]:
            if t1 in t2 or t2 in t1:
                dupes += 1
    logger.info(f"\nNear-duplicate pairs (substring, sampled): {dupes}")

    # Sample facts
    logger.info(f"\n10 random sample facts:")
    for f in random.sample(facts, min(10, len(facts))):
        logger.info(f"  [{f['domain']}] (conf={f.get('confidence', 1.0)}) {f['fact_text']}")


# ─── Main Collection ──────────────────────────────────────────────────────────


def collect_all_facts(
    wiki_source_id: str,
    wikidata_source_id: str,
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

    logger.info("=== TEST RUN: Greece Scraper ===")
    wiki_sid = ensure_wiki_source("Greek wine")
    wikidata_sid = ensure_wikidata_source("Greek wine")

    session = wiki_session()

    test_articles = ["Greek wine", "Assyrtiko", "Santorini (wine)",
                     "Naoussa (wine)", "Agiorgitiko"]
    facts = []
    seen = set()
    for title in test_articles[:TEST_RUN_LIMIT]:
        extract, wikitext = fetch_article(session, title)
        if extract:
            atomic = extract_atomic_facts(
                extract, title,
                region_keywords=GREECE_KEYWORDS,
            )
            for item in atomic[:3]:
                text = item["fact_text"]
                if text.lower() not in seen:
                    seen.add(text.lower())
                    facts.append({
                        "fact_text": text,
                        "domain": item["domain"],
                        "subdomain": "greece",
                        "source_id": wiki_sid,
                        "entities": [{"type": "region", "name": title}],
                        "confidence": 0.9,
                        "tags": ["greece", "wikipedia", "test"],
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
    """Greek wine scraper — genuine external data only."""

    if list_sections:
        click.echo("Greece Scraper — Data Sources:")
        click.echo("  1. Wikipedia: Key Greek wine articles (13 articles)")
        click.echo("  2. Wikipedia: Category crawl (wine regions, grapes)")
        click.echo("  3. Wikidata: Greek wine regions, grapes, appellations (SPARQL)")
        click.echo("     - Wine regions with P17=Q41 (country=Greece)")
        click.echo("     - Grape varieties with P495=Q41 (origin=Greece)")
        click.echo("     - Appellations with P17=Q41")
        click.echo("  Note: EU GIView API removed (broken/unreliable)")
        return

    if test_run:
        run_test(cleanup=cleanup)
        return

    if not run_all and not dry_run and not validate:
        click.echo("Use --all, --dry-run, --validate, --test-run, or --list")
        return

    # Register sources
    wiki_sid = ensure_wiki_source("Greek wine")
    wikidata_sid = ensure_wikidata_source("Greek wine")

    # Collect facts
    facts = collect_all_facts(wiki_sid, wikidata_sid)

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
