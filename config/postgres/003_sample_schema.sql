-- Sample-database schema (Phase 2g.18 follow-up, 2026-05-02)
--
-- Curated quality-vetted preview set of OenoBench questions assembled from
-- audit pilots v5-v16 that PASS the per-question quality gates.
--
-- Filters (applied in INSERT statements below):
--   - status = 'draft'
--   - has at least one audit_findings row (so audit-status is known)
--   - NO 'fail' finding on A1_LexicalHygiene, A3_FactEcho, B1_TriJudgeAnswer,
--     or C2_CategoryLeak
--   - not from pre-gate pilots v1-v4 (those predate the closed-book gate
--     and have known structural defects current audit agents may miss)
--   - cb-tagged INCLUDED (kept with `closed_book_solvable` tag preserved)
--
-- This schema mirrors the relevant subset of the public schema. It does NOT
-- mirror: questions table partitions, evaluation_runs / evaluation_answers,
-- audit_gold_labels, validation_records, or the *_history audit triggers.
-- Custom enums (domain_type, question_type, audit_severity, etc.) live in
-- the public schema and are reused here via search_path.
--
-- Idempotent: drops and recreates the entire `sample` schema. Re-running
-- this script gives a fresh snapshot from current public-schema data.

DROP SCHEMA IF EXISTS sample CASCADE;
CREATE SCHEMA sample;

-- ─── Mirror tables (structure only, no FKs into public) ──────────────────
CREATE TABLE sample.questions             (LIKE public.questions             INCLUDING DEFAULTS);
CREATE TABLE sample.facts                 (LIKE public.facts                 INCLUDING DEFAULTS);
CREATE TABLE sample.sources               (LIKE public.sources               INCLUDING DEFAULTS);
CREATE TABLE sample.question_facts        (LIKE public.question_facts        INCLUDING DEFAULTS);
CREATE TABLE sample.question_sources      (LIKE public.question_sources      INCLUDING DEFAULTS);
CREATE TABLE sample.generation_metadata   (LIKE public.generation_metadata   INCLUDING DEFAULTS);
CREATE TABLE sample.audit_runs            (LIKE public.audit_runs            INCLUDING DEFAULTS);
CREATE TABLE sample.audit_findings        (LIKE public.audit_findings        INCLUDING DEFAULTS);

-- Manifest: provenance + filter-criteria metadata. One row per assembly run.
CREATE TABLE sample.manifest (
    id              SERIAL PRIMARY KEY,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    description     TEXT NOT NULL,
    filters_json    JSONB NOT NULL,
    n_questions     INTEGER NOT NULL,
    n_facts         INTEGER NOT NULL,
    n_sources       INTEGER NOT NULL,
    n_findings      INTEGER NOT NULL,
    source_pilots   TEXT[] NOT NULL
);

-- ─── Compute the passing question set ────────────────────────────────────
-- Materialised once into a temp table so subsequent INSERTs stay consistent
-- even if production data changes mid-run.
CREATE TEMP TABLE _sample_passing AS
WITH any_fail AS (
    SELECT DISTINCT question_id
    FROM public.audit_findings
    WHERE severity = 'fail'
      AND agent_id IN ('A1_LexicalHygiene', 'A3_FactEcho',
                       'B1_TriJudgeAnswer', 'C2_CategoryLeak')
),
has_audit AS (
    SELECT DISTINCT question_id FROM public.audit_findings
),
old_pilots AS (
    SELECT id FROM public.questions
    WHERE EXISTS (
        SELECT 1 FROM unnest(tags) t
        WHERE t IN ('audit_pilot_v1', 'audit_pilot_v2',
                    'audit_pilot_v3', 'audit_pilot_v4')
    )
)
SELECT q.id AS question_id
FROM public.questions q
WHERE q.status = 'draft'
  AND q.id IN (SELECT question_id FROM has_audit)
  AND q.id NOT IN (SELECT question_id FROM any_fail)
  AND q.id NOT IN (SELECT id FROM old_pilots);

-- ─── Copy passing questions + their dependency closure ───────────────────
INSERT INTO sample.questions
SELECT q.* FROM public.questions q
JOIN _sample_passing p ON p.question_id = q.id;

INSERT INTO sample.question_facts
SELECT qf.* FROM public.question_facts qf
JOIN _sample_passing p ON p.question_id = qf.question_id;

INSERT INTO sample.question_sources
SELECT qs.* FROM public.question_sources qs
JOIN _sample_passing p ON p.question_id = qs.question_id;

INSERT INTO sample.facts
SELECT DISTINCT f.* FROM public.facts f
WHERE f.id IN (SELECT fact_id FROM sample.question_facts);

INSERT INTO sample.sources
SELECT DISTINCT s.* FROM public.sources s
WHERE s.id IN (SELECT source_id FROM sample.facts WHERE source_id IS NOT NULL)
   OR s.id IN (SELECT source_id FROM sample.question_sources);

