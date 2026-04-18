-- =============================================================================
-- OenoBench — Quality Audit Schema (Phase 2c)
-- Apply with:
--   docker exec -i wb-postgres psql -U winebench -d winebench < config/postgres/002_audit_schema.sql
-- Idempotent: safe to re-run.
-- =============================================================================

-- Severity enum used by every audit agent.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'audit_severity') THEN
        CREATE TYPE audit_severity AS ENUM ('pass', 'warn', 'fail', 'error');
    END IF;
END
$$;

-- One row per audit campaign. Captures config + cost ledger.
CREATE TABLE IF NOT EXISTS audit_runs (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at    TIMESTAMPTZ,
    corpus_tag      TEXT NOT NULL,
    corpus_size     INTEGER,
    config_hash     TEXT NOT NULL,
    random_seed     INTEGER NOT NULL,
    total_cost_usd  REAL DEFAULT 0,
    metadata        JSONB DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_audit_runs_tag ON audit_runs(corpus_tag);

-- One row per (run, question, agent, version). Population-level findings
-- have question_id IS NULL.
CREATE TABLE IF NOT EXISTS audit_findings (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    run_id          UUID NOT NULL REFERENCES audit_runs(id) ON DELETE CASCADE,
    question_id     UUID REFERENCES questions(id) ON DELETE CASCADE,
    agent_id        TEXT NOT NULL,
    agent_version   TEXT NOT NULL,
    severity        audit_severity NOT NULL,
    score           REAL,
    payload         JSONB NOT NULL DEFAULT '{}'::jsonb,
    llm_calls       INTEGER NOT NULL DEFAULT 0,
    cost_usd        REAL NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Idempotency key: same agent on same question in same run = single row.
-- Allows orchestrator to skip re-doing work on retry.
CREATE UNIQUE INDEX IF NOT EXISTS uq_audit_findings_agent
    ON audit_findings(run_id, COALESCE(question_id::text, ''), agent_id, agent_version);

CREATE INDEX IF NOT EXISTS idx_audit_findings_q     ON audit_findings(question_id);
CREATE INDEX IF NOT EXISTS idx_audit_findings_agent ON audit_findings(agent_id, agent_version);
CREATE INDEX IF NOT EXISTS idx_audit_findings_sev   ON audit_findings(severity);
CREATE INDEX IF NOT EXISTS idx_audit_findings_run   ON audit_findings(run_id);

-- Human gold-standard labels for judge calibration.
CREATE TABLE IF NOT EXISTS audit_gold_labels (
    question_id     UUID PRIMARY KEY REFERENCES questions(id) ON DELETE CASCADE,
    labels          JSONB NOT NULL,
    reviewer        TEXT NOT NULL,
    reviewed_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    notes           TEXT
);

-- Convenience view: all findings rolled up per question.
CREATE OR REPLACE VIEW v_question_audit_summary AS
SELECT  q.id,
        q.question_id            AS public_qid,
        q.domain,
        q.difficulty,
        q.cognitive_dim,
        q.question_type,
        gm.generator,
        gm.generation_method,
        count(f.id) FILTER (WHERE f.severity = 'fail') AS fail_count,
        count(f.id) FILTER (WHERE f.severity = 'warn') AS warn_count,
        count(f.id) FILTER (WHERE f.severity = 'pass') AS pass_count,
        count(f.id) FILTER (WHERE f.severity = 'error') AS error_count,
        sum(f.cost_usd) AS total_cost_usd,
        sum(f.llm_calls) AS total_llm_calls,
        jsonb_object_agg(
            f.agent_id,
            jsonb_build_object(
                'severity', f.severity,
                'score',    f.score,
                'payload',  f.payload
            )
        ) FILTER (WHERE f.id IS NOT NULL) AS findings_by_agent
FROM    questions q
LEFT JOIN generation_metadata gm ON gm.question_id = q.id
LEFT JOIN audit_findings f ON f.question_id = q.id
GROUP BY q.id, q.question_id, q.domain, q.difficulty, q.cognitive_dim,
         q.question_type, gm.generator, gm.generation_method;

-- Per-strategy roll-up (population-level reporting helper).
CREATE OR REPLACE VIEW v_strategy_audit_rollup AS
SELECT  gm.generation_method AS strategy,
        gm.generator,
        count(DISTINCT q.id) AS question_count,
        count(f.id) FILTER (WHERE f.severity = 'fail') AS total_fails,
        count(f.id) FILTER (WHERE f.severity = 'warn') AS total_warns,
        avg(f.cost_usd) AS avg_cost_usd
FROM    questions q
JOIN    generation_metadata gm ON gm.question_id = q.id
LEFT JOIN audit_findings f ON f.question_id = q.id
GROUP BY gm.generation_method, gm.generator;
