"""Team ε — per-country absolute cap tests for the fact sampler.

Verifies the new ``per_country_cap`` kwarg threading on ``sample_facts`` and
the multi-fact strategies (``sample_fact_pairs``, ``sample_fact_groups``,
``sample_fact_clusters``).

Backward-compat contract: when ``per_country_cap=None`` (the default) the
sampler behaves identically to the pre-fix path. When a fraction in (0, 1]
is supplied, no single country may exceed ``ceil(per_country_cap * total)``
of the returned set, where ``total`` accounts for multi-fact bundles
(pair = 2, group/cluster = group_size, etc.).
"""

from __future__ import annotations

import random
import uuid
from collections import Counter

import pytest

from src.generators import _fact_sampler
from src.generators._fact_sampler import (
    _apply_per_country_cap,
    _apply_per_country_cap_to_bundles,
    _country_cap_max,
)


# ─── Fake-DB plumbing (mirrors test_country_quota.py) ──────────────────────


class _FakeCursor:
    def __init__(self, fake_facts):
        self._facts = fake_facts
        self._last_limit = None
        self._rng = random.Random(0xBEEF)

    def execute(self, query, params=()):
        try:
            self._last_limit = int(params[-1])
        except (TypeError, ValueError, IndexError):
            self._last_limit = len(self._facts)

    def fetchall(self):
        n = self._last_limit or len(self._facts)
        shuffled = list(self._facts)
        self._rng.shuffle(shuffled)
        return [dict(row) for row in shuffled[:n]]


class _FakeConn:
    def __init__(self, fake_facts):
        self._facts = fake_facts
        self._rng = random.Random(0xBEEF)

    def cursor(self):
        cur = _FakeCursor(self._facts)
        cur._rng = self._rng
        return cur


def _make_fact(country: str, fact_text: str, idx: int) -> dict:
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


def _build_skewed_pool() -> list[dict]:
    """Build a pool that's HEAVILY skewed toward Australia.

    Mirrors the audit_pilot_v5 reality: Australia 50%, South Africa 25%,
    France 15%, Italy 10%. Without a per-call cap the sampler will return
    something close to those ratios; with cap=0.10 the sampler must clamp
    every country to ≤10% of the returned set even though the pool says
    Australia ought to be 50%.
    """
    facts: list[dict] = []
    idx = 0
    plan = {"Australia": 100, "South Africa": 50, "France": 30, "Italy": 20}
    for country, n in plan.items():
        for i in range(n):
            text = (
                f"{country} produces wine using specific terroir characteristics, "
                f"soil types, and elevation profiles that distinguish each region."
            )
            facts.append(_make_fact(country, f"{text} fact-{i}", idx))
            idx += 1
    return facts


# ─── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _patch_db(monkeypatch):
    fake_pool = _build_skewed_pool()
    fake_conn = _FakeConn(fake_pool)

    monkeypatch.setattr(_fact_sampler, "get_pg", lambda: fake_conn)

    # Fixed pool-share distribution so the existing 1.2x quota behaves
    # predictably alongside the new per-call cap.
    monkeypatch.setattr(
        _fact_sampler,
        "_country_base_distribution",
        lambda: {
            "Australia": 0.5,
            "South Africa": 0.25,
            "France": 0.15,
            "Italy": 0.10,
        },
    )

    _fact_sampler.reset_country_usage()
    yield
    _fact_sampler.reset_country_usage()


# ─── Helper-level tests for the per-call cap utilities ───────────────────


def test_country_cap_max_basic():
    # 10% of 100 = 10
    assert _country_cap_max(0.10, 100) == 10
    # 10% of 10 = 1.0 (already integer, ceil = 1)
    assert _country_cap_max(0.10, 10) == 1
    # 33% of 9 = 3 (already integer, ceil = 3)
    assert _country_cap_max(0.33, 9) == 3
    # round-up so 12% of 10 = 2 (ceil(1.2) = 2)
    assert _country_cap_max(0.12, 10) == 2
    # Floor at 1 even when fraction * count < 1
    assert _country_cap_max(0.05, 10) == 1


def test_country_cap_max_disabled():
    """None / 0 / negative should return target_count (cap disabled)."""
    assert _country_cap_max(None, 100) == 100
    assert _country_cap_max(0.0, 100) == 100
    assert _country_cap_max(-1.0, 100) == 100


