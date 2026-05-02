"""Tests for src/evaluation/configs.py and src/evaluation/_eval_client.py."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.evaluation.configs import EVAL_CONFIGS, EvalConfig, by_name, by_slot
from src.evaluation._eval_client import (
    EvalResult,
    build_extra_body,
    evaluate_one,
    parse_letter,
    render_question,
)
from src.generators._llm_client import LLMClient, LLMResponse


# ---------------------------------------------------------------------------
# Config registry tests
# ---------------------------------------------------------------------------


def test_configs_count():
    assert len(EVAL_CONFIGS) == 16


def test_configs_slots_ordered():
    """Slots must be exactly 1..16 in order."""
    assert [c.slot for c in EVAL_CONFIGS] == list(range(1, 17))


def test_configs_unique_slots():
    slots = [c.slot for c in EVAL_CONFIGS]
    assert len(slots) == len(set(slots))


def test_configs_sps_coverage():
    """At least one config per generator family has is_generator_family=True."""
    generator_families = {c.family for c in EVAL_CONFIGS if c.is_generator_family}
    for required in ("anthropic", "openai", "google", "meta"):
        assert required in generator_families, f"No generator-family config for {required}"


# ---------------------------------------------------------------------------
# build_extra_body tests
# ---------------------------------------------------------------------------


def test_build_extra_body_provider_pin():
    """Every config produces a body with correct provider order and allow_fallbacks=False."""
    for config in EVAL_CONFIGS:
        body = build_extra_body(config)
        assert body["provider"]["order"] == config.provider_order
        assert body["provider"]["allow_fallbacks"] is False


@pytest.mark.parametrize("slot", [14, 15, 16])
def test_build_extra_body_reasoning_explicit(slot):
    """Slots 14, 15, 16 have explicit_budget reasoning with max_tokens=512."""
    config = by_slot(slot)
    body = build_extra_body(config)
    assert "reasoning" in body
    assert body["reasoning"] == {"max_tokens": 512}


def test_build_extra_body_reasoning_effort():
    """Slot 13 (o3) uses effort-mode reasoning with 'medium'."""
    config = by_slot(13)
    body = build_extra_body(config)
    assert "reasoning" in body
    assert body["reasoning"] == {"effort": "medium"}


@pytest.mark.parametrize("slot", list(range(1, 13)))
def test_build_extra_body_no_reasoning_for_standard(slot):
    """Slots 1-12 (standard configs) have no 'reasoning' key."""
    config = by_slot(slot)
    body = build_extra_body(config)
    assert "reasoning" not in body


def test_build_extra_body_logit_bias():
    """Configs with logit_bias_supported=True include logit_bias dict; others don't."""
    logit_bias_slots = {3, 4, 9, 13, 15}
    for config in EVAL_CONFIGS:
        body = build_extra_body(config)
        if config.logit_bias_supported:
            assert config.slot in logit_bias_slots, (
                f"Slot {config.slot} has logit_bias_supported=True but not in expected set"
            )
            assert "logit_bias" in body
            assert isinstance(body["logit_bias"], dict)
        else:
            assert config.slot not in logit_bias_slots, (
                f"Slot {config.slot} should have logit_bias_supported=True"
            )
            assert "logit_bias" not in body


# ---------------------------------------------------------------------------
# parse_letter tests
# ---------------------------------------------------------------------------


def test_parse_letter_plain():
    assert parse_letter("A") == "A"


def test_parse_letter_with_whitespace_and_punct():
    assert parse_letter("  B.  ") == "B"


def test_parse_letter_embedded():
    assert parse_letter("The answer is C") == "C"


def test_parse_letter_empty():
    assert parse_letter("") is None


def test_parse_letter_no_match():
    assert parse_letter("xyz") is None


def test_parse_letter_lowercase():
    """parse_letter uppercases before matching."""
    assert parse_letter("a") == "A"


