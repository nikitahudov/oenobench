#!/usr/bin/env python3
"""Overnight monitor for the release_v1 build.

Snapshots metrics every 5 minutes to data/logs/release_v1_monitor.csv.

Stops when:
  * tag count >= TARGET (6,500), or
  * the build orchestrator is gone AND we've already collected > 100
    questions (terminal state — successful run).

Idempotent: if invoked while the CSV exists, it appends new rows.
"""

from __future__ import annotations

import csv
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/home/winebench/oenobench")
CSV_PATH = ROOT / "data/logs/release_v1_monitor.csv"
LOG_GLOB = "data/logs/release_v1_build_*.log"
INTERVAL = int(os.environ.get("MONITOR_INTERVAL", "300"))
TARGET = 6500
TAG = "release_v1"

FIELDS = [
    "ts_utc", "wall_min", "total", "draft", "cb_reserve",
    "template", "fact_to_question", "comparative",
    "scenario_synthesis", "distractor_mining",
    "llm_calls", "parse_fails", "gate_quota_full", "cb_reserved",
    "build_alive", "qpm_recent", "proj_eta_min",
]


def _docker_psql(sql: str) -> str:
    """Run a SQL statement inside the wb-postgres container, return stdout (single line)."""
    try:
        proc = subprocess.run(
            ["docker", "exec", "-i", "wb-postgres", "psql",
             "-U", "winebench", "-d", "winebench", "-t", "-A", "-F", "|", "-c", sql],
            capture_output=True, text=True, timeout=30,
        )
        return proc.stdout.strip()
    except Exception:
        return ""


def db_snapshot() -> dict[str, int]:
    """Return total / draft / cb_reserve and per-strategy counts for TAG."""
    sql = (
        "SELECT count(*),"
        " count(*) FILTER (WHERE q.status::text='draft'),"
        " count(*) FILTER (WHERE q.status::text='cb_reserve'),"
        " count(*) FILTER (WHERE gm.generation_method='template'),"
        " count(*) FILTER (WHERE gm.generation_method='fact_to_question'),"
        " count(*) FILTER (WHERE gm.generation_method='comparative'),"
        " count(*) FILTER (WHERE gm.generation_method='scenario_synthesis'),"
        " count(*) FILTER (WHERE gm.generation_method='distractor_mining')"
        " FROM questions q JOIN generation_metadata gm ON gm.question_id = q.id"
        f" WHERE '{TAG}' = ANY(q.tags);"
    )
    out = _docker_psql(sql).replace("\n", "")  # collapse any embedded newlines
    parts = out.split("|")
    keys = ["total", "draft", "cb_reserve",
            "template", "fact_to_question", "comparative",
            "scenario_synthesis", "distractor_mining"]
    if len(parts) != len(keys):
        return {k: 0 for k in keys}
    try:
        return {k: int(v) for k, v in zip(keys, parts)}
    except ValueError:
        return {k: 0 for k in keys}


