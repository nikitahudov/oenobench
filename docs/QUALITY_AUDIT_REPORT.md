# OenoBench Quality Audit Report

- Run ID: `9045e16d-1466-476f-97dc-3126550f22c4`
- Corpus tag: `audit_pilot_v13`
- Corpus size: 146
- Config hash: `c2b4e5ebde5d3c3b...`
- Started: 2026-05-01 16:16:23.863870+00:00
- Completed: 2026-05-01 17:34:36.040741+00:00
- LLM calls: 1593
- Cost: $2.90

## 1 · Executive summary

- Findings across 9 agents: 561 pass · 125 warn · 66 fail · 0 error

| Agent | pass | warn | fail | error | total |
|---|---:|---:|---:|---:|---:|
| A1_LexicalHygiene | 140 | 2 | 4 | 0 | 146 |
| A2_BiasStats | 0 | 1 | 0 | 0 | 1 |
| A3_FactEcho | 81 | 59 | 6 | 0 | 146 |
| A4_TemplateFingerprint | 1 | 9 | 9 | 0 | 19 |
| B1_TriJudgeAnswer | 138 | 8 | 0 | 0 | 146 |
| B2_ClosedBookSolvability | 60 | 41 | 45 | 0 | 146 |
| C2_CategoryLeak | 141 | 3 | 2 | 0 | 146 |
| D1_SelfPreference | 0 | 1 | 0 | 0 | 1 |
| D3_SkewAudit | 0 | 1 | 0 | 0 | 1 |

## 2 · Methodology

- Corpus: 146 questions tagged `audit_pilot_v13`, seed 53.
- Agents: ['A1_LexicalHygiene', 'A2_BiasStats', 'A3_FactEcho', 'A4_TemplateFingerprint', 'B1_TriJudgeAnswer', 'B2_ClosedBookSolvability', 'C2_CategoryLeak', 'C4_DifficultyAudit', 'D1_SelfPreference', 'D3_SkewAudit']
- Judge models: ['claude', 'chatgpt', 'gemini']
- Thresholds and seeds encoded in config hash (full hash: `c2b4e5ebde5d3c3b52206adda3488b8bcdfd980e08bbea24f7787eb501e5d0db`).

## 3 · Per-strategy deep dive

### template

- Question count: **30**
- Severity rollup: pass=110, warn=25, fail=15
- Failures by agent:
  - B2_ClosedBookSolvability: 14
  - A3_FactEcho: 1
- Sample failures:
  - WB-REG-0534-L1  ·  B2_ClosedBookSolvability  ·  
    > Based on the fact, in which country is the Costières de Nîmes wine region located?
  - WB-PRD-0423-L1  ·  B2_ClosedBookSolvability  ·  
    > A wine writer placing Fritsch on a country-by-country map turns to the fact. Which country is specified?
  - WB-PRD-0425-L1  ·  B2_ClosedBookSolvability  ·  
    > What wine region is Château La Gaffelière part of?

### fact_to_question

- Question count: **30**
- Severity rollup: pass=123, warn=20, fail=7
- Failures by agent:
  - B2_ClosedBookSolvability: 6
  - A3_FactEcho: 1
- Sample failures:
  - WB-GRP-0619-L2  ·  B2_ClosedBookSolvability  ·  
    > In which two Spanish regions is the white wine grape variety Vigiriega grown?
  - WB-VIT-0465-L2  ·  B2_ClosedBookSolvability  ·  
    > Among thin-skinned black grape varieties, one is noted in viticulture for its particular vulnerability to spring frost, flower abortion during fruit set, and Plasmopara viticola in
  - WB-BIZ-0308-L2  ·  B2_ClosedBookSolvability  ·  
    > Under an Extended Producer Responsibility (EPR) law that includes a bottle deposit exemption, which category of packaging is removed from the scope of the term 'Beverage Container'

### comparative

