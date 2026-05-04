# OenoBench Evaluation Report

**Tag:** `eval_release_v1_2_full`  
**Run ID:** `8b0a0864-f3c6-4ec5-8f3d-e30271b8c3a0`  
**Corpus:** `public`  
**Started:** 2026-05-03 21:43:30.751589+00:00  
**Completed:** 2026-05-03 23:44:04.875266+00:00  
**Wall time:** 120m 34s  
**Total questions:** 3266  
**Total LLM calls:** 52256  
**Total cost (effective):** $98.33  
**Config slate:** 16 configs  

---

## 1. Per-Config Summary

| Slot | Config | Family | Reasoning | Accuracy | Parse % | p50 lat (ms) | p95 lat (ms) | Tokens in | Tokens out | Tokens reason | Cost |
|---:|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | claude-opus-4.7 | anthropic | standard | 81.0% | 99.4% | 1278 | 2114 | 588831 | 16254 | — | $3.35 |
| 2 | claude-haiku-4.5 | anthropic | standard | 53.3% | 80.3% | 1277 | 20989 | 331007 | 21328 | — | $0.44 |
| 3 | gpt-5 | openai | standard | 82.8% | 96.0% | 10406 | 48978 | 377889 | 2142407 | — | $21.90 |
| 4 | gpt-5-mini | openai | standard | 78.4% | 99.8% | 7389 | 24192 | 379342 | 1364211 | — | $2.82 |
| 5 | gemini-2.5-pro | google | standard | 81.7% | 97.0% | 9004 | 20478 | 359476 | 2901683 | — | $29.47 |
| 6 | gemini-2.5-flash | google | standard | 75.1% | 100.0% | 403 | 777 | 361492 | 3266 | — | $0.12 |
| 7 | llama-3.3-70b | meta | standard | 67.1% | 100.0% | 488 | 3103 | 403332 | 6532 | — | $0.04 |
| 8 | llama-3.1-8b | meta | standard | 60.5% | 100.0% | 374 | 883 | 403288 | 6532 | — | $0.01 |
| 9 | deepseek-v3 | deepseek | standard | 70.3% | 100.0% | 656 | 1141 | 363308 | 6528 | — | $0.12 |
| 10 | qwen-2.5-72b | qwen | standard | 67.4% | 100.0% | 532 | 2728 | 401567 | 3266 | — | $0.15 |
| 11 | qwen-2.5-7b | qwen | standard | 57.0% | 100.0% | 416 | 808 | 401787 | 6521 | — | $0.12 |
| 12 | mistral-large-2411 | mistral | standard | 69.1% | 100.0% | 294 | 2498 | 419508 | 6532 | — | $0.87 |
| 13 | o3 | openai | effort | 83.6% | 98.2% | 5697 | 22366 | 377942 | 1381104 | — | $11.80 |
| 14 | gemini-2.5-pro-thinking | google | explicit_budget | 82.6% | 100.0% | 5650 | 6606 | 361492 | 1261267 | — | $13.06 |
| 15 | deepseek-r1 | deepseek | explicit_budget | 77.1% | 98.4% | 35687 | 130266 | 365667 | 4112254 | — | $10.54 |
| 16 | claude-opus-4.7-thinking | anthropic | explicit_budget | 81.0% | 99.4% | 1279 | 2145 | 588798 | 23317 | — | $3.53 |

*OR-authoritative cost is available for 99% of rows (51,612/52,256); remaining use locally-computed cost.*

## 2. Per-Config × Per-Domain Accuracy (%)

