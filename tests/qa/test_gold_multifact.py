"""δ-1: gold-sheet export must surface ALL linked source facts per question.

The pre-fix sheet showed only one fact even when a question was generated
from 2-5 facts (`comparative`, `scenario_synthesis`, `distractor_mining`),
which made the human reviewer unable to judge `source_faithful` fairly
on multi-fact strategies (see docs/GOLD_CALIBRATION_ANALYSIS.md §3).
"""

from __future__ import annotations

import csv
from pathlib import Path

from src.qa import _corpus


class _DummyCursor:
    """Minimal `psycopg2` cursor stand-in — captures the SQL it sees and
    serves a fixed result set when `fetchall()` is called.
    """

    def __init__(self, rows):
        self._rows = rows
        self.last_sql = ""
        self.last_params = ()

    def execute(self, sql, params):
        self.last_sql = sql
        self.last_params = params

    def fetchall(self):
        return self._rows


class _DummyConn:
    def __init__(self, rows):
        self._cursor = _DummyCursor(rows)

    def cursor(self):
        return self._cursor


def _multifact_row():
    """Two-fact comparative-style question that exercises the join."""
    return {
        "uuid": "00000000-0000-0000-0000-000000000abc",
        "question_id": "WB-REG-0042-L3",
        "domain": "wine_regions",
        "difficulty": "3",
        "cognitive_dim": "compare",
        "question_type": "multiple_choice",
        "question_text": "Which DOCG requires 100% Nebbiolo and which permits a Barbera blend?",
        "options": [
            {"id": "A", "text": "Barolo / Barbaresco"},
            {"id": "B", "text": "Barolo / Langhe Nebbiolo"},
            {"id": "C", "text": "Barbaresco / Roero"},
            {"id": "D", "text": "Roero / Nebbiolo d'Alba"},
        ],
        "correct_answer": "B",
        "correct_answer_text": "Barolo / Langhe Nebbiolo",
        "explanation": "Barolo DOCG requires 100% Nebbiolo; Langhe Nebbiolo can be blended.",
        "generator": "claude",
        "generation_method": "comparative",
        "source_facts": (
            "[1] Barolo DOCG requires 100% Nebbiolo grapes.\n"
            "---\n"
            "[2] Langhe Nebbiolo DOC permits a blend including Barbera up to 15%."
        ),
    }


def _singlefact_row():
    return {
        "uuid": "00000000-0000-0000-0000-000000000def",
        "question_id": "WB-REG-0001-L1",
        "domain": "wine_regions",
        "difficulty": "1",
        "cognitive_dim": "recall",
        "question_type": "multiple_choice",
        "question_text": "Which grape is required for Barolo DOCG?",
        "options": [
            {"id": "A", "text": "Nebbiolo"},
            {"id": "B", "text": "Barbera"},
            {"id": "C", "text": "Sangiovese"},
            {"id": "D", "text": "Dolcetto"},
        ],
        "correct_answer": "A",
        "correct_answer_text": "Nebbiolo",
        "explanation": "Barolo DOCG requires 100% Nebbiolo.",
        "generator": "claude",
        "generation_method": "fact_to_question",
        "source_facts": "[1] Barolo DOCG requires 100% Nebbiolo grapes.",
    }


def test_export_gold_sheet_emits_source_facts_column(monkeypatch, tmp_path):
    rows = [_multifact_row(), _singlefact_row()]
    monkeypatch.setattr(_corpus, "get_pg", lambda: _DummyConn(rows))

    out_path = tmp_path / "gold.csv"
    n = _corpus.export_gold_sheet("audit_pilot_v1", out_path, sample_size=10, seed=42)
    assert n == 2

    with out_path.open(encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        # Header MUST use the new column name
        assert "source_facts" in reader.fieldnames
        # Old column name must NOT survive
        assert "source_fact" not in reader.fieldnames

        rows_out = list(reader)

    by_qid = {r["public_qid"]: r for r in rows_out}

    multi = by_qid["WB-REG-0042-L3"]
    facts_block = multi["source_facts"]
    assert "[1] " in facts_block
    assert "[2] " in facts_block
    assert "\n---\n" in facts_block
    assert "Nebbiolo" in facts_block
    assert "Langhe Nebbiolo" in facts_block

    single = by_qid["WB-REG-0001-L1"]
    assert single["source_facts"].startswith("[1] ")
    # No '---' separator on single-fact questions
    assert "---" not in single["source_facts"]


def test_export_gold_sheet_query_uses_left_join_and_aggregation(monkeypatch, tmp_path):
    """The new SQL must group by question and aggregate fact texts so we
    don't lose questions whose facts have been deleted (LEFT JOIN) and so
    we surface every linked fact (string_agg)."""
    rows = [_multifact_row()]
    dummy = _DummyConn(rows)
    monkeypatch.setattr(_corpus, "get_pg", lambda: dummy)

    out_path = tmp_path / "gold.csv"
    _corpus.export_gold_sheet("audit_pilot_v1", out_path, sample_size=5, seed=42)

    # Normalise whitespace so we can match SQL keywords regardless of formatting.
    import re

    sql = re.sub(r"\s+", " ", dummy._cursor.last_sql.lower())
    assert "left join" in sql, "Expected LEFT JOIN to keep questions with deleted facts"
    assert "string_agg" in sql, "Expected string_agg(...) to roll up multi-fact bundles"
    assert "group by" in sql, "Expected GROUP BY q.id to collapse fact rows per question"
    assert "source_facts" in sql, "Expected the column alias source_facts in the SELECT"


def test_export_gold_sheet_column_count_unchanged(monkeypatch, tmp_path):
    """Header column count tracks the canonical rubric list.

    v2.3 Team γ added two narrow-proxy rubrics (`verbatim_copy`,
    `wine_category_leak`) that map to the A3 / C2 LLM signals at correct
    granularity. The header width grows accordingly; the rubric column
    block still starts immediately after the 11 metadata columns.
    """
    rows = [_singlefact_row()]
    monkeypatch.setattr(_corpus, "get_pg", lambda: _DummyConn(rows))

    out_path = tmp_path / "gold.csv"
    _corpus.export_gold_sheet("audit_pilot_v1", out_path, sample_size=5, seed=42)

    with out_path.open(encoding="utf-8") as fh:
        reader = csv.reader(fh)
        header = next(reader)

    # 11 metadata columns + len(GOLD_RUBRICS) rubric columns + 1 notes column
    expected = 11 + len(_corpus.GOLD_RUBRICS) + 1
    assert len(header) == expected
    # The rubric column indices must be unchanged (rubric block starts at col 11).
    rubric_idx = header.index("answer_correct")
    assert rubric_idx == 11
    # v2.3 Team γ — new rubrics must appear in the emitted header so human
    # reviewers can fill them in on the next gold sheet.
    assert "verbatim_copy" in header
    assert "wine_category_leak" in header
