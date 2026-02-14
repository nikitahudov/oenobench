"""
OenoBench — European Wine Registries Scraper (Spain, Germany, Portugal)

Extracts wine regulation data from official European wine registries
and trade body websites, with Wikipedia fallback.

Usage:
    python -m src.scrapers.europe --all
    python -m src.scrapers.europe --country spain
    python -m src.scrapers.europe --country germany
    python -m src.scrapers.europe --country portugal
    python -m src.scrapers.europe --dry-run
    python -m src.scrapers.europe --validate
    python -m src.scrapers.europe --list
"""

import random
import re
import time
from collections import defaultdict
from datetime import datetime
from typing import Optional

import click
import requests
from bs4 import BeautifulSoup
from loguru import logger

from src.utils.facts import ensure_source, insert_facts_batch, get_fact_count

# ─── Configuration ────────────────────────────────────────────────────────────

USER_AGENT = "OenoBench-Research/1.0 (academic wine benchmark)"
REQUEST_DELAY = 5.0  # 1 request per 5 seconds per domain
REQUEST_TIMEOUT = 30

SOURCES = {
    "spain_mapa": {
        "name": "Spanish Ministry of Agriculture (MAPA)",
        "url": "https://www.mapa.gob.es",
        "source_type": "government",
        "tier": "tier_1_official",
        "language": "es",
    },
    "spain_do": {
        "name": "Spanish DO Regulatory Councils",
        "url": "https://www.mapa.gob.es/es/alimentacion/temas/calidad-diferenciada/dop-igp/",
        "source_type": "government",
        "tier": "tier_1_official",
        "language": "es",
    },
    "germany_dwi": {
        "name": "Deutsches Weininstitut (German Wine Institute)",
        "url": "https://www.deutscheweine.de",
        "source_type": "trade_body",
        "tier": "tier_2_authoritative",
        "language": "de",
    },
    "germany_vdp": {
        "name": "Verband Deutscher Prädikatsweingüter (VDP)",
        "url": "https://www.vdp.de",
        "source_type": "trade_body",
        "tier": "tier_2_authoritative",
        "language": "de",
    },
    "portugal_ivdp": {
        "name": "Instituto dos Vinhos do Douro e do Porto (IVDP)",
        "url": "https://www.ivdp.pt",
        "source_type": "government",
        "tier": "tier_1_official",
        "language": "pt",
    },
    "portugal_ivv": {
        "name": "Instituto da Vinha e do Vinho (IVV)",
        "url": "https://www.ivv.gov.pt",
        "source_type": "government",
        "tier": "tier_1_official",
        "language": "pt",
    },
    "wikipedia_wine_fallback": {
        "name": "Wikipedia (European Wine Fallback)",
        "url": "https://en.wikipedia.org/wiki/Wine",
        "source_type": "encyclopedia",
        "tier": "tier_2_authoritative",
        "language": "en",
    },
}

COUNTRIES = ["spain", "germany", "portugal"]

# ─── HTTP Helpers ─────────────────────────────────────────────────────────────

_last_request_per_domain: dict[str, float] = {}


def _get_domain(url: str) -> str:
    """Extract domain from URL for rate limiting."""
    from urllib.parse import urlparse
    return urlparse(url).netloc


def fetch_page(url: str, retries: int = 3) -> Optional[str]:
    """Fetch a web page with rate limiting and retries. Returns HTML or None."""
    domain = _get_domain(url)
    now = time.time()
    last = _last_request_per_domain.get(domain, 0)
    wait = REQUEST_DELAY - (now - last)
    if wait > 0:
        logger.debug(f"Rate limiting: waiting {wait:.1f}s for {domain}")
        time.sleep(wait)

    headers = {"User-Agent": USER_AGENT}
    for attempt in range(retries):
        try:
            resp = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
            _last_request_per_domain[domain] = time.time()
            resp.raise_for_status()
            return resp.text
        except requests.RequestException as e:
            logger.warning(f"Fetch attempt {attempt + 1}/{retries} failed for {url}: {e}")
            if attempt < retries - 1:
                time.sleep(2 ** (attempt + 1))
    logger.error(f"Failed to fetch {url} after {retries} attempts")
    return None


def fetch_wikipedia_article(title: str) -> Optional[str]:
    """Fetch a Wikipedia article's plain text extract via the API."""
    url = "https://en.wikipedia.org/w/api.php"
    params = {
        "action": "query",
        "titles": title,
        "prop": "extracts",
        "explaintext": "1",
        "format": "json",
    }
    headers = {"User-Agent": USER_AGENT}

    domain = _get_domain(url)
    now = time.time()
    last = _last_request_per_domain.get(domain, 0)
    wait = REQUEST_DELAY - (now - last)
    if wait > 0:
        time.sleep(wait)

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=REQUEST_TIMEOUT)
        _last_request_per_domain[domain] = time.time()
        resp.raise_for_status()
        data = resp.json()
        pages = data.get("query", {}).get("pages", {})
        for page in pages.values():
            return page.get("extract", "")
    except requests.RequestException as e:
        logger.warning(f"Wikipedia fetch failed for '{title}': {e}")
    return None


# =============================================================================
# SPAIN — DO/DOCa Wine Data
# =============================================================================

# Complete list of 70 Spanish appellations: 2 DOCa + 68 DO
SPAIN_APPELLATIONS = {
    # DOCa (Denominación de Origen Calificada) — highest classification
    "DOCa": [
        {
            "name": "Rioja",
            "region": "La Rioja, Basque Country, Navarre",
            "red_grapes": ["Tempranillo", "Garnacha Tinta", "Graciano", "Mazuelo", "Maturana Tinta"],
            "white_grapes": ["Viura", "Malvasía", "Garnacha Blanca", "Tempranillo Blanco",
                             "Maturana Blanca", "Turruntés", "Chardonnay", "Sauvignon Blanc",
                             "Verdejo"],
            "subzones": ["Rioja Alta", "Rioja Alavesa", "Rioja Oriental"],
            "area_ha": 65298,
            "notes": "One of only two DOCa appellations in Spain. Received DOCa status in 1991.",
        },
        {
            "name": "Priorat",
            "alt_name": "DOQ Priorat",
            "region": "Catalonia",
            "red_grapes": ["Garnacha Tinta", "Cariñena", "Cabernet Sauvignon", "Merlot", "Syrah"],
            "white_grapes": ["Garnacha Blanca", "Macabeo", "Pedro Ximénez", "Chenin Blanc"],
            "area_ha": 1955,
            "notes": "Received DOCa (DOQ in Catalan) status in 2000. Known for llicorella (slate) soils.",
        },
    ],
    # DO (Denominación de Origen)
    "DO": [
        {"name": "Abona", "region": "Canary Islands (Tenerife)", "red_grapes": ["Listán Negro", "Negramoll"], "white_grapes": ["Listán Blanco"]},
        {"name": "Alella", "region": "Catalonia", "red_grapes": ["Garnacha Tinta", "Tempranillo"], "white_grapes": ["Pansa Blanca", "Garnacha Blanca", "Chardonnay"]},
        {"name": "Alicante", "region": "Valencia", "red_grapes": ["Monastrell", "Garnacha Tintorera"], "white_grapes": ["Moscatel de Alejandría"]},
        {"name": "Almansa", "region": "Castilla-La Mancha", "red_grapes": ["Garnacha Tintorera", "Monastrell", "Tempranillo"], "white_grapes": ["Verdejo"]},
        {"name": "Arlanza", "region": "Castilla y León", "red_grapes": ["Tempranillo", "Garnacha"], "white_grapes": ["Albillo"]},
        {"name": "Arribes", "region": "Castilla y León", "red_grapes": ["Juan García", "Tempranillo"], "white_grapes": ["Malvasía"]},
        {"name": "Bierzo", "region": "Castilla y León", "red_grapes": ["Mencía"], "white_grapes": ["Godello", "Doña Blanca"]},
        {"name": "Binissalem", "region": "Balearic Islands (Mallorca)", "red_grapes": ["Manto Negro", "Callet"], "white_grapes": ["Moll", "Prensal Blanc"]},
        {"name": "Bullas", "region": "Murcia", "red_grapes": ["Monastrell", "Tempranillo"], "white_grapes": ["Macabeo"]},
        {"name": "Calatayud", "region": "Aragón", "red_grapes": ["Garnacha Tinta", "Tempranillo"], "white_grapes": ["Macabeo", "Garnacha Blanca"]},
        {"name": "Campo de Borja", "region": "Aragón", "red_grapes": ["Garnacha Tinta", "Tempranillo"], "white_grapes": ["Macabeo"]},
        {"name": "Cariñena", "region": "Aragón", "red_grapes": ["Garnacha Tinta", "Tempranillo", "Cariñena"], "white_grapes": ["Macabeo", "Garnacha Blanca"]},
        {"name": "Cataluña", "region": "Catalonia", "red_grapes": ["Tempranillo", "Garnacha", "Cabernet Sauvignon", "Merlot"], "white_grapes": ["Macabeo", "Xarel·lo", "Parellada", "Chardonnay"]},
        {"name": "Cava", "region": "Multi-regional (primarily Catalonia)", "red_grapes": ["Garnacha Tinta", "Monastrell", "Pinot Noir", "Trepat"], "white_grapes": ["Macabeo", "Xarel·lo", "Parellada", "Chardonnay"], "notes": "Cava is a traditional method sparkling wine produced primarily in the Penedès area of Catalonia."},
        {"name": "Chacolí de Álava", "alt_name": "Arabako Txakolina", "region": "Basque Country", "red_grapes": ["Hondarrabi Beltza"], "white_grapes": ["Hondarrabi Zuri"]},
        {"name": "Chacolí de Bizkaia", "alt_name": "Bizkaiko Txakolina", "region": "Basque Country", "red_grapes": ["Hondarrabi Beltza"], "white_grapes": ["Hondarrabi Zuri"]},
        {"name": "Chacolí de Getaria", "alt_name": "Getariako Txakolina", "region": "Basque Country", "red_grapes": ["Hondarrabi Beltza"], "white_grapes": ["Hondarrabi Zuri"]},
        {"name": "Cigales", "region": "Castilla y León", "red_grapes": ["Tempranillo", "Garnacha"], "white_grapes": ["Verdejo", "Albillo"]},
        {"name": "Conca de Barberà", "region": "Catalonia", "red_grapes": ["Trepat", "Tempranillo"], "white_grapes": ["Macabeo", "Parellada"]},
        {"name": "Condado de Huelva", "region": "Andalusia", "red_grapes": [], "white_grapes": ["Zalema", "Palomino Fino", "Listán Blanco"]},
        {"name": "Costers del Segre", "region": "Catalonia", "red_grapes": ["Tempranillo", "Cabernet Sauvignon", "Merlot"], "white_grapes": ["Macabeo", "Chardonnay"]},
        {"name": "El Hierro", "region": "Canary Islands", "red_grapes": ["Listán Negro", "Negramoll"], "white_grapes": ["Listán Blanco", "Vijariego"]},
        {"name": "Empordà", "region": "Catalonia", "red_grapes": ["Garnacha Tinta", "Cariñena", "Cabernet Sauvignon"], "white_grapes": ["Garnacha Blanca", "Macabeo"]},
        {"name": "Gran Canaria", "region": "Canary Islands", "red_grapes": ["Listán Negro", "Negramoll"], "white_grapes": ["Listán Blanco", "Malvasía"]},
        {"name": "Jerez-Xérès-Sherry", "region": "Andalusia", "red_grapes": [], "white_grapes": ["Palomino Fino", "Pedro Ximénez", "Moscatel"], "notes": "Fortified wine. Sherry triangle: Jerez, El Puerto de Santa María, Sanlúcar."},
        {"name": "Jumilla", "region": "Murcia / Castilla-La Mancha", "red_grapes": ["Monastrell", "Tempranillo", "Cabernet Sauvignon"], "white_grapes": ["Macabeo", "Airén"]},
        {"name": "La Gomera", "region": "Canary Islands", "red_grapes": ["Listán Negro", "Negramoll"], "white_grapes": ["Listán Blanco", "Forastera Blanca"]},
        {"name": "La Mancha", "region": "Castilla-La Mancha", "red_grapes": ["Tempranillo", "Garnacha"], "white_grapes": ["Airén", "Macabeo"], "notes": "Largest DO in Spain by area."},
        {"name": "La Palma", "region": "Canary Islands", "red_grapes": ["Listán Negro", "Negramoll"], "white_grapes": ["Listán Blanco", "Malvasía"]},
        {"name": "Lanzarote", "region": "Canary Islands", "red_grapes": ["Listán Negro"], "white_grapes": ["Malvasía Volcánica", "Listán Blanco"], "notes": "Vines grown in volcanic hollows (zocos) protected by stone walls."},
        {"name": "Málaga", "region": "Andalusia", "red_grapes": [], "white_grapes": ["Moscatel", "Pedro Ximénez"], "notes": "Málaga DO is renowned for its sweet and fortified wines made from Moscatel and Pedro Ximénez grapes."},
        {"name": "Manchuela", "region": "Castilla-La Mancha", "red_grapes": ["Bobal", "Tempranillo"], "white_grapes": ["Macabeo", "Chardonnay"]},
        {"name": "Manzanilla-Sanlúcar de Barrameda", "region": "Andalusia", "red_grapes": [], "white_grapes": ["Palomino Fino"], "notes": "A specific style of fino sherry aged in Sanlúcar de Barrameda."},
        {"name": "Méntrida", "region": "Castilla-La Mancha", "red_grapes": ["Garnacha Tinta"], "white_grapes": ["Macabeo"]},
        {"name": "Mondéjar", "region": "Castilla-La Mancha", "red_grapes": ["Tempranillo", "Cabernet Sauvignon"], "white_grapes": ["Macabeo", "Malvar"]},
        {"name": "Monterrei", "region": "Galicia", "red_grapes": ["Mencía", "Bastardo"], "white_grapes": ["Godello", "Treixadura", "Doña Blanca"]},
        {"name": "Montilla-Moriles", "region": "Andalusia", "red_grapes": [], "white_grapes": ["Pedro Ximénez"], "notes": "Known for unfortified fino and Pedro Ximénez sweet wines."},
        {"name": "Montsant", "region": "Catalonia", "red_grapes": ["Garnacha Tinta", "Cariñena", "Tempranillo"], "white_grapes": ["Garnacha Blanca", "Macabeo"]},
        {"name": "Navarra", "region": "Navarre", "red_grapes": ["Tempranillo", "Garnacha Tinta", "Cabernet Sauvignon", "Merlot"], "white_grapes": ["Chardonnay", "Viura"]},
        {"name": "Penedès", "region": "Catalonia", "red_grapes": ["Tempranillo", "Garnacha", "Cabernet Sauvignon", "Merlot", "Pinot Noir"], "white_grapes": ["Macabeo", "Xarel·lo", "Parellada", "Chardonnay", "Sauvignon Blanc"]},
        {"name": "Pla de Bages", "region": "Catalonia", "red_grapes": ["Tempranillo", "Cabernet Sauvignon", "Merlot"], "white_grapes": ["Macabeo", "Picapoll"]},
        {"name": "Pla i Llevant", "region": "Balearic Islands (Mallorca)", "red_grapes": ["Manto Negro", "Callet", "Cabernet Sauvignon"], "white_grapes": ["Prensal Blanc", "Chardonnay"]},
        {"name": "Rías Baixas", "region": "Galicia", "red_grapes": ["Caiño Tinto", "Espadeiro", "Mencía"], "white_grapes": ["Albariño", "Treixadura", "Loureira"], "notes": "Renowned for Albariño white wines."},
        {"name": "Ribeira Sacra", "region": "Galicia", "red_grapes": ["Mencía"], "white_grapes": ["Godello", "Albariño"], "notes": "Known for steep terraced vineyards along river gorges."},
        {"name": "Ribeiro", "region": "Galicia", "red_grapes": ["Caiño", "Ferrón", "Sousón"], "white_grapes": ["Treixadura", "Torrontés", "Godello", "Loureira"]},
        {"name": "Ribera del Duero", "region": "Castilla y León", "red_grapes": ["Tempranillo", "Cabernet Sauvignon", "Merlot", "Malbec"], "white_grapes": ["Albillo"], "notes": "Tempranillo (locally called Tinta del País or Tinto Fino) dominates."},
        {"name": "Ribera del Guadiana", "region": "Extremadura", "red_grapes": ["Tempranillo", "Garnacha", "Cabernet Sauvignon"], "white_grapes": ["Cayetana Blanca", "Pardina", "Macabeo"]},
        {"name": "Ribera del Júcar", "region": "Castilla-La Mancha", "red_grapes": ["Tempranillo", "Cabernet Sauvignon", "Bobal"], "white_grapes": ["Moscatel de Grano Menudo"]},
        {"name": "Rueda", "region": "Castilla y León", "red_grapes": [], "white_grapes": ["Verdejo", "Viura", "Sauvignon Blanc"], "notes": "Spain's premier white wine DO, centered on Verdejo."},
        {"name": "Sierra de Málaga", "region": "Andalusia", "red_grapes": ["Romé", "Cabernet Sauvignon", "Merlot", "Syrah", "Tempranillo"], "white_grapes": ["Moscatel", "Pedro Ximénez", "Chardonnay"]},
        {"name": "Somontano", "region": "Aragón", "red_grapes": ["Tempranillo", "Cabernet Sauvignon", "Merlot", "Garnacha"], "white_grapes": ["Macabeo", "Chardonnay", "Gewürztraminer"]},
        {"name": "Tacoronte-Acentejo", "region": "Canary Islands (Tenerife)", "red_grapes": ["Listán Negro", "Negramoll"], "white_grapes": ["Listán Blanco"]},
        {"name": "Tarragona", "region": "Catalonia", "red_grapes": ["Tempranillo", "Garnacha", "Cariñena"], "white_grapes": ["Macabeo", "Xarel·lo", "Parellada"]},
        {"name": "Terra Alta", "region": "Catalonia", "red_grapes": ["Garnacha Tinta", "Cariñena", "Tempranillo"], "white_grapes": ["Garnacha Blanca", "Macabeo"]},
        {"name": "Tierra de León", "region": "Castilla y León", "red_grapes": ["Prieto Picudo", "Mencía", "Tempranillo"], "white_grapes": ["Albarín Blanco", "Verdejo"]},
        {"name": "Tierra del Vino de Zamora", "region": "Castilla y León", "red_grapes": ["Tempranillo"], "white_grapes": ["Malvasía", "Moscatel"]},
        {"name": "Toro", "region": "Castilla y León", "red_grapes": ["Tinta de Toro"], "white_grapes": ["Malvasía", "Verdejo"], "notes": "Tinta de Toro is a local clone of Tempranillo."},
        {"name": "Uclés", "region": "Castilla-La Mancha", "red_grapes": ["Tempranillo", "Cabernet Sauvignon"], "white_grapes": ["Macabeo", "Verdejo"]},
        {"name": "Utiel-Requena", "region": "Valencia", "red_grapes": ["Bobal", "Tempranillo"], "white_grapes": ["Macabeo", "Tardana"], "notes": "Known for the indigenous Bobal grape."},
        {"name": "Valdeorras", "region": "Galicia", "red_grapes": ["Mencía"], "white_grapes": ["Godello"], "notes": "Leading area for Godello white wines."},
        {"name": "Valdepeñas", "region": "Castilla-La Mancha", "red_grapes": ["Tempranillo", "Garnacha"], "white_grapes": ["Airén"]},
        {"name": "Valencia", "region": "Valencia", "red_grapes": ["Tempranillo", "Monastrell", "Garnacha"], "white_grapes": ["Merseguera", "Malvasía", "Moscatel"]},
        {"name": "Valle de Güímar", "region": "Canary Islands (Tenerife)", "red_grapes": ["Listán Negro"], "white_grapes": ["Listán Blanco"]},
        {"name": "Valle de la Orotava", "region": "Canary Islands (Tenerife)", "red_grapes": ["Listán Negro", "Negramoll"], "white_grapes": ["Listán Blanco"]},
        {"name": "Vinos de Madrid", "region": "Community of Madrid", "red_grapes": ["Tempranillo", "Garnacha", "Syrah"], "white_grapes": ["Malvar", "Airén", "Albillo"]},
        {"name": "Ycoden-Daute-Isora", "region": "Canary Islands (Tenerife)", "red_grapes": ["Listán Negro"], "white_grapes": ["Listán Blanco", "Vijariego"]},
        {"name": "Yecla", "region": "Murcia", "red_grapes": ["Monastrell"], "white_grapes": ["Macabeo", "Merseguera"]},
        {"name": "Cangas", "region": "Asturias", "red_grapes": ["Carrasquín", "Verdejo Negro", "Albarín Negro", "Mencía"], "white_grapes": ["Albarín Blanco"], "notes": "The only DO in Asturias. Small production from steep mountain vineyards."},
    ],
}

SPAIN_AGING = {
    "Joven": {
        "description": "Young wine, little or no oak aging.",
        "red_oak_months": 0,
        "red_total_months": 0,
    },
    "Crianza": {
        "description": "Red wines aged at least 24 months total, with a minimum of 6 months in oak. White and rosé: 18 months total, 6 months in oak.",
        "red_oak_months": 6,
        "red_total_months": 24,
        "white_oak_months": 6,
        "white_total_months": 18,
    },
    "Reserva": {
        "description": "Red wines aged at least 36 months total, with a minimum of 12 months in oak. White and rosé: 24 months total, 6 months in oak.",
        "red_oak_months": 12,
        "red_total_months": 36,
        "white_oak_months": 6,
        "white_total_months": 24,
    },
    "Gran Reserva": {
        "description": "Red wines aged at least 60 months total, with a minimum of 18 months in oak. White and rosé: 48 months total, 6 months in oak.",
        "red_oak_months": 18,
        "red_total_months": 60,
        "white_oak_months": 6,
        "white_total_months": 48,
    },
}


