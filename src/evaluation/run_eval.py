"""Phase 5 evaluation harness — parallel fan-out across 16 model configurations.

Mirrors the ThreadPoolExecutor + env-var-driven-concurrency pattern from
src/qa/_corpus.py.  Reads questions from sample.questions (default) or
public.questions.  Writes to public.evaluation_runs and public.evaluation_answers.

Env vars (all have sensible defaults):
  OENOBENCH_EVAL_CONFIG_WORKERS   outer thread count (default 16)
  OENOBENCH_EVAL_PER_CONFIG_WORKERS  inner concurrency override (default: per-config)
  OENOBENCH_LLM_THROTTLE_MS       set to "0" here for eval (inference-bound)
"""
from __future__ import annotations

import concurrent.futures as cf
import json
import os
import sys
import threading
import time
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

import click
from loguru import logger

from src.evaluation._corpus_loader import EvalQuestion, load_questions
from src.utils.db import get_pg

if TYPE_CHECKING:
    # Team B will provide these; imported lazily at runtime so tests can
    # monkeypatch them before the real modules land.
    from src.evaluation._eval_client import EvalResult, evaluate_one
    from src.evaluation.configs import EVAL_CONFIGS, EvalConfig
    from src.utils.cost import compute_cost

# ─── Env-var constants ────────────────────────────────────────────────────────

_CONFIG_WORKERS_ENV = "OENOBENCH_EVAL_CONFIG_WORKERS"
_PER_CONFIG_WORKERS_ENV = "OENOBENCH_EVAL_PER_CONFIG_WORKERS"
_DEFAULT_CONFIG_WORKERS = 16

# Max-skipped guardrail: if parse failures exceed this fraction in the first
# GUARDRAIL_MIN_QUESTIONS questions of a config, abort that config.
_GUARDRAIL_THRESHOLD = 0.02   # 2%
_GUARDRAIL_MIN_QUESTIONS = 200

# Stricter retry system prompt when first parse attempt returns None.
_RETRY_SYSTEM_PROMPT = (
    "You MUST reply with exactly one letter A, B, C, or D and nothing else."
)

# ─── Logging setup ────────────────────────────────────────────────────────────


def _setup_logging(tag: str) -> None:
    Path("data/logs").mkdir(parents=True, exist_ok=True)
    ts = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
    log_path = f"data/logs/eval_{tag}_{ts}.log"
    logger.remove()
    logger.add(sys.stderr, level="INFO", colorize=True)
    logger.add(log_path, level="DEBUG", rotation="100 MB")
    logger.info("Eval harness logging to {}", log_path)


# ─── DB helpers ───────────────────────────────────────────────────────────────


def _create_run(
    *,
    tag: str,
    corpus: str,
    configs: list,          # list[EvalConfig]
    dry_run: bool,
) -> str:
    """Insert an evaluation_runs row and return the run UUID string."""
    run_id = str(uuid.uuid4())
    if dry_run:
        logger.info("[dry-run] Would create evaluation_runs row id={} tag={}", run_id, tag)
        return run_id

    config_slots = [c.slot for c in configs]
    metadata = {"tag": tag, "corpus": corpus, "configs": config_slots}
    conn = get_pg()
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO evaluation_runs
                (id, model_name, prompt_strategy, temperature, started_at, metadata)
            VALUES
                (%s, %s, %s, %s, %s, %s)
            """,
            (
                run_id,
                f"multi_config/{len(configs)}",
                "single_letter",
                0.0,
                datetime.now(tz=timezone.utc),
                json.dumps(metadata),
            ),
        )
    conn.commit()
    logger.info("Created evaluation_runs row id={} tag={}", run_id, tag)
    return run_id


def _find_existing_run(tag: str) -> str | None:
    """Return the run_id for an existing in-progress run with this tag, or None."""
    conn = get_pg()
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id::text
            FROM evaluation_runs
            WHERE metadata->>'tag' = %s
              AND completed_at IS NULL
            ORDER BY started_at DESC
            LIMIT 1
            """,
            (tag,),
        )
        row = cur.fetchone()
    return row["id"] if row else None


