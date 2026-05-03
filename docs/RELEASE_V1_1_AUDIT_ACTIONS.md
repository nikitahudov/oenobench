# Release release_v1.1 — Audit actions report

- **Audit run_id**: `2ba38269-5e66-44aa-aaaf-010dc7ef19d4`
- **Corpus tag**: `release_v1.1`
- **Corpus size**: 3670
- **Generated**: 2026-05-03T20:10:12+00:00

## 1 · Categorisation summary

| Tag | Count | % | Recommended action |
|---|---:|---:|---|
| `audit_clean` | 68 | 1.9% | Keep |
| `audit_warn_only` | 1063 | 29.0% | Keep; flag in datasheet |
| `audit_fail_review` | 886 | 24.1% | Manual review (A1 vague-phrasing) |
| `audit_fail_critical` | 1653 | 45.0% | Drop candidates (pending precision check) |
| `audit_no_signal` | 0 | 0.0% | Re-run subset (audit signal incomplete) |

## 2 · Per-defect groups (FAIL findings)

### B1_TriJudgeAnswer — 47 questions

**Recommended action**: Drop from corpus if precision threshold passes. Tri-judge consensus disagrees with the keyed answer — likely wrong-key or unfaithful to source.

Sample UUIDs:
- `20e2ca08-9f2b-4c11-ad94-2e489e16f6b3` · WB-GRP-1197-L2 · L2 · Which wine entity is associated with a grape variety developed at the Geisenheim Grape Breeding Institute and represents…
- `276c5612-3816-4f6b-875e-26a4ed08a432` · WB-GRP-1336-L2 · L2 · Which dark-skinned grape variety is described by its winemaker as being resistant to raisining and to flavor degradation…
- `31d131b2-d0c7-470c-a4e8-a248c2a7651e` · WB-GRP-0938-L3 · L3 · Which grape variety is associated with wines that, despite being entitled to a specific appellation in Alba, have seen p…
- `329d560c-1e83-40a1-bf85-5204132ae9b4` · WB-VIT-0823-L3 · L3 · Which arachnid is generally considered beneficial in vineyards due to its predatory behavior?…
- `33039525-9ea7-47ff-8ea3-af14d88bef6c` · WB-GRP-0954-L4 · L4 · A Georgian winemaker is deciding between producing a dry white wine from Rkatsiteli and Mtsvane grapes grown in Kakheti,…

### B2_ClosedBookSolvability_L12 — 1452 questions

**Recommended action**: Drop from corpus if precision threshold passes. Question solvable from world knowledge alone at low difficulty — does not test source comprehension.

Sample UUIDs:
- `0018ba3d-6db5-4a0e-997b-220be4d2c7b8` · WB-VIT-0682-L2 · L1 · Which vineyard operation is used so air and fungicide applications can move through the vine wall and fully reach flower…
- `003045cd-1bb6-42d8-ad62-0ddf0a0d710e` · WB-REG-0733-L2 · L1 · Which Portuguese wine designation applies specifically to non-fortified wines that are simpler in style and originate fr…
- `0032d48b-c97f-4a8e-91d7-b808dfa0875c` · WB-GRP-0832-L2 · L1 · Which two grape varieties are the main focus of Rajat Parr's wine production?…
- `00547308-c5d4-4285-bf5f-955ddc5a3eb0` · WB-VIT-0741-L2 · L2 · Which certification programme, managed by a national industry body, serves as the primary sustainability standard for vi…
- `007d0a0e-6002-400b-8131-0e3052e652d0` · WB-REG-1031-L2 · L2 · Which indigenous grape variety is utilized to craft the distinct rosé wine known as Schilcher?…

### A3_FactEcho — 63 questions

**Recommended action**: Drop from corpus. Question text overlaps source verbatim (LCS≥0.65) — the test reduces to keyword matching.

Sample UUIDs:
- `047e7041-264d-44be-9074-a396114a5ad6` · WB-PRD-0553-L2 · L1 · Which of the following is a distinction held by the gardens of Château Val Joanis?…
- `06cdc7bd-cb4a-4f80-8def-6cc0706b478a` · WB-GRP-0812-L2 · L1 · What is the distinguishing characteristic of the Garnacha Peluda grape variety?…
- `0842757f-d7b1-4747-8767-0627ca2754ec` · WB-VIT-0549-L2 · L2 · By how many degrees Celsius was the average daytime temperature increased in a viticulture field trial using an open-top…
- `0956adf4-ae65-46ba-aaf7-0c589d612ae1` · WB-REG-1408-L4 · L4 · In which county is the Mount Pisgah, Polk County, Oregon AVA located, according to the source fact?…
- `09d5604c-8181-4d3c-b9bc-8d6b6442de2f` · WB-REG-1410-L4 · L4 · Which county or counties comprise the Lewis-Clark Valley AVA?…

### C2_CategoryLeak — 9 questions

**Recommended action**: Drop from corpus. Distractor's wine category mismatches correct answer's (red vs white, sparkling vs still) — easy elimination defeats the question.

