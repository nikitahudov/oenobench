"""
OenoBench — INAO Scraper

Extracts French wine appellation data from INAO (Institut national de
l'origine et de la qualité), the French government authority for appellations.

Primary data sources:
  1. data.gouv.fr open-data CSV — "Aires et produits AOC/AOP et IGP"
     (lists geographic areas and associated products under open licence)
  2. data.gouv.fr open-data CSV — "Aires géographiques des AOC/AOP"
     (commune-level geographic mapping with department info)
  3. INAO website (https://www.inao.gouv.fr) for individual appellation
     detail pages and PDF cahiers des charges (rate-limited, may 403)

The scraper generates atomic English-language facts about French wine
appellations from INAO's official regulatory data.

Usage:
    python -m src.scrapers.inao --all
    python -m src.scrapers.inao --region rhone
    python -m src.scrapers.inao --dry-run
    python -m src.scrapers.inao --validate
    python -m src.scrapers.inao --list
"""

import csv
import io
import json
import os
import random
import re
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Optional

import click
import requests
from loguru import logger

from src.utils.facts import ensure_source, insert_facts_batch, get_fact_count

# ─── Configuration ────────────────────────────────────────────────────────────

USER_AGENT = "OenoBench-Research/1.0 (academic wine benchmark)"
REQUEST_DELAY = 5  # seconds between requests to INAO (government site)

# data.gouv.fr open-data URLs (Licence Ouverte / Open Licence)
# Dataset: "Aires et produits AOC/AOP et IGP" by INAO
DATAGOUV_PRODUCTS_DATASET = "aires-et-produits-aoc-aop-et-igp"
DATAGOUV_API_BASE = "https://www.data.gouv.fr/api/1"

# OpenDataSoft mirror (alternative if data.gouv.fr is unavailable)
ODS_API_BASE = "https://public.opendatasoft.com/api/explore/v2.1/catalog/datasets"
ODS_DATASET_ID = "aires-et-produits-aocaop-et-igp"

# INAO website (may block scraping, used as fallback)
INAO_BASE_URL = "https://www.inao.gouv.fr"

# Source tier
SOURCE_TIER = "tier_1_official"

# Local cache path
CACHE_DIR = Path("data/raw")
PRODUCTS_CACHE = CACHE_DIR / "inao_products.csv"
AREAS_CACHE = CACHE_DIR / "inao_areas.csv"
TEMPLATE_PATH = CACHE_DIR / "inao_template.json"

# ─── French Region Mapping ───────────────────────────────────────────────────
# Maps French department numbers to wine regions for geographic hierarchy.

DEPARTMENT_TO_REGION = {
    # Alsace
    "67": "Alsace", "68": "Alsace",
    # Beaujolais / Burgundy
    "21": "Burgundy", "58": "Burgundy", "71": "Burgundy", "89": "Burgundy",
    "69": "Beaujolais",
    # Bordeaux
    "33": "Bordeaux",
    # Champagne
    "10": "Champagne", "51": "Champagne", "02": "Champagne",
    "52": "Champagne", "77": "Champagne",
    # Corsica
    "2A": "Corsica", "2B": "Corsica", "20": "Corsica",
    # Jura
    "39": "Jura",
    # Languedoc-Roussillon
    "11": "Languedoc-Roussillon", "30": "Languedoc-Roussillon",
    "34": "Languedoc-Roussillon", "48": "Languedoc-Roussillon",
    "66": "Languedoc-Roussillon",
    # Loire Valley
    "18": "Loire Valley", "36": "Loire Valley", "37": "Loire Valley",
    "41": "Loire Valley", "44": "Loire Valley", "45": "Loire Valley",
    "49": "Loire Valley", "72": "Loire Valley", "79": "Loire Valley",
    "85": "Loire Valley", "86": "Loire Valley",
    # Provence
    "04": "Provence", "06": "Provence", "13": "Provence",
    "83": "Provence", "84": "Provence",
    # Rhône Valley
    "07": "Rhône Valley", "26": "Rhône Valley", "42": "Rhône Valley",
    "38": "Rhône Valley",
    # Savoie
    "73": "Savoie", "74": "Savoie",
    # South-West
    "12": "South-West", "24": "South-West", "31": "South-West",
    "32": "South-West", "40": "South-West", "46": "South-West",
    "47": "South-West", "64": "South-West", "65": "South-West",
    "81": "South-West", "82": "South-West",
}

# Normalized region name lookup for --region filtering
REGION_ALIASES = {
    "alsace": "Alsace",
    "beaujolais": "Beaujolais",
    "bordeaux": "Bordeaux",
    "burgundy": "Burgundy",
    "bourgogne": "Burgundy",
    "champagne": "Champagne",
    "corsica": "Corsica",
    "corse": "Corsica",
    "jura": "Jura",
    "languedoc": "Languedoc-Roussillon",
    "languedoc-roussillon": "Languedoc-Roussillon",
    "roussillon": "Languedoc-Roussillon",
    "loire": "Loire Valley",
    "loire valley": "Loire Valley",
    "val de loire": "Loire Valley",
    "provence": "Provence",
    "rhone": "Rhône Valley",
    "rhône": "Rhône Valley",
    "rhone valley": "Rhône Valley",
    "rhône valley": "Rhône Valley",
    "savoie": "Savoie",
    "south-west": "South-West",
    "sud-ouest": "South-West",
    "southwest": "South-West",
}

# ─── Wine-related product categories ─────────────────────────────────────────
# The INAO dataset covers all AOC/AOP/IGP products (cheese, olive oil, etc.).
# We filter to wine-related entries only.

WINE_CATEGORIES = {
    "vins", "vin", "wine", "wines",
    "eaux-de-vie", "eau-de-vie",
    "cidre", "cidres",
    "mousseux",
}

# Keywords that identify wine products in the PRODUIT field
WINE_KEYWORDS = [
    "vin", "blanc", "rouge", "rosé", "rose", "mousseux", "pétillant",
    "crémant", "cremant", "champagne", "clairette", "liquoreux",
    "vendanges tardives", "sélection de grains nobles",
    "muscat", "rancio", "primeur", "nouveau", "supérieur",
    "grand cru", "premier cru", "1er cru", "villages",
]

# Sign types in the CSV
SIGN_TYPES = {
    "AOC": "AOC",
    "AOP": "AOP",
    "IGP": "IGP",
    "AOVDQS": "AOVDQS",
}

# ─── Known Appellation Data ──────────────────────────────────────────────────
# Curated reference data for major appellations where the open-data CSV
# only provides names and sign types.  These facts come from publicly
# available regulatory summaries and are rephrased as atomic facts.

