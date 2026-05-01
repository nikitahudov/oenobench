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

  * γ-5 LLM paraphrase post-pass: **default ON in v2.2** — each output is
    wrapped through ``_template_paraphrase.paraphrase_question_text`` (Gemini
    via OpenRouter) for anti-detectability. Use ``--no-paraphrase`` to disable
    for debug. A4 audit showed templates were 96% detectable pre-paraphrase;
    post-paraphrase drops to <80%.

Usage:
    python -m src.generators.template_generator --all
    python -m src.generators.template_generator --domain wine_regions --count 50
    python -m src.generators.template_generator --dry-run --count 5
    python -m src.generators.template_generator --list
    python -m src.generators.template_generator --validate
    python -m src.generators.template_generator --test-run
    python -m src.generators.template_generator --domain wine_regions --count 5 --test-run
    python -m src.generators.template_generator --domain wine_regions --count 5 --no-paraphrase  # debug only
"""

from __future__ import annotations

import hashlib
import os
import random
import re
from datetime import datetime
from functools import lru_cache
from pathlib import Path

import click
from loguru import logger

from src.generators._fact_sampler import DOMAIN_TARGETS, _classify_wine_category, sample_facts
from src.generators._id_generator import mint_question_id
from src.generators._question_db import (
    delete_questions_by_ids,
    get_question_count,
    get_used_fact_ids,
    insert_question_gated,
)
from src.qa._attempted_facts import (
    get_attempted_fact_ids,
    register_attempted_fact_ids,
)
from src.utils.db import get_pg

# Strategy name for the cross-pass attempted-fact-ID registry. Must match
# the key used in ``src.qa._corpus.STRATEGY_MODULES``.
_STRATEGY_NAME = "template"

# ─── Phase 2g.16 — Lever 1: wine-category distractor filter counter ──────────
#
# Tracks how many candidates were rejected from distractor pools because
# they belonged to a different wine category than the correct answer.
_CATEGORY_FILTERED_COUNT: int = 0


def get_category_filtered_count() -> int:
    """Return how many distractor candidates were rejected by category filter."""
    return _CATEGORY_FILTERED_COUNT


def reset_category_filtered_count() -> None:
    """Reset the category-filter counter (used in tests)."""
    global _CATEGORY_FILTERED_COUNT
    _CATEGORY_FILTERED_COUNT = 0


# ─── Phase 2g.16 — Lever 4: paraphrase success/failure counters ───────────────
#
# Tracks γ-5 paraphrase outcomes per process / CLI invocation so the run
# report can surface the success rate without parsing logs.
_PARAPHRASE_OK_COUNT: int = 0
_PARAPHRASE_FAIL_COUNT: int = 0


def get_paraphrase_stats() -> dict[str, int]:
    """Return a dict with keys 'ok' and 'fail' for γ-5 paraphrase outcomes."""
    return {"ok": _PARAPHRASE_OK_COUNT, "fail": _PARAPHRASE_FAIL_COUNT}


def reset_paraphrase_stats() -> None:
    """Reset paraphrase counters (used in tests and repeated CLI invocations)."""
    global _PARAPHRASE_OK_COUNT, _PARAPHRASE_FAIL_COUNT
    _PARAPHRASE_OK_COUNT = 0
    _PARAPHRASE_FAIL_COUNT = 0


# ─── Logging setup ────────────────────────────────────────────────────────────

LOG_DIR = Path("data/logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)

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

# ─── v2.2 fix #8a — Template inventory purge (2026-04-20) ──────────────────
#
# Gold-v2 human review showed template strategy clean-passed 0/12 on all 8
# rubrics. Root causes R1-R2 (superlative/identity templates producing
# unverifiable or world-knowledge-solvable questions) were traced to these
# templates, which have been DELETED in this revision:
#
#   T-REG-COUNTRY-01        — "Which country is {region} in?" (world-knowledge)
#   T-REG-GRAPE-01          — "primary grape" (superlative, unverifiable)
#                              REPLACED by T-REG-AUTH-GRAPE-01 (authorised-list)
#   T-REG-STYLE-01          — "primarily known for" (superlative)
#   T-REG-NEIGHBOR-01       — "borders or is near" (unverifiable from 1 fact)
#   T-GRP-REGION-01         — "most strongly associated with" (superlative)
#                              REPLACED by T-GRP-AUTH-APPELLATION-01
#   T-GRP-ORIGIN-01         — "country of origin" (world-knowledge, contested)
#   T-PRD-GRAPE-01          — "flagship grape of" (superlative, unverifiable)
#   T-PRD-COUNTRY-01        — "country of X producer" (world-knowledge)
#   T-BIZ-EXPORT-01         — "largest export market" (superlative, no fact basis)
#
# Surviving templates: 38 + 2 rewrites = 40. All now carry
# `verifiable_from_single_fact: True`.
#
TEMPLATES: list[dict] = [
    # ── wine_regions ─────────────────────────────────────────────────────
    # T-REG-AUTH-GRAPE-01 — v2.2 fix #8a rewrite of T-REG-GRAPE-01.
    # Asks about authorised grapes (factually verifiable from a fact that
    # lists permitted varieties), NOT which grape is "primary" (superlative).
    {
        "id": "T-REG-AUTH-GRAPE-01",
        "patterns": [
            "Which of the following grapes is authorised in {appellation}?",
            "Which grape variety is permitted for use in {appellation}?",
            "Identify a grape authorised for production in {appellation}.",
            "Name a grape variety approved for {appellation} wines.",
            "Under {appellation} regulations, which grape is authorised?",
        ],
        "domain": "wine_regions",
        "difficulty_range": ["2"],
        "cognitive_dim": "recall",
        "question_type": "multiple_choice",
        "correct_field": "grape",
        "distractor_strategy": "same_type",
        "required_entities": ["grape", "appellation"],
        "explanation_template": "{grape} is an authorised variety in {appellation}.",
        "requires_fact_specific": True,
        "verifiable_from_single_fact": True,
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
    # T-REG-TF-COUNTRY-01 deleted (v2.2 fix #8a) — region→country TF
    # questions are world-knowledge-solvable; gold-v2 WB-REG-0096-L1
    # ("Leelanau in US") failed needs_source at L1.
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
    # T-REG-STYLE-01 deleted (v2.2 fix #8a) — superlative "primarily known for"
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
    # T-REG-NEIGHBOR-01 deleted (v2.2 fix #8a) — "borders or is near" can't
    # be verified from a single fact (requires knowing ALL neighbors).
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
    # ── grape_varieties ──────────────────────────────────────────────────
    # T-GRP-AUTH-APPELLATION-01 — v2.2 fix #8a rewrite of T-GRP-REGION-01.
    # Asks which appellation authorises a grape (verifiable from one fact),
    # not which region is "most associated with" the grape (superlative).
    {
        "id": "T-GRP-AUTH-APPELLATION-01",
        "patterns": [
            "Which of the following appellations authorises {grape} in its wines?",
            "Which wine appellation permits {grape}?",
            "Identify an appellation that authorises {grape}.",
            "Name an appellation in which {grape} is permitted.",
            "In which of these appellations is {grape} authorised?",
        ],
        "domain": "grape_varieties",
        "difficulty_range": ["2"],
        "cognitive_dim": "recall",
        "question_type": "multiple_choice",
        "correct_field": "appellation",
        "distractor_strategy": "same_type",
        "required_entities": ["grape", "appellation"],
        "explanation_template": "{grape} is an authorised variety in {appellation}.",
        "requires_fact_specific": True,
        "verifiable_from_single_fact": True,
        "selection_weight": 1.0,
    },
    # T-GRP-COLOR-01 + T-GRP-TF-COLOR-01 deleted (v2.2 fix #8a) — grape→wine
    # colour is world-knowledge for any famous grape (Pinot Noir → red, etc.)
    # and the colour is inherent to the grape. These templates over-produced
    # L1 recall that every LLM trivially solves closed-book.
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
    # T-GRP-ORIGIN-01 deleted (v2.2 fix #8a) — country-of-origin is both
    # world-knowledge (e.g. Blaufränkisch → Austria is textbook) AND
    # contested for many grapes (parentage debates). The fact "grape X is
    # grown in country Y" does NOT establish Y as the origin.
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
    # T-PRD-GRAPE-01 deleted (v2.2 fix #8a) — "flagship grape" / "most
    # associated" is a superlative that requires global ranking, not
    # provable from a single fact.
    # T-PRD-COUNTRY-01 deleted (v2.2 fix #8a) — producer→country is too
    # world-knowledge-solvable (Château X → France, Penfolds → Australia).
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
    # T-BIZ-EXPORT-01 deleted (v2.2 fix #8a) — "largest export market" is
    # superlative and rarely reducible to a single fact's ranking.

    # ════════════════════════════════════════════════════════════════════
    # v2.3 Phase F fix #15 — Registry expansion: comprehension + application
    # ════════════════════════════════════════════════════════════════════
    # Gold-v3 audit surfaced 100% `cognitive_dim="recall"` in production.
    # The expansion below adds 8 `comprehension` templates (require inferring
    # a non-name attribute from the fact's entities) and 4 `application`
    # templates (require applying the fact's rule to a novel scenario).
    #
    # Every new template:
    #   * has `requires_fact_specific=True` and `verifiable_from_single_fact=True`
    #   * has `selection_weight >= 1.0`
    #   * has 4-6 paraphrase variants (γ-4 requirement)
    #   * uses only entity types that actually occur in the fact DB: region,
    #     country, grape, producer, ava, appellation, state, county, pest_disease,
    #     technique, process, compound, wine_style. No `soil`/`climate`/`aroma`
    #     entries since those types are not present in the fact-base
    #     (verified via SELECT count(*) FROM facts WHERE entities @> '[{"type":"soil"}]'::jsonb).
    #
    # Comprehension templates (8) — inference not pure lookup
    # ──────────────────────────────────────────────────────

    # T-REG-COMP-COUNTRY-01 — region→country. Requires reading the fact to
    # locate the country since regions (e.g. "Barolo", "Piemonte") don't
    # wear the country name on their surface. Comprehension because the
    # student must connect region context to national boundary.
    {
        "id": "T-REG-COMP-COUNTRY-01",
        "patterns": [
            "Based on the fact, in which country is the {region} wine region located?",
            "According to the source fact, which country hosts the {region} wine region?",
            "Per the fact, the {region} wine region is situated in which country?",
            "The fact places the {region} wine region in which country?",
            "Given the fact, in which country would a traveller find the {region} wine region?",
        ],
        "domain": "wine_regions",
        "difficulty_range": ["2", "3"],
        "cognitive_dim": "comprehension",
        "question_type": "multiple_choice",
        "correct_field": "country",
        "distractor_strategy": "same_type",
        "required_entities": ["region", "country"],
        "explanation_template": "The fact locates {region} in {country}.",
        "requires_fact_specific": True,
        "verifiable_from_single_fact": True,
        "selection_weight": 1.1,
    },
    # T-REG-COMP-AVA-STATE-01 — AVA→state. 261 matching facts; requires
    # reading the fact to pin the AVA to a US state.
    {
        "id": "T-REG-COMP-AVA-STATE-01",
        "patterns": [
            "According to the fact, in which US state is the {ava} AVA located?",
            "Based on the source fact, the {ava} AVA is found in which state?",
            "Per the fact, which state hosts the {ava} AVA?",
            "The fact assigns the {ava} AVA to which US state?",
            "Given the fact, in which state would a grower registering under the {ava} AVA be operating?",
        ],
        "domain": "wine_regions",
        "difficulty_range": ["2", "3"],
        "cognitive_dim": "comprehension",
        "question_type": "multiple_choice",
        "correct_field": "state",
        "distractor_strategy": "same_type",
        "required_entities": ["ava", "state"],
        "explanation_template": "The {ava} AVA is located in {state}.",
        "requires_fact_specific": True,
        "verifiable_from_single_fact": True,
        "selection_weight": 1.2,
    },
    # T-REG-COMP-AVA-COUNTY-01 — AVA→county. Parallel to state-level but
    # county is finer-grained; 288 matching facts.
    {
        "id": "T-REG-COMP-AVA-COUNTY-01",
        "patterns": [
            "Based on the fact, in which county is the {ava} AVA located?",
            "According to the source fact, the {ava} AVA is situated in which county?",
            "Per the fact, which county contains the {ava} AVA?",
            "The fact assigns the {ava} AVA to which county?",
            "Given the fact, the {ava} AVA falls within which county?",
        ],
        "domain": "wine_regions",
        "difficulty_range": ["3", "4"],
        "cognitive_dim": "comprehension",
        "question_type": "multiple_choice",
        "correct_field": "county",
        "distractor_strategy": "same_type",
        "required_entities": ["ava", "county"],
        "explanation_template": "The {ava} AVA lies within {county}.",
        "requires_fact_specific": True,
        "verifiable_from_single_fact": True,
        "selection_weight": 1.2,
    },
    # T-GRP-COMP-COUNTRY-01 — grape→country. 2458 matching facts. Comp
    # because the fact usually gives the region; country is inferable from
    # the region context the fact supplies.
    {
        "id": "T-GRP-COMP-COUNTRY-01",
        "patterns": [
            "According to the fact, in which country is {grape} described as being grown?",
            "Based on the source fact, {grape} is cultivated in which country?",
            "Per the fact, which country hosts cultivation of {grape}?",
            "The fact indicates that {grape} is grown in which country?",
            "Given the fact, a producer working with {grape} would be operating in which country?",
        ],
        "domain": "grape_varieties",
        "difficulty_range": ["2", "3"],
        "cognitive_dim": "comprehension",
        "question_type": "multiple_choice",
        "correct_field": "country",
        "distractor_strategy": "same_type",
        "required_entities": ["grape", "country"],
        "explanation_template": "The fact shows {grape} grown in {country}.",
        "requires_fact_specific": True,
        "verifiable_from_single_fact": True,
        "selection_weight": 1.1,
    },
    # T-GRP-COMP-REGION-01 — grape→region. Core variant: many facts in the
    # corpus follow "X is grown in Y region" or "Y region permits X".
    {
        "id": "T-GRP-COMP-REGION-01",
        "patterns": [
            "According to the fact, in which wine region is {grape} cultivated?",
            "Based on the source fact, {grape} is grown in which wine region?",
            "Per the fact, which wine region is linked to the cultivation of {grape}?",
            "The fact indicates cultivation of {grape} in which region?",
            "Given the fact, which region is a documented home for {grape}?",
        ],
        "domain": "grape_varieties",
        "difficulty_range": ["2", "3"],
        "cognitive_dim": "comprehension",
        "question_type": "multiple_choice",
        "correct_field": "region",
        "distractor_strategy": "same_type",
        "required_entities": ["grape", "region"],
        "explanation_template": "The fact documents {grape} cultivation in {region}.",
        "requires_fact_specific": True,
        "verifiable_from_single_fact": True,
        "selection_weight": 1.1,
    },
    # T-PRD-COMP-COUNTRY-01 — producer→country. 574 matching facts.
    {
        "id": "T-PRD-COMP-COUNTRY-01",
        "patterns": [
            "Based on the fact, in which country is the producer {producer} based?",
            "According to the source fact, {producer} operates in which country?",
            "Per the fact, the wine estate {producer} is located in which country?",
            "The fact places {producer} in which country?",
            "Given the fact, an importer ordering direct from {producer} would be sourcing from which country?",
        ],
        "domain": "producers",
        "difficulty_range": ["2", "3"],
        "cognitive_dim": "comprehension",
        "question_type": "multiple_choice",
        "correct_field": "country",
        "distractor_strategy": "same_type",
        "required_entities": ["producer", "country"],
        "explanation_template": "The fact identifies {producer} as based in {country}.",
        "requires_fact_specific": True,
        "verifiable_from_single_fact": True,
        "selection_weight": 1.1,
    },
    # T-GRP-COMP-APPELLATION-01 — appellation context from grape. 230 matching
    # facts. A variant of T-GRP-AUTH-APPELLATION-01 but comprehension-framed:
    # the student is asked to read the fact's listing and identify an
    # appellation that includes the grape.
    {
        "id": "T-GRP-COMP-APPELLATION-01",
        "patterns": [
            "According to the fact, which appellation is described as permitting {grape}?",
            "Based on the source fact, {grape} is an authorised variety in which appellation?",
            "Per the fact, the appellation that includes {grape} in its permitted list is which of the following?",
            "The fact identifies {grape} among the permitted varieties of which appellation?",
            "Given the fact, a bottle of {grape}-based wine labelled under the listed appellation would come from which of these?",
        ],
        "domain": "grape_varieties",
        "difficulty_range": ["2", "3"],
        "cognitive_dim": "comprehension",
        "question_type": "multiple_choice",
        "correct_field": "appellation",
        "distractor_strategy": "same_type",
        "required_entities": ["grape", "appellation"],
        "explanation_template": "The fact lists {grape} as permitted in {appellation}.",
        "requires_fact_specific": True,
        "verifiable_from_single_fact": True,
        "selection_weight": 1.1,
    },
    # T-VIT-COMP-PEST-GRAPE-01 — pest_disease→grape. 6 matching facts;
    # small but distinct cognitive dimension. Comprehension because the
    # fact typically names a pest alongside a grape without explicitly
    # saying "this grape suffers from that pest".
    {
        "id": "T-VIT-COMP-PEST-GRAPE-01",
        "patterns": [
            "According to the fact, which grape variety is cited alongside {pest_disease}?",
            "Based on the source fact, {pest_disease} is discussed in connection with which grape?",
            "Per the fact, which grape is noted as relevant to a {pest_disease} observation?",
            "The fact associates {pest_disease} with which grape variety?",
            "Given the fact, an integrated-pest-management plan targeting {pest_disease} would concern which grape?",
        ],
        "domain": "viticulture",
        "difficulty_range": ["3", "4"],
        "cognitive_dim": "comprehension",
        "question_type": "multiple_choice",
        "correct_field": "grape",
        "distractor_strategy": "same_type",
        "required_entities": ["grape", "pest_disease"],
        "explanation_template": "The fact cites {grape} alongside {pest_disease}.",
        "requires_fact_specific": True,
        "verifiable_from_single_fact": True,
        "selection_weight": 1.0,
    },

    # Application templates (4) — apply fact rule to novel scenario
    # ───────────────────────────────────────────────────────────

    # T-REG-APP-VARIETAL-LABEL-01 — application scenario: a winemaker is
    # considering labelling under an appellation; student must read the
    # fact's authorised-grape list and pick the matching variety that
    # would satisfy the rule. Uses `{grape, appellation}`.
    {
        "id": "T-REG-APP-VARIETAL-LABEL-01",
        "patterns": [
            "A winemaker plans to label a varietal wine under the {appellation} AOC. Per the fact, which grape would satisfy the authorised-variety rule?",
            "A producer intends to release a varietal wine as {appellation}. Based on the fact, which grape variety is permitted for this release?",
            "An importer wishes to source a single-varietal {appellation} wine. Per the fact, which grape should they look for on the label?",
            "A regulator is auditing labelling under {appellation}. Which grape, per the fact, is among the permitted varieties for this appellation?",
            "A sommelier is assembling a flight of {appellation} wines and needs to include a permitted varietal. According to the fact, which grape qualifies?",
        ],
        "domain": "wine_regions",
        "difficulty_range": ["2", "3"],
        "cognitive_dim": "application",
        "question_type": "multiple_choice",
        "correct_field": "grape",
        "distractor_strategy": "same_type",
        "required_entities": ["grape", "appellation"],
        "explanation_template": "The fact shows {grape} authorised under {appellation}.",
        "requires_fact_specific": True,
        "verifiable_from_single_fact": True,
        "selection_weight": 1.1,
    },
    # T-GRP-APP-REGION-PLANT-01 — application: a vigneron considers where
    # to plant a variety; answer comes from the fact's documented region.
    # Uses `{grape, region}`.
    # Phase 2g.16 Lever 3: changed distractor_strategy from "same_type" to
    # "same_country_same_category" so distractors are other regions in the
    # same country and same wine category — preventing cross-country leaks
    # (e.g. Portuguese parishes as distractors for Spanish DOs).
    {
        "id": "T-GRP-APP-REGION-PLANT-01",
        "patterns": [
            "A vigneron is considering planting {grape} in a region with an established track record. Per the fact, which region is documented as a home for this variety?",
            "An advisor is recommending a region for a new {grape} planting. Based on the fact, which region's cultivation of this grape is documented?",
            "A wine merchant looking for authentic {grape}-based wines consults the fact. Which region should they target?",
            "A new producer seeks advice on a proven region for {grape}. According to the fact, which wine region fits?",
            "A viticulture consultant maps established sites for {grape}. Per the fact, which region is listed?",
        ],
        "domain": "grape_varieties",
        "difficulty_range": ["2", "3"],
        "cognitive_dim": "application",
        "question_type": "multiple_choice",
        "correct_field": "region",
        "distractor_strategy": "same_country_same_category",
        "required_entities": ["grape", "region"],
        "explanation_template": "The fact documents {region} as a home for {grape}.",
        "requires_fact_specific": True,
        "verifiable_from_single_fact": True,
        "selection_weight": 1.1,
    },
    # T-REG-APP-AVA-SOURCING-01 — application: an importer needs to verify
    # AVA→state for labelling or sourcing compliance. Uses `{ava, state}`.
    {
        "id": "T-REG-APP-AVA-SOURCING-01",
        "patterns": [
            "An importer purchasing {ava} AVA wines is confirming the US state of origin for customs paperwork. Per the fact, which state should appear on the form?",
            "A buyer is routing a shipment of {ava} AVA wine. Based on the fact, which US state is the origin?",
            "A sommelier updating their map of US AVAs must assign {ava} to a state. According to the fact, which state is it?",
            "A retailer lists {ava} AVA wines on its website under state. Per the fact, which state should be used?",
            "A critic reviewing {ava} AVA wines wants to verify the state of origin. The fact identifies which state?",
        ],
        "domain": "wine_regions",
        "difficulty_range": ["2", "3"],
        "cognitive_dim": "application",
        "question_type": "multiple_choice",
        "correct_field": "state",
        "distractor_strategy": "same_type",
        "required_entities": ["ava", "state"],
        "explanation_template": "The {ava} AVA is in {state}, per the fact.",
        "requires_fact_specific": True,
        "verifiable_from_single_fact": True,
        "selection_weight": 1.1,
    },
    # T-PRD-APP-SOURCING-01 — application: an importer/sommelier needs the
    # producer→country mapping for sourcing logistics. Uses `{producer, country}`.
    {
        "id": "T-PRD-APP-SOURCING-01",
        "patterns": [
            "A buyer plans to import wines directly from the estate {producer}. Per the fact, which country's export procedures should they follow?",
            "A sommelier adding {producer} to a by-country wine list consults the fact. Which country should the entry list?",
            "A retailer preparing a country-of-origin label for {producer} wines checks the fact. Which country applies?",
            "An importer drafting a purchase order for {producer} needs the country of origin. Per the fact, which country is it?",
            "A wine writer placing {producer} on a country-by-country map turns to the fact. Which country is specified?",
        ],
        "domain": "producers",
        "difficulty_range": ["2", "3"],
        "cognitive_dim": "application",
        "question_type": "multiple_choice",
        "correct_field": "country",
        "distractor_strategy": "same_type",
        "required_entities": ["producer", "country"],
        "explanation_template": "The fact identifies {producer} as operating in {country}.",
        "requires_fact_specific": True,
        "verifiable_from_single_fact": True,
        "selection_weight": 1.1,
    },
]

# v2.2 fix #8a — set `verifiable_from_single_fact: True` as the default on
# every surviving template. After the purge all templates in the list are
# fact-specific (the superlative/identity ones were deleted, not kept with
# low weights as in γ-2). Individual templates can still override by setting
# the field explicitly in their dict literal.
for _t in TEMPLATES:
    _t.setdefault("verifiable_from_single_fact", True)
del _t  # don't leak loop var into module namespace

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


# v2.2 fix #8c — Distractor-pool hardening.
#
# Gold-v2 showed "region" pools contaminated with country-level concepts:
# "In which wine region is Force Majeure Vineyards located?" got distractors
# {Georgian wine, Canadian wine, Italian wine} because those appear tagged
# as `region` in some facts. A grape pool got "Verdejo" as a region. The
# root cause: the fact-base's entity_type labels are scraper-heterogeneous.
#
# The hardened pool:
#   1. Whitelist per correct_field — only accept entities tagged with an
#      allowed type for that field.
#   2. Drop candidates that pattern-match as bare country names (iconic
#      country sentinel from `_template_validators`).
#   3. Shape-homogeneity: the correct value and distractors must share
#      token shape (multi-word vs single token; hyphen vs no hyphen) so we
#      don't put a country-style single-word in an appellation-style pool.
#   4. Minimum pool size 20 (was 8) — skip the template instance if smaller.

_FIELD_ALLOWED_ENTITY_TYPES: dict[str, frozenset[str]] = {
    "country":          frozenset({"country"}),
    "region":           frozenset({"region"}),
    "appellation":      frozenset({"appellation"}),
    "subregion":        frozenset({"subregion", "region"}),
    "neighbor_region":  frozenset({"region"}),
    "grape":            frozenset({"grape"}),
    "parent_grape":     frozenset({"grape", "parent_grape"}),
    "flagship_grape":   frozenset({"grape"}),
    "producer":         frozenset({"producer"}),
    "soil":             frozenset({"soil"}),
    "climate":          frozenset({"climate"}),
    "wine_style":       frozenset({"wine_style"}),
    "classification":   frozenset({"classification"}),
    "technique":        frozenset({"technique"}),
    "process":          frozenset({"process"}),
    "regulatory_body":  frozenset({"regulatory_body"}),
    "market":           frozenset({"market", "country"}),
}

# Fields where drawing a bare country name as a distractor is always wrong.
_FIELDS_REJECTING_COUNTRY_SHAPE: frozenset[str] = frozenset({
    "region", "appellation", "subregion", "neighbor_region",
})

_MIN_POOL_SIZE_V22 = 20


def _same_shape(correct: str, candidate: str) -> bool:
    """Return True if both strings share a rough shape class.

    Classes:
      * multi_word  — 2+ space-separated tokens or contains a hyphen
      * single_word — one token, no hyphen
    """
    def _cls(s: str) -> str:
        s = s.strip()
        if not s:
            return ""
        if " " in s or "-" in s:
            return "multi_word"
        return "single_word"
    return _cls(correct) == _cls(candidate)


def _candidate_pool_for_type(
    entity_type: str,
    correct_value: str,
    facts: list[dict],
    source_fact_text: str = "",
    template_id: str = "",
) -> list[str]:
    """v2.2 fix #8c — hardened candidate pool for distractor sampling.

    Applies: type whitelist, country-sentinel, shape-homogeneity, min size 20.
    Phase 2g.16 Lever 1: wine-category coherence filter for category-sensitive
    fields (region, producer, appellation, grape). Candidates whose source fact
    text classifies to a different wine category than the correct answer are
    rejected. Falls back to no-category constraint if the correct answer is
    unclassifiable or if post-filter pool drops below _MIN_POOL_SIZE_V22.

    Returns [] if the hardened pool is too small; caller skips the template.
    """
    global _CATEGORY_FILTERED_COUNT
    from src.generators._template_validators import is_iconic_bare_country

    allowed = _FIELD_ALLOWED_ENTITY_TYPES.get(entity_type, frozenset({entity_type}))
    reject_countries = entity_type in _FIELDS_REJECTING_COUNTRY_SHAPE
    seen: set[str] = set()
    out: list[str] = []
    correct_lower = correct_value.lower()

    # Phase 2g.16 Lever 1: determine whether to apply category coherence.
    # Only applies to fields where wine category coherence is meaningful.
    _CATEGORY_SENSITIVE_FIELDS = frozenset({"region", "producer", "appellation", "grape"})
    apply_category_filter = entity_type in _CATEGORY_SENSITIVE_FIELDS
    correct_category: str | None = None
    if apply_category_filter and source_fact_text:
        correct_category = _classify_wine_category(source_fact_text)
        # If the correct answer is unclassifiable, skip category constraint.
        if correct_category is None:
            apply_category_filter = False

    def _accept(val: str, etype: str) -> bool:
        # Type gate: candidate must be tagged with an allowed entity_type.
        if etype and etype not in allowed:
            return False
        # Identity-skip.
        if val.lower() == correct_lower:
            return False
        # Country-sentinel: drop any bare country or "X wine" pseudo-region.
        if reject_countries and is_iconic_bare_country(val):
            return False
        # Shape homogeneity vs the correct value.
        if not _same_shape(correct_value, val):
            return False
        return True

    def _category_accept(candidate_fact_text: str) -> bool:
        """Return True if the candidate's wine category matches the correct answer."""
        if not apply_category_filter:
            return True
        cand_cat = _classify_wine_category(candidate_fact_text)
        if cand_cat is None:
            # Unclassifiable candidates are allowed through (permissive).
            return True
        return cand_cat == correct_category

    # In-memory pool first.
    for fact in facts:
        ents_map = _extract_entities(fact)  # type → first name
        val = ents_map.get(entity_type, "")
        if not val:
            continue
        if not _accept(val, entity_type):
            continue
        # Phase 2g.16 Lever 1: category coherence check.
        if apply_category_filter:
            cand_fact_text = fact.get("fact_text", "")
            if not _category_accept(cand_fact_text):
                _CATEGORY_FILTERED_COUNT += 1
                continue
        key = val.lower()
        if key not in seen:
            seen.add(key)
            out.append(val)

    # DB fallback when local pool is thin.
    # Note: DB fallback candidates have no source fact text available, so
    # category filter cannot apply to them — they pass through unchecked.
    if len(out) < _MIN_POOL_SIZE_V22 + 2:
        for cand in _global_candidates_for_type(entity_type):
            if not _accept(cand, entity_type):
                continue
            key = cand.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(cand)
            if len(out) >= 60:  # cap pool size to control embedding cost
                break

    # Phase 2g.16 Lever 1: if post-category-filter pool is too small, log and
    # fail closed so the caller skips this template instance.
    if len(out) < _MIN_POOL_SIZE_V22:
        if apply_category_filter and template_id:
            logger.info(
                "template distractor pool depleted by category filter | "
                "template={} | field={} | post_filter_size={}",
                template_id, entity_type, len(out),
            )
        return []
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


