# OenoBench — Current Status & Progress

**Last updated:** April 23, 2026
**Project phase:** Phase 2g — v2.3 §5b+§5c shipped (B2 generation-side leakage fix + judge recalibration). Ready for audit run #4.
**Target venue:** NeurIPS 2026 Datasets & Benchmarks Track (~May 15, 2026 deadline)

## Latest cliff notes (start here next session)

- **Phase 2g (2026-04-23) — two remaining v2.3 defects shipped via 3 parallel worktree teams:**
  - **Team α (generation-side B2):** `data/iconic_entities.yaml` expanded 60 → 188 entries; `_fact_sampler.py` widened iconic filter to multi-fact strategies via `_bundle_has_non_iconic_anchor`; 11 new vague-regex patterns; `AVOID WORLD-KNOWLEDGE SOLVABILITY` + numbered `HARD RULES` blocks across all 10 strategy prompts.
  - **Team β (judge recalibration):** `B2_VERSION v3.1.0` — L≤2 FAIL iff 5/5 keyed AND `cb_confidence_mean ≥ 0.80`; L≥3 WARN-only (never FAIL on closed-book alone). New `cb_confidence_mean` payload field.
  - **Team γ (rubric reframing):** A3 rubric_measured=`verbatim_copy` (v1.1.0); C2 rubric_measured=`wine_category_leak` (v1.1.0); audit-report rubric remap with `_HUMAN_ONLY_AGENT` sentinel for semantic `source_faithful`; `GOLD_RUBRICS` extended with the two new entries.
  - **Coordinator fixup:** wired `strategy="fact_to_question"` / `"template"` / `"distractor_mining"` at four `sample_facts()` call sites (single-fact iconic filter was dormant since v2.2).
- **Test status:** 269/269 pytest pass on merged main.
- **Audit run #3 (prior)**: `audit_pilot_v3`, 331 Qs, $8.51. v2.2 fixes landed. κ on 119 combined rows: only B1 `answer_correct` has usable signal (κ=0.47). B2 `needs_source` κ=-0.10 is now addressed by the v3.1.0 threshold change.
- **Phase D sign-off: Go/No-Go STILL BLOCKED** on 5 gates pending audit run #4 re-measurement: per-generator answer_correct; template 7-rubric clean-pass; difficulty_match; D3 country ratio; B1.
- **Next session start point:** Run audit_pilot_v4. `python -m src.qa.orchestrator build-corpus --tag audit_pilot_v4 --per-strategy 120 && run --teams A,B,C,D`. Expected: B2 fail rate drops from 66% to ~10–15%; new `verbatim_copy` + `wine_category_leak` rubric columns populate. Then export gold-v4 for human re-grading.

---

## Timeline Overview (30 weeks)

| Phase | Weeks | Status |
|-------|-------|--------|
| 1. Infrastructure & Data Collection | 1-6 | **Complete** — 38,104 facts from 35 genuine scrapers |
| 2. Question Generation Pipeline | 7-10 | **Complete** — all 5 strategies built and iteratively tuned |
| 2c. Quality Audit Framework | 11 | **Complete** — 9-agent multi-team audit |
| 2d. Audit run #1 (pilot 472 Qs) | 12 | **Complete** — Go/No-Go BLOCKED, see findings below |
| 2e. Defect fixes + audit run #2 | 13 | **Pending** — implement 3 critical fixes, re-run audit |
| 2f. Full 10k generation run | 14 | **Pending** — gated on Go/No-Go pass |
| 3. AI Validation | 15-17 | Not started |
| 4. Human Review & Control Set | 18-20 | Not started |
| 5. Evaluation & Analysis | 21-24 | Not started |
| 6. Publication & Release | 25-30 | Not started |

---

## Phase 2d: Audit Run #1 — Headline Findings (April 19, 2026)

**Run ID:** `e8eba8bb-cb49-42cd-9e32-c741c987043e`
**Corpus:** 472 questions tagged `audit_pilot_v1` (template=49, fact_to_q=120, comparative=85, scenario=119, distractor=99)
**Cost:** $8.49 / 3,207 LLM calls (well under $130–175 estimate; judge prompts shorter than expected)
**Wall time:** corpus build 2h50m + audit 3h25m
**Reports:** `docs/QUALITY_AUDIT_REPORT.md`, `docs/GENERATION_IMPROVEMENT_PLAN.md`

