#!/usr/bin/env bash
# Phase 2g.18 audit pilot v16 — phase 1 of 2: build corpus + export gold sheet.
#
# This is the cost-down v16 cost-validation pilot. It bakes in the v16
# env-var profile (Phase 2g.18 levers L1, L5, L6) on top of the carry-over
# Phase 2g.11/12 speedup levers, so a smoke pilot can validate the projected
# cost reduction before the full 10k run.
#
# Plan: /home/winebench/.claude/plans/virtual-snacking-anchor.md
#
# Active levers in this build (Phase 2g.18):
#
#   L1  Closed-book quota 25% → 40%  (env: OENOBENCH_CB_QUOTA=0.40)
#       Team A is also lifting the default in src/generators/_closed_book_gate.py;
#       the explicit env export here protects pre-merge pilot runs.
#   L2  B1/B2 "claude" judge resolves to Sonnet 4.6  (Team B code change in
#       src/qa/_judges.py — fires at audit time, not build).
#   L3  B2 panel slim 5 → 4 judges  (Team B code change — audit time).
#   L4  Generator mix v2.4: claude 1800, chatgpt 2400, gemini 3200, qwen 1000,
#       llama 600  (Team A code change in src/generators/orchestrator.py).
#   L5  Verifier-skip plumbing  (env: OENOBENCH_VERIFIER_SKIP=1; fires after
#       Team C reorders gate/verifier in _schemas.py + strategy callers so
#       should_skip_verifier() actually triggers on gate_passed + confidence).
#   L6  Tier-aware gate L3 → Sonnet 4.6  (env trial:
#       OENOBENCH_GATE_MODEL_L3=anthropic/claude-sonnet-4.6;
#       default flip deferred to Phase 2g.19 if v16 smoke validates).
#   L7  D1 d1-sample 20 → 10  (audit-script flag — see v16_audit.sh).
#   L8  C4 dropped from default audit  (audit-script flag — see v16_audit.sh).
#   L9  FTQ substantiveness filter strict mode  (Team A code change in
#       src/generators/fact_to_question.py — fires at sampler time).
#
# Cost baseline (verified):
#   - v9 build:  ~$3 / 100 attempted (per_strategy=20, target=100)
#   - v15_ubiq audit: $0.61 / 35 Qs / 380 calls = ~$1.74 / 100
#   - Combined: ~$9 / 100 final → $900 projected on 10k.
# Cost target (v16, full 10k):
#   - ≤ $4.50 / 100 final → ≤ $450 on 10k (50% reduction).
# Cost target (this smoke pilot, ~50 final Qs):
#   - Build: ≤ $1.75; Audit: ≤ $0.50; per-Q ≤ $0.045.
#
# After this script completes:
#   1. Open data/reports/gold_sheet_v16.csv in your spreadsheet of choice.
#   2. Fill in the 10 v2.3 rubric columns following docs/GOLD_REVIEW_GUIDE_V5.md.
#   3. Re-import the filled CSV:
#        python -m src.qa.orchestrator import-gold \
#            --csv-path data/reports/gold_sheet_v16.csv --reviewer nikita
#   4. Then run scripts/run_audit_pilot_v16_audit.sh to execute the audit
#      teams + build reports.
#
# Designed for nohup launch; survives session close. Logs everything to
# data/logs/audit_pilot_v16_build_<timestamp>.log.
set -euo pipefail

cd /home/winebench/oenobench

# ─── Carry-over speedup env vars (Phase 2g.11/12 — unchanged) ────────────────

# A1: zero out the LLM throttle. Tenacity already retries on rate-limit / 5xx
# with exponential backoff, so the floor is unnecessary.
export OENOBENCH_LLM_THROTTLE_MS=0

# B1: enable the content-hash cache for gate / verifier / paraphrase decisions.
export OENOBENCH_LLM_CACHE=1

# B2: enable the substantiveness pre-filter at the sampler.
export OENOBENCH_FACT_SUBSTANTIVE_FILTER=1

# B3: enable the per-cell circuit breaker.
export OENOBENCH_CIRCUIT_BREAKER=1

# A3: cell-level concurrency inside each strategy.
export OENOBENCH_MAX_WORKERS=8

# A4: top-level strategy concurrency.
export OENOBENCH_STRATEGY_WORKERS=3

# ─── Phase 2g.18 v16 cost-down env vars ──────────────────────────────────────

# L1: closed-book quota 25% → 40%. Team A is lifting the default in
# src/generators/_closed_book_gate.py:139; setting it explicitly here protects
# against any pre-merge pilot run on a worktree that hasn't picked up Team A's
# change yet.
export OENOBENCH_CB_QUOTA=0.40

# L5: verifier-skip lever. The Phase 2g.11 helper exists at _verify.py:61-83
# but was DORMANT under v9-v15 because the verifier ran inside parse_llm_response
# BEFORE the closed-book gate. Team C plumbing reorders the call chain and
# forwards (gate_passed, generator_confidence) into parse_llm_response so
# should_skip_verifier() actually fires when this env var is set.
export OENOBENCH_VERIFIER_SKIP=1