# ---------------------------------------------------------------------------
# render_question tests
# ---------------------------------------------------------------------------


def test_render_question():
    q = "What grape variety is used in Barolo?"
    opts = {
        "A": "Sangiovese",
        "B": "Nebbiolo",
        "C": "Barbera",
        "D": "Dolcetto",
    }
    rendered = render_question(q, opts)
    assert "A. Sangiovese" in rendered
    assert "B. Nebbiolo" in rendered
    assert "C. Barbera" in rendered
    assert "D. Dolcetto" in rendered
    # Check order: A before B before C before D
    pos_a = rendered.index("A.")
    pos_b = rendered.index("B.")
    pos_c = rendered.index("C.")
    pos_d = rendered.index("D.")
    assert pos_a < pos_b < pos_c < pos_d


# ---------------------------------------------------------------------------
# evaluate_one (mocked) test
# ---------------------------------------------------------------------------


def test_evaluate_one_mocked():
    """evaluate_one returns parsed_answer='A' and passes correct extra_body to generate."""
    config = by_slot(1)  # claude-opus-4.7, no reasoning, no logit bias

    stub_response = LLMResponse(
        content="A",
        success=True,
        model=config.model_id,
        input_tokens=10,
        output_tokens=1,
        reasoning_tokens=0,
        latency_ms=100,
    )

    mock_client = MagicMock(spec=LLMClient)
    mock_client.generate.return_value = stub_response

    q = "Which country is Barolo from?"
    opts = {"A": "Italy", "B": "France", "C": "Spain", "D": "Germany"}

    result = evaluate_one(mock_client, config, q, opts)

    assert isinstance(result, EvalResult)
    assert result.parsed_answer == "A"
    assert result.raw_text == "A"
    assert result.response is stub_response

    # Verify the generate call args
    call_kwargs = mock_client.generate.call_args.kwargs
    assert call_kwargs["model"] == config.model_id
    assert call_kwargs["temperature"] == 0.0
    assert call_kwargs["max_tokens"] == 2000
    assert call_kwargs["json_mode"] is False

    extra_body = call_kwargs["extra_body"]
    expected_extra_body = build_extra_body(config)
    assert extra_body == expected_extra_body
    assert extra_body["provider"]["order"] == ["Anthropic"]
    assert extra_body["provider"]["allow_fallbacks"] is False
    assert "reasoning" not in extra_body
    assert "logit_bias" not in extra_body


def test_evaluate_one_failed_response_returns_none_parsed():
    """When generate returns success=False, parsed_answer is None."""
    config = by_slot(3)  # GPT-5, logit_bias_supported

    stub_response = LLMResponse(
        content="",
        success=False,
        model=config.model_id,
        error="timeout",
        latency_ms=60000,
    )

    mock_client = MagicMock(spec=LLMClient)
    mock_client.generate.return_value = stub_response

    result = evaluate_one(mock_client, config, "Q?", {"A": "a", "B": "b", "C": "c", "D": "d"})
    assert result.parsed_answer is None


def test_evaluate_one_reasoning_config_extra_body():
    """Slot 16 (claude-opus thinking) passes reasoning extra_body correctly."""
    config = by_slot(16)

    stub_response = LLMResponse(
        content="B",
        success=True,
        model=config.model_id,
        input_tokens=20,
        output_tokens=1,
        reasoning_tokens=400,
        latency_ms=5000,
    )

    mock_client = MagicMock(spec=LLMClient)
    mock_client.generate.return_value = stub_response

    result = evaluate_one(mock_client, config, "Q?", {"A": "a", "B": "b", "C": "c", "D": "d"})
    assert result.parsed_answer == "B"

    call_kwargs = mock_client.generate.call_args.kwargs
    extra_body = call_kwargs["extra_body"]
    assert extra_body["reasoning"] == {"max_tokens": 512}
    assert extra_body["provider"]["order"] == ["Anthropic"]
