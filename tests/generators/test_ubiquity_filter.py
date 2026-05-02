"""Phase 2g.17 — ubiquitous-grape ambiguity guard integration tests.

Tests that sample_facts, sample_fact_pairs, and sample_confusable_facts
correctly filter ubiquitous grapes (Cabernet, Chardonnay, etc.) when
called with reject_ubiquitous_for_region_answer=True, and that they do NOT
over-block when the flag is off or when grapes differ.
"""

from __future__ import annotations

import random
import uuid
from unittest.mock import MagicMock, patch

import pytest

import src.generators._fact_sampler as _fs
from src.generators._fact_sampler import (
    get_ubiquity_filtered_count,
    reset_ubiquity_filtered_count,
    sample_confusable_facts,
    sample_fact_pairs,
    sample_facts,
)


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _make_fact(
    fact_text: str,
    idx: int,
    domain: str = "grape_varieties",
    subdomain: str = "test_sub",
    entities=None,
) -> dict:
    if entities is None:
        entities = [{"type": "country", "name": "France"}]
    return {
        "id": uuid.UUID(int=idx),
        "fact_text": fact_text,
        "domain": domain,
        "subdomain": subdomain,
        "entities": entities,
        "source_id": uuid.UUID(int=10_000 + idx),
        "source_name": "FakeSource",
        "source_url": f"https://example.test/{idx}",
        "confidence": 1.0,
        "tags": ["test"],
    }


class _FakeCursor:
    """Single-table cursor that returns the same facts on every execute."""

    def __init__(self, facts):
        self._facts = facts
        self._last_limit = None

    def execute(self, query, params=()):
        try:
            self._last_limit = int(params[-1])
        except (TypeError, ValueError, IndexError):
            self._last_limit = len(self._facts)

    def fetchall(self):
        n = min(self._last_limit or len(self._facts), len(self._facts))
        return [dict(row) for row in self._facts[:n]]


class _FakeConn:
    def __init__(self, facts):
        self._facts = facts

    def cursor(self):
        return _FakeCursor(self._facts)


# ─── Facts pool ──────────────────────────────────────────────────────────────

_CABERNET_FACT_TEXT = (
    "Napa Valley wine region permits the Cabernet Sauvignon grape variety "
    "and is a prominent AVA in California with extensive aging requirements."
)
_OBSCURE_FACT_1 = (
    "Santorini PDO permits the Assyrtiko grape variety and produces "
    "distinctive mineral wines on volcanic soils in the Aegean Sea."
)
_OBSCURE_FACT_2 = (
    "Wachau wine region permits the Grüner Veltliner grape variety and "
    "produces elegant white wines along the Danube River in Austria."
)

_POOL_3 = [
    _make_fact(_CABERNET_FACT_TEXT, idx=1),   # ubiquitous (Cabernet Sauvignon)
    _make_fact(_OBSCURE_FACT_1, idx=2),        # not ubiquitous (Assyrtiko)
    _make_fact(_OBSCURE_FACT_2, idx=3),        # not ubiquitous (Grüner Veltliner)
]


# ─── 7b: sample_facts tests ──────────────────────────────────────────────────


class TestSampleFactsUbiquityFlag:
    def setup_method(self):
        reset_ubiquity_filtered_count()
        # Ensure the ubiquity cache contains at least the curated set.
        _fs._UBIQUITOUS_GRAPE_NAMES_CACHE = set(_fs._UBIQUITOUS_INTERNATIONAL_GRAPES)

    def test_sample_facts_rejects_ubiquitous_grape_when_flag_on(self):
        """With flag=True, Cabernet fact must be excluded; counter must rise."""
        conn = _FakeConn(_POOL_3)
        before = get_ubiquity_filtered_count()

        with patch("src.generators._fact_sampler.get_pg", return_value=conn):
            results = sample_facts(
                domain="grape_varieties",
                count=3,
                reject_ubiquitous_for_region_answer=True,
            )

        result_texts = [r["fact_text"] for r in results]
        assert _CABERNET_FACT_TEXT not in result_texts, (
            "Cabernet fact should be filtered when reject_ubiquitous_for_region_answer=True"
        )
        assert get_ubiquity_filtered_count() > before, (
            "_UBIQUITY_FILTERED_COUNT should have incremented"
        )

    def test_sample_facts_keeps_ubiquitous_grape_when_flag_off(self):
        """With flag=False (default), Cabernet fact must NOT be filtered — regression guard."""
        conn = _FakeConn(_POOL_3)

        with patch("src.generators._fact_sampler.get_pg", return_value=conn):
            results = sample_facts(
                domain="grape_varieties",
                count=3,
                reject_ubiquitous_for_region_answer=False,
            )

        result_texts = [r["fact_text"] for r in results]
        assert _CABERNET_FACT_TEXT in result_texts, (
            "Cabernet fact should NOT be filtered when reject_ubiquitous_for_region_answer=False"
        )


