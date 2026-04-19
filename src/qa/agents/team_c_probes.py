"""Team C — Adversarial probes.

C2 CategoryLeak — detects wine-category mismatches between the correct option
and distractors (e.g. a red-wine question with a sparkling-wine option whose
category is inferable from the stem). Applies to *all* strategies, not just
distractor_mining.

C4 DifficultyAudit — single Gemini call per question that re-rates the question
difficulty 1–4; flags mismatches against the assigned label (warn = ±1 level,
fail = ≥2 levels). Promoted from deferred status per `docs/GENERATION_IMPROVEMENT_PLAN.md` §7.

Deferred (still not implemented):
    C1 DistractorDifficulty  — LLM plausibility scoring of each distractor
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
C2_VERSION = "v1.0.0"

C4_ID = "C4_DifficultyAudit"
C4_VERSION = "v1.0.0"

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

    def _emit(f: dict) -> None:
        if write_finding_fn:
            write_finding_fn(f)
        else:
            findings.append(f)

    pass_n = warn_n = fail_n = error_n = 0
    for idx, q in enumerate(questions, 1):
        qid = q["uuid"]
        if skip_existing_checker and skip_existing_checker(qid, C4_ID):
            continue

        assigned = _coerce_difficulty(q.get("difficulty"))
        options = _options_list(q)
        if assigned is None:
            _emit({
                "run_id": run_id,
                "question_id": qid,
                "agent_id": C4_ID,
                "agent_version": C4_VERSION,
                "severity": SEVERITY_PASS,
                "score": None,
                "payload": {"skipped": "no parseable difficulty label"},
                "llm_calls": 0,
                "cost_usd": 0.0,
            })
            continue

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
            _emit({
                "run_id": run_id,
                "question_id": qid,
                "agent_id": C4_ID,
                "agent_version": C4_VERSION,
                "severity": SEVERITY_ERROR,
                "score": None,
                "payload": {"error": str(exc)},
                "llm_calls": 0,
                "cost_usd": 0.0,
            })
            error_n += 1
            continue

        if rated is None:
            _emit({
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
            })
            error_n += 1
            continue

        delta = abs(rated - assigned)
        if delta == 0:
            severity = SEVERITY_PASS
            pass_n += 1
        elif delta == 1:
            severity = SEVERITY_WARN
            warn_n += 1
        else:
            severity = SEVERITY_FAIL
            fail_n += 1

        _emit({
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
        })

        if idx % 25 == 0:
            logger.info("C4 progress: {}/{}  (pass={} warn={} fail={} err={})",
                        idx, total, pass_n, warn_n, fail_n, error_n)

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
