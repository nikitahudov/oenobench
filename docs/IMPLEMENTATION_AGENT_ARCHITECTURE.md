# Implementation Agent Architecture (Improvement Plan v2.1)

How to execute `docs/GENERATION_IMPROVEMENT_PLAN.md` faster and with higher quality by partitioning the work across **4 specialised agent teams** running in parallel git worktrees, plus a **coordinator team** that sequences merges and re-runs the audit.

Sequential effort: ~10 days. **Parallelised: ~3 days wall-clock.**

---

## Why agent teams (not one agent doing everything)?

Three reasons emerge from the v2 plan:

1. **The work has natural seams.** Generator-orchestration, sampler logic, template overhaul, and audit calibration touch four largely-disjoint code paths. There's no value in serializing them.
2. **Each defect class needs a different mindset.** The verifier needs prompt-engineering judgment; the per-country quota needs statistical thinking; the template overhaul needs UI-style copywriting + retrieval engineering; the audit calibration needs statistical bias correction. A single agent context-switching across all four loses fidelity on each.
3. **Independent worktrees keep changes isolated.** Bugs in one team's PR can't break other teams' work; merges are reviewable diffs, not entangled snowballs.

---

## Team structure

```
                                 ┌──────────────────────────────┐
                                 │   Team Omega — Coordinator   │
                                 │  (sequencing, audit re-run)  │
                                 └──────────────┬───────────────┘
                                                │
        ┌────────────────────┬─────────────────┼────────────────┬───────────────────┐
        ▼                    ▼                  ▼                ▼                   ▼
┌──────────────┐    ┌──────────────┐   ┌──────────────┐ ┌──────────────┐  ┌──────────────┐
│   Team α     │    │   Team β     │   │   Team γ     │ │   Team δ     │  │   Team ε     │
│  Generator   │    │   Sampler    │   │   Template   │ │     Audit    │  │  Test/QA     │
│  Allocation  │    │  & Quotas    │   │  Overhaul    │ │ Calibration  │  │  & Sign-off  │
│  + Verifier  │    │              │   │              │ │              │  │              │
└──────────────┘    └──────────────┘   └──────────────┘ └──────────────┘  └──────────────┘
   P0 fixes #0,1,2     P0 fix #3            P0 fixes #6a,b      P1 fixes #4,5,7        P1/P2 fixes
                       P2 fixes #9,10,11      P1/P2 fixes #6c,d,e                      + final regression
```

Each team operates in its own `EnterWorktree` instance. Teams α–δ run **concurrently**; team ε runs after them.

---

## Team α — Generator Quality (P0)

**Charter:** ensure no LLM ships a wrong-keyed question, and make the generator allocation reflect quality.

**Worktree:** `phase2e-team-alpha`

| Sub-agent | File(s) | Deliverable | Effort |
|---|---|---|---|
| α-1 Allocator | `src/generators/orchestrator.py` | Update `STRATEGY_TARGETS` and `GENERATOR_TARGETS` per §0 v2.1 (template 1,000; Claude/ChatGPT/Gemini 2,400; Qwen 1,100; Llama 700) | S |
| α-2 Verifier | new `src/generators/_verify.py` + edits to `src/generators/_schemas.py`, `fact_to_question.py`, `comparative_generator.py`, `scenario_generator.py`, `distractor_miner.py` | Independent-solver verification step that runs ONLY for `generator in {llama, qwen}`. Picks `claude` or `gemini` (rotated), re-solves question with source visible, rejects on key mismatch. Single retry, then drop. Add cost ledger to log file. | M |
| α-3 Paraphrase guard | `src/generators/_prompts.py` (PARAPHRASE RULE in 5 templates) + `src/generators/_schemas.py` (`_max_lcs_against_facts` + post-LLM rejector) | A3 fix #2 from the plan | S |

**Tests added:**
- `tests/generators/test_verifier.py` — fixture with a planted wrong-key Llama question; verify it gets rejected.
- `tests/generators/test_paraphrase.py` — fixture with verbatim-copy question; verify LCS rejector fires.
- `tests/generators/test_targets.py` — assert sums match 10,000 and no model exceeds 35%.