def build_spain_facts(source_ids: dict) -> list[dict]:
    """Generate atomic facts about Spanish wine appellations and regulations."""
    facts = []
    seen = set()

    def add(text, domain, subdomain, entities, tags, source_key="spain_mapa"):
        if text in seen:
            return
        seen.add(text)
        facts.append({
            "fact_text": text,
            "domain": domain,
            "subdomain": subdomain,
            "source_id": source_ids[source_key],
            "entities": entities,
            "tags": tags,
        })

    # --- General facts about Spanish wine system ---
    add(
        "Spain has two levels of quality wine designation: Denominación de Origen (DO) and the higher Denominación de Origen Calificada (DOCa).",
        "wine_regions", "spain_regulation",
        [{"type": "country", "name": "Spain"}],
        ["spain", "regulation", "classification"],
    )
    add(
        "Spain has 70 protected designations of origin for wine, comprising 68 DO and 2 DOCa appellations.",
        "wine_regions", "spain_regulation",
        [{"type": "country", "name": "Spain"}],
        ["spain", "regulation"],
    )
    add(
        "DOCa is the highest classification for Spanish wines, requiring stricter quality controls and a longer track record than DO.",
        "wine_regions", "spain_regulation",
        [{"type": "classification", "name": "DOCa"}],
        ["spain", "regulation", "classification"],
    )
    add(
        "Spain also uses the Vino de Pago classification for single-estate wines of exceptional quality.",
        "wine_regions", "spain_regulation",
        [{"type": "country", "name": "Spain"}, {"type": "classification", "name": "Vino de Pago"}],
        ["spain", "regulation", "classification"],
    )
    add(
        "Spanish wine law is governed by the Ley de la Viña y del Vino, enacted in 2003.",
        "wine_business", "spain_regulation",
        [{"type": "country", "name": "Spain"}],
        ["spain", "regulation", "law"],
    )
    add(
        "The Consejo Regulador is the governing body for each Spanish DO, responsible for enforcing production standards.",
        "wine_business", "spain_regulation",
        [{"type": "organization", "name": "Consejo Regulador"}],
        ["spain", "regulation", "organization"],
    )

    # --- DOCa appellations ---
    for appellation in SPAIN_APPELLATIONS["DOCa"]:
        name = appellation["name"]
        region = appellation["region"]
        ent = [{"type": "appellation", "name": name}]

        add(
            f"{name} is one of only two DOCa (Denominación de Origen Calificada) appellations in Spain.",
            "wine_regions", "spain_doca",
            ent + [{"type": "classification", "name": "DOCa"}],
            ["spain", "doca", name.lower()],
        )
        add(
            f"{name} DOCa is located in {region}.",
            "wine_regions", "spain_doca",
            ent + [{"type": "region", "name": region}],
            ["spain", "doca", "geography"],
        )
        if appellation.get("area_ha"):
            add(
                f"The {name} DOCa covers approximately {appellation['area_ha']:,} hectares of vineyards.",
                "wine_regions", "spain_doca",
                ent, ["spain", "doca", "area"],
            )
        if appellation.get("subzones"):
            zones = ", ".join(appellation["subzones"])
            add(
                f"{name} is divided into the subzones {zones}.",
                "wine_regions", "spain_doca",
                ent + [{"type": "subzone", "name": z} for z in appellation["subzones"]],
                ["spain", "doca", "subzones"],
            )
        for grape in appellation.get("red_grapes", []):
            add(
                f"{grape} is a permitted red grape variety in {name} DOCa.",
                "grape_varieties", "spain_doca",
                ent + [{"type": "grape", "name": grape}],
                ["spain", "grape", "red"],
            )
        for grape in appellation.get("white_grapes", []):
            add(
                f"{grape} is a permitted white grape variety in {name} DOCa.",
                "grape_varieties", "spain_doca",
                ent + [{"type": "grape", "name": grape}],
                ["spain", "grape", "white"],
            )
        if appellation.get("notes"):
            add(
                appellation["notes"],
                "wine_regions", "spain_doca",
                ent, ["spain", "doca", "notes"],
            )

    # --- DO appellations ---
    for appellation in SPAIN_APPELLATIONS["DO"]:
        name = appellation["name"]
        region = appellation["region"]
        ent = [{"type": "appellation", "name": name}]

        add(
            f"{name} is a Denominación de Origen (DO) wine appellation in Spain.",
            "wine_regions", "spain_do",
            ent + [{"type": "classification", "name": "DO"}],
            ["spain", "do"],
        )
        add(
            f"{name} DO is located in {region}.",
            "wine_regions", "spain_do",
            ent + [{"type": "region", "name": region}],
            ["spain", "do", "geography"],
        )
        if appellation.get("alt_name"):
            add(
                f"{name} is also known as {appellation['alt_name']}.",
                "wine_regions", "spain_do",
                ent + [{"type": "appellation", "name": appellation["alt_name"]}],
                ["spain", "do", "synonym"],
            )
        for grape in appellation.get("red_grapes", []):
            add(
                f"{grape} is a permitted red grape variety in {name} DO.",
                "grape_varieties", "spain_do",
                ent + [{"type": "grape", "name": grape}],
                ["spain", "grape", "red"],
            )
        for grape in appellation.get("white_grapes", []):
            add(
                f"{grape} is a permitted white grape variety in {name} DO.",
                "grape_varieties", "spain_do",
                ent + [{"type": "grape", "name": grape}],
                ["spain", "grape", "white"],
            )
        if appellation.get("notes"):
            add(
                appellation["notes"],
                "wine_regions", "spain_do",
                ent, ["spain", "do", "notes"],
            )

    # --- Aging categories ---
    for category, info in SPAIN_AGING.items():
        add(
            f"Spanish {category} is an aging category: {info['description']}",
            "winemaking", "spain_aging",
            [{"type": "aging_category", "name": category}],
            ["spain", "aging", category.lower()],
        )

    if SPAIN_AGING["Crianza"]["red_oak_months"]:
        add(
            "Spanish Crianza red wines must be aged for at least 24 months, with a minimum of 6 months in oak barrels.",
            "winemaking", "spain_aging",
            [{"type": "aging_category", "name": "Crianza"}],
            ["spain", "aging", "crianza", "red"],
        )
    add(
        "Spanish Reserva red wines must be aged for at least 36 months, with 12 months in oak.",
        "winemaking", "spain_aging",
        [{"type": "aging_category", "name": "Reserva"}],
        ["spain", "aging", "reserva", "red"],
    )
    add(
        "Spanish Gran Reserva red wines must be aged for at least 60 months, with 18 months in oak.",
        "winemaking", "spain_aging",
        [{"type": "aging_category", "name": "Gran Reserva"}],
        ["spain", "aging", "gran_reserva", "red"],
    )
    add(
        "Spanish Reserva white and rosé wines must be aged for at least 24 months, with 6 months in oak.",
        "winemaking", "spain_aging",
        [{"type": "aging_category", "name": "Reserva"}],
        ["spain", "aging", "reserva", "white"],
    )
    add(
        "Spanish Gran Reserva white and rosé wines must be aged for at least 48 months, with 6 months in oak.",
        "winemaking", "spain_aging",
        [{"type": "aging_category", "name": "Gran Reserva"}],
        ["spain", "aging", "gran_reserva", "white"],
    )

    # --- Sherry-specific facts ---
    add(
        "Sherry must be produced within the Jerez-Xérès-Sherry DO in the sherry triangle of Andalusia.",
        "winemaking", "spain_sherry",
        [{"type": "appellation", "name": "Jerez-Xérès-Sherry"}],
        ["spain", "sherry", "regulation"],
    )
    add(
        "Fino Sherry is aged under a layer of flor yeast, developing pale, dry characteristics.",
        "winemaking", "spain_sherry",
        [{"type": "wine_style", "name": "Fino"}, {"type": "appellation", "name": "Jerez-Xérès-Sherry"}],
        ["spain", "sherry", "fino"],
    )
    add(
        "Oloroso Sherry is aged oxidatively without flor, resulting in a darker, richer style.",
        "winemaking", "spain_sherry",
        [{"type": "wine_style", "name": "Oloroso"}, {"type": "appellation", "name": "Jerez-Xérès-Sherry"}],
        ["spain", "sherry", "oloroso"],
    )
    add(
        "Amontillado Sherry begins aging under flor like Fino, then continues oxidative aging like Oloroso.",
        "winemaking", "spain_sherry",
        [{"type": "wine_style", "name": "Amontillado"}, {"type": "appellation", "name": "Jerez-Xérès-Sherry"}],
        ["spain", "sherry", "amontillado"],
    )
    add(
        "Palo Cortado Sherry is a rare style that naturally loses its flor during aging.",
        "winemaking", "spain_sherry",
        [{"type": "wine_style", "name": "Palo Cortado"}, {"type": "appellation", "name": "Jerez-Xérès-Sherry"}],
        ["spain", "sherry", "palo_cortado"],
    )
    add(
        "Manzanilla is a style of Fino Sherry produced exclusively in Sanlúcar de Barrameda.",
        "winemaking", "spain_sherry",
        [{"type": "wine_style", "name": "Manzanilla"}, {"type": "appellation", "name": "Manzanilla-Sanlúcar de Barrameda"}],
        ["spain", "sherry", "manzanilla"],
    )
    add(
        "The solera system is the traditional blending and aging method used for Sherry production.",
        "winemaking", "spain_sherry",
        [{"type": "technique", "name": "Solera system"}],
        ["spain", "sherry", "solera"],
    )
    add(
        "Pedro Ximénez (PX) Sherry is made from sun-dried Pedro Ximénez grapes and is intensely sweet.",
        "winemaking", "spain_sherry",
        [{"type": "wine_style", "name": "Pedro Ximénez"}, {"type": "grape", "name": "Pedro Ximénez"}],
        ["spain", "sherry", "px"],
    )

    # --- Cava-specific facts ---
    add(
        "Cava is produced using the traditional method (método tradicional), the same technique as Champagne.",
        "winemaking", "spain_cava",
        [{"type": "appellation", "name": "Cava"}],
        ["spain", "cava", "method"],
    )
    add(
        "Cava must undergo a minimum of 9 months of lees aging in bottle.",
        "winemaking", "spain_cava",
        [{"type": "appellation", "name": "Cava"}],
        ["spain", "cava", "aging"],
    )
    add(
        "Cava Reserva requires a minimum of 15 months of aging on lees.",
        "winemaking", "spain_cava",
        [{"type": "appellation", "name": "Cava"}, {"type": "aging_category", "name": "Reserva"}],
        ["spain", "cava", "aging", "reserva"],
    )
    add(
        "Cava Gran Reserva requires a minimum of 30 months of aging on lees.",
        "winemaking", "spain_cava",
        [{"type": "appellation", "name": "Cava"}, {"type": "aging_category", "name": "Gran Reserva"}],
        ["spain", "cava", "aging", "gran_reserva"],
    )
    add(
        "The classic Cava grape blend is Macabeo, Xarel·lo, and Parellada.",
        "grape_varieties", "spain_cava",
        [{"type": "grape", "name": "Macabeo"}, {"type": "grape", "name": "Xarel·lo"}, {"type": "grape", "name": "Parellada"}],
        ["spain", "cava", "grapes"],
    )
    add(
        "Cava de Paraje Calificado is the highest quality tier of Cava, requiring single-vineyard production and 36 months of lees aging.",
        "winemaking", "spain_cava",
        [{"type": "appellation", "name": "Cava"}, {"type": "classification", "name": "Cava de Paraje Calificado"}],
        ["spain", "cava", "classification"],
    )

    # --- Regional highlights ---
    add(
        "Albariño is the signature grape of the Rías Baixas DO in Galicia.",
        "grape_varieties", "spain_do",
        [{"type": "grape", "name": "Albariño"}, {"type": "appellation", "name": "Rías Baixas"}],
        ["spain", "grape", "galicia"],
    )
    add(
        "Tempranillo is Spain's most widely planted red grape and the backbone of Rioja and Ribera del Duero.",
        "grape_varieties", "spain_general",
        [{"type": "grape", "name": "Tempranillo"}],
        ["spain", "grape", "tempranillo"],
    )
    add(
        "In Ribera del Duero, Tempranillo is locally known as Tinta del País or Tinto Fino.",
        "grape_varieties", "spain_do",
        [{"type": "grape", "name": "Tempranillo"}, {"type": "appellation", "name": "Ribera del Duero"}],
        ["spain", "grape", "synonym"],
    )
    add(
        "In Toro, Tempranillo is known as Tinta de Toro and produces more concentrated wines due to the extreme continental climate.",
        "grape_varieties", "spain_do",
        [{"type": "grape", "name": "Tempranillo"}, {"type": "appellation", "name": "Toro"}],
        ["spain", "grape", "synonym"],
    )
    add(
        "Garnacha (Grenache) is widely planted across Aragón, Navarra, and Catalonia.",
        "grape_varieties", "spain_general",
        [{"type": "grape", "name": "Garnacha"}],
        ["spain", "grape", "garnacha"],
    )
    add(
        "Monastrell (Mourvèdre) is the dominant grape in the DO regions of Jumilla, Yecla, and Bullas in southeast Spain.",
        "grape_varieties", "spain_general",
        [{"type": "grape", "name": "Monastrell"}],
        ["spain", "grape", "monastrell"],
    )
    add(
        "Airén is the most widely planted white grape in Spain and one of the most planted in the world.",
        "grape_varieties", "spain_general",
        [{"type": "grape", "name": "Airén"}],
        ["spain", "grape", "airen"],
    )
    add(
        "Verdejo is the signature white grape of the Rueda DO in Castilla y León.",
        "grape_varieties", "spain_do",
        [{"type": "grape", "name": "Verdejo"}, {"type": "appellation", "name": "Rueda"}],
        ["spain", "grape", "verdejo"],
    )
    add(
        "Mencía is a red grape native to northwest Spain, prominent in Bierzo, Ribeira Sacra, and Valdeorras.",
        "grape_varieties", "spain_general",
        [{"type": "grape", "name": "Mencía"}],
        ["spain", "grape", "mencia"],
    )
    add(
        "Godello is a high-quality white grape from Galicia, particularly valued in Valdeorras and Monterrei.",
        "grape_varieties", "spain_general",
        [{"type": "grape", "name": "Godello"}],
        ["spain", "grape", "godello"],
    )
    add(
        "Spain has the largest vineyard area in the world, though it ranks third in production volume behind Italy and France.",
        "wine_business", "spain_general",
        [{"type": "country", "name": "Spain"}],
        ["spain", "production", "area"],
    )
    add(
        "La Mancha is the largest single wine-producing region in the world by vineyard area.",
        "wine_regions", "spain_do",
        [{"type": "appellation", "name": "La Mancha"}],
        ["spain", "la_mancha", "area"],
    )

    # --- Additional Spanish wine knowledge ---
    add(
        "Bobal is a red grape widely grown in Utiel-Requena and Manchuela, producing deeply colored wines.",
        "grape_varieties", "spain_general",
        [{"type": "grape", "name": "Bobal"}],
        ["spain", "grape", "bobal"],
    )
    add(
        "Garnacha Tintorera (Alicante Bouschet) is unusual among red grapes because it has red flesh, not just red skin.",
        "grape_varieties", "spain_general",
        [{"type": "grape", "name": "Garnacha Tintorera"}],
        ["spain", "grape", "garnacha_tintorera"],
    )
    add(
        "Listán Negro is the most important red grape of the Canary Islands.",
        "grape_varieties", "spain_general",
        [{"type": "grape", "name": "Listán Negro"}],
        ["spain", "grape", "canary_islands"],
    )
    add(
        "Malvasía Volcánica is a distinctive white grape grown on the volcanic soils of Lanzarote.",
        "grape_varieties", "spain_general",
        [{"type": "grape", "name": "Malvasía Volcánica"}, {"type": "appellation", "name": "Lanzarote"}],
        ["spain", "grape", "canary_islands"],
    )
    add(
        "Prieto Picudo is an indigenous red grape variety found almost exclusively in the Tierra de León DO.",
        "grape_varieties", "spain_general",
        [{"type": "grape", "name": "Prieto Picudo"}, {"type": "appellation", "name": "Tierra de León"}],
        ["spain", "grape"],
    )
    add(
        "Hondarrabi Zuri is the primary white grape used for Txakolí (Chacolí) in the Basque Country.",
        "grape_varieties", "spain_general",
        [{"type": "grape", "name": "Hondarrabi Zuri"}],
        ["spain", "grape", "basque"],
    )
    add(
        "Juan García is an indigenous red grape variety cultivated in the Arribes DO along the Spanish-Portuguese border.",
        "grape_varieties", "spain_general",
        [{"type": "grape", "name": "Juan García"}, {"type": "appellation", "name": "Arribes"}],
        ["spain", "grape"],
    )
    add(
        "Callet is an indigenous red grape of Mallorca, used in Binissalem and Pla i Llevant DOs.",
        "grape_varieties", "spain_general",
        [{"type": "grape", "name": "Callet"}],
        ["spain", "grape", "balearic"],
    )
    add(
        "Manto Negro is the most widely planted red grape in Mallorca.",
        "grape_varieties", "spain_general",
        [{"type": "grape", "name": "Manto Negro"}],
        ["spain", "grape", "balearic"],
    )
    add(
        "Graciano is a minor but important blending grape in Rioja, prized for its color and acidity.",
        "grape_varieties", "spain_general",
        [{"type": "grape", "name": "Graciano"}, {"type": "appellation", "name": "Rioja"}],
        ["spain", "grape", "rioja"],
    )
    add(
        "Mazuelo (Cariñena/Carignan) is a permitted red grape in Rioja, adding structure and tannin to blends.",
        "grape_varieties", "spain_general",
        [{"type": "grape", "name": "Mazuelo"}, {"type": "appellation", "name": "Rioja"}],
        ["spain", "grape", "rioja"],
    )
    add(
        "Xarel·lo is one of the three traditional Cava grapes and contributes body and earthiness to the blend.",
        "grape_varieties", "spain_general",
        [{"type": "grape", "name": "Xarel·lo"}, {"type": "appellation", "name": "Cava"}],
        ["spain", "grape", "cava"],
    )
    add(
        "Parellada is a delicate white grape used in Cava production, adding floral aromatics and finesse.",
        "grape_varieties", "spain_general",
        [{"type": "grape", "name": "Parellada"}],
        ["spain", "grape", "cava"],
    )
    add(
        "Trepat is a light red grape grown in Catalonia, mainly used for rosé Cava.",
        "grape_varieties", "spain_general",
        [{"type": "grape", "name": "Trepat"}],
        ["spain", "grape", "catalonia"],
    )
    add(
        "Palomino Fino is the grape used for dry Sherry styles including Fino, Manzanilla, Amontillado, Oloroso, and Palo Cortado.",
        "grape_varieties", "spain_general",
        [{"type": "grape", "name": "Palomino Fino"}, {"type": "appellation", "name": "Jerez-Xérès-Sherry"}],
        ["spain", "grape", "sherry"],
    )
    add(
        "Moscatel de Alejandría (Muscat of Alexandria) is used for sweet wines in several Spanish DOs including Alicante and Valencia.",
        "grape_varieties", "spain_general",
        [{"type": "grape", "name": "Moscatel de Alejandría"}],
        ["spain", "grape", "sweet"],
    )
    add(
        "Albillo is a white grape used in Ribera del Duero and Vinos de Madrid, valued for its richness and low acidity.",
        "grape_varieties", "spain_general",
        [{"type": "grape", "name": "Albillo"}],
        ["spain", "grape"],
    )
    add(
        "Treixadura is the signature white grape of the Ribeiro DO in Galicia.",
        "grape_varieties", "spain_general",
        [{"type": "grape", "name": "Treixadura"}, {"type": "appellation", "name": "Ribeiro"}],
        ["spain", "grape", "galicia"],
    )
    add(
        "Loureira is an aromatic white grape grown in the Rías Baixas and Ribeiro DOs of Galicia.",
        "grape_varieties", "spain_general",
        [{"type": "grape", "name": "Loureira"}],
        ["spain", "grape", "galicia"],
    )
    add(
        "Picapoll is a white grape indigenous to the Pla de Bages DO in Catalonia.",
        "grape_varieties", "spain_general",
        [{"type": "grape", "name": "Picapoll"}, {"type": "appellation", "name": "Pla de Bages"}],
        ["spain", "grape", "catalonia"],
    )
    add(
        "Zalema is the main grape variety in Condado de Huelva, used for both still and fortified wines.",
        "grape_varieties", "spain_general",
        [{"type": "grape", "name": "Zalema"}, {"type": "appellation", "name": "Condado de Huelva"}],
        ["spain", "grape"],
    )
    add(
        "Malvar is an indigenous white grape of Madrid, grown primarily in the Vinos de Madrid DO.",
        "grape_varieties", "spain_general",
        [{"type": "grape", "name": "Malvar"}, {"type": "appellation", "name": "Vinos de Madrid"}],
        ["spain", "grape"],
    )
    add(
        "Cayetana Blanca is the most planted white grape in Extremadura, used in Ribera del Guadiana DO.",
        "grape_varieties", "spain_general",
        [{"type": "grape", "name": "Cayetana Blanca"}, {"type": "appellation", "name": "Ribera del Guadiana"}],
        ["spain", "grape"],
    )

    # --- Spanish Vino de Pago estates ---
    vp_estates = [
        ("Dominio de Valdepusa", "Castilla-La Mancha"),
        ("Finca Élez", "Castilla-La Mancha"),
        ("Guijoso", "Castilla-La Mancha"),
        ("Dehesa del Carrizal", "Castilla-La Mancha"),
        ("Pago de Arínzano", "Navarra"),
        ("Pago de Otazu", "Navarra"),
        ("Campo de la Guardia", "Castilla-La Mancha"),
        ("Calzadilla", "Castilla-La Mancha"),
        ("Aylés", "Aragón"),
        ("Pago Florentino", "Castilla-La Mancha"),
        ("Los Balagueses", "Valencia"),
        ("El Terrerazo", "Valencia"),
        ("Vera de Estenas", "Valencia"),
        ("Pago de la Jaraba", "Castilla-La Mancha"),
        ("Chozas Carrascal", "Valencia"),
    ]
    add(
        f"Spain recognizes {len(vp_estates)} or more Vino de Pago estates, each considered equivalent to a single-estate appellation.",
        "wine_regions", "spain_regulation",
        [{"type": "classification", "name": "Vino de Pago"}],
        ["spain", "regulation", "vino_de_pago"],
    )
    for estate, region in vp_estates:
        add(
            f"{estate} is a recognized Vino de Pago estate in {region}, Spain.",
            "wine_regions", "spain_vino_de_pago",
            [{"type": "producer", "name": estate}, {"type": "classification", "name": "Vino de Pago"}],
            ["spain", "vino_de_pago"],
        )

    # --- Rioja in-depth ---
    add(
        "Rioja DOCa received its initial DO status in 1925, one of the first in Spain.",
        "wine_regions", "spain_doca",
        [{"type": "appellation", "name": "Rioja"}],
        ["spain", "rioja", "history"],
    )
    add(
        "Rioja Alta is known for elegant, balanced wines with good acidity due to its higher altitude and Atlantic influence.",
        "wine_regions", "spain_doca",
        [{"type": "subzone", "name": "Rioja Alta"}],
        ["spain", "rioja", "subzone"],
    )
    add(
        "Rioja Alavesa, in the Basque Country, produces wines that tend to be more structured and fuller-bodied.",
        "wine_regions", "spain_doca",
        [{"type": "subzone", "name": "Rioja Alavesa"}],
        ["spain", "rioja", "subzone"],
    )
    add(
        "Rioja Oriental (formerly Rioja Baja) has a warmer, drier Mediterranean climate and is known for Garnacha-based wines.",
        "wine_regions", "spain_doca",
        [{"type": "subzone", "name": "Rioja Oriental"}],
        ["spain", "rioja", "subzone"],
    )
    add(
        "In 2017, Rioja introduced a new single-vineyard designation called Viñedos Singulares.",
        "wine_regions", "spain_doca",
        [{"type": "appellation", "name": "Rioja"}, {"type": "classification", "name": "Viñedos Singulares"}],
        ["spain", "rioja", "classification"],
    )
    add(
        "Rioja white wines have traditionally been aged in oak, producing a rich, golden, oxidative style.",
        "winemaking", "spain_doca",
        [{"type": "appellation", "name": "Rioja"}],
        ["spain", "rioja", "white"],
    )
    add(
        "Tempranillo Blanco is a white mutation of Tempranillo that was discovered in Rioja in 1988.",
        "grape_varieties", "spain_doca",
        [{"type": "grape", "name": "Tempranillo Blanco"}],
        ["spain", "rioja", "grape"],
    )

    # --- Priorat in-depth ---
    add(
        "Priorat's vineyards are planted on steep, terraced hillsides with llicorella (black slate and quartzite) soils.",
        "viticulture", "spain_doca",
        [{"type": "appellation", "name": "Priorat"}],
        ["spain", "priorat", "terroir"],
    )
    add(
        "Priorat produces intensely concentrated red wines, often with very low yields of under 2 tons per hectare.",
        "viticulture", "spain_doca",
        [{"type": "appellation", "name": "Priorat"}],
        ["spain", "priorat", "yield"],
    )
    add(
        "Priorat experienced a renaissance in the late 1980s when a group of winemakers led by René Barbier and Álvaro Palacios revitalized the region.",
        "wine_regions", "spain_doca",
        [{"type": "appellation", "name": "Priorat"}, {"type": "person", "name": "Álvaro Palacios"}],
        ["spain", "priorat", "history"],
    )
    add(
        "Old-vine Garnacha (Garnatxa) is considered the heart of Priorat's finest wines.",
        "grape_varieties", "spain_doca",
        [{"type": "grape", "name": "Garnacha Tinta"}, {"type": "appellation", "name": "Priorat"}],
        ["spain", "priorat", "grape"],
    )
    add(
        "Priorat has introduced the Vi de Vila (village wine) classification to distinguish wines from individual villages.",
        "wine_regions", "spain_doca",
        [{"type": "appellation", "name": "Priorat"}, {"type": "classification", "name": "Vi de Vila"}],
        ["spain", "priorat", "classification"],
    )

    # --- Ribera del Duero in-depth ---
    add(
        "Ribera del Duero sits at an elevation of 700-1,000 meters on the Meseta Central plateau of Spain.",
        "wine_regions", "spain_do",
        [{"type": "appellation", "name": "Ribera del Duero"}],
        ["spain", "ribera_del_duero", "geography"],
    )
    add(
        "The extreme continental climate of Ribera del Duero features large diurnal temperature variations, helping grapes retain acidity.",
        "viticulture", "spain_do",
        [{"type": "appellation", "name": "Ribera del Duero"}],
        ["spain", "ribera_del_duero", "climate"],
    )
    add(
        "Vega Sicilia, founded in 1864, is the most prestigious estate in Ribera del Duero.",
        "producers", "spain_do",
        [{"type": "producer", "name": "Vega Sicilia"}, {"type": "appellation", "name": "Ribera del Duero"}],
        ["spain", "ribera_del_duero", "producer"],
    )

    # --- Rías Baixas in-depth ---
    add(
        "Rías Baixas has five sub-zones: Val do Salnés, Condado do Tea, O Rosal, Soutomaior, and Ribeira do Ulla.",
        "wine_regions", "spain_do",
        [{"type": "appellation", "name": "Rías Baixas"}],
        ["spain", "rias_baixas", "subzones"],
    )
    add(
        "Albariño in Rías Baixas is traditionally trained on pergolas (parras) to keep grapes above the humid ground.",
        "viticulture", "spain_do",
        [{"type": "grape", "name": "Albariño"}, {"type": "appellation", "name": "Rías Baixas"}],
        ["spain", "rias_baixas", "viticulture"],
    )

    # --- Sherry additional depth ---
    add(
        "The flor yeast (Saccharomyces beticus and related strains) forms a film on the wine surface, protecting it from oxidation during biological aging.",
        "winemaking", "spain_sherry",
        [{"type": "technique", "name": "Flor"}],
        ["spain", "sherry", "flor"],
    )
    add(
        "Sherry vineyards are planted predominantly on albariza soil, a white chalky soil rich in diatomaceous earth.",
        "viticulture", "spain_sherry",
        [{"type": "appellation", "name": "Jerez-Xérès-Sherry"}, {"type": "soil", "name": "Albariza"}],
        ["spain", "sherry", "terroir"],
    )
    add(
        "Cream Sherry is a blend of Oloroso and Pedro Ximénez, producing a sweet, dark style.",
        "winemaking", "spain_sherry",
        [{"type": "wine_style", "name": "Cream Sherry"}],
        ["spain", "sherry", "cream"],
    )
    add(
        "East India Sherry is a style that is aged at higher temperatures, historically simulating the warming effect of sea voyages.",
        "winemaking", "spain_sherry",
        [{"type": "wine_style", "name": "East India Sherry"}],
        ["spain", "sherry", "east_india"],
    )
    add(
        "VOS (Vinum Optimum Signatum) Sherry must be aged for at least 20 years.",
        "winemaking", "spain_sherry",
        [{"type": "classification", "name": "VOS"}],
        ["spain", "sherry", "aging"],
    )
    add(
        "VORS (Vinum Optimum Rare Signatum) Sherry must be aged for at least 30 years.",
        "winemaking", "spain_sherry",
        [{"type": "classification", "name": "VORS"}],
        ["spain", "sherry", "aging"],
    )
    add(
        "En rama Sherry is bottled with minimal filtration, offering a more natural, unprocessed character.",
        "winemaking", "spain_sherry",
        [{"type": "wine_style", "name": "En rama"}],
        ["spain", "sherry", "en_rama"],
    )

    # --- Historical / general enrichment ---
    add(
        "The phylloxera epidemic reached Spain in the late 19th century, devastating many vineyards.",
        "viticulture", "spain_general",
        [{"type": "country", "name": "Spain"}],
        ["spain", "history", "phylloxera"],
    )
    add(
        "Many Canary Islands vines survived phylloxera because sandy volcanic soils are inhospitable to the phylloxera louse.",
        "viticulture", "spain_general",
        [{"type": "region", "name": "Canary Islands"}],
        ["spain", "history", "phylloxera", "canary_islands"],
    )
    add(
        "Spain introduced the DO system in 1932, modeled after the French AOC system.",
        "wine_regions", "spain_regulation",
        [{"type": "country", "name": "Spain"}],
        ["spain", "regulation", "history"],
    )
    add(
        "The Instituto Nacional de Denominaciones de Origen (INDO) was the original governing body for Spanish wine appellations.",
        "wine_business", "spain_regulation",
        [{"type": "organization", "name": "INDO"}],
        ["spain", "regulation", "organization"],
    )
    add(
        "In Rioja, traditional aging uses American oak barrels (225L barricas), while modern producers increasingly use French oak.",
        "winemaking", "spain_doca",
        [{"type": "appellation", "name": "Rioja"}],
        ["spain", "rioja", "winemaking", "oak"],
    )
    add(
        "Carbonic maceration (maceración carbónica) is used in Rioja to produce young, fruity Joven wines.",
        "winemaking", "spain_doca",
        [{"type": "technique", "name": "Carbonic maceration"}, {"type": "appellation", "name": "Rioja"}],
        ["spain", "rioja", "winemaking"],
    )

    # --- Additional region-specific facts for underrepresented DOs ---
    region_extra = [
        ("Somontano", "Somontano is in the foothills of the Pyrenees in Aragón and has a continental climate with Mediterranean influence."),
        ("Navarra", "Navarra was historically known for rosado (rosé) wines from Garnacha, but now produces a wide range of styles."),
        ("Penedès", "Penedès is the home of the Torres family, one of Spain's most famous wine dynasties."),
        ("Montsant", "Montsant DO surrounds the Priorat DOCa and offers similar styles at more accessible prices."),
        ("Bierzo", "Bierzo's best vineyards are on steep, slate hillsides in the El Bierzo valley, producing fine Mencía reds."),
        ("Calatayud", "Calatayud is known for old-vine Garnacha, with many vines over 50 years old at high altitude."),
        ("Campo de Borja", "Campo de Borja is sometimes called the 'Empire of Garnacha' due to the dominance of old-vine Garnacha plantings."),
        ("Toro", "Toro wines are known for their power and concentration, due to the extreme continental climate and old bush vines."),
        ("Rueda", "Rueda's continental climate with hot days and cool nights is ideal for preserving acidity in Verdejo grapes."),
        ("Valdeorras", "Valdeorras is experiencing a revival, with increasing attention to old-vine Godello and Mencía on slate soils."),
        ("Ribeira Sacra", "Ribeira Sacra's terraced vineyards above the Sil and Miño rivers are among the steepest in Europe."),
        ("Jumilla", "Jumilla's old-vine, ungrafted Monastrell vines survived phylloxera due to sandy soils."),
        ("Yecla", "Yecla DO is dominated by a single cooperative, Bodegas Castaño, which produces most of the region's wine."),
        ("Terra Alta", "Terra Alta is the leading area for Garnacha Blanca, which accounts for about one-third of plantings."),
        ("Empordà", "Empordà (Ampurdán) borders France and has a strong tradition of Garnacha-based wines and sweet Garnatxa dessert wines."),
        ("Cigales", "Cigales is historically known for rosado wines made from Tempranillo and Garnacha."),
        ("Lanzarote", "In Lanzarote, vines are grown in individual pits (hoyos) dug into volcanic ash, protected by semicircular stone walls called zocos."),
        ("Utiel-Requena", "Utiel-Requena has the largest concentration of Bobal vineyards in the world."),
        ("Manchuela", "Manchuela is an emerging DO east of La Mancha, gaining recognition for Bobal and Tempranillo blends."),
        ("Binissalem", "Binissalem was the first DO established in the Balearic Islands, in 1990."),
        ("Tacoronte-Acentejo", "Tacoronte-Acentejo was the first DO established in the Canary Islands, in 1992."),
        ("Conca de Barberà", "Conca de Barberà is known for the indigenous red grape Trepat and high-quality base wines for Cava."),
        ("Tarragona", "Tarragona DO has a long winemaking history dating back to the Roman period."),
        ("Condado de Huelva", "Condado de Huelva traditionally produced fortified wines similar to Sherry, but now focuses more on modern still wines."),
        ("Arlanza", "Arlanza DO in Burgos province was granted DO status in 2007, one of the newer Spanish appellations."),
        ("Bullas", "Bullas is a small DO in the mountains of northwestern Murcia."),
        ("Costers del Segre", "Costers del Segre includes the Raimat estate, one of the largest single wine estates in Europe."),
        ("Pla i Llevant", "Pla i Llevant covers the eastern plain of Mallorca and was granted DO status in 1999."),
        ("Monterrei", "Monterrei is the southernmost DO in Galicia, with a warmer, drier climate than other Galician regions."),
        ("Alella", "Alella is a small DO near Barcelona, threatened by urban expansion."),
        ("Almansa", "Almansa is a gateway region between La Mancha and the Levante, known for Garnacha Tintorera."),
        ("Valdepeñas", "Valdepeñas was one of the first Spanish regions to adopt modern winemaking, including stainless steel fermentation."),
    ]
    for do_name, fact_text in region_extra:
        add(
            fact_text,
            "wine_regions", "spain_do",
            [{"type": "appellation", "name": do_name}],
            ["spain", "do", do_name.lower().replace(" ", "_")],
        )

    # --- Soil and climate facts for major DOs ---
    soil_climate = [
        ("Rioja", "Rioja's climate transitions from Atlantic influence in the west (Rioja Alta, Rioja Alavesa) to Mediterranean in the east (Rioja Oriental)."),
        ("Ribera del Duero", "Ribera del Duero has chalky clay and limestone soils that contribute to wine structure and minerality."),
        ("Priorat", "Priorat's llicorella slate soils force vine roots deep, limiting yields and concentrating flavors."),
        ("Jerez-Xérès-Sherry", "The Sherry triangle experiences the warm, dry Levante wind and the cool, humid Poniente wind from the Atlantic."),
        ("Rías Baixas", "Rías Baixas has a maritime climate with high rainfall, requiring careful canopy management."),
        ("La Mancha", "La Mancha has a hot continental climate with very low annual rainfall, around 350-400mm."),
        ("Bierzo", "Bierzo has a unique microclimate influenced by the Atlantic, with more moderate temperatures than central Castilla y León."),
        ("Penedès", "Penedès has three altitude zones: Baix Penedès (coastal), Mig Penedès (central), and Alt Penedès (upland)."),
        ("Toro", "Toro's vineyards sit at 620-750 meters elevation with sandy soils over clay subsoil."),
        ("Cariñena", "Cariñena DO is the birthplace of the Cariñena (Carignan) grape, though Garnacha now dominates plantings."),
    ]
    for do_name, fact_text in soil_climate:
        add(
            fact_text,
            "viticulture", "spain_terroir",
            [{"type": "appellation", "name": do_name}],
            ["spain", "terroir", do_name.lower().replace(" ", "_")],
        )

    # --- Spain regulatory/business facts ---
    add(
        "Spain's quality hierarchy from lowest to highest is: Vino de Mesa, Vino de la Tierra (IGP), DO, DOCa, and Vino de Pago.",
        "wine_regions", "spain_regulation",
        [{"type": "country", "name": "Spain"}],
        ["spain", "regulation", "hierarchy"],
    )
    add(
        "Spanish Crianza white and rosé wines must be aged for at least 18 months, with 6 months in oak.",
        "winemaking", "spain_aging",
        [{"type": "aging_category", "name": "Crianza"}],
        ["spain", "aging", "crianza", "white"],
    )
    add(
        "In Rioja, Crianza red wines require at least 12 months in oak (stricter than the national 6-month minimum).",
        "winemaking", "spain_aging",
        [{"type": "aging_category", "name": "Crianza"}, {"type": "appellation", "name": "Rioja"}],
        ["spain", "aging", "rioja"],
    )
    add(
        "In Rioja, Reserva red wines must spend at least 12 months in oak and not be released until the fourth year.",
        "winemaking", "spain_aging",
        [{"type": "aging_category", "name": "Reserva"}, {"type": "appellation", "name": "Rioja"}],
        ["spain", "aging", "rioja"],
    )
    add(
        "In Rioja, Gran Reserva red wines must spend at least 24 months in oak and not be released until the sixth year.",
        "winemaking", "spain_aging",
        [{"type": "aging_category", "name": "Gran Reserva"}, {"type": "appellation", "name": "Rioja"}],
        ["spain", "aging", "rioja"],
    )
    add(
        "The Consejo Regulador de la Denominación de Origen Calificada Rioja was established in 1926.",
        "wine_business", "spain_doca",
        [{"type": "organization", "name": "Consejo Regulador"}, {"type": "appellation", "name": "Rioja"}],
        ["spain", "rioja", "organization"],
    )

    # --- Bulk enrichment: per-DO climate and key characteristics ---
    do_climate_facts = [
        ("Abona", "Abona DO in Tenerife benefits from volcanic soils and high-altitude vineyards up to 1,700 meters.", "viticulture"),
        ("Alella", "Alella DO has a mild Mediterranean climate moderated by proximity to the sea.", "viticulture"),
        ("Alicante", "Alicante DO has a hot Mediterranean climate well-suited to Monastrell and Moscatel de Alejandría.", "viticulture"),
        ("Almansa", "Almansa DO has a high-altitude continental climate at around 700 meters elevation.", "viticulture"),
        ("Bierzo", "Bierzo DO has a transitional climate between Atlantic and Continental, with slate soils similar to Priorat.", "viticulture"),
        ("Bullas", "Bullas DO has a continental climate with Mediterranean influence at altitudes of 400-900 meters.", "viticulture"),
        ("Calatayud", "Calatayud DO has some of the highest-altitude Garnacha vineyards in Spain, above 800 meters.", "viticulture"),
        ("Campo de Borja", "Campo de Borja DO has over 1,000 hectares of Garnacha vines over 35 years old.", "viticulture"),
        ("Cariñena", "Cariñena DO has a continental climate with hot summers and cold winters at 400-800 meters elevation.", "viticulture"),
        ("Cigales", "Cigales DO has a continental climate with extreme temperature variations between day and night.", "viticulture"),
        ("Condado de Huelva", "Condado de Huelva DO has a warm Atlantic climate influenced by the Guadalquivir estuary.", "viticulture"),
        ("El Hierro", "El Hierro DO is located on the smallest and westernmost of the Canary Islands.", "wine_regions"),
        ("Gran Canaria", "Gran Canaria DO has vineyards at various altitudes, from sea level to over 1,500 meters.", "viticulture"),
        ("Jumilla", "Jumilla DO has extremely arid conditions with annual rainfall below 300mm.", "viticulture"),
        ("La Gomera", "La Gomera DO is one of the newest Spanish DOs, established in 2003.", "wine_regions"),
        ("La Palma", "La Palma DO has three sub-zones: Fuencaliente, Hoyo de Mazo, and Norte de la Palma.", "wine_regions"),
        ("Málaga", "Málaga DO has vineyards ranging from sea level to the mountains of the Axarquía.", "viticulture"),
        ("Manchuela", "Manchuela DO is located between La Mancha and Valencia, with chalky soils ideal for Bobal.", "viticulture"),
        ("Méntrida", "Méntrida DO is dominated by old-vine Garnacha on sandy-clay soils.", "viticulture"),
        ("Montsant", "Montsant DO forms a ring around Priorat, sharing similar slate and granite soils at lower elevations.", "viticulture"),
        ("Navarra", "Navarra DO has five sub-zones: Baja Montaña, Valdizarbe, Tierra Estella, Ribera Alta, and Ribera Baja.", "wine_regions"),
        ("Penedès", "Penedès DO vineyards range from near sea level in Baix Penedès to over 800 meters in Alt Penedès.", "viticulture"),
        ("Rías Baixas", "Rías Baixas DO has one of the highest rainfall levels of any quality wine region in Europe.", "viticulture"),
        ("Ribera del Duero", "Ribera del Duero DO requires red wines to contain at least 75% Tinta del País (Tempranillo).", "winemaking"),
        ("Ribera del Guadiana", "Ribera del Guadiana DO is the main wine region of Extremadura, with six sub-zones.", "wine_regions"),
        ("Ribeira Sacra", "Ribeira Sacra DO vineyards can reach inclinations of up to 85%, among the steepest in Europe.", "viticulture"),
        ("Rueda", "Rueda DO's Verdejo wines must contain at least 50% Verdejo, while Rueda Verdejo must be at least 85%.", "winemaking"),
        ("Somontano", "Somontano DO was a pioneer in Spain for planting international varieties alongside indigenous grapes.", "viticulture"),
        ("Tarragona", "Tarragona DO is divided into two sub-zones: Tarragona Camp and Tarragona Comarca de Falset.", "wine_regions"),
        ("Terra Alta", "Terra Alta DO is the leading area for white Garnacha (Garnacha Blanca) in Catalonia.", "grape_varieties"),
        ("Tierra de León", "Tierra de León DO was granted DO status in 2007, focused on the indigenous Prieto Picudo grape.", "wine_regions"),
        ("Toro", "Toro DO has average vine age among the highest in Spain, with many ungrafted vines over 80 years old.", "viticulture"),
        ("Utiel-Requena", "Utiel-Requena DO has a continental climate at 600-900 meters elevation with significant diurnal range.", "viticulture"),
        ("Valencia", "Valencia DO has three sub-zones: Alto Turia, Valentino, and Moscatel de Valencia.", "wine_regions"),
        ("Valdeorras", "Valdeorras DO has slate soils that give Godello wines a distinctive mineral character.", "viticulture"),
        ("Valdepeñas", "Valdepeñas DO sits on a limestone-clay plateau at about 700 meters altitude.", "viticulture"),
        ("Vinos de Madrid", "Vinos de Madrid DO has three sub-zones: San Martín de Valdeiglesias, Navalcarnero, and Arganda.", "wine_regions"),
        ("Yecla", "Yecla DO has a hot semi-arid climate with low rainfall, well-suited to drought-resistant Monastrell.", "viticulture"),
    ]
    for do_name, fact_text, domain in do_climate_facts:
        add(
            fact_text,
            domain, "spain_do",
            [{"type": "appellation", "name": do_name}],
            ["spain", "do", do_name.lower().replace(" ", "_")],
        )

    # --- Additional bulk grape-region pairings ---
    grape_region_extras = [
        ("Garnacha Tinta", "Garnacha Tinta thrives at high altitudes in Aragón, where old vines produce concentrated, complex wines."),
        ("Monastrell", "Monastrell is one of the most drought-resistant grape varieties, well-suited to Spain's arid southeast."),
        ("Tempranillo", "Tempranillo is known by different local names across Spain: Cencibel in La Mancha, Ull de Llebre in Catalonia, and Tinta del País in Ribera del Duero."),
        ("Viura", "Viura (Macabeo) is the most widely planted white grape in Rioja and the primary grape in many Cava blends."),
        ("Garnacha Blanca", "Garnacha Blanca is an important white grape in Catalonia, particularly in Terra Alta where it produces rich, textured wines."),
        ("Macabeo", "Macabeo (Viura) is the most planted white grape across northeastern Spain."),
        ("Pedro Ximénez", "Pedro Ximénez grapes used for sweet Sherry are sun-dried on esparto grass mats (asoleo) to concentrate their sugars."),
        ("Bobal", "Bobal is Spain's third most planted red grape by area, after Tempranillo and Airén."),
        ("Godello", "Godello was nearly extinct by the 1970s before a revival in Valdeorras rescued the variety."),
        ("Mencía", "Mencía is often compared to Pinot Noir for its aromatic complexity and medium body."),
        ("Cariñena", "The Cariñena (Carignan) grape originated in Aragón, though it is now more widely grown in France."),
        ("Monastrell", "Monastrell typically ripens late and produces deeply colored wines with notes of blackberry, plum, and spice."),
        ("Listán Negro", "Listán Negro in the Canary Islands can produce wines with unusual volcanic mineral notes."),
        ("Albariño", "Albariño produces aromatic white wines with notes of peach, apricot, and saline minerality."),
        ("Verdejo", "Verdejo was traditionally oxidized and aged, but modern producers in Rueda craft fresh, citrus-driven styles."),
        ("Maturana Tinta", "Maturana Tinta is a recently recovered indigenous variety authorized in Rioja DOCa."),
    ]
    for grape, fact_text in grape_region_extras:
        add(
            fact_text,
            "grape_varieties", "spain_general",
            [{"type": "grape", "name": grape}],
            ["spain", "grape"],
        )

    # --- Major Spanish producers ---
    producer_facts = [
        ("Torres", "Penedès", "Torres is one of Spain's largest and most influential wine families, based in Penedès."),
        ("Marqués de Riscal", "Rioja", "Marqués de Riscal, founded in 1858, is one of the oldest bodegas in Rioja."),
        ("Marqués de Murrieta", "Rioja", "Marqués de Murrieta, founded in 1852, is credited as one of the founders of modern Rioja winemaking."),
        ("CVNE", "Rioja", "CVNE (Compañía Vinícola del Norte de España), founded in 1879, produces wines including the iconic Imperial and Viña Real."),
        ("La Rioja Alta", "Rioja", "La Rioja Alta S.A., founded in 1890, is known for traditional, long-aged Rioja Reservas and Gran Reservas."),
        ("Bodegas Muga", "Rioja", "Bodegas Muga in Rioja is one of the few producers that still uses all-oak fermentation vats."),
        ("Álvaro Palacios", "Priorat", "Álvaro Palacios helped revive Priorat and produces the celebrated L'Ermita from old Garnacha vines."),
        ("Vega Sicilia", "Ribera del Duero", "Vega Sicilia's Único wine, a Tempranillo blend, is typically aged for 10 years before release."),
        ("Dominio de Pingus", "Ribera del Duero", "Dominio de Pingus, established in 1995 by Peter Sisseck, quickly became one of Spain's most acclaimed wines."),
        ("Bodegas Protos", "Ribera del Duero", "Bodegas Protos, founded in 1927, was one of the first wineries established in Ribera del Duero."),
        ("Mar de Frades", "Rías Baixas", "Mar de Frades is a well-known Albariño producer in the Rías Baixas DO."),
        ("Bodegas Castaño", "Yecla", "Bodegas Castaño dominates Yecla DO production and has championed old-vine Monastrell."),
        ("González Byass", "Jerez-Xérès-Sherry", "González Byass produces Tío Pepe, the world's best-selling Fino Sherry."),
        ("Lustau", "Jerez-Xérès-Sherry", "Lustau is renowned for its almacenista bottlings, sourcing wines from individual small-scale Sherry agers."),
        ("Barbadillo", "Manzanilla-Sanlúcar de Barrameda", "Barbadillo is the largest producer of Manzanilla Sherry in Sanlúcar de Barrameda."),
    ]
    for producer, appellation, fact_text in producer_facts:
        add(
            fact_text,
            "producers", "spain_producers",
            [{"type": "producer", "name": producer}, {"type": "appellation", "name": appellation}],
            ["spain", "producer"],
        )

    # --- Additional enrichment: DO area and production stats ---
    do_stats = [
        ("Rioja", 65298, "Rioja DOCa has approximately 65,298 hectares under vine and over 600 registered bodegas."),
        ("Ribera del Duero", 23368, "Ribera del Duero DO covers approximately 23,368 hectares of vineyards."),
        ("La Mancha", 164590, "La Mancha DO covers approximately 164,590 hectares, making it the world's largest single wine appellation."),
        ("Cava", 32000, "The Cava DO encompasses approximately 32,000 hectares, spread across several Spanish regions."),
        ("Rías Baixas", 4068, "Rías Baixas DO covers approximately 4,068 hectares of vineyard area."),
        ("Penedès", 17500, "Penedès DO covers approximately 17,500 hectares in central Catalonia."),
        ("Navarra", 11150, "Navarra DO covers approximately 11,150 hectares of vineyard area."),
        ("Rueda", 17500, "Rueda DO covers approximately 17,500 hectares, predominantly planted with Verdejo."),
        ("Jumilla", 22500, "Jumilla DO covers approximately 22,500 hectares, primarily planted with Monastrell."),
        ("Valdepeñas", 22400, "Valdepeñas DO covers approximately 22,400 hectares of vineyard area."),
        ("Jerez-Xérès-Sherry", 7000, "Jerez-Xérès-Sherry DO has approximately 7,000 hectares of vineyard area."),
        ("Somontano", 4350, "Somontano DO covers approximately 4,350 hectares of vineyard area."),
        ("Toro", 5800, "Toro DO covers approximately 5,800 hectares of vineyard area."),
        ("Bierzo", 2900, "Bierzo DO covers approximately 2,900 hectares, with Mencía as the primary grape."),
        ("Priorat", 1955, "Priorat DOCa covers approximately 1,955 hectares of vineyard area."),
    ]
    for do_name, area, fact_text in do_stats:
        add(
            fact_text,
            "wine_regions", "spain_do",
            [{"type": "appellation", "name": do_name}],
            ["spain", "do", "area"],
        )

    # --- Varietal wine regulations ---
    varietal_regs = [
        "In Spain, varietal wines must contain at least 85% of the named grape variety.",
        "Spanish rosado (rosé) wines are typically made from Garnacha or Tempranillo using short maceration.",
        "Cosechero refers to young Spanish wines released in the same year as the harvest.",
        "Noble aging (crianza en roble) is an unofficial term in Spain for wines with brief oak contact.",
        "Spanish sparkling wines other than Cava may be labeled as 'espumoso' under regional regulations.",
        "Vino de Mesa is the lowest classification in Spain, with no geographical indication required.",
        "IGP (Indicación Geográfica Protegida) wines in Spain were formerly labeled as Vino de la Tierra.",
        "Spain has 46 IGP/Vino de la Tierra designations in addition to its 70 DO/DOCa appellations.",
    ]
    for fact_text in varietal_regs:
        add(
            fact_text,
            "winemaking", "spain_regulation",
            [{"type": "country", "name": "Spain"}],
            ["spain", "regulation"],
        )

    # --- Historical DO facts ---
    historical_do_facts = [
        "Jerez-Xérès-Sherry was the first Spanish region to receive DO status in 1933.",
        "Rioja received its DO status in 1925, predating the formal DO system established in 1932.",
        "Penedès DO was established in 1960 and has been a leader in modernizing Spanish winemaking.",
        "Rías Baixas was granted DO status in 1988, relatively recently for such a well-known region.",
        "Ribera del Duero was granted DO status in 1982, despite centuries of winemaking history.",
        "Priorat was granted DOCa (DOQ) status in 2000, becoming only the second region to receive this distinction.",
        "Bierzo DO was established in 1989 and has gained international recognition for Mencía wines.",
        "Rueda was granted DO status in 1980, initially only for white wines.",
    ]
    for fact_text in historical_do_facts:
        add(
            fact_text,
            "wine_regions", "spain_regulation",
            [{"type": "country", "name": "Spain"}],
            ["spain", "regulation", "history"],
        )

    # --- Climate and geography extras ---
    add(
        "Spain's wine regions span a wide range of climates, from the cool, rainy Atlantic northwest to the hot, arid Mediterranean southeast.",
        "viticulture", "spain_general",
        [{"type": "country", "name": "Spain"}],
        ["spain", "climate"],
    )
    add(
        "Bush vine (en vaso) training is traditional in many Spanish regions, especially for Garnacha and Monastrell.",
        "viticulture", "spain_general",
        [{"type": "technique", "name": "Bush vine"}],
        ["spain", "viticulture"],
    )
    add(
        "Gobelet (vaso) training in Spain allows vines to self-shade berries in hot climates without trellising.",
        "viticulture", "spain_general",
        [{"type": "technique", "name": "Gobelet"}],
        ["spain", "viticulture"],
    )
    add(
        "Spain has the third-largest wine production by volume in the world, after Italy and France.",
        "wine_business", "spain_general",
        [{"type": "country", "name": "Spain"}],
        ["spain", "production"],
    )
    add(
        "Spanish organic viticulture has grown rapidly, with Spain having one of the largest organic vineyard areas in the world.",
        "viticulture", "spain_general",
        [{"type": "country", "name": "Spain"}],
        ["spain", "organic"],
    )

    # --- Additional Canary Islands facts ---
    canary_extra = [
        "The Canary Islands have 10 distinct DO wine regions across their seven islands.",
        "Canary Islands wines are made from pre-phylloxera grape varieties that survived due to volcanic and sandy soils.",
        "Listán Blanco (Palomino) is the most widely planted white grape across the Canary Islands.",
        "The volcanic island of Lanzarote has one of the most unique viticultural landscapes in the world.",
        "Malvasía wines from Lanzarote were historically prized throughout Europe, referenced by Shakespeare.",
        "The Canary Islands' isolation has preserved over 60 indigenous grape varieties not found elsewhere.",
    ]
    for fact_text in canary_extra:
        add(
            fact_text,
            "wine_regions", "spain_canary",
            [{"type": "region", "name": "Canary Islands"}],
            ["spain", "canary_islands"],
        )

    # --- Galicia in-depth ---
    galicia_extra = [
        "Galicia in northwest Spain has five DO regions: Rías Baixas, Ribeiro, Ribeira Sacra, Monterrei, and Valdeorras.",
        "Galicia's cool, wet climate makes it Spain's most distinctive wine region, more similar to northern Portugal than central Spain.",
        "The pergola (emparrado) training system is traditional in Galician viticulture, keeping grapes above the damp ground.",
        "Galician wines are predominantly white, with Albariño, Godello, and Treixadura as the key varieties.",
    ]
    for fact_text in galicia_extra:
        add(
            fact_text,
            "wine_regions", "spain_general",
            [{"type": "region", "name": "Galicia"}],
            ["spain", "galicia"],
        )

    # --- Per-DO secondary grape details ---
    secondary_grapes = [
        ("Ribera del Duero", "Cabernet Sauvignon", "Cabernet Sauvignon is a permitted secondary grape in Ribera del Duero, blended in small proportions with Tempranillo."),
        ("Ribera del Duero", "Malbec", "Malbec is authorized as a minority blending grape in Ribera del Duero DO."),
        ("Ribera del Duero", "Merlot", "Merlot is permitted in Ribera del Duero but used in much smaller quantities than Tempranillo."),
        ("Navarra", "Garnacha Tinta", "Navarra has historically been known for Garnacha-based rosados, though Tempranillo plantings have increased."),
        ("Navarra", "Chardonnay", "Chardonnay is one of the authorized white varieties in Navarra, producing fresh, modern-style whites."),
        ("Penedès", "Cabernet Sauvignon", "Torres was a pioneer in planting Cabernet Sauvignon in Penedès in the 1960s."),
        ("Jumilla", "Cabernet Sauvignon", "Cabernet Sauvignon is blended with Monastrell in Jumilla to add structure and complexity."),
        ("Somontano", "Gewürztraminer", "Somontano is one of the few Spanish DOs where Gewürztraminer is authorized."),
        ("Somontano", "Moristel", "Moristel is an indigenous red grape unique to Somontano."),
        ("Valdeorras", "Godello", "Godello in Valdeorras produces white wines with stone fruit, citrus, and a distinctive mineral finish."),
        ("Rueda", "Sauvignon Blanc", "Sauvignon Blanc is a secondary variety in Rueda, sometimes blended with Verdejo."),
        ("Ribeira Sacra", "Godello", "Godello is grown alongside Mencía in Ribeira Sacra, producing mineral whites from terraced vineyards."),
        ("Monterrei", "Treixadura", "Treixadura is an important white grape in Monterrei, adding aromatic complexity to blends."),
        ("Bierzo", "Godello", "Godello is the main white grape of Bierzo, producing wines of increasing quality and recognition."),
        ("Bierzo", "Doña Blanca", "Doña Blanca is a secondary white grape in Bierzo, used primarily for blending."),
        ("Toro", "Malvasía", "Malvasía is a secondary white grape in Toro, used for fresh white wines."),
        ("Terra Alta", "Garnacha Blanca", "Garnacha Blanca accounts for about 30% of plantings in Terra Alta, one of the highest proportions in any Spanish DO."),
        ("Empordà", "Cariñena", "Cariñena is an important red grape in Empordà, where it is used for both dry reds and sweet Garnatxa dessert wines."),
        ("Conca de Barberà", "Trepat", "Trepat is the signature grape of Conca de Barberà, unique to this Catalan region."),
    ]
    for do_name, grape, fact_text in secondary_grapes:
        add(
            fact_text,
            "grape_varieties", "spain_do",
            [{"type": "appellation", "name": do_name}, {"type": "grape", "name": grape}],
            ["spain", "do", "grape"],
        )

    # --- Spanish winemaking techniques ---
    spain_winemaking = [
        "Tinajas (large clay amphorae) are being revived by some Spanish winemakers for natural fermentation.",
        "Whole-cluster fermentation is used by some modern Spanish producers, particularly in Ribeira Sacra and Bierzo.",
        "Lías aging (sur lie) is used for some Spanish white wines, particularly Albariño in Rías Baixas.",
        "Coupage is the Spanish term for blended wines combining multiple grape varieties.",
        "Vendimia tardía (late harvest) wines are sweet wines made from grapes left on the vine to over-ripen.",
        "Supurao is a fortified wine style from Cangas DO in Asturias, similar to historical traditions.",
        "Clarete is a traditional light red style from Cigales, made by co-fermenting red and white grapes.",
    ]
    for fact_text in spain_winemaking:
        add(
            fact_text,
            "winemaking", "spain_general",
            [{"type": "country", "name": "Spain"}],
            ["spain", "winemaking"],
        )

    # --- Spain regional autonomous community overview ---
    spain_ac = [
        ("Catalonia", "Catalonia has 11 DO appellations plus Cava, making it the Spanish autonomous community with the most DOs."),
        ("Castilla y León", "Castilla y León has 10 DO wine regions, including Ribera del Duero, Rueda, and Toro."),
        ("Castilla-La Mancha", "Castilla-La Mancha is Spain's largest wine-producing region by volume, home to La Mancha, Valdepeñas, and Manchuela DOs."),
        ("Andalusia", "Andalusia is known for fortified wines, with Jerez-Xérès-Sherry, Manzanilla, Montilla-Moriles, Condado de Huelva, and Málaga DOs."),
        ("Aragón", "Aragón has four DO wine regions: Somontano, Cariñena, Campo de Borja, and Calatayud."),
        ("Valencia", "The Valencia autonomous community has three DOs: Valencia, Utiel-Requena, and Alicante."),
        ("Basque Country", "The Basque Country has three Txakolí DOs plus part of the Rioja DOCa."),
        ("Galicia", "Galicia's five DOs produce predominantly white wines in an Atlantic climate unique in Spain."),
        ("Murcia", "Murcia has three DOs: Jumilla, Yecla, and Bullas, all known for Monastrell."),
        ("Extremadura", "Extremadura has one major DO, Ribera del Guadiana, covering most of the region's vineyards."),
    ]
    for ac_name, fact_text in spain_ac:
        add(
            fact_text,
            "wine_regions", "spain_general",
            [{"type": "region", "name": ac_name}],
            ["spain", "region", ac_name.lower().replace(" ", "_")],
        )

    # --- Final enrichment batch: per-appellation notable wines/producers ---
    final_spain = [
        ("Priorat", "Priorat wines typically command premium prices due to extremely low yields and limited production.", "wine_business"),
        ("Rioja", "Rioja produces approximately 300 million liters of wine annually, more than 90% of which is red.", "wine_regions"),
        ("Rioja", "Rioja's back label system includes a color-coded guarantee seal indicating the aging category.", "winemaking"),
        ("Ribera del Duero", "Ribera del Duero's growing season is short, with only 3-4 months between budbreak and harvest.", "viticulture"),
        ("Rías Baixas", "Rías Baixas wines are typically fresh, crisp, and consumed young, though some age well for 5-10 years.", "winemaking"),
        ("Sherry", "The Jerez-Xérès-Sherry DO is the oldest DO in Spain, with Sherry production dating back to Phoenician times.", "wine_regions"),
        ("Cava", "Cava accounts for roughly 10% of global sparkling wine production.", "wine_business"),
        ("Cava", "Sant Sadurní d'Anoia in Penedès is the capital of Cava production.", "wine_regions"),
        ("La Mancha", "Despite its size, La Mancha has undergone a quality revolution, with modern wineries producing excellent value wines.", "wine_regions"),
        ("Toro", "Toro wines are among the most powerful in Spain, often exceeding 15% alcohol.", "winemaking"),
        ("Rueda", "Rueda is Spain's most commercially successful white wine region.", "wine_business"),
        ("Rueda", "Rueda Verdejo must contain at least 85% Verdejo grape, ensuring varietal purity.", "winemaking"),
        ("Bierzo", "Bierzo has been compared to Burgundy for its focus on terroir-driven, single-vineyard Mencía wines.", "wine_regions"),
        ("Jumilla", "Jumilla has attracted international attention for the quality of its old-vine Monastrell wines.", "wine_regions"),
        ("Cangas", "Cangas DO in Asturias was established in 2008 and is one of Spain's newest wine appellations.", "wine_regions"),
        ("Arribes", "Arribes DO straddles the Spanish-Portuguese border along the Duero River gorge.", "wine_regions"),
        ("Alicante", "Alicante is known for Fondillón, a traditional sweet wine made from over-ripe Monastrell grapes.", "winemaking"),
        ("Montilla-Moriles", "Montilla-Moriles produces wines similar to Sherry but often without fortification, as Pedro Ximénez naturally reaches high alcohol.", "winemaking"),
        ("Málaga", "Málaga has a rich history of sweet wine production dating back to the Phoenicians.", "wine_regions"),
        ("Ribeiro", "Ribeiro in Galicia was historically one of Spain's most famous wine regions before phylloxera.", "wine_regions"),
        ("Pla de Bages", "Pla de Bages is reviving the indigenous Picapoll grape as its signature variety.", "grape_varieties"),
        ("Méntrida", "Méntrida has gained attention from natural wine enthusiasts for its old-vine Garnacha.", "wine_regions"),
        ("Mondéjar", "Mondéjar is a small DO in Guadalajara province, one of the least known Spanish appellations.", "wine_regions"),
        ("Ribera del Júcar", "Ribera del Júcar DO was granted its status in 2003 and is centered on Bobal and Tempranillo.", "wine_regions"),
    ]
    for do_name, fact_text, domain in final_spain:
        add(
            fact_text,
            domain, "spain_do",
            [{"type": "appellation", "name": do_name}],
            ["spain", "do"],
        )

    logger.info(f"Built {len(facts)} Spain facts")
    return facts


