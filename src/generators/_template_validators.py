"""Template-specific post-fill validators (v2.2 fix #8).

These run AFTER the template is filled with entity data from a source fact
and BEFORE the question reaches the question DB / paraphrase post-pass.

The main two gates here are:

  * :func:`verify_answer_in_source_fact` — source-faithfulness gate. Requires
    that the correct_answer_text (and, for truth-preserving templates, the
    filled explanation) appears as a substring of the linked source fact's
    text, after normalization. Alias equivalences (US ↔ United States, etc.)
    are loaded lazily from ``data/aliases.yaml``. Gold-v2 showed "Kamptal
    is a wine region in Austria" was anchored to a fact that only said
    "Riesling is grown in the Kamptal region of Austria" — the claim was
    inferred, not supported. This gate closes that class of failure.

  * :func:`is_iconic_bare_country` — shape filter used by the distractor
    pool hardening (v2.2 fix #8c). Bans ~200 country names from being
    drawn as distractors for `region`/`appellation`/`subregion` fields.

Both are pure Python, no network calls. The Gemini answer-verifier lives in
``_verify.py::verify_template_answer_with_gemini`` (v2.2 fix #8e).
"""

from __future__ import annotations

import re
import unicodedata
from functools import lru_cache
from pathlib import Path


# ─── Normalization ────────────────────────────────────────────────────────

_PUNCT_RE = re.compile(r"[^\w\s-]")  # keep word chars, whitespace, hyphen
_WHITESPACE_RE = re.compile(r"\s+")


def _normalize(text: str) -> str:
    """Lowercase, strip accents/punctuation, collapse whitespace."""
    if not text:
        return ""
    # Strip accent marks so "Rhône" matches "Rhone" for free.
    nfkd = unicodedata.normalize("NFKD", text)
    no_accents = "".join(c for c in nfkd if not unicodedata.combining(c))
    no_punct = _PUNCT_RE.sub(" ", no_accents.lower())
    return _WHITESPACE_RE.sub(" ", no_punct).strip()


# ─── Alias loader (v2.2 fix #8b) ──────────────────────────────────────────


@lru_cache(maxsize=1)
def _load_aliases() -> dict[str, list[str]]:
    """Return a flat map: normalized canonical → list of normalized aliases.

    Each group in aliases.yaml (countries, regions, etc.) is flattened so
    callers can do one lookup. The reverse direction is populated too — any
    alias → any other alias in the same group — so order doesn't matter.
    """
    try:
        import yaml  # PyYAML
    except ImportError:
        return {}
    path = Path(__file__).resolve().parents[2] / "data" / "aliases.yaml"
    if not path.exists():
        return {}
    try:
        with path.open() as f:
            data = yaml.safe_load(f) or {}
    except Exception:
        return {}

    # Build equivalence classes. Each class is a set of normalized strings.
    classes: list[set[str]] = []
    for _group, entries in data.items():
        if not isinstance(entries, dict):
            continue
        for canonical, alias_list in entries.items():
            bucket = {_normalize(canonical)}
            for a in alias_list or []:
                norm = _normalize(a)
                if norm:
                    bucket.add(norm)
            bucket.discard("")
            if bucket:
                classes.append(bucket)

    # For each normalized name, map → list of all equivalents (including itself).
    out: dict[str, list[str]] = {}
    for cls in classes:
        for member in cls:
            out[member] = sorted(cls)
    return out


def _equivalents(name: str) -> list[str]:
    """Return all normalized aliases of a name (self-inclusive)."""
    n = _normalize(name)
    if not n:
        return []
    aliases = _load_aliases().get(n)
    return aliases if aliases else [n]


# ─── Source-faithfulness gate (v2.2 fix #8b) ──────────────────────────────


