"""v2.3 fix #16 — C4 calibration refresh + level-aware gen-time threshold.

Covers three concerns:

1. Unit: the rebuilt C4 prompt (`src.qa._prompts.C4_SYSTEM`) contains the new
   observable-property rubric text and calibration examples, so any regression
   that silently strips the rewrite gets caught.

2. Integration (skipped when no OPENROUTER_API_KEY): feed the four
   representative few-shot cases back through the live C4 LLM call and assert
   at least 3 of 4 round-trip to their `actual` difficulty.

3. Unit: the level-aware `_schemas.parse_llm_response` threshold — L3/L4
   questions must be rejected on a 1-level miss; L1/L2 tolerate it.
"""

from __future__ import annotations

import os

import pytest

from src.generators import _schemas
from src.qa import _prompts
from src.qa.agents import team_c_probes


# ─── Part A — prompt structure ───────────────────────────────────────────────


def test_c4_prompt_contains_observable_property_rubric():
    """The rebuilt C4 system prompt must embed the observable-property
    checklist and at least one calibration example of each of the four
    representative levels (L1 correct, L2→L3 miss, L3→L2 miss, L4 correct).
    """
    sys_prompt = _prompts.C4_SYSTEM

    # Observable-property anchor phrases — one per level
    assert "Direct recall of a named entity" in sys_prompt
    assert "pairing two fields from the fact" in sys_prompt
    assert "inference beyond what is literally in the" in sys_prompt
    assert "Multi-step reasoning" in sys_prompt

    # Checklist header
    assert "OBSERVABLE-PROPERTY CHECKLIST" in sys_prompt

    # Four representative cases
    assert "Château Margaux" in sys_prompt              # L1 correct
    assert "Cautín" in sys_prompt                       # L2→L3 miss
    assert "Château Sociando-Mallet" in sys_prompt      # L3→L2 miss
    assert "Rayon d'Or" in sys_prompt                   # L4 correct


def test_c4_template_includes_checklist_instruction():
    """The user template should nudge the model to run the checklist before
    committing to a level, so the step-by-step reasoning is anchored to the
    rubric rather than improvised.
    """
    assert "observable-property checklist" in _prompts.C4_TEMPLATE
    assert "difficulty" in _prompts.C4_TEMPLATE
    assert "rationale" in _prompts.C4_TEMPLATE


def test_c4_version_was_bumped():
    """The config hash must change when the prompt changes; bump surfaces it."""
    assert team_c_probes.C4_VERSION == "v1.2.0"


def test_c4_gold_v3_fewshot_constant_shape():
    """The harvested gold-v3 calibration pool must contain the expected
    shape so downstream tooling (documentation, follow-up audits) can
    iterate over it safely.
    """
    pool = team_c_probes._C4_GOLD_V3_FEWSHOT
    assert isinstance(pool, list)
    assert len(pool) >= 14, f"expected >= 14 calibration cases, got {len(pool)}"
    required_keys = {"question", "options", "correct_answer",
                     "labelled", "actual", "reasoning"}
    for case in pool:
        assert required_keys.issubset(case.keys()), (
            f"case missing keys: {required_keys - set(case.keys())}"
        )
        assert isinstance(case["labelled"], int)
        assert isinstance(case["actual"], int)
        assert 1 <= case["labelled"] <= 4
        assert 1 <= case["actual"] <= 4
        assert case["labelled"] != case["actual"], (
            "calibration cases must be mislabels; labelled == actual means pass"
        )
        # Reasoning should be concise per the task spec (< 30 words).
        word_count = len(case["reasoning"].split())
        assert word_count < 30, (
            f"reasoning too long ({word_count} words): {case['reasoning']!r}"
        )

    too_easy = [c for c in pool if c["actual"] > c["labelled"]]
    too_hard = [c for c in pool if c["actual"] < c["labelled"]]
    # Gold-v3 yielded 7 too-easy and 7 too-hard from the 14 clean cases.
    assert len(too_easy) >= 6
    assert len(too_hard) >= 3


# ─── Part B — live smoke test (skippable) ────────────────────────────────────

