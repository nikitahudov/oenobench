"""Prototype: closed-book pre-screen for B2 leakage gating.

For each L1/L2 fact behind audit_pilot_v4 questions, ask Haiku 4.5 whether a
question generated from the fact would be solvable without seeing it. Then
cross-tab the verdict against the actual B2 findings on the questions that
were generated from that fact.

Output: data/reports/prescreen_b2_prototype.csv + summary printed to stdout.
"""

from __future__ import annotations

import csv
import json
import os
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import openai
import orjson
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.generators._llm_client import _try_parse_json  # noqa: E402
from src.utils.db import get_pg  # noqa: E402

load_dotenv()

HAIKU_MODEL = "anthropic/claude-haiku-4.5"
RUN_ID = "4e3ead78-2b62-4733-919d-bf3f4878aaec"
OUT_CSV = Path("data/reports/prescreen_b2_prototype.csv")
WORKERS = 8

PROMPT = """You are evaluating a wine fact for use in a closed-book benchmark.

FACT: "{fact_text}"

Imagine the most natural multiple-choice question that could be derived from this fact, asking about the most informative element.

Could a strong LLM (e.g., GPT-5, Claude Opus 4) answer that question correctly using only its general training knowledge, WITHOUT being shown the fact?

Mark `world_knowledge_solvable: true` if the answer is widely-known wine knowledge (famous regions, classic grape-region pairings, well-known styles, taxonomic mappings like AVA->state).

Mark `world_knowledge_solvable: false` if the answer requires this specific fact (precise statistics, niche producers, regulatory minutiae, recent or local data).

Respond with ONLY a JSON object:
{{
  "candidate_question": "the most natural Q derivable from this fact",
  "candidate_answer": "the answer",
  "world_knowledge_solvable": true | false,
  "confidence": 0.0-1.0,
  "reasoning": "one sentence"
}}"""


def fetch_facts() -> list[dict]:
    sql = """
    SELECT DISTINCT
        f.id AS fact_id,
        f.fact_text,
        f.domain,
        f.subdomain
    FROM facts f
    JOIN question_facts qf ON qf.fact_id = f.id
    JOIN questions q ON q.id = qf.question_id
    WHERE q.tags && ARRAY['audit_pilot_v4']
      AND q.difficulty IN ('1', '2')
    ORDER BY f.id;
    """
    conn = get_pg()
    with conn.cursor() as cur:
        cur.execute(sql)
        return [dict(row) for row in cur.fetchall()]


def fetch_b2_by_fact() -> dict[str, list[dict]]:
    """For each fact_id, list of (question_id, severity) for L1/L2 questions."""
    sql = """
    SELECT
        qf.fact_id::text AS fact_id,
        q.id::text AS question_id,
        q.question_id AS qid,
        q.difficulty,
        f.severity::text AS severity
    FROM audit_findings f
    JOIN questions q ON q.id = f.question_id
    JOIN question_facts qf ON qf.question_id = q.id
    WHERE f.run_id = %s
      AND f.agent_id = 'B2_ClosedBookSolvability'
      AND q.difficulty IN ('1', '2')
      AND q.tags && ARRAY['audit_pilot_v4'];
    """
    conn = get_pg()
    with conn.cursor() as cur:
        cur.execute(sql, (RUN_ID,))
        out: dict[str, list[dict]] = defaultdict(list)
        for row in cur.fetchall():
            out[row["fact_id"]].append(dict(row))
    return out


def call_haiku(client: openai.OpenAI, fact_text: str) -> dict:
    msg = PROMPT.format(fact_text=fact_text.replace('"', '\\"'))
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
        parsed = _try_parse_json(content)
        return {
            "ok": True,
            "parsed": parsed,
            "raw": content,
            "latency_ms": latency_ms,
            "input_tokens": resp.usage.prompt_tokens if resp.usage else 0,
            "output_tokens": resp.usage.completion_tokens if resp.usage else 0,
        }
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e), "latency_ms": int((time.time() - t0) * 1000)}


def screen_one(client, fact: dict) -> dict:
    result = call_haiku(client, fact["fact_text"])
    out = {
        "fact_id": str(fact["fact_id"]),
        "domain": fact["domain"],
        "subdomain": fact["subdomain"] or "",
        "fact_text": fact["fact_text"],
        "ok": result["ok"],
        "latency_ms": result["latency_ms"],
        "input_tokens": result.get("input_tokens", 0),
        "output_tokens": result.get("output_tokens", 0),
    }
    if result["ok"] and result["parsed"]:
        p = result["parsed"]
        out["world_solvable"] = bool(p.get("world_knowledge_solvable"))
        out["confidence"] = float(p.get("confidence", 0.0) or 0.0)
        out["candidate_question"] = p.get("candidate_question", "")
        out["candidate_answer"] = p.get("candidate_answer", "")
        out["reasoning"] = p.get("reasoning", "")
    else:
        out["world_solvable"] = None
        out["confidence"] = None
        out["error"] = result.get("error") or "json_parse_failed"
    return out