def _fetch_completed_question_ids(run_id: str, model_name: str, reasoning_config_str: str | None) -> set[str]:
    """Return set of question_id strings already answered for this run+config."""
    conn = get_pg()
    coalesce_val = reasoning_config_str if reasoning_config_str is not None else ""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT question_id::text
            FROM evaluation_answers
            WHERE run_id = %s
              AND model_name = %s
              AND COALESCE(reasoning_config::text, '') = %s
            """,
            (run_id, model_name, coalesce_val),
        )
        rows = cur.fetchall()
    return {r["question_id"] for r in rows}


def _insert_answer(
    *,
    run_id: str,
    question_id: str,
    model_name: str,
    parsed_answer: str | None,
    is_correct: bool | None,
    provider_used: str | None,
    generation_id: str | None,
    input_tokens: int,
    output_tokens: int,
    reasoning_tokens: int,
    cost_usd: float,
    latency_ms: int,
    raw_response: str,
    reasoning_config: dict | None,
    dry_run: bool,
) -> None:
    if dry_run:
        return

    rc_json = json.dumps(reasoning_config) if reasoning_config else None
    conn = get_pg()
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO evaluation_answers (
                run_id, question_id, model_name,
                parsed_answer, model_answer, is_correct,
                provider_used, generation_id,
                input_tokens, output_tokens, reasoning_tokens,
                cost_usd, latency_ms, response_time_ms,
                raw_response, reasoning_config
            ) VALUES (
                %s, %s, %s,
                %s, %s, %s,
                %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                %s, %s::jsonb
            )
            ON CONFLICT (run_id, question_id, model_name,
                         COALESCE(reasoning_config::text, ''))
            DO NOTHING
            """,
            (
                run_id, question_id, model_name,
                parsed_answer, parsed_answer, is_correct,
                provider_used, generation_id,
                input_tokens, output_tokens, reasoning_tokens,
                cost_usd, latency_ms, latency_ms,
                raw_response, rc_json,
            ),
        )
    conn.commit()


