"""IRR-aware assignment tests for /api/next-question.

Verifies that the SELECT in src.review_app.app._next_question_for prefers
the least-reviewed un-completed question for the calling reviewer:

  - With 3 questions and 2 reviewers:
    * After R1 reviews q1, R2 should be served a 0-review question
      (q2 OR q3), NOT q1 (which already has 1 review).
    * After R1 reviews q2 and R2 reviews q3, R2's next question must
      be q1 — even though it has 1 review and the others have 1+1.
      Since the algorithm picks least-reviewed-not-completed-by-me,
      q1 is the only un-completed-by-R2 item.

DB-integration tests; require PostgreSQL reachable via src.utils.db.get_pg
and migration 004 applied. Each test cleans up the rows it created.
"""

from __future__ import annotations

import os
import uuid
from typing import Iterable

import pytest

from src.review_app.app import create_app
from src.utils.db import get_pg


pytestmark = pytest.mark.integration


# --- helpers -----------------------------------------------------------------


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
    import base64

    creds = base64.b64encode(b"admin:test-pw").decode()
    return {"Authorization": f"Basic {creds}"}


def _seed_questions(conn, n: int) -> list[tuple[str, str]]:
    suffix = uuid.uuid4().hex[:8]
    out: list[tuple[str, str]] = []
    with conn.cursor() as cur:
        for i in range(n):
            qid_text = f"WB-ASSIGN-{suffix}-{i:03d}"
            cur.execute(
                """
                INSERT INTO questions
                    (question_id, domain, question_type, difficulty,
                     cognitive_dim, question_text, correct_answer)
                VALUES (%s, 'wine_regions', 'multiple_choice', '1',
                        'recall', %s, 'A')
                RETURNING id::text
                """,
                (qid_text, f"stub assignment q {i}"),
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
            (name, "assignment-test batch", len(items)),
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


def _create_reviewer(conn, label: str) -> tuple[str, str]:
    email = f"r-{label}-{uuid.uuid4().hex[:8]}@test.local"
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO human_reviewers (email, name)
            VALUES (%s, %s)
            RETURNING id::text
            """,
            (email, f"Reviewer {label}"),
        )
        rid = cur.fetchone()["id"]
    return rid, email


def _record_review(conn, batch_id: str, reviewer_id: str, question_id: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO human_reviews
                (batch_id, reviewer_id, question_id,
                 answer_correct, overall_verdict, is_complete)
            VALUES (%s::uuid, %s::uuid, %s::uuid,
                    'pass'::rubric_score, 'approve'::overall_verdict, TRUE)
            """,
            (batch_id, reviewer_id, question_id),
        )


def _cleanup(conn, batch_id: str, reviewer_ids: Iterable[str], question_ids: Iterable[str]):
    with conn.cursor() as cur:
        cur.execute("DELETE FROM human_reviews WHERE batch_id = %s::uuid", (batch_id,))
        cur.execute("DELETE FROM review_batch_items WHERE batch_id = %s::uuid", (batch_id,))
        cur.execute("DELETE FROM review_batches WHERE id = %s::uuid", (batch_id,))
        rids = list(reviewer_ids)
        if rids:
            cur.execute("DELETE FROM human_reviewers WHERE id = ANY(%s::uuid[])", (rids,))
        qids = list(question_ids)
        if qids:
            cur.execute("DELETE FROM questions WHERE id = ANY(%s::uuid[])", (qids,))


@pytest.fixture
def scenario(db_conn):
    """Three questions, one batch, two reviewers — cleaned up at teardown."""
    questions = _seed_questions(db_conn, 3)
    batch_name = f"assign_test_{uuid.uuid4().hex[:8]}"
    batch_id = _create_batch(db_conn, batch_name, questions)
    r1_id, r1_email = _create_reviewer(db_conn, "1")
    r2_id, r2_email = _create_reviewer(db_conn, "2")
    try:
        yield {
            "conn": db_conn,
            "batch_name": batch_name,
            "batch_id": batch_id,
            "questions": questions,                # [(uuid, public_qid), ...]
            "q1": questions[0],
            "q2": questions[1],
            "q3": questions[2],
            "r1": {"id": r1_id, "email": r1_email},
            "r2": {"id": r2_id, "email": r2_email},
        }
    finally:
        _cleanup(
            db_conn,
            batch_id,
            [r1_id, r2_id],
            [q[0] for q in questions],
        )


def _login_as(client, reviewer_email: str):
    """Log a reviewer into the test client by hitting POST /login."""
    return client.post(
        "/login",
        data={"email": reviewer_email},
        headers=_basic_auth_headers(),
        follow_redirects=False,
    )


def _next_question(client, batch_name: str):
    return client.get(
        f"/api/next-question?batch={batch_name}",
        headers=_basic_auth_headers(),
    )


# --- tests -------------------------------------------------------------------


def test_next_question_prefers_zero_review_items(scenario, client):
    """After R1 reviews q1, R2 must get a 0-review question (q2 or q3), not q1."""
    s = scenario
    _record_review(s["conn"], s["batch_id"], s["r1"]["id"], s["q1"][0])

    resp = _login_as(client, s["r2"]["email"])
    assert resp.status_code in (302, 303), resp.data

    resp = _next_question(client, s["batch_name"])
    assert resp.status_code == 200, resp.data
    payload = resp.get_json()
    assert "question" in payload, payload
    served_qid = payload["question"]["id"]
    served_revcount = payload["question"]["rev_count"]

    assert served_qid in {s["q2"][0], s["q3"][0]}, (
        f"R2 was served {served_qid}; expected q2 ({s['q2'][0]}) or q3 ({s['q3'][0]})"
    )
    assert served_revcount == 0, (
        f"served question rev_count={served_revcount}; expected 0 (zero-review item)"
    )


def test_next_question_falls_back_to_higher_review_count(scenario, client):
    """When the only un-completed item for R2 has rev_count=1, it must still be served."""
    s = scenario
    # R1 reviews q2; R2 reviews q3 (so each has 1 review by someone else).
    _record_review(s["conn"], s["batch_id"], s["r1"]["id"], s["q2"][0])
    _record_review(s["conn"], s["batch_id"], s["r2"]["id"], s["q3"][0])
    # R1 also reviews q1 so q1 has rev_count=1 from R1; R2 has not reviewed q1.
    _record_review(s["conn"], s["batch_id"], s["r1"]["id"], s["q1"][0])

    resp = _login_as(client, s["r2"]["email"])
    assert resp.status_code in (302, 303), resp.data

    resp = _next_question(client, s["batch_name"])
    assert resp.status_code == 200, resp.data
    payload = resp.get_json()
    assert "question" in payload, payload
    assert payload["question"]["id"] == s["q1"][0], (
        f"R2 was served {payload['question']['id']}; expected q1 ({s['q1'][0]})"
    )
    assert payload["question"]["rev_count"] == 1, (
        f"served question rev_count={payload['question']['rev_count']}; expected 1"
    )


def test_next_question_done_when_reviewer_finished(scenario, client):
    s = scenario
    # R2 reviews all three.
    for qid, _ in s["questions"]:
        _record_review(s["conn"], s["batch_id"], s["r2"]["id"], qid)

    resp = _login_as(client, s["r2"]["email"])
    assert resp.status_code in (302, 303), resp.data

    resp = _next_question(client, s["batch_name"])
    assert resp.status_code == 200, resp.data
    payload = resp.get_json()
    assert payload.get("done") is True, payload
