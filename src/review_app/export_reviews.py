"""Export human reviews for a batch as a flat CSV (one row per review).

Usage:
    python -m src.review_app.export_reviews \\
        --batch release_v1_pilot \\
        --out /tmp/reviews.csv \\
        [--include-incomplete]

The output joins `human_reviews` + `human_reviewers` + `questions` so each
row carries everything needed for κ analysis or paper-ready summaries.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import click
from loguru import logger

from src.utils.db import get_pg


# Export emits both the v2 rubric set (8 cols, written by the v2 review form)
# and the legacy v1 cols (still on `human_reviews`, populated only on
# pre-v2 reviews) so downstream κ analysis can choose either schema.
RUBRIC_COLUMNS = (
    "answer_correct",
    "distractors_plausible",
    "not_ambiguous",
    "source_faithful",
    "needs_source",
    "no_vague_language",
    "labels_correct",
    "verbatim_copy",
    # Legacy v1 columns (kept for historical review rows).
    "difficulty_match",
    "cognitive_match",
    "wine_category_leak",
)

OUTPUT_COLUMNS = (
    "review_id",
    "batch_name",
    "public_qid",
    "question_id",
    "domain",
    "difficulty",
    "question_text",
    "correct_answer",
    "reviewer_email",
    "reviewer_name",
    "reviewer_credentials",
    *RUBRIC_COLUMNS,
    "overall_verdict",
    "suggested_answer",
    "suggested_difficulty",
    "notes",
    "time_spent_seconds",
    "is_complete",
    "created_at",
    "updated_at",
)


@click.command()
@click.option("--batch", "batch_name", required=True, type=str, help="Batch name slug.")
@click.option(
    "--out",
    "out_path",
    required=True,
    type=click.Path(dir_okay=False, path_type=Path),
    help="Output CSV path.",
)
@click.option(
    "--include-incomplete",
    is_flag=True,
    default=False,
    help="Include reviews where is_complete=false (default: completed only).",
)
def main(batch_name: str, out_path: Path, include_incomplete: bool) -> None:
    conn = get_pg()
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM review_batches WHERE name = %s", (batch_name,))
        row = cur.fetchone()
        if not row:
            logger.error(f"No batch named '{batch_name}'")
            sys.exit(1)

    rubric_select = ", ".join(f"hr.{c}" for c in RUBRIC_COLUMNS)
    where_complete = "" if include_incomplete else "AND hr.is_complete = TRUE"

    sql = f"""
        SELECT
            hr.id::text             AS review_id,
            b.name                  AS batch_name,
            q.question_id           AS public_qid,
            hr.question_id::text    AS question_id,
            q.domain::text          AS domain,
            q.difficulty::text      AS difficulty,
            q.question_text         AS question_text,
            q.correct_answer        AS correct_answer,
            hu.email                AS reviewer_email,
            hu.name                 AS reviewer_name,
            hu.credentials          AS reviewer_credentials,
            {rubric_select},
            hr.overall_verdict::text     AS overall_verdict,
            hr.suggested_answer          AS suggested_answer,
            hr.suggested_difficulty      AS suggested_difficulty,
            hr.notes                     AS notes,
            hr.time_spent_seconds        AS time_spent_seconds,
            hr.is_complete               AS is_complete,
            hr.created_at                AS created_at,
            hr.updated_at                AS updated_at
        FROM human_reviews hr
        JOIN human_reviewers hu ON hu.id = hr.reviewer_id
        JOIN questions q       ON q.id = hr.question_id
        JOIN review_batches b  ON b.id = hr.batch_id
        WHERE b.name = %s
        {where_complete}
        ORDER BY hr.created_at, hr.id
    """

    with conn.cursor() as cur:
        cur.execute(sql, (batch_name,))
        rows = cur.fetchall()

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(OUTPUT_COLUMNS))
        writer.writeheader()
        for r in rows:
            # cast each rubric enum value to a plain string when present
            row_out = {col: r.get(col) for col in OUTPUT_COLUMNS}
            for c in RUBRIC_COLUMNS:
                v = row_out.get(c)
                if v is not None and not isinstance(v, str):
                    row_out[c] = str(v)
            writer.writerow(row_out)

    logger.info(f"Exported {len(rows)} reviews from batch '{batch_name}' to {out_path}")
    click.echo(f"Exported {len(rows)} reviews to {out_path}")


if __name__ == "__main__":
    main()
