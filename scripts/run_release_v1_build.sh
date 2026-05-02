#!/usr/bin/env bash
# Phase 2j — release_v1 build: full 6,500-question generation run.
#
# Drives `src.generators.orchestrator generate-all` with the v16b cost-down
# env profile + cb_quota=0.50 + tag=release_v1 + target=6500 (weighted mix
# matching the project plan: FTQ 2925, comparative 975, scenario 975,
# distractor 975, template 650).
#
# After the build finishes, exports a 100-row stratified gold sheet for
# the user to spot-check before deciding whether to launch the audit phase.
#
# DESIGN: idempotent — the script can be re-run with the same tag after a
# crash and `--resume` will pick up the build window via MIN(created_at) of
# `release_v1`-tagged questions, so the closed-book quota stays scoped to
# this run.
#
# Cost projection: ~$220 build (6,500 × $0.034 v16b validated rate).
# Wall time: 6–10h with --max-workers 8 --strategy-workers 3.

set -uo pipefail   # NB: no -e — we want the final summary to print even if
                   # individual strategy cells fail; the orchestrator already
                   # logs and continues.
cd /home/winebench/oenobench

# ─── Speedup env vars (Phase 2g.11/2g.18 v16b profile) ────────────────────────

export OENOBENCH_LLM_THROTTLE_MS=0          # A1 — no throttle on OpenRouter
export OENOBENCH_LLM_CACHE=1                # B1 — Postgres-backed LLM cache
export OENOBENCH_FACT_SUBSTANTIVE_FILTER=1  # B2 — sampler substantiveness
export OENOBENCH_CIRCUIT_BREAKER=1          # B3 — per-cell rolling kept-rate
export OENOBENCH_MAX_WORKERS=8              # A3 — cell-level concurrency
export OENOBENCH_STRATEGY_WORKERS=3         # A4 — strategy-level concurrency
export OENOBENCH_VERIFIER_SKIP=1            # B5 — skip verifier when gate passes
export OENOBENCH_MAX_BUILD_PASSES=3

# ─── Phase 2j release_v1 levers ────────────────────────────────────────────────

# CB quota set to 0.50 (vs v16b's 0.40). At 6,500 corpus this caps the
# corpus-wide closed-book ceiling at 3,250; the per-strategy floor (set by
# the orchestrator from the smallest scaled target = template 650) gives
# each strategy a 325-slot ceiling. Total potential cb-tagged ≤ 1,625
# across 5 strategies — well under the corpus cap.
export OENOBENCH_CB_QUOTA=0.50

# Default tier-aware gate routing (L1 Haiku, L2 Haiku, L3 Sonnet) is fine.
unset OENOBENCH_GATE_MODEL || true
unset OENOBENCH_PARAPHRASE_MODEL || true
unset OENOBENCH_VERIFIER_MODEL || true

# ─── Run configuration ────────────────────────────────────────────────────────

TS=$(date -u +%Y%m%dT%H%M%SZ)
LOG=data/logs/release_v1_build_${TS}.log
TAG=release_v1
SEED=100
TARGET=6500
PER_COUNTRY_CAP=0.30
GOLD_OUT=data/reports/gold_sheet_release_v1.csv
GOLD_SIZE=100
PY=.venv/bin/python

mkdir -p data/logs data/reports

# Decide whether to use --resume. If any release_v1-tagged questions
# already exist, we resume; otherwise it's a fresh run.
RESUME_FLAG=""
EXISTING=$(docker exec -i wb-postgres psql -U winebench -d winebench -t -A -c \
    "SELECT count(*) FROM questions WHERE '${TAG}' = ANY(tags);" 2>/dev/null \
    || echo 0)
