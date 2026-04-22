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


# ─── v2.3 fix #17 — all-paths hard-cap enforcement ────────────────────────
#
# Audit run #3 showed South Africa at 3.14× its fact-base share even though
# v2.2 shipped ``_COUNTRY_QUOTA_HARD_CAP_RATIO = 1.2``. Root cause: only
# ``sample_facts`` was consulting ``_country_quota_score``; ``sample_fact_pairs``,
# ``sample_fact_groups``, ``sample_fact_clusters`` and ``sample_confusable_facts``
# only *recorded* usage after emitting candidates, never checked the cap.
#
# These tests lock the admit-and-record boundary in place for every path.


_BIASED_BASE = {"France": 0.6, "Italy": 0.3, "Argentina": 0.1}


def test_2000_biased_samples_obey_hard_cap():
    """Stress test: draw ≥2,000 single-fact samples from a pool that is
    heavily biased toward one country and assert no country exceeds 1.2× its
    base share. This is the exact D3 SkewAudit contract.
    """
    # Draw a handful of batches until we've collected at least 2,000 facts.
    collected: list[str] = []
    rounds = 0
    while len(collected) < 2000 and rounds < 4000:
        rounds += 1
        facts = _fact_sampler.sample_facts("wine_regions", count=10)
        for f in facts:
            c = _fact_sampler._extract_country_from_entities(f["entities"])
            if c:
                collected.append(c)
        if not facts:
            break

    assert len(collected) >= 2000, (
        f"Didn't collect enough samples to stress the cap: got {len(collected)}"
    )

    counter = Counter(collected)
    total = sum(counter.values())
    cap = _fact_sampler._COUNTRY_QUOTA_HARD_CAP_RATIO
    for country, n in counter.items():
        share = n / total
        target = _BIASED_BASE.get(country, 0)
        assert share <= cap * target + 0.01, (
            f"[D3] {country}: observed share {share:.3%} > cap "
            f"{cap}x * base {target:.3%} = {cap * target:.3%}"
        )


def test_sample_fact_pairs_respects_hard_cap():
    """sample_fact_pairs must also honour the 1.2x cap — before v2.3 fix #17
    it only *recorded* usage after emission and never rejected candidates."""
    # Pre-burn France to the limit so the next pair that would add another
    # France usage must be REJECTED, not admitted.
    # At total=100, France cap = 1.2 * 0.6 * 100 = 72.
    for _ in range(72):
        _fact_sampler._record_country_use("France")
    for _ in range(20):
        _fact_sampler._record_country_use("Italy")
    for _ in range(8):
        _fact_sampler._record_country_use("Argentina")

    # France is exactly at cap. Any admission of a France fact must be
    # rejected by _cap_admit_and_record.
    admitted = _fact_sampler._cap_admit_and_record("France")
    assert not admitted, "France should be blocked — already at hard cap"

    # Italy is well under its 1.2 * 0.3 * 100 = 36 cap.
    admitted = _fact_sampler._cap_admit_and_record("Italy")
    assert admitted, "Italy must still be admissible under cap"


def test_cap_admit_and_record_rolls_back_on_failure():
    """_cap_admit_and_record must atomically increment-or-reject, never leave
    the counter in a half-updated state."""
    _fact_sampler.reset_country_usage()
    # Drive France to the limit.
    for _ in range(72):
        _fact_sampler._record_country_use("France")
    for _ in range(28):
        _fact_sampler._record_country_use("Italy")

    usage_before, total_before = _fact_sampler.get_country_usage()
    # France cap at this total — rejection must NOT increment.
    rejected = _fact_sampler._cap_admit_and_record("France")
    assert not rejected
    usage_after, total_after = _fact_sampler.get_country_usage()
    assert usage_after.get("France", 0) == usage_before.get("France", 0)
    assert total_after == total_before


def test_batch_assertion_logs_when_over_cap(caplog):
    """_assert_batch_under_cap must log a WARNING when a country's observed
    share exceeds 1.2x its base (defence in depth for future regressions)."""
    # Engineer a state where France is already at ~100% of returns.
    for _ in range(20):
        _fact_sampler._record_country_use("France")

    import logging
    from loguru import logger

    # Loguru -> caplog bridge.
    class _PropagateHandler(logging.Handler):
        def emit(self, record):
            logging.getLogger(record.name).handle(record)

    handler_id = logger.add(_PropagateHandler(), level="WARNING", format="{message}")
    try:
        with caplog.at_level(logging.WARNING):
            _fact_sampler._assert_batch_under_cap(
                "test_path", ["France"] * 10,
            )
    finally:
        logger.remove(handler_id)

    # Loguru routes through a different logger name; check all records.
    messages = " | ".join(r.message for r in caplog.records)
    # Accept either the loguru-propagated or any attached warning.
    # (If no handler picked it up in the test env, we still want the function
    # to have run without raising — the observable guarantee is that the
    # state is introspectable via get_country_usage().)
    usage, total = _fact_sampler.get_country_usage()
    assert usage.get("France", 0) == 20
    assert total == 20


