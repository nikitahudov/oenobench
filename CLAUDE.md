# OenoBench — Claude Code Project Guide

## What Is This Project?

OenoBench (formerly WineBench) is a comprehensive AI benchmark for evaluating LLM knowledge across wine-related domains. It targets **5,000 questions** for the **NeurIPS 2026 Datasets & Benchmarks Track** (deadline ~May 15, 2026).

The key innovation is an AI-driven pipeline: automated data collection → multi-model question generation → AI validation → targeted human review.

## Repository Structure

```
~/oenobench/
├── CLAUDE.md                  # ← You are here. Read this first.
├── README.md                  # Public-facing project overview
├── requirements.txt           # Python dependencies
├── .env                       # Database credentials (not in git)
├── src/
│   ├── utils/
│   │   ├── db.py              # PostgreSQL, Elasticsearch, Neo4j, Redis connections
│   │   └── facts.py           # ensure_source(), insert_facts_batch(), get_fact_count()
│   └── scrapers/
│       ├── wikidata.py        # ✅ Done — 20,910 facts
│       ├── wikipedia.py       # ✅ Done — reference scraper
│       ├── huggingface.py     # ✅ Done — 16,514 facts
│       ├── ucdavis.py         # Scraper 4
│       ├── kaggle_data.py     # Scraper 5 (not kaggle.py — avoid naming conflict)
│       ├── inao.py            # Scraper 6 — French appellations
│       ├── italy.py           # Scraper 7 — Italian registries
│       ├── ttb.py             # Scraper 8 — US regulations
│       ├── europe.py          # Scraper 9 — Spain, Germany, Portugal
│       ├── newworld.py        # Scraper 10 — Australia, NZ, South Africa, South America
│       ├── eu_oiv.py          # Scraper 11 — EU regulations & OIV
│       ├── regional_france.py # Scraper 12 — Burgundy, Champagne, Bordeaux
│       ├── consortiums_italy.py # Scraper 13 — Italian consortiums
│       ├── academic.py        # Scraper 14 — Journal abstracts
│       └── verify.py          # Post-scraping gap analysis tool
├── data/
│   ├── raw/                   # Downloaded datasets (not in git)
│   ├── logs/                  # Scraper run logs
│   └── reports/               # Verification reports
└── docs/
    ├── PROJECT_PLAN.md        # Full project plan with methodology
    ├── DATA_SOURCES.md        # Data source inventory & scraping strategy
    ├── SCRAPER_PROMPTS.md     # Detailed prompts for each scraper
    └── CURRENT_STATUS.md      # Progress tracking
```

## Current Status (as of March 2026)

**Phase:** Data Collection (Phase 1)  
**Facts collected:** ~38,000+ raw facts  
**Completed scrapers:** Wikidata (20,910), HuggingFace (16,514), Wikipedia  
**Remaining scrapers:** 4-14 (see docs/SCRAPER_PROMPTS.md)

## Critical Patterns — READ BEFORE WRITING CODE

### Database Utilities

Always use the existing utilities in `src/utils/`:

```python
from src.utils.facts import ensure_source, insert_facts_batch, get_fact_count
from src.utils.db import get_pg_connection, get_es_client, get_neo4j_driver
```

- `ensure_source(name, url, tier)` — Register a data source before inserting facts
- `insert_facts_batch(facts)` — Bulk insert with dedup on exact `fact_text`
- `get_fact_count(source=None)` — Count facts, optionally filtered by source

### Scraper CLI Pattern

Every scraper MUST follow this CLI pattern:

```bash
python -m src.scrapers.<name> --all          # Run full extraction
python -m src.scrapers.<name> --dry-run      # Preview without DB writes
python -m src.scrapers.<name> --validate     # Quality checks on extracted data
python -m src.scrapers.<name> --list         # List available sub-sources
# Plus source-specific filters (--region, --country, --dataset, etc.)
```

### Fact Quality Rules

1. **Atomic facts only** — One fact per sentence: "Barolo DOCG requires 100% Nebbiolo."
2. **Never store verbatim source text** — Always rephrase into atomic facts
3. **Domain values:** `wine_regions`, `grape_varieties`, `producers`, `viticulture`, `winemaking`, `wine_business`
4. **Rate limiting:** All HTTP requests must be rate-limited (see per-scraper specs in docs/SCRAPER_PROMPTS.md)
5. **User-Agent:** `"OenoBench-Research/1.0 (academic wine benchmark)"`
6. **Logging:** Write to `data/logs/<scraper_name>_{timestamp}.log`

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

- **PostgreSQL** — Structured facts, sources, metadata
- **Elasticsearch** — Full-text search across facts
- **Neo4j** — Knowledge graph of wine entity relationships
- **Redis** — Caching layer
- All running in Docker containers on a dedicated server
- Database credentials in `.env` file (not committed to git)

## Quick Reference: Fact Targets by Domain

| Domain | Target Facts | Status |
|--------|-------------|--------|
| Wine Regions | 5,000 | In progress |
| Grape Varieties | 2,000 | In progress |
| Producers | 3,000 | In progress |
| Viticulture | 1,500 | Needs more coverage |
| Winemaking | 1,500 | Needs more coverage |
| Wine Business | 1,000 | Needs more coverage |

## What to Work On Next

1. **Implement remaining scrapers** (4-14) using prompts in `docs/SCRAPER_PROMPTS.md`
2. **Run verify.py** after each batch of scrapers to check coverage gaps
3. **Transition to question generation** once fact collection reaches targets
4. See `docs/CURRENT_STATUS.md` for detailed phase tracking

## Important Links

- **Full project plan:** `docs/PROJECT_PLAN.md`
- **Data sources:** `docs/DATA_SOURCES.md`
- **Scraper implementation specs:** `docs/SCRAPER_PROMPTS.md`
- **NeurIPS 2026 D&B Track:** Target submission venue
