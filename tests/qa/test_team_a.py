"""Team A agent tests. No DB, no API — in-memory finding dicts only."""

from __future__ import annotations

from tests.qa.fixtures.sample_questions import (
    A3_BORDERLINE_LCS_QUESTION,
    A3_HIGH_LCS_QUESTION,
    A3_LONG_NGRAM_QUESTION,
    BLEND_QUESTION,
    CATEGORY_LEAK_QUESTION,
    CLEAN_QUESTION,
    LENGTH_BIAS_QUESTION,
    LLM_FREEFORM_QUESTIONS,
    POSITION_BIAS_BATCH,
    TEMPLATE_QUESTIONS,
    TRUE_FALSE_HIGH_OVERLAP_QUESTION,
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


# ─── A1 v2.3.1 — Phase 2g.9 false-positive fixes ─────────────────────────────
# Audit #7 surfaced two regex over-matches: bare `celebrated` flagged the
# past-tense verb in factual prose, and `notable for` flagged factual "notable
# for being the country's first" constructions. These tests pin those FPs so
# we don't regress the loosened patterns.


def _mk_for_regex(qtext: str) -> dict:
    """Minimal question dict that A1 will accept; only question_text matters."""
    return {
        "uuid": "00000000-0000-0000-0000-0000a1regex01",
        "question_text": qtext,
        "options": [
            {"id": "A", "text": "Option A"},
            {"id": "B", "text": "Option B"},
            {"id": "C", "text": "Option C"},
            {"id": "D", "text": "Option D"},
        ],
        "correct_answer": "A",
        "correct_answer_text": "Option A",
        "explanation": "",
        "question_type": "multiple_choice",
        "difficulty": "2",
        "domain": "wine_regions",
    }


def test_a1_does_not_flag_celebrated_as_past_tense_verb():
    """v2.3.1: 'celebrated' as a past-tense verb (factual narrative) must
    not match. Fixture mirrors v7 fail #5 (a5564a29...): a Roman poet
    'celebrated the landscape during harvest'."""
    from src.qa.agents.team_a_static import run_a1_lexical_hygiene

    q = _mk_for_regex(
        "Which wine region had a Roman-era poet who celebrated the landscape "
        "during harvest in his published verses?"
    )
    findings = run_a1_lexical_hygiene(RUN_ID, [q])
    f = findings[0]
    matches = (f.get("payload") or {}).get("matches", {})
    qtext_hits = matches.get("question_text", [])
    assert not any("celebrated" in h.lower() for h in qtext_hits), (
        f"bare 'celebrated' (past-tense verb) should not be flagged; got hits {qtext_hits}"
    )


def test_a1_still_flags_celebrated_for_marketing_usage():
    """`celebrated for` remains in the regex — it's the marketing usage we
    want to keep catching ('celebrated for its terroir', etc.)."""
    from src.qa.agents.team_a_static import run_a1_lexical_hygiene

    q = _mk_for_regex(
        "Which Italian region is celebrated for its limestone-rich terroir?"
    )
    findings = run_a1_lexical_hygiene(RUN_ID, [q])
    f = findings[0]
    matches = (f.get("payload") or {}).get("matches", {})
    qtext_hits = matches.get("question_text", [])
    assert any("celebrated for" in h.lower() for h in qtext_hits), (
        f"'celebrated for' (marketing) should still be flagged; got hits {qtext_hits}"
    )


def test_a1_does_not_flag_notable_for_factual_statement():
    """v2.3.1: 'notable for' followed by a factual construction ('being the
    country's first...') must not match. Mirrors v7 fail #7 (ddf60bd8...)."""
    from src.qa.agents.team_a_static import run_a1_lexical_hygiene

    q = _mk_for_regex(
        "Which Italian wine brand was notable for being the country's first "
        "to be packaged in Tetra Pak?"
    )
    findings = run_a1_lexical_hygiene(RUN_ID, [q])
    f = findings[0]
    matches = (f.get("payload") or {}).get("matches", {})
    qtext_hits = matches.get("question_text", [])
    assert not any("notable for" in h.lower() for h in qtext_hits), (
        f"factual 'notable for being...' must not flag; got hits {qtext_hits}"
    )


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


def test_a3_skips_true_false():
    """v1.2.0 — A3 must skip true_false entirely. The LCS-with-correct-option
    metric is structurally unsuited because T/F's 1-token correct option does
    not dilute the denominator, so any well-paraphrased T/F over a short
    source fact over-flags as verbatim copy. With v1.2.0, T/F yields a PASS
    finding with a 'skipped: true_false' note in payload."""
    from src.qa.agents.team_a_static import (
        A3_VERSION,
        _A3_RUBRIC_MEASURED,
        run_a3_fact_echo,
    )

    findings = run_a3_fact_echo(RUN_ID, [TRUE_FALSE_HIGH_OVERLAP_QUESTION])
    assert len(findings) == 1
    f = findings[0]
    assert f["severity"] == "pass"
    assert f["score"] == 0.0
    assert f["agent_version"] == A3_VERSION
    assert "skipped: true_false" in f["payload"]["note"]
    assert f["payload"]["rubric_measured"] == _A3_RUBRIC_MEASURED
    # And critically, the LCS / n-gram details from the regular path must
    # NOT be present — we never measured them.
    assert "lcs_ratio" not in f["payload"]
    assert "longest_ngram" not in f["payload"]


def test_a3_passes_at_lcs_0_64():
    """v1.2.0 — borderline-LCS questions (LCS in 0.62-0.64 with low n-gram)
    must NOT FAIL. Under v1.1.0 (`_A3_FAIL_LCS = 0.60`) this would have
    failed; under v1.2.0 (`_A3_FAIL_LCS = 0.65`) it should be PASS or WARN.
    The n-gram path still catches genuine extended verbatim spans, so
    raising the LCS threshold does not lose sensitivity."""
    from src.qa.agents.team_a_static import run_a3_fact_echo

    findings = run_a3_fact_echo(RUN_ID, [A3_BORDERLINE_LCS_QUESTION])
    assert len(findings) == 1
    f = findings[0]
    # Sanity: confirm we're actually in the borderline regime the test
    # is designed to exercise.
    assert 0.60 <= f["payload"]["lcs_ratio"] < 0.65
    assert f["payload"]["longest_ngram"] < 6  # below WARN n-gram threshold
    assert f["severity"] in {"pass", "warn"}
    assert f["severity"] != "fail"


def test_a3_fails_at_lcs_0_66():
    """v1.2.0 — questions at or above the new LCS fail threshold (0.65)
    must still FAIL on the LCS path even when the longest contiguous
    n-gram is short (≤ 6). Confirms the threshold bump didn't accidentally
    disable LCS-based detection."""
    from src.qa.agents.team_a_static import run_a3_fact_echo

    findings = run_a3_fact_echo(RUN_ID, [A3_HIGH_LCS_QUESTION])
    assert len(findings) == 1
    f = findings[0]
    assert f["payload"]["lcs_ratio"] >= 0.65
    assert f["severity"] == "fail"


def test_a3_fails_on_long_ngram_below_lcs_threshold():
    """v1.2.0 — the n-gram path must remain the primary detector for
    genuine extended verbatim spans. A 12-token contiguous match with
    LCS < 0.65 (because the question pads the LCS denominator) must
    still FAIL. Mirrors the WB-VIT-0300 v6 case (12-token verbatim
    copy by Llama, correctly caught by `_A3_FAIL_NGRAM = 8`)."""
    from src.qa.agents.team_a_static import run_a3_fact_echo

    findings = run_a3_fact_echo(RUN_ID, [A3_LONG_NGRAM_QUESTION])
    assert len(findings) == 1
    f = findings[0]
    assert f["payload"]["lcs_ratio"] < 0.65
    assert f["payload"]["longest_ngram"] >= 8
    assert f["severity"] == "fail"


# ─── A4 ─────────────────────────────────────────────────────────────────────


def test_a4_trains_and_scores():
    from src.qa.agents.team_a_static import run_a4_template_fingerprint

    corpus = TEMPLATE_QUESTIONS + LLM_FREEFORM_QUESTIONS
    findings = run_a4_template_fingerprint(RUN_ID, corpus)
    pop = next(f for f in findings if f["question_id"] is None)
    # Either a trained classifier or a data-too-small pass
    assert "test_auc" in pop["payload"] or "note" in pop["payload"]
