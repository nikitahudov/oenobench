"""
OenoBench — French Regional Wine Scraper: Rhone, Loire, Alsace (genuine data only)

Extracts wine knowledge from:
  1. Wikipedia — key articles on Rhone, Loire, Alsace wine regions, grapes, appellations
  2. Wikipedia categories — crawl wine category trees for each region
  3. Wikidata SPARQL — wine regions, grape varieties, wineries with P17=Q142 (France)
  4. Official sites — inter-rhone.com, vinsdeloire.fr via _web_helpers.py

Every fact traces to a URL that was actually fetched and parsed.
No hardcoded wine knowledge.

Usage:
    python -m src.scrapers.rhone_loire_alsace --all
    python -m src.scrapers.rhone_loire_alsace --type rhone
    python -m src.scrapers.rhone_loire_alsace --type loire
    python -m src.scrapers.rhone_loire_alsace --type alsace
    python -m src.scrapers.rhone_loire_alsace --dry-run
    python -m src.scrapers.rhone_loire_alsace --validate
    python -m src.scrapers.rhone_loire_alsace --test-run
    python -m src.scrapers.rhone_loire_alsace --test-run --cleanup
    python -m src.scrapers.rhone_loire_alsace --list
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

# Override default 2s delay — Wikipedia rate-limits aggressively
import src.scrapers._wiki_helpers as _wiki_mod
_wiki_mod.WIKI_REQUEST_DELAY = 10.0

TEST_RUN_LIMIT = 5
FRANCE_QID = "Q142"
WEB_REQUEST_DELAY = 5.0

# ─── Region Keywords (for on-topic filtering) ────────────────────────────────

RHONE_KEYWORDS = {
    "rhône", "rhone", "northern rhône", "southern rhône",
    "côte-rôtie", "cote-rotie", "côte rôtie", "condrieu", "hermitage",
    "crozes-hermitage", "saint-joseph", "cornas", "châteauneuf-du-pape",
    "chateauneuf-du-pape", "gigondas", "vacqueyras", "beaumes-de-venise",
    "côtes du rhône", "cotes du rhone", "lirac", "tavel", "rasteau",
    "vinsobres", "cairanne", "laudun", "visan",
    "syrah", "grenache", "mourvèdre", "viognier", "marsanne",
    "roussanne", "clairette", "bourboulenc", "cinsault",
    "inter-rhône", "inter-rhone",
}

LOIRE_KEYWORDS = {
    "loire", "sancerre", "vouvray", "muscadet", "chinon", "bourgueil",
    "touraine", "anjou", "saumur", "savennières", "savennieres",
    "pouilly-fumé", "pouilly fume", "montlouis", "bonnezeaux",
    "quarts de chaume", "coteaux du layon", "jasnières", "jasnieres",
    "menetou-salon", "reuilly", "quincy", "valencay",
    "chenin blanc", "cabernet franc", "melon de bourgogne",
    "sauvignon blanc", "groslot", "pineau d'aunis",
    "vins de loire", "vinsdeloire",
}

ALSACE_KEYWORDS = {
    "alsace", "alsatian", "grand cru", "vendange tardive", "vendanges tardives",
    "sélection de grains nobles", "selection de grains nobles",
    "gewürztraminer", "gewurztraminer", "riesling", "pinot gris",
    "pinot blanc", "muscat", "sylvaner", "klevener", "crémant d'alsace",
    "cremant d'alsace", "edelzwicker",
    "haut-rhin", "bas-rhin", "colmar", "strasbourg", "ribeauvillé",
    "riquewihr", "kaysersberg", "turckheim",
}

ALL_KEYWORDS = RHONE_KEYWORDS | LOIRE_KEYWORDS | ALSACE_KEYWORDS


# ─── Wikipedia: Key Articles ──────────────────────────────────────────────────


RHONE_ARTICLES = [
    "Rhône wine",
    "Northern Rhône",
    "Southern Rhône",
    "Côtes du Rhône AOC",
    "Hermitage AOC",
    "Châteauneuf-du-Pape AOC",
    "Côte-Rôtie AOC",
    "Condrieu AOC",
    "Crozes-Hermitage AOC",
    "Saint-Joseph AOC",
    "Cornas AOC",
    "Gigondas AOC",
    "Vacqueyras AOC",
    "Tavel AOC",
    "Syrah",
    "Viognier",
]

LOIRE_ARTICLES = [
    "Loire wine",
    "Sancerre AOC",
    "Vouvray AOC",
    "Muscadet",
    "Chinon AOC",
    "Bourgueil AOC",
    "Touraine AOC",
    "Anjou AOC",
    "Saumur (wine)",
    "Savennières",
    "Pouilly-Fumé AOC",
    "Coteaux du Layon",
    "Chenin blanc",
]

ALSACE_ARTICLES = [
    "Alsace wine",
    "Alsace grand cru",
    "Gewürztraminer",
    "Crémant d'Alsace",
    "Alsace AOC",
]


def _scrape_wikipedia_key_articles(
    session: requests.Session,
    source_id: str,
    articles: list[str],
    region_keywords: set[str],
    subdomain: str,
    tags_prefix: str,
) -> list[dict]:
    """Scrape key Wikipedia articles for a specific sub-region."""
    facts = []
    seen = set()

    for title in articles:
        logger.info(f"Fetching Wikipedia article: {title}")
        extract, wikitext = fetch_article(session, title)

        if extract:
            atomic = extract_atomic_facts(
                extract, title,
                region_keywords=region_keywords,
            )
            for item in atomic:
                text = item["fact_text"]
                if text.lower() not in seen:
                    seen.add(text.lower())
                    facts.append({
                        "fact_text": text,
                        "domain": item["domain"],
                        "subdomain": subdomain,
                        "source_id": source_id,
                        "entities": [{"type": "region", "name": title}],
                        "confidence": 0.9,
                        "tags": [tags_prefix, "wikipedia", "key_article"],
                    })

        if wikitext:
            infobox = parse_infobox(wikitext)
            if infobox:
                _extract_infobox_facts(
                    infobox, title, source_id, subdomain,
                    tags_prefix, seen, facts,
                )

    logger.info(f"Key article facts for {subdomain}: {len(facts)}")
    return facts


def _extract_infobox_facts(
    infobox: dict, title: str, source_id: str, subdomain: str,
    tags_prefix: str, seen: set, facts: list,
) -> None:
    """Extract structured facts from a Wikipedia infobox."""
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
        area_clean = re.sub(r"[^\d.,]", " ", area).strip()
        if area_clean:
            text = f"{title} covers approximately {area_clean} hectares."
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
        text = f"{title} is a wine appellation in the {region} region of France."
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
            text = f"{title} appellation was established in {year_match.group()}."
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


# ─── Wikipedia: Category Crawl ──────────────────────────────────────────────


RHONE_CATEGORIES = [
    "Category:Rhône wine",
    "Category:Rhône wine AOCs",
    "Category:Northern Rhône wine AOCs",
    "Category:Southern Rhône wine AOCs",
]

LOIRE_CATEGORIES = [
    "Category:Loire wine",
    "Category:Loire wine AOCs",
]

ALSACE_CATEGORIES = [
    "Category:Alsace wine",
    "Category:Alsace wine AOCs",
    "Category:Alsace grand cru vineyards",
]


def _scrape_wikipedia_categories(
    session: requests.Session,
    source_id: str,
    categories: list[str],
    region_keywords: set[str],
    subdomain: str,
    tags_prefix: str,
    already_seen: set,
) -> list[dict]:
    """Crawl Wikipedia categories and extract facts from discovered articles."""
    facts = []
    seen = set(already_seen)

    all_titles = set()
    for cat in categories:
        logger.info(f"Crawling category: {cat}")
        titles = crawl_category(session, cat, max_depth=2, max_articles=100)
        all_titles.update(titles)

    logger.info(f"Found {len(all_titles)} articles from categories for {subdomain}")

    for title in sorted(all_titles):
        logger.info(f"Fetching: {title}")
        extract, wikitext = fetch_article(session, title)

        if extract:
            atomic = extract_atomic_facts(
                extract, title,
                region_keywords=region_keywords,
            )
            for item in atomic:
                text = item["fact_text"]
                if text.lower() not in seen:
                    seen.add(text.lower())
                    facts.append({
                        "fact_text": text,
                        "domain": item["domain"],
                        "subdomain": subdomain,
                        "source_id": source_id,
                        "entities": [{"type": "region", "name": title}],
                        "confidence": 0.9,
                        "tags": [tags_prefix, "wikipedia", "category"],
                    })

        if wikitext:
            infobox = parse_infobox(wikitext)
            if infobox:
                _extract_infobox_facts(
                    infobox, title, source_id, subdomain,
                    tags_prefix, seen, facts,
                )

    logger.info(f"Category facts for {subdomain}: {len(facts)}")
    return facts


# ─── Wikidata SPARQL ─────────────────────────────────────────────────────────


def _row_matches_region(row: dict, region_keywords: set[str]) -> bool:
    """Check if a SPARQL result row matches region keywords (strict).

    Requires at least one region keyword to appear in any label field.
    This is stricter than is_on_topic() which allows neutral results through.
    """
    labels = " ".join(
        v for k, v in row.items()
        if k.endswith("Label") and v and not v.startswith("Q")
    ).lower()
    return any(kw in labels for kw in region_keywords)


def _scrape_wikidata_for_region(
    source_id: str,
    region_keywords: set[str],
    subdomain: str,
    tags_prefix: str,
) -> list[dict]:
    """Query Wikidata for wine entities in France, filtered by region keywords."""
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
            "tags": tags or [tags_prefix, "wikidata"],
        })

    # Wine regions in France, filtered by sub-region keywords
    try:
        query = SPARQL_WINE_REGIONS_BY_COUNTRY.format(country_qid=FRANCE_QID)
        rows = run_sparql_filtered(
            query,
            expected_country="France",
            region_keywords=region_keywords,
        )
        for row in rows:
            if not _row_matches_region(row, region_keywords):
                continue
            name = row.get("itemLabel", "")
            region = row.get("regionLabel", "")
            area = row.get("areaHa", "")
            if not name or name.startswith("Q"):
                continue
            if region and not region.startswith("Q"):
                _add(
                    f"{name} is a wine region in {region}, France.",
                    entities=[{"type": "region", "name": name}],
                )
            else:
                _add(
                    f"{name} is a wine region in France.",
                    entities=[{"type": "region", "name": name}],
                )
            if area and re.search(r"\d", str(area)):
                _add(
                    f"{name} covers approximately {area} hectares.",
                    entities=[{"type": "region", "name": name}],
                    tags=[tags_prefix, "wikidata", "area"],
                )
    except Exception as e:
        logger.warning(f"Wikidata regions query failed for {subdomain}: {e}")

    # Appellations in France, filtered
    try:
        query = SPARQL_APPELLATIONS_BY_COUNTRY.format(country_qid=FRANCE_QID)
        rows = run_sparql_filtered(
            query,
            expected_country="France",
            region_keywords=region_keywords,
        )
        for row in rows:
            if not _row_matches_region(row, region_keywords):
                continue
            name = row.get("itemLabel", "")
            region = row.get("regionLabel", "")
            if not name or name.startswith("Q"):
                continue
            if region and not region.startswith("Q"):
                _add(
                    f"{name} is an appellation in the {region} region of France.",
                    entities=[{"type": "region", "name": name}],
                    tags=[tags_prefix, "wikidata", "appellation"],
                )
            else:
                _add(
                    f"{name} is an appellation in France.",
                    entities=[{"type": "region", "name": name}],
                    tags=[tags_prefix, "wikidata", "appellation"],
                )
    except Exception as e:
        logger.warning(f"Wikidata appellations query failed for {subdomain}: {e}")

    # Wineries in France, filtered
    try:
        query = SPARQL_WINERIES_BY_COUNTRY.format(country_qid=FRANCE_QID)
        rows = run_sparql_filtered(
            query,
            expected_country="France",
            region_keywords=region_keywords,
        )
        for row in rows:
            if not _row_matches_region(row, region_keywords):
                continue
            name = row.get("itemLabel", "")
            location = row.get("regionLabel", "")
            if not name or name.startswith("Q"):
                continue
            if location and not location.startswith("Q"):
                _add(
                    f"{name} is a wine producer in {location}, France.",
                    domain="producers",
                    entities=[
                        {"type": "producer", "name": name},
                        {"type": "region", "name": location},
                    ],
                    tags=[tags_prefix, "wikidata", "producer"],
                )
            else:
                _add(
                    f"{name} is a wine producer in France.",
                    domain="producers",
                    entities=[{"type": "producer", "name": name}],
                    tags=[tags_prefix, "wikidata", "producer"],
                )
    except Exception as e:
        logger.warning(f"Wikidata producers query failed for {subdomain}: {e}")

    logger.info(f"Wikidata facts for {subdomain}: {len(facts)}")
    return facts


# ─── Official Website Scraping ───────────────────────────────────────────────


def _scrape_inter_rhone(source_id: str) -> list[dict]:
    """Scrape supplementary facts from inter-rhone.com."""
    facts = []
    seen = set()

    seed_paths = [
        "/en/rhone-valley-wines",
        "/en/the-rhone-valley",
        "/en/the-appellations",
        "/en/grape-varieties",
    ]

    try:
        page_results = scrape_site_texts(
            base_url="https://www.inter-rhone.com",
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
            logger.warning("inter-rhone.com returned no text blocks (may be blocked)")
            return facts

        processed = process_facts(
            raw_texts=all_texts,
            subject="Rhône Valley wine",
            region_keywords=RHONE_KEYWORDS,
        )

        for item in processed:
            text = item["fact_text"]
            if text.lower() not in seen:
                seen.add(text.lower())
                facts.append({
                    "fact_text": text,
                    "domain": item["domain"],
                    "subdomain": "rhone",
                    "source_id": source_id,
                    "entities": [],
                    "confidence": 0.8,
                    "tags": ["rhone", "inter-rhone", "scraped"],
                })

    except Exception as e:
        logger.warning(f"Failed to scrape inter-rhone.com: {e}")

    logger.info(f"inter-rhone.com scraping yielded {len(facts)} facts")
    return facts


def _scrape_vinsdeloire(source_id: str) -> list[dict]:
    """Scrape supplementary facts from vinsdeloire.fr."""
    facts = []
    seen = set()

    seed_paths = [
        "/en/discover-the-wines",
        "/en/the-loire-valley",
        "/en/appellations",
        "/en/grape-varieties",
    ]

    try:
        page_results = scrape_site_texts(
            base_url="https://www.vinsdeloire.fr",
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
            logger.warning("vinsdeloire.fr returned no text blocks (may be blocked)")
            return facts

        processed = process_facts(
            raw_texts=all_texts,
            subject="Loire Valley wine",
            region_keywords=LOIRE_KEYWORDS,
        )

        for item in processed:
            text = item["fact_text"]
            if text.lower() not in seen:
                seen.add(text.lower())
                facts.append({
                    "fact_text": text,
                    "domain": item["domain"],
                    "subdomain": "loire",
                    "source_id": source_id,
                    "entities": [],
                    "confidence": 0.8,
                    "tags": ["loire", "vinsdeloire", "scraped"],
                })

    except Exception as e:
        logger.warning(f"Failed to scrape vinsdeloire.fr: {e}")

    logger.info(f"vinsdeloire.fr scraping yielded {len(facts)} facts")
    return facts


# ─── Validation ──────────────────────────────────────────────────────────────


def validate_facts(facts: list[dict]) -> None:
    """Run quality checks on extracted facts."""
    click.echo(f"\n{'='*60}")
    click.echo("VALIDATION REPORT — Rhône/Loire/Alsace Scraper")
    click.echo(f"{'='*60}")
    click.echo(f"Total facts: {len(facts)}")

    # Domain breakdown
    domains = Counter(f["domain"] for f in facts)
    click.echo("\nDomain breakdown:")
    for domain, count in domains.most_common():
        click.echo(f"  {domain}: {count}")

    # Subdomain breakdown
    subdomains = Counter(f.get("subdomain", "unknown") for f in facts)
    click.echo("\nSubdomain breakdown:")
    for sd, count in subdomains.most_common():
        click.echo(f"  {sd}: {count}")

    # Confidence breakdown
    confs = Counter(f.get("confidence", 1.0) for f in facts)
    click.echo("\nConfidence breakdown:")
    for conf, count in sorted(confs.items(), reverse=True):
        click.echo(f"  {conf}: {count}")

    # Source tag breakdown
    tag_counter = Counter()
    for f in facts:
        for t in f.get("tags", []):
            tag_counter[t] += 1
    click.echo("\nSource tags:")
    for tag, count in tag_counter.most_common(15):
        click.echo(f"  {tag}: {count}")

    # Length checks
    short = [f for f in facts if len(f["fact_text"].split()) < 5]
    long_f = [f for f in facts if len(f["fact_text"].split()) > 50]
    click.echo(f"\nShort facts (<5 words): {len(short)}")
    click.echo(f"Long facts (>50 words): {len(long_f)}")
    for f in short[:5]:
        click.echo(f"  SHORT: {f['fact_text']}")
    for f in long_f[:5]:
        click.echo(f"  LONG: {f['fact_text']}")

    # Near-duplicate check (sampled)
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

    # 10 random samples
    click.echo("\n10 random sample facts:")
    for f in random.sample(facts, min(10, len(facts))):
        click.echo(f"  [{f['domain']}] [{f.get('subdomain','')}] (conf={f.get('confidence',1.0)}) {f['fact_text']}")


# ─── Collection Orchestration ────────────────────────────────────────────────


def _collect_region(
    session: requests.Session,
    wiki_source_id: str,
    wikidata_source_id: str,
    articles: list[str],
    categories: list[str],
    region_keywords: set[str],
    subdomain: str,
    tags_prefix: str,
) -> list[dict]:
    """Collect facts for a single sub-region from Wikipedia + Wikidata."""
    all_facts = []
    seen_texts = set()

    # Wikipedia key articles
    logger.info(f"--- Wikipedia key articles: {subdomain} ---")
    key_facts = _scrape_wikipedia_key_articles(
        session, wiki_source_id, articles, region_keywords, subdomain, tags_prefix,
    )
    for f in key_facts:
        seen_texts.add(f["fact_text"].lower())
    all_facts.extend(key_facts)

    # Wikipedia category crawl
    logger.info(f"--- Wikipedia categories: {subdomain} ---")
    cat_facts = _scrape_wikipedia_categories(
        session, wiki_source_id, categories, region_keywords,
        subdomain, tags_prefix, seen_texts,
    )
    for f in cat_facts:
        seen_texts.add(f["fact_text"].lower())
    all_facts.extend(cat_facts)

    # Wikidata SPARQL
    logger.info(f"--- Wikidata SPARQL: {subdomain} ---")
    wd_facts = _scrape_wikidata_for_region(
        wikidata_source_id, region_keywords, subdomain, tags_prefix,
    )
    # Dedup against Wikipedia facts
    for f in wd_facts:
        if f["fact_text"].lower() not in seen_texts:
            seen_texts.add(f["fact_text"].lower())
            all_facts.append(f)

    logger.info(f"Total facts for {subdomain}: {len(all_facts)}")
    return all_facts


def collect_all_facts(
    data_type: Optional[str] = None,
    scrape_web: bool = True,
) -> list[dict]:
    """Collect all facts from all sources for selected region(s)."""
    session = wiki_session()
    all_facts = []

    # Register sources
    wiki_rhone_sid = ensure_wiki_source("Rhône wine")
    wiki_loire_sid = ensure_wiki_source("Loire wine")
    wiki_alsace_sid = ensure_wiki_source("Alsace wine")
    wikidata_sid = ensure_wikidata_source("French regional wine")

    # Rhône
    if not data_type or data_type == "rhone":
        rhone_facts = _collect_region(
            session, wiki_rhone_sid, wikidata_sid,
            RHONE_ARTICLES, RHONE_CATEGORIES,
            RHONE_KEYWORDS, "rhone", "rhone",
        )
        all_facts.extend(rhone_facts)

        if scrape_web:
            logger.info("--- inter-rhone.com ---")
            web_sid = ensure_source(
                name="Inter Rhône",
                url="https://www.inter-rhone.com",
                source_type="official_body",
                tier="tier_2_authoritative",
                language="en",
            )
            web_facts = _scrape_inter_rhone(web_sid)
            all_facts.extend(web_facts)

    # Loire
    if not data_type or data_type == "loire":
        loire_facts = _collect_region(
            session, wiki_loire_sid, wikidata_sid,
            LOIRE_ARTICLES, LOIRE_CATEGORIES,
            LOIRE_KEYWORDS, "loire", "loire",
        )
        all_facts.extend(loire_facts)

        if scrape_web:
            logger.info("--- vinsdeloire.fr ---")
            web_sid = ensure_source(
                name="Vins de Loire",
                url="https://www.vinsdeloire.fr",
                source_type="official_body",
                tier="tier_2_authoritative",
                language="en",
            )
            web_facts = _scrape_vinsdeloire(web_sid)
            all_facts.extend(web_facts)

    # Alsace
    if not data_type or data_type == "alsace":
        alsace_facts = _collect_region(
            session, wiki_alsace_sid, wikidata_sid,
            ALSACE_ARTICLES, ALSACE_CATEGORIES,
            ALSACE_KEYWORDS, "alsace", "alsace",
        )
        all_facts.extend(alsace_facts)

    # Global dedup
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

    logger.info("=== TEST RUN: Rhône/Loire/Alsace Scraper ===")
    wiki_sid = ensure_wiki_source("Rhône wine")
    wikidata_sid = ensure_wikidata_source("French regional wine")

    session = wiki_session()

    # Fetch just a couple of articles per region for quick test
    test_articles = ["Rhône wine", "Sancerre AOC", "Alsace wine"]
    facts = []
    for title in test_articles:
        logger.info(f"Test: fetching {title}")
        extract, wikitext = fetch_article(session, title)
        if extract:
            atomic = extract_atomic_facts(extract, title, region_keywords=ALL_KEYWORDS)
            for item in atomic[:TEST_RUN_LIMIT]:
                facts.append({
                    "fact_text": item["fact_text"],
                    "domain": item["domain"],
                    "subdomain": "test",
                    "source_id": wiki_sid,
                    "entities": [{"type": "region", "name": title}],
                    "confidence": 0.9,
                    "tags": ["test"],
                })

    click.echo(f"\nTest extracted {len(facts)} facts")
    for f in facts:
        click.echo(f"  [{f['domain']}] {f['fact_text']}")

    if facts:
        inserted = insert_facts_batch(facts)
        click.echo(f"\nInserted {inserted} facts into DB")

        if cleanup:
            pg = get_pg()
            cur = pg.cursor()
            cur.execute(
                "DELETE FROM facts WHERE source_id = %s AND 'test' = ANY(tags)",
                (wiki_sid,),
            )
            deleted = cur.rowcount
            pg.commit()
            click.echo(f"Cleaned up {deleted} test facts")


# ─── CLI ─────────────────────────────────────────────────────────────────────


@click.command()
@click.option("--all", "run_all_flag", is_flag=True, help="Extract all data from all regions")
@click.option(
    "--type", "data_type",
    type=click.Choice(["rhone", "loire", "alsace"]),
    help="Extract data for a specific region",
)
@click.option("--list", "list_sources", is_flag=True, help="List available data sources")
@click.option("--dry-run", is_flag=True, help="Extract facts but do not insert into DB")
@click.option("--validate", "validate_flag", is_flag=True, help="Run quality checks")
@click.option("--test-run", is_flag=True, help="Limited test with report")
@click.option("--cleanup", is_flag=True, help="With --test-run, delete inserted facts after reporting")
def main(
    run_all_flag: bool,
    data_type: Optional[str],
    list_sources: bool,
    dry_run: bool,
    validate_flag: bool,
    test_run: bool,
    cleanup: bool,
) -> None:
    """OenoBench French Regional Scraper — Rhône, Loire, Alsace (genuine data)."""
    logger.add("data/logs/rhone_loire_alsace_{time}.log", rotation="10 MB")

    if list_sources:
        click.echo("\nAvailable data sources:")
        click.echo(f"  {'rhone':10s} — Wikipedia ({len(RHONE_ARTICLES)} key articles), "
                    f"categories ({len(RHONE_CATEGORIES)}), Wikidata SPARQL, inter-rhone.com")
        click.echo(f"  {'loire':10s} — Wikipedia ({len(LOIRE_ARTICLES)} key articles), "
                    f"categories ({len(LOIRE_CATEGORIES)}), Wikidata SPARQL, vinsdeloire.fr")
        click.echo(f"  {'alsace':10s} — Wikipedia ({len(ALSACE_ARTICLES)} key articles), "
                    f"categories ({len(ALSACE_CATEGORIES)}), Wikidata SPARQL")
        click.echo("\nAll facts are scraped from genuine external sources.")
        click.echo("No hardcoded wine knowledge is used.")
        return

    if validate_flag:
        click.echo("Running validation (dry-run collection)...")
        facts = collect_all_facts(data_type=data_type, scrape_web=True)
        validate_facts(facts)
        return

    if test_run:
        run_test(cleanup=cleanup)
        return

    if run_all_flag or data_type:
        facts = collect_all_facts(data_type=data_type, scrape_web=True)
        click.echo(f"\nCollected {len(facts)} facts total")

        if dry_run:
            # Domain summary
            domains = Counter(f["domain"] for f in facts)
            subdomains = Counter(f.get("subdomain", "?") for f in facts)
            click.echo("\nDomain breakdown:")
            for d, c in domains.most_common():
                click.echo(f"  {d}: {c}")
            click.echo("\nSubdomain breakdown:")
            for sd, c in subdomains.most_common():
                click.echo(f"  {sd}: {c}")
            click.echo("\n10 sample facts:")
            for f in random.sample(facts, min(10, len(facts))):
                click.echo(f"  [{f['domain']}] [{f.get('subdomain','')}] {f['fact_text']}")
        else:
            inserted = insert_facts_batch(facts)
            click.echo(f"Inserted {inserted} new facts (from {len(facts)} generated)")

        return

    click.echo("Use --all to extract all data, or --type <region> for a specific region.")
    click.echo("Use --list to see available sources.")
    click.echo("Use --dry-run to preview without inserting.")
    click.echo("Use --validate to run quality checks.")
    click.echo("Use --test-run for a limited test extraction.")


if __name__ == "__main__":
    main()
