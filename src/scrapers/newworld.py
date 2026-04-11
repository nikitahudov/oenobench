"""
OenoBench — New World Wine Regions Scraper (genuine external data only)

Extracts wine data from Australia, New Zealand, and South Africa using:
  1. Wikipedia — key articles on wine regions, grape varieties, producers
  2. Wikipedia categories — "Wine regions of Australia/NZ/SA"
  3. Wikidata SPARQL — wine regions with P17=Q408/Q664/Q258
  4. Official websites — wineaustralia.com, nzwine.com, wosa.co.za

Every fact traces to a URL that was actually fetched and parsed.
No hardcoded wine knowledge.

Usage:
    python -m src.scrapers.newworld --all
    python -m src.scrapers.newworld --country australia
    python -m src.scrapers.newworld --country new-zealand
    python -m src.scrapers.newworld --country south-africa
    python -m src.scrapers.newworld --dry-run
    python -m src.scrapers.newworld --validate
    python -m src.scrapers.newworld --list
    python -m src.scrapers.newworld --test-run
    python -m src.scrapers.newworld --test-run --cleanup
"""

import random
import re
import time
from collections import Counter, defaultdict
from typing import Optional

import click
import requests
from loguru import logger

from src.utils.facts import ensure_source, insert_fact, insert_facts_batch, get_fact_count
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
    WIKI_REQUEST_DELAY as _DEFAULT_WIKI_DELAY,
)

# ─── Configuration ────────────────────────────────────────────────────────────

# Override wiki delay to 5s as required
WIKI_REQUEST_DELAY = 5.0

TEST_RUN_LIMIT = 5
REQUEST_TIMEOUT = 30

COUNTRY_SLUGS = ["australia", "new-zealand", "south-africa"]

# Wikidata QIDs for P17 (country) queries
COUNTRY_QIDS = {
    "australia": "Q408",
    "new-zealand": "Q664",
    "south-africa": "Q258",
}

# ─── Source Definitions ──────────────────────────────────────────────────────

SOURCES = {
    "australia": {
        "name": "Wine Australia",
        "url": "https://www.wineaustralia.com",
        "source_type": "national_wine_body",
        "tier": "tier_2_authoritative",
    },
    "new-zealand": {
        "name": "New Zealand Wine",
        "url": "https://www.nzwine.com",
        "source_type": "national_wine_body",
        "tier": "tier_2_authoritative",
    },
    "south-africa": {
        "name": "Wines of South Africa (WOSA)",
        "url": "https://www.wosa.co.za",
        "source_type": "national_wine_body",
        "tier": "tier_2_authoritative",
    },
}

# ─── Region keywords for on-topic filtering ──────────────────────────────────

AUSTRALIA_KEYWORDS = {
    "australia", "australian", "barossa", "hunter valley", "margaret river",
    "mclaren vale", "yarra valley", "coonawarra", "eden valley", "clare valley",
    "adelaide hills", "tasmania", "tasmanian", "rutherglen", "heathcote",
    "mornington", "geelong", "grampians", "king valley", "beechworth",
    "riverland", "langhorne creek", "padthaway", "wrattonbully",
    "great southern", "pemberton", "swan district", "geographe",
    "mudgee", "orange", "cowra", "canberra district", "tumbarumba",
    "goulburn valley", "bendigo", "pyrenees", "macedon",
    "shiraz", "semillon", "gsm", "geographical indication",
}

NZ_KEYWORDS = {
    "new zealand", "zealand", "marlborough", "hawke's bay", "hawkes bay",
    "central otago", "martinborough", "wairarapa", "waipara", "canterbury",
    "nelson", "gisborne", "auckland", "waiheke", "kumeu", "northland",
    "waikato", "sauvignon blanc", "pinot noir", "gimblett gravels",
    "wairau", "awatere", "bannockburn", "gibbston",
}

SA_KEYWORDS = {
    "south africa", "south african", "stellenbosch", "paarl", "franschhoek",
    "swartland", "constantia", "walker bay", "hemel-en-aarde", "elgin",
    "robertson", "worcester", "darling", "tulbagh", "cederberg",
    "cape south coast", "olifants river", "elim", "cape town",
    "pinotage", "chenin blanc", "steen", "cap classique",
    "wine of origin", "cape blend", "cape winelands",
}

