# OenoBench Quality Audit Report

- Run ID: `7dc2ab81-bc9a-40b1-a1a4-3ddf66a6e6fe`
- Corpus tag: `audit_pilot_v8`
- Corpus size: 111
- Config hash: `f8a1b4b7b85a8e63...`
- Started: 2026-04-28 19:40:08.030940+00:00
- Completed: 2026-04-28 21:16:44.857129+00:00
- LLM calls: 1313
- Cost: $2.33

## 1 · Executive summary

- Findings across 9 agents: 413 pass · 94 warn · 53 fail · 0 error

| Agent | pass | warn | fail | error | total |
|---|---:|---:|---:|---:|---:|
| A1_LexicalHygiene | 110 | 0 | 1 | 0 | 111 |
| A2_BiasStats | 0 | 1 | 0 | 0 | 1 |
| A3_FactEcho | 55 | 56 | 0 | 0 | 111 |
| A4_TemplateFingerprint | 0 | 2 | 0 | 0 | 2 |
| B1_TriJudgeAnswer | 97 | 13 | 1 | 0 | 111 |
| B2_ClosedBookSolvability | 42 | 19 | 50 | 0 | 111 |
| C2_CategoryLeak | 109 | 2 | 0 | 0 | 111 |
| D1_SelfPreference | 0 | 0 | 1 | 0 | 1 |
| D3_SkewAudit | 0 | 1 | 0 | 0 | 1 |

## 2 · Methodology

- Corpus: 111 questions tagged `audit_pilot_v8`, seed 45.
- Agents: ['A1_LexicalHygiene', 'A2_BiasStats', 'A3_FactEcho', 'A4_TemplateFingerprint', 'B1_TriJudgeAnswer', 'B2_ClosedBookSolvability', 'C2_CategoryLeak', 'C4_DifficultyAudit', 'D1_SelfPreference', 'D3_SkewAudit']
- Judge models: ['claude', 'chatgpt', 'gemini']
- Thresholds and seeds encoded in config hash (full hash: `f8a1b4b7b85a8e6344e14558c5e2d4d680e6d91034f2c169847c70cbecef57bb`).

## 3 · Per-strategy deep dive

### template

- Question count: **20**
- Severity rollup: pass=74, warn=14, fail=12
- Failures by agent:
  - B2_ClosedBookSolvability: 12
- Sample failures:
  - WB-REG-0439-L1  ·  B2_ClosedBookSolvability  ·  
    > A critic reviewing Chehalem Mountains AVA wines wants to verify the state of origin. The fact identifies which state?
  - WB-REG-0440-L3  ·  B2_ClosedBookSolvability  ·  
    > Which parent region encompasses Montefalco Sagrantino?
  - WB-PRD-0361-L1  ·  B2_ClosedBookSolvability  ·  
    > A wine writer placing Paolo Scavino on a country-by-country map turns to the fact. Which country is specified?

### fact_to_question

- Question count: **40**
- Severity rollup: pass=155, warn=25, fail=20
- Failures by agent:
  - B2_ClosedBookSolvability: 20
- Sample failures:
  - WB-WMK-0317-L2  ·  B2_ClosedBookSolvability  ·  
    > Which of the following methods can be used to introduce carbon dioxide into a sparkling wine, according to winemaking regulations?
  - WB-WMK-0320-L2  ·  B2_ClosedBookSolvability  ·  
    > Which country includes the Slavonian oak forest, a notable source of oak in cooperage?
  - WB-VIT-0393-L2  ·  B2_ClosedBookSolvability  ·  
    > Which Italian wine production area is noted for having basalt-derived volcanic earth, a geological feature that is credited with giving its wines a distinct mineral profile?

### comparative

- Question count: **14**
- Severity rollup: pass=53, warn=12, fail=5
- Failures by agent:
  - B2_ClosedBookSolvability: 5
