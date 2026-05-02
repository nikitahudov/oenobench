# OenoBench Quality Audit Report

- Run ID: `9a085a74-8c82-4a1d-a0ae-b2c555d3e75f`
- Corpus tag: `audit_pilot_v15_ubiq`
- Corpus size: 35
- Config hash: `6a4b67980f51a88e...`
- Started: 2026-05-02 08:55:50.184390+00:00
- Completed: 2026-05-02 09:12:18.148573+00:00
- LLM calls: 380
- Cost: $0.61

## 1 · Executive summary

- Findings across 9 agents: 132 pass · 34 warn · 13 fail · 0 error

| Agent | pass | warn | fail | error | total |
|---|---:|---:|---:|---:|---:|
| A1_LexicalHygiene | 34 | 1 | 0 | 0 | 35 |
| A2_BiasStats | 1 | 0 | 0 | 0 | 1 |
| A3_FactEcho | 14 | 20 | 1 | 0 | 35 |
| A4_TemplateFingerprint | 1 | 0 | 0 | 0 | 1 |
| B1_TriJudgeAnswer | 35 | 0 | 0 | 0 | 35 |
| B2_ClosedBookSolvability | 14 | 10 | 11 | 0 | 35 |
| C2_CategoryLeak | 33 | 2 | 0 | 0 | 35 |
| D1_SelfPreference | 0 | 0 | 1 | 0 | 1 |
| D3_SkewAudit | 0 | 1 | 0 | 0 | 1 |

## 2 · Methodology

- Corpus: 35 questions tagged `audit_pilot_v15_ubiq`, seed 58.
- Agents: ['A1_LexicalHygiene', 'A2_BiasStats', 'A3_FactEcho', 'A4_TemplateFingerprint', 'B1_TriJudgeAnswer', 'B2_ClosedBookSolvability', 'C2_CategoryLeak', 'C4_DifficultyAudit', 'D1_SelfPreference', 'D3_SkewAudit']
- Judge models: ['claude', 'chatgpt', 'gemini']
- Thresholds and seeds encoded in config hash (full hash: `6a4b67980f51a88e726892c968553d7a2b339e5e30d7c8037c2b303f80d7ca4f`).

## 3 · Per-strategy deep dive

### template

- Question count: **15**
- Severity rollup: pass=49, warn=17, fail=9
- Failures by agent:
  - B2_ClosedBookSolvability: 8
  - A3_FactEcho: 1
- Sample failures:
  - WB-REG-0582-L1  ·  B2_ClosedBookSolvability  ·  
    > The fact assigns the Tehachapi Mountains AVA to which US state?
  - WB-GRP-0723-L1  ·  B2_ClosedBookSolvability  ·  
    > Given the fact, a producer working with Tempranillo Blend would be operating in which country?
  - WB-PRD-0479-L2  ·  B2_ClosedBookSolvability  ·  
    > True or False: the producer Invivo Wines sits within the New Zealand wine region.

### fact_to_question

- Question count: **20**
- Severity rollup: pass=81, warn=16, fail=3
- Failures by agent:
  - B2_ClosedBookSolvability: 3
- Sample failures:
  - WB-PRD-0487-L2  ·  B2_ClosedBookSolvability  ·  
    > In which Chilean town is the Viña Tarapacá winery located?
  - WB-REG-0589-L2  ·  B2_ClosedBookSolvability  ·  
    > Which Burgundian subregion contains the commune where Puligny-Montrachet wine is made?
  - WB-PRD-0486-L2  ·  B2_ClosedBookSolvability  ·  
    > Established in 1870, Mikveh Israel holds the distinction of being the first Jewish agricultural college and included instruction in viticulture as part of its curriculum. In what y

## 4 · Per-generator deep dive

### chatgpt

- Authored question count: **4**
- Total fails: 1, warns: 3

### claude

- Authored question count: **4**
- Total fails: 1, warns: 3

### gemini

- Authored question count: **6**
- Total fails: 0, warns: 5

### llama

- Authored question count: **4**
- Total fails: 1, warns: 3

### qwen

- Authored question count: **2**
- Total fails: 0, warns: 2

### template_only

- Authored question count: **15**
- Total fails: 9, warns: 17

## 5 · Cross-cutting findings

### Template detectability (A4)
- Held-out AUC: **0.7857**
- Top discriminative features: `bg:PUN-WORD` (-0.42), `len:tokens` (+0.29), `bg:WORD-PUN` (-0.23), `len:sentences` (-0.21), `bg:WORD-SHORT` (-0.21), `punc:,` (-0.19), `bg:WORD-DET` (+0.18), `bg:PUN-NUM` (+0.17)

### Country / domain skew (D3)
- Max country over-representation ratio: **12.753**
- Question country counts (top 10): {'Spain': 1, 'Mexico': 2, 'Portugal': 1}
- Subdomain Herfindahl per strategy: template=0.1378, fact_to_question=0.13

## 6 · Gold calibration

- Human-reviewed items: **130**

| Rubric | Agent | Human pass% | LLM pass% | Agreement | κ | n |
|---|---|---:|---:|---:|---:|---:|
| answer_correct | B1 TriJudgeAnswer (majority_matches_key) | — | — | — | — | 0 |
| needs_source | B2 ClosedBookSolvability (NOT closed-book correct) | — | — | — | — | 0 |
| no_vague_language | A1 LexicalHygiene (no regex match) | — | — | — | — | 0 |
| verbatim_copy | A3 FactEcho (LCS < 0.6) | — | — | — | — | 0 |
| source_faithful | (human-only — no LLM proxy) | 76.2% | — | — | — | 130 |
| wine_category_leak | C2 WineCategoryLeak (no leaked distractor) | — | — | — | — | 0 |
| distractors_plausible | C2 WineCategoryLeak (partial — category leaks only) | — | — | — | — | 0 |

## 7 · Limitations & deferred checks

This MVA run excludes the following agents — failures in their weakness
classes cannot be disproved by this report alone.

- **C1 DistractorDifficulty** — per-distractor LLM plausibility scoring.
- **B3 ParaphraseStability** — stem-rewrite consistency.
- **B4 Ambiguity** — multi-defensible option scoring.
- **C3 SourceSwap** — robustness to fact substitution.
- **D2 DedupCalibration** — similarity-threshold P/R sweep.
- **D3-cultural** — LLM cultural-framing labelling (pure stats only ran).

Escalation triggers (if the audit finds these, run the deferred agents):
- A4 AUC ≥ 0.9 → run C1 + B4 on flagged subset.
- B1 fail rate ≥ 10% → run B3 + C3 to triangulate.
- D1 fail on any model → add more evaluator runs, include Llama/Qwen as secondary judges.

## 8 · Appendix — raw queries

```sql
-- All findings for this run
SELECT agent_id, severity, count(*) FROM audit_findings WHERE run_id = '9a085a74-8c82-4a1d-a0ae-b2c555d3e75f' GROUP BY 1,2;

-- Per-question rollup
SELECT * FROM v_question_audit_summary WHERE id IN (SELECT question_id FROM audit_findings WHERE run_id = '9a085a74-8c82-4a1d-a0ae-b2c555d3e75f');
```

_Generated 2026-05-02T09:12:19.345404_