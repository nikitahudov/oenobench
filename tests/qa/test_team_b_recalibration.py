"""B2 ClosedBookSolvability recalibration — v3.1.0 (unanimous + high-confidence FAIL).

Gold-v3 calibration (n=119) showed B2 v3.0.0 had κ = -0.099 against human
reviewers on the `needs_source` rubric (humans flagged ~7% of questions as
world-knowledge solvable; B2 flagged ~81%). The root cause was that the
wider 5-judge panel (Claude/GPT/Gemini/Llama/Qwen) with a ≥4/5 FAIL threshold
let the three expert LLMs out-vote the two proxy judges on textbook trivia.

The v3.1.0 gate is:
  difficulty ≤ 2 (L1/L2):
    - FAIL iff ALL 5 judges keyed AND mean-confidence ≥ 0.80 among keyed judges
    - WARN when ≥4/5 keyed (formerly FAIL under v3.0.0)
    - PASS otherwise
  difficulty ≥ 3 (L3/L4):
    - WARN when ALL 5 judges keyed (formerly FAIL under v3.0.0)
    - PASS otherwise (closed-book signal is informational only at hard difficulty)

The file name (`test_team_b_recalibration.py`) reflects that this exercises
Team B's B2 agent; the original δ-2 filename (`test_team_d_recalibration.py`)
was an artefact of the v2.2 fix-#2 rollout in which D-team drove the recal.
See docs/GENERATION_IMPROVEMENT_PLAN.md §5b and
docs/GOLD_CALIBRATION_ANALYSIS.md §4.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.qa import _judges
from src.qa.agents import team_b_validity


@dataclass
class _StubVerdict:
    judge: str
    chosen: str | None
    confidence: float = 0.7
    fact_supports_choice: bool | None = None
    rationale: str = ""
    raw: str = ""
    cost_usd: float = 0.0
    error: str | None = None
    prompt_hash: str = ""


@dataclass
class _StubBatch:
    open_book: list
    closed_book: list

    def total_cost(self):
        return 0.0

    def total_calls(self):
        return len(self.open_book) + len(self.closed_book)


def _question(difficulty: str = "2", correct: str = "A") -> dict:
    return {
        "uuid": "00000000-0000-0000-0000-0000000000b2",
        "question_text": "Which grape is required for Barolo DOCG?",
        "options": [
            {"id": "A", "text": "Nebbiolo"},
            {"id": "B", "text": "Sangiovese"},
            {"id": "C", "text": "Barbera"},
            {"id": "D", "text": "Dolcetto"},
        ],
        "correct_answer": correct,
        "difficulty": difficulty,
        "facts": [],
    }


def _run_with_panel(
    monkeypatch,
    *,
    closed_book_choices: list[str],
    difficulty="2",
    confidences: list[float] | None = None,
):
    """Drive one B2 row by stubbing judge_open_and_closed.

    `confidences` is an optional per-judge confidence list (same length as
    `closed_book_choices`). Defaults to 0.7 for each judge — safely below
    the v3.1.0 high-confidence threshold (0.80). Pass explicit values when
    a test needs to exercise the confidence gate.
    """
    open_book = [
        _StubVerdict(judge=j, chosen="A", fact_supports_choice=True)
        for j in ("claude", "chatgpt", "gemini")
    ]
    if confidences is None:
        confidences = [0.7] * len(closed_book_choices)
    assert len(confidences) == len(closed_book_choices), (
        "confidences must be same length as closed_book_choices"
    )
    closed_book = [
        _StubVerdict(judge=name, chosen=ch, confidence=conf)
        for name, ch, conf in zip(
            ("claude", "chatgpt", "gemini", "llama", "qwen"),
            closed_book_choices,
            confidences,
        )
    ]

    def _fake_judge(**kwargs):
        # Sanity: caller must rely on B2's wider panel
        cb_judges = kwargs.get("closed_book_judges")
        # Default panel resolution happens inside the function; either explicit
        # JUDGE_PANEL_B2 OR None (which triggers the same default) is acceptable.
        assert cb_judges is None or tuple(cb_judges) == _judges.JUDGE_PANEL_B2
        return _StubBatch(open_book=open_book, closed_book=closed_book)

    monkeypatch.setattr(team_b_validity, "judge_open_and_closed", _fake_judge)

    findings: list[dict] = []
    team_b_validity.run_team_b(
        run_id="00000000-0000-0000-0000-0000000000aa",
        questions=[_question(difficulty=difficulty)],
        write_finding_fn=findings.append,
    )
    b2 = next(f for f in findings if f["agent_id"] == "B2_ClosedBookSolvability")
    return b2


def test_b2_warns_when_4_of_5_judges_solve_easy_question(monkeypatch):
    # v3.1.0: at difficulty ≤ 2, 4/5 closed-book solves is WARN (not FAIL —
    # the FAIL condition now requires unanimous 5/5 AND mean-conf ≥ 0.80).
    b2 = _run_with_panel(
        monkeypatch,
        closed_book_choices=["A", "A", "A", "A", "B"],
        difficulty="2",
    )
    assert b2["severity"] == "warn", (
        f"v3.1.0: 4/5 keyed at diff=2 must WARN; got {b2['severity']}"
    )
    payload = b2["payload"]
    assert payload["judges_keyed"] == 4
    assert payload["judges_total"] == 5
    assert payload["closed_book_correct"] is True
    assert payload["leakage_ratio"] == round(4 / 5, 3)


def test_b2_passes_when_3_of_5_judges_solve_easy_question(monkeypatch):
    # v3.1.0: 3/5 at diff ≤ 2 is PASS (the v3.0.0 WARN band for 3/5 was
    # removed; WARN now requires ≥4/5).
    b2 = _run_with_panel(
        monkeypatch,
        closed_book_choices=["A", "A", "A", "B", "C"],
        difficulty="2",
    )
    assert b2["severity"] == "pass", (
        f"v3.1.0: 3/5 keyed at diff=2 must PASS; got {b2['severity']}"
    )


def test_b2_fails_when_all_5_judges_solve_easy_with_high_confidence(monkeypatch):
    # v3.1.0: 5/5 keyed + mean-conf ≥ 0.80 at diff ≤ 2 must FAIL. We pass
    # explicit confidences=[0.9]×5 because the default (0.7) is below the
    # high-confidence gate.
    b2 = _run_with_panel(
        monkeypatch,
        closed_book_choices=["A", "A", "A", "A", "A"],
        difficulty="1",
        confidences=[0.9, 0.9, 0.9, 0.9, 0.9],
    )
    assert b2["severity"] == "fail", (
        f"All judges solving an easy question with high conf must FAIL; "
        f"got {b2['severity']}"
    )
    payload = b2["payload"]
    assert payload["judges_keyed"] == 5
    assert payload["judges_total"] == 5
    assert payload["cb_confidence_mean"] == 0.9


def test_b2_passes_when_only_3_of_5_judges_solve_hard(monkeypatch):
    # v3.1.0: at difficulty ≥ 3 the closed-book signal is WARN-max; 3/5 is PASS.
    b2 = _run_with_panel(
        monkeypatch,
        closed_book_choices=["A", "A", "A", "B", "C"],
        difficulty="3",
    )
    assert b2["severity"] == "pass", (
        f"v3.1.0: 3/5 at diff=3 is below WARN gate; got {b2['severity']}"
    )


def test_b2_passes_when_4_of_5_judges_solve_hard_question(monkeypatch):
    # v3.1.0: at difficulty ≥ 3, only 5/5 triggers WARN; 4/5 is PASS
    # (v3.0.0 gave WARN at 4/5 and FAIL at 5/5 — both are relaxed).
    b2 = _run_with_panel(
        monkeypatch,
        closed_book_choices=["A", "A", "A", "A", "B"],
        difficulty="4",
    )
    assert b2["severity"] == "pass", (
        f"v3.1.0: 4/5 keyed at diff=4 must PASS; got {b2['severity']}"
    )


def test_b2_warns_when_5_of_5_judges_solve_hard_question(monkeypatch):
    # v3.1.0: at difficulty ≥ 3 a unanimous closed-book solve is WARN,
    # not FAIL (demoted because expert-LLM priors dominate on hard recall).
    b2 = _run_with_panel(
        monkeypatch,
        closed_book_choices=["A", "A", "A", "A", "A"],
        difficulty="3",
    )
    assert b2["severity"] == "warn", (
        f"v3.1.0: 5/5 at diff=3 must WARN (not FAIL); got {b2['severity']}"
    )


def test_judges_module_exposes_b2_panel():
    # The new constant exists and includes the test-taker-strength judges.
    assert _judges.JUDGE_PANEL_B2 == ("claude", "chatgpt", "gemini", "llama", "qwen")


# ─── v3.1.0 recalibration — new coverage ─────────────────────────────────────


def test_b2_l1_unanimous_high_confidence_fails(monkeypatch):
    """5/5 solve + mean-conf 0.9 at diff=1 → FAIL (exact spec case)."""
    b2 = _run_with_panel(
        monkeypatch,
        closed_book_choices=["A", "A", "A", "A", "A"],
        difficulty="1",
        confidences=[0.9, 0.9, 0.9, 0.9, 0.9],
    )
    assert b2["severity"] == "fail", (
        f"v3.1.0: 5/5 + mean-conf 0.9 at diff=1 must FAIL; got {b2['severity']}"
    )
    payload = b2["payload"]
    assert payload["judges_keyed"] == 5
    assert payload["judges_total"] == 5
    assert payload["cb_confidence_mean"] == 0.9
    assert payload["closed_book_correct"] is True


def test_b2_l1_unanimous_low_confidence_warns(monkeypatch):
    """5/5 solve + mean-conf 0.5 at diff=1 → WARN (was FAIL under v3.0.0).

    The v3.1.0 FAIL gate adds a mean-confidence ≥ 0.80 requirement; judges
    agreeing while uncertain demotes to WARN.
    """
    b2 = _run_with_panel(
        monkeypatch,
        closed_book_choices=["A", "A", "A", "A", "A"],
        difficulty="1",
        confidences=[0.5, 0.5, 0.5, 0.5, 0.5],
    )
    assert b2["severity"] == "warn", (
        f"v3.1.0: 5/5 + mean-conf 0.5 at diff=1 must WARN (not FAIL); "
        f"got {b2['severity']}"
    )
    payload = b2["payload"]
    assert payload["cb_confidence_mean"] == 0.5
    assert payload["judges_keyed"] == 5


def test_b2_l3_unanimous_warns_not_fails(monkeypatch):
    """5/5 solve at diff=3 → WARN (was FAIL under v3.0.0).

    At L≥3 the closed-book signal is demoted to informational-only: even
    unanimous high-confidence consensus is WARN, not FAIL, because the
    expert-LLM panel's priors dominate on hard recall questions.
    """
    b2 = _run_with_panel(
        monkeypatch,
        closed_book_choices=["A", "A", "A", "A", "A"],
        difficulty="3",
        confidences=[0.9, 0.9, 0.9, 0.9, 0.9],
    )
    assert b2["severity"] == "warn", (
        f"v3.1.0: 5/5 at diff=3 must WARN (not FAIL); got {b2['severity']}"
    )
    payload = b2["payload"]
    assert payload["judges_keyed"] == 5
    assert payload["cb_confidence_mean"] == 0.9


# ─── v3.1.0 guardrails ───────────────────────────────────────────────────────


def test_b2_version_is_v3_1_0():
    """Version bump guard — catches accidental revert to v3.0.0."""
    assert team_b_validity.B2_VERSION == "v3.1.0", (
        f"expected B2_VERSION=v3.1.0; got {team_b_validity.B2_VERSION}"
    )


def test_b2_l2_four_of_five_warns_under_v31(monkeypatch):
    """4/5 at diff=2 with high confidence on keyed judges → WARN, not FAIL.

    Guards the `cb_keyed_count == n_closed` FAIL predicate (unanimous only).
    """
    b2 = _run_with_panel(
        monkeypatch,
        closed_book_choices=["A", "A", "A", "A", "B"],
        difficulty="2",
        confidences=[0.9, 0.9, 0.9, 0.9, 0.5],
    )
    assert b2["severity"] == "warn", (
        f"v3.1.0: 4/5 at diff=2 must WARN (even with high conf); "
        f"got {b2['severity']}"
    )
    payload = b2["payload"]
    assert payload["judges_keyed"] == 4
    # Mean-conf computed only over keyed judges → (0.9*4)/4 = 0.9
    assert payload["cb_confidence_mean"] == 0.9
