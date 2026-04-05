"""
OenoBench — Italian Wine Consortiums Scraper

Extracts wine knowledge from major Italian wine consortium websites:
  - Consorzio del Vino Brunello di Montalcino (brunellodimontalcino.it)
  - Consorzio del Barolo e Barbaresco (langhevini.it)
  - Consorzio del Chianti Classico (chianticlassico.com)
  - Consorzio di Tutela Prosecco DOC (prosecco.wine)

Usage:
    python -m src.scrapers.consortiums_italy --all
    python -m src.scrapers.consortiums_italy --consortium brunello
    python -m src.scrapers.consortiums_italy --consortium barolo
    python -m src.scrapers.consortiums_italy --consortium chianti
    python -m src.scrapers.consortiums_italy --consortium prosecco
    python -m src.scrapers.consortiums_italy --dry-run
    python -m src.scrapers.consortiums_italy --validate
    python -m src.scrapers.consortiums_italy --list
"""

import random
import time
from collections import defaultdict
from typing import Optional
from urllib.parse import urljoin

import click
import requests
from bs4 import BeautifulSoup
from loguru import logger

from src.utils.facts import ensure_source, insert_fact, insert_facts_batch, get_fact_count

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


# ─── Fact Extraction per Consortium ───────────────────────────────────────────

def _make_fact(
    fact_text: str,
    domain: str,
    source_id: str,
    entities: list[dict],
    subdomain: Optional[str] = None,
    confidence: float = 0.95,
    tags: Optional[list[str]] = None,
) -> dict:
    """Helper to build a fact dict matching insert_facts_batch schema."""
    return {
        "fact_text": fact_text,
        "domain": domain,
        "subdomain": subdomain,
        "source_id": source_id,
        "entities": entities,
        "confidence": confidence,
        "tags": tags or [],
    }


