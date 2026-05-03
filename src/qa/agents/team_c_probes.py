"""Team C — Adversarial probes.

C2 CategoryLeak — detects **wine-category distractor leaks only**
(red vs white vs sparkling vs rosé / fortified mismatches between the correct
option and its distractors, e.g. a red-wine question with a sparkling-wine
distractor whose category is inferable from the stem). C2 does NOT measure
full distractor plausibility — the human rubric `distractors_plausible` is
broader, covering semantic plausibility and eliminability beyond wine
category.  Mapped to the narrower `wine_category_leak` audit-report rubric
(v2.3 Team γ, 2026-04-23). Applies to *all* strategies, not just
distractor_mining.

C4 DifficultyAudit — single Gemini call per question that re-rates the question
difficulty 1–4; flags mismatches against the assigned label (warn = ±1 level,
fail = ≥2 levels). Promoted from deferred status per `docs/GENERATION_IMPROVEMENT_PLAN.md` §7.

Deferred (still not implemented):
    C1 DistractorDifficulty  — LLM plausibility scoring of each distractor
                               (the signal needed for full `distractors_plausible`)
    C3 SourceSwap            — replace fact with unrelated, re-judge
"""

from __future__ import annotations

import hashlib
import re

import orjson
from loguru import logger

from src.generators._fact_sampler import _classify_wine_category
from src.generators._llm_client import GENERATOR_MODELS, get_client
from src.qa._findings import (
    SEVERITY_ERROR,
    SEVERITY_FAIL,
    SEVERITY_PASS,
    SEVERITY_WARN,
)
from src.qa._prompts import C4_SYSTEM, C4_TEMPLATE, render_options

C2_ID = "C2_CategoryLeak"
C2_VERSION = "v1.1.0"  # v2.3 Team γ — narrative rename to wine_category_leak (no logic change)
# Payload tag: which human rubric this agent's signal corresponds to. Read
# by `src.qa.reports.build_audit_report` when rendering the gold-calibration
# table. `wine_category_leak` is a strict subset of the broader human rubric
# `distractors_plausible`; treat this as a necessary-but-not-sufficient proxy.
_C2_RUBRIC_MEASURED = "wine_category_leak"

C4_ID = "C4_DifficultyAudit"
C4_VERSION = "v1.2.0"  # v2.3 fix #16 — gold-v3 calibration refresh + rubric anchored to observable properties

# ─── Gold-v3 calibration harvest (v2.3 fix #16) ──────────────────────────────
#
# These cases were extracted from the gold-v3 human review
# (data/reports/gold_sheet_v3_scored.csv, 2026-04-22). Each case represents a
# question where the labelled difficulty diverged from the human-rated actual
# difficulty, with the direction recorded in `notes`.
#
# The bulk of mislabels are L2→L3 ("too easy by one") and L3→L2 ("too hard by
# one"); these are the failure modes the existing gen-time C4 gate (delta ≥ 2)
# does not catch. The new level-aware threshold in
# `src/generators/_schemas.py` rejects L3/L4 questions at delta ≥ 1.
#
# The few-shot examples in `C4_SYSTEM` below are a curated subset of these
# cases; the rest act as silent calibration that the rewritten rubric text
# embeds indirectly (observable-property anchors for each level).

