"""
OenoBench — Human-readable question ID generator.

Produces IDs like WB-REG-0042-L3 for use in the questions table.
Sequence numbers are derived from the current DB count per domain.
"""

from loguru import logger

from src.utils.db import get_pg

# ─── Domain code mapping ─────────────────────────────────────────────────────

DOMAIN_CODES: dict[str, str] = {
    "wine_regions": "REG",
    "winemaking": "WMK",
    "viticulture": "VIT",
    "grape_varieties": "GRP",
    "wine_business": "BIZ",
    "producers": "PRD",
}


def mint_question_id(domain: str, difficulty: str) -> str:
    """Generate the next human-readable question ID for a domain.

    Format: WB-{DOMAIN_CODE}-{SEQ:04d}-L{DIFFICULTY}
    Example: WB-REG-0042-L3

    Args:
        domain: A domain_type value (e.g. 'wine_regions').
        difficulty: A difficulty_level value ('1'-'4').

    Returns:
        A unique question ID string.

    Raises:
        ValueError: If domain is not in DOMAIN_CODES.
    """
    code = DOMAIN_CODES.get(domain)
    if code is None:
        raise ValueError(
            f"Unknown domain '{domain}'. Valid: {list(DOMAIN_CODES.keys())}"
        )

    conn = get_pg()
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(*) AS cnt FROM questions WHERE question_id LIKE %s",
        (f"WB-{code}-%",),
    )
    seq = cur.fetchone()["cnt"] + 1

    qid = f"WB-{code}-{seq:04d}-L{difficulty}"
    logger.debug(f"Minted question ID: {qid}")
    return qid
