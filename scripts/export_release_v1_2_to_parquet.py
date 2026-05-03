"""Export release_v1.2 corpus to a HuggingFace-ready Parquet file.

Pulls the 3,329 questions tagged `release_v1.2` from public.questions, joins
generation_metadata + question_facts → facts → sources, and writes a single
Parquet file at data/exports/oenobench_v1/test.parquet.

Schema (one row per question):
    uuid                       str   internal UUID (stable across the project lifetime)
    question_id                str   public ID, e.g. WB-REG-0042-L3
    domain                     str   one of {wine_regions, grape_varieties, producers, viticulture, winemaking, wine_business}
    difficulty                 int   1..4, post-relabel (C4-corrected where applicable)
    difficulty_assigned        int   1..4, original generator-assigned label
    difficulty_relabel_source  str?  null | "c4_fail" | "human_override"
    question_type              str   "multiple_choice"
    cognitive_dim              str   {recall, compare, apply, synthesize}
    question_text              str   the stem
    options                    list[struct]   [{id: "A"/"B"/"C"/"D", text: "..."}]
    correct_answer             str   "A"|"B"|"C"|"D"
    correct_answer_text        str   the prose form of the correct option
    explanation                str   short rationale
    generator                  str   {claude, chatgpt, gemini, llama, qwen, template_only}
    generation_method          str   {fact_to_question, comparative, scenario_synthesis, distractor_mining, template}
    source_facts               list[struct]   [{fact_id, fact_text, source_name, source_url}]
    audit_verdict              str   {audit_clean, audit_warn_only, audit_calibration_warning, audit_fail_review}

The Parquet schema is fixed (no per-row schema variance) for clean
auto-detection by HF datasets viewer.

Usage::

    .venv/bin/python scripts/export_release_v1_2_to_parquet.py \\
        --tag release_v1.2 \\
        --out data/exports/oenobench_v1/test.parquet
"""

from __future__ import annotations

import json
from pathlib import Path

import click
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from loguru import logger

from src.utils.db import get_pg


AUDIT_TAG_PRIORITY = (
    "audit_fail_critical",       # would only appear if reclassification slipped
    "audit_fail_review",
    "audit_calibration_warning",
    "audit_warn_only",
    "audit_clean",
    "audit_no_signal",
)


def _resolve_audit_verdict(tags: list[str]) -> str:
    """Pick the most-significant audit_* tag from a question's tags."""
    audit_tags = [t for t in (tags or []) if t.startswith("audit_")]
    for priority_tag in AUDIT_TAG_PRIORITY:
        if priority_tag in audit_tags:
            return priority_tag
    return "audit_no_signal"


def _build_relabel_index(run_id: str) -> dict[str, dict]:
    """Re-derive the relabel provenance for each release_v1.2 question.

    The audit_difficulty_relabeled_* tags were inadvertently wiped by a
    later re-run of tag_audit_actions.py (which strips all `audit_*` tags
    before applying its own classification). The actual relabel data is
    intact: the questions.difficulty column is correctly updated, the C4
    findings are in audit_findings, and the human suggested_difficulty
    rows are in human_reviews. This reconstructs provenance from those
    sources of truth.

    Returns: {uuid: {"source": "c4_fail"|"human_override", "assigned": int}}
    """
    conn = get_pg()
    cur = conn.cursor()

    # 1. Human suggested_difficulty (wins priority — same logic as Phase 5b)
    cur.execute(
        """
        SELECT hr.question_id::text AS qid, hr.suggested_difficulty AS new_diff,
               q.difficulty::text AS current_diff
        FROM human_reviews hr
        JOIN public.questions q ON q.id = hr.question_id
        WHERE hr.batch_id = (SELECT id FROM review_batches WHERE name='release_v1_1_smart')
          AND hr.suggested_difficulty IS NOT NULL
          AND 'release_v1.2' = ANY(q.tags)
        """,
    )
    human_set = {row["qid"]: row for row in cur.fetchall()}

    # 2. ALL C4 findings (any severity) — needed because human_override rows
    # may have C4 WARN or PASS rather than FAIL, but the payload still carries
    # the original assigned_difficulty we want to surface in the parquet.
    cur.execute(
        """
        SELECT question_id::text AS qid,
               severity::text AS severity,
               (payload->>'assigned_difficulty')::int AS assigned,
               (payload->>'rated_difficulty')::int AS rated
        FROM audit_findings
        WHERE run_id = %s::uuid AND agent_id = 'C4_DifficultyAudit'
          AND question_id IS NOT NULL
        """,
        (run_id,),
    )
    c4_all = {row["qid"]: row for row in cur.fetchall()}
    # For the relabel-index decision, the C4_FAIL set is what matters
    # (relabel only fires on FAIL); other severities just provide assigned_difficulty.
    c4_set = {qid: r for qid, r in c4_all.items() if r["severity"] == "fail"}

    # Combined index — only include rows whose post-relabel difficulty
    # actually differs from C4's assigned (i.e., the relabel actually
    # happened in Phase 5b).
    cur.execute(
        """
        SELECT q.id::text AS qid, q.difficulty::text AS current_diff
        FROM public.questions q
        WHERE 'release_v1.2' = ANY(q.tags)
        """,
    )
    current = {row["qid"]: int(row["current_diff"]) for row in cur.fetchall()}

    out: dict[str, dict] = {}
    for qid, hrow in human_set.items():
        new_diff = int(hrow["new_diff"])
        if current.get(qid) == new_diff:
            # Difficulty matches the human suggestion → relabel happened
            assigned = c4_all.get(qid, {}).get("assigned")  # any-severity C4 row
            out[qid] = {"source": "human_override", "assigned": assigned}
    for qid, crow in c4_set.items():
        if qid in out:
            continue  # human override wins
        assigned = crow["assigned"]
        rated = crow["rated"]
        if current.get(qid) == rated and current.get(qid) != assigned:
            out[qid] = {"source": "c4_fail", "assigned": assigned}
    return out


