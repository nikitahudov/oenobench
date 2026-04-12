# OenoBench — Process Log

Chronological lab notebook for the NeurIPS 2026 paper methodology sections.

---

## 2026-04-11 — Phase 0: Shared Infrastructure & DB Purge

### What was done
1. Built `src/scrapers/_fact_processing.py` — shared fact processing pipeline for all scrapers
2. Built `src/scrapers/_web_helpers.py` — shared web scraping utilities
3. Updated `src/scrapers/_wiki_helpers.py` — improved Wikipedia/Wikidata extraction
4. Purged 7,861 hardcoded LLM-generated facts from PostgreSQL database

### Sources & inputs
- Existing scraper codebase (audit results from 2026-04-07)
- Wikidata SPARQL endpoint (query.wikidata.org)
- Wikipedia MediaWiki API

### Methodology

**`_fact_processing.py`** provides a 4-stage pipeline applied to all scraped text:
1. **Decompose** — split compound sentences into atomic facts
2. **Resolve references** — replace pronouns/anaphora with explicit entity names
3. **Classify domain** — assign each fact to one of 6 domain categories using keyword matching
4. **Validate** — filter facts that are too short (<5 words), too long (>50 words), or lack a predicate

**`_web_helpers.py`** provides:
- Rate-limited HTTP session with proper User-Agent
- Page discovery via sitemap.xml and link crawling
- Text extraction from HTML with boilerplate removal

**`_wiki_helpers.py` updates:**
- `extract_atomic_facts()` replaces `extract_lead_sentences()` — produces properly atomic facts
- `run_sparql_filtered()` — SPARQL with country-scoped filtering
- Country-scoped SPARQL templates using P17 (country) instead of P131* (located in administrative territorial entity, transitive) to prevent off-topic contamination

**DB purge:** Identified and deleted 7,861 facts from 17 hardcoded scrapers. Database went from 24,563 to 16,702 genuine facts.

**SPARQL QID fixes:**
- Q1131296 → wine-producing region
- Q10864048 → wine region
- Q454541 → appellation
- Q156362 → winery

### Quality controls
- All purged facts traced to scrapers with zero genuine HTTP calls
- Retained only facts from 10 verified-genuine scrapers + 6 rebuilt hybrid scrapers
- New `_fact_processing.py` pipeline ensures all future facts are atomic, reference-resolved, and domain-classified

### Quantitative results
- Facts purged: 7,861
- DB before: 24,563
- DB after: 16,702
- New shared modules: 3 files

### Decisions & trade-offs
- Chose P17 (country) over P131* (administrative territory, transitive) for SPARQL scoping. P131* caused severe off-topic contamination (e.g., Bordeaux scraper pulling Austrian wine data). P17 is less granular but prevents cross-country leakage.
- Built shared infrastructure before rebuilding scrapers to ensure consistency across all rebuilds.

---

## 2026-04-11 — Phase 1: Fix 8 Rebuilt/Genuine Scrapers

### What was done
Fixed 8 scrapers that had quality issues (off-topic SPARQL results, non-atomic facts, domain bias, hardcoded data mixed with genuine):

| Scraper | Before | After | Key Fix |
|---------|--------|-------|---------|
| bordeaux.py | 155 | 484 | P131* → P17 country-scoped SPARQL; official bordeaux.com scraping |
| burgundy.py | 64 | 483 | P131* → P17; bourgogne-wines.com scraping |
| champagne.py | 356 | 466 | P131* → P17; champagne.fr (partial access) |
| italian_wine_central.py | 729 | 788 | extract_lead_sentences → extract_atomic_facts; classify_domain() |
| austria.py | 317 | 146 | Removed off-topic German wine facts; P17 filtering |
| greece.py | 236 | 255 | Removed off-topic Italian Grechetto facts; P17 filtering |
| consortiums_italy.py | 453 | 85 | Applied atomic fact pipeline; domain classification |
| ttb.py | 515 | 513 | Verified _REGULATION_FACTS as genuine CFR text; minor cleanup |

### Sources & inputs
- Wikidata SPARQL (country-scoped with P17)
- Wikipedia MediaWiki API (via updated _wiki_helpers.py)
- Official websites: bordeaux.com, bourgogne-wines.com, champagne.fr
- US Code of Federal Regulations (eCFR) for TTB

### Methodology
- Replaced `P131*` (transitive administrative territory) with `P17` (country) in all SPARQL queries to scope results to correct country
- Replaced `extract_lead_sentences()` with `extract_atomic_facts()` for proper atomic fact extraction
- Replaced hardcoded `domain="wine_regions"` with `classify_domain()` for balanced domain distribution
- Added official website scraping via `_web_helpers.py` where sites were accessible

