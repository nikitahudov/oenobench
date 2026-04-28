"""Tests for the lever B1 LLM-decision content-hash cache.

The cache is shared by `_closed_book_gate`, `_verify`, and
`_template_paraphrase`. Disabled by default; enabled via
OENOBENCH_LLM_CACHE=1 so v8 reproducibility is preserved.

These tests use the real Postgres connection (the project standard for
integration tests) but isolate themselves with per-test version_tag
strings and an `invalidate_kind` cleanup in fixtures. They do NOT touch
the network — `_call_gate`, `LLMClient.generate`, and `_call_api` are
patched throughout.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from src.generators import _closed_book_gate, _llm_cache
from src.generators._llm_cache import (
    CACHE_ENABLED_ENV_VAR,
    cache_key,
    invalidate_kind,
    lookup,
    store,
)


# ─── cache_key stability ─────────────────────────────────────────────────────


def test_cache_key_is_stable_for_dict_ordering():
    """Equivalent dicts (different key insertion order) must hash identically."""
    a = cache_key({"a": 1, "b": 2, "c": 3})
    b = cache_key({"c": 3, "b": 2, "a": 1})
    assert a == b
    # And (sanity) different dicts hash differently.
    assert a != cache_key({"a": 1, "b": 2})


def test_cache_key_is_stable_for_nested_lists():
    """Nested structures with identical contents and key orders hash the same."""
    a = cache_key({
        "stem": "Which grape is in Barolo?",
        "options": [
            {"id": "A", "text": "Nebbiolo"},
            {"id": "B", "text": "Barbera"},
        ],
        "facts": ["Barolo requires 100% Nebbiolo."],
    })
    b = cache_key({
        "options": [
            {"text": "Nebbiolo", "id": "A"},
            {"text": "Barbera", "id": "B"},
        ],
        "facts": ["Barolo requires 100% Nebbiolo."],
        "stem": "Which grape is in Barolo?",
    })
    assert a == b


# ─── env-var gating ───────────────────────────────────────────────────────────


def _unique_version(base: str, name: str) -> str:
    """Per-test version tag so concurrent runs don't collide on UNIQUE."""
    pid = os.getpid()
    return f"TEST_{base}_{name}_{pid}"


def test_cache_disabled_by_default(monkeypatch):
    """With the env var unset, lookup is a no-op even when the row exists.

    To verify, we briefly enable the cache, store a row, then turn the cache
    off and confirm lookup returns None (i.e. it doesn't reach the DB).
    """
    version = _unique_version("disabled", "default")
    key = cache_key({"q": "test_cache_disabled_by_default"})
    # Enable, store, disable, look up.
    monkeypatch.setenv(CACHE_ENABLED_ENV_VAR, "1")
    try:
        store(
            kind="gate", key=key, model_id="m1",
            version_tag=version, payload={"ok": True},
        )
        # Confirm the stored row is visible while enabled.
        assert lookup(
            kind="gate", key=key, model_id="m1", version_tag=version,
        ) == {"ok": True}
    finally:
        # Disable + verify miss.
        monkeypatch.delenv(CACHE_ENABLED_ENV_VAR, raising=False)
        try:
            assert lookup(
                kind="gate", key=key, model_id="m1", version_tag=version,
            ) is None
        finally:
            # Cleanup: re-enable so invalidate_kind has cache_enabled-noop
            # behaviour avoided (invalidate_kind always runs).
            n = invalidate_kind(f"__test_disabled_{os.getpid()}")  # warm path
            # But our fixture used kind="gate", so wipe just our keys
            # without nuking real gate cache rows: safe because version
            # tag is unique to the test.
            # Use a low-level cleanup query keyed by version_tag:
            from src.utils.db import get_pg
            conn = get_pg()
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM llm_decisions WHERE version_tag = %s",
                    (version,),
                )
            conn.commit()


def test_cache_hit_when_enabled(monkeypatch):
    """env=1, store then lookup returns the payload."""
    version = _unique_version("hit", "enabled")
    monkeypatch.setenv(CACHE_ENABLED_ENV_VAR, "1")
    key = cache_key({"q": "hit-test"})
    try:
        store(
            kind="gate", key=key, model_id="m1",
            version_tag=version, payload={"foo": "bar", "n": 42},
        )
        got = lookup(
            kind="gate", key=key, model_id="m1", version_tag=version,
        )
        assert got == {"foo": "bar", "n": 42}
    finally:
        from src.utils.db import get_pg
        conn = get_pg()
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM llm_decisions WHERE version_tag = %s",
                (version,),
            )
        conn.commit()


