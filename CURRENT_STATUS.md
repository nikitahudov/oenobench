# OenoBench — Current Status & Progress

**Last updated:** May 4, 2026 (release_v1.2 SHIPPED — **3,266 questions** post-audit, post-drop, post-difficulty-relabel, post-zero-correct-audit, post-borderline-review)
**Project phase:** Phase 2j — release_v1.2 final NeurIPS submission corpus. Currently **3,266 questions** in release_v1.2 (3,329 pre-zero-correct-audit minus 54 round-1 audit drops minus 9 round-2 borderline-review-reject drops). Originally **3,329 questions** (all draft) after running the full 9-agent audit on release_v1.1 (3,670), dropping 341 with critical FAILs on {A1, A3, B1, C2, B3-UbiquityRisk}, and relabelling 1,259 difficulties using C4_DifficultyAudit's rated_difficulty (1,252) + human suggested_difficulty (7) from the gold-sheet review. B2 (closed-book solvability) and C4 (difficulty-audit) FAILs were intentionally KEPT — B2 because LLM judges have low historical κ with humans for this rubric, C4 because the relabel addresses the underlying signal. Per-strategy: FTQ 1,940, distractor 412, template 389, scenario 327, comparative 261. Per-domain: wine_regions 1,108, grape_varieties 766, producers 515, viticulture 502, wine_business 250, winemaking 188. Per-difficulty post-relabel: L1=694, L2=927, L3=698, L4=1,010 (vs pre-relabel L1=1,261, L2=1,559, L3=218, L4=291 — 51% L3+L4 vs prior 14%). Audit cost: ~$76 + ~$160 cumulative release_v1 work = ~$236 total OpenRouter. 771/771 tests pass on main.
**Target venue:** NeurIPS 2026 Datasets & Benchmarks Track (~May 15, 2026 deadline)

## Latest cliff notes (start here next session)

