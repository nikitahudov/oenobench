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
from click.testing import CliRunner

from src.generators import _question_db, orchestrator
from src.generators._fact_sampler import DOMAIN_TARGETS
from src.generators._question_db import BUILD_TAG_ENV_VAR
from src.generators.orchestrator import (
    DOMAIN_TO_SCENARIO_TYPES,
    GENERATOR_TARGETS,
    OVERALL_TARGET,
    STRATEGY_ORDER,
    STRATEGY_TARGETS,
    _dispatch_llm_strategy,
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


# ─── Phase 2j — DOMAIN_TO_SCENARIO_TYPES + cell explosion ───────────────────


def test_domain_to_scenario_types_covers_all_domain_targets():
    """Every domain in DOMAIN_TARGETS must have at least one scenario type
    so _dispatch_llm_strategy("scenario_synthesis") never falls through to
    the defensive None fallback under normal operation.
    """
    assert set(DOMAIN_TO_SCENARIO_TYPES.keys()) == set(DOMAIN_TARGETS.keys()), (
        f"Mismatch: DOMAIN_TO_SCENARIO_TYPES keys {set(DOMAIN_TO_SCENARIO_TYPES.keys())} "
        f"vs DOMAIN_TARGETS keys {set(DOMAIN_TARGETS.keys())}"
    )
    for domain, types in DOMAIN_TO_SCENARIO_TYPES.items():
        assert isinstance(types, list) and types, (
            f"Domain {domain!r} has empty scenario-type list"
        )


def test_dispatch_llm_strategy_explodes_scenario_cells_across_types(monkeypatch):
    """For scenario_synthesis, each (domain, generator) cell must explode
    into len(DOMAIN_TO_SCENARIO_TYPES[domain]) sub-cells, one per type.

    Verified by recording every _run_strategy call (via monkeypatch) and
    asserting the (domain → set_of_scenario_types) shape matches the map.
    """
    calls: list[dict] = []

    def fake_run_strategy(module, **kwargs):
        calls.append({"module": module, **kwargs})
        return True

    monkeypatch.setattr(orchestrator, "_run_strategy", fake_run_strategy)

    # Ample remaining count so per_generator >> 0 in every domain.
    _dispatch_llm_strategy(
        strategy="scenario_synthesis",
        module="scenario_generator",
        total_remaining=10_000,
        existing_dgc={},
        dry_run=True,
        max_workers=1,
    )

    assert calls, "no cells were dispatched"
    # Every dispatched call must carry a scenario_type for the scenario strategy.
    for c in calls:
        assert c["scenario_type"] is not None, (
            f"scenario_synthesis cell missing scenario_type: {c}"
        )

    # Per-generator: each domain should appear with exactly the set of types
    # named in DOMAIN_TO_SCENARIO_TYPES[domain].
    n_generators = len(GENERATOR_TARGETS)
    per_generator_per_domain: dict[tuple[str, str], set[str]] = {}
    for c in calls:
        key = (c["generator"], c["domain"])
        per_generator_per_domain.setdefault(key, set()).add(c["scenario_type"])

    expected_total_cells = 0
    for generator in GENERATOR_TARGETS:
        for domain, types in DOMAIN_TO_SCENARIO_TYPES.items():
            observed = per_generator_per_domain.get((generator, domain))
            assert observed == set(types), (
                f"({generator}, {domain}) types mismatch: observed={observed}, "
                f"expected={set(types)}"
            )
            expected_total_cells += len(types)

    assert len(calls) == expected_total_cells, (
        f"cell count mismatch: dispatched={len(calls)}, "
        f"expected={expected_total_cells} "
        f"(= n_generators({n_generators}) × sum(len(types))="
        f"{sum(len(t) for t in DOMAIN_TO_SCENARIO_TYPES.values())})"
    )


def test_dispatch_llm_strategy_non_scenario_keeps_legacy_shape(monkeypatch):
    """Non-scenario strategies (e.g. fact_to_question) must NOT receive a
    scenario_type and must NOT explode into per-type sub-cells.
    """
    calls: list[dict] = []

    def fake_run_strategy(module, **kwargs):
        calls.append({"module": module, **kwargs})
        return True

    monkeypatch.setattr(orchestrator, "_run_strategy", fake_run_strategy)

    _dispatch_llm_strategy(
        strategy="fact_to_question",
        module="fact_to_question",
        total_remaining=5_000,
        existing_dgc={},
        dry_run=True,
        max_workers=1,
    )

    assert calls
    # No cell carries a scenario_type for non-scenario strategies.
    assert all(c["scenario_type"] is None for c in calls), (
        "non-scenario strategy must not receive scenario_type"
    )
    # Cell count = n_generators × n_domains (one per (g, d), no per-type explosion).
    assert len(calls) == len(GENERATOR_TARGETS) * len(DOMAIN_TARGETS), (
        f"unexpected cell count for non-scenario: {len(calls)}"
    )


# ─── Phase 2j — --strategies filter ─────────────────────────────────────────


def test_generate_all_strategies_filter_runs_only_requested(monkeypatch):
    """`--strategies scenario_synthesis,template` runs ONLY those two."""
    invoked: list[str] = []

    # Replace the per-strategy dispatchers with no-op recorders so we can
    # observe which strategies the orchestrator actually iterates.
    def fake_dispatch_llm(strategy, module, total_remaining, existing_dgc,
                         dry_run, max_workers=1, total_target=OVERALL_TARGET):
        invoked.append(strategy)

    def fake_dispatch_template(module, count, dry_run,
                              max_workers=1, total_target=OVERALL_TARGET):
        invoked.append("template")

    monkeypatch.setattr(orchestrator, "_dispatch_llm_strategy", fake_dispatch_llm)
    monkeypatch.setattr(orchestrator, "_dispatch_template", fake_dispatch_template)

    # Stub DB-touching helpers so the click command runs in-memory.
    monkeypatch.setattr(orchestrator, "_count_by_method", lambda tag=None: {})
    monkeypatch.setattr(orchestrator, "get_domain_generator_counts", lambda tag=None: {})
    monkeypatch.setattr(orchestrator, "_resolve_build_started_at",
                        lambda tag, resume: __import__("datetime").datetime.now(__import__("datetime").timezone.utc))
    monkeypatch.setattr(orchestrator, "set_corpus_target", lambda *_a, **_kw: None)

    # Limit max_passes to 1 so each strategy is dispatched exactly once.
    monkeypatch.setenv("OENOBENCH_MAX_GENERATE_PASSES", "1")

    runner = CliRunner()
    result = runner.invoke(
        orchestrator.generate_all,
        ["--strategies", "scenario_synthesis,template", "--dry-run"],
    )
    assert result.exit_code == 0, result.output

    # Only the two requested strategies were dispatched.
    assert set(invoked) == {"scenario_synthesis", "template"}, (
        f"unexpected dispatch set: {invoked}"
    )


def test_generate_all_strategies_filter_rejects_unknown():
    """An unknown strategy name must fail fast with a clear error."""
    runner = CliRunner()
    result = runner.invoke(
        orchestrator.generate_all,
        ["--strategies", "nope_not_a_strategy", "--dry-run"],
    )
    assert result.exit_code != 0
    assert "Unknown strategy" in result.output or "Invalid value" in result.output
