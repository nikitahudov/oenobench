"""Load eval questions from sample.questions or public.questions.

Verified column layout (docker exec wb-postgres psql ... \\d sample.questions):
  id UUID, question_text TEXT, options JSONB, correct_answer TEXT,
  domain domain_type, difficulty difficulty_level, question_type question_type.

The options JSONB is a list of objects: [{"id": "A", "text": "..."}, ...].
The strategy (generation_method) lives in sample.generation_metadata, joined
here via a LEFT JOIN so public corpus questions without metadata still load.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from src.utils.db import get_pg


@dataclass(frozen=True)
class EvalQuestion:
    id: str  # UUID as string
    question_text: str
    options: dict[str, str]  # {"A": "...", "B": "...", ...}
    correct_answer: str  # "A"|"B"|"C"|"D"
    domain: str
    difficulty: str | None
    strategy: str | None


def _parse_options(raw) -> dict[str, str]:
    """Parse the options JSONB column into a plain {"A": text, ...} dict.

    Handles both:
    - list  [{"id": "A", "text": "..."}, ...]   (sample/public schema)
    - dict  {"A": "...", "B": "..."}             (legacy / public fallback)
    - Already a Python list/dict (psycopg2 converts JSONB automatically).
    """
    if isinstance(raw, str):
        raw = json.loads(raw)
    if isinstance(raw, list):
        return {item["id"]: item["text"] for item in raw}
    if isinstance(raw, dict):
        return raw
    raise ValueError(f"Unexpected options shape: {type(raw)!r}")


DEFAULT_PUBLIC_RELEASE = "v1.2"


def load_questions(
    corpus: str = "sample",
    limit: int | None = None,
    release: str | None = None,
) -> list[EvalQuestion]:
    """Load questions from sample.questions (default) or public.questions.

    `corpus` must be either 'sample' or 'public'. Returns a list of EvalQuestion
    sorted by id for determinism.

    `release` pins the public corpus to a specific tagged release subset.  When
    `corpus="public"` and `release` is None, defaults to `DEFAULT_PUBLIC_RELEASE`
    (currently `"v1.2"` — 3,329 questions tagged `release_v1.2` with
    status='draft').  Pass `release="all"` to load the full public table
    (5,893 rows minus stubs); useful for ad-hoc audits, NOT for the official eval.

    For the sample corpus the `release` parameter is ignored — the sample table
    has no release tagging.

    Column notes:
    - `options` is JSONB: list of {"id": letter, "text": ...} objects.
    - `correct_answer` is TEXT holding the letter ("A"/"B"/"C"/"D").
    - `difficulty` is a difficulty_level enum, cast to text.
    - `strategy` comes from generation_metadata.generation_method via LEFT JOIN.
      For public corpus rows without generation_metadata rows it will be None.
    """
    if corpus not in {"sample", "public"}:
        raise ValueError(f"corpus must be 'sample' or 'public', got {corpus!r}")

    schema = corpus

    # Defensive null-check — release_v1.2 already excludes stubs (verified:
    # 0 of the 153 stub-question rows carry the release tag), but the filter
    # also covers ad-hoc release="all" use and any future release that
    # accidentally re-introduces NULL options.
    where_clauses = [
        "q.options IS NOT NULL",
        "q.correct_answer IS NOT NULL",
        "q.correct_answer <> ''",
    ]

    # Public-corpus release pinning.  Pass release="all" to opt out.
    if corpus == "public":
        effective_release = release if release is not None else DEFAULT_PUBLIC_RELEASE
        if effective_release != "all":
            tag = f"release_{effective_release}"
            where_clauses.append(f"'{tag}' = ANY(q.tags)")
            where_clauses.append("q.status::text = 'draft'")

    where_sql = "\n          AND ".join(where_clauses)
    sql = f"""
        SELECT
            q.id::text          AS id,
            q.question_text,
            q.options,
            q.correct_answer,
            q.domain::text      AS domain,
            q.difficulty::text  AS difficulty,
            gm.generation_method AS strategy
        FROM {schema}.questions q
        LEFT JOIN {schema}.generation_metadata gm
               ON gm.question_id = q.id
        WHERE {where_sql}
        ORDER BY q.id
    """
    if limit is not None:
        sql += f" LIMIT {int(limit)}"

    conn = get_pg()
    with conn.cursor() as cur:
        cur.execute(sql)
        rows = cur.fetchall()

    out: list[EvalQuestion] = []
    for r in rows:
        out.append(EvalQuestion(
            id=r["id"],
            question_text=r["question_text"],
            options=_parse_options(r["options"]),
            correct_answer=(r["correct_answer"] or "").strip(),
            domain=r["domain"],
            difficulty=r.get("difficulty"),
            strategy=r.get("strategy"),
        ))
    return out
