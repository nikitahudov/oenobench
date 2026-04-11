"""
OenoBench — Croatia & Slovenia Wine Scraper (genuine external data only)

Extracts Croatian and Slovenian wine knowledge from:
  1. Wikipedia — key articles on Croatian/Slovenian wine, regions, grape varieties
  2. Wikipedia categories — "Wine regions of Croatia", "Wine regions of Slovenia"
  3. Wikidata SPARQL — wine regions with P17=Q224 (Croatia) / P17=Q215 (Slovenia),
     grape varieties, wineries, appellations

Every fact traces to a URL that was actually fetched and parsed.
No hardcoded wine knowledge.

Usage:
    python -m src.scrapers.croatia_slovenia --all
    python -m src.scrapers.croatia_slovenia --dry-run
    python -m src.scrapers.croatia_slovenia --validate
    python -m src.scrapers.croatia_slovenia --list
    python -m src.scrapers.croatia_slovenia --test-run
    python -m src.scrapers.croatia_slovenia --test-run --cleanup
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
CROATIA_QID = "Q224"
SLOVENIA_QID = "Q215"

# Region keywords for on-topic filtering
CROATIA_KEYWORDS = {
    "croatia", "croatian", "dalmatia", "dalmatian", "istria", "istrian",
    "slavonia", "slavonian", "zagorje", "moslavina", "plešivica",
    "plesivica", "kutjevo", "ilok", "pelješac", "peljesac",
    "hvar", "brač", "brac", "vis", "korčula", "korcula",
    "plavac mali", "graševina", "grasevina", "malvazija", "malvazija istarska",
    "babić", "babic", "pošip", "posip", "grk", "bogdanuša", "bogdanusa",
    "teran", "debit", "plavina", "žlahtina", "zlahtina",
    "dingač", "dingac", "postup", "primošten", "primosten",
}

SLOVENIA_KEYWORDS = {
    "slovenia", "slovenian", "goriška brda", "goriska brda", "brda",
    "vipava", "karst", "kras", "štajerska", "stajerska",
    "podravje", "posavje", "primorska", "dolenjska",
    "rebula", "zelen", "pinela", "teran", "refošk", "refosk",
    "šipon", "sipon", "ranina", "kraljevina", "cviček", "cvicek",
    "maribor", "old vine", "jeruzalem", "haloze", "ljutomer",
    "ormož", "ormoz", "ptuj",
}

ALL_KEYWORDS = CROATIA_KEYWORDS | SLOVENIA_KEYWORDS


# ─── Wikipedia: Croatia ─────────────────────────────────────────────────────


def _scrape_wikipedia_croatia(session: requests.Session, source_id: str) -> list[dict]:
    """Scrape key Croatian wine articles from Wikipedia."""
    facts = []
    seen = set()

    key_articles = [
        "Croatian wine",
        "Istrian wine",
        "Slavonian wine",
        "Plavac Mali",
        "Graševina",
        "Malvazija istarska",
        "Dingač",
        "Postup",
        "Babić (grape)",
        "Pošip",
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
                region_keywords=CROATIA_KEYWORDS,
            )
            for item in atomic:
                text = item["fact_text"]
                if text.lower() not in seen:
                    seen.add(text.lower())
                    facts.append({
                        "fact_text": text,
                        "domain": item["domain"],
                        "subdomain": "croatia",
                        "source_id": source_id,
                        "entities": [{"type": "region", "name": title}],
                        "confidence": 0.9,
                        "tags": ["croatia", "wikipedia", "key_article"],
                    })

        if wikitext:
            infobox = parse_infobox(wikitext)
            if infobox:
                _extract_infobox_facts(
                    infobox, title, source_id, "croatia", seen, facts,
                    country="Croatia", tags_prefix="croatia",
                )

    return facts


def _scrape_wikipedia_croatia_categories(session: requests.Session, source_id: str) -> list[dict]:
    """Scrape Croatian wine articles from Wikipedia category crawl."""
    facts = []
    seen = set()

    categories = [
        "Category:Wine regions of Croatia",
    ]

    all_titles = set()
    for cat in categories:
        logger.info(f"Crawling category: {cat}")
        titles = crawl_category(session, cat, max_depth=2, max_articles=150)
        all_titles.update(titles)

    logger.info(f"Found {len(all_titles)} Croatian wine articles from categories")

    for title in sorted(all_titles):
        logger.info(f"Fetching: {title}")
        time.sleep(WIKI_REQUEST_DELAY_OVERRIDE)
        extract, wikitext = fetch_article(session, title)

        if extract:
            atomic = extract_atomic_facts(
                extract, title,
                region_keywords=CROATIA_KEYWORDS,
            )
            for item in atomic:
                text = item["fact_text"]
                if text.lower() not in seen:
                    seen.add(text.lower())
                    facts.append({
                        "fact_text": text,
                        "domain": item["domain"],
                        "subdomain": "croatia",
                        "source_id": source_id,
                        "entities": [{"type": "region", "name": title}],
                        "confidence": 0.9,
                        "tags": ["croatia", "wikipedia", "category"],
                    })

        if wikitext:
            infobox = parse_infobox(wikitext)
            if infobox:
                _extract_infobox_facts(
                    infobox, title, source_id, "croatia", seen, facts,
                    country="Croatia", tags_prefix="croatia",
                )

    return facts


# ─── Wikipedia: Slovenia ─────────────────────────────────────────────────────


def _scrape_wikipedia_slovenia(session: requests.Session, source_id: str) -> list[dict]:
    """Scrape key Slovenian wine articles from Wikipedia."""
    facts = []
    seen = set()

    key_articles = [
        "Slovenian wine",
        "Rebula",
        "Teran (wine)",
        "Goriška Brda",
        "Vipava Valley",
        "Cviček",
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
                region_keywords=SLOVENIA_KEYWORDS,
            )
            for item in atomic:
                text = item["fact_text"]
                if text.lower() not in seen:
                    seen.add(text.lower())
                    facts.append({
                        "fact_text": text,
                        "domain": item["domain"],
                        "subdomain": "slovenia",
                        "source_id": source_id,
                        "entities": [{"type": "region", "name": title}],
                        "confidence": 0.9,
                        "tags": ["slovenia", "wikipedia", "key_article"],
                    })

        if wikitext:
            infobox = parse_infobox(wikitext)
            if infobox:
                _extract_infobox_facts(
                    infobox, title, source_id, "slovenia", seen, facts,
                    country="Slovenia", tags_prefix="slovenia",
                )

    return facts


def _scrape_wikipedia_slovenia_categories(session: requests.Session, source_id: str) -> list[dict]:
    """Scrape Slovenian wine articles from Wikipedia category crawl."""
    facts = []
    seen = set()

    categories = [
        "Category:Wine regions of Slovenia",
    ]

    all_titles = set()
    for cat in categories:
        logger.info(f"Crawling category: {cat}")
        titles = crawl_category(session, cat, max_depth=2, max_articles=150)
        all_titles.update(titles)

    logger.info(f"Found {len(all_titles)} Slovenian wine articles from categories")

    for title in sorted(all_titles):
        logger.info(f"Fetching: {title}")
        time.sleep(WIKI_REQUEST_DELAY_OVERRIDE)
        extract, wikitext = fetch_article(session, title)

        if extract:
            atomic = extract_atomic_facts(
                extract, title,
                region_keywords=SLOVENIA_KEYWORDS,
            )
            for item in atomic:
                text = item["fact_text"]
                if text.lower() not in seen:
                    seen.add(text.lower())
                    facts.append({
                        "fact_text": text,
                        "domain": item["domain"],
                        "subdomain": "slovenia",
                        "source_id": source_id,
                        "entities": [{"type": "region", "name": title}],
                        "confidence": 0.9,
                        "tags": ["slovenia", "wikipedia", "category"],
                    })

        if wikitext:
            infobox = parse_infobox(wikitext)
            if infobox:
                _extract_infobox_facts(
                    infobox, title, source_id, "slovenia", seen, facts,
                    country="Slovenia", tags_prefix="slovenia",
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
    click.echo(f"VALIDATION REPORT — Croatia & Slovenia Scraper")
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
    wiki_croatia_sid: str,
    wiki_slovenia_sid: str,
    wikidata_sid: str,
) -> list[dict]:
    """Collect all facts from all sources."""
    session = wiki_session()
    all_facts = []

    # Croatia Wikipedia key articles
    logger.info("--- Wikipedia: Croatia Key Articles ---")
    facts = _scrape_wikipedia_croatia(session, wiki_croatia_sid)
    logger.info(f"Croatia key article facts: {len(facts)}")
    all_facts.extend(facts)

    # Croatia Wikipedia categories
    logger.info("--- Wikipedia: Croatia Categories ---")
    facts = _scrape_wikipedia_croatia_categories(session, wiki_croatia_sid)
    logger.info(f"Croatia category facts: {len(facts)}")
    all_facts.extend(facts)

    # Slovenia Wikipedia key articles
    logger.info("--- Wikipedia: Slovenia Key Articles ---")
    facts = _scrape_wikipedia_slovenia(session, wiki_slovenia_sid)
    logger.info(f"Slovenia key article facts: {len(facts)}")
    all_facts.extend(facts)

    # Slovenia Wikipedia categories
    logger.info("--- Wikipedia: Slovenia Categories ---")
    facts = _scrape_wikipedia_slovenia_categories(session, wiki_slovenia_sid)
    logger.info(f"Slovenia category facts: {len(facts)}")
    all_facts.extend(facts)

    # Wikidata Croatia
    logger.info("--- Wikidata: Croatia ---")
    facts = _scrape_wikidata_country(
        wikidata_sid, CROATIA_QID, "Croatia", "croatia", CROATIA_KEYWORDS)
    logger.info(f"Wikidata Croatia facts: {len(facts)}")
    all_facts.extend(facts)

    # Wikidata Slovenia
    logger.info("--- Wikidata: Slovenia ---")
    facts = _scrape_wikidata_country(
        wikidata_sid, SLOVENIA_QID, "Slovenia", "slovenia", SLOVENIA_KEYWORDS)
    logger.info(f"Wikidata Slovenia facts: {len(facts)}")
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

    logger.info("=== TEST RUN: Croatia & Slovenia Scraper ===")
    wiki_croatia_sid = ensure_wiki_source("Croatian wine")
    wiki_slovenia_sid = ensure_wiki_source("Slovenian wine")

    session = wiki_session()
    test_articles = [
        ("Croatian wine", "croatia", CROATIA_KEYWORDS),
        ("Plavac Mali", "croatia", CROATIA_KEYWORDS),
        ("Graševina", "croatia", CROATIA_KEYWORDS),
        ("Slovenian wine", "slovenia", SLOVENIA_KEYWORDS),
        ("Rebula", "slovenia", SLOVENIA_KEYWORDS),
    ]

    facts = []
    seen = set()
    for title, subdomain, keywords in test_articles[:TEST_RUN_LIMIT]:
        time.sleep(WIKI_REQUEST_DELAY_OVERRIDE)
        extract, wikitext = fetch_article(session, title)
        sid = wiki_croatia_sid if subdomain == "croatia" else wiki_slovenia_sid
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
    """Croatia & Slovenia wine scraper — genuine external data only."""
    logger.add("data/logs/croatia_slovenia_{time}.log", rotation="10 MB")

    if list_sections:
        click.echo("Croatia & Slovenia Scraper — Data Sources:")
        click.echo("  1. Wikipedia: Croatian wine key articles")
        click.echo("     - Croatian wine, Istrian wine, Slavonian wine,")
        click.echo("       Plavac Mali, Graševina, Malvazija istarska, etc.")
        click.echo("  2. Wikipedia categories: Wine regions of Croatia")
        click.echo("  3. Wikipedia: Slovenian wine key articles")
        click.echo("     - Slovenian wine, Rebula, Teran (wine),")
        click.echo("       Goriška Brda, Vipava Valley, Cviček")
        click.echo("  4. Wikipedia categories: Wine regions of Slovenia")
        click.echo("  5. Wikidata: Croatia (P17=Q224)")
        click.echo("     - Wine regions, grape varieties, wineries, appellations")
        click.echo("  6. Wikidata: Slovenia (P17=Q215)")
        click.echo("     - Wine regions, grape varieties, wineries, appellations")
        return

    if test_run:
        run_test(cleanup=cleanup)
        return

    if not run_all and not dry_run and not validate:
        click.echo("Use --all, --dry-run, --validate, --test-run, or --list")
        return

    # Register sources
    wiki_croatia_sid = ensure_wiki_source("Croatian wine")
    wiki_slovenia_sid = ensure_wiki_source("Slovenian wine")
    wikidata_sid = ensure_wikidata_source("Croatian and Slovenian wine")

    # Collect facts
    facts = collect_all_facts(wiki_croatia_sid, wiki_slovenia_sid, wikidata_sid)

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
