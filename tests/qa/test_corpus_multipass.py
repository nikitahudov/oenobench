"""Phase 2g.13 — Team C: tests for the multi-pass strategy loop.

Validates ``_execute_strategy_passes`` exit conditions and
``_resolve_max_build_passes`` env-var parsing.

The multi-pass loop was added because v10 build kept 53/120 (44%) — the
Phase 2g.12 pipeline-waste fixes worked, but legitimate quality refusals
(LLM "fact too vague", substantiveness filter, multi-fact bundle
exhaustion) leave strategies under-budget with no recovery. The loop
re-runs cell allocation with the remaining budget up to
``OENOBENCH_MAX_BUILD_PASSES`` iterations, exiting early on success or
no-progress (sampler ceiling reached).
"""

from __future__ import annotations

import random
from datetime import datetime

import pytest

from src.qa._corpus import (
    DEFAULT_MAX_BUILD_PASSES,
    MAX_BUILD_PASSES_ENV_VAR,
    _execute_strategy_passes,
    _resolve_max_build_passes,
)


@pytest.fixture(autouse=True)
def _seed_random():
    random.seed(0)


# ─── Env-var resolver ─────────────────────────────────────────────────────────


def test_resolve_max_build_passes_default(monkeypatch):
    """No env var → default of 1 (preserves Phase 2g.12 behaviour)."""
    monkeypatch.delenv(MAX_BUILD_PASSES_ENV_VAR, raising=False)
    assert _resolve_max_build_passes() == DEFAULT_MAX_BUILD_PASSES == 1


def test_resolve_max_build_passes_explicit(monkeypatch):
    """Env-var-set value is parsed and returned."""
    monkeypatch.setenv(MAX_BUILD_PASSES_ENV_VAR, "3")
    assert _resolve_max_build_passes() == 3


def test_resolve_max_build_passes_invalid_falls_back(monkeypatch):
    """Non-integer values fall back to default with a warning."""
    monkeypatch.setenv(MAX_BUILD_PASSES_ENV_VAR, "not-a-number")
    assert _resolve_max_build_passes() == DEFAULT_MAX_BUILD_PASSES


def test_resolve_max_build_passes_zero_floors_at_one(monkeypatch):
    """0 or negative values floor at 1 — never run no passes at all."""
    monkeypatch.setenv(MAX_BUILD_PASSES_ENV_VAR, "0")
    assert _resolve_max_build_passes() == 1
    monkeypatch.setenv(MAX_BUILD_PASSES_ENV_VAR, "-5")
    assert _resolve_max_build_passes() == 1


# ─── Multi-pass loop semantics ────────────────────────────────────────────────


class _FakeRunner:
    """Records calls and lets tests script per-pass yields."""

    def __init__(self, per_pass_yields: list[int]):
        # ``per_pass_yields[i]`` = total cumulative actual after pass i+1
        self.per_pass_yields = per_pass_yields
        self.cell_calls_per_pass: list[int] = []
        self._current_pass_calls = 0

    def run_generator(self, **kwargs):
        """Stub for _run_generator — counts cell invocations."""
        self._current_pass_calls += 1

    def count_rows(self, strategy, since):
        """Stub for _count_strategy_rows_since — returns scripted yield."""
        # Record this pass's cell-call count, advance the pass counter.
        self.cell_calls_per_pass.append(self._current_pass_calls)
        self._current_pass_calls = 0
        idx = len(self.cell_calls_per_pass) - 1
        if idx < len(self.per_pass_yields):
            return self.per_pass_yields[idx]
        # Past the scripted range — sampler stuck at the last yield.
        return self.per_pass_yields[-1] if self.per_pass_yields else 0


def _run_loop(yields, *, want=24, max_passes=3, strategy="fact_to_question"):
    runner = _FakeRunner(yields)
    actual = _execute_strategy_passes(
        strategy=strategy, module="fact_to_question", want=want,
        per_country_cap=0.30, workers=1,
        strategy_started=datetime(2026, 4, 29, 14, 0, 0),
        max_passes=max_passes,
        run_generator_fn=runner.run_generator,
        count_rows_fn=runner.count_rows,
    )
    return actual, runner