# ─── 7c: sample_fact_pairs tests ─────────────────────────────────────────────


class TestSampleFactPairsUbiquityFilter:
    def setup_method(self):
        reset_ubiquity_filtered_count()
        _fs._UBIQUITOUS_GRAPE_NAMES_CACHE = set(_fs._UBIQUITOUS_INTERNATIONAL_GRAPES)

    def _make_pair_row(self, a_text, b_text, a_idx, b_idx, etype="grape"):
        """Build a dict that matches sample_fact_pairs SQL output columns."""
        return {
            "a_id": uuid.UUID(int=a_idx),
            "a_text": a_text,
            "a_domain": "grape_varieties",
            "a_sub": "test_sub",
            "a_entities": [{"type": "country", "name": "France"}, {"type": etype, "name": "TestGrape"}],
            "a_source_id": uuid.UUID(int=10_000 + a_idx),
            "a_source_name": "FakeSource",
            "a_source_url": f"https://example.test/{a_idx}",
            "a_confidence": 1.0,
            "a_tags": ["test"],
            "shared_type": etype,
            "a_entity": "TestGrapeA",
            "b_entity": "TestGrapeB",
            "b_id": uuid.UUID(int=b_idx),
            "b_text": b_text,
            "b_sub": "test_sub",
            "b_entities": [{"type": "country", "name": "France"}, {"type": etype, "name": "TestGrape"}],
            "b_source_id": uuid.UUID(int=10_000 + b_idx),
            "b_source_name": "FakeSource",
            "b_source_url": f"https://example.test/{b_idx}",
            "b_confidence": 1.0,
            "b_tags": ["test"],
        }

    def test_sample_fact_pairs_rejects_same_ubiquitous_grape_pair(self):
        """A pair where both facts have the same ubiquitous grape must be filtered."""
        cab_a = (
            "Verde Valley wine region permits the Cabernet Sauvignon grape variety "
            "and has notable tannin structure in its red wines produced there."
        )
        cab_b = (
            "Napa Valley wine region permits the Cabernet Sauvignon grape variety "
            "and is one of California's most prestigious appellations overall."
        )
        assyrtiko_a = (
            "Santorini PDO permits the Assyrtiko grape variety and produces "
            "distinctive mineral whites on volcanic soils in the Aegean Sea."
        )
        assyrtiko_b = (
            "Naxos wine region permits the Assyrtiko grape variety and is a "
            "smaller Greek island appellation with good soil conditions."
        )
        rows = [
            self._make_pair_row(cab_a, cab_b, a_idx=1, b_idx=2),      # same ubiquitous grape → must drop
            self._make_pair_row(assyrtiko_a, assyrtiko_b, a_idx=3, b_idx=4),  # non-ubiquitous → keep
            self._make_pair_row(_OBSCURE_FACT_1, _OBSCURE_FACT_2, a_idx=5, b_idx=6),  # different grapes → keep
        ]

        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = rows
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        before = get_ubiquity_filtered_count()

        with patch("src.generators._fact_sampler.get_pg", return_value=mock_conn):
            pairs = sample_fact_pairs(domain="grape_varieties", count=10)

        all_texts = [(a["fact_text"], b["fact_text"]) for a, b in pairs]
        cab_pair_present = any(
            (a == cab_a and b == cab_b) or (a == cab_b and b == cab_a)
            for a, b in all_texts
        )
        assert not cab_pair_present, "Same-ubiquitous-grape pair must be filtered"
        assert get_ubiquity_filtered_count() > before, "Counter must have incremented"

    def test_sample_fact_pairs_keeps_different_grape_pair(self):
        """A pair with Cabernet + Pinot Noir (different ubiquitous grapes) must NOT be
        rejected by the ubiquity filter — the counter must NOT increment for this pair."""
        cab_text = (
            "Napa Valley wine region permits the Cabernet Sauvignon grape variety "
            "and has significant international recognition for its red wines there."
        )
        pinot_text = (
            "Burgundy wine region permits the Pinot Noir grape variety "
            "and is renowned for its terroir-driven red wines produced in France."
        )
        rows = [self._make_pair_row(cab_text, pinot_text, a_idx=10, b_idx=11)]

        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = rows
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        before = get_ubiquity_filtered_count()

        with patch("src.generators._fact_sampler.get_pg", return_value=mock_conn):
            sample_fact_pairs(domain="grape_varieties", count=10)

        # The ubiquity filter must NOT have incremented the counter — the pair's
        # two grapes differ (Cabernet ≠ Pinot Noir) so the same-ubiquitous-grape
        # check should pass it through. Other sampler filters may still reject it
        # (dimension, affinity, length), but that is not what we're testing here.
        assert get_ubiquity_filtered_count() == before, (
            "Counter must not increment for a Cabernet+PinotNoir pair "
            "(different ubiquitous grapes — not same-grape ambiguity)"
        )


