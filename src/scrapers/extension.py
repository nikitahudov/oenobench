"""
OenoBench — US University Extension Services Scraper

Extracts viticulture and winemaking facts from university extension
programs that provide research-based agricultural guidance.

Sources:
  - eXtension Grapes hub (USDA)
  - Penn State Extension — Wine & Grapes
  - Oregon State Extension — Wine Grapes

Usage:
    python -m src.scrapers.extension --all
    python -m src.scrapers.extension --source extension
    python -m src.scrapers.extension --source psu
    python -m src.scrapers.extension --source osu
    python -m src.scrapers.extension --dry-run
    python -m src.scrapers.extension --validate
    python -m src.scrapers.extension --list
    python -m src.scrapers.extension --test-run
    python -m src.scrapers.extension --test-run --cleanup
"""

import random
import re
import time
from collections import defaultdict
from datetime import datetime
from typing import Optional
from urllib.parse import urljoin, urlparse

import click
import requests
from bs4 import BeautifulSoup, NavigableString, Comment
from loguru import logger

from src.utils.facts import (
    ensure_source,
    insert_facts_batch,
    insert_facts_batch_tracked,
    delete_facts_by_ids,
    get_fact_count,
)

# ─── Configuration ────────────────────────────────────────────────────────────

USER_AGENT = "OenoBench-Research/1.0 (academic wine benchmark)"
REQUEST_DELAY = 3.0  # 3 seconds between requests per domain
REQUEST_TIMEOUT = 30
DEFAULT_CONFIDENCE = 0.90

SOURCES = {
    "extension": {
        "name": "eXtension — USDA Grape Community",
        "url": "https://grapes.extension.org/",
        "source_type": "government_extension",
        "tier": "tier_2_authoritative",
        "language": "en",
        "index_url": "https://grapes.extension.org/",
    },
    "psu": {
        "name": "Penn State Extension — Wine & Grapes",
        "url": "https://extension.psu.edu/food-safety-and-quality/grape-and-wine-production",
        "source_type": "government_extension",
        "tier": "tier_2_authoritative",
        "language": "en",
        "index_url": "https://extension.psu.edu/food-safety-and-quality/grape-and-wine-production",
    },
    "osu": {
        "name": "Oregon State Extension — Wine Grapes",
        "url": "https://extension.oregonstate.edu/crop-production/wine-grapes",
        "source_type": "government_extension",
        "tier": "tier_2_authoritative",
        "language": "en",
        "index_url": "https://extension.oregonstate.edu/crop-production/wine-grapes",
    },
}

SOURCE_KEYS = list(SOURCES.keys())

# ─── HTTP Helpers ─────────────────────────────────────────────────────────────

_last_request_per_domain: dict[str, float] = {}


def _get_domain(url: str) -> str:
    """Extract domain from URL for rate limiting."""
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
            if resp.status_code == 404:
                logger.warning(f"404 Not Found: {url}")
                return None
            resp.raise_for_status()
            return resp.text
        except requests.RequestException as e:
            logger.warning(f"Fetch attempt {attempt + 1}/{retries} failed for {url}: {e}")
            if attempt < retries - 1:
                time.sleep(2 ** (attempt + 1))
    logger.error(f"Failed to fetch {url} after {retries} attempts")
    return None


# ─── Content Extraction ──────────────────────────────────────────────────────

# Tags that hold navigation / boilerplate (strip them before extracting text)
STRIP_TAGS = {"nav", "header", "footer", "aside", "script", "style", "noscript", "form"}

# CSS selectors for main content area, tried in order
MAIN_CONTENT_SELECTORS = [
    "article",
    "main",
    "[role='main']",
    ".field--name-body",
    ".article-content",
    ".content-area",
    ".main-content",
    "#main-content",
    "#content",
    ".entry-content",
    ".post-content",
    ".node__content",
    "div.content",
]


def extract_main_text(html: str) -> str:
    """Extract the main article text from an HTML page, stripping nav/sidebar/footer."""
    soup = BeautifulSoup(html, "html.parser")

    # Remove comments
    for comment in soup.find_all(string=lambda t: isinstance(t, Comment)):
        comment.extract()

    # Remove boilerplate tags
    for tag_name in STRIP_TAGS:
        for tag in soup.find_all(tag_name):
            tag.decompose()

    # Remove sidebar/related-content blocks by CSS class/id patterns
    _JUNK_SELECTORS = [
        ".sidebar", ".related-content", ".related-articles", ".related-links",
        ".share-links", ".social-share", ".author-info", ".author-bio",
        ".byline", ".article-meta", ".article-footer", ".field--name-field-author",
        ".field--name-field-date", ".field--name-field-tags",
        ".views-row", ".view-content", ".pager", ".pagination",
        ".breadcrumb", ".block-menu", ".block-facet",
        "[role='complementary']", "[role='navigation']",
    ]
    for sel in _JUNK_SELECTORS:
        for el in soup.select(sel):
            el.decompose()

    # Try to find the main content container
    content_el = None
    for selector in MAIN_CONTENT_SELECTORS:
        content_el = soup.select_one(selector)
        if content_el:
            break

    if content_el is None:
        # Fallback: use <body>
        content_el = soup.find("body")
    if content_el is None:
        content_el = soup

    # Get text, collapse whitespace
    text = content_el.get_text(separator=" ", strip=True)
    # Normalize whitespace
    text = re.sub(r"\s+", " ", text).strip()

    # Strip author/date bylines  ("Name | Date | Source ..." or "Name | Mon YYYY | ...")
    text = re.sub(
        r"[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\s*\|\s*"
        r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\w*\s+\d{4}\s*\|[^.]*(?:\.\s*|$)",
        " ", text
    )
    # Strip "Credit: ..." photo attributions (up to next sentence boundary)
    text = re.sub(r"Credit\s*:\s*[^.]*\.?\s*", " ", text, flags=re.IGNORECASE)
    # Strip "Length X hours/minutes" metadata
    text = re.sub(r"Length\s+\d+\s*(?:hours?|minutes?|hrs?|mins?)\b[^.]*\.?\s*", " ", text, flags=re.IGNORECASE)
    # Strip section headers that are just category labels
    text = re.sub(r"\b(?:Workshops?|Webinars?|Articles?|Videos?|Events?|Resources?)\s+(?:Workshops?|Webinars?|Articles?|Videos?|Events?|Resources?|\|)\s*", " ", text, flags=re.IGNORECASE)
    # Strip standalone section headers (word at boundary followed by nothing useful)
    text = re.sub(r"(?<=[.!?])\s+(?:Workshops?|Webinars?|Videos?|Events?)(?:\s+|$)(?=[A-Z]|$)", " ", text, flags=re.IGNORECASE)
    # Strip "Learn how to ..." promotional sentences
    text = re.sub(r"Learn\s+how\s+to\b[^.]*\.?\s*", " ", text, flags=re.IGNORECASE)
    # Strip "Impact story" labels
    text = re.sub(r"Impact\s+stor(?:y|ies)\b[^.]*\.?\s*", " ", text, flags=re.IGNORECASE)

    # Final whitespace cleanup
    text = re.sub(r"\s+", " ", text).strip()
    return text


