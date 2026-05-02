"""Tests for src/generators/_prompts.py — _avoid_wk_first_bullet."""

import pytest

from src.generators._prompts import _avoid_wk_first_bullet


class TestAvoidWkFirstBullet:
    """Tests for the _avoid_wk_first_bullet shared helper."""

    def test_avoid_wk_includes_ubiquitous_grape_bullet(self):
        """2g.17: The new bullet warning against ubiquitous-grape stems is present."""
        result = _avoid_wk_first_bullet("source fact")
        assert "globally-ubiquitous" in result, (
            "Expected 'globally-ubiquitous' marker phrase in output"
        )
        assert "Cabernet Sauvignon" in result, (
            "Expected canonical example grape 'Cabernet Sauvignon' in output"
        )
        assert "regulatory or technical detail" in result, (
            "Expected prescriptive guidance 'regulatory or technical detail' in output"
        )

    def test_avoid_wk_still_includes_iconic_block(self):
        """Regression: the original iconic-entities bullet must not be removed."""
        result = _avoid_wk_first_bullet("source fact")
        assert "Château Margaux" in result, (
            "Expected original iconic-entities example 'Château Margaux' to still be present"
        )

    def test_avoid_wk_fact_phrase_interpolated(self):
        """The fact_phrase argument is still interpolated into the first bullet."""
        result = _avoid_wk_first_bullet("target fact")
        assert "target fact" in result, (
            "Expected fact_phrase='target fact' to appear in the first bullet"
        )

    def test_avoid_wk_returns_two_bullets(self):
        """Output must contain at least two bullet lines (one per '-')."""
        result = _avoid_wk_first_bullet("source facts")
        bullet_count = result.count("\n- ")
        # The two bullets are joined by '\n', so the second starts with '- '
        # after the first newline; count '- ' occurrences to confirm both present.
        assert result.startswith("- "), "Output should start with first bullet marker"
        assert "- DO NOT phrase questions as \"Which region" in result, (
            "Second ubiquitous-grape bullet should be present as a separate bullet"
        )
