"""
OenoBench — Stratified fact sampling from PostgreSQL.

Selects facts for question generation with source diversity,
confidence filtering, and support for comparative / cluster queries.
"""

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
    r"one of the (?:best|finest|greatest|most important)|"
    r"is famous for its|is known for its quality)\b"
    # ── Gold-sheet review additions (no_vague_language flagged rows) ──
    # Ambiguous demonstrative referents — "these wines", "these Bordeaux
    # wines", "this wine" with no in-stem antecedent.
    r"|\bthese\s+(?:wines?|bordeaux\s+wines?|grapes?|producers?|appellations?|regions?)\b"
    r"|\bthis\s+wine\b"
    # Soft hedging that signals the stem doesn't actually use the source fact
    # (e.g. "Which country is considered the origin of Malbec?" — solvable
    # from common knowledge, no source needed).
    r"|\b(?:is|are)\s+considered\s+(?:the|to\s+be)\b"
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

_COUNTRY_QUOTA_HARD_CAP_RATIO = 1.5  # plan §3 — never exceed 1.5× base share
_QUOTA_LOCK = threading.Lock()
_COUNTRY_USAGE: dict[str, int] = defaultdict(int)
_TOTAL_RETURNED: int = 0


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
    global _TOTAL_RETURNED
    with _QUOTA_LOCK:
        _COUNTRY_USAGE.clear()
        _TOTAL_RETURNED = 0


def get_country_usage() -> tuple[dict[str, int], int]:
    """Return a snapshot ``(usage_counter_copy, total_returned)`` for tests."""
    with _QUOTA_LOCK:
        return dict(_COUNTRY_USAGE), _TOTAL_RETURNED


def _record_country_use(country: str | None) -> None:
    """Increment usage counters for a returned fact's country.

    Facts without an extractable country are still counted toward the total
    (so the hard cap denominator reflects all returned facts), but they don't
    increment any per-country bucket.
    """
    global _TOTAL_RETURNED
    with _QUOTA_LOCK:
        _TOTAL_RETURNED += 1
        if country:
            _COUNTRY_USAGE[country] += 1


_QUOTA_GRACE_N = 10  # cap is not enforced until at least N facts have been returned


def _country_quota_score(country: str | None) -> float:
    """Multiplicative weight in [0, 1] for a candidate fact's country.

    - Returns 1.0 if the country is unknown or the base distribution couldn't
      be computed (no down-weighting if we have no signal).
    - Returns 0.0 if the country has already reached its 1.5× hard cap, i.e.
      ``used >= 1.5 × target_share × total_returned`` AND
      ``total_returned >= _QUOTA_GRACE_N``. The grace period prevents the
      cap tautologically firing at small-N (the very first sample would
      otherwise always be 100% of the total and trip the cap).
    - Otherwise returns ``min(1.0, target_share / max(used_share, eps))`` so
      countries at or below target share keep a weight of 1.0 and over-quota
      countries are progressively penalised.
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
        total = _TOTAL_RETURNED

    # Hard cap: country has already reached 1.5× its target share. Apply only
    # once we've accumulated enough samples that the cap is meaningful — at
    # tiny totals (e.g. the first few samples) every category trivially
    # exceeds 1.5× by virtue of being 100% of the total.
    if total >= _QUOTA_GRACE_N:
        cap_count = _COUNTRY_QUOTA_HARD_CAP_RATIO * target_share * total
        if used >= cap_count:
            return 0.0

    if total == 0:
        return 1.0
    used_share = used / total
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
) -> list[dict]:
    """Sample facts from PostgreSQL for question generation.

    Returns list of dicts with keys: id, fact_text, domain, subdomain,
    entities, source_id, source_name, source_url, confidence, tags.

    Args:
        wine_category: optional wine category filter ("red", "white",
            "sparkling", "rosé", "fortified"). When set, only facts whose
            ``_classify_wine_category`` matches are returned. Default ``None``
            preserves the legacy behaviour (no category filtering).
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
    category_filtered = 0
    for r in rows:
        if not _is_fact_specific(r["fact_text"]):
            quality_filtered += 1
            continue
        if wine_category is not None:
            cat = _classify_wine_category(r["fact_text"])
            if cat != wine_category:
                category_filtered += 1
                continue
        candidates.append((1.0, dict(r)))

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

    results: list[dict] = []
    for _, fact in weighted:
        if len(results) >= count:
            break
        country = _extract_country_from_entities(fact.get("entities"))
        # Re-check the cap with the now-incremented totals so a streak of
        # same-country candidates can't slip past the gate.
        if _country_quota_score(country) <= 0.0:
            capped += 1
            continue
        _record_country_use(country)
        results.append(fact)

    if quality_filtered:
        logger.debug(f"Filtered {quality_filtered} vague/marketing facts")
    if category_filtered:
        logger.debug(f"Filtered {category_filtered} facts not matching wine_category={wine_category}")
    if capped:
        logger.debug(f"Skipped {capped} facts capped by country quota")
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
) -> list[tuple[dict, dict]]:
    """Sample pairs of comparable facts about different entities of the same type.

    Uses SQL to find facts about different appellations/regions/grapes/producers
    within the same subdomain — e.g., two Italian DOCGs with aging requirements,
    two Bordeaux châteaux, two grapes from the same country. This produces
    meaningful comparisons like "Both Barolo and Barbaresco are Piedmont DOCGs.
    Which requires longer minimum aging?"
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
        # Record country usage for both facts in the pair so the per-country
        # quota in sample_facts/sample_confusable_facts stays in sync across
        # strategies sharing the same generation run.
        _record_country_use(_extract_country_from_entities(fact_a.get("entities")))
        _record_country_use(_extract_country_from_entities(fact_b.get("entities")))
        pairs.append((fact_a, fact_b))
        seen_ids.update({a_id, b_id})

    logger.debug(
        f"Sampled {len(pairs)} entity-matched fact pairs for domain={domain}"
    )
    return pairs


def sample_fact_groups(
    domain: str,
    count: int,
    group_size: int = 3,
    exclude_ids: set[str] | None = None,
) -> list[list[dict]]:
    """Sample groups of 3-4 dimension-matched facts for multi-entity comparisons.

    Groups facts by (country, entity_type, dimension) to ensure all facts
    in a group discuss the same attribute about different but comparable entities.
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
            groups.append(selected)

    groups.sort(
        key=lambda g: sum(len(f["fact_text"]) for f in g),
        reverse=True,
    )

    logger.debug(
        f"Sampled {min(len(groups), count)} fact groups (size={group_size}) for domain={domain}"
    )
    return groups[:count]


