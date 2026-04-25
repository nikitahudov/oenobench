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
6. **Decisions & trade-offs** — what alternatives were considered, why this approach was chosen, what was sacrificed (e.g., "Site X was unreachable, fell back to Wikipedia-only", "switched from transitive to direct SPARQL property to fix off-topic contamination")
7. **Issues encountered & resolutions** — failures, bugs, unexpected results, and how each was resolved
8. **Human review notes** — any decisions made by the domain expert (sample reviews, quality judgments, coverage priorities)

**Format guidelines:**
- Each entry is a dated section with a phase label (e.g., `## 2026-04-11 — Phase 0: Shared Infrastructure`)
- Keep it factual and quantitative — lab notebook style, not prose
- Include before/after counts where relevant
- Group by project phase when multiple things happen on one day

**What the NeurIPS paper will need from this log (by section):**

| Paper Section | Key details from log |
|---------------|---------------------|
| Data Collection | Source inventory (types, URLs, tiers), collection methods per source, fact processing pipeline (decompose → resolve → classify → validate), provenance guarantees |
| Quality Assurance | Automated validation rules, acceptance/rejection rates, human expert review process, the provenance audit story (discovery + rebuild of integrity issues) |
| Question Generation | Which LLMs generated questions (Claude/GPT-4/Gemini/Llama/templates), prompt design, generation methodology, self-preference controls |
| Validation | AI validation pipeline, inter-annotator agreement, human review targeting strategy |
| Evaluation | Models tested, held-out subset methodology, scoring, Self-Preference Score analysis |
| Statistics | Total facts/questions, domain distributions, source type distributions, geographic coverage, known limitations |