_C4_GOLD_V3_FEWSHOT: list[dict] = [
    # ── Too-easy mislabels (labelled < actual): 7 cases ───────────────────
    {
        "uuid": "b4c3d2e1-0000-0000-0000-000000000003",
        "question": (
            "Cautín, a small wine-producing zone with only a few hectares under "
            "vine, is located at the far southern end of Chile. Within which broad "
            "Chilean viticultural region does it fall?"
        ),
        "options": [
            {"id": "A", "text": "Aconcagua"},
            {"id": "B", "text": "Austral"},
            {"id": "C", "text": "Central Valley"},
            {"id": "D", "text": "Coquimbo"},
        ],
        "correct_answer": "B",
        "labelled": 2,
        "actual": 3,
        "reasoning": (
            "Cautín is a tiny obscure Chilean zone well beyond textbook recall; "
            "fits advanced study rather than simple grape-region pairing at L2."
        ),
    },
    {
        "uuid": "b4c3d2e1-0000-0000-0000-000000000004",
        "question": (
            "A viticulture student compares two vineyard sites. Site 1 sits on a "
            "broad, level stretch of freely draining gravel between two mountain "
            "ranges. Site 2 shows mixed parent material from altered granite and "
            "marine sedimentary rocks. Which AVAs match the two sites?"
        ),
        "options": [
            {"id": "A", "text": "Site 1 = Oakville AVA; Site 2 = Paso Robles AVA"},
            {"id": "B", "text": "Both Site 1 and Site 2 = Oakville AVA"},
            {"id": "C", "text": "Site 1 = Paso Robles AVA; Site 2 = Oakville AVA"},
            {"id": "D", "text": "Both Site 1 and Site 2 = Paso Robles AVA"},
        ],
        "correct_answer": "A",
        "labelled": 2,
        "actual": 3,
        "reasoning": (
            "Requires inferring AVA identity from two soil descriptions and pairing "
            "them — two-step inference beyond a single grape-region fact."
        ),
    },
    {
        "uuid": "b4c3d2e1-0000-0000-0000-000000000005",
        "question": (
            "A winemaker in New Jersey's Outer Coastal Plain is evaluating whether "
            "to expand plantings of a red grape that has recently emerged as a "
            "notable success in that AVA. Which proposal should they pursue?"
        ),
        "options": [
            {"id": "A", "text": "Blaufränkisch as a newly created NJ specialty"},
            {"id": "B", "text": "Blaufränkisch — strong performer in the Outer Coastal Plain"},
            {"id": "C", "text": "Do not proceed with Blaufränkisch"},
            {"id": "D", "text": "Proceed with Blaufränkisch emphasizing AVA success"},
        ],
        "correct_answer": "D",
        "labelled": 2,
        "actual": 3,
        "reasoning": (
            "Obscure AVA + obscure Central-European grape; requires specialist "
            "knowledge of an emerging New Jersey varietal story, not textbook recall."
        ),
    },
    {
        "uuid": "b4c3d2e1-0000-0000-0000-000000000007",
        "question": (
            "A golden-skinned white grape variety capable of producing both dry "
            "table wines and lusciously sweet botrytized wines has its two most "
            "significant plantings in which pair of countries?"
        ),
        "options": [
            {"id": "A", "text": "France and Australia"},
            {"id": "B", "text": "Italy and Argentina"},
            {"id": "C", "text": "France and South Africa"},
            {"id": "D", "text": "Spain and Chile"},
        ],
        "correct_answer": "A",
        "labelled": 2,
        "actual": 3,
        "reasoning": (
            "Grape identified by three-feature description (colour, dry-sweet "
            "versatility, botrytis); requires inference + planting knowledge of "
            "Sémillon, beyond L2 recall."
        ),
    },
    {
        "uuid": "b4c3d2e1-0000-0000-0000-000000000008",
        "question": (
            "A European producer wants to go beyond mandatory labeling. The "
            "marketing director proposes tactile braille dots, a scannable "
            "graphic, and reverse-label content. Which assessment is correct?"
        ),
        "options": [
            {"id": "A", "text": "All three are optional; tactile follows the Chapoutier precedent"},
            {"id": "B", "text": "Tactile + scannable optional; reverse label legally required"},
            {"id": "C", "text": "Only scannable optional; tactile now mandatory EU-wide"},
            {"id": "D", "text": "All three must be approved in official label registration"},
        ],
        "correct_answer": "A",
        "labelled": 2,
        "actual": 3,
        "reasoning": (
            "Requires applying EU labelling rules to three concrete proposals — "
            "multi-step application of regulation that exceeds simple recall."
        ),
    },
    {
        "uuid": "b4c3d2e1-0000-0000-0000-000000000011",
        "question": (
            "Which of the following best describes the elevation range for "
            "vineyards producing a high-altitude sparkling wine in northern "
            "Italy, known for some of the world's upper-limit vineyard sites?"
        ),
        "options": [
            {"id": "A", "text": "500 to 1,200 meters above sea level"},
            {"id": "B", "text": "300 to 700 meters above sea level"},
            {"id": "C", "text": "200 to 900 meters above sea level"},
            {"id": "D", "text": "100 to 500 meters above sea level"},
        ],
        "correct_answer": "C",
        "labelled": 2,
        "actual": 3,
        "reasoning": (
            "Specific elevation numbers for Trentodoc are specialist viticultural "
            "detail, not L2 recall of a textbook grape-region pairing."
        ),
    },
    {
        "uuid": "b4c3d2e1-0000-0000-0000-000000000014",
        "question": (
            "A vineyard manager is reviewing planting compliance for two California "
            "estates: Estate X in Clarksburg AVA, Estate Y in Rutherford. Which "
            "varieties are permitted for each?"
        ),
        "options": [
            {"id": "A", "text": "Estate X: Sauvignon Blanc / Estate Y: Zinfandel"},
            {"id": "B", "text": "Estate X: Cabernet Franc / Estate Y: Chenin Blanc"},
            {"id": "C", "text": "Estate X: Pinot Noir / Estate Y: Syrah"},
            {"id": "D", "text": "Estate X: Chenin Blanc / Estate Y: Cabernet Franc"},
        ],
        "correct_answer": "D",
        "labelled": 2,
        "actual": 3,
        "reasoning": (
            "Paired AVA-variety compliance lookup over two AVAs demands specific "
            "appellation knowledge beyond a single grape-region recall."
        ),
    },
    # ── Too-hard mislabels (labelled > actual): 7 cases ───────────────────
    {
        "uuid": "b4c3d2e1-0000-0000-0000-000000000001",
        "question": (
            "Which certification system is exclusive to wines produced within a "
            "specific country, ensuring only domestically made wines can receive "
            "its official quality designation?"
        ),
        "options": [
            {"id": "A", "text": "European Union wine regulations"},
            {"id": "B", "text": "Vintners Quality Alliance (VQA)"},
            {"id": "C", "text": "Denominación de Origen"},
            {"id": "D", "text": "Appellation d'origine contrôlée (AOC)"},
        ],
        "correct_answer": "B",
        "labelled": 4,
        "actual": 3,
        "reasoning": (
            "VQA is a notable national scheme any advanced study covers; L3 fits "
            "better than expert-tier L4, which is reserved for niche/obscure terms."
        ),
    },
    {
        "uuid": "b4c3d2e1-0000-0000-0000-000000000002",
        "question": "True or False: Château Marquis de Terme is located in the Margaux wine region.",
        "options": [
            {"id": "A", "text": "True"},
            {"id": "B", "text": "False"},
        ],
        "correct_answer": "A",
        "labelled": 3,
        "actual": 2,
        "reasoning": (
            "Binary True/False on a classed-growth château-to-appellation mapping; "
            "this is intermediate recall (L2), not advanced study."
        ),
    },
    {
        "uuid": "b4c3d2e1-0000-0000-0000-000000000006",
        "question": (
            "This federal entity came into existence in January 2003 following a "
            "restructuring of the Bureau of Alcohol, Tobacco and Firearms. Which "
            "entity is it?"
        ),
        "options": [
            {"id": "A", "text": "Alcohol and Tobacco Tax and Trade Bureau (TTB)"},
            {"id": "B", "text": "Federal Alcohol Administration (FAA)"},
            {"id": "C", "text": "Wine Institute Regulatory Division"},
            {"id": "D", "text": "Bureau of Alcohol, Tobacco, Firearms and Explosives (ATF)"},
        ],
        "correct_answer": "A",
        "labelled": 3,
        "actual": 2,
        "reasoning": (
            "TTB is named in standard US wine-law curricula; recognising it from a "
            "clear date + origin clue is L2 recall, not advanced study."
        ),
    },
    {
        "uuid": "b4c3d2e1-0000-0000-0000-000000000009",
        "question": (
            "Which grape variety has strains that can produce berries in shades "
            "of pink or reddish brown, despite being technically classified as a "
            "white grape?"
        ),
        "options": [
            {"id": "A", "text": "Nama"},
            {"id": "B", "text": "Xinomavro"},
            {"id": "C", "text": "Malvasia"},
            {"id": "D", "text": "Muscat Blanc à Petits Grains"},
        ],
        "correct_answer": "D",
        "labelled": 4,
        "actual": 3,
        "reasoning": (
            "Muscat Blanc à Petits Grains pink strains appear in standard advanced "
            "curricula; L3 fits rather than the L4 expert/obscure tier."
        ),
    },
    {
        "uuid": "b4c3d2e1-0000-0000-0000-000000000010",
        "question": (
            "A New Zealand winemaker is drafting the back-label story for a small "
            "family cellar in Wairarapa. Which positioning best reflects the "
            "country's current quality image?"
        ),
        "options": [
            {"id": "A", "text": "NZ reputation driven by large-scale wineries across all regions"},
            {"id": "B", "text": "NZ best wines increasingly from small artisanal estates"},
            {"id": "C", "text": "Hawke's Bay lacks deep history; boutique recognition sparse"},
            {"id": "D", "text": "Wairarapa hosts the country's largest wineries"},
        ],
        "correct_answer": "B",
        "labelled": 4,
        "actual": 3,
        "reasoning": (
            "Choosing the best NZ quality narrative is an L3 judgement call using "
            "advanced country knowledge, not expert-level niche detail (L4)."
        ),
    },
    {
        "uuid": "b4c3d2e1-0000-0000-0000-000000000012",
        "question": "True or False: Château Sociando-Mallet is located in the Domaine Andron wine region.",
        "options": [
            {"id": "A", "text": "True"},
            {"id": "B", "text": "False"},
        ],
        "correct_answer": "A",
        "labelled": 3,
        "actual": 2,
        "reasoning": (
            "Binary True/False on a Bordeaux estate location mapping; recall-level "
            "check on a named property, fits L2 rather than L3 advanced study."
        ),
    },
    {
        "uuid": "b4c3d2e1-0000-0000-0000-000000000013",
        "question": (
            "A winemaker is selecting a grape variety suitable for a vineyard "
            "located in an AVA known for permitting Bordeaux red varieties but "
            "not Rhône white varieties. Which grape is the winemaker more likely "
            "to select?"
        ),
        "options": [
            {"id": "A", "text": "Marsanne"},
            {"id": "B", "text": "Viognier"},
            {"id": "C", "text": "Merlot"},
            {"id": "D", "text": "Petit Verdot"},
        ],
        "correct_answer": "C",
        "labelled": 3,
        "actual": 2,
        "reasoning": (
            "Bordeaux-red vs Rhône-white is a canonical taxonomy students learn "
            "early; picking Merlot is L2 application, not advanced study."
        ),
    },
]

