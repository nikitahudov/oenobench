# OenoBench Generation Improvement Plan

- Run ID: `e8eba8bb-cb49-42cd-9e32-c741c987043e`
- Corpus tag: `audit_pilot_v1`
- Generated: 2026-04-19T04:55:19.306420

## Prioritised defects

Ranked by impact = `3·fails + 1·warns + 2·errors`. Effort S ≈ <1d, M ≈ 1-3d, L ≈ 3-7d.

### Verbatim source copying in question text  ·  impact 673  ·  effort S

- Agent: `A3_FactEcho`
- Severity: fail=164, warn=181, error=0
- Affected: fact_to_question, scenario_synthesis.
- Proposed fix: Add a prompt instruction in `_prompts.py`: 'Paraphrase the fact — never copy >5 consecutive words verbatim.' Add a post-LLM reject if LCS ratio > 0.6.
- Verification: A3 fail rate drops below 2% on regenerated batch.
- Example question UUIDs: d042d121-a0b0-4c38-a4ee-f2c17269ce54, a78b4bd6-eed8-49c9-b488-509cfffd1dfb, 8ea13ce6-d4c9-42cf-8f52-cad63aebac5b, 536c6a88-328e-4b9c-9fc5-69bc418ea330, 79da0efa-a35f-4d74-8833-572f657ff5b2

### Question solvable from world knowledge (easy leakage)  ·  impact 570  ·  effort M

- Agent: `B2_ClosedBookSolvability`
- Severity: fail=140, warn=150, error=0
- Affected: fact_to_question (most), template.
- Proposed fix: Raise difficulty target for leaking questions; rewrite stems to use provided fact-specific terminology rather than famous-entity references.
- Verification: B2 leakage ratio < 0.5 on Level-3/4 questions.
- Example question UUIDs: d042d121-a0b0-4c38-a4ee-f2c17269ce54, f572724d-2bcf-48cf-8317-8e90faa7845d, 04b0f78f-434b-47d9-af75-b2ad21b643d3, 9b87bde4-e039-4a5d-a4b6-0b945e657a45, 49c6d892-27bf-4e06-842d-7723d4d8922a

### Key disagrees with judge consensus / source fact  ·  impact 123  ·  effort L

- Agent: `B1_TriJudgeAnswer`
- Severity: fail=22, warn=57, error=0
- Affected: All LLM strategies.
- Proposed fix: Root-cause per example: (a) fact hallucination → tighten 'use ONLY provided fact' instruction; (b) ambiguous key → add B4 and human review; (c) option swap bug → audit `_schemas.py` shuffle logic.
- Verification: B1 fail rate < 5% in follow-up run; rebuild failing questions.
- Example question UUIDs: 04b0f78f-434b-47d9-af75-b2ad21b643d3, 9b87bde4-e039-4a5d-a4b6-0b945e657a45, 49c6d892-27bf-4e06-842d-7723d4d8922a, 692755b4-de58-48ab-9c40-6ac536f6015c, 329e0a09-d848-4f9c-9c96-5b14a6626630

### Template questions statistically distinguishable from LLM ones  ·  impact 75  ·  effort M

- Agent: `A4_TemplateFingerprint`
- Severity: fail=21, warn=12, error=0
- Affected: template.
- Proposed fix: Diversify template phrasings (rotate opening verbs, add filler, vary punctuation). If AUC remains high, reduce template share of the final corpus.
- Verification: Re-run A4 after template edits; AUC target < 0.85.
- Example question UUIDs: 6d43294d-b8b6-4963-9189-1003166ed2df, 00bf35ff-fcc3-476f-b4f7-1b842b500498, bf73bf47-444a-4570-9476-1cb79d07f1a8, f5354cdb-c9ef-4483-946a-cb4008b51628, f013c407-313f-409a-9633-f5e2d983c9dd

### Vague / marketing / blend-as-variety phrasing  ·  impact 52  ·  effort S

- Agent: `A1_LexicalHygiene`
- Severity: fail=13, warn=13, error=0
- Affected: All LLM strategies.
- Proposed fix: Extend `_VAGUE_PATTERNS` and `_BLEND_AS_VARIETY` regexes with the matched phrases; add post-LLM filter in `_schemas.py` that rejects questions whose stem or options contain any blocked phrase.
- Verification: Fixture questions with each blocked phrase should score fail in A1.
- Example question UUIDs: 4dc8e167-63cf-4b6b-84e1-ca8455017512, ad7763f2-f0f4-4a04-bdd9-1d5a09a3de99, 617b5027-fdba-4487-bbfe-04fbab8853e2, d042d121-a0b0-4c38-a4ee-f2c17269ce54, f572724d-2bcf-48cf-8317-8e90faa7845d

### Distractor wine-category mismatch  ·  impact 24  ·  effort S

- Agent: `C2_CategoryLeak`
- Severity: fail=5, warn=9, error=0
- Affected: fact_to_question, comparative, scenario_synthesis.
- Proposed fix: Make `_classify_wine_category` mandatory for ALL distractor sampling (not just distractor_miner); reject mismatched distractors in sampler layer.
- Verification: C2 fail count == 0 on regenerated batch.
- Example question UUIDs: 23ec25f3-82b5-4230-9af5-1213de9a8efd, 2b51de72-35a0-462e-ad7b-95ba3f0c7b05, 0bdb8a31-fa68-4323-a71c-322ace2ee7bb, 082d82b4-a0a9-47f8-bbc4-3972f6b4a34d, cd87fc8f-ebdf-4dc9-af85-f1dda9db8090

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
