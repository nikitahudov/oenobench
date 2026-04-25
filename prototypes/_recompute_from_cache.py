"""Re-compute the threshold sweep summary from the cached JSONL verdicts.

Avoids re-spending API budget. Loads `team_alpha_raw_gate.jsonl`, calls
the same `_compute_metrics`/`_l3_metrics`/`_by_qtype_b2_fail` helpers,
and rewrites `team_alpha_results.json` with the cleaner segmented metrics.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Re-use the helpers from the sweep script.
import importlib.util
spec = importlib.util.spec_from_file_location(
    "team_alpha_threshold_sweep",
    ROOT / "prototypes" / "team_alpha_threshold_sweep.py",
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

THRESHOLDS = mod.THRESHOLDS

verdicts = [json.loads(l) for l in open(ROOT / "prototypes" / "team_alpha_raw_gate.jsonl")]
l1l2 = [v for v in verdicts if v["subset"] == "l1l2"]
l3 = [v for v in verdicts if v["subset"] == "l3"]

sweep_all = [mod._compute_metrics(l1l2, t, mc_only=False) for t in THRESHOLDS]
sweep_mc = [mod._compute_metrics(l1l2, t, mc_only=True) for t in THRESHOLDS]
l3_sweep = [mod._l3_metrics(l3, t) for t in THRESHOLDS]
qtype_breakdown = mod._by_qtype_b2_fail(l1l2)

targets = [s for s in sweep_mc if s["projected_fail_rate"] <= 0.15]
if targets:
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

(ROOT / "prototypes" / "team_alpha_results.json").write_text(json.dumps(summary, indent=2))
print(json.dumps(summary, indent=2))
