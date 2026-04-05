"""
OenoBench — EU Regulations & OIV Scraper

Extracts wine regulatory facts from EUR-Lex (EU legislation) and OIV
(International Organisation of Vine and Wine).

Sources:
    a) EUR-Lex — https://eur-lex.europa.eu
       EU wine classification (PDO/PGI), labeling regulations,
       permitted oenological practices, E-Bacchus database.
       License: Public domain (EU law).

    b) OIV — https://www.oiv.int
       Global wine statistics, international oenological codex,
       grape variety descriptions.

Usage:
    python -m src.scrapers.eu_oiv --all
    python -m src.scrapers.eu_oiv --source eurlex
    python -m src.scrapers.eu_oiv --source oiv
    python -m src.scrapers.eu_oiv --dry-run
    python -m src.scrapers.eu_oiv --validate
    python -m src.scrapers.eu_oiv --list
"""

import random
import re
import time
from collections import defaultdict
from typing import Optional

import click
import requests
from bs4 import BeautifulSoup
from loguru import logger

from src.utils.facts import ensure_source, insert_facts_batch, get_fact_count

# ─── Configuration ────────────────────────────────────────────────────────────

USER_AGENT = "OenoBench-Research/1.0 (academic wine benchmark)"
REQUEST_DELAY = 3.0  # seconds between HTTP requests
REQUEST_TIMEOUT = 30  # seconds

HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# ─── Source Definitions ───────────────────────────────────────────────────────

SOURCES = {
    "eurlex": {
        "name": "EUR-Lex EU Wine Legislation",
        "description": "EU wine classification, labeling, and oenological practices",
        "base_url": "https://eur-lex.europa.eu",
        "source_type": "government",
        "tier": "tier_1_official",
        "pages": [
            {
                "id": "regulation_1308_2013",
                "url": "https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32013R1308",
                "description": "Regulation (EU) No 1308/2013 — common organisation of agricultural markets (wine chapter)",
            },
            {
                "id": "regulation_2019_33",
                "url": "https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32019R0033",
                "description": "Delegated Regulation (EU) 2019/33 — wine labeling rules",
            },
            {
                "id": "regulation_2019_934",
                "url": "https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32019R0934",
                "description": "Delegated Regulation (EU) 2019/934 — authorised oenological practices",
            },
            {
                "id": "ebacchus",
                "url": "https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32009R0607",
                "description": "Regulation (EC) No 607/2009 — PDO/PGI wine names",
            },
        ],
    },
    "oiv": {
        "name": "OIV — International Organisation of Vine and Wine",
        "description": "Global wine statistics, oenological codex, grape variety standards",
        "base_url": "https://www.oiv.int",
        "source_type": "international_organisation",
        "tier": "tier_1_official",
        "pages": [
            {
                "id": "oiv_statistics",
                "url": "https://www.oiv.int/what-we-do/global-report",
                "description": "OIV global wine production/consumption statistics",
            },
            {
                "id": "oiv_standards",
                "url": "https://www.oiv.int/standards/international-code-of-oenological-practices",
                "description": "OIV International Code of Oenological Practices",
            },
            {
                "id": "oiv_varieties",
                "url": "https://www.oiv.int/what-we-do/variety-distribution",
                "description": "OIV grape variety distribution data",
            },
        ],
    },
}


# ─── HTTP Client ──────────────────────────────────────────────────────────────

_last_request_time = 0.0


def _rate_limited_get(url: str) -> Optional[requests.Response]:
    """Make a rate-limited GET request. Returns None on failure."""
    global _last_request_time
    elapsed = time.time() - _last_request_time
    if elapsed < REQUEST_DELAY:
        time.sleep(REQUEST_DELAY - elapsed)

    try:
        logger.info(f"Fetching: {url}")
        resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        _last_request_time = time.time()
        resp.raise_for_status()
        return resp
    except requests.RequestException as e:
        logger.warning(f"Failed to fetch {url}: {e}")
        _last_request_time = time.time()
        return None


def _get_soup(url: str) -> Optional[BeautifulSoup]:
    """Fetch a URL and return parsed BeautifulSoup, or None on failure."""
    resp = _rate_limited_get(url)
    if resp is None:
        return None
    return BeautifulSoup(resp.text, "lxml")


# ─── EUR-Lex Fact Extraction ─────────────────────────────────────────────────

# Curated EU wine regulatory knowledge. EUR-Lex pages are dense legal text;
# we extract structured atomic facts rephrased from the regulation content.
# This avoids storing verbatim legal text and ensures each fact is
# self-contained and testable.

_EURLEX_CLASSIFICATION_FACTS = [
    # PDO / PGI / Varietal wine framework (Reg 1308/2013, Part II Title II Ch I Sec 2)
    {
        "fact_text": "EU wine regulations recognise three categories: PDO (Protected Designation of Origin), PGI (Protected Geographical Indication), and wines without a geographical indication.",
        "domain": "wine_business",
        "subdomain": "eu_classification",
        "entities": [
            {"type": "classification", "name": "PDO"},
            {"type": "classification", "name": "PGI"},
        ],
        "tags": ["eu", "classification", "regulation"],
    },
    {
        "fact_text": "A PDO wine must be produced entirely within the defined geographical area, from grapes exclusively sourced from that area.",
        "domain": "wine_business",
        "subdomain": "eu_classification",
        "entities": [{"type": "classification", "name": "PDO"}],
        "tags": ["eu", "pdo", "regulation"],
    },
    {
        "fact_text": "A PGI wine must be produced at least partly within the designated geographical area, though grapes may originate from outside it.",
        "domain": "wine_business",
        "subdomain": "eu_classification",
        "entities": [{"type": "classification", "name": "PGI"}],
        "tags": ["eu", "pgi", "regulation"],
    },
    {
        "fact_text": "EU PDO wines correspond to the former French AOC, Italian DOCG/DOC, and Spanish DO/DOCa quality tiers.",
        "domain": "wine_business",
        "subdomain": "eu_classification",
        "entities": [
            {"type": "classification", "name": "PDO"},
            {"type": "classification", "name": "AOC"},
            {"type": "classification", "name": "DOCG"},
            {"type": "classification", "name": "DOC"},
        ],
        "tags": ["eu", "pdo", "aoc", "docg", "regulation"],
    },
    {
        "fact_text": "EU PGI wines correspond to the former French Vin de Pays, Italian IGT, and German Landwein categories.",
        "domain": "wine_business",
        "subdomain": "eu_classification",
        "entities": [
            {"type": "classification", "name": "PGI"},
            {"type": "classification", "name": "Vin de Pays"},
            {"type": "classification", "name": "IGT"},
            {"type": "classification", "name": "Landwein"},
        ],
        "tags": ["eu", "pgi", "igt", "regulation"],
    },
    {
        "fact_text": "Varietal wines without a geographical indication may display a single grape variety on the label if at least 85 percent of the wine is made from that variety.",
        "domain": "wine_business",
        "subdomain": "eu_classification",
        "entities": [],
        "tags": ["eu", "varietal", "labeling", "regulation"],
    },
    {
        "fact_text": "The E-Bacchus database is the official EU register of protected wine names, listing all PDO and PGI wines.",
        "domain": "wine_business",
        "subdomain": "eu_classification",
        "entities": [{"type": "database", "name": "E-Bacchus"}],
        "tags": ["eu", "ebacchus", "register"],
    },
    {
        "fact_text": "EU Member States must submit detailed product specifications when applying for PDO or PGI protection for a wine name.",
        "domain": "wine_business",
        "subdomain": "eu_classification",
        "entities": [
            {"type": "classification", "name": "PDO"},
            {"type": "classification", "name": "PGI"},
        ],
        "tags": ["eu", "pdo", "pgi", "regulation"],
    },
    {
        "fact_text": "Traditional terms such as 'Reserva', 'Riserva', 'Gran Reserva', and 'Auslese' are protected under EU wine law and may only be used according to specific ageing requirements.",
        "domain": "wine_business",
        "subdomain": "eu_classification",
        "entities": [
            {"type": "classification", "name": "Reserva"},
            {"type": "classification", "name": "Riserva"},
        ],
        "tags": ["eu", "traditional_terms", "regulation"],
    },
    {
        "fact_text": "Wines with a PDO must undergo an analytical and organoleptic assessment by an approved body before being marketed.",
        "domain": "wine_business",
        "subdomain": "eu_classification",
        "entities": [{"type": "classification", "name": "PDO"}],
        "tags": ["eu", "pdo", "quality_control"],
    },
]

