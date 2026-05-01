#!/usr/bin/env bash
# Phase 2g.14 audit pilot v12 — phase 1 of 2: build corpus + export gold sheet.
#
# What's new vs v11 (commit 02252d9):
#   * Lever 4: Closed-book quota fraction tightened 0.25 → 0.20.
#   * Lever 3': Verifier-"claude" pool decoupled from generator-"claude" pool.
#     Verifier dispatches to Sonnet 4.6; generator stays on Opus 4.7.
#   * Lever 2: Prompt boilerplate factored + iconic-entities list trimmed
#     (7 examples → 5).
#
# Phase 2g.13 multi-pass + cross-pass-dedup levers stay active.
# Phase 2g.12 fixes (Flash slug, Haiku slug, C4 threshold, cell allocation,
# JSON fence strip, truth-tell log) stay active.
# Phase 2g.11 speedup levers stay active.
#
# Build target: per_strategy=24 → 120 questions.
#
# v11 baseline: $6.37, 25m 5s, 86/120 kept (72%), 654 LLM calls.
# v12 expected: ~$5.55, ~25m, 86–105/120, ~600 LLM calls. Generator-claude
# unchanged (Opus 4.7) so quality should match v11; cost reduction comes
# entirely from auxiliary roles (verifier, paraphrase boilerplate, cb quota).

set -euo pipefail
cd /home/winebench/oenobench

# ─── Speedup env vars (same as v11) ───────────────────────────────────────────

export OENOBENCH_LLM_THROTTLE_MS=0
export OENOBENCH_LLM_CACHE=1
export OENOBENCH_FACT_SUBSTANTIVE_FILTER=1
export OENOBENCH_CIRCUIT_BREAKER=1
export OENOBENCH_MAX_WORKERS=8
export OENOBENCH_STRATEGY_WORKERS=3
unset OENOBENCH_GATE_MODEL || true
unset OENOBENCH_PARAPHRASE_MODEL || true
unset OENOBENCH_VERIFIER_MODEL || true

# ─── Phase 2g.13 multi-pass loop ──────────────────────────────────────────────
export OENOBENCH_MAX_BUILD_PASSES=3

# ─── Build configuration ──────────────────────────────────────────────────────

TS=$(date -u +%Y%m%dT%H%M%SZ)
LOG=data/logs/audit_pilot_v12_build_${TS}.log
TAG=audit_pilot_v12
SEED=49
PER_STRATEGY=24
PER_COUNTRY_CAP=0.30
GOLD_OUT=data/reports/gold_sheet_v12.csv
GOLD_SIZE=24
PY=.venv/bin/python

mkdir -p data/logs data/reports

echo "=== Phase 2g.14 audit pilot v12 — phase 1 (build) — start: $(date -u) ===" | tee -a "$LOG"
echo "tag=$TAG  seed=$SEED  per_strategy=$PER_STRATEGY  per_country_cap=$PER_COUNTRY_CAP" | tee -a "$LOG"
echo "max_build_passes=$OENOBENCH_MAX_BUILD_PASSES  workers=$OENOBENCH_MAX_WORKERS" | tee -a "$LOG"
echo "strategy_workers=$OENOBENCH_STRATEGY_WORKERS  cache=$OENOBENCH_LLM_CACHE" | tee -a "$LOG"
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

echo "" | tee -a "$LOG"
echo "=== Phase 2g.14 audit pilot v12 — phase 1 complete: $(date -u) ===" | tee -a "$LOG"
echo "" | tee -a "$LOG"
echo "─── Build telemetry ──────────────────────────────────" | tee -a "$LOG"
echo "Wall:                  ${ELAPSED_MIN}m ${ELAPSED_SEC}s  (${ELAPSED}s total)" | tee -a "$LOG"
echo "LLM calls:             $LLM_CALLS" | tee -a "$LOG"
echo "Sonnet verifier calls: $SONNET_VERIFIER  (Phase 2g.14 Lever 3' — verifier-claude → Sonnet)" | tee -a "$LOG"
echo "Circuit breakers:      $CIRCUIT_BREAKERS" | tee -a "$LOG"
echo "Cache hits:            $CACHE_HITS" | tee -a "$LOG"
echo "Gate relabels:         $GATE_RELABELS" | tee -a "$LOG"
echo "Gate quota full:       $GATE_QUOTA_FULL  (Phase 2g.14 Lever 4 — cb cap 25% → 20%)" | tee -a "$LOG"
echo "C4 rejects:            $C4_REJECTS" | tee -a "$LOG"
echo "Parse failures:        $PARSE_FAILS" | tee -a "$LOG"
echo "Flash 400s:            $FLASH_400S  (expected = 0)" | tee -a "$LOG"
echo "Haiku 400s:            $HAIKU_400S  (expected = 0)" | tee -a "$LOG"
echo "Pass markers:          $PASS_LINES" | tee -a "$LOG"
echo "" | tee -a "$LOG"
echo "v11 baseline: 25m / 654 calls / 13 cb / 30 relabel / 7 quota-full / 17 C4 / 112 parse / 0 Flash / 0 Haiku / \$6.37" | tee -a "$LOG"