- Sample failures:
  - WB-VIT-0406-L2  ·  B2_ClosedBookSolvability  ·  
    > One of these regions is characterized by roughly two extra daylight hours per day during the growing season, along with relatively steady temperatures, while the other is noted for
  - WB-VIT-0400-L2  ·  B2_ClosedBookSolvability  ·  
    > Which American Viticultural Area was originally approved under a different name and later became the first to undergo an official name change, covering approximately 33,000 acres i
  - WB-GRP-0515-L2  ·  B2_ClosedBookSolvability  ·  
    > Which grape variety is described by UC Davis FPS as having grey-colored berries?

### scenario_synthesis

- Question count: **23**
- Severity rollup: pass=80, warn=26, fail=10
- Failures by agent:
  - B2_ClosedBookSolvability: 9
  - B1_TriJudgeAnswer: 1
- Sample failures:
  - WB-GRP-0521-L3  ·  B2_ClosedBookSolvability  ·  
    > A consulting winemaker is helping a Mediterranean estate redesign a red blend built around Sangiovese. The brief is to use a historically established approach for this grape, take 
  - WB-GRP-0536-L4  ·  B1_TriJudgeAnswer  ·  majority_matches_key=False
    > A winemaker in northern Italy wants to produce a sparkling rosé using a traditional local grape variety. Which grape should they select to make a rosé sparkling wine that showcases
  - WB-VIT-0402-L3  ·  B2_ClosedBookSolvability  ·  
    > A winemaker in Pennsylvania is concerned about potential pest issues in their vineyard as harvest approaches. They have noticed some insect activity on the edges of the vineyard an

### distractor_mining

- Question count: **14**
- Severity rollup: pass=51, warn=14, fail=5
- Failures by agent:
  - B2_ClosedBookSolvability: 4
  - A1_LexicalHygiene: 1
- Sample failures:
  - WB-BIZ-0285-L3  ·  B2_ClosedBookSolvability  ·  
    > Which German wine entity is described by this classification detail: it is organized into 2 Bereiche, containing 11 Großlagen and 111 Einzellagen?
  - WB-REG-0452-L3  ·  A1_LexicalHygiene  ·  matches=['question_text']
    > Elevation to DOCG status in 1980 placed which appellation among the earliest Italian wines to receive that top-tier designation?
  - WB-PRD-0375-L3  ·  B2_ClosedBookSolvability  ·  
    > Which Georgian estate was home to a fashionable 19th century salon?

## 4 · Per-generator deep dive

### chatgpt

- Authored question count: **15**
- Total fails: 8, warns: 14

### claude

- Authored question count: **17**
- Total fails: 8, warns: 13

### gemini

- Authored question count: **13**
- Total fails: 2, warns: 8

### llama

- Authored question count: **26**
- Total fails: 12, warns: 24

### qwen

- Authored question count: **20**
- Total fails: 10, warns: 18

### template_only

- Authored question count: **20**
- Total fails: 12, warns: 14

## 5 · Cross-cutting findings

### Template detectability (A4)
- Held-out AUC: **0.9068**
- Top discriminative features: `len:tokens` (+1.35), `len:sentences` (-0.63), `bg:PUN-WORD` (-0.55), `bg:SHORT-PUN` (-0.41), `bg:WORD-SHORT` (-0.32), `len:avg_word` (+0.26), `bg:PUN-DET` (-0.20), `bg:WORD-WORD` (+0.18)

### Country / domain skew (D3)
- Max country over-representation ratio: **4.185**
- Question country counts (top 10): {'US': 2, 'Chile': 1, 'Italy': 3, 'Australia': 2, 'New Zealand': 1, 'South Africa': 1}
- Subdomain Herfindahl per strategy: template=0.135, comparative=0.3367, fact_to_question=0.0675, distractor_mining=0.0918, scenario_synthesis=0.0851

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
SELECT agent_id, severity, count(*) FROM audit_findings WHERE run_id = '7dc2ab81-bc9a-40b1-a1a4-3ddf66a6e6fe' GROUP BY 1,2;

-- Per-question rollup
SELECT * FROM v_question_audit_summary WHERE id IN (SELECT question_id FROM audit_findings WHERE run_id = '7dc2ab81-bc9a-40b1-a1a4-3ddf66a6e6fe');
```

_Generated 2026-04-28T21:16:45.990277_