_EURLEX_LABELING_FACTS = [
    # Labeling rules (Delegated Reg 2019/33)
    {
        "fact_text": "EU wine labels must display the product category (e.g. 'wine', 'sparkling wine'), the PDO or PGI name if applicable, and the actual alcoholic strength by volume.",
        "domain": "wine_business",
        "subdomain": "labeling",
        "entities": [],
        "tags": ["eu", "labeling", "regulation"],
    },
    {
        "fact_text": "The vintage year may appear on a wine label only if at least 85 percent of the grapes used were harvested in that year.",
        "domain": "wine_business",
        "subdomain": "labeling",
        "entities": [],
        "tags": ["eu", "labeling", "vintage", "regulation"],
    },
    {
        "fact_text": "A single grape variety name may appear on a PDO or PGI wine label if at least 85 percent of the wine is made from that variety.",
        "domain": "wine_business",
        "subdomain": "labeling",
        "entities": [],
        "tags": ["eu", "labeling", "variety", "regulation"],
    },
    {
        "fact_text": "Two or three grape variety names may appear on an EU wine label if 100 percent of the wine is made from those varieties, listed in descending order of proportion.",
        "domain": "wine_business",
        "subdomain": "labeling",
        "entities": [],
        "tags": ["eu", "labeling", "variety", "regulation"],
    },
    {
        "fact_text": "EU wine labels must include allergen declarations for sulphites when the concentration exceeds 10 milligrams per litre.",
        "domain": "wine_business",
        "subdomain": "labeling",
        "entities": [{"type": "additive", "name": "sulphites"}],
        "tags": ["eu", "labeling", "allergens", "regulation"],
    },
    {
        "fact_text": "Since December 2023, EU wine labels must include a nutrition declaration and a list of ingredients, which may be provided via an electronic link (QR code).",
        "domain": "wine_business",
        "subdomain": "labeling",
        "entities": [],
        "tags": ["eu", "labeling", "nutrition", "regulation", "2023"],
    },
    {
        "fact_text": "The term 'estate bottled' on an EU wine label requires that the wine was made exclusively from grapes grown on the producer's own vineyards and bottled on the estate.",
        "domain": "wine_business",
        "subdomain": "labeling",
        "entities": [],
        "tags": ["eu", "labeling", "estate_bottled", "regulation"],
    },
    {
        "fact_text": "EU law mandates that the bottler's name and municipality appear on every wine label, preceded by the term 'bottled by' or an equivalent expression.",
        "domain": "wine_business",
        "subdomain": "labeling",
        "entities": [],
        "tags": ["eu", "labeling", "bottler", "regulation"],
    },
    {
        "fact_text": "The nominal volume of wine in a bottle must be stated on the EU label in litres, centilitres, or millilitres.",
        "domain": "wine_business",
        "subdomain": "labeling",
        "entities": [],
        "tags": ["eu", "labeling", "volume", "regulation"],
    },
    {
        "fact_text": "The lot number must appear on every EU wine label to enable traceability in case of safety issues.",
        "domain": "wine_business",
        "subdomain": "labeling",
        "entities": [],
        "tags": ["eu", "labeling", "traceability", "regulation"],
    },
    {
        "fact_text": "EU regulations prohibit the use of lead-based capsules on wine bottles.",
        "domain": "wine_business",
        "subdomain": "labeling",
        "entities": [],
        "tags": ["eu", "labeling", "lead", "safety", "regulation"],
    },
    {
        "fact_text": "The actual alcoholic strength on an EU wine label must be expressed as a percentage by volume with no more than one decimal place.",
        "domain": "wine_business",
        "subdomain": "labeling",
        "entities": [],
        "tags": ["eu", "labeling", "alcohol", "regulation"],
    },
    {
        "fact_text": "EU wine labels may indicate a smaller geographical unit than the PDO or PGI area (such as a single vineyard) if at least 85 percent of the grapes come from that unit.",
        "domain": "wine_business",
        "subdomain": "labeling",
        "entities": [],
        "tags": ["eu", "labeling", "vineyard", "regulation"],
    },
]

