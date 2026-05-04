# OenoBench Evaluation Report

**Tag:** `eval_release_v1_2_full`  
**Run ID:** `8b0a0864-f3c6-4ec5-8f3d-e30271b8c3a0`  
**Corpus:** `public`  
**Started:** 2026-05-03 21:43:30.751589+00:00  
**Completed:** 2026-05-03 23:44:04.875266+00:00  
**Wall time:** 120m 34s  
**Total questions:** 3329  
**Total LLM calls:** 53264  
**Total cost (effective):** $101.04  
**Config slate:** 16 configs  

---

## 1. Per-Config Summary

| Slot | Config | Family | Reasoning | Accuracy | Parse % | p50 lat (ms) | p95 lat (ms) | Tokens in | Tokens out | Tokens reason | Cost |
|---:|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | claude-opus-4.7 | anthropic | standard | 79.5% | 99.4% | 1278 | 2109 | 599418 | 16569 | — | $3.41 |
| 2 | claude-haiku-4.5 | anthropic | standard | 52.3% | 80.3% | 1275 | 20987 | 337106 | 21532 | — | $0.44 |
| 3 | gpt-5 | openai | standard | 81.2% | 95.8% | 10552 | 49771 | 384611 | 2213213 | — | $22.61 |
| 4 | gpt-5-mini | openai | standard | 76.9% | 99.8% | 7436 | 24337 | 386144 | 1396362 | — | $2.89 |
| 5 | gemini-2.5-pro | google | standard | 80.2% | 96.7% | 9038 | 21116 | 365788 | 2982059 | — | $30.28 |
| 6 | gemini-2.5-flash | google | standard | 73.7% | 100.0% | 403 | 774 | 367888 | 3329 | — | $0.12 |
| 7 | llama-3.3-70b | meta | standard | 65.8% | 100.0% | 488 | 3108 | 410596 | 6658 | — | $0.04 |
| 8 | llama-3.1-8b | meta | standard | 59.4% | 100.0% | 375 | 885 | 410549 | 6658 | — | $0.01 |
| 9 | deepseek-v3 | deepseek | standard | 68.9% | 100.0% | 656 | 1138 | 369817 | 6654 | — | $0.12 |
| 10 | qwen-2.5-72b | qwen | standard | 66.1% | 100.0% | 532 | 2735 | 408747 | 3329 | — | $0.15 |
| 11 | qwen-2.5-7b | qwen | standard | 55.9% | 100.0% | 416 | 808 | 408967 | 6647 | — | $0.12 |
| 12 | mistral-large-2411 | mistral | standard | 67.8% | 100.0% | 294 | 2508 | 426991 | 6658 | — | $0.88 |
| 13 | o3 | openai | effort | 82.0% | 98.0% | 5775 | 23026 | 384624 | 1427419 | — | $12.19 |
| 14 | gemini-2.5-pro-thinking | google | explicit_budget | 81.0% | 100.0% | 5654 | 6605 | 367888 | 1285756 | — | $13.32 |
| 15 | deepseek-r1 | deepseek | explicit_budget | 75.6% | 98.4% | 36103 | 131469 | 372201 | 4237567 | — | $10.86 |
| 16 | claude-opus-4.7-thinking | anthropic | explicit_budget | 79.5% | 99.4% | 1278 | 2143 | 599385 | 23632 | — | $3.59 |

*OR-authoritative cost is available for 99% of rows (52,608/53,264); remaining use locally-computed cost.*

## 2. Per-Config × Per-Domain Accuracy (%)

