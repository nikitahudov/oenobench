"""
OenoBench — Closed-book vs contextual accuracy gap by difficulty tier.
======================================================================

Computes, for each of the 16 configs in the Phase 5 evaluation slate and each
L1/L2/L3/L4 difficulty tier:

    gap_k(m) = Acc(m on B2-flagged ∩ L_k)  −  Acc(m on contextual ∩ L_k)

Then aggregates a per-tier mean across the 16 configs with a 95 % bootstrap CI
(1,000 resamples; we resample over questions within each pool independently).

Self-test: the average per-tier means weighted by tier counts should reproduce
the +32.6 pp aggregate gap reported in §5.5 within ±0.5 pp.

Run:
    source .venv/bin/activate
    python -m analysis.cb_gap_by_tier
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from src.evaluation.configs import EVAL_CONFIGS
from src.utils.db import get_pg

# --------------------------------------------------------------------------
# Constants
# --------------------------------------------------------------------------

# B2-flagged closed-book questions are stored with the `closed_book_solvable`
# tag (set when the B2 audit panel reports severity warn|fail). The contextual
# set is the complement within the release_v1.2 corpus. See
# src/evaluation/cb_split.py for the canonical split.
CLOSED_BOOK_TAG = "closed_book_solvable"
RELEASE_TAG = "release_v1.2"
EVAL_RUN_TAG = "eval_release_v1_2_full"

DIFFICULTY_LEVELS = ["1", "2", "3", "4"]

N_BOOT = 1000
RNG_SEED = 42


# --------------------------------------------------------------------------
# DB queries
# --------------------------------------------------------------------------


def _row_compound_key(model_name: str, reasoning_config: Any) -> str:
    """Mirror src.evaluation.report._row_compound_key so reasoning twins
    (e.g. claude-opus-4.7 vs claude-opus-4.7-thinking) stay in separate
    buckets."""
    if reasoning_config is None or reasoning_config == {} or reasoning_config == "":
        return model_name
    if isinstance(reasoning_config, str):
        import json as _json
        try:
            reasoning_config = _json.loads(reasoning_config)
        except Exception:
            return f"{model_name}#{reasoning_config}"
    import json as _json
    return f"{model_name}#{_json.dumps(reasoning_config, sort_keys=True)}"


def _config_compound_key(c) -> str:
    import json as _json
    if c.reasoning_mode is None:
        return c.model_id
    if c.reasoning_mode == "explicit_budget":
        d = {"max_tokens": int(c.reasoning_budget or 512)}
    else:  # "effort"
        d = {"effort": c.reasoning_effort or "medium"}
    return f"{c.model_id}#{_json.dumps(d, sort_keys=True)}"


def load_question_df() -> pd.DataFrame:
    """Per-question DataFrame with question_id, difficulty, is_b2_flagged.

    Restricted to the release_v1.2 published corpus (3,266 questions).
    """
    conn = get_pg()
    cur = conn.cursor()
    cur.execute(
        f"""
        SELECT
            q.id::text AS question_id,
            q.difficulty::text AS difficulty,
            (%s = ANY(q.tags)) AS is_b2_flagged
        FROM public.questions q
        WHERE %s = ANY(q.tags)
        """,
        (CLOSED_BOOK_TAG, RELEASE_TAG),
    )
    rows = cur.fetchall()
    return pd.DataFrame([dict(r) for r in rows])


def load_answers_df() -> pd.DataFrame:
    """Per-(config, question) DataFrame with config_name, question_id, is_correct.

    Joins evaluation_answers from the release_v1_2 full eval run to questions in
    the release_v1.2 published corpus, mirroring the report renderer's release
    filter.
    """
    conn = get_pg()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, metadata
        FROM evaluation_runs
        WHERE metadata->>'tag' = %s
        ORDER BY started_at DESC
        LIMIT 1
        """,
        (EVAL_RUN_TAG,),
    )
    run = cur.fetchone()
    if run is None:
        raise RuntimeError(f"No evaluation_run with tag={EVAL_RUN_TAG!r}")
    run_id = run["id"]

    cur.execute(
        """
        SELECT
            a.question_id::text AS question_id,
            a.model_name        AS model_name,
            a.reasoning_config  AS reasoning_config,
            a.is_correct        AS is_correct
        FROM evaluation_answers a
        JOIN public.questions q ON q.id = a.question_id
        WHERE a.run_id = %s
          AND %s = ANY(q.tags)
        """,
        (run_id, RELEASE_TAG),
    )
    rows = cur.fetchall()
    df = pd.DataFrame([dict(r) for r in rows])

    # Compute compound key (collapses reasoning twins to distinct bucket).
    df["config_key"] = df.apply(
        lambda r: _row_compound_key(r["model_name"], r["reasoning_config"]),
        axis=1,
    )

    # NULL is_correct rows come from parse failures in the eval harness; treat
    # them as incorrect (the same convention src/evaluation/report.py uses).
    df["is_correct"] = df["is_correct"].fillna(False).infer_objects(copy=False).astype(bool)
    return df


