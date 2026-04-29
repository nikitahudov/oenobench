"""Tests for the v1.0 closed-book solvability gate.

The gate is the generation-time pre-screen for B2 leakage. Established by
the Phase 2g.5 prototype (see docs/PROCESS_LOG.md 2026-04-24): Sonnet 4.6
MC closed-book at conf>=0.7 → 94% recall, 77% precision on audit_pilot_v4.

These tests mock the OpenRouter call so we never touch the network.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field
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
    # Phase 2g.8 (2026-04-26): resolve GATE_MODEL at instantiation time
    # so this fixture follows whatever the module currently exposes
    # (default Opus 4.7; Sonnet under OENOBENCH_GATE_MODEL override).
    model: str = field(default_factory=lambda: _closed_book_gate.GATE_MODEL)

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

    # Lever B4 (2026-04-28): _call_gate now takes a model arg as well.
    # Default model=None keeps any pre-B4 callers working.
    def fake_call(client, prompt, model=None):  # signature matches _call_gate
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
    """true_false still skips — 2-option payload incompatible with the A/B/C/D prompt.

    Phase 2g.7 (2026-04-25) extended gate coverage to scenario_based but
    deliberately left true_false out: only 5 T/F questions on v5, and
    the gate prompt would need adapting to a 2-option payload first.
    """

    def explode(*_a, **_kw):
        raise AssertionError("Gate must not call API for non-MC types")

    monkeypatch.setattr(_closed_book_gate, "_call_gate", explode)
    result = screen_question("Q?", _OPTS, "A", "1", "true_false")
    assert result.passed is True
    assert result.applied is False


def test_gate_runs_on_scenario_based(monkeypatch):
    """scenario_based questions emit 4-option payloads — gate must run.

    Phase 2g.7 (2026-04-25): on audit_pilot_v5 the gate silently skipped
    all 69 scenario_based questions via the old type guard, so 19 of them
    leaked B2 closed-book solvability. Lifting the type guard is the
    structural fix Teams α + β both surfaced independently.
    """
    _patch_call(monkeypatch, selected="A", confidence=0.85)
    result = screen_question("Q?", _OPTS, "A", "2", "scenario_based")
    assert result.applied is True
    # 0.85 >= 0.6 threshold and matched gold → reject path
    assert result.passed is False
    assert result.matched_gold is True


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

    # Lever B4 (2026-04-28): _call_gate signature is (client, prompt, model).
    def boom(client, prompt, model=None):
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

    # Lever B4 (2026-04-28): _call_gate signature is (client, prompt, model).
    def fake_call(client, prompt, model=None):
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
    # Lever B4 (2026-04-28): the recorded model is now resolved per-difficulty.
    # This insert uses difficulty="2", so the gate records the L2-tier model.
    assert gate_meta["model"] == _closed_book_gate._resolve_gate_model("2")


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
    ceil(target × CLOSED_BOOK_QUOTA_FRACTION) — the correct per-corpus
    semantics. Phase 2g.14 lowered the fraction from 0.25 → 0.20.
    """
    import math

    from src.generators._closed_book_gate import CLOSED_BOOK_QUOTA_FRACTION
    from src.generators._question_db import _closed_book_quota_cap

    # Compute expectations from the live constant so future tweaks
    # don't break the test.
    assert _closed_book_quota_cap(target_size=295) == math.ceil(295 * CLOSED_BOOK_QUOTA_FRACTION)
    assert _closed_book_quota_cap(target_size=100) == math.ceil(100 * CLOSED_BOOK_QUOTA_FRACTION)
    assert _closed_book_quota_cap(target_size=101) == math.ceil(101 * CLOSED_BOOK_QUOTA_FRACTION)


def test_quota_cap_default_unchanged():
    """Backward compat: calling with no arg returns
    ceil(OVERALL_TARGET × CLOSED_BOOK_QUOTA_FRACTION) = the full-run cap.
    The orchestrator relies on this for the production 10k generation.
    """
    import math

    from src.generators import _question_db
    from src.generators._closed_book_gate import CLOSED_BOOK_QUOTA_FRACTION
    from src.generators._question_db import _closed_book_quota_cap

    # Defensive: clear any override leaked from an unrelated test.
    _question_db.set_corpus_target(None)
    try:
        expected = math.ceil(
            _question_db._OVERALL_TARGET_DEFAULT * CLOSED_BOOK_QUOTA_FRACTION
        )
        assert _closed_book_quota_cap() == expected
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


