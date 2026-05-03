-- =============================================================================
-- WineBench — PostgreSQL Schema Initialization
-- Runs automatically on first `docker compose up` via entrypoint.
-- =============================================================================

-- Extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "vector";          -- pgvector for embeddings
CREATE EXTENSION IF NOT EXISTS "pg_trgm";         -- trigram similarity

-- =============================================================================
-- ENUMS
-- =============================================================================

CREATE TYPE domain_type AS ENUM (
    'viticulture', 'winemaking', 'wine_business',
    'wine_regions', 'grape_varieties', 'producers'
);

CREATE TYPE difficulty_level AS ENUM ('1', '2', '3', '4');

CREATE TYPE cognitive_dimension AS ENUM (
    'recall', 'comprehension', 'application',
    'analysis', 'synthesis', 'evaluation'
);

CREATE TYPE question_type AS ENUM (
    'multiple_choice', 'multiple_select', 'true_false',
    'matching', 'short_answer', 'scenario_based'
);

CREATE TYPE question_status AS ENUM (
    'draft', 'ai_validated', 'cb_reserve', 'flagged', 'human_reviewed',
    'approved', 'rejected'
);

CREATE TYPE source_tier AS ENUM ('tier_1_official', 'tier_2_authoritative', 'tier_3_reliable');

CREATE TYPE generator_model AS ENUM (
    'claude', 'gpt4', 'gemini', 'llama', 'chatgpt', 'qwen',
    'template_only', 'human_authored'
);

-- =============================================================================
-- SOURCES — where facts originate
-- =============================================================================

