"""Phase 2g.18 cost-down — judge model override + panel slim tests.

Covers:
- ``JUDGE_MODEL_OVERRIDES`` and ``_resolve_judge_model`` route the "claude"
  judge slot through Sonnet 4.6 in the B1/B2 panels only.
- Other shorts (gemini/chatgpt/llama/qwen) fall back to GENERATOR_MODELS.
- ``self_pref_answer`` (D1 SelfPreference evaluator) bypasses the override
  and stays on the GENERATOR_MODELS Opus 4.7 slug to keep self-pref
  calibration history comparable across audit cycles.
- ``JUDGE_PANEL_B2`` is the 4-tuple expected by Phase 2g.18.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from src.generators._llm_client import GENERATOR_MODELS
from src.qa import _judges


# ─── Resolver tests ──────────────────────────────────────────────────────────


def test_resolve_judge_model_claude_routes_to_sonnet():
    """Claude judge slot → Sonnet 4.6 (Phase 2g.18 cost-down)."""
    assert _judges._resolve_judge_model("claude") == "anthropic/claude-sonnet-4.6"


def test_resolve_judge_model_gemini_falls_back_to_generator_models():
    """Gemini and other unmapped shorts use GENERATOR_MODELS."""
    assert _judges._resolve_judge_model("gemini") == GENERATOR_MODELS["gemini"]


def test_resolve_judge_model_chatgpt_falls_back_to_generator_models():
    assert _judges._resolve_judge_model("chatgpt") == GENERATOR_MODELS["chatgpt"]


def test_resolve_judge_model_llama_falls_back():
    assert _judges._resolve_judge_model("llama") == GENERATOR_MODELS["llama"]


def test_resolve_judge_model_qwen_falls_back():
    assert _judges._resolve_judge_model("qwen") == GENERATOR_MODELS["qwen"]


def test_resolve_judge_model_passthrough_unknown_short():
    """Unknown short-names return verbatim (lets callers pass full slugs)."""
    assert _judges._resolve_judge_model("anthropic/claude-haiku-4.5") == (
        "anthropic/claude-haiku-4.5"
    )


def test_judge_model_overrides_only_contains_claude():
    """Phase 2g.18 only routes claude. Adding more shorts requires audit
    review (per JUDGE_MODEL_OVERRIDES docstring)."""
    assert _judges.JUDGE_MODEL_OVERRIDES == {
        "claude": "anthropic/claude-sonnet-4.6",
    }


# ─── Panel slim guardrail ────────────────────────────────────────────────────


def test_judge_panel_b2_is_four_tuple_no_chatgpt():
    """Phase 2g.18: B2 panel slimmed 5→4, drops chatgpt."""
    assert _judges.JUDGE_PANEL_B2 == ("claude", "gemini", "llama", "qwen")
    assert "chatgpt" not in _judges.JUDGE_PANEL_B2


def test_judge_panel_b1_unchanged():
    """B1 panel stays 3-judge ("claude", "chatgpt", "gemini") — Phase 2g.18
    only slims B2."""
    assert _judges.JUDGE_PANEL == ("claude", "chatgpt", "gemini")


# ─── _ask_one routes through resolver; self_pref_answer bypasses it ──────────


@dataclass
class _FakeResponse:
    success: bool = True
    parsed: dict | None = None
    content: str = "{}"
    input_tokens: int = 10
    output_tokens: int = 5
    error: str | None = None


class _FakeClient:
    """Captures generate() calls so tests can inspect what model was sent."""

    def __init__(self):
        self.calls: list[dict] = []

    def generate(self, **kwargs):
        self.calls.append(kwargs)
        return _FakeResponse(parsed={"chosen": "A", "confidence": 0.9})


def _patch_client(monkeypatch) -> _FakeClient:
    fake = _FakeClient()
    monkeypatch.setattr(_judges, "get_client", lambda: fake)
    return fake


def test_ask_one_routes_claude_through_override(monkeypatch):
    """B1/B2 path: _ask_one resolves "claude" → Sonnet 4.6 before calling client."""
    fake = _patch_client(monkeypatch)
    _judges._ask_one(
        model_short="claude",
        system="judge sys",
        prompt="judge prompt",
        expects_fact_check=False,
    )
    assert len(fake.calls) == 1
    assert fake.calls[0]["model"] == "anthropic/claude-sonnet-4.6"


def test_ask_one_passes_other_shorts_through_generator_models(monkeypatch):
    """B1/B2 path: gemini/llama/etc. resolve through GENERATOR_MODELS (no
    override defined for them)."""
    fake = _patch_client(monkeypatch)
    _judges._ask_one(
        model_short="gemini",
        system="judge sys",
        prompt="judge prompt",
        expects_fact_check=False,
    )
    assert fake.calls[0]["model"] == GENERATOR_MODELS["gemini"]


def test_self_pref_answer_does_not_use_override(monkeypatch):
    """D1 path: self_pref_answer must NOT route claude through the override.

    This guards Phase 2g.18's deliberate split — the JUDGE_MODEL_OVERRIDES
    docstring explicitly says self_pref_answer keeps Opus 4.7 via
    GENERATOR_MODELS so self-pref calibration history doesn't mix model
    generations.
    """
    fake = _patch_client(monkeypatch)

    # If `_resolve_judge_model` is called, the test fails. We track invocations
    # via a wrapper rather than an outright stub so any incidental calls in
    # other code paths still raise immediately.
    invocations: list[str] = []

    def _spy(short: str) -> str:
        invocations.append(short)
        return _judges._resolve_judge_model(short)  # delegate (won't recurse)

    # Patch the name lookup so any call inside self_pref_answer goes through
    # our spy. We patch on the module so `from ... import` users would also
    # see it (though there are none today).
    monkeypatch.setattr(
        _judges,
        "_resolve_judge_model",
        _spy,
    )

    _judges.self_pref_answer(
        question_text="Q",
        options=[{"id": "A", "text": "Nebbiolo"}, {"id": "B", "text": "Sangiovese"}],
        model_short="claude",
    )

    # Critical assertion: the override resolver must NOT have been invoked
    # from self_pref_answer.
    assert invocations == [], (
        "self_pref_answer must not call _resolve_judge_model (D1 keeps Opus 4.7 "
        f"via GENERATOR_MODELS); got invocations={invocations}"
    )

    # And the actual model passed to the client is the GENERATOR_MODELS slug,
    # not the override.
    assert len(fake.calls) == 1
    assert fake.calls[0]["model"] == GENERATOR_MODELS["claude"]
    assert fake.calls[0]["model"] != "anthropic/claude-sonnet-4.6"


def test_self_pref_answer_other_models_use_generator_models(monkeypatch):
    """All non-claude shorts go through GENERATOR_MODELS in self_pref_answer."""
    fake = _patch_client(monkeypatch)
    for short in ("chatgpt", "gemini", "llama", "qwen"):
        _judges.self_pref_answer(
            question_text="Q",
            options=[{"id": "A", "text": "x"}, {"id": "B", "text": "y"}],
            model_short=short,
        )
    expected = [GENERATOR_MODELS[s] for s in ("chatgpt", "gemini", "llama", "qwen")]
    actual = [c["model"] for c in fake.calls]
    assert actual == expected
