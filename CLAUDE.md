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
│   ├── backup.sh                 # PostgreSQL & Neo4j backup
│   ├── run_audit_pilot_v5.sh     # Audit #5 harness (historical)
│   ├── run_audit_pilot_v6.sh     # Audit #6 harness (historical)
│   ├── run_audit_pilot_v7_build.sh # Audit #7 phase 1 — build corpus + export gold-v7 (historical)
│   ├── run_audit_pilot_v7_audit.sh # Audit #7 phase 2 — run audit teams + build reports (historical)
│   ├── run_audit_pilot_v8_build.sh # Audit #8 phase 1 — Phase 2g.9 fixes, per-country-cap 0.30
│   └── run_audit_pilot_v8_audit.sh # Audit #8 phase 2 — run audit teams + build reports
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
│   ├── generators/               # pytest tests for src/generators/
│   │   ├── test_closed_book_gate.py, test_corpus_build_cost.py,
│   │   ├── test_country_quota.py, test_fact_sampler.py, test_paraphrase.py,
│   │   ├── test_template_*.py, test_verifier.py, test_vague_regex.py, …
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

## Current Status (as of April 27, 2026)

**Phase:** 2g.9 — audit #7 ran on the post-2g.8 v7 corpus and failed Go/No-Go on B2 (53%), D3 (10.61×), and A1 (2.9%). Investigation traced all three to coordinator-layer wire-up + metric-denominator bugs: `set_corpus_target()` doesn't survive the `subprocess.run` boundary (so the closed-book quota cap silently defaulted to 2500), `--per-country-cap 0.10` was too aggressive at small per-call counts (gutted multi-fact strategies down to 30-40% of target), D3's `max_overrep_ratio` denominator collapses under sparse country annotation (16 of 242 questions tagged), and A1 `_EXTRA_VAGUE` flagged "celebrated" + "notable for" in factual contexts. Phase 2g.9 lands four targeted fixes (env-var fallback, per-country-cap default 0.30, D3 coverage guard, A1 v2.3.1 pattern trim), reverts the gate to Sonnet 4.6 for v8, and ships a v8 audit harness with smaller corpus (per_strategy 40, total 200) to halve audit time + cost. 347/347 tests pass. Awaiting (a) `bash scripts/run_audit_pilot_v8_build.sh` (~4-5h), (b) user gold review of `data/reports/gold_sheet_v8.csv` (~1h, 40 rows), (c) `import-gold` + `bash scripts/run_audit_pilot_v8_audit.sh` (~1-1.5h, ~$5-7).