def _resolve_relabel_source(tags: list[str]) -> str | None:
    """Legacy tag-based resolution. Kept for callers that still pass tags."""
    if not tags:
        return None
    if "audit_difficulty_relabeled_human_override" in tags:
        return "human_override"
    if "audit_difficulty_relabeled_c4_fail" in tags:
        return "c4_fail"
    return None


def fetch_corpus(tag: str) -> list[dict]:
    """Pull all questions in tag with provenance + facts joined."""
    conn = get_pg()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
            q.id::text                           AS uuid,
            q.question_id                        AS question_id,
            q.domain::text                       AS domain,
            q.difficulty::text                   AS difficulty,
            q.question_type::text                AS question_type,
            q.cognitive_dim::text                AS cognitive_dim,
            q.question_text                      AS question_text,
            q.options                            AS options_jsonb,
            q.correct_answer                     AS correct_answer,
            q.correct_answer_text                AS correct_answer_text,
            q.explanation                        AS explanation,
            q.tags                               AS tags,
            gm.generator::text                   AS generator,
            gm.generation_method                 AS generation_method,
            (
                SELECT json_agg(json_build_object(
                    'fact_id',     f.id::text,
                    'fact_text',   f.fact_text,
                    'source_name', s.name,
                    'source_url',  s.url
                ) ORDER BY qf.fact_id)
                FROM question_facts qf
                JOIN facts f ON f.id = qf.fact_id
                LEFT JOIN sources s ON s.id = f.source_id
                WHERE qf.question_id = q.id
            ) AS source_facts_json
        FROM public.questions q
        LEFT JOIN generation_metadata gm ON gm.question_id = q.id
        WHERE %s = ANY(q.tags) AND q.status::text = 'draft'
        ORDER BY q.question_id
        """,
        (tag,),
    )
    rows = cur.fetchall()
    return [dict(r) for r in rows]


def lookup_assigned_difficulty(uuid_str: str, c4_findings: dict[str, dict]) -> int | None:
    """For a relabelled question, recover the original generator-assigned difficulty
    from the C4 audit_findings payload. None if no C4 row exists.
    """
    rec = c4_findings.get(uuid_str)
    if not rec:
        return None
    payload = rec.get("payload") or {}
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except Exception:
            return None
    val = payload.get("assigned_difficulty")
    if val is None:
        return None
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def _row_to_parquet_dict(
    r: dict,
    c4_findings: dict[str, dict],
    relabel_index: dict[str, dict],
) -> dict:
    """Convert a fetched row into the Parquet schema."""
    options_raw = r.get("options_jsonb") or []
    if isinstance(options_raw, str):
        options = json.loads(options_raw)
    else:
        options = options_raw
    # Normalise to list of {id, text}
    norm_options = []
    for opt in options:
        if isinstance(opt, dict):
            norm_options.append({
                "id": str(opt.get("id") or ""),
                "text": str(opt.get("text") or ""),
            })
    source_facts_raw = r.get("source_facts_json") or []
    if isinstance(source_facts_raw, str):
        source_facts = json.loads(source_facts_raw)
    elif source_facts_raw is None:
        source_facts = []
    else:
        source_facts = source_facts_raw
    norm_source_facts = []
    for sf in source_facts:
        if not isinstance(sf, dict):
            continue
        norm_source_facts.append({
            "fact_id": str(sf.get("fact_id") or ""),
            "fact_text": str(sf.get("fact_text") or ""),
            "source_name": str(sf.get("source_name") or ""),
            "source_url": str(sf.get("source_url") or ""),
        })

    tags = r.get("tags") or []

    try:
        difficulty_post = int(r["difficulty"])
    except (TypeError, ValueError):
        difficulty_post = None

    # Prefer the reconstructed relabel index (audit_findings + human_reviews)
    # over the tag-based resolution since the tags were inadvertently wiped.
    relabel_source: str | None = None
    difficulty_assigned: int | None = None
    rec = relabel_index.get(r["uuid"])
    if rec:
        relabel_source = rec["source"]
        difficulty_assigned = rec.get("assigned")
    else:
        # Fallback to legacy tag-based resolution (still might be present
        # on a snapshot of the DB pre-tag-strip).
        relabel_source = _resolve_relabel_source(tags)
        if relabel_source:
            difficulty_assigned = lookup_assigned_difficulty(r["uuid"], c4_findings)
    if difficulty_assigned is None:
        # Not relabelled → assigned == post
        difficulty_assigned = difficulty_post

    return {
        "uuid": r["uuid"],
        "question_id": r["question_id"],
        "domain": r["domain"],
        "difficulty": difficulty_post,
        "difficulty_assigned": difficulty_assigned,
        "difficulty_relabel_source": relabel_source,
        "question_type": r["question_type"],
        "cognitive_dim": r["cognitive_dim"],
        "question_text": r["question_text"],
        "options": norm_options,
        "correct_answer": r["correct_answer"],
        "correct_answer_text": r["correct_answer_text"],
        "explanation": r["explanation"] or "",
        "generator": r["generator"],
        "generation_method": r["generation_method"],
        "source_facts": norm_source_facts,
        "audit_verdict": _resolve_audit_verdict(tags),
    }


def fetch_c4_payloads(run_id: str) -> dict[str, dict]:
    """Pull all C4 findings under a run_id, keyed by question_id."""
    conn = get_pg()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT question_id::text AS qid, severity::text AS severity, payload
        FROM audit_findings
        WHERE run_id = %s::uuid AND agent_id = 'C4_DifficultyAudit'
        """,
        (run_id,),
    )
    return {row["qid"]: dict(row) for row in cur.fetchall()}


