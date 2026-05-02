-- =============================================================================
-- OenoBench — Phase 5 telemetry fix: store OR's authoritative cost
-- Apply with:
--   docker exec -i wb-postgres psql -U winebench -d winebench < config/postgres/005_or_cost_telemetry.sql
-- Idempotent: safe to re-run (IF NOT EXISTS throughout).
-- =============================================================================

-- 005_or_cost_telemetry.sql — Phase 5 telemetry fix: store OR's authoritative cost
-- Idempotent.

ALTER TABLE evaluation_answers
  ADD COLUMN IF NOT EXISTS or_cost_usd  REAL,    -- OR's `usage.cost` field (authoritative bill)
  ADD COLUMN IF NOT EXISTS or_provider  TEXT;    -- OR's `provider` field (back-end OR routed to)

ALTER TABLE evaluation_runs
  ADD COLUMN IF NOT EXISTS total_or_cost_usd REAL;  -- sum of or_cost_usd across the run

CREATE INDEX IF NOT EXISTS idx_eval_answers_or_provider
  ON evaluation_answers (or_provider) WHERE or_provider IS NOT NULL;
