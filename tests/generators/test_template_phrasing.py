"""γ-4 — Phrasing diversification tests.

For each template we expect 4-6 paraphrase variants. The selection is
deterministic per (template_id, entity_name) so the same input always
yields the same phrasing — but across different entities we should see
≥ 3 distinct phrasings within a sample of 50.
"""

from __future__ import annotations

import re

from src.generators.template_generator import TEMPLATES, select_pattern_variant


def _by_id(template_id: str) -> dict:
    for t in TEMPLATES:
        if t["id"] == template_id:
            return t
    raise KeyError(template_id)


_FAKE_REGIONS = [
    # 50 distinct, vaguely regional-sounding strings — enough surface
    # variety to exercise the SHA-256 picker across all 6 variants.
    "Rheingau", "Mosel", "Pfalz", "Nahe", "Rheinhessen", "Baden", "Württemberg",
    "Franken", "Saale-Unstrut", "Sachsen", "Mittelrhein", "Hessische Bergstrasse",
    "Bordeaux", "Burgundy", "Champagne", "Loire", "Rhône", "Alsace",
    "Languedoc", "Provence", "Beaujolais", "Jura", "Savoie", "Cognac",
    "Tuscany", "Piedmont", "Veneto", "Sicily", "Sardinia", "Lombardy",
    "Friuli", "Marche", "Umbria", "Lazio", "Campania", "Puglia",
    "Rioja", "Ribera del Duero", "Priorat", "Penedès", "Rías Baixas", "Jerez",
    "Napa Valley", "Sonoma", "Willamette", "Walla Walla", "Finger Lakes", "Central Coast",
    "Mendoza", "Maipo Valley",
]


def test_template_has_at_least_four_variants():
    """Every template carries 4-6 paraphrase variants per the γ-4 spec."""
    for t in TEMPLATES:
        n_variants = len(t.get("patterns") or [])
        assert n_variants >= 4, (
            f"Template {t['id']} has only {n_variants} pattern variants; "
            "γ-4 requires at least 4."
        )
        assert n_variants <= 6, (
            f"Template {t['id']} has {n_variants} variants; γ-4 caps at 6."
        )


def test_select_pattern_variant_is_deterministic():
    """Same (template, entity) pair must always yield the same phrasing."""
    template = _by_id("T-REG-SOIL-01")
    pick_a = select_pattern_variant(template, "Rheingau")
    pick_b = select_pattern_variant(template, "Rheingau")
    assert pick_a == pick_b


def test_select_pattern_variant_different_entities_rotate():
    """Across many entities we should observe ≥ 3 distinct phrasings (γ-4 done-criterion)."""
    template = _by_id("T-REG-SOIL-01")
    seen: set[str] = set()
    for region in _FAKE_REGIONS:
        seen.add(select_pattern_variant(template, region))
    assert len(seen) >= 3, (
        f"Only {len(seen)} distinct phrasings produced for T-REG-SOIL-01 across "
        f"{len(_FAKE_REGIONS)} entities — phrasing diversification not working."
    )


def test_phrasing_distribution_across_multiple_templates():
    """Several different templates should each yield ≥ 3 distinct phrasings."""
    # v2.2 fix #8a — T-REG-GRAPE-01 replaced by T-REG-AUTH-GRAPE-01;
    # T-PRD-GRAPE-01 deleted (flagship-grape superlative).
    template_ids = [
        "T-REG-CLIMATE-01",
        "T-REG-AUTH-GRAPE-01",
        "T-GRP-AROMA-01",
        "T-PRD-APPELLATION-01",
        "T-WMK-TECHNIQUE-01",
        "T-VIT-PEST-01",
    ]
    for tid in template_ids:
        template = _by_id(tid)
        seen: set[str] = set()
        for region in _FAKE_REGIONS:
            seen.add(select_pattern_variant(template, region))
        assert len(seen) >= 3, (
            f"Template {tid} only produced {len(seen)} distinct phrasings."
        )


def test_total_phrasing_count_in_target_range():
    """Whole catalogue should land in the 170-320 variant range.

    v2.2 fix #8a deleted 12 templates (superlative + world-knowledge), which
    trimmed the variant total from ~260 to ~190. The γ-5 LLM paraphrase
    post-pass (default-on in v2.2) provides the remaining anti-detectability
    diversity, so the raw variant count can be lower.
    """
    total = sum(len(t.get("patterns") or []) for t in TEMPLATES)
    assert 170 <= total <= 320, (
        f"Total phrasing variants is {total}; expected 170-320 range."
    )


def test_variants_share_required_placeholders():
    """All variants of a template must reference the same {placeholder} set."""
    placeholder_re = re.compile(r"\{(\w+)\}")
    for t in TEMPLATES:
        variants = t.get("patterns") or []
        if len(variants) < 2:
            continue
        slot_sets = [
            frozenset(placeholder_re.findall(v)) for v in variants
        ]
        first = slot_sets[0]
        for i, s in enumerate(slot_sets[1:], 1):
            assert s == first, (
                f"Template {t['id']} variant {i} has placeholders {sorted(s)}, "
                f"but variant 0 uses {sorted(first)} — mismatch will break formatting."
            )


def test_variants_required_placeholders_subset_of_required_entities():
    """Every {placeholder} in any variant must be in required_entities (γ-4 sanity)."""
    placeholder_re = re.compile(r"\{(\w+)\}")
    allowed_extra = {"subdomain"}
    for t in TEMPLATES:
        required = set(t["required_entities"]) | allowed_extra
        for v in (t.get("patterns") or []):
            slots = set(placeholder_re.findall(v))
            extra = slots - required
            assert not extra, (
                f"Template {t['id']} variant {v!r} uses unknown placeholders {extra}; "
                f"required_entities is {sorted(required)}."
            )


def test_50_instances_yield_at_least_three_distinct_phrasings_for_specific_template():
    """The done-criterion phrasing test from the γ-4 brief."""
    template = _by_id("T-REG-CLIMATE-01")
    phrasings: list[str] = []
    for region in _FAKE_REGIONS:
        phrasings.append(select_pattern_variant(template, region))
    assert len(phrasings) == 50
    assert len(set(phrasings)) >= 3, (
        f"50 instances of T-REG-CLIMATE-01 only produced {len(set(phrasings))} "
        "distinct phrasings — γ-4 done criterion failed."
    )


def test_explanation_template_is_kept_singular():
    """The explanation_template stays single-form (it's not user-facing in the same way)."""
    for t in TEMPLATES:
        assert isinstance(t["explanation_template"], str)
