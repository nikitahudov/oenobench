"""
OenoBench — UC IPM Grape Pest Management Guidelines Scraper

Extracts viticulture facts from the UC Integrated Pest Management
program's Grape Pest Management Guidelines pages.

Source: https://ipm.ucanr.edu/agriculture/grape/

Usage:
    python -m src.scrapers.ucipm --all
    python -m src.scrapers.ucipm --dry-run
    python -m src.scrapers.ucipm --validate
    python -m src.scrapers.ucipm --list
    python -m src.scrapers.ucipm --test-run
    python -m src.scrapers.ucipm --test-run --cleanup
    python -m src.scrapers.ucipm --category diseases
    python -m src.scrapers.ucipm --category insects
"""

import random
import re
import time
from collections import defaultdict
from datetime import datetime
from typing import Optional
from urllib.parse import urljoin, urlparse

import click
import requests
from bs4 import BeautifulSoup, NavigableString
from loguru import logger

from src.utils.facts import (
    ensure_source,
    insert_facts_batch,
    insert_facts_batch_tracked,
    delete_facts_by_ids,
    get_fact_count,
)

# ─── Configuration ────────────────────────────────────────────────────────────

USER_AGENT = "OenoBench-Research/1.0 (academic wine benchmark)"
REQUEST_DELAY = 3.0  # 3 seconds between requests
REQUEST_TIMEOUT = 30

BASE_URL = "https://ipm.ucanr.edu/agriculture/grape/"

# Subdomain classification keywords
DISEASE_KEYWORDS = [
    "rot", "mildew", "blight", "canker", "dieback", "decline",
    "botrytis", "esca", "eutypa", "phomopsis", "anthracnose",
    "black measles", "pierce", "leafroll", "virus", "crown gall",
    "fungal", "fungus", "bacterial", "phytoplasma", "nematode",
]

PEST_KEYWORDS = [
    "mite", "mealybug", "leafhopper", "sharpshooter", "moth",
    "beetle", "weevil", "thrips", "scale", "aphid", "fly",
    "caterpillar", "borer", "worm", "cutworm", "omnivorous",
    "spider mite", "phylloxera", "insect", "larva", "larvae",
    "pest", "infestation",
]

MANAGEMENT_KEYWORDS = [
    "prune", "pruning", "irrigation", "canopy", "trellis",
    "cover crop", "spray", "sulfur", "copper", "fungicide",
    "insecticide", "miticide", "biological control", "cultural",
    "sanitation", "monitoring", "threshold", "degree-day",
    "dormant", "application", "treatment", "resistant",
    "rootstock", "cultivar",
]

# Categories used for --list and --category filtering
CATEGORIES = ["diseases", "insects", "nematodes", "disorders", "weeds", "other"]

# ─── HTTP Helpers ─────────────────────────────────────────────────────────────

_last_request_time: float = 0.0


def fetch_page(url: str, retries: int = 3) -> Optional[str]:
    """Fetch a web page with rate limiting and retries. Returns HTML or None."""
    global _last_request_time
    now = time.time()
    wait = REQUEST_DELAY - (now - _last_request_time)
    if wait > 0:
        logger.debug(f"Rate limiting: waiting {wait:.1f}s")
        time.sleep(wait)

    headers = {"User-Agent": USER_AGENT}
    for attempt in range(retries):
        try:
            resp = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
            _last_request_time = time.time()
            resp.raise_for_status()
            return resp.text
        except requests.RequestException as e:
            logger.warning(f"Fetch attempt {attempt + 1}/{retries} failed for {url}: {e}")
            if attempt < retries - 1:
                time.sleep(2 ** (attempt + 1))
    logger.error(f"Failed to fetch {url} after {retries} attempts")
    return None


# ─── Link Discovery ──────────────────────────────────────────────────────────