def extract_article_links(html: str, base_url: str, same_domain_only: bool = True) -> list[str]:
    """Extract article/guide links from an index page.

    Returns deduplicated list of absolute URLs that look like article pages
    (not images, PDFs, anchors, or mailto links).
    """
    soup = BeautifulSoup(html, "html.parser")
    base_domain = _get_domain(base_url)
    seen: set[str] = set()
    links: list[str] = []

    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"].strip()

        # Skip anchors, mailto, tel, javascript
        if href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        # Skip common non-article extensions
        if re.search(r"\.(pdf|jpg|jpeg|png|gif|svg|zip|doc|docx|xls|xlsx|ppt|pptx)$", href, re.I):
            continue

        abs_url = urljoin(base_url, href)
        # Strip fragment
        abs_url = abs_url.split("#")[0]

        if same_domain_only and _get_domain(abs_url) != base_domain:
            continue

        if abs_url in seen:
            continue
        seen.add(abs_url)

        # Heuristic: only keep URLs that look like article paths (have a path component)
        parsed = urlparse(abs_url)
        if parsed.path and parsed.path != "/" and len(parsed.path) > 5:
            links.append(abs_url)

    return links


# ─── Sentence Splitting & Fact Filtering ─────────────────────────────────────

# Regex to split text into sentences (handles abbreviations reasonably)
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z])")

# Keywords that signal factual content about viticulture or winemaking
_FACTUAL_INDICATORS = re.compile(
    r"""
    \b(?:
        # Numbers and measurements
        \d+\s*(?:%|percent|degrees?|°|ppm|mg/[Ll]|g/[Ll]|lbs?|gallons?|acres?|hectares?|ha\b|tons?|bushels?)
        |pH\s*\d
        |\d+\s*(?:days?|weeks?|months?|years?|hours?)
        # Chemical / scientific terms
        |Brix
        |sulfur\s*dioxide|SO2|sulfite|tartaric|malic|citric|acetic|lactic
        |nitrogen|potassium|phosphorus|calcium|magnesium|boron|zinc|iron
        |anthocyanin|tannin|phenol|polyphenol|flavonoid|resveratrol
        |ethanol|alcohol|ferment
        |Saccharomyces|Brettanomyces|Botrytis|Vitis\s+vinifera|Vitis\s+labrusca
        |phylloxera|powdery\s+mildew|downy\s+mildew|black\s+rot|Pierce.s\s+disease
        |Eutypa|Botryosphaeria|trunk\s+disease
        # Grape varieties
        |Cabernet\s+Sauvignon|Merlot|Pinot\s+Noir|Chardonnay|Riesling
        |Sauvignon\s+Blanc|Syrah|Shiraz|Zinfandel|Grenache|Tempranillo
        |Sangiovese|Nebbiolo|Malbec|Viognier|Gewurztraminer
        |Pinot\s+Gris|Pinot\s+Grigio|Semillon|Muscat|Moscato
        |Concord|Niagara|Chambourcin|Vidal\s+Blanc|Seyval\s+Blanc
        |Traminette|Cayuga\s+White|Norton|Catawba
        # Viticulture practices
        |rootstock|grafting|canopy\s+management|shoot\s+thinning
        |cluster\s+thinning|leaf\s+removal|veraison|budbreak|dormancy
        |pruning|trellising|VSP|Geneva\s+Double\s+Curtain|Scott\s+Henry
        |irrigation|drip\s+irrigation|deficit\s+irrigation
        |cover\s+crop|mulch|compost|fertil
        |harvest|yield|vigor|vine\s+spacing|row\s+spacing
        # Winemaking
        |maceration|cold\s+soak|malolactic|barrel\s+aging|oak
        |fining|racking|filtering|filtration|clarification
        |chaptaliz|amelioration|deacidification|acidification
        |yeast|inocul|must|crush|press|destem
        |free\s+run|cap\s+management|punchdown|pump.?over
        |bottling|corking|closure
        |residual\s+sugar|titratable\s+acidity|volatile\s+acidity
        # Pest & disease management
        |fungicide|insecticide|pesticide|herbicide|spray
        |integrated\s+pest\s+management|IPM
        |Japanese\s+beetle|grape\s+berry\s+moth|spotted\s+lanternfly
        |bird\s+netting|deer\s+fencing
    )\b
    """,
    re.VERBOSE | re.IGNORECASE,
)

