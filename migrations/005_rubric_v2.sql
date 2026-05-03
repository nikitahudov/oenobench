-- =============================================================================
-- Migration 005 — Rubric v2 (10 -> 8 rubrics)
--
-- The Phase 4 review-app v2 collapses two pairs of rubrics:
--   * difficulty_match + cognitive_match  -> labels_correct
--   * wine_category_leak                  -> folded into distractors_plausible
--
-- Schema-additive: this migration ONLY adds the new `labels_correct` column.
-- The legacy three columns (difficulty_match, cognitive_match,
-- wine_category_leak) stay in place and are simply not written by the v2
-- review form. They remain queryable for κ analysis on legacy review rows.
--
-- Idempotent: ADD COLUMN IF NOT EXISTS so the migration can be re-applied.
-- =============================================================================

ALTER TABLE human_reviews
    ADD COLUMN IF NOT EXISTS labels_correct rubric_score;
