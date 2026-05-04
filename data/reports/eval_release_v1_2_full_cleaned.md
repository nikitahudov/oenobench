# OenoBench Evaluation Report

**Tag:** `eval_release_v1_2_full`  
**Run ID:** `8b0a0864-f3c6-4ec5-8f3d-e30271b8c3a0`  
**Corpus:** `public`  
**Started:** 2026-05-03 21:43:30.751589+00:00  
**Completed:** 2026-05-03 23:44:04.875266+00:00  
**Wall time:** 120m 34s  
**Total questions:** 3275  
**Total LLM calls:** 52400  
**Total cost (effective):** $98.78  
**Config slate:** 16 configs  

---

## 1. Per-Config Summary

| Slot | Config | Family | Reasoning | Accuracy | Parse % | p50 lat (ms) | p95 lat (ms) | Tokens in | Tokens out | Tokens reason | Cost |
|---:|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | claude-opus-4.7 | anthropic | standard | 80.8% | 99.4% | 1278 | 2115 | 590544 | 16299 | — | $3.36 |
| 2 | claude-haiku-4.5 | anthropic | standard | 53.2% | 80.3% | 1278 | 20985 | 331889 | 21352 | — | $0.44 |
| 3 | gpt-5 | openai | standard | 82.6% | 95.9% | 10421 | 49366 | 378983 | 2155158 | — | $22.03 |
| 4 | gpt-5-mini | openai | standard | 78.2% | 99.8% | 7398 | 24282 | 380436 | 1369924 | — | $2.83 |
| 5 | gemini-2.5-pro | google | standard | 81.5% | 96.9% | 9008 | 20781 | 360506 | 2915269 | — | $29.60 |
| 6 | gemini-2.5-flash | google | standard | 74.9% | 100.0% | 403 | 778 | 362522 | 3275 | — | $0.12 |
| 7 | llama-3.3-70b | meta | standard | 66.9% | 100.0% | 489 | 3112 | 404485 | 6550 | — | $0.04 |
| 8 | llama-3.1-8b | meta | standard | 60.3% | 100.0% | 374 | 882 | 404439 | 6550 | — | $0.01 |
| 9 | deepseek-v3 | deepseek | standard | 70.1% | 100.0% | 656 | 1139 | 364351 | 6546 | — | $0.12 |
| 10 | qwen-2.5-72b | qwen | standard | 67.2% | 100.0% | 532 | 2731 | 402710 | 3275 | — | $0.15 |
| 11 | qwen-2.5-7b | qwen | standard | 56.8% | 100.0% | 416 | 808 | 402930 | 6539 | — | $0.12 |
| 12 | mistral-large-2411 | mistral | standard | 68.9% | 100.0% | 294 | 2500 | 420712 | 6550 | — | $0.87 |
| 13 | o3 | openai | effort | 83.3% | 98.2% | 5726 | 22635 | 378996 | 1388169 | — | $11.86 |
| 14 | gemini-2.5-pro-thinking | google | explicit_budget | 82.4% | 100.0% | 5651 | 6606 | 362522 | 1264802 | — | $13.10 |
| 15 | deepseek-r1 | deepseek | explicit_budget | 76.9% | 98.4% | 35709 | 131020 | 366724 | 4132197 | — | $10.59 |
| 16 | claude-opus-4.7-thinking | anthropic | explicit_budget | 80.8% | 99.4% | 1278 | 2146 | 590511 | 23362 | — | $3.54 |

*OR-authoritative cost is available for 99% of rows (51,753/52,400); remaining use locally-computed cost.*

## 2. Per-Config × Per-Domain Accuracy (%)