- **Phase 2j release_v1.2 shipped (2026-05-03):** Audit + drops + difficulty
  relabel applied to release_v1.1 (3,670). Final submission corpus is
  **3,329 questions** tagged `release_v1.2`.

  Audit run id: `2ba38269-5e66-44aa-aaaf-010dc7ef19d4`. Wall: 5h 22m. Cost: $76.
  Followed by Phase 5a (drops) + Phase 5b (difficulty relabel) in a single
  Postgres transaction.

  Drop policy: untag from release_v1.1 if any FAIL on
  {A1_LexicalHygiene, A3_FactEcho, B1_TriJudgeAnswer, C2_CategoryLeak,
  B3_UbiquityRisk}. KEEP if only B2 or C4 fails. User-decided rationale:
  B2 has low historical κ (0.007) — LLM closed-book judges are unreliable
  for this rubric, so don't bulk-drop on their signal. C4 difficulty
  mislabel is fixable via relabel rather than drop.

  Drop attribution (with overlap):
    A1 (vague phrasing)        :  60 questions
    A3 (verbatim copy)         :  63
    B1 (wrong answer key)      :  47
    C2 (wine-category leak)    :   9
    B3 (ubiquity-grape × region):  183  ← biggest contributor
  Distinct dropped: **341** (21 questions failed multiple drop-agents).

  Difficulty relabel:
    Source: C4_DifficultyAudit FAIL (delta ≥ 2 from assigned)  + human
    suggested_difficulty from the release_v1_1_smart gold-sheet review.
    Human override wins over C4 where both present (matched on 8/8 spot
    checks anyway — C4 well-calibrated against human judgement).
    Updated 1,259 questions (1,252 from C4, 7 from human).
    Provenance preserved via tags: `audit_difficulty_relabeled_c4_fail` /
    `audit_difficulty_relabeled_human_override`.
    Note: the public `question_id` (e.g. `WB-REG-0042-L3`) keeps its
    original L-suffix; only `questions.difficulty` column was updated.
    Eval consumers read from the column, not the suffix.

  **release_v1.2 final state:**

  | Strategy | release_v1.1 | release_v1.2 | Δ |
  |---|---:|---:|---:|
  | fact_to_question | 2,098 | 1,940 | -158 |
  | distractor_mining | 486 | 412 | -74 |
  | template | 433 | 389 | -44 |
  | scenario_synthesis | 345 | 327 | -18 |
  | comparative | 308 | 261 | -47 |
  | **TOTAL** | **3,670** | **3,329** | **-341** |

  Per-domain (draft only):
  | Domain | release_v1.1 | release_v1.2 |
  |---|---:|---:|
  | wine_regions | 1,206 | 1,108 |
  | grape_varieties | 935 | 766 (B3 hit hardest) |
  | producers | 539 | 515 |
  | viticulture | 525 | 502 |
  | wine_business | 272 | 250 |
  | winemaking | 193 | 188 |

  Per-difficulty (post-relabel):
  | Level | Pre | Post | Δ |
  |---|---:|---:|---:|
  | L1 | 1,261 | 694 | -567 |
  | L2 | 1,559 | 927 | -632 |
  | L3 | 218 | 698 | +480 |
  | L4 | 291 | 1,010 | +719 |

  Corpus is now 51% L3+L4 (was 14%) — meaningfully harder, calibrated by
  C4's Gemini-Pro re-rating + human spot-check overrides.

  Kept-but-flagged (FAIL surviving in release_v1.2 — disclosed in datasheet):
    B2 (closed-book solvability) : 1,340 questions
    C4 (difficulty mislabel)     : 1,252 questions (now relabelled — these
                                    are the SOURCE of the relabel; the
                                    audit signal pre-dates the new
                                    difficulty column)

  Tools shipped during this phase:
  - `scripts/audit_ubiquity_full.py` — corpus-wide B3_UbiquityRisk audit
    (curated + data-driven ubiquity grapes × region-class entity match)
  - `scripts/tag_audit_actions.py` — categorises questions into
    audit_clean / audit_warn_only / audit_fail_review / audit_fail_critical;
    emits `docs/RELEASE_V1_1_AUDIT_ACTIONS.md`
  - `scripts/build_smart_review_sheet.py` — composes a 50-Q smart sample
    (stratified random + critical-FAIL + borderline-WARN); fed
    `release_v1_1_smart` review batch into the Phase 4 Flask review app
  - Parallelised Team B + C4 outer loops via `OENOBENCH_AUDIT_MAX_WORKERS`
    (default 1 — sequential preserved; setting 8 brought B from ~25h
    sequential to ~3.5h)

  **Open decisions / next-session candidates:**
  - Phase 5 evaluation slate (16 configs × 3,329 Qs) ready to launch.
    Updated cost projection per the Phase 5 plan: standard ~$1700, with
    reasoning configs ~$2200. Stratified 1k subset ~$300.
  - Final paper datasheet generation
  - Submission packaging


