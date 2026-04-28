#!/usr/bin/env bash
# Phase 2g.11 audit pilot v9 — phase 1 of 2: build corpus + export gold sheet.
#
# What changed vs v8: this is the first audit cycle on the new speedup pipeline
# (Phase 2g.11). v8 ran in ~11.4h with ~16k LLM calls and 111 kept questions.
# v9 stacks 10 active speedup levers from the plan:
#
#   A1+C1 (`f728974`)  drop hardcoded time.sleep(1.5) + add LLM timeout/failover
#   A2     (`0550511`) in-process strategy dispatch (no subprocess cold starts)
#   A3     (`f2f6389`) ThreadPoolExecutor over (generator × domain) cells
#   A4     (`6b4bee0`) ThreadPoolExecutor over top-level strategies
#   B1     (`ca13b2d`) content-hash cache for gate / verifier / paraphrase
#   B2     (`0b190a0`) substantiveness pre-filter at the sampler
#   B3     (`49e2fe3`) per-cell circuit breaker + budget reallocation
#   B4     (`5f3247d`) tier-aware gate model (Haiku L1 / Sonnet L2 / Opus L3)
#   C2     (`aca5932`) Gemini Flash variant for paraphrase + template verifier
#
#   B5 (verifier skip on gate_passed + high confidence) is shipped but DORMANT
#   under the current pipeline ordering — defer to a Phase 2g.12 architecture
#   refactor.
#
# Expected wall (vs v8's 11.4h): ~1-3h.
#
# After this script completes:
#   1. Open data/reports/gold_sheet_v9.csv in your spreadsheet of choice.
#   2. Fill in the 10 v2.3 rubric columns following docs/GOLD_REVIEW_GUIDE_V5.md.
#   3. Re-import the filled CSV:
#        python -m src.qa.orchestrator import-gold \
#            --csv-path data/reports/gold_sheet_v9.csv --reviewer nikita
#   4. Then run scripts/run_audit_pilot_v9_audit.sh to execute the audit
#      teams + build reports.
#
# Designed for nohup launch; survives session close. Logs everything to
# data/logs/audit_pilot_v9_build_<timestamp>.log.
set -euo pipefail

cd /home/winebench/oenobench

# ─── Speedup env vars ─────────────────────────────────────────────────────────

# A1: zero out the LLM throttle (was 1.5s on every call in v8 — accounted for
# ~6.7h of v8 walltime). Tenacity already retries on rate-limit / 5xx with
# exponential backoff, so the floor is unnecessary.
export OENOBENCH_LLM_THROTTLE_MS=0

# B1: enable the content-hash cache for gate / verifier / paraphrase decisions.
# Cache key includes model_id + version_tag, so a model swap (e.g. Sonnet→Opus)
# bypasses cached entries. v9 starts cold; entries accumulate as the build runs.
export OENOBENCH_LLM_CACHE=1

# B2: enable the substantiveness pre-filter at the sampler. Drops geographically-
# trivial / iconic-only / under-anchored facts before they reach the LLM, so we
# don't burn calls on facts the LLM will reject anyway.
export OENOBENCH_FACT_SUBSTANTIVE_FILTER=1

# B3: enable the per-cell circuit breaker. After 10 attempts at <5% kept-rate,
# the cell is abandoned and the unused budget reallocates to the next cell
# (capped at 2× original to prevent soaking).
export OENOBENCH_CIRCUIT_BREAKER=1

# A3: cell-level concurrency inside each strategy. 8 workers saturates
# OpenRouter on our previous traffic without 429s.
export OENOBENCH_MAX_WORKERS=8

# A4: top-level strategy concurrency. 3 workers runs three of the five
# strategies in parallel; raise to 5 once we confirm OpenRouter survives 8×3=24
# concurrent inflight requests.
export OENOBENCH_STRATEGY_WORKERS=3

# B4: tier-aware gate model. With B4 the defaults are
# Haiku L1 / Sonnet L2 / Opus L3 — DO NOT export OENOBENCH_GATE_MODEL here
# (a global override would collapse all tiers to a single model and undo B4).
# Per-tier overrides are still available if needed:
#     OENOBENCH_GATE_MODEL_L1=anthropic/claude-haiku-4.5-20251001
#     OENOBENCH_GATE_MODEL_L2=anthropic/claude-sonnet-4.6
#     OENOBENCH_GATE_MODEL_L3=anthropic/claude-opus-4.7
unset OENOBENCH_GATE_MODEL || true