def discover_subpage_links() -> list[dict]:
    """Fetch the main grape IPM index page and extract links to subpages.

    Returns a list of dicts: {"url": ..., "title": ..., "category": ...}
    """
    html = fetch_page(BASE_URL)
    if not html:
        logger.error("Could not fetch main index page")
        return []

    soup = BeautifulSoup(html, "html.parser")
    links: list[dict] = []
    seen_urls: set[str] = set()

    # Search the entire page for grape subpage links
    content_areas = [soup]

    for area in content_areas:
        for a_tag in area.find_all("a", href=True):
            href = a_tag["href"]
            full_url = urljoin(BASE_URL, href)

            # Only follow links within the grape section of ipm.ucanr.edu
            parsed = urlparse(full_url)
            if "ipm.ucanr.edu" not in parsed.netloc:
                continue
            if "/agriculture/grape/" not in parsed.path:
                continue
            # Skip the index page itself, anchors, and fragment-only links
            if full_url.rstrip("/") == BASE_URL.rstrip("/"):
                continue
            if parsed.path.rstrip("/") == "/agriculture/grape":
                continue
            if href.startswith("#"):
                continue
            if full_url in seen_urls:
                continue

            title = a_tag.get_text(strip=True)
            if not title or len(title) < 3:
                continue

            seen_urls.add(full_url)
            category = _classify_link(title, full_url)
            links.append({
                "url": full_url,
                "title": title,
                "category": category,
            })

    logger.info(f"Discovered {len(links)} subpage links from index")
    for cat in CATEGORIES:
        count = sum(1 for l in links if l["category"] == cat)
        if count > 0:
            logger.info(f"  {cat}: {count} links")

    return links


def _classify_link(title: str, url: str) -> str:
    """Classify a subpage link into a category based on title and URL."""
    text = (title + " " + url).lower()

    if any(kw in text for kw in ["nematode"]):
        return "nematodes"
    if any(kw in text for kw in ["weed", "herbicide"]):
        return "weeds"
    if any(kw in text for kw in ["disorder", "physiological", "sunburn",
                                  "berry shrivel", "bunch-stem"]):
        return "disorders"

    # Check disease keywords
    disease_score = sum(1 for kw in DISEASE_KEYWORDS if kw in text)
    pest_score = sum(1 for kw in PEST_KEYWORDS if kw in text)

    if disease_score > pest_score:
        return "diseases"
    if pest_score > disease_score:
        return "insects"
    if disease_score > 0:
        return "diseases"
    if pest_score > 0:
        return "insects"

    return "other"


# ─── Content Extraction ──────────────────────────────────────────────────────

def extract_page_text(html: str) -> str:
    """Extract the main body text from a UC IPM page, stripping nav/headers/footers."""
    soup = BeautifulSoup(html, "html.parser")

    # Remove script, style, nav, header, footer elements
    for tag in soup.find_all(["script", "style", "nav", "header", "footer",
                              "noscript", "iframe"]):
        tag.decompose()

    # Try to find the main content area
    main_content = (
        soup.find("main")
        or soup.find("article")
        or soup.find("div", class_=re.compile(r"(field--name-body|content-area|main-content|node__content)", re.IGNORECASE))
        or soup.find("div", id=re.compile(r"(content|main)", re.IGNORECASE))
    )

    if main_content:
        text = main_content.get_text(separator="\n", strip=True)
    else:
        text = soup.get_text(separator="\n", strip=True)

    # Clean up excessive whitespace
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    return "\n".join(lines)


def split_into_sentences(text: str) -> list[str]:
    """Split text into sentences using regex-based splitting."""
    # Replace common abbreviations to avoid false splits
    text = re.sub(r"\b(Dr|Mr|Mrs|Ms|vs|etc|e\.g|i\.e|approx|ca|sp|spp)\.", r"\1<DOT>", text)
    text = re.sub(r"(\d)\.", r"\1<DOT>", text)  # Decimal numbers

    # Split on sentence-ending punctuation
    sentences = re.split(r"(?<=[.!?])\s+", text)

    # Restore dots
    sentences = [s.replace("<DOT>", ".") for s in sentences]

    # Filter: keep sentences with at least 4 words
    result = []
    for s in sentences:
        s = s.strip()
        if len(s.split()) >= 4 and len(s) > 20:
            result.append(s)
    return result


