"""v2.2 fix #5 — generation-time C4 difficulty gate."""

from __future__ import annotations

import os

import pytest

from src.generators import _schemas


@pytest.fixture
def sample_response_json() -> str:
    """Minimal valid LLM response that parse_llm_response accepts."""
    return (
        '{"question_text": "Which grape is authorised in Barolo DOCG?",'
        ' "options": ['
        '  {"id": "A", "text": "Nebbiolo"},'
        '  {"id": "B", "text": "Barbera"},'
        '  {"id": "C", "text": "Dolcetto"},'
        '  {"id": "D", "text": "Sangiovese"}'
        '], "correct_answer": "A",'
        ' "explanation": "Barolo DOCG requires 100% Nebbiolo."}'
    )


def _mock_c4(monkeypatch, predicted: str | None):
    """Patch classify_difficulty so tests don't hit the network."""
    from src.generators import _c4_helper

    def fake_classify(**kwargs):
        return predicted

    monkeypatch.setattr(_c4_helper, "classify_difficulty", fake_classify)


def test_c4_gate_accepts_same_difficulty(monkeypatch, sample_response_json):
    _mock_c4(monkeypatch, predicted="2")
    q = _schemas.parse_llm_response(
        sample_response_json,
        "multiple_choice",
        verify_difficulty_with_c4=True,
        labelled_difficulty="2",
    )
    assert q is not None


def test_c4_gate_accepts_one_level_off(monkeypatch, sample_response_json):
    _mock_c4(monkeypatch, predicted="3")
    q = _schemas.parse_llm_response(
        sample_response_json,
        "multiple_choice",
        verify_difficulty_with_c4=True,
        labelled_difficulty="2",
    )
    assert q is not None, "1-level mismatch must be accepted (delta < 2)"


def test_c4_gate_accepts_two_level_mismatch_on_l1_l2(monkeypatch, sample_response_json):
    """Phase 2g.12: L1/L2 reject threshold was loosened from 2 to 3.

    The C4 classifier consistently over-predicts difficulty for fact-anchored
    detail questions that the template heuristic correctly buckets at L1/L2,
    and the v9 audit-pilot rejected ~91 questions per build at exactly this
    delta=2 boundary. Audit-side D-gates on per-level distribution catch any
    drift downstream.
    """
    _mock_c4(monkeypatch, predicted="4")
    q = _schemas.parse_llm_response(
        sample_response_json,
        "multiple_choice",
        verify_difficulty_with_c4=True,
        labelled_difficulty="2",
    )
    assert q is not None, (
        "L2 labelled with L4 prediction (delta=2) must accept under the "
        "Phase 2g.12 loosened L1/L2 threshold of 3"
    )


def test_c4_gate_rejects_three_level_mismatch_on_l1_l2(monkeypatch, sample_response_json):
    """Three-level miss on L1/L2 still rejects (delta=3 == threshold=3 fires)."""
    _mock_c4(monkeypatch, predicted="4")
    q = _schemas.parse_llm_response(
        sample_response_json,
        "multiple_choice",
        verify_difficulty_with_c4=True,
        labelled_difficulty="1",
    )
    assert q is None, "L1 labelled with L4 prediction (delta=3) must reject"


def test_c4_gate_env_var_disables(monkeypatch, sample_response_json):
    """OENOBENCH_SKIP_C4_GATE=1 bypasses the gate even on a 3-level miss."""
    monkeypatch.setenv("OENOBENCH_SKIP_C4_GATE", "1")
    _mock_c4(monkeypatch, predicted="4")
    q = _schemas.parse_llm_response(
        sample_response_json,
        "multiple_choice",
        verify_difficulty_with_c4=True,
        labelled_difficulty="1",
    )
    assert q is not None, "Env-var should disable the gate"


def test_c4_gate_missing_labelled_difficulty_skips_gracefully(
    monkeypatch, sample_response_json
):
    # If the strategy didn't label a difficulty, the gate should not fire.
    _mock_c4(monkeypatch, predicted="4")  # would reject if gate fired
    q = _schemas.parse_llm_response(
        sample_response_json,
        "multiple_choice",
        verify_difficulty_with_c4=True,
        labelled_difficulty=None,
    )
    assert q is not None


def test_c4_gate_non_numeric_predicted_skips(monkeypatch, sample_response_json):
    """If Gemini returns None (API error / parse failure), don't reject."""
    _mock_c4(monkeypatch, predicted=None)
    q = _schemas.parse_llm_response(
        sample_response_json,
        "multiple_choice",
        verify_difficulty_with_c4=True,
        labelled_difficulty="2",
    )
    assert q is not None, "None predicted → skip gate, don't reject"