KNOWN_APPELLATIONS = {
    "Châteauneuf-du-Pape": {
        "region": "Rhône Valley",
        "sign": "AOC",
        "colors": ["red", "white"],
        "grapes_red": ["Grenache", "Syrah", "Mourvèdre", "Cinsault",
                       "Counoise", "Muscardin", "Vaccarèse", "Terret Noir",
                       "Clairette", "Bourboulenc", "Roussanne", "Picpoul"],
        "grapes_white": ["Grenache Blanc", "Clairette", "Bourboulenc",
                         "Roussanne", "Picpoul", "Picardan"],
        "max_yield_hl_ha": 35,
        "min_alcohol_red": 12.5,
        "min_alcohol_white": 12.5,
    },
    "Margaux": {
        "region": "Bordeaux",
        "sign": "AOC",
        "colors": ["red"],
        "grapes_red": ["Cabernet Sauvignon", "Merlot", "Cabernet Franc",
                       "Petit Verdot", "Malbec"],
        "max_yield_hl_ha": 57,
        "min_alcohol_red": 11.0,
    },
    "Saint-Émilion": {
        "region": "Bordeaux",
        "sign": "AOC",
        "colors": ["red"],
        "grapes_red": ["Merlot", "Cabernet Franc", "Cabernet Sauvignon"],
        "max_yield_hl_ha": 53,
        "min_alcohol_red": 11.0,
    },
    "Pauillac": {
        "region": "Bordeaux",
        "sign": "AOC",
        "colors": ["red"],
        "grapes_red": ["Cabernet Sauvignon", "Merlot", "Cabernet Franc",
                       "Petit Verdot", "Malbec"],
        "max_yield_hl_ha": 57,
        "min_alcohol_red": 11.0,
    },
    "Pommard": {
        "region": "Burgundy",
        "sign": "AOC",
        "colors": ["red"],
        "grapes_red": ["Pinot Noir"],
        "max_yield_hl_ha": 42,
        "min_alcohol_red": 10.5,
    },
    "Meursault": {
        "region": "Burgundy",
        "sign": "AOC",
        "colors": ["white", "red"],
        "grapes_white": ["Chardonnay"],
        "grapes_red": ["Pinot Noir"],
        "max_yield_hl_ha": 50,
        "min_alcohol_white": 11.0,
        "min_alcohol_red": 10.5,
    },
    "Chablis": {
        "region": "Burgundy",
        "sign": "AOC",
        "colors": ["white"],
        "grapes_white": ["Chardonnay"],
        "max_yield_hl_ha": 60,
        "min_alcohol_white": 10.0,
    },
    "Chablis Grand Cru": {
        "region": "Burgundy",
        "sign": "AOC",
        "colors": ["white"],
        "grapes_white": ["Chardonnay"],
        "max_yield_hl_ha": 54,
        "min_alcohol_white": 11.0,
    },
    "Sancerre": {
        "region": "Loire Valley",
        "sign": "AOC",
        "colors": ["white", "red", "rosé"],
        "grapes_white": ["Sauvignon Blanc"],
        "grapes_red": ["Pinot Noir"],
        "max_yield_hl_ha": 60,
        "min_alcohol_white": 10.5,
        "min_alcohol_red": 10.0,
    },
    "Pouilly-Fumé": {
        "region": "Loire Valley",
        "sign": "AOC",
        "colors": ["white"],
        "grapes_white": ["Sauvignon Blanc"],
        "max_yield_hl_ha": 60,
        "min_alcohol_white": 11.0,
    },
    "Muscadet": {
        "region": "Loire Valley",
        "sign": "AOC",
        "colors": ["white"],
        "grapes_white": ["Melon de Bourgogne"],
        "max_yield_hl_ha": 55,
        "min_alcohol_white": 9.5,
    },
    "Vouvray": {
        "region": "Loire Valley",
        "sign": "AOC",
        "colors": ["white"],
        "grapes_white": ["Chenin Blanc"],
        "max_yield_hl_ha": 52,
        "min_alcohol_white": 11.0,
    },
    "Hermitage": {
        "region": "Rhône Valley",
        "sign": "AOC",
        "colors": ["red", "white"],
        "grapes_red": ["Syrah"],
        "grapes_white": ["Marsanne", "Roussanne"],
        "max_yield_hl_ha": 40,
        "min_alcohol_red": 10.5,
        "min_alcohol_white": 10.5,
    },
    "Côte-Rôtie": {
        "region": "Rhône Valley",
        "sign": "AOC",
        "colors": ["red"],
        "grapes_red": ["Syrah", "Viognier"],
        "max_yield_hl_ha": 40,
        "min_alcohol_red": 10.0,
    },
    "Condrieu": {
        "region": "Rhône Valley",
        "sign": "AOC",
        "colors": ["white"],
        "grapes_white": ["Viognier"],
        "max_yield_hl_ha": 37,
        "min_alcohol_white": 11.0,
    },
    "Côtes du Rhône": {
        "region": "Rhône Valley",
        "sign": "AOC",
        "colors": ["red", "white", "rosé"],
        "grapes_red": ["Grenache", "Syrah", "Mourvèdre"],
        "grapes_white": ["Grenache Blanc", "Clairette", "Marsanne",
                         "Roussanne", "Bourboulenc", "Viognier"],
        "max_yield_hl_ha": 51,
        "min_alcohol_red": 11.0,
    },
    "Gigondas": {
        "region": "Rhône Valley",
        "sign": "AOC",
        "colors": ["red", "rosé"],
        "grapes_red": ["Grenache", "Syrah", "Mourvèdre"],
        "max_yield_hl_ha": 36,
        "min_alcohol_red": 12.5,
    },
    "Bandol": {
        "region": "Provence",
        "sign": "AOC",
        "colors": ["red", "white", "rosé"],
        "grapes_red": ["Mourvèdre", "Grenache", "Cinsault"],
        "grapes_white": ["Clairette", "Ugni Blanc", "Bourboulenc"],
        "max_yield_hl_ha": 40,
        "min_alcohol_red": 11.0,
        "aging_months_red": 18,
    },
    "Côtes de Provence": {
        "region": "Provence",
        "sign": "AOC",
        "colors": ["red", "white", "rosé"],
        "grapes_red": ["Grenache", "Syrah", "Cinsault", "Mourvèdre",
                       "Tibouren", "Cabernet Sauvignon"],
        "max_yield_hl_ha": 55,
        "min_alcohol_red": 11.0,
    },
    "Champagne": {
        "region": "Champagne",
        "sign": "AOC",
        "colors": ["white", "rosé"],
        "grapes_white": ["Chardonnay", "Pinot Noir", "Pinot Meunier"],
        "max_yield_hl_ha": 65,
        "min_alcohol_white": 11.0,
        "aging_months_white": 15,
    },
    "Alsace": {
        "region": "Alsace",
        "sign": "AOC",
        "colors": ["white"],
        "grapes_white": ["Riesling", "Gewurztraminer", "Pinot Gris",
                         "Muscat", "Sylvaner", "Pinot Blanc", "Auxerrois"],
        "max_yield_hl_ha": 80,
        "min_alcohol_white": 11.0,
    },
    "Alsace Grand Cru": {
        "region": "Alsace",
        "sign": "AOC",
        "colors": ["white"],
        "grapes_white": ["Riesling", "Gewurztraminer", "Pinot Gris", "Muscat"],
        "max_yield_hl_ha": 55,
        "min_alcohol_white": 12.5,
    },
    "Beaujolais": {
        "region": "Beaujolais",
        "sign": "AOC",
        "colors": ["red", "white", "rosé"],
        "grapes_red": ["Gamay"],
        "grapes_white": ["Chardonnay"],
        "max_yield_hl_ha": 60,
        "min_alcohol_red": 10.0,
    },
    "Morgon": {
        "region": "Beaujolais",
        "sign": "AOC",
        "colors": ["red"],
        "grapes_red": ["Gamay"],
        "max_yield_hl_ha": 52,
        "min_alcohol_red": 10.5,
    },
    "Moulis-en-Médoc": {
        "region": "Bordeaux",
        "sign": "AOC",
        "colors": ["red"],
        "grapes_red": ["Cabernet Sauvignon", "Merlot", "Cabernet Franc",
                       "Petit Verdot", "Malbec"],
        "max_yield_hl_ha": 55,
        "min_alcohol_red": 10.5,
    },
    "Pessac-Léognan": {
        "region": "Bordeaux",
        "sign": "AOC",
        "colors": ["red", "white"],
        "grapes_red": ["Cabernet Sauvignon", "Merlot", "Cabernet Franc",
                       "Petit Verdot", "Malbec"],
        "grapes_white": ["Sauvignon Blanc", "Sémillon", "Muscadelle"],
        "max_yield_hl_ha": 54,
        "min_alcohol_red": 10.5,
        "min_alcohol_white": 10.5,
    },
    "Sauternes": {
        "region": "Bordeaux",
        "sign": "AOC",
        "colors": ["white"],
        "grapes_white": ["Sémillon", "Sauvignon Blanc", "Muscadelle"],
        "max_yield_hl_ha": 25,
        "min_alcohol_white": 13.0,
    },
    "Pomerol": {
        "region": "Bordeaux",
        "sign": "AOC",
        "colors": ["red"],
        "grapes_red": ["Merlot", "Cabernet Franc", "Cabernet Sauvignon"],
        "max_yield_hl_ha": 54,
        "min_alcohol_red": 10.5,
    },
    "Médoc": {
        "region": "Bordeaux",
        "sign": "AOC",
        "colors": ["red"],
        "grapes_red": ["Cabernet Sauvignon", "Merlot", "Cabernet Franc",
                       "Petit Verdot", "Malbec"],
        "max_yield_hl_ha": 60,
        "min_alcohol_red": 10.5,
    },
    "Haut-Médoc": {
        "region": "Bordeaux",
        "sign": "AOC",
        "colors": ["red"],
        "grapes_red": ["Cabernet Sauvignon", "Merlot", "Cabernet Franc",
                       "Petit Verdot", "Malbec"],
        "max_yield_hl_ha": 57,
        "min_alcohol_red": 10.5,
    },
    "Saint-Julien": {
        "region": "Bordeaux",
        "sign": "AOC",
        "colors": ["red"],
        "grapes_red": ["Cabernet Sauvignon", "Merlot", "Cabernet Franc",
                       "Petit Verdot", "Malbec"],
        "max_yield_hl_ha": 57,
        "min_alcohol_red": 10.5,
    },
    "Listrac-Médoc": {
        "region": "Bordeaux",
        "sign": "AOC",
        "colors": ["red"],
        "grapes_red": ["Cabernet Sauvignon", "Merlot", "Cabernet Franc",
                       "Petit Verdot", "Malbec"],
        "max_yield_hl_ha": 58,
        "min_alcohol_red": 10.5,
    },
    "Graves": {
        "region": "Bordeaux",
        "sign": "AOC",
        "colors": ["red", "white"],
        "grapes_red": ["Cabernet Sauvignon", "Merlot", "Cabernet Franc",
                       "Petit Verdot", "Malbec"],
        "grapes_white": ["Sauvignon Blanc", "Sémillon", "Muscadelle"],
        "max_yield_hl_ha": 58,
        "min_alcohol_red": 10.0,
        "min_alcohol_white": 10.0,
    },
    "Entre-deux-Mers": {
        "region": "Bordeaux",
        "sign": "AOC",
        "colors": ["white"],
        "grapes_white": ["Sauvignon Blanc", "Sémillon", "Muscadelle"],
        "max_yield_hl_ha": 65,
        "min_alcohol_white": 10.0,
    },
    "Côtes de Bourg": {
        "region": "Bordeaux",
        "sign": "AOC",
        "colors": ["red", "white"],
        "grapes_red": ["Merlot", "Cabernet Sauvignon", "Cabernet Franc",
                       "Malbec"],
        "max_yield_hl_ha": 59,
        "min_alcohol_red": 10.5,
    },
    "Fronsac": {
        "region": "Bordeaux",
        "sign": "AOC",
        "colors": ["red"],
        "grapes_red": ["Merlot", "Cabernet Franc", "Cabernet Sauvignon"],
        "max_yield_hl_ha": 53,
        "min_alcohol_red": 10.5,
    },
    "Gevrey-Chambertin": {
        "region": "Burgundy",
        "sign": "AOC",
        "colors": ["red"],
        "grapes_red": ["Pinot Noir"],
        "max_yield_hl_ha": 42,
        "min_alcohol_red": 10.5,
    },
    "Nuits-Saint-Georges": {
        "region": "Burgundy",
        "sign": "AOC",
        "colors": ["red", "white"],
        "grapes_red": ["Pinot Noir"],
        "grapes_white": ["Chardonnay"],
        "max_yield_hl_ha": 42,
        "min_alcohol_red": 10.5,
    },
    "Puligny-Montrachet": {
        "region": "Burgundy",
        "sign": "AOC",
        "colors": ["white", "red"],
        "grapes_white": ["Chardonnay"],
        "grapes_red": ["Pinot Noir"],
        "max_yield_hl_ha": 50,
        "min_alcohol_white": 11.0,
    },
    "Chassagne-Montrachet": {
        "region": "Burgundy",
        "sign": "AOC",
        "colors": ["white", "red"],
        "grapes_white": ["Chardonnay"],
        "grapes_red": ["Pinot Noir"],
        "max_yield_hl_ha": 50,
        "min_alcohol_white": 11.0,
    },
    "Corton": {
        "region": "Burgundy",
        "sign": "AOC",
        "colors": ["red", "white"],
        "grapes_red": ["Pinot Noir"],
        "grapes_white": ["Chardonnay"],
        "max_yield_hl_ha": 40,
        "min_alcohol_red": 11.5,
    },
    "Musigny": {
        "region": "Burgundy",
        "sign": "AOC",
        "colors": ["red", "white"],
        "grapes_red": ["Pinot Noir"],
        "grapes_white": ["Chardonnay"],
        "max_yield_hl_ha": 35,
        "min_alcohol_red": 11.5,
    },
    "Côtes du Jura": {
        "region": "Jura",
        "sign": "AOC",
        "colors": ["red", "white", "rosé"],
        "grapes_red": ["Poulsard", "Trousseau", "Pinot Noir"],
        "grapes_white": ["Savagnin", "Chardonnay"],
        "max_yield_hl_ha": 60,
        "min_alcohol_red": 10.0,
    },
    "Vin Jaune": {
        "region": "Jura",
        "sign": "AOC",
        "colors": ["white"],
        "grapes_white": ["Savagnin"],
        "max_yield_hl_ha": 60,
        "min_alcohol_white": 11.5,
        "aging_months_white": 72,
    },
    "Corbières": {
        "region": "Languedoc-Roussillon",
        "sign": "AOC",
        "colors": ["red", "white", "rosé"],
        "grapes_red": ["Carignan", "Grenache", "Syrah", "Mourvèdre"],
        "max_yield_hl_ha": 50,
        "min_alcohol_red": 11.5,
    },
    "Minervois": {
        "region": "Languedoc-Roussillon",
        "sign": "AOC",
        "colors": ["red", "white", "rosé"],
        "grapes_red": ["Syrah", "Grenache", "Mourvèdre", "Carignan"],
        "max_yield_hl_ha": 50,
        "min_alcohol_red": 12.0,
    },
    "Fitou": {
        "region": "Languedoc-Roussillon",
        "sign": "AOC",
        "colors": ["red"],
        "grapes_red": ["Carignan", "Grenache", "Syrah", "Mourvèdre"],
        "max_yield_hl_ha": 45,
        "min_alcohol_red": 12.0,
        "aging_months_red": 9,
    },
    "Cahors": {
        "region": "South-West",
        "sign": "AOC",
        "colors": ["red"],
        "grapes_red": ["Malbec", "Merlot", "Tannat"],
        "max_yield_hl_ha": 50,
        "min_alcohol_red": 10.5,
    },
    "Madiran": {
        "region": "South-West",
        "sign": "AOC",
        "colors": ["red"],
        "grapes_red": ["Tannat", "Cabernet Franc", "Cabernet Sauvignon"],
        "max_yield_hl_ha": 55,
        "min_alcohol_red": 11.0,
        "aging_months_red": 12,
    },
    "Jurançon": {
        "region": "South-West",
        "sign": "AOC",
        "colors": ["white"],
        "grapes_white": ["Gros Manseng", "Petit Manseng"],
        "max_yield_hl_ha": 40,
        "min_alcohol_white": 11.0,
    },
    "Patrimonio": {
        "region": "Corsica",
        "sign": "AOC",
        "colors": ["red", "white", "rosé"],
        "grapes_red": ["Nielluccio"],
        "grapes_white": ["Vermentino"],
        "max_yield_hl_ha": 50,
        "min_alcohol_red": 12.0,
    },
    "Ajaccio": {
        "region": "Corsica",
        "sign": "AOC",
        "colors": ["red", "white", "rosé"],
        "grapes_red": ["Sciacarello", "Grenache", "Barbarossa"],
        "grapes_white": ["Vermentino"],
        "max_yield_hl_ha": 50,
        "min_alcohol_red": 11.5,
    },
    "Crépy": {
        "region": "Savoie",
        "sign": "AOC",
        "colors": ["white"],
        "grapes_white": ["Chasselas"],
        "max_yield_hl_ha": 66,
        "min_alcohol_white": 9.0,
    },
    "Vin de Savoie": {
        "region": "Savoie",
        "sign": "AOC",
        "colors": ["red", "white", "rosé"],
        "grapes_red": ["Gamay", "Mondeuse", "Pinot Noir"],
        "grapes_white": ["Jacquère", "Altesse", "Chasselas", "Chardonnay"],
        "max_yield_hl_ha": 67,
        "min_alcohol_red": 9.0,
    },
}