COUNTRY_KEYWORDS = {
    "australia": AUSTRALIA_KEYWORDS,
    "new-zealand": NZ_KEYWORDS,
    "south-africa": SA_KEYWORDS,
}

# ─── Wikipedia Key Articles ──────────────────────────────────────────────────

WIKI_KEY_ARTICLES = {
    "australia": [
        "Australian wine",
        "Barossa Valley (wine region)",
        "Hunter Valley wine region",
        "Margaret River wine region",
        "McLaren Vale",
        "Yarra Valley wine region",
        "Coonawarra wine region",
        "Clare Valley",
        "Eden Valley (wine region)",
        "Adelaide Hills wine region",
        "Tasmania wine",
        "Shiraz",
        "Rutherglen (wine region)",
        "Heathcote (wine region)",
        "King Valley wine region",
    ],
    "new-zealand": [
        "New Zealand wine",
        "Marlborough wine region",
        "Central Otago wine region",
        "Hawke's Bay wine region",
        "Martinborough",
        "Wairarapa wine region",
        "Waipara Valley",
        "Nelson, New Zealand",
        "Gisborne wine region",
        "Waiheke Island wine",
        "Sauvignon blanc",
        "Pinot noir",
    ],
    "south-africa": [
        "South African wine",
        "Stellenbosch wine region",
        "Constantia wine",
        "Pinotage",
        "Chenin blanc",
        "Swartland",
        "Walker Bay wine region",
        "Franschhoek",
        "Paarl wine region",
        "Elgin, Western Cape",
        "Robertson, Western Cape",
        "Cape Winelands",
    ],
}

# ─── Wikipedia Categories ────────────────────────────────────────────────────

WIKI_CATEGORIES = {
    "australia": [
        "Category:Wine regions of Australia",
    ],
    "new-zealand": [
        "Category:Wine regions of New Zealand",
    ],
    "south-africa": [
        "Category:Wine regions of South Africa",
    ],
}

# ─── Official Websites ───────────────────────────────────────────────────────

OFFICIAL_SITES = {
    "australia": {
        "base_url": "https://www.wineaustralia.com",
        "seed_paths": [
            "/growing-making/regions",
            "/growing-making/regions/south-australia",
            "/growing-making/regions/victoria",
            "/growing-making/regions/new-south-wales",
            "/growing-making/regions/western-australia",
        ],
        "max_pages": 30,
        "delay": 5.0,
    },
    "new-zealand": {
        "base_url": "https://www.nzwine.com",
        "seed_paths": [
            "/our-regions",
            "/our-regions/marlborough",
            "/our-regions/hawkes-bay",
            "/our-regions/central-otago",
        ],
        "max_pages": 20,
        "delay": 5.0,
    },
    "south-africa": {
        "base_url": "https://www.wosa.co.za",
        "seed_paths": [
            "/the-industry/wine-regions/",
            "/the-industry/grape-varieties/",
        ],
        "max_pages": 20,
        "delay": 5.0,
    },
}


# ─── Monkey-patch wiki delay ─────────────────────────────────────────────────

import src.scrapers._wiki_helpers as _wh
_wh.WIKI_REQUEST_DELAY = WIKI_REQUEST_DELAY


# ─── Wikipedia Scraping ──────────────────────────────────────────────────────


def _scrape_wikipedia_articles(
    session: requests.Session,
    country_slug: str,
    source_id: str,
) -> list[dict]:
    """Scrape key Wikipedia articles for a country using the atomic fact pipeline."""
    facts = []
    seen = set()
    articles = WIKI_KEY_ARTICLES.get(country_slug, [])
    keywords = COUNTRY_KEYWORDS.get(country_slug, set())
    subdomain = country_slug.replace("-", "_")

    for title in articles:
        logger.info(f"[{country_slug}] Fetching Wikipedia article: {title}")
        extract = fetch_full_extract(session, title)

        if not extract:
            logger.warning(f"[{country_slug}] No extract for: {title}")
            continue

        atomic = extract_atomic_facts(
            extract, title,
            region_keywords=keywords,
        )

        for item in atomic:
            text = item["fact_text"]
            norm = text.lower().strip()
            if norm in seen:
                continue
            seen.add(norm)

            domain = item.get("domain") or classify_domain(text)
            facts.append({
                "fact_text": text,
                "domain": domain,
                "subdomain": subdomain,
                "source_id": source_id,
                "entities": [{"type": "country", "name": country_slug.replace("-", " ").title()}],
                "tags": [subdomain, "wikipedia"],
                "confidence": 0.90,
            })

    logger.info(f"[{country_slug}] Wikipedia articles: {len(facts)} facts from {len(articles)} articles")
    return facts


