-- =============================================================================
-- OenoBench — cb_reserve status migration (Phase 2g.15)
-- Apply with:
--   docker exec -i wb-postgres psql -U winebench -d winebench < config/postgres/003_cb_reserve.sql
-- Idempotent: safe to re-run.
-- =============================================================================

-- Extend question_status enum with the cb_reserve value.
-- Questions that would have been dropped (quota full) are instead parked here
-- until a build pass has room to promote them to draft.
DO $$ BEGIN
    ALTER TYPE question_status ADD VALUE IF NOT EXISTS 'cb_reserve';
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