# ─── HTTP Session ─────────────────────────────────────────────────────────────

def _get_session() -> requests.Session:
    """Create an HTTP session with appropriate headers."""
    session = requests.Session()
    session.headers.update({
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
    })
    return session


def _rate_limited_get(session: requests.Session, url: str, **kwargs) -> requests.Response:
    """Make a rate-limited GET request."""
    time.sleep(REQUEST_DELAY)
    logger.debug(f"GET {url}")
    resp = session.get(url, timeout=30, **kwargs)
    resp.raise_for_status()
    return resp


# ─── Data Download ────────────────────────────────────────────────────────────

def _download_datagouv_csv(session: requests.Session) -> Optional[str]:
    """Download the INAO products CSV from data.gouv.fr API.

    Uses the data.gouv.fr API to find the latest CSV resource URL for
    the 'aires-et-produits-aoc-aop-et-igp' dataset.
    """
    try:
        # Get dataset metadata to find resource URLs
        api_url = f"{DATAGOUV_API_BASE}/datasets/{DATAGOUV_PRODUCTS_DATASET}/"
        logger.info(f"Fetching dataset metadata from {api_url}")
        resp = _rate_limited_get(session, api_url)
        dataset = resp.json()

        # Find the CSV resource
        csv_url = None
        for resource in dataset.get("resources", []):
            fmt = resource.get("format", "").lower()
            url = resource.get("url", "")
            if fmt == "csv" or url.endswith(".csv"):
                csv_url = url
                break

        if not csv_url:
            logger.warning("No CSV resource found in dataset metadata")
            return None

        logger.info(f"Downloading CSV from {csv_url}")
        resp = _rate_limited_get(session, csv_url)
        content = resp.text

        # Cache locally
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        PRODUCTS_CACHE.write_text(content, encoding="utf-8")
        logger.info(f"Cached CSV to {PRODUCTS_CACHE} ({len(content)} bytes)")

        return content

    except requests.RequestException as e:
        logger.warning(f"Failed to download from data.gouv.fr: {e}")
        return None


