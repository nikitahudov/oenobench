#!/usr/bin/env bash
# Phase 2g.13 audit pilot v11 — phase 1 of 2: build corpus with multi-pass loop.
#
# What's new vs v10 (commit 9452c91):
#   * Multi-pass strategy loop in `_run_one_strategy` (Phase 2g.13).
#     OENOBENCH_MAX_BUILD_PASSES=3 retries each strategy until budget
#     filled, sampler ceiling hit, or pass cap reached.
#
# Phase 2g.12 fixes from v10 stay active:
#   * Flash slug → Pro
#   * C4 reject threshold loosened
#   * Cell-allocation rewrite (12 cells × 2 budget per LLM strategy)
#   * JSON fence-strip pre-pass
#   * Truth-tell strategy log
#
# Phase 2g.11 speedup levers stay active (A1+C1, A2, A3, A4, B1, B2, B3, B4, C2).
#
# Build target: per_strategy=24 → 120 questions (matches v10).
#
# v10 baseline (single pass): 53/120 (44%), 9m 21s, 364 LLM calls, $2.82.
# v11 expected (3 passes): ~100-115/120 (~85-95%), ~22-28 min wall,
# ~$6-8 cost. Yield ceiling depends on multi-fact bundle availability —
# fact_to_question already ~88% in v10, so most gain comes from
# comparative/scenario/template (33%, 33%, 29% in v10).
#
# After this script completes:
#   1. Open data/reports/gold_sheet_v11.csv in your spreadsheet.
#   2. Fill in the 10 v2.3 rubric columns following docs/GOLD_REVIEW_GUIDE_V5.md.
#   3. Re-import the filled CSV:
#        python -m src.qa.orchestrator import-gold \
#            --csv-path data/reports/gold_sheet_v11.csv --reviewer nikita
#   4. Then run scripts/run_audit_pilot_v11_audit.sh (TODO).
#
# Designed for nohup launch; survives session close. Logs everything to
# data/logs/audit_pilot_v11_build_<timestamp>.log.
set -euo pipefail

cd /home/winebench/oenobench

# ─── Speedup env vars (same as v10) ───────────────────────────────────────────

export OENOBENCH_LLM_THROTTLE_MS=0
export OENOBENCH_LLM_CACHE=1
export OENOBENCH_FACT_SUBSTANTIVE_FILTER=1
export OENOBENCH_CIRCUIT_BREAKER=1
export OENOBENCH_MAX_WORKERS=8
export OENOBENCH_STRATEGY_WORKERS=3
unset OENOBENCH_GATE_MODEL || true
unset OENOBENCH_PARAPHRASE_MODEL || true
unset OENOBENCH_VERIFIER_MODEL || true

# ─── Phase 2g.13: multi-pass strategy loop ────────────────────────────────────
export OENOBENCH_MAX_BUILD_PASSES=3

# ─── Build configuration ──────────────────────────────────────────────────────

TS=$(date -u +%Y%m%dT%H%M%SZ)
LOG=data/logs/audit_pilot_v11_build_${TS}.log
TAG=audit_pilot_v11
SEED=48
PER_STRATEGY=24
PER_COUNTRY_CAP=0.30
GOLD_OUT=data/reports/gold_sheet_v11.csv
GOLD_SIZE=24
PY=.venv/bin/python

mkdir -p data/logs data/reports

echo "=== Phase 2g.13 audit pilot v11 — phase 1 (build) — start: $(date -u) ===" | tee -a "$LOG"
echo "tag=$TAG  seed=$SEED  per_strategy=$PER_STRATEGY  per_country_cap=$PER_COUNTRY_CAP" | tee -a "$LOG"
echo "max_workers=$OENOBENCH_MAX_WORKERS  strategy_workers=$OENOBENCH_STRATEGY_WORKERS" | tee -a "$LOG"
echo "throttle_ms=$OENOBENCH_LLM_THROTTLE_MS  cache=$OENOBENCH_LLM_CACHE" | tee -a "$LOG"
echo "substantive_filter=$OENOBENCH_FACT_SUBSTANTIVE_FILTER  circuit_breaker=$OENOBENCH_CIRCUIT_BREAKER" | tee -a "$LOG"
echo "max_build_passes=$OENOBENCH_MAX_BUILD_PASSES" | tee -a "$LOG"
echo "log=$LOG" | tee -a "$LOG"
echo "" | tee -a "$LOG"

START_EPOCH=$(date +%s)

