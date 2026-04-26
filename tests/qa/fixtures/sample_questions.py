"""Hand-crafted fixture questions, each engineered to trigger one weakness.

Each dict mimics the shape `fetch_corpus_questions` returns, so agents can
be unit-tested without any DB.
"""

from __future__ import annotations

# Base question template matching the real schema
_BASE = {
    "domain": "wine_regions",
    "subdomain": "italy_piedmont",
    "difficulty": "2",
    "cognitive_dim": "recall",
    "question_type": "multiple_choice",
    "tags": ["audit_pilot_v1"],
    "explanation": "Because Nebbiolo.",
    "generator": "claude",
    "generation_method": "fact_to_question",
    "template_id": None,
    "options": [
        {"id": "A", "text": "Nebbiolo"},
        {"id": "B", "text": "Sangiovese"},
        {"id": "C", "text": "Barbera"},
        {"id": "D", "text": "Dolcetto"},
    ],
    "correct_answer": "A",
    "correct_answer_text": "Nebbiolo",
    "public_qid": "WB-REG-0001-L2",
    "facts": [{
        "fact_id": "f-1",
        "fact_text": "Barolo DOCG in Piedmont, Italy, must be made from 100% Nebbiolo grapes.",
        "domain": "wine_regions",
        "subdomain": "italy_piedmont",
        "entities": [{"type": "country", "name": "Italy"}, {"type": "grape", "name": "Nebbiolo"}],
        "source_name": "Wikipedia",
        "source_url": "https://en.wikipedia.org/wiki/Barolo",
    }],
}


def _mk(uuid: str, question_text: str, **overrides) -> dict:
    q = dict(_BASE)
    q["uuid"] = uuid
    q["question_text"] = question_text
    # Allow overriding options / correct_answer / facts etc
    for k, v in overrides.items():
        q[k] = v
    return q


# 1 — Clean pass: atomic, specific, distractors consistent
CLEAN_QUESTION = _mk(
    "00000000-0000-0000-0000-000000000001",
    "Which grape is required to produce Barolo DOCG?",
)

# 2 — Vague / marketing phrasing in stem (A1 should fail)
VAGUE_STEM_QUESTION = _mk(
    "00000000-0000-0000-0000-000000000002",
    "Which legendary grape is grown in the world-renowned Barolo wine region?",
)

# 3 — Blend-as-variety misclassification (A1 fail via _BLEND_AS_VARIETY)
BLEND_QUESTION = _mk(
    "00000000-0000-0000-0000-000000000003",
    "Portuguese Red is grown in the Douro region — which category is it?",
    options=[
        {"id": "A", "text": "Grape variety"},
        {"id": "B", "text": "Blend category"},
        {"id": "C", "text": "Appellation"},
        {"id": "D", "text": "Vineyard"},
    ],
    correct_answer="B",
    correct_answer_text="Blend category",
)

# 4 — Verbatim source copying (A3 fail via high LCS ratio)
VERBATIM_QUESTION = _mk(
    "00000000-0000-0000-0000-000000000004",
    "Barolo DOCG in Piedmont Italy must be made from 100% Nebbiolo grapes — which grape?",
)

# 4a — True/false question over a short source fact. Without the v1.2.0 skip,
# the LCS metric over-flags T/F because the 1-token correct option ("True"/
# "False") doesn't dilute the LCS denominator. With v1.2.0, A3 should skip
# entirely and emit a PASS finding with a "skipped: true_false" note.
TRUE_FALSE_HIGH_OVERLAP_QUESTION = _mk(
    "00000000-0000-0000-0000-0000000000a4",
    "True or false: Barolo DOCG in Piedmont Italy must be made from 100% Nebbiolo grapes.",
    question_type="true_false",
    options=[
        {"id": "A", "text": "True"},
        {"id": "B", "text": "False"},
    ],
    correct_answer="A",
    correct_answer_text="True",
)

# 4b — Borderline LCS case (LCS computes to 0.625, longest n-gram = 4).
# Under v1.1.0 (`_A3_FAIL_LCS = 0.60`) this would FAIL. Under v1.2.0
# (`_A3_FAIL_LCS = 0.65`) this should PASS or WARN, NOT FAIL — a hair-
# trigger LCS overlap with no extended verbatim span isn't a real defect.
A3_BORDERLINE_LCS_QUESTION = _mk(
    "00000000-0000-0000-0000-0000000000b4",
    "Is Barolo located in northern Italy?",
    options=[
        {"id": "A", "text": "Red wine"},
        {"id": "B", "text": "White wine"},
        {"id": "C", "text": "Sparkling"},
        {"id": "D", "text": "Rosé"},
    ],
    correct_answer="A",
    correct_answer_text="Red wine",
    facts=[{
        "fact_id": "f-borderline",
        "fact_text": "The Barolo wine region is located in northern Italy.",
        "domain": "wine_regions",
        "subdomain": "italy_piedmont",
        "entities": [{"type": "country", "name": "Italy"}],
        "source_name": "Wikipedia",
        "source_url": "https://en.wikipedia.org/wiki/Barolo",
    }],
)

