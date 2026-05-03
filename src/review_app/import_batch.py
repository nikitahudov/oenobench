"""Import a gold-sheet-style CSV into a `review_batches` row + items.

Usage:
    python -m src.review_app.import_batch \\
        --csv data/reports/gold_sheet_release_v1.csv \\
        --name release_v1_pilot \\
        [--description "..."] [--dry-run] [--replace]

The CSV must contain at minimum the columns `uuid` and `public_qid`. Every
`uuid` is validated against `questions.id`; if any are unknown the importer
exits non-zero without writing.

Idempotency: a batch with a given `name` exists exactly once. Re-running the
importer with the same `--name` errors unless `--replace` is passed, in which
case the existing batch row + its items are deleted within the same
transaction before the new batch is inserted.
"""

from __future__ import annotations

import csv
import os
import sys
from pathlib import Path
from typing import Iterable

import click
from loguru import logger
from psycopg2.extras import execute_values

from src.utils.db import get_pg


REQUIRED_COLUMNS = ("uuid", "public_qid")


def _read_csv_rows(csv_path: Path) -> list[dict[str, str]]:
    with csv_path.open("r", newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        missing = [c for c in REQUIRED_COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise click.ClickException(
                f"CSV is missing required column(s): {', '.join(missing)}"
            )
        rows = []
        for i, row in enumerate(reader, start=1):
            uid = (row.get("uuid") or "").strip()
            qid = (row.get("public_qid") or "").strip()
            if not uid:
                raise click.ClickException(f"Row {i}: empty uuid")
            if not qid:
                raise click.ClickException(f"Row {i}: empty public_qid")
            rows.append({"uuid": uid, "public_qid": qid})
    return rows


def _validate_uuids(conn, uuids: Iterable[str]) -> set[str]:
    """Return the set of UUIDs missing from `questions.id`."""
    uuids = list(uuids)
    if not uuids:
        return set()
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id::text AS id FROM questions WHERE id = ANY(%s::uuid[])",
            (uuids,),
        )
        found = {r["id"] for r in cur.fetchall()}
    return set(uuids) - found


def _delete_existing_batch(conn, name: str) -> None:
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM review_batches WHERE name = %s", (name,))
        row = cur.fetchone()
        if not row:
            return
        batch_id = row["id"]
        cur.execute("DELETE FROM review_batch_items WHERE batch_id = %s", (batch_id,))
        cur.execute("DELETE FROM review_batches WHERE id = %s", (batch_id,))
        logger.info(f"Deleted existing batch '{name}' (id={batch_id})")


@click.command()
@click.option(
    "--csv",
    "csv_path",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Path to gold-sheet-style CSV (must contain uuid + public_qid columns).",
)
@click.option(
    "--name",
    required=True,
    type=str,
    help="Slug-like batch name; must be unique unless --replace is passed.",
)
@click.option(
    "--description",
    default=None,
    type=str,
    help="Optional human-readable description.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Validate the CSV without writing anything to the database.",
)
@click.option(
    "--replace",
    is_flag=True,
    default=False,
    help="If a batch with --name already exists, delete it first.",
)
def main(
    csv_path: Path,
    name: str,
    description: str | None,
    dry_run: bool,
    replace: bool,
) -> None:
    csv_path = csv_path.resolve()
    logger.info(f"Reading {csv_path}")
    rows = _read_csv_rows(csv_path)
    logger.info(f"Read {len(rows)} rows")

    conn = get_pg()
    # Ensure we're not entering with a stray open transaction (psycopg2
    # forbids set_session inside a txn). Rollback is a no-op if we're idle.
    try:
        conn.rollback()
    except Exception:
        pass
    conn.autocommit = False

    try:
        unknown = _validate_uuids(conn, [r["uuid"] for r in rows])
        if unknown:
            logger.error(f"{len(unknown)} unknown UUID(s) not found in questions:")
            for uid in sorted(unknown):
                logger.error(f"  {uid}")
            conn.rollback()
            sys.exit(1)
        logger.info("All UUIDs validated against questions table")

        if dry_run:
            logger.info(
                f"[dry-run] Would import {len(rows)} questions into batch '{name}'"
            )
            conn.rollback()
            click.echo(
                f"[dry-run] {len(rows)} rows would be imported into batch '{name}'"
            )
            return

        with conn.cursor() as cur:
            cur.execute("SELECT id FROM review_batches WHERE name = %s", (name,))
            existing = cur.fetchone()
            if existing and not replace:
                conn.rollback()
                raise click.ClickException(
                    f"Batch '{name}' already exists (id={existing['id']}). "
                    "Pass --replace to overwrite."
                )
            if existing and replace:
                _delete_existing_batch(conn, name)

            cur.execute(
                """
                INSERT INTO review_batches
                    (name, description, source_csv_path, question_count, created_by)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    name,
                    description,
                    str(csv_path),
                    len(rows),
                    os.getenv("USER", "unknown"),
                ),
            )
            batch_id = cur.fetchone()["id"]

            execute_values(
                cur,
                """
                INSERT INTO review_batch_items
                    (batch_id, question_id, public_qid, position)
                VALUES %s
                """,
                [
                    (batch_id, r["uuid"], r["public_qid"], i)
                    for i, r in enumerate(rows)
                ],
            )

        conn.commit()
        logger.info(f"imported {len(rows)} questions into batch '{name}' (id={batch_id})")
        click.echo(
            f"imported {len(rows)} questions into batch '{name}' (id={batch_id})"
        )
    except click.ClickException:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    except Exception:
        conn.rollback()
        logger.exception("Import failed; rolled back")
        raise


if __name__ == "__main__":
    main()
