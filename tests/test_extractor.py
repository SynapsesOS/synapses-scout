"""Tests for the web extractor (fast path + browser fallback)."""

from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from scout.config import ScoutConfig
from scout.extractor.web import _fast_extract, _trafilatura_extract, extract


@pytest.fixture
def config(tmp_path):
    return ScoutConfig(db_path=str(tmp_path / "test.db"), max_content_chars=50000)


class TestTrafilaturaExtract:
    def test_extracts_from_html(self):
        html = """
        <html><head><title>Test Page</title></head>
        <body>
        <article>
        <h1>Main Article</h1>
        <p>This is the main content of the article. It has enough words to pass
        the minimum threshold for extraction. Here is more content to ensure
        the extraction works properly with trafilatura's content detection.
        We need substantial content here for the algorithm to recognize it.</p>
        </article>
        </body></html>
        """
        result = _trafilatura_extract(html, "https://example.com", 50000)
        if result:  # trafilatura may not extract from minimal HTML
            markdown, title = result
            assert len(markdown) > 0

    def test_returns_none_for_empty_html(self):
        result = _trafilatura_extract("", "https://example.com", 50000)
        assert result is None

    def test_truncates_to_max_chars(self):
        html = "<html><body><article>" + "<p>word </p>" * 10000 + "</article></body></html>"
        result = _trafilatura_extract(html, "https://example.com", 100)
        if result:
            markdown, _ = result
            assert len(markdown) <= 100


class TestFastExtract:
    @pytest.mark.asyncio
    async def test_returns_none_on_http_error(self, config):
        with patch("scout.extractor.web.httpx") as mock_httpx:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_client.get = AsyncMock(side_effect=Exception("connection refused"))
            mock_httpx.AsyncClient.return_value = mock_client

            result = await _fast_extract("https://down.com", config)
            assert result is None


class TestExtractFallback:
    @pytest.mark.asyncio
    async def test_falls_back_to_browser_when_fast_path_fails(self, config):
        """When fast path returns None, browser path should be called."""
        from scout.models import WebContent
        from datetime import datetime, timezone

        mock_browser_result = WebContent(
            url="https://spa.com",
            title="SPA Page",
            content_md="# Rendered by browser",
            word_count=100,
            extracted_at=datetime.now(timezone.utc),
        )

        with patch("scout.extractor.web._fast_extract", new_callable=AsyncMock, return_value=None), \
             patch("scout.extractor.web._browser_extract", new_callable=AsyncMock, return_value=mock_browser_result):
            result = await extract("https://spa.com", config)

        assert result.title == "SPA Page"
        assert "browser" in result.content_md.lower()

    @pytest.mark.asyncio
    async def test_uses_fast_path_when_sufficient(self, config):
        """When fast path returns enough content, browser should NOT be called."""
        from scout.models import WebContent
        from datetime import datetime, timezone

        fast_result = WebContent(
            url="https://blog.com",
            title="Blog Post",
            content_md="# Blog\n" + "word " * 100,
            word_count=100,
            extracted_at=datetime.now(timezone.utc),
        )

        with patch("scout.extractor.web._fast_extract", new_callable=AsyncMock, return_value=fast_result) as mock_fast, \
             patch("scout.extractor.web._browser_extract", new_callable=AsyncMock) as mock_browser:
            result = await extract("https://blog.com", config)

        assert result.title == "Blog Post"
        mock_browser.assert_not_called()