# ─── Phase 2g.8 gate-model upgrade (Sonnet 4.6 → Opus 4.7) ───────────────────


def test_gate_model_default_is_opus_4_7(monkeypatch):
    """Phase 2g.8 (2026-04-26): the default GATE_MODEL must be Opus 4.7
    when OENOBENCH_GATE_MODEL is unset. Audit pilots run on the stronger
    (5x more expensive) model so the closed-book gate matches the upper
    end of what the 5-judge audit panel can solve.
    """
    monkeypatch.delenv("OENOBENCH_GATE_MODEL", raising=False)
    # Lever B4 (2026-04-28) bumped GATE_VERSION to 2.4.x and tiered the
    # gate model. The L3 default still resolves to Opus 4.7, so the
    # backwards-compat `GATE_MODEL` symbol still equals Opus.
    monkeypatch.delenv("OENOBENCH_GATE_MODEL_L3", raising=False)
    importlib.reload(_closed_book_gate)
    try:
        assert _closed_book_gate.GATE_MODEL == "anthropic/claude-opus-4.7"
        assert _closed_book_gate.GATE_VERSION.startswith("2.4")
    finally:
        # Reload one more time so the module's GATE_MODEL is at its
        # default for any tests that run after this one in the same
        # process. (delenv above already cleared the override.)
        importlib.reload(_closed_book_gate)


def test_gate_model_overridable_via_env(monkeypatch):
    """OENOBENCH_GATE_MODEL must override the default at import time so
    the full 10k generation can opt back to Sonnet without a code change.
    """
    monkeypatch.setenv("OENOBENCH_GATE_MODEL", "anthropic/claude-sonnet-4.6")
    importlib.reload(_closed_book_gate)
    try:
        assert _closed_book_gate.GATE_MODEL == "anthropic/claude-sonnet-4.6"
    finally:
        # Restore the default so subsequent tests in the same process
        # see Opus 4.7 again. monkeypatch will undo the env var on
        # teardown; the reload here uses the cleared env.
        monkeypatch.delenv("OENOBENCH_GATE_MODEL", raising=False)
        importlib.reload(_closed_book_gate)
        assert _closed_book_gate.GATE_MODEL == "anthropic/claude-opus-4.7"


# ─── Phase 2g.9 OENOBENCH_CORPUS_TARGET subprocess fallback ──────────────────
#
# Audit #7 ran with a 600-Q target but the closed-book quota cap defaulted to
# 2500 in every strategy subprocess: `set_corpus_target()` mutates a module-
# global that does not survive `subprocess.run`. The fix exports an env var
# alongside the in-process override so child processes resolve the same cap.


def test_quota_cap_uses_env_var_when_override_unset(monkeypatch):
    """When the in-process override is None, the env var must be honoured.

    This is the audit-pilot subprocess case: the parent exports the env var
    before `subprocess.run`, the child boots with `_CORPUS_TARGET_OVERRIDE =
    None`, and `_resolve_default_target_size()` must read the env var rather
    than falling through to the 10k default.
    """
    from src.generators import _question_db
    from src.generators._question_db import _closed_book_quota_cap

    _question_db.set_corpus_target(None)  # ensure in-process override is clear
    monkeypatch.setenv("OENOBENCH_CORPUS_TARGET", "600")
    try:
        import math

        from src.generators._closed_book_gate import CLOSED_BOOK_QUOTA_FRACTION

        assert _closed_book_quota_cap() == math.ceil(600 * CLOSED_BOOK_QUOTA_FRACTION)
    finally:
        monkeypatch.delenv("OENOBENCH_CORPUS_TARGET", raising=False)


def test_in_process_override_wins_over_env_var(monkeypatch):
    """`set_corpus_target()` takes precedence over the env var so unit tests
    and in-process callers can pin a specific value regardless of what the
    surrounding shell exported."""
    from src.generators import _question_db
    from src.generators._question_db import _closed_book_quota_cap

    monkeypatch.setenv("OENOBENCH_CORPUS_TARGET", "9999")
    _question_db.set_corpus_target(400)
    try:
        import math

        from src.generators._closed_book_gate import CLOSED_BOOK_QUOTA_FRACTION

        # In-process 400; env-var 9999 must NOT be read.
        assert _closed_book_quota_cap() == math.ceil(400 * CLOSED_BOOK_QUOTA_FRACTION)
    finally:
        _question_db.set_corpus_target(None)
        monkeypatch.delenv("OENOBENCH_CORPUS_TARGET", raising=False)


