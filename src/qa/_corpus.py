"""Stratified pilot-corpus builder for the audit.

Wraps the five existing generator CLIs without modifying them. Questions
generated through this module are tagged `audit_pilot_v1` so every downstream
agent can filter the corpus by tag.

Design notes:
- We call each strategy with a bounded `--count` per domain. The strategy
  itself picks difficulty/cognitive dim/question type from its own logic.
- After each call, we tag the newly-created rows for that `generation_method`
  so stage 2 agents know which corpus to read.
- `gold_sheet` export produces a CSV the reviewer fills offline; `import`
  writes it back into `audit_gold_labels`.
"""

from __future__ import annotations

import concurrent.futures as cf
import csv
import importlib
import os
import random
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Iterable

import click
from loguru import logger

from src.generators._question_db import (
    CORPUS_BUILD_SINCE_ENV_VAR,
    CORPUS_TARGET_ENV_VAR,
    STRATEGY_TARGET_ENV_VAR,
    set_corpus_target,
)
from src.qa._attempted_facts import (
    get_attempted_fact_ids,
    register_attempted_fact_ids,
    reset_attempted_fact_ids,
)
from src.qa._findings import upsert_gold_label
from src.utils.db import get_pg

# Phase 2g.10 (Team Delta A2): toggle subprocess fallback. Default is
# in-process dispatch (~2-3s/cell saved over the legacy subprocess.run path).
# Set OENOBENCH_USE_SUBPROCESS_DISPATCH=1 to revert to the subprocess path
# without a code change (defence-in-depth for v9 audit roll-back).
USE_SUBPROCESS_ENV_VAR = "OENOBENCH_USE_SUBPROCESS_DISPATCH"

# Phase 2g.10 (Team Delta A3): worker count for the (generator × domain) cell
# dispatch ThreadPoolExecutor. Default 1 = sequential (audit-pilot bit-for-bit
# reproducibility preserved). Override via --max-workers or OENOBENCH_MAX_WORKERS.
MAX_WORKERS_ENV_VAR = "OENOBENCH_MAX_WORKERS"

# Phase 2g.10 (Team Golf A4): worker count for the *top-level* strategy
# dispatch ThreadPoolExecutor. Default 1 = strategies run sequentially (audit
# pilots bit-for-bit reproducible). Override via --strategy-workers or
# OENOBENCH_STRATEGY_WORKERS env var.
STRATEGY_WORKERS_ENV_VAR = "OENOBENCH_STRATEGY_WORKERS"

# Phase 2g.10 (Team Golf B3): when set to "1", each strategy's per-cell loop
# maintains a CellTracker rolling window. Cells with sustained <5% kept-rate
# (after at least 10 attempts) are abandoned early and their unused budget
# is reallocated to the next cell in iteration order (capped at 2× original).
# Default OFF for v8-reproducibility. Per-strategy `--circuit-breaker` /
# `--no-circuit-breaker` flag also exposes the same toggle.
CIRCUIT_BREAKER_ENV_VAR = "OENOBENCH_CIRCUIT_BREAKER"

STRATEGY_MODULES = {
    "template": "template_generator",
    "fact_to_question": "fact_to_question",
    "comparative": "comparative_generator",
    "scenario_synthesis": "scenario_generator",
    "distractor_mining": "distractor_miner",
}

DOMAINS = [
    "wine_regions",
    "winemaking",
    "viticulture",
    "grape_varieties",
    "wine_business",
    "producers",
]

LLM_STRATEGIES = {"fact_to_question", "comparative", "scenario_synthesis", "distractor_mining"}

GENERATORS = ["claude", "chatgpt", "gemini", "llama", "qwen"]


def _count_strategy_rows_since(strategy: str, since: datetime) -> int:
    """Count actual questions produced by ``strategy`` since ``since``.

    Phase 2g.13 (Team C): used by the multi-pass loop in ``_run_one_strategy``
    to detect (a) success (actual >= want), (b) no-progress (this pass added
    zero rows → sampler ceiling reached), and (c) the final yield that the
    truth-tell log reports.
    """
    with get_pg().cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) AS n FROM questions q "
            "JOIN generation_metadata gm ON gm.question_id = q.id "
            "WHERE gm.generation_method = %s AND q.created_at >= %s",
            (strategy, since),
        )
        return cur.fetchone()["n"]


# Phase 2g.13 (Team C): multi-pass loop in ``_run_one_strategy``. Default 1
# preserves Phase 2g.12 behaviour exactly. Audit-pilot scripts can opt in by
# setting OENOBENCH_MAX_BUILD_PASSES=3 to retry under-budget strategies.
#
# Phase 2g.13 follow-up (2026-04-29): the cap was bumped from a hard 1 to a
# safety ceiling of 20 because the no-progress + wall-time + diminishing-
# returns exits make the loop self-terminating. Set to a high value
# (e.g. 10-15) and trust the early-exit logic to stop on real ceilings.
MAX_BUILD_PASSES_ENV_VAR = "OENOBENCH_MAX_BUILD_PASSES"
DEFAULT_MAX_BUILD_PASSES = 1
MAX_BUILD_PASSES_CEILING = 20

# Wall-time budget per strategy (seconds). 0 = no limit. Use this when
# `OENOBENCH_MAX_BUILD_PASSES` is set high — caps strategy walltime so a
# stuck-but-still-yielding strategy can't run unboundedly.
WALL_TIME_LIMIT_ENV_VAR = "OENOBENCH_BUILD_WALL_TIME_LIMIT_S"

# Diminishing-returns exit. If `produced / want < threshold` for
# CONSECUTIVE passes (>= MIN_YIELD_STREAK), stop. 0.0 = disabled. Set
# 0.05 for "stop when 2 passes in a row each produce <5% of remaining".
MIN_YIELD_PCT_ENV_VAR = "OENOBENCH_BUILD_MIN_YIELD_PCT"
MIN_YIELD_STREAK = 2


