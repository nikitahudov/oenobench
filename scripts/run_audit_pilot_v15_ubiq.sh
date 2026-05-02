#!/usr/bin/env bash
# Phase 2g.17 audit pilot v15 — cross-strategy ubiquity guard validation.
#
# Validates the ubiquity-guard fixes shipped by Teams A and B:
#   * Team A: sample-time filter in _fact_sampler.py — rejects ubiquitous-grape
#     facts when the answer entity is a region-class entity
#   * Team B: prompt-level guard in template_generator.py + fact_to_question.py
#     — instructs the LLM to avoid "which region grows X?" framing for
#     internationally ubiquitous varieties
#
# v14c baseline (template + fact_to_question strategies):
#   - 4/15 gold-reviewed questions had ubiquity defects (Cabernet-dominant)
#   - B3 DistractorValidity fails: ~3/4 of ubiquity-flagged questions
#   - A2 FactualAccuracy: borderline on the "ubiquitous" templates
#
# v15 targets:
#   - audit_ubiquity_check.sql returns 0 rows for the audit_pilot_v15_ubiq tag
#   - ubiquity_filtered counter > 0 (guard is actually firing)
#   - B3 fail rate on template + fact_to_question: ≤15%
#
# Cost: ~$1.00–1.80 build + audit (template + fact_to_question only, 20/strategy).
# Wall: ~12-18 min build + ~8 min audit.

set -euo pipefail
cd /home/winebench/oenobench

# ─── Speedup env vars (same as v14) ───────────────────────────────────────────

export OENOBENCH_LLM_THROTTLE_MS=0
export OENOBENCH_LLM_CACHE=1
export OENOBENCH_FACT_SUBSTANTIVE_FILTER=1
export OENOBENCH_CIRCUIT_BREAKER=1
export OENOBENCH_MAX_WORKERS=8
export OENOBENCH_STRATEGY_WORKERS=1   # template + fact_to_question only — no parallel strategies needed

# ─── Phase 2g.15 levers (still active) ────────────────────────────────────────
export OENOBENCH_CB_QUOTA=0.25
export OENOBENCH_MAX_BUILD_PASSES=3

unset OENOBENCH_GATE_MODEL || true
unset OENOBENCH_PARAPHRASE_MODEL || true
unset OENOBENCH_VERIFIER_MODEL || true

# ─── Build configuration ──────────────────────────────────────────────────────

TS=$(date -u +%Y%m%dT%H%M%SZ)
LOG=data/logs/audit_pilot_v15_ubiq_${TS}.log
TAG=audit_pilot_v15_ubiq
SEED=57
PER_STRATEGY=20
PER_COUNTRY_CAP=0.30
GOLD_OUT=data/reports/gold_sheet_v15_ubiq.csv
GOLD_SIZE=10
PY=.venv/bin/python

mkdir -p data/logs data/reports

echo "=== Phase 2g.17 audit pilot v15 (ubiquity guard) — start: $(date -u) ===" | tee -a "$LOG"
echo "tag=$TAG  seed=$SEED  per_strategy=$PER_STRATEGY  per_country_cap=$PER_COUNTRY_CAP" | tee -a "$LOG"
echo "max_build_passes=$OENOBENCH_MAX_BUILD_PASSES  cb_quota=$OENOBENCH_CB_QUOTA" | tee -a "$LOG"
echo "log=$LOG" | tee -a "$LOG"
echo "" | tee -a "$LOG"

START_EPOCH=$(date +%s)

# ─── [1/4] template + fact_to_question build (high-risk strategies only) ─────

echo "--- [1/4] build-corpus (template + fact_to_question only): $(date -u) ---" | tee -a "$LOG"
$PY -m src.qa.orchestrator build-corpus \
    --tag "$TAG" --per-strategy "$PER_STRATEGY" --seed "$SEED" \
    --per-country-cap "$PER_COUNTRY_CAP" \
    --skip comparative \
    --skip scenario_synthesis \
    --skip distractor_mining \
    --max-workers "$OENOBENCH_MAX_WORKERS" \
    --strategy-workers "$OENOBENCH_STRATEGY_WORKERS" 2>&1 | tee -a "$LOG"

# ─── [2/4] export gold sheet for human spot-check ────────────────────────────

echo "" | tee -a "$LOG"
echo "--- [2/4] export-gold (template + fact_to_question): $(date -u) ---" | tee -a "$LOG"
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

# ─── [3/4] targeted audit on the v15 ubiquity tag ────────────────────────────

echo "" | tee -a "$LOG"
echo "--- [3/4] audit (teams A,B,C,D on ubiquity-guard tag): $(date -u) ---" | tee -a "$LOG"
RUN_LOG=data/logs/audit_pilot_v15_ubiq_run_${TS}.log
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

# ─── [4/4] ubiquity audit SQL query ──────────────────────────────────────────

echo "" | tee -a "$LOG"
echo "--- [4/4] ubiquity audit query: $(date -u) ---" | tee -a "$LOG"
UBIQ_COUNT=$(docker exec -i wb-postgres psql -U winebench -d winebench -t -v tag="audit_pilot_v15_ubiq" < scripts/audit_ubiquity_check.sql | grep -c "WB-")
echo "audit_ubiquity_check.sql found $UBIQ_COUNT at-risk questions in v15 tag (target: 0)" | tee -a "$LOG"

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
UBIQUITY_FILTERED=$(grep -c "ubiquity_filtered\|reject.*ubiquitous" "$LOG" || echo 0)

# Pull final paraphrase/category/ubiquity counters via the API as a sanity-check.
COUNTERS=$($PY -c "
from src.generators.template_generator import get_paraphrase_stats, get_category_filtered_count
from src.generators._fact_sampler import get_ubiquity_filtered_count
ps = get_paraphrase_stats()
print(f'paraphrase_ok={ps[\"ok\"]} paraphrase_fail={ps[\"fail\"]} category_filtered={get_category_filtered_count()} ubiquity_filtered={get_ubiquity_filtered_count()}')
" 2>/dev/null || echo "counters_unavailable")

echo "" | tee -a "$LOG"
echo "=== Phase 2g.17 v15 ubiquity guard — complete: $(date -u) ===" | tee -a "$LOG"
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
echo "Ubiquity filtered (log):   $UBIQUITY_FILTERED  (guard active check)" | tee -a "$LOG"
echo "Final counters:            $COUNTERS" | tee -a "$LOG"
echo "Ubiquity SQL row count:    $UBIQ_COUNT  (target: 0)" | tee -a "$LOG"
echo "" | tee -a "$LOG"
echo "Audit run_id: $RUN_ID" | tee -a "$LOG"
echo "" | tee -a "$LOG"
echo "Reports:" | tee -a "$LOG"
echo "  docs/QUALITY_AUDIT_REPORT.md (now reflects $TAG)" | tee -a "$LOG"
echo "  docs/GENERATION_IMPROVEMENT_PLAN_AUTO.md" | tee -a "$LOG"
echo "" | tee -a "$LOG"
echo "Inspect ubiquity-strategy results:" | tee -a "$LOG"
echo "  docker exec wb-postgres psql -U winebench -d winebench -c \\" | tee -a "$LOG"
echo "    \"SELECT q.status, count(*) FROM questions q WHERE '$TAG' = ANY(q.tags) GROUP BY q.status;\"" | tee -a "$LOG"
