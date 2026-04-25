# OenoBench Quality Audit Report

- Run ID: `541d1d1d-1a89-4f5a-8940-218928da3729`
- Corpus tag: `audit_pilot_v5`
- Corpus size: 295
- Config hash: `46b46c6cd37835f5...`
- Started: 2026-04-25 00:39:50.803250+00:00
- Completed: 2026-04-25 04:14:35.305992+00:00
- LLM calls: 2860
- Cost: $5.50

## 1 · Executive summary

- Findings across 9 agents: 1070 pass · 285 warn · 234 fail · 0 error

| Agent | pass | warn | fail | error | total |
|---|---:|---:|---:|---:|---:|
| A1_LexicalHygiene | 273 | 12 | 10 | 0 | 295 |
| A2_BiasStats | 0 | 1 | 0 | 0 | 1 |
| A3_FactEcho | 149 | 135 | 11 | 0 | 295 |
| A4_TemplateFingerprint | 0 | 14 | 97 | 0 | 111 |
| B1_TriJudgeAnswer | 271 | 23 | 1 | 0 | 295 |
| B2_ClosedBookSolvability | 91 | 93 | 111 | 0 | 295 |
| C2_CategoryLeak | 285 | 7 | 3 | 0 | 295 |
| D1_SelfPreference | 1 | 0 | 0 | 0 | 1 |
| D3_SkewAudit | 0 | 0 | 1 | 0 | 1 |

## 2 · Methodology

- Corpus: 295 questions tagged `audit_pilot_v5`, seed 42.
- Agents: ['A1_LexicalHygiene', 'A2_BiasStats', 'A3_FactEcho', 'A4_TemplateFingerprint', 'B1_TriJudgeAnswer', 'B2_ClosedBookSolvability', 'C2_CategoryLeak', 'C4_DifficultyAudit', 'D1_SelfPreference', 'D3_SkewAudit']
- Judge models: ['claude', 'chatgpt', 'gemini']
- Thresholds and seeds encoded in config hash (full hash: `46b46c6cd37835f5fb4554f64317887a2329f7b0da1176deb835d91876184489`).

## 3 · Per-strategy deep dive

### template

- Question count: **34**
- Severity rollup: pass=115, warn=32, fail=23
- Failures by agent:
  - B2_ClosedBookSolvability: 20
  - A3_FactEcho: 3
- Sample failures:
  - WB-REG-0273-L1  ·  B2_ClosedBookSolvability  ·  
    > The fact assigns the Sierra Pelona AVA to which US state?
  - WB-REG-0274-L1  ·  B2_ClosedBookSolvability  ·  
    > A producer intends to release a varietal wine as Valtellina Superiore. Based on the fact, which grape variety is permitted for this release?
  - WB-REG-0275-L2  ·  B2_ClosedBookSolvability  ·  
    > A regulator is auditing labelling under Recioto di Gambellara. Which grape, per the fact, is among the permitted varieties for this appellation?

### fact_to_question

- Question count: **120**
- Severity rollup: pass=457, warn=72, fail=143
- Failures by agent:
  - B2_ClosedBookSolvability: 66
  - A4_TemplateFingerprint: 65
  - A1_LexicalHygiene: 7
  - A3_FactEcho: 5
- Sample failures:
  - WB-BIZ-0204-L2  ·  A1_LexicalHygiene  ·  matches=['question_text']
    > Which Italian wine region includes seven DOCG classifications, among them a renowned dried-grape red wine from the Valpolicella zone and a premium sparkling wine from a hilly subzo
  - WB-BIZ-0205-L2  ·  A4_TemplateFingerprint  ·  
    > An international regulatory body for viticulture and oenology was restructured in 2001, succeeding an earlier organization established in 1924. In which year was the predecessor or
  - WB-BIZ-0206-L2  ·  A4_TemplateFingerprint  ·  
    > Which Spanish wine region holds the highest regulatory classification under the country's appellation system, designated as a Qualified Designation of Origin?

### comparative

- Question count: **47**
- Severity rollup: pass=179, warn=51, fail=31
- Failures by agent:
  - A4_TemplateFingerprint: 23
  - B2_ClosedBookSolvability: 6
  - A3_FactEcho: 1
  - B1_TriJudgeAnswer: 1
