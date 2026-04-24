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

---

## 2026-04-15 — Phase 2: Question Generation Quality Improvements

### What was done
Major quality overhaul of the 3 LLM-based strategies (comparative, scenario, distractor) based on domain expert review of test batches. Six changes across 5 files (4 commits).

### Methodology

**1. Entity affinity scoring (`_fact_sampler.py`)**
- New `_entity_affinity_score()` function scores 0-1 similarity between fact pairs using entity JSONB metadata (shared country +0.3, shared region +0.3, comparable entity types +0.2)
- Comparative: SQL join changed from `a.subdomain = b.subdomain` to `a.country = b.country` (with subdomain fallback). Candidate pairs ranked by affinity, threshold 0.2
- Scenario: Cluster cohesion changed from entity *type* overlap to entity *name* overlap. Keyword matching uses content-keyword extraction with wine-generic stopword removal, threshold raised from 3→4
- Distractor: Priority 1 redefined as same-country + same-entity-type. Fallback candidates ranked by affinity score. Minimum lowered from 3→2

**2. Fact richness filter (`_fact_sampler.py`)**
- New `_is_fact_rich()` rejects thin geographic facts ("X is a wine region in Y", "X covers N hectares") from strategies 3-5 via regex pattern matching
- Short facts (<12 words) must contain wine-content signals (grape, barrel, AOC, tannin, etc.) to qualify
- Applied in `sample_fact_pairs()`, `sample_fact_clusters()`, `sample_confusable_facts()`

**3. Blend-as-variety rejection (`_fact_sampler.py`)**
- New `_BLEND_AS_VARIETY` regex rejects facts treating blend categories as grape varieties
- Applied globally in `_is_fact_specific()` (affects all strategies)

**4. Inference-over-recall prompt design (`_prompts.py`)**
- All 4 prompt templates updated with "INFERENCE OVER RECALL" instruction block
- Key instruction: present observable evidence → ask test-taker to reason backward to knowledge
- Inspired by Gemini's Barbera/Nebbiolo question (domain expert rated it "brilliant")
- Distractors must reverse/swap key relationships, not just state different facts

**5. Gemini/Qwen max_tokens fix (`_llm_client.py`)**
- Per-model `_MODEL_MAX_TOKENS` overrides: Gemini and Qwen get 6000 tokens (default 2000)
- Root cause: verbose JSON responses truncated mid-string, ~90% parse failure rate for Gemini

**6. Answer option shuffling (`_schemas.py`)**
- `_shuffle_options()` randomizes option order and remaps correct_answer IDs after every LLM parse
- Eliminates position A bias (LLMs overwhelmingly place correct answer first)
- Verified ~25% per-position distribution over 100 trials

### Quality controls
- ~393 blend-as-variety facts filtered from all strategies
- ~6,000+ thin geographic facts filtered from strategies 3-5
- LLM skip signals working correctly: Claude rejected incoherent scenario clusters (copyright disclaimers, personnel committee facts) and non-comparable pairs (different countries, trivial metadata)
- Affinity scoring verified: Barolo vs Barbaresco = 0.5 (pass), Niagara vs Douro = 0.2 (borderline pass), no cross-country pairs observed in test runs

### Quantitative results
- Scenario: 3/3 generated in final test run (after richness filter), all substantive wine content
- Comparative: works well on winemaking/grape_varieties/viticulture domains; wine_regions limited by high ratio of thin facts
- Distractor: skip rate appropriate — rejects cross-category distractors (AVA establishment vs AOC alcohol requirements)
- Gemini parse success rate: ~10% (before fix) → ~80%+ (after max_tokens increase)

### Multi-model quality ranking (scenario strategy, expert-reviewed)
1. **Gemini** — Best inference-style questions, concise framing, elegant distractor design
2. **ChatGPT** — Strong synthesis, good fact integration, slightly more verbose
3. **Claude** — Solid, reliable, occasionally over-engineered business framing
4. **Qwen** — Functional but slow (65s), needed retry for JSON parsing
5. **Llama** — Weakest: simpler question structure, doesn't fully synthesize facts

### Decisions & trade-offs
- Affinity threshold set to 0.2 (not 0.3): many facts lack explicit country entities, 0.3 was too strict for wine_regions domain
- Over-fetch for comparative increased to count×20 to compensate for richness filtering
- Minimum distractors lowered from 3→2: stricter matching produces fewer but better distractors, LLM supplements remaining options
- Inference-over-recall applied to all strategies including fact-to-question (40% of questions): biggest impact on overall benchmark quality

### Human review notes
- Domain expert verified scenario strategy output: marked as **Verified**
- Comparative and distractor marked as **Built**, verification pending (scheduled for 2026-04-16)
- Expert identified blend-as-variety issue in Q3 of Iberian wine scenario — led to filter implementation
- Expert ranked Gemini's Barbera/Nebbiolo question as exemplar for all future question design

## 2026-04-17 — Phase 2: Comparative Strategy — Dimension-Aware Pairing

### What was done
Added dimension-aware pairing and type-specific prompts to the comparative strategy. Facts are classified into semantic dimensions (aging_requirements, soil_geology, climate, etc.) and paired by matching dimension. Three type-specific templates (same_vs_different, which_one, most_least) auto-selected based on fact content.

## 2026-04-18 — Phase 2: Distractor Strategy — Dimension-Aware Sampling & Type-Specific Templates

### What was done
Applied the dimension-aware pattern from comparative to the distractor mining strategy. Three changes across 3 files.

### Methodology

**1. Dimension-aware distractor sampling (`_fact_sampler.py`)**
- `sample_confusable_facts()` now classifies target and candidate distractors using existing `_classify_dimension()`
- Candidates scored with +0.5 bonus for dimension match, -0.2 penalty for dimension mismatch
- All candidates sorted by score: dimension-matched distractors ranked first
- Each returned fact enriched with `_dimension` and `_confusability_context` metadata
- Over-fetch increased from count×5 to count×8 in Priority 1 to compensate for dimension scoring

**2. Auto distractor type selection (`_fact_sampler.py`)**
- New `_auto_distractor_type(target_dim, distractor_dims)` function
- `numeric`: target has numeric dimension (area_size, production_volume, alcohol_level, yield_regulation) AND majority of distractors share it
- `attribute_swap`: target dimension matches majority of distractors (non-numeric)
- `entity_id`: mixed/unclassified dimensions (fallback)

**3. Type-specific distractor templates (`_prompts.py`)**
- `DISTRACTOR_TEMPLATE_ATTRIBUTE_SWAP`: all facts share same dimension. Question swaps attribute values between confusable entities
- `DISTRACTOR_TEMPLATE_ENTITY_ID`: mixed dimensions. Present clues, ask which entity matches. Fallback template
- `DISTRACTOR_TEMPLATE_NUMERIC`: numeric dimensions. Use real numeric values from similar entities as distractors
- Generic `DISTRACTOR_TEMPLATE` updated to accept `{confusability_context}` placeholder
- All templates include inference-over-recall instructions and skip conditions

**4. Template selection in generator (`distractor_miner.py`)**
- `DISTRACTOR_TEMPLATE_MAP` mirrors comparative's pattern
- `_sample_target_and_distractors()` returns 3-tuple: (target, distractors, dtype)
- `_generate_one()` selects template by type, passes `dimension` and `confusability_context`
- Distractor type tracked in tags (`distractor:attribute_swap`, etc.) and `template_id`
- Enhanced `--test-run` output: shows dimension, confusability context, auto-selected type
- Enhanced `--validate`: reports distractor type distribution (from tags)

