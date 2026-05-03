"""
OenoBench -- Prompt templates for question generation.

All prompts used by the generation pipeline are defined here as string
constants. The LLM reformats facts into questions -- it never invents facts.
"""

import hashlib

# ═══════════════════════════════════════════════════════════════════════════════
# Helper dictionaries
# ═══════════════════════════════════════════════════════════════════════════════

DIFFICULTY_DESCRIPTIONS = {
    "1": (
        "Beginner / Wine enthusiast / WSET Level 1-2. "
        "Major regions, common grapes, basic winemaking terms."
    ),
    "2": (
        "Intermediate / WSET Level 3 / Certified Sommelier. "
        "Specific appellations, winemaking details, regional regulations."
    ),
    "3": (
        "Advanced / WSET Diploma / Advanced Sommelier. "
        "Precise subregions, technical viticulture, comparative knowledge."
    ),
    "4": (
        "Expert / Master of Wine / Master Sommelier level. "
        "Obscure details, precise numbers, exceptions to rules."
    ),
}

COGNITIVE_DESCRIPTIONS = {
    "recall": "Direct factual retrieval. 'What is...', 'Which...', 'Name the...'",
    "comprehension": "Understanding concepts. 'Why does...', 'Explain how...'",
    "application": "Applying knowledge to a new scenario or context.",
    "analysis": "Breaking down, comparing, contrasting, or distinguishing.",
    "synthesis": "Combining multiple pieces of knowledge to form a conclusion.",
    "evaluation": "Judging, critiquing, or assessing quality/correctness.",
}

QUESTION_TYPE_INSTRUCTIONS = {
    "multiple_choice": (
        "Provide exactly 4 options labeled A-D. Exactly one is correct."
    ),
    "multiple_select": (
        "Provide 5-6 options labeled A-F. Mark 2-3 as correct. "
        "Format correct_answer as comma-separated letters (e.g., 'A,C,E')."
    ),
    "true_false": (
        "State a claim derived from the fact. correct_answer is 'True' or 'False'. "
        "Provide 2 options: A) True, B) False."
    ),
    "matching": (
        "Provide items to match. Format options as pairs. "
        "correct_answer lists the correct pairings."
    ),
    "short_answer": (
        "Question requires a brief factual answer (1-5 words). "
        "Set options to null. correct_answer is the expected text."
    ),
    "scenario_based": (
        "Present a realistic wine scenario (winemaking decision, tasting, "
        "business case), then ask a question. Provide 4 options A-D."
    ),
}


# ═══════════════════════════════════════════════════════════════════════════════
# JSON output schema (shared across templates)
# ═══════════════════════════════════════════════════════════════════════════════

_JSON_SCHEMA = """\
{
  "question_text": "The full question text",
  "options": [
    {"id": "A", "text": "First option"},
    {"id": "B", "text": "Second option"},
    {"id": "C", "text": "Third option"},
    {"id": "D", "text": "Fourth option"}
  ],
  "correct_answer": "A",
  "correct_answer_text": "The text of the correct option",
  "explanation": "Why this answer is correct and others are wrong, citing the fact",
  "tags": ["relevant", "topic", "tags"],
  "confidence": 0.0-1.0
}"""

# Phase 2g.18 lever L5: ask the generator to self-report confidence in the
# correctness of the answer key. When the closed-book gate also passes
# (question is non-trivial) AND confidence ≥ 0.9, the independent-solver
# verifier (Llama/Qwen) can be skipped via OENOBENCH_VERIFIER_SKIP=1.
# Calibration matters — instruct the LLM to actually distinguish high-vs-low
# confidence rather than always emitting 1.0.
_JSON_SCHEMA_NOTE = (
    'For short_answer questions, set "options" to null. '
    'For true_false, provide only options A (True) and B (False). '
    'Set "confidence" between 0.0 and 1.0 reflecting how certain you are '
    'that the source fact supports the keyed answer over every distractor. '
    'Use ≥0.9 only when the fact unambiguously entails the key; use ≤0.7 '
    'when the fact only weakly supports the key or any distractor is '
    'partially true.'
)


# ═══════════════════════════════════════════════════════════════════════════════
# Shared boilerplate (Phase 2g.14 — DRY refactor + minor tightening)
# ═══════════════════════════════════════════════════════════════════════════════
#
# v9–v11 templates duplicated the PARAPHRASE_RULE and AVOID-WORLD-KNOWLEDGE
# header across 5–10 occurrences each (~3KB of duplicated boilerplate). Phase
# 2g.14 factors them into shared constants composed via f-string interpolation
# at module load. Each template's variant-specific second/third bullets stay
# inline so per-template wording (singular/plural/target, observable-attribute
# emphasis, skip-reason) is preserved.
#
# The iconic-entities list was tightened from 7 named examples down to 5 of
# the most-globally-recognised, dropping the more obscure cuts while keeping
# the prompt's intent. Modest token reduction (~30 chars × 10 occurrences).

_ICONIC_ENTITIES_LIST = (
    "Château Margaux, Napa Valley, Dom Pérignon, Romanée-Conti, Barolo, Champagne, Penfolds Grange, etc."
)

_PARAPHRASE_RULE_SINGULAR = (
    "PARAPHRASE RULE: Rephrase the source fact in your own words. Do NOT "
    "copy more than 5 consecutive words verbatim from the source fact into "
    "the question or any option. Synonyms, restructured clauses, and "
    "inversions are required."
)

_PARAPHRASE_RULE_PLURAL = (
    "PARAPHRASE RULE: Rephrase the source facts in your own words. Do NOT "
    "copy more than 5 consecutive words verbatim from any source fact into "
    "the question or any option. Synonyms, restructured clauses, and "
    "inversions are required."
)


