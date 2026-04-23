"""Team A — Static integrity agents (no LLM, pure analysis).

Covers weakness surfaces:
  #1 vague / marketing language
  #2 blend-as-variety leakage
  #3 thin-geo question wording
  #5 correct-answer position bias
  #6 correct-vs-distractor length bias
  #7 template statistical tells
  #19 verbatim source copying

All four agents are cheap — they run on the full 600-question corpus in
under a minute and never call an LLM.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from typing import Any

import orjson
from loguru import logger

from src.generators._fact_sampler import (
    _BLEND_AS_VARIETY,
    _THIN_GEO_PATTERNS,
    _VAGUE_PATTERNS,
)
from src.qa._findings import SEVERITY_FAIL, SEVERITY_PASS, SEVERITY_WARN
from src.qa._scoring import (
    auc,
    chi_square_uniform,
    feature_vector,
    fit_logreg,
    lcs_ratio,
    longest_common_ngram,
    mann_whitney_u,
    predict_proba,
    tokenize,
)

# ─── A1 — LexicalHygiene ─────────────────────────────────────────────────────

A1_ID = "A1_LexicalHygiene"
A1_VERSION = "v1.0.0"

# Additional patterns beyond `_VAGUE_PATTERNS` — picked to catch phrasings that
# the fact-level filter doesn't look for but that LLM question-writers love.
#
# The audit-side list is intentionally stricter than the generator-side
# (`src/generators/_fact_sampler._VAGUE_PATTERNS`): here we look at the final
# generated question text and can flag phrasings the generator missed.
# v2.3 Team γ — 2026-04-23: extended with 7 gold-sheet-observed phrasings
# (is known for producing, highly prized, distinguished by its, celebrated for,
# notable for, sought-after, one of the most) that were not already covered
# by existing `_VAGUE_PATTERNS` / `_EXTRA_VAGUE` rules. Patterns omitted as
# redundant: `renowned for` (subsumed by `renowned`), `world-class`
# (already `world[- ]class`), `premier` / `prestigious` / `celebrated`
# (already listed as bare tokens).
_EXTRA_VAGUE = re.compile(
    r"\b("
    r"acclaimed|esteemed|storied|legendary|revered|beloved|celebrated|"
    r"signature blend|signature wine|flagship (wine|cuvée|label)|"
    r"the wines of the region|jewel of|crown jewel|"
    r"pride of|heart and soul|unmistakable|quintessential|"
    r"unparalleled|unrivall?ed|world[- ]class|top[- ]tier|premier"
    # ── v2.3 Team γ gold-sheet additions ──
    r"|is known for producing"
    r"|highly prized"
    r"|distinguished by its"
    r"|celebrated for"
    r"|notable for"
    r"|sought[- ]after"
    r"|one of the most"
    r")\b",
    re.IGNORECASE,
)

# A question that merely restates a thin geographic claim is useless even if
# the underlying fact was richer.
_THIN_GEO_Q = re.compile(
    r"^(?:"
    r".{3,80}\s+(is a|was a)\s+(wine[- ]producing\s+)?(region|area|zone|commune|village|town)\s+in.+"
    r"|.{3,80}\s+wine region is located in.+"
    r")\s*\??$",
    re.IGNORECASE,
)


def _scan_text_for_patterns(text: str, *patterns: re.Pattern) -> list[str]:
    hits = []
    for pat in patterns:
        for m in pat.finditer(text or ""):
            hits.append(m.group(0))
    return hits


# v2.2 fix #4 — Short-stem guard. Demonstratives like "this wine" / "these
# wines" are LEGITIMATE in long scenario stems where an antecedent is
# established earlier in the text ("A winemaker is monitoring a Barolo
# vineyard... this wine..."). They are only vague when the stem is too
# short to possibly contain that antecedent. Applied only to question-text
# scanning (not facts or options).
_SHORT_STEM_WORD_THRESHOLD = 15
_DEMONSTRATIVE_HIT = re.compile(
    r"\b(?:this\s+wine|these\s+(?:wines?|bordeaux\s+wines?|grapes?|appellations?|regions?))\b",
    re.IGNORECASE,
)


def _filter_demonstrative_fps(qtext: str, hits: list[str]) -> list[str]:
    """Drop demonstrative hits in long stems where antecedent is presumed set."""
    if not hits:
        return hits
    word_count = len((qtext or "").split())
    if word_count <= _SHORT_STEM_WORD_THRESHOLD:
        return hits  # short stem — keep all hits
    # Long stem — drop hits that are purely demonstrative phrases.
    return [h for h in hits if not _DEMONSTRATIVE_HIT.fullmatch(h.strip())]


def run_a1_lexical_hygiene(run_id: str, questions: list[dict]) -> list[dict]:
    findings = []
    for q in questions:
        qtext = q.get("question_text") or ""
        options = q.get("options") or []
        if isinstance(options, str):
            try:
                options = orjson.loads(options)
            except Exception:
                options = []
        option_texts = [opt.get("text", "") for opt in options]
        explanation = q.get("explanation") or ""

        matched: dict[str, list[str]] = {}
        # Question stem
        q_hits = _scan_text_for_patterns(qtext, _VAGUE_PATTERNS, _EXTRA_VAGUE, _BLEND_AS_VARIETY)
        # v2.2 fix #4 — drop demonstrative hits in long stems with antecedent.
        q_hits = _filter_demonstrative_fps(qtext, q_hits)
        if _THIN_GEO_Q.match(qtext.strip()):
            q_hits.append("(thin-geo question stem)")
        if q_hits:
            matched["question_text"] = q_hits

        # Options and explanation
        for i, opt_text in enumerate(option_texts):
            hits = _scan_text_for_patterns(opt_text, _VAGUE_PATTERNS, _EXTRA_VAGUE, _BLEND_AS_VARIETY)
            if hits:
                matched.setdefault("options", []).append({"idx": i, "hits": hits})
        e_hits = _scan_text_for_patterns(explanation, _VAGUE_PATTERNS, _EXTRA_VAGUE, _BLEND_AS_VARIETY)
        if e_hits:
            matched["explanation"] = e_hits

        if matched:
            severity = SEVERITY_FAIL if "question_text" in matched else SEVERITY_WARN
        else:
            severity = SEVERITY_PASS
        findings.append({
            "run_id": run_id,
            "question_id": q["uuid"],
            "agent_id": A1_ID,
            "agent_version": A1_VERSION,
            "severity": severity,
            "score": float(sum(len(v) if isinstance(v, list) else 1 for v in matched.values())),
            "payload": {"matches": matched},
        })
    logger.info("A1: scanned {} questions, {} fails/warns",
                len(findings), sum(1 for f in findings if f["severity"] != SEVERITY_PASS))
    return findings


# ─── A2 — BiasStats ──────────────────────────────────────────────────────────

A2_ID = "A2_BiasStats"
A2_VERSION = "v1.0.0"


def _correct_option_text(q: dict) -> str | None:
    options = q.get("options") or []
    if isinstance(options, str):
        try:
            options = orjson.loads(options)
        except Exception:
            return None
    key = (q.get("correct_answer") or "").strip().upper()[:1]
    for opt in options:
        if (opt.get("id") or "").strip().upper()[:1] == key:
            return opt.get("text", "")
    return None


def _option_texts(q: dict) -> list[tuple[str, str]]:
    options = q.get("options") or []
    if isinstance(options, str):
        try:
            options = orjson.loads(options)
        except Exception:
            return []
    return [((opt.get("id") or "").strip().upper()[:1], opt.get("text", "")) for opt in options]


def run_a2_bias_stats(run_id: str, questions: list[dict]) -> list[dict]:
    """Population-level findings: χ² on position distribution, MWU on lengths.

    Findings have question_id=None. One row per (strategy) cell plus one row
    for the whole corpus.
    """
    findings: list[dict] = []

    cells: dict[tuple[str, str], list[dict]] = {}
    for q in questions:
        key = (q.get("generation_method") or "unknown", q.get("generator") or "template_only")
        cells.setdefault(key, []).append(q)

    def _one_cell(cell_name: str, items: list[dict]) -> dict:
        position_counter: Counter = Counter()
        correct_lengths: list[float] = []
        distractor_lengths: list[float] = []
        for q in items:
            opts = _option_texts(q)
            if not opts:
                continue
            key = (q.get("correct_answer") or "").strip().upper()[:1]
            position_counter[key] += 1
            for oid, text in opts:
                l = len(text)
                if oid == key:
                    correct_lengths.append(l)
                else:
                    distractor_lengths.append(l)

        # Use only A-D for χ² (true-false is 2-way, separate)
        mc_pos = [position_counter.get(x, 0) for x in ["A", "B", "C", "D"]]
        chi2, p_pos = chi_square_uniform(mc_pos) if sum(mc_pos) >= 20 else (0.0, 1.0)
        u, p_len = mann_whitney_u(correct_lengths, distractor_lengths) if correct_lengths and distractor_lengths else (0.0, 1.0)

        mean_correct = sum(correct_lengths) / len(correct_lengths) if correct_lengths else 0
        mean_distractor = sum(distractor_lengths) / len(distractor_lengths) if distractor_lengths else 0
        length_delta = mean_correct - mean_distractor

        severity = SEVERITY_PASS
        if p_pos < 0.05 and sum(mc_pos) >= 20:
            severity = SEVERITY_FAIL
        elif p_len < 0.01:
            severity = SEVERITY_FAIL
        elif p_len < 0.05 or (abs(length_delta) > 10 and mean_distractor > 0):
            severity = SEVERITY_WARN

        return {
            "cell": cell_name,
            "n_questions": len(items),
            "position_counts": dict(position_counter),
            "mc_ABCD": mc_pos,
            "position_chi2": round(chi2, 3),
            "position_p": round(p_pos, 4),
            "length_mwu_u": round(u, 3),
            "length_p": round(p_len, 4),
            "mean_correct_len": round(mean_correct, 1),
            "mean_distractor_len": round(mean_distractor, 1),
            "length_delta": round(length_delta, 1),
            "severity": severity,
        }

    # Bundle per-cell + corpus into a single finding (one row per agent for
    # population-level signals — the audit_findings unique constraint allows
    # only one population-level row per (run, agent, version)).
    cell_payloads = []
    worst_severity = SEVERITY_PASS
    severity_rank = {SEVERITY_PASS: 0, SEVERITY_WARN: 1, SEVERITY_FAIL: 2, "error": 2}
    for (method, generator), items in sorted(cells.items()):
        cell_name = f"{method}/{generator}"
        cell = _one_cell(cell_name, items)
        cell_payloads.append(cell)
        if severity_rank.get(cell["severity"], 0) > severity_rank.get(worst_severity, 0):
            worst_severity = cell["severity"]
    whole = _one_cell("CORPUS", questions)
    if severity_rank.get(whole["severity"], 0) > severity_rank.get(worst_severity, 0):
        worst_severity = whole["severity"]
    findings.append({
        "run_id": run_id,
        "question_id": None,
        "agent_id": A2_ID,
        "agent_version": A2_VERSION,
        "severity": worst_severity,
        "score": round(min(whole["position_p"], whole["length_p"]), 4),
        "payload": {"corpus": whole, "cells": cell_payloads},
    })
    logger.info("A2: wrote bundled finding for {} cells (+corpus)", len(cells))
    return findings


# ─── A3 — FactEcho ───────────────────────────────────────────────────────────

A3_ID = "A3_FactEcho"
A3_VERSION = "v1.0.0"
_A3_FAIL_LCS = 0.60
_A3_FAIL_NGRAM = 8
_A3_WARN_LCS = 0.40
_A3_WARN_NGRAM = 6


def run_a3_fact_echo(run_id: str, questions: list[dict]) -> list[dict]:
    findings = []
    for q in questions:
        facts = q.get("facts") or []
        if isinstance(facts, str):
            try:
                facts = orjson.loads(facts)
            except Exception:
                facts = []
        qtext = q.get("question_text") or ""
        correct = _correct_option_text(q) or ""
        target = tokenize(f"{qtext} {correct}")

        if not facts or not target:
            findings.append({
                "run_id": run_id,
                "question_id": q["uuid"],
                "agent_id": A3_ID,
                "agent_version": A3_VERSION,
                "severity": SEVERITY_PASS,
                "score": 0.0,
                "payload": {"note": "no source fact linked"},
            })
            continue

        best_ratio = 0.0
        best_ngram = 0
        worst_src = ""
        for f in facts:
            src = tokenize(f.get("fact_text") or "")
            if not src:
                continue
            r = lcs_ratio(target, src)
            n = longest_common_ngram(target, src)
            if r > best_ratio:
                best_ratio = r
                worst_src = f.get("fact_text", "")[:200]
            best_ngram = max(best_ngram, n)

        severity = SEVERITY_PASS
        if best_ratio >= _A3_FAIL_LCS or best_ngram >= _A3_FAIL_NGRAM:
            severity = SEVERITY_FAIL
        elif best_ratio >= _A3_WARN_LCS or best_ngram >= _A3_WARN_NGRAM:
            severity = SEVERITY_WARN

        findings.append({
            "run_id": run_id,
            "question_id": q["uuid"],
            "agent_id": A3_ID,
            "agent_version": A3_VERSION,
            "severity": severity,
            "score": round(best_ratio, 4),
            "payload": {
                "lcs_ratio": round(best_ratio, 4),
                "longest_ngram": best_ngram,
                "worst_source_snippet": worst_src,
            },
        })
    logger.info("A3: echo analysis complete over {} questions", len(findings))
    return findings


# ─── A4 — TemplateFingerprint ────────────────────────────────────────────────

A4_ID = "A4_TemplateFingerprint"
A4_VERSION = "v1.0.0"


def run_a4_template_fingerprint(run_id: str, questions: list[dict]) -> list[dict]:
    """Train a tiny logreg to separate template from LLM questions, then flag
    LLM questions scoring >= 0.7 template-likeness.

    Population-level finding summarises AUC; per-question findings flag the
    LLM questions that scored template-like.
    """
    tmpl = [q for q in questions if (q.get("generation_method") == "template")]
    llm = [q for q in questions if (q.get("generation_method") != "template")]

    if len(tmpl) < 20 or len(llm) < 20:
        return [{
            "run_id": run_id,
            "question_id": None,
            "agent_id": A4_ID,
            "agent_version": A4_VERSION,
            "severity": SEVERITY_PASS,
            "score": 0.0,
            "payload": {"note": "not enough data to train classifier",
                        "n_template": len(tmpl), "n_llm": len(llm)},
        }]

    feats = [feature_vector(q.get("question_text") or "") for q in tmpl + llm]
    labels = [1] * len(tmpl) + [0] * len(llm)

    # Train/test split 70/30 with interleaving so both classes are present
    pairs = list(zip(feats, labels, tmpl + llm))
    # Deterministic shuffle via (hash-by-position) — we already set seed upstream
    import random
    random.Random(123).shuffle(pairs)
    cut = int(len(pairs) * 0.7)
    train = pairs[:cut]
    test = pairs[cut:]

    w, b = fit_logreg([p[0] for p in train], [p[1] for p in train])
    y_true = [p[1] for p in test]
    y_score = [predict_proba(w, b, p[0]) for p in test]
    test_auc = auc(y_true, y_score)

    # Top 10 discriminative features by absolute weight
    top_feats = sorted(w.items(), key=lambda kv: -abs(kv[1]))[:10]

    # Per-question: score every *LLM-authored* question and flag the top tail
    per_q_findings: list[dict] = []
    for feat, _, q in pairs:
        if q.get("generation_method") == "template":
            continue
        score = predict_proba(w, b, feat)
        if score >= 0.7:
            sev = SEVERITY_WARN if score < 0.85 else SEVERITY_FAIL
            per_q_findings.append({
                "run_id": run_id,
                "question_id": q["uuid"],
                "agent_id": A4_ID,
                "agent_version": A4_VERSION,
                "severity": sev,
                "score": round(score, 3),
                "payload": {"template_likeness": round(score, 3)},
            })

    # Population-level summary
    sev_pop = SEVERITY_PASS
    if test_auc >= 0.95:
        sev_pop = SEVERITY_FAIL
    elif test_auc >= 0.85:
        sev_pop = SEVERITY_WARN
    pop = {
        "run_id": run_id,
        "question_id": None,
        "agent_id": A4_ID,
        "agent_version": A4_VERSION,
        "severity": sev_pop,
        "score": round(test_auc, 4),
        "payload": {
            "test_auc": round(test_auc, 4),
            "top_features": top_feats,
            "n_train": len(train),
            "n_test": len(test),
            "n_flagged_llm": len(per_q_findings),
        },
    }
    logger.info("A4: AUC={:.3f}, flagged {} LLM qs template-like", test_auc, len(per_q_findings))
    return [pop, *per_q_findings]


# ─── Team runner ──────────────────────────────────────────────────────────────

ALL_A_AGENTS = {
    A1_ID: A1_VERSION,
    A2_ID: A2_VERSION,
    A3_ID: A3_VERSION,
    A4_ID: A4_VERSION,
}


def run_team_a(run_id: str, questions: list[dict]) -> list[dict]:
    out: list[dict] = []
    out += run_a1_lexical_hygiene(run_id, questions)
    out += run_a2_bias_stats(run_id, questions)
    out += run_a3_fact_echo(run_id, questions)
    out += run_a4_template_fingerprint(run_id, questions)
    return out
