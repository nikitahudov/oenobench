# OenoBench Generation Improvement Plan (v2.3 — post-gold-v3)

**v2.3 source audit:** Run `0bfe85dc-4fdc-4500-b274-a4b05d982e20` (`audit_pilot_v3`, 331 Qs, $8.51).
**v2.3 gold review:** 119 combined gold rows (v1 + v2 + v3); κ recomputed, see §5 and `docs/QUALITY_AUDIT_REPORT.md` §6.
**Generated:** 2026-04-19 · **Last major update:** 2026-04-22 (v2.3: Gemini bump §13 + template diversity §14 added after Phase D sign-off).

This plan combines:
1. The original audit defects (verbatim copying, world-knowledge leakage, country skew, etc.).
2. The new defects surfaced by the gold review (Llama/Qwen wrong-key generation; LLM-judge κ < 0.6 on every audited rubric).
3. **A reweighted generator allocation** that rewards consistent quality without dropping any model. No single model may produce >35% of the corpus.

The whole list is ranked by impact-per-effort. Implement defects 0–3 in one iteration; re-run the audit; only then start the full 10k generation.

---

## 0 · Reweighted generator allocation (ACTIVE — v2.3)

v2.1 distributed LLM work evenly across the three "verifiable" LLMs (Claude/ChatGPT/Gemini @ 2,400 each) with Llama/Qwen verifier-gated. Gold-v3 + audit_pilot_v3 show Gemini is the overall quality leader and the clear winner on our highest-priority post-v2.1 defect (A3 FactEcho). v2.3 bumps Gemini modestly and pulls balance from the verifier-gated tails. See §13 for the full analysis.

### Active allocation (v2.3, in `src/generators/orchestrator.py`)

| Generator | v2.1 count | **v2.3 count** | Share | Reason |
|---|---:|---:|---:|---|
| Template | 1,000 | 1,000 | 10% | Held — §6 overhaul + §14 diversity plan handle template quality |
| Claude | 2,400 | **2,400** | 24% | Held — strong across the board |
| ChatGPT | 2,400 | **2,400** | 24% | Held — strong, but watch D1 self-pref warn |
| Gemini | 2,400 | **2,800** | **28%** | +400 — leader on avg pass rate (70.5%) and dominant on A3 FactEcho (81%) |
| Qwen | 1,100 | **800** | 8% | -300 — lowest A1 LexicalHygiene pass (79%); verifier catches wrong-keys but quality tail is thin |
| Llama | 700 | **600** | 6% | -100 — lowest A3 FactEcho pass (38%); verifier-gated |
| **TOTAL** | 10,000 | **10,000** | 100% | Max any model = 28% (Gemini), under 35% ceiling |

Rationale:
- Gold-v3 per-generator 8/8 perfect rate: Llama 78%, Gemini 75%, ChatGPT 67%, Claude 67%, Qwen 50%, template 58%. Avg rubric score: chatgpt/claude 7.58, Gemini 7.50, Qwen 7.33, Llama 7.00, template 5.83.
- Audit_pilot_v3 pass rate avg across 6 question-level agents: Gemini 70.5%, chatgpt 66.7%, claude 66.7%, llama 64.4%, qwen 63.3%, template 63.1%.
- Gemini's A3 FactEcho pass rate (81%) is >20pp above the next best LLM — the verifier-free answer to the v2.1 #1 defect.
- Llama cut is smaller than Qwen because Llama has the **lowest audit fail rate** (12.3% vs qwen 14.0%) — when it succeeds, Llama succeeds cleanly; when it fails, it fails catastrophically (90% of gold-v3 "completely incorrect" template-strategy fails came from llama or template). Cut Qwen harder because its failure mode is subtler (vague phrasing) — harder to catch post-hoc.
- Corpus cap rises from 24% to 28%; still under the 35% ceiling. Self-preference risk on Gemini monitored via D1.

