# OenoBench Quality Audit Report

- Run ID: `3c6e27ce-62fa-4c1b-bd0e-3958161a0082`
- Corpus tag: `audit_pilot_v2`
- Corpus size: 292
- Config hash: `fc36aabf4a583a73...`
- Started: 2026-04-19 17:43:13.081504+00:00
- Completed: 2026-04-19 20:42:09.730484+00:00
- LLM calls: 3003
- Cost: $7.64

## 1 · Executive summary

- Findings across 10 agents: 1124 pass · 371 warn · 275 fail · 3 error

| Agent | pass | warn | fail | error | total |
|---|---:|---:|---:|---:|---:|
| A1_LexicalHygiene | 266 | 12 | 14 | 0 | 292 |
| A2_BiasStats | 0 | 0 | 1 | 0 | 1 |
| A3_FactEcho | 143 | 132 | 17 | 0 | 292 |
| A4_TemplateFingerprint | 0 | 3 | 15 | 0 | 18 |
| B1_TriJudgeAnswer | 252 | 32 | 8 | 0 | 292 |
| B2_ClosedBookSolvability | 91 | 90 | 111 | 0 | 292 |
| C2_CategoryLeak | 288 | 1 | 3 | 0 | 292 |
| C4_DifficultyAudit | 83 | 101 | 105 | 3 | 292 |
| D1_SelfPreference | 1 | 0 | 0 | 0 | 1 |
| D3_SkewAudit | 0 | 0 | 1 | 0 | 1 |

## 2 · Methodology

- Corpus: 292 questions tagged `audit_pilot_v2`, seed 42.
- Agents: ['A1_LexicalHygiene', 'A2_BiasStats', 'A3_FactEcho', 'A4_TemplateFingerprint', 'B1_TriJudgeAnswer', 'B2_ClosedBookSolvability', 'C2_CategoryLeak', 'C4_DifficultyAudit', 'D1_SelfPreference', 'D3_SkewAudit']
- Judge models: ['claude', 'chatgpt', 'gemini']
- Thresholds and seeds encoded in config hash (full hash: `fc36aabf4a583a739530429419db89c06d3ca0604be913da796dddca8c3679df`).

## 3 · Per-strategy deep dive

### template

- Question count: **43**
- Severity rollup: pass=151, warn=58, fail=49
- Failures by agent:
  - B2_ClosedBookSolvability: 18
  - C4_DifficultyAudit: 16
  - A3_FactEcho: 11
  - B1_TriJudgeAnswer: 2
  - A1_LexicalHygiene: 2
- Sample failures:
  - WB-REG-0091-L1  ·  B2_ClosedBookSolvability  ·  
    > Which country is the Leelanau Peninsula wine region located in?
  - WB-REG-0092-L1  ·  B2_ClosedBookSolvability  ·  
    > Which country is the Awatere Valley wine region located in?
  - WB-REG-0093-L1  ·  B2_ClosedBookSolvability  ·  
    > Identify the country where the Fiano di Avellino wine region is located.

### fact_to_question

- Question count: **120**
- Severity rollup: pass=489, warn=109, fail=137
- Failures by agent:
  - B2_ClosedBookSolvability: 61
  - C4_DifficultyAudit: 55
  - A4_TemplateFingerprint: 14
  - A1_LexicalHygiene: 4
  - A3_FactEcho: 2
  - B1_TriJudgeAnswer: 1
- Sample failures:
  - WB-VIT-0079-L2  ·  B2_ClosedBookSolvability  ·  
    > Which of the following practices is NOT mentioned as a way to increase soil organic carbon in vineyards?
  - WB-VIT-0080-L2  ·  C4_DifficultyAudit  ·  
    > During the ripening process, what happens to the K/Na ratio in the pericarp of Flame Seedless grapes?
  - WB-GRP-0105-L2  ·  C4_DifficultyAudit  ·  
    > In a specific sample of 72 professional assessments, what mean score was achieved by Spätburgunder bottlings?

### comparative

