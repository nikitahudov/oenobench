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


def sample_fact_pairs(
    domain: str,
    count: int,
    exclude_ids: set[str] | None = None,
) -> list[tuple[dict, dict]]:
    """Sample pairs of facts from same domain but different subdomains for comparative questions."""
    conn = get_pg()
    cur = conn.cursor()
    exclude = list(exclude_ids) if exclude_ids else []

    # Get facts grouped by subdomain, then form cross-subdomain pairs
    cur.execute(
        """
        SELECT f.id, f.fact_text, f.domain, f.subdomain,
               f.entities, f.source_id, s.name AS source_name,
               s.url AS source_url, f.confidence, f.tags
        FROM facts f
        JOIN sources s ON s.id = f.source_id
        WHERE f.domain = %s
          AND f.subdomain IS NOT NULL
          AND f.confidence >= 0.7
          AND NOT (f.id = ANY(%s::uuid[]))
        ORDER BY random()
        LIMIT %s
        """,
        (domain, exclude, count * 4),
    )
    rows = [dict(r) for r in cur.fetchall()]

    # Group by subdomain
    by_sub: dict[str, list[dict]] = {}
    for row in rows:
        by_sub.setdefault(row["subdomain"], []).append(row)

    # Form pairs from different subdomains
    subdomains = list(by_sub.keys())
    pairs: list[tuple[dict, dict]] = []
    for i in range(len(subdomains)):
        for j in range(i + 1, len(subdomains)):
            for a in by_sub[subdomains[i]]:
                for b in by_sub[subdomains[j]]:
                    pairs.append((a, b))
                    if len(pairs) >= count:
                        logger.debug(f"Sampled {len(pairs)} fact pairs for domain={domain}")
                        return pairs
    logger.debug(f"Sampled {len(pairs)} fact pairs for domain={domain}")
    return pairs


def sample_fact_clusters(
    domain: str,
    count: int,
    cluster_size: int = 3,
    exclude_ids: set[str] | None = None,
) -> list[list[dict]]:
    """Sample clusters of related facts (same subdomain) for scenario synthesis."""
    conn = get_pg()
    cur = conn.cursor()
    exclude = list(exclude_ids) if exclude_ids else []

    # Get subdomains that have enough facts
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
        (domain, exclude, cluster_size),
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
            (domain, sub, exclude, cluster_size),
        )
        cluster = [dict(r) for r in cur.fetchall()]
        if len(cluster) == cluster_size:
            clusters.append(cluster)

    logger.debug(f"Sampled {len(clusters)} fact clusters for domain={domain}")
    return clusters


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
