"""Route-level tests for src.review_app.app.

Covers the basic-auth gate, the register → next-question → submit happy
path, and upsert semantics on POST /api/review (a second submit for the
same (batch, reviewer, question) does NOT create a duplicate row).

DB-integration tests; they require PostgreSQL reachable via
src.utils.db.get_pg and migration 004 applied.
"""

from __future__ import annotations

import base64
import os
import uuid

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


def _seed_question(conn) -> tuple[str, str]:
    suffix = uuid.uuid4().hex[:8]
    qid_text = f"WB-ROUTES-{suffix}"
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO questions
                (question_id, domain, question_type, difficulty,
                 cognitive_dim, question_text, options, correct_answer)
            VALUES (%s, 'wine_regions', 'multiple_choice', '1',
                    'recall', %s,
                    '[{"id":"A","text":"Alpha"},{"id":"B","text":"Beta"},'
                    '{"id":"C","text":"Gamma"},{"id":"D","text":"Delta"}]'::jsonb,
                    'A')
            RETURNING id::text
            """,
            (qid_text, "stub routes question"),
        )
        return cur.fetchone()["id"], qid_text


def _create_batch(conn, name: str, items: list[tuple[str, str]]) -> str:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO review_batches (name, description, question_count)
            VALUES (%s, %s, %s)
            RETURNING id::text
            """,
            (name, "routes-test batch", len(items)),
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


@pytest.fixture
def env(db_conn):
    """One question, one batch — cleaned up at teardown. No reviewer yet."""
    q_id, public_qid = _seed_question(db_conn)
    batch_name = f"routes_test_{uuid.uuid4().hex[:8]}"
    batch_id = _create_batch(db_conn, batch_name, [(q_id, public_qid)])
    created_emails: list[str] = []
    try:
        yield {
            "conn":       db_conn,
            "batch_name": batch_name,
            "batch_id":   batch_id,
            "question_id": q_id,
            "public_qid": public_qid,
            "created_emails": created_emails,
        }
    finally:
        with db_conn.cursor() as cur:
            cur.execute("DELETE FROM human_reviews WHERE batch_id = %s::uuid", (batch_id,))
            cur.execute("DELETE FROM review_batch_items WHERE batch_id = %s::uuid", (batch_id,))
            cur.execute("DELETE FROM review_batches WHERE id = %s::uuid", (batch_id,))
            cur.execute("DELETE FROM questions WHERE id = %s::uuid", (q_id,))
            if created_emails:
                cur.execute(
                    "DELETE FROM human_reviewers WHERE email = ANY(%s)",
                    (created_emails,),
                )


# --- tests -------------------------------------------------------------------


def test_root_requires_basic_auth(client):
    resp = client.get("/")
    assert resp.status_code == 401
    assert "WWW-Authenticate" in resp.headers
    assert resp.headers["WWW-Authenticate"].startswith("Basic")


def test_api_next_question_requires_basic_auth(client):
    resp = client.get("/api/next-question?batch=anything")
    assert resp.status_code == 401


def test_register_logs_in_and_redirects_to_dashboard(env, client):
    email = f"newreviewer-{uuid.uuid4().hex[:8]}@test.local"
    env["created_emails"].append(email)

    resp = client.post(
        "/register",
        data={
            "email": email,
            "name": "Test Reviewer",
            "credentials": "WSET 3",
            "expertise_domains": ["wine_regions", "grape_varieties"],
        },
        headers=_basic_auth_headers(),
        follow_redirects=False,
    )
    assert resp.status_code in (302, 303), resp.data
    assert "/dashboard" in resp.headers["Location"]

    # The session cookie should now contain reviewer_id.
    with client.session_transaction() as sess:
        assert sess.get("reviewer_id"), "reviewer_id missing from session after register"

    # Verify reviewer row exists.
    with env["conn"].cursor() as cur:
        cur.execute(
            "SELECT id, name FROM human_reviewers WHERE email = %s",
            (email,),
        )
        row = cur.fetchone()
        assert row is not None
        assert row["name"] == "Test Reviewer"


