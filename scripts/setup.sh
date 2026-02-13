#!/usr/bin/env bash
# =============================================================================
# WineBench — First-time setup script
# Run this once on a fresh DigitalOcean droplet.
#
# Prerequisites: Ubuntu 22.04+ droplet with SSH access
# Usage: chmod +x scripts/setup.sh && ./scripts/setup.sh
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log()  { echo -e "${GREEN}[WineBench]${NC} $*"; }
warn() { echo -e "${YELLOW}[WARNING]${NC} $*"; }
err()  { echo -e "${RED}[ERROR]${NC} $*" >&2; }

# ─── 1. System dependencies ──────────────────────────────────────────────────

install_docker() {
    if command -v docker &>/dev/null; then
        log "Docker already installed: $(docker --version)"
        return
    fi

    log "Installing Docker..."
    sudo apt-get update -qq
    sudo apt-get install -y -qq ca-certificates curl gnupg
    sudo install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    sudo chmod a+r /etc/apt/keyrings/docker.gpg

    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
      $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
      sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

    sudo apt-get update -qq
    sudo apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

    # Allow current user to use Docker without sudo
    sudo usermod -aG docker "${USER}" 2>/dev/null || true
    log "Docker installed. You may need to log out and back in for group changes."
}

# ─── 2. System tuning for Elasticsearch ──────────────────────────────────────

tune_system() {
    log "Tuning system settings..."

    # Elasticsearch requires vm.max_map_count >= 262144
    CURRENT_MAP_COUNT=$(sysctl -n vm.max_map_count 2>/dev/null || echo "0")
    if [ "$CURRENT_MAP_COUNT" -lt 262144 ]; then
        log "Setting vm.max_map_count=262144 (required by Elasticsearch)"
        sudo sysctl -w vm.max_map_count=262144
        echo "vm.max_map_count=262144" | sudo tee -a /etc/sysctl.conf > /dev/null
    fi

    # Increase file descriptor limits
    if ! grep -q "winebench" /etc/security/limits.conf 2>/dev/null; then
        log "Increasing file descriptor limits..."
        cat <<EOF | sudo tee -a /etc/security/limits.conf > /dev/null
# WineBench — increased limits for Elasticsearch
* soft nofile 65536
* hard nofile 65536
EOF
    fi
}

# ─── 3. Environment file ─────────────────────────────────────────────────────

setup_env() {
    cd "$PROJECT_DIR"

    if [ -f .env ]; then
        log ".env already exists, skipping creation."
        return
    fi

    log "Creating .env from template..."
    cp .env.example .env

    # Generate random passwords
    PG_PASS=$(openssl rand -base64 24 | tr -dc 'a-zA-Z0-9' | head -c 24)
    NEO4J_PASS=$(openssl rand -base64 24 | tr -dc 'a-zA-Z0-9' | head -c 24)
    REDIS_PASS=$(openssl rand -base64 24 | tr -dc 'a-zA-Z0-9' | head -c 24)

    sed -i "s/CHANGE_ME_pg_secure_password_here/$PG_PASS/" .env
    sed -i "s/CHANGE_ME_neo4j_secure_password_here/$NEO4J_PASS/" .env
    sed -i "s/CHANGE_ME_redis_secure_password_here/$REDIS_PASS/" .env

    log "Generated random passwords in .env"
    warn "Add your LLM API keys to .env before running the application."
    echo ""
    echo "  Generated credentials (also saved in .env):"
    echo "  ─────────────────────────────────────────────"
    echo "  PostgreSQL: winebench / $PG_PASS"
    echo "  Neo4j:      neo4j / $NEO4J_PASS"
    echo "  Redis:      $REDIS_PASS"
    echo ""
}

# ─── 4. Create data directories ──────────────────────────────────────────────

setup_dirs() {
    log "Creating data directories..."
    mkdir -p "$PROJECT_DIR/data"/{raw,processed,exports,backups}
}

# ─── 5. Start services ───────────────────────────────────────────────────────

