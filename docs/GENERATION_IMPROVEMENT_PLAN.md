# OenoBench Generation Improvement Plan (v2 — post-gold-calibration)

**Source audit:** Run `e8eba8bb-cb49-42cd-9e32-c741c987043e` (`audit_pilot_v1`, 472 Qs, $8.49).
**Gold review:** 60 questions hand-graded by domain expert; see `docs/GOLD_CALIBRATION_ANALYSIS.md`.
**Generated:** 2026-04-19 (v2 supersedes the auto-generated v1).

This plan combines:
1. The original audit defects (verbatim copying, world-knowledge leakage, country skew, etc.).
2. The new defects surfaced by the gold review (Llama/Qwen wrong-key generation; LLM-judge κ < 0.6 on every audited rubric).
3. **A reweighted generator allocation** that rewards consistent quality without dropping any model. No single model may produce >35% of the corpus.

The whole list is ranked by impact-per-effort. Implement defects 0–3 in one iteration; re-run the audit; only then start the full 10k generation.

---

## 0 · Reweighted generator allocation (NEW)

The original plan distributed LLM questions equally across the five generators (1,500 each = 20%). The gold review shows quality is **not** uniform:

| Generator | Gold-review answer_correct | Action |
|---|---:|---|
| **Claude Opus 4.7** | 100% | scale up |
| **ChatGPT 5.4** | 100% | scale up |
| **Gemini 3.1 Pro** | 100% | scale up |
| **Qwen 3 235B** | 71% | scale down + verify |
| **Llama 3.1 405B** | 60% | scale down + verify |
| Template (deterministic) | 100% | hold (cap unchanged) |

### Proposed final-corpus allocation

| Generator | Old % | **New %** | Old count | **New count** | Notes |
|---|---:|---:|---:|---:|---|
| Template | 25.0 | **25.0** | 2,500 | **2,500** | Keep — 100% answer_correct, but distractors weak (33%) — see fix #6 |
| Claude | 15.0 | **20.0** | 1,500 | **2,000** | Scale up |
| ChatGPT | 15.0 | **20.0** | 1,500 | **2,000** | Scale up |
| Gemini | 10.0 | **20.0** | 1,000 | **2,000** | Scale up — judged best by domain expert in process log |
| Qwen | 17.5 | **9.0** | 1,750 | **900** | Scale down + post-LLM verify |
| Llama | 17.5 | **6.0** | 1,750 | **600** | Scale down + post-LLM verify |
| **TOTAL** | 100.0 | **100.0** | 10,000 | **10,000** | Cap: max 25% any model (well under the 35% ceiling) |

