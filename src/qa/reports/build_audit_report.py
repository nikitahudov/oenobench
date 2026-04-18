"""Render `docs/QUALITY_AUDIT_REPORT.md` from audit_findings.

Pulls straight from Postgres — no LLM calls, no extra analysis. The sections
mirror the plan file:
  1 Executive summary
  2 Methodology
  3 Per-strategy deep dive
  4 Per-generator deep dive
  5 Cross-cutting
  6 Gold calibration
  7 Limitations
  8 Appendix (raw queries)
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from src.qa._findings import fetch_findings, fetch_gold_labels, get_run
from src.qa._scoring import cohens_kappa
from src.utils.db import get_pg

STRATEGY_ORDER = [
    "template",
    "fact_to_question",
    "comparative",
    "scenario_synthesis",
    "distractor_mining",
]


def _fetch_question_meta(tag: str) -> list[dict]:
    conn = get_pg()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT q.id, q.question_id, q.domain::text AS domain,
               q.difficulty::text AS difficulty,
               q.cognitive_dim::text AS cognitive_dim,
               q.question_type::text AS question_type,
               q.question_text, q.correct_answer,
               gm.generator::text AS generator, gm.generation_method
        FROM   questions q
        JOIN   generation_metadata gm ON gm.question_id = q.id
        WHERE  %s = ANY(q.tags)
        """,
        (tag,),
    )
    return cur.fetchall()


def _group_findings(findings: list[dict]) -> dict:
    by_agent: dict[str, list[dict]] = defaultdict(list)
    by_question: dict[str, list[dict]] = defaultdict(list)
    for f in findings:
        by_agent[f["agent_id"]].append(f)
        if f.get("question_id"):
            by_question[str(f["question_id"])].append(f)
    return {"by_agent": by_agent, "by_question": by_question}


def _severity_table(by_agent: dict[str, list[dict]]) -> list[str]:
    lines = ["| Agent | pass | warn | fail | error | total |",
             "|---|---:|---:|---:|---:|---:|"]
    for agent, rows in sorted(by_agent.items()):
        counts = Counter(r["severity"] for r in rows)
        total = sum(counts.values())
        lines.append(
            f"| {agent} | {counts.get('pass', 0)} | {counts.get('warn', 0)} | "
            f"{counts.get('fail', 0)} | {counts.get('error', 0)} | {total} |"
        )
    return lines


def _strategy_deep_dive(
    questions: list[dict],
    by_question: dict[str, list[dict]],
) -> list[str]:
    lines = []
    by_strategy: dict[str, list[dict]] = defaultdict(list)
    for q in questions:
        by_strategy[q.get("generation_method") or "unknown"].append(q)

    for strategy in STRATEGY_ORDER:
        qs = by_strategy.get(strategy, [])
        if not qs:
            continue
        lines.append(f"### {strategy}")
        lines.append("")
        lines.append(f"- Question count: **{len(qs)}**")

        # Aggregate severity across the strategy's questions
        sev_counter: Counter = Counter()
        per_agent_fail: dict[str, int] = defaultdict(int)
        for q in qs:
            qf = by_question.get(str(q["id"]), [])
            for f in qf:
                sev_counter[f["severity"]] += 1
                if f["severity"] == "fail":
                    per_agent_fail[f["agent_id"]] += 1
        lines.append(f"- Severity rollup: pass={sev_counter.get('pass', 0)}, "
                     f"warn={sev_counter.get('warn', 0)}, fail={sev_counter.get('fail', 0)}")
        if per_agent_fail:
            lines.append("- Failures by agent:")
            for agent, c in sorted(per_agent_fail.items(), key=lambda kv: -kv[1]):
                lines.append(f"  - {agent}: {c}")

        # Up to 3 failure examples
        fail_examples = []
        for q in qs:
            qf = by_question.get(str(q["id"]), [])
            fails = [f for f in qf if f["severity"] == "fail"]
            if fails:
                fail_examples.append((q, fails[0]))
            if len(fail_examples) == 3:
                break
        if fail_examples:
            lines.append("- Sample failures:")
            for q, f in fail_examples:
                snippet = (q.get("question_text") or "")[:180].replace("\n", " ")
                payload = f.get("payload") or {}
                if isinstance(payload, str):
                    try:
                        payload = json.loads(payload)
                    except Exception:
                        payload = {"raw": payload[:200]}
                reason = ""
                if "matches" in payload:
                    reason = f"matches={list(payload['matches'].keys())}"
                elif "leaked_distractors" in payload:
                    reason = f"leaked_categories={len(payload['leaked_distractors'])}"
                elif "majority_matches_key" in payload:
                    reason = f"majority_matches_key={payload['majority_matches_key']}"
                elif "lcs_ratio" in payload:
                    reason = f"lcs_ratio={payload['lcs_ratio']}"
                lines.append(
                    f"  - {q.get('question_id')}  ·  {f['agent_id']}  ·  {reason}"
                )
                lines.append(f"    > {snippet}")
        lines.append("")
    return lines


