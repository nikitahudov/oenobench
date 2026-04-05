"""
OenoBench — Academic Journal Scraper

Extracts scientific wine facts from open-access journal abstracts.

Sources:
    - OENO One (https://oeno-one.eu) — vine and wine sciences
    - Vitis (https://pub.jki.bund.de/index.php/VITIS) — grapevine research
    - Catalyst (AJEV) (https://www.ajevonline.org/content/catalyst)

Usage:
    python -m src.scrapers.academic --all
    python -m src.scrapers.academic --journal oeno
    python -m src.scrapers.academic --journal vitis
    python -m src.scrapers.academic --journal catalyst
    python -m src.scrapers.academic --dry-run
    python -m src.scrapers.academic --validate
    python -m src.scrapers.academic --list
"""

import random
import re
import time
from typing import Optional

import click
import requests
from bs4 import BeautifulSoup
from loguru import logger

from src.utils.facts import ensure_source, insert_fact, insert_facts_batch, get_fact_count

# ─── Configuration ────────────────────────────────────────────────────────────

USER_AGENT = "OenoBench-Research/1.0 (academic wine benchmark)"
REQUEST_DELAY = 5  # seconds between HTTP requests (academic sites, limited bandwidth)
REQUEST_TIMEOUT = 30  # seconds
TEST_RUN_LIMIT = 5  # max facts to extract per journal during --test-run

HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# ─── Journal Definitions ──────────────────────────────────────────────────────

JOURNALS = {
    "oeno": {
        "name": "OENO One",
        "base_url": "https://oeno-one.eu",
        "description": "International vine and wine sciences journal",
        "issue_index_url": "https://oeno-one.eu/issue/archive",
        "scraper": "_scrape_oeno",
        "verify_ssl": False,  # Site has SSL cert issues
    },
    "vitis": {
        "name": "Vitis - Journal of Grapevine Research",
        "base_url": "https://ojs.openagrar.de/index.php/VITIS",
        "description": "Grapevine research journal from Julius Kühn-Institut",
        "issue_index_url": "https://ojs.openagrar.de/index.php/VITIS/issue/archive",
        "scraper": "_scrape_vitis",
        "verify_ssl": True,
    },
    "catalyst": {
        "name": "Catalyst: Discovery into Practice (AJEV)",
        "base_url": "https://www.ajevonline.org",
        "description": "American Journal of Enology and Viticulture — Catalyst section",
        "issue_index_url": "https://www.ajevonline.org/content/early/recent",
        "scraper": "_scrape_catalyst",
        "verify_ssl": False,  # Site has SSL cert issues
    },
}


# ─── HTTP Helpers ─────────────────────────────────────────────────────────────

def _get_session() -> requests.Session:
    """Create a requests session with common headers."""
    session = requests.Session()
    session.headers.update(HEADERS)
    return session


def _fetch_page(session: requests.Session, url: str, verify: bool = True) -> Optional[BeautifulSoup]:
    """Fetch a page with rate limiting and error handling. Returns parsed soup."""
    time.sleep(REQUEST_DELAY)
    try:
        resp = session.get(url, timeout=REQUEST_TIMEOUT, verify=verify)
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "lxml")
    except requests.RequestException as e:
        logger.warning(f"Failed to fetch {url}: {e}")
        return None


# ─── Domain Classification ───────────────────────────────────────────────────

# Keywords for classifying facts into domains/subdomains
VITICULTURE_KEYWORDS = [
    "vine", "grapevine", "vineyard", "rootstock", "canopy", "pruning",
    "terroir", "soil", "irrigation", "drought", "water stress", "phenology",
    "veraison", "véraison", "ripening", "berry", "cluster", "leaf",
    "photosynthesis", "vigor", "vigour", "planting", "grafting", "clone",
    "phylloxera", "nematode", "downy mildew", "powdery mildew", "botrytis",
    "esca", "trunk disease", "pest", "insect", "fungal", "pathogen",
    "virus", "leafroll", "fanleaf", "growth", "shoot", "bud", "dormancy",
    "frost", "sunburn", "hail", "climate", "warming", "temperature",
    "precipitation", "altitude", "slope", "aspect", "exposure",
    "anthocyanin", "polyphenol", "tannin", "sugar accumulation",
    "acidity", "malic acid", "tartaric acid", "potassium",
]

WINEMAKING_KEYWORDS = [
    "fermentation", "yeast", "saccharomyces", "brettanomyces", "brett",
    "malolactic", "enzyme", "maceration", "extraction", "pressing",
    "crushing", "destemming", "must", "pomace", "lees", "racking",
    "fining", "filtration", "clarification", "stabilization", "bottling",
    "oak", "barrel", "aging", "ageing", "maturation", "oxidation",
    "reduction", "sulfite", "sulfur dioxide", "SO2", "pH", "volatile acidity",
    "ethanol", "alcohol", "glycerol", "ester", "aldehyde", "terpene",
    "thiol", "aroma", "flavor", "flavour", "sensory", "tasting",
    "mouthfeel", "astringency", "bitterness", "sweetness", "body",
    "color", "colour", "hue", "intensity", "phenolic", "anthocyanin",
    "proanthocyanidin", "catechin", "resveratrol", "vanillin", "eugenol",
    "furfural", "lactone", "guaiacol", "4-ethylphenol", "brett character",
    "cold soak", "carbonic maceration", "whole cluster",
    "chaptalisation", "chaptalization", "acidification", "deacidification",
    "micro-oxygenation", "micro-ox", "membrane", "reverse osmosis",
    "concentrate", "cryoextraction", "sparkling", "méthode champenoise",
    "riddling", "disgorgement", "dosage", "tirage", "autolysis",
]

GRAPE_KEYWORDS = [
    "cultivar", "variety", "varietal", "cabernet", "merlot", "pinot",
    "chardonnay", "sauvignon", "riesling", "syrah", "shiraz", "grenache",
    "tempranillo", "sangiovese", "nebbiolo", "barbera", "touriga",
    "mourvèdre", "viognier", "gewürztraminer", "muscat", "moscato",
    "grape variety", "vitis vinifera", "hybrid", "crossing",
]