def _download_ods_records(session: requests.Session) -> Optional[list[dict]]:
    """Download records from OpenDataSoft API as fallback."""
    try:
        records = []
        offset = 0
        limit = 100

        while True:
            url = (
                f"{ODS_API_BASE}/{ODS_DATASET_ID}/records"
                f"?limit={limit}&offset={offset}"
            )
            logger.info(f"Fetching ODS records (offset={offset})")
            resp = _rate_limited_get(session, url)
            data = resp.json()

            batch = data.get("results", [])
            if not batch:
                break

            records.extend(batch)
            offset += limit

            total = data.get("total_count", 0)
            if offset >= total:
                break

        logger.info(f"Downloaded {len(records)} records from OpenDataSoft")
        return records

    except requests.RequestException as e:
        logger.warning(f"Failed to download from OpenDataSoft: {e}")
        return None


def _load_cached_csv() -> Optional[str]:
    """Load the cached CSV if available."""
    if PRODUCTS_CACHE.exists():
        logger.info(f"Loading cached CSV from {PRODUCTS_CACHE}")
        return PRODUCTS_CACHE.read_text(encoding="utf-8")
    return None


# ─── CSV Parsing ──────────────────────────────────────────────────────────────

def _detect_delimiter(sample: str) -> str:
    """Detect CSV delimiter (comma or semicolon)."""
    semicolons = sample.count(";")
    commas = sample.count(",")
    return ";" if semicolons > commas else ","