### Quality controls
- Austria scraper: facts dropped from 317 to 146 because off-topic German wine data was correctly filtered out
- Consortiums Italy: dropped from 453 to 85 after applying atomic fact validation (many compound/non-factual statements removed)
- TTB _REGULATION_FACTS verified as genuine CFR regulatory text, not LLM-generated

### Issues encountered & resolutions
- **bordeaux.com**: Accessible, successfully scraped
- **bourgogne-wines.com**: Accessible, successfully scraped
- **champagne.fr**: Partial access only (some pages blocked)
- **brunellodimontalcino.it**: No route to host — fell back to Wikipedia/Wikidata only
- **franciacorta.wine, consorziovinonobile.it**: Not tested in this phase

---

## 2026-04-11 — Phase 2: Rebuild 17 Hardcoded Scrapers

### What was done
Rebuilt all 17 scrapers that contained 100% hardcoded LLM-generated facts. Each was rewritten to use genuine Wikipedia articles, Wikidata SPARQL queries, and official website scraping where available.

### Per-scraper details

| Scraper | Old Lines | New Lines | Lines Removed | Data Sources |
|---------|-----------|-----------|---------------|-------------|
| usa_enrichment.py | 1,737 | 871 | -866 | 22 Wikipedia articles + SPARQL |
| europe.py | 4,846 | 1,010 | -3,836 | 1,297 SPARQL facts verified; removed SPAIN_APPELLATIONS, GERMANY_REGIONS, PORT_CATEGORIES |
| italy.py | 2,093 | 874 | -1,219 | Removed DOCG_DATABASE (1,010 lines); Wikipedia + SPARQL |
| newworld.py | 2,439 | 1,047 | -1,392 | Removed 5 *_KNOWLEDGE dicts (AUSTRALIA, NZ, SA, ARG, CHILE); Wikipedia + SPARQL |
| rhone_loire_alsace.py | — | — | — | Wikipedia + SPARQL (inter-rhone.com unreachable) |
| spain_enrichment.py | — | — | — | Wikipedia + SPARQL |
| portugal_enrichment.py | — | — | — | Wikipedia + SPARQL |
| germany_enrichment.py | — | — | — | Wikipedia + SPARQL |
| eu_oiv.py | — | — | — | Wikipedia + SPARQL; removed hardcoded EU regulation dicts |
| hungary_georgia.py | — | — | — | Wikipedia + SPARQL |
| croatia_slovenia.py | — | — | — | Wikipedia + SPARQL |
| australia_nz_enrichment.py | — | — | — | Wikipedia + SPARQL |
| south_africa_enrichment.py | — | — | — | Wikipedia + SPARQL |
| south_america.py | — | — | — | Wikipedia + SPARQL |
| canada.py | — | — | — | Wikipedia + SPARQL |
| england.py | — | — | — | Wikipedia + SPARQL |
| lebanon_israel.py | — | — | — | Wikipedia + SPARQL |

### Sources & inputs
- Wikipedia MediaWiki API — category pages and article content for each country/region
- Wikidata SPARQL — country-scoped queries using P17 property
- Official websites where accessible (bordeaux.com, bourgogne-wines.com, champagne.fr partial)

### Methodology
All 17 scrapers were rewritten following the same pattern:
1. Remove all hardcoded data dictionaries (*_KNOWLEDGE, *_DATABASE, *_APPELLATIONS, etc.)
2. Implement genuine Wikipedia article fetching via `_wiki_helpers.py`
3. Implement genuine Wikidata SPARQL queries scoped by country (P17)
4. Apply `_fact_processing.py` pipeline (decompose → resolve → classify → validate)
5. Use `_web_helpers.py` for any official website scraping

### Quality controls
- Every fact must trace to a genuinely fetched URL (Wikipedia article, SPARQL endpoint, or official website)
- All facts processed through atomic fact pipeline
- Domain classification via `classify_domain()` instead of hardcoded `wine_regions`

### Quantitative results
- Total hardcoded lines removed: ~26,000+
- Scrapers rebuilt: 17
- All scrapers now use genuine HTTP-fetched data only

### Decisions & trade-offs
- **inter-rhone.com** (Rhone Valley): connection timeout — fell back to Wikipedia/Wikidata only
- **brunellodimontalcino.it**: no route to host — Wikipedia/Wikidata only
- Genuine scraping yields fewer facts than hardcoded versions, but every fact has verifiable provenance
- Accepted lower fact counts as the cost of data integrity for NeurIPS submission

