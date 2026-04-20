# Path to the Full 10k Generation

**Generated:** 2026-04-20
**Status:** v2.2 plan, immediately follows audit run #2 (`3c6e27ce-…`)
**Pre-reads:** `docs/GENERATION_IMPROVEMENT_PLAN.md` (v2.1), `docs/AUDIT_RUN_2_COMPARISON.md` (what worked / what didn't)

This document is the single source of truth for the work between today and the production 10,000-question generation run. Five phases (A–E), ~3-4 days wall-clock, ~$100 cost, ~3 hours human time.

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

### Recommended team partition

- **Generator team** — fixes 1, 5. Owns `template_generator.py`, `_schemas.py`, the 4 LLM strategy modules.
- **Audit team** — fix 2. Owns `src/qa/agents/team_b_validity.py`.
- **Sampler team** — fixes 3, 4, 6, 7. Owns `src/generators/_fact_sampler.py`.

Same parallel-worktree pattern as v2.1 (see `docs/IMPLEMENTATION_AGENT_ARCHITECTURE.md`). All 26+ existing tests must stay green; each fix adds 1-2 unit tests.

**Cost:** $0 (code only). **Wall-clock:** ~1.5 days parallel, ~3 days sequential.

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

**Cost:** ~$5 corpus + ~$10 audit = **~$15**. **Wall-clock:** ~6h overnight.

---

## Phase D · Sign-off (~1h)

Verify ALL gates from the Go/No-Go checklist in `docs/GENERATION_IMPROVEMENT_PLAN.md` pass on run #3:

- [ ] **Per-generator answer_correct ≥ 95%** on a fresh 30-question human spot-check (NEW gate from gold-cal #1)
- [ ] A1 fail rate < 1%
- [ ] A2 position-bias p > 0.2 in every (strategy, generator) cell with n ≥ 20
- [ ] A3 fail rate < 2% on single-fact strategies
- [ ] A4 held-out AUC < 0.85
- [ ] B1 majority-matches-key ≥ 95% AND human spot-check confirms
- [ ] B2 closed-book leakage < 15%
- [ ] C2 category-leak fail count = 0
- [ ] D1 self-preference |Δ| < 0.07 across all 5 evaluator models
- [ ] D3 max country over-representation ratio < 1.5
- [ ] difficulty_match ≥ 80% on human spot-check (or C4 fail rate < 5% as proxy)
- [ ] distractor_plausibility ≥ 75% on human spot-check (esp. templates)

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
| A · gold re-grade (parallel) | parallel with B | ~2h | $0 |
| B · v2.2 fixes (3 parallel teams) | ~1.5 days | minimal | $0 |
| C · audit run #3 | ~6h (overnight) | minimal | ~$15 |
| D · sign-off + any v2.3 iteration | ~1h-1d | ~30 min review | $0-5 |
| E · full 10k + dedup + post-audit | ~12h (overnight) | minimal | ~$90 |
| **TOTAL** | **~3-4 days** | **~3h** | **~$100-110** |

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

## Open question for the user

Phase B can start immediately while you re-grade gold (Phase A). **Want me to spawn the 3 parallel worktree teams now?** Or wait for your gold re-grade so we can also fold any new findings (κ for distractor_plausibility, ambiguity, source_faithful corrected for multi-fact) into Phase B?

If you want me to wait for gold re-grade, the runway shifts:
- A blocks B start (~2h delay)
- B then ~1.5 days
- Total: ~4 days instead of ~3

If you want me to start B now:
- A and B run in parallel
- Total: ~3 days

Default if no answer: start B immediately (parallel) — better wall-clock, and any gold-driven additions slot into a small Phase B' before C.
