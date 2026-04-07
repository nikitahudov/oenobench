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

## Repository Structure

```
~/oenobench/
├── CLAUDE.md                     # ← You are here. Read this first.
├── README.md                     # Public-facing project overview
├── PROJECT_PLAN.md               # Full project plan with methodology
├── DATA_SOURCES.md               # Data source inventory & scraping strategy
├── SCRAPER_PROMPTS.md            # Detailed prompts for each scraper
├── CURRENT_STATUS.md             # Progress tracking
├── requirements.txt              # Python dependencies
├── docker-compose.yml            # PostgreSQL, Elasticsearch, Neo4j, Redis
├── .env.example                  # Environment template (copy to .env)
├── .env                          # Database credentials (not in git)
├── .gitignore
├── config/
│   └── postgres/
│       └── init.sql              # PostgreSQL schema (auto-runs on first docker compose up)
├── scripts/
│   ├── setup.sh                  # First-time infrastructure setup
│   ├── health.sh                 # Service health check
│   └── backup.sh                 # PostgreSQL & Neo4j backup
├── src/
│   ├── __init__.py
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── db.py                 # PostgreSQL, Elasticsearch, Neo4j, Redis connections
│   │   └── facts.py              # ensure_source(), insert_facts_batch(), get_fact_count()
│   ├── scrapers/
│   │   ├── __init__.py
│   │   ├── wikidata.py           # ✅ Done — Wikidata SPARQL (20,910 facts)
│   │   ├── wikipedia.py          # ✅ Done — Wikipedia MediaWiki API
│   │   ├── huggingface.py        # ✅ Done — HuggingFace datasets (16,514 facts)
│   │   ├── ucdavis.py            # ✅ Done — UC Davis ontology, AVA, FPS
│   │   ├── kaggle_data.py        # ✅ Done — Kaggle wine-quality & wine-reviews (1,509 facts)
│   │   ├── inao.py              # ✅ Done — INAO French appellations (1,473 facts)
│   │   ├── italian_wine_central.py  # ✅ Done — Italian Wine Central (1,556 facts)
│   │   ├── austria.py              # ✅ Done — Austrian Wine (731 facts)
│   │   ├── greece.py               # ✅ Done — Greek Wine (587 facts)
│   │   ├── rhone_loire_alsace.py   # ✅ Done — Rhône/Loire/Alsace (763 facts)
│   │   ├── spain_enrichment.py    # ✅ Done — Spain enrichment (493 facts)
│   │   ├── portugal_enrichment.py # ✅ Done — Portugal enrichment (438 facts)
│   │   ├── south_america.py       # ✅ Done — Argentina & Chile (393 facts)
│   │   ├── australia_nz_enrichment.py # ✅ Done — Australia & NZ (391 facts)
│   │   ├── hungary_georgia.py     # ✅ Done — Hungary & Georgia (429 facts)
│   │   ├── germany_enrichment.py  # ✅ Done — Germany enrichment (333 facts)
│   │   ├── canada.py              # ✅ Done — Canada (268 facts)
│   │   ├── croatia_slovenia.py    # ✅ Done — Croatia & Slovenia (391 facts)
│   │   ├── england.py             # ✅ Done — England (225 facts)
│   │   ├── lebanon_israel.py      # ✅ Done — Lebanon & Israel (182 facts)
│   │   ├── south_africa_enrichment.py # ✅ Done — South Africa (339 facts)
│   │   └── usa_enrichment.py      # ✅ Done — USA enrichment (632 facts)
│   ├── dashboard/
│   │   ├── __init__.py
│   │   ├── app.py                # Flask monitoring dashboard (python -m src.dashboard.app)
│   │   ├── templates/
│   │   │   └── index.html        # Dashboard single-page template
│   │   └── static/
│   │       ├── css/style.css     # Dark theme styles
│   │       └── js/dashboard.js   # Auto-refresh polling logic
│   ├── evaluation/
│   │   └── __init__.py           # Placeholder — future evaluation pipeline
│   ├── generators/
│   │   └── __init__.py           # Placeholder — future question generation
│   ├── processors/
│   │   └── __init__.py           # Placeholder — future data processing
│   └── validators/
│       └── __init__.py           # Placeholder — future validation pipeline
├── tests/
│   └── __init__.py
└── data/                         # Not in git (see .gitignore)
    ├── raw/                      # Downloaded datasets
    ├── processed/                # Processed outputs
    ├── logs/                     # Scraper run logs
    ├── reports/                  # Verification reports
    ├── backups/                  # Database backups
    └── exports/                  # Data exports
```

### Files Not Yet Created (Planned)

These scrapers are specified in `SCRAPER_PROMPTS.md` but have not been implemented yet:

| File | Scraper | Target |
|------|---------|--------|
| ~~`src/scrapers/inao.py`~~ | ~~INAO French appellations~~ | ~~2,000-3,000 facts~~ ✅ Done (1,473 facts) |
| `src/scrapers/italy.py` | Italian registries | 1,500-2,000 facts |
| `src/scrapers/ttb.py` | US TTB regulations | 500-800 facts |
| `src/scrapers/europe.py` | Spain, Germany, Portugal | 1,500-2,400 facts |
| `src/scrapers/newworld.py` | Australia, NZ, South Africa, South America | 800-1,200 facts |
| `src/scrapers/eu_oiv.py` | EU regulations & OIV | 500-800 facts |
| `src/scrapers/regional_france.py` | Burgundy, Champagne, Bordeaux | 800-1,500 facts |
| `src/scrapers/consortiums_italy.py` | Italian consortiums | 400-600 facts |
| `src/scrapers/academic.py` | Journal abstracts | 500-800 facts |
| `src/scrapers/verify.py` | Post-scraping gap analysis | N/A |

