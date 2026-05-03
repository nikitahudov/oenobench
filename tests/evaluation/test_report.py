"""
Tests for src/evaluation/report.py

Pure-function tests run without DB.
Integration test (test_render_basic) requires OENOBENCH_EVAL_TESTS_DB=1.
"""

from __future__ import annotations

import math
import os
import uuid
from datetime import datetime, timezone

import numpy as np
import pytest

from src.evaluation.report import (
    bootstrap_ci,
    fmt_cost,
    fmt_ms,
    fmt_pct,
    fmt_tokens,
    pivot_accuracy,
    DOMAINS,
    STRATEGIES,
)


# ---------------------------------------------------------------------------
# test_format_accuracy — pure formatting helpers
# ---------------------------------------------------------------------------


class TestFormatAccuracy:
    def test_fmt_pct_normal(self):
        assert fmt_pct(8, 10) == "80.0%"

    def test_fmt_pct_full(self):
        assert fmt_pct(10, 10) == "100.0%"

    def test_fmt_pct_zero_numerator(self):
        assert fmt_pct(0, 10) == "0.0%"

    def test_fmt_pct_zero_denominator(self):
        """Empty cell when denominator is 0."""
        assert fmt_pct(0, 0) == "—"

    def test_fmt_pct_one_hundred_percent(self):
        assert fmt_pct(1, 1) == "100.0%"

    def test_fmt_cost_normal(self):
        assert fmt_cost(1.5) == "$1.50"

    def test_fmt_cost_small(self):
        assert fmt_cost(0.001) == "$0.00"

    def test_fmt_cost_none(self):
        assert fmt_cost(None) == "—"

    def test_fmt_cost_nan(self):
        assert fmt_cost(float("nan")) == "—"

    def test_fmt_ms_normal(self):
        assert fmt_ms(1234.7) == "1234"

    def test_fmt_ms_none(self):
        assert fmt_ms(None) == "—"

    def test_fmt_ms_nan(self):
        assert fmt_ms(float("nan")) == "—"

    def test_fmt_tokens_normal(self):
        assert fmt_tokens(512) == "512"

    def test_fmt_tokens_none(self):
        assert fmt_tokens(None) == "—"

    def test_fmt_tokens_zero(self):
        assert fmt_tokens(0) == "0"


# ---------------------------------------------------------------------------
# test_bootstrap_ci_shape
# ---------------------------------------------------------------------------


class TestBootstrapCI:
    def test_shape_all_correct(self):
        arr = np.ones(100)
        mean, lo, hi = bootstrap_ci(arr, n_resamples=500)
        assert lo <= mean <= hi
        assert math.isclose(mean, 1.0)
        assert math.isclose(lo, 1.0)
        assert math.isclose(hi, 1.0)

    def test_shape_all_wrong(self):
        arr = np.zeros(100)
        mean, lo, hi = bootstrap_ci(arr, n_resamples=500)
        assert lo <= mean <= hi
        assert math.isclose(mean, 0.0)

    def test_shape_mixed(self):
        rng = np.random.default_rng(0)
        arr = rng.integers(0, 2, size=200).astype(float)
        mean, lo, hi = bootstrap_ci(arr, n_resamples=500)
        assert lo <= mean <= hi
        assert 0.0 <= lo <= 1.0
        assert 0.0 <= hi <= 1.0

    def test_empty_array(self):
        arr = np.array([], dtype=float)
        mean, lo, hi = bootstrap_ci(arr)
        assert math.isnan(mean)
        assert math.isnan(lo)
        assert math.isnan(hi)

    def test_single_element(self):
        arr = np.array([1.0])
        mean, lo, hi = bootstrap_ci(arr, n_resamples=100)
        assert lo <= mean <= hi

    def test_ci_width_decreases_with_sample_size(self):
        """Larger samples produce narrower CIs (probabilistically)."""
        rng = np.random.default_rng(42)
        arr_small = rng.integers(0, 2, size=20).astype(float)
        arr_large = rng.integers(0, 2, size=2000).astype(float)
        _, lo_s, hi_s = bootstrap_ci(arr_small, n_resamples=500)
        _, lo_l, hi_l = bootstrap_ci(arr_large, n_resamples=500)
        width_small = hi_s - lo_s
        width_large = hi_l - lo_l
        assert width_large < width_small


