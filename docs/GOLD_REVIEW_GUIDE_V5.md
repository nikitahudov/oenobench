# Gold Review Guide — v5 (audit_pilot_v5)

**Audience:** the wine domain expert performing the human gold review for `audit_pilot_v5`.
**Sheet:** `data/reports/gold_sheet_v5.csv` — 120 rows, stratified 24 per strategy.
**Pipeline version:** v2.3 (Phase 2g) + v2.0 closed-book gate (Phase 2g.6).

---

## Purpose

The κ calibration table in `docs/QUALITY_AUDIT_REPORT.md` shows `n=0` for two rubrics that are new in v2.3: `verbatim_copy` and `wine_category_leak`. Those rubrics replaced — at finer granularity — the over-loaded `source_faithful` and `distractors_plausible` proxies. The pre-v2.3 gold review (110 rows from 2026-04-19) does not contain labels for them. This v5 sheet is a fresh stratified sample of the post-Phase-2g.6 corpus so we can:

1. Recompute κ for **all 10** rubrics with the correct rubric/proxy alignment.
2. Validate the closed-book gate v2.0 quota (questions tagged `closed_book_solvable` should — by construction — *fail* `needs_source` ~100% of the time).
3. Decide the regeneration Go/No-Go gate (per `docs/GENERATION_IMPROVEMENT_PLAN.md`).

The sheet contains 120 questions: 24 per strategy (template, fact_to_question, comparative, scenario_synthesis, distractor_mining), sub-stratified across generator and difficulty, and shuffled so you do not see all template_only questions clustered at the top.

---

## How to use the sheet

1. Open `data/reports/gold_sheet_v5.csv` in any spreadsheet tool (LibreOffice / Excel / Google Sheets). The 11 leftmost columns are read-only metadata; the rubric columns are blank for you to fill in.
2. Read the question (`question_text`), the options (`options`), the keyed answer (`correct_answer`), and the source evidence (`source_facts`). On multi-fact strategies (`comparative`, `scenario_synthesis`, `distractor_mining`) the `source_facts` column is multi-line and indexed `[1] … [2] …`.
3. Fill **only** the rubric columns. Use one of: `pass` / `warn` / `fail` (or `1` / `0` — both are accepted by the importer; `1`=pass, `0`=fail). **Leave a column blank if you genuinely cannot decide.** Blank cells are stored as NULL — they do not bias the calibration.
4. Use the `notes` column for any free-text comments (especially helpful when you flagged `fail` so the next iteration of generation prompts can target the actual defect).
5. Save the CSV in place. Then import via:

    ```
    python -m src.qa.orchestrator import-gold \
        --csv-path data/reports/gold_sheet_v5.csv \
        --reviewer nikita
    ```

   The importer is idempotent — re-running with corrections overwrites the previous label for the same question UUID.

---

## Rubric definitions

There are 10 rubric columns. They are independent — a question can pass `answer_correct` while failing `needs_source`, etc.

### `answer_correct`

Does the keyed `correct_answer` actually correspond to the wine fact stated in `source_facts`? You are the ground truth here. This is the **single most important** rubric — a wrong-keyed question makes everything else moot.

- **pass**: keyed answer is unambiguously correct given the source.
- **fail**: keyed answer contradicts the source, or the source does not support the claimed answer at all.
- **warn**: technically defensible but the source is ambiguous about it.

### `distractors_plausible`

Are the wrong options at least *plausibly close* to the correct answer? A distractor that is trivially eliminable (e.g. the answer is a grape but a distractor is a country) makes the question free.

- **pass**: each distractor is from the same category and could fool a reasonable taker.
- **warn**: 1 distractor is weak but the question is still non-trivial.
- **fail**: 2+ distractors are obviously wrong on their face.

### `no_vague_language`

Is the stem free of marketing fluff and hedge-words? Banned phrases include things like "Which best describes…", "Which of the following is most likely…", "iconic", "acclaimed", "renowned", "world-class".

- **pass**: clean, neutral, factual stem.
- **warn**: one borderline phrase but the question is still answerable.
- **fail**: the stem is so hedged or florid that the answer becomes a matter of interpretation.

### `not_ambiguous`

Is there exactly one defensible answer among the four options? An "all of the above" or two equally true options is a fail.

- **pass**: exactly one defensible answer.
- **warn**: a second option is technically defensible only on a wine-trivia stretch.
- **fail**: ≥2 options are equally well supported by mainstream wine reference works.

### `difficulty_match`

Does the labelled difficulty (`1`/`2`/`3`/`4`) match the actual cognitive load? L1 should be a fast recall question; L4 should require expert chained reasoning.

- **pass**: the label is right within ±0 levels.
- **warn**: off by 1 (e.g. labelled L3 but feels L2).
- **fail**: off by ≥2 (e.g. labelled L4 but a beginner could answer in 5 seconds).

### `cognitive_match`

Does the cognitive class (`recall`, `compare`, `apply`, `synthesize`, etc., shown in `cognitive_dim`) match what the question actually demands?

