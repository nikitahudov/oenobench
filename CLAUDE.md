# OenoBench — Claude Code Project Guide

## What Is This Project?

OenoBench (formerly WineBench) is a comprehensive AI benchmark for evaluating LLM knowledge across wine-related domains. It targets **5,000 questions** for the **NeurIPS 2026 Datasets & Benchmarks Track** (deadline ~May 15, 2026).

The key innovation is an AI-driven pipeline: automated data collection → multi-model question generation → AI validation → targeted human review.

## Workflow Rules — READ FIRST

### Git & GitHub

- **GitHub is the single source of truth.** Always push commits to GitHub after making changes on the VM. Use `git push` after every commit or logical batch of commits.
- **Always pull before starting work.** The user may also work via Claude Code on the web (claude.ai/code), creating PRs from separate branches. Before starting any task, run `git pull origin main` to pick up merged changes.
- **Use descriptive commit messages.** Each commit should clearly explain what changed and why, so the user can review the git log for a full audit trail.
- **Never force-push or rewrite history on main.** If conflicts arise, resolve them transparently.

### Documentation & Dashboard Updates

- **Update documentation after every change.** Follow the existing "Documentation Maintenance — MANDATORY" rules below. This applies to both code and infrastructure changes.
- **Update the monitoring dashboard data** when scraper status or fact counts change. This means updating the `SCRAPERS` list in `src/dashboard/app.py` to reflect current scraper statuses and known fact counts.
- **Update `CURRENT_STATUS.md`** with every significant change — it is the user's primary progress-tracking document.

### Transparency & Verification

- **The project owner is a wine domain expert.** All wine-related facts, classifications, and domain knowledge can and will be verified by the user. Never fabricate or guess wine facts — use only data from authoritative sources.
- **Show your work.** When running scrapers or making data changes, report: what was run, how many facts were inserted/modified, any errors encountered, and sample outputs.
- **Log all scraper runs.** Every scraper execution must produce a log file in `data/logs/` as specified in the scraper patterns.
- **Flag uncertainty.** If you're unsure about a wine-related classification, domain assignment, or fact accuracy, explicitly flag it for the user's review rather than making assumptions.
- **Provide verification commands.** After making changes, suggest commands the user can run to verify the results (e.g., `--validate` flag, SQL queries, dashboard checks).

### Process Documentation — MANDATORY (for NeurIPS paper)

All significant work on this project must be documented in `docs/PROCESS_LOG.md`. This is a **chronological lab notebook** that will be the primary source for writing the methodology sections of the NeurIPS paper. Every major project phase — data collection, question generation, validation, evaluation — must be traceable from this log. If it isn't logged, it didn't happen.

**After every significant action (scraper build/rebuild/fix, infrastructure change, pipeline step, quality audit, evaluation run), append a dated entry covering:**

1. **What was done** — what was built, fixed, rebuilt, or changed
2. **Sources & inputs** — exact URLs, APIs, datasets, models, or prior pipeline outputs used
3. **Methodology** — how inputs were processed, transformed, or evaluated. Include algorithms, heuristics, prompts, and any source-specific handling
4. **Quality controls** — what was filtered, rejected, or flagged, with counts and reasons
5. **Quantitative results** — counts, distributions, acceptance/rejection rates, before/after comparisons
6. **Decisions & trade-offs** — what alternatives were considered, why this approach was chosen, what was sacrificed
7. **Issues encountered & resolutions** — failures, bugs, unexpected results, and how each was resolved
8. **Human review notes** — any decisions made by the domain expert (sample reviews, quality judgments, coverage priorities)

**Format guidelines:**
- Each entry is a dated section with a phase label (e.g., `## 2026-04-11 — Phase 0: Shared Infrastructure`)
- Keep it factual and quantitative — lab notebook style, not prose
- Include before/after counts where relevant
- Group by project phase when multiple things happen on one day

**At the end of each major phase,** compile the relevant log entries into a structured summary in `docs/` (e.g., `DATA_COLLECTION_SUMMARY.md`, `QUESTION_GENERATION_SUMMARY.md`). These summaries should be paper-ready: concise, quantitative, with tables and statistics that can be directly cited or adapted into paper prose.