### Defect leaderboard (impact = 3·fails + warns + 2·errors)

| Rank | Defect | Agent | Severity | Impact |
|---:|---|---|---|---:|
| 1 | **Verbatim source copying** in question + correct option | A3 FactEcho | 35% fail, 38% warn | **673** |
| 2 | **Question solvable from world knowledge** (no source needed) | B2 ClosedBookSolvability | 30% fail, 32% warn | **570** |
| 3 | **Key disagrees with judge consensus** (likely wrong answers) | B1 TriJudgeAnswer | 5% fail, 12% warn | **123** |
| 4 | **Templates statistically distinguishable** (held-out AUC 0.96) | A4 TemplateFingerprint | 64% fail/warn | **75** |
| 5 | Vague / marketing / blend-as-variety phrasing | A1 LexicalHygiene | 3% fail, 3% warn | **52** |
| 6 | Wine-category distractor leak (red question, white distractor) | C2 CategoryLeak | 1% fail, 2% warn | **24** |
| 7 | Country over-representation **4.46×** (Chile, Israel, US, Austria) | D3 SkewAudit | FAIL | **3** |
| 8 | Position / length bias in MC options | A2 BiasStats | FAIL on at least one cell | **3** |
| 9 | ChatGPT shows ~12pp self-preference advantage | D1 SelfPreference | warn | **1** |

### Regeneration Go/No-Go: **BLOCKED**

Three defects far exceed the gate thresholds:
- A3 fail rate **35%** vs ≤2% threshold (×17 over)
- B2 leakage rate at Level 3/4 well above 50% threshold
- D3 country over-representation **4.46×** vs ≤1.5× threshold (×3 over)

### Critical fixes required before audit run #2

1. **A3 — paraphrase enforcement.** Add explicit "paraphrase, never copy >5 consecutive words verbatim" instruction to `src/generators/_prompts.py` for all LLM strategies. Add post-LLM rejector in `src/generators/_schemas.py` that fails any question with LCS ratio >0.6 against any linked source fact. Cost: S, blocks ranks 1.
2. **B2 — anti-leakage prompting.** Modify `_prompts.py` to push LLMs toward fact-specific terminology and away from famous-entity references that test-takers can solve from world knowledge alone. Re-target leaky question difficulty up. Cost: M, blocks rank 2.
3. **D3 — per-country quota.** Add per-country sampling cap to `src/generators/_fact_sampler.sample_facts` (or weight inverse to country frequency). Cost: M, blocks rank 7.

Lower-impact fixes (A1 vague-regex extension, A4 template phrasing diversification, C2 wine-category sampling pre-filter) can land in the same iteration.

### Pending human review (in flight)

- **Gold sheet** at `data/reports/gold_sheet.csv` — 60 questions × 8 rubrics for reviewer to grade. Once imported via `import-gold`, audit run #2 will compute LLM-judge ↔ human Cohen's κ per rubric and downweight any signal where κ<0.6.

### Next steps (in order)

1. Implement the 3 critical fixes + lower-impact fixes (1-2 days).
2. Re-run `build-corpus --per-strategy 120 --tag audit_pilot_v2` (~2-3h, ~$3).
3. Re-run `run --teams A,B,C,D` (~3-4h, ~$10).
4. `build-reports` and verify the Go/No-Go checklist now passes.
5. **Only then** start the full 10k generation run.

---

## Phase 2c: Quality Audit Framework (Complete — April 18, 2026)

After iterative generation-quality tuning through April 12–18 (blend-as-variety filter, thin-geo rejection, inference-over-recall prompting, dimension-aware pairing, option shuffling, Gemini/Qwen token fix), we built a dedicated multi-agent audit framework that gates the full 10k generation run.

### Architecture — 4 teams, 9 agents

