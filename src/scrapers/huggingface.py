"""
OenoBench — HuggingFace Dataset Scraper

Extracts wine facts from HuggingFace datasets:
  - spawn99/wine-reviews (variety-region, producer-region, price tiers)
  - christopher/winesensed (variety-descriptor sensory patterns)

Usage:
    python -m src.scrapers.huggingface --all
    python -m src.scrapers.huggingface --dataset wine-reviews
    python -m src.scrapers.huggingface --dataset winesensed
    python -m src.scrapers.huggingface --dry-run
    python -m src.scrapers.huggingface --validate
    python -m src.scrapers.huggingface --list
"""

import random
from collections import defaultdict
from typing import Optional

import click
import pandas as pd
from datasets import load_dataset
from loguru import logger

from src.utils.facts import ensure_source, insert_facts_batch, get_fact_count

# ─── Configuration ────────────────────────────────────────────────────────────

USER_AGENT = "OenoBench-Research/1.0 (academic wine benchmark)"

DATASETS = {
    "wine-reviews": {
        "hf_path": "spawn99/wine-reviews",
        "description": "281K wine reviews with variety, region, producer, and price data",
        "source_name": "spawn99/wine-reviews (HuggingFace)",
        "source_url": "https://huggingface.co/datasets/spawn99/wine-reviews",
        "source_type": "dataset",
        "tier": "tier_2_authoritative",
    },
    "winesensed": {
        "hf_path": "christopher/winesensed",
        "description": "1M+ sensory profiling rows — wine-variety-descriptor associations",
        "source_name": "christopher/winesensed (HuggingFace)",
        "source_url": "https://huggingface.co/datasets/christopher/winesensed",
        "source_type": "dataset",
        "tier": "tier_2_authoritative",
    },
}

# Minimum occurrence thresholds
MIN_VARIETY_REGION_COUNT = 5
MIN_PRODUCER_REVIEWS = 3
MIN_PRICE_DATAPOINTS = 10
MIN_DESCRIPTOR_OCCURRENCES = 20
TOP_VARIETIES_PER_PROVINCE = 3


# ─── Wine Reviews Extraction ─────────────────────────────────────────────────

def _load_wine_reviews() -> pd.DataFrame:
    """Load the spawn99/wine-reviews dataset into a DataFrame."""
    logger.info("Loading spawn99/wine-reviews from HuggingFace...")
    ds = load_dataset("spawn99/wine-reviews", split="train")
    df = ds.to_pandas()
    logger.info(f"Loaded {len(df)} rows with columns: {list(df.columns)}")
    return df


def _extract_variety_region_facts(df: pd.DataFrame, source_id: str) -> list[dict]:
    """Extract variety-region association facts from wine reviews."""
    facts = []
    seen = set()

    # Filter rows with valid variety and province/country
    valid = df.dropna(subset=["variety", "country"])

    # Group by (variety, province, country)
    grouped = valid.groupby(
        ["variety", "province", "country"], dropna=True
    ).size().reset_index(name="count")
    grouped = grouped[grouped["count"] >= MIN_VARIETY_REGION_COUNT]

    for _, row in grouped.iterrows():
        variety = str(row["variety"]).strip()
        province = str(row["province"]).strip() if pd.notna(row.get("province")) else ""
        country = str(row["country"]).strip()

        if not variety or not country:
            continue

        location = f"the {province} region of {country}" if province else country
        key = f"variety_region:{variety}:{province}:{country}"
        if key not in seen:
            seen.add(key)
            facts.append({
                "fact_text": f"{variety} is grown in {location}.",
                "domain": "wine_regions",
                "subdomain": "variety_distribution",
                "source_id": source_id,
                "entities": [
                    {"type": "grape", "name": variety},
                    {"type": "region", "name": province or country},
                    {"type": "country", "name": country},
                ],
                "confidence": min(1.0, row["count"] / 50),
                "tags": ["variety", "region", "huggingface"],
            })

    logger.info(f"Extracted {len(facts)} variety-region facts")
    return facts


