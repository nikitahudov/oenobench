"""Phase 2j — auto-tag release_v1.1 questions with audit verdicts + emit
actionable defect report.

Reads the most recent `audit_runs` row for `--tag release_v1.1`, classifies
every question into one of:

  audit_clean         no FAIL, no WARN, ≥1 PASS
  audit_warn_only     no FAIL, ≥1 WARN
  audit_fail_review   only A1 FAIL (vague phrasing — light defect)
  audit_fail_critical ≥1 FAIL on B1 / B2-at-L1L2 / A3 / C2 (drop candidates)
  audit_no_signal     only ERROR rows / no findings (rate-limit casualty)

Writes the chosen tag onto `public.questions.tags`, removing any prior
`audit_*` tag on the same row first (idempotent across re-runs).

Also emits ``docs/RELEASE_V1_1_AUDIT_ACTIONS.md`` summarising the per-defect
groups, sample UUIDs, recommended actions, corpus-size projections, and
per-strategy fail-rate table.

Usage::

    python -m scripts.tag_audit_actions \\
        --tag release_v1.1 \\
        --out docs/RELEASE_V1_1_AUDIT_ACTIONS.md
    # or with --dry-run to print the SQL diff without mutating DB.

Population-level findings (A2, A4, D1, D3) do NOT drive per-question tags;
they appear in the report's "Corpus-aggregate signals" section only.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import click
from loguru import logger

from src.qa._findings import fetch_findings, latest_run_for_tag
from src.utils.db import get_pg


# Audit tags this script may apply / clean. Removed via array_remove on every
# run so repeated invocations stay idempotent.
#
# Naming note (2026-05-03): B2 and C4 produce findings that the audit pipeline
# stores with severity='fail' for historical reasons, but they are NOT real
# question-quality fails — they're calibration signals (B2: low-difficulty
# closed-book solvability; C4: difficulty mislabel). The release_v1.2 ship
# policy keeps these questions; B2 is documented in the datasheet and C4 is
# resolved by relabelling the question's difficulty column to C4's
# rated_difficulty. So we route B2 / C4 fails into a NEW
# `audit_calibration_warning` bucket, not `audit_fail_critical`.
AUDIT_TAGS = (
    "audit_clean",
    "audit_warn_only",
    "audit_calibration_warning",
    "audit_fail_review",
    "audit_fail_critical",
    "audit_no_signal",
)

# FAIL on any of these → drop candidate (audit_fail_critical).
CRITICAL_FAIL_AGENTS = {
    "B1_TriJudgeAnswer",
    "A3_FactEcho",
    "C2_CategoryLeak",
    "B3_UbiquityRisk",
}

# FAIL on any of these → calibration warning (kept; informational only).
# B2 and C4 are not real question-quality fails. B2 has well-documented low
# κ with humans (κ ≈ 0.007 on `needs_source` rubric); C4 difficulty
# disagreements are addressed by relabelling, not by dropping.
CALIBRATION_AGENTS = {
    "B2_ClosedBookSolvability",
    "C4_DifficultyAudit",
}

A1_AGENT = "A1_LexicalHygiene"

# Population-level (no question_id) — handled separately, not per-Q.
POPULATION_AGENTS = {"A2_BiasStats", "A4_TemplateFingerprint",
                     "D1_SelfPreference", "D3_SkewAudit"}

# Recommended-action copy per defect group (cited in the report).
ACTION_COPY = {
    "B1_TriJudgeAnswer": (
        "Drop from corpus. Tri-judge consensus disagrees with the keyed "
        "answer — likely wrong-key or unfaithful to source."
    ),
    "A3_FactEcho": (
        "Drop from corpus. Question text overlaps source verbatim (LCS≥0.65) — "
        "the test reduces to keyword matching."
    ),
    "C2_CategoryLeak": (
        "Drop from corpus. Distractor's wine category mismatches correct answer's "
        "(red vs white, sparkling vs still) — easy elimination defeats the question."
    ),
    "B3_UbiquityRisk": (
        "Drop from corpus. Question stem mentions an internationally-grown grape "
        "(Cabernet/Pinot Noir/Chardonnay/Merlot/Sauvignon Blanc/Syrah/Riesling/etc.) "
        "and the correct answer is a region-class entity — multiple regions plausibly "
        "grow the grape, so the answer is ambiguous. Confirmed via human gold review "
        "(9/45 = 20% ambiguity rate in release_v1_1_smart sample)."
    ),
    "A1_LexicalHygiene": (
        "Manual review (light defect). Vague phrasing ('iconic', 'acclaimed') — "
        "salvageable with a regex pass + paraphrase, but does not invalidate the question."
    ),
    "B2_ClosedBookSolvability": (
        "Calibration signal (KEEP). LLM-judge panel solved the question without "
        "the source fact, but historical Cohen's κ vs human reviewers is ~0.007 "
        "on this rubric — judges over-report leakage by ~5×. We keep the "
        "question and disclose the closed-book finding in the datasheet."
    ),
    "C4_DifficultyAudit": (
        "Calibration signal (KEEP, with relabel). Gemini-Pro re-rated the "
        "difficulty and disagreed with the assigned label by ≥2 levels. We "
        "keep the question and update its `difficulty` column to the C4 "
        "rated_difficulty (or the human suggested_difficulty when available "
        "from the gold review). Public question_id keeps its original L-suffix."
    ),
}


# ─── Classification ─────────────────────────────────────────────────────────


def _classify(findings_for_q: list[dict], difficulty: str) -> str:
    """Return one of AUDIT_TAGS for a single question."""
    severities: Counter[str] = Counter()
    fail_agents: set[str] = set()
    for f in findings_for_q:
        sev = (f["severity"] or "").lower()
        severities[sev] += 1
        if sev == "fail":
            fail_agents.add(f["agent_id"])

    # No findings AT ALL or only ERROR rows → no usable signal
    pass_count = severities["pass"]
    warn_count = severities["warn"]
    fail_count = severities["fail"]
    if pass_count + warn_count + fail_count == 0:
        return "audit_no_signal"

    # Critical FAILs (drop candidates) — wins priority
    if fail_agents & CRITICAL_FAIL_AGENTS:
        return "audit_fail_critical"

    # A1-only fail → light defect, manual review (kept by ship policy)
    if A1_AGENT in fail_agents:
        return "audit_fail_review"

    # B2 / C4 calibration signals (kept; informational only)
    if fail_agents & CALIBRATION_AGENTS:
        return "audit_calibration_warning"

    # Some other (rare) fail we didn't explicitly bucket → review
    if fail_count > 0:
        return "audit_fail_review"

    # No FAILs but at least one WARN
    if warn_count > 0:
        return "audit_warn_only"

    # Pure clean — no FAIL, no WARN, ≥1 PASS
    return "audit_clean"


# ─── Tag application ─────────────────────────────────────────────────────────


def _apply_tags(
    classification: dict[str, str], dry_run: bool, conn,
) -> dict[str, int]:
    """Return counts of {tag: rows_updated}. In dry_run mode, no UPDATEs run."""
    cur = conn.cursor()
    counts: Counter[str] = Counter()
    if dry_run:
        for q_uuid, tag in classification.items():
            counts[tag] += 1
        logger.info("[DRY-RUN] would tag {} questions; tag counts: {}",
                    len(classification), dict(counts))
        return dict(counts)

    # First clear any prior audit_* tag on these rows (idempotent re-run)
    by_tag: dict[str, list[str]] = defaultdict(list)
    for q_uuid, tag in classification.items():
        by_tag[tag].append(q_uuid)

    # Single statement: remove all audit_* values from the relevant rows, then
    # append the new value per group. Note: `%` is doubled (`%%`) in the SQL
    # so psycopg2's parameter-substitution doesn't try to interpret it.
    all_uuids = list(classification.keys())
    cur.execute(
        """
        UPDATE public.questions SET tags = (
            SELECT array_agg(t) FROM unnest(tags) AS t WHERE t NOT LIKE 'audit\\_%%'
        )
        WHERE id = ANY(%s::uuid[])
        """,
        (all_uuids,),
    )

    for tag, uuids in by_tag.items():
        cur.execute(
            """
            UPDATE public.questions
            SET tags = array_append(tags, %s)
            WHERE id = ANY(%s::uuid[])
            """,
            (tag, uuids),
        )
        counts[tag] = len(uuids)

    conn.commit()
    logger.info("Applied audit tags: {}", dict(counts))
    return dict(counts)


# ─── Report rendering ────────────────────────────────────────────────────────


def _per_strategy_fail_rates(
    findings: list[dict], strategy_for: dict[str, str],
) -> dict[str, dict]:
    """Compute fail/warn/pass counts per strategy from per-question findings."""
    rollup: dict[str, Counter] = defaultdict(Counter)
    seen_q_per_strategy: dict[str, set] = defaultdict(set)
    for f in findings:
        qid = f.get("question_id")
        if not qid:
            continue
        strategy = strategy_for.get(str(qid))
        if not strategy:
            continue
        sev = (f["severity"] or "").lower()
        rollup[strategy][sev] += 1
        seen_q_per_strategy[strategy].add(str(qid))

    out: dict[str, dict] = {}
    for strategy, counts in rollup.items():
        total_q = len(seen_q_per_strategy[strategy])
        out[strategy] = {
            "total_q": total_q,
            "fail": counts["fail"],
            "warn": counts["warn"],
            "pass": counts["pass"],
            "error": counts["error"],
        }
    return out


def _render_report(
    out_path: Path,
    *,
    run_id: str,
    corpus_tag: str,
    corpus_size: int,
    classification: dict[str, str],
    findings: list[dict],
    questions: dict[str, dict],
) -> None:
    """Emit the actionable Markdown report."""
    tag_counts = Counter(classification.values())

    # Per-defect groups (one bucket per agent that emits per-question FAIL)
    fail_by_agent: dict[str, list[str]] = defaultdict(list)
    for f in findings:
        if (f["severity"] or "").lower() != "fail":
            continue
        qid = f.get("question_id")
        if not qid:
            continue
        fail_by_agent[f["agent_id"]].append(str(qid))

    def _action(group: str) -> str:
        return ACTION_COPY.get(group, "Investigate; no auto-action.")

    lines: list[str] = []
    lines.append(f"# Release {corpus_tag} — Audit actions report")
    lines.append("")
    lines.append(f"- **Audit run_id**: `{run_id}`")
    lines.append(f"- **Corpus tag**: `{corpus_tag}`")
    lines.append(f"- **Corpus size**: {corpus_size}")
    lines.append(f"- **Generated**: {datetime.now(tz=timezone.utc).isoformat(timespec='seconds')}")
    lines.append("")

    # Categorisation summary
    lines.append("## 1 · Categorisation summary")
    lines.append("")
    lines.append("| Tag | Count | % | Recommended action |")
    lines.append("|---|---:|---:|---|")
    total = sum(tag_counts.values()) or 1
    short_action = {
        "audit_clean": "Keep",
        "audit_warn_only": "Keep; flag in datasheet",
        "audit_calibration_warning": "Keep; B2/C4 calibration signal disclosed in datasheet (C4 mislabel resolved by relabel)",
        "audit_fail_review": "Manual review (A1 vague-phrasing)",
        "audit_fail_critical": "Drop candidate (B1/A3/C2/B3 critical FAIL)",
        "audit_no_signal": "Re-run subset (audit signal incomplete)",
    }
    for tag in AUDIT_TAGS:
        c = tag_counts.get(tag, 0)
        lines.append(f"| `{tag}` | {c} | {c / total * 100:.1f}% | {short_action[tag]} |")
    lines.append("")

    # Per-defect groups
    lines.append("## 2 · Per-defect groups (FAIL findings)")
    lines.append("")
    GROUP_ORDER = (
        "B1_TriJudgeAnswer",
        "A3_FactEcho",
        "C2_CategoryLeak",
        "B3_UbiquityRisk",
        "A1_LexicalHygiene",
        "B2_ClosedBookSolvability",   # calibration signal — KEPT
        "C4_DifficultyAudit",         # calibration signal — KEPT (relabel applied)
    )
    for group in GROUP_ORDER:
        qids = fail_by_agent.get(group, [])
        if not qids:
            continue
        unique_qids = sorted(set(qids))
        lines.append(f"### {group} — {len(unique_qids)} questions")
        lines.append("")
        lines.append(f"**Recommended action**: {_action(group)}")
        lines.append("")
        sample = unique_qids[:5]
        lines.append("Sample UUIDs:")
        for qid in sample:
            q = questions.get(qid) or {}
            stem = (q.get("question_text") or "")[:120].replace("\n", " ")
            lines.append(f"- `{qid}` · {q.get('public_qid','?')} · L{q.get('difficulty','?')} · {stem}…")
        lines.append("")

    # Other FAIL agents (per-question but not in critical set)
    other_fail = {a: v for a, v in fail_by_agent.items() if a not in GROUP_ORDER}
    if other_fail:
        lines.append("### Other per-question FAILs (no auto-action)")
        lines.append("")
        for agent, qids in other_fail.items():
            unique_qids = sorted(set(qids))
            lines.append(f"- **{agent}**: {len(unique_qids)} questions")
        lines.append("")

    # Corpus-size projections
    lines.append("## 3 · Corpus-size projections")
    lines.append("")
    drop_critical = tag_counts.get("audit_fail_critical", 0)
    drop_review = tag_counts.get("audit_fail_review", 0)
    no_signal = tag_counts.get("audit_no_signal", 0)
    lines.append("| Action | Resulting corpus size |")
    lines.append("|---|---:|")
    lines.append(f"| Keep all | {corpus_size} |")
    lines.append(f"| Drop `audit_fail_critical` | {corpus_size - drop_critical} |")
    lines.append(f"| Drop `audit_fail_critical` + `audit_no_signal` | {corpus_size - drop_critical - no_signal} |")
    lines.append(f"| Drop `audit_fail_critical` + `audit_fail_review` | {corpus_size - drop_critical - drop_review} |")
    lines.append("")

    # Per-strategy fail-rate
    strategy_for = {qid: q.get("generation_method", "?") for qid, q in questions.items()}
    per_strategy = _per_strategy_fail_rates(findings, strategy_for)
    lines.append("## 4 · Per-strategy fail-rate table")
    lines.append("")
    lines.append("| Strategy | Q in tag | Fail findings | Warn findings | Pass findings |")
    lines.append("|---|---:|---:|---:|---:|")
    for strategy in sorted(per_strategy):
        row = per_strategy[strategy]
        lines.append(f"| {strategy} | {row['total_q']} | {row['fail']} | {row['warn']} | {row['pass']} |")
    lines.append("")

    # Population-level findings
    lines.append("## 5 · Corpus-aggregate signals (A2 / A4 / D1 / D3)")
    lines.append("")
    # Filter to corpus-aggregate findings (question_id IS NULL) only.
    # A4 also writes per-question rows; those are not population-level
    # signals and don't belong here.
    pop_findings = [
        f for f in findings
        if f["agent_id"] in POPULATION_AGENTS and f.get("question_id") is None
    ]
    if not pop_findings:
        lines.append("_No population-level findings recorded._")
        lines.append("")
    else:
        lines.append("| Agent | Severity | Score | Highlights |")
        lines.append("|---|---|---:|---|")
        for f in sorted(pop_findings, key=lambda x: x["agent_id"]):
            payload = f.get("payload") or {}
            if isinstance(payload, str):
                try:
                    payload = json.loads(payload)
                except Exception:
                    payload = {}
            highlights_keys = ("max_ratio", "auc", "delta", "max_country_ratio",
                               "p_value", "subdomain_herfindahl")
            hi = []
            for k in highlights_keys:
                if k in payload:
                    hi.append(f"{k}={payload[k]}")
            score = f.get("score")
            score_str = f"{float(score):.4f}" if score is not None else "—"
            lines.append(
                f"| {f['agent_id']} | {f['severity']} | {score_str} | {' · '.join(hi) or '—'} |"
            )
        lines.append("")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("Wrote audit-actions report: {}", out_path)


# ─── CLI ─────────────────────────────────────────────────────────────────────


@click.command()
@click.option("--tag", default="release_v1.1", show_default=True)
@click.option("--run-id", default=None, help="Override latest_run_for_tag with explicit run id")
@click.option("--out", type=click.Path(), default="docs/RELEASE_V1_1_AUDIT_ACTIONS.md", show_default=True)
@click.option("--dry-run", is_flag=True, help="Compute classification + write report, but do NOT mutate tags")
def main(tag: str, run_id: str | None, out: str, dry_run: bool):
    """Tag release_v1.1 questions with audit verdicts and emit actionable report."""
    if run_id:
        run = {"id": run_id, "corpus_tag": tag, "corpus_size": None}
        click.echo(f"Using explicit --run-id {run_id}")
    else:
        run = latest_run_for_tag(tag)
        if not run:
            click.echo(f"No audit run found for tag={tag}", err=True)
            raise SystemExit(1)
        run_id = str(run["id"])
        click.echo(f"Using latest run for tag={tag}: {run_id}")

    findings = fetch_findings(run_id)
    click.echo(f"Loaded {len(findings)} findings")

    # Pull questions in tag (UUID, public_qid, difficulty, generation_method, question_text)
    conn = get_pg()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT q.id::text AS uuid, q.question_id AS public_qid,
               q.difficulty::text AS difficulty,
               q.question_text,
               gm.generation_method
        FROM public.questions q
        LEFT JOIN generation_metadata gm ON gm.question_id = q.id
        WHERE %s = ANY(q.tags)
        """,
        (tag,),
    )
    rows = cur.fetchall()
    questions: dict[str, dict] = {r["uuid"]: dict(r) for r in rows}
    in_tag_uuids: set[str] = set(questions.keys())
    click.echo(f"Found {len(questions)} questions in tag")

    # Phase 2j: ALSO fetch metadata for finding-flagged questions that are
    # NOT in the current tag (e.g. questions dropped from release_v1.1 →
    # release_v1.2). These are needed for SAMPLE RENDERING in the per-defect
    # report sections only — they MUST NOT be classified into the audit-tag
    # buckets. Track them via `in_tag_uuids` and only iterate that set when
    # classifying / applying tags.
    finding_qids = {str(f["question_id"]) for f in findings if f.get("question_id")}
    missing = finding_qids - in_tag_uuids
    if missing:
        cur.execute(
            """
            SELECT q.id::text AS uuid, q.question_id AS public_qid,
                   q.difficulty::text AS difficulty,
                   q.question_text,
                   gm.generation_method
            FROM public.questions q
            LEFT JOIN generation_metadata gm ON gm.question_id = q.id
            WHERE q.id::text = ANY(%s)
            """,
            (list(missing),),
        )
        for r in cur.fetchall():
            questions[r["uuid"]] = dict(r)
        click.echo(f"  + {len(missing)} out-of-tag rows fetched for sample rendering only "
                   f"(NOT classified)")

    # Group findings per question
    findings_by_q: dict[str, list[dict]] = defaultdict(list)
    for f in findings:
        qid = f.get("question_id")
        if qid:
            findings_by_q[str(qid)].append(f)

    # Classify — ONLY questions actually in the active tag. Out-of-tag rows
    # (dropped from release_v1.1 → release_v1.2) are present in `questions`
    # only for sample-UUID rendering in the per-defect groups.
    classification: dict[str, str] = {}
    for qid in in_tag_uuids:
        q = questions[qid]
        classification[qid] = _classify(findings_by_q.get(qid, []), q.get("difficulty", ""))

    # Apply (or dry-run print)
    counts = _apply_tags(classification, dry_run=dry_run, conn=conn)
    click.echo("")
    click.echo("=== Categorisation ===")
    for tag_name in AUDIT_TAGS:
        click.echo(f"  {tag_name:25s} {counts.get(tag_name, 0):>5}")
    click.echo("")

    # Render report (always — even on dry-run). corpus_size reflects in-tag
    # only; per-defect samples may include out-of-tag rows for visibility.
    _render_report(
        Path(out), run_id=run_id, corpus_tag=tag,
        corpus_size=len(in_tag_uuids),
        classification=classification,
        findings=findings,
        questions=questions,
    )
    click.echo(f"Report written: {out}")


if __name__ == "__main__":
    main()
