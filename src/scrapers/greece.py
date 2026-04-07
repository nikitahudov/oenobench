"""
OenoBench — Greek Wine Scraper (genuine external data only)

Extracts Greek wine knowledge from:
  1. Wikipedia — key articles on Greek wine regions, grapes, styles
  2. Wikidata SPARQL — Greek wine regions, grape varieties, PDO/PGI appellations
  3. EU GIView API — supplementary PDO/PGI data (best-effort)

Every fact traces to a URL that was actually fetched and parsed.
No hardcoded wine knowledge.

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
GIVIEW_BASE_URL = "https://www.tmdn.org/giview/api/geographical-indication"
GIVIEW_REQUEST_DELAY = 3
REQUEST_TIMEOUT = 30
GIVIEW_HEADERS = {
    "User-Agent": "OenoBench-Research/1.0 (academic wine benchmark)",
    "Accept": "application/json",
}


# ─── Wikipedia Scraping ──────────────────────────────────────────────────────


def _scrape_wikipedia_key_articles(session: requests.Session, source_id: str) -> list[dict]:
    """Scrape key Wikipedia articles about Greek wine."""
    facts = []
    seen = set()

    def _add(text, domain="wine_regions", subdomain="greece", entities=None,
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
            "tags": tags or ["greece", "wikipedia"],
        })

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
    ]

    for title in key_articles:
        logger.info(f"Fetching Wikipedia article: {title}")
        extract, wikitext = fetch_article(session, title)

        if extract:
            sentences = extract_lead_sentences(extract)
            for s in sentences[:10]:
                _add(s, entities=[{"type": "region", "name": title}],
                     tags=["greece", "wikipedia", "key_article"])

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
                            _add(
                                f"{title} permits the {g} grape variety.",
                                domain="grape_varieties",
                                entities=[
                                    {"type": "region", "name": title},
                                    {"type": "grape", "name": g},
                                ],
                                tags=["greece", "wikipedia", "grape"],
                            )

                if area and re.search(r"\d", area):
                    area_clean = re.sub(r"[^\d.,]", " ", area).strip()
                    if area_clean:
                        _add(
                            f"{title} covers approximately {area_clean} hectares.",
                            entities=[{"type": "region", "name": title}],
                            tags=["greece", "wikipedia", "area"],
                        )

                if classification and not classification.startswith("Q"):
                    _add(
                        f"{title} holds {classification} classification.",
                        entities=[{"type": "region", "name": title}],
                        tags=["greece", "wikipedia", "classification"],
                    )

                if region and not region.startswith("Q"):
                    _add(
                        f"{title} is located in the {region} wine region.",
                        entities=[{"type": "region", "name": title}],
                        tags=["greece", "wikipedia", "region"],
                    )

                if year and re.search(r"\d{4}", year):
                    year_match = re.search(r"\d{4}", year)
                    if year_match:
                        _add(
                            f"{title} was established in {year_match.group()}.",
                            entities=[{"type": "region", "name": title}],
                            tags=["greece", "wikipedia", "history"],
                        )

            # Parse tables for additional structured data
            rows = parse_wikitext_tables(wikitext)
            for row in rows:
                if len(row) >= 2:
                    name = row[0].strip()
                    detail = row[1].strip()

                    if not name or len(name) < 3 or len(name) > 80:
                        continue
                    if name.lower() in ("name", "grape", "variety", "region", "wine"):
                        continue

                    if detail and len(detail) < 60 and not detail.startswith(("–", "—", "-")):
                        if is_wine_relevant(f"{name} {detail}"):
                            _add(
                                f"{name}: {detail}.",
                                entities=[{"type": "region", "name": title}],
                                tags=["greece", "wikipedia", "table"],
                            )

    return facts


def _scrape_wikipedia_categories(session: requests.Session, source_id: str) -> list[dict]:
    """Scrape Greek wine articles discovered via Wikipedia category crawling."""
    facts = []
    seen = set()

    def _add(text, domain="wine_regions", subdomain="greece", entities=None,
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
            "tags": tags or ["greece", "wikipedia"],
        })

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
            sentences = extract_lead_sentences(extract)
            for s in sentences[:6]:
                _add(s, entities=[{"type": "region", "name": title}],
                     tags=["greece", "wikipedia", "category"])

        if wikitext:
            infobox = parse_infobox(wikitext)
            if infobox:
                region = infobox.get("region", "")
                grape = infobox.get("grapes", "") or infobox.get("grape", "")
                area = infobox.get("area", "") or infobox.get("size", "") or infobox.get("hectares", "")
                classification = infobox.get("classification", "") or infobox.get("appellation", "") or infobox.get("designation", "")
                year = infobox.get("year established", "") or infobox.get("established", "")
                colour = infobox.get("color", "") or infobox.get("colour", "")
                species = infobox.get("species", "")
                also_called = infobox.get("also called", "") or infobox.get("synonyms", "")

                if region and not region.startswith("Q"):
                    _add(
                        f"{title} is a wine appellation in {region}.",
                        entities=[{"type": "region", "name": title}],
                        tags=["greece", "wikipedia", "appellation"],
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
                                tags=["greece", "wikipedia", "grape"],
                            )

                if area and re.search(r"\d", area):
                    area_clean = re.sub(r"[^\d.,]", " ", area).strip()
                    if area_clean:
                        _add(
                            f"{title} covers approximately {area_clean} hectares.",
                            entities=[{"type": "region", "name": title}],
                            tags=["greece", "wikipedia", "area"],
                        )

                if classification and not classification.startswith("Q"):
                    _add(
                        f"{title} holds {classification} classification.",
                        entities=[{"type": "region", "name": title}],
                        tags=["greece", "wikipedia", "classification"],
                    )

                if year and re.search(r"\d{4}", year):
                    year_match = re.search(r"\d{4}", year)
                    if year_match:
                        _add(
                            f"{title} was established in {year_match.group()}.",
                            entities=[{"type": "region", "name": title}],
                            tags=["greece", "wikipedia", "history"],
                        )

                if colour and len(colour) < 30:
                    _add(
                        f"{title} is a {colour} grape variety.",
                        domain="grape_varieties",
                        entities=[{"type": "grape", "name": title}],
                        tags=["greece", "wikipedia", "grape"],
                    )

                if species and "vinifera" in species.lower():
                    _add(
                        f"{title} is a Vitis vinifera grape variety.",
                        domain="grape_varieties",
                        entities=[{"type": "grape", "name": title}],
                        tags=["greece", "wikipedia", "grape"],
                    )

                if also_called and len(also_called) < 80:
                    _add(
                        f"{title} is also known as {also_called}.",
                        domain="grape_varieties",
                        entities=[{"type": "grape", "name": title}],
                        tags=["greece", "wikipedia", "synonym"],
                    )

    return facts


# ─── Wikidata SPARQL ─────────────────────────────────────────────────────────


def _scrape_wikidata(source_id: str) -> list[dict]:
    """Query Wikidata for Greek wine entities."""
    facts = []
    seen = set()

    def _add(text, domain="wine_regions", subdomain="greece", entities=None,
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
            "tags": tags or ["greece", "wikidata"],
        })

    # Query 1: Wine regions in Greece (P17 = Q41)
    query_regions = """
    SELECT DISTINCT ?item ?itemLabel ?regionLabel WHERE {
        ?item wdt:P31/wdt:P279* wd:Q10864048 .  # wine appellation
        ?item wdt:P17 wd:Q41 .  # country: Greece
        OPTIONAL { ?item wdt:P131 ?region }
        SERVICE wikibase:label { bd:serviceParam wikibase:language "en,el" }
    }
    ORDER BY ?itemLabel
    LIMIT 200
    """

    try:
        rows = run_sparql(query_regions)
        for row in rows:
            name = row.get("itemLabel", "")
            region = row.get("regionLabel", "")
            if not name or name.startswith("Q"):
                continue
            if region and not region.startswith("Q"):
                _add(
                    f"{name} is a wine appellation in {region}, Greece.",
                    entities=[{"type": "region", "name": name}],
                )
            else:
                _add(
                    f"{name} is a wine appellation in Greece.",
                    entities=[{"type": "region", "name": name}],
                )
    except Exception as e:
        logger.warning(f"Wikidata regions query failed: {e}")

    # Query 2: Greek-origin grape varieties (P495 = Q41)
    query_grapes = """
    SELECT DISTINCT ?item ?itemLabel ?colorLabel WHERE {
        ?item wdt:P31 wd:Q10978 .  # grape variety
        ?item wdt:P495 wd:Q41 .  # country of origin: Greece
        OPTIONAL { ?item wdt:P462 ?color }
        SERVICE wikibase:label { bd:serviceParam wikibase:language "en,el" }
    }
    ORDER BY ?itemLabel
    LIMIT 300
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
    query_pdo = """
    SELECT DISTINCT ?item ?itemLabel ?typeLabel ?regionLabel WHERE {
        {
            ?item wdt:P31 wd:Q18564734 .  # PDO
            ?item wdt:P17 wd:Q41 .
        }
        UNION
        {
            ?item wdt:P31 wd:Q18564727 .  # PGI
            ?item wdt:P17 wd:Q41 .
        }
        OPTIONAL { ?item wdt:P31 ?type }
        OPTIONAL { ?item wdt:P131 ?region }
        SERVICE wikibase:label { bd:serviceParam wikibase:language "en,el" }
    }
    ORDER BY ?itemLabel
    LIMIT 200
    """

    try:
        rows = run_sparql(query_pdo)
        for row in rows:
            name = row.get("itemLabel", "")
            type_label = row.get("typeLabel", "")
            region = row.get("regionLabel", "")
            if not name or name.startswith("Q"):
                continue

            designation = ""
            if type_label and "protected designation" in type_label.lower():
                designation = "PDO"
            elif type_label and "protected geographical" in type_label.lower():
                designation = "PGI"

            if designation:
                if region and not region.startswith("Q"):
                    _add(
                        f"{name} is a {designation} wine appellation in {region}, Greece.",
                        entities=[{"type": "region", "name": name}],
                        tags=["greece", "wikidata", designation.lower()],
                    )
                else:
                    _add(
                        f"{name} is a {designation} wine appellation in Greece.",
                        entities=[{"type": "region", "name": name}],
                        tags=["greece", "wikidata", designation.lower()],
                    )
    except Exception as e:
        logger.warning(f"Wikidata PDO/PGI query failed: {e}")

    return facts