# 4c — High LCS, low n-gram (LCS = 0.6667, longest n-gram = 2). Above the
# v1.2.0 fail threshold (0.65); should FAIL even though the contiguous
# match is short — exercises the LCS-only fail path at the new threshold.
A3_HIGH_LCS_QUESTION = _mk(
    "00000000-0000-0000-0000-0000000000c4",
    "Where is Barolo located?",
    options=[
        {"id": "A", "text": "northern Italy"},
        {"id": "B", "text": "southern Spain"},
        {"id": "C", "text": "central France"},
        {"id": "D", "text": "western Greece"},
    ],
    correct_answer="A",
    correct_answer_text="northern Italy",
    facts=[{
        "fact_id": "f-highlcs",
        "fact_text": "The Barolo wine region is located in northern Italy.",
        "domain": "wine_regions",
        "subdomain": "italy_piedmont",
        "entities": [{"type": "country", "name": "Italy"}],
        "source_name": "Wikipedia",
        "source_url": "https://en.wikipedia.org/wiki/Barolo",
    }],
)

# 4d — Long contiguous verbatim span (12 tokens) embedded in a longer
# question that pads the LCS denominator down. LCS = 0.5714 (below the
# 0.65 fail threshold) but n-gram = 12 (≥ 8) → must FAIL on the n-gram
# path. Mirrors the WB-VIT-0300 v6 case.
A3_LONG_NGRAM_QUESTION = _mk(
    "00000000-0000-0000-0000-0000000000d4",
    "Phylloxera vastatrix is a sap sucking insect that feeds on grape vine.",
    options=[
        {"id": "A", "text": "Some other padding tokens here yes more padding tokens"},
        {"id": "B", "text": "Botrytis cinerea fungus"},
        {"id": "C", "text": "Mealybug colony"},
        {"id": "D", "text": "Powdery mildew spores"},
    ],
    correct_answer="A",
    correct_answer_text="Some other padding tokens here yes more padding tokens",
    facts=[{
        "fact_id": "f-longngram",
        "fact_text": (
            "Phylloxera vastatrix is a sap sucking insect that feeds on grape "
            "vine roots and leaves causing widespread devastation in European "
            "vineyards starting in the late nineteenth century"
        ),
        "domain": "viticulture",
        "subdomain": "phylloxera",
        "entities": [{"type": "pest", "name": "Phylloxera"}],
        "source_name": "Wikipedia",
        "source_url": "https://en.wikipedia.org/wiki/Phylloxera",
    }],
)

# 5 — Length-biased correct option (A2 length warn on cell)
LENGTH_BIAS_QUESTION = _mk(
    "00000000-0000-0000-0000-000000000005",
    "Which is the most widely planted grape in Barolo DOCG?",
    options=[
        {"id": "A", "text": "Nebbiolo — a noble red grape native to Piedmont with late ripening, thick skin, high acidity and robust tannins used exclusively for DOCG production"},
        {"id": "B", "text": "Merlot"},
        {"id": "C", "text": "Syrah"},
        {"id": "D", "text": "Zinfandel"},
    ],
)

# 6 — Position bias: batch of all-A correct (A2 fail on cell χ²)
POSITION_BIAS_BATCH = [
    _mk(f"00000000-0000-0000-0000-0000000000{10+i:02d}",
        f"Biased question #{i+1}",
        correct_answer="A")
    for i in range(25)
]

# 7 — Cross-category distractor leak (C2 fail)
CATEGORY_LEAK_QUESTION = _mk(
    "00000000-0000-0000-0000-000000000040",
    "Which red wine is characteristic of Piedmont?",
    options=[
        {"id": "A", "text": "Barolo (Nebbiolo)"},
        {"id": "B", "text": "Franciacorta (sparkling method traditionnelle)"},  # sparkling leaks
        {"id": "C", "text": "Chianti (Sangiovese)"},
        {"id": "D", "text": "Valpolicella (Corvina)"},
    ],
)

