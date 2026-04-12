"""
OenoBench — Stratified fact sampling from PostgreSQL.

Selects facts for question generation with source diversity,
confidence filtering, and support for comparative / cluster queries.
"""

import re

from loguru import logger

from src.utils.db import get_pg

# ─── Fact quality filters ─────────────────────────────────────────────────────

# Patterns that indicate vague, subjective, or marketing-style facts
_VAGUE_PATTERNS = re.compile(
    r"\b("
    r"highly regarded|world-famous|renowned|prestigious|legendary|iconic|"
    r"intriguing|fascinating|exceptional|extraordinary|outstanding|"
    r"best known|most famous|widely celebrated|greatly admired|"
    r"discover the|visit our|come and|join us|book now|must-visit|"
    r"one of the (best|finest|greatest|most important)|"
    r"is famous for its|is known for its quality"
    r")\b",
    re.IGNORECASE,
)

# Minimum word count for a fact to be specific enough
_MIN_SPECIFIC_WORDS = 8


def _is_fact_specific(fact_text: str) -> bool:
    """Check if a fact is specific enough for question generation.

    Rejects vague, subjective, or marketing-style facts.
    """
    if len(fact_text.split()) < _MIN_SPECIFIC_WORDS:
        return False
    if _VAGUE_PATTERNS.search(fact_text):
        return False
    return True


# ─── Domain question targets (for quota tracking) ───────────────────────────

DOMAIN_TARGETS = {
    "wine_regions": 3500,
    "winemaking": 2000,
    "viticulture": 1500,
    "grape_varieties": 1200,
    "wine_business": 1000,
    "producers": 800,
}


def sample_facts(
    domain: str,
    count: int,
    min_confidence: float = 0.7,
    exclude_ids: set[str] | None = None,
    prefer_diverse_sources: bool = True,
) -> list[dict]:
    """Sample facts from PostgreSQL for question generation.

    Returns list of dicts with keys: id, fact_text, domain, subdomain,
    entities, source_id, source_name, source_url, confidence, tags.
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

    # Over-fetch to account for quality filtering
    cur.execute(query, (domain, min_confidence, exclude, count * 3))
    rows = cur.fetchall()

    # Filter out vague/marketing facts
    results = []
    filtered = 0
    for r in rows:
        if _is_fact_specific(r["fact_text"]):
            results.append(dict(r))
            if len(results) >= count:
                break
        else:
            filtered += 1

    if filtered:
        logger.debug(f"Filtered {filtered} vague/marketing facts")
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
    # of the same type within the same subdomain, where both facts are specific
    # enough for comparison (contain requirements, numbers, classifications, etc.)
    cur.execute(
        """
        WITH entity_facts AS (
            SELECT f.id, f.fact_text, f.domain, f.subdomain,
                   f.entities, f.source_id, s.name AS source_name,
                   s.url AS source_url, f.confidence, f.tags,
                   e->>'type' AS etype, e->>'name' AS ename
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
          ON a.subdomain = b.subdomain
          AND a.etype = b.etype
          AND a.ename != b.ename
          AND a.id < b.id
        ORDER BY random()
        LIMIT %s
        """,
        (domain, exclude, count * 3),
    )

    rows = cur.fetchall()
    pairs: list[tuple[dict, dict]] = []
    seen_ids: set[str] = set()

    for row in rows:
        if len(pairs) >= count:
            break
        a_id, b_id = str(row["a_id"]), str(row["b_id"])
        # Avoid reusing the same fact in multiple pairs
        if a_id in seen_ids or b_id in seen_ids:
            continue
        a_text, b_text = row["a_text"], row["b_text"]
        if not _is_fact_specific(a_text) or not _is_fact_specific(b_text):
            continue

        fact_a = {
            "id": row["a_id"], "fact_text": a_text,
            "domain": row["a_domain"], "subdomain": row["a_sub"],
            "entities": row["a_entities"], "source_id": row["a_source_id"],
            "source_name": row["a_source_name"], "source_url": row["a_source_url"],
            "confidence": row["a_confidence"], "tags": row["a_tags"],
        }
        fact_b = {
            "id": row["b_id"], "fact_text": b_text,
            "domain": row["a_domain"], "subdomain": row["b_sub"],
            "entities": row["b_entities"], "source_id": row["b_source_id"],
            "source_name": row["b_source_name"], "source_url": row["b_source_url"],
            "confidence": row["b_confidence"], "tags": row["b_tags"],
        }
        pairs.append((fact_a, fact_b))
        seen_ids.update({a_id, b_id})

    logger.debug(
        f"Sampled {len(pairs)} entity-matched fact pairs for domain={domain}"
    )
    return pairs


def sample_fact_clusters(
    domain: str,
    count: int,
    cluster_size: int = 3,
    exclude_ids: set[str] | None = None,
) -> list[list[dict]]:
    """Sample clusters of cohesive, related facts for scenario synthesis.

    Facts in each cluster come from the same subdomain and share entity
    types or keywords, ensuring they can form a coherent scenario.
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
            (domain, sub, exclude, cluster_size * 3),
        )
        candidates = [dict(r) for r in cur.fetchall()]
        # Filter vague facts
        candidates = [c for c in candidates if _is_fact_specific(c["fact_text"])]

        if len(candidates) < cluster_size:
            continue

        # Pick a cohesive cluster: start with first fact, greedily add facts
        # that share entity types or keyword overlap with existing cluster
        cluster = [candidates[0]]
        cluster_types = _extract_entity_types(candidates[0]["entities"])
        cluster_words = set(candidates[0]["fact_text"].lower().split())

        for c in candidates[1:]:
            if len(cluster) >= cluster_size:
                break
            c_types = _extract_entity_types(c["entities"])
            c_words = set(c["fact_text"].lower().split())
            # Require shared entity types OR significant keyword overlap
            type_overlap = bool(cluster_types & c_types)
            word_overlap = len(cluster_words & c_words) >= 3
            if type_overlap or word_overlap:
                cluster.append(c)
                cluster_types |= c_types
                cluster_words |= c_words

        if len(cluster) >= cluster_size:
            clusters.append(cluster[:cluster_size])

    logger.debug(f"Sampled {len(clusters)} cohesive fact clusters for domain={domain}")
    return clusters


