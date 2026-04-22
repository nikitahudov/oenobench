"""
OenoBench — Bordeaux Wine Scraper (genuine external data only)

Extracts Bordeaux wine knowledge from:
  1. Wikipedia — classification articles, appellation articles, grape articles
  2. Wikidata SPARQL — wine regions, appellations, wineries (country-scoped)
  3. bordeaux.com (CIVB) — supplementary scraping when accessible

Every fact traces to a URL that was actually fetched and parsed.
No hardcoded wine knowledge.

Usage:
    python -m src.scrapers.bordeaux --all
    python -m src.scrapers.bordeaux --dry-run
    python -m src.scrapers.bordeaux --validate
    python -m src.scrapers.bordeaux --list
    python -m src.scrapers.bordeaux --test-run
    python -m src.scrapers.bordeaux --test-run --cleanup
"""

import random
import re
from collections import Counter

import click
from loguru import logger

from src.utils.facts import ensure_source, insert_facts_batch, get_fact_count
from src.scrapers._wiki_helpers import (
    wiki_session,
    fetch_article,
    fetch_full_extract,
    crawl_category,
    parse_infobox,
    parse_wikitext_tables,
    extract_atomic_facts,
    run_sparql_filtered,
    ensure_wiki_source,
    ensure_wikidata_source,
    clean_wiki_value,
    SPARQL_WINE_REGIONS_BY_COUNTRY,
    SPARQL_APPELLATIONS_BY_COUNTRY,
    SPARQL_WINERIES_BY_COUNTRY,
)
from src.scrapers._fact_processing import classify_domain, process_facts, is_on_topic
from src.scrapers._web_helpers import scrape_site_texts

# ─── Configuration ────────────────────────────────────────────────────────────

TEST_RUN_LIMIT = 5
FRANCE_QID = "Q142"

# Marketing/promotional text patterns to reject from official websites
_MARKETING_RE = re.compile(
    r"(?:^(?:Meet|Come|Discover|Share|Join|Visit|Explore|Experience|"
    r"Book|Plan|Find|Browse|Follow|Subscribe|Sign up|Download|Click|"
    r"Don't miss|Let us|Let's|Ready to)\b|"
    r"\b(?:you(?:'re|r| are| will| can| should| must| won't))\b)",
    re.IGNORECASE,
)

BORDEAUX_REGION_KEYWORDS = {
    "bordeaux", "gironde", "médoc", "medoc", "saint-émilion", "saint-emilion",
    "pauillac", "graves", "sauternes", "entre-deux-mers", "blaye", "bourg",
    "fronsac", "pomerol", "libournais", "margaux", "haut-médoc", "haut-medoc",
    "pessac-léognan", "pessac-leognan", "barsac", "loupiac", "cadillac",
    "côtes de bordeaux", "cotes de bordeaux", "saint-julien", "saint-estèphe",
    "saint-estephe", "listrac", "moulis", "lalande", "canon-fronsac",
    "castillon", "francs", "1855 classification", "nouvelle-aquitaine",
}

# ── v2.3 fix #14c — defensive region validators ───────────────────────────
# Added 2026-04-22 after audit gold-v3 traced 3 human-flagged "completely
# incorrect" template questions back to Saint-Émilion classified-growths
# table being mis-parsed. Two failure modes:
#   (a) Multi-column tables where every cell is a château name — the previous
#       code treated cell[0] as name and cell[1] as "commune/region", so each
#       row emitted "Château X is a classified Bordeaux estate in Château Y".
#   (b) Wikitext cell-attribute syntax ('colspan="2" align="center" | 178 g/L')
#       leaking through `clean_wiki_value` and into the region slot.
#
# `_REGION_IS_CHATEAU_RE` and `_MARKUP_LEAK_RE` act as a final gate on every
# candidate commune before a classification fact is emitted.

_REGION_IS_CHATEAU_RE = re.compile(r"^\s*ch(?:â|a)teau\b", re.IGNORECASE)
_MARKUP_LEAK_RE = re.compile(r"(?:\b(?:align|colspan|rowspan|bgcolor|valign|style)\s*=|&nbsp;|\|)", re.IGNORECASE)

# Article titles where table rows list classified estates in one or more
# parallel columns (NOT estate→commune pairs). For these, every cell in a
# data row is a château name at the same classification level; the commune
# is fixed by the article (here, Saint-Émilion).
_MULTICOL_ESTATE_TABLE_REGIONS = {
    "Classification of Saint-Émilion wine": "Saint-Émilion",
    "Classification of Saint-Emilion wine": "Saint-Émilion",
}


_CELL_CRUFT_RE = re.compile(r"(?:&nbsp;|&amp;|\u00a0)+", re.IGNORECASE)


