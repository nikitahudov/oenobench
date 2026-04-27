"""Team D — Population-level agents.

D1 SelfPreference — each generator model answers a balanced sample of
audited questions; we estimate whether a model performs better on questions
it authored than on questions authored by other models.

D3 SkewAudit (stats-only) — pure-SQL geographic + domain distribution checks
against the source fact base. Cultural-framing LLM slice is deferred.
"""

from __future__ import annotations

import random
from collections import defaultdict
from typing import Iterable

import orjson
from loguru import logger

from src.generators._llm_client import GENERATOR_MODELS
from src.qa._findings import SEVERITY_FAIL, SEVERITY_PASS, SEVERITY_WARN
from src.qa._judges import self_pref_answer
from src.qa._scoring import chi_square_uniform
from src.utils.db import get_pg

D1_ID = "D1_SelfPreference"
D1_VERSION = "v1.0.0"
D3_ID = "D3_SkewAudit"
D3_VERSION = "v1.1.0"  # 2026-04-27 Phase 2g.9 — coverage guard on max_overrep_ratio

# When fewer than this fraction of audited questions carry a country-tagged
# fact, max_overrep_ratio is computed against a tiny denominator and overstates
# the true skew (audit #7 reported 10.61× from 16/242 country-tagged questions
# while the actual ratio over all 242 was ~2.5×). Below this coverage we
# downgrade severity to WARN and surface the coverage as the headline signal.
COUNTRY_COVERAGE_MIN = 0.5


def _options_list(q: dict) -> list[dict]:
    opts = q.get("options") or []
    if isinstance(opts, str):
        try:
            return orjson.loads(opts)
        except Exception:
            return []
    return opts


# ─── D1 — SelfPreference ─────────────────────────────────────────────────────


def run_d1_self_preference(
    run_id: str,
    questions: list[dict],
    *,
    sample_per_generator: int = 20,
    seed: int = 42,
    models: Iterable[str] | None = None,
) -> list[dict]:
    """Have each model answer a balanced sample and measure own-author advantage.

    Sampling protocol: for each (evaluator_model, author_model) pair, present
    `sample_per_generator` questions authored by `author_model`. This gives a
    `n_models × n_models` matrix of accuracies from which own-vs-other
    differences are computed.
    """
    rng = random.Random(seed)
    models = list(models or GENERATOR_MODELS.keys())

    # Bucket questions by author (skip templates — no authoring model)
    by_author: dict[str, list[dict]] = defaultdict(list)
    for q in questions:
        gen = q.get("generator")
        if gen and gen in models:
            by_author[gen].append(q)

    # Prepare the evaluation set: per (evaluator, author), sample N
    # We evaluate each question once per evaluator to keep cost linear.
    # Build a flat list of (evaluator, author, question, options).
    plan: list[tuple[str, str, dict]] = []
    for evaluator in models:
        for author, items in by_author.items():
            if not items:
                continue
            picks = rng.sample(items, k=min(sample_per_generator, len(items)))
            for q in picks:
                plan.append((evaluator, author, q))

    if not plan:
        return [{
            "run_id": run_id,
            "question_id": None,
            "agent_id": D1_ID,
            "agent_version": D1_VERSION,
            "severity": SEVERITY_PASS,
            "score": None,
            "payload": {"note": "no authored questions found for any model"},
        }]

    logger.info("D1: running {} evaluator×author×question evaluations", len(plan))

    # Run calls
    acc_matrix: dict[tuple[str, str], dict] = {}  # (evaluator, author) -> {correct, total}
    total_cost = 0.0
    total_calls = 0
    for evaluator, author, q in plan:
        options = _options_list(q)
        if not options:
            continue
        claimed_key = (q.get("correct_answer") or "").strip().upper()[:1]
        try:
            verdict = self_pref_answer(
                question_text=q.get("question_text") or "",
                options=options,
                model_short=evaluator,
            )
        except Exception as exc:
            logger.error("D1 call failed {}:{} {}", evaluator, q["uuid"], exc)
            continue
        total_cost += verdict.cost_usd
        total_calls += 1
        bucket = acc_matrix.setdefault((evaluator, author), {"correct": 0, "total": 0, "cost": 0.0})
        bucket["total"] += 1
        bucket["cost"] += verdict.cost_usd
        if verdict.chosen == claimed_key:
            bucket["correct"] += 1

    # Compute per-model own-vs-other (bundled into ONE finding per agent —
    # audit_findings unique constraint allows only one population-level row).
    summary_rows = []
    worst_severity = SEVERITY_PASS
    sev_rank = {SEVERITY_PASS: 0, SEVERITY_WARN: 1, SEVERITY_FAIL: 2, "error": 2}
    max_delta = 0.0
    for evaluator in models:
        per_author = {}
        for author in models:
            if (evaluator, author) in acc_matrix:
                b = acc_matrix[(evaluator, author)]
                acc = (b["correct"] / b["total"]) if b["total"] else None
                per_author[author] = {"acc": acc, "n": b["total"]}
        own = per_author.get(evaluator, {}).get("acc")
        others_scores = [v["acc"] for a, v in per_author.items() if a != evaluator and v["acc"] is not None]
        others_mean = sum(others_scores) / len(others_scores) if others_scores else None
        delta = (own - others_mean) if (own is not None and others_mean is not None) else None
        sev = SEVERITY_PASS
        if delta is not None and delta >= 0.15:
            sev = SEVERITY_FAIL
        elif delta is not None and delta >= 0.07:
            sev = SEVERITY_WARN
        if sev_rank.get(sev, 0) > sev_rank.get(worst_severity, 0):
            worst_severity = sev
        if delta is not None and abs(delta) > max_delta:
            max_delta = abs(delta)
        summary_rows.append({
            "evaluator": evaluator,
            "per_author_accuracy": per_author,
            "own_accuracy": own,
            "others_mean_accuracy": others_mean,
            "self_pref_delta": round(delta, 4) if delta is not None else None,
            "severity": sev,
        })

    findings: list[dict] = [{
        "run_id": run_id,
        "question_id": None,
        "agent_id": D1_ID,
        "agent_version": D1_VERSION,
        "severity": worst_severity,
        "score": round(max_delta, 4),
        "payload": {
            "n_calls": total_calls,
            "total_cost_usd": round(total_cost, 4),
            "matrix": {f"{ev}->{au}": b for (ev, au), b in acc_matrix.items()},
            "per_evaluator": summary_rows,
        },
        "llm_calls": total_calls,
        "cost_usd": round(total_cost, 4),
    }]
    return findings