_EURLEX_OENOLOGICAL_FACTS = [
    # Permitted oenological practices (Delegated Reg 2019/934)
    {
        "fact_text": "Chaptalisation (adding sugar before fermentation to increase alcohol) is permitted in EU wine zones A and B (northern Europe) but prohibited in zone C III (southern regions).",
        "domain": "winemaking",
        "subdomain": "oenological_practices",
        "entities": [{"type": "process", "name": "chaptalisation"}],
        "tags": ["eu", "chaptalisation", "regulation"],
    },
    {
        "fact_text": "Acidification by adding tartaric acid is permitted in southern EU wine zones (C I, C II, C III) but not in northern zones (A and B) where enrichment is used instead.",
        "domain": "winemaking",
        "subdomain": "oenological_practices",
        "entities": [
            {"type": "process", "name": "acidification"},
            {"type": "additive", "name": "tartaric acid"},
        ],
        "tags": ["eu", "acidification", "regulation"],
    },
    {
        "fact_text": "De-acidification is permitted in all EU wine zones by adding calcium carbonate, neutral potassium tartrate, or potassium bicarbonate.",
        "domain": "winemaking",
        "subdomain": "oenological_practices",
        "entities": [{"type": "process", "name": "de-acidification"}],
        "tags": ["eu", "deacidification", "regulation"],
    },
    {
        "fact_text": "EU law divides wine-growing areas into zones A, B, C I(a), C I(b), C II, and C III based on climate, each with different enrichment and acidification rules.",
        "domain": "winemaking",
        "subdomain": "oenological_practices",
        "entities": [],
        "tags": ["eu", "wine_zones", "regulation"],
    },
    {
        "fact_text": "Zone A includes England, Belgium, the Netherlands, Denmark, northern Germany, and Poland; zone C III includes southern Spain, southern Italy, and Greece.",
        "domain": "winemaking",
        "subdomain": "oenological_practices",
        "entities": [],
        "tags": ["eu", "wine_zones", "geography"],
    },
    {
        "fact_text": "The maximum enrichment by chaptalisation in EU zone A is 3 percent volume of alcohol, while in zone B it is 2 percent.",
        "domain": "winemaking",
        "subdomain": "oenological_practices",
        "entities": [{"type": "process", "name": "chaptalisation"}],
        "tags": ["eu", "chaptalisation", "limits", "regulation"],
    },
    {
        "fact_text": "Enrichment by concentrated grape must or rectified concentrated grape must is permitted in all EU wine zones as an alternative to chaptalisation.",
        "domain": "winemaking",
        "subdomain": "oenological_practices",
        "entities": [
            {"type": "additive", "name": "concentrated grape must"},
            {"type": "additive", "name": "rectified concentrated grape must"},
        ],
        "tags": ["eu", "enrichment", "regulation"],
    },
    {
        "fact_text": "Sulphur dioxide additions in EU wines are limited to 150 milligrams per litre for dry red wines and 200 milligrams per litre for dry white and rosé wines.",
        "domain": "winemaking",
        "subdomain": "oenological_practices",
        "entities": [{"type": "additive", "name": "sulphur dioxide"}],
        "tags": ["eu", "so2", "limits", "regulation"],
    },
    {
        "fact_text": "Sweet wines with more than 5 grams per litre of residual sugar may contain up to 200 milligrams per litre of sulphur dioxide for red wines and 250 milligrams per litre for white wines under EU rules.",
        "domain": "winemaking",
        "subdomain": "oenological_practices",
        "entities": [{"type": "additive", "name": "sulphur dioxide"}],
        "tags": ["eu", "so2", "sweet_wine", "regulation"],
    },
    {
        "fact_text": "EU organic wines are limited to 100 milligrams per litre of sulphur dioxide for dry red wines and 150 milligrams per litre for dry white and rosé wines.",
        "domain": "winemaking",
        "subdomain": "oenological_practices",
        "entities": [{"type": "additive", "name": "sulphur dioxide"}],
        "tags": ["eu", "organic", "so2", "regulation"],
    },
    {
        "fact_text": "Oak chip contact is permitted in EU winemaking as an alternative to barrel ageing, but must be declared if the wine carries a PDO.",
        "domain": "winemaking",
        "subdomain": "oenological_practices",
        "entities": [{"type": "process", "name": "oak chip contact"}],
        "tags": ["eu", "oak", "regulation"],
    },
    {
        "fact_text": "The use of ion-exchange resins for tartrate stabilisation is an authorised oenological practice in the EU.",
        "domain": "winemaking",
        "subdomain": "oenological_practices",
        "entities": [{"type": "process", "name": "ion-exchange"}],
        "tags": ["eu", "stabilisation", "regulation"],
    },
    {
        "fact_text": "Reverse osmosis and vacuum evaporation are permitted in the EU for partial dealcoholisation of wine, up to a 2 percent volume reduction in alcohol.",
        "domain": "winemaking",
        "subdomain": "oenological_practices",
        "entities": [
            {"type": "process", "name": "reverse osmosis"},
            {"type": "process", "name": "vacuum evaporation"},
        ],
        "tags": ["eu", "dealcoholisation", "regulation"],
    },
    {
        "fact_text": "Electrodialysis is authorised in the EU for tartrate stabilisation as an alternative to cold stabilisation.",
        "domain": "winemaking",
        "subdomain": "oenological_practices",
        "entities": [{"type": "process", "name": "electrodialysis"}],
        "tags": ["eu", "stabilisation", "regulation"],
    },
    {
        "fact_text": "Spinning-cone column technology is permitted in the EU for partial dealcoholisation and volatile aroma recovery.",
        "domain": "winemaking",
        "subdomain": "oenological_practices",
        "entities": [{"type": "process", "name": "spinning-cone column"}],
        "tags": ["eu", "dealcoholisation", "technology", "regulation"],
    },
    {
        "fact_text": "Bentonite fining is authorised in the EU for protein stabilisation of white and rosé wines.",
        "domain": "winemaking",
        "subdomain": "oenological_practices",
        "entities": [
            {"type": "additive", "name": "bentonite"},
            {"type": "process", "name": "fining"},
        ],
        "tags": ["eu", "fining", "regulation"],
    },
    {
        "fact_text": "The use of polyvinylpolypyrrolidone (PVPP) for phenol removal is authorised in EU winemaking.",
        "domain": "winemaking",
        "subdomain": "oenological_practices",
        "entities": [{"type": "additive", "name": "PVPP"}],
        "tags": ["eu", "fining", "regulation"],
    },
    {
        "fact_text": "Potassium sorbate may be added to EU wines to inhibit secondary fermentation in bottle, up to a maximum of 200 milligrams per litre of sorbic acid.",
        "domain": "winemaking",
        "subdomain": "oenological_practices",
        "entities": [{"type": "additive", "name": "potassium sorbate"}],
        "tags": ["eu", "preservative", "regulation"],
    },
    {
        "fact_text": "Ascorbic acid (vitamin C) may be added to EU wines as an antioxidant, up to a maximum of 250 milligrams per litre.",
        "domain": "winemaking",
        "subdomain": "oenological_practices",
        "entities": [{"type": "additive", "name": "ascorbic acid"}],
        "tags": ["eu", "antioxidant", "regulation"],
    },
    {
        "fact_text": "Gum arabic (acacia gum) is authorised in EU winemaking for colloidal stabilisation and mouthfeel enhancement.",
        "domain": "winemaking",
        "subdomain": "oenological_practices",
        "entities": [{"type": "additive", "name": "gum arabic"}],
        "tags": ["eu", "stabilisation", "regulation"],
    },
    {
        "fact_text": "EU regulations permit the use of pectolytic enzymes during winemaking for clarification and improved juice extraction.",
        "domain": "winemaking",
        "subdomain": "oenological_practices",
        "entities": [{"type": "additive", "name": "pectolytic enzymes"}],
        "tags": ["eu", "enzymes", "regulation"],
    },
    {
        "fact_text": "Lysozyme is authorised in the EU for inhibiting malolactic fermentation, with a maximum dose of 500 milligrams per litre.",
        "domain": "winemaking",
        "subdomain": "oenological_practices",
        "entities": [{"type": "additive", "name": "lysozyme"}],
        "tags": ["eu", "enzymes", "regulation"],
    },
    {
        "fact_text": "Metatartaric acid may be added to EU wines for tartrate stabilisation at up to 100 milligrams per litre.",
        "domain": "winemaking",
        "subdomain": "oenological_practices",
        "entities": [{"type": "additive", "name": "metatartaric acid"}],
        "tags": ["eu", "stabilisation", "regulation"],
    },
    {
        "fact_text": "Dimethyl dicarbonate (DMDC) is authorised in the EU as an antimicrobial at bottling, at a maximum dose of 200 milligrams per litre.",
        "domain": "winemaking",
        "subdomain": "oenological_practices",
        "entities": [{"type": "additive", "name": "DMDC"}],
        "tags": ["eu", "antimicrobial", "regulation"],
    },
    {
        "fact_text": "EU wine law prohibits blending red and white wines to produce rosé, except in the case of sparkling wine production where it is permitted.",
        "domain": "winemaking",
        "subdomain": "oenological_practices",
        "entities": [],
        "tags": ["eu", "rosé", "blending", "regulation"],
    },
    {
        "fact_text": "Cryoextraction (freezing grapes before pressing) is a permitted oenological practice in the EU for concentrating grape must.",
        "domain": "winemaking",
        "subdomain": "oenological_practices",
        "entities": [{"type": "process", "name": "cryoextraction"}],
        "tags": ["eu", "concentration", "regulation"],
    },
]