# --------------------------------------------------------------------------
# Gap computation
# --------------------------------------------------------------------------


def compute_per_config_gaps(
    questions: pd.DataFrame,
    answers: pd.DataFrame,
) -> pd.DataFrame:
    """Return a DataFrame indexed by config_key with columns
    L1_gap..L4_gap (signed pp), gap_overall (pp), n_cb_<k>, n_ctx_<k>.
    """
    merged = answers.merge(
        questions[["question_id", "difficulty", "is_b2_flagged"]],
        on="question_id",
        how="inner",
    )

    out_rows: list[dict[str, Any]] = []
    for cfg_key, sub in merged.groupby("config_key", sort=False):
        row: dict[str, Any] = {"config_key": cfg_key}

        # Per-tier gaps.
        for diff in DIFFICULTY_LEVELS:
            tier = sub[sub["difficulty"] == diff]
            cb = tier[tier["is_b2_flagged"]]
            ctx = tier[~tier["is_b2_flagged"]]
            cb_acc = cb["is_correct"].mean() if len(cb) else float("nan")
            ctx_acc = ctx["is_correct"].mean() if len(ctx) else float("nan")
            gap = (cb_acc - ctx_acc) if (
                not np.isnan(cb_acc) and not np.isnan(ctx_acc)
            ) else float("nan")
            row[f"L{diff}_cb_n"] = int(len(cb))
            row[f"L{diff}_ctx_n"] = int(len(ctx))
            row[f"L{diff}_cb_acc"] = float(cb_acc) if not np.isnan(cb_acc) else None
            row[f"L{diff}_ctx_acc"] = float(ctx_acc) if not np.isnan(ctx_acc) else None
            row[f"L{diff}_gap"] = float(gap) if not np.isnan(gap) else None

        # Overall gap (un-weighted by tier — i.e. acc on full CB pool − acc on
        # full ctx pool, matching the §5.5 figure).
        cb_all = sub[sub["is_b2_flagged"]]
        ctx_all = sub[~sub["is_b2_flagged"]]
        cb_overall = cb_all["is_correct"].mean() if len(cb_all) else float("nan")
        ctx_overall = ctx_all["is_correct"].mean() if len(ctx_all) else float("nan")
        gap_overall = cb_overall - ctx_overall if (
            not np.isnan(cb_overall) and not np.isnan(ctx_overall)
        ) else float("nan")
        row["cb_n_all"] = int(len(cb_all))
        row["ctx_n_all"] = int(len(ctx_all))
        row["cb_acc_all"] = float(cb_overall) if not np.isnan(cb_overall) else None
        row["ctx_acc_all"] = float(ctx_overall) if not np.isnan(ctx_overall) else None
        row["gap_overall"] = float(gap_overall) if not np.isnan(gap_overall) else None
        out_rows.append(row)

    return pd.DataFrame(out_rows)


