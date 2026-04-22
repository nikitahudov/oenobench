"""v2.3 Phase F fix #14a/b — Purge legacy + Bordeaux-corrupt template questions.

Gold-v3 human review + audit_pilot_v3 surfaced two classes of stale template
questions that must be removed from the DB before the next audit and the
Phase E 10k run:

  a) Legacy templates: ``T-REG-COUNTRY-01``, ``T-GRP-REGION-01``,
     ``T-GRP-ORIGIN-01``, ``T-REG-GRAPE-01`` were *deleted from the code*
     in v2.2 fix #8a but the already-generated questions remained in the DB.

  b) Bordeaux-corrupt templates: 14 template questions anchored to facts
     with the bug pattern ``'... is a classified Bordeaux estate in Château
     ...'`` (Sampler team is fixing the scraper separately), plus any facts
     still carrying HTML attribute residue (``align=``, ``&nbsp;``). The
     questions built from these malformed facts are unrecoverable and must
     be purged.

All FKs referencing ``questions(id)`` (``generation_metadata``,
``question_facts``, ``question_sources``, ``validation_records``,
``evaluation_answers``, ``audit_findings``, ``audit_findings_human``) use
``ON DELETE CASCADE`` in both migrations 001 (``init.sql``) and 002
(``002_audit_schema.sql``). A single ``DELETE FROM questions WHERE id = ANY(...)``
is sufficient and consistent.

Usage::

    python -m src.generators._purge_legacy_templates             # dry-run (default)
    python -m src.generators._purge_legacy_templates --force     # actually delete
"""

from __future__ import annotations

import click
from loguru import logger

from src.utils.db import get_pg


# ─── Target question selectors ──────────────────────────────────────────────

# v2.2 fix #8a — templates deleted from the registry in code
_LEGACY_TEMPLATE_IDS: tuple[str, ...] = (
    "T-REG-COUNTRY-01",
    "T-GRP-REGION-01",
    "T-GRP-ORIGIN-01",
    "T-REG-GRAPE-01",
)

# SQL to list legacy-template questions (fix #14a)
_SELECT_LEGACY_SQL = """
    SELECT q.id, q.question_id, gm.template_id
    FROM questions q
    JOIN generation_metadata gm ON gm.question_id = q.id
    WHERE gm.template_id = ANY(%s)
      AND gm.generation_method = 'template'
    ORDER BY q.question_id
"""

# SQL to list Bordeaux-corrupt template questions (fix #14b)
_SELECT_BORDEAUX_SQL = """
    SELECT DISTINCT q.id, q.question_id
    FROM questions q
    JOIN generation_metadata gm ON gm.question_id = q.id
    JOIN question_facts qf ON qf.question_id = q.id
    JOIN facts f ON f.id = qf.fact_id
    WHERE gm.generation_method = 'template'
      AND (
             f.fact_text ILIKE '%% is a classified Bordeaux estate in Château %%'
          OR f.fact_text ILIKE '%%align=%%'
          OR f.fact_text ILIKE '%%&nbsp;%%'
      )
    ORDER BY q.question_id
"""


# ─── Helpers ────────────────────────────────────────────────────────────────


def _fetch_legacy_questions() -> list[dict]:
    conn = get_pg()
    cur = conn.cursor()
    cur.execute(_SELECT_LEGACY_SQL, (list(_LEGACY_TEMPLATE_IDS),))
    return list(cur.fetchall())


def _fetch_bordeaux_questions() -> list[dict]:
    conn = get_pg()
    cur = conn.cursor()
    cur.execute(_SELECT_BORDEAUX_SQL)
    return list(cur.fetchall())


def _delete_questions(question_uuids: list[str]) -> int:
    """DELETE FROM questions — cascades to FK children via ON DELETE CASCADE."""
    if not question_uuids:
        return 0
    conn = get_pg()
    cur = conn.cursor()
    deleted = 0
    # Batch of 200 keeps the IN-list modest and ID binding cheap.
    for i in range(0, len(question_uuids), 200):
        batch = question_uuids[i : i + 200]
        cur.execute(
            "DELETE FROM questions WHERE id = ANY(%s::uuid[])",
            (batch,),
        )
        deleted += cur.rowcount
    conn.commit()
    return deleted


def _preview(label: str, rows: list[dict]) -> None:
    click.echo(f"\n── {label}: {len(rows)} question(s) ──")
    for r in rows[:10]:
        tid = r.get("template_id", "—")
        click.echo(f"   {r['question_id']:<20}  template={tid}")
    if len(rows) > 10:
        click.echo(f"   … and {len(rows) - 10} more")


# ─── CLI ────────────────────────────────────────────────────────────────────


@click.command()
@click.option(
    "--force",
    is_flag=True,
    help="Actually delete the matched questions. Default is dry-run.",
)
def main(force: bool) -> None:
    """v2.3 Phase F fix #14 — purge legacy + Bordeaux-corrupt template questions."""
    legacy = _fetch_legacy_questions()
    bordeaux = _fetch_bordeaux_questions()

    _preview("Legacy-template questions (fix #14a)", legacy)
    _preview("Bordeaux-corrupt template questions (fix #14b)", bordeaux)

    # Dedup: a Bordeaux-corrupt question could also be legacy-template-tagged.
    all_uuids_seen: set[str] = set()
    all_uuids: list[str] = []
    for row in legacy + bordeaux:
        uid = str(row["id"])
        if uid in all_uuids_seen:
            continue
        all_uuids_seen.add(uid)
        all_uuids.append(uid)

    click.echo(f"\nTotal unique questions to delete: {len(all_uuids)}")

    if not force:
        click.echo("\n[DRY-RUN] No rows deleted. Re-run with --force to execute.")
        return

    if not all_uuids:
        click.echo("\nNothing to delete. Done.")
        return

    deleted = _delete_questions(all_uuids)
    logger.info(f"Purged {deleted} template questions (legacy + Bordeaux-corrupt)")
    click.echo(f"\n[FORCE] Deleted {deleted} questions.")

    # Sanity check: re-run the selectors — should both be empty now.
    remaining_legacy = _fetch_legacy_questions()
    remaining_bordeaux = _fetch_bordeaux_questions()
    click.echo(
        f"Post-delete verification: legacy={len(remaining_legacy)}, "
        f"bordeaux-corrupt={len(remaining_bordeaux)} (both should be 0)"
    )


if __name__ == "__main__":
    main()
