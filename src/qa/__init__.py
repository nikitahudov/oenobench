"""OenoBench Quality Audit (Phase 2c).

Multi-agent audit architecture that runs against a stratified pilot corpus
of generated questions, surfaces weaknesses across 24 known surfaces, and
produces a report + improvement plan that gates the full 10k generation run.

Entry point: `python -m src.qa.orchestrator --help`
"""
