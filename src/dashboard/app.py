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

PROJECT_PHASES = [
    {
        "id": 1,
        "name": "Data Collection",
        "status": "complete",
        "target": "15,000+ facts",
        "actual": None,
        "details": "35 scrapers across 22 countries. Wikipedia, Wikidata SPARQL, government registries, academic journals, official wine bodies.",
    },
    {
        "id": 2,
        "name": "Question Generation",
        "status": "not_started",
        "target": "7,000 raw \u2192 6,000 unique",
        "actual": None,
        "details": "Multi-model generation to avoid self-preference bias in evaluation.",
        "sub_tasks": [
            {"name": "Prompt engineering & templates", "status": "not_started"},
            {"name": "Claude generation (30%)", "status": "not_started"},
            {"name": "GPT-4 generation (30%)", "status": "not_started"},
            {"name": "Gemini generation (20%)", "status": "not_started"},
            {"name": "Llama generation (10%)", "status": "not_started"},
            {"name": "Template-based generation (10%)", "status": "not_started"},
            {"name": "Deduplication & normalization", "status": "not_started"},
        ],
    },
    {
        "id": 3,
        "name": "AI Validation",
        "status": "not_started",
        "target": "5,500 validated",
        "actual": None,
        "details": "Multi-model validator (3+ models must agree). Automated difficulty estimator with calibrated scores. Bias detection pass.",
    },
    {
        "id": 4,
        "name": "Human Review & Control Set",
        "status": "not_started",
        "target": "5,000 + 300 human-authored",
        "actual": None,
        "details": "Expert panel (3-5 wine domain experts) reviews flagged questions. 300 human-authored control questions for bias analysis.",
    },
    {
        "id": 5,
        "name": "Evaluation & Analysis",
        "status": "not_started",
        "target": "Full LLM benchmark",
        "actual": None,
        "details": "Evaluate target LLMs on held-out subsets. Self-Preference Score (SPS) analysis. Category-level scoring across all 6 domains.",
    },
    {
        "id": 6,
        "name": "Publication & Release",
        "status": "not_started",
        "target": "NeurIPS 2026",
        "actual": None,
        "details": "Paper writing, ArXiv preprint, public dataset release on HuggingFace + GitHub.",
        "deadline": "2026-05-15",
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

    phases = copy.deepcopy(PROJECT_PHASES)
    phases[0]["actual"] = f"{total_facts:,} facts"

    deadline = datetime(2026, 5, 15, tzinfo=timezone.utc)
    days_remaining = (deadline - datetime.now(timezone.utc)).days

    return jsonify({
        "phases": phases,
        "metrics": {
            "total_facts": total_facts,
            "total_questions": total_questions,
            "target_questions": 5000,
            "days_until_deadline": max(days_remaining, 0),
            "deadline": "2026-05-15",
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


# ── Main ─────────────────────────────────────────────────────────────────────


if __name__ == "__main__":
    port = int(os.getenv("DASHBOARD_PORT", 5555))
    app.run(host="0.0.0.0", port=port, debug=os.getenv("WINEBENCH_ENV") == "development")
