"""
OenoBench — Italian Wine Scraper (genuine external data only)

Extracts Italian wine knowledge from:
  1. Wikipedia — key articles on Italian wine, DOCG/DOC appellations, grapes, regions
  2. Wikipedia categories — DOCG wines, DOC wines, wine regions of Italy, Italian grapes
  3. Wikidata SPARQL — wine regions, appellations, wineries with P17=Q38 (Italy)
  4. Official sites — federdoc.com, politicheagricole.it (supplementary)

Every fact traces to a URL that was actually fetched and parsed.
No hardcoded wine knowledge.

Usage:
    python -m src.scrapers.italy --all
    python -m src.scrapers.italy --all --dry-run
    python -m src.scrapers.italy --validate
    python -m src.scrapers.italy --list
    python -m src.scrapers.italy --test-run
    python -m src.scrapers.italy --test-run --cleanup
"""

import random
import re
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
    parse_infobox,
    parse_wikitext_tables,
    extract_lead_sentences,
    extract_atomic_facts,
    run_sparql,
    run_sparql_filtered,
    ensure_wiki_source,
    ensure_wikidata_source,
    clean_wiki_value,
    is_wine_relevant,
    SPARQL_WINE_REGIONS_BY_COUNTRY,
    SPARQL_WINERIES_BY_COUNTRY,
    SPARQL_APPELLATIONS_BY_COUNTRY,
)

# ─── Configuration ────────────────────────────────────────────────────────────

TEST_RUN_LIMIT = 5
FEDERDOC_BASE_URL = "https://www.federdoc.com"
MIPAAF_BASE_URL = "https://www.politicheagricole.it"
WEB_REQUEST_DELAY = 5.0

# Italy = Q38 on Wikidata
ITALY_QID = "Q38"

# Region keywords for on-topic filtering
ITALY_KEYWORDS = {
    "italy", "italian", "italia",
    # Major regions
    "piedmont", "piemonte", "tuscany", "toscana", "veneto", "lombardy",
    "lombardia", "friuli", "trentino", "alto adige", "südtirol",
    "emilia-romagna", "emilia romagna", "umbria", "marche", "lazio",
    "abruzzo", "campania", "puglia", "apulia", "basilicata", "calabria",
    "sicily", "sicilia", "sardinia", "sardegna", "liguria", "molise",
    "valle d'aosta",
    # Key appellations
    "barolo", "barbaresco", "brunello", "chianti", "amarone",
    "prosecco", "franciacorta", "soave", "valpolicella", "montepulciano",
    "bolgheri", "montalcino", "gavi", "asti", "langhe", "roero",
    "etna", "marsala", "lambrusco", "orvieto", "frascati",
    # Classification terms
    "docg", "doc", "igt", "denominazione", "indicazione geografica",
    "consorzio", "disciplinare",
    # Key grapes
    "sangiovese", "nebbiolo", "barbera", "dolcetto", "corvina",
    "garganega", "glera", "trebbiano", "vermentino", "primitivo",
    "nero d'avola", "nerello", "aglianico", "montepulciano",
    "fiano", "greco", "falanghina", "cannonau", "verdicchio",
    "arneis", "cortese", "moscato", "sagrantino", "lagrein",
    "teroldego", "schiava", "ribolla", "friulano", "pinotage",
    # Winemaking terms
    "passito", "recioto", "ripasso", "appassimento", "governo",
    "super tuscan", "vino nobile",
}


# ─── Wikipedia Key Articles ──────────────────────────────────────────────────


