# OenoBench Generation Improvement Plan

- Run ID: `2ba38269-5e66-44aa-aaaf-010dc7ef19d4`
- Corpus tag: `release_v1.1`
- Generated: 2026-05-03T19:14:21.094741

## Prioritised defects

Ranked by impact = `3·fails + 1·warns + 2·errors`. Effort S ≈ <1d, M ≈ 1-3d, L ≈ 3-7d.

### C4_DifficultyAudit  ·  impact 5550  ·  effort M

- Agent: `C4_DifficultyAudit`
- Severity: fail=1351, warn=1483, error=7
- Affected: unknown
- Proposed fix: Investigate findings manually.
- Verification: Re-run audit after fix.
- Example question UUIDs: 41f8dbdf-3b27-4e04-9da1-f9e9348475bd, 96bce42f-2936-4ae1-8462-1794707a0152, 71b901c5-b091-49bd-babd-cb3fe7ed91ec, 7811ed62-03c5-4ab1-a766-c0c1105d6dc5, dcfcacb8-5f95-4331-8ee6-cdfb9f1e8233

### Question solvable from world knowledge (easy leakage)  ·  impact 5254  ·  effort M

- Agent: `B2_ClosedBookSolvability`
- Severity: fail=1452, warn=898, error=0
- Affected: fact_to_question (most), template.
- Proposed fix: Raise difficulty target for leaking questions; rewrite stems to use provided fact-specific terminology rather than famous-entity references.
- Verification: B2 leakage ratio < 0.5 of judges (5-judge panel: claude/chatgpt/gemini/llama/qwen).
- Example question UUIDs: e46c5ce1-be9d-4d3f-a123-33a6aba38bf7, 2f8632e4-4b30-4ff4-8aac-0378bc8bdbbc, eac06c84-85a7-4b12-841b-77999f9dfc06, 72f31b40-4df2-4e08-9570-6b34e3f9f7d9, 91d529b6-0f36-484b-a24c-d1caf6176bd2

### Verbatim source copying in question text  ·  impact 2083  ·  effort S

- Agent: `A3_FactEcho`
- Severity: fail=63, warn=1894, error=0
- Affected: fact_to_question, scenario_synthesis.
- Proposed fix: Add a prompt instruction in `_prompts.py`: 'Paraphrase the fact — never copy >5 consecutive words verbatim.' Add a post-LLM reject if LCS ratio > 0.6.
- Verification: A3 fail rate drops below 2% on regenerated batch.
- Example question UUIDs: 0f736df4-a91e-4957-9b56-f876ae06614c, 6b6b52c3-64b3-42c6-8283-c393676361e9, 30612295-017f-44f0-9a10-0e5f8e02c3dd, 395c6e4d-6fcb-4d3e-a252-136b07b74032, 2f8632e4-4b30-4ff4-8aac-0378bc8bdbbc

### Template questions statistically distinguishable from LLM ones  ·  impact 1281  ·  effort M

- Agent: `A4_TemplateFingerprint`
- Severity: fail=0, warn=1281, error=0
- Affected: template.
- Proposed fix: Diversify template phrasings (rotate opening verbs, add filler, vary punctuation). If AUC remains high, reduce template share of the final corpus.
- Verification: Re-run A4 after template edits; AUC target < 0.85.
- Example question UUIDs: c89f8054-a8f1-4ccd-96fb-dfe1102c5043, 92bfcb62-47ea-4c00-9b48-3fd30abbee98, 20a10c65-40f6-45e5-977c-98f3b626f7e3, 879cc9bb-b3e3-4073-b1ad-432008055f05, 11259084-8a23-4019-b3bd-42597dafa512

### Key disagrees with judge consensus / source fact  ·  impact 315  ·  effort L

- Agent: `B1_TriJudgeAnswer`
- Severity: fail=47, warn=174, error=0
- Affected: All LLM strategies.
- Proposed fix: Root-cause per example: (a) fact hallucination → tighten 'use ONLY provided fact' instruction; (b) ambiguous key → add B4 and human review; (c) option swap bug → audit `_schemas.py` shuffle logic.
- Verification: B1 fail rate < 5% in follow-up run; rebuild failing questions.
- Example question UUIDs: 1c1b75d3-cdfe-4734-ae66-87c354cbf726, 0b1cf335-7262-41e0-a336-de375fdcb267, c7981e01-3178-41b2-9768-f3c4f0184a12, a7852713-db6a-4a61-b709-a3d1df2900ba, 11b69d1b-b7fa-4e09-8d04-e4c13d0e64d3

### Vague / marketing / blend-as-variety phrasing  ·  impact 288  ·  effort S

- Agent: `A1_LexicalHygiene`
- Severity: fail=60, warn=108, error=0
- Affected: All LLM strategies.
- Proposed fix: Extend `_VAGUE_PATTERNS` and `_BLEND_AS_VARIETY` regexes with the matched phrases; add post-LLM filter in `_schemas.py` that rejects questions whose stem or options contain any blocked phrase.
- Verification: Fixture questions with each blocked phrase should score fail in A1.
- Example question UUIDs: 2f2f7085-8256-4d99-b60f-51a22f9377b4, ecf0af1d-0be1-4c6d-aa9b-3ba84f0875d9, 61e3220a-8dd3-4bf3-bec0-0944cd064d9a, 0933e1af-b3a6-4ed8-905e-072be2b23d43, 0083f38b-12eb-42db-9c15-1ad51605e369

### Distractor wine-category mismatch  ·  impact 77  ·  effort S

- Agent: `C2_CategoryLeak`
- Severity: fail=9, warn=50, error=0
- Affected: fact_to_question, comparative, scenario_synthesis.
- Proposed fix: Make `_classify_wine_category` mandatory for ALL distractor sampling (not just distractor_miner); reject mismatched distractors in sampler layer.
- Verification: C2 fail count == 0 on regenerated batch.
- Example question UUIDs: 83d88c78-1bd6-4389-bbfb-ccb520cd7aae, db5e6b77-fc0c-4730-ad84-e04b9ff92f8b, 911467c1-5ed1-493a-8b64-8815c3ac46db, 43e58328-0ccd-4061-a1d4-6390ccc71fca, 79e52ae2-2517-4329-9329-4d7847448901

### Model scores disproportionately well on its own questions  ·  impact 3  ·  effort L

- Agent: `D1_SelfPreference`
- Severity: fail=1, warn=0, error=0
- Affected: Dataset composition.
- Proposed fix: Rebalance final dataset so each model's share is capped at 22% (prevent dominance). Consider dropping the highest-SP model if delta ≥ 0.15.
- Verification: D1 delta < 0.07 across all 5 evaluators in follow-up run.

### Correct-answer position / length bias  ·  impact 3  ·  effort M

- Agent: `A2_BiasStats`
- Severity: fail=1, warn=0, error=0
- Affected: All MC strategies.
- Proposed fix: Ensure `_schemas.py` option-shuffle runs before DB insert; if length bias persists, add a length-normaliser to post-LLM validator that pads / trims distractor texts.
- Verification: After fix, A2 χ² p-value > 0.2 on any (strategy,generator) cell with n ≥ 20.

### Geographic or subdomain over-representation  ·  impact 1  ·  effort M

- Agent: `D3_SkewAudit`
- Severity: fail=0, warn=1, error=0
- Affected: All strategies.
- Proposed fix: Add per-country quota to `_fact_sampler.sample_facts`; or sample facts inversely weighted by country frequency. Reduce Portugal / France over-sampling.
- Verification: D3 max over-representation ratio < 1.5.

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