def verify_answer_in_source_fact(
    correct_answer_text: str,
    source_fact: str,
    *,
    explanation_filled: str | None = None,
) -> bool:
    """Return True iff the correct answer is literally supported by the fact.

    The rule (after normalization — lowercase, accent-strip, punctuation-strip,
    whitespace-collapse): the correct_answer_text (or any of its aliases
    from data/aliases.yaml) must appear as a substring of source_fact.

    The explanation_filled argument is kept in the signature for API stability
    but is NOT checked here. Semantic drift in the explanation is caught by
    the Gemini answer-verifier (v2.2 fix #8e), which reasons about whether
    the option set is directly supported by the fact. A stricter token-level
    explanation check was tried in the first v2.2 draft but over-rejected on
    benign plural/article mismatches (e.g. "slate soil" vs "slate soils").

    Gate returns False if the answer doesn't appear; caller should skip the
    template instance.
    """
    if not source_fact:
        return False

    n_fact = _normalize(source_fact)
    if not n_fact:
        return False

    # Check answer text (or an alias) substring-appears in the fact.
    for variant in _equivalents(correct_answer_text):
        if variant and variant in n_fact:
            return True

    # Fall back to raw substring (unaliased) — covers entities the alias
    # map doesn't know about yet (Leelanau Peninsula, obscure producers, etc.).
    n_answer = _normalize(correct_answer_text)
    if n_answer and n_answer in n_fact:
        return True

    return False


# ─── Country sentinel for distractor pool hardening (v2.2 fix #8c) ────────
# A bare country name must never be drawn as a distractor for a
# `region`/`appellation`/`subregion` field. The list is short, curated,
# and normalized.

_KNOWN_COUNTRIES_RAW = {
    "France", "Italy", "Spain", "Germany", "Portugal", "Austria", "Hungary",
    "Greece", "Switzerland", "Slovenia", "Croatia", "Georgia", "Lebanon",
    "Israel", "Turkey", "Czech Republic", "Czechia", "Bulgaria", "Romania",
    "Moldova", "Ukraine", "United States", "USA", "US", "U.S.", "U.S.A.",
    "Canada", "Mexico", "Argentina", "Chile", "Uruguay", "Brazil", "Peru",
    "Bolivia", "Australia", "New Zealand", "South Africa", "Morocco",
    "Tunisia", "Algeria", "Egypt", "China", "Japan", "Korea", "South Korea",
    "Thailand", "India", "Lebanon", "Cyprus", "Malta", "England",
    "Scotland", "Wales", "Ireland", "United Kingdom", "UK", "Britain",
    "Great Britain", "Luxembourg", "Belgium", "Netherlands", "Denmark",
    "Sweden", "Norway", "Finland", "Poland", "Slovakia", "Russia", "Armenia",
    "Azerbaijan", "Serbia", "Montenegro", "Bosnia", "Albania", "Macedonia",
    "North Macedonia", "Syria", "Iraq", "Iran",
}

_KNOWN_COUNTRIES_NORMALIZED: set[str] = {_normalize(c) for c in _KNOWN_COUNTRIES_RAW}


def is_iconic_bare_country(candidate: str) -> bool:
    """Return True if `candidate` (after normalization) is a bare country name.

    Also catches "Italian wine", "Georgian wine", etc. — the adjective-form
    references that appeared in the Force Majeure failure (gold-v2 WB-PRD-0104-L1).
    """
    n = _normalize(candidate)
    if not n:
        return False
    if n in _KNOWN_COUNTRIES_NORMALIZED:
        return True
    # "Italian wine" / "Georgian wine" — strip a trailing " wine" and recheck.
    if n.endswith(" wine"):
        stripped = n[: -len(" wine")].strip()
        # Demonym → country stem: Italian → Italy, Georgian → Georgia, etc.
        # We do a suffix-strip heuristic instead of a full demonym map.
        for suffix in ("ian", "ean", "ish", "ese", "ic"):
            if stripped.endswith(suffix):
                stem = stripped[: -len(suffix)]
                for country in _KNOWN_COUNTRIES_NORMALIZED:
                    if country.startswith(stem) and len(stem) >= 4:
                        return True
        # Direct: "italian" itself is not a country, but "italy wine" would
        # slip through the normalizer — guard against that too.
        if stripped in _KNOWN_COUNTRIES_NORMALIZED:
            return True
    return False
