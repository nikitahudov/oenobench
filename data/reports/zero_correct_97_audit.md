# Zero-Correct Question Audit — eval_release_v1_2_full

**Run:** 8b0a0864-f3c6-4ec5-8f3d-e30271b8c3a0
**Audited:** 2026-05-04
**Total questions:** 97 (all 16 configs answered, 0 correct)

## Summary

| Category | Count | % |
|---|---:|---:|
| DUP_OPTION | 6 | 6.2% |
| EQUIV_OPTIONS | 2 | 2.1% |
| ALL_CORRECT | 19 | 19.6% |
| WRONG_GROUND_TRUTH | 27 | 27.8% |
| SOURCE_FACT_DUBIOUS | 13 | 13.4% |
| AMBIGUOUS_WORDING | 16 | 16.5% |
| HARD_BUT_FAIR | 14 | 14.4% |
| **Total** | **97** | **100.0%** |

## Recommended drops vs keeps

- **DROP** (real defect — corpus correctness): **54** (DUP_OPTION 6 + EQUIV_OPTIONS 2 + ALL_CORRECT 19 + WRONG_GROUND_TRUTH 27)
- **REVIEW** (judgment call): **29** (SOURCE_FACT_DUBIOUS 13 + AMBIGUOUS_WORDING 16)
- **KEEP** (fair difficulty signal): **14** (HARD_BUT_FAIR 14)

That is **56%** of the 0/16-correct pool flagged as outright corpus defects, another **30%** marked review-worthy, and only **14%** retained as legitimately hard.

## Per-domain defect rate

| Domain | DUP_OPTION | EQUIV_OPTIONS | ALL_CORRECT | WRONG_GROUND_TRUTH | SOURCE_FACT_DUBIOUS | AMBIGUOUS_WORDING | HARD_BUT_FAIR | Total |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| grape_varieties | 0 | 1 | 11 | 11 | 2 | 5 | 2 | 32 |
| producers | 1 | 0 | 2 | 1 | 2 | 2 | 0 | 8 |
| viticulture | 3 | 0 | 0 | 5 | 0 | 1 | 2 | 11 |
| wine_business | 0 | 0 | 1 | 3 | 6 | 0 | 1 | 11 |
| wine_regions | 2 | 1 | 5 | 6 | 3 | 8 | 6 | 31 |
| winemaking | 0 | 0 | 0 | 1 | 0 | 0 | 3 | 4 |

## Detailed findings

### Category: DUP_OPTION (6)

#### qid `0534d251-fd20-4660-b696-7ee652cb12f4` — `wine_regions` / d2 / DUP_OPTION · cb_fail

**Q:** Which Spanish DOP is situated in Castile and León and extends across both the Burgos and Palencia provinces?

- A. Arlanza *(keyed)*
- B. Cigales
- C. Ribera del Duero
- D. Arlanza *(keyed)*

**Keyed:** A,D  
**Model picks:** A=12, C=4  
**Generator/strategy:** chatgpt / fact_to_question  
**Source fact:** Arlanza is a Spanish Denominación de Origen Protegida (DOP) located in the provinces of Burgos and Palencia, Castile and León, Spain.

**Defect:** Options A and D both 'Arlanza'; key 'A,D' but single-letter parser can only pick one.

**Recommended action:** drop

#### qid `11259084-8a23-4019-b3bd-42597dafa512` — `viticulture` / d3 / DUP_OPTION

**Q:** You are comparing vineyard footprint by hectares for two lesser-planted grapes outside their classic strongholds. One has a cited planting figure of 98 hectares in Victoria's King Valley, while the other is described at 994 hectares around Montefalco after expansion. Which grape has the larger planted area in the figures given?

- A. Sagrantino *(keyed)*
- B. Nebbiolo
- C. Nebbiolo
- D. Sagrantino *(keyed)*

**Keyed:** A,D  
**Model picks:** A=12, D=4  
**Generator/strategy:** chatgpt / comparative  
**Source fact:** In Argentina there are 49 hectares (120 acres) planted in the San Juan province and Australian producers in the King Valley region of Victoria have found some success with 98. / Sagrantino is grown primarily in the village of Montefalco and the surrounding area, with a recent rapid increase in planting area from 351 hectares (870 acres) in 2000 to 994.

**Defect:** Options A=D=Sagrantino and B=C=Nebbiolo; duplicates render single-letter parsing impossible.

**Recommended action:** drop

#### qid `2496140e-970b-4f2d-96bd-0eafe2d0050f` — `viticulture` / d3 / DUP_OPTION

**Q:** A vineyard survey lists two plantings: one at 63 hectares and another at 994 hectares. Which grape has the larger recorded planted area in these facts?

- A. Sangiovese
- B. Sagrantino *(keyed)*
- C. Sagrantino *(keyed)*
- D. Sangiovese

**Keyed:** B,C  
**Model picks:** D=7, B=4, A=3, C=2  
**Generator/strategy:** chatgpt / comparative  
**Source fact:** A small amount of Sangiovese is grown in South Africa with 63 hectares (160 acres) reported in 2008, mostly in the Stellenbosch and Darling regions. / Sagrantino: a rare native of Umbria, as of 2010, it is planted on only 994 hectares (2,460 acres).

**Defect:** Options A=D=Sangiovese and B=C=Sagrantino; duplicates.

**Recommended action:** drop

#### qid `503fc08e-93a8-426c-bf0b-64d93a855cdc` — `producers` / d1 / DUP_OPTION · cb_fail

**Q:** Which entity is identified by this clue: in the postwar era it became especially fashionable in both the UK and the US, and its bottle sold at roughly the same level as a second-growth red Bordeaux?

- A. Blue Nun *(keyed)*
- B. Franz Wilhelm Langguth Erben
- C. Franz Wilhelm Langguth Erben
- D. Blue Nun *(keyed)*

**Keyed:** A,D  
**Model picks:** A=16  
**Generator/strategy:** chatgpt / comparative  
**Source fact:** After World War II, the brand became widely popular in the United Kingdom and the United States, selling for the same price as a second growth red Bordeaux wine. / With annual production of about 50 million bottles and sales of about €108 million, Langguth was among the largest wine producers in the country.

**Defect:** Options A=D=Blue Nun and B=C=Langguth; duplicates.

**Recommended action:** drop

#### qid `94ae30dc-a812-485b-a269-40769e31a08c` — `wine_regions` / d2 / DUP_OPTION

**Q:** You are comparing two French appellations for a wine list and want the one with the tighter permitted crop level. Which appellation has the lower maximum authorized yield per hectare?

- A. Chablis Grand Cru *(keyed)*
- B. Chablis Grand Cru *(keyed)*
- C. Beaujolais
- D. Beaujolais

**Keyed:** A,B  
**Model picks:** A=16  
**Generator/strategy:** chatgpt / comparative  
**Source fact:** The maximum yield for Beaujolais AOC is 60 hl/ha. / The maximum yield for Chablis Grand Cru AOC is 54 hl/ha.

**Defect:** Options A=B=Chablis Grand Cru and C=D=Beaujolais; duplicates.

**Recommended action:** drop

#### qid `d45783af-c47b-4995-8c46-7c0e6cd00411` — `viticulture` / d3 / DUP_OPTION

**Q:** One of these AVAs has about 6,800 acres under vine, while the other has roughly 1,850 acres planted. Which appellation has the greater planted vineyard area?

- A. Santa Lucia Highlands AVA
- B. St. Helena AVA *(keyed)*
- C. St. Helena AVA *(keyed)*
- D. Santa Lucia Highlands AVA

**Keyed:** B,C  
**Model picks:** A=12, D=3, B=1  
**Generator/strategy:** chatgpt / comparative  
**Source fact:** St. Helena AVA is a sub-appellation within the larger, previously established Napa Valley viticultural area and is densely planted with 6,800 acres (2,800 ha) of vines sourcing 93 wineries. / Inititially, the total area of the appellation was approximately 22,000 acres (34 sq mi) with 1,850 acres (749 ha) committed to active viticulture.

**Defect:** Options A=D=Santa Lucia Highlands and B=C=St. Helena; duplicates.

**Recommended action:** drop

### Category: EQUIV_OPTIONS (2)

#### qid `0c984c8f-44c6-47c6-b520-9ec2fd156952` — `grape_varieties` / d2 / EQUIV_OPTIONS

**Q:** In which Slovenian wine region is Pinot Noir particularly produced?

- A. Posavje
- B. Podravje
- C. Primorska
- D. Slovenian Littoral *(keyed)*

**Keyed:** D  
**Model picks:** C=11, B=4, A=1  
**Generator/strategy:** llama / fact_to_question  
**Source fact:** === Slovenia ===
In Slovenia, the Pinot noir is produced especially in the Slovenian Littoral, particularly in the Goriška Brda sub-region.

**Defect:** Primorska (C) is the Slovenian-language name for the Slovenian Littoral (D); 11 models picked the synonym C.

**Recommended action:** drop

#### qid `344b6435-250a-4cac-a91f-443d3d51134f` — `wine_regions` / d2 / EQUIV_OPTIONS

**Q:** Which Italian wine denomination lies across the border from Slovenia's Brda district in Friuli-Venezia Giulia?

- A. Collio Goriziano DOC
- B. Gorizia Hills DOC *(keyed)*
- C. Colli Orientali del Friuli DOC
- D. Carso DOC

**Keyed:** B  
**Model picks:** A=16  
**Generator/strategy:** chatgpt / fact_to_question  
**Source fact:** The Brda district borders the Italian wine region of Friuli-Venezia Giulia with the Gorizia Hills Denominazione di origine controllata (DOC).

**Defect:** Gorizia Hills DOC and Collio Goriziano DOC are the same appellation (English vs Italian name); 16/16 picked Collio Goriziano.

**Recommended action:** drop

### Category: ALL_CORRECT (19)

#### qid `0d5660e2-875e-4167-a27d-eedbfd37be7a` — `wine_business` / d2 / ALL_CORRECT

**Q:** Which Portuguese wine region holds the country's top wine status, the Denominação de Origem Controlada (DOC)?

- A. Dão
- B. Colares
- C. Bucelas *(keyed)*
- D. Bairrada

**Keyed:** C  
**Model picks:** A=15, B=1  
**Generator/strategy:** chatgpt / fact_to_question  
**Source fact:** Bucelas DOC has Portugal's highest wine classification as a Denominação de Origem Controlada (DOC).

**Defect:** Dão, Colares, Bucelas, and Bairrada are all Portuguese DOCs; the question has four correct answers.

**Recommended action:** drop

#### qid `0d908a02-7eb6-4c12-b307-5c587a7a829c` — `producers` / d2 / ALL_CORRECT

**Q:** Which winery is identified as making traditional-method bubbly in England?

- A. Squerryes Estate *(keyed)*
- B. Nyetimber
- C. Ridgeview
- D. Gusbourne

**Keyed:** A  
**Model picks:** B=12, C=3, D=1  
**Generator/strategy:** chatgpt / fact_to_question  
**Source fact:** Squerryes Estate is a producer of English sparkling wine.

**Defect:** Nyetimber, Ridgeview, and Gusbourne are all famous English traditional-method sparkling producers; multiple correct.

**Recommended action:** drop

