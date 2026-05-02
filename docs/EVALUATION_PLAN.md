# OenoBench — Evaluation Model Slate (Phase 5)

**Status:** Slate locked 2026-05-02. Stratified-vs-full reasoning subset decision deferred (see §6).
**Author:** auto-drafted by Claude Code from the slate-selection conversation on 2026-05-02
**Linked memory:** `~/.claude/projects/-home-winebench-oenobench/memory/project_eval_slate.md`

---

## 1. Goals

The evaluation slate must support four claims in the NeurIPS 2026 paper:

1. **Capability separation** — the benchmark distinguishes frontier from mid/low-tier models.
2. **Cost-effect analysis** — within each major proprietary family, the cheap variant scores measurably worse than the flagship (or surprisingly close, which itself is a finding).
3. **Self-Preference Score (SPS) analysis** — every generator family that produced questions is also evaluated, so we can test whether models score higher on questions they authored.
4. **Reasoning-trace effect** — for each major family, compare a standard run against a thinking/reasoning-mode run.

## 2. Slate

16 model configurations across 14 unique OpenRouter IDs. Two IDs (Claude Opus 4.7, Gemini 2.5 Pro) appear twice with different `reasoning` parameters.

### 2.1 Standard configurations (12)

| # | OpenRouter ID | Tier | Family | Open weights | Role |
|---|---|---|---|---|---|
| 1 | `anthropic/claude-opus-4.7` | Frontier | Anthropic | No | SPS generator |
| 2 | `anthropic/claude-haiku-4.5` | Low-cost | Anthropic | No | Cost pair to #1 |
| 3 | `openai/gpt-5` | Frontier | OpenAI | No | SPS generator |
| 4 | `openai/gpt-5-mini` | Low-cost | OpenAI | No | Cost pair to #3 |
| 5 | `google/gemini-2.5-pro` | Frontier | Google | No | SPS generator |
| 6 | `google/gemini-2.5-flash` | Low-cost | Google | No | Cost pair to #5 |
| 7 | `meta-llama/llama-3.3-70b-instruct` | Frontier open | Meta | Yes | SPS generator |
| 8 | `meta-llama/llama-3.1-8b-instruct` | Small | Meta | Yes | Cost pair to #7 |
| 9 | `deepseek/deepseek-chat` (V3) | Frontier open | DeepSeek | Yes | Non-Western open frontier |
| 10 | `qwen/qwen-2.5-72b-instruct` | Frontier open | Alibaba | Yes | Non-Western open frontier |
| 11 | `qwen/qwen-2.5-7b-instruct` | Small | Alibaba | Yes | Cost pair to #10 |
| 12 | `mistralai/mistral-large-2411` | Mid-tier | Mistral | Open weights (research lic.) | EU provider; French-wine corpus heuristic |

### 2.2 Reasoning configurations (4)

| # | OpenRouter ID | Mode | Family | Notes |
|---|---|---|---|---|
| 13 | `openai/o3` | Native reasoning model | OpenAI | Dedicated SKU; `reasoning.effort=high` |
| 14 | `google/gemini-2.5-pro` | Same ID as #5, `reasoning` param on | Google | Distinct eval run, recorded as separate config |
| 15 | `deepseek/deepseek-r1` | Native reasoning model | DeepSeek | Dedicated SKU |
| 16 | `anthropic/claude-opus-4.7` | Same ID as #1, extended thinking on | Anthropic | Distinct eval run; OpenRouter has no `:thinking` SKU |

**Anthropic note:** Anthropic does not expose a separate reasoning SKU on OpenRouter. Extended thinking is enabled per-request via the `reasoning` parameter (`{"max_tokens": N}`) on the same `claude-opus-4.7` model ID. Same pattern applies to Gemini 2.5 Pro. Our eval harness will treat these as distinct evaluation configurations identified by `(model_id, reasoning_config)`.

## 3. Diversity matrix

| Axis | Distribution |
|---|---|
| Proprietary / open-weight | 10 / 6 |
| Frontier / mid / small | 10 / 1 (Mistral) / 5 |
| Reasoning / standard | 4 / 12 |
| Generator-family coverage (SPS) | Claude ✅ GPT ✅ Gemini ✅ Llama ✅ |
| Within-family cost pairs | Claude (Opus/Haiku), GPT (5/5-mini), Gemini (Pro/Flash), Llama (70B/8B), Qwen (72B/7B), DeepSeek (V3/R1) |
| Provider geography | US (Anthropic, OpenAI, Google, Meta), China (DeepSeek, Alibaba), France (Mistral) |

## 4. Pricing snapshot (verified on OpenRouter 2026-05-02)

Per 1M tokens (input / output, USD):

