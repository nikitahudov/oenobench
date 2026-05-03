"""
OenoBench — Monitoring Dashboard.

Run:  python -m src.dashboard.app
"""

import copy
import os
import subprocess
from datetime import datetime, timezone
from functools import wraps

from dotenv import load_dotenv
from flask import Flask, Response, jsonify, render_template, request

load_dotenv()

app = Flask(
    __name__,
    template_folder=os.path.join(os.path.dirname(__file__), "templates"),
    static_folder=os.path.join(os.path.dirname(__file__), "static"),
)

DASHBOARD_USER = os.getenv("DASHBOARD_USER", "admin")
DASHBOARD_PASSWORD = os.getenv("DASHBOARD_PASSWORD", "changeme")

DOMAIN_TARGETS = {
    "wine_regions": 5000,
    "grape_varieties": 2000,
    "producers": 3000,
    "viticulture": 1500,
    "winemaking": 1500,
    "wine_business": 1000,
}

DOMAIN_ORDER = ["wine_regions", "grape_varieties", "producers", "viticulture", "winemaking", "wine_business"]

DEADLINE = datetime(2026, 5, 4, tzinfo=timezone.utc)

PROJECT_PHASES = [
    {
        "id": 1,
        "name": "Data Collection",
        "status": "complete",
        "target": "15,000+ facts",
        "actual": None,
        "details": "35 genuine scrapers across 22 countries — Wikipedia + Wikidata SPARQL + government registries (INAO, TTB) + academic journals (UC Davis, OENO One) + official wine bodies. Full provenance rebuild April 2026.",
    },
    {
        "id": 2,
        "name": "Question Generation",
        "status": "complete",
        "target": "release_v1 corpus",
        "actual": None,
        "details": "5 generation strategies (fact-to-question, template, comparative, scenario synthesis, distractor mining) with multi-model prompts (Claude / GPT-5 / Gemini 2.5 / Llama / template). Build hit substantive-fact ceiling at ~2,535 release_v1 questions across all 6 domains.",
        "sub_tasks": [
            {"name": "Prompt engineering + 5 strategies (Phase 2 \u2192 2g)", "status": "complete"},
            {"name": "Closed-book gate v2 + cb_reserve (Phase 2g.6)", "status": "complete"},
            {"name": "10 speedup levers + cell-allocation fixes (Phase 2g.11\u201312)", "status": "complete"},
            {"name": "Yield recovery: parse retries + dead-cell skip (Phase 2g.15)", "status": "complete"},
            {"name": "Template quality push v14c (Phase 2g.16)", "status": "complete"},
            {"name": "release_v1 build (Phase 2j)", "status": "complete"},
        ],
    },
    {
        "id": 3,
        "name": "AI Validation",
        "status": "complete",
        "target": "9-agent audit framework",
        "actual": None,
        "details": "Multi-team audit: Team A (lexical hygiene, bias stats, fact echo, template fingerprint), Team B (tri-judge answer consensus + closed-book solvability), Team C (category leak), Team D (self-preference, skew). Iterative audit_pilot v1\u2192v16 with Go/No-Go gates.",
    },
    {
        "id": 4,
        "name": "Human Review",
        "status": "in_progress",
        "target": "Multi-expert review on release_v1",
        "actual": None,
        "details": "Web app on port 5556 \u2014 reviewers self-register, score 10 rubrics (pass/warn/fail) plus overall verdict, suggested-answer override, and notes. IRR-aware assignment ensures every question is reviewed by \u22652 reviewers when available, supporting Cohen's \u03ba reliability statistics.",
    },
    {
        "id": 5,
        "name": "Evaluation & Analysis",
        "status": "in_progress",
        "target": "16-config OpenRouter slate",
        "actual": None,
        "details": "Sample-DB eval shipped 2026-05-02 against the 1,062-question `sample` schema. 14 model configs, 16,572 LLM calls, ~$31 spend, 28-min wall. Final eval against release_v1 + reasoning-stratified subset pending. SPS analysis to follow.",
    },
    {
        "id": 6,
        "name": "Publication & Release",
        "status": "not_started",
        "target": "NeurIPS 2026 D&B Track",
        "actual": None,
        "details": "Paper writing, ArXiv preprint, public dataset release on HuggingFace + GitHub.",
        "deadline": "2026-05-04",
    },
]


# ── Auth ─────────────────────────────────────────────────────────────────────


def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or auth.username != DASHBOARD_USER or auth.password != DASHBOARD_PASSWORD:
            return Response(
                "Authentication required.",
                401,
                {"WWW-Authenticate": 'Basic realm="OenoBench Dashboard"'},
            )
        return f(*args, **kwargs)

    return decorated


# ── Helpers ──────────────────────────────────────────────────────────────────