| Config | Wine Regions | Grape Varieties | Producers | Viticulture | Winemaking | Wine Business |
|---|---|---|---|---|---|---|
| claude-opus-4.7 | 83.2% | 80.2% | 86.8% | 77.9% | 86.6% | 64.2% |
| claude-haiku-4.5 | 55.8% | 49.7% | 58.7% | 54.2% | 56.7% | 37.8% |
| gpt-5 | 88.1% | 78.2% | 88.4% | 82.8% | 80.7% | 63.0% |
| gpt-5-mini | 82.1% | 74.4% | 83.5% | 77.5% | 77.5% | 66.3% |
| gemini-2.5-pro | 87.0% | 78.8% | 89.0% | 78.5% | 77.5% | 61.8% |
| gemini-2.5-flash | 76.9% | 72.9% | 82.3% | 73.6% | 77.5% | 60.6% |
| llama-3.3-70b | 68.9% | 62.9% | 77.2% | 65.7% | 70.6% | 50.4% |
| llama-3.1-8b | 62.2% | 55.6% | 69.5% | 61.7% | 59.4% | 47.6% |
| deepseek-v3 | 74.4% | 68.5% | 73.2% | 70.8% | 69.0% | 51.2% |
| qwen-2.5-72b | 69.0% | 65.1% | 73.4% | 67.5% | 70.1% | 52.8% |
| qwen-2.5-7b | 59.1% | 55.6% | 59.4% | 57.4% | 57.8% | 44.7% |
| mistral-large-2411 | 71.5% | 65.6% | 75.4% | 69.4% | 73.3% | 51.6% |
| o3 | 88.4% | 81.3% | 90.9% | 80.3% | 76.5% | 65.4% |
| gemini-2.5-pro-thinking | 86.5% | 80.5% | 90.0% | 80.5% | 83.4% | 60.2% |
| deepseek-r1 | 80.5% | 73.6% | 85.6% | 72.2% | 76.5% | 64.6% |
| claude-opus-4.7-thinking | 83.2% | 80.9% | 87.0% | 78.7% | 84.0% | 61.4% |
| **all** | 76.0% | 70.2% | 79.4% | 71.8% | 73.6% | 56.5% |

## 3. Per-Config × Per-Strategy Accuracy (%)

| Config | FTQ | Scenario | Template | Comparative | Distractor |
|---|---|---|---|---|---|
| claude-opus-4.7 | 77.7% | 85.6% | 92.8% | 79.5% | 82.7% |
| claude-haiku-4.5 | 47.5% | 62.7% | 70.7% | 53.3% | 56.8% |
| gpt-5 | 79.9% | 80.9% | 95.4% | 79.5% | 87.9% |
| gpt-5-mini | 73.8% | 80.6% | 92.8% | 78.3% | 84.7% |
| gemini-2.5-pro | 77.4% | 87.5% | 93.1% | 82.4% | 86.4% |
| gemini-2.5-flash | 69.5% | 84.0% | 89.7% | 77.5% | 79.5% |
| llama-3.3-70b | 59.5% | 80.6% | 89.7% | 64.8% | 71.9% |
| llama-3.1-8b | 52.2% | 70.5% | 89.7% | 60.2% | 63.7% |
| deepseek-v3 | 64.5% | 80.3% | 86.4% | 71.7% | 73.3% |
| qwen-2.5-72b | 59.6% | 79.3% | 88.7% | 69.3% | 73.6% |
| qwen-2.5-7b | 49.1% | 72.1% | 78.9% | 57.0% | 61.0% |
| mistral-large-2411 | 62.7% | 80.6% | 87.4% | 67.6% | 73.3% |
| o3 | 79.9% | 84.3% | 94.9% | 84.8% | 88.4% |
| gemini-2.5-pro-thinking | 78.5% | 88.4% | 95.6% | 84.0% | 84.2% |
| deepseek-r1 | 73.4% | 75.5% | 92.5% | 77.0% | 80.7% |
| claude-opus-4.7-thinking | 77.3% | 85.6% | 93.6% | 80.3% | 83.0% |
| **all** | 67.6% | 79.9% | 89.5% | 73.0% | 76.9% |

## 4. Self-Preference Score (SPS)

Bootstrap 95% CI via 1000 resamples. δ = accuracy(own-family Qs) − accuracy(other Qs).