def bootstrap_tier_mean_ci(
    answers: pd.DataFrame,
    questions: pd.DataFrame,
    diff: str,
    cfg_keys: list[str],
    n_boot: int = N_BOOT,
    seed: int = RNG_SEED,
) -> tuple[float, float, float]:
    """
    Bootstrap 95 % CI on the per-config-mean gap at one tier.

    Resampling protocol: we resample question_ids independently within the
    closed-book pool of tier `diff` and within the contextual pool of tier
    `diff` (with replacement). For each resample we recompute every config's
    gap on the resampled pools, then average across the 16 configs to get one
    mean-gap draw. The 95 % percentile interval over `n_boot` draws is the CI.

    The same resampled question set is used across configs in a single draw,
    which preserves the question-level correlation across configs (a model
    that gets question X right tends to do so across many models).
    """
    tier_q = questions[questions["difficulty"] == diff]
    cb_qids = tier_q[tier_q["is_b2_flagged"]]["question_id"].tolist()
    ctx_qids = tier_q[~tier_q["is_b2_flagged"]]["question_id"].tolist()
    if not cb_qids or not ctx_qids:
        return (float("nan"), float("nan"), float("nan"))

    # Per-(config, question) accuracy lookup, restricted to this tier.
    tier_ans = answers[answers["question_id"].isin(set(cb_qids) | set(ctx_qids))]
    # Build wide-form indexed lookup: dict[(cfg_key, qid)] -> 0/1.  Treat
    # NULL is_correct (parse failures from the eval harness) as incorrect, the
    # same convention that src/evaluation/report.py uses everywhere.
    lookup: dict[tuple[str, str], int] = {}
    for cfg_key, qid, is_corr in zip(
        tier_ans["config_key"].values,
        tier_ans["question_id"].values,
        tier_ans["is_correct"].values,
    ):
        lookup[(cfg_key, qid)] = 1 if bool(is_corr) else 0

    # For each config, get arrays of (correctness on each cb qid, on each ctx qid).
    cb_qids_arr = np.array(cb_qids)
    ctx_qids_arr = np.array(ctx_qids)

    cfg_cb_arrays: dict[str, np.ndarray] = {}
    cfg_ctx_arrays: dict[str, np.ndarray] = {}
    for cfg in cfg_keys:
        cfg_cb_arrays[cfg] = np.array(
            [lookup.get((cfg, q), 0) for q in cb_qids_arr], dtype=float
        )
        cfg_ctx_arrays[cfg] = np.array(
            [lookup.get((cfg, q), 0) for q in ctx_qids_arr], dtype=float
        )

    rng = np.random.default_rng(seed)
    n_cb = len(cb_qids_arr)
    n_ctx = len(ctx_qids_arr)

    boot_means = np.empty(n_boot, dtype=float)
    for b in range(n_boot):
        cb_idx = rng.integers(0, n_cb, size=n_cb)
        ctx_idx = rng.integers(0, n_ctx, size=n_ctx)
        gaps_b = []
        for cfg in cfg_keys:
            cb_acc = cfg_cb_arrays[cfg][cb_idx].mean()
            ctx_acc = cfg_ctx_arrays[cfg][ctx_idx].mean()
            gaps_b.append(cb_acc - ctx_acc)
        boot_means[b] = float(np.mean(gaps_b))

    point = float(
        np.mean(
            [
                cfg_cb_arrays[cfg].mean() - cfg_ctx_arrays[cfg].mean()
                for cfg in cfg_keys
            ]
        )
    )
    lo = float(np.percentile(boot_means, 2.5))
    hi = float(np.percentile(boot_means, 97.5))
    return (point, lo, hi)


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------


