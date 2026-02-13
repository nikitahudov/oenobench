#!/usr/bin/env bash
# =============================================================================
# WineBench — Backup script
# Dumps PostgreSQL and Neo4j data. Run via cron or manually.
# Usage: ./scripts/backup.sh
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

if [ -f .env ]; then
    set -a; source .env; set +a
fi

BACKUP_DIR="$PROJECT_DIR/data/backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

GREEN='\033[0;32m'
NC='\033[0m'

log() { echo -e "${GREEN}[backup]${NC} $*"; }

mkdir -p "$BACKUP_DIR"

# ─── PostgreSQL dump ──────────────────────────────────────────────────────────
PG_FILE="$BACKUP_DIR/pg_winebench_${TIMESTAMP}.sql.gz"
log "Dumping PostgreSQL → $PG_FILE"
docker compose exec -T postgres pg_dump \
    -U "${POSTGRES_USER:-winebench}" \
    -d "${POSTGRES_DB:-winebench}" \
    --no-owner --no-acl \
    | gzip > "$PG_FILE"
log "PostgreSQL dump: $(du -h "$PG_FILE" | cut -f1)"

# ─── Neo4j dump (via cypher export) ──────────────────────────────────────────
NEO4J_FILE="$BACKUP_DIR/neo4j_export_${TIMESTAMP}.cypher.gz"
log "Exporting Neo4j → $NEO4J_FILE"
docker compose exec -T neo4j cypher-shell \
    -u "${NEO4J_USER:-neo4j}" \
    -p "${NEO4J_PASSWORD}" \
    "CALL apoc.export.cypher.all(null, {stream: true}) YIELD cypherStatements RETURN cypherStatements;" \
    2>/dev/null | gzip > "$NEO4J_FILE"
log "Neo4j export: $(du -h "$NEO4J_FILE" | cut -f1)"

# ─── Cleanup old backups (keep last 7) ───────────────────────────────────────
log "Cleaning up old backups (keeping last 7)..."
ls -t "$BACKUP_DIR"/pg_winebench_*.sql.gz 2>/dev/null | tail -n +8 | xargs rm -f 2>/dev/null || true
ls -t "$BACKUP_DIR"/neo4j_export_*.cypher.gz 2>/dev/null | tail -n +8 | xargs rm -f 2>/dev/null || true

log "Backup complete."
