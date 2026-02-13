"""
OenoBench — Fact storage helpers.

Inserts sources and facts into PostgreSQL with deduplication.
"""

import uuid
from datetime import date
from typing import Optional

from loguru import logger

from src.utils.db import get_pg


def ensure_source(
    name: str,
    url: str,
    source_type: str,
    tier: str = "tier_3_reliable",
    language: str = "en",
) -> str:
    """Insert a source if it doesn't exist, return its UUID."""
    conn = get_pg()
    cur = conn.cursor()

    # Check if source already exists by URL
    cur.execute("SELECT id FROM sources WHERE url = %s", (url,))
    row = cur.fetchone()
    if row:
        return str(row["id"])

    source_id = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO sources (id, name, url, source_type, tier, language, accessed_date)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """,
        (source_id, name, url, source_type, tier, language, date.today()),
    )
    conn.commit()
    logger.debug(f"Added source: {name}")
    return source_id


def insert_fact(
    fact_text: str,
    domain: str,
    source_id: str,
    subdomain: Optional[str] = None,
    entities: Optional[list] = None,
    confidence: float = 1.0,
    tags: Optional[list] = None,
) -> Optional[str]:
    """Insert a fact into PostgreSQL. Returns fact UUID or None if duplicate."""
    conn = get_pg()
    cur = conn.cursor()

    # Simple duplicate check on exact fact_text
    cur.execute("SELECT id FROM facts WHERE fact_text = %s", (fact_text,))
    if cur.fetchone():
        return None

    import orjson

    fact_id = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO facts (id, fact_text, domain, subdomain, entities, source_id, confidence, tags)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            fact_id,
            fact_text,
            domain,
            subdomain,
            orjson.dumps(entities or []).decode(),
            source_id,
            confidence,
            tags or [],
        ),
    )
    conn.commit()
    return fact_id


def insert_facts_batch(facts: list[dict], batch_size: int = 100) -> int:
    """Insert multiple facts efficiently. Returns count of new facts inserted."""
    conn = get_pg()
    cur = conn.cursor()
    inserted = 0

    import orjson

    for i in range(0, len(facts), batch_size):
        batch = facts[i : i + batch_size]
        for fact in batch:
            cur.execute("SELECT 1 FROM facts WHERE fact_text = %s", (fact["fact_text"],))
            if cur.fetchone():
                continue

            cur.execute(
                """
                INSERT INTO facts (id, fact_text, domain, subdomain, entities, source_id, confidence, tags)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    str(uuid.uuid4()),
                    fact["fact_text"],
                    fact["domain"],
                    fact.get("subdomain"),
                    orjson.dumps(fact.get("entities", [])).decode(),
                    fact["source_id"],
                    fact.get("confidence", 1.0),
                    fact.get("tags", []),
                ),
            )
            inserted += 1

        conn.commit()
        logger.info(f"Batch committed: {inserted} facts inserted so far")

    return inserted


def get_fact_count(domain: Optional[str] = None) -> int:
    """Get total fact count, optionally filtered by domain."""
    conn = get_pg()
    cur = conn.cursor()

    if domain:
        cur.execute("SELECT count(*) AS cnt FROM facts WHERE domain = %s", (domain,))
    else:
        cur.execute("SELECT count(*) AS cnt FROM facts")

    return cur.fetchone()["cnt"]
