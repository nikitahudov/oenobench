"""Phase 5 release_v1 follow-up — loose-fallback tests for sample_fact_pairs.

Verifies the two new behaviours added to ``src.generators._fact_sampler.sample_fact_pairs``:

1. The loose fallback fires when the strict candidate-set query returns
   fewer pairs than ``count`` requested. Loose-fallback pairs are tagged
   ``_pair_strictness="loose"`` on each fact in the pair, and the
   module-level ``_PAIR_STRICTNESS_COUNTS`` counter records them.
2. The loose fallback does NOT fire (no loose pairs admitted) when the
   strict pass already has enough candidates to fill ``count`` — strict
   callers must not silently regress.
3. The expanded entity-type whitelist (region, grape, appellation,
   producer + classification, style, doc, aoc, docg, ava, doca, igp, aop)
   is honoured: a pair built on the long-tail ``classification`` entity
   type can survive both passes' SQL-level whitelist.
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

import src.generators._fact_sampler as _fs
from src.generators._fact_sampler import (
    get_pair_strictness_counts,
    reset_pair_strictness_counts,
    sample_fact_pairs,
)


# ─── Fixtures ───────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_state(monkeypatch):
    reset_pair_strictness_counts()
    _fs.reset_country_usage()
    # Short-circuit the country-base-distribution lookup so it never reaches
    # for the patched cursor (which would otherwise consume a side_effect
    # slot before our strict/loose SQL even runs). Returning {} disables the
    # pool-share quota — the per-call cap in these tests is None anyway, so
    # this neither relaxes nor tightens any contract under test.
    monkeypatch.setattr(_fs, "_country_base_distribution", lambda: {})
    yield
    reset_pair_strictness_counts()
    _fs.reset_country_usage()


# ─── Row factory ────────────────────────────────────────────────────────


# Two long, content-rich Italian facts that survive _is_fact_specific,
# _is_fact_rich, and the affinity (>= 0.2) gates because they share
# country + same etype with different entity names.
_FACT_TEXT_A = (
    "Barolo DOCG mandates a minimum of thirty-eight months of aging including "
    "eighteen months in oak barrels for its traditional Nebbiolo bottlings produced "
    "in the Piedmont region of Italy throughout history."
)
_FACT_TEXT_B = (
    "Barbaresco DOCG mandates a minimum of twenty-six months of aging including "
    "nine months in oak barrels for its traditional Nebbiolo bottlings produced "
    "in the Piedmont region of Italy throughout history."
)


def _make_pair_row(
    a_text: str = _FACT_TEXT_A,
    b_text: str = _FACT_TEXT_B,
    a_idx: int = 1,
    b_idx: int = 2,
    etype: str = "appellation",
    country_a: str = "Italy",
    country_b: str = "Italy",
    sub_a: str = "italy_piedmont",
    sub_b: str = "italy_piedmont",
    domain: str = "wine_regions",
) -> dict:
    """Build a dict that matches the ``sample_fact_pairs`` SQL output columns."""
    a_entities = [{"type": etype, "name": f"AppA-{a_idx}"}]
    if country_a:
        a_entities.append({"type": "country", "name": country_a})
    b_entities = [{"type": etype, "name": f"AppB-{b_idx}"}]
    if country_b:
        b_entities.append({"type": "country", "name": country_b})
    return {
        "a_id": uuid.UUID(int=a_idx),
        "a_text": a_text,
        "a_domain": domain,
        "a_sub": sub_a,
        "a_entities": a_entities,
        "a_source_id": uuid.UUID(int=10_000 + a_idx),
        "a_source_name": "FakeSource",
        "a_source_url": f"https://example.test/{a_idx}",
        "a_confidence": 1.0,
        "a_tags": ["test"],
        "shared_type": etype,
        "a_entity": f"AppA-{a_idx}",
        "b_entity": f"AppB-{b_idx}",
        "b_id": uuid.UUID(int=b_idx),
        "b_text": b_text,
        "b_sub": sub_b,
        "b_entities": b_entities,
        "b_source_id": uuid.UUID(int=10_000 + b_idx),
        "b_source_name": "FakeSource",
        "b_source_url": f"https://example.test/{b_idx}",
        "b_confidence": 1.0,
        "b_tags": ["test"],
    }


def _build_mock_conn(strict_rows: list, loose_rows: list) -> MagicMock:
    """Return a mock connection whose .cursor() yields a NEW MagicMock cursor
    for each call, with the strict cursor's fetchall returning strict_rows
    and the loose cursor's fetchall returning loose_rows.
    """
    strict_cursor = MagicMock()
    strict_cursor.fetchall.return_value = list(strict_rows)
    loose_cursor = MagicMock()
    loose_cursor.fetchall.return_value = list(loose_rows)
    mock_conn = MagicMock()
    # First .cursor() = strict pass, second .cursor() = loose fallback.
    mock_conn.cursor.side_effect = [strict_cursor, loose_cursor]
    return mock_conn


# ─── Tests ──────────────────────────────────────────────────────────────


def test_loose_fallback_fires_when_strict_short():
    """When the strict pass returns fewer than ``count`` admissible pairs,
    the loose fallback must run and append loose pairs to the result.

    Loose pairs must (a) be tagged ``_pair_strictness="loose"`` on both
    facts and (b) bump the ``_PAIR_STRICTNESS_COUNTS["loose"]`` counter.
    """
    # Strict pass: one good Italian pair (admitted, strict).
    strict_rows = [_make_pair_row(a_idx=1, b_idx=2)]

    # Loose pass: a cross-country pair that the strict SQL would NOT have
    # surfaced (country differs, subdomain differs). Different IDs so it
    # isn't filtered out by seen_ids.
    loose_rows = [
        _make_pair_row(
            a_text=_FACT_TEXT_A.replace("Barolo", "Rioja Gran Reserva"),
            b_text=_FACT_TEXT_B.replace("Barbaresco", "Brunello di Montalcino"),
            a_idx=11,
            b_idx=12,
            country_a="Spain",
            country_b="Italy",
            sub_a="spain_rioja",
            sub_b="italy_tuscany",
        ),
    ]

    mock_conn = _build_mock_conn(strict_rows, loose_rows)
    with patch("src.generators._fact_sampler.get_pg", return_value=mock_conn):
        pairs = sample_fact_pairs(domain="wine_regions", count=5)

    # Both pairs admitted; loose fallback contributed at least one.
    assert len(pairs) >= 2, f"Expected >= 2 pairs (strict + loose); got {len(pairs)}"
    counts = get_pair_strictness_counts()
    assert counts["strict"] >= 1, f"Strict counter should reflect strict admit; got {counts}"
    assert counts["loose"] >= 1, f"Loose fallback should have fired; got {counts}"

    # The loose-tagged pair must carry the marker on BOTH facts.
    loose_pairs = [
        (a, b) for (a, b) in pairs
        if a.get("_pair_strictness") == "loose" and b.get("_pair_strictness") == "loose"
    ]
    assert loose_pairs, "Expected at least one pair tagged _pair_strictness='loose'"

    # Strict pairs must still carry the strict tag.
    strict_pairs = [
        (a, b) for (a, b) in pairs
        if a.get("_pair_strictness") == "strict" and b.get("_pair_strictness") == "strict"
    ]
    assert strict_pairs, "Expected at least one pair tagged _pair_strictness='strict'"

    # The mock connection's cursor must have been requested exactly twice
    # (one strict + one loose).
    assert mock_conn.cursor.call_count == 2


def test_loose_fallback_does_not_fire_when_strict_full():
    """When the strict pass already returns ``count`` admissible pairs, the
    loose fallback must NOT run — strict callers must see no regression.
    """
    # Strict pass: enough admissible pairs to fully satisfy count=2.
    strict_rows = [
        _make_pair_row(a_idx=1, b_idx=2),
        _make_pair_row(a_idx=3, b_idx=4),
        _make_pair_row(a_idx=5, b_idx=6),  # buffer so the post-filters can't starve us
    ]
    # Loose pass: would-have-been admissible — but should never be reached.
    loose_rows = [_make_pair_row(a_idx=99, b_idx=100)]

    mock_conn = _build_mock_conn(strict_rows, loose_rows)
    with patch("src.generators._fact_sampler.get_pg", return_value=mock_conn):
        pairs = sample_fact_pairs(domain="wine_regions", count=2)

    assert len(pairs) == 2, f"Expected exactly 2 strict pairs; got {len(pairs)}"

    # Every returned pair must be strict.
    for (a, b) in pairs:
        assert a.get("_pair_strictness") == "strict", \
            f"Strict-only run leaked _pair_strictness={a.get('_pair_strictness')!r}"
        assert b.get("_pair_strictness") == "strict"

    counts = get_pair_strictness_counts()
    assert counts["loose"] == 0, f"Loose fallback fired unexpectedly: {counts}"
    assert counts["strict"] == 2

    # The mock connection's cursor must have been requested exactly ONCE.
    assert mock_conn.cursor.call_count == 1, \
        f"Loose fallback ran when it shouldn't have (cursor calls={mock_conn.cursor.call_count})"


def test_loose_fallback_honours_expanded_entity_type_whitelist():
    """The expanded entity-type whitelist (classification / doc / docg / aoc /
    ava / doca / igp / aop / style) must be accepted by both the SQL filter
    and the post-filters. We verify by feeding a pair that uses one of the
    new long-tail entity types and confirming it survives end-to-end.
    """
    # Build a pair where the shared entity type is 'classification' — one of
    # the new whitelist entries. The fact texts are content-rich Italian
    # producer-tier facts that survive _is_fact_specific / _is_fact_rich /
    # the affinity score (same country, comparable entities, different names).
    strict_rows = [
        _make_pair_row(
            a_text=(
                "DOCG classification requires a minimum of thirty-eight months "
                "aging for Barolo wines in Italy and is the highest tier of the "
                "Italian wine classification system established in nineteen sixty-three."
            ),
            b_text=(
                "DOC classification requires a minimum of eighteen months aging "
                "for Chianti Classico wines in Italy and is the second tier of the "
                "Italian wine classification system established in nineteen sixty-three."
            ),
            a_idx=21,
            b_idx=22,
            etype="classification",
            country_a="Italy",
            country_b="Italy",
            sub_a="italy_classification",
            sub_b="italy_classification",
            domain="wine_business",
        )
    ]
    loose_rows: list[dict] = []  # no fallback rows needed

    mock_conn = _build_mock_conn(strict_rows, loose_rows)
    with patch("src.generators._fact_sampler.get_pg", return_value=mock_conn):
        pairs = sample_fact_pairs(domain="wine_business", count=5)

    assert pairs, (
        "Expected at least one pair built on the new 'classification' entity "
        "type; got none — the expanded whitelist isn't being honoured."
    )
    # Verify the expanded etype made it through.
    for (a, b) in pairs:
        # The entity-map extractor should pick up the 'classification' tag
        # from each fact's entities list.
        a_etypes = {e.get("type") for e in (a.get("entities") or [])}
        b_etypes = {e.get("type") for e in (b.get("entities") or [])}
        assert "classification" in a_etypes, f"Lost 'classification' tag on fact A: {a_etypes}"
        assert "classification" in b_etypes, f"Lost 'classification' tag on fact B: {b_etypes}"

    counts = get_pair_strictness_counts()
    # Strict-only result: no loose admissions.
    assert counts["strict"] >= 1
    assert counts["loose"] == 0
