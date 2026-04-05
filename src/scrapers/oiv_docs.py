"""
OenoBench — OIV PDF Document Scraper

Extracts winemaking and viticulture facts from OIV PDF publications that the
existing eu_oiv.py scraper did not cover (it only scraped HTML pages).

Sources:
    a) OIV Code of Oenological Practices (2025 PDF)
       https://www.oiv.int/sites/default/files/publication/2025-04/CPO%202025%20EN.pdf
       Definitions of wine types, permitted practices, chemical limits.

    b) OIV State of the World Vine and Wine Sector (2024 PDF)
       https://www.oiv.int/sites/default/files/2025-04/OIV-State_of_the_World_Vine-and-Wine-Sector-in-2024.pdf
       Production statistics, consumption trends, vineyard area, trade data.

Usage:
    python -m src.scrapers.oiv_docs --all
    python -m src.scrapers.oiv_docs --source cpo
    python -m src.scrapers.oiv_docs --source state
    python -m src.scrapers.oiv_docs --dry-run
    python -m src.scrapers.oiv_docs --validate
    python -m src.scrapers.oiv_docs --list
    python -m src.scrapers.oiv_docs --test-run
    python -m src.scrapers.oiv_docs --test-run --cleanup
"""

import random
import re
import time
from collections import defaultdict
from pathlib import Path
from typing import Optional

import click
import requests
from loguru import logger

from src.utils.facts import (
    ensure_source,
    insert_fact,
    insert_facts_batch,
    get_fact_count,
)

# ─── PDF library import ──────────────────────────────────────────────────────

try:
    import pdfplumber

    PDF_BACKEND = "pdfplumber"
except ImportError:
    pdfplumber = None  # type: ignore[assignment]
    try:
        from PyPDF2 import PdfReader  # type: ignore[import-untyped]

        PDF_BACKEND = "PyPDF2"
    except ImportError:
        PdfReader = None  # type: ignore[assignment,misc]
        PDF_BACKEND = None

# ─── Configuration ────────────────────────────────────────────────────────────

USER_AGENT = "OenoBench-Research/1.0 (academic wine benchmark)"
REQUEST_DELAY = 5.0  # seconds between requests (OIV server)
REQUEST_TIMEOUT = 120  # PDFs can be large

HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "application/pdf,*/*",
}

RAW_DIR = Path("data/raw")

# ─── Source Definitions ───────────────────────────────────────────────────────

SOURCES = {
    "cpo": {
        "name": "OIV — Code of Oenological Practices (2025)",
        "description": "Definitions of wine types, permitted oenological practices, chemical limits",
        "register_name": "OIV — Code of Oenological Practices (2025)",
        "register_url": "https://www.oiv.int/standards/international-code-of-oenological-practices",
        "pdf_url": "https://www.oiv.int/sites/default/files/publication/2025-04/CPO%202025%20EN.pdf",
        "local_filename": "oiv_cpo_2025_en.pdf",
        "source_type": "international_organization",
        "tier": "tier_1_official",
        "domain": "winemaking",
        "subdomain": "oiv_oenological_practices",
        "tags_base": ["oiv", "oenological_practices", "regulation"],
    },
    "state": {
        "name": "OIV — State of the World Vine and Wine Sector (2024)",
        "description": "Global production statistics, consumption trends, vineyard area, trade data",
        "register_name": "OIV — State of the World Vine and Wine Sector (2024)",
        "register_url": "https://www.oiv.int/what-we-do/statistics",
        "pdf_url": "https://www.oiv.int/sites/default/files/2025-04/OIV-State_of_the_World_Vine-and-Wine-Sector-in-2024.pdf",
        "local_filename": "oiv_state_world_2024.pdf",
        "source_type": "international_organization",
        "tier": "tier_1_official",
        "domain": "wine_business",
        "subdomain": "oiv_global_statistics",
        "tags_base": ["oiv", "statistics", "global"],
    },
}


# ─── HTTP / PDF Download ─────────────────────────────────────────────────────

_last_request_time = 0.0


def _rate_limited_download(url: str, dest: Path) -> bool:
    """Download a file with rate limiting. Returns True on success."""
    global _last_request_time
    elapsed = time.time() - _last_request_time
    if elapsed < REQUEST_DELAY:
        time.sleep(REQUEST_DELAY - elapsed)

    try:
        logger.info(f"Downloading: {url}")
        resp = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT, stream=True)
        _last_request_time = time.time()
        resp.raise_for_status()

        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)

        size_mb = dest.stat().st_size / (1024 * 1024)
        logger.info(f"Downloaded {dest} ({size_mb:.1f} MB)")
        return True
    except requests.RequestException as e:
        logger.error(f"Failed to download {url}: {e}")
        _last_request_time = time.time()
        return False