# L6: tier-aware gate L3 → Sonnet 4.6 (Phase 1 — env-var trial).
# Per-tier env var path already exists at _closed_book_gate.py:96-98.
# Phase 2 (default code change) is deferred to Phase 2g.19 if the v16 smoke
# confirms the gate-pass shift stays within 5pp on the 50-Q sample.
export OENOBENCH_GATE_MODEL_L3=anthropic/claude-sonnet-4.6

# B4 protection: tier-aware gate model has Haiku L1 / Sonnet L2 / Sonnet L3
# (with the L6 override above). DO NOT export OENOBENCH_GATE_MODEL globally —
# it would collapse all tiers to a single model and undo B4. The L1/L2 tier
# overrides are also unset so they fall through to the Phase 2g.11 defaults.
unset OENOBENCH_GATE_MODEL OENOBENCH_GATE_MODEL_L1 OENOBENCH_GATE_MODEL_L2 OENOBENCH_PARAPHRASE_MODEL OENOBENCH_VERIFIER_MODEL || true

# ─── Build configuration ──────────────────────────────────────────────────────

TS=$(date -u +%Y%m%dT%H%M%SZ)
LOG=data/logs/audit_pilot_v16_build_${TS}.log
TAG=audit_pilot_v16
SEED=59
# v16 sized at per_strategy=15 (~75 attempts, ~50–60 kept post-filter).
# Smaller than v9's 20 because we're cost-validating the env profile, not
# rebuilding the audit corpus. Per the plan §"Validation pilot (v16 smoke)",
# pass criteria = per-Q cost ≤ $0.045, verifier-skip events > 50,
# gate-pass + cb-relabel rate ≥ 60%, B1/B2 fail rate within ±3pp of v15_ubiq.
PER_STRATEGY=15
PER_COUNTRY_CAP=0.30
GOLD_OUT=data/reports/gold_sheet_v16.csv
GOLD_SIZE=20
PY=.venv/bin/python

mkdir -p data/logs data/reports

echo "=== Phase 2g.18 audit pilot v16 — phase 1 (build) — start: $(date -u) ===" | tee -a "$LOG"
echo "tag=$TAG  seed=$SEED  per_strategy=$PER_STRATEGY  per_country_cap=$PER_COUNTRY_CAP" | tee -a "$LOG"
echo "max_workers=$OENOBENCH_MAX_WORKERS  strategy_workers=$OENOBENCH_STRATEGY_WORKERS" | tee -a "$LOG"
echo "throttle_ms=$OENOBENCH_LLM_THROTTLE_MS  cache=$OENOBENCH_LLM_CACHE" | tee -a "$LOG"
echo "substantive_filter=$OENOBENCH_FACT_SUBSTANTIVE_FILTER  circuit_breaker=$OENOBENCH_CIRCUIT_BREAKER" | tee -a "$LOG"
echo "cb_quota=$OENOBENCH_CB_QUOTA  verifier_skip=$OENOBENCH_VERIFIER_SKIP  gate_l3=$OENOBENCH_GATE_MODEL_L3" | tee -a "$LOG"
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
echo "=== Phase 2g.18 audit pilot v16 — phase 1 complete: $(date -u) ===" | tee -a "$LOG"
echo "" | tee -a "$LOG"
echo "NEXT STEPS (manual):" | tee -a "$LOG"
echo "  1. Open $GOLD_OUT in your spreadsheet" | tee -a "$LOG"
echo "  2. Review per docs/GOLD_REVIEW_GUIDE_V5.md (rubric definitions stable across v5/v7/v8/v9/v15/v16)" | tee -a "$LOG"
echo "  3. Re-import: $PY -m src.qa.orchestrator import-gold --csv-path $GOLD_OUT --reviewer nikita" | tee -a "$LOG"
echo "  4. Run: bash scripts/run_audit_pilot_v16_audit.sh" | tee -a "$LOG"
echo "" | tee -a "$LOG"
echo "Sanity checks (compare against v9 baseline of 18 min / 772 LLM calls / 46 kept and v15_ubiq cost \$0.61 / 35 Qs):" | tee -a "$LOG"
echo "  * grep 'CIRCUIT BREAKER' \$LOG | wc -l           # >0 if any strategy abandoned a cell" | tee -a "$LOG"
echo "  * grep 'LLM cache HIT' \$LOG | wc -l             # cache hit count (B1)" | tee -a "$LOG"
echo "  * grep 'Filtered .* substantiveness' \$LOG       # B2 filter activity" | tee -a "$LOG"
echo "  * grep -c 'GATE QUOTA FULL\\|GATE RELABEL' \$LOG  # L1 quota events (target: capture more relabels at 0.40 cap)" | tee -a "$LOG"
echo "  * grep -c 'verifier-skip\\|VERIFIER SKIP' \$LOG   # L5 firing (target > 50 to confirm lever bite)" | tee -a "$LOG"
echo "  * grep -c 'LLM call' \$LOG                      # total LLM calls (target: ≤ ~600 on per_strategy=15)" | tee -a "$LOG"