def _extract_top_variety_facts(df: pd.DataFrame, source_id: str) -> list[dict]:
    """Extract top varieties per province facts."""
    facts = []
    seen = set()

    valid = df.dropna(subset=["variety", "province", "country"])

    # Count varieties per province
    province_variety = valid.groupby(
        ["province", "country", "variety"]
    ).size().reset_index(name="count")

    # For each province, get top N varieties
    for (province, country), group in province_variety.groupby(["province", "country"]):
        province = str(province).strip()
        country = str(country).strip()
        if not province or not country:
            continue

        top = group.nlargest(TOP_VARIETIES_PER_PROVINCE, "count")
        if len(top) == 0:
            continue

        # Only report the #1 variety if it has meaningful count
        top_row = top.iloc[0]
        if top_row["count"] < MIN_VARIETY_REGION_COUNT:
            continue

        variety = str(top_row["variety"]).strip()
        key = f"top_variety:{province}:{variety}"
        if key not in seen:
            seen.add(key)
            facts.append({
                "fact_text": f"The most widely reviewed variety in {province} is {variety}.",
                "domain": "wine_regions",
                "subdomain": "variety_distribution",
                "source_id": source_id,
                "entities": [
                    {"type": "region", "name": province},
                    {"type": "grape", "name": variety},
                    {"type": "country", "name": country},
                ],
                "confidence": 0.9,
                "tags": ["variety", "ranking", "huggingface"],
            })

    logger.info(f"Extracted {len(facts)} top-variety-per-province facts")
    return facts


def _extract_producer_region_facts(df: pd.DataFrame, source_id: str) -> list[dict]:
    """Extract producer-region link facts."""
    facts = []
    seen = set()

    valid = df.dropna(subset=["winery", "province", "country"])

    grouped = valid.groupby(
        ["winery", "province", "country"]
    ).size().reset_index(name="count")
    grouped = grouped[grouped["count"] >= MIN_PRODUCER_REVIEWS]

    for _, row in grouped.iterrows():
        winery = str(row["winery"]).strip()
        province = str(row["province"]).strip()
        country = str(row["country"]).strip()

        if not winery or not province:
            continue

        key = f"producer_region:{winery}:{province}"
        if key not in seen:
            seen.add(key)
            location = f"{province}, {country}" if country else province
            facts.append({
                "fact_text": f"{winery} is a producer in {location}.",
                "domain": "producers",
                "subdomain": "location",
                "source_id": source_id,
                "entities": [
                    {"type": "producer", "name": winery},
                    {"type": "region", "name": province},
                    {"type": "country", "name": country},
                ],
                "confidence": min(1.0, row["count"] / 20),
                "tags": ["producer", "region", "huggingface"],
            })

    logger.info(f"Extracted {len(facts)} producer-region facts")
    return facts


def _extract_region_country_facts(df: pd.DataFrame, source_id: str) -> list[dict]:
    """Extract unique province→country mappings."""
    facts = []
    seen = set()

    valid = df.dropna(subset=["province", "country"])
    mappings = valid[["province", "country"]].drop_duplicates()

    for _, row in mappings.iterrows():
        province = str(row["province"]).strip()
        country = str(row["country"]).strip()

        if not province or not country:
            continue

        key = f"region_country:{province}:{country}"
        if key not in seen:
            seen.add(key)
            facts.append({
                "fact_text": f"{province} is a wine region in {country}.",
                "domain": "wine_regions",
                "subdomain": country.lower().replace(" ", "_"),
                "source_id": source_id,
                "entities": [
                    {"type": "region", "name": province},
                    {"type": "country", "name": country},
                ],
                "confidence": 1.0,
                "tags": ["region", "geography", "huggingface"],
            })

    logger.info(f"Extracted {len(facts)} region-country facts")
    return facts


def _extract_price_tier_facts(df: pd.DataFrame, source_id: str) -> list[dict]:
    """Extract median price per variety-province combination."""
    facts = []
    seen = set()

    valid = df.dropna(subset=["variety", "province", "price"])
    valid = valid[valid["price"] > 0]

    grouped = valid.groupby(["variety", "province"]).agg(
        median_price=("price", "median"),
        count=("price", "size"),
    ).reset_index()
    grouped = grouped[grouped["count"] >= MIN_PRICE_DATAPOINTS]

    for _, row in grouped.iterrows():
        variety = str(row["variety"]).strip()
        province = str(row["province"]).strip()
        median = int(round(row["median_price"]))

        if not variety or not province or median <= 0:
            continue

        key = f"price_tier:{variety}:{province}"
        if key not in seen:
            seen.add(key)
            facts.append({
                "fact_text": f"{variety} wines from {province} have a median price of ${median}.",
                "domain": "wine_business",
                "subdomain": "pricing",
                "source_id": source_id,
                "entities": [
                    {"type": "grape", "name": variety},
                    {"type": "region", "name": province},
                ],
                "confidence": min(1.0, row["count"] / 100),
                "tags": ["price", "variety", "huggingface"],
            })

    logger.info(f"Extracted {len(facts)} price-tier facts")
    return facts


