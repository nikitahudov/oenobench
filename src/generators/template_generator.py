"""
OenoBench — Template-based question generator (Strategy 2, v2 overhaul).

Generates deterministic questions by filling parameterized templates with
entity data from the fact DB. Key v2 fixes (per docs/GENERATION_IMPROVEMENT_PLAN.md §6):

  * γ-1 Embedding-similarity distractors: instead of random same-type entities,
    candidate distractors are ranked by cosine similarity to the correct entity
    (positions 2-5 from the K=8 nearest neighbours), so wrong options are
    plausible alternatives — not trivially eliminable.

  * γ-2 Source-fact-anchored generation: templates are tagged
    ``requires_fact_specific``. Templates that ask about facts beyond the
    entity name (soil, climate, aging, classification, etc.) only fire when
    the fact's entities JSONB contains the relevant non-name field. Identity
    templates ("which country is X in?") are kept but down-weighted via
    ``selection_weight`` so they only fill remaining capacity.

  * γ-3 Per-instance difficulty: difficulty is overridden at generation time
    based on entity mention count in the fact base (≥100 → L1, 20-99 → L2,
    5-19 → L3, <5 → L4). Counts are cached per run.

  * γ-4 Phrasing diversification: every template has 4-6 paraphrase variants
    selected deterministically from a hash of (entity_name, template_id) so
    identical inputs reproduce identical phrasings.

  * γ-5 Optional LLM paraphrase post-pass: ``--paraphrase`` flag wraps each
    output through ``_template_paraphrase.paraphrase_question_text`` (Gemini
    via OpenRouter) for an extra anti-detectability layer.

Usage:
    python -m src.generators.template_generator --all
    python -m src.generators.template_generator --domain wine_regions --count 50
    python -m src.generators.template_generator --dry-run --count 5
    python -m src.generators.template_generator --list
    python -m src.generators.template_generator --validate
    python -m src.generators.template_generator --test-run
    python -m src.generators.template_generator --domain wine_regions --count 5 --test-run --paraphrase
"""

from __future__ import annotations

import hashlib
import os
import random
import re
from functools import lru_cache

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
from src.utils.db import get_pg

# ─── Template registry ──────────────────────────────────────────────────────
#
# Each template entry has:
#   id                       — short stable ID
#   patterns                 — list of 4-6 paraphrase variants (γ-4)
#   domain                   — domain enum value
#   difficulty_range         — fallback difficulty before γ-3 entity-count override
#   cognitive_dim, question_type, correct_field
#   distractor_strategy      — same_type | true_false
#   required_entities        — entity types that must be present in fact JSONB
#   explanation_template     — used as `explanation`
#   requires_fact_specific   — γ-2: True templates only fire when the fact
#                              has the relevant non-name entity (e.g. soil,
#                              climate). False templates are identity lookups
#                              (region→country); they're kept for fallback
#                              with low ``selection_weight``.
#   selection_weight         — γ-2: relative weight for template choice. Higher
#                              wins. Identity templates are weight 0.2; fact-
#                              specific templates are weight 1.0+.

