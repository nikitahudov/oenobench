"""Lever B2 (2026-04-28) — pre-flight substantiveness filter and
iconic-filter extension across all strategies.

Audit pilot v8 hit ~99% LLM-rejection. Many of those skipped facts are
pre-screenable from text alone. This module asserts:

* The new ``_is_fact_substantive`` predicate accepts numeric / technical /
  multi-word-non-iconic-proper-noun facts and rejects the rest.
* The predicate is gated by env var ``OENOBENCH_FACT_SUBSTANTIVE_FILTER``
  (default OFF) so v8 byte-for-byte reproducibility holds.
* The single-fact iconic filter inside ``sample_facts`` now applies for
  every non-None ``strategy`` value (was previously gated to two strategies).
"""

from __future__ import annotations

import random
import uuid

import pytest

from src.generators import _fact_sampler
from src.generators._fact_sampler import (
    _is_fact_specific,
    _is_fact_substantive,
    _should_apply_iconic_filter,
)


# ─── Predicate-only tests (no DB) ───────────────────────────────────────────


def test_substantive_with_numeric():
    assert (
        _is_fact_substantive(
            "Barolo DOCG requires 100% Nebbiolo and 38 months ageing"
        )
        is True
    )


def test_substantive_with_technical_term():
    assert (
        _is_fact_substantive(
            "Champagne uses méthode champenoise with secondary fermentation in bottle"
        )
        is True
    )


def test_substantive_with_non_iconic_proper_noun():
    # ``Paolo Bea`` is an Umbrian producer, NOT on the iconic YAML.
    # No numbers, no curated wine-technical terms — the multi-word
    # proper-noun branch is what carries the predicate to True.
    # Note: ``Clos des Mouches`` won't match the regex because ``des``
    # is lowercase and breaks the Capital-lower (space) Capital-lower
    # chain; we documented that and chose ``Paolo Bea`` instead.
    assert (
        _is_fact_substantive(
            "Paolo Bea farms ancestral vines on volcanic slopes near Montefalco"
        )
        is True
    )


def test_non_substantive_geographic_only():
    assert _is_fact_substantive("Beaujolais is a region in France.") is False


def test_non_substantive_marketing():
    text = "This iconic estate is celebrated for its world-class wines."
    # Already caught by the existing vague-pattern path.
    assert _is_fact_specific(text) is False
    # Predicate also rejects: no number, no term, no multi-word proper noun.
    assert _is_fact_substantive(text) is False


def test_non_substantive_iconic_proper_noun_alone():
    # The only multi-word proper noun is ``Château Margaux`` (iconic);
    # no numbers, no curated technical terms.
    assert _is_fact_substantive("Château Margaux is famous.") is False


# ─── DB-mocked sampler integration tests ───────────────────────────────────


class _FakeCursor:
    def __init__(self, fake_facts):
        self._facts = fake_facts
        self._last_limit = None
        self._rng = random.Random(0xB2)

    def execute(self, query, params=()):
        try:
            self._last_limit = int(params[-1])
        except (TypeError, ValueError, IndexError):
            self._last_limit = len(self._facts)

    def fetchall(self):
        n = self._last_limit or len(self._facts)
        shuffled = list(self._facts)
        self._rng.shuffle(shuffled)
        return [dict(r) for r in shuffled[:n]]


class _FakeConn:
    def __init__(self, facts):
        self._facts = facts
        self._rng = random.Random(0xB2)

    def cursor(self):
        cur = _FakeCursor(self._facts)
        cur._rng = self._rng
        return cur


def _fact(country: str, fact_text: str, idx: int) -> dict:
    return {
        "id": uuid.UUID(int=idx),
        "fact_text": fact_text,
        "domain": "wine_regions",
        "subdomain": f"{country.lower()}_test",
        "entities": [{"type": "country", "name": country}],
        "source_id": uuid.UUID(int=10_000 + idx),
        "source_name": "FakeSource",
        "source_url": f"https://example.test/{idx}",
        "confidence": 1.0,
        "tags": ["test"],
    }


@pytest.fixture
def patched_db(monkeypatch):
    pool = [
        # Substantive (numeric)
        _fact(
            "Italy",
            "Barolo DOCG requires 100% Nebbiolo and 38 months ageing minimum.",
            1,
        ),
        # Substantive (technical term: méthode + fermentation)
        _fact(
            "France",
            "Champagne uses méthode champenoise with secondary fermentation in bottle.",
            2,
        ),
        # NOT substantive — passes _is_fact_specific (>=8 words, no vague
        # patterns, no blend-as-variety) but has no number, no curated term,
        # and no multi-word non-iconic proper noun. Should drop when the
        # filter is on, survive when off.
        _fact(
            "France",
            "Wine is made from grapes in many places around the entire world.",
            3,
        ),
        # NOT substantive — geographic containment only.
        _fact(
            "France",
            "Beaujolais is a small region located within the country of France.",
            4,
        ),
    ]
    monkeypatch.setattr(_fact_sampler, "get_pg", lambda: _FakeConn(pool))
    monkeypatch.setattr(
        _fact_sampler,
        "_country_base_distribution",
        lambda: {"Italy": 0.5, "France": 0.5},
    )
    _fact_sampler.reset_country_usage()
    yield pool
    _fact_sampler.reset_country_usage()


def test_filter_disabled_by_default(monkeypatch, patched_db):
    """Without OENOBENCH_FACT_SUBSTANTIVE_FILTER set, the new predicate
    must NOT be applied — non-substantive but specific facts pass through.
    """
    monkeypatch.delenv("OENOBENCH_FACT_SUBSTANTIVE_FILTER", raising=False)
    out = _fact_sampler.sample_facts(
        "wine_regions", count=10, strategy="template"
    )
    texts = {f["fact_text"] for f in out}
    # Non-substantive but specific fact must be present in the legacy path.
    assert (
        "Wine is made from grapes in many places around the entire world."
        in texts
    )


def test_filter_enabled_via_env_var(monkeypatch, patched_db):
    """With the env var set to '1', non-substantive facts are dropped from
    the returned set. We assert behaviour rather than log capture (loguru's
    integration with pytest's caplog is brittle in this codebase)."""
    monkeypatch.setenv("OENOBENCH_FACT_SUBSTANTIVE_FILTER", "1")
    out = _fact_sampler.sample_facts(
        "wine_regions", count=10, strategy="template"
    )
    texts = {f["fact_text"] for f in out}
    # Non-substantive facts dropped.
    assert (
        "Wine is made from grapes in many places around the entire world."
        not in texts
    )
    assert (
        "Beaujolais is a small region located within the country of France."
        not in texts
    )
    # Substantive facts retained.
    assert any("100% Nebbiolo" in t for t in texts)
    assert any("méthode champenoise" in t for t in texts)


def test_filter_extends_to_all_strategies():
    """Lever B2: ``_should_apply_iconic_filter`` returns True for every
    one of the five strategy names (was previously only ``fact_to_question``
    + ``template``)."""
    for name in (
        "template",
        "fact_to_question",
        "comparative",
        "scenario_synthesis",
        "distractor_mining",
    ):
        assert _should_apply_iconic_filter(name) is True, name
    # And remains False when no strategy is supplied (unchanged contract).
    assert _should_apply_iconic_filter(None) is False