def test_cache_miss_on_different_version_tag(monkeypatch):
    """Same key/kind/model, different version tag → miss."""
    v_old = _unique_version("vmiss", "old")
    v_new = _unique_version("vmiss", "new")
    monkeypatch.setenv(CACHE_ENABLED_ENV_VAR, "1")
    key = cache_key({"q": "version-miss"})
    try:
        store(
            kind="gate", key=key, model_id="m1",
            version_tag=v_old, payload={"old": True},
        )
        # Miss under the new version.
        got = lookup(kind="gate", key=key, model_id="m1", version_tag=v_new)
        assert got is None
        # Hit under the original version (sanity).
        got_old = lookup(kind="gate", key=key, model_id="m1", version_tag=v_old)
        assert got_old == {"old": True}
    finally:
        from src.utils.db import get_pg
        conn = get_pg()
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM llm_decisions WHERE version_tag IN (%s, %s)",
                (v_old, v_new),
            )
        conn.commit()


def test_cache_miss_on_different_model_id(monkeypatch):
    """Same key/kind/version, different model_id → miss."""
    version = _unique_version("modelmiss", "tag")
    monkeypatch.setenv(CACHE_ENABLED_ENV_VAR, "1")
    key = cache_key({"q": "model-miss"})
    try:
        store(
            kind="gate", key=key, model_id="model-A",
            version_tag=version, payload={"m": "A"},
        )
        miss = lookup(
            kind="gate", key=key, model_id="model-B", version_tag=version,
        )
        assert miss is None
        hit = lookup(
            kind="gate", key=key, model_id="model-A", version_tag=version,
        )
        assert hit == {"m": "A"}
    finally:
        from src.utils.db import get_pg
        conn = get_pg()
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM llm_decisions WHERE version_tag = %s",
                (version,),
            )
        conn.commit()


def test_invalidate_kind_drops_only_that_kind(monkeypatch):
    """Invalidating one kind must leave the other kinds intact."""
    version = _unique_version("inv", "kinds")
    monkeypatch.setenv(CACHE_ENABLED_ENV_VAR, "1")
    gate_key = cache_key({"q": "inv-gate"})
    verifier_key = cache_key({"q": "inv-verifier"})
    try:
        store(
            kind="gate", key=gate_key, model_id="m1",
            version_tag=version, payload={"k": "gate"},
        )
        store(
            kind="verifier", key=verifier_key, model_id="m1",
            version_tag=version, payload={"k": "verifier"},
        )
        # Sanity — both visible.
        assert lookup(
            kind="gate", key=gate_key, model_id="m1", version_tag=version,
        ) == {"k": "gate"}
        assert lookup(
            kind="verifier", key=verifier_key, model_id="m1", version_tag=version,
        ) == {"k": "verifier"}

        # Invalidate gate only — but DELETE all gate rows is too broad if
        # other tests ran in parallel. Instead, scope the cleanup to our
        # test version tag with a direct SQL DELETE for this one assertion,
        # and then exercise invalidate_kind separately on a third kind we
        # uniquely populate.
        third = "verifier_test_kind_" + str(os.getpid())
        store(
            kind=third, key=gate_key, model_id="m1",
            version_tag=version, payload={"k": "third"},
        )
        n_deleted = invalidate_kind(third)
        assert n_deleted >= 1
        # And the gate / verifier rows we stored remain.
        assert lookup(
            kind="gate", key=gate_key, model_id="m1", version_tag=version,
        ) == {"k": "gate"}
        assert lookup(
            kind="verifier", key=verifier_key, model_id="m1", version_tag=version,
        ) == {"k": "verifier"}
    finally:
        from src.utils.db import get_pg
        conn = get_pg()
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM llm_decisions WHERE version_tag = %s",
                (version,),
            )
        conn.commit()


# ─── End-to-end wiring: gate ─────────────────────────────────────────────────

_OPTS = [
    {"id": "A", "text": "Nebbiolo"},
    {"id": "B", "text": "Barbera"},
    {"id": "C", "text": "Dolcetto"},
    {"id": "D", "text": "Sangiovese"},
]


@dataclass
class _FakeMessage:
    content: str


@dataclass
class _FakeChoice:
    message: _FakeMessage


@dataclass
class _FakeCompletion:
    choices: list


