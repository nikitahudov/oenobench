"""
OenoBench — Stratified fact sampling from PostgreSQL.

Selects facts for question generation with source diversity,
confidence filtering, and support for comparative / cluster queries.
"""

import os
import re
import threading
from collections import defaultdict
from functools import lru_cache

from loguru import logger

from src.utils.db import get_pg

# ─── Fact quality filters ─────────────────────────────────────────────────────

# Patterns that indicate vague, subjective, or marketing-style facts.
#
# The first block lists original marketing/superlative phrasings.  The second
# block (added 2026-04-19, plan §9) extends the regex with phrasings the
# domain expert flagged on the gold sheet that the original patterns missed —
# ambiguous demonstratives, hedging language, "best matches" matchers,
# external-document references, and quoted "Other" used as a slot label.
_VAGUE_PATTERNS = re.compile(
    r"("
    # ── Original marketing / superlative phrasings ──
    r"\b(?:highly regarded|world-famous|renowned|prestigious|legendary|iconic|"
    r"intriguing|fascinating|exceptional|extraordinary|outstanding|"
    r"best known|most famous|widely celebrated|greatly admired|"
    r"discover the|visit our|come and|join us|book now|must-visit|"
    r"one of the (?:best|finest|greatest|most important|most)|"
    r"is famous for its|is known for its quality|"
    # ── v2.3 Phase F additions — harvested from human gold notes and
    # audit-run-3 B2 leakage patterns. Only phrasings NOT already caught
    # by the original superlative vocabulary above are listed here.
    # "known/acclaimed for producing" — marketing phrasing around production
    r"is known for producing|known for producing|acclaimed for producing|"
    # "world-class" / "world class" — marketing superlative
    r"world[- ]class|"
    # "highly prized" / "highly sought(-after)" — value-judgement language
    r"highly prized|highly sought[- ]after|sought[- ]after|"
    # "distinguished by its" — precedes a marketing description
    r"distinguished by its|"
    # "celebrated for" — synonym of "famous for"
    r"celebrated for|"
    # "premier appellation" / "premier wine region" — branding, not technical
    # (intentionally NOT bare "premier" — keeps "Premier Cru" usable)
    r"premier appellation|premier wine region|premier growing region)\b"
    # ── Gold-sheet review additions (no_vague_language flagged rows) ──
    # Ambiguous demonstrative referents — "these wines", "this wine" with no
    # in-stem antecedent. v2.2 fix #4: removed 'producers' from the "these X"
    # list (gold-v1 FP: scenarios naming three producers establish antecedent).
    r"|\bthese\s+(?:wines?|bordeaux\s+wines?|grapes?|appellations?|regions?)\b"
    r"|\bthis\s+wine\b"
    # Soft hedging that signals the stem doesn't actually use the source fact.
    # v2.2 fix #4: narrowed "is considered the" — original caught "considered
    # the origin of X" which IS factual. Now requires a vague superlative to
    # follow (best/finest/top/most X).
    r"|\b(?:is|are)\s+considered\s+(?:the|to\s+be)\s+(?:best|finest|top|most\s+\w+|greatest|leading|premier)\b"
    r"|\b(?:is|are)\s+said\s+to\b"
    # "best matches this scenario" / "best matches the description" — vague
    # matching language that obscures what the question actually asks.
    r"|\bbest\s+matches\s+(?:this\s+scenario|the\s+description|this\s+description)\b"
    # External-document references the test-taker can't see.
    r"|\b(?:procedures|guidelines|methods|techniques|protocol|protocols)\s+discussed\s+in\b"
    r"|\bas\s+discussed\s+in\b"
    # Vague catch-all slot labels like 'Other' used as a region / category /
    # appellation in scenario stems.
    r"|['\"]Other['\"]\s+(?:region|area|category|appellation|zone)"
    r")",
    re.IGNORECASE,
)

# Blend categories that are NOT grape varieties — facts treating these as
# varieties produce misleading questions ("Which variety is grown in X?")
_BLEND_CATEGORIES = re.compile(
    r"\b("
    r"Red Blend|White Blend|Rosé Blend|Sparkling Blend|"
    r"Portuguese Red|Portuguese White|"
    r"Rhône Red Blend|Rhône White Blend|"
    r"Bordeaux-style Red Blend|"
    r"Austrian Red Blend|Austrian [Ww]hite [Bb]lend|"
    r"Champagne Blend"
    r")\b",
    re.IGNORECASE,
)
_BLEND_AS_VARIETY = re.compile(
    r"\b("
    # "X Blend is grown/produced in Y"
    r"(Red|White|Rosé|Sparkling|Champagne|Austrian\s+\w+|Bordeaux-style\s+\w+|Rhône\s+\w+)\s+Blend"
    r"|Portuguese (Red|White)"
    r")\b.{0,30}\b(is grown|is commonly produced|is planted)\b"
    # "most widely reviewed variety in X is Red Blend"
    r"|(most widely reviewed|most planted|most common) variety .{0,40}\b("
    r"Red Blend|White Blend|Rosé Blend|Portuguese Red|Portuguese White"
    r")\b",
    re.IGNORECASE,
)

# Minimum word count for a fact to be specific enough
_MIN_SPECIFIC_WORDS = 8


# ── Lever B2 (2026-04-28): pre-flight fact substantiveness predicate ─────
#
# Audit pilot v8 hit ~99% LLM-rejection, dominated by
# {"skip": true, "reason": "fact lacks technical depth / world-knowledge
# solvable / no entity name"} verdicts. Many of those facts are predictable
# from text alone (geographical containment, single-noun entries). Pre-
# screening saves the LLM round-trip.
#
# Rule: a fact is SUBSTANTIVE iff at least one of:
#   - contains ≥1 numeric token (digits/percentages/decimals/years), OR
#   - contains ≥1 4+-syllable wine-technical term from the curated list, OR
#   - contains ≥1 multi-word proper-noun construction not in the iconic set.
# Otherwise FAIL.
#
# Gated behind OENOBENCH_FACT_SUBSTANTIVE_FILTER env var (default OFF) so
# v8 audit runs reproduce byte-for-byte.

_FACT_SUBSTANTIVE_ENV_VAR = "OENOBENCH_FACT_SUBSTANTIVE_FILTER"

# Phase 2g.15 (Team C): iconic-exhaust fallback counter.
# Incremented each time sample_facts() falls back to the non-iconic pool
# because the iconic-filtered candidates were insufficient to fill count.
_ICONIC_FALLBACK_COUNT: int = 0


def get_iconic_fallback_count() -> int:
    """Return how many times the iconic-exhaust fallback fired this process."""
    return _ICONIC_FALLBACK_COUNT


def reset_iconic_fallback_count() -> None:
    """Reset the iconic-exhaust fallback counter (useful in tests)."""
    global _ICONIC_FALLBACK_COUNT
    _ICONIC_FALLBACK_COUNT = 0


_NUMERIC_TOKEN_RE = re.compile(r"\d")

_TECHNICAL_TERMS = frozenset(t.lower() for t in [
    "appellation", "viticulture", "vinification", "assemblage",
    "phylloxera", "chaptalisation", "chaptalization", "malolactic",
    "botrytis", "terroir", "vendange", "palissage", "enjambeur",
    "méthode", "methode", "fermentation", "clarification",
    "débourbage", "debourbage", "bâtonnage", "batonnage", "garrigue",
    "solera", "criadera", "flor", "oxidative", "reductive",
    "pied de cuve", "selected indigenous", "whole-bunch", "cold soak",
    "extended maceration", "microoxygenation", "micro-oxygenation",
    "latitude", "altitude", "precipitation", "humidity",
])

_MULTIWORD_PROPER_NOUN_RE = re.compile(
    r"\b[A-ZÀ-Ý][a-zà-ÿ]+(?:[ -][A-ZÀ-Ý][a-zà-ÿ]+){1,}\b"
)


def _is_fact_substantive(fact_text: str) -> bool:
    """Lever B2 pre-flight predicate.

    Returns True iff the fact has SOMETHING the LLM can't guess from
    surface text alone: a number, a wine-technical term, or a multi-word
    proper noun that isn't on the iconic list.

    Cheap (regex + set membership only), deterministic, no LLM/DB calls.
    Used as an opt-in pre-screen behind the OENOBENCH_FACT_SUBSTANTIVE_FILTER
    env var.
    """
    if not fact_text:
        return False
    text = fact_text

    # 1) Any digit at all — covers years, percentages, decimals, hectares.
    if _NUMERIC_TOKEN_RE.search(text):
        return True

    # 2) Curated wine-technical term — substring match on lowercased copy.
    lowered = text.lower()
    if any(term in lowered for term in _TECHNICAL_TERMS):
        return True

    # 3) Multi-word proper noun not on the iconic list. We require at
    #    least one such construction whose lowercased form is NOT iconic.
    iconic = _load_iconic_entities()
    for match in _MULTIWORD_PROPER_NOUN_RE.findall(text):
        if match.strip().lower() not in iconic:
            return True

    return False


# ─── Phase 2g.16 — grape-variety name validity filter ────────────────────────
#
# v14b gold review found 3/13 (23%) failing templates were caused by garbage
# entity names in grape_varieties facts (extracted scraper-side):
#   * "457 grape variety"             — pure number (probably a row index)
#   * "55% white varieties"           — regulation rule misextracted as a name
#   * "Champagne Blend"               — vague category, not a specific cultivar
#
# These pass _is_fact_substantive() because the surrounding fact text contains
# a multi-word proper noun (e.g. "New Zealand wine") and/or numeric tokens.
# This filter checks the EXTRACTED grape-variety NAME and rejects obvious
# malformations. Cheap regex-only — no LLM/DB calls.
_GRAPE_NAME_EXTRACTION_PATTERNS = (
    re.compile(r"permits the (.+?) grape variety", re.I),
    re.compile(r"^(.+?) is a widely reviewed grape variety", re.I),
    re.compile(r"^(.+?) is a cultivated grape variety", re.I),
    re.compile(r"^(.+?) is a grape variety", re.I),
)

_GRAPE_NAME_INVALID_PATTERNS = (
    re.compile(r"^\d+(\.\d+)?$"),                 # Pure number
    re.compile(r"%"),                             # Contains percent
    re.compile(r"\bvarieties\b", re.I),           # Plural/generic
    re.compile(
        r"^(Champagne|Local|Native|Indigenous|"
        r"Rare|White|Red|Generic|Mixed|Other)\s+(Blend|varieties?|grapes?)$",
        re.I,
    ),
)

_GRAPE_NAME_FILTERED_COUNT = 0


def get_grape_name_filtered_count() -> int:
    """Return how many facts were rejected by the grape-name validity filter."""
    return _GRAPE_NAME_FILTERED_COUNT


def reset_grape_name_filtered_count() -> None:
    """Reset the grape-name-filter counter (used in tests)."""
    global _GRAPE_NAME_FILTERED_COUNT
    _GRAPE_NAME_FILTERED_COUNT = 0


def _extract_grape_name(fact_text: str) -> str | None:
    """Extract the apparent grape-variety name from a fact_text using common
    fact patterns. Returns the matched name (whitespace-trimmed) or None when
    no pattern matched.
    """
    if not fact_text:
        return None
    for pat in _GRAPE_NAME_EXTRACTION_PATTERNS:
        m = pat.search(fact_text)
        if m:
            return m.group(1).strip()
    return None


def _is_grape_fact_valid(fact_text: str) -> bool:
    """Return False if the fact's extracted grape-variety name is malformed
    (a pure number, regulation-percentage rule, or vague generic blend).

    When no name pattern matches the fact, returns True (don't over-block —
    the fact may be using a phrasing this filter doesn't recognise; let
    other guards decide).
    """
    name = _extract_grape_name(fact_text)
    if name is None:
        return True
    return not any(p.search(name) for p in _GRAPE_NAME_INVALID_PATTERNS)


# ─── Phase 2g.17 — ubiquitous-grape ambiguity guard ──────────────────────────
#
# Wine-expert v14c gold review found 4/15 templates with ambiguity flags on
# Cabernet Sauvignon "find-the-region" stems. Cabernet is grown in 50+ regions
# worldwide; "Which region produces Cabernet Sauvignon?" has many valid
# answers, making the question ambiguous. Cross-strategy audit confirmed
# fact_to_question + comparative are equally exposed. This guard rejects
# ubiquitous-grape facts when the calling strategy needs a unique-answer region.

_UBIQUITOUS_INTERNATIONAL_GRAPES = frozenset({
    "cabernet sauvignon",
    "chardonnay",
    "merlot",
    "pinot noir",
    "sauvignon blanc",
    "syrah",
    "shiraz",
    "riesling",
})

_UBIQUITY_DATA_DRIVEN_THRESHOLD = 30  # any grape appearing in > N facts is "de-facto" ubiquitous

_UBIQUITOUS_GRAPE_NAMES_CACHE: set[str] | None = None

_UBIQUITY_FILTERED_COUNT = 0


def _normalise_grape_name(name: str) -> str:
    """Lowercase + strip + collapse whitespace + drop common diacritics."""
    import unicodedata
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    return " ".join(s.lower().split())


