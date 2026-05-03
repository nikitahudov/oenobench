"""16-configuration eval registry for the Phase 5 OenoBench eval.

See docs/EVALUATION_PLAN.md and /home/winebench/.claude/plans/snoopy-dancing-deer.md.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

ReasoningMode = Literal["explicit_budget", "effort"] | None


@dataclass(frozen=True)
class EvalConfig:
    slot: int                            # 1-16, position in the slate
    name: str                            # human-readable label, e.g. "claude-opus-4.7"
    model_id: str                        # OR model ID
    provider_order: list[str]            # provider pin (first item = preferred)
    reasoning_mode: ReasoningMode = None
    reasoning_budget: int | None = None  # for explicit_budget mode (token cap)
    reasoning_effort: str | None = None  # "low"/"medium"/"high" for effort mode
    concurrency: int = 20                # per-config request concurrency
    logit_bias_supported: bool = False   # True = inject letter-token bias
    timeout_s: float = 60.0
    sibling_of: int | None = None        # marks reasoning twin of slot N (for delta analysis)
    family: str = ""                     # "anthropic", "openai", "google", "meta", "deepseek", "qwen", "mistral"
    is_generator_family: bool = False    # True if this family generated questions in Phase 2 (for SPS)


# === The 16 configurations ===
EVAL_CONFIGS: list[EvalConfig] = [
    # 1. Claude Opus 4.7 (frontier, SPS generator)
    EvalConfig(1, "claude-opus-4.7", "anthropic/claude-opus-4.7",
               provider_order=["Anthropic"], concurrency=20,
               family="anthropic", is_generator_family=True),
    # 2. Claude Haiku 4.5 (low-cost)
    EvalConfig(2, "claude-haiku-4.5", "anthropic/claude-haiku-4.5",
               provider_order=["Anthropic"], concurrency=40,
               family="anthropic", is_generator_family=True),
    # 3. GPT-5 (frontier, SPS generator)
    EvalConfig(3, "gpt-5", "openai/gpt-5",
               provider_order=["OpenAI"], concurrency=20,
               logit_bias_supported=True,
               family="openai", is_generator_family=True),
    # 4. GPT-5 mini
    EvalConfig(4, "gpt-5-mini", "openai/gpt-5-mini",
               provider_order=["OpenAI"], concurrency=40,
               logit_bias_supported=True,
               family="openai", is_generator_family=True),
    # 5. Gemini 2.5 Pro (frontier, SPS generator)
    EvalConfig(5, "gemini-2.5-pro", "google/gemini-2.5-pro",
               provider_order=["Google AI Studio"], concurrency=20,
               family="google", is_generator_family=True),
    # 6. Gemini 2.5 Flash
    EvalConfig(6, "gemini-2.5-flash", "google/gemini-2.5-flash",
               provider_order=["Google AI Studio"], concurrency=40,
               family="google", is_generator_family=True),
    # 7. Llama 3.3 70B (frontier open, SPS generator)
    EvalConfig(7, "llama-3.3-70b", "meta-llama/llama-3.3-70b-instruct",
               provider_order=["DeepInfra", "Novita"], concurrency=20,
               family="meta", is_generator_family=True),
    # 8. Llama 3.1 8B (small open)
    EvalConfig(8, "llama-3.1-8b", "meta-llama/llama-3.1-8b-instruct",
               provider_order=["DeepInfra", "Novita"], concurrency=40,
               family="meta", is_generator_family=True),
    # 9. DeepSeek V3
    EvalConfig(9, "deepseek-v3", "deepseek/deepseek-chat",
               provider_order=["DeepInfra", "Novita"], concurrency=20,
               logit_bias_supported=True,
               family="deepseek"),
    # 10. Qwen 2.5 72B (SPS generator — Qwen authored ~20.5% of public corpus)
    EvalConfig(10, "qwen-2.5-72b", "qwen/qwen-2.5-72b-instruct",
               provider_order=["DeepInfra", "Novita"], concurrency=20,
               family="qwen", is_generator_family=True),
    # 11. Qwen 2.5 7B (SPS generator — Qwen authored ~20.5% of public corpus)
    EvalConfig(11, "qwen-2.5-7b", "qwen/qwen-2.5-7b-instruct",
               provider_order=["Together", "AtlasCloud"], concurrency=40,
               family="qwen", is_generator_family=True),
    # 12. Mistral Large 2411
    EvalConfig(12, "mistral-large-2411", "mistralai/mistral-large-2411",
               provider_order=["Mistral"], concurrency=40,
               family="mistral"),
    # 13. o3 (reasoning, OpenAI)
    EvalConfig(13, "o3", "openai/o3",
               provider_order=["OpenAI"],
               reasoning_mode="effort", reasoning_effort="medium",
               concurrency=30, logit_bias_supported=True,
               family="openai", is_generator_family=True),
    # 14. Gemini 2.5 Pro thinking
    EvalConfig(14, "gemini-2.5-pro-thinking", "google/gemini-2.5-pro",
               provider_order=["Google AI Studio"],
               reasoning_mode="explicit_budget", reasoning_budget=512,
               concurrency=30, sibling_of=5,
               family="google", is_generator_family=True),
    # 15. DeepSeek R1
    EvalConfig(15, "deepseek-r1", "deepseek/deepseek-r1",
               provider_order=["Novita", "Azure"],
               reasoning_mode="explicit_budget", reasoning_budget=512,
               concurrency=30, logit_bias_supported=True,
               family="deepseek"),
    # 16. Claude Opus 4.7 + extended thinking
    EvalConfig(16, "claude-opus-4.7-thinking", "anthropic/claude-opus-4.7",
               provider_order=["Anthropic"],
               reasoning_mode="explicit_budget", reasoning_budget=512,
               concurrency=30, sibling_of=1,
               family="anthropic", is_generator_family=True),
]

assert len(EVAL_CONFIGS) == 16, f"Expected 16 configs, got {len(EVAL_CONFIGS)}"
assert [c.slot for c in EVAL_CONFIGS] == list(range(1, 17)), "Slots must be 1..16 in order"


def by_slot(slot: int) -> EvalConfig:
    return EVAL_CONFIGS[slot - 1]


def by_name(name: str) -> EvalConfig:
    for c in EVAL_CONFIGS:
        if c.name == name:
            return c
    raise KeyError(name)
