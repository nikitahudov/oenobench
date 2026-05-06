"""Per-difficulty-tier breakdown of the Self-Preference Score (SPS).

For each of the 13 SPS-eligible configs (everyone except DeepSeek V3, DeepSeek R1,
Mistral Large — they have no own-family questions in release_v1.2), compute SPS
broken out by difficulty tier L1/L2/L3/L4:

    SPS_k(m) = Acc(m on Q_own ∩ L_k) − Acc(m on Q_other ∩ L_k)

Where Q_own = questions authored by the model's family generator and Q_other =
questions authored by a different *model* family generator (templates excluded
from both pools, matching ``src/evaluation/report.py::_section_sps``).

Run from the repo root with the project venv activated:

    source .venv/bin/activate
    python -m analysis.sps_by_tier

Usage modes:
  --table          render the LaTeX table snippet (default)
  --self-test      print overall δ next to Table 9 values for each config
  --json out.json  dump the full per-tier matrix
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from typing import Any

import numpy as np

from src.utils.db import get_pg

# ---------------------------------------------------------------------------
# Constants — match Table 9 / src/evaluation/report.py
# ---------------------------------------------------------------------------

RUN_TAG = "eval_release_v1_2_full"
RELEASE = "v1.2"

# generator enum value → config family.  Mirrors ``GENERATOR_TO_FAMILY`` in
# ``src/evaluation/report.py``.  template_only / human_authored / NULL are
# treated as "other-family for everyone" (they get filtered out of Q_other,
# matching the SPS computation upstream).
GENERATOR_TO_FAMILY: dict[str, str | None] = {
    "claude": "anthropic",
    "chatgpt": "openai",
    "gemini": "google",
    "llama": "meta",
    "qwen": "qwen",
    "template_only": None,
    "human_authored": None,
    "gpt4": "openai",
}

# (display name, family, model_name, reasoning_config-as-key) tuples.  The order
# matches Table 9 in paper/sections/09_appendix_evaluation.tex.
def _rc_key(rc):
    """Reasoning-config key — must match _row_compound_key in report.py."""
    if rc is None or rc == {} or rc == "":
        return None
    return tuple(sorted(rc.items()))


CONFIG_ORDER: list[tuple[str, str, str, Any]] = [
    ("claude-haiku-4.5",         "anthropic", "anthropic/claude-haiku-4.5",          None),
    ("claude-opus-4.7",          "anthropic", "anthropic/claude-opus-4.7",           None),
    ("claude-opus-4.7-thinking", "anthropic", "anthropic/claude-opus-4.7",           _rc_key({"max_tokens": 512})),
    ("qwen-2.5-7b",              "qwen",      "qwen/qwen-2.5-7b-instruct",           None),
    ("qwen-2.5-72b",             "qwen",      "qwen/qwen-2.5-72b-instruct",          None),
    ("llama-3.3-70b",            "meta",      "meta-llama/llama-3.3-70b-instruct",   None),
    ("gpt-5-mini",               "openai",    "openai/gpt-5-mini",                   None),
    ("o3",                       "openai",    "openai/o3",                           _rc_key({"effort": "medium"})),
    ("gpt-5",                    "openai",    "openai/gpt-5",                        None),
    ("llama-3.1-8b",             "meta",      "meta-llama/llama-3.1-8b-instruct",    None),
    ("gemini-2.5-pro",           "google",    "google/gemini-2.5-pro",               None),
    ("gemini-2.5-pro-thinking",  "google",    "google/gemini-2.5-pro",               _rc_key({"max_tokens": 512})),
    ("gemini-2.5-flash",         "google",    "google/gemini-2.5-flash",             None),
]

# Overall δ from Table 9 (paper/sections/09_appendix_evaluation.tex) — for the
# self-test sanity check.
TABLE9_DELTA = {
    "claude-haiku-4.5":         +10.0,
    "claude-opus-4.7":          +9.1,
    "claude-opus-4.7-thinking": +9.7,
    "qwen-2.5-7b":              +9.0,
    "qwen-2.5-72b":             +2.0,
    "llama-3.3-70b":            +1.9,
    "gpt-5-mini":               +1.7,
    "o3":                       -0.1,
    "gpt-5":                    -1.7,
    "llama-3.1-8b":             -3.0,
    "gemini-2.5-pro":           -6.1,
    "gemini-2.5-pro-thinking":  -8.0,
    "gemini-2.5-flash":         -10.4,
}

# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def _load_run_id(conn, tag: str) -> str:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id FROM evaluation_runs
            WHERE metadata->>'tag' = %s
            ORDER BY started_at DESC
            LIMIT 1
            """,
            (tag,),
        )
        row = cur.fetchone()
    if row is None:
        raise SystemExit(f"No evaluation_runs row with tag={tag!r}")
    return str(row["id"])


