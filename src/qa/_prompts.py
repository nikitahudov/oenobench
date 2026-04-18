"""Prompts used by audit judges (Team B and D1).

Kept terse on purpose — judges should not be asked to overthink. Every prompt
demands strict JSON to keep parsing reliable across models.
"""

from __future__ import annotations

# ─── Shared system prompt for Team B judges ──────────────────────────────────

JUDGE_SYSTEM = """You are a wine assessment expert acting as an independent judge for a benchmark.
You will be given a multiple-choice question and asked to:
  1) Pick the best answer from the options.
  2) Rate your confidence 0.0–1.0.
  3) Decide whether the supplied source fact (if shown) supports the keyed answer.

Reason carefully. Use ONLY the information given to you in this prompt and standard wine knowledge.
Output STRICT JSON matching the requested schema. No prose outside the JSON object."""


# ─── B1 — open-book judging (with source) ────────────────────────────────────

OPEN_BOOK_TEMPLATE = """## Question
{question_text}

## Options
{options_block}

## Source fact (the question was generated from this)
{source_text}

## Your task
Decide which option is the correct answer based on the source fact above.
Then judge whether the source fact actually supports the answer that the
benchmark says is correct (the "claimed key").

Claimed key (do NOT reveal in your reasoning): {claimed_key}

Return JSON:
{{
  "chosen": "A" | "B" | "C" | "D",
  "confidence": 0.0,
  "fact_supports_key": true | false,
  "rationale": "one short sentence"
}}"""


# ─── B2 — closed-book judging (no source shown) ──────────────────────────────

CLOSED_BOOK_TEMPLATE = """## Question
{question_text}

## Options
{options_block}

## Your task
Answer with only your own wine knowledge. The source fact is hidden from you.

Return JSON:
{{
  "chosen": "A" | "B" | "C" | "D",
  "confidence": 0.0,
  "rationale": "one short sentence"
}}"""


# ─── D1 — self-preference probing (open-book without claimed key) ───────────

SELF_PREF_SYSTEM = """You are a wine knowledge expert taking a benchmark exam.
Choose the single best answer. Output strict JSON only."""

SELF_PREF_TEMPLATE = """## Question
{question_text}

## Options
{options_block}

Return JSON:
{{
  "chosen": "A" | "B" | "C" | "D",
  "confidence": 0.0
}}"""


def render_options(options: list[dict]) -> str:
    """Render the option list as `A) text\\nB) text\\n...`. Robust to missing fields."""
    if not options:
        return "(no options provided)"
    lines = []
    for opt in options:
        oid = (opt.get("id") or opt.get("letter") or "?").strip()
        text = (opt.get("text") or opt.get("value") or "").strip()
        lines.append(f"{oid}) {text}")
    return "\n".join(lines)
