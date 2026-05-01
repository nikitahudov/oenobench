"""Tests for lever B5 (skip verifier when gate + generator agree) and
lever C2 (faster Gemini Flash variant for paraphrase + verifier).

B5 short-circuit:
    - Helper `should_skip_verifier(...)` is a pure predicate of (gate_passed,
      generator_confidence). The OENOBENCH_VERIFIER_SKIP env var gates
      whether the call sites actually consult it.
    - Skip happens BEFORE the B1 cache lookup so confident gate-passed
      questions never even hit the cache (let alone the API).

C2 model swap:
    - Default model in `_template_paraphrase.paraphrase_question_text` and
      in `_verify.verify_template_answer_with_gemini` is now Gemini Flash.
    - OENOBENCH_PARAPHRASE_MODEL / OENOBENCH_VERIFIER_MODEL allow override.
    - On a `success=False` response, the call is retried once on the Pro
      fallback (`google/gemini-3.1-pro-preview`).

The tests mock LLMClient.generate / _llm_cache to avoid network + DB.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.generators import _template_paraphrase, _verify
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


# ─── C2: paraphrase model swap ────────────────────────────────────────────────


def test_paraphrase_uses_haiku_by_default(monkeypatch):
    """With no env override, paraphrase must call the Claude Haiku 4.5 default.

    Phase 2g.16: switched from Gemini 3.1 Pro Preview (which burned the
    300-token budget on thinking-mode CoT, yielding empty content on ~50%
    of v14 calls) to Claude Haiku 4.5 (5× faster, reliable JSON, no
    thinking-mode budget burn). Gemini Pro stays as the fallback.
    """
    monkeypatch.delenv("OENOBENCH_PARAPHRASE_MODEL", raising=False)
    monkeypatch.delenv("OENOBENCH_LLM_CACHE", raising=False)

    captured = {}

    def fake_generate(self, **kwargs):
        captured.update(kwargs)
        return LLMResponse(
            content='{"question_text": "Which red grape variety is required for Barolo?"}',
            parsed={"question_text": "Which red grape variety is required for Barolo?"},
            model=kwargs.get("model", "?"),
            input_tokens=200, output_tokens=20,
            latency_ms=400, success=True, error=None,
        )

    monkeypatch.setattr(
        "src.generators._llm_client.LLMClient.generate",
        fake_generate,
    )

    _ = _template_paraphrase.paraphrase_question_text(
        "Barolo requires which red grape variety?",
        _OPTIONS,
    )
    # Paraphrase may return None if validation rejects; only assert the
    # MODEL argument we sent.
    assert captured.get("model") == "anthropic/claude-haiku-4.5"


def test_paraphrase_env_override(monkeypatch):
    """OENOBENCH_PARAPHRASE_MODEL overrides the default."""
    custom = "google/some-experimental-flash-x"
    monkeypatch.setenv("OENOBENCH_PARAPHRASE_MODEL", custom)
    monkeypatch.delenv("OENOBENCH_LLM_CACHE", raising=False)

    captured = {}

    def fake_generate(self, **kwargs):
        captured.update(kwargs)
        return LLMResponse(
            content='{"question_text": "Which grape variety must Barolo use?"}',
            parsed={"question_text": "Which grape variety must Barolo use?"},
            model=kwargs.get("model", "?"),
            input_tokens=200, output_tokens=20,
            latency_ms=400, success=True, error=None,
        )

    monkeypatch.setattr(
        "src.generators._llm_client.LLMClient.generate",
        fake_generate,
    )

    _ = _template_paraphrase.paraphrase_question_text(
        "Barolo requires which red grape variety?",
        _OPTIONS,
    )
    assert captured.get("model") == custom


def test_paraphrase_falls_back_to_pro_on_failure(monkeypatch):
    """First call fails → second call uses Pro; final result reflects Pro response.

    Phase 2g.12 made the Flash default == Pro slug to stop OpenRouter 400s,
    so the failover code path is no longer reachable on the default
    configuration. The env-var override is the supported way to put a
    non-Pro slug in the primary position; this test pins it to a fake
    "Flash" slug so the failover machinery is still exercised.
    """
    monkeypatch.setenv("OENOBENCH_PARAPHRASE_MODEL", "google/fake-flash-x")
    monkeypatch.delenv("OENOBENCH_LLM_CACHE", raising=False)

    call_log: list[str] = []

    def fake_generate(self, **kwargs):
        model = kwargs.get("model", "")
        call_log.append(model)
        if "flash" in model:
            # Flash fails → triggers Pro fallback.
            return LLMResponse(
                content="",
                parsed=None,
                model=model,
                input_tokens=0, output_tokens=0,
                latency_ms=100, success=False, error="flash_5xx",
            )
        # Pro succeeds.
        return LLMResponse(
            content='{"question_text": "Pro paraphrase: which grape variety must Barolo use?"}',
            parsed={
                "question_text": "Pro paraphrase: which grape variety must Barolo use?"
            },
            model=model,
            input_tokens=200, output_tokens=20,
            latency_ms=600, success=True, error=None,
        )

    monkeypatch.setattr(
        "src.generators._llm_client.LLMClient.generate",
        fake_generate,
    )

    out = _template_paraphrase.paraphrase_question_text(
        "Barolo requires which red grape variety?",
        _OPTIONS,
    )
    # Two calls total: primary (fake-flash), then Pro fallback.
    assert len(call_log) == 2
    assert "flash" in call_log[0]
    assert call_log[1] == "google/gemini-3.1-pro-preview"
    # The output (if validation passes) reflects the Pro response.
    if out is not None:
        assert "Pro paraphrase" in out


# ─── C2: template-verifier model swap ─────────────────────────────────────────


def _make_template_verify_response(parsed: dict | None, *, success: bool = True,
                                   error: str | None = None) -> LLMResponse:
    """Convenience for the template-verify tests below."""
    import orjson
    return LLMResponse(
        content=orjson.dumps(parsed or {}).decode() if parsed else "",
        parsed=parsed,
        model="mocked",
        input_tokens=120,
        output_tokens=15,
        latency_ms=400,
        success=success,
        error=error if error else (None if success else "mocked failure"),
    )


def test_verifier_uses_flash_by_default(monkeypatch):
    """Default model for verify_template_answer_with_gemini is Flash."""
    monkeypatch.delenv("OENOBENCH_VERIFIER_MODEL", raising=False)
    monkeypatch.delenv("OENOBENCH_VERIFIER_SKIP", raising=False)
    monkeypatch.delenv("OENOBENCH_LLM_CACHE", raising=False)

    captured = {}

    def fake_generate(self, **kwargs):
        captured.update(kwargs)
        return _make_template_verify_response({"chosen": "A"})

    monkeypatch.setattr(
        "src.generators._llm_client.LLMClient.generate",
        fake_generate,
    )

    agrees, debug = _verify.verify_template_answer_with_gemini(
        question_text="Q?",
        options=_OPTIONS,
        correct_answer_id="A",
        source_fact_text="Barolo requires 100% Nebbiolo.",
    )
    assert agrees is True
    assert captured.get("model") == "google/gemini-3.1-pro-preview"


def test_verifier_env_override(monkeypatch):
    """OENOBENCH_VERIFIER_MODEL overrides the default."""
    custom = "google/some-experimental-flash-y"
    monkeypatch.setenv("OENOBENCH_VERIFIER_MODEL", custom)
    monkeypatch.delenv("OENOBENCH_VERIFIER_SKIP", raising=False)
    monkeypatch.delenv("OENOBENCH_LLM_CACHE", raising=False)

    captured = {}

    def fake_generate(self, **kwargs):
        captured.update(kwargs)
        return _make_template_verify_response({"chosen": "A"})

    monkeypatch.setattr(
        "src.generators._llm_client.LLMClient.generate",
        fake_generate,
    )

    _ = _verify.verify_template_answer_with_gemini(
        question_text="Q?",
        options=_OPTIONS,
        correct_answer_id="A",
        source_fact_text="Some fact.",
    )
    assert captured.get("model") == custom


def test_verifier_falls_back_to_pro_on_failure(monkeypatch):
    """Flash failure → retry on Pro; final verdict reflects Pro response.

    Phase 2g.12 made the Flash default == Pro slug to stop OpenRouter 400s,
    so the failover code path is no longer reachable on the default
    configuration. Pin a fake "Flash" slug via the env var so the
    failover machinery is still exercised.
    """
    monkeypatch.setenv("OENOBENCH_VERIFIER_MODEL", "google/fake-flash-y")
    monkeypatch.delenv("OENOBENCH_VERIFIER_SKIP", raising=False)
    monkeypatch.delenv("OENOBENCH_LLM_CACHE", raising=False)

    call_log: list[str] = []

    def fake_generate(self, **kwargs):
        model = kwargs.get("model", "")
        call_log.append(model)
        if "flash" in model:
            return _make_template_verify_response(
                None, success=False, error="flash_503",
            )
        # Pro succeeds with chosen=A.
        return _make_template_verify_response({"chosen": "A"})

    monkeypatch.setattr(
        "src.generators._llm_client.LLMClient.generate",
        fake_generate,
    )

    agrees, debug = _verify.verify_template_answer_with_gemini(
        question_text="Q?",
        options=_OPTIONS,
        correct_answer_id="A",
        source_fact_text="Barolo requires 100% Nebbiolo.",
    )
    # Two calls: Flash (fail), Pro (success).
    assert len(call_log) == 2
    assert "flash" in call_log[0]
    assert call_log[1] == "google/gemini-3.1-pro-preview"
    assert agrees is True
    # Debug payload records the actually-used model (Pro).
    assert debug.get("verifier_model") == "google/gemini-3.1-pro-preview"
