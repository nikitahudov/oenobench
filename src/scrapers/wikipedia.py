"""
OenoBench — Wikipedia Scraper (v2 — complete rewrite)

Extracts wine facts from English Wikipedia via the MediaWiki API.
Crawls wine-related category trees and extracts atomic, rephrased facts
from infoboxes and lead paragraphs.

Critical design goals:
  - NEVER store Wikipedia text verbatim — always rephrase into atomic facts
  - ONLY extract wine-relevant information (strict keyword filter)
  - Each fact is a single claim, ideally 8-25 words

License: CC BY-SA 3.0

Usage:
    python -m src.scrapers.wikipedia --all
    python -m src.scrapers.wikipedia --category regions
    python -m src.scrapers.wikipedia --category grapes
    python -m src.scrapers.wikipedia --category wineries
    python -m src.scrapers.wikipedia --category appellations
    python -m src.scrapers.wikipedia --category viticulture
    python -m src.scrapers.wikipedia --category oenology
    python -m src.scrapers.wikipedia --list
    python -m src.scrapers.wikipedia --dry-run
    python -m src.scrapers.wikipedia --validate
    python -m src.scrapers.wikipedia --test-run
    python -m src.scrapers.wikipedia --test-run --cleanup
    python -m src.scrapers.wikipedia --test-run --category regions
"""

import json
import os
import random
import re
import time
from collections import defaultdict
from pathlib import Path
from typing import Optional
from urllib.parse import quote as url_quote

import click
import requests
from loguru import logger

from src.utils.facts import ensure_source, insert_facts_batch, get_fact_count

# ─── Configuration ────────────────────────────────────────────────────────────

API_ENDPOINT = "https://en.wikipedia.org/w/api.php"
USER_AGENT = "OenoBench-Research/1.0 (academic wine benchmark)"
REQUEST_DELAY = 2.0  # seconds between requests (Wikipedia API etiquette)
MAX_CATEGORY_DEPTH = 3
MAX_ARTICLES_PER_ROOT = 2000
SOURCE_TIER = "tier_2_authoritative"
PROGRESS_FILE = "data/logs/wikipedia_progress.json"
MAX_LEAD_FACTS_PER_ARTICLE = 8
MIN_ARTICLE_LENGTH = 100  # characters — skip true stubs only
TEST_RUN_ITEMS_PER_CATEGORY = 5

# ─── Category Configuration ───────────────────────────────────────────────────

CATEGORIES = {
    "regions": {
        "root": "Category:Wine regions",
        "domain": "wine_regions",
        "subdomain": None,
        "description": "Wine regions worldwide",
    },
    "grapes": {
        "root": "Category:Grape varieties",
        "domain": "grape_varieties",
        "subdomain": None,
        "description": "Grape varieties used in winemaking",
    },
    "wineries": {
        "root": "Category:Wineries",
        "domain": "producers",
        "subdomain": None,
        "description": "Wine producers and wineries",
    },
    "appellations": {
        "roots": [
            "Category:Appellations",
            "Category:American Viticultural Areas",
            "Category:French wine AOCs",
            "Category:Denominazioni di Origine Controllata",
            "Category:Wine classification systems",
        ],
        "domain": "wine_regions",
        "subdomain": "appellations",
        "description": "Wine appellations and designations of origin",
    },
    "classifications": {
        "root": "Category:Wine classification",
        "domain": "wine_regions",
        "subdomain": "classifications",
        "description": "Wine classification systems",
    },
    "viticulture": {
        "root": "Category:Viticulture",
        "domain": "viticulture",
        "subdomain": None,
        "description": "Grape growing and vineyard management",
    },
    "oenology": {
        "root": "Category:Oenology",
        "domain": "winemaking",
        "subdomain": None,
        "description": "Winemaking science and techniques",
    },
}

# ─── Title Filters ────────────────────────────────────────────────────────────

NON_ARTICLE_TITLE_PATTERNS = [
    r"^List of ",
    r"^Lists of ",
    r"^Template:",
    r"^Wikipedia:",
    r"^Portal:",
    r"^Category:",
    r"^File:",
    r"^Draft:",
]
NON_ARTICLE_TITLE_RE = re.compile(
    "|".join(NON_ARTICLE_TITLE_PATTERNS), re.IGNORECASE
)

# ─── Wine Relevance Keywords ─────────────────────────────────────────────────
# A sentence must contain at least one of these to pass the wine filter.

WINE_KEYWORDS = {
    # Core wine terms
    "wine", "winery", "wineries", "vineyard", "vineyards", "grape", "grapes",
    "viticulture", "viticultural", "viniculture", "vinification", "oenology",
    "enology", "winemaker", "winemaking", "vintner", "sommelier",
    # Appellations and classifications
    "appellation", "aoc", "aop", "doc", "docg", "dop", "ava", "vqa",
    "denomination", "cru", "grand cru", "premier cru", "classico",
    "riserva", "reserva", "crianza", "gran reserva",
    # Grape varieties (most common)
    "pinot", "cabernet", "merlot", "chardonnay", "riesling", "syrah",
    "shiraz", "sauvignon", "sangiovese", "nebbiolo", "tempranillo",
    "malbec", "grenache", "mourvèdre", "mourvedre", "zinfandel",
    "gamay", "gewürztraminer", "gewurztraminer", "muscat", "moscato",
    "trebbiano", "barbera", "garnacha", "monastrell", "carignan",
    "sémillon", "semillon", "viognier", "chenin", "verdejo", "albariño",
    "albarino", "grüner veltliner", "gruner veltliner", "glera",
    # Winemaking terms
    "fermentation", "barrel", "oak", "tannin", "tannins", "acidity",
    "vintage", "varietal", "terroir", "blend", "cuvée", "cuvee",
    "sparkling", "fortified", "dessert wine", "rosé", "rose wine",
    "red wine", "white wine", "crush", "harvest", "bottling", "cellar",
    "maceration", "malolactic", "lees", "sur lie", "chaptalisation",
    "must", "pomace", "press wine",
    # Wine regions and geography
    "côte", "cote", "château", "chateau", "domaine", "estate",
    "hectare", "hectares", "hl/ha",
    # Viticulture terms
    "rootstock", "phylloxera", "canopy", "pruning", "trellising",
    "terroir", "clone", "grafting", "yield", "véraison", "veraison",
    "brix", "bud break",
    # Alcohol / production
    "alcohol", "abv",
}

# Compiled pattern: match any wine keyword as a whole word (case-insensitive)
_WINE_KW_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(kw) for kw in sorted(WINE_KEYWORDS, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)

# ─── Rejection Patterns ──────────────────────────────────────────────────────
# Sentences matching these are NOT wine-relevant even if they contain a keyword.

