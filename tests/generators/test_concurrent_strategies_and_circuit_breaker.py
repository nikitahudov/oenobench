"""Phase 2g.10 (Team Golf) — A4 concurrent top-level strategies.

A4 covers:

- ``--strategy-workers N`` / ``OENOBENCH_STRATEGY_WORKERS`` resolution.
- Default ``strategy_workers=1`` runs strategies serially (no overlap).
- ``strategy_workers >= 2`` runs strategies concurrently (overlap observed).

B3 (per-cell circuit breaker) is appended as a separate test class in a
follow-up commit.
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
