"""
OenoBench — Wikidata SPARQL Scraper

Extracts structured wine knowledge from Wikidata via SPARQL queries.
This is the highest-value, lowest-risk data source (CC0 license).

Usage:
    python -m src.scrapers.wikidata --all
    python -m src.scrapers.wikidata --query regions
    python -m src.scrapers.wikidata --query grapes
    python -m src.scrapers.wikidata --query appellations
    python -m src.scrapers.wikidata --query producers
    python -m src.scrapers.wikidata --query classifications
    python -m src.scrapers.wikidata --test-run
    python -m src.scrapers.wikidata --test-run --cleanup
"""

import random
import time
from typing import Optional

import click
from loguru import logger
from SPARQLWrapper import SPARQLWrapper, JSON

from src.utils.facts import ensure_source, insert_fact, insert_facts_batch, get_fact_count

# ─── Configuration ────────────────────────────────────────────────────────────

WIKIDATA_ENDPOINT = "https://query.wikidata.org/sparql"
USER_AGENT = "OenoBench-Research/1.0 (academic wine benchmark; Python SPARQLWrapper)"
REQUEST_DELAY = 1.5  # seconds between queries (respectful rate limiting)
TEST_RUN_QUERIES = 2  # number of queries to run in --test-run mode

# ─── SPARQL Queries ───────────────────────────────────────────────────────────

QUERIES = {
    "regions": {
        "description": "Wine regions with country, parent region, and coordinates",
        "sparql": """
            SELECT DISTINCT
                ?region ?regionLabel
                ?country ?countryLabel
                ?parentRegion ?parentRegionLabel
                ?coord
            WHERE {
                {
                    ?region wdt:P31/wdt:P279* wd:Q1131296 .
                }
                UNION
                {
                    ?region wdt:P31/wdt:P279* wd:Q10864048 .
                    ?region wdt:P17 ?anyCountry .
                }
                OPTIONAL { ?region wdt:P17 ?country }
                OPTIONAL { ?region wdt:P131 ?parentRegion }
                OPTIONAL { ?region wdt:P625 ?coord }
                SERVICE wikibase:label { bd:serviceParam wikibase:language "en,fr,it,es,de" }
            }
            ORDER BY ?regionLabel
        """,
        "domain": "wine_regions",
        "fact_builder": "_build_region_facts",
    },

    "grapes": {
        "description": "Grape varieties with color, origin, and synonyms",
        "sparql": """
            SELECT DISTINCT
                ?grape ?grapeLabel
                ?color ?colorLabel
                ?origin ?originLabel
            WHERE {
                {
                    ?grape wdt:P31/wdt:P279* wd:Q10978 .
                }
                UNION
                {
                    ?grape wdt:P3900 ?vivc .
                }
                UNION
                {
                    ?grape wdt:P31 wd:Q13218644 .
                }
                OPTIONAL { ?grape wdt:P462 ?color }
                OPTIONAL { ?grape wdt:P495 ?origin }
                SERVICE wikibase:label { bd:serviceParam wikibase:language "en,fr,it,es,de" }
            }
            ORDER BY ?grapeLabel
        """,
        "domain": "grape_varieties",
        "fact_builder": "_build_grape_facts",
    },

    "appellations": {
        "description": "Wine appellations with classification type and country",
        "sparql": """
            SELECT DISTINCT
                ?appellation ?appellationLabel
                ?type ?typeLabel
                ?country ?countryLabel
                ?region ?regionLabel
                ?grape ?grapeLabel
            WHERE {
                ?appellation wdt:P31/wdt:P279* wd:Q454541 .
                OPTIONAL { ?appellation wdt:P31 ?type }
                OPTIONAL { ?appellation wdt:P17 ?country }
                OPTIONAL { ?appellation wdt:P131 ?region }
                OPTIONAL { ?appellation wdt:P186 ?grape }
                SERVICE wikibase:label { bd:serviceParam wikibase:language "en,fr,it,es,de" }
            }
            ORDER BY ?appellationLabel
        """,
        "domain": "wine_regions",
        "subdomain": "appellations",
        "fact_builder": "_build_appellation_facts",
    },

    "producers": {
        "description": "Wineries and wine producers with location and founding date",
        "sparql": """
            SELECT DISTINCT
                ?producer ?producerLabel
                ?country ?countryLabel
                ?region ?regionLabel
                ?inception
                ?coord
            WHERE {
                ?producer wdt:P31/wdt:P279* wd:Q156362 .
                OPTIONAL { ?producer wdt:P17 ?country }
                OPTIONAL { ?producer wdt:P131 ?region }
                OPTIONAL { ?producer wdt:P571 ?inception }
                OPTIONAL { ?producer wdt:P625 ?coord }
                SERVICE wikibase:label { bd:serviceParam wikibase:language "en,fr,it,es,de" }
            }
            ORDER BY ?producerLabel
        """,
        "domain": "producers",
        "fact_builder": "_build_producer_facts",
    },

    "classifications": {
        "description": "Wine classification systems (Bordeaux 1855, etc.)",
        "sparql": """
            SELECT DISTINCT
                ?wine ?wineLabel
                ?classification ?classificationLabel
                ?appellation ?appellationLabel
                ?producer ?producerLabel
            WHERE {
                {
                    ?wine wdt:P361 wd:Q1344189 .
                    OPTIONAL { ?wine wdt:P31 ?classification }
                    OPTIONAL { ?wine wdt:P131 ?appellation }
                    OPTIONAL { ?wine wdt:P176 ?producer }
                }
                UNION
                {
                    ?wine wdt:P361 wd:Q1090469 .
                    OPTIONAL { ?wine wdt:P31 ?classification }
                    OPTIONAL { ?wine wdt:P131 ?appellation }
                    OPTIONAL { ?wine wdt:P176 ?producer }
                }
                SERVICE wikibase:label { bd:serviceParam wikibase:language "en,fr,it,es,de" }
            }
            ORDER BY ?classificationLabel ?wineLabel
        """,
        "domain": "wine_regions",
        "subdomain": "classifications",
        "fact_builder": "_build_classification_facts",
    },
}