start_services() {
    cd "$PROJECT_DIR"
    log "Pulling Docker images..."
    docker compose pull

    log "Starting services..."
    docker compose up -d

    log "Waiting for services to become healthy..."
    local max_wait=120
    local elapsed=0

    while [ $elapsed -lt $max_wait ]; do
        local healthy
        healthy=$(docker compose ps --format json 2>/dev/null | grep -c '"healthy"' || echo "0")
        local total
        total=$(docker compose ps --format json 2>/dev/null | grep -c '"running"\|"healthy"' || echo "0")

        if [ "$healthy" -ge 4 ]; then
            log "All 4 services healthy!"
            return 0
        fi

        echo -ne "\r  Waiting... ${elapsed}s (${healthy}/4 healthy)"
        sleep 5
        elapsed=$((elapsed + 5))
    done

    echo ""
    warn "Timeout waiting for all services. Checking status..."
    docker compose ps
    return 1
}

# ─── 6. Verify services ──────────────────────────────────────────────────────

verify_services() {
    cd "$PROJECT_DIR"
    log "Verifying services..."

    echo ""

    # PostgreSQL
    if docker compose exec -T postgres pg_isready -U winebench -d winebench &>/dev/null; then
        echo -e "  ${GREEN}✓${NC} PostgreSQL — ready on port ${POSTGRES_PORT:-5432}"
    else
        echo -e "  ${RED}✗${NC} PostgreSQL — not responding"
    fi

    # Elasticsearch
    if curl -sf http://localhost:${ES_PORT:-9200}/_cluster/health &>/dev/null; then
        echo -e "  ${GREEN}✓${NC} Elasticsearch — ready on port ${ES_PORT:-9200}"
    else
        echo -e "  ${RED}✗${NC} Elasticsearch — not responding"
    fi

    # Neo4j
    if curl -sf http://localhost:${NEO4J_HTTP_PORT:-7474} &>/dev/null; then
        echo -e "  ${GREEN}✓${NC} Neo4j — browser on port ${NEO4J_HTTP_PORT:-7474}, bolt on ${NEO4J_BOLT_PORT:-7687}"
    else
        echo -e "  ${RED}✗${NC} Neo4j — not responding"
    fi

    # Redis
    if docker compose exec -T redis redis-cli -a "${REDIS_PASSWORD:-}" ping 2>/dev/null | grep -q PONG; then
        echo -e "  ${GREEN}✓${NC} Redis — ready on port ${REDIS_PORT:-6379}"
    else
        echo -e "  ${RED}✗${NC} Redis — not responding"
    fi

    echo ""
}

# ─── 7. Setup Elasticsearch indices ──────────────────────────────────────────

setup_elasticsearch() {
    log "Creating Elasticsearch indices..."

    # Facts index with dense_vector for embeddings
    curl -sf -X PUT "http://localhost:${ES_PORT:-9200}/winebench_facts" \
        -H 'Content-Type: application/json' \
        -d '{
            "settings": {
                "number_of_shards": 1,
                "number_of_replicas": 0,
                "analysis": {
                    "analyzer": {
                        "wine_analyzer": {
                            "type": "custom",
                            "tokenizer": "standard",
                            "filter": ["lowercase", "asciifolding", "wine_synonyms"]
                        }
                    },
                    "filter": {
                        "wine_synonyms": {
                            "type": "synonym",
                            "synonyms": [
                                "cab sav, cabernet sauvignon",
                                "sav blanc, sauvignon blanc",
                                "pinot noir, spätburgunder",
                                "syrah, shiraz",
                                "garnacha, grenache",
                                "tempranillo, tinto fino, tinta roriz"
                            ]
                        }
                    }
                }
            },
            "mappings": {
                "properties": {
                    "fact_id":      { "type": "keyword" },
                    "fact_text":    { "type": "text", "analyzer": "wine_analyzer" },
                    "domain":       { "type": "keyword" },
                    "subdomain":    { "type": "keyword" },
                    "entities":     { "type": "nested", "properties": {
                        "type": { "type": "keyword" },
                        "name": { "type": "text" }
                    }},
                    "source_tier":  { "type": "keyword" },
                    "tags":         { "type": "keyword" },
                    "embedding":    { "type": "dense_vector", "dims": 1536, "index": true, "similarity": "cosine" },
                    "created_at":   { "type": "date" }
                }
            }
        }' > /dev/null 2>&1 && echo -e "  ${GREEN}✓${NC} Index: winebench_facts" || echo -e "  ${YELLOW}⚠${NC} Index winebench_facts may already exist"

    # Questions index for deduplication
    curl -sf -X PUT "http://localhost:${ES_PORT:-9200}/winebench_questions" \
        -H 'Content-Type: application/json' \
        -d '{
            "settings": {
                "number_of_shards": 1,
                "number_of_replicas": 0
            },
            "mappings": {
                "properties": {
                    "question_id":   { "type": "keyword" },
                    "question_text": { "type": "text" },
                    "domain":        { "type": "keyword" },
                    "difficulty":    { "type": "keyword" },
                    "generator":     { "type": "keyword" },
                    "status":        { "type": "keyword" },
                    "embedding":     { "type": "dense_vector", "dims": 1536, "index": true, "similarity": "cosine" },
                    "created_at":    { "type": "date" }
                }
            }
        }' > /dev/null 2>&1 && echo -e "  ${GREEN}✓${NC} Index: winebench_questions" || echo -e "  ${YELLOW}⚠${NC} Index winebench_questions may already exist"

    echo ""
}