_EURLEX_PDO_PGI_FACTS = [
    # E-Bacchus / PDO-PGI examples (Reg 607/2009 and database)
    {
        "fact_text": "France has over 360 registered PDO wines and approximately 75 PGI wines in the E-Bacchus database.",
        "domain": "wine_regions",
        "subdomain": "eu_classification",
        "entities": [{"type": "country", "name": "France"}],
        "tags": ["eu", "france", "pdo", "pgi"],
    },
    {
        "fact_text": "Italy has over 400 registered PDO wines (DOCG and DOC combined) and approximately 120 PGI (IGT) wines.",
        "domain": "wine_regions",
        "subdomain": "eu_classification",
        "entities": [{"type": "country", "name": "Italy"}],
        "tags": ["eu", "italy", "pdo", "pgi"],
    },
    {
        "fact_text": "Spain has over 90 registered PDO wines (including DOCa and DO) and approximately 40 PGI wines.",
        "domain": "wine_regions",
        "subdomain": "eu_classification",
        "entities": [{"type": "country", "name": "Spain"}],
        "tags": ["eu", "spain", "pdo", "pgi"],
    },
    {
        "fact_text": "Germany has 13 Anbaugebiete (wine regions) recognised as PDOs and 26 Landwein areas recognised as PGIs.",
        "domain": "wine_regions",
        "subdomain": "eu_classification",
        "entities": [{"type": "country", "name": "Germany"}],
        "tags": ["eu", "germany", "pdo", "pgi"],
    },
    {
        "fact_text": "Portugal has over 30 registered PDO wines (DOC) and approximately 14 PGI wines (Vinho Regional).",
        "domain": "wine_regions",
        "subdomain": "eu_classification",
        "entities": [{"type": "country", "name": "Portugal"}],
        "tags": ["eu", "portugal", "pdo", "pgi"],
    },
    {
        "fact_text": "Champagne is a registered EU PDO that requires production within the Champagne region of France using the traditional method (méthode champenoise).",
        "domain": "wine_regions",
        "subdomain": "eu_classification",
        "entities": [
            {"type": "appellation", "name": "Champagne"},
            {"type": "country", "name": "France"},
        ],
        "tags": ["eu", "champagne", "pdo"],
    },
    {
        "fact_text": "Prosecco is a registered EU PDO, with production restricted to the Veneto and Friuli Venezia Giulia regions of Italy.",
        "domain": "wine_regions",
        "subdomain": "eu_classification",
        "entities": [
            {"type": "appellation", "name": "Prosecco"},
            {"type": "country", "name": "Italy"},
        ],
        "tags": ["eu", "prosecco", "pdo"],
    },
    {
        "fact_text": "Rioja is a registered EU PDO classified as DOCa (Denominación de Origen Calificada), the highest Spanish wine category.",
        "domain": "wine_regions",
        "subdomain": "eu_classification",
        "entities": [
            {"type": "appellation", "name": "Rioja"},
            {"type": "country", "name": "Spain"},
        ],
        "tags": ["eu", "rioja", "pdo", "doca"],
    },
    {
        "fact_text": "Port wine is a registered EU PDO, requiring production from grapes grown in the Douro region and ageing in Vila Nova de Gaia, Portugal.",
        "domain": "wine_regions",
        "subdomain": "eu_classification",
        "entities": [
            {"type": "appellation", "name": "Port"},
            {"type": "region", "name": "Douro"},
        ],
        "tags": ["eu", "port", "pdo", "portugal"],
    },
    {
        "fact_text": "Tokaji is a registered EU PDO requiring production in the Tokaj wine region of Hungary using Furmint, Hárslevelű, or Muscat Blanc grapes.",
        "domain": "wine_regions",
        "subdomain": "eu_classification",
        "entities": [
            {"type": "appellation", "name": "Tokaji"},
            {"type": "country", "name": "Hungary"},
        ],
        "tags": ["eu", "tokaji", "pdo", "hungary"],
    },
]

_EURLEX_SPARKLING_FACTS = [
    # Sparkling wine categories (Reg 1308/2013 Annex VII Part II)
    {
        "fact_text": "EU sparkling wine must have a minimum total pressure of 3 bar at 20 degrees Celsius in a closed container.",
        "domain": "winemaking",
        "subdomain": "sparkling_wine",
        "entities": [],
        "tags": ["eu", "sparkling", "regulation"],
    },
    {
        "fact_text": "Quality sparkling wine (Sekt in Germany) must have a minimum pressure of 3.5 bar and be produced by a second fermentation.",
        "domain": "winemaking",
        "subdomain": "sparkling_wine",
        "entities": [],
        "tags": ["eu", "sparkling", "sekt", "regulation"],
    },
    {
        "fact_text": "Quality aromatic sparkling wine must be made from aromatic grape varieties such as Muscat, and may use the Charmat (tank) method.",
        "domain": "winemaking",
        "subdomain": "sparkling_wine",
        "entities": [{"type": "grape", "name": "Muscat"}],
        "tags": ["eu", "sparkling", "aromatic", "charmat"],
    },
    {
        "fact_text": "EU Crémant is a quality sparkling wine produced by traditional method in a designated region, with at least 9 months of lees ageing.",
        "domain": "winemaking",
        "subdomain": "sparkling_wine",
        "entities": [{"type": "classification", "name": "Crémant"}],
        "tags": ["eu", "cremant", "sparkling", "regulation"],
    },
    {
        "fact_text": "Semi-sparkling wine (pétillant or frizzante) has a pressure between 1 and 2.5 bar and is distinct from fully sparkling wine under EU law.",
        "domain": "winemaking",
        "subdomain": "sparkling_wine",
        "entities": [],
        "tags": ["eu", "petillant", "frizzante", "regulation"],
    },
    {
        "fact_text": "EU sparkling wine sweetness levels range from 'brut nature' (0–3 g/L sugar) to 'doux' (over 50 g/L sugar).",
        "domain": "winemaking",
        "subdomain": "sparkling_wine",
        "entities": [],
        "tags": ["eu", "sparkling", "sweetness", "regulation"],
    },
    {
        "fact_text": "The term 'brut' on an EU sparkling wine indicates a residual sugar content of less than 12 grams per litre.",
        "domain": "winemaking",
        "subdomain": "sparkling_wine",
        "entities": [],
        "tags": ["eu", "sparkling", "brut", "sweetness"],
    },
    {
        "fact_text": "The term 'extra brut' on an EU sparkling wine indicates a residual sugar content between 0 and 6 grams per litre.",
        "domain": "winemaking",
        "subdomain": "sparkling_wine",
        "entities": [],
        "tags": ["eu", "sparkling", "extra_brut", "sweetness"],
    },
]


# ─── OIV Fact Extraction ─────────────────────────────────────────────────────

# OIV statistics and standards. The OIV publishes aggregate data in reports and
# press releases. We rephrase these into atomic facts.

