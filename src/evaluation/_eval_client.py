"""Per-config OpenRouter request shaping for Phase 5 eval.

Builds the right `extra_body` for each EvalConfig (provider pin,
reasoning param, logit_bias) and parses single-letter answers.
Wraps the existing src/generators/_llm_client.py:LLMClient.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from src.evaluation.configs import EvalConfig
from src.generators._llm_client import LLMClient, LLMResponse

# Cap the visible output. OpenAI's gpt-5/gpt-5-mini ALWAYS use implicit
# internal reasoning (even when our `reasoning` extra_body is unset), and
# those reasoning tokens are billed against `max_completion_tokens`. With a
# tight cap (16-100) the model uses the entire budget for reasoning and emits
# no visible text. 1000 gives enough headroom for implicit reasoning + the
# single visible letter. Models still emit short output (~1-3 visible tokens
# after the letter); we are only billed for what is actually generated.
_MAX_OUTPUT_TOKENS = 1000

_SINGLE_LETTER_SYSTEM_PROMPT = (
    "You are taking a multiple-choice exam. "
    "Reply with exactly one letter — A, B, C, or D — and nothing else. "
    "No explanation, no punctuation, no whitespace before or after."
)

# Static logit-bias table for OpenAI/DeepSeek-OAI compatible tokenizers.
# Letter tokens A/B/C/D are typically single-token; +5 logit boost is gentle.
# Tokens are looked up by string in OpenRouter requests (server resolves IDs).
# The table here uses string keys; the wrapper passes them as-is.
_LETTER_LOGIT_BIAS: dict[str, int] = {"A": 5, "B": 5, "C": 5, "D": 5}

_LETTER_RE = re.compile(r"\b([ABCD])\b")


@dataclass(frozen=True)
class EvalResult:
    config: EvalConfig
    response: LLMResponse
    parsed_answer: str | None  # "A"/"B"/"C"/"D" or None on parse failure
    raw_text: str


def build_extra_body(config: EvalConfig) -> dict:
    """Return the per-config extra_body dict for OpenRouter."""
    body: dict = {
        "provider": {
            "order": list(config.provider_order),
            "allow_fallbacks": False,
        }
    }
    if config.reasoning_mode == "explicit_budget":
        body["reasoning"] = {"max_tokens": int(config.reasoning_budget or 512)}
    elif config.reasoning_mode == "effort":
        body["reasoning"] = {"effort": config.reasoning_effort or "medium"}
    if config.logit_bias_supported:
        body["logit_bias"] = dict(_LETTER_LOGIT_BIAS)
    return body


def render_question(question_text: str, options: dict[str, str]) -> str:
    """Format a question + 4 options for the model. options is {'A': '...', 'B': '...', ...}."""
    parts = [question_text.strip(), ""]
    for letter in ("A", "B", "C", "D"):
        if letter in options:
            parts.append(f"{letter}. {options[letter].strip()}")
    return "\n".join(parts)


def parse_letter(text: str) -> str | None:
    """Extract first A/B/C/D from a model response. Returns None if not found."""
    if not text:
        return None
    m = _LETTER_RE.search(text.strip().upper())
    return m.group(1) if m else None


def evaluate_one(
    client: LLMClient,
    config: EvalConfig,
    question_text: str,
    options: dict[str, str],
    override_system: str | None = None,
) -> EvalResult:
    extra_body = build_extra_body(config)
    response = client.generate(
        prompt=render_question(question_text, options),
        system=override_system or _SINGLE_LETTER_SYSTEM_PROMPT,
        model=config.model_id,
        temperature=0.0,
        max_tokens=_MAX_OUTPUT_TOKENS,
        json_mode=False,
        extra_body=extra_body,
        timeout=config.timeout_s,
    )
    raw = response.content or ""
    parsed = parse_letter(raw) if response.success else None
    return EvalResult(config=config, response=response, parsed_answer=parsed, raw_text=raw)