- **Phase 2j release_v1.1 assembly (2026-05-03):** Combined three sources
  into the unified NeurIPS submission corpus tagged `release_v1.1`:

  1. **release_v1 cb_reserve promoted**: all 389 cb_reserve rows flipped to
     `draft` status via `promote-from-reserve --tag release_v1 --count 1000`.
  2. **release_v1 → release_v1.1 retagged**: all 2,650 release_v1 rows
     (now all draft) tagged with `release_v1.1`.
  3. **sample DB merged**: 1,062 sample.questions (curated quality-vetted
     set from Phase 5 work) tagged with `release_v1.1` in public.questions.
     Sample IDs are 100% subset of public.questions UUIDs — no row
     duplication, just additional tagging.
  4. **Embeddings**: 1,002 missing embeddings computed via `embed` command
     (1,425 total stored across DB, picked up some non-tagged stragglers).
  5. **Dedup pass** (cosine threshold 0.92, scoped to `release_v1.1` tag):
     - 56 duplicate pairs found pre-dedup
     - Sim distribution: 19 at ≥0.98 (near-identical), 13 at 0.95-0.98, 24 at 0.92-0.95
     - Top duplicates: exact-text repeats from FTQ (e.g. "Per the fact, the
       California wine region is situated in which country?" appearing 3×)
     - Resolution: untagged the higher-UUID side of each pair, preferring
       to keep sample-DB rows (quality-vetted) when one side was a sample row.
     - 42 questions untagged from release_v1.1 (34 release_v1 + 8 sample);
       0 pairs remaining above threshold after one pass (no transitive cycles).

  **release_v1.1 final state:**

  | Strategy | Total | from sample-DB | from release_v1 |
  |---|---:|---:|---:|
  | fact_to_question | 2,098 | 439 | 1,659 |
  | distractor_mining | 486 | 98 | 388 |
  | template | 433 | 183 | 250 |
  | scenario_synthesis | 345 | 195 | 150 |
  | comparative | 308 | 139 | 169 |
  | **TOTAL** | **3,670** | **1,054** | **2,616** |

  Per-domain: wine_regions 1,206, grape_varieties 935, producers 539,
  viticulture 525, wine_business 272, winemaking **193** (up from 91 in
  release_v1 — the sample DB contributed 102 winemaking questions).

  Per-difficulty: L1=1,379, L2=1,699, L3=265, L4=327.

  **All 3,670 questions are status=draft, tagged `release_v1.1`** in
  `public.questions`. The original `release_v1`, `audit_pilot_*`, and
  per-strategy tags are preserved on each row for provenance.



- **Phase 2j release_v1 — type-aware re-runs shipped (2026-05-03):** After
  the original build hit 2,146/6,500 with 91 scenario + 114 comparative
  questions, two targeted re-runs were dispatched via parallel agent teams:

  | Strategy | Before | After | Δ | Wall | Approach |
  |---|---:|---:|---:|---:|---|
  | scenario_synthesis | 91 | **150** | +59 | 36 min | type-aware prompt + DOMAIN_TO_SCENARIO_TYPES (commit `3fbe2d6`) |
  | comparative | 114 | **170** | +56 | ~3h (2 passes) | loose-pair sampler + DOMAIN_TO_COMPARISON_TYPES + softened cross-country skip (commit `e0fc429`) |

  Both used `--strategies <name>` + `--resume` to preserve existing rows.
  Stopped manually at user's direction during pass 3 of comparative
  (yields had collapsed to +4/pass — pass 1 was +51, pass 2 was +4).

  Final release_v1 corpus state:
  | Strategy | Draft | cb_reserve | Total |
  |---|---:|---:|---:|
  | fact_to_question | 1,292 | 389 | 1,681 |
  | distractor_mining | 389 | 0 | 389 |
  | template | 260 | 0 | 260 |
  | **comparative** | **170** | 0 | **170** |
  | **scenario_synthesis** | **150** | 0 | **150** |
  | **TOTAL** | **2,261** | **389** | **2,650** |

  Per-domain final (draft only):
  | Domain | Count | Plan share at 6,500 |
  |---|---:|---:|
  | wine_regions | 783 | ~2,275 (35%) |
  | grape_varieties | 546 | ~780 (12%) |
  | producers | 360 | ~520 (8%) |
  | viticulture | 300 | ~975 (15%) |
  | wine_business | 181 | ~650 (10%) |
  | winemaking | **91** | ~1,300 (20%) — STILL severely under |

  Key learning: the type-aware redesigns work as intended — the scenario
  question content is now appropriately distributed across personas
  (winemaker / viticulturist / sommelier / business / service) and the
  comparative loose-pair sampler unlocks new pair shapes. But the
  underlying **substantive-fact pool** (especially in winemaking and
  wine_business) is the binding ceiling. The original release_v1 build
  consumed most usable entity-tagged facts; even loose-fallback pair
  sampling yields 0 keeps for those small domains because the unused
  fact pool is exhausted.

  Code shipped during these re-runs (all on `main`):
  - Scenario:
    * `_prompts.py` — SCENARIO_TEMPLATE made type-aware with per-persona
      blocks; iconic-skip rule made type-conditional (strict for
      winemaking/viticulture, looser for tasting/business/service)
    * `orchestrator.py` — `DOMAIN_TO_SCENARIO_TYPES` map + cell-explosion
      in `_dispatch_llm_strategy` for scenario_synthesis (~50 cells/pass
      vs 30 legacy)
    * `--strategies` flag on `generate-all` for single-strategy re-runs
  - Comparative:
    * `_fact_sampler.py` — `sample_fact_pairs` rewritten with: entity-type
      whitelist 4 → 13 types, length floor 40 → 30, new cross-country
      same-subdomain JOIN arm, loose-fallback pass when strict
      candidates underflow, `_pair_strictness` telemetry
    * `_prompts.py` — COMPARATIVE_TEMPLATE softened (cross-country pairs
      allowed when fact-anchored on both sides); type-conditional
      iconic-skip mirroring scenario
    * `orchestrator.py` — `DOMAIN_TO_COMPARISON_TYPES` map + cell-explosion
      for comparative (~65 cells/pass vs 30 legacy); `_run_strategy`
      forwards `comparison_type` kwarg

  **Open decisions for next session:**
  - Accept the **2,650 release_v1 + 1,062 sample_v2** = 3,712 NeurIPS
    submission corpus
  - Or promote 389 cb_reserve via manual review → 2,650 + 389 = 3,039
    release-only (4,101 with sample DB)
  - Audit phase 2 NOT yet run on release_v1 — gated on user gold-sheet
    review and corpus-size decision
  - winemaking + wine_business expansion (new scrapers) remains the only
    path to materially more questions in those domains; multi-day lift
    not feasible before 2026-05-04 deadline

- **Phase 2j initial release_v1 build (2026-05-02 → 2026-05-03):** Original
  6,500-target run completed at **2,146 draft + 389 cb_reserve = 2,535
  questions**. Build
  hit a hard ceiling from the substantive-fact pool — multi-pass and tag-scoped
  count fixes maximised what could be extracted, but the underlying fact corpus
  cannot support 6,500 release questions without expansion.

  Per-strategy outcomes:
  | Strategy | Final draft | Target | Limit |
  |---|---:|---:|---|
  | fact_to_question | 1,292 (+389 cb_reserve) | 2,925 | sampler exhausted (passes 4-5 = 0) |
  | distractor_mining | 389 | 975 | producing through max_passes |
  | template | 260 | 650 | hit max_passes=8 cap |
  | comparative | 114 | 975 | entity-pair sampler exhausted |
  | scenario_synthesis | 91 | 975 | LLM cluster-coherence rejections |

  Per-domain (draft only):
  | Domain | Count | Plan share at 6,500 |
  |---|---:|---:|
  | wine_regions | 730 | ~2,275 (35%) |
  | grape_varieties | 508 | ~780 (12%) |
  | producers | 355 | ~520 (8%) |
  | viticulture | 281 | ~975 (15%) |
  | wine_business | 181 | ~650 (10%) |
  | winemaking | **91** | ~1,300 (20%) — SEVERE UNDER-REPRESENTATION |

  Three orchestrator bugs surfaced and were fixed mid-flight:
  1. `get_pg()` was `@lru_cache`'d → all 24 worker threads shared one psycopg2
     connection → killed 4 of 5 strategies in 4 min with `set_session cannot be
     used inside a transaction`. Fix: `threading.local()` per-thread connections
     (commit `49d13bc`).
  2. `generate-all` did single-pass dispatch → capped at 620/6,500 even after
     connection fix. Added outer multi-pass loop (commit `c5a4369`).
  3. `_count_by_method()` returned all-DB counts (incl. ~3,710 audit-pilot rows)
     → orchestrator's "remaining" math underestimated by ~3,000. Added `tag`
     parameter (commit `a300e54`).
  4. Outer multi-pass blocked 4 strategies on FTQ pass barrier (FTQ ran 2.2h on
     pass 1 while others sat idle 90+ min). Refactored to per-strategy
     multi-pass inside `_run_one_strategy` (commit `e088fa5`).

  Artefacts:
  - DB: 2,535 rows tagged `release_v1` in `public.questions`
  - Gold sheet: `data/reports/gold_sheet_release_v1.csv` (stratified sample for
    human review)
  - Build logs: `data/logs/release_v1_build_*.log` (4 logs across 4 launches)
  - Monitor CSV: `data/logs/release_v1_monitor.csv` (33 5-min snapshots tracking
    Q/min, per-strategy progress, alive flag, ETA projection)
  - Wrapper script: `scripts/run_release_v1_build.sh` (idempotent, auto-resume)
  - Monitor script: `scripts/monitor_release_v1.py` (overnight metrics)

  **Open decisions (next session):**
  - Accept ~2,150 corpus + sample-DB 1,062 (Phase 5) as the NeurIPS submission
  - Or promote 389 cb_reserve via manual review → ~2,540
  - Or expand the fact pool (especially winemaking + wine_business) — ~1-3 day
    lift but unblocks 500-1,000 more release questions
  - Or loosen filters (substantive, ubiquity, scenario coherence) and re-run —
    risks quality regressions
  - Audit phase 2 NOT yet run on release_v1 — gated on user gold-sheet review
    and corpus-size decision


- **Phase 5 sample-DB eval shipped (2026-05-02):** 16-config slate
  evaluated against the 1062-Q `sample` schema corpus. Tag
  `eval_sample_v2`, run_id `6ef6eff2-9c50-439c-8aff-b414300727fc`. 28m
  wall, ~$31 spend, 16,572 LLM calls. **15/16 configs at full 1062
  coverage**; slot 15 (DeepSeek R1) at 683/1062 because R1's provider
  throttled to ~5/min after ~600 calls (a follow-up `--resume --configs
  15` is in progress to fill the tail). Headline leaderboard top 4 all
  reasoning configs: Gemini 2.5 Pro thinking 83.6%, Claude Opus 4.7
  thinking 81.6%, o3 81.5%, Claude Opus 4.7 standard 80.9%. Reasoning
  effect strongest for **Gemini Pro (+5.5pp)** and **DeepSeek (+6.7pp,
  partial)**, smallest for **Claude Opus (+0.7pp)**. Within-family
  cost-tier delta largest for **Anthropic (-24.4pp Opus→Haiku)** —
  driven by Haiku's high skip rate (191/1062), not capability —
  smallest for **OpenAI/Google (~1-2pp)**. Full report at
  `data/reports/eval_sample_v2.md`. Implementation built in ~3h via 4
  parallel Agent Teams (A-foundation, B-client, C-harness, D-report)
  per the `~/.claude/plans/snoopy-dancing-deer.md` plan; six iterations
  needed during the first live run to fix `max_tokens` cap (5→16→100→1000→2000),
  provider name strings (DeepSeek/Alibaba/Together → DeepInfra/Novita/etc.),
  and the override_system kwarg integration between Teams B and C. All
  fixes shipped on `main` (commits `4f98975, c60e334, c12e69c, 574aaa9,
  500782a, 88f3190` plus integration commits).

- **Phase 5 evaluation slate locked (2026-05-02):** 16 configurations
  across 14 unique OpenRouter IDs, covering all 4 SPS generator
  families (Claude / GPT / Gemini / Llama), six within-family
  cost pairs, four reasoning configs (`openai/o3`,
  `deepseek/deepseek-r1`, plus `claude-opus-4.7` and `gemini-2.5-pro`
  with reasoning param on — neither has a separate `:thinking` SKU on
  OR). User constraints: **single-letter output (A/B/C/D)** with
  `max_tokens=5` + system prompt + stop sequences + logit_bias
  fallback; **fully parallel execution** with ~320 aggregate
  in-flight requests. Cost projections: **~$541 full / ~$147 stratified**
  (5k standard + 1k reasoning); standard block dominated by Claude
  Opus 4.7 (~$20.6); reasoning block dominated by Claude Opus thinking
  (~$270). Wall-time projection: ~55 min full / 12–15 min stratified.
  Plan at `docs/EVALUATION_PLAN.md`; pricing verified live on OR via
  `/api/v1/models` snapshot 2026-05-02. Open decisions: full vs
  stratified reasoning (user leaning stratified, awaiting Phase 3
  power calc); whether to add `openai/gpt-5-pro` as a stretch entry
  (~15× cost of `o3`).

- **Sample preview DB shipped (2026-05-02):** Curated quality-vetted set
  of **1062 questions** assembled into a new `sample` schema in the
  `winebench` Postgres DB (alongside `public`). Filters: `status=draft`
  + has audit findings + no FAIL on A1/A3/B1/C2 + excludes pre-gate
  pilots v1-v4. cb-tagged INCLUDED (538/1062 = 51%). Sources: 10 pilots
  (v5-v16, audited only). Mirrored tables: questions, facts, sources,
  question_facts, question_sources, generation_metadata, audit_runs,
  audit_findings, plus a `sample.manifest` row recording assembly
  metadata. Migration script at
  `config/postgres/003_sample_schema.sql` is idempotent (DROP + recreate).
  Strategy mix: FTQ 439, scenario 195, template 191, comparative 139,
  distractor 98. Domain mix: grape_varieties 312, wine_regions 223,
  viticulture 174, producers 165, winemaking 102, wine_business 86.
  624/624 tests pass.

- **Phase 2g.18 v16/v16b smoke validation (2026-05-02):** 4 parallel teams
  shipped 9 levers; 2 followups (path C) added confidence-field plumbing
  and comparative substantive filter. Three pilots completed:

  | Pilot | Tag | Per-strat | Kept | LLM calls | Build $ | $/Q |
  |---|---|---:|---:|---:|---:|---:|
  | v9 baseline | `audit_pilot_v9` | 20 | 46 | 772 | ~$7 | $0.152 |
  | v16 smoke | `audit_pilot_v16` | 15 | 27 | 139 | $1.40 | $0.052 |
  | **v16b smoke** | `audit_pilot_v16b` | 30 | **60** | 306 | **$2.02** | **$0.034** |

  Audit phase A on v16: 27 Qs / 294 calls / **$0.48** = $0.018/Q (v16
  vs v15_ubiq's $0.017/Q). At 10k scale audit projects to **~$170**
  (vs $340 baseline) = **50% audit reduction validated**. Build at 10k:
  $0.034 × 10000 = **~$337** vs ~$700 baseline = **52% build reduction**.
  Combined 10k projection: **~$507** vs $9/100 = $900 baseline =
  **44% reduction** (close to but slightly under the 50% target on this
  baseline; ~73% on the v9-extrapolated baseline). Verifier-skip B5
  fired 17 times (37% skip rate) on v16b after path C added the
  `confidence` field to generator JSON schema. Comparative yield 0/15
  → 5/30 (path C substantive filter). All 624/624 tests pass.

  **Files:** plan `/home/winebench/.claude/plans/virtual-snacking-anchor.md`;
  scripts `scripts/run_audit_pilot_v16_{build,audit}.sh`; commits
  `aee4af1, f5298b5, 667bd8a, c3d3565, 218e662`.

  **Next:** kick off the full 10k build with the v16 env profile
  (per_strategy left to default; total target = 10000) on user approval.
  Estimated wall: 6-12h. Audit follows; total cost projection ~$507.

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
| 4. Human Review & Control Set | 18-20 | **In progress** — review web app shipped 2026-05-03 (Flask, port 5556). Import + launch: `python -m src.review_app.import_batch --csv data/reports/gold_sheet_release_v1.csv --name release_v1_pilot && REVIEW_APP_USER=admin REVIEW_APP_PASSWORD=... python -m src.review_app.app` then share `http://<vm>:5556/`. |
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
