"""Phase 2g.10 (Team Delta) — A2 in-process dispatch + A3 concurrent cells.

A2 covers:

- Each strategy module exposes a stable ``run_generate(...)`` callable.
- ``_corpus._run_generator`` and ``orchestrator._run_strategy`` route through
  ``run_generate(...)`` in-process by default.
- Setting ``OENOBENCH_USE_SUBPROCESS_DISPATCH=1`` flips back to the legacy
  ``subprocess.run`` path (defence-in-depth roll-back hatch).
- The click ``main()`` shims still parse CLI args correctly.

A3 covers:

- ``--max-workers`` / ``OENOBENCH_MAX_WORKERS`` resolution.
- Default ``max_workers=1`` runs cells serially (no overlap).
- ``max_workers >= 2`` runs cells concurrently (overlap observed).
- Module-level ``threading.Lock`` in ``_question_db`` serialises the
  count-then-insert pair in ``insert_question_gated``.
- Concurrent ``insert_question_gated`` calls with the lock cannot exceed the
  closed-book quota cap.
"""

from __future__ import annotations

import threading
import time
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


# ─── A3.1 — max_workers env var resolution ──────────────────────────────────


def test_max_workers_env_var_is_picked_up(monkeypatch):
    from src.qa import _corpus

    monkeypatch.setenv("OENOBENCH_MAX_WORKERS", "4")
    assert _corpus._resolve_max_workers(None) == 4


def test_max_workers_explicit_arg_overrides_env(monkeypatch):
    from src.qa import _corpus

    monkeypatch.setenv("OENOBENCH_MAX_WORKERS", "4")
    assert _corpus._resolve_max_workers(8) == 8


def test_max_workers_defaults_to_one(monkeypatch):
    from src.qa import _corpus

    monkeypatch.delenv("OENOBENCH_MAX_WORKERS", raising=False)
    assert _corpus._resolve_max_workers(None) == 1


def test_max_workers_invalid_env_falls_back_to_one(monkeypatch):
    from src.qa import _corpus

    monkeypatch.setenv("OENOBENCH_MAX_WORKERS", "not_an_int")
    assert _corpus._resolve_max_workers(None) == 1


# ─── A3.2 — serial vs concurrent wallclock ──────────────────────────────────


def _patch_corpus_db_helpers(monkeypatch):
    """Stub DB calls so build_pilot_corpus runs without hitting Postgres."""
    from datetime import datetime
    from src.qa import _corpus as _c

    monkeypatch.setattr(_c, "_existing_corpus_count", lambda tag: {})
    monkeypatch.setattr(
        _c, "_tag_rows",
        lambda *, generation_method, since, limit, tag: limit,
    )
    monkeypatch.setattr(
        _c, "_resolve_build_started_at",
        lambda tag: (datetime.now(), False),
    )


def test_threadpool_max_workers_one_runs_serially(monkeypatch):
    """With max_workers=1, calls run sequentially — no overlap."""
    from src.qa import _corpus
    from src.qa._corpus import build_pilot_corpus

    _patch_corpus_db_helpers(monkeypatch)

    in_flight = []
    max_overlap = {"n": 0}
    lock = threading.Lock()

    def slow(**kw):
        with lock:
            in_flight.append(1)
            max_overlap["n"] = max(max_overlap["n"], len(in_flight))
        time.sleep(0.05)
        with lock:
            in_flight.pop()
        return True

    monkeypatch.setattr(_corpus, "_run_generator", slow)

    build_pilot_corpus(
        tag="test_serial", per_strategy=2, seed=1, max_workers=1,
    )
    assert max_overlap["n"] == 1, (
        f"max_workers=1 must serialise dispatch, observed overlap={max_overlap['n']}"
    )


def test_threadpool_max_workers_n_runs_concurrently(monkeypatch):
    """With max_workers >= 2, multiple cells overlap in time."""
    from src.qa import _corpus
    from src.qa._corpus import build_pilot_corpus

    _patch_corpus_db_helpers(monkeypatch)

    in_flight = []
    max_overlap = {"n": 0}
    lock = threading.Lock()

    def slow(**kw):
        with lock:
            in_flight.append(1)
            max_overlap["n"] = max(max_overlap["n"], len(in_flight))
        time.sleep(0.1)
        with lock:
            in_flight.pop()
        return True

    monkeypatch.setattr(_corpus, "_run_generator", slow)

    build_pilot_corpus(
        tag="test_concurrent", per_strategy=4, seed=1, max_workers=4,
    )
    assert max_overlap["n"] >= 2, (
        f"max_workers=4 must overlap dispatches, observed peak={max_overlap['n']}"
    )


