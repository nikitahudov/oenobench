# OenoBench Quality Audit Report

- Run ID: `9db7c95a-0154-4340-9265-37795694d78a`
- Corpus tag: `audit_pilot_v14b`
- Corpus size: 19
- Config hash: `21ef944a17258e89...`
- Started: 2026-05-01 21:26:39.734471+00:00
- Completed: 2026-05-01 21:33:56.670113+00:00
- LLM calls: 152
- Cost: $0.26

## 1 · Executive summary

- Findings across 9 agents: 72 pass · 17 warn · 10 fail · 0 error

| Agent | pass | warn | fail | error | total |
|---|---:|---:|---:|---:|---:|
| A1_LexicalHygiene | 19 | 0 | 0 | 0 | 19 |
| A2_BiasStats | 1 | 0 | 0 | 0 | 1 |
| A3_FactEcho | 8 | 11 | 0 | 0 | 19 |
| A4_TemplateFingerprint | 1 | 0 | 0 | 0 | 1 |
| B1_TriJudgeAnswer | 18 | 1 | 0 | 0 | 19 |
| B2_ClosedBookSolvability | 5 | 4 | 10 | 0 | 19 |
| C2_CategoryLeak | 19 | 0 | 0 | 0 | 19 |
| D1_SelfPreference | 1 | 0 | 0 | 0 | 1 |
| D3_SkewAudit | 0 | 1 | 0 | 0 | 1 |

## 2 · Methodology

- Corpus: 19 questions tagged `audit_pilot_v14b`, seed 55.
- Agents: ['A1_LexicalHygiene', 'A2_BiasStats', 'A3_FactEcho', 'A4_TemplateFingerprint', 'B1_TriJudgeAnswer', 'B2_ClosedBookSolvability', 'C2_CategoryLeak', 'C4_DifficultyAudit', 'D1_SelfPreference', 'D3_SkewAudit']
- Judge models: ['claude', 'chatgpt', 'gemini']
- Thresholds and seeds encoded in config hash (full hash: `21ef944a17258e89bbaf262b2fe9ebe0bbfe697ef714681270431c5a3c7e667d`).

## 3 · Per-strategy deep dive

### template

- Question count: **19**
- Severity rollup: pass=69, warn=16, fail=10
- Failures by agent:
  - B2_ClosedBookSolvability: 10
- Sample failures:
  - WB-REG-0567-L1  ·  B2_ClosedBookSolvability  ·  
    > According to the fact, in which US state is the The Burn of Columbia Valley AVA located?
  - WB-REG-0568-L1  ·  B2_ClosedBookSolvability  ·  
    > An importer purchasing The Burn of Columbia Valley AVA wines is confirming the US state of origin for customs paperwork. Per the fact, which state should appear on the form?
  - WB-REG-0569-L3  ·  B2_ClosedBookSolvability  ·  
    > Which region of origin is Rosazzo part of?

## 4 · Per-generator deep dive

### template_only

- Authored question count: **19**
- Total fails: 10, warns: 16

## 5 · Cross-cutting findings

### Template detectability (A4)
- Held-out AUC: **None**

### Country / domain skew (D3)
- Max country over-representation ratio: **42.45**
- Question country counts (top 10): {'US': 3, 'Italy': 1, 'Canada': 2, 'France': 1}
- Subdomain Herfindahl per strategy: template=0.1191

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
SELECT agent_id, severity, count(*) FROM audit_findings WHERE run_id = '9db7c95a-0154-4340-9265-37795694d78a' GROUP BY 1,2;

-- Per-question rollup
SELECT * FROM v_question_audit_summary WHERE id IN (SELECT question_id FROM audit_findings WHERE run_id = '9db7c95a-0154-4340-9265-37795694d78a');
```

_Generated 2026-05-01T21:33:57.608703_