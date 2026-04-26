# OenoBench Quality Audit Report

- Run ID: `bfc39e1a-ba6b-471d-bde0-87eead62d1dc`
- Corpus tag: `audit_pilot_v6`
- Corpus size: 264
- Config hash: `bfc5aaae81f8027f...`
- Started: 2026-04-26 10:20:13.096194+00:00
- Completed: 2026-04-26 13:38:57.199333+00:00
- LLM calls: 2612
- Cost: $4.82

## 1 · Executive summary

- Findings across 9 agents: 963 pass · 296 warn · 211 fail · 0 error

| Agent | pass | warn | fail | error | total |
|---|---:|---:|---:|---:|---:|
| A1_LexicalHygiene | 245 | 15 | 4 | 0 | 264 |
| A2_BiasStats | 0 | 0 | 1 | 0 | 1 |
| A3_FactEcho | 120 | 136 | 8 | 0 | 264 |
| A4_TemplateFingerprint | 1 | 75 | 71 | 0 | 147 |
| B1_TriJudgeAnswer | 245 | 16 | 3 | 0 | 264 |
| B2_ClosedBookSolvability | 90 | 52 | 122 | 0 | 264 |
| C2_CategoryLeak | 262 | 2 | 0 | 0 | 264 |
| D1_SelfPreference | 0 | 0 | 1 | 0 | 1 |
| D3_SkewAudit | 0 | 0 | 1 | 0 | 1 |

## 2 · Methodology

- Corpus: 264 questions tagged `audit_pilot_v6`, seed 43.
- Agents: ['A1_LexicalHygiene', 'A2_BiasStats', 'A3_FactEcho', 'A4_TemplateFingerprint', 'B1_TriJudgeAnswer', 'B2_ClosedBookSolvability', 'C2_CategoryLeak', 'C4_DifficultyAudit', 'D1_SelfPreference', 'D3_SkewAudit']
- Judge models: ['claude', 'chatgpt', 'gemini']
- Thresholds and seeds encoded in config hash (full hash: `bfc5aaae81f8027ff6d64ff3fef540b77699de6982f845ab2829d0ba63df0fe7`).

## 3 · Per-strategy deep dive

### template

- Question count: **34**
- Severity rollup: pass=127, warn=19, fail=24
- Failures by agent:
  - B2_ClosedBookSolvability: 21
  - A3_FactEcho: 3
- Sample failures:
  - WB-REG-0332-L1  ·  B2_ClosedBookSolvability  ·  
    > An importer purchasing Goose Gap AVA wines is confirming the US state of origin for customs paperwork. Per the fact, which state should appear on the form?
  - WB-REG-0333-L2  ·  B2_ClosedBookSolvability  ·  
    > A retailer lists Texas Hill Country AVA wines on its website under state. Per the fact, which state should be used?
  - WB-REG-0334-L1  ·  B2_ClosedBookSolvability  ·  
    > A buyer is routing a shipment of Chiles Valley AVA wine. Based on the fact, which US state is the origin?

### fact_to_question

- Question count: **120**
- Severity rollup: pass=448, warn=123, fail=86
- Failures by agent:
  - B2_ClosedBookSolvability: 61
  - A4_TemplateFingerprint: 20
  - A1_LexicalHygiene: 3
  - A3_FactEcho: 2
- Sample failures:
  - WB-VIT-0304-L2  ·  A4_TemplateFingerprint  ·  
    > Which vineyard practice helps lower the need for insecticide treatments by interfering with grapevine moth reproduction?
  - WB-VIT-0300-L2  ·  A3_FactEcho  ·  lcs_ratio=0.5769
    > Which factor significantly influences the content, composition and development of organic acids and volatile compounds in wine, as well as its sensory attributes?
  - WB-VIT-0301-L2  ·  B2_ClosedBookSolvability  ·  
    > What type of viruses in grapevines may not show symptoms or cause disease under certain conditions?

### comparative

- Question count: **39**
- Severity rollup: pass=138, warn=55, fail=25
- Failures by agent:
  - B2_ClosedBookSolvability: 14
  - A4_TemplateFingerprint: 6
  - A3_FactEcho: 3
  - B1_TriJudgeAnswer: 1
  - A1_LexicalHygiene: 1
