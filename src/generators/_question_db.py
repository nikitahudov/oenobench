"""
OenoBench — Question insertion utilities with full provenance linkage.

Handles atomic insertion of questions + generation metadata + fact/source
linkage in a single transaction, plus query helpers for quota tracking.
"""

import math
import os
import uuid

import orjson
from loguru import logger

from src.generators._closed_book_gate import (
    CLOSED_BOOK_QUOTA_FRACTION,
    CLOSED_BOOK_TAG,
    GateResult,
    screen_question,
)
from src.utils.db import get_pg

# 25% of the 10k overall target. Imported lazily to avoid circular import on
# orchestrator at module load. See `_closed_book_quota_cap()` below.
_OVERALL_TARGET_DEFAULT = 10_000

# Per-corpus override for the quota cap. Set by `set_corpus_target()` so the
# audit-pilot orchestrator can scope the 25% cap to a small corpus (e.g. 295
# questions → cap 74) rather than the global 10k → 2500. None means "use the
# orchestrator default".
_CORPUS_TARGET_OVERRIDE: int | None = None

# Env-var fallback for the quota target. `set_corpus_target()` only mutates
# the module-global above, which does not survive the `subprocess.run` boundary
# between `_corpus._run_generator()` and each strategy CLI. The orchestrator
# also exports this env var so child processes resolve the same scoped cap.
# Audit #7 shipped without this and ran with the default 10k cap → 172 closed-
# book relabels on a 242-Q corpus instead of the intended 150 ceiling.
CORPUS_TARGET_ENV_VAR = "OENOBENCH_CORPUS_TARGET"

# Env-var fallback for scoping the closed-book count to the current build.
# `count_closed_book_solvable()` queries the entire `questions` table; without
# scoping, every prior audit pilot's `closed_book_solvable`-tagged questions
# count toward the new build's cap. v8's first attempt hit `427/50` immediately
# because v5+v6+v7 had already accumulated 427 cb-tagged questions in the DB.
# The orchestrator exports this env var as an ISO-8601 timestamp before
# dispatching strategies; child subprocesses resolve it and pass it to the
# count query as a `created_at >= since` filter.
CORPUS_BUILD_SINCE_ENV_VAR = "OENOBENCH_CORPUS_BUILD_SINCE"

# Phase 2g.10 (2026-04-28): per-strategy closed-book budget. When set, the
# gate evaluates the 25% cap against the per-strategy target rather than the
# corpus target, with the cb count filtered by `generation_metadata.generation_method`.
# Prevents the first strategy in the build order from monopolising the cap and
# starving later strategies of cb-relabel slots. Audit #6/#7 ran with a single
# corpus-level cap; v8's prior cb-rates show 40-77% per strategy, so without
# per-strategy fairness the late strategies (scenario, distractor) end up with
# all their gate-flagged questions dropped instead of relabeled.
STRATEGY_TARGET_ENV_VAR = "OENOBENCH_STRATEGY_TARGET"


def set_corpus_target(size: int | None) -> None:
    """Override the corpus size used to compute the closed-book quota cap.

    Pass `None` to clear the override and revert to the orchestrator's
    `OVERALL_TARGET` (the 10k full-generation default).

    Audit-pilot builders set this so the 25% cap is evaluated against the
    pilot size (e.g. 295) instead of the global 10k. Without this, a 295-Q
    pilot's cap is 2500 — i.e. effectively no cap — which broke the
    documented "25% of corpus" semantics in v2.0.
    """
    global _CORPUS_TARGET_OVERRIDE
    if size is None:
        _CORPUS_TARGET_OVERRIDE = None
        return
    if int(size) <= 0:
        raise ValueError(f"corpus target must be positive, got {size}")
    _CORPUS_TARGET_OVERRIDE = int(size)


def _resolve_default_target_size() -> int:
    """Resolve the effective `target_size` when a caller does not pass one.

    Priority:
      1. `_CORPUS_TARGET_OVERRIDE` set via `set_corpus_target()` (audit pilots,
         in-process callers).
      2. `OENOBENCH_CORPUS_TARGET` env var (audit pilots, subprocess workers
         spawned by `_corpus._run_generator`). Subprocesses don't inherit
         the in-process module-global, so the orchestrator exports the env
         var alongside `set_corpus_target()` and child processes pick it up
         via this branch.
      3. `OVERALL_TARGET` imported from the orchestrator (full 10k run).
      4. `_OVERALL_TARGET_DEFAULT = 10_000` (final fallback).
    """
    if _CORPUS_TARGET_OVERRIDE is not None:
        return _CORPUS_TARGET_OVERRIDE
    env_target = os.environ.get(CORPUS_TARGET_ENV_VAR)
    if env_target:
        try:
            parsed = int(env_target)
            if parsed > 0:
                return parsed
        except ValueError:
            logger.warning(
                "{} is set but not a positive int (got {!r}); falling back",
                CORPUS_TARGET_ENV_VAR, env_target,
            )
    try:
        from src.generators.orchestrator import OVERALL_TARGET
        return int(OVERALL_TARGET)
    except Exception:  # noqa: BLE001
        return _OVERALL_TARGET_DEFAULT


