"""Tests for parse-failure 1-shot retry with stricter JSON-only prompt.

Phase 2g.15 (Team A): When `parse_llm_response` returns None on attempt 0,
the generator must fire a second LLM call whose prompt is prepended with the
strict JSON-only prefix, and must return the parsed result from attempt 1.

Tests cover fact_to_question and scenario_generator (two of the five
generators). The mock pattern mirrors test_closed_book_gate.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


# ─── Shared helpers ───────────────────────────────────────────────────────────

_STRICT_PREFIX = (
    "IMPORTANT: Respond with raw JSON only. Do NOT include markdown fences"
    " (no ```json), prose, or explanation. The first character of your"
    " response must be { and the last must be }.\n\n"
)

_VALID_JSON_QUESTION = """{
  "question_text": "What grape variety is used in Barolo DOCG?",
  "options": [
    {"id": "A", "text": "Nebbiolo"},
    {"id": "B", "text": "Barbera"},
    {"id": "C", "text": "Sangiovese"},
    {"id": "D", "text": "Dolcetto"}
  ],
  "correct_answer": "A",
  "correct_answer_text": "Nebbiolo",
  "explanation": "Barolo requires 100% Nebbiolo under DOCG rules.",
  "tags": ["barolo", "nebbiolo", "docg"]
}"""


@dataclass
class _FakeLLMResponse:
    """Mirrors src.generators._llm_client.LLMResponse."""
    content: str = ""
    parsed: dict | None = None
    model: str = "fake-model"
    input_tokens: int = 100
    output_tokens: int = 80
    latency_ms: int = 50
    success: bool = True
    error: str | None = None


def _bad_response():
    """Response that produces unparseable content (no valid JSON)."""
    return _FakeLLMResponse(content="not valid json at all", success=True)


def _good_response():
    """Response that produces a parseable question JSON."""
    return _FakeLLMResponse(content=_VALID_JSON_QUESTION, success=True)


# ─── fact_to_question retry tests ────────────────────────────────────────────


def test_fact_to_question_retry_fires_and_returns_parsed(monkeypatch):
    """fact_to_question must retry on parse failure and succeed on attempt 1.

    Mocks:
    - attempt 0: client.generate → bad JSON → parse fails
    - attempt 1: client.generate → valid JSON → parse succeeds

    Asserts:
    - generate() is called exactly twice
    - the retry call's prompt starts with the strict-JSON prefix
    - the final return value is the parsed result (not None)
    """
    import src.generators.fact_to_question as ftq

    call_log: list[str] = []

    def fake_generate(prompt, system="", model="", **kwargs):
        call_log.append(prompt)
        if len(call_log) == 1:
            return _bad_response()
        return _good_response()

    fake_client = MagicMock()
    fake_client.generate = fake_generate

    monkeypatch.setattr(ftq, "get_client", lambda: fake_client)

    # parse_llm_response must return None on bad content, dict on good.
    parse_results: list = [None, SimpleNamespace(
        question_text="What grape variety is used in Barolo DOCG?",
        options=[SimpleNamespace(id="A", text="Nebbiolo")],
        correct_answer="A",
        correct_answer_text="Nebbiolo",
        explanation="Barolo requires 100% Nebbiolo.",
        tags=["barolo"],
    )]

    def fake_parse(content, qtype, **kwargs):
        return parse_results.pop(0)

    monkeypatch.setattr(ftq, "parse_llm_response", fake_parse)

    fact = {"id": "fact-001", "fact_text": "Barolo DOCG requires 100% Nebbiolo.", "source_name": "test"}
    result = ftq._generate_one(
        fact=fact,
        domain="wine_regions",
        difficulty="2",
        cognitive_dim="recall",
        question_type="multiple_choice",
        generator="claude",
    )

    # Two generate calls must have been made.
    assert len(call_log) == 2, f"Expected 2 generate calls, got {len(call_log)}"

    # The second call must carry the strict prefix.
    assert call_log[1].startswith(_STRICT_PREFIX), (
        f"Retry prompt must start with strict-JSON prefix; got: {call_log[1][:80]!r}"
    )

    # The first call must NOT carry the strict prefix.
    assert not call_log[0].startswith(_STRICT_PREFIX), (
        "First attempt must not prepend the strict-JSON prefix"
    )

    # Final result must be the parsed dict (not None).
    assert result is not None, "Generator must return a result on the successful retry"
    assert result["parsed"].correct_answer == "A"


def test_fact_to_question_no_retry_when_first_attempt_succeeds(monkeypatch):
    """When attempt 0 parses successfully, generate() is called exactly once
    and the strict prefix is never used."""
    import src.generators.fact_to_question as ftq

    call_log: list[str] = []

    def fake_generate(prompt, system="", model="", **kwargs):
        call_log.append(prompt)
        return _good_response()

    fake_client = MagicMock()
    fake_client.generate = fake_generate
    monkeypatch.setattr(ftq, "get_client", lambda: fake_client)

    parsed_obj = SimpleNamespace(
        question_text="Q?",
        options=[],
        correct_answer="A",
        correct_answer_text="Nebbiolo",
        explanation="explanation",
        tags=[],
    )
    monkeypatch.setattr(ftq, "parse_llm_response", lambda *a, **kw: parsed_obj)

    fact = {"id": "fact-002", "fact_text": "Barolo DOCG requires 100% Nebbiolo.", "source_name": "test"}
    result = ftq._generate_one(
        fact=fact, domain="wine_regions", difficulty="2",
        cognitive_dim="recall", question_type="multiple_choice", generator="claude",
    )

    assert len(call_log) == 1, f"Expected 1 generate call, got {len(call_log)}"
    assert not call_log[0].startswith(_STRICT_PREFIX)
    assert result is not None


# ─── scenario_generator retry tests ──────────────────────────────────────────


def test_scenario_generator_retry_fires_and_returns_parsed(monkeypatch):
    """scenario_generator must retry on parse failure and succeed on attempt 1.

    Same mock structure as the fact_to_question test above.
    """
    import src.generators.scenario_generator as sg

    call_log: list[str] = []

    def fake_generate(prompt, system="", model="", **kwargs):
        call_log.append(prompt)
        if len(call_log) == 1:
            return _bad_response()
        return _good_response()

    fake_client = MagicMock()
    fake_client.generate = fake_generate
    monkeypatch.setattr(sg, "get_client", lambda: fake_client)

    parse_results: list = [None, SimpleNamespace(
        question_text="A winemaker in Barolo must use which grape?",
        options=[SimpleNamespace(id="A", text="Nebbiolo")],
        correct_answer="A",
        correct_answer_text="Nebbiolo",
        explanation="Barolo is 100% Nebbiolo.",
        tags=["scenario", "barolo"],
    )]

    def fake_parse(content, qtype, **kwargs):
        return parse_results.pop(0)

    monkeypatch.setattr(sg, "parse_llm_response", fake_parse)

    cluster = [
        {"id": "fact-003", "fact_text": "Barolo DOCG requires 100% Nebbiolo.", "source_name": "test", "subdomain": "italy_piedmont"},
        {"id": "fact-004", "fact_text": "Barolo must be aged at least 38 months.", "source_name": "test", "subdomain": "italy_piedmont"},
    ]
    result = sg._generate_one(
        cluster=cluster,
        domain="wine_regions",
        scenario_type="winemaking",
        generator="claude",
        labelled_difficulty="3",
    )

    assert len(call_log) == 2, f"Expected 2 generate calls, got {len(call_log)}"
    assert call_log[1].startswith(_STRICT_PREFIX), (
        f"Retry prompt must start with strict-JSON prefix; got: {call_log[1][:80]!r}"
    )
    assert not call_log[0].startswith(_STRICT_PREFIX)
    assert result is not None
    assert result["parsed"].correct_answer == "A"


def test_scenario_generator_returns_none_when_both_attempts_fail(monkeypatch):
    """When both attempts fail to parse, the generator must return None cleanly
    (no exception, no infinite loop)."""
    import src.generators.scenario_generator as sg

    call_log: list[str] = []

    def fake_generate(prompt, system="", model="", **kwargs):
        call_log.append(prompt)
        return _bad_response()

    fake_client = MagicMock()
    fake_client.generate = fake_generate
    monkeypatch.setattr(sg, "get_client", lambda: fake_client)
    monkeypatch.setattr(sg, "parse_llm_response", lambda *a, **kw: None)

    cluster = [
        {"id": "fact-005", "fact_text": "Barolo DOCG requires 100% Nebbiolo.", "source_name": "test", "subdomain": "italy_piedmont"},
    ]
    result = sg._generate_one(
        cluster=cluster,
        domain="wine_regions",
        scenario_type="winemaking",
        generator="claude",
        labelled_difficulty="3",
    )

    # Both attempts fired, result is None.
    assert len(call_log) == 2
    assert result is None
