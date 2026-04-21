# OenoBench Quality Audit Report

- Run ID: `0bfe85dc-4fdc-4500-b274-a4b05d982e20`
- Corpus tag: `audit_pilot_v3`
- Corpus size: 331
- Config hash: `9b5412b7428a2322...`
- Started: 2026-04-20 23:29:02.857716+00:00
- Completed: (in progress)
- LLM calls: 3479
- Cost: $8.51

## 1 · Executive summary

- Findings across 10 agents: 1312 pass · 397 warn · 275 fail · 6 error

| Agent | pass | warn | fail | error | total |
|---|---:|---:|---:|---:|---:|
| A1_LexicalHygiene | 302 | 13 | 16 | 0 | 331 |
| A2_BiasStats | 0 | 0 | 1 | 0 | 1 |
| A3_FactEcho | 181 | 134 | 16 | 0 | 331 |
| A4_TemplateFingerprint | 1 | 0 | 0 | 0 | 1 |
| B1_TriJudgeAnswer | 304 | 18 | 9 | 0 | 331 |
| B2_ClosedBookSolvability | 73 | 38 | 220 | 0 | 331 |
| C2_CategoryLeak | 324 | 7 | 0 | 0 | 331 |
| C4_DifficultyAudit | 127 | 186 | 12 | 6 | 331 |
| D1_SelfPreference | 0 | 1 | 0 | 0 | 1 |
| D3_SkewAudit | 0 | 0 | 1 | 0 | 1 |

## 2 · Methodology

- Corpus: 331 questions tagged `audit_pilot_v3`, seed 42.
- Agents: ['A1_LexicalHygiene', 'A2_BiasStats', 'A3_FactEcho', 'A4_TemplateFingerprint', 'B1_TriJudgeAnswer', 'B2_ClosedBookSolvability', 'C2_CategoryLeak', 'C4_DifficultyAudit', 'D1_SelfPreference', 'D3_SkewAudit']
- Judge models: ['claude', 'chatgpt', 'gemini']
- Thresholds and seeds encoded in config hash (full hash: `9b5412b7428a2322c47dd0aadfa23bed8de9ec86c748b0b89471144a04ae7dc5`).

## 3 · Per-strategy deep dive

### template

- Question count: **14**
- Severity rollup: pass=53, warn=13, fail=18
- Failures by agent:
  - B2_ClosedBookSolvability: 8
  - A3_FactEcho: 7
  - B1_TriJudgeAnswer: 2
  - C4_DifficultyAudit: 1
- Sample failures:
  - WB-REG-0136-L1  ·  B2_ClosedBookSolvability  ·  
    > Decide True or False — Nebbiolo is an authorised variety in Terre Alfieri.
  - WB-PRD-0147-L3  ·  A3_FactEcho  ·  lcs_ratio=0.75
    > True or False: Specific colour requirement (if applicable) is located in the align="center" | lightly coloured red wine region.
  - WB-PRD-0148-L2  ·  B2_ClosedBookSolvability  ·  
    > True or False: Rocca delle Macìe is located in the Tuscany wine region.

### fact_to_question

- Question count: **120**
- Severity rollup: pass=471, warn=132, fail=115
- Failures by agent:
  - B2_ClosedBookSolvability: 102
  - C4_DifficultyAudit: 7
  - A1_LexicalHygiene: 5
  - A3_FactEcho: 1
- Sample failures:
  - WB-WMK-0131-L2  ·  B2_ClosedBookSolvability  ·  
    > What type of aging is traditionally used for Bourgogne Aligoté wines?
  - WB-WMK-0134-L2  ·  B2_ClosedBookSolvability  ·  
    > Which materials are commonly used by modern South American wineries for aging wine?
  - WB-WMK-0136-L2  ·  B2_ClosedBookSolvability  ·  
    > Which of the following areas should be considered in preparation for the winemaking process called crush?

### comparative

- Question count: **57**
- Severity rollup: pass=224, warn=79, fail=38
- Failures by agent:
  - B2_ClosedBookSolvability: 27
  - B1_TriJudgeAnswer: 5
  - A1_LexicalHygiene: 3
  - A3_FactEcho: 2
  - C4_DifficultyAudit: 1
- Sample failures:
  - WB-WMK-0132-L2  ·  B2_ClosedBookSolvability  ·  
    > A wine labeled as DOCG must meet certain requirements. If a wine has been aged for 21 months, with 9 months in oak barrels, which classification is it more likely to be?
  - WB-WMK-0133-L3  ·  B2_ClosedBookSolvability  ·  
    > Which production method is used for Trento DOC wines?
  - WB-VIT-0142-L3  ·  B1_TriJudgeAnswer  ·  majority_matches_key=False
    > A viticulturist is evaluating a specific Napa Valley appellation characterized by exceptionally low temperatures compared to the surrounding areas, a feature that significantly ext