# ─── 7d: sample_confusable_facts tests ───────────────────────────────────────


class TestSampleConfusableFactsUbiquityFilter:
    def setup_method(self):
        reset_ubiquity_filtered_count()
        _fs._UBIQUITOUS_GRAPE_NAMES_CACHE = set(_fs._UBIQUITOUS_INTERNATIONAL_GRAPES)

    def _make_cab_sibling(self, region: str, idx: int) -> dict:
        text = (
            f"{region} wine region permits the Cabernet Sauvignon grape variety "
            f"and produces internationally recognised red wines with fine tannins."
        )
        return _make_fact(
            text, idx=idx,
            entities=[{"type": "country", "name": "France"}, {"type": "grape", "name": "Cabernet Sauvignon"}],
        )

    def test_sample_confusable_facts_excludes_ubiquitous_siblings(self):
        """When target has Cabernet, all Cabernet candidate siblings must be dropped."""
        target = _make_fact(
            _CABERNET_FACT_TEXT, idx=99,
            entities=[{"type": "country", "name": "United States"}, {"type": "grape", "name": "Cabernet Sauvignon"}],
        )
        cab_sibling_1 = self._make_cab_sibling("Bordeaux", idx=101)
        cab_sibling_2 = self._make_cab_sibling("Tuscany", idx=102)
        cab_sibling_3 = self._make_cab_sibling("Maipo Valley", idx=103)
        non_cab_1 = _make_fact(
            _OBSCURE_FACT_1, idx=104,
            entities=[{"type": "country", "name": "Greece"}, {"type": "grape", "name": "Assyrtiko"}],
        )
        non_cab_2 = _make_fact(
            _OBSCURE_FACT_2, idx=105,
            entities=[{"type": "country", "name": "Austria"}, {"type": "grape", "name": "Grüner Veltliner"}],
        )

        pool = [cab_sibling_1, cab_sibling_2, cab_sibling_3, non_cab_1, non_cab_2]

        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [dict(f) for f in pool]
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        before = get_ubiquity_filtered_count()

        with patch("src.generators._fact_sampler.get_pg", return_value=mock_conn):
            results = sample_confusable_facts(target, domain="grape_varieties", count=10)

        result_texts = {r["fact_text"] for r in results}
        for sibling in [cab_sibling_1, cab_sibling_2, cab_sibling_3]:
            assert sibling["fact_text"] not in result_texts, (
                f"Cabernet sibling should be excluded: {sibling['fact_text'][:60]!r}"
            )
        dropped = get_ubiquity_filtered_count() - before
        assert dropped == 3, f"Expected 3 dropped siblings, got {dropped}"

    def test_sample_confusable_facts_unaffected_when_target_not_ubiquitous(self):
        """When the target has a non-ubiquitous grape, Cabernet candidates must pass through."""
        target = _make_fact(
            "Santorini PDO permits the Vermentino grape variety and is a small "
            "island appellation in Greece known for its volcanic terroir there.",
            idx=200,
            entities=[{"type": "country", "name": "Greece"}, {"type": "grape", "name": "Vermentino"}],
        )
        cab_candidate = self._make_cab_sibling("Napa Valley", idx=201)

        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [dict(cab_candidate)]
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        before = get_ubiquity_filtered_count()

        with patch("src.generators._fact_sampler.get_pg", return_value=mock_conn):
            results = sample_confusable_facts(target, domain="grape_varieties", count=10)

        # Counter must not have changed (the filter doesn't fire for non-ubiquitous targets).
        assert get_ubiquity_filtered_count() == before, (
            "Counter should not change when target grape is not ubiquitous"
        )