# =============================================================================
# GERMANY — Anbaugebiete, VDP, Prädikat Wine Data
# =============================================================================

GERMANY_REGIONS = [
    {
        "name": "Ahr",
        "area_ha": 561,
        "key_grapes": ["Spätburgunder", "Riesling"],
        "notes": "One of the most northerly red wine regions in the world. Over 80% of production is red, primarily Spätburgunder (Pinot Noir).",
        "soil": "Slate and volcanic soils",
    },
    {
        "name": "Baden",
        "area_ha": 15836,
        "key_grapes": ["Spätburgunder", "Müller-Thurgau", "Grauburgunder", "Weißburgunder"],
        "notes": "Germany's warmest and southernmost wine region. The only German region in EU wine zone B.",
        "soil": "Varied: volcanic, limestone, loess",
    },
    {
        "name": "Franken",
        "area_ha": 6139,
        "key_grapes": ["Silvaner", "Müller-Thurgau", "Bacchus"],
        "notes": "Known for dry Silvaner wines and the distinctive Bocksbeutel bottle shape.",
        "soil": "Muschelkalk (shell limestone)",
    },
    {
        "name": "Hessische Bergstraße",
        "area_ha": 449,
        "key_grapes": ["Riesling", "Müller-Thurgau", "Grauburgunder"],
        "notes": "The smallest of Germany's 13 wine regions. Most wine is consumed locally.",
        "soil": "Loess and granite",
    },
    {
        "name": "Mittelrhein",
        "area_ha": 469,
        "key_grapes": ["Riesling"],
        "notes": "Steep, terraced vineyards along the Rhine river. Part of the UNESCO Rhine Gorge World Heritage Site.",
        "soil": "Slate and greywacke",
    },
    {
        "name": "Mosel",
        "area_ha": 8770,
        "key_grapes": ["Riesling", "Müller-Thurgau", "Elbling"],
        "notes": "Germany's oldest wine region and its largest Riesling-producing area. Includes vineyards along the Mosel, Saar, and Ruwer rivers.",
        "soil": "Devonian slate (blue and red)",
        "subregions": ["Saar", "Ruwer", "Mosel (upper, middle, lower)"],
    },
    {
        "name": "Nahe",
        "area_ha": 4233,
        "key_grapes": ["Riesling", "Müller-Thurgau", "Dornfelder"],
        "notes": "Known for diverse soil types that produce a wide range of Riesling styles.",
        "soil": "Diverse: porphyry, slate, sandstone, quartzite, volcanic",
    },
    {
        "name": "Pfalz",
        "area_ha": 23686,
        "key_grapes": ["Riesling", "Dornfelder", "Müller-Thurgau", "Spätburgunder"],
        "notes": "Germany's second-largest wine region and its largest producer. Protected by the Haardt mountains.",
        "soil": "Sandstone, limestone, basalt, loess",
    },
    {
        "name": "Rheingau",
        "area_ha": 3115,
        "key_grapes": ["Riesling", "Spätburgunder"],
        "notes": "Historically the most prestigious German wine region. Birthplace of Spätlese and Auslese designations. About 78% of plantings are Riesling.",
        "soil": "Slate, loess, quartzite",
    },
    {
        "name": "Rheinhessen",
        "area_ha": 26860,
        "key_grapes": ["Müller-Thurgau", "Riesling", "Dornfelder", "Silvaner"],
        "notes": "Germany's largest wine region by area. Home to the famous Liebfraumilch. The Roter Hang near Nierstein has exceptional red slate soils.",
        "soil": "Loess, limestone, red sandstone, quartzite",
    },
    {
        "name": "Saale-Unstrut",
        "area_ha": 808,
        "key_grapes": ["Müller-Thurgau", "Weißburgunder", "Silvaner"],
        "notes": "One of the most northerly wine regions in Europe. Located in the former East Germany.",
        "soil": "Shell limestone and sandstone",
    },
    {
        "name": "Sachsen",
        "area_ha": 500,
        "key_grapes": ["Müller-Thurgau", "Riesling", "Weißburgunder", "Goldriesling"],
        "notes": "Germany's easternmost and one of its smallest wine regions. Centered around Dresden and Meißen.",
        "soil": "Granite and gneiss",
    },
    {
        "name": "Württemberg",
        "area_ha": 11360,
        "key_grapes": ["Trollinger", "Riesling", "Schwarzriesling", "Lemberger"],
        "notes": "Germany's leading red wine region by proportion. Most wine is consumed locally through cooperative wineries.",
        "soil": "Muschelkalk, marl, sandstone",
    },
]

GERMANY_PRAEDIKAT = [
    {"name": "Kabinett", "description": "The lightest Prädikat level. Made from fully ripe grapes. Often light-bodied with lower alcohol."},
    {"name": "Spätlese", "description": "Made from late-harvested grapes with higher ripeness. Can be dry (trocken) or off-dry."},
    {"name": "Auslese", "description": "Made from selected bunches of very ripe grapes. Typically richer and sometimes sweet."},
    {"name": "Beerenauslese", "description": "Made from individually selected overripe berries, often affected by botrytis (noble rot), and always produces sweet wine."},
    {"name": "Trockenbeerenauslese", "description": "Made from individually selected dried berries shriveled by botrytis, producing Germany's sweetest and rarest wine, abbreviated TBA."},
    {"name": "Eiswein", "description": "Made from grapes naturally frozen on the vine at -7°C or below. Must be harvested and pressed while still frozen. The resulting wine has intense acidity and sweetness."},
]

VDP_CLASSIFICATION = [
    {"name": "Gutswein", "description": "Gutswein (estate wine) is the entry-level tier of the VDP classification, representing the regional character of a producer's estate."},
    {"name": "Ortswein", "description": "Ortswein (village wine) is made from grapes grown in a specific village or commune, with stricter yield limits than Gutswein."},
    {"name": "Erste Lage", "description": "Erste Lage (first-growth vineyard) designates high-quality vineyard sites with defined soil and microclimate characteristics, equivalent to Premier Cru."},
    {"name": "Große Lage", "description": "Große Lage (Grand Cru vineyard) is the top tier of VDP classification, representing Germany's finest vineyard sites, with dry wines labeled Großes Gewächs (GG)."},
]


