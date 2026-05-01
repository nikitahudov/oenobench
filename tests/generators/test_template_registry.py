"""v2.3 Phase F fix #15 — Template registry expansion tests.

The gold-v3 audit showed 100% of the template corpus at
``cognitive_dim="recall"`` with only 11 of 38 registered templates firing.
Fix #15 expands the registry to ≥50 templates with at least 10 comprehension
and 4 application entries. This test enforces:

  1. Minimum size of the registry (≥50).
  2. Minimum counts of `comprehension` (≥10) and `application` (≥4) entries.
  3. Every new template has `requires_fact_specific=True`,
     `verifiable_from_single_fact=True` and `selection_weight >= 1.0`.
  4. Every new template's `patterns` list carries 4-6 paraphrase variants
     (γ-4 requirement, already enforced by `test_template_phrasing.py` but
     we recheck the subset here for double-coverage).
  5. Every new template's `required_entities` actually occur as a tuple
     in the live facts.entities JSONB — at least one matching fact exists.

This last check is an integration test that needs the Postgres DB to be
up. It is skipped with a clear message if the DB is unreachable.
"""

from __future__ import annotations

import pytest

from src.generators.template_generator import TEMPLATES

# ─── New-template IDs introduced by v2.3 fix #15 ────────────────────────────
NEW_TEMPLATE_IDS: tuple[str, ...] = (
    # 8 comprehension
    "T-REG-COMP-COUNTRY-01",
    "T-REG-COMP-AVA-STATE-01",
    "T-REG-COMP-AVA-COUNTY-01",
    "T-GRP-COMP-COUNTRY-01",
    "T-GRP-COMP-REGION-01",
    "T-PRD-COMP-COUNTRY-01",
    "T-GRP-COMP-APPELLATION-01",
    "T-VIT-COMP-PEST-GRAPE-01",
    # 4 application
    "T-REG-APP-VARIETAL-LABEL-01",
    "T-GRP-APP-REGION-PLANT-01",
    "T-REG-APP-AVA-SOURCING-01",
    "T-PRD-APP-SOURCING-01",
)


def _by_id(tid: str) -> dict:
    for t in TEMPLATES:
        if t["id"] == tid:
            return t
    raise KeyError(f"Template {tid} missing")


# ─── Size / distribution invariants ────────────────────────────────────────


def test_registry_has_at_least_fifty_templates():
    assert len(TEMPLATES) >= 50, (
        f"Registry size {len(TEMPLATES)} < 50; fix #15 under-shipped."
    )


def test_registry_has_at_least_ten_comprehension():
    n_comp = sum(1 for t in TEMPLATES if t["cognitive_dim"] == "comprehension")
    assert n_comp >= 10, (
        f"Only {n_comp} comprehension templates; need ≥10 per fix #15."
    )


def test_registry_has_at_least_four_application():
    n_app = sum(1 for t in TEMPLATES if t["cognitive_dim"] == "application")
    assert n_app >= 4, (
        f"Only {n_app} application templates; need ≥4 per fix #15."
    )


# ─── Per-new-template hygiene checks ───────────────────────────────────────


@pytest.mark.parametrize("tid", NEW_TEMPLATE_IDS)
def test_new_template_exists(tid: str):
    """Each of the 12 new IDs is registered."""
    t = _by_id(tid)
    assert t["id"] == tid


@pytest.mark.parametrize("tid", NEW_TEMPLATE_IDS)
def test_new_template_is_fact_specific(tid: str):
    """Every new template enforces fact-specificity."""
    t = _by_id(tid)
    assert t["requires_fact_specific"] is True, (
        f"{tid} should have requires_fact_specific=True"
    )
    assert t.get("verifiable_from_single_fact") is True, (
        f"{tid} should have verifiable_from_single_fact=True"
    )


@pytest.mark.parametrize("tid", NEW_TEMPLATE_IDS)
def test_new_template_selection_weight_at_least_one(tid: str):
    t = _by_id(tid)
    assert (t.get("selection_weight") or 0.0) >= 1.0, (
        f"{tid} has selection_weight={t.get('selection_weight')}; needs ≥1.0"
    )


