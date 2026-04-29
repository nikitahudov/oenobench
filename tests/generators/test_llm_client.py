"""Phase 2g.12 — Team D: ``_try_parse_json`` fence-strip pre-pass.

In v9, Gemini Pro produced 65/67 (97%) of all parse failures, and most
were responses wrapped in Markdown fences with assorted language tags
(```json, ```jsonc, ```python, …) that the pre-existing ``_FENCE_RE``
(limited to ``(?:json)?``) did not match.

These tests verify:

- Bare JSON objects still parse (existing behaviour preserved).
- Fenced JSON with a ``json`` language tag parses.
- Fenced JSON with no language tag parses.
- Garbage input still returns ``None`` (existing fallback preserved).
- Other language tags (jsonc, python) parse — the fence-strip pre-pass
  is tag-agnostic.
- Whitespace around fences is tolerated.
"""

from __future__ import annotations

from src.generators._llm_client import _try_parse_json


def test_try_parse_json_bare_object():
    """A bare JSON object (no fences) still parses — existing behaviour."""
    assert _try_parse_json('{"a": 1}') == {"a": 1}


def test_try_parse_json_fenced_with_json_tag():
    """Gemini's most common malformation: ```json … ``` wrapper."""
    raw = '```json\n{"a": 1}\n```'
    assert _try_parse_json(raw) == {"a": 1}


def test_try_parse_json_fenced_no_tag():
    """Bare ``` … ``` wrapper with no language tag."""
    raw = '```\n{"a": 1}\n```'
    assert _try_parse_json(raw) == {"a": 1}


def test_try_parse_json_invalid():
    """Pure garbage input still returns None — existing fallback preserved."""
    assert _try_parse_json("this is not json at all") is None


def test_try_parse_json_fenced_other_lang_tag():
    """Other language tags (jsonc, python) are stripped too — the
    pre-pass treats anything between the opening ``` and the first
    newline as a tag and discards it.
    """
    assert _try_parse_json('```jsonc\n{"a": 1}\n```') == {"a": 1}
    assert _try_parse_json('```python\n{"a": 1}\n```') == {"a": 1}


def test_try_parse_json_fenced_with_surrounding_whitespace():
    """Leading/trailing whitespace around fences is tolerated."""
    raw = '\n\n```json\n{"a": 1, "b": [2, 3]}\n```\n\n'
    assert _try_parse_json(raw) == {"a": 1, "b": [2, 3]}


def test_try_parse_json_returns_none_for_array():
    """Top-level JSON arrays must not be returned as dicts — every
    caller in the codebase assumes a dict-shaped response. Verifies the
    isinstance(obj, dict) guard is preserved through the pre-pass.
    """
    assert _try_parse_json('[1, 2, 3]') is None
    assert _try_parse_json('```json\n[1, 2, 3]\n```') is None