# ─── SPARQL Client ────────────────────────────────────────────────────────────

def run_sparql_query(sparql_query: str) -> list[dict]:
    """Execute a SPARQL query against Wikidata and return results as dicts."""
    sparql = SPARQLWrapper(WIKIDATA_ENDPOINT)
    sparql.setQuery(sparql_query)
    sparql.setReturnFormat(JSON)
    sparql.addCustomHttpHeader("User-Agent", USER_AGENT)

    logger.info("Executing SPARQL query...")
    results = sparql.query().convert()

    rows = []
    for binding in results["results"]["bindings"]:
        row = {}
        for key, val in binding.items():
            row[key] = val.get("value", "")
        rows.append(row)

    logger.info(f"Query returned {len(rows)} results")
    return rows


# ─── Fact Builders ────────────────────────────────────────────────────────────

def _extract_qid(uri: str) -> str:
    """Extract Wikidata QID from a full URI."""
    return uri.split("/")[-1] if uri else ""


def _build_region_facts(rows: list[dict], source_id: str) -> list[dict]:
    """Convert Wikidata region results to atomic facts."""
    facts = []
    seen = set()

    for row in rows:
        region = row.get("regionLabel", "")
        country = row.get("countryLabel", "")
        parent = row.get("parentRegionLabel", "")
        qid = _extract_qid(row.get("region", ""))

        if not region or region.startswith("Q"):
            continue

        # Fact: Region exists in country
        if country and not country.startswith("Q"):
            key = f"region_country:{region}:{country}"
            if key not in seen:
                seen.add(key)
                facts.append({
                    "fact_text": f"{region} is a wine region in {country}.",
                    "domain": "wine_regions",
                    "subdomain": country.lower().replace(" ", "_"),
                    "source_id": source_id,
                    "entities": [
                        {"type": "region", "name": region, "wikidata_id": qid},
                        {"type": "country", "name": country},
                    ],
                    "tags": ["region", "geography", country.lower()],
                })

        # Fact: Region has parent region
        if parent and not parent.startswith("Q") and parent != region:
            key = f"region_parent:{region}:{parent}"
            if key not in seen:
                seen.add(key)
                facts.append({
                    "fact_text": f"{region} is located within the {parent} wine area.",
                    "domain": "wine_regions",
                    "source_id": source_id,
                    "entities": [
                        {"type": "region", "name": region, "wikidata_id": qid},
                        {"type": "region", "name": parent},
                    ],
                    "tags": ["region", "geography", "hierarchy"],
                })

    return facts