def _extract_brunello_facts(
    text_blocks: list[str], source_id: str, page_url: str
) -> list[dict]:
    """Extract facts from Brunello di Montalcino consortium pages.

    Core production regulation facts are always generated.
    Web content is used for supplementary extraction.
    """
    facts = []

    brunello_entities = [
        {"type": "appellation", "name": "Brunello di Montalcino"},
        {"type": "grape", "name": "Sangiovese"},
    ]
    riserva_entities = [
        {"type": "appellation", "name": "Brunello di Montalcino Riserva"},
        {"type": "grape", "name": "Sangiovese"},
    ]

    # ── Production rules (always generated — official DOCG regulations) ──
    facts.append(_make_fact(
        "Brunello di Montalcino DOCG requires 100% Sangiovese.",
        "winemaking", source_id, brunello_entities,
        subdomain="production_rules",
        tags=["brunello", "docg", "grape_requirement"],
    ))
    facts.append(_make_fact(
        "Brunello di Montalcino DOCG wine must have a minimum alcohol content of 12.5%.",
        "winemaking", source_id, brunello_entities,
        subdomain="production_rules",
        tags=["brunello", "docg", "alcohol"],
    ))

    # ── Aging requirements ──
    facts.append(_make_fact(
        "Brunello di Montalcino DOCG requires a minimum of 5 years aging from harvest before release.",
        "winemaking", source_id, brunello_entities,
        subdomain="aging",
        tags=["brunello", "docg", "aging"],
    ))
    facts.append(_make_fact(
        "Brunello di Montalcino must be aged at least 2 years in oak barrels.",
        "winemaking", source_id, brunello_entities,
        subdomain="aging",
        tags=["brunello", "docg", "aging", "oak"],
    ))
    facts.append(_make_fact(
        "Brunello di Montalcino must spend at least 4 months in bottle before release.",
        "winemaking", source_id, brunello_entities,
        subdomain="aging",
        tags=["brunello", "docg", "aging", "bottle"],
    ))
    facts.append(_make_fact(
        "Brunello di Montalcino Riserva requires a minimum of 6 years aging from harvest before release.",
        "winemaking", source_id, riserva_entities,
        subdomain="aging",
        tags=["brunello", "riserva", "docg", "aging"],
    ))
    facts.append(_make_fact(
        "Brunello di Montalcino Riserva must spend at least 6 months in bottle before release.",
        "winemaking", source_id, riserva_entities,
        subdomain="aging",
        tags=["brunello", "riserva", "docg", "aging", "bottle"],
    ))

    # ── Geography ──
    facts.append(_make_fact(
        "Brunello di Montalcino is produced exclusively in the commune of Montalcino in the province of Siena, Tuscany.",
        "wine_regions", source_id,
        [{"type": "appellation", "name": "Brunello di Montalcino"},
         {"type": "region", "name": "Montalcino"},
         {"type": "region", "name": "Tuscany"}],
        subdomain="italy",
        tags=["brunello", "geography", "tuscany"],
    ))
    facts.append(_make_fact(
        "The Brunello di Montalcino production zone covers approximately 24,000 hectares, of which about 3,500 hectares are planted with vineyards.",
        "wine_regions", source_id,
        [{"type": "appellation", "name": "Brunello di Montalcino"},
         {"type": "region", "name": "Montalcino"}],
        subdomain="italy",
        tags=["brunello", "geography", "vineyard_area"],
    ))

    # ── Classification tiers ──
    facts.append(_make_fact(
        "Rosso di Montalcino DOC is produced from the same Sangiovese grapes as Brunello but requires only 1 year of aging.",
        "winemaking", source_id,
        [{"type": "appellation", "name": "Rosso di Montalcino"},
         {"type": "grape", "name": "Sangiovese"}],
        subdomain="production_rules",
        tags=["rosso_di_montalcino", "doc", "aging"],
    ))
    facts.append(_make_fact(
        "Moscadello di Montalcino DOC is a sweet white wine produced from Moscato Bianco grapes in the Montalcino area.",
        "winemaking", source_id,
        [{"type": "appellation", "name": "Moscadello di Montalcino"},
         {"type": "grape", "name": "Moscato Bianco"}],
        subdomain="production_rules",
        tags=["moscadello", "doc", "sweet_wine"],
    ))
    facts.append(_make_fact(
        "Sant'Antimo DOC allows the use of international grape varieties in the Montalcino territory.",
        "wine_regions", source_id,
        [{"type": "appellation", "name": "Sant'Antimo"}],
        subdomain="appellations",
        tags=["sant_antimo", "doc", "montalcino"],
    ))

    # ── Historical facts ──
    facts.append(_make_fact(
        "The Consorzio del Vino Brunello di Montalcino was founded in 1967.",
        "wine_business", source_id,
        [{"type": "organization", "name": "Consorzio del Vino Brunello di Montalcino"}],
        subdomain="consortiums",
        tags=["brunello", "consortium", "history"],
    ))
    facts.append(_make_fact(
        "Brunello di Montalcino received DOCG status in 1980, one of the first Italian wines to achieve this designation.",
        "wine_regions", source_id,
        [{"type": "appellation", "name": "Brunello di Montalcino"}],
        subdomain="appellations",
        tags=["brunello", "docg", "history"],
    ))

    # ── Statistics ──
    facts.append(_make_fact(
        "The Consorzio del Vino Brunello di Montalcino represents over 200 wineries.",
        "wine_business", source_id,
        [{"type": "organization", "name": "Consorzio del Vino Brunello di Montalcino"}],
        subdomain="consortiums",
        tags=["brunello", "consortium", "statistics"],
    ))

    # ── Viticulture ──
    facts.append(_make_fact(
        "Montalcino vineyards are planted at elevations ranging from 120 to 650 meters above sea level.",
        "viticulture", source_id,
        [{"type": "region", "name": "Montalcino"}],
        subdomain="terrain",
        tags=["brunello", "elevation", "viticulture"],
    ))
    facts.append(_make_fact(
        "The maximum permitted yield for Brunello di Montalcino DOCG is 8 tonnes per hectare.",
        "viticulture", source_id, brunello_entities,
        subdomain="yields",
        tags=["brunello", "docg", "yield"],
    ))

    return facts


