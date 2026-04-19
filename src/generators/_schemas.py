"""
OenoBench — Pydantic schemas for question generation.

Validates LLM JSON output before database insertion, with robust
parsing that handles common LLM output quirks (markdown fences,
extra text around JSON, etc.).

Also hosts post-LLM rejection gates that fire AFTER Pydantic validation
but BEFORE the question is returned to the strategy module:

  1. LCS verbatim-copy guard (v2.1 plan §2 / fix #2). Rejects any question
     whose `question_text + correct_option_text` shares > 0.6 LCS ratio
     with any source fact. Uses the same tokenizer + algorithm as
     `src/qa/_scoring.tokenize` / `lcs_ratio` so audit and generation
     agree on what "verbatim" means.

  2. Independent-solver verification for Llama/Qwen output (v2.1 plan §1).
     Routes through `src/generators/_verify.verify_question_with_independent_solver`
     when `verify_with_independent_solver=True` AND the generator is in
     {llama, qwen}. Disagreement → reject.
"""

import random
import re
from typing import Optional

import orjson
from loguru import logger
from pydantic import BaseModel, Field, field_validator, model_validator

from src.qa._scoring import lcs_ratio, tokenize

# ─── Question types from DB enum ─────────────────────────────────────────────

QUESTION_TYPES = {
    "multiple_choice",
    "multiple_select",
    "true_false",
    "matching",
    "short_answer",
    "scenario_based",
}

# How many options each question type expects
_OPTION_COUNTS: dict[str, tuple[int, int] | None] = {
    "multiple_choice": (4, 4),
    "multiple_select": (4, 6),
    "true_false": (2, 2),
    "matching": None,       # variable
    "short_answer": None,   # no options
    "scenario_based": None, # variable
}

# Valid option IDs
_VALID_OPTION_IDS = {"A", "B", "C", "D", "E", "F"}


# ─── Models ───────────────────────────────────────────────────────────────────

class QuestionOption(BaseModel):
    """A single answer option (e.g. A, B, C, D)."""

    id: str = Field(..., pattern=r"^[A-F]$")
    text: str = Field(..., min_length=1, max_length=500)


class GeneratedQuestion(BaseModel):
    """Validated output from an LLM question-generation call."""

    question_text: str = Field(..., min_length=10, max_length=1000)
    options: Optional[list[QuestionOption]] = None
    correct_answer: str = Field(..., min_length=1, max_length=100)
    correct_answer_text: Optional[str] = None
    explanation: str = Field(..., min_length=10, max_length=2000)
    tags: list[str] = Field(default_factory=list)

    @field_validator("tags", mode="before")
    @classmethod
    def coerce_tags(cls, v):
        if v is None:
            return []
        return v

    @model_validator(mode="after")
    def validate_options_for_type(self):
        """Validate at model level — type-specific checks are done in parse_llm_response."""
        if self.options is not None:
            # Ensure option IDs are unique
            ids = [o.id for o in self.options]
            if len(ids) != len(set(ids)):
                raise ValueError("Option IDs must be unique")
        return self

    def check_option_count(self, question_type: str) -> None:
        """Validate option count against question type. Raises ValueError."""
        bounds = _OPTION_COUNTS.get(question_type)
        if bounds is None:
            return
        lo, hi = bounds
        n = len(self.options) if self.options else 0
        if self.options is None and lo > 0:
            raise ValueError(
                f"{question_type} requires {lo}-{hi} options, got none"
            )
        if not (lo <= n <= hi):
            raise ValueError(
                f"{question_type} requires {lo}-{hi} options, got {n}"
            )

    def check_correct_answer(self) -> None:
        """Validate correct_answer is a valid option ID when options exist."""
        if self.options is None:
            return
        valid_ids = {o.id for o in self.options}
        # Support comma-separated IDs for multiple_select
        answer_ids = [a.strip() for a in self.correct_answer.split(",")]
        for aid in answer_ids:
            if aid not in valid_ids:
                raise ValueError(
                    f"correct_answer '{aid}' not in option IDs {valid_ids}"
                )


# ─── JSON extraction helpers ─────────────────────────────────────────────────