def _build_ubiquitous_grape_set() -> set[str]:
    """Build the merged ubiquity set: curated international grapes + any
    grape appearing in > _UBIQUITY_DATA_DRIVEN_THRESHOLD facts in the DB.
    Runs ONE SQL query the first time it's called per process; cached after.
    """
    merged: set[str] = set(_UBIQUITOUS_INTERNATIONAL_GRAPES)
    try:
        conn = get_pg()
        cur = conn.cursor()
        # Use _extract_grape_name on every fact_text — pure-Python regex,
        # one DB pass, then group in Python.
        cur.execute(
            "SELECT fact_text FROM facts WHERE domain = 'grape_varieties' "
            "AND fact_text IS NOT NULL"
        )
        from collections import Counter
        counts: Counter[str] = Counter()
        for row in cur.fetchall():
            name = _extract_grape_name(row["fact_text"])
            if name:
                counts[_normalise_grape_name(name)] += 1
        added = {g for g, c in counts.items() if c > _UBIQUITY_DATA_DRIVEN_THRESHOLD}
        for g in sorted(added - _UBIQUITOUS_INTERNATIONAL_GRAPES):
            logger.info("ubiquity index: adding data-driven grape '{}' (count={})", g, counts[g])
        merged |= added
    except Exception as e:  # pragma: no cover — defensive
        logger.warning("ubiquity index: DB query failed, falling back to curated set: {}", e)
    return merged


def _get_ubiquitous_grape_names() -> set[str]:
    global _UBIQUITOUS_GRAPE_NAMES_CACHE
    if _UBIQUITOUS_GRAPE_NAMES_CACHE is None:
        _UBIQUITOUS_GRAPE_NAMES_CACHE = _build_ubiquitous_grape_set()
    return _UBIQUITOUS_GRAPE_NAMES_CACHE


def is_ubiquitous_grape_name(name: str) -> bool:
    """Public predicate: is this grape variety globally ubiquitous (Cabernet,
    Chardonnay, etc.) — and therefore unsuitable as the question variable in
    'find-the-region' templates?"""
    if not name:
        return False
    return _normalise_grape_name(name) in _get_ubiquitous_grape_names()


def get_ubiquity_filtered_count() -> int:
    return _UBIQUITY_FILTERED_COUNT


def reset_ubiquity_filtered_count() -> None:
    global _UBIQUITY_FILTERED_COUNT
    _UBIQUITY_FILTERED_COUNT = 0


def _fact_has_ubiquitous_grape(fact_text: str) -> bool:
    """Convenience: True if the fact's extracted grape name is in the ubiquity set."""
    name = _extract_grape_name(fact_text)
    if name is None:
        return False
    return is_ubiquitous_grape_name(name)


def _should_apply_iconic_filter(strategy: str | None) -> bool:
    """Lever B2: apply the iconic-only filter for every strategy that
    passes a non-None value to ``sample_facts``. Multi-fact strategies
    that don't go through ``sample_facts`` (comparative/scenario) still
    use ``_bundle_has_non_iconic_anchor`` on their bundles separately.
    """
    return strategy is not None


def _is_fact_specific(fact_text: str) -> bool:
    """Check if a fact is specific enough for question generation.

    Rejects vague, subjective, or marketing-style facts, and facts
    that misclassify blend categories as grape varieties.
    """
    if len(fact_text.split()) < _MIN_SPECIFIC_WORDS:
        return False
    if _VAGUE_PATTERNS.search(fact_text):
        return False
    if _BLEND_AS_VARIETY.search(fact_text):
        return False
    return True


# Patterns that indicate a fact is purely geographic with no wine-specific content.
# These are fine for simple fact-to-question but useless for comparative/scenario/distractor.
_THIN_GEO_PATTERNS = re.compile(
    r"^("
    # "X is a wine region in Y" / "X is a wine-producing region in Y"
    r".{3,80} is a (wine[- ]producing |wine )(region|area|commune|zone|village|town) in .+|"
    # "X is a wine-producing area within the Y region of Z"
    r".{3,80} is a wine[- ]producing area within .+|"
    # "X covers approximately N hectares"
    r".{3,80} covers approximately [\d,.]+ hectares\.?|"
    # "X is a classified cru village in Y"
    r".{3,80} is a classified cru (village|commune) in .+|"
    # "X wine region is located in Y"
    r".{3,80} wine region is located in .+|"
    # "X is an AOC/DOC/DOCG appellation in Y" (no additional detail)
    r".{3,80} is an? (AOC|DOC|DOCG|AOP|IGT|IGP) appellation in .+"
    r")$",
    re.IGNORECASE,
)

# Signals that a fact contains substantive wine content beyond geography
_WINE_CONTENT_SIGNALS = re.compile(
    r"\b("
    # Grape varieties / winemaking
    r"grape|varietal|blend|ferment|aged?ing|barrel|oak|tank|vintage|harvest|"
    r"vinification|maceration|malolactic|lees|riddling|dosage|"
    # Classifications
    r"DOC[G]?|AOC|AOP|AVA|IGT|IGP|VdP|Prädikat|Spätlese|Auslese|Kabinett|"
    r"Grand Cru|Premier Cru|Cru Classé|Reserva|Riserva|"
    # Tasting / sensory
    r"tannin|acidity|residual sugar|alcohol|body|aroma|bouquet|palate|finish|"
    # Viticulture
    r"rootstock|canopy|trellising|pruning|yield|clone|phylloxera|terroir|"
    r"limestone|clay|chalk|schist|slate|gravel|loam|"
    # Regulations / winemaking terms
    r"appellation|denomination|regulation|minimum.{1,20}(aging|alcohol|percent)|"
    r"permitted|authorized|required|prohibited|"
    # Numeric wine data (percentages, temperatures, years with context)
    r"\d+\s*%|\d+\s*°[CF]|\d+\s*(months?|years?)\s*(aging|minimum|barrel)"
    r")\b",
    re.IGNORECASE,
)


def _is_fact_rich(fact_text: str) -> bool:
    """Check if a fact has substantive wine content for higher-order strategies.

    Rejects thin geographic facts ("X is a wine region in Y") that lack any
    wine-specific information. These facts are fine for simple fact-to-question
    (Level 1) but produce weak comparative, scenario, and distractor questions.
    """
    # If it matches a thin geographic pattern, check for wine content signals
    if _THIN_GEO_PATTERNS.match(fact_text):
        return False
    # Also reject very short facts even if they don't match patterns
    if len(fact_text.split()) < 12:
        # Short facts need wine content signals to qualify
        return bool(_WINE_CONTENT_SIGNALS.search(fact_text))
    return True


# ─── Wine category classification for distractor filtering ─────────────────

_WINE_CATEGORY_PATTERNS = [
    ("sparkling", re.compile(
        r"\b(sparkling|spumante|mousseux|sekt|cava|champagne|crémant|franciacorta|"
        r"trentodoc|prosecco|méthode\s+(traditionnelle|champenoise|classique)|"
        r"charmat|tank\s+method|riddling|dosage|disgorgement|tirage|"
        r"brut|extra\s+brut|pas\s+dosé|demi-sec)\b", re.I)),
    ("fortified", re.compile(
        r"\b(fortified|port\b|porto\b|sherry|jerez|madeira|marsala|"
        r"vin\s+doux\s+naturel|VDN|banyuls|maury|rivesaltes|muscat\s+de\s+|"
        r"brandy\s+spirit|grape\s+spirit|aguardente|mutage)\b", re.I)),
    ("rosé", re.compile(
        r"\b(rosé|rosato|rosado|blush|vin\s+gris|saignée)\b", re.I)),
    ("white", re.compile(
        r"\b(white\s+wine|white\s+grape|bianco|blanc\b|weisswein|weißwein|"
        r"chardonnay|sauvignon\s+blanc|riesling|pinot\s+grigio|pinot\s+gris|"
        r"gewürztraminer|viognier|grüner\s+veltliner|albariño|garganega|"
        r"vermentino|trebbiano|cortese|arneis|moscato)\b", re.I)),
    ("red", re.compile(
        r"\b(red\s+wine|red\s+grape|rosso|rouge\b|rotwein|"
        r"cabernet\s+sauvignon|merlot|pinot\s+noir|syrah|shiraz|"
        r"nebbiolo|sangiovese|tempranillo|grenache|garnacha|mourvèdre|"
        r"malbec|barbera|touriga|aglianico|montepulciano\s+grape|"
        r"primitivo|zinfandel|carménère)\b", re.I)),
]


def _classify_wine_category(fact_text: str) -> str | None:
    """Classify a fact's wine category (sparkling, red, white, rosé, fortified).

    Returns the first matching category, or None if no category is detectable.
    Used to ensure distractor facts are about the same type of wine as the target.
    """
    for cat_name, pattern in _WINE_CATEGORY_PATTERNS:
        if pattern.search(fact_text):
            return cat_name
    return None


# ─── Dimension classification for comparative pairing ────────────────────────

_DIMENSION_PATTERNS = [
    ("aging_requirements", re.compile(
        r"(minimum|required|must|obligatory).{0,30}(aging|aged|matured|months|years|elevage)", re.I)),
    ("permitted_varieties", re.compile(
        r"(permit|permitted|permits|authorized|allowed|approved|principal|dominant).{0,20}(variet|grape|cultivar|cépage)", re.I)),
    ("soil_geology", re.compile(
        r"\b(soil|limestone|clay|chalk|schist|slate|gravel|loam|volcanic|alluvial|marl|granite|sandstone|terroir|calcareous|flint|silex|galestro|tufa)\b", re.I)),
    ("climate", re.compile(
        r"\b(climate|temperature|rainfall|precipitation|continental|maritime|Mediterranean|altitude|elevation|frost|diurnal|growing season|degree.days)\b", re.I)),
    ("area_size", re.compile(
        r"\d[\d,.]*\s*(hectares|ha|acres|km²|km2|square)", re.I)),
    ("production_volume", re.compile(
        r"\d[\d,.]*\s*(hectoliters|hl|bottles|cases|tons|tonnes|liters|litres)", re.I)),
    ("alcohol_level", re.compile(
        r"\d+\.?\d*\s*%?\s*(alcohol|ABV|vol|minimum alcohol)", re.I)),
    ("classification", re.compile(
        r"\b(DOCG|DOC|AOC|AOP|IGT|IGP|Grand Cru|Premier Cru|Cru Classé|Cru Bourgeois|classified|classification|Prädikat|Spätlese|Auslese|Kabinett|Grosses Gewächs|Erste Lage)\b", re.I)),
    ("history_founding", re.compile(
        r"(founded|established|first planted|dating back|origins|history|traces.{0,10}back).{0,30}(\d{3,4}|century)", re.I)),
    ("winemaking_technique", re.compile(
        r"\b(ferment|maceration|barrel.{0,5}(aged|aging)|oak|stainless.steel|lees|malolactic|riddling|dosage|vinification|carbonic|pressing|destemm|whole.cluster|cold.soak|bâtonnage)\b", re.I)),
    ("tasting_profile", re.compile(
        r"\b(aroma|bouquet|palate|finish|tannin|acidity|body|flavor|nose|fruit|mineral|spice|floral|herbaceous|earthy|structure)\b", re.I)),
    ("yield_regulation", re.compile(
        r"(yield|hectoliter.{0,10}hectare|hl/ha|maximum.{0,15}yield|rendement)", re.I)),
    ("grape_characteristics", re.compile(
        r"(early.{0,5}ripening|late.{0,5}ripening|thick.{0,5}skin|thin.{0,5}skin|vigor|bud.break|veraison|phenolic|berry.size|cluster.size)", re.I)),
    ("economic_market", re.compile(
        r"\b(price|market|export|import|revenue|sales|consumer|demand|value|trade|auction|en primeur)\b", re.I)),
    ("blend_composition", re.compile(
        r"(\d+\s*%\s*(minimum|maximum|at least|up to).{0,20}(blend|composition|assemblage|cuvée)|\d+\s*%\s+\w+\s+(grape|variety))", re.I)),
]


def _classify_dimension(fact_text: str) -> str | None:
    """Classify a fact into a semantic dimension for comparative pairing.

    Returns the first matching dimension label, or None if unclassifiable.
    Dimensions represent the attribute/aspect a fact discusses, enabling
    pairing of facts that talk about the SAME thing for different entities.
    """
    for dim_name, pattern in _DIMENSION_PATTERNS:
        if pattern.search(fact_text):
            return dim_name
    return None


_NUMERIC_RE = re.compile(
    r'([\d,]+\.?\d*)\s*(hectares|ha|years|months|%|hectoliters|hl|bottles|°[CF]|km|acres|liters|litres)',
    re.I,
)


def _extract_numeric_values(fact_text: str) -> list[tuple[float, str]]:
    """Extract (value, unit) tuples from a fact for most_least comparison."""
    results = []
    for match in _NUMERIC_RE.finditer(fact_text):
        try:
            val = float(match.group(1).replace(",", ""))
            unit = match.group(2).lower()
            if unit == "ha":
                unit = "hectares"
            if unit == "hl":
                unit = "hectoliters"
            results.append((val, unit))
        except ValueError:
            continue
    return results