Rationale:
- The three high-quality LLMs each go to 20% (well under the 35% cap), giving 60% of questions to verifiably-correct generators while keeping diversity.
- Llama and Qwen retain meaningful representation (15% combined = 1,500 questions) so we keep generator-family diversity in the dataset, but their output is gated by an independent verifier (see fix #1).
- The template strategy stays at 25% — it produces correct answers 100% of the time and gives us deterministic, zero-cost questions.
- Allocation will be encoded in `src/generators/orchestrator.py:GENERATOR_TARGETS`.

### Implementation
```python
# src/generators/orchestrator.py
GENERATOR_TARGETS = {
    "claude":  2000,
    "chatgpt": 2000,
    "gemini":  2000,
    "qwen":     900,
    "llama":    600,
}
# template stays at STRATEGY_TARGETS["template"] = 2500
```

---

## 1 · Post-LLM independent verification for Llama/Qwen (NEW, blocks defect #0)

**Defect:** Llama produces 40% wrong-keyed questions; Qwen ~30%. The B1 tri-judge panel agrees with the wrong answer (judges all reason from the same flawed stem). κ(human, B1) = -0.05.

**Fix (M, 1–2 days):** add a `_verify_with_independent_solver(question, fact)` step in `src/generators/_schemas.py` that runs ONLY for Llama and Qwen-generated questions:

1. Pick a verifier model from the high-quality set (`claude` or `gemini`, rotated).
2. Pass `(question_text, options, source_fact)` and ask: "Which option is correct based on the source fact? Return JSON `{chosen, confidence}`."
3. If verifier's `chosen` == question's `correct_answer` → accept.
4. If mismatch → reject; the generator's outer loop will resample a new fact and retry. After 2 retries on the same fact, drop it.

**Cost:** ~1 extra LLM call per Llama/Qwen question. At ~900+600=1,500 total Llama/Qwen Qs × 1.5 retry factor × $0.005 avg ≈ **$11 added cost** for the full 10k run.

**Verification:** post-fix, run `B1 TriJudgeAnswer` on a 200-Q sample of Llama+Qwen output; require fail rate < 5% (vs current ~30%).

**Why not drop Llama/Qwen entirely?** User mandate: keep all models for generator-family diversity in the released benchmark. The verifier is the cheapest way to honour that while filtering out wrong-key output.

---

## 2 · Verbatim source copying (A3 FactEcho — impact 673)

**Defect:** 35% fail / 38% warn — single-fact strategies (`fact_to_question`, `template`) most affected; multi-fact strategies' rate is partly an artifact (see `GOLD_CALIBRATION_ANALYSIS.md` §3).

**Fix (S, <1 day):**

1. **Prompt change** in `src/generators/_prompts.py`:
   ```
   PARAPHRASE RULE: Rephrase the source fact in your own words. Do NOT
   copy more than 5 consecutive words verbatim from the source fact into
   the question or any option. Synonyms, restructured clauses, and
   inversions are required.
   ```
   Add to `FACT_TO_QUESTION_TEMPLATE`, `COMPARATIVE_*`, `SCENARIO_TEMPLATE`, all `DISTRACTOR_TEMPLATE_*` variants.

2. **Post-LLM rejector** in `src/generators/_schemas.py`:
   - Add `_max_lcs_against_facts(question_text, correct_option_text, fact_texts) -> float`
   - In `parse_llm_response`, after Pydantic validation, reject any question with `lcs_ratio > 0.6` against any linked source fact.
   - Single retry, then skip.

**Verification:** A3 fail rate drops from 35% to <2% on `fact_to_question` and `template`; multi-fact strategies stay where they are (these need the source-faithful re-eval; see fix #4).

---

## 3 · Country over-representation (D3 SkewAudit — 4.46×)

**Defect:** Top over-represented country in the audit corpus is 4.46× its share of the fact base. Threshold is 1.5×.

**Fix (M, 1 day):** add a per-country quota to `src/generators/_fact_sampler.sample_facts`:

1. Compute the fact-base country distribution once at import time.
2. Track per-country usage in a session-level counter (already partially done via `get_used_fact_ids`).
3. When sampling, weight inversely proportional to `(used_for_country / target_for_country)` so over-quota countries are drawn less.
4. Hard cap: never let any country exceed 1.5× its fact-base share in the output.

**Verification:** D3 max over-representation ratio < 1.5 on the next audit.

---

## 4 · Source-faithful re-evaluation for multi-fact strategies (NEW)

**Defect:** The original gold sheet showed only 1 of N source facts per question. Multi-fact strategies scored 25% on `source_faithful` not because they were unfaithful but because the reviewer couldn't see the full evidence base.

**Fix (S, <1 day):** patch `src/qa/_corpus.export_gold_sheet`:

- Replace the `source_fact` column with a `source_facts` column that contains all linked facts joined by `\n---\n`, with a fact index prefix `[1] ... [2] ...`.
- Bump the column count and update import logic in `import_gold_sheet`.

**Verification:** re-run `export-gold` and inspect the CSV — multi-fact questions now show all their evidence. Source-faithful pass rate on multi-fact strategies should rise to >70% on the next gold review.

---

## 5 · LLM-judge calibration drift (NEW)

**Defect:** Cohen's κ(human, judge) on the 60-Q gold:

| Rubric | Agent | κ |
|---|---|---:|
| answer_correct | B1 TriJudgeAnswer | -0.05 |
| needs_source | B2 ClosedBookSolvability | 0.01 |
| no_vague_language | A1 LexicalHygiene | 0.00 |
| source_faithful | A3 FactEcho | -0.08 |
| distractors_plausible | C2 CategoryLeak | 0.15 |

Per the report's own gating criterion (κ < 0.6 → downweight), every signal must be downweighted.

**Fixes (per agent):**

5a. **B1 cannot detect Llama/Qwen wrong keys.** Replace the "blocks regeneration" gate by combining B1 with the post-LLM verifier from fix #1. B1 stays as a sanity check but no longer the sole gate.

5b. **B2 over-reports leakage 5×** because Opus 4.7 / GPT-5.4 / Gemini 3.1 Pro know more wine than the test-taker. Two changes:
- Add Llama and Qwen to the B2 closed-book judge panel (their world knowledge is closer to a typical test-taker).
- Re-tune the gate from "<50% leakage" to "<15% leakage" (calibrated against the human's 12% leakage rate on the gold sample).

5c. **A1 misses subtle vague phrasings.** Harvest the 8 vague-flagged phrasings from the gold sheet's `notes` column and add them to `_VAGUE_PATTERNS` in `src/generators/_fact_sampler.py`.

5d. **A3 interpretation flip.** High LCS isn't unfaithful — it's mechanically lazy. Rename the agent narrative as "no verbatim copying" not "source faithfulness", and keep the LCS<0.6 threshold.

5e. **C2 measures only category leaks.** Add a stub for **C1 DistractorDifficulty** (LLM per-distractor plausibility) so the broader human rubric has an LLM proxy. Defer until we see how it performs in audit run #2.

---

## 6 · Template distractor plausibility (NEW — gold review)

**Defect:** templates score 100% on answer correctness but only **33%** on distractor plausibility. Wrong options are sampled by entity-type matching (e.g. another "country" string) without semantic similarity, so they're trivially eliminable.

**Fix (M, 1–2 days) in `src/generators/template_generator.py`:**
- For each template's distractor type, fetch entity candidates from the same type, then rank by embedding similarity to the correct entity (use existing pgvector index).
- Take the 3 nearest neighbours that are not the correct answer; reject if no near-neighbours exist (skip the template instance).

**Verification:** human spot-check of 30 template questions; distractor plausibility ≥ 75%.

---

## 7 · Difficulty calibration (NEW — gold review)

**Defect:** human review found 38% of questions don't match their assigned difficulty label. Generators currently take whatever the LLM produces.

**Fix (M, 1–2 days):**
- Add a post-generation difficulty re-classifier in `src/qa/agents/team_c_probes.py` (promote C4 from deferred). Single LLM call per question (Gemini, cheap) returns rated difficulty 1–4.
- During the final 10k assembly, if re-rated difficulty differs by ≥2 levels from the assigned label, reject the question; if differs by 1, update the label.

**Verification:** human spot-check of 30 questions; difficulty_match ≥ 80%.

---

## 8 · Template detectability (A4 — AUC 0.96)

**Defect:** templates are statistically distinguishable from LLM questions by surface features (POS-bigram logreg AUC 0.96).

**Fix (M, 1–2 days) in `src/generators/template_generator.py`:**
- Diversify template phrasings: rotate opening verbs (Which / What / Identify the / Name the / In which …), randomise clause order where possible, vary punctuation.
- For each of the 45 templates, add 3 paraphrase variants and randomly select one per generation.

**Verification:** A4 held-out AUC < 0.85 in audit run #2.

---

## 9 · Vague / marketing / blend-as-variety phrasing (A1 — impact 52)

**Defect:** 13 fail + 13 warn = 5.5% in the audit; the human spotted additional vague phrasings A1's regex missed.

**Fix (S, <1 day):** extend `_VAGUE_PATTERNS` and `_BLEND_AS_VARIETY` regexes in `src/generators/_fact_sampler.py` with the phrases from the gold-review notes. Add a post-LLM filter in `src/generators/_schemas.py` that rejects questions whose stem or options contain any blocked phrase.

**Verification:** A1 fail rate < 1% on audit run #2.

---

## 10 · Wine-category distractor leak (C2 — impact 24)

**Defect:** 5 fail + 9 warn = 3% of questions have distractors from a different wine category than the keyed answer (e.g. sparkling distractor in a red-wine question).

**Fix (S, <1 day) in `src/generators/_fact_sampler.py`:** make `_classify_wine_category` mandatory in **all** distractor sampling paths (not just `distractor_miner`). Reject mismatched candidates at the sampler layer.

**Verification:** C2 fail count = 0 on audit run #2.

---

## 11 · Position / length bias (A2 — impact 3)

**Defect:** at least one (strategy, generator) cell shows significant position or length bias.

**Fix (S, <1 day):** verify the option-shuffle in `src/generators/_schemas.py` runs unconditionally before DB insert. If length bias persists after shuffle, add a length-normaliser that pads/trims distractor texts to within ±20% of the correct option's length.

**Verification:** A2 χ² p-value > 0.2 on every (strategy, generator) cell with n ≥ 20.

---

## 12 · Self-preference (D1 — warn, ChatGPT max Δ 0.117)

**Defect:** ChatGPT scores ~12pp better on its own questions than on others'. Within the warn band, but worth tracking.

**Fix (already addressed by allocation in §0):** the new allocation caps any single model at 25% of the dataset (well under the 35% ceiling), which limits the upside any one model can extract from self-preference.

**Verification:** in audit run #2, no model's self-pref delta exceeds 0.07 (the warn threshold).

---

## Regeneration Go/No-Go checklist (revised)

The original gates assumed LLM-judge findings were authoritative. After the κ < 0.6 finding, gates are revised to combine LLM-judge signals with human spot-checks.

**Do NOT start the full 10k generation run until ALL of these hold on audit run #2:**

- [ ] **Per-generator answer_correct ≥ 95%** on a fresh 30-question human spot-check (NEW, hard gate)
- [ ] A1 fail rate < 1%
- [ ] A2 position-bias p > 0.2 in every (strategy, generator) cell with n ≥ 20
- [ ] A3 fail rate < 2% **on single-fact strategies** (multi-fact tracked separately after fix #4)
- [ ] A4 held-out AUC < 0.85
- [ ] B1 majority-matches-key rate ≥ 95% **AND** human spot-check confirms
- [ ] B2 closed-book leakage **< 15%** (recalibrated, judge panel includes Llama/Qwen)
- [ ] C2 category-leak fail count = 0
- [ ] D1 self-preference |Δ| < 0.07 across all 5 evaluator models
- [ ] D3 max country over-representation ratio < 1.5
- [ ] **NEW:** difficulty_match ≥ 80% on human spot-check
- [ ] **NEW:** distractor_plausibility ≥ 75% on human spot-check (esp. templates)

If any gate fails twice in a row, escalate to the deferred LLM agents (C1, B3, B4, C3).

---

## Implementation order (recommended)

| # | Fix | Priority | Effort | Files |
|---|---|---|---|---|
| 0 | Reweighted generator allocation | **P0** | S | `src/generators/orchestrator.py:GENERATOR_TARGETS` |
| 1 | Post-LLM verifier for Llama/Qwen | **P0** | M | `src/generators/_schemas.py`, new `_verify.py` |
| 2 | A3 paraphrase prompt + LCS rejector | **P0** | S | `src/generators/_prompts.py`, `_schemas.py` |
| 3 | D3 per-country quota | **P0** | M | `src/generators/_fact_sampler.py` |
| 4 | Multi-fact source-faithful gold export | P1 | S | `src/qa/_corpus.py` |
| 5 | LLM-judge re-calibration (B2 panel + thresholds) | P1 | S | `src/qa/_judges.py`, `src/qa/agents/team_b_validity.py` |
| 6 | Template distractor embedding similarity | P1 | M | `src/generators/template_generator.py` |
| 7 | Difficulty re-classifier (promote C4) | P1 | M | `src/qa/agents/team_c_probes.py` |
| 8 | Template phrasing diversification | P2 | M | `src/generators/template_generator.py` |
| 9 | A1 extended vague regex | P2 | S | `src/generators/_fact_sampler.py` |
| 10 | C2 in all distractor sampling | P2 | S | `src/generators/_fact_sampler.py` |
| 11 | A2 verify shuffle + length-normaliser | P2 | S | `src/generators/_schemas.py` |
| 12 | (no extra work — handled by allocation) | — | — | — |

**Estimated total effort:** P0 fixes ~3 days; P1 fixes ~3 days; P2 fixes ~2 days. Total **~8 days** before audit run #2.

**Estimated cost of audit run #2 + final 10k:** ~$10 (audit) + ~$80 (10k generation with verification step) = **~$90**.