def test_invalid_env_var_falls_through_to_default(monkeypatch):
    """A malformed env var (non-numeric, zero, negative) must NOT crash the
    insert path. It is logged and we fall through to OVERALL_TARGET / 10k.
    """
    import math

    from src.generators import _question_db
    from src.generators._closed_book_gate import CLOSED_BOOK_QUOTA_FRACTION
    from src.generators._question_db import _closed_book_quota_cap

    _question_db.set_corpus_target(None)
    expected = math.ceil(
        _question_db._OVERALL_TARGET_DEFAULT * CLOSED_BOOK_QUOTA_FRACTION
    )
    for bad in ("not-a-number", "0", "-50", ""):
        monkeypatch.setenv("OENOBENCH_CORPUS_TARGET", bad)
        try:
            assert _closed_book_quota_cap() == expected, f"bad value {bad!r} should fall through"
        finally:
            monkeypatch.delenv("OENOBENCH_CORPUS_TARGET", raising=False)


# ─── Phase 2g.9 hotfix — scope cb count by build-start timestamp ─────────────
#
# `count_closed_book_solvable()` queries the entire `questions` table; without
# scoping, every historical pilot's cb-tagged questions accrue toward the new
# build's cap. v8's first launch hit 427/50 immediately. The hotfix reads
# OENOBENCH_CORPUS_BUILD_SINCE and applies it as a `created_at >= since`
# filter when set; behaviour is unchanged when the var is unset/blank.


def test_resolve_default_build_since_returns_none_when_unset(monkeypatch):
    from src.generators._question_db import _resolve_default_build_since

    monkeypatch.delenv("OENOBENCH_CORPUS_BUILD_SINCE", raising=False)
    assert _resolve_default_build_since() is None


def test_resolve_default_build_since_returns_iso_when_set(monkeypatch):
    from src.generators._question_db import _resolve_default_build_since

    monkeypatch.setenv("OENOBENCH_CORPUS_BUILD_SINCE", "2026-04-27T22:00:00+00:00")
    assert _resolve_default_build_since() == "2026-04-27T22:00:00+00:00"


def test_resolve_default_build_since_treats_blank_as_none(monkeypatch):
    """Blank or whitespace-only env var must NOT crash and must NOT be
    interpreted as a literal `''` filter (which would match no rows)."""
    from src.generators._question_db import _resolve_default_build_since

    for blank in ("", "   ", "\n"):
        monkeypatch.setenv("OENOBENCH_CORPUS_BUILD_SINCE", blank)
        assert _resolve_default_build_since() is None, f"{blank!r} should resolve to None"


def test_count_closed_book_solvable_unscoped_when_since_is_none(monkeypatch):
    """Backwards compat: with no since arg and no env var, count globally."""
    from src.generators import _question_db

    monkeypatch.delenv("OENOBENCH_CORPUS_BUILD_SINCE", raising=False)
    captured: dict = {}

    class _FakeCursor:
        def execute(self, sql, params):
            captured["sql"] = sql
            captured["params"] = params
        def fetchone(self):
            return {"cnt": 999}

    class _FakeConn:
        def cursor(self):
            return _FakeCursor()

    monkeypatch.setattr(_question_db, "get_pg", lambda: _FakeConn())

    n = _question_db.count_closed_book_solvable()
    assert n == 999
    assert "created_at" not in captured["sql"], (
        "unscoped call should NOT include a created_at filter"
    )


def test_count_closed_book_solvable_scoped_when_since_present(monkeypatch):
    """When the env var is set, the SQL must include a `created_at >= since`
    filter and pass the timestamp as the second parameter."""
    from src.generators import _question_db

    monkeypatch.setenv("OENOBENCH_CORPUS_BUILD_SINCE", "2026-04-27T22:00:00+00:00")
    captured: dict = {}

    class _FakeCursor:
        def execute(self, sql, params):
            captured["sql"] = sql
            captured["params"] = params
        def fetchone(self):
            return {"cnt": 7}

    class _FakeConn:
        def cursor(self):
            return _FakeCursor()

    monkeypatch.setattr(_question_db, "get_pg", lambda: _FakeConn())

    n = _question_db.count_closed_book_solvable()
    assert n == 7
    assert "created_at >= " in captured["sql"], (
        f"scoped call must include created_at filter; got SQL: {captured['sql']!r}"
    )
    assert captured["params"][1] == "2026-04-27T22:00:00+00:00", (
        f"scoped call must pass the since timestamp; got params: {captured['params']!r}"
    )