| Model | Input | Output |
|---|---:|---:|
| `anthropic/claude-opus-4.7` | $5.00 | $25.00 |
| `anthropic/claude-haiku-4.5` | $1.00 | $5.00 |
| `openai/gpt-5` | $1.25 | $10.00 |
| `openai/gpt-5-mini` | $0.25 | $2.00 |
| `openai/o3` | $2.00 | $8.00 |
| `google/gemini-2.5-pro` | $1.25 | $10.00 |
| `google/gemini-2.5-flash` | $0.30 | $2.50 |
| `meta-llama/llama-3.3-70b-instruct` | $0.10 | $0.32 |
| `meta-llama/llama-3.1-8b-instruct` | $0.02 | $0.05 |
| `deepseek/deepseek-chat` (V3) | $0.32 | $0.89 |
| `deepseek/deepseek-r1` | $0.70 | $2.50 |
| `qwen/qwen-2.5-72b-instruct` | $0.36 | $0.40 |
| `qwen/qwen-2.5-7b-instruct` | $0.04 | $0.10 |
| `mistralai/mistral-large-2411` | $2.00 | $6.00 |

**Premium reasoning alternative (not in slate):** `openai/gpt-5-pro` at $15 / $120 — ~15× the cost of `o3` for likely small quality gain. Reserved as a stretch addition if budget allows.

## 5. Cost projections

**Per-question assumption (single-letter output mode, see §7):** 800 input tokens (question + 4 MC options + system prompt), **5 output tokens** (single letter A/B/C/D plus minimal envelope). Reasoning configurations add a capped **2,000 reasoning tokens** billed at output rate, plus the same 5 visible output tokens.

### 5.1 Full eval (5,000 questions × all 16 configurations)

| Block | Configs | Subtotal |
|---|---|---:|
| Standard block | 12 | **~$49** |
| Reasoning block at full 5k | 4 | ~$492 |
| **Total (no headroom)** | 16 | **~$541** |
| Total with 30% headroom | 16 | **~$700** |

Per-config breakdown for the 12 standard configs at 5k Qs:

| Config | Cost |
|---|---:|
| Claude Opus 4.7 | $20.6 |
| Mistral Large 2411 | $8.2 |
| GPT-5 | $5.3 |
| Gemini 2.5 Pro | $5.3 |
| Claude Haiku 4.5 | $4.1 |
| Qwen 2.5 72B | $1.5 |
| DeepSeek V3 | $1.3 |
| Gemini 2.5 Flash | $1.3 |
| GPT-5-mini | $1.1 |
| Llama 3.3 70B | $0.4 |
| Qwen 2.5 7B | $0.2 |
| Llama 3.1 8B | $0.1 |

