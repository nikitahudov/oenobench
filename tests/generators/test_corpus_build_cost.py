"""Phase 2g.8 corpus-build cost optimizations and closed-book quota wiring.

Three categories of test in this file:

1. ``insert_question_gated(pre_screened=...)`` lets the caller hand in a
   ``GateResult`` it already computed, so the wrapper doesn't run the gate
   a second time. This is what template_generator.py uses to gate BEFORE
   running paraphrase + verifier (Gemini), saving ~60% of those Gemini
   calls on audit_pilot_v6 where the gate flagged most templates.

2. ``LLMClient.generate(extra_body=...)`` forwards arbitrary OpenRouter
   request fields to the underlying chat-completions call. The verifier
   and paraphrase modules pass ``{"provider": {"sort": "price"}}`` so
   OpenRouter routes their sub-2K-token prompts to the cheapest provider
   for the target model — i.e. the standard sub-200K-context tier
   instead of the long-context tier that drove Gemini Pro to $15/MTok
   output pricing on audit_pilot_v6.

3. ``build_pilot_corpus()`` must call ``set_corpus_target()`` before its
   strategy dispatch loop so the 25% closed-book cap is evaluated against
   the pilot size (per_strategy × 5 strategies) rather than the full-run
   10k default. The v6 regression: a 264-Q corpus accumulated 158
   closed-book relabels (cap should have been ceil(264 × 0.25) = 66 but
   the process used the global 2500 cap). The override must also be
   cleared in a ``finally`` block so an exception in a strategy generator
   does not leak the override into subsequent processes.

   Plus the per-country-cap propagation tests (``_run_generator`` forwards
   ``--per-country-cap`` to the strategy subprocess, every strategy CLI
   accepts the flag, etc.) — Phase 2g.8 D3 wire-up.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from src.generators import _closed_book_gate, _question_db
from src.generators._closed_book_gate import GateResult


# ─── Fixtures ────────────────────────────────────────────────────────────────


_OPTS = [
    {"id": "A", "text": "Nebbiolo"},
    {"id": "B", "text": "Barbera"},
    {"id": "C", "text": "Dolcetto"},
    {"id": "D", "text": "Sangiovese"},
]


def _question(**overrides):
    base = {
        "question_id": "TEST-COST-001",
        "question_text": "Which grape is in Barolo?",
        "options": _OPTS,
        "correct_answer": "A",
        "difficulty": "1",
        "question_type": "multiple_choice",
        "domain": "wine_regions",
    }
    base.update(overrides)
    return base


# ─── Optimization 1: pre_screened wires through the wrapper ─────────────────


def test_insert_question_gated_uses_pre_screened_skips_inner_gate(monkeypatch):
    """When the caller supplies a pre_screened verdict, the wrapper must
    NOT call screen_question / the OpenRouter gate API again.
    """

    def explode(*_a, **_kw):
        raise AssertionError("screen_question must not be called when pre_screened is set")

    monkeypatch.setattr(_question_db, "screen_question", explode)
    monkeypatch.setattr(_closed_book_gate, "_call_gate", explode)
    monkeypatch.setattr(_question_db, "count_closed_book_solvable", lambda: 0)

    captured = {}

    def fake_insert(question_data, generation_meta, fact_ids, source_ids):
        captured["meta"] = generation_meta
        captured["data"] = question_data
        return "uuid-pre-screened"

    monkeypatch.setattr(_question_db, "insert_question", fake_insert)

    pre_gate = GateResult(
        passed=False,
        applied=True,
        reason="reject: pre-screened by caller (selected=A conf=0.95 >= 0.6)",
        selected="A",
        confidence=0.95,
        matched_gold=True,
    )

    q_uuid, gate = _question_db.insert_question_gated(
        question_data=_question(),
        generation_meta={"generator": "template_only", "generation_method": "template"},
        fact_ids=[],
        source_ids=[],
        pre_screened=pre_gate,
    )

    assert q_uuid == "uuid-pre-screened"
    # Wrapper still applied the relabel routing because pre_gate.passed=False.
    assert gate.relabeled is True
    assert captured["data"]["difficulty"] == "1"
    assert "closed_book_solvable" in captured["data"]["tags"]
    # And the verdict still got stashed in generation_meta.
    assert captured["meta"]["raw_response"]["gate"]["selected"] == "A"


def test_insert_question_gated_pre_screened_pass_path(monkeypatch):
    """A pre-screened PASS (gate did not flag) goes straight to insert with
    no relabel and no quota check.
    """

    def explode(*_a, **_kw):
        raise AssertionError("screen_question must not be called when pre_screened is set")

    monkeypatch.setattr(_question_db, "screen_question", explode)

    def quota_explode():
        raise AssertionError("count_closed_book_solvable must not be called on the pass path")

    monkeypatch.setattr(_question_db, "count_closed_book_solvable", quota_explode)

    captured = {}

    def fake_insert(question_data, generation_meta, fact_ids, source_ids):
        captured["data"] = question_data
        return "uuid-pass"

    monkeypatch.setattr(_question_db, "insert_question", fake_insert)

    pre_gate = GateResult(
        passed=True,
        applied=True,
        reason="pass: gate picked B (gold=A)",
        selected="B",
        confidence=0.4,
        matched_gold=False,
    )

    q_uuid, gate = _question_db.insert_question_gated(
        question_data=_question(difficulty="2"),
        generation_meta={"generator": "template_only", "generation_method": "template"},
        fact_ids=[],
        source_ids=[],
        pre_screened=pre_gate,
    )

    assert q_uuid == "uuid-pass"
    assert gate.passed is True
    assert gate.relabeled is False
    # Original difficulty preserved.
    assert captured["data"]["difficulty"] == "2"
    # No closed_book_solvable tag added on the pass path.
    assert "closed_book_solvable" not in (captured["data"].get("tags") or [])


def test_insert_question_gated_pre_screened_quota_full(monkeypatch):
    """Phase 2g.15 (Team B): pre-screened reject + quota full → INSERT as
    cb_reserve (not dropped). uuid is non-None; status must be 'cb_reserve'.
    """
    monkeypatch.setattr(
        _question_db, "screen_question",
        lambda **_kw: (_ for _ in ()).throw(
            AssertionError("must not call screen_question with pre_screened set")
        ),
    )
    # Quota is at the 40%-of-default-corpus cap (10000 × 0.40 = 4000).
    # Phase 2g.18 cost-down L1 raised the fraction from 0.25 → 0.40.
    monkeypatch.setattr(_question_db, "count_closed_book_solvable", lambda: 4000)

    captured: dict = {}

    def fake_insert(*_a, status="draft", **_kw):
        captured["status"] = status
        return "uuid-reserved-prescreened"

    monkeypatch.setattr(_question_db, "insert_question", fake_insert)

    pre_gate = GateResult(
        passed=False,
        applied=True,
        reason="reject: gate solved closed-book (selected=A conf=0.9 >= 0.6)",
        selected="A",
        confidence=0.9,
        matched_gold=True,
    )

    q_uuid, gate = _question_db.insert_question_gated(
        question_data=_question(),
        generation_meta={"generator": "template_only", "generation_method": "template"},
        fact_ids=[],
        source_ids=[],
        pre_screened=pre_gate,
    )

    assert q_uuid == "uuid-reserved-prescreened"
    assert captured["status"] == "cb_reserve"
    assert gate.quota_full is True
    assert gate.relabeled is False


def test_insert_question_gated_no_pre_screened_falls_back_to_inner_gate(monkeypatch):
    """Backwards compatibility: callers that don't pass pre_screened still
    get the original behaviour (inner screen_question call).
    """
    called = {}

    def fake_screen(**kwargs):
        called["screen"] = kwargs
        return GateResult(
            passed=True,
            applied=True,
            reason="pass: gate picked B (gold=A)",
            selected="B",
            confidence=0.3,
            matched_gold=False,
        )

    monkeypatch.setattr(_question_db, "screen_question", fake_screen)
    monkeypatch.setattr(_question_db, "insert_question", lambda *a, **kw: "uuid-fallback")

    q_uuid, gate = _question_db.insert_question_gated(
        question_data=_question(),
        generation_meta={"generator": "test", "generation_method": "test"},
        fact_ids=[],
        source_ids=[],
    )
    assert q_uuid == "uuid-fallback"
    assert "screen" in called
    assert gate.passed is True


# ─── Optimization 3: extra_body forwards to the OpenRouter call ─────────────


@dataclass
class _Msg:
    content: str = '{"chosen": "A"}'


@dataclass
class _Choice:
    message: _Msg


@dataclass
class _Usage:
    prompt_tokens: int = 50
    completion_tokens: int = 10


@dataclass
class _Completion:
    choices: list
    usage: _Usage = None
    model: str = "google/gemini-3.1-pro-preview-20260219"

    def __post_init__(self):
        if self.usage is None:
            self.usage = _Usage()


def test_llm_client_generate_forwards_extra_body(monkeypatch):
    """LLMClient.generate(extra_body={...}) must pass the dict through to
    chat.completions.create as the extra_body kwarg, where the OpenAI SDK
    forwards it into the request body OpenRouter receives.
    """
    from src.generators._llm_client import LLMClient

    captured = {}

    class _FakeChatCompletions:
        def create(self, **kwargs):
            captured.update(kwargs)
            return _Completion(choices=[_Choice(message=_Msg())])

    class _FakeChat:
        completions = _FakeChatCompletions()

    class _FakeClient:
        chat = _FakeChat()

    client = LLMClient(api_key="dummy")
    monkeypatch.setattr(client, "_client", _FakeClient())
    # Suppress the post-call sleep so the test runs fast.
    monkeypatch.setattr("src.generators._llm_client.time.sleep", lambda *_: None)

    response = client.generate(
        prompt="hello",
        model="gemini",
        extra_body={"provider": {"sort": "price"}},
    )

    assert response.success is True
    # The captured request kwargs include extra_body verbatim.
    assert captured.get("extra_body") == {"provider": {"sort": "price"}}


def test_llm_client_generate_no_extra_body_omits_kwarg(monkeypatch):
    """When extra_body is not passed, it must NOT appear in the request kwargs
    (so we don't accidentally override OpenRouter's default routing for the
    main generators and the audit panel).
    """
    from src.generators._llm_client import LLMClient

    captured = {}

    class _FakeChatCompletions:
        def create(self, **kwargs):
            captured.update(kwargs)
            return _Completion(choices=[_Choice(message=_Msg())])

    class _FakeChat:
        completions = _FakeChatCompletions()

    class _FakeClient:
        chat = _FakeChat()

    client = LLMClient(api_key="dummy")
    monkeypatch.setattr(client, "_client", _FakeClient())
    monkeypatch.setattr("src.generators._llm_client.time.sleep", lambda *_: None)

    client.generate(prompt="hello", model="gemini")
    assert "extra_body" not in captured


def test_template_verifier_pins_cheap_provider(monkeypatch):
    """verify_template_answer_with_gemini must pass the cheap-provider hint."""
    from src.generators import _verify
    from src.generators._llm_client import LLMResponse

    captured = {}

    def fake_generate(self, **kwargs):
        captured.update(kwargs)
        return LLMResponse(
            content='{"chosen": "A"}',
            parsed={"chosen": "A"},
            model="google/gemini-3.1-pro-preview-20260219",
            input_tokens=120,
            output_tokens=8,
            success=True,
        )

    monkeypatch.setattr(
        "src.generators._llm_client.LLMClient.generate",
        fake_generate,
    )

    agrees, debug = _verify.verify_template_answer_with_gemini(
        question_text="Which grape is in Barolo?",
        options=_OPTS,
        correct_answer_id="A",
        source_fact_text="Barolo DOCG requires 100% Nebbiolo.",
    )

    assert agrees is True
    assert captured.get("extra_body") == {"provider": {"sort": "price"}}


def test_template_paraphrase_pins_cheap_provider(monkeypatch):
    """paraphrase_question_text must pass the cheap-provider hint."""
    from src.generators import _template_paraphrase
    from src.generators._llm_client import LLMResponse

    captured = {}

    def fake_generate(self, **kwargs):
        captured.update(kwargs)
        # Return a paraphrase that satisfies length + entity-preservation rules.
        return LLMResponse(
            content='{"question_text": "In the Barolo region, which grape is mandatory?"}',
            parsed={
                "question_text": "In the Barolo region, which grape is mandatory?"
            },
            model="google/gemini-3.1-pro-preview-20260219",
            input_tokens=180,
            output_tokens=20,
            success=True,
        )

    monkeypatch.setattr(
        "src.generators._llm_client.LLMClient.generate",
        fake_generate,
    )

    out = _template_paraphrase.paraphrase_question_text(
        "Which grape is mandatory in the Barolo region?",
        _OPTS,
    )
    # Paraphrase may return None if validation rejects the rephrasing; we
    # only require that the LLM call carried the routing hint.
    assert captured.get("extra_body") == {"provider": {"sort": "price"}}
    # Sanity: when validation passes, a non-None new stem is returned.
    if out is not None:
        assert "Barolo" in out


# ─── Phase 2g.8 D3 wire-up: --per-country-cap propagation ────────────────────
#
# The previous wire-up only carried per_country_cap as a Python kwarg on the
# sampler functions — the audit-pilot orchestrator never passed it through to
# the strategy subprocesses, so audit_pilot_v6 ran with NO cap (D3 = 4.52
# despite the cap supposedly being set). These tests pin down the propagation
# at every layer so the regression cannot return.


def test_run_generator_omits_per_country_cap_flag_when_none(monkeypatch):
    """Backwards compatibility: callers that don't pass per_country_cap must
    not push --per-country-cap onto the subprocess argv.

    Phase 2g.10 (Team Delta A2): exercise the subprocess fallback path,
    since in-process dispatch has no argv. Set OENOBENCH_USE_SUBPROCESS_DISPATCH=1
    so the original subprocess assertion still holds.
    """
    from unittest.mock import patch
    from src.qa import _corpus

    monkeypatch.setenv("OENOBENCH_USE_SUBPROCESS_DISPATCH", "1")
    with patch("src.qa._corpus.subprocess.run") as fake_run:
        fake_run.return_value.returncode = 0
        _corpus._run_generator(module="template_generator", domain="wine_regions", count=10)

    args = fake_run.call_args[0][0]
    assert "--per-country-cap" not in args
    # And the basic args we depend on still go through.
    assert "--domain" in args and "--count" in args


def test_run_generator_forwards_per_country_cap_to_subprocess(monkeypatch):
    """Phase 2g.8 fix: when the caller passes per_country_cap, it must
    appear on the strategy subprocess command line as --per-country-cap N.
    Phase 2g.10: must flip OENOBENCH_USE_SUBPROCESS_DISPATCH=1 to exercise
    the subprocess argv path explicitly.
    """
    from unittest.mock import patch
    from src.qa import _corpus

    monkeypatch.setenv("OENOBENCH_USE_SUBPROCESS_DISPATCH", "1")
    with patch("src.qa._corpus.subprocess.run") as fake_run:
        fake_run.return_value.returncode = 0
        _corpus._run_generator(
            module="template_generator", domain="wine_regions", count=10,
            per_country_cap=0.10,
        )

    args = fake_run.call_args[0][0]
    assert "--per-country-cap" in args
    idx = args.index("--per-country-cap")
    assert args[idx + 1] == "0.1"


def test_run_generator_forwards_with_generator_and_difficulty(monkeypatch):
    """All flags must coexist on the LLM-strategy path (--generator,
    --difficulty, --per-country-cap).
    Phase 2g.10: subprocess fallback path.
    """
    from unittest.mock import patch
    from src.qa import _corpus

    monkeypatch.setenv("OENOBENCH_USE_SUBPROCESS_DISPATCH", "1")
    with patch("src.qa._corpus.subprocess.run") as fake_run:
        fake_run.return_value.returncode = 0
        _corpus._run_generator(
            module="fact_to_question", domain="grape_varieties", count=4,
            generator="claude", difficulty=2, per_country_cap=0.15,
        )

    args = fake_run.call_args[0][0]
    assert "--generator" in args and args[args.index("--generator") + 1] == "claude"
    assert "--difficulty" in args and args[args.index("--difficulty") + 1] == "2"
    assert "--per-country-cap" in args and args[args.index("--per-country-cap") + 1] == "0.15"


def test_build_pilot_corpus_forwards_per_country_cap(monkeypatch):
    """build_pilot_corpus must hand its per_country_cap down to every
    strategy subprocess via _run_generator. We don't run the actual builds
    — we just assert the inner _run_generator calls all carry the kwarg.
    """
    from src.qa import _corpus

    captured: list[dict] = []

    def fake_run_generator(*, module, domain, count, generator=None,
                           difficulty=None, per_country_cap=None):
        captured.append({
            "module": module, "domain": domain, "count": count,
            "generator": generator, "per_country_cap": per_country_cap,
        })
        return True

    monkeypatch.setattr(_corpus, "_run_generator", fake_run_generator)
    monkeypatch.setattr(_corpus, "_existing_corpus_count", lambda tag: {})
    monkeypatch.setattr(_corpus, "_tag_rows", lambda **kw: 0)
    # Keep per_strategy tiny so the test is fast — we only need ≥1 call per
    # strategy to verify propagation.
    _corpus.build_pilot_corpus(
        tag="test_v7",
        per_strategy=1,
        seed=1,
        per_country_cap=0.10,
    )

    assert captured, "build_pilot_corpus must dispatch at least one strategy"
    for call in captured:
        assert call["per_country_cap"] == 0.10, (
            f"per_country_cap not forwarded: {call}"
        )


def test_build_pilot_corpus_omits_cap_when_none(monkeypatch):
    """Default (None) per_country_cap must reach _run_generator unchanged
    so the subprocess argv stays clean.
    """
    from src.qa import _corpus

    captured: list[dict] = []

    def fake_run_generator(*, module, domain, count, generator=None,
                           difficulty=None, per_country_cap=None):
        captured.append({"per_country_cap": per_country_cap})
        return True

    monkeypatch.setattr(_corpus, "_run_generator", fake_run_generator)
    monkeypatch.setattr(_corpus, "_existing_corpus_count", lambda tag: {})
    monkeypatch.setattr(_corpus, "_tag_rows", lambda **kw: 0)

    _corpus.build_pilot_corpus(tag="test_no_cap", per_strategy=1, seed=1)

    assert captured
    for call in captured:
        assert call["per_country_cap"] is None


def test_strategy_clis_all_accept_per_country_cap_flag():
    """All 5 strategy CLIs must register --per-country-cap as a click
    option. Catches the regression where Team ε's merge added the kwarg
    to the sampler functions but only wired the flag into fact_to_question.
    """
    from click.testing import CliRunner
    from src.generators import (
        comparative_generator,
        distractor_miner,
        fact_to_question,
        scenario_generator,
        template_generator,
    )

    modules = {
        "fact_to_question": fact_to_question.main,
        "template_generator": template_generator.main,
        "scenario_generator": scenario_generator.main,
        "comparative_generator": comparative_generator.main,
        "distractor_miner": distractor_miner.main,
    }
    runner = CliRunner()
    for name, cmd in modules.items():
        result = runner.invoke(cmd, ["--help"])
        assert result.exit_code == 0, f"{name} --help failed: {result.output}"
        assert "--per-country-cap" in result.output, (
            f"{name} missing --per-country-cap in --help output"
        )


def test_orchestrator_build_corpus_cli_accepts_per_country_cap():
    """The audit-pilot orchestrator's `build-corpus` subcommand must expose
    --per-country-cap so audit shell scripts can set it.
    """
    from click.testing import CliRunner
    from src.qa.orchestrator import cli as orchestrator_cli

    runner = CliRunner()
    result = runner.invoke(orchestrator_cli, ["build-corpus", "--help"])
    assert result.exit_code == 0, result.output
    assert "--per-country-cap" in result.output


# ─── Phase 2g.8 closed-book quota wiring: set_corpus_target propagation ─────
#
# `build_pilot_corpus()` must call `set_corpus_target()` before dispatching
# strategies so the 25% closed-book quota cap is scoped to the pilot size
# rather than the full-run 10k default. v6 ran with cap=2500 (effectively
# unbounded for a 600-Q pilot) and accumulated 158 relabels on a 264-Q
# corpus — should have been bounded at ceil(264 × 0.25) = 66.


@pytest.fixture(autouse=True)
def _reset_corpus_target_override():
    """Always clear the override before and after each test so a leaky test
    cannot poison another."""
    from src.generators import _question_db as _qdb
    _qdb.set_corpus_target(None)
    yield
    _qdb.set_corpus_target(None)


def _patch_db_helpers(monkeypatch):
    """Stub out the DB helpers `build_pilot_corpus` would otherwise hit."""
    from datetime import datetime
    from src.qa import _corpus as _c
    monkeypatch.setattr(_c, "_existing_corpus_count", lambda tag: {})
    monkeypatch.setattr(
        _c,
        "_tag_rows",
        lambda *, generation_method, since, limit, tag: limit,
    )
    # Default to the FRESH-BUILD branch so tests don't depend on DB state.
    # Individual tests that exercise resume behaviour patch this directly.
    monkeypatch.setattr(
        _c,
        "_resolve_build_started_at",
        lambda tag: (datetime.now(), False),
    )


def test_build_pilot_corpus_sets_corpus_target_during_dispatch(monkeypatch):
    """While the strategy dispatch loop runs, `_CORPUS_TARGET_OVERRIDE` must
    equal `per_strategy × len(STRATEGY_MODULES)` so the closed-book quota cap
    is scoped to the pilot, not the global 10k.
    """
    from src.generators import _question_db as _qdb
    from src.qa import _corpus as _c
    from src.qa._corpus import STRATEGY_MODULES, build_pilot_corpus

    _patch_db_helpers(monkeypatch)

    captured: list[int | None] = []

    def fake_run_generator(*, module, domain, count, generator=None,
                           difficulty=None, per_country_cap=None):
        captured.append(_qdb._CORPUS_TARGET_OVERRIDE)
        return True

    monkeypatch.setattr(_c, "_run_generator", fake_run_generator)

    per_strategy = 60
    expected_target = per_strategy * len(STRATEGY_MODULES)

    build_pilot_corpus(tag="audit_pilot_test", per_strategy=per_strategy, seed=42)

    assert captured, "_run_generator was never called — dispatch loop did not run"
    # Every observation during the dispatch loop must show the same scoped
    # override; the override must NOT be the default 10k or None.
    assert all(v == expected_target for v in captured), (
        f"Expected all _CORPUS_TARGET_OVERRIDE samples == {expected_target}, "
        f"got {set(captured)}"
    )


def test_build_pilot_corpus_resets_corpus_target_after(monkeypatch):
    """After `build_pilot_corpus` returns, the override must be cleared so a
    subsequent full-gen run sees the unscoped (None → 10k) default.
    """
    from src.generators import _question_db as _qdb
    from src.qa import _corpus as _c
    from src.qa._corpus import build_pilot_corpus

    _patch_db_helpers(monkeypatch)
    monkeypatch.setattr(
        _c,
        "_run_generator",
        lambda *, module, domain, count, generator=None,
               difficulty=None, per_country_cap=None: True,
    )

    # Pre-condition: no override leaked from a prior test.
    assert _qdb._CORPUS_TARGET_OVERRIDE is None

    build_pilot_corpus(tag="audit_pilot_test", per_strategy=30, seed=42)

    assert _qdb._CORPUS_TARGET_OVERRIDE is None, (
        "build_pilot_corpus must reset _CORPUS_TARGET_OVERRIDE to None on success"
    )


def test_build_pilot_corpus_resets_corpus_target_on_exception(monkeypatch):
    """If a strategy generator raises, the override must STILL be reset by
    the `finally` block — otherwise the leak poisons subsequent processes.
    """
    from src.generators import _question_db as _qdb
    from src.qa import _corpus as _c
    from src.qa._corpus import build_pilot_corpus

    _patch_db_helpers(monkeypatch)

    class _StrategyBoom(RuntimeError):
        pass

    def boom(*, module, domain, count, generator=None,
             difficulty=None, per_country_cap=None):
        raise _StrategyBoom("simulated generator failure")

    monkeypatch.setattr(_c, "_run_generator", boom)

    with pytest.raises(_StrategyBoom):
        build_pilot_corpus(tag="audit_pilot_test", per_strategy=30, seed=42)

    assert _qdb._CORPUS_TARGET_OVERRIDE is None, (
        "Override must be reset even when the strategy dispatch loop raises; "
        "otherwise the leak poisons full-gen runs."
    )


# ─── Phase 2g.9 OENOBENCH_CORPUS_TARGET subprocess propagation ──────────────
#
# `set_corpus_target()` only mutates an in-process module-global, which does
# not survive `subprocess.run`. The orchestrator must also export an env var
# so child strategy CLIs resolve the same scoped quota cap. Without this, v7
# ran with the default 2500 cap and accumulated 172 closed-book relabels on
# a 242-Q corpus instead of the intended 150.


def test_build_pilot_corpus_exports_env_var_during_dispatch(monkeypatch):
    """While the dispatch loop runs, OENOBENCH_CORPUS_TARGET must be set in
    the process environment so any subprocess inherits the scoped value.
    """
    from src.generators._question_db import CORPUS_TARGET_ENV_VAR
    from src.qa import _corpus as _c
    from src.qa._corpus import STRATEGY_MODULES, build_pilot_corpus

    _patch_db_helpers(monkeypatch)
    monkeypatch.delenv(CORPUS_TARGET_ENV_VAR, raising=False)

    captured: list[str | None] = []

    def fake_run_generator(*, module, domain, count, generator=None,
                           difficulty=None, per_country_cap=None):
        captured.append(os.environ.get(CORPUS_TARGET_ENV_VAR))
        return True

    monkeypatch.setattr(_c, "_run_generator", fake_run_generator)

    per_strategy = 60
    expected_target = str(per_strategy * len(STRATEGY_MODULES))

    build_pilot_corpus(tag="audit_pilot_test", per_strategy=per_strategy, seed=42)

    assert captured, "_run_generator was never called"
    assert all(v == expected_target for v in captured), (
        f"OENOBENCH_CORPUS_TARGET must equal {expected_target} during every "
        f"_run_generator call; saw distinct values {set(captured)}"
    )


def test_build_pilot_corpus_clears_env_var_after(monkeypatch):
    """After return, the env var must be removed (when previously unset) so
    subsequent unrelated processes don't inherit a stale value.
    """
    from src.generators._question_db import CORPUS_TARGET_ENV_VAR
    from src.qa import _corpus as _c
    from src.qa._corpus import build_pilot_corpus

    _patch_db_helpers(monkeypatch)
    monkeypatch.delenv(CORPUS_TARGET_ENV_VAR, raising=False)
    monkeypatch.setattr(
        _c,
        "_run_generator",
        lambda *, module, domain, count, generator=None,
               difficulty=None, per_country_cap=None: True,
    )

    build_pilot_corpus(tag="audit_pilot_test", per_strategy=30, seed=42)

    assert CORPUS_TARGET_ENV_VAR not in os.environ


def test_build_pilot_corpus_restores_pre_existing_env_var(monkeypatch):
    """If the caller already had OENOBENCH_CORPUS_TARGET set (e.g. CI rig),
    the original value must be restored on exit, not stripped to None.
    """
    from src.generators._question_db import CORPUS_TARGET_ENV_VAR
    from src.qa import _corpus as _c
    from src.qa._corpus import build_pilot_corpus

    _patch_db_helpers(monkeypatch)
    monkeypatch.setenv(CORPUS_TARGET_ENV_VAR, "12345")
    monkeypatch.setattr(
        _c,
        "_run_generator",
        lambda *, module, domain, count, generator=None,
               difficulty=None, per_country_cap=None: True,
    )

    build_pilot_corpus(tag="audit_pilot_test", per_strategy=30, seed=42)

    assert os.environ.get(CORPUS_TARGET_ENV_VAR) == "12345", (
        "Pre-existing env-var value must be restored, not stripped"
    )


# ─── Phase 2g.9 hotfix — OENOBENCH_CORPUS_BUILD_SINCE export ────────────────


def test_build_pilot_corpus_exports_build_since_env_var_during_dispatch(monkeypatch):
    """While the dispatch loop runs, OENOBENCH_CORPUS_BUILD_SINCE must be set
    to the build's start timestamp (ISO-8601) so subprocesses scope their
    cb-count query to the current build only."""
    from src.generators._question_db import CORPUS_BUILD_SINCE_ENV_VAR
    from src.qa import _corpus as _c
    from src.qa._corpus import build_pilot_corpus

    _patch_db_helpers(monkeypatch)
    monkeypatch.delenv(CORPUS_BUILD_SINCE_ENV_VAR, raising=False)

    captured: list[str | None] = []

    def fake_run_generator(*, module, domain, count, generator=None,
                           difficulty=None, per_country_cap=None):
        captured.append(os.environ.get(CORPUS_BUILD_SINCE_ENV_VAR))
        return True

    monkeypatch.setattr(_c, "_run_generator", fake_run_generator)

    build_pilot_corpus(tag="audit_pilot_test", per_strategy=10, seed=42)

    assert captured, "_run_generator was never called"
    assert all(v for v in captured), (
        f"OENOBENCH_CORPUS_BUILD_SINCE must be set during every _run_generator; "
        f"saw {captured!r}"
    )
    # All values must be identical across the dispatch loop (single build).
    assert len(set(captured)) == 1, f"timestamp must be stable; saw {set(captured)}"
    # Must be parseable as an ISO-8601 timestamp.
    from datetime import datetime
    datetime.fromisoformat(captured[0])  # raises if malformed


def test_build_pilot_corpus_clears_build_since_env_var_after(monkeypatch):
    """After return, the env var must be removed (when previously unset)."""
    from src.generators._question_db import CORPUS_BUILD_SINCE_ENV_VAR
    from src.qa import _corpus as _c
    from src.qa._corpus import build_pilot_corpus

    _patch_db_helpers(monkeypatch)
    monkeypatch.delenv(CORPUS_BUILD_SINCE_ENV_VAR, raising=False)
    monkeypatch.setattr(
        _c,
        "_run_generator",
        lambda *, module, domain, count, generator=None,
               difficulty=None, per_country_cap=None: True,
    )

    build_pilot_corpus(tag="audit_pilot_test", per_strategy=10, seed=42)

    assert CORPUS_BUILD_SINCE_ENV_VAR not in os.environ


def test_build_pilot_corpus_restores_pre_existing_build_since(monkeypatch):
    """Pre-existing env var value must be restored on exit, not stripped."""
    from src.generators._question_db import CORPUS_BUILD_SINCE_ENV_VAR
    from src.qa import _corpus as _c
    from src.qa._corpus import build_pilot_corpus

    _patch_db_helpers(monkeypatch)
    monkeypatch.setenv(CORPUS_BUILD_SINCE_ENV_VAR, "2024-01-01T00:00:00Z")
    monkeypatch.setattr(
        _c,
        "_run_generator",
        lambda *, module, domain, count, generator=None,
               difficulty=None, per_country_cap=None: True,
    )

    build_pilot_corpus(tag="audit_pilot_test", per_strategy=10, seed=42)

    assert os.environ.get(CORPUS_BUILD_SINCE_ENV_VAR) == "2024-01-01T00:00:00Z"


# ─── Phase 2g.10 — OENOBENCH_STRATEGY_TARGET export ─────────────────────────
#
# Per-strategy closed-book budget. The orchestrator must export
# OENOBENCH_STRATEGY_TARGET=per_strategy so subprocess strategy CLIs pass
# the per-strategy cap into insert_question_gated. Without this, the
# default (env var unset) is corpus-level cap — back to v6/v7 behaviour.


def test_build_pilot_corpus_exports_strategy_target_during_dispatch(monkeypatch):
    """While the dispatch loop runs, OENOBENCH_STRATEGY_TARGET must equal the
    per_strategy size, NOT the corpus target."""
    from src.generators._question_db import STRATEGY_TARGET_ENV_VAR
    from src.qa import _corpus as _c
    from src.qa._corpus import build_pilot_corpus

    _patch_db_helpers(monkeypatch)
    monkeypatch.delenv(STRATEGY_TARGET_ENV_VAR, raising=False)

    captured: list[str | None] = []

    def fake_run_generator(*, module, domain, count, generator=None,
                           difficulty=None, per_country_cap=None):
        captured.append(os.environ.get(STRATEGY_TARGET_ENV_VAR))
        return True

    monkeypatch.setattr(_c, "_run_generator", fake_run_generator)

    per_strategy = 40
    build_pilot_corpus(tag="audit_pilot_test", per_strategy=per_strategy, seed=42)

    assert captured, "_run_generator was never called"
    assert all(v == str(per_strategy) for v in captured), (
        f"OENOBENCH_STRATEGY_TARGET must equal {per_strategy} (per_strategy, "
        f"NOT the corpus target) during every _run_generator call; saw "
        f"distinct values {set(captured)}"
    )


def test_build_pilot_corpus_clears_strategy_target_after(monkeypatch):
    """After return, the env var must be removed (when previously unset)."""
    from src.generators._question_db import STRATEGY_TARGET_ENV_VAR
    from src.qa import _corpus as _c
    from src.qa._corpus import build_pilot_corpus

    _patch_db_helpers(monkeypatch)
    monkeypatch.delenv(STRATEGY_TARGET_ENV_VAR, raising=False)
    monkeypatch.setattr(
        _c,
        "_run_generator",
        lambda *, module, domain, count, generator=None,
               difficulty=None, per_country_cap=None: True,
    )

    build_pilot_corpus(tag="audit_pilot_test", per_strategy=10, seed=42)

    assert STRATEGY_TARGET_ENV_VAR not in os.environ


def test_build_pilot_corpus_restores_pre_existing_strategy_target(monkeypatch):
    """Pre-existing env-var value must be restored on exit, not stripped."""
    from src.generators._question_db import STRATEGY_TARGET_ENV_VAR
    from src.qa import _corpus as _c
    from src.qa._corpus import build_pilot_corpus

    _patch_db_helpers(monkeypatch)
    monkeypatch.setenv(STRATEGY_TARGET_ENV_VAR, "999")
    monkeypatch.setattr(
        _c,
        "_run_generator",
        lambda *, module, domain, count, generator=None,
               difficulty=None, per_country_cap=None: True,
    )

    build_pilot_corpus(tag="audit_pilot_test", per_strategy=10, seed=42)

    assert os.environ.get(STRATEGY_TARGET_ENV_VAR) == "999", (
        "Pre-existing env-var value must be restored, not stripped"
    )


# ─── Phase 2g.10 — restart-safe build start time ────────────────────────────
#
# `started = datetime.now()` at every entry to build_pilot_corpus is wrong
# when the build script crashes/is killed and the user re-runs the same tag:
# each restart resets the cb-count `since` window, so cb-relabels from
# prior process(es) fall outside the window and the per-strategy +
# per-corpus caps both under-count. v8 accumulated 53 relabels (29+13+11)
# across 3 sessions with 0 GATE QUOTA FULL events, well past both caps.


def test_build_pilot_corpus_uses_resumed_started_at_when_tag_exists(monkeypatch):
    """When the build tag already has questions, `since` must come from
    MIN(created_at) of those questions, not the current process clock.

    The env var OENOBENCH_CORPUS_BUILD_SINCE is what subprocesses read; if
    it equals the resumed timestamp, prior cb-tags fall inside the window
    and are counted toward the cap.
    """
    from datetime import datetime, timedelta
    from src.generators._question_db import CORPUS_BUILD_SINCE_ENV_VAR
    from src.qa import _corpus as _c
    from src.qa._corpus import build_pilot_corpus

    monkeypatch.setattr(_c, "_existing_corpus_count", lambda tag: {})
    monkeypatch.setattr(
        _c, "_tag_rows",
        lambda *, generation_method, since, limit, tag: limit,
    )

    # Simulate a prior run that started 2h ago (resume case).
    prior_start = datetime.now() - timedelta(hours=2)
    monkeypatch.setattr(
        _c, "_resolve_build_started_at",
        lambda tag: (prior_start, True),
    )
    monkeypatch.delenv(CORPUS_BUILD_SINCE_ENV_VAR, raising=False)

    captured: list[str | None] = []

    def fake_run_generator(*, module, domain, count, generator=None,
                           difficulty=None, per_country_cap=None):
        captured.append(os.environ.get(CORPUS_BUILD_SINCE_ENV_VAR))
        return True

    monkeypatch.setattr(_c, "_run_generator", fake_run_generator)

    build_pilot_corpus(tag="audit_pilot_test", per_strategy=10, seed=42)

    assert captured, "_run_generator was never called"
    expected = prior_start.isoformat()
    assert all(v == expected for v in captured), (
        f"OENOBENCH_CORPUS_BUILD_SINCE must equal the resumed start time "
        f"({expected!r}) on resume; saw distinct values {set(captured)}"
    )


def test_build_pilot_corpus_uses_now_when_tag_is_fresh(monkeypatch):
    """When no questions are tagged with the build tag, `since` must be
    set to a fresh `datetime.now()` (the conventional fresh-start path).
    """
    from datetime import datetime
    from src.generators._question_db import CORPUS_BUILD_SINCE_ENV_VAR
    from src.qa import _corpus as _c
    from src.qa._corpus import build_pilot_corpus

    monkeypatch.setattr(_c, "_existing_corpus_count", lambda tag: {})
    monkeypatch.setattr(
        _c, "_tag_rows",
        lambda *, generation_method, since, limit, tag: limit,
    )

    fresh_start = datetime.now()
    monkeypatch.setattr(
        _c, "_resolve_build_started_at",
        lambda tag: (fresh_start, False),
    )
    monkeypatch.delenv(CORPUS_BUILD_SINCE_ENV_VAR, raising=False)

    captured: list[str | None] = []

    def fake_run_generator(*, module, domain, count, generator=None,
                           difficulty=None, per_country_cap=None):
        captured.append(os.environ.get(CORPUS_BUILD_SINCE_ENV_VAR))
        return True

    monkeypatch.setattr(_c, "_run_generator", fake_run_generator)

    build_pilot_corpus(tag="audit_pilot_test", per_strategy=10, seed=42)

    assert captured, "_run_generator was never called"
    assert all(v == fresh_start.isoformat() for v in captured), (
        f"Fresh build must use a single fresh-start timestamp; saw {set(captured)}"
    )


def test_resolve_build_started_at_returns_min_created_at_on_resume(monkeypatch):
    """The helper queries MIN(created_at) for the tag and returns
    (min_ts, True) when prior questions exist.
    """
    from datetime import datetime, timedelta
    from src.qa import _corpus as _c

    expected = datetime.now() - timedelta(hours=3)

    class _FakeCursor:
        def execute(self, query, params):
            self._params = params
            assert "MIN(created_at)" in query
            assert "ANY(tags)" in query

        def fetchone(self):
            return {"earliest": expected}

    class _FakeConn:
        def cursor(self):
            return _FakeCursor()

    monkeypatch.setattr(_c, "get_pg", lambda: _FakeConn())

    started, is_resume = _c._resolve_build_started_at("audit_pilot_v8")

    assert is_resume is True
    assert started == expected


def test_resolve_build_started_at_returns_now_when_tag_unseen(monkeypatch):
    """No prior tagged rows → return (datetime.now(), False)."""
    from datetime import datetime
    from src.qa import _corpus as _c

    class _FakeCursor:
        def execute(self, query, params):
            pass

        def fetchone(self):
            return {"earliest": None}

    class _FakeConn:
        def cursor(self):
            return _FakeCursor()

    monkeypatch.setattr(_c, "get_pg", lambda: _FakeConn())

    before = datetime.now()
    started, is_resume = _c._resolve_build_started_at("audit_pilot_fresh")
    after = datetime.now()

    assert is_resume is False
    assert before <= started <= after