def _generator_deep_dive(
    questions: list[dict],
    by_question: dict[str, list[dict]],
    d1_findings: list[dict],
) -> list[str]:
    lines = []
    by_gen: dict[str, list[dict]] = defaultdict(list)
    for q in questions:
        by_gen[q.get("generator") or "template_only"].append(q)

    # D1 self-pref roll-up
    d1_by_eval: dict[str, dict] = {}
    for f in d1_findings:
        payload = f.get("payload") or {}
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except Exception:
                continue
        ev = payload.get("evaluator")
        if ev:
            d1_by_eval[ev] = payload

    for gen in sorted(by_gen):
        qs = by_gen[gen]
        lines.append(f"### {gen}")
        lines.append("")
        lines.append(f"- Authored question count: **{len(qs)}**")

        fail_counts: dict[str, int] = defaultdict(int)
        warn_counts: dict[str, int] = defaultdict(int)
        for q in qs:
            for f in by_question.get(str(q["id"]), []):
                if f["severity"] == "fail":
                    fail_counts[f["agent_id"]] += 1
                elif f["severity"] == "warn":
                    warn_counts[f["agent_id"]] += 1
        total_fails = sum(fail_counts.values())
        total_warns = sum(warn_counts.values())
        lines.append(f"- Total fails: {total_fails}, warns: {total_warns}")

        sp = d1_by_eval.get(gen)
        if sp and sp.get("self_pref_delta") is not None:
            lines.append(f"- Self-preference delta: **{sp['self_pref_delta']:+.3f}** "
                         f"(own={sp.get('own_accuracy')}, others={sp.get('others_mean_accuracy')})")
        lines.append("")
    return lines


def _cross_cutting(by_agent: dict[str, list[dict]]) -> list[str]:
    lines = ["## 5 · Cross-cutting findings", ""]

    # A2 bias summary
    a2 = [f for f in by_agent.get("A2_BiasStats", []) if (f.get("payload") or {}).get("cell") == "CORPUS"]
    if a2:
        p = a2[0].get("payload", {})
        if isinstance(p, str):
            try:
                p = json.loads(p)
            except Exception:
                p = {}
        lines.append("### Position / length bias (corpus-wide)")
        lines.append(f"- A/B/C/D counts: {p.get('mc_ABCD')}  χ²={p.get('position_chi2')}  p={p.get('position_p')}")
        lines.append(f"- mean(correct)={p.get('mean_correct_len')}  mean(distractor)={p.get('mean_distractor_len')}  Δ={p.get('length_delta')}")
        lines.append("")

    # A4 template AUC
    a4_pop = [f for f in by_agent.get("A4_TemplateFingerprint", []) if f.get("question_id") is None]
    if a4_pop:
        p = a4_pop[0].get("payload", {})
        if isinstance(p, str):
            try:
                p = json.loads(p)
            except Exception:
                p = {}
        lines.append("### Template detectability (A4)")
        lines.append(f"- Held-out AUC: **{p.get('test_auc')}**")
        top = p.get("top_features") or []
        if top:
            feats = ", ".join(f"`{k}` ({v:+.2f})" for k, v in top[:8])
            lines.append(f"- Top discriminative features: {feats}")
        lines.append("")

    # D3 skew
    d3 = by_agent.get("D3_SkewAudit", [])
    if d3:
        p = d3[0].get("payload", {})
        if isinstance(p, str):
            try:
                p = json.loads(p)
            except Exception:
                p = {}
        lines.append("### Country / domain skew (D3)")
        lines.append(f"- Max country over-representation ratio: **{p.get('max_overrep_ratio')}**")
        lines.append(f"- Question country counts (top 10): {dict(list((p.get('question_country_counts') or {}).items())[:10])}")
        hh = p.get("subdomain_herfindahl_by_strategy") or {}
        if hh:
            lines.append("- Subdomain Herfindahl per strategy: " +
                         ", ".join(f"{k}={v}" for k, v in hh.items()))
        lines.append("")
    return lines


def _gold_calibration(
    run_id: str,
    by_question: dict[str, list[dict]],
) -> list[str]:
    labels = fetch_gold_labels()
    if not labels:
        return [
            "## 6 · Gold calibration",
            "",
            "_No human gold labels imported. Run `import-gold` after offline review._",
            "",
        ]
    lines = ["## 6 · Gold calibration", "", f"- Human-reviewed items: **{len(labels)}**"]

    # κ on answer_correct vs B1 majority_matches_key
    rater_human = []
    rater_judge = []
    for qid, row in labels.items():
        human_labels = row.get("labels") or {}
        if isinstance(human_labels, str):
            try:
                human_labels = json.loads(human_labels)
            except Exception:
                continue
        h = human_labels.get("answer_correct")
        if h is None:
            continue
        qfindings = by_question.get(qid, [])
        b1 = next((f for f in qfindings if f["agent_id"] == "B1_TriJudgeAnswer"), None)
        if not b1:
            continue
        pb = b1.get("payload") or {}
        if isinstance(pb, str):
            try:
                pb = json.loads(pb)
            except Exception:
                continue
        j = bool(pb.get("majority_matches_key"))
        rater_human.append(1 if h else 0)
        rater_judge.append(1 if j else 0)
    if rater_human:
        kappa = cohens_kappa(rater_human, rater_judge)
        lines.append(f"- answer_correct κ(human, judge majority) = **{round(kappa, 3)}**  (n={len(rater_human)})")
        if kappa < 0.6:
            lines.append("- ⚠ κ below 0.6 — downweight B1 signal when interpreting strategy rollups.")
    lines.append("")
    return lines