def test_happy_path_register_next_question_submit(env, client):
    email = f"happy-{uuid.uuid4().hex[:8]}@test.local"
    env["created_emails"].append(email)

    # Register (also logs in).
    resp = client.post(
        "/register",
        data={"email": email, "name": "Happy Reviewer"},
        headers=_basic_auth_headers(),
        follow_redirects=False,
    )
    assert resp.status_code in (302, 303), resp.data

    # Get next question.
    resp = client.get(
        f"/api/next-question?batch={env['batch_name']}",
        headers=_basic_auth_headers(),
    )
    assert resp.status_code == 200, resp.data
    payload = resp.get_json()
    assert "question" in payload
    assert payload["question"]["id"] == env["question_id"]
    assert payload["question"]["public_qid"] == env["public_qid"]

    # Submit a review.
    resp = client.post(
        "/api/review",
        json={
            "batch_name": env["batch_name"],
            "question_id": env["question_id"],
            "answer_correct": "pass",
            "distractors_plausible": "pass",
            "not_ambiguous": "pass",
            "source_faithful": "pass",
            "needs_source": "pass",
            "no_vague_language": "pass",
            "labels_correct": "pass",
            "verbatim_copy": "pass",
            "overall_verdict": "approve",
            "suggested_answer": "",
            "suggested_difficulty": "",
            "notes": "looks good",
            "time_spent_seconds": 42,
        },
        headers=_basic_auth_headers(),
    )
    assert resp.status_code == 200, resp.data
    body = resp.get_json()
    assert body["ok"] is True
    first_review_id = body["review_id"]

    # After submit, /api/next-question for this reviewer should report done.
    resp = client.get(
        f"/api/next-question?batch={env['batch_name']}",
        headers=_basic_auth_headers(),
    )
    assert resp.status_code == 200, resp.data
    payload = resp.get_json()
    assert payload.get("done") is True

    # Submit a second review with different content; must upsert (no dupe).
    resp = client.post(
        "/api/review",
        json={
            "batch_name": env["batch_name"],
            "question_id": env["question_id"],
            "answer_correct": "warn",
            "distractors_plausible": "fail",
            "overall_verdict": "revise",
            "notes": "second pass",
            "time_spent_seconds": 99,
        },
        headers=_basic_auth_headers(),
    )
    assert resp.status_code == 200, resp.data
    body = resp.get_json()
    assert body["ok"] is True
    second_review_id = body["review_id"]
    assert second_review_id == first_review_id, (
        "second submit returned a different review_id; UNIQUE upsert appears broken"
    )

    # DB-level: exactly one human_reviews row exists for this triple.
    with env["conn"].cursor() as cur:
        cur.execute(
            """
            SELECT count(*) AS cnt,
                   max(answer_correct::text) AS ac,
                   max(distractors_plausible::text) AS dp,
                   max(overall_verdict::text) AS verdict,
                   max(notes) AS notes,
                   max(time_spent_seconds) AS tss
            FROM human_reviews
            WHERE batch_id    = %s::uuid
              AND question_id = %s::uuid
            """,
            (env["batch_id"], env["question_id"]),
        )
        row = cur.fetchone()
    assert row["cnt"] == 1, f"expected exactly 1 row after two submits, got {row['cnt']}"
    assert row["ac"]      == "warn"
    assert row["dp"]      == "fail"
    assert row["verdict"] == "revise"
    assert row["notes"]   == "second pass"
    assert row["tss"]     == 99


def test_login_with_unknown_email_redirects_to_register(env, client):
    email = f"unknown-{uuid.uuid4().hex[:8]}@test.local"
    resp = client.post(
        "/login",
        data={"email": email},
        headers=_basic_auth_headers(),
        follow_redirects=False,
    )
    assert resp.status_code in (302, 303)
    assert "/register" in resp.headers["Location"]
    # The redirect query string should preserve the email.
    assert email in resp.headers["Location"]


def test_login_with_known_email_logs_in(env, client):
    # Pre-create reviewer.
    email = f"known-{uuid.uuid4().hex[:8]}@test.local"
    env["created_emails"].append(email)
    with env["conn"].cursor() as cur:
        cur.execute(
            "INSERT INTO human_reviewers (email, name) VALUES (%s, %s) RETURNING id::text",
            (email, "Known Reviewer"),
        )
        rid = cur.fetchone()["id"]

    resp = client.post(
        "/login",
        data={"email": email},
        headers=_basic_auth_headers(),
        follow_redirects=False,
    )
    assert resp.status_code in (302, 303), resp.data
    assert "/dashboard" in resp.headers["Location"]
    with client.session_transaction() as sess:
        assert sess.get("reviewer_id") == rid


def test_api_review_persists_labels_correct(env, client):
    """The v2 rubric column `labels_correct` round-trips through /api/review."""
    email = f"v2-labels-{uuid.uuid4().hex[:8]}@test.local"
    env["created_emails"].append(email)
    client.post(
        "/register",
        data={"email": email, "name": "Labels Reviewer"},
        headers=_basic_auth_headers(),
    )
    resp = client.post(
        "/api/review",
        json={
            "batch_name": env["batch_name"],
            "question_id": env["question_id"],
            "labels_correct": "warn",
            "overall_verdict": "revise",
        },
        headers=_basic_auth_headers(),
    )
    assert resp.status_code == 200, resp.data
    with env["conn"].cursor() as cur:
        cur.execute(
            """
            SELECT
                labels_correct::text     AS labels_correct,
                difficulty_match::text   AS difficulty_match,
                cognitive_match::text    AS cognitive_match,
                wine_category_leak::text AS wine_category_leak
            FROM human_reviews
            WHERE batch_id    = %s::uuid
              AND question_id = %s::uuid
            """,
            (env["batch_id"], env["question_id"]),
        )
        row = cur.fetchone()
    assert row["labels_correct"] == "warn"
    # Legacy columns must stay NULL on v2 review rows.
    assert row["difficulty_match"] is None
    assert row["cognitive_match"] is None
    assert row["wine_category_leak"] is None


def test_api_review_validates_rubric_values(env, client):
    email = f"validator-{uuid.uuid4().hex[:8]}@test.local"
    env["created_emails"].append(email)
    client.post(
        "/register",
        data={"email": email, "name": "Validator"},
        headers=_basic_auth_headers(),
    )
    resp = client.post(
        "/api/review",
        json={
            "batch_name": env["batch_name"],
            "question_id": env["question_id"],
            "answer_correct": "definitely-not-valid",
            "overall_verdict": "approve",
        },
        headers=_basic_auth_headers(),
    )
    assert resp.status_code == 400
    assert "answer_correct" in (resp.get_json() or {}).get("error", "")