### Implementation
```python
# src/generators/orchestrator.py (v2.3 ACTIVE)
STRATEGY_TARGETS = {
    "fact_to_question":   4500,   # unchanged vs v2.1
    "template":           1000,
    "comparative":        1500,
    "scenario_synthesis": 1500,
    "distractor_mining":  1500,
}

GENERATOR_TARGETS = {
    "claude":  2400,
    "chatgpt": 2400,
    "gemini":  2800,   # +400 vs v2.1
    "qwen":     800,   # -300
    "llama":    600,   # -100
}
# Sum = 9,000 + template 1,000 = 10,000.
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

## 6 · Template strategy overhaul (REWRITTEN — gold review surfaced systemic defects)

The 12 template questions in the gold review revealed the strategy has the **same class of structural problems the LLM strategies had before April 12–18 fine-tuning**, but they're harder to fix because templates lack the LLM's flexibility.

### 6.1 Defect inventory (per the 12-Q gold sample)

| Rubric | Pass | Notes |
|---|---:|---|
| answer_correct | 100% | The keyed answer is always factually right |
| **distractors_plausible** | **33%** | Distractors are random same-type entities — often wildly off (e.g. "Sundarban Honey" as a wine sub-region; "Wine of Origin" as a producer location) |
| not_ambiguous | 92% | OK |
| **source_faithful** | **50%** | Many questions don't actually require the source fact — they're solvable from world knowledge alone (template fills slots from JSONB entities, source text is unused) |
| needs_source | 83% | Marginal — half the questions are world-knowledge solvable |
| no_vague_language | 83% | OK |
| **difficulty_match** | **42%** | Most labelled L2/L3 are actually L1 (recall-only); two L1/L2 are actually L3 (source fact doesn't contain the answer, requires knowledge transfer) |
| cognitive_match | 100% | OK |

Plus from the audit:
- A4 TemplateFingerprint AUC = **0.96** (templates are statistically distinguishable from LLM questions by surface features alone).
- A3 FactEcho fail on some templates (the question stem contains the fact's entity values verbatim).

### 6.2 Root cause analysis

The template strategy is **fact-agnostic by design**. It samples a fact, extracts JSONB entities (e.g. `{country: "Germany", region: "Rheingau"}`), then fills `"Which country is the {region} wine region located in?"`. The fact's text content is never used. Consequences:

1. **Distractors come from a flat entity-type pool.** "Same type as the correct answer" is too coarse — it lets any country be a distractor for "Germany", including continents away or non-wine countries.
2. **Questions are world-knowledge solvable** because the template asks about a fact most LLMs already know (Rheingau is in Germany).
3. **Difficulty labelling is decoupled from question difficulty** — the template-id has a fixed difficulty (T-REG-COUNTRY-01 → L1) regardless of how obscure the entity is. "Which country is California in?" gets L1; "Which country is Neusiedlersee in?" also gets L1 even though it's harder.
4. **Phrasing is rigid** — 45 templates, each with one canonical sentence, makes the strategy easy to fingerprint.
5. **No use of fact content** means templates can't generate inference-based or analysis-level questions; they're stuck at recall.

### 6.3 Fix bundle (multi-PR, ~3 days)

These changes can land in parallel; together they salvage the strategy at a reduced share.

**6.3a — Embedding-similarity distractor sampling (M, 1 day)**

In `src/generators/template_generator.py`, replace the random same-type distractor sampler with a pgvector nearest-neighbour search:
- For each template's distractor slot, embed the correct entity name + a short context phrase ("Rheingau wine region in Germany").
- Query pgvector for top-K (K=8) nearest entities of the same type, then pick 3 from positions 2-5 (skip the closest, which might be aliases; skip the farthest, which is too far).
- Reject the template instance if fewer than 3 viable neighbours exist for that entity.

**6.3b — Source-fact-anchored question generation (M, 1 day)**

Stop generating questions whose answer is solvable without the source fact. Two changes:

1. Restrict template strategy to facts whose JSONB entities include details NOT in the entity name itself (e.g. `{region: "Rheingau", soil: "slate"}`). A `"Which soil type is found in Rheingau?"` question requires the fact; `"Which country is Rheingau in?"` does not.
2. Rotate template pool to favour relationship-based templates (`region → soil`, `region → climate`, `grape → typical_aging`, `producer → flagship_wine`) over identity-based templates (`region → country`).

Update `src/generators/template_generator.py:TEMPLATES`:
- Mark each template as `requires_fact_specific=True/False`.
- When `True`, only fire if the fact's JSONB has the relevant non-name entity.
- Drop or down-weight `requires_fact_specific=False` templates (most of T-REG-COUNTRY-*, T-PRD-COUNTRY-*).

**6.3c — Per-instance difficulty re-rating (S, <1 day)**

Replace the template-id-fixed difficulty with a heuristic:
- L1: target entity has ≥ 100 mentions in the fact base (well-known).
- L2: 20-99 mentions.
- L3: 5-19 mentions.
- L4: < 5 mentions.

Combined with §7 (post-LLM difficulty re-classifier) for the cross-strategy check.

**6.3d — Phrasing diversification (M, 1 day)**

Each of the 45 templates gets 4-6 paraphrased variants. Variants rotate:
- Opening (`Which`, `What`, `In which`, `Identify the`, `Name the`, `The {entity_type} of {entity} is …`).
- Word order (subject-first vs object-first).
- Punctuation (with/without trailing definite article).

Random selection per generation. Should drop A4 detectability AUC well below 0.85.

**6.3e — LLM paraphrase post-pass (optional M, 1 day)**

For an extra anti-detectability layer: pass each generated template question through a single Gemini call with prompt "Rephrase this question naturally without changing its meaning or answer; keep the options exactly as given. Output JSON `{question_text}`." Costs ~1k template-Qs × $0.001 = $1. This converts templates from "deterministic" to "LLM-rephrased deterministic" — preserves correctness while breaking the fingerprint.

### 6.4 Verification gate

After the bundle lands and template count drops to 1,000:
- distractor_plausibility ≥ 75% on a fresh 30-Q template human spot-check
- source_faithful ≥ 80% on the same sample
- difficulty_match ≥ 80% on the same sample
- A4 held-out AUC < 0.80 (vs current 0.96)
- A3 fact-echo fail rate < 2% on templates

### 6.5 Decision log

- **Why keep templates at all?** Two reasons: (1) they're the only deterministic path to controllable difficulty/domain coverage; (2) for the L1 recall floor, a sound template-generated question is strictly cheaper and faster than an LLM call.
- **Why not drop to 0%?** With the §6.3 fixes the residual 10% is defensible. Going to 0 would require pushing more questions through Llama/Qwen, both of which have their own quality tax (the verifier).
- **Why not 5% or 15%?** 10% gives ~1,000 questions, enough to provide a difficulty-controlled L1 floor without the strategy dominating any domain. 5% leaves too few for stable per-domain coverage; 15% over-weights a strategy with structural ceilings.

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

**Fix:** subsumed by §6.3d (phrasing diversification) + optional §6.3e (LLM paraphrase post-pass). No separate work item.

**Verification:** A4 held-out AUC < 0.80 in audit run #2 (gate moved tighter to reflect §6.3e is on the table).

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
| 0 | Reweighted generator allocation v2.1 (incl. template cut to 10%) | **P0** | S | `src/generators/orchestrator.py` (STRATEGY_TARGETS, GENERATOR_TARGETS) |
| 1 | Post-LLM verifier for Llama/Qwen | **P0** | M | `src/generators/_schemas.py`, new `_verify.py` |
| 2 | A3 paraphrase prompt + LCS rejector | **P0** | S | `src/generators/_prompts.py`, `_schemas.py` |
| 3 | D3 per-country quota | **P0** | M | `src/generators/_fact_sampler.py` |
| 4 | Multi-fact source-faithful gold export | P1 | S | `src/qa/_corpus.py` |
| 5 | LLM-judge re-calibration (B2 panel + thresholds) | P1 | S | `src/qa/_judges.py`, `src/qa/agents/team_b_validity.py` |
| 6a | Template — embedding-similarity distractors | **P0** | M | `src/generators/template_generator.py` |
| 6b | Template — source-fact-anchored generation (filter, template selection) | **P0** | M | `src/generators/template_generator.py`, `_fact_sampler.py` |
| 6c | Template — per-instance difficulty re-rating heuristic | P1 | S | `src/generators/template_generator.py` |
| 6d | Template — phrasing diversification (4-6 paraphrases per template) | P1 | M | `src/generators/template_generator.py` |
| 6e | Template — optional LLM paraphrase post-pass (Gemini, ~$1) | P2 | M | new `src/generators/_template_paraphrase.py` |
| 7 | Difficulty re-classifier (promote C4) | P1 | M | `src/qa/agents/team_c_probes.py` |
| 9 | A1 extended vague regex | P2 | S | `src/generators/_fact_sampler.py` |
| 10 | C2 in all distractor sampling | P2 | S | `src/generators/_fact_sampler.py` |
| 11 | A2 verify shuffle + length-normaliser | P2 | S | `src/generators/_schemas.py` |
| 8, 12 | subsumed (see §8 and §12) | — | — | — |

**Estimated total effort (sequential):** P0 fixes ~5 days (was 3, +2 for template overhaul); P1 fixes ~3 days; P2 fixes ~2 days. Total **~10 days** before audit run #2.

**Estimated total effort (parallelised via the agent-team architecture in `docs/IMPLEMENTATION_AGENT_ARCHITECTURE.md`):** ~3 days wall-clock with 4 parallel teams.

**Estimated cost of audit run #2 + final 10k:** ~$10 (audit) + ~$80 (10k generation with verification step) + ~$1 (template paraphrase pass) = **~$91**.

---

## 13 · Gemini reallocation (v2.3 — post-gold-v3 analysis)

**Prompt:** User observation, 2026-04-22 — "I quite often like the gemini generated questions. Please analyze if we should increase the gemini allocation in the overall pool."

### Evidence

Three data sources all point the same direction.

**13.1 Audit_pilot_v3 (331 Qs, 6 question-level agents, no humans):**

| agent | chatgpt | claude | **gemini** | llama | qwen |
|---|---:|---:|---:|---:|---:|
| A1 LexicalHygiene | 95 | 90 | 93 | 98 | 79 |
| **A3 FactEcho** | 55 | 51 | **81** | 38 | 60 |
| B1 TriJudgeAnswer | 97 | 93 | 93 | 92 | 89 |
| B2 ClosedBookSolvability | 11 | 29 | 23 | 25 | 20 |
| C2 CategoryLeak | 100 | 100 | 96 | 97 | 96 |
| C4 DifficultyAudit | 42 | 37 | 37 | 35 | 37 |
| **Avg pass rate** | **66.7** | **66.7** | **70.5** | 64.4 | 63.3 |

Gemini leads on the avg pass rate and dominates the highest-priority post-v2.1 defect (A3 FactEcho: 81% pass vs 60% for the next-best LLM). The only rubric where Gemini noticeably lags is A1 (93% vs ChatGPT 95%) — noise-level.

**13.2 Gold v3 human review (59 scored questions, 8 rubrics):**

| generator | n | perfect 8/8 | avg /8 |
|---|---:|---:|---:|
| llama | 9 | 78% | 7.00 |
| **gemini** | 8 | **75%** | **7.50** |
| chatgpt | 12 | 67% | 7.58 |
| claude | 12 | 67% | 7.58 |
| template_only | 12 | 58% | 5.83 |
| qwen | 6 | 50% | 7.33 |

Gemini (n=8, small) is runner-up on perfect 8/8, and matches ChatGPT/Claude on average rubric score. Llama's higher 8/8 rate is polar: Llama tends to produce either clean questions or "completely incorrect" ones (failure mode caught by the verifier, but still burns budget).

**13.3 Subjective:** User reports preferring Gemini output qualitatively. Consistent with the quantitative signal.

### Decision

Bump Gemini 2,400 → 2,800 (+400 questions, +17% share within LLM allocation). Balance:
- Qwen 1,100 → 800 (−300): worst A1 pass rate (79%); phrasing-quality tail is long.
- Llama 700 → 600 (−100): worst A3 FactEcho (38%); kept in corpus for generator-family diversity but reduced to minimise verifier workload.
- Claude/ChatGPT: unchanged (each 2,400 / 24%). Bumping either would put a single model > 30% — tolerable but reduces signal for D1 self-preference analysis.

Final per-model share: Claude 24 · ChatGPT 24 · **Gemini 28** · Qwen 8 · Llama 6 · Template 10. Max any model = 28%; ceiling still 35%.

### Risks

- **Self-preference inflation.** Gemini is the B2 judge panel's 3rd member. Raising Gemini author share to 28% widens the worst-case window where Gemini judges its own work. Mitigation: run D1 self-pref audit with 5 judges after Phase F; drop to 2,600 if D1 |Δ| exceeds 0.07.
- **Small gold-v3 sample for Gemini (n=8).** Confidence interval on 75% perfect is wide. Mitigation: Phase F gold-v4 should re-sample Gemini at n≥15.
- **Llama catastrophic drop (9 → 6%)** could hurt generator-family diversity for the NeurIPS Self-Preference Score narrative. If a reviewer challenges "is Llama still meaningfully represented?" the answer is: 600 questions × 4 LLM strategies ≈ 150/strategy, enough for per-strategy evaluation cells with n ≥ 20 at 4-way splits.

Implementation: already applied in `src/generators/orchestrator.py` as part of this commit.

---

## 14 · Template diversity — pattern-monopoly fix (v2.3)

**Prompt:** User observation, 2026-04-22 — "template generation has improved significantly. However, all the template questions have similar pattern like 'true or false: producer X is located in region Y'. I think we should increase the diversity of the template patterns."

### Evidence

Gold-v3 sampled 12 template questions, and 12/12 were the same pattern (T/F producer→region). Investigation of the 107-question template DB population reveals a more general issue:

| Symptom | Observed |
|---|---|
| Distinct `template_id`s firing | **11 of 38** registered templates |
| Top template share (`T-PRD-TF-REGION-01`) | **30 / 107 = 28%** |
| Top-3 template share | **60 / 107 = 56%** (T-PRD-TF-REGION-01, T-PRD-REGION-01, T-REG-COUNTRY-01) |
| Legacy templates (deleted from registry per v2.2 §8a, still in DB) | ~32 / 107 (T-REG-COUNTRY-01, T-GRP-REGION-01, T-GRP-ORIGIN-01, T-REG-GRAPE-01) |
| Templates with `cognitive_dim=comprehension` or higher | **0 / 107** (registry has 5, none fire) |
| Templates with broken source fact (Bordeaux "estate in Château X") | 14 / 107 |

### Root causes

1. **No per-template cap in `fill_template()`.** The sampler picks the template whose `required_entities` slots match the current fact best; one common structure (producer → location) matches a huge fraction of producer facts, so it wins disproportionately.
2. **Registry expansion stalled.** The v2.2 radical overhaul (§6 + §8a) pruned broken superlative templates but didn't add replacements above `recall`. Result: a thinner registry than pre-v2.2, same monopoly dynamics.
3. **v2.2 §8a purged the CODE but not the DATA.** Templates the code no longer knows about are still in the DB because `fix #8a` deleted registry entries without a cleanup pass on existing generated questions.
4. **Upstream fact contamination.** 43 facts of the form "Château X is a classified Bordeaux estate in Château Y" (where Y is also a château, mis-parsed from a Wikipedia classified-list table) feed template T-PRD-TF-REGION-01 and produce obviously-broken "Château is located in Château" questions. This is a data-pipeline bug, not a template bug — but it concentrates in the template strategy.

