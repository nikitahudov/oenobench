# OenoBench — Current Status & Progress

**Last updated:** April 6, 2026
**Project phase:** Phase 1 — Data Collection
**Target venue:** NeurIPS 2026 Datasets & Benchmarks Track (~May 15, 2026 deadline)

---

## Timeline Overview (30 weeks)

| Phase | Weeks | Status |
|-------|-------|--------|
| 1. Infrastructure & Data Collection | 1-6 | In progress |
| 2. Question Generation | 7-12 | Not started |
| 3. AI Validation | 13-16 | Not started |
| 4. Human Review & Control Set | 17-20 | Not started |
| 5. Evaluation & Analysis | 21-24 | Not started |
| 6. Publication & Release | 25-30 | Not started |

---

## Phase 1: Data Collection Progress

### Infrastructure (Complete)

- PostgreSQL 16 (pgvector), Elasticsearch 8.x, Neo4j 5.x, Redis 7.x all configured in `docker-compose.yml`
- Git repository structure established
- `src/utils/db.py` — connection helpers (`get_pg`, `get_es`, `get_neo4j`, `get_redis`)
- `src/utils/facts.py` — fact storage (`ensure_source`, `insert_facts_batch`, `insert_fact`, `get_fact_count`)
- `config/postgres/init.sql` — full schema with enums, indexes, views, triggers
- `scripts/setup.sh` — automated first-time setup
- `scripts/health.sh` — service health checks
- `scripts/backup.sh` — PostgreSQL & Neo4j backup
- `.env.example` — environment template
- Universal `--test-run` and `--validate` flags across scrapers

### Scraper Status

| # | Scraper | File | Target | Actual | Status |
|---|---------|------|--------|--------|--------|
| 1 | Wikidata | `src/scrapers/wikidata.py` | 3,000-5,000 | **20,910** | Complete |
| 2 | Wikipedia | `src/scrapers/wikipedia.py` | 3,000-4,000 | — | Complete |
| 3 | HuggingFace | `src/scrapers/huggingface.py` | 1,500-2,500 | **16,514** | Complete |
| 4 | UC Davis | `src/scrapers/ucdavis.py` | 1,000-2,000 | — | Complete |
| 5 | Kaggle | `src/scrapers/kaggle_data.py` | 500-1,000 | **1,509** | Complete |
| 6 | INAO (France) | `src/scrapers/inao.py` | 2,000-3,000 | **1,473** | Complete |
| 7 | Italy | `src/scrapers/italy.py` | 1,500-2,000 | — | Not started (prompt ready) |
| 8 | TTB (US) | `src/scrapers/ttb.py` | 500-800 | — | Not started (prompt ready) |
| 9 | Europe (ES/DE/PT) | `src/scrapers/europe.py` | 1,500-2,400 | — | Not started (prompt ready) |
| 10 | New World | `src/scrapers/newworld.py` | 800-1,200 | — | Not started (prompt ready) |
| 11 | EU/OIV | `src/scrapers/eu_oiv.py` | 500-800 | — | Not started (prompt ready) |
| 12 | Regional France | `src/scrapers/regional_france.py` | 800-1,500 | — | Not started (prompt ready) |
| 13 | Italian Consortiums | `src/scrapers/consortiums_italy.py` | 400-600 | — | Not started (prompt ready) |
| 14 | Academic | `src/scrapers/academic.py` | 500-800 | — | Not started (prompt ready) |
| 15 | Italian Wine Central | `src/scrapers/italian_wine_central.py` | 1,500-2,000 | **1,556** | Complete |
| 16 | Austrian Wine | `src/scrapers/austria.py` | 800-1,200 | **731** | Complete |
| 17 | Greek Wine | `src/scrapers/greece.py` | 600-900 | **587** | Complete |
| 18 | Rhône/Loire/Alsace | `src/scrapers/rhone_loire_alsace.py` | 800-1,200 | **763** | Complete |
| — | Verify | `src/scrapers/verify.py` | — | — | Not started (prompt ready) |

**Total raw facts collected:** ~41,000+
**Target after dedup:** 15,000-20,000 unique facts

### Completed Scraper Details

**Scraper 1 — Wikidata (`wikidata.py`):**
- Uses SPARQL queries against Wikidata endpoint
- Extracts wine regions, grape varieties, appellations, producers, classifications
- 20,910 facts — significantly exceeded 3,000-5,000 target
- CC0 licensed data (public domain)

**Scraper 2 — Wikipedia (`wikipedia.py`):**
- Uses MediaWiki API for category-based article crawling
- Extracts from infoboxes and lead paragraphs
- Covers regions, grapes, wineries, appellations, viticulture, oenology categories
- Rephrases all text into atomic facts (never stores verbatim Wikipedia text)
- CC BY-SA 3.0 licensed

**Scraper 3 — HuggingFace (`huggingface.py`):**
- Processes spawn99/wine-reviews (281K rows) and christopher/winesensed datasets
- Extracts variety-region associations, producer-region links, price tiers
- 16,514 facts from structured dataset analysis