REJECT_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"\bpopulation\b.*\b\d{3,}",           # population stats
        r"\bcensus\b",                           # census data
        r"\bdemograph",                          # demographics
        r"\brailway\b",                          # transport
        r"\brailroad\b",
        r"\btrain station\b",
        r"\bairport\b",
        r"\bhighway\b",
        r"\bmotorway\b",
        r"\belection\b",                         # politics
        r"\bparliament\b",
        r"\bmayor\b",
        r"\bgovernment\b",
        r"\bfootball\b",                         # sports
        r"\bsoccer\b",
        r"\bcricket\b",
        r"\bolympic\b",
        r"\bhotel\b",                            # tourism (non-wine)
        r"\btourist\b(?!.*wine)",
        r"\brestaurant\b(?!.*wine)",
        r"\bschool\b",                           # education
        r"\buniversity\b(?!.*wine|.*viticult)",
        r"\bhospital\b",                         # healthcare
        r"\bchurch\b",                           # religion
        r"\bcathedral\b",
        r"\bmonastery\b(?!.*wine|.*vineyard)",
        r"\bchristian\w*\b",                       # religious context
        r"\brabb\w+\b",                             # rabbinic
        r"\bbibl\w+\b",                             # biblical
        r"\beucharist\b",
        r"\bsacrament\b",
        r"\bliturg\w*\b",
        r"\btheolog\w*\b",
        r"\bsynagogue\b",
        r"\bmosque\b",
        r"\bevangeli\w+\b",
        r"\babstain\b(?!.*wine)",                   # abstinence (non-wine)
        r"\bancient world\b",                       # ancient history
        r"\bdistillation\b(?!.*wine|.*grape|.*brandy)",  # distilling (non-wine)
        r"\btemperature\b(?!.*vine|.*grape|.*harvest|.*ripen)",  # general climate
        r"\brainfall\b(?!.*vine|.*grape|.*viticult)",
    ]
]

# Taste/opinion patterns — skip subjective descriptions
OPINION_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"\bdelicious\b",
        r"\bexcellent\b",
        r"\bsuperb\b",
        r"\bone of (?:the |[\w]+'s )(?:best|finest|greatest|most famous|most renowned)",
        r"\bmost (?:famous|renowned|prestigious|celebrated)\b",
    ]
]


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _get_roots(config: dict) -> list[str]:
    """Get root category list from config (supports 'root' or 'roots')."""
    if "roots" in config:
        return config["roots"]
    return [config["root"]]


def _entity_type_for_domain(domain: str) -> str:
    """Map domain to entity type."""
    return {
        "wine_regions": "region",
        "grape_varieties": "grape",
        "producers": "producer",
        "viticulture": "concept",
        "winemaking": "concept",
    }.get(domain, "concept")


def _make_fact(
    fact_text: str,
    domain: str,
    subdomain: Optional[str],
    source_id: str,
    title: str,
    extra_entity_names: Optional[list[str]] = None,
) -> dict:
    """Create a fact dict matching the insert_facts_batch schema."""
    entities = [{"type": _entity_type_for_domain(domain), "name": title}]
    if extra_entity_names:
        for name in extra_entity_names:
            entities.append({"type": "related", "name": name})
    return {
        "fact_text": fact_text,
        "domain": domain,
        "subdomain": subdomain,
        "source_id": source_id,
        "entities": entities,
        "confidence": 0.9,
        "tags": ["wikipedia", domain],
    }


def _extract_year(text: str) -> Optional[str]:
    """Extract a 4-digit year from text."""
    m = re.search(r"\b(1[0-9]{3}|20[0-2][0-9])\b", text)
    return m.group(1) if m else None


# ─── Session & API ────────────────────────────────────────────────────────────


def _make_session() -> requests.Session:
    """Create a requests session with proper headers and connection pooling."""
    session = requests.Session()
    session.headers.update({
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    })
    return session


def _api_request(
    session: requests.Session, params: dict, max_retries: int = 4
) -> dict:
    """MediaWiki API request with rate limiting and exponential backoff."""
    params["format"] = "json"
    params["formatversion"] = "2"

    for attempt in range(max_retries + 1):
        try:
            time.sleep(REQUEST_DELAY)
            resp = session.get(API_ENDPOINT, params=params, timeout=30)

            if resp.status_code == 429:
                wait = 2 ** (attempt + 1)
                logger.warning(f"Rate limited (429). Waiting {wait}s...")
                time.sleep(wait)
                continue

            resp.raise_for_status()
            return resp.json()

        except requests.exceptions.RequestException as e:
            if attempt < max_retries:
                wait = 2 ** (attempt + 1)
                logger.warning(f"Request failed: {e}. Retrying in {wait}s...")
                time.sleep(wait)
            else:
                logger.error(
                    f"Request failed after {max_retries + 1} attempts: {e}"
                )
                raise

    return {}


# ─── Category Crawling ────────────────────────────────────────────────────────


def get_category_members(
    session: requests.Session,
    category: str,
    depth: int = 0,
    seen_categories: Optional[set] = None,
    article_count: Optional[list] = None,
    max_articles: int = MAX_ARTICLES_PER_ROOT,
) -> list[str]:
    """Recursively crawl a category tree and return article titles.

    Returns article titles (namespace 0 only).
    Recurses into subcategories up to MAX_CATEGORY_DEPTH.
    """
    if seen_categories is None:
        seen_categories = set()
    if article_count is None:
        article_count = [0]

    if depth > MAX_CATEGORY_DEPTH:
        return []
    if category in seen_categories:
        return []
    seen_categories.add(category)

    articles = []
    cmcontinue = None

    while True:
        if article_count[0] >= max_articles:
            logger.info(
                f"Reached max articles ({max_articles}) for root category"
            )
            break

        params = {
            "action": "query",
            "list": "categorymembers",
            "cmtitle": category,
            "cmlimit": "500",
        }
        if cmcontinue:
            params["cmcontinue"] = cmcontinue

        data = _api_request(session, params)
        if not data or "query" not in data:
            break

        for member in data["query"].get("categorymembers", []):
            if article_count[0] >= max_articles:
                break

            ns = member.get("ns", 0)
            title = member.get("title", "")

            if ns == 0 and not NON_ARTICLE_TITLE_RE.match(title):
                articles.append(title)
                article_count[0] += 1
            elif ns == 14:
                sub = get_category_members(
                    session, title, depth + 1, seen_categories,
                    article_count, max_articles,
                )
                articles.extend(sub)

        # Handle API continuation
        cont = data.get("continue", {})
        cmcontinue = cont.get("cmcontinue")
        if not cmcontinue or article_count[0] >= max_articles:
            break

    return articles


# ─── Article Fetching ─────────────────────────────────────────────────────────


def get_article_extract(session: requests.Session, title: str) -> Optional[str]:
    """Get plain-text intro via prop=extracts&exintro=1&explaintext=1."""
    params = {
        "action": "query",
        "titles": title,
        "prop": "extracts",
        "exintro": "1",
        "explaintext": "1",
        "redirects": "1",
    }
    data = _api_request(session, params)
    if not data or "query" not in data:
        return None

    pages = data["query"].get("pages", [])
    if not pages:
        return None

    page = pages[0]
    if page.get("missing", False):
        return None

    return page.get("extract", "")


