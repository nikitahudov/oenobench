"""
Integration test for migration 005_or_cost_telemetry.sql.

Gated by env var OENOBENCH_EVAL_TESTS_DB=1.
Run with:
    OENOBENCH_EVAL_TESTS_DB=1 pytest tests/migrations/test_005_or_cost_telemetry.py -v -m integration
"""

import os
import uuid

import pytest


@pytest.mark.integration
def test_005_or_cost_telemetry_columns():
    """Verify or_cost_usd / or_provider / total_or_cost_usd columns exist and round-trip."""
    if not os.getenv("OENOBENCH_EVAL_TESTS_DB"):
        pytest.skip("OENOBENCH_EVAL_TESTS_DB not set — skipping DB integration test")

    from src.utils.db import get_pg

    conn = get_pg()
    cur = conn.cursor()

    # ---- 1. Column presence check on evaluation_answers ----------------------
    cur.execute(
        """
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name   = 'evaluation_answers'
          AND column_name  IN ('or_cost_usd', 'or_provider')
        ORDER BY column_name
        """,
    )
    rows = {r["column_name"]: r["data_type"] for r in cur.fetchall()}

    assert "or_cost_usd" in rows, "or_cost_usd column missing from evaluation_answers"
    assert rows["or_cost_usd"] == "real", (
        f"or_cost_usd expected type 'real', got '{rows['or_cost_usd']}'"
    )

    assert "or_provider" in rows, "or_provider column missing from evaluation_answers"
    assert rows["or_provider"] == "text", (
        f"or_provider expected type 'text', got '{rows['or_provider']}'"
    )

    # ---- 2. Column presence check on evaluation_runs -------------------------
    cur.execute(
        """
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name   = 'evaluation_runs'
          AND column_name  = 'total_or_cost_usd'
        """,
    )
    run_rows = {r["column_name"]: r["data_type"] for r in cur.fetchall()}

    assert "total_or_cost_usd" in run_rows, (
        "total_or_cost_usd column missing from evaluation_runs"
    )
    assert run_rows["total_or_cost_usd"] == "real", (
        f"total_or_cost_usd expected type 'real', got '{run_rows['total_or_cost_usd']}'"
    )

    # ---- 3. Sample insert round-trip -----------------------------------------
    # Create a throw-away evaluation_run row first (required by FK).
    run_id = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO evaluation_runs (id, model_name, prompt_strategy)
        VALUES (%s, %s, %s)
        """,
        (run_id, "_test_005_bravo", "zero_shot"),
    )

    # We need a real question_id to satisfy the FK on evaluation_answers.
    # Pick any existing question; if none exist, skip the insert test.
    cur.execute("SELECT id FROM questions LIMIT 1")
    q_row = cur.fetchone()
    if q_row is None:
        conn.rollback()
        pytest.skip("No rows in questions table — skipping insert round-trip")

    question_id = str(q_row["id"])
    answer_id = str(uuid.uuid4())
    test_or_cost = 0.00314
    test_or_provider = "Anthropic"

    cur.execute(
        """
        INSERT INTO evaluation_answers
            (id, run_id, question_id, model_name, or_cost_usd, or_provider)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (answer_id, run_id, question_id, "_test_005_bravo",
         test_or_cost, test_or_provider),
    )

    cur.execute(
        "SELECT or_cost_usd, or_provider FROM evaluation_answers WHERE id = %s",
        (answer_id,),
    )
    fetched = cur.fetchone()
    assert fetched is not None, "Inserted row not found"
    assert abs(fetched["or_cost_usd"] - test_or_cost) < 1e-6, (
        f"or_cost_usd round-trip failed: expected {test_or_cost}, got {fetched['or_cost_usd']}"
    )
    assert fetched["or_provider"] == test_or_provider, (
        f"or_provider round-trip failed: expected '{test_or_provider}', got '{fetched['or_provider']}'"
    )

    # Roll back so we leave no test data in the DB.
    conn.rollback()
