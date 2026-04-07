"""
Shared helpers for scrapers that use Wikipedia MediaWiki API and Wikidata SPARQL.

Extracts reusable functions from wikipedia.py and wikidata.py to avoid
duplicating ~200 lines of boilerplate across regional scrapers.
"""

import re
import time
from typing import Optional

import requests
from loguru import logger
from SPARQLWrapper import SPARQLWrapper, JSON

from src.utils.facts import ensure_source

# ─── Configuration ───────────────────────────────────────────────────────────

API_ENDPOINT = "https://en.wikipedia.org/w/api.php"
WIKIDATA_ENDPOINT = "https://query.wikidata.org/sparql"
USER_AGENT = "OenoBench-Research/1.0 (academic wine benchmark)"
WIKI_REQUEST_DELAY = 2.0  # seconds between Wikipedia API requests
SPARQL_REQUEST_DELAY = 1.5  # seconds between SPARQL queries
MAX_CATEGORY_DEPTH = 3
MAX_ARTICLES_PER_ROOT = 500

# ─── Regex patterns (reused from wikipedia.py) ──────────────────────────────

INFOBOX_FIELD_RE = re.compile(
    r"^\s*\|\s*(\w[\w\s]*?)\s*=\s*(.+?)$", re.MULTILINE
)
WIKI_LINK_RE = re.compile(r"\[\[(?:[^|\]]*\|)?([^\]]+)\]\]")
WIKI_REF_RE = re.compile(r"<ref[^>]*>.*?</ref>|<ref[^>]*/>", re.DOTALL)
WIKI_TAG_RE = re.compile(r"<[^>]+>")
WIKI_TEMPLATE_SIMPLE_RE = re.compile(r"\{\{[^{}]*\}\}")

NON_ARTICLE_TITLE_RE = re.compile(
    r"^(?:List of |Lists of |Template:|Wikipedia:|Portal:|Category:|File:|Draft:)",
    re.IGNORECASE,
)

# Wine relevance keywords
WINE_KEYWORDS = {
    "wine", "winery", "wineries", "vineyard", "vineyards", "grape", "grapes",
    "viticulture", "viticultural", "viniculture", "vinification", "oenology",
    "enology", "winemaker", "winemaking", "vintner", "sommelier",
    "appellation", "aoc", "aop", "doc", "docg", "dop", "ava", "vqa",
    "denomination", "cru", "grand cru", "premier cru", "classico",
    "riserva", "reserva", "crianza", "gran reserva",
    "pinot", "cabernet", "merlot", "chardonnay", "riesling", "syrah",
    "shiraz", "sauvignon", "sangiovese", "nebbiolo", "tempranillo",
    "malbec", "grenache", "mourvèdre", "zinfandel", "gamay",
    "muscat", "moscato", "trebbiano", "barbera", "viognier", "chenin",
    "fermentation", "barrel", "oak", "tannin", "tannins", "acidity",
    "vintage", "varietal", "terroir", "blend", "cuvée", "cuvee",
    "sparkling", "fortified", "dessert wine", "rosé",
    "red wine", "white wine", "harvest", "bottling", "cellar",
    "maceration", "malolactic", "lees", "chaptalisation",
    "côte", "cote", "château", "chateau", "domaine", "estate",
    "hectare", "hectares", "rootstock", "phylloxera", "pruning",
    "alcohol", "abv",
}

_WINE_KW_RE = re.compile(
    r"\b(?:" + "|".join(
        re.escape(kw) for kw in sorted(WINE_KEYWORDS, key=len, reverse=True)
    ) + r")\b",
    re.IGNORECASE,
)


# ─── Session ─────────────────────────────────────────────────────────────────


def wiki_session() -> requests.Session:
    """Create a requests.Session with proper User-Agent for MediaWiki API."""
    session = requests.Session()
    session.headers.update({
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    })
    return session


# ─── MediaWiki API ───────────────────────────────────────────────────────────


def _api_request(
    session: requests.Session, params: dict, max_retries: int = 4
) -> dict:
    """MediaWiki API request with rate limiting and exponential backoff."""
    params["format"] = "json"
    params["formatversion"] = "2"

    for attempt in range(max_retries + 1):
        try:
            time.sleep(WIKI_REQUEST_DELAY)
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
                logger.error(f"Request failed after {max_retries + 1} attempts: {e}")
                return {}
    return {}


def fetch_article(
    session: requests.Session, title: str
) -> tuple[Optional[str], Optional[str]]:
    """Fetch both plain-text extract and wikitext for a Wikipedia article.

    Returns (extract_text, wikitext). Either may be None if unavailable.
    """
    params = {
        "action": "query",
        "titles": title,
        "prop": "extracts|revisions",
        "exintro": "1",
        "explaintext": "1",
        "rvprop": "content",
        "rvslots": "main",
        "redirects": "1",
    }
    data = _api_request(session, params)
    if not data or "query" not in data:
        return None, None

    pages = data["query"].get("pages", [])
    if not pages:
        return None, None

    page = pages[0]
    if page.get("missing", False):
        return None, None

    extract = page.get("extract", "") or None
    wikitext = None
    revisions = page.get("revisions", [])
    if revisions:
        slots = revisions[0].get("slots", {})
        main_slot = slots.get("main", {})
        wikitext = main_slot.get("content", "")
        if not wikitext:
            wikitext = None

    return extract, wikitext