TEMPLATES: list[dict] = [
    # ── wine_regions: identity (down-weighted) ───────────────────────────
    {
        "id": "T-REG-COUNTRY-01",
        "patterns": [
            "Which country is the {region} wine region located in?",
            "In which country is the wine region of {region} found?",
            "Identify the country where the {region} wine region is located.",
            "Name the country in which the {region} wine region lies.",
            "The country of the {region} wine region is which of the following?",
            "What country is home to the {region} wine region?",
        ],
        "domain": "wine_regions",
        "difficulty_range": ["1"],
        "cognitive_dim": "recall",
        "question_type": "multiple_choice",
        "correct_field": "country",
        "distractor_strategy": "same_type",
        "required_entities": ["country", "region"],
        "explanation_template": "The {region} wine region is located in {country}.",
        "requires_fact_specific": False,
        "selection_weight": 0.2,
    },
    {
        "id": "T-REG-GRAPE-01",
        "patterns": [
            "Which grape variety is the primary grape used in {appellation} wines?",
            "What is the principal grape variety of {appellation}?",
            "Identify the dominant grape used in the production of {appellation}.",
            "Name the main grape variety associated with {appellation}.",
            "The primary grape behind {appellation} wines is which of the following?",
            "Which variety dominates {appellation} wine production?",
        ],
        "domain": "wine_regions",
        "difficulty_range": ["1", "2"],
        "cognitive_dim": "recall",
        "question_type": "multiple_choice",
        "correct_field": "grape",
        "distractor_strategy": "same_type",
        "required_entities": ["grape", "appellation"],
        "explanation_template": "{appellation} wines are primarily made from {grape}.",
        "requires_fact_specific": True,
        "selection_weight": 1.0,
    },
    {
        "id": "T-REG-CLASS-01",
        "patterns": [
            "What is the classification level of {appellation}?",
            "Which classification does {appellation} hold?",
            "Identify the classification rank of {appellation}.",
            "Name the classification tier assigned to {appellation}.",
            "The classification of {appellation} is which of the following?",
            "Which appellation status applies to {appellation}?",
        ],
        "domain": "wine_regions",
        "difficulty_range": ["2"],
        "cognitive_dim": "recall",
        "question_type": "multiple_choice",
        "correct_field": "classification",
        "distractor_strategy": "same_type",
        "required_entities": ["classification", "appellation"],
        "explanation_template": "{appellation} holds the {classification} classification.",
        "requires_fact_specific": True,
        "selection_weight": 1.0,
    },
    {
        "id": "T-REG-SUBREGION-01",
        "patterns": [
            "In which sub-region or parent region is {appellation} located?",
            "Which parent region encompasses {appellation}?",
            "Identify the broader region containing {appellation}.",
            "Name the parent wine region of {appellation}.",
            "The {appellation} appellation sits within which region?",
            "Which region of origin is {appellation} part of?",
        ],
        "domain": "wine_regions",
        "difficulty_range": ["2", "3"],
        "cognitive_dim": "recall",
        "question_type": "multiple_choice",
        "correct_field": "region",
        "distractor_strategy": "same_type",
        "required_entities": ["region", "appellation"],
        "explanation_template": "{appellation} is located in the {region} region.",
        "requires_fact_specific": True,
        "selection_weight": 0.8,
    },
    {
        "id": "T-REG-TF-COUNTRY-01",
        "patterns": [
            "True or False: {region} is a wine region in {country}.",
            "True or False: the {region} wine region lies within {country}.",
            "Decide True or False — {region} is a wine region in {country}.",
            "Indicate True or False: {region} is part of {country}'s wine landscape.",
        ],
        "domain": "wine_regions",
        "difficulty_range": ["1"],
        "cognitive_dim": "recall",
        "question_type": "true_false",
        "correct_field": "country",
        "distractor_strategy": "true_false",
        "required_entities": ["country", "region"],
        "explanation_template": "{region} is indeed located in {country}.",
        "requires_fact_specific": False,
        "selection_weight": 0.2,
    },
    {
        "id": "T-REG-SOIL-01",
        "patterns": [
            "What is a characteristic soil type found in {region}?",
            "Which soil type defines the {region} wine region?",
            "Identify the soil type characteristic of {region}.",
            "Name the soil type predominant in {region} vineyards.",
            "The soil typical of {region} is which of the following?",
            "Which type of soil is typical of {region}?",
        ],
        "domain": "wine_regions",
        "difficulty_range": ["2", "3"],
        "cognitive_dim": "recall",
        "question_type": "multiple_choice",
        "correct_field": "soil",
        "distractor_strategy": "same_type",
        "required_entities": ["soil", "region"],
        "explanation_template": "{region} is known for its {soil} soil.",
        "requires_fact_specific": True,
        "selection_weight": 1.2,
    },
    {
        "id": "T-REG-CLIMATE-01",
        "patterns": [
            "What type of climate characterises the {region} wine region?",
            "Which climate type defines {region}?",
            "Identify the climate that characterises {region}.",
            "Name the climate associated with the {region} wine region.",
            "The climate of {region} is best described as which of the following?",
            "Which kind of climate prevails in {region}?",
        ],
        "domain": "wine_regions",
        "difficulty_range": ["2"],
        "cognitive_dim": "comprehension",
        "question_type": "multiple_choice",
        "correct_field": "climate",
        "distractor_strategy": "same_type",
        "required_entities": ["climate", "region"],
        "explanation_template": "The {region} wine region has a {climate} climate.",
        "requires_fact_specific": True,
        "selection_weight": 1.2,
    },
    {
        "id": "T-REG-AREA-01",
        "patterns": [
            "Approximately how large is the {appellation} vineyard area?",
            "What is the approximate vineyard area of {appellation}?",
            "Identify the approximate vineyard area covered by {appellation}.",
            "The vineyard area of {appellation} is approximately which of the following?",
            "Roughly how many hectares does the {appellation} appellation cover?",
        ],
        "domain": "wine_regions",
        "difficulty_range": ["3"],
        "cognitive_dim": "recall",
        "question_type": "multiple_choice",
        "correct_field": "area",
        "distractor_strategy": "same_type",
        "required_entities": ["area", "appellation"],
        "explanation_template": "The {appellation} appellation covers approximately {area}.",
        "requires_fact_specific": True,
        "selection_weight": 1.0,
    },
    {
        "id": "T-REG-STYLE-01",
        "patterns": [
            "What style of wine is {appellation} primarily known for?",
            "Which wine style does {appellation} principally produce?",
            "Identify the wine style most associated with {appellation}.",
            "Name the dominant wine style of {appellation}.",
            "The wine style {appellation} is best known for is which of the following?",
            "Which style of wine dominates {appellation} production?",
        ],
        "domain": "wine_regions",
        "difficulty_range": ["1", "2"],
        "cognitive_dim": "recall",
        "question_type": "multiple_choice",
        "correct_field": "wine_style",
        "distractor_strategy": "same_type",
        "required_entities": ["wine_style", "appellation"],
        "explanation_template": "{appellation} is primarily known for producing {wine_style} wines.",
        "requires_fact_specific": True,
        "selection_weight": 1.0,
    },
    {
        "id": "T-REG-TF-GRAPE-01",
        "patterns": [
            "True or False: {grape} is an authorised grape variety in {appellation}.",
            "True or False: the {appellation} appellation permits {grape}.",
            "Decide True or False — {grape} is an authorised variety in {appellation}.",
            "Indicate True or False: {grape} is among the grapes permitted by {appellation}.",
        ],
        "domain": "wine_regions",
        "difficulty_range": ["2"],
        "cognitive_dim": "recall",
        "question_type": "true_false",
        "correct_field": "grape",
        "distractor_strategy": "true_false",
        "required_entities": ["grape", "appellation"],
        "explanation_template": "{grape} is an authorised variety in {appellation}.",
        "requires_fact_specific": True,
        "selection_weight": 1.0,
    },
    {
        "id": "T-REG-NEIGHBOR-01",
        "patterns": [
            "Which of the following wine regions borders or is near {region}?",
            "Identify the wine region neighbouring {region}.",
            "Name a wine region that lies adjacent to {region}.",
            "Which wine region sits near {region}?",
            "The wine region bordering {region} is which of the following?",
        ],
        "domain": "wine_regions",
        "difficulty_range": ["3"],
        "cognitive_dim": "comprehension",
        "question_type": "multiple_choice",
        "correct_field": "neighbor_region",
        "distractor_strategy": "same_type",
        "required_entities": ["neighbor_region", "region"],
        "explanation_template": "{neighbor_region} is a neighbouring wine region to {region}.",
        "requires_fact_specific": True,
        "selection_weight": 1.0,
    },
    {
        "id": "T-REG-ALTITUDE-01",
        "patterns": [
            "At what approximate altitude are vineyards in {region} typically planted?",
            "Which approximate altitude characterises {region} vineyards?",
            "Identify the typical vineyard altitude in {region}.",
            "The typical altitude of vineyards in {region} is which of the following?",
            "Roughly at what elevation are {region} vineyards planted?",
        ],
        "domain": "wine_regions",
        "difficulty_range": ["3", "4"],
        "cognitive_dim": "recall",
        "question_type": "multiple_choice",
        "correct_field": "altitude",
        "distractor_strategy": "same_type",
        "required_entities": ["altitude", "region"],
        "explanation_template": "Vineyards in {region} are typically found at approximately {altitude}.",
        "requires_fact_specific": True,
        "selection_weight": 1.0,
    },
    {
        "id": "T-REG-YEAR-01",
        "patterns": [
            "In what year was the {appellation} appellation officially established?",
            "Which year did the {appellation} appellation receive its official status?",
            "Identify the year of {appellation}'s official establishment.",
            "The {appellation} appellation was officially established in which year?",
            "When was {appellation} formally recognised as an appellation?",
        ],
        "domain": "wine_regions",
        "difficulty_range": ["3", "4"],
        "cognitive_dim": "recall",
        "question_type": "multiple_choice",
        "correct_field": "year",
        "distractor_strategy": "same_type",
        "required_entities": ["year", "appellation"],
        "explanation_template": "The {appellation} appellation was officially established in {year}.",
        "requires_fact_specific": True,
        "selection_weight": 1.0,
    },
    {
        "id": "T-REG-COLOR-01",
        "patterns": [
            "What colour(s) of wine is {appellation} authorised to produce?",
            "Which wine colour is {appellation} permitted to produce?",
            "Identify the wine colour authorised by the {appellation} appellation.",
            "The wine colour produced under {appellation} is which of the following?",
            "Which colour of wine does {appellation} formally cover?",
        ],
        "domain": "wine_regions",
        "difficulty_range": ["1", "2"],
        "cognitive_dim": "recall",
        "question_type": "multiple_choice",
        "correct_field": "color",
        "distractor_strategy": "same_type",
        "required_entities": ["color", "appellation"],
        "explanation_template": "{appellation} is authorised to produce {color} wines.",
        "requires_fact_specific": True,
        "selection_weight": 0.8,
    },
    {
        "id": "T-REG-RIVER-01",
        "patterns": [
            "Which river or body of water influences the climate of {region}?",
            "Identify the river that shapes the climate of {region}.",
            "Name the river or water body affecting {region}'s climate.",
            "The climate of {region} is influenced by which river?",
            "Which body of water moderates the climate in {region}?",
        ],
        "domain": "wine_regions",
        "difficulty_range": ["2", "3"],
        "cognitive_dim": "comprehension",
        "question_type": "multiple_choice",
        "correct_field": "river",
        "distractor_strategy": "same_type",
        "required_entities": ["river", "region"],
        "explanation_template": "The {river} influences the climate of {region}.",
        "requires_fact_specific": True,
        "selection_weight": 1.0,
    },
    # ── wine_regions: NEW γ-2 fact-specific templates ────────────────────
    {
        "id": "T-REG-AGING-01",
        "patterns": [
            "What is the typical aging requirement for {wine_style} from {region}?",
            "Which aging period applies to {wine_style} produced in {region}?",
            "Identify the minimum aging period for {wine_style} from {region}.",
            "The aging requirement for {wine_style} from {region} is which of the following?",
            "How long must {wine_style} from {region} be aged?",
        ],
        "domain": "wine_regions",
        "difficulty_range": ["2", "3"],
        "cognitive_dim": "recall",
        "question_type": "multiple_choice",
        "correct_field": "aging",
        "distractor_strategy": "same_type",
        "required_entities": ["aging", "wine_style", "region"],
        "explanation_template": "{wine_style} from {region} requires aging of {aging}.",
        "requires_fact_specific": True,
        "selection_weight": 1.2,
    },
    {
        "id": "T-REG-CLASS2-01",
        "patterns": [
            "Which classification level applies to {region}?",
            "What is the classification status of the {region} wine region?",
            "Identify the classification governing {region}.",
            "Name the classification tier of {region}.",
            "The classification level of {region} is which of the following?",
        ],
        "domain": "wine_regions",
        "difficulty_range": ["2"],
        "cognitive_dim": "recall",
        "question_type": "multiple_choice",
        "correct_field": "classification",
        "distractor_strategy": "same_type",
        "required_entities": ["classification", "region"],
        "explanation_template": "The {region} wine region holds the {classification} classification.",
        "requires_fact_specific": True,
        "selection_weight": 1.0,
    },
    # ── grape_varieties (~9 templates) ───────────────────────────────────
    {
        "id": "T-GRP-REGION-01",
        "patterns": [
            "Which wine region is best known for growing {grape}?",
            "What wine region is most associated with {grape}?",
            "Identify the wine region most strongly associated with {grape}.",
            "Name the signature wine region of {grape}.",
            "The wine region most identified with {grape} is which of the following?",
            "In which wine region does {grape} reach its highest expression?",
        ],
        "domain": "grape_varieties",
        "difficulty_range": ["1", "2"],
        "cognitive_dim": "recall",
        "question_type": "multiple_choice",
        "correct_field": "region",
        "distractor_strategy": "same_type",
        "required_entities": ["region", "grape"],
        "explanation_template": "{grape} is a signature grape of the {region} wine region.",
        "requires_fact_specific": True,
        "selection_weight": 0.6,
    },
    {
        "id": "T-GRP-COLOR-01",
        "patterns": [
            "What colour wine does the {grape} grape primarily produce?",
            "Which wine colour is associated with the {grape} grape?",
            "Identify the wine colour that {grape} produces.",
            "The colour of wine produced from {grape} is which of the following?",
            "Which wine colour does {grape} most commonly yield?",
        ],
        "domain": "grape_varieties",
        "difficulty_range": ["1"],
        "cognitive_dim": "recall",
        "question_type": "multiple_choice",
        "correct_field": "color",
        "distractor_strategy": "same_type",
        "required_entities": ["color", "grape"],
        "explanation_template": "{grape} is a {color} grape variety.",
        "requires_fact_specific": False,
        "selection_weight": 0.2,
    },
    {
        "id": "T-GRP-TF-COLOR-01",
        "patterns": [
            "True or False: {grape} is a {color} grape variety.",
            "True or False: the {grape} grape is classified as {color}.",
            "Decide True or False — {grape} is a {color} grape variety.",
            "Indicate True or False: {grape} produces {color} wine.",
        ],
        "domain": "grape_varieties",
        "difficulty_range": ["1"],
        "cognitive_dim": "recall",
        "question_type": "true_false",
        "correct_field": "color",
        "distractor_strategy": "true_false",
        "required_entities": ["color", "grape"],
        "explanation_template": "{grape} is indeed a {color} grape variety.",
        "requires_fact_specific": False,
        "selection_weight": 0.2,
    },
    {
        "id": "T-GRP-SYNONYM-01",
        "patterns": [
            "What is another name (synonym) for the {grape} grape?",
            "Which name is a known synonym of {grape}?",
            "Identify a synonym used for the {grape} grape.",
            "Name an alternative variety name for {grape}.",
            "Which of the following is a synonym for {grape}?",
        ],
        "domain": "grape_varieties",
        "difficulty_range": ["2", "3"],
        "cognitive_dim": "recall",
        "question_type": "multiple_choice",
        "correct_field": "synonym",
        "distractor_strategy": "same_type",
        "required_entities": ["synonym", "grape"],
        "explanation_template": "{grape} is also known as {synonym}.",
        "requires_fact_specific": True,
        "selection_weight": 1.0,
    },
    {
        "id": "T-GRP-ORIGIN-01",
        "patterns": [
            "Which country is considered the origin of the {grape} grape?",
            "What country is the homeland of the {grape} grape?",
            "Identify the country of origin of the {grape} grape.",
            "Name the country where {grape} originated.",
            "The grape {grape} originated in which country?",
        ],
        "domain": "grape_varieties",
        "difficulty_range": ["2"],
        "cognitive_dim": "recall",
        "question_type": "multiple_choice",
        "correct_field": "country",
        "distractor_strategy": "same_type",
        "required_entities": ["country", "grape"],
        "explanation_template": "{grape} originated in {country}.",
        "requires_fact_specific": False,
        "selection_weight": 0.3,
    },
    {
        "id": "T-GRP-PARENT-01",
        "patterns": [
            "Which grape is a parent variety of {grape}?",
            "What grape is among the parent varieties of {grape}?",
            "Identify a parent grape of {grape}.",
            "Name a parent variety of {grape}.",
            "A parent variety of {grape} is which of the following?",
        ],
        "domain": "grape_varieties",
        "difficulty_range": ["3", "4"],
        "cognitive_dim": "recall",
        "question_type": "multiple_choice",
        "correct_field": "parent_grape",
        "distractor_strategy": "same_type",
        "required_entities": ["parent_grape", "grape"],
        "explanation_template": "{parent_grape} is a parent variety of {grape}.",
        "requires_fact_specific": True,
        "selection_weight": 1.0,
    },
    {
        "id": "T-GRP-AROMA-01",
        "patterns": [
            "Which of the following is a characteristic aroma of wines made from {grape}?",
            "What aroma typifies wines made from {grape}?",
            "Identify a characteristic aroma of {grape} wines.",
            "Name an aroma associated with wines from {grape}.",
            "Wines made from {grape} are characteristically associated with which aroma?",
        ],
        "domain": "grape_varieties",
        "difficulty_range": ["2", "3"],
        "cognitive_dim": "recall",
        "question_type": "multiple_choice",
        "correct_field": "aroma",
        "distractor_strategy": "same_type",
        "required_entities": ["aroma", "grape"],
        "explanation_template": "Wines made from {grape} are characteristically associated with {aroma} aromas.",
        "requires_fact_specific": True,
        "selection_weight": 1.2,
    },
    {
        "id": "T-GRP-ACREAGE-01",
        "patterns": [
            "Approximately how many hectares of {grape} are planted worldwide?",
            "What is the approximate global hectarage planted to {grape}?",
            "Identify the approximate global plantings of {grape}.",
            "The approximate global area planted to {grape} is which of the following?",
            "Roughly how many hectares of {grape} exist worldwide?",
        ],
        "domain": "grape_varieties",
        "difficulty_range": ["3", "4"],
        "cognitive_dim": "recall",
        "question_type": "multiple_choice",
        "correct_field": "acreage",
        "distractor_strategy": "same_type",
        "required_entities": ["acreage", "grape"],
        "explanation_template": "There are approximately {acreage} of {grape} planted worldwide.",
        "requires_fact_specific": True,
        "selection_weight": 1.0,
    },
    # ── grape_varieties: NEW γ-2 fact-specific ───────────────────────────
    {
        "id": "T-GRP-AGING-01",
        "patterns": [
            "What is the typical aging requirement for {wine_style} made from {grape}?",
            "Which aging period applies to {wine_style} from {grape}?",
            "Identify the minimum aging requirement for {wine_style} based on {grape}.",
            "The aging requirement for {wine_style} from {grape} is which of the following?",
        ],
        "domain": "grape_varieties",
        "difficulty_range": ["2", "3"],
        "cognitive_dim": "recall",
        "question_type": "multiple_choice",
        "correct_field": "aging",
        "distractor_strategy": "same_type",
        "required_entities": ["aging", "wine_style", "grape"],
        "explanation_template": "{wine_style} from {grape} requires aging of {aging}.",
        "requires_fact_specific": True,
        "selection_weight": 1.2,
    },
    # ── producers ────────────────────────────────────────────────────────
    {
        "id": "T-PRD-REGION-01",
        "patterns": [
            "In which wine region is {producer} located?",
            "What wine region is {producer} part of?",
            "Identify the wine region in which {producer} is based.",
            "Name the wine region where {producer} is found.",
            "The wine region of {producer} is which of the following?",
            "Which region houses the producer {producer}?",
        ],
        "domain": "producers",
        "difficulty_range": ["1", "2"],
        "cognitive_dim": "recall",
        "question_type": "multiple_choice",
        "correct_field": "region",
        "distractor_strategy": "same_type",
        "required_entities": ["region", "producer"],
        "explanation_template": "{producer} is located in the {region} wine region.",
        "requires_fact_specific": True,
        "selection_weight": 0.6,
    },
    {
        "id": "T-PRD-APPELLATION-01",
        "patterns": [
            "Which appellation does the wine estate {producer} belong to?",
            "What appellation is {producer} located within?",
            "Identify the appellation of the producer {producer}.",
            "Name the appellation that includes {producer}.",
            "The appellation of {producer} is which of the following?",
        ],
        "domain": "producers",
        "difficulty_range": ["2", "3"],
        "cognitive_dim": "recall",
        "question_type": "multiple_choice",
        "correct_field": "appellation",
        "distractor_strategy": "same_type",
        "required_entities": ["appellation", "producer"],
        "explanation_template": "{producer} belongs to the {appellation} appellation.",
        "requires_fact_specific": True,
        "selection_weight": 1.0,
    },
    {
        "id": "T-PRD-GRAPE-01",
        "patterns": [
            "Which grape variety is {producer} most associated with?",
            "What grape variety is most strongly identified with {producer}?",
            "Identify the flagship grape variety of {producer}.",
            "Name the grape most associated with the producer {producer}.",
            "The flagship grape of {producer} is which of the following?",
            "What is the flagship grape of {producer}?",
        ],
        "domain": "producers",
        "difficulty_range": ["2", "3"],
        "cognitive_dim": "recall",
        "question_type": "multiple_choice",
        "correct_field": "flagship_grape",
        "distractor_strategy": "same_type",
        "required_entities": ["flagship_grape", "producer"],
        "explanation_template": "{producer} is most closely associated with the {flagship_grape} grape.",
        "requires_fact_specific": True,
        "selection_weight": 1.2,
    },
    {
        "id": "T-PRD-COUNTRY-01",
        "patterns": [
            "In which country is {producer} based?",
            "What country is the producer {producer} located in?",
            "Identify the country of the producer {producer}.",
            "Name the country in which {producer} operates.",
            "The country in which {producer} is based is which of the following?",
        ],
        "domain": "producers",
        "difficulty_range": ["1"],
        "cognitive_dim": "recall",
        "question_type": "multiple_choice",
        "correct_field": "country",
        "distractor_strategy": "same_type",
        "required_entities": ["country", "producer"],
        "explanation_template": "{producer} is based in {country}.",
        "requires_fact_specific": False,
        "selection_weight": 0.2,
    },
    {
        "id": "T-PRD-CLASS-01",
        "patterns": [
            "What classification does {producer} hold?",
            "Which classification is held by {producer}?",
            "Identify the classification awarded to {producer}.",
            "Name the classification level of {producer}.",
            "The classification of {producer} is which of the following?",
        ],
        "domain": "producers",
        "difficulty_range": ["3", "4"],
        "cognitive_dim": "recall",
        "question_type": "multiple_choice",
        "correct_field": "classification",
        "distractor_strategy": "same_type",
        "required_entities": ["classification", "producer"],
        "explanation_template": "{producer} holds the {classification} classification.",
        "requires_fact_specific": True,
        "selection_weight": 1.2,
    },
    {
        "id": "T-PRD-TF-REGION-01",
        "patterns": [
            "True or False: {producer} is located in the {region} wine region.",
            "True or False: the producer {producer} sits within the {region} wine region.",
            "Decide True or False — {producer} is a producer of the {region} wine region.",
            "Indicate True or False: {producer} operates in the {region} wine region.",
        ],
        "domain": "producers",
        "difficulty_range": ["1", "2"],
        "cognitive_dim": "recall",
        "question_type": "true_false",
        "correct_field": "region",
        "distractor_strategy": "true_false",
        "required_entities": ["region", "producer"],
        "explanation_template": "{producer} is indeed located in {region}.",
        "requires_fact_specific": True,
        "selection_weight": 0.6,
    },
    # ── winemaking ───────────────────────────────────────────────────────
    {
        "id": "T-WMK-TECHNIQUE-01",
        "patterns": [
            "Which winemaking technique is typically used in the production of {wine_style}?",
            "What technique is most commonly applied when producing {wine_style}?",
            "Identify the technique characteristic of {wine_style} production.",
            "Name the winemaking technique typically used for {wine_style}.",
            "The signature winemaking technique for {wine_style} is which of the following?",
        ],
        "domain": "winemaking",
        "difficulty_range": ["2", "3"],
        "cognitive_dim": "comprehension",
        "question_type": "multiple_choice",
        "correct_field": "technique",
        "distractor_strategy": "same_type",
        "required_entities": ["technique", "wine_style"],
        "explanation_template": "The production of {wine_style} typically involves {technique}.",
        "requires_fact_specific": True,
        "selection_weight": 1.0,
    },
    {
        "id": "T-WMK-TEMP-01",
        "patterns": [
            "At what temperature range is {process} typically conducted?",
            "Which temperature range is typical for the {process} process?",
            "Identify the typical temperature for {process}.",
            "Name the temperature range used in {process}.",
            "The typical temperature for {process} is which of the following?",
        ],
        "domain": "winemaking",
        "difficulty_range": ["2", "3"],
        "cognitive_dim": "recall",
        "question_type": "multiple_choice",
        "correct_field": "temperature",
        "distractor_strategy": "same_type",
        "required_entities": ["temperature", "process"],
        "explanation_template": "{process} is typically conducted at {temperature}.",
        "requires_fact_specific": True,
        "selection_weight": 1.0,
    },
    {
        "id": "T-WMK-VESSEL-01",
        "patterns": [
            "Which type of vessel is traditionally used for {process}?",
            "What vessel is conventionally used during {process}?",
            "Identify the traditional vessel for {process}.",
            "Name the vessel commonly used in {process}.",
            "The traditional vessel for {process} is which of the following?",
        ],
        "domain": "winemaking",
        "difficulty_range": ["2"],
        "cognitive_dim": "recall",
        "question_type": "multiple_choice",
        "correct_field": "vessel",
        "distractor_strategy": "same_type",
        "required_entities": ["vessel", "process"],
        "explanation_template": "{process} is traditionally carried out in {vessel}.",
        "requires_fact_specific": True,
        "selection_weight": 1.0,
    },
    {
        "id": "T-WMK-DURATION-01",
        "patterns": [
            "How long does {process} typically last?",
            "Which duration is typical for {process}?",
            "Identify the typical duration of {process}.",
            "Name the typical duration for {process}.",
            "The typical duration of {process} is which of the following?",
        ],
        "domain": "winemaking",
        "difficulty_range": ["2", "3"],
        "cognitive_dim": "recall",
        "question_type": "multiple_choice",
        "correct_field": "duration",
        "distractor_strategy": "same_type",
        "required_entities": ["duration", "process"],
        "explanation_template": "{process} typically lasts {duration}.",
        "requires_fact_specific": True,
        "selection_weight": 1.0,
    },
    {
        "id": "T-WMK-TF-01",
        "patterns": [
            "True or False: {technique} is a step in making {wine_style}.",
            "True or False: the production of {wine_style} involves {technique}.",
            "Decide True or False — {technique} is part of {wine_style} production.",
            "Indicate True or False: {technique} is used to make {wine_style}.",
        ],
        "domain": "winemaking",
        "difficulty_range": ["1", "2"],
        "cognitive_dim": "recall",
        "question_type": "true_false",
        "correct_field": "technique",
        "distractor_strategy": "true_false",
        "required_entities": ["technique", "wine_style"],
        "explanation_template": "{technique} is indeed used in the production of {wine_style}.",
        "requires_fact_specific": True,
        "selection_weight": 1.0,
    },
    {
        "id": "T-WMK-RESULT-01",
        "patterns": [
            "What is the primary purpose of {technique} in winemaking?",
            "Which purpose does {technique} serve in winemaking?",
            "Identify the primary purpose of {technique} during winemaking.",
            "Name the main purpose of using {technique} in winemaking.",
            "The primary purpose of {technique} in winemaking is which of the following?",
        ],
        "domain": "winemaking",
        "difficulty_range": ["2", "3"],
        "cognitive_dim": "comprehension",
        "question_type": "multiple_choice",
        "correct_field": "purpose",
        "distractor_strategy": "same_type",
        "required_entities": ["purpose", "technique"],
        "explanation_template": "The primary purpose of {technique} is {purpose}.",
        "requires_fact_specific": True,
        "selection_weight": 1.2,
    },
    # ── viticulture ──────────────────────────────────────────────────────
    {
        "id": "T-VIT-CLIMATE-01",
        "patterns": [
            "What type of climate is most suitable for growing {grape}?",
            "Which climate is most suited to {grape}?",
            "Identify the climate most suitable for cultivating {grape}.",
            "Name the climate type best suited to {grape}.",
            "The climate most suitable for {grape} is which of the following?",
        ],
        "domain": "viticulture",
        "difficulty_range": ["2"],
        "cognitive_dim": "comprehension",
        "question_type": "multiple_choice",
        "correct_field": "climate",
        "distractor_strategy": "same_type",
        "required_entities": ["climate", "grape"],
        "explanation_template": "{grape} thrives best in a {climate} climate.",
        "requires_fact_specific": True,
        "selection_weight": 1.0,
    },
    {
        "id": "T-VIT-PEST-01",
        "patterns": [
            "Which pest or disease commonly affects {grape} vineyards?",
            "What pest most often threatens {grape} vineyards?",
            "Identify a pest or disease that frequently affects {grape}.",
            "Name a pest or disease commonly seen in {grape} vineyards.",
            "A common threat to {grape} vineyards is which of the following?",
        ],
        "domain": "viticulture",
        "difficulty_range": ["2", "3"],
        "cognitive_dim": "recall",
        "question_type": "multiple_choice",
        "correct_field": "pest",
        "distractor_strategy": "same_type",
        "required_entities": ["pest", "grape"],
        "explanation_template": "{pest} is a common threat to {grape} vineyards.",
        "requires_fact_specific": True,
        "selection_weight": 1.2,
    },
    {
        "id": "T-VIT-TRAINING-01",
        "patterns": [
            "Which vine training system is commonly used in {region}?",
            "What training system is most prevalent in {region}?",
            "Identify the vine training system common in {region}.",
            "Name the training system commonly used in {region}.",
            "The vine training system commonly seen in {region} is which of the following?",
        ],
        "domain": "viticulture",
        "difficulty_range": ["2", "3"],
        "cognitive_dim": "recall",
        "question_type": "multiple_choice",
        "correct_field": "training_system",
        "distractor_strategy": "same_type",
        "required_entities": ["training_system", "region"],
        "explanation_template": "The {training_system} training system is commonly used in {region}.",
        "requires_fact_specific": True,
        "selection_weight": 1.0,
    },
    {
        "id": "T-VIT-ROOTSTOCK-01",
        "patterns": [
            "Which rootstock is commonly used for {grape} in {region}?",
            "What rootstock is preferred for {grape} grown in {region}?",
            "Identify the rootstock often paired with {grape} in {region}.",
            "Name the rootstock commonly used for {grape} in {region}.",
            "A common rootstock for {grape} in {region} is which of the following?",
        ],
        "domain": "viticulture",
        "difficulty_range": ["3", "4"],
        "cognitive_dim": "recall",
        "question_type": "multiple_choice",
        "correct_field": "rootstock",
        "distractor_strategy": "same_type",
        "required_entities": ["rootstock", "grape", "region"],
        "explanation_template": "{rootstock} is a common rootstock choice for {grape} in {region}.",
        "requires_fact_specific": True,
        "selection_weight": 1.2,
    },
    {
        "id": "T-VIT-TF-PEST-01",
        "patterns": [
            "True or False: {pest} is a significant viticultural threat in {region}.",
            "True or False: the pest {pest} is a notable concern in {region}.",
            "Decide True or False — {pest} significantly affects vineyards in {region}.",
            "Indicate True or False: {pest} poses a serious viticultural risk in {region}.",
        ],
        "domain": "viticulture",
        "difficulty_range": ["2"],
        "cognitive_dim": "recall",
        "question_type": "true_false",
        "correct_field": "pest",
        "distractor_strategy": "true_false",
        "required_entities": ["pest", "region"],
        "explanation_template": "{pest} is indeed a significant threat in {region}.",
        "requires_fact_specific": True,
        "selection_weight": 1.0,
    },
    # ── wine_business ────────────────────────────────────────────────────
    {
        "id": "T-BIZ-CLASSIF-01",
        "patterns": [
            "Which classification system is used in {region}?",
            "What classification system applies to {region}?",
            "Identify the classification system in force in {region}.",
            "Name the classification system used in {region}.",
            "The classification system used in {region} is which of the following?",
        ],
        "domain": "wine_business",
        "difficulty_range": ["2"],
        "cognitive_dim": "recall",
        "question_type": "multiple_choice",
        "correct_field": "classification",
        "distractor_strategy": "same_type",
        "required_entities": ["classification", "region"],
        "explanation_template": "The {classification} system is used in {region}.",
        "requires_fact_specific": True,
        "selection_weight": 1.0,
    },
    {
        "id": "T-BIZ-REGULATION-01",
        "patterns": [
            "Which regulatory body governs wine production in {region}?",
            "What body regulates wine production in {region}?",
            "Identify the regulatory body for wine in {region}.",
            "Name the agency that governs wine production in {region}.",
            "The regulatory body for wine in {region} is which of the following?",
        ],
        "domain": "wine_business",
        "difficulty_range": ["2", "3"],
        "cognitive_dim": "recall",
        "question_type": "multiple_choice",
        "correct_field": "regulatory_body",
        "distractor_strategy": "same_type",
        "required_entities": ["regulatory_body", "region"],
        "explanation_template": "Wine production in {region} is governed by {regulatory_body}.",
        "requires_fact_specific": True,
        "selection_weight": 1.0,
    },
    {
        "id": "T-BIZ-LABEL-01",
        "patterns": [
            "What label term indicates {wine_designation} in {country}?",
            "Which labelling term denotes {wine_designation} within {country}?",
            "Identify the label term meaning {wine_designation} in {country}.",
            "Name the term that indicates {wine_designation} on labels in {country}.",
            "In {country}, the label term for {wine_designation} is which of the following?",
        ],
        "domain": "wine_business",
        "difficulty_range": ["2", "3"],
        "cognitive_dim": "recall",
        "question_type": "multiple_choice",
        "correct_field": "label_term",
        "distractor_strategy": "same_type",
        "required_entities": ["label_term", "wine_designation", "country"],
        "explanation_template": "In {country}, the term {label_term} indicates {wine_designation}.",
        "requires_fact_specific": True,
        "selection_weight": 1.2,
    },
    {
        "id": "T-BIZ-TF-REG-01",
        "patterns": [
            "True or False: {regulatory_body} is responsible for wine regulation in {country}.",
            "True or False: the body {regulatory_body} regulates wine in {country}.",
            "Decide True or False — {regulatory_body} oversees wine regulation in {country}.",
            "Indicate True or False: {regulatory_body} is the wine regulator in {country}.",
        ],
        "domain": "wine_business",
        "difficulty_range": ["2"],
        "cognitive_dim": "recall",
        "question_type": "true_false",
        "correct_field": "regulatory_body",
        "distractor_strategy": "true_false",
        "required_entities": ["regulatory_body", "country"],
        "explanation_template": "{regulatory_body} is indeed the regulatory authority in {country}.",
        "requires_fact_specific": True,
        "selection_weight": 1.0,
    },
    {
        "id": "T-BIZ-EXPORT-01",
        "patterns": [
            "Which country is the largest export market for wines from {region}?",
            "What country is the top export destination for wines of {region}?",
            "Identify the largest export market for {region} wines.",
            "Name the leading export market for wines from {region}.",
            "The largest export market for {region} wines is which of the following?",
        ],
        "domain": "wine_business",
        "difficulty_range": ["3", "4"],
        "cognitive_dim": "recall",
        "question_type": "multiple_choice",
        "correct_field": "market",
        "distractor_strategy": "same_type",
        "required_entities": ["market", "region"],
        "explanation_template": "{market} is the largest export market for {region} wines.",
        "requires_fact_specific": True,
        "selection_weight": 1.0,
    },
]

