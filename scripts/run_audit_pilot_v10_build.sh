#!/usr/bin/env bash
# Phase 2g.12 audit pilot v10 — phase 1 of 2: build corpus + export gold sheet.
#
# What's new vs v9:
#   * Phase 2g.12 corpus-undershoot fixes (commit 2aa084a):
#       - Flash slug → Pro (kills OpenRouter 400s on every paraphrase + verify)
#       - C4 reject threshold loosened (L1/L2 tolerate delta=2)
#       - LLM-strategy cell-allocation rewrite (cell_count = max(1, min(G*D, want//2))
#         so each cell carries ≥2 budget; total scheduled budget == want)
#       - JSON fence-strip pre-pass in _try_parse_json (recovers Gemini malformations)
#       - Truth-tell strategy log (logs actual rowcount, not budget, as `generated`)
#
# Phase 2g.11 speedup levers stay active:
#   A1+C1 throttle removal + LLM timeout/failover
#   A2     in-process strategy dispatch
#   A3     ThreadPoolExecutor over (generator × domain) cells
#   A4     ThreadPoolExecutor over top-level strategies
#   B1     content-hash cache for gate / verifier / paraphrase
#   B2     substantiveness pre-filter at the sampler
#   B3     per-cell circuit breaker + budget reallocation
#   B4     tier-aware gate model (Haiku L1 / Sonnet L2 / Opus L3)
#   C2     Flash variant for paraphrase + verifier (now resolves to Pro)
#
# Build target: per_strategy=24 → 120 questions (5 strategies × 24 each).
# Cell-allocation math (Phase 2g.12): cell_count = min(30, 24//2) = 12 cells × 2
# budget each per LLM strategy. Saturated.
#
# Expected wall vs v9 (18 min, 100 budget): ~22 min for 120 budget.
# Expected LLM calls: ~900 (v9 was 772 with 100 budget; the fixes eliminate
# ~228 wasted calls — flash 400s, C4 rejects, parse failures — but the larger
# budget + better cell saturation will add productive calls).
# Expected kept: 90-110 of 120 (75-92%) per the Phase 2g.12 design estimate.
# Estimated cost: ~$5-8 (Gemini Pro paraphrase/verify dominates; Opus gate ~$2).
#
# After this script completes:
#   1. Open data/reports/gold_sheet_v10.csv in your spreadsheet of choice.
#   2. Fill in the 10 v2.3 rubric columns following docs/GOLD_REVIEW_GUIDE_V5.md.
#   3. Re-import the filled CSV:
#        python -m src.qa.orchestrator import-gold \
#            --csv-path data/reports/gold_sheet_v10.csv --reviewer nikita
#   4. Then run scripts/run_audit_pilot_v10_audit.sh to execute the audit
#      teams + build reports.
#
# Designed for nohup launch; survives session close. Logs everything to
# data/logs/audit_pilot_v10_build_<timestamp>.log.
set -euo pipefail

cd /home/winebench/oenobench

# ─── Speedup env vars (same as v9) ────────────────────────────────────────────

export OENOBENCH_LLM_THROTTLE_MS=0
export OENOBENCH_LLM_CACHE=1
export OENOBENCH_FACT_SUBSTANTIVE_FILTER=1
export OENOBENCH_CIRCUIT_BREAKER=1
export OENOBENCH_MAX_WORKERS=8
export OENOBENCH_STRATEGY_WORKERS=3
unset OENOBENCH_GATE_MODEL || true
unset OENOBENCH_PARAPHRASE_MODEL || true
unset OENOBENCH_VERIFIER_MODEL || true

# ─── Build configuration ──────────────────────────────────────────────────────

