"""
OenoBench — Kaggle Dataset Scraper

Extracts wine facts from Kaggle CSV datasets:
  - Wine Quality Dataset (UCI) — physicochemical statistics for red/white wines
  - Wine Reviews (zynicide/wine-reviews) — variety-region-producer associations

CSVs must be pre-downloaded to data/raw/kaggle/ before running.

Usage:
    python -m src.scrapers.kaggle_data --all
    python -m src.scrapers.kaggle_data --dataset wine-quality
    python -m src.scrapers.kaggle_data --dataset wine-reviews
    python -m src.scrapers.kaggle_data --dry-run
    python -m src.scrapers.kaggle_data --validate
    python -m src.scrapers.kaggle_data --list
"""

import os
import random
from collections import Counter, defaultdict
from pathlib import Path
from typing import Optional

import click
import numpy as np
import pandas as pd
from loguru import logger

from src.utils.facts import ensure_source, insert_facts_batch, get_fact_count

# ─── Configuration ────────────────────────────────────────────────────────────

USER_AGENT = "OenoBench-Research/1.0 (academic wine benchmark)"
RAW_DIR = Path("data/raw/kaggle")

# Expected file names in data/raw/kaggle/
WINE_QUALITY_RED = "winequality-red.csv"
WINE_QUALITY_WHITE = "winequality-white.csv"
WINE_REVIEWS_FILE = "winemag-data-130k-v2.csv"  # zynicide/wine-reviews

DATASETS = {
    "wine-quality": {
        "description": "UCI Wine Quality — physicochemical statistics for red/white wines",
        "files": [WINE_QUALITY_RED, WINE_QUALITY_WHITE],
        "tier": "tier_2_authoritative",
        "source_url": "https://www.kaggle.com/datasets/uciml/red-wine-quality-cortez-et-al-2009",
    },
    "wine-reviews": {
        "description": "Wine Reviews (zynicide) — 130K reviews with variety, region, winery",
        "files": [WINE_REVIEWS_FILE],
        "tier": "tier_3_reliable",
        "source_url": "https://www.kaggle.com/datasets/zynicide/wine-reviews",
    },
}


# ─── File Helpers ─────────────────────────────────────────────────────────────

def _check_files(dataset_name: str) -> list[Path]:
    """Check that required CSV files exist, return their paths or raise."""
    config = DATASETS[dataset_name]
    paths = []
    missing = []
    for fname in config["files"]:
        p = RAW_DIR / fname
        if p.exists():
            paths.append(p)
        else:
            missing.append(str(p))

    if missing:
        msg = (
            f"Missing files for '{dataset_name}':\n"
            + "\n".join(f"  - {m}" for m in missing)
            + "\n\nDownload instructions:\n"
        )
        if dataset_name == "wine-quality":
            msg += (
                "  1. Go to https://www.kaggle.com/datasets/uciml/red-wine-quality-cortez-et-al-2009\n"
                "  2. Download winequality-red.csv and winequality-white.csv\n"
                f"  3. Place them in {RAW_DIR}/\n"
                "  Or use: kaggle datasets download -d uciml/red-wine-quality-cortez-et-al-2009 -p data/raw/kaggle/ --unzip"
            )
        elif dataset_name == "wine-reviews":
            msg += (
                "  1. Go to https://www.kaggle.com/datasets/zynicide/wine-reviews\n"
                f"  2. Download {WINE_REVIEWS_FILE}\n"
                f"  3. Place it in {RAW_DIR}/\n"
                "  Or use: kaggle datasets download -d zynicide/wine-reviews -p data/raw/kaggle/ --unzip"
            )
        raise FileNotFoundError(msg)

    return paths


# ─── Wine Quality Fact Builders ───────────────────────────────────────────────

def _round_val(v: float, decimals: int = 1) -> str:
    """Round a float and return a clean string."""
    return f"{v:.{decimals}f}"


