"""Plan §9 (Team β-3) — extended A1 vague-language regex.

The original ``_VAGUE_PATTERNS`` regex caught marketing/superlative phrasings
("renowned", "iconic", etc.) but missed several phrasings the domain expert
flagged on the gold sheet (``data/reports/gold_sheet_scored.csv`` rows where
``no_vague_language=0``). This module asserts each new pattern matches its
flagged example so the regression doesn't silently regress.

The test does NOT touch the database — it only exercises the compiled regex
against literal example phrases harvested from the gold sheet.
"""

from __future__ import annotations

import pytest

from src.generators._fact_sampler import _VAGUE_PATTERNS


# Each entry: (label, example_phrase). The example is verbatim (or a minimal
# excerpt) from the gold sheet question_text field for a flagged row.
GOLD_SHEET_EXAMPLES = [
    (
        "demonstrative_these_bordeaux_wines",
        "For these Bordeaux wines, what bottle-ageing period is recommended?",
    ),
    (
        "demonstrative_these_wines",
        "Among these wines, which one has the highest tannin?",
    ),
    (
        "demonstrative_this_wine",
        "What grape is used to produce this wine?",
    ),
    (
        # v2.2 fix #4 — "is considered the" was over-firing on factual questions
        # like "considered the origin of X". The regex now requires a vague
        # superlative (best/finest/top/most X) to follow. New positive case:
        "is_considered_the_best",
        "Which producer is considered the best in the region?",
    ),
    (
        "is_considered_to_be",
        "Which appellation is considered to be the most prestigious in Burgundy?",
    ),
    (
        "is_said_to",
        "Which technique is said to enhance the depth of these wines?",
    ),
    (
        "best_matches_this_scenario",
        "Which of the following AVAs best matches this scenario?",
    ),
    (
        "best_matches_the_description",
        "Which producer best matches the description?",
    ),
    (
        "procedures_discussed_in_doc",
        "Following the procedures discussed in DELAYED-DORMANT AND BUDBREAK MONITORING, what should you do next?",
    ),
    (
        "guidelines_discussed_in",
        "Apply the guidelines discussed in CHAPTER 4 to determine the next step.",
    ),
    (
        "as_discussed_in",
        "As discussed in the previous section, which option is correct?",
    ),
    (
        "quoted_other_region",
        "Fruit from producers located in the 'Other' region of Argentina is routed elsewhere.",
    ),
    (
        "quoted_other_appellation",
        "Wines labelled 'Other' appellation may not display a region of origin.",
    ),
]


@pytest.mark.parametrize("label,example", GOLD_SHEET_EXAMPLES, ids=[lab for lab, _ in GOLD_SHEET_EXAMPLES])
def test_new_vague_pattern_matches_flagged_example(label: str, example: str) -> None:
    """Each new vague-pattern regex must match its flagged example phrasing."""
    match = _VAGUE_PATTERNS.search(example)
    assert match is not None, (
        f"Pattern for {label!r} failed to match its flagged example: {example!r}"
    )


# ─── Existing patterns must still match ────────────────────────────────────


PRE_EXISTING_EXAMPLES = [
    "Renowned for its terroir, this region produces wines.",
    "It is known for its quality across many vintages.",
    "Discover the legendary winery on your next visit.",
    "One of the best producers in the area.",
]


@pytest.mark.parametrize("example", PRE_EXISTING_EXAMPLES)
def test_existing_vague_patterns_still_match(example: str) -> None:
    """Confirm refactor of the regex didn't break the original phrasings."""
    assert _VAGUE_PATTERNS.search(example) is not None, (
        f"Pre-existing pattern regressed on: {example!r}"
    )


# ─── Negative controls — clean phrasings must NOT match ────────────────────


CLEAN_PHRASINGS = [
    "Barolo DOCG requires a minimum of 38 months ageing before release.",
    "Riesling is the dominant grape in the Mosel region of Germany.",
    "Champagne uses the méthode traditionnelle for its second fermentation.",
    "Which grape variety is required to produce Brunello di Montalcino?",
    # v2.2 fix #4 — these 5 examples were false positives in gold v1 review.
    # Predecessor sampler-team agent identified them; the regex now skips them.
    "Which country is considered the origin of the Malbec grape?",
    "Which country is considered the origin of Tempranillo?",
]


@pytest.mark.parametrize("example", CLEAN_PHRASINGS)
def test_clean_phrasings_do_not_match(example: str) -> None:
    """Clean, factual stems must not be flagged as vague."""
    assert _VAGUE_PATTERNS.search(example) is None, (
        f"False positive — clean phrasing was flagged: {example!r}"
    )


# ─── v2.2 fix #4 — demonstrative-hit long-stem guard (team_a_static layer) ──


LONG_STEM_WITH_ANTECEDENT = [
    # Long scenario stems where "these wines" / "these producers" / "this wine"
    # have antecedent established earlier in the stem. These must NOT be A1
    # question-level fails even though the raw regex matches.
    (
        "A sommelier is preparing a flight of three Châteaux Margaux vintages: "
        "1990, 1995, and 2000. Among these wines, which one has the highest tannin?"
    ),
    (
        "Three Mendoza producers — Catena, Zuccardi, and Trapiche — each released a 2020 "
        "Malbec. For these producers, which one uses the longest barrel aging?"
    ),
    (
        "A winemaker is monitoring a Barolo vineyard in late September. "
        "The nighttime temperatures have been unusually cool. For this wine, "
        "what harvest decision best balances tannin ripeness and acid retention?"
    ),
]


@pytest.mark.parametrize("qtext", LONG_STEM_WITH_ANTECEDENT)
def test_long_stem_demonstrative_is_not_flagged(qtext: str) -> None:
    """v2.2 fix #4: A1 question-level scan drops demonstrative hits when the
    stem is long enough to carry an antecedent."""
    from src.qa.agents.team_a_static import _filter_demonstrative_fps
    raw_hits = [m.group(0) for m in _VAGUE_PATTERNS.finditer(qtext)]
    filtered = _filter_demonstrative_fps(qtext, raw_hits)
    # Long-stem antecedent path: demonstrative-only hits must be dropped.
    demonstrative_only = all(
        h.lower().startswith(("this wine", "these "))
        for h in raw_hits
    )
    if demonstrative_only:
        assert filtered == [], (
            f"A1 long-stem guard failed — kept demonstrative hits in stem: "
            f"raw={raw_hits!r} filtered={filtered!r} qtext={qtext!r}"
        )