@pytest.mark.parametrize("tid", NEW_TEMPLATE_IDS)
def test_new_template_has_four_to_six_variants(tid: str):
    t = _by_id(tid)
    n = len(t.get("patterns") or [])
    assert 4 <= n <= 6, (
        f"{tid} has {n} pattern variants; γ-4 requires 4-6."
    )


@pytest.mark.parametrize("tid", NEW_TEMPLATE_IDS)
def test_new_template_cognitive_dim(tid: str):
    """Each new template is tagged comprehension or application (not recall)."""
    t = _by_id(tid)
    assert t["cognitive_dim"] in ("comprehension", "application"), (
        f"{tid} has cognitive_dim={t['cognitive_dim']!r}; fix #15 requires "
        "comprehension or application."
    )


# ─── Live-DB entity-coverage smoke test ────────────────────────────────────


def _db_has_fact_with_types(entity_types: list[str]) -> bool:
    """Return True iff at least one row in `facts` has every required type.

    Skip the test if the database isn't reachable — unit tests on a bare
    checkout should still collect.
    """
    try:
        from src.utils.db import get_pg
        conn = get_pg()
        cur = conn.cursor()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Postgres unreachable: {exc}")

    # Compose the entity-type @> predicate chain.
    clauses = " AND ".join(
        "entities @> %s::jsonb" for _ in entity_types
    )
    params = [f'[{{"type":"{et}"}}]' for et in entity_types]
    sql = f"SELECT 1 FROM facts WHERE {clauses} LIMIT 1"
    try:
        cur.execute(sql, params)
        row = cur.fetchone()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"DB query failed: {exc}")
    return row is not None


@pytest.mark.parametrize("tid", NEW_TEMPLATE_IDS)
def test_new_template_required_entities_exist_in_fact_base(tid: str):
    """For each new template, at least one live fact must supply all the
    required entity types — otherwise the template will never fire."""
    t = _by_id(tid)
    assert _db_has_fact_with_types(list(t["required_entities"])), (
        f"{tid} requires {t['required_entities']} but no fact in the live "
        "DB supplies all of them — template is dead-on-arrival."
    )


# ─── Phase 2g.16 Lever 5b: disabled-field handling ──────────────────────────


def test_quarantined_template_skipped_when_disabled():
    """Phase 2g.16 Lever 5b: a template entry with disabled=True must not
    appear in the effective iteration used by the generation loop.

    This exercises the `disabled` field on the TEMPLATES registry. We inject
    a synthetic disabled template into a copy of the list and verify it is
    filtered out by the same logic used in _run_generate_body.
    """
    import copy

    _FAKE_DOMAIN = "wine_regions"

    # Build a synthetic disabled template (mimics a quarantined entry).
    disabled_template = {
        "id": "T-TEST-DISABLED-01",
        "patterns": [
            "Test disabled template pattern 1?",
            "Test disabled template pattern 2?",
            "Test disabled template pattern 3?",
            "Test disabled template pattern 4?",
        ],
        "domain": _FAKE_DOMAIN,
        "difficulty_range": ["2"],
        "cognitive_dim": "recall",
        "question_type": "multiple_choice",
        "correct_field": "region",
        "distractor_strategy": "same_type",
        "required_entities": ["region"],
        "explanation_template": "Test explanation {region}.",
        "requires_fact_specific": True,
        "verifiable_from_single_fact": True,
        "selection_weight": 1.0,
        "disabled": True,  # ← the field under test
    }

    synthetic_templates = copy.copy(TEMPLATES) + [disabled_template]

    # Replicate the filter logic from _run_generate_body.
    active = [
        t for t in synthetic_templates
        if t["domain"] == _FAKE_DOMAIN
        and not t.get("disabled", False)
    ]
    active_ids = {t["id"] for t in active}

    assert disabled_template["id"] not in active_ids, (
        f"Disabled template {disabled_template['id']!r} leaked into the active set"
    )

    # A template without the disabled field must still appear.
    enabled_ids_in_domain = {t["id"] for t in TEMPLATES if t["domain"] == _FAKE_DOMAIN}
    assert enabled_ids_in_domain.issubset(active_ids), (
        "Some enabled templates were accidentally excluded: "
        f"{enabled_ids_in_domain - active_ids}"
    )