| Config | Wine Regions | Grape Varieties | Producers | Viticulture | Winemaking | Wine Business |
|---|---|---|---|---|---|---|
| claude-opus-4.7 | 83.1% | 79.8% | 86.3% | 77.7% | 86.6% | 64.2% |
| claude-haiku-4.5 | 55.8% | 49.4% | 58.3% | 54.0% | 56.7% | 37.8% |
| gpt-5 | 88.0% | 77.8% | 87.9% | 82.6% | 80.7% | 63.0% |
| gpt-5-mini | 82.0% | 74.0% | 83.0% | 77.3% | 77.5% | 66.3% |
| gemini-2.5-pro | 86.9% | 78.3% | 88.5% | 78.3% | 77.5% | 61.8% |
| gemini-2.5-flash | 76.8% | 72.5% | 81.8% | 73.5% | 77.5% | 60.6% |
| llama-3.3-70b | 68.8% | 62.6% | 76.7% | 65.6% | 70.6% | 50.4% |
| llama-3.1-8b | 62.2% | 55.3% | 69.1% | 61.5% | 59.4% | 47.6% |
| deepseek-v3 | 74.3% | 68.1% | 72.8% | 70.6% | 69.0% | 51.2% |
| qwen-2.5-72b | 68.9% | 64.7% | 73.0% | 67.4% | 70.1% | 52.8% |
| qwen-2.5-7b | 59.0% | 55.3% | 59.1% | 57.3% | 57.8% | 44.7% |
| mistral-large-2411 | 71.5% | 65.3% | 75.0% | 69.2% | 73.3% | 51.6% |
| o3 | 88.3% | 80.9% | 90.4% | 80.2% | 76.5% | 65.4% |
| gemini-2.5-pro-thinking | 86.4% | 80.1% | 89.4% | 80.4% | 83.4% | 60.2% |
| deepseek-r1 | 80.4% | 73.2% | 85.1% | 72.1% | 76.5% | 64.6% |
| claude-opus-4.7-thinking | 83.1% | 80.5% | 86.5% | 78.5% | 84.0% | 61.4% |
| **all** | 76.0% | 69.9% | 78.9% | 71.6% | 73.6% | 56.5% |

## 3. Per-Config × Per-Strategy Accuracy (%)

| Config | FTQ | Scenario | Template | Comparative | Distractor |
|---|---|---|---|---|---|
| claude-opus-4.7 | 77.7% | 85.0% | 92.8% | 78.5% | 82.1% |
| claude-haiku-4.5 | 47.4% | 62.3% | 70.7% | 52.6% | 56.4% |
| gpt-5 | 79.8% | 80.4% | 95.4% | 78.5% | 87.3% |
| gpt-5-mini | 73.8% | 80.1% | 92.8% | 77.3% | 84.1% |
| gemini-2.5-pro | 77.3% | 86.9% | 93.1% | 81.4% | 85.8% |
| gemini-2.5-flash | 69.4% | 83.5% | 89.7% | 76.5% | 78.9% |
| llama-3.3-70b | 59.4% | 80.1% | 89.7% | 64.0% | 71.3% |
| llama-3.1-8b | 52.2% | 70.1% | 89.7% | 59.5% | 63.2% |
| deepseek-v3 | 64.5% | 79.8% | 86.4% | 70.9% | 72.8% |
| qwen-2.5-72b | 59.5% | 78.8% | 88.7% | 68.4% | 73.0% |
| qwen-2.5-7b | 49.1% | 71.7% | 78.9% | 56.3% | 60.5% |
| mistral-large-2411 | 62.7% | 80.1% | 87.4% | 66.8% | 72.8% |
| o3 | 79.9% | 83.8% | 94.9% | 83.8% | 87.7% |
| gemini-2.5-pro-thinking | 78.4% | 87.9% | 95.6% | 83.0% | 83.6% |
| deepseek-r1 | 73.4% | 75.1% | 92.5% | 76.1% | 80.1% |
| claude-opus-4.7-thinking | 77.3% | 85.0% | 93.6% | 79.4% | 82.4% |
| **all** | 67.6% | 79.4% | 89.5% | 72.1% | 76.4% |

## 4. Self-Preference Score (SPS)

Bootstrap 95% CI via 1000 resamples. δ = accuracy(own-family Qs) − accuracy(other Qs).

