"""Phase 2j — build a 50-question smart review CSV for human spot-check.

Composition (default):
  * 25 stratified random Qs from `audit_clean` ∪ `audit_warn_only`
    (round-robin by generation_method × difficulty)
  * 20 critical-FAIL Qs from `audit_fail_critical`, capped per agent across
    {B1, B2, A3, C2}, round-robin if a stratum is empty
  *  5 borderline-WARN Qs (B1/B2 finding score in 0.4-0.6 band)

Output extends the standard GOLD_RUBRICS columns (so existing `import-gold`
works) with three info-only columns appended at the end:

  * audit_severity_summary  — e.g. "B1=FAIL,B2=PASS,A3=WARN,..."
  * flagged_by_agent        — primary FAIL agent (or empty)
  * recommended_action      — drop_critical / manual_review / warn_only / clean

Usage::

    python -m scripts.build_smart_review_sheet \\
        --tag release_v1.1 \\
        --out data/reports/gold_sheet_release_v1_1_smart.csv \\
        --size 50 --seed 100
"""

from __future__ import annotations

import csv
import random
from collections import Counter, defaultdict
from pathlib import Path

import click
from loguru import logger

from src.qa._corpus import GOLD_RUBRICS
from src.qa._findings import fetch_findings, latest_run_for_tag
from src.utils.db import get_pg


# Critical-FAIL agents that drive drop decisions. B2 is included but the
# script filters to L1/L2 questions only (consistent with tag_audit_actions).
CRITICAL_AGENTS = ("B1_TriJudgeAnswer", "B2_ClosedBookSolvability",
                   "A3_FactEcho", "C2_CategoryLeak")
B2_AGENT = "B2_ClosedBookSolvability"

ACTION_FOR_TAG = {
    "audit_fail_critical": "drop_critical",
    "audit_fail_review": "manual_review",
    "audit_warn_only": "warn_only",
    "audit_clean": "clean",
    "audit_no_signal": "no_signal",
}


# ─── DB queries ─────────────────────────────────────────────────────────────