def get_article_wikitext(session: requests.Session, title: str) -> Optional[str]:
    """Get raw wikitext via action=parse for infobox extraction."""
    params = {
        "action": "parse",
        "page": title,
        "prop": "wikitext",
        "redirects": "1",
    }
    data = _api_request(session, params)
    if not data or "parse" not in data:
        return None

    wikitext = data["parse"].get("wikitext", "")
    # formatversion=2 returns wikitext as a string;
    # formatversion=1 returns {"*": "..."}
    if isinstance(wikitext, dict):
        return wikitext.get("*", "")
    return wikitext or ""


def is_disambiguation_page(session: requests.Session, title: str) -> bool:
    """Check if article is a disambiguation page via its categories."""
    params = {
        "action": "query",
        "titles": title,
        "prop": "categories",
        "cllimit": "50",
        "redirects": "1",
    }
    data = _api_request(session, params)
    if not data or "query" not in data:
        return False

    pages = data["query"].get("pages", [])
    if not pages:
        return False

    for cat in pages[0].get("categories", []):
        if "disambiguation" in cat.get("title", "").lower():
            return True
    return False


# ─── Wine Relevance Filter ───────────────────────────────────────────────────


def is_wine_relevant(text: str) -> bool:
    """Return True if the text contains at least one wine keyword
    and does not match any rejection pattern."""
    if not _WINE_KW_RE.search(text):
        return False
    for pat in REJECT_PATTERNS:
        if pat.search(text):
            return False
    return True


def passes_opinion_filter(text: str) -> bool:
    """Return True if the text is NOT a subjective opinion."""
    return not any(pat.search(text) for pat in OPINION_PATTERNS)


# ─── Infobox Parsing ─────────────────────────────────────────────────────────

INFOBOX_FIELD_RE = re.compile(
    r"^\s*\|\s*(\w[\w\s]*?)\s*=\s*(.+?)$", re.MULTILINE
)
WIKI_LINK_RE = re.compile(r"\[\[(?:[^|\]]*\|)?([^\]]+)\]\]")
WIKI_REF_RE = re.compile(r"<ref[^>]*>.*?</ref>|<ref[^>]*/>", re.DOTALL)
WIKI_TAG_RE = re.compile(r"<[^>]+>")
WIKI_TEMPLATE_SIMPLE_RE = re.compile(r"\{\{[^{}]*\}\}")


def _clean_wiki_value(value: str) -> str:
    """Strip wiki markup from a field value."""
    value = WIKI_REF_RE.sub("", value)
    value = WIKI_LINK_RE.sub(r"\1", value)
    value = WIKI_TAG_RE.sub("", value)
    value = WIKI_TEMPLATE_SIMPLE_RE.sub("", value)
    value = re.sub(r"\s+", " ", value).strip().strip("'\"")
    return value


# Infobox fields we care about, mapped to semantic keys
INFOBOX_WINE_FIELDS = {
    "region": "region", "wine region": "region",
    "sub-region": "sub_region", "subregion": "sub_region",
    "country": "country",
    "location": "location",
    "state": "state", "province": "province",
    "grape": "grape", "grapes": "grape",
    "grape variety": "grape", "varieties": "grape", "primary grape": "grape",
    "established": "year_established", "year established": "year_established",
    "founded": "year_established", "year": "year_established",
    "inception": "year_established",
    "type": "type",
    "appellation": "appellation", "designation": "designation",
    "classification": "classification",
    "area": "area", "size": "area", "hectares": "area",
    "owner": "owner", "winemaker": "winemaker",
    "website": None, "image": None, "caption": None,
}


def parse_infobox(wikitext: str) -> list[dict]:
    """Extract infobox key-value pairs from wikitext.

    Returns list of dicts: {infobox_type, field, value}.
    """
    results = []
    text_lower = wikitext.lower()
    idx = 0

    while True:
        start = text_lower.find("{{infobox", idx)
        if start == -1:
            break

        # Extract infobox type from header line
        header_start = start + 2
        newline_pos = wikitext.find("\n", header_start)
        if newline_pos == -1:
            idx = start + 9
            continue

        header = wikitext[header_start:newline_pos].strip()
        infobox_type = (
            header.replace("Infobox", "").replace("infobox", "").strip()
        )

        # Track brace depth to find matching }}
        depth = 0
        end = start
        for i in range(start, min(start + 10000, len(wikitext) - 1)):
            if wikitext[i] == "{" and wikitext[i + 1] == "{":
                depth += 1
            elif wikitext[i] == "}" and wikitext[i + 1] == "}":
                depth -= 1
                if depth == 0:
                    end = i + 2
                    break

        if end <= start:
            idx = start + 9
            continue

        infobox_body = wikitext[start:end]
        for match in INFOBOX_FIELD_RE.finditer(infobox_body):
            field = match.group(1).strip().lower()
            value = _clean_wiki_value(match.group(2))
            if value:
                results.append({
                    "infobox_type": infobox_type,
                    "field": field,
                    "value": value,
                })

        idx = end

    return results


def build_infobox_facts(
    title: str,
    infobox_fields: list[dict],
    domain: str,
    subdomain: Optional[str],
    source_id: str,
) -> list[dict]:
    """Convert infobox fields into short atomic facts."""
    facts = []
    field_map = {}

    for entry in infobox_fields:
        semantic = INFOBOX_WINE_FIELDS.get(entry["field"])
        if semantic and entry["value"]:
            field_map[semantic] = entry["value"]

    region = field_map.get("region", "")
    country = field_map.get("country", "")
    location = field_map.get("location", "")
    state = field_map.get("state", "")
    province = field_map.get("province", "")
    loc_parts = [p for p in [location, region, state, province, country] if p]

    # --- wine_regions ---
    if domain == "wine_regions" and loc_parts:
        loc_str = ", ".join(loc_parts[:2])
        facts.append(_make_fact(
            f"{title} is a wine region in {loc_str}.",
            domain, subdomain, source_id, title, loc_parts,
        ))

    # --- producers ---
    if domain == "producers":
        if loc_parts:
            loc_str = ", ".join(loc_parts[:2])
            facts.append(_make_fact(
                f"{title} is a winery in {loc_str}.",
                domain, subdomain, source_id, title, loc_parts,
            ))
        year_raw = field_map.get("year_established")
        if year_raw:
            year = _extract_year(year_raw)
            if year:
                facts.append(_make_fact(
                    f"{title} was founded in {year}.",
                    domain, subdomain, source_id, title,
                ))
        owner = field_map.get("owner")
        if owner and len(owner) < 80:
            facts.append(_make_fact(
                f"{title} is owned by {owner}.",
                domain, subdomain, source_id, title,
            ))

    # --- grape_varieties ---
    if domain == "grape_varieties":
        origin = country or (loc_parts[0] if loc_parts else "")
        if origin:
            facts.append(_make_fact(
                f"{title} is a grape variety from {origin}.",
                domain, subdomain, source_id, title,
            ))

    # --- Grape varieties permitted in a region ---
    grape = field_map.get("grape")
    if grape and domain == "wine_regions":
        grapes = [g.strip() for g in re.split(r"[,;]", grape) if g.strip()]
        for g in grapes[:3]:
            if 2 < len(g) < 50:
                facts.append(_make_fact(
                    f"{title} permits the {g} grape variety.",
                    domain, subdomain, source_id, title, [g],
                ))

    # --- Classification ---
    cls = field_map.get("classification") or field_map.get("designation")
    if cls and domain == "wine_regions":
        facts.append(_make_fact(
            f"{title} holds {cls} classification.",
            domain, subdomain, source_id, title,
        ))

    # --- Area ---
    area = field_map.get("area")
    if area and domain == "wine_regions":
        area_num = re.sub(r"[^\d.,]", " ", area).strip()
        if area_num:
            facts.append(_make_fact(
                f"{title} covers approximately {area_num} hectares.",
                domain, subdomain, source_id, title,
            ))

    return facts


