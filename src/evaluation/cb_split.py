"""OenoBench — Closed-book split scoring for evaluation runs.

Pairs accuracy on questions tagged `closed_book_solvable` (parametric wine
knowledge) against the rest of the corpus (contextual wine reasoning). The
gap exposes whether a model leans on memorised facts or on the supplied
context. See docs/PROCESS_LOG.md 2026-04-24 (Phase 2g.6) for policy.
"""

from __future__ import annotations

import sys

from src.utils.db import get_pg

CLOSED_BOOK_TAG = "closed_book_solvable"


def score_by_cb_split(eval_run_id: str) -> dict:
    """Compute closed-book-pass vs closed-book-fail accuracy for an evaluation run.

    Joins `evaluation_answers` to `questions` for the given run and groups by
    whether the question carries the `closed_book_solvable` tag. Returns a dict
    with paired metrics so a downstream report can render the gap as a measure
    of "wine world knowledge" vs "contextual wine reasoning."

    Args:
        eval_run_id: UUID of an `evaluation_runs` row.

    Returns:
        {
            "eval_run_id": str,
            "cb_pass": {"n": int, "n_correct": int, "accuracy": float | None},
            "cb_fail": {"n": int, "n_correct": int, "accuracy": float | None},
            "gap": float | None,           # cb_fail.accuracy - cb_pass.accuracy
                                            # (positive = better at world knowledge)
            "total": {"n": int, "n_correct": int, "accuracy": float | None},
        }
    """
    conn = get_pg()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
            ea.is_correct AS is_correct,
            (%s = ANY(q.tags)) AS cb_solvable
        FROM evaluation_answers ea
        JOIN questions q ON q.id = ea.question_id
        WHERE ea.run_id = %s
        """,
        (CLOSED_BOOK_TAG, eval_run_id),
    )
    rows = cur.fetchall()

    # cb_pass = the harder set (no tag → gate could not solve closed-book).
    # cb_fail = the world-knowledge set (gate solved it → relabeled with tag).
    cb_pass_n = cb_pass_correct = 0
    cb_fail_n = cb_fail_correct = 0

    for row in rows:
        is_correct = bool(row["is_correct"])
        if row["cb_solvable"]:
            cb_fail_n += 1
            if is_correct:
                cb_fail_correct += 1
        else:
            cb_pass_n += 1
            if is_correct:
                cb_pass_correct += 1

    cb_pass_acc = (cb_pass_correct / cb_pass_n) if cb_pass_n else None
    cb_fail_acc = (cb_fail_correct / cb_fail_n) if cb_fail_n else None

    if cb_pass_acc is not None and cb_fail_acc is not None:
        gap = cb_fail_acc - cb_pass_acc
    else:
        gap = None

    total_n = cb_pass_n + cb_fail_n
    total_correct = cb_pass_correct + cb_fail_correct
    total_acc = (total_correct / total_n) if total_n else None

    return {
        "eval_run_id": str(eval_run_id),
        "cb_pass": {
            "n": cb_pass_n,
            "n_correct": cb_pass_correct,
            "accuracy": cb_pass_acc,
        },
        "cb_fail": {
            "n": cb_fail_n,
            "n_correct": cb_fail_correct,
            "accuracy": cb_fail_acc,
        },
        "gap": gap,
        "total": {
            "n": total_n,
            "n_correct": total_correct,
            "accuracy": total_acc,
        },
    }


def _fmt_acc(acc: float | None) -> str:
    return f"{acc * 100:.2f}%" if acc is not None else "n/a"


def _print_report(result: dict) -> None:
    print(f"eval_run_id: {result['eval_run_id']}")
    print(
        f"  total:    n={result['total']['n']:>5}  "
        f"correct={result['total']['n_correct']:>5}  "
        f"acc={_fmt_acc(result['total']['accuracy'])}"
    )
    print(
        f"  cb_pass:  n={result['cb_pass']['n']:>5}  "
        f"correct={result['cb_pass']['n_correct']:>5}  "
        f"acc={_fmt_acc(result['cb_pass']['accuracy'])}  "
        "(contextual wine reasoning)"
    )
    print(
        f"  cb_fail:  n={result['cb_fail']['n']:>5}  "
        f"correct={result['cb_fail']['n_correct']:>5}  "
        f"acc={_fmt_acc(result['cb_fail']['accuracy'])}  "
        "(parametric wine knowledge)"
    )
    gap = result["gap"]
    gap_str = f"{gap * 100:+.2f} pts" if gap is not None else "n/a"
    print(f"  gap (cb_fail - cb_pass): {gap_str}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: python -m src.evaluation.cb_split <eval_run_uuid>", file=sys.stderr)
        sys.exit(2)
    _print_report(score_by_cb_split(sys.argv[1]))


# python -m src.evaluation.cb_split <eval_run_uuid>
