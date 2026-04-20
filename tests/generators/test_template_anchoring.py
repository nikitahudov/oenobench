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


def test_deleted_templates_are_absent():
    """v2.2 fix #8a — identity and superlative templates are DELETED, not kept."""
    deleted_ids = [
        "T-REG-COUNTRY-01",      # region→country identity (world-knowledge)
        "T-REG-GRAPE-01",        # "primary grape" superlative
        "T-REG-STYLE-01",        # "primarily known for" superlative
        "T-REG-NEIGHBOR-01",     # "borders or is near" (can't verify from 1 fact)
        "T-GRP-REGION-01",       # "most strongly associated with" superlative
        "T-GRP-ORIGIN-01",       # grape→country-of-origin (world-knowledge + contested)
        "T-PRD-GRAPE-01",        # producer→flagship grape (superlative)
        "T-PRD-COUNTRY-01",      # producer→country (world-knowledge)
        "T-BIZ-EXPORT-01",       # "largest export market" (superlative)
    ]
    existing = {t["id"] for t in TEMPLATES}
    for tid in deleted_ids:
        assert tid not in existing, (
            f"Template {tid} should have been deleted by v2.2 fix #8a"
        )


def test_authorised_list_rewrites_present():
    """v2.2 fix #8a — two replacement templates use authorised-list phrasing."""
    for tid in ("T-REG-AUTH-GRAPE-01", "T-GRP-AUTH-APPELLATION-01"):
        template = _by_id(tid)
        assert template["requires_fact_specific"] is True
        assert template["verifiable_from_single_fact"] is True


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


# T-PRD-GRAPE-01 flagship_grape template deleted by v2.2 fix #8a —
# its "flagship grape of {producer}" phrasing is superlative and can't be
# proved from a single fact. No replacement; the relationship is better
# tested via comparative/scenario strategies.


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
    """Smoke test that an anchored template fills end-to-end with use_embeddings=False.

    v2.2 fix #8b: the fact_text must literally mention the correct answer
    (source-faithfulness gate), so we give the seed fact a realistic text.
    """
    template = _by_id("T-REG-SOIL-01")
    correct_fact = _make_fact(
        entities=[
            {"type": "region", "name": "Rheingau"},
            {"type": "soil", "name": "slate"},
        ],
        fact_text="The Rheingau wine region is known for its slate soils.",
    )
    # v2.2 fix #8c requires pool size ≥ 20 when embeddings are on; with
    # use_embeddings=False the legacy min-3 fallback is still exercised.
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


def test_all_templates_are_fact_specific_post_v22():
    """v2.2 fix #8a — identity templates deleted. Every surviving template
    must be fact-specific (so low-weight identity-only templates are gone)."""
    for t in TEMPLATES:
        assert t.get("requires_fact_specific") is True, (
            f"Template {t['id']} is not fact-specific; v2.2 fix #8a should "
            "have deleted it."
        )