def _scrape_wikipedia_categories(
    session: requests.Session,
    country_slug: str,
    source_id: str,
) -> list[dict]:
    """Crawl Wikipedia categories for country wine regions and extract facts."""
    facts = []
    seen = set()
    categories = WIKI_CATEGORIES.get(country_slug, [])
    keywords = COUNTRY_KEYWORDS.get(country_slug, set())
    subdomain = country_slug.replace("-", "_")

    for cat in categories:
        logger.info(f"[{country_slug}] Crawling category: {cat}")
        titles = crawl_category(session, cat, max_depth=2, max_articles=80)
        logger.info(f"[{country_slug}] Found {len(titles)} articles in {cat}")

        for title in titles:
            # Skip articles already covered by key articles
            if title in WIKI_KEY_ARTICLES.get(country_slug, []):
                continue

            logger.debug(f"[{country_slug}] Fetching category article: {title}")
            extract = fetch_full_extract(session, title)
            if not extract:
                continue

            # Check wine relevance before full processing
            if not is_wine_relevant(extract[:500]):
                continue

            atomic = extract_atomic_facts(
                extract, title,
                region_keywords=keywords,
            )

            for item in atomic:
                text = item["fact_text"]
                norm = text.lower().strip()
                if norm in seen:
                    continue
                seen.add(norm)

                domain = item.get("domain") or classify_domain(text)
                facts.append({
                    "fact_text": text,
                    "domain": domain,
                    "subdomain": subdomain,
                    "source_id": source_id,
                    "entities": [{"type": "country", "name": country_slug.replace("-", " ").title()}],
                    "tags": [subdomain, "wikipedia_category"],
                    "confidence": 0.85,
                })

    logger.info(f"[{country_slug}] Wikipedia categories: {len(facts)} facts")
    return facts


# ─── Wikidata SPARQL ─────────────────────────────────────────────────────────