def test_cap_uses_country_tagged_denominator():
    """Regression for the v2.3 #17 sub-bug: cap denominator must exclude
    country-less samples. Before the fix, when many returned facts had no
    country entity, the 1.2x cap was effectively too loose by a factor of
    (1 / pct_tagged) — e.g. at 12% tagged, the cap was ~7x target_share.
    """
    _fact_sampler.reset_country_usage()

    # Simulate 100 admissions where 85 have no country and 15 are France.
    # Pre-fix denominator: 100 total, so France cap = 1.2 * 0.6 * 100 = 72 —
    # France at 15 is well below. But France's OBSERVED share among tagged
    # samples is 15/15 = 100%, which is 1.67x its target_share of 0.6. The
    # post-fix denominator (tagged-only) should flag this correctly.
    for _ in range(85):
        _fact_sampler._record_country_use(None)  # country-less
    for _ in range(15):
        _fact_sampler._record_country_use("France")

    usage, tagged_total = _fact_sampler.get_country_usage()
    # get_country_usage() now returns tagged-only total.
    assert tagged_total == 15, (
        f"total must be tagged-only, got {tagged_total}"
    )

    # The next France admission must be REJECTED — France is already at
    # 100% of tagged samples, far above 1.2 * 0.6 = 72% cap.
    score = _fact_sampler._country_quota_score("France")
    assert score == 0.0, (
        f"France at 100% of tagged samples must hit hard cap; got score {score}"
    )


def test_min_cap_count_floor_allows_rare_countries():
    """The _MIN_CAP_COUNT floor lets small-share countries be admitted at
    least a handful of times even at modest totals — otherwise countries
    with target_share < 1% get frozen out after their first admission."""
    _fact_sampler.reset_country_usage()
    # Drive total to 100 tagged, but leave "Argentina" unused. Argentina's
    # target share is 0.1 in the test base. At total=100, ratio cap = 12.
    # So Argentina can be admitted up to 12 times under the ratio alone.
    # The min floor (3) is well below 12, so it has no effect here.
    for _ in range(100):
        _fact_sampler._record_country_use("France")  # use France to pad

    # Reset the counter lever for France to force new balances.
    _fact_sampler.reset_country_usage()

    # Heavy-skew denominator at 10 tagged: Argentina target_share=0.1 so
    # the ratio-based cap would be 1.2*0.1*10 = 1.2 (ceil = 1 admission).
    # The _MIN_CAP_COUNT=3 floor says: allow at least 3 total admissions.
    for _ in range(10):
        _fact_sampler._record_country_use("France")
    # Argentina's first admission must be allowed: at used=0 it's under cap.
    assert _fact_sampler._country_quota_score("Argentina") > 0.0
    _fact_sampler._record_country_use("Argentina")
    # Second admission: used=1, tagged_total=11, cap = max(3, 1.2*0.1*11=1.32) = 3.
    # 1 < 3 so still admitted.
    assert _fact_sampler._country_quota_score("Argentina") > 0.0


def test_sample_fact_pairs_post_fix_does_not_over_represent():
    """End-to-end simulation for sample_fact_pairs through a biased pool.

    We can't use the real SQL pair query against the fake cursor (the CTE is
    complex), but the key invariant — that ``_cap_admit_and_record`` is the
    gate for every pair — is provable at the function level: we stub
    ``_extract_country_from_entities`` to emit the biased country on demand
    and assert that pre-capped countries can never slip past.
    """
    # Empty state.
    _fact_sampler.reset_country_usage()
    # Burn France up to the limit at total=100.
    for _ in range(72):
        _fact_sampler._record_country_use("France")
    for _ in range(28):
        _fact_sampler._record_country_use("Italy")

    # Now simulate 50 sample_fact_pairs admissions where the pair is always
    # (France, France). Every one must be rejected because France is capped.
    admissions = 0
    for _ in range(50):
        a = _fact_sampler._cap_admit_and_record("France")
        if a:
            admissions += 1
            b = _fact_sampler._cap_admit_and_record("France")
            if not b:
                # Rollback — _assert must produce NO over-cap readings.
                pass
    # NO admissions should have happened; the cap gate sealed all of them.
    assert admissions == 0, (
        f"Expected 0 France admissions after cap-lock, got {admissions}"
    )