- Sample failures:
  - WB-GRP-0311-L3  ·  A4_TemplateFingerprint  ·  
    > One of these regions allows Chambourcin, while the other authorizes Sauvignon Blanc. Which option correctly matches the region to its permitted grape?
  - WB-GRP-0312-L2  ·  A4_TemplateFingerprint  ·  
    > One of these AVAs allows Cabernet Franc, while the other allows Merlot. Which option matches those permitted grapes to the correct AVAs?
  - WB-GRP-0313-L3  ·  A3_FactEcho  ·  lcs_ratio=0.6
    > One of these AVAs allows Cabernet Franc, while the other allows Pinot noir. Which option matches them correctly?

### scenario_synthesis

- Question count: **69**
- Severity rollup: pass=227, warn=94, fail=26
- Failures by agent:
  - B2_ClosedBookSolvability: 19
  - C2_CategoryLeak: 3
  - A1_LexicalHygiene: 2
  - A4_TemplateFingerprint: 1
  - A3_FactEcho: 1
- Sample failures:
  - WB-REG-0311-L2  ·  B2_ClosedBookSolvability  ·  
    > A winemaker in Chile is redesigning an estate and reviewing why older local practices and market positioning developed the way they did. In archived notes, she finds three patterns
  - WB-REG-0312-L2  ·  B2_ClosedBookSolvability  ·  
    > A winemaker is evaluating whether a high-elevation Andean vineyard can remain productive after a major consolidation of plantings. The estate has removed a large share of its viney
  - WB-REG-0314-L2  ·  B2_ClosedBookSolvability  ·  
    > A winemaker is designing a heritage bottling and wants every production choice and label note to align with a traditional Georgian model. The wine is intended to be an amber style 

### distractor_mining

- Question count: **25**
- Severity rollup: pass=91, warn=35, fail=9
- Failures by agent:
  - A4_TemplateFingerprint: 7
  - A1_LexicalHygiene: 1
  - A3_FactEcho: 1
- Sample failures:
  - WB-BIZ-0231-L3  ·  A4_TemplateFingerprint  ·  
    > Which South African wine-related aspect was not legally protected for a long time?
  - WB-BIZ-0232-L4  ·  A4_TemplateFingerprint  ·  
    > Which organization is hosting a Spring Board of Directors Meeting in March 2026 at The Sutter Club?
  - WB-BIZ-0234-L3  ·  A4_TemplateFingerprint  ·  
    > Which regulatory framework integrated European geographical indication concepts but discarded the traditional focus on terroir, choosing instead to utilize trademark principles bas

## 4 · Per-generator deep dive

### chatgpt

- Authored question count: **52**
- Total fails: 44, warns: 44

### claude

- Authored question count: **50**
- Total fails: 38, warns: 49

### gemini

- Authored question count: **40**
- Total fails: 30, warns: 26

### llama

- Authored question count: **55**
- Total fails: 53, warns: 71

### qwen

- Authored question count: **64**
- Total fails: 44, warns: 62

### template_only

- Authored question count: **34**
- Total fails: 23, warns: 32

## 5 · Cross-cutting findings

### Template detectability (A4)
- Held-out AUC: **0.9542**
- Top discriminative features: `len:sentences` (+2.95), `len:avg_word` (+2.47), `len:tokens` (-0.61), `punc:-` (+0.61), `bg:DET-WORD` (+0.39), `punc::` (+0.34), `punc:,` (+0.31), `bg:WORD-PUN` (+0.27)

### Country / domain skew (D3)
- Max country over-representation ratio: **3.696**
- Question country counts (top 10): {'US': 1, 'Italy': 2, 'Spain': 4, 'France': 2, 'Austria': 2, 'England': 2, 'Germany': 1, 'Uruguay': 1, 'Argentina': 1, 'Australia': 17}
- Subdomain Herfindahl per strategy: template=0.1107, comparative=0.3255, fact_to_question=0.0882, distractor_mining=0.0976, scenario_synthesis=0.0754

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
SELECT agent_id, severity, count(*) FROM audit_findings WHERE run_id = '541d1d1d-1a89-4f5a-8940-218928da3729' GROUP BY 1,2;

-- Per-question rollup
SELECT * FROM v_question_audit_summary WHERE id IN (SELECT question_id FROM audit_findings WHERE run_id = '541d1d1d-1a89-4f5a-8940-218928da3729');
```

_Generated 2026-04-25T04:14:36.495705_