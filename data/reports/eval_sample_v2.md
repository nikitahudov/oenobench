# OenoBench Evaluation Report

**Tag:** `eval_sample_v2`  
**Run ID:** `6ef6eff2-9c50-439c-8aff-b414300727fc`  
**Corpus:** `sample`  
**Started:** 2026-05-02 14:36:04.484875+00:00  
**Completed:** 2026-05-02 15:20:15.293010+00:00  
**Wall time:** 44m 10s  
**Total questions:** 1062  
**Total LLM calls:** 16992  
**Total cost:** $33.03  
**Config slate:** 16 configs  

---

## 0. Headline Leaderboard (16 configs × 1062 questions, full coverage)

Grouped by `(model_id, reasoning_config)` so reasoning siblings (Claude Opus
standard vs extended-thinking; Gemini 2.5 Pro standard vs thinking) appear
as separate rows. **All 16 configs reached full 1062 coverage.** Reported
accuracy is correct-rate over total attempted (eval_skipped rows count
against the denominator); parse rate excludes skipped rows.

| Rank | Slot | Config | Model ID | Reasoning | n | Skipped | Accuracy | Cost |
|---:|---:|---|---|---|---:|---:|---:|---:|
| 1 | 14 | gemini-2.5-pro-thinking | `google/gemini-2.5-pro` | `{"max_tokens": 512}` | 1062 | 0 | **83.6%** | $4.22 |
| 2 | 16 | claude-opus-4.7-thinking | `anthropic/claude-opus-4.7` | `{"max_tokens": 512}` | 1062 | 6 | 81.6% | $1.31 |
| 3 | 13 | o3 | `openai/o3` | `{"effort": "medium"}` | 1062 | 41 | 81.5% | $4.10 |
| 4 | 1 | claude-opus-4.7 | `anthropic/claude-opus-4.7` | — | 1062 | 4 | 80.9% | $1.21 |
| 5 | 3 | gpt-5 | `openai/gpt-5` | — | 1062 | 98 | 79.6% | $7.35 |
| 6 | 4 | gpt-5-mini | `openai/gpt-5-mini` | — | 1062 | 23 | 78.2% | $0.97 |
| 7 | 5 | gemini-2.5-pro | `google/gemini-2.5-pro` | — | 1062 | 101 | 78.1% | $9.62 |
| 8 | 15 | deepseek-r1 | `deepseek/deepseek-r1` | `{"max_tokens": 512}` | 1062 | 24 | 77.5% | $3.62 |
| 9 | 6 | gemini-2.5-flash | `google/gemini-2.5-flash` | — | 1062 | 0 | 76.8% | $0.04 |
| 10 | 9 | deepseek-v3 | `deepseek/deepseek-chat` | — | 1062 | 0 | 71.8% | $0.04 |
| 11 | 12 | mistral-large-2411 | `mistralai/mistral-large-2411` | — | 1062 | 0 | 70.8% | $0.32 |
| 12 | 7 | llama-3.3-70b | `meta-llama/llama-3.3-70b-instruct` | — | 1062 | 0 | 69.2% | $0.02 |
| 13 | 8 | llama-3.1-8b | `meta-llama/llama-3.1-8b-instruct` | — | 1062 | 0 | 64.2% | <$0.01 |
| 14 | 10 | qwen-2.5-72b | `qwen/qwen-2.5-72b-instruct` | — | 1062 | 93 | 62.3% | $0.05 |
| 15 | 11 | qwen-2.5-7b | `qwen/qwen-2.5-7b-instruct` | — | 1062 | 0 | 60.8% | $0.01 |
| 16 | 2 | claude-haiku-4.5 | `anthropic/claude-haiku-4.5` | — | 1062 | 191 | 56.5% | $0.16 |

### Reasoning-effect deltas (paired within family, n=1062 per config)

| Pair | Thinking acc | Standard acc | δ |
|---|---:|---:|---:|
| Gemini 2.5 Pro: thinking vs standard | 83.6% | 78.1% | **+5.5 pp** |
| DeepSeek R1 vs DeepSeek V3 | 77.5% | 71.8% | **+5.7 pp** |
| `o3` vs GPT-5 | 81.5% | 79.6% | **+1.9 pp** |
| Claude Opus 4.7: thinking vs standard | 81.6% | 80.9% | **+0.7 pp** (within noise) |

### Within-family cost-tier deltas

| Family | Frontier acc | Cheap-tier acc | δ |
|---|---:|---:|---:|
| Anthropic | 80.9% (Opus) | 56.5% (Haiku) | **−24.4 pp** — driven by Haiku's 191 skips, not capability |
| OpenAI | 79.6% (GPT-5) | 78.2% (GPT-5-mini) | **−1.4 pp** |
| Google | 78.1% (Gemini Pro) | 76.8% (Gemini Flash) | **−1.3 pp** |
| Meta | 69.2% (Llama 70B) | 64.2% (Llama 8B) | **−5.0 pp** |
| Qwen | 62.3% (72B) | 60.8% (7B) | **−1.5 pp** |
| DeepSeek | 71.8% (V3) | 77.5% (R1, reasoning) | **+5.7 pp** (R1 is reasoning, not "cheap") |

