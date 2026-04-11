"""
OenoBench — EU Regulations & OIV Scraper (genuine external data only)

Extracts wine regulatory facts from:
  1. Wikipedia — articles on EU wine regulations, PDO/PGI, OIV
  2. Wikipedia categories — EU wine law, wine classification topics
  3. EUR-Lex — EU wine regulation pages (when accessible)
  4. OIV (oiv.int) — International Organisation of Vine and Wine pages (when accessible)

Every fact traces to a URL that was actually fetched and parsed.
No hardcoded wine knowledge.

Usage:
    python -m src.scrapers.eu_oiv --all
    python -m src.scrapers.eu_oiv --source wikipedia
    python -m src.scrapers.eu_oiv --source eurlex
    python -m src.scrapers.eu_oiv --source oiv
    python -m src.scrapers.eu_oiv --dry-run
    python -m src.scrapers.eu_oiv --validate
    python -m src.scrapers.eu_oiv --list
    python -m src.scrapers.eu_oiv --test-run
    python -m src.scrapers.eu_oiv --test-run --cleanup
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
    extract_lead_sentences,
    extract_atomic_facts,
    ensure_wiki_source,
    is_wine_relevant,
    WIKI_REQUEST_DELAY,
)

# ─── Configuration ────────────────────────────────────────────────────────────

TEST_RUN_LIMIT = 5
EURLEX_BASE_URL = "https://eur-lex.europa.eu"
OIV_BASE_URL = "https://www.oiv.int"
WEB_REQUEST_DELAY = 5.0
REQUEST_TIMEOUT = 30

# Override wiki delay for rate limiting
WIKI_REQUEST_DELAY_OVERRIDE = 5.0

# Topic keywords for on-topic filtering
EU_OIV_KEYWORDS = {
    "eu", "european", "european union", "regulation", "directive",
    "pdo", "pgi", "protected designation", "protected geographical",
    "appellation", "denomination", "classification", "labeling", "labelling",
    "oenological", "wine law", "wine regulation", "wine classification",
    "oiv", "international organisation of vine and wine",
    "chaptalisation", "chaptalization", "enrichment", "acidification",
    "sulphur dioxide", "sulphite", "wine zone", "wine category",
    "sparkling wine", "fortified wine", "traditional term",
    "e-bacchus", "ebacchus", "varietal wine",
    "organic wine", "wine production", "wine trade", "wine market",
    "oenology", "enology", "viticulture", "vinification",
    "wine", "grape", "vineyard", "winery", "appellation",
    "aoc", "aop", "doc", "docg", "dop", "ava", "vqa",
}


# ─── Wikipedia Scraping ──────────────────────────────────────────────────────


def _scrape_wikipedia_key_articles(session: requests.Session, source_id: str) -> list[dict]:
    """Scrape key EU wine regulation and OIV articles from Wikipedia."""
    facts = []
    seen = set()

    key_articles = [
        "European Union wine regulations",
        "Appellation d'origine contrôlée",
        "Protected designation of origin",
        "Geographical indication",
        "International Organisation of Vine and Wine",
        "Wine classification",
        "Oenology",
        "Varietal wine",
        "Sparkling wine",
        "Organic wine",
        "Wine label",
        "Chaptalisation",
        "Sulphite",
        "Indicazione geografica tipica",
        "Denominación de origen",
        "Vin de pays",
        "Qualitätswein bestimmter Anbaugebiete",
        "Traditional term (wine)",
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
                region_keywords=EU_OIV_KEYWORDS,
            )
            for item in atomic:
                text = item["fact_text"]
                if text.lower() not in seen:
                    seen.add(text.lower())
                    facts.append({
                        "fact_text": text,
                        "domain": item["domain"],
                        "subdomain": "eu_regulations",
                        "source_id": source_id,
                        "entities": [{"type": "topic", "name": title}],
                        "confidence": 0.9,
                        "tags": ["eu_oiv", "wikipedia", "key_article"],
                    })

    return facts


def _scrape_wikipedia_categories(session: requests.Session, source_id: str) -> list[dict]:
    """Scrape EU wine regulation articles via Wikipedia category crawl."""
    facts = []
    seen = set()

    categories = [
        "Category:Wine classification",
        "Category:Appellations",
        "Category:Wine law",
    ]

    all_titles = set()
    for cat in categories:
        logger.info(f"Crawling category: {cat}")
        titles = crawl_category(session, cat, max_depth=2, max_articles=80)
        all_titles.update(titles)

    logger.info(f"Found {len(all_titles)} wine regulation articles from categories")

    for title in sorted(all_titles):
        logger.info(f"Fetching: {title}")
        time.sleep(WIKI_REQUEST_DELAY_OVERRIDE)
        extract, wikitext = fetch_article(session, title)

        if extract:
            atomic = extract_atomic_facts(
                extract, title,
                region_keywords=EU_OIV_KEYWORDS,
            )
            for item in atomic:
                text = item["fact_text"]
                if text.lower() not in seen:
                    seen.add(text.lower())
                    facts.append({
                        "fact_text": text,
                        "domain": item["domain"],
                        "subdomain": "eu_regulations",
                        "source_id": source_id,
                        "entities": [{"type": "topic", "name": title}],
                        "confidence": 0.9,
                        "tags": ["eu_oiv", "wikipedia", "category"],
                    })

    return facts


# ─── EUR-Lex Scraping ────────────────────────────────────────────────────────


def _scrape_eurlex(source_id: str) -> list[dict]:
    """Scrape EU wine regulation pages from EUR-Lex."""
    facts = []
    seen = set()

    # Key regulation URLs
    eurlex_pages = [
        {
            "url": "https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32013R1308",
            "subject": "EU Regulation 1308/2013 on common market organisation",
        },
        {
            "url": "https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32019R0033",
            "subject": "EU Regulation 2019/33 on wine labeling",
        },
        {
            "url": "https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32019R0934",
            "subject": "EU Regulation 2019/934 on oenological practices",
        },
        {
            "url": "https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32009R0607",
            "subject": "EU Regulation 607/2009 on PDO/PGI wine names",
        },
    ]

    session_obj, delay = create_session(EURLEX_BASE_URL, delay=WEB_REQUEST_DELAY)

    for page_info in eurlex_pages:
        url = page_info["url"]
        subject = page_info["subject"]
        logger.info(f"Fetching EUR-Lex page: {url}")

        soup = web_fetch_page(session_obj, url, delay=WEB_REQUEST_DELAY, timeout=REQUEST_TIMEOUT)
        if not soup:
            logger.warning(f"Failed to fetch EUR-Lex page: {url}")
            continue

        blocks = web_extract_text_blocks(soup, min_words=8, max_words=60)
        if not blocks:
            logger.warning(f"No text blocks from EUR-Lex page: {url}")
            continue

        logger.info(f"Extracted {len(blocks)} text blocks from {url}")

        processed = process_facts(
            raw_texts=blocks,
            subject=subject,
            region_keywords=EU_OIV_KEYWORDS,
        )

        for item in processed:
            text = item["fact_text"]
            if text.lower() not in seen:
                seen.add(text.lower())
                facts.append({
                    "fact_text": text,
                    "domain": item["domain"],
                    "subdomain": "eu_regulations",
                    "source_id": source_id,
                    "entities": [],
                    "confidence": 0.85,
                    "tags": ["eu_oiv", "eurlex", "regulation"],
                })

    logger.info(f"EUR-Lex scraping yielded {len(facts)} facts")
    return facts


# ─── OIV Scraping ────────────────────────────────────────────────────────────


def _scrape_oiv(source_id: str) -> list[dict]:
    """Scrape pages from oiv.int using shared web helpers."""
    facts = []
    seen = set()

    seed_paths = [
        "/what-we-do/global-report",
        "/standards/international-code-of-oenological-practices",
        "/what-we-do/variety-distribution",
        "/what-we-do",
        "/",
    ]

    try:
        page_results = scrape_site_texts(
            base_url=OIV_BASE_URL,
            seed_paths=seed_paths,
            max_pages=20,
            delay=WEB_REQUEST_DELAY,
            min_words=8,
            max_words=60,
        )

        all_texts = []
        for url, blocks in page_results:
            all_texts.extend(blocks)

        if not all_texts:
            logger.warning("oiv.int returned no text blocks (may be blocked or JS-rendered)")
            return facts

        processed = process_facts(
            raw_texts=all_texts,
            subject="OIV international wine standards",
            region_keywords=EU_OIV_KEYWORDS,
        )

        for item in processed:
            text = item["fact_text"]
            if text.lower() not in seen:
                seen.add(text.lower())
                facts.append({
                    "fact_text": text,
                    "domain": item["domain"],
                    "subdomain": "oiv_standards",
                    "source_id": source_id,
                    "entities": [],
                    "confidence": 0.8,
                    "tags": ["eu_oiv", "oiv", "scraped"],
                })

    except Exception as e:
        logger.warning(f"Failed to scrape oiv.int: {e}")

    logger.info(f"oiv.int scraping yielded {len(facts)} facts")
    return facts


# ─── Validation ───────────────────────────────────────────────────────────────


def validate_facts(facts: list[dict]) -> None:
    """Run quality checks on extracted facts."""
    click.echo(f"\n{'='*60}")
    click.echo(f"VALIDATION REPORT — EU/OIV Scraper")
    click.echo(f"{'='*60}")
    click.echo(f"Total facts: {len(facts)}")

    # Domain breakdown
    domains = Counter(f["domain"] for f in facts)
    click.echo(f"\nDomain breakdown:")
    for domain, count in domains.most_common():
        click.echo(f"  {domain}: {count}")

    # Subdomain breakdown
    subdomains = Counter(f.get("subdomain", "none") for f in facts)
    click.echo(f"\nSubdomain breakdown:")
    for sd, count in subdomains.most_common():
        click.echo(f"  {sd}: {count}")

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
    eurlex_source_id: str,
    oiv_source_id: str,
    sources_to_run: Optional[str] = None,
) -> list[dict]:
    """Collect all facts from all sources."""
    session = wiki_session()
    all_facts = []

    run_wiki = sources_to_run is None or sources_to_run == "wikipedia"
    run_eurlex = sources_to_run is None or sources_to_run == "eurlex"
    run_oiv = sources_to_run is None or sources_to_run == "oiv"

    if run_wiki:
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

    if run_eurlex:
        # EUR-Lex
        logger.info("--- EUR-Lex ---")
        eurlex_facts = _scrape_eurlex(eurlex_source_id)
        logger.info(f"EUR-Lex facts: {len(eurlex_facts)}")
        all_facts.extend(eurlex_facts)

    if run_oiv:
        # OIV
        logger.info("--- OIV (oiv.int) ---")
        oiv_facts = _scrape_oiv(oiv_source_id)
        logger.info(f"OIV facts: {len(oiv_facts)}")
        all_facts.extend(oiv_facts)

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

    logger.info("=== TEST RUN: EU/OIV Scraper ===")
    wiki_sid = ensure_wiki_source("EU wine regulations")
    eurlex_sid = ensure_source(
        name="EUR-Lex EU Wine Legislation",
        url="https://eur-lex.europa.eu",
        source_type="government",
        tier="tier_1_official",
        language="en",
    )
    oiv_sid = ensure_source(
        name="OIV — International Organisation of Vine and Wine",
        url="https://www.oiv.int",
        source_type="international_organisation",
        tier="tier_1_official",
        language="en",
    )

    session = wiki_session()

    test_articles = [
        "European Union wine regulations",
        "Protected designation of origin",
        "International Organisation of Vine and Wine",
    ]
    facts = []
    seen = set()
    for title in test_articles:
        time.sleep(WIKI_REQUEST_DELAY_OVERRIDE)
        extract, wikitext = fetch_article(session, title)
        if extract:
            atomic = extract_atomic_facts(
                extract, title,
                region_keywords=EU_OIV_KEYWORDS,
            )
            for item in atomic[:5]:
                text = item["fact_text"]
                if text.lower() not in seen:
                    seen.add(text.lower())
                    facts.append({
                        "fact_text": text,
                        "domain": item["domain"],
                        "subdomain": "eu_regulations",
                        "source_id": wiki_sid,
                        "entities": [{"type": "topic", "name": title}],
                        "confidence": 0.9,
                        "tags": ["eu_oiv", "wikipedia", "test"],
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
@click.option("--source", "source_filter", type=click.Choice(["wikipedia", "eurlex", "oiv"]),
              help="Run only a specific source")
@click.option("--list", "list_sections", is_flag=True, help="List available data sources")
@click.option("--dry-run", "dry_run", is_flag=True, help="Collect facts but don't insert into database")
@click.option("--validate", "validate", is_flag=True, help="Run quality checks on generated facts")
@click.option("--test-run", is_flag=True, help="Process a small sample, insert, and report")
@click.option("--cleanup", is_flag=True, help="With --test-run, delete inserted facts after reporting")
def main(run_all, source_filter, list_sections, dry_run, validate, test_run, cleanup):
    """EU wine regulations & OIV scraper — genuine external data only."""
    logger.add("data/logs/eu_oiv_{time}.log", rotation="10 MB")

    if list_sections:
        click.echo("EU/OIV Scraper — Data Sources:")
        click.echo("  1. Wikipedia: EU wine regulation & OIV key articles")
        click.echo("     - European Union wine regulations, PDO, PGI,")
        click.echo("       Appellation d'origine controlee, OIV, Wine classification, etc.")
        click.echo("     - Categories: Wine classification, Appellations, Wine law")
        click.echo("  2. EUR-Lex: EU wine legislation pages")
        click.echo("     - Regulation 1308/2013 (common market organisation)")
        click.echo("     - Regulation 2019/33 (wine labeling)")
        click.echo("     - Regulation 2019/934 (oenological practices)")
        click.echo("     - Regulation 607/2009 (PDO/PGI wine names)")
        click.echo("  3. OIV (oiv.int): International wine standards")
        click.echo("     - Global reports, oenological practices, variety distribution")
        return

    if test_run:
        run_test(cleanup=cleanup)
        return

    if not run_all and not dry_run and not validate and not source_filter:
        click.echo("Use --all, --dry-run, --validate, --test-run, or --list")
        click.echo("Use --source <wikipedia|eurlex|oiv> to run a specific source")
        return

    # Register sources
    wiki_sid = ensure_wiki_source("EU wine regulations")
    eurlex_sid = ensure_source(
        name="EUR-Lex EU Wine Legislation",
        url="https://eur-lex.europa.eu",
        source_type="government",
        tier="tier_1_official",
        language="en",
    )
    oiv_sid = ensure_source(
        name="OIV — International Organisation of Vine and Wine",
        url="https://www.oiv.int",
        source_type="international_organisation",
        tier="tier_1_official",
        language="en",
    )

    # Collect facts
    facts = collect_all_facts(wiki_sid, eurlex_sid, oiv_sid, sources_to_run=source_filter)

    if validate or dry_run:
        validate_facts(facts)

    if dry_run:
        click.echo(f"\nDRY RUN — {len(facts)} facts generated, not inserted")
        return

    if run_all or source_filter:
        before = get_fact_count()
        inserted = insert_facts_batch(facts)
        after = get_fact_count()
        click.echo(f"Inserted {inserted} new facts (DB: {before} -> {after})")


if __name__ == "__main__":
    main()
