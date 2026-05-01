"""OenoBench — Closed-book solvability gate (B2 leakage prevention).

Generation-time pre-screen that rejects L1/L2 multiple-choice questions
solvable by a strong LLM without seeing the source fact.

Ships v1.0 — see docs/PROCESS_LOG.md 2026-04-24 (Phase 2g.5) for the
prototype that established the threshold (Sonnet 4.6 MC closed-book at
conf>=0.7 → 94% recall, 77% precision on audit_pilot_v4).

Failure semantics
-----------------
On API error or response-parse failure the gate returns PASS (fail-open).
Rationale: a network blip should not silently drop generated questions.
The error is logged and surfaced in `GateResult.error` so post-hoc
analysis can identify gate flakiness.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass

import openai
from dotenv import load_dotenv
from loguru import logger
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from src.generators._llm_client import _try_parse_json
from src.generators import _llm_cache

load_dotenv()

GATE_VERSION = "2.4.0"  # 2026-04-28 — lever B4: tier-aware gate model (Haiku L1 / Sonnet L2 / Opus L3)

# Phase 2g.8 (2026-04-26) introduced a single OENOBENCH_GATE_MODEL env var
# so audit pilots could swap Sonnet ↔ Opus without code changes.
#
# Lever B4 (2026-04-28) tiers the gate model by question difficulty:
#   L1 → Haiku 4.5 — leakage near-zero on any model; cheapest+fastest is fine.
#   L2 → Sonnet 4.6 — balance.
#   L3 → Opus 4.7 — residual leakage lives here (33% in v5 at threshold 0.6).
#
# Override hierarchy (highest priority first):
#   1. Per-tier env var: OENOBENCH_GATE_MODEL_L1 / _L2 / _L3
#   2. Global env var:   OENOBENCH_GATE_MODEL (applies to ALL tiers — keeps
#                        the v8 audit pilot harness working byte-for-byte).
#   3. Module default for the tier (table above).
#
# Cost rationale (Anthropic list prices):
#   Haiku 4.5  — $1/$5  per MTok in/out — ~$0.0005 per gate call
#   Sonnet 4.6 — $3/$15 per MTok in/out — ~$0.0015 per gate call (3x)
#   Opus 4.7   — $15/$75 per MTok in/out — ~$0.0075 per gate call (15x)
#
# Backwards compatibility: GATE_MODEL is retained as a module attribute
# (resolves to the L3 default) so prototypes/team_beta_check_leakage.py
# and existing test fixtures that import the symbol keep working.
#
# Phase 2g.12 follow-up (2026-04-29): the Haiku slug was originally
# `anthropic/claude-haiku-4.5-20251001`, which OpenRouter rejects with
# `400 - 'is not a valid model ID'` (same class of bug as the Phase 2g.12
# Flash slug fix). v10 build saw 2 fail-open events; gate was effectively
# dead for L1. Switched to the bare `anthropic/claude-haiku-4.5` slug —
# matches the Sonnet/Opus pattern (no embedded date), which OpenRouter
# resolves to whatever the canonical Haiku 4.5 is. Per-tier env-var
# override (`OENOBENCH_GATE_MODEL_L1`) preserved for future flips.
_GATE_MODEL_DEFAULT_L1 = "anthropic/claude-haiku-4.5"
_GATE_MODEL_DEFAULT_L2 = "anthropic/claude-sonnet-4.6"
_GATE_MODEL_DEFAULT_L3 = "anthropic/claude-opus-4.7"


def _resolve_gate_model(difficulty) -> str:
    """Resolve the gate model for a given question difficulty.

    Override hierarchy:
      1. Per-tier env var: OENOBENCH_GATE_MODEL_L1/L2/L3 (highest)
      2. Global env var:   OENOBENCH_GATE_MODEL (applies to all tiers)
      3. Module default for the tier (Haiku/Sonnet/Opus for L1/L2/L3).

    If `difficulty` is missing, non-numeric, or outside {1, 2, 3}, falls
    back to the L3 default (defensive — protects against caller bugs and
    against any future relaxation of the L4-skip guard).
    """
    try:
        d = int(difficulty)
    except (TypeError, ValueError):
        d = 3
    if d not in {1, 2, 3}:
        d = 3
    per_tier = os.getenv(f"OENOBENCH_GATE_MODEL_L{d}")
    if per_tier:
        return per_tier
    glob = os.getenv("OENOBENCH_GATE_MODEL")
    if glob:
        return glob
    return {
        1: _GATE_MODEL_DEFAULT_L1,
        2: _GATE_MODEL_DEFAULT_L2,
        3: _GATE_MODEL_DEFAULT_L3,
    }[d]


# Backwards-compatible module attribute — resolves to the L3 default.
# Pre-B4 callers (prototypes/team_beta_check_leakage.py, test fixtures)
# read `_closed_book_gate.GATE_MODEL` as a string.
GATE_MODEL = _resolve_gate_model("3")
# Phase 2g.7 retune (2026-04-25): threshold lowered 0.7 -> 0.6 and gate
# extended to L3 multiple-choice. See prototypes/team_alpha_results.json.
#
# At threshold 0.7 the gate caught 0% of the residual non-cb L1/L2 fails
# on audit_pilot_v5 (Sonnet's confidence on the residual leaks lives in
# the 0.5-0.65 band, not 0.7+). Threshold 0.6 is the loosest setting that
# brings projected MC-only L1/L2 fail rate under the 15% Go gate (12.5%)
# while flagging only 15% of MC questions. L3 leakage at 0.6 is 33%
# (>=10% trigger) so the gate now applies to L3 MC as well.
#
# The OVERALL non-cb L1/L2 fail rate (33.7% on v5) is bounded by the
# non-MC populations (scenario_based: 63% B2 fail, true_false: 80%) which
# are structurally beyond the gate's reach. Closing the overall gate
# requires the parallel scenario_synthesis prompt fix (Team β).
CONFIDENCE_THRESHOLD = 0.6
# Maximum share of the 10k corpus that may be tagged `closed_book_solvable`.
# When this cap is hit at insertion time, additional gate-flagged questions
# are dropped instead of relabeled. See docs/PROCESS_LOG.md 2026-04-24
# (Phase 2g.6) for the original rationale.
#
# Phase 2g.14 (2026-04-29): tightened from 0.25 → 0.20 as part of the
# cost-reduction package. The 25% cap was conservative; gold review of
# v9/v10/v11 didn't flag the cb-tagged subset as too restrictive at the
# audit level. Lowering to 20% means more gate-flagged questions get
# DROPPED instead of relabeled, which (a) raises the average cb-free
# corpus quality and (b) trims downstream operations on cb-tagged rows.
CLOSED_BOOK_QUOTA_FRACTION = float(os.environ.get("OENOBENCH_CB_QUOTA", "0.25"))
CLOSED_BOOK_TAG = "closed_book_solvable"

# L1/L2/L3 questions of any 4-option type go through the gate. Phase
# 2g.7 (2026-04-25) extended coverage in two dimensions:
#   - difficulty: L1/L2 -> L1/L2/L3, after v5 showed 33% L3 leakage at
#     the new 0.6 threshold (>=10% escalation trigger).
#   - type: multiple_choice -> multiple_choice + scenario_based, after
#     v5 B2 revealed 63% scenario fail rate (19/30) on questions that
#     were silently bypassing the gate via the type guard. Scenarios
#     emit 4-option payloads identical in shape to MC, so the existing
#     prompt and parser work unchanged.
# L4 still skips: low volume, historically near-zero leakage, not worth
# the API spend. true_false (5 q on v5) skips because its 2-option
# payload doesn't fit the A/B/C/D prompt; revisit if T/F volume grows.
# short_answer / matching also skip — no fixed option list to mirror.
_GATED_DIFFICULTIES = {"1", "2", "3"}
_GATED_QUESTION_TYPES = {"multiple_choice", "scenario_based"}

_PROMPT = """You are taking a closed-book multiple-choice wine knowledge test. Pick the best answer using ONLY your general training knowledge — no external sources, no provided context facts.