# ---------------------------------------------------------------------------
# test_strategy_pivot_smoke
# ---------------------------------------------------------------------------


class TestStrategyPivot:
    def _make_rows(self) -> list[dict]:
        return [
            {"config_name": "model-a", "strategy": "fact_to_question", "is_correct": True},
            {"config_name": "model-a", "strategy": "fact_to_question", "is_correct": False},
            {"config_name": "model-a", "strategy": "template", "is_correct": True},
            {"config_name": "model-b", "strategy": "fact_to_question", "is_correct": True},
            {"config_name": "model-b", "strategy": "template", "is_correct": False},
            {"config_name": "model-b", "strategy": "comparative", "is_correct": True},
        ]

    def test_pivot_basic(self):
        rows = self._make_rows()
        pivot = pivot_accuracy(
            rows,
            row_key="config_name",
            col_key="strategy",
            row_order=["model-a", "model-b"],
            col_order=["fact_to_question", "template", "comparative"],
        )
        # model-a / fact_to_question: 1 correct out of 2
        assert pivot[("model-a", "fact_to_question")] == (1, 2)
        # model-a / template: 1 correct out of 1
        assert pivot[("model-a", "template")] == (1, 1)
        # model-a / comparative: no data
        assert pivot[("model-a", "comparative")] == (0, 0)
        # model-b / fact_to_question: 1/1
        assert pivot[("model-b", "fact_to_question")] == (1, 1)
        # model-b / template: 0/1
        assert pivot[("model-b", "template")] == (0, 1)
        # model-b / comparative: 1/1
        assert pivot[("model-b", "comparative")] == (1, 1)

    def test_pivot_all_correct(self):
        rows = [
            {"config_name": "m", "strategy": "template", "is_correct": True},
            {"config_name": "m", "strategy": "template", "is_correct": True},
        ]
        pivot = pivot_accuracy(rows, "config_name", "strategy", ["m"], ["template"])
        assert pivot[("m", "template")] == (2, 2)

    def test_pivot_none_values_skipped(self):
        rows = [
            {"config_name": None, "strategy": "template", "is_correct": True},
            {"config_name": "m", "strategy": None, "is_correct": True},
            {"config_name": "m", "strategy": "template", "is_correct": False},
        ]
        pivot = pivot_accuracy(rows, "config_name", "strategy", ["m"], ["template"])
        # Only the last row should count
        assert pivot[("m", "template")] == (0, 1)

    def test_pivot_accuracy_fmt_integration(self):
        """fmt_pct works correctly on pivot output."""
        rows = [{"config_name": "m", "strategy": "ftq", "is_correct": True}] * 3 + \
               [{"config_name": "m", "strategy": "ftq", "is_correct": False}] * 1
        pivot = pivot_accuracy(rows, "config_name", "strategy", ["m"], ["ftq"])
        correct, total = pivot[("m", "ftq")]
        assert fmt_pct(correct, total) == "75.0%"


# ---------------------------------------------------------------------------
# test_section_sps_matrix_diagonal_n_match
# ---------------------------------------------------------------------------


