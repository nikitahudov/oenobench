#!/usr/bin/env bash
# Phase 2g.11 audit pilot v9 — phase 2 of 2: run audit teams + build reports.
#
# Prerequisites:
#   * scripts/run_audit_pilot_v9_build.sh has been run (corpus tagged
#     audit_pilot_v9 exists in the questions table).
#   * (Recommended) gold labels for v9 questions have been imported via
#     `import-gold` so build-reports computes valid κ for the v2.3 rubrics.
#     If you skip the gold review, the run still completes — κ just shows
#     n=0 for the populated rubrics, and you can re-run only build-reports
#     after a later import to refresh the κ values.
#
# Cost: ~$2-4 expected on a v9 corpus of ~100-200 questions (linear-scaled
# from v7's $4.42 on 242 q). Wall time: ~30-60 min.
#
# Designed for nohup launch; survives session close. Logs everything to
# data/logs/audit_pilot_v9_audit_<timestamp>.log.
set -euo pipefail

cd /home/winebench/oenobench

# Audit phase 2 also benefits from the speedup levers (the tri-judge panel
# uses the same LLMClient that A1+C1 sped up; the cache helps if any judge
# is asked the same question twice). Keep the same env-var profile as v9
# build, except the substantiveness filter and circuit breaker are no-ops
# at audit time.
export OENOBENCH_LLM_THROTTLE_MS=0
export OENOBENCH_LLM_CACHE=1

TS=$(date -u +%Y%m%dT%H%M%SZ)
LOG=data/logs/audit_pilot_v9_audit_${TS}.log
TAG=audit_pilot_v9
SEED=46
PY=.venv/bin/python

mkdir -p data/logs

echo "=== Phase 2g.11 audit pilot v9 — phase 2 (audit) — start: $(date -u) ===" | tee -a "$LOG"
echo "tag=$TAG  seed=$SEED" | tee -a "$LOG"
echo "throttle_ms=$OENOBENCH_LLM_THROTTLE_MS  cache=$OENOBENCH_LLM_CACHE" | tee -a "$LOG"
echo "log=$LOG" | tee -a "$LOG"
echo "" | tee -a "$LOG"

echo "--- [1/2] run audit teams A,B,C,D: $(date -u) ---" | tee -a "$LOG"
RUN_LOG=data/logs/audit_pilot_v9_run_${TS}.log
$PY -m src.qa.orchestrator run \
    --tag "$TAG" --seed "$SEED" --teams A,B,C,D 2>&1 | tee -a "$LOG" "$RUN_LOG"

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
echo "=== Phase 2g.11 audit pilot v9 — phase 2 complete: $(date -u) ===" | tee -a "$LOG"
echo "Reports:" | tee -a "$LOG"
echo "  docs/QUALITY_AUDIT_REPORT.md" | tee -a "$LOG"
echo "  docs/GENERATION_IMPROVEMENT_PLAN_AUTO.md" | tee -a "$LOG"
echo "Run ID: $RUN_ID" | tee -a "$LOG"
echo "" | tee -a "$LOG"
echo "If you reviewed and imported gold-v9 BEFORE running this, the report" | tee -a "$LOG"
echo "should now show populated Cohen's κ values for the v2.3 rubrics." | tee -a "$LOG"
echo "If not, complete the gold review and re-run only build-reports:" | tee -a "$LOG"
echo "  $PY -m src.qa.orchestrator build-reports --run-id $RUN_ID" | tee -a "$LOG"
