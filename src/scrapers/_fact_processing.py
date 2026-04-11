"""
OenoBench — Shared fact processing pipeline.

Ensures all scraped text is decomposed into atomic, well-formed facts
with proper domain classification and quality validation.

Used by all scrapers after raw text extraction.
"""

import re
from typing import Optional

# ─── Constants ───────────────────────────────────────────────────────────────

MAX_FACT_WORDS = 30
MIN_FACT_WORDS = 5

# Pronouns / dangling references that need resolution
_DANGLING_STARTS = re.compile(
    r"^(He|She|It|They|The house|The estate|The château|The chateau|"
    r"The domaine|The domain|The winery|The vineyard|The region|"
    r"The village|The commune|The area|The wine|The grape|"
    r"This|These|Those|His|Her|Its|Their)\b",
    re.IGNORECASE,
)

# Sentence split points (compound sentence decomposition)
_COMPOUND_SPLIT = re.compile(
    r"(?:,\s+and\s+|;\s+|,\s+which\s+|,\s+where\s+|,\s+while\s+|"
    r",\s+although\s+|,\s+making\s+|,\s+producing\s+|,\s+giving\s+)",
    re.IGNORECASE,
)

# Detect if a sentence fragment has a verb (simple heuristic)
_HAS_VERB = re.compile(
    r"\b(?:is|are|was|were|has|have|had|produces?|grows?|makes?|contains?|"
    r"requires?|includes?|covers?|spans?|lies|located|situated|established|"
    r"founded|known|classified|designated|recognized|permitted|allowed|"
    r"planted|cultivated|aged|fermented|produced|blended|harvested|"
    r"borders?|extends?|encompasses|comprises?|consists?|became|became|"
    r"began|started|introduced|adopted|created|developed|expanded|"
    r"exports?|imports?|receives?|ranges?|averages?|reaches?|exceeds?|"
    r"represents?|accounts?|dominates?|features?|specializ\w+|"
    r"can|must|may|should|will|would|could|shall)\b",
    re.IGNORECASE,
)

# ─── Domain Classification ───────────────────────────────────────────────────

# Keywords mapped to domains (checked in priority order)
_DOMAIN_KEYWORDS = {
    "grape_varieties": {
        "grape", "grapes", "variety", "varieties", "varietal", "cultivar",
        "clone", "clones", "rootstock", "rootstocks", "vitis", "crossing",
        "vine", "vines", "grapevine", "berry", "berries", "cluster",
        "phenolic", "tannin", "acidity", "sugar", "brix", "ripening",
        "bud", "budburst", "veraison", "harvest date",
        "pinot", "cabernet", "merlot", "chardonnay", "riesling", "syrah",
        "shiraz", "sauvignon", "sangiovese", "nebbiolo", "tempranillo",
        "malbec", "grenache", "mourvèdre", "zinfandel", "gamay",
        "muscat", "moscato", "trebbiano", "barbera", "viognier", "chenin",
        "garnacha", "monastrell", "touriga", "mencía", "albariño",
        "grüner veltliner", "blaufränkisch", "zweigelt", "furmint",
        "xinomavro", "agiorgitiko", "assyrtiko", "saperavi", "rkatsiteli",
        "tannat", "carménère", "bonarda", "torrontés", "país", "criolla",
        "pinotage", "steen", "colombard",
    },
    "producers": {
        "château", "chateau", "domaine", "estate", "winery", "wineries",
        "bodega", "bodegas", "weingut", "cantina", "azienda", "quinta",
        "cave", "caves", "cooperative", "co-operative", "négociant",
        "producer", "producers", "vintner", "winemaker", "founder",
        "founded", "owner", "family", "generation", "generations",
        "bottles", "cases", "production volume", "annual production",
        "brand", "label", "house", "maison",
    },
    "winemaking": {
        "fermentation", "fermented", "maceration", "malolactic",
        "barrel", "barrels", "oak", "barrique", "tonneau", "foudre",
        "aging", "ageing", "maturation", "lees", "bâtonnage",
        "chaptalisation", "chaptalization", "fining", "filtration",
        "bottling", "bottled", "blending", "blend", "cuvée", "assemblage",
        "vinification", "pressing", "press", "must", "pomace",
        "yeast", "yeasts", "residual sugar", "dosage", "disgorgement",
        "riddling", "remuage", "méthode", "method", "traditional method",
        "charmat", "tank", "stainless steel", "concrete", "amphora",
        "carbonic", "whole cluster", "destemming", "crush", "cold soak",
        "punch down", "pump over", "racking", "sulfur", "sulfite",
        "stabilization", "clarification",
    },
    "viticulture": {
        "viticulture", "viticultural", "terroir", "soil", "soils",
        "climate", "microclimate", "mesoclimate", "altitude", "elevation",
        "slope", "aspect", "exposure", "rainfall", "temperature",
        "continental", "maritime", "mediterranean", "diurnal",
        "limestone", "clay", "chalk", "gravel", "sand", "schist",
        "slate", "granite", "volcanic", "alluvial", "loess", "marl",
        "calcareous", "siliceous", "basalt", "tufa",
        "pruning", "trellising", "canopy", "irrigation", "dry-farmed",
        "organic", "biodynamic", "sustainable", "integrated pest",
        "phylloxera", "grafting", "grafted", "ungrafted",
        "yield", "yields", "hectoliters per hectare", "hl/ha",
        "planting density", "vine age", "old vines", "vieilles vignes",
        "growing season", "frost", "hail", "drought",
        "hectare", "hectares", "acre", "acres", "vineyard area",
    },
    "wine_business": {
        "export", "exports", "import", "imports", "market", "trade",
        "consumption", "sales", "revenue", "price", "pricing",
        "classification", "reclassification", "regulation", "regulations",
        "law", "laws", "decree", "legislation", "council",
        "consortium", "consorzio", "interprofessional", "board",
        "tourism", "wine tourism", "enotourism", "cellar door",
        "route", "wine route", "wine trail",
        "certification", "certified", "audit", "inspection",
        "label", "labeling", "labelling", "protected",
        "economic", "economy", "industry", "sector",
        "million", "billion", "per capita", "consumption per",
    },
    # wine_regions is the fallback — no keyword list needed
}

