"""SPS own-N / other-N counts per config (Team D, M4 fix for Table 9).

For each of the 13 SPS-eligible configs in Table 9 of paper/sections/
09_appendix_evaluation.tex, this script computes:

    own_n   — number of release_v1.2 questions whose generator family
              matches the config's family (used as the "own" pool).
    other_n — number of release_v1.2 questions whose generator family
              is NOT the config's family AND is not None (templates and
              human_authored count as None and are excluded).

It also verifies that own_n + other_n + template_n = 3,266, and
self-tests that the existing Table 9 δ values are reproducible from the
data (re-using the bootstrap CI computation in analysis.sps_by_tier).

Run from the repo root with the project venv activated:

    source .venv/bin/activate
    python -m analysis.sps_n_counts                    # print counts table
    python -m analysis.sps_n_counts --self-test         # also reproduce δ
    python -m analysis.sps_n_counts --latex-rows        # emit Table 9 rows

The two integer columns own_n and other_n are intended to slot into a
modified Table 9 between the "Family" cell and the "own (%)" cell.
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from typing import Any

import numpy as np

from src.utils.db import get_pg

# ---------------------------------------------------------------------------
# Constants — must match Table 9 / src/evaluation/report.py / analysis/sps_by_tier.py
# ---------------------------------------------------------------------------

RUN_TAG = "eval_release_v1_2_full"
RELEASE = "v1.2"

# generator enum value → config family. Mirrors GENERATOR_TO_FAMILY in
# src/evaluation/report.py. template_only / human_authored / NULL are
# treated as "non-family" (excluded from both own and other pools — only
# the templates count as "non-family for everyone" by virtue of None).
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


def _rc_key(rc):
    """Reasoning-config key — must match _row_compound_key in report.py."""
    if rc is None or rc == {} or rc == "":
        return None
    return tuple(sorted(rc.items()))


# (display name, family, model_name, reasoning_config-key) tuples in the
# same order as Table 9 in paper/sections/09_appendix_evaluation.tex.
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

# Existing Table 9 reference values (from paper/sections/09_appendix_evaluation.tex).
TABLE9_REF = {
    "claude-haiku-4.5":         {"own": 58.8, "other": 48.8, "delta": +10.0,
                                  "ci": "[+5.7, +14.5]"},
    "claude-opus-4.7":          {"own": 86.6, "other": 77.5, "delta": +9.1,
                                  "ci": "[+6.1, +12.1]"},
    "claude-opus-4.7-thinking": {"own": 86.9, "other": 77.2, "delta": +9.7,
                                  "ci": "[+6.5, +13.1]"},
    "qwen-2.5-7b":              {"own": 60.9, "other": 51.9, "delta": +9.0,
                                  "ci": "[+4.5, +13.2]"},
    "qwen-2.5-72b":             {"own": 66.1, "other": 64.1, "delta": +2.0,
                                  "ci": "[-2.1, +6.0]"},
    "llama-3.3-70b":            {"own": 65.5, "other": 63.6, "delta": +1.9,
                                  "ci": "[-2.3, +6.1]"},
    "gpt-5-mini":               {"own": 77.9, "other": 76.1, "delta": +1.7,
                                  "ci": "[-2.4, +5.4]"},
    "o3":                       {"own": 81.9, "other": 82.1, "delta": -0.1,
                                  "ci": "[-3.9, +3.3]"},
    "gpt-5":                    {"own": 79.7, "other": 81.4, "delta": -1.7,
                                  "ci": "[-5.4, +2.1]"},
    "llama-3.1-8b":             {"own": 54.2, "other": 57.2, "delta": -3.0,
                                  "ci": "[-7.3, +1.4]"},
    "gemini-2.5-pro":           {"own": 75.0, "other": 81.1, "delta": -6.1,
                                  "ci": "[-10.7, -1.8]"},
    "gemini-2.5-pro-thinking":  {"own": 74.0, "other": 82.0, "delta": -8.0,
                                  "ci": "[-12.3, -3.8]"},
    "gemini-2.5-flash":         {"own": 64.3, "other": 74.7, "delta": -10.4,
                                  "ci": "[-15.3, -5.6]"},
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
    sql = """
        SELECT
            a.model_name,
            a.reasoning_config,
            a.question_id,
            a.is_correct,
            gm.generator::text AS generator
        FROM evaluation_answers a
        JOIN public.questions q ON q.id = a.question_id
        LEFT JOIN public.generation_metadata gm ON gm.question_id = q.id
        WHERE a.run_id = %s AND %s = ANY(q.tags)
    """
    with conn.cursor() as cur:
        cur.execute(sql, (run_id, f"release_{release}"))
        return [dict(r) for r in cur.fetchall()]


def _load_corpus_generator_counts(conn, release: str = "v1.2") -> dict[str | None, int]:
    """Return generator → question count for the release_v1.2 corpus."""
    sql = """
        SELECT  gm.generator::text AS generator,
                COUNT(*) AS n
        FROM    public.questions q
        LEFT JOIN public.generation_metadata gm ON gm.question_id = q.id
        WHERE   %s = ANY(q.tags) AND q.status::text = 'draft'
        GROUP BY gm.generator
    """
    with conn.cursor() as cur:
        cur.execute(sql, (f"release_{release}",))
        return {r["generator"]: int(r["n"]) for r in cur.fetchall()}


# ---------------------------------------------------------------------------
# Bootstrap (matches src/evaluation/report.py::_section_sps)
# ---------------------------------------------------------------------------


def _delta_ci(own: np.ndarray, other: np.ndarray, n_boot: int = 1000,
              seed: int = 42) -> tuple[float, float, float]:
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
    buckets: dict[tuple[str, Any], list[dict]] = defaultdict(list)
    for r in answers:
        key = (r["model_name"], _rc_key(r.get("reasoning_config")))
        buckets[key].append(r)
    return buckets


def compute(answers: list[dict]) -> dict[str, dict]:
    buckets = _bucket_answers(answers)
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
        own = np.array(
            [1 if r.get("is_correct") else 0 for r in rows
             if r["_gen_family"] == family],
            dtype=float,
        )
        other = np.array(
            [1 if r.get("is_correct") else 0 for r in rows
             if r["_gen_family"] not in (None, family)],
            dtype=float,
        )
        d, lo, hi = _delta_ci(own, other)
        out[display] = {
            "family": family,
            "own_n": int(len(own)),
            "other_n": int(len(other)),
            "own_acc": float(own.mean() * 100) if len(own) else float("nan"),
            "other_acc": float(other.mean() * 100) if len(other) else float("nan"),
            "delta_pp": d,
            "ci_lo_pp": lo,
            "ci_hi_pp": hi,
        }
    return out


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------


def _print_text_table(results: dict[str, dict]) -> None:
    print()
    print(f"{'Config':28s} {'Family':10s} {'own_n':>6s} {'other_n':>8s} "
          f"{'own%':>7s} {'other%':>8s} {'δ pp':>7s}")
    print("-" * 78)
    for display, _, _, _ in CONFIG_ORDER:
        r = results.get(display)
        if r is None:
            continue
        print(f"{display:28s} {r['family']:10s} {r['own_n']:>6d} {r['other_n']:>8d} "
              f"{r['own_acc']:>6.1f}% {r['other_acc']:>7.1f}% {r['delta_pp']:>+6.1f}")


def _self_test(results: dict[str, dict]) -> None:
    """Cross-check overall own_acc / other_acc / δ against Table 9 values."""
    print()
    print(f"{'Config':28s} {'own%':>7s} {'T9-own%':>9s} {'other%':>8s} "
          f"{'T9-other%':>11s} {'δ pp':>7s} {'T9-δ':>7s} {'OK?':>6s}")
    print("-" * 90)
    max_diff = 0.0
    all_ok = True
    for display, _, _, _ in CONFIG_ORDER:
        r = results.get(display)
        if r is None:
            continue
        ref = TABLE9_REF[display]
        own_diff = abs(r["own_acc"] - ref["own"])
        other_diff = abs(r["other_acc"] - ref["other"])
        delta_diff = abs(r["delta_pp"] - ref["delta"])
        row_max = max(own_diff, other_diff, delta_diff)
        max_diff = max(max_diff, row_max)
        ok = "OK" if row_max <= 0.1 else "MISMATCH"
        if ok != "OK":
            all_ok = False
        print(f"{display:28s} {r['own_acc']:>6.1f}% {ref['own']:>8.1f}% "
              f"{r['other_acc']:>7.1f}% {ref['other']:>10.1f}% "
              f"{r['delta_pp']:>+6.1f} {ref['delta']:>+6.1f} {ok:>6s}")
    print()
    print(f"max |diff| across own/other/δ = {max_diff:.3f} pp (target ≤ 0.1)")
    print(f"reproducibility: {'PASS' if all_ok else 'FAIL'}")


def _emit_latex_rows(results: dict[str, dict]) -> None:
    """Emit the 13 data rows for the new Table 9 (with own_n / other_n columns)."""
    print()
    for display, _, _, _ in CONFIG_ORDER:
        r = results.get(display)
        if r is None:
            continue
        ref = TABLE9_REF[display]
        delta = r["delta_pp"]
        sign = "+" if delta >= 0 else "-"
        delta_str = f"${sign}{abs(delta):.1f}$"
        # Emit row matching existing Table 9 styling exactly:
        # display & family & own_n & other_n & own% & other% & δ & CI \\
        print(
            f"    {display:28s} & {r['family']:9s} & "
            f"{r['own_n']:>4d} & {r['other_n']:>5d} & "
            f"{r['own_acc']:>4.1f} & {r['other_acc']:>4.1f} & "
            f"{delta_str:<8s} & {ref['ci']:<18s} \\\\"
        )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--self-test", action="store_true",
                   help="Cross-check own%, other%, δ against Table 9 reference values.")
    p.add_argument("--latex-rows", action="store_true",
                   help="Emit the 13 LaTeX data rows for the modified Table 9.")
    p.add_argument("--all", action="store_true",
                   help="Run text table + self-test + latex rows.")
    args = p.parse_args()

    conn = get_pg()
    run_id = _load_run_id(conn, RUN_TAG)
    answers = _load_answers(conn, run_id, RELEASE)
    print(f"# run_id = {run_id}", file=sys.stderr)
    print(f"# {len(answers)} answers loaded", file=sys.stderr)

    # Verify totals against the corpus.
    gen_counts = _load_corpus_generator_counts(conn, RELEASE)
    template_n = sum(n for g, n in gen_counts.items() if g in (None, "template_only", "human_authored"))
    non_template_n = sum(n for g, n in gen_counts.items() if g not in (None, "template_only", "human_authored"))
    total_n = template_n + non_template_n
    print(f"# release_v1.2 corpus generator distribution: {gen_counts}", file=sys.stderr)
    print(f"# total = {total_n}, template = {template_n}, non-template = {non_template_n}", file=sys.stderr)

    results = compute(answers)

    # Sanity: own_n + other_n must equal non_template_n for every config.
    for display, r in results.items():
        s = r["own_n"] + r["other_n"]
        if s != non_template_n:
            print(f"# WARN: {display} own+other = {s} ≠ non-template corpus = {non_template_n}",
                  file=sys.stderr)

    if args.all or not (args.self_test or args.latex_rows):
        _print_text_table(results)

    if args.all or args.self_test:
        _self_test(results)

    if args.all or args.latex_rows:
        _emit_latex_rows(results)


if __name__ == "__main__":
    main()