def test_single_pass_default_preserves_old_behaviour():
    """max_passes=1: runs once, returns whatever pass 1 produced."""
    actual, runner = _run_loop([10], want=24, max_passes=1)
    assert actual == 10
    assert len(runner.cell_calls_per_pass) == 1


def test_target_met_on_first_pass_skips_subsequent():
    """If pass 1 hits the target, no further passes run."""
    actual, runner = _run_loop([24], want=24, max_passes=3)
    assert actual == 24
    assert len(runner.cell_calls_per_pass) == 1, "pass 2/3 must not run when budget filled"


def test_target_met_partway_exits_early():
    """Pass 1=10, pass 2=24 (cumulative): exits after pass 2; pass 3 skipped."""
    actual, runner = _run_loop([10, 24], want=24, max_passes=3)
    assert actual == 24
    assert len(runner.cell_calls_per_pass) == 2


def test_runs_all_passes_when_target_unmet():
    """Pass 1=10, 2=15, 3=18: all three passes run; final actual=18 < want=24."""
    actual, runner = _run_loop([10, 15, 18], want=24, max_passes=3)
    assert actual == 18
    assert len(runner.cell_calls_per_pass) == 3


def test_no_progress_on_pass_two_exits_early():
    """Pass 1=10, pass 2=10 (no new rows): sampler ceiling — pass 3 skipped."""
    actual, runner = _run_loop([10, 10, 999], want=24, max_passes=3)
    assert actual == 10
    assert len(runner.cell_calls_per_pass) == 2, (
        "must stop after pass 2 produces zero new rows; pass 3 must NOT run"
    )


def test_no_progress_on_pass_one_does_not_exit():
    """Pass 1 producing 0 rows is normal (cold start) — pass 2 must still run.

    The no-progress guard only fires after pass_num > 1 because pass 1's
    result is the baseline; we need at least two data points to detect a
    plateau.
    """
    actual, runner = _run_loop([0, 5, 10], want=24, max_passes=3)
    assert actual == 10
    assert len(runner.cell_calls_per_pass) == 3


def test_smaller_remaining_budget_each_pass_shrinks_cell_count():
    """Each pass calls _build_cell_calls with the REMAINING budget,
    so the cell list shrinks as the strategy fills up.
    """
    actual, runner = _run_loop([10, 18, 22], want=24, max_passes=3)
    assert actual == 22
    # Pass 1: want=24, remaining=24 → 12 cells
    # Pass 2: want=24-10=14 remaining → 7 cells
    # Pass 3: want=24-18=6 remaining → 3 cells
    assert runner.cell_calls_per_pass == [12, 7, 3]


def test_max_passes_one_skips_all_no_progress_logic():
    """max_passes=1: even a 0-yield pass terminates normally."""
    actual, runner = _run_loop([0], want=24, max_passes=1)
    assert actual == 0
    assert len(runner.cell_calls_per_pass) == 1


def test_zero_want_short_circuits():
    """want=0 → no passes run, return 0 immediately."""
    actual, runner = _run_loop([], want=0, max_passes=3)
    assert actual == 0
    assert runner.cell_calls_per_pass == []


def test_target_exceeded_on_pass_one_returns_overshoot():
    """If a pass overshoots the target (rare but possible), report the actual."""
    actual, runner = _run_loop([26], want=24, max_passes=3)
    assert actual == 26
    assert len(runner.cell_calls_per_pass) == 1


# ─── Dynamic-loop limits (Phase 2g.13 follow-up) ──────────────────────────────


def test_resolve_max_build_passes_clamps_above_ceiling(monkeypatch):
    """Values > ceiling clamp down with a warning."""
    from src.qa._corpus import (
        MAX_BUILD_PASSES_CEILING,
        MAX_BUILD_PASSES_ENV_VAR,
    )
    monkeypatch.setenv(MAX_BUILD_PASSES_ENV_VAR, str(MAX_BUILD_PASSES_CEILING + 5))
    assert _resolve_max_build_passes() == MAX_BUILD_PASSES_CEILING