def _auto_comparison_type(
    dim_a: str | None,
    dim_b: str | None,
    text_a: str,
    text_b: str,
) -> str:
    """Auto-select comparison type based on fact content.

    - Both numeric dimensions + same unit -> most_least
    - Same dimension -> same_vs_different
    - Different/unknown dimensions -> which_one
    """
    _NUMERIC_DIMS = {"area_size", "production_volume", "alcohol_level", "yield_regulation"}

    if dim_a in _NUMERIC_DIMS and dim_b in _NUMERIC_DIMS and dim_a == dim_b:
        nums_a = _extract_numeric_values(text_a)
        nums_b = _extract_numeric_values(text_b)
        if nums_a and nums_b:
            units_a = {u for _, u in nums_a}
            units_b = {u for _, u in nums_b}
            if units_a & units_b:
                return "most_least"

    if dim_a is not None and dim_a == dim_b:
        return "same_vs_different"

    return "which_one"


# ─── Domain question targets (for quota tracking) ───────────────────────────

DOMAIN_TARGETS = {
    "wine_regions": 3500,
    "winemaking": 2000,
    "viticulture": 1500,
    "grape_varieties": 1200,
    "wine_business": 1000,
    "producers": 800,
}


# ─── Per-country quota (D3 SkewAudit fix, plan §3) ──────────────────────────
#
# Strategy: maintain a session-level per-country usage counter; when sampling
# returns a fact, increment the counter for the fact's country. At sampling
# time, weight candidates by `min(1.0, target_share / max(used_share, eps))`
# so over-quota countries get drawn less. Hard cap: never return a fact whose
# country has already reached `1.5 × target_share × total_returned`.
#
# The fact-base distribution is computed lazily once per process; the usage
# counter resets on module import.

_COUNTRY_QUOTA_HARD_CAP_RATIO = 1.2  # v2.2 fix #3 — tightened 1.5→1.2 after audit run #2 showed 3.38× residual skew


# ── v2.2 fix #11 — Iconic-entity list for FTQ pre-filter ───────────────────
# Loaded lazily from data/iconic_entities.yaml. Facts whose ONLY named entity
# is on this list are DROPPED from FTQ sampling (not from other strategies,
# which can still use iconic entities via multi-fact synthesis).

_ICONIC_CACHE: set[str] | None = None


def _load_iconic_entities() -> set[str]:
    """Read data/iconic_entities.yaml and return a lowercased name set.

    Returns an empty set (and logs a warning) if the file is missing so the
    sampler continues to work in test/dev environments without the YAML.
    """
    global _ICONIC_CACHE
    if _ICONIC_CACHE is not None:
        return _ICONIC_CACHE
    try:
        import yaml  # PyYAML
        from pathlib import Path
        path = Path(__file__).resolve().parents[2] / "data" / "iconic_entities.yaml"
        if not path.exists():
            logger.warning(f"iconic_entities.yaml not found at {path}")
            _ICONIC_CACHE = set()
            return _ICONIC_CACHE
        with path.open() as f:
            data = yaml.safe_load(f) or {}
        names: set[str] = set()
        for _category, entries in data.items():
            if isinstance(entries, list):
                for entry in entries:
                    if isinstance(entry, str) and entry.strip():
                        names.add(entry.strip().lower())
        _ICONIC_CACHE = names
        logger.debug(f"Loaded {len(names)} iconic entities from {path}")
        return _ICONIC_CACHE
    except Exception as e:
        logger.warning(f"Failed to load iconic_entities.yaml: {e}")
        _ICONIC_CACHE = set()
        return _ICONIC_CACHE


def _fact_is_iconic_only(fact: dict) -> bool:
    """Return True iff EVERY named entity on the fact is in the iconic list.

    Used by FTQ sampling to drop world-knowledge-solvable facts. A fact with
    ≥1 non-iconic entity is NOT iconic-only (the non-iconic entity is likely
    the real subject — e.g. "Bordeaux 1855 classified Château Chasse-Spleen"
    is about Chasse-Spleen, not Bordeaux 1855).
    """
    iconic = _load_iconic_entities()
    if not iconic:
        return False
    entities = fact.get("entities") or []
    parsed = _parse_entities(entities) if not isinstance(entities, list) else entities
    if not isinstance(parsed, list) or not parsed:
        return False
    names: list[str] = []
    for ent in parsed:
        if not isinstance(ent, dict):
            continue
        nm = (ent.get("name") or ent.get("value") or "").strip().lower()
        if nm:
            names.append(nm)
    if not names:
        return False
    return all(nm in iconic for nm in names)


def _bundle_has_non_iconic_anchor(facts: list[dict]) -> bool:
    """Return True iff ≥1 fact in the bundle has a non-iconic named entity.

    Used by multi-fact strategies (comparative pairs, scenario clusters,
    distractor groups) to guarantee the generated question is anchored in
    at least one fact-specific, non-world-knowledge entity.

    A bundle where EVERY fact is iconic-only is rejected: an LLM handed only
    iconic facts will produce world-knowledge-solvable questions
    ("Compare Château Margaux to Château Latour") — exactly the B2 failure
    pattern we're fixing.

    An entity-less fact (no entities field or empty entities) is treated as
    non-iconic (it can't be world-knowledge-solvable via entity recall) and
    therefore satisfies the anchor requirement.

    Args:
        facts: list of fact dicts (with an ``entities`` field).

    Returns:
        True if the bundle contains ≥1 non-iconic-only fact; False if EVERY
        fact is iconic-only. An empty bundle returns False.
    """
    if not facts:
        return False
    iconic = _load_iconic_entities()
    if not iconic:
        # With no iconic list loaded, we can't reason about iconicity at all
        # — treat every fact as an acceptable anchor (the filter is off).
        return True
    for fact in facts:
        if not _fact_is_iconic_only(fact):
            return True
    return False


# ── v2.2 fix #7 — Multi-category seed-fact filter ──────────────────────────
# Root-cause per sampler predecessor: all 3 C2 category-leak audit failures
# came from scenario_synthesis stems that explicitly compared wine categories
# (red vs white, sparkling vs still). Cluster was category-cohesive BUT the
# SEED FACT TEXT itself mentioned multiple categories. This filter rejects
# such seed facts before cluster building.

_MULTI_CATEGORY_COLOR_RE = re.compile(
    r"\b(?:red\s+(?:and|or|vs\.?|versus)\s+white|"
    r"white\s+(?:and|or|vs\.?|versus)\s+red|"
    r"sparkling\s+(?:and|or|vs\.?|versus)\s+still|"
    r"still\s+(?:and|or|vs\.?|versus)\s+sparkling|"
    r"dry\s+(?:and|or|vs\.?|versus)\s+(?:sweet|fortified)|"
    r"(?:sweet|fortified)\s+(?:and|or|vs\.?|versus)\s+dry|"
    r"red,\s*white,?\s*(?:and|or)\s+(?:rosé|ros\xe9|rose|sparkling))\b",
    re.IGNORECASE,
)


def _fact_has_multi_category_text(fact_text: str) -> bool:
    """Return True if the fact text explicitly enumerates multiple wine
    categories (red AND white, sparkling VS still, etc.). Such facts, when
    used as a scenario cluster seed, produce cross-category stems that fail
    C2 audit. Single-category mentions (e.g. "Barolo is a red wine") return
    False because the other category word doesn't appear.
    """
    return bool(_MULTI_CATEGORY_COLOR_RE.search(fact_text or ""))


_QUOTA_LOCK = threading.Lock()
_COUNTRY_USAGE: dict[str, int] = defaultdict(int)
_TOTAL_RETURNED: int = 0
# v2.3 fix #17 — track the denominator used by the cap. Audit D3 measures
# share over COUNTRY-TAGGED samples only (facts without an extractable country
# are excluded from both numerator and denominator), so the runtime cap must
# use the same denominator or it will be systematically too loose when many
# sampled facts have no country entity. `_TOTAL_RETURNED_TAGGED` counts only
# admissions whose country is non-None.
_TOTAL_RETURNED_TAGGED: int = 0


def _extract_country_from_entities(entities) -> str | None:
    """Return the first ``type='country'`` name from a JSONB entities field.

    Mirrors ``src.qa.agents.team_d_population._extract_country_from_entities``
    so the quota uses the same canonical country labels D3 audits against.
    """
    if not entities:
        return None
    parsed = _parse_entities(entities)
    if not isinstance(parsed, list):
        return None
    for ent in parsed:
        if not isinstance(ent, dict):
            continue
        etype = (ent.get("type") or "").lower()
        name = ent.get("name") or ent.get("value")
        if etype == "country" and name:
            return name
    return None


@lru_cache(maxsize=1)
def _country_base_distribution() -> dict[str, float]:
    """Compute the fact-base country share once per process.

    Returns ``{country_name: share}`` where shares sum to 1.0 over facts that
    have an extractable country entity. Facts without a country entity are
    excluded from both numerator and denominator.
    """
    counts: dict[str, int] = defaultdict(int)
    try:
        conn = get_pg()
        cur = conn.cursor()
        cur.execute("SELECT entities FROM facts WHERE entities IS NOT NULL")
        for row in cur.fetchall():
            country = _extract_country_from_entities(row["entities"])
            if country:
                counts[country] += 1
    except Exception as exc:  # pragma: no cover — defensive
        logger.warning(f"Country distribution query failed ({exc}); quota disabled")
        return {}

    total = sum(counts.values())
    if total == 0:
        return {}
    return {c: n / total for c, n in counts.items()}


def reset_country_usage() -> None:
    """Reset the per-country usage counter (for tests + new generation runs)."""
    global _TOTAL_RETURNED, _TOTAL_RETURNED_TAGGED
    with _QUOTA_LOCK:
        _COUNTRY_USAGE.clear()
        _TOTAL_RETURNED = 0
        _TOTAL_RETURNED_TAGGED = 0


def get_country_usage() -> tuple[dict[str, int], int]:
    """Return a snapshot ``(usage_counter_copy, total_returned)`` for tests.

    ``total_returned`` counts only country-tagged admissions (the audit D3
    denominator). Facts without an extractable country entity are excluded
    from the cap bookkeeping entirely — they don't change any country's
    observed share. ``_TOTAL_RETURNED`` (all admissions, including
    country-less) is still tracked internally for debugging but isn't part
    of the public contract.
    """
    with _QUOTA_LOCK:
        return dict(_COUNTRY_USAGE), _TOTAL_RETURNED_TAGGED


def _record_country_use(country: str | None) -> None:
    """Increment usage counters for a returned fact's country.

    Facts without an extractable country still tick ``_TOTAL_RETURNED`` but
    are excluded from ``_TOTAL_RETURNED_TAGGED`` — that denominator mirrors
    the audit D3 definition, which computes per-country share ONLY over
    country-tagged samples. Using the all-samples denominator makes the cap
    systematically too loose when many sampled facts lack a country entity
    (gold-v3 audit: 85% of sampled facts had no country tag, so the cap was
    effectively ~7× target_share).
    """
    global _TOTAL_RETURNED, _TOTAL_RETURNED_TAGGED
    with _QUOTA_LOCK:
        _TOTAL_RETURNED += 1
        if country:
            _COUNTRY_USAGE[country] += 1
            _TOTAL_RETURNED_TAGGED += 1


# v2.3 fix #17 — post-sample assertion guard. Audit run #3 showed South Africa
# at 3.14× its fact-base share even after _COUNTRY_QUOTA_HARD_CAP_RATIO was
# tightened to 1.2 in v2.2. Root cause: sample_fact_pairs, sample_fact_groups,
# sample_fact_clusters and sample_confusable_facts *recorded* usage post-hoc
# but never *checked* the cap on candidates — so the cap was effectively
# disabled for 4 of 5 sampler paths. The helpers below centralise the
# "check-then-record" boundary so every path gates admission on the same rule.
#
# The guard logs (at WARNING) when a sampler returns a batch that would push
# a single country over 1.2× its base share. This is a defence in depth for
# future sampler additions: even if a future path forgets to check the gate,
# the warning lights up before the audit run does.


def _cap_admits(country: str | None) -> bool:
    """Return True if this country can accept one more fact under the hard cap.

    Wraps ``_country_quota_score``: the gate only blocks admission when the
    score is 0.0 (strict over-quota). Weighted under-capping is applied inside
    ``sample_facts`` itself, not here — all other paths use a strict
    admit/deny boundary because they can't easily be re-weighted.
    """
    return _country_quota_score(country) > 0.0


def _cap_admit_and_record(country: str | None) -> bool:
    """Atomically check the hard cap AND record usage if admitted.

    Returns True iff the country was accepted (and the counter incremented).
    Used by every sampler path that isn't ``sample_facts`` (which has its own
    weighted gate).
    """
    if not _cap_admits(country):
        return False
    _record_country_use(country)
    return True


