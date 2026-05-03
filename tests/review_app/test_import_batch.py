"""Tests for src.review_app.import_batch.

These are DB-integration tests; they assume PostgreSQL is reachable via
src.utils.db.get_pg and that migration 004 has been applied. Each test
runs inside a savepoint that's rolled back at teardown so we never leave
artefacts in the DB.

Gated by env var OENOBENCH_REVIEW_TESTS_DB=1 (default: on if PG is up,
since the rest of the test suite is integration-style anyway).
"""

from __future__ import annotations

import csv
import os
import uuid
from pathlib import Path

import pytest
from click.testing import CliRunner

from src.review_app.import_batch import main as import_main
from src.utils.db import get_pg


pytestmark = pytest.mark.integration


def _seed_questions(conn, n: int) -> list[tuple[str, str]]:
    """Insert N stub questions and return [(uuid, public_qid), ...]."""
    suffix = uuid.uuid4().hex[:8]
    inserted: list[tuple[str, str]] = []
    with conn.cursor() as cur:
        for i in range(n):
            qid_text = f"WB-TEST-{suffix}-{i:03d}"
            cur.execute(
                """
                INSERT INTO questions
                    (question_id, domain, question_type, difficulty,
                     cognitive_dim, question_text, correct_answer)
                VALUES (%s, 'wine_regions', 'multiple_choice', '1',
                        'recall', %s, 'A')
                RETURNING id::text
                """,
                (qid_text, f"stub question {i}"),
            )
            row = cur.fetchone()
            inserted.append((row["id"], qid_text))
    return inserted


def _write_csv(tmp_path: Path, rows: list[tuple[str, str]]) -> Path:
    csv_path = tmp_path / "batch.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["uuid", "public_qid", "extra_col"])
        w.writeheader()
        for uid, qid in rows:
            w.writerow({"uuid": uid, "public_qid": qid, "extra_col": "ignored"})
    return csv_path


def _batch_count(conn, name: str) -> tuple[int, int]:
    """Return (batch_row_count, item_count) for a given batch name."""
    with conn.cursor() as cur:
        cur.execute("SELECT id, question_count FROM review_batches WHERE name = %s", (name,))
        row = cur.fetchone()
        if not row:
            return 0, 0
        cur.execute(
            "SELECT count(*) AS c FROM review_batch_items WHERE batch_id = %s",
            (row["id"],),
        )
        items = cur.fetchone()["c"]
    return 1, items


@pytest.fixture
def db_conn():
    if not _can_connect():
        pytest.skip("PostgreSQL not reachable; skipping DB integration test")
    conn = get_pg()
    # The shared psycopg2 connection may already be inside a transaction
    # from a prior test or from the import CLI; rollback first so we can
    # safely flip to autocommit (psycopg2 forbids set_session in a txn).
    try:
        conn.rollback()
    except Exception:
        pass
    conn.autocommit = True
    yield conn


def _can_connect() -> bool:
    if os.getenv("OENOBENCH_REVIEW_TESTS_DB") == "0":
        return False
    try:
        c = get_pg()
        with c.cursor() as cur:
            cur.execute("SELECT 1")
        c.rollback()
        return True
    except Exception:
        return False


@pytest.fixture
def seeded(db_conn, tmp_path):
    """Yield a CSV path + the batch name + cleanup hook for 3 stub questions."""
    rows = _seed_questions(db_conn, 3)
    name = f"test_batch_{uuid.uuid4().hex[:8]}"
    csv_path = _write_csv(tmp_path, rows)
    try:
        yield {"rows": rows, "csv": csv_path, "name": name, "conn": db_conn}
    finally:
        # Cleanup: batches + their items first (cascade handles items), then questions
        with db_conn.cursor() as cur:
            cur.execute("DELETE FROM review_batches WHERE name = %s", (name,))
            cur.execute(
                "DELETE FROM questions WHERE id = ANY(%s::uuid[])",
                ([uid for uid, _ in rows],),
            )


def test_happy_path_imports_three_questions(seeded):
    runner = CliRunner()
    result = runner.invoke(
        import_main,
        [
            "--csv", str(seeded["csv"]),
            "--name", seeded["name"],
            "--description", "fixture batch",
        ],
    )
    assert result.exit_code == 0, result.output
    batch_n, items_n = _batch_count(seeded["conn"], seeded["name"])
    assert batch_n == 1
    assert items_n == 3
    with seeded["conn"].cursor() as cur:
        cur.execute(
            "SELECT question_count FROM review_batches WHERE name = %s",
            (seeded["name"],),
        )
        assert cur.fetchone()["question_count"] == 3


def test_dry_run_inserts_nothing(seeded):
    runner = CliRunner()
    result = runner.invoke(
        import_main,
        [
            "--csv", str(seeded["csv"]),
            "--name", seeded["name"],
            "--dry-run",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "[dry-run]" in result.output
    batch_n, items_n = _batch_count(seeded["conn"], seeded["name"])
    assert batch_n == 0
    assert items_n == 0


def test_unknown_uuid_exits_nonzero(db_conn, tmp_path):
    bogus_uuid = str(uuid.uuid4())
    csv_path = _write_csv(tmp_path, [(bogus_uuid, "WB-DOES-NOT-EXIST")])
    name = f"test_batch_{uuid.uuid4().hex[:8]}"
    runner = CliRunner()
    result = runner.invoke(
        import_main,
        ["--csv", str(csv_path), "--name", name],
    )
    assert result.exit_code != 0
    batch_n, _ = _batch_count(db_conn, name)
    assert batch_n == 0


def test_replace_overwrites_existing_batch(seeded):
    runner = CliRunner()
    # First import
    r1 = runner.invoke(
        import_main,
        ["--csv", str(seeded["csv"]), "--name", seeded["name"]],
    )
    assert r1.exit_code == 0, r1.output
    _, items_n = _batch_count(seeded["conn"], seeded["name"])
    assert items_n == 3

    # Re-import without --replace should error
    r2 = runner.invoke(
        import_main,
        ["--csv", str(seeded["csv"]), "--name", seeded["name"]],
    )
    assert r2.exit_code != 0

    # Re-import with --replace should succeed and we should still have 3 items
    r3 = runner.invoke(
        import_main,
        ["--csv", str(seeded["csv"]), "--name", seeded["name"], "--replace"],
    )
    assert r3.exit_code == 0, r3.output
    _, items_n = _batch_count(seeded["conn"], seeded["name"])
    assert items_n == 3
