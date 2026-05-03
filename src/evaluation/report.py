"""
OenoBench Phase 5 — Evaluation Report Renderer
===============================================

CLI:
    python -m src.evaluation.report --tag eval_sample_v1 [--output PATH]

Renders a markdown report (stdout + file) with:
  - Header / run summary
  - Per-config summary (16 rows)
  - Per-config × per-domain accuracy (16 × 6)
  - Per-config × per-strategy accuracy (16 × 5)
  - Self-Preference Score (SPS) with bootstrap 95% CI
  - Reasoning-effect deltas with bootstrap 95% CI
  - Cost & wall ledger
"""

from __future__ import annotations

import math
import os
import sys
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from typing import Any

import click
import numpy as np

from src.evaluation.cb_split import CLOSED_BOOK_TAG

# ---------------------------------------------------------------------------
# Formatting helpers (pure, importable by tests)
# ---------------------------------------------------------------------------

DIFFICULTY_LEVELS = ["1", "2", "3", "4"]
DIFFICULTY_LABELS = {
    "1": "1 (easy)",
    "2": "2",
    "3": "3",
    "4": "4 (hardest)",
}

DOMAINS = [
    "wine_regions",
    "grape_varieties",
    "producers",
    "viticulture",
    "winemaking",
    "wine_business",
]

STRATEGIES = [
    "fact_to_question",
    "scenario_synthesis",
    "template",
    "comparative",
    "distractor_mining",
]

# Human-readable labels for markdown headers
DOMAIN_LABELS = {
    "wine_regions": "Wine Regions",
    "grape_varieties": "Grape Varieties",
    "producers": "Producers",
    "viticulture": "Viticulture",
    "winemaking": "Winemaking",
    "wine_business": "Wine Business",
}

STRATEGY_LABELS = {
    "fact_to_question": "FTQ",
    "scenario_synthesis": "Scenario",
    "template": "Template",
    "comparative": "Comparative",
    "distractor_mining": "Distractor",
}

# Mapping: generator enum value → config family (for SPS)
GENERATOR_TO_FAMILY = {
    "claude": "anthropic",
    "chatgpt": "openai",
    "gemini": "google",
    "llama": "meta",
    "qwen": "qwen",
    "template_only": None,
    "human_authored": None,
    "gpt4": "openai",
}


def fmt_pct(numerator: int, denominator: int) -> str:
    """Format accuracy as XX.X%; return '—' when denominator is 0."""
    if denominator == 0:
        return "—"
    return f"{100.0 * numerator / denominator:.1f}%"


def fmt_cost(cost: float | None) -> str:
    """Format cost as $X.XX; return '—' for None/NaN."""
    if cost is None or (isinstance(cost, float) and math.isnan(cost)):
        return "—"
    return f"${cost:.2f}"


def effective_cost(row: dict[str, Any]) -> float | None:
    """Return the authoritative cost for one answer row.

    Prefers ``or_cost_usd`` (OR's reported cost) when present and non-NULL;
    falls back to the locally-computed ``cost_usd`` otherwise.
    """
    or_cost = row.get("or_cost_usd")
    if or_cost is not None:
        return float(or_cost)
    local = row.get("cost_usd")
    if local is not None:
        return float(local)
    return None


def fmt_ms(ms: float | None) -> str:
    """Format latency in ms as integer string; return '—' for None."""
    if ms is None or (isinstance(ms, float) and math.isnan(ms)):
        return "—"
    return str(int(ms))


def fmt_tokens(n: int | None) -> str:
    """Format token count; return '—' for None."""
    if n is None:
        return "—"
    return str(n)


# ---------------------------------------------------------------------------
# Bootstrap CI helper (pure, importable by tests)
# ---------------------------------------------------------------------------


def bootstrap_ci(
    arr: np.ndarray,
    n_resamples: int = 1000,
    ci_level: float = 0.95,
    rng_seed: int = 42,
) -> tuple[float, float, float]:
    """
    Compute (mean, lower_bound, upper_bound) via bootstrap percentile CI.

    Parameters
    ----------
    arr : 1-D boolean/int array (1=correct, 0=incorrect)
    n_resamples : number of bootstrap resamples
    ci_level : confidence level (default 0.95)
    rng_seed : reproducibility seed

    Returns
    -------
    (mean, lo, hi) with lo <= mean <= hi
    """
    if len(arr) == 0:
        return (float("nan"), float("nan"), float("nan"))
    rng = np.random.default_rng(rng_seed)
    means = np.array(
        [rng.choice(arr, size=len(arr), replace=True).mean() for _ in range(n_resamples)]
    )
    alpha = 1.0 - ci_level
    lo = float(np.percentile(means, 100 * alpha / 2))
    hi = float(np.percentile(means, 100 * (1 - alpha / 2)))
    mean = float(arr.mean())
    return (mean, lo, hi)


# ---------------------------------------------------------------------------
# Pivot helpers (pure, importable by tests)
# ---------------------------------------------------------------------------


def pivot_accuracy(
    rows: list[dict[str, Any]],
    row_key: str,
    col_key: str,
    row_order: list[str],
    col_order: list[str],
) -> dict[tuple[str, str], tuple[int, int]]:
    """
    Build a pivot table of (correct_count, total_count) keyed by (row_val, col_val).

    Parameters
    ----------
    rows : list of dicts with keys including row_key, col_key, 'is_correct'
    row_key : column name for rows (e.g. 'config_name')
    col_key : column name for columns (e.g. 'domain')
    row_order, col_order : ordering for iteration

    Returns
    -------
    dict mapping (row_val, col_val) -> (correct, total)
    """
    counts: dict[tuple[str, str], list[int]] = {}
    for r in rows:
        rk = r.get(row_key)
        ck = r.get(col_key)
        if rk is None or ck is None:
            continue
        key = (rk, ck)
        if key not in counts:
            counts[key] = [0, 0]
        counts[key][1] += 1
        if r.get("is_correct"):
            counts[key][0] += 1
    result = {}
    for rv in row_order:
        for cv in col_order:
            pair = counts.get((rv, cv), [0, 0])
            result[(rv, cv)] = (pair[0], pair[1])
    return result


