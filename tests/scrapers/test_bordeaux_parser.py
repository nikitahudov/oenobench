"""Regression tests for v2.3 fix #14c — Bordeaux Saint-Émilion table parser.

Audit gold-v3 traced 3 human-flagged "completely incorrect" template questions
back to the Saint-Émilion classified-growths Wikipedia page being mis-parsed.
Two failure modes were observed in the production facts table:

 1. **Off-by-one (43 facts).** The Saint-Émilion article lays out the
    classified estates in a table with 2–3 château cells per row (all at the
    same classification level). The prior parser assumed the legacy
    ``name | commune`` two-column layout, so it produced rows like
    "Château Pavie is a classified Bordeaux estate in Château Figeac".

 2. **Markup leakage (9 facts).** Cells with wikitext attribute syntax
    (``colspan="2" align="center" | 178 g/L``) leaked raw HTML/table markup
    into the "region" slot of facts, producing strings such as
    "… in align=\"center\" | lightly coloured red".

These tests pin down the fix in ``src/scrapers/bordeaux.py``:

 * ``_facts_from_classification_table`` must emit *one fact per cell* with the
   correct commune ("Saint-Émilion") when the article title is in
   ``_MULTICOL_ESTATE_TABLE_REGIONS``.
 * The defensive gate ``_region_is_valid`` must reject any candidate commune
   that starts with "Château " or contains ``align=``, ``colspan=``, ``&nbsp;``
   or ``|``.
"""

from __future__ import annotations

import pytest

from src.scrapers import bordeaux


# ─── Fixture rows (verbatim from Wikipedia wikitext, April 2026) ──────────


# Matches the output of parse_wikitext_tables() on the "Classification of
# Saint-Émilion wine" article. Each non-header row contains 2–3 château
# cells. The first, third and seventh rows are section headers.
SAINT_EMILION_ROWS: list[list[str]] = [
    ["Premier Grand Cru Classé 'A' &nbsp;"],
    ["Château Pavie", "Château Figeac"],
    ["Premier Grand Cru Classé 'B"],
    ["Château Beauséjour (Duffau-Lagarrosse)", "Château Beau-Séjour Bécot", "Château Bélair-Monange"],
    ["Château Canon", "Château Canon-la-Gaffelière", "Château Larcis Ducasse"],
    ["Château Pavie-Macquin", "Château Troplong Mondot", "Château Trotte Vieille"],
    ["Château Valandraud", "Clos Fourtet", "La Mondotte"],
    ["Grand Cru Classé"],
    ["Château Balestard la Tonnelle", "Château Barde-Haut", "Château Bellefont-Belcier"],
    ["Château Bellevue", "Château Berliquet", "Château Cadet Bon"],
    ["Château Cap de Mourlin", "Château Chauvin", "Château Clos de Sarpe"],
    ["Château Corbin", "Château Corbin Michotte", "Château Côte de Baleau"],
]


# Rows mimicking the "Bordeaux AOC" article — wikitext cell attributes make
# it to the row output because clean_wiki_value only strips links/refs/tags,
# not attribute syntax. The (now-removed) legacy layout treated these as
# estate→commune pairs and happily emitted markup into the region slot.
BORDEAUX_AOC_ROWS: list[list[str]] = [
    ['Specific colour requirement (if applicable)', 'align="center" | lightly coloured red'],
    ['Grape ripeness (in terms of minimum sugar content)', 'colspan="2" align="center" | 178 g/L'],
    ['Alcohol content after fermentation', 'colspan="2" align="center" | min 10%'],
    ['Vineyard surface', 'align="center" | 44,000 ha'],
    ['Average annual production', 'align="center" | 2,500,000 hl'],
]


# Legacy two-column wikitext layout that should still work after the fix —
# e.g. a hypothetical article where the right column is a real commune.
LEGACY_PAIR_ROWS: list[list[str]] = [
    ["Château Lafite Rothschild", "Pauillac"],
    ["Château Latour", "Pauillac"],
    ["Château Haut-Brion", "Pessac"],
]


# ─── Tests ────────────────────────────────────────────────────────────────


def test_saint_emilion_no_chateau_as_region():
    """Every Saint-Émilion fact must have commune="Saint-Émilion", never a château."""
    facts = bordeaux._facts_from_classification_table(
        SAINT_EMILION_ROWS,
        "Classification of Saint-Émilion wine",
        "src-id",
        seen=set(),
    )
    assert facts, "Parser produced zero facts for Saint-Émilion — check fixture"

    for fact in facts:
        # The entity typed "region" is the commune slot in fact_text.
        regions = [e for e in fact["entities"] if e.get("type") == "region"]
        assert regions, f"Fact missing region entity: {fact['fact_text']}"
        for r in regions:
            name = r["name"]
            assert not name.lower().startswith("château"), (
                f"Region entity wrongly contains a château name: "
                f"{fact['fact_text']!r} -> region={name!r}"
            )
            # All Saint-Émilion facts must name the correct commune.
            assert name == "Saint-Émilion", (
                f"Expected commune='Saint-Émilion', got {name!r} in "
                f"{fact['fact_text']!r}"
            )


def test_saint_emilion_no_html_markup_in_region():
    """Commune slot must not contain HTML / table-attribute markup."""
    facts = bordeaux._facts_from_classification_table(
        SAINT_EMILION_ROWS,
        "Classification of Saint-Émilion wine",
        "src-id",
        seen=set(),
    )
    for fact in facts:
        text = fact["fact_text"]
        assert "align=" not in text, text
        assert "colspan=" not in text, text
        assert "&nbsp;" not in text, text
        # Bar "|" should never appear in a natural-language fact.
        assert "|" not in text, text