# ─── Fact Building ────────────────────────────────────────────────────────────

def _is_factual_sentence(sentence: str) -> bool:
    """Determine if a sentence contains a specific factual claim worth extracting.

    Filters for sentences with numbers, species names, treatment methods,
    or specific viticulture claims. Rejects navigational text, generic
    boilerplate, and purely instructional content with no data.
    """
    s_lower = sentence.lower()

    # Reject navigational / boilerplate
    reject_patterns = [
        r"^(click|select|visit|go to|see also|for more|read more)",
        r"^(home|menu|search|contact|about|skip to)",
        r"(copyright|all rights reserved|©)",
        r"^(pdf|print|share|email|subscribe)",
        r"^(table of contents|in this section)",
        r"(log\s*in|sign\s*up|register|account)",
        r"^(photo|image|figure|fig\.)",
    ]
    for pat in reject_patterns:
        if re.search(pat, s_lower):
            return False

    # Accept sentences with factual indicators
    factual_indicators = [
        # Numbers and measurements
        r"\d+",
        # Scientific names (italicized genus species)
        r"[A-Z][a-z]+ [a-z]+",
        # Chemical/treatment terms
        r"(sulfur|copper|fungicide|insecticide|pesticide|miticide|herbicide)",
        r"(spray|application|treatment|threshold|ppm|gallons|acres|percent|%)",
        # Biological terms
        r"(larva|larvae|nymph|adult|egg|spore|mycelium|overwinter)",
        r"(vector|host|pathogen|parasite|predator|parasitoid)",
        # Specific grape/vine terms
        r"(vine|grapevine|vineyard|berry|cluster|shoot|cane|trunk|cordon|spur)",
        r"(rootstock|cultivar|variety|scion|canopy)",
        # Disease/pest specifics
        r"(symptom|damage|infect|infest|lesion|discolor|wilt|necrosis|chlorosis)",
        # Management terms
        r"(prune|pruning|irrigation|dormant|bloom|veraison|harvest)",
        r"(biological control|cultural control|monitoring|degree.day)",
        # Cause/effect language
        r"(cause|result|lead to|associated with|transmitted by|spread)",
    ]

    match_count = sum(1 for pat in factual_indicators if re.search(pat, s_lower))
    return match_count >= 2


def _classify_subdomain(sentence: str, page_category: str) -> str:
    """Classify a fact's subdomain based on its content and the page category."""
    s_lower = sentence.lower()

    # Check for management/practice content first
    mgmt_score = sum(1 for kw in MANAGEMENT_KEYWORDS if kw in s_lower)
    disease_score = sum(1 for kw in DISEASE_KEYWORDS if kw in s_lower)
    pest_score = sum(1 for kw in PEST_KEYWORDS if kw in s_lower)

    if mgmt_score > disease_score and mgmt_score > pest_score:
        return "cultural_practices"
    if disease_score > pest_score:
        return "disease_management"
    if pest_score > disease_score:
        return "pest_management"

    # Fall back to page category
    category_map = {
        "diseases": "disease_management",
        "insects": "pest_management",
        "nematodes": "pest_management",
        "disorders": "disease_management",
        "weeds": "cultural_practices",
        "other": "cultural_practices",
    }
    return category_map.get(page_category, "cultural_practices")