def _mention_band(entity_name: str) -> str:
    """Return the mention-count band name (used by the v2.2 fix #8d table)."""
    cnt = _entity_mention_count(entity_name)
    if cnt >= 100:
        return "high"
    if cnt >= 20:
        return "med"
    if cnt >= 5:
        return "low"
    return "very_low"


# ─── v2.2 fix #8d — Per-template difficulty calibration table ─────────────
#
# Seeded from gold-v2 difficulty_match=0 rows. Keys are (template_id, band).
# Values are the ground-truth difficulty the human reviewer wrote in the
# `notes` column. For combinations not listed, we fall back to the γ-3
# heuristic difficulty().
#
# gold-v2 evidence (selected):
#   WB-PRD-0087-L1 (Force Majeure, low mentions, T-PRD-TF-REGION-01)
#     labelled d=1, actual d=3 → ("T-PRD-TF-REGION-01", "low"): "3"
#   WB-PRD-0096-L2 (Burrowing Owl, low, T-PRD-TF-REGION-01)
#     labelled d=2, actual d=3 → same key ends up "3"
#   WB-PRD-0099-L3 (Château Margaux, high, T-PRD-REGION-01)
#     labelled d=3, actual d=1 → ("T-PRD-REGION-01", "high"): "1"
#   WB-REG-0090-L3 (Castel del Monte, high, T-REG-SUBREGION-01)
#     labelled d=3, actual d=2 → ("T-REG-SUBREGION-01", "high"): "2"