def _parse_products_csv(csv_text: str) -> list[dict]:
    """Parse the INAO products CSV into a list of dicts.

    Expected columns (may vary slightly):
      IDA, AIRE GEOGRAPHIQUE, SIGNE FR, IDPRODUIT, PRODUIT
    """
    delimiter = _detect_delimiter(csv_text[:2000])
    reader = csv.DictReader(io.StringIO(csv_text), delimiter=delimiter)

    # Normalize column names (strip whitespace, uppercase)
    records = []
    for row in reader:
        normalized = {}
        for key, val in row.items():
            if key is None:
                continue
            nkey = key.strip().upper().replace(" ", "_")
            normalized[nkey] = val.strip() if val else ""
        records.append(normalized)

    logger.info(f"Parsed {len(records)} CSV rows")
    if records:
        logger.debug(f"CSV columns: {list(records[0].keys())}")

    return records


def _is_wine_product(record: dict) -> bool:
    """Check if a CSV record represents a wine product."""
    product = record.get("PRODUIT", "").lower()
    sign = record.get("SIGNE_FR", record.get("SIGNE", "")).upper()

    # Must have a recognized sign type
    if sign not in SIGN_TYPES:
        return False

    # Check for wine keywords in product name
    for kw in WINE_KEYWORDS:
        if kw in product:
            return True

    # Also check "aire géographique" for well-known wine names
    area = record.get("AIRE_GEOGRAPHIQUE", record.get("AIRE_GÉOGRAPHIQUE", "")).lower()
    wine_area_keywords = [
        "côtes de", "coteaux", "crémant", "champagne", "beaujolais",
        "bordeaux", "bourgogne", "alsace", "muscadet", "médoc",
        "saint-émilion", "pomerol", "sauternes", "graves",
        "châteauneuf", "hermitage", "condrieu", "côte-rôtie",
        "bandol", "provence", "languedoc", "corbières", "minervois",
        "cahors", "madiran", "jurançon", "sancerre", "pouilly",
        "vouvray", "chinon", "anjou", "touraine",
    ]
    for kw in wine_area_keywords:
        if kw in area:
            return True

    return False


def _extract_appellation_name(record: dict) -> str:
    """Extract clean appellation name from CSV record."""
    # Use AIRE_GEOGRAPHIQUE as the primary name
    name = record.get("AIRE_GEOGRAPHIQUE", record.get("AIRE_GÉOGRAPHIQUE", ""))
    if not name:
        name = record.get("PRODUIT", "")

    # Clean up: remove leading/trailing whitespace, normalize quotes
    name = name.strip().replace("'", "'").replace("`", "'")
    return name


def _extract_sign_type(record: dict) -> str:
    """Extract sign type (AOC, AOP, IGP) from record."""
    sign = record.get("SIGNE_FR", record.get("SIGNE", "")).upper().strip()
    return SIGN_TYPES.get(sign, sign)


# ─── Fact Builders ────────────────────────────────────────────────────────────

def _build_basic_facts(
    appellation: str,
    sign: str,
    region: Optional[str],
    source_id: str,
) -> list[dict]:
    """Build basic existence and location facts from CSV data."""
    facts = []

    if not appellation or not sign:
        return facts

    entities = [{"type": "appellation", "name": appellation}]
    tags = ["appellation", "french_wine", sign.lower()]

    # Fact: Appellation exists with sign type
    if region:
        facts.append({
            "fact_text": f"{appellation} is an {sign} appellation in the {region} region of France.",
            "domain": "wine_regions",
            "subdomain": "appellations",
            "source_id": source_id,
            "entities": entities + [{"type": "region", "name": region}],
            "tags": tags + ["geography", region.lower().replace(" ", "_")],
        })
    else:
        facts.append({
            "fact_text": f"{appellation} is an {sign} appellation in France.",
            "domain": "wine_regions",
            "subdomain": "appellations",
            "source_id": source_id,
            "entities": entities,
            "tags": tags,
        })

    return facts


