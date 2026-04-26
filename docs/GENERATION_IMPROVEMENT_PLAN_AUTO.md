# OenoBench Generation Improvement Plan

- Run ID: `bfc39e1a-ba6b-471d-bde0-87eead62d1dc`
- Corpus tag: `audit_pilot_v6`
- Generated: 2026-04-26T13:38:58.176348

## Prioritised defects

Ranked by impact = `3·fails + 1·warns + 2·errors`. Effort S ≈ <1d, M ≈ 1-3d, L ≈ 3-7d.

### Question solvable from world knowledge (easy leakage)  ·  impact 418  ·  effort M

- Agent: `B2_ClosedBookSolvability`
- Severity: fail=122, warn=52, error=0
- Affected: fact_to_question (most), template.
- Proposed fix: Raise difficulty target for leaking questions; rewrite stems to use provided fact-specific terminology rather than famous-entity references.
- Verification: B2 leakage ratio < 0.5 of judges (5-judge panel: claude/chatgpt/gemini/llama/qwen).
- Example question UUIDs: e5da88b1-97c9-46d6-bdd1-037e7a3c7573, 4155e82b-9d95-4879-8c31-83c51790df7b, 3526f194-25c5-4241-b1ea-a2c5074b4780, 1b3ef377-1e68-4b49-84f2-55c313e929eb, 8ca30a84-c626-4d54-ba3d-63d685bb16db

### Template questions statistically distinguishable from LLM ones  ·  impact 288  ·  effort M

- Agent: `A4_TemplateFingerprint`
- Severity: fail=71, warn=75, error=0
- Affected: template.
- Proposed fix: Diversify template phrasings (rotate opening verbs, add filler, vary punctuation). If AUC remains high, reduce template share of the final corpus.
- Verification: Re-run A4 after template edits; AUC target < 0.85.
- Example question UUIDs: 23e82bbf-1b60-4cce-a0af-cc841f28a6fa, 63540b13-cd37-409f-acc4-0a1433be70d2, 41ad9bb8-c97d-4b35-9e5e-89f450b011c4, bbcca4da-bc82-47a7-83f5-31aa84852ac2, 02eb9957-7dea-4b76-96d9-a2a1ac8a6c0c

### Verbatim source copying in question text  ·  impact 160  ·  effort S

- Agent: `A3_FactEcho`
- Severity: fail=8, warn=136, error=0
- Affected: fact_to_question, scenario_synthesis.
- Proposed fix: Add a prompt instruction in `_prompts.py`: 'Paraphrase the fact — never copy >5 consecutive words verbatim.' Add a post-LLM reject if LCS ratio > 0.6.
- Verification: A3 fail rate drops below 2% on regenerated batch.
- Example question UUIDs: 65a34a9d-72a3-4fe7-baa0-d1f8d8d23fe9, 288d787f-9c86-429c-97c9-924790976acb, 2f5816a1-f478-4a71-9525-e52363226308, bd0456d3-ddbc-4808-a7e4-e39bbab9f9d3, 3526f194-25c5-4241-b1ea-a2c5074b4780

### Vague / marketing / blend-as-variety phrasing  ·  impact 27  ·  effort S

- Agent: `A1_LexicalHygiene`
- Severity: fail=4, warn=15, error=0
- Affected: All LLM strategies.
- Proposed fix: Extend `_VAGUE_PATTERNS` and `_BLEND_AS_VARIETY` regexes with the matched phrases; add post-LLM filter in `_schemas.py` that rejects questions whose stem or options contain any blocked phrase.
- Verification: Fixture questions with each blocked phrase should score fail in A1.
- Example question UUIDs: f7086957-5e26-4140-9048-449f1d9c2e89, a8e24d36-312c-408e-b347-a4493c9c5bb7, 57e2ba82-b103-4690-9070-313f5426fb0b, 6ab08439-6ba3-473d-9a76-fc9728f255c5, b0f8c358-532d-4658-9f14-6c8208dde7ae

### Key disagrees with judge consensus / source fact  ·  impact 25  ·  effort L

- Agent: `B1_TriJudgeAnswer`
- Severity: fail=3, warn=16, error=0
- Affected: All LLM strategies.
- Proposed fix: Root-cause per example: (a) fact hallucination → tighten 'use ONLY provided fact' instruction; (b) ambiguous key → add B4 and human review; (c) option swap bug → audit `_schemas.py` shuffle logic.
- Verification: B1 fail rate < 5% in follow-up run; rebuild failing questions.
- Example question UUIDs: 2d4d1750-09db-4502-9b69-11bd5dfea601, c0ac6876-cca0-4079-a76f-5233fc72a3c9, 96819afa-680f-4294-88a2-e44080687c5d, a06126e8-d114-4598-b101-76000ce85ac1, a7b161b8-6801-4b85-9ccd-a5e3bf903383

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

### Correct-answer position / length bias  ·  impact 3  ·  effort M

- Agent: `A2_BiasStats`
- Severity: fail=1, warn=0, error=0
- Affected: All MC strategies.
- Proposed fix: Ensure `_schemas.py` option-shuffle runs before DB insert; if length bias persists, add a length-normaliser to post-LLM validator that pads / trims distractor texts.
- Verification: After fix, A2 χ² p-value > 0.2 on any (strategy,generator) cell with n ≥ 20.

### Distractor wine-category mismatch  ·  impact 2  ·  effort S

- Agent: `C2_CategoryLeak`
- Severity: fail=0, warn=2, error=0
- Affected: fact_to_question, comparative, scenario_synthesis.
- Proposed fix: Make `_classify_wine_category` mandatory for ALL distractor sampling (not just distractor_miner); reject mismatched distractors in sampler layer.
- Verification: C2 fail count == 0 on regenerated batch.
- Example question UUIDs: 3f9ef841-f5f5-44fa-9e7e-4898588c538f, a7b161b8-6801-4b85-9ccd-a5e3bf903383

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
