"""Maintenance script — purge corrupt Bordeaux facts (v2.3 fix #14d).

Deletes facts produced by the broken Saint-Émilion classified-growths table
parser in ``src/scrapers/bordeaux.py`` (fixed in v2.3 fix #14c). Two patterns
are targeted:

  1. Off-by-one pairing — ``<Château X> is a classified Bordeaux estate in
     Château Y``. 43 such rows were in production; all have a region entity
     that is itself a château name.

  2. Table-markup leakage — ``align="center"``, ``colspan="2"``, ``&nbsp;``
     or literal ``|`` in the region slot (9 such rows).

The script is idempotent and defaults to ``--dry-run``. Cascade policy: the
``question_facts`` foreign key on ``facts.id`` has ``ON DELETE CASCADE``, so
any linked question_facts rows are dropped automatically. Questions
themselves are NOT deleted (cascade doesn't propagate that far) because the
corrupt fact may have been one of several supporting facts — it's the user's
call whether to purge the whole question.

Usage:
    python -m src.scrapers._purge_bordeaux_corrupt_facts            # dry-run (default)
    python -m src.scrapers._purge_bordeaux_corrupt_facts --force    # actually delete
"""

from __future__ import annotations

import click
from loguru import logger

from src.utils.db import get_pg


# SQL patterns that match the two corruption classes identified in audit
# gold-v3 + ad-hoc DB review (2026-04-22).
_CORRUPT_FACT_CLAUSES = [
    # 1. "… classified Bordeaux estate in Château …"  (off-by-one)
    "fact_text ILIKE '%% is a classified Bordeaux estate in Château %%'",
    # 2. Table-attribute markup leaks into the region slot.
    "fact_text ILIKE '%%align=%%'",
    "fact_text ILIKE '%%colspan=%%'",
    "fact_text ILIKE '%%rowspan=%%'",
    "fact_text ILIKE '%%bgcolor=%%'",
    "fact_text ILIKE '%%&nbsp;%%'",
    # 3. Any classified-Bordeaux-estate fact whose region contains a literal
    #    pipe character (always table markup, never a real commune name).
    "(fact_text ILIKE '%% classified Bordeaux estate in %%' AND fact_text ~ '\\|')",
]

_COUNT_SQL = f"""
    SELECT id, fact_text
    FROM facts
    WHERE {' OR '.join(_CORRUPT_FACT_CLAUSES)}
"""

_DELETE_SQL = f"""
    DELETE FROM facts
    WHERE {' OR '.join(_CORRUPT_FACT_CLAUSES)}
    RETURNING id, fact_text
"""


def find_corrupt_facts() -> list[dict]:
    """Return the list of corrupt fact rows that match the purge criteria."""
    conn = get_pg()
    cur = conn.cursor()
    cur.execute(_COUNT_SQL)
    return [dict(r) for r in cur.fetchall()]


def purge_corrupt_facts(dry_run: bool = True) -> int:
    """Delete corrupt Bordeaux facts.

    Returns the number of fact rows deleted (or that would be deleted, in
    dry-run mode). Linked ``question_facts`` rows cascade automatically.
    """
    matches = find_corrupt_facts()
    logger.info(f"Found {len(matches)} corrupt Bordeaux facts matching purge criteria")
    for row in matches[:20]:
        logger.info(f"  {row['fact_text']}")
    if len(matches) > 20:
        logger.info(f"  … and {len(matches) - 20} more")

    if dry_run:
        logger.info(f"DRY RUN — would delete {len(matches)} facts. Re-run with --force to execute.")
        return len(matches)

    if not matches:
        return 0

    conn = get_pg()
    cur = conn.cursor()
    cur.execute(_DELETE_SQL)
    deleted = cur.fetchall()
    conn.commit()
    logger.info(f"Deleted {len(deleted)} corrupt facts (question_facts cascaded via FK)")
    return len(deleted)


@click.command()
@click.option("--force", is_flag=True, help="Actually delete (default is dry-run)")
def main(force: bool) -> None:
    """Purge corrupt Bordeaux facts (off-by-one pairing + table-markup leakage)."""
    n = purge_corrupt_facts(dry_run=not force)
    if force:
        click.echo(f"Deleted {n} corrupt Bordeaux facts.")
    else:
        click.echo(f"Dry run: {n} corrupt Bordeaux facts would be deleted. Pass --force to execute.")


if __name__ == "__main__":
    main()
