# Human Reference Set v1 — Sources & Provenance

This document records the sources and licensing for the 104-question
human-written reference set in `human_reference_v1.jsonl`. The set is the
**negative class** (human-written) used by A4 TemplateFingerprint v1.2.0
to learn the stylometric signature of human-authored wine questions
versus OenoBench LLM-generated output.

## Build script

`build_human_reference.py` is a deterministic, one-shot scaffolder. Re-run it
to regenerate the JSONL after edits.

## Quality control criteria

Each retained question must:
1. Be in scope: `wine_regions`, `grape_varieties`, `producers`, `viticulture`,
   `winemaking`, or `wine_business`.
2. Have a clear, self-contained stem (no "Which of the following best
   describes…" filler).
3. Have a definite correct answer.
4. Use a multiple-choice format (3-4 options, one correct). Rare True/False
   were excluded; all retained items have 3-4 options.
5. Avoid pop-culture references (movies, songs, celebrities, sports).
6. Avoid drinking-recommendation / health-claim content.
7. Be license-compatible with research use (CC-BY-SA-4.0 from open
   datasets, or factual content under fair-use research with attribution).

Sources whose quizzes were behind authentication (Quizlet, ThirtyFifty,
PassWSET, Brainscape) were skipped in line with the source-license caution.
Sources whose content was clearly proprietary exam material (Fine Vintage
Level 3 PDF — explicitly stated as extracted from the WSET textbook) were
also skipped.

## Source breakdown

### 1. OpenTriviaQA — 18 questions

- **URL:** https://github.com/uberspot/OpenTriviaQA
- **License:** Creative Commons Attribution-ShareAlike 4.0 International
  (CC-BY-SA-4.0)
- **Coverage:** General-trivia community-uploaded wine questions
  (`hobbies`, `general`, `world`, `history`, `humanities`, `science-technology`,
  `religion-faith`, `newest` categories). Filtered to wine-domain-relevant
  items only; pop-culture, cocktail, and incidental "wine" matches removed
  by hand.
- **Notes:** Some questions had encoding artifacts (Latin-1 in source);
  cleaned to UTF-8 in the JSONL.

### 2. AmEx Essentials wine trivia quiz — 20 questions

- **URL:** https://www.amexessentials.com/wine-trivia-quiz-grape-varieties-quiz/
- **License:** © American Express Services Europe Ltd. 2026. Factual
  content (grape provenance, region, varietal facts) used under fair-use
  research with attribution. Phrasings paraphrased where the original was
  too compressed; correct answer preserved.
- **Coverage:** Grape variety identification (Sangiovese, Tempranillo,
  Sauvignon Blanc, Primitivo, Teinturier, Bordeaux blend, Nebbiolo,
  Spätburgunder, Shiraz, Glera/Prosecco, Pinotage, Gewürztraminer,
  Chardonnay, Carménère, Eiswein, Malbec/Cot, Viognier, Champagne grape
  trio, Port wine origin, Botrytis cinerea).

### 3. TopTriviaQuestions.com — 10 questions

- **URL:** https://toptriviaquestions.com/wine-quiz-questions-and-answers/
- **License:** Published 2023 wine quiz. Factual content with attribution.
- **Coverage:** Champagne service temp, Bordeaux red grapes, Saint Vincent,
  largest producer (Italy), southern Rhône (Châteauneuf-du-Pape),
  Blanc de Blancs meaning, largest vine area (Spain), grapes/bottle ratio,
  sparkling-wine bubble source, leading wine consumer (USA).
- **Excluded:** Pop-culture and music questions (Cliff Richard's
  "Mistletoe and Wine"; Alder Yarrow's blog Vinography) were dropped as
  off-topic for the wine-knowledge domain.

### 4. Intovino Burgundy wine quiz — 4 questions

- **URL:** https://intovino.com/quiz/burgundy-wine-quiz-full-results/
- **License:** © Intovino Ltd 2026. Factual content with attribution.
- **Coverage:** Côte de Beaune appellations, Cistercian monastic
  influence, Burgundy grapes, Crémant de Bourgogne.
- **Excluded:** A True/False item ("Does Côte Chalonnaise have more
  Grand Crus than Côte de Beaune?") was dropped to keep MC format
  consistent.

### 5. L'Atelier du Vin wine quiz — 2 questions

- **URL:** https://www.atelierduvin.com/en/wine-quiz/
- **License:** © L'Atelier du Vin. Factual content with attribution.
- **Coverage:** Blanc de Noirs definition, basic-flavors-rare-in-wine
  question.
- **Excluded:** Two pop-culture items (James Bond's Dom Pérignon line;
  Louis Pasteur quote) were dropped.

### 6. ProProfs Wine Basics quiz — 5 questions

- **URL:** https://www.proprofs.com/quiz-school/story.php?title=wine-basics
- **License:** © ProProfs.com. Factual content with attribution.
- **Coverage:** Red-wine color source, Chardonnay style, Chianti regional
  red, Rioja regional red, Burgundy regional red.
- **Excluded:** Three-option items (Riesling style, Sauvignon Blanc style)
  were normalised to four-option MC by adding a domain-plausible distractor
  (Pinot Grigio for the Chardonnay item).

### 7. Wikipedia-derived (Team γ-authored) — 45 questions

- **License:** CC-BY-SA-4.0 — facts drawn from publicly available
  Wikipedia article material; phrasings authored by OenoBench Team γ.
- **Coverage:**
  - **Wine regions (15):** Châteauneuf-du-Pape grapes, Mosel, Marlborough,
    Tokaj, Maipo, Mendoza, Stellenbosch, Willamette, Bordeaux 1855
    Premiers Crus count, Loire Sancerre/Pouilly-Fumé, Barolo (Piedmont),
    Rías Baixas, Hermitage, Vinho Verde, Etna DOC.
  - **Grape varieties (12):** Pinot Noir/Burgundy, Gamay/Beaujolais,
    Tannat/Uruguay, Assyrtiko/Santorini, Sauvignon Blanc as Cab Sauv parent,
    Furmint/Tokaji, Grüner Veltliner, Riesling/"Rhine Riesling",
    Aglianico/Campania-Basilicata, Petit Manseng/Jurançon, Syrah/Hermitage,
    Mencía/Bierzo-Ribeira-Sacra.
  - **Viticulture (3):** Phylloxera, leaf pulling, veraison.
  - **Winemaking (7):** Malolactic fermentation, méthode traditionnelle,
    bâtonnage, carbonic maceration, fining, Brix scale, pourriture noble.
  - **Producers (4):** Romanée-Conti, Penfolds Grange, Vega Sicilia,
    Sassicaia.
  - **Wine business (4):** Magnum size, jeroboam (Champagne), En primeur,
    DOCG hierarchy.
- **Authoring methodology:** Stems were written in varied prose styles
  (declarative, "which of these…", "where would you…", "what is the term
  for…", clause-leading "X, often called Y, is…", and so on) to expose
  A4 to a realistic distribution of human authoring voices. Distractors
  are domain-plausible (sister regions, neighboring grapes, alternative
  techniques).

## Retained counts by topic

| Topic            | Count |
| ---------------- | ----: |
| `grape_varieties`|    33 |
| `wine_regions`   |    29 |
| `winemaking`     |    18 |
| `wine_business`  |    15 |
| `viticulture`    |     5 |
| `producers`      |     4 |
| **Total**        | **104** |

## Retained counts by style category

| Style category                                | Count |
| --------------------------------------------- | ----: |
| WSET / regional-knowledge style (AmEx, Intovino, ProProfs, Wikipedia regional/grape) |  ≈ 75 |
| CMS / sommelier-applied style (winemaking & service: TopTriviaQ, Atelier, Wikipedia winemaking) |  ≈ 25 |
| Other community / general (OpenTriviaQA, OpenTrivia trivia history) |  ≈  4 |

The CMS/sommelier "applied" style is intentionally smaller than the spec
target — community sources for genuinely-applied service or tasting MC
content under permissive licensing are scarce. The Wikipedia-authored set
compensates by including method-and-process questions (carbonic
maceration, bâtonnage, MLF, fining) that match the CMS style of testing
service-relevant winemaking knowledge.

## Notes for future revisions

- If A4 v1.2.0 detects too-strong style differences caused by the
  quiz-prose register (which differs from the project's LLM scenario
  prompts that emphasize narrative framing), expand the Wikipedia-authored
  block with longer, scenario-style human stems.
- The Quizlet flashcard sets for WSET/CMS are user-uploaded under
  Quizlet's user-generated-content terms; Quizlet's anti-bot blocks
  prevented automated extraction. A manual, attributed copy-by-hand
  effort to add ≈30 more questions from clearly-permissive Quizlet sets
  could lift the reference set above 130 and improve A4's per-class
  balance.
