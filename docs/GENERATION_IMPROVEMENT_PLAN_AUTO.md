# OenoBench Generation Improvement Plan

- Run ID: `9b299fd5-df36-4fe1-a8db-9b998129139d`
- Corpus tag: `audit_pilot_v16`
- Generated: 2026-05-02T12:15:02.671322

## Prioritised defects

Ranked by impact = `3·fails + 1·warns + 2·errors`. Effort S ≈ <1d, M ≈ 1-3d, L ≈ 3-7d.

### Question solvable from world knowledge (easy leakage)  ·  impact 33  ·  effort M

- Agent: `B2_ClosedBookSolvability`
- Severity: fail=9, warn=6, error=0
- Affected: fact_to_question (most), template.
- Proposed fix: Raise difficulty target for leaking questions; rewrite stems to use provided fact-specific terminology rather than famous-entity references.
- Verification: B2 leakage ratio < 0.5 of judges (5-judge panel: claude/chatgpt/gemini/llama/qwen).
- Example question UUIDs: 698a9b4a-1e92-4356-ab4e-f9eef5ff6b57, 9f7f8c22-7907-4458-802a-5d421f92a0be, 5c2f9172-0793-454c-9317-1c2e8656d242, f1dbc666-39f2-4fb3-addf-63450d5027f4, 7efdb90b-7520-43df-ba3d-af89e7cf5cd5

### Verbatim source copying in question text  ·  impact 21  ·  effort S

- Agent: `A3_FactEcho`
- Severity: fail=3, warn=12, error=0
- Affected: fact_to_question, scenario_synthesis.
- Proposed fix: Add a prompt instruction in `_prompts.py`: 'Paraphrase the fact — never copy >5 consecutive words verbatim.' Add a post-LLM reject if LCS ratio > 0.6.
- Verification: A3 fail rate drops below 2% on regenerated batch.
- Example question UUIDs: 698a9b4a-1e92-4356-ab4e-f9eef5ff6b57, 9f7f8c22-7907-4458-802a-5d421f92a0be, f1dbc666-39f2-4fb3-addf-63450d5027f4, e44452e3-1456-4b44-916d-7e963cdd4add, 1a5621c6-7443-40da-8503-c21d265ac9bc

### Model scores disproportionately well on its own questions  ·  impact 3  ·  effort L

- Agent: `D1_SelfPreference`
- Severity: fail=1, warn=0, error=0
- Affected: Dataset composition.
- Proposed fix: Rebalance final dataset so each model's share is capped at 22% (prevent dominance). Consider dropping the highest-SP model if delta ≥ 0.15.
- Verification: D1 delta < 0.07 across all 5 evaluators in follow-up run.

### Geographic or subdomain over-representation  ·  impact 1  ·  effort M

- Agent: `D3_SkewAudit`
- Severity: fail=0, warn=1, error=0
- Affected: All strategies.
- Proposed fix: Add per-country quota to `_fact_sampler.sample_facts`; or sample facts inversely weighted by country frequency. Reduce Portugal / France over-sampling.
- Verification: D3 max over-representation ratio < 1.5.

### Template questions statistically distinguishable from LLM ones  ·  impact 1  ·  effort M

- Agent: `A4_TemplateFingerprint`
- Severity: fail=0, warn=1, error=0
- Affected: template.
- Proposed fix: Diversify template phrasings (rotate opening verbs, add filler, vary punctuation). If AUC remains high, reduce template share of the final corpus.
- Verification: Re-run A4 after template edits; AUC target < 0.85.

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
