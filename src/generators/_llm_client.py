"""
OenoBench -- Unified LLM client for question generation.

Uses OpenRouter's OpenAI-compatible API to access all generator models
through a single interface. Handles retries, rate limiting, JSON parsing,
and structured logging.
"""

import copy
import os
import random
import re
import time
from dataclasses import dataclass, field
from functools import lru_cache

import openai
import orjson
from dotenv import load_dotenv
from loguru import logger
from tenacity import (
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

load_dotenv()


# -- Throttle configuration -------------------------------------------------
#
# Phase 2g.11 A1: replaces the hardcoded `time.sleep(1.5)` after every LLM
# call with a jittered floor gated by an env var. Tenacity already retries
# on RateLimitError with exponential backoff, so the 1.5s sleep was
# belt-and-suspenders and accounted for ~6.7h of v8's walltime
# (16k calls × 1.5s).
#
# Reversibility: if OpenRouter starts 429-storming, set
# OENOBENCH_LLM_THROTTLE_MS=1500 to restore old behaviour.

THROTTLE_ENV_VAR = "OENOBENCH_LLM_THROTTLE_MS"
_DEFAULT_THROTTLE_MS = 100


def _resolve_throttle_seconds() -> float:
    """Resolve the post-call throttle delay (seconds) with ±50% jitter.

    - Env var unset → default 100ms with ±50% jitter (range 50-150ms).
    - Env var = "0" (or any non-positive int) → return 0.0 (disables sleep).
    - Env var = positive int → that value in ms with ±50% jitter.
    - Env var = unparseable → log warning, fall back to default.
    """
    raw = os.environ.get(THROTTLE_ENV_VAR)
    if raw is None:
        ms = _DEFAULT_THROTTLE_MS
    else:
        try:
            ms = int(raw)
        except ValueError:
            logger.warning(
                "Invalid {} value {!r}; falling back to default {}ms",
                THROTTLE_ENV_VAR, raw, _DEFAULT_THROTTLE_MS,
            )
            ms = _DEFAULT_THROTTLE_MS
    if ms <= 0:
        return 0.0
    return (ms / 1000.0) * random.uniform(0.5, 1.5)


def _merge_throughput_failover(extra_body: dict | None) -> dict:
    """Deep-copy ``extra_body`` and force ``provider.sort = 'throughput'``.

    Preserves any other top-level keys (e.g. ``stream``) and any other
    sub-keys under ``provider`` the caller passed. Never mutates the input.
    """
    merged: dict = copy.deepcopy(extra_body) if extra_body else {}
    provider = merged.get("provider")
    if not isinstance(provider, dict):
        provider = {}
    provider["sort"] = "throughput"
    merged["provider"] = provider
    return merged

# -- Model registry --------------------------------------------------------

GENERATOR_MODELS = {
    "claude": "anthropic/claude-opus-4.7",
    "chatgpt": "openai/gpt-5.4",
    "gemini": "google/gemini-3.1-pro-preview",
    "llama": "nousresearch/hermes-3-llama-3.1-405b",    # Llama 3.1 405B via NousResearch
    "qwen": "qwen/qwen3-235b-a22b-2507",                 # Qwen 3 235B MoE (non-thinking)
}

DEFAULT_MODEL = "claude"

# Per-model max_tokens overrides. Gemini and Qwen produce verbose JSON
# responses that get truncated at the default 2000 tokens, causing parse
# failures. These models need a higher ceiling.
_MODEL_MAX_TOKENS = {
    "gemini": 6000,
    "qwen": 6000,
}

# -- Response dataclass -----------------------------------------------------


@dataclass
class LLMResponse:
    """Structured response from an LLM call."""

    content: str = ""
    parsed: dict | None = None
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0
    success: bool = False
    error: str | None = None


# -- JSON extraction --------------------------------------------------------

_FENCE_RE = re.compile(r"```(?:json)?\s*\n?(.*?)\n?\s*```", re.DOTALL)
_BRACE_RE = re.compile(r"\{.*\}", re.DOTALL)


def _try_parse_json(text: str) -> dict | None:
    """Try to parse JSON from text, handling markdown fences and raw braces.

    Only returns dicts — every caller in the codebase assumes a dict-shaped
    response (`.get(...)` or `... or {}`). If the LLM returns a JSON array
    or scalar, treat it as a parse failure rather than handing the caller
    an object whose interface doesn't match.

    Phase 2g.12 — Team D: prepend a fence-strip pre-pass that drops a
    leading ```<lang>?  fence and a trailing ``` fence before running the
    existing extraction modes. In v9, Gemini Pro produced 65/67 (97%) of
    parse failures, and most were responses wrapped in fences with
    arbitrary language tags (```json, ```jsonc, ```python, …) that the
    pre-existing ``_FENCE_RE`` (limited to ``(?:json)?``) did not match.
    The pre-pass is a no-op when the response has no fences, so behaviour
    for well-formed providers (Anthropic, OpenAI) is unchanged.
    """
    s = text.strip()
    # Strip leading/trailing markdown fences (e.g. ```json … ```,
    # ```jsonc … ```, ```python … ```, or bare ``` … ```).
    if s.startswith("```"):
        # Drop the opening fence including any language tag.
        first_newline = s.find("\n")
        if first_newline != -1:
            s = s[first_newline + 1:]
        else:
            s = s[3:]
        # Drop the trailing fence if present.
        if s.rstrip().endswith("```"):
            s = s.rstrip()
            s = s[:-3]
        s = s.strip()

    # Strip markdown code fences first (legacy regex path; still useful
    # when fences appear mid-string rather than at the boundaries).
    fence_match = _FENCE_RE.search(s)
    if fence_match:
        try:
            obj = orjson.loads(fence_match.group(1))
            if isinstance(obj, dict):
                return obj
        except (orjson.JSONDecodeError, ValueError):
            pass

    # Try raw string
    try:
        obj = orjson.loads(s)
        if isinstance(obj, dict):
            return obj
    except (orjson.JSONDecodeError, ValueError):
        pass

    # Regex-extract first {...} block
    brace_match = _BRACE_RE.search(s)
    if brace_match:
        try:
            obj = orjson.loads(brace_match.group(0))
            if isinstance(obj, dict):
                return obj
        except (orjson.JSONDecodeError, ValueError):
            pass

    return None


# -- Retry predicate --------------------------------------------------------


def _should_retry(exc: BaseException) -> bool:
    """Retry on rate limits and server errors (>= 500)."""
    if isinstance(exc, openai.RateLimitError):
        return True
    if isinstance(exc, openai.APIStatusError) and exc.status_code >= 500:
        return True
    return False


# -- Client class -----------------------------------------------------------


class LLMClient:
    """Unified LLM client using OpenRouter's OpenAI-compatible API."""

    def __init__(self, api_key: str | None = None):
        key = api_key or os.getenv("OPENROUTER_API_KEY")
        if not key:
            raise ValueError(
                "OPENROUTER_API_KEY not set. Provide it via .env or constructor."
            )
        self._client = openai.OpenAI(
            api_key=key,
            base_url="https://openrouter.ai/api/v1",
        )

    def _resolve_model(self, model: str) -> str:
        """Resolve a short name ('claude') to a full model ID."""
        return GENERATOR_MODELS.get(model, model)

    @retry(
        retry=retry_if_exception(_should_retry),
        wait=wait_exponential(min=2, max=16),
        stop=stop_after_attempt(4),
        reraise=True,
    )
    def _call_api(self, messages, model_id, temperature, max_tokens, json_mode, extra_body=None, timeout=None):
        """Make the actual API call (with tenacity retry)."""
        kwargs = dict(
            model=model_id,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        if extra_body:
            kwargs["extra_body"] = extra_body
        if timeout is not None:
            kwargs["timeout"] = timeout
        return self._client.chat.completions.create(**kwargs)

    def generate(
        self,
        prompt: str,
        system: str = "",
        model: str = "",
        temperature: float = 0.3,
        max_tokens: int = 2000,
        json_mode: bool = True,
        extra_body: dict | None = None,
        timeout: float | None = None,
    ) -> LLMResponse:
        """Generate a response from the specified model.

        Args:
            prompt: User message content.
            system: System message content. Empty string for no system message.
            model: Short name (e.g. 'claude') or full model ID.
            temperature: Sampling temperature.
            max_tokens: Maximum tokens in response.
            json_mode: If True, request JSON output format.
            extra_body: Optional dict merged into the request body. Used to
                pass OpenRouter-specific routing hints — e.g.
                ``{"provider": {"sort": "price"}}`` to force routing through
                the cheapest available provider for the model. Phase 2g.8
                introduced this for the verifier + paraphrase calls, which
                use sub-2K-token prompts and have no need for the >200K
                context tier that drives Gemini Pro to the $15/MTok output
                pricing band. See OpenRouter provider-routing docs for the
                full schema.
            timeout: Optional per-request timeout in seconds. When set and
                the SDK raises ``openai.APITimeoutError``, this client
                retries the call exactly once with ``provider.sort`` forced
                to ``"throughput"`` (merged into any caller-supplied
                ``extra_body``) so OpenRouter routes around the slow
                provider. When ``None`` (the default), no per-request
                timeout is applied and we do not catch ``APITimeoutError``
                ourselves — the existing failure-packaging path applies.

        Returns:
            LLMResponse with content, parsed JSON, token counts, and timing.
        """
        model_id = self._resolve_model(model or DEFAULT_MODEL)

        # Apply per-model max_tokens override if caller used the default
        if max_tokens == 2000:
            short_name = model or DEFAULT_MODEL
            max_tokens = _MODEL_MAX_TOKENS.get(short_name, max_tokens)

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        t0 = time.time()
        try:
            try:
                completion = self._call_api(
                    messages, model_id, temperature, max_tokens, json_mode,
                    extra_body=extra_body, timeout=timeout,
                )
            except openai.APITimeoutError as timeout_exc:
                # C1: long-tail timeout failover. Only intercept when the
                # caller asked for a timeout — otherwise fall through to the
                # generic failure-packaging path so behaviour is unchanged
                # for legacy call sites that don't pass timeout=.
                if timeout is None:
                    raise
                failover_extra_body = _merge_throughput_failover(extra_body)
                logger.info(
                    "LLM timeout failover | model={} | retrying with provider.sort=throughput",
                    model_id,
                )
                completion = self._call_api(
                    messages, model_id, temperature, max_tokens, json_mode,
                    extra_body=failover_extra_body, timeout=timeout,
                )
            latency_ms = int((time.time() - t0) * 1000)

            content = completion.choices[0].message.content or ""
            usage = completion.usage
            returned_model = completion.model or model_id

            parsed = _try_parse_json(content) if json_mode else None

            response = LLMResponse(
                content=content,
                parsed=parsed,
                model=returned_model,
                input_tokens=usage.prompt_tokens if usage else 0,
                output_tokens=usage.completion_tokens if usage else 0,
                latency_ms=latency_ms,
                success=True,
                error=None,
            )

            logger.info(
                "LLM call | model={} | tokens={}+{} | latency={}ms | json_ok={}",
                returned_model,
                response.input_tokens,
                response.output_tokens,
                latency_ms,
                parsed is not None,
            )

        except Exception as e:
            latency_ms = int((time.time() - t0) * 1000)
            logger.error(
                "LLM call failed | model={} | latency={}ms | error={}",
                model_id,
                latency_ms,
                str(e),
            )
            response = LLMResponse(
                model=model_id,
                latency_ms=latency_ms,
                error=str(e),
            )

        # Rate-limit spacing between calls (Phase 2g.11 A1: env-gated, default
        # 100ms ±50%; set OENOBENCH_LLM_THROTTLE_MS=0 to disable, or =1500 to
        # restore the pre-Phase-2g.11 behaviour).
        sleep_secs = _resolve_throttle_seconds()
        if sleep_secs > 0:
            time.sleep(sleep_secs)
        return response


# -- Singleton access -------------------------------------------------------

@lru_cache(maxsize=1)
def get_client() -> LLMClient:
    """Get singleton LLM client."""
    return LLMClient()