**Done when:** all tests green; 10-Q smoke run via `python -m src.generators.fact_to_question --generator llama --count 10` shows ≥1 verifier rejection logged and the rest accepted.

---

## Team β — Sampler & Quotas (P0 + P2)

**Charter:** stop oversampling already-overrepresented facts (countries, categories) and tighten distractor sampling everywhere.

**Worktree:** `phase2e-team-beta`

| Sub-agent | File(s) | Deliverable | Effort |
|---|---|---|---|
| β-1 Country quota | `src/generators/_fact_sampler.py` (new `_country_weights()` + integration into `sample_facts`, `sample_fact_pairs`, `sample_fact_clusters`, `sample_confusable_facts`) | D3 fix #3. Fact-base country distribution computed once at import; sampling weighted inversely to `(used_for_country / target_share)`; hard cap at 1.5× share | M |
| β-2 Universal C2 | `src/generators/_fact_sampler.py` | Make `_classify_wine_category` mandatory in ALL distractor candidate filtering, not just `distractor_miner` | S |
| β-3 A1 vague regex extension | `src/generators/_fact_sampler.py` (extend `_VAGUE_PATTERNS`) + post-LLM filter in `src/generators/_schemas.py` | A1 fix #9 — harvest the 8 vague phrasings from `data/reports/gold_sheet_scored.csv` notes column | S |
| β-4 A2 length normaliser (only if A2 still fails after shuffle) | `src/generators/_schemas.py` | A2 fix #11 — pad/trim distractor texts to within ±20% of correct option's length | S |

**Tests added:**
- `tests/generators/test_country_quota.py` — sample 1000 facts, assert no country exceeds 1.5× its base share.
- `tests/generators/test_category_filter.py` — fixture with red+sparkling+white candidate list; assert white-question sampler excludes red and sparkling.

**Done when:** new tests green; `python -m src.qa.orchestrator build-corpus --tag audit_smoke_v2 --per-strategy 5` with all strategies finishes and country distribution looks balanced.

---

## Team γ — Template Overhaul (P0 + P1 + P2)

**Charter:** salvage the template strategy at the reduced 10% allocation by fixing distractor quality, source-fact anchoring, difficulty rating, and phrasing diversity.

**Worktree:** `phase2e-team-gamma`

| Sub-agent | File(s) | Deliverable | Effort |
|---|---|---|---|
| γ-1 Embedding-similarity distractors | `src/generators/template_generator.py`, leverage existing pgvector index from `src/generators/_dedup.py` | Plan §6.3a — top-K nearest-entity sampling (skip closest, take 3 from positions 2-5) | M |
| γ-2 Source-fact anchoring | `src/generators/template_generator.py` (TEMPLATES catalogue), maybe new `src/generators/_template_catalogue.py` | Plan §6.3b — mark each template `requires_fact_specific=True/False`, drop world-knowledge-solvable templates, add 10 new fact-specific templates (region→soil, region→climate, grape→typical_aging, producer→flagship_wine, etc.) | M |
| γ-3 Per-instance difficulty heuristic | `src/generators/template_generator.py`, plus a one-time SQL query into the fact base | Plan §6.3c — entity-mention-count heuristic for difficulty | S |
| γ-4 Phrasing diversification | `src/generators/template_generator.py` (TEMPLATES list expanded to 4-6 variants per id) | Plan §6.3d — random rotation of opening verbs, word order, punctuation | M |
| γ-5 LLM paraphrase post-pass (P2, optional) | new `src/generators/_template_paraphrase.py` | Plan §6.3e — single Gemini call per question to rephrase naturally | M |

**Tests added:**
- `tests/generators/test_template_distractors.py` — plant a template with known similar/dissimilar candidates; assert the 3 picked distractors are in the expected similarity band.
- `tests/generators/test_template_anchoring.py` — assert templates marked `requires_fact_specific=True` skip facts without the relevant non-name entity.
- `tests/generators/test_template_phrasing.py` — generate 50 instances of a template; assert at least 3 distinct phrasings appear.