REGION_KEYWORDS = [
    "appellation", "denomination", "DOC", "DOCG", "AOC", "AOP", "AVA",
    "bordeaux", "burgundy", "champagne", "rhône", "rhone", "loire",
    "alsace", "languedoc", "provence", "piedmont", "tuscany", "veneto",
    "rioja", "ribera", "priorat", "douro", "napa", "sonoma", "barossa",
    "marlborough", "stellenbosch", "mendoza",
]

BUSINESS_KEYWORDS = [
    "market", "consumer", "price", "export", "import", "trade",
    "label", "brand", "marketing", "packaging", "e-commerce",
    "wine tourism", "sustainability", "organic", "biodynamic",
    "certification", "regulation",
]


def classify_domain(text: str) -> tuple[str, Optional[str]]:
    """Classify a fact text into domain and optional subdomain."""
    text_lower = text.lower()

    # Count keyword matches per domain
    scores = {
        "viticulture": sum(1 for kw in VITICULTURE_KEYWORDS if kw in text_lower),
        "winemaking": sum(1 for kw in WINEMAKING_KEYWORDS if kw in text_lower),
        "grape_varieties": sum(1 for kw in GRAPE_KEYWORDS if kw in text_lower),
        "wine_regions": sum(1 for kw in REGION_KEYWORDS if kw in text_lower),
        "wine_business": sum(1 for kw in BUSINESS_KEYWORDS if kw in text_lower),
    }

    best_domain = max(scores, key=scores.get)
    if scores[best_domain] == 0:
        # Default for academic wine papers
        best_domain = "winemaking"

    # Subdomain assignment
    subdomain = None
    if best_domain == "viticulture":
        if any(kw in text_lower for kw in ["disease", "mildew", "botrytis", "esca",
                                             "pathogen", "virus", "pest", "insect",
                                             "phylloxera", "nematode", "fungal"]):
            subdomain = "plant_pathology"
        elif any(kw in text_lower for kw in ["soil", "terroir", "climate", "temperature",
                                              "precipitation", "altitude", "warming"]):
            subdomain = "terroir_climate"
        elif any(kw in text_lower for kw in ["irrigation", "water stress", "drought"]):
            subdomain = "water_management"
        elif any(kw in text_lower for kw in ["canopy", "pruning", "shoot", "leaf"]):
            subdomain = "canopy_management"
    elif best_domain == "winemaking":
        if any(kw in text_lower for kw in ["fermentation", "yeast", "saccharomyces",
                                            "malolactic", "enzyme"]):
            subdomain = "fermentation"
        elif any(kw in text_lower for kw in ["aroma", "flavor", "flavour", "sensory",
                                              "tasting", "mouthfeel"]):
            subdomain = "sensory_chemistry"
        elif any(kw in text_lower for kw in ["oak", "barrel", "aging", "ageing",
                                              "maturation"]):
            subdomain = "aging"
        elif any(kw in text_lower for kw in ["phenolic", "anthocyanin", "tannin",
                                              "resveratrol", "polyphenol"]):
            subdomain = "phenolic_chemistry"

    return best_domain, subdomain


# ─── Fact Extraction from Abstracts ───────────────────────────────────────────

# Patterns that indicate factual content in abstracts
FACTUAL_PATTERNS = [
    # Sentences with numerical data
    re.compile(r'[A-Z][^.]*\d+[\.,]?\d*\s*(%|mg|g|L|mL|µg|°C|°F|ppm|ha|kg|mm|cm)[^.]*\.'),
    # Sentences with comparisons
    re.compile(r'[A-Z][^.]*(?:higher|lower|greater|less|more|fewer|increased|decreased|reduced|enhanced|improved|significant(?:ly)?)\b[^.]*\.'),
    # Sentences with causation
    re.compile(r'[A-Z][^.]*(?:caused|resulted? in|led to|contributed to|associated with|correlated with|due to|because of|attributed to)\b[^.]*\.'),
    # Definitions and descriptions
    re.compile(r'[A-Z][^.]*(?:is defined as|is characterized by|refers to|consists of|comprises|contains|is composed of)\b[^.]*\.'),
    # Conclusions / findings
    re.compile(r'[A-Z][^.]*(?:findings? (?:suggest|indicate|show|demonstrate|reveal|confirm)|results? (?:suggest|indicate|show|demonstrate)|we found that|this study (?:shows|demonstrates|reveals|confirms))\b[^.]*\.', re.IGNORECASE),
    # Process descriptions
    re.compile(r'[A-Z][^.]*(?:converts?|produces?|transforms?|catalyzes?|inhibits?|promotes?|regulates?|modulates?|activates?|induces?)\b[^.]*\.'),
]

# Sentences to skip — too generic or meta
SKIP_PATTERNS = [
    re.compile(r'(?:this paper|this study|this article|this review|we review|the aim|the objective|the purpose|the goal|in this work|in this paper|in this study)', re.IGNORECASE),
    re.compile(r'(?:wine is (?:a|an|the) (?:beverage|drink|product))', re.IGNORECASE),
    re.compile(r'(?:grapes are (?:fruit|used|grown))', re.IGNORECASE),
    re.compile(r'^(?:Introduction|Background|Methods|Materials|Conclusions?|Results|Discussion|Acknowledgments?|References)\s*\.?$', re.IGNORECASE),
    re.compile(r'(?:further research|future (?:studies|work|research)|more (?:studies|research|work) (?:is|are) needed)', re.IGNORECASE),
]

# Wine-related entity patterns for extraction
ENTITY_PATTERNS = {
    "compound": re.compile(r'\b(?:anthocyanin|tannin|resveratrol|catechin|quercetin|phenol(?:ic)?|flavonoid|polyphenol|thiol|terpene|ester|aldehyde|vanillin|eugenol|furfural|lactone|guaiacol|ethylphenol|ethanol|glycerol|acetaldehyde|diacetyl|malic acid|tartaric acid|citric acid|lactic acid|acetic acid|succinic acid)\w*', re.IGNORECASE),
    "organism": re.compile(r'\b(?:Saccharomyces|Brettanomyces|Oenococcus|Lactobacillus|Botrytis|Erysiphe|Plasmopara|Phylloxera|Xylella|Vitis\s+vinifera)\b', re.IGNORECASE),
    "grape": re.compile(r'\b(?:Cabernet\s+Sauvignon|Merlot|Pinot\s+Noir|Pinot\s+Gris|Pinot\s+Blanc|Chardonnay|Sauvignon\s+Blanc|Riesling|Syrah|Shiraz|Grenache|Tempranillo|Sangiovese|Nebbiolo|Barbera|Mourvèdre|Viognier|Gewürztraminer|Muscat|Moscato|Malbec|Carménère|Touriga\s+Nacional|Verdejo|Albariño|Grüner\s+Veltliner|Garnacha|Monastrell|Primitivo|Zinfandel)\b', re.IGNORECASE),
    "process": re.compile(r'\b(?:fermentation|maceration|malolactic|micro-oxygenation|cold\s+soak|carbonic\s+maceration|whole\s+cluster|cryoextraction|chaptalisation|chaptalization|riddling|disgorgement|autolysis|fining|racking)\b', re.IGNORECASE),
}