# ─── D3 — SkewAudit (stats-only) ─────────────────────────────────────────────


def _extract_country_from_entities(entities_json) -> str | None:
    if entities_json is None:
        return None
    if isinstance(entities_json, str):
        try:
            entities_json = orjson.loads(entities_json)
        except Exception:
            return None
    if not isinstance(entities_json, list):
        return None
    for ent in entities_json:
        if not isinstance(ent, dict):
            continue
        t = (ent.get("type") or "").lower()
        name = ent.get("name") or ent.get("value")
        if t == "country" and name:
            return name
    return None


def run_d3_skew_audit(run_id: str, questions: list[dict]) -> list[dict]:
    """Compare country + domain distribution of the audit corpus against the
    source facts base.

    - Country distribution: χ² of question-linked fact countries vs full
      fact-base country distribution.
    - Domain distribution: questions per domain vs DOMAIN_TARGETS (strategy
      target mix).
    """
    conn = get_pg()
    cur = conn.cursor()

    # Fact-base country distribution
    cur.execute(
        """
        SELECT  entities
        FROM    facts
        """
    )
    fact_countries: dict[str, int] = defaultdict(int)
    for row in cur.fetchall():
        c = _extract_country_from_entities(row["entities"])
        if c:
            fact_countries[c] += 1

    # Question-linked country distribution
    qids = [q["uuid"] for q in questions]
    q_countries: dict[str, int] = defaultdict(int)
    if qids:
        cur.execute(
            """
            SELECT  f.entities
            FROM    question_facts qf
            JOIN    facts f ON f.id = qf.fact_id
            WHERE   qf.question_id = ANY(%s::uuid[])
            """,
            (qids,),
        )
        for row in cur.fetchall():
            c = _extract_country_from_entities(row["entities"])
            if c:
                q_countries[c] += 1

    # Restrict to top-20 fact-base countries for the χ²
    top_countries = sorted(fact_countries.items(), key=lambda kv: -kv[1])[:20]
    country_labels = [c for c, _ in top_countries]
    observed = [q_countries.get(c, 0) for c in country_labels]
    expected_share = [
        fact_countries[c] / max(sum(fact_countries.values()), 1) for c in country_labels
    ]
    total_q = sum(observed) or 1
    expected = [max(round(e * total_q), 1) for e in expected_share]
    chi2, p = chi_square_uniform(observed) if sum(observed) > 0 else (0.0, 1.0)

    # Per-strategy domain mix
    domain_counter: dict[tuple[str, str], int] = defaultdict(int)
    for q in questions:
        domain_counter[(q.get("generation_method") or "unknown", q.get("domain") or "unknown")] += 1

    # Herfindahl index for subdomains within each strategy
    sub_counter: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for q in questions:
        sub_counter[q.get("generation_method") or "unknown"][q.get("subdomain") or "none"] += 1
    herfindahl: dict[str, float] = {}
    for method, subs in sub_counter.items():
        total = sum(subs.values())
        if total == 0:
            herfindahl[method] = 0.0
            continue
        herfindahl[method] = round(sum((c / total) ** 2 for c in subs.values()), 4)

    severity = SEVERITY_PASS
    max_ratio = 0.0
    for c, obs in zip(country_labels, observed):
        if expected_share[country_labels.index(c)] == 0:
            continue
        ratio = (obs / total_q) / expected_share[country_labels.index(c)]
        max_ratio = max(max_ratio, ratio)
    if max_ratio >= 1.5 or any(h >= 0.5 for h in herfindahl.values()):
        severity = SEVERITY_WARN
    if max_ratio >= 2.0:
        severity = SEVERITY_FAIL

    # Coverage guard (Phase 2g.9): when most questions lack a country tag,
    # max_overrep_ratio inflates against a tiny denominator. Audit #7 had
    # 16/242 country-tagged questions and reported 10.61× — but the metric
    # is inactionable when the denominator is that thin. Downgrade to WARN
    # and let the reviewer see the coverage value alongside the ratio.
    total_questions = max(len(questions), 1)
    country_coverage = total_q / total_questions if observed else 0.0
    coverage_sufficient = country_coverage >= COUNTRY_COVERAGE_MIN
    if not coverage_sufficient and severity == SEVERITY_FAIL:
        severity = SEVERITY_WARN

    finding = {
        "run_id": run_id,
        "question_id": None,
        "agent_id": D3_ID,
        "agent_version": D3_VERSION,
        "severity": severity,
        "score": round(max_ratio, 3),
        "payload": {
            "fact_base_top20": dict(top_countries),
            "question_country_counts": dict(sorted(q_countries.items(), key=lambda kv: -kv[1])[:20]),
            "chi2": round(chi2, 3),
            "p": round(p, 4),
            "max_overrep_ratio": round(max_ratio, 3),
            "country_annotation_coverage": round(country_coverage, 3),
            "country_coverage_sufficient": coverage_sufficient,
            "country_coverage_threshold": COUNTRY_COVERAGE_MIN,
            "country_tagged_questions": int(total_q) if observed else 0,
            "total_questions": int(total_questions),
            "domain_by_strategy": {f"{m}/{d}": c for (m, d), c in domain_counter.items()},
            "subdomain_herfindahl_by_strategy": herfindahl,
        },
    }
    if coverage_sufficient:
        logger.info("D3: max country over-representation ratio = {:.2f}", max_ratio)
    else:
        logger.warning(
            "D3: country annotation coverage {:.1%} (< {:.0%} threshold); "
            "max_overrep_ratio={:.2f} downgraded — denominator too sparse",
            country_coverage, COUNTRY_COVERAGE_MIN, max_ratio,
        )
    return [finding]


def run_team_d(run_id: str, questions: list[dict], *, seed: int = 42, d1_sample: int = 20) -> list[dict]:
    out: list[dict] = []
    out += run_d1_self_preference(run_id, questions, sample_per_generator=d1_sample, seed=seed)
    out += run_d3_skew_audit(run_id, questions)
    return out
