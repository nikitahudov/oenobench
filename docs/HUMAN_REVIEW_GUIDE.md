# Human Review Guide — OenoBench Question Review App

**Audience:** wine domain experts performing the human review for the OenoBench question corpus.
**Tool:** browser-based review app (Flask, port 5556).

---

## Why your review matters

OenoBench is being submitted to the **NeurIPS 2026 Datasets & Benchmarks Track**. The release candidate corpus (`release_v1`) currently holds **~2,535 questions** that have already passed automated audit gates. Your expert review is what turns that machine-vetted corpus into a benchmark we can defend in the paper: it produces the inter-rater statistics (Cohen's κ) that the methodology section will cite, surfaces wrong-keyed answers before they reach external evaluators, and gives the regeneration pipeline a final, human-grounded signal on which questions need to be revised or rejected. Every review you submit is attached to your reviewer record and used in the paper's reliability analysis.

---

## Web app workflow

1. **Visit the URL your project lead shared with you.** The page is gated by a shared password — your project lead will give you the username and password along with the link.
2. **Sign in with your email.** First time? You'll be asked for your name, professional credentials (e.g. "WSET Diploma", "MS candidate, 12 yrs in trade"), and which wine domains you feel most confident scoring. This is captured once and stamped onto every review you submit.
3. **From the dashboard, click "Review" on the active batch.** The dashboard shows which batches are open and how many questions you have left in each.
4. **Review one question at a time.** For each question:
    - Read the stem, the four options (the keyed correct option is flagged), and open the "Source facts" panel to see the supporting facts the question was generated from.
    - Score each of the 10 rubrics with **PASS / WARN / FAIL** — or leave it as **SKIP** if you genuinely cannot decide.
    - Set an **Overall Verdict**: Approve / Revise / Reject.
    - Optionally suggest a corrected answer letter (A/B/C/D) or a corrected difficulty (1–4) if the keyed values look wrong.
    - Add free-text notes when a `fail` rating needs context — these notes feed directly into the next regeneration round.
5. **Click Submit.** The next question loads automatically.
6. **When you reach the "All done" screen,** you can stop or come back later — your reviewer record is keyed by email, so picking up next session resumes where you left off.

---

## New fields

The web app captures three fields on top of the 10 rubrics:

- **`overall_verdict`** (Approve / Revise / Reject): the top-level call. Approve means the question is ready for release as-is; Revise means it has fixable defects (use notes to describe what); Reject means it should be removed from the corpus.
- **`suggested_answer`**: optional letter (A / B / C / D) when you believe the keyed answer is wrong and you can identify which option *should* be correct.
- **`suggested_difficulty`**: optional 1–4 override when `difficulty_match = fail`, so the corpus can be re-keyed without a follow-up review round.

These are independent of the 10 rubric scores — set them when they apply, leave them blank otherwise.

---

## Inter-rater reliability

Every question is shown to **≥2 reviewers when reviewers are available**. The app's question-selection algorithm preferentially routes questions with 0 prior reviews, then 1 prior review, then 2+ — so as more reviewers come online, IRR coverage grows automatically.

**Do not coordinate with other reviewers.** The whole point of IRR is to capture independent expert judgements; comparing notes mid-review contaminates the κ calculation.

**Honest blanks (SKIP) are better than guesses.** A SKIP is stored as NULL and is excluded from both per-rubric pass-rate stats and the κ calculation, so it does not bias the methodology numbers. A guess does bias them. If you genuinely cannot decide on a rubric — leave it SKIP and add a note explaining why.

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

### `needs_source`

Could a reasonably knowledgeable wine taker (think: WSET Diploma student) answer this question **without** consulting the source fact, purely from world knowledge? L1/L2 questions that fail this rubric are the gate's primary target — they are the ones being routed to the `closed_book_solvable` quota tag.

- **pass**: the question genuinely requires the source — answering needs the specific datum in `source_facts`.
- **warn**: a wine pro can guess but a layperson cannot.
- **fail**: the answer is part of basic wine knowledge (e.g. "Which grape is required for Barolo?" — most wine-curious adults know it's Nebbiolo without reading anything).

If you see a fail here on a question whose label is not 1, flag it in the notes.

### `verbatim_copy`

Does the question stem or the correct option text **copy more than ~60% of the source fact verbatim**? This is the narrow proxy that the audit pipeline measures via longest-common-subsequence. We split it out from `source_faithful` because the two rubrics measure different things — verbatim copying is a string-similarity issue; faithfulness is a semantic issue.

- **pass**: the question paraphrases or transforms the source.
- **warn**: a long phrase (≥6 words) is copied but the rest of the stem is rewritten.
- **fail**: the stem or correct option is essentially a cut-and-paste of the source fact.

Note: on multi-fact strategies a question MUST echo language from one of the facts to ground itself; mark `pass` unless the copying is verbatim-and-pointless (e.g. the entire stem is the source fact with the answer phrase blanked out).

### `wine_category_leak`

Do the distractors **leak the right wine category** of the correct answer? Example: the correct answer is a red wine and three of the distractors are also red wines, while the fourth is a white — the white is trivially eliminable, leaking that the answer is red.

This rubric is about distractor *category coherence*, not plausibility.

- **pass**: distractors all sit in the same category as (or a category overlapping with) the correct answer — there is no free elimination.
- **warn**: one distractor's category leaks the answer but you still need wine knowledge to pick among the rest.
- **fail**: the categorical split is so obvious that the question reduces to a 2- or 3-option choice.

This rubric was narrowed from the broader `distractors_plausible` so we can isolate one specific failure mode. Distractor plausibility broadly is still on the `distractors_plausible` rubric above.

---

## Worked examples

These are real questions from the corpus. They are illustrative — your judgement supersedes mine.

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

If anything is unclear, leave the rubric as SKIP and add a note. Blank cells are honest — guesses are not.
