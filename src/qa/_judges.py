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

# Three high-capability judges for B1 / D1 — intentionally excludes Llama/Qwen
# because their world-knowledge gaps would inflate B1 disagreement.
JUDGE_PANEL = ("claude", "chatgpt", "gemini")

# Wider panel for B2 ClosedBookSolvability ONLY. The gold review showed Opus 4.7
# / GPT-5.4 / Gemini 3.1 Pro know far more wine than the typical certification
# candidate; they over-report leakage by ~5×. Llama and Qwen approximate
# test-taker-strength world knowledge, so adding them re-calibrates the panel.
#
# Phase 2g.18 cost-down: 5→4. Drop chatgpt (most expensive at $2.5/$12).
# Keep claude(Sonnet via override) + gemini for premium triangulation,
# llama + qwen as test-taker calibration anchors. The Llama+Qwen calibration
# anchor logic (above) requires those judges to stay even though they're cheap;
# dropping GPT-5 leaves the surviving expert (Claude-Sonnet via override +
# Gemini) diluted 1:1 by Llama+Qwen, which strengthens the calibration anchor.
JUDGE_PANEL_B2 = ("claude", "gemini", "llama", "qwen")


@dataclass
class JudgeVerdict:
    judge: str
    chosen: str | None
    confidence: float
    fact_supports_choice: bool | None
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


# Phase 2g.18 (2026-05-02) cost-down: resolve "claude" judge slot to
# Sonnet 4.6 in the B1/B2 panels only. Verifier-claude is already
# Sonnet via _verify.VERIFIER_MODEL_OVERRIDES (Phase 2g.14). Generator
# pool and D1 SelfPreference evaluator stay on Opus 4.7 so self-pref
# calibration history doesn't mix model generations.
#
# Mirrors the Phase 2g.14 verifier override pattern; intentionally
# scoped to _ask_one and NOT applied inside self_pref_answer.
JUDGE_MODEL_OVERRIDES: dict[str, str] = {
    "claude": "anthropic/claude-sonnet-4.6",
}


def _resolve_judge_model(short: str) -> str:
    """Resolve a judge short-name to its OpenRouter slug for B1/B2 only.

    Looks up JUDGE_MODEL_OVERRIDES first, then falls back to GENERATOR_MODELS.
    Unknown shorts are returned verbatim so a caller passing a full slug
    is also supported.
    """
    if short in JUDGE_MODEL_OVERRIDES:
        return JUDGE_MODEL_OVERRIDES[short]
    return GENERATOR_MODELS.get(short, short)


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
            fact_supports_choice=None,
            rationale="",
            raw=response.error or "",
            error=response.error,
        )
    parsed = response.parsed or {}
    chosen = parsed.get("chosen")
    if isinstance(chosen, str):
        chosen = chosen.strip().upper()[:1] if chosen else None
    fsc = parsed.get("fact_supports_choice")
    if fsc is None:
        fsc = parsed.get("fact_supports_key")  # legacy field, tolerate
    return JudgeVerdict(
        judge=model_short,
        chosen=chosen,
        confidence=float(parsed.get("confidence", 0.0) or 0.0),
        fact_supports_choice=(bool(fsc) if expects_fact_check else None),
        rationale=str(parsed.get("rationale", ""))[:300],
        raw=response.content[:2000],
        cost_usd=_estimate_cost(model_short, response.input_tokens, response.output_tokens),
    )


def _ask_one_with_model(
    *,
    model_short: str,
    resolved_model: str,
    system: str,
    prompt: str,
    expects_fact_check: bool,
) -> JudgeVerdict:
    """Call one judge with an explicitly resolved model slug.

    `model_short` is used for the cost ledger and verdict identification;
    `resolved_model` is the actual OpenRouter slug passed to the LLM client.
    Splitting these lets B1/B2 route ``claude`` → Sonnet 4.6 (Phase 2g.18)
    while D1 ``self_pref_answer`` keeps Opus 4.7 via GENERATOR_MODELS.
    """
    client = get_client()
    response = client.generate(
        prompt=prompt,
        system=system,
        model=resolved_model,
        temperature=0.0,
        max_tokens=600,
        json_mode=True,
    )
    verdict = _parse_verdict(model_short, response, expects_fact_check)
    verdict.prompt_hash = _prompt_hash(prompt, system, resolved_model)
    return verdict


def _ask_one(
    *,
    model_short: str,
    system: str,
    prompt: str,
    expects_fact_check: bool,
) -> JudgeVerdict:
    # Phase 2g.18: resolve through JUDGE_MODEL_OVERRIDES so the "claude"
    # judge slot routes to Sonnet 4.6 instead of Opus 4.7. Pricing for
    # cost ledger is still keyed by short-name (_estimate_cost), but the
    # actual model call goes through the resolved slug.
    resolved_model = _resolve_judge_model(model_short)
    return _ask_one_with_model(
        model_short=model_short,
        resolved_model=resolved_model,
        system=system,
        prompt=prompt,
        expects_fact_check=expects_fact_check,
    )


def judge_open_and_closed(
    *,
    question_text: str,
    options: list[dict],
    source_text: str,
    claimed_key: str = "",
    judges: Iterable[str] = JUDGE_PANEL,
    closed_book_judges: Iterable[str] | None = None,
) -> JudgeBatchResult:
    """Run B1 (open-book) and B2 (closed-book) on the same question.

    `judges` controls the open-book pass (B1). `closed_book_judges` controls
    the closed-book pass (B2); when None it defaults to `JUDGE_PANEL_B2`,
    which adds Llama and Qwen so the panel approximates a real test-taker's
    world knowledge (see `docs/GOLD_CALIBRATION_ANALYSIS.md` §4 — Opus/GPT-5/
    Gemini over-report leakage by ~5× because they know more wine than the
    benchmark target audience).

    The claimed_key is NOT shown to judges; it's used post-hoc to score
    whether the judge majority matches the keyed answer.
    """
    if closed_book_judges is None:
        closed_book_judges = JUDGE_PANEL_B2

    options_block = render_options(options)
    open_prompt = OPEN_BOOK_TEMPLATE.format(
        question_text=question_text,
        options_block=options_block,
        source_text=source_text or "(no source fact recorded)",
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
    for judge in closed_book_judges:
        if judge not in GENERATOR_MODELS:
            logger.warning("closed-book judge {} not in GENERATOR_MODELS; skipping", judge)
            continue
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
    """One model answers one question, no source. Used by D1.

    D1 keeps Opus via GENERATOR_MODELS — see JUDGE_MODEL_OVERRIDES
    docstring for rationale. Self-preference calibration history is
    accumulated against Opus 4.7 generations; if D1's evaluator slot
    silently routed through the B1/B2 Sonnet override, the cross-version
    self-pref delta would no longer be comparable.
    """
    options_block = render_options(options)
    prompt = SELF_PREF_TEMPLATE.format(
        question_text=question_text,
        options_block=options_block,
    )
    # NOTE: deliberately bypasses `_resolve_judge_model` (and therefore
    # JUDGE_MODEL_OVERRIDES) so D1 stays on the generator pool model.
    return _ask_one_with_model(
        model_short=model_short,
        resolved_model=GENERATOR_MODELS.get(model_short, model_short),
        system=SELF_PREF_SYSTEM,
        prompt=prompt,
        expects_fact_check=False,
    )