### Issues encountered & resolutions
- Several official wine body websites unreachable (inter-rhone.com, brunellodimontalcino.it)
- Resolution: Wikipedia + Wikidata provide sufficient coverage; official sites can be retried later
- Some country SPARQL queries return fewer results than expected due to incomplete Wikidata coverage
- Resolution: supplemented with Wikipedia article scraping for broader coverage

---

## 2026-04-12 — Phase 3: Verification & Quality Cleanup

### What was done
1. Automated DB cleanup — removed low-quality facts via SQL pattern matching
2. Dangling reference resolution — resolved 129 facts, deleted 72 unresolvable
3. Over-length fact handling — deleted >50 word facts, confidence-reduced 31-50 word facts
4. Portugal over-representation trimming — removed 1,422 generic admin-region facts
5. Near-duplicate removal — deleted 224 duplicate facts
6. Refreshed `fact_count_summary` table for paper
7. Exported CSV distributions to `data/exports/`

### Methodology — Automated cleanup rules
| Rule | Pattern | Action | Count |
|------|---------|--------|-------|
| Marketing text | `discover the\|join us\|visit our\|come and\|book now\|subscribe` | Delete | 19 |
| Website boilerplate | `cookie\|privacy policy\|terms of use\|third parties` | Delete | 9 |
| Disambiguation pages | `may refer to:\|disambiguation` | Delete | 3 |
| Off-topic non-wine | `footballer\|politician\|rugby\|soccer\|tennis` | Delete | 4 |
| Promo with exclamation | `!\s` + promotional keywords | Delete | 3 |
| Under 5 words | word count < 5 | Delete | 31 |
| Non-English text | French sentence patterns from vinsdeloire.fr | Delete | 1 |
| Truncated sentences | No ending punctuation, >20 chars | Delete | 100 |
| Near-duplicates | Same first 60 chars, keep longer | Delete shorter | 224 |
| Portugal generic | "X is a wine region in Y, Portugal." (<80 chars, no detail) | Delete | 1,422 |
| Dangling references | Starts with It/He/She/They + Wikipedia source | Resolve subject | 129 resolved |
| Unresolvable dangles | Starts with It/He/She/They, no source context | Delete | 72 |
| Over 50 words | word count > 50 | Delete | 24 |
| 31-40 words | word count 31-40 | Reduce confidence ×0.8 | 694 |
| 41-50 words | word count 41-50 | Reduce confidence ×0.6 | 216 |

### Quantitative results
- Before cleanup: 40,020 facts
- After cleanup: 38,104 facts
- Removed: 1,916 facts (4.8%)
- Confidence-adjusted: 910 facts (31-50 words)

### Final database statistics
| Metric | Value |
|--------|-------|
| Total facts | 38,104 |
| Countries covered | 22 |
| Unique sources | ~580 |
| With entities | 36,002 (94.5%) |
| Tier 1 (official) | 7,472 (19.6%) |
| Tier 2 (authoritative) | 29,199 (76.6%) |
| Tier 3 (reliable) | 1,433 (3.8%) |

### Domain distribution (final)
| Domain | Facts | % |
|--------|-------|---|
| wine_regions | 18,943 | 49.7% |
| producers | 6,215 | 16.3% |
| grape_varieties | 5,959 | 15.6% |
| viticulture | 3,635 | 9.5% |
| wine_business | 1,985 | 5.2% |
| winemaking | 1,367 | 3.6% |

### Source type distribution
| Source Type | Sources | Facts | % |
|-------------|---------|-------|---|
| Encyclopedia (Wikipedia) | 265 | 13,083 | 34.3% |
| Knowledge base (Wikidata) | 3 | 11,806 | 31.0% |
| Dataset (HuggingFace/Kaggle) | 3 | 4,739 | 12.4% |
| Gov. extension (UC IPM, Penn State) | 3 | 1,786 | 4.7% |
| Gov. registry (INAO) | 1 | 1,471 | 3.9% |
| Gov. data (UC Davis AVA) | 1 | 1,412 | 3.7% |
| Academic journals (OENO One, Vitis) | 279 | 891 | 2.3% |
| Wine consortiums | 10 | 681 | 1.8% |
| National wine bodies | 3 | 566 | 1.5% |
| Government (TTB) | 3 | 514 | 1.3% |
| Other | 9 | 1,155 | 3.0% |

### Known limitations
- Portugal still over-represented (6,176 facts, 16.2%) due to broad Wikidata wine region coverage
- wine_regions domain at 49.7% — higher than 40% target but improved from initial 50%+
- 910 facts between 31-50 words remain (confidence-reduced, not atomic)
- Some off-topic SPARQL leakage remains (French Polynesia in France queries, etc.)
- inter-rhone.com, brunellodimontalcino.it unreachable — Rhône/some Italian consortium data limited
- Argentina, Chile, Lebanon have low counts (<150 facts each)

