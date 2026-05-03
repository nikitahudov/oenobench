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
    - Score each of the 8 rubrics with **PASS / WARN / FAIL** — or leave it as **SKIP** if you genuinely cannot decide.
    - Set an **Overall Verdict**: Approve / Revise / Reject.
    - Optionally suggest a corrected answer letter (A/B/C/D) inline with `answer_correct`, or a corrected difficulty (1–4) inline with `labels_correct`, when the keyed values look wrong.
    - Add free-text notes when a `fail` rating needs context — these notes feed directly into the next regeneration round.
5. **Click Submit.** The next question loads automatically.
6. **When you reach the "All done" screen,** you can stop or come back later — your reviewer record is keyed by email, so picking up next session resumes where you left off.

### Skip

The **Skip** button drops the current question for the rest of *this* session — it does not write a row to `human_reviews` and does not affect the IRR count for that question. The question still goes to other reviewers, and it will come back to you in a future session if it still needs your input. Use Skip when the question is outside your area of confidence; use SKIP on a single rubric (rather than the whole question) when only one dimension is the problem.

### Autosave

Your in-progress chip selections, verdict, suggested answer/difficulty, and notes are saved to your browser's local storage on every change. If the browser crashes, the tab is closed, or you reload the page, the form rehydrates from local storage when you next land on the same question. The autosaved entry is cleared on a successful Submit (or on Skip).

---

## New fields

The web app captures three fields on top of the 8 rubrics:

- **`overall_verdict`** (Approve / Revise / Reject): the top-level call. Approve means the question is ready for release as-is; Revise means it has fixable defects (use notes to describe what); Reject means it should be removed from the corpus.
- **`suggested_answer`**: optional letter (A / B / C / D) when you believe the keyed answer is wrong and you can identify which option *should* be correct. The input sits inline with the `answer_correct` rubric row.
- **`suggested_difficulty`**: optional 1–4 override when `labels_correct = fail` on the difficulty axis, so the corpus can be re-keyed without a follow-up review round. The dropdown sits inline with the `labels_correct` rubric row.

These are independent of the 8 rubric scores — set them when they apply, leave them blank otherwise.

---

## Keyboard shortcuts

The app is built for sustained 100+ question sessions, so most actions are reachable from the keyboard:

- **`1` / `2` / `3` / `4`** — when a rubric chip group has focus, score it `pass` / `warn` / `fail` / `skip` respectively.
- **`Tab` / `Shift+Tab`** — move forwards or backwards through the rubric rows, suggested-answer/difficulty inputs, verdict, and notes.
- **`V`** — opens the **Overall verdict** dropdown from anywhere on the page (as long as no input or textarea is focused).
- **`Enter`** — submits the form when the Submit button is enabled (i.e. once the verdict is non-empty).
- **`Esc`** — clears focus and any open chip group, useful for re-grabbing keyboard control after clicking a tip.
- **Show definitions** — a single button at the top of the rubric card flips all 8 rubric tip blocks open or closed at once. It does not have a keyboard shortcut; it's a one-time toggle when you want to see every definition without hovering.

---

## Inter-rater reliability

Every question is shown to **≥2 reviewers when reviewers are available**. The app's question-selection algorithm preferentially routes questions with 0 prior reviews, then 1 prior review, then 2+ — so as more reviewers come online, IRR coverage grows automatically.

**Do not coordinate with other reviewers.** The whole point of IRR is to capture independent expert judgements; comparing notes mid-review contaminates the κ calculation.

**Honest blanks (SKIP) are better than guesses.** A SKIP is stored as NULL and is excluded from both per-rubric pass-rate stats and the κ calculation, so it does not bias the methodology numbers. A guess does bias them. If you genuinely cannot decide on a rubric — leave it SKIP and add a note explaining why.

---

## Rubric definitions

There are 8 rubric columns. They are independent — a question can pass `answer_correct` while failing `needs_source`, etc.

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

This rubric also covers wine-category leakage: if the four options split categories so the correct answer's category is given away (e.g. correct = a red wine, three distractors red, one distractor white — the white is trivially eliminable, leaking that the answer is red), mark `warn` (one leak, question still has work) or `fail` (the categorical split collapses the question to a 2- or 3-option choice).

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

### `labels_correct`

Do the labelled difficulty (`1`/`2`/`3`/`4`) AND the cognitive-dimension label (`recall`, `compare`, `apply`, `synthesize`, etc., from `cognitive_dim`) both match what the question actually demands? This is one combined judgement covering both the difficulty axis and the cognitive-class axis. If only the difficulty axis is off, use the inline **Suggested difficulty** dropdown to record the correction; use the notes textarea for cognitive-axis comments.

- **pass**: both labels are right — difficulty within ±0 levels, cognitive class correct.
- **warn**: one axis is off by a small amount — difficulty off by 1 level (e.g. labelled L3 but feels L2), or the cognitive demand straddles two adjacent classes.
- **fail**: at least one axis is materially wrong — difficulty off by ≥2 (e.g. labelled L4 but a beginner could answer in 5 seconds), or a question labelled `synthesize` is in fact pure recall (or vice versa).

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

### `labels_correct` — fail signal

If labelled `4` (expert chained reasoning) but the question is "What grape is in Champagne?", mark fail — the cognitive demand is L1. Likewise, if a question is labelled `synthesize` but reduces to looking up a single fact, mark fail on the cognitive-class axis.

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

### `distractors_plausible` — wine-category leak fail signal

> Correct answer: Cabernet Sauvignon (red).
> Distractors: Merlot (red) / Syrah (red) / Sauvignon Blanc (white).
> **Verdict:** fail — Sauvignon Blanc is the only white, leaking that the answer is red. The question collapses to a 3-option red-grape choice. This is the wine-category-leak case folded into `distractors_plausible`.

---

If anything is unclear, leave the rubric as SKIP and add a note. Blank cells are honest — guesses are not.