# ─── Atomic Rephrasing ───────────────────────────────────────────────────────
#
# The core of the v2 rewrite: every Wikipedia sentence is transformed into
# a short, atomic fact that is NOT a verbatim copy.


# Patterns to strip from sentences before rephrasing
_PAREN_PRONUNCIATION_RE = re.compile(
    r"\s*\([^)]*(?:pronunciation|IPA|/[^)]+/|listen|French:|Italian:|Spanish:"
    r"|German:|Portuguese:|Latin:|Greek:|Catalan:|Occitan:)[^)]*\)",
    re.IGNORECASE,
)
_PAREN_LANG_ANNOTATION_RE = re.compile(
    r"\s*\([A-Z][a-z]+:\s*[^)]{1,80}\)"
)
_PAREN_GENERIC_SHORT_RE = re.compile(
    r"\s*\([^)]{1,30}\)"  # short parentheticals like "(abbr.)" or "(lit.)"
)
_PAREN_FORMAL_NAME_RE = re.compile(
    r"\s*\((?:formally|formerly|originally|also known as|trading as|"
    r"full name|born|née|stylized|stylised|abbr)[^)]{1,100}\)",
    re.IGNORECASE,
)
# Parentheticals containing quotes — translations, etymologies, glosses
# e.g. (vinis cultura, 'wine-growing'), (from French "vin")
_PAREN_TRANSLATION_RE = re.compile(
    r"""\s*\([^)]*['\u2018\u2019\u201c\u201d"][^)]*\)"""
)


def rephrase_to_atomic(sentence: str, article_title: str) -> list[str]:
    """Transform a Wikipedia sentence into one or more atomic facts.

    Rules:
    a) Strip parenthetical pronunciation/language annotations
    b) Split compound sentences on semicolons and conjunctions
    c) Strip relative clauses (", which ...,")
    d) Truncate overly long sentences at the first comma after 15 words
    e) Prepend article_title as subject if missing
    f) Remove "Regarding X:" prefixes
    g) Target: 8-25 words per fact
    """
    # --- Clean up ---
    s = sentence.strip()
    if not s:
        return []

    # Remove pronunciation / IPA / language / formal-name / translation parentheticals
    s = _PAREN_PRONUNCIATION_RE.sub("", s)
    s = _PAREN_LANG_ANNOTATION_RE.sub("", s)
    s = _PAREN_FORMAL_NAME_RE.sub("", s)
    s = _PAREN_TRANSLATION_RE.sub("", s)
    s = _PAREN_GENERIC_SHORT_RE.sub("", s)

    # Collapse whitespace
    s = re.sub(r"\s+", " ", s).strip()

    # Strip alternative names: "X, Y, or Z is" → "X is"
    # e.g. "Viticulture, viniculture, or winegrowing is..." → "Viticulture is..."
    s = re.sub(
        r"^([A-Z][\w-]+(?:\s+[\w-]+)?)"    # First name (1-2 words)
        r"(?:,\s*[\w-]+(?:\s+[\w-]+)?)*"    # , alternative names
        r",?\s+(?:or|and)\s+[\w-]+(?:\s+[\w-]+)?"  # or/and last alternative
        r"\s+(is|are|was|were)\b",
        r"\1 \2", s,
    )

    # --- Split compound sentences ---
    # Split on semicolons
    parts = re.split(r"\s*;\s*", s)

    # Further split on ", although", ", however", ", while" etc.
    _CONJUNCTION_SPLIT = re.compile(
        r",?\s*\b(?:although|however|while|whereas|but|though|rather|"
        r"instead|moreover|furthermore|additionally|nonetheless|"
        r"nevertheless|therefore|thus|consequently|indeed)\s+",
        re.IGNORECASE,
    )
    expanded = []
    for part in parts:
        sub = _CONJUNCTION_SPLIT.split(part)
        expanded.extend(sub)

    results = []
    for part in expanded:
        fact = _rephrase_one_clause(part.strip(), article_title)
        if fact:
            results.append(fact)

    return results


