# OenoBench Quality Audit Report

- Run ID: `2ba38269-5e66-44aa-aaaf-010dc7ef19d4`
- Corpus tag: `release_v1.1`
- Corpus size: 3670
- Config hash: `6d87248d5fd9dcc2...`
- Started: 2026-05-03 13:51:26.416321+00:00
- Completed: 2026-05-03 19:13:34.154134+00:00
- LLM calls: 29610
- Cost: $75.79

## 1 · Executive summary

- Findings across 10 agents: 14425 pass · 5889 warn · 2984 fail · 7 error

| Agent | pass | warn | fail | error | total |
|---|---:|---:|---:|---:|---:|
| A1_LexicalHygiene | 3502 | 108 | 60 | 0 | 3670 |
| A2_BiasStats | 0 | 0 | 1 | 0 | 1 |
| A3_FactEcho | 1713 | 1894 | 63 | 0 | 3670 |
| A4_TemplateFingerprint | 1 | 1281 | 0 | 0 | 1282 |
| B1_TriJudgeAnswer | 3449 | 174 | 47 | 0 | 3670 |
| B2_ClosedBookSolvability | 1320 | 898 | 1452 | 0 | 3670 |
| C2_CategoryLeak | 3611 | 50 | 9 | 0 | 3670 |
| C4_DifficultyAudit | 829 | 1483 | 1351 | 7 | 3670 |
| D1_SelfPreference | 0 | 0 | 1 | 0 | 1 |
| D3_SkewAudit | 0 | 1 | 0 | 0 | 1 |

## 2 · Methodology

- Corpus: 3670 questions tagged `release_v1.1`, seed 100.
- Agents: ['A1_LexicalHygiene', 'A2_BiasStats', 'A3_FactEcho', 'A4_TemplateFingerprint', 'B1_TriJudgeAnswer', 'B2_ClosedBookSolvability', 'C2_CategoryLeak', 'C4_DifficultyAudit', 'D1_SelfPreference', 'D3_SkewAudit']
- Judge models: ['claude', 'chatgpt', 'gemini']
- Thresholds and seeds encoded in config hash (full hash: `6d87248d5fd9dcc2ead85b72f280c38e0a4670d15fc1aa2ed727e73300efaffa`).

## 3 · Per-strategy deep dive

### template

- Question count: **433**
- Severity rollup: pass=1725, warn=499, fail=385
- Failures by agent:
  - B2_ClosedBookSolvability: 291
  - C4_DifficultyAudit: 84
  - A3_FactEcho: 10
- Sample failures:
  - WB-PRD-0257-L2  ·  B2_ClosedBookSolvability  ·  
    > Name the wine region where Nittnaus Hans und Christine is found.
  - WB-REG-0582-L1  ·  B2_ClosedBookSolvability  ·  
    > The fact assigns the Tehachapi Mountains AVA to which US state?
  - WB-REG-0809-L2  ·  B2_ClosedBookSolvability  ·  
    > Based on the source fact, the Bell Mountain AVA is found in which state?

### fact_to_question

- Question count: **2098**
- Severity rollup: pass=8343, warn=3143, fail=1737
- Failures by agent:
  - C4_DifficultyAudit: 894
  - B2_ClosedBookSolvability: 761
  - A3_FactEcho: 37
  - A1_LexicalHygiene: 27
  - B1_TriJudgeAnswer: 11
  - C2_CategoryLeak: 7
- Sample failures:
  - WB-WMK-0409-L2  ·  C4_DifficultyAudit  ·  
    > How many yeast species were identified by Renouf et al. (2007) on the surface of grape berries across different varieties?
  - WB-PRD-0487-L2  ·  B2_ClosedBookSolvability  ·  
    > In which Chilean town is the Viña Tarapacá winery located?
  - WB-WMK-0265-L2  ·  B2_ClosedBookSolvability  ·  
    > In French wine terminology, what does "cuvée" refer to?

### comparative