def _sanitize_cell(text: str) -> str:
    """Strip residual HTML entities (`&nbsp;`, non-breaking space) and
    collapse whitespace. ``clean_wiki_value`` in ``_wiki_helpers`` doesn't
    touch named entities, so they leak into cell text and would otherwise
    show up in emitted fact texts and entity names.
    """
    if not text:
        return ""
    cleaned = _CELL_CRUFT_RE.sub(" ", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _is_chateau_cell(text: str) -> bool:
    """True if a cell clearly names a château-style estate.

    Used to detect the multi-column "row of sibling estates" layout that the
    Saint-Émilion classification article uses.
    """
    return bool(_REGION_IS_CHATEAU_RE.match(_sanitize_cell(text) or ""))


def _region_is_valid(commune: str) -> bool:
    """Gate keeper for fact_text = '<name> is a classified Bordeaux estate in <commune>'.

    Rejects commune values that are themselves château names (the off-by-one
    bug) or that contain leftover wikitext/HTML markup (e.g. ``align="center"``
    or ``&nbsp;``). Returns True when the value is safe to emit.
    """
    if not commune:
        return False
    cleaned = commune.strip()
    if not cleaned:
        return False
    if _REGION_IS_CHATEAU_RE.match(cleaned):
        return False
    if _MARKUP_LEAK_RE.search(cleaned):
        return False
    return True


# Key Wikipedia articles to scrape
KEY_ARTICLES = [
    "Bordeaux wine",
    "Bordeaux wine regions",
    "Classification of Bordeaux wine",
    "1855 Bordeaux classification",
    "Classification of Saint-Émilion wine",
    "Médoc",
    "Saint-Émilion",
    "Pauillac",
    "Margaux AOC",
    "Graves (wine)",
    "Sauternes (wine)",
    "Pomerol",
    "Entre-Deux-Mers",
    "Pessac-Léognan",
    "Haut-Médoc AOC",
    "Saint-Julien AOC",
    "Saint-Estèphe AOC",
    "Listrac-Médoc AOC",
    "Moulis-en-Médoc AOC",
    "Fronsac AOC",
    "Barsac AOC",
    "Côtes de Bordeaux",
    "Lalande-de-Pomerol AOC",
    "Bordeaux AOC",
    "Côtes de Bourg",
    "Blaye AOC",
]

WIKIPEDIA_CATEGORIES = [
    "Category:Bordeaux AOCs",
    "Category:Wine regions of Gironde",
]


# ─── Wikipedia Scraping ──────────────────────────────────────────────────────


_HEADER_CELL_VALUES = {
    "name", "château", "chateau", "estate", "wine", "property",
    "appellation", "commune", "classification", "growth",
    "premier grand cru classé", "premier grand cru classé 'a'",
    "premier grand cru classé 'b'", "grand cru classé",
    "premier cru", "second cru", "third cru", "fourth cru", "fifth cru",
    "premier grand cru", "grand cru", "premier grand cru classe",
    "premier grand cru classe 'a'", "premier grand cru classe 'b'",
    "grand cru classe",
}


def _is_header_cell(text: str) -> bool:
    """Return True for cells that are clearly table headers, not data."""
    if not text:
        return True
    normalised = text.strip().lower().strip("'\" ")
    if not normalised:
        return True
    if normalised in _HEADER_CELL_VALUES:
        return True
    # Any row whose first cell is an unbulleted classification title
    if normalised.startswith(("premier grand cru", "grand cru classé",
                              "grand cru classe", "premier cru classé",
                              "premier cru classe")):
        return True
    return False


def _facts_from_classification_table(
    rows: list[list[str]],
    title: str,
    source_id: str,
    seen: set[str],
) -> list[dict]:
    """Build classification facts from wikitext table rows.

    v2.3 fix #14c — Saint-Émilion uses a multi-column layout where every
    data-row cell is a château name at the same classification level. The
    prior code ``name=row[0], commune=row[1]`` produced off-by-one facts like
    "Château Pavie is a classified Bordeaux estate in Château Figeac" (9 of
    13 rows affected, plus 9 more with table-attribute markup leaking into
    the commune slot).

    Behaviour per article layout:
      * ``title`` in ``_MULTICOL_ESTATE_TABLE_REGIONS`` — treat each cell as a
        sibling château name; set commune to the fixed region for that
        article (e.g. "Saint-Émilion").
      * Otherwise — fall back to the legacy two-column ``name | commune``
        layout, but apply ``_region_is_valid`` so no row where the commune
        is itself a château or carries HTML markup is ever emitted.
    """
    out: list[dict] = []
    is_multicol = title in _MULTICOL_ESTATE_TABLE_REGIONS
    # Non-château Saint-Émilion classified estates (Clos, domaines, etc.)
    # whose cells should still be treated as sibling producers in the
    # multi-column layout.
    _NON_CHATEAU_CLASSIFIED = (
        "clos ", "domaine ", "la mondotte", "le dôme", "le dome",
        "pavillon ", "vieux ",
    )

    for row in rows:
        if not row:
            continue
        # A single-cell row is a section header (e.g. "Grand Cru Classé") —
        # never a data row in these tables.
        if len(row) == 1:
            continue

        # Sanitize every cell up front so residual &nbsp; / non-breaking
        # spaces don't leak into producer names or commune strings.
        sanitized_row = [_sanitize_cell(c) for c in row]

        # Multi-column estate layout: every data row lists sibling classified
        # estates (mostly "Château X", occasionally "Clos Y" or "La Mondotte").
        # We enter this branch whenever the article is known to use this
        # layout AND at least one cell looks like a classified-estate name.
        if is_multicol and any(
            _is_chateau_cell(cell)
            or cell.lower().startswith(_NON_CHATEAU_CLASSIFIED)
            for cell in sanitized_row
        ):
            commune = _MULTICOL_ESTATE_TABLE_REGIONS[title]
            for name in sanitized_row:
                if not name or _is_header_cell(name):
                    continue
                if len(name) < 3 or len(name) > 80:
                    continue
                # Drop obvious non-estate cells (numbers, stray markup) —
                # classified estates either start with Château/Clos/Domaine
                # or are one of the handful of known one-off names.
                lname = name.lower()
                is_estate_name = (
                    _is_chateau_cell(name)
                    or any(lname.startswith(pfx) for pfx in _NON_CHATEAU_CLASSIFIED)
                )
                if not is_estate_name:
                    continue
                if not _region_is_valid(commune):
                    continue
                # Defensive: estate names themselves must not leak markup.
                if _MARKUP_LEAK_RE.search(name):
                    continue
                fact_text = f"{name} is a classified Bordeaux estate in {commune}."
                key = fact_text.lower()
                if key in seen:
                    continue
                seen.add(key)
                out.append({
                    "fact_text": fact_text,
                    "domain": classify_domain(fact_text),
                    "subdomain": "bordeaux",
                    "source_id": source_id,
                    "entities": [
                        {"type": "producer", "name": name},
                        {"type": "region", "name": commune},
                    ],
                    "confidence": 0.9,
                    "tags": ["bordeaux", "wikipedia", "classification"],
                })
            continue

        # Legacy two-column "name | commune" layout.
        name = sanitized_row[0] if sanitized_row else ""
        commune = sanitized_row[1] if len(sanitized_row) > 1 else ""
        if not name or _is_header_cell(name):
            continue
        if len(name) < 3 or len(name) > 80:
            continue
        if not commune or len(commune) >= 40:
            continue
        if commune.startswith(("–", "—", "-")):
            continue
        # v2.3 fix #14c defensive gate: drop off-by-one château-as-region
        # pairings and any row whose commune contains table-markup leakage.
        if not _region_is_valid(commune):
            continue
        # Estate names must also be markup-free.
        if _MARKUP_LEAK_RE.search(name):
            continue
        fact_text = f"{name} is a classified Bordeaux estate in {commune}."
        key = fact_text.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "fact_text": fact_text,
            "domain": classify_domain(fact_text),
            "subdomain": "bordeaux",
            "source_id": source_id,
            "entities": [
                {"type": "producer", "name": name},
                {"type": "region", "name": commune},
            ],
            "confidence": 0.9,
            "tags": ["bordeaux", "wikipedia", "classification"],
        })

    return out


