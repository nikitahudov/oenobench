"""Tests for Phase 2g.15 cb_reserve pool (Team B).

Verifies:
1. quota_full path INSERTs to cb_reserve instead of dropping.
2. promote_from_reserve issues the correct UPDATE.
3. _count_strategy_rows_since excludes cb_reserve rows.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.generators import _closed_book_gate
from src.generators._closed_book_gate import GateResult


# ─── Shared gate-mock helpers (mirrors test_closed_book_gate.py) ─────────────

_OPTS = [
    {"id": "A", "text": "Nebbiolo"},
    {"id": "B", "text": "Barbera"},
    {"id": "C", "text": "Dolcetto"},
    {"id": "D", "text": "Sangiovese"},
]


def _patch_call(monkeypatch, selected: str, confidence: float) -> None:
    """Patch OpenRouter gate call to return a canned answer."""
    from dataclasses import dataclass, field
    import json

    @dataclass
    class _FakeMsg:
        content: str

    @dataclass
    class _FakeChoice:
        message: _FakeMsg

    @dataclass
    class _FakeUsage:
        prompt_tokens: int = 100
        completion_tokens: int = 30

    @dataclass
    class _FakeCompletion:
        choices: list
        usage: _FakeUsage = None
        model: str = field(default_factory=lambda: _closed_book_gate.GATE_MODEL)

        def __post_init__(self):
            if self.usage is None:
                self.usage = _FakeUsage()

    content = json.dumps({
        "selected": selected,
        "confidence": confidence,
        "reasoning": "test",
    })
    fake = _FakeCompletion(choices=[_FakeChoice(message=_FakeMsg(content=content))])

    def fake_call(client, prompt, model=None):
        return fake

    monkeypatch.setattr(_closed_book_gate, "_call_gate", fake_call)
    monkeypatch.setattr(_closed_book_gate, "_get_client", lambda: SimpleNamespace())


# ─── Test 1: quota_full inserts to cb_reserve, does not drop ─────────────────


def test_cb_quota_full_inserts_to_reserve_not_drops(monkeypatch):
    """When the cb quota is full, insert_question_gated must INSERT with
    status='cb_reserve' and return (question_id, gate) — not (None, gate).
    The question's tags must include 'closed_book_solvable'.
    """
    from src.generators import _question_db

    # Gate will flag this question (correct answer, high confidence).
    _patch_call(monkeypatch, selected="A", confidence=0.9)
    # Quota is at cap. Phase 2g.18: cap is now 4000 (10k × 0.40), was 2500.
    monkeypatch.setattr(_question_db, "count_closed_book_solvable", lambda: 4000)

    captured: dict = {}

    def fake_insert(question_data, generation_meta, fact_ids, source_ids, status="draft"):
        captured["status"] = status
        captured["tags"] = question_data.get("tags", [])
        return "uuid-reserved"

    monkeypatch.setattr(_question_db, "insert_question", fake_insert)

    q_uuid, gate = _question_db.insert_question_gated(
        question_data={
            "question_id": "TEST-RESERVE-001",
            "question_text": "Which grape makes Barolo?",
            "options": _OPTS,
            "correct_answer": "A",
            "difficulty": "1",
            "question_type": "multiple_choice",
            "domain": "wine_regions",
        },
        generation_meta={"generator": "test", "generation_method": "test"},
        fact_ids=[],
        source_ids=[],
    )

    # Must return a uuid, not None.
    assert q_uuid == "uuid-reserved", "quota_full must insert (reserve) not drop"
    # Must use cb_reserve status.
    assert captured["status"] == "cb_reserve", (
        f"expected status='cb_reserve', got {captured['status']!r}"
    )
    # Must tag the question.
    assert "closed_book_solvable" in captured["tags"], (
        "reserved question must carry the closed_book_solvable tag"
    )
    # Gate flags match expected state.
    assert gate.quota_full is True
    assert gate.passed is False


# ─── Test 2: promote_from_reserve issues correct UPDATE ──────────────────────


def test_promote_from_reserve_updates_status(monkeypatch):
    """promote_from_reserve(tag, 2) must issue an UPDATE that targets
    status='cb_reserve' rows carrying the given tag, capped at 2, and
    returns the rowcount.
    """
    from src.qa import _corpus

    captured: dict = {}

    class _FakeCursor:
        rowcount = 2

        def execute(self, sql, params):
            captured["sql"] = sql
            captured["params"] = params

    class _FakeConn:
        def cursor(self):
            return _FakeCursor()

        def commit(self):
            captured["committed"] = True

    monkeypatch.setattr(_corpus, "get_pg", lambda: _FakeConn())

    n = _corpus.promote_from_reserve(tag="audit_pilot_v13", count=2)

    assert n == 2, f"expected 2 promoted, got {n}"
    assert captured.get("committed"), "commit must be called after update"
    sql = captured["sql"]
    assert "cb_reserve" in sql, "UPDATE must filter status='cb_reserve'"
    assert "audit_pilot_v13" in captured["params"] or "audit_pilot_v13" == captured["params"][0], (
        "tag must appear in params"
    )
    assert 2 in captured["params"], "count/LIMIT must appear in params"


# ─── Test 3: _count_strategy_rows_since excludes cb_reserve ──────────────────


def test_count_rows_since_excludes_reserve(monkeypatch):
    """_count_strategy_rows_since must include the cb_reserve exclusion
    filter in its SQL so reserved questions are not counted toward the
    active corpus budget.
    """
    from src.qa import _corpus

    captured: dict = {}

    class _FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def execute(self, sql, params):
            captured["sql"] = sql
            captured["params"] = params

        def fetchone(self):
            return {"n": 5}

    class _FakeConn:
        def cursor(self):
            return _FakeCursor()

    monkeypatch.setattr(_corpus, "get_pg", lambda: _FakeConn())

    from datetime import datetime, timezone
    since = datetime(2026, 1, 1, tzinfo=timezone.utc)
    n = _corpus._count_strategy_rows_since("template_only", since)

    assert n == 5
    sql = captured["sql"]
    assert "cb_reserve" in sql, (
        f"_count_strategy_rows_since SQL must exclude cb_reserve; got: {sql!r}"
    )
    assert "status" in sql, "cb_reserve filter must reference status column"