def _extract_entities(sentence: str, page_title: str) -> list[dict]:
    """Extract entity mentions from a sentence."""
    entities: list[dict] = []

    # Scientific names: Genus species (capitalized + lowercase)
    sci_names = re.findall(r"\b([A-Z][a-z]{2,})\s+([a-z]{2,})\b", sentence)
    for genus, species in sci_names:
        # Filter out common English phrases that match the pattern
        if genus.lower() not in {"the", "this", "that", "these", "those", "they",
                                  "when", "where", "which", "while", "with",
                                  "each", "some", "many", "most", "other",
                                  "such", "than", "after", "before", "during",
                                  "under", "over", "between", "through"}:
            entities.append({"type": "organism", "name": f"{genus} {species}"})

    # Add page topic as entity
    if page_title:
        clean_title = page_title.strip()
        if clean_title and len(clean_title) > 2:
            entities.append({"type": "topic", "name": clean_title})

    return entities


def _generate_tags(sentence: str, page_category: str, subdomain: str) -> list[str]:
    """Generate tags for a fact."""
    tags = ["uc_ipm", "grape", page_category]
    s_lower = sentence.lower()

    if "organic" in s_lower:
        tags.append("organic")
    if any(w in s_lower for w in ["biological control", "biocontrol", "predator", "parasitoid"]):
        tags.append("biological_control")
    if any(w in s_lower for w in ["fungicide", "insecticide", "pesticide", "miticide"]):
        tags.append("chemical_control")
    if any(w in s_lower for w in ["monitor", "sampling", "trap", "threshold"]):
        tags.append("monitoring")
    if any(w in s_lower for w in ["overwinter", "dormant", "season"]):
        tags.append("seasonal")

    return list(set(tags))


def _clean_fact_text(sentence: str) -> str:
    """Clean up a sentence for use as a fact.

    Ensures the text is a proper atomic fact statement.
    """
    # Remove leading bullets, dashes, numbers
    s = re.sub(r"^[\s\-\*\u2022\u2013\u2014]+", "", sentence)
    s = re.sub(r"^\d+[\.\)]\s*", "", s)

    # Remove parenthetical references like (see page X) or (Figure 1)
    s = re.sub(r"\(see [^)]+\)", "", s)
    s = re.sub(r"\((Figure|Fig\.|Table|Photo)\s*\d*\)", "", s, flags=re.IGNORECASE)

    # Collapse whitespace
    s = re.sub(r"\s+", " ", s).strip()

    # Ensure it ends with a period
    if s and not s.endswith((".","!","?")):
        s += "."

    return s


def build_facts_from_page(
    page_url: str,
    page_title: str,
    page_category: str,
    source_id: str,
) -> list[dict]:
    """Fetch a single UC IPM subpage and extract facts from its content.

    Returns a list of fact dicts ready for insert_facts_batch.
    """
    html = fetch_page(page_url)
    if not html:
        return []

    text = extract_page_text(html)
    if not text:
        logger.warning(f"No text extracted from {page_url}")
        return []

    sentences = split_into_sentences(text)
    logger.debug(f"Page '{page_title}': {len(sentences)} sentences extracted")

    facts: list[dict] = []
    seen_texts: set[str] = set()

    for sentence in sentences:
        if not _is_factual_sentence(sentence):
            continue

        clean = _clean_fact_text(sentence)

        # Skip too-short or too-long facts
        word_count = len(clean.split())
        if word_count < 5 or word_count > 50:
            continue

        # Skip near-duplicates within the same page
        norm = clean.lower().strip()
        if norm in seen_texts:
            continue
        seen_texts.add(norm)

        subdomain = _classify_subdomain(clean, page_category)
        entities = _extract_entities(clean, page_title)
        tags = _generate_tags(clean, page_category, subdomain)

        facts.append({
            "fact_text": clean,
            "domain": "viticulture",
            "source_id": source_id,
            "subdomain": subdomain,
            "entities": entities,
            "confidence": 0.95,
            "tags": tags,
        })

    logger.info(f"Page '{page_title}': {len(facts)} facts extracted")
    return facts


# ─── Validation ───────────────────────────────────────────────────────────────

