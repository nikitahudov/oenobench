"""γ-1 — Embedding-similarity distractor sampling tests.

These tests inject a deterministic stub `embed_fn` so we can simulate
"similar" vs "dissimilar" candidates without hitting OpenRouter. The
expected behaviour is:

  * The 3 picked distractors come from positions 1..4 of the K=8 nearest
    neighbours (skipping position 0 which may be a near-alias).
  * If fewer than ``count + 1`` neighbours are viable, the function
    returns [] so the caller can drop the question rather than fall back
    to random.
"""

from __future__ import annotations

from src.generators.template_generator import embedding_similarity_distractors


def _stub_embed_factory(embeddings: dict[str, list[float]]):
    """Build a stub embed_fn that returns canned embeddings keyed by phrase substring."""

    def _stub(text: str) -> list[float] | None:
        # Match by entity name appearing in the context phrase.
        for key, vec in embeddings.items():
            if key.lower() in text.lower():
                return list(vec)
        return None

    return _stub


def test_distractors_picked_from_positions_2_to_5():
    """The 3 distractors should be the 2nd, 3rd, 4th most similar — not the closest."""
    correct = "Rheingau"
    candidates = [
        "Rhinegau",     # near-alias — closest, should be SKIPPED (position 0)
        "Mosel",        # position 1, picked
        "Pfalz",        # position 2, picked
        "Nahe",         # position 3, picked
        "Rheinhessen",  # position 4 — within band but dropped (only 3 chosen)
        "Bordeaux",     # position 5 — too far
        "Tuscany",      # position 6 — too far
        "Napa Valley",  # position 7 — too far
    ]
    # Construct a 1-D embedding so cosine is monotonic in similarity.
    embeddings = {
        "Rheingau":    [1.0, 0.0],
        "Rhinegau":    [0.99, 0.01],
        "Mosel":       [0.95, 0.05],
        "Pfalz":       [0.93, 0.07],
        "Nahe":        [0.91, 0.09],
        "Rheinhessen": [0.88, 0.12],
        "Bordeaux":    [0.50, 0.50],
        "Tuscany":     [0.40, 0.60],
        "Napa Valley": [0.30, 0.70],
    }
    stub = _stub_embed_factory(embeddings)

    picks = embedding_similarity_distractors(
        correct, "region", candidates, count=3, embed_fn=stub
    )
    assert len(picks) == 3
    assert "Rhinegau" not in picks, "alias-like nearest neighbour must be skipped"
    assert set(picks).issubset({"Mosel", "Pfalz", "Nahe", "Rheinhessen"})
    # Bordeaux/Tuscany/Napa are too far — band 1..4 excludes them
    assert "Bordeaux" not in picks
    assert "Tuscany" not in picks
    assert "Napa Valley" not in picks


def test_distractors_returns_empty_when_pool_too_thin():
    """With fewer than count+1 candidates the function must signal "skip"."""
    correct = "Rheingau"
    candidates = ["Mosel", "Pfalz"]  # only 2 — not enough
    embeddings = {
        "Rheingau": [1.0, 0.0],
        "Mosel":    [0.9, 0.1],
        "Pfalz":    [0.8, 0.2],
    }
    stub = _stub_embed_factory(embeddings)
    picks = embedding_similarity_distractors(
        correct, "region", candidates, count=3, embed_fn=stub
    )
    assert picks == []


def test_distractors_skip_correct_value_in_pool():
    """If the correct entity is in the pool it must be filtered out."""
    correct = "Rheingau"
    candidates = ["Rheingau", "Mosel", "Pfalz", "Nahe", "Rheinhessen", "Baden", "Württemberg", "Franken"]
    embeddings = {
        "Rheingau":    [1.0, 0.0],
        "Mosel":       [0.95, 0.05],
        "Pfalz":       [0.93, 0.07],
        "Nahe":        [0.91, 0.09],
        "Rheinhessen": [0.89, 0.11],
        "Baden":       [0.85, 0.15],
        "Württemberg": [0.82, 0.18],
        "Franken":     [0.80, 0.20],
    }
    stub = _stub_embed_factory(embeddings)
    picks = embedding_similarity_distractors(
        correct, "region", candidates, count=3, embed_fn=stub
    )
    assert correct not in picks


def test_distractors_returns_empty_when_target_unembeddable():
    """If the target itself cannot be embedded we must bail out."""
    correct = "UnknownRegion"
    candidates = ["Mosel", "Pfalz", "Nahe", "Rheinhessen", "Baden", "Württemberg", "Franken", "Saale"]
    embeddings = {
        # Note: no entry for "UnknownRegion" — the stub returns None for it.
        "Mosel":       [0.95, 0.05],
        "Pfalz":       [0.93, 0.07],
        "Nahe":        [0.91, 0.09],
        "Rheinhessen": [0.89, 0.11],
        "Baden":       [0.85, 0.15],
        "Württemberg": [0.82, 0.18],
        "Franken":     [0.80, 0.20],
        "Saale":       [0.78, 0.22],
    }
    stub = _stub_embed_factory(embeddings)
    picks = embedding_similarity_distractors(
        correct, "region", candidates, count=3, embed_fn=stub
    )
    assert picks == []


def test_distractors_band_does_not_include_farthest():
    """With many candidates, the farthest (positions ≥5) must not be picked."""
    correct = "Rheingau"
    candidates = [
        "Rhinegau",     # 0 — alias, skipped
        "Mosel",        # 1
        "Pfalz",        # 2
        "Nahe",         # 3
        "Baden",        # 4
        "Bordeaux",     # 5 — too far
        "Tuscany",      # 6 — too far
        "Napa Valley",  # 7 — too far
        "Mendoza",      # 8 — too far
    ]
    embeddings = {
        "Rheingau":    [1.0, 0.0],
        "Rhinegau":    [0.99, 0.01],
        "Mosel":       [0.95, 0.05],
        "Pfalz":       [0.93, 0.07],
        "Nahe":        [0.91, 0.09],
        "Baden":       [0.88, 0.12],
        "Bordeaux":    [0.50, 0.50],
        "Tuscany":     [0.40, 0.60],
        "Napa Valley": [0.30, 0.70],
        "Mendoza":     [0.20, 0.80],
    }
    stub = _stub_embed_factory(embeddings)
    picks = embedding_similarity_distractors(
        correct, "region", candidates, count=3, embed_fn=stub
    )
    assert len(picks) == 3
    # The picks should all be in the high-similarity band, NOT in the far group.
    far = {"Bordeaux", "Tuscany", "Napa Valley", "Mendoza"}
    assert not (set(picks) & far), f"far candidates leaked into distractors: {picks}"