# ---------------------------------------------------------------------------
# Stub EvalConfig for when configs.py is not yet available
# ---------------------------------------------------------------------------


def _get_eval_configs() -> list[Any]:
    """
    Import EVAL_CONFIGS from src.evaluation.configs if available.
    Falls back to an empty list; report sections needing configs will note the gap.
    """
    try:
        from src.evaluation.configs import EVAL_CONFIGS  # type: ignore[import]
        return list(EVAL_CONFIGS)
    except ImportError:
        return []


# ---------------------------------------------------------------------------
# Database query helpers
# ---------------------------------------------------------------------------


def _resolve_run(conn, tag: str) -> dict[str, Any]:
    """
    Return the most-recent evaluation_run row for the given tag.
    Raises SystemExit if not found.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, started_at, completed_at, metadata,
                   total_cost_usd, total_questions, correct_count
            FROM evaluation_runs
            WHERE metadata->>'tag' = %s
            ORDER BY started_at DESC
            LIMIT 1
            """,
            (tag,),
        )
        row = cur.fetchone()
    if row is None:
        click.echo(f"ERROR: No evaluation_run found with tag='{tag}'.", err=True)
        sys.exit(1)
    return dict(row)


def _load_answers(conn, run_id: str, corpus_schema: str) -> list[dict[str, Any]]:
    """
    Load all evaluation_answers for run_id, joined to {corpus_schema}.questions
    for domain, tags, difficulty, and generation_method (strategy).
    Also joins {corpus_schema}.generation_metadata to obtain the generator enum
    for SPS.  Both ``sample`` and ``public`` schemas expose the same relevant
    columns, so the join is unconditional.
    """
    genmeta_join = (
        f"LEFT JOIN {corpus_schema}.generation_metadata gm ON gm.question_id = q.id"
    )
    genmeta_select = "gm.generator::text AS generator"
    strategy_select = "gm.generation_method::text AS strategy"

    sql = f"""
        SELECT
            a.id,
            a.run_id,
            a.question_id,
            a.model_name,
            a.is_correct,
            a.parsed_answer,
            a.input_tokens,
            a.output_tokens,
            a.reasoning_tokens,
            a.cost_usd,
            a.or_cost_usd,
            a.or_provider,
            a.latency_ms,
            a.response_time_ms,
            a.reasoning_config,
            a.provider_used,
            q.domain::text AS domain,
            q.tags,
            q.difficulty::text AS difficulty,
            {strategy_select},
            {genmeta_select}
        FROM evaluation_answers a
        JOIN {corpus_schema}.questions q ON q.id = a.question_id
        {genmeta_join}
        WHERE a.run_id = %s
    """
    with conn.cursor() as cur:
        cur.execute(sql, (run_id,))
        rows = cur.fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Report section renderers
# ---------------------------------------------------------------------------


def _section_header(buf: StringIO, run: dict, answers: list[dict], tag: str, corpus: str) -> None:
    configs = _get_eval_configs()
    n_configs = len(configs) if configs else "?"
    total_q = len({r["question_id"] for r in answers})
    total_calls = len(answers)
    # Use effective cost (prefers OR-authoritative when present) for the header total.
    total_cost = sum(c for c in (effective_cost(r) for r in answers) if c is not None)
    started = run.get("started_at")
    completed = run.get("completed_at")
    wall = "—"
    if started and completed:
        delta = completed - started
        total_secs = int(delta.total_seconds())
        wall = f"{total_secs // 60}m {total_secs % 60}s"

    buf.write(f"# OenoBench Evaluation Report\n\n")
    buf.write(f"**Tag:** `{tag}`  \n")
    buf.write(f"**Run ID:** `{run['id']}`  \n")
    buf.write(f"**Corpus:** `{corpus}`  \n")
    buf.write(f"**Started:** {started}  \n")
    buf.write(f"**Completed:** {completed}  \n")
    buf.write(f"**Wall time:** {wall}  \n")
    buf.write(f"**Total questions:** {total_q}  \n")
    buf.write(f"**Total LLM calls:** {total_calls}  \n")
    buf.write(f"**Total cost (effective):** {fmt_cost(total_cost if total_cost else None)}  \n")
    buf.write(f"**Config slate:** {n_configs} configs  \n")
    buf.write("\n---\n\n")


def _section_per_config_summary(buf: StringIO, answers: list[dict]) -> None:
    """Section 1: Per-config summary table (16 rows)."""
    configs = _get_eval_configs()

    # Group answers by model_name
    by_config: dict[str, list[dict]] = {}
    for r in answers:
        mn = r.get("model_name") or "unknown"
        by_config.setdefault(mn, []).append(r)

    # Determine ordering: if configs available, use slot order; else alphabetical
    if configs:
        order = [c.model_id for c in configs if c.model_id in by_config]
        # append any unexpected names
        for name in sorted(by_config):
            if name not in order:
                order.append(name)
    else:
        order = sorted(by_config)

    buf.write("## 1. Per-Config Summary\n\n")
    buf.write(
        "| Slot | Config | Family | Reasoning | Accuracy | Parse % "
        "| p50 lat (ms) | p95 lat (ms) "
        "| Tokens in | Tokens out | Tokens reason | Cost |\n"
    )
    buf.write(
        "|---:|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|\n"
    )

    config_map: dict[str, Any] = {}
    if configs:
        config_map = {c.model_id: c for c in configs}

    for name in order:
        rows = by_config[name]
        cfg = config_map.get(name)
        slot = cfg.slot if cfg else "—"
        family = cfg.family if cfg else "—"
        reasoning = cfg.reasoning_mode if cfg else "—"
        if reasoning is None:
            reasoning = "standard"

        total = len(rows)
        correct = sum(1 for r in rows if r.get("is_correct"))
        parsed = sum(1 for r in rows if r.get("parsed_answer") and r["parsed_answer"].strip())
        accuracy_str = fmt_pct(correct, total)
        parse_str = fmt_pct(parsed, total)

        # latency: prefer latency_ms, fall back to response_time_ms
        lat_vals = [
            r.get("latency_ms") or r.get("response_time_ms")
            for r in rows
            if (r.get("latency_ms") or r.get("response_time_ms")) is not None
        ]
        if lat_vals:
            p50 = fmt_ms(float(np.percentile(lat_vals, 50)))
            p95 = fmt_ms(float(np.percentile(lat_vals, 95)))
        else:
            p50 = p95 = "—"

        in_tok = sum(r["input_tokens"] for r in rows if r.get("input_tokens") is not None)
        out_tok = sum(r["output_tokens"] for r in rows if r.get("output_tokens") is not None)
        reason_tok = sum(r["reasoning_tokens"] for r in rows if r.get("reasoning_tokens") is not None)
        # Use effective cost (OR-authoritative when available, local otherwise).
        cost = sum(c for c in (effective_cost(r) for r in rows) if c is not None)

        display = cfg.name if cfg else name
        buf.write(
            f"| {slot} | {display} | {family} | {reasoning} "
            f"| {accuracy_str} | {parse_str} "
            f"| {p50} | {p95} "
            f"| {fmt_tokens(in_tok or None)} "
            f"| {fmt_tokens(out_tok or None)} "
            f"| {fmt_tokens(reason_tok or None)} "
            f"| {fmt_cost(cost or None)} |\n"
        )

    buf.write("\n")

    # OR-cost coverage note (shown immediately after the per-config table).
    or_rows = sum(1 for r in answers if r.get("or_cost_usd") is not None)
    total_rows = len(answers)
    if total_rows > 0:
        pct = 100.0 * or_rows / total_rows
        buf.write(
            f"*OR-authoritative cost is available for {pct:.0f}% of rows"
            f" ({or_rows:,}/{total_rows:,}); remaining use locally-computed cost.*\n\n"
        )
    else:
        buf.write("*No answer rows found for this run.*\n\n")


