"""Team α — closed-book gate threshold sweep on audit_pilot_v5.

Re-runs the Sonnet 4.6 closed-book gate against every L1/L2 question in
v5 (and L3 separately) and computes flag rate / precision / recall /
projected non-cb-tagged B2 fail rate at conf thresholds {0.4, 0.5, 0.6, 0.7}.

Strategy: call the gate ONCE per question (cache `selected` + `confidence`),
then apply each threshold post-hoc. The reject decision is purely a
function of (matched_gold, confidence >= threshold), so a single API call
per question gives us all four threshold readings.

Inputs:
    /tmp/v5_l1l2.csv  (header + 194 rows)
    /tmp/v5_l3.csv    (header + 73 rows)

Outputs:
    prototypes/team_alpha_results.json
    prototypes/team_alpha_raw_gate.jsonl  (per-question gate verdicts)

Cost: ~268 API calls @ ~$0.0005 → ~$0.13.
"""

from __future__ import annotations

import csv
import json
import os
import sys
import time
from pathlib import Path

# Ensure imports work when run directly.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.generators import _closed_book_gate as gate
from src.generators._closed_book_gate import GateResult, _format_options, _normalize_letter

THRESHOLDS = [0.4, 0.5, 0.6, 0.7]
L1L2_CSV = "/tmp/v5_l1l2.csv"
L3_CSV = "/tmp/v5_l3.csv"
OUT_JSON = ROOT / "prototypes" / "team_alpha_results.json"
RAW_JSONL = ROOT / "prototypes" / "team_alpha_raw_gate.jsonl"


def _load_rows(path: str) -> list[dict]:
    with open(path) as fh:
        reader = csv.DictReader(fh)
        return list(reader)


