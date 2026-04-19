"""γ-2 — Source-fact-anchored template selection tests.

A template marked ``requires_fact_specific=True`` must only fire when the
fact's entities JSONB contains the relevant non-name field. A fact that
lacks the field must NOT match the template even if all other required
entities are present.
"""

from __future__ import annotations

from src.generators.template_generator import (
    TEMPLATES,
    fill_template,
    find_matching_facts,
)


def _by_id(template_id: str) -> dict:
    for t in TEMPLATES:
        if t["id"] == template_id:
            return t
    raise KeyError(template_id)


def _make_fact(entities: list[dict], fact_text: str = "Synthetic test fact.") -> dict:
    return {
        "id": "00000000-0000-0000-0000-000000000001",
        "fact_text": fact_text,
        "domain": "wine_regions",
        "subdomain": "germany_rheingau",
        "entities": entities,
        "source_id": "00000000-0000-0000-0000-000000000099",
        "source_name": "test",
        "source_url": "https://example.com",
        "confidence": 1.0,
        "tags": [],
    }


def test_soil_template_requires_soil_entity():
    """T-REG-SOIL-01 is requires_fact_specific=True for `soil`."""
    template = _by_id("T-REG-SOIL-01")
    assert template["requires_fact_specific"] is True
    assert template["correct_field"] == "soil"

    # Fact WITHOUT soil should NOT match
    fact_no_soil = _make_fact(
        entities=[
            {"type": "region", "name": "Rheingau"},
            {"type": "country", "name": "Germany"},
        ],
    )
    matched = find_matching_facts(template, [fact_no_soil])
    assert matched == []

    # Fact WITH soil SHOULD match
    fact_with_soil = _make_fact(
        entities=[
            {"type": "region", "name": "Rheingau"},
            {"type": "country", "name": "Germany"},
            {"type": "soil", "name": "slate"},
        ],
    )
    matched = find_matching_facts(template, [fact_with_soil])
    assert len(matched) == 1


def test_climate_template_requires_climate_entity():
    template = _by_id("T-REG-CLIMATE-01")
    assert template["requires_fact_specific"] is True
    assert template["correct_field"] == "climate"

    fact_no_climate = _make_fact(
        entities=[
            {"type": "region", "name": "Mosel"},
        ],
    )
    assert find_matching_facts(template, [fact_no_climate]) == []

    fact_with_climate = _make_fact(
        entities=[
            {"type": "region", "name": "Mosel"},
            {"type": "climate", "name": "cool continental"},
        ],
    )
    matched = find_matching_facts(template, [fact_with_climate])
    assert len(matched) == 1


def test_country_identity_template_is_not_fact_specific():
    """Identity templates (region→country) are kept but down-weighted."""
    template = _by_id("T-REG-COUNTRY-01")
    assert template["requires_fact_specific"] is False
    assert template["selection_weight"] < 1.0


def test_aging_template_requires_aging_wine_style_region():
    """T-REG-AGING-01 needs aging + wine_style + region."""
    template = _by_id("T-REG-AGING-01")
    assert template["requires_fact_specific"] is True
    assert template["correct_field"] == "aging"

    incomplete_fact = _make_fact(
        entities=[
            {"type": "region", "name": "Barolo"},
            {"type": "wine_style", "name": "red"},
            # no aging
        ],
    )
    assert find_matching_facts(template, [incomplete_fact]) == []

    complete_fact = _make_fact(
        entities=[
            {"type": "region", "name": "Barolo"},
            {"type": "wine_style", "name": "red"},
            {"type": "aging", "name": "38 months"},
        ],
    )
    assert len(find_matching_facts(template, [complete_fact])) == 1


def test_flagship_grape_template_requires_flagship_grape():
    template = _by_id("T-PRD-GRAPE-01")
    assert template["requires_fact_specific"] is True
    assert template["correct_field"] == "flagship_grape"

    incomplete = _make_fact(
        entities=[{"type": "producer", "name": "Château Margaux"}],
    )
    assert find_matching_facts(template, [incomplete]) == []

    complete = _make_fact(
        entities=[
            {"type": "producer", "name": "Château Margaux"},
            {"type": "flagship_grape", "name": "Cabernet Sauvignon"},
        ],
    )
    assert len(find_matching_facts(template, [complete])) == 1


def test_classification_template_requires_classification_field():
    template = _by_id("T-REG-CLASS2-01")
    assert template["requires_fact_specific"] is True
    assert template["correct_field"] == "classification"

    no_class = _make_fact(entities=[{"type": "region", "name": "Bordeaux"}])
    assert find_matching_facts(template, [no_class]) == []

    with_class = _make_fact(
        entities=[
            {"type": "region", "name": "Bordeaux"},
            {"type": "classification", "name": "AOC"},
        ],
    )
    assert len(find_matching_facts(template, [with_class])) == 1


def test_fill_template_returns_none_when_correct_field_missing():
    """Even if find_matching_facts is bypassed, fill_template must reject."""
    template = _by_id("T-REG-SOIL-01")
    fact = _make_fact(
        entities=[
            {"type": "region", "name": "Rheingau"},
        ],
    )
    out = fill_template(template, fact, [fact], use_embeddings=False)
    assert out is None


def test_fill_template_works_when_all_anchored_fields_present():
    """Smoke test that an anchored template fills end-to-end with use_embeddings=False."""
    template = _by_id("T-REG-SOIL-01")
    correct_fact = _make_fact(
        entities=[
            {"type": "region", "name": "Rheingau"},
            {"type": "soil", "name": "slate"},
        ],
    )
    distractor_facts = [
        _make_fact(
            entities=[
                {"type": "region", "name": f"R{i}"},
                {"type": "soil", "name": s},
            ],
        )
        for i, s in enumerate(["loam", "limestone", "chalk", "clay", "gravel"])
    ]
    out = fill_template(
        template, correct_fact, [correct_fact] + distractor_facts, use_embeddings=False
    )
    assert out is not None
    assert out["correct_answer_text"] == "slate"
    # All 4 options must have unique text
    texts = [o["text"] for o in out["options"]]
    assert len(set(texts)) == 4
    assert "slate" in texts


def test_majority_of_templates_are_fact_specific():
    """Sanity check: after the γ-2 overhaul, most templates should be fact-specific."""
    fact_specific = sum(1 for t in TEMPLATES if t.get("requires_fact_specific"))
    assert fact_specific >= len(TEMPLATES) // 2, (
        f"Only {fact_specific}/{len(TEMPLATES)} templates are fact-specific; "
        "the γ-2 overhaul expected more than half."
    )


def test_identity_templates_have_low_selection_weight():
    """Identity (non-fact-specific) templates should be down-weighted ≤ 0.5."""
    for t in TEMPLATES:
        if not t.get("requires_fact_specific"):
            assert t["selection_weight"] <= 0.5, (
                f"Identity template {t['id']} has weight {t['selection_weight']}; "
                "should be ≤ 0.5 so fact-specific templates are preferred."
            )