- **Team A** (no LLM, static analysis): A1 LexicalHygiene, A2 BiasStats (position/length), A3 FactEcho (LCS vs source), A4 TemplateFingerprint (POS-bigram logreg).
- **Team B** (tri-judge panel — Claude Opus 4.7, ChatGPT 5.4, Gemini 3.1 Pro): B1 TriJudgeAnswer, B2 ClosedBookSolvability.
- **Team C** (deterministic, MVA slice): C2 CategoryLeak; C1/C3/C4 deferred with escalation triggers.
- **Team D**: D1 SelfPreference (5×5 evaluator×author), D3 SkewAudit (stats-only, cultural slice deferred).

### Infrastructure
- **New module**: `src/qa/` with orchestrator CLI, shared foundation, 4 team agent files, 2 report renderers.
- **New DB objects**: `audit_runs`, `audit_findings`, `audit_gold_labels` tables, `v_question_audit_summary`, `v_strategy_audit_rollup` views, `audit_severity` enum (applied via `config/postgres/002_audit_schema.sql`).
- **Reproducibility**: `config_hash = sha256(agents+versions | models | seed | thresholds)` stored on every run; findings idempotent on `(run_id, q_id, agent_id, version)`. Team B writes findings inline so audits are resumable.
- **Test suite**: 26 pytest tests green across `_scoring`, `_findings`, Team A (4 agents), Team C.

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
- `src/scrapers/_fact_processing.py` — shared fact processing pipeline (decompose, resolve refs, classify domain, validate)
- `src/scrapers/_web_helpers.py` — shared web scraping utilities (session, page discovery, text extraction, sitemap)
- `src/scrapers/_wiki_helpers.py` — updated with `extract_atomic_facts`, `run_sparql_filtered`, country-scoped SPARQL templates

### Data Provenance Audit & Rebuild (Complete — April 2026)

An audit (April 7, 2026) revealed that 19 scrapers contained hardcoded LLM-generated facts disguised as scraped data. A full rebuild was completed on April 11, 2026:

- **Phase 0:** Built shared infrastructure (`_fact_processing.py`, `_web_helpers.py`, updated `_wiki_helpers.py`). Purged 7,861 hardcoded facts from DB (24,563 → 16,702).
- **Phase 1:** Fixed 8 scrapers with quality issues (off-topic SPARQL, non-atomic facts, domain bias).
- **Phase 2:** Rebuilt all 17 hardcoded scrapers with genuine Wikipedia + Wikidata + official website data. Removed ~26,000+ lines of hardcoded data.

**All scrapers now use genuine HTTP-fetched data only.** Every fact traces to a verifiable URL.

### Scraper Status — All Genuine

#### Original Genuine Scrapers

| # | Scraper | File | Facts | Source Method |
|---|---------|------|-------|---------------|
| 1 | Wikidata | `wikidata.py` | **2,145** | SPARQL queries |
| 2 | Wikipedia | `wikipedia.py` | **323** | MediaWiki API |
| 3 | HuggingFace | `huggingface.py` | **3,231** | HuggingFace datasets |
| 4 | UC Davis | `ucdavis.py` | **2,199** | RDF + GeoJSON + HTML |
| 5 | Kaggle | `kaggle_data.py` | **1,509** | CSV datasets |
| 6 | INAO (France) | `inao.py` | **1,473** | data.gouv.fr CSV |
| 14 | Academic | `academic.py` | **925** | OENO One, Vitis, AJEV |
| — | Extension Services | `extension.py` | **705** | USDA, Penn State, Oregon State |
| — | UC IPM Grape | `ucipm.py` | **1,145** | UC IPM pages |
| — | OIV Docs | `oiv_docs.py` | **63** | OIV PDF downloads |

#### Fixed Scrapers (Phase 1 rebuild — April 11, 2026)

| Scraper | File | Before | After | Key Fix |
|---------|------|--------|-------|---------|
| Bordeaux | `bordeaux.py` | 155 | **484** | P17 SPARQL + bordeaux.com |
| Burgundy | `burgundy.py` | 64 | **483** | P17 SPARQL + bourgogne-wines.com |
| Champagne | `champagne.py` | 356 | **466** | P17 SPARQL + champagne.fr (partial) |
| Italian Wine Central | `italian_wine_central.py` | 729 | **788** | extract_atomic_facts + classify_domain |
| Austrian Wine | `austria.py` | 317 | **146** | Removed off-topic German facts |
| Greek Wine | `greece.py` | 236 | **255** | Removed off-topic Italian Grechetto |
| Italian Consortiums | `consortiums_italy.py` | 453 | **85** | Atomic fact pipeline applied |
| TTB (US) | `ttb.py` | 515 | **513** | Verified CFR text genuine |

