"""
OenoBench — Question Generation Pipeline.

Modules:
    _llm_client     — Unified OpenRouter LLM client
    _prompts        — Prompt templates for all generation strategies
    _schemas        — Pydantic output validation
    _id_generator   — Human-readable question ID minting
    _question_db    — Question insertion with provenance linkage
    _fact_sampler   — Stratified fact selection from PostgreSQL
    _dedup          — Embedding-based semantic deduplication

Strategies:
    fact_to_question    — Strategy 1: Fact → question via LLM (40%)
    template_generator  — Strategy 2: Deterministic templates (25%)
"""
