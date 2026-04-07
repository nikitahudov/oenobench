"""
OenoBench — Burgundy Wine Scraper (genuine external data only)

Extracts Burgundy wine knowledge from:
  1. Wikipedia — classification articles, Grand Cru articles, Chablis, appellations
  2. Wikidata SPARQL — appellations in Burgundy departments, Grand Cru vineyards
  3. bourgogne-wines.com — supplementary scraping when accessible

Every fact traces to a URL that was actually fetched and parsed.
No hardcoded wine knowledge.

Usage:
    python -m src.scrapers.burgundy --all
    python -m src.scrapers.burgundy --dry-run
    python -m src.scrapers.burgundy --validate
    python -m src.scrapers.burgundy --list
    python -m src.scrapers.burgundy --test-run
    python -m src.scrapers.burgundy --test-run --cleanup
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
BIVB_BASE_URL = "https://www.bourgogne-wines.com"
BIVB_REQUEST_DELAY = 5
REQUEST_TIMEOUT = 30
BIVB_HEADERS = {
    "User-Agent": "OenoBench-Research/1.0 (academic wine benchmark)",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


# ─── Wikipedia Scraping ──────────────────────────────────────────────────────


def _scrape_wikipedia_key_articles(session: requests.Session, source_id: str) -> list[dict]:
    """Scrape key Burgundy wine articles from Wikipedia."""
    facts = []
    seen = set()

    def _add(text, domain="wine_regions", subdomain="burgundy", entities=None,
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
            "tags": tags or ["burgundy", "wikipedia"],
        })

    key_articles = [
        "Burgundy wine",
        "Burgundy wine classifications",
        "Grand cru",
        "Chablis wine",
        "Côte de Nuits",
        "Côte de Beaune",
        "Côte Chalonnaise",
        "Mâconnais",
        "Beaujolais wine",
    ]

    for title in key_articles:
        logger.info(f"Fetching Wikipedia article: {title}")
        extract, wikitext = fetch_article(session, title)

        if extract:
            sentences = extract_lead_sentences(extract)
            for s in sentences[:10]:
                _add(s, entities=[{"type": "region", "name": title}],
                     tags=["burgundy", "wikipedia", "classification"])

        if wikitext:
            # Parse tables (e.g. Grand Cru listings, classification tables)
            rows = parse_wikitext_tables(wikitext)
            for row in rows:
                if len(row) >= 2:
                    name = row[0].strip()
                    commune = row[1].strip() if len(row) > 1 else ""

                    # Skip headers and non-vineyard rows
                    if not name or name.lower() in ("name", "vineyard", "climat",
                                                      "appellation", "wine", "aoc"):
                        continue
                    if len(name) < 3 or len(name) > 80:
                        continue

                    if commune and len(commune) < 40 and not commune.startswith(("–", "—", "-")):
                        _add(
                            f"{name} is a classified Burgundy vineyard in {commune}.",
                            entities=[
                                {"type": "region", "name": name},
                                {"type": "region", "name": commune},
                            ],
                            tags=["burgundy", "wikipedia", "classification"],
                        )

            # Parse infobox data
            infobox = parse_infobox(wikitext)
            if infobox:
                grape = infobox.get("grapes", "") or infobox.get("grape", "")
                area = infobox.get("area", "") or infobox.get("size", "") or infobox.get("hectares", "")
                classification = infobox.get("classification", "")

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
                                tags=["burgundy", "wikipedia", "grape"],
                            )

                if area and re.search(r"\d", area):
                    _add(
                        f"{title} covers approximately {area} hectares.",
                        entities=[{"type": "region", "name": title}],
                        tags=["burgundy", "wikipedia", "area"],
                    )

                if classification:
                    _add(
                        f"{title} holds {classification} classification.",
                        entities=[{"type": "region", "name": title}],
                        tags=["burgundy", "wikipedia", "classification"],
                    )

    return facts


def _scrape_wikipedia_appellations(session: requests.Session, source_id: str) -> list[dict]:
    """Scrape Burgundy appellation articles from Wikipedia categories."""
    facts = []
    seen = set()

    def _add(text, domain="wine_regions", subdomain="burgundy", entities=None,
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
            "tags": tags or ["burgundy", "wikipedia"],
        })

    # Crawl Burgundy wine categories
    categories = [
        "Category:Burgundy (region) AOCs",
        "Category:Wine regions of Burgundy",
        "Category:Grand Cru vineyards of Burgundy",
    ]

    all_titles = set()
    for cat in categories:
        logger.info(f"Crawling category: {cat}")
        titles = crawl_category(session, cat, max_depth=2, max_articles=150)
        all_titles.update(titles)

    logger.info(f"Found {len(all_titles)} Burgundy-related articles")

    for title in sorted(all_titles):
        logger.info(f"Fetching: {title}")
        extract, wikitext = fetch_article(session, title)

        if extract:
            sentences = extract_lead_sentences(extract)
            for s in sentences[:6]:
                _add(s, entities=[{"type": "region", "name": title}],
                     tags=["burgundy", "wikipedia", "appellation"])

        if wikitext:
            infobox = parse_infobox(wikitext)
            if infobox:
                region = infobox.get("region", "")
                grape = infobox.get("grapes", "") or infobox.get("grape", "")
                area = infobox.get("area", "") or infobox.get("size", "") or infobox.get("hectares", "")
                appellation = infobox.get("appellation", "") or infobox.get("designation", "")
                classification = infobox.get("classification", "")
                year = infobox.get("year established", "") or infobox.get("established", "")

                if region and not region.startswith("Q"):
                    _add(
                        f"{title} is a wine appellation in {region}.",
                        entities=[{"type": "region", "name": title}],
                        tags=["burgundy", "wikipedia", "appellation"],
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
                                tags=["burgundy", "wikipedia", "grape"],
                            )

                if area and re.search(r"\d", area):
                    area_clean = re.sub(r"[^\d.,]", " ", area).strip()
                    if area_clean:
                        _add(
                            f"{title} covers approximately {area_clean} hectares.",
                            entities=[{"type": "region", "name": title}],
                            tags=["burgundy", "wikipedia", "area"],
                        )

                if classification:
                    _add(
                        f"{title} holds {classification} classification.",
                        entities=[{"type": "region", "name": title}],
                        tags=["burgundy", "wikipedia", "classification"],
                    )

                if year and re.search(r"\d{4}", year):
                    year_match = re.search(r"\d{4}", year)
                    if year_match:
                        _add(
                            f"{title} was established in {year_match.group()}.",
                            entities=[{"type": "region", "name": title}],
                            tags=["burgundy", "wikipedia", "history"],
                        )

    return facts


# ─── Wikidata SPARQL ─────────────────────────────────────────────────────────


def _scrape_wikidata(source_id: str) -> list[dict]:
    """Query Wikidata for Burgundy wine entities."""
    facts = []
    seen = set()

    def _add(text, domain="wine_regions", subdomain="burgundy", entities=None,
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
            "tags": tags or ["burgundy", "wikidata"],
        })

    # Query 1: Wine appellations in Burgundy departments
    # Côte-d'Or (Q12474), Saône-et-Loire (Q12584), Yonne (Q12642)
    query_appellations = """
    SELECT DISTINCT ?item ?itemLabel ?regionLabel ?countryLabel WHERE {
        ?item wdt:P31/wdt:P279* wd:Q10864048 .  # wine appellation
        ?item wdt:P131* ?dept .
        VALUES ?dept { wd:Q12474 wd:Q12584 wd:Q12642 }  # Côte-d'Or, Saône-et-Loire, Yonne
        OPTIONAL { ?item wdt:P131 ?region }
        OPTIONAL { ?item wdt:P17 ?country }
        SERVICE wikibase:label { bd:serviceParam wikibase:language "en,fr" }
    }
    ORDER BY ?itemLabel
    LIMIT 300
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
                    f"{name} is a wine appellation in Burgundy.",
                    entities=[{"type": "region", "name": name}],
                )
    except Exception as e:
        logger.warning(f"Wikidata appellations query failed: {e}")

    # Query 2: Grand Cru vineyards in Burgundy
    query_grand_cru = """
    SELECT DISTINCT ?item ?itemLabel ?communeLabel ?areaLabel WHERE {
        {
            ?item wdt:P31 wd:Q15348455 .  # grand cru vineyard
        }
        UNION
        {
            ?item wdt:P31/wdt:P279* wd:Q10864048 .
            ?item wdt:P131* ?dept .
            VALUES ?dept { wd:Q12474 wd:Q12584 wd:Q12642 }
            ?item wdt:P2012 ?class .
            FILTER(CONTAINS(LCASE(STR(?class)), "grand"))
        }
        OPTIONAL { ?item wdt:P131 ?commune }
        OPTIONAL { ?item wdt:P2046 ?area }
        SERVICE wikibase:label { bd:serviceParam wikibase:language "en,fr" }
    }
    ORDER BY ?itemLabel
    LIMIT 200
    """

    try:
        rows = run_sparql(query_grand_cru)
        for row in rows:
            name = row.get("itemLabel", "")
            commune = row.get("communeLabel", "")
            area = row.get("areaLabel", "")
            if not name or name.startswith("Q"):
                continue
            if commune and not commune.startswith("Q"):
                _add(
                    f"{name} is a Grand Cru vineyard in {commune}.",
                    entities=[
                        {"type": "region", "name": name},
                        {"type": "region", "name": commune},
                    ],
                    tags=["burgundy", "wikidata", "grand_cru"],
                )
            else:
                _add(
                    f"{name} is a Grand Cru vineyard in Burgundy.",
                    entities=[{"type": "region", "name": name}],
                    tags=["burgundy", "wikidata", "grand_cru"],
                )
            if area and re.search(r"\d", str(area)):
                _add(
                    f"{name} covers approximately {area} hectares.",
                    entities=[{"type": "region", "name": name}],
                    tags=["burgundy", "wikidata", "area"],
                )
    except Exception as e:
        logger.warning(f"Wikidata Grand Cru query failed: {e}")

    # Query 3: Wine-related entities in Burgundy (domaines, producers)
    query_producers = """
    SELECT DISTINCT ?item ?itemLabel ?communeLabel WHERE {
        {
            ?item wdt:P31 wd:Q156076 .  # winery
        }
        UNION
        {
            ?item wdt:P31 wd:Q16917 .  # estate / domaine
        }
        ?item wdt:P131* ?dept .
        VALUES ?dept { wd:Q12474 wd:Q12584 wd:Q12642 }
        OPTIONAL { ?item wdt:P131 ?commune }
        SERVICE wikibase:label { bd:serviceParam wikibase:language "en,fr" }
    }
    ORDER BY ?itemLabel
    LIMIT 200
    """

    try:
        rows = run_sparql(query_producers)
        for row in rows:
            name = row.get("itemLabel", "")
            commune = row.get("communeLabel", "")
            if not name or name.startswith("Q"):
                continue
            if commune and not commune.startswith("Q"):
                _add(
                    f"{name} is a wine producer in {commune}, Burgundy.",
                    domain="producers",
                    entities=[
                        {"type": "producer", "name": name},
                        {"type": "region", "name": commune},
                    ],
                    tags=["burgundy", "wikidata", "producer"],
                )
    except Exception as e:
        logger.warning(f"Wikidata producers query failed: {e}")

    return facts


