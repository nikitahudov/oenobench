"""
OenoBench — Template-based question generator (Strategy 2).

Generates deterministic questions by filling parameterized templates with
entity data from the fact DB. No LLM calls — purely template-driven.
Targets 25% of all questions (~2,500).

Usage:
    python -m src.generators.template_generator --all
    python -m src.generators.template_generator --domain wine_regions --count 50
    python -m src.generators.template_generator --dry-run --count 5
    python -m src.generators.template_generator --list
    python -m src.generators.template_generator --validate
    python -m src.generators.template_generator --test-run
"""

import random

import click
from loguru import logger

from src.generators._fact_sampler import DOMAIN_TARGETS, sample_facts
from src.generators._id_generator import mint_question_id
from src.generators._question_db import (
    delete_questions_by_ids,
    get_question_count,
    get_used_fact_ids,
    insert_question,
)

# ─── Template registry ──────────────────────────────────────────────────────

TEMPLATES: list[dict] = [
    # ── wine_regions (~15 templates) ─────────────────────────────────────────
    {
        "id": "T-REG-COUNTRY-01",
        "pattern": "Which country is the {region} wine region located in?",
        "domain": "wine_regions",
        "difficulty_range": ["1"],
        "cognitive_dim": "recall",
        "question_type": "multiple_choice",
        "correct_field": "country",
        "distractor_strategy": "same_type",
        "required_entities": ["country", "region"],
        "explanation_template": "The {region} wine region is located in {country}.",
    },
    {
        "id": "T-REG-GRAPE-01",
        "pattern": "Which grape variety is the primary grape used in {appellation} wines?",
        "domain": "wine_regions",
        "difficulty_range": ["1", "2"],
        "cognitive_dim": "recall",
        "question_type": "multiple_choice",
        "correct_field": "grape",
        "distractor_strategy": "same_type",
        "required_entities": ["grape"],
        "explanation_template": "{appellation} wines are primarily made from {grape}.",
    },
    {
        "id": "T-REG-CLASS-01",
        "pattern": "What is the classification level of {appellation}?",
        "domain": "wine_regions",
        "difficulty_range": ["2"],
        "cognitive_dim": "recall",
        "question_type": "multiple_choice",
        "correct_field": "classification",
        "distractor_strategy": "same_type",
        "required_entities": ["classification"],
        "explanation_template": "{appellation} holds the {classification} classification.",
    },
    {
        "id": "T-REG-SUBREGION-01",
        "pattern": "In which sub-region or parent region is {appellation} located?",
        "domain": "wine_regions",
        "difficulty_range": ["2", "3"],
        "cognitive_dim": "recall",
        "question_type": "multiple_choice",
        "correct_field": "region",
        "distractor_strategy": "same_type",
        "required_entities": ["region"],
        "explanation_template": "{appellation} is located in the {region} region.",
    },
    {
        "id": "T-REG-TF-COUNTRY-01",
        "pattern": "True or False: {region} is a wine region in {country}.",
        "domain": "wine_regions",
        "difficulty_range": ["1"],
        "cognitive_dim": "recall",
        "question_type": "true_false",
        "correct_field": "country",
        "distractor_strategy": "true_false",
        "required_entities": ["country", "region"],
        "explanation_template": "{region} is indeed located in {country}.",
    },
    {
        "id": "T-REG-SOIL-01",
        "pattern": "What is a characteristic soil type found in {region}?",
        "domain": "wine_regions",
        "difficulty_range": ["2", "3"],
        "cognitive_dim": "recall",
        "question_type": "multiple_choice",
        "correct_field": "soil",
        "distractor_strategy": "same_type",
        "required_entities": ["soil"],
        "explanation_template": "{region} is known for its {soil} soil.",
    },
    {
        "id": "T-REG-CLIMATE-01",
        "pattern": "What type of climate characterizes the {region} wine region?",
        "domain": "wine_regions",
        "difficulty_range": ["2"],
        "cognitive_dim": "comprehension",
        "question_type": "multiple_choice",
        "correct_field": "climate",
        "distractor_strategy": "same_type",
        "required_entities": ["climate"],
        "explanation_template": "The {region} wine region has a {climate} climate.",
    },
    {
        "id": "T-REG-AREA-01",
        "pattern": "Approximately how large is the {appellation} vineyard area?",
        "domain": "wine_regions",
        "difficulty_range": ["3"],
        "cognitive_dim": "recall",
        "question_type": "multiple_choice",
        "correct_field": "area",
        "distractor_strategy": "same_type",
        "required_entities": ["area"],
        "explanation_template": "The {appellation} appellation covers approximately {area}.",
    },
    {
        "id": "T-REG-STYLE-01",
        "pattern": "What style of wine is {appellation} primarily known for?",
        "domain": "wine_regions",
        "difficulty_range": ["1", "2"],
        "cognitive_dim": "recall",
        "question_type": "multiple_choice",
        "correct_field": "wine_style",
        "distractor_strategy": "same_type",
        "required_entities": ["wine_style"],
        "explanation_template": "{appellation} is primarily known for producing {wine_style} wines.",
    },
    {
        "id": "T-REG-TF-GRAPE-01",
        "pattern": "True or False: {grape} is an authorized grape variety in {appellation}.",
        "domain": "wine_regions",
        "difficulty_range": ["2"],
        "cognitive_dim": "recall",
        "question_type": "true_false",
        "correct_field": "grape",
        "distractor_strategy": "true_false",
        "required_entities": ["grape"],
        "explanation_template": "{grape} is an authorized variety in {appellation}.",
    },
    {
        "id": "T-REG-NEIGHBOR-01",
        "pattern": "Which of the following wine regions borders or is near {region}?",
        "domain": "wine_regions",
        "difficulty_range": ["3"],
        "cognitive_dim": "comprehension",
        "question_type": "multiple_choice",
        "correct_field": "neighbor_region",
        "distractor_strategy": "same_type",
        "required_entities": ["neighbor_region"],
        "explanation_template": "{neighbor_region} is a neighboring wine region to {region}.",
    },
    {
        "id": "T-REG-ALTITUDE-01",
        "pattern": "At what approximate altitude are vineyards in {region} typically planted?",
        "domain": "wine_regions",
        "difficulty_range": ["3", "4"],
        "cognitive_dim": "recall",
        "question_type": "multiple_choice",
        "correct_field": "altitude",
        "distractor_strategy": "same_type",
        "required_entities": ["altitude"],
        "explanation_template": "Vineyards in {region} are typically found at approximately {altitude}.",
    },
    {
        "id": "T-REG-YEAR-01",
        "pattern": "In what year was the {appellation} appellation officially established?",
        "domain": "wine_regions",
        "difficulty_range": ["3", "4"],
        "cognitive_dim": "recall",
        "question_type": "multiple_choice",
        "correct_field": "year",
        "distractor_strategy": "same_type",
        "required_entities": ["year"],
        "explanation_template": "The {appellation} appellation was officially established in {year}.",
    },
    {
        "id": "T-REG-COLOR-01",
        "pattern": "What color(s) of wine is {appellation} authorized to produce?",
        "domain": "wine_regions",
        "difficulty_range": ["1", "2"],
        "cognitive_dim": "recall",
        "question_type": "multiple_choice",
        "correct_field": "color",
        "distractor_strategy": "same_type",
        "required_entities": ["color"],
        "explanation_template": "{appellation} is authorized to produce {color} wines.",
    },
    {
        "id": "T-REG-RIVER-01",
        "pattern": "Which river or body of water influences the climate of {region}?",
        "domain": "wine_regions",
        "difficulty_range": ["2", "3"],
        "cognitive_dim": "comprehension",
        "question_type": "multiple_choice",
        "correct_field": "river",
        "distractor_strategy": "same_type",
        "required_entities": ["river"],
        "explanation_template": "The {river} influences the climate of {region}.",
    },
    # ── grape_varieties (~8 templates) ───────────────────────────────────────
    {
        "id": "T-GRP-REGION-01",
        "pattern": "Which wine region is best known for growing {grape}?",
        "domain": "grape_varieties",
        "difficulty_range": ["1", "2"],
        "cognitive_dim": "recall",
        "question_type": "multiple_choice",
        "correct_field": "region",
        "distractor_strategy": "same_type",
        "required_entities": ["region"],
        "explanation_template": "{grape} is a signature grape of the {region} wine region.",
    },
    {
        "id": "T-GRP-COLOR-01",
        "pattern": "What color wine does the {grape} grape primarily produce?",
        "domain": "grape_varieties",
        "difficulty_range": ["1"],
        "cognitive_dim": "recall",
        "question_type": "multiple_choice",
        "correct_field": "color",
        "distractor_strategy": "same_type",
        "required_entities": ["color"],
        "explanation_template": "{grape} is a {color} grape variety.",
    },
    {
        "id": "T-GRP-TF-COLOR-01",
        "pattern": "True or False: {grape} is a {color} grape variety.",
        "domain": "grape_varieties",
        "difficulty_range": ["1"],
        "cognitive_dim": "recall",
        "question_type": "true_false",
        "correct_field": "color",
        "distractor_strategy": "true_false",
        "required_entities": ["color"],
        "explanation_template": "{grape} is indeed a {color} grape variety.",
    },
    {
        "id": "T-GRP-SYNONYM-01",
        "pattern": "What is another name (synonym) for the {grape} grape?",
        "domain": "grape_varieties",
        "difficulty_range": ["2", "3"],
        "cognitive_dim": "recall",
        "question_type": "multiple_choice",
        "correct_field": "synonym",
        "distractor_strategy": "same_type",
        "required_entities": ["synonym"],
        "explanation_template": "{grape} is also known as {synonym}.",
    },
    {
        "id": "T-GRP-ORIGIN-01",
        "pattern": "Which country is considered the origin of the {grape} grape?",
        "domain": "grape_varieties",
        "difficulty_range": ["2"],
        "cognitive_dim": "recall",
        "question_type": "multiple_choice",
        "correct_field": "country",
        "distractor_strategy": "same_type",
        "required_entities": ["country"],
        "explanation_template": "{grape} originated in {country}.",
    },
    {
        "id": "T-GRP-PARENT-01",
        "pattern": "Which grape is a parent variety of {grape}?",
        "domain": "grape_varieties",
        "difficulty_range": ["3", "4"],
        "cognitive_dim": "recall",
        "question_type": "multiple_choice",
        "correct_field": "parent_grape",
        "distractor_strategy": "same_type",
        "required_entities": ["parent_grape"],
        "explanation_template": "{parent_grape} is a parent variety of {grape}.",
    },
    {
        "id": "T-GRP-AROMA-01",
        "pattern": "Which of the following is a characteristic aroma of wines made from {grape}?",
        "domain": "grape_varieties",
        "difficulty_range": ["2", "3"],
        "cognitive_dim": "recall",
        "question_type": "multiple_choice",
        "correct_field": "aroma",
        "distractor_strategy": "same_type",
        "required_entities": ["aroma"],
        "explanation_template": "Wines made from {grape} are characteristically associated with {aroma} aromas.",
    },
    {
        "id": "T-GRP-ACREAGE-01",
        "pattern": "Approximately how many hectares of {grape} are planted worldwide?",
        "domain": "grape_varieties",
        "difficulty_range": ["3", "4"],
        "cognitive_dim": "recall",
        "question_type": "multiple_choice",
        "correct_field": "acreage",
        "distractor_strategy": "same_type",
        "required_entities": ["acreage"],
        "explanation_template": "There are approximately {acreage} of {grape} planted worldwide.",
    },
    # ── producers (~6 templates) ─────────────────────────────────────────────
    {
        "id": "T-PRD-REGION-01",
        "pattern": "In which wine region is {producer} located?",
        "domain": "producers",
        "difficulty_range": ["1", "2"],
        "cognitive_dim": "recall",
        "question_type": "multiple_choice",
        "correct_field": "region",
        "distractor_strategy": "same_type",
        "required_entities": ["region"],
        "explanation_template": "{producer} is located in the {region} wine region.",
    },
    {
        "id": "T-PRD-APPELLATION-01",
        "pattern": "Which appellation does the wine estate {producer} belong to?",
        "domain": "producers",
        "difficulty_range": ["2", "3"],
        "cognitive_dim": "recall",
        "question_type": "multiple_choice",
        "correct_field": "appellation",
        "distractor_strategy": "same_type",
        "required_entities": ["appellation"],
        "explanation_template": "{producer} belongs to the {appellation} appellation.",
    },
    {
        "id": "T-PRD-GRAPE-01",
        "pattern": "Which grape variety is {producer} most associated with?",
        "domain": "producers",
        "difficulty_range": ["2", "3"],
        "cognitive_dim": "recall",
        "question_type": "multiple_choice",
        "correct_field": "grape",
        "distractor_strategy": "same_type",
        "required_entities": ["grape"],
        "explanation_template": "{producer} is most closely associated with the {grape} grape.",
    },
    {
        "id": "T-PRD-COUNTRY-01",
        "pattern": "In which country is {producer} based?",
        "domain": "producers",
        "difficulty_range": ["1"],
        "cognitive_dim": "recall",
        "question_type": "multiple_choice",
        "correct_field": "country",
        "distractor_strategy": "same_type",
        "required_entities": ["country"],
        "explanation_template": "{producer} is based in {country}.",
    },
    {
        "id": "T-PRD-CLASS-01",
        "pattern": "What classification does {producer} hold?",
        "domain": "producers",
        "difficulty_range": ["3", "4"],
        "cognitive_dim": "recall",
        "question_type": "multiple_choice",
        "correct_field": "classification",
        "distractor_strategy": "same_type",
        "required_entities": ["classification"],
        "explanation_template": "{producer} holds the {classification} classification.",
    },
    {
        "id": "T-PRD-TF-REGION-01",
        "pattern": "True or False: {producer} is located in the {region} wine region.",
        "domain": "producers",
        "difficulty_range": ["1", "2"],
        "cognitive_dim": "recall",
        "question_type": "true_false",
        "correct_field": "region",
        "distractor_strategy": "true_false",
        "required_entities": ["region"],
        "explanation_template": "{producer} is indeed located in {region}.",
    },
    # ── winemaking (~6 templates) ────────────────────────────────────────────
    {
        "id": "T-WMK-TECHNIQUE-01",
        "pattern": "Which winemaking technique is typically used in the production of {wine_style}?",
        "domain": "winemaking",
        "difficulty_range": ["2", "3"],
        "cognitive_dim": "comprehension",
        "question_type": "multiple_choice",
        "correct_field": "technique",
        "distractor_strategy": "same_type",
        "required_entities": ["technique"],
        "explanation_template": "The production of {wine_style} typically involves {technique}.",
    },
    {
        "id": "T-WMK-TEMP-01",
        "pattern": "At what temperature range is {process} typically conducted?",
        "domain": "winemaking",
        "difficulty_range": ["2", "3"],
        "cognitive_dim": "recall",
        "question_type": "multiple_choice",
        "correct_field": "temperature",
        "distractor_strategy": "same_type",
        "required_entities": ["temperature"],
        "explanation_template": "{process} is typically conducted at {temperature}.",
    },
    {
        "id": "T-WMK-VESSEL-01",
        "pattern": "Which type of vessel is traditionally used for {process}?",
        "domain": "winemaking",
        "difficulty_range": ["2"],
        "cognitive_dim": "recall",
        "question_type": "multiple_choice",
        "correct_field": "vessel",
        "distractor_strategy": "same_type",
        "required_entities": ["vessel"],
        "explanation_template": "{process} is traditionally carried out in {vessel}.",
    },
    {
        "id": "T-WMK-DURATION-01",
        "pattern": "How long does {process} typically last?",
        "domain": "winemaking",
        "difficulty_range": ["2", "3"],
        "cognitive_dim": "recall",
        "question_type": "multiple_choice",
        "correct_field": "duration",
        "distractor_strategy": "same_type",
        "required_entities": ["duration"],
        "explanation_template": "{process} typically lasts {duration}.",
    },
    {
        "id": "T-WMK-TF-01",
        "pattern": "True or False: {technique} is a step in making {wine_style}.",
        "domain": "winemaking",
        "difficulty_range": ["1", "2"],
        "cognitive_dim": "recall",
        "question_type": "true_false",
        "correct_field": "technique",
        "distractor_strategy": "true_false",
        "required_entities": ["technique"],
        "explanation_template": "{technique} is indeed used in the production of {wine_style}.",
    },
    {
        "id": "T-WMK-RESULT-01",
        "pattern": "What is the primary purpose of {technique} in winemaking?",
        "domain": "winemaking",
        "difficulty_range": ["2", "3"],
        "cognitive_dim": "comprehension",
        "question_type": "multiple_choice",
        "correct_field": "purpose",
        "distractor_strategy": "same_type",
        "required_entities": ["purpose"],
        "explanation_template": "The primary purpose of {technique} is {purpose}.",
    },
    # ── viticulture (~5 templates) ───────────────────────────────────────────
    {
        "id": "T-VIT-CLIMATE-01",
        "pattern": "What type of climate is most suitable for growing {grape}?",
        "domain": "viticulture",
        "difficulty_range": ["2"],
        "cognitive_dim": "comprehension",
        "question_type": "multiple_choice",
        "correct_field": "climate",
        "distractor_strategy": "same_type",
        "required_entities": ["climate"],
        "explanation_template": "{grape} thrives best in a {climate} climate.",
    },
    {
        "id": "T-VIT-PEST-01",
        "pattern": "Which pest or disease commonly affects {grape} vineyards?",
        "domain": "viticulture",
        "difficulty_range": ["2", "3"],
        "cognitive_dim": "recall",
        "question_type": "multiple_choice",
        "correct_field": "pest",
        "distractor_strategy": "same_type",
        "required_entities": ["pest"],
        "explanation_template": "{pest} is a common threat to {grape} vineyards.",
    },
    {
        "id": "T-VIT-TRAINING-01",
        "pattern": "Which vine training system is commonly used in {region}?",
        "domain": "viticulture",
        "difficulty_range": ["2", "3"],
        "cognitive_dim": "recall",
        "question_type": "multiple_choice",
        "correct_field": "training_system",
        "distractor_strategy": "same_type",
        "required_entities": ["training_system"],
        "explanation_template": "The {training_system} training system is commonly used in {region}.",
    },
    {
        "id": "T-VIT-ROOTSTOCK-01",
        "pattern": "Which rootstock is commonly used for {grape} in {region}?",
        "domain": "viticulture",
        "difficulty_range": ["3", "4"],
        "cognitive_dim": "recall",
        "question_type": "multiple_choice",
        "correct_field": "rootstock",
        "distractor_strategy": "same_type",
        "required_entities": ["rootstock"],
        "explanation_template": "{rootstock} is a common rootstock choice for {grape} in {region}.",
    },
    {
        "id": "T-VIT-TF-PEST-01",
        "pattern": "True or False: {pest} is a significant viticultural threat in {region}.",
        "domain": "viticulture",
        "difficulty_range": ["2"],
        "cognitive_dim": "recall",
        "question_type": "true_false",
        "correct_field": "pest",
        "distractor_strategy": "true_false",
        "required_entities": ["pest"],
        "explanation_template": "{pest} is indeed a significant threat in {region}.",
    },
    # ── wine_business (~5 templates) ─────────────────────────────────────────
    {
        "id": "T-BIZ-CLASSIF-01",
        "pattern": "Which classification system is used in {region}?",
        "domain": "wine_business",
        "difficulty_range": ["2"],
        "cognitive_dim": "recall",
        "question_type": "multiple_choice",
        "correct_field": "classification",
        "distractor_strategy": "same_type",
        "required_entities": ["classification"],
        "explanation_template": "The {classification} system is used in {region}.",
    },
    {
        "id": "T-BIZ-REGULATION-01",
        "pattern": "Which regulatory body governs wine production in {region}?",
        "domain": "wine_business",
        "difficulty_range": ["2", "3"],
        "cognitive_dim": "recall",
        "question_type": "multiple_choice",
        "correct_field": "regulatory_body",
        "distractor_strategy": "same_type",
        "required_entities": ["regulatory_body"],
        "explanation_template": "Wine production in {region} is governed by {regulatory_body}.",
    },
    {
        "id": "T-BIZ-LABEL-01",
        "pattern": "What label term indicates {wine_designation} in {country}?",
        "domain": "wine_business",
        "difficulty_range": ["2", "3"],
        "cognitive_dim": "recall",
        "question_type": "multiple_choice",
        "correct_field": "label_term",
        "distractor_strategy": "same_type",
        "required_entities": ["label_term"],
        "explanation_template": "In {country}, the term {label_term} indicates {wine_designation}.",
    },
    {
        "id": "T-BIZ-TF-REG-01",
        "pattern": "True or False: {regulatory_body} is responsible for wine regulation in {country}.",
        "domain": "wine_business",
        "difficulty_range": ["2"],
        "cognitive_dim": "recall",
        "question_type": "true_false",
        "correct_field": "regulatory_body",
        "distractor_strategy": "true_false",
        "required_entities": ["regulatory_body"],
        "explanation_template": "{regulatory_body} is indeed the regulatory authority in {country}.",
    },
    {
        "id": "T-BIZ-EXPORT-01",
        "pattern": "Which country is the largest export market for wines from {region}?",
        "domain": "wine_business",
        "difficulty_range": ["3", "4"],
        "cognitive_dim": "recall",
        "question_type": "multiple_choice",
        "correct_field": "market",
        "distractor_strategy": "same_type",
        "required_entities": ["market"],
        "explanation_template": "{market} is the largest export market for {region} wines.",
    },
]