# Keywords that signal wine/grape content on a page
_WINE_CONTENT_TERMS = re.compile(
    r"\b(?:wine|grape|vineyard|viticulture|enology|oenology|winemaking|vine\b|grapevine"
    r"|varietal|vintage|appellation|terroir|sommelier|vintner"
    r"|Cabernet|Merlot|Pinot|Chardonnay|Riesling|Sauvignon|Syrah|Shiraz|Zinfandel"
    r"|Chambourcin|Traminette|Concord|Niagara|Vidal|Seyval|Norton|Catawba"
    r"|Vitis\s+vinifera|Vitis\s+labrusca"
    r"|trellis|rootstock|veraison|budbreak|canopy|pruning"
    r"|ferment|maceration|malolactic|barrel\s+aging|fining|racking"
    r"|powdery\s+mildew|downy\s+mildew|black\s+rot|Botrytis|phylloxera|Pierce.s\s+disease"
    r"|must\b|crush\b|Brix|titratable\s+acidity|residual\s+sugar"
    r")\b",
    re.IGNORECASE,
)

# Terms that indicate non-wine agricultural content
_NON_WINE_TERMS = re.compile(
    r"\b(?:dairy|swine|poultry|cattle|livestock|hog|pig|chicken|turkey|sheep|goat"
    r"|corn\s+silage|soybean|wheat\s+crop|hay\b|alfalfa|pasture\s+management"
    r"|beef|pork|milk\s+production|calf|heifer|bull\b|steer"
    r"|egg\s+production|broiler|layer\s+hen"
    r")\b",
    re.IGNORECASE,
)

# Patterns for generic/non-factual sentences to skip
_SKIP_PATTERNS = re.compile(
    r"""^(?:
        Welcome\s+to
        |This\s+(?:guide|article|page|section|resource)\s+(?:covers?|provides?|describes?|explains?|discusses?)
        |(?:Click|Tap|Visit|See|Read|Learn|Find|Explore|Browse|Subscribe|Sign\s+up|Register|Log\s+in|Contact)
        |For\s+more\s+information
        |Table\s+of\s+contents
        |Share\s+this
        |Print\s+this
        |Download\s+(?:the|this|our)
        |Copyright|All\s+rights\s+reserved
        |Last\s+(?:updated|modified|reviewed)
        |Published\s+(?:on|by)
        |\d{1,2}/\d{1,2}/\d{2,4}
        |Photo\s+(?:by|credit|courtesy)
        |Image\s+(?:by|credit|courtesy)
        |Figure\s+\d
        |Table\s+\d
    )""",
    re.VERBOSE | re.IGNORECASE,
)

# Additional patterns to skip: metadata, UI text, bylines, non-wine content
_SKIP_CONTENT_PATTERNS = re.compile(
    r"""(?:
        \bworkshops?\b
        |\bwebinars?\b
        |\bcredit\s*:
        |\bcropped\s+from\s+original\b
        |\blearn\s+how\b
        |\blength\s+\d+\s*(?:hours?|minutes?|hrs?|mins?)
        |\bimpact\s+story\b
        |\bsign\s+up\s+for\b
        |\bregister\s+(?:for|now|today)\b
        |\bjoin\s+us\b
        |\bfiled\s+under\b
        |\btags?\s*:\b
        |\bcategory\s*:\b
        |\bshare\s+(?:on|via|this)\b
        |\bfollow\s+us\b
        |\bnewsletter\b
    )""",
    re.VERBOSE | re.IGNORECASE,
)

# Byline pattern: "Name Name | Date | Source" or similar
_BYLINE_PATTERN = re.compile(
    r"[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\s*\|",
)

# Require at least one wine/grape/viticulture term in the sentence
_WINE_SENTENCE_TERMS = re.compile(
    r"\b(?:wine|grape|vineyard|viticulture|enology|oenology|winemaking|vine\b|grapevine"
    r"|varietal|vintage|appellation|terroir|vintner"
    r"|trellis|rootstock|veraison|budbreak|canopy|pruning|harvest"
    r"|ferment|maceration|malolactic|barrel|fining|racking|bottling"
    r"|must\b|crush\b|Brix|pH|sulfite|SO2|tannin|phenol|anthocyanin"
    r"|mildew|rot\b|Botrytis|phylloxera|Pierce|fungicide|spray"
    r"|Cabernet|Merlot|Pinot|Chardonnay|Riesling|Sauvignon|Syrah|Shiraz|Zinfandel"
    r"|Chambourcin|Traminette|Concord|Niagara|Vidal|Seyval|Norton"
    r"|Vitis|rootstock|grafting|irrigation|vigor|yield"
    r"|yeast|Saccharomyces|Brettanomyces|inocul"
    r"|spotted\s+lanternfly|Japanese\s+beetle|grape\s+berry\s+moth"
    r")\b",
    re.IGNORECASE,
)

# Minimum word count for a viable fact
MIN_WORDS = 5
# Maximum word count — longer sentences should be split or skipped
MAX_WORDS = 50


def split_into_sentences(text: str) -> list[str]:
    """Split text into sentences, handling common abbreviations."""
    # Pre-process: protect common abbreviations
    protected = text
    for abbr in ["Dr.", "Mr.", "Mrs.", "Ms.", "Prof.", "Jr.", "Sr.", "vs.",
                  "etc.", "e.g.", "i.e.", "Fig.", "No.", "Vol.",
                  "U.S.", "U.K.", "St."]:
        protected = protected.replace(abbr, abbr.replace(".", "\x00"))

    sentences = _SENTENCE_SPLIT.split(protected)
    # Restore periods
    return [s.replace("\x00", ".").strip() for s in sentences if s.strip()]


def is_factual_sentence(sentence: str) -> bool:
    """Return True if the sentence contains factual wine/grape content markers."""
    # Must have enough words
    word_count = len(sentence.split())
    if word_count < MIN_WORDS:
        return False
    if word_count > MAX_WORDS:
        return False

    # Must not be a generic/boilerplate sentence
    if _SKIP_PATTERNS.match(sentence):
        return False

    # Must not contain metadata/UI/byline patterns
    if _SKIP_CONTENT_PATTERNS.search(sentence):
        return False

    # Must not be a byline ("Name Name | ...")
    if _BYLINE_PATTERN.search(sentence):
        return False

    # Must not be about non-wine agricultural topics
    if _NON_WINE_TERMS.search(sentence):
        return False

    # Must contain at least one factual indicator AND a wine-related term
    if _FACTUAL_INDICATORS.search(sentence) and _WINE_SENTENCE_TERMS.search(sentence):
        return True

    return False