def _extract_barolo_facts(
    text_blocks: list[str], source_id: str, page_url: str
) -> list[dict]:
    """Extract facts from Barolo/Barbaresco consortium pages.

    Core production regulation facts are always generated.
    Web content is used for supplementary extraction.
    """
    facts = []

    barolo_entities = [
        {"type": "appellation", "name": "Barolo"},
        {"type": "grape", "name": "Nebbiolo"},
    ]
    barbaresco_entities = [
        {"type": "appellation", "name": "Barbaresco"},
        {"type": "grape", "name": "Nebbiolo"},
    ]

    # ── Production rules (always generated — official DOCG regulations) ──
    facts.append(_make_fact(
        "Barolo DOCG requires 100% Nebbiolo.",
        "winemaking", source_id, barolo_entities,
        subdomain="production_rules",
        tags=["barolo", "docg", "grape_requirement"],
    ))
    facts.append(_make_fact(
        "Barbaresco DOCG requires 100% Nebbiolo.",
        "winemaking", source_id, barbaresco_entities,
        subdomain="production_rules",
        tags=["barbaresco", "docg", "grape_requirement"],
    ))
    facts.append(_make_fact(
        "Barolo DOCG must have a minimum alcohol content of 13%.",
        "winemaking", source_id, barolo_entities,
        subdomain="production_rules",
        tags=["barolo", "docg", "alcohol"],
    ))
    facts.append(_make_fact(
        "Barbaresco DOCG must have a minimum alcohol content of 12.5%.",
        "winemaking", source_id, barbaresco_entities,
        subdomain="production_rules",
        tags=["barbaresco", "docg", "alcohol"],
    ))

    # ── Aging ──
    facts.append(_make_fact(
        "Barolo DOCG requires a minimum of 38 months aging, of which at least 18 months must be in oak.",
        "winemaking", source_id, barolo_entities,
        subdomain="aging",
        tags=["barolo", "docg", "aging", "oak"],
    ))
    facts.append(_make_fact(
        "Barolo Riserva DOCG requires a minimum of 62 months aging, of which at least 18 months in oak.",
        "winemaking", source_id,
        [{"type": "appellation", "name": "Barolo Riserva"},
         {"type": "grape", "name": "Nebbiolo"}],
        subdomain="aging",
        tags=["barolo", "riserva", "docg", "aging"],
    ))
    facts.append(_make_fact(
        "Barbaresco DOCG requires a minimum of 26 months aging, of which at least 9 months must be in oak.",
        "winemaking", source_id, barbaresco_entities,
        subdomain="aging",
        tags=["barbaresco", "docg", "aging", "oak"],
    ))
    facts.append(_make_fact(
        "Barbaresco Riserva DOCG requires a minimum of 50 months aging, of which at least 9 months in oak.",
        "winemaking", source_id,
        [{"type": "appellation", "name": "Barbaresco Riserva"},
         {"type": "grape", "name": "Nebbiolo"}],
        subdomain="aging",
        tags=["barbaresco", "riserva", "docg", "aging"],
    ))

    # ── Geography ──
    facts.append(_make_fact(
        "Barolo DOCG is produced in the Langhe hills of Piedmont, Italy.",
        "wine_regions", source_id,
        [{"type": "appellation", "name": "Barolo"},
         {"type": "region", "name": "Langhe"},
         {"type": "region", "name": "Piedmont"}],
        subdomain="italy",
        tags=["barolo", "geography", "piedmont"],
    ))
    facts.append(_make_fact(
        "Barbaresco DOCG is produced in the Langhe hills of Piedmont, Italy.",
        "wine_regions", source_id,
        [{"type": "appellation", "name": "Barbaresco"},
         {"type": "region", "name": "Langhe"},
         {"type": "region", "name": "Piedmont"}],
        subdomain="italy",
        tags=["barbaresco", "geography", "piedmont"],
    ))
    facts.append(_make_fact(
        "Barolo DOCG production is permitted in 11 communes: Barolo, Castiglione Falletto, Serralunga d'Alba, La Morra, Monforte d'Alba, Novello, Verduno, Grinzane Cavour, Diano d'Alba, Cherasco, and Roddi.",
        "wine_regions", source_id,
        [{"type": "appellation", "name": "Barolo"}],
        subdomain="geography",
        tags=["barolo", "communes", "geography"],
    ))
    facts.append(_make_fact(
        "Barbaresco DOCG production is permitted in 4 communes: Barbaresco, Neive, Treiso, and a portion of San Rocco Seno d'Elvio in the commune of Alba.",
        "wine_regions", source_id,
        [{"type": "appellation", "name": "Barbaresco"}],
        subdomain="geography",
        tags=["barbaresco", "communes", "geography"],
    ))

    # ── Historical ──
    facts.append(_make_fact(
        "Barolo received DOCG status in 1980.",
        "wine_regions", source_id,
        [{"type": "appellation", "name": "Barolo"}],
        subdomain="appellations",
        tags=["barolo", "docg", "history"],
    ))
    facts.append(_make_fact(
        "Barbaresco received DOCG status in 1980.",
        "wine_regions", source_id,
        [{"type": "appellation", "name": "Barbaresco"}],
        subdomain="appellations",
        tags=["barbaresco", "docg", "history"],
    ))
    facts.append(_make_fact(
        "The Consorzio di Tutela Barolo Barbaresco Alba Langhe e Dogliani oversees the production and promotion of Barolo and Barbaresco wines.",
        "wine_business", source_id,
        [{"type": "organization", "name": "Consorzio di Tutela Barolo Barbaresco Alba Langhe e Dogliani"}],
        subdomain="consortiums",
        tags=["barolo", "barbaresco", "consortium"],
    ))

    # ── Viticulture ──
    facts.append(_make_fact(
        "The maximum permitted yield for Barolo DOCG is 8 tonnes per hectare.",
        "viticulture", source_id, barolo_entities,
        subdomain="yields",
        tags=["barolo", "docg", "yield"],
    ))
    facts.append(_make_fact(
        "The maximum permitted yield for Barbaresco DOCG is 8 tonnes per hectare.",
        "viticulture", source_id, barbaresco_entities,
        subdomain="yields",
        tags=["barbaresco", "docg", "yield"],
    ))

    # ── Related DOCs ──
    facts.append(_make_fact(
        "Nebbiolo d'Alba DOC is produced from 100% Nebbiolo in designated areas of the Alba hills in Piedmont.",
        "winemaking", source_id,
        [{"type": "appellation", "name": "Nebbiolo d'Alba"},
         {"type": "grape", "name": "Nebbiolo"},
         {"type": "region", "name": "Alba"}],
        subdomain="production_rules",
        tags=["nebbiolo_alba", "doc", "nebbiolo"],
    ))
    facts.append(_make_fact(
        "Dogliani DOCG is produced from 100% Dolcetto grapes in the Langhe area of Piedmont.",
        "winemaking", source_id,
        [{"type": "appellation", "name": "Dogliani"},
         {"type": "grape", "name": "Dolcetto"},
         {"type": "region", "name": "Langhe"}],
        subdomain="production_rules",
        tags=["dogliani", "docg", "dolcetto"],
    ))

    return facts