#### qid `1475af73-4526-4236-95f3-a2263a4c4e5e` — `grape_varieties` / d3 / ALL_CORRECT

**Q:** Which grape variety is permitted in the Willow Creek AVA?

- A. Pinot noir
- B. Cabernet Sauvignon
- C. Malbec *(keyed)*
- D. Chardonnay

**Keyed:** C  
**Model picks:** A=10, B=5, D=1  
**Generator/strategy:** llama / comparative  
**Source fact:** Willow Creek AVA permits the Malbec grape variety. / Napa Valley AVA permits the Pinot noir grape variety.

**Defect:** Willow Creek District AVA permits Pinot noir, Cab Sauv, Chardonnay, and Malbec; all four options are permitted.

**Recommended action:** drop

#### qid `16fa4ec8-f41e-4adc-8184-cd0fc3a75d30` — `wine_regions` / d2 / ALL_CORRECT

**Q:** Which of the following is classified as a French AOC appellation?

- A. Meursault premier cru Les Perrières
- B. Pommard premier cru Les Rugiens
- C. Volnay premier cru Clos des Chênes
- D. Monthélie premier cru Le Cas Rougeot *(keyed)*

**Keyed:** D  
**Model picks:** A=10, B=3, null=3  
**Generator/strategy:** chatgpt / fact_to_question  
**Source fact:** Monthélie premier cru Le Cas Rougeot is an AOC appellation in France.

**Defect:** All four options (Meursault, Pommard, Volnay, Monthélie premier crus) are AOC appellations.

**Recommended action:** drop

#### qid `28755dfa-f2ee-4ce8-8ab2-7f9ed8225e16` — `grape_varieties` / d3 / ALL_CORRECT

**Q:** Which white grape variety is used to produce a Portuguese wine?

- A. Tamarez *(keyed)*
- B. Donzelinho branco
- C. Rabo de Ovelha
- D. Aragonez

**Keyed:** A  
**Model picks:** B=11, C=4, null=1  
**Generator/strategy:** llama / distractor_mining  
**Source fact:** Açores VR permits the Aragonez (Tinta Roriz) grape variety. / Rabo de Ovelha is an authorized grape variety in the Bairrada, Borba, Bucelas, Redondo, Reguengos, Setúbal and Vidigueira Denominação de Origem Controlada (DOC). / To prevent the wine from spoiling, the local vintners began adding neutral grape spirits. / Located in the southern half of the Ribatejo region, vineyards are planted on sandy plains and relay on irrigation to sustain the vines. / Donzelinho branco is one of the authorized grape permitted to be blended in the wines of Duriense. / Tamarez is a white grape variety that is t…

**Defect:** Donzelinho Branco and Rabo de Ovelha are also Portuguese white grapes used in Portuguese wines; multiple correct answers.

**Recommended action:** drop

#### qid `35806e9e-674c-4149-9b95-71626baaf8ec` — `grape_varieties` / d2 / ALL_CORRECT

**Q:** Which grape variety is permitted in the Clear Lake AVA in California?

- A. Syrah
- B. Cabernet Franc *(keyed)*
- C. Chardonnay
- D. Cinsault

**Keyed:** B  
**Model picks:** C=14, A=2  
**Generator/strategy:** llama / comparative  
**Source fact:** Clear Lake AVA permits the Cabernet Franc grape variety. / High Valley AVA permits the Cinsault grape variety.

**Defect:** Clear Lake AVA permits Chardonnay, Syrah, Cabernet Franc; all options are permitted varieties.

**Recommended action:** drop

#### qid `4f871f97-625a-4dd8-a935-de885b3a8727` — `grape_varieties` / d2 / ALL_CORRECT

**Q:** Which of the following grape varieties is permitted for use in wines produced within the San Antonio Valley AVA?

- A. Marsanne *(keyed)*
- B. Viognier
- C. Roussanne
- D. Grenache Blanc

**Keyed:** A  
**Model picks:** B=10, D=3, C=2, null=1  
**Generator/strategy:** qwen / fact_to_question  
**Source fact:** San Antonio Valley AVA permits the Marsanne grape variety.

**Defect:** San Antonio Valley AVA permits all four Rhône whites listed (Marsanne, Viognier, Roussanne, Grenache Blanc).

**Recommended action:** drop

#### qid `5e3d591c-ef02-46e5-b3bb-b7a34e887a45` — `grape_varieties` / d3 / ALL_CORRECT

**Q:** Which Australian wine region permits the production of Cabernet Sauvignon wines?

- A. Margaret River
- B. Barossa Valley
- C. Mudgee
- D. Kangaroo Island *(keyed)*

**Keyed:** D  
**Model picks:** A=16  
**Generator/strategy:** llama / comparative  
**Source fact:** Kangaroo Island wine region permits the | varietals = Cabernet Sauvignon grape variety. / Mudgee wine region permits the | varietals =Shiraz grape variety.