def _closed_book_quota_cap(target_size: int | None = None) -> int:
    """Absolute cap on closed-book-solvable questions in the current corpus.

    cap = ceil(target_size × CLOSED_BOOK_QUOTA_FRACTION)

    target_size is the planned corpus size (per-strategy, per-corpus, or
    OVERALL_TARGET). For the 10k full-generation run, defaults to OVERALL_TARGET.
    For audit pilots, the orchestrator should pass the pilot size.
    """
    if target_size is None:
        target_size = _resolve_default_target_size()
    return math.ceil(int(target_size) * CLOSED_BOOK_QUOTA_FRACTION)


def _resolve_strategy_target_size() -> int | None:
    """Read OENOBENCH_STRATEGY_TARGET. Returns None when unset/invalid.

    None means "no per-strategy budget" — the gate falls back to the
    corpus-level cap. A positive int activates the per-strategy mode:
    each strategy gets `ceil(target × CLOSED_BOOK_QUOTA_FRACTION)` cb slots,
    counted via JOIN to `generation_metadata.generation_method`.
    """
    raw = os.environ.get(STRATEGY_TARGET_ENV_VAR)
    if not raw:
        return None
    try:
        n = int(raw)
        return n if n > 0 else None
    except ValueError:
        logger.warning(
            "{} is set but not a positive int (got {!r}); ignoring",
            STRATEGY_TARGET_ENV_VAR, raw,
        )
        return None


def _resolve_default_build_since() -> str | None:
    """Return the build-start ISO-8601 timestamp, or None for unscoped count.

    Used by `count_closed_book_solvable()` so the quota cap is evaluated
    against questions created during the current build only — not against
    every historical pilot's `closed_book_solvable`-tagged questions still
    sitting in the DB. A blank or malformed env var falls through to None
    (unscoped, backwards-compatible behaviour).
    """
    raw = os.environ.get(CORPUS_BUILD_SINCE_ENV_VAR)
    if not raw:
        return None
    return raw.strip() or None


def count_closed_book_solvable(
    since: str | None = None,
    strategy: str | None = None,
) -> int:
    """Count questions currently tagged `closed_book_solvable`.

    Used by `insert_question_gated` to enforce the 25% cap, either at the
    corpus level (default) or per generation_method (when `strategy` is
    provided). Cheap enough to call per-insert thanks to the GIN index on
    `questions.tags` plus the b-tree on `generation_metadata.question_id`.

    Args:
        since: Optional ISO-8601 timestamp string. When provided, only
            questions with `created_at >= since` are counted. When None,
            the env var `OENOBENCH_CORPUS_BUILD_SINCE` is consulted; if
            unset/blank, the count is unscoped (legacy behaviour).
        strategy: Optional `generation_metadata.generation_method` filter.
            When provided, the count joins `generation_metadata` and only
            counts cb-tagged questions produced by that strategy. Used by
            the per-strategy budget mode (Phase 2g.10).
    """
    if since is None:
        since = _resolve_default_build_since()
    conn = get_pg()
    cur = conn.cursor()
    if strategy is not None:
        # Per-strategy count: JOIN generation_metadata so we can filter by
        # generation_method. The two filters compose with AND: cb-tag,
        # strategy, and (optional) created_at scope.
        if since:
            cur.execute(
                "SELECT count(*) AS cnt FROM questions q "
                "JOIN generation_metadata gm ON gm.question_id = q.id "
                "WHERE %s = ANY(q.tags) AND gm.generation_method = %s "
                "AND q.created_at >= %s::timestamptz",
                (CLOSED_BOOK_TAG, strategy, since),
            )
        else:
            cur.execute(
                "SELECT count(*) AS cnt FROM questions q "
                "JOIN generation_metadata gm ON gm.question_id = q.id "
                "WHERE %s = ANY(q.tags) AND gm.generation_method = %s",
                (CLOSED_BOOK_TAG, strategy),
            )
    elif since:
        cur.execute(
            "SELECT count(*) AS cnt FROM questions "
            "WHERE %s = ANY(tags) AND created_at >= %s::timestamptz",
            (CLOSED_BOOK_TAG, since),
        )
    else:
        cur.execute(
            "SELECT count(*) AS cnt FROM questions WHERE %s = ANY(tags)",
            (CLOSED_BOOK_TAG,),
        )
    row = cur.fetchone()
    return int(row["cnt"]) if row else 0


