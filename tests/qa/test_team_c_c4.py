"""δ-3: C4 difficulty re-classifier.

A single LLM call per question rates difficulty 1-4. Severity is computed by
comparing against the question's assigned label:
  pass — equal
  warn — differ by 1 level
  fail — differ by ≥ 2 levels
"""

from __future__ import annotations

from src.qa.agents import team_c_probes


def _question(uuid_suffix: str, difficulty: str = "2") -> dict:
    return {
        "uuid": f"00000000-0000-0000-0000-0000000000{uuid_suffix}",
        "domain": "wine_regions",
        "subdomain": "italy_piedmont",
        "difficulty": difficulty,
        "cognitive_dim": "recall",
        "question_type": "multiple_choice",
        "options": [
            {"id": "A", "text": "Nebbiolo"},
            {"id": "B", "text": "Sangiovese"},
            {"id": "C", "text": "Barbera"},
            {"id": "D", "text": "Dolcetto"},
        ],
        "correct_answer": "A",
        "correct_answer_text": "Nebbiolo",
        "question_text": "Which is the obscure grape required for an obscure DOCG?",
    }


def _make_call_llm(rated: int, rationale: str = "stub"):
    """Return a stub `_c4_call_llm` that returns a fixed rated difficulty."""
    def _stub(*, question_text, options, correct_answer, model_short):
        return rated, rationale, {
            "prompt_hash": "deadbeef",
            "llm_calls": 1,
            "cost_usd": 0.0001,
            "error": None,
            "raw": '{"difficulty": ' + str(rated) + '}',
            "judge_model": model_short,
        }
    return _stub


def test_c4_fails_when_rating_off_by_two_levels():
    findings = team_c_probes.run_c4_difficulty_audit(
        run_id="00000000-0000-0000-0000-00000000dead",
        questions=[_question("c1", difficulty="2")],
        call_llm_fn=_make_call_llm(rated=4, rationale="actually expert-level"),
    )
    assert len(findings) == 1
    f = findings[0]
    assert f["severity"] == "fail"
    assert f["payload"]["assigned_difficulty"] == 2
    assert f["payload"]["rated_difficulty"] == 4
    assert f["payload"]["delta"] == 2


def test_c4_warns_when_rating_off_by_one_level():
    findings = team_c_probes.run_c4_difficulty_audit(
        run_id="00000000-0000-0000-0000-00000000dead",
        questions=[_question("c2", difficulty="2")],
        call_llm_fn=_make_call_llm(rated=3),
    )
    f = findings[0]
    assert f["severity"] == "warn"
    assert f["payload"]["delta"] == 1


def test_c4_passes_when_rating_matches():
    findings = team_c_probes.run_c4_difficulty_audit(
        run_id="00000000-0000-0000-0000-00000000dead",
        questions=[_question("c3", difficulty="3")],
        call_llm_fn=_make_call_llm(rated=3),
    )
    f = findings[0]
    assert f["severity"] == "pass"
    assert f["payload"]["delta"] == 0


def test_c4_records_error_when_llm_returns_none():
    def _broken(*, question_text, options, correct_answer, model_short):
        return None, "", {
            "prompt_hash": "broken",
            "llm_calls": 1,
            "cost_usd": 0.0,
            "error": "JSON parse error",
            "raw": "garbage",
            "judge_model": model_short,
        }

    findings = team_c_probes.run_c4_difficulty_audit(
        run_id="00000000-0000-0000-0000-00000000dead",
        questions=[_question("c4", difficulty="3")],
        call_llm_fn=_broken,
    )
    f = findings[0]
    assert f["severity"] == "error"


def test_c4_inline_writes_use_callback_and_return_empty():
    captured = []
    findings = team_c_probes.run_c4_difficulty_audit(
        run_id="00000000-0000-0000-0000-00000000dead",
        questions=[_question("c5", difficulty="2"), _question("c6", difficulty="3")],
        call_llm_fn=_make_call_llm(rated=2),
        write_finding_fn=captured.append,
    )
    assert findings == []
    assert len(captured) == 2
    # First question: 2 vs 2 = pass; second: 3 vs 2 = warn
    sev = sorted(f["severity"] for f in captured)
    assert sev == ["pass", "warn"]


def test_c4_skips_questions_already_recorded():
    seen = []
    captured = []

    def _skip(qid, agent_id):
        return qid.endswith("c7") and agent_id == team_c_probes.C4_ID

    def _stub(*, question_text, options, correct_answer, model_short):
        seen.append(question_text)
        return 2, "ok", {
            "prompt_hash": "abc", "llm_calls": 1, "cost_usd": 0.0,
            "error": None, "raw": "", "judge_model": model_short,
        }

    team_c_probes.run_c4_difficulty_audit(
        run_id="00000000-0000-0000-0000-00000000dead",
        questions=[_question("c7", difficulty="2"), _question("c8", difficulty="2")],
        call_llm_fn=_stub,
        write_finding_fn=captured.append,
        skip_existing_checker=_skip,
    )
    # Only c8 should reach the LLM
    assert len(seen) == 1
    assert len(captured) == 1


def test_c4_difficulty_label_with_l_prefix_is_coerced():
    findings = team_c_probes.run_c4_difficulty_audit(
        run_id="00000000-0000-0000-0000-00000000dead",
        questions=[_question("c9", difficulty="L3")],
        call_llm_fn=_make_call_llm(rated=3),
    )
    assert findings[0]["severity"] == "pass"
    assert findings[0]["payload"]["assigned_difficulty"] == 3
