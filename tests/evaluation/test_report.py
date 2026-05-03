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


# ---------------------------------------------------------------------------
# test_section_item_analysis_distribution_sums
# ---------------------------------------------------------------------------


class TestSectionItemAnalysis:
    """Tests for Section 9 — item analysis."""

    def _synth_answers(
        self,
        n_questions: int = 100,
        n_configs: int = 16,
    ) -> list[dict]:
        """Build a deterministic synthetic answers list.

        Question q (0..n_questions-1) is answered correctly by config c
        (0..n_configs-1) iff (q + c) % n_configs <  c_threshold(q).  We use
        ``c_threshold = (q % (n_configs + 1))`` so that every k-bucket is
        exercised (q with threshold 0 -> 0 correct, q with threshold n_configs
        -> all configs correct).
        """
        rows: list[dict] = []
        for q in range(n_questions):
            threshold = q % (n_configs + 1)
            for c in range(n_configs):
                # Configs 0..threshold-1 mark this question correct;
                # configs threshold..n_configs-1 mark it incorrect.
                is_correct = c < threshold
                rows.append({
                    "question_id": f"q{q:03d}",
                    "model_name": f"cfg{c:02d}",
                    "is_correct": is_correct,
                    "parsed_answer": "A" if is_correct else "B",
                    "cost_usd": 0.001,
                    "or_cost_usd": None,
                    "domain": "wine_regions",
                })
        return rows

    def _parse_9a_histogram(self, md: str, n_configs: int) -> dict[int, int]:
        """Parse the 9a histogram from rendered markdown.

        Returns {k: count_of_questions} for k = 0..n_configs.
        """
        from io import StringIO as _S
        # Locate the section.
        idx = md.find("### 9a.")
        assert idx != -1, "9a section not found in rendered markdown"
        end = md.find("### 9b.", idx)
        block = md[idx:end] if end != -1 else md[idx:]

        result: dict[int, int] = {}
        for line in block.splitlines():
            line = line.strip()
            if not line.startswith("|"):
                continue
            # Skip header / separator rows.
            if "k correct" in line or set(line.replace("|", "").strip()) <= {"-", ":", " "}:
                continue
            cells = [c.strip() for c in line.strip("|").split("|")]
            if len(cells) < 3:
                continue
            try:
                k = int(cells[0])
                cnt = int(cells[1])
            except ValueError:
                continue
            result[k] = cnt
        return result

    def test_section_item_analysis_distribution_sums(self):
        """9a histogram counts must sum to total question count."""
        from io import StringIO
        from src.evaluation.report import _section_item_analysis

        n_questions = 100
        n_configs = 16
        answers = self._synth_answers(n_questions=n_questions, n_configs=n_configs)

        buf = StringIO()
        _section_item_analysis(buf, answers)
        md = buf.getvalue()

        # Spot-check headers.
        assert "## 9. Item Analysis" in md
        assert "### 9a." in md
        assert "### 9b." in md
        assert "### 9c." in md
        assert "### 9d." in md

        histogram = self._parse_9a_histogram(md, n_configs=n_configs)
        # All k from 0..n_configs must be present.
        for k in range(n_configs + 1):
            assert k in histogram, f"k={k} missing from 9a histogram"

        # Sum across all buckets must equal the question count.
        assert sum(histogram.values()) == n_questions

    def test_section_item_analysis_handles_empty(self):
        """No answers should produce a graceful skip message."""
        from io import StringIO
        from src.evaluation.report import _section_item_analysis

        buf = StringIO()
        _section_item_analysis(buf, [])
        md = buf.getvalue()
        assert "## 9. Item Analysis" in md
        assert "No answers" in md or "no answers" in md.lower()


# ---------------------------------------------------------------------------
# test_section_cost_efficiency_orders_by_efficiency
# ---------------------------------------------------------------------------


class TestSectionCostEfficiency:
    """Tests for Section 10 — cost efficiency."""

    def _parse_efficiency_rows(self, md: str) -> list[tuple[str, str]]:
        """Parse Section 10 rows; return list of (config_name, cost_per_correct_str)."""
        idx = md.find("## 10. Cost-Efficiency")
        assert idx != -1, "Section 10 header not found"
        block = md[idx:]
        # Stop at next section if any.
        next_section = block.find("\n## ", 1)
        if next_section != -1:
            block = block[:next_section]

        rows: list[tuple[str, str]] = []
        for line in block.splitlines():
            line = line.strip()
            if not line.startswith("|"):
                continue
            if "Slot" in line and "Config" in line:
                continue
            if set(line.replace("|", "").strip()) <= {"-", ":", " "}:
                continue
            cells = [c.strip() for c in line.strip("|").split("|")]
            if len(cells) < 5:
                continue
            # cells: slot, config, correct, effective_cost, cost_per_correct
            rows.append((cells[1], cells[4]))
        return rows

    def test_section_cost_efficiency_orders_by_efficiency(self):
        """Configs should appear in ascending cost-per-correct order."""
        from io import StringIO
        from src.evaluation.report import _section_cost_efficiency

        # Build 3 configs with known cost-per-correct values:
        #   cfg-cheap   -> 10 questions, 5 correct, $1.00 total -> $0.20 per correct
        #   cfg-medium  -> 10 questions, 4 correct, $2.00 total -> $0.50 per correct
        #   cfg-pricey  -> 10 questions, 2 correct, $4.00 total -> $2.00 per correct
        plans = [
            ("cfg-pricey", 10, 2, 4.00),
            ("cfg-cheap", 10, 5, 1.00),
            ("cfg-medium", 10, 4, 2.00),
        ]
        answers: list[dict] = []
        for name, n_q, n_correct, total_cost in plans:
            per_call_cost = total_cost / n_q
            for i in range(n_q):
                answers.append({
                    "question_id": f"{name}-q{i:02d}",
                    "model_name": name,
                    "is_correct": i < n_correct,
                    "parsed_answer": "A",
                    "cost_usd": per_call_cost,
                    "or_cost_usd": None,
                    "domain": "wine_regions",
                })

        buf = StringIO()
        _section_cost_efficiency(buf, answers)
        md = buf.getvalue()

        rows = self._parse_efficiency_rows(md)
        assert len(rows) == 3
        config_order = [r[0] for r in rows]
        assert config_order == ["cfg-cheap", "cfg-medium", "cfg-pricey"]

    def test_section_cost_efficiency_zero_correct_sorts_to_bottom(self):
        """Configs with 0 correct answers should render '—' and sort last."""
        from io import StringIO
        from src.evaluation.report import _section_cost_efficiency

        plans = [
            # name, n_questions, n_correct, total_cost
            ("cfg-zero", 10, 0, 0.50),
            ("cfg-some", 10, 5, 1.00),  # $0.20 per correct
        ]
        answers: list[dict] = []
        for name, n_q, n_correct, total_cost in plans:
            per_call_cost = total_cost / n_q
            for i in range(n_q):
                answers.append({
                    "question_id": f"{name}-q{i:02d}",
                    "model_name": name,
                    "is_correct": i < n_correct,
                    "parsed_answer": "A",
                    "cost_usd": per_call_cost,
                    "or_cost_usd": None,
                    "domain": "wine_regions",
                })

        buf = StringIO()
        _section_cost_efficiency(buf, answers)
        md = buf.getvalue()

        rows = self._parse_efficiency_rows(md)
        assert len(rows) == 2
        # Zero-correct row must be last.
        assert rows[-1][0] == "cfg-zero"
        assert rows[-1][1] == "—"
        # First row must be cfg-some with a price.
        assert rows[0][0] == "cfg-some"
        assert rows[0][1].startswith("$")


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