def _scrape_wikidata(country_slug: str, source_id: str) -> list[dict]:
    """Query Wikidata for wine regions, wineries, and grape varieties for a country."""
    facts = []
    seen = set()
    qid = COUNTRY_QIDS.get(country_slug)
    if not qid:
        return facts

    keywords = COUNTRY_KEYWORDS.get(country_slug, set())
    subdomain = country_slug.replace("-", "_")
    country_name = country_slug.replace("-", " ").title()

    # --- Wine regions ---
    logger.info(f"[{country_slug}] SPARQL: wine regions (P17={qid})")
    query = SPARQL_WINE_REGIONS_BY_COUNTRY.format(country_qid=qid)
    try:
        rows = run_sparql_filtered(query, expected_country=country_name, region_keywords=keywords)
    except Exception as e:
        logger.warning(f"[{country_slug}] SPARQL wine regions query failed: {e}")
        rows = []

    for row in rows:
        label = row.get("itemLabel", "")
        if not label or label.startswith("Q"):
            continue
        region = row.get("regionLabel", "")
        grape = row.get("grapeLabel", "")
        area = row.get("areaHa", "")

        text = f"{label} is a wine-producing region in {country_name}."
        norm = text.lower().strip()
        if norm not in seen:
            seen.add(norm)
            facts.append({
                "fact_text": text,
                "domain": "wine_regions",
                "subdomain": subdomain,
                "source_id": source_id,
                "entities": [
                    {"type": "region", "name": label},
                    {"type": "country", "name": country_name},
                ],
                "tags": [subdomain, "wikidata"],
                "confidence": 0.90,
            })

        if region and not region.startswith("Q"):
            text2 = f"{label} is located in the {region} area of {country_name}."
            norm2 = text2.lower().strip()
            if norm2 not in seen:
                seen.add(norm2)
                facts.append({
                    "fact_text": text2,
                    "domain": "wine_regions",
                    "subdomain": subdomain,
                    "source_id": source_id,
                    "entities": [
                        {"type": "region", "name": label},
                        {"type": "region", "name": region},
                    ],
                    "tags": [subdomain, "wikidata"],
                    "confidence": 0.85,
                })

        if grape and not grape.startswith("Q"):
            text3 = f"{grape} is a grape variety associated with the {label} wine region."
            norm3 = text3.lower().strip()
            if norm3 not in seen:
                seen.add(norm3)
                facts.append({
                    "fact_text": text3,
                    "domain": "grape_varieties",
                    "subdomain": subdomain,
                    "source_id": source_id,
                    "entities": [
                        {"type": "grape", "name": grape},
                        {"type": "region", "name": label},
                    ],
                    "tags": [subdomain, "wikidata"],
                    "confidence": 0.85,
                })

        if area:
            try:
                area_val = float(area)
                text4 = f"{label} wine region covers approximately {area_val:,.0f} hectares."
                norm4 = text4.lower().strip()
                if norm4 not in seen:
                    seen.add(norm4)
                    facts.append({
                        "fact_text": text4,
                        "domain": "wine_regions",
                        "subdomain": subdomain,
                        "source_id": source_id,
                        "entities": [{"type": "region", "name": label}],
                        "tags": [subdomain, "wikidata"],
                        "confidence": 0.85,
                    })
            except (ValueError, TypeError):
                pass

    # --- Wineries ---
    logger.info(f"[{country_slug}] SPARQL: wineries (P17={qid})")
    query = SPARQL_WINERIES_BY_COUNTRY.format(country_qid=qid)
    try:
        rows = run_sparql_filtered(query, expected_country=country_name, region_keywords=keywords)
    except Exception as e:
        logger.warning(f"[{country_slug}] SPARQL wineries query failed: {e}")
        rows = []

    for row in rows:
        label = row.get("itemLabel", "")
        if not label or label.startswith("Q"):
            continue
        region = row.get("regionLabel", "")
        founded = row.get("founded", "")

        text = f"{label} is a winery in {country_name}."
        if region and not region.startswith("Q"):
            text = f"{label} is a winery located in {region}, {country_name}."

        norm = text.lower().strip()
        if norm not in seen:
            seen.add(norm)
            entities = [
                {"type": "producer", "name": label},
                {"type": "country", "name": country_name},
            ]
            if region and not region.startswith("Q"):
                entities.append({"type": "region", "name": region})

            facts.append({
                "fact_text": text,
                "domain": "producers",
                "subdomain": subdomain,
                "source_id": source_id,
                "entities": entities,
                "tags": [subdomain, "wikidata"],
                "confidence": 0.85,
            })

        if founded:
            year = founded[:4]
            if year.isdigit():
                text2 = f"{label} winery was founded in {year}."
                norm2 = text2.lower().strip()
                if norm2 not in seen:
                    seen.add(norm2)
                    facts.append({
                        "fact_text": text2,
                        "domain": "producers",
                        "subdomain": subdomain,
                        "source_id": source_id,
                        "entities": [{"type": "producer", "name": label}],
                        "tags": [subdomain, "wikidata"],
                        "confidence": 0.85,
                    })

    # --- Grape varieties ---
    logger.info(f"[{country_slug}] SPARQL: grape varieties (P495={qid})")
    query = SPARQL_GRAPE_VARIETIES_BY_COUNTRY.format(country_qid=qid)
    try:
        rows = run_sparql_filtered(query, expected_country=country_name)
    except Exception as e:
        logger.warning(f"[{country_slug}] SPARQL grape varieties query failed: {e}")
        rows = []

    for row in rows:
        label = row.get("itemLabel", "")
        if not label or label.startswith("Q"):
            continue
        color = row.get("colorLabel", "")

        text = f"{label} is a grape variety originating from {country_name}."
        if color and not color.startswith("Q"):
            text = f"{label} is a {color} grape variety originating from {country_name}."

        norm = text.lower().strip()
        if norm not in seen:
            seen.add(norm)
            facts.append({
                "fact_text": text,
                "domain": "grape_varieties",
                "subdomain": subdomain,
                "source_id": source_id,
                "entities": [
                    {"type": "grape", "name": label},
                    {"type": "country", "name": country_name},
                ],
                "tags": [subdomain, "wikidata"],
                "confidence": 0.85,
            })

    logger.info(f"[{country_slug}] Wikidata: {len(facts)} facts total")
    return facts


