"""Team B — Answer Validity (LLM tri-judge panel).

B1 TriJudgeAnswer — each judge reads the question + source fact and picks an
answer, also verifying the claimed key follows from the fact.

B2 ClosedBookSolvability — same three judges answer WITHOUT the source fact.
If too many judges get the keyed answer anyway, the question leaks or is
trivially solvable from world knowledge.

Judges: Claude Opus 4.7, ChatGPT 5.4, Gemini 3.1 Pro.
"""

from __future__ import annotations

import orjson
from loguru import logger

from src.qa._findings import SEVERITY_FAIL, SEVERITY_PASS, SEVERITY_WARN
from src.qa._judges import JUDGE_PANEL, judge_open_and_closed

B1_ID = "B1_TriJudgeAnswer"
B1_VERSION = "v1.0.0"
B2_ID = "B2_ClosedBookSolvability"
B2_VERSION = "v3.1.0"  # gold-v3 κ recalibration: unanimous + high-conf FAIL at L≤2; L≥3 WARN-max


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

    def _emit(f: dict) -> None:
        if write_finding_fn:
            write_finding_fn(f)
        else:
            findings.append(f)

    for idx, q in enumerate(questions, 1):
        qid = q["uuid"]
        if skip_existing_checker and skip_existing_checker(qid, B1_ID) and skip_existing_checker(qid, B2_ID):
            continue

        options = _coerce_options(q)
        if not options:
            _emit({
                "run_id": run_id,
                "question_id": qid,
                "agent_id": B1_ID,
                "agent_version": B1_VERSION,
                "severity": SEVERITY_PASS,
                "score": None,
                "payload": {"skipped": "non-MC question (no options)"},
                "llm_calls": 0,
                "cost_usd": 0.0,
            })
            continue

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
            _emit({
                "run_id": run_id,
                "question_id": qid,
                "agent_id": B1_ID,
                "agent_version": B1_VERSION,
                "severity": "error",
                "score": None,
                "payload": {"error": str(exc)},
                "llm_calls": 0,
                "cost_usd": 0.0,
            })
            continue

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

        _emit({
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

        # ─── B2 — closed-book solvability (v3.1.0, gold-v3 κ recalibration) ──
        # Gold-v3 (n=119) showed v3.0.0 B2 vs human κ = -0.099 on `needs_source`
        # (humans flag ~7%; B2 flagged ~81%). Root cause: the wider 5-judge
        # panel (Claude/GPT/Gemini/Llama/Qwen) with a ≥4/5 threshold lets the
        # three expert judges out-vote the two proxy judges on textbook
        # trivia. v3.1.0 demands unanimous (5/5) AND mean-confidence ≥ 0.80
        # among keyed judges before FAIL at L≤2; at L≥3 the closed-book
        # signal is demoted to informational-only (WARN ceiling) because
        # expert-LLM priors dominate on hard recall questions. See
        # docs/GENERATION_IMPROVEMENT_PLAN.md §5b and
        # docs/GOLD_CALIBRATION_ANALYSIS.md §4.
        #   L ≤ 2:  FAIL iff 5/5 keyed AND mean-conf ≥ 0.80
        #           WARN if ≥4/5 keyed
        #           PASS otherwise
        #   L ≥ 3:  WARN if 5/5 keyed; PASS otherwise (never FAIL on CB alone)
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
        if diff_int <= 2:
            if n_closed and cb_keyed_count == n_closed and cb_confidence_mean >= 0.80:
                b2_severity = SEVERITY_FAIL
            elif closed_book_correct and cb_keyed_count >= 4:
                b2_severity = SEVERITY_WARN
            else:
                b2_severity = SEVERITY_PASS
        else:  # diff_int >= 3 — closed-book signal is informational only
            if n_closed and cb_keyed_count == n_closed:
                b2_severity = SEVERITY_WARN
            else:
                b2_severity = SEVERITY_PASS

        _emit({
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

        if idx % 10 == 0:
            logger.info("Team B progress: {}/{}", idx, total)

    if write_finding_fn:
        logger.info("Team B complete: incremental writes finished")
    else:
        logger.info("Team B complete: {} findings", len(findings))
    return findings
