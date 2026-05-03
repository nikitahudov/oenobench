-- =============================================================================
-- Migration 006 — Drop legacy pytest review batches
--
-- The pre-conftest.py test suite created `test_batch_*` rows that were never
-- cleaned up. CASCADE on review_batch_items + human_reviews makes a single
-- DELETE on review_batches sufficient.
--
-- Data-only and idempotent (safe to re-run; deletes nothing on a clean DB).
-- =============================================================================

DELETE FROM review_batches
WHERE name LIKE 'test_batch_%';