# C2: Gemini Flash variant for paraphrase + template verifier. Defaults are
# baked into the modules; env-var overrides exist for fallback to Pro.
# Leave unset to use the new Flash defaults.
unset OENOBENCH_PARAPHRASE_MODEL || true
unset OENOBENCH_VERIFIER_MODEL || true

# ─── Build configuration ──────────────────────────────────────────────────────

TS=$(date -u +%Y%m%dT%H%M%SZ)
LOG=data/logs/audit_pilot_v9_build_${TS}.log
TAG=audit_pilot_v9
SEED=46
# v9 sized at total=100 (per_strategy=20) to halve audit time + cost vs v8's
# 200 target. Sample is small (per-strategy ≥14, per-cell ~0.7 LLM-strategy
# attempts before circuit breaker), so per-cell statistics are noisy — but
# corpus-level Go/No-Go gates (B2 ≤ 15%, A1 ≤ 2%, etc.) remain meaningful.
# The circuit breaker may undershoot the budget on low-yield strategies —
# that's by design.
PER_STRATEGY=20
PER_COUNTRY_CAP=0.30
GOLD_OUT=data/reports/gold_sheet_v9.csv
GOLD_SIZE=20
PY=.venv/bin/python

mkdir -p data/logs data/reports

echo "=== Phase 2g.11 audit pilot v9 — phase 1 (build) — start: $(date -u) ===" | tee -a "$LOG"
echo "tag=$TAG  seed=$SEED  per_strategy=$PER_STRATEGY  per_country_cap=$PER_COUNTRY_CAP" | tee -a "$LOG"
echo "max_workers=$OENOBENCH_MAX_WORKERS  strategy_workers=$OENOBENCH_STRATEGY_WORKERS" | tee -a "$LOG"
echo "throttle_ms=$OENOBENCH_LLM_THROTTLE_MS  cache=$OENOBENCH_LLM_CACHE" | tee -a "$LOG"
echo "substantive_filter=$OENOBENCH_FACT_SUBSTANTIVE_FILTER  circuit_breaker=$OENOBENCH_CIRCUIT_BREAKER" | tee -a "$LOG"
echo "log=$LOG" | tee -a "$LOG"
echo "" | tee -a "$LOG"

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

echo "" | tee -a "$LOG"
echo "=== Phase 2g.11 audit pilot v9 — phase 1 complete: $(date -u) ===" | tee -a "$LOG"
echo "" | tee -a "$LOG"
echo "NEXT STEPS (manual):" | tee -a "$LOG"
echo "  1. Open $GOLD_OUT in your spreadsheet" | tee -a "$LOG"
echo "  2. Review per docs/GOLD_REVIEW_GUIDE_V5.md (rubric definitions stable across v5/v7/v8/v9)" | tee -a "$LOG"
echo "  3. Re-import: $PY -m src.qa.orchestrator import-gold --csv-path $GOLD_OUT --reviewer nikita" | tee -a "$LOG"
echo "  4. Run: bash scripts/run_audit_pilot_v9_audit.sh" | tee -a "$LOG"
echo "" | tee -a "$LOG"
echo "Sanity checks (compare against v8 baseline of 11.4h / 16k LLM calls / 111 q):" | tee -a "$LOG"
echo "  * grep 'CIRCUIT BREAKER' \$LOG | wc -l       # >0 if any strategy abandoned a cell" | tee -a "$LOG"
echo "  * grep 'LLM cache HIT' \$LOG | wc -l         # cache hit count (B1)" | tee -a "$LOG"
echo "  * grep 'Filtered .* substantiveness' \$LOG   # B2 filter activity" | tee -a "$LOG"
echo "  * grep 'GATE QUOTA FULL\\|GATE RELABEL' \$LOG # closed-book quota events" | tee -a "$LOG"
echo "  * grep -c 'LLM call' \$LOG                  # total LLM calls (target: significantly < 16k)" | tee -a "$LOG"