def extract_entities(text: str) -> list[dict]:
    """Extract wine-related entities from a fact sentence."""
    entities = []
    seen = set()
    for etype, pattern in ENTITY_PATTERNS.items():
        for match in pattern.finditer(text):
            name = match.group(0).strip()
            name_key = name.lower()
            if name_key not in seen:
                seen.add(name_key)
                entities.append({"type": etype, "name": name})
    return entities


def _split_into_sentences(text: str) -> list[str]:
    """Split abstract text into individual sentences."""
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text.strip())
    # Split on sentence boundaries, avoiding splits on abbreviations
    sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z])', text)
    return [s.strip() for s in sentences if s.strip()]


def _is_factual_sentence(sentence: str) -> bool:
    """Check if a sentence contains factual claims worth extracting."""
    # Skip too-short or too-long sentences
    word_count = len(sentence.split())
    if word_count < 6 or word_count > 60:
        return False

    # Skip meta/generic sentences
    for pattern in SKIP_PATTERNS:
        if pattern.search(sentence):
            return False

    # Must match at least one factual pattern
    for pattern in FACTUAL_PATTERNS:
        if pattern.search(sentence):
            return True

    return False


def _rephrase_fact(sentence: str) -> str:
    """Rephrase an abstract sentence into an atomic fact.

    Removes hedging language, simplifies academic phrasing,
    and normalizes into a single declarative statement.
    Never returns verbatim text — always applies transformations.
    """
    fact = sentence.strip()

    # Remove citation references like (Author et al., 2020) or [1,2]
    fact = re.sub(r'\([^)]*(?:et al\.|(?:19|20)\d{2})[^)]*\)', '', fact)
    fact = re.sub(r'\[\d+(?:[,;\s]*\d+)*\]', '', fact)

    # Remove hedging / academic phrasing
    hedging = [
        (r'\b[Ii]t (?:has been|was) (?:shown|demonstrated|found|reported|observed) that\s+', ''),
        (r'\b[Oo]ur (?:results|findings|data) (?:show|indicate|suggest|demonstrate|reveal) that\s+', ''),
        (r'\b[Tt]he (?:results|findings|data) (?:show|indicate|suggest|demonstrate|reveal) that\s+', ''),
        (r'\b[Tt]hese (?:results|findings|data) (?:show|indicate|suggest|demonstrate|reveal) that\s+', ''),
        (r'\b[Ww]e (?:found|observed|demonstrated|showed|report) that\s+', ''),
        (r'\b[Ii]t (?:is|was) (?:well )?(?:known|established|recognized|documented) that\s+', ''),
        (r'\b[Pp]revious (?:studies|research|work) (?:has |have )?(?:shown|demonstrated|indicated) that\s+', ''),
        (r'\b(?:[Ii]n this study|[Ii]n the present study|[Hh]ere),?\s+', ''),
        (r'\b(?:may|might|could)\s+', ''),
        (r'\b(?:approximately|about|roughly|around)\s+', 'approximately '),
    ]

    for pattern, replacement in hedging:
        fact = re.sub(pattern, replacement, fact)

    # Capitalize first letter after transformations
    fact = fact.strip()
    if fact and fact[0].islower():
        fact = fact[0].upper() + fact[1:]

    # Clean up extra whitespace
    fact = re.sub(r'\s+', ' ', fact).strip()

    # Ensure ends with period
    if fact and not fact.endswith('.'):
        fact += '.'

    return fact


def extract_facts_from_abstract(
    abstract: str,
    doi: str,
    title: str,
    journal_name: str,
) -> list[dict]:
    """Extract atomic facts from a paper abstract.

    Returns a list of fact dicts ready for insert_facts_batch().
    """
    if not abstract or len(abstract) < 50:
        return []

    sentences = _split_into_sentences(abstract)
    facts = []
    seen_facts = set()

    for sentence in sentences:
        if not _is_factual_sentence(sentence):
            continue

        fact_text = _rephrase_fact(sentence)

        # Skip if rephrasing produced something too short or identical to seen
        if len(fact_text.split()) < 5:
            continue

        fact_lower = fact_text.lower()
        if fact_lower in seen_facts:
            continue
        seen_facts.add(fact_lower)

        domain, subdomain = classify_domain(fact_text)
        entities = extract_entities(fact_text)

        facts.append({
            "fact_text": fact_text,
            "domain": domain,
            "subdomain": subdomain,
            "entities": entities,
            "confidence": 0.85,  # abstracts have peer-reviewed content
            "tags": ["academic", journal_name.lower().replace(" ", "_"), "abstract"],
            "_doi": doi,
            "_title": title,
        })

    return facts


# ─── OENO One Scraper ─────────────────────────────────────────────────────────