def _finalize_run(run_id: str, dry_run: bool) -> None:
    """Update evaluation_runs with completion stats."""
    if dry_run:
        logger.info("[dry-run] Would finalize run {}", run_id)
        return

    conn = get_pg()
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE evaluation_runs
            SET
                completed_at    = %s,
                total_questions = sub.total_q,
                correct_count   = sub.correct_q,
                accuracy        = CASE WHEN sub.total_q > 0
                                       THEN sub.correct_q::real / sub.total_q
                                       ELSE NULL END,
                total_cost_usd  = sub.total_cost
            FROM (
                SELECT
                    COUNT(*)                         AS total_q,
                    COUNT(*) FILTER (WHERE is_correct) AS correct_q,
                    COALESCE(SUM(cost_usd), 0)       AS total_cost
                FROM evaluation_answers
                WHERE run_id = %s
            ) sub
            WHERE id = %s
            """,
            (datetime.now(tz=timezone.utc), run_id, run_id),
        )
    conn.commit()


# ─── Worker helpers ───────────────────────────────────────────────────────────


def _resolve_config_workers() -> int:
    raw = os.environ.get(_CONFIG_WORKERS_ENV, "").strip()
    try:
        n = int(raw)
        if n > 0:
            return n
    except ValueError:
        pass
    return _DEFAULT_CONFIG_WORKERS


def _resolve_per_config_workers(config_concurrency: int) -> int:
    raw = os.environ.get(_PER_CONFIG_WORKERS_ENV, "").strip()
    try:
        n = int(raw)
        if n > 0:
            return n
    except ValueError:
        pass
    return config_concurrency


def _reasoning_config_dict(config) -> dict | None:
    """Extract the reasoning sub-dict from an EvalConfig, or None."""
    if not hasattr(config, "reasoning_mode") or config.reasoning_mode is None:
        return None
    if config.reasoning_mode == "explicit_budget":
        return {"max_tokens": config.reasoning_budget}
    if config.reasoning_mode == "effort":
        return {"effort": config.reasoning_effort}
    return None


def _reasoning_config_str(config) -> str | None:
    """Canonical string for the unique constraint coalesce."""
    d = _reasoning_config_dict(config)
    if d is None:
        return None
    return json.dumps(d, sort_keys=True)


# ─── Per-config evaluation ────────────────────────────────────────────────────


def _evaluate_config(
    *,
    config,                          # EvalConfig
    questions: list[EvalQuestion],
    run_id: str,
    dry_run: bool,
    evaluate_one_fn,                 # callable — injectable for tests
    compute_cost_fn,                 # callable — injectable for tests
) -> dict:
    """Fan out questions for one EvalConfig; returns per-config stats dict."""
    from src.generators._llm_client import LLMClient

    model_name = config.model_id
    rc_dict = _reasoning_config_dict(config)
    rc_str = _reasoning_config_str(config)

    # Resume: skip already-answered questions.
    completed_ids: set[str] = set()
    if not dry_run:
        try:
            completed_ids = _fetch_completed_question_ids(run_id, model_name, rc_str)
        except Exception as exc:
            logger.warning("config slot={} failed to fetch completed IDs: {}", config.slot, exc)

    pending = [q for q in questions if q.id not in completed_ids]
    if not pending:
        logger.info("config slot={} name={} fully resumed — nothing to do", config.slot, config.name)
        return {"slot": config.slot, "name": config.name, "total": 0, "skipped": 0, "correct": 0, "aborted": False}

    logger.info(
        "config slot={} name={} | questions={} completed={} pending={}",
        config.slot, config.name, len(questions), len(completed_ids), len(pending),
    )

    # Stats tracking — thread-safe via a lock.
    stats_lock = threading.Lock()
    stats = {"total": 0, "skipped": 0, "correct": 0, "aborted": False, "cost": 0.0}

    # Create LLM client once per config.
    if dry_run:
        client = None
    else:
        try:
            client = LLMClient()
        except Exception as exc:
            logger.error("config slot={} cannot create LLMClient: {}", config.slot, exc)
            return {"slot": config.slot, "name": config.name, "total": 0, "skipped": 0,
                    "correct": 0, "aborted": True, "error": str(exc)}

    workers = _resolve_per_config_workers(config.concurrency)
    abort_event = threading.Event()

    def _process_one(q: EvalQuestion) -> None:
        if abort_event.is_set():
            return

        if dry_run:
            logger.debug("[dry-run] Would call evaluate_one for q={} config={}", q.id, config.slot)
            with stats_lock:
                stats["total"] += 1
            return

        # First attempt.
        result = None
        try:
            result = evaluate_one_fn(client, config, q.question_text, q.options)
        except Exception as exc:
            logger.warning("config slot={} q={} evaluate_one raised: {}", config.slot, q.id, exc)

        parsed = result.parsed_answer if result is not None else None
        raw_text = result.raw_text if result is not None else ""
        response = result.response if result is not None else None

        # Single retry on parse failure with stricter system prompt.
        if parsed is None and result is not None:
            try:
                result2 = evaluate_one_fn(
                    client, config, q.question_text, q.options,
                    override_system=_RETRY_SYSTEM_PROMPT,
                )
                if result2.parsed_answer is not None:
                    result = result2
                    parsed = result2.parsed_answer
                    raw_text = result2.raw_text
                    response = result2.response
            except Exception as exc:
                logger.debug("config slot={} q={} retry raised: {}", config.slot, q.id, exc)

        # Extract telemetry.
        input_tokens = 0
        output_tokens = 0
        reasoning_toks = 0
        latency_ms = 0
        provider_used = "unknown"
        generation_id = None

        if response is not None:
            input_tokens = getattr(response, "input_tokens", 0) or 0
            output_tokens = getattr(response, "output_tokens", 0) or 0
            reasoning_toks = getattr(response, "reasoning_tokens", 0) or 0
            latency_ms = getattr(response, "latency_ms", 0) or 0
            provider_used = getattr(response, "provider", None) or "unknown"
            generation_id = getattr(response, "generation_id", None)

        cost = 0.0
        try:
            cost = compute_cost_fn(model_name, input_tokens, output_tokens, reasoning_toks)
        except Exception:
            pass

        is_correct = (parsed == q.correct_answer) if parsed is not None else None

        try:
            _insert_answer(
                run_id=run_id,
                question_id=q.id,
                model_name=model_name,
                parsed_answer=parsed,
                is_correct=is_correct,
                provider_used=provider_used,
                generation_id=generation_id,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                reasoning_tokens=reasoning_toks,
                cost_usd=cost,
                latency_ms=latency_ms,
                raw_response=raw_text,
                reasoning_config=rc_dict,
                dry_run=False,
            )
        except Exception as exc:
            logger.warning("config slot={} q={} DB write failed: {}", config.slot, q.id, exc)

        with stats_lock:
            stats["total"] += 1
            stats["cost"] += cost
            if parsed is None:
                stats["skipped"] += 1
            elif is_correct:
                stats["correct"] += 1

            # Guardrail check: abort config if skip rate > 2% over first 200 Qs.
            t = stats["total"]
            s = stats["skipped"]
            if t >= _GUARDRAIL_MIN_QUESTIONS and not abort_event.is_set():
                skip_rate = s / t
                if skip_rate > _GUARDRAIL_THRESHOLD:
                    logger.warning(
                        "config slot={} name={} GUARDRAIL TRIGGERED: "
                        "skip_rate={:.1%} ({}/{}) > {:.0%} — aborting this config",
                        config.slot, config.name, skip_rate, s, t, _GUARDRAIL_THRESHOLD,
                    )
                    abort_event.set()
                    stats["aborted"] = True

    # Inner thread pool.
    with cf.ThreadPoolExecutor(max_workers=workers) as inner:
        futures = {inner.submit(_process_one, q): q for q in pending}
        for fut in cf.as_completed(futures):
            try:
                fut.result()
            except Exception as exc:
                q = futures[fut]
                logger.error("config slot={} q={} future raised: {}", config.slot, q.id, exc)

    accuracy = (stats["correct"] / stats["total"]) if stats["total"] > 0 else None
    logger.info(
        "config slot={} name={} | done total={} skipped={} correct={} "
        "accuracy={:.1%} cost=${:.4f} aborted={}",
        config.slot, config.name, stats["total"], stats["skipped"], stats["correct"],
        accuracy if accuracy is not None else 0.0,
        stats["cost"], stats["aborted"],
    )
    return {
        "slot": config.slot,
        "name": config.name,
        "total": stats["total"],
        "skipped": stats["skipped"],
        "correct": stats["correct"],
        "cost": stats["cost"],
        "aborted": stats["aborted"],
    }


# ─── CLI ──────────────────────────────────────────────────────────────────────


@click.command()
@click.option("--tag", required=True, help="Identifier stored in metadata.tag.")
@click.option(
    "--corpus",
    type=click.Choice(["sample", "public"]),
    default="sample",
    show_default=True,
    help="Which questions schema to read from.",
)
@click.option(
    "--max-questions",
    type=int,
    default=None,
    help="Cap the number of questions (useful for debugging).",
)
@click.option(
    "--configs",
    "configs_str",
    default=None,
    help="Comma-separated slot ints, e.g. '1,2,3'. Default: all 16.",
)
@click.option(
    "--resume",
    is_flag=True,
    default=False,
    help="Resume an in-progress run that matches --tag.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Print the plan without making API calls or DB writes.",
)
def main(
    tag: str,
    corpus: str,
    max_questions: int | None,
    configs_str: str | None,
    resume: bool,
    dry_run: bool,
) -> None:
    """Phase 5 evaluation harness."""
    _setup_logging(tag)

    # Force throttle off for eval (inference-bound, not request-rate-bound).
    os.environ.setdefault("OENOBENCH_LLM_THROTTLE_MS", "0")

    # Lazy-import Team B's modules so tests can monkeypatch before import.
    try:
        from src.evaluation.configs import EVAL_CONFIGS
        from src.evaluation._eval_client import evaluate_one as _evaluate_one
        from src.utils.cost import compute_cost as _compute_cost
    except ImportError as exc:
        if dry_run:
            logger.warning(
                "Team B/A modules not yet on main (expected during dev): {}. "
                "Dry-run will use stubs.",
                exc,
            )
            EVAL_CONFIGS = []  # type: ignore[assignment]

            def _evaluate_one(*a, **kw):  # type: ignore[misc]
                raise NotImplementedError("evaluate_one stub")

            def _compute_cost(*a, **kw) -> float:  # type: ignore[misc]
                return 0.0
        else:
            logger.error("Cannot import required modules: {}", exc)
            raise SystemExit(1) from exc

    # Resolve which configs to run.
    if configs_str:
        slots = {int(s.strip()) for s in configs_str.split(",") if s.strip()}
        selected_configs = [c for c in EVAL_CONFIGS if c.slot in slots]
        if not selected_configs:
            logger.error("No configs matched slots: {}", slots)
            raise SystemExit(1)
    else:
        selected_configs = list(EVAL_CONFIGS)

    # Load questions.
    questions = load_questions(corpus=corpus, limit=max_questions)
    logger.info("Loaded {} questions from {}.questions", len(questions), corpus)

    if dry_run:
        click.echo(f"\n=== DRY RUN PLAN ===")
        click.echo(f"Tag:      {tag}")
        click.echo(f"Corpus:   {corpus}")
        click.echo(f"Questions:{len(questions)}")
        click.echo(f"Configs:  {len(selected_configs)} slots")
        for c in selected_configs:
            rc = _reasoning_config_dict(c) if hasattr(c, "reasoning_mode") else None
            click.echo(
                f"  slot={c.slot:>2} {c.name:<40} concurrency={c.concurrency}"
                f" reasoning={rc}"
            )
        total_calls = len(questions) * len(selected_configs)
        click.echo(f"Total API calls (est.): {total_calls:,}")
        click.echo("=== END DRY RUN — no DB writes, no API calls ===\n")
        return

    # Resume or fresh run.
    run_id: str
    if resume:
        existing = _find_existing_run(tag)
        if existing is None:
            logger.error("--resume requested but no in-progress run found for tag={}", tag)
            raise SystemExit(1)
        run_id = existing
        logger.info("Resuming run_id={} tag={}", run_id, tag)
    else:
        existing = _find_existing_run(tag)
        if existing is not None:
            logger.error(
                "Run with tag={} already exists (id={}). Use --resume to continue it.",
                tag, existing,
            )
            raise SystemExit(1)
        run_id = _create_run(tag=tag, corpus=corpus, configs=selected_configs, dry_run=False)

    # Outer fan-out: one thread per config.
    config_workers = _resolve_config_workers()
    logger.info(
        "Starting outer fan-out: {} configs × {} questions (config_workers={})",
        len(selected_configs), len(questions), config_workers,
    )
    t_start = time.monotonic()

    all_stats: list[dict] = []

    with cf.ThreadPoolExecutor(max_workers=config_workers) as outer:
        future_to_config = {
            outer.submit(
                _evaluate_config,
                config=c,
                questions=questions,
                run_id=run_id,
                dry_run=False,
                evaluate_one_fn=_evaluate_one,
                compute_cost_fn=_compute_cost,
            ): c
            for c in selected_configs
        }
        for fut in cf.as_completed(future_to_config):
            c = future_to_config[fut]
            try:
                result = fut.result()
                all_stats.append(result)
            except Exception as exc:
                logger.error("config slot={} raised at top level: {}", c.slot, exc)
                all_stats.append({"slot": c.slot, "name": c.name, "total": 0, "skipped": 0,
                                   "correct": 0, "cost": 0.0, "aborted": True, "error": str(exc)})

    wall_s = time.monotonic() - t_start

    # Finalize the run record.
    _finalize_run(run_id, dry_run=False)

    # Summary.
    total_q = sum(s["total"] for s in all_stats)
    total_correct = sum(s["correct"] for s in all_stats)
    total_cost = sum(s.get("cost", 0.0) for s in all_stats)
    aborted = [s["name"] for s in all_stats if s.get("aborted")]

    logger.info(
        "=== EVAL COMPLETE === run_id={} tag={} wall={:.1f}s "
        "total_answers={} correct={} accuracy={:.1%} cost=${:.2f}",
        run_id, tag, wall_s,
        total_q, total_correct,
        total_correct / total_q if total_q else 0.0,
        total_cost,
    )
    if aborted:
        logger.warning("Aborted configs (guardrail or error): {}", aborted)

    click.echo(f"\nRun complete. run_id={run_id}  tag={tag}")
    click.echo(f"Wall time: {wall_s:.1f}s   Total answers: {total_q}   Cost: ${total_cost:.2f}")
    if aborted:
        click.echo(f"WARNING: {len(aborted)} config(s) aborted: {aborted}")
    click.echo(f"\nRender report with: python -m src.evaluation.report --tag {tag}")


if __name__ == "__main__":
    main()