_OIV_STATISTICS_FACTS = [
    # Global wine production
    {
        "fact_text": "Global wine production in 2023 was approximately 237 million hectolitres, one of the lowest levels since the 1960s.",
        "domain": "wine_business",
        "subdomain": "global_statistics",
        "entities": [],
        "tags": ["oiv", "production", "statistics", "2023"],
    },
    {
        "fact_text": "Italy was the world's largest wine producer in 2023 with approximately 38.3 million hectolitres.",
        "domain": "wine_business",
        "subdomain": "global_statistics",
        "entities": [{"type": "country", "name": "Italy"}],
        "tags": ["oiv", "production", "italy", "2023"],
    },
    {
        "fact_text": "France was the world's second-largest wine producer in 2023 with approximately 45.8 million hectolitres in 2022 but lower output in 2023.",
        "domain": "wine_business",
        "subdomain": "global_statistics",
        "entities": [{"type": "country", "name": "France"}],
        "tags": ["oiv", "production", "france", "2023"],
    },
    {
        "fact_text": "Spain was the world's third-largest wine producer by volume, though it has the largest vineyard area globally.",
        "domain": "wine_business",
        "subdomain": "global_statistics",
        "entities": [{"type": "country", "name": "Spain"}],
        "tags": ["oiv", "production", "spain"],
    },
    {
        "fact_text": "The United States was the fourth-largest wine producer globally in 2023 with approximately 25.2 million hectolitres.",
        "domain": "wine_business",
        "subdomain": "global_statistics",
        "entities": [{"type": "country", "name": "United States"}],
        "tags": ["oiv", "production", "usa", "2023"],
    },
    {
        "fact_text": "Australia produced approximately 10.3 million hectolitres of wine in 2023, making it the fifth-largest producer.",
        "domain": "wine_business",
        "subdomain": "global_statistics",
        "entities": [{"type": "country", "name": "Australia"}],
        "tags": ["oiv", "production", "australia", "2023"],
    },
    {
        "fact_text": "Chile produced approximately 10.1 million hectolitres of wine in 2023, ranking as the sixth-largest producer.",
        "domain": "wine_business",
        "subdomain": "global_statistics",
        "entities": [{"type": "country", "name": "Chile"}],
        "tags": ["oiv", "production", "chile", "2023"],
    },
    {
        "fact_text": "Argentina produced approximately 8.8 million hectolitres of wine in 2023.",
        "domain": "wine_business",
        "subdomain": "global_statistics",
        "entities": [{"type": "country", "name": "Argentina"}],
        "tags": ["oiv", "production", "argentina", "2023"],
    },
    {
        "fact_text": "South Africa produced approximately 9.0 million hectolitres of wine in 2023.",
        "domain": "wine_business",
        "subdomain": "global_statistics",
        "entities": [{"type": "country", "name": "South Africa"}],
        "tags": ["oiv", "production", "south_africa", "2023"],
    },
    {
        "fact_text": "China's wine production has declined sharply since 2016, dropping below 4 million hectolitres by 2023.",
        "domain": "wine_business",
        "subdomain": "global_statistics",
        "entities": [{"type": "country", "name": "China"}],
        "tags": ["oiv", "production", "china", "2023"],
    },
    # Global wine consumption
    {
        "fact_text": "Global wine consumption in 2023 was approximately 221 million hectolitres, a continued decline from the peak of 250 million hectolitres in 2007.",
        "domain": "wine_business",
        "subdomain": "global_statistics",
        "entities": [],
        "tags": ["oiv", "consumption", "statistics", "2023"],
    },
    {
        "fact_text": "The United States was the world's largest wine-consuming country by total volume in 2023.",
        "domain": "wine_business",
        "subdomain": "global_statistics",
        "entities": [{"type": "country", "name": "United States"}],
        "tags": ["oiv", "consumption", "usa", "2023"],
    },
    {
        "fact_text": "France was the world's second-largest wine-consuming country by total volume in 2023, followed by Italy.",
        "domain": "wine_business",
        "subdomain": "global_statistics",
        "entities": [
            {"type": "country", "name": "France"},
            {"type": "country", "name": "Italy"},
        ],
        "tags": ["oiv", "consumption", "france", "italy", "2023"],
    },
    {
        "fact_text": "Portugal has the highest per-capita wine consumption in the world at approximately 52 litres per person per year.",
        "domain": "wine_business",
        "subdomain": "global_statistics",
        "entities": [{"type": "country", "name": "Portugal"}],
        "tags": ["oiv", "consumption", "per_capita", "portugal"],
    },
    {
        "fact_text": "France has the second-highest per-capita wine consumption at approximately 47 litres per person per year.",
        "domain": "wine_business",
        "subdomain": "global_statistics",
        "entities": [{"type": "country", "name": "France"}],
        "tags": ["oiv", "consumption", "per_capita", "france"],
    },
    {
        "fact_text": "Italy has the third-highest per-capita wine consumption at approximately 43 litres per person per year.",
        "domain": "wine_business",
        "subdomain": "global_statistics",
        "entities": [{"type": "country", "name": "Italy"}],
        "tags": ["oiv", "consumption", "per_capita", "italy"],
    },
    # Global vineyard area
    {
        "fact_text": "The global vineyard area in 2023 was approximately 7.2 million hectares.",
        "domain": "wine_business",
        "subdomain": "global_statistics",
        "entities": [],
        "tags": ["oiv", "vineyard_area", "statistics", "2023"],
    },
    {
        "fact_text": "Spain has the largest vineyard area in the world with approximately 955,000 hectares.",
        "domain": "wine_business",
        "subdomain": "global_statistics",
        "entities": [{"type": "country", "name": "Spain"}],
        "tags": ["oiv", "vineyard_area", "spain"],
    },
    {
        "fact_text": "France has the second-largest vineyard area at approximately 812,000 hectares.",
        "domain": "wine_business",
        "subdomain": "global_statistics",
        "entities": [{"type": "country", "name": "France"}],
        "tags": ["oiv", "vineyard_area", "france"],
    },
    {
        "fact_text": "China has the third-largest vineyard area at approximately 785,000 hectares, though most vines are for table grapes rather than wine.",
        "domain": "wine_business",
        "subdomain": "global_statistics",
        "entities": [{"type": "country", "name": "China"}],
        "tags": ["oiv", "vineyard_area", "china"],
    },
    # Global wine trade
    {
        "fact_text": "Global wine exports by volume totalled approximately 100 million hectolitres in 2023.",
        "domain": "wine_business",
        "subdomain": "global_statistics",
        "entities": [],
        "tags": ["oiv", "trade", "exports", "2023"],
    },
    {
        "fact_text": "Italy was the world's largest wine exporter by volume in 2023, followed by Spain and France.",
        "domain": "wine_business",
        "subdomain": "global_statistics",
        "entities": [
            {"type": "country", "name": "Italy"},
            {"type": "country", "name": "Spain"},
            {"type": "country", "name": "France"},
        ],
        "tags": ["oiv", "trade", "exports", "2023"],
    },
    {
        "fact_text": "France was the world's largest wine exporter by value in 2023, owing to high-value Champagne, Bordeaux, and Burgundy exports.",
        "domain": "wine_business",
        "subdomain": "global_statistics",
        "entities": [{"type": "country", "name": "France"}],
        "tags": ["oiv", "trade", "exports", "value", "2023"],
    },
    {
        "fact_text": "Germany was the world's largest wine importer by volume in 2023, followed by the United Kingdom and the United States.",
        "domain": "wine_business",
        "subdomain": "global_statistics",
        "entities": [
            {"type": "country", "name": "Germany"},
            {"type": "country", "name": "United Kingdom"},
            {"type": "country", "name": "United States"},
        ],
        "tags": ["oiv", "trade", "imports", "2023"],
    },
]

_OIV_OENOLOGICAL_CODEX_FACTS = [
    # OIV International Code of Oenological Practices
    {
        "fact_text": "The OIV International Code of Oenological Practices defines reference standards for winemaking techniques adopted by its 50 member states.",
        "domain": "winemaking",
        "subdomain": "oiv_standards",
        "entities": [{"type": "organisation", "name": "OIV"}],
        "tags": ["oiv", "codex", "standards"],
    },
    {
        "fact_text": "The OIV defines wine as the beverage resulting exclusively from the partial or complete alcoholic fermentation of fresh grapes or grape must.",
        "domain": "winemaking",
        "subdomain": "oiv_standards",
        "entities": [{"type": "organisation", "name": "OIV"}],
        "tags": ["oiv", "definition", "wine"],
    },
    {
        "fact_text": "The OIV sets a minimum natural alcoholic strength of 8.5 percent by volume for wines produced in EU zone C and 9 percent for other zones.",
        "domain": "winemaking",
        "subdomain": "oiv_standards",
        "entities": [{"type": "organisation", "name": "OIV"}],
        "tags": ["oiv", "alcohol", "minimum", "standards"],
    },
    {
        "fact_text": "The OIV distinguishes between wine, special wine (fortified, aromatised), and wine-based beverages in its classification system.",
        "domain": "winemaking",
        "subdomain": "oiv_standards",
        "entities": [{"type": "organisation", "name": "OIV"}],
        "tags": ["oiv", "classification", "standards"],
    },
    {
        "fact_text": "Malolactic fermentation, the conversion of malic acid to lactic acid by lactic acid bacteria, is recognised by the OIV as a standard oenological practice.",
        "domain": "winemaking",
        "subdomain": "oiv_standards",
        "entities": [{"type": "process", "name": "malolactic fermentation"}],
        "tags": ["oiv", "mlf", "standards"],
    },
    {
        "fact_text": "Cold stabilisation to precipitate tartrate crystals is an OIV-recognised oenological practice for preventing tartrate deposits in bottled wine.",
        "domain": "winemaking",
        "subdomain": "oiv_standards",
        "entities": [{"type": "process", "name": "cold stabilisation"}],
        "tags": ["oiv", "stabilisation", "standards"],
    },
    {
        "fact_text": "The OIV recommends that total volatile acidity in wine should not exceed 1.2 grams per litre expressed as acetic acid for red wines.",
        "domain": "winemaking",
        "subdomain": "oiv_standards",
        "entities": [],
        "tags": ["oiv", "volatile_acidity", "standards"],
    },
    {
        "fact_text": "The OIV Compendium of International Methods of Analysis specifies standard laboratory methods for measuring alcohol, acidity, residual sugar, and sulphur dioxide in wine.",
        "domain": "winemaking",
        "subdomain": "oiv_standards",
        "entities": [{"type": "organisation", "name": "OIV"}],
        "tags": ["oiv", "analysis", "standards"],
    },
    {
        "fact_text": "The OIV recognises the use of selected yeasts (Saccharomyces cerevisiae strains) for controlled fermentation as a standard practice.",
        "domain": "winemaking",
        "subdomain": "oiv_standards",
        "entities": [
            {"type": "organism", "name": "Saccharomyces cerevisiae"},
        ],
        "tags": ["oiv", "yeast", "fermentation", "standards"],
    },
    {
        "fact_text": "The OIV permits micro-oxygenation as a technique for controlled oxygen exposure during wine maturation.",
        "domain": "winemaking",
        "subdomain": "oiv_standards",
        "entities": [{"type": "process", "name": "micro-oxygenation"}],
        "tags": ["oiv", "micro_oxygenation", "standards"],
    },
    {
        "fact_text": "The OIV International Oenological Codex lists permitted additives, processing aids, and their maximum dosage limits for winemaking.",
        "domain": "winemaking",
        "subdomain": "oiv_standards",
        "entities": [{"type": "organisation", "name": "OIV"}],
        "tags": ["oiv", "codex", "additives", "standards"],
    },
    {
        "fact_text": "Activated carbon is permitted by the OIV for decolourising musts and removing off-odours, but must be removed before fermentation.",
        "domain": "winemaking",
        "subdomain": "oiv_standards",
        "entities": [{"type": "additive", "name": "activated carbon"}],
        "tags": ["oiv", "fining", "standards"],
    },
    {
        "fact_text": "The OIV classifies cork taint (2,4,6-trichloroanisole or TCA) as a major wine fault and publishes detection methods in its Compendium of Methods.",
        "domain": "winemaking",
        "subdomain": "oiv_standards",
        "entities": [{"type": "compound", "name": "TCA"}],
        "tags": ["oiv", "cork_taint", "fault", "standards"],
    },
]