def insert_question_gated(
    question_data: dict,
    generation_meta: dict,
    fact_ids: list[str],
    source_ids: list[str],
    apply_gate: bool = True,
    target_size: int | None = None,
    pre_screened: GateResult | None = None,
) -> tuple[str | None, GateResult]:
    """Run the closed-book gate, then route per Phase 2g.6 policy.

    The gate runs only on L1/L2 multiple-choice questions; L3+, non-MC
    types, and questions without options pass through unchanged. The gate's
    verdict is appended to `generation_meta['raw_response']['gate']` for
    downstream audit / split-evaluation.

    Routing (v2.0, 2026-04-24):
      * gate.passed=True  → INSERT as-is (the pre-screen could not solve it)
      * gate.passed=False AND quota has room
            → MUTATE question_data: append `closed_book_solvable` tag,
              force `difficulty='1'`. Set `gate.relabeled=True`. INSERT.
      * gate.passed=False AND quota full
            → set `gate.quota_full=True`. DROP. Return (None, gate).
      * gate.applied=False → INSERT as-is

    Args:
        pre_screened: Optional `GateResult` from a caller that already ran
            `screen_question(...)` on this question. When provided, the
            inner gate call is skipped (Phase 2g.8 cost optimization for
            template_generator, which gates BEFORE paraphrase + verifier
            so those Gemini calls can be skipped on flagged questions).
            Caller is responsible for passing a verdict computed against
            the same question payload.

    Returns:
        (q_uuid_or_none, gate_result). q_uuid is None when the question
        was dropped (quota full) or when the underlying DB insert failed.
    """
    if pre_screened is not None:
        gate = pre_screened
    elif apply_gate:
        gate = screen_question(
            stem=question_data["question_text"],
            options=question_data.get("options"),
            correct_answer=question_data["correct_answer"],
            difficulty=str(question_data["difficulty"]),
            question_type=question_data["question_type"],
        )
    else:
        gate = GateResult(passed=True, applied=False, reason="gate_disabled")

    if gate.applied and not gate.passed:
        # Phase 2g.10: prefer per-strategy budget when OENOBENCH_STRATEGY_TARGET
        # is set AND the caller's generation_meta carries a generation_method.
        # This stops the first strategy in build order from monopolising the
        # corpus-wide cap; each strategy gets its own ceil(per_strategy × 0.25)
        # slots, counted via JOIN to generation_metadata.generation_method.
        strategy_target = _resolve_strategy_target_size()
        strategy_name = generation_meta.get("generation_method")
        if strategy_target is not None and strategy_name:
            cap = math.ceil(int(strategy_target) * CLOSED_BOOK_QUOTA_FRACTION)
            current = count_closed_book_solvable(strategy=strategy_name)
            cap_label = f"strategy:{strategy_name}"
        else:
            cap = _closed_book_quota_cap(target_size)
            current = count_closed_book_solvable()
            cap_label = "corpus"
        if current >= cap:
            gate.quota_full = True
            gate.reason = (
                f"reject (quota_full): closed_book_solvable {current}/{cap} "
                f"({cap_label}); original={gate.reason}"
            )
            _stash_gate_meta(generation_meta, gate)
            logger.info(
                "GATE QUOTA FULL | qid={} | {}",
                question_data.get("question_id"), gate.reason,
            )
            return None, gate

        existing_tags = list(question_data.get("tags") or [])
        if CLOSED_BOOK_TAG not in existing_tags:
            existing_tags.append(CLOSED_BOOK_TAG)
        question_data["tags"] = existing_tags
        question_data["difficulty"] = "1"
        gate.relabeled = True
        gate.reason = (
            f"relabel: gate solved closed-book → tagged {CLOSED_BOOK_TAG}, "
            f"difficulty forced to L1; original={gate.reason}"
        )
        logger.info(
            "GATE RELABEL | qid={} | {}",
            question_data.get("question_id"), gate.reason,
        )

    _stash_gate_meta(generation_meta, gate)
    q_uuid = insert_question(question_data, generation_meta, fact_ids, source_ids)
    return q_uuid, gate


def _stash_gate_meta(generation_meta: dict, gate: GateResult) -> None:
    raw = generation_meta.setdefault("raw_response", {}) or {}
    if not isinstance(raw, dict):
        raw = {"content": raw}
    raw["gate"] = gate.to_dict()
    generation_meta["raw_response"] = raw


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
    # Defensive: clear any lingering transaction state from a prior failed
    # call before touching autocommit. Under heavy parallel load the
    # connection may be left mid-transaction when the previous caller
    # raised outside our try/except — and psycopg2 errors with
    # "set_session cannot be used inside a transaction" if we then try
    # to flip autocommit. Rollback is safe here (it's a no-op if there's
    # no open transaction).
    try:
        conn.rollback()
    except Exception:
        pass
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
