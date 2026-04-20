"""Regression tests for v2.2 fix #8 template radical overhaul.

Each of the 12 gold-v2 template questions (strategy=template, all 12
entries in data/reports/gold_sheet_v2_scored.csv) must now either be
rejected by one of the new gates (8a purge, 8b source-faithfulness,
8c distractor-pool type-gating, 8d difficulty table) OR, if still
produced, have a corrected difficulty / distractor set.

The Gemini verifier (8e) is not exercised here — it requires network
and is covered by integration-level dry-runs.
"""

from __future__ import annotations

from src.generators._template_validators import (
    is_iconic_bare_country,
    verify_answer_in_source_fact,
)
from src.generators.template_generator import (
    TEMPLATES,
    _DIFFICULTY_TABLE,
    calibrated_difficulty,
)


# ─── 8a — Deleted templates are gone ─────────────────────────────────────


def _all_template_ids() -> set[str]:
    return {t["id"] for t in TEMPLATES}


def test_deleted_templates_not_present():
    existing = _all_template_ids()
    for deleted in [
        "T-REG-COUNTRY-01",     # WB-REG-0091-L1 class (world-knowledge)
        "T-REG-GRAPE-01",       # replaced by T-REG-AUTH-GRAPE-01
        "T-REG-STYLE-01",       # "primarily known for" superlative
        "T-REG-NEIGHBOR-01",    # "borders / near" — can't verify
        "T-REG-TF-COUNTRY-01",  # WB-REG-0096-L1 class (TF world-knowledge)
        "T-GRP-REGION-01",      # WB-GRP-0095-L3, WB-GRP-0096-L3 class (superlative)
        "T-GRP-ORIGIN-01",      # WB-GRP-0100-L1 class (world-knowledge)
        "T-GRP-COLOR-01",       # world-knowledge
        "T-GRP-TF-COLOR-01",    # world-knowledge
        "T-PRD-GRAPE-01",       # flagship-grape superlative
        "T-PRD-COUNTRY-01",     # WB-PRD-0104-L1 class (world-knowledge)
        "T-BIZ-EXPORT-01",      # largest-export superlative
    ]:
        assert deleted not in existing, f"{deleted} should be deleted by fix #8a"


def test_rewrites_present_and_fact_specific():
    rewrites = ["T-REG-AUTH-GRAPE-01", "T-GRP-AUTH-APPELLATION-01"]
    for tid in rewrites:
        t = next((x for x in TEMPLATES if x["id"] == tid), None)
        assert t is not None, f"{tid} should be present as rewrite"
        assert t["requires_fact_specific"] is True
        assert t["verifiable_from_single_fact"] is True


# ─── 8b — Source-faithfulness gate ───────────────────────────────────────


def test_gold_v2_WB_REG_0091_would_be_rejected_by_8b_if_kept():
    """WB-REG-0091-L1: fact 'Leelanau Peninsula is a wine-producing area
    within the Michigan region of US'. Template asked 'Which country is
    Leelanau Peninsula in?' answer=US. US appears in the fact literally —
    so the source-faithfulness gate ALONE doesn't catch this case.
    Template deletion (8a) is what removes the whole class."""
    assert verify_answer_in_source_fact(
        "US",
        "Leelanau Peninsula is a wine-producing area within the Michigan region of US.",
    ) is True
    # The actual remediation is that T-REG-COUNTRY-01 is deleted.
    assert "T-REG-COUNTRY-01" not in _all_template_ids()


def test_gold_v2_WB_REG_0100_source_faithfulness():
    """WB-REG-0100-L1: fact 'Riesling is grown in the Kamptal region of
    Austria'; template claim 'Kamptal is a wine region in Austria', answer
    'True' (A). The fact DOES contain Austria, so the literal-answer
    check passes; the subtler 'Kamptal IS a wine region' claim isn't
    verified by this gate (Gemini verifier in 8e handles that). Template
    T-REG-TF-COUNTRY-01 has also been deleted in 8a to prevent this
    entire class."""
    assert "T-REG-TF-COUNTRY-01" not in _all_template_ids()


def test_source_faithfulness_alias_match():
    """'United States' and 'US' should match each other via aliases.yaml."""
    fact = "Force Majeure Vineyards is a wine producer located in the United States."
    assert verify_answer_in_source_fact("US", fact) is True
    assert verify_answer_in_source_fact("USA", fact) is True


def test_source_faithfulness_rejects_fabrication():
    """A fact about grapes should not anchor a claim about soils."""
    fact = "Nebbiolo is the authorised grape of Barolo DOCG."
    assert verify_answer_in_source_fact("limestone", fact) is False


# ─── 8c — Distractor pool country sentinel ───────────────────────────────


def test_force_majeure_case_country_sentinel():
    """WB-PRD-0104-L1 distractor-leak: 'Georgian wine', 'Canadian wine',
    'Italian wine' were all banned region-pool entries now."""
    assert is_iconic_bare_country("Georgian wine") is True
    assert is_iconic_bare_country("Canadian wine") is True
    assert is_iconic_bare_country("Italian wine") is True
    assert is_iconic_bare_country("United States") is True
    # A real appellation should NOT match.
    assert is_iconic_bare_country("Margaux-Cantenac") is False
    assert is_iconic_bare_country("Rheingau") is False
    assert is_iconic_bare_country("Saint-Émilion") is False


# ─── 8d — Per-template difficulty table ──────────────────────────────────


def test_difficulty_table_matches_gold_v2_ground_truth():
    """Check that the table overrides for keys corresponding to gold-v2
    actual-difficulty fills."""
    # WB-PRD-0087-L1 (Force Majeure, low mentions, TF-REGION) → actual d=3
    assert _DIFFICULTY_TABLE[("T-PRD-TF-REGION-01", "low")] == "3"
    # WB-PRD-0099-L3 (Château Margaux, high mentions, REGION) → actual d=1
    assert _DIFFICULTY_TABLE[("T-PRD-REGION-01", "high")] == "1"
    # WB-REG-0090-L3 (Castel del Monte, high mentions, SUBREGION) → actual d=2
    assert _DIFFICULTY_TABLE[("T-REG-SUBREGION-01", "high")] == "2"


def test_calibrated_difficulty_falls_back_to_heuristic_when_not_in_table():
    """An unknown template_id should use the γ-3 mention-count fallback."""
    # Non-existent template_id — should fall through to heuristic_difficulty.
    # We monkey-test just by calling; the γ-3 function returns strings "1"-"4".
    # If the entity name is ambiguous, cnt=0 → "4". We accept any valid band.
    out = calibrated_difficulty("T-NOT-A-REAL-TEMPLATE-99", "Xyzzy Unknown Entity")
    assert out in {"1", "2", "3", "4"}