# Stable Parquet schema (fixes column types so HF auto-detection is clean)
PARQUET_SCHEMA = pa.schema([
    pa.field("uuid", pa.string()),
    pa.field("question_id", pa.string()),
    pa.field("domain", pa.string()),
    pa.field("difficulty", pa.int8()),
    pa.field("difficulty_assigned", pa.int8()),
    pa.field("difficulty_relabel_source", pa.string()),
    pa.field("question_type", pa.string()),
    pa.field("cognitive_dim", pa.string()),
    pa.field("question_text", pa.string()),
    pa.field(
        "options",
        pa.list_(pa.struct([
            pa.field("id", pa.string()),
            pa.field("text", pa.string()),
        ])),
    ),
    pa.field("correct_answer", pa.string()),
    pa.field("correct_answer_text", pa.string()),
    pa.field("explanation", pa.string()),
    pa.field("generator", pa.string()),
    pa.field("generation_method", pa.string()),
    pa.field(
        "source_facts",
        pa.list_(pa.struct([
            pa.field("fact_id", pa.string()),
            pa.field("fact_text", pa.string()),
            pa.field("source_name", pa.string()),
            pa.field("source_url", pa.string()),
        ])),
    ),
    pa.field("audit_verdict", pa.string()),
])


@click.command()
@click.option("--tag", default="release_v1.2", show_default=True)
@click.option(
    "--run-id", default="2ba38269-5e66-44aa-aaaf-010dc7ef19d4", show_default=True,
    help="Audit run id used to recover original assigned difficulty for relabelled rows",
)
@click.option(
    "--out", type=click.Path(),
    default="data/exports/oenobench_v1/test.parquet", show_default=True,
)
def main(tag, run_id, out):
    """Export release_v1.2 corpus to Parquet."""
    rows = fetch_corpus(tag)
    click.echo(f"fetched {len(rows)} questions tagged {tag}")
    if not rows:
        click.echo(f"no questions found for tag={tag}; aborting", err=True)
        raise SystemExit(1)

    c4_findings = fetch_c4_payloads(run_id)
    click.echo(f"loaded {len(c4_findings)} C4 findings for assigned-difficulty lookup")

    relabel_index = _build_relabel_index(run_id)
    click.echo(f"reconstructed relabel provenance for {len(relabel_index)} questions "
               f"(c4_fail: {sum(1 for v in relabel_index.values() if v['source']=='c4_fail')}, "
               f"human_override: {sum(1 for v in relabel_index.values() if v['source']=='human_override')})")

    transformed = [_row_to_parquet_dict(r, c4_findings, relabel_index) for r in rows]

    # Convert to a pyarrow Table with explicit schema
    df = pd.DataFrame(transformed)
    table = pa.Table.from_pandas(df, schema=PARQUET_SCHEMA, preserve_index=False)

    out_path = Path(out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, out_path, compression="zstd")
    size_mb = out_path.stat().st_size / 1024 / 1024
    click.echo(f"wrote {out_path} ({size_mb:.2f} MB, {len(df)} rows)")

    # Sanity-print column dtypes + a sample row
    click.echo("\n=== Schema ===")
    for f in PARQUET_SCHEMA:
        click.echo(f"  {f.name}: {f.type}")
    click.echo("\n=== Sample row 0 (truncated) ===")
    sample = transformed[0].copy()
    sample["question_text"] = (sample.get("question_text") or "")[:120] + "..."
    sample["explanation"] = (sample.get("explanation") or "")[:80] + "..."
    click.echo(json.dumps(sample, indent=2, default=str)[:1500])


if __name__ == "__main__":
    main()
