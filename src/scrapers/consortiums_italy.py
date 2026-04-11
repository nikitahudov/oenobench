"""
OenoBench — Italian Wine Consortiums Scraper

Extracts wine knowledge from major Italian wine consortium websites:
  - Consorzio del Vino Brunello di Montalcino (brunellodimontalcino.it)
  - Consorzio del Barolo e Barbaresco (langhevini.it)
  - Consorzio del Chianti Classico (chianticlassico.com)
  - Consorzio di Tutela Prosecco DOC (prosecco.wine)
  - Consorzio Franciacorta (franciacorta.wine)
  - Consorzio per la Tutela dei Vini Valpolicella (consorziovalpolicella.it)
  - Consorzio del Vino Nobile di Montepulciano (consorziovinonobile.it)
  - Consorzio Tutela Soave (ilsoave.com)
  - Trentodoc — Istituto Trento DOC (trentodoc.com)

Usage:
    python -m src.scrapers.consortiums_italy --all
    python -m src.scrapers.consortiums_italy --consortium brunello
    python -m src.scrapers.consortiums_italy --consortium barolo
    python -m src.scrapers.consortiums_italy --consortium chianti
    python -m src.scrapers.consortiums_italy --consortium prosecco
    python -m src.scrapers.consortiums_italy --consortium franciacorta
    python -m src.scrapers.consortiums_italy --consortium valpolicella
    python -m src.scrapers.consortiums_italy --consortium vinonobile
    python -m src.scrapers.consortiums_italy --consortium soave
    python -m src.scrapers.consortiums_italy --consortium trentodoc
    python -m src.scrapers.consortiums_italy --dry-run
    python -m src.scrapers.consortiums_italy --validate
    python -m src.scrapers.consortiums_italy --list
"""

import random
import re
import time
from collections import defaultdict
from typing import Optional
from urllib.parse import urljoin

import click
import requests
from bs4 import BeautifulSoup
from loguru import logger

from src.utils.facts import ensure_source, insert_fact, insert_facts_batch, get_fact_count
from src.scrapers._fact_processing import (
    process_facts,
    classify_domain,
    validate_fact,
)

# ─── Configuration ────────────────────────────────────────────────────────────

USER_AGENT = "OenoBench-Research/1.0 (academic wine benchmark)"
REQUEST_DELAY = 5  # 1 request per 5 seconds per domain
REQUEST_TIMEOUT = 30
TEST_RUN_FACT_LIMIT = 5