def _scrape_oeno(session: requests.Session, dry_run: bool = False, max_issues: int = 10) -> list[dict]:
    """Scrape OENO One journal for article abstracts.

    OENO One uses OJS (Open Journal Systems) with a standard archive layout.
    """
    all_facts = []
    base_url = JOURNALS["oeno"]["base_url"]
    verify = JOURNALS["oeno"].get("verify_ssl", True)

    logger.info("Scraping OENO One issue archive...")
    archive_soup = _fetch_page(session, f"{base_url}/issue/archive", verify=verify)
    if not archive_soup:
        logger.error("Could not access OENO One archive page")
        return []

    # Find issue links — OJS uses various link patterns
    issue_links = []
    for link in archive_soup.select('a[href*="/issue/view/"]'):
        href = link.get("href", "")
        if href and href not in issue_links:
            if not href.startswith("http"):
                href = base_url + href
            issue_links.append(href)

    if not issue_links:
        # Try alternate OJS archive structure
        for link in archive_soup.find_all("a", href=True):
            href = link["href"]
            if "/issue/" in href and "/archive" not in href:
                if not href.startswith("http"):
                    href = base_url + href
                if href not in issue_links:
                    issue_links.append(href)

    logger.info(f"Found {len(issue_links)} issue links")
    issue_links = issue_links[:max_issues]

    for issue_url in issue_links:
        logger.info(f"Processing issue: {issue_url}")
        issue_soup = _fetch_page(session, issue_url, verify=verify)
        if not issue_soup:
            continue

        # Find article links — filter out galley sub-views, keep base article URLs only
        article_ids_seen = set()
        article_links = []
        for link in issue_soup.select('a[href*="/article/view/"]'):
            href = link.get("href", "")
            if not href:
                continue
            if not href.startswith("http"):
                href = base_url + href
            # Extract base article URL (strip galley suffix)
            match = re.search(r'(/article/view/\d+)', href)
            if match:
                base_article_url = href[:href.index(match.group(1)) + len(match.group(1))]
                article_id = match.group(1)
                if article_id not in article_ids_seen:
                    article_ids_seen.add(article_id)
                    article_links.append(base_article_url)

        if not article_links:
            for link in issue_soup.find_all("a", href=True):
                href = link["href"]
                if "/article/" in href and "/view/" in href:
                    if not href.startswith("http"):
                        href = base_url + href
                    match = re.search(r'(/article/view/\d+)', href)
                    if match:
                        base_article_url = href[:href.index(match.group(1)) + len(match.group(1))]
                        article_id = match.group(1)
                        if article_id not in article_ids_seen:
                            article_ids_seen.add(article_id)
                            article_links.append(base_article_url)

        logger.info(f"  Found {len(article_links)} articles in issue")

        for article_url in article_links:
            article_facts = _scrape_oeno_article(session, article_url, dry_run, verify=verify)
            all_facts.extend(article_facts)

    logger.info(f"OENO One: extracted {len(all_facts)} total facts")
    return all_facts


def _scrape_oeno_article(
    session: requests.Session,
    url: str,
    dry_run: bool = False,
    verify: bool = True,
) -> list[dict]:
    """Scrape a single OENO One article page for abstract and metadata."""
    soup = _fetch_page(session, url, verify=verify)
    if not soup:
        return []

    # Extract title
    title_tag = soup.find("h1", class_="page_title") or soup.find("h1")
    title = title_tag.get_text(strip=True) if title_tag else ""

    # Extract DOI
    doi = ""
    doi_link = soup.find("a", href=re.compile(r'doi\.org'))
    if doi_link:
        doi = doi_link.get("href", "")
    else:
        # Try meta tag
        doi_meta = soup.find("meta", attrs={"name": "citation_doi"})
        if doi_meta:
            doi = doi_meta.get("content", "")

    # Extract abstract — OJS typically uses specific divs/sections
    abstract = ""
    # Try common OJS abstract selectors
    for selector in [
        'div.item.abstract',
        'section.item.abstract',
        'div#abstract',
        'div.abstract',
        'section.abstract',
    ]:
        abstract_div = soup.select_one(selector)
        if abstract_div:
            # Remove the label "Abstract" if present
            label = abstract_div.find(['h2', 'h3', 'h4', 'label', 'strong'])
            if label:
                label.decompose()
            abstract = abstract_div.get_text(strip=True)
            break

    if not abstract:
        # Try meta tag fallback
        abstract_meta = soup.find("meta", attrs={"name": "DC.Description"})
        if abstract_meta:
            abstract = abstract_meta.get("content", "")

    if not title or not abstract:
        logger.debug(f"  Skipping article (no title/abstract): {url}")
        return []

    if not doi:
        doi = url  # Use article URL as fallback identifier

    logger.debug(f"  Article: {title[:80]}... (DOI: {doi})")

    facts = extract_facts_from_abstract(abstract, doi, title, "OENO One")

    if not dry_run and facts:
        # Register source for this paper
        source_id = ensure_source(
            name=f"OENO One — {title[:100]}",
            url=doi if doi.startswith("http") else f"https://doi.org/{doi}",
            source_type="academic_journal",
            tier="tier_2_authoritative",
        )
        for fact in facts:
            fact["source_id"] = source_id
            # Remove internal metadata keys
            fact.pop("_doi", None)
            fact.pop("_title", None)

    return facts


# ─── Vitis Scraper ────────────────────────────────────────────────────────────

def _scrape_vitis(session: requests.Session, dry_run: bool = False, max_issues: int = 10) -> list[dict]:
    """Scrape Vitis journal for article abstracts.

    Vitis uses OJS at ojs.openagrar.de (migrated from pub.jki.bund.de).
    """
    all_facts = []
    base_url = JOURNALS["vitis"]["base_url"]
    verify = JOURNALS["vitis"].get("verify_ssl", True)

    logger.info("Scraping Vitis issue archive...")
    archive_soup = _fetch_page(session, f"{base_url}/issue/archive", verify=verify)
    if not archive_soup:
        logger.error("Could not access Vitis archive page")
        return []

    # Find issue links
    issue_links = []
    for link in archive_soup.find_all("a", href=True):
        href = link["href"]
        if "/issue/view/" in href:
            if not href.startswith("http"):
                href = base_url.rsplit("/", 1)[0] + href if href.startswith("/") else base_url + "/" + href
            if href not in issue_links:
                issue_links.append(href)

    logger.info(f"Found {len(issue_links)} issue links")
    issue_links = issue_links[:max_issues]

    for issue_url in issue_links:
        logger.info(f"Processing issue: {issue_url}")
        issue_soup = _fetch_page(session, issue_url, verify=verify)
        if not issue_soup:
            continue

        # Find article links — filter out galley sub-views (e.g. /view/18180/17358)
        # Keep only base article URLs like /article/view/XXXXX
        article_ids_seen = set()
        article_links = []
        for link in issue_soup.find_all("a", href=True):
            href = link["href"]
            if "/article/view/" in href:
                if not href.startswith("http"):
                    href = base_url.rsplit("/", 1)[0] + href if href.startswith("/") else base_url + "/" + href
                # Extract base article URL (strip galley suffix like /17358)
                match = re.search(r'(/article/view/\d+)', href)
                if match:
                    base_article_url = href[:href.index(match.group(1)) + len(match.group(1))]
                    # Deduplicate by article ID
                    article_id = match.group(1)
                    if article_id not in article_ids_seen:
                        article_ids_seen.add(article_id)
                        article_links.append(base_article_url)

        logger.info(f"  Found {len(article_links)} articles in issue")

        for article_url in article_links:
            article_facts = _scrape_vitis_article(session, article_url, dry_run, verify=verify)
            all_facts.extend(article_facts)

    logger.info(f"Vitis: extracted {len(all_facts)} total facts")
    return all_facts