# ─── 8. Setup Neo4j constraints ───────────────────────────────────────────────

setup_neo4j() {
    log "Creating Neo4j constraints and indexes..."

    source "$PROJECT_DIR/.env"

    local CYPHER_CMD="docker compose exec -T neo4j cypher-shell -u ${NEO4J_USER:-neo4j} -p ${NEO4J_PASSWORD}"

    # Node constraints
    $CYPHER_CMD "CREATE CONSTRAINT IF NOT EXISTS FOR (r:Region) REQUIRE r.name IS UNIQUE;" 2>/dev/null
    $CYPHER_CMD "CREATE CONSTRAINT IF NOT EXISTS FOR (g:Grape) REQUIRE g.name IS UNIQUE;" 2>/dev/null
    $CYPHER_CMD "CREATE CONSTRAINT IF NOT EXISTS FOR (p:Producer) REQUIRE p.name IS UNIQUE;" 2>/dev/null
    $CYPHER_CMD "CREATE CONSTRAINT IF NOT EXISTS FOR (a:Appellation) REQUIRE a.name IS UNIQUE;" 2>/dev/null
    $CYPHER_CMD "CREATE CONSTRAINT IF NOT EXISTS FOR (t:Technique) REQUIRE t.name IS UNIQUE;" 2>/dev/null
    $CYPHER_CMD "CREATE CONSTRAINT IF NOT EXISTS FOR (c:Classification) REQUIRE c.name IS UNIQUE;" 2>/dev/null

    echo -e "  ${GREEN}✓${NC} Neo4j constraints created"
    echo ""
}

# ─── Main ─────────────────────────────────────────────────────────────────────

main() {
    echo ""
    echo "  ╔═══════════════════════════════════════════╗"
    echo "  ║     WineBench Infrastructure Setup        ║"
    echo "  ║     PostgreSQL · ES · Neo4j · Redis       ║"
    echo "  ╚═══════════════════════════════════════════╝"
    echo ""

    install_docker
    tune_system
    setup_env
    setup_dirs

    # Source .env for variable access
    set -a
    source "$PROJECT_DIR/.env"
    set +a

    start_services
    verify_services
    setup_elasticsearch
    setup_neo4j

    echo ""
    log "Setup complete! Infrastructure is ready."
    echo ""
    echo "  Next steps:"
    echo "  ─────────────────────────────────────────"
    echo "  1. Add your LLM API keys to .env"
    echo "  2. Verify: ./scripts/health.sh"
    echo "  3. Neo4j browser: http://localhost:${NEO4J_HTTP_PORT:-7474}"
    echo "  4. Start building your scraping pipelines"
    echo ""
}

main "$@"