### Caveats

- **Claude Haiku 4.5 high skip rate** (191/1062 ≈ 18%). Many responses were truncated before emitting a letter; bumping `max_tokens` further would likely recover 5-10pp accuracy. Defer to post-deadline.
- **Qwen 2.5 72B** had 93 empty-output responses (8.8%) — DeepInfra-side issue with our request shape; provider switch to Novita might fix.
- **Gemini 2.5 Pro standard** consumed 1.35M output tokens for $9.62 because it always reasons internally; significantly more expensive than its thinking variant ($4.22) which is bounded at 512 reasoning tokens.
- **The auto-rendered §1 table below groups by `model_name` only** and so merges siblings (slot 1 + slot 16 → "anthropic/claude-opus-4.7" with 2124 questions; slot 5 + slot 14 → "google/gemini-2.5-pro" with 2124). Use this §0 leaderboard for slot-aware numbers; §2-§3 grids are still useful for relative ranking by domain/strategy.

---

## 1. Per-Config Summary

| Slot | Config | Family | Reasoning | Accuracy | Parse % | p50 lat (ms) | p95 lat (ms) | Tokens in | Tokens out | Tokens reason | Cost |
|---:|---|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| — | anthropic/claude-haiku-4.5 | — | — | 56.5% | 82.0% | 1109 | 20911 | 122841 | 6965 | — | $0.16 |
| — | anthropic/claude-opus-4.7 | — | — | 81.3% | 99.5% | 1324 | 2462 | 429605 | 14665 | — | $2.51 |
| — | deepseek/deepseek-chat | — | — | 71.8% | 100.0% | 685 | 1300 | 131453 | 2124 | — | $0.04 |
| — | deepseek/deepseek-r1 | — | — | 77.5% | 97.7% | 41012 | 147438 | 132105 | 1411914 | — | $3.62 |
| — | google/gemini-2.5-flash | — | — | 76.8% | 100.0% | 432 | 797 | 130190 | 1062 | — | $0.04 |
| — | google/gemini-2.5-pro | — | — | 80.8% | 95.2% | 6464 | 17398 | 259561 | 1351975 | — | $13.84 |
| — | meta-llama/llama-3.1-8b-instruct | — | — | 64.2% | 100.0% | 552 | 1006 | 144697 | 2124 | — | $0.00 |
| — | meta-llama/llama-3.3-70b-instruct | — | — | 69.2% | 100.0% | 448 | 1771 | 144708 | 2124 | — | $0.02 |
| — | mistralai/mistral-large-2411 | — | — | 70.8% | 100.0% | 356 | 2918 | 151603 | 2124 | — | $0.32 |
| — | openai/gpt-5 | — | — | 79.6% | 90.8% | 11759 | 50156 | 135654 | 717952 | — | $7.35 |
| — | openai/gpt-5-mini | — | — | 78.2% | 97.8% | 6472 | 21795 | 136321 | 466326 | — | $0.97 |
| — | openai/o3 | — | — | 81.5% | 96.1% | 6011 | 24493 | 135806 | 478728 | — | $4.10 |
| — | qwen/qwen-2.5-72b-instruct | — | — | 62.3% | 91.2% | 495 | 5851 | 130977 | 969 | — | $0.05 |
| — | qwen/qwen-2.5-7b-instruct | — | — | 60.8% | 100.0% | 425 | 1074 | 143799 | 2124 | — | $0.01 |

## 2. Per-Config × Per-Domain Accuracy (%)

| Config | Wine Regions | Grape Varieties | Producers | Viticulture | Winemaking | Wine Business |
|---|---|---|---|---|---|---|
| anthropic/claude-haiku-4.5 | 61.0% | 50.3% | 55.2% | 62.6% | 57.8% | 55.8% |
| anthropic/claude-opus-4.7 | 85.4% | 72.4% | 86.1% | 81.6% | 88.2% | 84.3% |
| deepseek/deepseek-chat | 74.9% | 62.5% | 77.6% | 75.9% | 75.5% | 73.3% |
| deepseek/deepseek-r1 | 82.5% | 65.4% | 84.8% | 78.7% | 82.4% | 86.0% |
| google/gemini-2.5-flash | 79.4% | 68.9% | 83.0% | 79.9% | 78.4% | 79.1% |
| google/gemini-2.5-pro | 86.3% | 69.7% | 91.5% | 81.9% | 84.3% | 80.2% |
| meta-llama/llama-3.1-8b-instruct | 71.3% | 53.8% | 72.1% | 70.7% | 63.7% | 55.8% |
| meta-llama/llama-3.3-70b-instruct | 76.7% | 55.8% | 76.4% | 75.9% | 72.5% | 67.4% |
| mistralai/mistral-large-2411 | 77.1% | 60.6% | 75.8% | 75.3% | 78.4% | 64.0% |
| openai/gpt-5 | 85.7% | 66.7% | 87.3% | 85.1% | 82.4% | 81.4% |
| openai/gpt-5-mini | 83.4% | 67.3% | 83.6% | 81.0% | 83.3% | 81.4% |
| openai/o3 | 85.2% | 69.9% | 90.9% | 89.1% | 79.4% | 82.6% |
| qwen/qwen-2.5-72b-instruct | 70.4% | 51.9% | 67.3% | 65.5% | 60.8% | 65.1% |
| qwen/qwen-2.5-7b-instruct | 66.4% | 54.5% | 61.2% | 65.5% | 60.8% | 59.3% |
| **all** | 78.6% | 63.2% | 79.4% | 77.0% | 76.3% | 73.8% |