# ─── BIVB Website Scraping ──────────────────────────────────────────────────


def _scrape_bivb(source_id: str) -> list[dict]:
    """Scrape supplementary facts from bourgogne-wines.com (BIVB)."""
    facts = []
    seen = set()

    paths = [
        "/our-wines/our-appellations",
        "/our-wines",
        "/our-terroir",
        "/our-terroir/the-burgundy-vineyards",
        "/our-terroir/burgundy-grape-varieties",
    ]

    session = requests.Session()
    session.headers.update(BIVB_HEADERS)

    burgundy_keywords = re.compile(
        r"\b(?:appellation|vineyard|domaine|grape|wine|AOC|hectare|"
        r"terroir|pinot|chardonnay|gamay|aligoté|aligote|"
        r"grand cru|premier cru|village|climat|côte|cote|"
        r"vintage|barrel|oak|tannin|cuvée|cuvee|"
        r"viticulture|winemaking|vinification)\b",
        re.IGNORECASE,
    )

    for path in paths:
        url = f"{BIVB_BASE_URL}{path}"
        logger.info(f"Attempting to scrape: {url}")
        try:
            time.sleep(BIVB_REQUEST_DELAY)
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
                if not burgundy_keywords.search(text):
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
                    "subdomain": "burgundy",
                    "source_id": source_id,
                    "entities": [],
                    "confidence": 0.8,
                    "tags": ["burgundy", "bivb", "scraped"],
                })

        except requests.exceptions.RequestException as e:
            logger.warning(f"Failed to scrape {url}: {e}")

    logger.info(f"BIVB scraping yielded {len(facts)} facts")
    return facts


