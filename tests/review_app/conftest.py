"""Test fixtures for the review-app suite.

The pre-v2 review-app tests created `test_batch_*` rows that were never
cleaned up (migration 006 deletes the legacy stragglers). New tests in
this package should use the `created_batch_ids` fixture below to get
automatic teardown of any review_batches rows they create.

The fixture is opt-in (tests pass it as a parameter) so it doesn't fight
with existing per-fixture cleanup paths in `test_review_routes.py` /
`test_assignment.py`.
"""

from __future__ import annotations

from typing import Iterator

import pytest

from src.utils.db import get_pg


@pytest.fixture
def created_batch_ids() -> Iterator[list[str]]:
    """Yield a list a test can append created batch UUIDs to.

    On teardown, every appended id is DELETEd from `review_batches`.
    CASCADE on review_batch_items + human_reviews makes the single
    DELETE on review_batches sufficient.

    Skips the cleanup silently if PostgreSQL is unreachable so the
    fixture can be used in unit-style tests that never touched the DB.
    """
    ids: list[str] = []
    try:
        yield ids
    finally:
        if not ids:
            return
        try:
            conn = get_pg()
        except Exception:
            return
        try:
            conn.rollback()
        except Exception:
            pass
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM review_batches WHERE id = ANY(%s::uuid[])",
                    (ids,),
                )
            conn.commit()
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
