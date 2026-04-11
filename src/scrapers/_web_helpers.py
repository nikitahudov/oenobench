"""
OenoBench — Shared web scraping helpers.

Provides session management, page discovery, text extraction, and sitemap
parsing for official wine organization websites.

All HTTP requests use proper User-Agent, rate limiting, and retry logic.
"""

import re
import time
from typing import Optional
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup, Tag
from loguru import logger

# ─── Configuration ───────────────────────────────────────────────────────────

USER_AGENT = "OenoBench-Research/1.0 (academic wine benchmark)"
DEFAULT_TIMEOUT = 30
DEFAULT_DELAY = 3.0  # seconds between requests to same site
MAX_RETRIES = 3
BACKOFF_BASE = 2

# Tags to extract text from
_TEXT_TAGS = {"p", "li", "td", "h2", "h3", "h4", "blockquote", "dd"}

# Elements to skip (navigation, footer, etc.)
_SKIP_CLASSES = {
    "nav", "navbar", "navigation", "menu", "sidebar", "footer", "header",
    "breadcrumb", "pagination", "social", "share", "cookie", "banner",
    "popup", "modal", "advertisement", "ad", "widget", "comment",
}
_SKIP_IDS = {
    "nav", "navbar", "navigation", "menu", "sidebar", "footer", "header",
    "breadcrumb", "cookie-banner", "cookie-consent",
}


# ─── Session Management ─────────────────────────────────────────────────────


def create_session(
    base_url: str,
    extra_headers: Optional[dict] = None,
    delay: float = DEFAULT_DELAY,
) -> tuple[requests.Session, float]:
    """Create a requests.Session with browser-like headers and retry logic.

    Args:
        base_url: The site's base URL (used for Referer header).
        extra_headers: Additional headers to merge in.
        delay: Seconds between requests.

    Returns:
        (session, delay) tuple. Caller must sleep `delay` between calls.
    """
    session = requests.Session()
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,fr;q=0.8",
        "Accept-Encoding": "gzip, deflate",
        "Referer": base_url,
        "DNT": "1",
    }
    if extra_headers:
        headers.update(extra_headers)
    session.headers.update(headers)

    # Set up retry adapter
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry

    retry = Retry(
        total=MAX_RETRIES,
        backoff_factor=BACKOFF_BASE,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET", "HEAD"],
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)

    return session, delay


def fetch_page(
    session: requests.Session,
    url: str,
    delay: float = DEFAULT_DELAY,
    timeout: int = DEFAULT_TIMEOUT,
) -> Optional[BeautifulSoup]:
    """Fetch a page and return parsed BeautifulSoup, or None on failure.

    Includes rate limiting and error handling.
    """
    time.sleep(delay)
    try:
        resp = session.get(url, timeout=timeout)
        if resp.status_code == 403:
            logger.warning(f"Blocked (403) by {urlparse(url).netloc}")
            return None
        if resp.status_code == 404:
            logger.warning(f"Not found (404): {url}")
            return None
        resp.raise_for_status()
        return BeautifulSoup(resp.text, "html.parser")
    except requests.exceptions.RequestException as e:
        logger.warning(f"Failed to fetch {url}: {e}")
        return None


# ─── Page Discovery ──────────────────────────────────────────────────────────