def _assert_batch_under_cap(
    path: str,
    countries: list[str | None],
) -> None:
    """Post-sample defence-in-depth audit — log when a sampler path returns a
    batch whose country mix is already over the 1.2× hard cap. Uses the
    COUNTRY-TAGGED denominator to match the audit D3 contract. This fires at
    WARNING level so anomalies show up in the generator logs without breaking
    the run. Only runs after a meaningful sample (>= _QUOTA_GRACE_N
    country-tagged facts).
    """
    with _QUOTA_LOCK:
        total_tagged = _TOTAL_RETURNED_TAGGED
        usage = dict(_COUNTRY_USAGE)
    if total_tagged < _QUOTA_GRACE_N:
        return
    base = _country_base_distribution()
    if not base:
        return
    for c, n in usage.items():
        target_share = base.get(c)
        if target_share is None:
            continue
        observed = n / total_tagged
        cap = _COUNTRY_QUOTA_HARD_CAP_RATIO * target_share
        if observed > cap + 1e-9:
            logger.warning(
                f"[D3 quota] {path}: country {c!r} at {observed:.3%} of "
                f"{total_tagged} country-tagged facts (cap {cap:.3%} = "
                f"{_COUNTRY_QUOTA_HARD_CAP_RATIO}x {target_share:.3%} base)"
            )


_QUOTA_GRACE_N = 10  # cap is not enforced until at least N facts have been returned
# Minimum absolute number of admissions a country must be allowed before the
# cap fires. Prevents long-tail countries (shares < 1%) from being locked out
# after their very first admission at low totals. At audit scale (N >> 1000)
# the 1.2× ratio dominates and this floor never binds.
_MIN_CAP_COUNT = 3


# ─── Team ε — per-call absolute per-country cap (D3 fix v3) ─────────────────
#
# Addition: the existing 1.2× pool-share quota above is *pool-relative* and
# allows large pool-shares (Australia 22%, South Africa 13%, New Zealand 13%
# in the country-tagged slice) to legitimately fill ~26%, ~16%, ~15% of the
# returned set. That over-shoots the D3 max_overrep_ratio < 2.0 gate when
# combined with finite-sample noise.
#
# This per-call absolute cap (e.g. 0.10) is an additional gate on top of the
# 1.2× pool-share rule. Semantics:
#
#   per_country_cap = None  → behaviour unchanged (backward compat).
#   per_country_cap = 0.10  → no single country may exceed 10% of the
#                              returned-facts list for THIS sampling call.
#
# The cap is scoped to the candidate list of a single sampler call (not the
# global session counter) so multi-fact strategies (pairs/groups/clusters)
# count BOTH members of an Australian pair as 2 toward Australia's local
# quota. The implementation lives in ``_apply_per_country_cap`` below; each
# sampler post-processes its ranked candidate list through the helper before
# the existing ``_cap_admit_and_record`` step.


def _country_cap_max(per_country_cap: float, target_count: int) -> int:
    """Return the maximum per-country count allowed in a returned set of size
    ``target_count`` under the absolute fraction cap ``per_country_cap``.

    We use ``ceil`` so a request for ``count=10`` with ``cap=0.10`` allows
    exactly 1 fact per country (10% of 10 = 1.0, so the limit is 1, not 0).
    Below 1 we floor at 1 — disallowing any country at all would break
    sampling against single-country pools in tests.
    """
    if per_country_cap is None or per_country_cap <= 0.0:
        # No cap configured.
        return target_count
    raw = per_country_cap * target_count
    # Round-up so a 10% cap on 10 facts = 1 (not 0). Always allow at least 1.
    import math
    return max(1, math.ceil(raw))


def _apply_per_country_cap(
    candidates: list[dict],
    target_count: int,
    per_country_cap: float | None,
) -> list[dict]:
    """Filter a ranked candidate fact list to enforce a per-country absolute cap.

    Walks ``candidates`` in order, admitting each fact whose country still
    has room under the cap. Facts whose country is already at the cap are
    skipped; facts with no extractable country are always admitted (the cap
    only constrains country-tagged facts).

    This is the single-fact variant. For multi-fact strategies (pairs, groups,
    clusters) use ``_apply_per_country_cap_to_bundles`` so all bundle members
    count atomically.

    If ``per_country_cap`` is ``None``, the candidate list is returned
    unchanged (backward-compatible no-op).

    Args:
        candidates: ranked list of fact dicts (highest-priority first).
        target_count: caller's requested sample size — used to derive the
            per-country max via ``_country_cap_max``.
        per_country_cap: ``None`` for no cap, or a fraction in (0, 1].

    Returns:
        A new list (length ≤ ``target_count``) where no country's count
        exceeds ``ceil(per_country_cap * target_count)``.
    """
    if per_country_cap is None:
        return list(candidates)
    max_per_country = _country_cap_max(per_country_cap, target_count)
    selected: list[dict] = []
    per_country_count: dict[str, int] = defaultdict(int)
    for fact in candidates:
        if len(selected) >= target_count:
            break
        country = _extract_country_from_entities(fact.get("entities"))
        if country is not None:
            if per_country_count[country] >= max_per_country:
                continue
            per_country_count[country] += 1
        selected.append(fact)
    return selected


def _apply_per_country_cap_to_bundles(
    bundles: list[list[dict]] | list[tuple[dict, ...]],
    target_count: int,
    per_country_cap: float | None,
) -> list:
    """Per-call cap variant for bundle (multi-fact) outputs.

    Each bundle is a tuple/list of facts. A bundle is admitted iff every
    fact's country still has room under the cap; admitting the bundle counts
    EACH fact toward its country's total (so an all-Australian pair adds 2
    to Australia's count, not 1, matching the audit D3 contract).

    The denominator for the cap is ``target_count * group_size`` — the total
    number of facts that will appear in the returned bundle list. We infer
    ``group_size`` from the first bundle's length; for heterogeneous bundle
    shapes the caller should pass them through this helper separately.

    If ``per_country_cap`` is ``None``, returns the input unchanged.
    """
    if per_country_cap is None:
        return list(bundles)
    if not bundles:
        return list(bundles)
    group_size = len(bundles[0])
    fact_total = target_count * group_size
    max_per_country = _country_cap_max(per_country_cap, fact_total)
    selected: list = []
    per_country_count: dict[str, int] = defaultdict(int)
    for bundle in bundles:
        if len(selected) >= target_count:
            break
        # Tally this bundle's countries.
        bundle_countries: list[str | None] = [
            _extract_country_from_entities(f.get("entities")) for f in bundle
        ]
        # Per-country counts ADDED by this bundle (handles within-bundle dupes).
        added: dict[str, int] = defaultdict(int)
        for c in bundle_countries:
            if c is not None:
                added[c] += 1
        # Bundle admissible iff for every country, current + added <= max.
        ok = all(
            per_country_count[c] + n <= max_per_country
            for c, n in added.items()
        )
        if not ok:
            continue
        for c, n in added.items():
            per_country_count[c] += n
        selected.append(bundle)
    return selected


def _country_quota_score(country: str | None) -> float:
    """Multiplicative weight in [0, 1] for a candidate fact's country.

    - Returns 1.0 if the country is unknown or the base distribution couldn't
      be computed (no down-weighting if we have no signal).
    - Returns 0.0 if the country has already reached its 1.2× hard cap, i.e.
      ``used >= 1.2 × target_share × total_country_tagged_returned`` AND
      ``total_country_tagged_returned >= _QUOTA_GRACE_N``. The grace period
      prevents the cap tautologically firing at small-N (the very first
      sample would otherwise always be 100% of the total and trip the cap).
    - Otherwise returns ``min(1.0, target_share / max(used_share, eps))`` so
      countries at or below target share keep a weight of 1.0 and over-quota
      countries are progressively penalised.

    v2.3 fix #17: the denominator is ``_TOTAL_RETURNED_TAGGED`` (facts with
    a country entity), NOT ``_TOTAL_RETURNED`` (all returned). This matches
    the audit D3 definition — when 85% of returned facts have no country
    tag, using the all-samples denominator made the cap ~7× too loose.
    """
    if not country:
        return 1.0
    base = _country_base_distribution()
    if not base:
        return 1.0
    target_share = base.get(country)
    if target_share is None:
        # Country not present in the fact base — neutral weight.
        return 1.0

    with _QUOTA_LOCK:
        used = _COUNTRY_USAGE.get(country, 0)
        total_tagged = _TOTAL_RETURNED_TAGGED

    # Hard cap: country has already reached 1.2× its target share. Apply only
    # once we've accumulated enough samples that the cap is meaningful — at
    # tiny totals (e.g. the first few samples) every category trivially
    # exceeds 1.2× by virtue of being 100% of the total.
    #
    # ``_MIN_CAP_COUNT`` floors the cap at an absolute minimum so countries
    # with tiny base shares (e.g. Uruguay at 0.4%) can still be admitted at
    # least once per ~300-fact batch instead of being hard-banned after their
    # first admission. At full-run scale (total_tagged >= 1000) the ratio
    # dominates and the floor is inactive.
    if total_tagged >= _QUOTA_GRACE_N:
        cap_count = max(
            _MIN_CAP_COUNT,
            _COUNTRY_QUOTA_HARD_CAP_RATIO * target_share * total_tagged,
        )
        if used >= cap_count:
            return 0.0

    if total_tagged == 0:
        return 1.0
    used_share = used / total_tagged
    eps = 1e-6
    weight = min(1.0, target_share / max(used_share, eps))
    return weight


