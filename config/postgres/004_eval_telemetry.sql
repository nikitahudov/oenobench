-- =============================================================================
-- OenoBench — Phase 5 eval per-call telemetry
-- Apply with:
--   docker exec -i wb-postgres psql -U winebench -d winebench < config/postgres/004_eval_telemetry.sql
-- Idempotent: safe to re-run.
-- =============================================================================

ALTER TABLE evaluation_answers
  ADD COLUMN IF NOT EXISTS model_name       TEXT,
  ADD COLUMN IF NOT EXISTS provider_used    TEXT,
  ADD COLUMN IF NOT EXISTS generation_id    TEXT,
  ADD COLUMN IF NOT EXISTS input_tokens     INTEGER,
  ADD COLUMN IF NOT EXISTS output_tokens    INTEGER,
  ADD COLUMN IF NOT EXISTS reasoning_tokens INTEGER,
  ADD COLUMN IF NOT EXISTS cost_usd         REAL,
  ADD COLUMN IF NOT EXISTS latency_ms       INTEGER,
  ADD COLUMN IF NOT EXISTS parsed_answer    CHAR(1),
  ADD COLUMN IF NOT EXISTS reasoning_config JSONB;

ALTER TABLE evaluation_runs
  ADD COLUMN IF NOT EXISTS config_json      JSONB,
  ADD COLUMN IF NOT EXISTS reasoning_config JSONB,
  ADD COLUMN IF NOT EXISTS total_cost_usd   REAL;

ALTER TABLE evaluation_answers DROP CONSTRAINT IF EXISTS evaluation_answers_run_id_question_id_key;

CREATE UNIQUE INDEX IF NOT EXISTS uq_eval_answers_per_config
  ON evaluation_answers (run_id, question_id, model_name, COALESCE(reasoning_config::text, ''));

-- Helpful indexes for report queries
CREATE INDEX IF NOT EXISTS idx_eval_answers_run_model ON evaluation_answers (run_id, model_name);
CREATE INDEX IF NOT EXISTS idx_eval_runs_tag ON evaluation_runs ((metadata->>'tag'));