# Pre-compile keyword patterns per domain for fast matching
_DOMAIN_PATTERNS = {}
for _domain, _keywords in _DOMAIN_KEYWORDS.items():
    _pattern = re.compile(
        r"\b(?:" + "|".join(
            re.escape(kw) for kw in sorted(_keywords, key=len, reverse=True)
        ) + r")\b",
        re.IGNORECASE,
    )
    _DOMAIN_PATTERNS[_domain] = _pattern


# ─── Core Functions ──────────────────────────────────────────────────────────


def decompose_sentence(sentence: str, subject: str) -> list[str]:
    """Split a compound sentence into atomic facts.

    Each fragment is capped at MAX_FACT_WORDS words. Fragments that lose
    their subject get it prepended.

    Args:
        sentence: The compound sentence to decompose.
        subject: The topic entity (e.g., "Barolo", "Château Margaux").

    Returns:
        List of atomic fact strings.
    """
    sentence = sentence.strip()
    if not sentence:
        return []

    words = sentence.split()
    # If already short enough and atomic, return as-is
    if len(words) <= MAX_FACT_WORDS and not _COMPOUND_SPLIT.search(sentence):
        return [sentence]

    # Split at compound boundaries
    parts = _COMPOUND_SPLIT.split(sentence)
    results = []

    for i, part in enumerate(parts):
        part = part.strip().rstrip(",;")
        if not part:
            continue

        # Resolve dangling references first (e.g., "it requires" -> "Barolo requires")
        part = resolve_references(part, subject)

        # If still doesn't start with an entity (after ref resolution), prepend subject
        if i > 0 and not _starts_with_entity(part):
            part = f"{subject} {_lowercase_start(part)}"

        # Truncate if still too long (take first MAX_FACT_WORDS words, end at sentence boundary if possible)
        words = part.split()
        if len(words) > MAX_FACT_WORDS:
            part = " ".join(words[:MAX_FACT_WORDS])
            # Try to end at a natural boundary
            for end_char in (".", ",", ";"):
                idx = part.rfind(end_char)
                if idx > len(part) // 2:
                    part = part[:idx + 1].rstrip(",;")
                    break

        # Ensure ends with period
        if part and not part.endswith((".","!", "?")):
            part = part.rstrip(",;:") + "."

        if part and len(part.split()) >= MIN_FACT_WORDS:
            results.append(part)

    return results if results else [sentence] if len(sentence.split()) <= MAX_FACT_WORDS else []


def resolve_references(sentence: str, subject: str) -> str:
    """Replace leading pronouns/dangling references with the explicit subject.

    Args:
        sentence: Text that may start with "It", "They", etc.
        subject: The entity name to substitute in.

    Returns:
        Sentence with resolved references.
    """
    if not sentence or not subject:
        return sentence

    match = _DANGLING_STARTS.match(sentence)
    if not match:
        return sentence

    pronoun = match.group(1)
    rest = sentence[match.end():].lstrip()

    # Handle "The estate" -> "Château Margaux" (drop article-noun combos)
    if pronoun.lower().startswith("the "):
        return f"{subject} {rest}"

    # Handle "It is" -> "Barolo is", "They produce" -> "The producers produce"
    return f"{subject} {rest}"


def classify_domain(fact_text: str) -> str:
    """Classify a fact into a wine domain based on keyword matching.

    Checks domains in priority order. Falls back to 'wine_regions'.

    Args:
        fact_text: The fact text to classify.

    Returns:
        One of: grape_varieties, producers, winemaking, viticulture,
        wine_business, wine_regions.
    """
    # Count keyword hits per domain
    scores: dict[str, int] = {}
    for domain, pattern in _DOMAIN_PATTERNS.items():
        hits = len(pattern.findall(fact_text))
        if hits > 0:
            scores[domain] = hits

    if not scores:
        return "wine_regions"

    # Return domain with most keyword hits
    return max(scores, key=scores.get)