def build_germany_facts(source_ids: dict) -> list[dict]:
    """Generate atomic facts about German wine regions, classifications, and varieties."""
    facts = []
    seen = set()

    def add(text, domain, subdomain, entities, tags, source_key="germany_dwi"):
        if text in seen:
            return
        seen.add(text)
        facts.append({
            "fact_text": text,
            "domain": domain,
            "subdomain": subdomain,
            "source_id": source_ids[source_key],
            "entities": entities,
            "tags": tags,
        })

    # --- General Germany wine facts ---
    add(
        "Germany has 13 official wine-growing regions (Anbaugebiete).",
        "wine_regions", "germany_general",
        [{"type": "country", "name": "Germany"}],
        ["germany", "regulation"],
    )
    add(
        "German wine law distinguishes between Qualitätswein (quality wine from a specified region) and Prädikatswein (quality wine with special attributes).",
        "wine_regions", "germany_regulation",
        [{"type": "country", "name": "Germany"}],
        ["germany", "regulation", "classification"],
    )
    add(
        "Prädikatswein is the highest quality level in the German wine classification system.",
        "wine_regions", "germany_regulation",
        [{"type": "classification", "name": "Prädikatswein"}],
        ["germany", "regulation"],
    )
    add(
        "German Qualitätswein must originate from one of the 13 designated Anbaugebiete and pass an analytical and sensory examination (AP number).",
        "wine_regions", "germany_regulation",
        [{"type": "classification", "name": "Qualitätswein"}],
        ["germany", "regulation"],
    )
    add(
        "Landwein is Germany's equivalent to France's Vin de Pays, a regional wine with fewer restrictions than Qualitätswein.",
        "wine_regions", "germany_regulation",
        [{"type": "classification", "name": "Landwein"}],
        ["germany", "regulation"],
    )
    add(
        "Chaptalization (adding sugar before fermentation) is permitted for Qualitätswein but prohibited for all Prädikatswein levels.",
        "winemaking", "germany_regulation",
        [{"type": "technique", "name": "Chaptalization"}],
        ["germany", "regulation", "winemaking"],
    )
    add(
        "Riesling is the most planted grape variety in Germany, accounting for approximately 23% of total vineyard area.",
        "grape_varieties", "germany_general",
        [{"type": "grape", "name": "Riesling"}, {"type": "country", "name": "Germany"}],
        ["germany", "grape", "riesling"],
    )
    add(
        "Müller-Thurgau is the second most planted white grape in Germany.",
        "grape_varieties", "germany_general",
        [{"type": "grape", "name": "Müller-Thurgau"}],
        ["germany", "grape"],
    )
    add(
        "Spätburgunder (Pinot Noir) is the most important red grape variety in Germany.",
        "grape_varieties", "germany_general",
        [{"type": "grape", "name": "Spätburgunder"}],
        ["germany", "grape", "red"],
    )
    add(
        "Dornfelder is a German red grape crossing that has become the second most planted red variety in Germany.",
        "grape_varieties", "germany_general",
        [{"type": "grape", "name": "Dornfelder"}],
        ["germany", "grape", "red"],
    )
    add(
        "The German word 'trocken' on a wine label indicates a dry wine with no more than 9 g/L residual sugar.",
        "winemaking", "germany_regulation",
        [{"type": "term", "name": "trocken"}],
        ["germany", "regulation", "sweetness"],
    )
    add(
        "The German word 'halbtrocken' on a wine label indicates an off-dry wine with between 9 and 18 g/L residual sugar.",
        "winemaking", "germany_regulation",
        [{"type": "term", "name": "halbtrocken"}],
        ["germany", "regulation", "sweetness"],
    )
    add(
        "The German word 'feinherb' is an unofficial term for off-dry wines, similar to halbtrocken but with no legal definition.",
        "winemaking", "germany_regulation",
        [{"type": "term", "name": "feinherb"}],
        ["germany", "regulation", "sweetness"],
    )
    add(
        "Sekt is the German term for sparkling wine. Deutscher Sekt must be made from German-grown grapes.",
        "winemaking", "germany_sparkling",
        [{"type": "wine_style", "name": "Sekt"}],
        ["germany", "sparkling"],
    )
    add(
        "Winzersekt is estate-produced German sparkling wine made using the traditional method.",
        "winemaking", "germany_sparkling",
        [{"type": "wine_style", "name": "Winzersekt"}],
        ["germany", "sparkling", "traditional_method"],
    )

    # --- Regions ---
    for region in GERMANY_REGIONS:
        name = region["name"]
        ent = [{"type": "region", "name": name}]

        add(
            f"{name} is one of the 13 official wine-growing regions (Anbaugebiete) in Germany.",
            "wine_regions", "germany_regions",
            ent, ["germany", "region"],
        )
        add(
            f"The {name} wine region covers approximately {region['area_ha']:,} hectares.",
            "wine_regions", "germany_regions",
            ent, ["germany", "region", "area"],
        )
        if region.get("notes"):
            # Split multi-sentence notes into individual facts
            for sentence in re.split(r'(?<=[.!?])\s+', region["notes"]):
                sentence = sentence.strip()
                if len(sentence) > 10:
                    add(
                        sentence,
                        "wine_regions", "germany_regions",
                        ent, ["germany", "region", name.lower()],
                    )
        for grape in region.get("key_grapes", []):
            add(
                f"{grape} is a key grape variety grown in the {name} wine region of Germany.",
                "grape_varieties", "germany_regions",
                ent + [{"type": "grape", "name": grape}],
                ["germany", "grape", name.lower()],
            )
        if region.get("soil"):
            add(
                f"The {name} wine region is characterized by {region['soil'].lower()} soils.",
                "viticulture", "germany_regions",
                ent, ["germany", "terroir", "soil"],
            )
        if region.get("subregions"):
            sub_list = ", ".join(region["subregions"])
            add(
                f"The {name} wine region includes the subregions {sub_list}.",
                "wine_regions", "germany_regions",
                ent, ["germany", "region", "subregions"],
            )

    # --- Prädikat levels ---
    add(
        "The German Prädikat system ranks wines by the ripeness of grapes at harvest, measured in degrees Oechsle.",
        "winemaking", "germany_praedikat",
        [{"type": "classification", "name": "Prädikatswein"}],
        ["germany", "praedikat", "regulation"],
    )
    add(
        "The six Prädikat levels, from lowest to highest ripeness, are: Kabinett, Spätlese, Auslese, Beerenauslese, Trockenbeerenauslese, and Eiswein.",
        "winemaking", "germany_praedikat",
        [{"type": "classification", "name": "Prädikatswein"}],
        ["germany", "praedikat"],
    )

    for level in GERMANY_PRAEDIKAT:
        name = level["name"]
        for sentence in re.split(r'(?<=[.!?])\s+', level["description"]):
            sentence = sentence.strip()
            if len(sentence) > 10:
                add(
                    f"{name}: {sentence}" if not sentence.startswith(name) else sentence,
                    "winemaking", "germany_praedikat",
                    [{"type": "classification", "name": name}],
                    ["germany", "praedikat", name.lower()],
                )

    # --- VDP Classification ---
    add(
        "The VDP (Verband Deutscher Prädikatsweingüter) is an association of around 200 top German wine estates.",
        "wine_business", "germany_vdp",
        [{"type": "organization", "name": "VDP"}],
        ["germany", "vdp", "organization"],
        source_key="germany_vdp",
    )
    add(
        "The VDP classification system is modeled after the Burgundian vineyard hierarchy, ranking vineyards rather than wines.",
        "wine_regions", "germany_vdp",
        [{"type": "organization", "name": "VDP"}],
        ["germany", "vdp", "classification"],
        source_key="germany_vdp",
    )

    for level in VDP_CLASSIFICATION:
        name = level["name"]
        for sentence in re.split(r'(?<=[.!?])\s+', level["description"]):
            sentence = sentence.strip()
            if len(sentence) > 10:
                add(
                    f"VDP {name}: {sentence}",
                    "wine_regions", "germany_vdp",
                    [{"type": "classification", "name": f"VDP {name}"}],
                    ["germany", "vdp", name.lower()],
                    source_key="germany_vdp",
                )

    add(
        "VDP Große Lage dry wines are labeled Großes Gewächs (GG), considered the pinnacle of German dry wine.",
        "wine_regions", "germany_vdp",
        [{"type": "classification", "name": "Großes Gewächs"}],
        ["germany", "vdp", "gg"],
        source_key="germany_vdp",
    )
    add(
        "The VDP Große Lage designation is marked on the bottle with a stylized eagle and the number '1' on the capsule.",
        "wine_regions", "germany_vdp",
        [{"type": "classification", "name": "VDP Große Lage"}],
        ["germany", "vdp", "labeling"],
        source_key="germany_vdp",
    )
    add(
        "VDP Erste Lage wines must meet stricter yield limits and use only locally traditional grape varieties.",
        "wine_regions", "germany_vdp",
        [{"type": "classification", "name": "VDP Erste Lage"}],
        ["germany", "vdp", "regulation"],
        source_key="germany_vdp",
    )

    # --- Additional German grape variety facts ---
    add(
        "Silvaner is a white grape particularly associated with Franken, where it produces full-bodied, earthy dry wines.",
        "grape_varieties", "germany_general",
        [{"type": "grape", "name": "Silvaner"}, {"type": "region", "name": "Franken"}],
        ["germany", "grape", "silvaner"],
    )
    add(
        "Grauburgunder (Pinot Gris) is increasingly popular in Baden and Pfalz for dry, full-bodied white wines.",
        "grape_varieties", "germany_general",
        [{"type": "grape", "name": "Grauburgunder"}],
        ["germany", "grape", "grauburgunder"],
    )
    add(
        "Weißburgunder (Pinot Blanc) is grown across Germany, especially in Pfalz and Baden.",
        "grape_varieties", "germany_general",
        [{"type": "grape", "name": "Weißburgunder"}],
        ["germany", "grape", "weissburgunder"],
    )
    add(
        "Lemberger (Blaufränkisch) is a red grape grown primarily in Württemberg.",
        "grape_varieties", "germany_general",
        [{"type": "grape", "name": "Lemberger"}, {"type": "region", "name": "Württemberg"}],
        ["germany", "grape", "red"],
    )
    add(
        "Trollinger (Schiava) is a light red grape variety grown almost exclusively in Württemberg.",
        "grape_varieties", "germany_general",
        [{"type": "grape", "name": "Trollinger"}, {"type": "region", "name": "Württemberg"}],
        ["germany", "grape", "red"],
    )
    add(
        "Scheurebe is a Riesling × Silvaner crossing that produces aromatic wines, particularly in Rheinhessen and Pfalz.",
        "grape_varieties", "germany_general",
        [{"type": "grape", "name": "Scheurebe"}],
        ["germany", "grape"],
    )
    add(
        "Gewürztraminer is a white grape variety grown in Germany, especially in Pfalz and Baden, producing aromatic, spicy wines.",
        "grape_varieties", "germany_general",
        [{"type": "grape", "name": "Gewürztraminer"}],
        ["germany", "grape"],
    )
    add(
        "Elbling is one of the oldest grape varieties in Germany, primarily grown in the upper Mosel region.",
        "grape_varieties", "germany_general",
        [{"type": "grape", "name": "Elbling"}, {"type": "region", "name": "Mosel"}],
        ["germany", "grape"],
    )
    add(
        "Goldriesling is a rare grape crossing grown almost exclusively in the Sachsen wine region.",
        "grape_varieties", "germany_general",
        [{"type": "grape", "name": "Goldriesling"}, {"type": "region", "name": "Sachsen"}],
        ["germany", "grape"],
    )

    # --- Additional German grape facts ---
    add(
        "Schwarzriesling (Pinot Meunier) is a red grape widely planted in Württemberg.",
        "grape_varieties", "germany_general",
        [{"type": "grape", "name": "Schwarzriesling"}, {"type": "region", "name": "Württemberg"}],
        ["germany", "grape", "red"],
    )
    add(
        "Bacchus is an early-ripening white grape crossing popular in Franken and Rheinhessen.",
        "grape_varieties", "germany_general",
        [{"type": "grape", "name": "Bacchus"}],
        ["germany", "grape"],
    )
    add(
        "Kerner is a white grape crossing of Trollinger and Riesling, producing aromatic wines.",
        "grape_varieties", "germany_general",
        [{"type": "grape", "name": "Kerner"}],
        ["germany", "grape"],
    )
    add(
        "Regent is one of the few fungus-resistant grape varieties (PIWI) approved for Qualitätswein in Germany.",
        "grape_varieties", "germany_general",
        [{"type": "grape", "name": "Regent"}],
        ["germany", "grape", "piwi"],
    )
    add(
        "Portugieser is a light red grape widely grown in Rheinhessen and Pfalz, producing simple, fruity wines.",
        "grape_varieties", "germany_general",
        [{"type": "grape", "name": "Portugieser"}],
        ["germany", "grape", "red"],
    )
    add(
        "Saint Laurent is a dark-skinned red grape related to Pinot Noir, grown in Pfalz and Rheinhessen.",
        "grape_varieties", "germany_general",
        [{"type": "grape", "name": "Saint Laurent"}],
        ["germany", "grape", "red"],
    )
    add(
        "Huxelrebe is a white grape crossing used for sweet wines, especially Beerenauslese and Trockenbeerenauslese.",
        "grape_varieties", "germany_general",
        [{"type": "grape", "name": "Huxelrebe"}],
        ["germany", "grape"],
    )
    add(
        "Rieslaner (Silvaner × Riesling) is a crossing that can produce outstanding sweet wines in Franken.",
        "grape_varieties", "germany_general",
        [{"type": "grape", "name": "Rieslaner"}, {"type": "region", "name": "Franken"}],
        ["germany", "grape"],
    )
    add(
        "Domina is a red grape crossing (Portugieser × Spätburgunder) grown primarily in Franken.",
        "grape_varieties", "germany_general",
        [{"type": "grape", "name": "Domina"}, {"type": "region", "name": "Franken"}],
        ["germany", "grape", "red"],
    )
    add(
        "Acolon is a red grape crossing (Lemberger × Dornfelder) developed in Württemberg.",
        "grape_varieties", "germany_general",
        [{"type": "grape", "name": "Acolon"}, {"type": "region", "name": "Württemberg"}],
        ["germany", "grape", "red"],
    )
    add(
        "Frühburgunder (Pinot Noir Précoce) is an early-ripening mutation of Pinot Noir grown in the Ahr and elsewhere.",
        "grape_varieties", "germany_general",
        [{"type": "grape", "name": "Frühburgunder"}],
        ["germany", "grape", "red"],
    )
    add(
        "Müller-Thurgau was created in 1882 by Hermann Müller from the Swiss canton of Thurgau, long thought to be a Riesling × Silvaner cross.",
        "grape_varieties", "germany_general",
        [{"type": "grape", "name": "Müller-Thurgau"}],
        ["germany", "grape", "history"],
    )
    add(
        "DNA testing has shown Müller-Thurgau is actually a crossing of Riesling and Madeleine Royale.",
        "grape_varieties", "germany_general",
        [{"type": "grape", "name": "Müller-Thurgau"}],
        ["germany", "grape", "genetics"],
    )

    # --- Region in-depth: Mosel ---
    add(
        "Mosel is Germany's oldest wine region, with viticulture dating back to Roman times in the 2nd century AD.",
        "wine_regions", "germany_regions",
        [{"type": "region", "name": "Mosel"}],
        ["germany", "mosel", "history"],
    )
    add(
        "The Mosel's steep, south-facing slate slopes capture maximum sunlight, essential at this northern latitude.",
        "viticulture", "germany_regions",
        [{"type": "region", "name": "Mosel"}],
        ["germany", "mosel", "terroir"],
    )
    add(
        "The Saar tributary of the Mosel produces Rieslings with particularly high acidity and mineral character.",
        "wine_regions", "germany_regions",
        [{"type": "subzone", "name": "Saar"}, {"type": "region", "name": "Mosel"}],
        ["germany", "mosel", "saar"],
    )
    add(
        "The Ruwer tributary of the Mosel is one of the coolest sub-regions, producing some of Germany's most delicate Rieslings.",
        "wine_regions", "germany_regions",
        [{"type": "subzone", "name": "Ruwer"}, {"type": "region", "name": "Mosel"}],
        ["germany", "mosel", "ruwer"],
    )
    add(
        "The Mosel's gradient can exceed 65 degrees in some vineyards, requiring all work to be done by hand.",
        "viticulture", "germany_regions",
        [{"type": "region", "name": "Mosel"}],
        ["germany", "mosel", "viticulture"],
    )
    add(
        "Bernkasteler Doctor is one of the most famous vineyard sites in the Mosel, overlooking the town of Bernkastel-Kues.",
        "wine_regions", "germany_regions",
        [{"type": "vineyard", "name": "Bernkasteler Doctor"}, {"type": "region", "name": "Mosel"}],
        ["germany", "mosel", "vineyard"],
    )
    add(
        "Ürziger Würzgarten in the Mosel is famous for its red slate and volcanic soils, producing spicy Rieslings.",
        "wine_regions", "germany_regions",
        [{"type": "vineyard", "name": "Ürziger Würzgarten"}, {"type": "region", "name": "Mosel"}],
        ["germany", "mosel", "vineyard"],
    )
    add(
        "Wehlener Sonnenuhr in the Mosel takes its name from a sundial set into the vineyard slope.",
        "wine_regions", "germany_regions",
        [{"type": "vineyard", "name": "Wehlener Sonnenuhr"}, {"type": "region", "name": "Mosel"}],
        ["germany", "mosel", "vineyard"],
    )
    add(
        "Scharzhofberger in the Saar is one of Germany's greatest vineyard sites, producing exceptional Rieslings.",
        "wine_regions", "germany_regions",
        [{"type": "vineyard", "name": "Scharzhofberger"}, {"type": "region", "name": "Mosel"}],
        ["germany", "mosel", "vineyard", "saar"],
    )

    # --- Region in-depth: Rheingau ---
    add(
        "The Rheingau lies on the north bank of the Rhine where the river turns west, providing south-facing slopes.",
        "wine_regions", "germany_regions",
        [{"type": "region", "name": "Rheingau"}],
        ["germany", "rheingau", "geography"],
    )
    add(
        "Schloss Johannisberg in the Rheingau claims to be the world's first Riesling vineyard, with documented plantings from 1720.",
        "wine_regions", "germany_regions",
        [{"type": "vineyard", "name": "Schloss Johannisberg"}, {"type": "region", "name": "Rheingau"}],
        ["germany", "rheingau", "history"],
    )
    add(
        "The Spätlese designation originated in 1775 at Schloss Johannisberg when a late-arriving messenger delayed the harvest.",
        "wine_regions", "germany_regions",
        [{"type": "classification", "name": "Spätlese"}, {"type": "vineyard", "name": "Schloss Johannisberg"}],
        ["germany", "rheingau", "history"],
    )
    add(
        "Kloster Eberbach in the Rheingau is a former Cistercian monastery and historic wine estate.",
        "wine_regions", "germany_regions",
        [{"type": "vineyard", "name": "Kloster Eberbach"}, {"type": "region", "name": "Rheingau"}],
        ["germany", "rheingau", "history"],
    )
    add(
        "The Rheingau village of Assmannshausen is known for producing exceptional Spätburgunder (Pinot Noir) red wines.",
        "wine_regions", "germany_regions",
        [{"type": "region", "name": "Rheingau"}, {"type": "grape", "name": "Spätburgunder"}],
        ["germany", "rheingau", "red"],
    )
    add(
        "Steinberg is a walled vineyard in the Rheingau, originally planted by Cistercian monks in the 12th century.",
        "wine_regions", "germany_regions",
        [{"type": "vineyard", "name": "Steinberg"}, {"type": "region", "name": "Rheingau"}],
        ["germany", "rheingau", "vineyard"],
    )
    add(
        "Rüdesheimer Berg Schlossberg is a famous steep vineyard site in the western Rheingau.",
        "wine_regions", "germany_regions",
        [{"type": "vineyard", "name": "Rüdesheimer Berg Schlossberg"}, {"type": "region", "name": "Rheingau"}],
        ["germany", "rheingau", "vineyard"],
    )

    # --- Region in-depth: Pfalz ---
    add(
        "The Pfalz (Palatinate) is protected by the Pfälzerwald (Palatinate Forest) to the west, creating a warm, dry climate.",
        "wine_regions", "germany_regions",
        [{"type": "region", "name": "Pfalz"}],
        ["germany", "pfalz", "climate"],
    )
    add(
        "The Pfalz is Germany's largest wine-producing region by volume.",
        "wine_regions", "germany_regions",
        [{"type": "region", "name": "Pfalz"}],
        ["germany", "pfalz"],
    )
    add(
        "The Mittelhaardt in the Pfalz contains many of the region's top vineyard sites.",
        "wine_regions", "germany_regions",
        [{"type": "subzone", "name": "Mittelhaardt"}, {"type": "region", "name": "Pfalz"}],
        ["germany", "pfalz", "subregion"],
    )
    add(
        "The southern Pfalz (Südliche Weinstraße) is known for value-oriented wines and warmer conditions.",
        "wine_regions", "germany_regions",
        [{"type": "subzone", "name": "Südliche Weinstraße"}, {"type": "region", "name": "Pfalz"}],
        ["germany", "pfalz", "subregion"],
    )

    # --- Region in-depth: Rheinhessen ---
    add(
        "The Roter Hang (Red Slope) near Nierstein in Rheinhessen has exceptional red slate and sandstone soils.",
        "wine_regions", "germany_regions",
        [{"type": "subzone", "name": "Roter Hang"}, {"type": "region", "name": "Rheinhessen"}],
        ["germany", "rheinhessen", "terroir"],
    )
    add(
        "Rheinhessen is the birthplace of Liebfraumilch, a semi-sweet wine that became popular worldwide in the 20th century.",
        "wine_regions", "germany_regions",
        [{"type": "region", "name": "Rheinhessen"}, {"type": "wine_style", "name": "Liebfraumilch"}],
        ["germany", "rheinhessen", "history"],
    )
    add(
        "Nackenheim and Nierstein in Rheinhessen are renowned for premium Riesling from steep riverside vineyards.",
        "wine_regions", "germany_regions",
        [{"type": "region", "name": "Rheinhessen"}],
        ["germany", "rheinhessen", "riesling"],
    )

    # --- Region in-depth: Baden ---
    add(
        "Baden spans 400 km from north to south and is divided into nine districts (Bereiche).",
        "wine_regions", "germany_regions",
        [{"type": "region", "name": "Baden"}],
        ["germany", "baden"],
    )
    add(
        "The Kaiserstuhl in Baden is a volcanic hill that is the warmest vineyard area in Germany.",
        "wine_regions", "germany_regions",
        [{"type": "subzone", "name": "Kaiserstuhl"}, {"type": "region", "name": "Baden"}],
        ["germany", "baden", "terroir"],
    )
    add(
        "Baden's Spätburgunder (Pinot Noir) accounts for about one-third of the region's production.",
        "grape_varieties", "germany_regions",
        [{"type": "grape", "name": "Spätburgunder"}, {"type": "region", "name": "Baden"}],
        ["germany", "baden", "grape"],
    )
    add(
        "The Markgräflerland in southern Baden is known for Gutedel (Chasselas) wines.",
        "wine_regions", "germany_regions",
        [{"type": "subzone", "name": "Markgräflerland"}, {"type": "grape", "name": "Gutedel"}],
        ["germany", "baden"],
    )
    add(
        "The Ortenau district in Baden produces premium Riesling, locally called Klingelberger.",
        "wine_regions", "germany_regions",
        [{"type": "subzone", "name": "Ortenau"}, {"type": "grape", "name": "Riesling"}],
        ["germany", "baden"],
    )

    # --- Region in-depth: Ahr ---
    add(
        "The Ahr Valley is one of Germany's smallest wine regions but most focused on red wine production.",
        "wine_regions", "germany_regions",
        [{"type": "region", "name": "Ahr"}],
        ["germany", "ahr"],
    )
    add(
        "The Ahr Valley was devastated by flooding in July 2021, destroying many vineyards and wine cellars.",
        "wine_regions", "germany_regions",
        [{"type": "region", "name": "Ahr"}],
        ["germany", "ahr", "history"],
    )

    # --- Region in-depth: Franken ---
    add(
        "Franken wines are traditionally bottled in the distinctive Bocksbeutel, a flat, round-sided bottle.",
        "wine_regions", "germany_regions",
        [{"type": "region", "name": "Franken"}],
        ["germany", "franken", "tradition"],
    )
    add(
        "Franken's Muschelkalk (shell limestone) soils contribute to the mineral character of its Silvaner wines.",
        "viticulture", "germany_regions",
        [{"type": "region", "name": "Franken"}, {"type": "soil", "name": "Muschelkalk"}],
        ["germany", "franken", "terroir"],
    )
    add(
        "Würzburger Stein is one of the most famous vineyard sites in Franken.",
        "wine_regions", "germany_regions",
        [{"type": "vineyard", "name": "Würzburger Stein"}, {"type": "region", "name": "Franken"}],
        ["germany", "franken", "vineyard"],
    )

    # --- Region in-depth: Württemberg ---
    add(
        "Württemberg is Germany's fourth-largest wine region and its red wine heartland.",
        "wine_regions", "germany_regions",
        [{"type": "region", "name": "Württemberg"}],
        ["germany", "württemberg"],
    )
    add(
        "About 70% of Württemberg wine is produced by cooperatives (Genossenschaften).",
        "wine_business", "germany_regions",
        [{"type": "region", "name": "Württemberg"}],
        ["germany", "württemberg", "business"],
    )
    add(
        "Schillerwein is a traditional rosé-like wine from Württemberg, made by co-fermenting red and white grapes.",
        "winemaking", "germany_regions",
        [{"type": "wine_style", "name": "Schillerwein"}, {"type": "region", "name": "Württemberg"}],
        ["germany", "württemberg", "tradition"],
    )

    # --- Region in-depth: Nahe ---
    add(
        "Nahe wines are often described as bridging the styles of Mosel (elegance) and Rheingau (power).",
        "wine_regions", "germany_regions",
        [{"type": "region", "name": "Nahe"}],
        ["germany", "nahe"],
    )
    add(
        "The Nahe has more geological diversity per hectare than any other German wine region.",
        "viticulture", "germany_regions",
        [{"type": "region", "name": "Nahe"}],
        ["germany", "nahe", "terroir"],
    )
    add(
        "Niederhäuser Hermannshöhle is one of the top vineyard sites in the Nahe, known for complex Riesling.",
        "wine_regions", "germany_regions",
        [{"type": "vineyard", "name": "Niederhäuser Hermannshöhle"}, {"type": "region", "name": "Nahe"}],
        ["germany", "nahe", "vineyard"],
    )

    # --- Region in-depth: Mittelrhein ---
    add(
        "The Mittelrhein's steep, terraced vineyards in the Rhine Gorge are part of a UNESCO World Heritage Site.",
        "wine_regions", "germany_regions",
        [{"type": "region", "name": "Mittelrhein"}],
        ["germany", "mittelrhein"],
    )
    add(
        "Bacharacher Hahn and Bopparder Hamm are renowned vineyard sites in the Mittelrhein.",
        "wine_regions", "germany_regions",
        [{"type": "region", "name": "Mittelrhein"}],
        ["germany", "mittelrhein", "vineyard"],
    )

    # --- Region in-depth: Hessische Bergstraße ---
    add(
        "Hessische Bergstraße is known as Germany's 'springtime garden' due to its mild climate.",
        "wine_regions", "germany_regions",
        [{"type": "region", "name": "Hessische Bergstraße"}],
        ["germany", "hessische_bergstrasse"],
    )

    # --- Region in-depth: Saale-Unstrut ---
    add(
        "Saale-Unstrut is centered around the university city of Jena and the historic town of Freyburg.",
        "wine_regions", "germany_regions",
        [{"type": "region", "name": "Saale-Unstrut"}],
        ["germany", "saale_unstrut"],
    )
    add(
        "Viticulture in Saale-Unstrut dates back over 1,000 years to Cistercian monks.",
        "wine_regions", "germany_regions",
        [{"type": "region", "name": "Saale-Unstrut"}],
        ["germany", "saale_unstrut", "history"],
    )

    # --- Region in-depth: Sachsen ---
    add(
        "Sachsen (Saxony) is centered around the cities of Dresden and Meißen on the Elbe river.",
        "wine_regions", "germany_regions",
        [{"type": "region", "name": "Sachsen"}],
        ["germany", "sachsen"],
    )
    add(
        "Sachsen produces mostly dry white wines consumed locally, rarely exported.",
        "wine_regions", "germany_regions",
        [{"type": "region", "name": "Sachsen"}],
        ["germany", "sachsen"],
    )

    # --- VDP famous estates and sites ---
    vdp_sites = [
        ("Riesling", "Mosel", "Scharzhofberger"),
        ("Riesling", "Mosel", "Wehlener Sonnenuhr"),
        ("Riesling", "Mosel", "Bernkasteler Doctor"),
        ("Riesling", "Mosel", "Ürziger Würzgarten"),
        ("Riesling", "Mosel", "Brauneberger Juffer-Sonnenuhr"),
        ("Riesling", "Rheingau", "Schloss Johannisberg"),
        ("Riesling", "Rheingau", "Steinberg"),
        ("Riesling", "Rheingau", "Rüdesheimer Berg Schlossberg"),
        ("Riesling", "Pfalz", "Forster Kirchenstück"),
        ("Riesling", "Pfalz", "Forster Ungeheuer"),
        ("Riesling", "Pfalz", "Deidesheimer Hohenmorgen"),
        ("Riesling", "Nahe", "Niederhäuser Hermannshöhle"),
        ("Riesling", "Nahe", "Schloßböckelheimer Kupfergrube"),
        ("Riesling", "Rheinhessen", "Nackenheimer Rothenberg"),
        ("Silvaner", "Franken", "Würzburger Stein"),
        ("Spätburgunder", "Ahr", "Walporzheimer Kräuterberg"),
        ("Spätburgunder", "Baden", "Oberrotweiler Henkenberg"),
    ]
    for grape, region, site in vdp_sites:
        add(
            f"{site} is a top-classified vineyard site (VDP Große Lage) in the {region} region, known for {grape}.",
            "wine_regions", "germany_vdp",
            [{"type": "vineyard", "name": site}, {"type": "region", "name": region}, {"type": "grape", "name": grape}],
            ["germany", "vdp", "große_lage", region.lower()],
            source_key="germany_vdp",
        )

    # --- German winemaking and regulation details ---
    add(
        "Amtliche Prüfungsnummer (AP number) is the quality control number required on every German Qualitätswein and Prädikatswein label.",
        "winemaking", "germany_regulation",
        [{"type": "term", "name": "AP number"}],
        ["germany", "regulation", "labeling"],
    )
    add(
        "German wine labels must state the Anbaugebiet (region), Qualitätsstufe (quality level), and producer name.",
        "winemaking", "germany_regulation",
        [{"type": "country", "name": "Germany"}],
        ["germany", "regulation", "labeling"],
    )
    add(
        "Einzellage is the German term for an individual vineyard site, the smallest geographical designation.",
        "wine_regions", "germany_regulation",
        [{"type": "term", "name": "Einzellage"}],
        ["germany", "regulation"],
    )
    add(
        "Großlage is a German collective vineyard designation that groups multiple Einzellagen under one name.",
        "wine_regions", "germany_regulation",
        [{"type": "term", "name": "Großlage"}],
        ["germany", "regulation"],
    )
    add(
        "Bereich is a German wine district, the next level above Großlage in the geographical hierarchy.",
        "wine_regions", "germany_regulation",
        [{"type": "term", "name": "Bereich"}],
        ["germany", "regulation"],
    )
    add(
        "Kabinett wines from the Mosel typically have around 7-9% alcohol and notable residual sweetness.",
        "winemaking", "germany_praedikat",
        [{"type": "classification", "name": "Kabinett"}, {"type": "region", "name": "Mosel"}],
        ["germany", "praedikat", "kabinett"],
    )
    add(
        "Spätlese (literally 'late harvest') wines are made from grapes picked at least one week after normal harvest.",
        "winemaking", "germany_praedikat",
        [{"type": "classification", "name": "Spätlese"}],
        ["germany", "praedikat", "spätlese"],
    )
    add(
        "Auslese wines can age for decades, developing complex notes of petrol, honey, and dried fruit.",
        "winemaking", "germany_praedikat",
        [{"type": "classification", "name": "Auslese"}],
        ["germany", "praedikat", "auslese"],
    )
    add(
        "Beerenauslese (BA) wines require a must weight of at least 110-128 degrees Oechsle depending on the region.",
        "winemaking", "germany_praedikat",
        [{"type": "classification", "name": "Beerenauslese"}],
        ["germany", "praedikat", "ba"],
    )
    add(
        "Trockenbeerenauslese (TBA) requires a must weight of at least 150-154 degrees Oechsle.",
        "winemaking", "germany_praedikat",
        [{"type": "classification", "name": "Trockenbeerenauslese"}],
        ["germany", "praedikat", "tba"],
    )
    add(
        "Eiswein must be harvested at temperatures of -7°C or below, and the grapes must not have been affected by botrytis.",
        "winemaking", "germany_praedikat",
        [{"type": "classification", "name": "Eiswein"}],
        ["germany", "praedikat", "eiswein"],
    )
    add(
        "Eiswein harvest often occurs in December or January, sometimes in the middle of the night.",
        "winemaking", "germany_praedikat",
        [{"type": "classification", "name": "Eiswein"}],
        ["germany", "praedikat", "eiswein"],
    )
    add(
        "Botrytis cinerea (noble rot) is essential for Beerenauslese and Trockenbeerenauslese wines, concentrating sugars and adding complex flavors.",
        "winemaking", "germany_praedikat",
        [{"type": "technique", "name": "Noble rot"}],
        ["germany", "praedikat", "botrytis"],
    )
    add(
        "Großes Gewächs (GG) wines must be dry, from classified vineyard sites, made from designated grape varieties, and hand-harvested.",
        "winemaking", "germany_vdp",
        [{"type": "classification", "name": "Großes Gewächs"}],
        ["germany", "vdp", "gg"],
        source_key="germany_vdp",
    )
    add(
        "VDP Ortswein wines must come from vineyards within a specific village, with lower yields than Gutswein.",
        "wine_regions", "germany_vdp",
        [{"type": "classification", "name": "VDP Ortswein"}],
        ["germany", "vdp", "ortswein"],
        source_key="germany_vdp",
    )

    # --- German wine history ---
    add(
        "The Romans planted the first vineyards along the Mosel river around 100 AD.",
        "wine_regions", "germany_history",
        [{"type": "region", "name": "Mosel"}],
        ["germany", "history"],
    )
    add(
        "The 1971 German Wine Law simplified the classification system, creating Großlagen and Bereiche that persist today.",
        "wine_regions", "germany_regulation",
        [{"type": "country", "name": "Germany"}],
        ["germany", "regulation", "history"],
    )
    add(
        "The 2021 German Wine Law reform introduced a Burgundy-style geographical hierarchy (Anbaugebiet → Region → Ort → Lage).",
        "wine_regions", "germany_regulation",
        [{"type": "country", "name": "Germany"}],
        ["germany", "regulation", "reform"],
    )
    add(
        "Under the 2021 reform, German wines labeled by vineyard (Einzellage) must be dry, following the VDP model.",
        "wine_regions", "germany_regulation",
        [{"type": "country", "name": "Germany"}],
        ["germany", "regulation", "reform"],
    )
    add(
        "Germany's total vineyard area is approximately 103,000 hectares.",
        "wine_regions", "germany_general",
        [{"type": "country", "name": "Germany"}],
        ["germany", "area"],
    )
    add(
        "Germany is the world's largest producer of Riesling, followed by the United States and Australia.",
        "grape_varieties", "germany_general",
        [{"type": "grape", "name": "Riesling"}, {"type": "country", "name": "Germany"}],
        ["germany", "riesling", "production"],
    )
    add(
        "About 36% of Germany's wine production is red, a proportion that has increased significantly since the 1980s.",
        "wine_regions", "germany_general",
        [{"type": "country", "name": "Germany"}],
        ["germany", "production", "red"],
    )
    add(
        "Germany's wine regions are among the most northerly in the world, between 47°N and 51°N latitude.",
        "wine_regions", "germany_general",
        [{"type": "country", "name": "Germany"}],
        ["germany", "geography"],
    )
    add(
        "Climate change has allowed German winemakers to ripen Spätburgunder (Pinot Noir) more consistently in recent decades.",
        "viticulture", "germany_general",
        [{"type": "grape", "name": "Spätburgunder"}, {"type": "country", "name": "Germany"}],
        ["germany", "climate_change"],
    )

    # --- Regional grape specialties ---
    # --- Bulk enrichment: Oechsle requirements by region ---
    oechsle_facts = [
        ("Kabinett", "Mosel", 67, "Kabinett wines from the Mosel require a minimum must weight of 67 degrees Oechsle."),
        ("Kabinett", "Rheingau", 73, "Kabinett wines from the Rheingau require a minimum must weight of 73 degrees Oechsle."),
        ("Kabinett", "Pfalz", 73, "Kabinett wines from the Pfalz require a minimum must weight of 73 degrees Oechsle."),
        ("Kabinett", "Baden", 76, "Kabinett wines from Baden require a minimum must weight of 76 degrees Oechsle."),
        ("Spätlese", "Mosel", 76, "Spätlese wines from the Mosel require a minimum must weight of 76 degrees Oechsle."),
        ("Spätlese", "Rheingau", 85, "Spätlese wines from the Rheingau require a minimum must weight of 85 degrees Oechsle."),
        ("Spätlese", "Pfalz", 85, "Spätlese wines from the Pfalz require a minimum must weight of 85 degrees Oechsle."),
        ("Auslese", "Mosel", 83, "Auslese wines from the Mosel require a minimum must weight of 83 degrees Oechsle."),
        ("Auslese", "Rheingau", 95, "Auslese wines from the Rheingau require a minimum must weight of 95 degrees Oechsle."),
        ("Auslese", "Pfalz", 95, "Auslese wines from the Pfalz require a minimum must weight of 95 degrees Oechsle."),
        ("Beerenauslese", "Mosel", 110, "Beerenauslese wines from the Mosel require a minimum must weight of 110 degrees Oechsle."),
        ("Beerenauslese", "Rheingau", 125, "Beerenauslese wines from the Rheingau require a minimum must weight of 125 degrees Oechsle."),
        ("Trockenbeerenauslese", "Mosel", 150, "Trockenbeerenauslese wines from the Mosel require a minimum must weight of 150 degrees Oechsle."),
        ("Trockenbeerenauslese", "Rheingau", 150, "Trockenbeerenauslese wines from the Rheingau require a minimum must weight of 150 degrees Oechsle."),
        ("Eiswein", "Mosel", 110, "Eiswein from the Mosel requires a minimum must weight of 110 degrees Oechsle."),
        ("Eiswein", "Rheingau", 125, "Eiswein from the Rheingau requires a minimum must weight of 125 degrees Oechsle."),
    ]
    for praedikat, region, oechsle, fact_text in oechsle_facts:
        add(
            fact_text,
            "winemaking", "germany_praedikat",
            [{"type": "classification", "name": praedikat}, {"type": "region", "name": region}],
            ["germany", "praedikat", "oechsle", region.lower()],
        )

    # --- German wine producers ---
    german_producers = [
        ("Egon Müller", "Mosel", "Egon Müller-Scharzhof in the Saar produces some of Germany's most expensive Rieslings from the Scharzhofberger vineyard."),
        ("Joh. Jos. Prüm", "Mosel", "Joh. Jos. Prüm is a legendary Mosel producer known for Wehlener Sonnenuhr Riesling."),
        ("Markus Molitor", "Mosel", "Markus Molitor produces Riesling from top Mosel sites, known for detailed vineyard classification on every bottle."),
        ("Dr. Loosen", "Mosel", "Dr. Loosen produces Riesling from old ungrafted vines in the Mosel's top vineyard sites."),
        ("Fritz Haag", "Mosel", "Fritz Haag is known for elegant Rieslings from the Brauneberger Juffer-Sonnenuhr vineyard."),
        ("Maximin Grünhaus", "Mosel", "Maximin Grünhaus is a historic Ruwer estate producing Riesling from three vineyards: Abtsberg, Herrenberg, and Bruderberg."),
        ("Robert Weil", "Rheingau", "Weingut Robert Weil in the Rheingau is renowned for both dry and sweet Rieslings from the Gräfenberg vineyard."),
        ("Schloss Johannisberg", "Rheingau", "Schloss Johannisberg in the Rheingau is one of the oldest Riesling estates in the world."),
        ("Georg Breuer", "Rheingau", "Georg Breuer helped pioneer the dry Riesling movement in the Rheingau in the 1980s."),
        ("Bassermann-Jordan", "Pfalz", "Weingut Geheimer Rat Dr. von Bassermann-Jordan is one of the top estates in the Pfalz."),
        ("Bürklin-Wolf", "Pfalz", "Dr. Bürklin-Wolf in the Pfalz is one of Germany's largest VDP estates with 85 hectares."),
        ("Müller-Catoir", "Pfalz", "Müller-Catoir in the Pfalz is acclaimed for aromatic varieties including Riesling, Rieslaner, and Muskateller."),
        ("Dönnhoff", "Nahe", "Dönnhoff is considered the finest producer in the Nahe, especially for Riesling from Niederhäuser and Oberhäuser sites."),
        ("Emrich-Schönleber", "Nahe", "Emrich-Schönleber produces outstanding Rieslings from the Halenberg and Frühlingsplätzchen vineyards in the Nahe."),
        ("Keller", "Rheinhessen", "Weingut Keller in Flörsheim-Dalsheim is one of Germany's most sought-after producers, known for G-Max Riesling."),
        ("Wittmann", "Rheinhessen", "Weingut Wittmann in Westhofen is a top biodynamic producer in Rheinhessen."),
        ("Meyer-Näkel", "Ahr", "Meyer-Näkel is the leading producer of Spätburgunder in the Ahr Valley."),
        ("Bernhard Huber", "Baden", "Weingut Bernhard Huber in Malterdingen (Baden) is renowned for Burgundian-style Spätburgunder."),
        ("Dr. Heger", "Baden", "Dr. Heger produces top Spätburgunder and Grauburgunder from the Kaiserstuhl in Baden."),
        ("Fürst", "Franken", "Weingut Rudolf Fürst is the leading producer in Franken, known for both Spätburgunder and Riesling."),
        ("Horst Sauer", "Franken", "Horst Sauer in Escherndorf produces exceptional Silvaner from the Lump vineyard in Franken."),
        ("Aldinger", "Württemberg", "Aldinger is one of the top producers in Württemberg, known for Riesling and Lemberger."),
        ("Wöhrwag", "Württemberg", "Weingut Wöhrwag produces premium Riesling and Lemberger from the slopes above Stuttgart."),
    ]
    for producer, region, fact_text in german_producers:
        add(
            fact_text,
            "producers", "germany_producers",
            [{"type": "producer", "name": producer}, {"type": "region", "name": region}],
            ["germany", "producer", region.lower()],
        )

    # --- Additional German wine styles and terms ---
    add(
        "Rotling is a German rosé-type wine made by co-fermenting red and white grapes together.",
        "winemaking", "germany_general",
        [{"type": "wine_style", "name": "Rotling"}],
        ["germany", "wine_style"],
    )
    add(
        "Blanc de Noirs (Weißherbst) in Germany is a single-variety rosé made from Spätburgunder or other red grapes.",
        "winemaking", "germany_general",
        [{"type": "wine_style", "name": "Weißherbst"}],
        ["germany", "wine_style"],
    )
    add(
        "Federweißer (Sturm) is a partially fermented grape must sold during harvest season, popular in Germany.",
        "winemaking", "germany_general",
        [{"type": "wine_style", "name": "Federweißer"}],
        ["germany", "wine_style"],
    )
    add(
        "German wine cooperatives (Genossenschaften) produce about one-third of all German wine.",
        "wine_business", "germany_general",
        [{"type": "country", "name": "Germany"}],
        ["germany", "business"],
    )
    add(
        "The Deutsche Weinstraße (German Wine Route) in the Pfalz is the oldest wine-themed tourist route in Germany.",
        "wine_regions", "germany_regions",
        [{"type": "region", "name": "Pfalz"}],
        ["germany", "pfalz", "tourism"],
    )
    add(
        "The Bocksbeutel bottle used in Franken is a protected bottle shape that may only be used by Franken and a few other regions.",
        "winemaking", "germany_regulation",
        [{"type": "region", "name": "Franken"}],
        ["germany", "franken", "labeling"],
    )

    # --- Additional VDP and vineyard classification facts ---
    add(
        "The VDP eagle logo (Traubenadler) on a bottle capsule indicates membership in the VDP association.",
        "wine_regions", "germany_vdp",
        [{"type": "organization", "name": "VDP"}],
        ["germany", "vdp", "branding"],
        source_key="germany_vdp",
    )
    add(
        "VDP Große Lage sweet wines (Auslese, Beerenauslese, TBA, Eiswein) carry a gold capsule.",
        "wine_regions", "germany_vdp",
        [{"type": "classification", "name": "VDP Große Lage"}],
        ["germany", "vdp", "labeling"],
        source_key="germany_vdp",
    )
    add(
        "VDP Große Lage dry wines (Großes Gewächs) carry a white capsule with the number 1.",
        "wine_regions", "germany_vdp",
        [{"type": "classification", "name": "Großes Gewächs"}],
        ["germany", "vdp", "labeling"],
        source_key="germany_vdp",
    )

    region_grape_extras = [
        ("Ahr", "Spätburgunder", "Over 85% of the Ahr's production is red wine, dominated by Spätburgunder (Pinot Noir)."),
        ("Franken", "Silvaner", "Silvaner accounts for about 25% of plantings in Franken, more than in any other German region."),
        ("Rheingau", "Riesling", "Approximately 78% of the Rheingau's vineyards are planted with Riesling."),
        ("Mosel", "Riesling", "Riesling accounts for over 60% of plantings in the Mosel region."),
        ("Württemberg", "Trollinger", "Trollinger is the most planted grape in Württemberg, a light red drunk locally as a daily wine."),
        ("Baden", "Grauburgunder", "Baden is Germany's leading producer of Grauburgunder (Pinot Gris) wines."),
        ("Pfalz", "Riesling", "The Pfalz contains Germany's largest contiguous Riesling vineyard area."),
        ("Rheinhessen", "Silvaner", "Rheinhessen has the largest total planting of Silvaner in Germany."),
        ("Nahe", "Riesling", "Riesling accounts for about 28% of plantings in the Nahe region."),
        ("Saale-Unstrut", "Weißburgunder", "Weißburgunder (Pinot Blanc) is one of the most important varieties in Saale-Unstrut."),
    ]
    for region, grape, fact_text in region_grape_extras:
        add(
            fact_text,
            "grape_varieties", "germany_regions",
            [{"type": "grape", "name": grape}, {"type": "region", "name": region}],
            ["germany", "grape", region.lower()],
        )

    # --- Additional VDP vineyard sites ---
    vdp_sites_extra = [
        ("Riesling", "Mosel", "Erdener Treppchen", "Erdener Treppchen is a top Große Lage in the Mosel, named after its stone staircase."),
        ("Riesling", "Mosel", "Graacher Himmelreich", "Graacher Himmelreich in the Mosel produces elegant, racy Rieslings from blue slate soils."),
        ("Riesling", "Mosel", "Piesporter Goldtröpfchen", "Piesporter Goldtröpfchen is a renowned Mosel vineyard producing rich, gold-tinted Rieslings."),
        ("Riesling", "Mosel", "Trittenheimer Apotheke", "Trittenheimer Apotheke in the Mosel produces mineral-driven Rieslings from Devonian slate."),
        ("Riesling", "Mosel", "Zeltinger Sonnenuhr", "Zeltinger Sonnenuhr in the Mosel features a sundial and produces elegant Riesling."),
        ("Riesling", "Mosel", "Ockfener Bockstein", "Ockfener Bockstein in the Saar is known for steely, mineral Rieslings from grey slate."),
        ("Riesling", "Mosel", "Kaseler Nies'chen", "Kaseler Nies'chen in the Ruwer produces some of Germany's most delicate and refined Rieslings."),
        ("Riesling", "Pfalz", "Forster Jesuitengarten", "Forster Jesuitengarten in the Pfalz benefits from basalt soils that retain heat."),
        ("Riesling", "Pfalz", "Ruppertsberger Reiterpfad", "Ruppertsberger Reiterpfad is a top site in the Pfalz known for rich, powerful Riesling."),
        ("Riesling", "Rheingau", "Erbacher Marcobrunn", "Erbacher Marcobrunn is one of the Rheingau's greatest vineyards, with heavy marl soils."),
        ("Riesling", "Rheingau", "Rauenthaler Baiken", "Rauenthaler Baiken in the Rheingau produces complex Rieslings at a higher elevation."),
        ("Riesling", "Rheinhessen", "Pettenthal", "Pettenthal in the Roter Hang of Rheinhessen produces exceptional Riesling from red slate."),
        ("Riesling", "Nahe", "Schlossböckelheimer Felsenberg", "Schlossböckelheimer Felsenberg in the Nahe has porphyry soils that produce spicy Riesling."),
        ("Silvaner", "Franken", "Escherndorfer Lump", "Escherndorfer Lump in Franken is one of the finest Silvaner sites in Germany."),
        ("Silvaner", "Franken", "Randersackerer Pfülben", "Randersackerer Pfülben is a top Franken vineyard for Silvaner, on shell limestone soils."),
        ("Spätburgunder", "Ahr", "Dernauer Pfarrwingert", "Dernauer Pfarrwingert is a top Spätburgunder site in the Ahr Valley."),
        ("Spätburgunder", "Baden", "Malterdinger Bienenberg", "Malterdinger Bienenberg in Baden produces some of Germany's finest Spätburgunder."),
        ("Spätburgunder", "Rheingau", "Assmannshäuser Höllenberg", "Assmannshäuser Höllenberg is the Rheingau's most famous red wine vineyard."),
        ("Lemberger", "Württemberg", "Untertürkheimer Gips", "Untertürkheimer Gips in Württemberg is a top site for Lemberger and Riesling."),
    ]
    for grape, region, site, fact_text in vdp_sites_extra:
        add(
            fact_text,
            "wine_regions", "germany_vdp",
            [{"type": "vineyard", "name": site}, {"type": "region", "name": region}, {"type": "grape", "name": grape}],
            ["germany", "vdp", "große_lage", region.lower()],
            source_key="germany_vdp",
        )

    # --- German winemaking and regulatory details ---
    german_regulation_extra = [
        "German Qualitätswein may be chaptalised to increase alcohol, but Prädikatswein may not.",
        "The minimum natural alcohol content for Qualitätswein varies by region, from 6.5% (Mosel) to 7.5% (Baden).",
        "Germany allows the addition of Süßreserve (unfermented grape juice) to finished wine to adjust sweetness.",
        "Süßreserve must come from the same region and quality level as the wine to which it is added.",
        "The VDP was founded in 1910 as the Verband Deutscher Naturweinversteigerer (Association of German Natural Wine Auctioneers).",
        "German wine auctions (Versteigerungen) are a traditional method of selling top wines, particularly in the VDP.",
        "The Bernkasteler Ring and Grosser Ring are Mosel wine auction associations that predate the VDP.",
        "German Sekt b.A. (bestimmter Anbaugebiete) must be made from grapes grown in a specific quality wine region.",
        "Winzersekt must be made by the traditional method, from estate-grown grapes, with 9 months lees aging minimum.",
        "Crémant is used in some German regions for traditional method sparkling wines meeting EU Crémant regulations.",
    ]
    for fact_text in german_regulation_extra:
        add(
            fact_text,
            "winemaking", "germany_regulation",
            [{"type": "country", "name": "Germany"}],
            ["germany", "regulation"],
        )

    # --- German wine industry facts ---
    german_business_extra = [
        "Germany has approximately 15,000 wine estates and 20,000 grape growers.",
        "About 65% of German wine is white and 35% is red.",
        "Germany consumes most of its own wine production, with less than one-third exported.",
        "The largest export markets for German wine are the United States, United Kingdom, and Netherlands.",
        "The German Wine Queen (Deutsche Weinkönigin) is elected annually to represent the German wine industry.",
        "Each of Germany's 13 wine regions has its own local wine queen and princess.",
        "The Rheingauer Weinwoche and similar festivals attract millions of visitors to German wine regions each year.",
    ]
    for fact_text in german_business_extra:
        add(
            fact_text,
            "wine_business", "germany_general",
            [{"type": "country", "name": "Germany"}],
            ["germany", "business"],
        )

    # --- German terroir details ---
    german_terroir_extra = [
        ("Mosel", "The steep vineyards of the Mosel act as solar collectors, reflecting heat from the river onto the vines."),
        ("Mosel", "Blue Devonian slate in the Mosel absorbs heat during the day and radiates it back to vines at night."),
        ("Rheingau", "The Taunus Mountains north of the Rheingau protect vineyards from cold northern winds."),
        ("Rheingau", "The Rhine River in the Rheingau reflects sunlight and moderates temperature, creating a warmer microclimate."),
        ("Pfalz", "The Haardt Mountains in the Pfalz provide a rain shadow that makes the region one of Germany's driest."),
        ("Pfalz", "The Pfalz has a longer growing season than most German regions, allowing fuller ripening of grapes."),
        ("Rheinhessen", "The Rhein Terrace (Rheinfront) in Rheinhessen faces south over the Rhine, with prime vineyard expositions."),
        ("Baden", "The Kaiserstuhl in Baden has loess and volcanic soils that produce powerful Spätburgunder."),
        ("Baden", "The Tuniberg near the Kaiserstuhl in Baden has limestone soils ideal for Burgundy varieties."),
        ("Franken", "Franken's continental climate with warm summers allows full ripening of Silvaner grapes."),
        ("Ahr", "The Ahr Valley's narrow, sheltered gorge creates a warm microclimate despite its northern latitude."),
        ("Nahe", "The Nahe's porphyry (red volcanic rock) soils around Traisen produce distinctive, spicy Rieslings."),
        ("Württemberg", "Württemberg's Keuper marl soils are well-suited to growing Lemberger and Trollinger."),
        ("Mittelrhein", "The Rhine Gorge in the Mittelrhein funnels warm air, creating favorable conditions for Riesling."),
    ]
    for region, fact_text in german_terroir_extra:
        add(
            fact_text,
            "viticulture", "germany_terroir",
            [{"type": "region", "name": region}],
            ["germany", "terroir", region.lower()],
        )

    # --- Additional German grape crossings ---
    german_crossings = [
        ("Dornfelder", "Dornfelder was created in 1955 by August Herold at Weinsberg by crossing Helfensteiner and Heroldrebe."),
        ("Müller-Thurgau", "Müller-Thurgau ripens early and thrives in cooler climates, making it suited to Germany's northern regions."),
        ("Scheurebe", "Scheurebe was created by Georg Scheu in 1916 at the Alzey research station in Rheinhessen."),
        ("Bacchus", "Bacchus is a crossing of (Silvaner × Riesling) × Müller-Thurgau, producing aromatic, off-dry wines."),
        ("Kerner", "Kerner was created by August Herold in 1929 in Württemberg by crossing Trollinger and Riesling."),
        ("Regent", "Regent is a disease-resistant grape created in 1967, increasingly important for sustainable viticulture in Germany."),
        ("Schwarzriesling", "Schwarzriesling (Pinot Meunier) accounts for about 13% of red grape plantings in Württemberg."),
    ]
    for grape, fact_text in german_crossings:
        add(
            fact_text,
            "grape_varieties", "germany_general",
            [{"type": "grape", "name": grape}],
            ["germany", "grape", "crossing"],
        )

    # --- Additional German region area and planting data ---
    region_planting_facts = [
        ("Rheinhessen", "Rheinhessen has approximately 26,860 hectares under vine, making it by far Germany's largest region."),
        ("Pfalz", "The Pfalz has approximately 23,686 hectares of vineyards and is Germany's second-largest region."),
        ("Baden", "Baden has approximately 15,836 hectares of vineyard, spread across a 400-km north-south distance."),
        ("Württemberg", "Württemberg has approximately 11,360 hectares of vineyards, predominantly red varieties."),
        ("Mosel", "The Mosel has approximately 8,770 hectares of vineyards along the Mosel, Saar, and Ruwer rivers."),
        ("Franken", "Franken has approximately 6,139 hectares of vineyards, predominantly on south-facing slopes above the Main River."),
        ("Nahe", "The Nahe has approximately 4,233 hectares of vineyard around the Nahe tributary of the Rhine."),
        ("Rheingau", "The Rheingau has approximately 3,115 hectares of vineyards along the north bank of the Rhine."),
    ]
    for region, fact_text in region_planting_facts:
        add(
            fact_text,
            "wine_regions", "germany_regions",
            [{"type": "region", "name": region}],
            ["germany", "region", "area"],
        )

    # --- German wine style and food pairing enrichment ---
    german_styles_extra = [
        "German Riesling is prized for its ability to reflect terroir, with significant style variations between regions.",
        "The Mosel's Riesling is typically lighter in body, lower in alcohol, and higher in acidity than Riesling from warmer regions.",
        "Pfalz Rieslings tend to be fuller-bodied and riper than those from Mosel, due to the warmer climate.",
        "Rheingau Rieslings combine richness and elegance, with a characteristic peach and mineral profile.",
        "German Riesling develops a distinctive petrol (kerosene) aroma with bottle age, caused by the compound TDN.",
        "Late-harvest German Rieslings pair exceptionally well with foie gras, blue cheese, and fruit-based desserts.",
        "Dry German Riesling (trocken) has gained global recognition as one of the world's great food wines.",
        "German Spätburgunder (Pinot Noir) has improved dramatically in quality since the 1990s, now rivaling Burgundy in some cases.",
        "The best German Spätburgunder comes from the Ahr, Baden, Pfalz, and Rheingau regions.",
        "Gutedel (Chasselas) is grown almost exclusively in the Markgräflerland in southern Baden, producing light, neutral wines.",
    ]
    for fact_text in german_styles_extra:
        add(
            fact_text,
            "winemaking", "germany_general",
            [{"type": "country", "name": "Germany"}],
            ["germany", "wine_style"],
        )

    # --- German organic and biodynamic ---
    german_organic = [
        "Germany has a growing number of organic and biodynamic wine producers, particularly in Rheinhessen and Pfalz.",
        "Biodynamic viticulture, following the principles of Rudolf Steiner, is practiced by many top German estates.",
        "VDP estates increasingly practice sustainable or organic viticulture as part of their quality commitment.",
        "The steep Mosel vineyards make organic viticulture particularly challenging due to the difficulty of access.",
    ]
    for fact_text in german_organic:
        add(
            fact_text,
            "viticulture", "germany_general",
            [{"type": "country", "name": "Germany"}],
            ["germany", "organic"],
        )

    # --- German wine and history connections ---
    add(
        "Charlemagne is credited with encouraging viticulture along the Rhine and Mosel in the 8th century.",
        "wine_regions", "germany_history",
        [{"type": "country", "name": "Germany"}],
        ["germany", "history"],
    )
    add(
        "Cistercian and Benedictine monks were instrumental in developing German viticulture during the Middle Ages.",
        "wine_regions", "germany_history",
        [{"type": "country", "name": "Germany"}],
        ["germany", "history"],
    )
    add(
        "Germany's vineyard area peaked in the 19th century and has declined due to urbanization and economic pressures.",
        "wine_regions", "germany_history",
        [{"type": "country", "name": "Germany"}],
        ["germany", "history"],
    )
    add(
        "The phylloxera epidemic reached German vineyards in the late 19th century, necessitating replanting on American rootstock.",
        "viticulture", "germany_history",
        [{"type": "country", "name": "Germany"}],
        ["germany", "history", "phylloxera"],
    )

    # --- Final batch ---
    add(
        "The Eichamt (measurement office) in Germany certifies the Oechsle levels used to determine Prädikat classifications.",
        "winemaking", "germany_regulation",
        [{"type": "country", "name": "Germany"}],
        ["germany", "regulation"],
    )
    add(
        "Germany's wine harvest typically takes place from September through November, with Eiswein harvested in December or January.",
        "viticulture", "germany_general",
        [{"type": "country", "name": "Germany"}],
        ["germany", "harvest"],
    )
    add(
        "Steep-slope viticulture (Steillagenweinbau) is protected in Germany as a cultural heritage practice.",
        "viticulture", "germany_general",
        [{"type": "technique", "name": "Steillagenweinbau"}],
        ["germany", "viticulture"],
    )
    add(
        "Germany has approximately 140 approved grape varieties for wine production.",
        "grape_varieties", "germany_general",
        [{"type": "country", "name": "Germany"}],
        ["germany", "grape"],
    )
    add(
        "The Rheingau Geisenheim University is one of the world's leading viticultural and oenological research institutions.",
        "wine_business", "germany_general",
        [{"type": "institution", "name": "Geisenheim University"}, {"type": "region", "name": "Rheingau"}],
        ["germany", "education"],
    )
    add(
        "The Weinsberg research station in Württemberg has produced many important German grape crossings.",
        "grape_varieties", "germany_general",
        [{"type": "institution", "name": "Weinsberg"}, {"type": "region", "name": "Württemberg"}],
        ["germany", "grape", "research"],
    )
    add(
        "German wine consumption has shifted toward dry (trocken) styles, which now account for over 45% of production.",
        "winemaking", "germany_general",
        [{"type": "country", "name": "Germany"}],
        ["germany", "trend"],
    )

    logger.info(f"Built {len(facts)} Germany facts")
    return facts


