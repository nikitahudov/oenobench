"""δ-2 + v2.2 fix #2: B2 ClosedBookSolvability difficulty-aware gating (v3.0.0).

The v3.0.0 gate (v2.2 fix #2) is:
  difficulty ≤ 2 (L1/L2):
    - FAIL when ≥4 of 5 judges keyed correctly  (gold-v2 showed L2 FTQs
      with 4/5 closed-book solves were genuinely world-knowledge-leaky)
    - WARN when 3 of 5 keyed
    - PASS otherwise
  difficulty ≥ 3 (L3/L4):
    - FAIL when ALL 5 judges keyed
    - WARN when ≥4 of 5 keyed
    - PASS otherwise

This replaces v2.0.0 where even "4/5 keyed at diff ≤ 2" was only WARN; gold-v2
confirmed that was too permissive.
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


def test_b2_fails_when_4_of_5_judges_solve_easy_question(monkeypatch):
    # v3.0.0: at difficulty ≤ 2, ≥4/5 closed-book solves is FAIL (tightened
    # from v2.0.0's "only 5/5 at diff≤2 is FAIL").
    b2 = _run_with_panel(
        monkeypatch,
        closed_book_choices=["A", "A", "A", "A", "B"],
        difficulty="2",
    )
    assert b2["severity"] == "fail", (
        f"v3.0.0: 4/5 keyed at diff=2 must FAIL; got {b2['severity']}"
    )
    payload = b2["payload"]
    assert payload["judges_keyed"] == 4
    assert payload["judges_total"] == 5
    assert payload["closed_book_correct"] is True
    assert payload["leakage_ratio"] == round(4 / 5, 3)


def test_b2_warns_when_3_of_5_judges_solve_easy_question(monkeypatch):
    # v3.0.0: 3/5 at diff ≤ 2 is WARN band.
    b2 = _run_with_panel(
        monkeypatch,
        closed_book_choices=["A", "A", "A", "B", "C"],
        difficulty="2",
    )
    assert b2["severity"] == "warn", (
        f"v3.0.0: 3/5 keyed at diff=2 must WARN; got {b2['severity']}"
    )


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


def test_b2_passes_when_only_3_of_5_judges_solve_hard(monkeypatch):
    # v3.0.0: at difficulty ≥ 3, 3/5 is below the WARN gate (4/5 minimum).
    b2 = _run_with_panel(
        monkeypatch,
        closed_book_choices=["A", "A", "A", "B", "C"],
        difficulty="3",
    )
    assert b2["severity"] == "pass", (
        f"v3.0.0: 3/5 at diff=3 is below WARN gate; got {b2['severity']}"
    )


def test_b2_warns_when_4_of_5_judges_solve_hard_question(monkeypatch):
    # v3.0.0: at difficulty ≥ 3, 4/5 is WARN; 5/5 is FAIL.
    b2 = _run_with_panel(
        monkeypatch,
        closed_book_choices=["A", "A", "A", "A", "B"],
        difficulty="4",
    )
    assert b2["severity"] == "warn", (
        f"Hard question with 4/5 leakage should WARN; got {b2['severity']}"
    )


def test_b2_fails_when_5_of_5_judges_solve_hard_question(monkeypatch):
    # v3.0.0: at difficulty ≥ 3, only 5/5 triggers FAIL.
    b2 = _run_with_panel(
        monkeypatch,
        closed_book_choices=["A", "A", "A", "A", "A"],
        difficulty="3",
    )
    assert b2["severity"] == "fail", (
        f"v3.0.0: 5/5 at diff=3 must FAIL; got {b2['severity']}"
    )


def test_judges_module_exposes_b2_panel():
    # The new constant exists and includes the test-taker-strength judges.
    assert _judges.JUDGE_PANEL_B2 == ("claude", "chatgpt", "gemini", "llama", "qwen")