# ─── Validation ───────────────────────────────────────────────────────────────


def validate_facts(facts: list[dict]) -> None:
    """Run quality checks on extracted facts."""
    logger.info(f"\n{'='*60}")
    logger.info(f"VALIDATION REPORT — Burgundy Scraper")
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

    # Entity population rate
    with_entities = sum(1 for f in facts if f.get("entities"))
    logger.info(f"\nFacts with entities: {with_entities}/{len(facts)} "
                f"({100*with_entities/max(len(facts),1):.1f}%)")

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
    bivb_source_id: str,
    scrape_bivb: bool = True,
) -> list[dict]:
    """Collect all facts from all sources."""
    session = wiki_session()
    all_facts = []

    # Wikipedia key articles
    logger.info("--- Wikipedia: Key Articles ---")
    key_facts = _scrape_wikipedia_key_articles(session, wiki_source_id)
    logger.info(f"Key article facts: {len(key_facts)}")
    all_facts.extend(key_facts)

    # Wikipedia appellations via category crawl
    logger.info("--- Wikipedia: Appellations ---")
    appellation_facts = _scrape_wikipedia_appellations(session, wiki_source_id)
    logger.info(f"Appellation facts: {len(appellation_facts)}")
    all_facts.extend(appellation_facts)

    # Wikidata
    logger.info("--- Wikidata SPARQL ---")
    wikidata_facts = _scrape_wikidata(wikidata_source_id)
    logger.info(f"Wikidata facts: {len(wikidata_facts)}")
    all_facts.extend(wikidata_facts)

    # BIVB website
    if scrape_bivb:
        logger.info("--- BIVB website ---")
        bivb_facts = _scrape_bivb(bivb_source_id)
        logger.info(f"BIVB facts: {len(bivb_facts)}")
        all_facts.extend(bivb_facts)

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

    logger.info("=== TEST RUN: Burgundy Scraper ===")
    wiki_sid = ensure_wiki_source("Burgundy wine")
    wikidata_sid = ensure_wikidata_source("Burgundy wine")
    bivb_sid = ensure_source(
        name="BIVB (Burgundy Wine Board)",
        url="https://www.bourgogne-wines.com",
        source_type="official_body",
        tier="tier_2_authoritative",
        language="en",
    )

    session = wiki_session()

    # Just fetch a few specific articles
    test_articles = ["Gevrey-Chambertin", "Chablis wine", "Romanée-Conti",
                     "Pommard", "Burgundy wine"]
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
                        "subdomain": "burgundy",
                        "source_id": wiki_sid,
                        "entities": [{"type": "region", "name": title}],
                        "confidence": 0.9,
                        "tags": ["burgundy", "wikipedia", "test"],
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
    """Burgundy wine scraper — genuine external data only."""

    if list_sections:
        click.echo("Burgundy Scraper — Data Sources:")
        click.echo("  1. Wikipedia: Burgundy classification, Grand Cru & appellation articles")
        click.echo("  2. Wikidata: Burgundy appellations, Grand Cru vineyards, producers (SPARQL)")
        click.echo("  3. BIVB (bourgogne-wines.com): Supplementary web scraping")
        return

    if test_run:
        run_test(cleanup=cleanup)
        return

    if not run_all and not dry_run and not validate:
        click.echo("Use --all, --dry-run, --validate, --test-run, or --list")
        return

    # Register sources
    wiki_sid = ensure_wiki_source("Burgundy wine")
    wikidata_sid = ensure_wikidata_source("Burgundy wine")
    bivb_sid = ensure_source(
        name="BIVB (Burgundy Wine Board)",
        url="https://www.bourgogne-wines.com",
        source_type="official_body",
        tier="tier_2_authoritative",
        language="en",
    )

    # Collect facts
    facts = collect_all_facts(wiki_sid, wikidata_sid, bivb_sid)

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