def main():
    api_key = os.environ["OPENROUTER_API_KEY"]
    client = openai.OpenAI(api_key=api_key, base_url="https://openrouter.ai/api/v1")

    print("[1/4] Fetching L1/L2 v4 facts ...", flush=True)
    facts = fetch_facts()
    print(f"      {len(facts)} distinct facts", flush=True)

    print("[2/4] Fetching B2 findings on those facts' questions ...", flush=True)
    b2 = fetch_b2_by_fact()
    covered = sum(1 for f in facts if str(f["fact_id"]) in b2)
    print(f"      {covered}/{len(facts)} facts have ≥1 B2-judged question", flush=True)

    print(f"[3/4] Running Haiku pre-screen with {WORKERS} workers ...", flush=True)
    results: list[dict] = []
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = {pool.submit(screen_one, client, f): f for f in facts}
        for i, fut in enumerate(as_completed(futures), 1):
            results.append(fut.result())
            if i % 25 == 0:
                elapsed = time.time() - t0
                rate = i / elapsed
                eta = (len(facts) - i) / rate
                print(f"      {i}/{len(facts)}  rate={rate:.1f}/s  eta={eta:.0f}s", flush=True)
    print(f"      done in {time.time() - t0:.1f}s", flush=True)

    in_tok = sum(r.get("input_tokens", 0) or 0 for r in results)
    out_tok = sum(r.get("output_tokens", 0) or 0 for r in results)
    cost = in_tok * 1.0 / 1_000_000 + out_tok * 5.0 / 1_000_000
    parse_ok = sum(1 for r in results if r["world_solvable"] is not None)
    flag_true = sum(1 for r in results if r["world_solvable"] is True)
    print(
        f"      tokens in={in_tok} out={out_tok}  est_cost=${cost:.3f}  "
        f"parse_ok={parse_ok}/{len(results)}  flagged_solvable={flag_true}",
        flush=True,
    )

    print("[4/4] Cross-tabulating Haiku verdict vs B2 outcome ...", flush=True)
    fail_when_flagged = pass_when_flagged = warn_when_flagged = 0
    fail_when_clean = pass_when_clean = warn_when_clean = 0
    seen_q = set()
    for r in results:
        verdict = r["world_solvable"]
        if verdict is None:
            continue
        for q in b2.get(r["fact_id"], []):
            key = (q["question_id"], r["fact_id"])
            if key in seen_q:
                continue
            seen_q.add(key)
            sev = q["severity"]
            if verdict:
                if sev == "fail":
                    fail_when_flagged += 1
                elif sev == "warn":
                    warn_when_flagged += 1
                else:
                    pass_when_flagged += 1
            else:
                if sev == "fail":
                    fail_when_clean += 1
                elif sev == "warn":
                    warn_when_clean += 1
                else:
                    pass_when_clean += 1

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "fact_id", "domain", "subdomain", "fact_text", "ok", "world_solvable",
        "confidence", "candidate_question", "candidate_answer", "reasoning",
        "latency_ms", "input_tokens", "output_tokens", "error",
    ]
    with OUT_CSV.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for r in results:
            w.writerow(r)
    print(f"      wrote {OUT_CSV}", flush=True)

    flagged_total = fail_when_flagged + warn_when_flagged + pass_when_flagged
    clean_total = fail_when_clean + warn_when_clean + pass_when_clean

    summary = {
        "facts_screened": len(results),
        "haiku_parse_ok": parse_ok,
        "haiku_flagged_solvable": flag_true,
        "est_cost_usd": round(cost, 4),
        "fact_to_question_pairs_judged": flagged_total + clean_total,
        "when_haiku_flags_solvable": {
            "fail": fail_when_flagged,
            "warn": warn_when_flagged,
            "pass": pass_when_flagged,
            "fail_pct": round(100 * fail_when_flagged / max(flagged_total, 1), 1),
        },
        "when_haiku_says_clean": {
            "fail": fail_when_clean,
            "warn": warn_when_clean,
            "pass": pass_when_clean,
            "fail_pct": round(100 * fail_when_clean / max(clean_total, 1), 1),
        },
    }
    print("\n=== SUMMARY ===")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