| Config | Family | Own-family acc | Other acc | δ | 95% CI |
|---|---|---:|---:|---:|---|
| claude-haiku-4.5 | anthropic | 58.8% | 48.6% | +10.2% | [+5.7%, +14.7%] |
| claude-opus-4.7 | anthropic | 86.6% | 77.2% | +9.4% | [+6.2%, +12.4%] |
| claude-opus-4.7-thinking | anthropic | 86.9% | 76.9% | +10.0% | [+7.0%, +13.2%] |
| deepseek-v3 | deepseek | — | 67.9% | — | — |
| deepseek-r1 | deepseek | — | 74.7% | — | — |
| gemini-2.5-flash | google | 64.1% | 74.4% | -10.3% | [-15.4%, -5.6%] |
| gemini-2.5-pro | google | 74.8% | 80.8% | -6.0% | [-10.6%, -1.9%] |
| gemini-2.5-pro-thinking | google | 73.9% | 81.7% | -7.9% | [-12.2%, -3.5%] |
| llama-3.1-8b | meta | 53.8% | 57.1% | -3.3% | [-7.5%, +0.9%] |
| llama-3.3-70b | meta | 65.0% | 63.5% | +1.5% | [-2.4%, +6.0%] |
| mistral-large-2411 | mistral | — | 66.4% | — | — |
| gpt-5 | openai | 79.6% | 81.1% | -1.6% | [-5.3%, +2.1%] |
| gpt-5-mini | openai | 77.7% | 75.9% | +1.8% | [-2.0%, +5.5%] |
| o3 | openai | 81.8% | 81.8% | -0.0% | [-3.5%, +3.6%] |
| qwen-2.5-72b | qwen | 65.9% | 63.9% | +2.0% | [-2.4%, +5.9%] |
| qwen-2.5-7b | qwen | 60.7% | 51.7% | +9.0% | [+5.1%, +13.0%] |

## 4b. Self-Preference Family Matrix

Cells are accuracy% (N). Rows are evaluator families; columns are generator
families. Diagonal cells are own-family (SPS) accuracy; off-diagonal cells are
cross-family.

| Eval ↓ / Gen → | anthropic | openai | google | meta | qwen |
|---|---:|---:|---:|---:|---:|
| **anthropic** | 77.4% (1857) | 70.9% (1629) | 62.9% (1263) | 66.1% (1902) | 69.2% (2007) |
| **openai** | 86.4% (1857) | 79.7% (1629) | 76.3% (1263) | 76.9% (1902) | 77.9% (2007) |
| **google** | 86.3% (1857) | 78.0% (1629) | 70.9% (1263) | 75.2% (1902) | 76.7% (2007) |
| **meta** | 65.0% (1238) | 61.3% (1086) | 46.7% (842) | 59.4% (1268) | 63.6% (1338) |
| **qwen** | 64.3% (1238) | 59.4% (1086) | 46.1% (842) | 57.9% (1268) | 63.3% (1338) |

## 5. Reasoning-Effect Deltas

Bootstrap 95% CI via 1000 resamples. δ = accuracy(reasoning config) − accuracy(standard config).

| Pair | Thinking config | Standard config | Thinking acc | Standard acc | δ | 95% CI |
|---|---|---|---:|---:|---:|---|
| Claude Opus 4.7: thinking vs standard | claude-opus-4.7-thinking | claude-opus-4.7 | 80.8% | 80.8% | -0.1% | [-2.0%, +2.0%] |
| Gemini 2.5 Pro: thinking vs standard | gemini-2.5-pro-thinking | gemini-2.5-pro | 82.4% | 81.5% | +0.9% | [-0.9%, +2.8%] |
| o3 vs GPT-5 | o3 | gpt-5 | 83.3% | 82.6% | +0.8% | [-1.2%, +2.7%] |
| DeepSeek-R1 vs DeepSeek-V3 | deepseek-r1 | deepseek-v3 | 76.9% | 70.1% | +6.8% | [+4.6%, +8.9%] |

## 6. Cost & Wall Ledger

| Slot | Config | Questions | Cost (effective) | Effective wall (est.) |
|---:|---|---:|---|---|
| 1 | claude-opus-4.7 | 3275 | $3.36 | ~1225s |
| 2 | claude-haiku-4.5 | 3275 | $0.44 | ~2058s |
| 3 | gpt-5 | 3275 | $22.03 | ~24107s |
| 4 | gpt-5-mini | 3275 | $2.83 | ~6388s |
| 5 | gemini-2.5-pro | 3275 | $29.60 | ~15504s |
| 6 | gemini-2.5-flash | 3275 | $0.12 | ~2211s |
| 7 | llama-3.3-70b | 3275 | $0.04 | ~1164s |
| 8 | llama-3.1-8b | 3275 | $0.01 | ~464s |
| 9 | deepseek-v3 | 3275 | $0.12 | ~1144s |
| 10 | qwen-2.5-72b | 3275 | $0.15 | ~851s |
| 11 | qwen-2.5-7b | 3275 | $0.12 | ~233s |
| 12 | mistral-large-2411 | 3275 | $0.87 | ~1042s |
| 13 | o3 | 3275 | $11.86 | ~9015s |
| 14 | gemini-2.5-pro-thinking | 3275 | $13.10 | ~3758s |
| 15 | deepseek-r1 | 3275 | $10.59 | ~45231s |
| 16 | claude-opus-4.7-thinking | 3275 | $3.54 | ~3213s |
| | **Local cost (computed)** | | **$98.68** | |
| | **OR cost (authoritative, 51,753 rows)** | | **$98.78** | |