def _scrape_wikipedia_articles(session, source_id: str) -> list[dict]:
    """Scrape key Bordeaux wine articles from Wikipedia using atomic extraction."""
    facts = []
    seen = set()

    for title in KEY_ARTICLES:
        logger.info(f"Fetching Wikipedia article: {title}")
        extract, wikitext = fetch_article(session, title)

        if extract:
            atomic = extract_atomic_facts(
                extract, title,
                region_keywords=BORDEAUX_REGION_KEYWORDS,
            )
            for af in atomic:
                key = af["fact_text"].lower()
                if key not in seen:
                    seen.add(key)
                    facts.append({
                        **af,
                        "source_id": source_id,
                        "subdomain": "bordeaux",
                        "entities": [{"type": "region", "name": title}],
                        "confidence": 0.9,
                        "tags": ["bordeaux", "wikipedia"],
                    })

        if wikitext:
            # Parse tables from classification articles. v2.3 fix #14c:
            # delegate to _facts_from_classification_table so the multi-column
            # Saint-Émilion layout (rows of sibling château cells) and stray
            # table-attribute leakage (align=, colspan=, &nbsp;) can't produce
            # "<Château A> is a classified Bordeaux estate in <Château B>"
            # or markup-contaminated region entities.
            rows = parse_wikitext_tables(wikitext)
            facts.extend(
                _facts_from_classification_table(rows, title, source_id, seen)
            )

            # Parse infobox data
            infobox = parse_infobox(wikitext)
            if infobox:
                grape = infobox.get("grapes", "") or infobox.get("grape", "")
                area = infobox.get("area", "") or infobox.get("size", "")

                if grape:
                    grapes = [g.strip() for g in re.split(r"[,;]", grape) if g.strip()]
                    for g in grapes[:5]:
                        if 2 < len(g) < 50:
                            fact_text = f"{title} permits the {g} grape variety."
                            key = fact_text.lower()
                            if key not in seen:
                                seen.add(key)
                                facts.append({
                                    "fact_text": fact_text,
                                    "domain": "grape_varieties",
                                    "subdomain": "bordeaux",
                                    "source_id": source_id,
                                    "entities": [
                                        {"type": "region", "name": title},
                                        {"type": "grape", "name": g},
                                    ],
                                    "confidence": 0.9,
                                    "tags": ["bordeaux", "wikipedia", "grape"],
                                })

                if area and re.search(r"\d", area):
                    fact_text = f"{title} covers approximately {area} hectares."
                    key = fact_text.lower()
                    if key not in seen:
                        seen.add(key)
                        facts.append({
                            "fact_text": fact_text,
                            "domain": classify_domain(fact_text),
                            "subdomain": "bordeaux",
                            "source_id": source_id,
                            "entities": [{"type": "region", "name": title}],
                            "confidence": 0.9,
                            "tags": ["bordeaux", "wikipedia", "area"],
                        })

    return facts