def _scrape_wikipedia_key_articles(session: requests.Session, source_id: str) -> list[dict]:
    """Scrape key Italian wine articles from Wikipedia using atomic fact pipeline."""
    facts = []
    seen = set()

    key_articles = [
        "Italian wine",
        "Italian wine classification",
        "Barolo",
        "Chianti",
        "Brunello di Montalcino",
        "Amarone",
        "Prosecco",
        "Franciacorta DOCG",
        "Soave (wine)",
        "Valpolicella",
        "Barbera",
        "Sangiovese",
        "Nebbiolo",
        "Primitivo",
        "Montepulciano (grape)",
        "Vermentino",
        "Pinot grigio",
        "Nero d'Avola",
        "Aglianico",
        "Dolcetto",
        "Lambrusco",
        "Etna DOC",
        "Bolgheri",
        "Super Tuscan",
    ]

    for title in key_articles:
        logger.info(f"Fetching Wikipedia article: {title}")
        extract, wikitext = fetch_article(session, title)

        # Full extract gives more facts than just intro
        full_extract = fetch_full_extract(session, title)
        text_to_process = full_extract or extract

        if text_to_process:
            atomic = extract_atomic_facts(
                text_to_process, title,
                region_keywords=ITALY_KEYWORDS,
            )
            for item in atomic:
                text = item["fact_text"]
                if text.lower() not in seen:
                    seen.add(text.lower())
                    facts.append({
                        "fact_text": text,
                        "domain": item["domain"],
                        "subdomain": "italy",
                        "source_id": source_id,
                        "entities": [{"type": "region", "name": title}],
                        "confidence": 0.9,
                        "tags": ["italy", "wikipedia", "key_article"],
                    })

        if wikitext:
            infobox = parse_infobox(wikitext)
            if infobox:
                _extract_infobox_facts(
                    infobox, title, source_id, facts, seen,
                )

    logger.info(f"Wikipedia key articles: {len(facts)} facts from {len(key_articles)} articles")
    return facts


def _extract_infobox_facts(
    infobox: dict,
    title: str,
    source_id: str,
    facts: list[dict],
    seen: set,
) -> None:
    """Extract structured facts from a Wikipedia infobox."""
    grape = infobox.get("grapes", "") or infobox.get("grape", "")
    area = (
        infobox.get("area", "")
        or infobox.get("size", "")
        or infobox.get("hectares", "")
    )
    classification = (
        infobox.get("classification", "")
        or infobox.get("appellation", "")
        or infobox.get("designation", "")
    )
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
                        "subdomain": "italy",
                        "source_id": source_id,
                        "entities": [
                            {"type": "region", "name": title},
                            {"type": "grape", "name": g},
                        ],
                        "confidence": 0.9,
                        "tags": ["italy", "wikipedia", "grape"],
                    })

    if area and re.search(r"\d", area):
        text = f"{title} covers approximately {area} hectares."
        if text.lower() not in seen:
            seen.add(text.lower())
            facts.append({
                "fact_text": text,
                "domain": classify_domain(text),
                "subdomain": "italy",
                "source_id": source_id,
                "entities": [{"type": "region", "name": title}],
                "confidence": 0.9,
                "tags": ["italy", "wikipedia", "area"],
            })

    if classification:
        text = f"{title} holds {classification} classification in Italy."
        if text.lower() not in seen:
            seen.add(text.lower())
            facts.append({
                "fact_text": text,
                "domain": classify_domain(text),
                "subdomain": "italy",
                "source_id": source_id,
                "entities": [{"type": "region", "name": title}],
                "confidence": 0.9,
                "tags": ["italy", "wikipedia", "classification"],
            })

    if region and not region.startswith("Q"):
        text = f"{title} is a wine appellation in {region}, Italy."
        if text.lower() not in seen:
            seen.add(text.lower())
            facts.append({
                "fact_text": text,
                "domain": "wine_regions",
                "subdomain": "italy",
                "source_id": source_id,
                "entities": [{"type": "region", "name": title}],
                "confidence": 0.9,
                "tags": ["italy", "wikipedia", "region"],
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
                    "subdomain": "italy",
                    "source_id": source_id,
                    "entities": [{"type": "region", "name": title}],
                    "confidence": 0.9,
                    "tags": ["italy", "wikipedia", "history"],
                })


# ─── Wikipedia Category Crawl ───────────────────────────────────────────────


def _scrape_wikipedia_categories(session: requests.Session, source_id: str) -> list[dict]:
    """Scrape Italian wine articles discovered via Wikipedia category crawl."""
    facts = []
    seen = set()

    categories = [
        "Category:DOCG wines",
        "Category:DOC wines",
        "Category:Wine regions of Italy",
        "Category:Italian grape varieties",
        "Category:Italian wine",
    ]

    all_titles = set()
    for cat in categories:
        logger.info(f"Crawling category: {cat}")
        titles = crawl_category(session, cat, max_depth=2, max_articles=100)
        all_titles.update(titles)

    logger.info(f"Found {len(all_titles)} Italian wine-related articles from categories")

    for title in sorted(all_titles):
        logger.info(f"Fetching: {title}")
        extract, wikitext = fetch_article(session, title)

        if extract:
            atomic = extract_atomic_facts(
                extract, title,
                region_keywords=ITALY_KEYWORDS,
            )
            for item in atomic:
                text = item["fact_text"]
                if text.lower() not in seen:
                    seen.add(text.lower())
                    facts.append({
                        "fact_text": text,
                        "domain": item["domain"],
                        "subdomain": "italy",
                        "source_id": source_id,
                        "entities": [{"type": "region", "name": title}],
                        "confidence": 0.9,
                        "tags": ["italy", "wikipedia", "category"],
                    })

        if wikitext:
            infobox = parse_infobox(wikitext)
            if infobox:
                _extract_infobox_facts(
                    infobox, title, source_id, facts, seen,
                )

    logger.info(f"Wikipedia category crawl: {len(facts)} facts")
    return facts


