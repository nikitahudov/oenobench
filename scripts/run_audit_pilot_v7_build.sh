#!/usr/bin/env bash
# Phase 2g.8 audit pilot v7 — phase 1 of 2: build corpus + export gold sheet.
#
# After this script completes:
#   1. Open data/reports/gold_sheet_v7.csv in your spreadsheet of choice.
#   2. Fill in the 10 v2.3 rubric columns following docs/GOLD_REVIEW_GUIDE_V5.md
#      (the guide's rubric definitions are stable across v5 and v7 — only
#      the corpus tag differs).
#   3. Re-import the filled CSV:
#        python -m src.qa.orchestrator import-gold \
#            --csv-path data/reports/gold_sheet_v7.csv --reviewer nikita
#   4. Then run scripts/run_audit_pilot_v7_audit.sh to execute the audit
#      teams + build reports — Cohen's κ for the v2.3 rubrics
#      (verbatim_copy, wine_category_leak) will be populated automatically
#      from the imported gold labels.
#
# Why split phase 1 from phase 2: gold labels must be on v7 questions for
# Cohen's κ on this audit run to be valid. Reviewing v5 questions wouldn't
# calibrate against the post-Phase-2g.8 generation quality (per-country
# cap, set_corpus_target, A3 v1.2.0 scoring, Opus gate). See
# docs/PROCESS_LOG.md 2026-04-26 for the workflow rationale.
#
# Designed for nohup launch; survives session close. Logs everything to
# data/logs/audit_pilot_v7_build_<timestamp>.log.
set -euo pipefail

cd /home/winebench/oenobench

TS=$(date -u +%Y%m%dT%H%M%SZ)
LOG=data/logs/audit_pilot_v7_build_${TS}.log
TAG=audit_pilot_v7
SEED=44
PER_STRATEGY=120
PER_COUNTRY_CAP=0.10
GOLD_OUT=data/reports/gold_sheet_v7.csv
PY=.venv/bin/python

mkdir -p data/logs data/reports

echo "=== Phase 2g.8 audit pilot v7 — phase 1 (build) — start: $(date -u) ===" | tee -a "$LOG"
echo "tag=$TAG  seed=$SEED  per_strategy=$PER_STRATEGY  per_country_cap=$PER_COUNTRY_CAP" | tee -a "$LOG"
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
        --tag "$TAG" --out "$GOLD_OUT" --size 120 --seed "$SEED" 2>&1 | tee -a "$LOG"
fi

echo "" | tee -a "$LOG"
echo "=== Phase 2g.8 audit pilot v7 — phase 1 complete: $(date -u) ===" | tee -a "$LOG"
echo "" | tee -a "$LOG"
echo "NEXT STEPS (manual):" | tee -a "$LOG"
echo "  1. Open $GOLD_OUT in your spreadsheet" | tee -a "$LOG"
echo "  2. Review per docs/GOLD_REVIEW_GUIDE_V5.md (rubric definitions stable across v5/v7)" | tee -a "$LOG"
echo "  3. Re-import: $PY -m src.qa.orchestrator import-gold --csv-path $GOLD_OUT --reviewer nikita" | tee -a "$LOG"
echo "  4. Run: bash scripts/run_audit_pilot_v7_audit.sh" | tee -a "$LOG"