DOMAINS = list(DOMAIN_TARGETS.keys())
OPTION_IDS = ["A", "B", "C", "D"]

# γ-1 — Embedding cache parameters
_EMB_TOPK = 8
_EMB_LO = 1   # skip position 0 (closest, may be alias) — pick from indices 1..4
_EMB_HI = 5
_EMB_DIM = 1536

# γ-1 — Per-process embedding cache: maps phrase -> embedding (list[float])
_EMBED_CACHE: dict[str, list[float]] = {}

# γ-3 — Per-process entity-mention-count cache
_MENTION_CACHE: dict[str, int] = {}


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
            # First occurrence wins to keep behaviour deterministic
            out.setdefault(etype, ename)
    return out


def _extract_slot_names(pattern: str) -> list[str]:
    """Extract {placeholder} names from a template pattern."""
    return re.findall(r"\{(\w+)\}", pattern)


# ─── γ-1 Embedding-similarity distractor sampling ─────────────────────────


def _get_openai_embeddings_client():
    """OpenAI client routed through OpenRouter for embeddings (mirrors _dedup.py)."""
    from openai import OpenAI

    return OpenAI(
        api_key=os.getenv("OPENROUTER_API_KEY"),
        base_url="https://openrouter.ai/api/v1",
    )


def _context_phrase(entity_name: str, entity_type: str) -> str:
    """Build a short context phrase used to embed an entity for distractor lookup.

    For the correct entity we use a richer phrase that includes the entity type
    (e.g. "Rheingau wine region"). Candidate entities use the same shape so
    cosine similarity stays comparable.
    """
    norm_type = (entity_type or "").replace("_", " ")
    if entity_type in ("region", "appellation", "ava", "subregion", "neighbor_region"):
        return f"{entity_name} wine {norm_type}"
    if entity_type in ("country", "state", "county"):
        return f"{entity_name} {norm_type} wine production"
    if entity_type in ("grape", "parent_grape", "flagship_grape"):
        return f"{entity_name} grape variety"
    if entity_type == "producer":
        return f"{entity_name} wine producer"
    if entity_type == "soil":
        return f"{entity_name} vineyard soil type"
    if entity_type == "climate":
        return f"{entity_name} viticultural climate"
    if entity_type == "wine_style":
        return f"{entity_name} wine style"
    if entity_type == "classification":
        return f"{entity_name} wine classification"
    if entity_type == "technique":
        return f"{entity_name} winemaking technique"
    if entity_type == "process":
        return f"{entity_name} winemaking process"
    if entity_type == "regulatory_body":
        return f"{entity_name} wine regulatory body"
    return f"{entity_name} {norm_type}".strip()


