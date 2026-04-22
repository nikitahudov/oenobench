# OenoBench Generation Improvement Plan

- Run ID: `0bfe85dc-4fdc-4500-b274-a4b05d982e20`
- Corpus tag: `audit_pilot_v3`
- Generated: 2026-04-22T20:35:49.115774

## Prioritised defects

Ranked by impact = `3·fails + 1·warns + 2·errors`. Effort S ≈ <1d, M ≈ 1-3d, L ≈ 3-7d.

### Question solvable from world knowledge (easy leakage)  ·  impact 698  ·  effort M

- Agent: `B2_ClosedBookSolvability`
- Severity: fail=220, warn=38, error=0
- Affected: fact_to_question (most), template.
- Proposed fix: Raise difficulty target for leaking questions; rewrite stems to use provided fact-specific terminology rather than famous-entity references.
- Verification: B2 leakage ratio < 0.5 of judges (5-judge panel: claude/chatgpt/gemini/llama/qwen).
- Example question UUIDs: 2a0b4c8e-387e-4334-91e8-10f54a55de3d, 8abbd9cc-6cbc-4c0f-b000-82cbeac53c17, d300afa4-f082-49fe-9754-dbf5cbcee03a, f09ff278-6b7a-4c9a-8158-de686790a38d, 19b2622e-a1e1-49aa-b1f9-f0e123ec397e

### C4_DifficultyAudit  ·  impact 234  ·  effort M

- Agent: `C4_DifficultyAudit`
- Severity: fail=12, warn=186, error=6
- Affected: unknown
- Proposed fix: Investigate findings manually.
- Verification: Re-run audit after fix.
- Example question UUIDs: d0cf5ac4-2588-40c4-bd9a-ed1787562e85, 2a0b4c8e-387e-4334-91e8-10f54a55de3d, 8abbd9cc-6cbc-4c0f-b000-82cbeac53c17, 734123ca-c0d7-4374-b4de-28d11f774024, c1b0b2bf-c3f1-4518-a13a-adbc6645356c

### Verbatim source copying in question text  ·  impact 182  ·  effort S

- Agent: `A3_FactEcho`
- Severity: fail=16, warn=134, error=0
- Affected: fact_to_question, scenario_synthesis.
- Proposed fix: Add a prompt instruction in `_prompts.py`: 'Paraphrase the fact — never copy >5 consecutive words verbatim.' Add a post-LLM reject if LCS ratio > 0.6.
- Verification: A3 fail rate drops below 2% on regenerated batch.
- Example question UUIDs: 4ec1a779-f213-4d07-bc89-1d01f0a2e8c5, 80fcb68a-a03a-4628-b2f4-1d1c53c83c0b, 85e9e8fa-baff-498e-b608-2d98ea7532cd, c00a0ace-a75d-4103-9aa5-812e12ef8fdd, 25b4f40f-d3a3-4037-a5c1-da73d5e8bf1e

### Vague / marketing / blend-as-variety phrasing  ·  impact 61  ·  effort S

- Agent: `A1_LexicalHygiene`
- Severity: fail=16, warn=13, error=0
- Affected: All LLM strategies.
- Proposed fix: Extend `_VAGUE_PATTERNS` and `_BLEND_AS_VARIETY` regexes with the matched phrases; add post-LLM filter in `_schemas.py` that rejects questions whose stem or options contain any blocked phrase.
- Verification: Fixture questions with each blocked phrase should score fail in A1.
- Example question UUIDs: d28375d6-dab4-40e6-acb5-cdf4506667e6, 75ce6042-ee8e-4b13-8e61-e66d39e19958, a7be65a2-bd32-490e-85bb-a5edd7f3614d, f28a2b20-7308-4427-a837-db0d7ef3572d, b087b0cb-40a3-4a86-97e1-92b85d8cf253

### Key disagrees with judge consensus / source fact  ·  impact 45  ·  effort L

- Agent: `B1_TriJudgeAnswer`
- Severity: fail=9, warn=18, error=0
- Affected: All LLM strategies.
- Proposed fix: Root-cause per example: (a) fact hallucination → tighten 'use ONLY provided fact' instruction; (b) ambiguous key → add B4 and human review; (c) option swap bug → audit `_schemas.py` shuffle logic.
- Verification: B1 fail rate < 5% in follow-up run; rebuild failing questions.
- Example question UUIDs: c1b0b2bf-c3f1-4518-a13a-adbc6645356c, d9d0d250-7acd-4785-a3b2-3d2de160640a, 5dbbd408-1e2f-4738-815e-766b10bdd977, 7d6db076-708c-40be-a46a-200ce019dae0, c00a0ace-a75d-4103-9aa5-812e12ef8fdd

### Distractor wine-category mismatch  ·  impact 7  ·  effort S

- Agent: `C2_CategoryLeak`
- Severity: fail=0, warn=7, error=0
- Affected: fact_to_question, comparative, scenario_synthesis.
- Proposed fix: Make `_classify_wine_category` mandatory for ALL distractor sampling (not just distractor_miner); reject mismatched distractors in sampler layer.
- Verification: C2 fail count == 0 on regenerated batch.
- Example question UUIDs: 734123ca-c0d7-4374-b4de-28d11f774024, b2c2df9e-a8c8-40e7-ac6d-f4dc0b411bc7, 42ef01cf-c83a-4f4e-9466-e8e59bd21818, 8c2df0a3-e891-4749-98cf-08f4c2b691bd, 4f4a4642-fd4a-4c0a-9f5c-250cb7aecd01

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

### Model scores disproportionately well on its own questions  ·  impact 1  ·  effort L

- Agent: `D1_SelfPreference`
- Severity: fail=0, warn=1, error=0
- Affected: Dataset composition.
- Proposed fix: Rebalance final dataset so each model's share is capped at 22% (prevent dominance). Consider dropping the highest-SP model if delta ≥ 0.15.
- Verification: D1 delta < 0.07 across all 5 evaluators in follow-up run.

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