def sample_facts(
    domain: str,
    count: int,
    min_confidence: float = 0.7,
    exclude_ids: set[str] | None = None,
    prefer_diverse_sources: bool = True,
    wine_category: str | None = None,
    strategy: str | None = None,
    per_country_cap: float | None = None,
    require_substantive: bool = False,
    reject_ubiquitous_for_region_answer: bool = False,
) -> list[dict]:
    """Sample facts from PostgreSQL for question generation.

    Returns list of dicts with keys: id, fact_text, domain, subdomain,
    entities, source_id, source_name, source_url, confidence, tags.

    Args:
        wine_category: optional wine category filter ("red", "white",
            "sparkling", "rosé", "fortified"). When set, only facts whose
            ``_classify_wine_category`` matches are returned. Default ``None``
            preserves the legacy behaviour (no category filtering).
        strategy: name of the generator strategy requesting facts. When set
            to "fact_to_question" or "template", the v2.2 fix #11 iconic-
            entity filter fires: facts whose ONLY named entity is iconic
            (e.g. "Château Margaux is a Bordeaux 1855 First Growth") are
            dropped because the question is world-knowledge-solvable. Other
            strategies still get iconic facts (multi-fact synthesis keeps
            the difficulty up).
        per_country_cap: Team ε D3-fix v3 (April 2026). When set to a
            fraction in (0, 1], no single country may exceed
            ``ceil(per_country_cap * count)`` of the returned set. Backward-
            compatible default ``None`` disables the cap (existing callers
            unchanged). Pool-relative 1.2× quota (``_country_quota_score``)
            still applies — this is an additional, absolute gate stacked on
            top.
        require_substantive: Phase 2g.16 Lever 2. When True, forces the
            substantiveness filter ON regardless of the
            OENOBENCH_FACT_SUBSTANTIVE_FILTER env var. Use this for strategies
            that must exclude thin-geo facts (e.g. template generation). The
            env var still overrides to ON for all strategies when set; this
            kwarg only allows a caller to force ON without the env var.
        reject_ubiquitous_for_region_answer: Phase 2g.17. When True AND
            domain == "grape_varieties", facts whose extracted grape name is
            in the ubiquity set (Cabernet Sauvignon, Chardonnay, etc.) are
            rejected. Use for "find-the-region" template stems and
            fact_to_question calls where the grape is the question variable
            and region is the expected answer — ubiquitous grapes produce
            ambiguous questions with many valid answers.
    """
    conn = get_pg()
    cur = conn.cursor()
    exclude = list(exclude_ids) if exclude_ids else []

    if prefer_diverse_sources:
        # Window function: max 5 facts per source, then random sample
        query = """
            SELECT * FROM (
                SELECT
                    f.id, f.fact_text, f.domain, f.subdomain,
                    f.entities, f.source_id, s.name AS source_name,
                    s.url AS source_url, f.confidence, f.tags,
                    row_number() OVER (PARTITION BY f.source_id ORDER BY random()) AS rn
                FROM facts f
                JOIN sources s ON s.id = f.source_id
                WHERE f.domain = %s
                  AND f.confidence >= %s
                  AND NOT (f.id = ANY(%s::uuid[]))
            ) ranked
            WHERE rn <= 5
            ORDER BY random()
            LIMIT %s
        """
    else:
        query = """
            SELECT
                f.id, f.fact_text, f.domain, f.subdomain,
                f.entities, f.source_id, s.name AS source_name,
                s.url AS source_url, f.confidence, f.tags
            FROM facts f
            JOIN sources s ON s.id = f.source_id
            WHERE f.domain = %s
              AND f.confidence >= %s
              AND NOT (f.id = ANY(%s::uuid[]))
            ORDER BY random()
            LIMIT %s
        """

    # Over-fetch generously to give the country quota + category filter room
    # to skip over-quota or wrong-category candidates without starving.
    over_fetch = max(count * 6, 30)
    cur.execute(query, (domain, min_confidence, exclude, over_fetch))
    rows = cur.fetchall()

    # Pre-filter by quality + (optional) wine-category, then weight remaining
    # candidates by the country quota.  A hard cap of 0.0 on the quota score
    # means the candidate is over its 1.5× base share and must be skipped.
    candidates: list[tuple[float, dict]] = []
    quality_filtered = 0
    substantive_filtered = 0
    category_filtered = 0
    iconic_filtered_single = 0
    grape_name_filtered = 0
    # v2.2 fix #11 → Lever B2 (2026-04-28): apply iconic-only filter for any
    # strategy that calls sample_facts(). Multi-fact strategies that don't
    # pass through here still use _bundle_has_non_iconic_anchor.
    apply_iconic_filter = _should_apply_iconic_filter(strategy)
    # Lever B2: opt-in substantiveness pre-screen. Default OFF for v8
    # byte-for-byte reproducibility. Phase 2g.16 Lever 2: callers may also
    # pass require_substantive=True to force the filter on without the env var.
    substantive_filter_on = (
        os.environ.get(_FACT_SUBSTANTIVE_ENV_VAR, "").strip() == "1"
        or require_substantive
    )
    for r in rows:
        if not _is_fact_specific(r["fact_text"]):
            quality_filtered += 1
            continue
        if substantive_filter_on and not _is_fact_substantive(r["fact_text"]):
            substantive_filtered += 1
            continue
        # Phase 2g.16: grape-variety name validity filter — rejects facts
        # whose extracted grape name is a pure number, regulation rule, or
        # vague generic blend (e.g. "457", "55% white varieties",
        # "Champagne Blend"). Only applied to grape_varieties facts.
        if domain == "grape_varieties" and not _is_grape_fact_valid(r["fact_text"]):
            grape_name_filtered += 1
            global _GRAPE_NAME_FILTERED_COUNT
            _GRAPE_NAME_FILTERED_COUNT += 1
            continue
        # Phase 2g.17: ubiquitous-grape ambiguity guard — rejects facts about
        # globally ubiquitous varieties (Cabernet, Chardonnay, etc.) when the
        # calling strategy needs a unique-answer region question.
        if reject_ubiquitous_for_region_answer and domain == "grape_varieties" and _fact_has_ubiquitous_grape(r["fact_text"]):
            global _UBIQUITY_FILTERED_COUNT
            _UBIQUITY_FILTERED_COUNT += 1
            continue
        if wine_category is not None:
            cat = _classify_wine_category(r["fact_text"])
            if cat != wine_category:
                category_filtered += 1
                continue
        fact_dict = dict(r)
        if apply_iconic_filter and _fact_is_iconic_only(fact_dict):
            iconic_filtered_single += 1
            continue
        candidates.append((1.0, fact_dict))

    # Phase 2g.15 (Team C): iconic-exhaust fallback.
    # If the iconic filter is active but we still don't have enough candidates
    # to fill ``count``, retry the loop with apply_iconic_filter=False so the
    # non-iconic-substantive pool can fill the remaining slots. The vague,
    # substantive, and wine_category filters STILL apply — only iconic is
    # dropped for the fallback pass.
    if apply_iconic_filter and len(candidates) < count:
        global _ICONIC_FALLBACK_COUNT
        missing = count - len(candidates)
        # Track fact IDs already admitted in the primary pass to avoid duplication.
        existing_fact_ids = {fact.get("id") for _, fact in candidates}
        fallback_candidates: list[tuple[float, dict]] = []
        for r in rows:
            fact_dict = dict(r)
            # Skip facts already selected in the primary pass.
            if fact_dict.get("id") in existing_fact_ids:
                continue
            if not _is_fact_specific(fact_dict["fact_text"]):
                continue
            if substantive_filter_on and not _is_fact_substantive(fact_dict["fact_text"]):
                continue
            # Phase 2g.16: grape-name validity filter also applies on fallback.
            if domain == "grape_varieties" and not _is_grape_fact_valid(fact_dict["fact_text"]):
                continue
            # Phase 2g.17: ubiquitous-grape guard also applies on fallback.
            if reject_ubiquitous_for_region_answer and domain == "grape_varieties" and _fact_has_ubiquitous_grape(fact_dict["fact_text"]):
                _UBIQUITY_FILTERED_COUNT += 1
                continue
            if wine_category is not None:
                cat = _classify_wine_category(fact_dict["fact_text"])
                if cat != wine_category:
                    continue
            # Iconic filter intentionally NOT applied here — this is the fallback.
            # Only iconic-only facts reach this point (non-iconic facts were
            # already admitted in the primary pass above).
            if not _fact_is_iconic_only(fact_dict):
                continue  # already included in the primary pass
            fallback_candidates.append((1.0, fact_dict))
        if fallback_candidates:
            _ICONIC_FALLBACK_COUNT += 1
            logger.info(
                "sampler iconic-exhaust fallback: filling {}/{} from "
                "non-iconic-substantive pool | strategy={} | domain={}",
                missing, count, strategy, domain,
            )
            candidates.extend(fallback_candidates)

    # Apply per-country quota weighting + hard cap, then deterministic order
    # by score (highest first) — within the same score the SQL random() order
    # is preserved so we still get diversity across runs.
    weighted: list[tuple[float, dict]] = []
    capped = 0
    for _, fact in candidates:
        country = _extract_country_from_entities(fact.get("entities"))
        weight = _country_quota_score(country)
        if weight <= 0.0:
            capped += 1
            continue
        weighted.append((weight, fact))
    weighted.sort(key=lambda kv: kv[0], reverse=True)

    # Per-call absolute cap (Team ε): walk the ranked list and skip any
    # candidate whose country has already filled its per-call quota. This is
    # an additional gate stacked on top of the pool-relative 1.2× quota.
    max_per_country = _country_cap_max(per_country_cap, count) if per_country_cap is not None else None
    per_call_country_count: dict[str, int] = defaultdict(int)
    per_call_capped = 0

    results: list[dict] = []
    for _, fact in weighted:
        if len(results) >= count:
            break
        country = _extract_country_from_entities(fact.get("entities"))
        # Per-call cap check (only when configured).
        if max_per_country is not None and country is not None:
            if per_call_country_count[country] >= max_per_country:
                per_call_capped += 1
                continue
        # Re-check the pool-share cap with the now-incremented totals so a
        # streak of same-country candidates can't slip past the gate.
        if _country_quota_score(country) <= 0.0:
            capped += 1
            continue
        _record_country_use(country)
        if country is not None:
            per_call_country_count[country] += 1
        results.append(fact)

    if quality_filtered:
        logger.debug(f"Filtered {quality_filtered} vague/marketing facts")
    if substantive_filtered:
        logger.debug(
            f"Filtered {substantive_filtered} substantiveness-failed facts "
            f"(OENOBENCH_FACT_SUBSTANTIVE_FILTER=1)"
        )
    if category_filtered:
        logger.debug(f"Filtered {category_filtered} facts not matching wine_category={wine_category}")
    if iconic_filtered_single:
        logger.debug(
            f"Filtered {iconic_filtered_single} iconic-only facts "
            f"(single-fact strategy — v2.2 fix #11)"
        )
    if capped:
        logger.debug(f"Skipped {capped} facts capped by country quota")
    if per_call_capped:
        logger.debug(
            f"Skipped {per_call_capped} facts capped by per-call cap "
            f"(per_country_cap={per_country_cap})"
        )

    # v2.3 fix #17 — post-sample assertion guard (defence in depth).
    _assert_batch_under_cap("sample_facts", [
        _extract_country_from_entities(f.get("entities")) for f in results
    ])

    logger.debug(f"Sampled {len(results)} facts for domain={domain}")
    return results


def _extract_entity_names(entities) -> set[str]:
    """Extract entity name strings from JSONB entities field."""
    if not entities:
        return set()
    if isinstance(entities, str):
        import orjson
        try:
            entities = orjson.loads(entities)
        except Exception:
            return set()
    return {e.get("name", "").lower() for e in entities if e.get("name")}


def _extract_entity_types(entities) -> set[str]:
    """Extract entity type strings from JSONB entities field."""
    if not entities:
        return set()
    if isinstance(entities, str):
        import orjson
        try:
            entities = orjson.loads(entities)
        except Exception:
            return set()
    return {e.get("type", "").lower() for e in entities if e.get("type")}


def _parse_entities(entities):
    """Parse entities from JSONB field (handles str or list)."""
    if not entities:
        return []
    if isinstance(entities, str):
        import orjson
        try:
            return orjson.loads(entities)
        except Exception:
            return []
    return entities


def _extract_entity_map(entities) -> dict[str, set[str]]:
    """Map entity type -> set of entity names.

    Preserves type-name relationship unlike _extract_entity_types/_extract_entity_names.
    E.g. {"region": {"Barolo", "Piedmont"}, "grape": {"Nebbiolo"}, "country": {"Italy"}}
    """
    parsed = _parse_entities(entities)
    result: dict[str, set[str]] = {}
    for e in parsed:
        etype = e.get("type", "").lower()
        ename = e.get("name", "").strip()
        if etype and ename:
            result.setdefault(etype, set()).add(ename)
    return result


# Generic wine words to exclude from keyword matching
_WINE_STOPWORDS = frozenset({
    "wine", "wines", "region", "regions", "produced", "production",
    "located", "area", "known", "made", "grape", "grapes",
    "is", "the", "and", "for", "from", "with", "that", "this",
    "are", "was", "has", "been", "of", "in", "a", "an", "its",
    "by", "to", "it", "as", "or", "on", "at", "be", "not", "also",
    "which", "can", "may", "such", "used", "have", "had", "do",
})


def _content_keywords(text: str) -> set[str]:
    """Extract meaningful keywords from text, excluding wine-generic stopwords."""
    return {w for w in text.lower().split() if w not in _WINE_STOPWORDS and len(w) > 2}


def _entity_affinity_score(
    map_a: dict[str, set[str]],
    map_b: dict[str, set[str]],
) -> tuple[float, str]:
    """Score entity affinity (0-1) between two facts. Returns (score, reason).

    Higher scores mean more comparable entities. Used to rank/filter
    pairings for comparative, scenario, and distractor strategies.
    """
    score = 0.0
    reasons: list[str] = []

    countries_a = map_a.get("country", set())
    countries_b = map_b.get("country", set())
    shared_countries = countries_a & countries_b
    if shared_countries:
        score += 0.3
        reasons.append(f"same country ({', '.join(sorted(shared_countries))})")

    regions_a = map_a.get("region", set())
    regions_b = map_b.get("region", set())
    shared_regions = regions_a & regions_b
    if shared_regions:
        # Shared parent region (but they may differ on sub-entities)
        score += 0.3
        reasons.append(f"shared region ({', '.join(sorted(shared_regions))})")

    appellations_a = map_a.get("appellation", set())
    appellations_b = map_b.get("appellation", set())
    shared_apps = appellations_a & appellations_b
    if shared_apps:
        score += 0.2
        reasons.append(f"shared appellation ({', '.join(sorted(shared_apps))})")

    # Same entity type with different names (e.g., both have grapes but different ones)
    for etype in ("grape", "region", "appellation", "producer", "ava"):
        names_a = map_a.get(etype, set())
        names_b = map_b.get(etype, set())
        if names_a and names_b and names_a != names_b:
            diff_a = names_a - names_b
            diff_b = names_b - names_a
            if diff_a and diff_b:
                score += 0.2
                reasons.append(f"comparable {etype}s ({', '.join(sorted(diff_a))} vs {', '.join(sorted(diff_b))})")
                break  # Only count once

    # Penalty: if all primary entities are identical, this isn't a comparison
    all_names_a = _extract_entity_names_from_map(map_a)
    all_names_b = _extract_entity_names_from_map(map_b)
    if all_names_a and all_names_a == all_names_b:
        score = -1.0
        reasons = ["identical entities"]

    reason_str = "; ".join(reasons) if reasons else "no shared context"
    return (min(score, 1.0), reason_str)


def _extract_entity_names_from_map(emap: dict[str, set[str]]) -> set[str]:
    """Flatten entity map to set of all lowercase names."""
    result: set[str] = set()
    for names in emap.values():
        result.update(n.lower() for n in names)
    return result