def discover_pages(
    session: requests.Session,
    base_url: str,
    seed_paths: list[str],
    max_pages: int = 100,
    delay: float = DEFAULT_DELAY,
    url_filter: Optional[re.Pattern] = None,
) -> list[str]:
    """Discover internal pages by following links from seed pages.

    Args:
        session: Configured requests session.
        base_url: Site base URL (e.g., "https://www.bordeaux.com").
        seed_paths: Starting paths (e.g., ["/en/our-wines", "/en/vineyard"]).
        max_pages: Maximum pages to discover.
        delay: Seconds between requests.
        url_filter: Optional regex — only follow URLs matching this pattern.

    Returns:
        List of absolute URLs discovered.
    """
    parsed_base = urlparse(base_url)
    base_domain = parsed_base.netloc
    seen: set[str] = set()
    to_visit: list[str] = []
    discovered: list[str] = []

    # Build seed URLs
    for path in seed_paths:
        url = urljoin(base_url, path)
        if url not in seen:
            to_visit.append(url)
            seen.add(url)

    while to_visit and len(discovered) < max_pages:
        url = to_visit.pop(0)
        soup = fetch_page(session, url, delay=delay)
        if not soup:
            continue

        discovered.append(url)
        logger.debug(f"Discovered [{len(discovered)}/{max_pages}]: {url}")

        # Follow internal links
        for link in soup.find_all("a", href=True):
            href = link["href"]
            abs_url = urljoin(url, href)

            # Clean fragment and query
            abs_url = abs_url.split("#")[0].rstrip("/")
            if not abs_url:
                continue

            parsed = urlparse(abs_url)
            # Must be same domain
            if parsed.netloc and parsed.netloc != base_domain:
                continue
            # Must be http(s)
            if parsed.scheme and parsed.scheme not in ("http", "https"):
                continue

            abs_url = urljoin(url, href).split("#")[0].rstrip("/")
            if abs_url in seen:
                continue

            # Apply URL filter if provided
            if url_filter and not url_filter.search(abs_url):
                continue

            seen.add(abs_url)
            to_visit.append(abs_url)

    logger.info(f"Discovered {len(discovered)} pages from {base_url}")
    return discovered


# ─── Text Extraction ─────────────────────────────────────────────────────────


def _is_skip_element(tag: Tag) -> bool:
    """Check if a tag or its parents are navigation/footer/etc."""
    for parent in [tag] + list(tag.parents):
        if not isinstance(parent, Tag):
            continue
        classes = set(c.lower() for c in parent.get("class", []))
        if classes & _SKIP_CLASSES:
            return True
        tag_id = (parent.get("id") or "").lower()
        if tag_id in _SKIP_IDS:
            return True
        if parent.name in ("nav", "footer", "header", "aside"):
            return True
    return False


def extract_text_blocks(
    html_or_soup,
    min_words: int = 8,
    max_words: int = 60,
) -> list[str]:
    """Extract meaningful text blocks from HTML.

    Filters out navigation, footer, and other boilerplate.

    Args:
        html_or_soup: Raw HTML string or BeautifulSoup object.
        min_words: Minimum words for a text block.
        max_words: Maximum words for a text block.

    Returns:
        List of cleaned text strings.
    """
    if isinstance(html_or_soup, str):
        soup = BeautifulSoup(html_or_soup, "html.parser")
    else:
        soup = html_or_soup

    # Remove script, style, and other non-content tags
    for tag in soup.find_all(["script", "style", "noscript", "iframe"]):
        tag.decompose()

    blocks: list[str] = []
    seen: set[str] = set()

    for tag in soup.find_all(_TEXT_TAGS):
        if _is_skip_element(tag):
            continue

        text = tag.get_text(separator=" ", strip=True)
        if not text:
            continue

        # Clean up whitespace
        text = re.sub(r"\s+", " ", text).strip()

        # Length filter
        words = text.split()
        if len(words) < min_words or len(words) > max_words:
            continue

        # Dedup
        norm = text.lower()
        if norm in seen:
            continue
        seen.add(norm)

        blocks.append(text)

    return blocks


# ─── Sitemap ─────────────────────────────────────────────────────────────────


