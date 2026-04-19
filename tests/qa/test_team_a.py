"""Team A agent tests. No DB, no API — in-memory finding dicts only."""

from __future__ import annotations

from tests.qa.fixtures.sample_questions import (
    BLEND_QUESTION,
    CATEGORY_LEAK_QUESTION,
    CLEAN_QUESTION,
    LENGTH_BIAS_QUESTION,
    LLM_FREEFORM_QUESTIONS,
    POSITION_BIAS_BATCH,
    TEMPLATE_QUESTIONS,
    VAGUE_STEM_QUESTION,
    VERBATIM_QUESTION,
)

RUN_ID = "00000000-0000-0000-0000-00000000dead"


# ─── A1 ─────────────────────────────────────────────────────────────────────


def test_a1_passes_clean_question():
    from src.qa.agents.team_a_static import run_a1_lexical_hygiene

    findings = run_a1_lexical_hygiene(RUN_ID, [CLEAN_QUESTION])
    assert findings[0]["severity"] == "pass"


def test_a1_fails_vague_stem():
    from src.qa.agents.team_a_static import run_a1_lexical_hygiene

    findings = run_a1_lexical_hygiene(RUN_ID, [VAGUE_STEM_QUESTION])
    f = findings[0]
    assert f["severity"] == "fail"
    matches = f["payload"]["matches"]
    assert "question_text" in matches
    assert any("legendary" in h.lower() or "world-renowned" in h.lower()
               or "wine region" in h.lower() for h in matches["question_text"])


def test_a1_fails_blend_as_variety():
    from src.qa.agents.team_a_static import run_a1_lexical_hygiene

    findings = run_a1_lexical_hygiene(RUN_ID, [BLEND_QUESTION])
    # Blend-as-variety regex requires a verb pattern; depending on shape this
    # may land as fail (question_text match) or warn (options match). Either way
    # it must not pass cleanly.
    assert findings[0]["severity"] != "pass"


# ─── A2 ─────────────────────────────────────────────────────────────────────


def test_a2_detects_position_bias_in_cell():
    from src.qa.agents.team_a_static import run_a2_bias_stats

    # 25 questions all with correct_answer=A → strong position bias
    findings = run_a2_bias_stats(RUN_ID, list(POSITION_BIAS_BATCH))
    # At least one cell plus the corpus-wide finding should flag fail
    severities = [f["severity"] for f in findings]
    assert "fail" in severities


def test_a2_passes_balanced_corpus():
    from src.qa.agents.team_a_static import run_a2_bias_stats

    # Build 40 well-balanced questions cycling A/B/C/D
    from copy import deepcopy

    balanced = []
    for i in range(40):
        q = deepcopy(CLEAN_QUESTION)
        q["uuid"] = f"00000000-0000-0000-0000-{i:012d}"
        q["correct_answer"] = "ABCD"[i % 4]
        balanced.append(q)
    findings = run_a2_bias_stats(RUN_ID, balanced)
    # Single bundled finding now; corpus stats nested in payload['corpus']
    assert len(findings) == 1
    bundle = findings[0]
    assert bundle["payload"]["corpus"]["cell"] == "CORPUS"
    assert bundle["severity"] in {"pass", "warn"}


# ─── A3 ─────────────────────────────────────────────────────────────────────


def test_a3_detects_verbatim_copy():
    from src.qa.agents.team_a_static import run_a3_fact_echo

    findings = run_a3_fact_echo(RUN_ID, [VERBATIM_QUESTION])
    f = findings[0]
    assert f["severity"] == "fail"
    assert f["payload"]["lcs_ratio"] >= 0.6


def test_a3_passes_paraphrased_question():
    from src.qa.agents.team_a_static import run_a3_fact_echo

    findings = run_a3_fact_echo(RUN_ID, [CLEAN_QUESTION])
    assert findings[0]["severity"] in {"pass", "warn"}


# ─── A4 ─────────────────────────────────────────────────────────────────────


def test_a4_trains_and_scores():
    from src.qa.agents.team_a_static import run_a4_template_fingerprint

    corpus = TEMPLATE_QUESTIONS + LLM_FREEFORM_QUESTIONS
    findings = run_a4_template_fingerprint(RUN_ID, corpus)
    pop = next(f for f in findings if f["question_id"] is None)
    # Either a trained classifier or a data-too-small pass
    assert "test_auc" in pop["payload"] or "note" in pop["payload"]