def _limitations() -> list[str]:
    return [
        "## 7 · Limitations & deferred checks",
        "",
        "This MVA run excludes the following agents — failures in their weakness",
        "classes cannot be disproved by this report alone.",
        "",
        "- **C1 DistractorDifficulty** — per-distractor LLM plausibility scoring.",
        "- **B3 ParaphraseStability** — stem-rewrite consistency.",
        "- **B4 Ambiguity** — multi-defensible option scoring.",
        "- **C3 SourceSwap** — robustness to fact substitution.",
        "- **C4 DimensionCognitiveAudit** — LLM check on dimension/Bloom's/difficulty labels.",
        "- **D2 DedupCalibration** — similarity-threshold P/R sweep.",
        "- **D3-cultural** — LLM cultural-framing labelling (pure stats only ran).",
        "",
        "Escalation triggers (if the audit finds these, run the deferred agents):",
        "- A4 AUC ≥ 0.9 → run C1 + B4 on flagged subset.",
        "- B1 fail rate ≥ 10% → run B3 + C3 to triangulate.",
        "- D1 fail on any model → add more evaluator runs, include Llama/Qwen as secondary judges.",
        "",
    ]


def render(run_id: str, out_path: Path) -> None:
    run = get_run(run_id)
    if not run:
        raise RuntimeError(f"run {run_id} not found")
    tag = run["corpus_tag"]
    findings = fetch_findings(run_id)
    grouped = _group_findings(findings)
    questions = _fetch_question_meta(tag)
    d1_findings = [f for f in findings if f["agent_id"] == "D1_SelfPreference"]

    # Aggregate counts + cost
    total_cost = sum(f.get("cost_usd") or 0 for f in findings)
    total_calls = sum(f.get("llm_calls") or 0 for f in findings)
    sev_global = Counter(f["severity"] for f in findings)
    fail_count = sev_global.get("fail", 0)
    warn_count = sev_global.get("warn", 0)

    lines: list[str] = []
    lines.append("# OenoBench Quality Audit Report")
    lines.append("")
    lines.append(f"- Run ID: `{run_id}`")
    lines.append(f"- Corpus tag: `{tag}`")
    lines.append(f"- Corpus size: {run.get('corpus_size')}")
    lines.append(f"- Config hash: `{run['config_hash'][:16]}...`")
    lines.append(f"- Started: {run.get('started_at')}")
    lines.append(f"- Completed: {run.get('completed_at') or '(in progress)'}")
    lines.append(f"- LLM calls: {total_calls}")
    lines.append(f"- Cost: ${total_cost:.2f}")
    lines.append("")
    lines.append("## 1 · Executive summary")
    lines.append("")
    lines.append(f"- Findings across {len(grouped['by_agent'])} agents: "
                 f"{sev_global.get('pass', 0)} pass · {warn_count} warn · {fail_count} fail · {sev_global.get('error', 0)} error")
    lines.append("")
    lines += _severity_table(grouped["by_agent"])
    lines.append("")

    lines.append("## 2 · Methodology")
    lines.append("")
    lines.append(f"- Corpus: {len(questions)} questions tagged `{tag}`, seed {run.get('random_seed')}.")
    agents = run.get("metadata", {})
    if isinstance(agents, str):
        try:
            agents = json.loads(agents)
        except Exception:
            agents = {}
    lines.append(f"- Agents: {sorted((agents.get('agents') or {}).keys())}")
    lines.append(f"- Judge models: {agents.get('judges') or ['claude','chatgpt','gemini']}")
    lines.append(f"- Thresholds and seeds encoded in config hash (full hash: `{run['config_hash']}`).")
    lines.append("")

    lines.append("## 3 · Per-strategy deep dive")
    lines.append("")
    lines += _strategy_deep_dive(questions, grouped["by_question"])
    lines.append("## 4 · Per-generator deep dive")
    lines.append("")
    lines += _generator_deep_dive(questions, grouped["by_question"], d1_findings)

    lines += _cross_cutting(grouped["by_agent"])
    lines += _gold_calibration(run_id, grouped["by_question"])
    lines += _limitations()

    lines.append("## 8 · Appendix — raw queries")
    lines.append("")
    lines.append("```sql")
    lines.append(f"-- All findings for this run")
    lines.append(f"SELECT agent_id, severity, count(*) FROM audit_findings WHERE run_id = '{run_id}' GROUP BY 1,2;")
    lines.append("")
    lines.append(f"-- Per-question rollup")
    lines.append(f"SELECT * FROM v_question_audit_summary WHERE id IN (SELECT question_id FROM audit_findings WHERE run_id = '{run_id}');")
    lines.append("```")
    lines.append("")
    lines.append(f"_Generated {datetime.now().isoformat()}_")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