def _embed_text(text: str) -> list[float] | None:
    """Embed a phrase via OpenRouter's text-embedding-3-small.

    Returns None on failure; the caller falls back to random sampling.
    """
    if text in _EMBED_CACHE:
        cached = _EMBED_CACHE[text]
        return cached if cached else None
    try:
        client = _get_openai_embeddings_client()
        resp = client.embeddings.create(
            model="openai/text-embedding-3-small",
            input=text,
        )
        emb = list(resp.data[0].embedding)
        _EMBED_CACHE[text] = emb
        return emb
    except Exception as e:  # network / quota / config failure
        logger.warning(f"Embedding failed for {text!r}: {e}")
        _EMBED_CACHE[text] = []  # remember the failure to avoid retry storms
        return None


def _cosine(a: list[float], b: list[float]) -> float:
    """Plain cosine similarity between two equal-length lists."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _in_memory_topk(
    correct_value: str,
    entity_type: str,
    candidates: list[str],
    k: int,
) -> list[str]:
    """Embed the correct entity and each candidate, return the top-K by cosine sim.

    Returns an ordered list (descending similarity). May be shorter than ``k``
    if too many candidates failed to embed.
    """
    target_phrase = _context_phrase(correct_value, entity_type)
    target_emb = _embed_text(target_phrase)
    if target_emb is None:
        return []

    scored: list[tuple[float, str]] = []
    for cand in candidates:
        if cand.lower() == correct_value.lower():
            continue
        cand_phrase = _context_phrase(cand, entity_type)
        cand_emb = _embed_text(cand_phrase)
        if cand_emb is None:
            continue
        sim = _cosine(target_emb, cand_emb)
        scored.append((sim, cand))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [name for _, name in scored[:k]]


def embedding_similarity_distractors(
    correct_value: str,
    entity_type: str,
    candidate_pool: list[str],
    count: int = 3,
    *,
    embed_fn=None,
) -> list[str]:
    """γ-1 — Pick distractors from the K nearest neighbours of the correct entity.

    1. Take the K=8 nearest candidates by embedding cosine similarity.
    2. Skip position 0 (closest — may be a near-alias of the correct entity).
    3. From the remaining (positions 1..4) take ``count`` distractors.
    4. Return [] if fewer than ``count`` viable neighbours can be assembled —
       caller should drop the question rather than fall back to random.

    ``embed_fn`` lets unit tests inject a deterministic embedding lookup.
    Default is the OpenRouter-backed :func:`_embed_text`.
    """
    if not candidate_pool:
        return []

    embed_fn = embed_fn or _embed_text
    target_phrase = _context_phrase(correct_value, entity_type)
    target_emb = embed_fn(target_phrase)
    if target_emb is None:
        return []

    scored: list[tuple[float, str]] = []
    for cand in candidate_pool:
        if cand.lower() == correct_value.lower():
            continue
        cand_phrase = _context_phrase(cand, entity_type)
        cand_emb = embed_fn(cand_phrase)
        if cand_emb is None:
            continue
        sim = _cosine(target_emb, cand_emb)
        scored.append((sim, cand))

    if len(scored) < count + 1:
        return []

    scored.sort(key=lambda x: x[0], reverse=True)
    top = [name for _, name in scored[:_EMB_TOPK]]

    # Pick from positions [1, 2, 3, 4] — skip the very closest (potential alias)
    band = top[_EMB_LO:_EMB_HI]
    if len(band) < count:
        return []
    return band[:count]


def _candidate_pool_for_type(
    entity_type: str,
    correct_value: str,
    facts: list[dict],
) -> list[str]:
    """Collect unique candidate entity names of a given type for distractor sampling.

    Pulls first from the in-process fact list (cheap) and tops up from a cached
    DB lookup when the local pool is too thin.
    """
    seen: set[str] = set()
    out: list[str] = []
    correct_lower = correct_value.lower()
    for fact in facts:
        ents = _extract_entities(fact)
        val = ents.get(entity_type, "")
        if not val:
            continue
        if val.lower() == correct_lower:
            continue
        key = val.lower()
        if key not in seen:
            seen.add(key)
            out.append(val)

    # γ-1 needs at least K=8 candidates to pick a meaningful neighbour band.
    if len(out) < _EMB_TOPK + 2:
        for cand in _global_candidates_for_type(entity_type):
            key = cand.lower()
            if key in seen or key == correct_lower:
                continue
            seen.add(key)
            out.append(cand)
            if len(out) >= 50:  # cap pool size to control embedding cost
                break

    return out


@lru_cache(maxsize=None)
def _global_candidates_for_type(entity_type: str) -> tuple[str, ...]:
    """Cached DB lookup of all distinct entity names for a type (capped at 200)."""
    try:
        conn = get_pg()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT DISTINCT e->>'name' AS name
            FROM facts f, jsonb_array_elements(f.entities) e
            WHERE e->>'type' = %s
              AND e->>'name' IS NOT NULL
              AND length(e->>'name') > 1
            LIMIT 200
            """,
            (entity_type,),
        )
        return tuple(r["name"] for r in cur.fetchall() if r["name"])
    except Exception as e:
        logger.warning(f"Global candidate fetch failed for {entity_type!r}: {e}")
        return ()


