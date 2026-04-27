#!/usr/bin/env bash
# Phase 2g.9 audit pilot v8 — phase 1 of 2: build corpus + export gold sheet.
#
# What changed vs v7:
#   * --per-country-cap 0.10 → 0.30. The 0.10 cap on a 4-question per-call
#     budget rounds down to 1-2 facts per country, which gutted comparative,
#     scenario_synthesis, distractor_mining, and template down to 16-42
#     questions instead of 120 each (v7 corpus was 242 instead of 600). 0.30
#     keeps the soft country balance without starving multi-fact bundles.
#   * Closed-book quota cap now actually fires inside strategy subprocesses
#     (Phase 2g.9 OENOBENCH_CORPUS_TARGET env-var fallback in
#     src/generators/_question_db.py). v7 ran with the default 2500 cap and
#     accumulated 172 closed-book relabels on a 242-Q corpus; v8 (200-Q
#     target × 0.25) should emit `GATE QUOTA FULL` events at relabel #50
#     and stay under the cap.
#   * per_strategy reduced 120 → 40 (corpus 200 instead of 600) to cut wall
#     time + audit cost roughly in half — see PER_STRATEGY comment below.
#
# After this script completes:
#   1. Open data/reports/gold_sheet_v8.csv in your spreadsheet of choice.
#   2. Fill in the 10 v2.3 rubric columns following docs/GOLD_REVIEW_GUIDE_V5.md
#      (the guide's rubric definitions are stable — only the corpus tag differs).
#   3. Re-import the filled CSV:
#        python -m src.qa.orchestrator import-gold \
#            --csv-path data/reports/gold_sheet_v8.csv --reviewer nikita
#   4. Then run scripts/run_audit_pilot_v8_audit.sh to execute the audit
#      teams + build reports.
#
# Designed for nohup launch; survives session close. Logs everything to
# data/logs/audit_pilot_v8_build_<timestamp>.log.
set -euo pipefail

cd /home/winebench/oenobench

# Phase 2g.9: revert the gate to Sonnet 4.6 for v8. The v6→v7 evidence
# (Sonnet → Opus) added only +14 relabels (158 → 172) and now that the
# closed-book quota cap actually fires (Phase 2g.9 env-var fallback), both
# models saturate at the cap anyway. v8 isolates the effect of the cap fix
# from the gate-model upgrade. If v8 passes B2 on Sonnet, the 10k run
# stays on Sonnet (~$60 cheaper than Opus). If v8 still fails, retry on
# Opus by unsetting this export — the gate module re-resolves at import
# time, so the change is a one-line revert.
export OENOBENCH_GATE_MODEL=anthropic/claude-sonnet-4.6

TS=$(date -u +%Y%m%dT%H%M%SZ)
LOG=data/logs/audit_pilot_v8_build_${TS}.log
TAG=audit_pilot_v8
SEED=45
# Phase 2g.9: per_strategy reduced 120 → 40 (corpus 600 → 200) to cut audit
# wall time + cost roughly in half. v6 (264 q) and v7 (242 q) both gave
# actionable signal at this corpus size; per-strategy n=40 is enough for
# corpus-level Go/No-Go gates (B2 ≤ 15%, A1 ≤ 2%, etc.) but per-cell stats
# (5 generators × 6 domains = 30 cells) are 1-2 q/cell — too sparse for
# per-cell analysis. Audit phase: ~$5-7 instead of $15-20; ~1h instead of 3-4h.
PER_STRATEGY=40
PER_COUNTRY_CAP=0.30
GOLD_OUT=data/reports/gold_sheet_v8.csv
GOLD_SIZE=40
PY=.venv/bin/python

mkdir -p data/logs data/reports

echo "=== Phase 2g.9 audit pilot v8 — phase 1 (build) — start: $(date -u) ===" | tee -a "$LOG"
echo "tag=$TAG  seed=$SEED  per_strategy=$PER_STRATEGY  per_country_cap=$PER_COUNTRY_CAP" | tee -a "$LOG"
echo "gate_model=$OENOBENCH_GATE_MODEL" | tee -a "$LOG"
echo "log=$LOG" | tee -a "$LOG"
echo "" | tee -a "$LOG"

echo "--- [1/2] build-corpus: $(date -u) ---" | tee -a "$LOG"
$PY -m src.qa.orchestrator build-corpus \
    --tag "$TAG" --per-strategy "$PER_STRATEGY" --seed "$SEED" \
    --per-country-cap "$PER_COUNTRY_CAP" 2>&1 | tee -a "$LOG"

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
echo "=== Phase 2g.9 audit pilot v8 — phase 1 complete: $(date -u) ===" | tee -a "$LOG"
echo "" | tee -a "$LOG"
echo "NEXT STEPS (manual):" | tee -a "$LOG"
echo "  1. Open $GOLD_OUT in your spreadsheet" | tee -a "$LOG"
echo "  2. Review per docs/GOLD_REVIEW_GUIDE_V5.md (rubric definitions stable across v5/v7/v8)" | tee -a "$LOG"
echo "  3. Re-import: $PY -m src.qa.orchestrator import-gold --csv-path $GOLD_OUT --reviewer nikita" | tee -a "$LOG"
echo "  4. Run: bash scripts/run_audit_pilot_v8_audit.sh" | tee -a "$LOG"