def _ensure_pdf(source_key: str) -> Optional[Path]:
    """Return local path to PDF, downloading if not cached."""
    cfg = SOURCES[source_key]
    local_path = RAW_DIR / cfg["local_filename"]

    if local_path.exists() and local_path.stat().st_size > 1000:
        logger.info(f"Using cached PDF: {local_path}")
        return local_path

    ok = _rate_limited_download(cfg["pdf_url"], local_path)
    if ok and local_path.exists() and local_path.stat().st_size > 1000:
        return local_path

    logger.error(f"PDF not available for {source_key}: {cfg['pdf_url']}")
    return None


# ─── PDF Text Extraction ─────────────────────────────────────────────────────


def _extract_text_from_pdf(pdf_path: Path) -> list[str]:
    """Extract text from each page of a PDF. Returns list of page texts."""
    if PDF_BACKEND is None:
        logger.error(
            "No PDF library available. Install pdfplumber or PyPDF2: "
            "pip install pdfplumber"
        )
        return []

    pages: list[str] = []

    try:
        if PDF_BACKEND == "pdfplumber":
            with pdfplumber.open(pdf_path) as pdf:
                for page in pdf.pages:
                    text = page.extract_text() or ""
                    pages.append(text)
        else:
            # PyPDF2
            reader = PdfReader(str(pdf_path))
            for page in reader.pages:
                text = page.extract_text() or ""
                pages.append(text)
    except Exception as e:
        logger.error(f"Error reading PDF {pdf_path}: {e}")
        return []

    logger.info(f"Extracted text from {len(pages)} pages of {pdf_path.name}")
    return pages


# ─── Sentence Splitting ──────────────────────────────────────────────────────

# Pattern to split on sentence boundaries (period/question-mark/excl followed by space + capital)
_SENTENCE_SPLIT_RE = re.compile(
    r"(?<=[.!?])\s+(?=[A-Z])"
)

