# Team β — Scenario closed-book failure mode analysis

Source: audit_pilot_v5 run `541d1d1d-1a89-4f5a-8940-218928da3729`
B2 fails on non-cb-tagged L1/L2 scenario_synthesis questions: 19 (55.9% of all 34 such fails).
All 19 have leakage_ratio = 1.0 (5/5 closed-book judges correct), avg cb_confidence ≈ 0.91.

## Categorization

After reading all 19 failures, the failures cluster into 4 distinct, sometimes overlapping, modes.

### Mode 1 — Premise telegraphs the answer (synonyms/hints inside the stem) — 9 cases

The scenario premise restates or paraphrases the answer directly. The source fact only enriches the premise; the answer is recoverable from the premise alone.

* SCEN_3 ("Georgian heritage bottling"): premise names "amber wine, beeswax-lined large clay container, Georgian wine term". Option B reads back "qvevri-type vessels". Stem == answer.
* SCEN_4 ("Spanish traditional-method sparkling wine"): premise says "stylistic range found in established Spanish traditional-method sparkling wine, bone-dry to sweet". Option D names the Spanish sweetness ladder verbatim.
* SCEN_5 ("organic, isolated, river barriers"): premise contains "natural barriers that restrict the spread of external agricultural threats". Option D restates that.
* SCEN_6 ("continental climate, slope failure, microclimates"): all three constraints repeated in option B.
* SCEN_8 ("South African fortified — added grape spirit"): "raising its alcohol with added grape spirit" → "Classify as fortified" is direct.
* SCEN_10 ("French AOC varietal labeling — German-influenced"): premise names "vin de pays" classification target.
* SCEN_11 ("classified French AOC, terroir trumps grape"): premise hints "vineyard's geographic identity supersedes grape" verbatim in stem.
* SCEN_15 ("northern Chile, structured age-worthy reds, European-trained"): premise spells out "traditional methods... renowned Old World region... climatic similarities".
* SCEN_18 ("Barossa Chardonnay, big creamy"): premise names the target style; option D is canonical Barossa Chardonnay technique.

Evidence: all 9 have judges_keyed=5/5 with confidence ≥ 0.92.

### Mode 2 — Famous-region/canonical-answer cliché — 5 cases

Even with neutral phrasing, the answer is a single canonical fact tied to a region or grape that any wine generalist knows. The source fact is decorative.

* SCEN_1 ("Chile pre-1980s domestic, colonial constraint, flood irrigation"): three separate "common Chilean wine history" facts → option C just restates them as a synthesis. World knowledge enough.
* SCEN_2 ("high-elevation Andean, deep wells, vineyard removed"): "Andean = high altitude" is canonical world knowledge.
* SCEN_7 ("dark-skinned grape Central Europe, late-ripening, spicy, Burgundian comparison"): description matches Blaufränkisch/Pinot Noir cliché.
* SCEN_12 ("Roman 1st century CE German viticulture, climate red-difficult"): well-known historical narrative; option C is the "obvious" interpretation.
* SCEN_16 ("German lowest-tier neutral grapes, Liebfraumilch nostalgia"): canonical Liebfraumilch history.

These don't telegraph the answer in the stem text but stack so much regional flavor that a generalist re-derives the answer from world knowledge alone.

### Mode 3 — Single-canonical-best-practice viticulture/winemaking — 3 cases

The stem describes a generic situation with a single textbook correct technique that any oenology graduate knows by reflex.

* SCEN_9 ("Horse Heaven Hills Grenache, schist/granite, heavily irrigated → reduce irrigation"): "reduce irrigation = better quality" is reflex.
* SCEN_14 ("Argentine Malbec clone for smaller berries / tighter clusters / Argentine selection"): premise literally asks for "Argentine clone developed for Argentina"; option C says "Argentine Malbec clone".
* SCEN_18 ("Barossa Chardonnay big creamy"): also Mode 1; canonical winemaking sequence (barrel ferment + MLF).

The source fact (e.g. specific Argentine clone names, specific ABV thresholds) is not pinned to the answer.

### Mode 4 — Crown-gall / regulatory generic-knowledge problem — 2 cases

Plant-pathology or regulatory questions where the correct answer is the textbook caveat ("certification doesn't fully eliminate the bacterium"), and the source fact merely names the pathogen behind a generic well-known caveat.

* SCEN_13 ("crown-gall-style root tumors, certified shoot-tip culture, infection persistence"): option A is the textbook caveat about Agrobacterium; cb_correct.
* SCEN_19 ("Cape Ruby vs Cape LBV wood maturation"): regulatory category fit; the question reads back the rules.

## Common diagnosis

Across all 4 modes, the failure shape is the same: **the stem encodes enough of the source fact's information that a closed-book judge with general wine knowledge can recover the answer without seeing the source fact at all.**

The current SCENARIO_TEMPLATE has a `QUESTION DESIGN — INFERENCE OVER RECALL` block telling the model not to lead with iconic-entity recall, and an `AVOID WORLD-KNOWLEDGE SOLVABILITY` block. Those address Mode 2 (iconic entities) but **do not** address Mode 1 (premise-leaks-answer) or Modes 3-4 (canonical-best-practice / textbook-caveat).

The crucial missing constraint: the answer must depend on a **non-derivable anchor pulled from the source fact** — a number, year, regulatory threshold, named entity, or attribute value that a generalist could not invent from world knowledge alone. The stem must NOT contain that anchor; the answer must hinge on it.

## Fix direction

Add a HARD RULES — NON-DERIVABLE ANCHOR section to SCENARIO_TEMPLATE. Refuse generation when no such anchor exists. Force a self-check ("could a wine expert with no access to the source fact answer this from world knowledge alone? If yes, REWRITE.").

## Counts vs goal

Current B2 fail rate among non-cb-tagged scenario L1/L2: 19/(19+pass count). Need to drive to ≤15% (B2 v3.1.0 panel-of-5). Prototype target ≤ 20% closed-book solvable on Sonnet 4.6 manual gate.
