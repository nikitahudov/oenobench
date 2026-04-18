"""Tri-judge LLM panel used by Team B.

Wraps `src.generators._llm_client.LLMClient` so we reuse the existing
retry/rate-limit/JSON-extraction logic. Judges are kept distinct from the
generator pool: the user explicitly excluded Llama and Qwen from judging
(they are *subjects* of bias audits, never adjudicators).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Iterable

from loguru import logger

from src.generators._llm_client import GENERATOR_MODELS, get_client
from src.qa._prompts import (
    CLOSED_BOOK_TEMPLATE,
    JUDGE_SYSTEM,
    OPEN_BOOK_TEMPLATE,
    SELF_PREF_SYSTEM,
    SELF_PREF_TEMPLATE,
    render_options,
)

# Three high-capability judges; intentionally excludes Llama/Qwen.
JUDGE_PANEL = ("claude", "chatgpt", "gemini")


@dataclass
class JudgeVerdict:
    judge: str
    chosen: str | None
    confidence: float
    fact_supports_key: bool | None
    rationale: str
    raw: str
    cost_usd: float = 0.0
    error: str | None = None
    prompt_hash: str = ""


@dataclass
class JudgeBatchResult:
    """Container for both open-book and closed-book outcomes per question."""

    open_book: list[JudgeVerdict] = field(default_factory=list)
    closed_book: list[JudgeVerdict] = field(default_factory=list)

    def total_cost(self) -> float:
        return sum(v.cost_usd for v in [*self.open_book, *self.closed_book])

    def total_calls(self) -> int:
        return len(self.open_book) + len(self.closed_book)


# Rough OpenRouter pricing per 1M tokens (USD, as of April 2026 — adjust here
# when prices move). Used only for cost ledger reporting; not billing-critical.
_PRICING = {
    "claude": (3.0, 15.0),                 # ($/M input, $/M output)
    "chatgpt": (2.5, 12.0),
    "gemini": (1.25, 10.0),
    "llama": (0.50, 1.50),
    "qwen": (0.30, 1.20),
}


def _estimate_cost(model_short: str, input_tokens: int, output_tokens: int) -> float:
    in_cost, out_cost = _PRICING.get(model_short, (1.0, 5.0))
    return (input_tokens / 1_000_000) * in_cost + (output_tokens / 1_000_000) * out_cost


def _prompt_hash(prompt: str, system: str, model: str) -> str:
    h = hashlib.sha256()
    h.update(system.encode())
    h.update(b"\n---\n")
    h.update(prompt.encode())
    h.update(b"\n---\n")
    h.update(model.encode())
    return h.hexdigest()[:16]


def _parse_verdict(model_short: str, response, expects_fact_check: bool) -> JudgeVerdict:
    if not response.success:
        return JudgeVerdict(
            judge=model_short,
            chosen=None,
            confidence=0.0,
            fact_supports_key=None,
            rationale="",
            raw=response.error or "",
            error=response.error,
        )
    parsed = response.parsed or {}
    chosen = parsed.get("chosen")
    if isinstance(chosen, str):
        chosen = chosen.strip().upper()[:1] if chosen else None
    return JudgeVerdict(
        judge=model_short,
        chosen=chosen,
        confidence=float(parsed.get("confidence", 0.0) or 0.0),
        fact_supports_key=(
            bool(parsed.get("fact_supports_key")) if expects_fact_check else None
        ),
        rationale=str(parsed.get("rationale", ""))[:300],
        raw=response.content[:2000],
        cost_usd=_estimate_cost(model_short, response.input_tokens, response.output_tokens),
    )


def _ask_one(
    *,
    model_short: str,
    system: str,
    prompt: str,
    expects_fact_check: bool,
) -> JudgeVerdict:
    client = get_client()
    response = client.generate(
        prompt=prompt,
        system=system,
        model=model_short,
        temperature=0.0,
        max_tokens=600,
        json_mode=True,
    )
    verdict = _parse_verdict(model_short, response, expects_fact_check)
    verdict.prompt_hash = _prompt_hash(prompt, system, model_short)
    return verdict


def judge_open_and_closed(
    *,
    question_text: str,
    options: list[dict],
    source_text: str,
    claimed_key: str,
    judges: Iterable[str] = JUDGE_PANEL,
) -> JudgeBatchResult:
    """Run B1 (open-book) and B2 (closed-book) on the same question.

    Each judge is asked twice — once with the source fact, once without —
    so we get six calls per question across the three-judge panel.
    """
    options_block = render_options(options)
    open_prompt = OPEN_BOOK_TEMPLATE.format(
        question_text=question_text,
        options_block=options_block,
        source_text=source_text or "(no source fact recorded)",
        claimed_key=claimed_key or "(unknown)",
    )
    closed_prompt = CLOSED_BOOK_TEMPLATE.format(
        question_text=question_text,
        options_block=options_block,
    )

    result = JudgeBatchResult()
    for judge in judges:
        if judge not in GENERATOR_MODELS:
            logger.warning("judge {} not in GENERATOR_MODELS; skipping", judge)
            continue
        result.open_book.append(
            _ask_one(
                model_short=judge,
                system=JUDGE_SYSTEM,
                prompt=open_prompt,
                expects_fact_check=True,
            )
        )
        result.closed_book.append(
            _ask_one(
                model_short=judge,
                system=JUDGE_SYSTEM,
                prompt=closed_prompt,
                expects_fact_check=False,
            )
        )
    return result


def self_pref_answer(
    *,
    question_text: str,
    options: list[dict],
    model_short: str,
) -> JudgeVerdict:
    """One model answers one question, no source. Used by D1."""
    options_block = render_options(options)
    prompt = SELF_PREF_TEMPLATE.format(
        question_text=question_text,
        options_block=options_block,
    )
    return _ask_one(
        model_short=model_short,
        system=SELF_PREF_SYSTEM,
        prompt=prompt,
        expects_fact_check=False,
    )