# 8 — Template-grammar question (used to *train* A4 positive class)
TEMPLATE_QUESTIONS = [
    _mk(
        f"00000000-0000-0000-0000-0000000000{60+i:02d}",
        q_text,
        generation_method="template",
        generator="template_only",
        template_id=f"T-REG-{i:02d}",
    )
    for i, q_text in enumerate([
        "Which country is the Barolo wine region located in?",
        "Which country is the Champagne wine region located in?",
        "Which country is the Rioja wine region located in?",
        "Which grape is primarily used in Barolo wine?",
        "Which grape is primarily used in Champagne wine?",
        "Which grape is primarily used in Rioja wine?",
        "True or false: Barolo is located in Italy.",
        "True or false: Champagne is located in France.",
        "True or false: Rioja is located in Spain.",
        "In which country is the Sancerre appellation located?",
        "In which country is the Mosel appellation located?",
        "In which country is the Douro appellation located?",
        "Which wine region produces Nebbiolo?",
        "Which wine region produces Chardonnay?",
        "Which wine region produces Tempranillo?",
        "What is the primary grape of the Barolo region?",
        "What is the primary grape of the Champagne region?",
        "What is the primary grape of the Rioja region?",
        "Is Nebbiolo planted in Piedmont?",
        "Is Sangiovese planted in Tuscany?",
        "Is Tempranillo planted in Rioja?",
        "Which country is the Mendoza wine region located in?",
        "Which country is the Napa wine region located in?",
        "Which country is the Marlborough wine region located in?",
    ])
]

LLM_FREEFORM_QUESTIONS = [
    _mk(
        f"00000000-0000-0000-0000-0000000000{90+i:02d}",
        q_text,
    )
    for i, q_text in enumerate([
        "A winemaker in Piedmont has a 3-hectare parcel of 25-year-old Nebbiolo vines on south-facing limestone slopes. After a warm, early-harvested vintage, they observe unusually soft tannins in the must. Which choice best explains this?",
        "Given that the Barolo MGA system designates vineyard-specific crus, what does the designation 'Cannubi' imply about the resulting wine compared to a generic Barolo?",
        "Consider two Piedmont producers with identical vineyard plots but different fermentation practices. Producer X uses 30-day maceration while Producer Y uses 10-day maceration. Which sensory outcome is most expected?",
        "Why do Nebbiolo wines from elevations above 400m typically develop higher natural acidity than wines from valley-floor vineyards?",
        "An importer receives two Barolo wines from the same vintage but different producers. Wine A shows more evolved aromatics at bottling. Which factor most likely accounts for this?",
        "If a Piedmont winemaker adopted stainless-steel fermentation instead of traditional botti, which tasting profile change would be most noticeable after 5 years in bottle?",
        "How does the DOCG requirement of minimum 38-month aging influence Barolo's commercial release cycle compared to DOC Nebbiolo d'Alba?",
        "A sommelier notes that two bottles of Barolo from the same estate but different crus show distinctly different tannin structures. Which vineyard characteristic most plausibly drives this?",
        "Consider a Barbera-based wine and a Nebbiolo-based wine from neighbouring Piedmont communes. Which aspect differs most systematically between them?",
        "When a producer chooses to label their wine 'Barolo Riserva', what production commitment does this entail regarding aging and quality?",
        "Why might a conscientious buyer pay a premium for a single-cru Barolo over a blended one from the same estate?",
        "How does the late-ripening character of Nebbiolo influence where in Piedmont it can be successfully grown?",
        "A taster identifies rose, tar, and red cherry aromas in a wine but is unsure of the origin. Which grape's typicity best matches this profile?",
        "If a Barolo vineyard shifted from classic pergola training to vertical shoot positioning, which yield and quality effects would be most likely?",
        "Under the current DOCG regulations, how would a producer legally respond if a hailstorm reduced their yield below economic viability?",
        "Two adjacent parcels in La Morra differ only in row orientation. How might this affect final wine style?",
        "A New-World winemaker wants to create a Nebbiolo-inspired style. Which geographic feature would be most important to replicate?",
        "How does the interaction of Nebbiolo's thick skins with extended maceration produce the grape's signature tannin profile?",
        "When comparing Barolo and Barbaresco, which factor explains Barbaresco's generally shorter minimum aging requirement?",
        "If a warming climate shifts Piedmont harvest by two weeks, which organoleptic property is most at risk for Nebbiolo?",
        "A retailer observes that Barolo allocations from top producers sell out pre-release. Which economic mechanism best describes this phenomenon?",
        "Under what conditions would a Piedmont producer choose to declassify a Barolo to Langhe Nebbiolo?",
        "How does the use of large neutral Slavonian oak barrels ('botti') influence Nebbiolo's colour trajectory compared to small new French oak?",
        "A blind taster correctly identifies Nebbiolo despite a unfamiliar producer. Which cue is most diagnostic?",
    ])
]


ALL_FIXTURES = [
    CLEAN_QUESTION,
    VAGUE_STEM_QUESTION,
    BLEND_QUESTION,
    VERBATIM_QUESTION,
    TRUE_FALSE_HIGH_OVERLAP_QUESTION,
    A3_BORDERLINE_LCS_QUESTION,
    A3_HIGH_LCS_QUESTION,
    A3_LONG_NGRAM_QUESTION,
    LENGTH_BIAS_QUESTION,
    *POSITION_BIAS_BATCH,
    CATEGORY_LEAK_QUESTION,
    *TEMPLATE_QUESTIONS,
    *LLM_FREEFORM_QUESTIONS,
]
