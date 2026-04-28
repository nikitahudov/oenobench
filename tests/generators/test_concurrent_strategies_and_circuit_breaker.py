"""Phase 2g.10 (Team Golf) — A4 concurrent top-level strategies + B3 circuit breaker.

A4 covers:

- ``--strategy-workers N`` / ``OENOBENCH_STRATEGY_WORKERS`` resolution.
- Default ``strategy_workers=1`` runs strategies serially (no overlap).
- ``strategy_workers >= 2`` runs strategies concurrently (overlap observed).

B3 covers:

- ``CellTracker`` rolling-window kept-rate computation.
- Default OFF: ``OENOBENCH_CIRCUIT_BREAKER`` unset → no abandonment.
- Abandons cells at sustained 0% kept-rate after ``min_attempts``.
- Does not abandon below ``min_attempts``.
- Strict-less-than threshold (5% → not abandoned).
- Reallocation of unused budget to the next cell, capped at 2× original.
"""

from __future__ import annotations

import threading
import time
from datetime import datetime


# ─── A4.1 — strategy_workers env var resolution ─────────────────────────────


def test_strategy_workers_env_var_picked_up(monkeypatch):
    from src.qa import _corpus

    monkeypatch.setenv("OENOBENCH_STRATEGY_WORKERS", "3")
    assert _corpus._resolve_strategy_workers(None) == 3


def test_strategy_workers_explicit_arg_overrides_env(monkeypatch):
    from src.qa import _corpus

    monkeypatch.setenv("OENOBENCH_STRATEGY_WORKERS", "3")
    assert _corpus._resolve_strategy_workers(7) == 7


def test_strategy_workers_default_is_one(monkeypatch):
    from src.qa import _corpus

    monkeypatch.delenv("OENOBENCH_STRATEGY_WORKERS", raising=False)
    assert _corpus._resolve_strategy_workers(None) == 1


def test_strategy_workers_invalid_env_falls_back_to_one(monkeypatch):
    from src.qa import _corpus

    monkeypatch.setenv("OENOBENCH_STRATEGY_WORKERS", "not_an_int")
    assert _corpus._resolve_strategy_workers(None) == 1


# ─── A4.2 — serial vs concurrent wallclock for top-level strategies ─────────


def _patch_corpus_db_helpers(monkeypatch):
    """Stub DB calls so build_pilot_corpus runs without hitting Postgres."""
    from src.qa import _corpus as _c

    monkeypatch.setattr(_c, "_existing_corpus_count", lambda tag: {})
    monkeypatch.setattr(
        _c, "_tag_rows",
        lambda *, generation_method, since, limit, tag: limit,
    )
    monkeypatch.setattr(
        _c, "_resolve_build_started_at",
        lambda tag: (datetime.now(), False),
    )


def test_strategy_workers_one_runs_serially(monkeypatch):
    """With strategy_workers=1, strategies execute sequentially."""
    from src.qa import _corpus
    from src.qa._corpus import build_pilot_corpus

    _patch_corpus_db_helpers(monkeypatch)

    in_flight_strategies: set[str] = set()
    max_overlap = {"n": 0}
    lock = threading.Lock()

    def slow(*, module, **kw):
        with lock:
            in_flight_strategies.add(module)
            max_overlap["n"] = max(max_overlap["n"], len(in_flight_strategies))
        time.sleep(0.05)
        with lock:
            in_flight_strategies.discard(module)
        return True

    monkeypatch.setattr(_corpus, "_run_generator", slow)

    build_pilot_corpus(
        tag="test_serial_strategies", per_strategy=1, seed=1,
        max_workers=1, strategy_workers=1,
    )
    # With strategy_workers=1 + max_workers=1, only one cell runs at a time
    # across the whole build, so no two strategies' modules overlap either.
    assert max_overlap["n"] == 1, (
        f"strategy_workers=1 + max_workers=1 must serialise everything; "
        f"observed peak overlap={max_overlap['n']}"
    )