| Config | Wine Regions | Grape Varieties | Producers | Viticulture | Winemaking | Wine Business |
|---|---|---|---|---|---|---|
| claude-opus-4.7 | 82.0% | 77.4% | 85.6% | 76.5% | 86.2% | 63.2% |
| claude-haiku-4.5 | 55.1% | 47.9% | 57.9% | 53.2% | 56.4% | 37.2% |
| gpt-5 | 86.9% | 75.5% | 87.2% | 81.3% | 80.3% | 62.0% |
| gpt-5-mini | 81.0% | 71.8% | 82.3% | 76.1% | 77.1% | 65.2% |
| gemini-2.5-pro | 85.8% | 76.0% | 87.8% | 77.1% | 77.1% | 60.8% |
| gemini-2.5-flash | 75.8% | 70.4% | 81.2% | 72.3% | 77.1% | 59.6% |
| llama-3.3-70b | 68.0% | 60.7% | 76.1% | 64.5% | 70.2% | 49.6% |
| llama-3.1-8b | 61.4% | 53.7% | 68.5% | 60.6% | 59.0% | 46.8% |
| deepseek-v3 | 73.4% | 66.1% | 72.2% | 69.5% | 68.6% | 50.4% |
| qwen-2.5-72b | 68.1% | 62.8% | 72.4% | 66.3% | 69.7% | 52.0% |
| qwen-2.5-7b | 58.3% | 53.7% | 58.6% | 56.4% | 57.4% | 44.0% |
| mistral-large-2411 | 70.6% | 63.3% | 74.4% | 68.1% | 72.9% | 50.8% |
| o3 | 87.2% | 78.5% | 89.7% | 78.9% | 76.1% | 64.4% |
| gemini-2.5-pro-thinking | 85.3% | 77.7% | 88.7% | 79.1% | 83.0% | 59.2% |
| deepseek-r1 | 79.4% | 71.0% | 84.5% | 70.9% | 76.1% | 63.6% |
| claude-opus-4.7-thinking | 82.0% | 78.1% | 85.8% | 77.3% | 83.5% | 60.4% |
| **all** | 75.0% | 67.8% | 78.3% | 70.5% | 73.2% | 55.6% |

## 3. Per-Config × Per-Strategy Accuracy (%)

| Config | FTQ | Scenario | Template | Comparative | Distractor |
|---|---|---|---|---|---|
| claude-opus-4.7 | 76.5% | 83.5% | 92.8% | 74.3% | 81.3% |
| claude-haiku-4.5 | 46.7% | 61.2% | 70.7% | 49.8% | 55.8% |
| gpt-5 | 78.6% | 78.9% | 95.4% | 74.3% | 86.4% |
| gpt-5-mini | 72.6% | 78.6% | 92.8% | 73.2% | 83.3% |
| gemini-2.5-pro | 76.1% | 85.3% | 93.1% | 77.0% | 85.0% |
| gemini-2.5-flash | 68.4% | 82.0% | 89.7% | 72.4% | 78.2% |
| llama-3.3-70b | 58.5% | 78.6% | 89.7% | 60.5% | 70.6% |
| llama-3.1-8b | 51.4% | 68.8% | 89.7% | 56.3% | 62.6% |
| deepseek-v3 | 63.5% | 78.3% | 86.4% | 67.0% | 72.1% |
| qwen-2.5-72b | 58.6% | 77.4% | 88.7% | 64.8% | 72.3% |
| qwen-2.5-7b | 48.3% | 70.3% | 78.9% | 53.3% | 60.0% |
| mistral-large-2411 | 61.7% | 78.6% | 87.4% | 63.2% | 72.1% |
| o3 | 78.7% | 82.3% | 94.9% | 79.3% | 86.9% |
| gemini-2.5-pro-thinking | 77.2% | 86.2% | 95.6% | 78.5% | 82.8% |
| deepseek-r1 | 72.2% | 73.7% | 92.5% | 72.0% | 79.4% |
| claude-opus-4.7-thinking | 76.1% | 83.5% | 93.6% | 75.1% | 81.6% |
| **all** | 66.6% | 77.9% | 89.5% | 68.2% | 75.6% |

## 4. Self-Preference Score (SPS)

Bootstrap 95% CI via 1000 resamples. δ = accuracy(own-family Qs) − accuracy(other Qs).

