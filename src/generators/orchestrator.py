"""
OenoBench — Question Generation Pipeline Orchestrator.

Main CLI entry point that coordinates all 5 generation strategies,
manages quotas, tracks progress, and runs quality checks.

Usage:
    python -m src.generators.orchestrator status
    python -m src.generators.orchestrator generate-all --resume
    python -m src.generators.orchestrator generate-all --dry-run
    python -m src.generators.orchestrator dedup --threshold 0.92
    python -m src.generators.orchestrator embed
    python -m src.generators.orchestrator validate
"""

import concurrent.futures as cf
import importlib
import math
import os
import random
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import click
from loguru import logger

from src.generators._dedup import batch_embed_and_store, run_dedup_pass
from src.generators._fact_sampler import DOMAIN_TARGETS, get_domain_stats
from src.generators._llm_client import GENERATOR_MODELS
from src.generators._question_db import (
    BUILD_TAG_ENV_VAR,
    CORPUS_BUILD_SINCE_ENV_VAR,
    CORPUS_TARGET_ENV_VAR,
    STRATEGY_TARGET_ENV_VAR,
    get_domain_generator_counts,
    get_question_count,
    get_used_fact_ids,
    set_corpus_target,
)
from src.utils.db import get_pg

# Phase 2g.10 (Team Delta A2): toggle subprocess fallback. Default is
# in-process dispatch (~2-3s/cell saved over the legacy subprocess.run path).
USE_SUBPROCESS_ENV_VAR = "OENOBENCH_USE_SUBPROCESS_DISPATCH"

# Phase 2g.10 (Team Delta A3): worker count for the (generator × domain)
# cell dispatch ThreadPoolExecutor. Default 1.
MAX_WORKERS_ENV_VAR = "OENOBENCH_MAX_WORKERS"

# Phase 2g.10 (Team Golf A4): worker count for the *top-level* strategy-
# dispatch ThreadPoolExecutor. Default 1 (sequential).
STRATEGY_WORKERS_ENV_VAR = "OENOBENCH_STRATEGY_WORKERS"

# ─── Logging setup ────────────────────────────────────────────────────────────