## 7. Closed-Book vs Contextual Accuracy

CB-fail = questions tagged `closed_book_solvable` (parametric wine knowledge).
CB-pass = the rest (contextual wine reasoning). δ = acc(CB-fail) − acc(CB-pass);
positive means the model leans on memorised wine facts; negative means it does
better when it has to reason from the question.

| Slot | Config | n CB-fail | acc CB-fail | n CB-pass | acc CB-pass | δ | 95% CI |
|---:|---|---:|---:|---:|---:|---:|---|
| 1 | claude-opus-4.7 | 1601 | 97.3% | 1674 | 65.1% | +32.3% | [+29.9%, +34.8%] |
| 2 | claude-haiku-4.5 | 1601 | 70.2% | 1674 | 36.9% | +33.3% | [+30.2%, +36.4%] |
| 3 | gpt-5 | 1601 | 96.4% | 1674 | 69.4% | +27.0% | [+24.8%, +29.4%] |
| 4 | gpt-5-mini | 1601 | 94.7% | 1674 | 62.4% | +32.3% | [+29.4%, +34.8%] |
| 5 | gemini-2.5-pro | 1601 | 97.0% | 1674 | 66.7% | +30.3% | [+28.0%, +32.9%] |
| 6 | gemini-2.5-flash | 1601 | 92.6% | 1674 | 58.0% | +34.6% | [+31.7%, +37.3%] |
| 7 | llama-3.3-70b | 1601 | 85.6% | 1674 | 48.9% | +36.7% | [+33.9%, +39.6%] |
| 8 | llama-3.1-8b | 1601 | 76.0% | 1674 | 45.3% | +30.7% | [+27.4%, +33.9%] |
| 9 | deepseek-v3 | 1601 | 90.4% | 1674 | 50.6% | +39.8% | [+37.0%, +42.6%] |
| 10 | qwen-2.5-72b | 1601 | 86.8% | 1674 | 48.5% | +38.3% | [+35.3%, +41.2%] |
| 11 | qwen-2.5-7b | 1601 | 72.8% | 1674 | 41.5% | +31.4% | [+27.8%, +34.3%] |
| 12 | mistral-large-2411 | 1601 | 87.3% | 1674 | 51.3% | +36.1% | [+33.2%, +38.9%] |
| 13 | o3 | 1601 | 97.4% | 1674 | 69.9% | +27.5% | [+25.1%, +29.9%] |
| 14 | gemini-2.5-pro-thinking | 1601 | 97.4% | 1674 | 68.0% | +29.3% | [+27.0%, +31.9%] |
| 15 | deepseek-r1 | 1601 | 94.3% | 1674 | 60.2% | +34.0% | [+31.3%, +36.7%] |
| 16 | claude-opus-4.7-thinking | 1601 | 97.4% | 1674 | 64.8% | +32.6% | [+30.3%, +34.9%] |
| | **all configs (mean δ)** | | | | | **+32.9%** | |

## 8. Per-Config × Per-Difficulty Accuracy (%)

Difficulty 1 (easy) → 4 (hardest). Cells are accuracy on each difficulty tier.

| Config | 1 (easy) | 2 | 3 | 4 (hardest) |
|---|---|---|---|---|
| claude-opus-4.7 | 98.0% | 76.7% | 86.2% | 69.0% |
| claude-haiku-4.5 | 74.3% | 48.2% | 59.5% | 38.7% |
| gpt-5 | 98.3% | 82.2% | 87.0% | 69.1% |
| gpt-5-mini | 98.0% | 73.5% | 84.2% | 64.7% |
| gemini-2.5-pro | 98.6% | 78.9% | 86.8% | 68.4% |
| gemini-2.5-flash | 95.4% | 70.7% | 81.7% | 60.0% |
| llama-3.3-70b | 91.9% | 60.4% | 74.3% | 50.2% |
| llama-3.1-8b | 84.8% | 55.2% | 65.0% | 44.9% |
| deepseek-v3 | 95.8% | 65.7% | 75.8% | 52.3% |
| qwen-2.5-72b | 93.2% | 60.3% | 73.3% | 51.3% |
| qwen-2.5-7b | 82.0% | 50.4% | 59.7% | 43.2% |
| mistral-large-2411 | 94.4% | 62.9% | 72.9% | 53.9% |
| o3 | 98.4% | 81.2% | 88.9% | 71.1% |
| gemini-2.5-pro-thinking | 99.1% | 79.9% | 87.8% | 69.3% |
| deepseek-r1 | 97.5% | 73.9% | 81.5% | 62.0% |
| claude-opus-4.7-thinking | 98.3% | 76.6% | 86.5% | 68.5% |
| **all** | 93.6% | 68.5% | 78.2% | 58.5% |