def _build_wine_quality_facts(source_id: str) -> list[dict]:
    """Build statistical summary facts from UCI Wine Quality CSVs."""
    red_path = RAW_DIR / WINE_QUALITY_RED
    white_path = RAW_DIR / WINE_QUALITY_WHITE

    # Read CSVs — UCI dataset uses semicolons as separator
    red_df = pd.read_csv(red_path, sep=";")
    white_df = pd.read_csv(white_path, sep=";")

    logger.info(f"Wine Quality: {len(red_df)} red rows, {len(white_df)} white rows")

    facts = []

    # --- pH statistics ---
    red_ph_lo, red_ph_hi = red_df["pH"].quantile(0.05), red_df["pH"].quantile(0.95)
    white_ph_lo, white_ph_hi = white_df["pH"].quantile(0.05), white_df["pH"].quantile(0.95)

    facts.append({
        "fact_text": f"Red wines typically have a pH between {_round_val(red_ph_lo)} and {_round_val(red_ph_hi)}.",
        "domain": "winemaking",
        "subdomain": "chemistry",
        "source_id": source_id,
        "entities": [],
        "confidence": 0.9,
        "tags": ["statistics", "pH", "red_wine", "uci"],
    })
    facts.append({
        "fact_text": f"White wines typically have a pH between {_round_val(white_ph_lo)} and {_round_val(white_ph_hi)}.",
        "domain": "winemaking",
        "subdomain": "chemistry",
        "source_id": source_id,
        "entities": [],
        "confidence": 0.9,
        "tags": ["statistics", "pH", "white_wine", "uci"],
    })

    # --- Alcohol statistics ---
    red_alc_lo, red_alc_hi = red_df["alcohol"].quantile(0.05), red_df["alcohol"].quantile(0.95)
    white_alc_lo, white_alc_hi = white_df["alcohol"].quantile(0.05), white_df["alcohol"].quantile(0.95)
    red_alc_med = red_df["alcohol"].median()
    white_alc_med = white_df["alcohol"].median()

    facts.append({
        "fact_text": (
            f"Red wines typically have an alcohol content between "
            f"{_round_val(red_alc_lo)}% and {_round_val(red_alc_hi)}% by volume."
        ),
        "domain": "winemaking",
        "subdomain": "chemistry",
        "source_id": source_id,
        "entities": [],
        "confidence": 0.9,
        "tags": ["statistics", "alcohol", "red_wine", "uci"],
    })
    facts.append({
        "fact_text": (
            f"White wines typically have an alcohol content between "
            f"{_round_val(white_alc_lo)}% and {_round_val(white_alc_hi)}% by volume."
        ),
        "domain": "winemaking",
        "subdomain": "chemistry",
        "source_id": source_id,
        "entities": [],
        "confidence": 0.9,
        "tags": ["statistics", "alcohol", "white_wine", "uci"],
    })
    facts.append({
        "fact_text": (
            f"The median alcohol content is {_round_val(red_alc_med)}% for red wines "
            f"and {_round_val(white_alc_med)}% for white wines."
        ),
        "domain": "winemaking",
        "subdomain": "chemistry",
        "source_id": source_id,
        "entities": [],
        "confidence": 0.9,
        "tags": ["statistics", "alcohol", "comparison", "uci"],
    })

    # --- Residual sugar ---
    red_rs_med = red_df["residual sugar"].median()
    white_rs_med = white_df["residual sugar"].median()

    facts.append({
        "fact_text": (
            f"White wines generally have higher residual sugar than red wines, "
            f"with a median of {_round_val(white_rs_med)} g/L compared to {_round_val(red_rs_med)} g/L."
        ),
        "domain": "winemaking",
        "subdomain": "chemistry",
        "source_id": source_id,
        "entities": [],
        "confidence": 0.9,
        "tags": ["statistics", "residual_sugar", "comparison", "uci"],
    })

    # --- Volatile acidity ---
    red_va_med = red_df["volatile acidity"].median()
    white_va_med = white_df["volatile acidity"].median()

    facts.append({
        "fact_text": (
            f"Red wines tend to have higher volatile acidity than white wines, "
            f"with a median of {_round_val(red_va_med, 2)} g/L compared to {_round_val(white_va_med, 2)} g/L."
        ),
        "domain": "winemaking",
        "subdomain": "chemistry",
        "source_id": source_id,
        "entities": [],
        "confidence": 0.9,
        "tags": ["statistics", "volatile_acidity", "comparison", "uci"],
    })

    # --- Fixed acidity ---
    red_fa_lo, red_fa_hi = red_df["fixed acidity"].quantile(0.05), red_df["fixed acidity"].quantile(0.95)
    white_fa_lo, white_fa_hi = white_df["fixed acidity"].quantile(0.05), white_df["fixed acidity"].quantile(0.95)

    facts.append({
        "fact_text": (
            f"Red wines typically have a fixed acidity between "
            f"{_round_val(red_fa_lo)} and {_round_val(red_fa_hi)} g/L of tartaric acid."
        ),
        "domain": "winemaking",
        "subdomain": "chemistry",
        "source_id": source_id,
        "entities": [],
        "confidence": 0.9,
        "tags": ["statistics", "fixed_acidity", "red_wine", "uci"],
    })
    facts.append({
        "fact_text": (
            f"White wines typically have a fixed acidity between "
            f"{_round_val(white_fa_lo)} and {_round_val(white_fa_hi)} g/L of tartaric acid."
        ),
        "domain": "winemaking",
        "subdomain": "chemistry",
        "source_id": source_id,
        "entities": [],
        "confidence": 0.9,
        "tags": ["statistics", "fixed_acidity", "white_wine", "uci"],
    })

    # --- Sulfur dioxide ---
    red_tso2_med = red_df["total sulfur dioxide"].median()
    white_tso2_med = white_df["total sulfur dioxide"].median()

    facts.append({
        "fact_text": (
            f"White wines typically contain more total sulfur dioxide than red wines, "
            f"with a median of {_round_val(white_tso2_med, 0)} mg/L compared to {_round_val(red_tso2_med, 0)} mg/L."
        ),
        "domain": "winemaking",
        "subdomain": "chemistry",
        "source_id": source_id,
        "entities": [],
        "confidence": 0.9,
        "tags": ["statistics", "sulfur_dioxide", "comparison", "uci"],
    })

    red_fso2_med = red_df["free sulfur dioxide"].median()
    white_fso2_med = white_df["free sulfur dioxide"].median()

    facts.append({
        "fact_text": (
            f"The median free sulfur dioxide level is {_round_val(white_fso2_med, 0)} mg/L in white wines "
            f"and {_round_val(red_fso2_med, 0)} mg/L in red wines."
        ),
        "domain": "winemaking",
        "subdomain": "chemistry",
        "source_id": source_id,
        "entities": [],
        "confidence": 0.9,
        "tags": ["statistics", "free_sulfur_dioxide", "comparison", "uci"],
    })

    # --- Density ---
    red_dens_med = red_df["density"].median()
    white_dens_med = white_df["density"].median()

    facts.append({
        "fact_text": (
            f"Red wines have a median density of {_round_val(red_dens_med, 4)} g/cm³, "
            f"while white wines have a median density of {_round_val(white_dens_med, 4)} g/cm³."
        ),
        "domain": "winemaking",
        "subdomain": "chemistry",
        "source_id": source_id,
        "entities": [],
        "confidence": 0.9,
        "tags": ["statistics", "density", "comparison", "uci"],
    })

    # --- Chlorides ---
    red_cl_med = red_df["chlorides"].median()
    white_cl_med = white_df["chlorides"].median()

    facts.append({
        "fact_text": (
            f"Red wines tend to have higher chloride levels than white wines, "
            f"with a median of {_round_val(red_cl_med, 3)} g/L compared to {_round_val(white_cl_med, 3)} g/L."
        ),
        "domain": "winemaking",
        "subdomain": "chemistry",
        "source_id": source_id,
        "entities": [],
        "confidence": 0.9,
        "tags": ["statistics", "chlorides", "comparison", "uci"],
    })

    # --- Citric acid ---
    red_ca_med = red_df["citric acid"].median()
    white_ca_med = white_df["citric acid"].median()

    facts.append({
        "fact_text": (
            f"The median citric acid concentration is {_round_val(red_ca_med, 2)} g/L in red wines "
            f"and {_round_val(white_ca_med, 2)} g/L in white wines."
        ),
        "domain": "winemaking",
        "subdomain": "chemistry",
        "source_id": source_id,
        "entities": [],
        "confidence": 0.9,
        "tags": ["statistics", "citric_acid", "comparison", "uci"],
    })

    # --- Quality score distribution ---
    red_quality_mean = red_df["quality"].mean()
    white_quality_mean = white_df["quality"].mean()
    red_quality_mode = red_df["quality"].mode().iloc[0]
    white_quality_mode = white_df["quality"].mode().iloc[0]

    facts.append({
        "fact_text": (
            f"In the UCI Wine Quality dataset, red wines have a mean quality score of "
            f"{_round_val(red_quality_mean)} and white wines have a mean quality score of "
            f"{_round_val(white_quality_mean)} on a 0-10 scale."
        ),
        "domain": "winemaking",
        "subdomain": "quality",
        "source_id": source_id,
        "entities": [],
        "confidence": 0.85,
        "tags": ["statistics", "quality", "comparison", "uci"],
    })
    facts.append({
        "fact_text": (
            f"The most common quality rating is {int(red_quality_mode)} for red wines "
            f"and {int(white_quality_mode)} for white wines in the UCI Wine Quality dataset."
        ),
        "domain": "winemaking",
        "subdomain": "quality",
        "source_id": source_id,
        "entities": [],
        "confidence": 0.85,
        "tags": ["statistics", "quality", "mode", "uci"],
    })

    # --- Sulphates ---
    red_sulph_med = red_df["sulphates"].median()
    white_sulph_med = white_df["sulphates"].median()

    facts.append({
        "fact_text": (
            f"Red wines have a median sulphate concentration of {_round_val(red_sulph_med, 2)} g/L, "
            f"compared to {_round_val(white_sulph_med, 2)} g/L in white wines."
        ),
        "domain": "winemaking",
        "subdomain": "chemistry",
        "source_id": source_id,
        "entities": [],
        "confidence": 0.9,
        "tags": ["statistics", "sulphates", "comparison", "uci"],
    })

    # --- Correlation-based facts: alcohol vs quality ---
    red_high_q = red_df[red_df["quality"] >= 7]["alcohol"].median()
    red_low_q = red_df[red_df["quality"] <= 4]["alcohol"].median()
    white_high_q = white_df[white_df["quality"] >= 7]["alcohol"].median()
    white_low_q = white_df[white_df["quality"] <= 4]["alcohol"].median()

    if not np.isnan(red_high_q) and not np.isnan(red_low_q):
        facts.append({
            "fact_text": (
                f"Higher-rated red wines tend to have higher alcohol content, "
                f"with a median of {_round_val(red_high_q)}% for quality 7+ "
                f"versus {_round_val(red_low_q)}% for quality 4 or below."
            ),
            "domain": "winemaking",
            "subdomain": "quality",
            "source_id": source_id,
            "entities": [],
            "confidence": 0.85,
            "tags": ["statistics", "alcohol", "quality", "correlation", "uci"],
        })

    if not np.isnan(white_high_q) and not np.isnan(white_low_q):
        facts.append({
            "fact_text": (
                f"Higher-rated white wines tend to have higher alcohol content, "
                f"with a median of {_round_val(white_high_q)}% for quality 7+ "
                f"versus {_round_val(white_low_q)}% for quality 4 or below."
            ),
            "domain": "winemaking",
            "subdomain": "quality",
            "source_id": source_id,
            "entities": [],
            "confidence": 0.85,
            "tags": ["statistics", "alcohol", "quality", "correlation", "uci"],
        })

    # --- Dataset size facts ---
    facts.append({
        "fact_text": (
            f"The UCI Wine Quality dataset contains {len(red_df)} red wine samples "
            f"and {len(white_df)} white wine samples from the Vinho Verde region of Portugal."
        ),
        "domain": "winemaking",
        "subdomain": "datasets",
        "source_id": source_id,
        "entities": [{"type": "region", "name": "Vinho Verde"}],
        "confidence": 1.0,
        "tags": ["dataset", "uci", "vinho_verde"],
    })

    logger.info(f"Wine Quality: generated {len(facts)} statistical facts")
    return facts