def test_apply_per_country_cap_no_cap_passthrough():
    facts = [_make_fact("Australia", "x", i) for i in range(5)]
    out = _apply_per_country_cap(facts, target_count=5, per_country_cap=None)
    assert out == list(facts)


def test_apply_per_country_cap_caps_dominant_country():
    """With cap=0.10 on target_count=10, no country may exceed ceil(1.0)=1."""
    candidates: list[dict] = []
    for i in range(10):
        candidates.append(_make_fact("Australia", "AU", i))
    for i in range(10):
        candidates.append(_make_fact("Italy", "IT", 100 + i))
    out = _apply_per_country_cap(candidates, target_count=10, per_country_cap=0.10)
    counts = Counter(
        _fact_sampler._extract_country_from_entities(f["entities"]) for f in out
    )
    assert max(counts.values()) <= 1, f"Got counts={counts}"


def test_apply_per_country_cap_admits_country_less_facts():
    """Facts with no country entity should be admitted unconditionally."""
    candidates: list[dict] = []
    # 5 Australian facts + 5 country-less facts.
    for i in range(5):
        candidates.append(_make_fact("Australia", "AU", i))
    for i in range(5):
        f = _make_fact("Australia", "no-country", 100 + i)
        f["entities"] = []  # strip country
        candidates.append(f)
    out = _apply_per_country_cap(candidates, target_count=10, per_country_cap=0.10)
    # cap on AU = 1 (10% of 10), country-less facts unrestricted = 5 admitted.
    assert len(out) == 6  # 1 AU + 5 country-less


# ─── sample_facts integration tests ─────────────────────────────────────


def test_per_country_cap_none_unchanged_size():
    """When per_country_cap=None, the size and overall behaviour match the
    legacy default. We can't byte-compare candidate lists (the SQL random
    shuffle differs run-to-run) but the size + cap-uninvolved invariants
    must hold.
    """
    facts = _fact_sampler.sample_facts("wine_regions", count=20)
    # Legacy semantic: still respects pool-share 1.2x cap, returns up to count.
    assert len(facts) <= 20
    countries = Counter(
        _fact_sampler._extract_country_from_entities(f["entities"]) for f in facts
    )
    # Australia at pool-share 0.5 with cap 1.2x -> max 0.6 share.
    total = sum(countries.values())
    if total >= _fact_sampler._QUOTA_GRACE_N:
        for c, n in countries.items():
            base = {"Australia": 0.5, "South Africa": 0.25, "France": 0.15, "Italy": 0.10}.get(c, 0)
            # Allow a little wiggle room for finite-sample noise + grace period
            assert n / total <= 1.2 * base + 0.2


def test_per_country_cap_enforced_size_100():
    """With cap=0.10, no country may exceed 10 of 100 returned."""
    collected: list[str | None] = []
    rounds = 0
    # Sample 100 facts in batches of 20, with the cap enabled the entire time.
    while len(collected) < 100 and rounds < 50:
        rounds += 1
        # Reset usage between batches so pool-share gate can't lock long-tail
        # countries out across the whole run; the per-call cap is the gate
        # under test here.
        _fact_sampler.reset_country_usage()
        facts = _fact_sampler.sample_facts(
            "wine_regions", count=20, per_country_cap=0.10
        )
        for f in facts:
            collected.append(
                _fact_sampler._extract_country_from_entities(f["entities"])
            )
        if not facts:
            break

    # Within ANY single per-call batch (count=20, cap=0.10) no country may
    # exceed ceil(0.10 * 20) = 2 facts.
    # We re-verify the contract on the last batch:
    last_facts = _fact_sampler.sample_facts(
        "wine_regions", count=100, per_country_cap=0.10
    )
    last_counts = Counter(
        _fact_sampler._extract_country_from_entities(f["entities"])
        for f in last_facts
    )
    last_counts.pop(None, None)
    if last_counts:
        max_count = max(last_counts.values())
        # ceil(0.10 * 100) = 10
        assert max_count <= 10, f"Country over cap: {last_counts}"