- Phase 1 (Data Collection): ✅ 38,104 facts from 35 genuine scrapers
- Phase 2 (Question Generation Pipeline): ✅ 5 strategies built and iteratively tuned
- Phase 2c (Quality Audit Framework): ✅ 9 agents across 4 teams under `src/qa/`
- Phase 2d–2f (Audit runs #1–#3 + gold-v1–v3 sign-off): ✅
- Phase 2g (v2.3 §5b/§5c fixes): ✅ Three parallel worktree teams merged
- Phase 2g (audit #4 on `audit_pilot_v4`): ✅ B2 dropped 66% → 36%
- Phase 2g.5 (closed-book MC gate v1.0): ✅ Sonnet 4.6 wired into all 5 generators
- Phase 2g.6 (gate v2.0 — label+quota): ✅ relabel + 25% cap; `score_by_cb_split()` helper
- Phase 2g (audit #5 on `audit_pilot_v5`): ✅ B2 53.9% → **33.7%**; A4 AUC 0.954
- Phase 2g.7 (four-team retune): ✅ Gate threshold 0.6 + L1/L2/L3 + scenario_based; per-corpus quota math; scenario HARD RULE; `per_country_cap` sampler kwarg; A4 v1.2.0 fixed-reference (104-Q human set)
- Phase 2g (audit #6 on `audit_pilot_v6`): ✅ Run completed (run_id `bfc39e1a…`, $4.82, 2,612 LLM calls). **Failed Go/No-Go on B2 (46% > 15%) and D3 (4.52× > 2.0×).** Investigation found three coordinator-layer regressions: (i) Team ε's `per_country_cap` kwarg was never passed by the orchestrator → `_run_generator` → strategy CLIs (3 layers of missing wire-up); (ii) `set_corpus_target()` was defined but never called by `build_pilot_corpus()`, so v6 used the 10k default cap of 2500 instead of the per-pilot cap of 66 → 158 closed-book relabels leaked through; (iii) A3 over-flagging on T/F templates and borderline LCS=0.60 cases (8 fails / 264 = 3% > 2% gate, but 7/8 are measurement artifacts).
- Phase 2g.8 (cost optimizations + wire-up fixes): ✅ Branch `phase-2g.8/cheaper-corpus-build` (5 commits, 329/329 tests pass). Cost optimizations: gate-before-paraphrase reorder for templates (~60% Gemini call reduction); OpenRouter `provider.sort=price` routing for verifier + paraphrase calls (drops Gemini Pro from >200K-context tier). D3 wire-up: `--per-country-cap` flag on all 5 strategy CLIs + `_run_generator` propagation + orchestrator `build-corpus` exposure. Quota wire-up: `set_corpus_target(per_strategy × 5)` called from `build_pilot_corpus()` with try/finally cleanup. A3 v1.2.0: skip T/F + LCS fail threshold 0.60 → 0.65. Gate v2.3.0: model Sonnet 4.6 → Opus 4.7 (env-overridable via `OENOBENCH_GATE_MODEL`).
- Phase 2g (audit #7 on `audit_pilot_v7`): ✅ Run completed (run_id `9ba6f760-5a6c-4403-9709-412c13eac30c`, 242 questions, $4.42, 2,436 LLM calls). **Failed Go/No-Go on B2 (52.9%), D3 (10.61×), A1 (2.9%); D1 also fails (claude Δ = +0.16); Cohen's κ = n=0 (gold review not done).** Investigation found: (i) `set_corpus_target()` doesn't survive `subprocess.run`, so the closed-book quota cap defaulted to 2500 across all strategy workers (172 GATE RELABEL events, 0 GATE QUOTA FULL); (ii) `--per-country-cap 0.10` × `count=4` × `cluster_size=2-3` rounded to 1-2 facts/country/call, gutting multi-fact strategies (template 30, comparative 34, scenario 42, distractor 16 of 120 each); (iii) D3's `max_overrep_ratio` denominator was 16 of 242 country-tagged questions, inflating the metric by ~4×; (iv) A1 bare `\bcelebrated\b` and bare `notable for` flagged factual past-tense and historical phrasings.
- Phase 2g.9 (audit #7 follow-up fixes): ✅ Four targeted fixes shipped, 347/347 tests pass. Env-var fallback `OENOBENCH_CORPUS_TARGET` for closed-book quota cap that crosses subprocess boundaries; v8 build script with `--per-country-cap 0.30` default; D3 v1.1.0 coverage guard (downgrades FAIL→WARN below 50% country annotation coverage); A1 `_EXTRA_VAGUE` v2.3.1 (drop bare `celebrated`, drop `notable for`, keep `celebrated for`).

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

### Phase 2g.8 shipped (2026-04-26)

Audit #6 ran on `audit_pilot_v6` (run_id `bfc39e1a-ba6b-471d-bde0-87eead62d1dc`, 264 questions, $4.82, 2,612 LLM calls); B2 fail rate 46% (still > 15% gate), D3 max country ratio 4.52× (> 2.0× gate), A3 8/264 = 3% (> 2% gate). Investigation showed all three were dominated by coordinator-layer wire-up regressions or measurement artifacts — not the underlying generation logic. Phase 2g.8 lands the wire-up fixes + cost optimizations + gate model upgrade.

| Area | Change | Artifact |
|---|---|---|
| Build-corpus cost opt 1 | Gate-before-paraphrase reorder for templates: `_question_db.insert_question_gated()` accepts `pre_screened: GateResult \| None`; `template_generator.py` runs `screen_question()` first, skips Gemini paraphrase + verifier on gate-flagged questions (saves ~60% of those calls) | `d35ee00` |
| Build-corpus cost opt 3 | `LLMClient.generate(extra_body=...)` forwards OpenRouter routing hints; `_verify.py` + `_template_paraphrase.py` pass `{"provider": {"sort": "price"}}` to drop Gemini Pro from >200K-context tier | `d35ee00` |
| D3 wire-up | `--per-country-cap` `click.option` added to `template_generator`, `scenario_generator`, `comparative_generator`, `distractor_miner` (was already on `fact_to_question`); `_run_generator()` propagates it to subprocess argv; `build_pilot_corpus()` accepts `per_country_cap` kwarg; orchestrator `build-corpus` CLI exposes `--per-country-cap` | `846fb8e` |
| Quota wire-up | `build_pilot_corpus()` calls `set_corpus_target(per_strategy × 5)` before strategy dispatch with `try/finally` cleanup, so audit pilots actually use `ceil(corpus × 0.25)` cap (66 for 600-Q pilot) instead of the 10k default (2500) | `2a30348` |
| A3 v1.1.0 → v1.2.0 | Skip `true_false` (T/F's 1-token correct answer breaks LCS denominator); LCS fail threshold `0.60 → 0.65`. Projected v6 fail rate 8/264 = 3.0% → 1/260 = 0.4% | `c4443a9` |
| Gate v2.2.0 → v2.3.0 | `GATE_MODEL` Sonnet 4.6 → **Opus 4.7**, overridable via `OENOBENCH_GATE_MODEL` env var. Audit-cycle marginal cost: ~+$2. Full 10k decision deferred to post-audit-#7. | `5825aa8` |
| Audit harness | Two-phase harness: `scripts/run_audit_pilot_v7_build.sh` (build-corpus + export-gold-v7) and `scripts/run_audit_pilot_v7_audit.sh` (run audit teams + build-reports). Split because Cohen's κ requires gold labels on the same corpus the audit runs on, so the v7 review must happen on v7 questions (not v5) — between the two phases. v5/v6 scripts retained as historical references. | `846fb8e` (initial single-phase) + 2026-04-26 evening (split) |
| Tests | 329/329 pass (1 deselected: live-LLM smoke test). Phase 2g.8 net: +9 tests (3 set_corpus_target + 4 A3 v1.2.0 + 2 gate-model env override) plus the +14 tests from `846fb8e` (per-country wire-up across 4 layers) and +15 tests from `d35ee00` (cost opts) | All commits |

Branch state: `phase-2g.8/cheaper-corpus-build` carries 5 commits ready for v7 audit run, not yet merged to `main`.

### Phase 2g.9 shipped (2026-04-27)

Audit #7 ran on `audit_pilot_v7` (run_id `9ba6f760-5a6c-4403-9709-412c13eac30c`, 242 questions, $4.42, 2,436 LLM calls); failed three Go/No-Go gates and exposed four root causes — all coordinator-layer wire-up or metric-denominator bugs, not generation regressions. Phase 2g.9 lands the four targeted fixes plus a v8 audit harness.

| Area | Change | Notes |
|---|---|---|
| Closed-book quota propagation | `_resolve_default_target_size()` in `_question_db.py` reads `OENOBENCH_CORPUS_TARGET` env var between in-process override and `OVERALL_TARGET` fallback. `build_pilot_corpus()` exports it alongside `set_corpus_target()` and restores prior value in `finally`. | Env vars cross `subprocess.run` for free; no need for the four-layer CLI wire-up that broke audit #6's `--per-country-cap` |
| Per-country cap default | `scripts/run_audit_pilot_v8_build.sh` uses `--per-country-cap 0.30` (was 0.10 in v7). | At per-call `count=4`, `0.30 × 4 × cluster_size 2-3 = 3-4`, vs `0.10 × ... = 1-2` that disqualified multi-fact bundles. Structural sampler-math fix deferred until D3 denominator is calibrated. |
| D3 v1.1.0 coverage guard | `team_d_population.py`: when country-tag coverage < 50%, severity downgrades FAIL → WARN. Always-emitted payload fields: `country_annotation_coverage`, `country_coverage_sufficient`, `country_coverage_threshold`, `country_tagged_questions`, `total_questions`. | One-directional: never upgrades severity. The metric is still reported so reviewers see the inflated number alongside the coverage flag. |
| A1 `_EXTRA_VAGUE` v2.3.1 | Removed bare `\bcelebrated\b` (kept `celebrated for`) and removed `notable for` entirely. | v7 fail #5 (Roman poet "celebrated" the landscape) and v7 fail #7 ("notable for being the country's first" Tetra Pak) were clean false positives. Marketing usage of `notable for` overlaps with `acclaimed`/`world-class`/`quintessential` patterns that remain. |
| v8 audit harness | New `scripts/run_audit_pilot_v8_build.sh` and `_audit.sh`; `TAG=audit_pilot_v8`, `SEED=45`, `GOLD_OUT=data/reports/gold_sheet_v8.csv`. v7 scripts retained as historical references. | Phase 1 (~13h), gold review (~2-3h), phase 2 (~3-4h, ~$15-20). Same two-phase shape as v7. |
| Gate model for v8 | v8 build script exports `OENOBENCH_GATE_MODEL=anthropic/claude-sonnet-4.6` to revert the gate from Opus 4.7 (Phase 2g.8 default) back to Sonnet 4.6. Module default in `_closed_book_gate.py` unchanged (still Opus). | v6 → v7 (Sonnet → Opus, both with broken cap) only added +14 relabels; with Phase 2g.9 cap fix saturating at 150 either way, Opus's marginal pickup is small. Sonnet isolates the cap-fix effect and saves ~$60 on the 10k run if v8 passes B2. |
| Tests | 347/347 pass. Phase 2g.9 net: +13 new tests (6 env-var: 3 in `test_closed_book_gate.py` + 3 in `test_corpus_build_cost.py`; 3 D3 in new `tests/qa/test_team_d.py`; 3 A1 v2.3.1 in `test_team_a.py`). | All four fixes shipped with positive + negative test coverage. |

Reports: `docs/QUALITY_AUDIT_REPORT.md` (audit #7 results), `docs/PROCESS_LOG.md` 2026-04-27 (Phase 2g.7 audit run #7 + Phase 2g.9 fixes), `docs/GENERATION_IMPROVEMENT_PLAN_AUTO.md`.

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

Phase 2g.9 fixes are committed and tested (347/347 pass). The v7 corpus is superseded; v8 is the next audit cycle.

1. **Phase 1 — build v8 corpus + export gold sheet** (~4-5h, automated):
   ```bash
   nohup bash scripts/run_audit_pilot_v8_build.sh &
   ```
   This runs `build-corpus --tag audit_pilot_v8 --per-strategy 40 --seed 45 --per-country-cap 0.30` (with all Phase 2g.8 + 2g.9 fixes active, gate reverted to Sonnet 4.6), then exports `data/reports/gold_sheet_v8.csv` (40 rows × 10 rubrics, all rubric columns blank).

   **Sanity-check the build output before launching phase 2:**
   - Corpus size close to 200 (not 242/600).
   - `grep -c "GATE QUOTA FULL" data/logs/audit_pilot_v8_build_*.log` > 0.
   - `closed_book_solvable` count in DB ≤ 50 (= ceil(200 × 0.25)).

   If those don't hold, the Phase 2g.9 fixes didn't take and audit #8 should not launch.

2. **User: gold review of `data/reports/gold_sheet_v8.csv`** using `docs/GOLD_REVIEW_GUIDE_V5.md` (rubric definitions stable across v5/v7/v8). ~1h (40 rows instead of v7's 120). Then re-import:
   ```bash
   python -m src.qa.orchestrator import-gold \
       --csv-path data/reports/gold_sheet_v8.csv --reviewer nikita
   ```

3. **Phase 2 — run audit teams + build reports** (~1-1.5h, ~$5-7):
   ```bash
   nohup bash scripts/run_audit_pilot_v8_audit.sh &
   ```
   The build-reports step computes Cohen's κ from the imported v8 gold labels.

4. **Verify Go/No-Go on v8.** Pass criteria: B2 fail rate on non-cb-tagged L1/L2/L3 ≤ 15%; A1 ≤ 2%; A4 AUC < 0.9; κ ≥ 0.6 on populated rubrics; D3 either < 2.0× max country ratio OR `country_coverage_sufficient=false` with WARN severity; closed-book quota cap properly enforced (≤ 25% of corpus tagged `closed_book_solvable`). If B2 still fails, the residual is structural in scenario_synthesis prompts — fork to a scenario-prompt revision before further model upgrades.

5. **Re-measure D1 on v8.** With the v8 corpus mix likely changing under the Phase 2g.9 fixes, the Claude over-preference Δ may resolve naturally. If it doesn't, design a per-generator share cap before the 10k run.

6. **If v8 passes: decide on the full-generation gate model.** v8 already runs on Sonnet (via the build script's env-var export), so if B2 passes the cheaper gate is the proven path — no change needed for the 10k run, which falls back to the module default. If v8 fails B2, retry by deleting the env-var export from the v8 build script; `_closed_book_gate.py`'s module default is still Opus 4.7.

7. **Kick off the full 10k generation run** (`python -m src.generators.orchestrator generate-all`). The `OVERALL_TARGET` fallback in `_question_db.py` already resolves to 10,000, so the closed-book quota cap math uses 2,500 — no env var needed. If you switch to Opus for the 10k, set `OENOBENCH_GATE_MODEL=anthropic/claude-opus-4.7` (or unset for the module default).

**Skipping the v8 gold review is permitted but discouraged** — phase 2 will still complete (κ shows n=0 for the v2.3 rubrics). You can review later and re-run only `build-reports --run-id <v8_run_id>` to refresh κ.

See `CURRENT_STATUS.md` for detailed phase tracking, `docs/GENERATION_IMPROVEMENT_PLAN.md` for the full ranked defect list and Go/No-Go gates, and `docs/PROCESS_LOG.md` 2026-04-23 (Phase 2g), 2026-04-24 (Phase 2g.5 + 2g.6), 2026-04-25 (Phase 2g.7), 2026-04-26 (Phase 2g.7 audit #6 + Phase 2g.8), and 2026-04-27 (Phase 2g.7 audit #7 + Phase 2g.9) for methodology details.

## Important Links

- **Full project plan:** `PROJECT_PLAN.md`
- **Data sources:** `DATA_SOURCES.md`
- **Scraper implementation specs:** `SCRAPER_PROMPTS.md`
- **Progress tracking:** `CURRENT_STATUS.md`
- **Process log (lab notebook):** `docs/PROCESS_LOG.md`
- **Latest audit report:** `docs/QUALITY_AUDIT_REPORT.md`
- **Latest improvement plan + Go/No-Go gate:** `docs/GENERATION_IMPROVEMENT_PLAN.md`
- **NeurIPS 2026 D&B Track:** Target submission venue