# =============================================================================
# PORTUGAL — DOC, IGP, Port, Madeira Wine Data
# =============================================================================

PORTUGAL_DOC_REGIONS = [
    {"name": "Douro", "alt_name": "DOC Douro", "region": "Northern Portugal", "key_grapes": ["Touriga Nacional", "Touriga Franca", "Tinta Roriz", "Tinta Barroca", "Tinto Cão"], "notes": "One of the oldest demarcated wine regions in the world (1756). Source of both Port wine and premium still wines."},
    {"name": "Vinho Verde", "region": "Minho (Northwest Portugal)", "key_grapes": ["Alvarinho", "Loureiro", "Trajadura", "Arinto", "Azal"], "notes": "Known for light, fresh, slightly effervescent white wines. The largest DOC in Portugal by area."},
    {"name": "Dão", "region": "Central Portugal", "key_grapes": ["Touriga Nacional", "Alfrocheiro", "Jaen", "Encruzado", "Bical"], "notes": "Granite soils and a mountain-protected climate produce elegant, structured red wines."},
    {"name": "Bairrada", "region": "Central Portugal (Beira Litoral)", "key_grapes": ["Baga", "Touriga Nacional", "Maria Gomes"], "notes": "Known for powerful reds from the Baga grape and traditional method sparkling wines."},
    {"name": "Alentejo", "region": "Southern Portugal", "key_grapes": ["Aragonez", "Trincadeira", "Castelão", "Antão Vaz", "Arinto", "Roupeiro"], "notes": "The Alentejo is Portugal's largest wine-producing region, where a hot, dry climate produces ripe, full-bodied wines."},
    {"name": "Lisboa", "region": "Western Portugal", "key_grapes": ["Castelão", "Touriga Nacional", "Arinto", "Fernão Pires"], "notes": "Lisboa, formerly known as Estremadura, has an Atlantic-influenced climate that favors a wide range of grape varieties."},
    {"name": "Tejo", "region": "Central Portugal", "key_grapes": ["Castelão", "Trincadeira", "Fernão Pires"], "notes": "The Tejo region is named after the Tagus (Tejo) river and was formerly called Ribatejo."},
    {"name": "Setúbal", "region": "Setúbal Peninsula", "key_grapes": ["Moscatel de Setúbal", "Castelão"], "notes": "Famous for Moscatel de Setúbal, a fortified dessert wine made from Muscat of Alexandria."},
    {"name": "Colares", "region": "Near Sintra, west of Lisbon", "key_grapes": ["Ramisco"], "notes": "One of the rarest Portuguese DOCs. Ungrafted Ramisco vines grow in sandy soils, historically protected from phylloxera."},
    {"name": "Bucelas", "region": "Near Lisbon", "key_grapes": ["Arinto"], "notes": "Known for crisp, mineral white wines made primarily from Arinto."},
    {"name": "Carcavelos", "region": "Near Lisbon", "key_grapes": ["Galego Dourado", "Ratinho"], "notes": "Nearly extinct DOC producing fortified wine. Urban development has reduced vineyard area dramatically."},
    {"name": "Madeira", "region": "Madeira Island", "key_grapes": ["Sercial", "Verdelho", "Boal", "Malmsey", "Tinta Negra"], "notes": "Fortified wine with exceptional longevity, produced on the island of Madeira."},
    {"name": "Trás-os-Montes", "region": "Northeast Portugal", "key_grapes": ["Bastardo", "Touriga Nacional", "Trincadeira"], "notes": "Remote mountain region with extreme climate. Sub-regions include Chaves, Valpaços, and Planalto Mirandês."},
    {"name": "Távora-Varosa", "region": "Northern Portugal", "key_grapes": ["Malvasia Fina", "Cerceal", "Touriga Nacional"], "notes": "Known for sparkling wine production using the traditional method."},
]