_OIV_VARIETY_FACTS = [
    # OIV grape variety data
    {
        "fact_text": "Cabernet Sauvignon is the most widely planted grape variety in the world with approximately 341,000 hectares globally.",
        "domain": "grape_varieties",
        "subdomain": "oiv_varieties",
        "entities": [{"type": "grape", "name": "Cabernet Sauvignon"}],
        "tags": ["oiv", "cabernet_sauvignon", "planting"],
    },
    {
        "fact_text": "Merlot is the second-most planted grape variety in the world with approximately 266,000 hectares.",
        "domain": "grape_varieties",
        "subdomain": "oiv_varieties",
        "entities": [{"type": "grape", "name": "Merlot"}],
        "tags": ["oiv", "merlot", "planting"],
    },
    {
        "fact_text": "Tempranillo is the third-most planted grape variety globally with approximately 231,000 hectares, predominantly in Spain.",
        "domain": "grape_varieties",
        "subdomain": "oiv_varieties",
        "entities": [
            {"type": "grape", "name": "Tempranillo"},
            {"type": "country", "name": "Spain"},
        ],
        "tags": ["oiv", "tempranillo", "planting"],
    },
    {
        "fact_text": "Airén is the fourth-most planted grape variety globally with approximately 218,000 hectares, almost entirely in Spain's La Mancha region.",
        "domain": "grape_varieties",
        "subdomain": "oiv_varieties",
        "entities": [
            {"type": "grape", "name": "Airén"},
            {"type": "region", "name": "La Mancha"},
        ],
        "tags": ["oiv", "airen", "planting"],
    },
    {
        "fact_text": "Chardonnay is the most widely planted white wine grape used for quality wine production, with approximately 210,000 hectares globally.",
        "domain": "grape_varieties",
        "subdomain": "oiv_varieties",
        "entities": [{"type": "grape", "name": "Chardonnay"}],
        "tags": ["oiv", "chardonnay", "planting"],
    },
    {
        "fact_text": "Syrah (known as Shiraz in Australia) is planted on approximately 190,000 hectares worldwide.",
        "domain": "grape_varieties",
        "subdomain": "oiv_varieties",
        "entities": [{"type": "grape", "name": "Syrah"}],
        "tags": ["oiv", "syrah", "shiraz", "planting"],
    },
    {
        "fact_text": "Grenache (Garnacha) is planted on approximately 163,000 hectares globally, primarily in Spain and southern France.",
        "domain": "grape_varieties",
        "subdomain": "oiv_varieties",
        "entities": [{"type": "grape", "name": "Grenache"}],
        "tags": ["oiv", "grenache", "garnacha", "planting"],
    },
    {
        "fact_text": "Sauvignon Blanc is planted on approximately 124,000 hectares worldwide, with major plantings in France, New Zealand, and Chile.",
        "domain": "grape_varieties",
        "subdomain": "oiv_varieties",
        "entities": [{"type": "grape", "name": "Sauvignon Blanc"}],
        "tags": ["oiv", "sauvignon_blanc", "planting"],
    },
    {
        "fact_text": "Pinot Noir is planted on approximately 115,000 hectares globally, with the largest plantings in France, Germany, and the United States.",
        "domain": "grape_varieties",
        "subdomain": "oiv_varieties",
        "entities": [{"type": "grape", "name": "Pinot Noir"}],
        "tags": ["oiv", "pinot_noir", "planting"],
    },
    {
        "fact_text": "Trebbiano (Ugni Blanc) is one of the most planted white grape varieties with approximately 111,000 hectares, largely used for brandy distillation in France.",
        "domain": "grape_varieties",
        "subdomain": "oiv_varieties",
        "entities": [{"type": "grape", "name": "Trebbiano"}],
        "tags": ["oiv", "trebbiano", "ugni_blanc", "planting"],
    },
    {
        "fact_text": "The OIV maintains an international list of vine varieties and their synonyms, currently containing over 6,000 registered grape variety names.",
        "domain": "grape_varieties",
        "subdomain": "oiv_varieties",
        "entities": [{"type": "organisation", "name": "OIV"}],
        "tags": ["oiv", "variety_list", "register"],
    },
    {
        "fact_text": "Riesling is planted on approximately 51,000 hectares worldwide, with over 60 percent of plantings in Germany.",
        "domain": "grape_varieties",
        "subdomain": "oiv_varieties",
        "entities": [
            {"type": "grape", "name": "Riesling"},
            {"type": "country", "name": "Germany"},
        ],
        "tags": ["oiv", "riesling", "planting"],
    },
    {
        "fact_text": "Malbec is planted on approximately 53,000 hectares worldwide, with about 75 percent of global plantings in Argentina.",
        "domain": "grape_varieties",
        "subdomain": "oiv_varieties",
        "entities": [
            {"type": "grape", "name": "Malbec"},
            {"type": "country", "name": "Argentina"},
        ],
        "tags": ["oiv", "malbec", "planting"],
    },
    {
        "fact_text": "Sangiovese is planted on approximately 71,000 hectares, almost exclusively in Italy where it is the primary grape for Chianti and Brunello di Montalcino.",
        "domain": "grape_varieties",
        "subdomain": "oiv_varieties",
        "entities": [
            {"type": "grape", "name": "Sangiovese"},
            {"type": "country", "name": "Italy"},
        ],
        "tags": ["oiv", "sangiovese", "planting"],
    },
    {
        "fact_text": "Nebbiolo is planted on approximately 6,000 hectares, almost entirely in Piedmont, Italy, where it produces Barolo and Barbaresco wines.",
        "domain": "grape_varieties",
        "subdomain": "oiv_varieties",
        "entities": [
            {"type": "grape", "name": "Nebbiolo"},
            {"type": "region", "name": "Piedmont"},
        ],
        "tags": ["oiv", "nebbiolo", "planting"],
    },
]