DOMAINS = list(DOMAIN_TARGETS.keys())
OPTION_IDS = ["A", "B", "C", "D"]


# ─── Entity extraction helpers ───────────────────────────────────────────────

def _extract_entities(fact: dict) -> dict[str, str]:
    """Build {entity_type: entity_name} map from a fact's entities JSONB."""
    entities = fact.get("entities") or []
    if isinstance(entities, str):
        import orjson
        entities = orjson.loads(entities)
    out: dict[str, str] = {}
    for ent in entities:
        etype = ent.get("type", "")
        ename = ent.get("name", "")
        if etype and ename:
            out[etype] = ename
    return out


def _extract_slot_names(pattern: str) -> list[str]:
    """Extract {placeholder} names from a template pattern."""
    import re
    return re.findall(r"\{(\w+)\}", pattern)


# ─── Core generation functions ───────────────────────────────────────────────

def find_matching_facts(template: dict, facts: list[dict]) -> list[dict]:
    """Filter facts that have the required entity types for this template."""
    required = set(template["required_entities"])
    matched = []
    for fact in facts:
        ents = _extract_entities(fact)
        if required.issubset(ents.keys()):
            matched.append(fact)
    return matched


def source_distractors(
    correct_value: str,
    entity_type: str,
    facts: list[dict],
    count: int = 3,
) -> list[str]:
    """Find plausible wrong answers from other facts' entities of same type."""
    candidates: set[str] = set()
    correct_lower = correct_value.lower()
    for fact in facts:
        ents = _extract_entities(fact)
        val = ents.get(entity_type, "")
        if val and val.lower() != correct_lower and val not in candidates:
            candidates.add(val)
    result = list(candidates)
    random.shuffle(result)
    return result[:count]


