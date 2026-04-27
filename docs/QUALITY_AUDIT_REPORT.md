# OenoBench Quality Audit Report

- Run ID: `9ba6f760-5a6c-4403-9709-412c13eac30c`
- Corpus tag: `audit_pilot_v7`
- Corpus size: 242
- Config hash: `3d56b7d99fe9f153...`
- Started: 2026-04-27 06:36:29.754043+00:00
- Completed: 2026-04-27 09:41:06.917793+00:00
- LLM calls: 2436
- Cost: $4.42

## 1 · Executive summary

- Findings across 9 agents: 908 pass · 208 warn · 228 fail · 0 error

| Agent | pass | warn | fail | error | total |
|---|---:|---:|---:|---:|---:|
| A1_LexicalHygiene | 228 | 7 | 7 | 0 | 242 |
| A2_BiasStats | 0 | 1 | 0 | 0 | 1 |
| A3_FactEcho | 136 | 102 | 4 | 0 | 242 |
| A4_TemplateFingerprint | 1 | 45 | 85 | 0 | 131 |
| B1_TriJudgeAnswer | 229 | 11 | 2 | 0 | 242 |
| B2_ClosedBookSolvability | 77 | 37 | 128 | 0 | 242 |
| C2_CategoryLeak | 237 | 5 | 0 | 0 | 242 |
| D1_SelfPreference | 0 | 0 | 1 | 0 | 1 |
| D3_SkewAudit | 0 | 0 | 1 | 0 | 1 |

## 2 · Methodology

- Corpus: 242 questions tagged `audit_pilot_v7`, seed 44.
- Agents: ['A1_LexicalHygiene', 'A2_BiasStats', 'A3_FactEcho', 'A4_TemplateFingerprint', 'B1_TriJudgeAnswer', 'B2_ClosedBookSolvability', 'C2_CategoryLeak', 'C4_DifficultyAudit', 'D1_SelfPreference', 'D3_SkewAudit']
- Judge models: ['claude', 'chatgpt', 'gemini']
- Thresholds and seeds encoded in config hash (full hash: `3d56b7d99fe9f15340ff1b8289a32785b42a031fed43696a9d70d4a31cd57e72`).

## 3 · Per-strategy deep dive

### template

- Question count: **30**
- Severity rollup: pass=112, warn=16, fail=22
- Failures by agent:
  - B2_ClosedBookSolvability: 21
  - A3_FactEcho: 1
- Sample failures:
  - WB-REG-0397-L1  ·  B2_ClosedBookSolvability  ·  
    > A buyer is routing a shipment of Clements Hills AVA wine. Based on the fact, which US state is the origin?
  - WB-REG-0398-L1  ·  B2_ClosedBookSolvability  ·  
    > A buyer is routing a shipment of Kelsey Bench-Lake County AVA wine. Based on the fact, which US state is the origin?
  - WB-GRP-0434-L1  ·  B2_ClosedBookSolvability  ·  
    > Per the fact, which country hosts cultivation of Malbec?

### fact_to_question

- Question count: **120**
- Severity rollup: pass=458, warn=102, fail=97
- Failures by agent:
  - B2_ClosedBookSolvability: 67
  - A4_TemplateFingerprint: 27
  - A3_FactEcho: 2
  - A1_LexicalHygiene: 1
- Sample failures:
  - WB-BIZ-0260-L2  ·  A4_TemplateFingerprint  ·  
    > What is the role of the South African Wine Evaluation Committee in the country's wine industry?
  - WB-VIT-0345-L2  ·  A4_TemplateFingerprint  ·  
    > During which stage of development do grapevines typically not produce flowers, based on their physiological maturation pattern?
  - WB-WMK-0291-L2  ·  A4_TemplateFingerprint  ·  
    > When dealing with underripe fruit during red wine production, what is the observed impact of prolonging skin contact time?

### comparative

- Question count: **34**
- Severity rollup: pass=128, warn=35, fail=28
- Failures by agent:
  - B2_ClosedBookSolvability: 12
  - A4_TemplateFingerprint: 12
  - A1_LexicalHygiene: 3
  - B1_TriJudgeAnswer: 1
- Sample failures:
  - WB-VIT-0368-L2  ·  B2_ClosedBookSolvability  ·  
    > An American Viticultural Area situated entirely within a single California county, taking its identity from the state's largest natural freshwater lake, best matches which of the f
  - WB-GRP-0462-L2  ·  B2_ClosedBookSolvability  ·  
    > Which grape variety is associated with wines that have high acidity and tannin?
  - WB-VIT-0370-L3  ·  A4_TemplateFingerprint  ·  
    > Which of these wine regions is defined by its location within a specific county in California and recognized as a distinct viticultural area due to its unique geographic setting in

