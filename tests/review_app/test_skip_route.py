"""Tests for POST /skip-question.

The skip endpoint appends a question_id to a per-batch list in
`session["skipped_question_ids"]`. The skip is in-session only — other
reviewers and future sessions for the same reviewer still see it.

DB-integration tests; require PostgreSQL reachable via src.utils.db.get_pg
and migrations 004 + 005 applied.
"""

from __future__ import annotations

import base64
import os
import uuid
from typing import Iterable

import pytest

from src.review_app.app import create_app
from src.utils.db import get_pg


pytestmark = pytest.mark.integration


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
def db_conn():
    if not _can_connect():
        pytest.skip("PostgreSQL not reachable; skipping DB integration test")
    conn = get_pg()
    try:
        conn.rollback()
    except Exception:
        pass
    conn.autocommit = True
    yield conn


@pytest.fixture
def app():
    os.environ["REVIEW_APP_USER"] = "admin"
    os.environ["REVIEW_APP_PASSWORD"] = "test-pw"
    os.environ.setdefault("REVIEW_APP_SECRET", "test-secret-" + uuid.uuid4().hex)
    a = create_app()
    a.config["TESTING"] = True
    return a


@pytest.fixture
def client(app):
    return app.test_client()


def _basic_auth_headers() -> dict:
    creds = base64.b64encode(b"admin:test-pw").decode()
    return {"Authorization": f"Basic {creds}"}


def _seed_questions(conn, n: int) -> list[tuple[str, str]]:
    suffix = uuid.uuid4().hex[:8]
    out: list[tuple[str, str]] = []
    with conn.cursor() as cur:
        for i in range(n):
            qid_text = f"WB-SKIP-{suffix}-{i:03d}"
            cur.execute(
                """
                INSERT INTO questions
                    (question_id, domain, question_type, difficulty,
                     cognitive_dim, question_text, correct_answer)
                VALUES (%s, 'wine_regions', 'multiple_choice', '1',
                        'recall', %s, 'A')
                RETURNING id::text
                """,
                (qid_text, f"skip-test stub q {i}"),
            )
            out.append((cur.fetchone()["id"], qid_text))
    return out


def _create_batch(conn, name: str, items: list[tuple[str, str]]) -> str:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO review_batches (name, description, question_count)
            VALUES (%s, %s, %s)
            RETURNING id::text
            """,
            (name, "skip-test batch", len(items)),
        )
        batch_id = cur.fetchone()["id"]
        for pos, (qid, public_qid) in enumerate(items):
            cur.execute(
                """
                INSERT INTO review_batch_items (batch_id, question_id, public_qid, position)
                VALUES (%s::uuid, %s::uuid, %s, %s)
                """,
                (batch_id, qid, public_qid, pos),
            )
    return batch_id


def _cleanup(conn, batch_id: str, reviewer_ids: Iterable[str], question_ids: Iterable[str]):
    with conn.cursor() as cur:
        cur.execute("DELETE FROM review_batches WHERE id = %s::uuid", (batch_id,))
        rids = list(reviewer_ids)
        if rids:
            cur.execute("DELETE FROM human_reviewers WHERE id = ANY(%s::uuid[])", (rids,))
        qids = list(question_ids)
        if qids:
            cur.execute("DELETE FROM questions WHERE id = ANY(%s::uuid[])", (qids,))


@pytest.fixture
def scenario(db_conn):
    """Two questions, one batch, one reviewer — cleaned up at teardown."""
    questions = _seed_questions(db_conn, 2)
    batch_name = f"skip_test_{uuid.uuid4().hex[:8]}"
    batch_id = _create_batch(db_conn, batch_name, questions)
    email = f"skipper-{uuid.uuid4().hex[:8]}@test.local"
    with db_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO human_reviewers (email, name) VALUES (%s, %s) RETURNING id::text",
            (email, "Skipper"),
        )
        reviewer_id = cur.fetchone()["id"]
    try:
        yield {
            "conn": db_conn,
            "batch_name": batch_name,
            "batch_id": batch_id,
            "questions": questions,
            "q1": questions[0],
            "q2": questions[1],
            "reviewer_id": reviewer_id,
            "reviewer_email": email,
        }
    finally:
        _cleanup(db_conn, batch_id, [reviewer_id], [q[0] for q in questions])


def _login_as(client, reviewer_email: str):
    return client.post(
        "/login",
        data={"email": reviewer_email},
        headers=_basic_auth_headers(),
        follow_redirects=False,
    )


def test_skip_question_requires_basic_auth(client):
    resp = client.post("/skip-question", data={"batch_name": "x", "question_id": "y"})
    assert resp.status_code == 401


def test_skip_question_excludes_question_for_session(scenario, client):
    """After skipping q1, /api/next-question must return q2 (not q1)."""
    s = scenario
    resp = _login_as(client, s["reviewer_email"])
    assert resp.status_code in (302, 303), resp.data

    # Skip q1.
    resp = client.post(
        "/skip-question",
        data={"batch_name": s["batch_name"], "question_id": s["q1"][0]},
        headers=_basic_auth_headers(),
        follow_redirects=False,
    )
    assert resp.status_code in (302, 303), resp.data
    # 302s back to /review/<batch>.
    assert s["batch_name"] in resp.headers["Location"]

    # The session cookie now carries the skipped id.
    with client.session_transaction() as sess:
        assert s["q1"][0] in (sess.get("skipped_question_ids") or {}).get(
            s["batch_name"], []
        )

    # Next-question API must serve q2 instead of q1.
    resp = client.get(
        f"/api/next-question?batch={s['batch_name']}",
        headers=_basic_auth_headers(),
    )
    assert resp.status_code == 200, resp.data
    payload = resp.get_json()
    assert payload["question"]["id"] == s["q2"][0], (
        f"Skipped q1 but next-question returned {payload['question']['id']}"
    )


def test_skip_question_does_not_write_review_row(scenario, client):
    """Skipping must not insert anything into human_reviews."""
    s = scenario
    _login_as(client, s["reviewer_email"])
    resp = client.post(
        "/skip-question",
        data={"batch_name": s["batch_name"], "question_id": s["q1"][0]},
        headers=_basic_auth_headers(),
        follow_redirects=False,
    )
    assert resp.status_code in (302, 303), resp.data
    with s["conn"].cursor() as cur:
        cur.execute(
            "SELECT count(*) AS cnt FROM human_reviews WHERE batch_id = %s::uuid",
            (s["batch_id"],),
        )
        assert cur.fetchone()["cnt"] == 0, "skip wrote a human_reviews row"


def test_skip_question_rejects_missing_fields(scenario, client):
    """Empty batch_name or question_id -> 400."""
    s = scenario
    _login_as(client, s["reviewer_email"])
    resp = client.post(
        "/skip-question",
        data={"batch_name": "", "question_id": s["q1"][0]},
        headers=_basic_auth_headers(),
        follow_redirects=False,
    )
    assert resp.status_code == 400, resp.data
    resp = client.post(
        "/skip-question",
        data={"batch_name": s["batch_name"], "question_id": ""},
        headers=_basic_auth_headers(),
        follow_redirects=False,
    )
    assert resp.status_code == 400, resp.data
