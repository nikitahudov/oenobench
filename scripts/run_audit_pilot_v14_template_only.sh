#!/usr/bin/env bash
# Phase 2g.16 audit pilot v14 — template-only rebuild + targeted audit.
#
# Validates the four template-quality fixes shipped in commit e668a9d:
#   * Lever 1: wine-category-aware distractor pool (cross-category rejection)
#   * Lever 2: substantive-fact floor for template fact sampling
#   * Lever 3: T-GRP-APP-REGION-PLANT-01 distractor strategy rewritten to
#     `same_country_same_category` (was the lone template that failed both
#     gold-reviewed examples in v13)
#   * Lever 4: γ-5 paraphrase 1-shot retry + success/failure counters
#
# v13 baseline (template strategy):
#   - Active questions: 22 (post-promote: 18 after 2 cb_reserve promotions)
#   - B2 ClosedBookSolvability fails: 14/22 = 64%
#   - A4 fingerprint AUC: 0.8397 (corpus-wide, templates dominant contributor)
#   - Gold pass rate: 50% (2/4 sampled templates failed every rubric)
#
# v14 targets:
#   - Active questions: ≥24/30
#   - B2 fail rate: ≤25% (vs v13's 64%)
#   - A4 AUC: <0.80 on the rebuilt template subset
#   - T-GRP-APP-REGION-PLANT-01: zero fails on its 4-8 generated instances
#
# Cost: ~$1.50–2.50 build + audit (much cheaper than full corpus rebuild).
# Wall: ~15-20 min build + ~10 min audit.

set -euo pipefail
cd /home/winebench/oenobench

# ─── Speedup env vars (same as v13) ───────────────────────────────────────────

export OENOBENCH_LLM_THROTTLE_MS=0
export OENOBENCH_LLM_CACHE=1
export OENOBENCH_FACT_SUBSTANTIVE_FILTER=1
export OENOBENCH_CIRCUIT_BREAKER=1
export OENOBENCH_MAX_WORKERS=8
export OENOBENCH_STRATEGY_WORKERS=1   # template-only — no need for parallel strategies

# ─── Phase 2g.15 levers (still active) ────────────────────────────────────────
export OENOBENCH_CB_QUOTA=0.25
export OENOBENCH_MAX_BUILD_PASSES=3   # templates don't need 5 passes

unset OENOBENCH_GATE_MODEL || true
unset OENOBENCH_PARAPHRASE_MODEL || true
unset OENOBENCH_VERIFIER_MODEL || true

# ─── Build configuration ──────────────────────────────────────────────────────

TS=$(date -u +%Y%m%dT%H%M%SZ)
LOG=data/logs/audit_pilot_v14b_only_${TS}.log
TAG=audit_pilot_v14b
SEED=54
PER_STRATEGY=30
PER_COUNTRY_CAP=0.30
GOLD_OUT=data/reports/gold_sheet_v14_template.csv
GOLD_SIZE=15
PY=.venv/bin/python

mkdir -p data/logs data/reports

echo "=== Phase 2g.16 audit pilot v14 (template-only) — start: $(date -u) ===" | tee -a "$LOG"
echo "tag=$TAG  seed=$SEED  per_strategy=$PER_STRATEGY  per_country_cap=$PER_COUNTRY_CAP" | tee -a "$LOG"
echo "max_build_passes=$OENOBENCH_MAX_BUILD_PASSES  cb_quota=$OENOBENCH_CB_QUOTA" | tee -a "$LOG"
echo "log=$LOG" | tee -a "$LOG"
echo "" | tee -a "$LOG"

START_EPOCH=$(date +%s)

# ─── [1/3] template-only build ───────────────────────────────────────────────

echo "--- [1/3] build-corpus (template only): $(date -u) ---" | tee -a "$LOG"
$PY -m src.qa.orchestrator build-corpus \
    --tag "$TAG" --per-strategy "$PER_STRATEGY" --seed "$SEED" \
    --per-country-cap "$PER_COUNTRY_CAP" \
    --skip comparative \
    --skip distractor_mining \
    --skip fact_to_question \
    --skip scenario_synthesis \
    --max-workers "$OENOBENCH_MAX_WORKERS" \
    --strategy-workers "$OENOBENCH_STRATEGY_WORKERS" 2>&1 | tee -a "$LOG"

# ─── [2/3] export gold sheet for human spot-check ────────────────────────────

echo "" | tee -a "$LOG"
echo "--- [2/3] export-gold (template only): $(date -u) ---" | tee -a "$LOG"
if [[ -f "$GOLD_OUT" ]]; then
    echo "EXISTING $GOLD_OUT detected — skipping export." | tee -a "$LOG"
else
    $PY -m src.qa.orchestrator export-gold \
        --tag "$TAG" --out "$GOLD_OUT" --size "$GOLD_SIZE" --seed "$SEED" 2>&1 | tee -a "$LOG"
fi