_DIFFICULTY_TABLE: dict[tuple[str, str], str] = {
    # Producer-in-region (famous → trivial, obscure → harder than γ-3)
    ("T-PRD-REGION-01", "high"):     "1",
    ("T-PRD-REGION-01", "med"):      "2",
    ("T-PRD-REGION-01", "low"):      "3",
    ("T-PRD-REGION-01", "very_low"): "4",
    ("T-PRD-TF-REGION-01", "high"): "2",
    ("T-PRD-TF-REGION-01", "med"):  "2",
    ("T-PRD-TF-REGION-01", "low"):  "3",
    ("T-PRD-TF-REGION-01", "very_low"): "3",
    # Region/appellation containment
    ("T-REG-SUBREGION-01", "high"): "2",
    ("T-REG-SUBREGION-01", "med"):  "2",
    ("T-REG-SUBREGION-01", "low"):  "3",
    # Classification / regulatory — inherently L3+
    ("T-REG-CLASS-01",  "high"): "3",
    ("T-REG-CLASS-01",  "med"):  "3",
    ("T-REG-CLASS-01",  "low"):  "4",
    ("T-REG-CLASS2-01", "high"): "3",
    ("T-REG-CLASS2-01", "med"):  "3",
    ("T-PRD-CLASS-01",  "high"): "3",
    ("T-PRD-CLASS-01",  "med"):  "3",
    # Rewritten authorised-list templates — L2 for well-known regions
    ("T-REG-AUTH-GRAPE-01", "high"):     "2",
    ("T-REG-AUTH-GRAPE-01", "low"):      "3",
    ("T-GRP-AUTH-APPELLATION-01", "high"): "2",
    ("T-GRP-AUTH-APPELLATION-01", "low"):  "3",
}


