"""OenoBench Audit Orchestrator (Phase 2c).

Single CLI entry point for the multi-agent quality audit:

    python -m src.qa.orchestrator build-corpus --per-strategy 120
    python -m src.qa.orchestrator export-gold --size 60
    python -m src.qa.orchestrator import-gold --csv-path ... --reviewer ...
    python -m src.qa.orchestrator run-team-a --tag audit_pilot_v1
    python -m src.qa.orchestrator run-team-b --tag audit_pilot_v1
    python -m src.qa.orchestrator run-team-c --tag audit_pilot_v1
    python -m src.qa.orchestrator run-team-d --tag audit_pilot_v1
    python -m src.qa.orchestrator run --tag audit_pilot_v1 --teams A,B,C,D
    python -m src.qa.orchestrator aggregate --run-id <uuid>
    python -m src.qa.orchestrator build-reports --run-id <uuid>
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import click
from loguru import logger

from src.qa._corpus import (
    build_pilot_corpus,
    export_gold_sheet,
    import_gold_sheet,
    promote_from_reserve,
)
from src.qa._findings import (
    ALL_SEVERITIES,
    complete_run,
    compute_config_hash,
    create_run,
    fetch_corpus_questions,
    fetch_findings,
    find_existing,
    get_run,
    latest_run_for_tag,
    write_findings_bulk,
)
from src.qa.agents.team_a_static import ALL_A_AGENTS, run_team_a
from src.qa.agents.team_b_validity import (
    B1_ID,
    B1_VERSION,
    B2_ID,
    B2_VERSION,
    run_team_b,
)
from src.qa.agents.team_c_probes import (
    C2_ID,
    C2_VERSION,
    C4_ID,
    C4_VERSION,
    run_c4_difficulty_audit,
    run_team_c,
)
from src.qa.agents.team_d_population import (
    D1_ID,
    D1_VERSION,
    D3_ID,
    D3_VERSION,
    run_team_d,
)

LOG_DIR = Path("data/logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_TAG = "audit_pilot_v1"
DEFAULT_SEED = 42

# Aggregated agent registry for config hashing.
AGENT_REGISTRY = {
    **ALL_A_AGENTS,
    B1_ID: B1_VERSION,
    B2_ID: B2_VERSION,
    C2_ID: C2_VERSION,
    C4_ID: C4_VERSION,
    D1_ID: D1_VERSION,
    D3_ID: D3_VERSION,
}

JUDGE_MODELS = ["claude", "chatgpt", "gemini"]

DEFAULT_THRESHOLDS = {
    "a3_fail_lcs": 0.60,
    "a3_fail_ngram": 8,
    "a4_fail_auc": 0.95,
    "b2_leakage_ratio": 0.67,
    "d1_sp_fail_delta": 0.15,
    "d3_country_fail_ratio": 2.0,
}


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _setup_logging() -> None:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    logger.add(LOG_DIR / f"qa_audit_{ts}.log", rotation="50 MB")


def _get_or_create_run(tag: str, seed: int, size: int | None) -> str:
    config_hash = compute_config_hash(
        agent_versions=AGENT_REGISTRY,
        model_ids=JUDGE_MODELS,
        seed=seed,
        thresholds=DEFAULT_THRESHOLDS,
    )
    existing = latest_run_for_tag(tag)
    if existing and existing.get("config_hash") == config_hash and not existing.get("completed_at"):
        logger.info("Resuming run {} (tag={}, hash={}...)",
                    existing["id"], tag, config_hash[:8])
        return str(existing["id"])
    run_id = create_run(
        corpus_tag=tag,
        corpus_size=size or 0,
        config_hash=config_hash,
        seed=seed,
        metadata={"agents": AGENT_REGISTRY, "judges": JUDGE_MODELS},
    )
    return run_id


def _load_corpus(tag: str) -> list[dict]:
    rows = fetch_corpus_questions(tag)
    if not rows:
        raise click.ClickException(
            f"No questions tagged {tag}. Run `build-corpus` first."
        )
    logger.info("Loaded {} questions tagged {}", len(rows), tag)
    return rows


def _make_skip_checker(run_id: str):
    """Closure that answers: has (qid, agent) already been recorded?"""
    def _check(qid: str, agent_id: str) -> bool:
        version = AGENT_REGISTRY.get(agent_id)
        if not version:
            return False
        return bool(find_existing(run_id, qid, agent_id, version))
    return _check


# ─── CLI ──────────────────────────────────────────────────────────────────────


@click.group()
def cli() -> None:
    """OenoBench Audit Orchestrator."""


# ─── Corpus commands (delegate to _corpus) ───────────────────────────────────


@cli.command("build-corpus")
@click.option("--tag", default=DEFAULT_TAG)
@click.option("--per-strategy", default=120, type=int)
@click.option("--seed", default=DEFAULT_SEED, type=int)
@click.option("--skip", multiple=True)
@click.option(
    "--per-country-cap",
    type=float,
    default=None,
    help=(
        "Per-call absolute country cap (fraction in (0, 1]) forwarded to "
        "every strategy subprocess. Phase 2g.8 wire-up fix: audit_pilot_v6 "
        "ran with NO cap (D3 = 4.52) because this kwarg was not plumbed "
        "from the orchestrator down to the samplers. Pass 0.10 for audit "
        "pilots; default unset (no cap)."
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
def build_corpus_cmd(
    tag: str, per_strategy: int, seed: int,
    skip: tuple[str, ...], per_country_cap: float | None,
    max_workers: int | None,
    strategy_workers: int | None,
) -> None:
    _setup_logging()
    result = build_pilot_corpus(
        tag=tag,
        per_strategy=per_strategy,
        seed=seed,
        skip_strategies=skip,
        per_country_cap=per_country_cap,
        max_workers=max_workers,
        strategy_workers=strategy_workers,
    )
    click.echo(f"Built corpus tag={result['tag']} totals={result['totals']}")


@cli.command("export-gold")
@click.option("--tag", default=DEFAULT_TAG)
@click.option("--out", type=click.Path(), default="data/reports/gold_sheet.csv")
@click.option("--size", default=60, type=int)
@click.option("--seed", default=DEFAULT_SEED, type=int)
@click.option("--include-reserve", is_flag=True, default=False,
              help="Include cb_reserve questions in the export.")
def export_gold_cmd(tag: str, out: str, size: int, seed: int, include_reserve: bool) -> None:
    _setup_logging()
    n = export_gold_sheet(tag, Path(out), size, seed, include_reserve=include_reserve)
    click.echo(f"Wrote {n} rows to {out}")


@cli.command("import-gold")
@click.option("--csv-path", type=click.Path(exists=True), required=True)
@click.option("--reviewer", required=True)
def import_gold_cmd(csv_path: str, reviewer: str) -> None:
    _setup_logging()
    n = import_gold_sheet(Path(csv_path), reviewer)
    click.echo(f"Imported {n} labels")


# ─── Per-team runners ────────────────────────────────────────────────────────


def _run_team(team_letter: str, tag: str, seed: int, extras: dict | None = None) -> str:
    questions = _load_corpus(tag)
    run_id = _get_or_create_run(tag, seed, size=len(questions))
    skip = _make_skip_checker(run_id)

    findings: list[dict] = []
    if team_letter == "A":
        findings = run_team_a(run_id, questions)
    elif team_letter == "B":
        # Team B writes incrementally so the run can be monitored / resumed.
        from src.qa._findings import write_finding as _write_finding

        inline_count = 0
        def _inline(f: dict) -> None:
            nonlocal inline_count
            try:
                _write_finding(**f)
                inline_count += 1
            except Exception as exc:
                logger.error("inline write failed: {}", exc)
        run_team_b(run_id, questions, skip_existing_checker=skip, write_finding_fn=_inline)
        click.echo(f"Team B: wrote {inline_count} findings inline (run_id={run_id})")
        return run_id
    elif team_letter == "C":
        include_c4 = bool((extras or {}).get("include_c4", False))
        if include_c4:
            # Run C2 (deterministic) immediately, then C4 with inline writes
            # so progress on the LLM-bound pass is monitorable / resumable.
            from src.qa._findings import write_finding as _write_finding

            c2_findings = run_team_c(run_id, questions, include_c4=False)
            inserted_c2 = write_findings_bulk(c2_findings)

            inline_count = 0
            def _inline_c4(f: dict) -> None:
                nonlocal inline_count
                try:
                    _write_finding(**f)
                    inline_count += 1
                except Exception as exc:
                    logger.error("C4 inline write failed: {}", exc)
            run_c4_difficulty_audit(
                run_id,
                questions,
                skip_existing_checker=skip,
                write_finding_fn=_inline_c4,
            )
            click.echo(
                f"Team C: wrote {inserted_c2} C2 findings + {inline_count} C4 findings inline "
                f"(run_id={run_id})"
            )
            return run_id
        findings = run_team_c(run_id, questions, include_c4=False)
    elif team_letter == "D":
        findings = run_team_d(
            run_id,
            questions,
            seed=seed,
            d1_sample=(extras or {}).get("d1_sample", 10),
        )
    else:
        raise click.BadParameter(f"Unknown team: {team_letter}")

    inserted = write_findings_bulk(findings)
    click.echo(f"Team {team_letter}: wrote {inserted}/{len(findings)} findings (run_id={run_id})")
    return run_id


@cli.command("run-team-a")
@click.option("--tag", default=DEFAULT_TAG)
@click.option("--seed", default=DEFAULT_SEED, type=int)
def run_team_a_cmd(tag: str, seed: int) -> None:
    _setup_logging()
    _run_team("A", tag, seed)


@cli.command("run-team-b")
@click.option("--tag", default=DEFAULT_TAG)
@click.option("--seed", default=DEFAULT_SEED, type=int)
def run_team_b_cmd(tag: str, seed: int) -> None:
    _setup_logging()
    _run_team("B", tag, seed)


@cli.command("run-team-c")
@click.option("--tag", default=DEFAULT_TAG)
@click.option("--seed", default=DEFAULT_SEED, type=int)
@click.option(
    "--include-c4",
    is_flag=True,
    default=False,
    help="Also run C4_DifficultyAudit (1 Gemini call/question; ~$0.001 each).",
)
def run_team_c_cmd(tag: str, seed: int, include_c4: bool) -> None:
    _setup_logging()
    _run_team("C", tag, seed, extras={"include_c4": include_c4})


@cli.command("run-team-c-c4")
@click.option("--tag", default=DEFAULT_TAG)
@click.option("--seed", default=DEFAULT_SEED, type=int)
def run_team_c_c4_cmd(tag: str, seed: int) -> None:
    """Run only C4_DifficultyAudit (skip C2). Useful for incremental top-ups."""
    _setup_logging()
    questions = _load_corpus(tag)
    run_id = _get_or_create_run(tag, seed, size=len(questions))
    skip = _make_skip_checker(run_id)

    from src.qa._findings import write_finding as _write_finding

    inline_count = 0
    def _inline(f: dict) -> None:
        nonlocal inline_count
        try:
            _write_finding(**f)
            inline_count += 1
        except Exception as exc:
            logger.error("C4 inline write failed: {}", exc)
    run_c4_difficulty_audit(
        run_id,
        questions,
        skip_existing_checker=skip,
        write_finding_fn=_inline,
    )
    click.echo(f"C4: wrote {inline_count} findings inline (run_id={run_id})")


@cli.command("run-team-d")
@click.option("--tag", default=DEFAULT_TAG)
@click.option("--seed", default=DEFAULT_SEED, type=int)
@click.option(
    "--d1-sample",
    default=10,
    type=int,
    help=(
        "Questions per (evaluator, author) pair. Phase 2g.18 cost-down: "
        "default lowered 20 → 10 (5×5×10 = 250 calls vs 500 corpus-wide). "
        "Population stat retains power for the self-pref delta; bump back "
        "to 20 if a future audit shows borderline self-pref signal."
    ),
)
def run_team_d_cmd(tag: str, seed: int, d1_sample: int) -> None:
    _setup_logging()
    _run_team("D", tag, seed, extras={"d1_sample": d1_sample})


@cli.command("run")
@click.option("--tag", default=DEFAULT_TAG)
@click.option("--seed", default=DEFAULT_SEED, type=int)
@click.option("--teams", default="A,B,C,D", help="Comma-separated team letters")
@click.option(
    "--d1-sample",
    default=10,
    type=int,
    help="Phase 2g.18 cost-down: default lowered 20 → 10.",
)
@click.option(
    "--include-c4",
    is_flag=True,
    default=False,
    help=(
        "Phase 2g.18 cost-down: C4 DifficultyAudit removed from default "
        "audit (~$10 saving on 10k). Pass this flag to opt back in; "
        "difficulty calibration is informational, not a Go gate."
    ),
)
def run_all_cmd(tag: str, seed: int, teams: str, d1_sample: int, include_c4: bool) -> None:
    """Run the full audit end-to-end and seal the run."""
    _setup_logging()
    letters = [t.strip().upper() for t in teams.split(",") if t.strip()]
    run_id = None
    for L in letters:
        if L == "D":
            extras = {"d1_sample": d1_sample}
        elif L == "C":
            extras = {"include_c4": include_c4}
        else:
            extras = None
        run_id = _run_team(L, tag, seed, extras=extras)
    if run_id:
        complete_run(run_id)
        click.echo(f"Audit complete for run {run_id}")


# ─── Inspection ──────────────────────────────────────────────────────────────


@cli.command("aggregate")
@click.option("--run-id", required=True)
def aggregate_cmd(run_id: str) -> None:
    """Print a compact roll-up of findings for a run (no file writes)."""
    _setup_logging()
    run = get_run(run_id)
    if not run:
        raise click.ClickException(f"run {run_id} not found")
    click.echo(f"Run: {run_id}  tag={run['corpus_tag']}  size={run['corpus_size']}")
    click.echo(f"Config hash: {run['config_hash'][:16]}...  seed={run['random_seed']}")

    all_findings = fetch_findings(run_id)
    by_agent: dict[str, dict] = {}
    for f in all_findings:
        a = by_agent.setdefault(f["agent_id"], {s: 0 for s in ALL_SEVERITIES})
        a[f["severity"]] = a.get(f["severity"], 0) + 1
    click.echo("\nAgent severity breakdown:")
    click.echo(f"  {'agent':<30}  pass   warn   fail   error")
    for agent, sev in sorted(by_agent.items()):
        click.echo(
            f"  {agent:<30}  {sev['pass']:>4}   {sev['warn']:>4}   {sev['fail']:>4}   {sev['error']:>4}"
        )


@cli.command("build-reports")
@click.option("--run-id", required=True)
@click.option("--audit-out", default="docs/QUALITY_AUDIT_REPORT.md")
@click.option(
    "--plan-out",
    default="docs/GENERATION_IMPROVEMENT_PLAN_AUTO.md",
    help=(
        "Auto-generated plan output. The CURATED plan lives at "
        "docs/GENERATION_IMPROVEMENT_PLAN.md and is hand-edited from "
        "the auto plan + gold review."
    ),
)
def build_reports_cmd(run_id: str, audit_out: str, plan_out: str) -> None:
    _setup_logging()
    from src.qa.reports.build_audit_report import render as render_audit
    from src.qa.reports.build_improvement_plan import render as render_plan
    render_audit(run_id, Path(audit_out))
    render_plan(run_id, Path(plan_out))
    click.echo(f"Wrote {audit_out} and {plan_out}")


@cli.command("promote-from-reserve")
@click.option("--tag", required=True, help="Tag that must be present on reserve questions.")
@click.option("--count", default=10, type=int, show_default=True,
              help="Maximum number of questions to promote.")
@click.option("--strategy", default=None,
              help="Optional generation_method filter (e.g. 'template_only').")
def promote_from_reserve_cmd(tag: str, count: int, strategy: str | None) -> None:
    """Promote up to COUNT questions from cb_reserve → draft.

    Finds questions tagged with TAG that have status='cb_reserve', optionally
    filtered to a single generation strategy, and updates them to status='draft'
    so they enter the active corpus accounting.
    """
    _setup_logging()
    n = promote_from_reserve(tag=tag, count=count, strategy=strategy)
    click.echo(f"Promoted {n} questions from cb_reserve → draft")


if __name__ == "__main__":
    cli()
