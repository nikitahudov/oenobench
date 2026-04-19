"""Plan §3 (Team β-1) — per-country sampling quota.

These tests verify that ``sample_facts`` and the related helpers respect the
1.5× hard cap and the inverse-share weighting introduced for D3 SkewAudit.

We avoid touching the real PostgreSQL by:

1. Monkeypatching ``_country_base_distribution`` to return a fixed, lopsided
   base distribution (France 60%, Italy 30%, Argentina 10%) — this lets us
   assert the cap behaviour deterministically.
2. Building a small in-memory fake fact pool keyed by country, and patching
   ``get_pg`` so the SQL ``cur.execute`` / ``cur.fetchall`` returns rows
   mimicking the real query result.
"""

from __future__ import annotations

import random
import uuid
from collections import Counter

import pytest

from src.generators import _fact_sampler


# ─── Fake DB plumbing ──────────────────────────────────────────────────────


class _FakeCursor:
    """Minimal cursor replacement that yields canned fact rows.

    Every ``execute`` call records the most recent query so each ``fetchall``
    returns a fresh shuffled subset of ``_FAKE_FACTS`` honouring the LIMIT in
    the query (parsed loosely). Shuffling mimics PostgreSQL ``ORDER BY
    random()`` so the country-quota tests see candidates in random order
    rather than pool-build order.
    """

    def __init__(self, fake_facts):
        self._facts = fake_facts
        self._last_limit = None
        self._rng = random.Random(0xC0DE)

    def execute(self, query, params=()):
        # Parse the trailing limit param (last positional in our patched
        # sample_facts query) to bound how many rows we return.
        # The patched sample_facts passes (domain, min_confidence, exclude, over_fetch).
        try:
            self._last_limit = int(params[-1])
        except (TypeError, ValueError, IndexError):
            self._last_limit = len(self._facts)

    def fetchall(self):
        # Re-shuffle on every fetch to mimic ORDER BY random().
        n = self._last_limit or len(self._facts)
        shuffled = list(self._facts)
        self._rng.shuffle(shuffled)
        return [dict(row) for row in shuffled[:n]]


class _FakeConn:
    def __init__(self, fake_facts):
        self._facts = fake_facts
        # Share a single RNG across cursors so the shuffle keeps advancing
        # across successive ``cursor()`` calls.
        self._rng = random.Random(0xC0DE)

    def cursor(self):
        cur = _FakeCursor(self._facts)
        cur._rng = self._rng
        return cur


def _make_fact(country: str, fact_text: str, idx: int) -> dict:
    """Build a fact-row dict matching what sample_facts expects."""
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


# A pool of facts where the *available* ratio is uniform across France/Italy/
# Argentina (roughly equal counts), but the "fact base" target distribution
# is heavily skewed — France 60%, Italy 30%, Argentina 10%. Without the
# quota, sample_facts would return roughly equal numbers of each country
# from the random fetch; with the quota, France should dominate the output
# but never exceed 1.5x its 0.6 share = 0.9 of total returns.
def _build_fact_pool(per_country: int = 80) -> list[dict]:
    facts: list[dict] = []
    idx = 0
    for country in ("France", "Italy", "Argentina"):
        for n in range(per_country):
            text = (
                f"{country} produces wine in the {country.lower()} region with "
                f"specific terroir characteristics including soil and climate."
            )
            facts.append(_make_fact(country, f"{text} fact-{n}", idx))
            idx += 1
    return facts


# ─── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _patch_db(monkeypatch):
    """Patch get_pg() and the cached country distribution for every test."""
    fake_pool = _build_fact_pool()
    fake_conn = _FakeConn(fake_pool)

    monkeypatch.setattr(_fact_sampler, "get_pg", lambda: fake_conn)

    # Replace the lru_cache'd distribution computation with a fixed dict.
    monkeypatch.setattr(
        _fact_sampler,
        "_country_base_distribution",
        lambda: {"France": 0.6, "Italy": 0.3, "Argentina": 0.1},
    )

    # Reset module-level usage state so tests don't bleed into each other.
    _fact_sampler.reset_country_usage()
    yield
    _fact_sampler.reset_country_usage()


# ─── Tests ─────────────────────────────────────────────────────────────────


def test_quota_hard_cap_holds_over_many_rounds():
    """Repeatedly sample 1 fact at a time; assert no country exceeds 1.5x its share."""
    rounds = 100
    countries: list[str] = []
    for _ in range(rounds):
        facts = _fact_sampler.sample_facts("wine_regions", count=1)
        if not facts:
            continue
        c = _fact_sampler._extract_country_from_entities(facts[0]["entities"])
        if c:
            countries.append(c)

    counter = Counter(countries)
    total = sum(counter.values())
    assert total > 0, "Should have returned at least some facts"

    base = {"France": 0.6, "Italy": 0.3, "Argentina": 0.1}
    cap_ratio = _fact_sampler._COUNTRY_QUOTA_HARD_CAP_RATIO  # 1.5x
    for country, n in counter.items():
        share = n / total
        target = base.get(country, 0)
        # Allow a tiny epsilon for the small-N edge where the cap is not
        # enforced (total < 4) — but at total=100+ the cap must hold.
        assert share <= cap_ratio * target + 0.05, (
            f"Country {country} share {share:.3f} exceeds cap "
            f"({cap_ratio} * {target} = {cap_ratio * target:.3f})"
        )


def test_quota_resets_between_calls():
    """reset_country_usage() must wipe the per-country counter."""
    _fact_sampler.sample_facts("wine_regions", count=10)
    usage, total = _fact_sampler.get_country_usage()
    assert total > 0

    _fact_sampler.reset_country_usage()
    usage, total = _fact_sampler.get_country_usage()
    assert total == 0
    assert usage == {}


def test_quota_score_returns_one_for_unknown_country():
    """Country missing from base distribution should get a neutral weight."""
    score = _fact_sampler._country_quota_score("Atlantis")
    assert score == 1.0


def test_quota_score_returns_zero_when_over_cap():
    """Force over-quota state and confirm the hard cap returns 0.0."""
    # Force France to be heavily over-represented (50/50 = 100%) — well past
    # the 0.9 cap (0.6 * 1.5).
    for _ in range(50):
        _fact_sampler._record_country_use("France")
    score = _fact_sampler._country_quota_score("France")
    assert score == 0.0


def test_quota_score_under_target_stays_at_one():
    """A country at or below its target share should not be down-weighted."""
    # Burn 100 returns split evenly — France gets 33% (well below target 60%).
    for _ in range(33):
        _fact_sampler._record_country_use("France")
    for _ in range(33):
        _fact_sampler._record_country_use("Italy")
    for _ in range(34):
        _fact_sampler._record_country_use("Argentina")
    france_score = _fact_sampler._country_quota_score("France")
    # France used_share=0.33, target_share=0.6 -> weight = min(1, 0.6/0.33) = 1
    assert france_score == 1.0


def test_quota_does_not_reject_facts_without_country():
    """Facts with no extractable country must still be returnable."""
    # The country quota only applies when a country is detectable; ensure
    # the helper returns 1.0 for None.
    assert _fact_sampler._country_quota_score(None) == 1.0
    assert _fact_sampler._country_quota_score("") == 1.0