def _section_config_domain(buf: StringIO, answers: list[dict]) -> None:
    """Section 2: Per-config × per-domain accuracy grid."""
    configs = _get_eval_configs()

    by_config: dict[str, list[dict]] = {}
    for r in answers:
        mn = r.get("model_name") or "unknown"
        by_config.setdefault(mn, []).append(r)

    if configs:
        order = [c.model_id for c in configs if c.model_id in by_config]
        for name in sorted(by_config):
            if name not in order:
                order.append(name)
    else:
        order = sorted(by_config)

    pivot = pivot_accuracy(answers, "model_name", "domain", order, DOMAINS)

    buf.write("## 2. Per-Config × Per-Domain Accuracy (%)\n\n")
    domain_headers = " | ".join(DOMAIN_LABELS.get(d, d) for d in DOMAINS)
    buf.write(f"| Config | {domain_headers} |\n")
    buf.write("|" + "---|" * (len(DOMAINS) + 1) + "\n")

    all_domain_correct: dict[str, int] = {d: 0 for d in DOMAINS}
    all_domain_total: dict[str, int] = {d: 0 for d in DOMAINS}
    display_map = {c.model_id: c.name for c in configs} if configs else {}

    for name in order:
        cells = []
        for d in DOMAINS:
            correct, total = pivot.get((name, d), (0, 0))
            all_domain_correct[d] += correct
            all_domain_total[d] += total
            cells.append(fmt_pct(correct, total))
        buf.write(f"| {display_map.get(name, name)} | " + " | ".join(cells) + " |\n")

    # "all" row
    all_cells = [
        fmt_pct(all_domain_correct[d], all_domain_total[d]) for d in DOMAINS
    ]
    buf.write(f"| **all** | " + " | ".join(all_cells) + " |\n")
    buf.write("\n")


def _section_config_strategy(buf: StringIO, answers: list[dict]) -> None:
    """Section 3: Per-config × per-strategy accuracy grid."""
    configs = _get_eval_configs()

    by_config: dict[str, list[dict]] = {}
    for r in answers:
        mn = r.get("model_name") or "unknown"
        by_config.setdefault(mn, []).append(r)

    if configs:
        order = [c.model_id for c in configs if c.model_id in by_config]
        for name in sorted(by_config):
            if name not in order:
                order.append(name)
    else:
        order = sorted(by_config)

    pivot = pivot_accuracy(answers, "model_name", "strategy", order, STRATEGIES)

    buf.write("## 3. Per-Config × Per-Strategy Accuracy (%)\n\n")
    strat_headers = " | ".join(STRATEGY_LABELS.get(s, s) for s in STRATEGIES)
    buf.write(f"| Config | {strat_headers} |\n")
    buf.write("|" + "---|" * (len(STRATEGIES) + 1) + "\n")

    all_strat_correct: dict[str, int] = {s: 0 for s in STRATEGIES}
    all_strat_total: dict[str, int] = {s: 0 for s in STRATEGIES}
    display_map = {c.model_id: c.name for c in configs} if configs else {}

    for name in order:
        cells = []
        for s in STRATEGIES:
            correct, total = pivot.get((name, s), (0, 0))
            all_strat_correct[s] += correct
            all_strat_total[s] += total
            cells.append(fmt_pct(correct, total))
        buf.write(f"| {display_map.get(name, name)} | " + " | ".join(cells) + " |\n")

    # "all" row
    all_cells = [
        fmt_pct(all_strat_correct[s], all_strat_total[s]) for s in STRATEGIES
    ]
    buf.write(f"| **all** | " + " | ".join(all_cells) + " |\n")
    buf.write("\n")


