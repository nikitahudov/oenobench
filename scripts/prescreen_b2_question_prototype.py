"""Prototype v2: closed-book pre-screen on the QUESTION STEM (not the fact).

For each L1/L2 audit_pilot_v4 question, ask Haiku 4.5 to answer the stem
without the fact and without options. If Haiku produces the gold answer
with confidence >= threshold, the question is leaking world knowledge.

Cross-tab Haiku verdict against the 5-judge B2 finding.
"""

from __future__ import annotations

import csv
import difflib
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import openai
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.generators._llm_client import _try_parse_json  # noqa: E402
from src.utils.db import get_pg  # noqa: E402

load_dotenv()

HAIKU_MODEL = "anthropic/claude-haiku-4.5"
RUN_ID = "4e3ead78-2b62-4733-919d-bf3f4878aaec"
OUT_CSV = Path("data/reports/prescreen_b2_question_prototype.csv")
WORKERS = 8

PROMPT = """You are taking a closed-book wine knowledge test. Answer the question using ONLY your general training knowledge — no external sources, no provided facts.

QUESTION: {stem}

Respond with ONLY a JSON object:
{{
  "answer": "your best-guess answer in plain text",
  "confidence": 0.0-1.0,
  "reasoning": "one sentence on how you arrived at the answer"
}}

If you genuinely don't know, set confidence < 0.5 and explain why."""


def fetch_questions() -> list[dict]:
    sql = """
    SELECT
        q.id::text AS uuid,
        q.question_id AS qid,
        q.difficulty,
        q.question_text,
        q.correct_answer_text,
        q.correct_answer
    FROM questions q
    WHERE q.tags && ARRAY['audit_pilot_v4']
      AND q.difficulty IN ('1', '2');
    """
    conn = get_pg()
    with conn.cursor() as cur:
        cur.execute(sql)
        return [dict(row) for row in cur.fetchall()]


def fetch_b2() -> dict[str, str]:
    sql = """
    SELECT q.id::text AS uuid, f.severity::text AS severity
    FROM audit_findings f
    JOIN questions q ON q.id = f.question_id
    WHERE f.run_id = %s
      AND f.agent_id = 'B2_ClosedBookSolvability'
      AND q.difficulty IN ('1', '2')
      AND q.tags && ARRAY['audit_pilot_v4'];
    """
    conn = get_pg()
    with conn.cursor() as cur:
        cur.execute(sql, (RUN_ID,))
        return {r["uuid"]: r["severity"] for r in cur.fetchall()}


_NORMALIZE = re.compile(r"[^a-z0-9 ]")


def normalize(s: str) -> str:
    return _NORMALIZE.sub(" ", (s or "").lower()).strip()


def answer_match(haiku_ans: str, gold: str) -> tuple[bool, float]:
    """Return (matched, similarity_ratio)."""
    h, g = normalize(haiku_ans), normalize(gold)
    if not h or not g:
        return False, 0.0
    if g in h or h in g:
        return True, 1.0
    ratio = difflib.SequenceMatcher(None, h, g).ratio()
    return ratio >= 0.75, ratio


def call_haiku(client: openai.OpenAI, stem: str) -> dict:
    msg = PROMPT.format(stem=stem)
    t0 = time.time()
    try:
        resp = client.chat.completions.create(
            model=HAIKU_MODEL,
            messages=[{"role": "user", "content": msg}],
            temperature=0.1,
            max_tokens=400,
            response_format={"type": "json_object"},
        )
        latency_ms = int((time.time() - t0) * 1000)
        content = resp.choices[0].message.content or ""
        return {
            "ok": True,
            "parsed": _try_parse_json(content),
            "latency_ms": latency_ms,
            "input_tokens": resp.usage.prompt_tokens if resp.usage else 0,
            "output_tokens": resp.usage.completion_tokens if resp.usage else 0,
        }
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e), "latency_ms": int((time.time() - t0) * 1000)}


