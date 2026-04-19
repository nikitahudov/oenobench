# Gold-Standard Calibration Analysis

**Run ID:** `e8eba8bb-cb49-42cd-9e32-c741c987043e`
**Reviewer:** nikita (wine domain expert)
**Sample:** 60 questions, 12/strategy, sampled with seed 42
**Source:** `data/reports/gold_sheet_scored.csv` (committed in `ad58cf2`)

---

## TL;DR

The 60-question human review reveals **three findings the LLM-only audit could not surface**:

1. **Llama and Qwen produce 30–40% wrong-key questions, and the LLM tri-judge panel does not catch them** (B1 κ = -0.05 — judges agree with each other on the wrong answer because they all reason from the same flawed stem).
2. **B2 ClosedBookSolvability massively over-reports leakage** because the judge models (Opus 4.7, GPT-5.4, Gemini 3.1 Pro) are far more knowledgeable than the intended test-taker. Human says only 12% of questions are world-knowledge solvable; LLMs say 83%.
3. **A3 FactEcho's 73% fail/warn is heavily inflated by multi-fact strategies** where questions necessarily echo language from one of several source facts. After splitting by source-fact count, the real verbatim-copying problem is concentrated in single-fact strategies.

---

## 1 · Per-rubric pass rates (overall)

| Rubric | Pass | n | Pass % |
|---|---:|---:|---:|
| answer_correct | 54 | 60 | **90.0%** |
| needs_source | 53 | 60 | 88.3% |
| no_vague_language | 52 | 60 | 86.7% |
| cognitive_match | 52 | 60 | 86.7% |
| not_ambiguous | 48 | 60 | 80.0% |
| distractors_plausible | 45 | 60 | 75.0% |
| difficulty_match | 37 | 60 | **61.7%** |
| source_faithful | 26 | 60 | 43.3% (see §3 caveat) |

**Headline:** the keyed answer is correct in 90% of cases — the dataset's **factual** quality is high. The biggest weak spots are difficulty calibration (62%) and distractor plausibility (75%).

---

## 2 · Per-generator pass rates (the most actionable cut)

| Generator | n | answer_correct | distractors_plausible | not_ambiguous | needs_source | no_vague_language | difficulty_match | cognitive_match |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **claude** | 11 | **100%** | 100% | 91% | 100% | 100% | 64% | 91% |
| **chatgpt** | 8 | **100%** | 88% | 75% | 100% | 88% | 62% | 100% |
| **gemini** | 12 | **100%** | 100% | 92% | 100% | 92% | 83% | 83% |
| **template_only** | 12 | **100%** | 33% | 92% | 83% | 83% | 42% | 100% |
| **qwen** | 7 | **71%** | 71% | 57% | 71% | 86% | 43% | 86% |
| **llama** | 10 | **60%** | 60% | 60% | 70% | 70% | 70% | 60% |

### Critical: Llama and Qwen are the only generators producing wrong-keyed questions

All 6 `answer_correct = 0` rows are Llama (4) or Qwen (2). Claude, ChatGPT, Gemini, and the template strategy all scored 100% on this rubric. Reviewer notes mark three of the six as **"Completely incorrect"**.

### Critical: templates have the worst distractor quality (33% plausible)

The template strategy scores 100% on answer correctness but only 33% on distractor plausibility — distractors are sampled by entity-type matching alone with no semantic similarity check, so the wrong options are often trivially eliminable.

---

## 3 · The `source_faithful` caveat — split by source-fact count

The reviewer flagged this in the upload: the gold-sheet displays only ONE source fact per question, but multi-fact strategies (comparative, scenario, distractor) generate questions from 2–5 facts. The rubric was applied unfairly to those questions because the reviewer could not see the full evidence base.

**After splitting by actual source-fact count:**

| Source facts shown to LLM generator | Avg fact count | n | Pass | Pass % |
|---|---:|---:|---:|---:|
| Single-fact (`fact_to_question`, `template`) | 1.0 | 24 | 17 | **70.8%** |
| Multi-fact (`comparative`, `scenario`, `distractor`) | 2.0–5.2 | 36 | 9 | 25.0% |

The 70.8% pass on single-fact questions is the **true** source-faithfulness rate measured against complete evidence. The 25% multi-fact pass rate is **uninterpretable** — we cannot tell whether the questions are genuinely unfaithful or whether the reviewer simply lacked the additional source facts they were generated from.

**Per-strategy breakdown with average fact count:**