### Decisions & trade-offs
- Dimension-unmatched distractors NOT filtered out, only ranked lower — some questions work with mixed dimensions
- Generic template kept as fallback for edge cases where no type-specific template matches
- `_auto_distractor_type` uses simple majority rule: if ≥50% of distractors match target dimension, use typed template

## 2026-04-18 — Phase 2c: Quality Audit — Multi-Agent Team Architecture

### What was done
Built a multi-agent quality-audit framework (`src/qa/`) that gates the full-scale 10k question-generation run. After five strategies were tuned iteratively through April 12–18 (blend-as-variety, thin-geo, inference-over-recall, dimension-aware pairing, option shuffling, Gemini/Qwen token fix), each fix found issues the previous passes missed. The next round of iterative tuning would burn LLM budget blindly, so we instead built a final, critical, multi-agent audit against a stratified 600-question pilot corpus. Output: a reproducible audit report and a prioritised improvement plan that drives regeneration Go/No-Go.

### Sources & inputs
- Existing fact base: 38,104 verified facts
- Existing generator modules: `src/generators/{template_generator, fact_to_question, comparative_generator, scenario_generator, distractor_miner}.py`
- Existing quality filters reused: `_classify_wine_category`, `_classify_dimension`, `_VAGUE_PATTERNS`, `_BLEND_AS_VARIETY`, `_THIN_GEO_PATTERNS` from `_fact_sampler.py`
- Existing LLM infra reused: `_llm_client.py` (OpenRouter, retry, rate limit, JSON extraction)
- Existing views reused: `v_self_preference`

### Methodology

**Architecture: 4 teams, 9 agents, 2 modes (per-question vs population-level)**

Team A — Static integrity (no LLM, ~1 min for 600 Qs):
- A1 `LexicalHygiene` — extended vague/marketing/blend regex over stem, options, explanation
- A2 `BiasStats` — χ² on correct-answer position uniformity; Mann–Whitney U on correct-vs-distractor length
- A3 `FactEcho` — token LCS ratio + longest common n-gram vs source fact
- A4 `TemplateFingerprint` — tiny POS-bigram logistic regression distinguishing template from LLM questions; AUC and per-question template-likeness scoring

Team B — Answer validity (tri-judge panel: Claude Opus 4.7, ChatGPT 5.4, Gemini 3.1 Pro; Llama/Qwen excluded to keep them as generator-bias subjects):
- B1 `TriJudgeAnswer` — each judge picks answer with source, also verifies fact→key support; majority vote vs claimed key
- B2 `ClosedBookSolvability` — same judges answer without source; flags questions solvable from world knowledge

Team C — Adversarial probes (MVA: deterministic slice only):
- C2 `CategoryLeak` — wine-category classifier on correct + distractors; fail if stem mentions a category and any distractor has a different one

Team D — Population-level bias:
- D1 `SelfPreference` — 5×5 evaluator×author matrix; each generator model answers a balanced per-author sample; own-vs-other accuracy delta
- D3 `SkewAudit` (stats-only) — χ² of question-linked country distribution vs fact-base distribution; per-strategy subdomain Herfindahl

**Deferred agents** (explicit, with escalation triggers in the report):
- C1 DistractorDifficulty (LLM per-distractor plausibility)
- B3 ParaphraseStability, B4 Ambiguity (LLM)
- C3 SourceSwap, C4 DimensionCognitiveAudit (LLM)
- D2 DedupCalibration (threshold P/R sweep)
- D3 cultural-framing slice (LLM label)

**Pipeline**
```
Stage 0 build-corpus    → 600 Qs tagged `audit_pilot_v1`
Stage 1 Team A (static) → ~1 min, no cost
Stage 2 Team C + D3     → seconds, no cost
Stage 3 Team B + D1     → LLM stage, est. $90–$115 total
Stage 4 aggregate       → per-agent × per-strategy × per-generator roll-ups
Stage 5 build-reports   → docs/QUALITY_AUDIT_REPORT.md + docs/GENERATION_IMPROVEMENT_PLAN.md
```

### Quality controls & reproducibility contract
- `audit_runs.config_hash = sha256(sorted(agent_id+version) | sorted(model_ids) | seed | thresholds_json)`
- Every finding idempotent on `(run_id, question_id, agent_id, agent_version)` — re-runs are cache hits unless an agent's version bumps
- Every LLM judge call stores prompt hash, model snapshot, latency, full raw content in `payload`
- Gold-standard calibration set: 60 questions (12/strategy), reviewer fills 8 rubrics (answer_correct, distractors_plausible, not_ambiguous, source_faithful, needs_source, no_vague_language, difficulty_match, cognitive_match); Cohen's κ per rubric reported

