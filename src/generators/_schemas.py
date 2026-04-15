"""
OenoBench — Pydantic schemas for question generation.

Validates LLM JSON output before database insertion, with robust
parsing that handles common LLM output quirks (markdown fences,
extra text around JSON, etc.).
"""

import random
import re
from typing import Optional

import orjson
from loguru import logger
from pydantic import BaseModel, Field, field_validator, model_validator

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


# ─── Public API ───────────────────────────────────────────────────────────────

def parse_llm_response(raw: str, question_type: str) -> Optional[GeneratedQuestion]:
    """Parse and validate an LLM's JSON response into a GeneratedQuestion.

    Args:
        raw: Raw string output from the LLM.
        question_type: One of the QUESTION_TYPES values.

    Returns:
        A validated GeneratedQuestion, or None if parsing/validation fails.
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