## Repository Structure

```
~/oenobench/
├── CLAUDE.md                     # ← You are here. Read this first.
├── README.md                     # Public-facing project overview
├── PROJECT_PLAN.md               # Full project plan with methodology
├── DATA_SOURCES.md               # Data source inventory & scraping strategy
├── SCRAPER_PROMPTS.md            # Detailed prompts for each scraper
├── CURRENT_STATUS.md             # Progress tracking (current phase, blockers, next steps)
├── requirements.txt
├── docker-compose.yml            # PostgreSQL, Elasticsearch, Neo4j, Redis
├── .env.example                  # Environment template (copy to .env)
├── docs/
│   ├── PROCESS_LOG.md            # Chronological lab notebook — phase history lives here
│   ├── ARCHITECTURE.md
│   ├── QUALITY_AUDIT_REPORT.md   # Latest audit results
│   ├── GENERATION_IMPROVEMENT_PLAN.md  # Ranked defect list + Go/No-Go gates
│   └── DATA_COLLECTION_SUMMARY.md
├── config/postgres/init.sql      # PostgreSQL schema (auto-runs on first docker compose up)
├── scripts/                      # setup.sh, health.sh, backup.sh, run_audit_pilot_v*_*.sh
├── src/
│   ├── utils/                    # db.py, facts.py — shared connections + fact insertion
│   ├── scrapers/                 # 35 genuine scrapers + _fact_processing/_web_helpers/_wiki_helpers
│   ├── generators/               # Phase 2 — 5 question-generation strategies + orchestrator
│   ├── qa/                       # Phase 2c — multi-agent quality audit (4 teams, 9 agents)
│   ├── evaluation/               # Phase 3 placeholder + cb_split.py
│   └── dashboard/                # Flask monitoring dashboard
├── tests/                        # generators/ and qa/ pytest suites
└── data/                         # Not in git — raw/, processed/, logs/, reports/, backups/, exports/
```

For per-scraper details (status, fact counts, source), see `CURRENT_STATUS.md`. For phase-by-phase implementation history, see `docs/PROCESS_LOG.md`.

## Current Status

See `CURRENT_STATUS.md` for the authoritative current-phase summary, blockers, and next steps. `docs/PROCESS_LOG.md` is the chronological lab notebook of all phases shipped.

High-level snapshot:
- **Phase 1 (Data Collection):** ✅ 38,104 facts from 35 genuine scrapers
- **Phase 2 (Question Generation):** ✅ 5 strategies built, iteratively tuned through Phase 2g.11
- **Phase 2c (Quality Audit):** ✅ 9 agents across 4 teams; latest audit cycle is `audit_pilot_v9`

Always read `CURRENT_STATUS.md` at the start of a session to find the immediate next command.

## Documentation Maintenance — MANDATORY

After every PR or significant change, update all relevant documentation before committing. This is not optional — accurate docs are critical for this multi-session project where each Claude Code session relies on CLAUDE.md and other docs to understand the current state.

### What to update and when

**After implementing a new scraper:**
1. `CURRENT_STATUS.md` — Update the scraper status table (status, actual fact count). Add a "Completed Scraper Details" entry. Update "Total raw facts collected" and "Domain Coverage Assessment" if coverage changed.
2. `SCRAPER_PROMPTS.md` — Mark the scraper as done in the "Execution Order Summary" table. Update the shared context block if the new scraper serves as a good reference for future scrapers.

**After changing utility code (`src/utils/`):**
1. `CLAUDE.md` — Update the "Database Utilities" section with any new/changed function signatures, parameters, or return values. Update the "Fact dict format" example if the schema changed.
2. `SCRAPER_PROMPTS.md` — Update the shared context block that all future scraper prompts reference.

**After changing infrastructure (`docker-compose.yml`, `config/`, `scripts/`):**
1. `CLAUDE.md` — Update the "Infrastructure" section.
2. `README.md` — Update the "Tech Stack" and "Getting Started" sections if setup steps changed.