Sample UUIDs:
- `2f38be95-2387-4215-9138-5fa83b3bd4e1` · WB-GRP-1101-L2 · L2 · Which two grape varieties are cultivated by a traditional Champagne house known for adhering to the classic varietal com…
- `5da3a3b4-4d79-48b4-ad50-82a4dec004bc` · WB-WMK-0410-L2 · L1 · What was the result of the unpredictable fermentation process in early Champagne production?…
- `61dd2a66-d237-46a4-89b8-8c2221614539` · WB-GRP-0942-L2 · L1 · A single-vineyard Champagne bottling named Clos d'Ambonnay is produced using only one black-skinned grape. Which grape i…
- `7ae554c5-f6a4-4d05-8e05-b3bf645b57ff` · WB-GRP-0955-L2 · L1 · Within the Nuits-Saint-Georges AOC in Burgundy, which two grape varieties serve as the principal cultivars for red and w…
- `bcc5f292-9a26-4239-aebe-104d3d318278` · WB-GRP-0971-L2 · L2 · A Champagne grower based in Dizy farms 23 hectares spread across villages including Hautvillers, Aÿ, Mareuil-sur-Aÿ, Cru…

### B3_UbiquityRisk — 183 questions

**Recommended action**: Drop from corpus. Question stem mentions an internationally-grown grape (Cabernet/Pinot Noir/Chardonnay/Merlot/Sauvignon Blanc/Syrah/Riesling/etc.) and the correct answer is a region-class entity — multiple regions plausibly grow the grape, so the answer is ambiguous. Confirmed via human gold review (9/45 = 20% ambiguity rate in release_v1_1_smart sample).

Sample UUIDs:
- `031e4e85-0637-4286-8a68-d448f8cdd907` · WB-REG-0690-L3 · L1 · Which Argentine wine region was designated in 1993 as the country's first official appellation, setting a precedent for …
- `087d859c-5988-405d-bca7-889a02ae7976` · WB-GRP-1073-L2 · L2 · Wines made from Pinot noir in a French region located across the river valley from Burgundy tend to exhibit a lighter bo…
- `095d1faf-6073-427b-8580-eac62a13a5c1` · WB-GRP-0720-L3 · L3 · If a wine merchant wants to source genuine Cabernet Sauvignon-based wines, which of the following regions would be the m…
- `0a874369-5e69-4639-bb95-2a10ab7be47f` · WB-REG-1166-L2 · L2 · A Lombardy DOCG sparkling wine produced by the traditional method permits a blend of Chardonnay and Pinot Nero, with Pin…
- `0b50c57b-ba47-451c-b73b-955ec2230e06` · WB-GRP-1149-L2 · L2 · Which grape variety is generally cultivated with such wide spacing between plants that multiple different grapes, such a…

### A1_LexicalHygiene — 60 questions

**Recommended action**: Manual review (light defect). Vague phrasing ('iconic', 'acclaimed') — salvageable with a regex pass + paraphrase, but does not invalidate the question.

Sample UUIDs:
- `0512ee1f-3aa5-4e3f-823f-73c49c090410` · WB-REG-1025-L2 · L2 · The premier cru climat 'Île des Vergelesses' is classified within which Côte de Beaune village appellation?…
- `07de78eb-d388-419c-be18-9bcf77db0511` · WB-PRD-0869-L2 · L1 · A winery in Montalcino is rebuilding its production plan after a widely publicized fraud controversy that drew scrutiny …
- `0db45949-2a74-48bf-a2b1-99c2a3ca39a3` · WB-GRP-0914-L2 · L2 · Which Italian wine region is known for producing wines that emphasize the fresh fruit and pure varietal character of the…
- `11c125d6-f719-4397-bfd8-822f5e0a080c` · WB-GRP-1083-L3 · L1 · Which Argentine wine region is known for producing sherry-style wines in addition to premium red varietals made from Syr…
- `143025df-cb30-46da-88bc-8e87ab3a6104` · WB-REG-1280-L2 · L2 · Which of the following refers to a Premier Cru vineyard designation within the Chassagne-Montrachet appellation in Burgu…

### Other per-question FAILs (no auto-action)

- **C4_DifficultyAudit**: 1351 questions

## 3 · Corpus-size projections

| Action | Resulting corpus size |
|---|---:|
| Keep all | 3670 |
| Drop `audit_fail_critical` | 2017 |
| Drop `audit_fail_critical` + `audit_no_signal` | 2017 |
| Drop `audit_fail_critical` + `audit_fail_review` | 1131 |

## 4 · Per-strategy fail-rate table

| Strategy | Q in tag | Fail findings | Warn findings | Pass findings |
|---|---:|---:|---:|---:|
| comparative | 308 | 276 | 537 | 1194 |
| distractor_mining | 486 | 371 | 952 | 1860 |
| fact_to_question | 2098 | 1817 | 3143 | 8343 |
| scenario_synthesis | 345 | 282 | 757 | 1302 |
| template | 433 | 419 | 499 | 1725 |

## 5 · Corpus-aggregate signals (A2 / A4 / D1 / D3)

| Agent | Severity | Score | Highlights |
|---|---|---:|---|
| A2_BiasStats | fail | 0.9451 | — |
| A4_TemplateFingerprint | pass | 0.6390 | — |
| D1_SelfPreference | fail | 0.3250 | — |
| D3_SkewAudit | warn | 2.5550 | — |