def _scrape_wikipedia_categories(session, source_id: str) -> list[dict]:
    """Scrape Bordeaux appellation articles from Wikipedia categories."""
    facts = []
    seen = set()

    all_titles = set()
    for cat in WIKIPEDIA_CATEGORIES:
        logger.info(f"Crawling category: {cat}")
        titles = crawl_category(session, cat, max_depth=2, max_articles=100)
        all_titles.update(titles)

    # Remove articles already covered by KEY_ARTICLES
    all_titles -= set(KEY_ARTICLES)
    logger.info(f"Found {len(all_titles)} additional Bordeaux-related articles from categories")

    for title in sorted(all_titles):
        logger.info(f"Fetching: {title}")
        extract, wikitext = fetch_article(session, title)

        if extract:
            atomic = extract_atomic_facts(
                extract, title,
                region_keywords=BORDEAUX_REGION_KEYWORDS,
            )
            for af in atomic:
                key = af["fact_text"].lower()
                if key not in seen:
                    seen.add(key)
                    facts.append({
                        **af,
                        "source_id": source_id,
                        "subdomain": "bordeaux",
                        "entities": [{"type": "region", "name": title}],
                        "confidence": 0.9,
                        "tags": ["bordeaux", "wikipedia", "appellation"],
                    })

        if wikitext:
            infobox = parse_infobox(wikitext)
            if infobox:
                region = infobox.get("region", "")
                grape = infobox.get("grapes", "") or infobox.get("grape", "")
                area = infobox.get("area", "") or infobox.get("size", "") or infobox.get("hectares", "")
                classification = infobox.get("classification", "")
                year = infobox.get("year established", "") or infobox.get("established", "")

                if region and not region.startswith("Q"):
                    fact_text = f"{title} is a wine appellation in {region}."
                    key = fact_text.lower()
                    if key not in seen:
                        seen.add(key)
                        facts.append({
                            "fact_text": fact_text,
                            "domain": classify_domain(fact_text),
                            "subdomain": "bordeaux",
                            "source_id": source_id,
                            "entities": [{"type": "region", "name": title}],
                            "confidence": 0.9,
                            "tags": ["bordeaux", "wikipedia", "appellation"],
                        })

                if grape:
                    grapes = [g.strip() for g in re.split(r"[,;]", grape) if g.strip()]
                    for g in grapes[:5]:
                        if 2 < len(g) < 50:
                            fact_text = f"{title} permits the {g} grape variety."
                            key = fact_text.lower()
                            if key not in seen:
                                seen.add(key)
                                facts.append({
                                    "fact_text": fact_text,
                                    "domain": "grape_varieties",
                                    "subdomain": "bordeaux",
                                    "source_id": source_id,
                                    "entities": [
                                        {"type": "region", "name": title},
                                        {"type": "grape", "name": g},
                                    ],
                                    "confidence": 0.9,
                                    "tags": ["bordeaux", "wikipedia", "grape"],
                                })

                if area and re.search(r"\d", area):
                    area_clean = re.sub(r"[^\d.,]", " ", area).strip()
                    if area_clean:
                        fact_text = f"{title} covers approximately {area_clean} hectares."
                        key = fact_text.lower()
                        if key not in seen:
                            seen.add(key)
                            facts.append({
                                "fact_text": fact_text,
                                "domain": classify_domain(fact_text),
                                "subdomain": "bordeaux",
                                "source_id": source_id,
                                "entities": [{"type": "region", "name": title}],
                                "confidence": 0.9,
                                "tags": ["bordeaux", "wikipedia", "area"],
                            })

                if classification:
                    fact_text = f"{title} holds {classification} classification."
                    key = fact_text.lower()
                    if key not in seen:
                        seen.add(key)
                        facts.append({
                            "fact_text": fact_text,
                            "domain": classify_domain(fact_text),
                            "subdomain": "bordeaux",
                            "source_id": source_id,
                            "entities": [{"type": "region", "name": title}],
                            "confidence": 0.9,
                            "tags": ["bordeaux", "wikipedia", "classification"],
                        })

                if year and re.search(r"\d{4}", year):
                    year_match = re.search(r"\d{4}", year)
                    if year_match:
                        fact_text = f"{title} was established in {year_match.group()}."
                        key = fact_text.lower()
                        if key not in seen:
                            seen.add(key)
                            facts.append({
                                "fact_text": fact_text,
                                "domain": classify_domain(fact_text),
                                "subdomain": "bordeaux",
                                "source_id": source_id,
                                "entities": [{"type": "region", "name": title}],
                                "confidence": 0.9,
                                "tags": ["bordeaux", "wikipedia", "history"],
                            })

    return facts