# ─── EU GIView API Scraping ─────────────────────────────────────────────────


def _scrape_giview(source_id: str) -> list[dict]:
    """Scrape supplementary facts from the EU GIView database for Greek wines."""
    facts = []
    seen = set()

    urls_to_try = [
        f"{GIVIEW_BASE_URL}?country=GR&category=WINE",
        f"{GIVIEW_BASE_URL}?filters=%7B%22country%22%3A%5B%22GR%22%5D%2C%22category%22%3A%5B%22WINE%22%5D%7D",
    ]

    session = requests.Session()
    session.headers.update(GIVIEW_HEADERS)

    for url in urls_to_try:
        logger.info(f"Attempting GIView API: {url}")
        try:
            time.sleep(GIVIEW_REQUEST_DELAY)
            resp = session.get(url, timeout=REQUEST_TIMEOUT)
            if resp.status_code != 200:
                logger.warning(f"HTTP {resp.status_code} for {url}")
                continue

            data = resp.json()
            items = []
            if isinstance(data, list):
                items = data
            elif isinstance(data, dict):
                items = data.get("data", data.get("results", data.get("items", [])))

            if not items:
                logger.info(f"No items found in GIView response from {url}")
                continue

            logger.info(f"GIView returned {len(items)} items")
            for item in items:
                name = item.get("name", "") or item.get("denomination", "") or ""
                gi_type = item.get("type", "") or item.get("giType", "") or ""
                status = item.get("status", "")

                if not name or len(name) < 2:
                    continue

                designation = ""
                if "PDO" in gi_type.upper() or "designation of origin" in gi_type.lower():
                    designation = "PDO"
                elif "PGI" in gi_type.upper() or "geographical indication" in gi_type.lower():
                    designation = "PGI"

                text = ""
                if designation:
                    text = f"{name} is a {designation} wine from Greece registered in the EU GIView database."
                else:
                    text = f"{name} is a registered Greek wine in the EU GIView database."

                if text in seen:
                    continue
                seen.add(text)

                facts.append({
                    "fact_text": text,
                    "domain": "wine_regions",
                    "subdomain": "greece",
                    "source_id": source_id,
                    "entities": [{"type": "region", "name": name}],
                    "confidence": 0.8,
                    "tags": ["greece", "giview", designation.lower()] if designation else ["greece", "giview"],
                })

            # If we got results, don't try other URLs
            if facts:
                break

        except (requests.exceptions.RequestException, ValueError) as e:
            logger.warning(f"Failed to scrape GIView {url}: {e}")

    logger.info(f"GIView scraping yielded {len(facts)} facts")
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
    giview_source_id: str,
    scrape_giview: bool = True,
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

    # GIView
    if scrape_giview:
        logger.info("--- EU GIView API ---")
        giview_facts = _scrape_giview(giview_source_id)
        logger.info(f"GIView facts: {len(giview_facts)}")
        all_facts.extend(giview_facts)

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
            for s in extract_lead_sentences(extract)[:3]:
                if s not in seen:
                    seen.add(s)
                    facts.append({
                        "fact_text": s,
                        "domain": "wine_regions",
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
        click.echo("  1. Wikipedia: Key Greek wine articles (12 articles)")
        click.echo("  2. Wikipedia: Category crawl (wine regions, grapes)")
        click.echo("  3. Wikidata: Greek wine regions, grapes, PDO/PGI (SPARQL)")
        click.echo("  4. EU GIView: Greek PDO/PGI registrations (best-effort)")
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
    giview_sid = ensure_source(
        name="EU GIView: Greek wine",
        url="https://www.tmdn.org/giview",
        source_type="official_body",
        tier="tier_2_authoritative",
        language="en",
    )

    # Collect facts
    facts = collect_all_facts(wiki_sid, wikidata_sid, giview_sid)

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
