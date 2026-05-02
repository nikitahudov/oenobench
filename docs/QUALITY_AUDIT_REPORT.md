# OenoBench Quality Audit Report

- Run ID: `9b299fd5-df36-4fe1-a8db-9b998129139d`
- Corpus tag: `audit_pilot_v16`
- Corpus size: 27
- Config hash: `5b18431708c8bd36...`
- Started: 2026-05-02 11:58:10.942884+00:00
- Completed: 2026-05-02 12:15:01.050527+00:00
- LLM calls: 294
- Cost: $0.48

## 1 · Executive summary

- Findings across 9 agents: 105 pass · 21 warn · 13 fail · 0 error

| Agent | pass | warn | fail | error | total |
|---|---:|---:|---:|---:|---:|
| A1_LexicalHygiene | 27 | 0 | 0 | 0 | 27 |
| A2_BiasStats | 0 | 1 | 0 | 0 | 1 |
| A3_FactEcho | 12 | 12 | 3 | 0 | 27 |
| A4_TemplateFingerprint | 0 | 1 | 0 | 0 | 1 |
| B1_TriJudgeAnswer | 27 | 0 | 0 | 0 | 27 |
| B2_ClosedBookSolvability | 12 | 6 | 9 | 0 | 27 |
| C2_CategoryLeak | 27 | 0 | 0 | 0 | 27 |
| D1_SelfPreference | 0 | 0 | 1 | 0 | 1 |
| D3_SkewAudit | 0 | 1 | 0 | 0 | 1 |

## 2 · Methodology

- Corpus: 27 questions tagged `audit_pilot_v16`, seed 60.
- Agents: ['A1_LexicalHygiene', 'A2_BiasStats', 'A3_FactEcho', 'A4_TemplateFingerprint', 'B1_TriJudgeAnswer', 'B2_ClosedBookSolvability', 'C2_CategoryLeak', 'C4_DifficultyAudit', 'D1_SelfPreference', 'D3_SkewAudit']
- Judge models: ['claude', 'chatgpt', 'gemini']
- Thresholds and seeds encoded in config hash (full hash: `5b18431708c8bd369d6b338ad4ac18de9a2fbc476906dff98a16d86e154315b0`).

## 3 · Per-strategy deep dive

### template

- Question count: **6**
- Severity rollup: pass=21, warn=2, fail=7
- Failures by agent:
  - B2_ClosedBookSolvability: 4
  - A3_FactEcho: 3
- Sample failures:
  - WB-REG-0596-L2  ·  B2_ClosedBookSolvability  ·  
    > A retailer lists Fredericksburg in the Texas Hill Country AVA wines on its website under state. Per the fact, which state should be used?
  - WB-REG-0595-L2  ·  A3_FactEcho  ·  lcs_ratio=0.7143
    > Based on the source fact, the Fredericksburg in the Texas Hill Country AVA is found in which state?
  - WB-GRP-0731-L3  ·  A3_FactEcho  ·  lcs_ratio=0.6154
    > If a wine merchant wants to source genuine Grenache-based wines, which of the following regions would be the best choice?

### fact_to_question

- Question count: **14**
- Severity rollup: pass=57, warn=10, fail=3
- Failures by agent:
  - B2_ClosedBookSolvability: 3
- Sample failures:
  - WB-REG-0598-L2  ·  B2_ClosedBookSolvability  ·  
    > In which country is the Elqui Valley wine region located?
  - WB-GRP-0730-L2  ·  B2_ClosedBookSolvability  ·  
    > In Australian wine history, which grape variety was historically mislabeled and sold under the name 'Hunter River Riesling' before the misnomer was corrected?
  - WB-VIT-0494-L2  ·  B2_ClosedBookSolvability  ·  
    > Located in the province of Verona just east of Lake Garda, which Italian viticultural zone's name appears in the local Venetian dialect as 'Valpołexeła'?

### scenario_synthesis

- Question count: **4**
- Severity rollup: pass=18, warn=1, fail=1
- Failures by agent:
  - B2_ClosedBookSolvability: 1
- Sample failures:
  - WB-GRP-0735-L2  ·  B2_ClosedBookSolvability  ·  
    > A winemaker in a warm New World region is working with a red grape variety known for its low phenolic concentration, which historically was vinified into sweet, pale-colored wines 

### distractor_mining

- Question count: **3**
- Severity rollup: pass=9, warn=5, fail=1
- Failures by agent:
  - B2_ClosedBookSolvability: 1
- Sample failures:
  - WB-REG-0601-L3  ·  B2_ClosedBookSolvability  ·  
    > Which New York AVA was established in 1988?

## 4 · Per-generator deep dive

### chatgpt

- Authored question count: **7**
- Total fails: 0, warns: 4

### claude

- Authored question count: **4**
- Total fails: 2, warns: 4

### gemini

- Authored question count: **2**
- Total fails: 0, warns: 1

### llama

- Authored question count: **6**
- Total fails: 2, warns: 6

### qwen

- Authored question count: **2**
- Total fails: 1, warns: 1

### template_only

- Authored question count: **6**
- Total fails: 7, warns: 2

## 5 · Cross-cutting findings

### Template detectability (A4)
- Held-out AUC: **0.88**
- Top discriminative features: `len:tokens` (+0.88), `len:sentences` (-0.46), `bg:PUN-WORD` (-0.41), `bg:SHORT-PUN` (-0.38), `bg:WORD-WORD` (+0.22), `bg:NUM-PUN` (+0.18), `bg:WORD-PUN` (-0.17), `bg:DET-PUN` (-0.13)

### Country / domain skew (D3)
- Max country over-representation ratio: **129.196**
- Question country counts (top 10): {'England': 1, 'Germany': 1, 'Bulgaria': 1}
- Subdomain Herfindahl per strategy: template=0.3333, fact_to_question=0.1735, distractor_mining=0.3333, scenario_synthesis=0.25

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
SELECT agent_id, severity, count(*) FROM audit_findings WHERE run_id = '9b299fd5-df36-4fe1-a8db-9b998129139d' GROUP BY 1,2;

-- Per-question rollup
SELECT * FROM v_question_audit_summary WHERE id IN (SELECT question_id FROM audit_findings WHERE run_id = '9b299fd5-df36-4fe1-a8db-9b998129139d');
```

_Generated 2026-05-02T12:15:02.659061_