| Config | Family | Own-family acc | Other acc | δ | 95% CI |
|---|---|---:|---:|---:|---|
| claude-haiku-4.5 | anthropic | 58.8% | 48.8% | +10.0% | [+5.7%, +14.5%] |
| claude-opus-4.7 | anthropic | 86.6% | 77.5% | +9.1% | [+6.1%, +12.1%] |
| claude-opus-4.7-thinking | anthropic | 86.9% | 77.2% | +9.7% | [+6.5%, +13.1%] |
| deepseek-v3 | deepseek | — | 68.1% | — | — |
| deepseek-r1 | deepseek | — | 75.0% | — | — |
| gemini-2.5-flash | google | 64.3% | 74.7% | -10.4% | [-15.3%, -5.6%] |
| gemini-2.5-pro | google | 75.0% | 81.1% | -6.1% | [-10.7%, -1.8%] |
| gemini-2.5-pro-thinking | google | 74.0% | 82.0% | -8.0% | [-12.3%, -3.8%] |
| llama-3.1-8b | meta | 54.2% | 57.2% | -3.0% | [-7.3%, +1.4%] |
| llama-3.3-70b | meta | 65.5% | 63.6% | +1.9% | [-2.3%, +6.1%] |
| mistral-large-2411 | mistral | — | 66.6% | — | — |
| gpt-5 | openai | 79.7% | 81.4% | -1.7% | [-5.4%, +2.1%] |
| gpt-5-mini | openai | 77.9% | 76.1% | +1.7% | [-2.4%, +5.4%] |
| o3 | openai | 81.9% | 82.1% | -0.1% | [-3.9%, +3.3%] |
| qwen-2.5-72b | qwen | 66.1% | 64.1% | +2.0% | [-2.1%, +6.0%] |
| qwen-2.5-7b | qwen | 60.9% | 51.9% | +9.0% | [+4.5%, +13.2%] |

## 4b. Self-Preference Family Matrix

Cells are accuracy% (N). Rows are evaluator families; columns are generator
families. Diagonal cells are own-family (SPS) accuracy; off-diagonal cells are
cross-family.

| Eval ↓ / Gen → | anthropic | openai | google | meta | qwen |
|---|---:|---:|---:|---:|---:|
| **anthropic** | 77.4% (1857) | 71.0% (1626) | 63.0% (1260) | 66.6% (1887) | 69.4% (2001) |
| **openai** | 86.4% (1857) | 79.8% (1626) | 76.5% (1260) | 77.5% (1887) | 78.1% (2001) |
| **google** | 86.3% (1857) | 78.1% (1626) | 71.1% (1260) | 75.8% (1887) | 76.9% (2001) |
| **meta** | 65.0% (1238) | 61.4% (1084) | 46.8% (840) | 59.9% (1258) | 63.8% (1334) |
| **qwen** | 64.3% (1238) | 59.5% (1084) | 46.2% (840) | 58.3% (1258) | 63.5% (1334) |

## 5. Reasoning-Effect Deltas

Bootstrap 95% CI via 1000 resamples. δ = accuracy(reasoning config) − accuracy(standard config).

| Pair | Thinking config | Standard config | Thinking acc | Standard acc | δ | 95% CI |
|---|---|---|---:|---:|---:|---|
| Claude Opus 4.7: thinking vs standard | claude-opus-4.7-thinking | claude-opus-4.7 | 81.0% | 81.0% | -0.1% | [-1.9%, +1.8%] |
| Gemini 2.5 Pro: thinking vs standard | gemini-2.5-pro-thinking | gemini-2.5-pro | 82.6% | 81.7% | +0.9% | [-1.0%, +2.8%] |
| o3 vs GPT-5 | o3 | gpt-5 | 83.6% | 82.8% | +0.8% | [-1.0%, +2.6%] |
| DeepSeek-R1 vs DeepSeek-V3 | deepseek-r1 | deepseek-v3 | 77.1% | 70.3% | +6.8% | [+4.6%, +8.8%] |

## 6. Cost & Wall Ledger

| Slot | Config | Questions | Cost (effective) | Effective wall (est.) |
|---:|---|---:|---|---|
| 1 | claude-opus-4.7 | 3266 | $3.35 | ~1222s |
| 2 | claude-haiku-4.5 | 3266 | $0.44 | ~2052s |
| 3 | gpt-5 | 3266 | $21.90 | ~24040s |
| 4 | gpt-5-mini | 3266 | $2.82 | ~6370s |
| 5 | gemini-2.5-pro | 3266 | $29.47 | ~15461s |
| 6 | gemini-2.5-flash | 3266 | $0.12 | ~2205s |
| 7 | llama-3.3-70b | 3266 | $0.04 | ~1161s |
| 8 | llama-3.1-8b | 3266 | $0.01 | ~463s |
| 9 | deepseek-v3 | 3266 | $0.12 | ~1141s |
| 10 | qwen-2.5-72b | 3266 | $0.15 | ~848s |
| 11 | qwen-2.5-7b | 3266 | $0.12 | ~232s |
| 12 | mistral-large-2411 | 3266 | $0.87 | ~1039s |
| 13 | o3 | 3266 | $11.80 | ~8991s |
| 14 | gemini-2.5-pro-thinking | 3266 | $13.06 | ~3748s |
| 15 | deepseek-r1 | 3266 | $10.54 | ~45106s |
| 16 | claude-opus-4.7-thinking | 3266 | $3.53 | ~3204s |
| | **Local cost (computed)** | | **$98.24** | |
| | **OR cost (authoritative, 51,612 rows)** | | **$98.33** | |