def extract_wine_reviews(dry_run: bool = False) -> list[dict]:
    """Full extraction pipeline for the wine-reviews dataset."""
    cfg = DATASETS["wine-reviews"]
    df = _load_wine_reviews()

    if not dry_run:
        source_id = ensure_source(
            name=cfg["source_name"],
            url=cfg["source_url"],
            source_type=cfg["source_type"],
            tier=cfg["tier"],
        )
    else:
        source_id = "dry-run"

    all_facts = []
    all_facts.extend(_extract_variety_region_facts(df, source_id))
    all_facts.extend(_extract_top_variety_facts(df, source_id))
    all_facts.extend(_extract_producer_region_facts(df, source_id))
    all_facts.extend(_extract_region_country_facts(df, source_id))
    all_facts.extend(_extract_price_tier_facts(df, source_id))

    logger.info(f"Total wine-reviews facts: {len(all_facts)}")
    return all_facts


# ─── WineSensed Extraction ───────────────────────────────────────────────────

def _load_winesensed() -> pd.DataFrame:
    """Load the christopher/winesensed dataset into a DataFrame."""
    logger.info("Loading christopher/winesensed from HuggingFace...")
    ds = load_dataset("christopher/winesensed", split="train")
    df = ds.to_pandas()
    logger.info(f"Loaded {len(df)} rows with columns: {list(df.columns)}")
    # Print sample for schema exploration
    logger.info(f"Sample rows:\n{df.head(5).to_string()}")
    logger.info(f"Dtypes:\n{df.dtypes}")
    return df


def _extract_variety_descriptor_facts(df: pd.DataFrame, source_id: str) -> list[dict]:
    """Extract variety-descriptor association facts from sensory data.

    Adapts to the actual column schema found in the dataset.
    Looks for columns containing variety/grape info and descriptor/aroma info.
    """
    facts = []
    seen = set()

    columns_lower = {c.lower(): c for c in df.columns}

    # Identify variety column
    variety_col = None
    for candidate in ["variety", "grape", "grape_variety", "wine_variety", "wine"]:
        if candidate in columns_lower:
            variety_col = columns_lower[candidate]
            break

    # Identify descriptor/aroma columns
    descriptor_col = None
    for candidate in ["descriptor", "aroma", "flavor", "note", "attribute",
                       "sensory_descriptor", "aroma_descriptor"]:
        if candidate in columns_lower:
            descriptor_col = columns_lower[candidate]
            break

    if variety_col is None or descriptor_col is None:
        # Fallback: try to detect from schema
        logger.warning(
            f"Could not auto-detect variety/descriptor columns. "
            f"Available columns: {list(df.columns)}"
        )
        # Try a broader heuristic: any column with few unique string values could be variety,
        # any column with many unique string values could be descriptors
        str_cols = [c for c in df.columns if df[c].dtype == "object"]
        if len(str_cols) >= 2:
            unique_counts = {c: df[c].nunique() for c in str_cols}
            sorted_cols = sorted(unique_counts.items(), key=lambda x: x[1])
            # Fewer uniques = likely variety, more uniques = likely descriptors
            variety_col = sorted_cols[0][0]
            descriptor_col = sorted_cols[-1][0] if sorted_cols[-1][0] != variety_col else sorted_cols[-2][0]
            logger.info(f"Heuristic: using '{variety_col}' as variety, '{descriptor_col}' as descriptor")
        else:
            logger.error("Cannot determine variety/descriptor columns; skipping winesensed extraction")
            return facts

    logger.info(f"Using variety column: '{variety_col}', descriptor column: '{descriptor_col}'")

    valid = df.dropna(subset=[variety_col, descriptor_col])

    # Group by (variety, descriptor) and count occurrences
    grouped = valid.groupby([variety_col, descriptor_col]).size().reset_index(name="count")
    grouped = grouped[grouped["count"] >= MIN_DESCRIPTOR_OCCURRENCES]

    # For each variety, collect top descriptors
    variety_descriptors = defaultdict(list)
    for _, row in grouped.iterrows():
        variety = str(row[variety_col]).strip()
        descriptor = str(row[descriptor_col]).strip()
        if variety and descriptor:
            variety_descriptors[variety].append((descriptor, row["count"]))

    for variety, desc_list in variety_descriptors.items():
        # Sort by count descending, take top 5 descriptors
        desc_list.sort(key=lambda x: x[1], reverse=True)
        top_descriptors = [d[0] for d in desc_list[:5]]

        if len(top_descriptors) < 2:
            continue

        key = f"variety_descriptors:{variety}"
        if key not in seen:
            seen.add(key)
            # Format descriptor list nicely
            if len(top_descriptors) == 2:
                desc_text = f"{top_descriptors[0]} and {top_descriptors[1]}"
            else:
                desc_text = ", ".join(top_descriptors[:-1]) + f", and {top_descriptors[-1]}"

            facts.append({
                "fact_text": f"{variety} is commonly associated with {desc_text} aromas.",
                "domain": "grape_varieties",
                "subdomain": "sensory_profile",
                "source_id": source_id,
                "entities": [
                    {"type": "grape", "name": variety},
                ],
                "confidence": 0.85,
                "tags": ["sensory", "aroma", "descriptor", "huggingface"],
            })

    logger.info(f"Extracted {len(facts)} variety-descriptor facts")
    return facts


