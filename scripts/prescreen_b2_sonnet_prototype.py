"""Prototype v3: Sonnet 4.6 second-stage gate.

Run Sonnet 4.6 closed-book on every L1/L2 audit_pilot_v4 question, then join
with the existing Haiku results to compare:
    - Haiku alone
    - Sonnet alone
    - Haiku OR Sonnet (union gate — what we'd actually deploy)
"""

from __future__ import annotations

import csv
import difflib
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

SONNET_MODEL = "anthropic/claude-sonnet-4.6"
RUN_ID = "4e3ead78-2b62-4733-919d-bf3f4878aaec"
HAIKU_CSV = Path("data/reports/prescreen_b2_question_prototype.csv")
OUT_CSV = Path("data/reports/prescreen_b2_sonnet_prototype.csv")
WORKERS = 6

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
    SELECT q.id::text AS uuid, q.question_id AS qid, q.difficulty,
           q.question_text, q.correct_answer_text, q.correct_answer
    FROM questions q
    WHERE q.tags && ARRAY['audit_pilot_v4']
      AND q.difficulty IN ('1', '2');
    """
    conn = get_pg()
    with conn.cursor() as cur:
        cur.execute(sql)
        return [dict(r) for r in cur.fetchall()]


def fetch_b2() -> dict[str, str]:
    sql = """
    SELECT q.id::text AS uuid, f.severity::text AS severity
    FROM audit_findings f
    JOIN questions q ON q.id = f.question_id
    WHERE f.run_id = %s
      AND f.agent_id = 'B2_ClosedBookSolvability'
      AND q.difficulty IN ('1','2')
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
    h, g = normalize(haiku_ans), normalize(gold)
    if not h or not g:
        return False, 0.0
    if g in h or h in g:
        return True, 1.0
    ratio = difflib.SequenceMatcher(None, h, g).ratio()
    return ratio >= 0.75, ratio


def call_sonnet(client: openai.OpenAI, stem: str) -> dict:
    msg = PROMPT.format(stem=stem)
    t0 = time.time()
    try:
        resp = client.chat.completions.create(
            model=SONNET_MODEL,
            messages=[{"role": "user", "content": msg}],
            temperature=0.1,
            max_tokens=500,
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
    r = call_sonnet(client, q["question_text"])
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
        ans = str(p.get("answer", ""))
        conf = float(p.get("confidence", 0.0) or 0.0)
        matched, sim = answer_match(ans, out["gold"])
        out.update({
            "sonnet_answer": ans,
            "sonnet_confidence": conf,
            "sonnet_reasoning": str(p.get("reasoning", "")),
            "matched": matched,
            "similarity": round(sim, 3),
        })
    else:
        out.update({"sonnet_answer": "", "sonnet_confidence": None,
                    "matched": None, "similarity": None,
                    "error": r.get("error") or "json_parse_failed"})
    return out


def load_haiku_results() -> dict[str, dict]:
    out = {}
    with HAIKU_CSV.open() as fh:
        for r in csv.DictReader(fh):
            out[r["uuid"]] = {
                "haiku_matched": r["matched"] == "True",
                "haiku_confidence": float(r["haiku_confidence"]) if r["haiku_confidence"] else 0.0,
            }
    return out


def gate_stats(label: str, gate_fn, results, b2):
    fl_f = fl_w = fl_p = cl_f = cl_w = cl_p = 0
    for r in results:
        sev = b2.get(r["uuid"])
        if sev is None or r["matched"] is None:
            continue
        if gate_fn(r):
            if sev == "fail":
                fl_f += 1
            elif sev == "warn":
                fl_w += 1
            else:
                fl_p += 1
        else:
            if sev == "fail":
                cl_f += 1
            elif sev == "warn":
                cl_w += 1
            else:
                cl_p += 1
    flagged = fl_f + fl_w + fl_p
    clean = cl_f + cl_w + cl_p
    print(
        f"  {label:<35}  flagged: {fl_f}f {fl_w}w {fl_p}p  ({100*fl_f/max(flagged,1):.0f}% fail, n={flagged})  "
        f"|  clean: {cl_f}f {cl_w}w {cl_p}p  ({100*cl_f/max(clean,1):.0f}% fail, n={clean})  "
        f"|  precision={100*fl_f/max(flagged,1):.0f}%  recall={100*fl_f/max(fl_f+cl_f,1):.0f}%"
    )


def main():
    api_key = os.environ["OPENROUTER_API_KEY"]
    client = openai.OpenAI(api_key=api_key, base_url="https://openrouter.ai/api/v1")

    print("[1/3] Fetching v4 L1/L2 questions ...", flush=True)
    qs = fetch_questions()
    b2 = fetch_b2()
    print(f"      {len(qs)} questions, {len(b2)} have B2 verdict", flush=True)

    print(f"[2/3] Running Sonnet closed-book with {WORKERS} workers ...", flush=True)
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
    cost = in_tok * 3.0 / 1_000_000 + out_tok * 15.0 / 1_000_000
    parsed = sum(1 for r in results if r["matched"] is not None)
    matched = sum(1 for r in results if r["matched"] is True)
    print(
        f"      tokens in={in_tok} out={out_tok}  est_cost=${cost:.3f}  "
        f"parse_ok={parsed}/{len(results)}  sonnet_matched_gold={matched}",
        flush=True,
    )

    print("[3/3] Comparing gates ...", flush=True)
    haiku = load_haiku_results()
    # Merge haiku verdict into result rows for combined gates
    for r in results:
        h = haiku.get(r["uuid"], {"haiku_matched": False, "haiku_confidence": 0.0})
        r["haiku_matched"] = h["haiku_matched"]
        r["haiku_confidence"] = h["haiku_confidence"]

    print()
    gate_stats(
        "Haiku conf>=0.7",
        lambda r: r["haiku_matched"] and r["haiku_confidence"] >= 0.7,
        results, b2,
    )
    gate_stats(
        "Sonnet conf>=0.7",
        lambda r: bool(r["matched"]) and (r["sonnet_confidence"] or 0) >= 0.7,
        results, b2,
    )
    gate_stats(
        "Sonnet conf>=0.5",
        lambda r: bool(r["matched"]) and (r["sonnet_confidence"] or 0) >= 0.5,
        results, b2,
    )
    gate_stats(
        "Sonnet conf>=0.0 (any match)",
        lambda r: bool(r["matched"]),
        results, b2,
    )
    gate_stats(
        "UNION Haiku>=0.7 OR Sonnet>=0.7",
        lambda r: (r["haiku_matched"] and r["haiku_confidence"] >= 0.7)
                  or (bool(r["matched"]) and (r["sonnet_confidence"] or 0) >= 0.7),
        results, b2,
    )
    gate_stats(
        "UNION Haiku>=0.7 OR Sonnet>=0.5",
        lambda r: (r["haiku_matched"] and r["haiku_confidence"] >= 0.7)
                  or (bool(r["matched"]) and (r["sonnet_confidence"] or 0) >= 0.5),
        results, b2,
    )
    gate_stats(
        "UNION Haiku>=0.5 OR Sonnet>=0.5",
        lambda r: (r["haiku_matched"] and r["haiku_confidence"] >= 0.5)
                  or (bool(r["matched"]) and (r["sonnet_confidence"] or 0) >= 0.5),
        results, b2,
    )

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "uuid", "qid", "difficulty", "stem", "gold",
        "sonnet_answer", "sonnet_confidence", "sonnet_reasoning",
        "matched", "similarity", "haiku_matched", "haiku_confidence",
        "b2_severity", "ok", "latency_ms", "input_tokens", "output_tokens", "error",
    ]
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