CONSORTIUMS = {
    "brunello": {
        "name": "Consorzio del Vino Brunello di Montalcino",
        "base_url": "https://www.brunellodimontalcino.it",
        "source_type": "consortium",
        "tier": "tier_2_authoritative",
        "language": "it",
        "pages": [
            "/en/",
            "/en/brunello-di-montalcino/",
            "/en/rosso-di-montalcino/",
            "/en/the-territory/",
            "/en/the-consortium/",
            "/en/moscadello-di-montalcino/",
            "/en/sant-antimo/",
        ],
        "description": "Brunello di Montalcino DOCG consortium — production rules, zones, aging",
    },
    "barolo": {
        "name": "Consorzio di Tutela Barolo Barbaresco Alba Langhe e Dogliani",
        "base_url": "https://www.langhevini.it",
        "source_type": "consortium",
        "tier": "tier_2_authoritative",
        "language": "it",
        "pages": [
            "/en/",
            "/en/wines/barolo/",
            "/en/wines/barbaresco/",
            "/en/wines/langhe/",
            "/en/wines/dogliani/",
            "/en/wines/alba/",
            "/en/territory/",
            "/en/consortium/",
        ],
        "description": "Barolo and Barbaresco consortium — Nebbiolo, Langhe territory, aging rules",
    },
    "chianti": {
        "name": "Consorzio Vino Chianti Classico",
        "base_url": "https://www.chianticlassico.com",
        "source_type": "consortium",
        "tier": "tier_2_authoritative",
        "language": "it",
        "pages": [
            "/en/",
            "/en/chianti-classico/",
            "/en/chianti-classico-riserva/",
            "/en/chianti-classico-gran-selezione/",
            "/en/territory/",
            "/en/consortium/",
            "/en/production-regulations/",
        ],
        "description": "Chianti Classico consortium — DOCG tiers, Sangiovese, Black Rooster",
    },
    "prosecco": {
        "name": "Consorzio di Tutela della Denominazione di Origine Controllata Prosecco",
        "base_url": "https://www.prosecco.wine",
        "source_type": "consortium",
        "tier": "tier_2_authoritative",
        "language": "it",
        "pages": [
            "/en/",
            "/en/prosecco-doc/",
            "/en/denomination/",
            "/en/territory/",
            "/en/grape-varieties/",
            "/en/consortium/",
            "/en/production-regulations/",
        ],
        "description": "Prosecco DOC consortium — Glera grape, sparkling production, territory",
    },
    "franciacorta": {
        "name": "Consorzio Franciacorta",
        "base_url": "https://www.franciacorta.wine",
        "source_type": "consortium",
        "tier": "tier_2_authoritative",
        "language": "it",
        "pages": [
            "/en/",
            "/en/franciacorta/",
            "/en/territory/",
            "/en/production-method/",
        ],
        "description": "Franciacorta DOCG consortium — traditional method sparkling, Lombardy",
    },
    "valpolicella": {
        "name": "Consorzio per la Tutela dei Vini Valpolicella",
        "base_url": "https://www.consorziovalpolicella.it",
        "source_type": "consortium",
        "tier": "tier_2_authoritative",
        "language": "it",
        "pages": [
            "/en/",
            "/en/the-wines/",
            "/en/territory/",
        ],
        "description": "Valpolicella consortium — Amarone, Ripasso, Recioto, Corvina-based wines",
    },
    "vinonobile": {
        "name": "Consorzio del Vino Nobile di Montepulciano",
        "base_url": "https://www.consorziovinonobile.it",
        "source_type": "consortium",
        "tier": "tier_2_authoritative",
        "language": "it",
        "pages": [
            "/en/",
            "/en/the-wine/",
            "/en/the-territory/",
        ],
        "description": "Vino Nobile di Montepulciano DOCG consortium — Prugnolo Gentile, Tuscany",
    },
    "soave": {
        "name": "Consorzio Tutela Soave",
        "base_url": "https://www.ilsoave.com",
        "source_type": "consortium",
        "tier": "tier_2_authoritative",
        "language": "it",
        "pages": [
            "/en/",
            "/en/the-wine/",
            "/en/the-territory/",
        ],
        "description": "Soave consortium — Garganega, volcanic soils, Veneto white wines",
    },
    "trentodoc": {
        "name": "Trentodoc — Istituto Trento DOC",
        "base_url": "https://www.trentodoc.com",
        "source_type": "consortium",
        "tier": "tier_2_authoritative",
        "language": "it",
        "pages": [
            "/en/",
            "/en/trentodoc/",
            "/en/territory/",
        ],
        "description": "Trentodoc consortium — traditional method sparkling, mountain viticulture, Trentino",
    },
}

# ─── HTTP Fetching ────────────────────────────────────────────────────────────

_last_request_time: dict[str, float] = {}


def _get_session() -> requests.Session:
    """Create a requests session with appropriate headers."""
    session = requests.Session()
    session.headers.update({
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,it;q=0.5",
    })
    return session


def _rate_limit(domain: str) -> None:
    """Enforce per-domain rate limiting (1 request per 5 seconds)."""
    now = time.time()
    last = _last_request_time.get(domain, 0)
    wait = REQUEST_DELAY - (now - last)
    if wait > 0:
        logger.debug(f"Rate limiting: waiting {wait:.1f}s for {domain}")
        time.sleep(wait)
    _last_request_time[domain] = time.time()