def _section_sps(buf: StringIO, answers: list[dict]) -> None:
    """Section 4: Self-Preference Score analysis."""
    configs = _get_eval_configs()

    buf.write("## 4. Self-Preference Score (SPS)\n\n")

    # Check if we have generator info in answers
    has_generator = any(r.get("generator") is not None for r in answers)
    if not has_generator:
        buf.write(
            "_SPS analysis skipped: generator-family link not in schema "
            "(no generator column joined from generation_metadata)._\n\n"
        )
        return

    if not configs:
        buf.write(
            "_SPS analysis skipped: EVAL_CONFIGS not available (Team B module not yet merged)._\n\n"
        )
        return

    # Build: for each answer, what is the generator family?
    gen_family_answers: dict[str, Any] = {}
    for r in answers:
        gen_val = r.get("generator")
        if gen_val:
            r["_gen_family"] = GENERATOR_TO_FAMILY.get(str(gen_val))
        else:
            r["_gen_family"] = None

    # Get generator-family configs (is_generator_family=True)
    generator_families = [c for c in configs if getattr(c, "is_generator_family", False)]
    if not generator_families:
        # fallback: get distinct families that have is_generator_family from first config
        # Try to get at least anthropic, openai, google, meta
        family_set = {"anthropic", "openai", "google", "meta"}
        seen_families: set[str] = set()
        generator_family_configs = []
        for c in configs:
            fam = getattr(c, "family", None)
            if fam in family_set and fam not in seen_families:
                seen_families.add(fam)
                generator_family_configs.append(c)
    else:
        generator_family_configs = generator_families

    # Group answers by config
    by_config: dict[str, list[dict]] = {}
    for r in answers:
        mn = r.get("model_name") or "unknown"
        by_config.setdefault(mn, []).append(r)

    config_map = {c.model_id: c for c in configs}

    buf.write(
        "Bootstrap 95% CI via 1000 resamples. "
        "δ = accuracy(own-family Qs) − accuracy(other Qs).\n\n"
    )
    buf.write("| Config | Family | Own-family acc | Other acc | δ | 95% CI |\n")
    buf.write("|---|---|---:|---:|---:|---|\n")

    any_sps_computed = False
    for name, rows in sorted(by_config.items()):
        cfg = config_map.get(name)
        if cfg is None:
            continue
        fam = getattr(cfg, "family", None)
        if not fam:
            continue

        own_rows = np.array(
            [1 if r.get("is_correct") else 0 for r in rows if r.get("_gen_family") == fam],
            dtype=float,
        )
        other_rows = np.array(
            [1 if r.get("is_correct") else 0 for r in rows if r.get("_gen_family") not in (None, fam)],
            dtype=float,
        )

        if len(own_rows) == 0 and len(other_rows) == 0:
            continue

        any_sps_computed = True

        if len(own_rows) > 0:
            own_mean, own_lo, own_hi = bootstrap_ci(own_rows)
            own_str = f"{own_mean:.1%}"
        else:
            own_mean = float("nan")
            own_str = "—"

        if len(other_rows) > 0:
            other_mean, other_lo, other_hi = bootstrap_ci(other_rows)
            other_str = f"{other_mean:.1%}"
        else:
            other_mean = float("nan")
            other_str = "—"

        if not math.isnan(own_mean) and not math.isnan(other_mean):
            delta = own_mean - other_mean
            # CI for delta: combine own and other bootstrap
            # Use simple difference of bootstrap distributions
            rng = np.random.default_rng(42)
            n_boot = 1000
            own_boots = np.array([rng.choice(own_rows, size=len(own_rows), replace=True).mean() for _ in range(n_boot)])
            other_boots = np.array([rng.choice(other_rows, size=len(other_rows), replace=True).mean() for _ in range(n_boot)])
            delta_boots = own_boots - other_boots
            ci_lo = float(np.percentile(delta_boots, 2.5))
            ci_hi = float(np.percentile(delta_boots, 97.5))
            delta_str = f"{delta:+.1%}"
            ci_str = f"[{ci_lo:+.1%}, {ci_hi:+.1%}]"
        else:
            delta_str = "—"
            ci_str = "—"

        display = cfg.name if cfg else name
        buf.write(f"| {display} | {fam} | {own_str} | {other_str} | {delta_str} | {ci_str} |\n")

    if not any_sps_computed:
        buf.write("| — | — | — | — | — | No own-family questions found |\n")

    buf.write("\n")


def _section_sps_matrix(buf: StringIO, answers: list[dict]) -> None:
    """Section 4b: SPS family matrix.

    Renders a G × G grid of accuracy% (N) where rows are evaluator families
    and columns are generator families.  Diagonal cells are own-family (SPS)
    accuracy; off-diagonal cells are cross-family.

    Family ordering is fixed at [anthropic, openai, google, meta, qwen] —
    the five families that authored questions in Phase 2 and that have at
    least one ``EvalConfig`` with ``is_generator_family=True``.
    """
    configs = _get_eval_configs()

    buf.write("## 4b. Self-Preference Family Matrix\n\n")
    buf.write(
        "Cells are accuracy% (N). Rows are evaluator families; columns are generator\n"
        "families. Diagonal cells are own-family (SPS) accuracy; off-diagonal cells are\n"
        "cross-family.\n\n"
    )

    if not configs:
        buf.write(
            "_SPS matrix skipped: EVAL_CONFIGS not available._\n\n"
        )
        return

    has_generator = any(r.get("generator") is not None for r in answers)
    if not has_generator:
        buf.write(
            "_SPS matrix skipped: generator-family link not in schema "
            "(no generator column joined from generation_metadata)._\n\n"
        )
        return

    # Fixed family ordering — the 5 families that generated Phase-2 questions.
    families: list[str] = ["anthropic", "openai", "google", "meta", "qwen"]

    # Build map: model_id (DB-stored model_name) -> family from EVAL_CONFIGS
    # (only generator-families).
    model_to_family: dict[str, str] = {}
    for c in configs:
        fam = getattr(c, "family", None)
        if getattr(c, "is_generator_family", False) and fam in families:
            model_to_family[c.model_id] = fam

    # Stamp each row with evaluator_family and generator_family so we can pivot.
    stamped: list[dict[str, Any]] = []
    for r in answers:
        ev_fam = model_to_family.get(r.get("model_name") or "")
        gen_fam = GENERATOR_TO_FAMILY.get(str(r.get("generator"))) if r.get("generator") else None
        if ev_fam is None or gen_fam is None:
            continue
        stamped.append({
            "evaluator_family": ev_fam,
            "generator_family": gen_fam,
            "is_correct": r.get("is_correct"),
        })

    pivot = pivot_accuracy(
        stamped,
        row_key="evaluator_family",
        col_key="generator_family",
        row_order=families,
        col_order=families,
    )

    # Header row: blank corner + generator family columns.
    header_cells = " | ".join(families)
    buf.write(f"| Eval ↓ / Gen → | {header_cells} |\n")
    buf.write("|---|" + "---:|" * len(families) + "\n")

    for ev_fam in families:
        cells = []
        for gen_fam in families:
            correct, total = pivot.get((ev_fam, gen_fam), (0, 0))
            if total == 0:
                cells.append("— (0)")
            else:
                acc = correct / total
                cells.append(f"{acc:.1%} ({total})")
        buf.write(f"| **{ev_fam}** | " + " | ".join(cells) + " |\n")

    buf.write("\n")


