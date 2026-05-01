# OenoBench Generation Improvement Plan

- Run ID: `9db7c95a-0154-4340-9265-37795694d78a`
- Corpus tag: `audit_pilot_v14b`
- Generated: 2026-05-01T21:33:57.613689

## Prioritised defects

Ranked by impact = `3·fails + 1·warns + 2·errors`. Effort S ≈ <1d, M ≈ 1-3d, L ≈ 3-7d.

### Question solvable from world knowledge (easy leakage)  ·  impact 34  ·  effort M

- Agent: `B2_ClosedBookSolvability`
- Severity: fail=10, warn=4, error=0
- Affected: fact_to_question (most), template.
- Proposed fix: Raise difficulty target for leaking questions; rewrite stems to use provided fact-specific terminology rather than famous-entity references.
- Verification: B2 leakage ratio < 0.5 of judges (5-judge panel: claude/chatgpt/gemini/llama/qwen).
- Example question UUIDs: 0b758e9a-9cb7-4058-82ca-3803efa1e075, 6f5bb135-9f3f-487e-b466-be10df0a1fa4, efdefb7f-aea9-43ab-80bb-2dc135e981a2, 4ed16e8f-164f-4d71-a60d-fa3b4f758d2b, 6ac7ae85-ae35-4e64-b85c-cf1734559ab5

### Verbatim source copying in question text  ·  impact 11  ·  effort S

- Agent: `A3_FactEcho`
- Severity: fail=0, warn=11, error=0
- Affected: fact_to_question, scenario_synthesis.
- Proposed fix: Add a prompt instruction in `_prompts.py`: 'Paraphrase the fact — never copy >5 consecutive words verbatim.' Add a post-LLM reject if LCS ratio > 0.6.
- Verification: A3 fail rate drops below 2% on regenerated batch.
- Example question UUIDs: 0b758e9a-9cb7-4058-82ca-3803efa1e075, 6f5bb135-9f3f-487e-b466-be10df0a1fa4, 09bb6152-d0e0-4c3c-9501-5e910cb79d59, 106aa972-b4d0-46c1-8f67-5bbb60ae0159, 01b6fc7a-dfc6-40b0-9d23-0d8f279f42fe

### Geographic or subdomain over-representation  ·  impact 1  ·  effort M

- Agent: `D3_SkewAudit`
- Severity: fail=0, warn=1, error=0
- Affected: All strategies.
- Proposed fix: Add per-country quota to `_fact_sampler.sample_facts`; or sample facts inversely weighted by country frequency. Reduce Portugal / France over-sampling.
- Verification: D3 max over-representation ratio < 1.5.

### Key disagrees with judge consensus / source fact  ·  impact 1  ·  effort L

- Agent: `B1_TriJudgeAnswer`
- Severity: fail=0, warn=1, error=0
- Affected: All LLM strategies.
- Proposed fix: Root-cause per example: (a) fact hallucination → tighten 'use ONLY provided fact' instruction; (b) ambiguous key → add B4 and human review; (c) option swap bug → audit `_schemas.py` shuffle logic.
- Verification: B1 fail rate < 5% in follow-up run; rebuild failing questions.
- Example question UUIDs: b941d45c-6b3d-4380-82b3-61bf45713a2d

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
