# OenoBench Generation Improvement Plan

- Run ID: `541d1d1d-1a89-4f5a-8940-218928da3729`
- Corpus tag: `audit_pilot_v5`
- Generated: 2026-04-25T04:14:36.560495

## Prioritised defects

Ranked by impact = `3·fails + 1·warns + 2·errors`. Effort S ≈ <1d, M ≈ 1-3d, L ≈ 3-7d.

### Question solvable from world knowledge (easy leakage)  ·  impact 426  ·  effort M

- Agent: `B2_ClosedBookSolvability`
- Severity: fail=111, warn=93, error=0
- Affected: fact_to_question (most), template.
- Proposed fix: Raise difficulty target for leaking questions; rewrite stems to use provided fact-specific terminology rather than famous-entity references.
- Verification: B2 leakage ratio < 0.5 of judges (5-judge panel: claude/chatgpt/gemini/llama/qwen).
- Example question UUIDs: e46c5ce1-be9d-4d3f-a123-33a6aba38bf7, 2f8632e4-4b30-4ff4-8aac-0378bc8bdbbc, eac06c84-85a7-4b12-841b-77999f9dfc06, 72f31b40-4df2-4e08-9570-6b34e3f9f7d9, 91d529b6-0f36-484b-a24c-d1caf6176bd2

### Template questions statistically distinguishable from LLM ones  ·  impact 305  ·  effort M

- Agent: `A4_TemplateFingerprint`
- Severity: fail=97, warn=14, error=0
- Affected: template.
- Proposed fix: Diversify template phrasings (rotate opening verbs, add filler, vary punctuation). If AUC remains high, reduce template share of the final corpus.
- Verification: Re-run A4 after template edits; AUC target < 0.85.
- Example question UUIDs: 0777d7be-5c14-4ce7-b54f-2e215abd9e2a, 43e58328-0ccd-4061-a1d4-6390ccc71fca, f20aec20-c808-4e0b-92be-256db7514807, bdf6e745-e473-497c-bff2-b20cbae4cabe, 9a393d7c-9715-4fad-8f21-d0f261ba7d77

### Verbatim source copying in question text  ·  impact 168  ·  effort S

- Agent: `A3_FactEcho`
- Severity: fail=11, warn=135, error=0
- Affected: fact_to_question, scenario_synthesis.
- Proposed fix: Add a prompt instruction in `_prompts.py`: 'Paraphrase the fact — never copy >5 consecutive words verbatim.' Add a post-LLM reject if LCS ratio > 0.6.
- Verification: A3 fail rate drops below 2% on regenerated batch.
- Example question UUIDs: ef9f9d4e-2c2d-4cec-8c4d-b525fe2104cd, 2f8632e4-4b30-4ff4-8aac-0378bc8bdbbc, eac06c84-85a7-4b12-841b-77999f9dfc06, 91d529b6-0f36-484b-a24c-d1caf6176bd2, 2f4785de-4862-41b9-8bf2-c8809518ab26

### Vague / marketing / blend-as-variety phrasing  ·  impact 42  ·  effort S

- Agent: `A1_LexicalHygiene`
- Severity: fail=10, warn=12, error=0
- Affected: All LLM strategies.
- Proposed fix: Extend `_VAGUE_PATTERNS` and `_BLEND_AS_VARIETY` regexes with the matched phrases; add post-LLM filter in `_schemas.py` that rejects questions whose stem or options contain any blocked phrase.
- Verification: Fixture questions with each blocked phrase should score fail in A1.
- Example question UUIDs: 2713f328-46da-4bb5-a765-d733cc14284c, 82245cdd-4d1d-4ddf-bde9-8dfb9a4d96f2, 39a4fec7-26a8-4274-8dae-1880bea22071, 2f2f7085-8256-4d99-b60f-51a22f9377b4, c09cf69d-562b-482b-9b23-b69d7ad0efb7

### Key disagrees with judge consensus / source fact  ·  impact 26  ·  effort L

- Agent: `B1_TriJudgeAnswer`
- Severity: fail=1, warn=23, error=0
- Affected: All LLM strategies.
- Proposed fix: Root-cause per example: (a) fact hallucination → tighten 'use ONLY provided fact' instruction; (b) ambiguous key → add B4 and human review; (c) option swap bug → audit `_schemas.py` shuffle logic.
- Verification: B1 fail rate < 5% in follow-up run; rebuild failing questions.
- Example question UUIDs: 3de522d1-b057-4a44-9070-e167f290060e, c7981e01-3178-41b2-9768-f3c4f0184a12, a7852713-db6a-4a61-b709-a3d1df2900ba, afeb0416-d05b-497a-9f1c-a5a8c688e859, 5e3d591c-ef02-46e5-b3bb-b7a34e887a45

### Distractor wine-category mismatch  ·  impact 16  ·  effort S

- Agent: `C2_CategoryLeak`
- Severity: fail=3, warn=7, error=0
- Affected: fact_to_question, comparative, scenario_synthesis.
- Proposed fix: Make `_classify_wine_category` mandatory for ALL distractor sampling (not just distractor_miner); reject mismatched distractors in sampler layer.
- Verification: C2 fail count == 0 on regenerated batch.
- Example question UUIDs: 83d88c78-1bd6-4389-bbfb-ccb520cd7aae, 911467c1-5ed1-493a-8b64-8815c3ac46db, 43e58328-0ccd-4061-a1d4-6390ccc71fca, dc52f29a-0e05-4391-b9bc-24f402c71d99, dcfcacb8-5f95-4331-8ee6-cdfb9f1e8233

### Geographic or subdomain over-representation  ·  impact 3  ·  effort M

- Agent: `D3_SkewAudit`
- Severity: fail=1, warn=0, error=0
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
