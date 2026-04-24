# OenoBench Quality Audit Report

- Run ID: `4e3ead78-2b62-4733-919d-bf3f4878aaec`
- Corpus tag: `audit_pilot_v4`
- Corpus size: 341
- Config hash: `46b46c6cd37835f5...`
- Started: 2026-04-23 21:28:38.863657+00:00
- Completed: 2026-04-24 01:24:45.776806+00:00
- LLM calls: 3228
- Cost: $6.18

## 1 · Executive summary

- Findings across 9 agents: 1231 pass · 318 warn · 160 fail · 0 error

| Agent | pass | warn | fail | error | total |
|---|---:|---:|---:|---:|---:|
| A1_LexicalHygiene | 316 | 11 | 14 | 0 | 341 |
| A2_BiasStats | 0 | 1 | 0 | 0 | 1 |
| A3_FactEcho | 154 | 171 | 16 | 0 | 341 |
| A4_TemplateFingerprint | 1 | 0 | 0 | 0 | 1 |
| B1_TriJudgeAnswer | 326 | 13 | 2 | 0 | 341 |
| B2_ClosedBookSolvability | 102 | 115 | 124 | 0 | 341 |
| C2_CategoryLeak | 332 | 7 | 2 | 0 | 341 |
| D1_SelfPreference | 0 | 0 | 1 | 0 | 1 |
| D3_SkewAudit | 0 | 0 | 1 | 0 | 1 |

## 2 · Methodology

- Corpus: 341 questions tagged `audit_pilot_v4`, seed 42.
- Agents: ['A1_LexicalHygiene', 'A2_BiasStats', 'A3_FactEcho', 'A4_TemplateFingerprint', 'B1_TriJudgeAnswer', 'B2_ClosedBookSolvability', 'C2_CategoryLeak', 'C4_DifficultyAudit', 'D1_SelfPreference', 'D3_SkewAudit']
- Judge models: ['claude', 'chatgpt', 'gemini']
- Thresholds and seeds encoded in config hash (full hash: `46b46c6cd37835f5fb4554f64317887a2329f7b0da1176deb835d91876184489`).

## 3 · Per-strategy deep dive

### template

- Question count: **52**
- Severity rollup: pass=186, warn=44, fail=30
- Failures by agent:
  - B2_ClosedBookSolvability: 26
  - A3_FactEcho: 4
- Sample failures:
  - WB-REG-0186-L1  ·  B2_ClosedBookSolvability  ·  
    > The fact assigns the Madera AVA to which US state?
  - WB-REG-0187-L1  ·  B2_ClosedBookSolvability  ·  
    > The fact assigns the Rutherford AVA to which US state?
  - WB-REG-0189-L1  ·  B2_ClosedBookSolvability  ·  
    > Based on the fact, in which country is the Meursault wine region located?

### fact_to_question

- Question count: **120**
- Severity rollup: pass=443, warn=87, fail=70
- Failures by agent:
  - B2_ClosedBookSolvability: 61
  - A3_FactEcho: 6
  - A1_LexicalHygiene: 3
- Sample failures:
  - WB-PRD-0213-L2  ·  B2_ClosedBookSolvability  ·  
    > In which Médoc commune is the Bordeaux estate Château d'Angludet located?
  - WB-PRD-0215-L2  ·  B2_ClosedBookSolvability  ·  
    > An Adelaide Hills winery pioneered the cultivation of Grüner Veltliner in Australia by bringing in three clones from Austria in 2006, followed by an additional three clones or clon
  - WB-PRD-0216-L2  ·  B2_ClosedBookSolvability  ·  
    > A Salta producer established two vineyard sites at about 2,250 meters and 3,000 meters above sea level. Which winery fits those elevations?

### comparative

- Question count: **58**
- Severity rollup: pass=214, warn=58, fail=18
- Failures by agent:
  - B2_ClosedBookSolvability: 12
  - A1_LexicalHygiene: 2
  - A3_FactEcho: 2
  - C2_CategoryLeak: 1
  - B1_TriJudgeAnswer: 1
