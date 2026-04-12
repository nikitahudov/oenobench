"""
OenoBench — Question insertion utilities with full provenance linkage.

Handles atomic insertion of questions + generation metadata + fact/source
linkage in a single transaction, plus query helpers for quota tracking.
"""

import uuid

import orjson
from loguru import logger

from src.utils.db import get_pg


def insert_question(
    question_data: dict,
    generation_meta: dict,
    fact_ids: list[str],
    source_ids: list[str],
) -> str | None:
    """Atomically insert question + generation_metadata + question_facts + question_sources.

    Args:
        question_data: Keys — question_id, domain, subdomain, question_type, difficulty,
            cognitive_dim, question_text, options (list[dict]), correct_answer,
            correct_answer_text, explanation, tags.
        generation_meta: Keys — generator, generator_version, generation_method,
            template_id, llm_creativity, prompt_hash, raw_response.
        fact_ids: UUIDs of facts this question was generated from.
        source_ids: UUIDs of authoritative sources backing this question.

    Returns:
        Question UUID string, or None on failure.
    """
    conn = get_pg()
    cur = conn.cursor()
    q_uuid = str(uuid.uuid4())

    try:
        conn.autocommit = False

        # 1. Insert question
        options_json = (
            orjson.dumps(question_data["options"]).decode()
            if question_data.get("options")
            else None
        )
        cur.execute(
            """
            INSERT INTO questions
                (id, question_id, version, domain, subdomain, question_type,
                 difficulty, cognitive_dim, question_text, options,
                 correct_answer, correct_answer_text, explanation, status, tags)
            VALUES (%s, %s, '1.0', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'draft', %s)
            """,
            (
                q_uuid,
                question_data["question_id"],
                question_data["domain"],
                question_data.get("subdomain"),
                question_data["question_type"],
                question_data["difficulty"],
                question_data.get("cognitive_dim", "recall"),
                question_data["question_text"],
                options_json,
                question_data["correct_answer"],
                question_data.get("correct_answer_text"),
                question_data.get("explanation"),
                question_data.get("tags", []),
            ),
        )

        # 2. Insert generation metadata
        raw_resp = (
            orjson.dumps(generation_meta["raw_response"]).decode()
            if generation_meta.get("raw_response")
            else None
        )
        cur.execute(
            """
            INSERT INTO generation_metadata
                (id, question_id, generator, generator_version, generation_method,
                 template_id, llm_creativity, prompt_hash, raw_response)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                str(uuid.uuid4()),
                q_uuid,
                generation_meta["generator"],
                generation_meta.get("generator_version"),
                generation_meta["generation_method"],
                generation_meta.get("template_id"),
                generation_meta.get("llm_creativity", "medium"),
                generation_meta.get("prompt_hash"),
                raw_resp,
            ),
        )

        # 3. Link facts
        for fid in fact_ids:
            cur.execute(
                "INSERT INTO question_facts (question_id, fact_id) VALUES (%s, %s)",
                (q_uuid, fid),
            )

        # 4. Link sources
        for sid in source_ids:
            cur.execute(
                "INSERT INTO question_sources (question_id, source_id) VALUES (%s, %s)",
                (q_uuid, sid),
            )

        conn.commit()
        logger.debug(f"Inserted question {question_data['question_id']} ({q_uuid})")
        return q_uuid

    except Exception as e:
        conn.rollback()
        logger.error(f"Failed to insert question: {e}")
        return None
    finally:
        conn.autocommit = True


def get_question_count(
    domain: str | None = None,
    generator: str | None = None,
    method: str | None = None,
    status: str = "draft",
) -> int:
    """Count questions matching filters."""
    conn = get_pg()
    cur = conn.cursor()

    clauses = []
    params: list = []

    if status:
        clauses.append("q.status = %s")
        params.append(status)
    if domain:
        clauses.append("q.domain = %s")
        params.append(domain)
    if generator or method:
        # Need join to generation_metadata
        base = "SELECT count(*) AS cnt FROM questions q JOIN generation_metadata gm ON gm.question_id = q.id"
        if generator:
            clauses.append("gm.generator = %s")
            params.append(generator)
        if method:
            clauses.append("gm.generation_method = %s")
            params.append(method)
    else:
        base = "SELECT count(*) AS cnt FROM questions q"

    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    cur.execute(base + where, params)
    return cur.fetchone()["cnt"]


def get_used_fact_ids() -> set[str]:
    """Return all fact_ids linked to existing questions via question_facts table."""
    conn = get_pg()
    cur = conn.cursor()
    cur.execute("SELECT fact_id FROM question_facts")
    return {str(row["fact_id"]) for row in cur.fetchall()}


def get_domain_generator_counts() -> dict:
    """Return {(domain, generator, method): count} for quota tracking."""
    conn = get_pg()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT q.domain, gm.generator, gm.generation_method, count(*) AS cnt
        FROM questions q
        JOIN generation_metadata gm ON gm.question_id = q.id
        GROUP BY q.domain, gm.generator, gm.generation_method
        """
    )
    return {
        (row["domain"], row["generator"], row["generation_method"]): row["cnt"]
        for row in cur.fetchall()
    }


def delete_questions_by_ids(question_ids: list[str]) -> int:
    """Delete questions by UUID. Cascades to generation_metadata, question_facts, question_sources."""
    if not question_ids:
        return 0
    conn = get_pg()
    cur = conn.cursor()
    deleted = 0
    for i in range(0, len(question_ids), 100):
        batch = question_ids[i : i + 100]
        cur.execute(
            "DELETE FROM questions WHERE id = ANY(%s::uuid[])",
            (batch,),
        )
        deleted += cur.rowcount
    conn.commit()
    logger.info(f"Deleted {deleted} questions")
    return deleted