# ─── Official Website Scraping ───────────────────────────────────────────────


def _scrape_official_site(country_slug: str, source_id: str) -> list[dict]:
    """Scrape text from the official wine body website."""
    facts = []
    seen = set()
    site_config = OFFICIAL_SITES.get(country_slug)
    if not site_config:
        return facts

    keywords = COUNTRY_KEYWORDS.get(country_slug, set())
    subdomain = country_slug.replace("-", "_")
    country_name = country_slug.replace("-", " ").title()

    logger.info(f"[{country_slug}] Scraping official site: {site_config['base_url']}")

    try:
        page_results = scrape_site_texts(
            base_url=site_config["base_url"],
            seed_paths=site_config["seed_paths"],
            max_pages=site_config["max_pages"],
            delay=site_config["delay"],
        )
    except Exception as e:
        logger.warning(f"[{country_slug}] Official site unreachable: {e}")
        return facts

    for url, text_blocks in page_results:
        # Determine page subject from URL path
        path = url.split("/")[-1].replace("-", " ").title() or country_name

        processed = process_facts(
            raw_texts=text_blocks,
            subject=path,
            region_keywords=keywords,
        )

        for item in processed:
            text = item["fact_text"]
            norm = text.lower().strip()
            if norm in seen:
                continue
            seen.add(norm)

            domain = item.get("domain") or classify_domain(text)
            facts.append({
                "fact_text": text,
                "domain": domain,
                "subdomain": subdomain,
                "source_id": source_id,
                "entities": [{"type": "country", "name": country_name}],
                "tags": [subdomain, "official_site"],
                "confidence": 0.80,
            })

    logger.info(f"[{country_slug}] Official site: {len(facts)} facts from {len(page_results)} pages")
    return facts


# ─── Country Dispatch ────────────────────────────────────────────────────────


def _register_source(country_slug: str) -> dict:
    """Register all sources for a country. Returns dict of source_ids."""
    source_ids = {}

    # Wikipedia source
    country_name = country_slug.replace("-", " ").title()
    source_ids["wikipedia"] = ensure_wiki_source(f"{country_name} wine")

    # Wikidata source
    source_ids["wikidata"] = ensure_wikidata_source(f"{country_name} wine")

    # Official site source
    src = SOURCES[country_slug]
    source_ids["official"] = ensure_source(
        name=src["name"],
        url=src["url"],
        source_type=src["source_type"],
        tier=src["tier"],
    )

    return source_ids


def scrape_country(country_slug: str, dry_run: bool = False) -> tuple[int, list[dict]]:
    """Scrape facts for a single country. Returns (count_inserted, facts_list)."""
    if country_slug not in COUNTRY_SLUGS:
        logger.error(f"Unknown country: {country_slug}. Available: {COUNTRY_SLUGS}")
        return 0, []

    if dry_run:
        source_ids = {
            "wikipedia": "dry-run-wiki",
            "wikidata": "dry-run-wikidata",
            "official": "dry-run-official",
        }
    else:
        source_ids = _register_source(country_slug)

    session = wiki_session()
    all_facts = []
    seen_global = set()

    # 1. Wikipedia key articles
    wiki_facts = _scrape_wikipedia_articles(session, country_slug, source_ids["wikipedia"])
    for f in wiki_facts:
        norm = f["fact_text"].lower().strip()
        if norm not in seen_global:
            seen_global.add(norm)
            all_facts.append(f)

    # 2. Wikipedia categories
    cat_facts = _scrape_wikipedia_categories(session, country_slug, source_ids["wikipedia"])
    for f in cat_facts:
        norm = f["fact_text"].lower().strip()
        if norm not in seen_global:
            seen_global.add(norm)
            all_facts.append(f)

    # 3. Wikidata SPARQL
    wd_facts = _scrape_wikidata(country_slug, source_ids["wikidata"])
    for f in wd_facts:
        norm = f["fact_text"].lower().strip()
        if norm not in seen_global:
            seen_global.add(norm)
            all_facts.append(f)

    # 4. Official website
    site_facts = _scrape_official_site(country_slug, source_ids["official"])
    for f in site_facts:
        norm = f["fact_text"].lower().strip()
        if norm not in seen_global:
            seen_global.add(norm)
            all_facts.append(f)

    logger.info(f"[{country_slug}] Total unique facts: {len(all_facts)}")

    if dry_run or not all_facts:
        return 0, all_facts

    inserted = insert_facts_batch(all_facts)
    logger.info(f"[{country_slug}] Inserted {inserted} new facts (of {len(all_facts)} generated)")
    return inserted, all_facts


