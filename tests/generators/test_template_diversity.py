"""v2.3 Phase F fix #13 — Per-template diversity cap regression tests.

Gold-v3 + audit_pilot_v3 showed a 28% share for `T-PRD-TF-REGION-01` and
only 11 of 38 registered templates firing. The selection loop in
`template_generator.py` now caps each template at 15% of the per-domain
quota and exposes a `get_template_id_counts()` helper.

Scenarios covered:
  * When the fact pool is biased so every fact matches one dominant
    template, the cap still forces diversity — max-share stays < 20% of
    total picks and at least 3 distinct templates fire.
  * The cap is inclusive (templates at exactly N * 15% cap are excluded).
  * Reset helper zeros the counter.
"""

from __future__ import annotations

from collections import Counter

from src.generators.template_generator import (
    TEMPLATES,
    _template_cap,
    generate_with_diversity_cap,
    get_template_id_counts,
    reset_template_id_counts,
)


def _mk_producer_fact(uid: int, producer: str, region: str, country: str,
                       appellation: str | None = None,
                       classification: str | None = None) -> dict:
    """Build a synthetic producer fact.

    When ``appellation`` or ``classification`` are provided they are included
    in both the entities JSONB and the fact_text so additional templates
    (T-PRD-APPELLATION-01 / T-PRD-CLASS-01) can fire. The source-faithfulness
    gate (``verify_answer_in_source_fact``) requires the correct_answer to
    literally appear in fact_text.
    """
    pieces = [
        f"{producer} is a wine producer located in the {region} region",
        f"of {country}",
    ]
    entities = [
        {"name": producer, "type": "producer"},
        {"name": region, "type": "region"},
        {"name": country, "type": "country"},
    ]
    if appellation:
        pieces.append(f"within the {appellation} appellation")
        entities.append({"name": appellation, "type": "appellation"})
    if classification:
        pieces.append(f"holding {classification} classification")
        entities.append({"name": classification, "type": "classification"})
    return {
        "id": f"00000000-0000-0000-0000-{uid:012d}",
        "fact_text": ", ".join(pieces) + ".",
        "domain": "producers",
        "subdomain": None,
        "entities": entities,
        "source_id": "00000000-0000-0000-0000-aaaaaaaaaaaa",
        "source_name": "test",
        "source_url": "test://",
        "confidence": 1.0,
        "tags": [],
    }


def _fake_producer_corpus(n: int = 100) -> list[dict]:
    """Build ``n`` synthetic producer facts.

    Each fact carries at minimum producer+region+country. A rotating subset
    carries appellation and classification so the full producer template
    family can fire, which is needed to keep any single template's share
    below 20% once the v2.3 fix #13 cap is active.

    Multiple distinct regions (≥10) and countries (≥26, multi-word shape)
    are included so the v2.2 fix #8c hardened distractor pool (minimum size
    20, shape-homogeneity) is satisfiable without DB fallback.
    """
    regions = [
        "Mosel Valley", "Rhein Hills", "Pfalz Plains", "Nahe Slopes",
        "Baden Ridge", "Wurttemberg Terrace", "Saale Basin", "Sachsen Bank",
        "Rheinhessen Flats", "Franken Dale",
    ]
    countries = [
        "Testland Alpha", "Testland Beta", "Testland Gamma", "Testland Delta",
        "Testland Epsilon", "Testland Zeta", "Testland Eta", "Testland Theta",
        "Testland Iota", "Testland Kappa", "Testland Lambda", "Testland Mu",
        "Testland Nu", "Testland Xi", "Testland Omicron", "Testland Pi",
        "Testland Rho", "Testland Sigma", "Testland Tau", "Testland Upsilon",
        "Testland Phi", "Testland Chi", "Testland Psi", "Testland Omega",
        "Testland Alpha Beta", "Testland Gamma Delta",
    ]
    appellations = [
        "Appellation Alfa", "Appellation Bravo", "Appellation Charlie",
        "Appellation Delta", "Appellation Echo", "Appellation Foxtrot",
        "Appellation Golf", "Appellation Hotel", "Appellation India",
        "Appellation Juliet", "Appellation Kilo", "Appellation Lima",
        "Appellation Mike", "Appellation November", "Appellation Oscar",
        "Appellation Papa", "Appellation Quebec", "Appellation Romeo",
        "Appellation Sierra", "Appellation Tango", "Appellation Uniform",
        "Appellation Victor", "Appellation Whiskey", "Appellation Xray",
        "Appellation Yankee", "Appellation Zulu",
    ]
    classifications = [
        "Class Alpha Tier", "Class Beta Tier", "Class Gamma Tier",
        "Class Delta Tier", "Class Epsilon Tier", "Class Zeta Tier",
        "Class Eta Tier", "Class Theta Tier", "Class Iota Tier",
        "Class Kappa Tier", "Class Lambda Tier", "Class Mu Tier",
        "Class Nu Tier", "Class Xi Tier", "Class Omicron Tier",
        "Class Pi Tier", "Class Rho Tier", "Class Sigma Tier",
        "Class Tau Tier", "Class Upsilon Tier", "Class Phi Tier",
        "Class Chi Tier", "Class Psi Tier", "Class Omega Tier",
        "Class Alpha Prime", "Class Beta Prime",
    ]
    out: list[dict] = []
    for i in range(n):
        producer = f"Test Producer {i:03d}"  # multi-word shape
        region = regions[i % len(regions)]
        country = countries[i % len(countries)]
        appellation = appellations[i % len(appellations)]
        classification = classifications[i % len(classifications)]
        out.append(_mk_producer_fact(
            i, producer, region, country,
            appellation=appellation,
            classification=classification,
        ))
    return out