def extract_winesensed(dry_run: bool = False) -> list[dict]:
    """Full extraction pipeline for the winesensed dataset."""
    cfg = DATASETS["winesensed"]
    df = _load_winesensed()

    if not dry_run:
        source_id = ensure_source(
            name=cfg["source_name"],
            url=cfg["source_url"],
            source_type=cfg["source_type"],
            tier=cfg["tier"],
        )
    else:
        source_id = "dry-run"

    all_facts = _extract_variety_descriptor_facts(df, source_id)
    logger.info(f"Total winesensed facts: {len(all_facts)}")
    return all_facts


# ─── Validation ───────────────────────────────────────────────────────────────

def validate_facts(facts: list[dict]) -> None:
    """Run quality checks on extracted facts and print a report."""
    if not facts:
        click.echo("No facts to validate.")
        return

    total = len(facts)

    # (a) Domain/subdomain distribution
    domain_counts = defaultdict(int)
    subdomain_counts = defaultdict(int)
    for f in facts:
        domain_counts[f["domain"]] += 1
        sub = f.get("subdomain") or "(none)"
        subdomain_counts[f"{f['domain']}/{sub}"] += 1

    click.echo("\nDomain distribution:")
    for domain, count in sorted(domain_counts.items()):
        click.echo(f"  {domain:25s}: {count} facts")

    click.echo("\nSubdomain distribution:")
    for sub, count in sorted(subdomain_counts.items()):
        click.echo(f"  {sub:40s}: {count} facts")

    # (b) Length checks
    too_short = [f for f in facts if len(f["fact_text"].split()) < 5]
    too_long = [f for f in facts if len(f["fact_text"].split()) > 50]
    click.echo(f"\nQuality:")
    click.echo(f"  Too short (<5 words):  {len(too_short)} ({100*len(too_short)/total:.1f}%)")
    click.echo(f"  Too long (>50 words):  {len(too_long)} ({100*len(too_long)/total:.1f}%)")

    # (c) Entity-name-only facts (no predicate)
    no_predicate = [f for f in facts if f["fact_text"].rstrip(".").strip().split() == [f["fact_text"].rstrip(".").strip()]]
    click.echo(f"  No-predicate facts:    {len(no_predicate)} ({100*len(no_predicate)/total:.1f}%)")

    # (d) Near-duplicate check (substring containment)
    near_dupes = 0
    fact_texts = [f["fact_text"] for f in facts]
    # Sample-based check for performance (check 500 random pairs)
    sample_size = min(len(fact_texts), 500)
    sampled = random.sample(fact_texts, sample_size)
    for i, a in enumerate(sampled):
        for b in sampled[i + 1:]:
            a_stripped = a.rstrip(".")
            b_stripped = b.rstrip(".")
            if len(a_stripped) > 20 and len(b_stripped) > 20:
                if a_stripped in b_stripped or b_stripped in a_stripped:
                    near_dupes += 1
    click.echo(f"  Possible near-dupes:   {near_dupes} (sampled {sample_size} facts)")

    # (e) Entity population rate
    with_entities = sum(1 for f in facts if f.get("entities") and len(f["entities"]) > 0)
    missing_entities = total - with_entities
    click.echo(f"  Missing entities:      {missing_entities} ({100*missing_entities/total:.1f}%)")

    # (f) Random samples
    click.echo(f"\nSample facts ({min(10, total)} random):")
    samples = random.sample(facts, min(10, total))
    for i, f in enumerate(samples, 1):
        click.echo(f'  {i:2d}. "{f["fact_text"]}"')


