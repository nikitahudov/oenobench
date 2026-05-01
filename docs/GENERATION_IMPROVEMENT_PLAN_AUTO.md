# OenoBench Generation Improvement Plan

- Run ID: `2335e3f6-4f71-4926-95ce-bd799fe71a51`
- Corpus tag: `audit_pilot_v14c`
- Generated: 2026-05-01T22:28:19.355980

## Prioritised defects

Ranked by impact = `3·fails + 1·warns + 2·errors`. Effort S ≈ <1d, M ≈ 1-3d, L ≈ 3-7d.

### Question solvable from world knowledge (easy leakage)  ·  impact 51  ·  effort M

- Agent: `B2_ClosedBookSolvability`
- Severity: fail=16, warn=3, error=0
- Affected: fact_to_question (most), template.
- Proposed fix: Raise difficulty target for leaking questions; rewrite stems to use provided fact-specific terminology rather than famous-entity references.
- Verification: B2 leakage ratio < 0.5 of judges (5-judge panel: claude/chatgpt/gemini/llama/qwen).
- Example question UUIDs: 9da54183-5219-45e6-a1ea-476d1ad15b69, a62afd39-b9b1-47f4-9141-23d5b1a24faf, d5359844-6f58-44f9-b848-a88adc572e25, 1f03b8bc-ee69-49db-a476-1da1b32e1b15, 0ee3c3ab-7bf4-42fb-bf42-216c33b012fa

### Verbatim source copying in question text  ·  impact 11  ·  effort S

- Agent: `A3_FactEcho`
- Severity: fail=0, warn=11, error=0
- Affected: fact_to_question, scenario_synthesis.
- Proposed fix: Add a prompt instruction in `_prompts.py`: 'Paraphrase the fact — never copy >5 consecutive words verbatim.' Add a post-LLM reject if LCS ratio > 0.6.
- Verification: A3 fail rate drops below 2% on regenerated batch.
- Example question UUIDs: 4f931ba0-ad52-4ca0-b18e-99cbf540faef, 3f18eadb-690d-47a8-981f-eeb6b448bd46, 3383f328-f173-41ec-8e37-16e4343bace7, 9da54183-5219-45e6-a1ea-476d1ad15b69, a62afd39-b9b1-47f4-9141-23d5b1a24faf

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