def _avoid_wk_first_bullet(fact_phrase: str) -> str:
    """First bullet of every AVOID-WORLD-KNOWLEDGE block.

    The opening bullet was identical across all 10 templates except for
    the trailing fact-phrase ("source fact" / "source facts" / "target
    fact"). Factored here so the iconic-entities list lives in one place.

    2g.17: A second bullet was appended as prompt-level defense-in-depth
    against "which region grows [ubiquitous grape]?" stems that slip
    through sample-time filters (Team A, _fact_sampler.py).
    """
    bullet_one = (
        "- DO NOT phrase questions as recall on globally-famous entities "
        f"({_ICONIC_ENTITIES_LIST}). A well-read taster should not be "
        f"able to answer without the {fact_phrase}."
    )
    bullet_two = (
        "- DO NOT phrase questions as \"Which region produces [grape]?\" when the\n"
        "  grape is one of the globally-ubiquitous international varieties\n"
        "  (Cabernet Sauvignon, Chardonnay, Merlot, Pinot Noir, Sauvignon Blanc,\n"
        "  Syrah, Shiraz, Riesling). Lead instead with a regulatory or technical detail\n"
        "  (minimum aging, yield cap, soil type, blend %) that is unique\n"
        "  to that region."
    )
    return bullet_one + "\n" + bullet_two


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Fact-to-Question (single fact -> single question)
# ═══════════════════════════════════════════════════════════════════════════════

FACT_TO_QUESTION_SYSTEM = """\
You are a wine education assessment designer creating questions for OenoBench, \
an AI benchmark that evaluates wine knowledge. You create precise, unambiguous \
questions ONLY from the facts provided to you. You never invent, assume, or \
extrapolate beyond the given fact.

Rules:
1. The correct answer MUST be directly and unambiguously supported by the \
provided fact. Do not require knowledge beyond what the fact states.
2. Distractors (wrong options) must be plausible to someone with partial \
knowledge but clearly wrong given the fact. Use real wine entities as \
distractors (real regions, real grapes, real producers) -- never invented names.
3. Questions must be self-contained. A knowledgeable reader should be able to \
answer without any external context. Never reference "the passage", "the text", \
or "according to the source".
4. Match the specified difficulty level and cognitive dimension exactly.
5. Output valid JSON only. No text before or after the JSON object.
6. Blend categories (e.g., "Red Blend", "White Blend", "Bordeaux-style Red \
Blend", "Portuguese Red") are NOT grape varieties. Never refer to them as \
varieties. If a fact treats a blend category as a variety, rephrase the \
question to use accurate terminology (e.g., "wine style", "blend category", \
"wine type")."""

FACT_TO_QUESTION_TEMPLATE = (
    "Create a {question_type} question from the following fact.\n\n"
    + _PARAPHRASE_RULE_SINGULAR + "\n\n"
    + "AVOID WORLD-KNOWLEDGE SOLVABILITY:\n"
    + _avoid_wk_first_bullet("source fact") + "\n"
) + """\
- DO lead questions with an OBSERVABLE ATTRIBUTE from the source fact (aging \
months, soil type, yield limit, phenolic threshold, clone name, altitude, \
specific varietal %, regulatory minimum, grape blend percentage) and ask the \
test-taker to infer the entity.
- If the only fact-specific content is a famous entity name with no \
technical/regulatory/attribute detail, output instead: \
{{"skip": true, "reason": "Iconic entity without fact-specific technical depth"}}

FACT: {fact_text}
SOURCE: {source_name}
DOMAIN: {domain}

PARAMETERS:
- Difficulty: {difficulty} -- {difficulty_description}
- Cognitive dimension: {cognitive_dim} -- {cognitive_description}
- Question type: {question_type} -- {question_type_description}

TYPE-SPECIFIC INSTRUCTIONS:
{type_specific_instructions}

QUALITY REQUIREMENTS:
- The correct answer must be directly supported by the fact above
- Distractors must be plausible but clearly wrong given the fact
- The question must be self-contained and answerable without additional context
- Do not reference the source, say "according to...", or hint at the answer
- Use precise wine terminology appropriate for the difficulty level
- The explanation should cite the fact and explain why each distractor is wrong

DISTRACTOR RULES:
- For questions involving years or dates, distractors must be CLOSE (within 2-5 \
years of the correct answer), not evenly spaced decades apart
- For questions involving numeric values (hectares, percentages), distractors \
must be plausible nearby values, not obviously wrong round numbers
- Never use the pattern of spacing options exactly 10 years apart

FACT QUALITY GATE:
- If the fact is vague, generic, or subjective (e.g., "wines are highly regarded", \
"the region is famous", "it is one of the best"), DO NOT generate a question. \
Instead, output: {{"skip": true, "reason": "Fact too vague for unambiguous question"}}
- If the fact is promotional or marketing language (e.g., "intriguing and \
fascinating", "discover the excellence", "a must-visit destination"), DO NOT \
generate a question. Instead, output: {{"skip": true, "reason": "Marketing content"}}
- Only generate questions from facts that contain specific, verifiable information

QUESTION STYLE — INFERENCE OVER RECALL (HARD RULES):
1. Never ask "Which famous X produces Y?" or "What is Château Z known for?" \
when X, Y, or Z is a globally-famous entity.
2. Lead with fact-specific attributes (numbers, clones, minimum aging, soil \
type, yield cap, blend %), NOT with entity names.
3. The test-taker must *need* the source fact to select the correct answer — \
if a wine-reading generalist could answer without it, rewrite or skip.
4. Distractors should swap or reverse the key fact-specific attribute so a \
test-taker who confuses similar entities picks the wrong answer.

OUTPUT FORMAT (JSON):
{json_schema}

{json_schema_note}

Generate the question now."""


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Comparative questions (2-4 facts about different entities)
# ═══════════════════════════════════════════════════════════════════════════════

