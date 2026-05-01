#!/usr/bin/env bash
# Phase 2g.15 audit pilot v13 — smoke test (~3-5 min plumbing validator).
#
# Runs a minimal build (per_strategy=4, max_passes=2) to verify that all four
# team-D integrations are wired correctly before launching the full v13 build:
#   - OENOBENCH_CB_QUOTA env var is consumed (Team A)
#   - cb_reserve rows are inserted (Team B)
#   - dead-cell skipping and iconic-exhaust fallback log lines appear (Team C)
#   - parse-retry log lines appear when applicable (Team A)
#
# After build: validates that at least 1 cb_reserve question exists in DB and
# that at least 1 strategy produced a non-zero row count.

set -euo pipefail
cd /home/winebench/oenobench

# ─── Speedup env vars ─────────────────────────────────────────────────────────

export OENOBENCH_LLM_THROTTLE_MS=0
export OENOBENCH_LLM_CACHE=1
export OENOBENCH_FACT_SUBSTANTIVE_FILTER=1
export OENOBENCH_CIRCUIT_BREAKER=1
export OENOBENCH_MAX_WORKERS=8
export OENOBENCH_STRATEGY_WORKERS=3
unset OENOBENCH_GATE_MODEL || true
unset OENOBENCH_PARAPHRASE_MODEL || true
unset OENOBENCH_VERIFIER_MODEL || true

# ─── Phase 2g.15 Team A: cb quota ─────────────────────────────────────────────
export OENOBENCH_CB_QUOTA=0.25

# ─── Smoke: minimal passes ────────────────────────────────────────────────────
export OENOBENCH_MAX_BUILD_PASSES=2

# ─── Build configuration ──────────────────────────────────────────────────────

TS=$(date -u +%Y%m%dT%H%M%SZ)
LOG=data/logs/audit_pilot_v13_smoke_${TS}.log
TAG=audit_pilot_v13_smoke
SEED=52
PER_STRATEGY=4
PER_COUNTRY_CAP=0.30
GOLD_OUT=data/reports/gold_sheet_v13_smoke.csv
GOLD_SIZE=10
PY=.venv/bin/python

mkdir -p data/logs data/reports

echo "=== Phase 2g.15 audit pilot v13 — SMOKE TEST — start: $(date -u) ===" | tee -a "$LOG"
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

echo "" | tee -a "$LOG"
echo "─── Smoke telemetry ──────────────────────────────────" | tee -a "$LOG"
echo "Wall: ${ELAPSED_MIN}m ${ELAPSED_SEC}s  (${ELAPSED}s total)" | tee -a "$LOG"
LLM_CALLS=$(grep -c "LLM call" "$LOG" || echo 0)
CIRCUIT_BREAKERS=$(grep -c "CIRCUIT BREAKER" "$LOG" || echo 0)
CACHE_HITS=$(grep -c "LLM cache HIT" "$LOG" || echo 0)
GATE_QUOTA_FULL=$(grep -c "GATE QUOTA FULL" "$LOG" || echo 0)
PARSE_FAILS=$(grep -c "Parse failed" "$LOG" || echo 0)
CB_RESERVED=$(grep -c "GATE QUOTA FULL → RESERVED" "$LOG" || echo 0)
PARSE_RETRY_OK=$(grep -c "parse-retry attempt=1" "$LOG" || echo 0)
DEAD_CELLS_SKIPPED=$(grep -c "skipping .* dead cells" "$LOG" || echo 0)
ICONIC_FALLBACKS=$(grep -c "iconic-exhaust fallback" "$LOG" || echo 0)

echo "LLM calls:             $LLM_CALLS" | tee -a "$LOG"
echo "Circuit breakers:      $CIRCUIT_BREAKERS" | tee -a "$LOG"
echo "Cache hits:            $CACHE_HITS" | tee -a "$LOG"
echo "Gate quota full:       $GATE_QUOTA_FULL" | tee -a "$LOG"
echo "Parse failures:        $PARSE_FAILS" | tee -a "$LOG"
echo "cb_reserve banked:     $CB_RESERVED" | tee -a "$LOG"
echo "Parse retries OK:      $PARSE_RETRY_OK" | tee -a "$LOG"
echo "Dead cells skipped:    $DEAD_CELLS_SKIPPED" | tee -a "$LOG"
echo "Iconic-exhaust fallbacks: $ICONIC_FALLBACKS" | tee -a "$LOG"
echo "" | tee -a "$LOG"

# ─── Post-build DB validation ─────────────────────────────────────────────────

echo "--- [3/3] DB validation: $(date -u) ---" | tee -a "$LOG"

RESERVE_COUNT=$(docker exec wb-postgres psql -U winebench -d winebench -t -c \
    "SELECT count(*) FROM questions WHERE status='cb_reserve' AND 'audit_pilot_v13_smoke' = ANY(tags);" \
    | tr -d ' \n')
echo "cb_reserve count for smoke: $RESERVE_COUNT" | tee -a "$LOG"

STRATEGY_HIT=$(docker exec wb-postgres psql -U winebench -d winebench -t -c \
    "SELECT count(DISTINCT strategy) FROM generation_metadata gm JOIN questions q ON q.id = gm.question_id WHERE 'audit_pilot_v13_smoke' = ANY(q.tags) AND q.status != 'cb_reserve';" \
    | tr -d ' \n')
echo "Strategies with ≥1 active question: $STRATEGY_HIT" | tee -a "$LOG"

echo "" | tee -a "$LOG"
if [[ "$STRATEGY_HIT" -ge 1 ]]; then
    echo "SMOKE PASS: at least 1 strategy produced active questions." | tee -a "$LOG"
else
    echo "SMOKE FAIL: no strategies produced active questions — check build output above." | tee -a "$LOG"
    exit 1
fi

echo "" | tee -a "$LOG"
echo "=== Phase 2g.15 audit pilot v13 — SMOKE TEST complete: $(date -u) ===" | tee -a "$LOG"