def test_count_closed_book_solvable_explicit_since_overrides_env(monkeypatch):
    """An explicit `since` arg always takes precedence over the env var."""
    from src.generators import _question_db

    monkeypatch.setenv("OENOBENCH_CORPUS_BUILD_SINCE", "2099-01-01T00:00:00Z")
    captured: dict = {}

    class _FakeCursor:
        def execute(self, sql, params):
            captured["params"] = params
        def fetchone(self):
            return {"cnt": 1}

    class _FakeConn:
        def cursor(self):
            return _FakeCursor()

    monkeypatch.setattr(_question_db, "get_pg", lambda: _FakeConn())

    _question_db.count_closed_book_solvable(since="2026-04-27T22:00:00+00:00")
    assert captured["params"][1] == "2026-04-27T22:00:00+00:00"


# ─── Phase 2g.10 per-strategy closed-book budget ─────────────────────────────
#
# Audits #6/#7 ran with a single corpus-level cb cap. v8's prior cb-rates show
# 40-77% per strategy with no clear winner, but strategies run sequentially in
# `build_pilot_corpus`. The first one (template) reaches the cap and the late
# strategies (scenario_synthesis, distractor_mining) have all their cb-flagged
# questions DROPPED instead of relabeled — biasing the corpus toward early
# strategies. The fix: when `OENOBENCH_STRATEGY_TARGET` is set, evaluate the
# 25% cap per generation_method instead of corpus-wide.


def test_resolve_strategy_target_size_returns_none_when_unset(monkeypatch):
    from src.generators._question_db import _resolve_strategy_target_size

    monkeypatch.delenv("OENOBENCH_STRATEGY_TARGET", raising=False)
    assert _resolve_strategy_target_size() is None


def test_resolve_strategy_target_size_returns_int_when_set(monkeypatch):
    from src.generators._question_db import _resolve_strategy_target_size

    monkeypatch.setenv("OENOBENCH_STRATEGY_TARGET", "40")
    assert _resolve_strategy_target_size() == 40


def test_resolve_strategy_target_size_invalid_falls_through_to_none(monkeypatch):
    """Malformed env values must NOT crash the gate path; they degrade to None
    and the gate falls back to the corpus-level cap."""
    from src.generators._question_db import _resolve_strategy_target_size

    for bad in ("not-a-number", "0", "-50", ""):
        monkeypatch.setenv("OENOBENCH_STRATEGY_TARGET", bad)
        assert _resolve_strategy_target_size() is None, f"{bad!r} should resolve to None"


def test_count_closed_book_solvable_strategy_filter_uses_join(monkeypatch):
    """When `strategy` is passed, the SQL must JOIN generation_metadata and
    filter by `gm.generation_method = strategy`."""
    from src.generators import _question_db

    monkeypatch.delenv("OENOBENCH_CORPUS_BUILD_SINCE", raising=False)
    captured: dict = {}

    class _FakeCursor:
        def execute(self, sql, params):
            captured["sql"] = sql
            captured["params"] = params
        def fetchone(self):
            return {"cnt": 3}

    class _FakeConn:
        def cursor(self):
            return _FakeCursor()

    monkeypatch.setattr(_question_db, "get_pg", lambda: _FakeConn())

    n = _question_db.count_closed_book_solvable(strategy="scenario_synthesis")
    assert n == 3
    assert "JOIN generation_metadata" in captured["sql"]
    assert "gm.generation_method" in captured["sql"]
    # Strategy is the second positional param after the cb tag.
    assert captured["params"][1] == "scenario_synthesis"


