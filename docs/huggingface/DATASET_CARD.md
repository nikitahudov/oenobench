---
license: cc-by-sa-4.0
language:
- en
size_categories:
- 1K<n<10K
task_categories:
- question-answering
- multiple-choice
pretty_name: OenoBench
tags:
- wine
- viticulture
- enology
- benchmark
- multiple-choice-qa
- domain-knowledge
- evaluation
annotations_creators:
- machine-generated
- expert-generated
language_creators:
- machine-generated
multilinguality:
- monolingual
source_datasets:
- original
- extended|wikipedia
- extended|wikidata
configs:
- config_name: default
  data_files:
  - split: test
    path: data/test.parquet
---

# OenoBench (release_v1.2)

A 3,329-question multiple-choice benchmark covering the full breadth of the
wine domain — from viticulture and winemaking to wine regions, grape
varieties, producers, and the wine business. Designed to evaluate the
factual recall, comparative reasoning, and applied-decision capabilities
of large language models against expert-vetted, source-anchored knowledge.

- **Paper / repo:** https://github.com/nikitahudov/oenobench
- **Track:** NeurIPS 2026 Evaluations & Datasets (E&D) — single-blind submission
- **Version:** `release_v1.2` (post-audit, post difficulty-relabel, 2026-05-03)

---

## Dataset summary

| Metric | Value |
|---|---:|
| Total questions | **3,329** |
| Difficulty levels | 4 (post-relabel) |
| Domains | 6 (wine_regions, grape_varieties, producers, viticulture, winemaking, wine_business) |
| Question type | multiple choice (4 options) |
| Avg options per question | 4 |
| Cognitive dimensions | 4 (recall, compare, apply, synthesize) |
| Generators | 5 LLMs + deterministic templates |
| Generation strategies | 5 (fact_to_question, comparative, scenario_synthesis, distractor_mining, template) |
| Source facts | 38,104 atomic facts from 35 sources (Wikipedia, Wikidata, USDA, INAO, OIV, UC Davis, …) |
| Splits | one — `test` (this is an evaluation-only benchmark) |
| Audit | 9-agent automated audit + 50-question human gold review |

### Composition

**By generation strategy**
| Strategy | Questions |
|---|---:|
| fact_to_question | 1,940 |
| distractor_mining | 412 |
| template | 389 |
| scenario_synthesis | 327 |
| comparative | 261 |

**By generator**
| Generator | Questions |
|---|---:|
| Qwen 3.5 (235B) | 678 |
| Llama 3.1 (405B) | 654 |
| Claude Opus 4.7 | 622 |
| ChatGPT 5.4 | 560 |
| Gemini 3.1 Pro | 426 |
| template_only (no LLM) | 389 |

**By domain**
| Domain | Questions |
|---|---:|
| wine_regions | 1,108 |
| grape_varieties | 766 |
| producers | 515 |
| viticulture | 502 |
| wine_business | 250 |
| winemaking | 188 |

**By difficulty (post-relabel — see "Difficulty calibration" section)**
| Level | Questions | % |
|---|---:|---:|
| L1 (entry) | 694 | 20.8% |
| L2 (intermediate) | 927 | 27.8% |
| L3 (advanced) | 698 | 21.0% |
| L4 (expert) | 1,010 | 30.3% |

---

## How to load

```python
from datasets import load_dataset

ds = load_dataset("nikitahudov/oenobench-v1", split="test")
print(len(ds))           # 3329
print(ds[0]["question_text"])
print(ds[0]["options"])  # [{"id": "A", "text": "..."}, ...]
print(ds[0]["correct_answer"])  # "A" / "B" / "C" / "D"
```

Raw Parquet is also at `data/test.parquet` for direct pandas / polars / DuckDB
use.

```python
import pandas as pd
df = pd.read_parquet("hf://datasets/nikitahudov/oenobench-v1/data/test.parquet")
```

---

## Schema