### Fixes (v2.3, three tiers)

**14.1 Immediate (ship in Phase F, together with §13 allocation):**

- **Hard cap in `fill_template()`:** maintain a session counter on `template_id`; if any template's usage hits 15% of the per-strategy quota (i.e. 150 of 1000), force the selector to choose from the remaining templates. Second-choice must differ by template_id prefix (`T-PRD-*` → `T-REG-*` etc.) to break sub-domain concentration too.
- **Purge legacy templates:** `DELETE FROM questions USING generation_metadata gm WHERE q.id = gm.question_id AND gm.template_id IN (<deleted-list>)` plus cascading delete of `question_facts`, `generation_metadata`. Also purge the ~14 questions from Bordeaux-corrupted facts.
- **Fix Bordeaux scraper:** `src/scrapers/bordeaux.py` table-cell iteration is off-by-one on the Saint-Émilion classified-growths page; column indexing assumes a leading rank column that isn't always present. Regression test: after re-running the scraper, `select count(*) from facts where fact_text like '% is a classified Bordeaux estate in Château %' = 0`.

**14.2 Medium-term (Phase F, Template team worktree):**

- **Registry expansion:** add 10–12 new templates at `cognitive_dim=comprehension` (inference from the source fact, not entity recall) and 4–5 at `cognitive_dim=application` (apply fact rule to a novel scenario). Examples:
  - T-REG-TF-SOIL-01 (comp.) "True or False: the {soil_type} soils of {region} are better suited for {variety} than Chardonnay." (requires fact to have `{soil, grape, region}` triple)
  - T-GRP-TF-CLIMATE-01 (comp.) "True or False: {variety} is typically grown in {climate_descriptor} climates." (fact: `{variety, climate}`)
  - T-REG-APP-BLEND-01 (app.) "A winemaker in {region} is blending {variety_A} and {variety_B}. Which one is traditionally the dominant partner?" (fact encodes ordinal blend ratios)
  - T-WMK-APP-PROCESS-01 (app.) "For the style description '{style}', which maceration temperature is most appropriate?" (fact gives style→temp rule)