def calibrated_difficulty(template_id: str, entity_name: str) -> str:
    """v2.2 fix #8d — Look up difficulty in the per-template table; fall back
    to γ-3 mention-count heuristic when the combination is not listed."""
    band = _mention_band(entity_name)
    key = (template_id, band)
    if key in _DIFFICULTY_TABLE:
        return _DIFFICULTY_TABLE[key]
    return heuristic_difficulty(entity_name)


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


def _same_country_same_category_pool(
    correct_value: str,
    source_fact: dict,
    all_facts: list[dict],
) -> list[str]:
    """Phase 2g.16 Lever 3 — 'same_country_same_category' distractor pool.

    Returns region names from facts that share BOTH the country AND wine category
    of the source fact. Requires a pool of at least _MIN_POOL_SIZE_V22 to proceed;
    falls back to an unconstrained same-type pool if fewer candidates are found.

    Used exclusively by T-GRP-APP-REGION-PLANT-01 to prevent cross-country
    distractors (e.g. Portuguese parishes appearing for Spanish DOs).
    """
    # Extract country from source fact.
    source_ents = _extract_entities(source_fact)
    source_country = source_ents.get("country", "")
    source_fact_text = source_fact.get("fact_text", "")
    source_category = _classify_wine_category(source_fact_text)

    correct_lower = correct_value.lower()
    seen: set[str] = set()
    same_country_same_cat: list[str] = []
    same_country_only: list[str] = []

    for fact in all_facts:
        ents = _extract_entities(fact)
        region_val = ents.get("region", "")
        if not region_val or region_val.lower() == correct_lower:
            continue
        candidate_country = ents.get("country", "")
        if source_country and candidate_country != source_country:
            continue  # different country — skip regardless
        key = region_val.lower()
        if key in seen:
            continue
        seen.add(key)
        # Categorise this candidate.
        cand_fact_text = fact.get("fact_text", "")
        cand_category = _classify_wine_category(cand_fact_text)
        if source_category is not None and cand_category == source_category:
            same_country_same_cat.append(region_val)
        else:
            same_country_only.append(region_val)

    # Prefer strictly same-country + same-category.
    combined = same_country_same_cat + same_country_only
    if len(combined) >= _MIN_POOL_SIZE_V22:
        return combined

    # Fallback: unconstrained same-type pool.
    logger.debug(
        "same_country_same_category pool too small ({}) for correct_value={!r}; "
        "falling back to unconstrained same-type pool",
        len(combined), correct_value,
    )
    return _candidate_pool_for_type("region", correct_value, all_facts)


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

    # v2.2 fix #8b — source-faithfulness gate. Require the correct answer
    # (or its aliases) to appear literally in the linked source fact, and
    # require every content token of the filled explanation to be supported.
    source_fact_text = fact.get("fact_text") or ""
    from src.generators._template_validators import verify_answer_in_source_fact
    if not verify_answer_in_source_fact(
        correct_answer_text=correct_value,
        source_fact=source_fact_text,
        explanation_filled=explanation,
    ):
        logger.debug(
            f"Template {template['id']} REJECT source-faithfulness — "
            f"answer={correct_value!r} fact={source_fact_text[:80]!r}"
        )
        return None

    # v2.2 fix #8d — per-template difficulty calibration table (supersedes γ-3).
    difficulty = calibrated_difficulty(template["id"], correct_value)

    if question_type == "true_false":
        options = [{"id": "A", "text": "True"}, {"id": "B", "text": "False"}]
        correct_answer = "A"
        correct_answer_text = "True"
    elif question_type == "multiple_choice":
        # Phase 2g.16 Lever 3: dispatch on distractor_strategy.
        distractor_strategy = template.get("distractor_strategy", "same_type")
        if distractor_strategy == "same_country_same_category":
            candidate_pool = _same_country_same_category_pool(
                correct_value, fact, all_facts
            )
        else:
            candidate_pool = _candidate_pool_for_type(
                correct_field, correct_value, all_facts,
                source_fact_text=source_fact_text,
                template_id=template["id"],
            )
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