# ─── Domain Classification ───────────────────────────────────────────────────

_WINEMAKING_KEYWORDS = re.compile(
    r"\b(?:"
    r"ferment|winemaking|wine\s+making|cellar|barrel|oak|fining|racking|filtration|filtering"
    r"|maceration|cold\s+soak|malolactic|chaptaliz|amelioration|yeast|inocul"
    r"|must|crush|press|destem|free\s+run|cap\s+management|punchdown|pump.?over"
    r"|bottling|corking|closure|SO2|sulfite|sulfur\s+dioxide"
    r"|residual\s+sugar|titratable\s+acidity|volatile\s+acidity"
    r"|deacidification|acidification|clarification|Brix|pH\s*\d"
    r"|ethanol|alcohol\s+content|enolog"
    r")\b",
    re.IGNORECASE,
)

_VITICULTURE_KEYWORDS = re.compile(
    r"\b(?:"
    r"viticult|vineyard|vine\b|grapevine|rootstock|grafting|canopy"
    r"|shoot\s+thinning|cluster\s+thinning|leaf\s+removal|veraison|budbreak|dormancy"
    r"|pruning|trellising|VSP|irrigation|drip\s+irrigation|deficit\s+irrigation"
    r"|cover\s+crop|mulch|compost|fertil|harvest|yield|vigor"
    r"|vine\s+spacing|row\s+spacing|planting|soil|site\s+selection"
    r"|pest|disease|fungicide|insecticide|spray|IPM|mildew|rot\b|phylloxera"
    r"|bird\s+netting|deer|frost\s+protection|freeze|winter\s+injury"
    r"|spotted\s+lanternfly|Japanese\s+beetle|grape\s+berry\s+moth"
    r"|trunk\s+disease|Pierce.s\s+disease|Botrytis|black\s+rot"
    r"|powdery\s+mildew|downy\s+mildew"
    r")\b",
    re.IGNORECASE,
)

# Subdomain classification heuristics
_SUBDOMAIN_PATTERNS = {
    "pest_disease_management": re.compile(
        r"\b(?:pest|disease|fungicide|insecticide|spray|IPM|mildew|rot\b|phylloxera"
        r"|spotted\s+lanternfly|Japanese\s+beetle|grape\s+berry\s+moth"
        r"|trunk\s+disease|Pierce.s\s+disease|Botrytis|black\s+rot"
        r"|powdery\s+mildew|downy\s+mildew|Eutypa|Botryosphaeria)\b", re.I
    ),
    "canopy_management": re.compile(
        r"\b(?:canopy|shoot\s+thinning|cluster\s+thinning|leaf\s+removal"
        r"|trellising|VSP|Geneva\s+Double\s+Curtain|Scott\s+Henry"
        r"|hedging|tucking|training\s+system)\b", re.I
    ),
    "soil_nutrition": re.compile(
        r"\b(?:soil|nitrogen|potassium|phosphorus|calcium|magnesium|boron|zinc|iron"
        r"|fertil|nutrient|pH\s*\d|compost|amendment|lime|gypsum)\b", re.I
    ),
    "fermentation": re.compile(
        r"\b(?:ferment|yeast|inocul|Saccharomyces|Brettanomyces"
        r"|malolactic|must|sugar|Brix)\b", re.I
    ),
    "wine_chemistry": re.compile(
        r"\b(?:SO2|sulfite|sulfur\s+dioxide|titratable\s+acidity|volatile\s+acidity"
        r"|pH|tartaric|malic|citric|acetic|lactic|anthocyanin|tannin|phenol"
        r"|polyphenol|flavonoid|resveratrol|ethanol)\b", re.I
    ),
    "cellar_operations": re.compile(
        r"\b(?:barrel|oak|fining|racking|filtration|filtering|clarification"
        r"|maceration|cold\s+soak|bottling|corking|closure|aging|ageing"
        r"|cap\s+management|punchdown|pump.?over|press)\b", re.I
    ),
    "grape_varieties": re.compile(
        r"\b(?:Cabernet\s+Sauvignon|Merlot|Pinot\s+Noir|Chardonnay|Riesling"
        r"|Sauvignon\s+Blanc|Syrah|Zinfandel|Chambourcin|Vidal\s+Blanc"
        r"|Seyval\s+Blanc|Traminette|Cayuga\s+White|Norton|Concord|Niagara"
        r"|Catawba|Vitis\s+vinifera|Vitis\s+labrusca|hybrid|cultivar|variet)\b", re.I
    ),
    "site_selection_planting": re.compile(
        r"\b(?:site\s+selection|planting|row\s+spacing|vine\s+spacing"
        r"|rootstock|grafting|aspect|elevation|slope|drainage)\b", re.I
    ),
    "irrigation_water": re.compile(
        r"\b(?:irrigation|drip|deficit\s+irrigation|water\s+management"
        r"|water\s+stress|evapotranspiration)\b", re.I
    ),
    "harvest_ripeness": re.compile(
        r"\b(?:harvest|ripen|maturity|veraison|Brix|sugar\s+content"
        r"|acid\s+balance|pick\s+date)\b", re.I
    ),
}


def classify_domain(sentence: str) -> str:
    """Classify a sentence as 'viticulture' or 'winemaking'."""
    wm_score = len(_WINEMAKING_KEYWORDS.findall(sentence))
    vt_score = len(_VITICULTURE_KEYWORDS.findall(sentence))

    if wm_score > vt_score:
        return "winemaking"
    # Default to viticulture (extension services lean toward growing)
    return "viticulture"