# ─── Wine Reviews Fact Builders ───────────────────────────────────────────────

def _build_wine_reviews_facts(source_id: str) -> list[dict]:
    """Build aggregate facts from zynicide/wine-reviews 130K dataset."""
    csv_path = RAW_DIR / WINE_REVIEWS_FILE
    df = pd.read_csv(csv_path)
    logger.info(f"Wine Reviews: loaded {len(df)} rows")

    # Clean up columns
    for col in ["variety", "province", "country", "winery", "region_1", "designation"]:
        if col in df.columns:
            df[col] = df[col].fillna("").str.strip()

    facts = []
    seen = set()

    # --- Variety-country associations (top varieties per country) ---
    variety_country = (
        df[df["variety"].str.len() > 0]
        .groupby(["country", "variety"])
        .size()
        .reset_index(name="count")
    )
    variety_country = variety_country[variety_country["count"] >= 20]

    for country, grp in variety_country.groupby("country"):
        if not country:
            continue
        top_varieties = grp.nlargest(5, "count")
        for _, row in top_varieties.iterrows():
            variety = row["variety"]
            key = f"variety_country:{variety}:{country}"
            if key not in seen:
                seen.add(key)
                facts.append({
                    "fact_text": f"{variety} is a widely reviewed grape variety in {country}.",
                    "domain": "grape_varieties",
                    "subdomain": country.lower().replace(" ", "_"),
                    "source_id": source_id,
                    "entities": [
                        {"type": "grape", "name": variety},
                        {"type": "country", "name": country},
                    ],
                    "confidence": 0.8,
                    "tags": ["variety", "country", "kaggle_reviews"],
                })

    # --- Variety-province (region) associations ---
    variety_province = (
        df[(df["variety"].str.len() > 0) & (df["province"].str.len() > 0)]
        .groupby(["province", "country", "variety"])
        .size()
        .reset_index(name="count")
    )
    variety_province = variety_province[variety_province["count"] >= 15]

    for (province, country), grp in variety_province.groupby(["province", "country"]):
        if not province or not country:
            continue
        top_v = grp.nlargest(3, "count")
        for _, row in top_v.iterrows():
            variety = row["variety"]
            key = f"variety_province:{variety}:{province}"
            if key not in seen:
                seen.add(key)
                facts.append({
                    "fact_text": f"{variety} is commonly produced in the {province} region of {country}.",
                    "domain": "wine_regions",
                    "subdomain": country.lower().replace(" ", "_"),
                    "source_id": source_id,
                    "entities": [
                        {"type": "grape", "name": variety},
                        {"type": "region", "name": province},
                        {"type": "country", "name": country},
                    ],
                    "confidence": 0.8,
                    "tags": ["variety", "region", "kaggle_reviews"],
                })

    # --- Producer-region associations (top wineries per province) ---
    winery_region = (
        df[(df["winery"].str.len() > 0) & (df["province"].str.len() > 0)]
        .groupby(["province", "country", "winery"])
        .size()
        .reset_index(name="count")
    )
    winery_region = winery_region[winery_region["count"] >= 10]

    for (province, country), grp in winery_region.groupby(["province", "country"]):
        if not province or not country:
            continue
        top_w = grp.nlargest(5, "count")
        for _, row in top_w.iterrows():
            winery = row["winery"]
            key = f"winery_region:{winery}:{province}"
            if key not in seen:
                seen.add(key)
                facts.append({
                    "fact_text": f"{winery} is a wine producer in the {province} region of {country}.",
                    "domain": "producers",
                    "subdomain": country.lower().replace(" ", "_"),
                    "source_id": source_id,
                    "entities": [
                        {"type": "producer", "name": winery},
                        {"type": "region", "name": province},
                        {"type": "country", "name": country},
                    ],
                    "confidence": 0.75,
                    "tags": ["producer", "region", "kaggle_reviews"],
                })

    # --- Country-level statistics ---
    country_stats = (
        df[df["country"].str.len() > 0]
        .groupby("country")
        .agg(
            review_count=("title", "size"),
            avg_points=("points", "mean"),
            median_price=("price", "median"),
            variety_count=("variety", "nunique"),
        )
        .reset_index()
    )
    country_stats = country_stats[country_stats["review_count"] >= 50]

    for _, row in country_stats.iterrows():
        country = row["country"]

        # Variety count per country
        key = f"country_varieties:{country}"
        if key not in seen and row["variety_count"] > 1:
            seen.add(key)
            facts.append({
                "fact_text": (
                    f"Wine reviews from {country} cover {int(row['variety_count'])} "
                    f"distinct grape varieties."
                ),
                "domain": "wine_regions",
                "subdomain": country.lower().replace(" ", "_"),
                "source_id": source_id,
                "entities": [{"type": "country", "name": country}],
                "confidence": 0.75,
                "tags": ["statistics", "variety_count", "country", "kaggle_reviews"],
            })

        # Average points per country
        key = f"country_avg_points:{country}"
        if key not in seen and not np.isnan(row["avg_points"]):
            seen.add(key)
            facts.append({
                "fact_text": (
                    f"Wines from {country} have an average critic rating of "
                    f"{_round_val(row['avg_points'])} points on a 100-point scale."
                ),
                "domain": "wine_regions",
                "subdomain": country.lower().replace(" ", "_"),
                "source_id": source_id,
                "entities": [{"type": "country", "name": country}],
                "confidence": 0.75,
                "tags": ["statistics", "rating", "country", "kaggle_reviews"],
            })

        # Median price per country
        key = f"country_median_price:{country}"
        if key not in seen and not np.isnan(row["median_price"]) and row["median_price"] > 0:
            seen.add(key)
            facts.append({
                "fact_text": (
                    f"The median price of reviewed wines from {country} is "
                    f"${_round_val(row['median_price'], 0)}."
                ),
                "domain": "wine_business",
                "subdomain": country.lower().replace(" ", "_"),
                "source_id": source_id,
                "entities": [{"type": "country", "name": country}],
                "confidence": 0.7,
                "tags": ["statistics", "price", "country", "kaggle_reviews"],
            })

    # --- Top-rated varieties globally ---
    variety_ratings = (
        df[(df["variety"].str.len() > 0) & (df["points"].notna())]
        .groupby("variety")
        .agg(avg_points=("points", "mean"), count=("points", "size"))
        .reset_index()
    )
    variety_ratings = variety_ratings[variety_ratings["count"] >= 50]
    top_rated = variety_ratings.nlargest(10, "avg_points")

    for _, row in top_rated.iterrows():
        variety = row["variety"]
        key = f"variety_avg_rating:{variety}"
        if key not in seen:
            seen.add(key)
            facts.append({
                "fact_text": (
                    f"{variety} wines have an average critic rating of "
                    f"{_round_val(row['avg_points'])} points across {int(row['count'])} reviews."
                ),
                "domain": "grape_varieties",
                "subdomain": "ratings",
                "source_id": source_id,
                "entities": [{"type": "grape", "name": variety}],
                "confidence": 0.75,
                "tags": ["statistics", "rating", "variety", "kaggle_reviews"],
            })

    # --- Most expensive varieties ---
    variety_price = (
        df[(df["variety"].str.len() > 0) & (df["price"].notna()) & (df["price"] > 0)]
        .groupby("variety")
        .agg(median_price=("price", "median"), count=("price", "size"))
        .reset_index()
    )
    variety_price = variety_price[variety_price["count"] >= 30]
    top_priced = variety_price.nlargest(10, "median_price")

    for _, row in top_priced.iterrows():
        variety = row["variety"]
        key = f"variety_median_price:{variety}"
        if key not in seen:
            seen.add(key)
            facts.append({
                "fact_text": (
                    f"{variety} wines have a median price of "
                    f"${_round_val(row['median_price'], 0)} per bottle."
                ),
                "domain": "wine_business",
                "subdomain": "pricing",
                "source_id": source_id,
                "entities": [{"type": "grape", "name": variety}],
                "confidence": 0.7,
                "tags": ["statistics", "price", "variety", "kaggle_reviews"],
            })

    # --- Region-level sub-region facts (region_1 within province) ---
    if "region_1" in df.columns:
        subregion_data = (
            df[
                (df["region_1"].str.len() > 0)
                & (df["province"].str.len() > 0)
                & (df["country"].str.len() > 0)
            ]
            .groupby(["region_1", "province", "country"])
            .size()
            .reset_index(name="count")
        )
        subregion_data = subregion_data[subregion_data["count"] >= 20]

        for _, row in subregion_data.iterrows():
            region = row["region_1"]
            province = row["province"]
            country = row["country"]
            # Skip if region == province (redundant)
            if region.lower() == province.lower():
                continue
            key = f"subregion:{region}:{province}"
            if key not in seen:
                seen.add(key)
                facts.append({
                    "fact_text": f"{region} is a wine-producing area within the {province} region of {country}.",
                    "domain": "wine_regions",
                    "subdomain": country.lower().replace(" ", "_"),
                    "source_id": source_id,
                    "entities": [
                        {"type": "region", "name": region},
                        {"type": "region", "name": province},
                        {"type": "country", "name": country},
                    ],
                    "confidence": 0.8,
                    "tags": ["region", "subregion", "kaggle_reviews"],
                })

    logger.info(f"Wine Reviews: generated {len(facts)} aggregate facts")
    return facts