def _section_reasoning_deltas(buf: StringIO, answers: list[dict]) -> None:
    """Section 5: Reasoning-effect deltas."""
    configs = _get_eval_configs()

    buf.write("## 5. Reasoning-Effect Deltas\n\n")

    if not configs:
        buf.write(
            "_Reasoning-effect analysis skipped: EVAL_CONFIGS not available "
            "(Team B module not yet merged)._\n\n"
        )
        return

    config_map = {c.model_id: c for c in configs}
    slot_map = {c.slot: c for c in configs}

    # Define pairs (thinking_slot, standard_slot, label)
    pairs = [
        (16, 1, "Claude Opus 4.7: thinking vs standard"),
        (14, 5, "Gemini 2.5 Pro: thinking vs standard"),
        (13, 3, "o3 vs GPT-5"),
        (15, 9, "DeepSeek-R1 vs DeepSeek-V3"),
    ]

    # Group answers by model_name
    by_config: dict[str, list[dict]] = {}
    for r in answers:
        mn = r.get("model_name") or "unknown"
        by_config.setdefault(mn, []).append(r)

    buf.write(
        "Bootstrap 95% CI via 1000 resamples. "
        "δ = accuracy(reasoning config) − accuracy(standard config).\n\n"
    )
    buf.write("| Pair | Thinking config | Standard config | Thinking acc | Standard acc | δ | 95% CI |\n")
    buf.write("|---|---|---|---:|---:|---:|---|\n")

    for think_slot, std_slot, label in pairs:
        think_cfg = slot_map.get(think_slot)
        std_cfg = slot_map.get(std_slot)
        if think_cfg is None or std_cfg is None:
            buf.write(f"| {label} | slot {think_slot} | slot {std_slot} | — | — | — | config not in registry |\n")
            continue

        think_rows_raw = by_config.get(think_cfg.name, [])
        std_rows_raw = by_config.get(std_cfg.name, [])

        if not think_rows_raw and not std_rows_raw:
            buf.write(f"| {label} | {think_cfg.name} | {std_cfg.name} | — | — | — | no data |\n")
            continue

        think_arr = np.array([1 if r.get("is_correct") else 0 for r in think_rows_raw], dtype=float)
        std_arr = np.array([1 if r.get("is_correct") else 0 for r in std_rows_raw], dtype=float)

        if len(think_arr) > 0:
            think_mean, _, _ = bootstrap_ci(think_arr)
            think_str = f"{think_mean:.1%}"
        else:
            think_mean = float("nan")
            think_str = "—"

        if len(std_arr) > 0:
            std_mean, _, _ = bootstrap_ci(std_arr)
            std_str = f"{std_mean:.1%}"
        else:
            std_mean = float("nan")
            std_str = "—"

        if not math.isnan(think_mean) and not math.isnan(std_mean):
            delta = think_mean - std_mean
            rng = np.random.default_rng(42)
            n_boot = 1000
            think_boots = np.array([rng.choice(think_arr, size=len(think_arr), replace=True).mean() for _ in range(n_boot)])
            std_boots = np.array([rng.choice(std_arr, size=len(std_arr), replace=True).mean() for _ in range(n_boot)])
            delta_boots = think_boots - std_boots
            ci_lo = float(np.percentile(delta_boots, 2.5))
            ci_hi = float(np.percentile(delta_boots, 97.5))
            delta_str = f"{delta:+.1%}"
            ci_str = f"[{ci_lo:+.1%}, {ci_hi:+.1%}]"
        else:
            delta_str = "—"
            ci_str = "—"

        buf.write(
            f"| {label} | {think_cfg.name} | {std_cfg.name} "
            f"| {think_str} | {std_str} | {delta_str} | {ci_str} |\n"
        )

    buf.write("\n")


