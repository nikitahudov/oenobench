# OenoBench Generation Improvement Plan

- Run ID: `9045e16d-1466-476f-97dc-3126550f22c4`
- Corpus tag: `audit_pilot_v13`
- Generated: 2026-05-01T19:59:32.102543

## Prioritised defects

Ranked by impact = `3·fails + 1·warns + 2·errors`. Effort S ≈ <1d, M ≈ 1-3d, L ≈ 3-7d.

### Question solvable from world knowledge (easy leakage)  ·  impact 176  ·  effort M

- Agent: `B2_ClosedBookSolvability`
- Severity: fail=45, warn=41, error=0
- Affected: fact_to_question (most), template.
- Proposed fix: Raise difficulty target for leaking questions; rewrite stems to use provided fact-specific terminology rather than famous-entity references.
- Verification: B2 leakage ratio < 0.5 of judges (5-judge panel: claude/chatgpt/gemini/llama/qwen).
- Example question UUIDs: 95c7744b-5a2d-4561-812d-9f48ae923601, edee7a76-61f4-4c0f-bc1e-cab4347265f6, 5284ed13-51c1-4ccf-973b-106c94a90326, c9ffb4b7-81a6-459a-81d8-81c93c6ae53f, 5c15619f-4801-43d9-8c2a-fcf5b9abcdc8

### Verbatim source copying in question text  ·  impact 77  ·  effort S

- Agent: `A3_FactEcho`
- Severity: fail=6, warn=59, error=0
- Affected: fact_to_question, scenario_synthesis.
- Proposed fix: Add a prompt instruction in `_prompts.py`: 'Paraphrase the fact — never copy >5 consecutive words verbatim.' Add a post-LLM reject if LCS ratio > 0.6.
- Verification: A3 fail rate drops below 2% on regenerated batch.
- Example question UUIDs: 95c7744b-5a2d-4561-812d-9f48ae923601, 844a8825-3499-4769-ba3d-40694421a612, 321ec8f2-3345-4637-86d9-f21d608d66cc, 6cd33cae-d766-4d0d-ba10-cf6c3d52245d, b6fbd17d-6d32-405d-84c8-894e4e1e4fdc

### Template questions statistically distinguishable from LLM ones  ·  impact 36  ·  effort M

- Agent: `A4_TemplateFingerprint`
- Severity: fail=9, warn=9, error=0
- Affected: template.
- Proposed fix: Diversify template phrasings (rotate opening verbs, add filler, vary punctuation). If AUC remains high, reduce template share of the final corpus.
- Verification: Re-run A4 after template edits; AUC target < 0.85.
- Example question UUIDs: ab7c0695-f22c-45fa-9103-40d0987fe34f, 1c94632d-d153-4e5e-8435-162b873fd106, 39c3566e-2816-40cd-8040-db78e7a78472, 34700e7a-246a-42fa-8a18-dcfba758747c, c992d73e-5446-4914-bd79-4dd356e23c73

### Vague / marketing / blend-as-variety phrasing  ·  impact 14  ·  effort S

- Agent: `A1_LexicalHygiene`
- Severity: fail=4, warn=2, error=0
- Affected: All LLM strategies.
- Proposed fix: Extend `_VAGUE_PATTERNS` and `_BLEND_AS_VARIETY` regexes with the matched phrases; add post-LLM filter in `_schemas.py` that rejects questions whose stem or options contain any blocked phrase.
- Verification: Fixture questions with each blocked phrase should score fail in A1.
- Example question UUIDs: a4e97822-80c9-488d-90a7-6b00c4017a95, d5ac3c08-732a-4d0c-a293-1ca3465f846d, 95a7385c-9627-4ff4-8c0a-d2adc04bb2cc, c6d990f4-8bed-49d4-b461-6104daff2706, c657c830-89a6-4fb2-a2f6-f2d3c4be59a9

### Distractor wine-category mismatch  ·  impact 9  ·  effort S

