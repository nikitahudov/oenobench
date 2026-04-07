# OenoBench — Current Status & Progress

**Last updated:** April 7, 2026
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

**IMPORTANT: Data Provenance Audit (April 2026)**
An audit revealed that 19 scrapers contained hardcoded LLM-generated facts disguised as scraped data. These are being rebuilt to use genuine HTTP-fetched data only. See "Provenance Rebuild Status" below.

#### Genuine Scrapers (verified data provenance)

| # | Scraper | File | Actual | Source Method |
|---|---------|------|--------|---------------|
| 1 | Wikidata | `wikidata.py` | **2,145** | SPARQL queries |
| 2 | Wikipedia | `wikipedia.py` | **323** | MediaWiki API |
| 3 | HuggingFace | `huggingface.py` | **3,231** | HuggingFace datasets |
| 4 | UC Davis | `ucdavis.py` | **2,199** | RDF + GeoJSON + HTML |
| 5 | Kaggle | `kaggle_data.py` | **1,509** | CSV datasets |
| 6 | INAO (France) | `inao.py` | **1,473** | data.gouv.fr CSV |
| 7 | Italy | `italy.py` | **606** | Federdoc + Italian Wine Central |
| 8 | TTB (US) | `ttb.py` | **515** | TTB.gov + eCFR |
| 9 | Europe (ES/DE/PT) | `europe.py` | **1,605** | MAPA, DWI, IVV, IVDP |
| 10 | New World | `newworld.py` | **903** | Wine Australia, NZ Wine, WOSA |
| 11 | EU/OIV | `eu_oiv.py` | **130** | EUR-Lex + OIV |
| 13 | Italian Consortiums | `consortiums_italy.py` | **453** | 9 consortium websites |
| 14 | Academic | `academic.py` | **925** | OENO One, Vitis, AJEV |
| — | Extension Services | `extension.py` | **705** | USDA, Penn State, Oregon State |
| — | UC IPM Grape | `ucipm.py` | **1,145** | UC IPM pages |
| — | OIV Docs | `oiv_docs.py` | **63** | OIV PDF downloads |

#### Rebuilt Hybrid Scrapers (provenance fixed, re-run with genuine data)

| Scraper | File | Old (Fake) | New (Genuine) | Status |
|---------|------|------------|---------------|--------|
| Bordeaux | `bordeaux.py` | 469 | **155** | ✅ Rebuilt & run |
| Champagne | `champagne.py` | 211 | **356** | ✅ Rebuilt & run |
| Burgundy | `burgundy.py` | 982 | **64** | ✅ Rebuilt & run |
| Italian Wine Central | `italian_wine_central.py` | 1,556 | **729** | ✅ Rebuilt & run |
| Austrian Wine | `austria.py` | 731 | **317** | ✅ Rebuilt & run |
| Greek Wine | `greece.py` | 587 | **236** | ✅ Rebuilt & run |

#### Hardcoded Scrapers (need rebuild — all facts are LLM-generated, zero HTTP calls)

| Scraper | File | Fake Facts | Status |
|---------|------|-----------|--------|
| Rhône/Loire/Alsace | `rhone_loire_alsace.py` | 763 | ⚠️ Needs rebuild |
| Spain Enrichment | `spain_enrichment.py` | 493 | ⚠️ Needs rebuild |
| Portugal Enrichment | `portugal_enrichment.py` | 438 | ⚠️ Needs rebuild |
| South America | `south_america.py` | 393 | ⚠️ Needs rebuild |
| Australia/NZ | `australia_nz_enrichment.py` | 691 | ⚠️ Needs rebuild |
| Hungary & Georgia | `hungary_georgia.py` | 429 | ⚠️ Needs rebuild |
| Germany Enrichment | `germany_enrichment.py` | 333 | ⚠️ Needs rebuild |
| Canada | `canada.py` | 268 | ⚠️ Needs rebuild |
| Croatia & Slovenia | `croatia_slovenia.py` | 391 | ⚠️ Needs rebuild |
| England | `england.py` | 225 | ⚠️ Needs rebuild |
| Lebanon & Israel | `lebanon_israel.py` | 182 | ⚠️ Needs rebuild |
| South Africa | `south_africa_enrichment.py` | 339 | ⚠️ Needs rebuild |
| USA Enrichment | `usa_enrichment.py` | 632 | ⚠️ Needs rebuild |

**DB total (verified genuine facts only): 24,563**
**Hardcoded facts still in DB (to be purged): ~5,577**
**Target after full cleanup + rebuild: 20,000+ genuine facts**

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

**Italian Wine Central (`italian_wine_central.py`) — REBUILT:**
- Rebuilt April 2026 with genuine Wikipedia/Wikidata scraping (old version was 74% hardcoded)
- Wikipedia: 696 facts from Italian wine category pages; Wikidata: 59 SPARQL results
- 729 genuine facts (down from 1,556 fake)

**Austrian Wine (`austria.py`) — REBUILT:**
- Rebuilt April 2026 with genuine Wikipedia/Wikidata scraping
- Wikipedia categories: 142 facts; Wikidata SPARQL: 149 facts; austrianwine.com: 404'd
- 317 genuine facts (down from 731 fake)

**Greek Wine (`greece.py`) — REBUILT:**
- Rebuilt April 2026 with genuine Wikipedia/Wikidata scraping
- Wikipedia categories: 212 facts; Wikidata: 21 facts; EU GIView API: unavailable
- 236 genuine facts (down from 587 fake)

**Bordeaux (`bordeaux.py`) — REBUILT:**
- Rebuilt April 2026 — Wikipedia + Wikidata, replaces mostly-hardcoded Classification 1855
- 155 genuine facts (down from 469 fake)

**Champagne (`champagne.py`) — REBUILT:**
- Rebuilt April 2026 — Wikipedia + Wikidata
- 356 genuine facts (up from 211 fake)

**Burgundy (`burgundy.py`) — REBUILT:**
- Rebuilt April 2026 — Wikipedia + Wikidata; BIVB website returned 404 for all endpoints
- 64 genuine facts (down from 982 fake)

**Scrapers 18-30 (hardcoded, awaiting rebuild):**
- All 13 scrapers contain 100% LLM-generated facts with zero HTTP calls
- Facts attributed to fake source URLs that were never fetched
- Total ~5,577 fake facts still in DB — need purge + rebuild

### Key Learnings So Far

1. **Data provenance is paramount** — 19 scrapers were found to contain hardcoded LLM-generated facts disguised as scraped data. This was a critical integrity failure for a NeurIPS submission.
2. **Genuine scraping yields fewer but trustworthy facts** — Rebuilt scrapers average ~60% fewer facts than hardcoded versions, but every fact traces to a real URL.
3. **Wikipedia/Wikidata are the backbone** — The `_wiki_helpers.py` shared module enables rapid scraper rebuilds using MediaWiki API and SPARQL.
4. **Official wine body websites often block bots** — BIVB, austrianwine.com, GIView API all returned 404/errors. Wikipedia is the reliable fallback.
5. **Quality over quantity** — Atomic fact extraction works better than accepting verbose or compound statements.

---

## Next Steps

1. **Phase 2 of provenance rebuild:** Purge ~5,577 hardcoded facts from 13 fully-fake scrapers, then rebuild each using genuine Wikipedia/Wikidata/website scraping
2. After rebuild, verify DB integrity — all facts must trace to genuinely fetched URLs
3. Implement `verify.py` gap analysis tool
4. Begin question generation pipeline design (Phase 2)
5. Set up multi-model LLM API access for question generation
6. Design evaluation framework and scoring pipeline
