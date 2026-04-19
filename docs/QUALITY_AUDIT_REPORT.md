# OenoBench Quality Audit Report

- Run ID: `e8eba8bb-cb49-42cd-9e32-c741c987043e`
- Corpus tag: `audit_pilot_v1`
- Corpus size: 472
- Config hash: `a4b016003b3be5b6...`
- Started: 2026-04-19 01:28:16.558664+00:00
- Completed: 2026-04-19 04:57:41.290580+00:00
- LLM calls: 3207
- Cost: $8.49

## 1 · Executive summary

- Findings across 9 agents: 1606 pass · 423 warn · 367 fail · 0 error

| Agent | pass | warn | fail | error | total |
|---|---:|---:|---:|---:|---:|
| A1_LexicalHygiene | 446 | 13 | 13 | 0 | 472 |
| A2_BiasStats | 0 | 0 | 1 | 0 | 1 |
| A3_FactEcho | 127 | 181 | 164 | 0 | 472 |
| A4_TemplateFingerprint | 0 | 12 | 21 | 0 | 33 |
| B1_TriJudgeAnswer | 393 | 57 | 22 | 0 | 472 |
| B2_ClosedBookSolvability | 182 | 150 | 140 | 0 | 472 |
| C2_CategoryLeak | 458 | 9 | 5 | 0 | 472 |
| D1_SelfPreference | 0 | 1 | 0 | 0 | 1 |
| D3_SkewAudit | 0 | 0 | 1 | 0 | 1 |

## 2 · Methodology

- Corpus: 472 questions tagged `audit_pilot_v1`, seed 42.
- Agents: ['A1_LexicalHygiene', 'A2_BiasStats', 'A3_FactEcho', 'A4_TemplateFingerprint', 'B1_TriJudgeAnswer', 'B2_ClosedBookSolvability', 'C2_CategoryLeak', 'D1_SelfPreference', 'D3_SkewAudit']
- Judge models: ['claude', 'chatgpt', 'gemini']
- Thresholds and seeds encoded in config hash (full hash: `a4b016003b3be5b6dcfab738ed31c5ab8399e1188835095ff12d928a60fb90f8`).

## 3 · Per-strategy deep dive

### template

- Question count: **49**
- Severity rollup: pass=170, warn=33, fail=42
- Failures by agent:
  - B2_ClosedBookSolvability: 29
  - A1_LexicalHygiene: 5
  - A3_FactEcho: 5
  - B1_TriJudgeAnswer: 3
- Sample failures:
  - WB-REG-0017-L2  ·  B2_ClosedBookSolvability  ·  
    > In which sub-region or parent region is Valpolicella located?
  - WB-GRP-0006-L2  ·  A1_LexicalHygiene  ·  matches=['question_text']
    > Which wine region is best known for growing | varietals =?
  - WB-GRP-0007-L1  ·  A1_LexicalHygiene  ·  matches=['question_text']
    > Which wine region is best known for growing Castelão (Periquita)?

### fact_to_question

- Question count: **120**
- Severity rollup: pass=433, warn=64, fail=129
- Failures by agent:
  - B2_ClosedBookSolvability: 69
  - A3_FactEcho: 42
  - A4_TemplateFingerprint: 17
  - B1_TriJudgeAnswer: 1
- Sample failures:
  - WB-REG-0040-L2  ·  A4_TemplateFingerprint  ·  
    > In which Italian province is the Soave DOC located?
  - WB-PRD-0031-L2  ·  A3_FactEcho  ·  lcs_ratio=0.6364
    > Until the 1930s, approximately how many wineries were there in the Province mentioned in South American wine history?
  - WB-BIZ-0011-L2  ·  B2_ClosedBookSolvability  ·  
    > As of 2012, what was the average annual production volume of the Israeli wine industry?

### comparative

- Question count: **85**
- Severity rollup: pass=301, warn=69, fail=55
- Failures by agent:
  - A3_FactEcho: 26
  - B2_ClosedBookSolvability: 20
  - B1_TriJudgeAnswer: 4
  - C2_CategoryLeak: 3
  - A1_LexicalHygiene: 2
- Sample failures:
  - WB-GRP-0036-L3  ·  A3_FactEcho  ·  lcs_ratio=0.75
    > A grower is deciding between planting Mourvedre in Contra Costa AVA or Cabernet Franc in Ohio River Valley AVA. Which plan matches the permitted grape variety for each AVA?
  - WB-WMK-0026-L2  ·  C2_CategoryLeak  ·  leaked_categories=1
    > A white wine is labeled as Soave DOC. Based on the grape composition rules, which grape variety is most likely the majority of the blend?
  - WB-BIZ-0027-L2  ·  A1_LexicalHygiene  ·  matches=['question_text']
    > A wine producer in northern Italy wants to release a new sparkling wine under a prestigious Italian classification that requires adherence to strict DOCG regulations. Meanwhile, a 

### scenario_synthesis

- Question count: **119**
- Severity rollup: pass=366, warn=146, fail=83
- Failures by agent:
  - A3_FactEcho: 44
  - B2_ClosedBookSolvability: 22
  - B1_TriJudgeAnswer: 11
  - A1_LexicalHygiene: 4
  - C2_CategoryLeak: 2
