"""
OenoBench - Human Question Review web app.

Standalone Flask app for multi-expert review of release_v1 benchmark questions.
Two-layer auth:
  1. Outer HTTP Basic Auth (REVIEW_APP_USER / REVIEW_APP_PASSWORD).
  2. Inner reviewer session (cookie-signed, reviewer_id stored after register/login).

Run:
    python -m src.review_app.app
"""

from __future__ import annotations

import csv
import io
import os
import secrets
import time
from functools import wraps

from dotenv import load_dotenv
from flask import (
    Flask,
    Response,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from loguru import logger

load_dotenv()


def _expected_basic_auth() -> tuple[str, str]:
    """Read basic-auth credentials from env at request time.

    Reading on every request lets tests that set REVIEW_APP_USER /
    REVIEW_APP_PASSWORD before invoking the test client work even though
    the Flask app is constructed once at import time.
    """
    return (
        os.getenv("REVIEW_APP_USER", "admin"),
        os.getenv("REVIEW_APP_PASSWORD", "changeme"),
    )


REVIEW_APP_PORT = int(os.getenv("REVIEW_APP_PORT", "5556"))

# 8 rubric column names (v2; was 10). Display + submission order.
#
# Phase 4 review-app v2 collapses two pairs:
#   * difficulty_match + cognitive_match  -> labels_correct
#   * wine_category_leak                  -> folded into distractors_plausible
#
# The legacy three columns (difficulty_match, cognitive_match,
# wine_category_leak) remain in the human_reviews table (migration 005 is
# strictly additive) so historical κ analysis still works. The v2 form
# simply does not write them.
RUBRIC_COLUMNS = (
    "answer_correct",
    "distractors_plausible",
    "not_ambiguous",
    "source_faithful",
    "needs_source",
    "no_vague_language",
    "labels_correct",
    "verbatim_copy",
)

# Legacy v1 columns kept on `human_reviews` but no longer written by the
# v2 review form. Reads in export_reviews.py still emit them so downstream
# κ analysis on legacy review rows continues to work.
LEGACY_RUBRIC_COLUMNS = (
    "difficulty_match",
    "cognitive_match",
    "wine_category_leak",
)

VALID_RUBRIC_VALUES = {"pass", "warn", "fail"}
VALID_VERDICTS = {"approve", "revise", "reject"}


def _resolve_secret_key() -> str:
    raw = os.getenv("REVIEW_APP_SECRET")
    if raw:
        return raw
    generated = secrets.token_hex(32)
    logger.warning(
        "REVIEW_APP_SECRET not set; generated an ephemeral key. "
        "Sessions will not survive a restart. Set REVIEW_APP_SECRET in .env "
        "for persistent sessions."
    )
    return generated


# ---------------------------------------------------------------------------


def create_app() -> Flask:
    """Application factory (used by tests + the __main__ entry point)."""

    app = Flask(
        __name__,
        template_folder=os.path.join(os.path.dirname(__file__), "templates"),
        static_folder=os.path.join(os.path.dirname(__file__), "static"),
    )
    app.secret_key = _resolve_secret_key()

    # --- Auth helpers ------------------------------------------------------

    def require_basic_auth(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            auth = request.authorization
            user, password = _expected_basic_auth()
            if (
                not auth
                or auth.username != user
                or auth.password != password
            ):
                return Response(
                    "Authentication required.",
                    401,
                    {"WWW-Authenticate": 'Basic realm="OenoBench Review"'},
                )
            return f(*args, **kwargs)

        return decorated

    def require_reviewer(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if not session.get("reviewer_id"):
                if request.path.startswith("/api/"):
                    return jsonify({"error": "not_logged_in"}), 401
                return redirect(url_for("login"))
            return f(*args, **kwargs)

        return decorated

    # --- DB helpers --------------------------------------------------------

    def _reset_pg():
        from src.utils.db import _pg_local

        try:
            if getattr(_pg_local, "conn", None) is not None:
                try:
                    _pg_local.conn.close()
                except Exception:
                    pass
            _pg_local.conn = None
        except Exception:
            pass

    def _pg_query(sql, params=None):
        from src.utils.db import get_pg

        try:
            conn = get_pg()
            cur = conn.cursor()
            cur.execute(sql, params)
            return cur.fetchall()
        except Exception:
            _reset_pg()
            conn = get_pg()
            cur = conn.cursor()
            cur.execute(sql, params)
            return cur.fetchall()

    def _pg_execute(sql, params=None, fetch=False):
        """Execute a write statement; returns fetched row(s) when fetch=True."""
        from src.utils.db import get_pg

        try:
            conn = get_pg()
            cur = conn.cursor()
            cur.execute(sql, params)
            result = cur.fetchall() if fetch else None
            conn.commit()
            return result
        except Exception:
            try:
                conn = get_pg()
                conn.rollback()
            except Exception:
                pass
            _reset_pg()
            conn = get_pg()
            cur = conn.cursor()
            cur.execute(sql, params)
            result = cur.fetchall() if fetch else None
            conn.commit()
            return result

    # --- Template-context helpers -----------------------------------------

    def _current_reviewer_dict():
        rid = session.get("reviewer_id")
        if not rid:
            return None
        rows = _pg_query(
            "SELECT id::text AS id, email, name FROM human_reviewers WHERE id = %s::uuid",
            (rid,),
        )
        return dict(rows[0]) if rows else None

    def _active_batches_for(reviewer_id: str | None):
        rows = _pg_query(
            """
            SELECT
                rb.id::text       AS id,
                rb.name,
                rb.description,
                rb.question_count AS total,
                COALESCE(mine.cnt, 0) AS mine
            FROM review_batches rb
            LEFT JOIN (
                SELECT batch_id, count(*) AS cnt
                FROM human_reviews
                WHERE reviewer_id = %s::uuid AND is_complete
                GROUP BY batch_id
            ) mine ON mine.batch_id = rb.id
            WHERE rb.is_active
            ORDER BY rb.created_at DESC
            """,
            (reviewer_id or "00000000-0000-0000-0000-000000000000",),
        )
        out = []
        for r in rows:
            total = r["total"] or 0
            mine = r["mine"] or 0
            out.append({
                "id": r["id"],
                "name": r["name"],
                "description": r["description"],
                "total": total,
                "mine": mine,
                "pct": round((mine / total) * 100) if total else 0,
            })
        return out

    @app.context_processor
    def _inject_globals():
        reviewer = _current_reviewer_dict()
        batches = _active_batches_for(reviewer["id"]) if reviewer else []
        return {
            "reviewer": reviewer,
            "active_batches": batches,
        }

    def _reviewer_stats(reviewer_id: str) -> dict:
        rows = _pg_query(
            """
            SELECT
                count(*)                              AS total_reviews,
                COALESCE(round(avg(time_spent_seconds))::int, 0) AS avg_seconds,
                count(DISTINCT batch_id)              AS batches_touched
            FROM human_reviews
            WHERE reviewer_id = %s::uuid AND is_complete
            """,
            (reviewer_id,),
        )
        r = rows[0] if rows else {}
        return {
            "total_reviews": r.get("total_reviews", 0) or 0,
            "avg_seconds": r.get("avg_seconds", 0) or 0,
            "batches_touched": r.get("batches_touched", 0) or 0,
        }

    # --- Routes: auth ------------------------------------------------------

    @app.route("/", methods=["GET", "POST"])
    @app.route("/login", methods=["GET", "POST"])
    @require_basic_auth
    def login():
        if request.method == "GET":
            return render_template("login.html")
        email = (request.form.get("email") or "").strip().lower()
        if not email:
            return render_template("login.html", error="Email required."), 400
        rows = _pg_query(
            "SELECT id::text AS id, name FROM human_reviewers WHERE email = %s",
            (email,),
        )
        if not rows:
            return redirect(url_for("register", email=email))
        session["reviewer_id"] = rows[0]["id"]
        session["reviewer_name"] = rows[0]["name"]
        _pg_execute(
            "UPDATE human_reviewers SET last_active_at = now() WHERE id = %s::uuid",
            (rows[0]["id"],),
        )
        return redirect(url_for("dashboard"))

    @app.route("/register", methods=["GET", "POST"])
    @require_basic_auth
    def register():
        if request.method == "GET":
            return render_template(
                "register.html",
                form={"email": request.args.get("email", "")},
            )
        email = (request.form.get("email") or "").strip().lower()
        name = (request.form.get("name") or "").strip()
        credentials = (request.form.get("credentials") or "").strip() or None
        domains_raw = request.form.getlist("expertise_domains")
        if not email or not name:
            return (
                render_template(
                    "register.html",
                    form={
                        "email": email,
                        "name": name,
                        "credentials": credentials,
                        "expertise_domains": domains_raw,
                    },
                    error="Email and name are required.",
                ),
                400,
            )
        rows = _pg_execute(
            """
            INSERT INTO human_reviewers (email, name, credentials, expertise_domains)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (email) DO UPDATE
                SET name = EXCLUDED.name,
                    credentials = COALESCE(EXCLUDED.credentials, human_reviewers.credentials),
                    expertise_domains = CASE
                        WHEN COALESCE(array_length(EXCLUDED.expertise_domains, 1), 0) > 0
                            THEN EXCLUDED.expertise_domains
                            ELSE human_reviewers.expertise_domains
                    END,
                    last_active_at = now()
            RETURNING id::text AS id, name
            """,
            (email, name, credentials, domains_raw),
            fetch=True,
        )
        row = rows[0]
        session["reviewer_id"] = row["id"]
        session["reviewer_name"] = row["name"]
        return redirect(url_for("dashboard"))

    @app.route("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))

    # --- Routes: pages -----------------------------------------------------

    @app.route("/dashboard")
    @require_basic_auth
    @require_reviewer
    def dashboard():
        reviewer_id = session["reviewer_id"]
        batches = _active_batches_for(reviewer_id)
        stats = _reviewer_stats(reviewer_id)
        return render_template(
            "dashboard.html",
            batches=batches,
            stats=stats,
        )

    def _session_skipped_ids(batch_name: str) -> tuple[str, ...]:
        """Return the per-session skipped question_ids for this batch.

        Stored under session["skipped_question_ids"][batch_name]. Returned
        as a tuple so it can be passed straight to _next_question_for.
        """
        skipped = session.get("skipped_question_ids") or {}
        ids = skipped.get(batch_name) or []
        return tuple(ids)

    @app.route("/review/<batch>")
    @require_basic_auth
    @require_reviewer
    def review_batch(batch):
        batch_rows = _pg_query(
            """
            SELECT id::text AS id, name, question_count
            FROM review_batches
            WHERE name = %s
            """,
            (batch,),
        )
        if not batch_rows:
            return Response(f"Batch '{batch}' not found.", 404)
        batch_row = batch_rows[0]

        question_payload = _next_question_for(
            batch_row["id"],
            session["reviewer_id"],
            exclude_ids=_session_skipped_ids(batch_row["name"]),
        )
        if question_payload is None:
            return redirect(url_for("complete", batch=batch))

        progress = _progress_for(batch_row["id"], session["reviewer_id"])
        return render_template(
            "review.html",
            batch={
                "id": batch_row["id"],
                "name": batch_row["name"],
            },
            question=question_payload,
            progress=progress,
            render_ts=int(time.time() * 1000),
        )

    @app.route("/complete/<batch>")
    @require_basic_auth
    @require_reviewer
    def complete(batch):
        reviewer_id = session["reviewer_id"]
        batch_rows = _pg_query(
            """
            SELECT id::text AS id, name, question_count
            FROM review_batches
            WHERE name = %s
            """,
            (batch,),
        )
        if not batch_rows:
            return Response(f"Batch '{batch}' not found.", 404)
        b = batch_rows[0]
        rows = _pg_query(
            """
            SELECT
                count(*) FILTER (WHERE batch_id = %s::uuid)        AS batch_reviews,
                count(*)                                            AS total_reviews,
                COALESCE(round(avg(time_spent_seconds) FILTER (WHERE batch_id = %s::uuid))::int, 0) AS avg_seconds
            FROM human_reviews
            WHERE reviewer_id = %s::uuid AND is_complete
            """,
            (b["id"], b["id"], reviewer_id),
        )
        s = rows[0] if rows else {}
        stats = {
            "batch_reviews": s.get("batch_reviews", 0) or 0,
            "total_reviews": s.get("total_reviews", 0) or 0,
            "avg_seconds": s.get("avg_seconds", 0) or 0,
        }
        return render_template("complete.html", batch=b, stats=stats)

    @app.route("/instructions")
    @require_basic_auth
    def instructions():
        candidates = [
            os.path.join(os.path.dirname(__file__), "..", "..", "docs", "HUMAN_REVIEW_GUIDE.md"),
            os.path.join(os.path.dirname(__file__), "..", "..", "docs", "GOLD_REVIEW_GUIDE_V5.md"),
        ]
        guide_path = next((p for p in candidates if os.path.exists(p)), None)
        if not guide_path:
            return Response("Review guide not found.", 404)
        with open(guide_path, "r", encoding="utf-8") as fh:
            text = fh.read()
        try:
            import markdown as md  # type: ignore[import-not-found]

            html_body = md.markdown(text, extensions=["tables", "fenced_code"])
        except Exception:
            html_body = f"<pre>{text}</pre>"
        try:
            return render_template("instructions.html", html_body=html_body)
        except Exception:
            return Response(
                f"<!doctype html><html><body>{html_body}</body></html>",
                200,
                {"Content-Type": "text/html; charset=utf-8"},
            )

    # --- Internal helpers shared by HTML + API routes ---------------------

    def _next_question_for(
        batch_id: str,
        reviewer_id: str,
        exclude_ids: tuple[str, ...] = (),
    ) -> dict | None:
        # `exclude_ids` is the per-session skip list (see /skip-question).
        # Using a NULL-safe `!= ALL` against an empty array would still match
        # every row, so we always cast through the array form.
        exclude_list = list(exclude_ids) if exclude_ids else []
        rows = _pg_query(
            """
            WITH counts AS (
                SELECT
                    bi.question_id,
                    COUNT(hr.id) FILTER (WHERE hr.is_complete) AS rev_count
                FROM review_batch_items bi
                LEFT JOIN human_reviews hr
                    ON hr.question_id = bi.question_id
                   AND hr.batch_id    = bi.batch_id
                WHERE bi.batch_id = %s::uuid
                GROUP BY bi.question_id
            ),
            mine AS (
                SELECT question_id
                FROM human_reviews
                WHERE batch_id = %s::uuid
                  AND reviewer_id = %s::uuid
                  AND is_complete
            )
            SELECT
                bi.question_id::text AS question_id,
                bi.public_qid,
                bi.position,
                c.rev_count
            FROM review_batch_items bi
            JOIN counts c USING (question_id)
            WHERE bi.batch_id = %s::uuid
              AND bi.question_id NOT IN (SELECT question_id FROM mine)
              AND bi.question_id != ALL(%s::uuid[])
            ORDER BY c.rev_count ASC, bi.position ASC
            LIMIT 1
            """,
            (batch_id, batch_id, reviewer_id, batch_id, exclude_list),
        )
        if not rows:
            return None
        row = rows[0]
        question_id = row["question_id"]

        q_rows = _pg_query(
            """
            SELECT
                id::text                  AS id,
                question_id               AS public_qid,
                domain::text              AS domain,
                subdomain,
                question_type::text       AS question_type,
                difficulty::text          AS difficulty,
                cognitive_dim::text       AS cognitive_dim,
                question_text,
                options,
                correct_answer,
                correct_answer_text,
                explanation,
                tags
            FROM questions
            WHERE id = %s::uuid
            """,
            (question_id,),
        )
        if not q_rows:
            return None
        q = q_rows[0]

        fact_rows = _pg_query(
            """
            SELECT string_agg(
                       '[' || ord || '] ' || fact_text,
                       E'\n---\n'
                       ORDER BY ord
                   ) AS source_facts
            FROM (
                SELECT row_number() OVER () AS ord, f.fact_text
                FROM question_facts qf
                JOIN facts f ON f.id = qf.fact_id
                WHERE qf.question_id = %s::uuid
            ) AS x
            """,
            (question_id,),
        )
        source_facts = fact_rows[0]["source_facts"] if fact_rows else None

        # Normalise options into a flat list of strings for template iteration
        # while keeping the raw structure available to API consumers.
        options_raw = q["options"]
        options_list: list[str] = []
        if isinstance(options_raw, list):
            for item in options_raw:
                if isinstance(item, dict):
                    options_list.append(item.get("text") or "")
                else:
                    options_list.append(str(item))

        return {
            "id": q["id"],
            "public_qid": q["public_qid"],
            "domain": q["domain"],
            "subdomain": q["subdomain"],
            "question_type": q["question_type"],
            "difficulty": q["difficulty"],
            "cognitive_dim": q["cognitive_dim"],
            "strategy": None,
            "question_text": q["question_text"],
            "options": options_list,
            "options_raw": options_raw,
            "correct_answer": q["correct_answer"],
            "correct_answer_text": q["correct_answer_text"],
            "explanation": q["explanation"],
            "tags": q["tags"],
            "source_facts": source_facts,
            "position": row["position"],
            "rev_count": row["rev_count"],
        }

    def _progress_for(batch_id: str, reviewer_id: str) -> dict:
        b_rows = _pg_query(
            "SELECT question_count FROM review_batches WHERE id = %s::uuid",
            (batch_id,),
        )
        total = b_rows[0]["question_count"] if b_rows else 0
        m_rows = _pg_query(
            """
            SELECT count(*) AS cnt
            FROM human_reviews
            WHERE batch_id = %s::uuid
              AND reviewer_id = %s::uuid
              AND is_complete
            """,
            (batch_id, reviewer_id),
        )
        mine = m_rows[0]["cnt"] if m_rows else 0
        return {"total": total, "mine": mine}

    def _upsert_review(batch_id: str, reviewer_id: str, payload: dict) -> str:
        question_id = (payload.get("question_id") or "").strip()
        if not question_id:
            raise ValueError("question_id required")

        rubric_values: list[str | None] = []
        for col in RUBRIC_COLUMNS:
            val = payload.get(col)
            if val in (None, ""):
                rubric_values.append(None)
                continue
            if val not in VALID_RUBRIC_VALUES:
                raise ValueError(f"invalid value for {col}: {val}")
            rubric_values.append(val)

        verdict = payload.get("overall_verdict")
        if verdict in ("", None):
            verdict = None
        elif verdict not in VALID_VERDICTS:
            raise ValueError(f"invalid overall_verdict: {verdict}")

        suggested_answer = payload.get("suggested_answer")
        if isinstance(suggested_answer, str):
            suggested_answer = suggested_answer.strip().upper() or None
            if suggested_answer and suggested_answer not in {"A", "B", "C", "D"}:
                raise ValueError("suggested_answer must be A-D")

        suggested_difficulty = payload.get("suggested_difficulty")
        if suggested_difficulty in ("", None):
            suggested_difficulty = None
        else:
            try:
                suggested_difficulty = int(suggested_difficulty)
            except (TypeError, ValueError):
                raise ValueError("suggested_difficulty must be 1-4")
            if suggested_difficulty < 1 or suggested_difficulty > 4:
                raise ValueError("suggested_difficulty must be 1-4")

        notes = payload.get("notes")
        if isinstance(notes, str):
            notes = notes.strip() or None

        time_spent = payload.get("time_spent_seconds")
        if time_spent in ("", None):
            time_spent = None
        else:
            try:
                time_spent = int(time_spent)
            except (TypeError, ValueError):
                time_spent = None

        rubric_assigns = ", ".join(
            f"{col} = EXCLUDED.{col}" for col in RUBRIC_COLUMNS
        )
        sql = f"""
            INSERT INTO human_reviews (
                batch_id, reviewer_id, question_id,
                {", ".join(RUBRIC_COLUMNS)},
                overall_verdict, suggested_answer, suggested_difficulty,
                notes, time_spent_seconds, is_complete, updated_at
            )
            VALUES (
                %s::uuid, %s::uuid, %s::uuid,
                {", ".join(["%s::rubric_score"] * len(RUBRIC_COLUMNS))},
                %s::overall_verdict, %s, %s,
                %s, %s, TRUE, now()
            )
            ON CONFLICT (batch_id, reviewer_id, question_id) DO UPDATE SET
                {rubric_assigns},
                overall_verdict = EXCLUDED.overall_verdict,
                suggested_answer = EXCLUDED.suggested_answer,
                suggested_difficulty = EXCLUDED.suggested_difficulty,
                notes = EXCLUDED.notes,
                time_spent_seconds = EXCLUDED.time_spent_seconds,
                is_complete = TRUE,
                updated_at = now()
            RETURNING id::text AS id
        """
        params = [
            batch_id, reviewer_id, question_id,
            *rubric_values,
            verdict, suggested_answer, suggested_difficulty,
            notes, time_spent,
        ]
        rows = _pg_execute(sql, params, fetch=True)
        return rows[0]["id"]

    # --- Routes: API -------------------------------------------------------

    @app.route("/api/next-question")
    @require_basic_auth
    @require_reviewer
    def api_next_question():
        reviewer_id = session["reviewer_id"]
        batch_name = request.args.get("batch")
        if not batch_name:
            return jsonify({"error": "batch parameter required"}), 400
        rows = _pg_query(
            "SELECT id::text AS id FROM review_batches WHERE name = %s",
            (batch_name,),
        )
        if not rows:
            return jsonify({"error": "batch_not_found"}), 404
        batch_id = rows[0]["id"]
        q = _next_question_for(
            batch_id,
            reviewer_id,
            exclude_ids=_session_skipped_ids(batch_name),
        )
        if q is None:
            return jsonify({"done": True, "batch_id": batch_id})
        return jsonify({
            "batch_id": batch_id,
            "batch_name": batch_name,
            "question": q,
        })

    @app.route("/api/review", methods=["POST"])
    @require_basic_auth
    @require_reviewer
    def api_review():
        reviewer_id = session["reviewer_id"]
        data = request.get_json(silent=True) or {}
        batch_name = (data.get("batch_name") or "").strip()
        if not batch_name:
            return jsonify({"error": "batch_name required"}), 400
        rows = _pg_query(
            "SELECT id::text AS id FROM review_batches WHERE name = %s",
            (batch_name,),
        )
        if not rows:
            return jsonify({"error": "batch_not_found"}), 404
        batch_id = rows[0]["id"]
        try:
            review_id = _upsert_review(batch_id, reviewer_id, data)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify({"ok": True, "review_id": review_id})

    @app.route("/submit-review", methods=["POST"])
    @require_basic_auth
    @require_reviewer
    def submit_review():
        """Form-encoded submit endpoint used by the server-rendered review page."""
        reviewer_id = session["reviewer_id"]
        batch_id = (request.form.get("batch_id") or "").strip()
        if not batch_id:
            return Response("batch_id required", 400)
        b_rows = _pg_query(
            "SELECT id::text AS id, name FROM review_batches WHERE id = %s::uuid",
            (batch_id,),
        )
        if not b_rows:
            return Response("batch_not_found", 404)
        batch = b_rows[0]
        payload = {col: request.form.get(col) for col in RUBRIC_COLUMNS}
        payload.update({
            "question_id":          request.form.get("question_id"),
            "overall_verdict":      request.form.get("overall_verdict"),
            "suggested_answer":     request.form.get("suggested_answer"),
            "suggested_difficulty": request.form.get("suggested_difficulty"),
            "notes":                request.form.get("notes"),
            "time_spent_seconds":   request.form.get("time_spent_seconds"),
        })
        try:
            _upsert_review(batch_id, reviewer_id, payload)
        except ValueError as exc:
            flash(str(exc), "error")
            return redirect(url_for("review_batch", batch=batch["name"]))
        flash("Review saved.", "success")
        return redirect(url_for("review_batch", batch=batch["name"]))

    @app.route("/skip-question", methods=["POST"])
    @require_basic_auth
    @require_reviewer
    def skip_question():
        """Skip a question for the rest of the current session.

        Appends `question_id` to a per-batch list in `session["skipped_question_ids"]`.
        The skip is in-session only — the question still goes to other reviewers
        and to this reviewer in a future session.
        """
        batch_name = (request.form.get("batch_name") or "").strip()
        question_id = (request.form.get("question_id") or "").strip()
        if not batch_name or not question_id:
            return Response("batch_name and question_id required", 400)

        skipped = dict(session.get("skipped_question_ids") or {})
        ids = list(skipped.get(batch_name) or [])
        if question_id not in ids:
            ids.append(question_id)
        # Cap at 200 to keep the cookie compact.
        if len(ids) > 200:
            ids = ids[-200:]
        skipped[batch_name] = ids
        session["skipped_question_ids"] = skipped
        return redirect(url_for("review_batch", batch=batch_name))

    @app.route("/api/progress")
    @require_basic_auth
    @require_reviewer
    def api_progress():
        reviewer_id = session["reviewer_id"]
        batch_name = request.args.get("batch")
        if not batch_name:
            return jsonify({"error": "batch parameter required"}), 400
        batch_rows = _pg_query(
            "SELECT id::text AS id, question_count FROM review_batches WHERE name = %s",
            (batch_name,),
        )
        if not batch_rows:
            return jsonify({"error": "batch_not_found"}), 404
        batch_id = batch_rows[0]["id"]
        total = batch_rows[0]["question_count"]
        mine_rows = _pg_query(
            """
            SELECT count(*) AS cnt
            FROM human_reviews
            WHERE batch_id = %s::uuid
              AND reviewer_id = %s::uuid
              AND is_complete
            """,
            (batch_id, reviewer_id),
        )
        mine = mine_rows[0]["cnt"]
        coverage_rows = _pg_query(
            """
            WITH counts AS (
                SELECT
                    bi.question_id,
                    COUNT(hr.id) FILTER (WHERE hr.is_complete) AS rev_count
                FROM review_batch_items bi
                LEFT JOIN human_reviews hr
                    ON hr.question_id = bi.question_id
                   AND hr.batch_id    = bi.batch_id
                WHERE bi.batch_id = %s::uuid
                GROUP BY bi.question_id
            )
            SELECT
                SUM(CASE WHEN rev_count = 0 THEN 1 ELSE 0 END) AS zero_review,
                SUM(CASE WHEN rev_count = 1 THEN 1 ELSE 0 END) AS one_review,
                SUM(CASE WHEN rev_count >= 2 THEN 1 ELSE 0 END) AS two_plus
            FROM counts
            """,
            (batch_id,),
        )
        cov = coverage_rows[0] if coverage_rows else {}
        return jsonify({
            "batch_id": batch_id,
            "batch_name": batch_name,
            "total": total,
            "mine": mine,
            "batch_overall": {
                "0_review": int(cov.get("zero_review") or 0),
                "1_review": int(cov.get("one_review") or 0),
                "2plus":    int(cov.get("two_plus") or 0),
            },
        })

    # --- Admin -------------------------------------------------------------

    @app.route("/admin/batches")
    @require_basic_auth
    def admin_batches():
        batches = _pg_query(
            """
            SELECT
                rb.id::text       AS id,
                rb.name,
                rb.description,
                rb.question_count,
                rb.is_active,
                rb.created_at,
                rb.created_by,
                COALESCE(stats.review_count, 0)        AS review_count,
                COALESCE(stats.unique_reviewers, 0)    AS unique_reviewers
            FROM review_batches rb
            LEFT JOIN (
                SELECT
                    batch_id,
                    count(*) FILTER (WHERE is_complete) AS review_count,
                    count(DISTINCT reviewer_id) FILTER (WHERE is_complete) AS unique_reviewers
                FROM human_reviews
                GROUP BY batch_id
            ) stats ON stats.batch_id = rb.id
            ORDER BY rb.created_at DESC
            """,
        )
        reviewers = _pg_query(
            """
            SELECT
                r.id::text         AS id,
                r.email,
                r.name,
                r.credentials,
                r.expertise_domains,
                r.created_at,
                r.last_active_at,
                COALESCE(c.cnt, 0) AS completed_reviews
            FROM human_reviewers r
            LEFT JOIN (
                SELECT reviewer_id, count(*) AS cnt
                FROM human_reviews
                WHERE is_complete
                GROUP BY reviewer_id
            ) c ON c.reviewer_id = r.id
            ORDER BY r.last_active_at DESC NULLS LAST
            """,
        )
        try:
            return render_template(
                "admin.html",
                batches=batches,
                reviewers=reviewers,
            )
        except Exception:
            # admin template may be added by track D/C — return JSON fallback
            return jsonify({
                "batches": [dict(b) for b in batches],
                "reviewers": [dict(r) for r in reviewers],
            })

    @app.route("/admin/cleanup-test-batches")
    @require_basic_auth
    def admin_cleanup_test_batches():
        """Delete leftover `test_batch_*` batches (from pre-conftest pytest runs).

        CASCADE on review_batch_items + human_reviews makes a single DELETE
        on review_batches sufficient. Returns the deleted batch UUIDs.
        """
        rows = _pg_execute(
            """
            DELETE FROM review_batches
            WHERE name LIKE %s
            RETURNING id::text AS id
            """,
            ("test_batch_%",),
            fetch=True,
        ) or []
        deleted_ids = [r["id"] for r in rows]
        return jsonify({"deleted_batch_ids": deleted_ids})

    @app.route("/admin/export.csv")
    @require_basic_auth
    def admin_export_csv():
        batch_name = request.args.get("batch")
        if not batch_name:
            return Response("batch parameter required", 400)
        rows = _pg_query(
            """
            SELECT
                rb.name                   AS batch_name,
                rev.email                 AS reviewer_email,
                rev.name                  AS reviewer_name,
                bi.public_qid             AS public_qid,
                hr.question_id::text      AS question_id,
                hr.answer_correct::text,
                hr.distractors_plausible::text,
                hr.not_ambiguous::text,
                hr.source_faithful::text,
                hr.needs_source::text,
                hr.no_vague_language::text,
                hr.difficulty_match::text,
                hr.cognitive_match::text,
                hr.verbatim_copy::text,
                hr.wine_category_leak::text,
                hr.labels_correct::text,
                hr.overall_verdict::text,
                hr.suggested_answer,
                hr.suggested_difficulty,
                hr.notes,
                hr.time_spent_seconds,
                hr.is_complete,
                hr.created_at,
                hr.updated_at
            FROM human_reviews hr
            JOIN review_batches rb   ON rb.id = hr.batch_id
            JOIN human_reviewers rev ON rev.id = hr.reviewer_id
            JOIN review_batch_items bi
                ON bi.batch_id = hr.batch_id AND bi.question_id = hr.question_id
            WHERE rb.name = %s
            ORDER BY rev.email, bi.position
            """,
            (batch_name,),
        )
        if not rows:
            return Response("no rows", 404)
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        for r in rows:
            writer.writerow({k: ("" if v is None else v) for k, v in r.items()})
        return Response(
            buf.getvalue(),
            mimetype="text/csv",
            headers={
                "Content-Disposition": f'attachment; filename="{batch_name}_reviews.csv"',
            },
        )

    return app


# Module-level app for `python -m src.review_app.app` / WSGI imports.
app = create_app()


if __name__ == "__main__":
    logger.info(f"Starting review app on port {REVIEW_APP_PORT}")
    app.run(host="0.0.0.0", port=REVIEW_APP_PORT)