## 7. Closed-Book vs Contextual Accuracy

CB-fail = questions tagged `closed_book_solvable` (parametric wine knowledge).
CB-pass = the rest (contextual wine reasoning). δ = acc(CB-fail) − acc(CB-pass);
positive means the model leans on memorised wine facts; negative means it does
better when it has to reason from the question.

| Slot | Config | n CB-fail | acc CB-fail | n CB-pass | acc CB-pass | δ | 95% CI |
|---:|---|---:|---:|---:|---:|---:|---|
| 1 | claude-opus-4.7 | 1601 | 97.3% | 1665 | 65.4% | +31.9% | [+29.5%, +34.2%] |
| 2 | claude-haiku-4.5 | 1601 | 70.2% | 1665 | 37.1% | +33.1% | [+30.0%, +36.8%] |
| 3 | gpt-5 | 1601 | 96.4% | 1665 | 69.7% | +26.6% | [+24.3%, +29.2%] |
| 4 | gpt-5-mini | 1601 | 94.7% | 1665 | 62.8% | +31.9% | [+29.5%, +34.5%] |
| 5 | gemini-2.5-pro | 1601 | 97.0% | 1665 | 67.0% | +30.0% | [+27.5%, +32.5%] |
| 6 | gemini-2.5-flash | 1601 | 92.6% | 1665 | 58.3% | +34.3% | [+31.6%, +37.0%] |
| 7 | llama-3.3-70b | 1601 | 85.6% | 1665 | 49.2% | +36.4% | [+33.3%, +39.3%] |
| 8 | llama-3.1-8b | 1601 | 76.0% | 1665 | 45.6% | +30.4% | [+27.1%, +33.6%] |
| 9 | deepseek-v3 | 1601 | 90.4% | 1665 | 50.9% | +39.6% | [+36.6%, +42.5%] |
| 10 | qwen-2.5-72b | 1601 | 86.8% | 1665 | 48.8% | +38.1% | [+35.1%, +40.8%] |
| 11 | qwen-2.5-7b | 1601 | 72.8% | 1665 | 41.7% | +31.1% | [+27.7%, +34.3%] |
| 12 | mistral-large-2411 | 1601 | 87.3% | 1665 | 51.5% | +35.8% | [+32.8%, +38.9%] |
| 13 | o3 | 1601 | 97.4% | 1665 | 70.3% | +27.1% | [+24.8%, +29.4%] |
| 14 | gemini-2.5-pro-thinking | 1601 | 97.4% | 1665 | 68.4% | +29.0% | [+26.7%, +31.3%] |
| 15 | deepseek-r1 | 1601 | 94.3% | 1665 | 60.5% | +33.7% | [+31.1%, +36.5%] |
| 16 | claude-opus-4.7-thinking | 1601 | 97.4% | 1665 | 65.2% | +32.3% | [+30.0%, +34.7%] |
| | **all configs (mean δ)** | | | | | **+32.6%** | |

## 8. Per-Config × Per-Difficulty Accuracy (%)

Difficulty 1 (easy) → 4 (hardest). Cells are accuracy on each difficulty tier.

| Config | 1 (easy) | 2 | 3 | 4 (hardest) |
|---|---|---|---|---|
| claude-opus-4.7 | 98.0% | 77.0% | 86.7% | 69.1% |
| claude-haiku-4.5 | 74.3% | 48.3% | 59.9% | 38.8% |
| gpt-5 | 98.3% | 82.4% | 87.5% | 69.2% |
| gpt-5-mini | 98.0% | 73.7% | 84.7% | 64.8% |
| gemini-2.5-pro | 98.6% | 79.2% | 87.3% | 68.5% |
| gemini-2.5-flash | 95.4% | 70.9% | 82.2% | 60.1% |
| llama-3.3-70b | 91.9% | 60.6% | 74.8% | 50.3% |
| llama-3.1-8b | 84.8% | 55.4% | 65.3% | 45.0% |
| deepseek-v3 | 95.8% | 65.9% | 76.3% | 52.4% |
| qwen-2.5-72b | 93.2% | 60.5% | 73.7% | 51.4% |
| qwen-2.5-7b | 82.0% | 50.6% | 60.0% | 43.3% |
| mistral-large-2411 | 94.4% | 63.1% | 73.3% | 54.0% |
| o3 | 98.4% | 81.4% | 89.4% | 71.2% |
| gemini-2.5-pro-thinking | 99.1% | 80.2% | 88.3% | 69.4% |
| deepseek-r1 | 97.5% | 74.2% | 82.0% | 62.1% |
| claude-opus-4.7-thinking | 98.3% | 76.8% | 87.0% | 68.6% |
| **all** | 93.6% | 68.8% | 78.7% | 58.7% |

