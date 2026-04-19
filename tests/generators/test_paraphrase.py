"""Tests for the paraphrase / verbatim-copy guard in src.generators._schemas.

Covers:
- `_max_lcs_against_facts` returns > 0.6 when 8+ consecutive tokens are
  shared between the (question + correct option) and a source fact.
- `_max_lcs_against_facts` returns 0.0 for empty inputs.
- `parse_llm_response` rejects (returns None) when the LCS gate fails.
- `parse_llm_response` accepts when the source fact is truly paraphrased.
- `parse_llm_response` ignores the gate when no source_fact_texts are given.
"""

from __future__ import annotations

import orjson
import pytest

from src.generators._schemas import (
    _PARAPHRASE_LCS_THRESHOLD,
    _max_lcs_against_facts,
    parse_llm_response,
)


# ─── _max_lcs_against_facts ───────────────────────────────────────────────────


def test_max_lcs_returns_zero_for_empty_inputs():
    assert _max_lcs_against_facts("", "", []) == 0.0
    assert _max_lcs_against_facts("hello", "world", []) == 0.0
    assert _max_lcs_against_facts("", "", ["some fact text"]) == 0.0


def test_max_lcs_high_when_question_copies_fact_verbatim():
    """An 8+ consecutive-token overlap must drive the ratio above 0.6."""
    fact = "Barolo DOCG in Piedmont, Italy, must be made from 100% Nebbiolo grapes."
    # The question stem reuses 9 consecutive tokens verbatim.
    question = "Barolo DOCG in Piedmont Italy must be made from 100% Nebbiolo grapes — which grape?"
    correct = "Nebbiolo"
    ratio = _max_lcs_against_facts(question, correct, [fact])
    assert ratio > 0.6, f"Expected > 0.6, got {ratio}"


def test_max_lcs_low_for_paraphrased_question():
    """A genuine paraphrase should fall well below the threshold."""
    fact = "Barolo DOCG in Piedmont, Italy, must be made from 100% Nebbiolo grapes."
    question = "Which red grape variety is required for the production of Barolo?"
    correct = "Nebbiolo"
    ratio = _max_lcs_against_facts(question, correct, [fact])
    # Paraphrase should keep the verbatim-overlap token ratio low.
    assert ratio < 0.6


def test_max_lcs_picks_max_across_facts():
    """When multiple facts are linked, return the worst (highest) ratio."""
    facts = [
        "Sancerre is a Loire Valley appellation producing Sauvignon Blanc.",
        "Barolo DOCG in Piedmont must be made from 100% Nebbiolo.",
    ]
    # Verbatim from fact #2 only.
    question = "Barolo DOCG in Piedmont must be made from 100% Nebbiolo — which grape?"
    correct = "Nebbiolo"
    ratio = _max_lcs_against_facts(question, correct, facts)
    assert ratio > 0.6


# ─── parse_llm_response with paraphrase guard ─────────────────────────────────


def _build_llm_payload(question_text: str, correct_id: str = "A") -> str:
    """Create a JSON-encoded LLM payload with 4 options, one correct."""
    payload = {
        "question_text": question_text,
        "options": [
            {"id": "A", "text": "Nebbiolo"},
            {"id": "B", "text": "Sangiovese"},
            {"id": "C", "text": "Barbera"},
            {"id": "D", "text": "Dolcetto"},
        ],
        "correct_answer": correct_id,
        "correct_answer_text": "Nebbiolo",
        "explanation": "Barolo DOCG is made from 100% Nebbiolo, so the answer is A.",
        "tags": ["barolo", "nebbiolo"],
    }
    return orjson.dumps(payload).decode()


def test_parse_llm_response_rejects_verbatim_copy():
    """An 8+ consecutive-token overlap with the source fact must trigger rejection."""
    fact = "Barolo DOCG in Piedmont, Italy, must be made from 100% Nebbiolo grapes."
    # Question copies the source fact almost word-for-word.
    raw = _build_llm_payload(
        "Barolo DOCG in Piedmont Italy must be made from 100% Nebbiolo grapes — which grape?",
        correct_id="A",
    )
    result = parse_llm_response(
        raw,
        "multiple_choice",
        source_fact_texts=[fact],
        verify_with_independent_solver=False,
        generator="claude",
    )
    assert result is None


def test_parse_llm_response_accepts_paraphrase():
    """A genuinely paraphrased question passes the LCS gate."""
    fact = "Barolo DOCG in Piedmont, Italy, must be made from 100% Nebbiolo grapes."
    raw = _build_llm_payload(
        "Which red grape variety is required for production of the Barolo appellation?",
        correct_id="A",
    )
    result = parse_llm_response(
        raw,
        "multiple_choice",
        source_fact_texts=[fact],
        verify_with_independent_solver=False,
        generator="claude",
    )
    assert result is not None
    # Pydantic validation passed and option-shuffle ran (correct_answer may now
    # point to a different letter, but text remains "Nebbiolo").
    assert result.correct_answer_text == "Nebbiolo"


def test_parse_llm_response_no_facts_skips_guard():
    """When source_fact_texts is None, the LCS gate is a no-op."""
    raw = _build_llm_payload(
        "Barolo DOCG in Piedmont Italy must be made from 100% Nebbiolo grapes — which grape?",
        correct_id="A",
    )
    # No source_fact_texts → guard does not fire even on a verbatim copy.
    result = parse_llm_response(raw, "multiple_choice")
    assert result is not None


def test_paraphrase_threshold_constant_matches_audit():
    """Generator-side threshold must match the A3 audit agent (0.6)."""
    assert _PARAPHRASE_LCS_THRESHOLD == 0.6