# ─── Wikidata SPARQL ─────────────────────────────────────────────────────────


def _scrape_wikidata(source_id: str) -> list[dict]:
    """Query Wikidata for Italian wine entities using country-scoped SPARQL."""
    facts = []
    seen = set()

    def _add(text, domain="wine_regions", entities=None, tags=None, confidence=0.85):
        if text.lower() in seen:
            return
        seen.add(text.lower())
        facts.append({
            "fact_text": text,
            "domain": domain,
            "subdomain": "italy",
            "source_id": source_id,
            "entities": entities or [],
            "confidence": confidence,
            "tags": tags or ["italy", "wikidata"],
        })

    # Query 1: Wine regions in Italy
    try:
        query = SPARQL_WINE_REGIONS_BY_COUNTRY.format(country_qid=ITALY_QID)
        rows = run_sparql_filtered(
            query,
            expected_country="Italy",
            region_keywords=ITALY_KEYWORDS,
        )
        for row in rows:
            name = row.get("itemLabel", "")
            region = row.get("regionLabel", "")
            area = row.get("areaHa", "")
            grape = row.get("grapeLabel", "")
            if not name or name.startswith("Q"):
                continue
            if region and not region.startswith("Q"):
                _add(
                    f"{name} is a wine region in {region}, Italy.",
                    entities=[{"type": "region", "name": name}],
                )
            else:
                _add(
                    f"{name} is a wine region in Italy.",
                    entities=[{"type": "region", "name": name}],
                )
            if area and re.search(r"\d", str(area)):
                _add(
                    f"{name} covers approximately {area} hectares.",
                    entities=[{"type": "region", "name": name}],
                    tags=["italy", "wikidata", "area"],
                )
            if grape and not grape.startswith("Q"):
                _add(
                    f"{name} is associated with the {grape} grape variety.",
                    domain="grape_varieties",
                    entities=[
                        {"type": "region", "name": name},
                        {"type": "grape", "name": grape},
                    ],
                    tags=["italy", "wikidata", "grape"],
                )
        logger.info(f"Wikidata wine regions: {len([r for r in rows if not r.get('itemLabel', '').startswith('Q')])} results")
    except Exception as e:
        logger.warning(f"Wikidata regions query failed: {e}")

    # Query 2: Italian appellations
    try:
        query = SPARQL_APPELLATIONS_BY_COUNTRY.format(country_qid=ITALY_QID)
        rows = run_sparql_filtered(
            query,
            expected_country="Italy",
            region_keywords=ITALY_KEYWORDS,
        )
        for row in rows:
            name = row.get("itemLabel", "")
            region = row.get("regionLabel", "")
            if not name or name.startswith("Q"):
                continue
            if region and not region.startswith("Q"):
                _add(
                    f"{name} is a wine appellation located in {region}, Italy.",
                    entities=[
                        {"type": "appellation", "name": name},
                        {"type": "region", "name": region},
                    ],
                    tags=["italy", "wikidata", "appellation"],
                )
            else:
                _add(
                    f"{name} is a wine appellation in Italy.",
                    entities=[{"type": "appellation", "name": name}],
                    tags=["italy", "wikidata", "appellation"],
                )
        logger.info(f"Wikidata appellations: {len([r for r in rows if not r.get('itemLabel', '').startswith('Q')])} results")
    except Exception as e:
        logger.warning(f"Wikidata appellations query failed: {e}")

    # Query 3: Italian wineries
    try:
        query = SPARQL_WINERIES_BY_COUNTRY.format(country_qid=ITALY_QID)
        rows = run_sparql_filtered(
            query,
            expected_country="Italy",
            region_keywords=ITALY_KEYWORDS,
        )
        for row in rows:
            name = row.get("itemLabel", "")
            location = row.get("regionLabel", "")
            founded = row.get("founded", "")
            if not name or name.startswith("Q"):
                continue
            if location and not location.startswith("Q"):
                _add(
                    f"{name} is a wine producer in {location}, Italy.",
                    domain="producers",
                    entities=[
                        {"type": "producer", "name": name},
                        {"type": "region", "name": location},
                    ],
                    tags=["italy", "wikidata", "producer"],
                )
            else:
                _add(
                    f"{name} is a wine producer in Italy.",
                    domain="producers",
                    entities=[{"type": "producer", "name": name}],
                    tags=["italy", "wikidata", "producer"],
                )
            if founded and re.search(r"\d{4}", str(founded)):
                year_match = re.search(r"\d{4}", str(founded))
                if year_match:
                    _add(
                        f"{name} winery was founded in {year_match.group()}.",
                        domain="producers",
                        entities=[{"type": "producer", "name": name}],
                        tags=["italy", "wikidata", "producer", "founded"],
                    )
        logger.info(f"Wikidata wineries: {len([r for r in rows if not r.get('itemLabel', '').startswith('Q')])} results")
    except Exception as e:
        logger.warning(f"Wikidata producers query failed: {e}")

    # Query 4: Italian grape varieties by origin
    try:
        sparql_grapes = """
SELECT DISTINCT ?item ?itemLabel ?colorLabel WHERE {{
  ?item wdt:P31/wdt:P279* wd:Q10978 .
  ?item wdt:P495 wd:Q38 .
  OPTIONAL {{ ?item wdt:P462 ?color . }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en" . }}
}}
"""
        rows = run_sparql(sparql_grapes)
        for row in rows:
            name = row.get("itemLabel", "")
            color = row.get("colorLabel", "")
            if not name or name.startswith("Q"):
                continue
            if color and not color.startswith("Q"):
                _add(
                    f"{name} is an Italian {color} grape variety.",
                    domain="grape_varieties",
                    entities=[{"type": "grape", "name": name}],
                    tags=["italy", "wikidata", "grape"],
                )
            else:
                _add(
                    f"{name} is an Italian grape variety.",
                    domain="grape_varieties",
                    entities=[{"type": "grape", "name": name}],
                    tags=["italy", "wikidata", "grape"],
                )
        logger.info(f"Wikidata grape varieties: {len([r for r in rows if not r.get('itemLabel', '').startswith('Q')])} results")
    except Exception as e:
        logger.warning(f"Wikidata grapes query failed: {e}")

    return facts