| Column | Type | Description |
|---|---|---|
| `uuid` | string | internal stable UUID |
| `question_id` | string | public ID, e.g. `WB-REG-0042-L3` (the L-suffix is the **originally assigned** difficulty; see `difficulty` column for the post-relabel value) |
| `domain` | string | one of: `wine_regions`, `grape_varieties`, `producers`, `viticulture`, `winemaking`, `wine_business` |
| `difficulty` | int8 | 1–4 (post-relabel — calibrated by C4 difficulty audit + human spot-check overrides) |
| `difficulty_assigned` | int8 | 1–4 (original generator-assigned label) |
| `difficulty_relabel_source` | string\|null | `null` if not relabelled; `c4_fail` if updated by C4 difficulty audit (Gemini Pro re-rate, delta ≥ 2); `human_override` if a wine-expert reviewer set a `suggested_difficulty` |
| `question_type` | string | always `multiple_choice` in v1 |
| `cognitive_dim` | string | `recall`, `compare`, `apply`, `synthesize` |
| `question_text` | string | question stem |
| `options` | list\<struct\> | list of `{id: "A"\|"B"\|"C"\|"D", text: str}` |
| `correct_answer` | string | the keyed letter |
| `correct_answer_text` | string | the prose form of the correct option |
| `explanation` | string | short rationale for the correct answer |
| `generator` | string | `claude`, `chatgpt`, `gemini`, `llama`, `qwen`, `template_only` |
| `generation_method` | string | `fact_to_question`, `comparative`, `scenario_synthesis`, `distractor_mining`, `template` |
| `source_facts` | list\<struct\> | list of `{fact_id, fact_text, source_name, source_url}` — the externally-verified facts the question is grounded in |
| `audit_verdict` | string | one of `audit_clean`, `audit_warn_only`, `audit_calibration_warning` (see "Audit" below) |

---

## Data sources

OenoBench's source facts are scraped from 35 authoritative wine-knowledge
sources, all CC-BY-SA-compatible. Top contributors:

- **Wikipedia** (CC BY-SA 3.0) — 9,283 facts; English Wikipedia articles on
  wine regions, grapes, producers, and viticulture/oenology topics
- **Wikidata** (CC0) — 2,145 facts; SPARQL queries for wine entities
- **HuggingFace datasets** (varied) — 3,231 facts; `spawn99/wine-reviews`,
  `christopher/winesensed`
- **UC Davis** (CC-BY-SA) — 2,199 facts; Wine Ontology RDF, AVA Digitizing
  Project GeoJSON, FPS Grape Database
- **INAO (France)** (Licence Ouverte) — 1,473 facts; data.gouv.fr open-data
  CSVs of French AOC/AOP/IGP appellations
- **TTB (US)** (public domain) — 513 facts; Code of Federal Regulations text
- **OENO One / Vitis / AJEV (academic journals)** (CC-BY-SA) — 925 facts
- **UC IPM Grape** (CC-BY-SA) — 1,145 facts; integrated pest management
  guidelines
- **USDA / Penn State / Oregon State extension services** (public domain) —
  705 facts
- 25+ additional regional sources (Bordeaux, Burgundy, Champagne, Italian
  consortiums, Spanish DO bodies, Australian/NZ wine bodies, etc.)

Every fact in the DB traces to a verifiable source URL. No LLM-generated
"facts" are stored as ground truth — the entire pipeline was rebuilt in
April 2026 after a provenance audit.

---

## Data collection & generation pipeline

1. **Scraping** (35 scrapers, ~3 weeks): atomic-fact extraction from the
   sources above into a Postgres `facts` table with entity tags (`region`,
   `grape`, `appellation`, `producer`, `country`, `ava`, `doc`, `docg`, etc.)
2. **Question generation** (5 strategies × 5 LLMs): each strategy samples
   facts and asks an LLM (or a deterministic template) to produce a
   multiple-choice question. Strategies:
   - `fact_to_question` (45% of v1 build) — single fact → one Q
   - `comparative` (15%) — two facts about different but comparable
     entities → "which differs in X" Q
   - `scenario_synthesis` (15%) — fact cluster → applied-decision scenario Q
   - `distractor_mining` (15%) — fact + confusable distractors → multiple-
     choice with carefully-chosen wrong options
   - `template` (10%) — deterministic 45-template engine, no LLM
3. **Closed-book gate**: every L1/L2 LLM-MC question is pre-screened by an
   independent LLM solver. If the gate solves it correctly with no source
   fact, the question is either bumped to a `closed_book_solvable` reserve
   or relabeled to L1 (under a 50% per-strategy quota).
4. **Audit** (9 agents): see "Audit" section below.
5. **Drop policy + difficulty relabel** (Phase 2j): see "Curation" below.

Full methodology in `docs/PROCESS_LOG.md` of the GitHub repo.

---

## Audit

Each question was evaluated by a multi-agent audit framework (run_id
`2ba38269-5e66-44aa-aaaf-010dc7ef19d4`, 5h 22m wall, ~$76 OpenRouter cost):