# ─── Main Pipeline ────────────────────────────────────────────────────────────

def run_dataset(dataset_name: str, dry_run: bool = False) -> tuple[int, int]:
    """
    Process a single dataset and insert facts.
    Returns (generated_count, inserted_count).
    """
    if dataset_name not in DATASETS:
        logger.error(f"Unknown dataset: {dataset_name}. Available: {list(DATASETS.keys())}")
        return 0, 0

    config = DATASETS[dataset_name]
    logger.info(f"Processing dataset: {dataset_name} — {config['description']}")

    # Check files exist
    _check_files(dataset_name)

    # Register source
    source_id = ensure_source(
        name=f"Kaggle: {dataset_name}",
        url=config["source_url"],
        source_type="dataset",
        tier=config["tier"],
    )

    # Build facts
    if dataset_name == "wine-quality":
        facts = _build_wine_quality_facts(source_id)
    elif dataset_name == "wine-reviews":
        facts = _build_wine_reviews_facts(source_id)
    else:
        facts = []

    logger.info(f"Generated {len(facts)} facts from {dataset_name}")

    if dry_run:
        click.echo(f"\n[DRY RUN] Would insert {len(facts)} facts from '{dataset_name}'")
        click.echo(f"\nSample facts (first 10):")
        for i, f in enumerate(facts[:10], 1):
            click.echo(f"  {i}. [{f['domain']}] {f['fact_text']}")
        return len(facts), 0

    # Insert facts
    inserted = insert_facts_batch(facts)
    logger.info(f"Inserted {inserted} new facts from {dataset_name} ({len(facts) - inserted} duplicates skipped)")
    return len(facts), inserted