def _resolve_max_build_passes() -> int:
    """Resolve OENOBENCH_MAX_BUILD_PASSES with safe bounds.

    Returns a value in ``[1, MAX_BUILD_PASSES_CEILING]``. Default 1
    preserves Phase 2g.12 single-pass behaviour. Values above the
    ceiling are clamped down with a warning.
    """
    raw = os.environ.get(MAX_BUILD_PASSES_ENV_VAR, "").strip()
    if not raw:
        return DEFAULT_MAX_BUILD_PASSES
    try:
        n = int(raw)
    except ValueError:
        logger.warning(
            "{}={!r} is not an integer; falling back to {}",
            MAX_BUILD_PASSES_ENV_VAR, raw, DEFAULT_MAX_BUILD_PASSES,
        )
        return DEFAULT_MAX_BUILD_PASSES
    if n > MAX_BUILD_PASSES_CEILING:
        logger.warning(
            "{}={} exceeds ceiling {}; clamping",
            MAX_BUILD_PASSES_ENV_VAR, n, MAX_BUILD_PASSES_CEILING,
        )
        return MAX_BUILD_PASSES_CEILING
    return max(1, n)


def _resolve_wall_time_limit_s() -> float:
    """Resolve OENOBENCH_BUILD_WALL_TIME_LIMIT_S. 0 (default) = no limit."""
    raw = os.environ.get(WALL_TIME_LIMIT_ENV_VAR, "").strip()
    if not raw:
        return 0.0
    try:
        v = float(raw)
    except ValueError:
        logger.warning(
            "{}={!r} is not a number; falling back to 0 (no limit)",
            WALL_TIME_LIMIT_ENV_VAR, raw,
        )
        return 0.0
    return max(0.0, v)


def _resolve_min_yield_pct() -> float:
    """Resolve OENOBENCH_BUILD_MIN_YIELD_PCT. 0 (default) = disabled."""
    raw = os.environ.get(MIN_YIELD_PCT_ENV_VAR, "").strip()
    if not raw:
        return 0.0
    try:
        v = float(raw)
    except ValueError:
        logger.warning(
            "{}={!r} is not a number; falling back to 0 (disabled)",
            MIN_YIELD_PCT_ENV_VAR, raw,
        )
        return 0.0
    return max(0.0, v)


# Cross-pass attempted-fact-ID registry (Phase 2g.13) lives in
# ``src/qa/_attempted_facts.py`` to avoid potential import cycles with the
# strategy modules. Functions are re-exported above.


# ─── Cross-pass dead-cell registry (Phase 2g.15 Team C) ──────────────────────
#
# When a (model, domain) cell produced 0 questions in a pass it is very likely
# to fail again in the next pass (sampler pool exhausted, circuit-breaker
# budget spent). Tracking these "dead" cells and skipping them avoids wasting
# LLM budget on calls that are nearly certain to yield nothing.
#
# Pattern mirrors ``src/qa/_attempted_facts.py`` (Phase 2g.13).
#
# Thread safety: the registry is mutated only from ``_execute_strategy_passes``
# which serialises passes, so no lock is needed.

_dead_cells: dict[str, set[tuple[str, str]]] = {}


def register_dead_cell(strategy: str, model: str, domain: str) -> None:
    """Mark (model, domain) as a zero-yield cell for *strategy* this build."""
    _dead_cells.setdefault(strategy, set()).add((model, domain))


def get_dead_cells(strategy: str) -> set[tuple[str, str]]:
    """Return the current dead-cell set for *strategy* (may be empty)."""
    return _dead_cells.get(strategy, set())


def reset_dead_cells(strategy: str) -> None:
    """Clear the dead-cell registry for *strategy*.

    Called at the start of each ``_execute_strategy_passes`` run so stale
    state from a previous build in the same process doesn't carry over.
    """
    _dead_cells.pop(strategy, None)