def _rephrase_one_clause(clause: str, article_title: str) -> Optional[str]:
    """Rephrase a single clause into an atomic fact."""
    if not clause:
        return None

    s = clause.strip()

    # Strip relative clauses: ", which ..., " or ", who ..., "
    s = re.sub(r",\s+which\s[^,]{1,80},", ",", s)
    s = re.sub(r",\s+who\s[^,]{1,80},", ",", s)
    # Terminal relative clauses: ", which ..." at end of sentence
    s = re.sub(r",\s+which\s.{1,80}$", "", s)
    s = re.sub(r",\s+who\s.{1,80}$", "", s)

    # Remove "Regarding X:" prefixes
    s = re.sub(r"^Regarding\s+[^:]+:\s*", "", s, flags=re.IGNORECASE)

    # Truncate list-introducer sentences at the colon
    # "X is as follows: DOP – ..." → "X is as follows."
    s = re.sub(
        r"(?:,?\s+(?:and )?is\s+)?(?:as follows|including|such as)\s*:.*$",
        ".", s, flags=re.IGNORECASE,
    )

    # Strip leading conjunctions, adverbs, and discourse markers
    s = re.sub(
        r"^(?:Rather|Instead|Moreover|Furthermore|Additionally|Also|"
        r"Notably|Indeed|Nonetheless|Nevertheless|Therefore|Thus|"
        r"Consequently|Similarly|Conversely|Alternatively|Subsequently|"
        r"Meanwhile|Overall|Essentially|Specifically|Traditionally|"
        r"Historically|Generally|Typically|In fact|In particular|"
        r"As a result|For example|For instance|On the other hand|"
        r"However|Unlike\s+[^,]+)[,;]\s*",
        "", s, flags=re.IGNORECASE,
    )

    # Handle "In <topic>, this/it is..." → "<Topic> is..."
    m = re.match(r"^In\s+(\w[\w\s]{0,30}?),\s*(?:this|it)\s+(is|was|has)\b", s, re.IGNORECASE)
    if m:
        topic = m.group(1).strip()
        verb = m.group(2)
        s = f"{topic[0].upper()}{topic[1:]} {verb}{s[m.end():]}"

    # Capitalize first letter (clauses from splits may start lowercase)
    if s and s[0].islower():
        s = s[0].upper() + s[1:]

    # Remove leading "The " when followed by the article title
    if s.lower().startswith("the " + article_title.lower()):
        s = s[4:]

    # Ensure it ends with a period
    s = s.strip().rstrip(".")
    if not s:
        return None
    s += "."

    # Truncate: if >25 words, cut at first comma after word 15;
    # if no comma, try cutting at a conjunction; last resort: hard cut at 25
    words = s.split()
    if len(words) > 25:
        pos = 0
        for i, w in enumerate(words):
            pos = s.index(w, pos) + len(w)
            if i >= 14:
                break
        # Try comma first
        comma_pos = s.find(",", pos)
        if comma_pos != -1 and comma_pos < len(s) - 5:
            s = s[:comma_pos].rstrip() + "."
        else:
            # Try conjunction/relative pronoun as fallback cut point
            cut_match = re.search(
                r"\s+(?:which|that is|and\s+\w+s?\b|who)\s",
                s[pos:], re.IGNORECASE,
            )
            if cut_match:
                s = s[: pos + cut_match.start()].rstrip() + "."
            else:
                # Hard cut at word 25
                s = " ".join(words[:25]).rstrip(".") + "."

    # If the sentence doesn't start with the article title (or close),
    # prepend the title as subject
    words = s.split()
    if len(words) < 2:
        return None

    title_lower = article_title.lower()
    s_lower = s.lower()

    if not s_lower.startswith(title_lower):
        # Replace orphaned pronouns/articles with the article title
        if re.match(r"^It\s+is\b", s):
            s = f"{article_title} is{s[5:]}"
        elif re.match(r"^It\s+was\b", s):
            s = f"{article_title} was{s[6:]}"
        elif re.match(r"^It\s+has\b", s):
            s = f"{article_title} has{s[6:]}"
        elif re.match(r"^It\s+", s):
            s = f"{article_title} {s[3:]}"
        elif re.match(r"^They\s+are\b", s) or re.match(r"^These\s+", s):
            # Plural pronouns without referent — skip
            return None
        elif re.match(r"^This\s+is\b", s):
            s = f"{article_title} is{s[7:]}"
        elif re.match(r"^This\s+was\b", s):
            s = f"{article_title} was{s[8:]}"
        elif re.match(
            r"^[Tt]he\s+(?:wine\s+)?(?:region|grape|variety|vineyard|"
            r"winery|appellation|area|estate|domaine|denomination)\s", s,
        ):
            # "The region primarily uses..." → "Burgundy primarily uses..."
            m = re.match(
                r"^[Tt]he\s+(?:wine\s+)?(?:region|grape|variety|vineyard|"
                r"winery|appellation|area|estate|domaine|denomination)\s+", s,
            )
            s = f"{article_title} {s[m.end():]}"
        else:
            # For other cases, just capitalize — don't blindly prepend title
            if not s[0].isupper():
                s = s[0].upper() + s[1:]

    # Final length check
    words = s.split()
    if len(words) < 4 or len(words) > 40:
        return None

    return s


# ─── Lead Paragraph Extraction ───────────────────────────────────────────────


def extract_lead_facts(
    title: str,
    extract_text: str,
    domain: str,
    subdomain: Optional[str],
    source_id: str,
) -> list[dict]:
    """Extract atomic facts from the lead paragraph of a Wikipedia article.

    - Only keeps wine-relevant sentences
    - Rephrases every sentence (never verbatim)
    - Max MAX_LEAD_FACTS_PER_ARTICLE facts
    """
    if not extract_text or len(extract_text) < 50:
        return []

    facts = []
    sentences = re.split(r"(?<=[.!?])\s+", extract_text.strip())

    for sentence in sentences[:12]:  # scan first 12 sentences, cap output later
        sentence = sentence.strip()
        if not sentence:
            continue

        # Wine relevance gate
        if not is_wine_relevant(sentence):
            continue

        # Opinion gate
        if not passes_opinion_filter(sentence):
            continue

        # Rephrase into atomic facts (may produce 1-2 facts from one sentence)
        atomic_facts = rephrase_to_atomic(sentence, title)
        for fact_text in atomic_facts:
            if not is_wine_relevant(fact_text):
                continue

            facts.append(
                _make_fact(fact_text, domain, subdomain, source_id, title)
            )
            if len(facts) >= MAX_LEAD_FACTS_PER_ARTICLE:
                return facts

    return facts


# ─── Deduplication ────────────────────────────────────────────────────────────


def _load_existing_facts_for_dedup() -> list[str]:
    """Load existing fact texts from DB for substring dedup."""
    try:
        from src.utils.db import get_pg

        conn = get_pg()
        cur = conn.cursor()
        cur.execute(
            "SELECT fact_text FROM facts WHERE fact_text IS NOT NULL LIMIT 50000"
        )
        return [r["fact_text"].lower() for r in cur.fetchall()]
    except Exception as e:
        logger.warning(f"Could not load existing facts for dedup: {e}")
        return []


def deduplicate_facts(
    new_facts: list[dict], existing_texts: list[str]
) -> list[dict]:
    """Skip facts whose core entity+predicate already exists.

    Checks: is the new fact a substring of any existing fact, or vice versa?
    """
    if not existing_texts:
        return new_facts

    filtered = []
    for fact in new_facts:
        fact_lower = fact["fact_text"].lower()
        is_dup = False
        for existing in existing_texts:
            shorter = min(fact_lower, existing, key=len)
            longer = max(fact_lower, existing, key=len)
            if shorter in longer:
                is_dup = True
                break
        if not is_dup:
            filtered.append(fact)

    removed = len(new_facts) - len(filtered)
    if removed > 0:
        logger.info(f"Dedup removed {removed} near-duplicate facts")
    return filtered


# ─── Progress Tracking ────────────────────────────────────────────────────────


def _load_progress() -> dict:
    path = Path(PROGRESS_FILE)
    if path.exists():
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            return {"processed": {}}
    return {"processed": {}}


def _save_progress(progress: dict):
    path = Path(PROGRESS_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(progress, indent=2))


def _mark_processed(progress: dict, category: str, title: str):
    if category not in progress["processed"]:
        progress["processed"][category] = []
    progress["processed"][category].append(title)


def _is_processed(progress: dict, category: str, title: str) -> bool:
    return title in progress.get("processed", {}).get(category, [])


# ─── Article Processing ──────────────────────────────────────────────────────


