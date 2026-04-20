# Path to the Full 10k Generation

**Generated:** 2026-04-20
**Status:** v2.2 plan, immediately follows audit run #2 (`3c6e27ce-…`) and gold-v2 re-grade (48/48 scored).
**Pre-reads:** `docs/GENERATION_IMPROVEMENT_PLAN.md` (v2.1), `docs/AUDIT_RUN_2_COMPARISON.md` (what worked / what didn't), `data/reports/gold_sheet_v2_scored.csv` (human gold, 48 questions × 8 rubrics).

This document is the single source of truth for the work between today and the production 10,000-question generation run. Five phases (A–E), ~3-4 days wall-clock, ~$105 cost, ~3 hours human time.

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

## Execution status (2026-04-20)

- **Phase A — done.** `gold_sheet_v2_scored.csv` merged; human findings folded into fixes #8–#11.
- **Phase B — in flight.** 4 parallel worktree teams spawned simultaneously:
  - **Template team** (fix #8) — radical overhaul, ~2-day task
  - **Generator team** (fixes #1, #5) — paraphrase default + C4 generation-time gate
  - **Audit team** (fixes #2, #9, #10) — B2 threshold + ChatGPT comparative prompt fix + C4 calibration
  - **Sampler team** (fixes #3, #4, #6, #7, #11) — D3 cap, A1 calibration, β-2 walk-back, C2 triage, FTQ iconic-entity filter

Phase C kicks off once all 4 teams merge. If Template team lags (expected: it is L-sized, the others are S/M), audit run #3 either blocks on it or fires first without template, then re-fires the template slice.