COMPARATIVE_SYSTEM = """\
You are a wine education assessment designer creating comparative questions \
for OenoBench, an AI benchmark. You compare wine entities using ONLY the facts \
provided. You never invent or assume information beyond what is given.

Rules:
1. The question must require comparing or contrasting the provided entities.
2. The correct answer must be derivable solely from the provided facts.
3. Distractors must be plausible comparisons that are wrong given the facts.
4. Never reference sources or use phrases like "according to" or "based on the text".
5. Output valid JSON only. No text before or after the JSON object.
6. Blend categories (e.g., "Red Blend", "White Blend") are NOT grape varieties. \
Never refer to them as varieties — use "wine style" or "blend category" instead.
7. FACT-ANCHORING (v2.2 fix #9): BOTH halves of the comparative must be \
supported by a DISTINCT source fact from the set you are given. Do NOT invent \
a comparison that isn't anchored in the facts. If one entity's fact is garbled, \
incomplete, or missing the comparable attribute, return \
{{"error": "no_comparison", "reason": "..."}} — do not force a comparison.
8. DISTRACTOR TYPE CONSISTENCY (v2.2 fix #9): All distractors must be of the \
SAME entity type as the correct answer. If the correct answer is a grape, all \
distractors must be grapes. If it's an appellation, all distractors are \
appellations. Never mix grapes, regions, producers, or classifications in one \
option set."""

COMPARATIVE_TEMPLATE = (
    "Create a comparative question using these facts about different but "
    "related wine entities.\n\n"
    + _PARAPHRASE_RULE_SINGULAR + "\n\n"
    + "AVOID WORLD-KNOWLEDGE SOLVABILITY:\n"
    + _avoid_wk_first_bullet("source facts") + "\n"
) + """\
- DO lead with an OBSERVABLE ATTRIBUTE from the facts (aging months, soil \
type, yield limit, phenolic threshold, clone name, altitude, specific \
varietal %, regulatory minimum, blend percentage) and ask the test-taker \
to infer which entity it describes.
- ICONIC-SKIP RULE (TYPE-CONDITIONAL on COMPARISON TYPE below):
  * For comparison types `most_least` and `same_vs_different`: if both \
facts describe only iconic entities with no fact-specific \
technical/regulatory/attribute detail, output: \
{{"skip": true, "reason": "Iconic entities without fact-specific technical depth"}}. \
These framings test technical/quantitative depth, so name-recognition \
answers are world-knowledge-solvable.
  * For comparison type `which_one`: iconic entities ARE valid subjects — \
"which of these famous entities matches attribute X" is a legitimate \
identification framing PROVIDED the answer pivots on a specific \
source-fact detail (an attribute, number, or regulatory clause that \
appears verbatim or paraphrased in the facts). Skip ONLY if the facts \
contain no usable retrievable detail to anchor the identification \
clue on (e.g., the fact text is a fragment, a bare name with no \
predicate, or otherwise has zero detail beyond the entity name).

ENTITY A: {entity_a}
FACT A: {fact_a}

ENTITY B: {entity_b}
FACT B: {fact_b}

COMPARISON TYPE: {comparison_type}

WHY THESE ARE COMPARABLE: {comparison_context}

The question should exploit this specific relationship to test the ability \
to distinguish between these similar entities.

QUESTION DESIGN — INFERENCE OVER RECALL (HARD RULES):
1. Never ask "Which of these famous entities has attribute X?" — pure recall \
on globally-famous entities is world-knowledge-solvable.
2. Lead with fact-specific attributes, NOT entity names. Present the \
attribute profile (minimum aging, blend %, soil signature, altitude, \
production cap, etc.) and ask the test-taker to identify which entity it \
matches.
3. The test-taker must *need* BOTH source facts to reach the answer — if \
they can solve it with only general wine knowledge, rewrite or skip.
4. Distractors must reverse or swap the distinguishing attribute between the \
two entities so confusing them selects the wrong answer.

QUALITY REQUIREMENTS:
- The question MUST be about a meaningful, knowledge-testing difference \
or similarity between the two entities — not trivial metadata differences
- Both facts must be load-bearing — removing either fact should make the \
question unanswerable
- All options must reference real wine entities or attributes
- The explanation must cite the specific facts that support the correct answer
- Question difficulty should be intermediate to advanced (level 2-3)

SKIP CONDITIONS — output {{"skip": true, "reason": "..."}} if:
- The two facts don't contain a meaningful, testable comparison
- Cross-country pairs ARE acceptable when the comparison hinges on a \
comparable attribute that BOTH source facts independently anchor (e.g., \
"Pinot Noir in Burgundy vs Oregon: which has the higher minimum aging?"). \
Do NOT skip purely on country mismatch.
- Skip ONLY when the two facts share no comparable attribute at all (e.g., \
one fact is about producer founding year, the other about a grape's \
botanical origin — no axis of comparison).
- The only possible question would test trivial metadata, not wine knowledge

OUTPUT FORMAT (JSON):
{json_schema}

Generate the comparative question now."""


