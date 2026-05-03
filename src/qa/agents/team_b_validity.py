"""Team B — Answer Validity (LLM tri-judge panel).

B1 TriJudgeAnswer — each judge reads the question + source fact and picks an
answer, also verifying the claimed key follows from the fact.

B2 ClosedBookSolvability — same three judges answer WITHOUT the source fact.
If too many judges get the keyed answer anyway, the question leaks or is
trivially solvable from world knowledge.

Judges: Claude Opus 4.7, ChatGPT 5.4, Gemini 3.1 Pro.

Phase 2j: outer loop is parallelisable via ``OENOBENCH_AUDIT_MAX_WORKERS``
(default 1 — sequential, the legacy behaviour). With max_workers>=2, each
question is processed in its own thread and findings are written via the
caller-supplied `write_finding_fn` (which must be thread-safe; the
orchestrator's writer + the Phase 2j thread-local psycopg2 conns satisfy
that). At 3,670 questions, max_workers=8 brings the Team B wall time
from ~25h sequential to ~3-4h.
"""

from __future__ import annotations

import concurrent.futures as cf
import os

import orjson
from loguru import logger

from src.qa._findings import SEVERITY_FAIL, SEVERITY_PASS, SEVERITY_WARN
from src.qa._judges import JUDGE_PANEL, judge_open_and_closed


def _resolve_max_workers() -> int:
    """Return the per-question worker count for Team B.

    Reads ``OENOBENCH_AUDIT_MAX_WORKERS`` (positive int). Defaults to 1
    so the legacy sequential path is unchanged when the env var is unset.
    """
    raw = os.environ.get("OENOBENCH_AUDIT_MAX_WORKERS", "").strip()
    if not raw:
        return 1
    try:
        n = int(raw)
        return max(1, n)
    except ValueError:
        logger.warning(
            "OENOBENCH_AUDIT_MAX_WORKERS={!r} is not an int; falling back to 1",
            raw,
        )
        return 1

B1_ID = "B1_TriJudgeAnswer"
B1_VERSION = "v1.0.0"
B2_ID = "B2_ClosedBookSolvability"
B2_VERSION = "v3.2.0"  # Phase 2g.18 cost-down: 4-judge panel (drop chatgpt); thresholds rescaled 5/5→4/4 and ≥4/5→≥3/4


def _coerce_options(q: dict) -> list[dict]:
    opts = q.get("options") or []
    if isinstance(opts, str):
        try:
            return orjson.loads(opts)
        except Exception:
            return []
    return opts


def _concat_source_facts(q: dict) -> str:
    facts = q.get("facts") or []
    if isinstance(facts, str):
        try:
            facts = orjson.loads(facts)
        except Exception:
            facts = []
    if not facts:
        return ""
    lines = []
    for i, f in enumerate(facts, 1):
        src = f.get("source_name") or "source"
        text = f.get("fact_text") or ""
        lines.append(f"[{i}] ({src}) {text}")
    return "\n".join(lines)


def _majority(choices: list[str | None]) -> tuple[str | None, int]:
    """Return (majority_choice, count). None if no majority."""
    vals = [c for c in choices if c]
    if not vals:
        return None, 0
    tally: dict[str, int] = {}
    for v in vals:
        tally[v] = tally.get(v, 0) + 1
    best = max(tally.items(), key=lambda kv: kv[1])
    return best[0], best[1]