def _run_one(stem: str, options_str: str, correct_answer: str) -> dict:
    """Single API call to the gate, returns parsed selected+confidence.

    We bypass the public `screen_question` entry point so we can store the
    raw (selected, confidence) verdict and apply thresholds post-hoc.
    """
    try:
        opts = json.loads(options_str) if options_str else None
    except (json.JSONDecodeError, ValueError):
        opts = None

    if not opts:
        return {"error": "no_options", "selected": None, "confidence": 0.0, "matched_gold": False}

    options_block = _format_options(opts)
    gold_letter = _normalize_letter(correct_answer)
    prompt = gate._PROMPT.format(stem=stem, options_block=options_block)

    t0 = time.time()
    try:
        client = gate._get_client()
        resp = gate._call_gate(client, prompt)
        latency_ms = int((time.time() - t0) * 1000)
        content = resp.choices[0].message.content or ""
        from src.generators._llm_client import _try_parse_json
        parsed = _try_parse_json(content)
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)[:200], "selected": None, "confidence": 0.0, "matched_gold": False, "latency_ms": int((time.time() - t0) * 1000)}

    if not parsed:
        return {"error": "parse_failed", "selected": None, "confidence": 0.0, "matched_gold": False, "latency_ms": latency_ms}

    selected = _normalize_letter(parsed.get("selected"))
    try:
        confidence = float(parsed.get("confidence", 0.0) or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0
    return {
        "selected": selected,
        "confidence": confidence,
        "matched_gold": bool(selected) and selected == gold_letter,
        "reasoning": str(parsed.get("reasoning", ""))[:300],
        "latency_ms": latency_ms,
        "error": None,
    }


def _is_b2_fail(severity: str) -> bool:
    return severity == "fail"


def _compute_metrics(rows_with_verdict: list[dict], threshold: float, mc_only: bool = False) -> dict:
    """Compute flag rate / precision / recall / projected non-cb fail rate.

    The projection treats the v5 NON-CB-tagged L1/L2 subset (101 questions,
    34 fails per the audit) as the population we're trying to clean up.
    `gate_caught_fails` = fails in that subset that the gate would now flag
    at this threshold. Projected fail rate after gate routes them out:

        projected = (B2_fails - gate_caught_fails) / (population - gate_flagged)

    where `population` and `gate_flagged` are restricted to the NON-cb subset
    (the cb subset is already routed via tag and is out of the L1/L2 fail
    population by definition).

    When mc_only=True, restricts both population and gate-flagged set to
    multiple_choice questions — this is the gate's actual reach (the gate
    skips non-MC types by design). The MC-only number is the meaningful
    bound on the gate's contribution; the overall number reflects what the
    gate alone can do for the full L1/L2 population (which also contains
    scenario_synthesis and true_false questions the gate cannot reach).
    """
    non_cb = [r for r in rows_with_verdict if not r["is_cb_tagged"]]
    if mc_only:
        non_cb = [r for r in non_cb if r["question_type"] == "multiple_choice"]
    pop_total = len(non_cb)
    pop_b2_fails = sum(1 for r in non_cb if r["is_b2_fail"])

    flagged = [
        r for r in non_cb
        if r["matched_gold"] and r["confidence"] >= threshold
    ]
    flag_rate = len(flagged) / pop_total if pop_total else 0.0

    tp = sum(1 for r in flagged if r["is_b2_fail"])  # gate-flagged AND b2 fail
    precision = tp / len(flagged) if flagged else 0.0
    recall = tp / pop_b2_fails if pop_b2_fails else 0.0

    projected_remaining_fails = pop_b2_fails - tp
    projected_remaining_pop = pop_total - len(flagged)
    projected_fail_rate = (
        projected_remaining_fails / projected_remaining_pop
        if projected_remaining_pop else 0.0
    )

    return {
        "threshold": threshold,
        "scope": "mc_only" if mc_only else "all_l1l2",
        "population_total": pop_total,
        "population_b2_fails": pop_b2_fails,
        "gate_flagged": len(flagged),
        "flag_rate": round(flag_rate, 4),
        "true_positives": tp,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "projected_remaining_pop": projected_remaining_pop,
        "projected_remaining_fails": projected_remaining_fails,
        "projected_fail_rate": round(projected_fail_rate, 4),
    }


def _by_qtype_b2_fail(rows: list[dict]) -> dict:
    """Per-question-type B2 fail breakdown of the non-cb L1/L2 subset.

    Surfaces the population mix the gate is being asked to clean up: the
    gate touches only `multiple_choice`, so any contribution to overall
    fail rate from `scenario_based` / `true_false` is structurally beyond
    the gate's reach.
    """
    out: dict = {}
    non_cb = [r for r in rows if not r["is_cb_tagged"]]
    qtypes = sorted(set(r["question_type"] for r in non_cb))
    for qt in qtypes:
        sub = [r for r in non_cb if r["question_type"] == qt]
        fails = sum(1 for r in sub if r["is_b2_fail"])
        out[qt] = {
            "total": len(sub),
            "b2_fails": fails,
            "b2_fail_rate": round(fails / len(sub), 4) if sub else 0.0,
        }
    return out


def _l3_metrics(rows_with_verdict: list[dict], threshold: float) -> dict:
    """L3 leakage: % of L3 questions the gate would flag at this threshold."""
    total = len(rows_with_verdict)
    flagged = sum(
        1 for r in rows_with_verdict
        if r["matched_gold"] and r["confidence"] >= threshold
    )
    return {
        "threshold": threshold,
        "l3_total": total,
        "l3_flagged": flagged,
        "l3_leak_rate": round(flagged / total, 4) if total else 0.0,
    }


def main() -> None:
    if not Path(L1L2_CSV).exists() or not Path(L3_CSV).exists():
        raise SystemExit(f"Missing input CSVs: {L1L2_CSV}, {L3_CSV}")

    l1l2_rows = _load_rows(L1L2_CSV)
    l3_rows = _load_rows(L3_CSV)
    print(f"Loaded {len(l1l2_rows)} L1/L2 + {len(l3_rows)} L3 questions")

    raw_path = RAW_JSONL
    raw_path.parent.mkdir(parents=True, exist_ok=True)

    all_verdicts: list[dict] = []

    with open(raw_path, "w") as raw_fh:
        for label, rows in (("l1l2", l1l2_rows), ("l3", l3_rows)):
            for i, row in enumerate(rows):
                if row["question_type"] != "multiple_choice":
                    # Gate only fires on MC. Mirror that here so the metrics
                    # reflect production behaviour.
                    verdict = {
                        "selected": None,
                        "confidence": 0.0,
                        "matched_gold": False,
                        "reasoning": "skipped_non_mc",
                        "error": None,
                        "latency_ms": 0,
                    }
                else:
                    verdict = _run_one(
                        row["question_text"],
                        row["options"],
                        row["correct_answer"],
                    )

                # Tag bookkeeping
                tags_str = row.get("tags") or ""
                is_cb_tagged = "closed_book_solvable" in tags_str

                merged = {
                    "subset": label,
                    "id": row["id"],
                    "question_id": row["question_id"],
                    "difficulty": row["difficulty"],
                    "question_type": row["question_type"],
                    "is_cb_tagged": is_cb_tagged,
                    "is_b2_fail": _is_b2_fail(row.get("b2_severity", "")) if label == "l1l2" else None,
                    "b2_severity": row.get("b2_severity") if label == "l1l2" else None,
                    **verdict,
                }
                raw_fh.write(json.dumps(merged) + "\n")
                all_verdicts.append(merged)

                if (i + 1) % 25 == 0:
                    print(f"  [{label}] {i + 1}/{len(rows)}  conf={verdict.get('confidence')}  matched={verdict.get('matched_gold')}")

    # ─── Compute sweep metrics ───────────────────────────────────────────────

    l1l2_verdicts = [v for v in all_verdicts if v["subset"] == "l1l2"]
    l3_verdicts = [v for v in all_verdicts if v["subset"] == "l3"]

    sweep_all = [_compute_metrics(l1l2_verdicts, t, mc_only=False) for t in THRESHOLDS]
    sweep_mc = [_compute_metrics(l1l2_verdicts, t, mc_only=True) for t in THRESHOLDS]
    l3_sweep = [_l3_metrics(l3_verdicts, t) for t in THRESHOLDS]
    qtype_breakdown = _by_qtype_b2_fail(l1l2_verdicts)

    # ─── Pick recommended threshold ──────────────────────────────────────────
    #
    # The "Go gate" is on the MC-only subset (the gate's reach). Overall
    # fail rate is bounded below by the non-MC contribution, which the
    # gate cannot touch — that's a separate generator-prompt fix
    # (Team β / scenario_synthesis).

    targets = [s for s in sweep_mc if s["projected_fail_rate"] <= 0.15]
    if targets:
        # Pick the loosest (highest) threshold that meets the MC-only gate,
        # to minimise over-routing into the closed_book_solvable bucket.
        recommended = max(targets, key=lambda s: s["threshold"])
        recommendation_note = (
            f"Threshold {recommended['threshold']} achieves projected MC-only "
            f"fail rate {recommended['projected_fail_rate']:.1%} <= 15% Go gate "
            f"(recall {recommended['recall']:.0%}). The OVERALL non-cb L1/L2 "
            f"fail rate stays >15% because non-MC question types "
            f"(scenario_based, true_false) dominate the residual fail "
            f"population and the gate does not fire on them."
        )
    else:
        recommended = min(sweep_mc, key=lambda s: s["projected_fail_rate"])
        recommendation_note = (
            f"NO threshold achieves <=15% projected MC-only fail rate. "
            f"Best available is threshold {recommended['threshold']} at "
            f"{recommended['projected_fail_rate']:.1%}. Gate model upgrade "
            f"(Decision 4) likely required."
        )

    # L3 decision: if any threshold flags >=10% of L3, recommend extending guard.
    l3_at_recommended = next(
        (x for x in l3_sweep if x["threshold"] == recommended["threshold"]),
        None,
    )
    extend_to_l3 = bool(l3_at_recommended and l3_at_recommended["l3_leak_rate"] >= 0.10)

    summary = {
        "v5_run_id": "541d1d1d-1a89-4f5a-8940-218928da3729",
        "thresholds_swept": THRESHOLDS,
        "non_cb_population_qtype_breakdown": qtype_breakdown,
        "l1l2_sweep_all": sweep_all,
        "l1l2_sweep_mc_only": sweep_mc,
        "l3_sweep": l3_sweep,
        "recommended_threshold": recommended["threshold"],
        "recommended_metrics_mc_only": recommended,
        "recommendation_note": recommendation_note,
        "l3_leakage_at_recommended": l3_at_recommended,
        "extend_gate_to_l3": extend_to_l3,
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(summary, indent=2))
    print("\n=== Summary ===")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