COMPARATIVE_TEMPLATE_SAME_VS_DIFFERENT = (
    "Create a comparative question using these facts about two entities "
    "that share a common context but differ on a specific dimension.\n\n"
    + _PARAPHRASE_RULE_SINGULAR + "\n\n"
    + "AVOID WORLD-KNOWLEDGE SOLVABILITY:\n"
    + _avoid_wk_first_bullet("source facts") + "\n"
) + """\
- DO lead with the OBSERVABLE VALUE of the {dimension} dimension (e.g. the \
specific aging months, varietal %, altitude, yield cap) and ask the \
test-taker to infer which entity matches.
- If neither fact has fact-specific detail beyond naming an iconic entity, \
output instead: \
{{"skip": true, "reason": "Iconic entities without fact-specific technical depth"}}

ENTITY A: {entity_a}
FACT A: {fact_a}

ENTITY B: {entity_b}
FACT B: {fact_b}

SHARED CONTEXT: {comparison_context}
DISTINGUISHING DIMENSION: {dimension}

The question should test the ability to distinguish between these two entities \
based on how they DIFFER on the {dimension} dimension, despite their shared \
context.

QUESTION DESIGN — INFERENCE OVER RECALL (HARD RULES):
1. Never ask "Which of these famous entities has attribute X?" — pure recall \
on iconic names is world-knowledge-solvable.
2. Lead with the fact-specific {dimension} value, NOT entity names. Present \
the value and ask the test-taker to identify which entity it corresponds to.
3. The test-taker must *need* BOTH source facts — if general wine knowledge \
suffices, rewrite or skip.
4. Distractors must reverse or swap the {dimension} value between the two \
entities so confusing them selects the wrong answer.

QUALITY REQUIREMENTS:
- The question MUST highlight a meaningful difference on the {dimension} dimension
- Both facts must be load-bearing — removing either should make the question \
unanswerable
- All options must reference real wine entities or attributes
- The explanation must cite the specific facts that support the correct answer
- Difficulty: intermediate to advanced (level 2-3)

SKIP CONDITIONS — output {{"skip": true, "reason": "..."}} if:
- The two facts don't contain a meaningful, testable difference on {dimension}
- The distinguishing detail is trivially obvious or uninteresting
- The only possible question would test trivial metadata, not wine knowledge

OUTPUT FORMAT (JSON):
{json_schema}

Generate the comparative question now."""


COMPARATIVE_TEMPLATE_WHICH_ONE = (
    'Create a "which one" identification question using these facts about '
    "related wine entities.\n\n"
    + _PARAPHRASE_RULE_SINGULAR + "\n\n"
    + "AVOID WORLD-KNOWLEDGE SOLVABILITY:\n"
    + _avoid_wk_first_bullet("source facts") + "\n"
) + """\
- DO build the identification clue set from OBSERVABLE ATTRIBUTES (aging \
months, soil type, yield limit, phenolic threshold, clone name, altitude, \
varietal %, regulatory minimum, blend percentage) drawn from the facts.
- ICONIC-ENTITY POLICY (which_one is RELAXED): Iconic entities are \
LEGITIMATE subjects for "which of these famous entities matches \
attribute X" identification framings, provided the answer pivots on a \
specific source-fact detail (an attribute, number, or regulatory clause \
that appears verbatim or paraphrased in the facts). Skip ONLY if the \
facts contain no usable retrievable detail to anchor the identification \
clue on (e.g., the fact text is a fragment, a bare name with no \
predicate, or otherwise has zero detail beyond the entity name). In \
that case output: \
{{"skip": true, "reason": "Source facts contain no retrievable detail to anchor an identification clue"}}.

{facts_block}

SHARED CONTEXT: {comparison_context}

The question should describe characteristics or attributes that match \
exactly ONE of the entities above, and the test-taker must identify \
which entity is being described.

QUESTION DESIGN — INFERENCE OVER RECALL (HARD RULES):
1. Never name the target entity in the question stem — the test-taker must \
derive it from the clues.
2. Lead with fact-specific attribute clues, NOT entity-recall prompts. Use \
specific numbers, varietal compositions, soils, or regulations.
3. The clue set must be answerable only by someone who knows the source \
facts — if world knowledge alone suffices, rewrite or skip.
4. Each distractor should be a real similar entity that matches SOME but \
not ALL clues, so partial knowledge picks wrong.

QUALITY REQUIREMENTS:
- Exactly one entity must be the unambiguous correct answer given the facts
- All entities should be plausible candidates before careful analysis
- The explanation must identify which specific clues distinguish the correct \
entity from each distractor
- Difficulty: intermediate to advanced (level 2-3)

SKIP CONDITIONS — output {{"skip": true, "reason": "..."}} if:
- The facts don't allow distinguishing one entity from the others
- The entities are too dissimilar to create a challenging identification task
- The only possible question would test trivial metadata, not wine knowledge

OUTPUT FORMAT (JSON):
{json_schema}

Generate the identification question now."""


COMPARATIVE_TEMPLATE_MOST_LEAST = (
    "Create a superlative comparison question using these facts that "
    "contain comparable numeric or ordinal values.\n\n"
    + _PARAPHRASE_RULE_SINGULAR + "\n\n"
    + "AVOID WORLD-KNOWLEDGE SOLVABILITY:\n"
    + _avoid_wk_first_bullet("source facts") + "\n"
) + """\
- DO lead with the OBSERVABLE NUMERIC VALUE from the facts (hectares, hl/ha, \
% alcohol, aging months, etc.) and ask the test-taker to identify which \
entity ranks highest/lowest on that dimension.
- If the facts contain only famous names with no fact-specific numeric \
value, output instead: \
{{"skip": true, "reason": "Iconic entities without fact-specific numeric depth"}}

{facts_block}

SHARED CONTEXT: {comparison_context}
NUMERIC DIMENSION: {dimension}

The question should ask which entity has the highest, lowest, largest, \
smallest, earliest, or latest value for a specific measurable attribute.

QUESTION DESIGN — INFERENCE OVER RECALL (HARD RULES):
1. Never ask "Which famous region has the largest X?" as pure recall — \
frame as a practical decision or observation that *needs* the specific \
numeric values in the facts.
2. Lead with the fact-specific numeric values, NOT entity names.
3. The test-taker must *need* the source facts to rank correctly — if \
general wine knowledge gives the answer, rewrite or skip.
4. Distractors are the other real entities from the comparison set, each \
with its real but different numeric value.

QUALITY REQUIREMENTS:
- All entities must have comparable numeric measurements for the same attribute
- The correct answer must be unambiguously derivable from the facts provided
- The explanation must cite the specific numeric values from each fact
- Difficulty: intermediate (level 2-3)

SKIP CONDITIONS — output {{"skip": true, "reason": "..."}} if:
- The numeric values aren't truly comparable (different units, different metrics)
- The comparison is trivially obvious (one value is 100x larger)
- Only one entity has a numeric value

OUTPUT FORMAT (JSON):
{json_schema}

Generate the superlative comparison question now."""


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Scenario-based questions (multi-fact synthesis)
# ═══════════════════════════════════════════════════════════════════════════════

