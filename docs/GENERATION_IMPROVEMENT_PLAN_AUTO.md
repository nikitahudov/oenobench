# OenoBench Generation Improvement Plan

- Run ID: `9a085a74-8c82-4a1d-a0ae-b2c555d3e75f`
- Corpus tag: `audit_pilot_v15_ubiq`
- Generated: 2026-05-02T09:12:19.361388

## Prioritised defects

Ranked by impact = `3·fails + 1·warns + 2·errors`. Effort S ≈ <1d, M ≈ 1-3d, L ≈ 3-7d.

### Question solvable from world knowledge (easy leakage)  ·  impact 43  ·  effort M

- Agent: `B2_ClosedBookSolvability`
- Severity: fail=11, warn=10, error=0
- Affected: fact_to_question (most), template.
- Proposed fix: Raise difficulty target for leaking questions; rewrite stems to use provided fact-specific terminology rather than famous-entity references.
- Verification: B2 leakage ratio < 0.5 of judges (5-judge panel: claude/chatgpt/gemini/llama/qwen).
- Example question UUIDs: a716c632-04bd-4608-9d04-021398db055e, 3a63f7a5-2026-4e7a-8dbe-27b52aa41f7e, de4ca68d-f061-4fd2-86e2-63798be43459, 87ac35a9-099e-4c3a-b736-f68756158c91, 7a24e718-4d26-405c-84a9-2e21e13d69d3

### Verbatim source copying in question text  ·  impact 23  ·  effort S

- Agent: `A3_FactEcho`
- Severity: fail=1, warn=20, error=0
- Affected: fact_to_question, scenario_synthesis.
- Proposed fix: Add a prompt instruction in `_prompts.py`: 'Paraphrase the fact — never copy >5 consecutive words verbatim.' Add a post-LLM reject if LCS ratio > 0.6.
- Verification: A3 fail rate drops below 2% on regenerated batch.
- Example question UUIDs: 3a63f7a5-2026-4e7a-8dbe-27b52aa41f7e, a716c632-04bd-4608-9d04-021398db055e, de4ca68d-f061-4fd2-86e2-63798be43459, 7a24e718-4d26-405c-84a9-2e21e13d69d3, 201fb5b4-9d46-4947-b91d-9453b5203f5a

### Model scores disproportionately well on its own questions  ·  impact 3  ·  effort L

- Agent: `D1_SelfPreference`
- Severity: fail=1, warn=0, error=0
- Affected: Dataset composition.
- Proposed fix: Rebalance final dataset so each model's share is capped at 22% (prevent dominance). Consider dropping the highest-SP model if delta ≥ 0.15.
- Verification: D1 delta < 0.07 across all 5 evaluators in follow-up run.

### Distractor wine-category mismatch  ·  impact 2  ·  effort S

- Agent: `C2_CategoryLeak`
- Severity: fail=0, warn=2, error=0
- Affected: fact_to_question, comparative, scenario_synthesis.
- Proposed fix: Make `_classify_wine_category` mandatory for ALL distractor sampling (not just distractor_miner); reject mismatched distractors in sampler layer.
- Verification: C2 fail count == 0 on regenerated batch.
- Example question UUIDs: 7a24e718-4d26-405c-84a9-2e21e13d69d3, e1ce3d1d-ab57-41d2-a090-35e1f9f5a4de

### Geographic or subdomain over-representation  ·  impact 1  ·  effort M

- Agent: `D3_SkewAudit`
- Severity: fail=0, warn=1, error=0
- Affected: All strategies.
- Proposed fix: Add per-country quota to `_fact_sampler.sample_facts`; or sample facts inversely weighted by country frequency. Reduce Portugal / France over-sampling.
- Verification: D3 max over-representation ratio < 1.5.

### Vague / marketing / blend-as-variety phrasing  ·  impact 1  ·  effort S

- Agent: `A1_LexicalHygiene`
- Severity: fail=0, warn=1, error=0
- Affected: All LLM strategies.
- Proposed fix: Extend `_VAGUE_PATTERNS` and `_BLEND_AS_VARIETY` regexes with the matched phrases; add post-LLM filter in `_schemas.py` that rejects questions whose stem or options contain any blocked phrase.
- Verification: Fixture questions with each blocked phrase should score fail in A1.
- Example question UUIDs: f5069ce8-1562-41ed-bfbd-0b64892e7524

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