### Quantitative results
Pipeline ready to run; no audit data yet (questions table currently empty — awaits full generation run gated on this audit's go/no-go).
- Target corpus: 600 questions (120 per strategy; LLM strategies split 120 across 5 generators × 6 domains ≈ 4/cell)
- Estimated cost: corpus build $45–60 + Team B $70–90 + D1 $15–25 = **$130–175 end-to-end**
- Test suite: 26 unit tests green across `_scoring`, `_findings`, Team A (4 agents), Team C

### Decisions & trade-offs
- **MVA over Thorough**: user chose 5-LLM-agent minimum viable audit (~$80 LLM spend) but asked for "as many weaknesses as possible". Reconciliation: include all 4 static/analytics agents (A1–A4, C2, D3) for free on top of the MVA LLM core (B1, B2, D1). Result: 9 agents instead of 5, same budget.
- **Judge panel excludes Llama/Qwen**: they are subjects of the bias audit (D1), not arbiters. Three-way panel (Claude/ChatGPT/Gemini) keeps per-question cost at 6 calls (B1+B2 share scaffold) while preserving disagreement signal.
- **LLM-level adversarial probes deferred (C1, C3, B3, B4, C4)**: each has an explicit escalation trigger in the report (e.g., "if A4 AUC ≥ 0.9, run C1 + B4 on flagged subset") so follow-up cost is contingent, not upfront.
- **Tiny logistic regression in `_scoring.py` instead of sklearn**: OenoBench avoids adding an sklearn dependency just for the A4 classifier; a hand-rolled L2 logreg on ~600 examples × ~300 features trains in <1 s.
- **Corpus builder subprocess-per-cell**: instead of importing each generator's internals, we shell out to the battle-tested CLIs with controlled `--count`/`--domain`/`--generator` flags and tag newly-created rows post-hoc. Adds ~1 s/call process overhead but avoids coupling.

### Issues encountered & resolutions
- None so far — test suite green on first run; schema applied cleanly; CLI loads and enforces the "no questions tagged → error" guard.

### Human review notes
- Plan approved by user (see `/home/winebench/.claude/plans/glittery-conjuring-spindle.md`)
- User explicitly chose MVA (5 LLM agents) over Comprehensive (12 agents) to keep cost under $200
- User agreed to hand-grade 60 questions across 8 rubrics once corpus is built
- Gold CSV export/import round-trip implemented (no review done yet)

## 2026-04-19 — Phase 2d: Audit Run #1 (audit_pilot_v1, 472 questions)

### What was done
Executed the full QA pipeline end-to-end against a freshly-built 472-question pilot corpus. Output: two paper-ready Markdown reports (`docs/QUALITY_AUDIT_REPORT.md`, `docs/GENERATION_IMPROVEMENT_PLAN.md`) and a Go/No-Go verdict on starting the 10k full generation run.

### Sources & inputs
- Corpus: 472 questions tagged `audit_pilot_v1`, generated by `python -m src.qa.orchestrator build-corpus --per-strategy 120 --seed 42`. Stratification (per `_corpus.build_pilot_corpus`): for LLM strategies, ~4 Qs per (5 generator × 6 domain) cell; template strategy splits 120 across 6 domains × 20 each.
- Audit run ID: `e8eba8bb-cb49-42cd-9e32-c741c987043e`, config hash `a4b016003b3be5b6dcfab738ed31c5ab8399e1188835095ff12d928a60fb90f8`, seed 42.
- Judge models: `claude` (Opus 4.7), `chatgpt` (GPT-5.4), `gemini` (3.1 Pro). Llama and Qwen excluded as judges (kept as generator subjects for D1).

### Methodology
Pipeline executed in stages, all writing into `audit_findings`:
1. `build-corpus` → 472 tagged questions (49 template + 120 fact_to_question + 85 comparative + 119 scenario + 99 distractor; high skip rates on comparative/scenario/distractor due to coherence/dimension filters).
2. `export-gold --size 60 --seed 42` → 60-question reviewer sheet at `data/reports/gold_sheet.csv` (12/strategy, 8 rubrics).
3. `run-team-a` → A1 LexicalHygiene, A2 BiasStats, A3 FactEcho, A4 TemplateFingerprint (all deterministic, no LLM).
4. `run-team-c` → C2 CategoryLeak (deterministic, reuses `_classify_wine_category`).
5. `run-team-d` → D1 SelfPreference (5 evaluator × 5 author × 15 sample = 375 LLM calls), D3 SkewAudit (pure SQL).
6. `run-team-b` → B1 TriJudgeAnswer + B2 ClosedBookSolvability (3 judges × 472 Qs × 2 prompt variants = 2,832 LLM calls). Refactored mid-run to write findings inline so the audit could be monitored and resumed.
7. `build-reports` → renders the two paper-ready Markdown deliverables.

### Quality controls
- All findings idempotent on `(run_id, question_id, agent_id, agent_version)` — re-runs are cache hits.
- `config_hash = sha256(sorted agents+versions | sorted model IDs | seed | thresholds)` stored on the audit run.
- Three bugs surfaced and fixed during the run:
  1. Population-level findings (A2, D1) wrote multiple rows per agent under the same `(run, NULL, agent, version)` idempotency key — only the first committed. **Fix:** bundle per-cell payloads into one finding.
  2. Team B batched all findings until the 4-hour run completed — no progress signal, no resume on failure. **Fix:** `write_finding_fn` callback wired through `orchestrator._run_team` for inline writes.
  3. A4 logistic regression overflowed `math.exp` on diverged weights. **Fix:** added `_sigmoid()` with [-35, 35] clamp.
- 26 unit tests green throughout.

### Quantitative results

| Stage | Wall time | LLM calls | Cost |
|---|---|---:|---:|
| Corpus build | 2h50m | 480 | ~$3.50 |
| Team A | 1 min | 0 | $0.00 |
| Team C | 5s | 0 | $0.00 |
| Team D (D1+D3) | 25m | 375 | $0.45 |
| Team B (B1+B2) | 3h25m | 2,832 | $4.55 |
| **Total** | **~7h** | **3,687** | **$8.50** |

Cost came in **15× lower than the $130–175 estimate** — primarily because B1/B2 prompts are short (~300 tokens input, ~50 tokens output) so each judge call runs ~$0.0015 instead of the ~$0.025 used in the upfront estimate.

### Findings — defect leaderboard (impact = 3·fails + warns + 2·errors)

| Rank | Defect | Agent | Counts (out of 472) | Impact |
|---:|---|---|---|---:|
| 1 | Verbatim source copying in Q + correct option | A3 FactEcho | 164 fail / 181 warn / 127 pass | 673 |
| 2 | Question solvable from world knowledge alone | B2 ClosedBookSolvability | 140 fail / 150 warn / 182 pass | 570 |
| 3 | Key disagrees with judge consensus | B1 TriJudgeAnswer | 22 fail / 57 warn / 393 pass | 123 |
| 4 | Templates statistically distinguishable from LLM Qs | A4 TemplateFingerprint | 21 fail / 12 warn (pop AUC=0.959) | 75 |
| 5 | Vague / marketing / blend-as-variety phrasing | A1 LexicalHygiene | 13 fail / 13 warn | 52 |
| 6 | Wine-category distractor leak | C2 CategoryLeak | 5 fail / 9 warn | 24 |
| 7 | Country over-representation 4.46× (Chile, Israel, US, Austria) | D3 SkewAudit | FAIL (single pop finding) | 3 |
| 8 | Position / length bias on at least one strategy×generator cell | A2 BiasStats | FAIL (single pop finding) | 3 |
| 9 | ChatGPT shows ~12pp self-preference advantage | D1 SelfPreference | warn (max Δ = 0.117) | 1 |

### Decisions & trade-offs
- **Started Team B and Team D in parallel** — they write to disjoint agent_ids in `audit_findings`, no contention. Halved wall-clock time.
- **Killed Team D mid-run after the bundling bug surfaced**, fixed `team_d_population.py`, re-ran. Cost of waste: <$0.50.
- **Refactored Team B mid-run for inline writes.** Killed the existing run (which would have batched 4 hours of findings before writing), fixed `team_b_validity.py + orchestrator.py`, re-ran. Cost of waste: ~$0.15.
- **Did not run import-gold** — reviewer is grading the 60-Q sheet offline; gold calibration will appear in the report only after `import-gold` and a re-render of `build-reports`.

### Issues encountered & resolutions
1. **Population-finding dedup bug** (A2 + D1) — root cause: `audit_findings` unique constraint on `(run_id, COALESCE(question_id::text, ''), agent_id, agent_version)` collides for population-level findings (question_id=NULL). Fix: bundle per-cell payloads into one finding's payload. See `team_a_static.run_a2_bias_stats` and `team_d_population.run_d1_self_preference`.
2. **Logreg overflow** — A4 `fit_logreg` sometimes produced `z` outside the safe range for `math.exp`. Fix: clamp z in `_sigmoid()`.
3. **Team B batch-writing prevented monitoring/resume** — fix: optional `write_finding_fn` callback; orchestrator wires it in for Team B only.
4. **Smoke-test waste** — initial `build-corpus --per-strategy 5 --skip ...` on fact_to_question created 30 subprocess calls because `per_cell = max(1, 5 // 30) = 1`. Not a bug, but a sign that small smoke tests are inefficient with the per-cell partition. Used the smoke run only as a pipeline-validity check; full pilot used `--per-strategy 120` (where per_cell=4 is correct).

### Regeneration Go/No-Go: BLOCKED

Three defects exceed the gate thresholds in `docs/GENERATION_IMPROVEMENT_PLAN.md`:
- A3 fail rate 35% vs ≤2% threshold (×17 over).
- B2 closed-book leakage rate at Level 3/4 questions well above 50% threshold.
- D3 country over-representation ratio 4.46× vs ≤1.5× threshold (×3 over).

Critical fixes required before re-running the audit (see `CURRENT_STATUS.md` Phase 2d "Critical fixes required" section for code paths):
1. A3 paraphrase enforcement — prompt + LCS post-LLM rejector.
2. B2 anti-leakage prompt rewrite — force fact-specific terminology.
3. D3 per-country sampling cap in `_fact_sampler.sample_facts`.

### Human review notes
- Gold-sheet at `data/reports/gold_sheet.csv` exported 60 questions stratified across 5 strategies (12/strategy). Reviewer is grading 8 rubrics offline.
- Once imported via `python -m src.qa.orchestrator import-gold --csv-path data/reports/gold_sheet.csv --reviewer <name>`, the next `build-reports` will populate the §6 Gold Calibration section with Cohen's κ per rubric. Any LLM-judge signal where κ<0.6 will be downweighted in §3–4 strategy/generator scoring.

## 2026-04-19 — Phase 2e: v2.1 multi-agent execution + Audit Run #2

### What was done
Implemented v2.1 of `docs/GENERATION_IMPROVEMENT_PLAN.md` via 4 parallel `Agent` worktree teams (per `docs/IMPLEMENTATION_AGENT_ARCHITECTURE.md`), merged into main, ran audit run #2 (`audit_pilot_v2`, 292 Qs, $7.64), wrote `docs/AUDIT_RUN_2_COMPARISON.md` and `docs/PATH_TO_10K.md` (the v2.2 forward plan).

### Sources & inputs
- v2.1 plan in `docs/GENERATION_IMPROVEMENT_PLAN.md`
- Multi-agent architecture in `docs/IMPLEMENTATION_AGENT_ARCHITECTURE.md`
- Run #1 findings in `audit_findings` for `e8eba8bb-…`

### Methodology

**Multi-agent execution.** 4 parallel `Agent(isolation="worktree", mode="acceptEdits")` calls, one per team scope:
- Team α (worktree-agent-a91fd096, commit 27b55c7): orchestrator allocation v2.1 + new `src/generators/_verify.py` Llama/Qwen independent-solver + A3 paraphrase guard (prompt + LCS post-LLM rejector). 51 tests added.
- Team β (worktree-agent-aa79264a, commit b0547e5): per-country quota in `_fact_sampler.py` + universal wine-category filter + 8 new vague-pattern regexes harvested from gold review notes. 33 tests added.
- Team γ (worktree-agent-a4ea5991, commit a4261ee): full template overhaul per Plan §6.3a-e — embedding-similarity distractors via OpenRouter `text-embedding-3-small`, source-fact-anchored generation (42 of 48 templates marked `requires_fact_specific=True`), per-instance difficulty heuristic, 4-6 paraphrase variants per template (242 total), optional LLM-paraphrase post-pass. 24 tests added.
- Team δ (worktree-agent-aad56091, commit dad59b0): multi-fact gold export (`source_facts` column with `[1]/[2]` prefixes), B2 5-judge panel + tighter thresholds, C4 difficulty-audit promoted from deferred, report-renderer upgrades (per-rubric κ, per-strategy/generator gold pass rates). 15 tests added.

Coordinator merged in dependency order (α → β → γ → δ) with `git merge --no-ff` and ran `pytest tests/qa/ tests/generators/` after each: green at every step. Final test count: **123 passing**.

**Audit run #2.** Built `audit_pilot_v2` corpus stopped early at 292 Qs across 4 strategies (template 43, fact_to_q 120, comparative 78, scenario 51, distractor 0). The slow scenario throughput was traced to Team β's universal wine_category filter on `sample_fact_clusters` requiring 100% category match across 2-4 cluster facts; flagged for v2.2 walk-back to 75%. Then ran teams A → C+C4 → D → B in parallel where possible; total audit cost $7.64. Mid-run debug: C4 produced 291/292 errors because Gemini 3.1 Pro consumed all 300 max_tokens on internal reasoning; bumped `max_tokens` to 1500 in `team_c_probes.py` and re-ran successfully.

### Quality controls
- 26 + 97 = 123 unit tests green throughout
- `git status` after each team merge to detect mis-cwd writes (Team α did mis-cwd; cleaned up via `git restore` since canonical version was safely in worktree branch)
- `audit_runs.config_hash` stable across re-runs; only C4 needed a manual finding-delete + re-run (severity transitions error→pass after the max_tokens fix)
- Verifier's fail-closed semantics: API errors and unparseable verifier responses rejected, never silent-accept

### Quantitative results

| Metric | v1 | v2 | Change |
|---|---:|---:|---|
| Corpus | 472 Qs | 292 Qs | smaller (build stopped early) |
| Cost | $8.49 | $7.64 | within budget |
| A3 fail | 35% | 5.8% | **WIN** ✓ paraphrase guard works |
| B1 fail | 4.7% | 2.7% | **WIN** ✓ Llama/Qwen verifier catching wrong-keys |
| D1 self-pref | warn (Δ=0.117) | PASS (Δ=0.10) | **WIN** ✓ allocation cap helped |
| D3 country | 4.46× | 3.38× | improved (still > 1.5× gate) |
| A4 AUC | 0.96 | 0.96 | unchanged — phrasing diversification ineffective |
| B2 fail | 30% | 38% | WORSE — 5-judge recalibration backfired |
| C4 (new) | n/a | 36% fail / 35% warn | NEW signal — 71% difficulty mislabel rate |

Verifier costs ~$0.0017–$0.0024 per accepted Llama/Qwen question (well under the $11 plan budget for the full 10k run).

### Decisions & trade-offs
- **Stopped corpus build early** at 292 Qs because scenario_synthesis throughput crashed to ~5 Qs/hr (Team β's wine_category filter on cluster sampling was too strict). Prioritised getting an audit signal over completing the full 600.
- **Refactored Team B mid-run for inline writes** so the ~3-4h LLM pass was monitorable + resumable.
- **Renamed `docs/GENERATION_IMPROVEMENT_PLAN_AUTO.md`** so the curated plan stays canonical (orchestrator's `build-reports` writes the auto plan to the `_AUTO` suffix).

### Issues encountered & resolutions
1. C4 max_tokens too small for Gemini 3.1 Pro reasoning consumption — fixed by bumping 300 → 1500.
2. Team α mis-cwd to main repo — cleaned via `git restore`; no harm because canonical version was in worktree branch.
3. Slow scenario throughput from over-strict cluster filter — flagged for v2.2 walk-back (Plan §6 fix #6).
4. `.claude/` directory not gitignored — fixed; added to `.gitignore`.

### Human review notes
- Gold review #1 (60 Qs against pilot v1) revealed Llama/Qwen produce 30-40% wrong-key questions (only 60% / 71% answer_correct vs 100% for Claude/ChatGPT/Gemini/template). This was the audit's biggest blind spot and drove the verifier design.
- Gold review #2 pending: `data/reports/gold_sheet_v2.csv` exported (48 Qs, multi-fact column 11 — Plan §4 fix landed). Reviewer to grade offline; once imported the run #2 reports gain per-rubric κ for all 5 LLM-judge signals.

### Next steps (canonical)
See `docs/PATH_TO_10K.md` for the 5-phase v2.2 → 10k production plan: gold re-grade (parallel) → 6 v2.2 fixes via 3 worktree teams → audit run #3 → sign-off → full 10k run. Total ~3-4 days, ~$110.

---

## 2026-04-22 — Phase 2f: Gold-v3 sign-off + v2.3 plan

### What was done
Audit run #3 already-landed last session (`audit_pilot_v3`, 331 Qs, $8.51). Domain expert returned `data/reports/gold_sheet_v3_scored.csv` (59/60 rows scored). This session: imported the scored CSV, recomputed LLM-judge↔human κ across 119 combined gold rows (v1+v2+v3), computed per-generator and per-strategy pass-rate cross-tabs from the audit findings, diagnosed two user-flagged concerns (template pattern-monopoly, Gemini allocation), and drafted the v2.3 plan (`docs/PATH_TO_10K.md` Phase F, `docs/GENERATION_IMPROVEMENT_PLAN.md` §13–§14).

### Sources & inputs
- `data/reports/gold_sheet_v3_scored.csv` (user, pushed by 2026-04-22 commit a235848)
- `audit_runs` row id `0bfe85dc-4fdc-4500-b274-a4b05d982e20` (audit_pilot_v3)
- `audit_findings` table (1990 rows for run #3)
- `generation_metadata` + `questions` join (107 template questions currently in DB)
- `facts` table (for corrupt Bordeaux fact triage)

### Methodology
1. Re-encoded `gold_sheet_v3_scored.csv` from cp1252 (Excel export) → UTF-8 to allow `import_gold_sheet` to parse the en-dash characters in source-fact quotes.
2. Ran `python3 -m src.qa.orchestrator import-gold --csv-path … --reviewer nikita` (upserted 59 labels) then `build-reports --run-id 0bfe85dc-…` which refreshed `docs/QUALITY_AUDIT_REPORT.md` §6 Gold Calibration with κ for all 5 audited rubrics on n=119.
3. Computed per-generator and per-strategy pass rates by pivoting `audit_findings (run_id, agent_id, severity) × generation_metadata.generator` via ad-hoc SQL (same aggregation method as AUDIT_RUN_2_COMPARISON.md).
4. Diagnosed template diversity by querying `(gm.template_id, q.question_type, count(*))` — found 11 template_ids firing, top template T-PRD-TF-REGION-01 holding 28% of template questions.
5. Queried `facts` for known-broken patterns: `fact_text ILIKE '% classified Bordeaux estate in Château %' OR fact_text ILIKE '%align=%' OR fact_text ILIKE '%&nbsp;%'` → 43 corrupt facts; 14 template questions traced to them.

### Quality controls
- 59/60 gold rows scored (1 row left blank by reviewer, imported as missing label).
- Latin1 → UTF-8 re-encode verified by re-reading the file and checking line count unchanged.
- κ computation cross-checked against the auto-generated `docs/QUALITY_AUDIT_REPORT.md` §6 numbers — my standalone script matched the orchestrator output within rounding.

### Quantitative results

**Gold-v3 per-rubric pass rates (59 scored rows):**

| rubric | pass% |
|---|---:|
| answer_correct | 92% |
| distractors_plausible | 90% |
| not_ambiguous | 92% |
| source_faithful | 93% |
| needs_source | 93% |
| no_vague_language | 90% |
| difficulty_match | **69%** |
| cognitive_match | 92% |

Overall perfect 8/8: 66.1% (up from 45.8% in gold-v2).

**κ on 119 combined gold rows (v1+v2+v3) vs LLM-judge agents:**

| rubric | agent | κ |
|---|---|---:|
| answer_correct | B1_TriJudgeAnswer | 0.466 |
| source_faithful | A3_FactEcho | 0.304 |
| distractors_plausible | C2_CategoryLeak | 0.166 |
| no_vague_language | A1_LexicalHygiene | -0.113 |
| needs_source | B2_ClosedBookSolvability | -0.099 |

Only B1 approaches trustworthy; B2 is actively misleading (κ < 0).

**Per-generator audit pass rate (avg across 6 question-level agents, n=audit_pilot_v3):**

| gen | avg pass | A1 | A3 | B1 | B2 | C2 | C4 |
|---|---:|---:|---:|---:|---:|---:|---:|
| gemini | **70.5** | 93 | **81** | 93 | 23 | 96 | 37 |
| chatgpt | 66.7 | 95 | 55 | 97 | 11 | 100 | 42 |
| claude | 66.7 | 90 | 51 | 93 | 29 | 100 | 37 |
| llama | 64.4 | 98 | 38 | 92 | 25 | 97 | 35 |
| qwen | 63.3 | 79 | 60 | 89 | 20 | 96 | 37 |
| template_only | 63.1 | 100 | 14 | 71 | 43 | 100 | 50 |

**Template diversity audit:**

| metric | value |
|---|---|
| template questions in DB | 107 |
| distinct `template_id`s firing | 11 of 38 registered |
| top template share (T-PRD-TF-REGION-01) | 30 / 107 = 28% |
| top-3 template share | 56% |
| legacy templates (v2.2 §8a purge-from-code but not DB) | ~32 / 107 |
| templates with `cognitive_dim` > recall | 0 / 107 |
| templates with corrupt Bordeaux source fact | 14 / 107 |

### Decisions & trade-offs
- **Gemini allocation: 2400 → 2800.** Quantitative leader on pass rate and on A3; subjective user preference corroborates. Balanced from Qwen (-300, lowest A1) and Llama (-100, lowest A3). Gemini corpus share rises 24% → 28%, still under the 35% ceiling. Self-preference risk monitored via D1 after Phase F.
- **Why not go to 3000?** 30% would put Gemini uncomfortably close to the cap; it's also the B2 judge-panel member, so a 3rd of the corpus being author=Gemini makes evaluator-author decorrelation harder. 2800 is the conservative bump.
- **B2 gate retired.** κ=-0.10 means the signal is useless as a gate; kept as a warn-level ranked defect. Replaced with a human spot-check on `needs_source` during Phase E.
- **Template diversity cap at 15%.** 10% would starve common producer-region templates; 20% wouldn't have prevented the gold-v3 100% monopoly. 15% is the minimum that meaningfully breaks the current 28% concentration without harming throughput.
- **Template registry expansion over outright template-strategy elimination.** Dropping to 0% would push more through Llama/Qwen (each verifier-gated, each thin on A1/A3). Expanding to 50+ templates with comprehension+application tier lets templates earn their 10% share.

### Issues encountered & resolutions
1. **Gold CSV encoding.** Excel exports CSVs as cp1252 with en-dash bytes 0x96, 0x97; `import_gold_sheet` opens with `encoding="utf-8"` which raises `UnicodeDecodeError`. Fixed ad-hoc by re-encoding the file before import. Follow-up in a future PR: change `_corpus.import_gold_sheet` to open with `encoding="utf-8-sig", errors="surrogateescape"` or sniff the encoding.
2. **`wc -l` on gold CSV reports 254 rows** (newlines inside quoted multi-fact source cells). Actual row count via `csv.DictReader` is 60. Used the latter for all counts.
3. **Bordeaux scraper data contamination.** 43 "classified Bordeaux estate in Château X" facts originate from misreading the Saint-Émilion Grand Cru Classé Wikipedia table: the parser pairs each row's name with the NEXT row's name instead of the table's `region` column. Full fix in Phase F §14.3 Sampler team. Short-term: fact delete + question cascade delete during v2.3.

### Human review notes
- Gold-v3 notes column: 22 rows with free-text. 18 of those are difficulty corrections ("actual difficulty should be 3"), 3 are "completely incorrect" (all trace to corrupt Bordeaux facts on template strategy), 1 flags distractor-composition ("distractors should include different incorrect grape varieties").
- User flagged template pattern homogeneity and Gemini preference in the same session that produced this entry → addressed by §13 (Gemini) + §14 (template diversity) in the plan.

### Next steps (canonical)
See `docs/PATH_TO_10K.md` Phase F. Three parallel worktrees:
- **Template team:** fixes 13 (per-template cap), 14a/b (legacy purge + Bordeaux fact scrub), 15 (registry expansion with comprehension+application tier).
- **Sampler team:** fix 14c/d (Bordeaux scraper table-parser fix + rescrape), fix 17 (D3 cap enforcement — the 1.2× cap from v2.2 isn't being enforced; investigate where).
- **Audit team:** fix 16 (C4 difficulty calibration refresh from gold-v3's 18 directional fails).

Then audit_pilot_v4 + gold_sheet_v4 → sign-off → Phase E 10k run.

---

## 2026-04-23 — Phase 2g: B2 leakage + judge recalibration (v2.3 §5b + §5c execution)

### What was done
Shipped the two still-pending v2.3 defects against audit run #3's blockers: (a) B2 ClosedBookSolvability 66% fail rate on `audit_pilot_v3` and (b) LLM-judge κ < 0.6 on every gold-v3 rubric. Three parallel agent worktrees (Team α / β / γ per `docs/IMPLEMENTATION_AGENT_ARCHITECTURE.md`) with disjoint file ownership, merged to `main` with one coordinator fixup for a dormant `strategy=` parameter. All 269 tests pass on merged main.

### Sources & inputs
- `audit_findings` rows for run `0bfe85dc-4fdc-4500-b274-a4b05d982e20` (B2 fail sample for iconic-list harvest)
- `data/reports/gold_sheet_v3_scored.csv` (vague-phrase harvest for A1 regex extension)
- `docs/GOLD_CALIBRATION_ANALYSIS.md` (κ rationale for B2 threshold change)
- `docs/GENERATION_IMPROVEMENT_PLAN.md` §5b / §5c / §14 (the executed plan)

### Methodology
**Team α — Generation-side B2 fix.** Expanded `data/iconic_entities.yaml` from 60 → 188 entries across 9 categories (classified growths all 5 tiers, Burgundy Grand Crus, iconic producers Bordeaux right-bank + Spain/Portugal, famous generic appellations). Added `_bundle_has_non_iconic_anchor` helper in `_fact_sampler.py` and integrated into `sample_fact_pairs`, `sample_fact_groups`, `sample_fact_clusters`, `sample_confusable_facts` so multi-fact strategies reject iconic-only bundles. Extended `_VAGUE_PATTERNS` with 11 phrasings (e.g. `world[- ]class`, `highly prized`, `distinguished by its`). Added `AVOID WORLD-KNOWLEDGE SOLVABILITY` hard-rule block + numbered `INFERENCE OVER RECALL (HARD RULES)` to all 10 strategy templates in `_prompts.py` (FTQ, COMP + 3 variants, SCEN, DIST + 3 variants). Max prompt length growth ~20%.

**Team β — B2 threshold recalibration (v3.1.0).** Replaced the v3.0.0 majority-of-5 rule with: L≤2 FAIL iff 5/5 keyed AND `cb_confidence_mean ≥ 0.80`; WARN at ≥4/5; L≥3 WARN only (never FAIL on closed-book alone). Added `cb_confidence_mean` payload field. Bumped `B2_VERSION` to `v3.1.0`. Renamed misnamed test file `test_team_d_recalibration.py` → `test_team_b_recalibration.py` via `git mv` + updated 6 legacy cases to v3.1 semantics + added 5 new v3.1 cases.

**Team γ — Audit rubric reframing.** Extended A1 vague regex with 7 audit-side patterns (e.g. `celebrated for`, `notable for`, `sought-after`). Renamed A3 and C2 rubric narratives (no logic change): A3 payload `rubric_measured="verbatim_copy"` (v1.1.0); C2 payload `rubric_measured="wine_category_leak"` (v1.1.0). Remapped `GOLD_RUBRIC_TO_PROXY` in `build_audit_report.py` with a `_HUMAN_ONLY_AGENT` sentinel so `source_faithful` (semantic) is rendered human-only while the new `verbatim_copy` rubric proxies to A3. Extended `GOLD_RUBRICS` in `_corpus.py` additively — old gold sheets still import cleanly.

**Coordinator fixup.** Team α flagged that no caller of `sample_facts(strategy=…)` was passing the argument, leaving the v2.2 single-fact iconic filter dormant. Wired `strategy="fact_to_question"` / `"template"` / `"distractor_mining"` at four call sites (`fact_to_question.py:240,364`, `template_generator.py:2135`, `distractor_miner.py:80`).

### Quality controls
- Smoke assertions: `_load_iconic_entities()` returns 188; `Napa Valley`-only fact = iconic-only; `Chateau Leoville-Las-Cases + Cabernet` fact = NOT iconic-only (has non-iconic entity).
- All 4 strategy templates contain `AVOID WORLD-KNOWLEDGE` block; all 3 version bumps (`B2=v3.1.0`, `A3=v1.1.0`, `C2=v1.1.0`) observable from module imports.
- `GOLD_RUBRICS` registry contains both new additive entries.
- `pytest tests/` — **269/269 pass** (32 s).

### Quantitative results
| Deliverable | Before | After |
|---|---|---|
| Iconic entities | 60 | 188 |
| Vague regex patterns | baseline | +11 generator-side, +7 audit-side |
| Hardened strategy templates | 0 | 10 of 10 |
| B2 FAIL rule (L≤2) | ≥4/5 keyed | 5/5 keyed AND conf ≥ 0.80 |
| B2 FAIL rule (L≥3) | 5/5 keyed | never (WARN only) |
| Gold rubrics in registry | 8 | 10 |

### Decisions & trade-offs
- **B2 at L≥3: never FAIL.** At hard difficulty, closed-book leakage signal is dominated by judge priors (well-read LLMs) rather than test-taker solvability. Demoting to WARN-only preserves observability without gating.
- **A3 payload rename, not new agent.** Adding a new agent for semantic faithfulness would require a new LLM-judge call per question (~$0.005 × 10k ≈ $50). Renaming is free; new semantic agent deferred to post-Phase-F if κ gains don't materialize.
- **Sentinel `_HUMAN_ONLY_AGENT` row for `source_faithful`.** Keeps the rubric visible in the report with `—` for LLM columns, reminding readers that semantic faithfulness is a human-only signal until a new agent lands.
- **4 call sites for `strategy=`.** Could have defaulted the param inside `sample_facts` based on caller module introspection, but explicit is better than magic — the four 1-line edits are self-documenting.

### Issues encountered & resolutions
1. **Team β's B2 test file misnamed.** `tests/qa/test_team_d_recalibration.py` was actually a Team-B file (its docstring described δ-2's B2 deliverable). Resolved via `git mv` to `test_team_b_recalibration.py`.
2. **`sample_facts(strategy=…)` dormant.** Team α could not fix from its worktree because the four call sites live in files owned by other teams. Coordinator merged first, then wired the parameter in a single fixup commit.
3. **Plan mode inheritance.** Team β initially interpreted the coordinator's plan-mode context as inherited and wrote a plan file instead of executing. Resolved via SendMessage authorization.

### Human review notes
User approved the plan at `/home/winebench/.claude/plans/linear-scribbling-scott.md` and requested auto-mode + parallel Agent Teams. No wine-domain facts changed in this phase.

### Next steps
1. **Audit run #4.** `python -m src.qa.orchestrator build-corpus --tag audit_pilot_v4 --per-strategy 120 && run --teams A,B,C,D`. Expected: B2 fail rate drops from 66% to ~10–15%; D3 stays <1.5; new A3 `verbatim_copy` and C2 `wine_category_leak` columns populate in the report.
2. **Gold-v4 export** (60 Qs, 12/strategy) → human grading → import → recompute κ on every rubric including the two new ones.
3. **Go/No-Go verification** per `docs/GENERATION_IMPROVEMENT_PLAN.md` Regeneration Checklist.
4. **Unblock full 10k run** if gates clear.

---

## 2026-04-24 — Phase 2g.5: Generation-time closed-book gate (v1.0)

### What was done
Audit run #4 (`audit_pilot_v4`, 341 Qs, $6.18) showed B2 dropped 66% → 36% but missed the ≤15% gate. Diagnosis + four prototypes confirmed that v2.3 §5b prompt rules can't close the gap because the residual leakage is structural: generators write attribute-bundle stems whose answer is recoverable from the cues alone. Built and shipped a v1.0 generation-time pre-screen (`src/generators/_closed_book_gate.py`) — Sonnet 4.6 closed-book MC at conf≥0.7 — wired into all 5 strategy modules via a new `insert_question_gated()` wrapper. 13 new unit tests + 269 baseline = 282/282 pass.

### Sources & inputs
- `audit_findings` rows for run `4e3ead78-2b62-4733-919d-bf3f4878aaec` (`audit_pilot_v4`)
- 343 facts behind L1/L2 v4 questions (joined via `question_facts`)
- 230 L1/L2 v4 question stems (with options)
- OpenRouter API: `anthropic/claude-haiku-4.5`, `anthropic/claude-sonnet-4.6`

### Methodology

**Prototype 1 — fact-level Haiku pre-screen** (`scripts/prescreen_b2_prototype.py`).
For each L1/L2 fact, asked Haiku 4.5 whether a question derived from it would be world-knowledge-solvable. Discovery: Haiku 4.5 wraps JSON in markdown fences even with `response_format=json_object`; reused `_try_parse_json` to strip them. Result: 79 of 343 facts flagged solvable; gate gave 19-pt fail-rate gap (68% vs 49%) — insufficient.

**Prototype 2 — stem-level Haiku pre-screen** (`scripts/prescreen_b2_question_prototype.py`).
Asked Haiku closed-book on the question stem (no options, no fact). At conf≥0.7: 88% precision, 40% recall. Free-text matching on gold answer via `difflib.SequenceMatcher` ratio≥0.75. Sample of false negatives showed Haiku is too weak — gets close-but-wrong on entities Opus/GPT in B2's panel solve cleanly.

**Prototype 3 — Sonnet 4.6 stem-level pre-screen** (`scripts/prescreen_b2_sonnet_prototype.py`).
Replaced Haiku with Sonnet 4.6. Marginal improvement: 49% recall vs Haiku's 40%, similar precision. Sample of false negatives revealed the real issue: many stubborn cases are MC-disambiguation problems — Sonnet can't reproduce the gold in free-text but COULD pick it from the options.

**Prototype 4 — MC closed-book pre-screen** (`scripts/prescreen_b2_mc_prototype.py`).
Re-ran both Haiku and Sonnet WITH the option list, picking A/B/C/D. Result: Sonnet @ conf≥0.7 hit **94% recall, 77% precision**, dropping residual L1/L2 fail rate from 54% to **10%** — clears the ≤15% gate target. Haiku∪Sonnet union pushed residual to 5%. Established Sonnet-alone @ conf≥0.7 as the v1.0 threshold.

**Implementation.**
- `src/generators/_closed_book_gate.py` — `screen_question(stem, options, gold, difficulty, question_type) -> GateResult`. Only fires for `multiple_choice` + `difficulty in {1,2}`; everything else passes through. On API/parse error: fail-open (PASS) with `error` recorded. Tenacity-backed retries on rate-limit / 5xx.
- `src/generators/_question_db.py` — `insert_question_gated()` wraps `insert_question`, runs the gate, appends verdict to `generation_meta['raw_response']['gate']`, returns `(uuid_or_none, GateResult)`.
- All 5 strategy modules (`fact_to_question.py`, `comparative_generator.py`, `scenario_generator.py`, `distractor_miner.py`, `template_generator.py`) — switched to `insert_question_gated`, count and log `skipped_gate`.
- `tests/generators/test_closed_book_gate.py` — 13 tests covering: skip conditions (L3+, non-MC, no options), reject paths (correct + high conf), pass paths (wrong answer, low conf), fail-open semantics (API error, parse failure), and wrapper behavior (DB skip on reject, gate-verdict in metadata, L3 passthrough, `apply_gate=False`).

### Quality controls
- 282/282 pytest pass (269 baseline + 13 new).
- Smoke test: `python -m src.generators.fact_to_question --domain wine_regions --count 15 --difficulty 2 --generator chatgpt`. Result: 15 inserted, 30 gate-rejected (67% reject — matches Prototype 4's predicted 65%), 58 chatgpt parse failures (unrelated to gate). Gate verdicts visible in `generation_metadata.raw_response->'gate'` for all 15 accepted questions; all show either `matched_gold=false` OR `confidence<0.7`.

### Quantitative results
| Variant | Precision | Recall | Residual L1/L2 B2 fail % |
|---|---:|---:|---:|
| Fact-level Haiku | 68% | 44% | 49% |
| Stem-level Haiku conf≥0.7 (free-text) | 88% | 40% | 43% |
| Stem-level Sonnet conf≥0.7 (free-text) | 82% | 49% | 40% |
| **MC Sonnet conf≥0.7 (shipped v1.0)** | **77%** | **94%** | **10%** |
| MC Haiku∪Sonnet conf≥0.7 | 72% | 98% | 5% |

| Phase | Cost (343 facts / 230 Qs) | Throughput |
|---|---|---|
| Prototype 1 (Haiku, 343 facts) | $0.33 | 92 s |
| Prototype 2 (Haiku stems, 230 Qs) | $0.16 | 63 s |
| Prototype 3 (Sonnet stems, 230 Qs) | $0.55 | 196 s |
| Prototype 4 (Haiku+Sonnet MC, 230 Qs) | $0.61 | 172 s |
| Smoke test (ChatGPT gen + Sonnet gate, 15 inserts) | gate-only ~$0.01 | 7.4 min |

### Decisions & trade-offs
- **Sonnet alone, not Haiku∪Sonnet union.** Union improves residual 10% → 5% but doubles model count and adds Haiku's 88% precision (vs Sonnet's 77%) — noisier. Phase 2g.5 ships Sonnet-only; the union upgrade is reserved for a later iteration if v5 audit shows residual >15%.
- **Threshold conf≥0.7, not conf≥0.5.** conf≥0.5 hits 98% recall but cuts an extra 12% of L1/L2 candidates with no measurable gain on residual (already at the gate target). Conservative choice keeps generator throughput higher.
- **Fail-open on API error, not fail-closed.** A network blip during a 10k run shouldn't silently drop hundreds of questions. The error lands in `GateResult.error` so post-hoc analysis can quantify how often the gate degraded.
- **Verdict in `raw_response['gate']`, not a new column or table.** Schema-migration-free; keeps the audit trail self-contained per question; `jsonb` indexing already in place if we need to query gate stats.
- **Gate not applied to non-MC types.** Free-text MC scoring would require either a gold-string normaliser or an LLM-as-judge layer. Out of scope for v1.0; non-MC types are <10% of the corpus.
- **No regenerate-on-reject.** The orchestrator just over-samples the L1/L2 facts pool. 67%-observed reject rate at L2 implies ~3× over-sampling needed; this is configured per-strategy at run time, not in the gate module.

### Issues encountered & resolutions
1. **Haiku 4.5 markdown-wrapped JSON.** First prototype run: 0/343 parsed. Probe call confirmed Haiku returns ` ```json\n{...}\n``` ` even with `response_format=json_object`. Fix: imported `_try_parse_json` from `_llm_client.py` (already handles fences). Same fix applies to Sonnet 4.6.
2. **Free-text gold matching too brittle.** Many "stubborn" B2 fails in Prototype 3 were Sonnet producing semantically-correct but lexically-different answers (e.g. "Charmat method" vs "Ferment in pressurized tanks"). Resolved by Prototype 4's MC-with-options framing — letter match is unambiguous.
3. **`questions.tag` does not exist.** First DB query used singular `tag`; PostgreSQL hint pointed to `tags` (text[]). Switched to `tags && ARRAY['audit_pilot_v4']`.
4. **`audit_findings` schema mismatch.** Used `rubric_id`/`status` initially; actual columns are `agent_id`/`severity`. Fixed via `\d audit_findings`.

### Human review notes
User chose option (A) "prototype the Sonnet-4.6 second stage" then (B) "start implementing the compound fix" after seeing the MC-pre-screen result. No wine-domain facts changed in this phase.

### Next steps
1. **Audit run #5 with gated corpus.** Build `audit_pilot_v5` (120/strategy) with the gate in force, then `run --teams A,B,C,D`. Target: B2 fail at L1/L2 ≤ 15%, residual structural fixes via prompt edits if gap remains.
2. **Tune over-sampling.** Bump `_dispatch_llm_strategy` per-generator counts by 3× for L1/L2 to compensate for the gate's 65% reject rate.
3. **Gold-v5 export** if v5 audit clears.
4. **Cost budget check.** Sonnet gate adds ~$20 per 10k generation + ~3× over-sampling adds ~$30 LLM-gen cost. Total run estimate revises upward from $80 → ~$130.

---

## 2026-04-24 — Phase 2g.6: Reframe gate from reject to label+quota (v2.0)

### What was done
Reframed the closed-book gate from a reject filter (v1.0, shipped earlier today) into a label+quota router (v2.0). Gate-flagged L1/L2 multiple-choice questions are no longer dropped: they are tagged `closed_book_solvable`, forced to `difficulty='1'`, and admitted to the corpus until a 25% cap is reached. Above the cap, additional gate-flagged questions are dropped. New eval helper `src/evaluation/cb_split.py` exposes `score_by_cb_split()` for paired closed-book-pass vs closed-book-fail accuracy. GATE_VERSION bumped to 2.0.0; 286+/286+ tests pass.

### Sources & inputs
The user proposed the reframe directly after reviewing the Phase 2g.5 v1.0 ship in this same lab notebook (entry above). No external data; the policy change is paper-story driven. The v1.0 implementation in `src/generators/_closed_book_gate.py` and `_question_db.py` is the substrate.

### Methodology
Routing table inside `insert_question_gated()` (`src/generators/_question_db.py`):
- `gate.passed=True` → INSERT as-is (the closed-book pre-screen could not solve it).
- `gate.passed=False AND quota has room` → mutate `question_data` (append `closed_book_solvable` to `tags`, force `difficulty='1'`), set `gate.relabeled=True`, INSERT.
- `gate.passed=False AND quota full` → set `gate.quota_full=True`, DROP. Returns `(None, gate)`.
- `gate.applied=False` (wrong difficulty, non-MC, or no options) → INSERT as-is.

Quota enforcement uses `count_closed_book_solvable()` per-insert against `CLOSED_BOOK_QUOTA_FRACTION = 0.25` of the orchestrator's `OVERALL_TARGET` (= 2,500 of the 10k corpus). `CLOSED_BOOK_TAG = "closed_book_solvable"` is the canonical tag string. The GIN index already on `questions.tags` keeps the per-insert COUNT cheap.

New module `src/evaluation/cb_split.py` defines `score_by_cb_split(eval_run_id) -> dict`, joining `evaluation_answers` to `questions` and aggregating accuracy by tag membership. Returns paired `cb_pass` (no tag — contextual reasoning) and `cb_fail` (tagged — parametric knowledge) buckets plus `gap = cb_fail.accuracy - cb_pass.accuracy`. CLI entrypoint pretty-prints the result.

Multi-agent dispatch followed the parallel-worktree pattern in `docs/IMPLEMENTATION_AGENT_ARCHITECTURE.md`: 3 teams under one coordinator (Team α: gate routing + tests; Team β: orchestrator + quota CLI; Team γ: eval split helper + docs).

### Quality controls
Tests added cover the v2.0 routing surface: relabel-when-room (tag append + L1 force), reject-when-quota-full (drop + `quota_full=True`), no-double-tag (idempotent on already-tagged input), and preserve-other-tags (existing tag list untouched). 285+/285+ pytest pass after the merge. Coordinator will run a generation smoke test post-merge to confirm relabel+quota behavior on real OpenRouter calls.

### Quantitative results

| Axis | v1.0 (reject) | v2.0 (label + quota) |
|---|---|---|
| L1/L2 gate-flagged kept | 0% (rejected) | 100% up to 25% cap, then 0% |
| `closed_book_solvable` corpus share | 0% | ≤25% (≤2,500 of 10k) |
| Estimated 10k-run cost | ~$130 (gate + 3× over-sample) | ~$100 (gate, no over-sample) |
| Eval-time deliverable | accuracy only | paired `cb_pass` vs `cb_fail` accuracy + gap |

### Decisions & trade-offs
- **Relabel + quota, not reject.** Gate-flagged questions are by definition wine-world-knowledge questions — a legitimate axis for the benchmark. Keeping them as a labeled subset preserves throughput economics (no 3× over-sampling) and gives the paper a paired metric (parametric wine knowledge vs contextual wine reasoning).
- **Cap at 25%.** Keeps the world-knowledge subset visible to evaluation without letting it dominate. Aligned with typical fact-recall benchmark weightings; revisitable post-v5 audit.
- **Force to L1, not preserve original difficulty.** A gate-solved question is, by definition, closed-book-solvable, which is the L1 difficulty contract. Preserving an L2 stamp on a closed-book-trivial item would mislead the difficulty histogram.
- **First-come-first-served quota fill.** Stratification (e.g., balance the cap across domains/strategies) is deferred to post-v5 audit data analysis where we can see actual flag rates per stratum.
- **v5 onward only, no retro re-labeling of v4.** Clean policy boundary. v4 stays under v1.0 reject semantics so v4-vs-v5 audit deltas remain attributable to the policy switch, not retroactive relabeling.
- **Quota check via SQL `count(*)` per insert.** Cheap thanks to the existing GIN index on `questions.tags`. A Redis counter would shave milliseconds but adds operational surface area; not worth it for the 10k-question regime.

### Issues encountered & resolutions
1. **Existing test invalidated.** `test_insert_question_gated_skips_db_when_rejected` encoded the v1.0 reject semantics and broke under v2.0. Team α rewrote it to assert the new relabel-when-room path. No other test breakage.

### Human review notes
The user drove the policy reframe interactively after reviewing Phase 2g.5. Earlier in the day they had chosen options A and B (prototype Sonnet-4.6 second stage; implement compound fix), which yielded the v1.0 ship. After v1.0 they proposed the v2.0 reframe directly. Coordinator surfaced two design questions — quota-overflow behavior and retroactive v4 application — and the user took the recommended defaults (drop when quota full; v5 onward only).

### Next steps
1. Build `audit_pilot_v5` corpus with the v2.0 gate active.
2. Run audit #5; expect `closed_book_solvable` to populate up to ~25% cap; expect L2 fail rate <15% on the un-tagged subset.
3. Stand up the basic eval-run executor so `score_by_cb_split()` can be exercised on real data.
4. Update D1 self-preference and D3 skew agents to optionally split by the `closed_book_solvable` tag.