SCENARIO_SYSTEM = """\
You are a wine education assessment designer creating scenario-based questions \
for OenoBench, an AI benchmark. You synthesize multiple facts into realistic \
wine scenarios. You use ONLY the facts provided -- you never invent additional \
wine knowledge.

Rules:
1. Create a realistic scenario (winemaking decision, tasting situation, \
business case, or service situation) that requires applying the provided facts.
2. The correct answer must be derivable from the combination of provided facts.
3. The scenario must be plausible and professionally relevant.
4. Never reference sources. The scenario should read naturally.
5. Output valid JSON only. No text before or after the JSON object.
6. Blend categories (e.g., "Red Blend", "White Blend") are NOT grape varieties. \
Never refer to them as varieties — use "wine style" or "blend category" instead.
7. SINGLE WINE CATEGORY (v2.2 fix #9 addendum): The scenario MUST NOT compare \
across wine categories. Do NOT write stems that ask the reader to choose \
between red vs white wines, sparkling vs still, fortified vs dry, etc. The \
scenario must operate within a single wine category (red OR white OR sparkling \
OR fortified OR sweet). If the provided facts span multiple categories, return \
{{"error": "multi_category_cluster", "reason": "..."}} instead of producing \
a question. All 3 audit-run-2 C2 category-leak failures were scenario stems \
explicitly comparing categories (red-vs-white, Sauvignon-Blanc-vs-premium-reds, \
pink-sparkling-by-blending-red-and-white)."""

