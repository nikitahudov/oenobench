#!/usr/bin/env bash
# Phase 2j — release_v1 scenario_synthesis re-run (post type-aware redesign).
#
# The original release_v1 build (2026-05-02 → 2026-05-03) shipped 91
# scenario_synthesis questions (vs 975 target). Root cause: every cell
# defaulted to scenario_type="winemaking", forcing a winemaker-persona
# framing on facts from grape/region/producer/business domains. 76% of
# scenario output ended up winemaking-themed regardless of source-fact
# domain, and most non-winemaking-domain clusters were rejected by the
# LLM as "facts too unrelated".
#
# This re-run leverages the type-aware redesign:
#   * DOMAIN_TO_SCENARIO_TYPES maps each domain to natural framings
#     (wine_regions → business/service/tasting; producers → service/business; …)
#   * _dispatch_llm_strategy explodes (gen × domain) cells into
#     (gen × domain × scenario_type) sub-cells (~50 vs 30 per pass)
#   * SCENARIO_TEMPLATE in _prompts.py now has type-aware persona blocks
#     and a type-conditional "iconic without depth" skip rule
#
# --resume preserves the existing 91 release_v1 scenario rows. The
# multi-pass loop will add new ones in the same tag, capping naturally
# when the fact pool exhausts.
#
# Target: 200-300 scenario_synthesis keeps (per user direction). The
# scaled strategy target (975) stays in code; per-strategy multi-pass
# will stop at 2 zero-progress passes before reaching it.
#
# Cost projection: ~$20-40 (5,000-10,000 LLM calls).
# Wall projection: 30-90 min.

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
LOG=data/logs/release_v1_scenario_${TS}.log
TAG=release_v1
SEED=200            # fresh seed so cluster sampling differs from the original run
TARGET=6500
PY=.venv/bin/python

mkdir -p data/logs

# Pre-snapshot of existing scenario_synthesis rows
EXISTING_SCENARIO=$(docker exec -i wb-postgres psql -U winebench -d winebench -t -A -c \
    "SELECT count(*) FROM questions q
     JOIN generation_metadata gm ON gm.question_id = q.id
     WHERE '${TAG}' = ANY(q.tags) AND gm.generation_method = 'scenario_synthesis';" \
    2>/dev/null || echo 0)
EXISTING_SCENARIO=${EXISTING_SCENARIO//[^0-9]/}
if [[ -z "$EXISTING_SCENARIO" ]]; then EXISTING_SCENARIO=0; fi

echo "=== Phase 2j scenario re-run — start: $(date -u) ===" | tee -a "$LOG"
echo "tag=$TAG  seed=$SEED  target=$TARGET  strategy=scenario_synthesis only" | tee -a "$LOG"
echo "existing_scenario_in_tag=$EXISTING_SCENARIO" | tee -a "$LOG"
echo "cb_quota=$OENOBENCH_CB_QUOTA  workers=$OENOBENCH_MAX_WORKERS  passes=$OENOBENCH_MAX_GENERATE_PASSES" | tee -a "$LOG"
echo "log=$LOG" | tee -a "$LOG"
echo "" | tee -a "$LOG"

START_EPOCH=$(date +%s)

# ─── [1/2] scenario-only generate ─────────────────────────────────────────────

echo "--- [1/2] generate-all --strategies scenario_synthesis: $(date -u) ---" | tee -a "$LOG"
$PY -m src.generators.orchestrator generate-all \
    --target "$TARGET" \
    --tag "$TAG" \
    --seed "$SEED" \
    --strategies scenario_synthesis \
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

NEW_SCENARIO=$(docker exec -i wb-postgres psql -U winebench -d winebench -t -A -c \
    "SELECT count(*) FROM questions q
     JOIN generation_metadata gm ON gm.question_id = q.id
     WHERE '${TAG}' = ANY(q.tags) AND gm.generation_method = 'scenario_synthesis';" \
    2>/dev/null || echo 0)
NEW_SCENARIO=${NEW_SCENARIO//[^0-9]/}

DELTA=$((NEW_SCENARIO - EXISTING_SCENARIO))
LLM_CALLS=$(grep -c "LLM call |" "$LOG" || echo 0)

# Per-domain × scenario_type breakdown of NEW questions only.
DOMAIN_TYPE_BREAKDOWN=$(docker exec -i wb-postgres psql -U winebench -d winebench -t -A -F'|' -c "
SELECT q.domain::text, count(*) FILTER (WHERE q.created_at > NOW() - interval '6 hours')
FROM questions q JOIN generation_metadata gm ON gm.question_id = q.id
WHERE '${TAG}' = ANY(q.tags) AND gm.generation_method = 'scenario_synthesis'
GROUP BY q.domain ORDER BY q.domain;" 2>/dev/null || echo "<db query failed>")

echo "" | tee -a "$LOG"
echo "=== scenario re-run complete: $(date -u) ===" | tee -a "$LOG"
echo "Wall:                 ${ELAPSED_MIN}m ${ELAPSED_SEC}s" | tee -a "$LOG"
echo "Build exit code:      $GEN_EXIT" | tee -a "$LOG"
echo "LLM calls (logged):   $LLM_CALLS" | tee -a "$LOG"
echo "" | tee -a "$LOG"
echo "Scenario rows:        ${EXISTING_SCENARIO} → ${NEW_SCENARIO}  (Δ +${DELTA})" | tee -a "$LOG"
echo "" | tee -a "$LOG"
echo "Per-domain (recent only):" | tee -a "$LOG"
echo "$DOMAIN_TYPE_BREAKDOWN" | tee -a "$LOG"
echo "" | tee -a "$LOG"
echo "Log: $LOG" | tee -a "$LOG"
