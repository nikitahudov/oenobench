"""Phase 2g.18 lever L5 — verifier-skip plumbing tests.

These tests cover the wiring added in Phase 2g.18 that lets the existing
B5 lever (``should_skip_verifier`` in ``src/generators/_verify.py``)
actually fire on the four LLM strategies:

1. ``verify_question_with_independent_solver`` short-circuits when
   OENOBENCH_VERIFIER_SKIP=1 and gate_passed=True + confidence>=0.9 —
   the same B5 path that ``verify_template_answer_with_gemini`` already
   uses.
2. ``parse_llm_response`` accepts ``pre_gate_passed`` +
   ``generator_confidence`` kwargs and forwards them into the verifier.
3. ``pre_screen_for_verifier_skip`` returns a usable verdict from a
   raw LLM JSON response.

The B5 predicate itself (``should_skip_verifier``) is already covered
by ``test_verifier_skip_and_flash.py``; this file focuses on the
plumbing that lets the predicate fire on the LLM-strategy hot path.
"""

from __future__ import annotations

import inspect
from unittest.mock import patch

import pytest

from src.generators import _schemas, _verify
from src.generators._llm_client import LLMResponse
from src.generators._schemas import parse_llm_response, pre_screen_for_verifier_skip
from src.generators._verify import (
    should_skip_verifier,
    verify_question_with_independent_solver,
)


# ─── Test fixtures ────────────────────────────────────────────────────────────

_OPTIONS = [
    {"id": "A", "text": "Nebbiolo"},
    {"id": "B", "text": "Sangiovese"},
    {"id": "C", "text": "Barbera"},
    {"id": "D", "text": "Dolcetto"},
]


def _make_llm_response(parsed: dict | None, *, success: bool = True,
                      content: str | None = None,
                      error: str | None = None) -> LLMResponse:
    """Build a minimal LLMResponse for mocking."""
    if content is None:
        import orjson
        content = orjson.dumps(parsed or {}).decode()
    return LLMResponse(
        content=content,
        parsed=parsed,
        model="mocked",
        input_tokens=120,
        output_tokens=15,
        latency_ms=400,
        success=success,
        error=error if error else (None if success else "mocked failure"),
    )


# ─── B5 predicate (re-baseline of plan's three core cases) ────────────────────


def test_b5_predicate_gate_passed_high_conf_true():
    assert should_skip_verifier(
        gate_passed=True, generator_confidence=0.95,
    ) is True


def test_b5_predicate_gate_failed_high_conf_false():
    assert should_skip_verifier(
        gate_passed=False, generator_confidence=0.95,
    ) is False


def test_b5_predicate_gate_passed_low_conf_false():
    assert should_skip_verifier(
        gate_passed=True, generator_confidence=0.7,
    ) is False


# ─── verify_question_with_independent_solver: B5 short-circuit ────────────────


def test_independent_verifier_skips_when_env_on_and_signals_align(monkeypatch):
    """OENOBENCH_VERIFIER_SKIP=1 + gate_passed=True + conf=0.95 →
    no LLM call, returns synthetic AGREE."""
    monkeypatch.setenv("OENOBENCH_VERIFIER_SKIP", "1")
    monkeypatch.delenv("OENOBENCH_LLM_CACHE", raising=False)

    # If anything tries to dial the LLM, fail loudly.
    def fake_get_client():
        raise AssertionError(
            "verify_question_with_independent_solver called the LLM; B5 skip should fire."
        )

    monkeypatch.setattr("src.generators._verify.get_client", fake_get_client)

    is_valid, debug = verify_question_with_independent_solver(
        question_text="Which red grape variety is required for Barolo DOCG?",
        options=_OPTIONS,
        correct_answer="A",
        source_facts=["Barolo DOCG must contain 100% Nebbiolo."],
        generator="llama",  # in GENERATORS_REQUIRING_VERIFICATION
        gate_passed=True,
        generator_confidence=0.95,
    )
    assert is_valid is True
    assert debug.get("skipped") is True
    assert debug.get("reason") == "gate_passed_and_high_confidence"
    # cost_usd is not present on the synthetic agreement payload, but the
    # important property is that no LLM call was made (asserted above).