| Team | Agent | What it checks |
|---|---|---|
| A (static) | A1 LexicalHygiene | Vague phrasing (`iconic`, `acclaimed`, …) + thin-geo template detection |
| A (static) | A2 BiasStats | χ² on correct-answer position; Mann-Whitney U on length (correct vs distractors) |
| A (static) | A3 FactEcho | Verbatim copy: LCS ratio + contiguous n-gram against source facts |
| A (static) | A4 TemplateFingerprint | Logreg AUC: machine-vs-human stylistic distinguishability |
| B (LLM panel) | B1 TriJudgeAnswer | 3-judge consensus answers the question with source; flag if majority disagrees with key |
| B (LLM panel) | B2 ClosedBookSolvability | Same panel + Llama/Qwen, NO source — flag if too many judges still keyed |
| C (static) | C2 CategoryLeak | Distractor wine-category mismatch (red question with white distractor, etc.) |
| C (LLM, opt) | C4 DifficultyAudit | Gemini Pro re-rates difficulty; FAIL if delta ≥ 2 from assigned |
| D (corpus) | D1 SelfPreference | 5×5 evaluator×author matrix |
| D (corpus) | D3 SkewAudit | Country / subdomain over-representation |
| Custom | B3 UbiquityRisk | Static check: stem mentions an internationally-grown grape × correct answer is a region-class entity (ambiguous) |

### Audit verdicts in the corpus

| Verdict | Count | Meaning |
|---|---:|---|
| `audit_clean` | 68 | No FAIL, no WARN |
| `audit_warn_only` | 1,063 | One or more WARNs, no FAILs |
| `audit_calibration_warning` | 2,198 | B2 closed-book or C4 difficulty calibration signal — *not* a question-quality fail |
| `audit_fail_review` | 0 | (questions in this bucket were dropped before v1.2) |
| `audit_fail_critical` | 0 | (dropped) |

---

## Curation (drops + difficulty relabel)

The release_v1.1 audit-time corpus had 3,670 questions. Curation policy:

### Drops — 341 questions removed

A question was untagged from the release if it had at least one FAIL on
**A1, A3, B1, C2, or B3**:

| Defect | Distinct Qs |
|---|---:|
| A1 LexicalHygiene (vague phrasing) | 60 |
| A3 FactEcho (verbatim copy LCS≥0.65) | 63 |
| B1 TriJudgeAnswer (key disagrees with judges) | 47 |
| C2 CategoryLeak (distractor category mismatch) | 9 |
| B3 UbiquityRisk (ubiquity-grape × region answer) | 183 |
| **Total distinct dropped** | **341** |

### Kept — B2 + C4 (calibration signals, not real fails)

- **B2 ClosedBookSolvability**: ~1,452 questions where an LLM panel
  solved the question without the source. We **kept** these. Cohen's κ
  between B2's signal and human reviewers on the `needs_source` rubric
  is ≈ 0.007 (essentially no agreement) — frontier-LLM judges over-report
  closed-book solvability by ~5× because they know more wine than the
  benchmark target audience. We disclose the B2 finding in the dataset
  but do not treat it as a defect.
- **C4 DifficultyAudit**: 1,351 questions where Gemini Pro re-rated the
  difficulty by delta ≥ 2 from the generator-assigned label. We resolved
  this by **relabelling**, not dropping: the post-relabel `difficulty`
  column is C4's `rated_difficulty` (or the human reviewer's
  `suggested_difficulty` when available). 1,259 of the 3,329 questions
  have a relabel applied (1,252 from C4, 7 from human review). The
  public `question_id` (e.g. `WB-REG-0042-L3`) keeps the original
  L-suffix as a stable label; eval consumers must read from the
  `difficulty` column for the post-relabel value.

Difficulty distribution shifted dramatically (corpus is genuinely harder
post-relabel):

| Level | Pre-relabel | Post-relabel | Δ |
|---|---:|---:|---:|
| L1 | 1,261 | 694 | -567 |
| L2 | 1,559 | 927 | -632 |
| L3 | 218 | 698 | +480 |
| L4 | 291 | 1,010 | +719 |
| L3+L4 share | 14% | **51%** | +37pp |

### Human review

A 50-question stratified smart sample was scored by a wine domain expert
on 8 rubrics (answer correct, distractors plausible, not ambiguous,
source faithful, needs source, no vague language, labels correct,
verbatim copy). Of the 45 completed reviews:

- 36 approved, 6 rejected (13%), 3 needs revision
- 9/45 (20%) flagged ambiguous → drove the **B3_UbiquityRisk** custom audit
- 14/45 set a `suggested_difficulty` → 7 of those were on questions in
  the release_v1.2 corpus and overrode C4's rating

Cross-check: in 8/8 spot-checked human suggestions, C4's rating was
within ±1 of the human's — supporting the C4 relabel choice.

---

## Intended uses

- **Evaluating LLM wine knowledge** at four difficulty tiers, calibrated
  to industry certification standards (entry-level WSET 1 → Master of
  Wine).