def _section_item_analysis(buf: StringIO, answers: list[dict]) -> None:
    """Section 9: Item analysis — per-question accuracy distribution, ceiling/floor,
    hardest/easiest, and item discrimination (point-biserial).

    Pure aggregation over ``answers``.  No new LLM calls, no new joins.
    """
    buf.write("## 9. Item Analysis\n\n")

    if not answers:
        buf.write("_No answers found for this run._\n\n")
        return

    # Group answers by config (model_name) to determine n_configs and per-config accuracy.
    by_config: dict[str, list[dict]] = {}
    for r in answers:
        mn = r.get("model_name") or "unknown"
        by_config.setdefault(mn, []).append(r)

    config_names = sorted(by_config.keys())
    n_configs = len(config_names)
    if n_configs == 0:
        buf.write("_No configs found in answers._\n\n")
        return

    # Per-config overall accuracy (used for point-biserial later).
    per_config_acc: dict[str, float] = {}
    for name, rows in by_config.items():
        if not rows:
            per_config_acc[name] = float("nan")
        else:
            per_config_acc[name] = sum(1 for r in rows if r.get("is_correct")) / len(rows)

    # Group answers by question_id; track per-(question, config) correctness.
    # outcomes[qid] is a dict {config_name -> 0/1}.
    outcomes: dict[str, dict[str, int]] = {}
    correct_letter: dict[str, str] = {}
    for r in answers:
        qid = r.get("question_id")
        if qid is None:
            continue
        qid = str(qid)
        cfg = r.get("model_name") or "unknown"
        outcomes.setdefault(qid, {})[cfg] = 1 if r.get("is_correct") else 0
        # Capture a parsed_answer for floor sample reporting (any one is fine).
        if qid not in correct_letter and r.get("is_correct") and r.get("parsed_answer"):
            correct_letter[qid] = str(r.get("parsed_answer")).strip()

    # Per-question correct-count (across configs).
    per_q_correct: dict[str, int] = {qid: sum(d.values()) for qid, d in outcomes.items()}
    # Per-question mean accuracy = correct / observed_configs (avoid division by 0).
    per_q_mean: dict[str, float] = {}
    for qid, d in outcomes.items():
        if not d:
            per_q_mean[qid] = float("nan")
        else:
            per_q_mean[qid] = sum(d.values()) / len(d)

    total_questions = len(outcomes)

    # ---------- 9a. Per-question accuracy distribution ----------
    buf.write(f"### 9a. Per-Question Accuracy Distribution\n\n")
    buf.write(
        f"Histogram of how many questions were answered correctly by exactly k configs"
        f" (out of N = {n_configs}).\n\n"
    )
    buf.write(f"| k correct out of {n_configs} | # questions | % of corpus |\n")
    buf.write("|---:|---:|---:|\n")
    for k in range(n_configs + 1):
        n_k = sum(1 for c in per_q_correct.values() if c == k)
        pct = (100.0 * n_k / total_questions) if total_questions > 0 else 0.0
        buf.write(f"| {k} | {n_k} | {pct:.1f}% |\n")
    buf.write("\n")

    # ---------- 9b. Ceiling and floor item counts ----------
    buf.write("### 9b. Ceiling and Floor Items\n\n")
    ceiling_threshold = math.ceil(n_configs * 15.0 / 16.0)
    ceiling_qids = sorted(
        [qid for qid, c in per_q_correct.items() if c >= ceiling_threshold]
    )
    floor_qids = sorted([qid for qid, c in per_q_correct.items() if c == 0])

    buf.write(
        f"- **Ceiling items** (correct by >= {ceiling_threshold} of {n_configs} configs): "
        f"{len(ceiling_qids)} items.\n"
    )
    if ceiling_qids:
        sample = ceiling_qids[:5]
        buf.write("  Sample question_ids: " + ", ".join(f"`{q}`" for q in sample) + "\n")
    buf.write(
        f"- **Floor items** (correct by 0 of {n_configs} configs): "
        f"{len(floor_qids)} items.\n"
    )
    if floor_qids:
        sample = floor_qids[:5]
        formatted = []
        for q in sample:
            letter = correct_letter.get(q, "?")
            formatted.append(f"`{q}` (correct=`{letter}`)" if letter != "?" else f"`{q}`")
        buf.write("  Sample question_ids: " + ", ".join(formatted) + "\n")
    buf.write("\n")

    # ---------- 9c. Hardest and easiest items ----------
    buf.write("### 9c. Hardest and Easiest Items\n\n")
    sorted_by_acc = sorted(per_q_mean.items(), key=lambda kv: (kv[1], kv[0]))
    hardest = sorted_by_acc[:10]
    easiest = list(reversed(sorted_by_acc[-10:]))

    buf.write("**Top 10 hardest** (lowest mean accuracy first):\n\n")
    buf.write("| question_id | mean accuracy |\n|---|---:|\n")
    for qid, mean_acc in hardest:
        buf.write(f"| `{qid}` | {mean_acc:.1%} |\n")
    buf.write("\n")

    buf.write("**Top 10 easiest** (highest mean accuracy first):\n\n")
    buf.write("| question_id | mean accuracy |\n|---|---:|\n")
    for qid, mean_acc in easiest:
        buf.write(f"| `{qid}` | {mean_acc:.1%} |\n")
    buf.write("\n")

    # ---------- 9d. Item discrimination (point-biserial) ----------
    buf.write("### 9d. Item Discrimination (Point-Biserial)\n\n")
    buf.write(
        "For each question we correlate the per-config 0/1 outcome vector with each"
        " config's overall accuracy. Lower / negative `rpb` flags items that"
        " behave inconsistently with overall config skill — paper-quality QA"
        " candidates.\n\n"
    )

    # Per-config accuracy aligned to config_names ordering.
    y = np.array([per_config_acc.get(name, float("nan")) for name in config_names], dtype=float)
    sigma_y = float(np.nanstd(y))

    rpb_results: list[tuple[str, float, float]] = []  # (qid, mean_acc, rpb)
    for qid, d in outcomes.items():
        x = np.array([d.get(name, 0) for name in config_names], dtype=float)
        x_sum = x.sum()
        if x_sum == 0 or x_sum == len(x):
            continue  # no variance
        if sigma_y <= 0:
            continue
        mean_y_correct = y[x == 1].mean()
        mean_y_incorrect = y[x == 0].mean()
        p = x_sum / len(x)
        q_ = 1.0 - p
        rpb = float((mean_y_correct - mean_y_incorrect) * np.sqrt(p * q_) / sigma_y)
        rpb_results.append((qid, per_q_mean[qid], rpb))

    if not rpb_results:
        buf.write("_No items with variance across configs; discrimination not computed._\n\n")
        return

    rpb_results.sort(key=lambda t: (t[2], t[0]))
    worst = rpb_results[:10]
    buf.write(
        "**Top 10 worst-discriminating items** (lowest / most-negative `rpb` first):\n\n"
    )
    buf.write("| question_id | mean accuracy | rpb |\n|---|---:|---:|\n")
    for qid, mean_acc, rpb in worst:
        buf.write(f"| `{qid}` | {mean_acc:.1%} | {rpb:+.3f} |\n")
    buf.write("\n")


