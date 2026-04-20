"""Lazy wrapper so generators can reuse the C4 difficulty re-classifier
from the audit pipeline without creating an import cycle.

v2.2 fix #5. Promotes C4 from audit-only into the generation pipeline:
every LLM-generated question gets ONE Gemini difficulty rating. If the
rating differs by ≥ 2 levels from the labelled difficulty, the question
is rejected and the strategy resamples.

Cost: ~1000 tokens per call × 8000 questions at full 10k = ~$8.
"""

from __future__ import annotations

from loguru import logger


def classify_difficulty(
    *,
    question_text: str,
    options: list[dict],
    correct_answer: str,
) -> str | None:
    """Return Gemini's predicted difficulty level as a string ("1"-"4") or
    None on any failure. Uses the audit pipeline's C4 prompt + model so the
    generation-time gate and the post-hoc audit agree on what counts.
    """
    # Local import to avoid module-load-time coupling with the QA package.
    from src.qa.agents.team_c_probes import _c4_call_llm

    try:
        rated, _rationale, _meta = _c4_call_llm(
            question_text=question_text,
            options=options,
            correct_answer=correct_answer,
        )
    except Exception as exc:
        logger.warning(f"C4 gen-time call raised: {exc}")
        return None

    if rated is None:
        return None
    return str(int(rated))