# ─── v2.3 fix #13 — Per-template diversity cap ────────────────────────────
#
# Gold-v3 + audit_pilot_v3 showed that `T-PRD-TF-REGION-01` held 28% of all
# 107 template questions in the DB and its paraphrase variants filled 100%
# of the 12 gold-v3 template slots. Only 11 of 38 templates ever fired.
#
# Remediation: a session-scoped counter caps any single `template_id` at
# 15% of the per-domain quota. When the cap is reached the template is
# excluded from the candidate list for subsequent picks. If the candidate
# list goes empty after exclusion we emit a `loguru.warning` and allow the
# capped template through anyway (throughput-safety fallback).
#
# The counter is kept on the module so callers (tests, CLI) can introspect
# it via :func:`get_template_id_counts` / :func:`reset_template_id_counts`.

_TEMPLATE_ID_COUNTS: dict[str, int] = {}
_TEMPLATE_CAP_FRACTION: float = 0.15


def get_template_id_counts() -> dict[str, int]:
    """Return a copy of the current per-template session counter (v2.3 fix #13)."""
    return dict(_TEMPLATE_ID_COUNTS)


def reset_template_id_counts() -> None:
    """Reset the per-template session counter. Used by CLI + tests."""
    _TEMPLATE_ID_COUNTS.clear()


