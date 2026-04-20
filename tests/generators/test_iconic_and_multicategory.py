"""v2.2 fixes #7 + #11 — iconic-entity FTQ filter and multi-category seed filter."""

from __future__ import annotations

from src.generators._fact_sampler import (
    _fact_has_multi_category_text,
    _fact_is_iconic_only,
    _load_iconic_entities,
)


# ─── Fix #11 — iconic-entity filter ───────────────────────────────────────


def test_iconic_yaml_loads_nonempty() -> None:
    iconic = _load_iconic_entities()
    # Lowercased set should have at least a few dozen entries from the seed YAML.
    assert len(iconic) >= 30, f"Expected ≥30 iconic entries, got {len(iconic)}"
    # Spot-check a handful of expected entries.
    assert "château margaux" in iconic
    assert "dom pérignon" in iconic
    assert "bordeaux 1855" in iconic


def test_fact_with_only_iconic_entity_rejected() -> None:
    fact = {
        "entities": [{"type": "classification", "name": "Bordeaux 1855"}],
        "fact_text": "The Bordeaux 1855 classification is a legal framework.",
    }
    assert _fact_is_iconic_only(fact) is True


def test_fact_with_one_nonobscure_entity_accepted() -> None:
    fact = {
        "entities": [
            {"type": "classification", "name": "Bordeaux 1855"},
            {"type": "producer", "name": "Château Chasse-Spleen"},
        ],
        "fact_text": "Château Chasse-Spleen is a Cru Bourgeois in the Médoc.",
    }
    assert _fact_is_iconic_only(fact) is False


def test_fact_with_empty_entities_not_iconic() -> None:
    assert _fact_is_iconic_only({"entities": [], "fact_text": ""}) is False


# ─── Fix #7 — multi-category seed filter ─────────────────────────────────


def test_fact_text_red_and_white_flagged() -> None:
    assert _fact_has_multi_category_text(
        "The estate produces red and white wines from the same parcel."
    ) is True


def test_fact_text_sparkling_vs_still_flagged() -> None:
    assert _fact_has_multi_category_text(
        "The zone permits sparkling vs still production under separate rules."
    ) is True


def test_fact_text_sparkling_by_blending_red_and_white_flagged() -> None:
    # The chatgpt scenario stem that caused C2 audit failure.
    assert _fact_has_multi_category_text(
        "The rosé cuvée is made by blending red and white base wines."
    ) is True


def test_single_category_fact_not_flagged() -> None:
    assert _fact_has_multi_category_text("Barolo is a red wine from Piedmont.") is False
    assert _fact_has_multi_category_text(
        "Riesling produces white wines of high acidity."
    ) is False


def test_empty_or_none_fact_not_flagged() -> None:
    assert _fact_has_multi_category_text("") is False
    assert _fact_has_multi_category_text(None) is False  # type: ignore[arg-type]
