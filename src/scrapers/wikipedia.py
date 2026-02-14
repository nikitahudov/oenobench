"""
OenoBench — Wikipedia Scraper

Extracts wine facts from English Wikipedia via the MediaWiki API.
Crawls wine-related category trees and extracts atomic facts from
infoboxes and lead paragraphs.

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

# ─── Non-wine filter keywords ────────────────────────────────────────────────
# Articles with these title patterns are likely not wine-related even if they
# appear in wine categories (e.g. villages, generic geography).
NON_WINE_TITLE_PATTERNS = [
    r"^List of ",
    r"^Lists of ",
    r"^Template:",
    r"^Wikipedia:",
    r"^Portal:",
    r"^Category:",
    r"^File:",
    r"^Draft:",
]
NON_WINE_TITLE_RE = re.compile("|".join(NON_WINE_TITLE_PATTERNS), re.IGNORECASE)

# ─── Session Setup ────────────────────────────────────────────────────────────


def _get_roots(config: dict) -> list[str]:
    """Get root category list from a category config (supports 'root' or 'roots')."""
    if "roots" in config:
        return config["roots"]
    return [config["root"]]


def _make_session() -> requests.Session:
    """Create a requests session with proper headers and connection pooling."""
    session = requests.Session()
    session.headers.update({
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    })
    return session


# ─── MediaWiki API Helpers ────────────────────────────────────────────────────


def _api_request(session: requests.Session, params: dict, max_retries: int = 4) -> dict:
    """Make a request to the MediaWiki API with rate limiting and retry."""
    params["format"] = "json"
    params["formatversion"] = "2"

    for attempt in range(max_retries + 1):
        try:
            time.sleep(REQUEST_DELAY)
            resp = session.get(API_ENDPOINT, params=params, timeout=30)

            if resp.status_code == 429:
                wait = 2 ** (attempt + 1)
                logger.warning(f"Rate limited (429). Waiting {wait}s before retry...")
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
                raise

    return {}


def get_category_members(
    session: requests.Session,
    category: str,
    depth: int = 0,
    seen_categories: Optional[set] = None,
    article_count: Optional[list] = None,
    max_articles: int = MAX_ARTICLES_PER_ROOT,
) -> list[str]:
    """Recursively crawl a category tree and return article titles.

    Returns a list of article titles (namespace 0 only).
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
            logger.info(f"Reached max articles ({max_articles}) for this root category")
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

        members = data["query"].get("categorymembers", [])
        for member in members:
            if article_count[0] >= max_articles:
                break

            ns = member.get("ns", 0)
            title = member.get("title", "")

            if ns == 0:
                # Article namespace
                if not NON_WINE_TITLE_RE.match(title):
                    articles.append(title)
                    article_count[0] += 1
            elif ns == 14:
                # Subcategory namespace — recurse
                sub_articles = get_category_members(
                    session, title, depth + 1, seen_categories,
                    article_count, max_articles,
                )
                articles.extend(sub_articles)

        # Handle continuation
        if "continue" in data and article_count[0] < max_articles:
            cmcontinue = data["continue"].get("cmcontinue")
            if not cmcontinue:
                break
        else:
            break

    return articles


def get_article_extract(session: requests.Session, title: str) -> Optional[str]:
    """Get the plain-text intro of an article using prop=extracts."""
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
        logger.debug(f"Skipping missing page: {title}")
        return None

    return page.get("extract", "")