def _load_answers(conn, run_id: str, release: str = "v1.2") -> list[dict]:
    """Pull (model_name, reasoning_config, question_id, is_correct, difficulty,
    generator) for every answer in the run, restricted to release_v1.2 questions.
    """
    sql = """
        SELECT
            a.model_name,
            a.reasoning_config,
            a.question_id,
            a.is_correct,
            q.difficulty::text AS difficulty,
            gm.generator::text AS generator
        FROM evaluation_answers a
        JOIN public.questions q ON q.id = a.question_id
        LEFT JOIN public.generation_metadata gm ON gm.question_id = q.id
        WHERE a.run_id = %s AND %s = ANY(q.tags)
    """
    with conn.cursor() as cur:
        cur.execute(sql, (run_id, f"release_{release}"))
        return [dict(r) for r in cur.fetchall()]


# ---------------------------------------------------------------------------
# Bootstrap helpers
# ---------------------------------------------------------------------------

def _delta_ci(own: np.ndarray, other: np.ndarray, n_boot: int = 1000,
              seed: int = 42) -> tuple[float, float, float]:
    """Return (delta_pp, ci_lo_pp, ci_hi_pp) for own_mean − other_mean.

    Resamples each pool independently at the question level, matching
    src/evaluation/report.py::_section_sps.
    """
    if len(own) == 0 or len(other) == 0:
        return (float("nan"), float("nan"), float("nan"))
    delta = own.mean() - other.mean()
    rng = np.random.default_rng(seed)
    own_boots = np.array([rng.choice(own, size=len(own), replace=True).mean()
                          for _ in range(n_boot)])
    other_boots = np.array([rng.choice(other, size=len(other), replace=True).mean()
                            for _ in range(n_boot)])
    delta_boots = own_boots - other_boots
    return (
        float(delta * 100),
        float(np.percentile(delta_boots, 2.5) * 100),
        float(np.percentile(delta_boots, 97.5) * 100),
    )


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

def _bucket_answers(answers: list[dict]) -> dict[tuple[str, Any], list[dict]]:
    """Return dict mapping (model_name, rc_key) -> list of rows."""
    buckets: dict[tuple[str, Any], list[dict]] = defaultdict(list)
    for r in answers:
        key = (r["model_name"], _rc_key(r.get("reasoning_config")))
        buckets[key].append(r)
    return buckets


def compute_sps_by_tier(answers: list[dict]) -> dict[str, dict]:
    """For each config in CONFIG_ORDER, compute overall + per-tier SPS.

    Returns:
        {
          display_name: {
            "family": ...,
            "overall": {"own_n", "own_acc", "other_n", "other_acc",
                        "delta_pp", "ci_lo_pp", "ci_hi_pp"},
            "tiers":   {"1": {...}, "2": {...}, "3": {...}, "4": {...}},
          },
          ...
        }
    """
    buckets = _bucket_answers(answers)
    # Stamp each row with its generator family.
    for rows in buckets.values():
        for r in rows:
            gen = r.get("generator")
            r["_gen_family"] = GENERATOR_TO_FAMILY.get(str(gen)) if gen else None

    out: dict[str, dict] = {}
    for display, family, model_name, rc_key in CONFIG_ORDER:
        rows = buckets.get((model_name, rc_key))
        if rows is None:
            print(f"WARN: no rows for ({model_name}, rc_key={rc_key})", file=sys.stderr)
            continue

        # Overall pools
        own_overall = np.array(
            [1 if r.get("is_correct") else 0 for r in rows
             if r["_gen_family"] == family],
            dtype=float,
        )
        other_overall = np.array(
            [1 if r.get("is_correct") else 0 for r in rows
             if r["_gen_family"] not in (None, family)],
            dtype=float,
        )
        d, lo, hi = _delta_ci(own_overall, other_overall)
        cfg_out: dict = {
            "family": family,
            "overall": {
                "own_n": int(len(own_overall)),
                "own_acc": float(own_overall.mean() * 100) if len(own_overall) else float("nan"),
                "other_n": int(len(other_overall)),
                "other_acc": float(other_overall.mean() * 100) if len(other_overall) else float("nan"),
                "delta_pp": d,
                "ci_lo_pp": lo,
                "ci_hi_pp": hi,
            },
            "tiers": {},
        }

        # Per-tier
        for tier in ("1", "2", "3", "4"):
            own = np.array(
                [1 if r.get("is_correct") else 0 for r in rows
                 if r["_gen_family"] == family and r["difficulty"] == tier],
                dtype=float,
            )
            other = np.array(
                [1 if r.get("is_correct") else 0 for r in rows
                 if r["_gen_family"] not in (None, family) and r["difficulty"] == tier],
                dtype=float,
            )
            d, lo, hi = _delta_ci(own, other)
            cfg_out["tiers"][tier] = {
                "own_n": int(len(own)),
                "own_acc": float(own.mean() * 100) if len(own) else float("nan"),
                "other_n": int(len(other)),
                "other_acc": float(other.mean() * 100) if len(other) else float("nan"),
                "delta_pp": d,
                "ci_lo_pp": lo,
                "ci_hi_pp": hi,
            }
        out[display] = cfg_out
    return out


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def _fmt_cell(d: float, lo: float, hi: float) -> str:
    """Signed pp with one decimal; \\bfseries when 95% CI excludes zero."""
    if np.isnan(d):
        return "—"
    sign = "+" if d >= 0 else "-"
    s = f"${sign}{abs(d):.1f}$"
    excludes_zero = (not np.isnan(lo)) and (not np.isnan(hi)) and (lo > 0 or hi < 0)
    if excludes_zero:
        s = f"$\\mathbf{{{sign}{abs(d):.1f}}}$"
    return s


