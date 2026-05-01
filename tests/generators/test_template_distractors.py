"""γ-1 — Embedding-similarity distractor sampling tests.

These tests inject a deterministic stub `embed_fn` so we can simulate
"similar" vs "dissimilar" candidates without hitting OpenRouter. The
expected behaviour is:

  * The 3 picked distractors come from positions 1..4 of the K=8 nearest
    neighbours (skipping position 0 which may be a near-alias).
  * If fewer than ``count + 1`` neighbours are viable, the function
    returns [] so the caller can drop the question rather than fall back

Phase 2g.16 Lever 1 tests are also in this file:
  * test_wine_category_filter_rejects_cross_category_distractors
  * test_min_pool_size_after_category_filter_skips_template
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


# ─── Phase 2g.16 Lever 1: wine-category distractor filter ───────────────────


def _make_fact(entity_type: str, name: str, fact_text: str, country: str = "") -> dict:
    """Helper: build a minimal fact dict for pool tests."""
    entities = [{"type": entity_type, "name": name}]
    if country:
        entities.append({"type": "country", "name": country})
    return {"fact_text": fact_text, "entities": entities}


def test_wine_category_filter_rejects_cross_category_distractors():
    """Lever 1: candidates classified as a different wine category than the
    correct answer must be filtered out of the distractor pool.

    Correct answer source fact: classified as 'red' (contains 'Cabernet Sauvignon').
    Pool members with 'vinho_verde'-style sparkling text should be rejected.
    """
    from unittest.mock import patch

    import src.generators.template_generator as tg

    tg.reset_category_filtered_count()

    # Correct answer source fact — red wine category
    correct_fact_text = "Napa Valley is known for Cabernet Sauvignon red wine production."

    # Build a pool: 25 red-wine facts + 10 sparkling/white-wine facts.
    # Use multi-word names so they pass shape-homogeneity with "Napa Valley".
    # Red-wine facts (same category — should be accepted)
    red_facts = [
        _make_fact("region", f"Red Valley{i}", f"Red Valley{i} produces Cabernet Sauvignon red wines.", "USA")
        for i in range(25)
    ]
    # Sparkling facts (different category — should be rejected by category filter)
    sparkling_facts = [
        _make_fact("region", f"Spark Valley{i}", f"Spark Valley{i} produces sparkling méthode champenoise wines.", "USA")
        for i in range(10)
    ]
    all_facts = red_facts + sparkling_facts

    # Patch _global_candidates_for_type to return empty (isolate to in-memory pool)
    with patch.object(tg, "_global_candidates_for_type", return_value=()):
        pool = tg._candidate_pool_for_type(
            "region",
            "Napa Valley",
            all_facts,
            source_fact_text=correct_fact_text,
            template_id="T-GRP-APP-REGION-PLANT-01",
        )

    # Sparkling-category candidates should have been filtered out
    sparkling_names = {f"Spark Valley{i}" for i in range(10)}
    pool_set = set(pool)
    cross_category_leaked = sparkling_names & pool_set
    assert not cross_category_leaked, (
        f"Cross-category candidates leaked into pool: {cross_category_leaked}"
    )
    # Category-filter counter should have fired (at least for some sparkling facts)
    assert tg.get_category_filtered_count() > 0, (
        "Expected _CATEGORY_FILTERED_COUNT > 0 but counter is 0"
    )


def test_min_pool_size_after_category_filter_skips_template():
    """Lever 1: when the post-category-filter pool drops below 20, the
    function returns [] so the caller skips the template instance.
    """
    from unittest.mock import patch

    import src.generators.template_generator as tg

    tg.reset_category_filtered_count()

    correct_fact_text = "Rioja produces world-class Tempranillo red wine."

    # Build a pool with only 5 same-category facts (below _MIN_POOL_SIZE_V22=20).
    # Use multi-word names to pass shape-homogeneity check with "Rioja" (single-word)...
    # Actually "Rioja" is single-word; use single-word names for compat.
    small_red_pool = [
        _make_fact("region", f"Redoja{i}", f"Redoja{i} produces Tempranillo red wines.", "Spain")
        for i in range(5)
    ]
    # 20 sparkling facts that will be filtered out (same single-word shape as Rioja)
    sparkling_facts = [
        _make_fact("region", f"Cavaoja{i}", f"Cavaoja{i} produces sparkling Cava wines.", "Spain")
        for i in range(20)
    ]
    all_facts = small_red_pool + sparkling_facts

    with patch.object(tg, "_global_candidates_for_type", return_value=()):
        pool = tg._candidate_pool_for_type(
            "region",
            "Rioja",
            all_facts,
            source_fact_text=correct_fact_text,
            template_id="T-GRP-APP-REGION-PLANT-01",
        )

    assert pool == [], (
        f"Expected empty pool when post-category-filter size < 20, got {pool}"
    )