def validate_fact(fact_text: str) -> tuple[bool, str]:
    """Validate that a fact meets quality criteria.

    Returns:
        (is_valid, reason) — reason is empty string if valid.
    """
    if not fact_text or not fact_text.strip():
        return False, "empty"

    text = fact_text.strip()
    words = text.split()

    # Length checks
    if len(words) < MIN_FACT_WORDS:
        return False, f"too_short ({len(words)} words)"
    if len(words) > MAX_FACT_WORDS:
        return False, f"too_long ({len(words)} words)"

    # Must contain a verb
    if not _HAS_VERB.search(text):
        return False, "no_verb"

    # No unresolved pronouns at start
    if _DANGLING_STARTS.match(text):
        return False, f"dangling_reference ({_DANGLING_STARTS.match(text).group(1)})"

    # Not just an entity name (must have predicate structure)
    if not any(c in text for c in ".!?,;:"):
        # Check it's not just a noun phrase
        if len(words) < 7 and not _HAS_VERB.search(text):
            return False, "no_predicate"

    return True, ""


def is_on_topic(fact_text: str, region_keywords: set[str]) -> bool:
    """Check if a fact is relevant to the expected region/topic.

    Args:
        fact_text: The fact to check.
        region_keywords: Set of lowercase keywords that indicate on-topic
            content (e.g., {"bordeaux", "gironde", "médoc", "saint-émilion"}).

    Returns:
        True if the fact appears on-topic or is neutral (no conflicting region).
    """
    if not region_keywords:
        return True

    text_lower = fact_text.lower()

    # If any target keyword is present, it's on-topic
    for kw in region_keywords:
        if kw in text_lower:
            return True

    # Check for off-topic region indicators (other major wine regions)
    _OFF_TOPIC_REGIONS = {
        "burgundy", "bourgogne", "champagne", "alsace", "loire",
        "rhône", "rhone", "provence", "languedoc", "roussillon",
        "piedmont", "piemonte", "tuscany", "toscana", "veneto",
        "rioja", "ribera del duero", "priorat", "jerez", "sherry",
        "mosel", "rheingau", "pfalz", "baden", "franken",
        "barossa", "hunter valley", "marlborough", "hawke's bay",
        "napa", "sonoma", "willamette", "finger lakes",
        "mendoza", "maipo", "stellenbosch", "constantia",
        "tokaj", "wachau", "douro", "alentejo",
    }

    # Only flag as off-topic if an off-topic region is mentioned
    # AND no target keyword is present
    for region in _OFF_TOPIC_REGIONS:
        if region in text_lower:
            return False

    # Neutral — no region indicators either way
    return True


def process_facts(
    raw_texts: list[str],
    subject: str,
    region_keywords: Optional[set[str]] = None,
    default_domain: Optional[str] = None,
) -> list[dict]:
    """Full processing pipeline: decompose → resolve → classify → validate → filter.

    Args:
        raw_texts: Raw sentences/text blocks to process.
        subject: The topic entity for reference resolution.
        region_keywords: Optional set of keywords for on-topic filtering.
        default_domain: If set, override classify_domain for all facts.

    Returns:
        List of dicts with keys: fact_text, domain.
        (Caller adds source_id, subdomain, entities, etc.)
    """
    results = []
    seen = set()

    for text in raw_texts:
        # Decompose compound sentences
        atoms = decompose_sentence(text, subject)

        for atom in atoms:
            # Resolve any remaining dangling references
            atom = resolve_references(atom, subject)

            # Validate
            valid, reason = validate_fact(atom)
            if not valid:
                continue

            # On-topic filter
            if region_keywords and not is_on_topic(atom, region_keywords):
                continue

            # Dedup within this batch
            norm = atom.lower().strip()
            if norm in seen:
                continue
            seen.add(norm)

            # Classify domain
            domain = default_domain if default_domain else classify_domain(atom)

            results.append({
                "fact_text": atom,
                "domain": domain,
            })

    return results


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _starts_with_entity(text: str) -> bool:
    """Check if text starts with a capitalized word (likely an entity name)."""
    if not text:
        return False
    # Starts with uppercase letter (not a pronoun from our dangling list)
    if text[0].isupper() and not _DANGLING_STARTS.match(text):
        return True
    return False


def _lowercase_start(text: str) -> str:
    """Lowercase the first character if it's an uppercase non-proper-noun start."""
    if not text:
        return text
    # Don't lowercase if it looks like a proper noun (followed by more uppercase)
    if len(text) > 1 and text[1].isupper():
        return text
    return text[0].lower() + text[1:]