_FENCE_RE = re.compile(r"```(?:json)?\s*\n?(.*?)\n?\s*```", re.DOTALL)
_BRACE_RE = re.compile(r"\{.*\}", re.DOTALL)


def _extract_json(raw: str) -> Optional[dict]:
    """Three-tier JSON extraction from LLM output.

    1. Strip markdown code fences and try orjson.loads()
    2. Try orjson.loads() on the raw string
    3. Regex-extract first {...} block and try orjson.loads()

    Returns parsed dict or None.
    """
    # Tier 1: strip markdown fences
    fence_match = _FENCE_RE.search(raw)
    if fence_match:
        try:
            return orjson.loads(fence_match.group(1))
        except (orjson.JSONDecodeError, ValueError):
            pass

    # Tier 2: raw string
    try:
        return orjson.loads(raw)
    except (orjson.JSONDecodeError, ValueError):
        pass

    # Tier 3: regex extract first {...} block
    brace_match = _BRACE_RE.search(raw)
    if brace_match:
        try:
            return orjson.loads(brace_match.group(0))
        except (orjson.JSONDecodeError, ValueError):
            pass

    return None


# ─── Post-LLM rejection gates (v2.1 plan) ────────────────────────────────────

# LCS threshold for the verbatim-copy guard. Matches the A3 audit agent's
# fail bound (`_A3_FAIL_LCS = 0.6` in src/qa/agents/team_a_static.py) so the
# generator and the auditor agree on what counts as "verbatim".
_PARAPHRASE_LCS_THRESHOLD = 0.6


def _max_lcs_against_facts(
    question_text: str,
    correct_option_text: str,
    fact_texts: list[str],
) -> float:
    """Return max LCS ratio between (question + correct option) and any fact.

    Uses `src.qa._scoring.tokenize` + `lcs_ratio` so the metric matches the
    A3 FactEcho audit agent exactly. A return value > 0.6 means the answer
    leg is dominated by verbatim source-fact tokens — exactly what the
    PARAPHRASE RULE in the prompts is meant to prevent.

    Args:
        question_text: The LLM's question stem.
        correct_option_text: Concatenated text of the correct option(s). Use
            an empty string for short_answer (no options) — we still compare
            the question text against the source.
        fact_texts: Source fact strings. Empty/blank entries are skipped.

    Returns:
        Max LCS ratio in [0, 1]; 0.0 if there are no usable inputs.
    """
    target = tokenize(f"{question_text or ''} {correct_option_text or ''}")
    if not target:
        return 0.0

    best = 0.0
    for fact in fact_texts or []:
        if not fact:
            continue
        src_tokens = tokenize(fact)
        if not src_tokens:
            continue
        ratio = lcs_ratio(target, src_tokens)
        if ratio > best:
            best = ratio
    return best


def _correct_option_text(question: "GeneratedQuestion") -> str:
    """Return the concatenated text of the question's correct option(s).

    Multi-select keys are comma-separated (e.g. "A,C") — concatenate all
    matching option texts so the LCS check sees the full answer leg. Falls
    back to question.correct_answer_text if present, then to "".
    """
    if not question.options:
        return question.correct_answer_text or ""
    correct_ids = {a.strip().upper() for a in (question.correct_answer or "").split(",")}
    parts = [o.text for o in question.options if o.id.upper() in correct_ids]
    if parts:
        return " ".join(parts)
    return question.correct_answer_text or ""


# ─── Public API ───────────────────────────────────────────────────────────────