#### Rebuilt Scrapers (Phase 2 rebuild — April 11, 2026)

All formerly hardcoded scrapers rebuilt with genuine Wikipedia + Wikidata + official website data:

| Scraper | File | Status | Source Method |
|---------|------|--------|--------------|
| Italy | `italy.py` | ✅ Rebuilt | Wikipedia + SPARQL (removed DOCG_DATABASE) |
| Europe (ES/DE/PT) | `europe.py` | ✅ Rebuilt | Wikipedia + SPARQL (removed hardcoded dicts) |
| New World | `newworld.py` | ✅ Rebuilt | Wikipedia + SPARQL (removed 5 *_KNOWLEDGE dicts) |
| EU/OIV | `eu_oiv.py` | ✅ Rebuilt | Wikipedia + SPARQL |
| Rhone/Loire/Alsace | `rhone_loire_alsace.py` | ✅ Rebuilt | Wikipedia + SPARQL |
| Spain Enrichment | `spain_enrichment.py` | ✅ Rebuilt | Wikipedia + SPARQL |
| Portugal Enrichment | `portugal_enrichment.py` | ✅ Rebuilt | Wikipedia + SPARQL |
| Germany Enrichment | `germany_enrichment.py` | ✅ Rebuilt | Wikipedia + SPARQL |
| USA Enrichment | `usa_enrichment.py` | ✅ Rebuilt | 22 Wikipedia articles + SPARQL |
| South America | `south_america.py` | ✅ Rebuilt | Wikipedia + SPARQL |
| Australia/NZ | `australia_nz_enrichment.py` | ✅ Rebuilt | Wikipedia + SPARQL |
| Hungary & Georgia | `hungary_georgia.py` | ✅ Rebuilt | Wikipedia + SPARQL |
| Croatia & Slovenia | `croatia_slovenia.py` | ✅ Rebuilt | Wikipedia + SPARQL |
| Canada | `canada.py` | ✅ Rebuilt | Wikipedia + SPARQL |
| England | `england.py` | ✅ Rebuilt | Wikipedia + SPARQL |
| Lebanon & Israel | `lebanon_israel.py` | ✅ Rebuilt | Wikipedia + SPARQL |
| South Africa | `south_africa_enrichment.py` | ✅ Rebuilt | Wikipedia + SPARQL |

**Note:** Fact counts for rebuilt Phase 2 scrapers pending — scrapers are being re-run to populate DB.

### Completed Scraper Details

**Scraper 1 — Wikidata (`wikidata.py`):**
- Uses SPARQL queries against Wikidata endpoint
- Extracts wine regions, grape varieties, appellations, producers, classifications
- 2,145 genuine facts (after dedup)
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
- 3,231 facts from structured dataset analysis

**Scraper 4 — UC Davis (`ucdavis.py`):**
- Three data sources: Wine Ontology (RDF), AVA Digitizing Project (GeoJSON), FPS Grape Database (HTML)
- Parses RDF with rdflib, GeoJSON natively, HTML with BeautifulSoup
- Covers wine classifications, 267+ US AVAs, 595 grape varieties with clones
- Full implementation with --all, --source, --dry-run, --validate, --test-run, --list flags

**Scraper 5 — Kaggle (`kaggle_data.py`):**
- Two datasets: Wine Quality (UCI physicochemical stats) and Wine Reviews (zynicide/wine-reviews variety-region-producer associations)
- CSVs pre-downloaded to `data/raw/kaggle/`
- 1,509 facts total (1,434 from wine-reviews, 75 from wine-quality)

**Scraper 6 — INAO (`inao.py`):**
- Extracts French wine appellation data from INAO via data.gouv.fr open-data CSVs
- Covers 1,210 unique appellations (AOC/AOP/IGP) across 13 French wine regions
- 1,473 facts
- Licence Ouverte (French open licence)

### Unreachable Official Sites (documented)

