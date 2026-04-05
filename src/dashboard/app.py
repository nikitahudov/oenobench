"""
OenoBench — Monitoring Dashboard.

Run:  python -m src.dashboard.app
"""

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

SCRAPERS = [
    {"name": "Wikidata", "file": "wikidata.py", "status": "complete", "facts": 20911},
    {"name": "Wikipedia", "file": "wikipedia.py", "status": "complete", "facts": 323},
    {"name": "HuggingFace", "file": "huggingface.py", "status": "complete", "facts": 16514},
    {"name": "UC Davis", "file": "ucdavis.py", "status": "complete", "facts": 3371},
    {"name": "Kaggle", "file": "kaggle_data.py", "status": "complete", "facts": 1509},
    {"name": "INAO (France)", "file": "inao.py", "status": "complete", "facts": 1473},
    {"name": "Italy Registries", "file": "italy.py", "status": "complete", "facts": None},
    {"name": "US TTB", "file": "ttb.py", "status": "complete", "facts": None},
    {"name": "Europe (ES/DE/PT)", "file": "europe.py", "status": "complete", "facts": None},
    {"name": "New World", "file": "newworld.py", "status": "complete", "facts": None},
    {"name": "EU/OIV Regulations", "file": "eu_oiv.py", "status": "complete", "facts": None},
    {"name": "Burgundy", "file": "burgundy.py", "status": "complete", "facts": None},
    {"name": "Bordeaux", "file": "bordeaux.py", "status": "complete", "facts": None},
    {"name": "Champagne", "file": "champagne.py", "status": "complete", "facts": None},
    {"name": "Italian Consortiums", "file": "consortiums_italy.py", "status": "complete", "facts": None},
    {"name": "Academic Journals", "file": "academic.py", "status": "complete", "facts": None},
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


@app.route("/api/facts")
@require_auth
def api_facts():
    try:
        domain_rows = _pg_query("SELECT domain, count(*) AS cnt FROM facts GROUP BY domain")
        domain_counts = {r["domain"]: r["cnt"] for r in domain_rows}
    except Exception:
        domain_counts = {}

    domains = []
    total_count = 0
    for name, target in DOMAIN_TARGETS.items():
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
        source_rows = _pg_query("SELECT count(*) AS cnt FROM sources")
        source_count = source_rows[0]["cnt"]
    except Exception:
        source_count = 0

    # Questions by status
    try:
        q_rows = _pg_query("SELECT status, count(*) AS cnt FROM questions GROUP BY status")
        questions = {r["status"]: r["cnt"] for r in q_rows}
        questions["total"] = sum(questions.values())
    except Exception:
        questions = {"total": 0}

    # Recent facts
    try:
        recent = _pg_query(
            "SELECT fact_text, domain, created_at FROM facts ORDER BY created_at DESC LIMIT 10"
        )
        recent_facts = [
            {
                "fact_text": r["fact_text"][:120],
                "domain": r["domain"],
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            }
            for r in recent
        ]
    except Exception:
        recent_facts = []

    return jsonify({
        "domains": domains,
        "total": {
            "count": total_count,
            "target": target_total,
            "pct": round(total_count / target_total * 100, 1) if target_total else 0,
        },
        "sources": {"count": source_count},
        "questions": questions,
        "recent_facts": recent_facts,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


@app.route("/api/scrapers")
@require_auth
def api_scrapers():
    completed = sum(1 for s in SCRAPERS if s["status"] == "complete")
    return jsonify({
        "scrapers": SCRAPERS,
        "phase": {
            "current": "Data Collection (Phase 1)",
            "completed_scrapers": completed,
            "total_scrapers": len(SCRAPERS),
            "pct": round(completed / len(SCRAPERS) * 100, 1),
        },
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

    # Docker container stats (optional)
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
