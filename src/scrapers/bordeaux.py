"""
OenoBench — Bordeaux Wine Scraper (genuine external data only)

Extracts Bordeaux wine knowledge from:
  1. Wikipedia — classification articles, appellation articles, grape articles
  2. Wikidata SPARQL — classified châteaux, appellation structured data
  3. bordeaux.com (CIVB) — supplementary scraping when accessible

Every fact traces to a URL that was actually fetched and parsed.
No hardcoded wine knowledge.

Usage:
    python -m src.scrapers.bordeaux --all
    python -m src.scrapers.bordeaux --dry-run
    python -m src.scrapers.bordeaux --validate
    python -m src.scrapers.bordeaux --list
    python -m src.scrapers.bordeaux --test-run
    python -m src.scrapers.bordeaux --test-run --cleanup
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
CIVB_BASE_URL = "https://www.bordeaux.com"
CIVB_REQUEST_DELAY = 5
REQUEST_TIMEOUT = 30
CIVB_HEADERS = {
    "User-Agent": "OenoBench-Research/1.0 (academic wine benchmark)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


# ─── Wikipedia Scraping ──────────────────────────────────────────────────────


def _scrape_wikipedia_classifications(session: requests.Session, source_id: str) -> list[dict]:
    """Scrape the 1855, Saint-Émilion, and Graves classifications from Wikipedia."""
    facts = []
    seen = set()

    def _add(text, domain="wine_regions", subdomain="bordeaux", entities=None,
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
            "tags": tags or ["bordeaux", "wikipedia"],
        })

    # --- 1855 Classification ---
    classification_articles = [
        "Bordeaux wine",
        "Classification of Bordeaux wine",
        "Bordeaux Wine Official Classification of 1855",
        "Classification of Saint-Émilion wine",
        "Pessac-Léognan",
    ]

    for title in classification_articles:
        logger.info(f"Fetching Wikipedia article: {title}")
        extract, wikitext = fetch_article(session, title)

        if extract:
            sentences = extract_lead_sentences(extract)
            for s in sentences[:10]:
                _add(s, entities=[{"type": "region", "name": title}],
                     tags=["bordeaux", "wikipedia", "classification"])

        if wikitext:
            # Parse tables from classification articles
            rows = parse_wikitext_tables(wikitext)
            for row in rows:
                if len(row) >= 2:
                    # Try to identify château + commune patterns
                    name = row[0].strip()
                    commune = row[1].strip() if len(row) > 1 else ""

                    # Skip headers and non-château rows
                    if not name or name.lower() in ("name", "château", "chateau",
                                                      "estate", "wine", "property"):
                        continue
                    if len(name) < 3 or len(name) > 80:
                        continue

                    # Look for growth level context in the wikitext
                    # Build fact about château location
                    if commune and len(commune) < 40 and not commune.startswith(("–", "—", "-")):
                        _add(
                            f"{name} is a classified Bordeaux estate in {commune}.",
                            entities=[
                                {"type": "producer", "name": name},
                                {"type": "region", "name": commune},
                            ],
                            tags=["bordeaux", "wikipedia", "classification", "1855"],
                        )

            # Parse infobox data
            infobox = parse_infobox(wikitext)
            if infobox:
                region = infobox.get("region", "")
                grape = infobox.get("grapes", "") or infobox.get("grape", "")
                area = infobox.get("area", "") or infobox.get("size", "")

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
                                tags=["bordeaux", "wikipedia", "grape"],
                            )

                if area and re.search(r"\d", area):
                    _add(
                        f"{title} covers approximately {area} hectares.",
                        entities=[{"type": "region", "name": title}],
                        tags=["bordeaux", "wikipedia", "area"],
                    )

    return facts


def _scrape_wikipedia_appellations(session: requests.Session, source_id: str) -> list[dict]:
    """Scrape Bordeaux appellation articles from Wikipedia categories."""
    facts = []
    seen = set()

    def _add(text, domain="wine_regions", subdomain="bordeaux", entities=None,
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
            "tags": tags or ["bordeaux", "wikipedia"],
        })

    # Crawl Bordeaux wine categories
    categories = [
        "Category:Bordeaux AOCs",
        "Category:Wine regions of Gironde",
    ]

    all_titles = set()
    for cat in categories:
        logger.info(f"Crawling category: {cat}")
        titles = crawl_category(session, cat, max_depth=2, max_articles=100)
        all_titles.update(titles)

    logger.info(f"Found {len(all_titles)} Bordeaux-related articles")

    for title in sorted(all_titles):
        logger.info(f"Fetching: {title}")
        extract, wikitext = fetch_article(session, title)

        if extract:
            sentences = extract_lead_sentences(extract)
            for s in sentences[:6]:
                _add(s, entities=[{"type": "region", "name": title}],
                     tags=["bordeaux", "wikipedia", "appellation"])

        if wikitext:
            infobox = parse_infobox(wikitext)
            if infobox:
                region = infobox.get("region", "")
                country = infobox.get("country", "")
                grape = infobox.get("grapes", "") or infobox.get("grape", "")
                area = infobox.get("area", "") or infobox.get("size", "") or infobox.get("hectares", "")
                appellation = infobox.get("appellation", "") or infobox.get("designation", "")
                classification = infobox.get("classification", "")
                year = infobox.get("year established", "") or infobox.get("established", "")

                if region and not region.startswith("Q"):
                    _add(
                        f"{title} is a wine appellation in {region}.",
                        entities=[{"type": "region", "name": title}],
                        tags=["bordeaux", "wikipedia", "appellation"],
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
                                tags=["bordeaux", "wikipedia", "grape"],
                            )

                if area and re.search(r"\d", area):
                    area_clean = re.sub(r"[^\d.,]", " ", area).strip()
                    if area_clean:
                        _add(
                            f"{title} covers approximately {area_clean} hectares.",
                            entities=[{"type": "region", "name": title}],
                            tags=["bordeaux", "wikipedia", "area"],
                        )

                if classification:
                    _add(
                        f"{title} holds {classification} classification.",
                        entities=[{"type": "region", "name": title}],
                        tags=["bordeaux", "wikipedia", "classification"],
                    )

                if year and re.search(r"\d{4}", year):
                    year_match = re.search(r"\d{4}", year)
                    if year_match:
                        _add(
                            f"{title} was established in {year_match.group()}.",
                            entities=[{"type": "region", "name": title}],
                            tags=["bordeaux", "wikipedia", "history"],
                        )

    return facts


# ─── Wikidata SPARQL ─────────────────────────────────────────────────────────


def _scrape_wikidata(source_id: str) -> list[dict]:
    """Query Wikidata for Bordeaux wine entities."""
    facts = []
    seen = set()

    def _add(text, domain="wine_regions", subdomain="bordeaux", entities=None,
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
            "tags": tags or ["bordeaux", "wikidata"],
        })

    # Query 1: Bordeaux wine appellations
    query_appellations = """
    SELECT DISTINCT ?item ?itemLabel ?regionLabel ?countryLabel WHERE {
        ?item wdt:P31/wdt:P279* wd:Q10864048 .  # wine appellation
        ?item wdt:P131* ?gironde .
        VALUES ?gironde { wd:Q12526 wd:Q15104 }  # Gironde or Nouvelle-Aquitaine
        OPTIONAL { ?item wdt:P131 ?region }
        OPTIONAL { ?item wdt:P17 ?country }
        SERVICE wikibase:label { bd:serviceParam wikibase:language "en,fr" }
    }
    ORDER BY ?itemLabel
    LIMIT 200
    """

    try:
        rows = run_sparql(query_appellations)
        for row in rows:
            name = row.get("itemLabel", "")
            region = row.get("regionLabel", "")
            if not name or name.startswith("Q"):
                continue
            if region and not region.startswith("Q"):
                _add(
                    f"{name} is a wine appellation in {region}.",
                    entities=[{"type": "region", "name": name}],
                )
            else:
                _add(
                    f"{name} is a wine appellation in Bordeaux.",
                    entities=[{"type": "region", "name": name}],
                )
    except Exception as e:
        logger.warning(f"Wikidata appellations query failed: {e}")

    # Query 2: Bordeaux châteaux / wine estates
    query_chateaux = """
    SELECT DISTINCT ?item ?itemLabel ?communeLabel ?classLabel WHERE {
        {
            ?item wdt:P31 wd:Q3658505 .  # château in Bordeaux
        }
        UNION
        {
            ?item wdt:P361 wd:Q1344189 .  # part of 1855 classification
        }
        OPTIONAL { ?item wdt:P131 ?commune }
        OPTIONAL { ?item wdt:P361 ?class }
        SERVICE wikibase:label { bd:serviceParam wikibase:language "en,fr" }
    }
    ORDER BY ?itemLabel
    LIMIT 300
    """

    try:
        rows = run_sparql(query_chateaux)
        for row in rows:
            name = row.get("itemLabel", "")
            commune = row.get("communeLabel", "")
            classification = row.get("classLabel", "")
            if not name or name.startswith("Q"):
                continue
            if commune and not commune.startswith("Q"):
                _add(
                    f"{name} is a Bordeaux wine estate in {commune}.",
                    domain="producers",
                    entities=[
                        {"type": "producer", "name": name},
                        {"type": "region", "name": commune},
                    ],
                    tags=["bordeaux", "wikidata", "chateau"],
                )
            if classification and not classification.startswith("Q"):
                _add(
                    f"{name} is part of the {classification}.",
                    domain="producers",
                    entities=[{"type": "producer", "name": name}],
                    tags=["bordeaux", "wikidata", "classification"],
                )
    except Exception as e:
        logger.warning(f"Wikidata châteaux query failed: {e}")

    return facts


# ─── CIVB Website Scraping ───────────────────────────────────────────────────


def _scrape_civb(source_id: str) -> list[dict]:
    """Scrape supplementary facts from bordeaux.com (CIVB)."""
    facts = []
    seen = set()

    paths = [
        "/us/our-terroir/appellations",
        "/us/our-wines",
        "/us/our-terroir",
    ]

    session = requests.Session()
    session.headers.update(CIVB_HEADERS)

    bordeaux_keywords = re.compile(
        r"\b(?:appellation|vineyard|château|chateau|grape|wine|AOC|hectare|"
        r"terroir|cabernet|merlot|sauvignon|sémillon|semillon|muscadelle|"
        r"petit verdot|malbec|carménère|vintage|barrel|oak|tannin|blend)\b",
        re.IGNORECASE,
    )

    for path in paths:
        url = f"{CIVB_BASE_URL}{path}"
        logger.info(f"Attempting to scrape: {url}")
        try:
            time.sleep(CIVB_REQUEST_DELAY)
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
                if not bordeaux_keywords.search(text):
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
                    "subdomain": "bordeaux",
                    "source_id": source_id,
                    "entities": [],
                    "confidence": 0.8,
                    "tags": ["bordeaux", "civb", "scraped"],
                })

        except requests.exceptions.RequestException as e:
            logger.warning(f"Failed to scrape {url}: {e}")

    logger.info(f"CIVB scraping yielded {len(facts)} facts")
    return facts


# ─── Validation ───────────────────────────────────────────────────────────────


def validate_facts(facts: list[dict]) -> None:
    """Run quality checks on extracted facts."""
    logger.info(f"\n{'='*60}")
    logger.info(f"VALIDATION REPORT — Bordeaux Scraper")
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

    # Sample facts
    logger.info(f"\n10 random sample facts:")
    for f in random.sample(facts, min(10, len(facts))):
        logger.info(f"  [{f['domain']}] (conf={f.get('confidence', 1.0)}) {f['fact_text']}")


# ─── Main Collection ──────────────────────────────────────────────────────────


def collect_all_facts(
    wiki_source_id: str,
    wikidata_source_id: str,
    civb_source_id: str,
    scrape_civb: bool = True,
) -> list[dict]:
    """Collect all facts from all sources."""
    session = wiki_session()
    all_facts = []

    # Wikipedia classifications
    logger.info("--- Wikipedia: Classifications ---")
    classification_facts = _scrape_wikipedia_classifications(session, wiki_source_id)
    logger.info(f"Classification facts: {len(classification_facts)}")
    all_facts.extend(classification_facts)

    # Wikipedia appellations
    logger.info("--- Wikipedia: Appellations ---")
    appellation_facts = _scrape_wikipedia_appellations(session, wiki_source_id)
    logger.info(f"Appellation facts: {len(appellation_facts)}")
    all_facts.extend(appellation_facts)

    # Wikidata
    logger.info("--- Wikidata SPARQL ---")
    wikidata_facts = _scrape_wikidata(wikidata_source_id)
    logger.info(f"Wikidata facts: {len(wikidata_facts)}")
    all_facts.extend(wikidata_facts)

    # CIVB website
    if scrape_civb:
        logger.info("--- CIVB website ---")
        civb_facts = _scrape_civb(civb_source_id)
        logger.info(f"CIVB facts: {len(civb_facts)}")
        all_facts.extend(civb_facts)

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

    logger.info("=== TEST RUN: Bordeaux Scraper ===")
    wiki_sid = ensure_wiki_source("Bordeaux wine")
    wikidata_sid = ensure_wikidata_source("Bordeaux wine")
    civb_sid = ensure_source(
        name="CIVB (Bordeaux Wine Council)",
        url="https://www.bordeaux.com",
        source_type="official_body",
        tier="tier_2_authoritative",
        language="en",
    )

    session = wiki_session()

    # Just fetch a few specific articles
    test_articles = ["Pauillac", "Margaux AOC", "Saint-Julien AOC",
                     "Château Lafite Rothschild", "Bordeaux wine"]
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
                        "subdomain": "bordeaux",
                        "source_id": wiki_sid,
                        "entities": [{"type": "region", "name": title}],
                        "confidence": 0.9,
                        "tags": ["bordeaux", "wikipedia", "test"],
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
    """Bordeaux wine scraper — genuine external data only."""

    if list_sections:
        click.echo("Bordeaux Scraper — Data Sources:")
        click.echo("  1. Wikipedia: Bordeaux classification & appellation articles")
        click.echo("  2. Wikidata: Bordeaux châteaux & appellations (SPARQL)")
        click.echo("  3. CIVB (bordeaux.com): Supplementary web scraping")
        return

    if test_run:
        run_test(cleanup=cleanup)
        return

    if not run_all and not dry_run and not validate:
        click.echo("Use --all, --dry-run, --validate, --test-run, or --list")
        return

    # Register sources
    wiki_sid = ensure_wiki_source("Bordeaux wine")
    wikidata_sid = ensure_wikidata_source("Bordeaux wine")
    civb_sid = ensure_source(
        name="CIVB (Bordeaux Wine Council)",
        url="https://www.bordeaux.com",
        source_type="official_body",
        tier="tier_2_authoritative",
        language="en",
    )

    # Collect facts
    facts = collect_all_facts(wiki_sid, wikidata_sid, civb_sid)

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