CREATE TABLE sources (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name            TEXT NOT NULL,
    url             TEXT,
    source_type     TEXT NOT NULL,           -- 'website', 'book', 'paper', 'regulation', etc.
    tier            source_tier NOT NULL DEFAULT 'tier_3_reliable',
    language        TEXT DEFAULT 'en',
    accessed_date   DATE,
    content_date    DATE,                    -- when the source information was current/valid
    notes           TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_sources_tier ON sources(tier);
CREATE INDEX idx_sources_type ON sources(source_type);

-- =============================================================================
-- FACTS — verified atomic pieces of wine knowledge
-- =============================================================================

CREATE TABLE facts (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    fact_text       TEXT NOT NULL,
    domain          domain_type NOT NULL,
    subdomain       TEXT,                    -- e.g. 'france_burgundy', 'fermentation'
    entities        JSONB DEFAULT '[]',      -- extracted entities [{type, name, id}]
    source_id       UUID REFERENCES sources(id),
    confidence      REAL DEFAULT 1.0 CHECK (confidence BETWEEN 0 AND 1),
    verified        BOOLEAN DEFAULT false,
    embedding       vector(1536),            -- for similarity / dedup
    tags            TEXT[] DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_facts_domain ON facts(domain);
CREATE INDEX idx_facts_subdomain ON facts(subdomain);
CREATE INDEX idx_facts_verified ON facts(verified);
CREATE INDEX idx_facts_source ON facts(source_id);
CREATE INDEX idx_facts_entities ON facts USING GIN (entities);
CREATE INDEX idx_facts_tags ON facts USING GIN (tags);

-- =============================================================================
-- QUESTIONS — the benchmark dataset
-- =============================================================================

CREATE TABLE questions (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    question_id     TEXT NOT NULL UNIQUE,     -- human-readable: WB-REG-FR-1247-L3
    version         TEXT NOT NULL DEFAULT '1.0',
    domain          domain_type NOT NULL,
    subdomain       TEXT,
    question_type   question_type NOT NULL,
    difficulty      difficulty_level NOT NULL,
    cognitive_dim   cognitive_dimension NOT NULL DEFAULT 'recall',
    question_text   TEXT NOT NULL,
    options         JSONB,                    -- [{id, text}] for MC/MS
    correct_answer  TEXT NOT NULL,            -- letter or text
    correct_answer_text TEXT,
    explanation     TEXT,
    status          question_status NOT NULL DEFAULT 'draft',
    embedding       vector(1536),             -- for deduplication
    tags            TEXT[] DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_questions_qid ON questions(question_id);
CREATE INDEX idx_questions_domain ON questions(domain);
CREATE INDEX idx_questions_difficulty ON questions(difficulty);
CREATE INDEX idx_questions_status ON questions(status);
CREATE INDEX idx_questions_type ON questions(question_type);
CREATE INDEX idx_questions_cognitive ON questions(cognitive_dim);
CREATE INDEX idx_questions_tags ON questions USING GIN (tags);

-- =============================================================================
-- QUESTION ↔ FACT LINKAGE — traceability
-- =============================================================================

CREATE TABLE question_facts (
    question_id     UUID REFERENCES questions(id) ON DELETE CASCADE,
    fact_id         UUID REFERENCES facts(id) ON DELETE CASCADE,
    PRIMARY KEY (question_id, fact_id)
);

-- =============================================================================
-- GENERATION METADATA — provenance tracking per question
-- =============================================================================

CREATE TABLE generation_metadata (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    question_id     UUID NOT NULL UNIQUE REFERENCES questions(id) ON DELETE CASCADE,
    generator       generator_model NOT NULL,
    generator_version TEXT,                   -- e.g. 'gpt-4o-2024-05-13'
    generation_method TEXT NOT NULL,          -- 'fact_to_question', 'template', etc.
    template_id     TEXT,                     -- if template-based
    llm_creativity  TEXT DEFAULT 'medium',    -- 'none', 'low', 'medium', 'high'
    prompt_hash     TEXT,                     -- hash of generation prompt for reproducibility
    raw_response    JSONB,                    -- full LLM response (optional, for audit)
    generation_date TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_genmeta_generator ON generation_metadata(generator);
CREATE INDEX idx_genmeta_method ON generation_metadata(generation_method);

-- =============================================================================
-- VALIDATION METADATA — AI + human review tracking
-- =============================================================================

CREATE TABLE validation_records (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    question_id     UUID NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
    validator_type  TEXT NOT NULL,             -- 'claude', 'gpt4', 'gemini', 'human'
    validator_id    TEXT,                      -- model version or expert ID
    verdict         TEXT NOT NULL,             -- 'correct', 'incorrect', 'ambiguous', 'approved', 'rejected'
    confidence      REAL,
    notes           TEXT,
    validated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_validation_question ON validation_records(question_id);
CREATE INDEX idx_validation_type ON validation_records(validator_type);

-- =============================================================================
-- QUESTION SOURCES — link questions back to authoritative sources
-- =============================================================================

CREATE TABLE question_sources (
    question_id     UUID REFERENCES questions(id) ON DELETE CASCADE,
    source_id       UUID REFERENCES sources(id) ON DELETE CASCADE,
    PRIMARY KEY (question_id, source_id)
);

-- =============================================================================
-- LLM EVALUATION RESULTS — benchmark scores
-- =============================================================================

CREATE TABLE evaluation_runs (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    model_name      TEXT NOT NULL,
    model_version   TEXT,
    prompt_strategy TEXT NOT NULL DEFAULT 'zero_shot',
    temperature     REAL NOT NULL DEFAULT 0.0,
    run_number      INTEGER NOT NULL DEFAULT 1,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at    TIMESTAMPTZ,
    total_questions INTEGER,
    correct_count   INTEGER,
    accuracy        REAL,
    metadata        JSONB DEFAULT '{}'
);

CREATE INDEX idx_evalruns_model ON evaluation_runs(model_name);

CREATE TABLE evaluation_answers (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    run_id          UUID NOT NULL REFERENCES evaluation_runs(id) ON DELETE CASCADE,
    question_id     UUID NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
    model_answer    TEXT,
    is_correct      BOOLEAN,
    response_time_ms INTEGER,
    raw_response    TEXT,
    UNIQUE (run_id, question_id)
);

CREATE INDEX idx_evalanswers_run ON evaluation_answers(run_id);
CREATE INDEX idx_evalanswers_question ON evaluation_answers(question_id);
CREATE INDEX idx_evalanswers_correct ON evaluation_answers(is_correct);

-- =============================================================================
-- UTILITY: updated_at trigger
-- =============================================================================

CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_sources_updated BEFORE UPDATE ON sources
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER trg_facts_updated BEFORE UPDATE ON facts
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER trg_questions_updated BEFORE UPDATE ON questions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- =============================================================================
-- VIEWS for quick analysis
-- =============================================================================

-- Question distribution overview
CREATE VIEW v_question_distribution AS
SELECT
    domain,
    difficulty,
    question_type,
    status,
    count(*) AS count
FROM questions
GROUP BY domain, difficulty, question_type, status
ORDER BY domain, difficulty;

-- Generator breakdown
CREATE VIEW v_generator_distribution AS
SELECT
    gm.generator,
    gm.generation_method,
    q.domain,
    q.status,
    count(*) AS count
FROM generation_metadata gm
JOIN questions q ON q.id = gm.question_id
GROUP BY gm.generator, gm.generation_method, q.domain, q.status
ORDER BY gm.generator, q.domain;

-- Self-preference analysis helper
CREATE VIEW v_self_preference AS
SELECT
    er.model_name AS evaluated_model,
    gm.generator AS question_generator,
    count(*) AS total_questions,
    sum(CASE WHEN ea.is_correct THEN 1 ELSE 0 END) AS correct,
    round(avg(CASE WHEN ea.is_correct THEN 1.0 ELSE 0.0 END) * 100, 2) AS accuracy_pct
FROM evaluation_answers ea
JOIN evaluation_runs er ON er.id = ea.run_id
JOIN questions q ON q.id = ea.question_id
JOIN generation_metadata gm ON gm.question_id = q.id
GROUP BY er.model_name, gm.generator
ORDER BY er.model_name, gm.generator;

-- =============================================================================
-- Done. Schema ready for WineBench Phase 1.
-- =============================================================================


-- =============================================================================
-- Migration 004 — Human review tables (Phase 4: multi-expert human review)
-- Mirrors migrations/004_human_review.sql so a fresh cluster boots ready.
-- Strictly additive; idempotent.
-- =============================================================================

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

CREATE TABLE IF NOT EXISTS human_reviewers (
    id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email             TEXT NOT NULL UNIQUE,
    name              TEXT NOT NULL,
    credentials       TEXT,
    expertise_domains TEXT[] DEFAULT '{}',
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_active_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

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
    labels_correct           rubric_score,

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
