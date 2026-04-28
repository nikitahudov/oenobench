"""Phase 2g.11 — A1 (env-gated post-call throttle) and C1 (timeout +
provider-failover hint) on ``LLMClient.generate``.

Pre-2g.11, ``generate`` ended with an unconditional ``time.sleep(1.5)`` after
every API call. On the v8 audit pilot that was ~6.7h of pure idle wall
time (16k calls × 1.5s) on top of OpenRouter latency. Tenacity already
retries ``RateLimitError`` with exponential backoff, so the global throttle
was belt-and-suspenders.

A1 replaces the hardcoded sleep with a jittered floor gated by
``OENOBENCH_LLM_THROTTLE_MS``:

- unset → default 100ms with ±50% jitter (50–150ms)
- ``"0"`` → no sleep at all
- positive int → that value in ms with ±50% jitter
- unparseable → log warning, fall back to default

C1 adds a ``timeout`` kwarg to ``LLMClient.generate``. When the SDK raises
``openai.APITimeoutError`` and the caller passed ``timeout``, the client
retries exactly once with ``extra_body`` merged with
``{"provider": {"sort": "throughput"}}`` so OpenRouter routes around the
slow provider. When ``timeout=None`` (the default), legacy behaviour is
preserved — the timeout exception is not specially intercepted.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx
import openai
import pytest

from src.generators._llm_client import LLMClient


# ─── Fake SDK plumbing (mirrors test_corpus_build_cost.py) ──────────────────


@dataclass
class _Msg:
    content: str = '{"ok": true}'


@dataclass
class _Choice:
    message: _Msg


@dataclass
class _Usage:
    prompt_tokens: int = 50
    completion_tokens: int = 10


@dataclass
class _Completion:
    choices: list
    usage: _Usage = None
    model: str = "anthropic/claude-opus-4.7"

    def __post_init__(self):
        if self.usage is None:
            self.usage = _Usage()


def _make_completion() -> _Completion:
    return _Completion(choices=[_Choice(message=_Msg())])


class _CapturingChatCompletions:
    """Records every ``create(**kwargs)`` call and returns a static success."""

    def __init__(self):
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return _make_completion()


class _ScriptedChatCompletions:
    """Replays a list of side-effects (Exception or Completion) per call."""

    def __init__(self, *side_effects):
        self.side_effects = list(side_effects)
        self.calls: list[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if not self.side_effects:
            raise AssertionError("scripted client out of side_effects")
        effect = self.side_effects.pop(0)
        if isinstance(effect, BaseException):
            raise effect
        return effect


def _install_fake(client: LLMClient, monkeypatch, completions) -> None:
    class _FakeChat:
        pass

    fake_chat = _FakeChat()
    fake_chat.completions = completions

    class _FakeClient:
        pass

    fake_client = _FakeClient()
    fake_client.chat = fake_chat
    monkeypatch.setattr(client, "_client", fake_client)


def _spy_sleep(monkeypatch) -> list[float]:
    """Replace ``time.sleep`` in the LLM-client module with a recording stub."""
    calls: list[float] = []

    def _record(secs):
        calls.append(secs)

    monkeypatch.setattr("src.generators._llm_client.time.sleep", _record)
    return calls


def _timeout_error() -> openai.APITimeoutError:
    return openai.APITimeoutError(request=httpx.Request("POST", "https://example.com"))


# ─── A1 — env-gated throttle ────────────────────────────────────────────────


def test_no_sleep_by_default(monkeypatch):
    """Env var unset → throttle defaults to 100ms with ±50% jitter (50–150ms).
    Critically must NOT be the legacy 1.5s.
    """
    monkeypatch.delenv("OENOBENCH_LLM_THROTTLE_MS", raising=False)
    sleep_calls = _spy_sleep(monkeypatch)

    client = LLMClient(api_key="dummy")
    _install_fake(client, monkeypatch, _CapturingChatCompletions())
    client.generate(prompt="hi")

    # Either zero (env var explicitly disables it — not the case here) or
    # exactly one call in the 50–150ms band. Never the legacy 1.5s.
    assert len(sleep_calls) <= 1
    if sleep_calls:
        secs = sleep_calls[0]
        assert 0.05 <= secs <= 0.15, f"throttle outside 50-150ms jitter band: {secs}"
        assert abs(secs - 1.5) > 0.5, "throttle must not be the legacy 1.5s"


def test_throttle_zero_disables_sleep(monkeypatch):
    """``OENOBENCH_LLM_THROTTLE_MS=0`` → ``time.sleep`` is not called."""
    monkeypatch.setenv("OENOBENCH_LLM_THROTTLE_MS", "0")
    sleep_calls = _spy_sleep(monkeypatch)

    client = LLMClient(api_key="dummy")
    _install_fake(client, monkeypatch, _CapturingChatCompletions())
    client.generate(prompt="hi")

    assert sleep_calls == [], f"sleep must not be called when throttle=0 (got {sleep_calls!r})"


def test_throttle_custom_value(monkeypatch):
    """``OENOBENCH_LLM_THROTTLE_MS=500`` → sleep arg lands in [0.25, 0.75]."""
    monkeypatch.setenv("OENOBENCH_LLM_THROTTLE_MS", "500")
    sleep_calls = _spy_sleep(monkeypatch)

    client = LLMClient(api_key="dummy")
    _install_fake(client, monkeypatch, _CapturingChatCompletions())
    client.generate(prompt="hi")

    assert len(sleep_calls) == 1
    secs = sleep_calls[0]
    assert 0.25 <= secs <= 0.75, f"500ms ±50% should be in [0.25, 0.75]; got {secs}"


def test_throttle_invalid_value_falls_back(monkeypatch):
    """Unparseable env var → log warning and use the 100ms default."""
    monkeypatch.setenv("OENOBENCH_LLM_THROTTLE_MS", "not-a-number")
    sleep_calls = _spy_sleep(monkeypatch)

    client = LLMClient(api_key="dummy")
    _install_fake(client, monkeypatch, _CapturingChatCompletions())
    client.generate(prompt="hi")

    assert len(sleep_calls) == 1
    secs = sleep_calls[0]
    assert 0.05 <= secs <= 0.15, (
        f"invalid env var should fall back to 100ms ±50% (50-150ms); got {secs}"
    )


# ─── C1 — timeout + provider failover ───────────────────────────────────────


def test_timeout_passed_through(monkeypatch):
    """``generate(timeout=10)`` must forward ``timeout=10`` into the SDK call."""
    monkeypatch.setenv("OENOBENCH_LLM_THROTTLE_MS", "0")
    _spy_sleep(monkeypatch)

    completions = _CapturingChatCompletions()
    client = LLMClient(api_key="dummy")
    _install_fake(client, monkeypatch, completions)

    response = client.generate(prompt="hi", timeout=10)

    assert response.success is True
    assert len(completions.calls) == 1
    assert completions.calls[0].get("timeout") == 10


def test_timeout_retry_with_throughput_sort(monkeypatch):
    """First call raises ``APITimeoutError``; second call must carry
    ``extra_body={"provider": {"sort": "throughput"}}`` and succeed.
    """
    monkeypatch.setenv("OENOBENCH_LLM_THROTTLE_MS", "0")
    _spy_sleep(monkeypatch)

    completions = _ScriptedChatCompletions(_timeout_error(), _make_completion())
    client = LLMClient(api_key="dummy")
    _install_fake(client, monkeypatch, completions)

    response = client.generate(prompt="hi", timeout=10)

    assert response.success is True
    assert len(completions.calls) == 2, "expected exactly one failover retry"
    # First call had no extra_body (caller passed nothing).
    assert "extra_body" not in completions.calls[0]
    # Second call must inject the throughput hint.
    assert completions.calls[1].get("extra_body") == {"provider": {"sort": "throughput"}}
    # Both calls must carry the per-request timeout.
    assert completions.calls[0].get("timeout") == 10
    assert completions.calls[1].get("timeout") == 10


def test_timeout_retry_preserves_user_extra_body(monkeypatch):
    """Caller's ``extra_body`` is merged on retry: ``provider.sort`` is forced
    to ``"throughput"`` but other top-level keys (``stream``) survive, and
    the original dict is not mutated.
    """
    monkeypatch.setenv("OENOBENCH_LLM_THROTTLE_MS", "0")
    _spy_sleep(monkeypatch)

    completions = _ScriptedChatCompletions(_timeout_error(), _make_completion())
    client = LLMClient(api_key="dummy")
    _install_fake(client, monkeypatch, completions)

    user_extra = {"provider": {"sort": "price"}, "stream": False}
    user_extra_snapshot = {"provider": {"sort": "price"}, "stream": False}

    response = client.generate(prompt="hi", timeout=10, extra_body=user_extra)

    assert response.success is True
    assert len(completions.calls) == 2
    # First call carried the user's price-sort hint verbatim.
    assert completions.calls[0].get("extra_body") == {
        "provider": {"sort": "price"},
        "stream": False,
    }
    # Retry merged: provider.sort flipped to throughput, stream preserved.
    assert completions.calls[1].get("extra_body") == {
        "provider": {"sort": "throughput"},
        "stream": False,
    }
    # The caller's original dict must not be mutated.
    assert user_extra == user_extra_snapshot


def test_no_timeout_means_no_failover(monkeypatch):
    """When ``timeout=None``, ``APITimeoutError`` is NOT specially handled —
    the call falls through the generic failure-packaging path and we do
    NOT issue a second request.
    """
    monkeypatch.setenv("OENOBENCH_LLM_THROTTLE_MS", "0")
    _spy_sleep(monkeypatch)

    completions = _ScriptedChatCompletions(_timeout_error())
    client = LLMClient(api_key="dummy")
    _install_fake(client, monkeypatch, completions)

    response = client.generate(prompt="hi")  # no timeout=

    assert response.success is False
    assert response.error is not None
    # Critically: only one call attempted by *our* code (tenacity does not
    # retry APITimeoutError because _should_retry only covers RateLimitError
    # and 5xx APIStatusError).
    assert len(completions.calls) == 1, (
        f"timeout=None must NOT trigger our failover retry; "
        f"got {len(completions.calls)} calls"
    )