| Config | Family | Own-family acc | Other acc | δ | 95% CI |
|---|---|---:|---:|---:|---|
| claude-haiku-4.5 | anthropic | 58.5% | 47.5% | +11.0% | [+6.9%, +15.1%] |
| claude-opus-4.7 | anthropic | 86.2% | 75.5% | +10.7% | [+7.5%, +13.8%] |
| claude-opus-4.7-thinking | anthropic | 86.5% | 75.2% | +11.3% | [+7.8%, +14.5%] |
| deepseek-v3 | deepseek | — | 66.6% | — | — |
| deepseek-r1 | deepseek | — | 73.4% | — | — |
| gemini-2.5-flash | google | 63.4% | 73.0% | -9.6% | [-14.5%, -4.7%] |
| gemini-2.5-pro | google | 73.9% | 79.2% | -5.3% | [-10.0%, -0.8%] |
| gemini-2.5-pro-thinking | google | 73.0% | 80.2% | -7.1% | [-11.9%, -2.5%] |
| llama-3.1-8b | meta | 52.1% | 56.3% | -4.1% | [-8.4%, -0.0%] |
| llama-3.3-70b | meta | 63.0% | 62.5% | +0.5% | [-3.9%, +4.6%] |
| mistral-large-2411 | mistral | — | 65.2% | — | — |
| gpt-5 | openai | 77.1% | 79.9% | -2.7% | [-6.6%, +1.0%] |
| gpt-5-mini | openai | 75.4% | 74.7% | +0.7% | [-3.6%, +4.4%] |
| o3 | openai | 79.3% | 80.5% | -1.2% | [-5.1%, +2.4%] |
| qwen-2.5-72b | qwen | 65.0% | 62.6% | +2.4% | [-1.7%, +6.3%] |
| qwen-2.5-7b | qwen | 59.9% | 50.7% | +9.2% | [+5.2%, +13.3%] |

## 4b. Self-Preference Family Matrix

Cells are accuracy% (N). Rows are evaluator families; columns are generator
families. Diagonal cells are own-family (SPS) accuracy; off-diagonal cells are
cross-family.

| Eval ↓ / Gen → | anthropic | openai | google | meta | qwen |
|---|---:|---:|---:|---:|---:|
| **anthropic** | 77.1% (1866) | 68.8% (1680) | 62.1% (1278) | 64.1% (1962) | 68.3% (2034) |
| **openai** | 86.0% (1866) | 77.3% (1680) | 75.4% (1278) | 74.6% (1962) | 76.8% (2034) |
| **google** | 85.9% (1866) | 75.6% (1680) | 70.1% (1278) | 72.9% (1962) | 75.7% (2034) |
| **meta** | 64.7% (1244) | 59.5% (1120) | 46.1% (852) | 57.6% (1308) | 62.8% (1356) |
| **qwen** | 64.0% (1244) | 57.6% (1120) | 45.5% (852) | 56.1% (1308) | 62.5% (1356) |

## 5. Reasoning-Effect Deltas

Bootstrap 95% CI via 1000 resamples. δ = accuracy(reasoning config) − accuracy(standard config).

| Pair | Thinking config | Standard config | Thinking acc | Standard acc | δ | 95% CI |
|---|---|---|---:|---:|---:|---|
| Claude Opus 4.7: thinking vs standard | claude-opus-4.7-thinking | claude-opus-4.7 | 79.5% | 79.5% | -0.1% | [-2.0%, +1.9%] |
| Gemini 2.5 Pro: thinking vs standard | gemini-2.5-pro-thinking | gemini-2.5-pro | 81.0% | 80.2% | +0.9% | [-1.0%, +2.8%] |
| o3 vs GPT-5 | o3 | gpt-5 | 82.0% | 81.2% | +0.8% | [-1.1%, +2.5%] |
| DeepSeek-R1 vs DeepSeek-V3 | deepseek-r1 | deepseek-v3 | 75.6% | 68.9% | +6.7% | [+4.6%, +9.1%] |

## 6. Cost & Wall Ledger

| Slot | Config | Questions | Cost (effective) | Effective wall (est.) |
|---:|---|---:|---|---|
| 1 | claude-opus-4.7 | 3329 | $3.41 | ~1246s |
| 2 | claude-haiku-4.5 | 3329 | $0.44 | ~2092s |
| 3 | gpt-5 | 3329 | $22.61 | ~24504s |
| 4 | gpt-5-mini | 3329 | $2.89 | ~6493s |
| 5 | gemini-2.5-pro | 3329 | $30.28 | ~15759s |
| 6 | gemini-2.5-flash | 3329 | $0.12 | ~2247s |
| 7 | llama-3.3-70b | 3329 | $0.04 | ~1183s |
| 8 | llama-3.1-8b | 3329 | $0.01 | ~472s |
| 9 | deepseek-v3 | 3329 | $0.12 | ~1163s |
| 10 | qwen-2.5-72b | 3329 | $0.15 | ~865s |
| 11 | qwen-2.5-7b | 3329 | $0.12 | ~236s |
| 12 | mistral-large-2411 | 3329 | $0.88 | ~1059s |
| 13 | o3 | 3329 | $12.19 | ~9164s |
| 14 | gemini-2.5-pro-thinking | 3329 | $13.32 | ~3820s |
| 15 | deepseek-r1 | 3329 | $10.86 | ~45976s |
| 16 | claude-opus-4.7-thinking | 3329 | $3.59 | ~3266s |
| | **Local cost (computed)** | | **$100.94** | |
| | **OR cost (authoritative, 52,608 rows)** | | **$101.04** | |