def render_latex_table(
    per_cfg: pd.DataFrame,
    cfg_order: list[tuple[str, str]],  # list of (display_name, config_key)
    tier_means: dict[str, tuple[float, float, float]],
) -> str:
    """Build the §C.3 LaTeX table snippet, matching Table 13's row order."""
    lines: list[str] = []
    lines.append(r"\begin{table}[H]")
    lines.append(r"  \centering")
    lines.append(r"  \footnotesize")
    lines.append(
        r"  \caption{Closed-book vs.\ contextual accuracy gap (pp) within each "
        r"difficulty tier. A positive gap means the model scores higher on "
        r"B2-flagged closed-book-solvable items than on contextual items at "
        r"the same difficulty tier.}"
    )
    lines.append(r"  \label{tab:cb-by-tier}")
    lines.append(r"  \begin{tabular}{lrrrr}")
    lines.append(r"    \toprule")
    lines.append(r"    Config & L1 gap & L2 gap & L3 gap & L4 gap \\")
    lines.append(r"    \midrule")

    def _fmt_pp(v: float | None) -> str:
        """Match the paper's "$+$X.X" / "$-$X.X" style (reasoning-by-diff table)."""
        if v is None or (isinstance(v, float) and np.isnan(v)):
            return "—"
        pp = v * 100.0
        sign = r"$+$" if pp >= 0 else r"$-$"
        return f"{sign}{abs(pp):.1f}"

    for display, key in cfg_order:
        row = per_cfg[per_cfg["config_key"] == key]
        if row.empty:
            cells = ["—"] * 4
        else:
            r = row.iloc[0]
            cells = [_fmt_pp(r[f"L{d}_gap"]) for d in DIFFICULTY_LEVELS]
        # Pad display name for visual alignment in the source.
        lines.append(f"    {display:<28} & " + " & ".join(cells) + r" \\")
    lines.append(r"    \midrule")

    def _fmt_mean_ci(d: str) -> str:
        pt, lo, hi = tier_means[d]
        if any(np.isnan(x) for x in (pt, lo, hi)):
            return r"\textbf{—}"
        def _fmt_one(x: float) -> str:
            pp = x * 100.0
            return (r"$+$" if pp >= 0 else r"$-$") + f"{abs(pp):.1f}"
        return (
            rf"\textbf{{{_fmt_one(pt)} [{_fmt_one(lo)}, {_fmt_one(hi)}]}}"
        )

    mean_cells = [_fmt_mean_ci(d) for d in DIFFICULTY_LEVELS]
    lines.append(
        r"    \textbf{Mean (16 configs)}    & "
        + " & ".join(mean_cells)
        + r" \\"
    )
    lines.append(r"    \bottomrule")
    lines.append(r"  \end{tabular}")
    lines.append(r"\end{table}")
    return "\n".join(lines)


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------