# ─── Wikidata SPARQL ─────────────────────────────────────────────────────────


def _has_bordeaux_keyword(labels_text: str) -> bool:
    """Check if any Bordeaux-specific keyword appears in SPARQL labels."""
    text = labels_text.lower()
    return any(kw in text for kw in BORDEAUX_REGION_KEYWORDS)


def _scrape_wikidata(source_id: str) -> list[dict]:
    """Query Wikidata for Bordeaux wine entities using country-scoped queries."""
    facts = []
    seen = set()

    def _add(text, domain=None, entities=None, tags=None, confidence=0.85):
        if not domain:
            domain = classify_domain(text)
        key = text.lower()
        if key in seen:
            return
        seen.add(key)
        if not is_on_topic(text, BORDEAUX_REGION_KEYWORDS):
            return
        facts.append({
            "fact_text": text,
            "domain": domain,
            "subdomain": "bordeaux",
            "source_id": source_id,
            "entities": entities or [],
            "confidence": confidence,
            "tags": tags or ["bordeaux", "wikidata"],
        })

    # Query 1: Wine regions in France, post-filtered for Bordeaux
    logger.info("SPARQL: Wine regions in France (Bordeaux-filtered)")
    query = SPARQL_WINE_REGIONS_BY_COUNTRY.format(country_qid=FRANCE_QID)
    rows = run_sparql_filtered(
        query, expected_country="France",
        region_keywords=BORDEAUX_REGION_KEYWORDS,
    )
    for row in rows:
        name = row.get("itemLabel", "")
        region = row.get("regionLabel", "")
        grape = row.get("grapeLabel", "")
        area = row.get("areaHa", "")
        if not name or name.startswith("Q"):
            continue
        # Require Bordeaux keyword in labels to avoid non-Bordeaux French results
        labels = " ".join(v for k, v in row.items() if k.endswith("Label") and v)
        if not _has_bordeaux_keyword(f"{name} {labels}"):
            continue
        if region and not region.startswith("Q"):
            _add(
                f"{name} is a wine region in {region}.",
                entities=[{"type": "region", "name": name}],
            )
        else:
            _add(
                f"{name} is a wine region in Bordeaux.",
                entities=[{"type": "region", "name": name}],
            )
        if grape and not grape.startswith("Q"):
            _add(
                f"{name} is associated with the {grape} grape variety.",
                entities=[
                    {"type": "region", "name": name},
                    {"type": "grape", "name": grape},
                ],
                tags=["bordeaux", "wikidata", "grape"],
            )
        if area and re.search(r"\d", str(area)):
            _add(
                f"{name} covers approximately {area} hectares.",
                entities=[{"type": "region", "name": name}],
                tags=["bordeaux", "wikidata", "area"],
            )

    # Query 2: Appellations in France, post-filtered for Bordeaux
    logger.info("SPARQL: Appellations in France (Bordeaux-filtered)")
    query = SPARQL_APPELLATIONS_BY_COUNTRY.format(country_qid=FRANCE_QID)
    rows = run_sparql_filtered(
        query, expected_country="France",
        region_keywords=BORDEAUX_REGION_KEYWORDS,
    )
    for row in rows:
        name = row.get("itemLabel", "")
        region = row.get("regionLabel", "")
        if not name or name.startswith("Q"):
            continue
        labels = " ".join(v for k, v in row.items() if k.endswith("Label") and v)
        if not _has_bordeaux_keyword(f"{name} {labels}"):
            continue
        if region and not region.startswith("Q"):
            _add(
                f"{name} is a wine appellation in {region}.",
                entities=[{"type": "region", "name": name}],
                tags=["bordeaux", "wikidata", "appellation"],
            )
        else:
            _add(
                f"{name} is a wine appellation in Bordeaux.",
                entities=[{"type": "region", "name": name}],
                tags=["bordeaux", "wikidata", "appellation"],
            )

    # Query 3: Wineries in France, post-filtered for Bordeaux
    logger.info("SPARQL: Wineries in France (Bordeaux-filtered)")
    query = SPARQL_WINERIES_BY_COUNTRY.format(country_qid=FRANCE_QID)
    rows = run_sparql_filtered(
        query, expected_country="France",
        region_keywords=BORDEAUX_REGION_KEYWORDS,
    )
    for row in rows:
        name = row.get("itemLabel", "")
        region = row.get("regionLabel", "")
        founded = row.get("founded", "")
        if not name or name.startswith("Q"):
            continue
        labels = " ".join(v for k, v in row.items() if k.endswith("Label") and v)
        if not _has_bordeaux_keyword(f"{name} {labels}"):
            continue
        if region and not region.startswith("Q"):
            _add(
                f"{name} is a wine estate in {region}.",
                domain="producers",
                entities=[
                    {"type": "producer", "name": name},
                    {"type": "region", "name": region},
                ],
                tags=["bordeaux", "wikidata", "chateau"],
            )
        if founded and re.search(r"\d{4}", founded):
            year = re.search(r"\d{4}", founded).group()
            _add(
                f"{name} was founded in {year}.",
                domain="producers",
                entities=[{"type": "producer", "name": name}],
                tags=["bordeaux", "wikidata", "history"],
            )

    return facts


