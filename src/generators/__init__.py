"""
OenoBench — Question Generation Pipeline.

Shared modules:
    _llm_client     — Unified OpenRouter LLM client (5 models)
    _prompts        — Prompt templates for all generation strategies
    _schemas        — Pydantic output validation
    _id_generator   — Human-readable question ID minting
    _question_db    — Question insertion with provenance linkage
    _fact_sampler   — Stratified fact selection from PostgreSQL
    _dedup          — Embedding-based semantic deduplication

Strategies:
    fact_to_question        — Strategy 1: Fact -> question via LLM (40%)
    template_generator      — Strategy 2: Deterministic templates (25%)
    comparative_generator   — Strategy 3: Entity comparison (15%)
    scenario_generator      — Strategy 4: Multi-fact scenarios (10%)
    distractor_miner        — Strategy 5: Mined distractors (10%)

Orchestrator:
    orchestrator            — Main CLI: generate-all, status, dedup, embed, validate
"""