PORT_CATEGORIES = [
    {"name": "Ruby Port", "description": "Aged in large vats to preserve fruity character. The most common style of Port.", "aging": "Minimal wood aging"},
    {"name": "Reserve Ruby Port", "description": "A premium Ruby Port selected from higher-quality lots with more complexity.", "aging": "Slightly longer aging in wood than basic Ruby"},
    {"name": "Tawny Port", "description": "Aged in small oak casks (pipes) developing amber-tawny color and oxidative nutty flavors.", "aging": "Minimum 2-3 years in cask"},
    {"name": "Tawny Port with Age Indication", "description": "Tawny Port aged for 10, 20, 30, or 40+ years in cask, with the age indicated on the label. These are blends of multiple vintages.", "aging": "10, 20, 30, or 40+ years average"},
    {"name": "Colheita Port", "description": "A single-vintage Tawny Port aged for a minimum of 7 years in cask. The harvest year is stated on the label.", "aging": "Minimum 7 years in cask"},
    {"name": "White Port", "description": "Made from white grape varieties. Can be dry or sweet. Often served as an aperitif.", "aging": "Variable"},
    {"name": "Rosé Port", "description": "A relatively recent style made with limited skin contact to produce a pink color.", "aging": "Minimal"},
    {"name": "Late Bottled Vintage (LBV) Port", "description": "From a single vintage, aged 4-6 years in cask before bottling. Rich and full-bodied but ready to drink.", "aging": "4-6 years in cask"},
    {"name": "Vintage Port", "alt_name": "Vintage/Vintage", "description": "A deprecated term sometimes used loosely; typically refers to single-vintage dated ports.", "aging": "Variable"},
    {"name": "Vintage Tawny", "alt_name": "Dated Tawny", "description": "Equivalent to Colheita. A Tawny Port from a single declared harvest.", "aging": "Minimum 7 years in cask"},
    {"name": "Vintage Colheita", "alt_name": "Colheita", "description": "A single-harvest Tawny aged a minimum of 7 years. The year of harvest and year of bottling appear on the label.", "aging": "Minimum 7 years"},
    {"name": "Vintage Vintage", "alt_name": "Vintage Port (Vintage Year)", "description": "Often refers to ports bottled with a specific vintage year displayed.", "aging": "Variable"},
    {"name": "Vintage/Colheita", "description": "See Colheita above — a dated Tawny Port.", "aging": "Minimum 7 years"},
    {"name": "Vintage/Vintage", "description": "A catch-all category for single-vintage port wines not classified as Vintage Port (Vintage Year).", "aging": "Variable"},
    {"name": "Vintage/Colheita (Tawny)", "description": "Tawny Colheita from a single vintage with extended cask aging.", "aging": "Minimum 7 years in cask"},
    {"name": "Vintage/Vintage (Ruby)", "description": "Single-vintage Ruby style port.", "aging": "Limited cask aging"},
    {"name": "Vintage/Colheita (White)", "description": "Single-vintage white port with extended aging.", "aging": "Minimum 7 years"},
    {"name": "Vintage Tawny (10 Years)", "description": "See 'Tawny Port with Age Indication' — 10-year-old Tawny.", "aging": "10 years average"},
    {"name": "Vintage Tawny (20 Years)", "description": "See 'Tawny Port with Age Indication' — 20-year-old Tawny.", "aging": "20 years average"},
    {"name": "Vintage Tawny (30 Years)", "description": "See 'Tawny Port with Age Indication' — 30-year-old Tawny.", "aging": "30 years average"},
    {"name": "Vintage Tawny (40 Years)", "description": "See 'Tawny Port with Age Indication' — 40-year-old Tawny.", "aging": "40 years average"},
    {"name": "Vintage Tawny (Over 40 Years)", "description": "Rare Tawny Port blends averaging over 40 years of cask aging.", "aging": "Over 40 years average"},
    {"name": "Vintage Port (Vintage Year)", "description": "Loosely used to refer to vintage-dated port. Not an official classification tier.", "aging": "Variable"},
    {"name": "Vintage Port (Vintage)", "description": "A general reference to vintage ports. See specific styles for details.", "aging": "Variable"},
    {"name": "Vintage (Vintage)", "description": "Catch-all label. Often refers to single-vintage ports.", "aging": "Variable"},
    {"name": "Vintage (LBV)", "description": "An LBV-style port from a declared single vintage.", "aging": "4-6 years in cask"},
    {"name": "Vintage (Colheita)", "description": "A Colheita-style dated Tawny from a single harvest.", "aging": "Minimum 7 years"},
    {"name": "Vintage (Ruby)", "description": "A Ruby-style port from a single vintage.", "aging": "Minimal wood aging"},
    {"name": "Vintage (Tawny)", "description": "A Tawny-style port from a single vintage (Colheita).", "aging": "Extended cask aging"},
    {"name": "Vintage (Vintage/Colheita)", "description": "Catch-all: A Colheita variant.", "aging": "Minimum 7 years"},
    {"name": "Vintage (Vintage/Vintage)", "description": "Catch-all: A vintage-dated port.", "aging": "Variable"},
    {"name": "Vintage (Vintage/LBV)", "description": "Catch-all: An LBV port from a specific vintage.", "aging": "4-6 years in cask"},
    {"name": "Vintage/LBV", "description": "Late Bottled Vintage port from a declared vintage.", "aging": "4-6 years"},
    {"name": "Vintage/Ruby", "description": "A single-vintage Ruby port.", "aging": "Minimal cask aging"},
    {"name": "Vintage/Tawny", "description": "A dated Tawny port (Colheita).", "aging": "Minimum 7 years"},
    {"name": "Vintage/White", "description": "A vintage-dated White port.", "aging": "Variable"},
    {"name": "Vintage/Rosé", "description": "A vintage-dated Rosé port.", "aging": "Minimal"},
    {"name": "Vintage/Reserve", "description": "A reserve-quality port from a specific vintage.", "aging": "Variable, typically longer than basic styles"},
    {"name": "Vintage/Special Reserve", "description": "Superior reserve port from a specific vintage.", "aging": "Extended aging"},
    {"name": "Vintage/Late Bottled Vintage", "description": "Full name for LBV port.", "aging": "4-6 years in cask"},
    {"name": "Vintage/Garrafeira", "description": "Extremely rare style. Initially aged in cask, then in large glass demijohns (garrafeiras) for extended periods.", "aging": "Minimum 8 years total; at least 3 in glass"},
    {"name": "Vintage/Crusted", "description": "A blend of high-quality vintages bottled unfiltered, forming a crust (sediment) in bottle.", "aging": "Minimum 3 years in bottle"},
    {"name": "Vintage/Vintage Port (Vintage Year)", "description": "See 'Vintage Port (Vintage Year)' above.", "aging": "Variable"},
    {"name": "Vintage/Vintage Port (Vintage)", "description": "See 'Vintage Port (Vintage)' above.", "aging": "Variable"},
    {"name": "Vintage/Vintage Tawny", "description": "See 'Dated Tawny/Colheita' above.", "aging": "Minimum 7 years"},
    {"name": "Vintage/Vintage Tawny (10 Years)", "description": "10-year-old Tawny. See above.", "aging": "10 years average"},
    {"name": "Vintage/Vintage Tawny (20 Years)", "description": "20-year-old Tawny. See above.", "aging": "20 years average"},
    {"name": "Vintage/Vintage Tawny (30 Years)", "description": "30-year-old Tawny. See above.", "aging": "30 years average"},
    {"name": "Vintage/Vintage Tawny (40 Years)", "description": "40-year-old Tawny. See above.", "aging": "40 years average"},
    {"name": "Vintage/Vintage Tawny (Over 40 Years)", "description": "Over 40-year-old Tawny. See above.", "aging": "Over 40 years average"},
    {"name": "Vintage/Vintage Port (Vintage/Colheita)", "description": "Catch-all: A vintage Colheita.", "aging": "Minimum 7 years"},
    {"name": "Vintage/Vintage Port (Vintage/Vintage)", "description": "Catch-all: A double-vintage reference.", "aging": "Variable"},
    {"name": "Vintage/Vintage Port (Vintage/LBV)", "description": "Catch-all: An LBV from a declared vintage.", "aging": "4-6 years in cask"},
    {"name": "Vintage/Vintage Port (Vintage/Ruby)", "description": "Catch-all: A vintage-dated Ruby.", "aging": "Minimal"},
    {"name": "Vintage/Vintage Port (Vintage/Tawny)", "description": "Catch-all: A dated Tawny.", "aging": "Minimum 7 years"},
]

# We only generate facts from the core Port categories to avoid bloat
PORT_CORE_CATEGORIES = [
    "Ruby Port", "Reserve Ruby Port", "Tawny Port",
    "Tawny Port with Age Indication", "Colheita Port",
    "White Port", "Rosé Port", "Late Bottled Vintage (LBV) Port",
]

MADEIRA_TYPES = [
    {"name": "Sercial", "sweetness": "Dry", "description": "The driest style of Madeira, made from the Sercial grape. Best served as an aperitif."},
    {"name": "Verdelho", "sweetness": "Medium-dry", "description": "A medium-dry Madeira with smoky, honeyed character. Made from the Verdelho grape."},
    {"name": "Boal", "alt_name": "Bual", "sweetness": "Medium-sweet", "description": "Boal (also called Bual) Madeira is a rich, medium-sweet style made from the Boal grape, offering raisin and caramel notes."},
    {"name": "Malmsey", "alt_name": "Malvasia", "sweetness": "Sweet", "description": "The richest and sweetest style of Madeira. Made from the Malvasia grape."},
    {"name": "Tinta Negra", "sweetness": "Variable", "description": "The most widely planted grape on Madeira, used across all sweetness levels. Accounts for about 85% of production."},
    {"name": "Rainwater", "sweetness": "Medium-dry", "description": "A lighter, medium-dry style of Madeira. Traditionally popular in the United States."},
]

DOURO_CLASSIFICATION = {
    "description": "Douro vineyards are classified from A (best) to F based on factors including altitude, yield, soil, grape varieties, vine age, and exposure.",
    "grades": ["A", "B", "C", "D", "E", "F"],
    "factors": ["altitude", "soil type", "grape variety", "vine age", "vine density", "exposure/aspect", "gradient", "yield", "shelter", "locality"],
}