# ─── γ-3 Per-instance difficulty heuristic ────────────────────────────────


def _entity_mention_count(entity_name: str) -> int:
    """Return the number of facts whose entities JSONB contains ``entity_name``.

    Cached per process so the same entity isn't looked up repeatedly.
    """
    if not entity_name:
        return 0
    key = entity_name.lower().strip()
    if key in _MENTION_CACHE:
        return _MENTION_CACHE[key]
    try:
        import orjson as _orjson
        conn = get_pg()
        cur = conn.cursor()
        # @> with a JSONB literal of a one-element array containing {name: ...}
        # works against the GIN index on facts.entities.
        payload = _orjson.dumps([{"name": entity_name}]).decode()
        cur.execute(
            "SELECT count(*) AS cnt FROM facts WHERE entities @> %s::jsonb",
            (payload,),
        )
        cnt = int(cur.fetchone()["cnt"])
    except Exception as e:
        logger.warning(f"Mention-count lookup failed for {entity_name!r}: {e}")
        cnt = 0
    _MENTION_CACHE[key] = cnt
    return cnt


def heuristic_difficulty(entity_name: str) -> str:
    """Map entity-mention count to a difficulty band (γ-3).

    >=100 mentions → '1' (well-known)
    20-99 → '2'
    5-19 → '3'
    <5 → '4'
    """
    cnt = _entity_mention_count(entity_name)
    if cnt >= 100:
        return "1"
    if cnt >= 20:
        return "2"
    if cnt >= 5:
        return "3"
    return "4"