def validate_facts(facts: list[dict]) -> None:
    """Run quality checks on generated facts and print a report."""

    domain_counts: dict[str, int] = defaultdict(int)
    subdomain_counts: dict[str, int] = defaultdict(int)
    for f in facts:
        domain_counts[f["domain"]] += 1
        sd = f.get("subdomain") or "(none)"
        subdomain_counts[sd] += 1

    click.echo("\n" + "=" * 60)
    click.echo("VALIDATION REPORT — UC IPM Grape Pest Management")
    click.echo("=" * 60)

    click.echo("\nDomain distribution:")
    for d in sorted(domain_counts.keys()):
        click.echo(f"  {d:25s}: {domain_counts[d]:>5} facts")
    click.echo(f"  {'TOTAL':25s}: {len(facts):>5} facts")

    click.echo("\nSubdomain distribution:")
    for sd, cnt in sorted(subdomain_counts.items(), key=lambda x: -x[1]):
        click.echo(f"  {sd:30s}: {cnt:>5} facts")

    # Quality checks
    too_short = [f for f in facts if len(f["fact_text"].split()) < 5]
    too_long = [f for f in facts if len(f["fact_text"].split()) > 50]
    no_predicate = [f for f in facts if len(f["fact_text"].split()) <= 2
                    or not any(c in f["fact_text"] for c in ".!")]
    missing_entities = [f for f in facts if not f.get("entities")]

    # Near-duplicate detection via string containment
    near_dupes = []
    fact_texts = [f["fact_text"] for f in facts]
    sample_size = min(len(fact_texts), 500)
    sampled = random.sample(range(len(fact_texts)), sample_size) if fact_texts else []
    for i in range(len(sampled)):
        for j in range(i + 1, len(sampled)):
            a = fact_texts[sampled[i]].lower()
            b = fact_texts[sampled[j]].lower()
            if a != b and (a in b or b in a):
                near_dupes.append((fact_texts[sampled[i]], fact_texts[sampled[j]]))

    click.echo("\nQuality:")
    n = max(len(facts), 1)
    click.echo(f"  Too short (<5 words):   {len(too_short):>5} ({100 * len(too_short) / n:.1f}%)")
    click.echo(f"  Too long (>50 words):   {len(too_long):>5} ({100 * len(too_long) / n:.1f}%)")
    click.echo(f"  No predicate:           {len(no_predicate):>5} ({100 * len(no_predicate) / n:.1f}%)")
    click.echo(f"  Missing entities:       {len(missing_entities):>5} ({100 * len(missing_entities) / n:.1f}%)")
    click.echo(f"  Possible near-dupes:    {len(near_dupes):>5} ({100 * len(near_dupes) / n:.1f}%)")

    total_with_entities = len(facts) - len(missing_entities)
    click.echo(f"\n  % with entities:        {100 * total_with_entities / n:.1f}%")

    if too_short:
        click.echo("\nExamples of too-short facts:")
        for f in too_short[:5]:
            click.echo(f'  - "{f["fact_text"]}"')

    if too_long:
        click.echo("\nExamples of too-long facts:")
        for f in too_long[:5]:
            click.echo(f'  - "{f["fact_text"][:100]}..."')

    if near_dupes:
        click.echo("\nExamples of possible near-duplicates:")
        for a, b in near_dupes[:5]:
            click.echo(f'  A: "{a[:80]}..."')
            click.echo(f'  B: "{b[:80]}..."')
            click.echo()

    # Random sample
    sample = random.sample(facts, min(10, len(facts)))
    click.echo("\nSample facts (10 random):")
    for i, f in enumerate(sample, 1):
        click.echo(f'  {i:>2}. [{f.get("subdomain", "?")}] "{f["fact_text"]}"')

    click.echo("\n" + "=" * 60)


# ─── Pipeline ─────────────────────────────────────────────────────────────────