def _build_grape_facts(rows: list[dict], source_id: str) -> list[dict]:
    """Convert Wikidata grape variety results to atomic facts."""
    facts = []
    seen = set()

    for row in rows:
        grape = row.get("grapeLabel", "")
        color = row.get("colorLabel", "")
        origin = row.get("originLabel", "")
        qid = _extract_qid(row.get("grape", ""))

        if not grape or grape.startswith("Q"):
            continue

        # Fact: Grape variety exists (always create this)
        base_key = f"grape_exists:{grape}"
        if base_key not in seen:
            seen.add(base_key)
            color_mapped = _map_grape_color(color) if (color and not color.startswith("Q")) else None
            if color_mapped:
                facts.append({
                    "fact_text": f"{grape} is a {color_mapped} grape variety.",
                    "domain": "grape_varieties",
                    "source_id": source_id,
                    "entities": [
                        {"type": "grape", "name": grape, "wikidata_id": qid},
                    ],
                    "tags": ["grape", color_mapped],
                })
            else:
                facts.append({
                    "fact_text": f"{grape} is a grape variety.",
                    "domain": "grape_varieties",
                    "source_id": source_id,
                    "entities": [
                        {"type": "grape", "name": grape, "wikidata_id": qid},
                    ],
                    "tags": ["grape"],
                })

        # Fact: Grape origin
        if origin and not origin.startswith("Q"):
            key = f"grape_origin:{grape}:{origin}"
            if key not in seen:
                seen.add(key)
                facts.append({
                    "fact_text": f"{grape} is a grape variety originating from {origin}.",
                    "domain": "grape_varieties",
                    "source_id": source_id,
                    "entities": [
                        {"type": "grape", "name": grape, "wikidata_id": qid},
                        {"type": "country", "name": origin},
                    ],
                    "tags": ["grape", "origin", origin.lower()],
                })

    return facts


def _map_grape_color(wikidata_color: str) -> Optional[str]:
    """Map Wikidata color labels to standard wine grape colors."""
    color_lower = wikidata_color.lower()
    if any(c in color_lower for c in ["black", "dark", "noir", "red", "blue"]):
        return "red"
    elif any(c in color_lower for c in ["white", "green", "yellow", "blanc"]):
        return "white"
    elif any(c in color_lower for c in ["pink", "rose", "grey", "gris", "gray"]):
        return "rosé"
    return None


def _build_appellation_facts(rows: list[dict], source_id: str) -> list[dict]:
    """Convert Wikidata appellation results to atomic facts."""
    facts = []
    seen = set()

    for row in rows:
        appellation = row.get("appellationLabel", "")
        country = row.get("countryLabel", "")
        region = row.get("regionLabel", "")
        grape = row.get("grapeLabel", "")
        type_label = row.get("typeLabel", "")
        qid = _extract_qid(row.get("appellation", ""))

        if not appellation or appellation.startswith("Q"):
            continue

        # Fact: Appellation exists in country
        if country and not country.startswith("Q"):
            key = f"appellation_country:{appellation}:{country}"
            if key not in seen:
                seen.add(key)
                facts.append({
                    "fact_text": f"{appellation} is a wine appellation in {country}.",
                    "domain": "wine_regions",
                    "subdomain": "appellations",
                    "source_id": source_id,
                    "entities": [
                        {"type": "appellation", "name": appellation, "wikidata_id": qid},
                        {"type": "country", "name": country},
                    ],
                    "tags": ["appellation", country.lower()],
                })

        # Fact: Appellation permits grape variety
        if grape and not grape.startswith("Q"):
            key = f"appellation_grape:{appellation}:{grape}"
            if key not in seen:
                seen.add(key)
                facts.append({
                    "fact_text": f"The {appellation} appellation permits the {grape} grape variety.",
                    "domain": "wine_regions",
                    "subdomain": "appellations",
                    "source_id": source_id,
                    "entities": [
                        {"type": "appellation", "name": appellation, "wikidata_id": qid},
                        {"type": "grape", "name": grape},
                    ],
                    "tags": ["appellation", "grape", "regulation"],
                })

    return facts


def _build_producer_facts(rows: list[dict], source_id: str) -> list[dict]:
    """Convert Wikidata producer results to atomic facts."""
    facts = []
    seen = set()

    for row in rows:
        producer = row.get("producerLabel", "")
        country = row.get("countryLabel", "")
        region = row.get("regionLabel", "")
        inception = row.get("inception", "")
        qid = _extract_qid(row.get("producer", ""))

        if not producer or producer.startswith("Q"):
            continue

        # Fact: Producer location
        location = region if (region and not region.startswith("Q")) else country
        if location and not location.startswith("Q"):
            key = f"producer_location:{producer}:{location}"
            if key not in seen:
                seen.add(key)
                facts.append({
                    "fact_text": f"{producer} is a wine producer located in {location}.",
                    "domain": "producers",
                    "source_id": source_id,
                    "entities": [
                        {"type": "producer", "name": producer, "wikidata_id": qid},
                        {"type": "region", "name": location},
                    ],
                    "tags": ["producer", "location"],
                })

        # Fact: Producer founding year
        if inception:
            year = inception[:4]
            if year.isdigit():
                key = f"producer_founded:{producer}:{year}"
                if key not in seen:
                    seen.add(key)
                    facts.append({
                        "fact_text": f"{producer} was founded in {year}.",
                        "domain": "producers",
                        "source_id": source_id,
                        "entities": [
                            {"type": "producer", "name": producer, "wikidata_id": qid},
                        ],
                        "tags": ["producer", "history", "founding"],
                    })

    return facts