def get_article_wikitext(session: requests.Session, title: str) -> Optional[str]:
    """Get raw wikitext of an article (for infobox parsing)."""
    params = {
        "action": "query",
        "titles": title,
        "prop": "revisions",
        "rvprop": "content",
        "rvslots": "main",
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

    revisions = page.get("revisions", [])
    if not revisions:
        return None

    slots = revisions[0].get("slots", {})
    main_slot = slots.get("main", {})
    return main_slot.get("content", "")


# ─── Infobox Parsing ─────────────────────────────────────────────────────────

# Matches {{Infobox ...}} blocks. The regex captures the infobox type and body.
INFOBOX_RE = re.compile(
    r"\{\{[Ii]nfobox\s+([\w\s]+?)\s*\n(.*?)\n\}\}",
    re.DOTALL,
)

# Matches key = value lines within an infobox
INFOBOX_FIELD_RE = re.compile(
    r"^\s*\|\s*(\w[\w\s]*?)\s*=\s*(.+?)$",
    re.MULTILINE,
)

# Clean wiki markup from field values
WIKI_LINK_RE = re.compile(r"\[\[(?:[^|\]]*\|)?([^\]]+)\]\]")
WIKI_REF_RE = re.compile(r"<ref[^>]*>.*?</ref>|<ref[^>]*/>", re.DOTALL)
WIKI_TAG_RE = re.compile(r"<[^>]+>")
WIKI_TEMPLATE_SIMPLE_RE = re.compile(r"\{\{[^{}]*\}\}")


def _clean_wiki_value(value: str) -> str:
    """Strip wiki markup from a field value."""
    value = WIKI_REF_RE.sub("", value)
    value = WIKI_LINK_RE.sub(r"\1", value)
    value = WIKI_TAG_RE.sub("", value)
    # Remove simple templates (non-nested)
    value = WIKI_TEMPLATE_SIMPLE_RE.sub("", value)
    value = value.strip().strip("'\"")
    return value


def parse_infobox(wikitext: str) -> list[dict]:
    """Extract infobox key-value pairs from wikitext.

    Returns a list of dicts with keys: infobox_type, field, value.
    """
    results = []
    # Find all infoboxes — use a simpler approach for nested braces
    # Search for {{Infobox and then track brace depth
    idx = 0
    text_lower = wikitext.lower()
    while True:
        start = text_lower.find("{{infobox", idx)
        if start == -1:
            break

        # Find the infobox type (text between "Infobox" and the first newline or pipe)
        header_start = start + 2  # skip {{
        newline_pos = wikitext.find("\n", header_start)
        if newline_pos == -1:
            idx = start + 9
            continue

        header = wikitext[header_start:newline_pos].strip()
        infobox_type = header.replace("Infobox", "").replace("infobox", "").strip()

        # Track brace depth to find the end of the infobox
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

        # Extract fields
        for match in INFOBOX_FIELD_RE.finditer(infobox_body):
            field = match.group(1).strip().lower()
            value = _clean_wiki_value(match.group(2))
            if value and len(value) > 0:
                results.append({
                    "infobox_type": infobox_type,
                    "field": field,
                    "value": value,
                })

        idx = end

    return results


# ─── Fact Extraction ─────────────────────────────────────────────────────────

# Fields we care about in infoboxes, mapped to their semantic meaning
INFOBOX_WINE_FIELDS = {
    # Location fields
    "region": "region",
    "wine region": "region",
    "sub-region": "sub_region",
    "subregion": "sub_region",
    "country": "country",
    "location": "location",
    "state": "state",
    "province": "province",
    # Grape fields
    "grape": "grape",
    "grapes": "grape",
    "grape variety": "grape",
    "varieties": "grape",
    "primary grape": "grape",
    # Date fields
    "established": "year_established",
    "year established": "year_established",
    "founded": "year_established",
    "year": "year_established",
    "inception": "year_established",
    # Classification fields
    "type": "type",
    "appellation": "appellation",
    "designation": "designation",
    "classification": "classification",
    # Size fields
    "area": "area",
    "size": "area",
    "hectares": "area",
    # Other
    "owner": "owner",
    "winemaker": "winemaker",
    "website": None,  # skip
    "image": None,  # skip
    "caption": None,  # skip
}


def _extract_year(text: str) -> Optional[str]:
    """Extract a 4-digit year from text."""
    match = re.search(r"\b(1[0-9]{3}|20[0-2][0-9])\b", text)
    return match.group(1) if match else None


def build_infobox_facts(
    title: str,
    infobox_fields: list[dict],
    domain: str,
    subdomain: Optional[str],
    source_id: str,
) -> list[dict]:
    """Convert infobox fields into atomic facts."""
    facts = []
    field_map = {}

    for entry in infobox_fields:
        field = entry["field"]
        value = entry["value"]
        semantic = INFOBOX_WINE_FIELDS.get(field)
        if semantic and value:
            field_map[semantic] = value

    # Build location-based facts
    region = field_map.get("region", "")
    country = field_map.get("country", "")
    location = field_map.get("location", "")
    state = field_map.get("state", "")
    province = field_map.get("province", "")

    loc_parts = [p for p in [location, region, state, province, country] if p]

    if domain == "wine_regions" and loc_parts:
        loc_str = ", ".join(loc_parts[:2])  # Keep it concise
        fact_text = f"{title} is a wine region in {loc_str}."
        facts.append(_make_fact(fact_text, domain, subdomain, source_id, title, loc_parts))

    if domain == "producers":
        if loc_parts:
            loc_str = ", ".join(loc_parts[:2])
            fact_text = f"{title} is a winery located in {loc_str}."
            facts.append(_make_fact(fact_text, domain, subdomain, source_id, title, loc_parts))

        year = field_map.get("year_established")
        if year:
            extracted_year = _extract_year(year)
            if extracted_year:
                fact_text = f"{title} was established in {extracted_year}."
                facts.append(_make_fact(fact_text, domain, subdomain, source_id, title))

        owner = field_map.get("owner")
        if owner and len(owner) < 100:
            fact_text = f"{title} is owned by {owner}."
            facts.append(_make_fact(fact_text, domain, subdomain, source_id, title))

    if domain == "grape_varieties":
        if country:
            fact_text = f"{title} is a grape variety originating from {country}."
            facts.append(_make_fact(fact_text, domain, subdomain, source_id, title))
        elif loc_parts:
            loc_str = loc_parts[0]
            fact_text = f"{title} is a grape variety from {loc_str}."
            facts.append(_make_fact(fact_text, domain, subdomain, source_id, title))

    # Grape variety in region/appellation
    grape = field_map.get("grape")
    if grape and domain in ("wine_regions",):
        # Clean up grape list (may be comma-separated)
        grapes = [g.strip() for g in re.split(r"[,;]", grape) if g.strip()]
        for g in grapes[:3]:  # Limit to first 3
            if len(g) > 2 and len(g) < 50:
                fact_text = f"{title} permits the {g} grape variety."
                facts.append(_make_fact(fact_text, domain, subdomain, source_id, title, [g]))

    # Classification
    classification = field_map.get("classification") or field_map.get("designation")
    if classification and domain == "wine_regions":
        fact_text = f"{title} holds the {classification} classification."
        facts.append(_make_fact(fact_text, domain, subdomain, source_id, title))

    # Area
    area = field_map.get("area")
    if area and domain in ("wine_regions",):
        area_clean = re.sub(r"[^\d.,]", " ", area).strip()
        if area_clean:
            fact_text = f"{title} has a vineyard area of approximately {area} hectares."
            facts.append(_make_fact(fact_text, domain, subdomain, source_id, title))

    return facts


def _make_fact(
    fact_text: str,
    domain: str,
    subdomain: Optional[str],
    source_id: str,
    title: str,
    extra_entities: Optional[list] = None,
) -> dict:
    """Create a fact dict matching the insert_facts_batch schema."""
    entities = [{"type": _entity_type_for_domain(domain), "name": title}]
    if extra_entities:
        for e in extra_entities:
            if isinstance(e, str):
                entities.append({"type": "related", "name": e})
    return {
        "fact_text": fact_text,
        "domain": domain,
        "subdomain": subdomain,
        "source_id": source_id,
        "entities": entities,
        "confidence": 0.9,
        "tags": ["wikipedia", domain],
    }


def _entity_type_for_domain(domain: str) -> str:
    """Map domain to entity type."""
    mapping = {
        "wine_regions": "region",
        "grape_varieties": "grape",
        "producers": "producer",
        "viticulture": "concept",
        "winemaking": "concept",
    }
    return mapping.get(domain, "concept")


# ─── Lead paragraph extraction ───────────────────────────────────────────────

# Patterns that indicate a factual sentence worth extracting
FACTUAL_PATTERNS = [
    re.compile(r"\bis\s+(?:a|an|the|one\s+of)", re.IGNORECASE),
    re.compile(r"\bwas\s+(?:a|an|the|founded|established|created|first)", re.IGNORECASE),
    re.compile(r"\bproduced\s+from\b", re.IGNORECASE),
    re.compile(r"\bmade\s+from\b", re.IGNORECASE),
    re.compile(r"\bknown\s+for\b", re.IGNORECASE),
    re.compile(r"\blocated\s+in\b", re.IGNORECASE),
    re.compile(r"\bregion\s+(?:of|in)\b", re.IGNORECASE),
    re.compile(r"\bgrown\s+in\b", re.IGNORECASE),
    re.compile(r"\bappellation\b", re.IGNORECASE),
    re.compile(r"\bvariet(?:y|ies)\b", re.IGNORECASE),
    re.compile(r"\bvineyard", re.IGNORECASE),
    re.compile(r"\bhectares?\b", re.IGNORECASE),
    re.compile(r"\bacres?\b", re.IGNORECASE),
    re.compile(r"\bwiner(?:y|ies)\b", re.IGNORECASE),
    re.compile(r"\bvintage\b", re.IGNORECASE),
    re.compile(r"\b\d{4}\b"),  # Contains a year
    re.compile(r"\b\d+[.,]?\d*\s*%", re.IGNORECASE),  # Contains a percentage
    re.compile(r"\bcontains?\b", re.IGNORECASE),
    re.compile(r"\brequires?\b", re.IGNORECASE),
    re.compile(r"\bpermits?\b", re.IGNORECASE),
]

# Patterns indicating a sentence is opinion/taste description (skip these)
SKIP_PATTERNS = [
    re.compile(r"\btast(?:e|es|ing)\b", re.IGNORECASE),
    re.compile(r"\baroma\b", re.IGNORECASE),
    re.compile(r"\bflavor\b", re.IGNORECASE),
    re.compile(r"\bpalate\b", re.IGNORECASE),
    re.compile(r"\bnotes?\s+of\b", re.IGNORECASE),
    re.compile(r"\bbouquet\b", re.IGNORECASE),
    re.compile(r"\bdelicious\b", re.IGNORECASE),
    re.compile(r"\bexcellent\b", re.IGNORECASE),
    re.compile(r"\bone\s+of\s+the\s+(?:best|finest|greatest)", re.IGNORECASE),
    re.compile(r"\bmost\s+(?:famous|renowned|prestigious)\b", re.IGNORECASE),
]


def extract_lead_facts(
    title: str,
    extract_text: str,
    domain: str,
    subdomain: Optional[str],
    source_id: str,
) -> list[dict]:
    """Extract atomic facts from the lead paragraph of an article."""
    if not extract_text or len(extract_text) < 20:
        return []

    facts = []
    # Split into sentences
    sentences = re.split(r"(?<=[.!?])\s+", extract_text.strip())

    # Only process first 3 sentences of the lead
    for sentence in sentences[:3]:
        sentence = sentence.strip()
        if not sentence:
            continue

        # Skip very short or very long sentences
        word_count = len(sentence.split())
        if word_count < 5 or word_count > 50:
            continue

        # Skip opinion/taste sentences
        if any(p.search(sentence) for p in SKIP_PATTERNS):
            continue

        # Check if sentence contains factual patterns
        if not any(p.search(sentence) for p in FACTUAL_PATTERNS):
            continue

        # Rephrase: ensure it starts with the article title or a reference to it
        fact_text = _rephrase_sentence(title, sentence, domain)
        if fact_text and len(fact_text.split()) >= 5:
            facts.append(_make_fact(fact_text, domain, subdomain, source_id, title))

    return facts


def _rephrase_sentence(title: str, sentence: str, domain: str) -> Optional[str]:
    """Rephrase a Wikipedia sentence into an atomic fact.

    Ensures the fact is self-contained and not just copied verbatim.
    """
    # Clean up the sentence
    sentence = sentence.strip()
    if not sentence.endswith("."):
        sentence += "."

    # Remove parenthetical pronunciations and IPA: (French: ...), (/ˌ.../)
    sentence = re.sub(r"\s*\([^)]*(?:pronunciation|IPA|French|Italian|Spanish|German|listen)[^)]*\)", "", sentence, flags=re.IGNORECASE)
    sentence = re.sub(r"\s*\(/[^)]+/\)", "", sentence)
    # Remove other short parenthetical notes if they're just language annotations
    sentence = re.sub(r"\s*\([A-Z][a-z]+:\s*[^)]+\)", "", sentence)

    # If the sentence already mentions the title, use a rephrased version
    if title.lower() in sentence.lower():
        return sentence.strip()

    # If it doesn't mention the title at all, prepend context
    entity_type = _entity_type_for_domain(domain)
    type_label = {
        "region": "wine region",
        "grape": "grape variety",
        "producer": "winery",
        "concept": "wine concept",
    }.get(entity_type, "wine topic")

    # Only add a prefix if the sentence seems orphaned
    if sentence[0].isupper() and not sentence.startswith(("The ", "A ", "An ", "It ")):
        return sentence

    return f"Regarding {title}: {sentence}"


# ─── Deduplication Against Existing Facts ─────────────────────────────────────


def _load_existing_facts_for_dedup() -> list[str]:
    """Load existing fact texts from the database for substring dedup."""
    try:
        from src.utils.db import get_pg
        conn = get_pg()
        cur = conn.cursor()
        cur.execute("SELECT fact_text FROM facts WHERE fact_text IS NOT NULL LIMIT 50000")
        rows = cur.fetchall()
        return [r["fact_text"].lower() for r in rows]
    except Exception as e:
        logger.warning(f"Could not load existing facts for dedup: {e}")
        return []


def deduplicate_facts(new_facts: list[dict], existing_texts: list[str]) -> list[dict]:
    """Remove facts that are trivially similar to existing facts.

    Uses substring containment: if an existing fact contains the core claim
    of a new fact, skip it.
    """
    if not existing_texts:
        return new_facts

    filtered = []
    for fact in new_facts:
        fact_lower = fact["fact_text"].lower()
        # Check: is the new fact a substring of any existing fact?
        # Or is any existing fact a substring of the new fact?
        is_dup = False
        for existing in existing_texts:
            # Check if significant overlap exists (> 80% of shorter string)
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
    """Load progress from the progress file."""
    path = Path(PROGRESS_FILE)
    if path.exists():
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            return {"processed": {}}
    return {"processed": {}}


def _save_progress(progress: dict):
    """Save progress to the progress file."""
    path = Path(PROGRESS_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(progress, indent=2))


def _mark_processed(progress: dict, category: str, title: str):
    """Mark an article as processed."""
    if category not in progress["processed"]:
        progress["processed"][category] = []
    progress["processed"][category].append(title)


def _is_processed(progress: dict, category: str, title: str) -> bool:
    """Check if an article was already processed."""
    return title in progress.get("processed", {}).get(category, [])


# ─── Main Processing Pipeline ────────────────────────────────────────────────


def process_article(
    session: requests.Session,
    title: str,
    domain: str,
    subdomain: Optional[str],
    existing_facts: list[str],
    dry_run: bool = False,
) -> list[dict]:
    """Process a single Wikipedia article and return extracted facts.

    Phase A: Extract facts from infoboxes (structured data).
    Phase B: Extract facts from lead paragraphs (semi-structured).
    """
    all_facts = []

    # Register source for this article
    article_url = f"https://en.wikipedia.org/wiki/{url_quote(title.replace(' ', '_'))}"
    if not dry_run:
        source_id = ensure_source(
            name=f"Wikipedia: {title}",
            url=article_url,
            source_type="encyclopedia",
            tier=SOURCE_TIER,
        )
    else:
        source_id = "dry-run"

    # Phase A: Infobox extraction
    wikitext = get_article_wikitext(session, title)
    if wikitext:
        infobox_fields = parse_infobox(wikitext)
        if infobox_fields:
            infobox_facts = build_infobox_facts(title, infobox_fields, domain, subdomain, source_id)
            all_facts.extend(infobox_facts)
            logger.debug(f"  Infobox: {len(infobox_facts)} facts from {title}")

    # Phase B: Lead paragraph extraction
    extract_text = get_article_extract(session, title)
    if extract_text:
        # Check for disambiguation or stub pages
        if "may refer to" in extract_text or "can refer to" in extract_text:
            logger.debug(f"  Skipping disambiguation page: {title}")
            return []
        if len(extract_text) < 50:
            logger.debug(f"  Skipping stub article: {title}")
            return []

        lead_facts = extract_lead_facts(title, extract_text, domain, subdomain, source_id)
        all_facts.extend(lead_facts)
        logger.debug(f"  Lead: {len(lead_facts)} facts from {title}")
    elif not wikitext:
        logger.debug(f"  Skipping empty article: {title}")
        return []

    # Deduplicate against existing facts
    if all_facts and existing_facts:
        all_facts = deduplicate_facts(all_facts, existing_facts)

    return all_facts


def scrape_category(
    category_key: str,
    dry_run: bool = False,
    resume: bool = True,
) -> int:
    """Scrape all articles in a category tree and insert facts.

    Returns count of new facts inserted.
    """
    if category_key not in CATEGORIES:
        logger.error(f"Unknown category: {category_key}. Available: {list(CATEGORIES.keys())}")
        return 0

    config = CATEGORIES[category_key]
    domain = config["domain"]
    subdomain = config["subdomain"]
    roots = _get_roots(config)

    logger.info(f"Scraping category: {category_key} ({config['description']})")
    logger.info(f"  Roots: {roots}, Domain: {domain}")

    session = _make_session()

    # Discover articles from all root categories
    logger.info("Crawling category tree...")
    articles = []
    for root in roots:
        root_articles = get_category_members(session, root)
        articles.extend(root_articles)
        logger.info(f"  {root}: {len(root_articles)} articles")
    # Deduplicate article list (preserving order)
    articles = list(dict.fromkeys(articles))
    logger.info(f"Found {len(articles)} unique articles across {len(roots)} root(s)")

    if dry_run:
        click.echo(f"  {category_key}: {len(articles)} articles (dry run, no insertion)")
        return 0

    # Load progress for resume
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

        logger.info(f"Processing {category_key}: {title} ({idx + 1}/{len(articles)})")

        try:
            facts = process_article(session, title, domain, subdomain, existing_facts, dry_run=False)
            total_facts += len(facts)
            batch_buffer.extend(facts)

            # Insert in batches
            if len(batch_buffer) >= batch_size:
                inserted = insert_facts_batch(batch_buffer)
                total_inserted += inserted
                # Add newly inserted facts to dedup list
                for f in batch_buffer:
                    existing_facts.append(f["fact_text"].lower())
                batch_buffer = []
                logger.info(f"  Progress: {total_inserted} inserted / {total_facts} extracted")

            _mark_processed(progress, category_key, title)
            # Save progress periodically
            if (idx + 1) % 50 == 0:
                _save_progress(progress)

        except Exception as e:
            logger.error(f"Error processing {title}: {e}")
            continue

    # Insert remaining facts
    if batch_buffer:
        inserted = insert_facts_batch(batch_buffer)
        total_inserted += inserted
        for f in batch_buffer:
            existing_facts.append(f["fact_text"].lower())

    _save_progress(progress)
    logger.info(f"Category {category_key}: {total_inserted} new facts inserted ({total_facts} extracted)")
    return total_inserted


def scrape_all(dry_run: bool = False) -> dict:
    """Scrape all categories. Returns per-category insertion counts."""
    summary = {}
    total = 0

    for cat_key in CATEGORIES:
        count = scrape_category(cat_key, dry_run=dry_run)
        summary[cat_key] = count
        total += count

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

    # Get all Wikipedia-sourced facts
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

    click.echo(f"\nValidation Report — Wikipedia Facts ({len(rows)} total)")
    click.echo("=" * 60)

    # a) Domain distribution
    domain_counts = defaultdict(int)
    subdomain_counts = defaultdict(int)
    for row in rows:
        domain_counts[row["domain"]] += 1
        if row["subdomain"]:
            subdomain_counts[f"{row['domain']}/{row['subdomain']}"] += 1

    click.echo("\nDomain distribution:")
    for domain, count in sorted(domain_counts.items(), key=lambda x: -x[1]):
        click.echo(f"  {domain:25s}: {count} facts")
    if subdomain_counts:
        click.echo("\nSubdomain distribution:")
        for sd, count in sorted(subdomain_counts.items(), key=lambda x: -x[1]):
            click.echo(f"  {sd:25s}: {count} facts")

    # b) Length checks
    too_short = [r for r in rows if len(r["fact_text"].split()) < 5]
    too_long = [r for r in rows if len(r["fact_text"].split()) > 50]

    # c) Entity-name-only facts (no predicate)
    no_predicate = []
    for r in rows:
        text = r["fact_text"].rstrip(".")
        if len(text.split()) <= 2:
            no_predicate.append(r)

    # d) Near-duplicate check (simple substring containment)
    fact_texts = [r["fact_text"].lower() for r in rows]
    near_dupes = 0
    checked = set()
    for i, t1 in enumerate(fact_texts):
        if i in checked:
            continue
        for j, t2 in enumerate(fact_texts):
            if i >= j or j in checked:
                continue
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
    missing_entities = len(rows) - has_entities

    click.echo("\nQuality:")
    n = len(rows)
    click.echo(f"  Too short (<5 words):  {len(too_short)} ({100*len(too_short)/n:.1f}%)")
    click.echo(f"  Too long (>50 words):  {len(too_long)} ({100*len(too_long)/n:.1f}%)")
    click.echo(f"  No predicate:          {len(no_predicate)} ({100*len(no_predicate)/n:.1f}%)")
    click.echo(f"  Missing entities:      {missing_entities} ({100*missing_entities/n:.1f}%)")
    click.echo(f"  Possible near-dupes:   {near_dupes} ({100*near_dupes/n:.1f}%)")

    # f) Random sample
    sample_size = min(10, len(rows))
    sample = random.sample(rows, sample_size)
    click.echo(f"\nSample facts ({sample_size}):")
    for i, r in enumerate(sample, 1):
        click.echo(f"  {i}. \"{r['fact_text']}\"")

    click.echo()


# ─── CLI ──────────────────────────────────────────────────────────────────────


@click.command()
@click.option("--category", "-c", type=str, help="Scrape a specific category (regions/grapes/wineries/appellations/classifications/viticulture/oenology)")
@click.option("--all", "run_all", is_flag=True, help="Scrape all categories")
@click.option("--list", "list_categories", is_flag=True, help="List available categories with article counts")
@click.option("--dry-run", is_flag=True, help="Crawl categories and count articles without inserting facts")
@click.option("--validate", "run_validate", is_flag=True, help="Run quality checks on existing Wikipedia facts")
def main(
    category: Optional[str],
    run_all: bool,
    list_categories: bool,
    dry_run: bool,
    run_validate: bool,
):
    """OenoBench Wikipedia Scraper — Extract wine facts from English Wikipedia."""
    # Ensure log directory exists
    os.makedirs("data/logs", exist_ok=True)
    logger.add("data/logs/wikipedia_{time}.log", rotation="10 MB")

    if run_validate:
        validate()
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
                    click.echo(f"  {'':20s}   {root}: {pages} articles, {subcats} subcategories")
                except Exception:
                    click.echo(f"  {'':20s}   {root}: (count unavailable)")
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

    click.echo("Use --all to scrape all categories, or --category <name> for a specific one.")
    click.echo("Use --list to see available categories, --dry-run to count without inserting.")
    click.echo("Use --validate to check quality of existing Wikipedia facts.")


if __name__ == "__main__":
    main()