def test_independent_verifier_does_not_skip_when_env_off(monkeypatch):
    """Default env (skip OFF) + signals aligned → verifier IS called."""
    monkeypatch.delenv("OENOBENCH_VERIFIER_SKIP", raising=False)
    monkeypatch.delenv("OENOBENCH_LLM_CACHE", raising=False)

    counter = {"calls": 0}

    def fake_generate(self, **kwargs):
        counter["calls"] += 1
        return _make_llm_response({"chosen": "A", "confidence": 0.9})

    monkeypatch.setattr(
        "src.generators._llm_client.LLMClient.generate",
        fake_generate,
    )

    is_valid, debug = verify_question_with_independent_solver(
        question_text="Q?",
        options=_OPTIONS,
        correct_answer="A",
        source_facts=["Some fact."],
        generator="llama",
        gate_passed=True,
        generator_confidence=0.95,
    )
    assert counter["calls"] == 1, "Verifier should run when skip is disabled"
    assert is_valid is True
    # Crucially, NOT skipped via the B5 path.
    assert debug.get("skipped") is not True


def test_independent_verifier_does_not_skip_when_gate_failed(monkeypatch):
    """Env on but gate_passed=False → verifier IS called (skip predicate False)."""
    monkeypatch.setenv("OENOBENCH_VERIFIER_SKIP", "1")
    monkeypatch.delenv("OENOBENCH_LLM_CACHE", raising=False)

    counter = {"calls": 0}

    def fake_generate(self, **kwargs):
        counter["calls"] += 1
        return _make_llm_response({"chosen": "A", "confidence": 0.9})

    monkeypatch.setattr(
        "src.generators._llm_client.LLMClient.generate",
        fake_generate,
    )

    is_valid, debug = verify_question_with_independent_solver(
        question_text="Q?",
        options=_OPTIONS,
        correct_answer="A",
        source_facts=["Some fact."],
        generator="qwen",
        gate_passed=False,            # blocks the skip
        generator_confidence=0.95,
    )
    assert counter["calls"] == 1, "Skip must NOT fire when gate did not pass"
    assert is_valid is True
    assert debug.get("skipped") is not True


# ─── parse_llm_response: signature + verifier kwarg forwarding ────────────────


def test_parse_llm_response_accepts_new_kwargs():
    """Phase 2g.18: pre_gate_passed + generator_confidence are documented kwargs."""
    sig = inspect.signature(parse_llm_response)
    assert "pre_gate_passed" in sig.parameters
    assert "generator_confidence" in sig.parameters
    # Default values preserve backwards compatibility.
    assert sig.parameters["pre_gate_passed"].default is False
    assert sig.parameters["generator_confidence"].default is None


def test_parse_llm_response_forwards_kwargs_into_verifier(monkeypatch):
    """parse_llm_response must thread pre_gate_passed and generator_confidence
    into verify_question_with_independent_solver when verification is on."""
    captured: dict = {}

    def fake_verify(**kwargs):
        captured.update(kwargs)
        return True, {"skipped": False, "verifier_model": "mocked"}

    monkeypatch.setattr(
        "src.generators._verify.verify_question_with_independent_solver",
        fake_verify,
    )

    # A minimal valid 4-option MC payload.
    raw = (
        '{"question_text": "Which red grape variety is required for Barolo DOCG?",'
        ' "options": ['
        ' {"id": "A", "text": "Nebbiolo"},'
        ' {"id": "B", "text": "Sangiovese"},'
        ' {"id": "C", "text": "Barbera"},'
        ' {"id": "D", "text": "Dolcetto"}'
        ' ],'
        ' "correct_answer": "A",'
        ' "explanation": "Barolo DOCG requires 100% Nebbiolo grapes.",'
        ' "tags": []'
        '}'
    )

    out = parse_llm_response(
        raw,
        "multiple_choice",
        source_fact_texts=["Barolo DOCG requires 100% Nebbiolo."],
        verify_with_independent_solver=True,
        generator="llama",
        pre_gate_passed=True,
        generator_confidence=0.95,
    )
    assert out is not None  # parse + verify both succeed
    # The verifier must have received both new kwargs verbatim.
    assert captured.get("gate_passed") is True
    assert captured.get("generator_confidence") == 0.95