QUESTION: {stem}

OPTIONS:
{options_block}

Respond with ONLY a JSON object:
{{
  "selected": "A" | "B" | "C" | "D",
  "confidence": 0.0-1.0,
  "reasoning": "one sentence on why"
}}

If you genuinely don't know, set confidence < 0.5 and pick your best guess."""


@dataclass
class GateResult:
    """Verdict from the closed-book gate.

    `passed` retains its v1.0 meaning — True iff the closed-book pre-screen
    did NOT solve the question. The new v2.0 wrapper translates `passed=False`
    into one of two downstream actions tracked by the booleans below:

    * `relabeled=True` — question was kept (inserted) under the
      `closed_book_solvable` tag with difficulty forced to L1.
    * `quota_full=True` — corpus already at the 25% closed-book-solvable
      cap, so this question was dropped.
    """

    passed: bool                    # True = pre-screen could not solve, keep as-is
    applied: bool                   # False = gate skipped (wrong difficulty/type)
    reason: str                     # human-readable verdict
    selected: str | None = None     # gate's MC pick (A/B/C/D)
    confidence: float | None = None # gate's self-reported confidence
    matched_gold: bool | None = None
    reasoning: str | None = None    # gate's one-line justification
    model: str = GATE_MODEL
    version: str = GATE_VERSION
    latency_ms: int | None = None
    error: str | None = None
    relabeled: bool = False         # set by wrapper when re-routed to L1 + tag
    quota_full: bool = False        # set by wrapper when dropped over the 25% cap

    def to_dict(self) -> dict:
        return asdict(self)