# ─── Main Pipeline ────────────────────────────────────────────────────────────

def run_dataset(dataset_name: str, dry_run: bool = False) -> int:
    """Run extraction for a single dataset. Returns count of facts inserted."""
    if dataset_name not in DATASETS:
        logger.error(f"Unknown dataset: {dataset_name}. Available: {list(DATASETS.keys())}")
        return 0

    if dataset_name == "wine-reviews":
        facts = extract_wine_reviews(dry_run=dry_run)
    elif dataset_name == "winesensed":
        facts = extract_winesensed(dry_run=dry_run)
    else:
        return 0

    if dry_run:
        click.echo(f"\n[DRY RUN] Would insert {len(facts)} facts from {dataset_name}")
        validate_facts(facts)
        return len(facts)

    inserted = insert_facts_batch(facts)
    logger.info(f"Inserted {inserted} new facts from {dataset_name} (duplicates skipped)")
    return inserted


def run_all(dry_run: bool = False) -> dict:
    """Run extraction for all datasets. Returns summary."""
    summary = {}
    total = 0

    for name in DATASETS:
        count = run_dataset(name, dry_run=dry_run)
        summary[name] = count
        total += count

    logger.info(f"HuggingFace scraping complete. Total facts: {total}")
    if not dry_run:
        logger.info(f"Total facts in database: {get_fact_count()}")
    return summary


# ─── CLI ──────────────────────────────────────────────────────────────────────

@click.command()
@click.option("--dataset", "-d", type=str, help="Run a specific dataset (wine-reviews/winesensed)")
@click.option("--all", "run_all_flag", is_flag=True, help="Run all datasets")
@click.option("--list", "list_datasets", is_flag=True, help="List available datasets")
@click.option("--dry-run", "dry_run", is_flag=True, help="Extract facts but do not insert into DB")
@click.option("--validate", "validate_flag", is_flag=True, help="Run quality checks on extracted facts")
def main(
    dataset: Optional[str],
    run_all_flag: bool,
    list_datasets: bool,
    dry_run: bool,
    validate_flag: bool,
):
    """OenoBench HuggingFace Scraper — Extract wine knowledge from HuggingFace datasets."""
    logger.add("data/logs/huggingface_{time}.log", rotation="10 MB")

    if list_datasets:
        click.echo("\nAvailable datasets:")
        for name, cfg in DATASETS.items():
            click.echo(f"  {name:20s} — {cfg['description']}")
        return

    if validate_flag:
        # Extract all facts in dry-run mode and validate
        click.echo("Running validation on all datasets...")
        all_facts = []
        for name in DATASETS:
            if name == "wine-reviews":
                all_facts.extend(extract_wine_reviews(dry_run=True))
            elif name == "winesensed":
                all_facts.extend(extract_winesensed(dry_run=True))
        validate_facts(all_facts)
        return

    if run_all_flag:
        summary = run_all(dry_run=dry_run)
        click.echo("\nSummary:")
        for name, count in summary.items():
            label = f"{name} (dry-run)" if dry_run else name
            click.echo(f"  {label:30s}: {count} facts")
        click.echo(f"  {'TOTAL':30s}: {sum(summary.values())} facts")
        return

    if dataset:
        count = run_dataset(dataset, dry_run=dry_run)
        if dry_run:
            click.echo(f"\n[DRY RUN] {count} facts extracted from '{dataset}'.")
        else:
            click.echo(f"\nInserted {count} new facts from '{dataset}'.")
        return

    click.echo("Use --all to run all datasets, or --dataset <name> for a specific one.")
    click.echo("Use --list to see available datasets.")
    click.echo("Use --dry-run to preview without inserting.")
    click.echo("Use --validate to run quality checks.")


if __name__ == "__main__":
    main()
