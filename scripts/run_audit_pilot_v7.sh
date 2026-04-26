#!/usr/bin/env bash
# Phase 2g.8 audit run #7 — first audit with:
#   * Phase 2g.8 cost optimizations 1 + 3 (gate-before-paraphrase template
#     reorder; --provider sort=price routing for verifier + paraphrase).
#   * Phase 2g.8 D3 wire-up fix (--per-country-cap forwarded all the way
#     from this script through build-corpus, _run_generator, every strategy
#     CLI, into the sampler).
#
# Audit_pilot_v6 ran with effectively per_country_cap=None due to the wire-up
# regression (D3 max country ratio 4.52 vs <2.0 target). v7 sets the cap to
# 0.10 explicitly via the flag chain, which the sampler then enforces.
#
# Generates ~600 fresh questions tagged audit_pilot_v7 (per_strategy=120,
# 5 strategies), runs all 4 audit teams, regenerates the auto reports.
#
# Designed for nohup launch; survives session close. Logs everything to
# data/logs/audit_pilot_v7_full_<timestamp>.log.
set -euo pipefail

cd /home/winebench/oenobench

TS=$(date -u +%Y%m%dT%H%M%SZ)
LOG=data/logs/audit_pilot_v7_full_${TS}.log
TAG=audit_pilot_v7
SEED=44
PER_STRATEGY=120
PER_COUNTRY_CAP=0.10
PY=.venv/bin/python

mkdir -p data/logs

echo "=== Phase 2g.8 audit pilot v7 — start: $(date -u) ===" | tee -a "$LOG"
echo "tag=$TAG  seed=$SEED  per_strategy=$PER_STRATEGY  per_country_cap=$PER_COUNTRY_CAP" | tee -a "$LOG"
echo "log=$LOG" | tee -a "$LOG"
echo "" | tee -a "$LOG"

echo "--- [1/3] build-corpus: $(date -u) ---" | tee -a "$LOG"
$PY -m src.qa.orchestrator build-corpus \
    --tag "$TAG" --per-strategy "$PER_STRATEGY" --seed "$SEED" \
    --per-country-cap "$PER_COUNTRY_CAP" 2>&1 | tee -a "$LOG"

echo "" | tee -a "$LOG"
echo "--- [2/3] run audit teams A,B,C,D: $(date -u) ---" | tee -a "$LOG"
RUN_LOG=data/logs/audit_pilot_v7_run_${TS}.log
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
echo "=== Phase 2g.8 audit pilot v7 — complete: $(date -u) ===" | tee -a "$LOG"
echo "Reports regenerated:" | tee -a "$LOG"
echo "  docs/QUALITY_AUDIT_REPORT.md" | tee -a "$LOG"
echo "  docs/GENERATION_IMPROVEMENT_PLAN_AUTO.md" | tee -a "$LOG"
echo "Run ID: $RUN_ID" | tee -a "$LOG"