### scenario_synthesis

- Question count: **57**
- Severity rollup: pass=213, warn=75, fail=53
- Failures by agent:
  - B2_ClosedBookSolvability: 42
  - A1_LexicalHygiene: 5
  - A3_FactEcho: 3
  - C4_DifficultyAudit: 2
  - B1_TriJudgeAnswer: 1
- Sample failures:
  - WB-WMK-0128-L3  ·  C4_DifficultyAudit  ·  
    > A Georgian winemaker is preparing to ferment their wine using traditional kvevri vessels. They have sourced clay from two different regions, with one having higher mineral content 
  - WB-WMK-0138-L4  ·  B2_ClosedBookSolvability  ·  
    > A Champagne house is creating a special limited edition cuvée to commemorate a significant anniversary. They want to use only vintage wine for this release, and age it on the lees 
  - WB-WMK-0141-L2  ·  B2_ClosedBookSolvability  ·  
    > A winemaker in the Wairarapa region of New Zealand is deciding whether to age their Sauvignon Blanc in stainless steel or oak barrels. They want to produce a wine that aligns with 

### distractor_mining

- Question count: **83**
- Severity rollup: pass=350, warn=97, fail=49
- Failures by agent:
  - B2_ClosedBookSolvability: 41
  - A3_FactEcho: 3
  - A1_LexicalHygiene: 3
  - C4_DifficultyAudit: 1
  - B1_TriJudgeAnswer: 1
- Sample failures:
  - WB-REG-0157-L4  ·  B2_ClosedBookSolvability  ·  
    > Which California AVA was established in 2005?
  - WB-WMK-0135-L3  ·  A3_FactEcho  ·  lcs_ratio=0.381
    > Which technique combination shows promise for accelerating wine ageing while preserving sensory quality?
  - WB-VIT-0127-L4  ·  B2_ClosedBookSolvability  ·  
    > During a controlled environmental study evaluating the resilience of juvenile white grapevines, researchers monitored specific physiological responses. Which simulated climatic str

## 4 · Per-generator deep dive

### chatgpt

- Authored question count: **66**
- Total fails: 58, warns: 73

### claude

- Authored question count: **59**
- Total fails: 45, warns: 73

### gemini

- Authored question count: **57**
- Total fails: 45, warns: 56

### llama

- Authored question count: **65**
- Total fails: 48, warns: 87

### qwen

- Authored question count: **70**
- Total fails: 59, warns: 94

### template_only

- Authored question count: **14**
- Total fails: 18, warns: 13

## 5 · Cross-cutting findings

### Template detectability (A4)
- Held-out AUC: **None**

### Country / domain skew (D3)
- Max country over-representation ratio: **3.139**
- Question country counts (top 10): {'US': 2, 'Chile': 6, 'Italy': 9, 'Canada': 1, 'Israel': 3, 'England': 1, 'Germany': 1, 'Australia': 12, 'New Zealand': 20, 'South Africa': 39}
- Subdomain Herfindahl per strategy: template=0.1837, comparative=0.4004, fact_to_question=0.091, distractor_mining=0.0515, scenario_synthesis=0.0853

## 6 · Gold calibration

- Human-reviewed items: **60**

| Rubric | Agent | Human pass% | LLM pass% | Agreement | κ | n |
|---|---|---:|---:|---:|---:|---:|
| answer_correct | B1 TriJudgeAnswer (majority_matches_key) | — | — | — | — | 0 |
| needs_source | B2 ClosedBookSolvability (NOT closed-book correct) | — | — | — | — | 0 |
| no_vague_language | A1 LexicalHygiene (no regex match) | — | — | — | — | 0 |
| source_faithful | A3 FactEcho (LCS < 0.6) | — | — | — | — | 0 |
| distractors_plausible | C2 CategoryLeak (no leaked distractor) | — | — | — | — | 0 |

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
SELECT agent_id, severity, count(*) FROM audit_findings WHERE run_id = '0bfe85dc-4fdc-4500-b274-a4b05d982e20' GROUP BY 1,2;

-- Per-question rollup
SELECT * FROM v_question_audit_summary WHERE id IN (SELECT question_id FROM audit_findings WHERE run_id = '0bfe85dc-4fdc-4500-b274-a4b05d982e20');
```

_Generated 2026-04-21T02:54:14.500970_