def _scrape_vitis_article(
    session: requests.Session,
    url: str,
    dry_run: bool = False,
    verify: bool = True,
) -> list[dict]:
    """Scrape a single Vitis article page for abstract and metadata."""
    soup = _fetch_page(session, url, verify=verify)
    if not soup:
        return []

    # Extract title
    title_tag = soup.find("h1", class_="page_title") or soup.find("h1")
    title = title_tag.get_text(strip=True) if title_tag else ""

    # Extract DOI
    doi = ""
    doi_meta = soup.find("meta", attrs={"name": "citation_doi"})
    if doi_meta:
        doi = doi_meta.get("content", "")
    else:
        doi_link = soup.find("a", href=re.compile(r'doi\.org'))
        if doi_link:
            doi = doi_link.get("href", "")

    # Extract abstract
    abstract = ""
    for selector in [
        'div.item.abstract',
        'section.item.abstract',
        'div#abstract',
        'div.abstract',
        'section.abstract',
    ]:
        abstract_div = soup.select_one(selector)
        if abstract_div:
            label = abstract_div.find(['h2', 'h3', 'h4', 'label', 'strong'])
            if label:
                label.decompose()
            abstract = abstract_div.get_text(strip=True)
            break

    if not abstract:
        abstract_meta = soup.find("meta", attrs={"name": "DC.Description"})
        if abstract_meta:
            abstract = abstract_meta.get("content", "")

    if not title or not abstract:
        logger.debug(f"  Skipping article (no title/abstract): {url}")
        return []

    if not doi:
        doi = url

    logger.debug(f"  Article: {title[:80]}... (DOI: {doi})")

    facts = extract_facts_from_abstract(abstract, doi, title, "Vitis")

    if not dry_run and facts:
        source_id = ensure_source(
            name=f"Vitis — {title[:100]}",
            url=doi if doi.startswith("http") else f"https://doi.org/{doi}",
            source_type="academic_journal",
            tier="tier_2_authoritative",
        )
        for fact in facts:
            fact["source_id"] = source_id
            fact.pop("_doi", None)
            fact.pop("_title", None)

    return facts


# ─── Catalyst (AJEV) Scraper ─────────────────────────────────────────────────

def _scrape_catalyst(session: requests.Session, dry_run: bool = False, max_pages: int = 5) -> list[dict]:
    """Scrape Catalyst (AJEV) for article abstracts.

    Catalyst uses HighWire Press platform (different from OJS).
    """
    all_facts = []
    base_url = JOURNALS["catalyst"]["base_url"]
    listing_url = JOURNALS["catalyst"]["issue_index_url"]
    verify = JOURNALS["catalyst"].get("verify_ssl", True)

    logger.info("Scraping Catalyst (AJEV) listing...")
    listing_soup = _fetch_page(session, listing_url, verify=verify)
    if not listing_soup:
        logger.error("Could not access Catalyst listing page")
        return []

    # Find article links — HighWire uses /content/ paths
    article_links = []
    for link in listing_soup.find_all("a", href=True):
        href = link["href"]
        # HighWire article URLs look like /content/X/Y/ZZZZ or /content/early/...
        if re.search(r'/content/(?:\d+/\d+/|early/)', href) and ".full" not in href and ".pdf" not in href:
            if not href.startswith("http"):
                href = base_url + href
            if href not in article_links:
                article_links.append(href)

    # Also check for article links within issue TOC pages
    toc_links = []
    for link in listing_soup.find_all("a", href=True):
        href = link["href"]
        if "/content/catalyst/" in href and href != listing_url:
            if not href.startswith("http"):
                href = base_url + href
            if href not in toc_links:
                toc_links.append(href)

    # Crawl TOC pages for more articles
    for toc_url in toc_links[:max_pages]:
        logger.info(f"Processing TOC page: {toc_url}")
        toc_soup = _fetch_page(session, toc_url, verify=verify)
        if not toc_soup:
            continue

        for link in toc_soup.find_all("a", href=True):
            href = link["href"]
            if re.search(r'/content/(?:\d+/\d+/|early/)', href) and ".full" not in href and ".pdf" not in href:
                if not href.startswith("http"):
                    href = base_url + href
                if href not in article_links:
                    article_links.append(href)

    logger.info(f"Found {len(article_links)} article links")

    for article_url in article_links:
        article_facts = _scrape_catalyst_article(session, article_url, dry_run, verify=verify)
        all_facts.extend(article_facts)

    logger.info(f"Catalyst: extracted {len(all_facts)} total facts")
    return all_facts