BUILD_END_EPOCH=$(date +%s)
BUILD_ELAPSED=$((BUILD_END_EPOCH - START_EPOCH))
BUILD_MIN=$((BUILD_ELAPSED / 60))
BUILD_SEC=$((BUILD_ELAPSED % 60))

# ─── [3/3] targeted audit on the v14 template tag ────────────────────────────

echo "" | tee -a "$LOG"
echo "--- [3/3] audit (teams A,B,C,D on template-only tag): $(date -u) ---" | tee -a "$LOG"
RUN_LOG=data/logs/audit_pilot_v14b_run_${TS}.log
$PY -m src.qa.orchestrator run \
    --tag "$TAG" --seed "$((SEED + 1))" --teams A,B,C,D 2>&1 | tee -a "$LOG" "$RUN_LOG"

RUN_ID=$(grep -oE 'Audit complete for run [a-f0-9-]+' "$RUN_LOG" \
    | tail -1 | awk '{print $5}')

if [[ -z "${RUN_ID:-}" ]]; then
    echo "ERROR: could not extract run_id from run log" | tee -a "$LOG"
    exit 1
fi
echo "run_id=$RUN_ID" | tee -a "$LOG"

echo "" | tee -a "$LOG"
echo "--- build-reports for run $RUN_ID: $(date -u) ---" | tee -a "$LOG"
$PY -m src.qa.orchestrator build-reports --run-id "$RUN_ID" 2>&1 | tee -a "$LOG"

END_EPOCH=$(date +%s)
ELAPSED=$((END_EPOCH - START_EPOCH))
ELAPSED_MIN=$((ELAPSED / 60))
ELAPSED_SEC=$((ELAPSED % 60))
LLM_CALLS=$(grep -c "LLM call" "$LOG" || echo 0)
GATE_QUOTA_FULL=$(grep -c "GATE QUOTA FULL" "$LOG" || echo 0)
CB_RESERVED=$(grep -c "GATE QUOTA FULL → RESERVED" "$LOG" || echo 0)
PARSE_RETRY_OK=$(grep -c "parse-retry attempt=1" "$LOG" || echo 0)
CATEGORY_DEPLETED=$(grep -c "template distractor pool depleted by category filter" "$LOG" || echo 0)
PARAPHRASE_FAILS=$(grep -c "template paraphrase FAIL" "$LOG" || echo 0)
ICONIC_FALLBACKS=$(grep -c "iconic-exhaust fallback" "$LOG" || echo 0)

# Pull final paraphrase/category counters via the API as a sanity-check.
COUNTERS=$($PY -c "
from src.generators.template_generator import get_paraphrase_stats, get_category_filtered_count
ps = get_paraphrase_stats()
print(f'paraphrase_ok={ps[\"ok\"]} paraphrase_fail={ps[\"fail\"]} category_filtered={get_category_filtered_count()}')
" 2>/dev/null || echo "counters_unavailable")

echo "" | tee -a "$LOG"
echo "=== Phase 2g.16 v14 template-only — complete: $(date -u) ===" | tee -a "$LOG"
echo "" | tee -a "$LOG"
echo "─── Build + audit telemetry ──────────────────────────────────" | tee -a "$LOG"
echo "Total wall:                ${ELAPSED_MIN}m ${ELAPSED_SEC}s  (${ELAPSED}s)" | tee -a "$LOG"
echo "Build wall:                ${BUILD_MIN}m ${BUILD_SEC}s" | tee -a "$LOG"
echo "LLM calls (build+audit):   $LLM_CALLS" | tee -a "$LOG"
echo "Gate quota full:           $GATE_QUOTA_FULL" | tee -a "$LOG"
echo "cb_reserve banked:         $CB_RESERVED" | tee -a "$LOG"
echo "Parse retries OK:          $PARSE_RETRY_OK" | tee -a "$LOG"
echo "Category-depleted skips:   $CATEGORY_DEPLETED  (Lever 1)" | tee -a "$LOG"
echo "Paraphrase fails:          $PARAPHRASE_FAILS  (Lever 4 — should be 0)" | tee -a "$LOG"
echo "Iconic-exhaust fallbacks:  $ICONIC_FALLBACKS" | tee -a "$LOG"
echo "Final counters:            $COUNTERS" | tee -a "$LOG"
echo "" | tee -a "$LOG"
echo "Audit run_id: $RUN_ID" | tee -a "$LOG"
echo "" | tee -a "$LOG"
echo "Reports:" | tee -a "$LOG"
echo "  docs/QUALITY_AUDIT_REPORT.md (now reflects $TAG)" | tee -a "$LOG"
echo "  docs/GENERATION_IMPROVEMENT_PLAN_AUTO.md" | tee -a "$LOG"
echo "" | tee -a "$LOG"
echo "Inspect template-strategy results:" | tee -a "$LOG"
echo "  docker exec wb-postgres psql -U winebench -d winebench -c \\" | tee -a "$LOG"
echo "    \"SELECT q.status, count(*) FROM questions q WHERE '$TAG' = ANY(q.tags) GROUP BY q.status;\"" | tee -a "$LOG"
