"""Phase 5 telemetry fix — tests for generation_id, provider, or_cost on LLMResponse.

Mirrors the mocking pattern from test_llm_client_throttle.py.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from src.generators._llm_client import LLMClient


# ─── Fake SDK plumbing (mirrors test_llm_client_throttle.py) ────────────────


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
    cost: float | None = None
    completion_tokens_details: object = None


@dataclass
class _Completion:
    choices: list
    usage: _Usage = None
    model: str = "anthropic/claude-opus-4.7"
    id: str = "gen-abc"
    provider: str | None = "Anthropic"

    def __post_init__(self):
        if self.usage is None:
            self.usage = _Usage()


def _make_completion(**kwargs) -> _Completion:
    return _Completion(choices=[_Choice(message=_Msg())], **kwargs)


class _StaticChatCompletions:
    """Returns a pre-built completion on every create() call."""

    def __init__(self, completion: _Completion):
        self.completion = completion

    def create(self, **kwargs):
        return self.completion


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


# ─── Tests ───────────────────────────────────────────────────────────────────


def test_response_has_generation_id(monkeypatch):
    """completion.id='gen-abc' → LLMResponse.generation_id == 'gen-abc'."""
    monkeypatch.setenv("OENOBENCH_LLM_THROTTLE_MS", "0")
    completion = _make_completion(id="gen-abc")
    client = LLMClient(api_key="dummy")
    _install_fake(client, monkeypatch, _StaticChatCompletions(completion))

    response = client.generate(prompt="hi")

    assert response.success is True
    assert response.generation_id == "gen-abc"


def test_response_has_provider(monkeypatch):
    """completion.provider='Anthropic' → LLMResponse.provider == 'Anthropic'."""
    monkeypatch.setenv("OENOBENCH_LLM_THROTTLE_MS", "0")
    completion = _make_completion(provider="Anthropic")
    client = LLMClient(api_key="dummy")
    _install_fake(client, monkeypatch, _StaticChatCompletions(completion))

    response = client.generate(prompt="hi")

    assert response.success is True
    assert response.provider == "Anthropic"


def test_response_has_or_cost(monkeypatch):
    """completion.usage.cost=0.00048 → LLMResponse.or_cost == 0.00048."""
    monkeypatch.setenv("OENOBENCH_LLM_THROTTLE_MS", "0")
    usage = _Usage(prompt_tokens=71, completion_tokens=5, cost=0.00048)
    completion = _make_completion(usage=usage)
    client = LLMClient(api_key="dummy")
    _install_fake(client, monkeypatch, _StaticChatCompletions(completion))

    response = client.generate(prompt="hi")

    assert response.success is True
    assert response.or_cost == pytest.approx(0.00048)


def test_response_or_cost_handles_missing(monkeypatch):
    """No 'cost' attribute on usage → LLMResponse.or_cost is None."""
    monkeypatch.setenv("OENOBENCH_LLM_THROTTLE_MS", "0")

    # Use a usage object that has no 'cost' attribute at all.
    @dataclass
    class _UsageNoCost:
        prompt_tokens: int = 50
        completion_tokens: int = 10

    usage = _UsageNoCost()
    completion = _make_completion(usage=usage)
    client = LLMClient(api_key="dummy")
    _install_fake(client, monkeypatch, _StaticChatCompletions(completion))

    response = client.generate(prompt="hi")

    assert response.success is True
    assert response.or_cost is None


def test_response_provider_handles_missing(monkeypatch):
    """No 'provider' attribute on completion → LLMResponse.provider is None."""
    monkeypatch.setenv("OENOBENCH_LLM_THROTTLE_MS", "0")

    # Build a completion without the 'provider' attribute.
    @dataclass
    class _CompletionNoProvider:
        choices: list
        usage: _Usage = None
        model: str = "anthropic/claude-opus-4.7"
        id: str = "gen-xyz"

        def __post_init__(self):
            if self.usage is None:
                self.usage = _Usage()

    completion = _CompletionNoProvider(choices=[_Choice(message=_Msg())])
    client = LLMClient(api_key="dummy")
    _install_fake(client, monkeypatch, _StaticChatCompletions(completion))

    response = client.generate(prompt="hi")

    assert response.success is True
    assert response.provider is None


def test_response_handles_string_cost(monkeypatch):
    """usage.cost='0.001' (string) → LLMResponse.or_cost == 0.001 (float)."""
    monkeypatch.setenv("OENOBENCH_LLM_THROTTLE_MS", "0")

    # Some providers return cost as a string; we must cast it to float.
    @dataclass
    class _UsageStringCost:
        prompt_tokens: int = 50
        completion_tokens: int = 10
        cost: str = "0.001"

    usage = _UsageStringCost()
    completion = _make_completion(usage=usage)
    client = LLMClient(api_key="dummy")
    _install_fake(client, monkeypatch, _StaticChatCompletions(completion))

    response = client.generate(prompt="hi")

    assert response.success is True
    assert response.or_cost == pytest.approx(0.001)
    assert isinstance(response.or_cost, float)


def test_response_failure_path_has_none(monkeypatch):
    """Exception during API call → all three new fields are None on failure response."""
    monkeypatch.setenv("OENOBENCH_LLM_THROTTLE_MS", "0")

    class _ExplodingCompletions:
        def create(self, **kwargs):
            raise RuntimeError("simulated API failure")

    client = LLMClient(api_key="dummy")
    _install_fake(client, monkeypatch, _ExplodingCompletions())

    response = client.generate(prompt="hi")

    assert response.success is False
    assert response.error is not None
    assert response.generation_id is None
    assert response.provider is None
    assert response.or_cost is None