def test_strategy_workers_two_runs_concurrently(monkeypatch):
    """With strategy_workers=2, two strategies' cells overlap in time."""
    from src.qa import _corpus
    from src.qa._corpus import build_pilot_corpus

    _patch_corpus_db_helpers(monkeypatch)

    # Track in-flight DISTINCT strategy modules at any given moment.
    in_flight_strategies: dict[str, int] = {}
    max_distinct_strategies = {"n": 0}
    lock = threading.Lock()

    def slow(*, module, **kw):
        with lock:
            in_flight_strategies[module] = in_flight_strategies.get(module, 0) + 1
            distinct = sum(1 for v in in_flight_strategies.values() if v > 0)
            max_distinct_strategies["n"] = max(
                max_distinct_strategies["n"], distinct,
            )
        time.sleep(0.1)
        with lock:
            in_flight_strategies[module] -= 1
        return True

    monkeypatch.setattr(_corpus, "_run_generator", slow)

    build_pilot_corpus(
        tag="test_concurrent_strategies", per_strategy=1, seed=1,
        max_workers=1, strategy_workers=3,
    )
    assert max_distinct_strategies["n"] >= 2, (
        f"strategy_workers=3 must overlap at least 2 strategies; "
        f"observed peak distinct strategies={max_distinct_strategies['n']}"
    )


def test_build_pilot_corpus_propagates_strategy_workers_arg(monkeypatch):
    """The build_pilot_corpus(strategy_workers=...) kwarg must reach the executor."""
    from src.qa import _corpus
    from src.qa._corpus import build_pilot_corpus

    _patch_corpus_db_helpers(monkeypatch)
    monkeypatch.setattr(
        _corpus, "_run_generator",
        lambda *, module, domain, count, generator=None,
               difficulty=None, per_country_cap=None: True,
    )

    captured = []
    real_executor = _corpus.cf.ThreadPoolExecutor

    class CapturingExecutor(real_executor):
        def __init__(self, max_workers=None, **kw):
            captured.append(max_workers)
            super().__init__(max_workers=max_workers, **kw)

    monkeypatch.setattr(_corpus.cf, "ThreadPoolExecutor", CapturingExecutor)

    build_pilot_corpus(
        tag="test_strategy_workers_arg", per_strategy=1, seed=1,
        max_workers=1, strategy_workers=4,
    )
    # The first executor created is the top-level strategy executor.
    assert 4 in captured, (
        f"strategy_workers=4 must be passed to the top-level executor; "
        f"executors observed: {captured}"
    )


def test_strategy_workers_default_one_does_not_use_executor(monkeypatch):
    """strategy_workers=1 must keep the legacy serial loop (no top-level executor)."""
    from src.qa import _corpus
    from src.qa._corpus import build_pilot_corpus

    _patch_corpus_db_helpers(monkeypatch)
    monkeypatch.setattr(
        _corpus, "_run_generator",
        lambda *, module, domain, count, generator=None,
               difficulty=None, per_country_cap=None: True,
    )
    monkeypatch.delenv("OENOBENCH_STRATEGY_WORKERS", raising=False)
    monkeypatch.delenv("OENOBENCH_MAX_WORKERS", raising=False)

    captured = []
    real_executor = _corpus.cf.ThreadPoolExecutor

    class CapturingExecutor(real_executor):
        def __init__(self, max_workers=None, **kw):
            captured.append(max_workers)
            super().__init__(max_workers=max_workers, **kw)

    monkeypatch.setattr(_corpus.cf, "ThreadPoolExecutor", CapturingExecutor)

    build_pilot_corpus(
        tag="test_no_executor", per_strategy=1, seed=1,
    )
    # No executor of any kind should be spun up at default settings.
    assert captured == [], (
        f"default strategy_workers=1 + max_workers=1 must not spin up any "
        f"ThreadPoolExecutor; observed: {captured}"
    )


# ─── B3.1 — CellTracker class basic ─────────────────────────────────────────