## 7. Closed-Book vs Contextual Accuracy

CB-fail = questions tagged `closed_book_solvable` (parametric wine knowledge).
CB-pass = the rest (contextual wine reasoning). δ = acc(CB-fail) − acc(CB-pass);
positive means the model leans on memorised wine facts; negative means it does
better when it has to reason from the question.

| Slot | Config | n CB-fail | acc CB-fail | n CB-pass | acc CB-pass | δ | 95% CI |
|---:|---|---:|---:|---:|---:|---:|---|
| 1 | claude-opus-4.7 | 1603 | 97.2% | 1726 | 63.1% | +34.1% | [+31.6%, +36.4%] |
| 2 | claude-haiku-4.5 | 1603 | 70.1% | 1726 | 35.7% | +34.4% | [+31.2%, +37.4%] |
| 3 | gpt-5 | 1603 | 96.3% | 1726 | 67.3% | +29.0% | [+26.7%, +31.3%] |
| 4 | gpt-5-mini | 1603 | 94.6% | 1726 | 60.5% | +34.0% | [+31.6%, +36.7%] |
| 5 | gemini-2.5-pro | 1603 | 96.9% | 1726 | 64.7% | +32.2% | [+30.0%, +34.7%] |
| 6 | gemini-2.5-flash | 1603 | 92.5% | 1726 | 56.3% | +36.3% | [+33.6%, +38.9%] |
| 7 | llama-3.3-70b | 1603 | 85.5% | 1726 | 47.5% | +38.1% | [+35.2%, +41.0%] |
| 8 | llama-3.1-8b | 1603 | 75.9% | 1726 | 44.0% | +31.9% | [+28.7%, +34.8%] |
| 9 | deepseek-v3 | 1603 | 90.3% | 1726 | 49.1% | +41.3% | [+38.5%, +44.0%] |
| 10 | qwen-2.5-72b | 1603 | 86.7% | 1726 | 47.0% | +39.7% | [+36.9%, +42.6%] |
| 11 | qwen-2.5-7b | 1603 | 72.7% | 1726 | 40.2% | +32.5% | [+29.4%, +35.6%] |
| 12 | mistral-large-2411 | 1603 | 87.2% | 1726 | 49.7% | +37.5% | [+34.6%, +40.3%] |
| 13 | o3 | 1603 | 97.3% | 1726 | 67.8% | +29.5% | [+27.3%, +31.7%] |
| 14 | gemini-2.5-pro-thinking | 1603 | 97.3% | 1726 | 66.0% | +31.3% | [+28.9%, +33.5%] |
| 15 | deepseek-r1 | 1603 | 94.1% | 1726 | 58.4% | +35.7% | [+33.4%, +38.5%] |
| 16 | claude-opus-4.7-thinking | 1603 | 97.3% | 1726 | 62.9% | +34.5% | [+32.1%, +37.0%] |
| | **all configs (mean δ)** | | | | | **+34.5%** | |

## 8. Per-Config × Per-Difficulty Accuracy (%)

Difficulty 1 (easy) → 4 (hardest). Cells are accuracy on each difficulty tier.