def fetch_page(url: str, session: requests.Session) -> Optional[str]:
    """Fetch a single page with rate limiting. Returns HTML or None."""
    from urllib.parse import urlparse

    domain = urlparse(url).netloc
    _rate_limit(domain)

    try:
        resp = session.get(url, timeout=REQUEST_TIMEOUT, allow_redirects=True)
        resp.raise_for_status()
        logger.info(f"Fetched {url} ({len(resp.text)} bytes)")
        return resp.text
    except requests.RequestException as exc:
        logger.warning(f"Failed to fetch {url}: {exc}")
        return None


def extract_text_blocks(html: str) -> list[str]:
    """Extract meaningful text blocks from HTML page."""
    soup = BeautifulSoup(html, "lxml")

    # Remove script, style, nav, footer, header elements
    for tag in soup.find_all(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()

    blocks = []
    # Extract from main content areas
    content_areas = soup.find_all(
        ["article", "main", "section", "div"],
        class_=lambda c: c and any(
            kw in (c if isinstance(c, str) else " ".join(c)).lower()
            for kw in ["content", "text", "body", "article", "main", "wine", "desc"]
        ),
    )

    # Fallback to body if no content areas found
    if not content_areas:
        content_areas = [soup.find("body")] if soup.find("body") else []

    for area in content_areas:
        if area is None:
            continue
        for element in area.find_all(["p", "li", "h1", "h2", "h3", "h4", "td", "dd"]):
            text = element.get_text(separator=" ", strip=True)
            # Filter out very short or navigation-like text
            if text and len(text) > 20 and len(text.split()) > 3:
                blocks.append(text)

    return blocks


# ─── Region keywords for on-topic filtering per consortium ────────────────────

CONSORTIUM_KEYWORDS = {
    "brunello": {
        "brunello", "montalcino", "sangiovese", "rosso", "moscadello",
        "sant'antimo", "sant antimo", "siena", "tuscany", "toscana",
        "docg", "doc", "oak", "aging", "barrel",
    },
    "barolo": {
        "barolo", "barbaresco", "nebbiolo", "langhe", "piedmont", "piemonte",
        "alba", "dogliani", "dolcetto", "docg", "serralunga", "la morra",
        "castiglione", "monforte", "roero",
    },
    "chianti": {
        "chianti", "classico", "sangiovese", "tuscany", "toscana",
        "florence", "siena", "gallo nero", "black rooster", "gran selezione",
        "riserva", "annata", "docg",
    },
    "prosecco": {
        "prosecco", "glera", "charmat", "spumante", "frizzante",
        "treviso", "veneto", "friuli", "conegliano", "valdobbiadene",
        "brut", "extra dry", "doc", "docg",
    },
    "franciacorta": {
        "franciacorta", "chardonnay", "pinot", "lombardy", "lombardia",
        "brescia", "iseo", "metodo classico", "traditional method",
        "satèn", "saten", "docg", "sparkling", "millesimato",
    },
    "valpolicella": {
        "valpolicella", "amarone", "ripasso", "recioto", "corvina",
        "corvinone", "rondinella", "verona", "veneto", "appassimento",
        "classico", "docg", "doc",
    },
    "vinonobile": {
        "vino nobile", "montepulciano", "sangiovese", "prugnolo",
        "tuscany", "toscana", "siena", "docg", "riserva",
        "rosso di montepulciano",
    },
    "soave": {
        "soave", "garganega", "trebbiano", "verona", "veneto",
        "volcanic", "classico", "superiore", "recioto", "docg", "doc",
    },
    "trentodoc": {
        "trentodoc", "trento", "trentino", "chardonnay", "pinot",
        "metodo classico", "traditional method", "sparkling",
        "millesimato", "riserva", "doc", "adige",
    },
}


# ─── Fact Extraction from Scraped Text ───────────────────────────────────────


def _extract_facts_from_text(
    text_blocks: list[str],
    consortium_key: str,
    source_id: str,
) -> list[dict]:
    """Extract atomic facts from scraped text blocks using the shared pipeline.

    Processes raw text through decompose -> resolve -> classify -> validate -> filter.
    No hardcoded wine knowledge.
    """
    if not text_blocks:
        return []

    cfg = CONSORTIUMS[consortium_key]
    subject = cfg["name"]
    keywords = CONSORTIUM_KEYWORDS.get(consortium_key, set())

    # Run through the shared fact processing pipeline
    processed = process_facts(
        raw_texts=text_blocks,
        subject=subject,
        region_keywords=keywords if keywords else None,
    )

    facts = []
    for item in processed:
        facts.append({
            "fact_text": item["fact_text"],
            "domain": item["domain"],
            "subdomain": f"italy_{consortium_key}",
            "source_id": source_id,
            "entities": [],
            "confidence": 0.85,
            "tags": [consortium_key, "consortium", "scraped"],
        })

    return facts



# ─── Scraping Pipeline ───────────────────────────────────────────────────────

def scrape_consortium(
    consortium_name: str, dry_run: bool = False
) -> list[dict]:
    """Scrape a single consortium and return extracted facts."""
    if consortium_name not in CONSORTIUMS:
        logger.error(
            f"Unknown consortium: {consortium_name}. "
            f"Available: {list(CONSORTIUMS.keys())}"
        )
        return []

    cfg = CONSORTIUMS[consortium_name]
    logger.info(f"Scraping consortium: {cfg['name']}")
    logger.info(f"Description: {cfg['description']}")

    # Register source
    if not dry_run:
        source_id = ensure_source(
            name=cfg["name"],
            url=cfg["base_url"],
            source_type=cfg["source_type"],
            tier=cfg["tier"],
            language=cfg["language"],
        )
    else:
        source_id = "dry-run"

    # Fetch pages
    session = _get_session()
    all_text_blocks: list[str] = []
    pages_fetched = 0

    for page_path in cfg["pages"]:
        url = urljoin(cfg["base_url"], page_path)
        html = fetch_page(url, session)
        if html:
            blocks = extract_text_blocks(html)
            all_text_blocks.extend(blocks)
            pages_fetched += 1
            logger.info(f"  Extracted {len(blocks)} text blocks from {url}")
        else:
            logger.warning(f"  Could not fetch {url}")

    logger.info(
        f"Fetched {pages_fetched}/{len(cfg['pages'])} pages, "
        f"extracted {len(all_text_blocks)} total text blocks"
    )

    if not all_text_blocks:
        logger.warning(
            f"No text extracted from {cfg['name']} website. "
            f"No facts can be generated without scraped content."
        )
        return []

    # Build facts using shared processing pipeline
    facts = _extract_facts_from_text(all_text_blocks, consortium_name, source_id)

    # Deduplicate within this consortium run
    seen_texts = set()
    unique_facts = []
    for fact in facts:
        if fact["fact_text"] not in seen_texts:
            seen_texts.add(fact["fact_text"])
            unique_facts.append(fact)

    logger.info(
        f"Built {len(unique_facts)} unique facts for {consortium_name} "
        f"({len(facts) - len(unique_facts)} in-run duplicates removed)"
    )
    return unique_facts


def run_consortium(consortium_name: str, dry_run: bool = False) -> int:
    """Scrape a consortium and insert facts. Returns count inserted."""
    facts = scrape_consortium(consortium_name, dry_run=dry_run)

    if dry_run:
        click.echo(
            f"\n[DRY RUN] Would insert {len(facts)} facts from {consortium_name}"
        )
        return len(facts)

    if not facts:
        return 0

    inserted = insert_facts_batch(facts)
    logger.info(
        f"Inserted {inserted} new facts from {consortium_name} (duplicates skipped)"
    )
    return inserted


def run_all(dry_run: bool = False) -> dict:
    """Scrape all consortiums. Returns summary dict."""
    summary = {}
    total = 0

    for name in CONSORTIUMS:
        count = run_consortium(name, dry_run=dry_run)
        summary[name] = count
        total += count

    logger.info(f"Italian consortiums scraping complete. Total facts: {total}")
    if not dry_run:
        logger.info(f"Total facts in database: {get_fact_count()}")
    return summary


# ─── Validation ───────────────────────────────────────────────────────────────

def validate_facts(facts: list[dict]) -> None:
    """Run quality checks on extracted facts and print a report."""
    if not facts:
        click.echo("No facts to validate.")
        return

    total = len(facts)

    # (a) Domain/subdomain distribution
    domain_counts: dict[str, int] = defaultdict(int)
    subdomain_counts: dict[str, int] = defaultdict(int)
    for f in facts:
        domain_counts[f["domain"]] += 1
        sub = f.get("subdomain") or "(none)"
        subdomain_counts[f"{f['domain']}/{sub}"] += 1

    click.echo("\nDomain distribution:")
    for domain, count in sorted(domain_counts.items()):
        click.echo(f"  {domain:25s}: {count} facts")

    click.echo("\nSubdomain distribution:")
    for sub, count in sorted(subdomain_counts.items()):
        click.echo(f"  {sub:45s}: {count} facts")

    # (b) Length checks
    too_short = [f for f in facts if len(f["fact_text"].split()) < 5]
    too_long = [f for f in facts if len(f["fact_text"].split()) > 50]
    click.echo(f"\nQuality:")
    click.echo(
        f"  Too short (<5 words):  {len(too_short)} ({100 * len(too_short) / total:.1f}%)"
    )
    click.echo(
        f"  Too long (>50 words):  {len(too_long)} ({100 * len(too_long) / total:.1f}%)"
    )
    if too_short:
        click.echo("  Short facts:")
        for f in too_short:
            click.echo(f'    - "{f["fact_text"]}"')
    if too_long:
        click.echo("  Long facts:")
        for f in too_long:
            click.echo(f'    - "{f["fact_text"]}"')

    # (c) Entity-name-only facts (no predicate)
    no_predicate = [
        f
        for f in facts
        if len(f["fact_text"].rstrip(".").strip().split()) <= 2
    ]
    click.echo(
        f"  No-predicate facts:    {len(no_predicate)} ({100 * len(no_predicate) / total:.1f}%)"
    )

    # (d) Near-duplicate check (substring containment)
    near_dupes = 0
    fact_texts = [f["fact_text"] for f in facts]
    sample_size = min(len(fact_texts), 500)
    sampled = random.sample(fact_texts, sample_size)
    for i, a in enumerate(sampled):
        for b in sampled[i + 1 :]:
            a_stripped = a.rstrip(".")
            b_stripped = b.rstrip(".")
            if len(a_stripped) > 20 and len(b_stripped) > 20:
                if a_stripped in b_stripped or b_stripped in a_stripped:
                    near_dupes += 1
    click.echo(f"  Possible near-dupes:   {near_dupes} (sampled {sample_size} facts)")

    # (e) Entity population rate
    with_entities = sum(
        1 for f in facts if f.get("entities") and len(f["entities"]) > 0
    )
    missing_entities = total - with_entities
    click.echo(
        f"  Missing entities:      {missing_entities} ({100 * missing_entities / total:.1f}%)"
    )

    # (f) Random samples
    click.echo(f"\nSample facts ({min(10, total)} random):")
    samples = random.sample(facts, min(10, total))
    for i, f in enumerate(samples, 1):
        click.echo(f'  {i:2d}. "{f["fact_text"]}"')


# ─── Test Run ────────────────────────────────────────────────────────────────


def _print_test_report(
    category_stats: dict[str, dict],
    all_facts: list[dict],
    all_inserted_ids: list[str],
) -> None:
    """Print structured test-run report with quality checks."""
    click.echo("\n=== TEST RUN REPORT ===")
    click.echo("")

    # Table header
    header = (
        f"  {'Source/Category':<25s} {'Items Processed':>17s} "
        f"{'Facts Generated':>17s} {'Facts Inserted (new)':>22s}"
    )
    separator = "  " + "─" * 83
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

    # Quality checks
    if not all_facts:
        click.echo("\n  No facts to analyze.")
        return

    total = len(all_facts)
    too_short = []
    too_long = []
    missing_entities = 0
    total_words = 0

    for f in all_facts:
        text = f["fact_text"]
        wc = len(text.split())
        total_words += wc

        if wc < 5:
            too_short.append(text)
        if wc > 50:
            too_long.append(text)
        if not f.get("entities"):
            missing_entities += 1

    avg_words = total_words / total if total else 0

    click.echo(f"\n  Quality Checks:")
    click.echo(
        f"    Too short (<5 words):  {len(too_short)} ({len(too_short)/total*100:.1f}%)"
    )
    click.echo(
        f"    Too long (>50 words):  {len(too_long)} ({len(too_long)/total*100:.1f}%)"
    )
    click.echo(
        f"    Missing entities:      {missing_entities} ({missing_entities/total*100:.1f}%)"
    )
    click.echo(f"    Avg words per fact:    {avg_words:.1f}")

    # Sample facts
    sample = random.sample(all_facts, min(10, len(all_facts)))
    click.echo(f"\n  Sample Facts ({min(10, len(all_facts))} random from this run):")
    for i, f in enumerate(sample, 1):
        click.echo(f"    {i:2d}. \"{f['fact_text']}\"")

    # Warnings
    warnings = []

    for cat_name, stats in category_stats.items():
        if stats["facts_inserted"] == 0 and stats["items_processed"] > 0:
            warnings.append(f"ERROR: No facts from {cat_name}")

        items = stats["items_processed"]
        generated = stats["facts_generated"]
        if items > 0 and generated / items < 2:
            warnings.append(
                f"WARNING: Low extraction rate in {cat_name} "
                f"({generated/items:.1f} facts/item)"
            )

        if items > 0 and generated > 0:
            skipped = generated - stats["facts_inserted"]
            if skipped / generated > 0.5:
                warnings.append(
                    f"WARNING: High duplicate rate in {cat_name} "
                    f"({skipped}/{generated} = {skipped/generated*100:.0f}% skipped)"
                )

    if len(too_short) / total > 0.1:
        warnings.append("WARNING: Too many trivial facts")

    if len(too_long) / total > 0.1:
        warnings.append("WARNING: Facts need better splitting")

    if warnings:
        click.echo(f"\n  ⚠ Warnings:")
        for w in warnings:
            click.echo(f"    * {w}")
    else:
        click.echo(f"\n  ✔ No warnings — all checks passed.")


def run_test(cleanup: bool = False) -> None:
    """Run a limited test extraction: first consortium only, insert, report."""
    category_stats = {}
    all_facts = []
    inserted_ids = []

    # Test with just the first consortium to keep it quick
    test_consortiums = list(CONSORTIUMS.keys())[:2]

    for consortium_key in test_consortiums:
        cfg = CONSORTIUMS[consortium_key]
        # Register source
        source_id = ensure_source(
            name=cfg["name"],
            url=cfg["base_url"],
            source_type=cfg["source_type"],
            tier=cfg["tier"],
            language=cfg["language"],
        )

        # Scrape just 2 pages to keep test quick
        session = _get_session()
        text_blocks = []
        pages_fetched = 0
        for page_path in cfg["pages"][:2]:
            url = urljoin(cfg["base_url"], page_path)
            html = fetch_page(url, session)
            if html:
                blocks = extract_text_blocks(html)
                text_blocks.extend(blocks)
                pages_fetched += 1

        # Extract facts from scraped text
        all_generated = _extract_facts_from_text(text_blocks, consortium_key, source_id)

        # Limit to TEST_RUN_FACT_LIMIT facts
        test_facts = all_generated[:TEST_RUN_FACT_LIMIT]

        # Insert individually to track IDs
        cat_inserted = 0
        for f in test_facts:
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
                inserted_ids.append(fact_id)
                cat_inserted += 1

        all_facts.extend(test_facts)
        category_stats[consortium_key] = {
            "items_processed": pages_fetched,
            "facts_generated": len(test_facts),
            "facts_inserted": cat_inserted,
        }

    _print_test_report(category_stats, all_facts, inserted_ids)

    # Cleanup
    if cleanup and inserted_ids:
        from src.utils.db import get_pg
        pg = get_pg()
        cur = pg.cursor()
        cur.execute("DELETE FROM facts WHERE id = ANY(%s::uuid[])", (inserted_ids,))
        pg.commit()
        click.echo(f"\n  Cleaned up {len(inserted_ids)} test facts from database.")


# ─── CLI ──────────────────────────────────────────────────────────────────────

@click.command()
@click.option(
    "--consortium",
    "-c",
    type=click.Choice(["brunello", "barolo", "chianti", "prosecco", "franciacorta", "valpolicella", "vinonobile", "soave", "trentodoc"]),
    help="Scrape a specific consortium",
)
@click.option("--all", "run_all_flag", is_flag=True, help="Scrape all consortiums")
@click.option(
    "--list", "list_consortiums", is_flag=True, help="List available consortiums"
)
@click.option(
    "--dry-run",
    "dry_run",
    is_flag=True,
    help="Extract facts but do not insert into DB",
)
@click.option(
    "--validate",
    "validate_flag",
    is_flag=True,
    help="Run quality checks on extracted facts",
)
@click.option(
    "--test-run",
    is_flag=True,
    help="Process first consortium with limited facts, insert, and report",
)
@click.option(
    "--cleanup",
    is_flag=True,
    help="With --test-run, delete inserted facts after reporting",
)
def main(
    consortium: Optional[str],
    run_all_flag: bool,
    list_consortiums: bool,
    dry_run: bool,
    validate_flag: bool,
    test_run: bool,
    cleanup: bool,
) -> None:
    """OenoBench Italian Consortiums Scraper — Extract wine knowledge from Italian consortium websites."""
    logger.add("data/logs/consortiums_italy_{time}.log", rotation="10 MB")

    if list_consortiums:
        click.echo("\nAvailable consortiums:")
        for name, cfg in CONSORTIUMS.items():
            click.echo(f"  {name:12s} — {cfg['description']}")
        return

    if validate_flag:
        click.echo("Running validation on all consortiums...")
        all_facts: list[dict] = []
        for name in CONSORTIUMS:
            all_facts.extend(scrape_consortium(name, dry_run=True))
        validate_facts(all_facts)
        return

    if test_run:
        run_test(cleanup=cleanup)
        return

    if run_all_flag:
        summary = run_all(dry_run=dry_run)
        click.echo("\nSummary:")
        for name, count in summary.items():
            label = f"{name} (dry-run)" if dry_run else name
            click.echo(f"  {label:25s}: {count} facts")
        click.echo(f"  {'TOTAL':25s}: {sum(summary.values())} facts")
        return

    if consortium:
        count = run_consortium(consortium, dry_run=dry_run)
        if dry_run:
            click.echo(
                f"\n[DRY RUN] {count} facts extracted from '{consortium}'."
            )
        else:
            click.echo(f"\nInserted {count} new facts from '{consortium}'.")
        return

    click.echo(
        "Use --all to scrape all consortiums, or --consortium <name> for a specific one."
    )
    click.echo("Use --list to see available consortiums.")
    click.echo("Use --dry-run to preview without inserting.")
    click.echo("Use --validate to run quality checks.")
    click.echo("Use --test-run to process first consortium with limited facts and report.")


if __name__ == "__main__":
    main()