def scrape_all(dry_run: bool = False) -> dict:
    """Scrape all countries. Returns summary dict."""
    summary = {}
    total_inserted = 0
    total_generated = 0

    for slug in COUNTRY_SLUGS:
        inserted, facts = scrape_country(slug, dry_run=dry_run)
        summary[slug] = {"inserted": inserted, "generated": len(facts)}
        total_inserted += inserted
        total_generated += len(facts)

    summary["_total"] = {"inserted": total_inserted, "generated": total_generated}
    return summary


# ─── Validation ──────────────────────────────────────────────────────────────


def validate_facts() -> None:
    """Run quality checks on all New World facts (dry-run mode)."""
    all_facts = []
    for slug in COUNTRY_SLUGS:
        _, facts = scrape_country(slug, dry_run=True)
        all_facts.extend(facts)

    if not all_facts:
        click.echo("No facts generated. Check scraper logic.")
        return

    domain_counts = defaultdict(int)
    subdomain_counts = defaultdict(int)

    for f in all_facts:
        domain_counts[f["domain"]] += 1
        sd = f.get("subdomain", "unknown")
        subdomain_counts[sd] += 1

    click.echo("\n" + "=" * 60)
    click.echo("  NEW WORLD WINE SCRAPER — VALIDATION REPORT")
    click.echo("=" * 60)

    click.echo(f"\nTotal facts: {len(all_facts)}")
    click.echo("\nDomain distribution:")
    for domain, count in sorted(domain_counts.items()):
        click.echo(f"  {domain:25s}: {count:5d} facts")

    click.echo("\nCountry/subdomain distribution:")
    for sd, count in sorted(subdomain_counts.items()):
        flag = " *** UNDER-SCRAPED ***" if count < 50 else ""
        click.echo(f"  {sd:25s}: {count:5d} facts{flag}")

    # Quality checks
    too_short = []
    too_long = []
    no_predicate = []
    missing_entities = []
    near_dupes = []

    fact_texts = [f["fact_text"] for f in all_facts]

    for i, f in enumerate(all_facts):
        text = f["fact_text"]
        words = text.split()

        if len(words) < 5:
            too_short.append((i, text))
        if len(words) > 50:
            too_long.append((i, text))

        stripped = text.rstrip(".")
        if len(stripped.split()) <= 2 and not any(
            v in text.lower() for v in ["is", "was", "has", "are", "were", "have"]
        ):
            no_predicate.append((i, text))

        entities = f.get("entities", [])
        if not entities:
            missing_entities.append((i, text))

    # Near-duplicate check
    for i in range(len(fact_texts)):
        for j in range(i + 1, min(i + 50, len(fact_texts))):
            t1 = fact_texts[i].lower().rstrip(".")
            t2 = fact_texts[j].lower().rstrip(".")
            if t1 != t2 and (t1 in t2 or t2 in t1):
                near_dupes.append((i, j, fact_texts[i], fact_texts[j]))

    total = len(all_facts)
    click.echo("\nQuality:")
    click.echo(f"  Too short (<5 words):  {len(too_short):5d} ({100*len(too_short)/total:.1f}%)")
    click.echo(f"  Too long (>50 words):  {len(too_long):5d} ({100*len(too_long)/total:.1f}%)")
    click.echo(f"  No predicate:          {len(no_predicate):5d} ({100*len(no_predicate)/total:.1f}%)")
    click.echo(f"  Missing entities:      {len(missing_entities):5d} ({100*len(missing_entities)/total:.1f}%)")
    click.echo(f"  Possible near-dupes:   {len(near_dupes):5d} ({100*len(near_dupes)/total:.1f}%)")

    with_entities = sum(1 for f in all_facts if f.get("entities"))
    click.echo(f"\n  Facts with entities:   {with_entities:5d} ({100*with_entities/total:.1f}%)")
    click.echo(f"  Facts without entities:{total - with_entities:5d} ({100*(total-with_entities)/total:.1f}%)")

    if too_short:
        click.echo("\n  Examples of too-short facts:")
        for idx, text in too_short[:5]:
            click.echo(f'    [{idx}] "{text}"')

    if too_long:
        click.echo("\n  Examples of too-long facts:")
        for idx, text in too_long[:5]:
            click.echo(f'    [{idx}] "{text[:80]}..."')

    if near_dupes:
        click.echo("\n  Examples of near-duplicates:")
        for i, j, t1, t2 in near_dupes[:5]:
            click.echo(f'    [{i}] "{t1}"')
            click.echo(f'    [{j}] "{t2}"')
            click.echo()

    # Random samples
    click.echo("\nSample facts (10 random):")
    samples = random.sample(all_facts, min(10, len(all_facts)))
    for i, f in enumerate(samples, 1):
        click.echo(f'  {i:2d}. "{f["fact_text"]}"')

    click.echo("\n" + "=" * 60)
    click.echo("  Validation complete.")
    click.echo("=" * 60)