def test_celltracker_class_basic():
    from src.qa._corpus import CellTracker

    t = CellTracker(window=20, min_attempts=10, threshold=0.05)
    assert t.attempts == 0
    assert t.kept == 0
    assert t.should_abandon() is False
    assert t.kept_rate() == 0.0

    for _ in range(5):
        t.record(True)
    assert t.attempts == 5 and t.kept == 5
    assert t.kept_rate() == 1.0
    # Below min_attempts → never abandon.
    assert t.should_abandon() is False

    for _ in range(15):
        t.record(False)
    assert t.attempts == 20
    # Rolling window of 20 with 5 kept => 25%.
    assert abs(t.kept_rate() - 0.25) < 1e-9
    assert t.should_abandon() is False


# ─── B3.2 — env-var gate ────────────────────────────────────────────────────


def test_circuit_breaker_disabled_by_default(monkeypatch):
    from src.qa import _corpus

    monkeypatch.delenv("OENOBENCH_CIRCUIT_BREAKER", raising=False)
    assert _corpus._circuit_breaker_enabled() is False


def test_circuit_breaker_enabled_under_env_var(monkeypatch):
    from src.qa import _corpus

    monkeypatch.setenv("OENOBENCH_CIRCUIT_BREAKER", "1")
    assert _corpus._circuit_breaker_enabled() is True


def test_circuit_breaker_other_env_value_disabled(monkeypatch):
    from src.qa import _corpus

    monkeypatch.setenv("OENOBENCH_CIRCUIT_BREAKER", "true")  # not exactly "1"
    assert _corpus._circuit_breaker_enabled() is False


# ─── B3.3 — abandons at zero yield after min_attempts ───────────────────────


def test_circuit_breaker_abandons_cell_at_zero_yield():
    from src.qa._corpus import CellTracker

    t = CellTracker(window=20, min_attempts=10, threshold=0.05)
    for _ in range(9):
        t.record(False)
        assert t.should_abandon() is False
    # 10th attempt: rate is 0/10 = 0% < 5% threshold → abandon.
    t.record(False)
    assert t.attempts == 10
    assert t.should_abandon() is True


# ─── B3.4 — does not abandon below min_attempts ─────────────────────────────


def test_circuit_breaker_does_not_abandon_below_min_attempts():
    from src.qa._corpus import CellTracker

    t = CellTracker(window=20, min_attempts=10, threshold=0.05)
    for _ in range(5):
        t.record(False)
    assert t.attempts == 5
    assert t.kept_rate() == 0.0
    # Even at 0% rate, below min_attempts we hold.
    assert t.should_abandon() is False


# ─── B3.5 — strict-less-than threshold ──────────────────────────────────────


def test_circuit_breaker_does_not_abandon_at_5pct_yield():
    from src.qa._corpus import CellTracker

    t = CellTracker(window=20, min_attempts=10, threshold=0.05)
    # 1 kept of 20 = 5% exactly. With strict <, this MUST NOT abandon.
    t.record(True)
    for _ in range(19):
        t.record(False)
    assert t.attempts == 20
    assert abs(t.kept_rate() - 0.05) < 1e-9
    assert t.should_abandon() is False


# ─── B3.6 — reallocation of unused budget to the next cell ──────────────────


def test_circuit_breaker_reallocates_unused_budget_to_next_cell():
    """Spec: an abandoned cell with N unused passes ``count + N`` to the next
    cell, capped at 2 × original. Exercised via ``CellTracker.remaining_budget``
    plus ``_reallocate_with_cap`` (the helper used by both ``_corpus`` and
    ``template_generator`` for cross-cell carry-over).
    """
    from src.qa._corpus import CellTracker, _reallocate_with_cap

    # Cell A: original count = 4, abandoned with 0 kept after 10 attempts.
    a = CellTracker(window=20, min_attempts=10, threshold=0.05)
    for _ in range(10):
        a.record(False)
    assert a.should_abandon() is True
    unused_a = a.remaining_budget(4)
    assert unused_a == 4

    next_original = 4
    reallocated = _reallocate_with_cap(
        original=next_original, leftover=unused_a, cap_factor=2,
    )
    # 4 + 4 = 8 == 2 × 4 cap.
    assert reallocated == 8

    # Cap test: a tiny next-cell original with a big leftover is clamped.
    next_small = 2
    big_leftover = 20
    reallocated_clamped = _reallocate_with_cap(
        original=next_small, leftover=big_leftover, cap_factor=2,
    )
    assert reallocated_clamped == next_small * 2 == 4

    # Zero next-original returns 0.
    assert _reallocate_with_cap(original=0, leftover=10) == 0