def parse_llm_response(
    raw: str,
    question_type: str,
    *,
    source_fact_texts: Optional[list[str]] = None,
    verify_with_independent_solver: bool = False,
    generator: Optional[str] = None,
) -> Optional[GeneratedQuestion]:
    """Parse and validate an LLM's JSON response into a GeneratedQuestion.

    Args:
        raw: Raw string output from the LLM.
        question_type: One of the QUESTION_TYPES values.
        source_fact_texts: List of source fact strings linked to the question.
            When provided, the LCS verbatim-copy guard runs after Pydantic
            validation (v2.1 plan §2). When None or empty, the guard is a no-op.
        verify_with_independent_solver: When True AND `generator` is in the
            verification set ({llama, qwen}), an independent solver is asked
            to re-answer the question. Disagreement → reject (returns None).
            Cheap models (claude/chatgpt/gemini) are never re-verified.
        generator: Short name of the generator that produced `raw` (e.g.
            "llama"). Required when verify_with_independent_solver=True.

    Returns:
        A validated GeneratedQuestion, or None if parsing/validation fails
        (including paraphrase-guard rejection or verifier disagreement).
    """
    if question_type not in QUESTION_TYPES:
        logger.error(f"Unknown question_type: {question_type}")
        return None

    data = _extract_json(raw)
    if data is None:
        logger.warning("Failed to extract JSON from LLM response")
        logger.debug(f"Raw response (first 500 chars): {raw[:500]}")
        return None

    try:
        question = GeneratedQuestion(**data)
    except Exception as e:
        logger.warning(f"Pydantic validation failed: {e}")
        logger.debug(f"Parsed data keys: {list(data.keys()) if isinstance(data, dict) else 'N/A'}")
        return None

    # Type-specific validation
    try:
        question.check_option_count(question_type)
        question.check_correct_answer()
    except ValueError as e:
        logger.warning(f"Type-specific validation failed for {question_type}: {e}")
        return None

    # Shuffle option order to prevent correct-answer position bias.
    # LLMs overwhelmingly place the correct answer in position A.
    if question.options and len(question.options) >= 2:
        question = _shuffle_options(question)

    # ─── Post-validation rejection gates ──────────────────────────────────

    # Paraphrase guard: reject questions that copy too many consecutive
    # tokens from any source fact (v2.1 §2).
    if source_fact_texts:
        correct_text = _correct_option_text(question)
        ratio = _max_lcs_against_facts(
            question.question_text, correct_text, source_fact_texts,
        )
        if ratio > _PARAPHRASE_LCS_THRESHOLD:
            logger.warning(
                "Paraphrase guard FAIL | lcs_ratio={:.3f} > {} | generator={} | "
                "question={!r}",
                ratio, _PARAPHRASE_LCS_THRESHOLD, generator,
                question.question_text[:120],
            )
            return None

    # Independent-solver verification (v2.1 §1). Only fires for Llama/Qwen.
    if verify_with_independent_solver and generator:
        # Local import to avoid a hard cycle: _verify imports the LLM client,
        # _schemas is itself imported at the top of every strategy module.
        from src.generators._verify import (
            GENERATORS_REQUIRING_VERIFICATION,
            verify_question_with_independent_solver,
        )

        if generator in GENERATORS_REQUIRING_VERIFICATION:
            options_payload = (
                [{"id": o.id, "text": o.text} for o in question.options]
                if question.options
                else []
            )
            is_valid, debug = verify_question_with_independent_solver(
                question_text=question.question_text,
                options=options_payload,
                correct_answer=question.correct_answer,
                source_facts=source_fact_texts or [],
                generator=generator,
            )
            if not is_valid:
                logger.warning(
                    "Independent verifier REJECT | verifier={} | chosen={} | "
                    "expected={} | generator={} | question={!r}",
                    debug.get("verifier_model"), debug.get("chosen"),
                    question.correct_answer, generator,
                    question.question_text[:120],
                )
                return None

    return question


def _shuffle_options(question: GeneratedQuestion) -> GeneratedQuestion:
    """Shuffle option order and remap correct_answer to the new position."""
    options = list(question.options)
    correct_ids = {a.strip() for a in question.correct_answer.split(",")}

    # Track which options are correct by their current text
    correct_texts = {o.text for o in options if o.id in correct_ids}

    # Shuffle the option objects
    random.shuffle(options)

    # Reassign IDs (A, B, C, ...) in new order
    labels = list("ABCDEF")
    new_correct_ids = []
    for i, opt in enumerate(options):
        new_id = labels[i]
        if opt.text in correct_texts:
            new_correct_ids.append(new_id)
        opt.id = new_id

    # Update the question
    question.options = options
    question.correct_answer = ",".join(sorted(new_correct_ids))
    if question.correct_answer_text is None and len(new_correct_ids) == 1:
        for o in options:
            if o.id == new_correct_ids[0]:
                question.correct_answer_text = o.text
                break

    return question
