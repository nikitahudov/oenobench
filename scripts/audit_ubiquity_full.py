"""B3_UbiquityRisk — corpus-wide audit for ubiquitous-grape × region-answer ambiguity.

Background.
-----------
A question is at risk of "ubiquitous-grape ambiguity" if its stem mentions an
internationally-grown grape (Cabernet Sauvignon, Chardonnay, Merlot, Pinot
Noir, Sauvignon Blanc, Syrah/Shiraz, Riesling — plus any grape mentioned in
>30 facts in the local DB) AND its correct answer is a region-class entity
(region / country / appellation / AVA / DOC / DOCG / county / state / etc.).

Such questions typically have multiple valid answers ("Which region grows
Cabernet?" — many regions do), so any reasonable distractor could also be
correct. The pre-existing Phase 2g.17 sampler-time guard
(`_fact_sampler._fact_has_ubiquitous_grape`) prevents many of these at
generation time, but the gold-sheet review on `release_v1_1_smart` still
showed ambiguity in 9/45 (20%) of the smart sample.

What this script does
---------------------
1. Builds the ubiquity grape set the same way the sampler does (curated
   international grapes + any grape appearing in > 30 DB facts).
2. Builds a set of all known region-class entity names from the `facts`
   table's entities array (region, country, appellation, ava, doc, docg,
   doca, igp, aop, county, state, sub_region, subregion, wine_region).
3. For each question in the target tag, flags if:
     a. stem mentions any ubiquity grape (case-insensitive substring match
        with word-boundary check to avoid 'non-Cabernet' false positives),
        AND
     b. correct_answer_text matches a known region-class entity name
        (case-insensitive exact match).
4. Inserts findings under agent_id `B3_UbiquityRisk` into the existing
   audit_findings table, scoped to the audit run for the target tag
   (idempotent on the existing unique constraint).
5. Returns counts + per-strategy breakdown to stdout.

Usage::

    python -m scripts.audit_ubiquity_full \\
        --tag release_v1.1 --run-id 2ba38269-5e66-44aa-aaaf-010dc7ef19d4
    # or with --dry-run to see counts without writing findings
"""

from __future__ import annotations

import re
import uuid as _uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone

import click
import orjson
from loguru import logger

from src.qa._findings import latest_run_for_tag
from src.utils.db import get_pg


B3_AGENT_ID = "B3_UbiquityRisk"
B3_AGENT_VERSION = "v1.0.0"


# Curated international ubiquity set — same as _fact_sampler.UBIQUITY_GRAPES_CURATED
CURATED_UBIQUITY_GRAPES = {
    "cabernet sauvignon",
    "chardonnay",
    "merlot",
    "pinot noir",
    "sauvignon blanc",
    "syrah",
    "shiraz",
    "riesling",
}

# Data-driven cutoff: any grape mentioned in > N DB facts is "de-facto" ubiquitous.
DATA_DRIVEN_THRESHOLD = 30

# Entity types we consider "region-class" answers
REGION_ENTITY_TYPES = (
    "region",
    "country",
    "appellation",
    "ava",
    "doc",
    "aoc",
    "docg",
    "doca",
    "igp",
    "aop",
    "county",
    "state",
    "wine_region",
    "sub_region",
    "subregion",
)


def _normalise(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _build_ubiquity_set() -> set[str]:
    """Curated grapes + any grape with > DATA_DRIVEN_THRESHOLD fact mentions."""
    grapes = set(CURATED_UBIQUITY_GRAPES)
    conn = get_pg()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT lower(e->>'name') AS gname, count(*) AS n
            FROM facts f, jsonb_array_elements(f.entities) e
            WHERE e->>'type' = 'grape' AND e->>'name' IS NOT NULL
            GROUP BY lower(e->>'name')
            HAVING count(*) > %s
            """,
            (DATA_DRIVEN_THRESHOLD,),
        )
        for row in cur.fetchall():
            name = (row["gname"] or "").strip()
            if not name or len(name) < 4:
                continue
            grapes.add(_normalise(name))
    except Exception as exc:  # pragma: no cover — defensive
        logger.warning("ubiquity build: data-driven query failed: {}", exc)
    return grapes


def _build_region_set() -> set[str]:
    """All region-class entity names across the facts table (lowercased)."""
    conn = get_pg()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT DISTINCT lower(e->>'name') AS rname
        FROM facts f, jsonb_array_elements(f.entities) e
        WHERE e->>'type' = ANY(%s::text[]) AND e->>'name' IS NOT NULL
        """,
        (list(REGION_ENTITY_TYPES),),
    )
    return {(row["rname"] or "").strip() for row in cur.fetchall() if row["rname"]}


def _stem_mentions_ubiquity(stem: str, ubiquity: set[str]) -> str | None:
    """Return the matched grape name, or None.

    Uses word-boundary regex to avoid 'non-Cabernet' / 'unlike Pinot' style
    false positives at the token boundary, while still permitting
    partial-word-internal matches like 'Pinot Noir' inside a longer phrase.
    """
    s = stem.lower()
    for grape in ubiquity:
        # \b at the boundaries handles common cases. For multi-word grapes
        # the embedded space already creates an internal boundary.
        # `re.escape` guards against any special chars in the grape name.
        pattern = r"\b" + re.escape(grape) + r"\b"
        if re.search(pattern, s):
            return grape
    return None