def fetch_full_extract(session: requests.Session, title: str) -> Optional[str]:
    """Fetch the FULL article extract (not just intro) as plain text."""
    params = {
        "action": "query",
        "titles": title,
        "prop": "extracts",
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
    return page.get("extract", "") or None


def crawl_category(
    session: requests.Session,
    category: str,
    max_depth: int = MAX_CATEGORY_DEPTH,
    max_articles: int = MAX_ARTICLES_PER_ROOT,
) -> list[str]:
    """Recursively crawl a Wikipedia category tree and return article titles."""
    seen_categories: set[str] = set()
    article_count = [0]

    def _crawl(cat: str, depth: int) -> list[str]:
        if depth > max_depth or cat in seen_categories:
            return []
        seen_categories.add(cat)
        articles = []
        cmcontinue = None

        while True:
            if article_count[0] >= max_articles:
                break
            params = {
                "action": "query",
                "list": "categorymembers",
                "cmtitle": cat,
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
                    articles.extend(_crawl(title, depth + 1))

            cont = data.get("continue", {})
            cmcontinue = cont.get("cmcontinue")
            if not cmcontinue or article_count[0] >= max_articles:
                break
        return articles

    return _crawl(category, 0)


# ─── Wikitext Parsing ────────────────────────────────────────────────────────


def clean_wiki_value(value: str) -> str:
    """Strip wiki markup from a field value."""
    value = WIKI_REF_RE.sub("", value)
    value = WIKI_LINK_RE.sub(r"\1", value)
    value = WIKI_TAG_RE.sub("", value)
    value = WIKI_TEMPLATE_SIMPLE_RE.sub("", value)
    value = re.sub(r"\s+", " ", value).strip().strip("'\"")
    return value


def parse_infobox(wikitext: str) -> dict[str, str]:
    """Extract infobox key-value pairs from wikitext.

    Returns a flat dict of field_name -> cleaned_value.
    """
    results = {}
    text_lower = wikitext.lower()
    idx = 0

    while True:
        start = text_lower.find("{{infobox", idx)
        if start == -1:
            break

        newline_pos = wikitext.find("\n", start + 2)
        if newline_pos == -1:
            idx = start + 9
            continue

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
            value = clean_wiki_value(match.group(2))
            if value:
                results[field] = value
        idx = end

    return results


def parse_wikitext_tables(wikitext: str) -> list[list[str]]:
    """Extract rows from wikitext tables.

    Returns a list of rows, where each row is a list of cell values.
    Handles both {| ... |} table syntax with || delimiters and |-/| rows.
    """
    tables = []
    # Find table blocks
    table_pattern = re.compile(r"\{\|[^\n]*\n(.*?)\|\}", re.DOTALL)
    for table_match in table_pattern.finditer(wikitext):
        table_body = table_match.group(1)
        rows = []
        current_row: list[str] = []

        for line in table_body.split("\n"):
            line = line.strip()
            if line.startswith("|-"):
                if current_row:
                    rows.append(current_row)
                current_row = []
            elif line.startswith("!"):
                # Header row — treat like data
                cells = re.split(r"\s*!!\s*", line.lstrip("! "))
                current_row.extend(clean_wiki_value(c) for c in cells if c.strip())
            elif line.startswith("|"):
                cells = re.split(r"\s*\|\|\s*", line.lstrip("| "))
                current_row.extend(clean_wiki_value(c) for c in cells if c.strip())

        if current_row:
            rows.append(current_row)
        if rows:
            tables.extend(rows)

    return tables


# ─── Lead Sentence Extraction ────────────────────────────────────────────────


def extract_lead_sentences(extract: str, min_words: int = 5) -> list[str]:
    """Split a Wikipedia extract into individual sentences.

    Filters for wine-relevant content and minimum length.
    Returns cleaned sentences (not yet rephrased into atomic facts).
    """
    if not extract:
        return []

    # Split on sentence boundaries
    sentences = re.split(r"(?<=[.!?])\s+", extract)
    results = []

    for s in sentences:
        s = s.strip()
        if not s:
            continue
        words = s.split()
        if len(words) < min_words:
            continue
        if len(words) > 50:
            continue
        # Must contain at least one wine keyword
        if not _WINE_KW_RE.search(s):
            continue
        results.append(s)

    return results


# ─── SPARQL ──────────────────────────────────────────────────────────────────


def run_sparql(query: str) -> list[dict]:
    """Execute a SPARQL query against Wikidata and return results as dicts."""
    sparql = SPARQLWrapper(WIKIDATA_ENDPOINT)
    sparql.setQuery(query)
    sparql.setReturnFormat(JSON)
    sparql.addCustomHttpHeader("User-Agent", USER_AGENT)

    logger.info("Executing SPARQL query...")
    time.sleep(SPARQL_REQUEST_DELAY)
    results = sparql.query().convert()

    rows = []
    for binding in results["results"]["bindings"]:
        row = {}
        for key, val in binding.items():
            row[key] = val.get("value", "")
        rows.append(row)

    logger.info(f"SPARQL query returned {len(rows)} results")
    return rows


# ─── Source Registration ─────────────────────────────────────────────────────


def ensure_wiki_source(scope: str) -> str:
    """Register a Wikipedia source for a specific scope (e.g. 'Bordeaux wine').

    Returns the source UUID.
    """
    return ensure_source(
        name=f"Wikipedia: {scope}",
        url=f"https://en.wikipedia.org/wiki/{scope.replace(' ', '_')}",
        source_type="encyclopedia",
        tier="tier_2_authoritative",
        language="en",
    )


def ensure_wikidata_source(scope: str = "wine") -> str:
    """Register Wikidata as a source for a specific scope.

    Returns the source UUID.
    """
    return ensure_source(
        name=f"Wikidata: {scope}",
        url="https://www.wikidata.org",
        source_type="knowledge_base",
        tier="tier_2_authoritative",
        language="en",
    )


# ─── Wine Relevance ─────────────────────────────────────────────────────────


def is_wine_relevant(text: str) -> bool:
    """Return True if text contains at least one wine keyword."""
    return bool(_WINE_KW_RE.search(text))
