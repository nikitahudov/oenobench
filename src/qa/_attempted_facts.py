"""Cross-pass attempted-fact-ID registry (Phase 2g.13).

The multi-pass strategy loop in ``_corpus._execute_strategy_passes`` runs
each strategy up to N times until the budget is filled. Without
cross-pass de-duplication, pass 2/3 can re-pick a fact pass 1 already
tried (and got LLM-skipped or parse-failed), wasting LLM calls.

This module is a thread-safe per-strategy fact-ID accumulator that
survives across passes WITHIN a single build. Strategies call
``register_attempted_fact_ids`` after sampling to add picked IDs, and
read prior-pass IDs via ``get_attempted_fact_ids`` at start to seed
their ``run_used_ids``. The orchestrator calls
``reset_attempted_fact_ids`` before each strategy build so consecutive
builds in the same Python process don't carry state.

Lives in its own module to avoid import cycles between strategy modules
and ``src.qa._corpus`` (which loads strategies lazily via importlib).
"""

from __future__ import annotations

import threading
from typing import Iterable

_BUILD_ATTEMPTED_FACTS: dict[str, set[str]] = {}
_BUILD_ATTEMPTED_LOCK = threading.Lock()


def get_attempted_fact_ids(strategy: str) -> frozenset[str]:
    """Return a frozen snapshot of fact IDs ``strategy`` has attempted.

    Strategies should call this at the start of ``_run_generate_body``
    and seed their initial ``run_used_ids`` with it so the sampler
    skips already-attempted facts on subsequent passes.
    """
    with _BUILD_ATTEMPTED_LOCK:
        return frozenset(_BUILD_ATTEMPTED_FACTS.get(strategy, set()))


def register_attempted_fact_ids(
    strategy: str, ids: Iterable[str | int]
) -> None:
    """Record fact IDs that ``strategy`` has just attempted.

    Strategies should call this after each sampler hand-back, regardless
    of whether the attempt produced a question. Cross-pass de-duplication
    is the whole point — failed attempts must not be re-tried.
    """
    with _BUILD_ATTEMPTED_LOCK:
        bucket = _BUILD_ATTEMPTED_FACTS.setdefault(strategy, set())
        bucket.update(str(i) for i in ids)


def reset_attempted_fact_ids(strategy: str | None = None) -> None:
    """Clear cross-pass state.

    Called by the orchestrator before each strategy build so state from
    a prior build (in the same Python process) doesn't leak. Pass
    ``strategy=None`` to clear all strategies.
    """
    with _BUILD_ATTEMPTED_LOCK:
        if strategy is None:
            _BUILD_ATTEMPTED_FACTS.clear()
        else:
            _BUILD_ATTEMPTED_FACTS.pop(strategy, None)


def _peek_attempted_count(strategy: str) -> int:
    """Test-only helper: returns the current size of the registry for ``strategy``."""
    with _BUILD_ATTEMPTED_LOCK:
        return len(_BUILD_ATTEMPTED_FACTS.get(strategy, set()))