def test_count_closed_book_solvable_strategy_filter_composes_with_since(monkeypatch):
    """Both filters must compose with AND when both are active."""
    from src.generators import _question_db

    monkeypatch.setenv("OENOBENCH_CORPUS_BUILD_SINCE", "2026-04-28T06:46:00+00:00")
    captured: dict = {}

    class _FakeCursor:
        def execute(self, sql, params):
            captured["sql"] = sql
            captured["params"] = params
        def fetchone(self):
            return {"cnt": 1}

    class _FakeConn:
        def cursor(self):
            return _FakeCursor()

    monkeypatch.setattr(_question_db, "get_pg", lambda: _FakeConn())

    _question_db.count_closed_book_solvable(strategy="comparative")
    assert "JOIN generation_metadata" in captured["sql"]
    assert "gm.generation_method = %s" in captured["sql"]
    assert "q.created_at >= %s::timestamptz" in captured["sql"]
    # Params order: cb_tag, strategy, since.
    assert captured["params"] == (
        "closed_book_solvable", "comparative", "2026-04-28T06:46:00+00:00",
    )


def test_insert_question_gated_uses_per_strategy_budget_when_env_set(monkeypatch):
    """With OENOBENCH_STRATEGY_TARGET=40, gate-flagged questions must be
    counted per generation_method, with the cap computed from
    CLOSED_BOOK_QUOTA_FRACTION (Phase 2g.14: ceil(40 × 0.20) = 8).
    """
    from src.generators import _question_db

    monkeypatch.setenv("OENOBENCH_STRATEGY_TARGET", "40")
    _patch_call(monkeypatch, selected="A", confidence=0.9)

    seen: dict = {"strategy_kwargs": []}

    def fake_count(since=None, strategy=None):
        seen["strategy_kwargs"].append(strategy)
        # Return 0 so the relabel path runs (room in the per-strategy budget).
        return 0

    monkeypatch.setattr(_question_db, "count_closed_book_solvable", fake_count)

    captured: dict = {}

    def fake_insert(question_data, generation_meta, fact_ids, source_ids):
        captured["meta"] = generation_meta
        return "uuid-per-strategy"

    monkeypatch.setattr(_question_db, "insert_question", fake_insert)

    q_uuid, gate = _question_db.insert_question_gated(
        question_data={
            "question_id": "TEST-PSTR-001",
            "question_text": "Which grape is in Barolo?",
            "options": _OPTS,
            "correct_answer": "A",
            "difficulty": "1",
            "question_type": "multiple_choice",
            "domain": "wine_regions",
        },
        generation_meta={"generator": "test", "generation_method": "scenario_synthesis"},
        fact_ids=[],
        source_ids=[],
    )

    assert q_uuid == "uuid-per-strategy"
    assert gate.relabeled is True
    # The count function must have been called with strategy="scenario_synthesis".
    assert seen["strategy_kwargs"] == ["scenario_synthesis"]


def test_insert_question_gated_per_strategy_quota_full_at_correct_cap(monkeypatch):
    """Cap = ceil(per_strategy × CLOSED_BOOK_QUOTA_FRACTION).
    Phase 2g.14: ceil(40 × 0.20) = 8. When the per-strategy count
    is at the cap, the gate must reject (quota_full)."""
    import math

    from src.generators import _question_db
    from src.generators._closed_book_gate import CLOSED_BOOK_QUOTA_FRACTION

    monkeypatch.setenv("OENOBENCH_STRATEGY_TARGET", "40")
    _patch_call(monkeypatch, selected="A", confidence=0.9)

    cap = math.ceil(40 * CLOSED_BOOK_QUOTA_FRACTION)
    # Mock returns the cap exactly — any further cb-flagged inserts must drop.
    monkeypatch.setattr(
        _question_db,
        "count_closed_book_solvable",
        lambda since=None, strategy=None: cap,
    )

    def db_explode(*_a, **_kw):
        raise AssertionError("insert_question must not run when per-strategy quota is full")

    monkeypatch.setattr(_question_db, "insert_question", db_explode)

    q_uuid, gate = _question_db.insert_question_gated(
        question_data={
            "question_id": "TEST-PSTR-FULL",
            "question_text": "Which grape is in Barolo?",
            "options": _OPTS,
            "correct_answer": "A",
            "difficulty": "1",
            "question_type": "multiple_choice",
            "domain": "wine_regions",
        },
        generation_meta={"generator": "test", "generation_method": "scenario_synthesis"},
        fact_ids=[],
        source_ids=[],
    )
    assert q_uuid is None
    assert gate.quota_full is True
    assert "strategy:scenario_synthesis" in gate.reason