- **Minimum distinct-template-id floor:** `fill_template()` must ensure ≥25 distinct templates fire across the 1,000-question quota (vs current 11). If any cell is starved, log a `TemplateStarvationWarning`.

- **Opening phrase diversity within T/F templates:** the existing `γ-4 Phrasing diversification` has 4–6 paraphrase variants per template; gold-v3 showed all 3 T/F variants of the same template (`True or False:…` / `Decide True or False…` / `Indicate True or False…`) still read as "one pattern" to the reviewer. Add 3 more variants: interrogative (`Is it true that…?`), corrective (`Students sometimes say…; which is correct?`), and declarative (`The following statement is:…`). Ensure the variant hash picks across the full 7-variant space.

**14.3 Long-term (post-v2.3, before NeurIPS submission):**

- **Cognitive-dim quota per template strategy:** target 50% recall / 35% comprehension / 15% application. Parallel to domain targets but on the cognitive axis.
- **A4 re-measurement on new templates:** POS-bigram detectability AUC stays a gate (< 0.85). Paraphrase post-pass (v2.2 §6.3e) should still fire on the expanded registry.

### Verification gate

Phase F audit run #4 (`audit_pilot_v4`) and gold-v4:
- HHI on `template_id` distribution in the 120-template corpus slice: < 0.10 (v3 was ~0.13).
- Distinct template_ids firing: ≥ 25 (v3 was 11).
- Top template share: < 15% (v3 was 28%).
- No template question's source fact contains `"classified Bordeaux estate in Château"` or HTML table markup.
- Human gold-v4 spot-check (30 template Qs): pattern concentration subjectively acceptable (user sign-off).

### Decision log

- **Why not just drop template strategy to 0%?** The expanded comprehension/application registry (§14.2) turns templates into a controllable deterministic L2/L3 floor — something no LLM strategy guarantees. The fingerprint cost (A4 AUC) is manageable with paraphrase post-pass.
- **Why cap at 15% and not 10%?** 10% of 1,000 = 100 questions; insufficient for some well-populated domains (e.g. any comparative-variety template on Rhône blends). 15% gives headroom without any single pattern dominating a gold sample.
- **Why not measure by `question_type` instead of `template_id`?** question_type is too coarse (only MC/T-F); gold-v3's 12 templates were all T/F but from 3 paraphrases of ONE template — the diversity problem lives at the `template_id` level.