# ─── CIVB Website Scraping ───────────────────────────────────────────────────


def _scrape_civb(source_id: str) -> list[dict]:
    """Scrape supplementary facts from bordeaux.com (CIVB) using shared helpers."""
    facts = []

    logger.info("Attempting to scrape bordeaux.com (CIVB)...")
    url_filter = re.compile(r"(?:appellation|wine|terroir|grape|vineyard)", re.IGNORECASE)

    try:
        page_texts = scrape_site_texts(
            base_url="https://www.bordeaux.com",
            seed_paths=[
                "/us/our-terroir/appellations",
                "/us/our-wines",
                "/us/our-terroir",
            ],
            max_pages=30,
            delay=5.0,
            url_filter=url_filter,
        )
    except Exception as e:
        logger.warning(f"CIVB scraping failed: {e}")
        return facts

    if not page_texts:
        logger.warning("CIVB website returned no pages (may be blocked)")
        return facts

    # Process all text blocks through the fact pipeline
    marketing_rejected = 0
    for url, blocks in page_texts:
        # Filter out marketing/promotional text and URL-encoded junk
        filtered_blocks = []
        for b in blocks:
            if _MARKETING_RE.search(b):
                marketing_rejected += 1
                continue
            # Reject blocks with URL-encoded content or HTML artifacts
            if "%2" in b or "%3" in b or ".Html" in b or ".html" in b:
                continue
            filtered_blocks.append(b)

        # Try to extract an entity name from the URL path
        url_entity = None
        url_path = url.rsplit("/", 1)[-1] if "/" in url else ""
        if (url_path
                and url_path not in ("our-terroir", "our-wines", "appellations", "")
                and "%" not in url_path
                and "." not in url_path
                and len(url_path) < 60):
            url_entity = url_path.replace("-", " ").title()

        processed = process_facts(
            raw_texts=filtered_blocks,
            subject=url_entity or "Bordeaux",
            region_keywords=BORDEAUX_REGION_KEYWORDS,
        )
        for pf in processed:
            entities = []
            if url_entity:
                entities = [{"type": "region", "name": url_entity}]
            facts.append({
                **pf,
                "source_id": source_id,
                "subdomain": "bordeaux",
                "entities": entities,
                "confidence": 0.8,
                "tags": ["bordeaux", "civb", "scraped"],
            })

    if marketing_rejected:
        logger.info(f"CIVB: rejected {marketing_rejected} marketing/promotional text blocks")
    logger.info(f"CIVB scraping yielded {len(facts)} facts")
    return facts