**After changing the database schema (`config/postgres/init.sql`):**
1. `CLAUDE.md` — Update the "PostgreSQL Schema" table.
2. `PROJECT_PLAN.md` — Update if schema changes affect the methodology or data model sections.

**After reaching a project milestone:**
1. `CURRENT_STATUS.md` — Update the phase status table, mark phases complete, update next steps.
2. `README.md` — Update the "Current Status" paragraph.
3. `docs/PROCESS_LOG.md` — Append a dated phase-summary entry.

### Rules

- Always update `CURRENT_STATUS.md` "Last updated" date when making changes to it.
- Never leave stale fact counts — if you know the count, update it; if you don't, use "—" (not a guess).
- The `SCRAPER_PROMPTS.md` shared context block is pasted into every new scraper session — it must always reflect the current state of utilities and completed scrapers.
- Phase-by-phase changelogs go in `docs/PROCESS_LOG.md`, not CLAUDE.md. Keep CLAUDE.md focused on durable patterns and pointers.

## Critical Patterns — READ BEFORE WRITING CODE

### Database Utilities

Always use the existing utilities in `src/utils/`:

```python
from src.utils.db import get_pg, get_es, get_neo4j, get_redis
from src.utils.facts import ensure_source, insert_facts_batch, insert_fact, get_fact_count
```

**`src/utils/db.py`** — Connection helpers (all cached with `@lru_cache`):
- `get_pg()` — Returns a `psycopg2` connection (with `RealDictCursor`)
- `get_es()` — Returns an `Elasticsearch` client
- `get_neo4j()` — Returns a Neo4j `GraphDatabase.driver`
- `get_redis()` — Returns a Redis client

**`src/utils/facts.py`** — Fact storage:
- `ensure_source(name, url, source_type, tier="tier_3_reliable", language="en")` — Register a data source, returns UUID. Deduplicates on URL.
- `insert_facts_batch(facts, batch_size=100)` — Bulk insert list of fact dicts. Deduplicates on exact `fact_text`. Returns count inserted.
- `insert_fact(fact_text, domain, source_id, subdomain=None, entities=None, confidence=1.0, tags=None)` — Insert a single fact. Returns UUID or None if duplicate.
- `get_fact_count(domain=None)` — Count facts, optionally filtered by domain.

**Fact dict format** (for `insert_facts_batch`):
```python
{
    "fact_text": "Barolo DOCG requires 100% Nebbiolo.",
    "domain": "wine_regions",
    "source_id": "<uuid from ensure_source>",
    "subdomain": "italy_piedmont",     # optional
    "entities": [{"type": "grape", "name": "Nebbiolo"}],  # optional
    "confidence": 1.0,                 # optional, default 1.0
    "tags": ["docg", "piedmont"],      # optional
}
```

### Scraper CLI Pattern

Every scraper MUST follow this CLI pattern (using `click`):

```bash
python -m src.scrapers.<name> --all          # Run full extraction
python -m src.scrapers.<name> --dry-run      # Preview without DB writes
python -m src.scrapers.<name> --validate     # Quality checks on extracted data
python -m src.scrapers.<name> --list         # List available sub-sources
python -m src.scrapers.<name> --test-run     # Small test run with cleanup option
# Plus source-specific filters (--region, --country, --dataset, --source, etc.)
```

### Fact Quality Rules

1. **Atomic facts only** — One fact per sentence: "Barolo DOCG requires 100% Nebbiolo."
2. **Never store verbatim source text** — Always rephrase into atomic facts
3. **Domain values** (PostgreSQL enum): `wine_regions`, `grape_varieties`, `producers`, `viticulture`, `winemaking`, `wine_business`
4. **Rate limiting:** All HTTP requests must be rate-limited (see per-scraper specs in `SCRAPER_PROMPTS.md`)
5. **User-Agent:** `"OenoBench-Research/1.0 (academic wine benchmark)"`
6. **Logging:** Use `loguru`. Write to `data/logs/<scraper_name>_{timestamp}.log`