def run_all(dry_run: bool = False) -> dict:
    """Run all datasets. Returns summary dict."""
    summary = {}
    total_generated = 0
    total_inserted = 0

    for ds_name in DATASETS:
        try:
            generated, inserted = run_dataset(ds_name, dry_run=dry_run)
            summary[ds_name] = {"generated": generated, "inserted": inserted}
            total_generated += generated
            total_inserted += inserted
        except FileNotFoundError as e:
            logger.warning(f"Skipping {ds_name}: {e}")
            summary[ds_name] = {"generated": 0, "inserted": 0, "error": str(e)}

    logger.info(
        f"Kaggle scraping complete. Generated: {total_generated}, Inserted: {total_inserted}"
    )
    return summary


# ─── Validation ───────────────────────────────────────────────────────────────

def validate_facts() -> None:
    """Run quality checks on all Kaggle-sourced facts in the database."""
    from src.utils.db import get_pg

    conn = get_pg()
    cur = conn.cursor()

    # Fetch all facts from Kaggle sources
    cur.execute(
        """
        SELECT f.fact_text, f.domain, f.subdomain, f.entities, f.tags
        FROM facts f
        JOIN sources s ON f.source_id = s.id
        WHERE s.name LIKE 'Kaggle:%'
        """
    )
    rows = cur.fetchall()

    if not rows:
        click.echo("No Kaggle facts found in database. Run --all first.")
        return

    all_facts = [dict(r) for r in rows]
    total = len(all_facts)
    click.echo(f"\nValidating {total} Kaggle facts...\n")

    # --- Domain distribution ---
    domain_counts = Counter(f["domain"] for f in all_facts)
    subdomain_counts = Counter(
        f"{f['domain']}/{f['subdomain']}" for f in all_facts if f.get("subdomain")
    )

    click.echo("Domain distribution:")
    for domain, cnt in sorted(domain_counts.items(), key=lambda x: -x[1]):
        click.echo(f"  {domain:25s} {cnt} facts")

    click.echo("\nSubdomain distribution:")
    for sd, cnt in sorted(subdomain_counts.items(), key=lambda x: -x[1])[:15]:
        click.echo(f"  {sd:35s} {cnt} facts")

    # --- Quality checks ---
    too_short = [f for f in all_facts if len(f["fact_text"].split()) < 5]
    too_long = [f for f in all_facts if len(f["fact_text"].split()) > 50]

    # Check for facts that are just entity names with no predicate
    no_predicate = [
        f for f in all_facts
        if f["fact_text"].rstrip(".").strip().replace(",", "").replace(" ", "").isalpha()
        and len(f["fact_text"].split()) <= 3
    ]

    # Check entities populated
    import orjson
    entities_empty = 0
    for f in all_facts:
        ents = f.get("entities")
        if isinstance(ents, str):
            ents = orjson.loads(ents)
        if not ents:
            entities_empty += 1

    # Near-duplicate detection via string containment
    fact_texts = [f["fact_text"] for f in all_facts]
    near_dupes = set()
    for i in range(len(fact_texts)):
        for j in range(i + 1, len(fact_texts)):
            # Check if one fact fully contains another (ignoring case)
            fi = fact_texts[i].lower()
            fj = fact_texts[j].lower()
            if len(fi) > 20 and len(fj) > 20:
                if fi in fj or fj in fi:
                    near_dupes.add(i)
                    near_dupes.add(j)

    click.echo(f"\nQuality:")
    click.echo(f"  Too short (<5 words):  {len(too_short)} ({len(too_short)/total*100:.1f}%)")
    click.echo(f"  Too long (>50 words):  {len(too_long)} ({len(too_long)/total*100:.1f}%)")
    click.echo(f"  No predicate:          {len(no_predicate)} ({len(no_predicate)/total*100:.1f}%)")
    click.echo(f"  Missing entities:      {entities_empty} ({entities_empty/total*100:.1f}%)")
    click.echo(f"  Possible near-dupes:   {len(near_dupes)} ({len(near_dupes)/total*100:.1f}%)")

    # --- Check overlap with existing non-Kaggle facts ---
    cur.execute(
        """
        SELECT f.fact_text
        FROM facts f
        JOIN sources s ON f.source_id = s.id
        WHERE s.name NOT LIKE 'Kaggle:%'
        """
    )
    other_facts = {r["fact_text"] for r in cur.fetchall()}
    exact_overlap = sum(1 for f in all_facts if f["fact_text"] in other_facts)

    click.echo(f"\nOverlap with existing DB facts:")
    click.echo(f"  Exact duplicates with non-Kaggle sources: {exact_overlap}")

    if too_short:
        click.echo(f"\nExamples of too-short facts:")
        for f in too_short[:5]:
            click.echo(f'  - "{f["fact_text"]}"')

    if too_long:
        click.echo(f"\nExamples of too-long facts:")
        for f in too_long[:5]:
            click.echo(f'  - "{f["fact_text"][:100]}..."')

    # --- Sample facts ---
    click.echo(f"\nSample facts (10 random):")
    sample = random.sample(all_facts, min(10, len(all_facts)))
    for i, f in enumerate(sample, 1):
        click.echo(f'  {i}. [{f["domain"]}] "{f["fact_text"]}"')