# Single high-quality, low-cost judge model. Gemini was the lowest-cost of the
# three high-capability judges in the gold review and the user-favoured model
# for difficulty rating.
C4_JUDGE_MODEL = "gemini"

# Rough OpenRouter pricing (mirrors src.qa._judges._PRICING). Used only for
# a cost ledger column in the finding payload; not billing-critical.
_C4_PRICING = {
    "claude": (3.0, 15.0),
    "chatgpt": (2.5, 12.0),
    "gemini": (1.25, 10.0),
    "llama": (0.50, 1.50),
    "qwen": (0.30, 1.20),
}

# Question stems that make the wine category directly inferable. If the stem
# literally names a category, a distractor from a different category is a leak.
_STEM_CATEGORY = re.compile(
    r"\b(red wine|white wine|sparkling wine|rosé wine|rose wine|fortified wine|"
    r"dry red|dry white|sweet red|sweet white|dessert wine|port|champagne|prosecco|"
    r"cava|cr[eé]mant)\b",
    re.I,
)


def _options_list(q: dict) -> list[dict]:
    """Coerce a question's `options` field into a list of dicts. Tolerates
    both already-parsed lists and raw JSON strings.
    """
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
                "payload": {
                    "skipped": "< 2 options",
                    "rubric_measured": _C2_RUBRIC_MEASURED,
                },
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
                "rubric_measured": _C2_RUBRIC_MEASURED,
            },
        })

    fail_count = sum(1 for f in findings if f["severity"] == SEVERITY_FAIL)
    warn_count = sum(1 for f in findings if f["severity"] == SEVERITY_WARN)
    logger.info("C2: {} fails, {} warns over {} questions", fail_count, warn_count, len(findings))
    return findings