def _section_cost_efficiency(buf: StringIO, answers: list[dict]) -> None:
    """Section 10: Cost-efficiency — cost per correct answer per config.

    Uses ``effective_cost`` (OR-authoritative when present, else local).  Configs
    with zero correct answers render '—' and sort to the bottom.
    """
    configs = _get_eval_configs()
    config_map = {c.model_id: c for c in configs} if configs else {}

    by_config: dict[str, list[dict]] = {}
    for r in answers:
        mn = r.get("model_name") or "unknown"
        by_config.setdefault(mn, []).append(r)

    buf.write("## 10. Cost-Efficiency\n\n")
    buf.write(
        "Cost per correct answer = effective_cost / correct_count. Lower is better.\n"
        "\"effective\" cost prefers OR-authoritative when present, else locally computed.\n\n"
    )
    buf.write("| Slot | Config | Correct | Effective cost | Cost / correct |\n")
    buf.write("|---:|---|---:|---|---|\n")

    rows_for_table: list[tuple[Any, str, int, float, float | None]] = []
    for name, rows in by_config.items():
        cfg = config_map.get(name)
        slot = cfg.slot if cfg else "—"
        display = cfg.name if cfg else name
        correct = sum(1 for r in rows if r.get("is_correct"))
        eff_cost = sum(c for c in (effective_cost(r) for r in rows) if c is not None)
        per_correct = (eff_cost / correct) if correct > 0 else None
        rows_for_table.append((slot, display, correct, eff_cost, per_correct))

    # Sort: ascending by per_correct; rows with None (zero correct) go to bottom.
    def _sort_key(row):
        slot, name, correct, eff_cost, per_correct = row
        if per_correct is None:
            return (1, 0.0, name)
        return (0, per_correct, name)

    rows_for_table.sort(key=_sort_key)

    for slot, name, correct, eff_cost, per_correct in rows_for_table:
        if per_correct is None:
            per_correct_str = "—"
        else:
            per_correct_str = f"${per_correct:.4f}"
        buf.write(
            f"| {slot} | {name} | {correct} | {fmt_cost(eff_cost or None)} "
            f"| {per_correct_str} |\n"
        )

    buf.write("\n")


def _section_cost_ledger(buf: StringIO, answers: list[dict]) -> None:
    """Section 6: Cost & wall ledger.

    Shows per-config effective cost (prefers OR-authoritative when available)
    plus two grand-total lines: local-computed and OR-authoritative, so users
    can reconcile against the OR billing dashboard at a glance.
    """
    configs = _get_eval_configs()

    by_config: dict[str, list[dict]] = {}
    for r in answers:
        mn = r.get("model_name") or "unknown"
        by_config.setdefault(mn, []).append(r)

    if configs:
        order = [c.model_id for c in configs if c.model_id in by_config]
        for name in sorted(by_config):
            if name not in order:
                order.append(name)
    else:
        order = sorted(by_config)

    config_map = {c.model_id: c for c in configs} if configs else {}

    buf.write("## 6. Cost & Wall Ledger\n\n")
    buf.write("| Slot | Config | Questions | Cost (effective) | Effective wall (est.) |\n")
    buf.write("|---:|---|---:|---|---|\n")

    grand_local = 0.0
    grand_or = 0.0
    grand_or_rows = 0

    for name in order:
        rows = by_config[name]
        cfg = config_map.get(name)
        slot = cfg.slot if cfg else "—"
        n_q = len(rows)

        # Effective cost per row: OR-authoritative if available, else local.
        eff_cost = sum(c for c in (effective_cost(r) for r in rows) if c is not None)
        local_cost = sum(r["cost_usd"] for r in rows if r.get("cost_usd") is not None)
        or_cost_sum = sum(r["or_cost_usd"] for r in rows if r.get("or_cost_usd") is not None)

        grand_local += local_cost
        grand_or += or_cost_sum
        grand_or_rows += sum(1 for r in rows if r.get("or_cost_usd") is not None)

        # Effective wall = max_latency * n_q / concurrency (approximation)
        lat_vals = [
            r.get("latency_ms") or r.get("response_time_ms")
            for r in rows
            if (r.get("latency_ms") or r.get("response_time_ms")) is not None
        ]
        if lat_vals and cfg and getattr(cfg, "concurrency", None):
            concurrency = cfg.concurrency
            max_lat_ms = float(np.max(lat_vals))
            wall_ms = max_lat_ms * n_q / concurrency
            wall_str = f"~{int(wall_ms / 1000)}s"
        else:
            wall_str = "—"

        display = cfg.name if cfg else name
        buf.write(f"| {slot} | {display} | {n_q} | {fmt_cost(eff_cost or None)} | {wall_str} |\n")

    buf.write(f"| | **Local cost (computed)** | | **{fmt_cost(grand_local or None)}** | |\n")
    or_label = f"OR cost (authoritative, {grand_or_rows:,} rows)"
    buf.write(f"| | **{or_label}** | | **{fmt_cost(grand_or or None)}** | |\n")
    buf.write("\n")


def _section_cb_split(buf: StringIO, answers: list[dict]) -> None:
    """Section 7: Per-config CB-fail vs CB-pass accuracy with bootstrap CI on δ."""
    configs = _get_eval_configs()

    buf.write("## 7. Closed-Book vs Contextual Accuracy\n\n")
    buf.write(
        "CB-fail = questions tagged `closed_book_solvable` (parametric wine knowledge).\n"
        "CB-pass = the rest (contextual wine reasoning). δ = acc(CB-fail) − acc(CB-pass);\n"
        "positive means the model leans on memorised wine facts; negative means it does\n"
        "better when it has to reason from the question.\n\n"
    )

    by_config: dict[str, list[dict]] = {}
    for r in answers:
        mn = r.get("model_name") or "unknown"
        by_config.setdefault(mn, []).append(r)

    if configs:
        order = [c.model_id for c in configs if c.model_id in by_config]
        for name in sorted(by_config):
            if name not in order:
                order.append(name)
    else:
        order = sorted(by_config)

    config_map = {c.model_id: c for c in configs} if configs else {}

    buf.write(
        "| Slot | Config | n CB-fail | acc CB-fail | n CB-pass | acc CB-pass | δ | 95% CI |\n"
    )
    buf.write("|---:|---|---:|---:|---:|---:|---:|---|\n")

    deltas: list[float] = []

    for name in order:
        rows = by_config[name]
        cfg = config_map.get(name)
        slot = cfg.slot if cfg else "—"

        cb_fail = np.array(
            [
                1 if r.get("is_correct") else 0
                for r in rows
                if r.get("tags") and CLOSED_BOOK_TAG in r["tags"]
            ],
            dtype=float,
        )
        cb_pass = np.array(
            [
                1 if r.get("is_correct") else 0
                for r in rows
                if not (r.get("tags") and CLOSED_BOOK_TAG in r["tags"])
            ],
            dtype=float,
        )

        n_fail = len(cb_fail)
        n_pass = len(cb_pass)

        if n_fail > 0:
            fail_mean, _, _ = bootstrap_ci(cb_fail)
            fail_str = f"{fail_mean:.1%}"
        else:
            fail_mean = float("nan")
            fail_str = "—"

        if n_pass > 0:
            pass_mean, _, _ = bootstrap_ci(cb_pass)
            pass_str = f"{pass_mean:.1%}"
        else:
            pass_mean = float("nan")
            pass_str = "—"

        if n_fail > 0 and n_pass > 0:
            delta = fail_mean - pass_mean
            rng = np.random.default_rng(42)
            n_boot = 1000
            fail_boots = np.array(
                [rng.choice(cb_fail, size=n_fail, replace=True).mean() for _ in range(n_boot)]
            )
            pass_boots = np.array(
                [rng.choice(cb_pass, size=n_pass, replace=True).mean() for _ in range(n_boot)]
            )
            delta_boots = fail_boots - pass_boots
            ci_lo = float(np.percentile(delta_boots, 2.5))
            ci_hi = float(np.percentile(delta_boots, 97.5))
            delta_str = f"{delta:+.1%}"
            ci_str = f"[{ci_lo:+.1%}, {ci_hi:+.1%}]"
            deltas.append(delta)
        else:
            delta_str = "—"
            ci_str = "—"

        display = cfg.name if cfg else name
        buf.write(
            f"| {slot} | {display} | {n_fail} | {fail_str} | {n_pass} | {pass_str} "
            f"| {delta_str} | {ci_str} |\n"
        )

    if deltas:
        mean_delta = sum(deltas) / len(deltas)
        mean_delta_str = f"{mean_delta:+.1%}"
    else:
        mean_delta_str = "—"

    buf.write(
        f"| | **all configs (mean δ)** | | | | | **{mean_delta_str}** | |\n"
    )
    buf.write("\n")