echo "--- [1/2] build-corpus: $(date -u) ---" | tee -a "$LOG"
$PY -m src.qa.orchestrator build-corpus \
    --tag "$TAG" --per-strategy "$PER_STRATEGY" --seed "$SEED" \
    --per-country-cap "$PER_COUNTRY_CAP" \
    --max-workers "$OENOBENCH_MAX_WORKERS" \
    --strategy-workers "$OENOBENCH_STRATEGY_WORKERS" 2>&1 | tee -a "$LOG"

echo "" | tee -a "$LOG"
echo "--- [2/2] export-gold: $(date -u) ---" | tee -a "$LOG"
if [[ -f "$GOLD_OUT" ]]; then
    echo "EXISTING $GOLD_OUT detected — skipping export." | tee -a "$LOG"
else
    $PY -m src.qa.orchestrator export-gold \
        --tag "$TAG" --out "$GOLD_OUT" --size "$GOLD_SIZE" --seed "$SEED" 2>&1 | tee -a "$LOG"
fi

END_EPOCH=$(date +%s)
ELAPSED=$((END_EPOCH - START_EPOCH))
ELAPSED_MIN=$((ELAPSED / 60))
ELAPSED_SEC=$((ELAPSED % 60))
LLM_CALLS=$(grep -c "LLM call" "$LOG" || echo 0)
CIRCUIT_BREAKERS=$(grep -c "CIRCUIT BREAKER" "$LOG" || echo 0)
CACHE_HITS=$(grep -c "LLM cache HIT" "$LOG" || echo 0)
GATE_RELABELS=$(grep -c "GATE RELABEL" "$LOG" || echo 0)
GATE_QUOTA_FULL=$(grep -c "GATE QUOTA FULL" "$LOG" || echo 0)
C4_REJECTS=$(grep -c "C4 gen-time REJECT" "$LOG" || echo 0)
PARSE_FAILS=$(grep -c "Parse failed" "$LOG" || echo 0)
FLASH_400S=$(grep -c "flash-preview-20260219 is not a valid" "$LOG" || echo 0)
HAIKU_400S=$(grep -c "haiku-4.5-20251001 is not a valid" "$LOG" || echo 0)
NOPROG_EXITS=$(grep -c "no-progress on pass" "$LOG" || echo 0)
PASS_LINES=$(grep -c "pass [0-9]/[0-9] produced=" "$LOG" || echo 0)

echo "" | tee -a "$LOG"
echo "=== Phase 2g.13 audit pilot v11 — phase 1 complete: $(date -u) ===" | tee -a "$LOG"
echo "" | tee -a "$LOG"
echo "─── Build telemetry ──────────────────────────────────" | tee -a "$LOG"
echo "Wall:                  ${ELAPSED_MIN}m ${ELAPSED_SEC}s  (${ELAPSED}s total)" | tee -a "$LOG"
echo "LLM calls:             $LLM_CALLS" | tee -a "$LOG"
echo "Circuit breakers:      $CIRCUIT_BREAKERS" | tee -a "$LOG"
echo "Cache hits:            $CACHE_HITS  (B1; cold start, fills as build runs)" | tee -a "$LOG"
echo "Gate relabels:         $GATE_RELABELS" | tee -a "$LOG"
echo "Gate quota full:       $GATE_QUOTA_FULL" | tee -a "$LOG"
echo "C4 rejects:            $C4_REJECTS" | tee -a "$LOG"
echo "Parse failures:        $PARSE_FAILS" | tee -a "$LOG"
echo "Flash 400s:            $FLASH_400S  (Phase 2g.12 expected = 0)" | tee -a "$LOG"
echo "Haiku 400s:            $HAIKU_400S  (Phase 2g.12 follow-up expected = 0)" | tee -a "$LOG"
echo "Pass markers logged:   $PASS_LINES  (5 strategies × up to 3 passes = 15 max)" | tee -a "$LOG"
echo "No-progress early exits: $NOPROG_EXITS  (sampler ceiling hits)" | tee -a "$LOG"
echo "" | tee -a "$LOG"
echo "v10 baseline: 9m21s / 364 calls / 4 cb / 0 relabel-quota / 6 C4 / 55 parse / 0 Flash / 2 Haiku / no multi-pass" | tee -a "$LOG"
echo "v9 baseline:  18m / 772 calls / 21 cb / 22 relabel / 113 C4 / 224 parse / ~50 Flash / no multi-pass" | tee -a "$LOG"
echo "" | tee -a "$LOG"
echo "NEXT STEPS (manual):" | tee -a "$LOG"
echo "  1. Open $GOLD_OUT in your spreadsheet" | tee -a "$LOG"
echo "  2. Review per docs/GOLD_REVIEW_GUIDE_V5.md" | tee -a "$LOG"
echo "  3. Re-import: $PY -m src.qa.orchestrator import-gold --csv-path $GOLD_OUT --reviewer nikita" | tee -a "$LOG"