def sample_confusable_facts(
    target_fact: dict,
    domain: str,
    count: int = 4,
    exclude_ids: set[str] | None = None,
) -> list[dict]:
    """Sample facts about confusable entities for distractor mining.

    Finds facts from the SAME subdomain or with overlapping entity types,
    so distractors are plausible alternatives — not obviously unrelated.
    """
    conn = get_pg()
    cur = conn.cursor()
    exclude = list(exclude_ids or set()) + [str(target_fact["id"])]
    target_sub = target_fact.get("subdomain")
    target_types = _extract_entity_types(target_fact["entities"])

    confusable: list[dict] = []

    # Priority 1: same subdomain, different entities (strongest confusability)
    if target_sub:
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
            (domain, target_sub, exclude, count * 3),
        )
        rows = [dict(r) for r in cur.fetchall()]
        target_names = _extract_entity_names(target_fact["entities"])
        for r in rows:
            if not _is_fact_specific(r["fact_text"]):
                continue
            r_names = _extract_entity_names(r["entities"])
            # Must be about a different entity (not the same one)
            if r_names and r_names != target_names:
                confusable.append(r)
                if len(confusable) >= count:
                    break

    # Priority 2: different subdomain but shared entity types
    if len(confusable) < count and target_types:
        already = {str(c["id"]) for c in confusable}
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
            ORDER BY random()
            LIMIT %s
            """,
            (domain, exclude + list(already), count * 5),
        )
        for r in cur.fetchall():
            r = dict(r)
            if not _is_fact_specific(r["fact_text"]):
                continue
            r_types = _extract_entity_types(r["entities"])
            r_names = _extract_entity_names(r["entities"])
            target_names = _extract_entity_names(target_fact["entities"])
            if r_types & target_types and r_names != target_names:
                confusable.append(r)
                if len(confusable) >= count:
                    break

    logger.debug(
        f"Sampled {len(confusable)} confusable facts for target={target_fact['id']}"
    )
    return confusable


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