def _section_difficulty(buf: StringIO, answers: list[dict]) -> None:
    """Section 8: Per-config × per-difficulty accuracy grid."""
    configs = _get_eval_configs()

    by_config: dict[str, list[dict]] = {}
    for r in answers:
        mn = r.get("model_name") or "unknown"
        by_config.setdefault(mn, []).append(r)

    if configs:
        order = [c.model_id for c in configs if c.model_id in by_config]
        for name in sorted(by_config):
            if name not in order:
                order.append(name)
    else:
        order = sorted(by_config)

    pivot = pivot_accuracy(
        answers, "model_name", "difficulty", order, DIFFICULTY_LEVELS
    )

    buf.write("## 8. Per-Config × Per-Difficulty Accuracy (%)\n\n")
    buf.write(
        "Difficulty 1 (easy) → 4 (hardest). Cells are accuracy on each difficulty tier.\n\n"
    )
    diff_headers = " | ".join(DIFFICULTY_LABELS[d] for d in DIFFICULTY_LEVELS)
    buf.write(f"| Config | {diff_headers} |\n")
    buf.write("|" + "---|" * (len(DIFFICULTY_LEVELS) + 1) + "\n")

    all_diff_correct: dict[str, int] = {d: 0 for d in DIFFICULTY_LEVELS}
    all_diff_total: dict[str, int] = {d: 0 for d in DIFFICULTY_LEVELS}
    display_map = {c.model_id: c.name for c in configs} if configs else {}

    for name in order:
        cells = []
        for d in DIFFICULTY_LEVELS:
            correct, total = pivot.get((name, d), (0, 0))
            all_diff_correct[d] += correct
            all_diff_total[d] += total
            cells.append(fmt_pct(correct, total))
        buf.write(f"| {display_map.get(name, name)} | " + " | ".join(cells) + " |\n")

    all_cells = [
        fmt_pct(all_diff_correct[d], all_diff_total[d]) for d in DIFFICULTY_LEVELS
    ]
    buf.write(f"| **all** | " + " | ".join(all_cells) + " |\n")
    buf.write("\n")


# ---------------------------------------------------------------------------
# Main render function (importable by tests)
# ---------------------------------------------------------------------------


def render_report(tag: str, output_path: str | None = None) -> str:
    """
    Query DB and render the full markdown report.
    Returns the markdown string.
    Also writes to output_path (or data/reports/eval_<tag>_<ts>.md).
    """
    from src.utils.db import get_pg

    conn = get_pg()

    # 1. Resolve run
    run = _resolve_run(conn, tag)
    run_id = str(run["id"])

    # 2. Determine corpus
    metadata = run.get("metadata") or {}
    corpus = metadata.get("corpus", "sample")
    # Normalise: 'sample_v1' -> 'sample', 'public' -> 'public'
    if corpus.startswith("sample"):
        corpus_schema = "sample"
    else:
        corpus_schema = "public"

    # 3. Load answers
    answers = _load_answers(conn, run_id, corpus_schema)

    # 4. Render
    buf = StringIO()
    _section_header(buf, run, answers, tag, corpus)
    _section_per_config_summary(buf, answers)
    _section_config_domain(buf, answers)
    _section_config_strategy(buf, answers)
    _section_sps(buf, answers)
    _section_sps_matrix(buf, answers)
    _section_reasoning_deltas(buf, answers)
    _section_cost_ledger(buf, answers)
    _section_cb_split(buf, answers)
    _section_difficulty(buf, answers)
    _section_item_analysis(buf, answers)
    _section_cost_efficiency(buf, answers)

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    buf.write(f"\n---\n_Generated at {ts} by OenoBench report renderer._\n")

    report_md = buf.getvalue()

    # 5. Write to file
    if output_path is None:
        reports_dir = Path("data/reports")
        reports_dir.mkdir(parents=True, exist_ok=True)
        output_path = str(reports_dir / f"eval_{tag}_{ts}.md")

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(report_md, encoding="utf-8")
    click.echo(f"Report written to: {output_path}", err=True)

    return report_md


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


@click.command()
@click.option("--tag", required=True, help="Evaluation run tag (e.g. eval_sample_v1)")
@click.option("--output", default=None, help="Output file path (default: data/reports/eval_<tag>_<ts>.md)")
def main(tag: str, output: str | None) -> None:
    """Render a markdown evaluation report for a given run tag."""
    report_md = render_report(tag=tag, output_path=output)
    click.echo(report_md)


if __name__ == "__main__":
    main()