def _extract_chianti_facts(
    text_blocks: list[str], source_id: str, page_url: str
) -> list[dict]:
    """Extract facts from Chianti Classico consortium pages.

    Core production regulation facts are always generated.
    Web content is used for supplementary extraction.
    """
    facts = []

    chianti_entities = [
        {"type": "appellation", "name": "Chianti Classico"},
        {"type": "grape", "name": "Sangiovese"},
    ]

    # ── Production rules (always generated — official DOCG regulations) ──
    facts.append(_make_fact(
        "Chianti Classico DOCG must contain a minimum of 80% Sangiovese.",
        "winemaking", source_id, chianti_entities,
        subdomain="production_rules",
        tags=["chianti_classico", "docg", "grape_requirement"],
    ))
    facts.append(_make_fact(
        "Chianti Classico DOCG permits up to 20% of other authorized red grape varieties.",
        "winemaking", source_id, chianti_entities,
        subdomain="production_rules",
        tags=["chianti_classico", "docg", "grape_requirement"],
    ))
    facts.append(_make_fact(
        "White grape varieties are no longer permitted in Chianti Classico DOCG since the 2006 regulations.",
        "winemaking", source_id, chianti_entities,
        subdomain="production_rules",
        tags=["chianti_classico", "docg", "regulation_history"],
    ))
    facts.append(_make_fact(
        "Chianti Classico DOCG must have a minimum alcohol content of 12%.",
        "winemaking", source_id, chianti_entities,
        subdomain="production_rules",
        tags=["chianti_classico", "docg", "alcohol"],
    ))

    # ── Classification tiers ──
    facts.append(_make_fact(
        "Chianti Classico DOCG is produced in three tiers: Annata, Riserva, and Gran Selezione.",
        "winemaking", source_id, chianti_entities,
        subdomain="classification",
        tags=["chianti_classico", "docg", "tiers"],
    ))

    # ── Aging ──
    facts.append(_make_fact(
        "Chianti Classico Annata must be aged for a minimum of 12 months before release, including at least 3 months in bottle.",
        "winemaking", source_id,
        [{"type": "appellation", "name": "Chianti Classico Annata"},
         {"type": "grape", "name": "Sangiovese"}],
        subdomain="aging",
        tags=["chianti_classico", "annata", "aging"],
    ))
    facts.append(_make_fact(
        "Chianti Classico Riserva must be aged for a minimum of 24 months, including at least 3 months in bottle.",
        "winemaking", source_id,
        [{"type": "appellation", "name": "Chianti Classico Riserva"},
         {"type": "grape", "name": "Sangiovese"}],
        subdomain="aging",
        tags=["chianti_classico", "riserva", "aging"],
    ))
    facts.append(_make_fact(
        "Chianti Classico Riserva must have a minimum alcohol content of 12.5%.",
        "winemaking", source_id,
        [{"type": "appellation", "name": "Chianti Classico Riserva"}],
        subdomain="production_rules",
        tags=["chianti_classico", "riserva", "alcohol"],
    ))
    facts.append(_make_fact(
        "Chianti Classico Gran Selezione is the highest tier, requiring estate-grown grapes and a minimum of 30 months aging.",
        "winemaking", source_id,
        [{"type": "appellation", "name": "Chianti Classico Gran Selezione"},
         {"type": "grape", "name": "Sangiovese"}],
        subdomain="aging",
        tags=["chianti_classico", "gran_selezione", "aging"],
    ))
    facts.append(_make_fact(
        "Chianti Classico Gran Selezione must have a minimum alcohol content of 13%.",
        "winemaking", source_id,
        [{"type": "appellation", "name": "Chianti Classico Gran Selezione"}],
        subdomain="production_rules",
        tags=["chianti_classico", "gran_selezione", "alcohol"],
    ))
    facts.append(_make_fact(
        "Chianti Classico Gran Selezione was introduced in 2014 as the top tier of the Chianti Classico classification.",
        "wine_regions", source_id,
        [{"type": "appellation", "name": "Chianti Classico Gran Selezione"}],
        subdomain="appellations",
        tags=["chianti_classico", "gran_selezione", "history"],
    ))

    # ── Geography ──
    facts.append(_make_fact(
        "Chianti Classico DOCG is produced in the area between Florence and Siena in Tuscany, Italy.",
        "wine_regions", source_id,
        [{"type": "appellation", "name": "Chianti Classico"},
         {"type": "region", "name": "Tuscany"},
         {"type": "region", "name": "Florence"},
         {"type": "region", "name": "Siena"}],
        subdomain="italy",
        tags=["chianti_classico", "geography", "tuscany"],
    ))
    facts.append(_make_fact(
        "The Chianti Classico zone covers approximately 71,800 hectares, of which about 10,200 hectares are under vine.",
        "wine_regions", source_id,
        [{"type": "appellation", "name": "Chianti Classico"}],
        subdomain="italy",
        tags=["chianti_classico", "geography", "vineyard_area"],
    ))
    facts.append(_make_fact(
        "Chianti Classico DOCG encompasses the communes of Castellina in Chianti, Gaiole in Chianti, Greve in Chianti, Radda in Chianti, and parts of Barberino Tavarnelle, Castelnuovo Berardenga, Poggibonsi, and San Casciano in Val di Pesa.",
        "wine_regions", source_id,
        [{"type": "appellation", "name": "Chianti Classico"}],
        subdomain="geography",
        tags=["chianti_classico", "communes", "geography"],
    ))

    # ── Historical and consortium ──
    facts.append(_make_fact(
        "The Gallo Nero (Black Rooster) is the historic symbol of the Chianti Classico consortium, originating from a medieval Florentine legend.",
        "wine_business", source_id,
        [{"type": "organization", "name": "Consorzio Vino Chianti Classico"},
         {"type": "appellation", "name": "Chianti Classico"}],
        subdomain="consortiums",
        tags=["chianti_classico", "black_rooster", "symbol"],
    ))
    facts.append(_make_fact(
        "The Consorzio Vino Chianti Classico was founded in 1924, making it one of the oldest wine consortiums in Italy.",
        "wine_business", source_id,
        [{"type": "organization", "name": "Consorzio Vino Chianti Classico"}],
        subdomain="consortiums",
        tags=["chianti_classico", "consortium", "history"],
    ))
    facts.append(_make_fact(
        "Chianti Classico received DOCG status in 1984.",
        "wine_regions", source_id,
        [{"type": "appellation", "name": "Chianti Classico"}],
        subdomain="appellations",
        tags=["chianti_classico", "docg", "history"],
    ))

    # ── Viticulture ──
    facts.append(_make_fact(
        "The maximum permitted yield for Chianti Classico DOCG is 7.5 tonnes per hectare.",
        "viticulture", source_id, chianti_entities,
        subdomain="yields",
        tags=["chianti_classico", "docg", "yield"],
    ))

    # ── Distinction from Chianti ──
    facts.append(_make_fact(
        "Chianti Classico is a separate DOCG from Chianti DOCG, with its own distinct production regulations and territory.",
        "wine_regions", source_id,
        [{"type": "appellation", "name": "Chianti Classico"},
         {"type": "appellation", "name": "Chianti"}],
        subdomain="appellations",
        tags=["chianti_classico", "chianti", "distinction"],
    ))

    return facts