def _answer_is_region(answer_text: str, region_set: set[str]) -> bool:
    if not answer_text:
        return False
    norm = _normalise(answer_text)
    if norm in region_set:
        return True
    # Common pattern: "the X region" or "X AVA" — try stripping
    # "the " prefix and trailing region-style suffixes.
    norm_alt = re.sub(r"^the\s+", "", norm)
    norm_alt = re.sub(
        r"\s+(region|wine region|appellation|aoc|aop|doc|docg|igp|ava|county|state)$",
        "", norm_alt,
    ).strip()
    if norm_alt and norm_alt in region_set:
        return True
    return False


def _insert_finding(cur, run_id, question_id, severity, score, payload):
    """Insert one audit_findings row, idempotent on uq_audit_findings_agent.

    The unique index is on `(run_id, COALESCE(question_id::text, ''),
    agent_id, agent_version)` (see config/postgres/002_audit_schema.sql).
    Use ON CONFLICT ON CONSTRAINT to target it by name.
    """
    cur.execute(
        """
        INSERT INTO audit_findings
            (id, run_id, question_id, agent_id, agent_version,
             severity, score, payload, llm_calls, cost_usd, created_at)
        VALUES (%s, %s, %s, %s, %s, %s::audit_severity, %s, %s::jsonb, %s, %s, NOW())
        ON CONFLICT (run_id, (COALESCE((question_id)::text, ''::text)), agent_id, agent_version)
        DO UPDATE SET severity = EXCLUDED.severity,
                      score    = EXCLUDED.score,
                      payload  = EXCLUDED.payload
        """,
        (
            str(_uuid.uuid4()), run_id, question_id, B3_AGENT_ID, B3_AGENT_VERSION,
            severity, score, orjson.dumps(payload).decode(), 0, 0.0,
        ),
    )


@click.command()
@click.option("--tag", default="release_v1.1", show_default=True)
@click.option("--run-id", default=None, help="Audit run id (default: latest for --tag)")
@click.option("--dry-run", is_flag=True, help="Compute matches without writing findings")
def main(tag, run_id, dry_run):
    if not run_id:
        run = latest_run_for_tag(tag)
        if not run:
            click.echo(f"No audit run for tag={tag}", err=True)
            raise SystemExit(1)
        run_id = str(run["id"])
    click.echo(f"audit run: {run_id}")

    ubiquity = _build_ubiquity_set()
    click.echo(f"ubiquity grape set: {len(ubiquity)} entries")
    click.echo(f"  curated:     {len(CURATED_UBIQUITY_GRAPES)}")
    click.echo(f"  data-driven: {len(ubiquity) - len(CURATED_UBIQUITY_GRAPES)}")
    region_set = _build_region_set()
    click.echo(f"region entity set: {len(region_set)} unique names")

    conn = get_pg()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT q.id::text AS uuid, q.question_id AS public_qid,
               q.question_text, q.correct_answer_text, q.difficulty::text AS difficulty,
               gm.generation_method, gm.generator::text AS generator
        FROM public.questions q
        LEFT JOIN generation_metadata gm ON gm.question_id = q.id
        WHERE %s = ANY(q.tags) AND q.status::text = 'draft'
        """,
        (tag,),
    )
    rows = cur.fetchall()
    click.echo(f"scanning {len(rows)} draft questions tagged {tag}")

    flagged = []  # list of dicts
    by_strategy = Counter()
    by_grape = Counter()

    for r in rows:
        stem = r["question_text"] or ""
        answer = r["correct_answer_text"] or ""
        matched_grape = _stem_mentions_ubiquity(stem, ubiquity)
        if not matched_grape:
            continue
        if not _answer_is_region(answer, region_set):
            continue
        flagged.append({
            "uuid": r["uuid"],
            "public_qid": r["public_qid"],
            "strategy": r["generation_method"],
            "generator": r["generator"],
            "difficulty": r["difficulty"],
            "matched_grape": matched_grape,
            "answer": answer,
            "stem_excerpt": stem[:160],
        })
        by_strategy[r["generation_method"]] += 1
        by_grape[matched_grape] += 1

    click.echo("")
    click.echo(f"=== B3_UbiquityRisk: {len(flagged)} flagged questions "
               f"({len(flagged)/max(1, len(rows))*100:.1f}% of corpus) ===")
    click.echo("\nBy strategy:")
    for s, c in by_strategy.most_common():
        click.echo(f"  {s:25s} {c}")
    click.echo("\nTop 10 grapes:")
    for g, c in by_grape.most_common(10):
        click.echo(f"  {g:30s} {c}")

    if flagged:
        click.echo("\nSample (first 8):")
        for f in flagged[:8]:
            click.echo(f"  {f['public_qid']} · L{f['difficulty']} · grape={f['matched_grape']!r}"
                       f" · ans={f['answer']!r}")
            click.echo(f"    stem: {f['stem_excerpt']}…")

    if dry_run:
        click.echo("\n[DRY-RUN] no findings written")
        return

    # Write findings — one per question. Severity=fail.
    for f in flagged:
        _insert_finding(
            cur, run_id, f["uuid"], "fail", 1.0,
            {
                "matched_grape": f["matched_grape"],
                "answer": f["answer"],
                "stem_excerpt": f["stem_excerpt"],
                "agent_version": B3_AGENT_VERSION,
                "rule": "ubiquity-grape × region-answer",
                "cf": "Multiple regions plausibly grow this grape; answer is therefore"
                      " ambiguous. The pre-Phase-2g.17 generator-side filter should"
                      " have caught this; treat as a drop candidate.",
            },
        )
    conn.commit()
    click.echo(f"\nWrote {len(flagged)} {B3_AGENT_ID} findings under run {run_id}")


if __name__ == "__main__":
    main()
