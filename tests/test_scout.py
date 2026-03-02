"""Integration tests for the Scout class."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from scout.config import ScoutConfig
from scout.models import ContentType, MediaContent, SearchHit, WebContent
from scout.scout import Scout


@pytest.fixture
async def scout(tmp_path):
    config = ScoutConfig(
        db_path=str(tmp_path / "scout.db"),
        distill=False,
        search_expand=False,  # disable expansion in tests for predictable mock calls
    )
    s = await Scout.create(config)
    yield s
    await s.close()


class TestScoutFetch:
    @pytest.mark.asyncio
    async def test_search_query_routes_to_searcher(self, scout):
        mock_hits = [SearchHit(title="Result", url="https://example.com", snippet="A snippet")]
        scout.searcher = AsyncMock()
        scout.searcher.search = AsyncMock(return_value=mock_hits)

        result = await scout.fetch("python async patterns")

        assert result.content_type == ContentType.SEARCH
        assert "Search Results" in result.content_md

    @pytest.mark.asyncio
    async def test_web_url_routes_to_extractor(self, scout):
        mock_web = WebContent(
            url="https://example.com",
            title="Example",
            content_md="# Hello",
            word_count=1,
            extracted_at=datetime.now(timezone.utc),
        )

        with patch("scout.scout.extract_web", new_callable=AsyncMock, return_value=mock_web):
            result = await scout.fetch("https://example.com")

        assert result.content_type == ContentType.WEB_PAGE
        assert result.title == "Example"

    @pytest.mark.asyncio
    async def test_youtube_url_routes_to_media(self, scout):
        mock_media = MediaContent(
            url="https://www.youtube.com/watch?v=abc",
            title="Test Video",
            channel="TestChannel",
            duration_seconds=120,
            transcript="Hello world",
            extracted_at=datetime.now(timezone.utc),
        )

        with patch("scout.scout.extract_youtube", new_callable=AsyncMock, return_value=mock_media):
            result = await scout.fetch("https://www.youtube.com/watch?v=abc")

        assert result.content_type == ContentType.YOUTUBE
        assert result.title == "Test Video"
        assert "Transcript" in result.content_md

    @pytest.mark.asyncio
    async def test_cache_hit(self, scout):
        mock_hits = [SearchHit(title="R", url="https://e.com", snippet="s")]
        scout.searcher = AsyncMock()
        scout.searcher.search = AsyncMock(return_value=mock_hits)

        # First fetch — fills cache
        r1 = await scout.fetch("cache test query")
        assert r1.cached is False

        # Second fetch — should come from cache
        r2 = await scout.fetch("cache test query")
        assert r2.cached is True

    @pytest.mark.asyncio
    async def test_force_refresh_bypasses_cache(self, scout):
        mock_hits = [SearchHit(title="R", url="https://e.com", snippet="s")]
        scout.searcher = AsyncMock()
        scout.searcher.search = AsyncMock(return_value=mock_hits)

        await scout.fetch("force test query")
        r2 = await scout.fetch("force test query", force_refresh=True)
        assert r2.cached is False

    @pytest.mark.asyncio
    async def test_fetch_with_region_and_timelimit(self, scout):
        mock_hits = [SearchHit(title="R", url="https://e.com", snippet="s")]
        scout.searcher = AsyncMock()
        scout.searcher.search = AsyncMock(return_value=mock_hits)

        result = await scout.fetch("test query", region="fr-fr", timelimit="w")
        assert result.content_type == ContentType.SEARCH


class TestScoutDeepSearch:
    @pytest.mark.asyncio
    async def test_deep_search_returns_orchestrated(self, scout):
        mock_hits = [
            SearchHit(title="Result A", url="https://a.com", snippet="First result"),
            SearchHit(title="Result B", url="https://b.com", snippet="Second result"),
        ]
        scout.searcher = AsyncMock()
        scout.searcher.search = AsyncMock(return_value=mock_hits)

        orch = await scout.deep_search("python patterns", expand=True)

        assert orch.original_query == "python patterns"
        assert len(orch.expanded_queries) > 1
        assert len(orch.hits) > 0

    @pytest.mark.asyncio
    async def test_deep_search_no_expand(self, scout):
        mock_hits = [SearchHit(title="R", url="https://e.com", snippet="s")]
        scout.searcher = AsyncMock()
        scout.searcher.search = AsyncMock(return_value=mock_hits)

        orch = await scout.deep_search("test", expand=False)

        assert orch.expanded_queries == ["test"]
        scout.searcher.search.assert_called_once()