- Sample failures:
  - WB-GRP-0390-L3  ·  A4_TemplateFingerprint  ·  
    > When examining the authorized grape varieties for specific American Viticultural Areas, one region approves the Iberian white grape Albariño for wine production, while another auth
  - WB-GRP-0386-L3  ·  B1_TriJudgeAnswer  ·  majority_matches_key=False
    > Which of the following wine regions or estates allows the use of a grape variety that is not explicitly named as Tempranillo in its permitted varietals list?
  - WB-GRP-0387-L3  ·  B2_ClosedBookSolvability  ·  
    > Which grape variety is characterized as a dark-skinned type used in wine production and officially classified as a black variety in the Foundation Plant Services database at the Un

### scenario_synthesis

- Question count: **49**
- Severity rollup: pass=168, warn=62, fail=64
- Failures by agent:
  - A4_TemplateFingerprint: 41
  - B2_ClosedBookSolvability: 21
  - B1_TriJudgeAnswer: 2
- Sample failures:
  - WB-REG-0370-L2  ·  A4_TemplateFingerprint  ·  
    > A winery team is preparing a staff briefing about a dessert wine made from grapes left on the vine deep into winter. They want the briefing to accurately explain both the category’
  - WB-WMK-0288-L3  ·  A4_TemplateFingerprint  ·  
    > A German winery is finalizing production notes and legal labeling for a low-cost bubbly. The cellar team says their base wine could already have been sold during its initial fermen
  - WB-GRP-0411-L2  ·  A4_TemplateFingerprint  ·  
    > A cellar team is drafting training notes for new assistants after a difficult harvest. One parcel came in very ripe, with lots of natural sugar but not enough freshness, so the win

### distractor_mining

- Question count: **22**
- Severity rollup: pass=81, warn=37, fail=9
- Failures by agent:
  - B2_ClosedBookSolvability: 5
  - A4_TemplateFingerprint: 4
- Sample failures:
  - WB-PRD-0324-L3  ·  A4_TemplateFingerprint  ·  
    > Which winery is associated with a Vino de Pago designation established in 2019, representing a single-estate classification in Spain that emphasizes geographic specificity and regu
  - WB-REG-0383-L3  ·  A4_TemplateFingerprint  ·  
    > This South American wine region features vineyards that stretch across a dramatic longitudinal gradient, beginning at the coastal edge of the Pacific Ocean and extending eastward i
  - WB-REG-0387-L3  ·  B2_ClosedBookSolvability  ·  
    > Within the Bordeaux wine region, which AOC is dedicated exclusively to the production of sweet white wine?

## 4 · Per-generator deep dive

### chatgpt

- Authored question count: **38**
- Total fails: 31, warns: 41

### claude

- Authored question count: **48**
- Total fails: 40, warns: 54

### gemini

- Authored question count: **35**
- Total fails: 23, warns: 39

### llama

- Authored question count: **53**
- Total fails: 37, warns: 71

### qwen

- Authored question count: **56**
- Total fails: 53, warns: 72

### template_only

- Authored question count: **34**
- Total fails: 24, warns: 19

## 5 · Cross-cutting findings

### Template detectability (A4)
- Held-out AUC: **0.7933**
- Top discriminative features: `len:tokens` (+1.15), `bg:PUN-WORD` (-0.55), `len:sentences` (-0.53), `len:avg_word` (+0.53), `bg:SHORT-PUN` (-0.38), `bg:WORD-SHORT` (-0.25), `bg:PUN-DET` (-0.18), `bg:DET-WORD` (+0.18)

### Country / domain skew (D3)
- Max country over-representation ratio: **4.516**
- Question country counts (top 10): {'US': 2, 'Chile': 2, 'Italy': 1, 'Spain': 3, 'France': 4, 'Austria': 4, 'Hungary': 1, 'Portugal': 1, 'Australia': 3, 'New Zealand': 10}
- Subdomain Herfindahl per strategy: template=0.0969, comparative=0.3872, fact_to_question=0.066, distractor_mining=0.0785, scenario_synthesis=0.0812

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
SELECT agent_id, severity, count(*) FROM audit_findings WHERE run_id = 'bfc39e1a-ba6b-471d-bde0-87eead62d1dc' GROUP BY 1,2;

-- Per-question rollup
SELECT * FROM v_question_audit_summary WHERE id IN (SELECT question_id FROM audit_findings WHERE run_id = 'bfc39e1a-ba6b-471d-bde0-87eead62d1dc');
```

_Generated 2026-04-26T13:38:58.131998_