def test_saint_emilion_emits_one_fact_per_chateau_cell():
    """Data rows have 2-3 cells; each should produce its own fact."""
    facts = bordeaux._facts_from_classification_table(
        SAINT_EMILION_ROWS,
        "Classification of Saint-Émilion wine",
        "src-id",
        seen=set(),
    )
    names = {e["name"] for f in facts for e in f["entities"] if e.get("type") == "producer"}
    # A selection of names that must all appear.
    expected = {
        "Château Pavie", "Château Figeac",
        "Château Beauséjour (Duffau-Lagarrosse)",
        "Château Beau-Séjour Bécot", "Château Bélair-Monange",
        "Château Canon", "Château Canon-la-Gaffelière",
        "Château Larcis Ducasse",
        "Château Trotte Vieille",
        "Château Valandraud", "Clos Fourtet", "La Mondotte",
        "Château Balestard la Tonnelle", "Château Côte de Baleau",
    }
    missing = expected - names
    assert not missing, f"Saint-Émilion fixture dropped expected châteaux: {missing}"


def test_saint_emilion_skips_header_rows():
    """Section-header rows ('Grand Cru Classé' etc.) must not become facts."""
    facts = bordeaux._facts_from_classification_table(
        SAINT_EMILION_ROWS,
        "Classification of Saint-Émilion wine",
        "src-id",
        seen=set(),
    )
    producers = {e["name"] for f in facts for e in f["entities"] if e.get("type") == "producer"}
    banned = {
        "Premier Grand Cru Classé 'A' &nbsp;",
        "Premier Grand Cru Classé 'B",
        "Grand Cru Classé",
    }
    overlap = producers & banned
    assert not overlap, f"Header rows leaked into facts: {overlap}"


def test_bordeaux_aoc_markup_rows_are_rejected():
    """Rows with align=/colspan=/&nbsp; in the second cell must be dropped."""
    facts = bordeaux._facts_from_classification_table(
        BORDEAUX_AOC_ROWS,
        "Bordeaux AOC",  # NOT in _MULTICOL_ESTATE_TABLE_REGIONS — legacy path
        "src-id",
        seen=set(),
    )
    # None of these rows name a château, so the legacy path's region gate
    # should refuse all of them outright.
    assert not facts, (
        f"Markup-carrying rows should produce zero facts; got {len(facts)}:\n"
        + "\n".join(f" - {f['fact_text']}" for f in facts)
    )


def test_legacy_two_column_layout_still_works():
    """Non-multicol articles with genuine (name, commune) rows still emit facts."""
    facts = bordeaux._facts_from_classification_table(
        LEGACY_PAIR_ROWS,
        "Classification of Bordeaux wine",
        "src-id",
        seen=set(),
    )
    names = {e["name"] for f in facts for e in f["entities"] if e.get("type") == "producer"}
    assert {"Château Lafite Rothschild", "Château Latour", "Château Haut-Brion"} <= names

    communes = {e["name"] for f in facts for e in f["entities"] if e.get("type") == "region"}
    assert {"Pauillac", "Pessac"} <= communes
    # Sanity: the commune is never a château even though the estate is.
    for fact in facts:
        for e in fact["entities"]:
            if e.get("type") == "region":
                assert not e["name"].lower().startswith("château"), fact["fact_text"]


def test_region_is_valid_gate():
    """_region_is_valid must reject château names and all known markup leaks."""
    assert bordeaux._region_is_valid("Pauillac")
    assert bordeaux._region_is_valid("Saint-Émilion")
    # Off-by-one bug (château-as-region)
    assert not bordeaux._region_is_valid("Château Figeac")
    assert not bordeaux._region_is_valid("chateau margaux")
    # Markup leakage
    assert not bordeaux._region_is_valid('align="center" | lightly coloured red')
    assert not bordeaux._region_is_valid('colspan="2" align="center" | 178 g/L')
    assert not bordeaux._region_is_valid("Saint-Émilion&nbsp;")
    assert not bordeaux._region_is_valid("Pauillac |")
    # Trivial rejects
    assert not bordeaux._region_is_valid("")
    assert not bordeaux._region_is_valid("   ")


def test_is_chateau_cell():
    """Helper must correctly classify sibling château cells."""
    assert bordeaux._is_chateau_cell("Château Pavie")
    assert bordeaux._is_chateau_cell("château lafite")
    assert bordeaux._is_chateau_cell("Chateau Latour")  # no diacritic
    assert not bordeaux._is_chateau_cell("Pauillac")
    assert not bordeaux._is_chateau_cell("Clos Fourtet")


@pytest.mark.parametrize("row", [
    ["Château Pavie", "Château Figeac"],
    ["Château Laroze", "Château la Clotte", "Château la Commanderie"],
    ["Château les Grandes Murailles", "Château l'Arrosée"],
])
def test_no_chateau_named_as_region_on_any_real_row(row):
    """Parametrized: no matter the row, a Saint-Émilion call never emits
    a fact whose region starts with 'Château '."""
    facts = bordeaux._facts_from_classification_table(
        [row],
        "Classification of Saint-Émilion wine",
        "src-id",
        seen=set(),
    )
    for fact in facts:
        for e in fact["entities"]:
            if e.get("type") == "region":
                assert not e["name"].lower().startswith("château"), (
                    f"Bug recurrence: {fact['fact_text']!r}"
                )
