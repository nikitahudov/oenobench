"""Data-access layer for `audit_runs`, `audit_findings`, `audit_gold_labels`.

All write paths are idempotent on `(run_id, question_id, agent_id, agent_version)`,
so re-running an interrupted audit is a no-op for already-stored findings.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

import orjson
from loguru import logger

from src.utils.db import get_pg

# Canonical severity strings — must match the Postgres enum.
SEVERITY_PASS = "pass"
SEVERITY_WARN = "warn"
SEVERITY_FAIL = "fail"
SEVERITY_ERROR = "error"
ALL_SEVERITIES = {SEVERITY_PASS, SEVERITY_WARN, SEVERITY_FAIL, SEVERITY_ERROR}


def compute_config_hash(
    *,
    agent_versions: dict[str, str],
    model_ids: list[str],
    seed: int,
    thresholds: dict[str, Any],
) -> str:
    """Stable hash for an audit run's configuration. Used for cache lookups."""
    payload = {
        "agents": dict(sorted(agent_versions.items())),
        "models": sorted(model_ids),
        "seed": seed,
        "thresholds": thresholds,
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(blob).hexdigest()


def create_run(
    *,
    corpus_tag: str,
    corpus_size: int,
    config_hash: str,
    seed: int,
    metadata: dict[str, Any] | None = None,
) -> str:
    """Insert a new `audit_runs` row and return the UUID."""
    conn = get_pg()
    cur = conn.cursor()
    run_id = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO audit_runs (id, corpus_tag, corpus_size, config_hash, random_seed, metadata)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (
            run_id,
            corpus_tag,
            corpus_size,
            config_hash,
            seed,
            orjson.dumps(metadata or {}).decode(),
        ),
    )
    conn.commit()
    logger.info("Created audit run {} for tag {}", run_id, corpus_tag)
    return run_id


def complete_run(run_id: str) -> None:
    """Mark a run completed and update the cost ledger from its findings."""
    conn = get_pg()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE audit_runs
           SET completed_at = now(),
               total_cost_usd = COALESCE((
                   SELECT sum(cost_usd) FROM audit_findings WHERE run_id = %s
               ), 0)
         WHERE id = %s
        """,
        (run_id, run_id),
    )
    conn.commit()


def find_existing(
    run_id: str,
    question_id: str | None,
    agent_id: str,
    agent_version: str,
) -> dict | None:
    """Lookup the idempotency row, if any."""
    conn = get_pg()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, severity, score, payload, llm_calls, cost_usd
          FROM audit_findings
         WHERE run_id = %s
           AND COALESCE(question_id::text, '') = %s
           AND agent_id = %s
           AND agent_version = %s
        """,
        (run_id, question_id or "", agent_id, agent_version),
    )
    return cur.fetchone()


def write_finding(
    *,
    run_id: str,
    question_id: str | None,
    agent_id: str,
    agent_version: str,
    severity: str,
    score: float | None = None,
    payload: dict | None = None,
    llm_calls: int = 0,
    cost_usd: float = 0.0,
) -> str | None:
    """Insert (or skip if exists) one finding row.

    Returns the row UUID, or None if the row already existed.
    """
    if severity not in ALL_SEVERITIES:
        raise ValueError(f"unknown severity: {severity}")

    existing = find_existing(run_id, question_id, agent_id, agent_version)
    if existing:
        return None

    conn = get_pg()
    cur = conn.cursor()
    fid = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO audit_findings
            (id, run_id, question_id, agent_id, agent_version,
             severity, score, payload, llm_calls, cost_usd)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            fid,
            run_id,
            question_id,
            agent_id,
            agent_version,
            severity,
            score,
            orjson.dumps(payload or {}).decode(),
            llm_calls,
            cost_usd,
        ),
    )
    conn.commit()
    return fid


