#!/usr/bin/env bash
# =============================================================================
# WineBench — Health check script
# Usage: ./scripts/health.sh
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

# Load env
if [ -f .env ]; then
    set -a; source .env; set +a
fi

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'
BOLD='\033[1m'

echo ""
echo -e "${BOLD}  WineBench Health Check${NC}"
echo "  ─────────────────────────────────────────"

PASS=0
FAIL=0

check() {
    local name="$1"
    local cmd="$2"
    local detail="$3"

    if eval "$cmd" &>/dev/null; then
        echo -e "  ${GREEN}✓${NC} ${name}  ${detail}"
        PASS=$((PASS + 1))
    else
        echo -e "  ${RED}✗${NC} ${name}  ${detail}"
        FAIL=$((FAIL + 1))
    fi
}

# PostgreSQL
PG_VER=$(docker compose exec -T postgres psql -U "${POSTGRES_USER:-winebench}" -d "${POSTGRES_DB:-winebench}" -tAc "SELECT version();" 2>/dev/null | head -1 | grep -oP 'PostgreSQL \d+\.\d+' || echo "unknown")
check "PostgreSQL" \
    "docker compose exec -T postgres pg_isready -U ${POSTGRES_USER:-winebench}" \
    "(${PG_VER}, port ${POSTGRES_PORT:-5432})"

# Table count
TBL_COUNT=$(docker compose exec -T postgres psql -U "${POSTGRES_USER:-winebench}" -d "${POSTGRES_DB:-winebench}" -tAc "SELECT count(*) FROM information_schema.tables WHERE table_schema='public';" 2>/dev/null || echo "?")
echo -e "         ${TBL_COUNT} tables in public schema"

# Elasticsearch
ES_STATUS=$(curl -sf "http://localhost:${ES_PORT:-9200}/_cluster/health" 2>/dev/null | grep -oP '"status":"\K[^"]+' || echo "unknown")
check "Elasticsearch" \
    "curl -sf http://localhost:${ES_PORT:-9200}/_cluster/health" \
    "(status: ${ES_STATUS}, port ${ES_PORT:-9200})"

# Index count
IDX_COUNT=$(curl -sf "http://localhost:${ES_PORT:-9200}/_cat/indices?h=index" 2>/dev/null | grep winebench | wc -l || echo "?")
echo -e "         ${IDX_COUNT} winebench indices"

# Neo4j
check "Neo4j" \
    "curl -sf http://localhost:${NEO4J_HTTP_PORT:-7474}" \
    "(browser: ${NEO4J_HTTP_PORT:-7474}, bolt: ${NEO4J_BOLT_PORT:-7687})"

# Redis
check "Redis" \
    "docker compose exec -T redis redis-cli -a ${REDIS_PASSWORD:-nopass} ping 2>/dev/null | grep -q PONG" \
    "(port ${REDIS_PORT:-6379})"

# Memory usage
echo ""
echo -e "${BOLD}  Resource Usage${NC}"
echo "  ─────────────────────────────────────────"
docker stats --no-stream --format "  {{.Name}}:\t{{.MemUsage}}\t{{.CPUPerc}}" 2>/dev/null | grep wb- | sort || echo "  (could not read stats)"

# Summary
echo ""
echo "  ─────────────────────────────────────────"
if [ $FAIL -eq 0 ]; then
    echo -e "  ${GREEN}All ${PASS} services healthy${NC}"
else
    echo -e "  ${GREEN}${PASS} healthy${NC}, ${RED}${FAIL} failing${NC}"
    echo "  Run 'docker compose logs <service>' to diagnose."
fi
echo ""