# ─── Official Sites Scraping ────────────────────────────────────────────────


def _scrape_federdoc(source_id: str) -> list[dict]:
    """Scrape supplementary facts from federdoc.com using shared web helpers."""
    facts = []
    seen = set()

    seed_paths = [
        "/",
        "/new/consorziate/",
        "/new/chi-siamo/",
    ]

    try:
        page_results = scrape_site_texts(
            base_url=FEDERDOC_BASE_URL,
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
            logger.warning("federdoc.com returned no text blocks (may be blocked or down)")
            return facts

        processed = process_facts(
            raw_texts=all_texts,
            subject="Italian wine",
            region_keywords=ITALY_KEYWORDS,
        )

        for item in processed:
            text = item["fact_text"]
            if text.lower() not in seen:
                seen.add(text.lower())
                facts.append({
                    "fact_text": text,
                    "domain": item["domain"],
                    "subdomain": "italy",
                    "source_id": source_id,
                    "entities": [],
                    "confidence": 0.8,
                    "tags": ["italy", "federdoc", "scraped"],
                })

    except Exception as e:
        logger.warning(f"Failed to scrape federdoc.com: {e}")

    logger.info(f"federdoc.com scraping yielded {len(facts)} facts")
    return facts


def _scrape_mipaaf(source_id: str) -> list[dict]:
    """Scrape supplementary facts from politicheagricole.it."""
    facts = []
    seen = set()

    seed_paths = [
        "/flex/cm/pages/ServeBLOB.php/L/IT/IDPagina/4386",
        "/",
    ]

    try:
        page_results = scrape_site_texts(
            base_url=MIPAAF_BASE_URL,
            seed_paths=seed_paths,
            max_pages=15,
            delay=WEB_REQUEST_DELAY,
            min_words=8,
            max_words=60,
        )

        all_texts = []
        for url, blocks in page_results:
            all_texts.extend(blocks)

        if not all_texts:
            logger.warning("politicheagricole.it returned no text blocks (may be blocked or down)")
            return facts

        processed = process_facts(
            raw_texts=all_texts,
            subject="Italian wine regulation",
            region_keywords=ITALY_KEYWORDS,
        )

        for item in processed:
            text = item["fact_text"]
            if text.lower() not in seen:
                seen.add(text.lower())
                facts.append({
                    "fact_text": text,
                    "domain": item["domain"],
                    "subdomain": "italy",
                    "source_id": source_id,
                    "entities": [],
                    "confidence": 0.8,
                    "tags": ["italy", "mipaaf", "scraped"],
                })

    except Exception as e:
        logger.warning(f"Failed to scrape politicheagricole.it: {e}")

    logger.info(f"politicheagricole.it scraping yielded {len(facts)} facts")
    return facts


# ─── Validation ──────────────────────────────────────────────────────────────


def validate_facts(facts: list[dict]) -> None:
    """Run quality checks on extracted facts."""
    click.echo(f"\n{'='*60}")
    click.echo(f"VALIDATION REPORT — Italy Scraper")
    click.echo(f"{'='*60}")
    click.echo(f"Total facts: {len(facts)}")

    # Domain breakdown
    domains = Counter(f["domain"] for f in facts)
    click.echo(f"\nDomain breakdown:")
    for domain, count in domains.most_common():
        click.echo(f"  {domain}: {count}")

    # Source tag breakdown
    tag_counter = Counter()
    for f in facts:
        for t in f.get("tags", []):
            tag_counter[t] += 1
    click.echo(f"\nSource tags (top 15):")
    for tag, count in tag_counter.most_common(15):
        click.echo(f"  {tag}: {count}")

    # Confidence breakdown
    confs = Counter(f.get("confidence", 1.0) for f in facts)
    click.echo(f"\nConfidence breakdown:")
    for conf, count in sorted(confs.items(), reverse=True):
        click.echo(f"  {conf}: {count}")

    # Length checks
    short = [f for f in facts if len(f["fact_text"].split()) < 5]
    long = [f for f in facts if len(f["fact_text"].split()) > 50]
    click.echo(f"\nShort facts (<5 words): {len(short)}")
    click.echo(f"Long facts (>50 words): {len(long)}")
    for f in short[:5]:
        click.echo(f"  SHORT: {f['fact_text']}")
    for f in long[:5]:
        click.echo(f"  LONG: {f['fact_text']}")

    # Near-duplicate check (sampled)
    texts = [f["fact_text"].lower() for f in facts]
    dupes = 0
    sample = texts[:200]
    for i, t1 in enumerate(sample):
        for t2 in sample[i + 1:]:
            if len(t1) > 20 and (t1 in t2 or t2 in t1):
                dupes += 1
    click.echo(f"\nNear-duplicate pairs (substring, sampled): {dupes}")

    # Entity coverage
    with_entities = sum(1 for f in facts if f.get("entities"))
    click.echo(f"\nFacts with entities: {with_entities}/{len(facts)} ({100*with_entities//max(len(facts),1)}%)")

    # Sample facts
    click.echo(f"\n10 random sample facts:")
    for f in random.sample(facts, min(10, len(facts))):
        click.echo(f"  [{f['domain']}] (conf={f.get('confidence', 1.0)}) {f['fact_text']}")


# ─── Main Collection ─────────────────────────────────────────────────────────


def collect_all_facts(
    wiki_source_id: str,
    wikidata_source_id: str,
    federdoc_source_id: str,
    mipaaf_source_id: str,
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

    # Wikidata SPARQL
    logger.info("--- Wikidata SPARQL ---")
    wikidata_facts = _scrape_wikidata(wikidata_source_id)
    logger.info(f"Wikidata facts: {len(wikidata_facts)}")
    all_facts.extend(wikidata_facts)

    # Official sites
    if scrape_web:
        logger.info("--- federdoc.com ---")
        federdoc_facts = _scrape_federdoc(federdoc_source_id)
        logger.info(f"federdoc.com facts: {len(federdoc_facts)}")
        all_facts.extend(federdoc_facts)

        logger.info("--- politicheagricole.it ---")
        mipaaf_facts = _scrape_mipaaf(mipaaf_source_id)
        logger.info(f"politicheagricole.it facts: {len(mipaaf_facts)}")
        all_facts.extend(mipaaf_facts)

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

    logger.info("=== TEST RUN: Italy Scraper ===")
    wiki_sid = ensure_wiki_source("Italian wine")
    session = wiki_session()

    test_articles = ["Italian wine", "Barolo", "Chianti", "Sangiovese", "Prosecco"]
    facts = []
    seen = set()

    for title in test_articles[:TEST_RUN_LIMIT]:
        extract, wikitext = fetch_article(session, title)
        if extract:
            atomic = extract_atomic_facts(
                extract, title,
                region_keywords=ITALY_KEYWORDS,
            )
            for item in atomic[:3]:
                text = item["fact_text"]
                if text.lower() not in seen:
                    seen.add(text.lower())
                    facts.append({
                        "fact_text": text,
                        "domain": item["domain"],
                        "subdomain": "italy",
                        "source_id": wiki_sid,
                        "entities": [{"type": "region", "name": title}],
                        "confidence": 0.9,
                        "tags": ["italy", "wikipedia", "test"],
                    })

    click.echo(f"\nTest run generated {len(facts)} facts")
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


# ─── CLI ─────────────────────────────────────────────────────────────────────


@click.command()
@click.option("--all", "run_all", is_flag=True, help="Run full extraction and insert into database")
@click.option("--list", "list_sections", is_flag=True, help="List available data sources")
@click.option("--dry-run", "dry_run", is_flag=True, help="Collect facts but don't insert into database")
@click.option("--validate", "validate_flag", is_flag=True, help="Run quality checks on generated facts")
@click.option("--test-run", is_flag=True, help="Process a small sample, insert, and report")
@click.option("--cleanup", is_flag=True, help="With --test-run, delete inserted facts after reporting")
def main(run_all, list_sections, dry_run, validate_flag, test_run, cleanup):
    """OenoBench Italian Wine Scraper — genuine external data only."""
    logger.add("data/logs/italy_{time}.log", rotation="10 MB")

    if list_sections:
        click.echo("Italy Scraper — Data Sources:")
        click.echo("  1. Wikipedia: Italian wine key articles (24 articles)")
        click.echo("     - Italian wine, Barolo, Chianti, Brunello, Amarone, etc.")
        click.echo("  2. Wikipedia: Category crawl")
        click.echo("     - DOCG wines, DOC wines, Wine regions of Italy, Italian grape varieties")
        click.echo("  3. Wikidata: Italian wine entities (SPARQL)")
        click.echo("     - Wine regions with P17=Q38 (country=Italy)")
        click.echo("     - Appellations with P17=Q38")
        click.echo("     - Wineries with P17=Q38")
        click.echo("     - Grape varieties with P495=Q38 (origin=Italy)")
        click.echo("  4. federdoc.com: Italian wine consortiums")
        click.echo("  5. politicheagricole.it: Italian wine regulations")
        return

    if test_run:
        run_test(cleanup=cleanup)
        return

    if not run_all and not dry_run and not validate_flag:
        click.echo("Use --all, --dry-run, --validate, --test-run, or --list")
        return

    # Register sources
    wiki_sid = ensure_wiki_source("Italian wine")
    wikidata_sid = ensure_wikidata_source("Italian wine")
    federdoc_sid = ensure_source(
        name="Federdoc — Italian Wine Consortiums Federation",
        url="https://www.federdoc.com",
        source_type="consortium",
        tier="tier_2_authoritative",
        language="it",
    )
    mipaaf_sid = ensure_source(
        name="Italian Ministry of Agriculture (MASAF)",
        url="https://www.politicheagricole.it",
        source_type="government",
        tier="tier_1_official",
        language="it",
    )

    # Collect facts
    facts = collect_all_facts(wiki_sid, wikidata_sid, federdoc_sid, mipaaf_sid)

    if validate_flag or dry_run:
        validate_facts(facts)

    if dry_run:
        click.echo(f"\nDRY RUN — {len(facts)} facts generated, not inserted")
        return

    if run_all:
        before = get_fact_count()
        inserted = insert_facts_batch(facts)
        after = get_fact_count()
        click.echo(f"\nInserted {inserted} new facts (DB: {before} -> {after})")


if __name__ == "__main__":
    main()
