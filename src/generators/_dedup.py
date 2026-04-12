"""
OenoBench — Embedding-based semantic deduplication for generated questions.

Uses OpenAI text-embedding-3-small via OpenRouter and pgvector cosine
distance for near-duplicate detection.
"""

import os

from loguru import logger

from src.utils.db import get_pg


def _get_openai_client():
    """Return an OpenAI client configured for OpenRouter."""
    from openai import OpenAI

    return OpenAI(
        api_key=os.getenv("OPENROUTER_API_KEY"),
        base_url="https://openrouter.ai/api/v1",
    )


def compute_embedding(text: str) -> list[float]:
    """Compute 1536-dim embedding via OpenRouter (text-embedding-3-small)."""
    client = _get_openai_client()
    resp = client.embeddings.create(
        model="openai/text-embedding-3-small",
        input=text,
    )
    return resp.data[0].embedding


def check_duplicate(
    question_text: str, threshold: float = 0.92
) -> tuple[bool, str | None]:
    """Check if question_text is semantically similar to existing questions.

    Uses pgvector cosine distance: similarity = 1 - (embedding <=> query).
    Returns (is_duplicate, matching_question_id_or_None).
    """
    embedding = compute_embedding(question_text)
    conn = get_pg()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT id, 1 - (embedding <=> %s::vector) AS similarity
        FROM questions
        WHERE embedding IS NOT NULL
        ORDER BY embedding <=> %s::vector
        LIMIT 1
        """,
        (embedding, embedding),
    )
    row = cur.fetchone()
    if row is None:
        return False, None

    sim = float(row["similarity"])
    if sim >= threshold:
        logger.info(
            f"Duplicate detected: similarity={sim:.4f} with question {row['id']}"
        )
        return True, str(row["id"])

    return False, None


def batch_embed_and_store(question_uuids: list[str]) -> int:
    """Compute and store embeddings for questions that lack them.

    Returns count of questions updated.
    """
    conn = get_pg()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT id, question_text FROM questions
        WHERE id = ANY(%s::uuid[])
          AND embedding IS NULL
        """,
        (question_uuids,),
    )
    rows = cur.fetchall()
    if not rows:
        return 0

    updated = 0
    for row in rows:
        try:
            emb = compute_embedding(row["question_text"])
            cur.execute(
                "UPDATE questions SET embedding = %s::vector WHERE id = %s",
                (emb, row["id"]),
            )
            updated += 1
        except Exception as e:
            logger.warning(f"Embedding failed for question {row['id']}: {e}")

    conn.commit()
    logger.info(f"Stored embeddings for {updated}/{len(rows)} questions")
    return updated


def run_dedup_pass(threshold: float = 0.92) -> list[tuple[str, str, float]]:
    """Full scan: find all question pairs above similarity threshold.

    Returns list of (q1_id, q2_id, similarity) sorted by similarity desc.
    """
    conn = get_pg()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT a.id AS id_a, b.id AS id_b,
               1 - (a.embedding <=> b.embedding) AS similarity
        FROM questions a, questions b
        WHERE a.id < b.id
          AND a.embedding IS NOT NULL
          AND b.embedding IS NOT NULL
          AND 1 - (a.embedding <=> b.embedding) >= %s
        ORDER BY similarity DESC
        """,
        (threshold,),
    )
    results = [
        (str(row["id_a"]), str(row["id_b"]), float(row["similarity"]))
        for row in cur.fetchall()
    ]
    logger.info(f"Dedup pass found {len(results)} pairs above threshold={threshold}")
    return results