def test_insert_question_gated_strategies_have_independent_budgets(monkeypatch):
    """Strategy A at cap must not affect Strategy B's budget. The count call
    must pass each caller's own generation_method, so the database-level filter
    keeps the counts separate."""
    from src.generators import _question_db

    import math

    from src.generators._closed_book_gate import CLOSED_BOOK_QUOTA_FRACTION

    monkeypatch.setenv("OENOBENCH_STRATEGY_TARGET", "40")
    _patch_call(monkeypatch, selected="A", confidence=0.9)

    cap = math.ceil(40 * CLOSED_BOOK_QUOTA_FRACTION)
    # Per-strategy counts: scenario_synthesis is full (=cap), distractor_mining has room (cap-2).
    counts = {"scenario_synthesis": cap, "distractor_mining": max(0, cap - 2)}

    def fake_count(since=None, strategy=None):
        return counts.get(strategy, 0)

    monkeypatch.setattr(_question_db, "count_closed_book_solvable", fake_count)
    monkeypatch.setattr(
        _question_db, "insert_question",
        lambda *_a, **_kw: "uuid-distractor",
    )

    # Scenario should be rejected (full).
    q1, g1 = _question_db.insert_question_gated(
        question_data={
            "question_id": "TEST-A",
            "question_text": "Q?", "options": _OPTS, "correct_answer": "A",
            "difficulty": "1", "question_type": "multiple_choice", "domain": "wine_regions",
        },
        generation_meta={"generator": "test", "generation_method": "scenario_synthesis"},
        fact_ids=[], source_ids=[],
    )
    assert q1 is None
    assert g1.quota_full is True

    # Distractor should be relabeled (independent budget at 3/10).
    q2, g2 = _question_db.insert_question_gated(
        question_data={
            "question_id": "TEST-B",
            "question_text": "Q?", "options": _OPTS, "correct_answer": "A",
            "difficulty": "1", "question_type": "multiple_choice", "domain": "wine_regions",
        },
        generation_meta={"generator": "test", "generation_method": "distractor_mining"},
        fact_ids=[], source_ids=[],
    )
    assert q2 == "uuid-distractor"
    assert g2.relabeled is True
    assert g2.quota_full is False


def test_insert_question_gated_falls_back_to_corpus_cap_when_env_unset(monkeypatch):
    """Without OENOBENCH_STRATEGY_TARGET set, the wrapper must use the corpus
    cap (existing v2.0 behaviour). count_closed_book_solvable must be called
    WITHOUT a strategy filter."""
    from src.generators import _question_db

    monkeypatch.delenv("OENOBENCH_STRATEGY_TARGET", raising=False)
    _patch_call(monkeypatch, selected="A", confidence=0.9)

    seen: dict = {"strategy_kwargs": []}

    def fake_count(since=None, strategy=None):
        seen["strategy_kwargs"].append(strategy)
        return 0

    monkeypatch.setattr(_question_db, "count_closed_book_solvable", fake_count)
    monkeypatch.setattr(_question_db, "insert_question", lambda *_a, **_kw: "uuid-corpus")

    q_uuid, gate = _question_db.insert_question_gated(
        question_data={
            "question_id": "TEST-FALLBACK",
            "question_text": "Q?", "options": _OPTS, "correct_answer": "A",
            "difficulty": "1", "question_type": "multiple_choice", "domain": "wine_regions",
        },
        generation_meta={"generator": "test", "generation_method": "scenario_synthesis"},
        fact_ids=[], source_ids=[],
    )
    assert q_uuid == "uuid-corpus"
    assert gate.relabeled is True
    # No strategy kwarg → corpus-level count (legacy path).
    assert seen["strategy_kwargs"] == [None]


def test_insert_question_gated_falls_back_when_generation_method_missing(monkeypatch):
    """If env var is set but generation_meta has no generation_method, the
    wrapper must NOT crash — it falls back to the corpus-level cap. Defensive
    against test fixtures or partial metadata."""
    from src.generators import _question_db

    monkeypatch.setenv("OENOBENCH_STRATEGY_TARGET", "40")
    _patch_call(monkeypatch, selected="A", confidence=0.9)

    seen: dict = {"strategy_kwargs": []}

    def fake_count(since=None, strategy=None):
        seen["strategy_kwargs"].append(strategy)
        return 0

    monkeypatch.setattr(_question_db, "count_closed_book_solvable", fake_count)
    monkeypatch.setattr(_question_db, "insert_question", lambda *_a, **_kw: "uuid-no-method")

    q_uuid, gate = _question_db.insert_question_gated(
        question_data={
            "question_id": "TEST-NO-METHOD",
            "question_text": "Q?", "options": _OPTS, "correct_answer": "A",
            "difficulty": "1", "question_type": "multiple_choice", "domain": "wine_regions",
        },
        generation_meta={"generator": "test"},  # no generation_method
        fact_ids=[], source_ids=[],
    )
    assert q_uuid == "uuid-no-method"
    # Falls back to corpus-level (strategy=None on the count call).
    assert seen["strategy_kwargs"] == [None]


