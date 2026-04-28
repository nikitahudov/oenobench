"""Phase 2g.10 (Team Delta) — A2 in-process dispatch.

A2 covers:

- Each strategy module exposes a stable ``run_generate(...)`` callable.
- ``_corpus._run_generator`` and ``orchestrator._run_strategy`` route through
  ``run_generate(...)`` in-process by default.
- Setting ``OENOBENCH_USE_SUBPROCESS_DISPATCH=1`` flips back to the legacy
  ``subprocess.run`` path (defence-in-depth roll-back hatch).
- The click ``main()`` shims still parse CLI args correctly.

A3 (concurrent cells + threading.Lock) follows in a sibling commit.
"""

from __future__ import annotations

from unittest.mock import patch


# ─── A2.1 — each strategy exposes run_generate ──────────────────────────────


def test_run_generate_callable_template():
    from src.generators.template_generator import run_generate

    result = run_generate(domain="wine_regions", count=0, dry_run=True)
    assert isinstance(result, dict)
    assert "generated" in result
    assert result["generated"] == 0


def test_run_generate_callable_fact_to_question():
    from src.generators.fact_to_question import run_generate

    result = run_generate(
        domain="wine_regions", count=0, generator="claude",
        question_type="multiple_choice", difficulty="2",
        cognitive_dim="recall", dry_run=True,
    )
    assert isinstance(result, dict)
    assert result["generated"] == 0


def test_run_generate_callable_comparative():
    from src.generators.comparative_generator import run_generate

    result = run_generate(
        domain="wine_regions", count=0, generator="claude",
        comparison_type="auto", dry_run=True,
    )
    assert isinstance(result, dict)
    assert result["generated"] == 0


def test_run_generate_callable_scenario():
    from src.generators.scenario_generator import run_generate

    result = run_generate(
        domain="wine_regions", count=0, generator="claude",
        scenario_type="winemaking", dry_run=True,
    )
    assert isinstance(result, dict)
    assert result["generated"] == 0


def test_run_generate_callable_distractor():
    from src.generators.distractor_miner import run_generate

    result = run_generate(
        domain="wine_regions", count=0, generator="claude", dry_run=True,
    )
    assert isinstance(result, dict)
    assert result["generated"] == 0


# ─── A2.2 — _corpus._run_generator routes in-process by default ─────────────


def test_run_generator_in_process_calls_run_generate(monkeypatch):
    """Default path: import the strategy module and call run_generate(...)."""
    from src.qa import _corpus
    from src.generators import template_generator

    captured: dict = {}

    def fake_run_generate(**kwargs):
        captured.update(kwargs)
        return {"generated": kwargs["count"], "relabeled_l1": 0, "rejected_overflow": 0}

    monkeypatch.setattr(template_generator, "run_generate", fake_run_generate)
    monkeypatch.delenv("OENOBENCH_USE_SUBPROCESS_DISPATCH", raising=False)

    # Ensure we don't accidentally call subprocess.run
    def explode(*_a, **_kw):
        raise AssertionError(
            "subprocess.run must not be called when OENOBENCH_USE_SUBPROCESS_DISPATCH is unset"
        )

    monkeypatch.setattr("src.qa._corpus.subprocess.run", explode)

    ok = _corpus._run_generator(
        module="template_generator", domain="wine_regions", count=2,
    )
    assert ok is True
    assert captured["domain"] == "wine_regions"
    assert captured["count"] == 2
    assert captured["per_country_cap"] is None


def test_run_generator_in_process_forwards_per_country_cap(monkeypatch):
    """per_country_cap propagates as a kwarg, not as argv."""
    from src.qa import _corpus
    from src.generators import fact_to_question

    captured: dict = {}

    def fake_run_generate(**kwargs):
        captured.update(kwargs)
        return {"generated": 0}

    monkeypatch.setattr(fact_to_question, "run_generate", fake_run_generate)
    monkeypatch.delenv("OENOBENCH_USE_SUBPROCESS_DISPATCH", raising=False)

    ok = _corpus._run_generator(
        module="fact_to_question", domain="wine_regions", count=4,
        generator="claude", difficulty=3, per_country_cap=0.20,
    )
    assert ok is True
    assert captured["domain"] == "wine_regions"
    assert captured["count"] == 4
    assert captured["generator"] == "claude"
    assert captured["difficulty"] == "3"
    assert captured["per_country_cap"] == 0.20


def test_run_generator_in_process_handles_strategy_exception(monkeypatch):
    """If run_generate raises, _run_generator returns False (no propagation)."""
    from src.qa import _corpus
    from src.generators import scenario_generator

    def boom(**_kw):
        raise RuntimeError("simulated failure")

    monkeypatch.setattr(scenario_generator, "run_generate", boom)
    monkeypatch.delenv("OENOBENCH_USE_SUBPROCESS_DISPATCH", raising=False)

    ok = _corpus._run_generator(
        module="scenario_generator", domain="winemaking", count=2,
    )
    assert ok is False


# ─── A2.3 — subprocess fallback under env var ───────────────────────────────


def test_run_generator_falls_back_to_subprocess_under_env_var(monkeypatch):
    """OENOBENCH_USE_SUBPROCESS_DISPATCH=1 flips the dispatcher back to the
    legacy subprocess.run path with the expected argv."""
    from src.qa import _corpus

    monkeypatch.setenv("OENOBENCH_USE_SUBPROCESS_DISPATCH", "1")
    with patch("src.qa._corpus.subprocess.run") as fake_run:
        fake_run.return_value.returncode = 0
        ok = _corpus._run_generator(
            module="template_generator", domain="wine_regions", count=2,
        )
    assert ok is True
    args = fake_run.call_args[0][0]
    # argv shape preserved — same as Phase 2g.8 wire-up.
    assert any("template_generator" in a for a in args)
    assert "--domain" in args and "--count" in args


def test_run_generator_subprocess_path_returns_false_on_failure(monkeypatch):
    """When the subprocess returns non-zero, _run_generator returns False."""
    from src.qa import _corpus

    monkeypatch.setenv("OENOBENCH_USE_SUBPROCESS_DISPATCH", "1")
    with patch("src.qa._corpus.subprocess.run") as fake_run:
        fake_run.return_value.returncode = 1
        ok = _corpus._run_generator(
            module="template_generator", domain="wine_regions", count=2,
        )
    assert ok is False


# ─── A2.4 — click main() shim still works ───────────────────────────────────


def test_main_shim_invokes_run_generate(monkeypatch):
    """The click main() must delegate to run_generate(...) with the parsed
    flag values."""
    from click.testing import CliRunner
    from src.generators import fact_to_question

    captured: dict = {}

    def fake_run_generate(**kwargs):
        captured.update(kwargs)
        return {"generated": 0, "skipped_parse": 0, "skipped_dup": 0,
                "skipped_sample": 0, "relabeled_l1": 0, "rejected_overflow": 0,
                "inserted_uuids": []}

    monkeypatch.setattr(fact_to_question, "run_generate", fake_run_generate)

    runner = CliRunner()
    result = runner.invoke(
        fact_to_question.main,
        ["--domain", "wine_regions", "--count", "5", "--dry-run"],
    )
    assert result.exit_code == 0, result.output
    assert captured["domain"] == "wine_regions"
    assert captured["count"] == 5
    assert captured["dry_run"] is True
