#!/usr/bin/env bash
# Phase 2g.7 audit run #6 — first audit with the retuned gate (threshold
# 0.6, L1/L2/L3 + multiple_choice/scenario_based, GATE_VERSION 2.2.0),
# the new scenario HARD RULE, and the corrected per-corpus quota math.
#
# Generates ~600 fresh questions tagged audit_pilot_v6 (per_strategy=120,
# 5 strategies), runs all 4 audit teams, regenerates the auto reports.
#
# Designed for nohup launch; survives session close. Logs everything to
# data/logs/audit_pilot_v6_full_<timestamp>.log.
set -euo pipefail

cd /home/winebench/oenobench

TS=$(date -u +%Y%m%dT%H%M%SZ)
LOG=data/logs/audit_pilot_v6_full_${TS}.log
TAG=audit_pilot_v6
SEED=43
PER_STRATEGY=120
PY=.venv/bin/python

mkdir -p data/logs

echo "=== Phase 2g.7 audit pilot v6 — start: $(date -u) ===" | tee -a "$LOG"
echo "tag=$TAG  seed=$SEED  per_strategy=$PER_STRATEGY" | tee -a "$LOG"
echo "log=$LOG" | tee -a "$LOG"
echo "" | tee -a "$LOG"

echo "--- [1/3] build-corpus: $(date -u) ---" | tee -a "$LOG"
$PY -m src.qa.orchestrator build-corpus \
    --tag "$TAG" --per-strategy "$PER_STRATEGY" --seed "$SEED" 2>&1 | tee -a "$LOG"

echo "" | tee -a "$LOG"
echo "--- [2/3] run audit teams A,B,C,D: $(date -u) ---" | tee -a "$LOG"
RUN_LOG=data/logs/audit_pilot_v6_run_${TS}.log
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
echo "--- [3/3] build-reports: $(date -u) ---" | tee -a "$LOG"
$PY -m src.qa.orchestrator build-reports --run-id "$RUN_ID" 2>&1 | tee -a "$LOG"

echo "" | tee -a "$LOG"
echo "=== Phase 2g.7 audit pilot v6 — complete: $(date -u) ===" | tee -a "$LOG"
echo "Reports regenerated:" | tee -a "$LOG"
echo "  docs/QUALITY_AUDIT_REPORT.md" | tee -a "$LOG"
echo "  docs/GENERATION_IMPROVEMENT_PLAN_AUTO.md" | tee -a "$LOG"
echo "Run ID: $RUN_ID" | tee -a "$LOG"
