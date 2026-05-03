#!/usr/bin/env bash
# End-to-end smoke for the review app:
#   1. apply migration 004
#   2. import the release_v1 gold sheet as batch 'release_v1_pilot'
#   3. export reviews (include-incomplete so empty exports are OK on a fresh DB)
set -euo pipefail
cd "$(dirname "$0")/.."
PY=.venv/bin/python
docker exec -i wb-postgres psql -U "${POSTGRES_USER:-winebench}" -d "${POSTGRES_DB:-winebench}" < migrations/004_human_review.sql
$PY -m src.review_app.import_batch --csv data/reports/gold_sheet_release_v1.csv --name release_v1_pilot --replace
$PY -m src.review_app.export_reviews --batch release_v1_pilot --out /tmp/exp.csv --include-incomplete
echo "OK — review app smoke complete"