def register_source() -> str:
    """Register the UC IPM source and return its UUID."""
    return ensure_source(
        name="UC IPM — Grape Pest Management Guidelines",
        url="https://ipm.ucanr.edu/agriculture/grape/",
        source_type="government_extension",
        tier="tier_1_official",
        language="en",
    )


def scrape_all(
    source_id: str,
    dry_run: bool = False,
    category_filter: Optional[str] = None,
    max_pages: Optional[int] = None,
) -> list[dict]:
    """Discover subpages and scrape all of them for facts.

    Args:
        source_id: UUID of the registered source.
        dry_run: If True, do not insert into database.
        category_filter: Optional category to limit scraping.
        max_pages: Optional limit on number of pages to scrape.

    Returns:
        List of all extracted fact dicts.
    """
    links = discover_subpage_links()

    if category_filter:
        links = [l for l in links if l["category"] == category_filter]
        logger.info(f"Filtered to {len(links)} links in category '{category_filter}'")

    if max_pages:
        links = links[:max_pages]
        logger.info(f"Limited to {max_pages} pages")

    all_facts: list[dict] = []
    for i, link in enumerate(links, 1):
        logger.info(f"[{i}/{len(links)}] Scraping: {link['title']} ({link['url']})")
        page_facts = build_facts_from_page(
            page_url=link["url"],
            page_title=link["title"],
            page_category=link["category"],
            source_id=source_id,
        )
        all_facts.extend(page_facts)
        click.echo(f"  [{i}/{len(links)}] {link['title']}: {len(page_facts)} facts")

    logger.info(f"Total facts extracted: {len(all_facts)}")

    if dry_run:
        click.echo(f"\n[DRY RUN] {len(all_facts)} facts generated (not inserted)")
        if all_facts:
            click.echo("\nFirst 5 facts:")
            for f in all_facts[:5]:
                click.echo(f'  - [{f.get("subdomain")}] "{f["fact_text"]}"')
            if len(all_facts) > 5:
                click.echo(f"  ... and {len(all_facts) - 5} more")
    else:
        inserted = insert_facts_batch(all_facts)
        click.echo(f"\nInserted {inserted} new facts ({len(all_facts)} generated, duplicates skipped)")
        click.echo(f"Total viticulture facts in database: {get_fact_count('viticulture')}")

    return all_facts


# ─── Test Run ─────────────────────────────────────────────────────────────────

CATEGORY_MAP = {
    "pest_management": "ucipm/pest_management",
    "disease_management": "ucipm/disease_management",
    "cultural_practices": "ucipm/cultural_practices",
}


def _primary_entity_name(fact: dict) -> str:
    """Extract the primary entity name from a fact for item-grouping."""
    entities = fact.get("entities", [])
    if entities:
        return entities[0].get("name", "")
    return fact["fact_text"][:40]


def limit_facts_for_test_run(
    facts: list[dict], items_per_category: int = 5,
) -> tuple[list[dict], dict]:
    """Limit facts to first N unique items per subdomain.

    Returns (limited_facts, category_stats).
    """
    by_subdomain: dict[str, list[dict]] = defaultdict(list)
    for f in facts:
        sd = f.get("subdomain") or "(none)"
        by_subdomain[sd].append(f)

    limited: list[dict] = []
    stats: dict[str, dict] = {}

    for sd, sd_facts in by_subdomain.items():
        category = CATEGORY_MAP.get(sd, sd)

        seen_items: list[str] = []
        item_facts: list[dict] = []
        for fact in sd_facts:
            entity = _primary_entity_name(fact)
            if entity not in seen_items:
                if len(seen_items) >= items_per_category:
                    continue
                seen_items.append(entity)
            elif seen_items.index(entity) >= items_per_category:
                continue
            item_facts.append(fact)

        limited.extend(item_facts)
        stats[category] = {
            "items": len(seen_items),
            "facts": len(item_facts),
        }

    return limited, stats