def run_team_b(
    run_id: str,
    questions: list[dict],
    *,
    judges: tuple[str, ...] = JUDGE_PANEL,
    skip_existing_checker=None,
    write_finding_fn=None,
) -> list[dict]:
    """Run B1 + B2 on every question. Returns findings for both agents.

    `skip_existing_checker` is an optional callable(q_uuid, agent_id) -> bool
    that returns True when the finding already exists (so we skip the LLM
    call entirely). The orchestrator passes one that queries audit_findings.

    `write_finding_fn` is an optional callable(finding_dict) that writes the
    finding to the DB immediately. Used for incremental writes so the audit
    can be monitored / resumed mid-run instead of batching at completion.
    When supplied, the returned list is empty (everything is already persisted).
    """
    findings: list[dict] = []
    total = len(questions)
    workers = _resolve_max_workers()

    def _emit(f: dict) -> None:
        if write_finding_fn:
            write_finding_fn(f)
        else:
            findings.append(f)

    # Phase 2j: process one question's B1 + B2 work and return its finding
    # dicts. Hoisted out of the for-loop so the parallel path can submit
    # this to a ThreadPoolExecutor; sequential path calls it directly. The
    # function is closure-pure with respect to ``run_id``, ``judges``, and
    # ``skip_existing_checker``; it never touches `findings` / `_emit`.
    def _process_one(q: dict) -> list[dict]:
        qid = q["uuid"]
        if skip_existing_checker and skip_existing_checker(qid, B1_ID) and skip_existing_checker(qid, B2_ID):
            return []

        options = _coerce_options(q)
        if not options:
            return [{
                "run_id": run_id,
                "question_id": qid,
                "agent_id": B1_ID,
                "agent_version": B1_VERSION,
                "severity": SEVERITY_PASS,
                "score": None,
                "payload": {"skipped": "non-MC question (no options)"},
                "llm_calls": 0,
                "cost_usd": 0.0,
            }]

        claimed_key = (q.get("correct_answer") or "").strip().upper()[:1]
        source_text = _concat_source_facts(q)

        try:
            result = judge_open_and_closed(
                question_text=q.get("question_text") or "",
                options=options,
                source_text=source_text,
                claimed_key=claimed_key,
                judges=judges,
            )
        except Exception as exc:  # pragma: no cover — defensive
            logger.error("Team B call failed for {}: {}", qid, exc)
            return [{
                "run_id": run_id,
                "question_id": qid,
                "agent_id": B1_ID,
                "agent_version": B1_VERSION,
                "severity": "error",
                "score": None,
                "payload": {"error": str(exc)},
                "llm_calls": 0,
                "cost_usd": 0.0,
            }]

        local: list[dict] = []

        # ─── B1 — open-book / fact support / cross-judge agreement ────────────
        # Judges are NOT shown the claimed key. We compute "majority_matches_key"
        # by comparing their independent majority choice to the DB key.
        ob_choices = [v.chosen for v in result.open_book]
        ob_majority, ob_count = _majority(ob_choices)
        majority_matches_key = bool(ob_majority and ob_majority == claimed_key)
        fact_supports = [v.fact_supports_choice for v in result.open_book
                         if v.fact_supports_choice is not None]
        fact_supports_count = sum(1 for v in fact_supports if v)
        disagreement = len(set(ob_choices)) > 1
        b1_severity = SEVERITY_PASS
        if not majority_matches_key:
            b1_severity = SEVERITY_FAIL
        elif fact_supports and fact_supports_count < len(fact_supports):
            b1_severity = SEVERITY_WARN
        elif disagreement:
            b1_severity = SEVERITY_WARN

        local.append({
            "run_id": run_id,
            "question_id": qid,
            "agent_id": B1_ID,
            "agent_version": B1_VERSION,
            "severity": b1_severity,
            "score": (ob_count / len(result.open_book)) if result.open_book else None,
            "payload": {
                "claimed_key": claimed_key,
                "open_book_choices": [
                    {"judge": v.judge, "chosen": v.chosen, "confidence": v.confidence,
                     "fact_supports_choice": v.fact_supports_choice,
                     "rationale": v.rationale}
                    for v in result.open_book
                ],
                "majority_choice": ob_majority,
                "majority_matches_key": majority_matches_key,
                "fact_supports_majority_ratio": (
                    round(fact_supports_count / len(fact_supports), 3) if fact_supports else None
                ),
                "judge_disagreement": disagreement,
            },
            "llm_calls": len(result.open_book),
            "cost_usd": sum(v.cost_usd for v in result.open_book),
        })

        # ─── B2 — closed-book solvability (v3.2.0, 4-judge panel rescale) ────
        # Phase 2g.18 cost-down (4-judge panel): unanimous threshold shifts
        # 5/5 → 4/4; warn shifts ≥4/5 → ≥3/4. Mean-conf threshold (0.80)
        # unchanged. Drop the "three expert judges out-vote two proxies"
        # rationale since GPT-5 is no longer in the panel; the surviving
        # expert (Claude-Sonnet via override + Gemini) is now diluted by
        # Llama+Qwen 1:1, which strengthens the calibration anchor.
        #
        # Gold-v3 (n=119) showed v3.0.0 B2 vs human κ = -0.099 on
        # `needs_source` (humans flag ~7%; B2 flagged ~81%). v3.1.0 demanded
        # unanimous (5/5) AND mean-confidence ≥ 0.80 before FAIL at L≤2;
        # v3.2.0 keeps that recipe but rescales to 4/4. At L≥3 the
        # closed-book signal stays informational-only (WARN ceiling) because
        # expert-LLM priors dominate on hard recall questions. See
        # docs/GENERATION_IMPROVEMENT_PLAN.md §5b and
        # docs/GOLD_CALIBRATION_ANALYSIS.md §4.
        #   L ≤ 2:  FAIL iff 4/4 keyed AND mean-conf ≥ 0.80
        #           WARN if ≥3/4 keyed
        #           PASS otherwise
        #   L ≥ 3:  WARN if 4/4 keyed; PASS otherwise (never FAIL on CB alone)
        #
        # Thresholds reference len(cb_choices) rather than hardcoded 4/5 so
        # the same logic survives a future panel-size change.
        cb_choices = [v.chosen for v in result.closed_book]
        cb_majority, cb_count = _majority(cb_choices)
        closed_book_correct = bool(cb_majority and cb_majority == claimed_key)
        difficulty = str(q.get("difficulty") or "1")
        try:
            diff_int = int(difficulty)
        except ValueError:
            diff_int = 1
        n_closed = len(result.closed_book)
        cb_ratio = (cb_count / n_closed) if n_closed else 0.0
        # Counts of judges that picked the keyed answer (regardless of majority)
        cb_keyed_count = sum(1 for c in cb_choices if c == claimed_key)
        # Mean confidence among judges who picked the keyed answer (0.0 if none)
        _keyed_confs = [v.confidence for v in result.closed_book if v.chosen == claimed_key]
        cb_confidence_mean = (sum(_keyed_confs) / len(_keyed_confs)) if _keyed_confs else 0.0
        # Panel-size-relative WARN threshold: ≥(n-1)/n keyed (i.e. 3/4 for the
        # current 4-judge panel; would be 4/5 if reverted to v3.1.0).
        warn_threshold = max(1, n_closed - 1) if n_closed else 0
        if diff_int <= 2:
            if n_closed and cb_keyed_count == n_closed and cb_confidence_mean >= 0.80:
                b2_severity = SEVERITY_FAIL
            elif closed_book_correct and cb_keyed_count >= warn_threshold:
                b2_severity = SEVERITY_WARN
            else:
                b2_severity = SEVERITY_PASS
        else:  # diff_int >= 3 — closed-book signal is informational only
            if n_closed and cb_keyed_count == n_closed:
                b2_severity = SEVERITY_WARN
            else:
                b2_severity = SEVERITY_PASS

        local.append({
            "run_id": run_id,
            "question_id": qid,
            "agent_id": B2_ID,
            "agent_version": B2_VERSION,
            "severity": b2_severity,
            "score": round(cb_ratio, 3),
            "payload": {
                "claimed_key": claimed_key,
                "closed_book_choices": [
                    {"judge": v.judge, "chosen": v.chosen, "confidence": v.confidence,
                     "rationale": v.rationale}
                    for v in result.closed_book
                ],
                "majority_choice": cb_majority,
                "closed_book_correct": closed_book_correct,
                "leakage_ratio": round(cb_ratio, 3),
                "judges_keyed": cb_keyed_count,
                "judges_total": n_closed,
                "cb_confidence_mean": round(cb_confidence_mean, 3),
                "difficulty": difficulty,
            },
            "llm_calls": len(result.closed_book),
            "cost_usd": sum(v.cost_usd for v in result.closed_book),
        })
        return local

    # ─── Dispatch ─────────────────────────────────────────────────────────
    if workers <= 1:
        # Legacy sequential path — bit-identical to pre-Phase-2j behaviour.
        for idx, q in enumerate(questions, 1):
            for f in _process_one(q):
                _emit(f)
            if idx % 10 == 0:
                logger.info("Team B progress: {}/{}", idx, total)
    else:
        # Phase 2j parallel path — outer loop runs `workers` questions in
        # flight at once. Each thread executes _process_one (which makes
        # ~8 sequential LLM calls) and the produced findings are persisted
        # via _emit (which delegates to a thread-safe write_finding_fn).
        logger.info(
            "Team B parallel dispatch: {} workers across {} questions",
            workers, total,
        )
        completed = 0
        with cf.ThreadPoolExecutor(max_workers=workers) as ex:
            futures = {ex.submit(_process_one, q): q for q in questions}
            for fut in cf.as_completed(futures):
                try:
                    for f in fut.result():
                        _emit(f)
                except Exception as exc:  # pragma: no cover — defensive
                    qid = futures[fut].get("uuid", "?")
                    logger.error("Team B parallel cell {} raised: {}", qid, exc)
                completed += 1
                if completed % 25 == 0:
                    logger.info("Team B progress: {}/{}", completed, total)

    if write_finding_fn:
        logger.info("Team B complete: incremental writes finished")
    else:
        logger.info("Team B complete: {} findings", len(findings))
    return findings