def sample_fact_pairs(
    domain: str,
    count: int,
    exclude_ids: set[str] | None = None,
    per_country_cap: float | None = None,
) -> list[tuple[dict, dict]]:
    """Sample pairs of comparable facts about different entities of the same type.

    Uses SQL to find facts about different appellations/regions/grapes/producers
    within the same subdomain — e.g., two Italian DOCGs with aging requirements,
    two Bordeaux châteaux, two grapes from the same country. This produces
    meaningful comparisons like "Both Barolo and Barbaresco are Piedmont DOCGs.
    Which requires longer minimum aging?"

    Args:
        per_country_cap: Team ε D3-fix v3. When set to a fraction in (0, 1],
            no single country may contribute more than
            ``ceil(per_country_cap * count * 2)`` facts to the returned set
            (pairs contribute 2 facts each toward the country quota). Default
            ``None`` preserves the prior behaviour (no per-call cap).
    """
    conn = get_pg()
    cur = conn.cursor()
    exclude = list(exclude_ids) if exclude_ids else []

    # Entity-based pairing: find pairs of facts that mention different entities
    # of the same type, constrained by country (or subdomain when country is
    # absent). This prevents nonsensical cross-country comparisons.
    cur.execute(
        """
        WITH entity_facts AS (
            SELECT f.id, f.fact_text, f.domain, f.subdomain,
                   f.entities, f.source_id, s.name AS source_name,
                   s.url AS source_url, f.confidence, f.tags,
                   e->>'type' AS etype, e->>'name' AS ename,
                   (SELECT e2->>'name' FROM jsonb_array_elements(f.entities) e2
                    WHERE e2->>'type' = 'country' LIMIT 1) AS country
            FROM facts f
            JOIN sources s ON s.id = f.source_id,
            jsonb_array_elements(f.entities) e
            WHERE f.domain = %s
              AND f.confidence >= 0.7
              AND f.subdomain IS NOT NULL
              AND length(f.fact_text) > 40
              AND e->>'type' IN ('region', 'grape', 'appellation', 'producer')
              AND NOT (f.id = ANY(%s::uuid[]))
        )
        SELECT
            a.id AS a_id, a.fact_text AS a_text, a.domain AS a_domain,
            a.subdomain AS a_sub, a.entities AS a_entities,
            a.source_id AS a_source_id, a.source_name AS a_source_name,
            a.source_url AS a_source_url, a.confidence AS a_confidence,
            a.tags AS a_tags, a.etype AS shared_type,
            a.ename AS a_entity, b.ename AS b_entity,
            b.id AS b_id, b.fact_text AS b_text,
            b.subdomain AS b_sub, b.entities AS b_entities,
            b.source_id AS b_source_id, b.source_name AS b_source_name,
            b.source_url AS b_source_url, b.confidence AS b_confidence,
            b.tags AS b_tags
        FROM entity_facts a
        JOIN entity_facts b
          ON a.etype = b.etype
          AND a.ename != b.ename
          AND a.id < b.id
          AND (
              (a.country IS NOT NULL AND a.country = b.country)
              OR (a.country IS NULL AND b.country IS NULL AND a.subdomain = b.subdomain)
          )
        ORDER BY random()
        LIMIT %s
        """,
        (domain, exclude, count * 20),
    )

    rows = cur.fetchall()

    # Phase 2g.17: post-filter rows where BOTH facts contain the SAME ubiquitous
    # grape — e.g. "Napa + Cabernet" vs "Bordeaux + Cabernet". Such pairs produce
    # ambiguous comparative questions ("Which region makes better Cabernet?").
    # Pairs where the two grapes differ, or neither is ubiquitous, are kept.
    global _UBIQUITY_FILTERED_COUNT
    filtered_rows = []
    for row in rows:
        a_text, b_text = row["a_text"], row["b_text"]
        if _fact_has_ubiquitous_grape(a_text) and _fact_has_ubiquitous_grape(b_text):
            name_a = _extract_grape_name(a_text)
            name_b = _extract_grape_name(b_text)
            if (name_a is not None and name_b is not None
                    and _normalise_grape_name(name_a) == _normalise_grape_name(name_b)):
                _UBIQUITY_FILTERED_COUNT += 1
                logger.debug("dropped same-ubiquitous-grape pair | grape={}", _normalise_grape_name(name_a))
                continue
        filtered_rows.append(row)
    rows = filtered_rows

    # Score all candidates by entity affinity + dimension match
    scored: list[tuple[float, str, dict, str | None, str]] = []
    for row in rows:
        a_text, b_text = row["a_text"], row["b_text"]
        if not _is_fact_specific(a_text) or not _is_fact_specific(b_text):
            continue
        if not _is_fact_rich(a_text) or not _is_fact_rich(b_text):
            continue
        # Stricter minimum for comparative: short facts are too thin
        if len(a_text.split()) < 18 or len(b_text.split()) < 18:
            if not (_WINE_CONTENT_SIGNALS.search(a_text) and _WINE_CONTENT_SIGNALS.search(b_text)):
                continue

        # Plan §10 — wine-category leak guard. If both facts have a detectable
        # wine category and they DIFFER, reject the pair so we never compare
        # a sparkling fact against a red fact (or similar). Pairs where one
        # or both facts are category-unclassifiable are allowed through.
        cat_a = _classify_wine_category(a_text)
        cat_b = _classify_wine_category(b_text)
        if cat_a and cat_b and cat_a != cat_b:
            continue

        map_a = _extract_entity_map(row["a_entities"])
        map_b = _extract_entity_map(row["b_entities"])
        affinity, reason = _entity_affinity_score(map_a, map_b)
        if affinity < 0.2:
            continue

        # Dimension classification and scoring
        dim_a = _classify_dimension(a_text)
        dim_b = _classify_dimension(b_text)

        if dim_a is not None and dim_a == dim_b:
            affinity += 0.4
            reason += f"; same dimension ({dim_a})"
        elif dim_a is not None and dim_b is not None and dim_a != dim_b:
            affinity -= 0.2
            reason += f"; dimension mismatch ({dim_a} vs {dim_b})"
        elif dim_a is None and dim_b is None:
            # Both unclassified — require keyword overlap as fallback
            kw_overlap = len(_content_keywords(a_text) & _content_keywords(b_text))
            if kw_overlap < 3:
                continue
            reason += f"; keyword overlap ({kw_overlap})"

        auto_type = _auto_comparison_type(dim_a, dim_b, a_text, b_text)
        scored.append((affinity, reason, row, dim_a, auto_type))

    # Sort by affinity descending — best pairs first
    scored.sort(key=lambda x: x[0], reverse=True)

    pairs: list[tuple[dict, dict]] = []
    seen_ids: set[str] = set()
    capped = 0
    iconic_bundle_rejected = 0
    per_call_capped = 0

    # Per-call absolute cap (Team ε). Total facts in the returned set =
    # count * 2 (each pair contributes 2 facts). Bookkeeping: track per-country
    # facts admitted by this call only.
    per_call_max = (
        _country_cap_max(per_country_cap, count * 2)
        if per_country_cap is not None
        else None
    )
    per_call_country_count: dict[str, int] = defaultdict(int)

    for affinity, reason, row, dim, auto_type in scored:
        if len(pairs) >= count:
            break
        a_id, b_id = str(row["a_id"]), str(row["b_id"])
        # Avoid reusing the same fact in multiple pairs
        if a_id in seen_ids or b_id in seen_ids:
            continue

        fact_a = {
            "id": row["a_id"], "fact_text": row["a_text"],
            "domain": row["a_domain"], "subdomain": row["a_sub"],
            "entities": row["a_entities"], "source_id": row["a_source_id"],
            "source_name": row["a_source_name"], "source_url": row["a_source_url"],
            "confidence": row["a_confidence"], "tags": row["a_tags"],
            "_comparison_context": reason,
            "_dimension": dim,
            "_auto_comparison_type": auto_type,
            "_matched_entity_name": row["a_entity"],
        }
        fact_b = {
            "id": row["b_id"], "fact_text": row["b_text"],
            "domain": row["a_domain"], "subdomain": row["b_sub"],
            "entities": row["b_entities"], "source_id": row["b_source_id"],
            "source_name": row["b_source_name"], "source_url": row["b_source_url"],
            "confidence": row["b_confidence"], "tags": row["b_tags"],
            "_dimension": dim,
            "_matched_entity_name": row["b_entity"],
        }
        # v2.3 Phase F — iconic anchor requirement. If BOTH facts in the pair
        # are iconic-only, the comparative question is world-knowledge-solvable
        # ("Compare Château Margaux to Château Latour") — reject. A pair with
        # ≥1 non-iconic anchor fact is fine: the anchor fact supplies the
        # fact-specific attribute the question must key on.
        if not _bundle_has_non_iconic_anchor([fact_a, fact_b]):
            iconic_bundle_rejected += 1
            continue
        # v2.3 fix #17 — enforce the 1.2x hard cap BEFORE accepting the pair.
        # We admit both facts atomically: if admitting the first would fit
        # but admitting the second would not, roll back the first. This keeps
        # the country quota honest across all generator strategies.
        country_a = _extract_country_from_entities(fact_a.get("entities"))
        country_b = _extract_country_from_entities(fact_b.get("entities"))

        # Per-call absolute cap (Team ε). Both facts of a pair count toward
        # the same country if they share one — admit atomically.
        if per_call_max is not None:
            added_a = 1 if country_a is not None else 0
            added_b = 1 if country_b is not None else 0
            if country_a is not None and country_a == country_b:
                # Same-country pair: total addition is 2, must fit at once.
                if per_call_country_count[country_a] + 2 > per_call_max:
                    per_call_capped += 1
                    continue
            else:
                if (
                    country_a is not None
                    and per_call_country_count[country_a] + added_a > per_call_max
                ):
                    per_call_capped += 1
                    continue
                if (
                    country_b is not None
                    and per_call_country_count[country_b] + added_b > per_call_max
                ):
                    per_call_capped += 1
                    continue

        if not _cap_admit_and_record(country_a):
            capped += 1
            continue
        if not _cap_admit_and_record(country_b):
            # Roll back the A admission so the counters stay consistent.
            with _QUOTA_LOCK:
                global _TOTAL_RETURNED, _TOTAL_RETURNED_TAGGED
                _TOTAL_RETURNED -= 1
                if country_a:
                    _TOTAL_RETURNED_TAGGED -= 1
                    if _COUNTRY_USAGE.get(country_a, 0) > 0:
                        _COUNTRY_USAGE[country_a] -= 1
                        if _COUNTRY_USAGE[country_a] == 0:
                            del _COUNTRY_USAGE[country_a]
            capped += 1
            continue
        pairs.append((fact_a, fact_b))
        seen_ids.update({a_id, b_id})
        # Per-call cap bookkeeping (Team ε).
        if country_a is not None:
            per_call_country_count[country_a] += 1
        if country_b is not None:
            per_call_country_count[country_b] += 1

    if capped:
        logger.debug(
            f"sample_fact_pairs: skipped {capped} pairs blocked by country cap"
        )
    if per_call_capped:
        logger.debug(
            f"sample_fact_pairs: skipped {per_call_capped} pairs blocked by "
            f"per-call cap (per_country_cap={per_country_cap})"
        )
    if iconic_bundle_rejected:
        logger.debug(
            f"sample_fact_pairs: rejected {iconic_bundle_rejected} iconic-only "
            f"pairs (v2.3 Phase F — no non-iconic anchor)"
        )

    # Defence-in-depth: log a warning if the returned batch already exceeds
    # the hard cap (shouldn't happen with the admit-and-record gate, but the
    # guard surfaces any future sampler regression).
    _assert_batch_under_cap("sample_fact_pairs", [
        _extract_country_from_entities(f.get("entities"))
        for pair in pairs for f in pair
    ])

    logger.debug(
        f"Sampled {len(pairs)} entity-matched fact pairs for domain={domain}"
    )
    return pairs