def print_test_run_report(
    category_stats: dict[str, dict],
    all_facts: list[dict],
    inserted_count: int,
    inserted_ids: list[str],
    cleanup: bool = False,
) -> None:
    """Print a structured test-run report."""
    total_items = sum(s["items"] for s in category_stats.values())
    total_facts = sum(s["facts"] for s in category_stats.values())

    click.echo("\n=== TEST RUN REPORT — UC IPM ===")
    click.echo()
    click.echo(f"{'Source/Category':<40s} {'Items Processed':>16s} {'Facts Generated':>16s}")
    click.echo("-" * 74)

    for cat in sorted(category_stats.keys()):
        s = category_stats[cat]
        click.echo(f"  {cat:<38s} {s['items']:>14d} {s['facts']:>14d}")

    click.echo("-" * 74)
    click.echo(f"  {'TOTAL':<38s} {total_items:>14d} {total_facts:>14d}")
    click.echo(f"\n  Inserted: {inserted_count} (duplicates skipped: {total_facts - inserted_count})")

    # Quality checks
    too_short = [f for f in all_facts if len(f["fact_text"].split()) < 5]
    too_long = [f for f in all_facts if len(f["fact_text"].split()) > 50]
    missing_entities = [f for f in all_facts if not f.get("entities")]
    word_counts = [len(f["fact_text"].split()) for f in all_facts]
    avg_words = sum(word_counts) / max(len(word_counts), 1)

    click.echo()
    click.echo("  Quality Checks:")
    click.echo(f"    Too short (<5 words):  {len(too_short)} ({100 * len(too_short) / max(total_facts, 1):.1f}%)")
    click.echo(f"    Too long (>50 words):  {len(too_long)} ({100 * len(too_long) / max(total_facts, 1):.1f}%)")
    click.echo(f"    Missing entities:      {len(missing_entities)} ({100 * len(missing_entities) / max(total_facts, 1):.1f}%)")
    click.echo(f"    Avg words per fact:    {avg_words:.1f}")

    # Sample facts
    sample = random.sample(all_facts, min(10, len(all_facts)))
    click.echo()
    click.echo("  Sample Facts (10 random):")
    for i, f in enumerate(sample, 1):
        click.echo(f'    {i:>2}. "{f["fact_text"]}"')

    # Warnings
    warnings: list[str] = []
    for cat, s in category_stats.items():
        if s["facts"] == 0:
            warnings.append(f"ERROR: No facts from {cat}")
        elif s["items"] > 0 and s["facts"] / s["items"] < 2:
            warnings.append(f"WARNING: Low extraction rate in {cat} ({s['facts'] / s['items']:.1f} facts/item)")

    if inserted_count > 0:
        dup_rate = 1 - (inserted_count / max(total_facts, 1))
        if dup_rate > 0.5:
            warnings.append(f"WARNING: High duplicate rate ({dup_rate:.0%} skipped)")

    if warnings:
        click.echo()
        click.echo("  Warnings:")
        for w in warnings:
            click.echo(f"    {w}")

    # Cleanup
    if cleanup and inserted_ids:
        deleted = delete_facts_by_ids(inserted_ids)
        click.echo()
        click.echo(f"  Cleaned up {deleted} test facts from database")

    click.echo()


def run_test(cleanup: bool = False, items_per_category: int = 5) -> None:
    """Execute a test run: scrape a few pages, limit facts, insert, report."""
    source_id = register_source()

    # For test run, only scrape first 3 pages
    links = discover_subpage_links()
    test_links = links[:3]
    if not test_links:
        click.echo("No subpage links discovered. Cannot run test.")
        return

    click.echo(f"Test run: scraping {len(test_links)} pages (of {len(links)} discovered)")

    all_facts: list[dict] = []
    for i, link in enumerate(test_links, 1):
        logger.info(f"[TEST {i}/{len(test_links)}] {link['title']}")
        page_facts = build_facts_from_page(
            page_url=link["url"],
            page_title=link["title"],
            page_category=link["category"],
            source_id=source_id,
        )
        all_facts.extend(page_facts)

    limited, category_stats = limit_facts_for_test_run(all_facts, items_per_category)
    logger.info(f"[TEST RUN] Limited to {len(limited)} facts")

    inserted_count, inserted_ids = insert_facts_batch_tracked(limited)

    print_test_run_report(
        category_stats=category_stats,
        all_facts=limited,
        inserted_count=inserted_count,
        inserted_ids=inserted_ids,
        cleanup=cleanup,
    )


