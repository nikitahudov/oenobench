# OenoBench Generation Improvement Plan

- Run ID: `7dc2ab81-bc9a-40b1-a1a4-3ddf66a6e6fe`
- Corpus tag: `audit_pilot_v8`
- Generated: 2026-04-28T21:16:46.016521

## Prioritised defects

Ranked by impact = `3·fails + 1·warns + 2·errors`. Effort S ≈ <1d, M ≈ 1-3d, L ≈ 3-7d.

### Question solvable from world knowledge (easy leakage)  ·  impact 169  ·  effort M

- Agent: `B2_ClosedBookSolvability`
- Severity: fail=50, warn=19, error=0
- Affected: fact_to_question (most), template.
- Proposed fix: Raise difficulty target for leaking questions; rewrite stems to use provided fact-specific terminology rather than famous-entity references.
- Verification: B2 leakage ratio < 0.5 of judges (5-judge panel: claude/chatgpt/gemini/llama/qwen).
- Example question UUIDs: 39503090-e3f3-41b2-a6f1-4de3a5d40b16, 6c11c109-b45b-4c27-bc0f-679aaa3cc0e9, e123784e-9e78-48eb-be1a-20d3b0f43e10, b48635ad-d454-480a-a8c0-8924be69f403, ea43d993-799c-4e72-be4c-7e9dc0e54760

### Verbatim source copying in question text  ·  impact 56  ·  effort S

- Agent: `A3_FactEcho`
- Severity: fail=0, warn=56, error=0
- Affected: fact_to_question, scenario_synthesis.
- Proposed fix: Add a prompt instruction in `_prompts.py`: 'Paraphrase the fact — never copy >5 consecutive words verbatim.' Add a post-LLM reject if LCS ratio > 0.6.
- Verification: A3 fail rate drops below 2% on regenerated batch.
- Example question UUIDs: 39503090-e3f3-41b2-a6f1-4de3a5d40b16, f7a122ba-84e9-4380-81c3-fc4501d1e4b6, baac31a4-5f84-4a42-8981-dff5672a8e82, 6c11c109-b45b-4c27-bc0f-679aaa3cc0e9, e123784e-9e78-48eb-be1a-20d3b0f43e10

### Key disagrees with judge consensus / source fact  ·  impact 16  ·  effort L

- Agent: `B1_TriJudgeAnswer`
- Severity: fail=1, warn=13, error=0
- Affected: All LLM strategies.
- Proposed fix: Root-cause per example: (a) fact hallucination → tighten 'use ONLY provided fact' instruction; (b) ambiguous key → add B4 and human review; (c) option swap bug → audit `_schemas.py` shuffle logic.
- Verification: B1 fail rate < 5% in follow-up run; rebuild failing questions.
- Example question UUIDs: b51d5a12-5eed-4a90-beeb-a8dff5896907, dee0ac6f-0347-4c69-8410-75e3363558c9, e4ca44ee-9501-4850-b6d4-2638650ec88a, 4cb191c7-71a0-4a31-85e9-ba5c64a90991, dd5f41b8-b82c-4380-99e9-c501936d5f2d

### Model scores disproportionately well on its own questions  ·  impact 3  ·  effort L

- Agent: `D1_SelfPreference`
- Severity: fail=1, warn=0, error=0
- Affected: Dataset composition.
- Proposed fix: Rebalance final dataset so each model's share is capped at 22% (prevent dominance). Consider dropping the highest-SP model if delta ≥ 0.15.
- Verification: D1 delta < 0.07 across all 5 evaluators in follow-up run.

### Vague / marketing / blend-as-variety phrasing  ·  impact 3  ·  effort S

- Agent: `A1_LexicalHygiene`
- Severity: fail=1, warn=0, error=0
- Affected: All LLM strategies.
- Proposed fix: Extend `_VAGUE_PATTERNS` and `_BLEND_AS_VARIETY` regexes with the matched phrases; add post-LLM filter in `_schemas.py` that rejects questions whose stem or options contain any blocked phrase.
- Verification: Fixture questions with each blocked phrase should score fail in A1.
- Example question UUIDs: 7541a694-a6c1-4407-b6a2-20177e69671b

### Distractor wine-category mismatch  ·  impact 2  ·  effort S

- Agent: `C2_CategoryLeak`
- Severity: fail=0, warn=2, error=0
- Affected: fact_to_question, comparative, scenario_synthesis.
- Proposed fix: Make `_classify_wine_category` mandatory for ALL distractor sampling (not just distractor_miner); reject mismatched distractors in sampler layer.
- Verification: C2 fail count == 0 on regenerated batch.
- Example question UUIDs: 9d483655-67fa-4069-b607-7d987ee424ee, 41a121c1-4c3a-4960-b951-6743056cfdfd

### Template questions statistically distinguishable from LLM ones  ·  impact 2  ·  effort M

- Agent: `A4_TemplateFingerprint`
- Severity: fail=0, warn=2, error=0
- Affected: template.
- Proposed fix: Diversify template phrasings (rotate opening verbs, add filler, vary punctuation). If AUC remains high, reduce template share of the final corpus.
- Verification: Re-run A4 after template edits; AUC target < 0.85.
- Example question UUIDs: 8c59e839-61e1-4eb5-aaba-90272b1f39a8

### Geographic or subdomain over-representation  ·  impact 1  ·  effort M

- Agent: `D3_SkewAudit`
- Severity: fail=0, warn=1, error=0
- Affected: All strategies.
- Proposed fix: Add per-country quota to `_fact_sampler.sample_facts`; or sample facts inversely weighted by country frequency. Reduce Portugal / France over-sampling.
- Verification: D3 max over-representation ratio < 1.5.

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