## 9. Item Analysis

### 9a. Per-Question Accuracy Distribution

Histogram of how many questions were answered correctly by exactly k configs (out of N = 16).

| k correct out of 16 | # questions | % of corpus |
|---:|---:|---:|
| 0 | 34 | 1.0% |
| 1 | 65 | 2.0% |
| 2 | 96 | 2.9% |
| 3 | 58 | 1.8% |
| 4 | 85 | 2.6% |
| 5 | 98 | 3.0% |
| 6 | 112 | 3.4% |
| 7 | 116 | 3.6% |
| 8 | 149 | 4.6% |
| 9 | 140 | 4.3% |
| 10 | 153 | 4.7% |
| 11 | 154 | 4.7% |
| 12 | 185 | 5.7% |
| 13 | 191 | 5.8% |
| 14 | 282 | 8.6% |
| 15 | 496 | 15.2% |
| 16 | 852 | 26.1% |

### 9b. Ceiling and Floor Items

- **Ceiling items** (correct by >= 15 of 16 configs): 1348 items.
  Sample question_ids: `0018ba3d-6db5-4a0e-997b-220be4d2c7b8`, `003045cd-1bb6-42d8-ad62-0ddf0a0d710e`, `00547308-c5d4-4285-bf5f-955ddc5a3eb0`, `007d0a0e-6002-400b-8131-0e3052e652d0`, `0081729c-c583-4f1d-9b05-4741a612b3a5`
- **Floor items** (correct by 0 of 16 configs): 34 items.
  Sample question_ids: `01b8ebdb-d030-4a63-bb98-adc0b96642ac`, `193bcee8-8952-4f2a-82a6-ad811d10178b`, `1c1b75d3-cdfe-4734-ae66-87c354cbf726`, `3a5023ff-a7bf-42ed-9fff-16340d2dfdf0`, `3ceda321-766a-40fb-a596-f8133adae634`

### 9c. Hardest and Easiest Items

**Top 10 hardest** (lowest mean accuracy first):

| question_id | mean accuracy |
|---|---:|
| `01b8ebdb-d030-4a63-bb98-adc0b96642ac` | 0.0% |
| `193bcee8-8952-4f2a-82a6-ad811d10178b` | 0.0% |
| `1c1b75d3-cdfe-4734-ae66-87c354cbf726` | 0.0% |
| `3a5023ff-a7bf-42ed-9fff-16340d2dfdf0` | 0.0% |
| `3ceda321-766a-40fb-a596-f8133adae634` | 0.0% |
| `3d76f4a5-fdfe-4434-bab5-3c5bd0df4afe` | 0.0% |
| `41ea4ae4-3781-4b64-9d5b-ce30e9a5a92e` | 0.0% |
| `43306f0b-7039-4037-a426-c3aaabf184fe` | 0.0% |
| `5c9e22f9-fbbe-4284-beef-1ba0d3213308` | 0.0% |
| `5cc99a9d-0a8f-4deb-88e5-4ffdc95453cc` | 0.0% |

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
| 4 | gpt-5-mini | 2561 | $2.82 | $0.0011 |
| 1 | claude-opus-4.7 | 2647 | $3.35 | $0.0013 |
| 16 | claude-opus-4.7-thinking | 2645 | $3.53 | $0.0013 |
| 15 | deepseek-r1 | 2517 | $10.54 | $0.0042 |
| 13 | o3 | 2729 | $11.80 | $0.0043 |
| 14 | gemini-2.5-pro-thinking | 2698 | $13.06 | $0.0048 |
| 3 | gpt-5 | 2704 | $21.90 | $0.0081 |
| 5 | gemini-2.5-pro | 2669 | $29.47 | $0.0110 |


---
_Generated at 20260504T112905Z by OenoBench report renderer._