_OIV_SUSTAINABILITY_FACTS = [
    # OIV sustainability and climate
    {
        "fact_text": "The OIV has adopted guidelines for sustainable vitiviniculture covering environmental, social, and economic pillars.",
        "domain": "viticulture",
        "subdomain": "sustainability",
        "entities": [{"type": "organisation", "name": "OIV"}],
        "tags": ["oiv", "sustainability", "guidelines"],
    },
    {
        "fact_text": "The OIV estimates that climate change has advanced grape harvest dates by an average of two to three weeks over the past 50 years in European wine regions.",
        "domain": "viticulture",
        "subdomain": "climate",
        "entities": [{"type": "organisation", "name": "OIV"}],
        "tags": ["oiv", "climate_change", "harvest"],
    },
    {
        "fact_text": "The OIV recommends integrated pest management (IPM) as the standard approach for vine disease control in its sustainability guidelines.",
        "domain": "viticulture",
        "subdomain": "sustainability",
        "entities": [{"type": "practice", "name": "IPM"}],
        "tags": ["oiv", "ipm", "sustainability"],
    },
    {
        "fact_text": "According to the OIV, the global area under organic viticulture was approximately 540,000 hectares in 2022, representing about 7.5 percent of total vineyard area.",
        "domain": "viticulture",
        "subdomain": "sustainability",
        "entities": [],
        "tags": ["oiv", "organic", "statistics"],
    },
    {
        "fact_text": "The OIV defines three categories of sustainability certification: organic, biodynamic, and integrated production.",
        "domain": "viticulture",
        "subdomain": "sustainability",
        "entities": [{"type": "organisation", "name": "OIV"}],
        "tags": ["oiv", "certification", "sustainability"],
    },
    {
        "fact_text": "Water stress management is a key focus of OIV sustainability guidelines, recommending deficit irrigation where permitted and drought-resistant rootstocks.",
        "domain": "viticulture",
        "subdomain": "sustainability",
        "entities": [],
        "tags": ["oiv", "water", "irrigation", "sustainability"],
    },
]

_OIV_ADDITIONAL_FACTS = [
    # OIV institutional and membership facts
    {
        "fact_text": "The OIV (International Organisation of Vine and Wine) was established in 2001 as the successor to the International Vine and Wine Office founded in 1924.",
        "domain": "wine_business",
        "subdomain": "oiv_standards",
        "entities": [{"type": "organisation", "name": "OIV"}],
        "tags": ["oiv", "history", "institution"],
    },
    {
        "fact_text": "The OIV is headquartered in Dijon, France, having relocated from Paris in 2022.",
        "domain": "wine_business",
        "subdomain": "oiv_standards",
        "entities": [{"type": "organisation", "name": "OIV"}],
        "tags": ["oiv", "headquarters", "institution"],
    },
    {
        "fact_text": "The OIV has 50 member states representing approximately 85 percent of global wine production.",
        "domain": "wine_business",
        "subdomain": "oiv_standards",
        "entities": [{"type": "organisation", "name": "OIV"}],
        "tags": ["oiv", "membership", "institution"],
    },
    {
        "fact_text": "The United States is not a member of the OIV, though it participates as an observer.",
        "domain": "wine_business",
        "subdomain": "oiv_standards",
        "entities": [
            {"type": "country", "name": "United States"},
            {"type": "organisation", "name": "OIV"},
        ],
        "tags": ["oiv", "membership", "usa"],
    },
    {
        "fact_text": "OIV resolutions adopted by consensus become non-binding recommendations that many countries incorporate into their national wine legislation.",
        "domain": "wine_business",
        "subdomain": "oiv_standards",
        "entities": [{"type": "organisation", "name": "OIV"}],
        "tags": ["oiv", "resolutions", "legislation"],
    },
]


# ─── Fact Collection Builders ─────────────────────────────────────────────────

def _build_eurlex_facts(source_id: str) -> list[dict]:
    """Build all EUR-Lex facts with proper source_id attached."""
    all_facts = []
    fact_sets = [
        _EURLEX_CLASSIFICATION_FACTS,
        _EURLEX_LABELING_FACTS,
        _EURLEX_OENOLOGICAL_FACTS,
        _EURLEX_PDO_PGI_FACTS,
        _EURLEX_SPARKLING_FACTS,
    ]
    for fact_set in fact_sets:
        for fact in fact_set:
            fact_with_source = dict(fact)
            fact_with_source["source_id"] = source_id
            all_facts.append(fact_with_source)
    return all_facts


def _build_oiv_facts(source_id: str) -> list[dict]:
    """Build all OIV facts with proper source_id attached."""
    all_facts = []
    fact_sets = [
        _OIV_STATISTICS_FACTS,
        _OIV_OENOLOGICAL_CODEX_FACTS,
        _OIV_VARIETY_FACTS,
        _OIV_SUSTAINABILITY_FACTS,
        _OIV_ADDITIONAL_FACTS,
    ]
    for fact_set in fact_sets:
        for fact in fact_set:
            fact_with_source = dict(fact)
            fact_with_source["source_id"] = source_id
            all_facts.append(fact_with_source)
    return all_facts


def _try_scrape_eurlex(source_id: str) -> list[dict]:
    """Attempt to scrape additional facts from EUR-Lex HTML pages.

    Returns any additional facts found beyond the curated set. If pages
    are unreachable, returns an empty list (curated facts still get used).
    """
    additional_facts = []
    for page in SOURCES["eurlex"]["pages"]:
        soup = _get_soup(page["url"])
        if soup is None:
            logger.info(f"Could not reach {page['id']}, using curated facts only")
            continue

        text = soup.get_text(separator=" ", strip=True)
        # Extract additional wine-related terms and definitions from regulation text
        additional_facts.extend(
            _extract_regulation_facts(text, page["id"], source_id)
        )
    return additional_facts


def _extract_regulation_facts(
    text: str, page_id: str, source_id: str
) -> list[dict]:
    """Extract additional structured facts from EUR-Lex regulation text.

    Looks for definitional patterns in EU regulation text (e.g. 'means ...',
    'shall ...', definitions sections) and converts them to atomic facts.
    Only extracts clearly wine-related content.
    """
    facts = []
    seen_keys = set()

    # Look for wine product definitions (e.g. "liqueur wine", "semi-sparkling wine")
    wine_product_patterns = [
        (r"['\u2018]([Ll]iqueur wine)['\u2019].*?means\s+(.+?\.)", "winemaking", "wine_types"),
        (r"['\u2018]([Ff]ortified wine)['\u2019].*?means\s+(.+?\.)", "winemaking", "wine_types"),
        (r"['\u2018]([Aa]romatised wine)['\u2019].*?means\s+(.+?\.)", "winemaking", "wine_types"),
    ]
    for pattern, domain, subdomain in wine_product_patterns:
        for match in re.finditer(pattern, text[:50000]):
            term = match.group(1).strip()
            definition = match.group(2).strip()
            if len(definition.split()) < 5 or len(definition.split()) > 50:
                continue
            key = f"eurlex_def:{term.lower()}"
            if key in seen_keys:
                continue
            seen_keys.add(key)
            fact_text = f"Under EU regulation, {term.lower()} is defined as a wine that {definition.lower()}"
            if not fact_text.endswith("."):
                fact_text += "."
            facts.append({
                "fact_text": fact_text,
                "domain": domain,
                "subdomain": subdomain,
                "source_id": source_id,
                "entities": [{"type": "wine_type", "name": term}],
                "tags": ["eu", "definition", "regulation", page_id],
            })

    return facts