LOG_DIR = Path("data/logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)

# ─── Quota targets ────────────────────────────────────────────────────────────

OVERALL_TARGET = 10_000

# 25% of OVERALL_TARGET. Tracks the maximum share of `closed_book_solvable`
# questions in the corpus (Phase 2g.6 policy). Surfaced in `status` so
# the user can see when this cap is approaching.
from src.generators._closed_book_gate import CLOSED_BOOK_QUOTA_FRACTION
CLOSED_BOOK_QUOTA = int(CLOSED_BOOK_QUOTA_FRACTION * OVERALL_TARGET)

# v2.3 allocation (post-gold-v3 calibration, 2026-04-22). See
# docs/GENERATION_IMPROVEMENT_PLAN.md §0 and §13.
#
# Rationale: gold-v3 + audit_pilot_v3 show Gemini is the overall pass-rate
# leader (70.5% avg across 6 question-level agents vs 66.7% for Claude/ChatGPT)
# AND dominant on A3 FactEcho (81% pass vs 60% next best). Human review of 59
# gold-v3 rows corroborates (Gemini matches Claude/ChatGPT on avg rubric score,
# 75% perfect 8/8). Bump Gemini from 2400 → 2800 (+400); balance from the two
# verifier-gated tails: Qwen 1100 → 800 (-300, worst A1 score), Llama 700 → 600
# (-100, worst A3 score). Corpus cap stays under the 35% ceiling (Gemini 31%).
#
# Strategy allocation unchanged — template 10% share is defensible after v2.2
# radical overhaul (see §6). The template inventory has a separate diversity
# problem (one T/F pattern at 28% share, 27 of 38 registered templates never
# fire) addressed by §13 not by rebalancing strategies.
#
# v2.4 allocation (Phase 2g.18 cost-down, 2026-05-02). Volume-rebalance
# instead of per-call model downgrade (Opus stays Opus where it runs).
# Claude(Opus) drops 2400 → 1800 (-25%, the most expensive per-call model);
# Gemini bumps 2800 → 3200 (still 32% of corpus, under the 35% per-model
# corpus cap, and Gemini is the audit pass-rate leader so spending more on
# it is also a quality gain); Qwen bumps 800 → 1000 (calibration anchor for
# the B2 ScenarioCoherence audit, which needs the volume to converge).
# ChatGPT and Llama unchanged. Total stays at 9000 across the 5 LLM
# strategies (template still provides the remaining 1000 deterministically).
# Estimated 10k-run savings: $300-400 from the Opus volume cut. Combines
# with the L1 cb-quota relax (0.25 → 0.40) for the full cost-down package.
STRATEGY_TARGETS = {
    "fact_to_question": 4500,
    "template": 1000,
    "comparative": 1500,
    "scenario_synthesis": 1500,
    "distractor_mining": 1500,
}

# LLM-based strategies share 9,000 questions across 5 generators (template
# strategy contributes the remaining 1,000 deterministically). No model may
# exceed 35% of the corpus; current max is Gemini at 31%.
GENERATOR_TARGETS = {
    "claude": 1800,
    "chatgpt": 2400,
    "gemini": 3200,
    "qwen": 1000,
    "llama": 600,
}

# Maps strategy name to the module invoked via `python -m src.generators.<module>`
STRATEGY_MODULES = {
    "template": "template_generator",
    "fact_to_question": "fact_to_question",
    "comparative": "comparative_generator",
    "scenario_synthesis": "scenario_generator",
    "distractor_mining": "distractor_miner",
}

# Execution order (templates first — no LLM cost)
STRATEGY_ORDER = [
    "template",
    "fact_to_question",
    "comparative",
    "scenario_synthesis",
    "distractor_mining",
]

# Strategies that use an LLM generator
LLM_STRATEGIES = {"fact_to_question", "comparative", "scenario_synthesis", "distractor_mining"}


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _count_by_method(tag: str | None = None) -> dict[str, int]:
    """Return {generation_method: count}.

    When ``tag`` is provided, the count is scoped to questions that carry
    that tag (i.e. only the current release-tagged build). When omitted,
    counts span all questions in the table — used by the legacy 10k
    full-corpus run where there is no per-build tag.
    """
    conn = get_pg()
    cur = conn.cursor()
    if tag:
        cur.execute(
            """
            SELECT gm.generation_method, count(*) AS cnt
            FROM questions q
            JOIN generation_metadata gm ON gm.question_id = q.id
            WHERE %s = ANY(q.tags)
            GROUP BY gm.generation_method
            """,
            (tag,),
        )
    else:
        cur.execute(
            """
            SELECT gm.generation_method, count(*) AS cnt
            FROM questions q
            JOIN generation_metadata gm ON gm.question_id = q.id
            GROUP BY gm.generation_method
            """
        )
    return {row["generation_method"]: row["cnt"] for row in cur.fetchall()}


def _count_by_generator() -> dict[str, int]:
    """Return {generator: count} across all questions."""
    conn = get_pg()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT gm.generator, count(*) AS cnt
        FROM questions q
        JOIN generation_metadata gm ON gm.question_id = q.id
        GROUP BY gm.generator
        """
    )
    return {row["generator"]: row["cnt"] for row in cur.fetchall()}


def _count_by_domain() -> dict[str, int]:
    """Return {domain: count} across all questions."""
    conn = get_pg()
    cur = conn.cursor()
    cur.execute(
        "SELECT domain, count(*) AS cnt FROM questions GROUP BY domain"
    )
    return {row["domain"]: row["cnt"] for row in cur.fetchall()}


def _run_subprocess(module: str, args: list[str], dry_run: bool) -> bool:
    """Run a generator module as a subprocess. Returns True on success.

    Phase 2g.10 (Team Delta A2): subprocess path retained for the
    OENOBENCH_USE_SUBPROCESS_DISPATCH=1 fallback. The default execution path
    now goes through ``_run_strategy(...)`` which dispatches in-process.
    """
    cmd = [sys.executable, "-m", f"src.generators.{module}"] + args
    if dry_run:
        cmd.append("--dry-run")
    logger.info("Running: {}", " ".join(cmd))
    result = subprocess.run(cmd)
    if result.returncode != 0:
        logger.error("Command failed with exit code {}: {}", result.returncode, " ".join(cmd))
        return False
    return True


def _run_strategy(
    module: str,
    *,
    domain: str,
    count: int,
    generator: str | None = None,
    dry_run: bool = False,
) -> bool:
    """Dispatch a single (strategy × domain × generator) cell from the
    full-generation orchestrator.

    In-process by default (Phase 2g.10 Team Delta A2). Set
    ``OENOBENCH_USE_SUBPROCESS_DISPATCH=1`` to fall back to the legacy
    subprocess path.
    """
    if os.environ.get(USE_SUBPROCESS_ENV_VAR) == "1":
        args = ["--domain", domain, "--count", str(count)]
        if generator:
            args += ["--generator", generator]
        return _run_subprocess(module, args, dry_run)

    try:
        mod = importlib.import_module(f"src.generators.{module}")
    except Exception as e:  # noqa: BLE001
        logger.error("orchestrator: failed to import {}: {}", module, e)
        return False
    if not hasattr(mod, "run_generate"):
        logger.error("orchestrator: {} missing run_generate(...)", module)
        return False

    kwargs: dict = {"domain": domain, "count": count, "dry_run": dry_run}
    if generator is not None:
        kwargs["generator"] = generator
    logger.info(
        "orchestrator: in-process {} domain={} count={} generator={} dry_run={}",
        module, domain, count, generator, dry_run,
    )
    try:
        result = mod.run_generate(**kwargs)
    except Exception as e:  # noqa: BLE001
        logger.error(
            "orchestrator: {} raised in-process: {}: {}",
            module, type(e).__name__, e,
        )
        return False
    if isinstance(result, dict):
        logger.info(
            "orchestrator: {} done domain={} → generated={}",
            module, domain, result.get("generated"),
        )
    return True


def _resolve_max_workers(arg: int | None) -> int:
    """Resolve the cell-dispatch worker count for the full-gen orchestrator.

    Priority: explicit arg > OENOBENCH_MAX_WORKERS env var > default 1.
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

    Priority: explicit arg > OENOBENCH_STRATEGY_WORKERS env var > default 1.
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


# ─── CLI ──────────────────────────────────────────────────────────────────────


@click.group()
def cli():
    """OenoBench Question Generation Pipeline."""


# ─── status ───────────────────────────────────────────────────────────────────


@cli.command()
@click.option("--target", type=int, default=OVERALL_TARGET, help="Overall question target")
def status(target):
    """Show current generation progress vs targets."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    logger.add(LOG_DIR / f"orchestrator_{timestamp}.log", rotation="50 MB")

    total = get_question_count(status=None)
    pct = (total / target * 100) if target else 0

    by_domain = _count_by_domain()
    by_method = _count_by_method()
    by_generator = _count_by_generator()
    domain_stats = get_domain_stats()
    used_facts = get_used_fact_ids()
    total_facts = sum(d["total"] for d in domain_stats.values())

    click.echo(f"\n{'=' * 50}")
    click.echo("  OenoBench Question Generation Status")
    click.echo(f"{'=' * 50}\n")

    click.echo(f"Total: {total:,} / {target:,} ({pct:.1f}%)\n")

    # By domain
    click.echo("By Domain:")
    for domain in sorted(DOMAIN_TARGETS.keys()):
        have = by_domain.get(domain, 0)
        want = DOMAIN_TARGETS[domain]
        click.echo(f"  {domain:20s} {have:>5,} / {want:,}")

    # By strategy
    click.echo("\nBy Strategy:")
    for strategy in STRATEGY_ORDER:
        have = by_method.get(strategy, 0)
        want = STRATEGY_TARGETS[strategy]
        share = int(want / target * 100) if target else 0
        click.echo(f"  {strategy:20s} {have:>5,} / {want:,} ({share}%)")

    # By generator
    click.echo("\nBy Generator:")
    # LLM generators
    for gen in sorted(GENERATOR_TARGETS.keys()):
        have = by_generator.get(gen, 0)
        want = GENERATOR_TARGETS[gen]
        click.echo(f"  {gen:20s} {have:>5,} / {want:,}")
    # Template-only
    tmpl_count = by_method.get("template", 0)
    click.echo(f"  {'template_only':20s} {tmpl_count:>5,} / {STRATEGY_TARGETS['template']:,}")

    # Closed-book-solvable subset (Phase 2g.6 policy)
    from src.generators._question_db import count_closed_book_solvable
    cb_count = count_closed_book_solvable()
    cb_pct = (cb_count / CLOSED_BOOK_QUOTA * 100) if CLOSED_BOOK_QUOTA else 0
    click.echo(f"\nClosed-book-solvable subset:")
    click.echo(f"  closed_book_solvable {cb_count:>5,} / {CLOSED_BOOK_QUOTA:,}  ({cb_pct:.0f}% of quota)")

    # Fact coverage
    click.echo("\nFact Coverage:")
    click.echo(f"  Total facts:        {total_facts:>10,}")
    click.echo(f"  Facts used:         {len(used_facts):>10,}")
    coverage_pct = (len(used_facts) / total_facts * 100) if total_facts else 0
    click.echo(f"  Coverage:           {coverage_pct:>9.1f}%")

    click.echo()


# ─── generate-all ─────────────────────────────────────────────────────────────


def _scale_strategy_targets(target: int) -> dict[str, int]:
    """Scale `STRATEGY_TARGETS` proportionally to ``target``.

    Default `target == OVERALL_TARGET` is the identity. For sub-targets
    (e.g. 6500 for release_v1), each strategy is scaled by `target / OVERALL_TARGET`
    and rounded; rounding drift is absorbed by the largest strategy
    (`fact_to_question`) so the totals match exactly.
    """
    if target == OVERALL_TARGET:
        return dict(STRATEGY_TARGETS)
    if target <= 0:
        raise click.BadParameter("--target must be positive")
    ratio = target / OVERALL_TARGET
    scaled: dict[str, int] = {
        s: max(1, int(round(STRATEGY_TARGETS[s] * ratio)))
        for s in STRATEGY_TARGETS
    }
    drift = target - sum(scaled.values())
    if drift != 0:
        # Absorb rounding drift on the largest strategy so the sum matches target.
        biggest = max(scaled, key=scaled.get)
        scaled[biggest] = max(1, scaled[biggest] + drift)
    return scaled


def _resolve_build_started_at(tag: str | None, resume: bool) -> datetime:
    """Return the build-window start timestamp (UTC).

    Mirrors `src.qa._corpus._resolve_build_started_at` so the closed-book
    quota count is scoped to questions created during this build only.

    Resume + tag given + tagged rows exist in DB → use MIN(created_at) of
    those rows so a restart picks up the same window.
    Otherwise → NOW().
    """
    if resume and tag:
        try:
            conn = get_pg()
            cur = conn.cursor()
            cur.execute(
                "SELECT MIN(created_at) AS started "
                "FROM questions WHERE %s = ANY(tags)",
                (tag,),
            )
            row = cur.fetchone()
            if row and row.get("started"):
                started = row["started"]
                if started.tzinfo is None:
                    started = started.replace(tzinfo=timezone.utc)
                return started
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "orchestrator: could not resolve resume start from tag {!r}: "
                "{}; falling back to NOW()", tag, e,
            )
    return datetime.now(timezone.utc)


@cli.command("generate-all")
@click.option("--target", type=int, default=OVERALL_TARGET, help="Total questions to generate (scales STRATEGY_TARGETS proportionally)")
@click.option("--tag", type=str, default=None, help="Build-wide tag appended to every inserted question (e.g. release_v1)")
@click.option("--seed", type=int, default=None, help="Random seed for sampler reproducibility")
@click.option("--resume", is_flag=True, help="Resume from current DB state (re-uses tag's build window if --tag is set)")
@click.option("--dry-run", is_flag=True, help="Preview without DB writes")
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
        "sequentially). Override via this flag or OENOBENCH_STRATEGY_WORKERS "
        "env var."
    ),
)
def generate_all(target, tag, seed, resume, dry_run, max_workers, strategy_workers):
    """Run full generation pipeline across all strategies/models/domains."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    logger.add(LOG_DIR / f"orchestrator_{timestamp}.log", rotation="50 MB")

    if seed is not None:
        random.seed(seed)
        logger.info("orchestrator: random seeded with {}", seed)

    scaled_targets = _scale_strategy_targets(target)
    if scaled_targets != STRATEGY_TARGETS:
        click.echo(
            f"Scaling STRATEGY_TARGETS from {OVERALL_TARGET:,} → {target:,}: "
            + ", ".join(f"{s}={scaled_targets[s]:,}" for s in STRATEGY_ORDER)
        )

    # Phase 2j: scope the closed-book quota cap to the actual run target,
    # propagate the build tag + build-window start to child threads via env
    # vars (so `insert_question_gated` resolves the same scoped cap and
    # `insert_question` appends the build tag to every row).
    build_started = _resolve_build_started_at(tag, resume)
    set_corpus_target(target)
    prev_env = {
        BUILD_TAG_ENV_VAR: os.environ.get(BUILD_TAG_ENV_VAR),
        CORPUS_TARGET_ENV_VAR: os.environ.get(CORPUS_TARGET_ENV_VAR),
        CORPUS_BUILD_SINCE_ENV_VAR: os.environ.get(CORPUS_BUILD_SINCE_ENV_VAR),
        STRATEGY_TARGET_ENV_VAR: os.environ.get(STRATEGY_TARGET_ENV_VAR),
    }
    if tag:
        os.environ[BUILD_TAG_ENV_VAR] = tag
    os.environ[CORPUS_TARGET_ENV_VAR] = str(target)
    os.environ[CORPUS_BUILD_SINCE_ENV_VAR] = build_started.isoformat()
    # Use the smallest scaled per-strategy target as the per-strategy cb floor
    # so no single strategy can monopolise the corpus cap. With
    # release_v1 (target=6500, cb_quota=0.50) this gives template a 325-slot
    # cap and the larger strategies inherit the same floor — total potential
    # cb-tagged ≤ 5 × 325 = 1625 (well under the 3250 corpus cap).
    min_strat = min(scaled_targets.values())
    os.environ[STRATEGY_TARGET_ENV_VAR] = str(min_strat)
    logger.info(
        "orchestrator: tag={} target={} build_since={} per_strategy_cb_floor={}",
        tag, target, build_started.isoformat(), min_strat,
    )

    try:
        existing_by_method = _count_by_method(tag=tag) if resume else {}
        existing_dgc = get_domain_generator_counts(tag=tag) if resume else {}

        total_existing = sum(existing_by_method.values()) if resume else 0
        if resume:
            click.echo(f"Resuming from {total_existing:,} existing questions")
        else:
            click.echo("Starting fresh generation run")

        workers = _resolve_max_workers(max_workers)
        s_workers = _resolve_strategy_workers(strategy_workers)
        click.echo(
            f"Target: {target:,} questions | tag={tag or '<none>'} | "
            f"dry_run={dry_run} | max_workers={workers} | strategy_workers={s_workers}\n"
        )

        # Phase 2j: per-strategy multi-pass.
        #
        # The first multi-pass implementation (commit c5a4369) wrapped the
        # entire strategy-dispatch in an outer pass loop, which serialised
        # all 5 strategies on a single pass barrier. In practice, FTQ
        # (target 2,925) ran for >2h on pass 1 while the other 4 strategies
        # had completed their pass-1 cells in 20 min and sat idle. The
        # per-strategy refactor here lets each strategy thread run its
        # own multi-pass loop independently — when template/comparative/
        # scenario complete pass 1 in 5-15 min, they immediately retry
        # with fresh fact samples instead of waiting for FTQ.
        max_passes = max(1, int(os.environ.get(
            "OENOBENCH_MAX_GENERATE_PASSES", "5",
        )))

        def _run_one_strategy(strategy: str) -> None:
            strategy_target = scaled_targets[strategy]
            module = STRATEGY_MODULES[strategy]
            zero_streak = 0
            for pass_idx in range(1, max_passes + 1):
                # Re-resolve THIS strategy's existing count + per-cell
                # generator counts so each pass dispatches against the
                # current DB state.
                existing_for_strategy = _count_by_method(tag=tag).get(strategy, 0)
                existing_dgc_local = get_domain_generator_counts(tag=tag)
                remaining = max(0, strategy_target - existing_for_strategy)
                if remaining == 0:
                    click.echo(
                        f"[{strategy}] Target reached "
                        f"({existing_for_strategy:,}/{strategy_target:,}) "
                        f"after pass {pass_idx - 1}/{max_passes}"
                    )
                    return

                click.echo(
                    f"[{strategy}] pass {pass_idx}/{max_passes} | "
                    f"{existing_for_strategy:,}/{strategy_target:,} "
                    f"(remaining {remaining:,})"
                )
                pre_count = existing_for_strategy

                if strategy not in LLM_STRATEGIES:
                    _dispatch_template(
                        module, remaining, dry_run,
                        max_workers=workers, total_target=target,
                    )
                else:
                    _dispatch_llm_strategy(
                        strategy, module, remaining, existing_dgc_local,
                        dry_run, max_workers=workers, total_target=target,
                    )

                post_count = _count_by_method(tag=tag).get(strategy, 0)
                produced = post_count - pre_count
                click.echo(
                    f"[{strategy}] pass {pass_idx} produced {produced:,} "
                    f"(now {post_count:,}/{strategy_target:,})"
                )
                if produced == 0:
                    zero_streak += 1
                    if zero_streak >= 2:
                        click.echo(
                            f"[{strategy}] {zero_streak} zero-progress passes — stopping"
                        )
                        return
                else:
                    zero_streak = 0
            click.echo(
                f"[{strategy}] hit max_passes={max_passes} cap "
                f"at {_count_by_method(tag=tag).get(strategy, 0):,}/{strategy_target:,}"
            )

        if s_workers <= 1:
            for strategy in STRATEGY_ORDER:
                _run_one_strategy(strategy)
        else:
            logger.info(
                "orchestrator: dispatching {} strategies concurrently "
                "(strategy_workers={}, max_passes={})",
                len(STRATEGY_ORDER), s_workers, max_passes,
            )
            with cf.ThreadPoolExecutor(max_workers=s_workers) as ex:
                futures = {ex.submit(_run_one_strategy, s): s for s in STRATEGY_ORDER}
                for fut in cf.as_completed(futures):
                    strategy = futures[fut]
                    try:
                        fut.result()
                    except Exception as e:  # noqa: BLE001
                        logger.error(
                            "orchestrator: top-level strategy {} raised: {}",
                            strategy, e,
                        )

        click.echo("\nGeneration pipeline complete.")
    finally:
        set_corpus_target(None)
        for k, v in prev_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _dispatch_template(
    module: str, count: int, dry_run: bool,
    max_workers: int = 1, total_target: int = OVERALL_TARGET,
):
    """Run template generator for the given count across all domains.

    Phase 2g.10 (Team Delta A2 + A3): dispatches in-process via
    ``_run_strategy`` and optionally parallelises over domains via a
    ThreadPoolExecutor when ``max_workers > 1``.

    ``total_target`` is accepted for signature parity with
    ``_dispatch_llm_strategy``. Domain proportions are derived from
    ``DOMAIN_TARGETS / OVERALL_TARGET`` (which sums to 1.0 by construction)
    so the project-plan ratios hold regardless of corpus size.
    """
    cells: list[tuple[str, int]] = []
    for domain in sorted(DOMAIN_TARGETS.keys()):
        # Proportional split based on domain targets
        domain_share = DOMAIN_TARGETS[domain] / OVERALL_TARGET
        domain_count = max(1, int(count * domain_share))
        cells.append((domain, domain_count))

    if max_workers <= 1:
        for domain, domain_count in cells:
            _run_strategy(module, domain=domain, count=domain_count, dry_run=dry_run)
        return

    with cf.ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = [
            ex.submit(_run_strategy, module, domain=d, count=c, dry_run=dry_run)
            for d, c in cells
        ]
        for fut in cf.as_completed(futures):
            try:
                fut.result()
            except Exception as e:  # noqa: BLE001
                logger.error("orchestrator: template cell raised: {}", e)


def _dispatch_llm_strategy(
    strategy: str,
    module: str,
    total_remaining: int,
    existing_dgc: dict,
    dry_run: bool,
    max_workers: int = 1,
    total_target: int = OVERALL_TARGET,
):
    """Dispatch an LLM strategy across generators and domains.

    Phase 2g.10 (Team Delta A3): cell dispatch parallelised via a
    ThreadPoolExecutor when ``max_workers > 1``. Default 1 keeps the
    full-gen run sequential.
    """
    generators = list(GENERATOR_TARGETS.keys())
    per_generator = max(1, total_remaining // len(generators))

    cells: list[tuple[str, str, int]] = []  # (domain, generator, count)
    for generator in generators:
        # Check per-generator quota
        gen_existing = sum(
            cnt for (dom, gen, meth), cnt in existing_dgc.items()
            if gen == generator and meth == strategy
        )
        gen_remaining = max(0, per_generator - gen_existing)
        if gen_remaining == 0:
            logger.info(
                "Generator {} at quota for strategy {}, skipping",
                generator, strategy,
            )
            continue

        # Split across domains proportionally
        for domain in sorted(DOMAIN_TARGETS.keys()):
            domain_share = DOMAIN_TARGETS[domain] / OVERALL_TARGET
            domain_count = max(1, int(gen_remaining * domain_share))
            cells.append((domain, generator, domain_count))

    if max_workers <= 1:
        for domain, generator, count in cells:
            _run_strategy(
                module, domain=domain, count=count,
                generator=generator, dry_run=dry_run,
            )
        return

    with cf.ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = [
            ex.submit(
                _run_strategy, module,
                domain=d, count=c, generator=g, dry_run=dry_run,
            )
            for d, g, c in cells
        ]
        for fut in cf.as_completed(futures):
            try:
                fut.result()
            except Exception as e:  # noqa: BLE001
                logger.error("orchestrator: {} cell raised: {}", strategy, e)


# ─── dedup ────────────────────────────────────────────────────────────────────


@cli.command()
@click.option("--threshold", type=float, default=0.92, help="Similarity threshold")
@click.option("--delete", "do_delete", is_flag=True, help="Delete duplicates (with confirmation)")
def dedup(threshold, do_delete):
    """Run deduplication pass on all draft questions."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    logger.add(LOG_DIR / f"orchestrator_{timestamp}.log", rotation="50 MB")

    click.echo(f"Running deduplication pass (threshold={threshold})...")
    pairs = run_dedup_pass(threshold)

    if not pairs:
        click.echo("No duplicate pairs found.")
        return

    click.echo(f"\nFound {len(pairs)} duplicate pairs above threshold {threshold}:")
    for q1, q2, sim in pairs[:20]:
        click.echo(f"  {q1[:8]}... <-> {q2[:8]}...  similarity={sim:.4f}")
    if len(pairs) > 20:
        click.echo(f"  ... and {len(pairs) - 20} more")

    if do_delete:
        # Collect the second question from each pair for deletion
        to_delete = list({q2 for _, q2, _ in pairs})
        if click.confirm(f"\nDelete {len(to_delete)} duplicate questions?"):
            from src.generators._question_db import delete_questions_by_ids
            deleted = delete_questions_by_ids(to_delete)
            click.echo(f"Deleted {deleted} questions")
        else:
            click.echo("Aborted.")


# ─── embed ────────────────────────────────────────────────────────────────────


@cli.command()
def embed():
    """Compute and store embeddings for questions missing them."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    logger.add(LOG_DIR / f"orchestrator_{timestamp}.log", rotation="50 MB")

    conn = get_pg()
    cur = conn.cursor()
    cur.execute("SELECT id FROM questions WHERE embedding IS NULL")
    rows = cur.fetchall()
    ids = [str(r["id"]) for r in rows]

    if not ids:
        click.echo("All questions already have embeddings.")
        return

    click.echo(f"Computing embeddings for {len(ids)} questions...")

    # Process in batches of 50
    total_embedded = 0
    for i in range(0, len(ids), 50):
        batch = ids[i : i + 50]
        embedded = batch_embed_and_store(batch)
        total_embedded += embedded
        click.echo(f"  Batch {i // 50 + 1}: embedded {embedded}/{len(batch)}")

    click.echo(f"\nDone: embedded {total_embedded}/{len(ids)} questions.")


# ─── validate ─────────────────────────────────────────────────────────────────


@cli.command()
def validate():
    """Run comprehensive quality checks on all generated questions."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    logger.add(LOG_DIR / f"orchestrator_{timestamp}.log", rotation="50 MB")

    conn = get_pg()
    cur = conn.cursor()

    click.echo(f"\n{'=' * 50}")
    click.echo("  OenoBench Question Validation Report")
    click.echo(f"{'=' * 50}\n")

    # 1. Total by status
    cur.execute(
        "SELECT status, count(*) AS cnt FROM questions GROUP BY status ORDER BY status"
    )
    rows = cur.fetchall()
    click.echo("Questions by status:")
    for r in rows:
        click.echo(f"  {r['status']:20s} {r['cnt']:>6,}")
    total = sum(r["cnt"] for r in rows)
    click.echo(f"  {'TOTAL':20s} {total:>6,}")

    # 2. Domain distribution vs targets
    by_domain = _count_by_domain()
    click.echo("\nDomain distribution vs targets:")
    for domain in sorted(DOMAIN_TARGETS.keys()):
        have = by_domain.get(domain, 0)
        want = DOMAIN_TARGETS[domain]
        pct = (have / want * 100) if want else 0
        click.echo(f"  {domain:20s} {have:>5,} / {want:,} ({pct:.0f}%)")

    # 3. Generator distribution vs targets
    by_gen = _count_by_generator()
    click.echo("\nGenerator distribution vs targets:")
    for gen in sorted(GENERATOR_TARGETS.keys()):
        have = by_gen.get(gen, 0)
        want = GENERATOR_TARGETS[gen]
        pct = (have / want * 100) if want else 0
        click.echo(f"  {gen:20s} {have:>5,} / {want:,} ({pct:.0f}%)")
    tmpl = by_gen.get("template_engine", 0)
    click.echo(f"  {'template_engine':20s} {tmpl:>5,} / {STRATEGY_TARGETS['template']:,}")

    # 4. Strategy distribution vs targets
    by_method = _count_by_method()
    click.echo("\nStrategy distribution vs targets:")
    for strategy in STRATEGY_ORDER:
        have = by_method.get(strategy, 0)
        want = STRATEGY_TARGETS[strategy]
        pct = (have / want * 100) if want else 0
        click.echo(f"  {strategy:20s} {have:>5,} / {want:,} ({pct:.0f}%)")

    # 5. Difficulty distribution
    cur.execute(
        "SELECT difficulty, count(*) AS cnt FROM questions GROUP BY difficulty ORDER BY difficulty"
    )
    rows = cur.fetchall()
    click.echo("\nDifficulty distribution:")
    for r in rows:
        click.echo(f"  Level {r['difficulty']:5s} {r['cnt']:>6,}")

    # 6. Question type distribution
    cur.execute(
        "SELECT question_type, count(*) AS cnt FROM questions GROUP BY question_type ORDER BY cnt DESC"
    )
    rows = cur.fetchall()
    click.echo("\nQuestion type distribution:")
    for r in rows:
        click.echo(f"  {r['question_type']:20s} {r['cnt']:>6,}")

    # 7. Missing fields
    cur.execute(
        "SELECT count(*) AS cnt FROM questions "
        "WHERE explanation IS NULL OR explanation = ''"
    )
    no_expl = cur.fetchone()["cnt"]
    cur.execute(
        "SELECT count(*) AS cnt FROM questions "
        "WHERE question_type IN ('multiple_choice', 'multiple_select', 'true_false') "
        "  AND (options IS NULL OR options = '[]'::jsonb)"
    )
    no_opts = cur.fetchone()["cnt"]
    click.echo(f"\nQuality issues:")
    click.echo(f"  Missing explanations:  {no_expl:>6,}")
    click.echo(f"  Empty options (MC/TF): {no_opts:>6,}")

    # 8. Duplicate count (questions with embeddings that are very similar)
    cur.execute(
        "SELECT count(*) AS cnt FROM questions WHERE embedding IS NULL"
    )
    no_emb = cur.fetchone()["cnt"]
    click.echo(f"  Missing embeddings:    {no_emb:>6,}")

    # 9. Cognitive dimension distribution
    cur.execute(
        "SELECT cognitive_dim, count(*) AS cnt FROM questions GROUP BY cognitive_dim ORDER BY cnt DESC"
    )
    rows = cur.fetchall()
    click.echo("\nCognitive dimension distribution:")
    for r in rows:
        click.echo(f"  {r['cognitive_dim']:20s} {r['cnt']:>6,}")

    # 10. Random sample
    cur.execute(
        """
        SELECT q.question_id, q.question_text, q.correct_answer,
               q.domain, q.question_type, q.difficulty, q.status,
               gm.generator, gm.generation_method
        FROM questions q
        JOIN generation_metadata gm ON gm.question_id = q.id
        ORDER BY random()
        LIMIT 10
        """
    )
    samples = cur.fetchall()
    if samples:
        click.echo(f"\nRandom sample ({len(samples)} questions):")
        for s in samples:
            click.echo(f"\n  [{s['question_id']}] {s['domain']} | {s['question_type']} | "
                        f"diff={s['difficulty']} | {s['generator']}/{s['generation_method']} | "
                        f"status={s['status']}")
            click.echo(f"  Q: {s['question_text'][:120]}")
            click.echo(f"  A: {s['correct_answer']}")

    click.echo(f"\n{'=' * 50}")
    click.echo("  Validation complete.")
    click.echo(f"{'=' * 50}\n")


# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    cli()
