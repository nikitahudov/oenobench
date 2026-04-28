"""OenoBench — Content-hash cache for LLM verdicts (lever B1).

Audit pilot v8 burned ~16k LLM calls for 111 questions. A meaningful
fraction were repeats — gate calls on near-duplicate questions, verifier
calls on regenerated templates, paraphrase calls on identical stems. This
module caches those verdicts in Postgres keyed by SHA-256 of a canonical
JSON serialization of the input, so repeats skip the API call entirely.

Design:
- Single shared table `llm_decisions`. Three "kinds" today: `gate`,
  `verifier`, `paraphrase`. UNIQUE on (cache_key, kind, model_id,
  version_tag) so changing model or version invalidates automatically.
- Disabled by default. Set OENOBENCH_LLM_CACHE=1 to enable. Audit pilot
  v8 reproducibility is preserved when the env var is unset.
- Failures (parse errors, HTTP errors) are NEVER cached — only successful
  verdicts. Caching a transient failure would poison every later call
  with the same input.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
from typing import Any

import psycopg2
from loguru import logger

from src.utils.db import get_pg

# ─── Public env-var gate ─────────────────────────────────────────────────────

CACHE_ENABLED_ENV_VAR = "OENOBENCH_LLM_CACHE"


def is_enabled() -> bool:
    """Return True iff the cache is enabled via env var.

    Resolved per-call rather than at import time so test fixtures that
    monkeypatch the env var see the change immediately.
    """
    val = os.environ.get(CACHE_ENABLED_ENV_VAR, "").strip().lower()
    return val in {"1", "true", "yes", "on"}


# ─── DDL bootstrap ───────────────────────────────────────────────────────────
#
# Lazy: run once on first lookup/store. Idempotent (CREATE IF NOT EXISTS).
# Module-import-side-effect would force every consumer to have a Postgres
# connection just to import the module, breaking the unit tests that patch
# `get_pg`.

_DDL_LOCK = threading.Lock()
_DDL_INITIALISED = False

_DDL_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS llm_decisions (
        id           BIGSERIAL PRIMARY KEY,
        cache_key    TEXT NOT NULL,
        cache_kind   TEXT NOT NULL,
        model_id     TEXT NOT NULL,
        version_tag  TEXT NOT NULL,
        payload      JSONB NOT NULL,
        created_at   TIMESTAMPTZ DEFAULT now(),
        UNIQUE (cache_key, cache_kind, model_id, version_tag)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS llm_decisions_lookup_idx
        ON llm_decisions (cache_kind, cache_key, model_id, version_tag)
    """,
)


def _ensure_schema() -> None:
    """Create the `llm_decisions` table on first use.

    Safe to call concurrently — the lock guards the local "have we
    initialised" flag, the CREATE statements themselves are idempotent
    via IF NOT EXISTS.
    """
    global _DDL_INITIALISED
    if _DDL_INITIALISED:
        return
    with _DDL_LOCK:
        if _DDL_INITIALISED:
            return
        try:
            conn = get_pg()
            with conn.cursor() as cur:
                for stmt in _DDL_STATEMENTS:
                    cur.execute(stmt)
            conn.commit()
        except Exception as e:  # noqa: BLE001
            # Surface the failure but don't crash callers — cache misses
            # are always safe (the original LLM call still runs).
            logger.warning("LLM cache DDL bootstrap failed: {}", e)
            try:
                conn.rollback()  # type: ignore[name-defined]
            except Exception:
                pass
            return
        _DDL_INITIALISED = True


def _reset_schema_flag_for_tests() -> None:
    """Test-only: forget the DDL-initialised flag so a monkeypatched
    `get_pg()` runs the bootstrap path again."""
    global _DDL_INITIALISED
    _DDL_INITIALISED = False


# ─── Public API ──────────────────────────────────────────────────────────────


def cache_key(parts: dict) -> str:
    """SHA-256 hex of a canonical-JSON serialization of `parts`.

    `sort_keys=True` makes the hash invariant to dict insertion order;
    `default=str` avoids the JSONEncoder choking on stray UUIDs / dates.
    """
    serialised = json.dumps(parts, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(serialised.encode("utf-8")).hexdigest()


def lookup(
    *, kind: str, key: str, model_id: str, version_tag: str
) -> dict | None:
    """Return cached payload dict, or None on miss / when cache disabled."""
    if not is_enabled():
        return None
    _ensure_schema()
    try:
        conn = get_pg()
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT payload
                FROM llm_decisions
                WHERE cache_kind = %s
                  AND cache_key = %s
                  AND model_id = %s
                  AND version_tag = %s
                LIMIT 1
                """,
                (kind, key, model_id, version_tag),
            )
            row = cur.fetchone()
        # Some psycopg2 cursor configurations return RealDictRow, others tuples.
        if row is None:
            return None
        if isinstance(row, dict):
            payload = row.get("payload")
        else:
            payload = row[0]
        if payload is None:
            return None
        # JSONB columns are returned as already-parsed Python objects by
        # psycopg2's default behaviour with RealDictCursor; if a deployment
        # returns a string (older drivers), parse it ourselves.
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except (json.JSONDecodeError, ValueError):
                return None
        if not isinstance(payload, dict):
            return None
        logger.info(
            "LLM cache HIT | kind={} | key={} | model={} | version={}",
            kind, key[:16], model_id, version_tag,
        )
        return payload
    except Exception as e:  # noqa: BLE001
        logger.warning("LLM cache lookup failed (treating as miss): {}", e)
        try:
            conn.rollback()  # type: ignore[name-defined]
        except Exception:
            pass
        return None


def store(
    *,
    kind: str,
    key: str,
    model_id: str,
    version_tag: str,
    payload: dict,
) -> None:
    """Upsert (ON CONFLICT DO NOTHING) the cache entry.

    No-op when the cache is disabled. Idempotent — concurrent threads
    racing on the same key are resolved by the UNIQUE constraint.
    """
    if not is_enabled():
        return
    _ensure_schema()
    try:
        conn = get_pg()
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO llm_decisions
                    (cache_key, cache_kind, model_id, version_tag, payload)
                VALUES (%s, %s, %s, %s, %s::jsonb)
                ON CONFLICT (cache_key, cache_kind, model_id, version_tag)
                DO NOTHING
                """,
                (key, kind, model_id, version_tag, json.dumps(payload, default=str)),
            )
        conn.commit()
        logger.debug(
            "LLM cache STORE | kind={} | key={} | model={} | version={}",
            kind, key[:16], model_id, version_tag,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("LLM cache store failed (continuing without cache): {}", e)
        try:
            conn.rollback()  # type: ignore[name-defined]
        except Exception:
            pass


def invalidate_kind(kind: str) -> int:
    """Delete all entries for a kind. Returns number of rows deleted.

    Used by tests to isolate fixtures and by manual ops scripts when a
    schema bug is found in a cached payload format. Always runs (does
    NOT short-circuit when cache disabled) so tests can clean up rows
    inserted under env-var-enabled context.
    """
    _ensure_schema()
    try:
        conn = get_pg()
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM llm_decisions WHERE cache_kind = %s",
                (kind,),
            )
            n = cur.rowcount
        conn.commit()
        return int(n)
    except Exception as e:  # noqa: BLE001
        logger.warning("LLM cache invalidate failed: {}", e)
        try:
            conn.rollback()  # type: ignore[name-defined]
        except Exception:
            pass
        return 0