def test_build_pilot_corpus_propagates_max_workers_arg(monkeypatch):
    """The build_pilot_corpus(max_workers=...) kwarg must reach the executor."""
    from src.qa import _corpus
    from src.qa._corpus import build_pilot_corpus

    _patch_corpus_db_helpers(monkeypatch)
    monkeypatch.setattr(
        _corpus, "_run_generator",
        lambda *, module, domain, count, generator=None,
               difficulty=None, per_country_cap=None: True,
    )

    captured = {}
    real_executor = _corpus.cf.ThreadPoolExecutor

    class CapturingExecutor(real_executor):
        def __init__(self, max_workers=None, **kw):
            captured["max_workers"] = max_workers
            super().__init__(max_workers=max_workers, **kw)

    monkeypatch.setattr(_corpus.cf, "ThreadPoolExecutor", CapturingExecutor)

    build_pilot_corpus(
        tag="test_workers_arg", per_strategy=2, seed=1, max_workers=3,
    )
    assert captured.get("max_workers") == 3


# ─── A3.3 — threading lock contract on insert_question_gated ────────────────


def test_quota_lock_module_global_exists():
    """The lock must live at module scope so concurrent threads share it."""
    from src.generators import _question_db

    assert hasattr(_question_db, "_QUOTA_LOCK")
    # It quacks like a threading lock (acquire/release/locked).
    assert callable(_question_db._QUOTA_LOCK.acquire)
    assert callable(_question_db._QUOTA_LOCK.release)
    assert callable(_question_db._QUOTA_LOCK.locked)


def test_quota_lock_is_held_during_count_then_insert(monkeypatch):
    """The count → cap-check → insert sequence runs under the lock."""
    from src.generators import _question_db
    from src.generators._closed_book_gate import GateResult

    held_during_count: list[bool] = []
    held_during_insert: list[bool] = []

    def fake_count(*_a, **_kw):
        held_during_count.append(_question_db._QUOTA_LOCK.locked())
        return 0

    def fake_insert(*_a, **_kw):
        held_during_insert.append(_question_db._QUOTA_LOCK.locked())
        return "uuid-locked"

    monkeypatch.setattr(_question_db, "count_closed_book_solvable", fake_count)
    monkeypatch.setattr(_question_db, "insert_question", fake_insert)

    pre_gate = GateResult(
        passed=False, applied=True,
        reason="reject (closed-book solvable)",
        selected="A", confidence=0.9, matched_gold=True,
    )
    qd = {
        "question_id": "T-LOCK-001",
        "question_text": "Q?",
        "options": [{"id": "A", "text": "x"}],
        "correct_answer": "A",
        "difficulty": "1",
        "question_type": "multiple_choice",
        "domain": "wine_regions",
    }
    _question_db.insert_question_gated(
        question_data=qd,
        generation_meta={"generator": "g", "generation_method": "template"},
        fact_ids=[], source_ids=[],
        pre_screened=pre_gate,
    )
    assert held_during_count == [True]
    assert held_during_insert == [True]


def test_concurrent_inserts_respect_quota_cap(monkeypatch):
    """N threads racing on insert_question_gated: at most `cap` relabeled
    (non-reserve) inserts; the rest must be reserved (status='cb_reserve').
    Phase 2g.15: quota-full questions are reserved, not dropped, so total
    inserts = 20 but active-cap inserts = cap.
    """
    from src.generators import _question_db
    from src.generators._closed_book_gate import GateResult

    cap = 5
    # Track relabeled (draft) inserts separately from cb_reserve inserts.
    active_counter = {"n": 0}
    counter_lock = threading.Lock()

    def fake_count(*_a, **_kw):
        with counter_lock:
            return active_counter["n"]

    def fake_insert(*_a, status="draft", **_kw):
        # Tiny pause to widen the race window without the lock.
        time.sleep(0.001)
        with counter_lock:
            if status != "cb_reserve":
                active_counter["n"] += 1
        return f"uuid-{active_counter['n']}"

    monkeypatch.setattr(_question_db, "count_closed_book_solvable", fake_count)
    monkeypatch.setattr(_question_db, "insert_question", fake_insert)
    monkeypatch.setattr(_question_db, "_closed_book_quota_cap", lambda *a, **kw: cap)
    # Disable per-strategy budget so we exercise the corpus-level cap path.
    monkeypatch.setattr(_question_db, "_resolve_strategy_target_size", lambda: None)

    def worker():
        pre = GateResult(
            passed=False, applied=True, reason="r",
            selected="A", confidence=0.9, matched_gold=True,
        )
        qd = {
            "question_id": "X",
            "question_text": "Q?",
            "options": [{"id": "A", "text": "x"}],
            "correct_answer": "A",
            "difficulty": "1",
            "question_type": "multiple_choice",
            "domain": "wine_regions",
            "tags": [],
        }
        _question_db.insert_question_gated(
            question_data=qd,
            generation_meta={"generator": "g", "generation_method": "template"},
            fact_ids=[], source_ids=[],
            pre_screened=pre,
        )

    threads = [threading.Thread(target=worker) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert active_counter["n"] <= cap, (
        f"concurrent relabeled inserts blew the cap: {active_counter['n']}/{cap}"
    )