| Site | Error | Fallback |
|------|-------|----------|
| inter-rhone.com | Connection timeout | Wikipedia/Wikidata |
| brunellodimontalcino.it | No route to host | Wikipedia/Wikidata |
| franciacorta.wine | Not tested | Wikipedia/Wikidata |
| consorziovinonobile.it | Not tested | Wikipedia/Wikidata |
| austrianwine.com | 404 | Wikipedia/Wikidata |
| BIVB (bourgogne-wines.com) | Partially accessible | Wikipedia/Wikidata + partial |

### Key Learnings

1. **Data provenance is paramount** — 19 scrapers were found to contain hardcoded LLM-generated facts disguised as scraped data. This was a critical integrity failure for a NeurIPS submission.
2. **Genuine scraping yields fewer but trustworthy facts** — Rebuilt scrapers average ~60% fewer facts than hardcoded versions, but every fact traces to a real URL.
3. **Wikipedia/Wikidata are the backbone** — The shared `_wiki_helpers.py` module enables rapid scraper rebuilds using MediaWiki API and SPARQL.
4. **P17 > P131* for SPARQL scoping** — Transitive P131* caused severe off-topic contamination (e.g., Austrian data in Bordeaux scraper). Direct P17 (country) prevents cross-country leakage.
5. **Official wine body websites often block bots** — BIVB, austrianwine.com, GIView API, inter-rhone.com all returned errors. Wikipedia is the reliable fallback.
6. **Shared infrastructure pays off** — `_fact_processing.py` and `_web_helpers.py` ensured consistency across all 25+ scraper rebuilds.

---

## Phase 2: Question Generation (In Progress)

### Pipeline Infrastructure (Complete)
Built 7 shared modules in `src/generators/`:
- `_llm_client.py` — Unified OpenRouter client for 5 LLMs
- `_prompts.py` — Prompt templates for all generation strategies
- `_schemas.py` — Pydantic output validation with 3-tier JSON extraction
- `_id_generator.py` — WB-{DOMAIN}-{SEQ}-L{DIFF} question ID minting
- `_question_db.py` — Atomic insertion with provenance (question_facts + question_sources)
- `_fact_sampler.py` — Stratified fact sampling with source diversity
- `_dedup.py` — Embedding-based semantic deduplication via pgvector

### Generation Models (via OpenRouter)
| Generator | Model | Status |
|-----------|-------|--------|
| Claude | `anthropic/claude-opus-4-6` | Ready |
| ChatGPT | `openai/chatgpt-5.4` | Ready |
| Gemini | `google/gemini-3.1` | Ready |
| Llama | `meta-llama/llama-3.1-405b-instruct` | Ready |
| Qwen | `qwen/qwen-3.5` | Ready |
| Template-only | N/A (deterministic) | Ready |

### Generation Strategies
| Strategy | File | % | Status |
|----------|------|---|--------|
| Fact-to-Question | `fact_to_question.py` | 40% (4,000) | **Built** |
| Template-Based | `template_generator.py` | 25% (2,500) | **Built** — 45 templates |
| Comparative | `comparative_generator.py` | 15% (1,500) | **Built** — entity affinity scoring, country-level filtering |
| Scenario Synthesis | `scenario_generator.py` | 10% (1,000) | **Verified** — inference-over-recall prompts, cohesion checks |
| Distractor Mining | `distractor_miner.py` | 10% (1,000) | **Built** — confusable entity matching, richness filtering |

### Target: 10,000 Questions
| Domain | Target | Available Facts |
|--------|--------|----------------|
| wine_regions | 3,500 (35%) | 18,943 |
| winemaking | 2,000 (20%) | 1,367 |
| viticulture | 1,500 (15%) | 3,635 |
| grape_varieties | 1,200 (12%) | 5,959 |
| wine_business | 1,000 (10%) | 1,985 |
| producers | 800 (8%) | 6,215 |

---

## Next Steps

1. **Set OPENROUTER_API_KEY** in `.env` and run `fact_to_question.py --test-run` with live LLM
2. **User reviews** 20-50 sample questions for quality, iterates prompts
3. **Build remaining 3 strategies** (comparative, scenario, distractor mining)
4. **Build orchestrator.py** for full pipeline with quota management
5. **Full generation run** — generate ~14,000 raw, dedup to 10,000
6. Transition to Phase 3: AI Validation
