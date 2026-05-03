-- =============================================================================
-- Migration 004 — Human review tables (Phase 4: Multi-expert human review)
--
-- Adds the schema needed by the standalone Flask review app at
-- src/review_app/. Strictly additive — no existing tables are touched.
--
-- Idempotent: every CREATE is guarded so the script can be applied to a
-- cluster that already has some/all of these objects (e.g. a fresh
-- cluster initialized via config/postgres/init.sql).
-- =============================================================================

-- Enums ---------------------------------------------------------------------

DO $$
BEGIN
    CREATE TYPE rubric_score AS ENUM ('pass', 'warn', 'fail');
EXCEPTION
    WHEN duplicate_object THEN NULL;
END$$;

DO $$
BEGIN
    CREATE TYPE overall_verdict AS ENUM ('approve', 'revise', 'reject');
EXCEPTION
    WHEN duplicate_object THEN NULL;
END$$;


-- Batches -------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS review_batches (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name            TEXT NOT NULL UNIQUE,
    description     TEXT,
    source_csv_path TEXT,
    question_count  INTEGER NOT NULL DEFAULT 0,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by      TEXT
);

CREATE TABLE IF NOT EXISTS review_batch_items (
    batch_id        UUID NOT NULL REFERENCES review_batches(id) ON DELETE CASCADE,
    question_id     UUID NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
    public_qid      TEXT NOT NULL,
    position        INTEGER NOT NULL,
    PRIMARY KEY (batch_id, question_id)
);

CREATE INDEX IF NOT EXISTS idx_rbi_question ON review_batch_items(question_id);


-- Reviewers -----------------------------------------------------------------

CREATE TABLE IF NOT EXISTS human_reviewers (
    id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email             TEXT NOT NULL UNIQUE,
    name              TEXT NOT NULL,
    credentials       TEXT,
    expertise_domains TEXT[] DEFAULT '{}',
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_active_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);


-- Reviews -------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS human_reviews (
    id                       UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    batch_id                 UUID NOT NULL REFERENCES review_batches(id) ON DELETE CASCADE,
    reviewer_id              UUID NOT NULL REFERENCES human_reviewers(id) ON DELETE RESTRICT,
    question_id              UUID NOT NULL REFERENCES questions(id) ON DELETE CASCADE,

    answer_correct           rubric_score,
    distractors_plausible    rubric_score,
    not_ambiguous            rubric_score,
    source_faithful          rubric_score,
    needs_source             rubric_score,
    no_vague_language        rubric_score,
    difficulty_match         rubric_score,
    cognitive_match          rubric_score,
    verbatim_copy            rubric_score,
    wine_category_leak       rubric_score,

    overall_verdict          overall_verdict,
    suggested_answer         TEXT,
    suggested_difficulty     SMALLINT CHECK (suggested_difficulty BETWEEN 1 AND 4),
    notes                    TEXT,

    time_spent_seconds       INTEGER,
    is_complete              BOOLEAN NOT NULL DEFAULT FALSE,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at               TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE (batch_id, reviewer_id, question_id)
);

CREATE INDEX IF NOT EXISTS idx_hr_batch    ON human_reviews(batch_id);
CREATE INDEX IF NOT EXISTS idx_hr_reviewer ON human_reviews(reviewer_id);
CREATE INDEX IF NOT EXISTS idx_hr_question ON human_reviews(question_id);
CREATE INDEX IF NOT EXISTS idx_hr_complete ON human_reviews(is_complete);