- Question count: **78**
- Severity rollup: pass=306, warn=110, fail=53
- Failures by agent:
  - B2_ClosedBookSolvability: 23
  - C4_DifficultyAudit: 20
  - A1_LexicalHygiene: 4
  - A3_FactEcho: 3
  - B1_TriJudgeAnswer: 3
- Sample failures:
  - WB-BIZ-0111-L2  ·  B2_ClosedBookSolvability  ·  
    > A wine labeled as DOCG Frascati Superiore most likely originates from which Italian wine region?
  - WB-GRP-0121-L2  ·  C4_DifficultyAudit  ·  
    > A compliance officer is checking two proposed single-varietal labels. One wine is made from a grape authorized in Lenswood, while the other uses a grape allowed in Mount Gambier. W
  - WB-GRP-0122-L2  ·  A3_FactEcho  ·  lcs_ratio=0.6
    > A grower is choosing between two AVAs for a single-varietal planting. One site must allow Pinot noir, while the other must allow Barbera. Which pairing matches those planting goals

### scenario_synthesis

- Question count: **51**
- Severity rollup: pass=177, warn=94, fail=33
- Failures by agent:
  - C4_DifficultyAudit: 14
  - B2_ClosedBookSolvability: 9
  - A1_LexicalHygiene: 4
  - C2_CategoryLeak: 3
  - B1_TriJudgeAnswer: 2
  - A3_FactEcho: 1
- Sample failures:
  - WB-REG-0123-L4  ·  C2_CategoryLeak  ·  leaked_categories=2
    > A Champagne producer is reviewing notes from an early-1800s cellar trial. The team wants to launch a pink sparkling cuvée by blending red and white base wines, but their current cl
  - WB-REG-0125-L2  ·  B2_ClosedBookSolvability  ·  
    > A Georgian producer is finalizing the launch plan for a skin-contact amber wine. In a tasting trial, the sample shows a deep amber hue with a full, well-knit palate and an obvious 
  - WB-REG-0126-L3  ·  C4_DifficultyAudit  ·  
    > A Croatian producer is preparing a new cellar project and wants the proposal to highlight three points in one concise opening paragraph: the country's very long history of formal v

## 4 · Per-generator deep dive

### chatgpt

- Authored question count: **49**
- Total fails: 49, warns: 59

### claude

- Authored question count: **48**
- Total fails: 40, warns: 55

### gemini

- Authored question count: **43**
- Total fails: 34, warns: 42

### llama

- Authored question count: **54**
- Total fails: 52, warns: 82

### qwen

- Authored question count: **55**
- Total fails: 48, warns: 75

### template_only

- Authored question count: **43**
- Total fails: 49, warns: 58

## 5 · Cross-cutting findings

### Template detectability (A4)
- Held-out AUC: **0.9615**
- Top discriminative features: `len:avg_word` (+2.89), `punc:?` (-2.31), `punc::` (+1.61), `len:sentences` (+1.45), `punc:,` (-1.30), `punc:-` (+1.28), `len:tokens` (-0.97), `bg:WORD-PUN` (+0.33)

### Country / domain skew (D3)
- Max country over-representation ratio: **3.377**
- Question country counts (top 10): {'US': 4, 'Chile': 12, 'Italy': 2, 'Canada': 2, 'France': 6, 'Austria': 3, 'Argentina': 5, 'Australia': 13, 'New Zealand': 15, 'South Africa': 26}
- Subdomain Herfindahl per strategy: template=0.0871, comparative=0.2344, fact_to_question=0.0785, scenario_synthesis=0.0511

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
SELECT agent_id, severity, count(*) FROM audit_findings WHERE run_id = '3c6e27ce-62fa-4c1b-bd0e-3958161a0082' GROUP BY 1,2;

-- Per-question rollup
SELECT * FROM v_question_audit_summary WHERE id IN (SELECT question_id FROM audit_findings WHERE run_id = '3c6e27ce-62fa-4c1b-bd0e-3958161a0082');
```

_Generated 2026-04-19T20:42:10.781523_