def classify_subdomain(sentence: str, domain: str) -> str:
    """Classify into a subdomain based on keyword matching."""
    best_subdomain = None
    best_count = 0
    for subdomain, pattern in _SUBDOMAIN_PATTERNS.items():
        matches = pattern.findall(sentence)
        if len(matches) > best_count:
            best_count = len(matches)
            best_subdomain = subdomain

    if best_subdomain:
        return best_subdomain

    # Fallback subdomains
    if domain == "winemaking":
        return "winemaking_general"
    return "viticulture_general"


# ─── Entity Extraction ───────────────────────────────────────────────────────

_GRAPE_VARIETY_PATTERN = re.compile(
    r"\b("
    r"Cabernet\s+Sauvignon|Merlot|Pinot\s+Noir|Chardonnay|Riesling"
    r"|Sauvignon\s+Blanc|Syrah|Shiraz|Zinfandel|Grenache|Tempranillo"
    r"|Sangiovese|Nebbiolo|Malbec|Viognier|Gewurztraminer"
    r"|Pinot\s+Gris|Pinot\s+Grigio|Semillon|Muscat|Moscato"
    r"|Concord|Niagara|Chambourcin|Vidal\s+Blanc|Seyval\s+Blanc"
    r"|Traminette|Cayuga\s+White|Norton|Catawba|Cabernet\s+Franc"
    r"|Petit\s+Verdot|Mourvedre|Petite\s+Sirah|Barbera|Dolcetto"
    r"|Gruner\s+Veltliner|Albarino|Vermentino|Marsanne|Roussanne"
    r"|Chenin\s+Blanc|Gamay|Lemberger|Blaufrankisch"
    r")\b",
    re.IGNORECASE,
)

_PEST_DISEASE_PATTERN = re.compile(
    r"\b("
    r"powdery\s+mildew|downy\s+mildew|black\s+rot|Botrytis|bunch\s+rot"
    r"|Pierce.s\s+disease|phylloxera|crown\s+gall|Eutypa\s+dieback"
    r"|Botryosphaeria|trunk\s+disease|anthracnose"
    r"|spotted\s+lanternfly|Japanese\s+beetle|grape\s+berry\s+moth"
    r"|grape\s+leafhopper|grape\s+flea\s+beetle|rose\s+chafer"
    r"|Erysiphe\s+necator|Plasmopara\s+viticola|Guignardia\s+bidwellii"
    r")\b",
    re.IGNORECASE,
)

_CHEMICAL_PATTERN = re.compile(
    r"\b("
    r"sulfur\s+dioxide|SO2|tartaric\s+acid|malic\s+acid|citric\s+acid"
    r"|acetic\s+acid|lactic\s+acid|nitrogen|potassium|phosphorus"
    r"|calcium|magnesium|boron|zinc|iron|anthocyanin|tannin"
    r"|phenol|polyphenol|resveratrol|ethanol"
    r")\b",
    re.IGNORECASE,
)

_TECHNIQUE_PATTERN = re.compile(
    r"\b("
    r"VSP|Geneva\s+Double\s+Curtain|Scott\s+Henry|Smart-Dyson"
    r"|lyre\s+trellis|bilateral\s+cordon|cane\s+pruning|spur\s+pruning"
    r"|drip\s+irrigation|deficit\s+irrigation|cover\s+crop"
    r"|integrated\s+pest\s+management|IPM"
    r"|cold\s+soak|malolactic\s+fermentation|barrel\s+aging"
    r"|sur\s+lie|batonnage|carbonic\s+maceration"
    r")\b",
    re.IGNORECASE,
)


def extract_entities(sentence: str) -> list[dict]:
    """Extract named entities from a sentence."""
    entities: list[dict] = []
    seen: set[str] = set()

    for pattern, entity_type in [
        (_GRAPE_VARIETY_PATTERN, "grape"),
        (_PEST_DISEASE_PATTERN, "pest_disease"),
        (_CHEMICAL_PATTERN, "chemical"),
        (_TECHNIQUE_PATTERN, "technique"),
    ]:
        for match in pattern.finditer(sentence):
            name = match.group(0).strip()
            key = name.lower()
            if key not in seen:
                seen.add(key)
                entities.append({"type": entity_type, "name": name})

    return entities


# ─── Source-Specific Link Filtering ──────────────────────────────────────────

def _is_article_link_extension_org(url: str) -> bool:
    """Filter links for grapes.extension.org — keep article-like paths."""
    parsed = urlparse(url)
    path = parsed.path.lower()
    # Keep pages that look like articles (not just category listings)
    if any(skip in path for skip in ["/tag/", "/category/", "/author/", "/page/",
                                      "/feed/", "/wp-content/", "/wp-admin/",
                                      "/login", "/register", "/search"]):
        return False
    return True


def _is_article_link_psu(url: str) -> bool:
    """Filter links for extension.psu.edu — keep only wine/grape article pages."""
    parsed = urlparse(url)
    path = parsed.path.lower()
    if any(skip in path for skip in ["/search", "/login", "/user/", "/admin/",
                                      "/sites/default/files/", "/themes/"]):
        return False
    if "extension.psu.edu" not in parsed.netloc:
        return False
    # Must be related to grapes, wine, or viticulture
    wine_grape_kw = ["grape", "wine", "vineyard", "viticulture", "enology",
                     "oenology", "vine", "vintage", "ferment", "cellar"]
    return any(kw in path for kw in wine_grape_kw)


def _is_article_link_osu(url: str) -> bool:
    """Filter links for extension.oregonstate.edu — keep only wine grape pages."""
    parsed = urlparse(url)
    path = parsed.path.lower()
    if any(skip in path for skip in ["/search", "/login", "/user/", "/admin/",
                                      "/sites/default/files/", "/themes/",
                                      "/taxonomy/"]):
        return False
    if "extension.oregonstate.edu" not in parsed.netloc:
        return False
    # Must be related to grapes, wine, or viticulture
    wine_grape_kw = ["grape", "wine", "vineyard", "viticulture", "enology",
                     "vine", "vintage", "ferment"]
    return any(kw in path for kw in wine_grape_kw)


LINK_FILTERS = {
    "extension": _is_article_link_extension_org,
    "psu": _is_article_link_psu,
    "osu": _is_article_link_osu,
}


