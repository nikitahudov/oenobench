#!/usr/bin/env bash
# Phase 5 eval against the sample schema (1062 Qs × 16 configs).
# Estimated wall: ~10 min. Estimated cost: ~$40.
set -euo pipefail

cd "$(dirname "$0")/.."

TAG="${TAG:-eval_sample_$(date +%Y%m%d_%H%M%S)}"
echo "Running eval with tag: $TAG"

OENOBENCH_LLM_THROTTLE_MS=0 \
OENOBENCH_EVAL_CONFIG_WORKERS=16 \
python -m src.evaluation.run_eval \
    --tag "$TAG" \
    --corpus sample \
    "$@"

echo "Eval complete. Tag: $TAG"
echo "Render report with: python -m src.evaluation.report --tag $TAG"