def _pg_query(sql, params=None):
    """Execute a PG query with automatic reconnect on stale connection."""
    from src.utils.db import get_pg

    try:
        conn = get_pg()
        cur = conn.cursor()
        cur.execute(sql, params)
        return cur.fetchall()
    except Exception:
        get_pg.cache_clear()
        conn = get_pg()
        cur = conn.cursor()
        cur.execute(sql, params)
        return cur.fetchall()


# ── Routes ───────────────────────────────────────────────────────────────────


@app.route("/")
@require_auth
def index():
    return render_template("index.html")


@app.route("/api/project")
@require_auth
def api_project():
    """Project plan overview with phases and key metrics."""
    try:
        rows = _pg_query("SELECT count(*) AS cnt FROM facts")
        total_facts = rows[0]["cnt"]
    except Exception:
        total_facts = 0

    try:
        rows = _pg_query("SELECT count(*) AS cnt FROM questions")
        total_questions = rows[0]["cnt"]
    except Exception:
        total_questions = 0

    try:
        rows = _pg_query("SELECT count(*) AS cnt FROM questions WHERE 'release_v1' = ANY(tags)")
        release_v1_count = rows[0]["cnt"]
    except Exception:
        release_v1_count = 0

    phases = copy.deepcopy(PROJECT_PHASES)
    phases[0]["actual"] = f"{total_facts:,} facts"
    phases[1]["actual"] = f"{release_v1_count:,} questions"

    days_remaining = (DEADLINE - datetime.now(timezone.utc)).days

    return jsonify({
        "phases": phases,
        "metrics": {
            "total_facts": total_facts,
            "total_questions": total_questions,
            "release_v1_count": release_v1_count,
            "target_questions": release_v1_count or 2535,
            "days_until_deadline": max(days_remaining, 0),
            "deadline": DEADLINE.date().isoformat(),
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


@app.route("/api/facts")
@require_auth
def api_facts():
    # Domain counts
    try:
        domain_rows = _pg_query("SELECT domain, count(*) AS cnt FROM facts GROUP BY domain")
        domain_counts = {r["domain"]: r["cnt"] for r in domain_rows}
    except Exception:
        domain_counts = {}

    domains = []
    total_count = 0
    for name in DOMAIN_ORDER:
        target = DOMAIN_TARGETS[name]
        count = domain_counts.get(name, 0)
        total_count += count
        domains.append({
            "name": name,
            "count": count,
            "target": target,
            "pct": round(count / target * 100, 1) if target else 0,
        })

    target_total = sum(DOMAIN_TARGETS.values())

    # Source count
    try:
        source_rows = _pg_query("SELECT count(*) AS cnt FROM sources WHERE id IN (SELECT DISTINCT source_id FROM facts)")
        source_count = source_rows[0]["cnt"]
    except Exception:
        source_count = 0

    # Country x Domain pivot from fact_count_summary
    try:
        pivot_rows = _pg_query(
            "SELECT country, domain, SUM(fact_count) AS cnt "
            "FROM fact_count_summary GROUP BY country, domain ORDER BY country, domain"
        )
        countries = {}
        for r in pivot_rows:
            c = r["country"]
            if c not in countries:
                countries[c] = {}
            countries[c][r["domain"]] = r["cnt"]

        pivot = []
        for country, dcounts in sorted(
            countries.items(), key=lambda x: sum(x[1].values()), reverse=True
        ):
            row = {"country": country}
            row_total = 0
            for d in DOMAIN_ORDER:
                val = dcounts.get(d, 0)
                row[d] = val
                row_total += val
            row["total"] = row_total
            pivot.append(row)

        col_totals = {"country": "Total"}
        grand_total = 0
        for d in DOMAIN_ORDER:
            col_sum = sum(r.get(d, 0) for r in pivot)
            col_totals[d] = col_sum
            grand_total += col_sum
        col_totals["total"] = grand_total
    except Exception:
        pivot = []
        col_totals = {}

    # Source type distribution
    try:
        source_dist = _pg_query(
            "SELECT s.source_type, COUNT(f.id) AS cnt "
            "FROM facts f JOIN sources s ON f.source_id = s.id "
            "GROUP BY s.source_type ORDER BY cnt DESC"
        )
        source_distribution = [{"type": r["source_type"], "count": r["cnt"]} for r in source_dist]
    except Exception:
        source_distribution = []

    return jsonify({
        "domains": domains,
        "domains_list": DOMAIN_ORDER,
        "total": {
            "count": total_count,
            "target": target_total,
            "pct": round(total_count / target_total * 100, 1) if target_total else 0,
        },
        "sources": {"count": source_count},
        "pivot": pivot,
        "pivot_totals": col_totals,
        "source_distribution": source_distribution,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


@app.route("/api/health")
@require_auth
def api_health():
    services = []

    # PostgreSQL
    try:
        rows = _pg_query("SELECT version()")
        version = rows[0]["version"].split(",")[0] if rows else "unknown"
        table_rows = _pg_query(
            "SELECT count(*) AS cnt FROM information_schema.tables WHERE table_schema = 'public'"
        )
        table_count = table_rows[0]["cnt"]
        services.append({
            "name": "PostgreSQL",
            "status": "healthy",
            "details": {"version": version, "tables": table_count, "port": 5432},
        })
    except Exception as e:
        services.append({
            "name": "PostgreSQL",
            "status": "down",
            "details": {"error": str(e)},
        })

    # Elasticsearch
    try:
        from src.utils.db import get_es

        es = get_es()
        health = es.cluster.health()
        indices = es.cat.indices(format="json")
        wb_indices = [i for i in indices if i.get("index", "").startswith("winebench")]
        es_status = "healthy" if health["status"] == "green" else (
            "degraded" if health["status"] == "yellow" else "down"
        )
        services.append({
            "name": "Elasticsearch",
            "status": es_status,
            "details": {
                "cluster_status": health["status"],
                "indices": len(wb_indices),
                "port": 9200,
            },
        })
    except Exception as e:
        services.append({
            "name": "Elasticsearch",
            "status": "down",
            "details": {"error": str(e)},
        })

    # Neo4j
    try:
        from src.utils.db import get_neo4j

        driver = get_neo4j()
        with driver.session() as session:
            result = session.run("MATCH (n) RETURN count(n) AS cnt")
            node_count = result.single()["cnt"]
        services.append({
            "name": "Neo4j",
            "status": "healthy",
            "details": {"nodes": node_count, "bolt_port": 7687, "http_port": 7474},
        })
    except Exception as e:
        services.append({
            "name": "Neo4j",
            "status": "down",
            "details": {"error": str(e)},
        })

    # Redis
    try:
        from src.utils.db import get_redis

        r = get_redis()
        r.ping()
        info = r.info("memory")
        services.append({
            "name": "Redis",
            "status": "healthy",
            "details": {
                "memory_used": info.get("used_memory_human", "N/A"),
                "port": 6379,
            },
        })
    except Exception as e:
        services.append({
            "name": "Redis",
            "status": "down",
            "details": {"error": str(e)},
        })

    # Docker container stats
    docker_stats = []
    try:
        result = subprocess.run(
            ["docker", "stats", "--no-stream", "--format", "{{.Name}}\t{{.MemUsage}}\t{{.CPUPerc}}"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        for line in result.stdout.strip().split("\n"):
            if not line or "wb-" not in line:
                continue
            parts = line.split("\t")
            if len(parts) >= 3:
                docker_stats.append({
                    "container": parts[0],
                    "memory": parts[1],
                    "cpu": parts[2],
                })
    except Exception:
        pass

    return jsonify({
        "services": services,
        "docker_stats": docker_stats,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


@app.route("/api/questions")
@require_auth
def api_questions():
    """release_v1 corpus breakdown — per-strategy, per-domain, status counts."""
    try:
        status_rows = _pg_query(
            "SELECT status, count(*) AS cnt FROM questions WHERE 'release_v1' = ANY(tags) GROUP BY status"
        )
        by_status = {r["status"]: r["cnt"] for r in status_rows}
    except Exception:
        by_status = {}

    try:
        strat_rows = _pg_query(
            "SELECT gm.generation_method AS strategy, count(*) AS cnt "
            "FROM questions q JOIN generation_metadata gm ON gm.question_id = q.id "
            "WHERE 'release_v1' = ANY(q.tags) GROUP BY gm.generation_method ORDER BY cnt DESC"
        )
        by_strategy = [{"strategy": r["strategy"], "count": r["cnt"]} for r in strat_rows]
    except Exception:
        by_strategy = []

    try:
        domain_rows = _pg_query(
            "SELECT domain, count(*) AS cnt FROM questions "
            "WHERE 'release_v1' = ANY(tags) GROUP BY domain"
        )
        domain_counts = {r["domain"]: r["cnt"] for r in domain_rows}
    except Exception:
        domain_counts = {}

    try:
        diff_rows = _pg_query(
            "SELECT difficulty::text AS difficulty, count(*) AS cnt FROM questions "
            "WHERE 'release_v1' = ANY(tags) GROUP BY difficulty ORDER BY difficulty"
        )
        by_difficulty = [{"level": r["difficulty"], "count": r["cnt"]} for r in diff_rows]
    except Exception:
        by_difficulty = []

    by_domain = []
    total = sum(domain_counts.values())
    for name in DOMAIN_ORDER:
        cnt = domain_counts.get(name, 0)
        by_domain.append({
            "domain": name,
            "count": cnt,
            "pct": round(cnt / total * 100, 1) if total else 0,
        })

    return jsonify({
        "tag": "release_v1",
        "total": sum(by_status.values()),
        "by_status": by_status,
        "by_strategy": by_strategy,
        "by_domain": by_domain,
        "by_difficulty": by_difficulty,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


@app.route("/api/reviews")
@require_auth
def api_reviews():
    """Human review progress — batches, reviewers, completed reviews."""
    try:
        rows = _pg_query("SELECT count(*) AS cnt FROM human_reviewers")
        reviewer_count = rows[0]["cnt"]
    except Exception:
        reviewer_count = 0

    try:
        rows = _pg_query("SELECT count(*) AS cnt FROM human_reviews WHERE is_complete")
        review_count = rows[0]["cnt"]
    except Exception:
        review_count = 0

    try:
        # Exclude pytest fixture batches (named test_batch_*)
        batch_rows = _pg_query(
            "SELECT b.name, b.question_count, b.created_at, "
            "  count(DISTINCT hr.reviewer_id) FILTER (WHERE hr.is_complete) AS reviewer_count, "
            "  count(*) FILTER (WHERE hr.is_complete) AS review_count, "
            "  count(DISTINCT hr.question_id) FILTER (WHERE hr.is_complete) AS questions_with_review "
            "FROM review_batches b "
            "LEFT JOIN human_reviews hr ON hr.batch_id = b.id "
            "WHERE b.name NOT LIKE 'test_batch_%%' "
            "GROUP BY b.id, b.name, b.question_count, b.created_at "
            "ORDER BY b.created_at DESC"
        )
        batches = [
            {
                "name": r["name"],
                "question_count": r["question_count"],
                "reviewer_count": r["reviewer_count"] or 0,
                "review_count": r["review_count"] or 0,
                "questions_with_review": r["questions_with_review"] or 0,
                "coverage_pct": round((r["questions_with_review"] or 0) / r["question_count"] * 100, 1)
                                if r["question_count"] else 0,
            }
            for r in batch_rows
        ]
    except Exception:
        batches = []

    try:
        rev_rows = _pg_query(
            "SELECT hu.name, hu.email, hu.credentials, count(hr.id) FILTER (WHERE hr.is_complete) AS reviews "
            "FROM human_reviewers hu "
            "LEFT JOIN human_reviews hr ON hr.reviewer_id = hu.id "
            "GROUP BY hu.id, hu.name, hu.email, hu.credentials "
            "ORDER BY reviews DESC NULLS LAST"
        )
        reviewers = [
            {
                "name": r["name"],
                "email": r["email"],
                "credentials": r["credentials"] or "",
                "reviews": r["reviews"] or 0,
            }
            for r in rev_rows
        ]
    except Exception:
        reviewers = []

    return jsonify({
        "reviewer_count": reviewer_count,
        "review_count": review_count,
        "batches": batches,
        "reviewers": reviewers,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


@app.route("/api/evaluation")
@require_auth
def api_evaluation():
    """LLM evaluation leaderboard from the latest run."""
    try:
        rows = _pg_query(
            "SELECT ea.model_name, count(*) AS n, "
            "  sum(CASE WHEN ea.is_correct THEN 1 ELSE 0 END) AS correct, "
            "  round((avg(CASE WHEN ea.is_correct THEN 1.0 ELSE 0.0 END) * 100)::numeric, 1) AS pct "
            "FROM evaluation_answers ea "
            "WHERE ea.parsed_answer IS NOT NULL "
            "GROUP BY ea.model_name "
            "ORDER BY pct DESC NULLS LAST"
        )
        leaderboard = [
            {
                "model": r["model_name"],
                "n": r["n"],
                "correct": r["correct"],
                "pct": float(r["pct"]) if r["pct"] is not None else 0.0,
            }
            for r in rows
        ]
    except Exception:
        leaderboard = []

    try:
        run_rows = _pg_query(
            "SELECT count(*) AS cnt, max(started_at) AS latest_run "
            "FROM evaluation_runs"
        )
        run_count = run_rows[0]["cnt"]
        latest = run_rows[0]["latest_run"].isoformat() if run_rows[0]["latest_run"] else None
    except Exception:
        run_count = 0
        latest = None

    return jsonify({
        "run_count": run_count,
        "latest_run": latest,
        "leaderboard": leaderboard,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


# ── Main ─────────────────────────────────────────────────────────────────────


if __name__ == "__main__":
    port = int(os.getenv("DASHBOARD_PORT", 5555))
    app.run(host="0.0.0.0", port=port, debug=os.getenv("WINEBENCH_ENV") == "development")