def _load_tagged_questions(tag: str) -> dict[str, dict]:
    """Return {uuid: row dict} for questions in the corpus tag with audit_*.

    Joins generation_metadata, computes audit_tag from the questions.tags array.
    """
    conn = get_pg()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
            q.id::text AS uuid,
            q.question_id AS public_qid,
            q.domain::text AS domain,
            q.difficulty::text AS difficulty,
            q.cognitive_dim::text AS cognitive_dim,
            q.question_text,
            q.options,
            q.correct_answer,
            q.tags,
            gm.generator::text AS generator,
            gm.generation_method,
            COALESCE((
                SELECT string_agg('[' || row_number || '] ' || fact_text, E'\n---\n' ORDER BY row_number)
                FROM (
                    SELECT f.fact_text,
                           row_number() OVER (PARTITION BY qf.question_id ORDER BY qf.fact_id)
                    FROM question_facts qf
                    JOIN facts f ON f.id = qf.fact_id
                    WHERE qf.question_id = q.id
                ) sub
            ), '') AS source_facts
        FROM public.questions q
        LEFT JOIN generation_metadata gm ON gm.question_id = q.id
        WHERE %s = ANY(q.tags) AND q.status::text = 'draft'
        """,
        (tag,),
    )
    rows = cur.fetchall()
    out: dict[str, dict] = {}
    for r in rows:
        d = dict(r)
        # Derive audit_tag from tags[]
        for t in (d.get("tags") or []):
            if t.startswith("audit_"):
                d["audit_tag"] = t
                break
        else:
            d["audit_tag"] = None
        out[d["uuid"]] = d
    return out


def _build_severity_summary(findings_by_q: dict[str, list[dict]], qid: str) -> str:
    """e.g. 'B1=FAIL,B2=PASS,A1=WARN'."""
    findings = findings_by_q.get(qid, [])
    by_agent: dict[str, str] = {}
    for f in findings:
        agent_short = (f["agent_id"] or "").split("_")[0]
        sev = (f["severity"] or "").upper()
        prev = by_agent.get(agent_short)
        # FAIL > WARN > ERROR > PASS in display priority
        order = {"FAIL": 4, "ERROR": 3, "WARN": 2, "PASS": 1}
        if not prev or order.get(sev, 0) > order.get(prev, 0):
            by_agent[agent_short] = sev
    parts = [f"{a}={s}" for a, s in sorted(by_agent.items())]
    return ",".join(parts)


def _flagged_by_agent(findings_by_q: dict[str, list[dict]], qid: str) -> str:
    """Pick the most-significant FAIL agent for this question (drop driver)."""
    findings = findings_by_q.get(qid, [])
    fails = [f for f in findings if (f["severity"] or "").lower() == "fail"]
    priority = ("B1_TriJudgeAnswer", "B2_ClosedBookSolvability",
                "A3_FactEcho", "C2_CategoryLeak", "A1_LexicalHygiene")
    for agent in priority:
        if any(f["agent_id"] == agent for f in fails):
            return agent
    return ""


# ─── Sampling layers ─────────────────────────────────────────────────────────


def _sample_stratified(
    pool: list[dict], n: int, seed: int,
) -> list[dict]:
    """Round-robin sampler across (generation_method, difficulty)."""
    if not pool or n <= 0:
        return []
    random.seed(seed)
    buckets: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in pool:
        key = (r.get("generation_method") or "?", str(r.get("difficulty") or "?"))
        buckets[key].append(r)
    for items in buckets.values():
        random.shuffle(items)

    chosen: list[dict] = []
    keys = sorted(buckets.keys())
    random.shuffle(keys)
    while len(chosen) < n and any(buckets[k] for k in keys):
        for k in keys:
            if not buckets[k]:
                continue
            chosen.append(buckets[k].pop())
            if len(chosen) >= n:
                break
    return chosen


def _sample_critical_fails(
    pool: list[dict],
    findings_by_q: dict[str, list[dict]],
    n: int,
    per_agent_cap: int,
    seed: int,
) -> list[dict]:
    """Sample critical-FAIL questions with per-agent quota."""
    if not pool or n <= 0:
        return []
    random.seed(seed + 1)
    by_agent: dict[str, list[dict]] = defaultdict(list)
    for r in pool:
        primary = _flagged_by_agent(findings_by_q, r["uuid"])
        if not primary:
            continue
        # B2 only counts at L1/L2
        if primary == B2_AGENT and str(r.get("difficulty", "")) not in ("1", "2"):
            continue
        by_agent[primary].append(r)
    for items in by_agent.values():
        random.shuffle(items)

    chosen: list[dict] = []
    quotas: Counter[str] = Counter()
    keys = sorted(by_agent.keys())
    random.shuffle(keys)
    # Round-robin with per-agent cap
    while len(chosen) < n and any(by_agent[k] for k in keys):
        for k in keys:
            if not by_agent[k] or quotas[k] >= per_agent_cap:
                continue
            chosen.append(by_agent[k].pop())
            quotas[k] += 1
            if len(chosen) >= n:
                break
        # If everyone hit cap but we still need more, allow over-cap (shouldn't happen at N=20, cap=5, 4 agents)
        if all((not by_agent[k]) or (quotas[k] >= per_agent_cap) for k in keys):
            if len(chosen) < n:
                for k in keys:
                    while by_agent[k] and len(chosen) < n:
                        chosen.append(by_agent[k].pop())
            break
    return chosen


def _sample_borderline_warn(
    questions: dict[str, dict],
    findings: list[dict],
    n: int,
    seed: int,
) -> list[dict]:
    """Pick questions whose B1/B2 WARN finding score is in 0.4-0.6."""
    if n <= 0:
        return []
    random.seed(seed + 2)
    candidates: dict[str, dict] = {}
    for f in findings:
        if (f["severity"] or "").lower() != "warn":
            continue
        if f["agent_id"] not in ("B1_TriJudgeAnswer", B2_AGENT):
            continue
        score = f.get("score")
        if score is None:
            continue
        try:
            s = float(score)
        except (TypeError, ValueError):
            continue
        if not (0.4 <= s <= 0.6):
            continue
        qid = str(f.get("question_id") or "")
        if not qid or qid not in questions:
            continue
        if qid not in candidates:
            candidates[qid] = questions[qid]
    pool = list(candidates.values())
    random.shuffle(pool)
    return pool[:n]


# ─── Output ─────────────────────────────────────────────────────────────────


def _write_csv(
    rows: list[dict], findings_by_q: dict[str, list[dict]], out_path: Path,
) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    extra_cols = ["audit_severity_summary", "flagged_by_agent", "recommended_action"]
    header = [
        "uuid", "public_qid", "strategy", "generator", "domain",
        "difficulty", "cognitive_dim", "question_text", "options",
        "correct_answer", "source_facts",
    ] + GOLD_RUBRICS + ["notes"] + extra_cols

    with out_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        for r in rows:
            audit_tag = r.get("audit_tag") or ""
            sev_summary = _build_severity_summary(findings_by_q, r["uuid"])
            flagged = _flagged_by_agent(findings_by_q, r["uuid"])
            action = ACTION_FOR_TAG.get(audit_tag, "")
            w.writerow([
                r["uuid"],
                r.get("public_qid") or "",
                r.get("generation_method") or "",
                r.get("generator") or "",
                r.get("domain") or "",
                r.get("difficulty") or "",
                r.get("cognitive_dim") or "",
                r.get("question_text") or "",
                r.get("options") or "",
                r.get("correct_answer") or "",
                (r.get("source_facts") or "")[:2000],
            ] + [""] * (len(GOLD_RUBRICS) + 1) + [
                sev_summary, flagged, action,
            ])


# ─── CLI ─────────────────────────────────────────────────────────────────────


@click.command()
@click.option("--tag", default="release_v1.1", show_default=True)
@click.option("--out", type=click.Path(),
              default="data/reports/gold_sheet_release_v1_1_smart.csv", show_default=True)
@click.option("--size", default=50, show_default=True, type=int)
@click.option("--n-stratified", default=25, show_default=True, type=int)
@click.option("--n-critical", default=20, show_default=True, type=int)
@click.option("--n-borderline", default=5, show_default=True, type=int)
@click.option("--per-agent-cap", default=5, show_default=True, type=int)
@click.option("--seed", default=100, show_default=True, type=int)
def main(tag, out, size, n_stratified, n_critical, n_borderline, per_agent_cap, seed):
    """Build a smart human-review CSV combining stratified + uncertainty sampling."""
    if n_stratified + n_critical + n_borderline != size:
        click.echo(f"WARNING: layer sizes ({n_stratified}+{n_critical}+{n_borderline}={n_stratified+n_critical+n_borderline}) "
                   f"don't sum to --size {size}; using layer values directly.", err=True)

    run = latest_run_for_tag(tag)
    if not run:
        click.echo(f"No audit run found for tag={tag}", err=True)
        raise SystemExit(1)
    run_id = str(run["id"])
    click.echo(f"Using audit run {run_id} for tag={tag}")

    findings = fetch_findings(run_id)
    findings_by_q: dict[str, list[dict]] = defaultdict(list)
    for f in findings:
        qid = f.get("question_id")
        if qid:
            findings_by_q[str(qid)].append(f)

    questions = _load_tagged_questions(tag)
    click.echo(f"Loaded {len(questions)} draft questions in tag")

    # Pool 1 — clean / warn-only
    pool_clean = [q for q in questions.values()
                  if q.get("audit_tag") in ("audit_clean", "audit_warn_only")]
    # Pool 2 — fail_critical
    pool_critical = [q for q in questions.values()
                     if q.get("audit_tag") == "audit_fail_critical"]

    if not pool_clean and not pool_critical:
        click.echo("No tagged questions found — was tag_audit_actions.py run already?", err=True)
        raise SystemExit(1)

    layer1 = _sample_stratified(pool_clean, n_stratified, seed)
    layer2 = _sample_critical_fails(pool_critical, findings_by_q, n_critical, per_agent_cap, seed)
    layer3 = _sample_borderline_warn(questions, findings, n_borderline, seed)

    # Dedupe across layers (a borderline could double-count)
    seen: set[str] = set()
    rows: list[dict] = []
    for layer_name, layer in [("stratified", layer1),
                              ("critical_fail", layer2),
                              ("borderline_warn", layer3)]:
        for r in layer:
            uuid = r["uuid"]
            if uuid in seen:
                continue
            seen.add(uuid)
            rows.append(r)
    random.seed(seed + 3)
    random.shuffle(rows)

    _write_csv(rows, findings_by_q, Path(out))

    click.echo("")
    click.echo("=== Sample composition ===")
    click.echo(f"  stratified clean/warn : {len(layer1)}")
    click.echo(f"  critical-FAIL         : {len(layer2)}")
    click.echo(f"  borderline-WARN       : {len(layer3)}")
    click.echo(f"  total (deduped)       : {len(rows)}")
    click.echo("")

    # Per-agent breakdown of critical layer
    by_agent: Counter[str] = Counter()
    for r in layer2:
        by_agent[_flagged_by_agent(findings_by_q, r["uuid"])] += 1
    if by_agent:
        click.echo("Critical-FAIL by primary agent:")
        for agent, c in sorted(by_agent.items()):
            click.echo(f"  {agent:30s} {c}")
        click.echo("")

    click.echo(f"CSV written: {out}")


if __name__ == "__main__":
    main()
