"""Tests for lever B5 (skip verifier when gate + generator agree).

Lever C2 (Flash variant for paraphrase + verifier) tests are added in
the C2 commit and live in this same file.

B5 short-circuit:
    - Helper `should_skip_verifier(...)` is a pure predicate of (gate_passed,
      generator_confidence). The OENOBENCH_VERIFIER_SKIP env var gates
      whether the call sites actually consult it.
    - Skip happens BEFORE the B1 cache lookup so confident gate-passed
      questions never even hit the cache (let alone the API).

The tests mock LLMClient.generate / _llm_cache to avoid network + DB.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.generators import _verify
from src.generators._llm_client import LLMResponse


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


# ─── B5 helper: should_skip_verifier ──────────────────────────────────────────


def test_should_skip_verifier_returns_false_when_gate_failed():
    assert _verify.should_skip_verifier(
        gate_passed=False, generator_confidence=0.95,
    ) is False


def test_should_skip_verifier_returns_false_when_confidence_low():
    assert _verify.should_skip_verifier(
        gate_passed=True, generator_confidence=0.5,
    ) is False


def test_should_skip_verifier_returns_false_when_confidence_none():
    assert _verify.should_skip_verifier(
        gate_passed=True, generator_confidence=None,
    ) is False


def test_should_skip_verifier_returns_true_when_both_signals_align():
    assert _verify.should_skip_verifier(
        gate_passed=True, generator_confidence=0.95,
    ) is True


def test_should_skip_verifier_threshold_boundary():
    """conf == 0.9 exactly should trigger skip (>=, not >)."""
    assert _verify.should_skip_verifier(
        gate_passed=True, generator_confidence=0.9,
    ) is True
    # And 0.89 falls just below.
    assert _verify.should_skip_verifier(
        gate_passed=True, generator_confidence=0.89,
    ) is False


# ─── B5 wiring: env-var gating + cache ordering (verify_template) ─────────────


def test_verifier_skip_disabled_by_default(monkeypatch):
    """Env var unset → verifier IS called even when both signals would skip."""
    monkeypatch.delenv("OENOBENCH_VERIFIER_SKIP", raising=False)
    monkeypatch.delenv("OENOBENCH_LLM_CACHE", raising=False)

    fake_response = _make_llm_response({"chosen": "A"})
    counter = {"calls": 0}

    def fake_generate(self, **kwargs):
        counter["calls"] += 1
        return fake_response

    monkeypatch.setattr(
        "src.generators._llm_client.LLMClient.generate",
        fake_generate,
    )

    agrees, debug = _verify.verify_template_answer_with_gemini(
        question_text="Q?",
        options=_OPTIONS,
        correct_answer_id="A",
        source_fact_text="Barolo requires 100% Nebbiolo.",
        gate_passed=True,
        generator_confidence=0.99,
    )
    assert counter["calls"] == 1, "Verifier should run when skip is disabled"
    assert agrees is True
    # Crucially, NOT skipped.
    assert debug.get("skipped") is not True


def test_verifier_skip_enabled_via_env_var(monkeypatch):
    """Env var on + signals aligned → verifier NOT called; skipped verdict returned."""
    monkeypatch.setenv("OENOBENCH_VERIFIER_SKIP", "1")
    monkeypatch.delenv("OENOBENCH_LLM_CACHE", raising=False)

    counter = {"calls": 0}

    def fake_generate(self, **kwargs):
        counter["calls"] += 1
        return _make_llm_response({"chosen": "A"})

    monkeypatch.setattr(
        "src.generators._llm_client.LLMClient.generate",
        fake_generate,
    )

    agrees, debug = _verify.verify_template_answer_with_gemini(
        question_text="Q?",
        options=_OPTIONS,
        correct_answer_id="A",
        source_fact_text="Some fact.",
        gate_passed=True,
        generator_confidence=0.95,
    )
    assert counter["calls"] == 0, "Verifier must NOT be called when skip applies"
    assert agrees is True
    assert debug.get("skipped") is True
    assert debug.get("reason") == "gate_passed_and_high_confidence"


def test_verifier_skip_runs_before_cache_lookup(monkeypatch):
    """Skip wins over cache: cache.lookup is not called when skip applies.

    Reverse: when skip does not apply (gate_passed=False), cache IS consulted.
    """
    monkeypatch.setenv("OENOBENCH_VERIFIER_SKIP", "1")
    monkeypatch.setenv("OENOBENCH_LLM_CACHE", "1")

    cache_lookup_calls = {"n": 0}

    def fake_lookup(**kwargs):
        cache_lookup_calls["n"] += 1
        # Return a sentinel value so we'd see it in debug if cache were
        # actually consulted (but skip should fire first).
        raise AssertionError("cache.lookup must not be called when skip wins")

    def fake_generate(self, **kwargs):
        # If we got here, neither skip nor cache short-circuited correctly.
        return _make_llm_response({"chosen": "A"})

    monkeypatch.setattr("src.generators._verify._llm_cache.lookup", fake_lookup)
    monkeypatch.setattr(
        "src.generators._llm_client.LLMClient.generate",
        fake_generate,
    )

    # Skip applies → cache.lookup must NOT be called.
    agrees, debug = _verify.verify_template_answer_with_gemini(
        question_text="Q?",
        options=_OPTIONS,
        correct_answer_id="A",
        source_fact_text="Fact.",
        gate_passed=True,
        generator_confidence=0.95,
    )
    assert agrees is True
    assert debug.get("skipped") is True
    assert cache_lookup_calls["n"] == 0

    # Reverse: skip does NOT apply (gate_passed=False) → cache IS consulted.
    consulted = {"n": 0}

    def counting_lookup(**kwargs):
        consulted["n"] += 1
        return None

    monkeypatch.setattr("src.generators._verify._llm_cache.lookup", counting_lookup)

    agrees2, _debug2 = _verify.verify_template_answer_with_gemini(
        question_text="Q?",
        options=_OPTIONS,
        correct_answer_id="A",
        source_fact_text="Fact.",
        gate_passed=False,           # skip cannot apply
        generator_confidence=0.95,
    )
    assert consulted["n"] == 1, "Cache must be consulted when skip cannot apply"