_client_singleton: openai.OpenAI | None = None


def _get_client() -> openai.OpenAI:
    global _client_singleton
    if _client_singleton is None:
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            raise ValueError(
                "OPENROUTER_API_KEY not set; closed-book gate cannot run."
            )
        _client_singleton = openai.OpenAI(
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1",
        )
    return _client_singleton


def _format_options(options) -> str:
    """Render options list as 'A. text\\nB. text...' for the prompt."""
    if isinstance(options, str):
        try:
            options = json.loads(options)
        except (json.JSONDecodeError, ValueError):
            return options
    if not options:
        return ""
    lines = []
    for opt in options:
        if isinstance(opt, dict):
            lines.append(f"{opt.get('id', '?')}. {opt.get('text', '')}")
        else:
            lines.append(str(opt))
    return "\n".join(lines)


def _normalize_letter(s: str | None) -> str:
    if not s:
        return ""
    s = str(s).strip().upper()
    return s[:1] if s and s[0] in "ABCDE" else ""


def _should_retry(exc: BaseException) -> bool:
    if isinstance(exc, openai.RateLimitError):
        return True
    if isinstance(exc, openai.APIStatusError) and exc.status_code >= 500:
        return True
    return False


@retry(
    retry=retry_if_exception(_should_retry),
    wait=wait_exponential(min=2, max=16),
    stop=stop_after_attempt(3),
    reraise=True,
)
def _call_gate(client: openai.OpenAI, prompt: str, model: str):
    return client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        max_tokens=400,
        response_format={"type": "json_object"},
    )