**Done when:** `python -m src.generators.template_generator --domain wine_regions --count 30 --test-run` shows: (a) plausible distractors, (b) source-anchored questions, (c) ≥3 distinct phrasings, (d) per-instance difficulty matches entity rarity.

---

## Team δ — Audit Calibration (P1)

**Charter:** make the next audit run trustworthy by patching the calibration drift the gold review surfaced.

**Worktree:** `phase2e-team-delta`

| Sub-agent | File(s) | Deliverable | Effort |
|---|---|---|---|
| δ-1 Multi-fact gold export | `src/qa/_corpus.py:export_gold_sheet` and `import_gold_sheet` | Plan §4 — show ALL linked facts in `source_facts` column (joined with `\n---\n` and `[1]/[2]` prefixes); update the import to handle the new column | S |
| δ-2 B2 judge re-calibration | `src/qa/_judges.py:JUDGE_PANEL` (add `llama`, `qwen` for B2 only — keep B1 panel as-is) + `src/qa/agents/team_b_validity.py` (adjust B2 leakage threshold from 0.8/0.67 to 0.9/0.8 for the recalibrated panel) + `src/qa/reports/build_improvement_plan.py` (gate threshold) | Plan §5b — closed-book panel uses test-taker-strength judges | S |
| δ-3 Difficulty re-classifier (promote C4) | `src/qa/agents/team_c_probes.py` — implement C4 stub | Plan §7 — single Gemini call per question, return rated 1-4; flag mismatch ≥1 level as warn, ≥2 as fail | M |
| δ-4 Report renderer updates | `src/qa/reports/build_audit_report.py` and `build_improvement_plan.py` | Render the new C4 findings; render per-rubric κ for ALL rubrics (not just answer_correct); add per-strategy + per-generator gold pass-rate tables when gold labels are present | S |

**Tests added:**
- `tests/qa/test_gold_multifact.py` — fixture multi-fact question; assert `source_facts` column contains all facts.
- `tests/qa/test_team_d_recalibration.py` — fixture with closed-book ratio 0.85; assert WARN under new thresholds (was FAIL under old).

**Done when:** `python -m src.qa.orchestrator export-gold --size 5` produces a CSV with the `source_facts` column populated; smoke run of C4 on the existing `audit_pilot_v1` corpus produces the expected count of difficulty-mismatch findings.

---

## Team ε — Test, Audit Re-run, Sign-off

**Charter:** prove the fixes work by running audit run #2 end-to-end and verifying all Go/No-Go gates.

**Sequencing:** depends on α, β, γ, δ all merged.

| Sub-agent | Action |
|---|---|
| ε-1 Test runner | `pytest tests/` after each merge; rollback any team that breaks the suite |
| ε-2 Smoke build | `python -m src.qa.orchestrator build-corpus --tag audit_smoke_v2 --per-strategy 10` to validate end-to-end pipeline |
| ε-3 Pilot rebuild | `build-corpus --tag audit_pilot_v2 --per-strategy 120 --seed 42` (~3h, ~$5) |
| ε-4 Audit run | `run --teams A,B,C,D --tag audit_pilot_v2` (~3-4h, ~$10) |
| ε-5 Gold re-export + re-import | re-export with multi-fact column; user re-grades 60 Qs; import; rebuild reports |
| ε-6 Sign-off | Verify every Go/No-Go gate in `docs/GENERATION_IMPROVEMENT_PLAN.md` passes; if all green, **unlock the full 10k generation run** |

---

## Team Omega — Coordinator

The single coordinator agent (could be the main session) handles:

- Spawning each team's worktree via `EnterWorktree`.
- Reviewing each team's PR diff before merge (security check, no destructive operations, no skipped hooks).
- Resolving cross-team conflicts (rare; the partition is designed to minimise file overlap).
- Sequencing the merges in dependency order: α + β + γ + δ in any order, then ε.
- Updating `CURRENT_STATUS.md`, `docs/PROCESS_LOG.md`, `CLAUDE.md` after each phase completes.
- Final sign-off: pushes the v2.1 plan as "executed" and starts audit run #2.

