#!/usr/bin/env bash
# Usage: ./scripts/promote_from_reserve.sh <tag> <count> [<strategy>]
# Promotes N cb_reserve questions to active draft status.
set -euo pipefail
cd /home/winebench/oenobench
TAG="${1:?tag required}"
COUNT="${2:?count required}"
STRATEGY_ARG=""
if [[ -n "${3:-}" ]]; then STRATEGY_ARG="--strategy $3"; fi
.venv/bin/python -m src.qa.orchestrator promote-from-reserve --tag "$TAG" --count "$COUNT" $STRATEGY_ARG