def _scrape_catalyst_article(
    session: requests.Session,
    url: str,
    dry_run: bool = False,
    verify: bool = True,
) -> list[dict]:
    """Scrape a single Catalyst/AJEV article page for abstract and metadata."""
    # Ensure we're fetching the abstract view
    abstract_url = url
    if not url.endswith(".abstract") and ".full" not in url:
        abstract_url = url.rstrip("/") + ".abstract"

    soup = _fetch_page(session, abstract_url, verify=verify)
    if not soup:
        # Try the base URL if .abstract doesn't work
        soup = _fetch_page(session, url, verify=verify)
        if not soup:
            return []

    # Extract title — HighWire uses specific id/class
    title = ""
    title_tag = soup.find("h1", id="article-title-1") or soup.find("h1", class_="highwire-cite-title")
    if title_tag:
        title = title_tag.get_text(strip=True)
    else:
        title_tag = soup.find("h1")
        if title_tag:
            title = title_tag.get_text(strip=True)

    # Extract DOI
    doi = ""
    doi_meta = soup.find("meta", attrs={"name": "citation_doi"})
    if doi_meta:
        doi = doi_meta.get("content", "")
    else:
        doi_link = soup.find("a", href=re.compile(r'doi\.org'))
        if doi_link:
            doi = doi_link.get("href", "")

    # Extract abstract — HighWire uses specific class
    abstract = ""
    for selector in [
        'div.section.abstract',
        'div#abstract-1',
        'div.abstract',
        'section.abstract',
    ]:
        abstract_div = soup.select_one(selector)
        if abstract_div:
            # Remove section title
            for heading in abstract_div.find_all(['h2', 'h3', 'h4']):
                heading.decompose()
            abstract = abstract_div.get_text(strip=True)
            break

    if not abstract:
        abstract_meta = soup.find("meta", attrs={"name": "DC.Description"})
        if abstract_meta:
            abstract = abstract_meta.get("content", "")

    if not title or not abstract:
        logger.debug(f"  Skipping article (no title/abstract): {url}")
        return []

    if not doi:
        doi = url

    logger.debug(f"  Article: {title[:80]}... (DOI: {doi})")

    facts = extract_facts_from_abstract(abstract, doi, title, "Catalyst AJEV")

    if not dry_run and facts:
        source_id = ensure_source(
            name=f"Catalyst (AJEV) — {title[:100]}",
            url=doi if doi.startswith("http") else f"https://doi.org/{doi}",
            source_type="academic_journal",
            tier="tier_2_authoritative",
        )
        for fact in facts:
            fact["source_id"] = source_id
            fact.pop("_doi", None)
            fact.pop("_title", None)

    return facts


# ─── Scraper Dispatch ─────────────────────────────────────────────────────────

SCRAPER_DISPATCH = {
    "_scrape_oeno": _scrape_oeno,
    "_scrape_vitis": _scrape_vitis,
    "_scrape_catalyst": _scrape_catalyst,
}


# ─── Validation ───────────────────────────────────────────────────────────────

def validate_facts():
    """Run quality checks on academic facts in the database.

    Prints distribution table, quality issues, and sample facts.
    """
    from src.utils.db import get_pg

    conn = get_pg()
    cur = conn.cursor()

    # Get all academic facts
    cur.execute("""
        SELECT f.fact_text, f.domain, f.subdomain, f.entities, f.tags
        FROM facts f
        JOIN sources s ON f.source_id = s.id
        WHERE s.source_type = 'academic_journal'
    """)
    rows = cur.fetchall()

    if not rows:
        click.echo("No academic journal facts found in database.")
        click.echo("Run --all or --journal first to scrape facts.")
        return

    total = len(rows)
    click.echo(f"\n{'='*60}")
    click.echo(f"  Academic Journal Facts — Validation Report")
    click.echo(f"  Total facts: {total}")
    click.echo(f"{'='*60}")

    # Domain distribution
    domain_counts: dict[str, int] = {}
    subdomain_counts: dict[str, int] = {}
    for row in rows:
        d = row["domain"]
        sd = row.get("subdomain") or "none"
        domain_counts[d] = domain_counts.get(d, 0) + 1
        key = f"{d}/{sd}"
        subdomain_counts[key] = subdomain_counts.get(key, 0) + 1

    click.echo(f"\n  Domain distribution:")
    for domain in sorted(domain_counts, key=domain_counts.get, reverse=True):
        count = domain_counts[domain]
        pct = count / total * 100
        click.echo(f"    {domain:25s}: {count:5d} facts ({pct:.1f}%)")

    click.echo(f"\n  Subdomain distribution:")
    for sd in sorted(subdomain_counts, key=subdomain_counts.get, reverse=True)[:15]:
        count = subdomain_counts[sd]
        pct = count / total * 100
        click.echo(f"    {sd:35s}: {count:5d} facts ({pct:.1f}%)")

    # Quality checks
    too_short = []
    too_long = []
    missing_entities = 0
    entity_name_only = []

    for row in rows:
        text = row["fact_text"]
        words = text.split()

        if len(words) < 5:
            too_short.append(text)
        if len(words) > 50:
            too_long.append(text)

        entities = row.get("entities")
        if not entities or entities == "[]":
            missing_entities += 1

        # Check for facts that are just entity names
        stripped = text.rstrip(".")
        if len(words) <= 2:
            entity_name_only.append(text)

    # Near-duplicate detection (simple string containment)
    near_dupes = 0
    fact_texts = [r["fact_text"] for r in rows]
    checked_pairs = set()
    for i, f1 in enumerate(fact_texts):
        f1_lower = f1.lower().rstrip(".")
        for j, f2 in enumerate(fact_texts):
            if i >= j:
                continue
            pair_key = (min(i, j), max(i, j))
            if pair_key in checked_pairs:
                continue
            checked_pairs.add(pair_key)
            f2_lower = f2.lower().rstrip(".")
            # Check if one fact is contained within the other
            if len(f1_lower) > 20 and len(f2_lower) > 20:
                if f1_lower in f2_lower or f2_lower in f1_lower:
                    near_dupes += 1
            # Also bail early to avoid O(n^2) explosion on large datasets
            if len(checked_pairs) > 50000:
                break
        if len(checked_pairs) > 50000:
            break

    # Generic fact detection
    generic_patterns = [
        re.compile(r'^wine is (?:a |an |the )', re.IGNORECASE),
        re.compile(r'^grapes are ', re.IGNORECASE),
        re.compile(r'^wine (?:can be|is) made from', re.IGNORECASE),
    ]
    generic_count = 0
    for row in rows:
        for gp in generic_patterns:
            if gp.search(row["fact_text"]):
                generic_count += 1
                break

    click.echo(f"\n  Quality:")
    click.echo(f"    Too short (<5 words):    {len(too_short):5d} ({len(too_short)/total*100:.1f}%)")
    click.echo(f"    Too long (>50 words):    {len(too_long):5d} ({len(too_long)/total*100:.1f}%)")
    click.echo(f"    Entity-name only:        {len(entity_name_only):5d} ({len(entity_name_only)/total*100:.1f}%)")
    click.echo(f"    Missing entities:        {missing_entities:5d} ({missing_entities/total*100:.1f}%)")
    click.echo(f"    Possible near-dupes:     {near_dupes:5d} ({near_dupes/total*100:.1f}%)")
    click.echo(f"    Too generic:             {generic_count:5d} ({generic_count/total*100:.1f}%)")

    # Entity coverage
    has_entities = total - missing_entities
    click.echo(f"\n  Entity coverage:")
    click.echo(f"    Facts with entities:     {has_entities:5d} ({has_entities/total*100:.1f}%)")
    click.echo(f"    Facts without entities:  {missing_entities:5d} ({missing_entities/total*100:.1f}%)")

    # Viticulture/winemaking ratio (specific to academic scraper)
    vit_count = domain_counts.get("viticulture", 0)
    wm_count = domain_counts.get("winemaking", 0)
    other_count = total - vit_count - wm_count
    click.echo(f"\n  Academic domain focus:")
    click.echo(f"    Viticulture:             {vit_count:5d} ({vit_count/total*100:.1f}%)")
    click.echo(f"    Winemaking:              {wm_count:5d} ({wm_count/total*100:.1f}%)")
    click.echo(f"    Other:                   {other_count:5d} ({other_count/total*100:.1f}%)")

    # Sample facts
    click.echo(f"\n  Sample facts (10 random):")
    sample_size = min(10, total)
    samples = random.sample(rows, sample_size)
    for i, row in enumerate(samples, 1):
        text = row["fact_text"]
        domain = row["domain"]
        click.echo(f"    {i:2d}. [{domain}] \"{text}\"")

    if too_short:
        click.echo(f"\n  Examples of too-short facts:")
        for t in too_short[:5]:
            click.echo(f"    - \"{t}\"")

    if too_long:
        click.echo(f"\n  Examples of too-long facts:")
        for t in too_long[:5]:
            click.echo(f"    - \"{t[:100]}...\"")

    click.echo(f"\n{'='*60}")


