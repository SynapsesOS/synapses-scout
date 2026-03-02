"""Tests for SQLite cache layer."""

import pytest

from scout.cache import Cache, normalize_url, query_hash, url_hash
from scout.models import ContentType, ScoutFragment, ScoutResult


class TestNormalization:
    def test_normalize_strips_tracking(self):
        url = "https://example.com/page?utm_source=twitter&id=42"
        normalized = normalize_url(url)
        assert "utm_source" not in normalized
        assert "id=42" in normalized

    def test_normalize_lowercases_host(self):
        assert "example.com" in normalize_url("https://EXAMPLE.COM/Page")

    def test_normalize_strips_trailing_slash(self):
        a = normalize_url("https://example.com/page/")
        b = normalize_url("https://example.com/page")
        assert a == b

    def test_url_hash_deterministic(self):
        h1 = url_hash("https://example.com/page")
        h2 = url_hash("https://example.com/page")
        assert h1 == h2
        assert len(h1) == 32

    def test_query_hash_normalizes_whitespace(self):
        h1 = query_hash("python   async")
        h2 = query_hash("python async")
        assert h1 == h2


@pytest.fixture
async def cache(tmp_path):
    c = await Cache.open(tmp_path / "test.db")
    yield c
    await c.close()


class TestCacheOps:
    @pytest.mark.asyncio
    async def test_put_and_get(self, cache):
        result = ScoutResult(
            url="https://example.com/test",
            content_type=ContentType.WEB_PAGE,
            title="Test",
            content_md="# Hello",
            word_count=1,
        )
        await cache.put(result, ttl_hours=24)
        got = await cache.get("https://example.com/test")
        assert got is not None
        assert got.title == "Test"
        assert got.cached is True

    @pytest.mark.asyncio
    async def test_get_missing_returns_none(self, cache):
        got = await cache.get("https://nonexistent.com")
        assert got is None

    @pytest.mark.asyncio
    async def test_expired_returns_none(self, cache):
        result = ScoutResult(
            url="https://example.com/expired",
            content_type=ContentType.WEB_PAGE,
            title="Expired",
            content_md="old",
            word_count=1,
        )
        await cache.put(result, ttl_hours=0)  # expires immediately
        got = await cache.get("https://example.com/expired")
        assert got is None

    @pytest.mark.asyncio
    async def test_invalidate(self, cache):
        result = ScoutResult(
            url="https://example.com/remove",
            content_type=ContentType.WEB_PAGE,
            title="Remove",
            content_md="bye",
            word_count=1,
        )
        await cache.put(result, ttl_hours=24)
        removed = await cache.invalidate("https://example.com/remove")
        assert removed is True
        got = await cache.get("https://example.com/remove")
        assert got is None

    @pytest.mark.asyncio
    async def test_fragment_persists(self, cache):
        result = ScoutResult(
            url="https://example.com/distilled",
            content_type=ContentType.WEB_PAGE,
            title="Distilled",
            content_md="content",
            word_count=1,
            fragment=ScoutFragment(summary="A great article", tags=["python", "async"]),
        )
        await cache.put(result, ttl_hours=24)
        got = await cache.get("https://example.com/distilled")
        assert got is not None
        assert got.fragment is not None
        assert got.fragment.summary == "A great article"
        assert got.fragment.tags == ["python", "async"]

    @pytest.mark.asyncio
    async def test_search_cache(self, cache):
        await cache.put_search(
            "test query", "duckduckgo", [{"title": "T", "url": "u", "snippet": "s"}], 6
        )
        got = await cache.get_search("test query")
        assert got is not None
        assert got["provider"] == "duckduckgo"
        assert len(got["results"]) == 1

    @pytest.mark.asyncio
    async def test_stats(self, cache):
        result = ScoutResult(
            url="https://example.com/stats",
            content_type=ContentType.WEB_PAGE,
            title="Stats",
            content_md="x",
            word_count=1,
        )
        await cache.put(result, ttl_hours=24)
        stats = await cache.stats()
        assert stats["total_entries"] >= 1