def process_article(
    session: requests.Session,
    title: str,
    domain: str,
    subdomain: Optional[str],
    existing_facts: list[str],
    dry_run: bool = False,
) -> list[dict]:
    """Process a single Wikipedia article.

    Phase A: Infobox extraction (structured data).
    Phase B: Lead paragraph extraction (rephrased atomic facts).
    """
    all_facts = []

    # Register source
    article_url = (
        f"https://en.wikipedia.org/wiki/{url_quote(title.replace(' ', '_'))}"
    )
    if not dry_run:
        source_id = ensure_source(
            name=f"Wikipedia: {title}",
            url=article_url,
            source_type="encyclopedia",
            tier=SOURCE_TIER,
        )
    else:
        source_id = "dry-run"

    # --- Phase A: Infobox ---
    wikitext = get_article_wikitext(session, title)
    if wikitext:
        infobox_fields = parse_infobox(wikitext)
        if infobox_fields:
            infobox_facts = build_infobox_facts(
                title, infobox_fields, domain, subdomain, source_id
            )
            all_facts.extend(infobox_facts)
            logger.debug(f"  Infobox: {len(infobox_facts)} facts")

    # --- Phase B: Lead paragraph ---
    extract_text = get_article_extract(session, title)
    if extract_text:
        # Check for disambiguation via text (fast path)
        if "may refer to" in extract_text or "can refer to" in extract_text:
            logger.debug(f"  Skip (disambiguation): {title}")
            return []

        # Stub check
        if len(extract_text) < MIN_ARTICLE_LENGTH:
            logger.debug(f"  Skip (stub, {len(extract_text)} chars): {title}")
            return []

        # Per-sentence wine relevance is checked inside extract_lead_facts();
        # no need for a first-sentence gate here since all articles come from
        # wine-related categories and individual sentences are filtered.

        lead_facts = extract_lead_facts(
            title, extract_text, domain, subdomain, source_id
        )
        all_facts.extend(lead_facts)
        logger.debug(f"  Lead: {len(lead_facts)} facts")

    elif not wikitext:
        logger.debug(f"  Skip (empty article): {title}")
        return []

    # Deduplicate against existing facts
    if all_facts and existing_facts:
        all_facts = deduplicate_facts(all_facts, existing_facts)

    return all_facts


# ─── Category Scraping ────────────────────────────────────────────────────────


def scrape_category(
    category_key: str,
    dry_run: bool = False,
    resume: bool = True,
) -> int:
    """Scrape all articles in a category tree and insert facts."""
    if category_key not in CATEGORIES:
        logger.error(
            f"Unknown category: {category_key}. "
            f"Available: {list(CATEGORIES.keys())}"
        )
        return 0

    config = CATEGORIES[category_key]
    domain = config["domain"]
    subdomain = config["subdomain"]
    roots = _get_roots(config)

    logger.info(f"Scraping category: {category_key} ({config['description']})")
    logger.info(f"  Roots: {roots}, Domain: {domain}")

    session = _make_session()

    # Discover articles
    logger.info("Crawling category tree...")
    articles = []
    for root in roots:
        root_articles = get_category_members(session, root)
        articles.extend(root_articles)
        logger.info(f"  {root}: {len(root_articles)} articles")
    articles = list(dict.fromkeys(articles))  # dedup preserving order
    logger.info(
        f"Found {len(articles)} unique articles across {len(roots)} root(s)"
    )

    if dry_run:
        click.echo(
            f"  {category_key}: {len(articles)} articles (dry run, no insertion)"
        )
        return 0

    # Load progress
    progress = _load_progress() if resume else {"processed": {}}

    # Load existing facts for dedup
    logger.info("Loading existing facts for deduplication...")
    existing_facts = _load_existing_facts_for_dedup()
    logger.info(f"Loaded {len(existing_facts)} existing facts for dedup")

    total_inserted = 0
    total_facts = 0
    batch_buffer = []
    batch_size = 100

    for idx, title in enumerate(articles):
        if _is_processed(progress, category_key, title):
            continue

        try:
            facts = process_article(
                session, title, domain, subdomain, existing_facts
            )
            total_facts += len(facts)
            batch_buffer.extend(facts)

            click.echo(
                f"Processing [{idx + 1}/{len(articles)}] {category_key}: "
                f"{title} — {len(facts)} facts extracted"
            )

            # Batch insert
            if len(batch_buffer) >= batch_size:
                inserted = insert_facts_batch(batch_buffer)
                total_inserted += inserted
                for f in batch_buffer:
                    existing_facts.append(f["fact_text"].lower())
                batch_buffer = []
                logger.info(
                    f"  Progress: {total_inserted} inserted / "
                    f"{total_facts} extracted"
                )

            _mark_processed(progress, category_key, title)
            if (idx + 1) % 50 == 0:
                _save_progress(progress)

        except Exception as e:
            logger.error(f"Error processing {title}: {e}")
            continue

    # Flush remaining
    if batch_buffer:
        inserted = insert_facts_batch(batch_buffer)
        total_inserted += inserted
        for f in batch_buffer:
            existing_facts.append(f["fact_text"].lower())

    _save_progress(progress)
    logger.info(
        f"Category {category_key}: {total_inserted} new facts "
        f"({total_facts} extracted)"
    )
    return total_inserted


def scrape_all(dry_run: bool = False) -> dict:
    """Scrape all categories. Returns per-category counts."""
    summary = {}
    for cat_key in CATEGORIES:
        summary[cat_key] = scrape_category(cat_key, dry_run=dry_run)

    total = sum(summary.values())
    logger.info(f"Wikipedia scraping complete. Total new facts: {total}")
    if not dry_run:
        logger.info(f"Total facts in database: {get_fact_count()}")
    return summary


# ─── Validation ───────────────────────────────────────────────────────────────