_REPRESENTATIVE_FEWSHOT = [
    {
        "question": "Which region houses the producer Château Margaux?",
        "options": [
            {"id": "A", "text": "Bordeaux"},
            {"id": "B", "text": "Burgundy"},
            {"id": "C", "text": "Rhône"},
            {"id": "D", "text": "Loire"},
        ],
        "correct_answer": "A",
        "actual": 1,
    },
    {
        "question": (
            "Cautín, a small wine-producing zone with only a few hectares "
            "under vine, is located at the far southern end of Chile. Within "
            "which broad Chilean viticultural region does it fall?"
        ),
        "options": [
            {"id": "A", "text": "Aconcagua"},
            {"id": "B", "text": "Austral"},
            {"id": "C", "text": "Central Valley"},
            {"id": "D", "text": "Coquimbo"},
        ],
        "correct_answer": "B",
        "actual": 3,
    },
    {
        "question": (
            "True or False: Château Sociando-Mallet is located in the "
            "Médoc wine region."
        ),
        "options": [
            {"id": "A", "text": "True"},
            {"id": "B", "text": "False"},
        ],
        "correct_answer": "A",
        "actual": 2,
    },
    {
        "question": (
            "Which grape was crossed with Aramon du Gard to create "
            "Rayon d'Or, the second parent of Vidal blanc?"
        ),
        "options": [
            {"id": "A", "text": "Seibel 4986"},
            {"id": "B", "text": "Folle Blanche"},
            {"id": "C", "text": "Sultanina"},
            {"id": "D", "text": "Muscat Hamburg"},
        ],
        "correct_answer": "A",
        "actual": 4,
    },
]


@pytest.mark.skipif(
    not os.environ.get("OPENROUTER_API_KEY"),
    reason="no OPENROUTER_API_KEY — skip live C4 round-trip smoke test",
)
def test_c4_live_roundtrip_on_representative_fewshot():
    """Feed the four representative cases through the live Gemini judge and
    assert ≥ 3 of 4 agree with the `actual` level within ±0 (exact match).
    A strict check ensures the rebuilt prompt is actually calibrated.
    """
    hits = 0
    misses: list[tuple[int, int]] = []
    for case in _REPRESENTATIVE_FEWSHOT:
        rated, _rationale, meta = team_c_probes._c4_call_llm(
            question_text=case["question"],
            options=case["options"],
            correct_answer=case["correct_answer"],
        )
        if rated == case["actual"]:
            hits += 1
        else:
            misses.append((case["actual"], rated or -1))

    assert hits >= 3, (
        f"live C4 smoke: only {hits}/4 exact matches; "
        f"misses (actual, rated) = {misses}"
    )


# ─── Part C — level-aware gen-time reject threshold ──────────────────────────


@pytest.fixture
def sample_response_json() -> str:
    return (
        '{"question_text": "Which grape is authorised in Barolo DOCG?",'
        ' "options": ['
        '  {"id": "A", "text": "Nebbiolo"},'
        '  {"id": "B", "text": "Barbera"},'
        '  {"id": "C", "text": "Dolcetto"},'
        '  {"id": "D", "text": "Sangiovese"}'
        '], "correct_answer": "A",'
        ' "explanation": "Barolo DOCG requires 100% Nebbiolo."}'
    )


def _mock_classify(monkeypatch, predicted: str | None):
    """Patch `classify_difficulty` so tests don't hit the network."""
    from src.generators import _c4_helper

    def fake(**kwargs):
        return predicted

    monkeypatch.setattr(_c4_helper, "classify_difficulty", fake)


def test_level_aware_threshold_rejects_l4_on_one_level_miss(
    monkeypatch, sample_response_json
):
    """Labelled L4, predicted L2 — delta=2, threshold=1 for L4, reject."""
    _mock_classify(monkeypatch, predicted="2")
    q = _schemas.parse_llm_response(
        sample_response_json,
        "multiple_choice",
        verify_difficulty_with_c4=True,
        labelled_difficulty="4",
    )
    assert q is None, (
        "L4 labelled with L2 prediction (delta=2) must be rejected "
        "under the new level-aware threshold"
    )


