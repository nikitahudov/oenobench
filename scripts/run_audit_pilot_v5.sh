#!/usr/bin/env bash
# Phase 2g.6 audit run #5 — first audit with the v2.0 closed-book gate
# (label+quota) active. Generates ~600 fresh questions tagged audit_pilot_v5,
# runs all 4 audit teams, then regenerates the auto reports.
#
# Designed for nohup launch; survives session close. Logs everything to
# data/logs/audit_pilot_v5_full_<timestamp>.log.
set -euo pipefail

cd /home/winebench/oenobench

TS=$(date -u +%Y%m%dT%H%M%SZ)
LOG=data/logs/audit_pilot_v5_full_${TS}.log
TAG=audit_pilot_v5
SEED=42
PER_STRATEGY=120
PY=.venv/bin/python

mkdir -p data/logs

echo "=== Phase 2g.6 audit pilot v5 — start: $(date -u) ===" | tee -a "$LOG"
echo "tag=$TAG  seed=$SEED  per_strategy=$PER_STRATEGY" | tee -a "$LOG"
echo "log=$LOG" | tee -a "$LOG"
echo "" | tee -a "$LOG"

echo "--- [1/3] build-corpus: $(date -u) ---" | tee -a "$LOG"
$PY -m src.qa.orchestrator build-corpus \
    --tag "$TAG" --per-strategy "$PER_STRATEGY" --seed "$SEED" 2>&1 | tee -a "$LOG"

echo "" | tee -a "$LOG"
echo "--- [2/3] run audit teams A,B,C,D: $(date -u) ---" | tee -a "$LOG"
# Tee the run command's output to a separate file so we can extract the run_id
RUN_LOG=data/logs/audit_pilot_v5_run_${TS}.log
$PY -m src.qa.orchestrator run \
    --tag "$TAG" --seed "$SEED" --teams A,B,C,D 2>&1 | tee -a "$LOG" "$RUN_LOG"

# Extract run_id from the "Audit complete for run <uuid>" line
RUN_ID=$(grep -oE 'Audit complete for run [a-f0-9-]+' "$RUN_LOG" \
    | tail -1 | awk '{print $5}')

if [[ -z "${RUN_ID:-}" ]]; then
    echo "ERROR: could not extract run_id from run log" | tee -a "$LOG"
    exit 1
fi
echo "run_id=$RUN_ID" | tee -a "$LOG"

echo "" | tee -a "$LOG"
echo "--- [3/3] build-reports: $(date -u) ---" | tee -a "$LOG"
$PY -m src.qa.orchestrator build-reports --run-id "$RUN_ID" 2>&1 | tee -a "$LOG"

echo "" | tee -a "$LOG"
echo "=== Phase 2g.6 audit pilot v5 — complete: $(date -u) ===" | tee -a "$LOG"
echo "Reports regenerated:" | tee -a "$LOG"
echo "  docs/QUALITY_AUDIT_REPORT.md" | tee -a "$LOG"
echo "  docs/GENERATION_IMPROVEMENT_PLAN_AUTO.md" | tee -a "$LOG"
echo "Run ID: $RUN_ID" | tee -a "$LOG"
