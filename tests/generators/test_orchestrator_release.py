"""Phase 2j (release_v1) — tests for the --tag and --target plumbing.

The full-generation orchestrator (`src.generators.orchestrator generate-all`)
gained two flags so it could drive a non-uniform 6,500-question release run:

  * --target N      proportionally scales STRATEGY_TARGETS
  * --tag NAME      appended to every inserted question's `tags` array
                    via the OENOBENCH_BUILD_TAG env var read by
                    `_question_db.insert_question`

These tests cover both paths end-to-end without invoking any live LLM.
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from src.generators import _question_db
from src.generators._question_db import BUILD_TAG_ENV_VAR
from src.generators.orchestrator import (
    OVERALL_TARGET,
    STRATEGY_ORDER,
    STRATEGY_TARGETS,
    _scale_strategy_targets,
)


# ─── _scale_strategy_targets ─────────────────────────────────────────────────


def test_scale_targets_identity_at_full_target():
    """At target=OVERALL_TARGET the scaler is the identity."""
    out = _scale_strategy_targets(OVERALL_TARGET)
    assert out == STRATEGY_TARGETS


def test_scale_targets_release_v1_6500():
    """6500 → expected weighted mix matches the project plan ratios."""
    out = _scale_strategy_targets(6500)
    expected = {
        "fact_to_question": 2925,   # 4500 * 0.65
        "template": 650,            # 1000 * 0.65
        "comparative": 975,         # 1500 * 0.65
        "scenario_synthesis": 975,  # 1500 * 0.65
        "distractor_mining": 975,   # 1500 * 0.65
    }
    assert out == expected
    assert sum(out.values()) == 6500


def test_scale_targets_sums_to_target_with_drift():
    """Rounding drift lands on the largest strategy (fact_to_question)."""
    # 6501 forces non-integer scaling — totals must still match.
    out = _scale_strategy_targets(6501)
    assert sum(out.values()) == 6501
    # All strategies remain positive.
    for v in out.values():
        assert v >= 1


def test_scale_targets_rejects_nonpositive():
    import click

    with pytest.raises(click.BadParameter):
        _scale_strategy_targets(0)
    with pytest.raises(click.BadParameter):
        _scale_strategy_targets(-100)


def test_scale_targets_preserves_strategy_order_keys():
    """Every strategy key in STRATEGY_ORDER survives the scaling."""
    out = _scale_strategy_targets(6500)
    assert set(out.keys()) == set(STRATEGY_ORDER)


# ─── BUILD_TAG_ENV_VAR plumbing in insert_question ───────────────────────────


def test_insert_question_appends_build_tag_from_env(monkeypatch):
    """When OENOBENCH_BUILD_TAG is set, it lands in the inserted row's tags."""
    monkeypatch.setenv(BUILD_TAG_ENV_VAR, "release_v1")

    captured = {}

    class _FakeCursor:
        def execute(self, sql, params=None):
            # Capture the first INSERT (the questions row); ignore the
            # downstream metadata + facts inserts.
            if "INSERT INTO questions" in sql and "tags" not in captured:
                # tags is the last positional param in the insert (see
                # `_question_db.insert_question`).
                captured["tags"] = params[-1]
        def fetchone(self):
            return None
        def fetchall(self):
            return []
        def close(self):
            pass

    class _FakeConn:
        autocommit = False

        def cursor(self):
            return _FakeCursor()
        def commit(self):
            pass
        def rollback(self):
            pass

    fake = _FakeConn()
    with patch("src.generators._question_db.get_pg", return_value=fake):
        question_data = {
            "question_id": "WB-REG-9999-L2",
            "domain": "wine_regions",
            "subdomain": None,
            "question_type": "multiple_choice",
            "difficulty": "2",
            "cognitive_dim": "recall",
            "question_text": "test",
            "options": [{"id": "A", "text": "x"}],
            "correct_answer": "A",
            "correct_answer_text": "x",
            "explanation": "",
            "tags": ["existing_tag"],
        }
        generation_meta = {
            "generator": "claude",
            "generator_version": "1.0",
            "generation_method": "fact_to_question",
            "template_id": None,
            "llm_creativity": 0.7,
            "prompt_hash": "h",
            "raw_response": {"x": 1},
        }
        # We don't care about the return value — capture is what we assert.
        try:
            _question_db.insert_question(
                question_data, generation_meta, [], [],
            )
        except Exception:
            # The fake cursor doesn't fully simulate all paths; we just need
            # to verify the questions-row tags were captured.
            pass

    assert "tags" in captured, "questions INSERT was never executed"
    assert "release_v1" in captured["tags"]
    assert "existing_tag" in captured["tags"]


def test_insert_question_no_tag_env_leaves_tags_unchanged(monkeypatch):
    """When OENOBENCH_BUILD_TAG is unset, tags pass through unchanged."""
    monkeypatch.delenv(BUILD_TAG_ENV_VAR, raising=False)

    captured = {}

    class _FakeCursor:
        def execute(self, sql, params=None):
            if "INSERT INTO questions" in sql and "tags" not in captured:
                captured["tags"] = params[-1]
        def fetchone(self):
            return None
        def fetchall(self):
            return []
        def close(self):
            pass

    class _FakeConn:
        autocommit = False
        def cursor(self):
            return _FakeCursor()
        def commit(self):
            pass
        def rollback(self):
            pass

    fake = _FakeConn()
    with patch("src.generators._question_db.get_pg", return_value=fake):
        try:
            _question_db.insert_question(
                {
                    "question_id": "WB-REG-9998-L2",
                    "domain": "wine_regions",
                    "subdomain": None,
                    "question_type": "multiple_choice",
                    "difficulty": "2",
                    "cognitive_dim": "recall",
                    "question_text": "test",
                    "options": [{"id": "A", "text": "x"}],
                    "correct_answer": "A",
                    "correct_answer_text": "x",
                    "explanation": "",
                    "tags": ["only_tag"],
                },
                {
                    "generator": "claude",
                    "generator_version": "1.0",
                    "generation_method": "fact_to_question",
                    "template_id": None,
                    "llm_creativity": 0.7,
                    "prompt_hash": "h",
                    "raw_response": {},
                },
                [], [],
            )
        except Exception:
            pass

    assert "tags" in captured
    assert captured["tags"] == ["only_tag"]