def _build_detailed_facts(
    appellation: str,
    info: dict,
    source_id: str,
) -> list[dict]:
    """Build detailed facts from curated appellation data."""
    facts = []
    sign = info.get("sign", "AOC")
    region = info.get("region", "")
    entities_base = [{"type": "appellation", "name": appellation}]
    tags_base = ["appellation", "french_wine", sign.lower()]

    # Fact: Appellation with region
    if region:
        facts.append({
            "fact_text": f"{appellation} is an {sign} appellation in the {region} region of France.",
            "domain": "wine_regions",
            "subdomain": "appellations",
            "source_id": source_id,
            "entities": entities_base + [{"type": "region", "name": region}],
            "tags": tags_base + ["geography"],
        })

    # Fact: Colors produced
    colors = info.get("colors", [])
    if colors:
        color_str = ", ".join(colors)
        facts.append({
            "fact_text": f"{appellation} {sign} produces {color_str} wines.",
            "domain": "wine_regions",
            "subdomain": "appellations",
            "source_id": source_id,
            "entities": entities_base,
            "tags": tags_base + ["wine_style"],
        })

    # Fact: Permitted grape varieties (red)
    grapes_red = info.get("grapes_red", [])
    if grapes_red:
        grape_entities = [{"type": "grape", "name": g} for g in grapes_red]
        if len(grapes_red) <= 3:
            grape_str = ", ".join(grapes_red)
            facts.append({
                "fact_text": (
                    f"{appellation} {sign} permits {grape_str} "
                    f"for red wine production."
                ),
                "domain": "wine_regions",
                "subdomain": "appellations",
                "source_id": source_id,
                "entities": entities_base + grape_entities,
                "tags": tags_base + ["grape_varieties", "regulation"],
            })
        else:
            main_grapes = ", ".join(grapes_red[:3])
            facts.append({
                "fact_text": (
                    f"{appellation} {sign} permits {len(grapes_red)} grape varieties "
                    f"for red wine including {main_grapes}."
                ),
                "domain": "wine_regions",
                "subdomain": "appellations",
                "source_id": source_id,
                "entities": entities_base + grape_entities,
                "tags": tags_base + ["grape_varieties", "regulation"],
            })

    # Fact: Permitted grape varieties (white)
    grapes_white = info.get("grapes_white", [])
    if grapes_white:
        grape_entities = [{"type": "grape", "name": g} for g in grapes_white]
        if len(grapes_white) <= 3:
            grape_str = ", ".join(grapes_white)
            facts.append({
                "fact_text": (
                    f"{appellation} {sign} permits {grape_str} "
                    f"for white wine production."
                ),
                "domain": "wine_regions",
                "subdomain": "appellations",
                "source_id": source_id,
                "entities": entities_base + grape_entities,
                "tags": tags_base + ["grape_varieties", "regulation"],
            })
        else:
            main_grapes = ", ".join(grapes_white[:3])
            facts.append({
                "fact_text": (
                    f"{appellation} {sign} permits {len(grapes_white)} grape varieties "
                    f"for white wine including {main_grapes}."
                ),
                "domain": "wine_regions",
                "subdomain": "appellations",
                "source_id": source_id,
                "entities": entities_base + grape_entities,
                "tags": tags_base + ["grape_varieties", "regulation"],
            })

    # Fact: Maximum yield
    max_yield = info.get("max_yield_hl_ha")
    if max_yield is not None:
        facts.append({
            "fact_text": (
                f"The maximum yield for {appellation} {sign} is "
                f"{max_yield} hl/ha."
            ),
            "domain": "wine_regions",
            "subdomain": "appellations",
            "source_id": source_id,
            "entities": entities_base,
            "tags": tags_base + ["yield", "regulation"],
        })

    # Fact: Minimum alcohol (red)
    min_alc_red = info.get("min_alcohol_red")
    if min_alc_red is not None:
        facts.append({
            "fact_text": (
                f"{appellation} {sign} requires a minimum alcohol content "
                f"of {min_alc_red}% for red wines."
            ),
            "domain": "wine_regions",
            "subdomain": "appellations",
            "source_id": source_id,
            "entities": entities_base,
            "tags": tags_base + ["alcohol", "regulation"],
        })

    # Fact: Minimum alcohol (white)
    min_alc_white = info.get("min_alcohol_white")
    if min_alc_white is not None:
        facts.append({
            "fact_text": (
                f"{appellation} {sign} requires a minimum alcohol content "
                f"of {min_alc_white}% for white wines."
            ),
            "domain": "wine_regions",
            "subdomain": "appellations",
            "source_id": source_id,
            "entities": entities_base,
            "tags": tags_base + ["alcohol", "regulation"],
        })

    # Fact: Aging requirements
    for color in ["red", "white"]:
        aging = info.get(f"aging_months_{color}")
        if aging is not None:
            facts.append({
                "fact_text": (
                    f"{appellation} {sign} requires a minimum aging period "
                    f"of {aging} months for {color} wines."
                ),
                "domain": "wine_regions",
                "subdomain": "appellations",
                "source_id": source_id,
                "entities": entities_base,
                "tags": tags_base + ["aging", "regulation"],
            })

    return facts


# ─── Main Extraction Pipeline ────────────────────────────────────────────────

def _resolve_region(appellation: str, departments: Optional[list[str]] = None) -> Optional[str]:
    """Resolve appellation region from known data or department codes."""
    # Check curated data first
    if appellation in KNOWN_APPELLATIONS:
        return KNOWN_APPELLATIONS[appellation].get("region")

    # Try department-based lookup
    if departments:
        for dept in departments:
            region = DEPARTMENT_TO_REGION.get(dept)
            if region:
                return region

    return None


