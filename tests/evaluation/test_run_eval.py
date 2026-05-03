"""Tests for Phase 5 eval harness (Team C).

Non-integration tests run by default:
  pytest tests/evaluation/test_run_eval.py -v -m "not integration"

Integration tests (require live DB + populated sample schema) run with:
  OENOBENCH_EVAL_TESTS_DB=1 pytest tests/evaluation/test_run_eval.py -v
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import uuid
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# ─── Helpers ─────────────────────────────────────────────────────────────────

_DB_ENABLED = os.environ.get("OENOBENCH_EVAL_TESTS_DB") == "1"

_DB_SKIP = pytest.mark.skipif(
    not _DB_ENABLED,
    reason="Set OENOBENCH_EVAL_TESTS_DB=1 to run DB-integration tests",
)


def _db_available() -> bool:
    """Quick liveness check against the running wb-postgres container."""
    try:
        from src.utils.db import get_pg
        conn = get_pg()
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
        return True
    except Exception:
        return False


# ─── Test 1: corpus loader — live sample.questions ───────────────────────────


@pytest.mark.integration
@_DB_SKIP
def test_corpus_loader_sample() -> None:
    """load_questions('sample', limit=5) returns 5 well-formed EvalQuestions."""
    if not _db_available():
        pytest.skip("DB not reachable")

    from src.evaluation._corpus_loader import load_questions

    questions = load_questions("sample", limit=5)
    assert len(questions) == 5, f"Expected 5 questions, got {len(questions)}"

    for q in questions:
        assert q.id, "id must be non-empty"
        assert q.question_text, "question_text must be non-empty"
        assert len(q.options) == 4, f"Expected 4 options, got {len(q.options)}: {q.options}"
        for letter in ("A", "B", "C", "D"):
            assert letter in q.options, f"Missing option {letter}"
            assert q.options[letter], f"Option {letter} text is empty"
        assert q.correct_answer in ("A", "B", "C", "D"), (
            f"correct_answer {q.correct_answer!r} is not a valid letter"
        )
        assert q.domain, "domain must be non-empty"


# ─── Test 2: corpus loader — invalid corpus name raises ValueError ────────────


def test_corpus_loader_invalid_corpus() -> None:
    """load_questions('foo') raises ValueError immediately (no DB needed)."""
    from src.evaluation._corpus_loader import load_questions

    with pytest.raises(ValueError, match="corpus must be"):
        load_questions("foo")


# ─── Test 2b: corpus loader — release_v1.2 default pins to 3,329 ──────────────


@pytest.mark.integration
@_DB_SKIP
def test_corpus_loader_public_default_is_release_v1_2() -> None:
    """When corpus='public' and release is unset, the loader returns the
    3,329-question release_v1.2 set (NOT the full 5,740 row table).  This is
    the official NeurIPS submission corpus."""
    if not _db_available():
        pytest.skip("DB not reachable")

    from src.evaluation._corpus_loader import (
        DEFAULT_PUBLIC_RELEASE,
        load_questions,
    )

    assert DEFAULT_PUBLIC_RELEASE == "v1.2", (
        f"Default release must be v1.2 to match the NeurIPS submission; "
        f"got {DEFAULT_PUBLIC_RELEASE!r}"
    )

    questions = load_questions("public")
    # release_v1.2 is fixed at 3,329 questions per docs/PROCESS_LOG.md
    # 2026-05-03 entry.  If this asserts changes, the release-tagging policy
    # has shifted and the eval pipeline + paper numbers must be reviewed.
    assert len(questions) == 3329, (
        f"release_v1.2 should yield 3,329 questions, got {len(questions)}.  "
        f"Either the release filter regressed or the DB tagging changed."
    )


@pytest.mark.integration
@_DB_SKIP
def test_corpus_loader_public_release_all_loads_more() -> None:
    """release='all' opt-out loads the full public table (minus stubs)."""
    if not _db_available():
        pytest.skip("DB not reachable")

    from src.evaluation._corpus_loader import load_questions

    questions = load_questions("public", release="all")
    # Full public minus 153 stubs = 5,740.  Larger than release_v1.2.
    assert len(questions) > 3329, (
        f"release='all' should load more than release_v1.2; got {len(questions)}"
    )


# ─── Test 3: dry-run exits 0 without DB writes ───────────────────────────────


def test_dry_run() -> None:
    """--dry-run mode prints plan and exits 0 without any DB writes."""
    result = subprocess.run(
        [
            sys.executable,
            "-m", "src.evaluation.run_eval",
            "--tag", "test_dry",
            "--corpus", "sample",
            "--max-questions", "5",
            "--dry-run",
        ],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=str(_repo_root()),
    )
    assert result.returncode == 0, (
        f"dry-run exited {result.returncode}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    combined = result.stdout + result.stderr
    assert "DRY RUN" in combined, "Expected DRY RUN marker in output"
    assert "no DB writes" in combined or "no API calls" in combined, (
        "Expected 'no DB writes' or 'no API calls' in dry-run output"
    )


def _repo_root():
    """Return the repo root as a Path."""
    from pathlib import Path
    return Path(__file__).parent.parent.parent


# ─── Test 4: resume skips existing answers ────────────────────────────────────


@pytest.mark.integration
@_DB_SKIP
def test_resume_skips_existing() -> None:
    """Inserting a fake answer row then resuming does not duplicate it."""
    if not _db_available():
        pytest.skip("DB not reachable")

    from src.evaluation._corpus_loader import load_questions
    from src.evaluation.run_eval import (
        _create_run,
        _fetch_completed_question_ids,
        _insert_answer,
    )
    from src.utils.db import get_pg

    # Load one question for the test.
    questions = load_questions("sample", limit=1)
    assert questions, "Need at least one sample question"
    q = questions[0]

    model_name = "test/model-resume"
    tag = f"test_resume_{uuid.uuid4().hex[:8]}"

    # Create a fresh run.
    run_id = _create_run(tag=tag, corpus="sample", configs=[], dry_run=False)

    # Insert a fake answer.
    _insert_answer(
        run_id=run_id,
        question_id=q.id,
        model_name=model_name,
        parsed_answer="A",
        is_correct=True,
        provider_used="test",
        generation_id=None,
        input_tokens=10,
        output_tokens=5,
        reasoning_tokens=0,
        cost_usd=0.0001,
        latency_ms=100,
        raw_response="A",
        reasoning_config=None,
        dry_run=False,
    )

    # Resume: fetch completed IDs and assert question is listed.
    completed = _fetch_completed_question_ids(run_id, model_name, None)
    assert q.id in completed, f"Expected {q.id} in completed IDs, got {completed}"

    # Attempt duplicate insert — ON CONFLICT DO NOTHING means count stays 1.
    _insert_answer(
        run_id=run_id,
        question_id=q.id,
        model_name=model_name,
        parsed_answer="B",
        is_correct=False,
        provider_used="test",
        generation_id=None,
        input_tokens=10,
        output_tokens=5,
        reasoning_tokens=0,
        cost_usd=0.0001,
        latency_ms=100,
        raw_response="B",
        reasoning_config=None,
        dry_run=False,
    )

    conn = get_pg()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) AS n, MAX(parsed_answer) AS ans "
            "FROM evaluation_answers WHERE run_id=%s AND model_name=%s",
            (run_id, model_name),
        )
        row = cur.fetchone()
    assert row["n"] == 1, f"Expected 1 row, got {row['n']} (duplicate not suppressed)"
    assert row["ans"] == "A", f"Expected first answer 'A' preserved, got {row['ans']!r}"

    # Cleanup.
    with conn.cursor() as cur:
        cur.execute("DELETE FROM evaluation_runs WHERE id=%s", (run_id,))
    conn.commit()


# ─── Test 5: max-skipped guardrail aborts config ──────────────────────────────


@pytest.mark.integration
@_DB_SKIP
def test_max_skipped_guardrail() -> None:
    """When evaluate_one always returns parsed_answer=None for one config,
    that config is aborted while the other continues.

    Uses --configs 1,2 with --max-questions 250 so we cross the 200-Q
    guardrail window.  Config slot 1 is monkeypatched to always skip;
    slot 2 succeeds (returns 'A').

    This test runs against the live DB because it needs real question rows
    and the harness DB write path; isolation is provided by a unique tag.
    """
    if not _db_available():
        pytest.skip("DB not reachable")

    from src.evaluation._corpus_loader import load_questions
    from src.evaluation.run_eval import _create_run, _evaluate_config

    # Need Team B's configs; if not available, skip.
    try:
        from src.evaluation.configs import EVAL_CONFIGS, by_slot
    except ImportError:
        pytest.skip("Team B configs not yet on main")

    questions = load_questions("sample", limit=250)
    if len(questions) < 210:
        pytest.skip("Need >=210 questions to trigger guardrail")

    tag = f"test_guardrail_{uuid.uuid4().hex[:8]}"
    config_1 = by_slot(1)
    config_2 = by_slot(2)

    run_id = _create_run(
        tag=tag, corpus="sample",
        configs=[config_1, config_2],
        dry_run=False,
    )

    # Stub: config 1 → always None (skip); config 2 → always "A".
    call_counts: dict[int, int] = {1: 0, 2: 0}
    call_lock = threading.Lock()

    def _stub_evaluate_one(client, config, question_text, options, **kwargs):
        with call_lock:
            call_counts[config.slot] = call_counts.get(config.slot, 0) + 1
        response = SimpleNamespace(
            input_tokens=10,
            output_tokens=1,
            reasoning_tokens=0,
            latency_ms=5,
            provider="stub",
            generation_id=None,
        )
        if config.slot == 1:
            return SimpleNamespace(
                parsed_answer=None,
                raw_text="",
                response=response,
                config=config,
            )
        return SimpleNamespace(
            parsed_answer="A",
            raw_text="A",
            response=response,
            config=config,
        )

    def _stub_compute_cost(*args, **kwargs) -> float:
        return 0.0

    # Run config 1 (should abort after guardrail).
    stats_1 = _evaluate_config(
        config=config_1,
        questions=questions,
        run_id=run_id,
        dry_run=False,
        evaluate_one_fn=_stub_evaluate_one,
        compute_cost_fn=_stub_compute_cost,
    )

    # Run config 2 (should complete normally).
    stats_2 = _evaluate_config(
        config=config_2,
        questions=questions,
        run_id=run_id,
        dry_run=False,
        evaluate_one_fn=_stub_evaluate_one,
        compute_cost_fn=_stub_compute_cost,
    )

    assert stats_1["aborted"], (
        f"Config 1 should have been aborted by guardrail, stats={stats_1}"
    )
    assert not stats_2["aborted"], (
        f"Config 2 should NOT be aborted, stats={stats_2}"
    )
    assert stats_2["total"] == len(questions), (
        f"Config 2 should process all {len(questions)} questions, got {stats_2['total']}"
    )

    # Cleanup.
    from src.utils.db import get_pg
    conn = get_pg()
    with conn.cursor() as cur:
        cur.execute("DELETE FROM evaluation_runs WHERE id=%s", (run_id,))
    conn.commit()