class TestSectionSpsMatrix:
    """
    Construct a synthetic ``answers`` list with known (model_name, generator)
    pairs across all 5 families.  After rendering Section 4b, parse the
    markdown and assert that each diagonal cell's N equals the count we
    constructed and that the row/column ordering is the canonical
    [anthropic, openai, google, meta, qwen].
    """

    # Map evaluator family -> a slate config name in that family with
    # is_generator_family=True.  These exist in EVAL_CONFIGS post-Foundation.
    EV_MODEL_BY_FAMILY = {
        "anthropic": "claude-opus-4.7",      # slot 1
        "openai":    "gpt-5",                # slot 3
        "google":    "gemini-2.5-pro",       # slot 5
        "meta":      "llama-3.3-70b",        # slot 7
        "qwen":      "qwen-2.5-72b",         # slot 10
    }

    # The DB enum value that maps via GENERATOR_TO_FAMILY back to each family.
    GEN_ENUM_BY_FAMILY = {
        "anthropic": "claude",
        "openai":    "chatgpt",
        "google":    "gemini",
        "meta":      "llama",
        "qwen":      "qwen",
    }

    # Diagonal cell N targets — distinct values so we can verify each cell
    # came from the correct (evaluator, generator) bucket.
    DIAGONAL_N = {
        "anthropic": 7,
        "openai":    9,
        "google":    11,
        "meta":      13,
        "qwen":      5,
    }

    def _build_synthetic_answers(self) -> list[dict]:
        """Build answers with known counts in each diagonal cell.

        For simplicity we fill ONLY the diagonal — off-diagonal cells will
        render as ``— (0)``.  The diagonal counts are the load-bearing thing
        we assert on.
        """
        rows: list[dict] = []
        for fam, n in self.DIAGONAL_N.items():
            for i in range(n):
                rows.append({
                    "model_name": self.EV_MODEL_BY_FAMILY[fam],
                    "generator":  self.GEN_ENUM_BY_FAMILY[fam],
                    # 1 correct out of n -> deterministic, non-zero accuracy.
                    "is_correct": (i == 0),
                })
        return rows

    def test_section_sps_matrix_diagonal_n_match(self):
        from io import StringIO

        from src.evaluation.report import _section_sps_matrix

        answers = self._build_synthetic_answers()
        buf = StringIO()
        _section_sps_matrix(buf, answers)
        out = buf.getvalue()

        # Header is present.
        assert "## 4b. Self-Preference Family Matrix" in out

        families = ["anthropic", "openai", "google", "meta", "qwen"]

        # Header row contains all five families in canonical order.
        # The header line looks like:
        #   | Eval ↓ / Gen → | anthropic | openai | google | meta | qwen |
        header_lines = [ln for ln in out.splitlines() if "Eval" in ln and "Gen" in ln]
        assert len(header_lines) == 1, (
            f"expected exactly one header row, got {header_lines}"
        )
        header = header_lines[0]
        # The five family names must appear in this exact order in the header.
        positions = [header.find(f) for f in families]
        assert all(p > 0 for p in positions), f"missing family in header: {header}"
        assert positions == sorted(positions), (
            f"column order is not [anthropic, openai, google, meta, qwen]: {header}"
        )

        # Body rows: one per evaluator family, in the canonical order.
        body_lines = [
            ln for ln in out.splitlines()
            if ln.startswith("| **") and "**" in ln[3:]
        ]
        assert len(body_lines) == len(families), (
            f"expected {len(families)} body rows, got {len(body_lines)}: {body_lines}"
        )
        for ln, expected_fam in zip(body_lines, families):
            assert f"**{expected_fam}**" in ln, (
                f"expected row for '{expected_fam}', got: {ln}"
            )

        # Each diagonal cell's N must equal the constructed count.
        # Diagonal cell text on row=fam is "{acc:.1%} ({n})" and only the
        # diagonal cell has a non-zero N (off-diagonal stays "— (0)").
        for ln, ev_fam in zip(body_lines, families):
            expected_n = self.DIAGONAL_N[ev_fam]
            # Split the markdown row on "|" and trim.
            parts = [p.strip() for p in ln.split("|")]
            # parts[0] == '' (leading), parts[1] == '**fam**',
            # parts[2..6] == the 5 data cells.
            diag_idx = families.index(ev_fam)
            cell = parts[2 + diag_idx]
            assert f"({expected_n})" in cell, (
                f"row '{ev_fam}': diagonal cell expected N={expected_n}, "
                f"got cell '{cell}' (full row: {ln})"
            )
            # Off-diagonal cells should be "— (0)" since we didn't fill them.
            for off_idx, off_fam in enumerate(families):
                if off_idx == diag_idx:
                    continue
                off_cell = parts[2 + off_idx]
                assert off_cell == "— (0)", (
                    f"row '{ev_fam}', col '{off_fam}': expected '— (0)', "
                    f"got '{off_cell}'"
                )