def validate():
    """Run quality checks on Wikipedia-sourced facts in the database."""
    from src.utils.db import get_pg

    conn = get_pg()
    cur = conn.cursor()

    cur.execute("""
        SELECT f.fact_text, f.domain, f.subdomain, f.entities
        FROM facts f
        JOIN sources s ON f.source_id = s.id
        WHERE s.url LIKE 'https://en.wikipedia.org/wiki/%%'
    """)
    rows = cur.fetchall()

    if not rows:
        click.echo("No Wikipedia facts found in the database.")
        return

    n = len(rows)
    click.echo(f"\nValidation Report — Wikipedia Facts ({n} total)")
    click.echo("=" * 60)

    # a) Domain distribution
    domain_counts = defaultdict(int)
    subdomain_counts = defaultdict(int)
    for row in rows:
        domain_counts[row["domain"]] += 1
        if row["subdomain"]:
            subdomain_counts[f"{row['domain']}/{row['subdomain']}"] += 1

    click.echo("\nDomain distribution:")
    for dom, cnt in sorted(domain_counts.items(), key=lambda x: -x[1]):
        click.echo(f"  {dom:25s}: {cnt} facts")
    if subdomain_counts:
        click.echo("\nSubdomain distribution:")
        for sd, cnt in sorted(subdomain_counts.items(), key=lambda x: -x[1]):
            click.echo(f"  {sd:25s}: {cnt} facts")

    # b) Length checks
    too_short = [r for r in rows if len(r["fact_text"].split()) < 5]
    too_long = [r for r in rows if len(r["fact_text"].split()) > 50]

    # c) No-predicate facts
    no_predicate = [r for r in rows if len(r["fact_text"].rstrip(".").split()) <= 2]

    # d) Near-duplicate check
    fact_texts = [r["fact_text"].lower() for r in rows]
    near_dupes = 0
    checked = set()
    for i, t1 in enumerate(fact_texts):
        if i in checked:
            continue
        for j in range(i + 1, len(fact_texts)):
            if j in checked:
                continue
            t2 = fact_texts[j]
            shorter = min(t1, t2, key=len)
            longer = max(t1, t2, key=len)
            if shorter in longer and shorter != longer:
                near_dupes += 1
                checked.add(j)
                break

    # e) Entity coverage
    import orjson

    has_entities = 0
    for r in rows:
        ents = r["entities"]
        if isinstance(ents, str):
            ents = orjson.loads(ents)
        if ents:
            has_entities += 1
    missing_entities = n - has_entities

    click.echo("\nQuality:")
    click.echo(f"  Too short (<5 words):  {len(too_short)} ({100*len(too_short)/n:.1f}%)")
    click.echo(f"  Too long (>50 words):  {len(too_long)} ({100*len(too_long)/n:.1f}%)")
    click.echo(f"  No predicate:          {len(no_predicate)} ({100*len(no_predicate)/n:.1f}%)")
    click.echo(f"  Missing entities:      {missing_entities} ({100*missing_entities/n:.1f}%)")
    click.echo(f"  Possible near-dupes:   {near_dupes} ({100*near_dupes/n:.1f}%)")

    # f) Random sample
    sample_size = min(10, n)
    sample = random.sample(rows, sample_size)
    click.echo(f"\nSample facts ({sample_size}):")
    for i, r in enumerate(sample, 1):
        click.echo(f"  {i}. \"{r['fact_text']}\"")
    click.echo()


# ─── Test Run ─────────────────────────────────────────────────────────────────


def test_run_category(
    category_key: str,
    session: requests.Session,
    existing_facts: list[str],
) -> dict:
    """Process first TEST_RUN_ITEMS_PER_CATEGORY articles from a category.

    Returns a stats dict with items_processed, facts_generated,
    facts_inserted, and the list of all generated fact dicts.
    """
    config = CATEGORIES[category_key]
    domain = config["domain"]
    subdomain = config["subdomain"]
    roots = _get_roots(config)

    # Discover articles (full crawl — we just limit how many we process)
    articles = []
    for root in roots:
        root_articles = get_category_members(session, root)
        articles.extend(root_articles)
    articles = list(dict.fromkeys(articles))

    limit = TEST_RUN_ITEMS_PER_CATEGORY
    selected = articles[:limit]

    all_generated = []
    items_processed = 0

    for idx, title in enumerate(selected):
        click.echo(
            f"  [{idx + 1}/{len(selected)}] {category_key}: {title}",
            nl=False,
        )
        try:
            facts = process_article(
                session, title, domain, subdomain, existing_facts
            )
            all_generated.extend(facts)
            items_processed += 1
            click.echo(f" — {len(facts)} facts")
        except Exception as e:
            click.echo(f" — ERROR: {e}")
            continue

    # Insert into DB
    facts_inserted = 0
    if all_generated:
        facts_inserted = insert_facts_batch(all_generated)
        for f in all_generated:
            existing_facts.append(f["fact_text"].lower())

    return {
        "category": category_key,
        "items_processed": items_processed,
        "facts_generated": len(all_generated),
        "facts_inserted": facts_inserted,
        "facts": all_generated,
    }


def _print_test_run_report(
    cat_stats: list[dict],
    cleanup: bool = False,
):
    """Print structured report and warnings for a test run."""
    from src.utils.db import get_pg

    all_facts = []
    for cs in cat_stats:
        all_facts.extend(cs["facts"])

    total_items = sum(cs["items_processed"] for cs in cat_stats)
    total_generated = sum(cs["facts_generated"] for cs in cat_stats)
    total_inserted = sum(cs["facts_inserted"] for cs in cat_stats)

    # ── Report Table ──
    click.echo("\n=== TEST RUN REPORT ===")
    hdr = f"{'Source/Category':<25s} {'Items Processed':>17s} {'Facts Generated':>17s} {'Facts Inserted (new)':>22s}"
    click.echo(hdr)
    click.echo("\u2500" * len(hdr))

    for cs in cat_stats:
        click.echo(
            f"{cs['category']:<25s} {cs['items_processed']:>17d} "
            f"{cs['facts_generated']:>17d} {cs['facts_inserted']:>22d}"
        )

    click.echo("\u2500" * len(hdr))
    click.echo(
        f"{'TOTAL':<25s} {total_items:>17d} "
        f"{total_generated:>17d} {total_inserted:>22d}"
    )

    # ── Quality Checks ──
    if all_facts:
        n = len(all_facts)
        too_short = [f for f in all_facts if len(f["fact_text"].split()) < 5]
        too_long = [f for f in all_facts if len(f["fact_text"].split()) > 50]
        word_counts = [len(f["fact_text"].split()) for f in all_facts]
        avg_words = sum(word_counts) / n

        import orjson

        missing_ents = 0
        for f in all_facts:
            ents = f.get("entities", [])
            if isinstance(ents, str):
                ents = orjson.loads(ents)
            if not ents:
                missing_ents += 1

        click.echo("\nQuality Checks:")
        click.echo(f"  Too short (<5 words):    {len(too_short)} ({100*len(too_short)/n:.1f}%)")
        click.echo(f"  Too long (>50 words):    {len(too_long)} ({100*len(too_long)/n:.1f}%)")
        click.echo(f"  Missing entities:        {missing_ents} ({100*missing_ents/n:.1f}%)")
        click.echo(f"  Avg words per fact:      {avg_words:.1f}")

        # Sample facts
        sample_size = min(10, n)
        sample = random.sample(all_facts, sample_size)
        click.echo(f"\nSample Facts ({sample_size} random from this run):")
        for i, f in enumerate(sample, 1):
            click.echo(f"  {i:>3d}. \"{f['fact_text']}\"")

    # ── Warnings ──
    warnings = []

    for cs in cat_stats:
        cat = cs["category"]
        if cs["facts_inserted"] == 0 and cs["items_processed"] > 0:
            warnings.append(f"ERROR: No facts from {cat}")
        if cs["items_processed"] > 0:
            avg_per_item = cs["facts_generated"] / cs["items_processed"]
            if avg_per_item < 2:
                warnings.append(
                    f"WARNING: Low extraction rate in {cat} "
                    f"({avg_per_item:.1f} facts/item)"
                )
        if cs["facts_generated"] > 0:
            dup_rate = 1 - cs["facts_inserted"] / cs["facts_generated"]
            if dup_rate > 0.5:
                warnings.append(
                    f"WARNING: High duplicate rate in {cat} "
                    f"({100*dup_rate:.0f}% skipped)"
                )

    if all_facts:
        n = len(all_facts)
        n_short = sum(1 for f in all_facts if len(f["fact_text"].split()) < 5)
        n_long = sum(1 for f in all_facts if len(f["fact_text"].split()) > 50)
        if n_short / n > 0.1:
            warnings.append("WARNING: Too many trivial facts (>10% under 5 words)")
        if n_long / n > 0.1:
            warnings.append("WARNING: Facts need better splitting (>10% over 50 words)")

        for f in all_facts:
            if "Regarding" in f["fact_text"]:
                warnings.append(
                    f"WARNING: Verbatim text detected — \"{f['fact_text'][:80]}...\""
                )

        over_40 = [f for f in all_facts if len(f["fact_text"].split()) > 40]
        for f in over_40:
            warnings.append(
                f"WARNING: Fact over 40 words — \"{f['fact_text'][:100]}...\""
            )

    if warnings:
        click.echo(f"\nWarnings ({len(warnings)}):")
        for w in warnings:
            click.echo(f"  {w}")
    else:
        click.echo("\nNo warnings.")

    # ── Cleanup ──
    if cleanup and all_facts:
        fact_texts = [f["fact_text"] for f in all_facts]
        conn = get_pg()
        cur = conn.cursor()

        # Find IDs of facts we just inserted
        placeholders = ",".join(["%s"] * len(fact_texts))
        cur.execute(
            f"SELECT id FROM facts WHERE fact_text IN ({placeholders})",
            fact_texts,
        )
        ids = [row["id"] for row in cur.fetchall()]

        if ids:
            id_placeholders = ",".join(["%s"] * len(ids))
            cur.execute(
                f"DELETE FROM facts WHERE id IN ({id_placeholders})",
                [str(i) for i in ids],
            )
            conn.commit()
            click.echo(f"\nCleaned up {len(ids)} test facts from database.")
        else:
            click.echo("\nNo test facts to clean up.")

    click.echo()


