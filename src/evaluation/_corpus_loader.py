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


def load_questions(corpus: str = "sample", limit: int | None = None) -> list[EvalQuestion]:
    """Load questions from sample.questions (default) or public.questions.

    `corpus` must be either 'sample' or 'public'. Returns a list of EvalQuestion
    sorted by id for determinism.

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

    # For the sample schema we can join generation_metadata directly.
    # For the public schema the metadata is also in public.generation_metadata.
    # Both schemas use the same join pattern; we just prefix with the schema.
    # Filter out rows with NULL options or NULL/empty correct_answer — these are
    # stub/legacy rows that are not answerable as MCQ.  Public corpus contains
    # 153 such "stub question N" rows accidentally left over from earlier
    # pipeline development; they have question_type=multiple_choice but no
    # options column populated, which would crash _parse_options below.
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
        WHERE q.options IS NOT NULL
          AND q.correct_answer IS NOT NULL
          AND q.correct_answer <> ''
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