def _try_scrape_oiv(source_id: str) -> list[dict]:
    """Attempt to scrape additional facts from OIV web pages.

    Returns any additional facts found. If pages are unreachable,
    returns empty list.
    """
    additional_facts = []
    for page in SOURCES["oiv"]["pages"]:
        soup = _get_soup(page["url"])
        if soup is None:
            logger.info(f"Could not reach {page['id']}, using curated facts only")
            continue

        text = soup.get_text(separator=" ", strip=True)
        additional_facts.extend(
            _extract_oiv_page_facts(text, page["id"], source_id)
        )
    return additional_facts


def _extract_oiv_page_facts(
    text: str, page_id: str, source_id: str
) -> list[dict]:
    """Extract additional structured facts from OIV page text.

    Looks for statistical data patterns (numbers + hectolitres, hectares, etc.)
    and converts them to atomic facts.
    """
    facts = []
    seen_keys = set()

    # Look for country + production/area statistics
    stat_patterns = [
        (
            r"(\d[\d,.]+)\s*(?:million\s+)?(?:hectolitres|hL|hl)",
            "production",
            "wine_business",
            "global_statistics",
        ),
        (
            r"(\d[\d,.]+)\s*(?:million\s+)?(?:hectares|ha)",
            "area",
            "wine_business",
            "global_statistics",
        ),
    ]
    countries = [
        "Italy", "France", "Spain", "Germany", "United States",
        "China", "Australia", "Argentina", "Chile", "South Africa",
        "Portugal", "Romania", "New Zealand", "Greece", "Hungary",
    ]

    for pattern, stat_type, domain, subdomain in stat_patterns:
        for match in re.finditer(pattern, text[:50000]):
            value = match.group(1)
            context_start = max(0, match.start() - 200)
            context = text[context_start : match.end() + 100]
            for country in countries:
                if country.lower() in context.lower():
                    key = f"oiv_stat:{country}:{stat_type}:{value}"
                    if key in seen_keys:
                        continue
                    seen_keys.add(key)
                    if stat_type == "production":
                        fact_text = f"According to OIV data, {country} produced {value} hectolitres of wine."
                    else:
                        fact_text = f"According to OIV data, {country} has a vineyard area of {value} hectares."
                    facts.append({
                        "fact_text": fact_text,
                        "domain": domain,
                        "subdomain": subdomain,
                        "source_id": source_id,
                        "entities": [{"type": "country", "name": country}],
                        "tags": ["oiv", stat_type, country.lower().replace(" ", "_"), page_id],
                    })

    return facts


# ─── Source Pipeline ──────────────────────────────────────────────────────────

def run_source(source_name: str, dry_run: bool = False) -> tuple[int, list[dict]]:
    """Run extraction for a single source. Returns (count, facts)."""
    if source_name not in SOURCES:
        logger.error(f"Unknown source: {source_name}. Available: {list(SOURCES.keys())}")
        return 0, []

    src_config = SOURCES[source_name]
    logger.info(f"Running source: {source_name} — {src_config['description']}")

    # Register source
    if dry_run:
        source_id = "dry-run"
    else:
        source_id = ensure_source(
            name=src_config["name"],
            url=src_config["base_url"],
            source_type=src_config["source_type"],
            tier=src_config["tier"],
        )

    # Build curated facts
    if source_name == "eurlex":
        facts = _build_eurlex_facts(source_id)
        logger.info(f"Built {len(facts)} curated EUR-Lex facts")
        # Try scraping for additional facts
        extra = _try_scrape_eurlex(source_id)
        if extra:
            logger.info(f"Scraped {len(extra)} additional EUR-Lex facts")
            facts.extend(extra)
    elif source_name == "oiv":
        facts = _build_oiv_facts(source_id)
        logger.info(f"Built {len(facts)} curated OIV facts")
        # Try scraping for additional facts
        extra = _try_scrape_oiv(source_id)
        if extra:
            logger.info(f"Scraped {len(extra)} additional OIV facts")
            facts.extend(extra)
    else:
        facts = []

    logger.info(f"Total facts for {source_name}: {len(facts)}")

    if dry_run:
        click.echo(f"\n[DRY RUN] Would insert {len(facts)} facts from {source_name}")
        return len(facts), facts

    # Insert into PostgreSQL
    inserted = insert_facts_batch(facts)
    logger.info(f"Inserted {inserted} new facts from {source_name} (duplicates skipped)")
    return inserted, facts


def run_all_sources(dry_run: bool = False) -> dict:
    """Run extraction for all sources. Returns summary."""
    summary = {}
    total = 0
    all_facts = []

    for name in SOURCES:
        count, facts = run_source(name, dry_run=dry_run)
        summary[name] = count
        total += count
        all_facts.extend(facts)

    logger.info(f"EU/OIV scraping complete. Total facts: {total}")
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
    click.echo(f"  Too short (<5 words):  {len(too_short)} ({100 * len(too_short) / total:.1f}%)")
    click.echo(f"  Too long (>50 words):  {len(too_long)} ({100 * len(too_long) / total:.1f}%)")

    # (c) Entity-name-only facts (no predicate — single word without punctuation)
    no_predicate = [
        f
        for f in facts
        if len(f["fact_text"].rstrip(".").strip().split()) <= 1
    ]
    click.echo(
        f"  No-predicate facts:    {len(no_predicate)} ({100 * len(no_predicate) / total:.1f}%)"
    )

    # (d) Near-duplicate check (substring containment, sampled)
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


# ─── CLI ──────────────────────────────────────────────────────────────────────

@click.command()
@click.option(
    "--source",
    "-s",
    type=click.Choice(["eurlex", "oiv"]),
    help="Run a specific source (eurlex or oiv)",
)
@click.option("--all", "run_all", is_flag=True, help="Run all sources")
@click.option("--list", "list_sources", is_flag=True, help="List available sources")
@click.option(
    "--dry-run", "dry_run", is_flag=True, help="Extract facts but do not insert into DB"
)
@click.option(
    "--validate",
    "validate_flag",
    is_flag=True,
    help="Run quality checks on extracted facts",
)
def main(
    source: Optional[str],
    run_all: bool,
    list_sources: bool,
    dry_run: bool,
    validate_flag: bool,
):
    """OenoBench EU/OIV Scraper — Extract wine regulatory facts from EUR-Lex and OIV."""
    logger.add("data/logs/eu_oiv_{time}.log", rotation="10 MB")

    if list_sources:
        click.echo("\nAvailable sources:")
        for name, cfg in SOURCES.items():
            click.echo(f"  {name:20s} — {cfg['description']}")
            for page in cfg["pages"]:
                click.echo(f"    {page['id']:30s} {page['url']}")
        return

    if validate_flag:
        click.echo("Running validation on all sources...")
        all_facts = []
        all_facts.extend(_build_eurlex_facts("dry-run"))
        all_facts.extend(_build_oiv_facts("dry-run"))
        validate_facts(all_facts)
        return

    if run_all:
        summary = run_all_sources(dry_run=dry_run)
        click.echo("\nSummary:")
        for name, count in summary.items():
            label = f"{name} (dry-run)" if dry_run else name
            click.echo(f"  {label:30s}: {count} facts")
        click.echo(f"  {'TOTAL':30s}: {sum(summary.values())} facts")
        return

    if source:
        count, facts = run_source(source, dry_run=dry_run)
        if dry_run:
            click.echo(f"\n[DRY RUN] {count} facts extracted from '{source}'.")
            validate_facts(facts)
        else:
            click.echo(f"\nInserted {count} new facts from '{source}'.")
        return

    click.echo("Use --all to run all sources, or --source <name> for a specific one.")
    click.echo("Use --list to see available sources.")
    click.echo("Use --dry-run to preview without inserting.")
    click.echo("Use --validate to run quality checks.")


if __name__ == "__main__":
    main()
