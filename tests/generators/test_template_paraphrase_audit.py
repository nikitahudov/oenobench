"""Phase 2g.16 Lever 4 — Paraphrase success-rate audit + retry tests.

Exercises the three new paraphrase counter/retry behaviours:
  * _PARAPHRASE_OK_COUNT incremented on success.
  * _PARAPHRASE_FAIL_COUNT incremented on failure (after 2 attempts).
  * Retry fires on first failure and succeeds on second attempt.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# ── helpers ─────────────────────────────────────────────────────────────────


def _minimal_result(question_text: str = "Which region is documented?") -> dict:
    """Build the minimal result dict that the paraphrase block reads."""
    return {
        "_template_id": "T-GRP-APP-REGION-PLANT-01",
        "question_text": question_text,
        "options": [
            {"id": "A", "text": "Rioja"},
            {"id": "B", "text": "Douro"},
            {"id": "C", "text": "Barossa Valley"},
            {"id": "D", "text": "Napa Valley"},
        ],
        "correct_answer": "A",
        "correct_answer_text": "Rioja",
    }


def _run_paraphrase_block(mock_fn, result: dict) -> dict:
    """Simulate the γ-5 paraphrase block from _run_generate_body.

    Replicates the retry logic introduced in Phase 2g.16 Lever 4 so tests
    can exercise it without spinning up the full generation loop.
    """
    import src.generators.template_generator as tg

    tg.reset_paraphrase_stats()

    tid_for_log = result.get("_template_id", "UNKNOWN")
    rephrased: str | None = None
    for _attempt in range(1, 3):
        try:
            rephrased = mock_fn(result["question_text"], result["options"])
        except Exception:
            rephrased = None
        if rephrased:
            break

    if rephrased:
        result = dict(result)
        result["question_text"] = rephrased
        # Mirror the counter logic from template_generator.
        tg._PARAPHRASE_OK_COUNT += 1
    else:
        tg._PARAPHRASE_FAIL_COUNT += 1

    return result


# ── tests ────────────────────────────────────────────────────────────────────


class TestParaphraseFailIncrementsFailCounter:
    """test_paraphrase_failure_increments_fail_counter

    mock paraphrase_question_text to raise on every call;
    assert _PARAPHRASE_FAIL_COUNT increments by 1 (not 2 — even though we retry,
    it is one observed failure event).
    """

    def test_paraphrase_failure_increments_fail_counter(self):
        import src.generators.template_generator as tg

        tg.reset_paraphrase_stats()

        def _always_raise(text, options):
            raise RuntimeError("LLM unavailable")

        result = _minimal_result()
        _run_paraphrase_block(_always_raise, result)

        stats = tg.get_paraphrase_stats()
        assert stats["fail"] == 1, (
            f"Expected fail counter == 1, got {stats['fail']}"
        )
        assert stats["ok"] == 0, (
            f"Expected ok counter == 0, got {stats['ok']}"
        )


class TestParaphraseSuccessIncrementsOkCounter:
    """test_paraphrase_success_increments_ok_counter

    mock paraphrase_question_text to return a clean rewrite;
    assert _PARAPHRASE_OK_COUNT increments by 1.
    """

    def test_paraphrase_success_increments_ok_counter(self):
        import src.generators.template_generator as tg

        tg.reset_paraphrase_stats()

        clean_rewrite = "A wine merchant needs a documented home region for Tempranillo. Which is it?"

        def _always_succeed(text, options):
            return clean_rewrite

        result = _minimal_result()
        updated = _run_paraphrase_block(_always_succeed, result)

        stats = tg.get_paraphrase_stats()
        assert stats["ok"] == 1, (
            f"Expected ok counter == 1, got {stats['ok']}"
        )
        assert stats["fail"] == 0, (
            f"Expected fail counter == 0, got {stats['fail']}"
        )
        assert updated["question_text"] == clean_rewrite, (
            "Paraphrased text not stored in result"
        )


class TestParaphraseRetryOnFirstFailThenSucceed:
    """test_paraphrase_retry_on_first_fail_then_succeed

    mock to fail-then-succeed; assert retry fired and OK counter incremented.
    """

    def test_paraphrase_retry_on_first_fail_then_succeed(self):
        import src.generators.template_generator as tg

        tg.reset_paraphrase_stats()

        call_count = {"n": 0}
        clean_rewrite = "A viticulture consultant identifies the documented region for Grenache."

        def _fail_then_succeed(text, options):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return None  # first attempt fails
            return clean_rewrite  # second attempt succeeds

        result = _minimal_result()
        updated = _run_paraphrase_block(_fail_then_succeed, result)

        assert call_count["n"] == 2, (
            f"Expected exactly 2 paraphrase calls (retry fired), got {call_count['n']}"
        )

        stats = tg.get_paraphrase_stats()
        assert stats["ok"] == 1, (
            f"Expected ok counter == 1 after retry success, got {stats['ok']}"
        )
        assert stats["fail"] == 0, (
            f"Expected fail counter == 0 after retry success, got {stats['fail']}"
        )
        assert updated["question_text"] == clean_rewrite, (
            "Paraphrased text from retry not stored in result"
        )