def write_findings_bulk(rows: list[dict]) -> int:
    """Bulk-insert pre-checked finding rows (skips conflicts via upsert)."""
    if not rows:
        return 0
    conn = get_pg()
    cur = conn.cursor()
    inserted = 0
    for r in rows:
        try:
            res = write_finding(**r)
            if res:
                inserted += 1
        except Exception as exc:  # pragma: no cover — defensive
            logger.error("write_finding failed for {}: {}", r.get("agent_id"), exc)
    return inserted


def get_run(run_id: str) -> dict | None:
    conn = get_pg()
    cur = conn.cursor()
    cur.execute("SELECT * FROM audit_runs WHERE id = %s", (run_id,))
    return cur.fetchone()


def latest_run_for_tag(corpus_tag: str) -> dict | None:
    conn = get_pg()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM audit_runs WHERE corpus_tag = %s ORDER BY started_at DESC LIMIT 1",
        (corpus_tag,),
    )
    return cur.fetchone()


def fetch_findings(
    run_id: str,
    *,
    agent_id: str | None = None,
    severity: str | None = None,
) -> list[dict]:
    conn = get_pg()
    cur = conn.cursor()
    clauses = ["run_id = %s"]
    params: list[Any] = [run_id]
    if agent_id:
        clauses.append("agent_id = %s")
        params.append(agent_id)
    if severity:
        clauses.append("severity = %s")
        params.append(severity)
    cur.execute(
        f"SELECT * FROM audit_findings WHERE {' AND '.join(clauses)}",
        params,
    )
    return cur.fetchall()


def fetch_corpus_questions(corpus_tag: str) -> list[dict]:
    """Return every question rowed against the corpus tag with full context.

    Joins generation_metadata, question_facts → facts, question_sources → sources.
    Used by every agent as its input set.
    """
    conn = get_pg()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
            q.id                          AS uuid,
            q.question_id                 AS public_qid,
            q.domain::text                AS domain,
            q.subdomain                   AS subdomain,
            q.question_type::text         AS question_type,
            q.difficulty::text            AS difficulty,
            q.cognitive_dim::text         AS cognitive_dim,
            q.question_text               AS question_text,
            q.options                     AS options,
            q.correct_answer              AS correct_answer,
            q.correct_answer_text         AS correct_answer_text,
            q.explanation                 AS explanation,
            q.tags                        AS tags,
            gm.generator::text            AS generator,
            gm.generation_method          AS generation_method,
            gm.template_id                AS template_id,
            COALESCE((
                SELECT json_agg(json_build_object(
                    'fact_id', f.id,
                    'fact_text', f.fact_text,
                    'domain', f.domain,
                    'subdomain', f.subdomain,
                    'entities', f.entities,
                    'source_name', s.name,
                    'source_url', s.url
                ))
                FROM question_facts qf
                JOIN facts f ON f.id = qf.fact_id
                JOIN sources s ON s.id = f.source_id
                WHERE qf.question_id = q.id
            ), '[]'::json) AS facts
        FROM questions q
        JOIN generation_metadata gm ON gm.question_id = q.id
        WHERE %s = ANY(q.tags)
        ORDER BY q.created_at
        """,
        (corpus_tag,),
    )
    return cur.fetchall()


def upsert_gold_label(question_id: str, labels: dict, reviewer: str, notes: str = "") -> None:
    conn = get_pg()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO audit_gold_labels (question_id, labels, reviewer, notes)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (question_id) DO UPDATE
           SET labels = EXCLUDED.labels,
               reviewer = EXCLUDED.reviewer,
               reviewed_at = now(),
               notes = EXCLUDED.notes
        """,
        (question_id, orjson.dumps(labels).decode(), reviewer, notes),
    )
    conn.commit()


def fetch_gold_labels() -> dict[str, dict]:
    conn = get_pg()
    cur = conn.cursor()
    cur.execute("SELECT question_id, labels, reviewer FROM audit_gold_labels")
    return {str(row["question_id"]): row for row in cur.fetchall()}
