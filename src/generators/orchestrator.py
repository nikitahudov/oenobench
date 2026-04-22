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

import subprocess
import sys
from datetime import datetime
from pathlib import Path

import click
from loguru import logger

from src.generators._dedup import batch_embed_and_store, run_dedup_pass
from src.generators._fact_sampler import DOMAIN_TARGETS, get_domain_stats
from src.generators._llm_client import GENERATOR_MODELS
from src.generators._question_db import (
    get_domain_generator_counts,
    get_question_count,
    get_used_fact_ids,
)
from src.utils.db import get_pg

# ─── Logging setup ────────────────────────────────────────────────────────────

LOG_DIR = Path("data/logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)

# ─── Quota targets ────────────────────────────────────────────────────────────

OVERALL_TARGET = 10_000

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
    "claude": 2400,
    "chatgpt": 2400,
    "gemini": 2800,
    "qwen": 800,
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


def _count_by_method() -> dict[str, int]:
    """Return {generation_method: count} across all questions."""
    conn = get_pg()
    cur = conn.cursor()
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
    """Run a generator module as a subprocess. Returns True on success."""
    cmd = [sys.executable, "-m", f"src.generators.{module}"] + args
    if dry_run:
        cmd.append("--dry-run")
    logger.info("Running: {}", " ".join(cmd))
    result = subprocess.run(cmd)
    if result.returncode != 0:
        logger.error("Command failed with exit code {}: {}", result.returncode, " ".join(cmd))
        return False
    return True


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

    # Fact coverage
    click.echo("\nFact Coverage:")
    click.echo(f"  Total facts:        {total_facts:>10,}")
    click.echo(f"  Facts used:         {len(used_facts):>10,}")
    coverage_pct = (len(used_facts) / total_facts * 100) if total_facts else 0
    click.echo(f"  Coverage:           {coverage_pct:>9.1f}%")

    click.echo()


# ─── generate-all ─────────────────────────────────────────────────────────────


@cli.command("generate-all")
@click.option("--target", type=int, default=OVERALL_TARGET, help="Total questions to generate")
@click.option("--resume", is_flag=True, help="Resume from current DB state")
@click.option("--dry-run", is_flag=True, help="Preview without DB writes")
def generate_all(target, resume, dry_run):
    """Run full generation pipeline across all strategies/models/domains."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    logger.add(LOG_DIR / f"orchestrator_{timestamp}.log", rotation="50 MB")

    existing_by_method = _count_by_method() if resume else {}
    existing_dgc = get_domain_generator_counts() if resume else {}

    total_existing = sum(existing_by_method.values()) if resume else 0
    if resume:
        click.echo(f"Resuming from {total_existing:,} existing questions")
    else:
        click.echo("Starting fresh generation run")

    click.echo(f"Target: {target:,} questions | dry_run={dry_run}\n")

    for strategy in STRATEGY_ORDER:
        strategy_target = STRATEGY_TARGETS[strategy]
        existing_for_strategy = existing_by_method.get(strategy, 0)
        remaining = max(0, strategy_target - existing_for_strategy)

        if remaining == 0:
            click.echo(f"[{strategy}] Target reached ({existing_for_strategy:,}/{strategy_target:,}), skipping")
            continue

        click.echo(f"[{strategy}] Generating {remaining:,} questions "
                    f"({existing_for_strategy:,}/{strategy_target:,} exist)")

        module = STRATEGY_MODULES[strategy]

        if strategy not in LLM_STRATEGIES:
            # Template strategy: single run, no generator split
            _dispatch_template(module, remaining, dry_run)
        else:
            # LLM strategies: split across generators and domains
            _dispatch_llm_strategy(
                strategy, module, remaining, existing_dgc, dry_run,
            )

    click.echo("\nGeneration pipeline complete.")


def _dispatch_template(module: str, count: int, dry_run: bool):
    """Run template generator for the given count across all domains."""
    for domain in sorted(DOMAIN_TARGETS.keys()):
        # Proportional split based on domain targets
        domain_share = DOMAIN_TARGETS[domain] / OVERALL_TARGET
        domain_count = max(1, int(count * domain_share))
        args = ["--domain", domain, "--count", str(domain_count)]
        _run_subprocess(module, args, dry_run)


def _dispatch_llm_strategy(
    strategy: str,
    module: str,
    total_remaining: int,
    existing_dgc: dict,
    dry_run: bool,
):
    """Dispatch an LLM strategy across generators and domains."""
    generators = list(GENERATOR_TARGETS.keys())
    per_generator = max(1, total_remaining // len(generators))

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

            args = [
                "--domain", domain,
                "--count", str(domain_count),
                "--generator", generator,
            ]
            _run_subprocess(module, args, dry_run)


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