# ─── γ-4 Phrasing diversification ─────────────────────────────────────────


def select_pattern_variant(template: dict, seed_key: str) -> str:
    """Deterministically pick one phrasing variant for a (template, entity).

    The choice is stable across runs: the same (template_id, seed_key) pair
    always yields the same pattern string. Different entities naturally
    rotate through the variants thanks to the SHA-256 distribution.
    """
    patterns = template.get("patterns") or []
    if not patterns:
        # Backward-compatibility shim if a caller still uses singular ``pattern``
        single = template.get("pattern")
        if single:
            patterns = [single]
    if not patterns:
        raise ValueError(f"Template {template.get('id')} has no patterns")
    if len(patterns) == 1:
        return patterns[0]
    digest = hashlib.sha256(
        f"{template['id']}::{seed_key}".encode("utf-8")
    ).hexdigest()
    idx = int(digest[:8], 16) % len(patterns)
    return patterns[idx]


# ─── Core generation functions ────────────────────────────────────────────


def find_matching_facts(template: dict, facts: list[dict]) -> list[dict]:
    """Filter facts that have the required entity types for this template.

    γ-2: when ``requires_fact_specific`` is True the correct field MUST be
    present (otherwise the template would fall back to a world-knowledge
    answer and the question would be solvable without the source fact).
    """
    required = set(template["required_entities"])
    correct_field = template["correct_field"]
    matched: list[dict] = []
    for fact in facts:
        ents = _extract_entities(fact)
        if not required.issubset(ents.keys()):
            continue
        if template.get("requires_fact_specific") and not ents.get(correct_field):
            continue
        matched.append(fact)
    return matched


