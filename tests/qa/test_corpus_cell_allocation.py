"""Phase 2g.12 — Team C: tests for ``_corpus._build_cell_calls``.

The cell-allocation formula was rewritten to fix the v9 sampler-starvation
issue. Previously, LLM-pickable strategies scheduled all 30 (G*D) cells
with take=1 whenever want < 30, which silently overspent the budget by up
to 50% and starved sampler-empty cells. The new formula gives each cell
≥2 budget for any want ≥ 4 and total scheduled budget == want.

These tests pin the cell-count and budget-conservation invariants for the
common audit-pilot sizes (want=10, 20, 40, 100) plus boundary cases.
"""

from __future__ import annotations

import random

import pytest

from src.qa import _corpus
from src.qa._corpus import (
    DOMAINS,
    GENERATORS,
    LLM_STRATEGIES,
    _build_cell_calls,
)


# Use a non-LLM strategy and an LLM strategy as fixtures.
_LLM_STRATEGY = "fact_to_question"
_NON_LLM_STRATEGY = "template"
_MODULE = "fact_to_question"


@pytest.fixture(autouse=True)
def _seed_random():
    """Make ``random.shuffle`` deterministic per test."""
    random.seed(0)


def _total_count(cell_calls: list[dict]) -> int:
    return sum(c["count"] for c in cell_calls)


# ─── LLM-pickable strategy: cell_count = max(1, min(G*D, want // 2)) ─────────


def test_llm_want_10_yields_5_cells_of_2():
    cell_calls = _build_cell_calls(
        _LLM_STRATEGY, _MODULE, want=10, per_country_cap=0.30,
    )
    assert len(cell_calls) == 5
    assert all(c["count"] == 2 for c in cell_calls)
    assert _total_count(cell_calls) == 10


def test_llm_want_20_yields_10_cells_of_2():
    cell_calls = _build_cell_calls(
        _LLM_STRATEGY, _MODULE, want=20, per_country_cap=0.30,
    )
    assert len(cell_calls) == 10
    assert all(c["count"] == 2 for c in cell_calls)
    assert _total_count(cell_calls) == 20


def test_llm_want_40_yields_20_cells_of_2():
    cell_calls = _build_cell_calls(
        _LLM_STRATEGY, _MODULE, want=40, per_country_cap=0.30,
    )
    assert len(cell_calls) == 20
    assert all(c["count"] == 2 for c in cell_calls)
    assert _total_count(cell_calls) == 40


def test_llm_want_100_caps_at_30_cells_with_uneven_budget():
    """want=100 hits the G*D=30 cap; per_cell=3, rem=10 → 10 cells × 4 + 20 cells × 3."""
    cell_calls = _build_cell_calls(
        _LLM_STRATEGY, _MODULE, want=100, per_country_cap=0.30,
    )
    total_cells = len(GENERATORS) * len(DOMAINS)  # 30
    assert len(cell_calls) == total_cells
    counts = sorted(c["count"] for c in cell_calls)
    assert counts == [3] * 20 + [4] * 10
    assert _total_count(cell_calls) == 100


def test_llm_total_budget_always_equals_want():
    """Budget conservation invariant: sum(count) == want for every want."""
    for want in [4, 6, 10, 17, 20, 25, 31, 40, 60, 99, 100]:
        cell_calls = _build_cell_calls(
            _LLM_STRATEGY, _MODULE, want=want, per_country_cap=0.30,
        )
        assert _total_count(cell_calls) == want, (
            f"want={want} produced budget={_total_count(cell_calls)}; "
            f"cells={len(cell_calls)}"
        )


def test_llm_each_cell_has_take_at_least_2_for_want_geq_4():
    """No cell ever gets take=1 for the audit-pilot range (want ≥ 4)."""
    for want in [4, 8, 10, 20, 40, 60, 100]:
        cell_calls = _build_cell_calls(
            _LLM_STRATEGY, _MODULE, want=want, per_country_cap=0.30,
        )
        assert all(c["count"] >= 2 for c in cell_calls), (
            f"want={want} produced a cell with take<2: {cell_calls}"
        )


def test_llm_cell_count_capped_at_total_cells():
    """want > G*D*2 still caps at G*D=30 cells."""
    cell_calls = _build_cell_calls(
        _LLM_STRATEGY, _MODULE, want=200, per_country_cap=0.30,
    )
    assert len(cell_calls) == 30  # G * D
    assert _total_count(cell_calls) == 200


def test_llm_small_want_floors_at_one_cell():
    """want=1 is degenerate but must still produce a valid plan."""
    cell_calls = _build_cell_calls(
        _LLM_STRATEGY, _MODULE, want=1, per_country_cap=0.30,
    )
    assert len(cell_calls) == 1
    assert cell_calls[0]["count"] == 1


def test_llm_per_country_cap_propagated():
    """The per_country_cap kwarg makes it into every cell call."""
    cell_calls = _build_cell_calls(
        _LLM_STRATEGY, _MODULE, want=20, per_country_cap=0.30,
    )
    assert all(c["per_country_cap"] == 0.30 for c in cell_calls)


def test_llm_each_cell_carries_a_generator_and_domain():
    """Every LLM-strategy cell must specify both generator and domain."""
    cell_calls = _build_cell_calls(
        _LLM_STRATEGY, _MODULE, want=20, per_country_cap=0.30,
    )
    for c in cell_calls:
        assert c["generator"] in GENERATORS
        assert c["domain"] in DOMAINS
        assert c["module"] == _MODULE


def test_llm_strategies_set_matches_runtime_set():
    """Sanity: the test fixture _LLM_STRATEGY is in the runtime set."""
    assert _LLM_STRATEGY in LLM_STRATEGIES


# ─── Non-LLM strategy (template): per-domain only, untouched by Phase 2g.12 ───


def test_non_llm_template_uses_per_domain_formula():
    """Template strategy schedules one cell per domain; no generator picks."""
    cell_calls = _build_cell_calls(
        _NON_LLM_STRATEGY, "template_generator", want=20, per_country_cap=0.30,
    )
    assert len(cell_calls) == len(DOMAINS)  # 6
    # No "generator" key — template strategy doesn't pick a generator.
    assert all("generator" not in c for c in cell_calls)
    assert _total_count(cell_calls) == 20


def test_non_llm_template_budget_conservation():
    for want in [6, 10, 20, 30, 60]:
        cell_calls = _build_cell_calls(
            _NON_LLM_STRATEGY, "template_generator",
            want=want, per_country_cap=None,
        )
        assert _total_count(cell_calls) == want
        assert len(cell_calls) == len(DOMAINS)
