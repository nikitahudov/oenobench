"""Cost computation for OpenRouter LLM calls.

Pricing snapshot: 2026-05-02 from https://openrouter.ai/api/v1/models
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelPricing:
    input_per_mtok_usd: float
    output_per_mtok_usd: float


# Per 1M tokens (USD)
_PRICING: dict[str, ModelPricing] = {
    "anthropic/claude-opus-4.7":          ModelPricing(5.00, 25.00),
    "anthropic/claude-haiku-4.5":         ModelPricing(1.00,  5.00),
    "openai/gpt-5":                       ModelPricing(1.25, 10.00),
    "openai/gpt-5-mini":                  ModelPricing(0.25,  2.00),
    "openai/o3":                          ModelPricing(2.00,  8.00),
    "google/gemini-2.5-pro":              ModelPricing(1.25, 10.00),
    "google/gemini-2.5-flash":            ModelPricing(0.30,  2.50),
    "meta-llama/llama-3.3-70b-instruct":  ModelPricing(0.10,  0.32),
    "meta-llama/llama-3.1-8b-instruct":   ModelPricing(0.02,  0.05),
    "deepseek/deepseek-chat":             ModelPricing(0.32,  0.89),
    "deepseek/deepseek-r1":               ModelPricing(0.70,  2.50),
    "qwen/qwen-2.5-72b-instruct":         ModelPricing(0.36,  0.40),
    "qwen/qwen-2.5-7b-instruct":          ModelPricing(0.04,  0.10),
    "mistralai/mistral-large-2411":       ModelPricing(2.00,  6.00),
}


def compute_cost(
    model_id: str,
    input_tokens: int,
    output_tokens: int,
    reasoning_tokens: int = 0,
) -> float:
    """Compute USD cost. Reasoning tokens are billed at the output rate.

    Returns 0.0 if model_id is unknown (caller should log a warning).
    """
    pricing = _PRICING.get(model_id)
    if pricing is None:
        return 0.0
    return (
        input_tokens * pricing.input_per_mtok_usd
        + (output_tokens + reasoning_tokens) * pricing.output_per_mtok_usd
    ) / 1_000_000.0


def get_pricing(model_id: str) -> ModelPricing | None:
    return _PRICING.get(model_id)


def known_models() -> list[str]:
    return sorted(_PRICING.keys())
