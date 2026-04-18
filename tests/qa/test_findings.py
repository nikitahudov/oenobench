"""Tests for audit findings DAO (mocks the DB)."""

from __future__ import annotations

from src.qa._findings import compute_config_hash


def test_config_hash_is_stable_and_ordered():
    h1 = compute_config_hash(
        agent_versions={"A1_LexicalHygiene": "v1.0.0", "B1_TriJudgeAnswer": "v1.0.0"},
        model_ids=["claude", "gemini", "chatgpt"],
        seed=42,
        thresholds={"a": 0.6, "b": 0.4},
    )
    h2 = compute_config_hash(
        agent_versions={"B1_TriJudgeAnswer": "v1.0.0", "A1_LexicalHygiene": "v1.0.0"},
        model_ids=["chatgpt", "gemini", "claude"],
        seed=42,
        thresholds={"b": 0.4, "a": 0.6},
    )
    assert h1 == h2


def test_config_hash_changes_on_version_bump():
    h1 = compute_config_hash(
        agent_versions={"A1_LexicalHygiene": "v1.0.0"},
        model_ids=["claude"],
        seed=42,
        thresholds={},
    )
    h2 = compute_config_hash(
        agent_versions={"A1_LexicalHygiene": "v1.0.1"},
        model_ids=["claude"],
        seed=42,
        thresholds={},
    )
    assert h1 != h2