# ─── CLI ──────────────────────────────────────────────────────────────────────

@click.command()
@click.option("--all", "run_all_flag", is_flag=True, help="Scrape all UC IPM grape subpages")
@click.option("--category", type=click.Choice(CATEGORIES, case_sensitive=False),
              help="Scrape only a specific category")
@click.option("--dry-run", is_flag=True, help="Generate facts without inserting into database")
@click.option("--validate", "validate_flag", is_flag=True, help="Run quality checks on extracted facts")
@click.option("--list", "list_flag", is_flag=True, help="List discovered subpages and categories")
@click.option("--test-run", "test_run_flag", is_flag=True, help="Small test run with first 3 pages")
@click.option("--cleanup", is_flag=True, help="Delete test-run facts after report (use with --test-run)")
def main(
    run_all_flag: bool,
    category: Optional[str],
    dry_run: bool,
    validate_flag: bool,
    list_flag: bool,
    test_run_flag: bool,
    cleanup: bool,
):
    """OenoBench UC IPM Grape Pest Management Guidelines Scraper."""
    log_time = datetime.now().strftime("%Y%m%d_%H%M%S")
    logger.add(f"data/logs/ucipm_{log_time}.log", rotation="10 MB")

    if list_flag:
        click.echo("\nDiscovering UC IPM grape subpages...")
        links = discover_subpage_links()
        if not links:
            click.echo("No subpages found.")
            return
        click.echo(f"\nFound {len(links)} subpages:\n")
        by_cat: dict[str, list[dict]] = defaultdict(list)
        for l in links:
            by_cat[l["category"]].append(l)
        for cat in sorted(by_cat.keys()):
            click.echo(f"  {cat} ({len(by_cat[cat])} pages):")
            for l in by_cat[cat]:
                click.echo(f"    - {l['title']}")
                click.echo(f"      {l['url']}")
            click.echo()
        return

    if validate_flag:
        click.echo("Scraping pages for validation (dry run)...")
        source_id = "placeholder-ucipm"
        links = discover_subpage_links()
        all_facts: list[dict] = []
        for i, link in enumerate(links, 1):
            page_facts = build_facts_from_page(
                page_url=link["url"],
                page_title=link["title"],
                page_category=link["category"],
                source_id=source_id,
            )
            all_facts.extend(page_facts)
            click.echo(f"  [{i}/{len(links)}] {link['title']}: {len(page_facts)} facts")
        validate_facts(all_facts)
        return

    if test_run_flag:
        run_test(cleanup=cleanup)
        return

    if run_all_flag or category:
        source_id = register_source()
        scrape_all(
            source_id=source_id,
            dry_run=dry_run,
            category_filter=category,
        )
        return

    click.echo("UC IPM Grape Pest Management Guidelines Scraper")
    click.echo()
    click.echo("Usage:")
    click.echo("  --all           Scrape all grape pest management subpages")
    click.echo("  --category X    Scrape only a specific category (diseases, insects, etc.)")
    click.echo("  --dry-run       Generate facts without database insertion")
    click.echo("  --validate      Scrape and run quality checks (no DB writes)")
    click.echo("  --list          Discover and list available subpages")
    click.echo("  --test-run      Small test run with first 3 pages")
    click.echo("  --cleanup       Delete test facts after report (use with --test-run)")


if __name__ == "__main__":
    main()
