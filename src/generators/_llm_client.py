"""
OenoBench -- Unified LLM client for question generation.

Uses OpenRouter's OpenAI-compatible API to access all generator models
through a single interface. Handles retries, rate limiting, JSON parsing,
and structured logging.
"""

import os
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

# -- Model registry --------------------------------------------------------

GENERATOR_MODELS = {
    "claude": "anthropic/claude-opus-4-6",
    "chatgpt": "openai/chatgpt-5.4",
    "gemini": "google/gemini-3.1",
    "llama": "meta-llama/llama-3.1-405b-instruct",
    "qwen": "qwen/qwen-3.5",
}

DEFAULT_MODEL = "claude"

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
    """Try to parse JSON from text, handling markdown fences and raw braces."""
    # Strip markdown code fences first
    fence_match = _FENCE_RE.search(text)
    if fence_match:
        try:
            return orjson.loads(fence_match.group(1))
        except (orjson.JSONDecodeError, ValueError):
            pass

    # Try raw string
    try:
        return orjson.loads(text)
    except (orjson.JSONDecodeError, ValueError):
        pass

    # Regex-extract first {...} block
    brace_match = _BRACE_RE.search(text)
    if brace_match:
        try:
            return orjson.loads(brace_match.group(0))
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
    def _call_api(self, messages, model_id, temperature, max_tokens, json_mode):
        """Make the actual API call (with tenacity retry)."""
        kwargs = dict(
            model=model_id,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        return self._client.chat.completions.create(**kwargs)

    def generate(
        self,
        prompt: str,
        system: str = "",
        model: str = "",
        temperature: float = 0.3,
        max_tokens: int = 2000,
        json_mode: bool = True,
    ) -> LLMResponse:
        """Generate a response from the specified model.

        Args:
            prompt: User message content.
            system: System message content. Empty string for no system message.
            model: Short name (e.g. 'claude') or full model ID.
            temperature: Sampling temperature.
            max_tokens: Maximum tokens in response.
            json_mode: If True, request JSON output format.

        Returns:
            LLMResponse with content, parsed JSON, token counts, and timing.
        """
        model_id = self._resolve_model(model or DEFAULT_MODEL)
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        t0 = time.time()
        try:
            completion = self._call_api(
                messages, model_id, temperature, max_tokens, json_mode
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

        # Rate-limit spacing between calls
        time.sleep(1.5)
        return response


# -- Singleton access -------------------------------------------------------

@lru_cache(maxsize=1)
def get_client() -> LLMClient:
    """Get singleton LLM client."""
    return LLMClient()
