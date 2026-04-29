"""Phase 2g.13 — Team C: tests for the cross-pass attempted-fact-ID registry.

The multi-pass strategy loop in ``_corpus._execute_strategy_passes`` runs
each strategy up to N times. Without cross-pass de-duplication, pass 2/3
can re-pick a fact pass 1 already tried (LLM-skipped, parse-failed, gate-
rejected), wasting LLM calls.

These tests verify:
- Empty registry returns empty frozenset.
- ``register_attempted_fact_ids`` accumulates IDs.
- Concurrent ``register_attempted_fact_ids`` from many threads is
  thread-safe (no lost updates).
- ``reset_attempted_fact_ids(strategy)`` clears one strategy without
  touching others.
- ``reset_attempted_fact_ids(None)`` clears all strategies.
- Mixed int/str IDs are normalised to str.
"""

from __future__ import annotations

import threading

import pytest

from src.qa._attempted_facts import (
    _peek_attempted_count,
    get_attempted_fact_ids,
    register_attempted_fact_ids,
    reset_attempted_fact_ids,
)


@pytest.fixture(autouse=True)
def _clear_registry():
    """Each test starts with an empty registry."""
    reset_attempted_fact_ids(None)
    yield
    reset_attempted_fact_ids(None)


def test_empty_registry_returns_empty_frozenset():
    out = get_attempted_fact_ids("fact_to_question")
    assert isinstance(out, frozenset)
    assert len(out) == 0


def test_register_accumulates():
    register_attempted_fact_ids("fact_to_question", ["a", "b", "c"])
    assert get_attempted_fact_ids("fact_to_question") == frozenset({"a", "b", "c"})


def test_register_dedupes_on_repeat():
    register_attempted_fact_ids("fact_to_question", ["a", "b"])
    register_attempted_fact_ids("fact_to_question", ["b", "c"])
    assert get_attempted_fact_ids("fact_to_question") == frozenset({"a", "b", "c"})


def test_register_normalises_int_to_str():
    """Integer IDs (e.g. from psycopg fetch) get coerced to strings."""
    register_attempted_fact_ids("fact_to_question", [1, 2, 3])
    assert get_attempted_fact_ids("fact_to_question") == frozenset({"1", "2", "3"})


def test_register_handles_uuid_strings():
    """Real fact IDs are UUID strings — store them verbatim."""
    uuid = "c4d6afde-dfc1-4847-b863-aad661f306b6"
    register_attempted_fact_ids("comparative", [uuid])
    assert get_attempted_fact_ids("comparative") == frozenset({uuid})


def test_strategy_isolation():
    """Each strategy has its own bucket — registering in one doesn't
    leak into another.
    """
    register_attempted_fact_ids("fact_to_question", ["a", "b"])
    register_attempted_fact_ids("comparative", ["c", "d"])
    assert get_attempted_fact_ids("fact_to_question") == frozenset({"a", "b"})
    assert get_attempted_fact_ids("comparative") == frozenset({"c", "d"})
    assert get_attempted_fact_ids("scenario_synthesis") == frozenset()


def test_reset_one_strategy():
    register_attempted_fact_ids("fact_to_question", ["a", "b"])
    register_attempted_fact_ids("comparative", ["c", "d"])
    reset_attempted_fact_ids("fact_to_question")
    assert get_attempted_fact_ids("fact_to_question") == frozenset()
    assert get_attempted_fact_ids("comparative") == frozenset({"c", "d"})


def test_reset_all_strategies():
    register_attempted_fact_ids("fact_to_question", ["a"])
    register_attempted_fact_ids("comparative", ["b"])
    register_attempted_fact_ids("template", ["c"])
    reset_attempted_fact_ids(None)
    assert get_attempted_fact_ids("fact_to_question") == frozenset()
    assert get_attempted_fact_ids("comparative") == frozenset()
    assert get_attempted_fact_ids("template") == frozenset()


def test_reset_unknown_strategy_is_noop():
    """Resetting a strategy that was never registered is safe."""
    reset_attempted_fact_ids("never_registered_strategy")
    # No exception raised.


def test_peek_helper():
    """Test-only ``_peek_attempted_count`` returns the bucket size."""
    register_attempted_fact_ids("fact_to_question", ["a", "b"])
    assert _peek_attempted_count("fact_to_question") == 2
    assert _peek_attempted_count("comparative") == 0


# ─── Concurrency ──────────────────────────────────────────────────────────────


def test_concurrent_register_does_not_lose_updates():
    """100 threads × 100 IDs each → 10,000 unique IDs in the registry.

    Validates the threading.Lock prevents lost set-update interleavings.
    """
    n_threads = 100
    n_ids_per_thread = 100

    def worker(thread_idx):
        ids = [f"thread{thread_idx}-id{i}" for i in range(n_ids_per_thread)]
        register_attempted_fact_ids("fact_to_question", ids)

    threads = [
        threading.Thread(target=worker, args=(i,)) for i in range(n_threads)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    out = get_attempted_fact_ids("fact_to_question")
    assert len(out) == n_threads * n_ids_per_thread


def test_get_returns_immutable_snapshot():
    """The returned frozenset cannot be mutated to corrupt the registry."""
    register_attempted_fact_ids("fact_to_question", ["a"])
    snapshot = get_attempted_fact_ids("fact_to_question")
    with pytest.raises(AttributeError):
        snapshot.add("b")  # type: ignore[attr-defined]
    # The registry is unchanged.
    assert get_attempted_fact_ids("fact_to_question") == frozenset({"a"})


def test_get_snapshot_does_not_observe_later_writes():
    """Snapshots are point-in-time, not live views."""
    register_attempted_fact_ids("fact_to_question", ["a"])
    snapshot = get_attempted_fact_ids("fact_to_question")
    register_attempted_fact_ids("fact_to_question", ["b"])
    assert snapshot == frozenset({"a"})
    assert get_attempted_fact_ids("fact_to_question") == frozenset({"a", "b"})