Reasoning configs at 5k Qs (dominated by thinking tokens — single-letter visible-output cap doesn't help the hidden reasoning stream):

| Config | Cost |
|---|---:|
| Claude Opus 4.7 + thinking | ~$270 |
| Gemini 2.5 Pro + thinking | ~$105 |
| `openai/o3` | ~$89 |
| DeepSeek R1 | ~$28 |

### 5.2 Stratified-subset reasoning (5,000 standard + 1,000 reasoning)

| Block | Configs | Subtotal |
|---|---|---:|
| Standard block at 5k | 12 | ~$49 |
| Reasoning block at 1k stratified | 4 | ~$98 |
| **Total (no headroom)** | 16 | **~$147** |
| Total with 30% headroom | 16 | **~$200** |

Stratification proposal (TBD): 1,000-question subset balanced across the six domains and the five generation strategies, sampled with seed lock for reproducibility.

**Compared to the original 400-token-output assumption,** the standard block dropped from ~$172 → ~$49 (-71%); reasoning block largely unchanged because hidden thinking tokens dominate. Total full-eval projection: ~$754 → ~$541 (-28%).

## 6. Open decisions

1. **Stratified vs full reasoning runs.** User leaning toward stratified subset; final call deferred. Decision driver is whether SPS and reasoning-effect signals reach significance at n=1k per reasoning config — a power calculation will follow once Phase 3 produces a calibrated answer-key confidence distribution.
2. **Retries / determinism.** Single pass per (question, config) at `temperature=0` proposed. If a config fails to return parseable JSON, retry up to 3× then mark `eval_skipped`.
3. **OpenRouter routing.** Default `provider` settings; capture `provider_used` and `generation_id` in `evaluation_answers` for each row so downstream paper reproducibility doesn't depend on OR's load balancer state.

## 7. Implementation notes for the eval harness

### 7.1 Single-letter output mode (cost optimization)

Every configuration must answer with **exactly one letter (A, B, C, or D)** — no explanation, no JSON envelope unless strictly required. This caps standard-model output billing at ~5 tokens per question.

Layered enforcement, applied in this order:

1. **System prompt:** `"You are taking a multiple-choice exam. Reply with exactly one letter — A, B, C, or D — and nothing else. No explanation, no punctuation, no whitespace before or after."`
2. **`max_tokens=5`** on the request. Hard cap on visible output. (Tight enough to prevent prose, loose enough to absorb leading whitespace or a stray newline.)
3. **Stop sequences** where supported: `["\n\n", ".", " ", ":"]` to halt at the first non-letter character.
4. **`logit_bias`** where supported (OpenAI-compatible providers — currently `openai/*` and some others on OR): bias the four single-letter token IDs upward by ~+10 logits and the EOS/newline tokens slightly upward; do not zero out other tokens (some letters are sub-tokens of legitimate vocabulary). This is a hint, not a constraint.
5. **Post-hoc parse:** regex `r"\b([ABCD])\b"` against the response. First match wins. If no match, retry once with a stricter prompt; if still no match, store `eval_skipped` and log the raw response for offline analysis.

**Reasoning configs:** the visible-output cap (`max_tokens=5`) still applies, but reasoning tokens are billed separately. Cap reasoning effort via OpenRouter's normalized `reasoning` parameter:
- `openai/o3`: `{"reasoning": {"effort": "medium"}}` — `effort` is the supported lever; medium gives ~1k–2k reasoning tokens. Map to high only if accuracy on the stratified subset is unacceptable.
- `deepseek/deepseek-r1`: `{"reasoning": {"max_tokens": 2000}}` — explicit budget cap.
- `anthropic/claude-opus-4.7` (extended thinking): `{"reasoning": {"max_tokens": 2000}}`.
- `google/gemini-2.5-pro` (thinking): `{"reasoning": {"max_tokens": 2000}}`.

If a provider rejects the `reasoning` schema, fall back to the provider-native form (`thinking_config`, etc.) — exact schemas to be confirmed against OR docs at harness implementation time.

### 7.2 Parallel execution

Wall-time goal: complete the full 16-config × 5,000-Q eval in under one hour. The eval harness must fan out across two axes simultaneously:

- **Across configurations** (16-way fan-out): launch all 16 configurations as independent tasks. Each config has its own OpenRouter session, retry/backoff policy, and progress writer. No config blocks any other.
- **Within each configuration** (per-config concurrency): batch questions with `asyncio.Semaphore(N)` where `N` is the per-config concurrency cap. Recommended starting values:
  - Frontier proprietary (Opus, GPT-5, Gemini Pro): N=20
  - Low-cost proprietary + Mistral Large: N=40
  - Open-weight via OR aggregator: N=20 (OR back-end pools have lower per-key limits)
  - Reasoning configs: N=10 (latency per call is 10–30s; higher concurrency triggers OR throttling without speedup)

Aggregate concurrency ≈ 16 configs × 20 avg = ~320 in-flight requests. Configure the OpenRouter HTTP client with `limit=400`, `limit_per_host=400`.

**Failure handling:**
- Transient HTTP errors (429, 5xx, timeout): exponential backoff with jitter, max 3 retries.
- Per-config quotas: track per-config 5xx rate; if a config exceeds 10% over 100 requests, pause that config for 60s, then resume. Other configs unaffected.
- Crash-safe: persist each `(config, question_id, answer, latency_ms, generation_id)` row to Postgres immediately on response. Resuming a crashed run skips rows already in `evaluation_answers`.

**Wall-time projection** (single-letter output, capped reasoning, target concurrency):

| Block | Avg latency / call | Effective throughput | Wall for 5k Qs |
|---|---:|---:|---:|
| Standard configs (12 × 5k = 60k calls) | ~3s | ~80 calls/s aggregate | ~12 min |
| Reasoning configs (4 × 5k = 20k calls) | ~25s | ~1.6 calls/s per config (×4 = ~6.4/s) | ~52 min |
| **Total (parallel across blocks)** | — | — | **~55 min** (bounded by reasoning block) |

If reasoning is run at 1k stratified: reasoning block drops to ~10 min and total wall ≈ 12–15 min.

### 7.3 Schema and persistence

- Track configurations as `(model_id, reasoning_config)` tuples; persist to `evaluation_runs.config_json`.
- Store every response with: `provider_used`, `generation_id`, `request_tokens`, `completion_tokens`, `reasoning_tokens` (where reported), `latency_ms`, `parsed_answer`, `raw_response`. The first three guarantee reproducibility against OpenRouter's load balancer state.
- All 14 distinct IDs verified live on OpenRouter as of 2026-05-02 via `https://openrouter.ai/api/v1/models`.

## 8. Provenance

- Slate-selection conversation: 2026-05-02 with project owner.
- Pricing source: OpenRouter `/api/v1/models` snapshot, 2026-05-02.
- Generator alignment confirmed against `CURRENT_STATUS.md` §"Generation Models (via OpenRouter)" table — Claude/GPT/Gemini/Llama families all represented.