def try_sitemap(
    session: requests.Session,
    base_url: str,
    delay: float = DEFAULT_DELAY,
    url_filter: Optional[re.Pattern] = None,
    max_urls: int = 500,
) -> list[str]:
    """Try to parse sitemap.xml for valid page URLs.

    Checks both /sitemap.xml and /sitemap_index.xml.

    Args:
        session: Configured requests session.
        base_url: Site base URL.
        delay: Seconds between requests.
        url_filter: Optional regex to filter URLs.
        max_urls: Maximum URLs to return.

    Returns:
        List of URLs from sitemap, or empty list if no sitemap found.
    """
    import xml.etree.ElementTree as ET

    urls: list[str] = []
    sitemap_paths = ["/sitemap.xml", "/sitemap_index.xml"]

    for path in sitemap_paths:
        sitemap_url = urljoin(base_url, path)
        time.sleep(delay)
        try:
            resp = session.get(sitemap_url, timeout=DEFAULT_TIMEOUT)
            if resp.status_code != 200:
                continue

            root = ET.fromstring(resp.content)
            # Handle namespace
            ns = ""
            if root.tag.startswith("{"):
                ns = root.tag.split("}")[0] + "}"

            # Check if this is a sitemap index
            sitemaps = root.findall(f".//{ns}sitemap/{ns}loc")
            if sitemaps:
                # It's an index — fetch child sitemaps
                for sitemap_loc in sitemaps[:10]:  # Limit child sitemaps
                    child_url = sitemap_loc.text.strip()
                    time.sleep(delay)
                    try:
                        child_resp = session.get(child_url, timeout=DEFAULT_TIMEOUT)
                        if child_resp.status_code == 200:
                            child_root = ET.fromstring(child_resp.content)
                            for loc in child_root.findall(f".//{ns}url/{ns}loc"):
                                page_url = loc.text.strip()
                                if url_filter and not url_filter.search(page_url):
                                    continue
                                urls.append(page_url)
                                if len(urls) >= max_urls:
                                    break
                    except Exception:
                        continue
                    if len(urls) >= max_urls:
                        break
            else:
                # Direct sitemap
                for loc in root.findall(f".//{ns}url/{ns}loc"):
                    page_url = loc.text.strip()
                    if url_filter and not url_filter.search(page_url):
                        continue
                    urls.append(page_url)
                    if len(urls) >= max_urls:
                        break

            if urls:
                logger.info(f"Found {len(urls)} URLs in sitemap at {sitemap_url}")
                return urls

        except ET.ParseError:
            logger.debug(f"Failed to parse sitemap at {sitemap_url}")
        except requests.exceptions.RequestException as e:
            logger.debug(f"Failed to fetch sitemap at {sitemap_url}: {e}")

    logger.info(f"No sitemap found for {base_url}")
    return urls


# ─── Convenience ─────────────────────────────────────────────────────────────


def scrape_site_texts(
    base_url: str,
    seed_paths: list[str],
    max_pages: int = 50,
    delay: float = DEFAULT_DELAY,
    min_words: int = 8,
    max_words: int = 60,
    url_filter: Optional[re.Pattern] = None,
) -> list[tuple[str, list[str]]]:
    """High-level: discover pages on a site and extract text blocks from each.

    Args:
        base_url: Site base URL.
        seed_paths: Starting paths to crawl from.
        max_pages: Maximum pages to scrape.
        delay: Seconds between requests.
        min_words: Minimum words per text block.
        max_words: Maximum words per text block.
        url_filter: Optional regex to filter discovered URLs.

    Returns:
        List of (url, [text_blocks]) tuples.
    """
    session, delay = create_session(base_url, delay=delay)
    results: list[tuple[str, list[str]]] = []

    # Try sitemap first
    sitemap_urls = try_sitemap(session, base_url, delay=delay, url_filter=url_filter, max_urls=max_pages)

    if sitemap_urls:
        page_urls = sitemap_urls[:max_pages]
        logger.info(f"Using {len(page_urls)} URLs from sitemap")
    else:
        page_urls = discover_pages(
            session, base_url, seed_paths,
            max_pages=max_pages, delay=delay, url_filter=url_filter,
        )

    for url in page_urls:
        soup = fetch_page(session, url, delay=delay)
        if not soup:
            continue
        blocks = extract_text_blocks(soup, min_words=min_words, max_words=max_words)
        if blocks:
            results.append((url, blocks))

    logger.info(f"Extracted text from {len(results)} pages on {base_url}")
    return results
