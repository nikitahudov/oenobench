"""Phase 2g.8 corpus-build cost optimizations.

Two changes under test:

1. ``insert_question_gated(pre_screened=...)`` lets the caller hand in a
   ``GateResult`` it already computed, so the wrapper doesn't run the gate
   a second time. This is what template_generator.py uses to gate BEFORE
   running paraphrase + verifier (Gemini), saving ~60% of those Gemini
   calls on audit_pilot_v6 where the gate flagged most templates.

2. ``LLMClient.generate(extra_body=...)`` forwards arbitrary OpenRouter
   request fields to the underlying chat-completions call. The verifier
   and paraphrase modules pass ``{"provider": {"sort": "price"}}`` so
   OpenRouter routes their sub-2K-token prompts to the cheapest provider
   for the target model — i.e. the standard sub-200K-context tier
   instead of the long-context tier that drove Gemini Pro to $15/MTok
   output pricing on audit_pilot_v6.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

from src.generators import _closed_book_gate, _question_db
from src.generators._closed_book_gate import GateResult


# ─── Fixtures ────────────────────────────────────────────────────────────────


_OPTS = [
    {"id": "A", "text": "Nebbiolo"},
    {"id": "B", "text": "Barbera"},
    {"id": "C", "text": "Dolcetto"},
    {"id": "D", "text": "Sangiovese"},
]


def _question(**overrides):
    base = {
        "question_id": "TEST-COST-001",
        "question_text": "Which grape is in Barolo?",
        "options": _OPTS,
        "correct_answer": "A",
        "difficulty": "1",
        "question_type": "multiple_choice",
        "domain": "wine_regions",
    }
    base.update(overrides)
    return base


# ─── Optimization 1: pre_screened wires through the wrapper ─────────────────


def test_insert_question_gated_uses_pre_screened_skips_inner_gate(monkeypatch):
    """When the caller supplies a pre_screened verdict, the wrapper must
    NOT call screen_question / the OpenRouter gate API again.
    """

    def explode(*_a, **_kw):
        raise AssertionError("screen_question must not be called when pre_screened is set")

    monkeypatch.setattr(_question_db, "screen_question", explode)
    monkeypatch.setattr(_closed_book_gate, "_call_gate", explode)
    monkeypatch.setattr(_question_db, "count_closed_book_solvable", lambda: 0)

    captured = {}

    def fake_insert(question_data, generation_meta, fact_ids, source_ids):
        captured["meta"] = generation_meta
        captured["data"] = question_data
        return "uuid-pre-screened"

    monkeypatch.setattr(_question_db, "insert_question", fake_insert)

    pre_gate = GateResult(
        passed=False,
        applied=True,
        reason="reject: pre-screened by caller (selected=A conf=0.95 >= 0.6)",
        selected="A",
        confidence=0.95,
        matched_gold=True,
    )

    q_uuid, gate = _question_db.insert_question_gated(
        question_data=_question(),
        generation_meta={"generator": "template_only", "generation_method": "template"},
        fact_ids=[],
        source_ids=[],
        pre_screened=pre_gate,
    )

    assert q_uuid == "uuid-pre-screened"
    # Wrapper still applied the relabel routing because pre_gate.passed=False.
    assert gate.relabeled is True
    assert captured["data"]["difficulty"] == "1"
    assert "closed_book_solvable" in captured["data"]["tags"]
    # And the verdict still got stashed in generation_meta.
    assert captured["meta"]["raw_response"]["gate"]["selected"] == "A"


def test_insert_question_gated_pre_screened_pass_path(monkeypatch):
    """A pre-screened PASS (gate did not flag) goes straight to insert with
    no relabel and no quota check.
    """

    def explode(*_a, **_kw):
        raise AssertionError("screen_question must not be called when pre_screened is set")

    monkeypatch.setattr(_question_db, "screen_question", explode)

    def quota_explode():
        raise AssertionError("count_closed_book_solvable must not be called on the pass path")

    monkeypatch.setattr(_question_db, "count_closed_book_solvable", quota_explode)

    captured = {}

    def fake_insert(question_data, generation_meta, fact_ids, source_ids):
        captured["data"] = question_data
        return "uuid-pass"

    monkeypatch.setattr(_question_db, "insert_question", fake_insert)

    pre_gate = GateResult(
        passed=True,
        applied=True,
        reason="pass: gate picked B (gold=A)",
        selected="B",
        confidence=0.4,
        matched_gold=False,
    )

    q_uuid, gate = _question_db.insert_question_gated(
        question_data=_question(difficulty="2"),
        generation_meta={"generator": "template_only", "generation_method": "template"},
        fact_ids=[],
        source_ids=[],
        pre_screened=pre_gate,
    )

    assert q_uuid == "uuid-pass"
    assert gate.passed is True
    assert gate.relabeled is False
    # Original difficulty preserved.
    assert captured["data"]["difficulty"] == "2"
    # No closed_book_solvable tag added on the pass path.
    assert "closed_book_solvable" not in (captured["data"].get("tags") or [])


def test_insert_question_gated_pre_screened_quota_full(monkeypatch):
    """Pre-screened reject + quota full → drop, no insert."""
    monkeypatch.setattr(
        _question_db, "screen_question",
        lambda **_kw: (_ for _ in ()).throw(
            AssertionError("must not call screen_question with pre_screened set")
        ),
    )
    # Quota is at the 25%-of-default-corpus cap (10000 × 0.25 = 2500).
    monkeypatch.setattr(_question_db, "count_closed_book_solvable", lambda: 2500)

    def explode_insert(*_a, **_kw):
        raise AssertionError("insert_question must not be called when quota is full")

    monkeypatch.setattr(_question_db, "insert_question", explode_insert)

    pre_gate = GateResult(
        passed=False,
        applied=True,
        reason="reject: gate solved closed-book (selected=A conf=0.9 >= 0.6)",
        selected="A",
        confidence=0.9,
        matched_gold=True,
    )

    q_uuid, gate = _question_db.insert_question_gated(
        question_data=_question(),
        generation_meta={"generator": "template_only", "generation_method": "template"},
        fact_ids=[],
        source_ids=[],
        pre_screened=pre_gate,
    )

    assert q_uuid is None
    assert gate.quota_full is True
    assert gate.relabeled is False


def test_insert_question_gated_no_pre_screened_falls_back_to_inner_gate(monkeypatch):
    """Backwards compatibility: callers that don't pass pre_screened still
    get the original behaviour (inner screen_question call).
    """
    called = {}

    def fake_screen(**kwargs):
        called["screen"] = kwargs
        return GateResult(
            passed=True,
            applied=True,
            reason="pass: gate picked B (gold=A)",
            selected="B",
            confidence=0.3,
            matched_gold=False,
        )

    monkeypatch.setattr(_question_db, "screen_question", fake_screen)
    monkeypatch.setattr(_question_db, "insert_question", lambda *a, **kw: "uuid-fallback")

    q_uuid, gate = _question_db.insert_question_gated(
        question_data=_question(),
        generation_meta={"generator": "test", "generation_method": "test"},
        fact_ids=[],
        source_ids=[],
    )
    assert q_uuid == "uuid-fallback"
    assert "screen" in called
    assert gate.passed is True


# ─── Optimization 3: extra_body forwards to the OpenRouter call ─────────────


@dataclass
class _Msg:
    content: str = '{"chosen": "A"}'


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
    model: str = "google/gemini-3.1-pro-preview-20260219"

    def __post_init__(self):
        if self.usage is None:
            self.usage = _Usage()


def test_llm_client_generate_forwards_extra_body(monkeypatch):
    """LLMClient.generate(extra_body={...}) must pass the dict through to
    chat.completions.create as the extra_body kwarg, where the OpenAI SDK
    forwards it into the request body OpenRouter receives.
    """
    from src.generators._llm_client import LLMClient

    captured = {}

    class _FakeChatCompletions:
        def create(self, **kwargs):
            captured.update(kwargs)
            return _Completion(choices=[_Choice(message=_Msg())])

    class _FakeChat:
        completions = _FakeChatCompletions()

    class _FakeClient:
        chat = _FakeChat()

    client = LLMClient(api_key="dummy")
    monkeypatch.setattr(client, "_client", _FakeClient())
    # Suppress the post-call sleep so the test runs fast.
    monkeypatch.setattr("src.generators._llm_client.time.sleep", lambda *_: None)

    response = client.generate(
        prompt="hello",
        model="gemini",
        extra_body={"provider": {"sort": "price"}},
    )

    assert response.success is True
    # The captured request kwargs include extra_body verbatim.
    assert captured.get("extra_body") == {"provider": {"sort": "price"}}


def test_llm_client_generate_no_extra_body_omits_kwarg(monkeypatch):
    """When extra_body is not passed, it must NOT appear in the request kwargs
    (so we don't accidentally override OpenRouter's default routing for the
    main generators and the audit panel).
    """
    from src.generators._llm_client import LLMClient

    captured = {}

    class _FakeChatCompletions:
        def create(self, **kwargs):
            captured.update(kwargs)
            return _Completion(choices=[_Choice(message=_Msg())])

    class _FakeChat:
        completions = _FakeChatCompletions()

    class _FakeClient:
        chat = _FakeChat()

    client = LLMClient(api_key="dummy")
    monkeypatch.setattr(client, "_client", _FakeClient())
    monkeypatch.setattr("src.generators._llm_client.time.sleep", lambda *_: None)

    client.generate(prompt="hello", model="gemini")
    assert "extra_body" not in captured


def test_template_verifier_pins_cheap_provider(monkeypatch):
    """verify_template_answer_with_gemini must pass the cheap-provider hint."""
    from src.generators import _verify
    from src.generators._llm_client import LLMResponse

    captured = {}

    def fake_generate(self, **kwargs):
        captured.update(kwargs)
        return LLMResponse(
            content='{"chosen": "A"}',
            parsed={"chosen": "A"},
            model="google/gemini-3.1-pro-preview-20260219",
            input_tokens=120,
            output_tokens=8,
            success=True,
        )

    monkeypatch.setattr(
        "src.generators._llm_client.LLMClient.generate",
        fake_generate,
    )

    agrees, debug = _verify.verify_template_answer_with_gemini(
        question_text="Which grape is in Barolo?",
        options=_OPTS,
        correct_answer_id="A",
        source_fact_text="Barolo DOCG requires 100% Nebbiolo.",
    )

    assert agrees is True
    assert captured.get("extra_body") == {"provider": {"sort": "price"}}


def test_template_paraphrase_pins_cheap_provider(monkeypatch):
    """paraphrase_question_text must pass the cheap-provider hint."""
    from src.generators import _template_paraphrase
    from src.generators._llm_client import LLMResponse

    captured = {}

    def fake_generate(self, **kwargs):
        captured.update(kwargs)
        # Return a paraphrase that satisfies length + entity-preservation rules.
        return LLMResponse(
            content='{"question_text": "In the Barolo region, which grape is mandatory?"}',
            parsed={
                "question_text": "In the Barolo region, which grape is mandatory?"
            },
            model="google/gemini-3.1-pro-preview-20260219",
            input_tokens=180,
            output_tokens=20,
            success=True,
        )

    monkeypatch.setattr(
        "src.generators._llm_client.LLMClient.generate",
        fake_generate,
    )

    out = _template_paraphrase.paraphrase_question_text(
        "Which grape is mandatory in the Barolo region?",
        _OPTS,
    )
    # Paraphrase may return None if validation rejects the rephrasing; we
    # only require that the LLM call carried the routing hint.
    assert captured.get("extra_body") == {"provider": {"sort": "price"}}
    # Sanity: when validation passes, a non-None new stem is returned.
    if out is not None:
        assert "Barolo" in out