SCENARIO_TEMPLATE = (
    "Create a scenario-based question that synthesizes these facts.\n\n"
    + _PARAPHRASE_RULE_SINGULAR + "\n\n"
    + "AVOID WORLD-KNOWLEDGE SOLVABILITY:\n"
    + _avoid_wk_first_bullet("source facts") + "\n"
) + """\
- DO ground the scenario in OBSERVABLE ATTRIBUTES from the facts (aging \
months, soil type, yield limit, phenolic threshold, clone name, altitude, \
varietal %, regulatory minimum, blend percentage, regional/producer/style \
associations) and ask the test-taker to infer the entity or decision.
- ICONIC-SKIP RULE (TYPE-CONDITIONAL):
  * For winemaking and viticulture scenarios: if every provided fact is just \
an iconic entity reference with no fact-specific technical/regulatory/numeric \
depth, output: \
{{"skip": true, "reason": "Iconic entities without fact-specific technical depth"}}. \
These framings test technical decision-making, so an answer that pivots only \
on name recognition is world-knowledge-solvable.
  * For tasting, business, and service scenarios: iconic entities (famous \
producers, classic regions, well-known styles) are LEGITIMATE subject matter \
— sommeliers identify renowned wines, retail staff recommend famous regions, \
buyers evaluate prestige labels. Skip ONLY if the source facts contain no \
usable information at all (e.g., the fact text is a fragment, a bare name \
with no predicate, or otherwise has zero retrievable detail to anchor a \
question on). A fact like "Domaine de la Romanée-Conti is a Burgundy producer \
of Pinot Noir" IS usable for service/tasting/business scenarios even though \
it is iconic.

FACTS:
{facts}

SCENARIO TYPE: {scenario_type}

Build a realistic wine scenario that requires applying knowledge from multiple \
facts above. The test-taker should need to synthesize information to arrive at \
the correct answer.

COHERENCE CHECK — before generating, verify that ALL facts relate to a single \
coherent decision context. The facts should address different aspects of the \
SAME situation (e.g., a grape's characteristics + its regional regulations + \
its typical vinification). If the facts are about unrelated topics that cannot \
naturally arise in one scenario, output: \
{{"skip": true, "reason": "Facts too unrelated for coherent scenario"}}. \
For example, a fact about white wine residual sugar and a fact about red wine \
volatile acidity do NOT belong in the same scenario unless the situation \
specifically involves comparing both wines.

SCENARIO TYPE GUIDANCE — match the persona, decision context, and anchor style \
to the scenario_type above. Only the block matching {scenario_type} applies; \
the others are shown for calibration.

- winemaking:
  * Persona: a winemaker or cellar master.
  * Context: a technical decision about technique, timing, vessel, or \
materials (fermentation temperature, MLF, pressing regime, élevage choice, \
fining/filtration, blending percentages).
  * Anchor examples: "given a 24-month barrel-aging minimum and 13% min ABV \
under DOCG X, which élevage program qualifies?"; "with phenolic ripeness \
reached at 14.2% potential alcohol, which press fraction should be excluded?"

- viticulture:
  * Persona: a grower, vineyard manager, or viticulturist.
  * Context: a vineyard-floor decision about planting, training, canopy, \
irrigation, pest pressure, or harvest timing.
  * Anchor examples: "given 1,800 m elevation and a 60 hl/ha yield cap under \
the appellation rules cited, which canopy approach satisfies both ripening \
and yield?"; "with the named clone's documented bud-break date and frost \
risk window, which training system fits?"

- tasting:
  * Persona: a sommelier, taster, or wine educator running a blind or guided \
tasting.
  * Context: identifying, describing, pairing, or selecting wines from \
sensory and provenance cues. Iconic producers, classic regions, and signature \
styles ARE the legitimate subject matter here.
  * Anchor examples: "the flight shows a wine with the regional signature \
described in the facts (e.g., Mosel slate-driven Riesling at the cited \
Prädikat level) — which bottle is it?"; "given the producer's house style \
detail from the source fact, which glass in the lineup matches?"

- business:
  * Persona: a wine buyer, distributor, importer, brand manager, or market \
analyst.
  * Context: a purchasing, pricing, allocation, or market-positioning \
decision. Famous regions and prestige producers ARE the legitimate subject \
matter — buying decisions routinely turn on classification tier, allocation \
mechanics, or producer reputation.
  * Anchor examples: "given the cited classification level and the producer's \
allocation policy from the source fact, which channel placement maximizes \
sell-through?"; "with the appellation's named sub-tier and its production \
volume from the facts, which price band is defensible?"

- service:
  * Persona: a restaurant sommelier, retail wine advisor, or hospitality \
professional advising a guest or customer.
  * Context: recommending or pairing a wine for a specific guest preference, \
dish, or occasion. Iconic regions and well-known producers are EXACTLY what \
service staff steer customers toward — recognizing them is the job.
  * Anchor examples: "a guest asks for the producer's signature style \
described in the facts to pair with the named dish — which bottle on the \
list fits?"; "for a customer requesting the regional style detailed in the \
source fact, which by-the-glass option matches?"

QUESTION DESIGN — INFERENCE OVER RECALL (HARD RULES):
1. Never build a scenario around "which famous Y is this?" — pure recall on \
iconic names is world-knowledge-solvable.
2. Lead the scenario with fact-specific observations (numeric values, named \
regulations, specific techniques), NOT entity names.
3. The question must be unsolvable without synthesizing ALL provided facts — \
if a wine-reading generalist could answer without them, rewrite or skip.
4. Distractors must reverse or swap key relationships from the facts, so a \
test-taker relying on general knowledge picks wrong.

HARD RULES — NON-DERIVABLE ANCHOR (closed-book leakage prevention):
1. ANCHOR REQUIREMENT — The correct answer MUST hinge on a specific anchor \
drawn directly from one of the source facts: a numeric threshold (yield cap, \
ABV minimum, hectares, % varietal, aging months), a year (founding, \
regulation, classification), a named entity (specific producer not on the \
iconic list, specific clone designation, specific AVA/DOC sub-tier name, \
specific person), or an exact regulatory value (allowed grape list item, \
sweetness term, vessel material). Generic regional/category facts are NOT \
anchors — "Andean elevation", "Old World techniques", "natural barriers \
reduce pests", "fortified because grape spirit added", "icewine freezes on \
vine", "Crémant uses traditional method", and well-known grape synonyms \
("Franconia Nera = Blaufränkisch") are world-knowledge cliches that a \
frontier LLM solves closed-book. If your only candidate anchor is one of \
those, the cluster is inadequate — output skip.

2. STEM SCRUBBING — The scenario premise MUST NOT contain the answer or any \
synonym/paraphrase of it. Do not write a stem that says "the team wants \
the vessel most strongly associated with that culture: a very large clay \
container lined internally with beeswax" and then offer "qvevri" as the \
correct option — the stem already describes the answer. Do not say \
"raising its alcohol with added grape spirit" and then ask the test-taker \
to classify it as "fortified" — the stem already names the category. \
Hide the answer from the stem.

3. SUBSTITUTION TEST — If you replaced the source fact(s) with analogous \
fact(s) from a different region/grape/producer, the question MUST become \
factually wrong (not merely awkward). If a Chilean fact could be swapped \
for an Argentine fact and the answer would still be the same (e.g. \
"high-elevation vineyards yield concentrated wines"), the question is \
world-knowledge-solvable — REWRITE or skip.

4. CLICHE BLOCKLIST — These answer patterns are world-knowledge cliches and \
must NOT be the correct answer unless the source fact provides a specific \
numeric/named anchor a generalist could not guess: "reduce irrigation for \
quality"; "barrel ferment + MLF for full body"; "natural barriers reduce \
pest pressure"; "fortified wine = added grape spirit"; "vintage indicates \
harvest year not quality"; "Old World methods for age-worthy wines"; "high \
elevation means concentration"; "qvevri for amber Georgian wine"; "vin de \
pays allows varietal labels"; "Roman influence on early German viticulture"; \
"reduce yields for quality"; "thin skins → sunburn risk → leaf cover"; \
"icewine freeze-on-vine → low juice yield → high price"; "Crémant/Trento \
DOC use traditional method"; common grape synonym recognition. If your \
draft answer is one of these, REWRITE with a fact-specific anchor (move a \
textbook detail from the stem into a distractor; pin the answer on a \
specific sub-tier number or named entity from the source fact) or skip. \
These cliche bans apply most strictly to winemaking and viticulture \
scenarios; for tasting, business, and service the test is the appropriate \
USE of regional/producer/style associations, so cliche framing is acceptable \
provided the answer still pivots on a specific source-fact detail (a named \
producer, classification tier, allocation mechanic, regional signature, or \
service-relevant attribute drawn from the facts) rather than on textbook \
recall alone.

5. FRONTIER-LLM SELF-CHECK — Before emitting, pretend a frontier LLM is \
answering with the source facts hidden. Frontier LLMs know virtually all \
mainstream wine textbook material. The correct answer must hinge on a \
detail that ONLY the source fact establishes — a precise number, a niche \
name, an unusual regulatory tier — not on textbook knowledge. If your \
draft fails this bar, output: {{"skip": true, "reason": "..."}}.

QUALITY REQUIREMENTS:
- The scenario must feel authentic and professionally relevant
- ALL provided facts must be load-bearing in the reasoning path — if a fact \
can be removed without changing the answer, the question is too simple
- All options must be plausible actions or conclusions
- The explanation must trace the reasoning through the relevant facts
- Target difficulty level 2-3 (intermediate to advanced)

OUTPUT FORMAT (JSON):
{json_schema}

Generate the scenario-based question now."""


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Distractor-mined questions (fact + related distractor facts)
# ═══════════════════════════════════════════════════════════════════════════════

