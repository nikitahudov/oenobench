"""
OenoBench — γ-5 LLM paraphrase post-pass for template-generated questions.

Plan reference: docs/GENERATION_IMPROVEMENT_PLAN.md §6.3e.

Wraps a Gemini-via-OpenRouter call that rephrases a template-generated MCQ
stem in natural language without changing its meaning, the question type,
or the answer key. The options remain exactly as the template produced
them — the LLM never sees, edits, or re-orders them.

Validation rules (all must pass or the original stem is kept):
  * Returned text is non-empty after stripping.
  * Length is within ±50% of the original.
  * Every entity name that appears in the options also appears in the new
    stem if it appeared in the original (so the question still references
    the same entities).
  * The string "True or False" is preserved if it was in the original
    (true/false vs. multiple-choice format must not flip).

The function is INTENTIONALLY conservative: when in doubt, return None and
let the template-generated stem stand. The caller (template_generator.py)
treats None as "keep original".

Usage:
    from src.generators._template_paraphrase import paraphrase_question_text
    new_text = paraphrase_question_text(question_text, options)
    if new_text:
        question_text = new_text
"""

from __future__ import annotations

from loguru import logger

from src.generators import _llm_cache

# Default model. Caller can override via the ``model`` argument.
_DEFAULT_MODEL = "gemini"

# Lever B1 (2026-04-28): cache version tag for paraphrase outputs. Bump
# when the prompt template or validation logic changes.
_PARAPHRASE_CACHE_VERSION = "PARAPHRASE_V1"

_PROMPT_TEMPLATE = (
    "Rephrase this multiple-choice question stem naturally without "
    "changing its meaning or the answer. Keep the question type "
    "identical (do NOT switch a multiple-choice question to true/false "
    "or vice versa). Preserve every entity name from the options. "
    "Output strict JSON of the form {{\"question_text\": \"...\"}}.\n\n"
    "Original stem: {original}\n"
    "Answer options (do NOT modify these — they are listed only for context):\n"
    "{options_str}"
)


def _length_within(orig: str, new: str, ratio: float = 0.5) -> bool:
    """Return True if ``new`` length is within ±ratio of ``orig`` length."""
    if not orig or not new:
        return False
    lo = max(1, int(len(orig) * (1 - ratio)))
    hi = int(len(orig) * (1 + ratio)) + 5  # +5 word slack for short stems
    return lo <= len(new) <= hi


def _option_entities_preserved(orig: str, new: str, options: list[dict]) -> bool:
    """Return True if every option text that appeared in ``orig`` also appears in ``new``.

    Many template stems quote one of the entity names (e.g. "Rheingau") in
    the stem itself. We require those references to survive paraphrasing so
    the question doesn't drift to a different entity.
    """
    orig_lower = orig.lower()
    new_lower = new.lower()
    for opt in options or []:
        text = (opt.get("text") or "").strip()
        if not text or text.lower() in {"true", "false"}:
            continue
        if text.lower() in orig_lower and text.lower() not in new_lower:
            return False
    return True


def _tf_format_preserved(orig: str, new: str) -> bool:
    """Detect format flips between true/false and MCQ phrasings."""
    orig_tf = "true or false" in orig.lower()
    new_tf = "true or false" in new.lower()
    return orig_tf == new_tf


def paraphrase_question_text(
    question_text: str,
    options: list[dict],
    model: str = _DEFAULT_MODEL,
) -> str | None:
    """γ-5 — Paraphrase a template-generated stem via Gemini.

    Returns the new stem string on success, or ``None`` if the LLM call
    failed or any validation check rejected the rephrasing. The caller
    keeps the original text on None.
    """
    if not question_text or not options:
        return None

    try:
        from src.generators._llm_client import GENERATOR_MODELS, get_client
    except Exception as e:  # pragma: no cover — defensive
        logger.warning(f"_llm_client unavailable for paraphrase: {e}")
        return None

    # Lever B1: cache lookup before we even build the prompt. Includes the
    # text + options because option text can leak into the entity-
    # preservation guard and change whether a paraphrase is accepted.
    _cache_model_id = GENERATOR_MODELS.get(model, model)
    _cache_key = _llm_cache.cache_key({
        "text": question_text,
        "options": options,
    })
    _cached = _llm_cache.lookup(
        kind="paraphrase",
        key=_cache_key,
        model_id=_cache_model_id,
        version_tag=_PARAPHRASE_CACHE_VERSION,
    )
    if _cached is not None:
        cached_text = _cached.get("paraphrased_text")
        if isinstance(cached_text, str) and cached_text:
            return cached_text
        # Stored payload missing or malformed → fall through to live call.

    options_str = "\n".join(
        f"  {o.get('id', '?')}. {o.get('text', '')}" for o in options
    )
    prompt = _PROMPT_TEMPLATE.format(
        original=question_text.strip(),
        options_str=options_str,
    )

    try:
        client = get_client()
    except Exception as e:
        logger.warning(f"Paraphrase client init failed: {e}")
        return None

    try:
        resp = client.generate(
            prompt=prompt,
            system="You are a careful technical editor for a wine knowledge benchmark.",
            model=model,
            temperature=0.3,
            max_tokens=300,
            json_mode=True,
            # Phase 2g.8: paraphrase prompts are sub-2K tokens. Pin OpenRouter
            # to the cheapest provider for the requested model so we don't
            # get billed at the >200K-context Gemini Pro tier ($5/$15 per
            # MTok) that the unpinned route was hitting on audit_pilot_v6.
            extra_body={"provider": {"sort": "price"}},
        )
    except Exception as e:
        logger.warning(f"Paraphrase LLM call raised: {e}")
        return None

    if not resp.success or not resp.parsed:
        logger.debug(f"Paraphrase LLM returned no parsed JSON; keeping original")
        return None

    new_text = (resp.parsed.get("question_text") or "").strip()
    if not new_text:
        return None

    if not _length_within(question_text, new_text):
        logger.debug(
            f"Paraphrase length out of band ({len(new_text)} vs {len(question_text)}); keeping original"
        )
        return None

    if not _tf_format_preserved(question_text, new_text):
        logger.debug("Paraphrase flipped TF/MC format; keeping original")
        return None

    if not _option_entities_preserved(question_text, new_text, options):
        logger.debug("Paraphrase dropped a referenced entity; keeping original")
        return None

    # Lever B1: cache only successful, validated paraphrases. Failed
    # validations (length, TF/MC flip, dropped entity) and LLM call
    # failures all returned None above without reaching here, so the
    # cache never stores a None — keeping cached_text truthiness check
    # in the lookup path safe.
    _llm_cache.store(
        kind="paraphrase",
        key=_cache_key,
        model_id=_cache_model_id,
        version_tag=_PARAPHRASE_CACHE_VERSION,
        payload={"paraphrased_text": new_text},
    )
    return new_text
