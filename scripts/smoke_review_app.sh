#!/usr/bin/env bash
set -euo pipefail
docker exec -i wb-postgres psql -U "${POSTGRES_USER:-winebench}" -d "${POSTGRES_DB:-winebench}" < migrations/004_human_review.sql
python -m src.review_app.import_batch --csv data/reports/gold_sheet_release_v1.csv --name release_v1_pilot --replace
python -m src.review_app.export_reviews --batch release_v1_pilot --out /tmp/exp.csv --include-incomplete
echo "OK — review app smoke complete"