def _c4_estimate_cost(model_short: str, input_tokens: int, output_tokens: int) -> float:
    in_cost, out_cost = _C4_PRICING.get(model_short, (1.0, 5.0))
    return (input_tokens / 1_000_000) * in_cost + (output_tokens / 1_000_000) * out_cost


def _c4_prompt_hash(prompt: str, system: str, model: str) -> str:
    h = hashlib.sha256()
    h.update(system.encode())
    h.update(b"\n---\n")
    h.update(prompt.encode())
    h.update(b"\n---\n")
    h.update(model.encode())
    return h.hexdigest()[:16]


def _coerce_difficulty(value) -> int | None:
    """Coerce a difficulty-like value (int, str, 'L2', etc.) into an int 1-4."""
    if value is None:
        return None
    if isinstance(value, int):
        return value if 1 <= value <= 4 else None
    s = str(value).strip().upper().lstrip("L")
    if not s:
        return None
    try:
        n = int(s[:1])
    except ValueError:
        return None
    return n if 1 <= n <= 4 else None


def _c4_call_llm(
    *,
    question_text: str,
    options: list[dict],
    correct_answer: str,
    model_short: str = C4_JUDGE_MODEL,
) -> tuple[int | None, str, dict]:
    """One LLM call for C4. Returns (rated_difficulty, rationale, meta_dict).

    `meta_dict` carries: prompt_hash, llm_calls (always 1 here), cost_usd,
    error (None on success), raw (truncated response text).
    """
    options_block = render_options(options)
    prompt = C4_TEMPLATE.format(
        question_text=question_text or "",
        options_block=options_block,
        correct_answer=correct_answer or "",
    )
    client = get_client()
    # Gemini 3.1 Pro consumes ~300 tokens on internal reasoning before
    # producing the visible JSON. Need a large ceiling so the actual
    # JSON body still fits.
    response = client.generate(
        prompt=prompt,
        system=C4_SYSTEM,
        model=model_short,
        temperature=0.0,
        max_tokens=1500,
        json_mode=True,
    )
    meta = {
        "prompt_hash": _c4_prompt_hash(prompt, C4_SYSTEM, model_short),
        "llm_calls": 1,
        "cost_usd": _c4_estimate_cost(
            model_short, response.input_tokens, response.output_tokens
        ),
        "error": response.error,
        "raw": (response.content or "")[:500],
        "judge_model": model_short,
    }
    if not response.success:
        return None, "", meta
    parsed = response.parsed or {}
    rated = _coerce_difficulty(parsed.get("difficulty"))
    rationale = str(parsed.get("rationale", ""))[:300]
    return rated, rationale, meta