def latest_build_log() -> Path | None:
    candidates = sorted(ROOT.glob(LOG_GLOB), key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None


def grep_count(path: Path, pattern: str) -> int:
    if not path or not path.exists():
        return 0
    rx = re.compile(pattern)
    n = 0
    try:
        with path.open("r", errors="replace") as fh:
            for line in fh:
                if rx.search(line):
                    n += 1
    except Exception:
        return 0
    return n


def build_alive() -> bool:
    """True iff the build orchestrator process is still running."""
    try:
        proc = subprocess.run(
            ["pgrep", "-f", "src.generators.orchestrator generate-all"],
            capture_output=True, text=True, timeout=10,
        )
        return bool(proc.stdout.strip())
    except Exception:
        return False


def build_start_epoch(log_path: Path | None) -> float:
    if log_path and log_path.exists():
        with log_path.open("r", errors="replace") as fh:
            head = fh.read(2048)
        m = re.search(r"start: (\w+ +\w+ +\d+ [\d:]+ UTC \d+)", head)
        if m:
            try:
                ts = datetime.strptime(m.group(1), "%a %b %d %H:%M:%S %Z %Y")
                ts = ts.replace(tzinfo=timezone.utc)
                return ts.timestamp()
            except Exception:
                pass
    # Fallback: use the file mtime (close enough)
    if log_path and log_path.exists():
        return log_path.stat().st_mtime
    return time.time()


def main() -> int:
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    write_header = not CSV_PATH.exists() or CSV_PATH.stat().st_size == 0

    log_path = latest_build_log()
    start_epoch = build_start_epoch(log_path)
    print(f"[monitor] start_epoch={start_epoch:.0f} log={log_path}")

    while True:
        # Re-resolve in case the build script rotates logs (it does not, but cheap).
        log_path = latest_build_log()
        now = time.time()
        wall_min = (now - start_epoch) / 60.0

        snap = db_snapshot()
        llm_calls = grep_count(log_path, r"LLM call \|") if log_path else 0
        parse_fails = grep_count(log_path, r"Parse failed|Failed to extract JSON") if log_path else 0
        gate_qf = grep_count(log_path, r"GATE QUOTA FULL") if log_path else 0
        cb_reserved_log = grep_count(log_path, r"GATE QUOTA FULL → RESERVED") if log_path else 0
        alive = 1 if build_alive() else 0

        # Recent throughput: rolling delta vs previous CSV row (~INTERVAL ago).
        qpm_recent: float | None = None
        proj_eta_min: float | None = None
        if CSV_PATH.exists() and CSV_PATH.stat().st_size > 0:
            try:
                with CSV_PATH.open("r", errors="replace") as fh:
                    lines = [l.rstrip("\n") for l in fh if l.strip()]
                if len(lines) >= 2:
                    last = lines[-1].split(",")
                    prev_ts = datetime.strptime(last[0], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
                    prev_total = int(last[2])
                    dt = now - prev_ts.timestamp()
                    dq = snap["total"] - prev_total
                    if dt > 0 and dq > 0:
                        qpm_recent = (dq * 60.0) / dt
                        if qpm_recent > 0:
                            remaining = max(0, TARGET - snap["total"])
                            proj_eta_min = remaining / qpm_recent
            except Exception:
                pass

        ts_iso = datetime.fromtimestamp(now, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        row = {
            "ts_utc": ts_iso,
            "wall_min": f"{wall_min:.1f}",
            "total": snap["total"],
            "draft": snap["draft"],
            "cb_reserve": snap["cb_reserve"],
            "template": snap["template"],
            "fact_to_question": snap["fact_to_question"],
            "comparative": snap["comparative"],
            "scenario_synthesis": snap["scenario_synthesis"],
            "distractor_mining": snap["distractor_mining"],
            "llm_calls": llm_calls,
            "parse_fails": parse_fails,
            "gate_quota_full": gate_qf,
            "cb_reserved": cb_reserved_log,
            "build_alive": alive,
            "qpm_recent": f"{qpm_recent:.2f}" if qpm_recent is not None else "-",
            "proj_eta_min": f"{proj_eta_min:.1f}" if proj_eta_min is not None else "-",
        }

        with CSV_PATH.open("a", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=FIELDS)
            if write_header:
                w.writeheader()
                write_header = False
            w.writerow(row)

        print(
            f"[monitor] {ts_iso} | wall={wall_min:.1f}m total={snap['total']} "
            f"draft={snap['draft']} cb_res={snap['cb_reserve']} "
            f"qpm={row['qpm_recent']} eta={row['proj_eta_min']}m alive={alive}"
        )

        # Stop conditions
        if snap["total"] >= TARGET:
            print(f"[monitor] target {TARGET} reached — stopping")
            return 0
        if not alive and snap["total"] > 100:
            # Build no longer running and we have substantial output → terminal.
            print(f"[monitor] build process exited at total={snap['total']} — stopping")
            return 0

        time.sleep(INTERVAL)


if __name__ == "__main__":
    sys.exit(main())