def _fake_gate_response(selected: str, confidence: float) -> _FakeCompletion:
    body = (
        '{"selected": "' + selected + '",'
        ' "confidence": ' + str(confidence) + ','
        ' "reasoning": "test"}'
    )
    return _FakeCompletion(choices=[_FakeChoice(message=_FakeMessage(content=body))])


def _cleanup_version(version_tag: str) -> None:
    from src.utils.db import get_pg
    conn = get_pg()
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM llm_decisions WHERE version_tag = %s",
            (version_tag,),
        )
    conn.commit()


def test_gate_uses_cache_when_enabled(monkeypatch):
    """First call hits API + stores; second identical call returns from cache."""
    monkeypatch.setenv(CACHE_ENABLED_ENV_VAR, "1")
    # Pin the gate model so a future Lever B4 default change doesn't make
    # the cache hit/miss depend on environment.
    monkeypatch.setenv("OENOBENCH_GATE_MODEL", "anthropic/claude-test-gate-cache")

    counter = {"n": 0}

    def counting_call(client, prompt, model=None):
        counter["n"] += 1
        return _fake_gate_response("A", 0.85)

    monkeypatch.setattr(_closed_book_gate, "_call_gate", counting_call)
    monkeypatch.setattr(
        _closed_book_gate, "_get_client", lambda: SimpleNamespace()
    )

    version_tag = f"GATE_VERSION={_closed_book_gate.GATE_VERSION}"
    # Build the cache key manually so we can clean up by version_tag.
    try:
        # First call — miss → API + store.
        r1 = _closed_book_gate.screen_question(
            "stem-cache-test", _OPTS, "A", "1", "multiple_choice",
        )
        assert counter["n"] == 1
        assert r1.passed is False
        assert r1.matched_gold is True

        # Second call with identical inputs — hit → counter unchanged.
        r2 = _closed_book_gate.screen_question(
            "stem-cache-test", _OPTS, "A", "1", "multiple_choice",
        )
        assert counter["n"] == 1, "second call must not invoke _call_gate"
        assert r2.passed == r1.passed
        assert r2.matched_gold == r1.matched_gold
        assert r2.selected == r1.selected

        # A different stem → miss → API runs again.
        r3 = _closed_book_gate.screen_question(
            "stem-cache-different", _OPTS, "A", "1", "multiple_choice",
        )
        assert counter["n"] == 2
    finally:
        _cleanup_version(version_tag)


def test_gate_does_not_cache_parse_errors(monkeypatch):
    """Garbage payloads from the gate must not get cached.

    Otherwise transient flakiness would poison every later call with the
    same input.
    """
    monkeypatch.setenv(CACHE_ENABLED_ENV_VAR, "1")
    monkeypatch.setenv("OENOBENCH_GATE_MODEL", "anthropic/claude-test-gate-parseerr")

    bad = _FakeCompletion(
        choices=[_FakeChoice(message=_FakeMessage(content="not json at all"))]
    )

    def bad_call(client, prompt, model=None):
        return bad

    monkeypatch.setattr(_closed_book_gate, "_call_gate", bad_call)
    monkeypatch.setattr(
        _closed_book_gate, "_get_client", lambda: SimpleNamespace()
    )

    version_tag = f"GATE_VERSION={_closed_book_gate.GATE_VERSION}"
    try:
        r = _closed_book_gate.screen_question(
            "stem-parseerr", _OPTS, "A", "1", "multiple_choice",
        )
        assert r.error == "json_parse_failed"
        # The cache must NOT contain this key.
        key = _llm_cache.cache_key({
            "stem": "stem-parseerr",
            "options": _OPTS,
            "correct_answer": "A",
            "difficulty": "1",
            "question_type": "multiple_choice",
        })
        got = _llm_cache.lookup(
            kind="gate",
            key=key,
            model_id=_closed_book_gate._resolve_gate_model("1"),
            version_tag=version_tag,
        )
        assert got is None, "parse-error verdict must not be cached"
    finally:
        _cleanup_version(version_tag)


# ─── End-to-end wiring: verifier ─────────────────────────────────────────────