# ─── Validation ───────────────────────────────────────────────────────────────


def validate_facts(facts: list[dict]) -> None:
    """Run quality checks on extracted facts."""
    logger.info(f"\n{'='*60}")
    logger.info(f"VALIDATION REPORT — Bordeaux Scraper")
    logger.info(f"{'='*60}")
    logger.info(f"Total facts: {len(facts)}")

    # Domain breakdown
    domains = Counter(f["domain"] for f in facts)
    logger.info(f"\nDomain breakdown:")
    for domain, count in domains.most_common():
        logger.info(f"  {domain}: {count}")

    # Confidence breakdown
    confs = Counter(f.get("confidence", 1.0) for f in facts)
    logger.info(f"\nConfidence breakdown:")
    for conf, count in sorted(confs.items(), reverse=True):
        logger.info(f"  {conf}: {count}")

    # Source tag breakdown
    tag_counter = Counter()
    for f in facts:
        for t in f.get("tags", []):
            tag_counter[t] += 1
    logger.info(f"\nSource tags:")
    for tag, count in tag_counter.most_common(10):
        logger.info(f"  {tag}: {count}")

    # Length checks
    short = [f for f in facts if len(f["fact_text"].split()) < 5]
    long = [f for f in facts if len(f["fact_text"].split()) > 50]
    logger.info(f"\nShort facts (<5 words): {len(short)}")
    logger.info(f"Long facts (>50 words): {len(long)}")
    for f in short[:5]:
        logger.info(f"  SHORT: {f['fact_text']}")
    for f in long[:5]:
        logger.info(f"  LONG: {f['fact_text']}")

    # Entity population rate
    with_entities = sum(1 for f in facts if f.get("entities"))
    logger.info(f"\nFacts with entities: {with_entities}/{len(facts)} "
                f"({100*with_entities/max(len(facts),1):.1f}%)")

    # Near-duplicate check (limit to avoid O(n^2) on large sets)
    texts = [f["fact_text"].lower() for f in facts]
    dupes = 0
    check_limit = min(len(texts), 500)
    for i in range(check_limit):
        for j in range(i + 1, check_limit):
            if texts[i] in texts[j] or texts[j] in texts[i]:
                dupes += 1
    logger.info(f"\nNear-duplicate pairs (substring, checked {check_limit}): {dupes}")

    # Sample facts
    logger.info(f"\n10 random sample facts:")
    for f in random.sample(facts, min(10, len(facts))):
        logger.info(f"  [{f['domain']}] (conf={f.get('confidence', 1.0)}) {f['fact_text']}")


# ─── Main Collection ──────────────────────────────────────────────────────────


def collect_all_facts(
    wiki_source_id: str,
    wikidata_source_id: str,
    civb_source_id: str,
    scrape_civb: bool = True,
) -> list[dict]:
    """Collect all facts from all sources."""
    session = wiki_session()
    all_facts = []

    # Wikipedia key articles
    logger.info("--- Wikipedia: Key Articles ---")
    article_facts = _scrape_wikipedia_articles(session, wiki_source_id)
    logger.info(f"Key article facts: {len(article_facts)}")
    all_facts.extend(article_facts)

    # Wikipedia category crawl
    logger.info("--- Wikipedia: Category Crawl ---")
    category_facts = _scrape_wikipedia_categories(session, wiki_source_id)
    logger.info(f"Category facts: {len(category_facts)}")
    all_facts.extend(category_facts)

    # Wikidata
    logger.info("--- Wikidata SPARQL ---")
    wikidata_facts = _scrape_wikidata(wikidata_source_id)
    logger.info(f"Wikidata facts: {len(wikidata_facts)}")
    all_facts.extend(wikidata_facts)

    # CIVB website
    if scrape_civb:
        logger.info("--- CIVB website ---")
        civb_facts = _scrape_civb(civb_source_id)
        logger.info(f"CIVB facts: {len(civb_facts)}")
        all_facts.extend(civb_facts)

    # Deduplicate across sources (exact match)
    deduped = []
    seen_texts = set()
    for f in all_facts:
        key = f["fact_text"].lower().strip()
        if key not in seen_texts:
            seen_texts.add(key)
            deduped.append(f)

    # Substring dedup: if fact A is a substring of fact B, keep only B (the longer one)
    texts_lower = [f["fact_text"].lower().strip() for f in deduped]
    to_remove = set()
    for i in range(len(texts_lower)):
        if i in to_remove:
            continue
        for j in range(i + 1, len(texts_lower)):
            if j in to_remove:
                continue
            if texts_lower[i] in texts_lower[j]:
                to_remove.add(i)
            elif texts_lower[j] in texts_lower[i]:
                to_remove.add(j)
    if to_remove:
        logger.info(f"Substring dedup removed {len(to_remove)} facts")
        deduped = [f for idx, f in enumerate(deduped) if idx not in to_remove]

    logger.info(f"Total after dedup: {len(deduped)} (from {len(all_facts)} raw)")
    return deduped


