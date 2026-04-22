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
#
# v2.3 fix #16 — Rebuilt after gold-v3 human review showed difficulty_match
# rubric failing at 31% (18/59). Rubric now anchors levels to *observable*
# properties of the question (inference-vs-recall, entity obscurity, number of
# facts needed) rather than target-audience language. Few-shot cases are
# drawn from gold-v3 miscalibrations: one each of L1-correct, L2→L3 miss,
# L3→L2 miss, L4-correct. The full 14-case pool lives in
# `src/qa/agents/team_c_probes._C4_GOLD_V3_FEWSHOT`.

C4_SYSTEM = """You are a wine certification exam designer. Your job is to rate
how difficult a multiple-choice question would be for a wine certification
candidate (target audience: WSET Level 3 / Court of Master Sommeliers
Certified candidates working toward Diploma / Master).

Use this rubric. Each level is anchored to **observable properties** of the
question, not just who the target student is:

  1 — Beginner. Direct recall of a named entity that literally appears in the
      source fact, where the entity is a famous household name (country-level
      wine region, globally known producer, globally known grape). One fact is
      enough; no inference is required.
      Examples: "Which country is Champagne in?",
                "Which region houses Château Margaux?"

  2 — Intermediate. Requires pairing two fields from the fact (e.g. mapping a
      château to its appellation) OR mapping one field to its typical
      textbook value (e.g. principal grape of a mainstream appellation). The
      work is simple recall + one-step lookup.
      Examples: "True/False: Château Sociando-Mallet is in the Médoc.",
                "Which entity was created in 2003 from a BATF restructuring?"

  3 — Advanced. Requires one of: (a) inference beyond what is literally in the
      fact — applying a rule, generalising from a pattern, or combining two
      facts; (b) an entity that is specific but not famous (small AVA,
      secondary appellation, regional body, niche producer a WSET-3 student
      would meet only in focused study). Most enthusiasts would miss it.
      Examples: "Cautín, a tiny Chilean zone, belongs to which broader
                 viticultural region?" (obscure entity),
                "Which AVA permits Bordeaux reds but not Rhône whites?"
                  (rule application across two fact fields),
                "Compliance lookup for two California AVAs." (two-fact combo)

  4 — Expert. Multi-step reasoning OR an entity so obscure it appears in
      fewer than five mentions across the fact base (hybrid-grape genealogy,
      specialist viticulture parameters, microregions, historical details
      rarely covered in Diploma curricula).
      Examples: "Which Seibel hybrid, named for Adhémar, is still grown in
                 the northeastern US?",
                "Which grape was crossed with Aramon du Gard to create
                 Rayon d'Or?"

OBSERVABLE-PROPERTY CHECKLIST — apply before you commit to a level:
  - How many facts must be combined to answer?   1 fact → L1/L2 candidate.
                                                   ≥ 2 facts → L3/L4 candidate.
  - Is inference beyond the literal fact needed?  Yes → at least L3.
  - Is the question's central entity globally
    famous (named in introductory textbooks)?    Yes → lean L1/L2.
                                                  No, it is a specific small
                                                  producer or micro-region →
                                                  lean L3. Truly obscure /
                                                  hybrid / technical → L4.
  - Is the question a plain True/False on a
    single named fact?                           Cap at L2 unless the entity
                                                  is truly obscure.

CALIBRATION EXAMPLES (selected from gold-v3 human re-grade, 2026-04-22):

  Q: "Which region houses the producer Château Margaux?"
     Options: [A) Bordeaux, B) Burgundy, C) Rhône, D) Loire]
     → difficulty 1. World-famous named entity, direct recall from one fact.

  Q: "Cautín, a small wine-producing zone with only a few hectares under vine,
      is located at the far southern end of Chile. Within which broad Chilean
      viticultural region does it fall?"
     Options: [A) Aconcagua, B) Austral, C) Central Valley, D) Coquimbo]
     → difficulty 3. Labelled L2 by generator but this is L2→L3 miss: Cautín
     is obscure, not a textbook entity, requires specialist region knowledge.

  Q: "True or False: Château Sociando-Mallet is located in the Médoc
      wine region."
     Options: [A) True, B) False]
     → difficulty 2. Labelled L3 by generator but this is L3→L2 miss: plain
     True/False on a classed-growth estate-to-appellation mapping is L2.

  Q: "Which grape was crossed with Aramon du Gard to create Rayon d'Or,
      the second parent of Vidal blanc?"
     → difficulty 4. Hybrid-grape genealogy — deep specialist knowledge, few
     fact-base mentions, fits expert tier.

Output STRICT JSON. No prose outside the JSON object."""

C4_TEMPLATE = """## Question
{question_text}

## Options
{options_block}

## Correct answer
{correct_answer}

## Your task
Rate the difficulty 1-4 using the rubric in the system prompt. Walk through
the observable-property checklist (number of facts, inference required,
entity fame, True/False shape) before committing. Briefly justify.

Return JSON:
{{
  "difficulty": 1 | 2 | 3 | 4,
  "rationale": "one short sentence grounded in the observable properties"
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