- Question count: **30**
- Severity rollup: pass=113, warn=23, fail=18
- Failures by agent:
  - B2_ClosedBookSolvability: 12
  - A1_LexicalHygiene: 4
  - C2_CategoryLeak: 1
  - A4_TemplateFingerprint: 1
- Sample failures:
  - WB-GRP-0663-L2  ·  B2_ClosedBookSolvability  ·  
    > Which of the following grape varieties is classified as a dark-skinned type, used in red wine production, and identified by ampelographic authorities as having a pigmented berry sk
  - WB-GRP-0665-L2  ·  A1_LexicalHygiene  ·  matches=['question_text']
    > Which grape variety is a color mutation of a more widely known red variety and is specifically associated with a white wine expression in a renowned Spanish region, where it origin
  - WB-GRP-0616-L3  ·  B2_ClosedBookSolvability  ·  
    > One wine category introduced DOCG planting rules requiring newly established vineyards to use espalier training and a minimum density of 4,000 plants per hectare. The other had a t

### scenario_synthesis

- Question count: **27**
- Severity rollup: pass=101, warn=32, fail=16
- Failures by agent:
  - A4_TemplateFingerprint: 8
  - B2_ClosedBookSolvability: 6
  - A3_FactEcho: 2
- Sample failures:
  - WB-VIT-0469-L3  ·  A4_TemplateFingerprint  ·  
    > A vineyard manager is planning the fungicide and canopy management program for a vineyard block that has experienced powdery mildew pressure in previous seasons. The site is schedu
  - WB-REG-0536-L4  ·  A4_TemplateFingerprint  ·  
    > A winemaker in a German wine village is preparing labels for a new Riesling release harvested from a specific vineyard site. The wine exceeds the minimum ripeness requirement for i
  - WB-GRP-0650-L4  ·  A4_TemplateFingerprint  ·  
    > A winemaking team is redesigning a regional bottling strategy for a German area with 4,155 hectares of vines. Their historical review shows that, for many years, fruit from this ar

### distractor_mining

- Question count: **29**
- Severity rollup: pass=113, warn=22, fail=10
- Failures by agent:
  - B2_ClosedBookSolvability: 7
  - A3_FactEcho: 2
  - C2_CategoryLeak: 1
- Sample failures:
  - WB-VIT-0471-L3  ·  B2_ClosedBookSolvability  ·  
    > Which wine region in Hungary features a vineyard area of approximately 832 hectares and is known for its distinct volcanic terroir, yet has no significant plantings of Blaufränkisc
  - WB-GRP-0630-L3  ·  B2_ClosedBookSolvability  ·  
    > Which Italian wine style has permitted a minimum of 75% Sangiovese and up to 10% Canaiolo since 1996?
  - WB-PRD-0439-L3  ·  B2_ClosedBookSolvability  ·  
    > Which entity permits shipping a maximum of 12 9-liter cases of wine per consumer annually under its direct-to-consumer regulations?

## 3.5 · Per-strategy gold pass rates

Cross-tab of human-rated rubric pass percentages by generation strategy. Empty cells (`—`) mean no gold label was recorded for that (strategy, rubric) cell.

| strategy | n | answer_correct | needs_source | no_vague_language | verbatim_copy | source_faithful | wine_category_leak | distractors_plausible |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| comparative | 4 | 100.0% | 100.0% | 100.0% | — | 100.0% | — | 100.0% |
| distractor_mining | 4 | 100.0% | 100.0% | 100.0% | — | 100.0% | — | 100.0% |
| fact_to_question | 4 | 100.0% | 100.0% | 100.0% | — | 100.0% | — | 100.0% |
| scenario_synthesis | 4 | 100.0% | 100.0% | 100.0% | — | 100.0% | — | 100.0% |
| template | 4 | 50.0% | 50.0% | 50.0% | — | 50.0% | — | 50.0% |

## 4 · Per-generator deep dive

### chatgpt

- Authored question count: **20**
- Total fails: 7, warns: 21

### claude