def extract_all(
    region_filter: Optional[str] = None,
    dry_run: bool = False,
) -> dict:
    """Run the full INAO extraction pipeline.

    Returns a summary dict with counts.
    """
    session = _get_session()
    summary = {
        "csv_records": 0,
        "wine_records": 0,
        "appellations_found": 0,
        "facts_generated": 0,
        "facts_inserted": 0,
        "complete_data": 0,
        "partial_data": 0,
    }

    # Step 1: Register source
    if not dry_run:
        source_id = ensure_source(
            name="INAO (Institut national de l'origine et de la qualité)",
            url="https://www.inao.gouv.fr",
            source_type="government_registry",
            tier=SOURCE_TIER,
            language="fr",
        )
    else:
        source_id = "dry-run-source-id"

    # Step 2: Download / load CSV data
    csv_text = _load_cached_csv()
    if not csv_text:
        logger.info("No cached CSV found, downloading from data.gouv.fr...")
        csv_text = _download_datagouv_csv(session)

    all_facts = []

    # Step 3: Parse CSV and extract wine appellations
    if csv_text:
        records = _parse_products_csv(csv_text)
        summary["csv_records"] = len(records)

        wine_records = [r for r in records if _is_wine_product(r)]
        summary["wine_records"] = len(wine_records)

        # Deduplicate by appellation name
        seen_appellations = {}
        for record in wine_records:
            name = _extract_appellation_name(record)
            sign = _extract_sign_type(record)
            if name and name not in seen_appellations:
                seen_appellations[name] = sign

        logger.info(
            f"Found {len(seen_appellations)} unique wine appellations "
            f"from {len(wine_records)} wine-related CSV records"
        )
        summary["appellations_found"] = len(seen_appellations)

        # Build facts from CSV data
        for name, sign in seen_appellations.items():
            region = _resolve_region(name)

            # Apply region filter
            if region_filter:
                target = REGION_ALIASES.get(region_filter.lower(), region_filter)
                if region and region != target:
                    continue
                if not region and target:
                    continue

            facts = _build_basic_facts(name, sign, region, source_id)
            all_facts.extend(facts)
    else:
        logger.warning(
            "Could not download CSV data. Falling back to curated data only."
        )

    # Step 4: Add detailed facts from curated KNOWN_APPELLATIONS
    for name, info in KNOWN_APPELLATIONS.items():
        region = info.get("region", "")

        # Apply region filter
        if region_filter:
            target = REGION_ALIASES.get(region_filter.lower(), region_filter)
            if region != target:
                continue

        detailed = _build_detailed_facts(name, info, source_id)
        all_facts.extend(detailed)
        summary["complete_data"] += 1

    # Count partial vs complete
    summary["partial_data"] = summary["appellations_found"] - summary["complete_data"]
    if summary["partial_data"] < 0:
        summary["partial_data"] = 0

    # Deduplicate facts by fact_text
    seen_texts = set()
    unique_facts = []
    for fact in all_facts:
        if fact["fact_text"] not in seen_texts:
            seen_texts.add(fact["fact_text"])
            unique_facts.append(fact)

    summary["facts_generated"] = len(unique_facts)
    logger.info(f"Generated {len(unique_facts)} unique facts")

    # Step 5: Insert facts
    if dry_run:
        logger.info("[DRY RUN] Would insert {} facts".format(len(unique_facts)))
        _print_sample_facts(unique_facts, count=10)
    else:
        inserted = insert_facts_batch(unique_facts)
        summary["facts_inserted"] = inserted
        logger.info(f"Inserted {inserted} new facts")

    return summary


# ─── Validation ───────────────────────────────────────────────────────────────

def validate_facts(facts: list[dict]) -> None:
    """Run quality checks on generated facts and print a report."""
    if not facts:
        click.echo("No facts to validate.")
        return

    total = len(facts)

    # Domain distribution
    domain_counts = Counter()
    subdomain_counts = Counter()
    for f in facts:
        domain_counts[f["domain"]] += 1
        sd = f.get("subdomain", "")
        if sd:
            subdomain_counts[sd] += 1

    click.echo("\n  Domain distribution:")
    for domain, cnt in domain_counts.most_common():
        click.echo(f"    {domain:25s}: {cnt} facts")
    if subdomain_counts:
        click.echo("\n  Subdomain distribution:")
        for sd, cnt in subdomain_counts.most_common():
            click.echo(f"    {sd:25s}: {cnt} facts")

    # Quality checks
    too_short = []
    too_long = []
    no_predicate = []
    missing_entities = 0
    possible_dupes = []

    for f in facts:
        text = f["fact_text"]
        word_count = len(text.split())

        if word_count < 5:
            too_short.append(text)
        if word_count > 50:
            too_long.append(text)

        # Check for entity-only facts (no verb/predicate)
        stripped = text.rstrip(".")
        if " " not in stripped or word_count <= 2:
            no_predicate.append(text)

        entities = f.get("entities", [])
        if not entities:
            missing_entities += 1

    # Check near-duplicates using string containment
    fact_texts = [f["fact_text"] for f in facts]
    for i in range(len(fact_texts)):
        for j in range(i + 1, min(i + 50, len(fact_texts))):
            t1 = fact_texts[i].lower()
            t2 = fact_texts[j].lower()
            if t1 != t2 and (t1 in t2 or t2 in t1):
                possible_dupes.append((fact_texts[i], fact_texts[j]))
                if len(possible_dupes) >= 50:
                    break
        if len(possible_dupes) >= 50:
            break

    entities_populated = total - missing_entities

    click.echo(f"\n  Quality:")
    click.echo(
        f"    Too short (<5 words):  {len(too_short)} "
        f"({len(too_short)/total*100:.1f}%)"
    )
    click.echo(
        f"    Too long (>50 words):  {len(too_long)} "
        f"({len(too_long)/total*100:.1f}%)"
    )
    click.echo(
        f"    No predicate:          {len(no_predicate)} "
        f"({len(no_predicate)/total*100:.1f}%)"
    )
    click.echo(
        f"    Missing entities:      {missing_entities} "
        f"({missing_entities/total*100:.1f}%)"
    )
    click.echo(
        f"    Entities populated:    {entities_populated} "
        f"({entities_populated/total*100:.1f}%)"
    )
    click.echo(
        f"    Possible near-dupes:   {len(possible_dupes)} "
        f"({len(possible_dupes)/total*100:.1f}%)"
    )

    # Sample facts
    click.echo(f"\n  Sample facts:")
    sample = random.sample(facts, min(10, len(facts)))
    for i, f in enumerate(sample, 1):
        click.echo(f"    {i:2d}. \"{f['fact_text']}\"")

    # Report too-short facts if any
    if too_short:
        click.echo(f"\n  Too-short facts:")
        for text in too_short[:5]:
            click.echo(f"    - \"{text}\"")

    # Report near-dupes if any
    if possible_dupes:
        click.echo(f"\n  Near-duplicate examples:")
        for t1, t2 in possible_dupes[:3]:
            click.echo(f"    - \"{t1}\"")
            click.echo(f"      ~ \"{t2}\"")


def run_validate() -> None:
    """Generate facts in dry-run mode and validate them."""
    session = _get_session()
    source_id = "validation-source-id"

    # Load data
    csv_text = _load_cached_csv()
    if not csv_text:
        logger.info("No cached CSV, attempting download for validation...")
        csv_text = _download_datagouv_csv(session)

    all_facts = []

    # From CSV
    if csv_text:
        records = _parse_products_csv(csv_text)
        wine_records = [r for r in records if _is_wine_product(r)]

        seen = {}
        for record in wine_records:
            name = _extract_appellation_name(record)
            sign = _extract_sign_type(record)
            if name and name not in seen:
                seen[name] = sign

        for name, sign in seen.items():
            region = _resolve_region(name)
            all_facts.extend(_build_basic_facts(name, sign, region, source_id))

        click.echo(f"\n  CSV data summary:")
        click.echo(f"    Total CSV records:     {len(records)}")
        click.echo(f"    Wine-related records:  {len(wine_records)}")
        click.echo(f"    Unique appellations:   {len(seen)}")

        # Coverage against known ~360 target
        coverage = len(seen) / 360 * 100
        click.echo(f"    Coverage vs ~360 AOC:  {coverage:.0f}%")
    else:
        click.echo("\n  [WARNING] No CSV data available. Using curated data only.")

    # From curated data
    for name, info in KNOWN_APPELLATIONS.items():
        all_facts.extend(_build_detailed_facts(name, info, source_id))

    # Deduplicate
    seen_texts = set()
    unique_facts = []
    for f in all_facts:
        if f["fact_text"] not in seen_texts:
            seen_texts.add(f["fact_text"])
            unique_facts.append(f)

    click.echo(f"\n  Total unique facts: {len(unique_facts)}")

    # Curated data completeness
    complete = len(KNOWN_APPELLATIONS)
    click.echo(f"  Appellations with full data (grapes + yield + alcohol): {complete}")
    click.echo(
        f"  Appellations with basic data only: "
        f"{max(0, len(unique_facts) // 2 - complete)} (approx)"
    )

    validate_facts(unique_facts)


