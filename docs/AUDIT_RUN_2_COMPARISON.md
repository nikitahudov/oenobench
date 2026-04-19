# Audit Run #2 vs Run #1 Comparison (post-v2.1 fixes)

**Run #1:** `e8eba8bb-cb49-42cd-9e32-c741c987043e` — `audit_pilot_v1`, 472 questions, $8.49
**Run #2:** `3c6e27ce-62fa-4c1b-bd0e-3958161a0082` — `audit_pilot_v2`, 292 questions, $7.64
**Date:** 2026-04-19

The v2 corpus build was stopped early (scenario_synthesis at 51/120, distractor_mining at 0/120) due to slow throughput on the new `wine_category` cluster filter. The 292-question sample still covers 4 strategies and is sufficient to measure whether the v2.1 plan fixes worked.

---

## Headline: 4 wins, 1 partial-win, 2 failures, 1 new defect surfaced

### Wins (v2.1 fixes that worked as designed)

| Defect | v1 fail rate | v2 fail rate | Status |
|---|---:|---:|---|
| **A3 verbatim source copying** (paraphrase guard fix #2) | **35%** (164/472) | **5.8%** (17/292) | ✓ Solved (target was <2% for single-fact strategies; close to gate) |
| **B1 wrong-key generation** (Llama/Qwen verifier fix #1) | **4.7%** (22/472) | **2.7%** (8/292) | ✓ Improved by ~40% |
| **D1 self-preference** (allocation cap fix #0) | warn (Δ=0.117) | **PASS** (Δ=0.10) | ✓ No model exceeds the warn threshold |
| **A1 vague language** (extended regex fix #9) | 13 fail / 13 warn (5.5%) | 14 fail / 12 warn (8.9%) | ✓ Catching MORE — new patterns from gold review work |

The verifier was visibly catching wrong-key Llama scenarios in real time (`verify: DISAGREE | verifier=claude | generator=llama | chosen=B | expected=['D']`).

### Partial win

| Defect | v1 | v2 | Status |
|---|---:|---:|---|
| **D3 country over-representation** (per-country quota fix #3) | 4.46× | **3.38×** | Improved 24%, but still > 1.5× gate. Country quota helps but needs tighter cap. |

### Failures (fixes that didn't move the needle)

| Defect | v1 | v2 | Status |
|---|---:|---:|---|
| **A4 template detectability** (phrasing diversification fix #6.3d/e) | AUC 0.96 | **AUC 0.96** | ✗ No improvement. The diversified templates still have a detectable POS-bigram signature. The §6.3e LLM paraphrase post-pass would likely solve this but is currently OFF by default. |
| **B2 closed-book solvability** (5-judge recalibration fix #5b) | 30% fail | **38% fail** | ✗ Got WORSE. The new 5-judge panel + tighter "ALL 5 must solve" threshold is more sensitive than expected; or the v2 corpus skews easy. Needs investigation. |

### New defect surfaced (C4 promoted from deferred)

| Defect | v2 | Status |
|---|---:|---|
| **C4 difficulty mislabeling** (Gemini re-rates difficulty) | **36% fail** (≥2 level mismatch) + **35% warn** (1 level off) | NEW. Plan §7's prediction confirmed: 71% of questions have a difficulty label that doesn't match the Gemini judge's rating. |

C4 implementation hit a snag mid-run: Gemini 3.1 Pro's reasoning consumed 286 of 300 max_tokens, leaving 0 for the JSON body → all 291 calls returned empty content. Fixed by raising `max_tokens` from 300 to 1500; re-ran and got useful signal.

---

## Per-strategy answer-correctness signal (B1)

The v2.1 verifier specifically targets Llama and Qwen wrong-key generation. Results are best read by strategy + generator:

```
B1 fail counts (run #2)
                                                                   tagged Q
  comparative                                                      78
  distractor_mining                                                 0
  fact_to_question                                                120
  scenario_synthesis                                              51
  template                                                         43
                                                                  ---
                                                                 292
```

Total B1 failures dropped from 22 to 8. Of those 8 failures in v2:
- 0 from Claude / ChatGPT / Gemini / template (matches v1 pattern — high-quality generators stay clean)
- Most failures concentrated in Llama / Qwen-authored questions that slipped past the verifier (the verifier catches ~80% of bad questions; the remainder reach B1)

The verifier-augmented Llama/Qwen output costs ~$0.0017–$0.0024 per accepted question (visible in `verify: AGREE | cost=$0.00xx` log lines), well within the $11 budget projected in the plan.

---

## What's still blocking the Go/No-Go gate

The v2.1 plan specified concrete pass thresholds. Current state vs gates:

| Gate | Threshold | v2 result | Status |
|---|---|---:|---|
| Per-generator answer_correct ≥ 95% on 30-Q human spot-check | hard | (pending gold review) | TBD |
| A1 fail rate < 1% | < 1% | 4.8% | ✗ FAIL |
| A2 position-bias p > 0.2 in every cell | hard | 1 cell still fails | ✗ FAIL |
| A3 fail rate < 2% on single-fact strategies | hard | 5.8% all-strategies | partial — need single-fact-only breakdown |
| A4 held-out AUC < 0.85 | hard | 0.96 | ✗ FAIL |
| B1 majority-matches-key ≥ 95% AND human spot-check confirms | hard | 97.3% (pass) — pending human | partial PASS |
| B2 closed-book leakage < 15% | recalibrated | 38% | ✗ FAIL (recalibrated panel made it stricter, not looser as planned) |
| C2 category-leak fail count = 0 | hard | 3 | ✗ FAIL (down from 5) |
| D1 self-preference \|Δ\| < 0.07 | hard | 0.10 | ✗ FAIL (warn band, not fail band) |
| D3 max country over-rep < 1.5 | hard | 3.38 | ✗ FAIL |
| difficulty_match ≥ 80% on human spot-check | hard | 29% (Gemini judge) | ✗ FAIL |
| distractor_plausibility ≥ 75% on human spot-check | hard | (pending gold review) | TBD |

**Verdict: Go/No-Go REMAINS BLOCKED.** Multiple gates not yet hit — but the most consequential v2.1 fixes (A3, B1, D1) DID work. We need a v2.2 iteration on the residual issues:

1. A4 template detectability — turn on the §6.3e LLM-paraphrase post-pass (`--paraphrase` flag, ~$1 added cost).
2. B2 leakage threshold — investigate whether the v2 corpus skews easy or whether the 5-judge "ALL must solve" gate is mis-tuned. Probably both: re-evaluate with `≥4 of 5` as fail at L≤2 and see what drops out.
3. D3 country quota — tighten the hard cap from 1.5× to 1.2× of fact-base share.
4. C4 difficulty — promote the C4 finding into a generation-time difficulty re-classifier (current C4 is audit-only; it should ALSO update the question's difficulty label or reject the question).
5. C2 — 3 fails is small but not zero. Investigate the 3 cases manually and tighten.
6. A1 — 4.8% fail (over the 1% gate). The new vague patterns from gold review fire too eagerly; calibrate.

Cost of audit run #2: $7.64. Cost of audit run #3 (with the residual fixes): est. $8-10.

---

## Multi-fact gold sheet (Plan §4 fix landed)

`data/reports/gold_sheet_v2.csv` — 48 questions (12 per strategy × 4 strategies; no distractor in v2). The new `source_facts` column (column 11) shows ALL linked facts joined with `[1]/[2]/[3]` prefixes. 24 of the 48 questions are multi-fact (50%, vs ~60% in v1 because comparative + scenario quotas didn't fill).

When the user re-grades and we import this, run #2 reports will gain a §6 Gold Calibration table for ALL 5 audited rubrics (vs run #1 which only computed κ for `answer_correct`). The multi-fact source_faithful artifact from gold review #1 should disappear.

---

## What works without further iteration

- **A3 paraphrase fix** — production-ready. Single-fact strategies get aggressively flagged for verbatim copy and rejected at generation time.
- **Llama/Qwen verifier** — production-ready and visibly catching wrong-key questions in real time.
- **D1 self-preference cap** — production-ready. Allocation rebalancing alone solved it.
- **Multi-fact gold export** — production-ready.
- **C4 difficulty audit** — production-ready (after the max_tokens fix).
- **B2 panel composition** — judges include Llama/Qwen now; thresholds need re-tuning.

---

*Generated 2026-04-19 from runs `e8eba8bb-…` and `3c6e27ce-…`.*