def test_parse_llm_response_default_kwargs_are_safe(monkeypatch):
    """Backwards-compat: omitting the new kwargs sends defaults
    (gate_passed=False, generator_confidence=None) into the verifier."""
    captured: dict = {}

    def fake_verify(**kwargs):
        captured.update(kwargs)
        return True, {"skipped": False}

    monkeypatch.setattr(
        "src.generators._verify.verify_question_with_independent_solver",
        fake_verify,
    )

    raw = (
        '{"question_text": "Which red grape variety is required for Barolo DOCG?",'
        ' "options": ['
        ' {"id": "A", "text": "Nebbiolo"},'
        ' {"id": "B", "text": "Sangiovese"},'
        ' {"id": "C", "text": "Barbera"},'
        ' {"id": "D", "text": "Dolcetto"}'
        ' ],'
        ' "correct_answer": "A",'
        ' "explanation": "Barolo DOCG requires 100% Nebbiolo grapes.",'
        ' "tags": []'
        '}'
    )

    out = parse_llm_response(
        raw,
        "multiple_choice",
        source_fact_texts=["Barolo DOCG requires 100% Nebbiolo."],
        verify_with_independent_solver=True,
        generator="qwen",
    )
    assert out is not None
    # No skip plumbing → defaults forwarded.
    assert captured.get("gate_passed") is False
    assert captured.get("generator_confidence") is None


# ─── pre_screen_for_verifier_skip: helper used by the strategy callers ────────


def test_pre_screen_returns_false_none_for_unparseable():
    """Helper must not raise on garbage input — returns the conservative
    fallback that disables the skip."""
    pre_passed, conf = pre_screen_for_verifier_skip(
        "not json {oops",
        question_type="multiple_choice",
        labelled_difficulty="2",
    )
    assert pre_passed is False
    assert conf is None


def test_pre_screen_returns_false_for_missing_fields():
    """Helper handles empty JSON dicts gracefully."""
    pre_passed, conf = pre_screen_for_verifier_skip(
        "{}",
        question_type="multiple_choice",
        labelled_difficulty="2",
    )
    assert pre_passed is False
    assert conf is None


def test_pre_screen_extracts_confidence_when_present(monkeypatch):
    """When the gate is monkeypatched and confidence is in the JSON,
    the helper returns (gate_passed, confidence) as parsed."""
    # Mock screen_question so we don't hit OpenRouter.
    from src.generators import _closed_book_gate

    class _FakeGate:
        passed = True
        applied = True

    def fake_screen(**kwargs):
        return _FakeGate()

    monkeypatch.setattr(_closed_book_gate, "screen_question", fake_screen)

    raw = (
        '{"question_text": "Stem?",'
        ' "options": ['
        ' {"id": "A", "text": "x"},'
        ' {"id": "B", "text": "y"},'
        ' {"id": "C", "text": "z"},'
        ' {"id": "D", "text": "w"}'
        ' ],'
        ' "correct_answer": "A",'
        ' "confidence": 0.91'
        '}'
    )
    pre_passed, conf = pre_screen_for_verifier_skip(
        raw,
        question_type="multiple_choice",
        labelled_difficulty="2",
    )
    assert pre_passed is True
    assert conf == 0.91


def test_pre_screen_returns_false_when_gate_rejects(monkeypatch):
    """Gate-rejected → pre_passed=False even with high confidence."""
    from src.generators import _closed_book_gate

    class _FakeGate:
        passed = False
        applied = True

    monkeypatch.setattr(
        _closed_book_gate, "screen_question", lambda **kw: _FakeGate(),
    )

    raw = (
        '{"question_text": "Stem?",'
        ' "options": ['
        ' {"id": "A", "text": "x"},'
        ' {"id": "B", "text": "y"},'
        ' {"id": "C", "text": "z"},'
        ' {"id": "D", "text": "w"}'
        ' ],'
        ' "correct_answer": "A",'
        ' "confidence": 0.95'
        '}'
    )
    pre_passed, conf = pre_screen_for_verifier_skip(
        raw,
        question_type="multiple_choice",
        labelled_difficulty="2",
    )
    assert pre_passed is False
    assert conf == 0.95
