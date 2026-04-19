# OenoBench Generation Improvement Plan

- Run ID: `3c6e27ce-62fa-4c1b-bd0e-3958161a0082`
- Corpus tag: `audit_pilot_v2`
- Generated: 2026-04-19T20:42:10.834873

## Prioritised defects

Ranked by impact = `3·fails + 1·warns + 2·errors`. Effort S ≈ <1d, M ≈ 1-3d, L ≈ 3-7d.

### Question solvable from world knowledge (easy leakage)  ·  impact 423  ·  effort M

- Agent: `B2_ClosedBookSolvability`
- Severity: fail=111, warn=90, error=0
- Affected: fact_to_question (most), template.
- Proposed fix: Raise difficulty target for leaking questions; rewrite stems to use provided fact-specific terminology rather than famous-entity references.
- Verification: B2 leakage ratio < 0.5 of judges (5-judge panel: claude/chatgpt/gemini/llama/qwen).
- Example question UUIDs: 61ac0c67-c7e1-4a50-95e4-2c203f83a897, 8b8b3d1d-4c71-416e-90e3-ff57dbd7de90, a4f78e44-4556-4db9-943b-42c81416a753, 2484bb3a-64a8-4191-a948-90b19bd02f07, f9ecbbf1-e6c5-4518-b114-62ef2d66a331

### C4_DifficultyAudit  ·  impact 422  ·  effort M

- Agent: `C4_DifficultyAudit`
- Severity: fail=105, warn=101, error=3
- Affected: unknown
- Proposed fix: Investigate findings manually.
- Verification: Re-run audit after fix.
- Example question UUIDs: 61ac0c67-c7e1-4a50-95e4-2c203f83a897, 9569c479-65ff-407d-bde8-f657cdedffcf, 727c4bd6-60f1-4732-acfe-1f8d595a6f31, 7badd4c7-6781-457c-b2e5-77650e34b991, b79bf8ff-6df0-4cd6-a129-b3018f44b8f4

### Verbatim source copying in question text  ·  impact 183  ·  effort S

- Agent: `A3_FactEcho`
- Severity: fail=17, warn=132, error=0
- Affected: fact_to_question, scenario_synthesis.
- Proposed fix: Add a prompt instruction in `_prompts.py`: 'Paraphrase the fact — never copy >5 consecutive words verbatim.' Add a post-LLM reject if LCS ratio > 0.6.
- Verification: A3 fail rate drops below 2% on regenerated batch.
- Example question UUIDs: 61ac0c67-c7e1-4a50-95e4-2c203f83a897, 9569c479-65ff-407d-bde8-f657cdedffcf, e740a4b5-aa63-449e-9769-0d0bf088702b, 4ee226b4-d2c6-4a2e-9d21-3fe2ba42722a, ecdab857-b3af-466d-8d73-1a7ced893970

### Key disagrees with judge consensus / source fact  ·  impact 56  ·  effort L

- Agent: `B1_TriJudgeAnswer`
- Severity: fail=8, warn=32, error=0
- Affected: All LLM strategies.
- Proposed fix: Root-cause per example: (a) fact hallucination → tighten 'use ONLY provided fact' instruction; (b) ambiguous key → add B4 and human review; (c) option swap bug → audit `_schemas.py` shuffle logic.
- Verification: B1 fail rate < 5% in follow-up run; rebuild failing questions.
- Example question UUIDs: 6ac4b29c-d87a-4fc1-bf0b-68960bf809f6, b79bf8ff-6df0-4cd6-a129-b3018f44b8f4, 9569c479-65ff-407d-bde8-f657cdedffcf, 727c4bd6-60f1-4732-acfe-1f8d595a6f31, 7badd4c7-6781-457c-b2e5-77650e34b991

### Vague / marketing / blend-as-variety phrasing  ·  impact 54  ·  effort S

- Agent: `A1_LexicalHygiene`
- Severity: fail=14, warn=12, error=0
- Affected: All LLM strategies.
- Proposed fix: Extend `_VAGUE_PATTERNS` and `_BLEND_AS_VARIETY` regexes with the matched phrases; add post-LLM filter in `_schemas.py` that rejects questions whose stem or options contain any blocked phrase.
- Verification: Fixture questions with each blocked phrase should score fail in A1.
- Example question UUIDs: 30eb6dd2-1a34-4400-b34b-e0be7ce30f32, 9d9122cb-f8a3-4ff8-8d6e-002ba17435fb, 1be43c25-f0b8-46a7-8b51-5034045ff719, 29f64644-7552-4c62-a873-818e254b9346, 85a7b621-41e2-4a7b-9805-59d020ad1806

### Template questions statistically distinguishable from LLM ones  ·  impact 48  ·  effort M

- Agent: `A4_TemplateFingerprint`
- Severity: fail=15, warn=3, error=0
- Affected: template.
- Proposed fix: Diversify template phrasings (rotate opening verbs, add filler, vary punctuation). If AUC remains high, reduce template share of the final corpus.
- Verification: Re-run A4 after template edits; AUC target < 0.85.
- Example question UUIDs: 5f06483d-0b9b-4e7b-b02f-09e20d19f83e, 6ec5cd45-4496-42a6-8372-59570cf63d5e, b4d99041-9644-4b40-b2d7-174ca11e6b68, 51f2ede5-b775-4f5c-8414-3f97960e954d, 7d01ea00-6517-4ad8-a37a-23bb7f23d3e1

### Distractor wine-category mismatch  ·  impact 10  ·  effort S

- Agent: `C2_CategoryLeak`
- Severity: fail=3, warn=1, error=0
- Affected: fact_to_question, comparative, scenario_synthesis.
- Proposed fix: Make `_classify_wine_category` mandatory for ALL distractor sampling (not just distractor_miner); reject mismatched distractors in sampler layer.
- Verification: C2 fail count == 0 on regenerated batch.
- Example question UUIDs: 56a2f53d-d18e-4c2c-beb2-497719af6ac6, 4e13012b-b375-4582-a85f-778fbeda1a2d, 39e5923a-88c7-4651-8376-775ec94ecc15, 34188854-0638-4469-9d5f-e2d45f6f6220

### Geographic or subdomain over-representation  ·  impact 3  ·  effort M

- Agent: `D3_SkewAudit`
- Severity: fail=1, warn=0, error=0
- Affected: All strategies.
- Proposed fix: Add per-country quota to `_fact_sampler.sample_facts`; or sample facts inversely weighted by country frequency. Reduce Portugal / France over-sampling.
- Verification: D3 max over-representation ratio < 1.5.

### Correct-answer position / length bias  ·  impact 3  ·  effort M

- Agent: `A2_BiasStats`
- Severity: fail=1, warn=0, error=0
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