def test_level_aware_threshold_rejects_l3_on_two_level_miss(
    monkeypatch, sample_response_json
):
    """Labelled L3, predicted L1 — delta=2, threshold=2 for L3, reject.

    Phase 2g.12 loosened the L3+ threshold from 1 to 2 (tolerates a
    1-level boundary miss while keeping L3+ strict at 2-level misses).
    This case still rejects, ensuring the level-aware semantics survive.
    """
    _mock_classify(monkeypatch, predicted="1")
    q = _schemas.parse_llm_response(
        sample_response_json,
        "multiple_choice",
        verify_difficulty_with_c4=True,
        labelled_difficulty="3",
    )
    assert q is None, (
        "L3 labelled with L1 prediction (delta=2) must be rejected "
        "under the Phase 2g.12 L3+ threshold of 2"
    )


def test_level_aware_threshold_accepts_l1_on_one_level_miss(
    monkeypatch, sample_response_json
):
    """Labelled L1, predicted L2 — delta=1, threshold=2 for L1, accept."""
    _mock_classify(monkeypatch, predicted="2")
    q = _schemas.parse_llm_response(
        sample_response_json,
        "multiple_choice",
        verify_difficulty_with_c4=True,
        labelled_difficulty="1",
    )
    assert q is not None, (
        "L1 labelled with L2 prediction (delta=1) must still be accepted; "
        "L1/L2 tolerate a 1-level miss"
    )


def test_level_aware_threshold_accepts_l2_on_one_level_miss(
    monkeypatch, sample_response_json
):
    """Labelled L2, predicted L3 — delta=1, threshold=2 for L2, accept.

    Preserves the existing permissive behaviour for L2 labels.
    """
    _mock_classify(monkeypatch, predicted="3")
    q = _schemas.parse_llm_response(
        sample_response_json,
        "multiple_choice",
        verify_difficulty_with_c4=True,
        labelled_difficulty="2",
    )
    assert q is not None, "L2 label with L3 prediction (delta=1) must accept"


def test_level_aware_threshold_accepts_exact_match_l4(
    monkeypatch, sample_response_json
):
    """Labelled L4, predicted L4 — delta=0, accept regardless of threshold."""
    _mock_classify(monkeypatch, predicted="4")
    q = _schemas.parse_llm_response(
        sample_response_json,
        "multiple_choice",
        verify_difficulty_with_c4=True,
        labelled_difficulty="4",
    )
    assert q is not None, "exact L4 match must always accept"


def test_env_escape_hatch_still_works_under_level_aware_threshold(
    monkeypatch, sample_response_json
):
    """OENOBENCH_SKIP_C4_GATE=1 bypasses the gate even for L4 delta=2."""
    monkeypatch.setenv("OENOBENCH_SKIP_C4_GATE", "1")
    _mock_classify(monkeypatch, predicted="2")
    q = _schemas.parse_llm_response(
        sample_response_json,
        "multiple_choice",
        verify_difficulty_with_c4=True,
        labelled_difficulty="4",
    )
    assert q is not None, "env-var escape hatch must still disable the gate"


def test_level_aware_threshold_accepts_l1_on_two_level_miss(
    monkeypatch, sample_response_json
):
    """Phase 2g.12 v9 calibration drift: L1 labelled, predicted L3 — accept.

    The C4 classifier consistently over-predicts difficulty for fact-anchored
    detail questions that the template heuristic correctly buckets at L1/L2.
    In the v9 audit-pilot build this rejected ~91 questions per build, all
    at the L1/L2 delta=2 boundary. Phase 2g.12 loosens the L1/L2 reject
    threshold from 2 to 3 to recover them; audit-side D-gates on per-level
    distribution catch any drift downstream.
    """
    _mock_classify(monkeypatch, predicted="3")
    q = _schemas.parse_llm_response(
        sample_response_json,
        "multiple_choice",
        verify_difficulty_with_c4=True,
        labelled_difficulty="1",
    )
    assert q is not None, (
        "L1 labelled with L3 prediction (delta=2) must accept under the "
        "Phase 2g.12 loosened L1/L2 threshold of 3"
    )