**Defect:** All four Australian regions listed permit Cabernet Sauvignon (it's grown nationwide).

**Recommended action:** drop

#### qid `6682ceb8-ce25-4655-8de0-3525139078c9` — `wine_regions` / d3 / ALL_CORRECT

**Q:** This American Viticultural Area is a sub-appellation nested entirely within the Sonoma Coast AVA. Which AVA is being described?

- A. Petaluma Gap
- B. Fort Ross-Seaview
- C. Green Valley of Russian River Valley
- D. Sonoma County Green Valley *(keyed)*

**Keyed:** D  
**Model picks:** B=14, C=1, A=1  
**Generator/strategy:** claude / comparative  
**Source fact:** Sonoma County Green Valley AVA is located within the Sonoma Coast AVA. / Columbia Valley AVA contains the Snipes Mountain AVA.

**Defect:** Fort Ross-Seaview AVA is also entirely nested within Sonoma Coast AVA; question has multiple correct answers.

**Recommended action:** drop

#### qid `694975b6-afc6-426c-b6eb-e330d3c5dcf9` — `grape_varieties` / d3 / ALL_CORRECT

**Q:** Which grape variety is permitted in the McLaren Vale wine region?

- A. Grenache
- B. Syrah
- C. Merlot
- D. Cabernet Sauvignon *(keyed)*

**Keyed:** D  
**Model picks:** A=11, B=5  
**Generator/strategy:** llama / distractor_mining  
**Source fact:** Grenache is the dominant variety in most Southern Rhône wines, especially in Châteauneuf-du-Pape. / === France ===

In France, Grenache is most widely associated with the wines of the Rhône and southern France. / McLaren Vale permits the Cabernet Sauvignon grape variety. / Marginal and wet climates can increase Grenache's propensity to develop these viticultural dangers. / As a blending component, Grenache is valued for the added body and fruitiness that it brings without added tannins.

**Defect:** All four (Grenache, Shiraz, Merlot, Cab Sauv) are permitted and widely grown in McLaren Vale.

**Recommended action:** drop

#### qid `75a54567-cd9f-4503-bd61-22cb1cde047b` — `grape_varieties` / d2 / ALL_CORRECT

**Q:** Which grape variety is permitted in the Borden Ranch AVA?

- A. Vermentino
- B. Albariño
- C. Verdejo
- D. Garnacha Blanca *(keyed)*

**Keyed:** D  
**Model picks:** B=9, A=6, C=1  
**Generator/strategy:** llama / fact_to_question  
**Source fact:** Borden Ranch AVA permits the Garnacha Blanca grape variety.

**Defect:** Borden Ranch AVA permits Vermentino, Albariño, Verdejo, and Garnacha Blanca; all four valid.

**Recommended action:** drop

#### qid `a56aa874-7670-417e-90fa-10febc118887` — `grape_varieties` / d4 / ALL_CORRECT

**Q:** Which grape variety was bred at the experimental viticulture institute in Conegliano, located in Veneto in northeastern Italy, and only gradually became more widely planted after its introduction?

- A. Raboso
- B. Glera
- C. Incrocio Manzoni
- D. Vega *(keyed)*

**Keyed:** D  
**Model picks:** C=14, null=1, B=1  
**Generator/strategy:** chatgpt / fact_to_question  
**Source fact:** Developed at the Istituto Sperimentale per la Viticoltura of Conegliano in the Veneto wine region of northeast Italy, the grape has slowly spread since its release.

**Defect:** Incrocio Manzoni is the famously Conegliano-bred grape (e.g., Manzoni Bianco 6.0.13); Vega is far less canonical.

**Recommended action:** drop

#### qid `c4e8d418-83ed-487b-9c80-e7dcade12269` — `grape_varieties` / d2 / ALL_CORRECT

**Q:** A US winemaker wants to create a new white blend and is considering which grape varieties to use. They want to include Chardonnay for its broad consumer appeal. Which additional varieties are approved for use on US wine labels and could be blended with Chardonnay?

- A. Vermentino and Verdejo
- B. Albariño and Grüner Veltliner
- C. Sauvignon Blanc and Sémillon
- D. Picpoul Blanc and Ribolla Gialla *(keyed)*

**Keyed:** D  
**Model picks:** C=15, null=1  
**Generator/strategy:** llama / scenario_synthesis  
**Source fact:** Picpoul Blanc is an approved grape variety name for use on US wine labels per TTB regulations. / Ribolla Gialla is an approved grape variety name for use on US wine labels per TTB regulations. / Chardonnay is an approved grape variety name for use on US wine labels per TTB regulations.

**Defect:** Sauvignon Blanc, Sémillon, Albariño, Grüner Veltliner, Vermentino, Verdejo, Picpoul Blanc, Ribolla Gialla are ALL TTB-approved varieties for US white blends.

**Recommended action:** drop

#### qid `d320c6bc-8343-4681-849b-b176c21a6191` — `grape_varieties` / d2 / ALL_CORRECT

**Q:** According to U.S. regulatory standards for wine labeling, which of the following synonyms is officially permitted for use in place of 'Chasselas' on a wine label?

- A. Gutedel
- B. Chasselas doré *(keyed)*
- C. Fendant
- D. Doré de Chasselas

**Keyed:** B  
**Model picks:** A=11, C=4, null=1  
**Generator/strategy:** qwen / fact_to_question  
**Source fact:** Chasselas doré is an approved synonym for Chasselas Doré on US wine labels.

**Defect:** Gutedel (German) and Fendant (Swiss) are also widely recognized Chasselas synonyms; multiple options valid.

**Recommended action:** drop

#### qid `d5ac3c08-732a-4d0c-a293-1ca3465f846d` — `wine_regions` / d4 / ALL_CORRECT

**Q:** Which French wine designation is specifically classified as an AOC appellation?

- A. Mâcon-Villages
- B. Montagny premier cru Vignes sur le Cloux *(keyed)*
- C. Viré-Clessé
- D. Pouilly-Fuissé premier cru

**Keyed:** B  
**Model picks:** C=8, A=5, null=2, D=1  
**Generator/strategy:** chatgpt / fact_to_question  
**Source fact:** Montagny premier cru Vignes sur le Cloux is an AOC appellation in France.

**Defect:** Mâcon-Villages, Viré-Clessé, and Pouilly-Fuissé premier cru are all also AOCs.

**Recommended action:** drop

#### qid `d6dce0f1-1210-4526-ba49-f17e1b15ffb5` — `producers` / d4 / ALL_CORRECT

**Q:** Which winery produces a Cabernet Sauvignon under their own name?

- A. Robert Mondavi Winery
- B. Château Margaux
- C. Penfolds
- D. Page Mill Winery *(keyed)*

**Keyed:** D  
**Model picks:** A=15, null=1  
**Generator/strategy:** llama / fact_to_question  
**Source fact:** Page Mill Winery Cabernet Sauvignon is made by Page Mill Winery.

**Defect:** Robert Mondavi, Penfolds, and Château Margaux all produce Cabernet Sauvignon under their own labels.

**Recommended action:** drop

#### qid `eacfc31a-5415-4868-bf7b-9696e990ac56` — `wine_regions` / d2 / ALL_CORRECT

**Q:** Which of the following is an AOC appellation in the Chambolle-Musigny region of France?

- A. Les Amoureuses
- B. Aux Echanges *(keyed)*
- C. Les Charmes
- D. Clos de Vougeot

**Keyed:** B  
**Model picks:** A=12, D=3, null=1  
**Generator/strategy:** llama / fact_to_question  
**Source fact:** Chambolle-Musigny premier cru Aux Echanges is an AOC appellation in France.

**Defect:** Les Amoureuses, Aux Echanges, Les Charmes are all Chambolle-Musigny premier cru AOCs; Clos de Vougeot is also AOC. All four valid.

**Recommended action:** drop

#### qid `f2e364d7-edf0-4466-a929-beb7d48f15d4` — `wine_regions` / d2 / ALL_CORRECT

**Q:** Which of the following is a white wine appellation in France that holds AOC status?

- A. Coteaux du Layon
- B. Gaillac blanc *(keyed)*
- C. Mâcon-Villages
- D. Côtes de Provence

**Keyed:** B  
**Model picks:** C=13, null=2, A=1  
**Generator/strategy:** qwen / fact_to_question  
**Source fact:** Gaillac blanc is an AOC appellation in France.

**Defect:** Coteaux du Layon, Gaillac blanc, Mâcon-Villages, Côtes de Provence — all four are AOCs and all produce white wines.

**Recommended action:** drop

#### qid `f7ffd486-b21b-4453-a3fc-e678a6136e50` — `grape_varieties` / d3 / ALL_CORRECT

**Q:** Which grape variety is permitted for use in the late harvest wines of Alsace Grand Cru AOC, including Vendange Tardive and Sélection de Grains Nobles?

- A. Gewürztraminer
- B. Riesling
- C. Spätburgunder
- D. Grauburgunder *(keyed)*

**Keyed:** D  
**Model picks:** A=11, B=3, null=2  
**Generator/strategy:** llama / comparative  
**Source fact:** === Chile ===

Pinot noir is produced at the Leyda Valley, one of the minor wine districts of the Aconcagua wine region of Chile and in the southern district Biobio. / Grauburgunder may be used for varietal Alsace Grand Cru AOC and the late harvest wines Vendange Tardive and Sélection de Grains Nobles.

**Defect:** Alsace Grand Cru VT/SGN allows Riesling, Gewürztraminer, Pinot Gris, AND Muscat. Three of the four options listed are valid noble varieties.

**Recommended action:** drop

### Category: WRONG_GROUND_TRUTH (27)

#### qid `06dcf574-85c6-42ad-924e-5a7f33115e13` — `winemaking` / d2 / WRONG_GROUND_TRUTH

**Q:** Within what range does the typical alcohol content of red wines fall?

- A. 12.5% to 15.5%
- B. 18.5% to 21.5%
- C. 15.5% to 18.5%
- D. 9.2% to 12.5% *(keyed)*

**Keyed:** D  
**Model picks:** A=16  
**Generator/strategy:** llama / fact_to_question  
**Source fact:** Red wines typically have an alcohol content between 9.2% and 12.5% by volume.

**Defect:** Typical red wine ABV is 12-15%, not 9.2-12.5%. Source fact is wrong; all 16 models picked the consensus-correct 12.5-15.5% range.

**Recommended action:** drop

#### qid `12ccc0a7-dbe6-49b6-8154-db8acf087629` — `wine_business` / d2 / WRONG_GROUND_TRUTH

**Q:** What is the minimum alcohol level required for the lowest level of the German wine classification system?

- A. 12.5%
- B. 10.5%
- C. 9.5%
- D. 11.5% *(keyed)*

**Keyed:** D  
**Model picks:** C=8, A=3, null=3, B=2  
**Generator/strategy:** llama / fact_to_question  
**Source fact:** German wine classification the minimum level is 11.5%.

**Defect:** Lowest German classification (Deutscher Wein) minimum ABV is 8.5%, not 11.5%; source fact is incorrect.

**Recommended action:** drop

#### qid `2ba023f4-220c-43dd-9b85-b12cfc7f6e60` — `grape_varieties` / d3 / WRONG_GROUND_TRUTH

**Q:** Which of these American Viticultural Areas includes Carignane among its approved grape varieties for wine production?

- A. Chalone AVA
- B. Redwood Valley AVA
- C. Mendocino AVA
- D. Gabilan Mountains AVA *(keyed)*

**Keyed:** D  
**Model picks:** B=13, C=3  
**Generator/strategy:** qwen / comparative  
**Source fact:** Redwood Valley AVA permits the Barbera grape variety. / Gabilan Mountains AVA permits the Carignane grape variety.

**Defect:** Mendocino AVA is the canonical Carignane region (old-vine Carignane); the keyed Gabilan Mountains is only one of several permitting AVAs.

**Recommended action:** drop

#### qid `2f391a19-9369-402b-91f4-4fafaa144d9a` — `viticulture` / d2 / WRONG_GROUND_TRUTH

**Q:** Which Australian wine region was first planted in the late 1850s and remained free from phylloxera during the widespread epidemic of the 19th century?

- A. South Australia
- B. Western Australia
- C. New South Wales *(keyed)*
- D. Victoria

**Keyed:** C  
**Model picks:** A=10, B=6  
**Generator/strategy:** qwen / fact_to_question  
**Source fact:** New South Wales wine was first planted in 1858 and was never affected by the phylloxera epidemic that hit Australia in the late 19th century.

**Defect:** South Australia is the famously phylloxera-free state; NSW had outbreaks. Source fact contradicts standard wine knowledge.

**Recommended action:** drop

#### qid `36b14441-47b7-44ca-b48e-559daf775588` — `viticulture` / d2 / WRONG_GROUND_TRUTH

**Q:** During the two decades following 1960, which white grape variety expanded significantly to represent 30 percent of German vineyards and 25 percent of the planted acreage in Alsace?

- A. Müller-Thurgau
- B. Riesling
- C. Sylvaner *(keyed)*
- D. Gewürztraminer

**Keyed:** C  
**Model picks:** A=15, null=1  
**Generator/strategy:** gemini / fact_to_question  
**Source fact:** Sylvaner was planted widely in Germany and Alsace after the Second World War, reaching 30% and 25% respectively of total vineyard area in the 1960s - 1970s.

**Defect:** Müller-Thurgau hit ~30% of German vineyards by the late 1970s; Sylvaner peaked earlier and declined. Source fact contradicts standard data.

**Recommended action:** drop

#### qid `6641f0ca-b7fd-4f67-bc1b-e1e03f908892` — `grape_varieties` / d3 / WRONG_GROUND_TRUTH

**Q:** Which of these grape varieties is classified as a white variety, despite having a name that does not include a color descriptor commonly associated with white grapes?

- A. Flame Seedless
- B. Concord Seedless
- C. Seedless Tokay *(keyed)*
- D. Thompson Seedless

**Keyed:** C  
**Model picks:** D=15, A=1  
**Generator/strategy:** qwen / comparative  
**Source fact:** Seedless Tokay is a white grape variety according to UC Davis FPS. / Concord Seedless is a black grape variety according to UC Davis FPS.

**Defect:** Thompson Seedless is canonically a white grape (Sultana); Seedless Tokay is obscure. 15/16 picked Thompson which is also correct.

**Recommended action:** drop

#### qid `72361da1-7bfe-427c-8fe5-65fcc4aa3945` — `grape_varieties` / d3 / WRONG_GROUND_TRUTH

**Q:** Which grape variety is characterized by early budbreak and thrives in arid conditions with abundant sunlight, making it well-suited to regions where moisture is limited and consistent warmth supports full ripening?

- A. Primitivo
- B. Sangiovese
- C. Aglianico *(keyed)*
- D. Nero d'Avola

**Keyed:** C  
**Model picks:** A=9, D=7  
**Generator/strategy:** qwen / comparative  
**Source fact:** == Viticulture and winemaking ==
Zinfandel vines are quite vigorous and grow best in warm but not too hot climates because grapes may shrivel in hot weather. / == Viticulture ==
The Aglianico vine buds early and grows best in dry climates with generous amounts of sunshine.

**Defect:** Aglianico is canonically a LATE-budbreak, late-ripening variety; consensus contradicts the keyed claim.

**Recommended action:** drop

#### qid `75f38ade-de59-478b-a3ad-c3cc0d296490` — `grape_varieties` / d4 / WRONG_GROUND_TRUTH

**Q:** A domestic wine producer in California is finalizing the packaging for an experimental series of single-varietal bottlings. The marketing department submits three front label drafts to the winery's compliance director. The drafts prominently feature the following text to identify the grapes used: "100% Marsala", "100% Criolla Grande", and "100% Tinta Amarela". The compliance director consults federal labeling codes regarding permissible varietal terminology. Based on federal regulations, what must the compliance director conclude about these proposed varietal designations?

- A. All three terms are legally authorized to be printed as grape identities on domestic packaging. *(keyed)*
- B. None of the terms are authorized; they must be substituted with their federally mandated synonyms.
- C. Only Tinta Amarela is authorized; the other two must be legally declared as proprietary red blends.
- D. Only Criolla Grande and Tinta Amarela are authorized; Marsala is strictly regulated as a geographic class and cannot denote a grape.

**Keyed:** A  
**Model picks:** D=14, B=1, null=1  
**Generator/strategy:** gemini / scenario_synthesis  
**Source fact:** Criolla Grande is an approved grape variety name for use on US wine labels per TTB regulations. / Tinta Amarela is an approved grape variety name for use on US wine labels per TTB regulations. / Marsala is an approved grape variety name for use on US wine labels per TTB regulations.

**Defect:** Marsala is a fortified-wine class, not a TTB-approved varietal name; only Criolla Grande and Tinta Amarela are authorized. Models' D answer is correct.

**Recommended action:** drop

#### qid `8483254a-b089-430d-b53a-452123690cb4` — `wine_business` / d4 / WRONG_GROUND_TRUTH

**Q:** Which Canadian wine style is known for its ice wines that frequently win international competitions and are a successful export product?

- A. Niagara Peninsula ice wines
- B. Adhémar de Chaunac ice wines *(keyed)*
- C. British Columbia ice wines
- D. Okanagan Valley ice wines

**Keyed:** B  
**Model picks:** A=15, D=1  
**Generator/strategy:** llama / distractor_mining  
**Source fact:** More recently, the British Columbia Wine Authority was formed by the provincial government to regulate part of the industry. / Adhémar de Chaunac ice wines which are a successful export product and routinely win international competitions. / The Okanagan wine industry has been developed to include dining experiences for pairing wine with farm-to-plate foods. / Okanagan Valley (wine region) are second in economic importance for wine production to the Niagara Peninsula of Ontario.

**Defect:** 'Adhémar de Chaunac' is a grape variety, not a Canadian ice wine style. Niagara Peninsula icewines is the canonical answer (15/16 models picked).

**Recommended action:** drop

#### qid `92bfcb62-47ea-4c00-9b48-3fd30abbee98` — `wine_business` / d2 / WRONG_GROUND_TRUTH

**Q:** Which of the following wine designations is considered to fall entirely beyond the regulatory framework of Germany's national viticultural statutes?

- A. Deutscher Wein
- B. Qualitätswein bestimmter Anbaugebiete *(keyed)*
- C. Prädikatswein
- D. Landwein

**Keyed:** B  
**Model picks:** A=11, D=4, null=1  
**Generator/strategy:** gemini / fact_to_question  
**Source fact:** Qualitätswein bestimmter Anbaugebiete are outside the scope of the German wine law.

**Defect:** Qualitätswein b.A. is one of the central pillars of the German Wine Law (Weingesetz), not outside it. Source fact misreads context.

**Recommended action:** drop

#### qid `964b3ed0-4402-46fb-9ff6-f24f3ed91d12` — `grape_varieties` / d2 / WRONG_GROUND_TRUTH

**Q:** In Barsac AOC, which grape is specifically noted as being used when it has been altered by Botrytis cinerea, the fungus responsible for noble rot?

- A. Ugni Blanc
- B. Sauvignon Blanc
- C. Sémillon
- D. Muscadelle *(keyed)*

**Keyed:** D  
**Model picks:** C=16  
**Generator/strategy:** chatgpt / fact_to_question  
**Source fact:** Barsac AOC muscadelle grapes that have been affected by Botrytis cinerea, also known as noble rot.

**Defect:** Sémillon is the primary Botrytis-affected grape in Barsac/Sauternes; Muscadelle is a minor blender. Models' Sémillon answer is correct.

**Recommended action:** drop

#### qid `96819afa-680f-4294-88a2-e44080687c5d` — `grape_varieties` / d2 / WRONG_GROUND_TRUTH

**Q:** Which of the following grape varieties is NOT commonly used in South African Wine of Origin wines?

- A. Cabernet Sauvignon *(keyed)*
- B. Shiraz
- C. Pinotage
- D. Tinta Barroca

**Keyed:** A  
**Model picks:** D=15, C=1  
**Generator/strategy:** llama / fact_to_question  
**Source fact:** Wine of Origin wines are made from a variety of grapes, including Shiraz and Pinotage, as well as Portuguese varieties such as Tinta Barroca, Touriga Nacional, Souzão.

**Defect:** Cabernet Sauvignon is widely used in South African WO wines; absence from one source list does not mean 'not commonly used'.

**Recommended action:** drop

#### qid `970d5e12-12cf-4f05-863a-f86559bb66fa` — `producers` / d3 / WRONG_GROUND_TRUTH

**Q:** An Israeli winemaker is considering expanding their operations to either the Golan Heights or the West Bank. They are looking for an area with a well-established wine industry and a significant number of existing wineries to potentially collaborate with. Which region should they choose?

- A. West Bank *(keyed)*
- B. Judean Hills
- C. Galilee
- D. Golan Heights

**Keyed:** A  
**Model picks:** D=15, C=1  
**Generator/strategy:** llama / scenario_synthesis  
**Source fact:** Kim Marcus, managing editor of Wine Spectator magazine, was not impressed by Israel's wineries in the 1990s, but in 2008, he wrote that quality had improved immensely. / There are seven Israeli wineries in the Golan Heights that cultivate a total of 1,600 acres (647 ha). / By 2011 it was estimated that the West Bank had 29 wineries run by Israeli entrepreneurs, as opposed to 14 in the Golan Heights.

**Defect:** Golan Heights is the more established Israeli wine region (7 wineries cited in the fact!); West Bank is not. Key contradicts source fact.

**Recommended action:** drop

#### qid `996024ac-a9af-4180-aeba-e60241a98e77` — `wine_regions` / d2 / WRONG_GROUND_TRUTH

**Q:** Which diminutive Hungarian appellation is recognized as the most prominent growing area for Hárslevelű, a variety originating from the Carpathian Basin?

- A. Somló *(keyed)*
- B. Tokaj
- C. Eger
- D. Badacsony

**Keyed:** A  
**Model picks:** B=15, null=1  
**Generator/strategy:** gemini / fact_to_question  
**Source fact:** Hárslevelű is native to the Carpathian Basin and is planted in several Hungarian wine regions, but most prominently in the tiny wine region of Somló.

**Defect:** Hárslevelű is most associated with Tokaj (where it's a key Tokaji aszú grape), not Somló. Source fact contradicts wine consensus.

**Recommended action:** drop

#### qid `99923e63-5fbb-49bb-92bf-3250def7ed67` — `wine_regions` / d2 / WRONG_GROUND_TRUTH

**Q:** The Slovenian wine region of Goriška Brda sits directly adjacent to which Italian DOC across the border?

- A. Isonzo del Friuli
- B. Collio Goriziano
- C. Colli Orientali del Friuli *(keyed)*
- D. Carso

**Keyed:** C  
**Model picks:** B=15, null=1  
**Generator/strategy:** claude / fact_to_question  
**Source fact:** Goriška Brda borders the Colli Orientali del Friuli DOC, to the Slovene border on the east.

**Defect:** Goriška Brda borders Collio Goriziano DOC (same hills, different name across the border). Colli Orientali del Friuli is to the west and doesn't share the border.

**Recommended action:** drop

#### qid `a557cf20-93be-498e-9d58-937234d01f2b` — `grape_varieties` / d2 / WRONG_GROUND_TRUTH

**Q:** Which grape cultivar, derived from Vitis labrusca and commonly known as 'Fox grape', is utilized both for table consumption and winemaking in the United States?

- A. Concord
- B. Catawba
- C. Delaware *(keyed)*
- D. Niagara

**Keyed:** C  
**Model picks:** A=15, null=1  
**Generator/strategy:** qwen / fact_to_question  
**Source fact:** The Delaware grape is a cultivar derived from the grape species Vitis labrusca or 'Fox grape' which is used for the table and wine production.

**Defect:** Concord is the canonical Vitis labrusca 'Fox grape' for table and wine; Delaware is actually a complex hybrid, not pure labrusca.

**Recommended action:** drop

#### qid `a7b161b8-6801-4b85-9ccd-a5e3bf903383` — `grape_varieties` / d3 / WRONG_GROUND_TRUTH

**Q:** Which grape variety is permitted in the Nashoba Valley AVA but not in Monterey County?

- A. Sauvignon Blanc
- B. Chardonnay *(keyed)*
- C. Albarino
- D. Pinot Noir

**Keyed:** B  
**Model picks:** C=14, A=2  
**Generator/strategy:** llama / comparative  
**Source fact:** Nashoba Valley AVA permits the Chardonnay grape variety. / Monterey County wine permits the Albarino grape variety.

**Defect:** Chardonnay is widely permitted/grown in Monterey County (its top white). The 'not in Monterey' premise is false.

**Recommended action:** drop

#### qid `aeb75a54-5a43-452c-bb45-8ea41d045f47` — `wine_regions` / d4 / WRONG_GROUND_TRUTH

**Q:** Within U.S. wine tax rules, the excise charge is determined using which measurement, alongside a separate 2% wholesale occupational levy?

- A. Residual sugar level
- B. Alcohol by weight (ABW) *(keyed)*
- C. Alcohol by volume (ABV)
- D. Titratable acidity

**Keyed:** B  
**Model picks:** C=16  
**Generator/strategy:** chatgpt / fact_to_question  
**Source fact:** Additional 2% occupational wholesale tax Excise tax rates are based on Alcohol By Weight (ABW)

**Defect:** US federal wine excise tax is determined by ABV, not ABW. Models' ABV answer is correct.

**Recommended action:** drop

#### qid `c5c97ee4-c8d7-4141-911a-6b45336131fa` — `viticulture` / d4 / WRONG_GROUND_TRUTH

**Q:** A vineyard manager in the San Joaquin Valley has noticed an increasing number of grape mealybug infestations in recent years. They are considering postharvest treatments to control the population. However, they have also heard that natural predators can help keep mealybug numbers down. What should the vineyard manager do to effectively manage the mealybug infestation?

- A. Use insecticides to control the infestation, as postharvest treatments are ineffective *(keyed)*
- B. Introduce parasites and predators to control the mealybug population
- C. Do nothing, as the infestation will likely resolve itself over time
- D. Apply postharvest treatments immediately to eliminate the mealybugs

**Keyed:** A  
**Model picks:** B=16  
**Generator/strategy:** llama / scenario_synthesis  
**Source fact:** Postharvest Treatments Postharvest treatments are not effective against Pseudococcus mealybugs because the majority of the population is in the egg stage under the bark and not vulnerable to foliar treatments at this time. / Damage In recent years there have been increases in the number of grape mealybug infestations in the San Joaquin Valley and North Coast and an increase in the incidence of obscure and longtailed mealybugs in Central Coast vineyards. / Once established, parasites and predators can help keep populations down, but an infestation may slowly spread unless controlled with insect…

**Defect:** The fact states postharvest treatments are NOT effective, so option A's 'use insecticides because postharvest treatments are ineffective' is internally contradictory; introducing predators (B) is standard IPM. Models' B answer is correct.

**Recommended action:** drop

#### qid `caa19e44-4101-4fca-99b3-e01ff3f85ac5` — `wine_regions` / d2 / WRONG_GROUND_TRUTH

**Q:** When sugar accumulation reaches 23 degrees Brix—a point generally viewed as standard ripeness for red wine production—which specific fruit characteristic typically emerges?

- A. Strawberry *(keyed)*
- B. Blackberry
- C. Black pepper
- D. Green bell pepper

**Keyed:** A  
**Model picks:** B=14, null=1, C=1  
**Generator/strategy:** gemini / fact_to_question  
**Source fact:** At 23°Bx (the degree that most red wine is considered "ripe"), strawberry flavors develop.

**Defect:** At 23 Brix (full ripeness), red wines develop darker fruit notes (blackberry); strawberry is lighter/lower-Brix. Source fact contradicts winemaking pedagogy.

**Recommended action:** drop

#### qid `cc2c3ef9-cd77-45a3-8459-e7105a90cceb` — `wine_regions` / d2 / WRONG_GROUND_TRUTH

**Q:** Which Portuguese wine area is identified as holding the more elevated Denominação de Origem Controlada classification?

- A. Almeirim *(keyed)*
- B. Dão
- C. Bucelas
- D. Colares

**Keyed:** A  
**Model picks:** B=11, null=3, D=2  
**Generator/strategy:** chatgpt / fact_to_question  
**Source fact:** Almeirim wine has the higher Denominação de Origem Controlada (DOC) status.

**Defect:** Almeirim is a Vinho Regional Tejo subregion, not a DOC. Dão and Bucelas are DOCs. Source fact misclassifies Almeirim.

**Recommended action:** drop

#### qid `d3a37708-7ece-47ff-8916-8840af05e398` — `grape_varieties` / d2 / WRONG_GROUND_TRUTH

**Q:** Which grape is identified as the variety used for Chateau DYchem Sauterne?

- A. Muscadelle
- B. Sauvignon Blanc *(keyed)*
- C. Semillon
- D. Chenin Blanc

**Keyed:** B  
**Model picks:** C=16  
**Generator/strategy:** chatgpt / fact_to_question  
**Source fact:** Chateau DYchem Sauterne is made from Sauvignon Blanc Grape.

**Defect:** Château d'Yquem is dominantly Sémillon (~80%) with Sauv Blanc minor. Source fact is incorrect.

**Recommended action:** drop

#### qid `d5fa8585-2fa5-4e91-bdd1-b449379e0929` — `grape_varieties` / d2 / WRONG_GROUND_TRUTH

**Q:** A winemaker in Germany is producing a sweet Riesling wine intended for long-term cellaring. What special considerations should be taken during the harvesting process to ensure the grapes are suitable for this style of wine?

- A. Allow the grapes to partially raisinate on the vine
- B. Avoid crushing or bruising the grape skins *(keyed)*
- C. Harvest the grapes at a very low ripeness level
- D. Harvest the grapes during the coolest part of the night

**Keyed:** B  
**Model picks:** A=15, null=1  
**Generator/strategy:** llama / scenario_synthesis  
**Source fact:** Sweet Riesling wines, such as German Trockenbeerenauslese, are especially suited for cellaring since the high sugar content provides for additional preservation. / == Production ==

In wine making, the delicate nature of the Riesling grape requires special handling during harvesting to avoid crushing or bruising the skin. / Riesling is presumed that the Riesling was born somewhere in the valley of the Rhine, since both Heunisch and Traminer have a long documented history in Germany.

**Defect:** TBA-style sweet German Riesling explicitly uses partially raisinated grapes on the vine (Auslese/BA/TBA categories). Models' A answer is correct.

**Recommended action:** drop

#### qid `da66db06-d4cc-4a81-9900-7ecff2d703da` — `viticulture` / d3 / WRONG_GROUND_TRUTH

**Q:** Which wine regulatory framework is explicitly structured to reflect the influence of local geology, climate, and soil on wine characteristics, emphasizing the expression of place in its standards?

- A. Appellation d'origine contrôlée
- B. Protected Designation of Origin
- C. Vintners Quality Alliance *(keyed)*
- D. Denominación de Origen

**Keyed:** C  
**Model picks:** A=16  
**Generator/strategy:** qwen / distractor_mining  
**Source fact:** There were 632 acres (256 ha) of vineyards in production in 2015. / In 2015, there are 548 wineries in Canada, spread over 12,150 hectares (30,000 acres). / Vintners Quality Alliance is in accordance with the concept of terroir. / There are three VQA designated viticultural areas in Ontario, the Niagara Peninsula (which includes ten different sub-appellations), Prince Edward County. / There are five VQA designated viticultural regions in British Columbia, Vancouver Island, the Gulf Islands, the Fraser Valley, Similkameen Valley. / Pelee, Ontario grows about 2,000 hectares (5,000 acres) of soyb…

**Defect:** AOC is the original terroir framework explicitly built around local geology/climate/soil; VQA borrows from it. Source fact (about Canadian acreage) doesn't even support the keyed answer.

**Recommended action:** drop

#### qid `e37c02e0-f0a0-4dbe-acdd-e2752f4488bf` — `viticulture` / d3 / WRONG_GROUND_TRUTH

**Q:** A viticulturist discovers eggs on the undersides of young grapevine leaves in their vineyard. What is the most appropriate action to take to prevent potential damage to the vines?

- A. Release beneficial insects to control the pest population
- B. Apply insecticide treatment to the entire vineyard *(keyed)*
- C. Prune the vines to increase air circulation and reduce pest habitat
- D. Remove the affected leaves and monitor the situation

**Keyed:** B  
**Model picks:** D=13, A=2, null=1  
**Generator/strategy:** llama / scenario_synthesis  
**Source fact:** When sharpshooters feed on vines, they inject the bacterium, which multiplies in the water-conducting system and causes water stress of the plant. / Females lay their eggs in masses of up to 28 in the lower leaf surface of young leaves that have recently expanded. / Apply insecticide treatment to vineyards if any glassy-winged sharpshooter life stage is discovered in a vineyard or if there is a potential for movement of this pest into the vineyard.

**Defect:** Identifying eggs and removing leaves / monitoring is standard IPM; blanket insecticide is not best practice and the source fact doesn't support it.

**Recommended action:** drop

#### qid `ee544a76-4c70-4703-b226-fc20c3d1e363` — `grape_varieties` / d2 / WRONG_GROUND_TRUTH

**Q:** Under Bordeaux white wine classification standards, what is the maximum residual sugar level permitted for a wine to be labeled as dry?

- A. Less than 2 g/L *(keyed)*
- B. Less than 9 g/L
- C. Less than 12 g/L
- D. Less than 4 g/L

**Keyed:** A  
**Model picks:** D=12, B=4  
**Generator/strategy:** claude / fact_to_question  
**Source fact:** A dry white contains less than 2 g/L of residual sugar — a direct reading of the terroir, with no ornament.

**Defect:** EU dry-wine threshold is 4 g/L (or up to 9 with acidity); 2 g/L is a marketing claim not a Bordeaux standard.

**Recommended action:** drop

#### qid `f9b3d5b7-c581-449c-9537-0f881c894485` — `wine_regions` / d2 / WRONG_GROUND_TRUTH

**Q:** Which German wine region includes vineyard land along Lake Constance?

- A. Württemberg *(keyed)*
- B. Mosel
- C. Baden
- D. Pfalz

**Keyed:** A  
**Model picks:** C=16  
**Generator/strategy:** chatgpt / fact_to_question  
**Source fact:** There are also vineyards on Lake Constance that belong to Württemberg.

**Defect:** Baden's Bodensee subregion is the principal Lake Constance wine area; Württemberg has only a small Lake Constance enclave. Models' Baden answer is at least equally correct.

**Recommended action:** drop

### Category: SOURCE_FACT_DUBIOUS (13)

#### qid `01b8ebdb-d030-4a63-bb98-adc0b96642ac` — `wine_regions` / d2 / SOURCE_FACT_DUBIOUS

**Q:** In the Shomron wine region of Israel, which grape variety appears most frequently in published wine reviews?

- A. Sauvignon Blanc *(keyed)*
- B. Chardonnay
- C. Chenin Blanc
- D. Cabernet Sauvignon

**Keyed:** A  
**Model picks:** D=16  
**Generator/strategy:** claude / fact_to_question  
**Source fact:** The most widely reviewed variety in Shomron is Sauvignon Blanc.

**Defect:** 'Most reviewed' is an unverifiable claim from a single uncited fact; Cab Sauv is the more famous Shomron variety so all 16 models picked D.

**Recommended action:** drop

#### qid `41ea4ae4-3781-4b64-9d5b-ce30e9a5a92e` — `producers` / d3 / SOURCE_FACT_DUBIOUS

**Q:** True or False: Golden Vine Winery is located in the Anaheim wine region.

- A. True *(keyed)*
- B. False

**Keyed:** A  
**Model picks:** B=16  
**Generator/strategy:** template_only / template  
**Source fact:** Golden Vine Winery is a wine producer located in Anaheim.

**Defect:** Anaheim is not a recognized wine region; 'Golden Vine Winery' may be Disneyland's restaurant, not a producer. Source fact is dubious.

**Recommended action:** drop

#### qid `43306f0b-7039-4037-a426-c3aaabf184fe` — `wine_business` / d4 / SOURCE_FACT_DUBIOUS

**Q:** What is the median price of Chardonnay wines from Northeastern Italy?

- A. $30
- B. $15
- C. $20
- D. $25 *(keyed)*

**Keyed:** D  
**Model picks:** C=12, B=4  
**Generator/strategy:** llama / fact_to_question  
**Source fact:** Chardonnay wines from Northeastern Italy have a median price of $25.

**Defect:** Median-price questions from a single uncited dataset are unverifiable parametric knowledge; arbitrary discretization across $15/$20/$25/$30 is a coin-flip.

**Recommended action:** drop

#### qid `5c9e22f9-fbbe-4284-beef-1ba0d3213308` — `wine_business` / d4 / SOURCE_FACT_DUBIOUS

**Q:** Which grape variety cultivated in the Central Valley is associated with a statistical midpoint retail value of exactly $10?

- A. Sauvignon Blanc *(keyed)*
- B. Chenin Blanc
- C. Chardonnay
- D. Pinot Grigio

**Keyed:** A  
**Model picks:** B=11, C=5  
**Generator/strategy:** gemini / fact_to_question  
**Source fact:** Sauvignon Blanc wines from Central Valley have a median price of $10.

**Defect:** Median-price coin-flip from one uncited dataset; arbitrary across $10 buckets.

**Recommended action:** drop

#### qid `5cc99a9d-0a8f-4deb-88e5-4ffdc95453cc` — `wine_regions` / d4 / SOURCE_FACT_DUBIOUS

**Q:** In the German wine industry, holders of which regional title automatically qualify to compete for the national German Wine Queen title in the year following their tenure?

- A. The Rheingau Wine Queen
- B. The Moselle Wine Queen *(keyed)*
- C. The Franken Wine Queen
- D. The Pfalz Wine Queen

**Keyed:** B  
**Model picks:** D=8, A=6, C=2  
**Generator/strategy:** claude / fact_to_question  
**Source fact:** In the year following her 'reign', the Moselle Wine Queen is eligible to run for the position of German Wine Queen.

**Defect:** Specific regional wine-queen succession rule; unverifiable single-source claim, models split 4 ways.

**Recommended action:** drop

#### qid `5d6005ef-6078-4c15-b46f-0fc88247e9a6` — `wine_business` / d4 / SOURCE_FACT_DUBIOUS

**Q:** Bottlings of which grape variety originating in Mendoza Province carry a median market value of $13?

- A. Bonarda
- B. Merlot *(keyed)*
- C. Malbec
- D. Cabernet Franc

**Keyed:** B  
**Model picks:** C=13, A=3  
**Generator/strategy:** gemini / fact_to_question  
**Source fact:** Merlot wines from Mendoza Province have a median price of $13.

**Defect:** Median-price arbitrary discretization, single-source.

**Recommended action:** drop

#### qid `5ee74b64-9e8c-4857-a1b7-e5840404512a` — `producers` / d2 / SOURCE_FACT_DUBIOUS

**Q:** Which Spanish winery produces Cava under the Cava DOP appellation?

- A. Cava Canals i Domingo
- B. Vera de Estenas Viñedos y Bodegas *(keyed)*
- C. Cellers de Cal Ventosa
- D. Caves Canals & Munné

**Keyed:** B  
**Model picks:** D=8, A=6, null=1, C=1  
**Generator/strategy:** llama / distractor_mining  
**Source fact:** Cellers de Cal Ventosa winery is located in Banyeres del Penedès, Spain. / Cava Canals i Domingo winery is located in Sant Sadurní d'Anoia, Spain. / The Vera de Estenas Viñedos y Bodegas winery also produces Cava under the Cava DOP appellation. / Caves Canals & Munné winery is located in Sant Sadurní d'Anoia, Spain. / Since then, the winery has quickly built up a reputation for producing quality wines.

**Defect:** Vera de Estenas is in Utiel-Requena (Valencia); the Penedès distractors are more canonical Cava producers; multiple producers listed make Cava.

**Recommended action:** drop

#### qid `656575eb-e7d8-46c1-a832-9e7da21f13aa` — `grape_varieties` / d4 / SOURCE_FACT_DUBIOUS

**Q:** A Georgian producer is preparing an export release aimed at buyers newly exploring Eastern and Central European wines. The cellar team has finished a port-style bottling sourced from Tsitska and Tsolikauri grown in four districts west of central Georgia. Before approving the final lot, the winemaker wants to confirm the target analytical profile matches the established style for this wine when it is ready for market. Which specification should the team use?

- A. Alcohol 12.5-14%, sugar 8-10%, titratable acidity 2-3%
- B. Alcohol 10.5-12%, sugar 1.5-2.5%, titratable acidity 5-7% *(keyed)*
- C. Alcohol 8-9.5%, sugar 4-6%, titratable acidity 7.5-9%
- D. Alcohol 13.5-15%, sugar 0-0.5%, titratable acidity 3-4%

**Keyed:** B  
**Model picks:** A=11, D=3, null=2  
**Generator/strategy:** chatgpt / scenario_synthesis  
**Source fact:** Now that the wines of Eastern and Central Europe are coming to greater international awareness, grapes from this region are becoming better known. / Lelo is a port-type wine made from the Tsitska and Tsolikauri grape varieties grown in Zestaponi, Terjola, Baghdati and Vani districts. / When ready for use, the wine contains 10.5-12% alcohol, 1.5-2.5% sugar and has 5-7% titrated acidity.

**Defect:** Specific Lelo analytical specs (alc/sugar/TA) are arbitrary; not parametric LLM knowledge.

**Recommended action:** drop

#### qid `6c3d1c3f-333a-47db-8a81-ebf317c4a5ca` — `wine_business` / d4 / SOURCE_FACT_DUBIOUS

**Q:** Which of the following red wine styles has a median market price of $30 when produced in Oregon?

- A. Tempranillo *(keyed)*
- B. Syrah
- C. Cabernet Franc
- D. Pinot Noir

**Keyed:** A  
**Model picks:** D=15, B=1  
**Generator/strategy:** qwen / fact_to_question  
**Source fact:** Tempranillo wines from Oregon have a median price of $30.

**Defect:** Single-source median price; arbitrary buckets.

**Recommended action:** drop

#### qid `7943889f-af60-4007-9c1c-47c90da3147c` — `wine_business` / d4 / SOURCE_FACT_DUBIOUS

**Q:** Market data indicates a median retail cost of $28 for bottlings of which specific grape variety produced in California?

- A. Tempranillo *(keyed)*
- B. Sangiovese
- C. Mourvèdre
- D. Barbera

**Keyed:** A  
**Model picks:** C=7, D=7, B=2  
**Generator/strategy:** gemini / fact_to_question  
**Source fact:** Tempranillo wines from California have a median price of $28.

**Defect:** Single-source median price; arbitrary.

**Recommended action:** drop

#### qid `7cbb066d-6adc-4ae1-b596-eea1bcf458ec` — `grape_varieties` / d4 / SOURCE_FACT_DUBIOUS

**Q:** A Chilean winery's expansion program six years on includes seven grape varieties across its portfolio. Which of the following is NOT among those seven varieties?

- A. Gewürztraminer
- B. Pinot Gris
- C. Viognier *(keyed)*
- D. Albariño

**Keyed:** C  
**Model picks:** D=8, null=3, A=3, B=2  
**Generator/strategy:** claude / fact_to_question  
**Source fact:** Chilean wine six years after taking the decision of expanding, they have seven varieties: Chardonnay, Pinot Noir, Sauvignon Blanc, Albariño, Pinot Gris, Gewürztraminer and Riesling.

**Defect:** Specific 'six years on, seven varieties' Chilean expansion list is unverifiable single-source.

**Recommended action:** drop

#### qid `82064b9a-ff5b-4460-afb5-b7c19b3fd847` — `wine_business` / d4 / SOURCE_FACT_DUBIOUS

**Q:** What is the median price of Syrah wines from Colchagua Valley?

- A. $45
- B. $35
- C. $25
- D. $18 *(keyed)*

**Keyed:** D  
**Model picks:** C=9, B=7  
**Generator/strategy:** llama / fact_to_question  
**Source fact:** Syrah wines from Colchagua Valley have a median price of $18.

**Defect:** Single-source median price.

**Recommended action:** drop

#### qid `d482cf87-a321-4956-b5c3-b33f8b706501` — `wine_regions` / d4 / SOURCE_FACT_DUBIOUS

**Q:** Which of the following designated areas spans a total surface measurement of roughly 3.71 hectares?

- A. Clos de la Coulée de Serrant
- B. Clos de Tart
- C. Cuide de Vila Verde *(keyed)*
- D. Château-Grillet

**Keyed:** C  
**Model picks:** D=10, A=5, B=1  
**Generator/strategy:** gemini / fact_to_question  
**Source fact:** Cuide de Vila Verde covers approximately 3.71 hectares.

**Defect:** 3.71 ha is also Château-Grillet's famous size; the keyed 'Cuide de Vila Verde' is obscure and the fact is single-source.

**Recommended action:** drop

### Category: AMBIGUOUS_WORDING (16)

#### qid `1134c7d6-5ec8-4a7d-848e-3d83b0a880d2` — `grape_varieties` / d3 / AMBIGUOUS_WORDING

**Q:** Which grape variety is authorized for cultivation in the Ramona Valley AVA, known for its warm climate and focus on Mediterranean varieties?

- A. Grenache
- B. Mourvèdre
- C. Carignane *(keyed)*
- D. Syrah

**Keyed:** C  
**Model picks:** D=10, A=6  
**Generator/strategy:** qwen / comparative  
**Source fact:** Ramona Valley AVA permits the Carignane grape variety. / North Yuba AVA permits the Grenache grape variety.

**Defect:** Question primes 'Mediterranean varieties' (Grenache/Mourvèdre/Syrah are listed) yet keys Carignane; all distractors are plausibly authorized too.

**Recommended action:** drop

#### qid `193bcee8-8952-4f2a-82a6-ad811d10178b` — `wine_regions` / d2 / AMBIGUOUS_WORDING

**Q:** How long after harvest are Tokaji wines typically ready for release?

- A. 6 to 8 years
- B. 10 or more years
- C. 1 to 2 years *(keyed)*
- D. 3 to 5 years

**Keyed:** C  
**Model picks:** D=12, B=3, A=1  
**Generator/strategy:** llama / fact_to_question  
**Source fact:** Tokaji are ready for release a year to 18 months after harvest.

**Defect:** Tokaji aszú is matured 3+ years by tradition; only basic Tokaji styles release at 1-2 years. Question doesn't specify style.

**Recommended action:** drop

#### qid `3d76f4a5-fdfe-4434-bab5-3c5bd0df4afe` — `wine_regions` / d2 / AMBIGUOUS_WORDING

**Q:** Which Australian wine region encompasses the majority of significant vineyards but is smaller in area than its broader geographical indication zone?

- A. Yarra Valley
- B. McLaren Vale
- C. Barossa Valley
- D. Hunter Valley *(keyed)*

**Keyed:** D  
**Model picks:** C=13, A=2, B=1  
**Generator/strategy:** qwen / fact_to_question  
**Source fact:** Hunter Valley is not as large as the Hunter Valley zone, but includes most of the significant vineyards.

**Defect:** The wording 'majority of significant vineyards but smaller than its zone' applies equally to Barossa Valley vs Barossa zone; question is genuinely ambiguous.

**Recommended action:** drop

#### qid `4924da7b-d1bc-4ab1-ae24-c40472f86113` — `viticulture` / d2 / AMBIGUOUS_WORDING

**Q:** A winemaker in Monterey County is looking to expand their vineyard holdings and is considering purchasing land in the Hames Valley AVA. The winemaker wants to ensure the new site will produce high-quality fruit that complements their existing portfolio from other Monterey County AVAs like Chalone, Arroyo Seco, and Santa Lucia Highlands. What geographic feature should the winemaker consider when evaluating the Hames Valley site?

- A. Adjacency to the San Lucas AVA *(keyed)*
- B. Elevation of the vineyard site
- C. Proximity to the Pacific Ocean
- D. Soil composition and drainage

**Keyed:** A  
**Model picks:** D=8, C=5, B=3  
**Generator/strategy:** llama / scenario_synthesis  
**Source fact:** Monterey County wine are Chalone, Arroyo Seco, San Lucas, Santa Lucia Highlands, San Bernabe, Hames Valley, Carmel Valley, San Antonio Valley, Gabilan Mountains and the large Monterey viticultural areas. / Hames Valley is an American Viticultural Area (AVA) in  Monterey County, California a few miles from its southern border with San Luis Obispo (SLO) County. / The appellation's northern border is Pine Canyon and is adjacent on its southern border to the San Lucas viticultural area.

**Defect:** Adjacency, ocean proximity, soil and elevation are all valid 'geographic features' for vineyard evaluation; key has no decisive support.

**Recommended action:** drop

#### qid `639b66eb-ccf2-41a8-ab1e-dd7fc5983492` — `producers` / d3 / AMBIGUOUS_WORDING

**Q:** Which entity is licensed to manufacture and sell items under their own brand or trademark using purchased grapes?

- A. Abbot's Passage Supply Co.
- B. Franzia
- C. Sandhi *(keyed)*
- D. Winery Sixteen 600

**Keyed:** C  
**Model picks:** B=8, A=3, D=3, null=2  
**Generator/strategy:** llama / distractor_mining  
**Source fact:** Sandhi is his label of purchased grapes while Lompoc, Domaine de la Cote. / Abbot's Passage Supply Co. is a wine producer in Sonoma, United States. / Phil Coturri is the chief executive officer of Enterprise Vineyard Management and co-owner of Winery Sixteen 600. / As of 2008, there were  no commercially bonded wineries in the region. / 2. If not above, the producer is the person licensed to manufacturer and sell or offer for sale to consumers an item with packaging under the brand or trademark of. / The Franzia family sold the brand to Coca-Cola in 1973 when Fred Franzia was in his early adul…

**Defect:** All four entities are licensed wineries selling under their own brand; vague predicate.

**Recommended action:** drop

#### qid `7ce9c38c-c919-494b-92ae-2c95ccbd9c81` — `producers` / d3 / AMBIGUOUS_WORDING

**Q:** Which Spanish winery is known for its fine wines?

- A. Bodegas Torres
- B. Casajús *(keyed)*
- C. Marqués de Riscal
- D. Bodegas Williams & Humbert

**Keyed:** B  
**Model picks:** C=13, A=2, null=1  
**Generator/strategy:** llama / distractor_mining  
**Source fact:** Casajús or Casajús Winery, in Spanish: Bodegas Casajús, is a Spanish fine winery. / Bodegas Williams & Humbert winery is located in Jerez de la Frontera, Spain. / Bodegas Torres holds Penedès, Conca de Barberà, Jumilla, Priorat, Ribera del Duero, Rioja, Toro classification.

**Defect:** 'Known for fine wines' is true of Bodegas Torres, Marqués de Riscal, and Williams & Humbert; the keyed Casajús is one of many.

**Recommended action:** drop

#### qid `804dcc8d-ea2f-4928-b1aa-e50767a80ea5` — `grape_varieties` / d4 / AMBIGUOUS_WORDING

**Q:** While both of these red grapes are authorized in specific California appellations, which variety is officially sanctioned for cultivation within Diablo Grande rather than being the designated grape for Hames Valley?

- A. Petite Sirah
- B. Zinfandel
- C. Cabernet Sauvignon
- D. Merlot *(keyed)*

**Keyed:** D  
**Model picks:** A=9, B=3, C=2, null=2  
**Generator/strategy:** gemini / comparative  
**Source fact:** Diablo Grande AVA permits the Merlot grape variety. / Hames Valley AVA permits the Petite Sirah grape variety.

**Defect:** Both AVAs permit Cab Sauv/Merlot/Petite Sirah/Zinfandel; the fact picking out one each per AVA is incidental.

**Recommended action:** drop

#### qid `812041c4-1338-4a40-9d7b-dd799df6e3ed` — `grape_varieties` / d2 / AMBIGUOUS_WORDING

**Q:** Wines made from certain grape varieties in a specific Southern Hemisphere country are generally characterized by low aromatic intensity and simple structure, making them more suitable for blending or conversion into spirits rather than being bottled as single-varietal wines. In which wine-producing nation are these neutral-profile grapes most commonly associated with large-scale plantings?

- A. South Africa *(keyed)*
- B. Argentina
- C. Australia
- D. Chile

**Keyed:** A  
**Model picks:** B=8, C=5, D=3  
**Generator/strategy:** qwen / fact_to_question  
**Source fact:** South African wine grapes typically produce bland, neutral wine that lends itself well to blending and distillation, but are rarely seen in varietal bottlings.

**Defect:** Argentina (Cereza/Criolla for distillation), Chile (País for pisco) also fit; the predicate isn't unique to South Africa.

**Recommended action:** drop

#### qid `91298417-6d21-48fa-952c-3bbba85de3a0` — `wine_regions` / d2 / AMBIGUOUS_WORDING

**Q:** In which US state is the Shenandoah Valley wine-producing area located?

- A. Virginia
- B. Washington
- C. California *(keyed)*
- D. Oregon

**Keyed:** C  
**Model picks:** A=16  
**Generator/strategy:** llama / fact_to_question  
**Source fact:** Shenandoah Valley (CA) is a wine-producing area within the California region of US.

**Defect:** There are two Shenandoah Valley AVAs: California AND Virginia; the question has two correct answers.

**Recommended action:** drop

#### qid `936a7ba6-4691-4ad5-a497-e650addaef39` — `wine_regions` / d1 / AMBIGUOUS_WORDING · cb_fail

**Q:** Which ancient wine was extensively traded across the Mediterranean and held in high esteem in Italy during the Roman Empire?

- A. Coan wine
- B. Greek wine *(keyed)*
- C. Epirus Region wine
- D. Rumney wine

**Keyed:** B  
**Model picks:** A=16  
**Generator/strategy:** llama / distractor_mining  
**Source fact:** Greek wine was not a "fortified" wine in the modern sense, rather a "cooked" wine (vin cuit) to which boiled-down must (grape syrup) was added. / In ancient times, as trade in wine became extensive, it was transported from end to end of the Mediterranean; Greek wine had especially high prestige in Italy under the Roman Empire. / Epirus Region is a wine appellation in Greece, Greece. / Coan wine is wine from the Greek island of Kos, and in particular a style of wine invented there in classical antiquity that was known for its saltiness.

**Defect:** Coan wine IS a famous ancient Greek wine traded across the Mediterranean (from Kos); both A and B are correct.

**Recommended action:** drop

#### qid `982e5c3a-bb7a-43ff-bec9-0b5d034b39d9` — `grape_varieties` / d3 / AMBIGUOUS_WORDING

**Q:** Which of these American Viticultural Areas includes a grape variety known for its herbaceous and peppery characteristics when grown in cooler climates as an approved variety for appellation-labeled wines?

- A. Cienega Valley AVA
- B. El Dorado AVA
- C. Mendocino AVA
- D. Clear Lake AVA *(keyed)*

**Keyed:** D  
**Model picks:** C=10, A=3, null=2, B=1  
**Generator/strategy:** qwen / comparative  
**Source fact:** Clear Lake AVA permits the Cabernet Franc grape variety. / Cienega Valley AVA permits the Chardonnay grape variety.

**Defect:** Multiple AVAs permit Cab Franc; the herbaceous/peppery profile description is generic. Question doesn't single out Clear Lake.

**Recommended action:** drop

#### qid `a5925478-12cd-458c-af90-e91cf31bb4f2` — `wine_regions` / d3 / AMBIGUOUS_WORDING

**Q:** Which wine-producing region offers a diverse range of activities including winter sports and wine tourism, set against the backdrop of the Andes mountain range at notable altitudes?

- A. Aconcagua Valley *(keyed)*
- B. Valle de Uco
- C. Mendoza wine
- D. San Rafael

**Keyed:** A  
**Model picks:** B=10, C=5, null=1  
**Generator/strategy:** qwen / distractor_mining  
**Source fact:** One area of emerging importance in the Mendoza wine region is the Valle de Uco which includes the Tupungato Department featuring vineyards planted nearly 1,200 metres (3. / San Rafael was also awarded DOC status in 1993. / From winter activities to wine tasting with a privileged view of the Andes mountain range, in the Aconcagua Valley the offer is very diverse.

**Defect:** Mendoza/Valle de Uco are higher-altitude with closer ski resorts; Aconcagua Valley is coastal. The wording fits Mendoza better.

**Recommended action:** drop

#### qid `b1db99b5-7efb-4b2b-8a80-6d3463bb30b9` — `grape_varieties` / d2 / AMBIGUOUS_WORDING

**Q:** One of these AVAs allows Malbec, while the other allows Zinfandel. Which option correctly matches the grapes to Contra Costa AVA and Tehachapi Mountains AVA?

- A. Contra Costa AVA — Malbec; Tehachapi Mountains AVA — Malbec
- B. Contra Costa AVA — Zinfandel; Tehachapi Mountains AVA — Zinfandel
- C. Contra Costa AVA — Zinfandel; Tehachapi Mountains AVA — Malbec
- D. Contra Costa AVA — Malbec; Tehachapi Mountains AVA — Zinfandel *(keyed)*

**Keyed:** D  
**Model picks:** C=16  
**Generator/strategy:** chatgpt / comparative  
**Source fact:** Contra Costa AVA permits the Malbec grape variety. / Tehachapi Mountains AVA permits the Zinfandel grape variety.

**Defect:** Contra Costa is canonically known for old-vine Zinfandel; the source fact's narrow 'permits' list (Malbec for Contra Costa, Zinfandel for Tehachapi) inverts the iconic varietal association. Both AVAs permit both varieties.

**Recommended action:** drop

#### qid `be33af32-00cf-4c7b-ba71-969ccd48b495` — `wine_regions` / d4 / AMBIGUOUS_WORDING

**Q:** Which American Viticultural Area is situated in a county that lies east of the Cascade Range and is not part of any larger AVA, based on its standalone county location?

- A. Howell Mountain AVA
- B. Naches Heights AVA
- C. Goose Gap AVA *(keyed)*
- D. Russian River Valley AVA

**Keyed:** C  
**Model picks:** B=14, null=2  
**Generator/strategy:** qwen / distractor_mining  
**Source fact:** Central Coast AVA contains the York Mountain AVA. / Russian River Valley AVA is located within the Sonoma Coast AVA. / Goose Gap AVA is located in Benton County. / Howell Mountain AVA is located in Napa County. / Anderson Valley AVA contains the Mendocino Ridge AVA. / Naches Heights AVA is located within the Columbia Valley AVA.

**Defect:** Naches Heights AVA is also east of Cascades and in Yakima County, also nested only in Columbia Valley parent; ambiguous.

**Recommended action:** drop

#### qid `dee0ac6f-0347-4c69-8410-75e3363558c9` — `wine_regions` / d2 / AMBIGUOUS_WORDING

**Q:** Which AVA is situated in a Texas county known for its Hill Country terrain and German-influenced place names?

- A. Bell Mountain AVA *(keyed)*
- B. Escondido Valley AVA
- C. Fredericksburg in the Texas Hill Country AVA
- D. Texas High Plains AVA

**Keyed:** A  
**Model picks:** C=16  
**Generator/strategy:** qwen / fact_to_question  
**Source fact:** Bell Mountain AVA is located in Gillespie County.

**Defect:** Fredericksburg in the Texas Hill Country AVA literally has 'Texas Hill Country' in its name and is the iconic German-Texan town; 16/16 picked it correctly.

**Recommended action:** drop

#### qid `f64ed682-7d18-4e12-8317-bb5c6433c82d` — `wine_regions` / d4 / AMBIGUOUS_WORDING

**Q:** A Georgian winemaker is deciding how to position their straw-colored wine for export markets, given past political challenges. What should be their primary focus in marketing materials to highlight the wine's authentic qualities?

- A. Its fresh, harmonious taste with fruity flavors *(keyed)*
- B. The use of qvevri vessels for fermentation
- C. Its similarity to popular Russian wine styles
- D. The wine's high alcohol content

**Keyed:** A  
**Model picks:** B=16  
**Generator/strategy:** llama / scenario_synthesis  
**Source fact:** Political tensions with Russia have contributed to the 2006 Russian embargo of Georgian wine, with Russia claiming that Georgia produced counterfeit wine. / Georgian wine of straw color has a characteristic savor with a fruity flavor and fresh harmonious taste. / Georgian wine of straw color has a characteristic aroma, a fine, fresh and a harmonious taste.

**Defect:** Qvevri fermentation IS the canonical Georgian wine marketing differentiator; 16/16 picking B reflects standard wine-marketing practice.

**Recommended action:** drop

### Category: HARD_BUT_FAIR (14)

#### qid `1c1b75d3-cdfe-4734-ae66-87c354cbf726` — `wine_regions` / d2 / HARD_BUT_FAIR · cb_fail

**Q:** Clare Valley belongs to which Australian geographic zone?

- A. Mount Lofty Ranges Zone
- B. Fleurieu Zone
- C. Yorke and Mid North *(keyed)*
- D. Barossa Zone

**Keyed:** C  
**Model picks:** A=14, D=2  
**Generator/strategy:** chatgpt / fact_to_question  
**Source fact:** Clare Valley is a wine region in Yorke and Mid North.

**Defect:** Clare Valley is officially in the Yorke and Mid North zone; legitimately tricky factual recall. cb_fail tag is appropriate but answer is correct.

**Recommended action:** keep

#### qid `3a5023ff-a7bf-42ed-9fff-16340d2dfdf0` — `wine_business` / d4 / HARD_BUT_FAIR

**Q:** Which US state's regulatory initiatives impacting the wine industry included the formation of an Extended Producer Responsibility (EPR) Advisory Council and a mandated statewide evaluation of recycling needs finalized in early 2025?

- A. Maryland *(keyed)*
- B. Colorado
- C. Oregon
- D. California

**Keyed:** A  
**Model picks:** C=6, D=5, null=3, B=2  
**Generator/strategy:** gemini / fact_to_question  
**Source fact:** American wine established the EPR Advisory Council and mandated a statewide Recycling Needs Assessment. Resources: Maryland Statewide Recycling Final Needs Assessment, February 21, 2025.

**Defect:** Niche US-state regulatory trivia; obscure but factually correct.

**Recommended action:** keep

#### qid `3ceda321-766a-40fb-a596-f8133adae634` — `wine_regions` / d2 / HARD_BUT_FAIR

**Q:** Which nation is recognized as the largest volume producer of wine south of the equator, while simultaneously holding the number five spot globally?

- A. South Africa
- B. Argentina
- C. Australia
- D. Chile *(keyed)*

**Keyed:** D  
**Model picks:** B=9, C=6, A=1  
**Generator/strategy:** gemini / fact_to_question  
**Source fact:** According to statistics from the Food and Agriculture Organization (FAO), Chile has the fifth-highest wine production worldwide and the highest in the Southern Hemisphere.

**Defect:** Chile-vs-Argentina rankings flip year-to-year; FAO stats genuinely support Chile in some years. Hard recall.

**Recommended action:** keep

#### qid `958ba425-9279-4c15-bab7-ef9052681eb2` — `winemaking` / d2 / HARD_BUT_FAIR

**Q:** When evaluating active spring frost protection techniques, systems utilizing permanent installations—like heating cables or wind machines—demonstrate reduced variability. What is the primary reason for this consistency?

- A. Reduced reliance on manual labor during frost events
- B. Decreased water consumption per hectare
- C. Lower initial capital investment per hectare
- D. Decreased fuel usage per hectare *(keyed)*

**Keyed:** D  
**Model picks:** A=16  
**Generator/strategy:** gemini / fact_to_question  
**Source fact:** In contrast, ASFPMs requiring fixed infrastructure, such as wind machines, sprinklers, winter covers and heating cables, showed less variability due to their lower fuel consumption per hectare.

**Defect:** Specific scientific finding from frost-protection literature; legitimately hard but factually keyed.

**Recommended action:** keep

#### qid `99792793-6c3f-4955-90ec-7894d709e09b` — `grape_varieties` / d4 / HARD_BUT_FAIR

**Q:** Upon its initial creation, which specific appellation encompassed 490 hectares (1,200 acres) of planted vineyards alongside half a dozen approved bonded wineries or cellars?

- A. Arkansas Mountain *(keyed)*
- B. Ozark Mountain
- C. Altus
- D. Augusta

**Keyed:** A  
**Model picks:** D=5, C=5, B=4, null=2  
**Generator/strategy:** gemini / fact_to_question  
**Source fact:** At the outset, there were 1,200 acres (490 ha) under vine and six bonded wineries or bonded wine cellars authorized to operate within Arkansas Mountain.

**Defect:** Niche US AVA establishment trivia; legitimately hard but correctly keyed.

**Recommended action:** keep

#### qid `9b0db1b3-730a-4991-9218-1dce83796803` — `wine_regions` / d4 / HARD_BUT_FAIR

**Q:** Which English wine producer was recognized with the 'Champion Team Trophy' following a competitive evaluation, according to Wines of Great Britain?

- A. Chapel Down Winery
- B. Davenport Vineyards *(keyed)*
- C. Nyetimber Estate
- D. Ridgeview Vineyards

**Keyed:** B  
**Model picks:** D=11, C=3, A=2  
**Generator/strategy:** qwen / fact_to_question  
**Source fact:** After a competitive battle the ‘Champion Team Trophy’ was awarded to Davenport Vineyards , based in Sussex.

**Defect:** Obscure trade-show award trivia; correctly keyed but obscure.

**Recommended action:** keep

#### qid `a0764446-f50b-4c95-bc16-23d651cebc89` — `wine_regions` / d4 / HARD_BUT_FAIR

**Q:** In medieval times, which royal court position was specifically tasked with overseeing both the production and acquisition of wine?

- A. Wine steward of the crown
- B. Chief vinifier
- C. Royal cellar master
- D. Royal wine procurer *(keyed)*

**Keyed:** D  
**Model picks:** C=12, A=4  
**Generator/strategy:** qwen / fact_to_question  
**Source fact:** During the Middle Ages, there was a royal court official called the "royal wine procurer", whose responsibilities included the production and procurement of wine.

**Defect:** Obscure medieval-history wine term; legitimately hard but factually keyed.

**Recommended action:** keep

#### qid `a58fad2c-ce15-4223-969f-89225ca066a8` — `wine_regions` / d4 / HARD_BUT_FAIR

**Q:** Which town in the United States shares a zip code with Athens and is the only dry municipality where wine may not be shipped?

- A. McDowell Valley
- B. Baltimore *(keyed)*
- C. Fiddletown
- D. Comptche

**Keyed:** B  
**Model picks:** D=7, C=6, null=3  
**Generator/strategy:** llama / distractor_mining  
**Source fact:** Wine may not be shipped into municipalities voted as dry – Baltimore is the only dry town. Note that Baltimore and Athens share zip code 05143. / Comptche AVA is surrounded by land designated as a Timberland Production Zone and zoned solely for the growing and harvesting of timber for no less than ten years from the. / Fiddletown AVA became abundant by the end of the nineteenth century. / McDowell Valley AVA appellation is located on sloped bench land at elevations as high as 1,000 feet (300 m) above sea level that overlook the Russian River to the west.

**Defect:** Vermont dry-municipality trivia tied to a specific zip code; obscure.

**Recommended action:** keep

#### qid `aab6c72a-7f6f-413f-b3a8-a026fe9960b8` — `viticulture` / d2 / HARD_BUT_FAIR

**Q:** Which grape variety's variability is predominantly dictated by mesoclimatic factors, specifically its elevation and its exposure to maritime breezes?

- A. Touriga Nacional
- B. Tannat *(keyed)*
- C. Albariño
- D. Malbec

**Keyed:** B  
**Model picks:** C=14, D=2  
**Generator/strategy:** gemini / fact_to_question  
**Source fact:** Mesoclimate, especially due to altitude and exposition to the ocean winds, mostly explained 'Tannat' variability.

**Defect:** Specific Uruguayan Tannat research finding on mesoclimate; hard but correctly keyed.

**Recommended action:** keep

#### qid `dea90a6d-cd2c-45bf-83f9-0777760ba87c` — `viticulture` / d4 / HARD_BUT_FAIR

**Q:** What is the maximum annual application rate allowed for a single treatment in grape pest management when applying at the standard concentration?

- A. 8.955 oz/acre limited to one application per growing season
- B. 2.985 oz/acre with no more than two applications per year *(keyed)*
- C. 5.97 oz/acre with up to four applications permitted annually
- D. 1.4925 oz/acre with a maximum of three applications per year

**Keyed:** B  
**Model picks:** A=8, C=6, null=1, D=1  
**Generator/strategy:** qwen / fact_to_question  
**Source fact:** Do not apply more than two applications at 2.985 oz/acre per acre per year.

**Defect:** Specific pesticide-rate regulation; obscure but correctly keyed.

**Recommended action:** keep

#### qid `e050acf0-4333-4315-86d9-8d67c7962130` — `winemaking` / d4 / HARD_BUT_FAIR

**Q:** Over the past four decades, which wine style has shown a statistically significant increase in quality?

- A. White wines *(keyed)*
- B. Rosé wines
- C. Sparkling wines
- D. Red wines

**Keyed:** A  
**Model picks:** D=14, B=2  
**Generator/strategy:** llama / fact_to_question  
**Source fact:** Generally, white wine quality increased (p < 0.05) over the years, while red and sparkling wines remained unaffected.

**Defect:** Specific finding from a peer-reviewed wine-quality time-series study; correctly keyed.

**Recommended action:** keep

#### qid `e3e6b52b-98ad-4bf8-bb4c-4dd0d8f6d715` — `grape_varieties` / d4 / HARD_BUT_FAIR

**Q:** In viticultural taxonomy, what is the berry color classification of the Kizil Sapak cultivar?

- A. White *(keyed)*
- B. Rose
- C. Gris
- D. Black

**Keyed:** A  
**Model picks:** D=10, B=4, null=1, C=1  
**Generator/strategy:** gemini / fact_to_question  
**Source fact:** Kizil Sapak is a white grape variety according to UC Davis FPS.

**Defect:** Kizil Sapak's color classification per UC Davis FPS; obscure but verifiable.

**Recommended action:** keep

#### qid `f9e2eaaf-f025-4232-bda3-862047357eb1` — `winemaking` / d2 / HARD_BUT_FAIR

**Q:** When dealing with underripe fruit during red wine production, what is the observed impact of prolonging skin contact time?

- A. It makes up for the lack of sugar accumulation by extracting higher levels of anthocyanins.
- B. It successfully masks green, herbaceous flavors by extracting more mature seed tannins.
- C. It significantly exacerbates the negative sensory traits associated with the lack of ripeness.
- D. It fails to offset the lack of ripeness and does not amplify the underripe characteristics. *(keyed)*

**Keyed:** D  
**Model picks:** C=14, A=2  
**Generator/strategy:** gemini / fact_to_question  
**Source fact:** Extended maceration neither compensated for grape immaturity nor enhanced the effects of immaturity.

**Defect:** Specific extended-maceration research finding; the wording is technical but the keyed answer matches the fact verbatim.

**Recommended action:** keep

#### qid `fe26b166-2a28-45a1-8adf-ef7c54e06861` — `wine_regions` / d4 / HARD_BUT_FAIR

**Q:** Introduced in 1984, Aguna is a Georgian wine characterized by which combination of color and sweetness level?

- A. White and semi-sweet
- B. Amber and off-dry
- C. Red and dry
- D. Rosé and semi-dry *(keyed)*

**Keyed:** D  
**Model picks:** A=9, C=4, B=3  
**Generator/strategy:** claude / fact_to_question  
**Source fact:** Aguna is a pink semi-dry wine produced since 1984.

**Defect:** Obscure 1984-introduced Georgian wine recall; correctly keyed but very niche.

**Recommended action:** keep

---

## Audit method

- Pulled the 97 questions where exactly 16/16 evaluator configs answered and 0 were correct under run `8b0a0864-f3c6-4ec5-8f3d-e30271b8c3a0` (eval_release_v1_2_full).
- For each item: read question text, all options, source-fact provenance, 16-model parsed-answer distribution, and applied wine-domain knowledge to pick the first-fitting category from {DUP_OPTION, EQUIV_OPTIONS, ALL_CORRECT, WRONG_GROUND_TRUTH, SOURCE_FACT_DUBIOUS, AMBIGUOUS_WORDING, HARD_BUT_FAIR}.
- DUP_OPTION detected programmatically (case-insensitive option-text equality) and confirmed manually; all other categories were assessed manually.
- Decision-bias: per the briefing, when borderline between WRONG_GROUND_TRUTH and HARD_BUT_FAIR, the prior of frequent corpus defects warranted defaulting to WRONG_GROUND_TRUTH.
- HARD_BUT_FAIR was reserved for items with internally-consistent fact + key + options, even when 16/16 models failed; cb_fail-tagged items were scrutinized more closely.