- Question count: **308**
- Severity rollup: pass=1194, warn=537, fail=248
- Failures by agent:
  - B2_ClosedBookSolvability: 114
  - C4_DifficultyAudit: 105
  - B1_TriJudgeAnswer: 17
  - A1_LexicalHygiene: 6
  - A3_FactEcho: 5
  - C2_CategoryLeak: 1
- Sample failures:
  - WB-GRP-0748-L3  ·  B1_TriJudgeAnswer  ·  majority_matches_key=False
    > A red grape variety fits the following profile: historically valued in Piedmont for generous yields and the capacity to reach ripeness roughly a fortnight ahead of its more tempera
  - WB-PRD-0509-L2  ·  B2_ClosedBookSolvability  ·  
    > Which German wine region is restricted from producing all quality levels of German wine classification?
  - WB-REG-0625-L3  ·  C4_DifficultyAudit  ·  
    > Which wine is produced in a region where the primary grape must constitute at least 85% of the blend, allowing up to 15% of other permitted varieties, and where the grape used for 

### scenario_synthesis

- Question count: **345**
- Severity rollup: pass=1302, warn=757, fail=278
- Failures by agent:
  - C4_DifficultyAudit: 136
  - B2_ClosedBookSolvability: 127
  - B1_TriJudgeAnswer: 8
  - A1_LexicalHygiene: 4
  - A3_FactEcho: 2
  - C2_CategoryLeak: 1
- Sample failures:
  - WB-GRP-0749-L2  ·  B2_ClosedBookSolvability  ·  
    > A winery team is reviewing old vineyard records before propagating material for a new dry white wine project. The archive shows one parent grape with an unusually dense concentrati
  - WB-WMK-0371-L2  ·  C4_DifficultyAudit  ·  
    > A winemaker in DOC Bairrada is producing a high-quality Espumante using the traditional method. They are considering whether to allow the wine to undergo malolactic fermentation. W
  - WB-WMK-0286-L2  ·  B2_ClosedBookSolvability  ·  
    > A winemaker in Ontario is producing a unique sparkling wine using the Traditional Method. After riddling and disgorgement, they want to top up the wine with a dosage to add a touch

### distractor_mining

- Question count: **486**
- Severity rollup: pass=1860, warn=952, fail=334
- Failures by agent:
  - B2_ClosedBookSolvability: 159
  - C4_DifficultyAudit: 132
  - A1_LexicalHygiene: 23
  - B1_TriJudgeAnswer: 11
  - A3_FactEcho: 9
- Sample failures:
  - WB-REG-0642-L3  ·  B2_ClosedBookSolvability  ·  
    > An American Viticultural Area created in 1984 in Arkansas corresponds to which of the following places?
  - WB-REG-0654-L3  ·  B2_ClosedBookSolvability  ·  
    > Which Spanish wine designation matches these clues: it is a protected designation of origin in Catalonia, positioned in the far northeast of that autonomous community, and it lies 
  - WB-GRP-0630-L3  ·  B2_ClosedBookSolvability  ·  
    > Which Italian wine style has permitted a minimum of 75% Sangiovese and up to 10% Canaiolo since 1996?

## 3.5 · Per-strategy gold pass rates

Cross-tab of human-rated rubric pass percentages by generation strategy. Empty cells (`—`) mean no gold label was recorded for that (strategy, rubric) cell.

| strategy | n | answer_correct | needs_source | no_vague_language | verbatim_copy | source_faithful | wine_category_leak | distractors_plausible |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| comparative | 4 | 100.0% | 100.0% | 100.0% | — | 100.0% | — | 100.0% |
| distractor_mining | 4 | 100.0% | 100.0% | 100.0% | — | 100.0% | — | 100.0% |
| fact_to_question | 4 | 100.0% | 100.0% | 100.0% | — | 100.0% | — | 100.0% |
| scenario_synthesis | 3 | 100.0% | 100.0% | 100.0% | — | 100.0% | — | 100.0% |
| template | 4 | 50.0% | 50.0% | 50.0% | — | 50.0% | — | 50.0% |

## 4 · Per-generator deep dive

### chatgpt

- Authored question count: **604**
- Total fails: 490, warns: 877

### claude