def screen_one(client, q: dict) -> dict:
    r = call_haiku(client, q["question_text"])
    out = {
        "uuid": q["uuid"],
        "qid": q["qid"],
        "difficulty": q["difficulty"],
        "stem": q["question_text"],
        "gold": q["correct_answer_text"] or q["correct_answer"],
        "ok": r["ok"],
        "latency_ms": r["latency_ms"],
        "input_tokens": r.get("input_tokens", 0),
        "output_tokens": r.get("output_tokens", 0),
    }
    if r["ok"] and r["parsed"]:
        p = r["parsed"]
        out["haiku_answer"] = str(p.get("answer", ""))
        out["haiku_confidence"] = float(p.get("confidence", 0.0) or 0.0)
        out["haiku_reasoning"] = str(p.get("reasoning", ""))
        matched, ratio = answer_match(out["haiku_answer"], out["gold"])
        out["matched"] = matched
        out["similarity"] = round(ratio, 3)
    else:
        out["haiku_answer"] = ""
        out["haiku_confidence"] = None
        out["matched"] = None
        out["similarity"] = None
        out["error"] = r.get("error") or "json_parse_failed"
    return out


def main():
    api_key = os.environ["OPENROUTER_API_KEY"]
    client = openai.OpenAI(api_key=api_key, base_url="https://openrouter.ai/api/v1")

    print("[1/3] Fetching v4 L1/L2 questions ...", flush=True)
    qs = fetch_questions()
    b2 = fetch_b2()
    print(f"      {len(qs)} questions, {len(b2)} have B2 verdict", flush=True)

    print(f"[2/3] Running Haiku closed-book with {WORKERS} workers ...", flush=True)
    results: list[dict] = []
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = {pool.submit(screen_one, client, q): q for q in qs}
        for i, fut in enumerate(as_completed(futures), 1):
            results.append(fut.result())
            if i % 25 == 0:
                e = time.time() - t0
                rate = i / e
                eta = (len(qs) - i) / rate
                print(f"      {i}/{len(qs)}  rate={rate:.1f}/s  eta={eta:.0f}s", flush=True)
    print(f"      done in {time.time() - t0:.1f}s", flush=True)

    in_tok = sum(r.get("input_tokens", 0) or 0 for r in results)
    out_tok = sum(r.get("output_tokens", 0) or 0 for r in results)
    cost = in_tok * 1.0 / 1_000_000 + out_tok * 5.0 / 1_000_000
    parsed = sum(1 for r in results if r["matched"] is not None)
    matched = sum(1 for r in results if r["matched"] is True)
    print(
        f"      tokens in={in_tok} out={out_tok}  est_cost=${cost:.3f}  "
        f"parse_ok={parsed}/{len(results)}  haiku_matched_gold={matched}",
        flush=True,
    )

    print("[3/3] Cross-tabulating vs B2 ...", flush=True)
    # Try several confidence thresholds
    for conf_thresh in (0.0, 0.5, 0.7, 0.8):
        flagged_fail = flagged_warn = flagged_pass = 0
        clean_fail = clean_warn = clean_pass = 0
        for r in results:
            sev = b2.get(r["uuid"])
            if sev is None or r["matched"] is None:
                continue
            haiku_solves = bool(r["matched"]) and (r["haiku_confidence"] or 0) >= conf_thresh
            if haiku_solves:
                if sev == "fail":
                    flagged_fail += 1
                elif sev == "warn":
                    flagged_warn += 1
                else:
                    flagged_pass += 1
            else:
                if sev == "fail":
                    clean_fail += 1
                elif sev == "warn":
                    clean_warn += 1
                else:
                    clean_pass += 1
        flagged_total = flagged_fail + flagged_warn + flagged_pass
        clean_total = clean_fail + clean_warn + clean_pass
        n = flagged_total + clean_total
        print(
            f"\n  conf>={conf_thresh}  ({n} judged)  "
            f"|  flagged: {flagged_fail}f {flagged_warn}w {flagged_pass}p  "
            f"({100*flagged_fail/max(flagged_total,1):.0f}% fail, n={flagged_total})  "
            f"|  clean: {clean_fail}f {clean_warn}w {clean_pass}p  "
            f"({100*clean_fail/max(clean_total,1):.0f}% fail, n={clean_total})"
        )

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "uuid", "qid", "difficulty", "stem", "gold",
        "haiku_answer", "haiku_confidence", "haiku_reasoning",
        "matched", "similarity", "ok", "latency_ms",
        "input_tokens", "output_tokens", "error",
    ]
    with OUT_CSV.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for r in results:
            r_with_b2 = {**r, "b2_severity": b2.get(r["uuid"], "")}
            w.writerow(r_with_b2)
    # Re-write with b2 col added properly
    fieldnames.append("b2_severity")
    with OUT_CSV.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for r in results:
            row = dict(r)
            row["b2_severity"] = b2.get(r["uuid"], "")
            w.writerow(row)
    print(f"\nwrote {OUT_CSV}")


if __name__ == "__main__":
    main()
