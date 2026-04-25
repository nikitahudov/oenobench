"""Tests for the v1.0 closed-book solvability gate.

The gate is the generation-time pre-screen for B2 leakage. Established by
the Phase 2g.5 prototype (see docs/PROCESS_LOG.md 2026-04-24): Sonnet 4.6
MC closed-book at conf>=0.7 → 94% recall, 77% precision on audit_pilot_v4.

These tests mock the OpenRouter call so we never touch the network.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from src.generators import _closed_book_gate
from src.generators._closed_book_gate import (
    CONFIDENCE_THRESHOLD,
    GateResult,
    screen_question,
)

# ─── Helpers ─────────────────────────────────────────────────────────────────


@dataclass
class _FakeMessage:
    content: str


@dataclass
class _FakeChoice:
    message: _FakeMessage


@dataclass
class _FakeUsage:
    prompt_tokens: int = 100
    completion_tokens: int = 30


@dataclass
class _FakeCompletion:
    choices: list
    usage: _FakeUsage = None
    model: str = "anthropic/claude-sonnet-4.6"

    def __post_init__(self):
        if self.usage is None:
            self.usage = _FakeUsage()


def _fake_response(selected: str, confidence: float, reasoning: str = "test"):
    """Build a fake OpenRouter completion object with the given JSON content."""
    content = (
        '{"selected": "' + selected + '",'
        ' "confidence": ' + str(confidence) + ','
        ' "reasoning": "' + reasoning + '"}'
    )
    return _FakeCompletion(choices=[_FakeChoice(message=_FakeMessage(content=content))])


def _patch_call(monkeypatch, selected: str, confidence: float):
    """Patch the underlying OpenRouter call to return a fake completion."""
    fake = _fake_response(selected, confidence)

    def fake_call(client, prompt):  # signature matches _call_gate
        return fake

    monkeypatch.setattr(_closed_book_gate, "_call_gate", fake_call)
    monkeypatch.setattr(
        _closed_book_gate, "_get_client", lambda: SimpleNamespace()
    )


_OPTS = [
    {"id": "A", "text": "Nebbiolo"},
    {"id": "B", "text": "Barbera"},
    {"id": "C", "text": "Dolcetto"},
    {"id": "D", "text": "Sangiovese"},
]


# ─── Skip-conditions (gate must NOT call the API) ────────────────────────────


def test_gate_skips_l4_questions(monkeypatch):
    """L4 questions must skip the gate entirely.

    Phase 2g.7 (2026-04-25) extended the gate to L3 after audit_pilot_v5
    showed 33% L3 closed-book leakage. L4 still skips — too low-volume
    to justify the API spend and historically near-zero leakage.
    """

    def explode(*_a, **_kw):
        raise AssertionError("Gate must not call API for L4 questions")

    monkeypatch.setattr(_closed_book_gate, "_call_gate", explode)
    result = screen_question("Q?", _OPTS, "A", "4", "multiple_choice")
    assert result.passed is True
    assert result.applied is False
    assert "skipped" in result.reason


def test_gate_now_runs_on_l3_questions(monkeypatch):
    """Phase 2g.7: L3 multiple-choice questions go through the gate."""
    _patch_call(monkeypatch, selected="A", confidence=0.85)
    result = screen_question("Q?", _OPTS, "A", "3", "multiple_choice")
    assert result.applied is True
    # 0.85 >= 0.6 (current threshold) → reject path
    assert result.passed is False
    assert result.matched_gold is True


def test_gate_skips_non_mc_questions(monkeypatch):
    def explode(*_a, **_kw):
        raise AssertionError("Gate must not call API for non-MC types")

    monkeypatch.setattr(_closed_book_gate, "_call_gate", explode)
    result = screen_question("Q?", _OPTS, "A", "1", "true_false")
    assert result.passed is True
    assert result.applied is False


def test_gate_skips_when_no_options(monkeypatch):
    """The MC gate cannot evaluate without options — pass through."""

    def explode(*_a, **_kw):
        raise AssertionError("Gate must not call API when options absent")

    monkeypatch.setattr(_closed_book_gate, "_call_gate", explode)
    result = screen_question("Q?", None, "A", "1", "multiple_choice")
    assert result.passed is True
    assert result.applied is False


# ─── Reject path ─────────────────────────────────────────────────────────────


def test_gate_rejects_when_correct_high_conf(monkeypatch):
    _patch_call(monkeypatch, selected="A", confidence=0.85)
    result = screen_question("Q?", _OPTS, "A", "1", "multiple_choice")
    assert result.passed is False
    assert result.applied is True
    assert result.matched_gold is True
    assert result.confidence == pytest.approx(0.85)
    assert result.selected == "A"


def test_gate_rejects_at_threshold(monkeypatch):
    """conf == threshold should reject (>= comparison)."""
    _patch_call(monkeypatch, selected="A", confidence=CONFIDENCE_THRESHOLD)
    result = screen_question("Q?", _OPTS, "A", "2", "multiple_choice")
    assert result.passed is False


# ─── Pass path ───────────────────────────────────────────────────────────────


def test_gate_passes_when_correct_low_conf(monkeypatch):
    """Right answer but low confidence → keep (gate uses conf>=threshold)."""
    _patch_call(monkeypatch, selected="A", confidence=0.4)
    result = screen_question("Q?", _OPTS, "A", "1", "multiple_choice")
    assert result.passed is True
    assert result.applied is True
    assert result.matched_gold is True


def test_gate_passes_when_wrong_high_conf(monkeypatch):
    """Wrong answer at high conf → keep (gate didn't actually solve it)."""
    _patch_call(monkeypatch, selected="B", confidence=0.95)
    result = screen_question("Q?", _OPTS, "A", "1", "multiple_choice")
    assert result.passed is True
    assert result.matched_gold is False


# ─── Fail-open semantics ─────────────────────────────────────────────────────


def test_gate_fails_open_on_api_error(monkeypatch):
    """A network/API error must NOT silently drop the question."""

    def boom(client, prompt):
        raise RuntimeError("simulated network error")

    monkeypatch.setattr(_closed_book_gate, "_call_gate", boom)
    monkeypatch.setattr(
        _closed_book_gate, "_get_client", lambda: SimpleNamespace()
    )
    result = screen_question("Q?", _OPTS, "A", "1", "multiple_choice")
    assert result.passed is True
    assert result.applied is True
    assert result.error == "simulated network error"
    assert "fail_open" in result.reason


def test_gate_fails_open_on_unparseable_response(monkeypatch):
    """Garbled JSON from the gate model must fail open, not crash."""
    bad = _FakeCompletion(
        choices=[_FakeChoice(message=_FakeMessage(content="not json at all"))]
    )

    def fake_call(client, prompt):
        return bad

    monkeypatch.setattr(_closed_book_gate, "_call_gate", fake_call)
    monkeypatch.setattr(
        _closed_book_gate, "_get_client", lambda: SimpleNamespace()
    )
    result = screen_question("Q?", _OPTS, "A", "1", "multiple_choice")
    assert result.passed is True
    assert result.applied is True
    assert result.error == "json_parse_failed"


# ─── Wrapper behaviour ───────────────────────────────────────────────────────


def test_insert_question_gated_relabels_when_quota_has_room(monkeypatch):
    """Phase 2g.6 contract: gate-flagged L1/L2 are relabeled (not dropped)
    when the corpus-wide closed_book_solvable quota still has room.
    """
    from src.generators import _question_db

    _patch_call(monkeypatch, selected="A", confidence=0.9)
    monkeypatch.setattr(_question_db, "count_closed_book_solvable", lambda: 0)

    captured = {}

    def fake_insert(question_data, generation_meta, fact_ids, source_ids):
        # Snapshot the (mutated) question_data the wrapper handed us.
        captured["question_data"] = question_data
        captured["generation_meta"] = generation_meta
        return "uuid-relabeled"

    monkeypatch.setattr(_question_db, "insert_question", fake_insert)

    q_uuid, gate = _question_db.insert_question_gated(
        question_data={
            "question_id": "TEST-001",
            "question_text": "Which grape is in Barolo?",
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

    # Insert WAS called (relabel path, not reject path).
    assert q_uuid == "uuid-relabeled"
    assert "question_data" in captured

    # Question was relabeled to L1 + tagged closed_book_solvable.
    qd = captured["question_data"]
    assert qd["difficulty"] == "1"
    assert "closed_book_solvable" in qd["tags"]

    # Gate verdict reflects the relabel routing.
    assert gate.passed is False
    assert gate.relabeled is True
    assert gate.quota_full is False


def test_insert_question_gated_records_gate_in_metadata(monkeypatch):
    """Whether passed or rejected, the verdict must land in raw_response['gate']."""
    from src.generators import _question_db

    _patch_call(monkeypatch, selected="B", confidence=0.95)  # wrong answer → pass

    captured = {}

    def fake_insert(question_data, generation_meta, fact_ids, source_ids):
        captured["meta"] = generation_meta
        return "fake-uuid"

    monkeypatch.setattr(_question_db, "insert_question", fake_insert)

    q_uuid, gate = _question_db.insert_question_gated(
        question_data={
            "question_id": "TEST-002",
            "question_text": "Which grape is in Barolo?",
            "options": _OPTS,
            "correct_answer": "A",
            "difficulty": "2",
            "question_type": "multiple_choice",
            "domain": "wine_regions",
        },
        generation_meta={"generator": "test", "generation_method": "test"},
        fact_ids=[],
        source_ids=[],
    )
    assert q_uuid == "fake-uuid"
    assert gate.passed is True
    gate_meta = captured["meta"]["raw_response"]["gate"]
    assert gate_meta["selected"] == "B"
    assert gate_meta["matched_gold"] is False
    assert gate_meta["model"] == "anthropic/claude-sonnet-4.6"


def test_insert_question_gated_passthrough_for_l4(monkeypatch):
    """L4 questions must skip the gate AND still insert.

    Phase 2g.7: gate now extends to L3, so this test pivots to L4 to
    cover the same skip-path-still-inserts contract.
    """
    from src.generators import _question_db

    def explode(*_a, **_kw):
        raise AssertionError("Gate must not call API for L4 questions")

    monkeypatch.setattr(_closed_book_gate, "_call_gate", explode)

    captured = {}

    def fake_insert(question_data, generation_meta, fact_ids, source_ids):
        captured["meta"] = generation_meta
        return "uuid-l4"

    monkeypatch.setattr(_question_db, "insert_question", fake_insert)

    q_uuid, gate = _question_db.insert_question_gated(
        question_data={
            "question_id": "TEST-003",
            "question_text": "Q?",
            "options": _OPTS,
            "correct_answer": "A",
            "difficulty": "4",
            "question_type": "multiple_choice",
            "domain": "wine_regions",
        },
        generation_meta={"generator": "test", "generation_method": "test"},
        fact_ids=[],
        source_ids=[],
    )
    assert q_uuid == "uuid-l4"
    assert gate.applied is False
    assert captured["meta"]["raw_response"]["gate"]["applied"] is False


def test_insert_question_gated_disable_flag(monkeypatch):
    """apply_gate=False must skip the gate entirely."""
    from src.generators import _question_db

    def explode(*_a, **_kw):
        raise AssertionError("Gate must not call API when apply_gate=False")

    monkeypatch.setattr(_closed_book_gate, "_call_gate", explode)
    monkeypatch.setattr(
        _question_db, "insert_question",
        lambda *a, **kw: "uuid-disabled",
    )

    q_uuid, gate = _question_db.insert_question_gated(
        question_data={
            "question_id": "TEST-004",
            "question_text": "Q?",
            "options": _OPTS,
            "correct_answer": "A",
            "difficulty": "1",
            "question_type": "multiple_choice",
            "domain": "wine_regions",
        },
        generation_meta={"generator": "test", "generation_method": "test"},
        fact_ids=[],
        source_ids=[],
        apply_gate=False,
    )
    assert q_uuid == "uuid-disabled"
    assert gate.applied is False
    assert gate.reason == "gate_disabled"


# ─── Phase 2g.6 quota / relabel routing ──────────────────────────────────────


def test_insert_question_gated_rejects_when_quota_full(monkeypatch):
    """When the closed_book_solvable quota is full (>= cap), gate-flagged
    questions must be DROPPED — `insert_question` must not run.
    """
    from src.generators import _question_db

    _patch_call(monkeypatch, selected="A", confidence=0.9)
    monkeypatch.setattr(_question_db, "count_closed_book_solvable", lambda: 2500)

    def db_explode(*_a, **_kw):
        raise AssertionError("insert_question must not run when quota is full")

    monkeypatch.setattr(_question_db, "insert_question", db_explode)

    q_uuid, gate = _question_db.insert_question_gated(
        question_data={
            "question_id": "TEST-QUOTA-FULL",
            "question_text": "Which grape is in Barolo?",
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
    assert q_uuid is None
    assert gate.passed is False
    assert gate.quota_full is True
    assert gate.relabeled is False


def test_insert_question_gated_does_not_double_tag(monkeypatch):
    """If `closed_book_solvable` is already in tags, the relabel path must
    NOT append a duplicate. Other tags must be preserved.
    """
    from src.generators import _question_db

    _patch_call(monkeypatch, selected="A", confidence=0.9)
    monkeypatch.setattr(_question_db, "count_closed_book_solvable", lambda: 0)

    captured = {}

    def fake_insert(question_data, generation_meta, fact_ids, source_ids):
        captured["question_data"] = question_data
        return "uuid-no-double-tag"

    monkeypatch.setattr(_question_db, "insert_question", fake_insert)

    q_uuid, gate = _question_db.insert_question_gated(
        question_data={
            "question_id": "TEST-NO-DUPE",
            "question_text": "Which grape is in Barolo?",
            "options": _OPTS,
            "correct_answer": "A",
            "difficulty": "1",
            "question_type": "multiple_choice",
            "domain": "wine_regions",
            "tags": ["italy", "closed_book_solvable", "docg"],
        },
        generation_meta={"generator": "test", "generation_method": "test"},
        fact_ids=[],
        source_ids=[],
    )
    assert q_uuid == "uuid-no-double-tag"
    assert gate.relabeled is True

    tags = captured["question_data"]["tags"]
    # Exactly one occurrence of the closed_book_solvable tag.
    assert tags.count("closed_book_solvable") == 1
    # Other tags preserved.
    assert "italy" in tags
    assert "docg" in tags


def test_insert_question_gated_preserves_other_tags_during_relabel(monkeypatch):
    """Pre-existing tags must be preserved (in order) and the
    closed_book_solvable tag appended at the end.
    """
    from src.generators import _question_db

    _patch_call(monkeypatch, selected="A", confidence=0.9)
    monkeypatch.setattr(_question_db, "count_closed_book_solvable", lambda: 0)

    captured = {}

    def fake_insert(question_data, generation_meta, fact_ids, source_ids):
        captured["question_data"] = question_data
        return "uuid-tags-preserved"

    monkeypatch.setattr(_question_db, "insert_question", fake_insert)

    q_uuid, gate = _question_db.insert_question_gated(
        question_data={
            "question_id": "TEST-TAGS-PRESERVED",
            "question_text": "Which grape is in Barolo?",
            "options": _OPTS,
            "correct_answer": "A",
            "difficulty": "1",
            "question_type": "multiple_choice",
            "domain": "wine_regions",
            "tags": ["italy", "barolo"],
        },
        generation_meta={"generator": "test", "generation_method": "test"},
        fact_ids=[],
        source_ids=[],
    )
    assert q_uuid == "uuid-tags-preserved"
    assert gate.relabeled is True
    assert captured["question_data"]["tags"] == ["italy", "barolo", "closed_book_solvable"]


# ─── Phase 2g.7 quota math + tunable threshold ───────────────────────────────


def test_quota_cap_with_explicit_target_size():
    """When a caller passes an explicit `target_size`, the cap is
    ceil(target × 0.25) — the correct per-corpus semantics. A 295-Q
    pilot must produce a 74-Q cap, not the 2500-Q global cap.
    """
    from src.generators._question_db import _closed_book_quota_cap

    # 295 × 0.25 = 73.75 → ceil = 74
    assert _closed_book_quota_cap(target_size=295) == 74
    # Spot-check a couple more sizes for the ceil() behaviour.
    assert _closed_book_quota_cap(target_size=100) == 25  # exact
    assert _closed_book_quota_cap(target_size=101) == 26  # 25.25 → ceil 26


def test_quota_cap_default_unchanged():
    """Backward compat: calling with no arg must still return 2500
    (= 10_000 × 0.25, the OVERALL_TARGET full-run cap). The orchestrator
    relies on this for the production 10k generation.
    """
    from src.generators import _question_db
    from src.generators._question_db import _closed_book_quota_cap

    # Defensive: clear any override leaked from an unrelated test.
    _question_db.set_corpus_target(None)
    try:
        assert _closed_book_quota_cap() == 2500
    finally:
        _question_db.set_corpus_target(None)


def test_threshold_parameter_respected(monkeypatch):
    """Per-call confidence_threshold override must change the reject decision.

    Same gate verdict (matched A at conf=0.55) — at threshold=0.7 the gate
    PASSES (0.55 < 0.7), at threshold=0.5 the gate REJECTS (0.55 >= 0.5).
    """
    _patch_call(monkeypatch, selected="A", confidence=0.55)

    high = screen_question("Q?", _OPTS, "A", "1", "multiple_choice", confidence_threshold=0.7)
    assert high.passed is True
    assert high.matched_gold is True
    assert high.confidence == pytest.approx(0.55)

    low = screen_question("Q?", _OPTS, "A", "1", "multiple_choice", confidence_threshold=0.5)
    assert low.passed is False
    assert low.matched_gold is True
    assert low.confidence == pytest.approx(0.55)
