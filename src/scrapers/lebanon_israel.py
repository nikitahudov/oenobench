"""
OenoBench — Lebanon & Israel Wine Scraper — genuine external data only

Extracts Lebanese and Israeli wine knowledge from:
  1. Wikipedia — key articles on Lebanese wine, Israeli wine, key producers, regions
  2. Wikipedia categories — "Lebanese wine", "Israeli wine"
  3. Wikidata SPARQL — wine regions with P17=Q822 (Lebanon), P17=Q801 (Israel)

Wikipedia-focused (fewer official sites available for these countries).
Every fact traces to a URL that was actually fetched and parsed.
No hardcoded wine knowledge.

Usage:
    python -m src.scrapers.lebanon_israel --all
    python -m src.scrapers.lebanon_israel --dry-run
    python -m src.scrapers.lebanon_israel --validate
    python -m src.scrapers.lebanon_israel --list
    python -m src.scrapers.lebanon_israel --test-run
    python -m src.scrapers.lebanon_israel --test-run --cleanup
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
    SPARQL_WINERIES_BY_COUNTRY,
    SPARQL_APPELLATIONS_BY_COUNTRY,
    WIKI_REQUEST_DELAY,
)

# ─── Configuration ────────────────────────────────────────────────────────────

TEST_RUN_LIMIT = 5
REQUEST_TIMEOUT = 30

# Override wiki delay for rate limiting
WIKI_REQUEST_DELAY_OVERRIDE = 5.0

# Wikidata QIDs
LEBANON_QID = "Q822"
ISRAEL_QID = "Q801"

# Region keywords for on-topic filtering
LEBANON_KEYWORDS = {
    "lebanon", "lebanese", "bekaa", "beqaa", "baalbek",
    "château musar", "chateau musar", "ksara", "kefraya",
    "mount lebanon", "batroun", "chouf", "zahle", "zahlé",
    "cinsaut", "carignan", "obaideh", "merwah",
    "arak", "phoenician", "union vinicole du liban",
}

ISRAEL_KEYWORDS = {
    "israel", "israeli", "golan heights", "galilee", "judean hills",
    "judean", "negev", "shomron", "samson", "shimshon",
    "carmel winery", "golan heights winery", "barkan", "yarden",
    "kosher", "mevushal", "kashrut",
    "cabernet sauvignon", "carignan", "argaman",
}

LEBANON_ISRAEL_KEYWORDS = LEBANON_KEYWORDS | ISRAEL_KEYWORDS | {
    "eastern mediterranean", "levant", "levantine",
}


# ─── Wikipedia Scraping ──────────────────────────────────────────────────────


def _scrape_wikipedia_key_articles(session: requests.Session, source_id: str) -> list[dict]:
    """Scrape key Lebanon & Israel wine articles from Wikipedia."""
    facts = []
    seen = set()

    key_articles = [
        "Lebanese wine",
        "Château Musar",
        "Bekaa Valley",
        "Israeli wine",
        "Golan Heights Winery",
        "Carmel Winery",
        "Judean Hills",
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
                region_keywords=LEBANON_ISRAEL_KEYWORDS,
            )
            for item in atomic:
                text = item["fact_text"]
                if text.lower() not in seen:
                    seen.add(text.lower())
                    facts.append({
                        "fact_text": text,
                        "domain": item["domain"],
                        "subdomain": "lebanon_israel",
                        "source_id": source_id,
                        "entities": [{"type": "region", "name": title}],
                        "confidence": 0.9,
                        "tags": ["lebanon_israel", "wikipedia", "key_article"],
                    })

        if wikitext:
            infobox = parse_infobox(wikitext)
            if infobox:
                grape = infobox.get("grapes", "") or infobox.get("grape", "")
                area = infobox.get("area", "") or infobox.get("size", "") or infobox.get("hectares", "")
                classification = infobox.get("classification", "") or infobox.get("appellation", "")
                region = infobox.get("region", "") or infobox.get("location", "")
                year = infobox.get("year established", "") or infobox.get("established", "") or infobox.get("founded", "")

                if grape:
                    grapes = [g.strip() for g in re.split(r"[,;]", grape) if g.strip()]
                    for g in grapes[:5]:
                        if 2 < len(g) < 50:
                            text = f"{title} grows the {g} grape variety."
                            if text.lower() not in seen:
                                seen.add(text.lower())
                                facts.append({
                                    "fact_text": text,
                                    "domain": "grape_varieties",
                                    "subdomain": "lebanon_israel",
                                    "source_id": source_id,
                                    "entities": [
                                        {"type": "region", "name": title},
                                        {"type": "grape", "name": g},
                                    ],
                                    "confidence": 0.9,
                                    "tags": ["lebanon_israel", "wikipedia", "grape"],
                                })

                if area and re.search(r"\d", area):
                    text = f"{title} covers approximately {area} hectares."
                    if text.lower() not in seen:
                        seen.add(text.lower())
                        facts.append({
                            "fact_text": text,
                            "domain": classify_domain(text),
                            "subdomain": "lebanon_israel",
                            "source_id": source_id,
                            "entities": [{"type": "region", "name": title}],
                            "confidence": 0.9,
                            "tags": ["lebanon_israel", "wikipedia", "area"],
                        })

                if classification:
                    text = f"{title} holds {classification} classification."
                    if text.lower() not in seen:
                        seen.add(text.lower())
                        facts.append({
                            "fact_text": text,
                            "domain": classify_domain(text),
                            "subdomain": "lebanon_israel",
                            "source_id": source_id,
                            "entities": [{"type": "region", "name": title}],
                            "confidence": 0.9,
                            "tags": ["lebanon_israel", "wikipedia", "classification"],
                        })

                if region and not region.startswith("Q"):
                    text = f"{title} is located in {region}."
                    if text.lower() not in seen:
                        seen.add(text.lower())
                        facts.append({
                            "fact_text": text,
                            "domain": "wine_regions",
                            "subdomain": "lebanon_israel",
                            "source_id": source_id,
                            "entities": [{"type": "region", "name": title}],
                            "confidence": 0.9,
                            "tags": ["lebanon_israel", "wikipedia", "region"],
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
                                "subdomain": "lebanon_israel",
                                "source_id": source_id,
                                "entities": [{"type": "region", "name": title}],
                                "confidence": 0.9,
                                "tags": ["lebanon_israel", "wikipedia", "history"],
                            })

    return facts


def _scrape_wikipedia_categories(session: requests.Session, source_id: str) -> list[dict]:
    """Scrape Lebanon & Israel wine articles from Wikipedia category crawl."""
    facts = []
    seen = set()

    categories = [
        "Category:Lebanese wine",
        "Category:Israeli wine",
    ]

    all_titles = set()
    for cat in categories:
        logger.info(f"Crawling category: {cat}")
        titles = crawl_category(session, cat, max_depth=2, max_articles=100)
        all_titles.update(titles)

    logger.info(f"Found {len(all_titles)} Lebanon/Israel wine articles from categories")

    for title in sorted(all_titles):
        logger.info(f"Fetching: {title}")
        time.sleep(WIKI_REQUEST_DELAY_OVERRIDE)
        extract, wikitext = fetch_article(session, title)

        if extract:
            atomic = extract_atomic_facts(
                extract, title,
                region_keywords=LEBANON_ISRAEL_KEYWORDS,
            )
            for item in atomic:
                text = item["fact_text"]
                if text.lower() not in seen:
                    seen.add(text.lower())
                    facts.append({
                        "fact_text": text,
                        "domain": item["domain"],
                        "subdomain": "lebanon_israel",
                        "source_id": source_id,
                        "entities": [{"type": "region", "name": title}],
                        "confidence": 0.9,
                        "tags": ["lebanon_israel", "wikipedia", "category"],
                    })

        if wikitext:
            infobox = parse_infobox(wikitext)
            if infobox:
                region = infobox.get("region", "") or infobox.get("location", "")
                grape = infobox.get("grapes", "") or infobox.get("grape", "")
                area = infobox.get("area", "") or infobox.get("size", "") or infobox.get("hectares", "")
                year = infobox.get("year established", "") or infobox.get("established", "") or infobox.get("founded", "")

                if region and not region.startswith("Q"):
                    text = f"{title} is located in {region}."
                    if text.lower() not in seen:
                        seen.add(text.lower())
                        facts.append({
                            "fact_text": text,
                            "domain": "wine_regions",
                            "subdomain": "lebanon_israel",
                            "source_id": source_id,
                            "entities": [{"type": "region", "name": title}],
                            "confidence": 0.9,
                            "tags": ["lebanon_israel", "wikipedia", "region"],
                        })

                if grape:
                    grapes = [g.strip() for g in re.split(r"[,;]", grape) if g.strip()]
                    for g in grapes[:5]:
                        if 2 < len(g) < 50:
                            text = f"{title} grows the {g} grape variety."
                            if text.lower() not in seen:
                                seen.add(text.lower())
                                facts.append({
                                    "fact_text": text,
                                    "domain": "grape_varieties",
                                    "subdomain": "lebanon_israel",
                                    "source_id": source_id,
                                    "entities": [
                                        {"type": "region", "name": title},
                                        {"type": "grape", "name": g},
                                    ],
                                    "confidence": 0.9,
                                    "tags": ["lebanon_israel", "wikipedia", "grape"],
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
                                "subdomain": "lebanon_israel",
                                "source_id": source_id,
                                "entities": [{"type": "region", "name": title}],
                                "confidence": 0.9,
                                "tags": ["lebanon_israel", "wikipedia", "area"],
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
                                "subdomain": "lebanon_israel",
                                "source_id": source_id,
                                "entities": [{"type": "region", "name": title}],
                                "confidence": 0.9,
                                "tags": ["lebanon_israel", "wikipedia", "history"],
                            })

    return facts


# ─── Wikidata SPARQL ─────────────────────────────────────────────────────────


def _scrape_wikidata_country(
    source_id: str, country_qid: str, country_name: str,
    region_keywords: set[str], subdomain_tag: str,
) -> list[dict]:
    """Query Wikidata for wine entities in a specific country."""
    facts = []
    seen = set()

    def _add(text, domain="wine_regions", entities=None, tags=None, confidence=0.85):
        if text.lower() in seen:
            return
        seen.add(text.lower())
        facts.append({
            "fact_text": text,
            "domain": domain,
            "subdomain": "lebanon_israel",
            "source_id": source_id,
            "entities": entities or [],
            "confidence": confidence,
            "tags": tags or ["lebanon_israel", "wikidata", subdomain_tag],
        })

    # Wine regions
    try:
        query = SPARQL_WINE_REGIONS_BY_COUNTRY.format(country_qid=country_qid)
        rows = run_sparql_filtered(
            query, expected_country=country_name, region_keywords=region_keywords,
        )
        for row in rows:
            name = row.get("itemLabel", "")
            region = row.get("regionLabel", "")
            area = row.get("areaHa", "")
            if not name or name.startswith("Q"):
                continue
            if region and not region.startswith("Q"):
                _add(
                    f"{name} is a wine region in {region}, {country_name}.",
                    entities=[{"type": "region", "name": name}],
                )
            else:
                _add(
                    f"{name} is a wine region in {country_name}.",
                    entities=[{"type": "region", "name": name}],
                )
            if area and re.search(r"\d", str(area)):
                _add(
                    f"{name} covers approximately {area} hectares.",
                    entities=[{"type": "region", "name": name}],
                    tags=["lebanon_israel", "wikidata", subdomain_tag, "area"],
                )
    except Exception as e:
        logger.warning(f"Wikidata {country_name} regions query failed: {e}")

    # Grape varieties
    try:
        query = SPARQL_GRAPE_VARIETIES_BY_COUNTRY.format(country_qid=country_qid)
        rows = run_sparql_filtered(
            query, expected_country=country_name, region_keywords=region_keywords,
        )
        for row in rows:
            name = row.get("itemLabel", "")
            color = row.get("colorLabel", "")
            if not name or name.startswith("Q"):
                continue
            if color and not color.startswith("Q"):
                _add(
                    f"{name} is a {country_name} {color} grape variety.",
                    domain="grape_varieties",
                    entities=[{"type": "grape", "name": name}],
                    tags=["lebanon_israel", "wikidata", subdomain_tag, "grape"],
                )
            else:
                _add(
                    f"{name} is a grape variety from {country_name}.",
                    domain="grape_varieties",
                    entities=[{"type": "grape", "name": name}],
                    tags=["lebanon_israel", "wikidata", subdomain_tag, "grape"],
                )
    except Exception as e:
        logger.warning(f"Wikidata {country_name} grapes query failed: {e}")

    # Wineries
    try:
        query = SPARQL_WINERIES_BY_COUNTRY.format(country_qid=country_qid)
        rows = run_sparql_filtered(
            query, expected_country=country_name, region_keywords=region_keywords,
        )
        for row in rows:
            name = row.get("itemLabel", "")
            location = row.get("regionLabel", "")
            founded = row.get("founded", "")
            if not name or name.startswith("Q"):
                continue
            if location and not location.startswith("Q"):
                _add(
                    f"{name} is a wine producer in {location}, {country_name}.",
                    domain="producers",
                    entities=[
                        {"type": "producer", "name": name},
                        {"type": "region", "name": location},
                    ],
                    tags=["lebanon_israel", "wikidata", subdomain_tag, "producer"],
                )
            else:
                _add(
                    f"{name} is a wine producer in {country_name}.",
                    domain="producers",
                    entities=[{"type": "producer", "name": name}],
                    tags=["lebanon_israel", "wikidata", subdomain_tag, "producer"],
                )
            if founded:
                year_match = re.search(r"\d{4}", str(founded))
                if year_match:
                    _add(
                        f"{name} was founded in {year_match.group()}.",
                        domain="producers",
                        entities=[{"type": "producer", "name": name}],
                        tags=["lebanon_israel", "wikidata", subdomain_tag, "producer", "history"],
                    )
    except Exception as e:
        logger.warning(f"Wikidata {country_name} producers query failed: {e}")

    # Appellations
    try:
        query = SPARQL_APPELLATIONS_BY_COUNTRY.format(country_qid=country_qid)
        rows = run_sparql_filtered(
            query, expected_country=country_name, region_keywords=region_keywords,
        )
        for row in rows:
            name = row.get("itemLabel", "")
            region = row.get("regionLabel", "")
            if not name or name.startswith("Q"):
                continue
            if region and not region.startswith("Q"):
                _add(
                    f"{name} is a wine appellation in {region}, {country_name}.",
                    domain="wine_regions",
                    entities=[{"type": "appellation", "name": name}],
                    tags=["lebanon_israel", "wikidata", subdomain_tag, "appellation"],
                )
            else:
                _add(
                    f"{name} is a wine appellation in {country_name}.",
                    domain="wine_regions",
                    entities=[{"type": "appellation", "name": name}],
                    tags=["lebanon_israel", "wikidata", subdomain_tag, "appellation"],
                )
    except Exception as e:
        logger.warning(f"Wikidata {country_name} appellations query failed: {e}")

    return facts


def _scrape_wikidata(wikidata_source_id: str) -> list[dict]:
    """Query Wikidata for both Lebanon and Israel wine entities."""
    facts = []

    logger.info("--- Wikidata: Lebanon ---")
    lebanon_facts = _scrape_wikidata_country(
        wikidata_source_id, LEBANON_QID, "Lebanon",
        LEBANON_KEYWORDS, "lebanon",
    )
    logger.info(f"Lebanon Wikidata facts: {len(lebanon_facts)}")
    facts.extend(lebanon_facts)

    logger.info("--- Wikidata: Israel ---")
    israel_facts = _scrape_wikidata_country(
        wikidata_source_id, ISRAEL_QID, "Israel",
        ISRAEL_KEYWORDS, "israel",
    )
    logger.info(f"Israel Wikidata facts: {len(israel_facts)}")
    facts.extend(israel_facts)

    return facts


# ─── Validation ───────────────────────────────────────────────────────────────


def validate_facts(facts: list[dict]) -> None:
    """Run quality checks on extracted facts."""
    click.echo(f"\n{'='*60}")
    click.echo(f"VALIDATION REPORT — Lebanon & Israel Scraper")
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
    for tag, count in tag_counter.most_common(15):
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

    logger.info("=== TEST RUN: Lebanon & Israel Scraper ===")
    wiki_sid = ensure_wiki_source("Lebanese and Israeli wine")
    wikidata_sid = ensure_wikidata_source("Lebanese and Israeli wine")

    session = wiki_session()

    test_articles = ["Lebanese wine", "Château Musar", "Israeli wine",
                     "Golan Heights Winery", "Bekaa Valley"]
    facts = []
    seen = set()
    for title in test_articles[:TEST_RUN_LIMIT]:
        time.sleep(WIKI_REQUEST_DELAY_OVERRIDE)
        extract, wikitext = fetch_article(session, title)
        if extract:
            atomic = extract_atomic_facts(
                extract, title,
                region_keywords=LEBANON_ISRAEL_KEYWORDS,
            )
            for item in atomic[:3]:
                text = item["fact_text"]
                if text.lower() not in seen:
                    seen.add(text.lower())
                    facts.append({
                        "fact_text": text,
                        "domain": item["domain"],
                        "subdomain": "lebanon_israel",
                        "source_id": wiki_sid,
                        "entities": [{"type": "region", "name": title}],
                        "confidence": 0.9,
                        "tags": ["lebanon_israel", "wikipedia", "test"],
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
    """Lebanon & Israel wine scraper — genuine external data only."""
    logger.add("data/logs/lebanon_israel_{time}.log", rotation="10 MB")

    if list_sections:
        click.echo("Lebanon & Israel Scraper — Data Sources:")
        click.echo("  1. Wikipedia: Lebanon & Israel wine key articles & category crawl")
        click.echo("     - Key articles: Lebanese wine, Chateau Musar, Bekaa Valley,")
        click.echo("       Israeli wine, Golan Heights Winery, Carmel Winery, Judean Hills")
        click.echo("     - Categories: Lebanese wine, Israeli wine")
        click.echo("  2. Wikidata: Lebanon & Israel wine entities (SPARQL)")
        click.echo("     - Lebanon: wine regions P17=Q822, grapes P495=Q822, wineries")
        click.echo("     - Israel: wine regions P17=Q801, grapes P495=Q801, wineries")
        return

    if test_run:
        run_test(cleanup=cleanup)
        return

    if not run_all and not dry_run and not validate:
        click.echo("Use --all, --dry-run, --validate, --test-run, or --list")
        return

    # Register sources
    wiki_sid = ensure_wiki_source("Lebanese and Israeli wine")
    wikidata_sid = ensure_wikidata_source("Lebanese and Israeli wine")

    # Collect facts
    facts = collect_all_facts(wiki_sid, wikidata_sid)

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