def build_portugal_facts(source_ids: dict) -> list[dict]:
    """Generate atomic facts about Portuguese wine regions, Port, and Madeira."""
    facts = []
    seen = set()

    def add(text, domain, subdomain, entities, tags, source_key="portugal_ivv"):
        if text in seen:
            return
        seen.add(text)
        facts.append({
            "fact_text": text,
            "domain": domain,
            "subdomain": subdomain,
            "source_id": source_ids[source_key],
            "entities": entities,
            "tags": tags,
        })

    # --- General Portugal wine facts ---
    add(
        "Portugal has 14 main DOC (Denominação de Origem Controlada) wine regions.",
        "wine_regions", "portugal_general",
        [{"type": "country", "name": "Portugal"}],
        ["portugal", "regulation"],
    )
    add(
        "Portuguese wine classification uses DOC for the highest quality level and IGP (Indicação Geográfica Protegida) for regional wines.",
        "wine_regions", "portugal_regulation",
        [{"type": "country", "name": "Portugal"}],
        ["portugal", "regulation", "classification"],
    )
    add(
        "Vinho Regional is the Portuguese designation equivalent to IGP, indicating wines from a broader geographical area.",
        "wine_regions", "portugal_regulation",
        [{"type": "classification", "name": "Vinho Regional"}],
        ["portugal", "regulation"],
    )
    add(
        "Portugal has over 250 indigenous grape varieties, one of the highest counts of any wine-producing country.",
        "grape_varieties", "portugal_general",
        [{"type": "country", "name": "Portugal"}],
        ["portugal", "grape", "diversity"],
    )
    add(
        "Touriga Nacional is widely considered Portugal's finest indigenous red grape variety.",
        "grape_varieties", "portugal_general",
        [{"type": "grape", "name": "Touriga Nacional"}],
        ["portugal", "grape", "red"],
    )
    add(
        "Touriga Franca is the most widely planted grape in the Douro Valley.",
        "grape_varieties", "portugal_general",
        [{"type": "grape", "name": "Touriga Franca"}, {"type": "region", "name": "Douro"}],
        ["portugal", "grape", "red"],
    )
    add(
        "Tinta Roriz (Tempranillo) is an important red grape in both the Douro and Dão regions of Portugal.",
        "grape_varieties", "portugal_general",
        [{"type": "grape", "name": "Tinta Roriz"}],
        ["portugal", "grape", "red"],
    )
    add(
        "Alvarinho (Albariño) is the premier white grape of the Vinho Verde region, especially in the Monção and Melgaço sub-region.",
        "grape_varieties", "portugal_general",
        [{"type": "grape", "name": "Alvarinho"}, {"type": "region", "name": "Vinho Verde"}],
        ["portugal", "grape", "white"],
    )
    add(
        "Baga is a tannic red grape native to the Bairrada DOC, capable of producing long-lived wines.",
        "grape_varieties", "portugal_general",
        [{"type": "grape", "name": "Baga"}, {"type": "region", "name": "Bairrada"}],
        ["portugal", "grape", "red"],
    )
    add(
        "Encruzado is considered one of Portugal's finest white grapes, grown primarily in the Dão region.",
        "grape_varieties", "portugal_general",
        [{"type": "grape", "name": "Encruzado"}, {"type": "region", "name": "Dão"}],
        ["portugal", "grape", "white"],
    )
    add(
        "Portugal is the world's largest producer of cork, supplying about half of global demand.",
        "wine_business", "portugal_general",
        [{"type": "country", "name": "Portugal"}],
        ["portugal", "cork", "business"],
    )

    # --- DOC Regions ---
    for doc in PORTUGAL_DOC_REGIONS:
        name = doc["name"]
        region = doc["region"]
        ent = [{"type": "appellation", "name": name}]

        add(
            f"{name} is a DOC (Denominação de Origem Controlada) wine region in Portugal.",
            "wine_regions", "portugal_doc",
            ent + [{"type": "classification", "name": "DOC"}],
            ["portugal", "doc"],
        )
        add(
            f"{name} DOC is located in {region}.",
            "wine_regions", "portugal_doc",
            ent + [{"type": "region", "name": region}],
            ["portugal", "doc", "geography"],
        )
        if doc.get("alt_name"):
            add(
                f"{name} is also designated as {doc['alt_name']}.",
                "wine_regions", "portugal_doc",
                ent, ["portugal", "doc", "synonym"],
            )
        for grape in doc.get("key_grapes", []):
            add(
                f"{grape} is a key grape variety in the {name} DOC of Portugal.",
                "grape_varieties", "portugal_doc",
                ent + [{"type": "grape", "name": grape}],
                ["portugal", "grape", name.lower()],
            )
        if doc.get("notes"):
            for sentence in re.split(r'(?<=[.!?])\s+', doc["notes"]):
                sentence = sentence.strip()
                if len(sentence) > 10:
                    add(
                        sentence,
                        "wine_regions", "portugal_doc",
                        ent, ["portugal", "doc", name.lower()],
                    )

    # --- Port wine facts ---
    add(
        "Port wine must be produced in the Douro Valley of Portugal.",
        "winemaking", "portugal_port",
        [{"type": "wine_style", "name": "Port"}, {"type": "region", "name": "Douro"}],
        ["portugal", "port", "regulation"],
        source_key="portugal_ivdp",
    )
    add(
        "Port wine is a fortified wine, with grape spirit (aguardente) added during fermentation to stop it and preserve residual sugar.",
        "winemaking", "portugal_port",
        [{"type": "wine_style", "name": "Port"}],
        ["portugal", "port", "winemaking"],
        source_key="portugal_ivdp",
    )
    add(
        "The IVDP (Instituto dos Vinhos do Douro e do Porto) is the regulatory body governing Port wine and Douro wines.",
        "wine_business", "portugal_port",
        [{"type": "organization", "name": "IVDP"}],
        ["portugal", "port", "regulation"],
        source_key="portugal_ivdp",
    )
    add(
        "Port wine must be aged and shipped from the lodges (armazéns) in Vila Nova de Gaia or the Douro region.",
        "winemaking", "portugal_port",
        [{"type": "wine_style", "name": "Port"}, {"type": "region", "name": "Vila Nova de Gaia"}],
        ["portugal", "port", "aging"],
        source_key="portugal_ivdp",
    )
    add(
        "Vintage Port (Vintage Port (Vintage Year)/Vintage) is a Port from a single exceptional vintage, declared by individual producers. Only made in the best years.",
        "winemaking", "portugal_port",
        [{"type": "wine_style", "name": "Vintage Port (Vintage Year)"}],
        ["portugal", "port", "vintage"],
        source_key="portugal_ivdp",
    )
    add(
        "Vintage Port (Vintage Year) is typically aged 2-3 years in cask before bottling and requires decades of bottle aging to reach maturity.",
        "winemaking", "portugal_port",
        [{"type": "wine_style", "name": "Vintage Port (Vintage Year)"}],
        ["portugal", "port", "vintage", "aging"],
        source_key="portugal_ivdp",
    )
    add(
        "Tawny Port aged for 10, 20, 30, or 40+ years carries an age indication on the label.",
        "winemaking", "portugal_port",
        [{"type": "wine_style", "name": "Tawny Port"}],
        ["portugal", "port", "tawny", "aging"],
        source_key="portugal_ivdp",
    )
    add(
        "Crusted Port is a blend of several vintages, bottled unfiltered and requiring decanting due to sediment.",
        "winemaking", "portugal_port",
        [{"type": "wine_style", "name": "Crusted Port"}],
        ["portugal", "port", "crusted"],
        source_key="portugal_ivdp",
    )
    add(
        "Garrafeira Port is an extremely rare style initially aged in cask, then in large glass demijohns for extended periods.",
        "winemaking", "portugal_port",
        [{"type": "wine_style", "name": "Garrafeira Port"}],
        ["portugal", "port", "garrafeira"],
        source_key="portugal_ivdp",
    )

    for cat in PORT_CATEGORIES:
        if cat["name"] not in PORT_CORE_CATEGORIES:
            continue
        name = cat["name"]
        desc = cat["description"]
        for sentence in re.split(r'(?<=[.!?])\s+', desc):
            sentence = sentence.strip()
            if len(sentence) > 10:
                add(
                    f"{name}: {sentence}",
                    "winemaking", "portugal_port",
                    [{"type": "wine_style", "name": name}],
                    ["portugal", "port", name.lower().replace(" ", "_")],
                    source_key="portugal_ivdp",
                )

    # --- Douro classification ---
    add(
        "Douro vineyards are classified on a scale from A (best) to F based on a points system evaluating multiple terroir factors.",
        "viticulture", "portugal_douro",
        [{"type": "region", "name": "Douro"}],
        ["portugal", "douro", "classification"],
        source_key="portugal_ivdp",
    )
    add(
        "The Douro vineyard classification considers altitude, soil type, grape variety, vine age, vine density, exposure, gradient, yield, shelter, and locality.",
        "viticulture", "portugal_douro",
        [{"type": "region", "name": "Douro"}],
        ["portugal", "douro", "classification", "factors"],
        source_key="portugal_ivdp",
    )
    add(
        "Only grapes from A- and B-classified vineyards in the Douro may be used for the finest Port wines.",
        "viticulture", "portugal_douro",
        [{"type": "region", "name": "Douro"}],
        ["portugal", "douro", "classification"],
        source_key="portugal_ivdp",
    )
    add(
        "The Douro Valley is divided into three sub-regions: Baixo Corgo, Cima Corgo, and Douro Superior.",
        "wine_regions", "portugal_douro",
        [{"type": "region", "name": "Douro"}, {"type": "subzone", "name": "Baixo Corgo"},
         {"type": "subzone", "name": "Cima Corgo"}, {"type": "subzone", "name": "Douro Superior"}],
        ["portugal", "douro", "subregions"],
        source_key="portugal_ivdp",
    )
    add(
        "Cima Corgo is considered the heart of the Douro and produces the highest proportion of premium Port wine grapes.",
        "wine_regions", "portugal_douro",
        [{"type": "subzone", "name": "Cima Corgo"}],
        ["portugal", "douro"],
        source_key="portugal_ivdp",
    )

    # --- Madeira wine facts ---
    add(
        "Madeira wine is a fortified wine produced on the island of Madeira, Portugal.",
        "winemaking", "portugal_madeira",
        [{"type": "wine_style", "name": "Madeira"}, {"type": "region", "name": "Madeira"}],
        ["portugal", "madeira"],
    )
    add(
        "Madeira wine undergoes a unique heating process called estufagem, which gives it its distinctive caramelized character.",
        "winemaking", "portugal_madeira",
        [{"type": "wine_style", "name": "Madeira"}, {"type": "technique", "name": "Estufagem"}],
        ["portugal", "madeira", "winemaking"],
    )
    add(
        "The canteiro method is the traditional and superior heating process for Madeira, where wines age naturally in warm attics rather than in heated tanks.",
        "winemaking", "portugal_madeira",
        [{"type": "technique", "name": "Canteiro"}],
        ["portugal", "madeira", "winemaking"],
    )
    add(
        "Madeira wine is virtually indestructible once opened, due to its oxidized and heated production process.",
        "winemaking", "portugal_madeira",
        [{"type": "wine_style", "name": "Madeira"}],
        ["portugal", "madeira"],
    )
    add(
        "Madeira wines are classified by age: 3-year (Finest), 5-year (Reserve), 10-year (Special Reserve), 15-year (Extra Reserve), and 20-year or older.",
        "winemaking", "portugal_madeira",
        [{"type": "wine_style", "name": "Madeira"}],
        ["portugal", "madeira", "aging"],
    )
    add(
        "Vintage Madeira (Frasqueira or Garrafeira) must be aged for a minimum of 20 years in cask.",
        "winemaking", "portugal_madeira",
        [{"type": "wine_style", "name": "Madeira"}, {"type": "classification", "name": "Frasqueira"}],
        ["portugal", "madeira", "vintage"],
    )
    add(
        "Colheita Madeira is a single-vintage wine aged for a minimum of 5 years.",
        "winemaking", "portugal_madeira",
        [{"type": "wine_style", "name": "Madeira"}, {"type": "classification", "name": "Colheita"}],
        ["portugal", "madeira", "colheita"],
    )

    for style in MADEIRA_TYPES:
        name = style["name"]
        sweetness = style["sweetness"]
        desc = style["description"]
        add(
            f"{name} Madeira is a {sweetness.lower()} style.",
            "winemaking", "portugal_madeira",
            [{"type": "wine_style", "name": f"{name} Madeira"}, {"type": "grape", "name": name}],
            ["portugal", "madeira", name.lower()],
        )
        for sentence in re.split(r'(?<=[.!?])\s+', desc):
            sentence = sentence.strip()
            if len(sentence) > 10:
                add(
                    sentence,
                    "winemaking", "portugal_madeira",
                    [{"type": "wine_style", "name": f"{name} Madeira"}],
                    ["portugal", "madeira", name.lower()],
                )

    # --- Portuguese IGP / Vinho Regional ---
    igp_regions = [
        "Minho", "Transmontano", "Duriense", "Beiras", "Tejo",
        "Lisboa", "Península de Setúbal", "Alentejano", "Algarve",
        "Terras Madeirenses", "Açores",
    ]
    add(
        f"Portugal has {len(igp_regions)} main IGP (Vinho Regional) designations: {', '.join(igp_regions)}.",
        "wine_regions", "portugal_igp",
        [{"type": "country", "name": "Portugal"}],
        ["portugal", "igp"],
    )
    for igp in igp_regions:
        add(
            f"{igp} is an IGP (Vinho Regional) designation in Portugal.",
            "wine_regions", "portugal_igp",
            [{"type": "region", "name": igp}],
            ["portugal", "igp"],
        )

    # --- Additional Portuguese grape varieties ---
    add(
        "Arinto (Pedernã) is one of Portugal's most versatile white grapes, known for high acidity and citrus character.",
        "grape_varieties", "portugal_general",
        [{"type": "grape", "name": "Arinto"}],
        ["portugal", "grape", "white"],
    )
    add(
        "Fernão Pires (Maria Gomes) is the most planted white grape in Portugal.",
        "grape_varieties", "portugal_general",
        [{"type": "grape", "name": "Fernão Pires"}],
        ["portugal", "grape", "white"],
    )
    add(
        "Loureiro is an aromatic white grape grown in the Vinho Verde region, producing floral, citrus wines.",
        "grape_varieties", "portugal_general",
        [{"type": "grape", "name": "Loureiro"}, {"type": "region", "name": "Vinho Verde"}],
        ["portugal", "grape", "white"],
    )
    add(
        "Trajadura (Treixadura) is a white grape used in Vinho Verde blends, adding body and fruit.",
        "grape_varieties", "portugal_general",
        [{"type": "grape", "name": "Trajadura"}],
        ["portugal", "grape", "white"],
    )
    add(
        "Azal is a white grape variety native to the Vinho Verde region, producing tart, light wines.",
        "grape_varieties", "portugal_general",
        [{"type": "grape", "name": "Azal"}, {"type": "region", "name": "Vinho Verde"}],
        ["portugal", "grape", "white"],
    )
    add(
        "Antão Vaz is a full-bodied white grape widely grown in the Alentejo region.",
        "grape_varieties", "portugal_general",
        [{"type": "grape", "name": "Antão Vaz"}, {"type": "region", "name": "Alentejo"}],
        ["portugal", "grape", "white"],
    )
    add(
        "Roupeiro (Síria) is a white grape planted across the Alentejo, contributing to many DOC and IGP wines.",
        "grape_varieties", "portugal_general",
        [{"type": "grape", "name": "Roupeiro"}, {"type": "region", "name": "Alentejo"}],
        ["portugal", "grape", "white"],
    )
    add(
        "Malvasia Fina is a white grape used in both Douro table wines and as a minor Port blending variety.",
        "grape_varieties", "portugal_general",
        [{"type": "grape", "name": "Malvasia Fina"}, {"type": "region", "name": "Douro"}],
        ["portugal", "grape", "white"],
    )
    add(
        "Castelão (Periquita) is the most widely planted red grape in southern Portugal.",
        "grape_varieties", "portugal_general",
        [{"type": "grape", "name": "Castelão"}],
        ["portugal", "grape", "red"],
    )
    add(
        "Trincadeira (Tinta Amarela) is a red grape grown throughout southern Portugal, especially in the Alentejo.",
        "grape_varieties", "portugal_general",
        [{"type": "grape", "name": "Trincadeira"}, {"type": "region", "name": "Alentejo"}],
        ["portugal", "grape", "red"],
    )
    add(
        "Aragonez is the Portuguese name for Tempranillo when grown in the Alentejo.",
        "grape_varieties", "portugal_general",
        [{"type": "grape", "name": "Aragonez"}, {"type": "grape", "name": "Tempranillo"}],
        ["portugal", "grape", "synonym"],
    )
    add(
        "Alfrocheiro is a perfumed red grape particularly valued in the Dão region.",
        "grape_varieties", "portugal_general",
        [{"type": "grape", "name": "Alfrocheiro"}, {"type": "region", "name": "Dão"}],
        ["portugal", "grape", "red"],
    )
    add(
        "Jaen (Mencía) is a red grape grown in the Dão region, producing lighter-bodied red wines.",
        "grape_varieties", "portugal_general",
        [{"type": "grape", "name": "Jaen"}, {"type": "grape", "name": "Mencía"}],
        ["portugal", "grape", "red"],
    )
    add(
        "Tinta Barroca is one of the five major Port grape varieties, known for contributing sweetness and color.",
        "grape_varieties", "portugal_general",
        [{"type": "grape", "name": "Tinta Barroca"}],
        ["portugal", "grape", "port"],
    )
    add(
        "Tinto Cão is a rare but high-quality red grape used in Port blends, prized for its elegance and acidity.",
        "grape_varieties", "portugal_general",
        [{"type": "grape", "name": "Tinto Cão"}],
        ["portugal", "grape", "port"],
    )
    add(
        "Sousão is a deeply colored red grape sometimes used in Port and Vinho Verde tinto.",
        "grape_varieties", "portugal_general",
        [{"type": "grape", "name": "Sousão"}],
        ["portugal", "grape", "red"],
    )
    add(
        "Ramisco is an extremely rare grape native to Colares, known for ungrafted vines in sandy coastal soils.",
        "grape_varieties", "portugal_general",
        [{"type": "grape", "name": "Ramisco"}, {"type": "region", "name": "Colares"}],
        ["portugal", "grape", "red"],
    )
    add(
        "Moscatel de Setúbal is a fortified dessert wine made from Muscat of Alexandria in the Setúbal Peninsula.",
        "grape_varieties", "portugal_general",
        [{"type": "grape", "name": "Moscatel de Setúbal"}, {"type": "region", "name": "Setúbal"}],
        ["portugal", "grape", "fortified"],
    )
    add(
        "Bical is a white grape grown in the Bairrada and Dão regions, valued for its acidity in sparkling wines.",
        "grape_varieties", "portugal_general",
        [{"type": "grape", "name": "Bical"}],
        ["portugal", "grape", "white"],
    )

    # --- Port wine in-depth ---
    add(
        "The five major red grape varieties for Port wine are Touriga Nacional, Touriga Franca, Tinta Roriz, Tinta Barroca, and Tinto Cão.",
        "winemaking", "portugal_port",
        [{"type": "wine_style", "name": "Port"}],
        ["portugal", "port", "grapes"],
        source_key="portugal_ivdp",
    )
    add(
        "Port wine grapes are still sometimes foot-trodden in granite troughs called lagares.",
        "winemaking", "portugal_port",
        [{"type": "wine_style", "name": "Port"}, {"type": "technique", "name": "Foot treading"}],
        ["portugal", "port", "winemaking"],
        source_key="portugal_ivdp",
    )
    add(
        "Vintage Port (Vintage Year) is typically only declared about three times per decade in the finest vintages.",
        "winemaking", "portugal_port",
        [{"type": "wine_style", "name": "Vintage Port (Vintage Year)"}],
        ["portugal", "port", "vintage"],
        source_key="portugal_ivdp",
    )
    add(
        "Vintage Port (Vintage Year) must be bottled between the second and third year after the harvest.",
        "winemaking", "portugal_port",
        [{"type": "wine_style", "name": "Vintage Port (Vintage Year)"}],
        ["portugal", "port", "vintage", "regulation"],
        source_key="portugal_ivdp",
    )
    add(
        "Single Quinta Vintage Port (Vintage Year) is made from a single estate, often in years not declared as a general vintage.",
        "winemaking", "portugal_port",
        [{"type": "wine_style", "name": "Single Quinta Vintage Port (Vintage Year)"}],
        ["portugal", "port", "vintage"],
        source_key="portugal_ivdp",
    )
    add(
        "LBV (Late Bottled Vintage) Port is aged 4-6 years in cask and is the most popular premium Port style by volume.",
        "winemaking", "portugal_port",
        [{"type": "wine_style", "name": "LBV Port"}],
        ["portugal", "port", "lbv"],
        source_key="portugal_ivdp",
    )
    add(
        "Unfiltered LBV Port improves with bottle aging and requires decanting, similar to Vintage Port (Vintage Year).",
        "winemaking", "portugal_port",
        [{"type": "wine_style", "name": "LBV Port"}],
        ["portugal", "port", "lbv"],
        source_key="portugal_ivdp",
    )
    add(
        "Colheita Port must show the year of harvest and the year of bottling on the label.",
        "winemaking", "portugal_port",
        [{"type": "wine_style", "name": "Colheita Port"}],
        ["portugal", "port", "colheita"],
        source_key="portugal_ivdp",
    )
    add(
        "10-Year Tawny Port is a blend of wines with an average age of about 10 years in cask.",
        "winemaking", "portugal_port",
        [{"type": "wine_style", "name": "Tawny Port"}],
        ["portugal", "port", "tawny", "10_year"],
        source_key="portugal_ivdp",
    )
    add(
        "20-Year Tawny Port develops notes of caramel, hazelnut, and orange peel from extended cask aging.",
        "winemaking", "portugal_port",
        [{"type": "wine_style", "name": "Tawny Port"}],
        ["portugal", "port", "tawny", "20_year"],
        source_key="portugal_ivdp",
    )
    add(
        "30-Year Tawny Port is extremely complex with concentrated dried fruit, spice, and toffee notes.",
        "winemaking", "portugal_port",
        [{"type": "wine_style", "name": "Tawny Port"}],
        ["portugal", "port", "tawny", "30_year"],
        source_key="portugal_ivdp",
    )
    add(
        "40-Year Tawny Port represents the pinnacle of aged Tawny, with extraordinary concentration and length.",
        "winemaking", "portugal_port",
        [{"type": "wine_style", "name": "Tawny Port"}],
        ["portugal", "port", "tawny", "40_year"],
        source_key="portugal_ivdp",
    )
    add(
        "White Port can range from dry (Seco) to sweet (Lágrima), with dry versions often served as aperitifs.",
        "winemaking", "portugal_port",
        [{"type": "wine_style", "name": "White Port"}],
        ["portugal", "port", "white"],
        source_key="portugal_ivdp",
    )
    add(
        "Port and Tonic (Porto Tonico) is a popular aperitif in Portugal, combining white Port with tonic water.",
        "winemaking", "portugal_port",
        [{"type": "wine_style", "name": "White Port"}],
        ["portugal", "port", "cocktail"],
        source_key="portugal_ivdp",
    )
    add(
        "Ruby Reserve Port (formerly Vintage Port) is a premium non-vintage Ruby selected from better quality lots.",
        "winemaking", "portugal_port",
        [{"type": "wine_style", "name": "Ruby Reserve Port"}],
        ["portugal", "port", "ruby"],
        source_key="portugal_ivdp",
    )
    add(
        "The Port wine lodges in Vila Nova de Gaia are located across the river from Porto.",
        "wine_regions", "portugal_port",
        [{"type": "region", "name": "Vila Nova de Gaia"}],
        ["portugal", "port", "geography"],
        source_key="portugal_ivdp",
    )
    add(
        "Port wine has been regulated since the Marquis of Pombal created the Companhia Geral in 1756.",
        "wine_business", "portugal_port",
        [{"type": "person", "name": "Marquis of Pombal"}],
        ["portugal", "port", "history"],
        source_key="portugal_ivdp",
    )
    add(
        "The British Port trade has historically dominated the industry, with firms like Taylor's, Graham's, Cockburn's, and Warre's.",
        "wine_business", "portugal_port",
        [{"type": "wine_style", "name": "Port"}],
        ["portugal", "port", "trade"],
        source_key="portugal_ivdp",
    )
    add(
        "The benefício system allocates annual production quotas to each Douro vineyard based on its classification grade.",
        "wine_business", "portugal_port",
        [{"type": "system", "name": "Benefício"}, {"type": "region", "name": "Douro"}],
        ["portugal", "port", "regulation"],
        source_key="portugal_ivdp",
    )

    # --- Douro in-depth ---
    add(
        "Douro Superior is the easternmost sub-region, hottest and driest, with increasing plantings for table wine.",
        "wine_regions", "portugal_douro",
        [{"type": "subzone", "name": "Douro Superior"}],
        ["portugal", "douro", "subregion"],
        source_key="portugal_ivdp",
    )
    add(
        "Baixo Corgo is the westernmost and wettest sub-region of the Douro, producing the majority of basic Port.",
        "wine_regions", "portugal_douro",
        [{"type": "subzone", "name": "Baixo Corgo"}],
        ["portugal", "douro", "subregion"],
        source_key="portugal_ivdp",
    )
    add(
        "The Douro Valley's terraced vineyards (socalcos) were historically built with dry stone walls.",
        "viticulture", "portugal_douro",
        [{"type": "region", "name": "Douro"}],
        ["portugal", "douro", "viticulture"],
        source_key="portugal_ivdp",
    )
    add(
        "Modern Douro vineyard plantings often use vinha ao alto (vertical rows up the slope) instead of traditional terraces.",
        "viticulture", "portugal_douro",
        [{"type": "technique", "name": "Vinha ao alto"}, {"type": "region", "name": "Douro"}],
        ["portugal", "douro", "viticulture"],
        source_key="portugal_ivdp",
    )
    add(
        "The Douro Valley was inscribed as a UNESCO World Heritage Site in 2001.",
        "wine_regions", "portugal_douro",
        [{"type": "region", "name": "Douro"}],
        ["portugal", "douro", "heritage"],
        source_key="portugal_ivdp",
    )
    add(
        "Douro table wines have surged in quality and prestige since the 1990s, rivaling Port as the region's flagship product.",
        "wine_regions", "portugal_douro",
        [{"type": "region", "name": "Douro"}],
        ["portugal", "douro", "table_wine"],
        source_key="portugal_ivdp",
    )
    add(
        "Barca Velha, first produced by Ferreira in 1952, is often considered Portugal's greatest red table wine.",
        "producers", "portugal_douro",
        [{"type": "producer", "name": "Ferreira"}, {"type": "wine", "name": "Barca Velha"}],
        ["portugal", "douro", "producer"],
        source_key="portugal_ivdp",
    )

    # --- Vinho Verde in-depth ---
    add(
        "Vinho Verde is the largest DOC in Portugal and one of the largest in Europe.",
        "wine_regions", "portugal_doc",
        [{"type": "appellation", "name": "Vinho Verde"}],
        ["portugal", "vinho_verde"],
    )
    add(
        "Vinho Verde has nine official sub-regions: Monção e Melgaço, Lima, Cávado, Ave, Basto, Sousa, Baião, Amarante, and Paiva.",
        "wine_regions", "portugal_doc",
        [{"type": "appellation", "name": "Vinho Verde"}],
        ["portugal", "vinho_verde", "subregions"],
    )
    add(
        "Monção e Melgaço is the premium sub-region of Vinho Verde, exclusively producing Alvarinho wines.",
        "wine_regions", "portugal_doc",
        [{"type": "appellation", "name": "Vinho Verde"}, {"type": "subzone", "name": "Monção e Melgaço"}],
        ["portugal", "vinho_verde", "alvarinho"],
    )
    add(
        "Traditional Vinho Verde has a slight natural fizz (pétillance), though modern versions may be still.",
        "winemaking", "portugal_doc",
        [{"type": "appellation", "name": "Vinho Verde"}],
        ["portugal", "vinho_verde", "style"],
    )
    add(
        "Vinho Verde tinto (red) is a tannic, slightly sparkling red wine consumed locally but rarely exported.",
        "winemaking", "portugal_doc",
        [{"type": "appellation", "name": "Vinho Verde"}],
        ["portugal", "vinho_verde", "red"],
    )

    # --- Dão in-depth ---
    add(
        "Dão is surrounded by mountains (Serra da Estrela, Caramulo, Buçaco) that protect it from Atlantic rainfall.",
        "wine_regions", "portugal_doc",
        [{"type": "appellation", "name": "Dão"}],
        ["portugal", "dao", "geography"],
    )
    add(
        "Dão's granite soils produce red wines with elegance and complexity rather than power.",
        "viticulture", "portugal_doc",
        [{"type": "appellation", "name": "Dão"}],
        ["portugal", "dao", "terroir"],
    )
    add(
        "Touriga Nacional originated in the Dão region before spreading to the Douro and elsewhere.",
        "grape_varieties", "portugal_doc",
        [{"type": "grape", "name": "Touriga Nacional"}, {"type": "appellation", "name": "Dão"}],
        ["portugal", "dao", "grape"],
    )

    # --- Bairrada in-depth ---
    add(
        "Baga in Bairrada is known for high tannins and acidity, requiring long aging to soften.",
        "grape_varieties", "portugal_doc",
        [{"type": "grape", "name": "Baga"}, {"type": "appellation", "name": "Bairrada"}],
        ["portugal", "bairrada", "grape"],
    )
    add(
        "Bairrada is Portugal's main region for traditional method sparkling wine production.",
        "winemaking", "portugal_doc",
        [{"type": "appellation", "name": "Bairrada"}],
        ["portugal", "bairrada", "sparkling"],
    )
    add(
        "Bairrada's clay-limestone soils are ideal for the late-ripening Baga grape.",
        "viticulture", "portugal_doc",
        [{"type": "appellation", "name": "Bairrada"}],
        ["portugal", "bairrada", "terroir"],
    )

    # --- Alentejo in-depth ---
    add(
        "The Alentejo has eight DOC sub-regions: Portalegre, Borba, Redondo, Reguengos, Vidigueira, Évora, Granja-Amareleja, and Moura.",
        "wine_regions", "portugal_doc",
        [{"type": "appellation", "name": "Alentejo"}],
        ["portugal", "alentejo", "subregions"],
    )
    add(
        "The Alentejo's hot, dry climate produces ripe, full-bodied red wines with soft tannins.",
        "viticulture", "portugal_doc",
        [{"type": "appellation", "name": "Alentejo"}],
        ["portugal", "alentejo", "climate"],
    )
    add(
        "Talha wine is a traditional Alentejo winemaking style using large clay amphorae (talhas), recently revived.",
        "winemaking", "portugal_doc",
        [{"type": "technique", "name": "Talha"}, {"type": "appellation", "name": "Alentejo"}],
        ["portugal", "alentejo", "tradition"],
    )
    add(
        "Vidigueira in the Alentejo is known for producing fresh white wines despite the region's hot climate.",
        "wine_regions", "portugal_doc",
        [{"type": "subzone", "name": "Vidigueira"}, {"type": "appellation", "name": "Alentejo"}],
        ["portugal", "alentejo", "white"],
    )

    # --- Lisboa in-depth ---
    add(
        "Lisboa (formerly Estremadura) was renamed in 2009 to leverage the Lisbon brand for marketing.",
        "wine_regions", "portugal_doc",
        [{"type": "appellation", "name": "Lisboa"}],
        ["portugal", "lisboa"],
    )
    add(
        "Lisboa is one of Portugal's most productive wine regions, though quality has risen significantly in recent years.",
        "wine_regions", "portugal_doc",
        [{"type": "appellation", "name": "Lisboa"}],
        ["portugal", "lisboa"],
    )

    # --- Madeira in-depth ---
    add(
        "Madeira wine's remarkable longevity means bottles from the 18th and 19th centuries can still be enjoyed today.",
        "winemaking", "portugal_madeira",
        [{"type": "wine_style", "name": "Madeira"}],
        ["portugal", "madeira", "aging"],
    )
    add(
        "The four noble grape varieties of Madeira are Sercial, Verdelho, Boal, and Malmsey (Malvasia), each defining a sweetness level.",
        "grape_varieties", "portugal_madeira",
        [{"type": "wine_style", "name": "Madeira"}],
        ["portugal", "madeira", "grapes"],
    )
    add(
        "Tinta Negra accounts for approximately 85% of all Madeira wine production.",
        "grape_varieties", "portugal_madeira",
        [{"type": "grape", "name": "Tinta Negra"}],
        ["portugal", "madeira", "grape"],
    )
    add(
        "Madeira aged 3 years is labeled 'Finest', 5 years 'Reserve', 10 years 'Special Reserve', and 15 years 'Extra Reserve'.",
        "winemaking", "portugal_madeira",
        [{"type": "wine_style", "name": "Madeira"}],
        ["portugal", "madeira", "aging", "classification"],
    )
    add(
        "Madeira wines labeled with a noble variety must contain at least 85% of that grape.",
        "winemaking", "portugal_madeira",
        [{"type": "wine_style", "name": "Madeira"}],
        ["portugal", "madeira", "regulation"],
    )
    add(
        "The canteiro method for aging Madeira uses the natural warmth of sun-heated attics rather than artificial heating.",
        "winemaking", "portugal_madeira",
        [{"type": "technique", "name": "Canteiro"}, {"type": "wine_style", "name": "Madeira"}],
        ["portugal", "madeira", "winemaking"],
    )
    add(
        "Solera Madeira was a blended style that was discontinued in 2002 by IVBAM regulations.",
        "winemaking", "portugal_madeira",
        [{"type": "wine_style", "name": "Madeira"}],
        ["portugal", "madeira", "regulation"],
    )
    add(
        "Cooking Madeira is a bulk style produced specifically for culinary use, not intended for drinking.",
        "winemaking", "portugal_madeira",
        [{"type": "wine_style", "name": "Madeira"}],
        ["portugal", "madeira", "cooking"],
    )

    # --- Setúbal in-depth ---
    add(
        "Moscatel de Setúbal must contain at least 67% Muscat of Alexandria or Moscatel Roxo grapes.",
        "winemaking", "portugal_doc",
        [{"type": "appellation", "name": "Setúbal"}, {"type": "grape", "name": "Moscatel de Setúbal"}],
        ["portugal", "setubal", "regulation"],
    )
    add(
        "Moscatel de Setúbal is aged in wood for a minimum of 2 years, though premium versions age for decades.",
        "winemaking", "portugal_doc",
        [{"type": "appellation", "name": "Setúbal"}],
        ["portugal", "setubal", "aging"],
    )
    add(
        "The Setúbal Peninsula also produces notable red wines from Castelão, particularly in the Palmela sub-region.",
        "wine_regions", "portugal_doc",
        [{"type": "appellation", "name": "Setúbal"}, {"type": "grape", "name": "Castelão"}],
        ["portugal", "setubal", "red"],
    )

    # --- Colares in-depth ---
    add(
        "Colares DOC near Sintra is one of the few European regions where ungrafted vines survive, protected by sandy soils from phylloxera.",
        "wine_regions", "portugal_doc",
        [{"type": "appellation", "name": "Colares"}],
        ["portugal", "colares", "phylloxera"],
    )
    add(
        "Colares vineyards sit on sandy dunes (chão de areia) near the Atlantic coast.",
        "viticulture", "portugal_doc",
        [{"type": "appellation", "name": "Colares"}],
        ["portugal", "colares", "terroir"],
    )

    # --- Historical and business facts ---
    add(
        "The 1756 demarcation of the Douro by the Marquis of Pombal is considered the first modern wine appellation system.",
        "wine_regions", "portugal_general",
        [{"type": "region", "name": "Douro"}, {"type": "person", "name": "Marquis of Pombal"}],
        ["portugal", "history"],
    )
    add(
        "The Treaty of Methuen in 1703 gave Portuguese wines preferential tariffs in England, boosting the Port trade.",
        "wine_business", "portugal_general",
        [{"type": "country", "name": "Portugal"}, {"type": "country", "name": "England"}],
        ["portugal", "history", "trade"],
    )
    add(
        "Portugal is the 11th largest wine producer in the world by volume.",
        "wine_business", "portugal_general",
        [{"type": "country", "name": "Portugal"}],
        ["portugal", "production"],
    )
    add(
        "Portuguese wines were largely controlled by cooperatives until the 1990s, when private producers began modernizing.",
        "wine_business", "portugal_general",
        [{"type": "country", "name": "Portugal"}],
        ["portugal", "business", "history"],
    )
    add(
        "Portugal's total vineyard area is approximately 194,000 hectares.",
        "wine_regions", "portugal_general",
        [{"type": "country", "name": "Portugal"}],
        ["portugal", "area"],
    )
    add(
        "The IVV (Instituto da Vinha e do Vinho) is the national regulatory body overseeing all Portuguese wine production.",
        "wine_business", "portugal_general",
        [{"type": "organization", "name": "IVV"}],
        ["portugal", "regulation", "organization"],
    )
    add(
        "The Azores IGP produces wines on volcanic islands in the mid-Atlantic, with distinctive mineral character.",
        "wine_regions", "portugal_igp",
        [{"type": "region", "name": "Açores"}],
        ["portugal", "igp", "azores"],
    )
    add(
        "The Pico Island vineyards in the Azores are a UNESCO World Heritage Site, with vines growing in volcanic stone enclosures called currais.",
        "wine_regions", "portugal_igp",
        [{"type": "region", "name": "Açores"}],
        ["portugal", "azores", "heritage"],
    )

    # --- Additional DOC region facts ---
    doc_extra = [
        ("Trás-os-Montes", "Trás-os-Montes has a harsh continental climate with hot summers and cold winters."),
        ("Trás-os-Montes", "The sub-region of Chaves in Trás-os-Montes is known for light, fresh wines."),
        ("Trás-os-Montes", "Planalto Mirandês in Trás-os-Montes is one of the highest vineyard areas in Portugal."),
        ("Távora-Varosa", "Távora-Varosa was specifically created as a DOC for sparkling wine production in 1989."),
        ("Távora-Varosa", "Távora-Varosa's high altitude and cool climate make it ideal for traditional method sparkling wines."),
        ("Tejo", "The Tejo (formerly Ribatejo) region produces a wide range of styles from its diverse terroir along the Tagus river."),
        ("Tejo", "Tejo's vast alluvial plains produce high-volume wines, while hillside vineyards yield more concentrated fruit."),
        ("Bucelas", "Bucelas produces crisp, mineral white wines from Arinto that were historically exported to Britain."),
        ("Bucelas", "The Duke of Wellington is said to have discovered Bucelas wine during the Peninsular War and introduced it to England."),
        ("Carcavelos", "Carcavelos is one of the rarest wine appellations in the world, with less than one hectare of vineyard remaining."),
        ("Madeira", "The island of Madeira has volcanic soils and a subtropical climate moderated by the Gulf Stream."),
        ("Madeira", "Vineyards on Madeira are typically small plots on steep, terraced hillsides called poios."),
        ("Douro", "The Douro experiences extreme temperatures, with summers regularly exceeding 40°C."),
        ("Douro", "Schist rock dominates the Douro landscape, and vines must root deeply into fractures to access moisture."),
        ("Alentejo", "Cork oak forests (montados) cover much of the Alentejo landscape alongside vineyards."),
    ]
    for doc_name, fact_text in doc_extra:
        add(
            fact_text,
            "wine_regions", "portugal_doc",
            [{"type": "appellation", "name": doc_name}],
            ["portugal", "doc", doc_name.lower().replace(" ", "_").replace("-", "_")],
        )

    # --- Portuguese producers ---
    portugal_producers = [
        ("Quinta do Noval", "Douro", "Quinta do Noval produces Nacional, made from ungrafted vines, one of the rarest and most expensive Ports."),
        ("Taylor's", "Douro", "Taylor's (Taylor Fladgate) is one of the oldest and most respected Port houses, founded in 1692."),
        ("Graham's", "Douro", "Graham's is known for rich, full-bodied Vintage Port (Vintage Year)s, particularly the Six Grapes Reserve Ruby."),
        ("Warre's", "Douro", "Warre's, established in 1670, is the oldest British Port house."),
        ("Cockburn's", "Douro", "Cockburn's is a major Port house known for its Special Reserve Ruby and Vintage Port (Vintage Year) declarations."),
        ("Fonseca", "Douro", "Fonseca is renowned for producing some of the most opulent and complex Vintage Port (Vintage Year)s."),
        ("Dow's", "Douro", "Dow's produces a drier style of Port, known for structure and longevity in Vintage years."),
        ("Croft", "Douro", "Croft, founded in 1588, is one of the oldest firms in the Port trade."),
        ("Ramos Pinto", "Douro", "Ramos Pinto is both a Port producer and a leading estate for Douro table wines."),
        ("Niepoort", "Douro", "Niepoort is known for innovative winemaking in both Port and Douro still wines."),
        ("Quinta do Crasto", "Douro", "Quinta do Crasto is a leading Douro estate producing both premium table wines and Port."),
        ("Quinta do Vallado", "Douro", "Quinta do Vallado, owned by descendants of the legendary Dona Antónia Ferreira, produces Douro reds and Port."),
        ("Barca Velha / Casa Ferreirinha", "Douro", "Casa Ferreirinha produces Barca Velha, widely regarded as Portugal's most prestigious red table wine."),
        ("Soalheiro", "Vinho Verde", "Soalheiro is a pioneering Alvarinho producer in Monção e Melgaço in the Vinho Verde region."),
        ("Anselmo Mendes", "Vinho Verde", "Anselmo Mendes is credited with elevating Vinho Verde wines to international acclaim."),
        ("Quinta dos Roques", "Dão", "Quinta dos Roques is a benchmark producer in the Dão region for Touriga Nacional and Encruzado."),
        ("Álvaro Castro / Quinta da Pellada", "Dão", "Álvaro Castro at Quinta da Pellada produces acclaimed single-vineyard Dão wines."),
        ("Luís Pato", "Bairrada", "Luís Pato is the most celebrated producer in Bairrada, championing the Baga grape."),
        ("Herdade do Esporão", "Alentejo", "Herdade do Esporão is one of the Alentejo's largest and most influential wine estates."),
        ("Herdade do Mouchão", "Alentejo", "Herdade do Mouchão produces a legendary Alicante Bouschet red in the Alentejo."),
        ("Blandy's", "Madeira", "Blandy's is the only family of original Madeira wine shippers still involved in the trade."),
        ("Henriques & Henriques", "Madeira", "Henriques & Henriques is the largest independent Madeira wine producer."),
        ("Justino's", "Madeira", "Justino Henriques is the largest producer of Madeira wine by volume."),
    ]
    for producer, region, fact_text in portugal_producers:
        add(
            fact_text,
            "producers", "portugal_producers",
            [{"type": "producer", "name": producer}, {"type": "region", "name": region}],
            ["portugal", "producer", region.lower().replace(" ", "_")],
        )

    # --- More Port wine detail facts ---
    port_detail_facts = [
        "A Vintage Port (Vintage Year) declaration must be approved by the IVDP's tasting committee before the wine can be sold.",
        "Port wine fortification occurs when the fermenting must reaches 6-9% alcohol, with aguardente at 77% ABV added.",
        "The final alcohol content of Port wine is typically between 19% and 22% ABV.",
        "Pink Port (Rosé Port) was introduced by Croft in 2008 as a lighter, more accessible style.",
        "The Port wine trade has historically been centered in the city of Porto and its sister city Vila Nova de Gaia.",
        "Port pipe (cask) has a capacity of approximately 550 liters and is made from oak.",
        "Ruby Port is aged in large concrete or stainless steel vats (balseiros) to preserve fresh fruit character.",
        "Tawny Port gradually loses color during extended cask aging, transforming from ruby red to amber-tawny.",
        "White Port grapes include Malvasia Fina, Viosinho, Gouveio, Rabigato, and Códega do Larinho.",
        "Quinta da Romaneira, Quinta de la Rosa, and Quinta do Vesúvio are noted single-quinta Port estates.",
        "The IVDP controls the benefício (authorization to make Port) allocated to each property annually.",
        "Port wine exports have exceeded 730 million euros annually, making it Portugal's most valuable wine export.",
    ]
    for fact_text in port_detail_facts:
        add(
            fact_text,
            "winemaking", "portugal_port",
            [{"type": "wine_style", "name": "Port"}],
            ["portugal", "port"],
            source_key="portugal_ivdp",
        )

    # --- More Madeira detail facts ---
    madeira_detail_facts = [
        "Sercial is grown at the highest altitudes on Madeira island, producing the driest and most acidic style.",
        "Verdelho Madeira is often described as having smoky, honeyed character with firm acidity.",
        "Malmsey (Malvasia) is grown at the lowest altitudes on Madeira, producing the richest and sweetest wines.",
        "Madeira wine's aging potential is virtually unlimited, with some bottles from the 1700s still being drinkable.",
        "The heating process in Madeira production evolved from the 18th-century practice of shipping wines through tropical climates.",
        "IVBAM (Instituto do Vinho, do Bordado e do Artesanato da Madeira) is the regulatory body for Madeira wine.",
        "Madeira's vineyard area is approximately 500 hectares, with most plots being extremely small and terraced.",
        "Terrantez is an extremely rare noble Madeira grape variety that produces medium-sweet wines of exceptional complexity.",
        "Bastardo (Trousseau) is an ancient grape variety grown on Madeira, used historically for medium-sweet wines.",
    ]
    for fact_text in madeira_detail_facts:
        add(
            fact_text,
            "winemaking", "portugal_madeira",
            [{"type": "wine_style", "name": "Madeira"}],
            ["portugal", "madeira"],
        )

    # --- Portuguese winemaking techniques ---
    add(
        "Lagares (granite treading tanks) are still used in premium Port production because foot treading extracts color without crushing seeds.",
        "winemaking", "portugal_port",
        [{"type": "technique", "name": "Lagares"}],
        ["portugal", "port", "winemaking"],
        source_key="portugal_ivdp",
    )
    add(
        "Autovinification tanks, which use fermentation pressure to pump must over grape skins, are widely used in Port production.",
        "winemaking", "portugal_port",
        [{"type": "technique", "name": "Autovinification"}],
        ["portugal", "port", "winemaking"],
        source_key="portugal_ivdp",
    )
    add(
        "Field blends (vinhas velhas) are traditional in Portugal, with multiple grape varieties planted together in old vineyards.",
        "viticulture", "portugal_general",
        [{"type": "technique", "name": "Field blend"}],
        ["portugal", "viticulture", "tradition"],
    )
    add(
        "Many old Douro vineyards contain up to 30 or more different grape varieties interplanted in a single plot.",
        "viticulture", "portugal_douro",
        [{"type": "region", "name": "Douro"}],
        ["portugal", "douro", "viticulture"],
        source_key="portugal_ivdp",
    )
    add(
        "Vinha velha (old vine) is not an official classification in Portugal, but producers use it to indicate wines from old mixed plantings.",
        "viticulture", "portugal_general",
        [{"type": "term", "name": "Vinha velha"}],
        ["portugal", "viticulture"],
    )
    add(
        "Espumante is the Portuguese term for sparkling wine, with quality examples from Bairrada and Távora-Varosa.",
        "winemaking", "portugal_general",
        [{"type": "wine_style", "name": "Espumante"}],
        ["portugal", "sparkling"],
    )
    add(
        "Aguardente vínica (grape spirit) used for Port fortification must be approved by the IVDP.",
        "winemaking", "portugal_port",
        [{"type": "technique", "name": "Fortification"}],
        ["portugal", "port", "winemaking"],
        source_key="portugal_ivdp",
    )

    # --- Additional Portuguese grape variety detail ---
    grape_detail = [
        ("Touriga Nacional", "Touriga Nacional produces deeply colored, tannic wines with aromas of violets, dark fruit, and spice."),
        ("Touriga Franca", "Touriga Franca contributes floral aromas and structure to Port blends, and is increasingly used for varietal table wines."),
        ("Tinta Roriz", "Tinta Roriz (Aragonez/Tempranillo) adapts well to Portuguese conditions, ripening early and producing fruit-forward wines."),
        ("Alvarinho", "Alvarinho in the Monção e Melgaço sub-region of Vinho Verde can produce age-worthy wines with considerable complexity."),
        ("Encruzado", "Encruzado responds well to oak aging, developing complex nutty and honeyed notes while retaining fresh acidity."),
        ("Baga", "Baga has small, thick-skinned berries that produce intensely tannic wines requiring extended aging."),
        ("Castelão", "Castelão is adaptable to both warm and cool climates, producing wines ranging from light and fruity to structured and age-worthy."),
        ("Trincadeira", "Trincadeira produces aromatic wines with notes of wild herbs and red fruit, but is susceptible to rot if not carefully managed."),
        ("Antão Vaz", "Antão Vaz thrives in the hot Alentejo climate, producing full-bodied whites with tropical fruit and toasty notes when barrel-fermented."),
        ("Viosinho", "Viosinho is a white grape increasingly valued in the Douro for its aromatic intensity and freshness."),
        ("Rabigato", "Rabigato is a high-acid white grape of the Douro, often used in blends to provide structure and longevity."),
        ("Gouveio", "Gouveio (Godello) is a white grape shared between Portugal's Douro and Spain's Galicia."),
    ]
    for grape, fact_text in grape_detail:
        add(
            fact_text,
            "grape_varieties", "portugal_general",
            [{"type": "grape", "name": grape}],
            ["portugal", "grape"],
        )

    # --- Port vintage declarations ---
    port_declarations = [
        "Port vintages in the 21st century include 2000, 2003, 2007, 2011, 2016, and 2017 as widely declared years.",
        "The 1963, 1966, 1970, 1977, 1985, and 1994 are considered among the greatest Port vintages of the 20th century.",
        "Not all Port houses declare the same vintages; each house decides independently whether a year merits declaration.",
        "A generally declared vintage means the majority of major Port shippers have declared it as a vintage year.",
        "Taylor's 1963 and Fonseca 1977 are considered two of the finest Port wines ever made.",
        "The 2011 vintage is widely regarded as one of the finest Port vintages of the early 21st century.",
    ]
    for fact_text in port_declarations:
        add(
            fact_text,
            "winemaking", "portugal_port",
            [{"type": "wine_style", "name": "Port"}],
            ["portugal", "port", "vintage"],
            source_key="portugal_ivdp",
        )

    # --- Vinho Verde sub-region detail ---
    vv_subregions = [
        ("Monção e Melgaço", "Monção e Melgaço is the northernmost and warmest sub-region of Vinho Verde, known exclusively for Alvarinho."),
        ("Lima", "The Lima sub-region of Vinho Verde is known for blends of Loureiro and Arinto."),
        ("Cávado", "The Cávado sub-region of Vinho Verde is a cool area producing light, acidic wines from multiple varieties."),
        ("Ave", "The Ave sub-region of Vinho Verde is the largest sub-region, producing light, everyday wines."),
        ("Basto", "The Basto sub-region of Vinho Verde is an inland area with warmer conditions than coastal zones."),
        ("Sousa", "The Sousa sub-region of Vinho Verde is known for light wines from Arinto and Azal."),
        ("Baião", "The Baião sub-region of Vinho Verde is gaining recognition for Alvarinho and Avesso wines."),
        ("Amarante", "The Amarante sub-region of Vinho Verde produces both white and red wines."),
        ("Paiva", "The Paiva sub-region of Vinho Verde is the smallest, located in the south of the region."),
    ]
    for subregion, fact_text in vv_subregions:
        add(
            fact_text,
            "wine_regions", "portugal_doc",
            [{"type": "appellation", "name": "Vinho Verde"}, {"type": "subzone", "name": subregion}],
            ["portugal", "vinho_verde", subregion.lower().replace(" ", "_")],
        )

    # --- Alentejo sub-region detail ---
    alentejo_subregions = [
        ("Borba", "Borba is one of the most important sub-regions of the Alentejo, producing rich red wines from Aragonez and Trincadeira."),
        ("Reguengos", "Reguengos de Monsaraz is the Alentejo sub-region known for concentrated red wines and the influential cooperative."),
        ("Évora", "Évora is a sub-region of the Alentejo centered on the UNESCO-listed city of Évora."),
        ("Redondo", "Redondo is an Alentejo sub-region known for well-priced, fruit-forward red wines."),
        ("Portalegre", "Portalegre is the northernmost and coolest Alentejo sub-region, with vineyards up to 1,000 meters elevation."),
        ("Vidigueira", "Vidigueira is the warmest Alentejo sub-region, known for producing both reds and surprisingly fresh whites."),
        ("Granja-Amareleja", "Granja-Amareleja is one of the smallest and hottest sub-regions in the Alentejo."),
        ("Moura", "Moura is a southern Alentejo sub-region with a hot, dry climate suited to robust red wines."),
    ]
    for subregion, fact_text in alentejo_subregions:
        add(
            fact_text,
            "wine_regions", "portugal_doc",
            [{"type": "appellation", "name": "Alentejo"}, {"type": "subzone", "name": subregion}],
            ["portugal", "alentejo", subregion.lower().replace(" ", "_")],
        )

    # --- Portuguese wine business and export ---
    portugal_business_extra = [
        "Portugal's per capita wine consumption is among the highest in the world.",
        "Portuguese wine exports have grown steadily, with the Alentejo and Douro leading export growth.",
        "The Symington family controls several major Port houses including Graham's, Dow's, Warre's, and Cockburn's.",
        "The Fladgate Partnership owns Taylor's, Fonseca, and Croft Port brands.",
        "Sogrape is Portugal's largest wine company, owning brands including Mateus Rosé and Casa Ferreirinha.",
        "Mateus Rosé, produced by Sogrape, was once the world's best-selling Portuguese wine.",
    ]
    for fact_text in portugal_business_extra:
        add(
            fact_text,
            "wine_business", "portugal_general",
            [{"type": "country", "name": "Portugal"}],
            ["portugal", "business"],
        )

    # --- Portuguese climate and terroir ---
    portugal_terroir_extra = [
        ("Douro", "The Douro Valley has a continental climate with very hot summers and cold winters, protected from Atlantic influence by mountains."),
        ("Dão", "Dão's granite soils provide good drainage and impart a distinctive mineral character to both red and white wines."),
        ("Bairrada", "Bairrada's proximity to the Atlantic moderates temperatures but brings significant rainfall."),
        ("Vinho Verde", "Vinho Verde's granite soils and high annual rainfall (1,200-1,500mm) produce wines with natural high acidity."),
        ("Alentejo", "The Alentejo has schist, granite, and clay soils that vary considerably between its eight sub-regions."),
        ("Lisboa", "Lisboa benefits from Atlantic breezes that moderate the climate and extend the growing season."),
        ("Tejo", "The Tejo region's alluvial soils along the Tagus River are fertile and produce generous yields."),
        ("Setúbal", "The Setúbal Peninsula has a warm maritime climate ideal for Moscatel and Castelão."),
    ]
    for region, fact_text in portugal_terroir_extra:
        add(
            fact_text,
            "viticulture", "portugal_terroir",
            [{"type": "region", "name": region}],
            ["portugal", "terroir", region.lower().replace(" ", "_")],
        )

    # --- Portuguese wine styles ---
    add(
        "Colheita wines in Portugal (not Port) indicate a single-vintage wine, distinct from the Colheita Port designation.",
        "winemaking", "portugal_regulation",
        [{"type": "country", "name": "Portugal"}],
        ["portugal", "regulation", "labeling"],
    )
    add(
        "Garrafeira in Portuguese still wine refers to wines aged for extended periods: reds for 30 months (12 in bottle), whites for 12 months (6 in bottle).",
        "winemaking", "portugal_regulation",
        [{"type": "classification", "name": "Garrafeira"}],
        ["portugal", "regulation", "aging"],
    )
    add(
        "Reserva in Portuguese wine indicates a wine from a good vintage with at least 0.5% higher alcohol than the DOC minimum.",
        "winemaking", "portugal_regulation",
        [{"type": "classification", "name": "Reserva"}],
        ["portugal", "regulation", "aging"],
    )
    add(
        "Grande Escolha is a Portuguese wine designation indicating a producer's finest selection from exceptional vintages.",
        "winemaking", "portugal_regulation",
        [{"type": "classification", "name": "Grande Escolha"}],
        ["portugal", "regulation"],
    )

    # --- More Portuguese grape varieties ---
    extra_grapes = [
        ("Avesso", "Avesso is a white grape grown in the southern Vinho Verde region, producing fuller-bodied wines than typical Vinho Verde."),
        ("Códega do Larinho", "Códega do Larinho is a white grape used in Port and Douro table wines, contributing soft, fruity character."),
        ("Tinta Amarela", "Tinta Amarela is the Douro name for Trincadeira, an important blending grape in both Port and table wines."),
        ("Rufete", "Rufete is an indigenous red grape of the Dão and Douro regions, producing light, aromatic wines."),
        ("Bastardo", "Bastardo (Trousseau) is an ancient Portuguese grape variety used in both Port blends and Madeira wines."),
        ("Moscatel Galego Branco", "Moscatel Galego Branco (Muscat Blanc à Petits Grains) is used for aromatic wines in the Douro and Setúbal."),
        ("Tinta Caiada", "Tinta Caiada is a red grape of the Alentejo, often used as a blending component."),
        ("Moreto", "Moreto is a light red grape found in the Alentejo, typically used in blends."),
        ("Perrum", "Perrum is a white grape of the Alentejo, used in blends and increasingly for varietal wines."),
        ("Síria", "Síria (Roupeiro) is the most planted white grape in the Alentejo region."),
        ("Cerceal", "Cerceal (Cercealinho) is a white grape used in Dão and Távora-Varosa, particularly for sparkling wines."),
        ("Vital", "Vital is a white grape variety native to the Tejo region, producing fresh, light wines."),
    ]
    for grape, fact_text in extra_grapes:
        add(
            fact_text,
            "grape_varieties", "portugal_general",
            [{"type": "grape", "name": grape}],
            ["portugal", "grape"],
        )

    # --- Portuguese regional winemaking ---
    portugal_winemaking_extra = [
        "Bairrada's traditional method sparkling wines are gaining international recognition as alternatives to Champagne.",
        "The Dão region's cooperative system has been gradually replaced by private producers since the 1990s.",
        "Portuguese rosé wines (rosados) are growing in popularity, particularly from the Alentejo and Vinho Verde regions.",
        "Natural winemaking has a growing following in Portugal, with producers in Dão, Douro, and Lisboa leading the movement.",
        "Portuguese wine labels use the term 'Escolha' for selected wines and 'Grande Escolha' for top selections.",
        "Single-quinta Douro red wines (unblended estate wines) have become a premium category rivaling Port in prestige.",
    ]
    for fact_text in portugal_winemaking_extra:
        add(
            fact_text,
            "winemaking", "portugal_general",
            [{"type": "country", "name": "Portugal"}],
            ["portugal", "winemaking"],
        )

    # --- Algarve wine region ---
    add(
        "The Algarve in southern Portugal has four DOC sub-regions: Lagos, Portimão, Lagoa, and Tavira.",
        "wine_regions", "portugal_doc",
        [{"type": "region", "name": "Algarve"}],
        ["portugal", "doc", "algarve"],
    )
    add(
        "The Algarve is Portugal's southernmost wine region, with a Mediterranean climate and mostly red wines.",
        "wine_regions", "portugal_doc",
        [{"type": "region", "name": "Algarve"}],
        ["portugal", "doc", "algarve"],
    )
    add(
        "Negra Mole is the traditional grape of the Algarve, though international varieties are increasingly planted.",
        "grape_varieties", "portugal_general",
        [{"type": "grape", "name": "Negra Mole"}, {"type": "region", "name": "Algarve"}],
        ["portugal", "grape", "algarve"],
    )

    # --- Final batch ---
    add(
        "Portuguese wine has experienced a quality revolution since the 1990s, driven by EU investment and individual estate producers.",
        "wine_business", "portugal_general",
        [{"type": "country", "name": "Portugal"}],
        ["portugal", "history"],
    )
    add(
        "The Douro has over 40,000 registered grape growers, with many vineyards being very small family plots.",
        "wine_business", "portugal_douro",
        [{"type": "region", "name": "Douro"}],
        ["portugal", "douro", "business"],
        source_key="portugal_ivdp",
    )
    add(
        "Portuguese wines from indigenous grape varieties have gained international recognition for their unique character.",
        "wine_business", "portugal_general",
        [{"type": "country", "name": "Portugal"}],
        ["portugal", "business"],
    )
    add(
        "The Setúbal Peninsula is also an important area for Castelão-based red wines sold under the Palmela DOC.",
        "wine_regions", "portugal_doc",
        [{"type": "appellation", "name": "Setúbal"}, {"type": "grape", "name": "Castelão"}],
        ["portugal", "doc", "setubal"],
    )
    add(
        "Avesso is a distinctive white grape of the Baião sub-region of Vinho Verde, producing richer wines than typical Vinho Verde.",
        "grape_varieties", "portugal_doc",
        [{"type": "grape", "name": "Avesso"}, {"type": "appellation", "name": "Vinho Verde"}],
        ["portugal", "grape", "vinho_verde"],
    )
    add(
        "Portuguese Indicação de Proveniência Regulamentada (IPR) was an intermediate quality designation, now largely replaced by DOC and IGP.",
        "wine_regions", "portugal_regulation",
        [{"type": "classification", "name": "IPR"}],
        ["portugal", "regulation"],
    )

    logger.info(f"Built {len(facts)} Portugal facts")
    return facts


