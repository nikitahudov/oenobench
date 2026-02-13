# WineBench Infrastructure

Docker-based infrastructure for the WineBench wine knowledge LLM benchmark.

## Services

| Service | Port | Purpose |
|---------|------|---------|
| **PostgreSQL 16** (pgvector) | 5432 | Structured facts, questions, evaluation results |
| **Elasticsearch 8.13** | 9200 | Full-text search, embedding similarity, deduplication |
| **Neo4j 5.19** | 7474 (browser), 7687 (bolt) | Wine entity knowledge graph |
| **Redis 7** | 6379 | Caching, scraping job queues, rate-limit tracking |

## Quick Start

```bash
# 1. Clone and configure
cp .env.example .env
# Edit .env — at minimum set passwords (or let setup.sh generate them)

# 2. Run setup (installs Docker if needed, tunes system, starts everything)
chmod +x scripts/*.sh
./scripts/setup.sh

# 3. Verify
./scripts/health.sh
```

## Directory Structure

```
winebench-infra/
├── docker-compose.yml          # Service definitions
├── .env.example                # Environment template
├── .env                        # Your secrets (git-ignored)
├── config/
│   └── postgres/
│       └── init.sql            # Schema: facts, questions, evaluation tables
├── scripts/
│   ├── setup.sh                # First-time setup
│   ├── health.sh               # Health check
│   └── backup.sh               # PostgreSQL + Neo4j backup
└── data/
    ├── raw/                    # Scraped documents
    ├── processed/              # Cleaned/extracted data
    ├── exports/                # Dataset exports
    └── backups/                # Database dumps
```

## PostgreSQL Schema

Core tables created by `init.sql`:

- **sources** — authoritative data sources with quality tiers
- **facts** — verified atomic wine knowledge with embeddings
- **questions** — the 5,000-question benchmark dataset
- **question_facts** — traceability from questions → source facts
- **generation_metadata** — which LLM generated each question
- **validation_records** — AI and human review results
- **evaluation_runs / evaluation_answers** — LLM benchmark scores

Includes views for distribution analysis (`v_question_distribution`),
generator breakdown (`v_generator_distribution`), and self-preference
analysis (`v_self_preference`).

## Common Commands

```bash
# Start/stop
docker compose up -d
docker compose down

# Logs
docker compose logs -f postgres
docker compose logs -f elasticsearch

# PostgreSQL shell
docker compose exec postgres psql -U winebench -d winebench

# Neo4j shell
docker compose exec neo4j cypher-shell -u neo4j -p <password>

# Redis CLI
docker compose exec redis redis-cli -a <password>

# Backup
./scripts/backup.sh

# Reset everything (DESTROYS DATA)
docker compose down -v
```

## Resource Requirements

| Config | RAM | vCPUs | Notes |
|--------|-----|-------|-------|
| Minimum | 4 GB | 2 | Tight — ES may struggle under load |
| Recommended | 8 GB | 4 | Comfortable for all services + scraping |
| With scraping pipeline running | 8+ GB | 4 | Headroom for Playwright/Scrapy |

All services bind to `127.0.0.1` by default — not exposed publicly.
Use SSH tunnels or a reverse proxy for remote access.