def _increment_template_count(template_id: str) -> None:
    """Bump the session counter for ``template_id`` by one."""
    _TEMPLATE_ID_COUNTS[template_id] = _TEMPLATE_ID_COUNTS.get(template_id, 0) + 1


def _template_cap(domain_quota: int) -> int:
    """Return the integer per-template cap for a given per-domain quota.

    15% of the quota, rounded down but never less than 1 so cap logic
    still applies for tiny dry-runs (count=5).
    """
    cap = int(domain_quota * _TEMPLATE_CAP_FRACTION)
    return max(cap, 1)


def _templates_under_cap(
    candidate_templates: list[dict],
    domain_quota: int,
) -> list[dict]:
    """Filter out templates that have already hit the diversity cap."""
    cap = _template_cap(domain_quota)
    under = [
        t for t in candidate_templates
        if _TEMPLATE_ID_COUNTS.get(t["id"], 0) < cap
    ]
    return under


def generate_with_diversity_cap(
    domain: str,
    target: int,
    facts: list[dict],
    *,
    templates: list[dict] | None = None,
    use_embeddings: bool = False,
    allow_cap_overflow: bool = True,
) -> list[dict]:
    """Run the template-selection loop end-to-end with the v2.3 diversity cap.

    This is the programmatic equivalent of the selection + fill portion of
    the CLI's ``main()``, extracted so tests can drive it without network
    calls or DB writes. Returns the list of filled-question dicts (exactly
    what ``fill_template`` returns). Side-effect: updates
    :data:`_TEMPLATE_ID_COUNTS`.

    The cap is 15% of ``target`` (rounded down, minimum 1). Behavior when
    all templates hit the cap is controlled by ``allow_cap_overflow``:
      * ``True`` (default, matches CLI behavior) — a single warning is
        logged and the last-picked template continues past the cap so
        throughput doesn't crash.
      * ``False`` — generation stops cleanly at the cap; useful for tests
        that want strict cap enforcement.
    """
    if templates is None:
        templates = [t for t in TEMPLATES if t["domain"] == domain]
    if not templates:
        return []

    templates = _weighted_template_order(list(templates))
    cap = _template_cap(target)
    generated: list[dict] = []

    for template in templates:
        if len(generated) >= target:
            break
        if _TEMPLATE_ID_COUNTS.get(template["id"], 0) >= cap:
            remaining_under_cap = _templates_under_cap(
                [t for t in templates if t["id"] != template["id"]],
                target,
            )
            if remaining_under_cap:
                continue
            if not allow_cap_overflow:
                # Strict mode: every template is at cap — stop cleanly.
                logger.info(
                    f"All templates for domain={domain} at cap; stopping "
                    f"at {len(generated)}/{target} (strict mode)."
                )
                break
            logger.warning(
                f"All templates for domain={domain} at cap; "
                f"{template['id']} continuing past cap."
            )

        matching = find_matching_facts(template, facts)
        random.shuffle(matching)
        for fact in matching:
            if len(generated) >= target:
                break
            if _TEMPLATE_ID_COUNTS.get(template["id"], 0) >= cap:
                remaining_under_cap = _templates_under_cap(
                    [t for t in templates if t["id"] != template["id"]],
                    target,
                )
                if remaining_under_cap:
                    break
                if not allow_cap_overflow:
                    break
                # Single warning per template in the loop; don't re-log.

            result = fill_template(
                template, fact, facts, use_embeddings=use_embeddings
            )
            if result is None:
                continue
            _increment_template_count(result["_template_id"])
            generated.append(result)

    return generated


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
@click.option("--no-paraphrase", is_flag=True, help="Disable γ-5 LLM paraphrase post-pass (debug). Default: paraphrase ON.")
@click.option("--no-embeddings", is_flag=True, help="Disable γ-1 embedding distractors (debug)")
@click.option("--no-verify", is_flag=True, help="Disable v2.2 fix #8e mandatory Gemini answer-verification (debug).")
@click.option(
    "--per-country-cap",
    type=float,
    default=None,
    help=(
        "Per-call absolute country cap as a fraction in (0, 1]. "
        "When set, no single country may exceed ceil(cap * count) of "
        "the sampled facts. Default unset (no cap). Phase 2g.7 Team ε."
    ),
)
@click.option(
    "--circuit-breaker/--no-circuit-breaker",
    default=None,
    help=(
        "Phase 2g.10 (Team Golf B3): per-cell (per-domain) circuit breaker. "
        "Default OFF (env var OENOBENCH_CIRCUIT_BREAKER=1 also enables)."
    ),
)
def main(
    domain,
    count,
    difficulty,
    dry_run,
    test_run,
    validate,
    list_templates,
    run_all,
    no_paraphrase,
    no_embeddings,
    no_verify,
    per_country_cap,
    circuit_breaker,
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

    result = run_generate(
        domain=domain,
        count=count,
        difficulty=difficulty,
        dry_run=dry_run,
        no_paraphrase=no_paraphrase,
        no_embeddings=no_embeddings,
        no_verify=no_verify,
        per_country_cap=per_country_cap,
        run_all=run_all,
        circuit_breaker=circuit_breaker,
    )
    if test_run and result.get("inserted_uuids"):
        ids = result["inserted_uuids"]
        click.echo(f"Test run — cleaning up {len(ids)} questions")
        delete_questions_by_ids(ids)


def run_generate(
    *,
    domain: str | None = None,
    count: int = 10,
    difficulty: str | int | None = None,
    dry_run: bool = False,
    no_paraphrase: bool = False,
    no_embeddings: bool = False,
    no_verify: bool = False,
    per_country_cap: float | None = None,
    run_all: bool = False,
    # Accepted for API uniformity with other strategies; unused here.
    generator: str | None = None,
    circuit_breaker: bool | None = None,
) -> dict:
    """Run template generation. Returns stats dict.

    Phase 2g.10 (Team Delta A2): in-process callable. The click ``main()`` is
    a thin shim around this function. CLI-only modes (``--list``, ``--validate``,
    ``--test-run``) are handled in ``main()`` because they are user-interactive
    side effects, not part of the generation pipeline.

    Phase 2g.10 (Team Golf B3): when ``circuit_breaker`` is True or the
    ``OENOBENCH_CIRCUIT_BREAKER`` env var is "1", each per-domain cell
    inside this call gets its own ``CellTracker``; abandoned-cell unused
    budget reallocates to the next domain (capped at 2× original).
    """
    from src.qa._corpus import _circuit_breaker_enabled
    enabled = circuit_breaker if circuit_breaker is not None else _circuit_breaker_enabled()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    handler_id = logger.add(
        LOG_DIR / f"template_generator_{timestamp}.log", rotation="50 MB",
    )
    try:
        return _run_generate_body(
            domain=domain, count=count,
            difficulty=str(difficulty) if difficulty is not None else None,
            dry_run=dry_run, no_paraphrase=no_paraphrase,
            no_embeddings=no_embeddings, no_verify=no_verify,
            per_country_cap=per_country_cap, run_all=run_all,
            circuit_breaker=enabled,
        )
    finally:
        try:
            logger.remove(handler_id)
        except ValueError:
            pass


def _run_generate_body(
    *,
    domain: str | None,
    count: int,
    difficulty: str | None,
    dry_run: bool,
    no_paraphrase: bool,
    no_embeddings: bool,
    no_verify: bool,
    per_country_cap: float | None,
    run_all: bool,
    circuit_breaker: bool = False,
) -> dict:
    """Inner generation loop, sans logger-handler setup."""
    if count <= 0 and not run_all:
        return {
            "generated": 0, "skipped_parse": 0, "skipped_dup": 0,
            "skipped_sample": 0, "relabeled_l1": 0, "rejected_overflow": 0,
            "inserted_uuids": [],
        }

    domains = [domain] if domain else DOMAINS
    if run_all:
        domains = DOMAINS

    # Phase 2g.13: seed used_facts with cross-pass attempted IDs so the
    # multi-pass loop's previous passes' attempted facts are excluded from
    # the per-domain bulk sample.
    used_facts = get_used_fact_ids() if not dry_run else set()
    if not dry_run:
        used_facts = used_facts | get_attempted_fact_ids(_STRATEGY_NAME)
    total_generated = 0
    total_relabeled_l1 = 0
    total_rejected_overflow = 0
    generated_ids: list[str] = []

    # v2.2 fix #1 — γ-5 LLM paraphrase post-pass is DEFAULT ON (was opt-in via --paraphrase).
    # A4 audit showed templates at 96% detectability; γ-5 drops that to <80%. Default-on fixes
    # the root issue. Use --no-paraphrase for debug.
    paraphrase_fn = None
    if not no_paraphrase:
        try:
            from src.generators._template_paraphrase import paraphrase_question_text
            paraphrase_fn = paraphrase_question_text
            logger.info("γ-5 LLM paraphrase post-pass ENABLED (Gemini) — default ON in v2.2")
        except Exception as e:
            logger.error(f"Paraphrase module unavailable, continuing without it: {e}")
    else:
        logger.info("γ-5 LLM paraphrase post-pass DISABLED (--no-paraphrase)")

    use_embeddings = not no_embeddings

    # v2.3 fix #13 — reset the per-template session counter per CLI invocation so
    # repeated runs don't share cap state across processes. The counter is
    # per-domain-quota-aware via ``_template_cap``.
    reset_template_id_counts()

    # Phase 2g.10 (Team Golf B3): per-domain budget reallocation. When
    # circuit_breaker is on and a domain abandons early, its unused budget
    # carries forward to the next domain (capped at 2 × original).
    if circuit_breaker:
        from src.qa._corpus import CellTracker, _reallocate_with_cap
    leftover = 0

    for dom in domains:
        original_target = count if not run_all else DOMAIN_TARGETS.get(dom, 100) // 4
        if circuit_breaker and leftover > 0:
            target = _reallocate_with_cap(
                original=original_target, leftover=leftover, cap_factor=2,
            )
            logger.info(
                "circuit-breaker reallocation: domain={} target {} → {} "
                "(leftover {})",
                dom, original_target, target, leftover,
            )
        else:
            target = original_target
        leftover = 0

        templates_for_domain = [
            t for t in TEMPLATES if t["domain"] == dom
            and (not difficulty or difficulty in t["difficulty_range"])
            and not t.get("disabled", False)  # Phase 2g.16 Lever 5: skip disabled templates
        ]
        if not templates_for_domain:
            logger.warning(f"No templates for domain={dom}")
            continue

        # γ-2 — high-weight fact-specific templates first
        templates_for_domain = _weighted_template_order(templates_for_domain)

        facts = sample_facts(
            dom, count=target * 10, exclude_ids=used_facts, strategy="template",
            per_country_cap=per_country_cap,
            require_substantive=True,  # Phase 2g.16 Lever 2: force substantive filter for templates
        )
        if not facts:
            logger.warning(f"No facts available for domain={dom}")
            continue
        # Phase 2g.13: register the sampled fact IDs so subsequent passes
        # in the multi-pass loop exclude them.
        register_attempted_fact_ids(
            _STRATEGY_NAME, [str(f["id"]) for f in facts],
        )

        tracker = CellTracker() if circuit_breaker else None
        generated = 0
        # v2.3 fix #13 — filter out cap-exceeded templates each iteration. If the
        # whole candidate list empties out we log a warning and fall back to the
        # full (capped) list so throughput doesn't crash.
        cap = _template_cap(target)
        for template in templates_for_domain:
            if generated >= target:
                break
            if tracker is not None and tracker.should_abandon():
                logger.warning(
                    "CIRCUIT BREAKER | strategy=template | cell={} | "
                    "attempts={} | kept={} | rate={:.1%} — abandoning",
                    dom, tracker.attempts, tracker.kept,
                    tracker.kept_rate(),
                )
                break
            # Cap check: skip templates that are already at/over the cap.
            if _TEMPLATE_ID_COUNTS.get(template["id"], 0) >= cap:
                # If EVERY candidate is over the cap we fall through and use
                # this one anyway (logged). Otherwise skip — the outer loop
                # will pick up an uncapped template next.
                remaining_under_cap = _templates_under_cap(
                    [
                        t for t in templates_for_domain
                        if t["id"] != template["id"]
                    ],
                    target,
                )
                if remaining_under_cap:
                    logger.debug(
                        f"Template {template['id']} hit cap "
                        f"({_TEMPLATE_ID_COUNTS[template['id']]}/{cap}); skipping."
                    )
                    continue
                logger.warning(
                    f"All templates for domain={dom} hit the 15% diversity cap; "
                    f"falling back to {template['id']} to preserve throughput."
                )
            matching = find_matching_facts(template, facts)
            random.shuffle(matching)
            for fact in matching:
                if generated >= target:
                    break
                if tracker is not None and tracker.should_abandon():
                    logger.warning(
                        "CIRCUIT BREAKER | strategy=template | cell={} | "
                        "attempts={} | kept={} | rate={:.1%} — abandoning",
                        dom, tracker.attempts, tracker.kept,
                        tracker.kept_rate(),
                    )
                    break
                # v2.3 fix #13 — re-check the cap inside the facts loop so a
                # single template doesn't blow past 15% from one candidate
                # pool. The outer if-block picked this template when at least
                # one slot was still available; if we've now filled them, stop
                # and let the next template take over.
                if _TEMPLATE_ID_COUNTS.get(template["id"], 0) >= cap:
                    remaining_under_cap = _templates_under_cap(
                        [
                            t for t in templates_for_domain
                            if t["id"] != template["id"]
                        ],
                        target,
                    )
                    if remaining_under_cap:
                        break
                    # No other uncapped templates — fall through with a warning.
                    logger.warning(
                        f"All templates for domain={dom} at cap; "
                        f"{template['id']} continuing past cap."
                    )
                result = fill_template(
                    template, fact, facts, use_embeddings=use_embeddings
                )
                if result is None:
                    if tracker is not None:
                        tracker.record(False)
                    continue

                # Phase 2g.8 cost optimization (2026-04-26):
                # Run the closed-book gate BEFORE paraphrase + verifier so we
                # can skip those Gemini calls on questions the gate will
                # relabel/drop anyway. On audit_pilot_v6 the gate flagged
                # ~60% of templates as closed-book-solvable; under the old
                # ordering each of those incurred two Gemini roundtrips
                # (paraphrase + answer-verify) before the gate even ran.
                #
                # The verdict computed here is passed to insert_question_gated
                # via pre_screened= so the downstream insert wrapper does NOT
                # re-screen a second time.
                from src.generators._closed_book_gate import screen_question
                pre_gate = screen_question(
                    stem=result["question_text"],
                    options=result["options"],
                    correct_answer=result["correct_answer"],
                    difficulty=str(result["difficulty"]),
                    question_type=result["question_type"],
                )
                # gate_skipped True ⇔ the gate did not flag this question
                # (either it ran and passed, or it didn't apply). Only those
                # questions get the full paraphrase + verifier treatment.
                gate_skipped = pre_gate.passed

                # γ-5 — optional LLM paraphrase (default-on in v2.2, fix #1).
                # Skipped on gate-flagged questions (Phase 2g.8): they are
                # destined for the closed_book_solvable bucket and don't
                # benefit from A4 stylometric obfuscation.
                # Phase 2g.16 Lever 4: 1-shot retry on failure + OK/FAIL counters.
                if paraphrase_fn is not None and gate_skipped:
                    global _PARAPHRASE_OK_COUNT, _PARAPHRASE_FAIL_COUNT
                    _tid_for_log = result.get("_template_id", template["id"])
                    rephrased: str | None = None
                    for _attempt in range(1, 3):  # attempts 1, 2
                        try:
                            rephrased = paraphrase_fn(
                                result["question_text"], result["options"]
                            )
                        except Exception as _perr:
                            logger.warning(
                                "template paraphrase EXCEPTION tid={} attempt={} err={}",
                                _tid_for_log, _attempt, _perr,
                            )
                            rephrased = None
                        if rephrased:
                            break  # success — stop retrying
                        # failure mode A: returned None/falsy
                    if rephrased:
                        result["question_text"] = rephrased
                        _PARAPHRASE_OK_COUNT += 1
                    else:
                        logger.warning(
                            "WARNING template paraphrase FAIL qid={} attempt=2 "
                            "falling back to raw template stem",
                            _tid_for_log,
                        )
                        _PARAPHRASE_FAIL_COUNT += 1

                # v2.2 fix #8e — mandatory Gemini answer-verification. One
                # call per template question before insert; rejects on
                # disagreement or "N" (fact doesn't support any option).
                # Skipped on gate-flagged questions (Phase 2g.8): the gate's
                # gold-letter match implicitly verifies the answer key for
                # questions Sonnet can solve closed-book.
                if not no_verify and gate_skipped and result["question_type"] == "multiple_choice":
                    from src.generators._verify import verify_template_answer_with_gemini
                    agrees, _vdebug = verify_template_answer_with_gemini(
                        question_text=result["question_text"],
                        options=result["options"],
                        correct_answer_id=result["correct_answer"],
                        source_fact_text=fact.get("fact_text", ""),
                    )
                    if not agrees:
                        if tracker is not None:
                            tracker.record(False)
                        logger.warning(
                            f"Template {template['id']} REJECT by Gemini verifier "
                            f"({_vdebug.get('chosen')!r} vs {_vdebug.get('expected')!r}) "
                            f"— cost=${_vdebug.get('cost_usd', 0.0):.4f}"
                        )
                        continue

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
                    if tracker is not None:
                        tracker.record(True)
                    _increment_template_count(result["_template_id"])  # v2.3 fix #13
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
                q_uuid, gate = insert_question_gated(
                    question_data,
                    generation_meta,
                    fact_ids=[result["_fact_id"]],
                    source_ids=[result["_source_id"]],
                    pre_screened=pre_gate,  # Phase 2g.8 — avoid duplicate gate call
                )
                if q_uuid and gate.relabeled:
                    generated += 1
                    total_relabeled_l1 += 1
                    generated_ids.append(q_uuid)
                    used_facts.add(result["_fact_id"])
                    if tracker is not None:
                        tracker.record(True)
                    _increment_template_count(result["_template_id"])  # v2.3 fix #13
                    logger.info(
                        "OK (relabeled L1) | template={} | {}",
                        result["_template_id"], gate.reason,
                    )
                elif q_uuid:
                    generated += 1
                    generated_ids.append(q_uuid)
                    used_facts.add(result["_fact_id"])
                    if tracker is not None:
                        tracker.record(True)
                    _increment_template_count(result["_template_id"])  # v2.3 fix #13
                elif gate.applied and gate.quota_full:
                    total_rejected_overflow += 1
                    if tracker is not None:
                        tracker.record(False)
                    logger.info(
                        "DROP (cb_quota_full) | template={} | {}",
                        result["_template_id"], gate.reason,
                    )
                else:
                    if tracker is not None:
                        tracker.record(False)

        total_generated += generated
        # Carry over abandoned-cell budget to the next domain.
        if tracker is not None and tracker.should_abandon():
            leftover = tracker.remaining_budget(target)
        logger.info(f"Domain {dom}: generated {generated}/{target} questions")

    click.echo(
        f"\nTotal generated: {total_generated}  "
        f"({total_relabeled_l1} relabeled to L1 (closed_book_solvable), "
        f"{total_rejected_overflow} dropped over quota)"
    )

    return {
        "generated": total_generated,
        "skipped_parse": 0,
        "skipped_dup": 0,
        "skipped_sample": 0,
        "relabeled_l1": total_relabeled_l1,
        "rejected_overflow": total_rejected_overflow,
        "inserted_uuids": list(generated_ids),
    }


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