def _count_strategy_rows_per_cell(
    strategy: str,
    since: datetime,
    count_rows_fn=None,
) -> dict[tuple[str, str], int]:
    """Return a mapping of (generator, domain) → question count for *strategy*.

    Used after each pass to identify zero-yield cells and mark them dead.

    Args:
        count_rows_fn: Optional override injected by tests. When provided it
            must accept ``(strategy, since)`` and return an iterable of
            ``(generator, domain, count)`` tuples. Falls back to a live DB
            query when None.
    """
    if count_rows_fn is not None:
        return {(g, d): n for g, d, n in count_rows_fn(strategy, since)}

    conn = get_pg()
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT gm.generator, q.domain, COUNT(*) AS n
            FROM questions q
            JOIN generation_metadata gm ON gm.question_id = q.id
            WHERE gm.generation_method = %s AND q.created_at >= %s
            GROUP BY gm.generator, q.domain
            """,
            (strategy, since),
        )
        return {(row["generator"], row["domain"]): row["n"] for row in cur.fetchall()}


def _execute_strategy_passes(
    *,
    strategy: str,
    module: str,
    want: int,
    per_country_cap: float | None,
    workers: int,
    strategy_started: datetime,
    max_passes: int,
    run_generator_fn=None,
    count_rows_fn=None,
) -> int:
    """Run cell allocation + execution up to ``max_passes`` times.

    Phase 2g.13 (Team C). Extracted from ``_run_one_strategy`` so the
    multi-pass loop is unit-testable independently of the DB.

    Exit conditions:
      * actual >= want (success — full budget filled)
      * pass produced 0 new rows AND pass_num > 1 (sampler ceiling)
      * pass_num == max_passes (cap reached)

    Returns the final ``actual`` rowcount produced by ``strategy`` since
    ``strategy_started``.

    Args:
        run_generator_fn: Override for the per-cell dispatch. Tests pass
            a stub that records cell calls without touching the DB. Falls
            back to the module-level ``_run_generator`` when None.
        count_rows_fn: Override for the rowcount query. Tests pass a stub
            that returns scripted yields. Falls back to
            ``_count_strategy_rows_since`` when None.
    """
    if run_generator_fn is None:
        run_generator_fn = _run_generator
    if count_rows_fn is None:
        count_rows_fn = _count_strategy_rows_since

    # Phase 2g.13 cross-pass threading: clear any stale attempted-IDs from
    # a previous build in the same process. Strategies will re-populate
    # this as they sample.
    reset_attempted_fact_ids(strategy)

    # Phase 2g.15 (Team C): reset dead-cell registry so stale state from a
    # previous build in the same process doesn't carry forward.
    reset_dead_cells(strategy)

    # Dynamic-loop limits (all default OFF — single-pass behaviour preserved).
    wall_limit_s = _resolve_wall_time_limit_s()
    min_yield_pct = _resolve_min_yield_pct()
    start_wall = time.monotonic()
    low_yield_streak = 0

    # Phase 2g.15: track the per-cell rowcount snapshot before each pass so we
    # can compute per-cell deltas after it completes.
    _pass_cell_count_fn = None  # optional injection point for tests

    actual = 0
    for pass_num in range(1, max_passes + 1):
        remaining = want - actual
        if remaining <= 0:
            break

        if wall_limit_s > 0:
            elapsed = time.monotonic() - start_wall
            if elapsed >= wall_limit_s:
                logger.info(
                    "corpus: {} wall-time budget exhausted "
                    "({:.1f}s ≥ {:.1f}s), stopping at pass {}/{}",
                    strategy, elapsed, wall_limit_s, pass_num - 1, max_passes,
                )
                break

        # Phase 2g.15: skip cells that were zero-yield in a previous pass.
        dead = get_dead_cells(strategy)
        if dead and pass_num > 1:
            logger.info(
                "corpus: {} pass {}/{} skipping {} dead cells: {}",
                strategy, pass_num, max_passes, len(dead), sorted(dead),
            )

        cell_calls = _build_cell_calls(
            strategy, module, remaining, per_country_cap,
            skip_cells=dead if dead else None,
        )

        # Phase 2g.15: snapshot pre-pass per-cell counts to detect zeros.
        # The snapshot is keyed (generator, domain) for LLM strategies and
        # (None, domain) for template; the heuristic only skips LLM cells
        # (template cells are always cheap to re-run).
        pre_pass_counts: dict[tuple[str, str], int] = {}
        if strategy in LLM_STRATEGIES:
            pre_pass_counts = _count_strategy_rows_per_cell(
                strategy, strategy_started, _pass_cell_count_fn,
            )

        if workers <= 1:
            for kw in cell_calls:
                run_generator_fn(**kw)
        else:
            with cf.ThreadPoolExecutor(max_workers=workers) as ex:
                futures = [ex.submit(run_generator_fn, **kw) for kw in cell_calls]
                for fut in cf.as_completed(futures):
                    try:
                        fut.result()
                    except Exception as e:  # noqa: BLE001
                        logger.error("corpus: {} cell raised: {}", strategy, e)

        new_actual = count_rows_fn(strategy, strategy_started)
        produced = new_actual - actual
        logger.info(
            "corpus: {} pass {}/{} produced={} cumulative={}/{}",
            strategy, pass_num, max_passes, produced, new_actual, want,
        )

        # Phase 2g.15: after the pass, identify cells that produced 0 rows
        # and register them as dead so the next pass skips them.
        if strategy in LLM_STRATEGIES:
            post_pass_counts = _count_strategy_rows_per_cell(
                strategy, strategy_started, _pass_cell_count_fn,
            )
            newly_dispatched = {
                (kw.get("generator", ""), kw.get("domain", ""))
                for kw in cell_calls
            }
            for cell in newly_dispatched:
                pre = pre_pass_counts.get(cell, 0)
                post = post_pass_counts.get(cell, 0)
                if post - pre == 0:
                    register_dead_cell(strategy, cell[0], cell[1])

        if produced == 0 and pass_num > 1:
            logger.info(
                "corpus: {} no-progress on pass {} — sampler ceiling "
                "hit, stopping early",
                strategy, pass_num,
            )
            break
        # Diminishing-returns exit (off by default). Triggers when
        # `produced` is below `min_yield_pct%` of the budget for two
        # consecutive passes. Pass 1 doesn't count because it has no
        # prior pass to compare against.
        if min_yield_pct > 0 and want > 0 and pass_num > 1:
            yield_frac = (produced / want) * 100.0
            if yield_frac < min_yield_pct:
                low_yield_streak += 1
                if low_yield_streak >= MIN_YIELD_STREAK:
                    logger.info(
                        "corpus: {} diminishing returns "
                        "({} consecutive passes < {:.1f}% of {}), "
                        "stopping at pass {}/{}",
                        strategy, low_yield_streak, min_yield_pct, want,
                        pass_num, max_passes,
                    )
                    actual = new_actual
                    break
            else:
                low_yield_streak = 0
        actual = new_actual

    return actual


def _build_cell_calls(
    strategy: str,
    module: str,
    want: int,
    per_country_cap: float | None,
    skip_cells: set[tuple[str, str]] | None = None,
) -> list[dict]:
    """Build the per-strategy cell list for ``_run_one_strategy``.

    Phase 2g.12 (Team C). Extracted from ``build_pilot_corpus._run_one_strategy``
    so the cell-allocation formula is unit-testable. Callers must seed
    ``random`` for deterministic shuffles in tests.

    LLM-pickable strategies use ``cell_count = max(1, min(G*D, want // 2))``
    so each cell carries ≥2 budget for any want ≥ 4. The previous formula
    (per_cell = max(1, want // (G*D))) scheduled all 30 cells with take=1
    when want < 30, silently overspent the budget by up to 50%, and
    starved sampler-empty cells out at 0 questions each. v9 audit-pilot
    saw 26/60 cells exit zero-attempt.

    Non-LLM strategies (template) use the simpler per-domain formula —
    they don't rotate generators and have a denser viable-fact pool.

    Args:
        skip_cells: Phase 2g.15 (Team C). When provided, these (generator,
            domain) pairs are excluded from the candidate cell list before
            shuffling. The per-cell budget is redistributed across the
            remaining cells so the total ``want`` is unchanged.
    """
    cell_calls: list[dict] = []
    if strategy in LLM_STRATEGIES:
        total_cells = len(GENERATORS) * len(DOMAINS)
        all_cells = [(g, d) for g in GENERATORS for d in DOMAINS]
        # Phase 2g.15: drop dead cells before sizing the run.
        if skip_cells:
            all_cells = [(g, d) for g, d in all_cells if (g, d) not in skip_cells]
        cell_count = max(1, min(len(all_cells) if all_cells else total_cells, want // 2))
        random.shuffle(all_cells)
        cells = all_cells[:cell_count]
        per_cell = max(1, want // cell_count)
        rem = want - per_cell * cell_count
        for g, d in cells:
            take = per_cell + (1 if rem > 0 else 0)
            if rem > 0:
                rem -= 1
            if take <= 0:
                continue
            cell_calls.append({
                "module": module, "domain": d, "count": take,
                "generator": g, "per_country_cap": per_country_cap,
            })
    else:
        per_cell = max(1, want // len(DOMAINS))
        rem = want - per_cell * len(DOMAINS)
        doms = DOMAINS[:]
        random.shuffle(doms)
        for d in doms:
            take = per_cell + (1 if rem > 0 else 0)
            if rem > 0:
                rem -= 1
            cell_calls.append({
                "module": module, "domain": d, "count": take,
                "per_country_cap": per_country_cap,
            })
    return cell_calls


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _tag_rows(
    *,
    generation_method: str,
    since: datetime,
    limit: int,
    tag: str,
) -> int:
    """Add `tag` to the tags[] of the newest `limit` questions generated by
    `generation_method` after `since`. Returns rows updated."""
    conn = get_pg()
    cur = conn.cursor()
    cur.execute(
        """
        WITH candidates AS (
            SELECT q.id
            FROM   questions q
            JOIN   generation_metadata gm ON gm.question_id = q.id
            WHERE  gm.generation_method = %s
              AND  q.created_at >= %s
            ORDER BY q.created_at
            LIMIT  %s
        )
        UPDATE questions q
           SET tags = array_append(
                   COALESCE(array_remove(q.tags, %s), '{}'::text[]),
                   %s)
         FROM  candidates c
         WHERE q.id = c.id
        """,
        (generation_method, since, limit, tag, tag),
    )
    updated = cur.rowcount
    conn.commit()
    return updated


def _existing_corpus_count(tag: str) -> dict[str, int]:
    conn = get_pg()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT gm.generation_method, count(*) AS cnt
        FROM   questions q
        JOIN   generation_metadata gm ON gm.question_id = q.id
        WHERE  %s = ANY(q.tags)
        GROUP  BY gm.generation_method
        """,
        (tag,),
    )
    return {row["generation_method"]: row["cnt"] for row in cur.fetchall()}


def _resolve_build_started_at(tag: str) -> tuple[datetime, bool]:
    """Return the build's effective start time, restart-safe.

    Returns ``(started, is_resume)``. On a fresh build (no questions yet
    tagged with ``tag``), returns ``(datetime.now(), False)``. On a resume,
    returns ``(MIN(created_at) of build-tagged questions, True)`` so the
    closed-book quota cap query in ``count_closed_book_solvable`` scopes
    the count across all cb-tagged questions created during the build's
    lifetime, not just the current process.

    Audit pilot v8 (Phase 2g.10) accumulated 53 cb-relabels (29+13+11)
    across three sessions — well over the corpus cap of 50 and the
    per-strategy cap of 10 — because each restart reset ``started`` to
    the new process's clock and the prior runs' cb-tags fell outside
    the ``since`` window.
    """
    conn = get_pg()
    cur = conn.cursor()
    cur.execute(
        "SELECT MIN(created_at) AS earliest FROM questions WHERE %s = ANY(tags)",
        (tag,),
    )
    row = cur.fetchone()
    earliest = row["earliest"] if row else None
    if earliest is not None:
        return earliest, True
    return datetime.now(), False


def _run_generator(
    *,
    module: str,
    domain: str,
    count: int,
    generator: str | None = None,
    difficulty: int | None = None,
    per_country_cap: float | None = None,
) -> bool:
    """Dispatch a single (strategy × domain × generator) cell.

    In-process by default (Phase 2g.10 Team Delta A2). Set
    ``OENOBENCH_USE_SUBPROCESS_DISPATCH=1`` to fall back to the legacy
    ``subprocess.run`` path — useful as a roll-back hatch if the in-process
    path misbehaves on a given audit run.
    """
    if os.environ.get(USE_SUBPROCESS_ENV_VAR) == "1":
        return _run_generator_subprocess(
            module=module, domain=domain, count=count,
            generator=generator, difficulty=difficulty,
            per_country_cap=per_country_cap,
        )
    return _run_generator_in_process(
        module=module, domain=domain, count=count,
        generator=generator, difficulty=difficulty,
        per_country_cap=per_country_cap,
    )


def _run_generator_subprocess(
    *,
    module: str,
    domain: str,
    count: int,
    generator: str | None = None,
    difficulty: int | None = None,
    per_country_cap: float | None = None,
) -> bool:
    """Legacy subprocess path. Pays a Python cold-start (~2-3s) per cell."""
    args = [
        sys.executable,
        "-m",
        f"src.generators.{module}",
        "--domain",
        domain,
        "--count",
        str(count),
    ]
    if generator:
        args += ["--generator", generator]
    if difficulty:
        args += ["--difficulty", str(difficulty)]
    if per_country_cap is not None:
        # Phase 2g.8 fix: previously per_country_cap was plumbed only into
        # the sampler functions; the audit-pilot orchestrator never passed
        # it through to the strategy subprocesses, so audit_pilot_v6 ran
        # with NO country cap (D3 ratio = 4.52). All 5 strategy CLIs
        # accept --per-country-cap as of Phase 2g.8.
        args += ["--per-country-cap", str(per_country_cap)]
    logger.info("corpus: running {}", " ".join(args[2:]))
    res = subprocess.run(args)
    if res.returncode != 0:
        logger.error("corpus: generator exited non-zero: {}", " ".join(args))
        return False
    return True


def _run_generator_in_process(
    *,
    module: str,
    domain: str,
    count: int,
    generator: str | None = None,
    difficulty: int | None = None,
    per_country_cap: float | None = None,
) -> bool:
    """In-process dispatch via the strategy module's ``run_generate(...)``.

    Removes the ~2-3s Python cold-start each subprocess pays. v8 paid ~13min
    of pure cold-start overhead across 321 cells; the 10k full run pays ~5h.
    """
    try:
        mod = importlib.import_module(f"src.generators.{module}")
    except Exception as e:  # noqa: BLE001
        logger.error("corpus: failed to import strategy module {}: {}", module, e)
        return False

    if not hasattr(mod, "run_generate"):
        logger.error(
            "corpus: strategy module {} does not expose run_generate(...). "
            "Set OENOBENCH_USE_SUBPROCESS_DISPATCH=1 as a fallback.",
            module,
        )
        return False

    kwargs: dict = {
        "domain": domain,
        "count": count,
        "per_country_cap": per_country_cap,
    }
    if generator is not None:
        kwargs["generator"] = generator
    if difficulty is not None:
        kwargs["difficulty"] = str(difficulty)

    logger.info(
        "corpus: in-process {} domain={} count={} generator={} difficulty={} "
        "per_country_cap={}",
        module, domain, count, generator, difficulty, per_country_cap,
    )
    try:
        result = mod.run_generate(**kwargs)
    except Exception as e:  # noqa: BLE001
        logger.error(
            "corpus: strategy {} raised in-process: {}: {}",
            module, type(e).__name__, e,
        )
        return False
    if isinstance(result, dict):
        logger.info(
            "corpus: {} done domain={} → generated={} relabeled_l1={} "
            "rejected_overflow={}",
            module, domain,
            result.get("generated"),
            result.get("relabeled_l1"),
            result.get("rejected_overflow"),
        )
    return True


def _resolve_max_workers(arg: int | None) -> int:
    """Resolve the cell-dispatch worker count.

    Priority: explicit ``arg`` > ``OENOBENCH_MAX_WORKERS`` env var > default 1.
    A non-positive value falls through to default 1 so audit pilots don't
    silently jump from "serial" to "16-way concurrent" if a stale env var leaks.
    """
    if arg is not None and arg > 0:
        return int(arg)
    raw = os.environ.get(MAX_WORKERS_ENV_VAR)
    if raw:
        try:
            n = int(raw)
            if n > 0:
                return n
        except ValueError:
            logger.warning(
                "{} is set but not a positive int (got {!r}); falling back to 1",
                MAX_WORKERS_ENV_VAR, raw,
            )
    return 1


def _resolve_strategy_workers(arg: int | None) -> int:
    """Resolve the top-level strategy-dispatch worker count.

    Priority: explicit ``arg`` > ``OENOBENCH_STRATEGY_WORKERS`` env var >
    default 1. A non-positive value falls through to default 1 (sequential).

    Phase 2g.10 (Team Golf A4).
    """
    if arg is not None and arg > 0:
        return int(arg)
    raw = os.environ.get(STRATEGY_WORKERS_ENV_VAR)
    if raw:
        try:
            n = int(raw)
            if n > 0:
                return n
        except ValueError:
            logger.warning(
                "{} is set but not a positive int (got {!r}); falling back to 1",
                STRATEGY_WORKERS_ENV_VAR, raw,
            )
    return 1


# ─── Phase 2g.10 (Team Golf B3) — per-cell circuit breaker ───────────────────


class CellTracker:
    """Rolling-window tracker for kept-rate-driven cell abandonment.

    Each strategy's per-cell loop instantiates one tracker, calls
    ``record(was_kept)`` after each attempt, and breaks when
    ``should_abandon()`` returns True.

    Defaults match the spec: ``window=20`` attempts, ``min_attempts=10``,
    ``threshold=0.05`` (strict <). When the live kept-rate falls strictly
    below 5% after at least 10 attempts, ``should_abandon()`` returns True
    and the cell is abandoned. ``remaining_budget(original)`` exposes the
    unused share. Caller applies the 2 × original cap when reallocating to
    the next cell, so one badly-misfiring cell can't soak the whole strategy
    budget.
    """

    def __init__(
        self,
        *,
        window: int = 20,
        min_attempts: int = 15,
        threshold: float = 0.05,
    ) -> None:
        self.window = max(1, window)
        self.min_attempts = max(1, min_attempts)
        self.threshold = float(threshold)
        self.attempts = 0
        self.kept = 0
        self._recent: list[int] = []
        self._abandoned = False

    def record(self, was_kept: bool) -> None:
        self.attempts += 1
        flag = 1 if was_kept else 0
        if was_kept:
            self.kept += 1
        self._recent.append(flag)
        if len(self._recent) > self.window:
            self._recent.pop(0)

    def kept_rate(self) -> float:
        """Rolling kept-rate over the last ``window`` attempts.

        Falls back to overall kept-rate while ``attempts`` < ``window`` so
        ``should_abandon()`` doesn't false-fire on the first 9 attempts.
        """
        if self.attempts == 0:
            return 0.0
        if len(self._recent) < self.window:
            return self.kept / self.attempts
        return sum(self._recent) / len(self._recent)

    def should_abandon(self) -> bool:
        if self._abandoned:
            return True
        if self.attempts < self.min_attempts:
            return False
        if self.kept_rate() < self.threshold:
            self._abandoned = True
            return True
        return False

    def remaining_budget(self, original: int) -> int:
        """Unused per-cell budget when the tracker abandons.

        Returns ``max(0, original - kept)`` so an early-abandoned cell with
        0 kept hands its full ``original`` count to the next cell. Caller
        applies the 2 × original cap when reallocating.
        """
        if original <= 0:
            return 0
        unused = original - self.kept
        return max(0, int(unused))


def _circuit_breaker_enabled() -> bool:
    """Whether the circuit-breaker env-var gate is active.

    Default OFF for v8 reproducibility. Strategies should consult this AND
    accept an explicit ``tracker`` kwarg so callers can override.
    """
    return os.environ.get(CIRCUIT_BREAKER_ENV_VAR) == "1"


def _reallocate_with_cap(
    *, original: int, leftover: int, cap_factor: int = 2,
) -> int:
    """Compute the next cell's count given carry-over from prior cells.

    Spec: ``next_count = min(original + leftover, original × cap_factor)``.
    Used by both ``_corpus.build_pilot_corpus`` (between LLM-strategy cells)
    and ``template_generator`` (between domains inside ``run_generate``).
    """
    if original <= 0:
        return 0
    proposed = original + max(0, leftover)
    cap = original * cap_factor
    return min(proposed, cap)


# ─── Build ────────────────────────────────────────────────────────────────────


def build_pilot_corpus(
    *,
    tag: str = "audit_pilot_v1",
    per_strategy: int = 120,
    seed: int = 42,
    skip_strategies: Iterable[str] = (),
    per_country_cap: float | None = None,
    max_workers: int | None = None,
    strategy_workers: int | None = None,
) -> dict:
    """Generate ~`per_strategy` questions for each strategy and tag them.

    Total target = 5 × per_strategy (≈600 for MVA).
    Per-strategy breakdown is round-robin across domains (and generators
    for LLM strategies) so we get reasonable coverage without micro-managing
    difficulty/cognitive cells inside each call.

    Args:
        per_country_cap: Phase 2g.8. Forwarded to every strategy subprocess
            via ``--per-country-cap``. Set to a fraction in (0, 1] to enforce
            a per-call country cap on the sampler (Team ε D3-fix v3); ``None``
            disables. Audit pilots should typically pass 0.10.
        max_workers: Phase 2g.10 (Team Delta A3). Worker count for the
            (generator × domain) cell dispatch ThreadPoolExecutor. ``None``
            (default) resolves via ``OENOBENCH_MAX_WORKERS`` env var, falling
            back to 1 (sequential) so audit-pilot runs stay bit-for-bit
            reproducible by default.
        strategy_workers: Phase 2g.10 (Team Golf A4). Worker count for the
            *top-level* strategy-dispatch ThreadPoolExecutor. The 5 strategies
            (template, fact_to_question, comparative, scenario_synthesis,
            distractor_mining) run sequentially when ``1`` (default) so audit
            pilots reproduce bit-for-bit. ``>=2`` runs strategies concurrently.
            Resolves via ``OENOBENCH_STRATEGY_WORKERS`` env var when ``None``.
            Concurrency-safety: the ``_QUOTA_LOCK`` in
            ``_question_db.insert_question_gated`` serialises the cb-quota
            count-then-insert pair across strategies; ``_tag_rows`` uses a
            per-strategy ``strategy_started`` snapshot so tag windows don't
            overlap.
    """
    workers = _resolve_max_workers(max_workers)
    s_workers = _resolve_strategy_workers(strategy_workers)
    random.seed(seed)
    started, is_resume = _resolve_build_started_at(tag)

    counts_before = _existing_corpus_count(tag)
    if is_resume:
        logger.info(
            "corpus: RESUME detected for tag {} — reusing build start {} so the "
            "closed-book quota count spans prior process(es). Existing rows = {}",
            tag, started.isoformat(), counts_before,
        )
    else:
        logger.info(
            "corpus: FRESH BUILD for tag {} — start={}. Existing rows = {}",
            tag, started.isoformat(), counts_before,
        )

    # Phase 2g.8: scope the closed-book quota cap to this pilot's size, not the
    # 10k full-run default. Without this, a 600-Q pilot's cap is 2500 (i.e.
    # effectively no cap), which let v6 leak 158 closed-book relabels on a
    # 264-Q corpus instead of the documented ceil(264 × 0.25) = 66. The
    # `try/finally` ensures the override is cleared even if a strategy raises,
    # so subsequent processes (full-gen runs, tests) see clean state.
    #
    # Phase 2g.9 (audit #7 follow-up): in addition to the in-process module-
    # global, also export an env var so child subprocesses spawned by
    # `_run_generator` resolve the same scoped cap. The module-global alone
    # only works for in-process callers; v7 ran with the default 10k cap and
    # accumulated 172 closed-book relabels on a 242-Q corpus.
    target_size = per_strategy * len(STRATEGY_MODULES)
    set_corpus_target(target_size)
    prev_env_target = os.environ.get(CORPUS_TARGET_ENV_VAR)
    os.environ[CORPUS_TARGET_ENV_VAR] = str(target_size)
    # Phase 2g.9 hotfix: scope the closed-book count to questions created
    # during this build only. Without this, the global query in
    # `count_closed_book_solvable()` totals every historical pilot's
    # cb-tagged questions; v8's first launch saw 427/50 immediately because
    # v5+v6+v7 had already accumulated 427 cb-tagged questions in the DB.
    prev_env_since = os.environ.get(CORPUS_BUILD_SINCE_ENV_VAR)
    os.environ[CORPUS_BUILD_SINCE_ENV_VAR] = started.isoformat()
    # Phase 2g.10: per-strategy closed-book budget. Each strategy gets its
    # own ceil(per_strategy × 0.25) slot count, counted by generation_method,
    # so the first strategy in build order can't monopolise the corpus-wide
    # cap and starve later strategies. The corpus-level env var stays set so
    # callers without a generation_method (or without the per-strategy var)
    # still fall back to the corpus cap.
    prev_env_strategy = os.environ.get(STRATEGY_TARGET_ENV_VAR)
    os.environ[STRATEGY_TARGET_ENV_VAR] = str(per_strategy)
    logger.info(
        "corpus: set closed-book quota target to {} (per-pilot 25% cap), "
        "per-strategy budget {} (per-strategy 25% cap = {}), "
        "scoped to questions created since {}",
        target_size, per_strategy,
        (per_strategy * 25 + 99) // 100,
        started.isoformat(),
    )

    def _run_one_strategy(strategy: str, module: str) -> tuple[str, dict]:
        """Body of a single strategy iteration.

        Returns ``(strategy, {generated, tagged, skipped})``. Hoisted out so
        the top-level executor (Team Golf A4, ``strategy_workers >= 2``) can
        submit each strategy independently. The per-strategy
        ``strategy_started`` snapshot is captured INSIDE this body, after
        the executor admits us, so concurrent strategies don't share a
        single ``since`` window in ``_tag_rows``.
        """
        if strategy in skip_strategies:
            logger.info("corpus: skipping {}", strategy)
            return strategy, {"generated": 0, "tagged": 0, "skipped": True}
        already = counts_before.get(strategy, 0)
        if already >= per_strategy:
            logger.info("corpus: {} already at {}/{}, skipping", strategy, already, per_strategy)
            return strategy, {"generated": 0, "tagged": 0, "skipped": True}
        want = per_strategy - already
        strategy_started = datetime.now()

        # Phase 2g.13 (Team C): multi-pass cell-execution loop.
        #
        # v10 build kept 53/120 (44%) — the Phase 2g.12 fixes eliminated
        # pipeline waste, but the bottleneck moved upstream to legitimate
        # quality refusals (LLM "fact too vague", substantiveness filter,
        # sampler exhaustion of multi-fact bundles). Strategies that hit
        # those gates exit under-budget with no recovery.
        #
        # The retry loop re-runs cell allocation with the REMAINING budget
        # up to OENOBENCH_MAX_BUILD_PASSES iterations. Already-used facts
        # are excluded naturally via ``get_used_fact_ids()`` inside each
        # strategy module, so successive passes try fresh facts. Exit
        # conditions: success (actual >= want), no-progress (pass added
        # zero rows = hard sampler ceiling), or pass cap.
        max_passes = _resolve_max_build_passes()
        actual = _execute_strategy_passes(
            strategy=strategy, module=module, want=want,
            per_country_cap=per_country_cap, workers=workers,
            strategy_started=strategy_started, max_passes=max_passes,
        )

        tagged = _tag_rows(
            generation_method=strategy,
            since=strategy_started,
            limit=want,
            tag=tag,
        )
        logger.info(
            "corpus: {} budget={} generated={} tagged={}",
            strategy, want, actual, tagged,
        )
        return strategy, {
            "budget": want, "generated": actual, "tagged": tagged,
            "skipped": False,
        }

    results: dict[str, dict] = {}
    try:
        if s_workers <= 1:
            for strategy, module in STRATEGY_MODULES.items():
                name, stats = _run_one_strategy(strategy, module)
                results[name] = stats
        else:
            logger.info(
                "corpus: dispatching {} strategies concurrently (strategy_workers={})",
                len(STRATEGY_MODULES), s_workers,
            )
            with cf.ThreadPoolExecutor(max_workers=s_workers) as ex:
                futures = {
                    ex.submit(_run_one_strategy, s, m): s
                    for s, m in STRATEGY_MODULES.items()
                }
                for fut in cf.as_completed(futures):
                    strategy = futures[fut]
                    try:
                        name, stats = fut.result()
                        results[name] = stats
                    except Exception as e:  # noqa: BLE001
                        logger.error(
                            "corpus: top-level strategy {} raised: {}",
                            strategy, e,
                        )
                        results[strategy] = {
                            "generated": 0, "tagged": 0, "skipped": True,
                            "error": str(e),
                        }
    finally:
        set_corpus_target(None)
        if prev_env_target is None:
            os.environ.pop(CORPUS_TARGET_ENV_VAR, None)
        else:
            os.environ[CORPUS_TARGET_ENV_VAR] = prev_env_target
        if prev_env_since is None:
            os.environ.pop(CORPUS_BUILD_SINCE_ENV_VAR, None)
        else:
            os.environ[CORPUS_BUILD_SINCE_ENV_VAR] = prev_env_since
        if prev_env_strategy is None:
            os.environ.pop(STRATEGY_TARGET_ENV_VAR, None)
        else:
            os.environ[STRATEGY_TARGET_ENV_VAR] = prev_env_strategy

    counts_after = _existing_corpus_count(tag)
    logger.info("corpus: post-build totals = {}", counts_after)
    return {
        "started_at": started.isoformat(),
        "seed": seed,
        "tag": tag,
        "per_strategy": per_strategy,
        "results": results,
        "totals": counts_after,
    }


# ─── Gold sheet ───────────────────────────────────────────────────────────────

GOLD_RUBRICS = [
    "answer_correct",         # the keyed answer is correct given the source
    "distractors_plausible",  # each distractor is plausibly wrong (not trivially eliminable)
    "not_ambiguous",          # only one defensible answer
    "source_faithful",        # question content stays within source fact (semantic)
    "needs_source",           # not solvable purely from general world knowledge
    "no_vague_language",      # no marketing / "acclaimed" / "iconic" etc.
    "difficulty_match",       # difficulty label fits perceived hardness
    "cognitive_match",        # cognitive_dim label fits the cognitive demand
    # v2.3 Team γ — new rubrics that align with narrow LLM-proxy signals.
    # Kept additive so old gold sheets (run #1..#3) still import cleanly.
    "verbatim_copy",          # question/correct-option copies source verbatim (LCS ≥ 0.6)
    "wine_category_leak",     # a distractor's wine category differs from the correct option's
]


def export_gold_sheet(tag: str, out_path: Path, sample_size: int, seed: int) -> int:
    """Sample `sample_size` questions from the corpus and write a CSV for offline review.

    The `source_facts` column contains ALL linked facts joined with `\\n---\\n`
    and prefixed by `[1] ... [2] ... ` so multi-fact strategies (comparative,
    scenario, distractor) can be reviewed against their full evidence base
    (see `docs/GOLD_CALIBRATION_ANALYSIS.md` §3).
    """
    random.seed(seed)
    conn = get_pg()
    cur = conn.cursor()
    # Aggregate ALL linked facts per question. We synthesize a 1-based index
    # via row_number() because question_facts has no explicit ordering column;
    # ordering by fact_id is stable per-question.
    cur.execute(
        """
        WITH ordered_facts AS (
            SELECT
                qf.question_id,
                f.fact_text,
                row_number() OVER (
                    PARTITION BY qf.question_id
                    ORDER BY qf.fact_id
                ) AS fact_order
            FROM question_facts qf
            JOIN facts f ON f.id = qf.fact_id
        )
        SELECT q.id AS uuid, q.question_id, q.domain::text, q.difficulty::text,
               q.cognitive_dim::text, q.question_type::text,
               q.question_text, q.options, q.correct_answer, q.correct_answer_text,
               q.explanation, gm.generator::text, gm.generation_method,
               COALESCE(
                   string_agg(
                       '[' || of.fact_order::text || '] ' || of.fact_text,
                       E'\n---\n'
                       ORDER BY of.fact_order
                   ),
                   ''
               ) AS source_facts
        FROM   questions q
        JOIN   generation_metadata gm ON gm.question_id = q.id
        LEFT   JOIN ordered_facts of ON of.question_id = q.id
        WHERE  %s = ANY(q.tags)
        GROUP  BY q.id, gm.generator, gm.generation_method
        """,
        (tag,),
    )
    rows = cur.fetchall()
    if not rows:
        logger.warning("gold sheet: no rows tagged {}", tag)
        return 0

    # Stratified sample: take ~`sample_size / N_strategies` from each strategy.
    # Within a strategy, sub-stratify across (generator, difficulty) cells so
    # the reviewer doesn't see e.g. all template_only L1 questions clustered
    # at the top. Falls back to random fill when a strategy is short on cells.
    strategy_buckets: dict[str, list[dict]] = {}
    for r in rows:
        strategy_buckets.setdefault(r["generation_method"], []).append(r)

    n_strategies = max(1, len(strategy_buckets))
    per_strategy = max(1, sample_size // n_strategies)

    selected: list[dict] = []
    for method, group in strategy_buckets.items():
        # Build (generator, difficulty) sub-buckets and round-robin pick from
        # them so the per-strategy slice is as balanced as the corpus allows.
        sub: dict[tuple[str, str], list[dict]] = {}
        for r in group:
            key = (r.get("generator") or "template_only", str(r.get("difficulty") or ""))
            sub.setdefault(key, []).append(r)
        for items in sub.values():
            random.shuffle(items)

        chosen: list[dict] = []
        # Round-robin across cells until we hit per_strategy or exhaust the cells.
        keys = sorted(sub.keys())
        random.shuffle(keys)
        while len(chosen) < per_strategy and any(sub[k] for k in keys):
            for k in keys:
                if not sub[k]:
                    continue
                chosen.append(sub[k].pop())
                if len(chosen) >= per_strategy:
                    break
        selected.extend(chosen)
    random.shuffle(selected)
    selected = selected[:sample_size]

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        header = [
            "uuid",
            "public_qid",
            "strategy",
            "generator",
            "domain",
            "difficulty",
            "cognitive_dim",
            "question_text",
            "options",
            "correct_answer",
            "source_facts",
        ] + GOLD_RUBRICS + ["notes"]
        writer.writerow(header)
        for r in selected:
            writer.writerow([
                r["uuid"],
                r["question_id"],
                r["generation_method"],
                r["generator"],
                r["domain"],
                r["difficulty"],
                r["cognitive_dim"],
                r["question_text"],
                r["options"],
                r["correct_answer"],
                # Truncated for spreadsheet legibility; full evidence is still
                # present (most multi-fact bundles are well under 2000 chars).
                (r["source_facts"] or "")[:2000],
            ] + [""] * (len(GOLD_RUBRICS) + 1))
    logger.info("gold sheet: wrote {} rows to {}", len(selected), out_path)
    return len(selected)


def import_gold_sheet(csv_path: Path, reviewer: str) -> int:
    """Read a filled gold CSV and upsert into audit_gold_labels.

    Values recognised: 1/0 or y/n or true/false (case-insensitive). Blanks
    are ignored (treated as missing).
    """
    def _norm(val: str) -> bool | None:
        s = val.strip().lower()
        if not s:
            return None
        if s in {"1", "y", "yes", "true", "t"}:
            return True
        if s in {"0", "n", "no", "false", "f"}:
            return False
        return None

    imported = 0
    with csv_path.open(encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            labels: dict[str, bool | None] = {k: _norm(row.get(k, "")) for k in GOLD_RUBRICS}
            if all(v is None for v in labels.values()):
                continue
            qid = row.get("uuid", "").strip()
            if not qid:
                continue
            upsert_gold_label(
                question_id=qid,
                labels=labels,
                reviewer=reviewer,
                notes=row.get("notes", "").strip(),
            )
            imported += 1
    logger.info("gold import: upserted {} rows", imported)
    return imported


# ─── CLI ──────────────────────────────────────────────────────────────────────


@click.group()
def cli() -> None:
    """Audit pilot-corpus helpers."""


@cli.command("build")
@click.option("--tag", default="audit_pilot_v1")
@click.option("--per-strategy", default=120, type=int)
@click.option("--seed", default=42, type=int)
@click.option(
    "--skip",
    multiple=True,
    type=click.Choice(list(STRATEGY_MODULES)),
    help="Skip one or more strategies",
)
@click.option(
    "--per-country-cap",
    type=float,
    default=None,
    help=(
        "Per-call absolute country cap (fraction in (0, 1]) forwarded to "
        "every strategy subprocess. Phase 2g.8 wire-up: previously the "
        "sampler accepted this kwarg but the orchestrator never passed it, "
        "so audit_pilot_v6 ran with NO cap (D3 = 4.52). Pass 0.10 for "
        "audit pilots; default unset (no cap)."
    ),
)
@click.option(
    "--max-workers",
    type=int,
    default=None,
    help=(
        "Phase 2g.10 (Team Delta A3): worker count for the (generator × "
        "domain) cell dispatch ThreadPoolExecutor. Default 1 (sequential, "
        "audit-pilot reproducibility preserved). Override via this flag or "
        "OENOBENCH_MAX_WORKERS env var."
    ),
)
@click.option(
    "--strategy-workers",
    type=int,
    default=None,
    help=(
        "Phase 2g.10 (Team Golf A4): worker count for the *top-level* "
        "strategy-dispatch ThreadPoolExecutor. Default 1 (strategies run "
        "sequentially — audit-pilot reproducibility preserved). Override "
        "via this flag or OENOBENCH_STRATEGY_WORKERS env var."
    ),
)
def build_cmd(
    tag: str, per_strategy: int, seed: int,
    skip: tuple[str, ...], per_country_cap: float | None,
    max_workers: int | None,
    strategy_workers: int | None,
) -> None:
    summary = build_pilot_corpus(
        tag=tag,
        per_strategy=per_strategy,
        seed=seed,
        skip_strategies=skip,
        per_country_cap=per_country_cap,
        max_workers=max_workers,
        strategy_workers=strategy_workers,
    )
    click.echo(f"Corpus tag: {summary['tag']}")
    click.echo(f"Totals by strategy: {summary['totals']}")


@cli.command("export-gold")
@click.option("--tag", default="audit_pilot_v1")
@click.option("--out", type=click.Path(), default="data/reports/gold_sheet.csv")
@click.option("--size", default=60, type=int)
@click.option("--seed", default=42, type=int)
def export_gold_cmd(tag: str, out: str, size: int, seed: int) -> None:
    count = export_gold_sheet(tag, Path(out), size, seed)
    click.echo(f"Wrote {count} rows to {out}")


@cli.command("import-gold")
@click.option("--csv-path", type=click.Path(exists=True), required=True)
@click.option("--reviewer", required=True, help="Reviewer identifier (e.g. 'nikita')")
def import_gold_cmd(csv_path: str, reviewer: str) -> None:
    count = import_gold_sheet(Path(csv_path), reviewer)
    click.echo(f"Imported {count} gold labels")


if __name__ == "__main__":
    cli()
