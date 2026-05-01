# OenoBench Quality Audit Report

- Run ID: `2335e3f6-4f71-4926-95ce-bd799fe71a51`
- Corpus tag: `audit_pilot_v14c`
- Corpus size: 24
- Config hash: `21ef944a17258e89...`
- Started: 2026-05-01 22:18:39.124464+00:00
- Completed: 2026-05-01 22:28:18.433630+00:00
- LLM calls: 192
- Cost: $0.33

## 1 · Executive summary

- Findings across 9 agents: 93 pass · 15 warn · 16 fail · 0 error

| Agent | pass | warn | fail | error | total |
|---|---:|---:|---:|---:|---:|
| A1_LexicalHygiene | 24 | 0 | 0 | 0 | 24 |
| A2_BiasStats | 1 | 0 | 0 | 0 | 1 |
| A3_FactEcho | 13 | 11 | 0 | 0 | 24 |
| A4_TemplateFingerprint | 1 | 0 | 0 | 0 | 1 |
| B1_TriJudgeAnswer | 24 | 0 | 0 | 0 | 24 |
| B2_ClosedBookSolvability | 5 | 3 | 16 | 0 | 24 |
| C2_CategoryLeak | 24 | 0 | 0 | 0 | 24 |
| D1_SelfPreference | 1 | 0 | 0 | 0 | 1 |
| D3_SkewAudit | 0 | 1 | 0 | 0 | 1 |

## 2 · Methodology

- Corpus: 24 questions tagged `audit_pilot_v14c`, seed 55.
- Agents: ['A1_LexicalHygiene', 'A2_BiasStats', 'A3_FactEcho', 'A4_TemplateFingerprint', 'B1_TriJudgeAnswer', 'B2_ClosedBookSolvability', 'C2_CategoryLeak', 'C4_DifficultyAudit', 'D1_SelfPreference', 'D3_SkewAudit']
- Judge models: ['claude', 'chatgpt', 'gemini']
- Thresholds and seeds encoded in config hash (full hash: `21ef944a17258e89bbaf262b2fe9ebe0bbfe697ef714681270431c5a3c7e667d`).

## 3 · Per-strategy deep dive

### template

- Question count: **24**
- Severity rollup: pass=90, warn=14, fail=16
- Failures by agent:
  - B2_ClosedBookSolvability: 16
- Sample failures:
  - WB-REG-0574-L1  ·  B2_ClosedBookSolvability  ·  
    > The fact assigns the Arroyo Seco AVA to which US state?
  - WB-REG-0575-L1  ·  B2_ClosedBookSolvability  ·  
    > A buyer is routing a shipment of South Coast AVA wine. Based on the fact, which US state is the origin?
  - WB-REG-0576-L1  ·  B2_ClosedBookSolvability  ·  
    > Given the fact, in which country would a traveller find the Südsteiermark wine region?

## 4 · Per-generator deep dive

### template_only

- Authored question count: **24**
- Total fails: 16, warns: 14

## 5 · Cross-cutting findings

### Template detectability (A4)
- Held-out AUC: **0.7**
- Top discriminative features: `len:avg_word` (-0.27), `bg:DET-WORD` (+0.22), `bg:SHORT-PUN` (-0.15), `bg:WORD-AUX` (+0.14), `bg:SHORT-WORD` (-0.11), `bg:WORD-PUN` (-0.10), `bg:WORD-DET` (+0.09), `bg:VERB?-PUN` (+0.09)

### Country / domain skew (D3)
- Max country over-representation ratio: **7.837**
- Question country counts (top 10): {'Chile': 3, 'France': 1, 'Austria': 1, 'Portugal': 2}
- Subdomain Herfindahl per strategy: template=0.1562

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
SELECT agent_id, severity, count(*) FROM audit_findings WHERE run_id = '2335e3f6-4f71-4926-95ce-bd799fe71a51' GROUP BY 1,2;

-- Per-question rollup
SELECT * FROM v_question_audit_summary WHERE id IN (SELECT question_id FROM audit_findings WHERE run_id = '2335e3f6-4f71-4926-95ce-bd799fe71a51');
```

_Generated 2026-05-01T22:28:19.350198_