# ─── Test Run ────────────────────────────────────────────────────────────────


def run_test(cleanup: bool = False) -> None:
    """Run a small test: fetch a few articles, insert, report, optionally clean up."""
    from src.utils.db import get_pg

    logger.info("=== TEST RUN: Bordeaux Scraper ===")
    wiki_sid = ensure_wiki_source("Bordeaux wine")

    session = wiki_session()

    test_articles = ["Pauillac", "Margaux AOC", "Saint-Julien AOC",
                     "Château Lafite Rothschild", "Bordeaux wine"]
    facts = []
    seen = set()
    for title in test_articles[:TEST_RUN_LIMIT]:
        extract, wikitext = fetch_article(session, title)
        if extract:
            atomic = extract_atomic_facts(
                extract, title,
                region_keywords=BORDEAUX_REGION_KEYWORDS,
            )
            for af in atomic:
                key = af["fact_text"].lower()
                if key not in seen:
                    seen.add(key)
                    facts.append({
                        **af,
                        "source_id": wiki_sid,
                        "subdomain": "bordeaux",
                        "entities": [{"type": "region", "name": title}],
                        "confidence": 0.9,
                        "tags": ["bordeaux", "wikipedia", "test"],
                    })

    logger.info(f"Test run generated {len(facts)} facts")
    if facts:
        inserted = insert_facts_batch(facts)
        logger.info(f"Inserted: {inserted}")

    for f in facts[:10]:
        logger.info(f"  [{f['domain']}] {f['fact_text']}")

    if cleanup and facts:
        conn = get_pg()
        cur = conn.cursor()
        for f in facts:
            cur.execute("DELETE FROM facts WHERE fact_text = %s", (f["fact_text"],))
        conn.commit()
        logger.info(f"Cleaned up {len(facts)} test facts")


# ─── CLI ──────────────────────────────────────────────────────────────────────


@click.command()
@click.option("--all", "run_all", is_flag=True, help="Run full extraction and insert into database")
@click.option("--list", "list_sections", is_flag=True, help="List available data sources")
@click.option("--dry-run", "dry_run", is_flag=True, help="Collect facts but don't insert into database")
@click.option("--validate", "validate", is_flag=True, help="Run quality checks on generated facts")
@click.option("--test-run", is_flag=True, help="Process a small sample, insert, and report")
@click.option("--cleanup", is_flag=True, help="With --test-run, delete inserted facts after reporting")
def main(run_all, list_sections, dry_run, validate, test_run, cleanup):
    """Bordeaux wine scraper — genuine external data only."""

    if list_sections:
        click.echo("Bordeaux Scraper — Data Sources:")
        click.echo("  1. Wikipedia: Bordeaux classification & appellation articles")
        click.echo("  2. Wikidata: Wine regions, appellations, wineries (SPARQL, country-scoped)")
        click.echo("  3. CIVB (bordeaux.com): Supplementary web scraping")
        return

    if test_run:
        run_test(cleanup=cleanup)
        return

    if not run_all and not dry_run and not validate:
        click.echo("Use --all, --dry-run, --validate, --test-run, or --list")
        return

    # Register sources
    wiki_sid = ensure_wiki_source("Bordeaux wine")
    wikidata_sid = ensure_wikidata_source("Bordeaux wine")
    civb_sid = ensure_source(
        name="CIVB (Bordeaux Wine Council)",
        url="https://www.bordeaux.com",
        source_type="official_body",
        tier="tier_2_authoritative",
        language="en",
    )

    # Collect facts
    facts = collect_all_facts(wiki_sid, wikidata_sid, civb_sid)

    if validate or dry_run:
        validate_facts(facts)

    if dry_run:
        logger.info(f"\nDRY RUN — {len(facts)} facts generated, not inserted")
        return

    if run_all:
        before = get_fact_count()
        inserted = insert_facts_batch(facts)
        after = get_fact_count()
        logger.info(f"Inserted {inserted} new facts (DB: {before} → {after})")


if __name__ == "__main__":
    main()
