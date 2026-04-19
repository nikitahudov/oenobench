"""δ-2: Team B B2 ClosedBookSolvability recalibration with the wider judge panel.

The new gate is:
  - FAIL when ALL 5 judges (claude/chatgpt/gemini/llama/qwen) solved an easy
    (difficulty ≤ 2) question without the source.
  - WARN when ≥ 4 of 5 judges solved it.
  - PASS otherwise.

Under the OLD gate a closed-book ratio of 0.85 (4/5 judges, equivalent to 4/5 = 0.8)
on a difficulty-2 question would have been FAIL (cb_ratio >= 0.8 AND diff <= 2).
Under the NEW gate it must be WARN (only 4 of 5 keyed; not all 5).
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


def _run_with_panel(monkeypatch, *, closed_book_choices: list[str], difficulty="2"):
    """Drive one B2 row by stubbing judge_open_and_closed."""
    open_book = [
        _StubVerdict(judge=j, chosen="A", fact_supports_choice=True)
        for j in ("claude", "chatgpt", "gemini")
    ]
    closed_book = [
        _StubVerdict(judge=name, chosen=ch)
        for name, ch in zip(("claude", "chatgpt", "gemini", "llama", "qwen"), closed_book_choices)
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
    # 4 of 5 judges keyed A (the correct answer); 1 chose B.
    # Under OLD thresholds (cb_ratio>=0.8, diff<=2) this was FAIL.
    # Under NEW thresholds (need ALL 5 keyed for FAIL) this is WARN.
    b2 = _run_with_panel(
        monkeypatch,
        closed_book_choices=["A", "A", "A", "A", "B"],
        difficulty="2",
    )
    assert b2["severity"] == "warn", (
        f"Expected WARN under recalibrated 5-judge panel; got {b2['severity']}"
    )
    payload = b2["payload"]
    assert payload["judges_keyed"] == 4
    assert payload["judges_total"] == 5
    assert payload["closed_book_correct"] is True
    assert payload["leakage_ratio"] == round(4 / 5, 3)


def test_b2_fails_when_all_5_judges_solve_easy_question(monkeypatch):
    b2 = _run_with_panel(
        monkeypatch,
        closed_book_choices=["A", "A", "A", "A", "A"],
        difficulty="1",
    )
    assert b2["severity"] == "fail", (
        f"All judges solving an easy question must FAIL; got {b2['severity']}"
    )
    payload = b2["payload"]
    assert payload["judges_keyed"] == 5
    assert payload["judges_total"] == 5


def test_b2_passes_when_only_3_of_5_judges_solve(monkeypatch):
    b2 = _run_with_panel(
        monkeypatch,
        closed_book_choices=["A", "A", "A", "B", "C"],
        difficulty="3",
    )
    assert b2["severity"] == "pass", (
        f"3 of 5 judges (60%) is below the WARN gate; got {b2['severity']}"
    )


def test_b2_warns_when_4_of_5_judges_solve_hard_question(monkeypatch):
    # Even on hard questions, ≥4-of-5 is enough to WARN (no FAIL since diff>2).
    b2 = _run_with_panel(
        monkeypatch,
        closed_book_choices=["A", "A", "A", "A", "B"],
        difficulty="4",
    )
    assert b2["severity"] == "warn", (
        f"Hard question with 4/5 leakage should WARN; got {b2['severity']}"
    )


def test_judges_module_exposes_b2_panel():
    # The new constant exists and includes the test-taker-strength judges.
    assert _judges.JUDGE_PANEL_B2 == ("claude", "chatgpt", "gemini", "llama", "qwen")