- Authored question count: **666**
- Total fails: 585, warns: 1148

### gemini

- Authored question count: **457**
- Total fails: 347, warns: 686

### llama

- Authored question count: **741**
- Total fails: 556, warns: 1262

### qwen

- Authored question count: **769**
- Total fails: 619, warns: 1416

### template_only

- Authored question count: **433**
- Total fails: 385, warns: 499

## 4.5 · Per-generator gold pass rates

Cross-tab of human-rated rubric pass percentages by generator model. Use this to compare quality across the 5 LLM generators (plus `template_only`) and decide allocation.

| generator | n | answer_correct | needs_source | no_vague_language | verbatim_copy | source_faithful | wine_category_leak | distractors_plausible |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| chatgpt | 3 | 100.0% | 100.0% | 100.0% | — | 100.0% | — | 100.0% |
| claude | 4 | 100.0% | 100.0% | 100.0% | — | 100.0% | — | 100.0% |
| llama | 2 | 100.0% | 100.0% | 100.0% | — | 100.0% | — | 100.0% |
| qwen | 6 | 100.0% | 100.0% | 100.0% | — | 100.0% | — | 100.0% |
| template_only | 4 | 50.0% | 50.0% | 50.0% | — | 50.0% | — | 50.0% |

## 5 · Cross-cutting findings

### Template detectability (A4)
- Held-out AUC: **0.639**
- Top discriminative features: `len:avg_word` (+0.77), `len:tokens` (+0.18), `bg:PUN-WORD` (-0.07), `bg:WORD-WORD` (+0.05), `bg:PUN-NUM` (+0.05), `bg:NUM-SHORT` (+0.03), `len:sentences` (-0.03), `bg:DET-WORD` (+0.02)

### Country / domain skew (D3)
- Max country over-representation ratio: **2.555**
- Question country counts (top 10): {'US': 44, 'Chile': 27, 'Italy': 44, 'Spain': 22, 'Canada': 2, 'France': 38, 'Israel': 2, 'Austria': 20, 'England': 3, 'Georgia': 2}
- Subdomain Herfindahl per strategy: template=0.0719, comparative=0.2121, fact_to_question=0.0391, distractor_mining=0.0577, scenario_synthesis=0.057

## 6 · Gold calibration

- Human-reviewed items: **130**

| Rubric | Agent | Human pass% | LLM pass% | Agreement | κ | n |
|---|---|---:|---:|---:|---:|---:|
| answer_correct | B1 TriJudgeAnswer (majority_matches_key) | 89.5% | 100.0% | 89.5% | **0.0** | 19 |
| needs_source | B2 ClosedBookSolvability (NOT closed-book correct) | 89.5% | 26.3% | 26.3% | **-0.073** | 19 |
| no_vague_language | A1 LexicalHygiene (no regex match) | 89.5% | 100.0% | 89.5% | **0.0** | 19 |
| verbatim_copy | A3 FactEcho (LCS < 0.6) | — | — | — | — | 0 |
| source_faithful | (human-only — no LLM proxy) | 76.2% | — | — | — | 130 |
| wine_category_leak | C2 WineCategoryLeak (no leaked distractor) | — | — | — | — | 0 |
| distractors_plausible | C2 WineCategoryLeak (partial — category leaks only) | 89.5% | 100.0% | 89.5% | **0.0** | 19 |

- ⚠ κ below 0.6 — downweight these LLM signals when interpreting strategy rollups: `answer_correct` (κ=0.0), `needs_source` (κ=-0.073), `no_vague_language` (κ=0.0), `distractors_plausible` (κ=0.0).

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
SELECT agent_id, severity, count(*) FROM audit_findings WHERE run_id = '2ba38269-5e66-44aa-aaaf-010dc7ef19d4' GROUP BY 1,2;

-- Per-question rollup
SELECT * FROM v_question_audit_summary WHERE id IN (SELECT question_id FROM audit_findings WHERE run_id = '2ba38269-5e66-44aa-aaaf-010dc7ef19d4');
```

_Generated 2026-05-03T19:14:20.059490_