"""
OenoBench — Austrian Wine Scraper (genuine external data only)

Extracts Austrian wine knowledge from:
  1. Wikipedia — key articles on Austrian wine, grape varieties, regions
  2. Wikidata SPARQL — wine regions with P17=Q40 (Austria), grape varieties
  3. austrianwine.com — supplementary scraping when accessible

Every fact traces to a URL that was actually fetched and parsed.
No hardcoded wine knowledge.

Usage:
    python -m src.scrapers.austria --all
    python -m src.scrapers.austria --dry-run
    python -m src.scrapers.austria --validate
    python -m src.scrapers.austria --list
    python -m src.scrapers.austria --test-run
    python -m src.scrapers.austria --test-run --cleanup
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
AUSTRIANWINE_BASE_URL = "https://www.austrianwine.com"
AUSTRIANWINE_REQUEST_DELAY = 5
REQUEST_TIMEOUT = 30
AUSTRIANWINE_HEADERS = {
    "User-Agent": "OenoBench-Research/1.0 (academic wine benchmark)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


# ─── Wikipedia Scraping ──────────────────────────────────────────────────────


def _scrape_wikipedia_key_articles(session: requests.Session, source_id: str) -> list[dict]:
    """Scrape key Austrian wine articles from Wikipedia."""
    facts = []
    seen = set()

    def _add(text, domain="wine_regions", subdomain="austria", entities=None,
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
            "tags": tags or ["austria", "wikipedia"],
        })

    key_articles = [
        "Austrian wine",
        "Grüner Veltliner",
        "Zweigelt",
        "Blaufränkisch",
        "Wachau (wine region)",
        "Kamptal (wine region)",
        "Kremstal (wine region)",
        "Burgenland (wine region)",
        "Steiermark (wine region)",
        "Weinviertel",
        "Wien (wine)",
    ]

    for title in key_articles:
        logger.info(f"Fetching Wikipedia article: {title}")
        extract, wikitext = fetch_article(session, title)

        if extract:
            sentences = extract_lead_sentences(extract)
            for s in sentences[:10]:
                _add(s, entities=[{"type": "region", "name": title}],
                     tags=["austria", "wikipedia", "key_article"])

        if wikitext:
            # Parse tables for classification data (DAC, Prädikat, etc.)
            rows = parse_wikitext_tables(wikitext)
            for row in rows:
                if len(row) >= 2:
                    name = row[0].strip()
                    detail = row[1].strip() if len(row) > 1 else ""

                    # Skip headers and non-data rows
                    if not name or name.lower() in ("name", "region", "area",
                                                      "variety", "grape", "wine"):
                        continue
                    if len(name) < 3 or len(name) > 80:
                        continue

                    if detail and len(detail) < 60 and not detail.startswith(("–", "—", "-")):
                        _add(
                            f"{name}: {detail}.",
                            entities=[{"type": "region", "name": name}],
                            tags=["austria", "wikipedia", "table"],
                        )

            # Parse infobox data
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
                            _add(
                                f"{title} permits the {g} grape variety.",
                                domain="grape_varieties",
                                entities=[
                                    {"type": "region", "name": title},
                                    {"type": "grape", "name": g},
                                ],
                                tags=["austria", "wikipedia", "grape"],
                            )

                if area and re.search(r"\d", area):
                    _add(
                        f"{title} covers approximately {area} hectares.",
                        entities=[{"type": "region", "name": title}],
                        tags=["austria", "wikipedia", "area"],
                    )

                if classification:
                    _add(
                        f"{title} holds {classification} classification.",
                        entities=[{"type": "region", "name": title}],
                        tags=["austria", "wikipedia", "classification"],
                    )

                if region and not region.startswith("Q"):
                    _add(
                        f"{title} is a wine region in {region}.",
                        entities=[{"type": "region", "name": title}],
                        tags=["austria", "wikipedia", "region"],
                    )

                if year and re.search(r"\d{4}", year):
                    year_match = re.search(r"\d{4}", year)
                    if year_match:
                        _add(
                            f"{title} was established in {year_match.group()}.",
                            entities=[{"type": "region", "name": title}],
                            tags=["austria", "wikipedia", "history"],
                        )

    return facts


def _scrape_wikipedia_categories(session: requests.Session, source_id: str) -> list[dict]:
    """Scrape Austrian wine articles discovered via Wikipedia category crawl."""
    facts = []
    seen = set()

    def _add(text, domain="wine_regions", subdomain="austria", entities=None,
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
            "tags": tags or ["austria", "wikipedia"],
        })

    categories = [
        "Category:Wine regions of Austria",
        "Category:Austrian wine",
    ]

    all_titles = set()
    for cat in categories:
        logger.info(f"Crawling category: {cat}")
        titles = crawl_category(session, cat, max_depth=2, max_articles=100)
        all_titles.update(titles)

    logger.info(f"Found {len(all_titles)} Austrian wine-related articles from categories")

    for title in sorted(all_titles):
        logger.info(f"Fetching: {title}")
        extract, wikitext = fetch_article(session, title)

        if extract:
            sentences = extract_lead_sentences(extract)
            for s in sentences[:6]:
                _add(s, entities=[{"type": "region", "name": title}],
                     tags=["austria", "wikipedia", "category"])

        if wikitext:
            infobox = parse_infobox(wikitext)
            if infobox:
                region = infobox.get("region", "")
                grape = infobox.get("grapes", "") or infobox.get("grape", "")
                area = infobox.get("area", "") or infobox.get("size", "") or infobox.get("hectares", "")
                classification = infobox.get("classification", "") or infobox.get("appellation", "") or infobox.get("designation", "")
                year = infobox.get("year established", "") or infobox.get("established", "")

                if region and not region.startswith("Q"):
                    _add(
                        f"{title} is a wine region in {region}.",
                        entities=[{"type": "region", "name": title}],
                        tags=["austria", "wikipedia", "region"],
                    )

                if grape:
                    grapes = [g.strip() for g in re.split(r"[,;]", grape) if g.strip()]
                    for g in grapes[:5]:
                        if 2 < len(g) < 50:
                            _add(
                                f"{title} permits the {g} grape variety.",
                                domain="grape_varieties",
                                entities=[
                                    {"type": "region", "name": title},
                                    {"type": "grape", "name": g},
                                ],
                                tags=["austria", "wikipedia", "grape"],
                            )

                if area and re.search(r"\d", area):
                    area_clean = re.sub(r"[^\d.,]", " ", area).strip()
                    if area_clean:
                        _add(
                            f"{title} covers approximately {area_clean} hectares.",
                            entities=[{"type": "region", "name": title}],
                            tags=["austria", "wikipedia", "area"],
                        )

                if classification:
                    _add(
                        f"{title} holds {classification} classification.",
                        entities=[{"type": "region", "name": title}],
                        tags=["austria", "wikipedia", "classification"],
                    )

                if year and re.search(r"\d{4}", year):
                    year_match = re.search(r"\d{4}", year)
                    if year_match:
                        _add(
                            f"{title} was established in {year_match.group()}.",
                            entities=[{"type": "region", "name": title}],
                            tags=["austria", "wikipedia", "history"],
                        )

    return facts


# ─── Wikidata SPARQL ─────────────────────────────────────────────────────────


def _scrape_wikidata(source_id: str) -> list[dict]:
    """Query Wikidata for Austrian wine entities."""
    facts = []
    seen = set()

    def _add(text, domain="wine_regions", subdomain="austria", entities=None,
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
            "tags": tags or ["austria", "wikidata"],
        })

    # Query 1: Wine regions in Austria (P17 = Q40)
    query_regions = """
    SELECT DISTINCT ?item ?itemLabel ?regionLabel ?areaLabel WHERE {
        {
            ?item wdt:P31/wdt:P279* wd:Q2516866 .  # wine region
            ?item wdt:P17 wd:Q40 .                   # country = Austria
        }
        UNION
        {
            ?item wdt:P31/wdt:P279* wd:Q10864048 .  # wine appellation
            ?item wdt:P17 wd:Q40 .
        }
        OPTIONAL { ?item wdt:P131 ?region }
        OPTIONAL { ?item wdt:P2046 ?area }
        SERVICE wikibase:label { bd:serviceParam wikibase:language "en,de" }
    }
    ORDER BY ?itemLabel
    LIMIT 200
    """

    try:
        rows = run_sparql(query_regions)
        for row in rows:
            name = row.get("itemLabel", "")
            region = row.get("regionLabel", "")
            area = row.get("areaLabel", "")
            if not name or name.startswith("Q"):
                continue
            if region and not region.startswith("Q"):
                _add(
                    f"{name} is a wine region in {region}, Austria.",
                    entities=[{"type": "region", "name": name}],
                )
            else:
                _add(
                    f"{name} is a wine region in Austria.",
                    entities=[{"type": "region", "name": name}],
                )
            if area and re.search(r"\d", area):
                _add(
                    f"{name} covers approximately {area} hectares.",
                    entities=[{"type": "region", "name": name}],
                    tags=["austria", "wikidata", "area"],
                )
    except Exception as e:
        logger.warning(f"Wikidata regions query failed: {e}")

    # Query 2: Austrian grape varieties
    query_grapes = """
    SELECT DISTINCT ?item ?itemLabel ?colorLabel ?originLabel WHERE {
        ?item wdt:P31/wdt:P279* wd:Q10978 .  # grape variety
        ?item wdt:P495 wd:Q40 .                # country of origin = Austria
        OPTIONAL { ?item wdt:P462 ?color }
        OPTIONAL { ?item wdt:P495 ?origin }
        SERVICE wikibase:label { bd:serviceParam wikibase:language "en,de" }
    }
    ORDER BY ?itemLabel
    LIMIT 200
    """

    try:
        rows = run_sparql(query_grapes)
        for row in rows:
            name = row.get("itemLabel", "")
            color = row.get("colorLabel", "")
            if not name or name.startswith("Q"):
                continue
            if color and not color.startswith("Q"):
                _add(
                    f"{name} is an Austrian {color} grape variety.",
                    domain="grape_varieties",
                    entities=[{"type": "grape", "name": name}],
                    tags=["austria", "wikidata", "grape"],
                )
            else:
                _add(
                    f"{name} is an Austrian grape variety.",
                    domain="grape_varieties",
                    entities=[{"type": "grape", "name": name}],
                    tags=["austria", "wikidata", "grape"],
                )
    except Exception as e:
        logger.warning(f"Wikidata grapes query failed: {e}")

    # Query 3: Austrian wineries / wine producers
    query_producers = """
    SELECT DISTINCT ?item ?itemLabel ?locationLabel WHERE {
        {
            ?item wdt:P31/wdt:P279* wd:Q156362 .  # winery
            ?item wdt:P17 wd:Q40 .
        }
        UNION
        {
            ?item wdt:P31 wd:Q4830453 .  # business enterprise
            ?item wdt:P17 wd:Q40 .
            ?item wdt:P452 wd:Q282 .      # industry = wine
        }
        OPTIONAL { ?item wdt:P131 ?location }
        SERVICE wikibase:label { bd:serviceParam wikibase:language "en,de" }
    }
    ORDER BY ?itemLabel
    LIMIT 200
    """

    try:
        rows = run_sparql(query_producers)
        for row in rows:
            name = row.get("itemLabel", "")
            location = row.get("locationLabel", "")
            if not name or name.startswith("Q"):
                continue
            if location and not location.startswith("Q"):
                _add(
                    f"{name} is a wine producer in {location}, Austria.",
                    domain="producers",
                    entities=[
                        {"type": "producer", "name": name},
                        {"type": "region", "name": location},
                    ],
                    tags=["austria", "wikidata", "producer"],
                )
            else:
                _add(
                    f"{name} is a wine producer in Austria.",
                    domain="producers",
                    entities=[{"type": "producer", "name": name}],
                    tags=["austria", "wikidata", "producer"],
                )
    except Exception as e:
        logger.warning(f"Wikidata producers query failed: {e}")

    return facts


# ─── austrianwine.com Scraping ──────────────────────────────────────────────


def _scrape_austrianwine(source_id: str) -> list[dict]:
    """Scrape supplementary facts from austrianwine.com."""
    facts = []
    seen = set()

    paths = [
        "/en/our-wine/grape-varieties",
        "/en/our-wine/wine-growing-regions",
        "/en/our-wine/austrian-wine-and-the-law",
        "/en/our-wine",
    ]

    session = requests.Session()
    session.headers.update(AUSTRIANWINE_HEADERS)

    austria_keywords = re.compile(
        r"\b(?:appellation|vineyard|grape|wine|DAC|hectare|"
        r"terroir|grüner veltliner|riesling|zweigelt|blaufränkisch|"
        r"welschriesling|muskateller|sauvignon|pinot|chardonnay|"
        r"niederösterreich|burgenland|steiermark|wien|wachau|kamptal|"
        r"kremstal|weinviertel|neusiedlersee|thermenregion|"
        r"prädikat|spätlese|auslese|beerenauslese|trockenbeerenauslese|"
        r"eiswein|strohwein|qualitätswein|vintage|barrel|oak|tannin|blend)\b",
        re.IGNORECASE,
    )

    for path in paths:
        url = f"{AUSTRIANWINE_BASE_URL}{path}"
        logger.info(f"Attempting to scrape: {url}")
        try:
            time.sleep(AUSTRIANWINE_REQUEST_DELAY)
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
                if not austria_keywords.search(text):
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
                    "subdomain": "austria",
                    "source_id": source_id,
                    "entities": [],
                    "confidence": 0.8,
                    "tags": ["austria", "austrianwine", "scraped"],
                })

        except requests.exceptions.RequestException as e:
            logger.warning(f"Failed to scrape {url}: {e}")

    logger.info(f"austrianwine.com scraping yielded {len(facts)} facts")
    return facts


# ─── Validation ───────────────────────────────────────────────────────────────


def validate_facts(facts: list[dict]) -> None:
    """Run quality checks on extracted facts."""
    logger.info(f"\n{'='*60}")
    logger.info(f"VALIDATION REPORT — Austria Scraper")
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
    for i, t1 in enumerate(texts):
        for t2 in texts[i + 1:]:
            if t1 in t2 or t2 in t1:
                dupes += 1
    logger.info(f"\nNear-duplicate pairs (substring): {dupes}")

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
    austrianwine_source_id: str,
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

    # austrianwine.com
    if scrape_web:
        logger.info("--- austrianwine.com ---")
        web_facts = _scrape_austrianwine(austrianwine_source_id)
        logger.info(f"austrianwine.com facts: {len(web_facts)}")
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

    logger.info("=== TEST RUN: Austria Scraper ===")
    wiki_sid = ensure_wiki_source("Austrian wine")
    wikidata_sid = ensure_wikidata_source("Austrian wine")
    web_sid = ensure_source(
        name="Austrian Wine Marketing Board",
        url="https://www.austrianwine.com",
        source_type="official_body",
        tier="tier_2_authoritative",
        language="en",
    )

    session = wiki_session()

    # Just fetch a few specific articles
    test_articles = ["Austrian wine", "Grüner Veltliner", "Zweigelt",
                     "Wachau (wine region)", "Weinviertel"]
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
                        "subdomain": "austria",
                        "source_id": wiki_sid,
                        "entities": [{"type": "region", "name": title}],
                        "confidence": 0.9,
                        "tags": ["austria", "wikipedia", "test"],
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
    """Austrian wine scraper — genuine external data only."""

    if list_sections:
        click.echo("Austria Scraper — Data Sources:")
        click.echo("  1. Wikipedia: Austrian wine key articles & category crawl")
        click.echo("     - Key articles: Austrian wine, Grüner Veltliner, Zweigelt, etc.")
        click.echo("     - Categories: Wine regions of Austria, Austrian wine")
        click.echo("  2. Wikidata: Austrian wine regions & grape varieties (SPARQL)")
        click.echo("     - Wine regions with P17=Q40 (country=Austria)")
        click.echo("     - Grape varieties with P495=Q40 (origin=Austria)")
        click.echo("  3. austrianwine.com: Supplementary web scraping")
        return

    if test_run:
        run_test(cleanup=cleanup)
        return

    if not run_all and not dry_run and not validate:
        click.echo("Use --all, --dry-run, --validate, --test-run, or --list")
        return

    # Register sources
    wiki_sid = ensure_wiki_source("Austrian wine")
    wikidata_sid = ensure_wikidata_source("Austrian wine")
    web_sid = ensure_source(
        name="Austrian Wine Marketing Board",
        url="https://www.austrianwine.com",
        source_type="official_body",
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