def test_verifier_uses_cache_when_enabled(monkeypatch):
    """verify_question_with_independent_solver caches successful verdicts."""
    from src.generators import _verify
    from src.generators._llm_client import LLMResponse

    monkeypatch.setenv(CACHE_ENABLED_ENV_VAR, "1")

    counter = {"n": 0}

    def fake_generate(*args, **kwargs):
        counter["n"] += 1
        return LLMResponse(
            content='{"chosen": "A", "confidence": 0.9}',
            parsed={"chosen": "A", "confidence": 0.9},
            model="anthropic/claude-opus-4.7",
            input_tokens=120, output_tokens=15,
            latency_ms=500, success=True, error=None,
        )

    fake_client = SimpleNamespace(generate=fake_generate)

    version_tag = "VERIFY_V1"
    # We share VERIFY_V1 with production; clean up by hashing the unique stem
    # we use here.
    unique_stem = "verifier-cache-test-stem-zzz"
    try:
        with patch("src.generators._verify.get_client", return_value=fake_client):
            v1, _ = _verify.verify_question_with_independent_solver(
                question_text=unique_stem,
                options=[{"id": "A", "text": "x"}, {"id": "B", "text": "y"}],
                correct_answer="A",
                source_facts=["a fact"],
                generator="llama",
            )
            assert v1 is True
            assert counter["n"] == 1

            # Second identical call — hit.
            v2, _ = _verify.verify_question_with_independent_solver(
                question_text=unique_stem,
                options=[{"id": "A", "text": "x"}, {"id": "B", "text": "y"}],
                correct_answer="A",
                source_facts=["a fact"],
                generator="llama",
            )
            assert v2 is True
            assert counter["n"] == 1, "cache hit must skip the LLM call"

            # Different stem — miss.
            v3, _ = _verify.verify_question_with_independent_solver(
                question_text=unique_stem + "-different",
                options=[{"id": "A", "text": "x"}, {"id": "B", "text": "y"}],
                correct_answer="A",
                source_facts=["a fact"],
                generator="llama",
            )
            assert counter["n"] == 2
    finally:
        # Clean up just the rows our test made (by recomputing keys).
        from src.utils.db import get_pg
        from src.generators._llm_client import GENERATOR_MODELS
        keys = [
            _llm_cache.cache_key({
                "fn": "verify_question_with_independent_solver",
                "stem": stem,
                "options": [{"id": "A", "text": "x"}, {"id": "B", "text": "y"}],
                "correct_answer": "A",
                "source_facts": ["a fact"],
            })
            for stem in (unique_stem, unique_stem + "-different")
        ]
        conn = get_pg()
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM llm_decisions WHERE version_tag = %s AND cache_key = ANY(%s)",
                (version_tag, keys),
            )
        conn.commit()


# ─── End-to-end wiring: paraphrase ───────────────────────────────────────────


def test_paraphrase_uses_cache_when_enabled(monkeypatch):
    """paraphrase_question_text caches successful paraphrases by content."""
    from src.generators import _template_paraphrase
    from src.generators._llm_client import LLMResponse

    monkeypatch.setenv(CACHE_ENABLED_ENV_VAR, "1")

    counter = {"n": 0}
    paraphrased = "Which red grape variety must Barolo be made from?"

    def fake_generate(*args, **kwargs):
        counter["n"] += 1
        return LLMResponse(
            content='{"question_text": "' + paraphrased + '"}',
            parsed={"question_text": paraphrased},
            model="google/gemini-3.1-pro-preview",
            input_tokens=200, output_tokens=20,
            latency_ms=400, success=True, error=None,
        )

    fake_client = SimpleNamespace(generate=fake_generate)

    original = "Barolo requires which red grape variety?"
    options = [
        {"id": "A", "text": "Nebbiolo"},
        {"id": "B", "text": "Sangiovese"},
        {"id": "C", "text": "Barbera"},
        {"id": "D", "text": "Dolcetto"},
    ]
    version_tag = "PARAPHRASE_V1"
    try:
        with patch("src.generators._llm_client.get_client", return_value=fake_client):
            r1 = _template_paraphrase.paraphrase_question_text(original, options)
            assert r1 == paraphrased
            assert counter["n"] == 1

            r2 = _template_paraphrase.paraphrase_question_text(original, options)
            assert r2 == paraphrased
            assert counter["n"] == 1, "second identical call must hit cache"

            r3 = _template_paraphrase.paraphrase_question_text(
                original + " (variant)", options,
            )
            # Different stem → cache miss → API runs again.
            assert counter["n"] == 2
    finally:
        # Clean up our two rows by version tag + cache_key.
        from src.utils.db import get_pg
        keys = [
            _llm_cache.cache_key({"text": original, "options": options}),
            _llm_cache.cache_key({"text": original + " (variant)", "options": options}),
        ]
        conn = get_pg()
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM llm_decisions WHERE version_tag = %s AND cache_key = ANY(%s)",
                (version_tag, keys),
            )
        conn.commit()
