# OenoBench — Current Status & Progress

**Last updated:** May 2, 2026
**Project phase:** Phase 2g.12 — corpus-build undershoot fixes. v9 audit pilot ran the speedup pipeline in 18 min (vs v8's 11.4h, ~21× faster) but kept only 46/100 (46%, vs v8's 56%). Investigation surfaced 4 root causes — broken Gemini Flash slug returning OpenRouter 400s, C4 reject-threshold off-by-one firing on 113 boundary cases, LLM-strategy cell-allocation that schedules 30 cells × take=1 and starves on `sample_fact_pairs() == []`, and Gemini Pro JSON-fence malformations. All 5 fixes (4 root causes + 1 misleading log line) shipped on `phase-2g.12/corpus-undershoot-fixes`. 494/494 tests pass.
**Target venue:** NeurIPS 2026 Datasets & Benchmarks Track (~May 15, 2026 deadline)

## Latest cliff notes (start here next session)

- **Phase 2g.18 cost-down v16 plan (2026-05-02):** 9 levers across 4 parallel
  worktree teams targeting ≥50% cost reduction on the 10k run (baseline
  ~$9/100 from v9-v15 pilots → target ≤$4.50/100). Quota changes: closed-book
  cap 25%→40% (L1), template share 10% (already in code, doc-only fix).
  Audit: B1/B2 "claude" judge → Sonnet 4.6 (L2), B2 panel 5→4 (L3), D1
  sample 20→10 (L7), C4 opt-in (L8). Build: generator mix v2.4 (L4 — gemini
  +400, claude -600, qwen +200), verifier-skip B5 plumbing (L5),
  gate L3 → Sonnet (L6 env trial), FTQ substantiveness strict (L9).
  Plan: /home/winebench/.claude/plans/virtual-snacking-anchor.md.
  Pilot: scripts/run_audit_pilot_v16_build.sh (per_strategy=15, ~75 attempts).

