#!/usr/bin/env bash
# Phase 2g.18 audit pilot v16 — phase 2 of 2: run audit teams + build reports.
#
# Plan: /home/winebench/.claude/plans/virtual-snacking-anchor.md
#
# This is the cost-down v16 cost-validation pilot. The audit-side levers
# (L7 d1-sample 20→10, L8 C4 dropped) are activated by command-line flags
# below; the L2 (B1/B2 "claude" judge → Sonnet) and L3 (B2 panel slim 5→4)
# levers fire automatically through Team B's code edits in src/qa/_judges.py
# and src/qa/agents/team_b_validity.py.
#
# Active levers in this audit (Phase 2g.18):
#
#   L2  B1/B2 "claude" judge resolves to Sonnet 4.6  (Team B code; D1
#       SelfPreference evaluator stays on Opus 4.7 to preserve calibration).
#   L3  B2 panel slim 5 → 4 judges  (Team B code; drops chatgpt, keeps
#       claude/gemini/llama/qwen — preserves Llama+Qwen calibration anchors
#       plus 2 premium signals for triangulation).
#   L7  D1 d1-sample 20 → 10  (--d1-sample 10 below; 5 generators × 5
#       evaluators × 10 samples = 250 calls instead of 500).
#   L8  C4 dropped from default audit  (no --include-c4 flag below;
#       difficulty calibration is informational, not a Go gate).
#
# Prerequisites:
#   * scripts/run_audit_pilot_v16_build.sh has been run (corpus tagged
#     audit_pilot_v16 exists in the questions table).
#   * (Recommended) gold labels for v16 questions have been imported via
#     `import-gold` so build-reports computes valid κ for the v2.3 rubrics.
#     If you skip the gold review, the run still completes — κ just shows
#     n=0 for the populated rubrics, and you can re-run only build-reports
#     after a later import to refresh the κ values.
#
# Cost: ~$0.50 expected on a v16 corpus of ~50 questions (vs v15_ubiq's
# $0.61 / 35 Qs / 380 calls baseline). Wall time: ~20-40 min.
#
# Designed for nohup launch; survives session close. Logs everything to
# data/logs/audit_pilot_v16_audit_<timestamp>.log.
set -euo pipefail

cd /home/winebench/oenobench

# Audit phase 2 also benefits from the speedup levers (the tri-judge panel
# uses the same LLMClient that A1+C1 sped up; the cache helps if any judge
# is asked the same question twice). Keep the same env-var profile as v16
# build, except the substantiveness filter and circuit breaker are no-ops
# at audit time.
export OENOBENCH_LLM_THROTTLE_MS=0
export OENOBENCH_LLM_CACHE=1

TS=$(date -u +%Y%m%dT%H%M%SZ)
LOG=data/logs/audit_pilot_v16_audit_${TS}.log
TAG=audit_pilot_v16
SEED=60   # build seed + 1 (build used 59)
PY=.venv/bin/python

mkdir -p data/logs

echo "=== Phase 2g.18 audit pilot v16 — phase 2 (audit) — start: $(date -u) ===" | tee -a "$LOG"
echo "tag=$TAG  seed=$SEED" | tee -a "$LOG"
echo "throttle_ms=$OENOBENCH_LLM_THROTTLE_MS  cache=$OENOBENCH_LLM_CACHE" | tee -a "$LOG"
echo "levers active: L2 (B1/B2 claude→Sonnet), L3 (B2 panel 4-judge), L7 (--d1-sample 10), L8 (C4 dropped)" | tee -a "$LOG"
echo "log=$LOG" | tee -a "$LOG"
echo "" | tee -a "$LOG"

echo "--- [1/2] run audit teams A,B,C,D (with --d1-sample 10, no --include-c4): $(date -u) ---" | tee -a "$LOG"
RUN_LOG=data/logs/audit_pilot_v16_run_${TS}.log
$PY -m src.qa.orchestrator run \
    --tag "$TAG" --seed "$SEED" --teams A,B,C,D \
    --d1-sample 10 2>&1 | tee -a "$LOG" "$RUN_LOG"

RUN_ID=$(grep -oE 'Audit complete for run [a-f0-9-]+' "$RUN_LOG" \
    | tail -1 | awk '{print $5}')

if [[ -z "${RUN_ID:-}" ]]; then
    echo "ERROR: could not extract run_id from run log" | tee -a "$LOG"
    exit 1
fi
echo "run_id=$RUN_ID" | tee -a "$LOG"

echo "" | tee -a "$LOG"
echo "--- [2/2] build-reports: $(date -u) ---" | tee -a "$LOG"
$PY -m src.qa.orchestrator build-reports --run-id "$RUN_ID" 2>&1 | tee -a "$LOG"

echo "" | tee -a "$LOG"
echo "=== Phase 2g.18 audit pilot v16 — phase 2 complete: $(date -u) ===" | tee -a "$LOG"
echo "Reports:" | tee -a "$LOG"
echo "  docs/QUALITY_AUDIT_REPORT.md" | tee -a "$LOG"
echo "  docs/GENERATION_IMPROVEMENT_PLAN_AUTO.md" | tee -a "$LOG"
echo "Run ID: $RUN_ID" | tee -a "$LOG"
echo "" | tee -a "$LOG"
echo "If you reviewed and imported gold-v16 BEFORE running this, the report" | tee -a "$LOG"
echo "should now show populated Cohen's κ values for the v2.3 rubrics." | tee -a "$LOG"
echo "If not, complete the gold review and re-run only build-reports:" | tee -a "$LOG"
echo "  $PY -m src.qa.orchestrator build-reports --run-id $RUN_ID" | tee -a "$LOG"
echo "" | tee -a "$LOG"
echo "Sanity checks (Phase 2g.18 cost-down validation):" | tee -a "$LOG"
echo "  * grep -E 'Cost: \\\\\$' docs/QUALITY_AUDIT_REPORT.md | head -3   # audit cost line at top of report" | tee -a "$LOG"
echo "  * grep -c 'LLM call' \$LOG                                     # total audit LLM calls (target: ≤ ~250 with L3+L7)" | tee -a "$LOG"
echo "  * grep -E 'B1 .* fail|B2 .* fail' docs/QUALITY_AUDIT_REPORT.md  # confirm fail-rate within ±3pp of v15_ubiq" | tee -a "$LOG"
echo "  * Per-Q cost target: ≤ \\\$0.045 (= \\\$4.50 / 100); compare audit cost / kept-Q against this" | tee -a "$LOG"