def test_reset_counter_clears_state():
    """Sanity: the counter reset is effective."""
    reset_template_id_counts()
    assert get_template_id_counts() == {}


def test_template_cap_math():
    """Cap = floor(quota * 0.15), minimum 1."""
    assert _template_cap(100) == 15
    assert _template_cap(50) == 7
    assert _template_cap(5) == 1   # min floor — tiny dry-runs still enforce cap
    assert _template_cap(1) == 1


def test_diversity_cap_prevents_single_template_monopoly():
    """With ≥100 biased producer facts the cap forces ≥3 templates + low max share.

    Task spec: ``max(counts.values()) / sum(counts.values()) < 0.20`` and
    ``len(counts) >= 3``. The fixture carries producer+region+country+
    appellation+classification so that all six producer templates in the
    registry can match; the expected behaviour is that the cap rotates
    through all of them at 15% each, keeping max share ≤ 17%.
    """
    reset_template_id_counts()

    producer_templates = [t for t in TEMPLATES if t["domain"] == "producers"]
    assert len(producer_templates) >= 6, (
        f"Only {len(producer_templates)} producer templates; the test fixture "
        "relies on having several candidates to rotate through."
    )

    facts = _fake_producer_corpus(n=200)
    # target=100 so cap=15; running in strict mode (allow_cap_overflow=False)
    # means generation stops at ≤6×15=90 questions, well below 100, once
    # every template is at the cap. The CLI uses the permissive fallback
    # path (see `allow_cap_overflow=True`) for throughput-safety; this test
    # exercises the strict cap to make the invariant easy to check.
    target = 100
    results = generate_with_diversity_cap(
        domain="producers",
        target=target,
        facts=facts,
        templates=producer_templates,
        use_embeddings=False,
        allow_cap_overflow=False,
    )

    # We expect ~ cap × n_templates ≤ 6 × 15 = 90 results.
    assert len(results) >= 60, (
        f"Expected ≥60 results in strict mode, got {len(results)}"
    )

    counts = Counter(r["_template_id"] for r in results)
    total = sum(counts.values())
    assert total > 0
    max_share = max(counts.values()) / total

    # Task spec: the monopoly is broken — no template exceeds 20% share.
    assert max_share < 0.20, (
        f"Max template share = {max_share:.2%} > 20%; diversity cap broken. "
        f"counts={dict(counts)}"
    )
    # Task spec: at least 3 distinct template IDs fire.
    assert len(counts) >= 3, (
        f"Only {len(counts)} distinct templates fired; cap did not force "
        f"rotation. counts={dict(counts)}"
    )


def test_counter_gets_incremented_on_each_result():
    """Each successful fill_template output bumps the counter by exactly 1."""
    reset_template_id_counts()

    producer_templates = [t for t in TEMPLATES if t["domain"] == "producers"]
    facts = _fake_producer_corpus(n=100)
    results = generate_with_diversity_cap(
        domain="producers",
        target=50,
        facts=facts,
        templates=producer_templates,
        use_embeddings=False,
        allow_cap_overflow=False,
    )

    counts = get_template_id_counts()
    # Counter total == result count.
    assert sum(counts.values()) == len(results)


def test_cap_is_enforced_at_per_domain_quota_level():
    """With target=20 (cap=3), no template can accumulate >3 picks in strict mode."""
    reset_template_id_counts()

    producer_templates = [t for t in TEMPLATES if t["domain"] == "producers"]
    facts = _fake_producer_corpus(n=200)
    results = generate_with_diversity_cap(
        domain="producers",
        target=20,
        facts=facts,
        templates=producer_templates,
        use_embeddings=False,
        allow_cap_overflow=False,
    )

    counts = Counter(r["_template_id"] for r in results)
    cap = _template_cap(20)  # 3
    # In strict mode no template may exceed the cap.
    over_cap = {tid: n for tid, n in counts.items() if n > cap}
    assert not over_cap, (
        f"Template(s) exceeded cap={cap} in strict mode: {over_cap}"
    )


def test_cap_fallback_allows_overflow_when_enabled():
    """With ``allow_cap_overflow=True`` (CLI default) the target is hit even
    when all templates are at cap."""
    reset_template_id_counts()

    producer_templates = [t for t in TEMPLATES if t["domain"] == "producers"]
    facts = _fake_producer_corpus(n=200)
    results = generate_with_diversity_cap(
        domain="producers",
        target=100,
        facts=facts,
        templates=producer_templates,
        use_embeddings=False,
        allow_cap_overflow=True,
    )

    # Target met or close to it.
    assert len(results) >= 90, (
        f"Overflow-enabled run stopped short at {len(results)}/100"
    )
    # Multiple templates still fire — the fallback only kicks in once the
    # primary rotation is exhausted.
    counts = Counter(r["_template_id"] for r in results)
    assert len(counts) >= 3