**At the end of each major phase,** compile the relevant log entries into a structured summary in `docs/` (e.g., `DATA_COLLECTION_SUMMARY.md`, `QUESTION_GENERATION_SUMMARY.md`). These summaries should be paper-ready: concise, quantitative, with tables and statistics that can be directly cited or adapted into paper prose.

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
├── docs/
│   ├── PROCESS_LOG.md            # Chronological lab notebook (all phases)
│   ├── ARCHITECTURE.md           # Architecture documentation
│   ├── DATA_COLLECTION_SUMMARY.md # Paper-ready summary (after data collection)
│   └── figures/                  # Diagrams and figures
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
│   │   ├── _fact_processing.py   # Shared: decompose, resolve refs, classify domain, validate
│   │   ├── _web_helpers.py       # Shared: HTTP session, page discovery, text extraction
│   │   ├── _wiki_helpers.py      # Shared: extract_atomic_facts, run_sparql_filtered, SPARQL templates
│   │   ├── wikidata.py           # ✅ Genuine — Wikidata SPARQL (2,145 facts)
│   │   ├── wikipedia.py          # ✅ Genuine — Wikipedia MediaWiki API (323 facts)
│   │   ├── huggingface.py        # ✅ Genuine — HuggingFace datasets (3,231 facts)
│   │   ├── ucdavis.py            # ✅ Genuine — UC Davis ontology, AVA, FPS (2,199 facts)
│   │   ├── kaggle_data.py        # ✅ Genuine — Kaggle wine-quality & wine-reviews (1,509 facts)
│   │   ├── inao.py               # ✅ Genuine — INAO French appellations (1,473 facts)
│   │   ├── academic.py           # ✅ Genuine — OENO One, Vitis, AJEV (925 facts)
│   │   ├── ucipm.py              # ✅ Genuine — UC IPM pages (1,145 facts)
│   │   ├── extension.py          # ✅ Genuine — USDA, Penn State, Oregon State (705 facts)
│   │   ├── oiv_docs.py           # ✅ Genuine — OIV PDF downloads (63 facts)
│   │   ├── bordeaux.py           # ✅ Rebuilt — Wikipedia + SPARQL + bordeaux.com (484 facts)
│   │   ├── burgundy.py           # ✅ Rebuilt — Wikipedia + SPARQL + bourgogne-wines.com (483 facts)
│   │   ├── champagne.py          # ✅ Rebuilt — Wikipedia + SPARQL + champagne.fr (466 facts)
│   │   ├── italian_wine_central.py  # ✅ Rebuilt — Wikipedia + SPARQL (788 facts)
│   │   ├── austria.py            # ✅ Rebuilt — Wikipedia + SPARQL (146 facts)
│   │   ├── greece.py             # ✅ Rebuilt — Wikipedia + SPARQL (255 facts)
│   │   ├── consortiums_italy.py  # ✅ Rebuilt — Consortium websites (85 facts)
│   │   ├── ttb.py                # ✅ Rebuilt — TTB.gov + eCFR (513 facts)
│   │   ├── italy.py              # ✅ Rebuilt — Wikipedia + SPARQL
│   │   ├── europe.py             # ✅ Rebuilt — Wikipedia + SPARQL
│   │   ├── newworld.py           # ✅ Rebuilt — Wikipedia + SPARQL
│   │   ├── eu_oiv.py             # ✅ Rebuilt — Wikipedia + SPARQL
│   │   ├── rhone_loire_alsace.py # ✅ Rebuilt — Wikipedia + SPARQL
│   │   ├── spain_enrichment.py   # ✅ Rebuilt — Wikipedia + SPARQL
│   │   ├── portugal_enrichment.py # ✅ Rebuilt — Wikipedia + SPARQL
│   │   ├── south_america.py      # ✅ Rebuilt — Wikipedia + SPARQL
│   │   ├── australia_nz_enrichment.py # ✅ Rebuilt — Wikipedia + SPARQL
│   │   ├── hungary_georgia.py    # ✅ Rebuilt — Wikipedia + SPARQL
│   │   ├── germany_enrichment.py # ✅ Rebuilt — Wikipedia + SPARQL
│   │   ├── canada.py             # ✅ Rebuilt — Wikipedia + SPARQL
│   │   ├── croatia_slovenia.py   # ✅ Rebuilt — Wikipedia + SPARQL
│   │   ├── england.py            # ✅ Rebuilt — Wikipedia + SPARQL
│   │   ├── lebanon_israel.py     # ✅ Rebuilt — Wikipedia + SPARQL
│   │   ├── south_africa_enrichment.py # ✅ Rebuilt — Wikipedia + SPARQL
│   │   └── usa_enrichment.py     # ✅ Rebuilt — 22 Wikipedia articles + SPARQL
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
│   ├── generators/               # Phase 2 — question generation (5 strategies + orchestrator)
│   │   ├── _closed_book_gate.py, _dedup.py, _fact_sampler.py, _id_generator.py,
│   │   ├── _llm_client.py, _prompts.py, _question_db.py, _schemas.py,
│   │   ├── template_generator.py, fact_to_question.py,
│   │   ├── comparative_generator.py, scenario_generator.py,
│   │   ├── distractor_miner.py, orchestrator.py
│   ├── qa/                       # Phase 2c — multi-agent quality audit
│   │   ├── __init__.py
│   │   ├── orchestrator.py       # CLI: build-corpus, run-team-{a,b,c,d}, run, build-reports
│   │   ├── _corpus.py            # Stratified 600-Q pilot builder + gold-sheet import/export
│   │   ├── _findings.py          # audit_runs + audit_findings DAO with idempotency
│   │   ├── _judges.py            # Tri-judge panel (Claude Opus 4.7, ChatGPT 5.4, Gemini 3.1 Pro)
│   │   ├── _prompts.py           # B1/B2/D1 judge prompts
│   │   ├── _scoring.py           # χ², Mann–Whitney U, LCS, Cohen's κ, tiny logreg, POS features
│   │   ├── agents/
│   │   │   ├── team_a_static.py      # A1 LexicalHygiene, A2 BiasStats, A3 FactEcho, A4 TemplateFingerprint
│   │   │   ├── team_b_validity.py    # B1 TriJudgeAnswer, B2 ClosedBookSolvability
│   │   │   ├── team_c_probes.py      # C2 CategoryLeak (C1/C3/C4 deferred)
│   │   │   └── team_d_population.py  # D1 SelfPreference, D3 SkewAudit (stats slice)
│   │   └── reports/
│   │       ├── build_audit_report.py    # Renders docs/QUALITY_AUDIT_REPORT.md
│   │       └── build_improvement_plan.py # Renders docs/GENERATION_IMPROVEMENT_PLAN.md
│   ├── processors/
│   │   └── __init__.py           # Placeholder — future data processing
│   └── validators/
│       └── __init__.py           # Placeholder — future validation pipeline
├── tests/
│   ├── __init__.py
│   └── qa/                       # pytest fixtures + tests for src/qa/
│       ├── fixtures/sample_questions.py
│       ├── test_scoring.py, test_team_a.py, test_team_c.py, test_findings.py
└── data/                         # Not in git (see .gitignore)
    ├── raw/                      # Downloaded datasets
    ├── processed/                # Processed outputs
    ├── logs/                     # Scraper run logs
    ├── reports/                  # Verification reports
    ├── backups/                  # Database backups
    └── exports/                  # Data exports
