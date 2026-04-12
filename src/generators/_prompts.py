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
  "tags": ["relevant", "topic", "tags"]
}"""

_JSON_SCHEMA_NOTE = (
    'For short_answer questions, set "options" to null. '
    'For true_false, provide only options A (True) and B (False).'
)


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
5. Output valid JSON only. No text before or after the JSON object."""

FACT_TO_QUESTION_TEMPLATE = """\
Create a {question_type} question from the following fact.

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

QUESTION STYLE:
- Ask directly about the underlying knowledge, not about "what research shows" \
or "what studies indicate". For example, instead of "Which statement about X is \
supported by research?", ask "What effect does X have on Y?"
- The question should test wine knowledge, not reading comprehension of the fact

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
5. Output valid JSON only. No text before or after the JSON object."""

COMPARATIVE_TEMPLATE = """\
Create a comparative question using these facts about different wine entities.

FACTS:
{facts}

COMPARISON TYPE: {comparison_type}

The question should require the test-taker to compare or contrast the entities \
described in the facts above. The correct answer must be derivable from the \
facts alone.

QUALITY REQUIREMENTS:
- Highlight meaningful differences or similarities between the entities
- All options must reference real wine entities or attributes
- The explanation must cite specific facts that support the correct answer
- Question difficulty should be intermediate to advanced (level 2-3)

OUTPUT FORMAT (JSON):
{json_schema}

Generate the comparative question now."""


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
5. Output valid JSON only. No text before or after the JSON object."""

SCENARIO_TEMPLATE = """\
Create a scenario-based question that synthesizes these facts.

FACTS:
{facts}

SCENARIO TYPE: {scenario_type}

Build a realistic wine scenario that requires applying knowledge from multiple \
facts above. The test-taker should need to synthesize information to arrive at \
the correct answer.

SCENARIO TYPE GUIDANCE:
- winemaking: A winemaker facing a decision about technique, timing, or materials
- tasting: A sommelier or taster identifying, describing, or selecting wines
- business: A wine business professional making purchasing, pricing, or market decisions
- service: A restaurant or retail professional advising a customer
- viticulture: A grower deciding on planting, canopy, or harvest decisions

QUALITY REQUIREMENTS:
- The scenario must feel authentic and professionally relevant
- Integrate at least 2 of the provided facts into the reasoning path
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
5. Output valid JSON only. No text before or after the JSON object."""

DISTRACTOR_TEMPLATE = """\
Create a multiple-choice question where distractors are mined from related facts.

TARGET FACT (basis for the correct answer):
{fact_text}

DISTRACTOR FACTS (mine these for plausible wrong options):
{distractor_facts}

Create a question where:
- The correct answer is based on the TARGET FACT
- Each wrong option uses a real detail from one of the DISTRACTOR FACTS
- The distractors are true statements about other entities, making them \
especially tricky

QUALITY REQUIREMENTS:
- The question should be answerable only with knowledge of the target fact
- Each distractor should be a true statement about a different entity
- The explanation must clarify why each distractor is wrong for THIS question
- Target difficulty level 3-4 (advanced to expert)

OUTPUT FORMAT (JSON):
{json_schema}

Generate the distractor-mined question now."""


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
