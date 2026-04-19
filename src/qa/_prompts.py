"""Prompts used by audit judges (Team B and D1).

Kept terse on purpose — judges should not be asked to overthink. Every prompt
demands strict JSON to keep parsing reliable across models.
"""

from __future__ import annotations

# ─── Shared system prompt for Team B judges ──────────────────────────────────

JUDGE_SYSTEM = """You are a wine assessment expert acting as an independent judge for a benchmark.
You will be shown a multiple-choice question and asked to:
  1) Pick the single best answer from the options.
  2) Rate your confidence 0.0–1.0.
  3) Say whether the supplied source fact (if any) supports the answer you chose.

Reason carefully. Use ONLY the information given to you in this prompt and standard wine knowledge.
Output STRICT JSON matching the requested schema. No prose outside the JSON object.
Do not be told what the "official" answer is — decide for yourself."""


# ─── B1 — open-book judging (with source, claimed key intentionally hidden) ──

OPEN_BOOK_TEMPLATE = """## Question
{question_text}

## Options
{options_block}

## Source fact (the question was generated from this)
{source_text}

## Your task
Based only on the source fact above (supplemented by standard wine knowledge if and
only if the fact is silent on a detail), pick the single best option.
Then say whether the source fact actually supports your chosen answer.

Return JSON:
{{
  "chosen": "A" | "B" | "C" | "D",
  "confidence": 0.0,
  "fact_supports_choice": true | false,
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


# ─── C4 — difficulty re-classifier (single Gemini call per question) ─────────

C4_SYSTEM = """You are a wine certification exam designer. Your job is to rate
how difficult a multiple-choice question would be for a wine certification
candidate (target audience: WSET Level 3 / Court of Master Sommeliers
Certified candidates working toward Diploma / Master).

Use this rubric strictly:
  1 — Beginner. Recall of well-known basics any wine enthusiast would answer.
      Examples: "Which country is Champagne in?", "Which grape is the main red of Burgundy?"
  2 — Intermediate. Recall or simple application requiring formal study.
      Examples: classic appellation rules, common grape-region pairings, basic vinification facts.
  3 — Advanced. Requires study beyond the major regions: lesser-known appellations,
      specific regulations, viticultural / winemaking details. Most enthusiasts would miss it.
  4 — Expert. Specialist knowledge: obscure sub-regions, niche producers, technical viticulture
      / oenology, regional regulation specifics. Even Diploma-level candidates struggle.

Output STRICT JSON. No prose outside the JSON object."""

C4_TEMPLATE = """## Question
{question_text}

## Options
{options_block}

## Correct answer
{correct_answer}

## Your task
Rate the difficulty 1-4 using the rubric in the system prompt. Briefly justify.

Return JSON:
{{
  "difficulty": 1 | 2 | 3 | 4,
  "rationale": "one short sentence"
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