- **Phase 2g.12 fixes shipped (2026-04-29):** Branch `phase-2g.12/corpus-undershoot-fixes`, one squash-style commit `2aa084a`, 494/494 pytest pass (was 472, +22 new tests across 5 fixes).

  | Fix | File | What | Why |
  |---|---|---|---|
  | 1 | `src/generators/_template_paraphrase.py` + `src/generators/_verify.py` | `_PARAPHRASE_FLASH_DEFAULT` and `_VERIFIER_FLASH_DEFAULT` from `google/gemini-3.1-flash-preview-20260219` → `google/gemini-3.1-pro-preview` | OpenRouter rejected the Flash slug with 400 ("not a valid model ID"); every paraphrase + every Llama/Qwen verify call wasted a round-trip before failing over to Pro. Phase 2g.11 C2 lever was effectively dead. Env-var override (`OENOBENCH_PARAPHRASE_MODEL` / `OENOBENCH_VERIFIER_MODEL`) preserved for when a real Flash 3.1 listing appears. |
  | 2 | `src/generators/_schemas.py` | C4 reject_threshold: `1 if labelled_int >= 3 else 2` → `2 if labelled_int >= 3 else 3` | All 113 v9 C4 rejects were `delta=2 threshold=2` for L1/L2 — the C4 classifier consistently over-predicts difficulty on fact-anchored detail questions that the template heuristic correctly buckets. Loosen L1/L2 to tolerate a 2-level miss; L3+ stays strict at 1. Audit-side D-gates catch downstream drift. |
  | 3 | `src/qa/_corpus.py` | `_build_cell_calls(strategy, module, want, per_country_cap)` extracted; `cell_count = max(1, min(G*D, want // 2))` so each LLM-strategy cell carries ≥2 budget | Old formula `per_cell = max(1, want // (G*D))` scheduled all 30 cells with take=1 when `want < 30`, silently overspending budget by 50% AND starving sampler-empty cells out at 0 questions. v9 saw 26/60 cells exit zero-attempt; comparative + scenario stuck at 4/20 each. New formula gives e.g. `want=20 → 10 cells × 2`, `want=40 → 20 cells × 2`, `want=100 → 30 cells (capped) × 3-4`. |
  | 4 | `src/generators/_llm_client.py` | `_try_parse_json` prepended with tag-agnostic Markdown-fence strip pre-pass | Gemini Pro produced 65/67 (97%) of v9 parse failures, mostly responses wrapped in ```json / ```jsonc / ```python fences that the existing `_FENCE_RE` (limited to `(?:json)?`) didn't match. No-op when fences absent. |
  | 5 | `src/qa/_corpus.py` | Strategy-completion log: `"corpus: {s} budget={want} generated={actual} tagged={tagged}"` (was `generated={want}`) | Old line reported the budget as `generated`, so v9 logs read "generated=20 tagged=4" for strategies that produced 4 questions, hiding the undershoot. New line counts actual rows since `strategy_started`. |

- **v9 audit pilot — phase 1 build (2026-04-28):** Per_strategy=20 (target=100, capped down from v8's 40/200 by `6482ebd` to halve audit cost). Wall **18 min 27 s** vs v8's 11.4h (~37× faster). LLM calls **772** vs v8's ~16k (~21× fewer). Kept **46/100 (46%)**: comparative=4, distractor=10, fact_to_question=20, scenario=4, template=8. closed_book_solvable=20/46 (43%). 21 circuit-breaker fires (9 fact_to_question, 9 scenario, 2 comparative); 26 zero-attempt sampler-starved cells. Gold sheet `data/reports/gold_sheet_v9.csv` exported (20 rows). Audit phase 2 NOT YET RUN — corpus too small + Phase 2g.12 fixes pending.

- **Audit run #8 on `audit_pilot_v8` (run_id `7dc2ab81-bc9a-40b1-a1a4-3ddf66a6e6fe`, 111 Qs):** Phase 2 completed in 1h 36min. D3 max country ratio 4.19× was correctly downgraded to WARN by the Phase 2g.9 coverage guard (annotation coverage 9.0%, < 50% threshold). Reports at `docs/QUALITY_AUDIT_REPORT.md` + `docs/GENERATION_IMPROVEMENT_PLAN_AUTO.md`. v8 build itself ran across 4 sessions (sleep, restart, sleep) and accumulated 53/111 cb-tagged questions because of a now-fixed restart-window bug (`d8a8a5f`).

- **Phase 2g.11 — 10 speedup levers shipped (2026-04-28):** Parallel agent teams (Alpha/Bravo/Charlie/Delta/Echo/Foxtrot/Golf) implemented the levers from `~/.claude/plans/optimized-forging-locket.md`. All on `main`, 472/472 pytest pass (was 373; +99 new tests).

  | Lever | Commit | Activation | Default |
  |---|---|---|---|
  | A1 throttle removal | `f728974` | `OENOBENCH_LLM_THROTTLE_MS` | 100ms ±50% jitter; 0 disables |
  | C1 timeout + provider failover | `f728974` | `timeout` kwarg in callers | None (off until callers opt in) |
  | A2 in-process strategy dispatch | `0550511` | `OENOBENCH_USE_SUBPROCESS_DISPATCH` reverts | in-process ON |
  | A3 cell-level ThreadPool + `_QUOTA_LOCK` | `f2f6389` | `OENOBENCH_MAX_WORKERS` / `--max-workers N` | 1 (sequential) |
  | A4 strategy-level ThreadPool | `6b4bee0` | `OENOBENCH_STRATEGY_WORKERS` / `--strategy-workers N` | 1 (sequential) |
  | B1 LLM-decision cache (Postgres) | `ca13b2d` | `OENOBENCH_LLM_CACHE` | OFF |
  | B2 sampler substantiveness filter | `0b190a0` | `OENOBENCH_FACT_SUBSTANTIVE_FILTER` | OFF |
  | B3 per-cell circuit breaker | `49e2fe3` | `OENOBENCH_CIRCUIT_BREAKER` | OFF |
  | B4 tier-aware gate (Haiku/Sonnet/Opus) | `5f3247d` | `OENOBENCH_GATE_MODEL_L{1,2,3}` or global `OENOBENCH_GATE_MODEL` | tier-aware ON |
  | B5 verifier-skip helper (DORMANT) | `7393e9b` | `OENOBENCH_VERIFIER_SKIP` | helper exists; pipeline runs verifier BEFORE gate, so `gate_passed` is always False until a Phase 2g.12 reorder |
  | C2 Gemini Flash variant | `aca5932` | `OENOBENCH_PARAPHRASE_MODEL` / `OENOBENCH_VERIFIER_MODEL` revert | Flash; Pro fallback on failure |

  Plus: `d8a8a5f` restart-safe `started` timestamp in `build_pilot_corpus` (closes a Phase 2g.10 bug where each restart of a build script reset the cb-quota window, letting cb-tags accumulate past the cap across sessions).

- **v9 harness on `main`:** `scripts/run_audit_pilot_v9_build.sh` exports the speedup env vars (`OENOBENCH_LLM_THROTTLE_MS=0`, `OENOBENCH_LLM_CACHE=1`, `OENOBENCH_FACT_SUBSTANTIVE_FILTER=1`, `OENOBENCH_CIRCUIT_BREAKER=1`, `OENOBENCH_MAX_WORKERS=8`, `OENOBENCH_STRATEGY_WORKERS=3`) and runs `build-corpus --tag audit_pilot_v9 --per-strategy 40 --seed 46 --per-country-cap 0.30 --max-workers 8 --strategy-workers 3`. Mirrors v8's budget for direct A/B comparison. Expected wall: ~1-3h (vs v8's 11.4h). Audit phase 2 cost: ~$2-4 / ~30-60 min on v9-sized corpus.

- **Test status:** 472/472 pytest pass on `main` (was 373 at start of Phase 2g.11; +99 new across the 10 levers).

- **v9 sanity-check checklist (after build):**
  - Corpus size close to 200 (circuit breaker may undershoot on low-yield strategies — by design).
  - `grep -c "LLM call" data/logs/audit_pilot_v9_build_*.log` should be **significantly < 16k** (v8 baseline).
  - `grep "CIRCUIT BREAKER" data/logs/audit_pilot_v9_build_*.log | wc -l` → cells abandoned.
  - `grep "LLM cache HIT" data/logs/audit_pilot_v9_build_*.log | wc -l` → cache hit-rate.
  - `closed_book_solvable` count in DB ≤ 50 (= ceil(200 × 0.25)).
  - `grep -c "GATE QUOTA FULL"` should be > 0 if cb-rate is high.

- **Phase 2g.12 deferred candidates:** B5 architecture refactor (reorder pipeline so gate runs before verifier so `should_skip_verifier` actually fires); C3 budget pooling (soft strategy floors with fungible residual); C4 batched dedup embeddings (only if profiling shows dedup as bottleneck); the cap-vs-actual-yield mismatch in the closed-book quota math (cap computed against `target_size`, evaluated against actual kept count).

- **Next session start point:**
  1. Run phase 1: `nohup bash scripts/run_audit_pilot_v9_build.sh &` (~1-3h).
  2. Sanity-check the build log against the v8 baseline (LLM call count, cache hits, circuit-breaker activations).
  3. User: gold review of `data/reports/gold_sheet_v9.csv` (~1h) using `docs/GOLD_REVIEW_GUIDE_V5.md`.
  4. Import: `python -m src.qa.orchestrator import-gold --csv-path data/reports/gold_sheet_v9.csv --reviewer nikita`.
  5. Run phase 2: `nohup bash scripts/run_audit_pilot_v9_audit.sh &` (~30-60 min, ~$2-4).
  6. Verify Go/No-Go on v9 (criteria below). Compare wall + LLM-call counts against v8.
  7. If v9 passes: kick off the full 10k run with `python -m src.generators.orchestrator generate-all --max-workers 8 --strategy-workers 3` and the same env-var profile as v9.

---

## Timeline Overview (30 weeks)

| Phase | Weeks | Status |
|-------|-------|--------|
| 1. Infrastructure & Data Collection | 1-6 | **Complete** — 38,104 facts from 35 genuine scrapers |
| 2. Question Generation Pipeline | 7-10 | **Complete** — all 5 strategies built and iteratively tuned |
| 2c. Quality Audit Framework | 11 | **Complete** — 9-agent multi-team audit |
| 2d. Audit run #1 (pilot 472 Qs) | 12 | **Complete** — Go/No-Go BLOCKED, see findings below |
| 2e. Defect fixes + audit run #2 | 13 | **Complete** — v2.2 fixes shipped |
| 2f–2g. v2.3 fixes + audits #3, #4 | 14 | **Complete** — B2 dropped 66% → 36%; structural residual identified |
| 2g.5. Closed-book gate v1.0 (REJECT) | 14 | **Complete** — Sonnet 4.6 MC pre-screen wired into all 5 generators |
| 2g.6. Closed-book gate v2.0 (LABEL+QUOTA) | 14 | **Complete** — relabel + 25% cap; paired eval helper `score_by_cb_split()` |
| 2g.7. Audit #5 + four-team retune | 14 | **Complete** — gate threshold 0.6, L3 + scenario_based coverage, per-corpus quota math, scenario HARD RULE, sampler country cap kwarg, gold sheet refresh, A4 v1.2.0 fixed-reference |
| 2g.7. Audit #6 (`audit_pilot_v6`) | 15 | **Complete** — failed Go/No-Go on B2 (46%) + D3 (4.52×); revealed three coordinator wire-up regressions |
| 2g.8. Wire-up fixes + cost opts + gate upgrade | 15 | **Complete** — `set_corpus_target` wired up (in-process), `--per-country-cap` plumbed end-to-end, A3 v1.2.0, gate model Sonnet→Opus, Gemini cost opts. Merged to `main`. |
| 2g.7. Audit #7 (`audit_pilot_v7`) | 15 | **Complete** — failed Go/No-Go on B2 (52.9%, regression), D3 (10.61×, regression), A1 (2.9%); revealed four root causes (subprocess quota propagation, per-country-cap math, D3 denominator, A1 FP) |
| 2g.9. Audit #7 follow-up fixes + v8 harness | 15 | **Complete** — env-var fallback for closed-book quota that crosses subprocess boundaries, per-country-cap default 0.30 in v8 script, D3 v1.1.0 coverage guard, A1 v2.3.1 pattern trim. 347/347 tests pass on `main`. |
| 2g.10. Per-strategy closed-book budget | 15 | **Complete** — `OENOBENCH_STRATEGY_TARGET` env var, per-strategy `count_closed_book_solvable(strategy=...)`, fairness routing in `insert_question_gated`. 369/369 tests pass. |
| 2g.10 follow-up. Restart-safe build window | 15 | **Complete** (`d8a8a5f`) — `_resolve_build_started_at(tag)` queries `MIN(created_at)` of build-tagged questions so `OENOBENCH_CORPUS_BUILD_SINCE` survives restart. Closed v8 cap-leak (53/111 cb-tagged across 4 sessions). |
| 2h. Audit run #8 (`audit_pilot_v8`) | 15 | **Complete** — phase 1 build 11.4h / 16k LLM calls / 111 Qs (~99% rejection); phase 2 audit 1h 36min, run_id `7dc2ab81…`. D3 4.19× correctly downgraded by coverage guard (9% < 50%). |
| 2g.11. Generation pipeline speedup | 15 | **Complete** — 10 levers (A1/A2/A3/A4/B1/B2/B3/B4/C1/C2 active; B5 dormant) shipped via 7 parallel agent teams. v9 harness on `main`. 472/472 tests pass. |
| 2i. Audit run #9 (`audit_pilot_v9`) — phase 1 build | 15-16 | **Complete** — 18 min wall, 772 LLM calls, kept 46/100 (46%); validates speedup but undershoots corpus. Drove Phase 2g.12 root-cause investigation. |
| 2g.12. Corpus-build undershoot fixes | 15-16 | **Complete** — 5 fixes shipped (Flash slug, C4 threshold, cell-allocation, JSON fence strip, truth-tell log). 494/494 tests pass. |
| 2i. Audit run #10 (rebuild on Phase 2g.12 fixes) | 15-16 | **Pending** — re-run `run_audit_pilot_v9_build.sh` at `per_strategy=40` (target=200) on a new tag to validate the fixes. Estimated yield 145–165/200 vs v8's 111/200. |
| 2j. Full 10k generation run | 16 | **Pending** — gated on v9 Go/No-Go pass; runs with `--max-workers 8 --strategy-workers 3` and the v9 env-var profile. |
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

Phase 2g.18 (2026-05-02): user direction is to keep template at 10% (weakest
strategy per gold-v3 review). The 25% number in earlier docs was stale —
`STRATEGY_TARGETS` has been at 1000 since v2.3 (2026-04-22).

| Strategy | File | % | Status |
|----------|------|---|--------|
| Fact-to-Question | `fact_to_question.py` | 45% (4,500) | **Built** |
| Template-Based | `template_generator.py` | 10% (1,000) | **Built** — 45 templates |
| Comparative | `comparative_generator.py` | 15% (1,500) | **Built** — entity affinity scoring, country-level filtering |
| Scenario Synthesis | `scenario_generator.py` | 15% (1,500) | **Verified** — inference-over-recall prompts, cohesion checks |
| Distractor Mining | `distractor_miner.py` | 15% (1,500) | **Built** — confusable entity matching, richness filtering |

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