**Scraper 4 — UC Davis (`ucdavis.py`):**
- Three data sources: Wine Ontology (RDF), AVA Digitizing Project (GeoJSON), FPS Grape Database (HTML)
- Parses RDF with rdflib, GeoJSON natively, HTML with BeautifulSoup
- Covers wine classifications, 267+ US AVAs, 595 grape varieties with clones
- Full implementation with --all, --source, --dry-run, --validate, --test-run, --list flags

**Scraper 5 — Kaggle (`kaggle_data.py`):**
- Two datasets: Wine Quality (UCI physicochemical stats) and Wine Reviews (zynicide/wine-reviews variety-region-producer associations)
- CSVs pre-downloaded to `data/raw/kaggle/`
- 1,509 facts total (1,434 from wine-reviews, 75 from wine-quality)
- Exceeded 500-1,000 target

**Scraper 6 — INAO (`inao.py`):**
- Extracts French wine appellation data from INAO via data.gouv.fr open-data CSVs
- Covers 1,210 unique appellations (AOC/AOP/IGP) across 13 French wine regions
- Generates facts about appellation status, permitted grape varieties, minimum alcohol, maximum yields, wine types
- 1,473 facts — below 2,000-3,000 target (CSV-only extraction; INAO website detail pages not scraped)
- 100% entity population, 0% quality issues
- Licence Ouverte (French open licence)

**Scraper 15 — Italian Wine Central (`italian_wine_central.py`):**
- Extracts structured data from Italian Wine Central reference database (italianwinecentral.com)
- Focus: climate, soil, elevation, grape variety profiles, MeGA/UGA subzones, and production statistics
- Covers 20 Italian wine regions, 70 DOCG supplements, 58 grape varieties, 8 MeGA/UGA DOCGs
- Complements italy.py (which covers basic classification/aging/grape rules) with terroir and climate data
- 1,556 facts — 350 grape_varieties, 878 wine_regions, 201 viticulture, 112 winemaking, 40 wine_business
- Covers 20 regions, 70 DOCG supplements, 111 DOC appellations, 58 grape varieties, 8 MeGA/UGA DOCGs
- 0% quality issues, 0% overlaps with italy.py, 100% entity population

**Scraper 16 — Austrian Wine (`austria.py`):**
- Comprehensive Austrian wine data from Austrian Wine Marketing Board (austrianwine.com)
- 19 wine regions with climate, soil, elevation; 26 grape varieties; DAC system; Prädikat levels; Wachau classifications
- 731 facts — 209 wine_regions, 190 grape_varieties, 30 wine_business, 22 winemaking, 19 viticulture
- 0% quality issues, 0% near-duplicates

**Scraper 17 — Greek Wine (`greece.py`):**
- Greek wine data from Wines of Greece (winesofgreece.org) and EL.G.O. DIMITRA
- 10 wine regions, 32 PDO appellations, 22 grape varieties; unique winemaking traditions (kouloura, Retsina, Vinsanto)
- 587 facts — 254 wine_regions, 132 grape_varieties, 101 winemaking, 42 viticulture, 18 wine_business

**Scraper 18 — Rhône/Loire/Alsace (`rhone_loire_alsace.py`):**
- French regional enrichment from Inter Rhône, InterLoire, CIVA
- 18 Rhône appellations (Côte-Rôtie, Hermitage, Châteauneuf-du-Pape, etc.)
- 20 Loire appellations (Sancerre, Vouvray, Muscadet, Chinon, etc.)
- 51 Alsace Grand Cru vineyards with soil types and key grapes
- 763 facts — 520 wine_regions, 193 grape_varieties, 35 viticulture

### Key Learnings So Far

1. **Quality over quantity** — Atomic fact extraction works better than accepting verbose or compound statements
2. **Validation before full runs** — Always inspect data quality before committing to full scraper runs
3. **Claude Code workflow** — Using Claude Code prompts for scraper implementation has been effective
4. **Wikidata overperformed** — 20,910 facts vs 3,000-5,000 target, excellent structured data source
5. **HuggingFace contributed well** — 16,514 facts from wine review datasets
6. **UC Davis provides authoritative data** — Ontology + AVA + FPS covers varieties and US regions comprehensively

---

## Domain Coverage Assessment (Estimated)

Based on completed scrapers (1-4), coverage is weighted toward regions and varieties. Upcoming scrapers should balance this:

| Domain | Current Coverage | Scrapers That Will Help |
|--------|-----------------|-------------------------|
| Wine Regions | Good | Scrapers 6-10, 12 |
| Grape Varieties | Good | Scrapers 5, 6-10 |
| Producers | Moderate | Scrapers 12, 13 |
| Viticulture | Low | Scrapers 14 (academic) |
| Winemaking | Low | Scrapers 11, 14 (academic) |
| Wine Business | Low | Scrapers 8, 11 |

---

## Next Steps

1. Implement scrapers 7-14 using prompts in `SCRAPER_PROMPTS.md`
2. Implement `verify.py` gap analysis tool
3. Run verify.py after completing scraper batches
4. Begin question generation pipeline design (Phase 2)
5. Set up multi-model LLM API access for question generation
6. Design evaluation framework and scoring pipeline