def test_resolve_wall_time_limit_default_zero(monkeypatch):
    from src.qa._corpus import (
        WALL_TIME_LIMIT_ENV_VAR,
        _resolve_wall_time_limit_s,
    )
    monkeypatch.delenv(WALL_TIME_LIMIT_ENV_VAR, raising=False)
    assert _resolve_wall_time_limit_s() == 0.0


def test_resolve_wall_time_limit_explicit(monkeypatch):
    from src.qa._corpus import (
        WALL_TIME_LIMIT_ENV_VAR,
        _resolve_wall_time_limit_s,
    )
    monkeypatch.setenv(WALL_TIME_LIMIT_ENV_VAR, "120.5")
    assert _resolve_wall_time_limit_s() == 120.5


def test_resolve_wall_time_limit_invalid_falls_back(monkeypatch):
    from src.qa._corpus import (
        WALL_TIME_LIMIT_ENV_VAR,
        _resolve_wall_time_limit_s,
    )
    monkeypatch.setenv(WALL_TIME_LIMIT_ENV_VAR, "NaN-value")
    assert _resolve_wall_time_limit_s() == 0.0


def test_resolve_min_yield_pct_default_zero(monkeypatch):
    from src.qa._corpus import MIN_YIELD_PCT_ENV_VAR, _resolve_min_yield_pct
    monkeypatch.delenv(MIN_YIELD_PCT_ENV_VAR, raising=False)
    assert _resolve_min_yield_pct() == 0.0


def test_resolve_min_yield_pct_explicit(monkeypatch):
    from src.qa._corpus import MIN_YIELD_PCT_ENV_VAR, _resolve_min_yield_pct
    monkeypatch.setenv(MIN_YIELD_PCT_ENV_VAR, "5.0")
    assert _resolve_min_yield_pct() == 5.0


def test_diminishing_returns_exit_after_two_low_passes(monkeypatch):
    """Two consecutive passes below min_yield_pct% → exit early.

    With min_yield_pct=10 and want=24:
      pass 1: 5 (no comparison since first pass)
      pass 2: 1 (4.2% of 24 → low yield, streak=1)
      pass 3: 1 (4.2% of 24 → low yield, streak=2 → exit)
    """
    from src.qa._corpus import MIN_YIELD_PCT_ENV_VAR
    monkeypatch.setenv(MIN_YIELD_PCT_ENV_VAR, "10.0")
    actual, runner = _run_loop([5, 6, 7, 999], want=24, max_passes=10)
    assert actual == 7  # 5 + 1 + 1
    assert len(runner.cell_calls_per_pass) == 3, (
        "must exit after pass 3 (2 consecutive low-yield passes)"
    )


def test_diminishing_returns_streak_resets_on_good_pass(monkeypatch):
    """Streak counter resets when a pass yields above the threshold."""
    from src.qa._corpus import MIN_YIELD_PCT_ENV_VAR
    monkeypatch.setenv(MIN_YIELD_PCT_ENV_VAR, "10.0")
    # Yields: 5, 6, 12, 13, 14 → pass2 low (streak=1), pass3 good (streak=0),
    # pass4 low (streak=1), pass5 low (streak=2 → exit) — but want=24 hit at pass4.
    actual, runner = _run_loop([5, 6, 12, 24], want=24, max_passes=10)
    assert actual == 24
    assert len(runner.cell_calls_per_pass) == 4

def test_diminishing_returns_disabled_when_pct_zero(monkeypatch):
    """min_yield_pct=0 disables the check; loop runs until other exit fires.

    Yields are CUMULATIVE in the fake runner, so [1, 2, 3, 4, 5] simulates
    one new question per pass. With min_yield_pct=0, the diminishing-
    returns guard is disabled, and the loop runs all 5 passes (no
    no-progress trigger because each pass produces 1 new row).
    """
    from src.qa._corpus import MIN_YIELD_PCT_ENV_VAR
    monkeypatch.setenv(MIN_YIELD_PCT_ENV_VAR, "0")
    actual, runner = _run_loop([1, 2, 3, 4, 5], want=24, max_passes=5)
    assert actual == 5
    assert len(runner.cell_calls_per_pass) == 5