| Strategy | Avg facts | n | Pass | Pass % | Reliable? |
|---|---:|---:|---:|---:|---|
| fact_to_question | 1.0 | 12 | 11 | 91.7% | ✅ reliable |
| template | 1.0 | 12 | 6 | 50.0% | ✅ reliable |
| comparative | 2.0 | 12 | 4 | 33.3% | ⚠ partially blind |
| scenario_synthesis | 3.0 | 12 | 2 | 16.7% | ⚠ partially blind |
| distractor_mining | 5.2 | 12 | 3 | 25.0% | ⚠ partially blind |

**Action:** the next gold-sheet export must include all linked source facts (column or pipe-joined block), not just the first. Patch `src/qa/_corpus.export_gold_sheet` accordingly before audit run #2.

---

## 4 · LLM-judge ↔ human Cohen's κ — all four signals fail the κ ≥ 0.6 threshold

| Rubric | Agent (LLM proxy) | Human pass% | LLM pass% | Agreement | **κ** |
|---|---|---:|---:|---:|---:|
| answer_correct | B1 TriJudgeAnswer (majority_matches_key) | 90.0% | 96.7% | 86.7% | **-0.053** |
| needs_source | B2 ClosedBookSolvability (NOT closed-book correct) | 88.3% | 16.7% | 25.0% | **0.007** |
| no_vague_language | A1 LexicalHygiene (no regex match) | 86.7% | 100.0% | 86.7% | **0.000** |
| source_faithful | A3 FactEcho (LCS < 0.6) | 43.3% | 70.0% | 43.3% | **-0.076** |
| distractors_plausible | C2 CategoryLeak (no leaked distractor) | 75.0% | 95.0% | 76.7% | **0.152** |

**Per the report's own gating criterion (κ < 0.6 → downweight signal), every audited rubric must be downweighted.** Specifically:

### B1 TriJudgeAnswer — κ = -0.053 (worse than random)

The 6 questions humans flagged as wrong-key were ALL marked `majority_matches_key = True` by the tri-judge panel. This is a **systematic blind spot**: when Llama produces a question with a flawed stem, all three judges (Claude, ChatGPT, Gemini) reason from the same flawed stem and converge on the same wrong "correct" answer.

**Implication:** B1 cannot be the gating check for answer correctness. We need an **independent** verification — e.g., have judges answer the question both with and without the source fact and check whether the with-source answer changes (true-correct questions should flip to the keyed answer when the source is provided; flawed-stem questions show no flip).

### B2 ClosedBookSolvability — κ = 0.007 (no agreement)

Human says 88% of questions need the source fact. LLMs say only 17% need it (i.e., judges solved 83% closed-book). This is **judge-capability bias**: Opus 4.7, GPT-5.4, and Gemini 3.1 Pro know far more wine than the typical certified-sommelier or master-of-wine candidate the benchmark targets.

**Implication:** the audit's "30% closed-book leakage" finding is overstated. The real leakage rate (against an actual test-taker) is closer to 12%. We should still rewrite stems that judges easily solve, but the Go/No-Go threshold should be re-tuned (e.g., "<10% leakage on level-3+ questions when measured by a calibrated test-taker model" rather than "<50% by Opus/GPT-5").

### A3 FactEcho — κ = -0.076 (anti-correlated)

LCS-based echo detection mostly disagrees with human source-faithfulness judgments. Two reasons:
1. The multi-fact source-faithful caveat (§3): humans flagged 75% of multi-fact Qs as unfaithful because they couldn't see all evidence; A3 only looked at the linked facts and many had high LCS.
2. A high LCS to a source fact means the question echoes the source — that's actually a sign of faithfulness in many cases, not a violation. The real defect "verbatim copying" is a quality concern (plagiarism / makes the question trivially answerable by string matching), not a faithfulness concern.

**Implication:** A3's interpretation needs to flip. High-LCS questions are not unfaithful — they are mechanically lazy. Re-frame the agent as `A3 LazyParaphrase` and keep the gate threshold.

### A1 LexicalHygiene — κ = 0.000

A1 flagged 0% of the 60 gold questions; human flagged 13%. Regex misses subtle phrasings reviewer caught.

**Implication:** harvest the human's `notes` from the 8 vague-flagged Qs and add those phrases to `_VAGUE_PATTERNS`.

### C2 CategoryLeak — κ = 0.152 (low but positive)

C2 only catches wine-category leaks (sparkling distractor in red question). Human's `distractors_plausible` rubric is much broader. They're measuring different things, so low κ is expected.

---

## 5 · Specific failures the audit missed

The 6 wrong-key questions all have `B1 majority_matches_key = True`:

| public_qid | Generator | Strategy | Judge majority | Human note |
|---|---|---|---|---|
| WB-GRP-0042-L3 | llama | comparative | D | "More than one source fact required" |
| WB-VIT-0074-L3 | qwen | distractor_mining | C | (no note) |
| WB-VIT-0035-L2 | qwen | comparative | A | "Completely incorrect" |
| WB-REG-0058-L2 | llama | scenario_synthesis | D | (no note) |
| WB-VIT-0068-L3 | llama | distractor_mining | A | "Completely incorrect" |
| WB-VIT-0051-L2 | llama | scenario_synthesis | A | "Completely incorrect" |

These are exactly the questions the benchmark cannot ship with — and the audit greenlit all six.

---

## 6 · Updates to the Generation Improvement Plan

The gold review elevates one defect that didn't exist in the original plan and re-prioritises others. **Apply these on top of the existing plan in `docs/GENERATION_IMPROVEMENT_PLAN.md`.**

### NEW defect #0 (highest priority): Llama/Qwen wrong-key generation

- **Evidence:** 60% / 71% answer_correct on Llama/Qwen vs 100% on Claude/ChatGPT/Gemini in the gold review. B1 LLM-judge cannot catch it (κ = -0.05).
- **Proposed fix:** any of the following, in increasing order of cost
  - **(S, recommended)** Drop Llama and Qwen from generator rotation; redistribute their 3,000-question quota across Claude, ChatGPT, Gemini.
  - **(M)** Keep Llama and Qwen but add a **post-LLM verification step**: after generation, ask a second model (different family) to answer the question with and without the source. If the with-source answer doesn't match the key, flag for human review.
  - **(L)** Add a B5 `IndependentSolver` audit agent that uses a single high-capability judge to re-solve every question with source visible; reject any question where the judge disagrees with the key.
- **Verification:** human re-review of a 60-Q sample after re-generation; target answer_correct ≥ 95% per generator.

### Reprioritised: A3 FactEcho

The 35% fail rate is real for single-fact strategies but inflated for multi-fact ones. Re-frame as a "no verbatim copying" rule, narrow to fact_to_question + template, and keep the LCS<0.6 threshold.

### Reprioritised: B2 ClosedBookSolvability

LLM-judge bias means the 30% fail rate is overstated. Either:
- Use Llama/Qwen as the closed-book judge (weaker world knowledge, closer to test-taker capability), OR
- Calibrate the threshold against the human gold (12% leakage in our 60-Q sample → set the gate at "<15% leakage" instead of "<50%").

### Reprioritised: source_faithful

Patch `_corpus.export_gold_sheet` to show all linked facts before the next gold review. Until that patch lands, the audit's source-faithful signal for multi-fact strategies is uninterpretable.

### NEW defect: Difficulty calibration (62% match)

Levels 1–4 are mislabeled in 38% of questions per human review. Likely root cause: the generators don't observe difficulty distribution as a soft constraint — they accept whatever the LLM produces.

- **Proposed fix:** post-generation difficulty re-classifier (small LLM call) that re-rates each question and either (a) updates the difficulty label or (b) rejects mis-labeled questions during sampling for the final 10k.

### NEW defect: Distractor plausibility for templates (33% pass)

Template-strategy distractors are entity-type-matched but not semantically similar.

- **Proposed fix:** improve template distractor sampling to use embedding similarity (pgvector) within the entity type, picking near-neighbors instead of random matches.

---

## 7 · Go/No-Go gate revisions

The original gate (`docs/GENERATION_IMPROVEMENT_PLAN.md`) treats LLM-judge findings as authoritative. After this calibration, several gates should be revised:

| Gate | Original | Revised |
|---|---|---|
| B1 majority-matches-key rate | ≥ 95% | **≥ 95% AND human-spot-check ≥ 95% per generator** |
| B2 closed-book leakage | < 50% | **< 15% calibrated** (or measured by Llama/Qwen as judge) |
| A3 fail rate | < 2% | **< 2% on single-fact strategies; multi-fact gated by re-evaluation with all facts shown** |
| _NEW_: per-generator answer_correct (human spot-check ≥ 30 Qs) | n/a | **≥ 95% for every generator in the rotation** |
| _NEW_: difficulty_match (human spot-check) | n/a | **≥ 80%** |

---

## 8 · Reviewer effort & cost

- Time spent: ~2 hours (estimated from sheet upload time vs export time)
- Cost: $0 (offline manual review)
- Returns: surfaced **the most important defect in the entire audit** (Llama/Qwen wrong-key rate undetected by LLM judges) for the price of an afternoon

The gold-set will pay off again on every future audit run by re-calibrating the LLM-judge κ. Keep the same 60-question split (or rotate to a fresh sample if any get used as in-context examples).

---

*Generated 2026-04-19 from `data/reports/gold_sheet_scored.csv` and `audit_findings` for run `e8eba8bb-cb49-42cd-9e32-c741c987043e`.*