## 3. Per-Config × Per-Strategy Accuracy (%)

| Config | FTQ | Scenario | Template | Comparative | Distractor |
|---|---|---|---|---|---|
| anthropic/claude-haiku-4.5 | 52.4% | 62.6% | 63.4% | 54.0% | 53.1% |
| anthropic/claude-opus-4.7 | 82.0% | 85.6% | 83.8% | 70.9% | 79.1% |
| deepseek/deepseek-chat | 69.7% | 75.4% | 81.2% | 66.9% | 62.2% |
| deepseek/deepseek-r1 | 79.7% | 77.9% | 83.2% | 66.9% | 70.4% |
| google/gemini-2.5-flash | 73.6% | 81.0% | 82.7% | 71.9% | 78.6% |
| google/gemini-2.5-pro | 82.1% | 80.8% | 84.0% | 72.3% | 81.1% |
| meta-llama/llama-3.1-8b-instruct | 57.9% | 71.3% | 80.6% | 56.8% | 57.1% |
| meta-llama/llama-3.3-70b-instruct | 64.9% | 76.9% | 80.6% | 59.0% | 65.3% |
| mistralai/mistral-large-2411 | 67.0% | 77.9% | 79.1% | 61.2% | 71.4% |
| openai/gpt-5 | 82.5% | 80.5% | 82.7% | 64.7% | 79.6% |
| openai/gpt-5-mini | 78.8% | 79.5% | 82.2% | 64.7% | 83.7% |
| openai/o3 | 83.4% | 82.1% | 85.3% | 71.2% | 78.6% |
| qwen/qwen-2.5-72b-instruct | 58.3% | 68.2% | 73.3% | 54.0% | 59.2% |
| qwen/qwen-2.5-7b-instruct | 54.9% | 69.7% | 70.2% | 52.5% | 63.3% |
| **all** | 72.0% | 77.2% | 80.0% | 64.4% | 71.4% |

## 4. Self-Preference Score (SPS)

Bootstrap 95% CI via 1000 resamples. δ = accuracy(own-family Qs) − accuracy(other Qs).

| Config | Family | Own-family acc | Other acc | δ | 95% CI |
|---|---|---:|---:|---:|---|
| — | — | — | — | — | No own-family questions found |

## 5. Reasoning-Effect Deltas

Bootstrap 95% CI via 1000 resamples. δ = accuracy(reasoning config) − accuracy(standard config).

| Pair | Thinking config | Standard config | Thinking acc | Standard acc | δ | 95% CI |
|---|---|---|---:|---:|---:|---|
| Claude Opus 4.7: thinking vs standard | claude-opus-4.7-thinking | claude-opus-4.7 | — | — | — | no data |
| Gemini 2.5 Pro: thinking vs standard | gemini-2.5-pro-thinking | gemini-2.5-pro | — | — | — | no data |
| o3 vs GPT-5 | o3 | gpt-5 | — | — | — | no data |
| DeepSeek-R1 vs DeepSeek-V3 | deepseek-r1 | deepseek-v3 | — | — | — | no data |

## 6. Cost & Wall Ledger

| Slot | Config | Questions | Cost | Effective wall (est.) |
|---:|---|---:|---|---|
| — | anthropic/claude-haiku-4.5 | 1062 | $0.16 | — |
| — | anthropic/claude-opus-4.7 | 2124 | $2.51 | — |
| — | deepseek/deepseek-chat | 1062 | $0.04 | — |
| — | deepseek/deepseek-r1 | 1062 | $3.62 | — |
| — | google/gemini-2.5-flash | 1062 | $0.04 | — |
| — | google/gemini-2.5-pro | 2124 | $13.84 | — |
| — | meta-llama/llama-3.1-8b-instruct | 1062 | $0.00 | — |
| — | meta-llama/llama-3.3-70b-instruct | 1062 | $0.02 | — |
| — | mistralai/mistral-large-2411 | 1062 | $0.32 | — |
| — | openai/gpt-5 | 1062 | $7.35 | — |
| — | openai/gpt-5-mini | 1062 | $0.97 | — |
| — | openai/o3 | 1062 | $4.10 | — |
| — | qwen/qwen-2.5-72b-instruct | 1062 | $0.05 | — |
| — | qwen/qwen-2.5-7b-instruct | 1062 | $0.01 | — |
| | **Grand total** | | **$33.03** | |


---
_Generated at 20260502T152024Z by OenoBench report renderer._