- Sample failures:
  - WB-REG-0216-L2  ·  B2_ClosedBookSolvability  ·  
    > Which grape variety is permitted for white wine production under the Chablis Grand Cru AOC?
  - WB-REG-0217-L2  ·  B2_ClosedBookSolvability  ·  
    > Which appellation has separate DOCG status and distinct production regulations from the larger DOCG that surrounds it?
  - WB-WMK-0200-L2  ·  B2_ClosedBookSolvability  ·  
    > Which of these grape varieties is used to produce a DOC wine with a minimum 85% varietal requirement?

### scenario_synthesis

- Question count: **86**
- Severity rollup: pass=294, warn=100, fail=36
- Failures by agent:
  - B2_ClosedBookSolvability: 25
  - A1_LexicalHygiene: 6
  - A3_FactEcho: 3
  - B1_TriJudgeAnswer: 1
  - C2_CategoryLeak: 1
- Sample failures:
  - WB-REG-0221-L2  ·  B2_ClosedBookSolvability  ·  
    > A winemaker in a well-known northeastern Hungarian appellation is planning the cellar lineup for the next release. The team wants to showcase the area's breadth while also introduc
  - WB-REG-0222-L2  ·  B2_ClosedBookSolvability  ·  
    > A Chilean winemaker is planning a new Pinot Noir program and wants to shortlist vineyard sources in areas where that grape is regularly made. Four internal proposals are on the tab
  - WB-REG-0224-L2  ·  B2_ClosedBookSolvability  ·  
    > A winemaker is planning a small Canadian release and wants the project to align with three internal benchmarks from past review data: it should use a grape that is regularly made i

### distractor_mining

- Question count: **25**
- Severity rollup: pass=93, warn=28, fail=4
- Failures by agent:
  - A1_LexicalHygiene: 3
  - A3_FactEcho: 1
- Sample failures:
  - WB-REG-0242-L3  ·  A1_LexicalHygiene  ·  matches=['question_text']
    > This specific geographical indication is positioned roughly sixty kilometers to the north of Christchurch. It is notable for containing the greatest proportion of vineyard planting
  - WB-GRP-0279-L3  ·  A1_LexicalHygiene  ·  matches=['question_text']
    > This grape variety is native to Spain and is authorized for use in certain designated wine regions of the country. While several Spanish geographical indications permit its inclusi
  - WB-GRP-0280-L3  ·  A1_LexicalHygiene  ·  matches=['question_text']
    > In the Burgundy region, a group of 44 appellations is defined by a naming convention that directly reflects the commune in which the vineyards are located. These designations are t

## 4 · Per-generator deep dive

### chatgpt

- Authored question count: **62**
- Total fails: 29, warns: 65

### claude

- Authored question count: **52**
- Total fails: 19, warns: 56

### gemini

- Authored question count: **49**
- Total fails: 13, warns: 29

### llama

- Authored question count: **60**
- Total fails: 26, warns: 58

### qwen

- Authored question count: **66**
- Total fails: 41, warns: 65

### template_only

- Authored question count: **52**
- Total fails: 30, warns: 44

## 5 · Cross-cutting findings

### Template detectability (A4)
- Held-out AUC: **0.7293**
- Top discriminative features: `len:tokens` (-3.44), `len:sentences` (+2.48), `len:avg_word` (+1.58), `punc::` (+0.92), `bg:WORD-PUN` (+0.38), `bg:DET-WORD` (+0.33), `bg:WORD-AUX` (+0.20), `punc:?` (-0.17)

### Country / domain skew (D3)
- Max country over-representation ratio: **6.368**
- Question country counts (top 10): {'Chile': 3, 'China': 1, 'Italy': 2, 'Spain': 6, 'Canada': 3, 'France': 2, 'Austria': 1, 'Germany': 6, 'Argentina': 3, 'Australia': 13}
- Subdomain Herfindahl per strategy: template=0.1021, comparative=0.2354, fact_to_question=0.0733, distractor_mining=0.0752, scenario_synthesis=0.056

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
SELECT agent_id, severity, count(*) FROM audit_findings WHERE run_id = '4e3ead78-2b62-4733-919d-bf3f4878aaec' GROUP BY 1,2;

-- Per-question rollup
SELECT * FROM v_question_audit_summary WHERE id IN (SELECT question_id FROM audit_findings WHERE run_id = '4e3ead78-2b62-4733-919d-bf3f4878aaec');
```

_Generated 2026-04-24T01:24:46.782117_