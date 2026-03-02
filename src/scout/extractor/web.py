"""Web page extraction with fast-path (httpx + trafilatura) and browser fallback (Crawl4AI).

Fast path (<1s): httpx fetch + trafilatura extraction. Works for ~80% of pages (blogs,
articles, docs, wikis). No browser, no JS rendering.

Browser path (3-8s): Crawl4AI with Chromium. Used when fast path fails or content is
too thin (JS-heavy SPAs, pages behind JS rendering).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from functools import partial

import httpx
import trafilatura

from scout.config import ScoutConfig
from scout.models import WebContent

log = logging.getLogger(__name__)

# Pages shorter than this after fast extraction trigger browser fallback
_MIN_CONTENT_WORDS = 50

# Headers that make httpx look like a real browser
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Apple Silicon Mac OS X 14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
}


async def extract(url: str, config: ScoutConfig) -> WebContent:
    """Extract web content. Tries fast path first, falls back to browser if needed."""
    result = await _fast_extract(url, config)
    if result and result.word_count >= _MIN_CONTENT_WORDS:
        log.debug("fast path succeeded for %s (%d words)", url, result.word_count)
        return result

    log.debug("fast path insufficient for %s, falling back to browser", url)
    return await _browser_extract(url, config)


async def _fast_extract(url: str, config: ScoutConfig) -> WebContent | None:
    """Fast path: httpx + trafilatura. No browser, no JS. Returns None on failure."""
    try:
        async with httpx.AsyncClient(
            headers=_HEADERS,
            follow_redirects=True,
            timeout=15.0,
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            html = resp.text
    except Exception as e:
        log.debug("fast fetch failed for %s: %s", url, e)
        return None

    if not html or len(html) < 100:
        return None

    # trafilatura is sync — run in thread pool
    loop = asyncio.get_running_loop()
    extracted = await loop.run_in_executor(
        None, partial(_trafilatura_extract, html, url, config.max_content_chars)
    )
    if not extracted:
        return None

    markdown, title = extracted
    word_count = len(markdown.split())

    return WebContent(
        url=url,
        title=title,
        content_md=markdown,
        word_count=word_count,
        extracted_at=datetime.now(timezone.utc),
    )


def _trafilatura_extract(html: str, url: str, max_chars: int) -> tuple[str, str] | None:
    """Run trafilatura extraction (sync). Returns (markdown, title) or None."""
    result = trafilatura.extract(
        html,
        url=url,
        output_format="markdown",
        include_links=True,
        include_tables=True,
        include_images=False,
        include_comments=False,
        favor_recall=True,
    )
    if not result:
        return None

    if len(result) > max_chars:
        result = result[:max_chars]

    metadata = trafilatura.extract_metadata(html, default_url=url)
    title = ""
    if metadata:
        title = metadata.title or ""

    return result, title


async def _browser_extract(url: str, config: ScoutConfig) -> WebContent:
    """Browser path: Crawl4AI with Chromium. Slower but handles JS-heavy pages."""
    from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig

    browser_cfg = BrowserConfig(headless=True)
    run_cfg = CrawlerRunConfig(
        word_count_threshold=10,
        excluded_tags=["nav", "footer", "header"],
    )

    async with AsyncWebCrawler(config=browser_cfg) as crawler:
        result = await crawler.arun(url=url, config=run_cfg)

    markdown = result.markdown or ""
    if len(markdown) > config.max_content_chars:
        markdown = markdown[: config.max_content_chars]

    title = ""
    if result.metadata:
        title = result.metadata.get("title", "") or ""

    word_count = len(markdown.split())

    return WebContent(
        url=url,
        title=title,
        content_md=markdown,
        word_count=word_count,
        extracted_at=datetime.now(timezone.utc),
    )