TS=$(date -u +%Y%m%dT%H%M%SZ)
LOG=data/logs/audit_pilot_v10_build_${TS}.log
TAG=audit_pilot_v10
SEED=47
# v10 sized at total=120 (per_strategy=24) to test the Phase 2g.12 fixes
# under a slightly larger budget than v9 (100). Cell allocation now gives
# 12 cells × 2 budget per LLM strategy — every cell carries enough budget
# that a single sampler-empty doesn't kill its yield.
PER_STRATEGY=24
PER_COUNTRY_CAP=0.30
GOLD_OUT=data/reports/gold_sheet_v10.csv
GOLD_SIZE=24
PY=.venv/bin/python

mkdir -p data/logs data/reports

echo "=== Phase 2g.12 audit pilot v10 — phase 1 (build) — start: $(date -u) ===" | tee -a "$LOG"
echo "tag=$TAG  seed=$SEED  per_strategy=$PER_STRATEGY  per_country_cap=$PER_COUNTRY_CAP" | tee -a "$LOG"
echo "max_workers=$OENOBENCH_MAX_WORKERS  strategy_workers=$OENOBENCH_STRATEGY_WORKERS" | tee -a "$LOG"
echo "throttle_ms=$OENOBENCH_LLM_THROTTLE_MS  cache=$OENOBENCH_LLM_CACHE" | tee -a "$LOG"
echo "substantive_filter=$OENOBENCH_FACT_SUBSTANTIVE_FILTER  circuit_breaker=$OENOBENCH_CIRCUIT_BREAKER" | tee -a "$LOG"
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
    echo "EXISTING $GOLD_OUT detected — skipping export to preserve any review in progress." | tee -a "$LOG"
    echo "If you want a fresh export, delete the file first." | tee -a "$LOG"
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
FLASH_400S=$(grep -c "is not a valid model ID" "$LOG" || echo 0)

echo "" | tee -a "$LOG"
echo "=== Phase 2g.12 audit pilot v10 — phase 1 complete: $(date -u) ===" | tee -a "$LOG"
echo "" | tee -a "$LOG"
echo "─── Build telemetry ──────────────────────────────────" | tee -a "$LOG"
echo "Wall:                  ${ELAPSED_MIN}m ${ELAPSED_SEC}s  (${ELAPSED}s total)" | tee -a "$LOG"
echo "LLM calls:             $LLM_CALLS" | tee -a "$LOG"
echo "Circuit breakers:      $CIRCUIT_BREAKERS  (lower is better — many fires = lots of dead cells)" | tee -a "$LOG"
echo "Cache hits:            $CACHE_HITS  (cold start; fills as build runs)" | tee -a "$LOG"
echo "Gate relabels:         $GATE_RELABELS  (closed-book solvable → tagged + L1)" | tee -a "$LOG"
echo "Gate quota full:       $GATE_QUOTA_FULL  (>0 means cb-quota cap hit; questions dropped)" | tee -a "$LOG"
echo "C4 rejects:            $C4_REJECTS  (Phase 2g.12 expected ≪ v9's 113)" | tee -a "$LOG"
echo "Parse failures:        $PARSE_FAILS  (Phase 2g.12 expected < v9's 224 due to fence strip)" | tee -a "$LOG"
echo "Flash 400s:            $FLASH_400S  (Phase 2g.12 expected = 0)" | tee -a "$LOG"
echo "" | tee -a "$LOG"
echo "v9 baseline for comparison: 18m / 772 calls / 21 cb / 22 relabel / 113 C4 reject / 224 parse fail / ~50 flash 400" | tee -a "$LOG"
echo "" | tee -a "$LOG"
echo "NEXT STEPS (manual):" | tee -a "$LOG"
echo "  1. Open $GOLD_OUT in your spreadsheet" | tee -a "$LOG"
echo "  2. Review per docs/GOLD_REVIEW_GUIDE_V5.md (rubric definitions stable v5–v10)" | tee -a "$LOG"
echo "  3. Re-import: $PY -m src.qa.orchestrator import-gold --csv-path $GOLD_OUT --reviewer nikita" | tee -a "$LOG"
echo "  4. Run: bash scripts/run_audit_pilot_v10_audit.sh (TODO — copy from v9_audit.sh)" | tee -a "$LOG"
