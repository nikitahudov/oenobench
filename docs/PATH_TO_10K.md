# Path to the Full 10k Generation

**Generated:** 2026-04-20 · **Updated:** 2026-04-22 (Phase D sign-off done → v2.3 added)
**Status:** Phase C audit #3 + Phase D gold-v3 sign-off complete → **2 of 14 gates still failing → v2.3 iteration required before Phase E.**
**Pre-reads:** `docs/GENERATION_IMPROVEMENT_PLAN.md`, `docs/QUALITY_AUDIT_REPORT.md` (audit_pilot_v3 + 119-row gold κ), `data/reports/gold_sheet_v3_scored.csv` (59/60 scored).

This document is the single source of truth for the work between today and the production 10,000-question generation run. Phases A–E (v2.2) followed by Phase F (v2.3) target the two remaining blockers plus two user-flagged quality concerns: template pattern-monopoly and Gemini reallocation.

---

## Gold-v2 headline findings (informs Phase B)

48/48 questions scored. Overall clean-pass (all 8 rubrics) = 45.8%. Excluding difficulty_match (calibration fails dominate) = 75%.

| Strategy | 7-rubric clean | 8-rubric clean | Hard fails |
|---|---|---|---|
| **template** | **33%** (4/12) | 0% | 3 catastrophic wrong-key, 2 category-leak distractors, 3 identity-template `needs_source` fails |
| comparative | 83% (10/12) | 75% | 1 chatgpt catastrophic (WB-GRP-0121-L2) |
| fact_to_question | 92% (11/12) | 42% | 1 chatgpt ambiguous; most fails are difficulty calibration |
| scenario_synthesis | 92% (11/12) | 67% | only 1 needs_source fail |

Per-generator answer_correct: claude/qwen/llama/gemini = 100%; **chatgpt = 88%; template = 75%**. Difficulty bias is systematic: 10 of 15 directional miscalibrations are labeled-too-easy-by-1 level.

