"""Tests for the independent-solver verification gate.

Covers:
- The fast-path skip when the generator is not in {llama, qwen}.
- Disagreement detection: planted wrong-key question is rejected when the
  mocked verifier returns a different option than the keyed answer.
- Unparseable verifier output is treated as rejection (not silent accept).
- The deterministic verifier-rotation hash returns one of {claude, gemini}.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.generators._llm_client import LLMResponse
from src.generators._verify import (
    GENERATORS_REQUIRING_VERIFICATION,
    VERIFIER_POOL,
    _pick_verifier,
    verify_question_with_independent_solver,
)


# ─── Fixture ──────────────────────────────────────────────────────────────────


@pytest.fixture
def planted_wrong_key_question() -> dict:
    """A multiple-choice question whose KEYED answer ('A') is wrong.

    The source fact unambiguously supports option B (Sangiovese is the dominant
    Chianti grape; the question asks which grape Chianti DOCG requires). A
    correctly-functioning verifier should pick B and the gate should reject.
    """
    return {
        "question_text": "Which grape is required to be the dominant variety in Chianti DOCG?",
        "options": [
            {"id": "A", "text": "Nebbiolo"},      # planted as "correct" — actually wrong
            {"id": "B", "text": "Sangiovese"},    # the real answer per the source fact
            {"id": "C", "text": "Barbera"},
            {"id": "D", "text": "Dolcetto"},
        ],
        "correct_answer": "A",
        "source_facts": [
            "Chianti DOCG must contain a minimum of 70% Sangiovese, the dominant grape variety in the appellation.",
        ],
    }


# ─── Fast-path: no-verify generators ──────────────────────────────────────────


def test_no_verify_path_for_claude():
    """Generator 'claude' should be accepted without any LLM call."""
    with patch("src.generators._verify.get_client") as mock_get_client:
        is_valid, debug = verify_question_with_independent_solver(
            question_text="What is the dominant grape of Chianti?",
            options=[
                {"id": "A", "text": "Sangiovese"},
                {"id": "B", "text": "Nebbiolo"},
            ],
            correct_answer="A",
            source_facts=["Chianti requires at least 70% Sangiovese."],
            generator="claude",
        )
    assert is_valid is True
    assert debug["skipped"] is True
    assert debug["verifier_model"] is None
    # Critically, no LLM call should have been issued.
    mock_get_client.assert_not_called()


def test_no_verify_path_for_chatgpt_and_gemini():
    """ChatGPT and Gemini are also in the no-verify (fast) set."""
    with patch("src.generators._verify.get_client") as mock_get_client:
        for gen in ("chatgpt", "gemini"):
            is_valid, debug = verify_question_with_independent_solver(
                question_text="Q?",
                options=[{"id": "A", "text": "x"}, {"id": "B", "text": "y"}],
                correct_answer="A",
                source_facts=["A fact"],
                generator=gen,
            )
            assert is_valid is True
            assert debug["skipped"] is True
        mock_get_client.assert_not_called()


def test_generators_requiring_verification_set():
    """Only Llama and Qwen should be in the verification set."""
    assert GENERATORS_REQUIRING_VERIFICATION == {"llama", "qwen"}


# ─── Verifier rotation determinism ────────────────────────────────────────────


def test_pick_verifier_returns_pool_member():
    for q in ("a", "b", "longer question text", "Which grape is Nebbiolo?"):
        assert _pick_verifier(q) in VERIFIER_POOL


def test_pick_verifier_is_deterministic():
    """Same question text → same verifier (reproducibility requirement)."""
    q = "Which DOCG appellation in Tuscany requires at least 70% Sangiovese?"
    chosen_first = _pick_verifier(q)
    for _ in range(10):
        assert _pick_verifier(q) == chosen_first


# ─── Disagreement detection ───────────────────────────────────────────────────


def _make_llm_response(parsed: dict, *, success: bool = True, content: str | None = None) -> LLMResponse:
    """Build a minimal LLMResponse for mocking."""
    if content is None:
        import orjson
        content = orjson.dumps(parsed).decode()
    return LLMResponse(
        content=content,
        parsed=parsed,
        model="anthropic/claude-opus-4.7",
        input_tokens=120,
        output_tokens=15,
        latency_ms=850,
        success=success,
        error=None if success else "mocked failure",
    )


def test_verifier_rejects_wrong_key(planted_wrong_key_question):
    """Llama generator + mocked verifier picking 'B' must reject (key was 'A')."""
    fake_response = _make_llm_response({"chosen": "B", "confidence": 0.95})

    with patch("src.generators._verify.get_client") as mock_get_client:
        mock_get_client.return_value.generate.return_value = fake_response

        is_valid, debug = verify_question_with_independent_solver(
            question_text=planted_wrong_key_question["question_text"],
            options=planted_wrong_key_question["options"],
            correct_answer=planted_wrong_key_question["correct_answer"],
            source_facts=planted_wrong_key_question["source_facts"],
            generator="llama",
        )

    assert is_valid is False
    assert debug["chosen"] == "B"
    assert debug["confidence"] == pytest.approx(0.95)
    assert debug["verifier_model"] in VERIFIER_POOL
    assert debug["cost_usd"] > 0  # cost ledger populated
    mock_get_client.return_value.generate.assert_called_once()


def test_verifier_accepts_when_chosen_matches_key():
    """Mocked verifier agreeing with the key returns is_valid=True."""
    fake_response = _make_llm_response({"chosen": "A", "confidence": 0.9})

    with patch("src.generators._verify.get_client") as mock_get_client:
        mock_get_client.return_value.generate.return_value = fake_response

        is_valid, debug = verify_question_with_independent_solver(
            question_text="Which grape is dominant in Chianti?",
            options=[
                {"id": "A", "text": "Sangiovese"},
                {"id": "B", "text": "Nebbiolo"},
                {"id": "C", "text": "Barbera"},
                {"id": "D", "text": "Cabernet Sauvignon"},
            ],
            correct_answer="A",
            source_facts=["Chianti is dominated by Sangiovese."],
            generator="qwen",
        )

    assert is_valid is True
    assert debug["chosen"] == "A"


def test_verifier_failed_call_treated_as_rejection():
    """A non-success LLMResponse (API error) must reject — never silently accept."""
    failed_response = _make_llm_response(
        parsed={}, success=False, content="",
    )

    with patch("src.generators._verify.get_client") as mock_get_client:
        mock_get_client.return_value.generate.return_value = failed_response

        is_valid, debug = verify_question_with_independent_solver(
            question_text="Q?",
            options=[{"id": "A", "text": "x"}, {"id": "B", "text": "y"}],
            correct_answer="A",
            source_facts=["A fact."],
            generator="llama",
        )

    assert is_valid is False
    assert debug["error"] == "mocked failure"


def test_verifier_unparseable_response_rejects():
    """When the verifier emits no 'chosen' field, treat as rejection."""
    fake_response = _make_llm_response({"foo": "bar"})

    with patch("src.generators._verify.get_client") as mock_get_client:
        mock_get_client.return_value.generate.return_value = fake_response

        is_valid, debug = verify_question_with_independent_solver(
            question_text="Q?",
            options=[{"id": "A", "text": "x"}, {"id": "B", "text": "y"}],
            correct_answer="A",
            source_facts=["A fact."],
            generator="qwen",
        )

    assert is_valid is False
    assert debug["chosen"] is None


def test_verifier_skips_when_no_options():
    """Open-ended (no-options) questions cannot be verified — accept by default."""
    with patch("src.generators._verify.get_client") as mock_get_client:
        is_valid, debug = verify_question_with_independent_solver(
            question_text="Name the dominant grape of Chianti.",
            options=[],
            correct_answer="Sangiovese",
            source_facts=["Chianti is dominated by Sangiovese."],
            generator="llama",
        )
    assert is_valid is True
    assert debug["skipped"] is True
    mock_get_client.assert_not_called()