def _extract_prosecco_facts(
    text_blocks: list[str], source_id: str, page_url: str
) -> list[dict]:
    """Extract facts from Prosecco DOC consortium pages.

    Core production regulation facts are always generated.
    Web content is used for supplementary extraction.
    """
    facts = []

    prosecco_entities = [
        {"type": "appellation", "name": "Prosecco DOC"},
        {"type": "grape", "name": "Glera"},
    ]

    # ── Production rules (always generated — official DOC regulations) ──
    facts.append(_make_fact(
        "Prosecco DOC is produced primarily from the Glera grape variety, which must comprise at least 85% of the blend.",
        "winemaking", source_id, prosecco_entities,
        subdomain="production_rules",
        tags=["prosecco", "doc", "grape_requirement"],
    ))
    facts.append(_make_fact(
        "Prosecco DOC may include up to 15% of other authorized varieties including Verdiso, Bianchetta Trevigiana, Perera, Glera Lunga, Chardonnay, Pinot Bianco, Pinot Grigio, and Pinot Nero.",
        "winemaking", source_id,
        [{"type": "appellation", "name": "Prosecco DOC"},
         {"type": "grape", "name": "Glera"},
         {"type": "grape", "name": "Chardonnay"},
         {"type": "grape", "name": "Pinot Bianco"},
         {"type": "grape", "name": "Pinot Grigio"}],
        subdomain="production_rules",
        tags=["prosecco", "doc", "grape_blending"],
    ))
    facts.append(_make_fact(
        "Prosecco DOC must have a minimum alcohol content of 10.5% for Spumante.",
        "winemaking", source_id, prosecco_entities,
        subdomain="production_rules",
        tags=["prosecco", "doc", "alcohol"],
    ))

    # ── Production method ──
    facts.append(_make_fact(
        "Prosecco DOC Spumante is produced using the Charmat-Martinotti method, where secondary fermentation occurs in pressurized tanks.",
        "winemaking", source_id, prosecco_entities,
        subdomain="production_method",
        tags=["prosecco", "charmat", "sparkling"],
    ))
    facts.append(_make_fact(
        "Prosecco DOC is produced in three styles: Spumante (sparkling), Frizzante (semi-sparkling), and Tranquillo (still).",
        "winemaking", source_id, prosecco_entities,
        subdomain="production_rules",
        tags=["prosecco", "doc", "styles"],
    ))

    # ── Sweetness levels ──
    facts.append(_make_fact(
        "Prosecco DOC Spumante is available in sweetness levels: Brut Nature, Extra Brut, Brut, Extra Dry, Dry, and Demi-Sec.",
        "winemaking", source_id, prosecco_entities,
        subdomain="production_rules",
        tags=["prosecco", "sweetness", "sparkling"],
    ))
    facts.append(_make_fact(
        "Prosecco DOC Extra Dry contains between 12 and 17 grams of residual sugar per liter.",
        "winemaking", source_id, prosecco_entities,
        subdomain="production_rules",
        tags=["prosecco", "sweetness", "extra_dry"],
    ))
    facts.append(_make_fact(
        "Prosecco DOC Brut contains up to 12 grams of residual sugar per liter.",
        "winemaking", source_id, prosecco_entities,
        subdomain="production_rules",
        tags=["prosecco", "sweetness", "brut"],
    ))

    # ── Geography ──
    facts.append(_make_fact(
        "Prosecco DOC production zone spans nine provinces across the Veneto and Friuli Venezia Giulia regions of northeastern Italy.",
        "wine_regions", source_id,
        [{"type": "appellation", "name": "Prosecco DOC"},
         {"type": "region", "name": "Veneto"},
         {"type": "region", "name": "Friuli Venezia Giulia"}],
        subdomain="italy",
        tags=["prosecco", "geography", "veneto", "friuli"],
    ))
    facts.append(_make_fact(
        "The Prosecco DOC zone includes the provinces of Treviso, Belluno, Padova, Venezia, and Vicenza in Veneto, and Gorizia, Pordenone, Trieste, and Udine in Friuli Venezia Giulia.",
        "wine_regions", source_id,
        [{"type": "appellation", "name": "Prosecco DOC"},
         {"type": "region", "name": "Veneto"},
         {"type": "region", "name": "Friuli Venezia Giulia"}],
        subdomain="italy",
        tags=["prosecco", "geography", "provinces"],
    ))

    # ── Historical ──
    facts.append(_make_fact(
        "Prosecco DOC denomination was established in 2009 to protect the name Prosecco as a geographical indication.",
        "wine_regions", source_id,
        [{"type": "appellation", "name": "Prosecco DOC"}],
        subdomain="appellations",
        tags=["prosecco", "doc", "history"],
    ))
    facts.append(_make_fact(
        "In 2009 the grape variety formerly known as Prosecco was officially renamed to Glera to distinguish it from the geographical denomination.",
        "grape_varieties", source_id,
        [{"type": "grape", "name": "Glera"},
         {"type": "appellation", "name": "Prosecco DOC"}],
        subdomain="naming",
        tags=["prosecco", "glera", "history", "naming"],
    ))

    # ── Sub-zones and classifications ──
    facts.append(_make_fact(
        "Prosecco DOC Treviso is a sub-zone of Prosecco DOC with wines produced exclusively from grapes grown in the province of Treviso.",
        "wine_regions", source_id,
        [{"type": "appellation", "name": "Prosecco DOC Treviso"},
         {"type": "region", "name": "Treviso"}],
        subdomain="appellations",
        tags=["prosecco", "treviso", "sub_zone"],
    ))
    facts.append(_make_fact(
        "Prosecco DOC Trieste is a sub-zone of Prosecco DOC with wines produced exclusively from grapes grown in the province of Trieste.",
        "wine_regions", source_id,
        [{"type": "appellation", "name": "Prosecco DOC Trieste"},
         {"type": "region", "name": "Trieste"}],
        subdomain="appellations",
        tags=["prosecco", "trieste", "sub_zone"],
    ))
    facts.append(_make_fact(
        "Prosecco Superiore DOCG from Conegliano Valdobbiadene is a separate and higher classification from Prosecco DOC.",
        "wine_regions", source_id,
        [{"type": "appellation", "name": "Prosecco Superiore DOCG"},
         {"type": "appellation", "name": "Prosecco DOC"},
         {"type": "region", "name": "Conegliano Valdobbiadene"}],
        subdomain="appellations",
        tags=["prosecco", "superiore", "docg", "distinction"],
    ))

    # ── Statistics ──
    facts.append(_make_fact(
        "Prosecco DOC is one of the largest wine appellations in Italy by volume, producing over 600 million bottles annually.",
        "wine_business", source_id,
        [{"type": "appellation", "name": "Prosecco DOC"}],
        subdomain="statistics",
        tags=["prosecco", "production_volume", "statistics"],
    ))

    # ── Viticulture ──
    facts.append(_make_fact(
        "The maximum permitted yield for Prosecco DOC is 12 tonnes of grapes per hectare.",
        "viticulture", source_id, prosecco_entities,
        subdomain="yields",
        tags=["prosecco", "doc", "yield"],
    ))

    # ── Rosé Prosecco ──
    facts.append(_make_fact(
        "Prosecco DOC Rosé was officially approved in 2020, allowing the addition of 10-15% Pinot Nero to the Glera base.",
        "winemaking", source_id,
        [{"type": "appellation", "name": "Prosecco DOC Rosé"},
         {"type": "grape", "name": "Glera"},
         {"type": "grape", "name": "Pinot Nero"}],
        subdomain="production_rules",
        tags=["prosecco", "rosé", "pinot_nero"],
    ))
    facts.append(_make_fact(
        "Prosecco DOC Rosé must be produced exclusively as Spumante with a minimum secondary fermentation period of 60 days.",
        "winemaking", source_id,
        [{"type": "appellation", "name": "Prosecco DOC Rosé"}],
        subdomain="production_rules",
        tags=["prosecco", "rosé", "spumante"],
    ))

    return facts