# ─── Main Pipeline ────────────────────────────────────────────────────────────

def run_journal(journal_key: str, dry_run: bool = False, max_issues: int = 10) -> int:
    """Scrape a single journal and store results. Returns facts inserted."""
    if journal_key not in JOURNALS:
        logger.error(f"Unknown journal: {journal_key}. Available: {list(JOURNALS.keys())}")
        return 0

    config = JOURNALS[journal_key]
    logger.info(f"Scraping journal: {config['name']} — {config['description']}")

    session = _get_session()
    scraper_fn = SCRAPER_DISPATCH[config["scraper"]]

    if journal_key == "catalyst":
        facts = scraper_fn(session, dry_run=dry_run, max_pages=max_issues)
    else:
        facts = scraper_fn(session, dry_run=dry_run, max_issues=max_issues)

    if dry_run:
        click.echo(f"\n[DRY RUN] Would insert {len(facts)} facts from {config['name']}")
        if facts:
            click.echo(f"\nSample facts:")
            for i, fact in enumerate(facts[:10], 1):
                click.echo(f"  {i}. [{fact['domain']}] \"{fact['fact_text']}\"")
                if fact.get("_doi"):
                    click.echo(f"     DOI: {fact['_doi']}")
        return 0

    if not facts:
        logger.warning(f"No facts extracted from {config['name']}")
        return 0

    inserted = insert_facts_batch(facts)
    logger.info(f"Inserted {inserted} new facts from {config['name']} (duplicates skipped)")
    return inserted


def run_all(dry_run: bool = False, max_issues: int = 10) -> dict:
    """Run all journal scrapers. Returns summary."""
    summary = {}
    total = 0

    for journal_key in JOURNALS:
        count = run_journal(journal_key, dry_run=dry_run, max_issues=max_issues)
        summary[journal_key] = count
        total += count

    logger.info(f"Academic scraping complete. Total new facts: {total}")
    if not dry_run:
        logger.info(f"Total facts in database: {get_fact_count()}")
    return summary


# ─── Test Run ────────────────────────────────────────────────────────────────

def _print_test_report(
    category_stats: dict[str, dict],
    all_facts: list[dict],
    all_inserted_ids: list[str],
) -> None:
    """Print the structured test-run report with quality checks."""
    click.echo("\n=== TEST RUN REPORT ===")
    click.echo("")

    # Table header
    header = (
        f"  {'Source/Category':<25s} {'Items Processed':>17s} "
        f"{'Facts Generated':>17s} {'Facts Inserted (new)':>22s}"
    )
    separator = "  " + "-" * 83
    click.echo(header)
    click.echo(separator)

    total_items = 0
    total_generated = 0
    total_inserted = 0

    for cat_name, stats in category_stats.items():
        items = stats["items_processed"]
        generated = stats["facts_generated"]
        inserted = stats["facts_inserted"]
        total_items += items
        total_generated += generated
        total_inserted += inserted
        click.echo(
            f"  {cat_name:<25s} {items:>17d} {generated:>17d} {inserted:>22d}"
        )

    click.echo(separator)
    click.echo(
        f"  {'TOTAL':<25s} {total_items:>17d} {total_generated:>17d} "
        f"{total_inserted:>22d}"
    )

    # Quality checks
    if not all_facts:
        click.echo("\n  No facts to analyze.")
        return

    total = len(all_facts)
    too_short = []
    too_long = []
    missing_entities = 0
    total_words = 0

    for f in all_facts:
        text = f["fact_text"]
        wc = len(text.split())
        total_words += wc

        if wc < 5:
            too_short.append(text)
        if wc > 50:
            too_long.append(text)
        if not f.get("entities"):
            missing_entities += 1

    avg_words = total_words / total if total else 0

    click.echo(f"\n  Quality Checks:")
    click.echo(
        f"    Too short (<5 words):  {len(too_short)} ({len(too_short)/total*100:.1f}%)"
    )
    click.echo(
        f"    Too long (>50 words):  {len(too_long)} ({len(too_long)/total*100:.1f}%)"
    )
    click.echo(
        f"    Missing entities:      {missing_entities} ({missing_entities/total*100:.1f}%)"
    )
    click.echo(f"    Avg words per fact:    {avg_words:.1f}")

    # Sample facts
    sample = random.sample(all_facts, min(10, len(all_facts)))
    click.echo(f"\n  Sample Facts ({min(10, len(all_facts))} random from this run):")
    for i, f in enumerate(sample, 1):
        click.echo(f"    {i:2d}. \"{f['fact_text']}\"")

    # Warnings
    warnings = []

    for cat_name, stats in category_stats.items():
        if stats["facts_inserted"] == 0 and stats["items_processed"] > 0:
            warnings.append(f"ERROR: No facts from {cat_name}")

        items = stats["items_processed"]
        generated = stats["facts_generated"]
        if items > 0 and generated / items < 2:
            warnings.append(
                f"WARNING: Low extraction rate in {cat_name} "
                f"({generated/items:.1f} facts/item)"
            )

        if items > 0 and generated > 0:
            skipped = generated - stats["facts_inserted"]
            if skipped / generated > 0.5:
                warnings.append(
                    f"WARNING: High duplicate rate in {cat_name} "
                    f"({skipped}/{generated} = {skipped/generated*100:.0f}% skipped)"
                )

    if len(too_short) / total > 0.1:
        warnings.append("WARNING: Too many trivial facts")

    if len(too_long) / total > 0.1:
        warnings.append("WARNING: Facts need better splitting")

    if warnings:
        click.echo(f"\n  Warnings:")
        for w in warnings:
            click.echo(f"    * {w}")
    else:
        click.echo(f"\n  No warnings — all checks passed.")