# ─── CLI ──────────────────────────────────────────────────────────────────────

@click.command()
@click.option("--dataset", "-d", type=click.Choice(["wine-quality", "wine-reviews"]),
              help="Process a specific dataset")
@click.option("--all", "run_all_flag", is_flag=True, help="Process all datasets")
@click.option("--list", "list_datasets", is_flag=True, help="List available datasets")
@click.option("--dry-run", is_flag=True, help="Generate facts without inserting into DB")
@click.option("--validate", is_flag=True, help="Run quality checks on existing Kaggle facts")
def main(
    dataset: Optional[str],
    run_all_flag: bool,
    list_datasets: bool,
    dry_run: bool,
    validate: bool,
):
    """OenoBench Kaggle Dataset Scraper — Extract wine facts from Kaggle CSVs."""
    logger.add("data/logs/kaggle_data_{time}.log", rotation="10 MB")

    if list_datasets:
        click.echo("\nAvailable datasets:")
        for name, config in DATASETS.items():
            files = ", ".join(config["files"])
            click.echo(f"  {name:20s} — {config['description']}")
            click.echo(f"  {'':20s}   Files: {files}")
        click.echo(f"\n  CSV directory: {RAW_DIR}/")
        return

    if validate:
        validate_facts()
        return

    if run_all_flag:
        summary = run_all(dry_run=dry_run)
        click.echo("\nSummary:")
        for name, info in summary.items():
            if "error" in info:
                click.echo(f"  {name:20s}: SKIPPED (missing files)")
            else:
                click.echo(
                    f"  {name:20s}: {info['generated']} generated, {info['inserted']} inserted"
                )
        total_gen = sum(v["generated"] for v in summary.values())
        total_ins = sum(v["inserted"] for v in summary.values())
        click.echo(f"  {'TOTAL':20s}: {total_gen} generated, {total_ins} inserted")
        if not dry_run:
            click.echo(f"\n  Total facts in database: {get_fact_count()}")
        return

    if dataset:
        try:
            generated, inserted = run_dataset(dataset, dry_run=dry_run)
            if dry_run:
                click.echo(f"\n[DRY RUN] Generated {generated} facts from '{dataset}'.")
            else:
                click.echo(
                    f"\nInserted {inserted} new facts from '{dataset}' "
                    f"({generated - inserted} duplicates skipped)."
                )
        except FileNotFoundError as e:
            click.echo(str(e), err=True)
            raise SystemExit(1)
        return

    click.echo("Use --all to process all datasets, or --dataset <name> for a specific one.")
    click.echo("Use --list to see available datasets.")
    click.echo("Use --validate to run quality checks on existing facts.")


if __name__ == "__main__":
    main()