# ---------------------------------------------------------------------------
# test_render_basic — integration test (gated by env var)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# test_load_answers_joins_genmeta_for_public_schema
# ---------------------------------------------------------------------------


class TestLoadAnswersSchema:
    """
    Verify that ``_load_answers`` builds the same column set for both the
    ``sample`` and ``public`` corpus schemas, and that the SQL contains the
    expected joins / projections.  We monkeypatch the cursor's ``execute`` to
    capture the SQL string without hitting the database.
    """

    class _FakeCursor:
        def __init__(self):
            self.captured_sql: str | None = None
            self.captured_params: tuple | None = None

        def execute(self, sql, params=None):
            self.captured_sql = sql
            self.captured_params = params

        def fetchall(self):
            return []

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    class _FakeConn:
        def __init__(self):
            self.cursor_obj = TestLoadAnswersSchema._FakeCursor()

        def cursor(self):
            return self.cursor_obj

    def _captured_sql(self, schema: str) -> str:
        from src.evaluation.report import _load_answers

        conn = self._FakeConn()
        rows = _load_answers(conn, run_id="00000000-0000-0000-0000-000000000000",
                             corpus_schema=schema)
        assert rows == []
        sql = conn.cursor_obj.captured_sql
        assert sql is not None
        return sql

    def test_public_schema_joins_genmeta(self):
        sql = self._captured_sql("public")
        assert "LEFT JOIN public.generation_metadata gm ON gm.question_id = q.id" in sql
        assert "gm.generator::text AS generator" in sql
        assert "gm.generation_method::text AS strategy" in sql
        assert "q.tags" in sql
        assert "q.difficulty::text AS difficulty" in sql
        # Should not contain a NULL placeholder for generator anymore.
        assert "NULL::text AS generator" not in sql

    def test_sample_schema_joins_genmeta(self):
        sql = self._captured_sql("sample")
        assert "LEFT JOIN sample.generation_metadata gm ON gm.question_id = q.id" in sql
        assert "gm.generator::text AS generator" in sql
        assert "gm.generation_method::text AS strategy" in sql
        assert "q.tags" in sql
        assert "q.difficulty::text AS difficulty" in sql

    def test_both_schemas_select_identical_columns(self):
        """
        Sanity-check that the SELECT clause is structurally identical for the
        two corpus schemas (modulo the schema-qualified table refs).
        """
        sample_sql = self._captured_sql("sample")
        public_sql = self._captured_sql("public")
        # Strip the schema name to get a schema-agnostic comparison.
        normalised_sample = sample_sql.replace("sample.", "")
        normalised_public = public_sql.replace("public.", "")
        assert normalised_sample == normalised_public


# ---------------------------------------------------------------------------
# test_qwen_family_mapping
# ---------------------------------------------------------------------------


class TestQwenFamilyMapping:
    def test_generator_to_family_maps_qwen_to_qwen(self):
        from src.evaluation.report import GENERATOR_TO_FAMILY
        assert GENERATOR_TO_FAMILY["qwen"] == "qwen"

    def test_qwen_72b_is_generator_family(self):
        from src.evaluation.configs import by_slot
        assert by_slot(10).is_generator_family is True
        assert by_slot(10).family == "qwen"

    def test_qwen_7b_is_generator_family(self):
        from src.evaluation.configs import by_slot
        assert by_slot(11).is_generator_family is True
        assert by_slot(11).family == "qwen"