def run_test_run(
    category: Optional[str] = None,
    cleanup: bool = False,
):
    """Execute a test run: 5 items per category, insert, report, optionally cleanup."""
    session = _make_session()

    # Load existing facts for dedup
    logger.info("Loading existing facts for deduplication...")
    existing_facts = _load_existing_facts_for_dedup()
    logger.info(f"Loaded {len(existing_facts)} existing facts for dedup")

    # Determine which categories to process
    if category:
        if category not in CATEGORIES:
            click.echo(
                f"Unknown category: {category}. "
                f"Available: {', '.join(CATEGORIES.keys())}"
            )
            return
        cat_keys = [category]
    else:
        cat_keys = list(CATEGORIES.keys())

    click.echo(
        f"\n=== TEST RUN — {TEST_RUN_ITEMS_PER_CATEGORY} items per category "
        f"({len(cat_keys)} categories) ===\n"
    )

    cat_stats = []
    for cat_key in cat_keys:
        click.echo(f"\n--- {cat_key} ---")
        stats = test_run_category(cat_key, session, existing_facts)
        cat_stats.append(stats)

    _print_test_run_report(cat_stats, cleanup=cleanup)


# ─── CLI ──────────────────────────────────────────────────────────────────────


@click.command()
@click.option(
    "--category", "-c", type=str,
    help="Scrape a specific category "
    "(regions/grapes/wineries/appellations/classifications/viticulture/oenology)",
)
@click.option("--all", "run_all", is_flag=True, help="Scrape all categories")
@click.option(
    "--list", "list_categories", is_flag=True,
    help="List available categories with article counts",
)
@click.option(
    "--dry-run", is_flag=True,
    help="Crawl categories and count articles without inserting",
)
@click.option(
    "--validate", "run_validate", is_flag=True,
    help="Run quality checks on existing Wikipedia facts",
)
@click.option(
    "--test-run", "test_run", is_flag=True,
    help="Process 5 items per category, insert, and print quality report",
)
@click.option(
    "--cleanup", is_flag=True,
    help="With --test-run: delete inserted facts after printing report",
)
def main(
    category: Optional[str],
    run_all: bool,
    list_categories: bool,
    dry_run: bool,
    run_validate: bool,
    test_run: bool,
    cleanup: bool,
):
    """OenoBench Wikipedia Scraper — Extract wine facts from English Wikipedia."""
    os.makedirs("data/logs", exist_ok=True)
    logger.add("data/logs/wikipedia_{time}.log", rotation="10 MB")

    if run_validate:
        validate()
        return

    if test_run:
        run_test_run(category=category, cleanup=cleanup)
        return

    if list_categories:
        click.echo("\nAvailable categories:")
        session = _make_session()
        for key, config in CATEGORIES.items():
            click.echo(f"  {key:20s} — {config['description']}")
            for root in _get_roots(config):
                params = {
                    "action": "query",
                    "list": "categorymembers",
                    "cmtitle": root,
                    "cmtype": "page|subcat",
                    "cmlimit": "500",
                    "format": "json",
                    "formatversion": "2",
                }
                try:
                    time.sleep(REQUEST_DELAY)
                    resp = session.get(API_ENDPOINT, params=params, timeout=30)
                    data = resp.json()
                    members = data.get("query", {}).get("categorymembers", [])
                    pages = sum(1 for m in members if m.get("ns") == 0)
                    subcats = sum(1 for m in members if m.get("ns") == 14)
                    click.echo(
                        f"  {'':20s}   {root}: "
                        f"{pages} articles, {subcats} subcategories"
                    )
                except Exception:
                    click.echo(
                        f"  {'':20s}   {root}: (count unavailable)"
                    )
        return

    if dry_run:
        click.echo("\n=== DRY RUN — Counting articles per category ===\n")
        if category:
            scrape_category(category, dry_run=True)
        else:
            session = _make_session()
            for key, config in CATEGORIES.items():
                all_articles = []
                for root in _get_roots(config):
                    all_articles.extend(get_category_members(session, root))
                all_articles = list(dict.fromkeys(all_articles))
                click.echo(f"  {key:20s}: {len(all_articles)} articles")
            click.echo("\nNo facts inserted (dry run).")
        return

    if run_all:
        summary = scrape_all(dry_run=False)
        click.echo("\nSummary:")
        for name, count in summary.items():
            click.echo(f"  {name:20s}: {count} facts")
        click.echo(f"  {'TOTAL':20s}: {sum(summary.values())} facts")
        return

    if category:
        count = scrape_category(category, dry_run=False)
        click.echo(f"\nInserted {count} new facts from '{category}' category.")
        return

    click.echo(
        "Use --all to scrape all categories, "
        "or --category <name> for a specific one.\n"
        "Use --list to see available categories, "
        "--dry-run to count without inserting.\n"
        "Use --validate to check quality of existing Wikipedia facts."
    )


if __name__ == "__main__":
    main()