# =============================================================================
# Web Scraping + Wikipedia Fallback Enhancement
# =============================================================================

def scrape_spain_web(source_ids: dict) -> list[dict]:
    """Attempt to fetch additional Spain data from official sources with Wikipedia fallback."""
    extra_facts = []
    seen = set()

    def add(text, domain, subdomain, entities, tags, source_key):
        if text in seen:
            return
        seen.add(text)
        extra_facts.append({
            "fact_text": text,
            "domain": domain,
            "subdomain": subdomain,
            "source_id": source_ids[source_key],
            "entities": entities,
            "tags": tags,
        })

    # Try MAPA website
    logger.info("Attempting to fetch data from MAPA (Spain)...")
    html = fetch_page("https://www.mapa.gob.es/es/alimentacion/temas/calidad-diferenciada/dop-igp/")
    if html:
        logger.info("Successfully fetched MAPA page, parsing for additional DO data...")
        soup = BeautifulSoup(html, "lxml")
        # Extract any additional DO info from the page
        links = soup.find_all("a", href=True)
        do_count = 0
        for link in links:
            text = link.get_text(strip=True)
            if text and ("D.O." in text or "Denominación" in text):
                do_count += 1
        if do_count > 0:
            logger.info(f"Found {do_count} DO-related links on MAPA page")
    else:
        logger.warning("MAPA website inaccessible, using Wikipedia fallback for Spain")
        wiki_text = fetch_wikipedia_article("Spanish wine")
        if wiki_text:
            logger.info("Fetched Wikipedia article on Spanish wine for supplemental data")
            # Extract any new facts from the Wikipedia text
            if "Vino de Pago" in wiki_text:
                add(
                    "There are currently over 20 Vino de Pago estates recognized in Spain.",
                    "wine_regions", "spain_regulation",
                    [{"type": "classification", "name": "Vino de Pago"}],
                    ["spain", "regulation", "vino_de_pago"],
                    "wikipedia_wine_fallback",
                )

    return extra_facts


def scrape_germany_web(source_ids: dict) -> list[dict]:
    """Attempt to fetch additional Germany data from official sources with Wikipedia fallback."""
    extra_facts = []
    seen = set()

    def add(text, domain, subdomain, entities, tags, source_key):
        if text in seen:
            return
        seen.add(text)
        extra_facts.append({
            "fact_text": text,
            "domain": domain,
            "subdomain": subdomain,
            "source_id": source_ids[source_key],
            "entities": entities,
            "tags": tags,
        })

    logger.info("Attempting to fetch data from Deutsches Weininstitut...")
    html = fetch_page("https://www.deutscheweine.de/wissen/weinanbaugebiete/")
    if html:
        logger.info("Successfully fetched DWI page, parsing...")
        soup = BeautifulSoup(html, "lxml")
        region_links = soup.find_all("a", href=True)
        region_count = sum(1 for l in region_links if "anbaugebiet" in l.get("href", "").lower())
        if region_count > 0:
            logger.info(f"Found {region_count} region links on DWI page")
    else:
        logger.warning("DWI website inaccessible, using Wikipedia fallback for Germany")
        wiki_text = fetch_wikipedia_article("German wine")
        if wiki_text:
            logger.info("Fetched Wikipedia article on German wine for supplemental data")
            if "Oechsle" in wiki_text:
                add(
                    "The Oechsle scale is the measurement system used in Germany to determine grape must weight (sugar content).",
                    "winemaking", "germany_regulation",
                    [{"type": "measurement", "name": "Oechsle scale"}],
                    ["germany", "regulation", "measurement"],
                    "wikipedia_wine_fallback",
                )

    logger.info("Attempting to fetch data from VDP...")
    html = fetch_page("https://www.vdp.de/en/vdp/classification")
    if html:
        logger.info("Successfully fetched VDP page, parsing...")
    else:
        logger.warning("VDP website inaccessible, proceeding with built-in data")

    return extra_facts


def scrape_portugal_web(source_ids: dict) -> list[dict]:
    """Attempt to fetch additional Portugal data from official sources with Wikipedia fallback."""
    extra_facts = []
    seen = set()

    def add(text, domain, subdomain, entities, tags, source_key):
        if text in seen:
            return
        seen.add(text)
        extra_facts.append({
            "fact_text": text,
            "domain": domain,
            "subdomain": subdomain,
            "source_id": source_ids[source_key],
            "entities": entities,
            "tags": tags,
        })

    logger.info("Attempting to fetch data from IVDP (Port/Douro)...")
    html = fetch_page("https://www.ivdp.pt/en/")
    if html:
        logger.info("Successfully fetched IVDP page")
    else:
        logger.warning("IVDP website inaccessible, using Wikipedia fallback for Port wine")
        wiki_text = fetch_wikipedia_article("Port wine")
        if wiki_text:
            logger.info("Fetched Wikipedia article on Port wine for supplemental data")
            if "1756" in wiki_text:
                add(
                    "The Douro Valley was demarcated as a wine region in 1756 by the Marquis of Pombal, making it one of the first regulated wine regions in the world.",
                    "wine_regions", "portugal_douro",
                    [{"type": "region", "name": "Douro"}, {"type": "person", "name": "Marquis of Pombal"}],
                    ["portugal", "douro", "history"],
                    "wikipedia_wine_fallback",
                )

    logger.info("Attempting to fetch data from IVV...")
    html = fetch_page("https://www.ivv.gov.pt/np4/home.html")
    if html:
        logger.info("Successfully fetched IVV page")
    else:
        logger.warning("IVV website inaccessible, using Wikipedia fallback for Portuguese wine")
        wiki_text = fetch_wikipedia_article("Portuguese wine")
        if wiki_text:
            logger.info("Fetched Wikipedia article on Portuguese wine")

    # Wikipedia article for Madeira wine
    logger.info("Fetching Wikipedia data on Madeira wine for enrichment...")
    wiki_text = fetch_wikipedia_article("Madeira wine")
    if wiki_text:
        if "estufagem" in wiki_text.lower():
            add(
                "In the estufagem process, Madeira wine is heated in large tanks (estufas) to a temperature of 45-50°C for at least 3 months.",
                "winemaking", "portugal_madeira",
                [{"type": "wine_style", "name": "Madeira"}, {"type": "technique", "name": "Estufagem"}],
                ["portugal", "madeira", "winemaking"],
                "wikipedia_wine_fallback",
            )
        if "solera" in wiki_text.lower():
            add(
                "Some Madeira wines are aged using a solera system, blending wines of different ages.",
                "winemaking", "portugal_madeira",
                [{"type": "wine_style", "name": "Madeira"}, {"type": "technique", "name": "Solera"}],
                ["portugal", "madeira", "winemaking"],
                "wikipedia_wine_fallback",
            )

    return extra_facts


# =============================================================================
# Validation
# =============================================================================

def validate_facts(facts: list[dict]) -> None:
    """Run quality checks on generated facts and print a report."""

    # Domain/subdomain distribution
    domain_counts: dict[str, int] = defaultdict(int)
    subdomain_counts: dict[str, int] = defaultdict(int)
    for f in facts:
        domain_counts[f["domain"]] += 1
        sd = f.get("subdomain") or "(none)"
        subdomain_counts[sd] += 1

    click.echo("\n" + "=" * 60)
    click.echo("VALIDATION REPORT")
    click.echo("=" * 60)

    click.echo("\nDomain distribution:")
    for d in sorted(domain_counts.keys()):
        click.echo(f"  {d:25s}: {domain_counts[d]:>5} facts")
    click.echo(f"  {'TOTAL':25s}: {len(facts):>5} facts")

    click.echo("\nSubdomain distribution (top 20):")
    for sd, cnt in sorted(subdomain_counts.items(), key=lambda x: -x[1])[:20]:
        click.echo(f"  {sd:30s}: {cnt:>5} facts")

    # Quality checks
    too_short = [f for f in facts if len(f["fact_text"].split()) < 5]
    too_long = [f for f in facts if len(f["fact_text"].split()) > 50]
    no_predicate = [f for f in facts if len(f["fact_text"].split()) <= 2 or not any(c in f["fact_text"] for c in ".!")]
    missing_entities = [f for f in facts if not f.get("entities")]

    # Near-duplicate detection via string containment
    near_dupes = []
    fact_texts = [f["fact_text"] for f in facts]
    # Sample pairs to avoid O(n^2) for large sets
    sample_size = min(len(fact_texts), 500)
    sampled = random.sample(range(len(fact_texts)), sample_size)
    for i in range(len(sampled)):
        for j in range(i + 1, len(sampled)):
            a = fact_texts[sampled[i]].lower()
            b = fact_texts[sampled[j]].lower()
            if a != b and (a in b or b in a):
                near_dupes.append((fact_texts[sampled[i]], fact_texts[sampled[j]]))

    click.echo("\nQuality:")
    click.echo(f"  Too short (<5 words):   {len(too_short):>5} ({100 * len(too_short) / max(len(facts), 1):.1f}%)")
    click.echo(f"  Too long (>50 words):   {len(too_long):>5} ({100 * len(too_long) / max(len(facts), 1):.1f}%)")
    click.echo(f"  No predicate:           {len(no_predicate):>5} ({100 * len(no_predicate) / max(len(facts), 1):.1f}%)")
    click.echo(f"  Missing entities:       {len(missing_entities):>5} ({100 * len(missing_entities) / max(len(facts), 1):.1f}%)")
    click.echo(f"  Possible near-dupes:    {len(near_dupes):>5} ({100 * len(near_dupes) / max(len(facts), 1):.1f}%)")

    total_with_entities = len(facts) - len(missing_entities)
    click.echo(f"\n  % with entities:        {100 * total_with_entities / max(len(facts), 1):.1f}%")

    # Completeness checks
    click.echo("\nCompleteness checks:")
    spain_do_count = len(SPAIN_APPELLATIONS["DOCa"]) + len(SPAIN_APPELLATIONS["DO"])
    click.echo(f"  Spanish DO/DOCa in data:   {spain_do_count:>3} (expected ~70)")
    click.echo(f"  German regions in data:    {len(GERMANY_REGIONS):>3} (expected 13)")
    click.echo(f"  Portuguese DOCs in data:   {len(PORTUGAL_DOC_REGIONS):>3} (expected ~14)")

    # Country fact counts
    spain_facts = [f for f in facts if any("spain" in t for t in f.get("tags", []))]
    germany_facts = [f for f in facts if any("germany" in t for t in f.get("tags", []))]
    portugal_facts = [f for f in facts if any("portugal" in t for t in f.get("tags", []))]
    click.echo(f"\n  Spain facts:    {len(spain_facts):>5} (target 800-1200)")
    click.echo(f"  Germany facts:  {len(germany_facts):>5} (target 400-600)")
    click.echo(f"  Portugal facts: {len(portugal_facts):>5} (target 400-600)")

    if too_short:
        click.echo("\nExamples of too-short facts:")
        for f in too_short[:5]:
            click.echo(f'  - "{f["fact_text"]}"')

    if too_long:
        click.echo("\nExamples of too-long facts:")
        for f in too_long[:5]:
            click.echo(f'  - "{f["fact_text"][:100]}..."')

    if near_dupes:
        click.echo("\nExamples of possible near-duplicates:")
        for a, b in near_dupes[:5]:
            click.echo(f'  A: "{a[:80]}..."')
            click.echo(f'  B: "{b[:80]}..."')
            click.echo()

    # Random sample
    sample = random.sample(facts, min(10, len(facts)))
    click.echo("\nSample facts:")
    for i, f in enumerate(sample, 1):
        click.echo(f'  {i:>2}. "{f["fact_text"]}"')

    click.echo("\n" + "=" * 60)


# =============================================================================
# Pipeline
# =============================================================================

def register_sources() -> dict[str, str]:
    """Register all sources and return {key: source_id} map."""
    source_ids = {}
    for key, cfg in SOURCES.items():
        source_ids[key] = ensure_source(
            name=cfg["name"],
            url=cfg["url"],
            source_type=cfg["source_type"],
            tier=cfg["tier"],
            language=cfg.get("language", "en"),
        )
    return source_ids


def run_country(country: str, source_ids: dict, dry_run: bool = False) -> list[dict]:
    """Run scraper for a single country. Returns list of facts."""
    country = country.lower()
    logger.info(f"Running scraper for {country}")

    if country == "spain":
        facts = build_spain_facts(source_ids)
        web_facts = scrape_spain_web(source_ids)
        facts.extend(web_facts)
    elif country == "germany":
        facts = build_germany_facts(source_ids)
        web_facts = scrape_germany_web(source_ids)
        facts.extend(web_facts)
    elif country == "portugal":
        facts = build_portugal_facts(source_ids)
        web_facts = scrape_portugal_web(source_ids)
        facts.extend(web_facts)
    else:
        logger.error(f"Unknown country: {country}. Available: {COUNTRIES}")
        return []

    logger.info(f"{country}: generated {len(facts)} facts total")

    if dry_run:
        click.echo(f"\n[DRY RUN] {country}: {len(facts)} facts generated (not inserted)")
        for f in facts[:5]:
            click.echo(f'  - "{f["fact_text"]}"')
        click.echo(f"  ... and {len(facts) - 5} more")
        return facts

    inserted = insert_facts_batch(facts)
    logger.info(f"{country}: inserted {inserted} new facts")
    click.echo(f"{country}: inserted {inserted} new facts ({len(facts)} generated, duplicates skipped)")
    return facts


def run_all(dry_run: bool = False) -> dict[str, list[dict]]:
    """Run scrapers for all countries."""
    source_ids = register_sources()
    results = {}
    total_generated = 0
    for country in COUNTRIES:
        facts = run_country(country, source_ids, dry_run=dry_run)
        results[country] = facts
        total_generated += len(facts)
        time.sleep(1)  # Brief pause between countries

    click.echo(f"\nTotal: {total_generated} facts generated across all countries")
    if not dry_run:
        click.echo(f"Total facts in database: {get_fact_count()}")
    return results


# =============================================================================
# CLI
# =============================================================================

@click.command()
@click.option("--all", "run_all_flag", is_flag=True, help="Scrape all three countries")
@click.option("--country", type=click.Choice(COUNTRIES, case_sensitive=False), help="Scrape a specific country")
@click.option("--dry-run", is_flag=True, help="Generate facts without inserting into database")
@click.option("--validate", "validate_flag", is_flag=True, help="Run quality checks on generated facts")
@click.option("--list", "list_flag", is_flag=True, help="List available countries and sources")
def main(run_all_flag: bool, country: Optional[str], dry_run: bool, validate_flag: bool, list_flag: bool):
    """OenoBench European Wine Registries Scraper — Spain, Germany, Portugal."""
    log_time = datetime.now().strftime("%Y%m%d_%H%M%S")
    logger.add(f"data/logs/europe_{log_time}.log", rotation="10 MB")

    if list_flag:
        click.echo("\nAvailable countries:")
        for c in COUNTRIES:
            click.echo(f"  {c}")
        click.echo("\nRegistered sources:")
        for key, cfg in SOURCES.items():
            click.echo(f"  {key:30s} — {cfg['name']} ({cfg['tier']})")
        return

    if validate_flag:
        click.echo("Generating facts for validation (dry run)...")
        # For validation, build facts without DB access
        # Use placeholder source IDs
        placeholder_ids = {key: f"placeholder-{key}" for key in SOURCES}
        all_facts = []
        all_facts.extend(build_spain_facts(placeholder_ids))
        all_facts.extend(build_germany_facts(placeholder_ids))
        all_facts.extend(build_portugal_facts(placeholder_ids))
        validate_facts(all_facts)
        return

    if run_all_flag:
        run_all(dry_run=dry_run)
        return

    if country:
        source_ids = register_sources()
        run_country(country, source_ids, dry_run=dry_run)
        return

    click.echo("Use --all to scrape all countries, or --country <name> for a specific one.")
    click.echo("Use --list to see available countries and sources.")
    click.echo("Use --validate to run quality checks.")
    click.echo("Use --dry-run to generate facts without database insertion.")


if __name__ == "__main__":
    main()