def fill_template(
    template: dict,
    fact: dict,
    all_facts: list[dict],
) -> dict | None:
    """Fill a template with fact data to produce a question dict.

    Returns a dict ready for insert_question(), or None if the fact
    doesn't have the required entities or not enough distractors.
    """
    ents = _extract_entities(fact)
    required = set(template["required_entities"])
    if not required.issubset(ents.keys()):
        return None

    correct_field = template["correct_field"]
    correct_value = ents.get(correct_field)
    if not correct_value:
        return None

    # Build slot values: entities + subdomain/fact-level fields
    slots = dict(ents)
    if fact.get("subdomain"):
        slots.setdefault("subdomain", fact["subdomain"])

    # Fill pattern and explanation
    try:
        question_text = template["pattern"].format(**slots)
        explanation = template["explanation_template"].format(**slots)
    except KeyError:
        return None

    question_type = template["question_type"]
    difficulty = random.choice(template["difficulty_range"])

    if question_type == "true_false":
        options = [{"id": "A", "text": "True"}, {"id": "B", "text": "False"}]
        correct_answer = "A"
        correct_answer_text = "True"
    elif question_type == "multiple_choice":
        distractors = source_distractors(correct_value, correct_field, all_facts, count=3)
        if len(distractors) < 3:
            return None

        choices = [correct_value] + distractors[:3]
        random.shuffle(choices)
        correct_idx = choices.index(correct_value)
        options = [
            {"id": OPTION_IDS[i], "text": choices[i]}
            for i in range(4)
        ]
        correct_answer = OPTION_IDS[correct_idx]
        correct_answer_text = correct_value
    else:
        return None

    return {
        "question_text": question_text,
        "question_type": question_type,
        "difficulty": difficulty,
        "cognitive_dim": template["cognitive_dim"],
        "domain": template["domain"],
        "subdomain": fact.get("subdomain"),
        "options": options,
        "correct_answer": correct_answer,
        "correct_answer_text": correct_answer_text,
        "explanation": explanation,
        "tags": [f"template:{template['id']}"],
        # Provenance
        "_template_id": template["id"],
        "_fact_id": str(fact["id"]),
        "_source_id": str(fact["source_id"]),
    }