→ Phase B additions below (fixes #8–#11).

---

## Phase A · Gold re-grade (parallel — blocks D, not B)

Domain expert grades `data/reports/gold_sheet_v2.csv` (48 questions × 8 rubrics).

**Critical change vs gold v1:** column 11 is now `source_facts` and contains ALL linked facts joined with `[1]/[2]/[3]` prefixes. Multi-fact strategies (comparative / scenario / distractor) can finally be judged against complete evidence — fix #4 from the v2.1 plan.

When complete:
```
git add data/reports/gold_sheet_v2_scored.csv && git push
# Then on this side:
python -m src.qa.orchestrator import-gold --csv-path data/reports/gold_sheet_v2_scored.csv --reviewer nikita
python -m src.qa.orchestrator build-reports --run-id 3c6e27ce-62fa-4c1b-bd0e-3958161a0082
```

This refreshes `docs/QUALITY_AUDIT_REPORT_V2.md` §6 Gold Calibration with κ for **all 5 audited rubrics** (vs run #1's `answer_correct`-only). Any rubric where κ ≥ 0.6 becomes a trustworthy LLM-judge gate; rubrics where κ < 0.6 stay downweighted.

**Cost:** $0. **Time:** ~2 h human, otherwise unblocked work.

---

## Phase B · v2.2 fixes (start immediately, parallel with A)

Six focused fixes, partitionable across 3 worktree teams (or sequential ~3 days).

| # | Fix | File(s) | Effort | Owner team |
|---|---|---|---|---|
| 1 | **A4** — turn on §6.3e LLM-paraphrase post-pass by default for templates (drop `--paraphrase` flag, make it the default) | `src/generators/template_generator.py` | S | Generator |
| 2 | **B2** — change FAIL threshold from "ALL 5 solve" to "≥4 of 5 solve" at L≤2; recompute warn band; bump `B2_VERSION` to `v3.0.0` | `src/qa/agents/team_b_validity.py` | S | Audit |
| 3 | **D3** — tighten hard country cap from 1.5× → 1.2× of base share | `src/generators/_fact_sampler.py` | S | Sampler |
| 4 | **A1 calibration** — read `data/reports/gold_sheet_scored.csv` rows where `no_vague_language=1` BUT v2 audit flagged the question as A1 fail/warn (false positives); identify which new patterns from gold v1 over-fire and remove them | `src/generators/_fact_sampler.py` (`_VAGUE_PATTERNS`) | S | Sampler |
| 5 | **C4 generation-time** — promote C4 from audit-only into the generator pipeline. After every LLM-generated question, ONE Gemini difficulty rating; if rating differs ≥2 levels from labelled, reject & resample. Reuse `src/qa/agents/team_c_probes._c4_call_llm`. | `src/generators/_schemas.py` (post-LLM step), wire kwargs through 4 LLM strategy modules | M | Generator |
| 6 | **β-2 walk-back** — relax wine_category filter on `sample_fact_clusters`: only require ≥75% of cluster facts to share category, not 100%. Was the cause of scenario throughput crashing in v2 corpus build. | `src/generators/_fact_sampler.py` | S | Sampler |
| 7 | **C2 manual triage** (after #4 lands) — inspect the 3 remaining C2 fails in `audit_pilot_v2`; add a regex case if a pattern emerges | manual SQL + `_fact_sampler.py` | S | Sampler |
| 8 | **Template strategy radical overhaul** (gold-v2: 0/12 clean-pass all-8, 3 catastrophic wrong-key) — see §B.8 below | `template_generator.py`, `_schemas.py`, new `_template_validators.py` | L | Template |
| 9 | **ChatGPT-comparative prompt fix** (gold-v2: 1 catastrophic + 2 ambiguous from chatgpt comparative; other generators clean) | `_prompts.py` (comparative chatgpt branch) | S | Audit |
| 10 | **Difficulty classifier recalibration from gold-v2** — 10 of 15 directional miscalibrations are labeled-too-easy-by-1. Fold the 19 gold difficulty_match fails into C4's calibration set & bump prompt. | `team_c_probes.py::_c4_call_llm`, add calibration examples | S | Audit |
| 11 | **FTQ `needs_source` gate for iconic entities** (gold-v2: WB-BIZ-0095-L2 world-knowledge-solvable FTQ slipped through) — pre-generation filter rejecting top-K famous brand / UNESCO wine sites when they are the sole entity | `_fact_sampler.py` | S | Sampler |

### Recommended team partition (4 parallel worktrees)

- **Generator team** — fixes 1, 5. Owns `template_generator.py` (paraphrase default), `_schemas.py`, the 4 LLM strategy modules (C4 generation-time gate).
- **Audit team** — fixes 2, 9, 10. Owns `src/qa/agents/team_b_validity.py` (B2 threshold), `_prompts.py` comparative branch, `team_c_probes.py` (C4 calibration).
- **Sampler team** — fixes 3, 4, 6, 7, 11. Owns `src/generators/_fact_sampler.py`.
- **Template team** — fix 8 exclusively. Owns template inventory audit, `_template_validators.py` (new), distractor pool hardening, per-template difficulty table, mandatory Gemini verifier. Fix scope is large enough to justify its own worktree.

Same parallel-worktree pattern as v2.1 (see `docs/IMPLEMENTATION_AGENT_ARCHITECTURE.md`). All 26+ existing tests must stay green; each fix adds 1-2 unit tests.

**Cost:** ~$1-5 for Gemini template-verifier dry-run in fix #8; otherwise code only. **Wall-clock:** ~2 days parallel, ~4 days sequential.

### §B.8 — Template radical overhaul spec

Gold-v2 showed 5 root causes:

- **R1** — Superlative-attribution templates ("most strongly associated with", "flagship grape of") can't be proven from a single fact → produced 3 catastrophic wrong-key questions.
- **R2** — Identity templates ("Which country is X in?") on well-known entities fail `needs_source` (world-knowledge solvable).
- **R3** — Distractor pools category-contaminated: "In which wine region is Force Majeure Vineyards?" got `{Georgian wine, Canadian wine, Italian wine}` as distractors (all country-level concepts tagged as `region`).
- **R4** — Correct answer not literally supported by the linked source fact ("Kamptal is in Austria" anchored to "Riesling is grown in Kamptal region of Austria").
- **R5** — Difficulty heuristic ignores the template: γ-3 uses only entity-mention count.

Five sub-fixes, all in the Template-team worktree:

| Sub | What | Effort |
|---|---|---|
| **8a** | Template inventory audit & purge — delete all superlative/unverifiable templates (~8), delete well-known identity templates (~5), rewrite survivors into authorised-list phrasing. Target ~35-40 templates, all `requires_fact_specific=True` + new `verifiable_from_single_fact=True` metadata. | S |
| **8b** | `_template_validators.verify_answer_in_source_fact`: require `correct_answer_text` to appear (normalized) as a substring of the linked source fact. Alias list in `data/aliases.yaml` for known equivalences (US↔United States, UK↔Britain, etc). Wired into `fill_template()`. | M |
| **8c** | Distractor pool strict type-gating: (1) hardcoded field→entity_type whitelist, (2) homogeneity check (token-count + shape), (3) static countries sentinel (~200 names) banned from `region`/`appellation` pools, (4) minimum pool size 20 (was 8). | M |
| **8d** | Per-template difficulty calibration table keyed by `(template_id, mention_band)`, seeded from all 19 gold-v2 difficulty_match fails. γ-3 heuristic stays as fallback for unlisted combinations. | M |
| **8e** | Mandatory Gemini answer-verification on every template question before insert — adapt `_verify.py` to a template-specific prompt: *"Given the source fact, question, and options — which option is most directly supported?"* Reject on disagreement. At 1000 templates × ~$0.001 = ~$1. | M |

Regression test: `tests/generators/test_template_radical.py` — each of the 12 gold-v2 template questions must either be rejected or produce the corrected answer. Dry-run 100 templates, human spot-check 20, clean-pass ≥70%.

Gate for Phase C audit run #3 (new): template `answer_correct ≥ 95%` on 30-Q human spot-check AND template 7-rubric clean-pass `≥ 70%`.

---

## Phase C · Audit run #3 (~6h, ~$10)

```bash
# 1. Build pilot v3 corpus — should now reach the full 600 thanks to #6 walk-back
python -m src.qa.orchestrator build-corpus --tag audit_pilot_v3 --per-strategy 120

# 2. Run all teams (A static + C+C4 + D + B)
python -m src.qa.orchestrator run --tag audit_pilot_v3 --teams A,B,C,D

# 3. Render reports + export multi-fact gold sheet for spot-check
python -m src.qa.orchestrator build-reports --run-id <new_uuid>
python -m src.qa.orchestrator export-gold --tag audit_pilot_v3 --size 60 --out data/reports/gold_sheet_v3.csv
```

Expected outcomes per fix:
- A4 AUC drops from 0.96 → < 0.80 (fix #1)
- B2 fail rate drops from 38% → 10-15% (fix #2)
- D3 ratio drops from 3.38× → < 1.5× (fix #3)
- A1 fail rate drops from 4.8% → < 2% (fix #4)
- C4 fail rate drops from 36% → < 10% in audit, because generation-time gate rejects mismatches before they reach the audit (fix #5)
- Scenario_synthesis hits ~110-120 of 120 target instead of stopping at 51 (fix #6)
- **Template answer_correct rises from 75% → ≥ 95%** on a 30-Q spot-check (fix #8)
- **Template 7-rubric clean-pass rises from 33% → ≥ 70%** (fix #8)
- **ChatGPT answer_correct ≥ 95%** across comparative/FTQ/scenario (fix #9)
- **Difficulty-match audit rate ≥ 80%** (from ~60% in gold-v2) (fix #10)

**Cost:** ~$5 corpus + ~$10 audit + ~$1 template verifier dry-run = **~$16**. **Wall-clock:** ~6h overnight.

---

## Phase D · Sign-off (~1h)

Verify ALL gates from the Go/No-Go checklist in `docs/GENERATION_IMPROVEMENT_PLAN.md` pass on run #3:

- [ ] **Per-generator answer_correct ≥ 95%** on a fresh 30-question human spot-check (gold-cal gate, confirmed critical by gold-v2 chatgpt & template outliers)
- [ ] **Template-specific answer_correct ≥ 95%** on a 30-Q template-only spot-check (NEW gate from gold-v2 fix #8)
- [ ] **Template 7-rubric clean-pass ≥ 70%** on the same spot-check (NEW, gold-v2 baseline was 33%)
- [ ] A1 fail rate < 1%
- [ ] A2 position-bias p > 0.2 in every (strategy, generator) cell with n ≥ 20
- [ ] A3 fail rate < 2% on single-fact strategies
- [ ] A4 held-out AUC < 0.85
- [ ] B1 majority-matches-key ≥ 95% AND human spot-check confirms
- [ ] B2 closed-book leakage < 15%
- [ ] C2 category-leak fail count = 0
- [ ] D1 self-preference |Δ| < 0.07 across all 5 evaluator models
- [ ] D3 max country over-representation ratio < 1.5
- [ ] difficulty_match ≥ 80% on human spot-check (gold-v2 baseline ~60%, target raised via fix #10)
- [ ] distractor_plausibility ≥ 75% on human spot-check (esp. templates — fix #8c is the primary lever)

If any gate fails: bounded v2.3 iteration on just that defect (~1 day each), then re-run a TARGETED audit (just the failing agent on a 200-Q sample, $2-3) before retrying the gate.

**Cost:** $0–$5 for any iteration. **Wall-clock:** 1h sign-off + iteration days if needed.

---

## Phase E · Full 10k generation (~12h overnight, ~$90)

```bash
# 1. Pre-flight: confirm STRATEGY_TARGETS + GENERATOR_TARGETS in orchestrator.py
# match the v2.1 allocation (Claude/ChatGPT/Gemini @ 2400 each, Qwen 1100,
# Llama 700, template 1000) and that all v2.1 + v2.2 quality gates are active.

# 2. Fire it
python -m src.generators.orchestrator generate-all --resume

# 3. Post-run: deduplication pass (already-built infrastructure)
python -m src.generators.orchestrator dedup --threshold 0.92

# 4. Production audit (sampled 600-Q from the 10k delivered corpus)
python -m src.qa.orchestrator build-corpus --tag audit_full_v1 --from-existing  # tag a stratified sample
python -m src.qa.orchestrator run --tag audit_full_v1 --teams A,B,C,D
python -m src.qa.orchestrator build-reports --run-id <uuid>
```

Active quality gates during the run:
- A3 paraphrase guard (post-LLM LCS ≤ 0.6 reject)
- Llama/Qwen post-LLM independent-solver verifier (rejects wrong-key questions)
- Per-country sampling quota (1.2× hard cap)
- C4 generation-time difficulty re-classifier (rejects ≥2-level mismatches)
- Universal wine-category filter on all distractor sampling
- A1 vague-phrase rejector (calibrated post-fix #4)
- LLM-paraphrased templates (A4 detectability mitigation)
- A2 length normaliser (post-LLM ±20% adjustment)

Per-question budget includes verifier retries: ~$0.005-0.015 average. **Total: ~$80-90.**

If post-run audit (`audit_full_v1`) hits all gates → ship the dataset. If any gate fails on the production corpus, rebuild only the bad cell (e.g. one strategy×generator combo) — the orchestrator's `--resume` flag handles this.

---

## Total runway

| Phase | Wall-clock | Human time | Cost |
|---|---|---|---|
| A · gold re-grade ✅ (done 2026-04-20) | — | ~2h | $0 |
| B · v2.2 fixes (4 parallel teams inc. Template) | ~2 days | minimal | ~$1 (template verifier dry-run) |
| C · audit run #3 | ~6h (overnight) | minimal | ~$16 |
| D · sign-off + any v2.3 iteration | ~1h-1d | ~30 min review | $0-5 |
| E · full 10k + dedup + post-audit | ~12h (overnight) | minimal | ~$90 |
| **TOTAL** | **~3-4 days** | **~3h** | **~$107-112** |

NeurIPS deadline: May 15. Comfortable margin (3+ weeks).

---

## Risk register

| Risk | Mitigation |
|---|---|
| C4 generation-time gate rejects too many questions, throughput drops | Tune the rejection threshold from "≥2 levels off" to "≥3 levels off" if fail rate balloons during pilot v3 |
| LLM-paraphrase post-pass on templates introduces new errors (wrong answer text changes meaning) | The validator already requires entity names to survive paraphrase; if rejection rate > 30%, fall back to template phrasing diversification only |
| B2 ≥4 of 5 threshold turns out also too strict OR too loose | Inspect distribution of `judges_keyed/judges_total` from run #3 and pick the threshold that aligns with the human gold's 12% leakage rate |
| Scenario_synthesis still slow even with β-6 walk-back | Drop scenario quota from 1500 → 1000 and increase fact_to_question to 5000 |
| 10k production run fails midway | Orchestrator already has `--resume`; finished cells stay, partial cells re-fire |
| Cost overrun beyond $110 | Hard cap: monitor `audit_runs.total_cost_usd` after each phase; if > $80 after Phase C, audit the verifier cost ledger |

---

## Execution status (2026-04-22)

- **Phase A — done** (2026-04-20). Gold v2 merged; v2.2 fixes 8–11 derived.
- **Phase B — done** (2026-04-20→21). All 4 worktree teams shipped: fixes #1–#11 merged. Commits 547086e, 60490ae, 0078371, 64130f8, d352871.
- **Phase C — done** (2026-04-21, run `0bfe85dc-…`, 331 Qs, $8.51). Most v2.2 expected outcomes hit: C4 fail rate 36% → 3.6%, C2 fails 3 → 0, A3 fails 35% → 4.8%. B2 fails stayed at 66% (threshold recalibration less effective than hoped), A4 AUC unsampled (only 1 template survived filter).
- **Phase D — done** (2026-04-22, this update). Gold v3 (`gold_sheet_v3_scored.csv`, 59 rows) imported and κ recomputed across 119 combined labels. Per-generator and per-template analysis below (§D.1–D.3).
- **Phase E — BLOCKED** on 2 hard gates + 2 user-flagged quality concerns → v2.3.

---

## Phase D · Gold-v3 sign-off (findings, 2026-04-22)

### D.1 · Gate status after run #3 + gold v3

| Gate | Target | Observed | Status |
|---|---|---|---|
| Per-generator `answer_correct` ≥ 95% (human) | 95% | chatgpt 100%, claude 100%, qwen 100%, **gemini 88%, llama 89%, template 75%** | ✗ (3 cells) |
| Template-specific `answer_correct` ≥ 95% | 95% | **75% (9/12)** — 3 catastrophic still come from broken source facts | ✗ |
| Template 7-rubric clean-pass ≥ 70% | 70% | 58% (7/12) perfect 8/8; 75% if `difficulty_match` excluded | ✗ |
| Overall perfect 8/8 rate | — | **66.1%** (39/59) — up from 45.8% in gold v2 | — |
| A1 fail rate < 1% | <1% | 4.8% | ✗ |
| A3 fail rate < 2% (single-fact) | <2% | 4.8% overall; 50% on template strategy alone | marginal ✗ |
| A4 AUC < 0.85 | <0.85 | unsampled (n=1 template post-filter) | ⚠ |
| B1 majority-matches-key ≥ 95% | 95% | 91.8% audit; 91.5% human | ✗ |
| B2 leakage < 15% | <15% | 66% | ✗ (threshold recalibration debated) |
| C2 category-leak fail count = 0 | 0 | 0 | ✓ |
| D1 self-pref \|Δ\| < 0.07 | <0.07 | 0.06 (ChatGPT) warn | ~✓ |
| D3 max country ratio < 1.5 | <1.5 | 3.14× (South Africa) | ✗ |
| `difficulty_match` ≥ 80% (human) | 80% | **69%** — biggest single rubric weakness | ✗ |
| `distractor_plausibility` ≥ 75% | 75% | 90% | ✓ |

**Hard blockers for Phase E: template correctness (75%), difficulty calibration (69%), country skew (D3), B2 leakage.** B2's gate deserves reconsideration because human κ shows LLM-judge needs_source signal is noise (§D.2).

### D.2 · LLM-judge ↔ human κ on 119 combined gold rows

| Rubric | Agent | human pass% | LLM pass% | agreement | κ |
|---|---|---:|---:|---:|---:|
| `answer_correct` | B1_TriJudgeAnswer | 91.5% | 94.9% | 93.2% | **0.466** |
| `distractors_plausible` | C2_CategoryLeak | 89.8% | 94.9% | 88.1% | 0.166 |
| `source_faithful` | A3_FactEcho | 93.2% | 88.1% | 88.1% | 0.304 |
| `no_vague_language` | A1_LexicalHygiene | 89.8% | 89.8% | 79.7% | -0.113 |
| `needs_source` | B2_ClosedBookSolvability | 93.2% | 18.6% | 15.3% | **-0.099** |

Only B1 carries a usable signal (κ ≈ 0.47, approaching but still below the 0.6 gate). **B2 is actively misleading** — it flags 75% of human-acceptable questions as failures. Every other LLM-judge signal must be treated as noisy proxy, not a gate.

**Implications for Phase E sign-off:** hard gates trigger on human spot-check (not LLM-judge). LLM-judge agents stay for triage / broad signal only. The B2 ≥15% leakage gate is **dropped** in v2.3 and replaced with a tighter human sample during production audit.

### D.3 · Per-generator and per-strategy pass rates

From audit_pilot_v3 (331 Qs, all 6 question-level agents):

| Generator | Avg pass rate | A1 | A3 FactEcho | B1 | B2 | C2 | C4 |
|---|---:|---:|---:|---:|---:|---:|---:|
| **gemini** | **70.5%** | 93 | **81** | 93 | 23 | 96 | 37 |
| chatgpt | 66.7 | 95 | 55 | 97 | 11 | 100 | 42 |
| claude | 66.7 | 90 | 51 | 93 | 29 | 100 | 37 |
| llama | 64.4 | 98 | 38 | 92 | 25 | 97 | 35 |
| qwen | 63.3 | 79 | 60 | 89 | 20 | 96 | 37 |
| template_only | 63.1 | 100 | 14 | 71 | 43 | 100 | 50 |

**Gemini is the overall pass-rate leader, decisively dominant on A3 FactEcho (81% vs 60% next).** Human gold-v3 corroborates: Gemini 75% perfect-8/8 (matching Llama, beating Claude/ChatGPT at 67%) with avg 7.50/8. → Reallocation rationale in §13 of the improvement plan.

By strategy (pass rate avg across 6 agents):

| Strategy | Pass% | Top weakness |
|---|---:|---|
| distractor_mining | 70.3 | — |
| comparative | 65.5 | B2 (32%), C4 (37%) |
| fact_to_question | 65.4 | B2 (9%), C4 (35%) |
| template | 63.1 | A3 (14%), B1 (71%) |
| scenario_synthesis | 62.3 | B2 (12%), A3 (46%) |

### D.4 · User-flagged findings

**Template pattern-monopoly** (user observation 2026-04-22 — confirmed):

- 107 template questions in DB, but only **11 distinct `template_id`s** fire — registry has 38.
- Dominant template `T-PRD-TF-REGION-01` accounts for **30/107 (28%)** of all templates; its 3 paraphrase variants occupied all 12 gold-v3 template slots (100% of the sample was one pattern).
- All 107 templates carry `cognitive_dim=recall`; registry defines 5 `comprehension` templates that never fire.
- ~32 of 107 templates use `template_id`s that v2.2 fix #8a marked for deletion (`T-REG-COUNTRY-01`, `T-GRP-REGION-01`, `T-GRP-ORIGIN-01`) but were never purged from DB.
- **14 templates were generated from 43 corrupt Bordeaux "classified estate in Château X" source facts** (the Bordeaux scraper misread classified-list table columns). This is what produced the 3 "Completely incorrect: Chateau name used as region" human fails.

**Gemini performance** (user observation 2026-04-22 — confirmed):

See §D.3. Gemini leads overall quality metrics and is dominant on the highest-priority post-v2.1 defect (A3 FactEcho). Reallocation shipped to `orchestrator.py` in this commit; details in GENERATION_IMPROVEMENT_PLAN.md §13.

---

## Phase F · v2.3 fixes (before Phase E 10k run)

Six fixes, partitionable across 3 worktree teams. All address Phase D blockers.

| # | Fix | File(s) | Effort | Owner team |
|---|---|---|---|---|
| 12 | **Gemini allocation bump** (2400 → 2800) balanced from qwen (1100 → 800) and llama (700 → 600). Already shipped in this commit's orchestrator edit. | `src/generators/orchestrator.py` | S ✅ | — |
| 13 | **Template diversity cap** — hard cap any single `template_id` at 15% of template strategy output; `T-PRD-TF-REGION-01` currently holds 28%. Add to `fill_template()` selection loop a running counter keyed on `template_id`; when cap hit, skip and resample a different template. Increase minimum distinct-template-id floor to 20 (vs observed 11). | `template_generator.py` | S | Template |
| 14 | **Legacy template purge + Bordeaux fact scrub** — (a) DELETE templates with `template_id IN ('T-REG-COUNTRY-01','T-GRP-REGION-01','T-GRP-ORIGIN-01','T-REG-GRAPE-01')` from questions (n≈32). (b) DELETE the 43 broken `'... classified Bordeaux estate in Château ...'` and `'%align=%'`/`'%&nbsp;%'` facts, and the ~14 template questions derived from them. (c) Patch `src/scrapers/bordeaux.py` table-cell parser so it never re-creates these facts. (d) Re-run `bordeaux.py --all` to backfill correctly-parsed data. | `bordeaux.py`, ad-hoc SQL | M | Sampler |
| 15 | **Template registry expansion — comprehension / application tier** — add 10–12 new templates at `cognitive_dim=comprehension` (requires inference from fact, not entity recall) and 4–5 at `cognitive_dim=application` (requires applying fact rule to novel scenario). Seed from facts whose `entities` JSONB has multiple non-name fields (soil+climate, aging+vessel, etc.). Target 50+ registered templates, ≥25 firing. | `template_generator.py` TEMPLATES | M | Template |
| 16 | **Difficulty re-calibration pass #2** — gold v3 showed 18 directional difficulty fails (15 labelled-too-easy-by-1). Fold these into `_c4_call_llm` calibration few-shot and tighten threshold: reject generation on ≥1-level mismatch at L3/L4 (was ≥2); keep ≥2 at L1/L2 to preserve throughput. | `team_c_probes.py` | S | Audit |
| 17 | **D3 hard-cap enforcement pass** — v2.2 set the cap to 1.2× but run #3 still showed 3.14× for South Africa. Investigate whether the cap is (a) not being consulted, (b) being consulted after over-sampling already happened, or (c) South Africa is genuinely a multi-country entity category. Fix the detected failure mode. | `_fact_sampler.py` | S | Sampler |
| 18 | **B2 gate retirement** — drop the "B2 leakage < 15%" gate from Phase E Go/No-Go. Keep B2 as a ranked defect signal only (warn threshold) since κ = -0.10 with humans. Add a compensating human gate: **needs_source ≥ 85% on a 30-Q production spot-check**. | `docs/PATH_TO_10K.md` §Phase E | S ✅ | this commit |

### Recommended team partition (3 parallel worktrees)

- **Template team** — fixes 13, 14 (a,b), 15. Owns `template_generator.py` inventory + cap logic.
- **Sampler team** — fixes 14 (c,d), 17. Owns `bordeaux.py` fact-parser fix + D3 cap enforcement.
- **Audit team** — fix 16. Owns `team_c_probes.py` C4 calibration.

Fixes 12 and 18 are already applied in this commit.

**Wall-clock:** ~2 days parallel, ~4 days sequential. **Cost:** ~$2 (Bordeaux rescrape + Gemini difficulty re-calibration dry-run).

### Phase F verification

Re-run `build-corpus --tag audit_pilot_v4 --per-strategy 120` + `run --teams A,B,C,D` + `export-gold --size 60 --out gold_sheet_v4.csv`. Expected outcomes:

- Template questions: `answer_correct` ≥ 95% (v2.3 target)
- Template diversity: HHI on `template_id` < 0.10 (run #3 was ~0.13); ≥25 distinct templates fire; no single pattern > 15% share
- No question references any corrupt Bordeaux "estate in Château" fact
- `difficulty_match` (human) ≥ 80%
- D3 max country ratio < 1.5×
- Gemini share of corpus ≈ 28–31%

Human spot-check: 30 Qs per strategy → sign off Phase E.

---
