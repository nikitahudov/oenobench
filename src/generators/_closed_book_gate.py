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

load_dotenv()

GATE_VERSION = "2.1.0"
GATE_MODEL = "anthropic/claude-sonnet-4.6"
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
# (Phase 2g.6) for the rationale.
CLOSED_BOOK_QUOTA_FRACTION = 0.25
CLOSED_BOOK_TAG = "closed_book_solvable"

# L1/L2/L3 multiple-choice questions go through the gate. Phase 2g.7
# extended this to L3 after audit_pilot_v5 showed 33% L3 leakage at the
# new 0.6 threshold (>=10% trigger). L4 still skips: too low-volume to
# justify the API spend and historically near-zero leakage. Non-MC types
# (true/false, short_answer, matching, scenario_based) lack the option
# list the gate uses to mirror B2's evaluation, so they remain skipped.
_GATED_DIFFICULTIES = {"1", "2", "3"}
_GATED_QUESTION_TYPES = {"multiple_choice"}

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
def _call_gate(client: openai.OpenAI, prompt: str):
    return client.chat.completions.create(
        model=GATE_MODEL,
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

    t0 = time.time()
    try:
        client = _get_client()
        resp = _call_gate(client, prompt)
        latency_ms = int((time.time() - t0) * 1000)
        content = resp.choices[0].message.content or ""
        parsed = _try_parse_json(content)
    except Exception as e:  # noqa: BLE001
        latency_ms = int((time.time() - t0) * 1000)
        logger.warning(
            "Closed-book gate API error (failing open) | err={} | latency={}ms",
            str(e), latency_ms,
        )
        return GateResult(
            passed=True,
            applied=True,
            reason="api_error_fail_open",
            latency_ms=latency_ms,
            error=str(e),
        )

    if not parsed:
        logger.warning(
            "Closed-book gate JSON parse failed (failing open) | content={}",
            content[:200],
        )
        return GateResult(
            passed=True,
            applied=True,
            reason="parse_failed_fail_open",
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

    return GateResult(
        passed=passed,
        applied=True,
        reason=reason,
        selected=selected or None,
        confidence=confidence,
        matched_gold=matched_gold,
        reasoning=reasoning,
        latency_ms=latency_ms,
    )