def sample_fact_groups(
    domain: str,
    count: int,
    group_size: int = 3,
    exclude_ids: set[str] | None = None,
    per_country_cap: float | None = None,
) -> list[list[dict]]:
    """Sample groups of 3-4 dimension-matched facts for multi-entity comparisons.

    Groups facts by (country, entity_type, dimension) to ensure all facts
    in a group discuss the same attribute about different but comparable entities.

    Args:
        per_country_cap: Team ε D3-fix v3. When set to a fraction in (0, 1],
            no single country may contribute more than
            ``ceil(per_country_cap * count * group_size)`` facts to the
            returned set. Default ``None`` preserves the prior behaviour
            (no per-call cap).
    """
    conn = get_pg()
    cur = conn.cursor()
    exclude = list(exclude_ids) if exclude_ids else []

    cur.execute(
        """
        WITH entity_facts AS (
            SELECT f.id, f.fact_text, f.domain, f.subdomain,
                   f.entities, f.source_id, s.name AS source_name,
                   s.url AS source_url, f.confidence, f.tags,
                   e->>'type' AS etype, e->>'name' AS ename,
                   (SELECT e2->>'name' FROM jsonb_array_elements(f.entities) e2
                    WHERE e2->>'type' = 'country' LIMIT 1) AS country
            FROM facts f
            JOIN sources s ON s.id = f.source_id,
            jsonb_array_elements(f.entities) e
            WHERE f.domain = %s
              AND f.confidence >= 0.7
              AND f.subdomain IS NOT NULL
              AND length(f.fact_text) > 40
              AND e->>'type' IN ('region', 'grape', 'appellation', 'producer')
              AND NOT (f.id = ANY(%s::uuid[]))
        )
        SELECT id, fact_text, domain, subdomain, entities, source_id,
               source_name, source_url, confidence, tags, etype, ename, country
        FROM entity_facts
        ORDER BY random()
        LIMIT %s
        """,
        (domain, exclude, count * 100),
    )
    rows = cur.fetchall()

    # Filter, classify, and bucket by (country, etype, dimension)
    classified: dict[tuple, list[dict]] = {}
    seen_ids: set[str] = set()

    for row in rows:
        fid = str(row["id"])
        if fid in seen_ids:
            continue
        text = row["fact_text"]
        if not _is_fact_specific(text) or not _is_fact_rich(text):
            continue
        if len(text.split()) < 18 and not _WINE_CONTENT_SIGNALS.search(text):
            continue

        dim = _classify_dimension(text)
        if dim is None:
            continue  # Multi-entity groups require classified dimensions

        # Use explicit country entity, fall back to subdomain for grouping
        country = row["country"] or row.get("subdomain")
        if not country:
            continue  # Skip facts with no geographic context
        key = (country, row["etype"], dim)
        classified.setdefault(key, []).append(dict(row) | {"_dimension": dim})
        seen_ids.add(fid)

    # Build groups: pick facts with distinct entity names within each bucket
    groups: list[list[dict]] = []
    capped = 0
    iconic_bundle_rejected = 0
    per_call_capped = 0

    # Per-call absolute cap (Team ε). Total facts in returned set =
    # count * group_size. Track per-country fact admissions for this call.
    per_call_max = (
        _country_cap_max(per_country_cap, count * group_size)
        if per_country_cap is not None
        else None
    )
    per_call_country_count: dict[str, int] = defaultdict(int)

    for key, facts in classified.items():
        if len(facts) < group_size:
            continue
        selected: list[dict] = []
        used_names: set[str] = set()
        for f in facts:
            ename = f["ename"].lower()
            if ename not in used_names:
                selected.append(f)
                used_names.add(ename)
                if len(selected) >= group_size:
                    break
        if len(selected) >= group_size:
            auto_type = _auto_comparison_type(
                selected[0]["_dimension"], selected[1]["_dimension"],
                selected[0]["fact_text"], selected[1]["fact_text"],
            )
            if auto_type != "most_least":
                auto_type = "which_one"

            country, etype, dim = key
            context = f"same country ({country}); same {etype} type; same dimension ({dim})"
            for f in selected:
                f["_comparison_context"] = context
                f["_auto_comparison_type"] = auto_type
                f["_matched_entity_name"] = f["ename"]

            # v2.3 Phase F — iconic anchor requirement. A group where EVERY
            # fact is iconic-only produces a world-knowledge-solvable
            # comparative question. Require ≥1 non-iconic fact to anchor the
            # question on a fact-specific attribute.
            if not _bundle_has_non_iconic_anchor(selected):
                iconic_bundle_rejected += 1
                continue

            # Per-call absolute cap pre-check (Team ε). Tally added counts
            # per country and reject the whole group if any country would
            # overshoot the per-call max.
            if per_call_max is not None:
                added_per_country: dict[str, int] = defaultdict(int)
                for f in selected:
                    c = _extract_country_from_entities(f.get("entities"))
                    if c is not None:
                        added_per_country[c] += 1
                if any(
                    per_call_country_count[c] + n > per_call_max
                    for c, n in added_per_country.items()
                ):
                    per_call_capped += 1
                    continue

            # v2.3 fix #17 — hard-cap admission BEFORE emitting the group.
            # All N facts in a group are admitted atomically; if any single
            # country-cap check fails, the whole group is rejected and the
            # already-incremented counters are rolled back.
            admitted_countries: list[str | None] = []
            ok = True
            for f in selected:
                c = _extract_country_from_entities(f.get("entities"))
                if _cap_admit_and_record(c):
                    admitted_countries.append(c)
                else:
                    ok = False
                    break
            if not ok:
                # Roll back any partial admissions for this group.
                with _QUOTA_LOCK:
                    global _TOTAL_RETURNED, _TOTAL_RETURNED_TAGGED
                    for c in admitted_countries:
                        _TOTAL_RETURNED -= 1
                        if c:
                            _TOTAL_RETURNED_TAGGED -= 1
                            if _COUNTRY_USAGE.get(c, 0) > 0:
                                _COUNTRY_USAGE[c] -= 1
                                if _COUNTRY_USAGE[c] == 0:
                                    del _COUNTRY_USAGE[c]
                capped += 1
                continue
            groups.append(selected)
            # Per-call cap bookkeeping (Team ε): commit the per-country adds.
            if per_call_max is not None:
                for c, n in added_per_country.items():
                    per_call_country_count[c] += n

    if capped:
        logger.debug(
            f"sample_fact_groups: skipped {capped} groups blocked by country cap"
        )
    if per_call_capped:
        logger.debug(
            f"sample_fact_groups: skipped {per_call_capped} groups blocked by "
            f"per-call cap (per_country_cap={per_country_cap})"
        )
    if iconic_bundle_rejected:
        logger.debug(
            f"sample_fact_groups: rejected {iconic_bundle_rejected} iconic-only "
            f"groups (v2.3 Phase F — no non-iconic anchor)"
        )

    groups.sort(
        key=lambda g: sum(len(f["fact_text"]) for f in g),
        reverse=True,
    )

    # Post-sample assertion guard.
    _assert_batch_under_cap("sample_fact_groups", [
        _extract_country_from_entities(f.get("entities"))
        for group in groups[:count] for f in group
    ])

    logger.debug(
        f"Sampled {min(len(groups), count)} fact groups (size={group_size}) for domain={domain}"
    )
    return groups[:count]


def sample_fact_clusters(
    domain: str,
    count: int,
    cluster_size: int = 3,
    exclude_ids: set[str] | None = None,
    per_country_cap: float | None = None,
) -> list[list[dict]]:
    """Sample clusters of cohesive, related facts for scenario synthesis.

    Facts in each cluster come from the same subdomain and share entity
    types or keywords, ensuring they can form a coherent scenario.

    Plan §10 (universal C2): all facts in a cluster must share the same
    detectable wine category (red / white / sparkling / rosé / fortified)
    — clusters that mix categories are rejected so scenario stems never end
    up combining "Pinot Noir red" facts with "Champagne sparkling" facts.
    Facts with no detectable category are allowed (the seed fact's category
    governs).

    Args:
        per_country_cap: Team ε D3-fix v3. When set to a fraction in (0, 1],
            no single country may contribute more than
            ``ceil(per_country_cap * count * cluster_size)`` facts to the
            returned set. Default ``None`` preserves the prior behaviour
            (no per-call cap).
    """
    conn = get_pg()
    cur = conn.cursor()
    exclude = list(exclude_ids) if exclude_ids else []

    # Get subdomains that have enough specific facts
    cur.execute(
        """
        SELECT subdomain, count(*) AS cnt
        FROM facts
        WHERE domain = %s
          AND subdomain IS NOT NULL
          AND confidence >= 0.7
          AND NOT (id = ANY(%s::uuid[]))
        GROUP BY subdomain
        HAVING count(*) >= %s
        ORDER BY random()
        """,
        (domain, exclude, cluster_size * 2),  # require 2x to allow filtering
    )
    eligible = [row["subdomain"] for row in cur.fetchall()]

    clusters: list[list[dict]] = []
    iconic_bundle_rejected = 0
    per_call_capped = 0

    # Per-call absolute cap (Team ε). Total facts in returned set =
    # count * cluster_size. Track per-country fact admissions for this call.
    per_call_max = (
        _country_cap_max(per_country_cap, count * cluster_size)
        if per_country_cap is not None
        else None
    )
    per_call_country_count: dict[str, int] = defaultdict(int)

    for sub in eligible:
        if len(clusters) >= count:
            break
        cur.execute(
            """
            SELECT f.id, f.fact_text, f.domain, f.subdomain,
                   f.entities, f.source_id, s.name AS source_name,
                   s.url AS source_url, f.confidence, f.tags
            FROM facts f
            JOIN sources s ON s.id = f.source_id
            WHERE f.domain = %s
              AND f.subdomain = %s
              AND f.confidence >= 0.7
              AND NOT (f.id = ANY(%s::uuid[]))
            ORDER BY random()
            LIMIT %s
            """,
            (domain, sub, exclude, cluster_size * 6),
        )
        candidates = [dict(r) for r in cur.fetchall()]
        # Filter vague and thin geographic facts. v2.2 fix #7: also drop
        # facts whose text explicitly enumerates multiple wine categories
        # (e.g. "red and white blends" in a single fact). Using such a fact
        # as the scenario seed caused all 3 C2 category-leak audit failures.
        candidates = [
            c for c in candidates
            if _is_fact_specific(c["fact_text"])
            and _is_fact_rich(c["fact_text"])
            and not _fact_has_multi_category_text(c["fact_text"])
        ]

        if len(candidates) < cluster_size:
            continue

        # Pick a cohesive cluster: start with first fact, greedily add facts
        # that share entity NAMES (not just types) or meaningful keyword overlap.
        # This ensures facts in a cluster are about the same entities/topic.
        cluster = [candidates[0]]
        cluster_names = _extract_entity_names(candidates[0]["entities"])
        cluster_keywords = _content_keywords(candidates[0]["fact_text"])
        cluster_category = _classify_wine_category(candidates[0]["fact_text"])

        for c in candidates[1:]:
            if len(cluster) >= cluster_size:
                break
            c_names = _extract_entity_names(c["entities"])
            c_keywords = _content_keywords(c["fact_text"])
            # v2.2 fix #6 — β-2 walk-back: allow minority-category members so
            # scenario_synthesis isn't throughput-starved. We no longer reject
            # candidates whose category differs from the cluster seed; instead
            # we enforce a ≥75% majority-category rule at cluster-close time.
            # Require shared entity NAMES or strong meaningful keyword overlap
            name_overlap = bool(cluster_names & c_names)
            keyword_overlap = len(cluster_keywords & c_keywords) >= 4
            if name_overlap or keyword_overlap:
                cluster.append(c)
                cluster_names |= c_names
                cluster_keywords |= c_keywords

        if len(cluster) >= cluster_size:
            cluster = cluster[:cluster_size]
            # v2.2 fix #6 — require ≥75% of classified-category facts in the
            # cluster to share the majority category. Unclassifiable (None)
            # facts don't count toward either numerator or denominator.
            cats_in_cluster = [
                _classify_wine_category(f["fact_text"]) for f in cluster
            ]
            classified = [c for c in cats_in_cluster if c is not None]
            if classified:
                from collections import Counter as _C
                top_cat, top_count = _C(classified).most_common(1)[0]
                purity = top_count / len(classified)
                if purity < 0.75:
                    logger.debug(
                        f"Cluster rejected — category purity {purity:.2f} < 0.75 "
                        f"(top={top_cat}, counts={_C(classified)})"
                    )
                    continue
                logger.debug(
                    f"Cluster accepted — category purity {purity:.2f} "
                    f"(top={top_cat}, counts={_C(classified)})"
                )
            # v2.3 Phase F — iconic anchor requirement. A cluster where EVERY
            # fact is iconic-only produces a world-knowledge-solvable scenario
            # ("A sommelier presents Château Margaux, Lafite, and Latour…").
            # Require ≥1 non-iconic fact to anchor the scenario on a
            # fact-specific attribute.
            if not _bundle_has_non_iconic_anchor(cluster):
                iconic_bundle_rejected += 1
                continue
            # Per-call absolute cap pre-check (Team ε). Tally added counts
            # per country and reject the whole cluster if any country would
            # overshoot the per-call max.
            if per_call_max is not None:
                added_per_country: dict[str, int] = defaultdict(int)
                for f in cluster:
                    c = _extract_country_from_entities(f.get("entities"))
                    if c is not None:
                        added_per_country[c] += 1
                if any(
                    per_call_country_count[c] + n > per_call_max
                    for c, n in added_per_country.items()
                ):
                    per_call_capped += 1
                    continue

            # v2.3 fix #17 — admit the whole cluster under the 1.2x cap
            # atomically. If any fact's country would push it over, reject
            # the whole cluster and roll back partial admissions.
            admitted_countries: list[str | None] = []
            ok = True
            for f in cluster:
                c = _extract_country_from_entities(f.get("entities"))
                if _cap_admit_and_record(c):
                    admitted_countries.append(c)
                else:
                    ok = False
                    break
            if not ok:
                with _QUOTA_LOCK:
                    global _TOTAL_RETURNED, _TOTAL_RETURNED_TAGGED
                    for c in admitted_countries:
                        _TOTAL_RETURNED -= 1
                        if c:
                            _TOTAL_RETURNED_TAGGED -= 1
                            if _COUNTRY_USAGE.get(c, 0) > 0:
                                _COUNTRY_USAGE[c] -= 1
                                if _COUNTRY_USAGE[c] == 0:
                                    del _COUNTRY_USAGE[c]
                logger.debug(
                    "sample_fact_clusters: cluster rejected by country cap"
                )
                continue
            clusters.append(cluster)
            # Per-call cap bookkeeping (Team ε): commit per-country adds.
            if per_call_max is not None:
                for c, n in added_per_country.items():
                    per_call_country_count[c] += n

    if iconic_bundle_rejected:
        logger.debug(
            f"sample_fact_clusters: rejected {iconic_bundle_rejected} "
            f"iconic-only clusters (v2.3 Phase F — no non-iconic anchor)"
        )
    if per_call_capped:
        logger.debug(
            f"sample_fact_clusters: skipped {per_call_capped} clusters blocked "
            f"by per-call cap (per_country_cap={per_country_cap})"
        )

    _assert_batch_under_cap("sample_fact_clusters", [
        _extract_country_from_entities(f.get("entities"))
        for cluster in clusters for f in cluster
    ])

    logger.debug(f"Sampled {len(clusters)} cohesive fact clusters for domain={domain}")
    return clusters


