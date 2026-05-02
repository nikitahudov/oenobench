"""Tests for OR telemetry fields wired through the eval harness.

Non-integration tests run by default:
  pytest tests/evaluation/test_run_eval_telemetry.py -v -m "not integration"

Integration tests (require live DB) run with:
  OENOBENCH_EVAL_TESTS_DB=1 pytest tests/evaluation/test_run_eval_telemetry.py -v
"""
from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import pytest

# ─── Helpers ─────────────────────────────────────────────────────────────────

_DB_ENABLED = os.environ.get("OENOBENCH_EVAL_TESTS_DB") == "1"

_DB_SKIP = pytest.mark.skipif(
    not _DB_ENABLED,
    reason="Set OENOBENCH_EVAL_TESTS_DB=1 to run DB-integration tests",
)


def _db_available() -> bool:
    try:
        from src.utils.db import get_pg
        conn = get_pg()
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
        return True
    except Exception:
        return False


# ─── Minimal stub dataclasses matching Team Alpha's LLMResponse contract ─────


@dataclass
class _StubLLMResponse:
    """Minimal LLMResponse stub with the three new Team Alpha fields."""
    content: str = ""
    success: bool = True
    input_tokens: int = 10
    output_tokens: int = 2
    reasoning_tokens: int = 0
    latency_ms: int = 50
    error: str | None = None
    # Team Alpha fields:
    generation_id: str | None = None
    provider: str | None = None
    or_cost: float | None = None


@dataclass
class _StubEvalResult:
    """Minimal EvalResult stub."""
    parsed_answer: str | None
    raw_text: str
    response: _StubLLMResponse
    config: Any


@dataclass
class _StubEvalConfig:
    """Minimal EvalConfig stub — just enough for _persist_answer_row."""
    slot: int
    model_id: str
    name: str
    reasoning_mode: str | None = None
    reasoning_budget: int | None = None
    concurrency: int = 10


# ─── Test 1: or_cost and or_provider round-trip through DB ───────────────────


@pytest.mark.integration
@_DB_SKIP
def test_insert_writes_or_cost_and_or_provider() -> None:
    """_persist_answer_row stores or_cost_usd and or_provider correctly."""
    if not _db_available():
        pytest.skip("DB not reachable")

    from src.evaluation._corpus_loader import load_questions
    from src.evaluation.run_eval import _create_run, _persist_answer_row
    from src.utils.db import get_pg

    questions = load_questions("sample", limit=1)
    assert questions, "Need at least one sample question"
    q = questions[0]

    config = _StubEvalConfig(slot=99, model_id="test/or-telemetry-model", name="test-or-telemetry")
    response = _StubLLMResponse(
        generation_id="gen-abc123",
        provider="Anthropic",
        or_cost=0.001234,
    )
    result = _StubEvalResult(
        parsed_answer="A",
        raw_text="A",
        response=response,
        config=config,
    )

    tag = f"test_or_telemetry_{uuid.uuid4().hex[:8]}"
    run_id = _create_run(tag=tag, corpus="sample", configs=[], dry_run=False)

    conn = get_pg()
    try:
        parsed, is_correct, cost = _persist_answer_row(
            conn,
            run_id=run_id,
            question_id=q.id,
            config=config,
            result=result,
            compute_cost_fn=lambda *a, **kw: 0.0005,
            correct_answer=q.correct_answer,
        )

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT or_cost_usd, or_provider, generation_id, provider_used
                FROM evaluation_answers
                WHERE run_id = %s AND model_name = %s
                LIMIT 1
                """,
                (run_id, config.model_id),
            )
            row = cur.fetchone()

        assert row is not None, "Expected an inserted row"
        assert abs(row["or_cost_usd"] - 0.001234) < 1e-8, (
            f"or_cost_usd mismatch: expected 0.001234, got {row['or_cost_usd']}"
        )
        assert row["or_provider"] == "Anthropic", (
            f"or_provider mismatch: expected 'Anthropic', got {row['or_provider']!r}"
        )
        assert row["generation_id"] == "gen-abc123", (
            f"generation_id mismatch: expected 'gen-abc123', got {row['generation_id']!r}"
        )
        assert row["provider_used"] == "Anthropic", (
            f"provider_used mismatch: expected 'Anthropic', got {row['provider_used']!r}"
        )

    finally:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM evaluation_answers WHERE run_id = %s", (run_id,))
            cur.execute("DELETE FROM evaluation_runs WHERE id = %s", (run_id,))
        conn.commit()


# ─── Test 2: None telemetry results in NULLs in DB ───────────────────────────


@pytest.mark.integration
@_DB_SKIP
def test_insert_handles_none_telemetry() -> None:
    """_persist_answer_row stores NULLs when or_cost and provider are None."""
    if not _db_available():
        pytest.skip("DB not reachable")

    from src.evaluation._corpus_loader import load_questions
    from src.evaluation.run_eval import _create_run, _persist_answer_row
    from src.utils.db import get_pg

    questions = load_questions("sample", limit=1)
    assert questions, "Need at least one sample question"
    q = questions[0]

    config = _StubEvalConfig(slot=98, model_id="test/or-none-model", name="test-or-none")
    response = _StubLLMResponse(
        generation_id=None,
        provider=None,
        or_cost=None,
    )
    result = _StubEvalResult(
        parsed_answer="B",
        raw_text="B",
        response=response,
        config=config,
    )

    tag = f"test_or_none_{uuid.uuid4().hex[:8]}"
    run_id = _create_run(tag=tag, corpus="sample", configs=[], dry_run=False)

    conn = get_pg()
    try:
        _persist_answer_row(
            conn,
            run_id=run_id,
            question_id=q.id,
            config=config,
            result=result,
            compute_cost_fn=lambda *a, **kw: 0.0002,
            correct_answer=q.correct_answer,
        )

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT or_cost_usd, or_provider, generation_id, provider_used
                FROM evaluation_answers
                WHERE run_id = %s AND model_name = %s
                LIMIT 1
                """,
                (run_id, config.model_id),
            )
            row = cur.fetchone()

        assert row is not None, "Expected an inserted row"
        assert row["or_cost_usd"] is None, (
            f"or_cost_usd should be NULL, got {row['or_cost_usd']!r}"
        )
        assert row["or_provider"] is None, (
            f"or_provider should be NULL, got {row['or_provider']!r}"
        )
        assert row["generation_id"] is None, (
            f"generation_id should be NULL, got {row['generation_id']!r}"
        )
        # provider_used falls back to "unknown" when provider is None.
        assert row["provider_used"] == "unknown", (
            f"provider_used should be 'unknown', got {row['provider_used']!r}"
        )

    finally:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM evaluation_answers WHERE run_id = %s", (run_id,))
            cur.execute("DELETE FROM evaluation_runs WHERE id = %s", (run_id,))
        conn.commit()