# ─── Lever B4 — tier-aware closed-book gate model ────────────────────────────
#
# 2026-04-28: the gate model is now selected per question difficulty:
#   L1 → Haiku 4.5  (cheap, leakage near-zero on any model)
#   L2 → Sonnet 4.6 (balance)
#   L3 → Opus 4.7   (residual leakage lives here — 33% in v5 at threshold 0.6)
#
# Override hierarchy: per-tier env > global env > module default.

_PER_TIER_ENV_VARS = (
    "OENOBENCH_GATE_MODEL",
    "OENOBENCH_GATE_MODEL_L1",
    "OENOBENCH_GATE_MODEL_L2",
    "OENOBENCH_GATE_MODEL_L3",
)


def _clear_gate_model_env(monkeypatch):
    for var in _PER_TIER_ENV_VARS:
        monkeypatch.delenv(var, raising=False)


def test_gate_model_default_l1_is_haiku(monkeypatch):
    """With no env overrides, L1 questions resolve to Haiku 4.5."""
    _clear_gate_model_env(monkeypatch)
    assert (
        _closed_book_gate._resolve_gate_model("1")
        == "anthropic/claude-haiku-4.5"
    )


def test_gate_model_default_l2_is_sonnet(monkeypatch):
    """With no env overrides, L2 questions resolve to Sonnet 4.6."""
    _clear_gate_model_env(monkeypatch)
    assert (
        _closed_book_gate._resolve_gate_model("2")
        == "anthropic/claude-sonnet-4.6"
    )


def test_gate_model_default_l3_is_opus(monkeypatch):
    """With no env overrides, L3 questions resolve to Opus 4.7."""
    _clear_gate_model_env(monkeypatch)
    assert (
        _closed_book_gate._resolve_gate_model("3")
        == "anthropic/claude-opus-4.7"
    )


def test_gate_model_l1_env_override(monkeypatch):
    """OENOBENCH_GATE_MODEL_L1 must be returned for L1 questions verbatim."""
    _clear_gate_model_env(monkeypatch)
    monkeypatch.setenv("OENOBENCH_GATE_MODEL_L1", "anthropic/claude-test-l1")
    assert (
        _closed_book_gate._resolve_gate_model("1") == "anthropic/claude-test-l1"
    )
    # Other tiers untouched.
    assert (
        _closed_book_gate._resolve_gate_model("2") == "anthropic/claude-sonnet-4.6"
    )
    assert (
        _closed_book_gate._resolve_gate_model("3") == "anthropic/claude-opus-4.7"
    )


def test_gate_model_l2_env_override(monkeypatch):
    """OENOBENCH_GATE_MODEL_L2 must be returned for L2 questions verbatim."""
    _clear_gate_model_env(monkeypatch)
    monkeypatch.setenv("OENOBENCH_GATE_MODEL_L2", "anthropic/claude-test-l2")
    assert (
        _closed_book_gate._resolve_gate_model("2") == "anthropic/claude-test-l2"
    )
    assert (
        _closed_book_gate._resolve_gate_model("1")
        == "anthropic/claude-haiku-4.5"
    )
    assert (
        _closed_book_gate._resolve_gate_model("3") == "anthropic/claude-opus-4.7"
    )


def test_gate_model_l3_env_override(monkeypatch):
    """OENOBENCH_GATE_MODEL_L3 must be returned for L3 questions verbatim."""
    _clear_gate_model_env(monkeypatch)
    monkeypatch.setenv("OENOBENCH_GATE_MODEL_L3", "anthropic/claude-test-l3")
    assert (
        _closed_book_gate._resolve_gate_model("3") == "anthropic/claude-test-l3"
    )
    assert (
        _closed_book_gate._resolve_gate_model("1")
        == "anthropic/claude-haiku-4.5"
    )
    assert (
        _closed_book_gate._resolve_gate_model("2") == "anthropic/claude-sonnet-4.6"
    )