# ─── Core Scraping Pipeline ─────────────────────────────────────────────────

def discover_article_urls(source_key: str, max_pages: int = 5) -> list[str]:
    """Discover article URLs from a source's index page.

    Follows pagination links (up to max_pages) if they exist.
    Returns a deduplicated list of article URLs.
    """
    cfg = SOURCES[source_key]
    index_url = cfg["index_url"]
    link_filter = LINK_FILTERS.get(source_key, lambda u: True)

    all_urls: list[str] = []
    seen: set[str] = set()
    pages_fetched = 0
    current_url = index_url

    while current_url and pages_fetched < max_pages:
        logger.info(f"[{source_key}] Fetching index page: {current_url}")
        html = fetch_page(current_url)
        if not html:
            logger.warning(f"[{source_key}] Could not fetch index page: {current_url}")
            break

        pages_fetched += 1
        links = extract_article_links(html, current_url, same_domain_only=True)

        new_count = 0
        for link in links:
            if link not in seen and link_filter(link):
                seen.add(link)
                all_urls.append(link)
                new_count += 1

        logger.info(f"[{source_key}] Found {new_count} new article links on page {pages_fetched}")

        # Try to find a "next page" link
        soup = BeautifulSoup(html, "html.parser")
        next_link = None
        for a_tag in soup.find_all("a", href=True):
            text = a_tag.get_text(strip=True).lower()
            rel = a_tag.get("rel", [])
            if "next" in text or "next" in rel:
                next_url = urljoin(current_url, a_tag["href"]).split("#")[0]
                if next_url != current_url and next_url not in seen:
                    next_link = next_url
                    break

        current_url = next_link

    logger.info(f"[{source_key}] Discovered {len(all_urls)} article URLs total")
    return all_urls


def _page_is_wine_content(text: str) -> bool:
    """Check if a page's text is primarily about wine/grape topics.

    Returns True if at least 10% of sentences mention wine/grape/vine terms
    and the page is not dominated by non-wine agricultural content.
    """
    sentences = split_into_sentences(text)
    if not sentences:
        return False

    wine_count = sum(1 for s in sentences if _WINE_CONTENT_TERMS.search(s))
    non_wine_count = sum(1 for s in sentences if _NON_WINE_TERMS.search(s))

    # Skip pages dominated by non-wine content
    if non_wine_count > wine_count:
        return False

    wine_pct = wine_count / len(sentences)
    return wine_pct >= 0.10


def scrape_article(url: str) -> list[str]:
    """Scrape a single article page and return a list of factual sentences."""
    html = fetch_page(url)
    if not html:
        return []

    text = extract_main_text(html)
    if not text or len(text) < 100:
        logger.debug(f"Skipping page with insufficient content: {url}")
        return []

    # Content-based filtering: skip non-wine pages
    if not _page_is_wine_content(text):
        logger.info(f"Skipping non-wine content page: {url}")
        return []

    sentences = split_into_sentences(text)
    factual = [s for s in sentences if is_factual_sentence(s)]

    logger.debug(f"Extracted {len(factual)} factual sentences from {url} ({len(sentences)} total)")
    return factual


def build_facts_from_source(
    source_key: str,
    source_id: str,
    max_articles: int = 100,
    max_pages: int = 5,
    seen_texts: Optional[set] = None,
) -> list[dict]:
    """Build fact dicts from a single extension source.

    Steps:
      1. Discover article URLs from the index page
      2. Fetch and parse each article
      3. Extract factual sentences
      4. Classify domain/subdomain, extract entities
      5. Build fact dicts

    Args:
        seen_texts: Optional shared set for cross-source deduplication.
                    If None, a local set is created.
    """
    cfg = SOURCES[source_key]
    logger.info(f"Building facts from {cfg['name']}")

    article_urls = discover_article_urls(source_key, max_pages=max_pages)
    if not article_urls:
        logger.warning(f"[{source_key}] No article URLs discovered")
        return []

    # Limit articles
    if len(article_urls) > max_articles:
        logger.info(f"[{source_key}] Limiting to {max_articles} articles (of {len(article_urls)} found)")
        article_urls = article_urls[:max_articles]

    facts: list[dict] = []
    if seen_texts is None:
        seen_texts = set()

    for i, url in enumerate(article_urls, 1):
        logger.info(f"[{source_key}] Scraping article {i}/{len(article_urls)}: {url}")
        sentences = scrape_article(url)

        for sentence in sentences:
            # Normalize for dedup
            norm = sentence.strip()
            if norm in seen_texts:
                continue
            seen_texts.add(norm)

            domain = classify_domain(norm)
            subdomain = classify_subdomain(norm, domain)
            entities = extract_entities(norm)

            tags = [source_key, "us_extension"]
            if domain == "viticulture":
                tags.append("viticulture")
            else:
                tags.append("winemaking")

            facts.append({
                "fact_text": norm,
                "domain": domain,
                "source_id": source_id,
                "subdomain": subdomain,
                "entities": entities,
                "confidence": DEFAULT_CONFIDENCE,
                "tags": tags,
            })

    logger.info(f"[{source_key}] Generated {len(facts)} facts from {len(article_urls)} articles")
    return facts


# ─── Validation ──────────────────────────────────────────────────────────────