- **pass**: label correctly describes the cognitive demand.
- **warn**: the demand straddles two adjacent classes.
- **fail**: a question labelled `synthesize` is in fact pure recall, or vice versa.

### `source_faithful`

Does the question's content stay **within the semantic claims** of the source fact(s)? This is the *human-only* rubric — there is no LLM proxy that gets it right (gold-v3 calibration showed κ=0.30 for the verbatim-LCS proxy, which is why we split it into the narrower `verbatim_copy` rubric in v2.3).

- **pass**: the question, options, and explanation only assert claims that are in `source_facts` (or are trivial logical entailments thereof).
- **warn**: 1 minor factual extension that you happen to know is true but isn't in `source_facts`.
- **fail**: the question makes a wine claim that is **not** supported by the listed source facts (even if the claim happens to be true in the wider world).

### `needs_source` — **the critical rubric for v5**

Could a reasonably knowledgeable wine taker (think: WSET Diploma student) answer this question **without** consulting the source fact, purely from world knowledge? L1/L2 questions that fail this rubric are the gate's primary target — they are the ones being routed to the `closed_book_solvable` quota tag (see Phase 2g.6).

- **pass**: the question genuinely requires the source — answering needs the specific datum in `source_facts`.
- **warn**: a wine pro can guess but a layperson cannot.
- **fail**: the answer is part of basic wine knowledge (e.g. "Which grape is required for Barolo?" — most wine-curious adults know it's Nebbiolo without reading anything).

This rubric is where we expect to see the biggest distribution shift from v4 → v5: the gate should have moved most fail-here L1/L2 questions into the `closed_book_solvable` tag (and forced their difficulty to 1). If you see a fail here on a question whose label is not 1, flag it in `notes`.

### `verbatim_copy` (new in v2.3)

Does the question stem or the correct option text **copy more than ~60% of the source fact verbatim**? This is the v2.3 narrow proxy that A3 measures via longest-common-subsequence. We split it out from `source_faithful` because gold-v3 showed the two rubrics measure different things — verbatim copying is a string-similarity issue; faithfulness is a semantic issue.

- **pass**: the question paraphrases or transforms the source.
- **warn**: a long phrase (≥6 words) is copied but the rest of the stem is rewritten.
- **fail**: the stem or correct option is essentially a cut-and-paste of the source fact.

Note: on multi-fact strategies a question MUST echo language from one of the facts to ground itself; mark `pass` unless the copying is verbatim-and-pointless (e.g. the entire stem is the source fact with the answer phrase blanked out).

### `wine_category_leak` (new in v2.3)

Do the distractors **leak the right wine category** of the correct answer? Example: the correct answer is a red wine and three of the distractors are also red wines, while the fourth is a white — the white is trivially eliminable, leaking that the answer is red.

This rubric is about distractor *category coherence*, not plausibility.

- **pass**: distractors all sit in the same category as (or a category overlapping with) the correct answer — there is no free elimination.
- **warn**: one distractor's category leaks the answer but you still need wine knowledge to pick among the rest.
- **fail**: the categorical split is so obvious that the question reduces to a 2- or 3-option choice.

This is C2's rubric, narrowed from the broader v2.2 `distractors_plausible` so we can isolate one specific failure mode. Distractor plausibility broadly is still on the `distractors_plausible` rubric above.

---

## Worked examples

These are real questions from the v5 sheet. They are illustrative — your judgement supersedes mine.

### `answer_correct` — pass example

> **Q:** Name a grape variety approved for Recioto di Gambellara wines.
> **Options:** Malagouzia / Godello / Pallagrello / **Garganega**
> **Source [1]:** Recioto di Gambellara DOCG requires minimum 80% Garganega.
> **Verdict:** pass — the source explicitly states Garganega is required.

### `answer_correct` — fail signal

If the source fact says "Barolo DOCG requires 100% Nebbiolo" but the keyed answer is `Sangiovese`, mark **fail**. Do not "rescue" the question by inventing context — wrong is wrong.

### `distractors_plausible` — pass

> **Q:** Which white grape variety, primarily cultivated in northern Portugal, is known for achieving high acidity levels in its wines?
> **Options:** Gouveio / Arinto / **Viosinho** / Rabigato
> **Verdict:** pass — all four are northern-Portuguese white grapes; you must actually know the source attribution.

### `distractors_plausible` — fail signal

If the answer is a grape and one distractor is a country, two are grapes from a totally different region, mark fail.

### `no_vague_language` — fail signal

> Stem starts with "Which of the following best describes the most iconic style of…"
> **Verdict:** fail — `best describes` + `most iconic` is exactly the marketing-fluff anti-pattern.

### `not_ambiguous` — pass

> **Q:** Which Italian wine region saw the formation of a consortium in 1990 that implemented self-regulatory codes, including the gradual reduction of yields and the elimination of Pinot grigio from its wines?
> **Options:** Nizza / Valpolicella / **Franciacorta DOCG** / Ostuni DOC
> **Verdict:** pass — only Franciacorta matches the 1990 consortium + Pinot-grigio-elimination signature.

### `difficulty_match` — fail signal

If labelled `4` (expert chained reasoning) but the question is "What grape is in Champagne?", mark fail — the cognitive demand is L1.

### `source_faithful` — multi-fact pass

> **Q:** A winemaker in a northern European region has just finished a growing season marked by cold, rainy weather. The harvested must shows unusually low sugar levels, and the winemaker is considering a technique to compensate.
> **Source [1]:** A chemist named Ludwig Gall suggested Chaptal's method of adding sugar to the must to help wine makers compensate for the effects of detrimental weather.
> **Source [2]:** Chaptalisation process is not intended to make the wine sweeter, but rather to provide more sugar for the yeast to ferment into alcohol.
> **Verdict:** pass — the scenario synthesises both facts faithfully (cold-weather context + chaptalisation as the technique).

### `source_faithful` — fail signal

The source fact is "Barolo requires 100% Nebbiolo" but the question stem describes Barolo as "a Tuscan red". The wine claim ("Tuscan") is not in the source and is, in fact, wrong (Barolo is Piedmontese). Mark fail.

### `needs_source` — fail signal

> Question: "Which grape is required for Champagne?"
> Options include Pinot Noir / Chardonnay / Pinot Meunier / Riesling.
> Source: [some Champagne fact].
> **Verdict:** fail — most wine-curious adults know Champagne uses Chardonnay/Pinot Noir/Pinot Meunier without reading any source. This is exactly the closed-book-solvable pattern the gate v2.0 should have either tagged `closed_book_solvable` (if L1/L2) or accepted as a deliberate L1.

### `verbatim_copy` — fail signal

> **Source:** "Barolo DOCG requires 100% Nebbiolo grapes."
> **Question:** "Barolo DOCG requires 100% _______ grapes."
> **Verdict:** fail — the stem is the source fact with the answer blanked out. Trivial pattern-matching.

### `wine_category_leak` — fail signal

> Correct answer: Cabernet Sauvignon (red).
> Distractors: Merlot (red) / Syrah (red) / Sauvignon Blanc (white).
> **Verdict:** fail — Sauvignon Blanc is the only white, leaking that the answer is red. The question collapses to a 3-option red-grape choice.

---

## CSV column reference

| Column | Editable | What it means |
|---|---|---|
| `uuid` | no | Internal question UUID — the import key. |
| `public_qid` | no | Human-readable ID like `WB-REG-0042-L3`. |
| `strategy` | no | One of the 5 generation strategies. |
| `generator` | no | claude / chatgpt / gemini / llama / qwen / template_only. |
| `domain` | no | wine_regions / grape_varieties / producers / viticulture / winemaking / wine_business. |
| `difficulty` | no | 1 / 2 / 3 / 4. |
| `cognitive_dim` | no | recall / compare / apply / synthesize / etc. |
| `question_text` | no | The stem. |
| `options` | no | JSON array of `{id, text}` options. |
| `correct_answer` | no | The keyed letter (A/B/C/D). |
| `source_facts` | no | `[1] …\n---\n[2] …` — all linked source facts. |
| `answer_correct` | **yes** | pass / warn / fail / blank. |
| `distractors_plausible` | **yes** | pass / warn / fail / blank. |
| `not_ambiguous` | **yes** | pass / warn / fail / blank. |
| `source_faithful` | **yes** | pass / warn / fail / blank. |
| `needs_source` | **yes** | pass / warn / fail / blank. |
| `no_vague_language` | **yes** | pass / warn / fail / blank. |
| `difficulty_match` | **yes** | pass / warn / fail / blank. |
| `cognitive_match` | **yes** | pass / warn / fail / blank. |
| `verbatim_copy` | **yes** | pass / warn / fail / blank. |
| `wine_category_leak` | **yes** | pass / warn / fail / blank. |
| `notes` | **yes** | Free text — especially valuable on `fail` rows. |

The importer accepts `pass` / `warn` / `fail` / `1` / `0` / `y` / `n` / `yes` / `no` / `true` / `false` (case-insensitive). Anything else (or blank) is treated as missing and stored as NULL. `warn` is treated as `pass` by the κ calculation — if you want to make a finer distinction, please use `notes`.

---

## Submission

1. Save the filled CSV in place at `data/reports/gold_sheet_v5.csv` (overwrite the blank export).
2. Run:

   ```
   python -m src.qa.orchestrator import-gold \
       --csv-path data/reports/gold_sheet_v5.csv \
       --reviewer nikita
   ```

3. Re-render the audit report:

   ```
   python -m src.qa.orchestrator build-reports --run-id 541d1d1d-1a89-4f5a-8940-218928da3729
   ```

4. Verify the `§6 · Gold calibration` table in `docs/QUALITY_AUDIT_REPORT.md` now shows non-zero `n` for all 10 rubrics.

If anything is unclear, leave the rubric blank and add a note. Blank cells are honest — guesses are not.