# ─── Test Run ────────────────────────────────────────────────────────────────


def run_test(
    country_filter: Optional[str] = None,
    cleanup: bool = False,
) -> None:
    """Run a limited test extraction, insert a few facts, report quality."""
    if country_filter:
        slugs = [country_filter]
    else:
        slugs = list(COUNTRY_SLUGS)

    category_stats = {}
    all_facts_collected = []
    all_inserted_ids = []

    for slug in slugs:
        if slug not in COUNTRY_SLUGS:
            logger.warning(f"Unknown country: {slug}")
            continue

        source_ids = _register_source(slug)

        # Only scrape Wikipedia key articles for speed in test mode
        session = wiki_session()
        # Limit to first 2 articles
        articles = WIKI_KEY_ARTICLES.get(slug, [])[:2]
        temp_facts = []
        seen = set()

        for title in articles:
            logger.info(f"[test:{slug}] Fetching: {title}")
            extract = fetch_full_extract(session, title)
            if not extract:
                continue
            atomic = extract_atomic_facts(
                extract, title,
                region_keywords=COUNTRY_KEYWORDS.get(slug, set()),
            )
            for item in atomic:
                text = item["fact_text"]
                norm = text.lower().strip()
                if norm in seen:
                    continue
                seen.add(norm)
                domain = item.get("domain") or classify_domain(text)
                temp_facts.append({
                    "fact_text": text,
                    "domain": domain,
                    "subdomain": slug.replace("-", "_"),
                    "source_id": source_ids["wikipedia"],
                    "entities": [{"type": "country", "name": slug.replace("-", " ").title()}],
                    "tags": [slug.replace("-", "_"), "wikipedia", "test"],
                    "confidence": 0.90,
                })

        limited_facts = temp_facts[:TEST_RUN_LIMIT]
        inserted_count = 0

        for f in limited_facts:
            fact_id = insert_fact(
                fact_text=f["fact_text"],
                domain=f["domain"],
                source_id=f["source_id"],
                subdomain=f.get("subdomain"),
                entities=f.get("entities"),
                confidence=f.get("confidence", 1.0),
                tags=f.get("tags"),
            )
            if fact_id:
                all_inserted_ids.append(fact_id)
                inserted_count += 1

        all_facts_collected.extend(limited_facts)
        category_stats[slug] = {
            "items_processed": len(articles),
            "facts_generated": len(limited_facts),
            "facts_inserted": inserted_count,
        }

    # Print report
    click.echo("\n=== TEST RUN REPORT ===\n")
    header = (
        f"  {'Source/Category':<25s} {'Items Processed':>17s} "
        f"{'Facts Generated':>17s} {'Facts Inserted (new)':>22s}"
    )
    separator = "  " + "-" * 83
    click.echo(header)
    click.echo(separator)

    total_items = 0
    total_generated = 0
    total_inserted = 0

    for cat_name, stats in category_stats.items():
        items = stats["items_processed"]
        generated = stats["facts_generated"]
        inserted = stats["facts_inserted"]
        total_items += items
        total_generated += generated
        total_inserted += inserted
        click.echo(
            f"  {cat_name:<25s} {items:>17d} {generated:>17d} {inserted:>22d}"
        )

    click.echo(separator)
    click.echo(
        f"  {'TOTAL':<25s} {total_items:>17d} {total_generated:>17d} "
        f"{total_inserted:>22d}"
    )

    if all_facts_collected:
        click.echo(f"\n  Sample Facts ({min(5, len(all_facts_collected))} from this run):")
        for i, f in enumerate(all_facts_collected[:5], 1):
            click.echo(f'    {i:2d}. "{f["fact_text"]}"')

    # Cleanup
    if cleanup and all_inserted_ids:
        from src.utils.db import get_pg
        pg = get_pg()
        cur = pg.cursor()
        cur.execute("DELETE FROM facts WHERE id = ANY(%s::uuid[])", (all_inserted_ids,))
        pg.commit()
        click.echo(f"\n  Cleaned up {len(all_inserted_ids)} test facts from database.")
    elif cleanup:
        click.echo("\n  No facts to clean up.")