# ─── CLI ─────────────────────────────────────────────────────────────────────

@click.command()
@click.option("--domain", type=click.Choice(DOMAINS), help="Generate for one domain only")
@click.option("--count", type=int, default=10, help="Questions to generate per domain")
@click.option("--difficulty", type=click.Choice(["1", "2", "3", "4"]), help="Filter templates by difficulty")
@click.option("--dry-run", is_flag=True, help="Preview without DB writes")
@click.option("--test-run", is_flag=True, help="Small test run (5 questions)")
@click.option("--validate", is_flag=True, help="Quality report on generated questions")
@click.option("--list", "list_templates", is_flag=True, help="List available templates")
@click.option("--all", "run_all", is_flag=True, help="Generate for all domains using targets")
def main(domain, count, difficulty, dry_run, test_run, validate, list_templates, run_all):
    """Template-based question generator (Strategy 2)."""
    if list_templates:
        _do_list(difficulty)
        return

    if validate:
        _do_validate()
        return

    if test_run:
        count = 5
        dry_run = True

    domains = [domain] if domain else DOMAINS
    if run_all:
        domains = DOMAINS

    used_facts = get_used_fact_ids() if not dry_run else set()
    total_generated = 0
    generated_ids: list[str] = []

    for dom in domains:
        target = count if not run_all else DOMAIN_TARGETS.get(dom, 100) // 4
        templates_for_domain = [
            t for t in TEMPLATES if t["domain"] == dom
            and (not difficulty or difficulty in t["difficulty_range"])
        ]
        if not templates_for_domain:
            logger.warning(f"No templates for domain={dom}")
            continue

        facts = sample_facts(dom, count=target * 10, exclude_ids=used_facts)
        if not facts:
            logger.warning(f"No facts available for domain={dom}")
            continue

        generated = 0
        for template in templates_for_domain:
            if generated >= target:
                break
            matching = find_matching_facts(template, facts)
            random.shuffle(matching)
            for fact in matching:
                if generated >= target:
                    break
                result = fill_template(template, fact, facts)
                if result is None:
                    continue

                if dry_run:
                    click.echo(
                        f"[DRY-RUN] {result['_template_id']} | "
                        f"{result['question_type']} L{result['difficulty']} | "
                        f"{result['question_text'][:80]}"
                    )
                    generated += 1
                    continue

                qid = mint_question_id(dom, result["difficulty"])
                question_data = {
                    "question_id": qid,
                    "domain": result["domain"],
                    "subdomain": result["subdomain"],
                    "question_type": result["question_type"],
                    "difficulty": result["difficulty"],
                    "cognitive_dim": result["cognitive_dim"],
                    "question_text": result["question_text"],
                    "options": result["options"],
                    "correct_answer": result["correct_answer"],
                    "correct_answer_text": result["correct_answer_text"],
                    "explanation": result["explanation"],
                    "tags": result["tags"],
                }
                generation_meta = {
                    "generator": "template_only",
                    "generator_version": None,
                    "generation_method": "template",
                    "template_id": result["_template_id"],
                    "llm_creativity": "none",
                    "prompt_hash": None,
                    "raw_response": None,
                }
                q_uuid = insert_question(
                    question_data,
                    generation_meta,
                    fact_ids=[result["_fact_id"]],
                    source_ids=[result["_source_id"]],
                )
                if q_uuid:
                    generated += 1
                    generated_ids.append(q_uuid)
                    used_facts.add(result["_fact_id"])

        total_generated += generated
        logger.info(f"Domain {dom}: generated {generated}/{target} questions")

    click.echo(f"\nTotal generated: {total_generated}")
    if test_run and generated_ids:
        click.echo(f"Test run — cleaning up {len(generated_ids)} questions")
        delete_questions_by_ids(generated_ids)