| Config | 1 (easy) | 2 | 3 | 4 (hardest) |
|---|---|---|---|---|
| claude-opus-4.7 | 97.8% | 74.2% | 84.2% | 68.5% |
| claude-haiku-4.5 | 74.2% | 46.6% | 58.2% | 38.4% |
| gpt-5 | 98.1% | 79.5% | 85.0% | 68.6% |
| gpt-5-mini | 97.8% | 71.1% | 82.2% | 64.3% |
| gemini-2.5-pro | 98.4% | 76.4% | 84.8% | 67.9% |
| gemini-2.5-flash | 95.2% | 68.4% | 79.8% | 59.6% |
| llama-3.3-70b | 91.8% | 58.5% | 72.6% | 49.9% |
| llama-3.1-8b | 84.7% | 53.4% | 63.5% | 44.6% |
| deepseek-v3 | 95.7% | 63.5% | 74.1% | 52.0% |
| qwen-2.5-72b | 93.1% | 58.4% | 71.6% | 51.0% |
| qwen-2.5-7b | 81.8% | 48.8% | 58.3% | 42.9% |
| mistral-large-2411 | 94.2% | 60.8% | 71.2% | 53.6% |
| o3 | 98.3% | 78.5% | 86.8% | 70.6% |
| gemini-2.5-pro-thinking | 99.0% | 77.3% | 85.8% | 68.8% |
| deepseek-r1 | 97.4% | 71.5% | 79.7% | 61.6% |
| claude-opus-4.7-thinking | 98.1% | 74.1% | 84.5% | 68.0% |
| **all** | 93.5% | 66.3% | 76.4% | 58.1% |

## 9. Item Analysis

### 9a. Per-Question Accuracy Distribution

Histogram of how many questions were answered correctly by exactly k configs (out of N = 16).

| k correct out of 16 | # questions | % of corpus |
|---:|---:|---:|
| 0 | 97 | 2.9% |
| 1 | 65 | 2.0% |
| 2 | 96 | 2.9% |
| 3 | 58 | 1.7% |
| 4 | 85 | 2.6% |
| 5 | 98 | 2.9% |
| 6 | 112 | 3.4% |
| 7 | 116 | 3.5% |
| 8 | 149 | 4.5% |
| 9 | 140 | 4.2% |
| 10 | 153 | 4.6% |
| 11 | 154 | 4.6% |
| 12 | 185 | 5.6% |
| 13 | 191 | 5.7% |
| 14 | 282 | 8.5% |
| 15 | 496 | 14.9% |
| 16 | 852 | 25.6% |

### 9b. Ceiling and Floor Items

- **Ceiling items** (correct by >= 15 of 16 configs): 1348 items.
  Sample question_ids: `0018ba3d-6db5-4a0e-997b-220be4d2c7b8`, `003045cd-1bb6-42d8-ad62-0ddf0a0d710e`, `00547308-c5d4-4285-bf5f-955ddc5a3eb0`, `007d0a0e-6002-400b-8131-0e3052e652d0`, `0081729c-c583-4f1d-9b05-4741a612b3a5`
- **Floor items** (correct by 0 of 16 configs): 97 items.
  Sample question_ids: `01b8ebdb-d030-4a63-bb98-adc0b96642ac`, `0534d251-fd20-4660-b696-7ee652cb12f4`, `06dcf574-85c6-42ad-924e-5a7f33115e13`, `0c984c8f-44c6-47c6-b520-9ec2fd156952`, `0d5660e2-875e-4167-a27d-eedbfd37be7a`

### 9c. Hardest and Easiest Items

**Top 10 hardest** (lowest mean accuracy first):

| question_id | mean accuracy |
|---|---:|
| `01b8ebdb-d030-4a63-bb98-adc0b96642ac` | 0.0% |
| `0534d251-fd20-4660-b696-7ee652cb12f4` | 0.0% |
| `06dcf574-85c6-42ad-924e-5a7f33115e13` | 0.0% |
| `0c984c8f-44c6-47c6-b520-9ec2fd156952` | 0.0% |
| `0d5660e2-875e-4167-a27d-eedbfd37be7a` | 0.0% |
| `0d908a02-7eb6-4c12-b307-5c587a7a829c` | 0.0% |
| `11259084-8a23-4019-b3bd-42597dafa512` | 0.0% |
| `1134c7d6-5ec8-4a7d-848e-3d83b0a880d2` | 0.0% |
| `12ccc0a7-dbe6-49b6-8154-db8acf087629` | 0.0% |
| `1475af73-4526-4236-95f3-a2263a4c4e5e` | 0.0% |

