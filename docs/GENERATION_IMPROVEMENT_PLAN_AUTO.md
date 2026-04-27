# OenoBench Generation Improvement Plan

- Run ID: `9ba6f760-5a6c-4403-9709-412c13eac30c`
- Corpus tag: `audit_pilot_v7`
- Generated: 2026-04-27T09:41:08.248946

## Prioritised defects

Ranked by impact = `3·fails + 1·warns + 2·errors`. Effort S ≈ <1d, M ≈ 1-3d, L ≈ 3-7d.

### Question solvable from world knowledge (easy leakage)  ·  impact 421  ·  effort M

- Agent: `B2_ClosedBookSolvability`
- Severity: fail=128, warn=37, error=0
- Affected: fact_to_question (most), template.
- Proposed fix: Raise difficulty target for leaking questions; rewrite stems to use provided fact-specific terminology rather than famous-entity references.
- Verification: B2 leakage ratio < 0.5 of judges (5-judge panel: claude/chatgpt/gemini/llama/qwen).
- Example question UUIDs: a6bd0c45-713c-4b59-a579-c0f803197dd8, e9b1c3c4-ffa8-4bbf-ae75-2b4b4ec8ea3c, 5bea9a41-e306-4371-a8d9-9b3b405fadd8, 32202c60-7810-426b-a90a-8256f7a66eb2, e5713209-ce9a-4d13-8280-7bd2bb4fe8c7

### Template questions statistically distinguishable from LLM ones  ·  impact 300  ·  effort M

- Agent: `A4_TemplateFingerprint`
- Severity: fail=85, warn=45, error=0
- Affected: template.
- Proposed fix: Diversify template phrasings (rotate opening verbs, add filler, vary punctuation). If AUC remains high, reduce template share of the final corpus.
- Verification: Re-run A4 after template edits; AUC target < 0.85.
- Example question UUIDs: 474f183a-685a-45c0-a9d3-cf96c1b86823, f9e2eaaf-f025-4232-bda3-862047357eb1, 58b1c854-4094-44c5-9505-28de76520608, 82b86b72-03d5-48d3-b1d7-5e7fbf1c108f, c38a44ae-5a23-4ad5-9c7f-507ba34f9ac1

### Verbatim source copying in question text  ·  impact 114  ·  effort S

- Agent: `A3_FactEcho`
- Severity: fail=4, warn=102, error=0
- Affected: fact_to_question, scenario_synthesis.
- Proposed fix: Add a prompt instruction in `_prompts.py`: 'Paraphrase the fact — never copy >5 consecutive words verbatim.' Add a post-LLM reject if LCS ratio > 0.6.
- Verification: A3 fail rate drops below 2% on regenerated batch.
- Example question UUIDs: e9b1c3c4-ffa8-4bbf-ae75-2b4b4ec8ea3c, e5713209-ce9a-4d13-8280-7bd2bb4fe8c7, 36c1775c-2cbf-4c88-bbf5-9d49a216e502, 063bcbfc-a27f-4eb8-ae81-5d61f45191de, f58ca79e-b27a-4205-84e6-f1f7928936e4

### Vague / marketing / blend-as-variety phrasing  ·  impact 28  ·  effort S

- Agent: `A1_LexicalHygiene`
- Severity: fail=7, warn=7, error=0
- Affected: All LLM strategies.
- Proposed fix: Extend `_VAGUE_PATTERNS` and `_BLEND_AS_VARIETY` regexes with the matched phrases; add post-LLM filter in `_schemas.py` that rejects questions whose stem or options contain any blocked phrase.
- Verification: Fixture questions with each blocked phrase should score fail in A1.
- Example question UUIDs: ddf60bd8-322f-44ff-8ed6-3d95d3e0db6d, 75113407-4515-46d4-87d1-0f435400fb14, 013409d1-bfc8-44e5-a33e-f3ab165855c3, bd62e7de-a263-400c-a300-cdb495becff8, a5564a29-0a20-46e8-871e-601cfd45df97

### Key disagrees with judge consensus / source fact  ·  impact 17  ·  effort L

- Agent: `B1_TriJudgeAnswer`
- Severity: fail=2, warn=11, error=0
- Affected: All LLM strategies.
- Proposed fix: Root-cause per example: (a) fact hallucination → tighten 'use ONLY provided fact' instruction; (b) ambiguous key → add B4 and human review; (c) option swap bug → audit `_schemas.py` shuffle logic.
- Verification: B1 fail rate < 5% in follow-up run; rebuild failing questions.
- Example question UUIDs: d022e2c5-a537-4eed-babd-e725a90c453e, 2def76dc-a43f-4c89-8ba5-90f8a66d6d3e, 9c54484a-8e95-498b-bed3-1c35be61537e, 4fddaa20-8cb7-4058-b7ae-17ba5960e22a, 245d1202-8221-4d37-a428-25bd28623f59

### Distractor wine-category mismatch  ·  impact 5  ·  effort S

- Agent: `C2_CategoryLeak`
- Severity: fail=0, warn=5, error=0
- Affected: fact_to_question, comparative, scenario_synthesis.
- Proposed fix: Make `_classify_wine_category` mandatory for ALL distractor sampling (not just distractor_miner); reject mismatched distractors in sampler layer.
- Verification: C2 fail count == 0 on regenerated batch.
- Example question UUIDs: f291c690-b07f-4d81-8188-da27d0610af5, 14b6840c-c2db-42f2-a68a-ebee2ed55914, 70626b54-eb5a-476c-9e14-3e7731a7f3c6, 1475af73-4526-4236-95f3-a2263a4c4e5e, c7f67437-dd93-4379-b100-23420c5e5390

### Geographic or subdomain over-representation  ·  impact 3  ·  effort M

- Agent: `D3_SkewAudit`
- Severity: fail=1, warn=0, error=0
- Affected: All strategies.
- Proposed fix: Add per-country quota to `_fact_sampler.sample_facts`; or sample facts inversely weighted by country frequency. Reduce Portugal / France over-sampling.
- Verification: D3 max over-representation ratio < 1.5.

### Model scores disproportionately well on its own questions  ·  impact 3  ·  effort L

- Agent: `D1_SelfPreference`
- Severity: fail=1, warn=0, error=0
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