## Current Status (as of March 2026)

**Phase:** Data Collection (Phase 1)
**Facts collected:** ~43,000+ raw facts (27,408 in DB after dedup)
**Completed scrapers:** 24 enrichment scrapers + 6 original

| # | Scraper | Status | Facts |
|---|---------|--------|-------|
| 1 | Wikidata (`wikidata.py`) | ✅ Complete | 20,910 |
| 2 | Wikipedia (`wikipedia.py`) | ✅ Complete | — |
| 3 | HuggingFace (`huggingface.py`) | ✅ Complete | 16,514 |
| 4 | UC Davis (`ucdavis.py`) | ✅ Complete | — |
| 5 | Kaggle (`kaggle_data.py`) | ✅ Complete | 1,509 |
| 6 | INAO (`inao.py`) | ✅ Complete | 1,473 |
| 15 | Italian Wine Central (`italian_wine_central.py`) | ✅ Complete | 1,556 |
| 16 | Austrian Wine (`austria.py`) | ✅ Complete | 731 |
| 17 | Greek Wine (`greece.py`) | ✅ Complete | 587 |
| 18 | Rhône/Loire/Alsace (`rhone_loire_alsace.py`) | ✅ Complete | 763 |
| 19 | Spain Enrichment (`spain_enrichment.py`) | ✅ Complete | 493 |
| 20 | Portugal Enrichment (`portugal_enrichment.py`) | ✅ Complete | 438 |
| 21 | South America (`south_america.py`) | ✅ Complete | 393 |
| 22 | Australia/NZ (`australia_nz_enrichment.py`) | ✅ Complete | 391 |
| 23 | Hungary & Georgia (`hungary_georgia.py`) | ✅ Complete | 429 |
| 24 | Germany Enrichment (`germany_enrichment.py`) | ✅ Complete | 333 |
| 25 | Canada (`canada.py`) | ✅ Complete | 268 |
| 26 | Croatia & Slovenia (`croatia_slovenia.py`) | ✅ Complete | 391 |
| 27 | England (`england.py`) | ✅ Complete | 225 |
| 28 | Lebanon & Israel (`lebanon_israel.py`) | ✅ Complete | 182 |
| 29 | South Africa (`south_africa_enrichment.py`) | ✅ Complete | 339 |
| 30 | USA Enrichment (`usa_enrichment.py`) | ✅ Complete | 632 |
| 7-14 | Remaining scrapers | Not started | See `SCRAPER_PROMPTS.md` |

**Remaining scrapers:** 5-14 (see `SCRAPER_PROMPTS.md`)

## Documentation Maintenance — MANDATORY

After every PR or significant change, update all relevant documentation before committing. This is not optional — accurate docs are critical for this multi-session project where each Claude Code session relies on CLAUDE.md and other docs to understand the current state.

### What to update and when

**After implementing a new scraper:**
1. `CLAUDE.md` — Move the scraper from "Files Not Yet Created" table to the repo structure tree (mark with ✅ Done). Update the "Current Status" scraper table. Update fact counts if known.
2. `CURRENT_STATUS.md` — Update the scraper status table (status, actual fact count). Add a "Completed Scraper Details" entry describing what the scraper does. Update "Total raw facts collected" count. Update "Domain Coverage Assessment" if coverage changed.
3. `SCRAPER_PROMPTS.md` — Mark the scraper as done in the "Execution Order Summary" table. Update the shared context block if the new scraper serves as a good reference for future scrapers.

**After changing utility code (`src/utils/`):**
1. `CLAUDE.md` — Update the "Database Utilities" section with any new/changed function signatures, parameters, or return values. Update the "Fact dict format" example if the schema changed.
2. `SCRAPER_PROMPTS.md` — Update the shared context block that all future scraper prompts reference.

**After changing infrastructure (`docker-compose.yml`, `config/`, `scripts/`):**
1. `CLAUDE.md` — Update the "Infrastructure" section and "Repository Structure" tree.
2. `README.md` — Update the "Tech Stack" and "Getting Started" sections if setup steps changed.

**After changing the database schema (`config/postgres/init.sql`):**
1. `CLAUDE.md` — Update the "PostgreSQL Schema" table.
2. `PROJECT_PLAN.md` — Update if schema changes affect the methodology or data model sections.

**After reaching a project milestone (e.g., completing all scrapers, starting question generation):**
1. `CURRENT_STATUS.md` — Update the phase status table, mark phases complete, update next steps.
2. `CLAUDE.md` — Update "Current Status" and "What to Work On Next".
3. `README.md` — Update the "Current Status" paragraph.

### Rules

- Always update `CURRENT_STATUS.md` "Last updated" date when making changes to it.
- Never leave stale fact counts — if you know the count, update it; if you don't, use "—" (not a guess).
- Keep the "Repository Structure" tree in `CLAUDE.md` in sync with the actual filesystem. If you add a file, add it to the tree.
- The `SCRAPER_PROMPTS.md` shared context block is pasted into every new scraper session — it must always reflect the current state of utilities and completed scrapers.

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

1. **Implement remaining scrapers** (5-14) using prompts in `SCRAPER_PROMPTS.md`
2. **Run verify.py** after each batch of scrapers to check coverage gaps
3. **Transition to question generation** once fact collection reaches targets
4. See `CURRENT_STATUS.md` for detailed phase tracking

## Important Links

- **Full project plan:** `PROJECT_PLAN.md`
- **Data sources:** `DATA_SOURCES.md`
- **Scraper implementation specs:** `SCRAPER_PROMPTS.md`
- **Progress tracking:** `CURRENT_STATUS.md`
- **NeurIPS 2026 D&B Track:** Target submission venue