- Agent: `C2_CategoryLeak`
- Severity: fail=2, warn=3, error=0
- Affected: fact_to_question, comparative, scenario_synthesis.
- Proposed fix: Make `_classify_wine_category` mandatory for ALL distractor sampling (not just distractor_miner); reject mismatched distractors in sampler layer.
- Verification: C2 fail count == 0 on regenerated batch.
- Example question UUIDs: f78d23ab-4a7c-4da5-84a4-4cbee76a2bed, 3f470557-3705-4a4f-916d-b4aa594d4ff7, f1302a8b-70cb-4adf-9b52-1577a44ff36a, c657c830-89a6-4fb2-a2f6-f2d3c4be59a9, 26608ac0-d1c0-4743-b995-077efbed4d78

### Key disagrees with judge consensus / source fact  ·  impact 8  ·  effort L

- Agent: `B1_TriJudgeAnswer`
- Severity: fail=0, warn=8, error=0
- Affected: All LLM strategies.
- Proposed fix: Root-cause per example: (a) fact hallucination → tighten 'use ONLY provided fact' instruction; (b) ambiguous key → add B4 and human review; (c) option swap bug → audit `_schemas.py` shuffle logic.
- Verification: B1 fail rate < 5% in follow-up run; rebuild failing questions.
- Example question UUIDs: 844a8825-3499-4769-ba3d-40694421a612, a741379b-e623-47ab-a750-945dd3b52231, c0f236f7-ca04-4858-b57d-fd799ada5d3d, 9e056d57-1674-4787-82d7-13d6e896aabb, c5c97ee4-c8d7-4141-911a-6b45336131fa

### Geographic or subdomain over-representation  ·  impact 1  ·  effort M

- Agent: `D3_SkewAudit`
- Severity: fail=0, warn=1, error=0
- Affected: All strategies.
- Proposed fix: Add per-country quota to `_fact_sampler.sample_facts`; or sample facts inversely weighted by country frequency. Reduce Portugal / France over-sampling.
- Verification: D3 max over-representation ratio < 1.5.

### Model scores disproportionately well on its own questions  ·  impact 1  ·  effort L

- Agent: `D1_SelfPreference`
- Severity: fail=0, warn=1, error=0
- Affected: Dataset composition.
- Proposed fix: Rebalance final dataset so each model's share is capped at 22% (prevent dominance). Consider dropping the highest-SP model if delta ≥ 0.15.
- Verification: D1 delta < 0.07 across all 5 evaluators in follow-up run.

### Correct-answer position / length bias  ·  impact 1  ·  effort M

- Agent: `A2_BiasStats`
- Severity: fail=0, warn=1, error=0
- Affected: All MC strategies.
- Proposed fix: Ensure `_schemas.py` option-shuffle runs before DB insert; if length bias persists, add a length-normaliser to post-LLM validator that pads / trims distractor texts.
- Verification: After fix, A2 χ² p-value > 0.2 on any (strategy,generator) cell with n ≥ 20.

## Regeneration Go/No-Go checklist

Do NOT start the full 10k generation run until ALL of these hold on the next audit pass:

- [ ] A1 fail rate **< 2%**
- [ ] A2 position-bias p > 0.2 in every (strategy, generator) cell with n ≥ 20
- [ ] A3 fail rate **< 2%**, no question with contiguous n-gram ≥ 8 tokens
- [ ] A4 held-out AUC **< 0.85**
- [ ] B1 majority-matches-key rate **≥ 95%**, fact-supports ratio ≥ 0.9
- [ ] B2 closed-book leakage ratio **< 0.5** on Level-3/4 questions
- [ ] C2 category-leak fail count **= 0**
- [ ] D1 self-preference |Δ| **< 0.07** across all 5 evaluator models
- [ ] D3 max country over-representation ratio **< 1.5**

If any box fails twice in a row, escalate to the deferred agents (C1, B3, B4, C3, C4, D2).