def _build_classification_facts(rows: list[dict], source_id: str) -> list[dict]:
    """Convert Wikidata classification results to atomic facts."""
    facts = []
    seen = set()

    for row in rows:
        wine = row.get("wineLabel", "")
        classification = row.get("classificationLabel", "")
        appellation = row.get("appellationLabel", "")
        producer = row.get("producerLabel", "")
        qid = _extract_qid(row.get("wine", ""))

        if not wine or wine.startswith("Q"):
            continue

        # Fact: Wine in classification
        if classification and not classification.startswith("Q"):
            key = f"classification:{wine}:{classification}"
            if key not in seen:
                seen.add(key)
                entities = [{"type": "wine", "name": wine, "wikidata_id": qid}]
                if producer and not producer.startswith("Q"):
                    entities.append({"type": "producer", "name": producer})

                facts.append({
                    "fact_text": f"{wine} is classified as {classification}.",
                    "domain": "wine_regions",
                    "subdomain": "classifications",
                    "source_id": source_id,
                    "entities": entities,
                    "tags": ["classification", "bordeaux"],
                })

    return facts


# ─── Fact Builder Dispatch ────────────────────────────────────────────────────

FACT_BUILDERS = {
    "_build_region_facts": _build_region_facts,
    "_build_grape_facts": _build_grape_facts,
    "_build_appellation_facts": _build_appellation_facts,
    "_build_producer_facts": _build_producer_facts,
    "_build_classification_facts": _build_classification_facts,
}


# ─── Main Pipeline ────────────────────────────────────────────────────────────

def run_query(query_name: str) -> int:
    """Run a single named query and store results. Returns facts inserted."""
    if query_name not in QUERIES:
        logger.error(f"Unknown query: {query_name}. Available: {list(QUERIES.keys())}")
        return 0

    query_config = QUERIES[query_name]
    logger.info(f"Running query: {query_name} — {query_config['description']}")

    # Ensure source exists
    source_id = ensure_source(
        name="Wikidata",
        url=f"https://www.wikidata.org/wiki/Wikidata:Main_Page",
        source_type="knowledge_base",
        tier="tier_1_official",
    )

    # Execute SPARQL
    rows = run_sparql_query(query_config["sparql"])

    if not rows:
        logger.warning(f"No results for query: {query_name}")
        return 0

    # Build facts
    builder_name = query_config["fact_builder"]
    builder_fn = FACT_BUILDERS[builder_name]
    facts = builder_fn(rows, source_id)
    logger.info(f"Built {len(facts)} facts from {len(rows)} results")

    # Insert into PostgreSQL
    inserted = insert_facts_batch(facts)
    logger.info(f"Inserted {inserted} new facts (duplicates skipped)")

    return inserted


def run_all_queries() -> dict:
    """Run all queries with delays between them. Returns summary."""
    summary = {}
    total = 0

    for query_name in QUERIES:
        count = run_query(query_name)
        summary[query_name] = count
        total += count

        logger.info(f"Waiting {REQUEST_DELAY}s before next query...")
        time.sleep(REQUEST_DELAY)

    logger.info(f"Wikidata scraping complete. Total new facts: {total}")
    logger.info(f"Total facts in database: {get_fact_count()}")
    return summary


# ─── Test Run Helpers ────────────────────────────────────────────────────────

def _insert_facts_tracked(facts: list[dict]) -> tuple[int, list[str]]:
    """Insert facts and return (inserted_count, list_of_inserted_fact_ids).

    Wraps insert_facts_batch by querying back for inserted IDs.
    """
    if not facts:
        return 0, []

    fact_texts = [f["fact_text"] for f in facts]
    inserted_count = insert_facts_batch(facts)

    from src.utils.db import get_pg
    conn = get_pg()
    cur = conn.cursor()
    inserted_ids = []
    for text in fact_texts:
        cur.execute("SELECT id FROM facts WHERE fact_text = %s", (text,))
        row = cur.fetchone()
        if row:
            inserted_ids.append(str(row["id"]))

    return inserted_count, inserted_ids


