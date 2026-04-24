# OenoBench Generation Improvement Plan

- Run ID: `4e3ead78-2b62-4733-919d-bf3f4878aaec`
- Corpus tag: `audit_pilot_v4`
- Generated: 2026-04-24T01:24:46.826811

## Prioritised defects

Ranked by impact = `3·fails + 1·warns + 2·errors`. Effort S ≈ <1d, M ≈ 1-3d, L ≈ 3-7d.

### Question solvable from world knowledge (easy leakage)  ·  impact 487  ·  effort M

- Agent: `B2_ClosedBookSolvability`
- Severity: fail=124, warn=115, error=0
- Affected: fact_to_question (most), template.
- Proposed fix: Raise difficulty target for leaking questions; rewrite stems to use provided fact-specific terminology rather than famous-entity references.
- Verification: B2 leakage ratio < 0.5 of judges (5-judge panel: claude/chatgpt/gemini/llama/qwen).
- Example question UUIDs: 486ad243-d07b-4a73-b793-5c7a163eec58, 8dc45402-c4d0-4469-8698-ff75d264c54d, 040aba52-ca07-4584-a7a8-d3f66700f075, 8119fc51-288a-4f2a-94a8-9e571aa54b97, 916fdffd-68bb-4440-b5f0-0620010e908c

### Verbatim source copying in question text  ·  impact 219  ·  effort S

- Agent: `A3_FactEcho`
- Severity: fail=16, warn=171, error=0
- Affected: fact_to_question, scenario_synthesis.
- Proposed fix: Add a prompt instruction in `_prompts.py`: 'Paraphrase the fact — never copy >5 consecutive words verbatim.' Add a post-LLM reject if LCS ratio > 0.6.
- Verification: A3 fail rate drops below 2% on regenerated batch.
- Example question UUIDs: 3416ce5b-3ddd-4a1a-9b7e-a9c2411a4d1e, 87a50470-5395-4ec0-ba22-96f0aeb06b47, 30e0a5d0-9893-4866-b0e4-aee365342fa4, 926041ce-50fe-4355-acb5-ba8b04e9981c, 99d9a63b-91c6-4d24-bd23-6f32fc5c18ee

### Vague / marketing / blend-as-variety phrasing  ·  impact 53  ·  effort S

- Agent: `A1_LexicalHygiene`
- Severity: fail=14, warn=11, error=0
- Affected: All LLM strategies.
- Proposed fix: Extend `_VAGUE_PATTERNS` and `_BLEND_AS_VARIETY` regexes with the matched phrases; add post-LLM filter in `_schemas.py` that rejects questions whose stem or options contain any blocked phrase.
- Verification: Fixture questions with each blocked phrase should score fail in A1.
- Example question UUIDs: 6075785b-5b64-4d64-8d43-02491d34e62d, 9aafcdf8-c43c-4783-923e-fa981d4f3f72, 2f96ad39-3b86-43ca-b9ea-6657516ab226, bfcb5b05-1563-4492-99ad-2cef0a1603ea, 97b52840-76aa-4ea1-992c-a01f900600d4

### Key disagrees with judge consensus / source fact  ·  impact 19  ·  effort L

- Agent: `B1_TriJudgeAnswer`
- Severity: fail=2, warn=13, error=0
- Affected: All LLM strategies.
- Proposed fix: Root-cause per example: (a) fact hallucination → tighten 'use ONLY provided fact' instruction; (b) ambiguous key → add B4 and human review; (c) option swap bug → audit `_schemas.py` shuffle logic.
- Verification: B1 fail rate < 5% in follow-up run; rebuild failing questions.
- Example question UUIDs: 685cf418-01cf-4db8-b366-bcbf75a576f3, c92540e5-4096-4ba5-9d7c-6cae017590e6, b5f80df0-892c-4f61-889a-10157859e8ad, e8263a4d-5ae5-4248-aa76-0951fa840317, 95d2141a-27aa-495c-ad57-fd83193b47ab

### Distractor wine-category mismatch  ·  impact 13  ·  effort S

- Agent: `C2_CategoryLeak`
- Severity: fail=2, warn=7, error=0
- Affected: fact_to_question, comparative, scenario_synthesis.
- Proposed fix: Make `_classify_wine_category` mandatory for ALL distractor sampling (not just distractor_miner); reject mismatched distractors in sampler layer.
- Verification: C2 fail count == 0 on regenerated batch.
- Example question UUIDs: 31d353e9-83d0-4b7a-9034-5ef4d922266f, db22a553-9941-443c-9ed4-61c4e2e9aef3, 3bf49a22-b82d-4239-a490-2bf37806ea61, 587fbadd-2541-44a7-9f14-958065b232a6, 4fa92095-51c2-4a11-b281-92f9df0dfd67

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
