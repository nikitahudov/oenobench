-- Phase 2g.17 — at-risk question audit.
--
-- Lists active (non-cb_reserve) questions in the corpus tagged ":tag"
-- whose stem mentions one of the globally-ubiquitous international grape
-- varieties AND whose correct_answer_text is a region-class entity.
-- These questions are likely to suffer "ubiquitous-grape ambiguity"
-- (e.g., "Which region produces Cabernet?" — many regions are valid
-- answers, so any reasonable distractor could also be correct).
--
-- Usage:
--   docker exec -i wb-postgres psql -U winebench -d winebench \
--     -v tag="audit_pilot_v14c" < scripts/audit_ubiquity_check.sql

\set ON_ERROR_STOP on

WITH ubiquitous_grapes AS (
    SELECT unnest(ARRAY[
        'Cabernet Sauvignon',
        'Chardonnay',
        'Merlot',
        'Pinot Noir',
        'Sauvignon Blanc',
        'Syrah',
        'Shiraz',
        'Riesling'
    ]) AS grape
)
SELECT  q.question_id  AS public_qid,
        gm.generation_method  AS strategy,
        q.domain,
        q.difficulty::text   AS level,
        q.question_text
FROM    questions q
JOIN    generation_metadata gm ON gm.question_id = q.id
WHERE   :'tag' = ANY(q.tags)
  AND   q.status::text != 'cb_reserve'
  AND   EXISTS (
            SELECT 1 FROM ubiquitous_grapes ug
            WHERE q.question_text ILIKE '%' || ug.grape || '%'
        )
ORDER BY gm.generation_method, q.question_id;