def source_distractors(
    correct_value: str,
    entity_type: str,
    facts: list[dict],
    count: int = 3,
) -> list[str]:
    """Legacy random-pool distractor sampler (fallback only).

    Kept as a backstop when embedding lookup is unavailable (e.g. no API key
    or network failure). The primary path is
    :func:`embedding_similarity_distractors`.
    """
    candidates: list[str] = []
    seen: set[str] = set()
    correct_lower = correct_value.lower()
    for fact in facts:
        ents = _extract_entities(fact)
        val = ents.get(entity_type, "")
        if val and val.lower() != correct_lower and val.lower() not in seen:
            seen.add(val.lower())
            candidates.append(val)
    random.shuffle(candidates)
    return candidates[:count]


def fill_template(
    template: dict,
    fact: dict,
    all_facts: list[dict],
    *,
    use_embeddings: bool = True,
) -> dict | None:
    """Fill a template with fact data to produce a question dict.

    Returns a dict ready for ``insert_question``, or None if the fact doesn't
    have the required entities, the embedding lookup couldn't yield 3 viable
    distractors, or the format step fails. When ``use_embeddings`` is False
    (e.g. unit tests with a stubbed pool) the legacy random sampler is used.
    """
    ents = _extract_entities(fact)
    required = set(template["required_entities"])
    if not required.issubset(ents.keys()):
        return None

    correct_field = template["correct_field"]
    correct_value = ents.get(correct_field)
    if not correct_value:
        return None

    if template.get("requires_fact_specific") and not correct_value:
        return None

    slots = dict(ents)
    if fact.get("subdomain"):
        slots.setdefault("subdomain", fact["subdomain"])

    # γ-4 — pick a phrasing variant deterministically by entity name
    seed_key = correct_value.lower()
    pattern = select_pattern_variant(template, seed_key)
    explanation_pattern = template["explanation_template"]

    try:
        question_text = pattern.format(**slots)
        explanation = explanation_pattern.format(**slots)
    except KeyError:
        return None

    question_type = template["question_type"]

    # γ-3 — per-instance difficulty heuristic
    difficulty = heuristic_difficulty(correct_value)

    if question_type == "true_false":
        options = [{"id": "A", "text": "True"}, {"id": "B", "text": "False"}]
        correct_answer = "A"
        correct_answer_text = "True"
    elif question_type == "multiple_choice":
        candidate_pool = _candidate_pool_for_type(correct_field, correct_value, all_facts)
        distractors: list[str] = []
        if use_embeddings and len(candidate_pool) >= _EMB_TOPK:
            distractors = embedding_similarity_distractors(
                correct_value, correct_field, candidate_pool, count=3
            )
        if len(distractors) < 3:
            # γ-1 spec: "If fewer than 3 viable neighbours exist for that
            # entity, skip the template instance (don't produce a question)."
            # When use_embeddings is explicitly disabled (unit tests, debug
            # runs), fall back to random sampling.
            if use_embeddings:
                return None
            distractors = source_distractors(
                correct_value, correct_field, all_facts, count=3
            )
            if len(distractors) < 3:
                return None

        choices = [correct_value] + distractors[:3]
        random.shuffle(choices)
        correct_idx = choices.index(correct_value)
        options = [
            {"id": OPTION_IDS[i], "text": choices[i]} for i in range(4)
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


# ─── Template selection (γ-2 weighted) ────────────────────────────────────


def _weighted_template_order(
    templates_for_domain: list[dict],
    rng: random.Random | None = None,
) -> list[dict]:
    """Order templates so high-weight (fact-specific) ones come first.

    Tie-breaking is randomised per call so a long run rotates evenly through
    the templates within each weight band.
    """
    rng = rng or random
    ordered = sorted(
        templates_for_domain,
        key=lambda t: (-(t.get("selection_weight") or 1.0), rng.random()),
    )
    return ordered


# ─── CLI ──────────────────────────────────────────────────────────────────


@click.command()
@click.option("--domain", type=click.Choice(DOMAINS), help="Generate for one domain only")
@click.option("--count", type=int, default=10, help="Questions to generate per domain")
@click.option("--difficulty", type=click.Choice(["1", "2", "3", "4"]), help="Filter templates by difficulty")
@click.option("--dry-run", is_flag=True, help="Preview without DB writes")
@click.option("--test-run", is_flag=True, help="Small test run (5 questions)")
@click.option("--validate", is_flag=True, help="Quality report on generated questions")
@click.option("--list", "list_templates", is_flag=True, help="List available templates")
@click.option("--all", "run_all", is_flag=True, help="Generate for all domains using targets")
@click.option("--paraphrase", is_flag=True, help="Optional γ-5 LLM paraphrase post-pass (Gemini)")
@click.option("--no-embeddings", is_flag=True, help="Disable γ-1 embedding distractors (debug)")
def main(
    domain,
    count,
    difficulty,
    dry_run,
    test_run,
    validate,
    list_templates,
    run_all,
    paraphrase,
    no_embeddings,
):
    """Template-based question generator (Strategy 2, v2 overhaul)."""
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

    paraphrase_fn = None
    if paraphrase:
        try:
            from src.generators._template_paraphrase import paraphrase_question_text
            paraphrase_fn = paraphrase_question_text
            logger.info("γ-5 LLM paraphrase post-pass ENABLED (Gemini)")
        except Exception as e:
            logger.warning(f"Paraphrase module unavailable: {e}")

    use_embeddings = not no_embeddings

    for dom in domains:
        target = count if not run_all else DOMAIN_TARGETS.get(dom, 100) // 4
        templates_for_domain = [
            t for t in TEMPLATES if t["domain"] == dom
            and (not difficulty or difficulty in t["difficulty_range"])
        ]
        if not templates_for_domain:
            logger.warning(f"No templates for domain={dom}")
            continue

        # γ-2 — high-weight fact-specific templates first
        templates_for_domain = _weighted_template_order(templates_for_domain)

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
                result = fill_template(
                    template, fact, facts, use_embeddings=use_embeddings
                )
                if result is None:
                    continue

                # γ-5 — optional LLM paraphrase
                if paraphrase_fn is not None:
                    rephrased = paraphrase_fn(
                        result["question_text"], result["options"]
                    )
                    if rephrased:
                        result["question_text"] = rephrased

                if dry_run:
                    click.echo(
                        f"[DRY-RUN] {result['_template_id']} | "
                        f"{result['question_type']} L{result['difficulty']} | "
                        f"{result['question_text'][:80]}"
                    )
                    if result["question_type"] == "multiple_choice":
                        for opt in result["options"]:
                            mark = "*" if opt["id"] == result["correct_answer"] else " "
                            click.echo(f"          {mark} {opt['id']}. {opt['text']}")
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
                    "llm_creativity": "none" if not paraphrase_fn else "low",
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
    click.echo(
        f"{'ID':<22} {'Domain':<18} {'Type':<18} {'Diff':<6} {'Wt':<5} {'Var':<4} Pattern"
    )
    click.echo("-" * 130)
    for t in TEMPLATES:
        if difficulty_filter and difficulty_filter not in t["difficulty_range"]:
            continue
        diff = ",".join(t["difficulty_range"])
        wt = t.get("selection_weight", 1.0)
        n_var = len(t.get("patterns") or [])
        first = (t.get("patterns") or [""])[0]
        click.echo(
            f"{t['id']:<22} {t['domain']:<18} {t['question_type']:<18} "
            f"L{diff:<5} {wt:<5} {n_var:<4} {first[:60]}"
        )
    click.echo(f"\nTotal templates: {len(TEMPLATES)}")
    total_variants = sum(len(t.get("patterns") or []) for t in TEMPLATES)
    click.echo(f"Total phrasing variants: {total_variants}")
    by_domain: dict[str, int] = {}
    for t in TEMPLATES:
        by_domain[t["domain"]] = by_domain.get(t["domain"], 0) + 1
    for dom, cnt in sorted(by_domain.items()):
        click.echo(f"  {dom}: {cnt}")


def _do_validate():
    """Quality report on template generation capability."""
    click.echo("Template Generator Validation Report (v2 overhaul)")
    click.echo("=" * 60)

    by_domain: dict[str, list[dict]] = {}
    for t in TEMPLATES:
        by_domain.setdefault(t["domain"], []).append(t)

    total_variants = sum(len(t.get("patterns") or []) for t in TEMPLATES)
    click.echo(f"\nTotal templates: {len(TEMPLATES)}")
    click.echo(f"Total phrasing variants: {total_variants}")
    fact_specific = sum(1 for t in TEMPLATES if t.get("requires_fact_specific"))
    click.echo(f"Fact-specific templates: {fact_specific}/{len(TEMPLATES)}")

    click.echo("\nTemplates per domain:")
    for dom in DOMAINS:
        tmpls = by_domain.get(dom, [])
        click.echo(f"  {dom}: {len(tmpls)}")

    click.echo("\nFact matching analysis (sample):")
    zero_match_templates: list[str] = []
    for dom in DOMAINS:
        facts = sample_facts(dom, count=200)
        if not facts:
            click.echo(f"  {dom}: no facts in DB")
            continue

        for template in by_domain.get(dom, []):
            matching = find_matching_facts(template, facts)
            if not matching:
                zero_match_templates.append(template["id"])
                click.echo(f"  {template['id']}: 0 matching facts")
                continue
            click.echo(
                f"  {template['id']}: {len(matching)} matching facts"
            )

    click.echo("\nExisting template questions in DB:")
    total = get_question_count(generator="template_only", method="template", status=None)
    click.echo(f"  Total: {total}")
    for dom in DOMAINS:
        cnt = get_question_count(
            domain=dom, generator="template_only", method="template", status=None
        )
        if cnt > 0:
            click.echo(f"  {dom}: {cnt}")

    click.echo("\nSummary:")
    click.echo(f"  Total templates: {len(TEMPLATES)}")
    click.echo(f"  Templates with zero matching facts: {len(zero_match_templates)}")
    if zero_match_templates:
        click.echo(f"  Zero-match IDs: {', '.join(zero_match_templates)}")


if __name__ == "__main__":
    main()