# ─── Template Generator ──────────────────────────────────────────────────────

def generate_template() -> None:
    """Generate a JSON template for semi-manual data entry.

    This is the fallback when the INAO site proves too difficult
    to scrape programmatically for detailed data.
    """
    template = {
        "_comment": (
            "INAO appellation data template for semi-manual entry. "
            "The INAO website (inao.gouv.fr) blocks automated scraping. "
            "The data.gouv.fr CSV provides appellation names and sign types, "
            "but not detailed regulatory info (grapes, yields, alcohol). "
            "Fill in the fields below from INAO cahiers des charges PDFs."
        ),
        "_schema_version": "1.0",
        "_fields": {
            "name": "Appellation name (French, preserve accents)",
            "sign": "Sign type: AOC, AOP, or IGP",
            "region": "Wine region (English name)",
            "departments": "List of department numbers",
            "colors": "List of wine colors: red, white, rosé",
            "grapes_red": "Permitted red wine grape varieties",
            "grapes_white": "Permitted white wine grape varieties",
            "max_yield_hl_ha": "Maximum yield in hectoliters per hectare",
            "min_alcohol_red": "Minimum alcohol % for red wines",
            "min_alcohol_white": "Minimum alcohol % for white wines",
            "aging_months_red": "Minimum aging months for red (null if none)",
            "aging_months_white": "Minimum aging months for white (null if none)",
            "notes": "Free-text notes about special requirements",
        },
        "_auto_extracted_fields": [
            "name", "sign",
        ],
        "_manual_fields": [
            "region", "departments", "colors",
            "grapes_red", "grapes_white",
            "max_yield_hl_ha", "min_alcohol_red", "min_alcohol_white",
            "aging_months_red", "aging_months_white", "notes",
        ],
        "appellations": [
            {
                "name": "Example-Appellation",
                "sign": "AOC",
                "region": None,
                "departments": [],
                "colors": [],
                "grapes_red": [],
                "grapes_white": [],
                "max_yield_hl_ha": None,
                "min_alcohol_red": None,
                "min_alcohol_white": None,
                "aging_months_red": None,
                "aging_months_white": None,
                "notes": "",
            }
        ],
    }

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    with open(TEMPLATE_PATH, "w", encoding="utf-8") as f:
        json.dump(template, f, indent=2, ensure_ascii=False)

    click.echo(f"Template written to {TEMPLATE_PATH}")
    click.echo(
        "Fill in the 'appellations' array with data from INAO cahiers des charges PDFs."
    )


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _print_sample_facts(facts: list[dict], count: int = 10) -> None:
    """Print a sample of generated facts."""
    sample = random.sample(facts, min(count, len(facts)))
    click.echo(f"\n  Sample facts ({len(sample)} of {len(facts)}):")
    for i, f in enumerate(sample, 1):
        click.echo(f"    {i:2d}. [{f['domain']}] \"{f['fact_text']}\"")


def _print_summary(summary: dict) -> None:
    """Print extraction summary."""
    click.echo("\n  Extraction Summary:")
    click.echo(f"    CSV records parsed:      {summary['csv_records']}")
    click.echo(f"    Wine-related records:    {summary['wine_records']}")
    click.echo(f"    Unique appellations:     {summary['appellations_found']}")
    click.echo(f"    Facts generated:         {summary['facts_generated']}")
    click.echo(f"    Facts inserted:          {summary['facts_inserted']}")
    click.echo(f"    Complete data:           {summary['complete_data']}")
    click.echo(f"    Partial data only:       {summary['partial_data']}")

    # Coverage assessment
    if summary["appellations_found"] > 0:
        coverage = summary["appellations_found"] / 360 * 100
        click.echo(f"    Coverage vs ~360 AOC:    {coverage:.0f}%")


# ─── CLI ──────────────────────────────────────────────────────────────────────

@click.command()
@click.option("--all", "run_all", is_flag=True, help="Extract all wine appellations")
@click.option("--region", type=str, default=None, help="Filter by region (e.g. rhone, bordeaux, burgundy)")
@click.option("--dry-run", is_flag=True, help="Generate facts without inserting into database")
@click.option("--validate", "do_validate", is_flag=True, help="Run quality checks on generated facts")
@click.option("--list", "list_regions", is_flag=True, help="List available regions")
@click.option("--template", "gen_template", is_flag=True, help="Generate JSON template for manual data entry")
def main(
    run_all: bool,
    region: Optional[str],
    dry_run: bool,
    do_validate: bool,
    list_regions: bool,
    gen_template: bool,
):
    """OenoBench INAO Scraper — Extract French wine appellation data from INAO."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = f"data/logs/inao_{timestamp}.log"
    os.makedirs("data/logs", exist_ok=True)
    logger.add(log_path, rotation="10 MB")

    if list_regions:
        click.echo("\nAvailable regions:")
        seen = set()
        for alias, canonical in sorted(REGION_ALIASES.items()):
            if canonical not in seen:
                aliases = [a for a, c in REGION_ALIASES.items() if c == canonical]
                click.echo(f"  {canonical:25s} (aliases: {', '.join(aliases)})")
                seen.add(canonical)
        return

    if gen_template:
        generate_template()
        return

    if do_validate:
        run_validate()
        return

    if run_all or region:
        summary = extract_all(
            region_filter=region,
            dry_run=dry_run,
        )
        _print_summary(summary)
        return

    click.echo("Use --all to extract all appellations, --region <name> to filter,")
    click.echo("--dry-run to preview, or --validate for quality checks.")
    click.echo("Use --list to see available regions.")
    click.echo("Use --template to generate a manual data entry template.")


if __name__ == "__main__":
    main()
