#!/usr/bin/env bash
# =============================================================================
# OenoBench — Safe docker compose wrapper
#
# Automatically backs up PostgreSQL before destructive operations
# (down, down -v, rm) to prevent accidental data loss.
#
# Usage:  ./scripts/dc.sh down       # backs up, then runs docker compose down
#         ./scripts/dc.sh up -d      # passes through directly (no backup)
#         ./scripts/dc.sh restart    # passes through directly
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

DESTRUCTIVE_CMDS="down rm"

needs_backup() {
    for cmd in $DESTRUCTIVE_CMDS; do
        if [[ "${1:-}" == "$cmd" ]]; then
            return 0
        fi
    done
    return 1
}

if needs_backup "${1:-}"; then
    echo -e "${YELLOW}[dc]${NC} Destructive operation detected: docker compose $*"

    # Check if postgres is running
    if docker compose ps --format '{{.Name}}' 2>/dev/null | grep -q wb-postgres; then
        echo -e "${GREEN}[dc]${NC} Running backup before proceeding..."
        BACKUP_DIR="$PROJECT_DIR/data/backups"
        TIMESTAMP=$(date +%Y%m%d_%H%M%S)
        PG_FILE="$BACKUP_DIR/pg_pre_${1}_${TIMESTAMP}.sql.gz"
        mkdir -p "$BACKUP_DIR"

        if [ -f .env ]; then
            set -a; source .env; set +a
        fi

        docker compose exec -T postgres pg_dump \
            -U "${POSTGRES_USER:-winebench}" \
            -d "${POSTGRES_DB:-winebench}" \
            --no-owner --no-acl \
            | gzip > "$PG_FILE"

        SIZE=$(du -h "$PG_FILE" | cut -f1)
        echo -e "${GREEN}[dc]${NC} Backup saved: $PG_FILE ($SIZE)"
    else
        echo -e "${YELLOW}[dc]${NC} PostgreSQL not running — skipping backup."
    fi

    # Extra warning for -v flag (volume deletion)
    if [[ "$*" == *"-v"* ]]; then
        echo -e "${RED}[dc] WARNING: -v flag will DELETE ALL DOCKER VOLUMES (including database data)!${NC}"
        read -p "Are you sure? Type 'yes' to continue: " confirm
        if [[ "$confirm" != "yes" ]]; then
            echo -e "${YELLOW}[dc]${NC} Aborted."
            exit 1
        fi
    fi
fi

echo -e "${GREEN}[dc]${NC} Running: docker compose $*"
exec docker compose "$@"