DISTRACTOR_SYSTEM = """\
You are a wine education assessment designer creating questions with carefully \
chosen distractors for OenoBench, an AI benchmark. You are given a target fact \
and a set of related facts to mine for plausible distractors.

Rules:
1. The correct answer comes from the target fact ONLY.
2. Distractors MUST come from the distractor facts provided. Use real details \
from those facts to construct wrong-but-plausible options.
3. This technique creates harder questions because distractors are factually \
true about other entities, just wrong for this specific question.
4. Never reference sources or say "according to...".
5. Output valid JSON only. No text before or after the JSON object.
6. Blend categories (e.g., "Red Blend", "White Blend") are NOT grape varieties. \
Never refer to them as varieties — use "wine style" or "blend category" instead."""

DISTRACTOR_TEMPLATE = (
    "Create a multiple-choice question where distractors are mined from "
    "related facts.\n\n"
    + _PARAPHRASE_RULE_SINGULAR + "\n\n"
    + "AVOID WORLD-KNOWLEDGE SOLVABILITY:\n"
    + _avoid_wk_first_bullet("target fact") + "\n"
) + """\
- DO lead with an OBSERVABLE ATTRIBUTE from the target fact (aging months, \
soil type, yield limit, phenolic threshold, clone name, altitude, varietal \
%, regulatory minimum, blend percentage) and ask the test-taker to infer \
the correct entity.
- If the target fact contains only an iconic entity reference with no \
fact-specific technical/regulatory/attribute detail, output instead: \
{{"skip": true, "reason": "Iconic entity without fact-specific technical depth"}}

TARGET FACT (basis for the correct answer):
{fact_text}

DISTRACTOR FACTS (mine these for plausible wrong options):
{distractor_facts}

CONFUSABILITY NOTE: {confusability_context}

QUESTION DESIGN — INFERENCE OVER RECALL (HARD RULES):
1. Never ask "What is true about [famous entity]?" — pure recall on \
iconic names is world-knowledge-solvable.
2. Lead with fact-specific attributes from the target fact, NOT entity names.
3. The test-taker must *need* the target fact — if general wine knowledge \
alone solves it, rewrite or skip.
4. Each distractor uses a real attribute value from a different but similar \
entity, so partial knowledge finds the distractor plausible.

Create a question where:
- The correct answer is based on the TARGET FACT
- Each wrong option uses a real detail from one of the DISTRACTOR FACTS
- The distractors are true statements about other entities, making them \
especially tricky

QUALITY REQUIREMENTS:
- The question should be answerable only with knowledge of the target fact
- Each distractor should be a true statement about a different but similar entity
- The explanation must clarify why each distractor is wrong for THIS question
- Target difficulty level 3-4 (advanced to expert)

SKIP CONDITIONS — output {{"skip": true, "reason": "..."}} if:
- The distractor facts are about entities obviously different from the target \
(different country, different wine color, clearly unrelated category)
- The distractors would be trivially eliminable by anyone with basic wine knowledge

OUTPUT FORMAT (JSON):
{json_schema}

Generate the distractor-mined question now."""


DISTRACTOR_TEMPLATE_ATTRIBUTE_SWAP = (
    "Create a question where all entities share the same attribute type but "
    "differ in their specific values — the test-taker must know which value "
    "belongs to which entity.\n\n"
    + _PARAPHRASE_RULE_SINGULAR + "\n\n"
    + "AVOID WORLD-KNOWLEDGE SOLVABILITY:\n"
    + _avoid_wk_first_bullet("target fact") + "\n"
) + """\
- DO lead with the specific {dimension} VALUE from the target fact and ask \
the test-taker to identify which entity it matches.
- If the target fact has only an iconic entity with no fact-specific \
{dimension} detail, output instead: \
{{"skip": true, "reason": "Iconic entity without fact-specific {dimension} depth"}}

TARGET FACT (basis for the correct answer):
{fact_text}

DISTRACTOR FACTS (same attribute, different entities):
{distractor_facts}

SHARED CONTEXT: {confusability_context}
ATTRIBUTE DIMENSION: {dimension}

All facts above discuss the {dimension} dimension for similar entities. The \
wrong options should SWAP attribute values between entities — a test-taker \
who confuses these similar entities will pick the wrong one's value.

QUESTION DESIGN — INFERENCE OVER RECALL (HARD RULES):
1. Never ask "What is the {dimension} of [famous entity]?" — pure recall on \
iconic names is world-knowledge-solvable.
2. Lead with the {dimension} value from the target fact, NOT entity names.
3. The test-taker must *need* the target fact's specific {dimension} value \
to answer — general wine knowledge should not suffice.
4. Each wrong option uses a real {dimension} value from a DIFFERENT entity, \
so confusing entities selects the wrong value.

QUALITY REQUIREMENTS:
- The question MUST test knowledge of the {dimension} dimension specifically
- Each distractor must use a real attribute value from a different entity
- The explanation must specify which entity each distractor's value belongs to
- Target difficulty level 3-4 (advanced to expert)

SKIP CONDITIONS — output {{"skip": true, "reason": "..."}} if:
- The attribute values are identical across entities (no distinguishing detail)
- The entities are too dissimilar for the attribute swap to be confusing
- The dimension is trivially obvious (e.g., entirely different categories)

OUTPUT FORMAT (JSON):
{json_schema}

Generate the attribute-swap question now."""