# Abbreviations that should not trigger a sentence split
_ABBREV = {"e.g.", "i.e.", "etc.", "vs.", "approx.", "no.", "No.", "vol.", "Vol."}


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences, handling PDF-specific quirks.

    PDF text often has:
    - Line breaks within sentences (should be joined)
    - Bullet points that should be individual facts
    - Table data mixed with prose
    - Repeated page headers/footers
    """
    if not text or not text.strip():
        return []

    # Step 1: Remove common PDF page headers/footers that repeat
    # e.g. "International Code of Oenological Practices" at top of every page
    text = re.sub(
        r"International\s+Code\s+of\s+Oenological\s+Practices",
        "", text, flags=re.IGNORECASE,
    )
    text = re.sub(
        r"State\s+of\s+the\s+World\s+Vine\s+and\s+Wine\s+Sector\s+in\s+\d{4}",
        "", text, flags=re.IGNORECASE,
    )
    # Remove bare page numbers (line that is just a number)
    text = re.sub(r"\n\s*\d{1,3}\s*\n", "\n", text)
    # Remove "OIV" alone on a line
    text = re.sub(r"\n\s*OIV\s*\n", "\n", text)

    # Step 2: Handle bullet points — convert bullets to sentence breaks
    # Common bullet chars: •, -, –, —, ▪, ◦, *, and numbered lists (a), (b), (i), (ii)
    text = re.sub(r"\n\s*[\u2022\u25AA\u25E6\u2023]\s*", "\n", text)
    text = re.sub(r"\n\s*[-\u2013\u2014]\s+", "\n", text)
    text = re.sub(r"\n\s*\([a-z]\)\s+", "\n", text)
    text = re.sub(r"\n\s*\([ivx]+\)\s+", "\n", text)

    # Step 3: Join lines that are mid-sentence (line break within a sentence).
    # A line ending without sentence-ending punctuation followed by a line
    # starting with a lowercase letter or number is likely a continuation.
    lines = text.split("\n")
    joined_lines = []
    buffer = ""
    for line in lines:
        stripped = line.strip()
        if not stripped:
            # Empty line = paragraph break
            if buffer:
                joined_lines.append(buffer)
                buffer = ""
            continue
        if buffer:
            # Check if this line continues the previous sentence
            # Continuation: previous line doesn't end with sentence punct, and
            # this line starts with lowercase or a digit (mid-sentence)
            if (
                not buffer.rstrip().endswith((".", "!", "?", ":", ";"))
                and stripped
                and (stripped[0].islower() or stripped[0].isdigit())
            ):
                buffer = buffer.rstrip() + " " + stripped
            else:
                joined_lines.append(buffer)
                buffer = stripped
        else:
            buffer = stripped
    if buffer:
        joined_lines.append(buffer)

    # Step 4: Split each paragraph/joined-line into sentences
    result = []
    for paragraph in joined_lines:
        # Normalize whitespace within the paragraph
        paragraph = re.sub(r"\s+", " ", paragraph).strip()
        if not paragraph:
            continue

        raw_sentences = _SENTENCE_SPLIT_RE.split(paragraph)
        for s in raw_sentences:
            s = s.strip()
            if len(s) < 15:
                continue
            # Skip page headers, footers, TOC lines
            if re.match(r"^(Page\s+\d+|Table of Contents|\d+\s*$)", s, re.IGNORECASE):
                continue
            # Skip lines that are mostly numbers/punctuation (table residue)
            alpha_chars = sum(1 for c in s if c.isalpha())
            if len(s) > 0 and alpha_chars / len(s) < 0.4:
                continue
            # Skip ALL-CAPS section titles (common in PDFs)
            words = s.split()
            upper_words = sum(1 for w in words if w.isupper() and len(w) > 2)
            if len(words) > 0 and upper_words / len(words) > 0.6 and len(words) < 10:
                continue
            # Skip TOC entries (text ... page number)
            if re.search(r"\.{3,}\s*\d+\s*$", s):
                continue
            result.append(s)

    return result


# ─── Fact Filtering & Classification ─────────────────────────────────────────

# Keywords that indicate a factual sentence worth extracting.
# Each alternative is designed to match SPECIFIC wine knowledge, not generic text.
_FACTUAL_INDICATORS = re.compile(
    r"""
    # Specific numeric values with units (chemical limits, production stats)
    \d+[\.,]?\d*\s*(mg/L|mg/l|g/L|g/l|%\s*vol|%\s*v/v|°C|ml/L|mL/L|hl|hectolitres?|tonnes?|million\s+hectolitres?|million\s+tonnes?|billion|mha|kha|hectares?|mg|g/hl)
    # Percentage with context
    | \d+[\.,]?\d*\s*(%|percent|per\s+cent)\s+(?:of|increase|decrease|decline|growth|higher|lower|more|less|compared)
    # Chemical limits and regulatory thresholds
    | \b(maximum\s+permitted|minimum\s+required|must\s+not\s+exceed|shall\s+not\s+exceed|no\s+more\s+than|at\s+least|upper\s+limit|maximum\s+dose|maximum\s+concentration|maximum\s+level)
    # Specific chemical compounds in wine context
    | \b(sulphur\s+dioxide|SO2|volatile\s+acidity|total\s+acidity|residual\s+sugar|tartaric\s+acid|malic\s+acid|lactic\s+acid|citric\s+acid|ascorbic\s+acid|sorbic\s+acid|potassium\s+sorbate|potassium\s+metabisulphite|bentonite|gelatin|casein|metatartaric\s+acid|copper\s+sulphate|diammonium\s+phosphate|thiamine|lysozyme|PVPP|polyvinylpolypyrrolidone|tannin|carbon\s+dioxide|CO2|acetic\s+acid|acetaldehyde)\b
    # Specific winemaking process descriptions (require at least partial context)
    | \b(fermentation\s+temperature|malolactic\s+fermentation|alcoholic\s+fermentation|cold\s+maceration|carbonic\s+maceration|cold\s+stabilisation|cold\s+stabilization|reverse\s+osmosis|micro-?filtration|cross-?flow|must\s+concentration|chaptalis[ae]tion|deacidification|acidification|dealcoholi[sz]ation)\b
    # Permitted/prohibited with substance or practice
    | \b(permitted\s+(?:additive|addition|practice|treatment|substance|dose|level|use)|prohibited\s+(?:in|for|practice|substance|additive))\b
    # Production statistics with country or year context
    | \b(production\s+(?:in\s+\d{4}|of\s+wine|reached|estimated|was|totall?ed|amounted)|consumption\s+(?:in\s+\d{4}|of\s+wine|reached|estimated|per\s+capita|was|totall?ed))\b
    | \b(exports?\s+(?:of\s+wine|reached|totall?ed|amounted|in\s+value|in\s+volume)|imports?\s+(?:of\s+wine|reached|totall?ed|amounted|in\s+value|in\s+volume))\b
    # Vineyard area with numbers
    | \b(vineyard\s+area|planted\s+area|area\s+under\s+vines?)\b.*\d
    # Wine type definitions
    | \b(is\s+(?:a\s+wine|the\s+product|obtained\s+by|defined\s+as)|wine\s+(?:obtained|produced|made)\s+(?:from|by|exclusively|through))\b
    # Specific country + wine stat combination
    | \b(France|Italy|Spain|United\s+States|China|Germany|Argentina|Australia|Chile|South\s+Africa|Portugal)\b.*\b(produc|export|import|consump|vineyard|hectolitre|hectare|wine)\b
    # Year-over-year comparisons
    | \b(compared\s+to\s+\d{4}|year-over-year|between\s+\d{4}\s+and\s+\d{4}|since\s+\d{4}|from\s+\d{4}\s+to\s+\d{4})\b
    """,
    re.VERBOSE | re.IGNORECASE,
)

# Domain classification keywords
_WINEMAKING_KEYWORDS = re.compile(
    r"\b(ferment|vinif|oenolog|enolog|macerat|chaptalis|deacidif|acidif|clarif|"
    r"filtrat|stabilis|pasteuris|fining|ageing|aging|barrel|oak|yeast|malolactic|"
    r"sulphur|SO2|tannin|phenol|anthocyanin|must|wine|sparkling|fortified|"
    r"dessert\s+wine|rosé|white\s+wine|red\s+wine|blending|bottling|racking|"
    r"definition|defined\s+as|permitted|practice|treatment|addition|limit|threshold|"
    r"maximum|minimum|concentration|residual\s+sugar|alcohol|volatile\s+acidity|"
    r"total\s+acidity|tartaric|malic|lactic|citric|ascorbic|sorbic|potassium|"
    r"calcium|copper|iron|lead|arsenic|cadmium|mercury)",
    re.IGNORECASE,
)

_VITICULTURE_KEYWORDS = re.compile(
    r"\b(viticult|vine|vineyard|rootstock|pruning|canopy|trellis|irrigation|"
    r"grafting|phylloxera|terroir|soil|climate|rainfall|temperature|frost|"
    r"sunlight|photosynthesis|berry|veraison|bud\s+break|harvest|ripeness|"
    r"planted\s+area|planting\s+density|yield\s+per\s+hectare)",
    re.IGNORECASE,
)

_BUSINESS_KEYWORDS = re.compile(
    r"\b(production\s+volume|consumption|export|import|trade|market|price|"
    r"revenue|economic|billion|million|tonnes|hectolitres|growth|decline|"
    r"increase|decrease|rank|share|country|countries|global|world|total|"
    r"per\s+capita|average|value|volume|trend)",
    re.IGNORECASE,
)

# Patterns to detect and skip non-factual content
_SKIP_PATTERNS = [
    re.compile(r"^\s*(chapter|section|part|annex|appendix)\s+\d", re.IGNORECASE),
    re.compile(r"^(see|refer|note|source|figure|table|graph|chart)\s", re.IGNORECASE),
    re.compile(r"^(the\s+)?(author|editor|publisher|organisation|organization)\b", re.IGNORECASE),
    re.compile(r"(www\.|http|@|copyright|©|all\s+rights\s+reserved)", re.IGNORECASE),
    re.compile(r"^\d+\.\d+\.\d+"),  # Section numbering like 1.2.3
    re.compile(r"(FOREWORD|PREFACE|INTRODUCTION|PREAMBLE)", re.IGNORECASE),
    re.compile(r"(stipulations|General\s+Assembly|Agreement\s+of\s+3\s+April)", re.IGNORECASE),
    re.compile(r"(Legal\s+basis|Resolution\s+[A-Z]+\s+\d)", re.IGNORECASE),
    re.compile(r"(present\s+edition|codification|regulatory\s+corpus)", re.IGNORECASE),
    re.compile(r"^(STATE\s+OF\s+THE\s+WORLD|APRIL\s+\d{4})", re.IGNORECASE),
    re.compile(r"^\s*—\s*\d+\s"),  # Page markers like "— 2"
    # --- A) Additional skip patterns ---
    # Document self-references
    re.compile(r"\b(this\s+document|this\s+code|this\s+edition|present\s+edition)\b", re.IGNORECASE),
    # OIV procedural/administrative language
    re.compile(r"\b(Member\s+Countries|General\s+Assembly|adopted\s+by|was\s+adopted)\b", re.IGNORECASE),
    re.compile(r"\b(Resolution\s+\w+/\d|OIV\s+Resolution)\b", re.IGNORECASE),
    # Document metadata
    re.compile(r"\b(published\s+in|edition\s+of|updated\s+on|last\s+updated|date\s+of\s+publication)\b", re.IGNORECASE),
    # Page numbers and section markers
    re.compile(r"^\s*\d+\s*$"),  # Bare page numbers
    re.compile(r"^\s*\d+\s*[-/]\s*\d+\s*$"),  # Page ranges like "12/345"
    re.compile(r"^(International\s+Code|Code\s+of\s+Oenological)", re.IGNORECASE),  # Repeated header
    # TOC entries (text followed by dots and page number)
    re.compile(r"\.{3,}\s*\d+\s*$"),
    # Meta-descriptions about the document purpose
    re.compile(r"\b(constitutes\s+a\s+(technical|legal)|aims\s+to\s+(describe|provide|present)|scope\s+of\s+this)\b", re.IGNORECASE),
    re.compile(r"\b(the\s+purpose\s+of\s+this|the\s+objective\s+of\s+this|is\s+intended\s+to)\b", re.IGNORECASE),
    # Acknowledgements and attribution
    re.compile(r"\b(acknowledgement|contributors|prepared\s+by|compiled\s+by|drafted\s+by)\b", re.IGNORECASE),
]


def _is_factual(sentence: str) -> bool:
    """Check if a sentence contains factual/numeric/regulatory content."""
    if len(sentence.split()) < 6:
        return False
    if len(sentence.split()) > 40:
        return False
    for pat in _SKIP_PATTERNS:
        if pat.search(sentence):
            return False
    return bool(_FACTUAL_INDICATORS.search(sentence))


def _classify_domain(sentence: str, default_domain: str) -> str:
    """Classify a sentence into a domain based on keyword matching."""
    winemaking_score = len(_WINEMAKING_KEYWORDS.findall(sentence))
    viticulture_score = len(_VITICULTURE_KEYWORDS.findall(sentence))
    business_score = len(_BUSINESS_KEYWORDS.findall(sentence))

    if business_score > winemaking_score and business_score > viticulture_score:
        return "wine_business"
    if viticulture_score > winemaking_score and viticulture_score > business_score:
        return "viticulture"
    if winemaking_score > 0:
        return "winemaking"

    return default_domain


def _extract_entities(sentence: str) -> list[dict]:
    """Extract entities from a sentence: countries, chemicals, wine types, processes, measures."""
    entities = []

    # Countries commonly mentioned in wine context
    country_pattern = re.compile(
        r"\b(France|Italy|Spain|United\s+States|USA|U\.S\.|China|Germany|Argentina|"
        r"Australia|Chile|South\s+Africa|Portugal|Romania|Greece|New\s+Zealand|"
        r"Austria|Hungary|Brazil|Georgia|Moldova|Russia|Turkey|Switzerland|"
        r"Canada|Japan|UK|United\s+Kingdom|India|Mexico|Uruguay|Algeria|"
        r"Morocco|Tunisia|Croatia|Slovenia|Serbia|Bulgaria|Czech\s+Republic|"
        r"Lebanon|Israel|Peru|Bolivia)\b",
        re.IGNORECASE,
    )
    for m in country_pattern.finditer(sentence):
        name = m.group(0)
        # Normalize abbreviations
        if name.upper() in ("USA", "U.S."):
            name = "United States"
        elif name.upper() == "UK":
            name = "United Kingdom"
        entities.append({"type": "country", "name": name})

    # Chemical/oenological substances
    chem_pattern = re.compile(
        r"\b(sulphur\s+dioxide|sulfur\s+dioxide|SO2|tartaric\s+acid|malic\s+acid|"
        r"lactic\s+acid|citric\s+acid|ascorbic\s+acid|sorbic\s+acid|acetic\s+acid|"
        r"volatile\s+acidity|total\s+acidity|residual\s+sugar|ethanol|alcohol|"
        r"potassium\s+sorbate|potassium\s+metabisulphite|potassium\s+bitartrate|"
        r"bentonite|gelatin|casein|albumin|isinglass|PVPP|"
        r"polyvinylpolypyrrolidone|activated\s+carbon|silicon\s+dioxide|"
        r"copper\s+sulphate|copper\s+sulfate|metatartaric\s+acid|"
        r"diammonium\s+phosphate|DAP|thiamine|lysozyme|pectinase|"
        r"carbon\s+dioxide|CO2|nitrogen|oxygen|argon|tannin|tannins|"
        r"anthocyanin|anthocyanins|phenol|phenols|polyphenol|polyphenols|"
        r"acetaldehyde|glycerol|methanol)\b",
        re.IGNORECASE,
    )
    for m in chem_pattern.finditer(sentence):
        entities.append({"type": "chemical", "name": m.group(0)})

    # Wine types
    wine_type_pattern = re.compile(
        r"\b(red\s+wine|white\s+wine|rosé\s+wine|rosé|sparkling\s+wine|"
        r"fortified\s+wine|dessert\s+wine|still\s+wine|liqueur\s+wine|"
        r"sweet\s+wine|dry\s+wine|semi-sweet\s+wine|semi-dry\s+wine|"
        r"table\s+wine|natural\s+wine|ice\s+wine|noble\s+rot\s+wine|"
        r"botrytised\s+wine|late\s+harvest\s+wine|aromatised\s+wine|"
        r"aromatized\s+wine|special\s+wine|organic\s+wine|"
        r"de-?alcoholi[sz]ed\s+wine|low[- ]alcohol\s+wine|"
        r"reds?|whites?|sparkling|fortified)\b",
        re.IGNORECASE,
    )
    for m in wine_type_pattern.finditer(sentence):
        # Avoid bare "red", "white" without wine context nearby
        name = m.group(0)
        if name.lower() in ("red", "reds", "white", "whites", "sparkling", "fortified"):
            # Only include if "wine" appears elsewhere in the sentence
            if "wine" not in sentence.lower():
                continue
        entities.append({"type": "wine_type", "name": name})

    # Winemaking processes
    process_pattern = re.compile(
        r"\b(fermentation|alcoholic\s+fermentation|malolactic\s+fermentation|"
        r"maceration|cold\s+maceration|carbonic\s+maceration|"
        r"chaptalisation|chaptalization|enrichment|"
        r"fining|clarification|filtration|micro-?filtration|ultra-?filtration|"
        r"cross-?flow\s+filtration|"
        r"stabilisation|stabilization|cold\s+stabili[sz]ation|"
        r"pasteurisation|pasteurization|flash\s+pasteurisation|"
        r"acidification|deacidification|"
        r"dealcoholi[sz]ation|reverse\s+osmosis|"
        r"racking|lees\s+contact|sur\s+lie|bâtonnage|batonnage|"
        r"riddling|disgorgement|dosage|"
        r"blending|assemblage|coupage|"
        r"ageing|aging|barrel\s+ageing|barrel\s+aging|oak\s+ageing|"
        r"bottling|corking|"
        r"must\s+concentration|cryoextraction|cryoconcentration|"
        r"saignée|délestage|remontage|pigeage)\b",
        re.IGNORECASE,
    )
    for m in process_pattern.finditer(sentence):
        entities.append({"type": "process", "name": m.group(0)})

    # Numeric measures (extract the value + unit as an entity)
    measure_pattern = re.compile(
        r"(\d+[\.,]?\d*)\s*(mg/L|mg/l|g/L|g/l|%\s*vol|°C|hl|hectolitres?|"
        r"million\s+hectolitres?|tonnes?|million\s+tonnes?|hectares?|mha|kha|"
        r"billion|million)\b",
        re.IGNORECASE,
    )
    for m in measure_pattern.finditer(sentence):
        entities.append({"type": "measure", "name": m.group(0).strip()})

    # Deduplicate
    seen = set()
    unique = []
    for e in entities:
        key = (e["type"], e["name"].lower())
        if key not in seen:
            seen.add(key)
            unique.append(e)

    return unique


# ─── Fact Extraction from CPO ────────────────────────────────────────────────


def _clean_fact_text(text: str) -> str:
    """Clean and normalize a fact sentence."""
    # Remove leading/trailing whitespace and punctuation artifacts
    text = text.strip()
    # Remove leading bullet points, dashes, numbering
    text = re.sub(r"^[\-\u2022\u2013\u2014]\s*", "", text)
    text = re.sub(r"^\d+[\.\)]\s*", "", text)
    # Collapse multiple spaces
    text = re.sub(r"\s+", " ", text)
    # Ensure ends with period
    if text and not text.endswith((".","!","?")):
        text += "."
    return text


def _extract_facts_from_pages(
    pages: list[str],
    source_id: str,
    default_domain: str,
    default_subdomain: str,
    tags_base: list[str],
    confidence: float = 0.95,
) -> list[dict]:
    """Extract atomic facts from PDF page texts."""
    facts = []
    seen_texts: set[str] = set()

    for page_idx, page_text in enumerate(pages):
        sentences = _split_sentences(page_text)

        for sentence in sentences:
            if not _is_factual(sentence):
                continue

            cleaned = _clean_fact_text(sentence)
            if not cleaned or len(cleaned) < 20:
                continue

            # Deduplicate within this extraction run
            lower = cleaned.lower()
            if lower in seen_texts:
                continue
            seen_texts.add(lower)

            domain = _classify_domain(cleaned, default_domain)
            entities = _extract_entities(cleaned)

            facts.append({
                "fact_text": cleaned,
                "domain": domain,
                "source_id": source_id,
                "subdomain": default_subdomain,
                "entities": entities,
                "confidence": confidence,
                "tags": list(tags_base),
            })

    logger.info(
        f"Extracted {len(facts)} facts from {len(pages)} pages "
        f"(domain default: {default_domain})"
    )
    return facts


# ─── Source Runners ───────────────────────────────────────────────────────────


def _run_source(source_key: str, dry_run: bool = False) -> tuple[int, list[dict]]:
    """Extract facts from a single OIV PDF source. Returns (count, facts)."""
    cfg = SOURCES[source_key]
    logger.info(f"Running source: {source_key} — {cfg['description']}")

    # Register source (or use placeholder for dry-run)
    if dry_run:
        source_id = "dry-run"
    else:
        source_id = ensure_source(
            name=cfg["register_name"],
            url=cfg["register_url"],
            source_type=cfg["source_type"],
            tier=cfg["tier"],
            language="en",
        )

    # Download / cache PDF
    pdf_path = _ensure_pdf(source_key)
    if pdf_path is None:
        logger.error(f"Cannot proceed without PDF for {source_key}")
        return 0, []

    # Extract text
    pages = _extract_text_from_pdf(pdf_path)
    if not pages:
        logger.error(f"No text extracted from {pdf_path}")
        return 0, []

    # Extract facts
    facts = _extract_facts_from_pages(
        pages=pages,
        source_id=source_id,
        default_domain=cfg["domain"],
        default_subdomain=cfg["subdomain"],
        tags_base=cfg["tags_base"],
        confidence=0.95,
    )

    if not facts:
        logger.warning(f"No facts extracted from {source_key}")
        return 0, []

    if dry_run:
        click.echo(f"\n[DRY RUN] Would insert {len(facts)} facts from '{source_key}'.")
        return len(facts), facts

    # Insert into PostgreSQL
    inserted = insert_facts_batch(facts)
    logger.info(
        f"Inserted {inserted} new facts from {source_key} (duplicates skipped)"
    )
    return inserted, facts


def run_all_sources(dry_run: bool = False) -> dict[str, int]:
    """Run extraction for all sources. Returns {source: count}."""
    summary: dict[str, int] = {}
    for name in SOURCES:
        count, _ = _run_source(name, dry_run=dry_run)
        summary[name] = count
    logger.info(f"OIV PDF scraping complete. Total facts: {sum(summary.values())}")
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

    # (c) Entity-name-only facts (no predicate)
    no_predicate = [
        f for f in facts if len(f["fact_text"].rstrip(".").strip().split()) <= 1
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
        for b in sampled[i + 1:]:
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
        click.echo(f'  {i:2d}. [{f["domain"]}] "{f["fact_text"]}"')


# ─── Test Run ─────────────────────────────────────────────────────────────────

TEST_RUN_LIMIT = 5  # facts per source


def _insert_facts_tracked(facts: list[dict]) -> tuple[int, list[str]]:
    """Insert facts individually and track inserted IDs. Returns (count, ids)."""
    if not facts:
        return 0, []

    inserted_count = 0
    inserted_ids: list[str] = []
    for f in facts:
        fid = insert_fact(
            fact_text=f["fact_text"],
            domain=f["domain"],
            source_id=f["source_id"],
            subdomain=f.get("subdomain"),
            entities=f.get("entities"),
            confidence=f.get("confidence", 1.0),
            tags=f.get("tags"),
        )
        if fid:
            inserted_count += 1
            inserted_ids.append(str(fid))

    return inserted_count, inserted_ids


def _cleanup_test_facts(fact_ids: list[str]) -> int:
    """Delete facts by their IDs. Returns count deleted."""
    if not fact_ids:
        return 0

    from src.utils.db import get_pg

    conn = get_pg()
    cur = conn.cursor()
    deleted = 0
    for fid in fact_ids:
        cur.execute("DELETE FROM facts WHERE id = %s", (fid,))
        deleted += cur.rowcount
    conn.commit()
    return deleted


def _print_test_report(
    category_stats: dict[str, dict],
    all_facts: list[dict],
    all_inserted_ids: list[str],
) -> None:
    """Print the structured test-run report with quality checks."""
    click.echo("\n=== TEST RUN REPORT ===")
    click.echo("")

    header = (
        f"  {'Source/Category':<25s} {'Pages Extracted':>17s} "
        f"{'Facts Generated':>17s} {'Facts Inserted (new)':>22s}"
    )
    separator = "  " + "\u2500" * 83
    click.echo(header)
    click.echo(separator)

    total_pages = 0
    total_generated = 0
    total_inserted = 0

    for cat_name, stats in category_stats.items():
        pages = stats["pages_extracted"]
        generated = stats["facts_generated"]
        inserted = stats["facts_inserted"]
        total_pages += pages
        total_generated += generated
        total_inserted += inserted
        click.echo(
            f"  {cat_name:<25s} {pages:>17d} {generated:>17d} {inserted:>22d}"
        )

    click.echo(separator)
    click.echo(
        f"  {'TOTAL':<25s} {total_pages:>17d} {total_generated:>17d} "
        f"{total_inserted:>22d}"
    )

    # Quality checks
    if not all_facts:
        click.echo("\n  No facts to analyze.")
        return

    total = len(all_facts)
    too_short = 0
    too_long = 0
    missing_entities = 0
    total_words = 0

    for f in all_facts:
        text = f["fact_text"]
        wc = len(text.split())
        total_words += wc
        if wc < 5:
            too_short += 1
        if wc > 50:
            too_long += 1
        if not f.get("entities"):
            missing_entities += 1

    avg_words = total_words / total if total else 0

    click.echo(f"\n  Quality Checks:")
    click.echo(
        f"    Too short (<5 words):  {too_short} ({too_short / total * 100:.1f}%)"
    )
    click.echo(
        f"    Too long (>50 words):  {too_long} ({too_long / total * 100:.1f}%)"
    )
    click.echo(
        f"    Missing entities:      {missing_entities} ({missing_entities / total * 100:.1f}%)"
    )
    click.echo(f"    Avg words per fact:    {avg_words:.1f}")

    # Sample facts
    sample = random.sample(all_facts, min(10, len(all_facts)))
    click.echo(f"\n  Sample Facts ({min(10, len(all_facts))} random from this run):")
    for i, f in enumerate(sample, 1):
        click.echo(f'    {i:2d}. [{f["domain"]}] "{f["fact_text"]}"')


def run_test(source_filter: Optional[str] = None, cleanup: bool = False) -> None:
    """Run a limited test extraction: TEST_RUN_LIMIT facts per source, insert, report."""
    category_stats: dict[str, dict] = {}
    all_facts_collected: list[dict] = []
    all_inserted_ids: list[str] = []

    sources_to_run = [source_filter] if source_filter else list(SOURCES.keys())

    for source_key in sources_to_run:
        if source_key not in SOURCES:
            logger.warning(f"Unknown source: {source_key}")
            continue

        cfg = SOURCES[source_key]
        source_id = ensure_source(
            name=cfg["register_name"],
            url=cfg["register_url"],
            source_type=cfg["source_type"],
            tier=cfg["tier"],
            language="en",
        )

        # Download / cache PDF
        pdf_path = _ensure_pdf(source_key)
        if pdf_path is None:
            category_stats[source_key] = {
                "pages_extracted": 0,
                "facts_generated": 0,
                "facts_inserted": 0,
            }
            continue

        # Extract text
        pages = _extract_text_from_pdf(pdf_path)
        if not pages:
            category_stats[source_key] = {
                "pages_extracted": 0,
                "facts_generated": 0,
                "facts_inserted": 0,
            }
            continue

        # Extract facts (all of them, then limit)
        facts = _extract_facts_from_pages(
            pages=pages,
            source_id=source_id,
            default_domain=cfg["domain"],
            default_subdomain=cfg["subdomain"],
            tags_base=cfg["tags_base"],
            confidence=0.95,
        )

        # Limit to TEST_RUN_LIMIT
        subset = facts[:TEST_RUN_LIMIT]

        inserted, ids = _insert_facts_tracked(subset)
        category_stats[source_key] = {
            "pages_extracted": len(pages),
            "facts_generated": len(subset),
            "facts_inserted": inserted,
        }
        all_facts_collected.extend(subset)
        all_inserted_ids.extend(ids)

    # Report
    _print_test_report(category_stats, all_facts_collected, all_inserted_ids)

    # Cleanup
    if cleanup and all_inserted_ids:
        deleted = _cleanup_test_facts(all_inserted_ids)
        click.echo(f"\n  Cleaned up {deleted} test facts from database.")


# ─── CLI ──────────────────────────────────────────────────────────────────────


@click.command()
@click.option(
    "--source",
    "-s",
    type=click.Choice(["cpo", "state"]),
    help="Run a specific source (cpo or state)",
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
@click.option(
    "--test-run", is_flag=True, help="Process 5 facts per source, insert, and report"
)
@click.option(
    "--cleanup", is_flag=True, help="With --test-run, delete inserted facts after reporting"
)
def main(
    source: Optional[str],
    run_all: bool,
    list_sources: bool,
    dry_run: bool,
    validate_flag: bool,
    test_run: bool,
    cleanup: bool,
):
    """OenoBench OIV PDF Scraper — Extract wine facts from OIV PDF documents."""
    logger.add("data/logs/oiv_docs_{time}.log", rotation="10 MB")

    if PDF_BACKEND is None:
        click.echo(
            "ERROR: No PDF library available. Install pdfplumber: pip install pdfplumber"
        )
        return

    click.echo(f"Using PDF backend: {PDF_BACKEND}")

    if list_sources:
        click.echo("\nAvailable sources:")
        for name, cfg in SOURCES.items():
            click.echo(f"  {name:10s} — {cfg['description']}")
            click.echo(f"             PDF: {cfg['pdf_url']}")
            click.echo(f"             Domain: {cfg['domain']}")
        return

    if validate_flag:
        click.echo("Running validation on all sources (dry-run extraction)...")
        all_facts: list[dict] = []
        for source_key in SOURCES:
            _, facts = _run_source(source_key, dry_run=True)
            all_facts.extend(facts)
        validate_facts(all_facts)
        return

    if test_run:
        run_test(source_filter=source, cleanup=cleanup)
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
        count, facts = _run_source(source, dry_run=dry_run)
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
    click.echo("Use --test-run to process 5 facts per source and report.")


if __name__ == "__main__":
    main()