def sample_confusable_facts(
    target_fact: dict,
    domain: str,
    count: int = 4,
    exclude_ids: set[str] | None = None,
    per_country_cap: float | None = None,
) -> list[dict]:
    """Sample dimension-aware confusable facts for distractor mining.

    Finds facts from the SAME subdomain or with overlapping entity types,
    so distractors are plausible alternatives — not obviously unrelated.
    Dimension-matched distractors (same attribute as target) are ranked first.

    Each returned fact dict is enriched with:
      _dimension: str | None  — classified semantic dimension
      _confusability_context: str — why this distractor is confusable with target

    Args:
        per_country_cap: Team ε D3-fix v3. When set to a fraction in (0, 1],
            no single country may contribute more than
            ``ceil(per_country_cap * count)`` distractors to the returned set.
            Note that this scope is per-call and EXCLUDES the target fact;
            callers responsible for whole-bundle cap accounting (target +
            distractors) should not rely on this kwarg alone for that.
            Default ``None`` preserves the prior behaviour (no per-call cap).

            Within distractor mining the same-country filtering is already
            quite tight — Priority 1 candidates all share the target's
            country — so a per-call cap below 1.0 will effectively shrink
            the returned distractor count when the target has a "popular"
            country. This is intentional: under-supplying distractors is
            preferable to over-representing a single country across the
            audit corpus.
    """
    conn = get_pg()
    cur = conn.cursor()
    exclude = list(exclude_ids or set()) + [str(target_fact["id"])]
    target_sub = target_fact.get("subdomain")
    target_types = _extract_entity_types(target_fact["entities"])

    target_map = _extract_entity_map(target_fact["entities"])
    target_names = _extract_entity_names(target_fact["entities"])
    target_dim = _classify_dimension(target_fact["fact_text"])
    target_cat = _classify_wine_category(target_fact["fact_text"])

    # Find the target's country for same-country filtering
    target_country = None
    for c in target_map.get("country", set()):
        target_country = c
        break

    # Collect all viable candidates with dimension + affinity metadata
    candidates: list[tuple[float, dict]] = []

    # Priority 1: same country + same entity type, different entity name
    if target_country and target_types:
        primary_type = next(
            (t for t in ("region", "grape", "appellation", "producer", "ava")
             if t in target_types),
            None,
        )
        if primary_type:
            cur.execute(
                """
                SELECT f.id, f.fact_text, f.domain, f.subdomain,
                       f.entities, f.source_id, s.name AS source_name,
                       s.url AS source_url, f.confidence, f.tags
                FROM facts f
                JOIN sources s ON s.id = f.source_id
                WHERE f.domain = %s
                  AND f.confidence >= 0.7
                  AND f.entities != '[]'::jsonb
                  AND NOT (f.id = ANY(%s::uuid[]))
                  AND EXISTS (
                      SELECT 1 FROM jsonb_array_elements(f.entities) e
                      WHERE e->>'type' = 'country' AND e->>'name' = %s
                  )
                  AND EXISTS (
                      SELECT 1 FROM jsonb_array_elements(f.entities) e
                      WHERE e->>'type' = %s
                  )
                ORDER BY random()
                LIMIT %s
                """,
                (domain, exclude, target_country, primary_type, count * 8),
            )
            for r in cur.fetchall():
                r = dict(r)
                if not _is_fact_specific(r["fact_text"]):
                    continue
                if not _is_fact_rich(r["fact_text"]):
                    continue
                r_names = _extract_entity_names(r["entities"])
                if not r_names or r_names == target_names:
                    continue

                r_dim = _classify_dimension(r["fact_text"])
                r_cat = _classify_wine_category(r["fact_text"])
                # Plan §10 — wine-category leak guard. If the target has a
                # detectable category, REJECT mismatched candidates outright
                # rather than down-weighting (the audit showed soft penalties
                # weren't enough to keep cross-category distractors out).
                if target_cat and r_cat and r_cat != target_cat:
                    continue
                # Score: base 1.0 for Priority 1, +0.5 for dimension match
                score = 1.0
                ctx_parts = [f"same country ({target_country})", f"same {primary_type} type"]
                if target_dim and r_dim == target_dim:
                    score += 0.5
                    ctx_parts.append(f"same dimension ({target_dim})")
                elif target_dim and r_dim and r_dim != target_dim:
                    score -= 0.2
                if target_cat and r_cat == target_cat:
                    score += 0.3
                    ctx_parts.append(f"same wine category ({target_cat})")
                r["_dimension"] = r_dim
                r["_confusability_context"] = "; ".join(ctx_parts)
                candidates.append((score, r))

    # Priority 2: same subdomain, different entities (fallback)
    if target_sub:
        already = {str(c["id"]) for _, c in candidates}
        cur.execute(
            """
            SELECT f.id, f.fact_text, f.domain, f.subdomain,
                   f.entities, f.source_id, s.name AS source_name,
                   s.url AS source_url, f.confidence, f.tags
            FROM facts f
            JOIN sources s ON s.id = f.source_id
            WHERE f.domain = %s
              AND f.subdomain = %s
              AND f.confidence >= 0.7
              AND f.entities != '[]'::jsonb
              AND NOT (f.id = ANY(%s::uuid[]))
            ORDER BY random()
            LIMIT %s
            """,
            (domain, target_sub, exclude + list(already), count * 5),
        )
        for r in cur.fetchall():
            r = dict(r)
            if not _is_fact_specific(r["fact_text"]):
                continue
            if not _is_fact_rich(r["fact_text"]):
                continue
            r_names = _extract_entity_names(r["entities"])
            if not r_names or r_names == target_names:
                continue
            if str(r["id"]) in already:
                continue

            r_map = _extract_entity_map(r["entities"])
            affinity, reason = _entity_affinity_score(target_map, r_map)
            r_dim = _classify_dimension(r["fact_text"])
            r_cat = _classify_wine_category(r["fact_text"])

            # Plan §10 — wine-category leak guard (mandatory in fallback path
            # too). Reject candidates whose detectable category disagrees
            # with the target's.
            if target_cat and r_cat and r_cat != target_cat:
                continue

            # Score: base from affinity, +0.5 for dimension match
            score = affinity
            ctx_parts = [reason] if reason != "no shared context" else [f"same subdomain ({target_sub})"]
            if target_dim and r_dim == target_dim:
                score += 0.5
                ctx_parts.append(f"same dimension ({target_dim})")
            if target_cat and r_cat == target_cat:
                score += 0.3
                ctx_parts.append(f"same wine category ({target_cat})")
            r["_dimension"] = r_dim
            r["_confusability_context"] = "; ".join(ctx_parts)
            candidates.append((score, r))

    # Phase 2g.17: ubiquitous-grape sibling filter — when the TARGET fact has a
    # ubiquitous grape (e.g. Cabernet), drop any candidate that ALSO has the
    # SAME ubiquitous grape. Keeping same-ubiquitous-grape siblings would make
    # "which region produces Cabernet?" a correct answer for multiple distractors.
    target_text = target_fact["fact_text"]
    if _fact_has_ubiquitous_grape(target_text):
        target_grape = _normalise_grape_name(_extract_grape_name(target_text) or "")
        before_count = len(candidates)
        candidates = [
            (score, c) for score, c in candidates
            if not (_fact_has_ubiquitous_grape(c["fact_text"])
                    and _normalise_grape_name(_extract_grape_name(c["fact_text"]) or "") == target_grape)
        ]
        dropped = before_count - len(candidates)
        if dropped:
            global _UBIQUITY_FILTERED_COUNT
            _UBIQUITY_FILTERED_COUNT += dropped

    # Sort by score descending — dimension-matched distractors first
    candidates.sort(key=lambda x: x[0], reverse=True)

    # v2.3 fix #17 — walk the ranked candidate list, admitting one at a time
    # under the 1.2x cap. Unlike pairs/groups/clusters which are atomic, each
    # distractor is independent, so we simply skip a candidate whose country
    # is already over quota and keep looking.
    confusable: list[dict] = []
    capped = 0
    per_call_capped = 0

    # Per-call absolute cap (Team ε). Applied per-call across the returned
    # distractor list (target itself excluded). Most distractor calls already
    # have a tight country filter via Priority 1, so this cap is more relevant
    # for the rare Priority 2 fallback path.
    per_call_max = (
        _country_cap_max(per_country_cap, count)
        if per_country_cap is not None
        else None
    )
    per_call_country_count: dict[str, int] = defaultdict(int)

    for score, cand in candidates:
        if len(confusable) >= count:
            break
        c = _extract_country_from_entities(cand.get("entities"))
        # Per-call cap pre-check (Team ε).
        if per_call_max is not None and c is not None:
            if per_call_country_count[c] >= per_call_max:
                per_call_capped += 1
                continue
        if _cap_admit_and_record(c):
            confusable.append(cand)
            if per_call_max is not None and c is not None:
                per_call_country_count[c] += 1
        else:
            capped += 1

    if capped:
        logger.debug(
            f"sample_confusable_facts: skipped {capped} distractors blocked by country cap"
        )
    if per_call_capped:
        logger.debug(
            f"sample_confusable_facts: skipped {per_call_capped} distractors "
            f"blocked by per-call cap (per_country_cap={per_country_cap})"
        )

    # v2.3 Phase F — iconic anchor requirement for distractor-mining. If BOTH
    # the target and every distractor are iconic-only, the resulting MC
    # question is world-knowledge-solvable (all four options are famous
    # entities a well-read taster can recall). Require ≥1 non-iconic anchor
    # in the target+distractor bundle — mirrors the bundle rule used by
    # comparative/scenario sampling above.
    bundle_for_anchor = [target_fact, *confusable]
    if confusable and not _bundle_has_non_iconic_anchor(bundle_for_anchor):
        logger.debug(
            f"sample_confusable_facts: bundle all iconic-only for target="
            f"{target_fact['id']} — rejecting distractors (v2.3 Phase F)"
        )
        # Roll back the country-quota admissions for the rejected distractors
        # so the counters stay consistent with the audit D3 contract.
        with _QUOTA_LOCK:
            global _TOTAL_RETURNED, _TOTAL_RETURNED_TAGGED
            for cand in confusable:
                c = _extract_country_from_entities(cand.get("entities"))
                _TOTAL_RETURNED -= 1
                if c:
                    _TOTAL_RETURNED_TAGGED -= 1
                    if _COUNTRY_USAGE.get(c, 0) > 0:
                        _COUNTRY_USAGE[c] -= 1
                        if _COUNTRY_USAGE[c] == 0:
                            del _COUNTRY_USAGE[c]
        confusable = []

    _assert_batch_under_cap("sample_confusable_facts", [
        _extract_country_from_entities(f.get("entities")) for f in confusable
    ])

    logger.debug(
        f"Sampled {len(confusable)} confusable facts for target={target_fact['id']} "
        f"(target_dim={target_dim})"
    )
    return confusable


_NUMERIC_DISTRACTOR_DIMS = {"area_size", "production_volume", "alcohol_level", "yield_regulation"}


def _auto_distractor_type(
    target_dim: str | None,
    distractor_dims: list[str | None],
) -> str:
    """Auto-select distractor question type based on dimension alignment.

    - numeric: target has a numeric dimension and majority of distractors share it
    - attribute_swap: target dimension matches majority of distractors
    - entity_id: mixed or unclassified dimensions (fallback)
    """
    if not target_dim or not distractor_dims:
        return "entity_id"

    matched = sum(1 for d in distractor_dims if d == target_dim)
    majority = matched >= len(distractor_dims) / 2

    if target_dim in _NUMERIC_DISTRACTOR_DIMS and majority:
        return "numeric"
    if majority:
        return "attribute_swap"
    return "entity_id"


# ─── A2 length normaliser stub (plan §11) ───────────────────────────────────


def _normalize_option_lengths(
    options: list[dict],
    correct_id: str,
    target_pct: float = 0.20,
) -> list[dict]:
    """Pad/trim distractor option texts to within ±target_pct of the correct
    option's length.

    This is a P2 stub. Per the improvement plan §11, the option-shuffle in
    ``src/generators/_schemas.py`` (Team α scope) is the primary fix for A2
    position/length bias. This length-normaliser is only wired in if A2
    continues to flag length-bias failures after the shuffle is verified to
    run unconditionally. Until then the function is intentionally NOT called
    from any sampling or generation path.

    Args:
        options: list of option dicts with at least ``id`` and ``text`` keys.
        correct_id: the ``id`` of the correct option (its length is the
            target the others get normalised against).
        target_pct: half-width of the allowed length band as a fraction of
            the correct option's length (default 0.20 = ±20%).

    Returns:
        A new list of option dicts; the correct option is unchanged, and any
        distractor whose text length falls outside the allowed band is
        adjusted (truncated or padded with neutral filler) to land within it.
        Currently a no-op pending verification of the upstream shuffle.
    """
    # Intentional no-op stub — see docstring. Returns input unchanged so
    # call sites can be wired in safely once the upstream A2 fix is verified.
    return list(options)


def get_domain_stats() -> dict:
    """Return {domain: {total, with_entities, avg_confidence}} for coverage analysis."""
    conn = get_pg()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
            domain,
            count(*) AS total,
            count(*) FILTER (WHERE entities != '[]'::jsonb) AS with_entities,
            round(avg(confidence)::numeric, 3) AS avg_confidence
        FROM facts
        GROUP BY domain
        ORDER BY domain
        """
    )
    return {
        row["domain"]: {
            "total": row["total"],
            "with_entities": row["with_entities"],
            "avg_confidence": float(row["avg_confidence"]),
        }
        for row in cur.fetchall()
    }
