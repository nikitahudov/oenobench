"""Prototype v4: closed-book MC pre-screen.

Same as v3 but presents options to the gate model (matching how B2 evaluates).
Tests Haiku 4.5 and Sonnet 4.6, both with options. Reports gates and unions.
"""

from __future__ import annotations

import csv
import json
import os
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

HAIKU = "anthropic/claude-haiku-4.5"
SONNET = "anthropic/claude-sonnet-4.6"
RUN_ID = "4e3ead78-2b62-4733-919d-bf3f4878aaec"
OUT_CSV = Path("data/reports/prescreen_b2_mc_prototype.csv")
WORKERS = 8

PROMPT = """You are taking a closed-book multiple-choice wine knowledge test. Pick the best answer using ONLY your general training knowledge — no external sources, no provided context facts.

QUESTION: {stem}

OPTIONS:
{options_block}

Respond with ONLY a JSON object:
{{
  "selected": "A" | "B" | "C" | "D",
  "confidence": 0.0-1.0,
  "reasoning": "one sentence on why"
}}

If you genuinely don't know, set confidence < 0.5 and pick your best guess."""


def fetch_questions() -> list[dict]:
    sql = """
    SELECT q.id::text AS uuid, q.question_id AS qid, q.difficulty,
           q.question_text, q.options, q.correct_answer
    FROM questions q
    WHERE q.tags && ARRAY['audit_pilot_v4']
      AND q.difficulty IN ('1','2');
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


def options_block(options) -> str:
    """Render options as 'A. text\\nB. text...'."""
    if isinstance(options, str):
        try:
            options = json.loads(options)
        except (json.JSONDecodeError, ValueError):
            return options
    if not options:
        return ""
    lines = []
    for opt in options:
        if isinstance(opt, dict):
            lines.append(f"{opt.get('id', '?')}. {opt.get('text', '')}")
        else:
            lines.append(str(opt))
    return "\n".join(lines)


def call_model(client, model_id, stem, opts) -> dict:
    msg = PROMPT.format(stem=stem, options_block=opts)
    t0 = time.time()
    try:
        resp = client.chat.completions.create(
            model=model_id,
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
    opts = options_block(q["options"])
    out = {
        "uuid": q["uuid"],
        "qid": q["qid"],
        "difficulty": q["difficulty"],
        "stem": q["question_text"],
        "options": opts,
        "gold": q["correct_answer"],
    }
    for tag, model_id in (("haiku", HAIKU), ("sonnet", SONNET)):
        r = call_model(client, model_id, q["question_text"], opts)
        if r["ok"] and r["parsed"]:
            sel = str(r["parsed"].get("selected", "")).strip().upper()[:1]
            conf = float(r["parsed"].get("confidence", 0.0) or 0.0)
            out[f"{tag}_selected"] = sel
            out[f"{tag}_confidence"] = conf
            out[f"{tag}_correct"] = sel == out["gold"].strip().upper()[:1]
            out[f"{tag}_reasoning"] = str(r["parsed"].get("reasoning", ""))
        else:
            out[f"{tag}_selected"] = ""
            out[f"{tag}_confidence"] = None
            out[f"{tag}_correct"] = None
            out[f"{tag}_error"] = r.get("error", "parse_failed")
        out[f"{tag}_in_tok"] = r.get("input_tokens", 0)
        out[f"{tag}_out_tok"] = r.get("output_tokens", 0)
    return out


def gate_stats(label, gate_fn, results, b2):
    fl_f = fl_w = fl_p = cl_f = cl_w = cl_p = 0
    for r in results:
        sev = b2.get(r["uuid"])
        if sev is None:
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
        f"  {label:<40}  flagged: {fl_f}f {fl_w}w {fl_p}p  ({100*fl_f/max(flagged,1):.0f}% fail, n={flagged})  "
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

    print(f"[2/3] Running Haiku + Sonnet MC closed-book with {WORKERS} workers ...", flush=True)
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

    h_in = sum(r.get("haiku_in_tok", 0) or 0 for r in results)
    h_out = sum(r.get("haiku_out_tok", 0) or 0 for r in results)
    s_in = sum(r.get("sonnet_in_tok", 0) or 0 for r in results)
    s_out = sum(r.get("sonnet_out_tok", 0) or 0 for r in results)
    haiku_cost = h_in * 1.0 / 1_000_000 + h_out * 5.0 / 1_000_000
    sonnet_cost = s_in * 3.0 / 1_000_000 + s_out * 15.0 / 1_000_000
    h_ok = sum(1 for r in results if r["haiku_correct"] is True)
    s_ok = sum(1 for r in results if r["sonnet_correct"] is True)
    print(
        f"      Haiku correct={h_ok}/{len(results)}  cost=${haiku_cost:.3f}  |  "
        f"Sonnet correct={s_ok}/{len(results)}  cost=${sonnet_cost:.3f}",
        flush=True,
    )

    print("\n[3/3] Gates ...")
    gate_stats(
        "Haiku correct & conf>=0.7",
        lambda r: bool(r["haiku_correct"]) and (r["haiku_confidence"] or 0) >= 0.7,
        results, b2,
    )
    gate_stats(
        "Sonnet correct & conf>=0.7",
        lambda r: bool(r["sonnet_correct"]) and (r["sonnet_confidence"] or 0) >= 0.7,
        results, b2,
    )
    gate_stats(
        "Sonnet correct & conf>=0.5",
        lambda r: bool(r["sonnet_correct"]) and (r["sonnet_confidence"] or 0) >= 0.5,
        results, b2,
    )
    gate_stats(
        "Sonnet correct (any conf)",
        lambda r: bool(r["sonnet_correct"]),
        results, b2,
    )
    gate_stats(
        "UNION Haiku>=0.7 OR Sonnet>=0.7",
        lambda r: (bool(r["haiku_correct"]) and (r["haiku_confidence"] or 0) >= 0.7)
                  or (bool(r["sonnet_correct"]) and (r["sonnet_confidence"] or 0) >= 0.7),
        results, b2,
    )
    gate_stats(
        "UNION Haiku correct OR Sonnet correct",
        lambda r: bool(r["haiku_correct"]) or bool(r["sonnet_correct"]),
        results, b2,
    )
    gate_stats(
        "BOTH Haiku correct AND Sonnet correct",
        lambda r: bool(r["haiku_correct"]) and bool(r["sonnet_correct"]),
        results, b2,
    )

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "uuid", "qid", "difficulty", "stem", "options", "gold",
        "haiku_selected", "haiku_confidence", "haiku_correct", "haiku_reasoning",
        "sonnet_selected", "sonnet_confidence", "sonnet_correct", "sonnet_reasoning",
        "b2_severity",
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