**Top 10 easiest** (highest mean accuracy first):

| question_id | mean accuracy |
|---|---:|
| `ff8e67b4-49fe-4d18-afbb-8654143c3903` | 100.0% |
| `ff222779-812a-4e91-a159-d715ad95dc6b` | 100.0% |
| `fe8baddf-d25b-4835-b7ee-bb260e16f2df` | 100.0% |
| `fe4ab3a9-0f13-472c-b051-f78b83d7422f` | 100.0% |
| `fe339e20-b13b-44d3-94e9-98f067bf12eb` | 100.0% |
| `fe267264-541f-4f1e-8389-001ebd584fc3` | 100.0% |
| `fe235a2a-646a-4e8f-8688-ee3b2d289170` | 100.0% |
| `fde710d8-67c0-4499-97c7-03118c43b9f6` | 100.0% |
| `fdc3ed77-2eca-4cf7-a326-8fdc5f58a837` | 100.0% |
| `fd49db47-3fe4-45b2-9e62-f5465bed1ceb` | 100.0% |

### 9d. Item Discrimination (Point-Biserial)

For each question we correlate the per-config 0/1 outcome vector with each config's overall accuracy. Lower / negative `rpb` flags items that behave inconsistently with overall config skill — paper-quality QA candidates.

**Top 10 worst-discriminating items** (lowest / most-negative `rpb` first):

| question_id | mean accuracy | rpb |
|---|---:|---:|
| `2495d9bc-39bc-4a73-a242-5d95ba7eba71` | 37.5% | -0.848 |
| `3294ddbb-d11d-485f-9c7b-911d21c73aa2` | 50.0% | -0.819 |
| `d37a888c-3149-41e2-82b6-78f38a166f8a` | 56.2% | -0.797 |
| `5a834c2d-b60e-4563-b753-ed0dfba1afa2` | 56.2% | -0.724 |
| `5156b118-449f-4cac-bf94-9b6d01c90ae8` | 37.5% | -0.717 |
| `edb268fd-55f6-4638-98dc-914f57c84a0e` | 31.2% | -0.658 |
| `47ee0c01-b9b7-4bed-a694-e806cf2f9759` | 37.5% | -0.634 |
| `e657e167-0cdf-4843-9718-ec4567fcc472` | 62.5% | -0.629 |
| `4e4c6414-6f07-4833-856a-4fc182c91df9` | 31.2% | -0.599 |
| `ec0e0990-87c2-4965-800e-e1da398996dd` | 37.5% | -0.596 |

## 10. Cost-Efficiency

Cost per correct answer = effective_cost / correct_count. Lower is better.
"effective" cost prefers OR-authoritative when present, else locally computed.

| Slot | Config | Correct | Effective cost | Cost / correct |
|---:|---|---:|---|---|
| 8 | llama-3.1-8b | 1976 | $0.01 | $0.0000 |
| 7 | llama-3.3-70b | 2190 | $0.04 | $0.0000 |
| 6 | gemini-2.5-flash | 2454 | $0.12 | $0.0000 |
| 9 | deepseek-v3 | 2295 | $0.12 | $0.0001 |
| 11 | qwen-2.5-7b | 1860 | $0.12 | $0.0001 |
| 10 | qwen-2.5-72b | 2202 | $0.15 | $0.0001 |
| 2 | claude-haiku-4.5 | 1741 | $0.44 | $0.0003 |
| 12 | mistral-large-2411 | 2256 | $0.88 | $0.0004 |
| 4 | gpt-5-mini | 2561 | $2.89 | $0.0011 |
| 1 | claude-opus-4.7 | 2647 | $3.41 | $0.0013 |
| 16 | claude-opus-4.7-thinking | 2645 | $3.59 | $0.0014 |
| 15 | deepseek-r1 | 2517 | $10.86 | $0.0043 |
| 13 | o3 | 2729 | $12.19 | $0.0045 |
| 14 | gemini-2.5-pro-thinking | 2698 | $13.32 | $0.0049 |
| 3 | gpt-5 | 2704 | $22.61 | $0.0084 |
| 5 | gemini-2.5-pro | 2669 | $30.28 | $0.0113 |


---
_Generated at 20260503T234445Z by OenoBench report renderer._