def render_table(results: dict[str, dict]) -> str:
    """Render the LaTeX table snippet."""
    lines = [
        r"\begin{table}[H]",
        r"  \centering",
        r"  \footnotesize",
        r"  \caption{Per-tier Self-Preference Score $\delta$ (pp). Per-config own-vs-other accuracy gap broken out by difficulty tier (L1--L4); cells where the 95\% bootstrap CI excludes zero are bold.}",
        r"  \label{tab:sps-by-tier}",
        r"  \begin{tabular}{llrrrr}",
        r"    \toprule",
        r"    Config & Family & L1 $\delta$ & L2 $\delta$ & L3 $\delta$ & L4 $\delta$ \\",
        r"    \midrule",
    ]
    for display, family, _, _ in CONFIG_ORDER:
        r = results.get(display)
        if r is None:
            continue
        cells = []
        for tier in ("1", "2", "3", "4"):
            t = r["tiers"][tier]
            cells.append(_fmt_cell(t["delta_pp"], t["ci_lo_pp"], t["ci_hi_pp"]))
        lines.append(f"    {display:24s} & {family:9s} & " + " & ".join(cells) + r" \\")
    lines += [
        r"    \bottomrule",
        r"  \end{tabular}",
        r"\end{table}",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--self-test", action="store_true",
                   help="Print overall δ next to Table 9 values; do not render table.")
    p.add_argument("--table", action="store_true",
                   help="Render the LaTeX table snippet (default if no other action).")
    p.add_argument("--json", metavar="OUT",
                   help="Dump the full results dict as JSON to OUT.")
    p.add_argument("--verbose-tiers", action="store_true",
                   help="Print own/other N + accuracy per tier for inspection.")
    args = p.parse_args()

    conn = get_pg()
    run_id = _load_run_id(conn, RUN_TAG)
    answers = _load_answers(conn, run_id, RELEASE)
    print(f"# run_id = {run_id}", file=sys.stderr)
    print(f"# {len(answers)} answers loaded", file=sys.stderr)

    results = compute_sps_by_tier(answers)

    if args.self_test or not (args.table or args.json or args.verbose_tiers):
        # Self-test: compare overall δ against Table 9 values.
        print()
        print(f"{'Config':24s}  {'family':10s}  {'overall δ (pp)':>15s}  {'Table 9':>10s}  {'diff (pp)':>10s}")
        print("-" * 80)
        max_diff = 0.0
        for display, family, _, _ in CONFIG_ORDER:
            r = results.get(display)
            if r is None:
                continue
            d = r["overall"]["delta_pp"]
            t9 = TABLE9_DELTA[display]
            diff = d - t9
            max_diff = max(max_diff, abs(diff))
            ok = "OK" if abs(diff) <= 0.1 else "MISMATCH"
            print(f"{display:24s}  {family:10s}  {d:+15.2f}  {t9:+10.2f}  {diff:+10.2f}  {ok}")
        print(f"\nmax |diff| = {max_diff:.3f} pp (target <= 0.1)")

    if args.verbose_tiers:
        print()
        for display, family, _, _ in CONFIG_ORDER:
            r = results.get(display)
            if r is None:
                continue
            print(f"\n{display} ({family}):")
            print(f"  overall: own n={r['overall']['own_n']}, acc={r['overall']['own_acc']:.1f}% / "
                  f"other n={r['overall']['other_n']}, acc={r['overall']['other_acc']:.1f}% / "
                  f"δ={r['overall']['delta_pp']:+.2f} pp [CI {r['overall']['ci_lo_pp']:+.1f}, {r['overall']['ci_hi_pp']:+.1f}]")
            for tier in ("1", "2", "3", "4"):
                t = r["tiers"][tier]
                print(f"  L{tier}: own n={t['own_n']}, acc={t['own_acc'] if not np.isnan(t['own_acc']) else 'NaN':>5} / "
                      f"other n={t['other_n']}, acc={t['other_acc'] if not np.isnan(t['other_acc']) else 'NaN':>5} / "
                      f"δ={t['delta_pp']:+.2f} pp [CI {t['ci_lo_pp']:+.1f}, {t['ci_hi_pp']:+.1f}]")

    if args.table:
        print()
        print(render_table(results))

    if args.json:
        with open(args.json, "w") as fh:
            json.dump(results, fh, indent=2)
        print(f"# wrote {args.json}", file=sys.stderr)


if __name__ == "__main__":
    main()