def validate_facts(facts: list[dict]) -> None:
    """Run quality checks on generated facts and print a report."""
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
    no_predicate = [
        f for f in facts
        if len(f["fact_text"].split()) <= 2 or not any(c in f["fact_text"] for c in ".!")
    ]
    missing_entities = [f for f in facts if not f.get("entities")]

    # Near-duplicate detection via string containment
    near_dupes = []
    fact_texts = [f["fact_text"] for f in facts]
    sample_size = min(len(fact_texts), 500)
    sampled = random.sample(range(len(fact_texts)), sample_size) if sample_size > 0 else []
    for i in range(len(sampled)):
        for j in range(i + 1, len(sampled)):
            a = fact_texts[sampled[i]].lower()
            b = fact_texts[sampled[j]].lower()
            if a != b and (a in b or b in a):
                near_dupes.append((fact_texts[sampled[i]], fact_texts[sampled[j]]))

    click.echo("\nQuality:")
    total = max(len(facts), 1)
    click.echo(f"  Too short (<5 words):   {len(too_short):>5} ({100 * len(too_short) / total:.1f}%)")
    click.echo(f"  Too long (>50 words):   {len(too_long):>5} ({100 * len(too_long) / total:.1f}%)")
    click.echo(f"  No predicate:           {len(no_predicate):>5} ({100 * len(no_predicate) / total:.1f}%)")
    click.echo(f"  Missing entities:       {len(missing_entities):>5} ({100 * len(missing_entities) / total:.1f}%)")
    click.echo(f"  Possible near-dupes:    {len(near_dupes):>5} ({100 * len(near_dupes) / total:.1f}%)")

    total_with_entities = len(facts) - len(missing_entities)
    click.echo(f"\n  % with entities:        {100 * total_with_entities / total:.1f}%")

    # Source distribution
    click.echo("\nSource distribution:")
    source_counts: dict[str, int] = defaultdict(int)
    for f in facts:
        for t in f.get("tags", []):
            if t in SOURCE_KEYS:
                source_counts[t] += 1
    for src in SOURCE_KEYS:
        click.echo(f"  {src:25s}: {source_counts.get(src, 0):>5} facts")

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
    if facts:
        sample = random.sample(facts, min(10, len(facts)))
        click.echo("\nSample facts:")
        for i, f in enumerate(sample, 1):
            click.echo(f'  {i:>2}. [{f["domain"]}:{f.get("subdomain", "")}] "{f["fact_text"]}"')

    click.echo("\n" + "=" * 60)


# ─── Pipeline ────────────────────────────────────────────────────────────────

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


def run_source(source_key: str, source_ids: dict, dry_run: bool = False,
               max_articles: int = 100, seen_texts: Optional[set] = None) -> list[dict]:
    """Run scraper for a single source. Returns list of facts."""
    logger.info(f"Running scraper for source: {source_key}")
    source_id = source_ids[source_key]
    facts = build_facts_from_source(source_key, source_id, max_articles=max_articles,
                                     seen_texts=seen_texts)

    logger.info(f"{source_key}: generated {len(facts)} facts total")

    if dry_run:
        click.echo(f"\n[DRY RUN] {source_key}: {len(facts)} facts generated (not inserted)")
        for f in facts[:5]:
            click.echo(f'  - "{f["fact_text"]}"')
        if len(facts) > 5:
            click.echo(f"  ... and {len(facts) - 5} more")
        return facts

    inserted = insert_facts_batch(facts)
    logger.info(f"{source_key}: inserted {inserted} new facts")
    click.echo(f"{source_key}: inserted {inserted} new facts ({len(facts)} generated, duplicates skipped)")
    return facts


def run_all(dry_run: bool = False) -> dict[str, list[dict]]:
    """Run scrapers for all sources."""
    source_ids = register_sources()
    results = {}
    total_generated = 0
    seen_texts: set[str] = set()  # Shared across all sources for dedup
    for key in SOURCE_KEYS:
        facts = run_source(key, source_ids, dry_run=dry_run, seen_texts=seen_texts)
        results[key] = facts
        total_generated += len(facts)
        time.sleep(1)  # Brief pause between sources

    click.echo(f"\nTotal: {total_generated} facts generated across all sources")
    if not dry_run:
        click.echo(f"Total facts in database: {get_fact_count()}")
    return results


# ─── Test Run ────────────────────────────────────────────────────────────────

CATEGORY_MAP = {
    "viticulture_general": "viticulture/general",
    "winemaking_general": "winemaking/general",
    "pest_disease_management": "viticulture/pest_disease_management",
    "canopy_management": "viticulture/canopy_management",
    "soil_nutrition": "viticulture/soil_nutrition",
    "fermentation": "winemaking/fermentation",
    "wine_chemistry": "winemaking/wine_chemistry",
    "cellar_operations": "winemaking/cellar_operations",
    "grape_varieties": "viticulture/grape_varieties",
    "site_selection_planting": "viticulture/site_selection_planting",
    "irrigation_water": "viticulture/irrigation_water",
    "harvest_ripeness": "viticulture/harvest_ripeness",
}


def limit_facts_for_test_run(
    facts: list[dict], items_per_category: int = 5
) -> tuple[list[dict], dict]:
    """Limit facts to the first N unique items per subdomain category.

    Returns (limited_facts, category_stats).
    """
    by_subdomain: dict[str, list[dict]] = defaultdict(list)
    for f in facts:
        sd = f.get("subdomain") or "(none)"
        by_subdomain[sd].append(f)

    limited: list[dict] = []
    stats: dict[str, dict] = {}

    for sd, sd_facts in by_subdomain.items():
        category = CATEGORY_MAP.get(sd, sd)
        kept = sd_facts[:items_per_category]
        limited.extend(kept)
        stats[category] = {
            "items": len(kept),
            "facts": len(kept),
        }

    return limited, stats