EXISTING=${EXISTING//[^0-9]/}
if [[ -z "$EXISTING" ]]; then EXISTING=0; fi
if (( EXISTING > 0 )); then
    RESUME_FLAG="--resume"
    echo "Detected $EXISTING existing $TAG questions — resuming."
fi

echo "=== Phase 2j release_v1 build — start: $(date -u) ===" | tee -a "$LOG"
echo "tag=$TAG  seed=$SEED  target=$TARGET  per_country_cap=$PER_COUNTRY_CAP" | tee -a "$LOG"
echo "cb_quota=$OENOBENCH_CB_QUOTA  workers=$OENOBENCH_MAX_WORKERS  strategy_workers=$OENOBENCH_STRATEGY_WORKERS" | tee -a "$LOG"
echo "resume=${RESUME_FLAG:-<fresh>}  existing_in_tag=$EXISTING" | tee -a "$LOG"
echo "log=$LOG  gold_out=$GOLD_OUT" | tee -a "$LOG"
echo "" | tee -a "$LOG"

START_EPOCH=$(date +%s)

# ─── [1/3] full generation run ────────────────────────────────────────────────

# Note: the orchestrator's `generate-all` does not accept --per-country-cap
# directly (that flag lives on the qa.orchestrator path). The sampler's
# country cap defaults are honoured per generators._fact_sampler.
echo "--- [1/3] generate-all: $(date -u) ---" | tee -a "$LOG"
$PY -m src.generators.orchestrator generate-all \
    --target "$TARGET" \
    --tag "$TAG" \
    --seed "$SEED" \
    --max-workers "$OENOBENCH_MAX_WORKERS" \
    --strategy-workers "$OENOBENCH_STRATEGY_WORKERS" \
    $RESUME_FLAG 2>&1 | tee -a "$LOG"
GEN_EXIT=${PIPESTATUS[0]}

BUILD_END_EPOCH=$(date +%s)
BUILD_ELAPSED=$((BUILD_END_EPOCH - START_EPOCH))
BUILD_MIN=$((BUILD_ELAPSED / 60))
BUILD_SEC=$((BUILD_ELAPSED % 60))

# ─── [2/3] export 100-row stratified gold sheet ──────────────────────────────

echo "" | tee -a "$LOG"
echo "--- [2/3] export-gold ($GOLD_SIZE rows): $(date -u) ---" | tee -a "$LOG"
$PY -m src.qa.orchestrator export-gold \
    --tag "$TAG" --out "$GOLD_OUT" --size "$GOLD_SIZE" --seed "$SEED" 2>&1 | tee -a "$LOG"
GOLD_EXIT=${PIPESTATUS[0]}

# ─── [3/3] final summary (DB-backed, source of truth) ────────────────────────

END_EPOCH=$(date +%s)
ELAPSED=$((END_EPOCH - START_EPOCH))
ELAPSED_MIN=$((ELAPSED / 60))
ELAPSED_SEC=$((ELAPSED % 60))

echo "" | tee -a "$LOG"
echo "--- [3/3] final summary: $(date -u) ---" | tee -a "$LOG"

# Per-strategy counts (active vs cb_reserve)
STRATEGY_TABLE=$(docker exec -i wb-postgres psql -U winebench -d winebench -t -A -F'|' -c "
SELECT
  gm.generation_method,
  count(*) FILTER (WHERE q.status::text = 'draft') AS draft,
  count(*) FILTER (WHERE q.status::text = 'cb_reserve') AS cb_reserve,
  count(*) FILTER (WHERE 'closed_book_solvable' = ANY(q.tags) AND q.status::text = 'draft') AS cb_tagged_draft,
  count(*) AS total
FROM questions q
JOIN generation_metadata gm ON gm.question_id = q.id
WHERE '${TAG}' = ANY(q.tags)
GROUP BY gm.generation_method
ORDER BY gm.generation_method;
" 2>/dev/null || echo "<db query failed>")

DOMAIN_TABLE=$(docker exec -i wb-postgres psql -U winebench -d winebench -t -A -F'|' -c "
SELECT q.domain::text, count(*) FROM questions q
WHERE '${TAG}' = ANY(q.tags) AND q.status::text = 'draft'
GROUP BY q.domain ORDER BY q.domain;
" 2>/dev/null || echo "<db query failed>")

TOTAL_DRAFT=$(docker exec -i wb-postgres psql -U winebench -d winebench -t -A -c \
    "SELECT count(*) FROM questions WHERE '${TAG}' = ANY(tags) AND status::text = 'draft';" \
    2>/dev/null || echo 0)
TOTAL_RESERVE=$(docker exec -i wb-postgres psql -U winebench -d winebench -t -A -c \
    "SELECT count(*) FROM questions WHERE '${TAG}' = ANY(tags) AND status::text = 'cb_reserve';" \
    2>/dev/null || echo 0)
LLM_CALLS=$(grep -c "LLM call" "$LOG" || echo 0)
GATE_QUOTA_FULL=$(grep -c "GATE QUOTA FULL" "$LOG" || echo 0)
CB_RESERVED=$(grep -c "GATE QUOTA FULL → RESERVED" "$LOG" || echo 0)

echo "" | tee -a "$LOG"
echo "=== release_v1 build complete: $(date -u) ===" | tee -a "$LOG"
echo "" | tee -a "$LOG"
echo "─── Wall + cost telemetry ────────────────────────────────────" | tee -a "$LOG"
echo "Total wall:           ${ELAPSED_MIN}m ${ELAPSED_SEC}s  (${ELAPSED}s)" | tee -a "$LOG"
echo "Build wall:           ${BUILD_MIN}m ${BUILD_SEC}s" | tee -a "$LOG"
echo "Build exit code:      $GEN_EXIT  (gold export exit: $GOLD_EXIT)" | tee -a "$LOG"
echo "LLM calls (logged):   $LLM_CALLS" | tee -a "$LOG"
echo "Gate quota fires:     $GATE_QUOTA_FULL" | tee -a "$LOG"
echo "cb_reserve banked:    $CB_RESERVED" | tee -a "$LOG"
echo "" | tee -a "$LOG"
echo "─── DB state for tag=$TAG ────────────────────────────────────" | tee -a "$LOG"
echo "Total draft:          $TOTAL_DRAFT  (target: $TARGET)" | tee -a "$LOG"
echo "Total cb_reserve:     $TOTAL_RESERVE" | tee -a "$LOG"
echo "" | tee -a "$LOG"
echo "Per-strategy (method | draft | cb_reserve | cb_tagged_draft | total):" | tee -a "$LOG"
echo "$STRATEGY_TABLE" | tee -a "$LOG"
echo "" | tee -a "$LOG"
echo "Per-domain (draft only):" | tee -a "$LOG"
echo "$DOMAIN_TABLE" | tee -a "$LOG"
echo "" | tee -a "$LOG"
echo "Gold sheet:           $GOLD_OUT" | tee -a "$LOG"
echo "Log:                  $LOG" | tee -a "$LOG"
echo "" | tee -a "$LOG"
echo "Next steps:" | tee -a "$LOG"
echo "  1. Eyeball the gold sheet at $GOLD_OUT" | tee -a "$LOG"
echo "  2. Decide whether to launch audit phase 2 (separate command)" | tee -a "$LOG"
echo "  3. To resume on partial completion: re-run this script (it'll" | tee -a "$LOG"
echo "     auto-detect existing $TAG rows and add --resume)." | tee -a "$LOG"
