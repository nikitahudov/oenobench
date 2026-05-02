"""Phase 2g.18 lever L9 — fact_to_question must call ``sample_facts``
with ``require_substantive=True``.

Mirrors the same kwarg already passed by ``template_generator`` so the
substantive pre-filter applies regardless of the ``OENOBENCH_FACT_SUBSTANTIVE_FILTER``
env var. The env var stays the master switch; the kwarg makes FTQ opt-in
even when the env is off, trimming wasted Opus generation attempts on
filler facts the gate would reject.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.generators import fact_to_question


def test_fact_to_question_passes_require_substantive(monkeypatch):
    """Phase 2g.18: ``run_generate`` (FTQ) must call ``sample_facts``
    with ``require_substantive=True`` on every batch.

    The plan calls this lever L9. Mirror of template_generator.py:2452.
    """
    captured_kwargs: list[dict] = []

    # Stub the sampler — return empty so the loop exits immediately on
    # the first iteration (we only care about how it was called).
    def fake_sample_facts(*args, **kwargs):
        captured_kwargs.append(kwargs)
        return []

    monkeypatch.setattr(fact_to_question, "sample_facts", fake_sample_facts)

    # Stub the used-id helpers so the real DB isn't queried.
    monkeypatch.setattr(fact_to_question, "get_used_fact_ids", lambda: set())
    monkeypatch.setattr(
        fact_to_question, "get_attempted_fact_ids", lambda strategy: []
    )

    fact_to_question.run_generate(
        domain="wine_regions",
        count=5,
        generator="claude",
        question_type="multiple_choice",
        difficulty="2",
        cognitive_dim="recall",
        dry_run=True,
    )

    # At least one sampler call recorded.
    assert captured_kwargs, "sample_facts was not invoked"

    # Every call must pass require_substantive=True.
    for kw in captured_kwargs:
        assert kw.get("require_substantive") is True, (
            f"sample_facts call missing require_substantive=True; got: {kw!r}"
        )


def test_fact_to_question_keeps_strategy_kwarg(monkeypatch):
    """Sanity check: existing kwargs (strategy='fact_to_question',
    reject_ubiquitous_for_region_answer for grape_varieties) are still
    forwarded alongside the new require_substantive kwarg.
    """
    captured_kwargs: list[dict] = []

    def fake_sample_facts(*args, **kwargs):
        captured_kwargs.append(kwargs)
        return []

    monkeypatch.setattr(fact_to_question, "sample_facts", fake_sample_facts)
    monkeypatch.setattr(fact_to_question, "get_used_fact_ids", lambda: set())
    monkeypatch.setattr(
        fact_to_question, "get_attempted_fact_ids", lambda strategy: []
    )

    fact_to_question.run_generate(
        domain="grape_varieties",
        count=3,
        generator="claude",
        question_type="multiple_choice",
        difficulty="2",
        cognitive_dim="recall",
        dry_run=True,
    )

    assert captured_kwargs
    kw0 = captured_kwargs[0]
    assert kw0.get("strategy") == "fact_to_question"
    assert kw0.get("require_substantive") is True
    # Phase 2g.17 guard for "find-the-region" stems on grape_varieties.
    assert kw0.get("reject_ubiquitous_for_region_answer") is True
