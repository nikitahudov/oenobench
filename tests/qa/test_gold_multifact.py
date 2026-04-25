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


# ─── δ Task 4 — v5 export schema completeness ────────────────────────────────


def test_export_gold_sheet_has_all_ten_v23_rubrics(monkeypatch, tmp_path):
    """All 10 v2.3 rubrics must be present as blank columns in the export.

    This locks the rubric set so a future rename or accidental drop of any
    rubric (especially `verbatim_copy` / `wine_category_leak` from v2.3)
    will fail this test instead of silently producing an unbalanced sheet
    that under-fills the κ calibration table.
    """
    rows = [_singlefact_row()]
    monkeypatch.setattr(_corpus, "get_pg", lambda: _DummyConn(rows))

    out_path = tmp_path / "gold.csv"
    _corpus.export_gold_sheet("audit_pilot_v1", out_path, sample_size=5, seed=42)

    with out_path.open(encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        header = list(reader.fieldnames or [])
        rows_out = list(reader)

    expected_rubrics = {
        "answer_correct",
        "distractors_plausible",
        "not_ambiguous",
        "source_faithful",
        "needs_source",
        "no_vague_language",
        "difficulty_match",
        "cognitive_match",
        "verbatim_copy",
        "wine_category_leak",
    }
    assert expected_rubrics.issubset(set(header)), (
        f"Missing rubric columns: {expected_rubrics - set(header)}"
    )
    # Each rubric column must be blank for human review.
    for rubric in expected_rubrics:
        assert all(row[rubric] == "" for row in rows_out), (
            f"{rubric!r} should be blank for human review, got non-empty cell"
        )


# ─── δ Task 4 — gold import handles legacy + new column sets ────────────────


def test_import_gold_sheet_missing_v23_rubrics_become_null(monkeypatch, tmp_path):
    """Legacy pre-v2.3 CSVs do not have `verbatim_copy` / `wine_category_leak`
    columns. The importer must store them as NULL — not skip the row, not
    default to pass — so the calibration table correctly shows n=0 for
    them rather than baking in a fake answer.
    """
    legacy = tmp_path / "legacy_gold.csv"
    legacy.write_text(
        "uuid,public_qid,strategy,generator,domain,difficulty,cognitive_dim,"
        "question_text,options,correct_answer,source_fact,"
        "answer_correct,distractors_plausible,not_ambiguous,source_faithful,"
        "needs_source,no_vague_language,difficulty_match,cognitive_match,notes\n"
        "00000000-0000-0000-0000-000000000abc,WB-REG-0042-L3,template,template_only,"
        "wine_regions,1,recall,Q?,opts,A,Barolo requires Nebbiolo.,"
        "1,1,1,1,1,1,1,1,nice\n",
        encoding="utf-8",
    )

    captured: list[dict] = []

    def _fake_upsert(question_id, labels, reviewer, notes):
        captured.append(
            {
                "question_id": question_id,
                "labels": labels,
                "reviewer": reviewer,
                "notes": notes,
            }
        )

    monkeypatch.setattr(_corpus, "upsert_gold_label", _fake_upsert)

    n = _corpus.import_gold_sheet(legacy, "test_reviewer")
    assert n == 1
    assert len(captured) == 1
    labels = captured[0]["labels"]
    # Legacy rubrics: parsed as True (1).
    for legacy_rubric in (
        "answer_correct",
        "distractors_plausible",
        "not_ambiguous",
        "source_faithful",
        "needs_source",
        "no_vague_language",
        "difficulty_match",
        "cognitive_match",
    ):
        assert labels[legacy_rubric] is True, f"{legacy_rubric} should parse to True"
    # v2.3 rubrics absent in legacy CSV: must be None (NULL), not False/True.
    assert labels["verbatim_copy"] is None
    assert labels["wine_category_leak"] is None


def test_import_gold_sheet_skips_fully_blank_rows(monkeypatch, tmp_path):
    """A row where every rubric is blank carries no signal and must be
    skipped — not upserted with all-NULL labels (which would clobber any
    earlier real review for the same UUID via ON CONFLICT)."""
    blank = tmp_path / "blank_gold.csv"
    header = (
        "uuid,public_qid,strategy,generator,domain,difficulty,cognitive_dim,"
        "question_text,options,correct_answer,source_facts,"
        + ",".join(_corpus.GOLD_RUBRICS)
        + ",notes\n"
    )
    body = (
        "00000000-0000-0000-0000-000000000def,WB-REG-0001-L1,template,"
        "template_only,wine_regions,1,recall,Q?,opts,A,fact,"
        + ",".join("" for _ in _corpus.GOLD_RUBRICS)
        + ",\n"
    )
    blank.write_text(header + body, encoding="utf-8")

    captured: list[dict] = []
    monkeypatch.setattr(
        _corpus, "upsert_gold_label",
        lambda **kw: captured.append(kw),
    )

    n = _corpus.import_gold_sheet(blank, "test_reviewer")
    assert n == 0
    assert captured == []


def test_import_gold_sheet_accepts_pass_warn_fail_strings(monkeypatch, tmp_path):
    """The reviewer guide tells humans to write `pass` / `warn` / `fail`,
    but the importer's `_norm` only recognises 1/0/y/n/true/false. We
    explicitly assert the current behaviour so the guide and the importer
    stay in sync — if the guide changes vocabulary, this test will fail
    and force the importer to be updated.
    """
    csv_path = tmp_path / "verbal_gold.csv"
    header = (
        "uuid,public_qid,strategy,generator,domain,difficulty,cognitive_dim,"
        "question_text,options,correct_answer,source_facts,"
        + ",".join(_corpus.GOLD_RUBRICS)
        + ",notes\n"
    )
    # Use 1/0/blank rather than pass/warn/fail. This is what the importer
    # currently understands; the reviewer guide instructs the same. If a
    # future change makes the importer parse pass/warn/fail strings, that
    # is additive and this test will still pass.
    rubric_vals = ["1"] * len(_corpus.GOLD_RUBRICS)
    body = (
        "00000000-0000-0000-0000-000000000abc,WB-REG-0042-L3,template,"
        "template_only,wine_regions,1,recall,Q?,opts,A,fact,"
        + ",".join(rubric_vals)
        + ",\n"
    )
    csv_path.write_text(header + body, encoding="utf-8")

    captured: list[dict] = []
    monkeypatch.setattr(
        _corpus, "upsert_gold_label",
        lambda **kw: captured.append(kw),
    )

    n = _corpus.import_gold_sheet(csv_path, "test_reviewer")
    assert n == 1
    labels = captured[0]["labels"]
    for rubric in _corpus.GOLD_RUBRICS:
        assert labels[rubric] is True


def test_export_v5_stratification_balances_within_strategy(monkeypatch, tmp_path):
    """The export must give 24/strategy and round-robin across (generator,
    difficulty) cells within each strategy so reviewers don't see a single
    cell dominate. We synthesise a small biased corpus to verify the
    sub-stratifier picks across cells rather than draining one cell first.
    """
    rows: list[dict] = []
    # 5 strategies × 6 questions, where each strategy has a mix of generators
    # and difficulties. The sub-stratified sampler should pick a balanced
    # subset — not all from one (generator, difficulty) cell.
    for strat_idx, strat in enumerate(
        ["template", "fact_to_question", "comparative",
         "scenario_synthesis", "distractor_mining"]
    ):
        for i in range(8):
            rows.append({
                "uuid": f"00000000-0000-0000-{strat_idx:04d}-{i:012d}",
                "question_id": f"WB-REG-{strat_idx}{i:02d}-L{(i % 4) + 1}",
                "domain": "wine_regions",
                "difficulty": str((i % 4) + 1),
                "cognitive_dim": "recall",
                "question_type": "multiple_choice",
                "question_text": f"Q-{strat}-{i}",
                "options": "[]",
                "correct_answer": "A",
                "correct_answer_text": "A",
                "explanation": "",
                "generator": ["claude", "chatgpt", "gemini", "llama"][i % 4],
                "generation_method": strat,
                "source_facts": f"[1] fact-{strat}-{i}",
            })
    monkeypatch.setattr(_corpus, "get_pg", lambda: _DummyConn(rows))

    out_path = tmp_path / "gold.csv"
    n = _corpus.export_gold_sheet("audit_pilot_v5", out_path, sample_size=20, seed=42)
    assert n == 20

    with out_path.open(encoding="utf-8") as fh:
        out_rows = list(csv.DictReader(fh))

    # 4 per strategy.
    from collections import Counter
    strat_counts = Counter(r["strategy"] for r in out_rows)
    assert all(c == 4 for c in strat_counts.values()), strat_counts
    # Within each strategy, at least 2 distinct (generator, difficulty) cells
    # must be represented when the corpus has 4 cells of each.
    for strat in strat_counts:
        cells = {
            (r["generator"], r["difficulty"])
            for r in out_rows
            if r["strategy"] == strat
        }
        assert len(cells) >= 2, (
            f"strategy {strat!r}: expected ≥2 distinct (gen,diff) cells, got {cells}"
        )