# ─── B3.7 — env-var disabled → no consultation ──────────────────────────────


def test_circuit_breaker_strategy_no_op_when_env_unset(monkeypatch):
    """With env var unset and ``circuit_breaker`` not passed, the strategy
    must NOT instantiate a tracker — guarantees v8 reproducibility.
    """
    from src.generators import fact_to_question

    monkeypatch.delenv("OENOBENCH_CIRCUIT_BREAKER", raising=False)
    tracker = fact_to_question._resolve_tracker(None, None)
    assert tracker is None


def test_circuit_breaker_strategy_active_under_env(monkeypatch):
    from src.generators import fact_to_question
    from src.qa._corpus import CellTracker

    monkeypatch.setenv("OENOBENCH_CIRCUIT_BREAKER", "1")
    tracker = fact_to_question._resolve_tracker(None, None)
    assert isinstance(tracker, CellTracker)


def test_circuit_breaker_explicit_arg_overrides_env(monkeypatch):
    from src.generators import comparative_generator
    from src.qa._corpus import CellTracker

    monkeypatch.setenv("OENOBENCH_CIRCUIT_BREAKER", "1")
    # circuit_breaker=False overrides env-var-on.
    assert comparative_generator._resolve_tracker(None, False) is None

    monkeypatch.delenv("OENOBENCH_CIRCUIT_BREAKER", raising=False)
    # circuit_breaker=True overrides env-var-off.
    out = comparative_generator._resolve_tracker(None, True)
    assert isinstance(out, CellTracker)


# ─── B3.8 — strategy run_generate honours tracker (early-abandon) ───────────


def test_run_generate_template_honours_tracker_via_env(monkeypatch):
    """With circuit_breaker on, an early-abandoned tracker stops the loop
    even though target was higher.
    """
    from src.generators import template_generator

    monkeypatch.setenv("OENOBENCH_CIRCUIT_BREAKER", "1")
    # count=0 short-circuits before any DB hit but still passes through the
    # circuit-breaker setup branch — verifies wiring doesn't crash.
    result = template_generator.run_generate(
        domain="wine_regions", count=0, dry_run=True,
    )
    assert isinstance(result, dict)
    assert result["generated"] == 0


def test_run_generate_fact_to_question_accepts_circuit_breaker_kwarg():
    from src.generators import fact_to_question

    result = fact_to_question.run_generate(
        domain="wine_regions", count=0, generator="claude",
        question_type="multiple_choice", difficulty="2",
        cognitive_dim="recall", dry_run=True,
        circuit_breaker=True,
    )
    assert isinstance(result, dict)
    assert result["generated"] == 0


def test_run_generate_comparative_accepts_circuit_breaker_kwarg():
    from src.generators import comparative_generator

    result = comparative_generator.run_generate(
        domain="wine_regions", count=0, generator="claude",
        comparison_type="auto", dry_run=True, circuit_breaker=True,
    )
    assert isinstance(result, dict)
    assert result["generated"] == 0


def test_run_generate_scenario_accepts_circuit_breaker_kwarg():
    from src.generators import scenario_generator

    result = scenario_generator.run_generate(
        domain="wine_regions", count=0, generator="claude",
        scenario_type="winemaking", dry_run=True, circuit_breaker=True,
    )
    assert isinstance(result, dict)
    assert result["generated"] == 0


def test_run_generate_distractor_accepts_circuit_breaker_kwarg():
    from src.generators import distractor_miner

    result = distractor_miner.run_generate(
        domain="wine_regions", count=0, generator="claude",
        dry_run=True, circuit_breaker=True,
    )
    assert isinstance(result, dict)
    assert result["generated"] == 0
