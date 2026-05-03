#!/usr/bin/env bash
# Phase 2j — release_v1 comparative re-run (post type-aware redesign).
#
# The original release_v1 build shipped 114/975 comparative questions. Root
# causes: (a) sample_fact_pairs returned 0 candidates for most domains
# ("No more fact pairs available for domain=producers/winemaking/wine_business"
# spammed the build log), (b) the orchestrator never overrode
# comparison_type so all cells defaulted to "auto" → same_vs_different
# regardless of fact-pool fit, (c) the prompt's SKIP CONDITIONS rejected
# any cross-country pair as "no shared context".
#
# This re-run uses the type-aware redesign:
#   * sample_fact_pairs now has expanded entity-type whitelist
#     (region, grape, appellation, producer + classification, style,
#     doc, aoc, docg, ava, doca, igp, aop), lower length floor (40→30),
#     a third JOIN arm for cross-country same-subdomain pairs, and a
#     loose-fallback pass when the strict candidate set underflows.
#   * DOMAIN_TO_COMPARISON_TYPES maps each domain to natural framings
#     (wine_regions → same_vs_different/most_least/which_one, etc.)
#   * _dispatch_llm_strategy explodes (gen × domain) cells into
#     (gen × domain × comparison_type) sub-cells (~65 vs 30 per pass)
#   * COMPARATIVE_TEMPLATE skip rules loosened: cross-country pairs
#     allowed when the comparison axis is fact-anchored on both sides;
#     iconic-skip made type-conditional (relaxed for which_one)
#
# --resume preserves the existing 114 release_v1 comparative rows.
# Multi-pass loop will add new ones; capping naturally when the loose-
# fallback also exhausts.
#
# Target per user direction: 200-300 comparative questions total
# (current 114 + 86-186 new). Strategy target stays 975 in code; the
# multi-pass + zero-streak guard will stop early.
#
# Cost projection: ~$15-30 (5,000-10,000 LLM calls).
# Wall projection: 30-60 min.

set -uo pipefail
cd /home/winebench/oenobench

# ─── Speedup env vars (Phase 2g.11/2g.18 v16b profile) ────────────────────────

export OENOBENCH_LLM_THROTTLE_MS=0
export OENOBENCH_LLM_CACHE=1
export OENOBENCH_FACT_SUBSTANTIVE_FILTER=1
export OENOBENCH_CIRCUIT_BREAKER=1
export OENOBENCH_MAX_WORKERS=8
export OENOBENCH_STRATEGY_WORKERS=1   # only one strategy in flight
export OENOBENCH_VERIFIER_SKIP=1
export OENOBENCH_MAX_BUILD_PASSES=3
export OENOBENCH_MAX_GENERATE_PASSES=8

# ─── Phase 2j release_v1 levers ───────────────────────────────────────────────

export OENOBENCH_CB_QUOTA=0.50

unset OENOBENCH_GATE_MODEL || true
unset OENOBENCH_PARAPHRASE_MODEL || true
unset OENOBENCH_VERIFIER_MODEL || true

# ─── Run configuration ────────────────────────────────────────────────────────

TS=$(date -u +%Y%m%dT%H%M%SZ)
LOG=data/logs/release_v1_comparative_${TS}.log
TAG=release_v1
SEED=300            # fresh seed so pair sampling differs from prior runs
TARGET=6500
PY=.venv/bin/python

mkdir -p data/logs

# Pre-snapshot of existing comparative rows
EXISTING_COMP=$(docker exec -i wb-postgres psql -U winebench -d winebench -t -A -c \
    "SELECT count(*) FROM questions q
     JOIN generation_metadata gm ON gm.question_id = q.id
     WHERE '${TAG}' = ANY(q.tags) AND gm.generation_method = 'comparative';" \
    2>/dev/null || echo 0)
EXISTING_COMP=${EXISTING_COMP//[^0-9]/}
if [[ -z "$EXISTING_COMP" ]]; then EXISTING_COMP=0; fi

echo "=== Phase 2j comparative re-run — start: $(date -u) ===" | tee -a "$LOG"
echo "tag=$TAG  seed=$SEED  target=$TARGET  strategy=comparative only" | tee -a "$LOG"
echo "existing_comparative_in_tag=$EXISTING_COMP" | tee -a "$LOG"
echo "cb_quota=$OENOBENCH_CB_QUOTA  workers=$OENOBENCH_MAX_WORKERS  passes=$OENOBENCH_MAX_GENERATE_PASSES" | tee -a "$LOG"
echo "log=$LOG" | tee -a "$LOG"
echo "" | tee -a "$LOG"

START_EPOCH=$(date +%s)

# ─── [1/2] comparative-only generate ──────────────────────────────────────────

echo "--- [1/2] generate-all --strategies comparative: $(date -u) ---" | tee -a "$LOG"
$PY -m src.generators.orchestrator generate-all \
    --target "$TARGET" \
    --tag "$TAG" \
    --seed "$SEED" \
    --strategies comparative \
    --max-workers "$OENOBENCH_MAX_WORKERS" \
    --strategy-workers "$OENOBENCH_STRATEGY_WORKERS" \
    --resume 2>&1 | tee -a "$LOG"
GEN_EXIT=${PIPESTATUS[0]}

END_EPOCH=$(date +%s)
ELAPSED=$((END_EPOCH - START_EPOCH))
ELAPSED_MIN=$((ELAPSED / 60))
ELAPSED_SEC=$((ELAPSED % 60))

# ─── [2/2] final summary ──────────────────────────────────────────────────────

echo "" | tee -a "$LOG"
echo "--- [2/2] final summary: $(date -u) ---" | tee -a "$LOG"

NEW_COMP=$(docker exec -i wb-postgres psql -U winebench -d winebench -t -A -c \
    "SELECT count(*) FROM questions q
     JOIN generation_metadata gm ON gm.question_id = q.id
     WHERE '${TAG}' = ANY(q.tags) AND gm.generation_method = 'comparative';" \
    2>/dev/null || echo 0)
NEW_COMP=${NEW_COMP//[^0-9]/}

DELTA=$((NEW_COMP - EXISTING_COMP))
LLM_CALLS=$(grep -c "LLM call |" "$LOG" || echo 0)

DOMAIN_BREAKDOWN=$(docker exec -i wb-postgres psql -U winebench -d winebench -t -A -F'|' -c "
SELECT q.domain::text, count(*)
FROM questions q JOIN generation_metadata gm ON gm.question_id = q.id
WHERE '${TAG}' = ANY(q.tags) AND gm.generation_method = 'comparative'
GROUP BY q.domain ORDER BY q.domain;" 2>/dev/null || echo "<db query failed>")

echo "" | tee -a "$LOG"
echo "=== comparative re-run complete: $(date -u) ===" | tee -a "$LOG"
echo "Wall:                 ${ELAPSED_MIN}m ${ELAPSED_SEC}s" | tee -a "$LOG"
echo "Build exit code:      $GEN_EXIT" | tee -a "$LOG"
echo "LLM calls (logged):   $LLM_CALLS" | tee -a "$LOG"
echo "" | tee -a "$LOG"
echo "Comparative rows:     ${EXISTING_COMP} → ${NEW_COMP}  (Δ +${DELTA})" | tee -a "$LOG"
echo "" | tee -a "$LOG"
echo "Per-domain (all comparative in tag):" | tee -a "$LOG"
echo "$DOMAIN_BREAKDOWN" | tee -a "$LOG"
echo "" | tee -a "$LOG"
echo "Log: $LOG" | tee -a "$LOG"