def _do_list(difficulty_filter: str | None):
    """Print all templates."""
    click.echo(f"{'ID':<22} {'Domain':<18} {'Type':<18} {'Difficulty':<12} Pattern")
    click.echo("-" * 110)
    for t in TEMPLATES:
        if difficulty_filter and difficulty_filter not in t["difficulty_range"]:
            continue
        diff = ",".join(t["difficulty_range"])
        click.echo(
            f"{t['id']:<22} {t['domain']:<18} {t['question_type']:<18} "
            f"L{diff:<11} {t['pattern'][:50]}"
        )
    click.echo(f"\nTotal templates: {len(TEMPLATES)}")
    by_domain: dict[str, int] = {}
    for t in TEMPLATES:
        by_domain[t["domain"]] = by_domain.get(t["domain"], 0) + 1
    for dom, cnt in sorted(by_domain.items()):
        click.echo(f"  {dom}: {cnt}")


def _do_validate():
    """Quality report on template generation capability."""
    click.echo("Template Generator Validation Report")
    click.echo("=" * 60)

    # Template distribution
    by_domain: dict[str, list[dict]] = {}
    for t in TEMPLATES:
        by_domain.setdefault(t["domain"], []).append(t)

    click.echo(f"\nTemplates per domain:")
    for dom in DOMAINS:
        tmpls = by_domain.get(dom, [])
        click.echo(f"  {dom}: {len(tmpls)}")

    # Check fact matching per template
    click.echo(f"\nFact matching analysis:")
    zero_match_templates = []
    low_distractor_count = 0

    for dom in DOMAINS:
        facts = sample_facts(dom, count=500)
        if not facts:
            click.echo(f"  {dom}: no facts in DB")
            continue

        for template in by_domain.get(dom, []):
            matching = find_matching_facts(template, facts)
            if not matching:
                zero_match_templates.append(template["id"])
                click.echo(f"  {template['id']}: 0 matching facts")
                continue

            # Check distractor quality on a sample
            ok, bad = 0, 0
            for fact in matching[:10]:
                result = fill_template(template, fact, facts)
                if result:
                    ok += 1
                else:
                    bad += 1
            if bad > ok:
                low_distractor_count += 1
            click.echo(
                f"  {template['id']}: {len(matching)} matching facts, "
                f"{ok}/{ok + bad} fillable (sample of {ok + bad})"
            )

    # Existing question counts
    click.echo(f"\nExisting template questions in DB:")
    total = get_question_count(generator="template_only", method="template", status=None)
    click.echo(f"  Total: {total}")
    for dom in DOMAINS:
        cnt = get_question_count(domain=dom, generator="template_only", method="template", status=None)
        if cnt > 0:
            click.echo(f"  {dom}: {cnt}")

    # Summary
    click.echo(f"\nSummary:")
    click.echo(f"  Total templates: {len(TEMPLATES)}")
    click.echo(f"  Templates with zero matching facts: {len(zero_match_templates)}")
    click.echo(f"  Templates with low distractor quality: {low_distractor_count}")
    if zero_match_templates:
        click.echo(f"  Zero-match IDs: {', '.join(zero_match_templates)}")


if __name__ == "__main__":
    main()