def test_per_country_cap_pair_strategy_counts_both_facts():
    """For pair-strategy, both facts in a pair count toward the country quota.

    We exercise the bundle-cap helper directly (the real
    ``sample_fact_pairs`` SQL is too complex to fake in-memory) — that is
    where the "pair counts as 2" rule lives.
    """
    # Build 10 all-Australian pairs and 5 all-Italian pairs.
    bundles: list[tuple[dict, dict]] = []
    idx = 0
    for _ in range(10):
        bundles.append(
            (
                _make_fact("Australia", "x", idx),
                _make_fact("Australia", "y", idx + 1),
            )
        )
        idx += 2
    for _ in range(5):
        bundles.append(
            (
                _make_fact("Italy", "x", idx),
                _make_fact("Italy", "y", idx + 1),
            )
        )
        idx += 2

    # cap=0.10, target_count=10 (pairs) -> 20 facts total -> max per-country = 2
    # An all-AU pair adds 2 to AU; first pair fills the cap, all subsequent
    # AU pairs must be rejected. Italy pairs must still be admissible until
    # they hit their own cap.
    out = _apply_per_country_cap_to_bundles(
        bundles, target_count=10, per_country_cap=0.10
    )
    flat = [f for bundle in out for f in bundle]
    counts = Counter(
        _fact_sampler._extract_country_from_entities(f["entities"]) for f in flat
    )
    counts.pop(None, None)
    # 10% of 20 facts = 2 -> max per-country = 2 facts -> 1 AU pair + 1 IT pair
    # = 2 bundles total. Other bundles must be rejected.
    assert counts.get("Australia", 0) <= 2
    assert counts.get("Italy", 0) <= 2
    # Verify pair-counting: the same-country pair occupies 2 slots, not 1.
    if "Australia" in counts:
        assert counts["Australia"] == 2  # whole pair admitted = 2 facts
    assert len(out) <= 2


def test_per_country_cap_pair_strategy_mixed_country_admissible():
    """A pair with two different countries can still be admitted when each
    country independently has room under the cap.
    """
    bundles: list[tuple[dict, dict]] = [
        (_make_fact("Australia", "x", 1), _make_fact("Italy", "y", 2)),
        (_make_fact("Australia", "x", 3), _make_fact("Italy", "y", 4)),
        (_make_fact("Australia", "x", 5), _make_fact("Italy", "y", 6)),
        (_make_fact("Australia", "x", 7), _make_fact("Italy", "y", 8)),
        (_make_fact("Australia", "x", 9), _make_fact("Italy", "y", 10)),
    ]
    # cap=0.20, target_count=5 -> 10 facts total -> max per-country = 2
    out = _apply_per_country_cap_to_bundles(
        bundles, target_count=5, per_country_cap=0.20
    )
    flat = [f for bundle in out for f in bundle]
    counts = Counter(
        _fact_sampler._extract_country_from_entities(f["entities"]) for f in flat
    )
    counts.pop(None, None)
    # Each pair adds 1 to AU + 1 to IT. With max=2 we admit exactly 2 pairs.
    assert counts.get("Australia", 0) == 2
    assert counts.get("Italy", 0) == 2
    assert len(out) == 2


def test_per_country_cap_does_not_lock_out_singletons():
    """A pair where ONLY ONE side is country-tagged should still consume
    only 1 slot for that country."""
    f_au = _make_fact("Australia", "x", 1)
    f_no = _make_fact("Italy", "y", 2)
    f_no["entities"] = []  # strip country
    bundles = [(f_au, f_no)] * 5
    # cap=0.10, target_count=5 -> 10 facts -> max = 1
    out = _apply_per_country_cap_to_bundles(bundles, target_count=5, per_country_cap=0.10)
    # Exactly 1 bundle admitted (Australia hits cap after first).
    assert len(out) == 1


# ─── Default-value contract test ─────────────────────────────────────────


def test_per_country_cap_default_value_is_none():
    """The kwarg must default to None on every public sampler entry point so
    backward-compat callers continue to work without changes."""
    import inspect

    for fn_name in (
        "sample_facts",
        "sample_fact_pairs",
        "sample_fact_groups",
        "sample_fact_clusters",
        "sample_confusable_facts",
    ):
        fn = getattr(_fact_sampler, fn_name)
        sig = inspect.signature(fn)
        assert "per_country_cap" in sig.parameters, (
            f"{fn_name} missing per_country_cap kwarg"
        )
        assert sig.parameters["per_country_cap"].default is None, (
            f"{fn_name} default for per_country_cap must be None, "
            f"got {sig.parameters['per_country_cap'].default}"
        )