# ─── CLI ─────────────────────────────────────────────────────────────────────


@click.command()
@click.option("--all", "run_all", is_flag=True, help="Scrape all New World countries (AU, NZ, SA)")
@click.option(
    "--country", "-c",
    type=click.Choice(COUNTRY_SLUGS, case_sensitive=False),
    help="Scrape a specific country",
)
@click.option("--list", "list_countries", is_flag=True, help="List available countries")
@click.option("--dry-run", is_flag=True, help="Generate facts without inserting into DB")
@click.option("--validate", is_flag=True, help="Run quality validation on generated facts")
@click.option("--test-run", is_flag=True, help="Small test run with limited articles")
@click.option("--cleanup", is_flag=True, help="With --test-run, delete inserted facts after reporting")
def main(
    run_all: bool,
    country: Optional[str],
    list_countries: bool,
    dry_run: bool,
    validate: bool,
    test_run: bool,
    cleanup: bool,
):
    """OenoBench New World Wine Scraper — Extract wine knowledge from AU, NZ, ZA."""
    logger.add("data/logs/newworld_{time}.log", rotation="10 MB")

    if validate:
        validate_facts()
        return

    if test_run:
        run_test(country_filter=country, cleanup=cleanup)
        return

    if list_countries:
        click.echo("\nAvailable countries:")
        for slug in COUNTRY_SLUGS:
            src = SOURCES[slug]
            click.echo(f"  {slug:20s} -- {src['name']} ({src['url']})")
        return

    if run_all:
        click.echo("Scraping all New World wine countries (AU, NZ, ZA)...")
        if dry_run:
            click.echo("(DRY RUN -- no database writes)\n")

        summary = scrape_all(dry_run=dry_run)

        click.echo("\nSummary:")
        click.echo(f"  {'Country':20s} {'Generated':>10s} {'Inserted':>10s}")
        click.echo(f"  {'-'*20} {'-'*10} {'-'*10}")
        for slug in COUNTRY_SLUGS:
            s = summary[slug]
            click.echo(f"  {slug:20s} {s['generated']:10d} {s['inserted']:10d}")
        t = summary["_total"]
        click.echo(f"  {'TOTAL':20s} {t['generated']:10d} {t['inserted']:10d}")

        if not dry_run:
            click.echo(f"\nTotal facts in database: {get_fact_count()}")
        return

    if country:
        click.echo(f"Scraping {country}...")
        if dry_run:
            click.echo("(DRY RUN -- no database writes)\n")

        inserted, facts = scrape_country(country, dry_run=dry_run)
        click.echo(f"\nGenerated {len(facts)} facts, inserted {inserted} new facts for {country}.")

        if not dry_run:
            click.echo(f"Total facts in database: {get_fact_count()}")
        return

    # Default: show help
    click.echo("Use --all to scrape all countries, or --country <name> for a specific one.")
    click.echo("Use --list to see available countries.")
    click.echo("Use --validate to run quality checks on generated facts.")
    click.echo("Use --dry-run to generate facts without database writes.")
    click.echo("Use --test-run to process a small subset and report quality metrics.")


if __name__ == "__main__":
    main()