### Validation Flag (--validate)

Every scraper must include `--validate` that reports:
- Fact count per domain/subdomain
- Suspiciously short (<5 words) or long (>50 words) facts
- Facts that are just entity names with no predicate
- Near-duplicate detection (substring matching)
- % of facts with populated vs empty entity fields
- 10 random sample facts for manual review

## Key Design Decisions

- **Multi-model question generation:** Claude (30%), GPT-4 (30%), Gemini (20%), Llama (10%), templates (10%)
- **300-question human-authored control set** for bias analysis
- **Self-Preference Score (SPS)** analysis: do models score better on their own questions?
- **Held-out evaluation subsets:** each model tested on questions it didn't generate
- **Target 15,000-20,000 unique facts** after deduplication (from ~35,000-42,000 raw)

## Infrastructure

- **PostgreSQL 16** (pgvector) — Structured facts, sources, metadata, questions, evaluation results
- **Elasticsearch 8.x** — Full-text search with wine-specific synonym analyzer
- **Neo4j 5.x** (community) — Knowledge graph of wine entity relationships
- **Redis 7.x** — Caching layer, job queues, rate-limit tracking
- All running in Docker containers (`docker-compose.yml`)
- Database credentials in `.env` file (not committed to git)
- Schema initialized automatically via `config/postgres/init.sql`

**Key Docker container names:** `wb-postgres`, `wb-elasticsearch`, `wb-neo4j`, `wb-redis`

**Database name:** `winebench` (historical, predates rename to OenoBench)

**Monitoring Dashboard:** `python -m src.dashboard.app` — Flask app on port 5555 (configurable via `DASHBOARD_PORT`). HTTP Basic Auth via `DASHBOARD_USER`/`DASHBOARD_PASSWORD` in `.env`. Shows fact collection progress, scraper status, and infrastructure health with 30s auto-refresh.

### PostgreSQL Schema (key tables)

| Table | Purpose |
|-------|---------|
| `sources` | Data source registry (name, URL, tier) |
| `facts` | Atomic facts with domain, entities, embeddings |
| `questions` | Benchmark questions (5,000 target) |
| `question_facts` | Links questions to supporting facts |
| `generation_metadata` | Which LLM generated each question |
| `validation_records` | AI + human review results |
| `evaluation_runs` | LLM benchmark run metadata |
| `evaluation_answers` | Per-question LLM answers |

See `config/postgres/init.sql` for full schema with enums, indexes, views, and triggers.

## Quick Reference: Fact Targets by Domain

| Domain | Target Facts | Status |
|--------|-------------|--------|
| Wine Regions | 5,000 | In progress (best coverage from Wikidata) |
| Grape Varieties | 2,000 | In progress (good from Wikidata + UC Davis) |
| Producers | 3,000 | In progress (some from Wikidata + HuggingFace) |
| Viticulture | 1,500 | Needs more coverage |
| Winemaking | 1,500 | Needs more coverage |
| Wine Business | 1,000 | Needs more coverage |

## What to Work On Next

Read `CURRENT_STATUS.md` first — it has the immediate next command, current blockers, and any pending user actions (gold reviews, sign-offs).

For phase-level history and methodology details, see `docs/PROCESS_LOG.md`. For the ranked defect list and Go/No-Go gates on the active audit cycle, see `docs/GENERATION_IMPROVEMENT_PLAN.md`.

## Important Links

- **Full project plan:** `PROJECT_PLAN.md`
- **Data sources:** `DATA_SOURCES.md`
- **Scraper implementation specs:** `SCRAPER_PROMPTS.md`
- **Progress tracking:** `CURRENT_STATUS.md`
- **Process log (lab notebook):** `docs/PROCESS_LOG.md`
- **Latest audit report:** `docs/QUALITY_AUDIT_REPORT.md`
- **Latest improvement plan + Go/No-Go gate:** `docs/GENERATION_IMPROVEMENT_PLAN.md`
- **NeurIPS 2026 D&B Track:** Target submission venue