def test_gate_model_global_env_var_overrides_all_tiers(monkeypatch):
    """OENOBENCH_GATE_MODEL applies to all three tiers — keeps the v8 audit
    pilot harness (`scripts/run_audit_pilot_v8_build.sh` exports
    OENOBENCH_GATE_MODEL=anthropic/claude-sonnet-4.6) working byte-for-byte.
    """
    _clear_gate_model_env(monkeypatch)
    monkeypatch.setenv("OENOBENCH_GATE_MODEL", "anthropic/claude-sonnet-4.6")
    for diff in ("1", "2", "3"):
        assert (
            _closed_book_gate._resolve_gate_model(diff)
            == "anthropic/claude-sonnet-4.6"
        ), f"global override must apply to L{diff}"


def test_gate_model_per_tier_override_beats_global(monkeypatch):
    """Per-tier env vars must win over the global override."""
    _clear_gate_model_env(monkeypatch)
    monkeypatch.setenv("OENOBENCH_GATE_MODEL", "anthropic/global-X")
    monkeypatch.setenv("OENOBENCH_GATE_MODEL_L1", "anthropic/per-tier-Y")
    assert _closed_book_gate._resolve_gate_model("1") == "anthropic/per-tier-Y"
    # L2 / L3 fall through to the global override.
    assert _closed_book_gate._resolve_gate_model("2") == "anthropic/global-X"
    assert _closed_book_gate._resolve_gate_model("3") == "anthropic/global-X"


def test_gate_model_invalid_difficulty_falls_back_to_l3_default(monkeypatch):
    """Defensive fallback: any difficulty outside {1,2,3} resolves to L3
    (Opus by default). Covers garbage strings, None, floats outside range."""
    _clear_gate_model_env(monkeypatch)
    for bad in ("99", "0", "4", None, "not-a-number", "", "1.5"):
        assert (
            _closed_book_gate._resolve_gate_model(bad)
            == "anthropic/claude-opus-4.7"
        ), f"difficulty={bad!r} should fall back to L3 default"


def test_screen_question_uses_l1_model_for_l1_question(monkeypatch):
    """End-to-end: an L1 MC question must dispatch with the L1-tier model.

    Captures the `model` arg passed to `_call_gate` and asserts it matches
    the L1 default (Haiku) when no env overrides are set. Also verifies
    `GateResult.model` records the actually-used model.
    """
    _clear_gate_model_env(monkeypatch)
    captured: dict = {}
    fake = _fake_response(selected="A", confidence=0.85)

    def capturing_call(client, prompt, model):
        captured["model"] = model
        return fake

    monkeypatch.setattr(_closed_book_gate, "_call_gate", capturing_call)
    monkeypatch.setattr(
        _closed_book_gate, "_get_client", lambda: SimpleNamespace()
    )
    result = screen_question("Q?", _OPTS, "A", "1", "multiple_choice")
    assert captured["model"] == "anthropic/claude-haiku-4.5"
    assert result.model == "anthropic/claude-haiku-4.5"
    assert result.applied is True


def test_screen_question_uses_l3_model_for_l3_question(monkeypatch):
    """End-to-end: an L3 MC question must dispatch with the L3-tier model
    (Opus 4.7) when no env overrides are set."""
    _clear_gate_model_env(monkeypatch)
    captured: dict = {}
    fake = _fake_response(selected="A", confidence=0.85)

    def capturing_call(client, prompt, model):
        captured["model"] = model
        return fake

    monkeypatch.setattr(_closed_book_gate, "_call_gate", capturing_call)
    monkeypatch.setattr(
        _closed_book_gate, "_get_client", lambda: SimpleNamespace()
    )
    result = screen_question("Q?", _OPTS, "A", "3", "multiple_choice")
    assert captured["model"] == "anthropic/claude-opus-4.7"
    assert result.model == "anthropic/claude-opus-4.7"
    assert result.applied is True


def test_gate_version_bumped():
    """B4 bumps GATE_VERSION to 2.4.x for downstream cache invalidation."""
    assert _closed_book_gate.GATE_VERSION.startswith("2.4")