---

## Conflict-minimization design

To make parallel work safe, the file partition is designed so each team mostly owns disjoint files:

| File | Owner |
|---|---|
| `src/generators/orchestrator.py` (targets) | α |
| `src/generators/_verify.py` (new) | α |
| `src/generators/_prompts.py` | α |
| `src/generators/_schemas.py` | α (sole writer; β only reads) |
| `src/generators/_fact_sampler.py` | β (sole writer) |
| `src/generators/template_generator.py` | γ (sole writer) |
| `src/generators/_template_*.py` (new) | γ |
| `src/qa/_corpus.py` | δ |
| `src/qa/_judges.py`, `src/qa/agents/team_b_validity.py` | δ |
| `src/qa/agents/team_c_probes.py` | δ |
| `src/qa/reports/*.py` | δ |
| All `tests/**` | every team writes tests in its own subdir |
| Docs (`CURRENT_STATUS.md`, `PROCESS_LOG.md`, `CLAUDE.md`) | Omega only (post-merge) |

Only one cross-team touchpoint: α writes `_schemas.py`'s post-LLM rejector pipeline; γ's LLM paraphrase post-pass (γ-5, optional P2) interacts with the same pipeline. **Resolution:** γ-5 lands AFTER α merges, and γ-5 only adds — never modifies — α's rejector.

---

## Estimated wall-clock

| Stage | Wall-clock | Cost |
|---|---|---:|
| Teams α, β, γ, δ in parallel | ~2 days | $0 (code only) |
| Team ε smoke + pilot + audit | ~1 day | ~$15 |
| User re-grades 60-Q gold | parallel with ε | $0 |
| Sign-off + start full 10k | hours | ~$80 |
| **TOTAL** | **~3 days + 10k generation overnight** | **~$95** |

Compare to sequential single-agent: ~10 days + same overnight = ~13 days total.

---

## Risk register

| Risk | Mitigation |
|---|---|
| Team γ rewrites template_generator.py and breaks API for orchestrator | γ owns the file alone; orchestrator only calls public CLI (`--domain`, `--count`) which γ preserves |
| α's verifier doubles cost beyond budget | Budget ceiling: $80 for verifier-augmented Llama/Qwen 10k generation; alert if exceeded |
| Templates with §6.3b changes can't generate enough Qs to fill the 1,000 quota | Fallback: relax `requires_fact_specific=True` to allow up to 30% identity-based templates as filler, OR shrink template share further to 5-7% and absorb in LLMs |
| ε-4 audit fails Go/No-Go on a different defect we didn't fix | Iterate: add a v2.2 plan addendum, run a third audit. Budget: 2 audit cycles before NeurIPS deadline |
| User unavailable for second gold-grade pass | Use LLM-judge κ from first gold sheet as proxy gate for the LLM-judge-only signals; defer the human-spot-check gates |

---

## Why this is "Agent Teams" not just "branches"

Three things distinguish this architecture from "open 4 PRs in parallel":

1. **Each team is one specialised agent** (or coordinated sub-agents) with a focused scope, prompt, and toolset. Team γ knows about template phrasing and embedding similarity; team β knows about country-distribution stats. Specialisation reduces context-switch cost and improves judgment per task.
2. **The coordinator manages dependencies and sign-off** rather than each agent doing it ad-hoc. Reviewing a 4-team integration is a different skill than implementing one team's work.
3. **Findings flow back into the next team.** If α's verifier shows 80% Llama rejection (worse than expected), Omega can re-allocate Llama's quota DOWN before team ε runs the pilot, saving an audit cycle.

---

*This architecture is the recommended execution path for `docs/GENERATION_IMPROVEMENT_PLAN.md` v2.1. Coordinator should spin up the four worktrees and proceed when given the green light.*