- Authored question count: **18**
- Total fails: 10, warns: 12

### gemini

- Authored question count: **7**
- Total fails: 0, warns: 2

### llama

- Authored question count: **30**
- Total fails: 12, warns: 38

### qwen

- Authored question count: **41**
- Total fails: 22, warns: 24

### template_only

- Authored question count: **30**
- Total fails: 15, warns: 25

## 4.5 · Per-generator gold pass rates

Cross-tab of human-rated rubric pass percentages by generator model. Use this to compare quality across the 5 LLM generators (plus `template_only`) and decide allocation.

| generator | n | answer_correct | needs_source | no_vague_language | verbatim_copy | source_faithful | wine_category_leak | distractors_plausible |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| chatgpt | 3 | 100.0% | 100.0% | 100.0% | — | 100.0% | — | 100.0% |
| claude | 4 | 100.0% | 100.0% | 100.0% | — | 100.0% | — | 100.0% |
| llama | 3 | 100.0% | 100.0% | 100.0% | — | 100.0% | — | 100.0% |
| qwen | 6 | 100.0% | 100.0% | 100.0% | — | 100.0% | — | 100.0% |
| template_only | 4 | 50.0% | 50.0% | 50.0% | — | 50.0% | — | 50.0% |

## 5 · Cross-cutting findings

### Template detectability (A4)
- Held-out AUC: **0.8397**
- Top discriminative features: `len:tokens` (+1.49), `len:sentences` (-0.75), `bg:PUN-WORD` (-0.66), `bg:SHORT-PUN` (-0.54), `len:avg_word` (+0.37), `bg:WORD-SHORT` (-0.28), `bg:WORD-WORD` (+0.22), `bg:PUN-DET` (-0.22)

### Country / domain skew (D3)
- Max country over-representation ratio: **5.844**
- Question country counts (top 10): {'US': 1, 'Italy': 1, 'Spain': 2, 'France': 1, 'Austria': 2, 'Portugal': 2}
- Subdomain Herfindahl per strategy: template=0.1244, comparative=0.2689, fact_to_question=0.1689, distractor_mining=0.0868, scenario_synthesis=0.1166

## 6 · Gold calibration

- Human-reviewed items: **130**

| Rubric | Agent | Human pass% | LLM pass% | Agreement | κ | n |
|---|---|---:|---:|---:|---:|---:|
| answer_correct | B1 TriJudgeAnswer (majority_matches_key) | 90.0% | 100.0% | 90.0% | **0.0** | 20 |
| needs_source | B2 ClosedBookSolvability (NOT closed-book correct) | 90.0% | 25.0% | 35.0% | **0.071** | 20 |
| no_vague_language | A1 LexicalHygiene (no regex match) | 90.0% | 100.0% | 90.0% | **0.0** | 20 |
| verbatim_copy | A3 FactEcho (LCS < 0.6) | — | — | — | — | 0 |
| source_faithful | (human-only — no LLM proxy) | 76.2% | — | — | — | 130 |
| wine_category_leak | C2 WineCategoryLeak (no leaked distractor) | — | — | — | — | 0 |
| distractors_plausible | C2 WineCategoryLeak (partial — category leaks only) | 90.0% | 100.0% | 90.0% | **0.0** | 20 |

- ⚠ κ below 0.6 — downweight these LLM signals when interpreting strategy rollups: `answer_correct` (κ=0.0), `needs_source` (κ=0.071), `no_vague_language` (κ=0.0), `distractors_plausible` (κ=0.0).

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
SELECT agent_id, severity, count(*) FROM audit_findings WHERE run_id = '9045e16d-1466-476f-97dc-3126550f22c4' GROUP BY 1,2;

-- Per-question rollup
SELECT * FROM v_question_audit_summary WHERE id IN (SELECT question_id FROM audit_findings WHERE run_id = '9045e16d-1466-476f-97dc-3126550f22c4');
```

_Generated 2026-05-01T19:59:32.064656_