def screen_question(
    stem: str,
    options,
    correct_answer: str,
    difficulty: str,
    question_type: str,
    confidence_threshold: float | None = None,
) -> GateResult:
    """Run the closed-book gate on a candidate question.

    Args:
        stem: The question text.
        options: List of {'id': 'A', 'text': '...'} dicts, or pre-rendered string.
        correct_answer: The gold-truth letter ('A'/'B'/'C'/'D').
        difficulty: '1' through '4'.
        question_type: 'multiple_choice', 'true_false', etc.
        confidence_threshold: Optional override of the module-level
            `CONFIDENCE_THRESHOLD`. Used by the Phase 2g.7 threshold
            sweep prototype; production callers should pass None to use
            the configured default.

    Returns:
        GateResult. `passed=True` means keep the question.
    """
    threshold = (
        CONFIDENCE_THRESHOLD if confidence_threshold is None else float(confidence_threshold)
    )
    if (
        str(difficulty) not in _GATED_DIFFICULTIES
        or question_type not in _GATED_QUESTION_TYPES
    ):
        return GateResult(
            passed=True,
            applied=False,
            reason=f"skipped (difficulty={difficulty} type={question_type})",
        )

    options_block = _format_options(options)
    if not options_block:
        return GateResult(
            passed=True,
            applied=False,
            reason="skipped (no options to evaluate)",
        )

    gold_letter = _normalize_letter(correct_answer)
    prompt = _PROMPT.format(stem=stem, options_block=options_block)
    # Lever B4 (2026-04-28): resolve the gate model per call from the
    # question's difficulty. Hierarchy = per-tier env > global env > default.
    model = _resolve_gate_model(difficulty)
    logger.info(
        "Closed-book gate dispatch | difficulty={} type={} model={}",
        difficulty, question_type, model,
    )

    # Lever B1 (2026-04-28): content-hash cache. Skip the API call entirely
    # on a hit. Key includes the question payload + difficulty + type so a
    # paraphrase or distractor change re-runs the gate. Version tag and
    # model are part of the cache identity so a model swap or a
    # GATE_VERSION bump invalidates automatically.
    _cache_version_tag = f"GATE_VERSION={GATE_VERSION}"
    _cache_key = _llm_cache.cache_key({
        "stem": stem,
        "options": options,
        "correct_answer": correct_answer,
        "difficulty": str(difficulty),
        "question_type": question_type,
    })
    _cached = _llm_cache.lookup(
        kind="gate",
        key=_cache_key,
        model_id=model,
        version_tag=_cache_version_tag,
    )
    if _cached is not None:
        try:
            return GateResult(**_cached)
        except TypeError as e:
            # Stale schema (a field was added or removed since this row
            # was written). Treat as a miss; the next store() will
            # overwrite it on the next non-cached call.
            logger.warning(
                "LLM cache gate payload incompatible (treating as miss): {}", e,
            )

    t0 = time.time()
    try:
        client = _get_client()
        resp = _call_gate(client, prompt, model)
        latency_ms = int((time.time() - t0) * 1000)
        content = resp.choices[0].message.content or ""
        parsed = _try_parse_json(content)
    except Exception as e:  # noqa: BLE001
        latency_ms = int((time.time() - t0) * 1000)
        logger.warning(
            "Closed-book gate API error (failing open) | model={} err={} latency={}ms",
            model, str(e), latency_ms,
        )
        return GateResult(
            passed=True,
            applied=True,
            reason="api_error_fail_open",
            model=model,
            latency_ms=latency_ms,
            error=str(e),
        )

    if not parsed:
        logger.warning(
            "Closed-book gate JSON parse failed (failing open) | model={} content={}",
            model, content[:200],
        )
        return GateResult(
            passed=True,
            applied=True,
            reason="parse_failed_fail_open",
            model=model,
            latency_ms=latency_ms,
            error="json_parse_failed",
        )

    selected = _normalize_letter(parsed.get("selected"))
    try:
        confidence = float(parsed.get("confidence", 0.0) or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0
    reasoning = str(parsed.get("reasoning", ""))[:500]
    matched_gold = bool(selected) and selected == gold_letter

    if matched_gold and confidence >= threshold:
        passed = False
        reason = (
            f"reject: gate solved closed-book (selected={selected} "
            f"conf={confidence:.2f} >= {threshold})"
        )
    else:
        passed = True
        if matched_gold:
            reason = f"pass: gate matched gold but conf={confidence:.2f} < {threshold}"
        elif selected:
            reason = f"pass: gate picked {selected} (gold={gold_letter})"
        else:
            reason = "pass: gate response had no clear selection"

    result = GateResult(
        passed=passed,
        applied=True,
        reason=reason,
        selected=selected or None,
        confidence=confidence,
        matched_gold=matched_gold,
        reasoning=reasoning,
        model=model,
        latency_ms=latency_ms,
    )
    # Lever B1 cache store: only successful verdicts. We deliberately skip
    # the api_error / parse_failed paths above — caching a transient
    # failure would poison every later call with the same input.
    _llm_cache.store(
        kind="gate",
        key=_cache_key,
        model_id=model,
        version_tag=_cache_version_tag,
        payload=result.to_dict(),
    )
    return result