INSERT INTO sample.generation_metadata
SELECT gm.* FROM public.generation_metadata gm
JOIN _sample_passing p ON p.question_id = gm.question_id;

INSERT INTO sample.audit_findings
SELECT af.* FROM public.audit_findings af
JOIN _sample_passing p ON p.question_id = af.question_id;

INSERT INTO sample.audit_runs
SELECT DISTINCT ar.* FROM public.audit_runs ar
WHERE ar.id IN (SELECT DISTINCT run_id FROM sample.audit_findings);

-- ─── Primary keys + foreign keys ────────────────────────────────────────
-- Add minimal PKs so JOINs in queries remain efficient. FKs point inside
-- the sample schema only.

ALTER TABLE sample.questions             ADD PRIMARY KEY (id);
ALTER TABLE sample.facts                 ADD PRIMARY KEY (id);
ALTER TABLE sample.sources               ADD PRIMARY KEY (id);
ALTER TABLE sample.question_facts        ADD PRIMARY KEY (question_id, fact_id);
ALTER TABLE sample.question_sources      ADD PRIMARY KEY (question_id, source_id);
ALTER TABLE sample.generation_metadata   ADD PRIMARY KEY (id);
ALTER TABLE sample.audit_runs            ADD PRIMARY KEY (id);
ALTER TABLE sample.audit_findings        ADD PRIMARY KEY (id);

ALTER TABLE sample.facts
    ADD CONSTRAINT facts_source_id_fkey
    FOREIGN KEY (source_id) REFERENCES sample.sources(id);
ALTER TABLE sample.question_facts
    ADD CONSTRAINT question_facts_question_id_fkey
    FOREIGN KEY (question_id) REFERENCES sample.questions(id) ON DELETE CASCADE,
    ADD CONSTRAINT question_facts_fact_id_fkey
    FOREIGN KEY (fact_id) REFERENCES sample.facts(id) ON DELETE CASCADE;
ALTER TABLE sample.question_sources
    ADD CONSTRAINT question_sources_question_id_fkey
    FOREIGN KEY (question_id) REFERENCES sample.questions(id) ON DELETE CASCADE,
    ADD CONSTRAINT question_sources_source_id_fkey
    FOREIGN KEY (source_id) REFERENCES sample.sources(id) ON DELETE CASCADE;
ALTER TABLE sample.generation_metadata
    ADD CONSTRAINT generation_metadata_question_id_fkey
    FOREIGN KEY (question_id) REFERENCES sample.questions(id) ON DELETE CASCADE;
ALTER TABLE sample.audit_findings
    ADD CONSTRAINT audit_findings_run_id_fkey
    FOREIGN KEY (run_id) REFERENCES sample.audit_runs(id),
    ADD CONSTRAINT audit_findings_question_id_fkey
    FOREIGN KEY (question_id) REFERENCES sample.questions(id);

-- ─── Useful indexes ─────────────────────────────────────────────────────
CREATE INDEX ON sample.questions             (status);
CREATE INDEX ON sample.questions             (domain);
CREATE INDEX ON sample.questions             (difficulty);
CREATE INDEX ON sample.questions             USING gin (tags);
CREATE INDEX ON sample.facts                 (domain);
CREATE INDEX ON sample.audit_findings        (question_id);
CREATE INDEX ON sample.audit_findings        (agent_id, severity);
CREATE INDEX ON sample.generation_metadata   (question_id);
CREATE INDEX ON sample.generation_metadata   (generation_method);

-- ─── Manifest row ────────────────────────────────────────────────────────
INSERT INTO sample.manifest (
    description, filters_json, n_questions, n_facts, n_sources,
    n_findings, source_pilots
)
SELECT
    'OenoBench v1 sample — quality-vetted preview from audit pilots v5-v16',
    jsonb_build_object(
        'status', 'draft',
        'must_have_audit_findings', true,
        'no_fail_on', ARRAY['A1_LexicalHygiene','A3_FactEcho',
                            'B1_TriJudgeAnswer','C2_CategoryLeak'],
        'exclude_pilots', ARRAY['audit_pilot_v1','audit_pilot_v2',
                                'audit_pilot_v3','audit_pilot_v4'],
        'cb_tagged', 'included',
        'phase', '2g.18-followup'
    ),
    (SELECT COUNT(*) FROM sample.questions),
    (SELECT COUNT(*) FROM sample.facts),
    (SELECT COUNT(*) FROM sample.sources),
    (SELECT COUNT(*) FROM sample.audit_findings),
    ARRAY(
        SELECT DISTINCT t
        FROM sample.questions q, unnest(q.tags) t
        WHERE t LIKE 'audit_pilot_%'
        ORDER BY t
    );

-- ─── Final summary echo ──────────────────────────────────────────────────
\echo '=== sample schema assembly complete ==='
SELECT n_questions, n_facts, n_sources, n_findings, source_pilots
FROM sample.manifest ORDER BY id DESC LIMIT 1;