DISTRACTOR_TEMPLATE_ENTITY_ID = (
    "Create an entity identification question: present clues from the "
    "target fact and ask which entity they describe.\n\n"
    + _PARAPHRASE_RULE_SINGULAR + "\n\n"
    + "AVOID WORLD-KNOWLEDGE SOLVABILITY:\n"
    + _avoid_wk_first_bullet("target fact") + "\n"
) + """\
- DO build the clue set from OBSERVABLE ATTRIBUTES in the target fact \
(aging months, soil type, yield limit, phenolic threshold, clone name, \
altitude, varietal %, regulatory minimum, blend percentage).
- If the target fact has only an iconic entity reference with no \
fact-specific technical detail to seed clues, output instead: \
{{"skip": true, "reason": "Iconic entity without fact-specific technical depth"}}

TARGET FACT (basis for the correct answer):
{fact_text}

DISTRACTOR FACTS (similar entities, different characteristics):
{distractor_facts}

SHARED CONTEXT: {confusability_context}

The distractors are about entities similar to the target but with different \
distinguishing details. The test-taker must identify the correct entity \
from multiple clues.

QUESTION DESIGN — INFERENCE OVER RECALL (HARD RULES):
1. Never name the target entity in the stem — the test-taker must derive \
it from the clues.
2. Lead with fact-specific attribute clues from the target fact, NOT \
entity-recall prompts.
3. The test-taker must *need* the target fact's attributes — if world \
knowledge alone picks the correct entity, rewrite or skip.
4. Wrong options are real, similar entities that match SOME but not ALL \
clues, so partial knowledge finds them plausible.

QUALITY REQUIREMENTS:
- The clues must be specific enough for an unambiguous correct answer
- Each distractor entity must be a real entity that shares some overlap \
with the target but differs on the key distinguishing detail
- The explanation must identify which clue(s) distinguish the correct \
entity from each distractor
- Target difficulty level 3-4 (advanced to expert)

SKIP CONDITIONS — output {{"skip": true, "reason": "..."}} if:
- The target fact doesn't contain enough distinguishing detail for clues
- The distractor entities are too dissimilar to create genuine confusion
- The only possible question would test trivial metadata, not wine knowledge

OUTPUT FORMAT (JSON):
{json_schema}

Generate the entity identification question now."""


DISTRACTOR_TEMPLATE_NUMERIC = (
    "Create a question involving numeric values where distractors use real "
    "numbers from similar entities.\n\n"
    + _PARAPHRASE_RULE_SINGULAR + "\n\n"
    + "AVOID WORLD-KNOWLEDGE SOLVABILITY:\n"
    + _avoid_wk_first_bullet("target fact") + "\n"
) + """\
- DO lead with the fact-specific NUMERIC VALUE from the target fact and ask \
the test-taker to infer the matching entity.
- If the target fact has only an iconic entity with no fact-specific \
numeric detail, output instead: \
{{"skip": true, "reason": "Iconic entity without fact-specific numeric depth"}}

TARGET FACT (basis for the correct answer):
{fact_text}

DISTRACTOR FACTS (similar entities with comparable numeric values):
{distractor_facts}

SHARED CONTEXT: {confusability_context}
NUMERIC DIMENSION: {dimension}

All facts discuss measurable {dimension} values for similar entities. The \
wrong options use REAL numeric values from the distractor entities.

QUESTION DESIGN — INFERENCE OVER RECALL (HARD RULES):
1. Never ask "How many X does [famous entity] have?" — pure recall on iconic \
names is world-knowledge-solvable.
2. Lead with the specific numeric value from the target fact, NOT entity \
names.
3. The test-taker must *need* the target fact's specific value — if a \
wine-reading generalist knows the value, rewrite or skip.
4. Wrong options must use the ACTUAL numeric values from the distractor \
entities, so confusing entities selects a real-but-wrong value.

QUALITY REQUIREMENTS:
- The numeric values must be genuinely comparable (same units, same type)
- Include specific numeric values in the options where relevant
- The explanation must cite the actual numeric values for all entities
- Target difficulty level 3-4 (advanced to expert)

SKIP CONDITIONS — output {{"skip": true, "reason": "..."}} if:
- The numeric values aren't truly comparable (different units or metrics)
- One value is so different it's trivially obvious (100x larger)
- Only the target has a numeric value (no numeric distractors possible)

OUTPUT FORMAT (JSON):
{json_schema}

Generate the numeric distractor question now."""


# ═══════════════════════════════════════════════════════════════════════════════
# Template rendering
# ═══════════════════════════════════════════════════════════════════════════════

def build_prompt(template: str, **kwargs) -> str:
    """Fill a prompt template with parameters.

    Automatically injects shared constants (json_schema, json_schema_note)
    if they appear in the template and are not provided in kwargs.

    Returns:
        Rendered prompt string with all placeholders filled.
    """
    # Inject shared schema strings if template uses them and caller didn't provide
    if "{json_schema}" in template and "json_schema" not in kwargs:
        kwargs["json_schema"] = _JSON_SCHEMA
    if "{json_schema_note}" in template and "json_schema_note" not in kwargs:
        kwargs["json_schema_note"] = _JSON_SCHEMA_NOTE

    return template.format(**kwargs)


def prompt_hash(rendered_prompt: str) -> str:
    """Return SHA-256 hash (first 16 hex chars) of rendered prompt.

    Used for reproducibility tracking -- each unique prompt gets a
    deterministic fingerprint that can be stored alongside generated questions.
    """
    return hashlib.sha256(rendered_prompt.encode("utf-8")).hexdigest()[:16]
