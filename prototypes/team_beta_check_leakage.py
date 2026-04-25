"""Manual closed-book leakage check on team_beta prototype questions.

Calls the same Sonnet 4.6 closed-book setup the gate uses, forcing the
gate to apply regardless of question_type ('scenario_based' is normally
skipped by screen_question).

Reports leakage rate (gate solved closed-book at conf>=0.7) on the tagged
prototype set.
"""

import sys
import time
from typing import Any

import click
from loguru import logger

from src.generators._closed_book_gate import (
    CONFIDENCE_THRESHOLD,
    GATE_MODEL,
    _call_gate,
    _format_options,
    _get_client,
    _normalize_letter,
    _PROMPT,
)
from src.generators._llm_client import _try_parse_json
from src.utils.db import get_pg


def force_gate(stem, options, correct_answer):
    """Identical logic to screen_question() but bypasses type/difficulty skips."""
    options_block = _format_options(options)
    if not options_block:
        return {"applied": False, "reason": "no options"}
    gold = _normalize_letter(correct_answer)
    prompt = _PROMPT.format(stem=stem, options_block=options_block)
    client = _get_client()
    t0 = time.time()
    try:
        resp = _call_gate(client, prompt)
        latency_ms = int((time.time() - t0) * 1000)
        content = resp.choices[0].message.content or ""
        parsed = _try_parse_json(content)
    except Exception as e:
        return {"applied": True, "error": str(e)}
    if not parsed:
        return {"applied": True, "error": "parse_failed", "raw": content[:200]}
    selected = _normalize_letter(parsed.get("selected"))
    try:
        confidence = float(parsed.get("confidence", 0.0) or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0
    matched = bool(selected) and selected == gold
    leaked = matched and confidence >= CONFIDENCE_THRESHOLD
    return {
        "applied": True,
        "selected": selected,
        "gold": gold,
        "confidence": confidence,
        "matched": matched,
        "leaked": leaked,
        "reasoning": str(parsed.get("reasoning", ""))[:300],
        "latency_ms": latency_ms,
    }


@click.command()
@click.option("--tag", default="prototype_team_beta",
              help="Tag to filter prototype questions.")
@click.option("--limit", type=int, default=20, help="How many to gate-check.")
def main(tag, limit):
    conn = get_pg()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT q.id, q.question_id, q.question_text, q.options, q.correct_answer,
               q.difficulty, q.tags
        FROM questions q
        WHERE %s = ANY(q.tags)
        ORDER BY q.created_at
        LIMIT %s
        """,
        (tag, limit),
    )
    rows = cur.fetchall()
    if not rows:
        click.echo("No tagged questions found.")
        return 1

    click.echo(f"\nManual closed-book gate (model={GATE_MODEL}, conf>={CONFIDENCE_THRESHOLD})\n")
    click.echo(f"Total tagged: {len(rows)}\n")

    leaked = 0
    api_err = 0
    parse_err = 0
    for i, r in enumerate(rows, 1):
        result = force_gate(
            r["question_text"], r["options"], r["correct_answer"],
        )
        if not result.get("applied"):
            click.echo(f"[{i}] {r['question_id']} L{r['difficulty']} — SKIP: {result.get('reason')}")
            continue
        if result.get("error"):
            api_err += 1
            click.echo(f"[{i}] {r['question_id']} L{r['difficulty']} — ERROR: {result['error']}")
            continue
        marker = "LEAK" if result["leaked"] else ("near" if result["matched"] else "ok")
        click.echo(
            f"[{i}] {r['question_id']} L{r['difficulty']} — gate={result['selected']} "
            f"gold={result['gold']} conf={result['confidence']:.2f} → {marker}"
        )
        click.echo(f"     reasoning: {result['reasoning'][:140]}")
        if result["leaked"]:
            leaked += 1

    click.echo(f"\n=== Summary ===")
    click.echo(f"Total tested:    {len(rows)}")
    click.echo(f"Closed-book leaked (matched + conf>=0.7): {leaked}")
    click.echo(f"Leak rate:       {leaked/len(rows)*100:.1f}%")
    if api_err:
        click.echo(f"API errors:      {api_err}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