def _cleanup_test_facts(fact_ids: list[str]) -> int:
    """Delete facts by their IDs. Returns count deleted."""
    if not fact_ids:
        return 0

    from src.utils.db import get_pg
    conn = get_pg()
    cur = conn.cursor()
    deleted = 0
    for fid in fact_ids:
        cur.execute("DELETE FROM facts WHERE id = %s", (fid,))
        deleted += cur.rowcount
    conn.commit()
    return deleted


def _print_test_report(
    category_stats: dict[str, dict],
    all_facts: list[dict],
    all_inserted_ids: list[str],
) -> None:
    """Print the structured test-run report with quality checks."""
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
        click.echo(f"\n  Warnings:")
        for w in warnings:
            click.echo(f"    * {w}")

    if not warnings:
        click.echo(f"\n  No warnings — all checks passed.")


def run_test(cleanup: bool = False) -> None:
    """Run a limited test extraction: first 2 queries, insert, report."""
    source_id = ensure_source(
        name="Wikidata",
        url="https://www.wikidata.org/wiki/Wikidata:Main_Page",
        source_type="knowledge_base",
        tier="tier_1_official",
    )

    query_names = list(QUERIES.keys())[:TEST_RUN_QUERIES]
    category_stats = {}
    all_facts_collected = []
    all_inserted_ids = []

    for query_name in query_names:
        query_config = QUERIES[query_name]
        logger.info(f"[test-run] Running query: {query_name} — {query_config['description']}")

        # Execute SPARQL
        rows = run_sparql_query(query_config["sparql"])
        items_processed = len(rows)

        if not rows:
            logger.warning(f"No results for query: {query_name}")
            category_stats[query_name] = {
                "items_processed": 0,
                "facts_generated": 0,
                "facts_inserted": 0,
            }
            continue

        # Build facts
        builder_name = query_config["fact_builder"]
        builder_fn = FACT_BUILDERS[builder_name]
        facts = builder_fn(rows, source_id)
        logger.info(f"[test-run] Built {len(facts)} facts from {len(rows)} results")

        # Insert and track IDs
        inserted_count, inserted_ids = _insert_facts_tracked(facts)

        category_stats[query_name] = {
            "items_processed": items_processed,
            "facts_generated": len(facts),
            "facts_inserted": inserted_count,
        }
        all_facts_collected.extend(facts)
        all_inserted_ids.extend(inserted_ids)

        if query_name != query_names[-1]:
            logger.info(f"Waiting {REQUEST_DELAY}s before next query...")
            time.sleep(REQUEST_DELAY)

    # Report
    _print_test_report(category_stats, all_facts_collected, all_inserted_ids)

    # Cleanup
    if cleanup:
        deleted = _cleanup_test_facts(all_inserted_ids)
        click.echo(f"\n  Cleaned up {deleted} test facts from database.")


# ─── CLI ──────────────────────────────────────────────────────────────────────

@click.command()
@click.option("--query", "-q", type=str, help="Run a specific query (regions/grapes/appellations/producers/classifications)")
@click.option("--all", "run_all", is_flag=True, help="Run all queries")
@click.option("--list", "list_queries", is_flag=True, help="List available queries")
@click.option("--test-run", is_flag=True, help="Process first 2 queries, insert, and report")
@click.option("--cleanup", is_flag=True, help="With --test-run, delete inserted facts after reporting")
def main(query: Optional[str], run_all: bool, list_queries: bool, test_run: bool, cleanup: bool):
    """OenoBench Wikidata Scraper — Extract wine knowledge from Wikidata."""
    logger.add("data/logs/wikidata_{time}.log", rotation="10 MB")

    if list_queries:
        click.echo("\nAvailable queries:")
        for name, config in QUERIES.items():
            click.echo(f"  {name:20s} — {config['description']}")
        return

    if test_run:
        run_test(cleanup=cleanup)
        return

    if run_all:
        summary = run_all_queries()
        click.echo("\nSummary:")
        for name, count in summary.items():
            click.echo(f"  {name:20s}: {count} facts")
        click.echo(f"  {'TOTAL':20s}: {sum(summary.values())} facts")
        return

    if query:
        count = run_query(query)
        click.echo(f"\nInserted {count} new facts from '{query}' query.")
        return

    click.echo("Use --all to run all queries, or --query <name> for a specific one.")
    click.echo("Use --list to see available queries.")
    click.echo("Use --test-run to process first 2 queries, insert, and report.")


if __name__ == "__main__":
    main()