### scenario_synthesis

- Question count: **42**
- Severity rollup: pass=149, warn=37, fail=65
- Failures by agent:
  - A4_TemplateFingerprint: 40
  - B2_ClosedBookSolvability: 23
  - A1_LexicalHygiene: 2
- Sample failures:
  - WB-REG-0419-L3  ·  A4_TemplateFingerprint  ·  
    > A viticultural team in Quebec is preparing for their inaugural late-season sweet wine harvest. Because they plan to pick during the freezing pre-dawn hours, they are finalizing the
  - WB-REG-0427-L2  ·  A4_TemplateFingerprint  ·  
    > A viticulturist is evaluating two Chilean coastal wine regions for a new planting of aromatic white varieties. Both regions benefit from maritime influence, but in one region, the 
  - WB-REG-0420-L4  ·  A4_TemplateFingerprint  ·  
    > A production director at a California wine estate is finalizing the bottling schedule for three distinct single-appellation red wines. To align with a new 'Heritage Timeline' marke

### distractor_mining

- Question count: **16**
- Severity rollup: pass=60, warn=17, fail=14
- Failures by agent:
  - A4_TemplateFingerprint: 6
  - B2_ClosedBookSolvability: 5
  - A1_LexicalHygiene: 1
  - B1_TriJudgeAnswer: 1
  - A3_FactEcho: 1
- Sample failures:
  - WB-GRP-0501-L3  ·  B2_ClosedBookSolvability  ·  
    > Which grape variety was historically cultivated across Catalonia and remained in use both prior to and following the phylloxera epidemic, distinguishing it by its long-standing pre
  - WB-GRP-0502-L4  ·  A4_TemplateFingerprint  ·  
    > Which historical figure is associated with the development of disease-resistant grape varieties that enabled viticulture in regions where phylloxera and fungal pressures had previo
  - WB-REG-0430-L4  ·  A4_TemplateFingerprint  ·  
    > Which of the following American Viticultural Areas received its official federal designation during the year 1981?

## 4 · Per-generator deep dive

### chatgpt

- Authored question count: **40**
- Total fails: 40, warns: 37

### claude

- Authored question count: **39**
- Total fails: 36, warns: 36

### gemini

- Authored question count: **38**
- Total fails: 32, warns: 25

### llama

- Authored question count: **48**
- Total fails: 43, warns: 43

### qwen

- Authored question count: **47**
- Total fails: 53, warns: 50

### template_only

- Authored question count: **30**
- Total fails: 22, warns: 16

## 5 · Cross-cutting findings

### Template detectability (A4)
- Held-out AUC: **0.7417**
- Top discriminative features: `len:tokens` (+1.24), `len:sentences` (-0.61), `bg:PUN-WORD` (-0.57), `len:avg_word` (+0.52), `bg:SHORT-PUN` (-0.42), `bg:WORD-SHORT` (-0.25), `bg:DET-WORD` (+0.18), `bg:PUN-DET` (-0.18)

### Country / domain skew (D3)
- Max country over-representation ratio: **10.613**
- Question country counts (top 10): {'US': 1, 'Italy': 4, 'Spain': 1, 'Canada': 2, 'France': 3, 'Germany': 1, 'Hungary': 1, 'Uruguay': 1, 'Bulgaria': 1, 'Portugal': 1}
- Subdomain Herfindahl per strategy: template=0.0911, comparative=0.4948, fact_to_question=0.0561, distractor_mining=0.1094, scenario_synthesis=0.0816

## 6 · Gold calibration

- Human-reviewed items: **110**

| Rubric | Agent | Human pass% | LLM pass% | Agreement | κ | n |
|---|---|---:|---:|---:|---:|---:|
| answer_correct | B1 TriJudgeAnswer (majority_matches_key) | — | — | — | — | 0 |
| needs_source | B2 ClosedBookSolvability (NOT closed-book correct) | — | — | — | — | 0 |
| no_vague_language | A1 LexicalHygiene (no regex match) | — | — | — | — | 0 |
| verbatim_copy | A3 FactEcho (LCS < 0.6) | — | — | — | — | 0 |
| source_faithful | (human-only — no LLM proxy) | 73.6% | — | — | — | 110 |
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
SELECT agent_id, severity, count(*) FROM audit_findings WHERE run_id = '9ba6f760-5a6c-4403-9709-412c13eac30c' GROUP BY 1,2;

-- Per-question rollup
SELECT * FROM v_question_audit_summary WHERE id IN (SELECT question_id FROM audit_findings WHERE run_id = '9ba6f760-5a6c-4403-9709-412c13eac30c');
```

_Generated 2026-04-27T09:41:08.196647_