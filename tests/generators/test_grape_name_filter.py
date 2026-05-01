"""Phase 2g.16 — grape-variety name validity filter.

v14b gold review found 3/13 (23%) failing templates were caused by garbage
entity names in `grape_varieties` facts (extracted scraper-side):

* "457 grape variety"             — pure number
* "55% white varieties"           — regulation rule misextracted as a name
* "Champagne Blend"               — vague category, not a specific cultivar

These all pass the substantiveness filter because the surrounding fact text
contains a multi-word proper noun and/or numeric tokens. The grape-name
validity filter catches them at sample time.
"""

from __future__ import annotations

import pytest

from src.generators._fact_sampler import (
    _extract_grape_name,
    _is_grape_fact_valid,
    get_grape_name_filtered_count,
    reset_grape_name_filtered_count,
)


# ─── Real failing facts from v14b gold review (must be REJECTED) ─────────────


@pytest.mark.parametrize(
    "fact_text",
    [
        "New Zealand wine permits the 457 grape variety.",
        "Lazio wine region permits the 55% white varieties grape variety.",
        "Champagne Blend is a widely reviewed grape variety in France.",
    ],
)
def test_real_v14b_failures_are_rejected(fact_text: str) -> None:
    """The 3 v14b gold-failed grape facts must all return False."""
    assert _is_grape_fact_valid(fact_text) is False


# ─── Synthetic invalid names (must be REJECTED) ──────────────────────────────


@pytest.mark.parametrize(
    "fact_text",
    [
        # Pure numbers in different fact patterns
        "California wine permits the 99 grape variety.",
        "12 is a widely reviewed grape variety in Australia.",
        "1234.5 is a cultivated grape variety.",
        # Percentage / regulation rules
        "Bordeaux wine permits the 100% Cabernet grape variety.",
        "Some region permits the 30% red varieties grape variety.",
        # Vague generic blends
        "Local varieties is a grape variety in Italy.",
        "Native varieties is a widely reviewed grape variety in Greece.",
        "Indigenous Blend is a grape variety in Portugal.",
        "Mixed Blend is a widely reviewed grape variety in Spain.",
    ],
)
def test_synthetic_invalid_names_are_rejected(fact_text: str) -> None:
    assert _is_grape_fact_valid(fact_text) is False


# ─── Real valid grape facts (must be ACCEPTED) ───────────────────────────────


@pytest.mark.parametrize(
    "fact_text",
    [
        "Barolo DOCG permits the Nebbiolo grape variety.",
        "Champagne Region permits the Pinot Noir grape variety.",
        "Cabernet Sauvignon is a widely reviewed grape variety in France.",
        "Sangiovese is a cultivated grape variety in Tuscany.",
        "Vigiriega is a grape variety in Spain.",
        # Names with hyphens, apostrophes, accents
        "Saint-Émilion permits the Cabernet Franc grape variety.",
        "Nero d'Avola is a widely reviewed grape variety in Sicily.",
        "Grüner Veltliner is a cultivated grape variety in Austria.",
    ],
)
def test_real_valid_facts_are_accepted(fact_text: str) -> None:
    assert _is_grape_fact_valid(fact_text) is True


# ─── No-pattern-match → not blocked (don't over-block) ──────────────────────


@pytest.mark.parametrize(
    "fact_text",
    [
        # No "grape variety" phrasing at all — should not be evaluated.
        "Bordeaux is a famous wine region in France.",
        "The 2018 vintage was excellent in Burgundy.",
        # Empty / whitespace
        "",
        "   ",
    ],
)
def test_facts_without_grape_pattern_pass_through(fact_text: str) -> None:
    """When the extraction pattern doesn't match, the filter must NOT reject —
    it falls through to other guards."""
    assert _is_grape_fact_valid(fact_text) is True


# ─── Extraction helper sanity checks ─────────────────────────────────────────


def test_extract_grape_name_permits_pattern() -> None:
    name = _extract_grape_name(
        "Lazio wine region permits the 55% white varieties grape variety."
    )
    assert name == "55% white varieties"


def test_extract_grape_name_widely_reviewed_pattern() -> None:
    name = _extract_grape_name("Champagne Blend is a widely reviewed grape variety in France.")
    assert name == "Champagne Blend"


def test_extract_grape_name_returns_none_for_non_match() -> None:
    name = _extract_grape_name("Bordeaux is a famous wine region in France.")
    assert name is None


# ─── Counter behaviour ───────────────────────────────────────────────────────


def test_counter_starts_at_zero_after_reset() -> None:
    reset_grape_name_filtered_count()
    assert get_grape_name_filtered_count() == 0


def test_counter_resettable() -> None:
    """We can't directly increment from outside (the counter lives in the
    sample_facts loop), but the reset must always return the count to 0."""
    reset_grape_name_filtered_count()
    assert get_grape_name_filtered_count() == 0
    reset_grape_name_filtered_count()
    assert get_grape_name_filtered_count() == 0