@pytest.mark.integration
@pytest.mark.skipif(
    os.environ.get("OENOBENCH_EVAL_TESTS_DB") != "1",
    reason="Set OENOBENCH_EVAL_TESTS_DB=1 to run DB integration tests",
)
class TestRenderBasic:
    """
    Inserts fixture rows into evaluation_runs + evaluation_answers under a unique
    test tag, runs the report renderer, then cleans up.
    """

    FIXTURE_CONFIGS = [
        "fixture-model-alpha",
        "fixture-model-beta",
        "fixture-model-gamma",
        "fixture-model-delta",
        "fixture-model-epsilon",
    ]

    def _get_sample_question_ids(self, conn, n: int = 10) -> list[str]:
        """Grab real question UUIDs from sample.questions."""
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM sample.questions LIMIT %s", (n,))
            rows = cur.fetchall()
        return [str(r["id"]) for r in rows]

    def _insert_fixture_run(self, conn, tag: str) -> str:
        """Insert a fixture evaluation_run; return run_id."""
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO evaluation_runs
                    (model_name, prompt_strategy, metadata, total_questions,
                     correct_count, started_at, completed_at, total_cost_usd)
                VALUES (%s, %s, %s::jsonb, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    "fixture-model-alpha",
                    "zero_shot",
                    '{"tag": "' + tag + '", "corpus": "sample_v1"}',
                    50,
                    35,
                    datetime(2026, 5, 1, 10, 0, 0, tzinfo=timezone.utc),
                    datetime(2026, 5, 1, 10, 8, 0, tzinfo=timezone.utc),
                    0.42,
                ),
            )
            run_id = str(cur.fetchone()["id"])
        conn.commit()
        return run_id

    def _insert_fixture_answers(self, conn, run_id: str, question_ids: list[str]) -> None:
        """Insert fixture answers across 5 configs and question_ids."""
        import random
        random.seed(42)
        with conn.cursor() as cur:
            for config_name in self.FIXTURE_CONFIGS:
                for qid in question_ids:
                    is_correct = random.random() > 0.35
                    cur.execute(
                        """
                        INSERT INTO evaluation_answers
                            (run_id, question_id, model_name, is_correct,
                             parsed_answer, input_tokens, output_tokens,
                             reasoning_tokens, cost_usd, latency_ms,
                             response_time_ms)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT DO NOTHING
                        """,
                        (
                            run_id,
                            qid,
                            config_name,
                            is_correct,
                            "A" if is_correct else "B",
                            random.randint(180, 320),
                            random.randint(1, 5),
                            0,
                            round(random.uniform(0.0001, 0.005), 6),
                            random.randint(800, 3500),
                            random.randint(800, 3500),
                        ),
                    )
        conn.commit()

    def _cleanup(self, conn, run_id: str) -> None:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM evaluation_answers WHERE run_id = %s", (run_id,))
            cur.execute("DELETE FROM evaluation_runs WHERE id = %s", (run_id,))
        conn.commit()

    def test_render_basic(self, tmp_path):
        from src.utils.db import get_pg
        from src.evaluation.report import render_report

        conn = get_pg()
        tag = f"test_report_pytest_{uuid.uuid4().hex[:8]}"
        run_id = None

        try:
            question_ids = self._get_sample_question_ids(conn, n=10)
            assert len(question_ids) >= 5, "Need at least 5 sample questions"

            run_id = self._insert_fixture_run(conn, tag)
            self._insert_fixture_answers(conn, run_id, question_ids)

            output_path = str(tmp_path / f"eval_{tag}.md")
            report_md = render_report(tag=tag, output_path=output_path)

            # Assert all major sections present
            assert "# OenoBench Evaluation Report" in report_md
            assert "## 1. Per-Config Summary" in report_md
            assert "## 2. Per-Config × Per-Domain Accuracy" in report_md
            assert "## 3. Per-Config × Per-Strategy Accuracy" in report_md
            assert "## 4. Self-Preference Score" in report_md
            assert "## 5. Reasoning-Effect Deltas" in report_md
            assert "## 6. Cost & Wall Ledger" in report_md

            # Assert fixture configs appear
            for cfg_name in self.FIXTURE_CONFIGS:
                assert cfg_name in report_md

            # Assert at least one accuracy cell present in domain grid
            assert "Wine Regions" in report_md or "wine_regions" in report_md

            # Assert at least one strategy column present
            assert "FTQ" in report_md or "fact_to_question" in report_md

            # Assert output file was written
            assert os.path.exists(output_path)
            written = open(output_path).read()
            assert len(written) > 500

        finally:
            if run_id:
                self._cleanup(conn, run_id)
