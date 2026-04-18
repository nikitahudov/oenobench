"""Team C — Adversarial probes (MVA: deterministic slice only).

C2 CategoryLeak — detects wine-category mismatches between the correct option
and distractors (e.g. a red-wine question with a sparkling-wine option whose
category is inferable from the stem). Applies to *all* strategies, not just
distractor_mining.

Deferred (not implemented in MVA):
    C1 DistractorDifficulty  — LLM plausibility scoring of each distractor
    C3 SourceSwap            — replace fact with unrelated, re-judge
    C4 DimensionCognitiveAudit — LLM re-classifies dimension/Bloom's/difficulty
"""

from __future__ import annotations

import re

import orjson
from loguru import logger

from src.generators._fact_sampler import _classify_wine_category
from src.qa._findings import SEVERITY_FAIL, SEVERITY_PASS, SEVERITY_WARN

C2_ID = "C2_CategoryLeak"
C2_VERSION = "v1.0.0"

# Question stems that make the wine category directly inferable. If the stem
# literally names a category, a distractor from a different category is a leak.
_STEM_CATEGORY = re.compile(
    r"\b(red wine|white wine|sparkling wine|rosé wine|rose wine|fortified wine|"
    r"dry red|dry white|sweet red|sweet white|dessert wine|port|champagne|prosecco|"
    r"cava|cr[eé]mant)\b",
    re.I,
)


def _options_list(q: dict) -> list[dict]:
    opts = q.get("options") or []
    if isinstance(opts, str):
        try:
            return orjson.loads(opts)
        except Exception:
            return []
    return opts


def _correct_letter(q: dict) -> str:
    return (q.get("correct_answer") or "").strip().upper()[:1]


def run_c2_category_leak(run_id: str, questions: list[dict]) -> list[dict]:
    findings = []
    for q in questions:
        options = _options_list(q)
        if len(options) < 2:
            findings.append({
                "run_id": run_id,
                "question_id": q["uuid"],
                "agent_id": C2_ID,
                "agent_version": C2_VERSION,
                "severity": SEVERITY_PASS,
                "score": None,
                "payload": {"skipped": "< 2 options"},
            })
            continue

        correct = _correct_letter(q)
        correct_text = ""
        distractor_texts: list[tuple[str, str]] = []
        for opt in options:
            oid = (opt.get("id") or "").strip().upper()[:1]
            text = opt.get("text") or ""
            if oid == correct:
                correct_text = text
            else:
                distractor_texts.append((oid, text))

        correct_cat = _classify_wine_category(correct_text)
        qtext = q.get("question_text") or ""
        stem_mentions_cat = bool(_STEM_CATEGORY.search(qtext))

        leaked: list[dict] = []
        for oid, dtext in distractor_texts:
            dcat = _classify_wine_category(dtext)
            if correct_cat and dcat and dcat != correct_cat:
                leaked.append({
                    "option_id": oid,
                    "option_category": dcat,
                    "correct_category": correct_cat,
                    "text": dtext[:160],
                })

        severity = SEVERITY_PASS
        if leaked:
            # If the stem reveals the category, any mismatched distractor is a fail
            # because the test-taker can eliminate it from the stem alone.
            severity = SEVERITY_FAIL if stem_mentions_cat else SEVERITY_WARN

        findings.append({
            "run_id": run_id,
            "question_id": q["uuid"],
            "agent_id": C2_ID,
            "agent_version": C2_VERSION,
            "severity": severity,
            "score": float(len(leaked)),
            "payload": {
                "correct_category": correct_cat,
                "stem_mentions_category": stem_mentions_cat,
                "leaked_distractors": leaked,
            },
        })

    fail_count = sum(1 for f in findings if f["severity"] == SEVERITY_FAIL)
    warn_count = sum(1 for f in findings if f["severity"] == SEVERITY_WARN)
    logger.info("C2: {} fails, {} warns over {} questions", fail_count, warn_count, len(findings))
    return findings


def run_team_c(run_id: str, questions: list[dict]) -> list[dict]:
    return run_c2_category_leak(run_id, questions)
