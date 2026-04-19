"""Render `docs/GENERATION_IMPROVEMENT_PLAN.md` from audit_findings.

Ranks defects by (impact × fix-cost) using a simple heuristic over severity
and breadth. Every row is a concrete, actionable plan item with an attached
verification test description.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from src.qa._findings import fetch_findings, get_run

# Defect catalogue — maps each agent to a (human name, default fix, test) triple
# plus an "effort" estimate in S/M/L.
DEFECT_CATALOGUE = {
    "A1_LexicalHygiene": {
        "name": "Vague / marketing / blend-as-variety phrasing",
        "fix": "Extend `_VAGUE_PATTERNS` and `_BLEND_AS_VARIETY` regexes with the matched phrases; "
               "add post-LLM filter in `_schemas.py` that rejects questions whose stem or options "
               "contain any blocked phrase.",
        "affected": "All LLM strategies.",
        "test": "Fixture questions with each blocked phrase should score fail in A1.",
        "effort": "S",
    },
    "A2_BiasStats": {
        "name": "Correct-answer position / length bias",
        "fix": "Ensure `_schemas.py` option-shuffle runs before DB insert; if length bias persists, "
               "add a length-normaliser to post-LLM validator that pads / trims distractor texts.",
        "affected": "All MC strategies.",
        "test": "After fix, A2 χ² p-value > 0.2 on any (strategy,generator) cell with n ≥ 20.",
        "effort": "M",
    },
    "A3_FactEcho": {
        "name": "Verbatim source copying in question text",
        "fix": "Add a prompt instruction in `_prompts.py`: 'Paraphrase the fact — never copy >5 "
               "consecutive words verbatim.' Add a post-LLM reject if LCS ratio > 0.6.",
        "affected": "fact_to_question, scenario_synthesis.",
        "test": "A3 fail rate drops below 2% on regenerated batch.",
        "effort": "S",
    },
    "A4_TemplateFingerprint": {
        "name": "Template questions statistically distinguishable from LLM ones",
        "fix": "Diversify template phrasings (rotate opening verbs, add filler, vary punctuation). "
               "If AUC remains high, reduce template share of the final corpus.",
        "affected": "template.",
        "test": "Re-run A4 after template edits; AUC target < 0.85.",
        "effort": "M",
    },
    "B1_TriJudgeAnswer": {
        "name": "Key disagrees with judge consensus / source fact",
        "fix": "Root-cause per example: (a) fact hallucination → tighten 'use ONLY provided fact' "
               "instruction; (b) ambiguous key → add B4 and human review; (c) option swap bug → "
               "audit `_schemas.py` shuffle logic.",
        "affected": "All LLM strategies.",
        "test": "B1 fail rate < 5% in follow-up run; rebuild failing questions.",
        "effort": "L",
    },
    "B2_ClosedBookSolvability": {
        "name": "Question solvable from world knowledge (easy leakage)",
        "fix": "Raise difficulty target for leaking questions; rewrite stems to use provided fact-specific "
               "terminology rather than famous-entity references.",
        "affected": "fact_to_question (most), template.",
        "test": "B2 leakage ratio < 0.5 of judges (5-judge panel: claude/chatgpt/gemini/llama/qwen).",
        "effort": "M",
    },
    "C2_CategoryLeak": {
        "name": "Distractor wine-category mismatch",
        "fix": "Make `_classify_wine_category` mandatory for ALL distractor sampling (not just "
               "distractor_miner); reject mismatched distractors in sampler layer.",
        "affected": "fact_to_question, comparative, scenario_synthesis.",
        "test": "C2 fail count == 0 on regenerated batch.",
        "effort": "S",
    },
    "D1_SelfPreference": {
        "name": "Model scores disproportionately well on its own questions",
        "fix": "Rebalance final dataset so each model's share is capped at 22% (prevent dominance). "
               "Consider dropping the highest-SP model if delta ≥ 0.15.",
        "affected": "Dataset composition.",
        "test": "D1 delta < 0.07 across all 5 evaluators in follow-up run.",
        "effort": "L",
    },
    "D3_SkewAudit": {
        "name": "Geographic or subdomain over-representation",
        "fix": "Add per-country quota to `_fact_sampler.sample_facts`; or sample facts inversely "
               "weighted by country frequency. Reduce Portugal / France over-sampling.",
        "affected": "All strategies.",
        "test": "D3 max over-representation ratio < 1.5.",
        "effort": "M",
    },
}


# Severity→impact weight. Fail is 3× warn.
SEV_WEIGHT = {"fail": 3, "warn": 1, "error": 2, "pass": 0}


def render(run_id: str, out_path: Path) -> None:
    run = get_run(run_id)
    findings = fetch_findings(run_id)
    if not findings:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(f"# Improvement plan\n\nNo findings for run {run_id}.\n", encoding="utf-8")
        return

    # Aggregate per agent
    by_agent: dict[str, Counter] = defaultdict(Counter)
    per_agent_examples: dict[str, list[str]] = defaultdict(list)
    for f in findings:
        by_agent[f["agent_id"]][f["severity"]] += 1
        if f["severity"] in {"fail", "warn"} and f.get("question_id"):
            if len(per_agent_examples[f["agent_id"]]) < 5:
                per_agent_examples[f["agent_id"]].append(str(f["question_id"]))

    ranked = []
    for agent, counts in by_agent.items():
        impact = (
            counts.get("fail", 0) * SEV_WEIGHT["fail"]
            + counts.get("warn", 0) * SEV_WEIGHT["warn"]
            + counts.get("error", 0) * SEV_WEIGHT["error"]
        )
        if impact == 0:
            continue
        info = DEFECT_CATALOGUE.get(agent, {
            "name": agent,
            "fix": "Investigate findings manually.",
            "affected": "unknown",
            "test": "Re-run audit after fix.",
            "effort": "M",
        })
        ranked.append((impact, agent, counts, info))

    ranked.sort(reverse=True)

    lines = ["# OenoBench Generation Improvement Plan", ""]
    lines.append(f"- Run ID: `{run_id}`")
    lines.append(f"- Corpus tag: `{run['corpus_tag']}`")
    lines.append(f"- Generated: {datetime.now().isoformat()}")
    lines.append("")
    lines.append("## Prioritised defects")
    lines.append("")
    lines.append("Ranked by impact = `3·fails + 1·warns + 2·errors`. Effort S ≈ <1d, M ≈ 1-3d, L ≈ 3-7d.")
    lines.append("")

    for impact, agent, counts, info in ranked:
        lines.append(f"### {info['name']}  ·  impact {impact}  ·  effort {info['effort']}")
        lines.append("")
        lines.append(f"- Agent: `{agent}`")
        lines.append(f"- Severity: fail={counts.get('fail', 0)}, warn={counts.get('warn', 0)}, error={counts.get('error', 0)}")
        lines.append(f"- Affected: {info['affected']}")
        lines.append(f"- Proposed fix: {info['fix']}")
        lines.append(f"- Verification: {info['test']}")
        if per_agent_examples[agent]:
            lines.append(f"- Example question UUIDs: " + ", ".join(per_agent_examples[agent]))
        lines.append("")

    lines.append("## Regeneration Go/No-Go checklist")
    lines.append("")
    lines.append("Do NOT start the full 10k generation run until ALL of these hold on the next audit pass:")
    lines.append("")
    lines.append("- [ ] A1 fail rate **< 2%**")
    lines.append("- [ ] A2 position-bias p > 0.2 in every (strategy, generator) cell with n ≥ 20")
    lines.append("- [ ] A3 fail rate **< 2%**, no question with contiguous n-gram ≥ 8 tokens")
    lines.append("- [ ] A4 held-out AUC **< 0.85**")
    lines.append("- [ ] B1 majority-matches-key rate **≥ 95%**, fact-supports ratio ≥ 0.9")
    lines.append("- [ ] B2 closed-book leakage ratio **< 0.5** on Level-3/4 questions")
    lines.append("- [ ] C2 category-leak fail count **= 0**")
    lines.append("- [ ] D1 self-preference |Δ| **< 0.07** across all 5 evaluator models")
    lines.append("- [ ] D3 max country over-representation ratio **< 1.5**")
    lines.append("")
    lines.append("If any box fails twice in a row, escalate to the deferred agents (C1, B3, B4, C3, C4, D2).")
    lines.append("")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines), encoding="utf-8")