def main() -> None:
    print("=== Loading per-question + per-answer data...", flush=True)
    questions = load_question_df()
    answers = load_answers_df()

    n_q_total = len(questions)
    n_cb = int(questions["is_b2_flagged"].sum())
    n_ctx = int((~questions["is_b2_flagged"]).sum())
    print(
        f"questions in release_v1.2: total={n_q_total}, "
        f"B2-flagged={n_cb}, contextual={n_ctx}"
    )
    if n_cb != 1601 or n_ctx != 1665:
        print(
            f"WARNING: population sizes don't match paper (1,601 / 1,665)."
        )
    else:
        print("Population sizes match paper (1,601 / 1,665). ✓")

    print(
        "answers loaded:",
        len(answers),
        "rows from",
        answers["config_key"].nunique(),
        "configs",
    )

    # Order rows like Table 13 (per-difficulty table).
    cfg_order = [(c.name, _config_compound_key(c)) for c in EVAL_CONFIGS]
    if not all(k in set(answers["config_key"]) for _, k in cfg_order):
        missing = [k for _, k in cfg_order if k not in set(answers["config_key"])]
        raise RuntimeError(f"Missing configs in answers: {missing}")

    per_cfg = compute_per_config_gaps(questions, answers)
    print("\n=== Per-config gaps (pp):")
    for display, key in cfg_order:
        r = per_cfg[per_cfg["config_key"] == key].iloc[0]
        gaps = [r[f"L{d}_gap"] for d in DIFFICULTY_LEVELS]
        gap_overall = r["gap_overall"]
        print(
            f"  {display:<28}  "
            f"L1={gaps[0]*100:+5.1f}  L2={gaps[1]*100:+5.1f}  "
            f"L3={gaps[2]*100:+5.1f}  L4={gaps[3]*100:+5.1f}  "
            f"|  overall={gap_overall*100:+5.1f}"
        )

    cfg_keys = [k for _, k in cfg_order]

    print("\n=== Bootstrap CIs over per-tier means (1,000 resamples)...", flush=True)
    tier_means: dict[str, tuple[float, float, float]] = {}
    for d in DIFFICULTY_LEVELS:
        pt, lo, hi = bootstrap_tier_mean_ci(
            answers, questions, d, cfg_keys
        )
        tier_means[d] = (pt, lo, hi)
        print(
            f"  L{d}: mean gap = {pt*100:+.1f} pp  [95% CI {lo*100:+.1f}, {hi*100:+.1f}]"
        )

    # ----- Self-test: weighted by tier counts should reproduce the +32.6 pp.
    print("\n=== Self-test: weighted-by-tier-count vs aggregate gap")

    # Aggregate per-config gap = un-weighted overall (matches §5.5 figure).
    aggr_gaps = per_cfg["gap_overall"].dropna().to_numpy()
    aggr_mean = float(aggr_gaps.mean())
    print(f"  §5.5-style aggregate mean gap (per-config un-weighted): "
          f"{aggr_mean*100:+.2f} pp")

    # Weight per-tier means by total per-tier question count: this is what the
    # paper's aggregate gap is (the cb-fail / cb-pass acc on the full pool with
    # no tier stratification).
    cb_counts = {
        d: int(((questions["difficulty"] == d) & questions["is_b2_flagged"]).sum())
        for d in DIFFICULTY_LEVELS
    }
    ctx_counts = {
        d: int(((questions["difficulty"] == d) & ~questions["is_b2_flagged"]).sum())
        for d in DIFFICULTY_LEVELS
    }
    print(f"  CB tier counts:  {cb_counts}")
    print(f"  CTX tier counts: {ctx_counts}")

    # Mean across configs of:
    #   sum_d cb_n_d * cb_acc_d / sum_d cb_n_d
    # − sum_d ctx_n_d * ctx_acc_d / sum_d ctx_n_d
    weighted_per_cfg: list[float] = []
    for cfg in cfg_keys:
        r = per_cfg[per_cfg["config_key"] == cfg].iloc[0]
        cb_num = sum(
            cb_counts[d] * (r[f"L{d}_cb_acc"] or 0.0) for d in DIFFICULTY_LEVELS
        )
        cb_den = sum(cb_counts[d] for d in DIFFICULTY_LEVELS)
        ctx_num = sum(
            ctx_counts[d] * (r[f"L{d}_ctx_acc"] or 0.0) for d in DIFFICULTY_LEVELS
        )
        ctx_den = sum(ctx_counts[d] for d in DIFFICULTY_LEVELS)
        weighted_per_cfg.append((cb_num / cb_den) - (ctx_num / ctx_den))
    weighted_mean = float(np.mean(weighted_per_cfg))
    print(
        f"  Tier-weighted mean (sums to overall aggregate): "
        f"{weighted_mean*100:+.2f} pp"
    )

    # Two-stage check 1: simple arithmetic mean of the four per-tier means.
    simple_mean_of_tier_means = float(
        np.mean([tier_means[d][0] for d in DIFFICULTY_LEVELS])
    )
    print(
        f"  Simple mean of four per-tier means (un-weighted): "
        f"{simple_mean_of_tier_means*100:+.2f} pp"
    )

    delta = (weighted_mean - aggr_mean) * 100.0
    print(f"\n  weighted-vs-aggregate delta: {delta:+.3f} pp "
          f"(target |Δ| ≤ 0.5 pp)")
    assert abs(delta) <= 0.5, "Weighted mean should reproduce aggregate within 0.5 pp."

    # Build LaTeX table.
    print("\n=== LaTeX table:\n")
    tex = render_latex_table(per_cfg, cfg_order, tier_means)
    print(tex)


if __name__ == "__main__":
    main()