## 9. Item Analysis

### 9a. Per-Question Accuracy Distribution

Histogram of how many questions were answered correctly by exactly k configs (out of N = 16).

| k correct out of 16 | # questions | % of corpus |
|---:|---:|---:|
| 0 | 43 | 1.3% |
| 1 | 65 | 2.0% |
| 2 | 96 | 2.9% |
| 3 | 58 | 1.8% |
| 4 | 85 | 2.6% |
| 5 | 98 | 3.0% |
| 6 | 112 | 3.4% |
| 7 | 116 | 3.5% |
| 8 | 149 | 4.5% |
| 9 | 140 | 4.3% |
| 10 | 153 | 4.7% |
| 11 | 154 | 4.7% |
| 12 | 185 | 5.6% |
| 13 | 191 | 5.8% |
| 14 | 282 | 8.6% |
| 15 | 496 | 15.1% |
| 16 | 852 | 26.0% |

### 9b. Ceiling and Floor Items

- **Ceiling items** (correct by >= 15 of 16 configs): 1348 items.
  Sample question_ids: `0018ba3d-6db5-4a0e-997b-220be4d2c7b8`, `003045cd-1bb6-42d8-ad62-0ddf0a0d710e`, `00547308-c5d4-4285-bf5f-955ddc5a3eb0`, `007d0a0e-6002-400b-8131-0e3052e652d0`, `0081729c-c583-4f1d-9b05-4741a612b3a5`
- **Floor items** (correct by 0 of 16 configs): 43 items.
  Sample question_ids: `01b8ebdb-d030-4a63-bb98-adc0b96642ac`, `1134c7d6-5ec8-4a7d-848e-3d83b0a880d2`, `193bcee8-8952-4f2a-82a6-ad811d10178b`, `1c1b75d3-cdfe-4734-ae66-87c354cbf726`, `3a5023ff-a7bf-42ed-9fff-16340d2dfdf0`

### 9c. Hardest and Easiest Items

**Top 10 hardest** (lowest mean accuracy first):

| question_id | mean accuracy |
|---|---:|
| `01b8ebdb-d030-4a63-bb98-adc0b96642ac` | 0.0% |
| `1134c7d6-5ec8-4a7d-848e-3d83b0a880d2` | 0.0% |
| `193bcee8-8952-4f2a-82a6-ad811d10178b` | 0.0% |
| `1c1b75d3-cdfe-4734-ae66-87c354cbf726` | 0.0% |
| `3a5023ff-a7bf-42ed-9fff-16340d2dfdf0` | 0.0% |
| `3ceda321-766a-40fb-a596-f8133adae634` | 0.0% |
| `3d76f4a5-fdfe-4434-bab5-3c5bd0df4afe` | 0.0% |
| `41ea4ae4-3781-4b64-9d5b-ce30e9a5a92e` | 0.0% |
| `43306f0b-7039-4037-a426-c3aaabf184fe` | 0.0% |
| `4924da7b-d1bc-4ab1-ae24-c40472f86113` | 0.0% |

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
| 12 | mistral-large-2411 | 2256 | $0.87 | $0.0004 |
| 4 | gpt-5-mini | 2561 | $2.83 | $0.0011 |
| 1 | claude-opus-4.7 | 2647 | $3.36 | $0.0013 |
| 16 | claude-opus-4.7-thinking | 2645 | $3.54 | $0.0013 |
| 15 | deepseek-r1 | 2517 | $10.59 | $0.0042 |
| 13 | o3 | 2729 | $11.86 | $0.0043 |
| 14 | gemini-2.5-pro-thinking | 2698 | $13.10 | $0.0049 |
| 3 | gpt-5 | 2704 | $22.03 | $0.0081 |
| 5 | gemini-2.5-pro | 2669 | $29.60 | $0.0111 |


---
_Generated at 20260504T082931Z by OenoBench report renderer._