def print_test_run_report(
    category_stats: dict[str, dict],
    all_facts: list[dict],
    inserted_count: int,
    inserted_ids: list[str],
    cleanup: bool = False,
) -> None:
    """Print the structured test-run report."""
    total_items = sum(s["items"] for s in category_stats.values())
    total_facts = sum(s["facts"] for s in category_stats.values())

    click.echo("\n=== TEST RUN REPORT ===")
    click.echo()
    click.echo(f"{'Source/Category':<40s} {'Items Processed':>16s} {'Facts Generated':>16s} {'Facts Inserted':>16s}")
    click.echo("-" * 90)

    for cat in sorted(category_stats.keys()):
        s = category_stats[cat]
        click.echo(f"  {cat:<38s} {s['items']:>14d} {s['facts']:>14d} {'-':>14s}")

    click.echo("-" * 90)
    click.echo(f"  {'TOTAL':<38s} {total_items:>14d} {total_facts:>14d} {inserted_count:>14d}")

    # Quality checks
    too_short = [f for f in all_facts if len(f["fact_text"].split()) < 5]
    too_long = [f for f in all_facts if len(f["fact_text"].split()) > 50]
    missing_entities = [f for f in all_facts if not f.get("entities")]
    word_counts = [len(f["fact_text"].split()) for f in all_facts]
    avg_words = sum(word_counts) / max(len(word_counts), 1)

    total = max(total_facts, 1)
    click.echo()
    click.echo("  Quality Checks:")
    click.echo(f"    Too short (<5 words):  {len(too_short)} ({100 * len(too_short) / total:.1f}%)")
    click.echo(f"    Too long (>50 words):  {len(too_long)} ({100 * len(too_long) / total:.1f}%)")
    click.echo(f"    Missing entities:      {len(missing_entities)} ({100 * len(missing_entities) / total:.1f}%)")
    click.echo(f"    Avg words per fact:    {avg_words:.1f}")

    # Sample facts
    if all_facts:
        sample = random.sample(all_facts, min(10, len(all_facts)))
        click.echo()
        click.echo("  Sample Facts (up to 10 random from this run):")
        for i, f in enumerate(sample, 1):
            click.echo(f'    {i:>2}. "{f["fact_text"]}"')

    # Warnings
    warnings: list[str] = []
    for cat, s in category_stats.items():
        if s["facts"] == 0:
            warnings.append(f"ERROR: No facts from {cat}")

    pct_short = 100 * len(too_short) / total
    pct_long = 100 * len(too_long) / total
    if pct_short > 10:
        warnings.append("WARNING: Too many trivial facts")
    if pct_long > 10:
        warnings.append("WARNING: Facts need better splitting")

    long_review = [f for f in all_facts if len(f["fact_text"].split()) > 40]
    if long_review:
        warnings.append(f"* {len(long_review)} facts exceed 40 words - review fact splitting logic")

    if warnings:
        click.echo()
        click.echo("  Warnings:")
        for w in warnings:
            click.echo(f"    {w}")

    # Cleanup
    if cleanup and inserted_ids:
        deleted = delete_facts_by_ids(inserted_ids)
        click.echo()
        click.echo(f"  Cleaned up {deleted} test facts from database")

    click.echo()


def run_test(
    source: Optional[str] = None,
    cleanup: bool = False,
    items_per_category: int = 5,
) -> None:
    """Execute a test run: limit articles and facts, insert, report."""
    source_ids = register_sources()

    # For test runs, limit to 3 articles per source
    test_max_articles = 3

    all_facts: list[dict] = []
    seen_texts: set[str] = set()  # Shared across all sources for dedup
    if source:
        facts = build_facts_from_source(
            source, source_ids[source], max_articles=test_max_articles,
            seen_texts=seen_texts,
        )
        all_facts.extend(facts)
    else:
        for key in SOURCE_KEYS:
            facts = build_facts_from_source(
                key, source_ids[key], max_articles=test_max_articles,
                seen_texts=seen_texts,
            )
            all_facts.extend(facts)

    if not all_facts:
        click.echo("No facts generated during test run.")
        return

    limited, category_stats = limit_facts_for_test_run(all_facts, items_per_category)

    inserted_count, inserted_ids = insert_facts_batch_tracked(limited)

    print_test_run_report(
        category_stats, limited, inserted_count, inserted_ids, cleanup=cleanup
    )


# ─── CLI ─────────────────────────────────────────────────────────────────────

@click.command()
@click.option("--all", "run_all_flag", is_flag=True, help="Scrape all extension sources")
@click.option("--source", type=click.Choice(SOURCE_KEYS, case_sensitive=False),
              help="Scrape a specific source")
@click.option("--dry-run", is_flag=True, help="Generate facts without inserting into database")
@click.option("--validate", "validate_flag", is_flag=True, help="Run quality checks on generated facts")
@click.option("--list", "list_flag", is_flag=True, help="List available sources")
@click.option("--test-run", "test_run_flag", is_flag=True,
              help="Small test run with limited articles per source")
@click.option("--cleanup", is_flag=True, help="Delete test-run facts after report (use with --test-run)")
def main(
    run_all_flag: bool,
    source: Optional[str],
    dry_run: bool,
    validate_flag: bool,
    list_flag: bool,
    test_run_flag: bool,
    cleanup: bool,
):
    """OenoBench US University Extension Services Scraper."""
    log_time = datetime.now().strftime("%Y%m%d_%H%M%S")
    logger.add(f"data/logs/extension_{log_time}.log", rotation="10 MB")

    if list_flag:
        click.echo("\nAvailable sources:")
        for key, cfg in SOURCES.items():
            click.echo(f"  {key:15s} - {cfg['name']}")
            click.echo(f"                  {cfg['url']}")
        return

    if validate_flag:
        click.echo("Generating facts for validation (dry run mode)...")
        placeholder_ids = {key: f"placeholder-{key}" for key in SOURCES}
        all_facts = []
        for key in SOURCE_KEYS:
            facts = build_facts_from_source(key, placeholder_ids[key])
            all_facts.extend(facts)
        validate_facts(all_facts)
        return

    if test_run_flag:
        run_test(source=source, cleanup=cleanup)
        return

    if run_all_flag:
        run_all(dry_run=dry_run)
        return

    if source:
        source_ids = register_sources()
        run_source(source, source_ids, dry_run=dry_run)
        return

    click.echo("Use --all to scrape all sources, or --source <name> for a specific one.")
    click.echo("Use --list to see available sources.")
    click.echo("Use --validate to run quality checks.")
    click.echo("Use --dry-run to generate facts without database insertion.")
    click.echo("Use --test-run to process a small sample and report.")
    click.echo("Use --test-run --cleanup to auto-delete test facts after report.")


if __name__ == "__main__":
    main()