---

## 2026-04-12 — Phase 2: Question Generation Pipeline (Infrastructure + Strategies 1-2)

### What was done
Built the question generation pipeline — 7 shared infrastructure modules and 2 of 5 generation strategies:

**Shared modules (src/generators/):**
1. `_llm_client.py` — Unified OpenRouter client (5 LLMs via single API)
2. `_prompts.py` — Prompt templates for all generation strategies (~400 lines)
3. `_schemas.py` — Pydantic output validation with 3-tier JSON extraction
4. `_id_generator.py` — WB-{DOMAIN}-{SEQ}-L{DIFF} question ID minting
5. `_question_db.py` — Atomic insertion with provenance linkage
6. `_fact_sampler.py` — Stratified fact sampling with source diversity
7. `_dedup.py` — Embedding-based semantic deduplication via pgvector

**Generation strategies:**
8. `fact_to_question.py` — Strategy 1: LLM converts facts → questions (40%, 4,000 target)
9. `template_generator.py` — Strategy 2: 45 deterministic templates (25%, 2,500 target)

### Sources & inputs
- 38,104 verified facts in PostgreSQL (from Phase 1)
- OpenRouter API for unified LLM access
- 5 generator models: Claude Opus 4.6, ChatGPT 5.4, Gemini 3.1, Llama 3.1 405B, Qwen 3.5
- Existing DB schema: questions, generation_metadata, question_facts, question_sources tables

### Methodology

**LLM client design:** Single OpenRouter API gateway replaces per-provider SDKs. Uses `openai` library with custom `base_url`. Tenacity retry with exponential backoff (2-16s, max 4 attempts). Rate limited at 1 request/1.5s.

**Prompt design (fact-to-question):** System prompt instructs LLM to act as wine education assessment designer. User prompt provides: verified fact + source name + target domain/difficulty/cognitive dimension/question type. LLM reformats fact into question — never invents facts. JSON output schema embedded in prompt.

**Template-based generation:** 45 parameterized templates across 6 domains (15 wine_regions, 8 grape_varieties, 6 producers, 6 winemaking, 5 viticulture, 5 wine_business). Templates extract entity values from fact JSONB, source distractors from other facts of same entity type. Zero LLM involvement — purely deterministic.

**Output validation:** Pydantic models validate JSON structure (option counts per question type, correct_answer matches option IDs, field lengths). Three-tier JSON extraction handles markdown fences, raw JSON, and regex brace extraction.

**Provenance:** Every question atomically linked to source facts (question_facts), external sources (question_sources), and generation metadata (generator model, version, method, prompt hash, raw LLM response).

### Quality controls
- Pydantic validation rejects malformed LLM output before DB insertion
- Semantic deduplication via pgvector (cosine similarity threshold 0.92)
- Parse failure → single retry, then skip (never insert unvalidated questions)
- Source diversity in fact sampling (max 5 facts per source_id per sample)

### Quantitative results
- Total new code: 2,779 lines across 13 files (9 new, 4 modified)
- Template registry: 45 templates across 6 domains
- All 9 files pass syntax check
- Both CLIs verified: `--help`, `--test-run`, `--list`, `--validate`
- Template test run: 10/30 questions generated (wine_regions and grape_varieties matched; other domains need richer entity data)

### Decisions & trade-offs
- **OpenRouter over per-provider SDKs:** Single API key, unified rate limiting, no SDK version conflicts. Slightly higher per-token cost but dramatically simpler implementation.
- **5 LLM generators (even 20% split):** Equal distribution across Claude/ChatGPT/Gemini/Llama/Qwen for maximum bias diversity. Paper can analyze self-preference across all 5.
- **Incremental build:** Strategies 1-2 built first (65% of target). Quality review before building remaining 3. Reduces risk of prompt-quality issues at scale.
- **Synchronous generation:** Matches scraper patterns. ~6 hours per model for 2,100 questions at 1.5s/call. Acceptable for one-time pipeline.
- **Template generator entity-dependent:** Templates only match facts with required entity types. Domains with sparse JSONB entities (winemaking, viticulture) will rely more on LLM strategies.

### Issues encountered & resolutions
- Template test run showed 0 matches for winemaking, viticulture, wine_business, producers. Root cause: facts in these domains have fewer structured entities in JSONB. Resolution: these domains will rely primarily on fact-to-question (LLM) strategy rather than templates. Template contribution will be weighted toward wine_regions and grape_varieties.