def sample_fact_clusters(
    domain: str,
    count: int,
    cluster_size: int = 3,
    exclude_ids: set[str] | None = None,
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
        # Filter vague and thin geographic facts
        candidates = [
            c for c in candidates
            if _is_fact_specific(c["fact_text"]) and _is_fact_rich(c["fact_text"])
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
            c_category = _classify_wine_category(c["fact_text"])
            # Plan §10 — wine-category cohesion. If both the cluster and this
            # candidate have a detectable category and they DIFFER, skip the
            # candidate. Unclassifiable candidates (None) are allowed.
            if cluster_category and c_category and cluster_category != c_category:
                continue
            # Require shared entity NAMES or strong meaningful keyword overlap
            name_overlap = bool(cluster_names & c_names)
            keyword_overlap = len(cluster_keywords & c_keywords) >= 4
            if name_overlap or keyword_overlap:
                cluster.append(c)
                cluster_names |= c_names
                cluster_keywords |= c_keywords
                # Lock in the cluster's category once any classified fact lands
                # so subsequent additions are filtered against it.
                if cluster_category is None and c_category is not None:
                    cluster_category = c_category

        if len(cluster) >= cluster_size:
            cluster = cluster[:cluster_size]
            # Final cohesion check — defensive belt-and-braces: if the picked
            # cluster ended up mixing categories (shouldn't happen given the
            # per-step filter above, but guard against future refactors), drop
            # the cluster.
            cats_in_cluster = {
                _classify_wine_category(f["fact_text"]) for f in cluster
            } - {None}
            if len(cats_in_cluster) > 1:
                continue
            for f in cluster:
                _record_country_use(_extract_country_from_entities(f.get("entities")))
            clusters.append(cluster)

    logger.debug(f"Sampled {len(clusters)} cohesive fact clusters for domain={domain}")
    return clusters


def sample_confusable_facts(
    target_fact: dict,
    domain: str,
    count: int = 4,
    exclude_ids: set[str] | None = None,
) -> list[dict]:
    """Sample dimension-aware confusable facts for distractor mining.

    Finds facts from the SAME subdomain or with overlapping entity types,
    so distractors are plausible alternatives — not obviously unrelated.
    Dimension-matched distractors (same attribute as target) are ranked first.

    Each returned fact dict is enriched with:
      _dimension: str | None  — classified semantic dimension
      _confusability_context: str — why this distractor is confusable with target
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

    # Sort by score descending — dimension-matched distractors first
    candidates.sort(key=lambda x: x[0], reverse=True)
    confusable = [c for _, c in candidates[:count]]

    # Track per-country usage so distractor sampling participates in the
    # session-level country quota too.
    for f in confusable:
        _record_country_use(_extract_country_from_entities(f.get("entities")))

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