```

### Files Not Yet Created (Planned)

| File | Scraper | Target |
|------|---------|--------|
| `src/scrapers/verify.py` | Post-scraping gap analysis | N/A |

All other planned scrapers have been implemented and rebuilt with genuine data provenance.

## Current Status (as of April 25, 2026)

**Phase:** 2g.7 — audit #5 + four-team retune shipped on engineering side. v6 build is **blocked on OpenRouter API key cap exhaustion**. Awaiting (a) user top-up of OpenRouter key, (b) gold review of `data/reports/gold_sheet_v5.csv`, and (c) Team γ A4 reference set ship before audit #6.

- Phase 1 (Data Collection): ✅ 38,104 facts from 35 genuine scrapers
- Phase 2 (Question Generation Pipeline): ✅ 5 strategies built and iteratively tuned
- Phase 2c (Quality Audit Framework): ✅ 9 agents across 4 teams under `src/qa/`
- Phase 2d–2f (Audit runs #1–#3 + gold-v1–v3 sign-off): ✅
- Phase 2g (v2.3 §5b/§5c fixes): ✅ Three parallel worktree teams merged
- Phase 2g (audit #4 on `audit_pilot_v4`): ✅ B2 dropped 66% → 36% — improved but missed ≤15% gate
- Phase 2g.5 (closed-book MC gate v1.0): ✅ Sonnet 4.6 wired into all 5 generators; 282/282 tests pass; smoke test 65% reject rate matches prototype prediction
- Phase 2g.6 (gate v2.0 — label+quota): ✅ Routes gate-flagged L1/L2 to `closed_book_solvable` tag at L1, capped at 25% of corpus; new `score_by_cb_split()` eval helper; 285+/285+ tests pass
- Phase 2g (audit #5 on `audit_pilot_v5`): ✅ B2 non-cb-tagged L1/L2 dropped 53.9% → **33.7%** (still above ≤15% gate); A4 AUC 0.954 trips 0.9 escalation; κ n=0 for new v2.3 rubrics (gold predates Phase 2g)
- Phase 2g.7 (four-team retune): ✅ Gate threshold 0.7→0.6 + L1/L2/L3 + multiple_choice+scenario_based; quota math fixed to per-corpus; scenario HARD RULE; `per_country_cap` sampler kwarg; gold sheet v5 ready for review (Team δ); 289/289 tests pass; Team γ (A4 external reference set via WSET/CMS scrape) running in background

### Phase 2g shipped (2026-04-23)

| Area | Change | Artifact |
|---|---|---|
| Generation iconic filter | `data/iconic_entities.yaml` 60 → 188 entries, 4 new categories | Team α merge |
| Multi-fact bundle filter | `_bundle_has_non_iconic_anchor` integrated into `sample_fact_pairs/groups/clusters/confusable_facts` | Team α merge |
| Vague regex | +11 generator-side patterns, +7 audit-side patterns | Teams α + γ |
| Strategy prompts | `AVOID WORLD-KNOWLEDGE SOLVABILITY` + `HARD RULES` across 10 templates | Team α merge |
| B2 threshold | v3.0 (majority ≥4/5) → **v3.1.0** (L≤2 FAIL iff 5/5 + conf≥0.80; L≥3 WARN-only) | Team β merge |
| A3 rubric narrative | `source_faithful` → `verbatim_copy` (v1.1.0, logic unchanged) | Team γ merge |
| C2 rubric narrative | `CategoryLeak` → `wine_category_leak` (v1.1.0, logic unchanged) | Team γ merge |
| Gold report remap | `_HUMAN_ONLY_AGENT` sentinel for semantic `source_faithful`; `GOLD_RUBRICS` extended additively | Team γ merge |
| Sampler strategy wiring | Four `sample_facts()` call sites now pass `strategy=…` (was dormant since v2.2) | Coordinator fixup |

### Phase 2g.5 shipped (2026-04-24)

| Area | Change | Artifact |
|---|---|---|
| Closed-book gate v1.0 | New module `src/generators/_closed_book_gate.py` — Sonnet 4.6 MC closed-book at conf≥0.7. Only fires for L1/L2 multiple-choice. Fails open on API/parse error. | gate-only smoke test 30 rejects / 15 accepts |
| Insert wrapper | New `_question_db.insert_question_gated()` — runs gate, appends verdict to `generation_meta['raw_response']['gate']`, returns `(uuid_or_none, GateResult)` | schema-migration-free |
| Generator switchover | All 5 strategy modules switched to `insert_question_gated`; each tracks `skipped_gate` count | fact_to_question, comparative, scenario, distractor_miner, template_generator |
| Tests | 13 new in `tests/generators/test_closed_book_gate.py` | 282/282 total pytest pass |

Prototype evidence (audit_pilot_v4 corpus, 230 L1/L2 questions): MC Sonnet @ conf≥0.7 → 94% recall, 77% precision, residual L1/L2 fail rate 54% → **10%**. See `docs/PROCESS_LOG.md` 2026-04-24 for full prototype methodology.

### Phase 2g.6 shipped (2026-04-24)

| Area | Change | Artifact |
|---|---|---|
| Gate routing change | v1.0 reject → v2.0 label+quota: gate-flagged L1/L2 questions are tagged `closed_book_solvable`, forced to `difficulty='1'`, kept in corpus until 25% cap | `src/generators/_closed_book_gate.py` (GATE_VERSION 2.0.0; `relabeled` + `quota_full` on `GateResult`) |
| Quota constant + status command | `CLOSED_BOOK_QUOTA_FRACTION = 0.25`, `CLOSED_BOOK_TAG = "closed_book_solvable"`, new `count_closed_book_solvable()` helper; `insert_question_gated()` rewritten as routing wrapper | `src/generators/_question_db.py` |
| Eval split helper | New `score_by_cb_split(eval_run_id)` returns paired cb_pass vs cb_fail accuracy + gap, exposing parametric wine knowledge vs contextual wine reasoning | `src/evaluation/cb_split.py` |
| Tests | Routing tests (relabel-when-room, reject-when-quota-full, no-double-tag, preserve-other-tags); 1 v1.0 reject test rewritten | 285+/285+ pytest pass |

### Phase 2g.7 shipped (2026-04-25)

Audit #5 ran on `audit_pilot_v5` (run_id `541d1d1d…`); B2 non-cb-tagged L1/L2 fail rate dropped 53.9% → 33.7% (still ≥15% Go gate). Four parallel autonomous teams + one coordinator commit shipped the engineering retune; v6 build is blocked on OpenRouter rate limit.

| Area | Change | Artifact |
|---|---|---|
| Gate threshold | `CONFIDENCE_THRESHOLD` 0.7 → **0.6** (Sonnet's residual leaks live in 0.5-0.65 band) | Team α merge (`_closed_book_gate.py`) |
| Gate difficulty coverage | L1/L2 → **L1/L2/L3** (v5 L3 leakage 33%) | Team α merge |
| Gate question_type coverage | `multiple_choice` → **`multiple_choice + scenario_based`** (scenario_based was 63% B2 fail rate, silently bypassing gate) | Coordinator commit (`_closed_book_gate.py` GATE_VERSION 2.2.0) |
| Quota math | `OVERALL_TARGET × 0.25` (=2500 absolute) → `ceil(target_size × 0.25)` per-corpus; `set_corpus_target()` setter; `target_size` kwarg on `insert_question_gated()` | Team α merge (`_question_db.py`) |
| Scenario prompt | `+ HARD RULES — NON-DERIVABLE ANCHOR` section in `SCENARIO_TEMPLATE`; answer must depend on a specific entity drawn from the source fact and not implied by the scenario premise | Team β merge (`_prompts.py`) |
| Sampler country balance | `per_country_cap: float | None = None` kwarg on all 5 sampler entry points; multi-fact bundles count every fact toward country quota; `--per-country-cap` CLI flag | Team ε merge (`_fact_sampler.py`, `fact_to_question.py`) |
| Gold sheet refresh | Sub-stratified 120-row export at `data/reports/gold_sheet_v5.csv`; `docs/GOLD_REVIEW_GUIDE_V5.md`; all 10 v2.3 rubrics blank for human review | Team δ branch (awaits user gold review before merge) |
| A4 reference set | External human reference via WSET/CMS public-practice scrape | Team γ branch (running) |
| Tests | 289/289 pass (1 deselected: live-LLM smoke test 403'd by OpenRouter cap) | Phase 2g.7 net: +14 sampler + 5 gold + 4 gate + 1 scenario_based |

Reports: `docs/QUALITY_AUDIT_REPORT.md`, `docs/GENERATION_IMPROVEMENT_PLAN.md`, `docs/PROCESS_LOG.md` (Phase 2g + 2g.5 + 2g.6 + 2g.7 entries).

See `CURRENT_STATUS.md` for detailed phase tracking and the regeneration Go/No-Go gate.

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

Phase 2g.7 four-team retune is merged and green (289/289 tests excluding the OpenRouter-403'd live-LLM smoke test). The immediate sequence is gated on user actions and external signals:

1. **User: top up OpenRouter API key.** `test_c4_calibration::test_c4_live_roundtrip_on_representative_fewshot` and any v6 build/audit will return HTTP 403 "Key limit exceeded" until this is resolved. Until then, all LLM-dependent work is paused.
2. **User: gold review of `data/reports/gold_sheet_v5.csv`** using `docs/GOLD_REVIEW_GUIDE_V5.md` (~120 questions × 10 rubrics, 2-3h). Then re-import: `python -m src.qa.orchestrator import-gold --csv-path data/reports/gold_sheet_v5.csv --reviewer nikita`. After re-import, merge `team-delta-gold-sheet` and rebuild reports — expect κ ≥ 0.6 on `verbatim_copy` and `wine_category_leak`.
3. **Coordinator: build `audit_pilot_v6`** once OpenRouter is unblocked: `python -m src.qa.orchestrator build-corpus --tag audit_pilot_v6 --per-strategy 120 --seed 43` (passing `per_country_cap=0.10` where supported) → `run --teams A,B,C,D`. Cost ≈ $6.
4. **Verify Go/No-Go on v6.** Pass criteria: B2 fail rate on non-cb-tagged L1/L2 ≤ 15%; A4 AUC < 0.9 (or A4 fixed via Team γ); κ ≥ 0.6 on populated rubrics; D3 max country ratio < 2.0. If failing, fork to (a) gate model upgrade Sonnet 4.6 → Opus 4.7 (Decision 4), (b) build C1 + B4 audit agents (deferred Decision 3), or (c) accept and ship.
5. **If v6 passes: kick off the full 10k generation run** (`python -m src.generators.orchestrator generate-all`, revised cost estimate ≈$90 with v2.2 gate at threshold 0.6 + scenario type coverage).

See `CURRENT_STATUS.md` for detailed phase tracking, `docs/GENERATION_IMPROVEMENT_PLAN.md` for the full ranked defect list and Go/No-Go gates, and `docs/PROCESS_LOG.md` 2026-04-23 (Phase 2g), 2026-04-24 (Phase 2g.5 + 2g.6 — closed-book gate v1.0 + v2.0), and 2026-04-25 (Phase 2g.7 — four-team retune) for methodology details.

## Important Links

- **Full project plan:** `PROJECT_PLAN.md`
- **Data sources:** `DATA_SOURCES.md`
- **Scraper implementation specs:** `SCRAPER_PROMPTS.md`
- **Progress tracking:** `CURRENT_STATUS.md`
- **Process log (lab notebook):** `docs/PROCESS_LOG.md`
- **Latest audit report:** `docs/QUALITY_AUDIT_REPORT.md`
- **Latest improvement plan + Go/No-Go gate:** `docs/GENERATION_IMPROVEMENT_PLAN.md`
- **NeurIPS 2026 D&B Track:** Target submission venue
