#!/usr/bin/env bash
set -euo pipefail

PG_USER="${POSTGRES_USER:-winebench}"
PG_DB="${POSTGRES_DB:-winebench}"

docker exec -i wb-postgres psql -U "$PG_USER" -d "$PG_DB" < migrations/004_human_review.sql
docker exec -i wb-postgres psql -U "$PG_USER" -d "$PG_DB" < migrations/005_rubric_v2.sql
docker exec -i wb-postgres psql -U "$PG_USER" -d "$PG_DB" < migrations/006_drop_test_batches.sql

# Verify the v2 rubric column landed on human_reviews
LABELS_CORRECT_COUNT=$(docker exec -i wb-postgres psql -U "$PG_USER" -d "$PG_DB" -At \
    -c "SELECT count(*) FROM information_schema.columns WHERE table_name='human_reviews' AND column_name='labels_correct';")
if [ "$LABELS_CORRECT_COUNT" != "1" ]; then
    echo "FAIL — human_reviews.labels_correct column missing after migration 005" >&2
    exit 1
fi

# Verify the test-batch cleanup wiped the legacy pytest leftovers
TEST_BATCH_COUNT=$(docker exec -i wb-postgres psql -U "$PG_USER" -d "$PG_DB" -At \
    -c "SELECT count(*) FROM review_batches WHERE name LIKE 'test_batch_%';")
if [ "$TEST_BATCH_COUNT" != "0" ]; then
    echo "WARN — $TEST_BATCH_COUNT test_batch_* rows remain after migration 006" >&2
fi

python -m src.review_app.import_batch --csv data/reports/gold_sheet_release_v1.csv --name release_v1_pilot --replace
python -m src.review_app.export_reviews --batch release_v1_pilot --out /tmp/exp.csv --include-incomplete
echo "OK — review app smoke complete (8-rubric schema, labels_correct present)"