- Sample failures:
  - WB-REG-0053-L2  ·  A3_FactEcho  ·  lcs_ratio=0.7273
    > A consulting winemaker oversees three estates in France: one producing Syrah on the steep schist slopes of Côte-Rôtie, one producing Chenin Blanc in Vouvray, and one producing a Sé
  - WB-REG-0055-L2  ·  B2_ClosedBookSolvability  ·  
    > A Chilean wine importer is building a portfolio focused exclusively on a single grape variety that has become the country's flagship red. She wants to showcase regional diversity b
  - WB-BIZ-0045-L4  ·  A3_FactEcho  ·  lcs_ratio=0.9167
    > A German winemaker is finalizing the cellar schedule for their recently harvested 2023 vintage. They intend to submit the wine for official classification under the national regula

### distractor_mining

- Question count: **99**
- Severity rollup: pass=336, warn=110, fail=55
- Failures by agent:
  - A3_FactEcho: 47
  - A4_TemplateFingerprint: 3
  - B1_TriJudgeAnswer: 3
  - A1_LexicalHygiene: 2
- Sample failures:
  - WB-GRP-0075-L4  ·  A3_FactEcho  ·  lcs_ratio=0.6538
    > A Canadian wine region's industry, from its early commercial era through the mid-1970s, was built entirely on the production of fruit wines and wines made from hybrid grape varieti
  - WB-GRP-0077-L4  ·  A3_FactEcho  ·  lcs_ratio=0.625
    > Identify the German wine grape described: a white variety developed as a crossing between Silvaner and Chasselas.
  - WB-PRD-0070-L3  ·  A3_FactEcho  ·  lcs_ratio=0.7143
    > Which winery is described by these clues: it is a Canadian wine producer, and it is specifically located in Lake Country rather than Kelowna, the Regional District of Okanagan-Simi

## 4 · Per-generator deep dive

### chatgpt

- Authored question count: **84**
- Total fails: 74, warns: 78

### claude

- Authored question count: **81**
- Total fails: 67, warns: 62

### gemini

- Authored question count: **76**
- Total fails: 52, warns: 67

### llama

- Authored question count: **94**
- Total fails: 66, warns: 92

### qwen

- Authored question count: **88**
- Total fails: 63, warns: 90

### template_only

- Authored question count: **49**
- Total fails: 42, warns: 33

## 5 · Cross-cutting findings

### Template detectability (A4)
- Held-out AUC: **0.9588**
- Top discriminative features: `len:avg_word` (+1.25), `punc::` (+0.68), `punc:-` (+0.67), `len:sentences` (+0.61), `len:tokens` (-0.45), `punc:,` (-0.37), `bg:WORD-AUX` (+0.18), `bg:WORD-VERB?` (+0.13)

### Country / domain skew (D3)
- Max country over-representation ratio: **4.455**
- Question country counts (top 10): {'US': 10, 'Chile': 13, 'China': 1, 'Italy': 3, 'Spain': 7, 'Canada': 2, 'France': 8, 'Greece': 6, 'Israel': 6, 'Austria': 10}
- Subdomain Herfindahl per strategy: template=0.0912, comparative=0.2709, fact_to_question=0.0818, distractor_mining=0.043, scenario_synthesis=0.0286

## 6 · Gold calibration

- Human-reviewed items: **60**
- answer_correct κ(human, judge majority) = **-0.053**  (n=60)
- ⚠ κ below 0.6 — downweight B1 signal when interpreting strategy rollups.

## 7 · Limitations & deferred checks

This MVA run excludes the following agents — failures in their weakness
classes cannot be disproved by this report alone.

- **C1 DistractorDifficulty** — per-distractor LLM plausibility scoring.
- **B3 ParaphraseStability** — stem-rewrite consistency.
- **B4 Ambiguity** — multi-defensible option scoring.
- **C3 SourceSwap** — robustness to fact substitution.
- **C4 DimensionCognitiveAudit** — LLM check on dimension/Bloom's/difficulty labels.
- **D2 DedupCalibration** — similarity-threshold P/R sweep.
- **D3-cultural** — LLM cultural-framing labelling (pure stats only ran).

Escalation triggers (if the audit finds these, run the deferred agents):
- A4 AUC ≥ 0.9 → run C1 + B4 on flagged subset.
- B1 fail rate ≥ 10% → run B3 + C3 to triangulate.
- D1 fail on any model → add more evaluator runs, include Llama/Qwen as secondary judges.

## 8 · Appendix — raw queries

```sql
-- All findings for this run
SELECT agent_id, severity, count(*) FROM audit_findings WHERE run_id = 'e8eba8bb-cb49-42cd-9e32-c741c987043e' GROUP BY 1,2;

-- Per-question rollup
SELECT * FROM v_question_audit_summary WHERE id IN (SELECT question_id FROM audit_findings WHERE run_id = 'e8eba8bb-cb49-42cd-9e32-c741c987043e');
```

_Generated 2026-04-19T10:33:54.141735_