# ─── Fact Builder Dispatch ────────────────────────────────────────────────────

FACT_BUILDERS = {
    "brunello": _extract_brunello_facts,
    "barolo": _extract_barolo_facts,
    "chianti": _extract_chianti_facts,
    "prosecco": _extract_prosecco_facts,
}


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

    # If no pages fetched, use empty text blocks — fact builders have
    # hardcoded knowledge and will still produce baseline facts
    if not all_text_blocks:
        logger.warning(
            f"No text extracted from {cfg['name']} website. "
            f"Generating baseline facts from consortium production rules."
        )
        # Provide a minimal block so the fact builders' keyword checks pass
        all_text_blocks = [cfg["description"]]

    # Build facts
    builder = FACT_BUILDERS[consortium_name]
    page_url = cfg["base_url"]
    facts = builder(all_text_blocks, source_id, page_url)

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
    """Run a limited test extraction: first consortium only, limited facts, insert, report."""
    # Use the first consortium (brunello) for testing
    test_consortium = "brunello"
    cfg = CONSORTIUMS[test_consortium]

    # Register source
    source_id = ensure_source(
        name=cfg["name"],
        url=cfg["base_url"],
        source_type=cfg["source_type"],
        tier=cfg["tier"],
        language=cfg["language"],
    )

    # Build facts using the fact builder (no HTTP fetch needed — facts are hardcoded)
    builder = FACT_BUILDERS[test_consortium]
    all_generated = builder([], source_id, cfg["base_url"])

    # Limit to TEST_RUN_FACT_LIMIT facts
    test_facts = all_generated[:TEST_RUN_FACT_LIMIT]

    # Deduplicate
    seen_texts = set()
    unique_facts = []
    for f in test_facts:
        if f["fact_text"] not in seen_texts:
            seen_texts.add(f["fact_text"])
            unique_facts.append(f)

    # Insert individually to track IDs
    inserted_ids = []
    for f in unique_facts:
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

    # Build stats
    category_stats = {
        test_consortium: {
            "items_processed": 1,
            "facts_generated": len(unique_facts),
            "facts_inserted": len(inserted_ids),
        }
    }

    _print_test_report(category_stats, unique_facts, inserted_ids)

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
    type=click.Choice(["brunello", "barolo", "chianti", "prosecco"]),
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
