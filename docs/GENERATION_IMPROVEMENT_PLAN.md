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

## 0 · Reweighted generator allocation (REVISED v2.1)

The original plan distributed LLM questions equally across the five generators. The gold review shows quality is **not** uniform — and a deeper template-strategy audit (see new §6) reveals templates have systemic structural defects despite their 100% answer-correctness.

| Generator | Gold-review answer_correct | Other major issues | Action |
|---|---:|---|---|
| **Claude Opus 4.7** | 100% | none material | scale up |
| **ChatGPT 5.4** | 100% | none material | scale up |
| **Gemini 3.1 Pro** | 100% | none material | scale up |
| **Qwen 3 235B** | 71% | wrong-key generation | scale down + verify |
| **Llama 3.1 405B** | 60% | wrong-key generation | scale down + verify |
| Template (deterministic) | 100% | distractor 33%, difficulty 42%, source-faithful 50%, A4 AUC 0.96 — see §6 | **scale down sharply** |

### Proposed final-corpus allocation (v2.1)

| Generator | v1 % | v2 % | **v2.1 %** | v1 count | v2 count | **v2.1 count** | Notes |
|---|---:|---:|---:|---:|---:|---:|---|
| Template | 25.0 | 25.0 | **10.0** | 2,500 | 2,500 | **1,000** | Cut from 25% to 10% per gold review — see §6 overhaul |
| Claude | 15.0 | 20.0 | **24.0** | 1,500 | 2,000 | **2,400** | Absorb template share |
| ChatGPT | 15.0 | 20.0 | **24.0** | 1,500 | 2,000 | **2,400** | Absorb template share |
| Gemini | 10.0 | 20.0 | **24.0** | 1,000 | 2,000 | **2,400** | Absorb template share — best-rated by domain expert |
| Qwen | 17.5 | 9.0 | **11.0** | 1,750 | 900 | **1,100** | Slight bump; still gated by verifier |
| Llama | 17.5 | 6.0 | **7.0** | 1,750 | 600 | **700** | Slight bump; still gated by verifier |
| **TOTAL** | 100.0 | 100.0 | **100.0** | 10,000 | 10,000 | **10,000** | Max 24% any model (under the 35% ceiling) |

Rationale:
- The three high-quality LLMs each go to 24% (just under the 25% mark, well under the 35% cap), giving 72% of questions to verifiably-correct generators.
- Template share drops from 2,500 → 1,000. Templates retained as a deterministic floor for L1-recall coverage of well-defined entities (regions, grapes, producers); the §6 overhaul fixes the structural defects so the remaining 1,000 are actually defensible.
- Llama and Qwen get a small bump (combined 18% → 1,800 questions) absorbing some of the template cut, since their output goes through the verifier and surviving questions match the quality of the other LLMs.
- All allocations encoded in `src/generators/orchestrator.py:GENERATOR_TARGETS` and `STRATEGY_TARGETS["template"]`.

### Implementation
```python
# src/generators/orchestrator.py
STRATEGY_TARGETS = {
    "fact_to_question":   4500,   # +500 vs v1
    "template":           1000,   # -1500 vs v1
    "comparative":        1500,
    "scenario_synthesis": 1500,   # +500 vs v1
    "distractor_mining":  1500,   # +500 vs v1
}

# Per-LLM targets (LLM strategies share 9,000 questions across 5 models)
GENERATOR_TARGETS = {
    "claude":  2400,
    "chatgpt": 2400,
    "gemini":  2400,
    "qwen":    1100,
    "llama":    700,
}
# Sum = 9,000 = template (1,000) total to 10,000.
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