def run_c4_difficulty_audit(
    run_id: str,
    questions: list[dict],
    *,
    judge_model: str = C4_JUDGE_MODEL,
    skip_existing_checker=None,
    write_finding_fn=None,
    call_llm_fn=None,
) -> list[dict]:
    """C4 — re-rate question difficulty via a single Gemini call per question.

    Severity logic:
      pass — rated == assigned
      warn — |rated - assigned| == 1
      fail — |rated - assigned| >= 2

    `skip_existing_checker(qid, agent_id)` — optional callable that returns
    True when the finding already exists; used to skip re-calling the LLM.

    `write_finding_fn(finding)` — optional callable for inline writes
    (mirrors the Team B pattern so progress is monitorable / resumable).
    When supplied, the returned list is empty.

    `call_llm_fn` — DI hook for tests (signature: keyword args matching
    `_c4_call_llm`; defaults to the live LLM client).
    """
    if call_llm_fn is None:
        call_llm_fn = _c4_call_llm
    if judge_model not in GENERATOR_MODELS:
        logger.warning(
            "C4 judge model {} not in GENERATOR_MODELS; falling back to {}",
            judge_model, C4_JUDGE_MODEL,
        )
        judge_model = C4_JUDGE_MODEL

    findings: list[dict] = []
    total = len(questions)

    # Phase 2j: same parallelisation pattern as Team B —
    # OENOBENCH_AUDIT_MAX_WORKERS gates the outer loop. Default 1 keeps the
    # sequential legacy path bit-identical.
    import concurrent.futures as cf
    import os
    raw = os.environ.get("OENOBENCH_AUDIT_MAX_WORKERS", "").strip()
    try:
        workers = max(1, int(raw)) if raw else 1
    except ValueError:
        workers = 1

    def _emit(f: dict) -> None:
        if write_finding_fn:
            write_finding_fn(f)
        else:
            findings.append(f)

    def _process_one(q: dict) -> tuple[list[dict], str]:
        """Return (findings_list, outcome_tag) for stats accounting.

        outcome_tag is one of: 'skip', 'pass', 'warn', 'fail', 'error'.
        Closure-pure with respect to run_id, judge_model, call_llm_fn, and
        skip_existing_checker.
        """
        qid = q["uuid"]
        if skip_existing_checker and skip_existing_checker(qid, C4_ID):
            return [], "skip"

        assigned = _coerce_difficulty(q.get("difficulty"))
        options = _options_list(q)
        if assigned is None:
            return [{
                "run_id": run_id,
                "question_id": qid,
                "agent_id": C4_ID,
                "agent_version": C4_VERSION,
                "severity": SEVERITY_PASS,
                "score": None,
                "payload": {"skipped": "no parseable difficulty label"},
                "llm_calls": 0,
                "cost_usd": 0.0,
            }], "pass"

        try:
            rated, rationale, meta = call_llm_fn(
                question_text=q.get("question_text") or "",
                options=options,
                correct_answer=(q.get("correct_answer_text")
                                or q.get("correct_answer")
                                or ""),
                model_short=judge_model,
            )
        except Exception as exc:  # pragma: no cover — defensive
            logger.error("C4 call failed for {}: {}", qid, exc)
            return [{
                "run_id": run_id,
                "question_id": qid,
                "agent_id": C4_ID,
                "agent_version": C4_VERSION,
                "severity": SEVERITY_ERROR,
                "score": None,
                "payload": {"error": str(exc)},
                "llm_calls": 0,
                "cost_usd": 0.0,
            }], "error"

        if rated is None:
            return [{
                "run_id": run_id,
                "question_id": qid,
                "agent_id": C4_ID,
                "agent_version": C4_VERSION,
                "severity": SEVERITY_ERROR,
                "score": None,
                "payload": {
                    "error": meta.get("error") or "LLM did not return a rateable difficulty",
                    "raw": meta.get("raw", ""),
                    "judge_model": meta.get("judge_model"),
                    "prompt_hash": meta.get("prompt_hash"),
                },
                "llm_calls": meta.get("llm_calls", 1),
                "cost_usd": meta.get("cost_usd", 0.0),
            }], "error"

        delta = abs(rated - assigned)
        if delta == 0:
            severity = SEVERITY_PASS
            tag = "pass"
        elif delta == 1:
            severity = SEVERITY_WARN
            tag = "warn"
        else:
            severity = SEVERITY_FAIL
            tag = "fail"

        return [{
            "run_id": run_id,
            "question_id": qid,
            "agent_id": C4_ID,
            "agent_version": C4_VERSION,
            "severity": severity,
            "score": float(delta),
            "payload": {
                "assigned_difficulty": assigned,
                "rated_difficulty": rated,
                "delta": delta,
                "rationale": rationale,
                "judge_model": meta.get("judge_model"),
                "prompt_hash": meta.get("prompt_hash"),
            },
            "llm_calls": meta.get("llm_calls", 1),
            "cost_usd": meta.get("cost_usd", 0.0),
        }], tag

    pass_n = warn_n = fail_n = error_n = 0

    if workers <= 1:
        for idx, q in enumerate(questions, 1):
            fs, tag = _process_one(q)
            for f in fs:
                _emit(f)
            if tag == "pass":
                pass_n += 1
            elif tag == "warn":
                warn_n += 1
            elif tag == "fail":
                fail_n += 1
            elif tag == "error":
                error_n += 1
            if idx % 25 == 0:
                logger.info("C4 progress: {}/{}  (pass={} warn={} fail={} err={})",
                            idx, total, pass_n, warn_n, fail_n, error_n)
    else:
        logger.info(
            "C4 parallel dispatch: {} workers across {} questions",
            workers, total,
        )
        completed = 0
        with cf.ThreadPoolExecutor(max_workers=workers) as ex:
            futures = {ex.submit(_process_one, q): q for q in questions}
            for fut in cf.as_completed(futures):
                try:
                    fs, tag = fut.result()
                    for f in fs:
                        _emit(f)
                    if tag == "pass":
                        pass_n += 1
                    elif tag == "warn":
                        warn_n += 1
                    elif tag == "fail":
                        fail_n += 1
                    elif tag == "error":
                        error_n += 1
                except Exception as exc:  # pragma: no cover — defensive
                    qid = futures[fut].get("uuid", "?")
                    logger.error("C4 parallel cell {} raised: {}", qid, exc)
                completed += 1
                if completed % 50 == 0:
                    logger.info(
                        "C4 progress: {}/{}  (pass={} warn={} fail={} err={})",
                        completed, total, pass_n, warn_n, fail_n, error_n,
                    )

    if write_finding_fn:
        logger.info(
            "C4 complete (incremental): pass={} warn={} fail={} err={} of {}",
            pass_n, warn_n, fail_n, error_n, total,
        )
    else:
        logger.info(
            "C4 complete: {} findings (pass={} warn={} fail={} err={})",
            len(findings), pass_n, warn_n, fail_n, error_n,
        )
    return findings


def run_team_c(run_id: str, questions: list[dict], *, include_c4: bool = False) -> list[dict]:
    """Run all default Team C agents over the corpus.

    By default only C2 (deterministic, cheap) is run. Pass `include_c4=True`
    to also run the LLM-based difficulty re-classifier; that path costs a
    Gemini call per question (~$0.001 each) and is gated behind a CLI flag.
    """
    findings = run_c2_category_leak(run_id, questions)
    if include_c4:
        findings.extend(run_c4_difficulty_audit(run_id, questions))
    return findings
