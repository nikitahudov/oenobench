"""
OenoBench — Hungary & Georgia Wine Scraper (genuine external data only)

Extracts Hungarian and Georgian wine knowledge from:
  1. Wikipedia — key articles on Hungarian/Georgian wine, regions, grape varieties
  2. Wikipedia categories — "Wine regions of Hungary", "Georgian wine"
  3. Wikidata SPARQL — wine regions with P17=Q28 (Hungary) / P17=Q230 (Georgia),
     grape varieties, wineries, appellations

Every fact traces to a URL that was actually fetched and parsed.
No hardcoded wine knowledge.

Usage:
    python -m src.scrapers.hungary_georgia --all
    python -m src.scrapers.hungary_georgia --dry-run
    python -m src.scrapers.hungary_georgia --validate
    python -m src.scrapers.hungary_georgia --list
    python -m src.scrapers.hungary_georgia --test-run
    python -m src.scrapers.hungary_georgia --test-run --cleanup
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

# Override wiki delay for rate limiting (avoid 429s)
WIKI_REQUEST_DELAY_OVERRIDE = 5.0

# Wikidata QIDs
HUNGARY_QID = "Q28"
GEORGIA_QID = "Q230"

# Region keywords for on-topic filtering
HUNGARY_KEYWORDS = {
    "hungary", "hungarian", "tokaj", "tokaji", "eger", "egri", "villány",
    "villany", "szekszárd", "szekszard", "sopron", "badacsony", "somló",
    "somlo", "kunság", "kunsag", "mátra", "matra", "etyek", "neszmély",
    "balaton", "pannonhalma", "hajós-baja", "pécs", "bükk", "bukk",
    "furmint", "hárslevelű", "harslevelü", "kadarka", "kékfrankos",
    "kekfrankos", "olaszrizling", "cserszegi", "irsai olivér",
    "sárgamuskotály", "blaufränkisch", "bikavér", "bikaver",
    "aszú", "aszu", "szamorodni", "eszencia", "puttonyos",
}

GEORGIA_KEYWORDS = {
    "georgia", "georgian", "kakheti", "kartli", "imereti", "racha",
    "lechkhumi", "guria", "samegrelo", "adjara", "abkhazia",
    "saperavi", "rkatsiteli", "mtsvane", "kisi", "chinuri",
    "aleksandrouli", "mujuretuli", "ojaleshi", "tsolikouri",
    "qvevri", "kvevri", "amber wine", "orange wine", "chacha",
    "tsinandali", "mukuzani", "kindzmarauli", "khvanchkara",
    "napareuli", "teliani", "alaverdi", "tbilisi",
}

ALL_KEYWORDS = HUNGARY_KEYWORDS | GEORGIA_KEYWORDS


# ─── Wikipedia: Hungary ─────────────────────────────────────────────────────


def _scrape_wikipedia_hungary(session: requests.Session, source_id: str) -> list[dict]:
    """Scrape key Hungarian wine articles from Wikipedia."""
    facts = []
    seen = set()

    key_articles = [
        "Tokaj wine region",
        "Tokaji",
        "Furmint",
        "Hárslevelű",
        "Hungarian wine",
        "Bikavér",
        "Villány wine region",
        "Szekszárd wine region",
        "Eger wine region",
        "Kadarka",
        "Kékfrankos",
        "Olaszrizling",
        "Sopron wine region",
        "Badacsony",
        "Somló wine region",
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
                region_keywords=HUNGARY_KEYWORDS,
            )
            for item in atomic:
                text = item["fact_text"]
                if text.lower() not in seen:
                    seen.add(text.lower())
                    facts.append({
                        "fact_text": text,
                        "domain": item["domain"],
                        "subdomain": "hungary",
                        "source_id": source_id,
                        "entities": [{"type": "region", "name": title}],
                        "confidence": 0.9,
                        "tags": ["hungary", "wikipedia", "key_article"],
                    })

        if wikitext:
            infobox = parse_infobox(wikitext)
            if infobox:
                _extract_infobox_facts(
                    infobox, title, source_id, "hungary", seen, facts,
                    country="Hungary", tags_prefix="hungary",
                )

    return facts


def _scrape_wikipedia_hungary_categories(session: requests.Session, source_id: str) -> list[dict]:
    """Scrape Hungarian wine articles from Wikipedia category crawl."""
    facts = []
    seen = set()

    categories = [
        "Category:Wine regions of Hungary",
    ]

    all_titles = set()
    for cat in categories:
        logger.info(f"Crawling category: {cat}")
        titles = crawl_category(session, cat, max_depth=2, max_articles=150)
        all_titles.update(titles)

    logger.info(f"Found {len(all_titles)} Hungarian wine articles from categories")

    for title in sorted(all_titles):
        logger.info(f"Fetching: {title}")
        time.sleep(WIKI_REQUEST_DELAY_OVERRIDE)
        extract, wikitext = fetch_article(session, title)

        if extract:
            atomic = extract_atomic_facts(
                extract, title,
                region_keywords=HUNGARY_KEYWORDS,
            )
            for item in atomic:
                text = item["fact_text"]
                if text.lower() not in seen:
                    seen.add(text.lower())
                    facts.append({
                        "fact_text": text,
                        "domain": item["domain"],
                        "subdomain": "hungary",
                        "source_id": source_id,
                        "entities": [{"type": "region", "name": title}],
                        "confidence": 0.9,
                        "tags": ["hungary", "wikipedia", "category"],
                    })

        if wikitext:
            infobox = parse_infobox(wikitext)
            if infobox:
                _extract_infobox_facts(
                    infobox, title, source_id, "hungary", seen, facts,
                    country="Hungary", tags_prefix="hungary",
                )

    return facts


# ─── Wikipedia: Georgia ─────────────────────────────────────────────────────


def _scrape_wikipedia_georgia(session: requests.Session, source_id: str) -> list[dict]:
    """Scrape key Georgian wine articles from Wikipedia."""
    facts = []
    seen = set()

    key_articles = [
        "Georgian wine",
        "Saperavi",
        "Rkatsiteli",
        "Qvevri",
        "Kakheti",
        "Winemaking in Georgia",
        "Tsinandali",
        "Mukuzani",
        "Kindzmarauli",
        "Khvanchkara",
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
                region_keywords=GEORGIA_KEYWORDS,
            )
            for item in atomic:
                text = item["fact_text"]
                if text.lower() not in seen:
                    seen.add(text.lower())
                    facts.append({
                        "fact_text": text,
                        "domain": item["domain"],
                        "subdomain": "georgia",
                        "source_id": source_id,
                        "entities": [{"type": "region", "name": title}],
                        "confidence": 0.9,
                        "tags": ["georgia", "wikipedia", "key_article"],
                    })

        if wikitext:
            infobox = parse_infobox(wikitext)
            if infobox:
                _extract_infobox_facts(
                    infobox, title, source_id, "georgia", seen, facts,
                    country="Georgia", tags_prefix="georgia",
                )

    return facts


def _scrape_wikipedia_georgia_categories(session: requests.Session, source_id: str) -> list[dict]:
    """Scrape Georgian wine articles from Wikipedia category crawl."""
    facts = []
    seen = set()

    categories = [
        "Category:Georgian wine",
    ]

    all_titles = set()
    for cat in categories:
        logger.info(f"Crawling category: {cat}")
        titles = crawl_category(session, cat, max_depth=2, max_articles=150)
        all_titles.update(titles)

    logger.info(f"Found {len(all_titles)} Georgian wine articles from categories")

    for title in sorted(all_titles):
        logger.info(f"Fetching: {title}")
        time.sleep(WIKI_REQUEST_DELAY_OVERRIDE)
        extract, wikitext = fetch_article(session, title)

        if extract:
            atomic = extract_atomic_facts(
                extract, title,
                region_keywords=GEORGIA_KEYWORDS,
            )
            for item in atomic:
                text = item["fact_text"]
                if text.lower() not in seen:
                    seen.add(text.lower())
                    facts.append({
                        "fact_text": text,
                        "domain": item["domain"],
                        "subdomain": "georgia",
                        "source_id": source_id,
                        "entities": [{"type": "region", "name": title}],
                        "confidence": 0.9,
                        "tags": ["georgia", "wikipedia", "category"],
                    })

        if wikitext:
            infobox = parse_infobox(wikitext)
            if infobox:
                _extract_infobox_facts(
                    infobox, title, source_id, "georgia", seen, facts,
                    country="Georgia", tags_prefix="georgia",
                )

    return facts


# ─── Infobox Helper ─────────────────────────────────────────────────────────


def _extract_infobox_facts(
    infobox: dict,
    title: str,
    source_id: str,
    subdomain: str,
    seen: set,
    facts: list,
    country: str = "",
    tags_prefix: str = "",
) -> None:
    """Extract structured facts from a parsed Wikipedia infobox."""
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
                        "subdomain": subdomain,
                        "source_id": source_id,
                        "entities": [
                            {"type": "region", "name": title},
                            {"type": "grape", "name": g},
                        ],
                        "confidence": 0.9,
                        "tags": [tags_prefix, "wikipedia", "grape"],
                    })

    if area and re.search(r"\d", area):
        text = f"{title} covers approximately {area} hectares."
        if text.lower() not in seen:
            seen.add(text.lower())
            facts.append({
                "fact_text": text,
                "domain": classify_domain(text),
                "subdomain": subdomain,
                "source_id": source_id,
                "entities": [{"type": "region", "name": title}],
                "confidence": 0.9,
                "tags": [tags_prefix, "wikipedia", "area"],
            })

    if classification:
        text = f"{title} holds {classification} classification."
        if text.lower() not in seen:
            seen.add(text.lower())
            facts.append({
                "fact_text": text,
                "domain": classify_domain(text),
                "subdomain": subdomain,
                "source_id": source_id,
                "entities": [{"type": "region", "name": title}],
                "confidence": 0.9,
                "tags": [tags_prefix, "wikipedia", "classification"],
            })

    if region and not region.startswith("Q"):
        suffix = f", {country}" if country else ""
        text = f"{title} is a wine region in {region}{suffix}."
        if text.lower() not in seen:
            seen.add(text.lower())
            facts.append({
                "fact_text": text,
                "domain": "wine_regions",
                "subdomain": subdomain,
                "source_id": source_id,
                "entities": [{"type": "region", "name": title}],
                "confidence": 0.9,
                "tags": [tags_prefix, "wikipedia", "region"],
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
                    "subdomain": subdomain,
                    "source_id": source_id,
                    "entities": [{"type": "region", "name": title}],
                    "confidence": 0.9,
                    "tags": [tags_prefix, "wikipedia", "history"],
                })


# ─── Wikidata SPARQL ─────────────────────────────────────────────────────────


def _scrape_wikidata_country(
    source_id: str,
    country_qid: str,
    country_name: str,
    subdomain: str,
    region_keywords: set[str],
) -> list[dict]:
    """Query Wikidata for wine entities using country-scoped SPARQL."""
    facts = []
    seen = set()

    def _add(text, domain="wine_regions", entities=None, tags=None, confidence=0.85):
        if text.lower() in seen:
            return
        seen.add(text.lower())
        facts.append({
            "fact_text": text,
            "domain": domain,
            "subdomain": subdomain,
            "source_id": source_id,
            "entities": entities or [],
            "confidence": confidence,
            "tags": tags or [subdomain, "wikidata"],
        })

    # Query 1: Wine regions
    try:
        query = SPARQL_WINE_REGIONS_BY_COUNTRY.format(country_qid=country_qid)
        rows = run_sparql_filtered(query, expected_country=country_name, region_keywords=region_keywords)
        for row in rows:
            name = row.get("itemLabel", "")
            region = row.get("regionLabel", "")
            area = row.get("areaHa", "")
            if not name or name.startswith("Q"):
                continue
            if region and not region.startswith("Q"):
                _add(f"{name} is a wine region in {region}, {country_name}.",
                     entities=[{"type": "region", "name": name}])
            else:
                _add(f"{name} is a wine region in {country_name}.",
                     entities=[{"type": "region", "name": name}])
            if area and re.search(r"\d", str(area)):
                _add(f"{name} covers approximately {area} hectares.",
                     entities=[{"type": "region", "name": name}],
                     tags=[subdomain, "wikidata", "area"])
    except Exception as e:
        logger.warning(f"Wikidata regions query failed for {country_name}: {e}")

    # Query 2: Grape varieties
    try:
        query = SPARQL_GRAPE_VARIETIES_BY_COUNTRY.format(country_qid=country_qid)
        rows = run_sparql_filtered(query, expected_country=country_name, region_keywords=region_keywords)
        for row in rows:
            name = row.get("itemLabel", "")
            color = row.get("colorLabel", "")
            if not name or name.startswith("Q"):
                continue
            if color and not color.startswith("Q"):
                _add(f"{name} is a {country_name} {color} grape variety.",
                     domain="grape_varieties",
                     entities=[{"type": "grape", "name": name}],
                     tags=[subdomain, "wikidata", "grape"])
            else:
                _add(f"{name} is a {country_name} grape variety.",
                     domain="grape_varieties",
                     entities=[{"type": "grape", "name": name}],
                     tags=[subdomain, "wikidata", "grape"])
    except Exception as e:
        logger.warning(f"Wikidata grapes query failed for {country_name}: {e}")

    # Query 3: Wineries
    try:
        query = SPARQL_WINERIES_BY_COUNTRY.format(country_qid=country_qid)
        rows = run_sparql_filtered(query, expected_country=country_name, region_keywords=region_keywords)
        for row in rows:
            name = row.get("itemLabel", "")
            location = row.get("regionLabel", "")
            founded = row.get("founded", "")
            if not name or name.startswith("Q"):
                continue
            if location and not location.startswith("Q"):
                _add(f"{name} is a wine producer in {location}, {country_name}.",
                     domain="producers",
                     entities=[{"type": "producer", "name": name}, {"type": "region", "name": location}],
                     tags=[subdomain, "wikidata", "producer"])
            else:
                _add(f"{name} is a wine producer in {country_name}.",
                     domain="producers",
                     entities=[{"type": "producer", "name": name}],
                     tags=[subdomain, "wikidata", "producer"])
            if founded:
                year_match = re.search(r"\d{4}", str(founded))
                if year_match:
                    _add(f"{name} was founded in {year_match.group()}.",
                         domain="producers",
                         entities=[{"type": "producer", "name": name}],
                         tags=[subdomain, "wikidata", "producer", "history"])
    except Exception as e:
        logger.warning(f"Wikidata producers query failed for {country_name}: {e}")

    # Query 4: Appellations
    try:
        query = SPARQL_APPELLATIONS_BY_COUNTRY.format(country_qid=country_qid)
        rows = run_sparql_filtered(query, expected_country=country_name, region_keywords=region_keywords)
        for row in rows:
            name = row.get("itemLabel", "")
            region = row.get("regionLabel", "")
            if not name or name.startswith("Q"):
                continue
            if region and not region.startswith("Q"):
                _add(f"{name} is a {country_name} wine appellation in {region}.",
                     entities=[{"type": "appellation", "name": name}],
                     tags=[subdomain, "wikidata", "appellation"])
            else:
                _add(f"{name} is a {country_name} wine appellation.",
                     entities=[{"type": "appellation", "name": name}],
                     tags=[subdomain, "wikidata", "appellation"])
    except Exception as e:
        logger.warning(f"Wikidata appellations query failed for {country_name}: {e}")

    return facts


# ─── Validation ───────────────────────────────────────────────────────────────


def validate_facts(facts: list[dict]) -> None:
    """Run quality checks on extracted facts."""
    click.echo(f"\n{'='*60}")
    click.echo(f"VALIDATION REPORT — Hungary & Georgia Scraper")
    click.echo(f"{'='*60}")
    click.echo(f"Total facts: {len(facts)}")

    # Domain breakdown
    domains = Counter(f["domain"] for f in facts)
    click.echo(f"\nDomain breakdown:")
    for domain, count in domains.most_common():
        click.echo(f"  {domain}: {count}")

    # Subdomain breakdown
    subdomains = Counter(f.get("subdomain", "unknown") for f in facts)
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
        click.echo(f"  [{f['domain']}] [{f.get('subdomain','')}] (conf={f.get('confidence', 1.0)}) {f['fact_text']}")


# ─── Main Collection ──────────────────────────────────────────────────────────


def collect_all_facts(
    wiki_hungary_sid: str,
    wiki_georgia_sid: str,
    wikidata_sid: str,
) -> list[dict]:
    """Collect all facts from all sources."""
    session = wiki_session()
    all_facts = []

    # Hungary Wikipedia key articles
    logger.info("--- Wikipedia: Hungary Key Articles ---")
    facts = _scrape_wikipedia_hungary(session, wiki_hungary_sid)
    logger.info(f"Hungary key article facts: {len(facts)}")
    all_facts.extend(facts)

    # Hungary Wikipedia categories
    logger.info("--- Wikipedia: Hungary Categories ---")
    facts = _scrape_wikipedia_hungary_categories(session, wiki_hungary_sid)
    logger.info(f"Hungary category facts: {len(facts)}")
    all_facts.extend(facts)

    # Georgia Wikipedia key articles
    logger.info("--- Wikipedia: Georgia Key Articles ---")
    facts = _scrape_wikipedia_georgia(session, wiki_georgia_sid)
    logger.info(f"Georgia key article facts: {len(facts)}")
    all_facts.extend(facts)

    # Georgia Wikipedia categories
    logger.info("--- Wikipedia: Georgia Categories ---")
    facts = _scrape_wikipedia_georgia_categories(session, wiki_georgia_sid)
    logger.info(f"Georgia category facts: {len(facts)}")
    all_facts.extend(facts)

    # Wikidata Hungary
    logger.info("--- Wikidata: Hungary ---")
    facts = _scrape_wikidata_country(
        wikidata_sid, HUNGARY_QID, "Hungary", "hungary", HUNGARY_KEYWORDS)
    logger.info(f"Wikidata Hungary facts: {len(facts)}")
    all_facts.extend(facts)

    # Wikidata Georgia
    logger.info("--- Wikidata: Georgia ---")
    facts = _scrape_wikidata_country(
        wikidata_sid, GEORGIA_QID, "Georgia", "georgia", GEORGIA_KEYWORDS)
    logger.info(f"Wikidata Georgia facts: {len(facts)}")
    all_facts.extend(facts)

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

    logger.info("=== TEST RUN: Hungary & Georgia Scraper ===")
    wiki_hungary_sid = ensure_wiki_source("Hungarian wine")
    wiki_georgia_sid = ensure_wiki_source("Georgian wine")

    session = wiki_session()
    test_articles = [
        ("Hungarian wine", "hungary", HUNGARY_KEYWORDS),
        ("Tokaji", "hungary", HUNGARY_KEYWORDS),
        ("Georgian wine", "georgia", GEORGIA_KEYWORDS),
        ("Saperavi", "georgia", GEORGIA_KEYWORDS),
        ("Qvevri", "georgia", GEORGIA_KEYWORDS),
    ]

    facts = []
    seen = set()
    for title, subdomain, keywords in test_articles[:TEST_RUN_LIMIT]:
        time.sleep(WIKI_REQUEST_DELAY_OVERRIDE)
        extract, wikitext = fetch_article(session, title)
        sid = wiki_hungary_sid if subdomain == "hungary" else wiki_georgia_sid
        if extract:
            atomic = extract_atomic_facts(extract, title, region_keywords=keywords)
            for item in atomic[:3]:
                text = item["fact_text"]
                if text.lower() not in seen:
                    seen.add(text.lower())
                    facts.append({
                        "fact_text": text,
                        "domain": item["domain"],
                        "subdomain": subdomain,
                        "source_id": sid,
                        "entities": [{"type": "region", "name": title}],
                        "confidence": 0.9,
                        "tags": [subdomain, "wikipedia", "test"],
                    })

    click.echo(f"Test run generated {len(facts)} facts")
    if facts:
        inserted = insert_facts_batch(facts)
        click.echo(f"Inserted: {inserted}")

    for f in facts[:10]:
        click.echo(f"  [{f['domain']}] [{f['subdomain']}] {f['fact_text']}")

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
    """Hungary & Georgia wine scraper — genuine external data only."""
    logger.add("data/logs/hungary_georgia_{time}.log", rotation="10 MB")

    if list_sections:
        click.echo("Hungary & Georgia Scraper — Data Sources:")
        click.echo("  1. Wikipedia: Hungarian wine key articles")
        click.echo("     - Tokaj wine region, Tokaji, Furmint, Hárslevelű,")
        click.echo("       Hungarian wine, Bikavér, Villány, Szekszárd, etc.")
        click.echo("  2. Wikipedia categories: Wine regions of Hungary")
        click.echo("  3. Wikipedia: Georgian wine key articles")
        click.echo("     - Georgian wine, Saperavi, Rkatsiteli, Qvevri,")
        click.echo("       Kakheti, Winemaking in Georgia, etc.")
        click.echo("  4. Wikipedia categories: Georgian wine")
        click.echo("  5. Wikidata: Hungary (P17=Q28)")
        click.echo("     - Wine regions, grape varieties, wineries, appellations")
        click.echo("  6. Wikidata: Georgia (P17=Q230)")
        click.echo("     - Wine regions, grape varieties, wineries, appellations")
        return

    if test_run:
        run_test(cleanup=cleanup)
        return

    if not run_all and not dry_run and not validate:
        click.echo("Use --all, --dry-run, --validate, --test-run, or --list")
        return

    # Register sources
    wiki_hungary_sid = ensure_wiki_source("Hungarian wine")
    wiki_georgia_sid = ensure_wiki_source("Georgian wine")
    wikidata_sid = ensure_wikidata_source("Hungarian and Georgian wine")

    # Collect facts
    facts = collect_all_facts(wiki_hungary_sid, wiki_georgia_sid, wikidata_sid)

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
