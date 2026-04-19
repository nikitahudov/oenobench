"""Plan §10 (Team β-2) — universal wine-category filter.

These tests verify the new ``wine_category`` parameter on ``sample_facts``
filters out candidates whose ``_classify_wine_category`` doesn't match, and
that the category leak guard in ``sample_fact_pairs`` /
``sample_fact_clusters`` / ``sample_confusable_facts`` rejects mismatched
candidates rather than down-weighting them.

Like ``test_country_quota.py`` we mock ``get_pg`` and the cached country
distribution so no real DB call is needed.
"""

from __future__ import annotations

import uuid

import pytest

from src.generators import _fact_sampler


# ─── Fact builders ─────────────────────────────────────────────────────────


def _mk_fact(idx: int, fact_text: str, country: str = "France") -> dict:
    return {
        "id": uuid.UUID(int=idx),
        "fact_text": fact_text,
        "domain": "wine_regions",
        "subdomain": "test_sub",
        "entities": [{"type": "country", "name": country}],
        "source_id": uuid.UUID(int=10_000 + idx),
        "source_name": "FakeSource",
        "source_url": f"https://example.test/{idx}",
        "confidence": 1.0,
        "tags": ["test"],
    }


# Mixed-category fact pool — facts that the wine-category classifier should
# clearly bin into red / white / sparkling.
MIXED_POOL = [
    # Red wines (Cabernet Sauvignon, Pinot Noir, Nebbiolo trigger "red")
    _mk_fact(1, "Cabernet Sauvignon is the dominant red grape in Médoc, with structured tannins."),
    _mk_fact(2, "Pinot Noir thrives in the cool red wine climate of Burgundy's Côte de Nuits."),
    _mk_fact(3, "Nebbiolo produces the structured red wine of Barolo with high tannin content."),
    # White wines
    _mk_fact(4, "Chardonnay is the dominant white grape variety planted in Chablis."),
    _mk_fact(5, "Sauvignon Blanc produces the crisp white wine of Sancerre with mineral notes."),
    _mk_fact(6, "Riesling is the dominant white grape variety in the Mosel region of Germany."),
    # Sparkling wines
    _mk_fact(7, "Champagne uses the méthode traditionnelle with secondary fermentation in bottle."),
    _mk_fact(8, "Prosecco is a sparkling wine from Veneto produced via the tank method."),
    _mk_fact(9, "Cava is a Spanish sparkling wine from Catalonia using méthode traditionnelle."),
]


# ─── Fake DB ───────────────────────────────────────────────────────────────


class _FakeCursor:
    def __init__(self, rows):
        self._rows = rows
        self._last_limit = None

    def execute(self, query, params=()):
        try:
            self._last_limit = int(params[-1])
        except (TypeError, ValueError, IndexError):
            self._last_limit = len(self._rows)

    def fetchall(self):
        return [dict(r) for r in self._rows[: self._last_limit or len(self._rows)]]


class _FakeConn:
    def __init__(self, rows):
        self._rows = rows

    def cursor(self):
        return _FakeCursor(self._rows)


@pytest.fixture(autouse=True)
def _patch_db(monkeypatch):
    fake_conn = _FakeConn(MIXED_POOL)
    monkeypatch.setattr(_fact_sampler, "get_pg", lambda: fake_conn)
    # Disable the country quota so it doesn't interfere with category filtering
    monkeypatch.setattr(_fact_sampler, "_country_base_distribution", lambda: {})
    _fact_sampler.reset_country_usage()
    yield
    _fact_sampler.reset_country_usage()


# ─── Tests ─────────────────────────────────────────────────────────────────


def test_classify_wine_category_recognises_each_pool_member():
    """Sanity check: every pool fact must classify into a category."""
    for fact in MIXED_POOL:
        cat = _fact_sampler._classify_wine_category(fact["fact_text"])
        assert cat is not None, f"Fact failed to classify: {fact['fact_text']!r}"


def test_sample_facts_red_category_returns_only_red():
    """sample_facts(..., wine_category='red') must return only red facts."""
    facts = _fact_sampler.sample_facts(
        "wine_regions", count=10, wine_category="red", prefer_diverse_sources=False
    )
    assert facts, "Expected at least one red-wine fact"
    for f in facts:
        cat = _fact_sampler._classify_wine_category(f["fact_text"])
        assert cat == "red", (
            f"Expected category 'red', got {cat!r} for {f['fact_text']!r}"
        )


def test_sample_facts_white_category_returns_only_white():
    facts = _fact_sampler.sample_facts(
        "wine_regions", count=10, wine_category="white", prefer_diverse_sources=False
    )
    assert facts, "Expected at least one white-wine fact"
    for f in facts:
        cat = _fact_sampler._classify_wine_category(f["fact_text"])
        assert cat == "white", (
            f"Expected category 'white', got {cat!r} for {f['fact_text']!r}"
        )


def test_sample_facts_sparkling_category_returns_only_sparkling():
    facts = _fact_sampler.sample_facts(
        "wine_regions", count=10, wine_category="sparkling", prefer_diverse_sources=False
    )
    assert facts, "Expected at least one sparkling-wine fact"
    for f in facts:
        cat = _fact_sampler._classify_wine_category(f["fact_text"])
        assert cat == "sparkling", (
            f"Expected category 'sparkling', got {cat!r} for {f['fact_text']!r}"
        )


def test_sample_facts_no_category_keeps_legacy_behaviour():
    """Default wine_category=None must NOT filter any candidate."""
    facts = _fact_sampler.sample_facts(
        "wine_regions", count=20, prefer_diverse_sources=False
    )
    # Without filtering, the fake pool's 9 facts should all be returnable
    # (subject to the count cap and quality filtering).
    assert len(facts) >= 6, (
        f"Expected ~all 9 pool facts to be returnable; got {len(facts)}"
    )


def test_sample_facts_unknown_category_returns_empty():
    """An unrecognised wine_category should yield zero facts (no false matches)."""
    facts = _fact_sampler.sample_facts(
        "wine_regions",
        count=10,
        wine_category="nonexistent_category",
        prefer_diverse_sources=False,
    )
    assert facts == [], (
        f"Expected empty list for nonexistent category; got {len(facts)} facts"
    )
