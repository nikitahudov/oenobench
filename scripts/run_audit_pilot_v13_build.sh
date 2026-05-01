#!/usr/bin/env bash
# Phase 2g.15 audit pilot v13 — yield recovery (revert Lever 4+2, raise CB to 15,
# parse-retry, cell rebalance, cb_reserve pool, sampler iconic fallback, headroom).
#
# What's new vs v12 (commit 02252d9):
#   * Team A: Revert Lever 4 — cb_quota 0.20 → 0.25 (env-overridable via
#     OENOBENCH_CB_QUOTA). Revert Lever 2 — iconic-entities list restored
#     7 examples. Raise CellTracker.min_attempts 10 → 15. Parse-failure
#     1-shot retry with stricter "raw JSON only" prompt across all 5 generators.
#   * Team B: cb_reserve question status. GATE QUOTA FULL questions now
#     INSERT with status='cb_reserve' instead of dropped. Read paths filter
#     status != 'cb_reserve' by default. New CLI: promote-from-reserve.
#   * Team C: Cross-pass dead-cell awareness — cells producing 0 rows skipped
#     next pass; budget reallocated to healthy cells. Sampler iconic-exhaust
#     fallback — when iconic pool exhausts, retry with iconic filter off
#     (substantive-only) to fill remaining slots.
#   * Team D: This script (per_strategy=30, max_passes=5, seed=51) + smoke
#     variant + promote-from-reserve wrapper.
#
# Phase 2g.13 multi-pass + cross-pass-dedup levers stay active.
# Phase 2g.12 fixes stay active.
# Phase 2g.11 speedup levers stay active.
#
# Build target: per_strategy=30 → 150 questions generated (target ≥110 kept).
#
# v11: 25m / 86 kept (72%) / $6.37
# v12: 32m / 69 kept (57%) / $5.50
# v13 target: ~32m / ≥110 kept (≥92%) / ~$8-10

set -euo pipefail
cd /home/winebench/oenobench

# ─── Speedup env vars (same as v11/v12) ───────────────────────────────────────

export OENOBENCH_LLM_THROTTLE_MS=0
export OENOBENCH_LLM_CACHE=1
export OENOBENCH_FACT_SUBSTANTIVE_FILTER=1
export OENOBENCH_CIRCUIT_BREAKER=1
export OENOBENCH_MAX_WORKERS=8
export OENOBENCH_STRATEGY_WORKERS=3
unset OENOBENCH_GATE_MODEL || true
unset OENOBENCH_PARAPHRASE_MODEL || true
unset OENOBENCH_VERIFIER_MODEL || true

# ─── Phase 2g.15 Team A: revert Lever 4 — cb quota restored to 0.25 ──────────
export OENOBENCH_CB_QUOTA=0.25

# ─── Phase 2g.15 multi-pass loop (raised from 3 → 5) ─────────────────────────
export OENOBENCH_MAX_BUILD_PASSES=5

# ─── Build configuration ──────────────────────────────────────────────────────

TS=$(date -u +%Y%m%dT%H%M%SZ)
LOG=data/logs/audit_pilot_v13_build_${TS}.log
TAG=audit_pilot_v13
SEED=51
PER_STRATEGY=30
PER_COUNTRY_CAP=0.30
GOLD_OUT=data/reports/gold_sheet_v13.csv
GOLD_SIZE=24
PY=.venv/bin/python

mkdir -p data/logs data/reports

echo "=== Phase 2g.15 audit pilot v13 — phase 1 (build) — start: $(date -u) ===" | tee -a "$LOG"
echo "tag=$TAG  seed=$SEED  per_strategy=$PER_STRATEGY  per_country_cap=$PER_COUNTRY_CAP" | tee -a "$LOG"
echo "max_build_passes=$OENOBENCH_MAX_BUILD_PASSES  workers=$OENOBENCH_MAX_WORKERS" | tee -a "$LOG"
echo "strategy_workers=$OENOBENCH_STRATEGY_WORKERS  cache=$OENOBENCH_LLM_CACHE" | tee -a "$LOG"
echo "cb_quota=$OENOBENCH_CB_QUOTA" | tee -a "$LOG"
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
SONNET_VERIFIER=$(grep -c "model=anthropic/claude-sonnet-4.6" "$LOG" || echo 0)
PASS_LINES=$(grep -c "pass [0-9]/[0-9] produced=" "$LOG" || echo 0)
CB_RESERVED=$(grep -c "GATE QUOTA FULL → RESERVED" "$LOG" || echo 0)
PARSE_RETRY_OK=$(grep -c "parse-retry attempt=1" "$LOG" || echo 0)
DEAD_CELLS_SKIPPED=$(grep -c "skipping .* dead cells" "$LOG" || echo 0)
ICONIC_FALLBACKS=$(grep -c "iconic-exhaust fallback" "$LOG" || echo 0)

echo "" | tee -a "$LOG"
echo "=== Phase 2g.15 audit pilot v13 — phase 1 complete: $(date -u) ===" | tee -a "$LOG"
echo "" | tee -a "$LOG"
echo "─── Build telemetry ──────────────────────────────────" | tee -a "$LOG"
echo "Wall:                  ${ELAPSED_MIN}m ${ELAPSED_SEC}s  (${ELAPSED}s total)" | tee -a "$LOG"
echo "LLM calls:             $LLM_CALLS" | tee -a "$LOG"
echo "Sonnet verifier calls: $SONNET_VERIFIER  (Phase 2g.14 Lever 3' — verifier-claude → Sonnet)" | tee -a "$LOG"
echo "Circuit breakers:      $CIRCUIT_BREAKERS" | tee -a "$LOG"
echo "Cache hits:            $CACHE_HITS" | tee -a "$LOG"
echo "Gate relabels:         $GATE_RELABELS" | tee -a "$LOG"
echo "Gate quota full:       $GATE_QUOTA_FULL  (Phase 2g.15 — cb cap restored to 25%)" | tee -a "$LOG"
echo "C4 rejects:            $C4_REJECTS" | tee -a "$LOG"
echo "Parse failures:        $PARSE_FAILS" | tee -a "$LOG"
echo "Flash 400s:            $FLASH_400S  (expected = 0)" | tee -a "$LOG"
echo "Haiku 400s:            $HAIKU_400S  (expected = 0)" | tee -a "$LOG"
echo "Pass markers:          $PASS_LINES" | tee -a "$LOG"
echo "cb_reserve banked:     $CB_RESERVED  (Phase 2g.15 Team B — quota-full → reserved)" | tee -a "$LOG"
echo "Parse retries OK:      $PARSE_RETRY_OK  (Phase 2g.15 Team A — 1-shot parse retry)" | tee -a "$LOG"
echo "Dead cells skipped:    $DEAD_CELLS_SKIPPED  (Phase 2g.15 Team C — cross-pass dead-cell awareness)" | tee -a "$LOG"
echo "Iconic-exhaust fallbacks: $ICONIC_FALLBACKS  (Phase 2g.15 Team C — substantive fallback)" | tee -a "$LOG"
echo "" | tee -a "$LOG"
echo "v11: 25m / 86 kept (72%) / \$6.37; v12: 32m / 69 kept (57%) / \$5.50; v13 target: ~32m / ≥110 kept (≥92%) / ~\$8-10" | tee -a "$LOG"