def run_test(journal_filter: Optional[str] = None, cleanup: bool = False) -> None:
    """Run a limited test extraction: first journal only, limited to 5 facts, insert, report."""
    session = _get_session()

    category_stats: dict[str, dict] = {}
    all_facts_collected: list[dict] = []
    all_inserted_ids: list[str] = []

    # Pick which journals to test
    if journal_filter:
        journal_keys = [journal_filter]
    else:
        # All journals for a representative test
        journal_keys = list(JOURNALS.keys())

    for journal_key in journal_keys:
        config = JOURNALS[journal_key]
        journal_name = config["name"]
        logger.info(f"Test run: scraping {journal_name}...")

        scraper_fn = SCRAPER_DISPATCH[config["scraper"]]
        # Use max_issues=1 to limit scope
        if journal_key == "catalyst":
            facts = scraper_fn(session, dry_run=False, max_pages=1)
        else:
            facts = scraper_fn(session, dry_run=False, max_issues=1)

        # Limit to TEST_RUN_LIMIT facts
        facts = facts[:TEST_RUN_LIMIT]
        generated = len(facts)
        items_processed = 1  # 1 issue/page processed

        # Insert individually to track IDs
        inserted_count = 0
        for fact in facts:
            # Ensure source_id is set (scrapers set it when dry_run=False)
            if "source_id" not in fact:
                source_id = ensure_source(
                    name=f"{journal_name} — test",
                    url=config["base_url"],
                    source_type="academic_journal",
                    tier="tier_2_authoritative",
                )
                fact["source_id"] = source_id

            fact_id = insert_fact(
                fact_text=fact["fact_text"],
                domain=fact["domain"],
                source_id=fact["source_id"],
                subdomain=fact.get("subdomain"),
                entities=fact.get("entities"),
                confidence=fact.get("confidence", 0.85),
                tags=fact.get("tags"),
            )
            if fact_id:
                all_inserted_ids.append(fact_id)
                inserted_count += 1

        all_facts_collected.extend(facts)
        category_stats[journal_name] = {
            "items_processed": items_processed,
            "facts_generated": generated,
            "facts_inserted": inserted_count,
        }

    _print_test_report(category_stats, all_facts_collected, all_inserted_ids)

    if cleanup and all_inserted_ids:
        from src.utils.db import get_pg
        pg = get_pg()
        cur = pg.cursor()
        cur.execute("DELETE FROM facts WHERE id = ANY(%s::uuid[])", (all_inserted_ids,))
        pg.commit()
        click.echo(f"\n  Cleaned up {len(all_inserted_ids)} test facts from database.")


# ─── CLI ──────────────────────────────────────────────────────────────────────

@click.command()
@click.option("--journal", "-j", type=click.Choice(["oeno", "vitis", "catalyst"]),
              help="Scrape a specific journal")
@click.option("--all", "run_all_flag", is_flag=True, help="Scrape all journals")
@click.option("--list", "list_journals", is_flag=True, help="List available journals")
@click.option("--dry-run", is_flag=True, help="Extract facts without inserting into database")
@click.option("--validate", is_flag=True, help="Run quality checks on stored academic facts")
@click.option("--max-issues", default=10, type=int, help="Max issues to scrape per journal (default: 10)")
@click.option("--test-run", is_flag=True, help="Process first journal (limited to 5 facts), insert, and report")
@click.option("--cleanup", is_flag=True, help="With --test-run, delete inserted facts after reporting")
def main(
    journal: Optional[str],
    run_all_flag: bool,
    list_journals: bool,
    dry_run: bool,
    validate: bool,
    max_issues: int,
    test_run: bool,
    cleanup: bool,
):
    """OenoBench Academic Journal Scraper — Extract wine science facts from open-access abstracts."""
    logger.add("data/logs/academic_{time}.log", rotation="10 MB")

    if list_journals:
        click.echo("\nAvailable journals:")
        for key, config in JOURNALS.items():
            click.echo(f"  {key:12s} — {config['name']}")
            click.echo(f"  {' ':12s}   {config['description']}")
            click.echo(f"  {' ':12s}   {config['base_url']}")
        return

    if validate:
        validate_facts()
        return

    if test_run:
        run_test(journal_filter=journal, cleanup=cleanup)
        return

    if run_all_flag:
        summary = run_all(dry_run=dry_run, max_issues=max_issues)
        click.echo(f"\n{'Summary':}")
        for name, count in summary.items():
            label = JOURNALS[name]["name"]
            click.echo(f"  {label:40s}: {count} facts")
        click.echo(f"  {'TOTAL':40s}: {sum(summary.values())} facts")
        return

    if journal:
        count = run_journal(journal, dry_run=dry_run, max_issues=max_issues)
        label = JOURNALS[journal]["name"]
        if dry_run:
            click.echo(f"\n[DRY RUN] Extracted facts shown above from {label}.")
        else:
            click.echo(f"\nInserted {count} new facts from {label}.")
        return

    click.echo("Use --all to scrape all journals, or --journal <name> for a specific one.")
    click.echo("Use --list to see available journals.")
    click.echo("Use --validate to check quality of stored facts.")
    click.echo("Use --dry-run to preview without inserting.")
    click.echo("Use --test-run to process first journal (5 facts) and report.")
    click.echo("Use --test-run --cleanup to auto-delete test facts after reporting.")


if __name__ == "__main__":
    main()