- **Studying domain-specific reasoning** — the corpus deliberately mixes
  factual recall (`recall`), comparative reasoning (`compare`), applied
  decisions (`apply`), and synthesis across multiple facts (`synthesize`).
- **Self-preference / generator-bias analysis** — five LLMs each
  contributed ~10–20% of questions, enabling per-evaluator-per-author
  measurements (D1 SelfPreference is reported in the audit).
- **Pre-eval probing of source-grounding** — the `source_facts` column
  exposes the externally-verified facts each question rests on, so
  evaluators can probe whether a model uses world knowledge or actually
  reasons from the provided source.

---

## Limitations + biases (Responsible AI)

- **English-only.** All questions and source facts are in English. Wine
  is a deeply multilingual domain (French, Italian, Spanish, German
  technical vocabularies dominate) — this is a known limitation.
- **Geographic skew** toward Old World (Europe) and US/Australia/New
  Zealand. Asian, African, and South American producing regions are
  under-represented relative to global production volume because the
  authoritative sources cluster geographically. The `D3_SkewAudit`
  finding records the population statistics; max country
  over-representation is 2.56× (downgraded to WARN by the coverage guard
  because only 12.1% of questions carry a country tag).
- **Generator-mix bias.** Five LLMs contributed questions; each may have
  systematic blind spots. The D1_SelfPreference audit measured a
  population-level Δ of 0.33 — interpret per-model evaluation results
  alongside D1.
- **Closed-book solvability** (B2 signal). 2,198 questions carry a B2
  WARN/FAIL meaning an LLM panel solved them without the source. This is
  *not* a defect — frontier LLMs know a lot of wine — but downstream
  evaluators should be aware that ~66% of the corpus could in principle
  be answered without reading the source fact.
- **Ubiquity-grape filter is rule-based.** B3 catches questions where
  ubiquitous international grapes (Cabernet, Pinot Noir, Chardonnay,
  Riesling, …) appear in stems with region-class answers. We caught and
  dropped 183. Some borderline cases (e.g. data-driven ubiquity threshold)
  may slip through; please raise an issue if you find one.
- **Difficulty re-rating relies on Gemini Pro + 8 human spot checks.** L3
  and L4 levels are now the largest buckets after C4 re-rating. We have
  not independently verified C4's rating against a wine expert at scale;
  the 8 human spot checks all agreed with C4 within ±1.
- **No PII.** Source facts are public; producer names and famous
  individuals are mentioned but only insofar as they appear in
  Wikipedia/Wikidata or government appellation registries.
- **No medical / health claims.** This is wine-domain knowledge, not
  medical advice. Some questions touch on residual sugar, alcohol levels,
  and sulfite content for technical/regulatory reasons; nothing should
  be construed as health guidance.
- **Synthetic data flag**: the questions are LLM-generated (synthetic),
  but the source facts they rest on are NOT. Every fact traces to a
  verifiable URL.

---

## Citation

```bibtex
@misc{oenobench2026,
  title  = {OenoBench: A Comprehensive Wine Knowledge Benchmark for Large Language Models},
  author = {Hudov, Nikita},
  year   = {2026},
  note   = {NeurIPS 2026 Evaluations & Datasets Track},
  url    = {https://huggingface.co/datasets/nikitahudov/oenobench-v1}
}
```

(Full BibTeX will be updated post-acceptance with the published reference.)

---

## License

**CC-BY-SA-4.0** — chosen for compatibility with the upstream Wikipedia
sources and to encourage open reuse with share-alike obligations.

You may copy, redistribute, remix, transform, and build upon this dataset
for any purpose, including commercially, provided you:

1. Give appropriate credit and indicate if changes were made.
2. Distribute your contributions under the same license as the original.

See https://creativecommons.org/licenses/by-sa/4.0/ for the full license.

---

## Contact / issues

- GitHub: https://github.com/nikitahudov/oenobench
- Issues / PRs welcome.

---

## Changelog

- **release_v1.2** (2026-05-03): post-audit, post-difficulty-relabel.
  3,329 questions. 341 dropped on B1/A3/C2/B3/A1 critical fails. 1,259
  difficulty relabels. Three audit verdicts surface in the
  `audit_verdict` column.
- release_v1.1 (2026-05-03): pre-audit assembly. 3,670 questions.
  Combined original release_v1 + sample-DB v2 (1,062 quality-vetted) +
  389 cb_reserve promoted, deduped at cosine 0.92.
- release_v1 (2026-05-02): initial 6,500-target build hit substantive-
  fact ceiling at 2,535 questions.
