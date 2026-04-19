"""Tests for the v2.1 generator allocation in src.generators.orchestrator.

Covers:
- STRATEGY_TARGETS sums to OVERALL_TARGET (10,000).
- No GENERATOR_TARGETS value exceeds the 35% cap (3,500).
- Template share is exactly 1,000 (10% of 10,000) per the gold-review cut.
"""

from __future__ import annotations

from src.generators.orchestrator import (
    GENERATOR_TARGETS,
    OVERALL_TARGET,
    STRATEGY_TARGETS,
)


# ─── STRATEGY_TARGETS ─────────────────────────────────────────────────────────


def test_strategy_targets_sum_to_overall_target():
    """All five strategy quotas must sum to OVERALL_TARGET (10,000)."""
    assert OVERALL_TARGET == 10_000
    assert sum(STRATEGY_TARGETS.values()) == 10_000


def test_strategy_targets_template_is_1000():
    """Per the v2.1 plan §0, the template share is cut to 1,000 (10%)."""
    assert STRATEGY_TARGETS["template"] == 1000


def test_strategy_targets_have_expected_keys():
    """The five canonical strategies must all be present."""
    expected = {
        "fact_to_question",
        "template",
        "comparative",
        "scenario_synthesis",
        "distractor_mining",
    }
    assert set(STRATEGY_TARGETS) == expected


# ─── GENERATOR_TARGETS ────────────────────────────────────────────────────────


def test_generator_targets_under_35_percent_cap():
    """No single generator may exceed 35% of OVERALL_TARGET (3,500 questions)."""
    cap = int(OVERALL_TARGET * 0.35)
    assert cap == 3500
    for generator, target in GENERATOR_TARGETS.items():
        assert target <= cap, (
            f"Generator '{generator}' target {target} exceeds 35% cap of {cap}"
        )


def test_generator_targets_sum_to_9000():
    """LLM strategies share 9,000 questions (template absorbs the other 1,000)."""
    assert sum(GENERATOR_TARGETS.values()) == 9000


def test_generator_targets_have_all_five_models():
    """All five generator models must appear in the allocation."""
    expected = {"claude", "chatgpt", "gemini", "qwen", "llama"}
    assert set(GENERATOR_TARGETS) == expected


def test_strategy_plus_template_consistency():
    """Template strategy quota plus LLM strategy quotas equal OVERALL_TARGET."""
    llm_strategies = {
        "fact_to_question",
        "comparative",
        "scenario_synthesis",
        "distractor_mining",
    }
    llm_total = sum(STRATEGY_TARGETS[s] for s in llm_strategies)
    assert llm_total == sum(GENERATOR_TARGETS.values())
    assert llm_total + STRATEGY_TARGETS["template"] == OVERALL_TARGET
