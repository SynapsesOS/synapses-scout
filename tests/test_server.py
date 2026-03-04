"""Tests for the Scout HTTP server layer."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.testclient import TestClient

from scout.models import ContentType, ScoutResult, SearchHit
from scout.server import create_app


def _make_result(**kwargs) -> ScoutResult:
    defaults = dict(
        url="https://example.com",
        content_type=ContentType.WEB_PAGE,
        title="Test",
        content_md="# Test",
        word_count=2,
        fetched_at=datetime.now(timezone.utc),
    )
    defaults.update(kwargs)
    return ScoutResult(**defaults)


@pytest.fixture
def mock_scout():
    scout = MagicMock()
    scout.intelligence = MagicMock()
    scout.intelligence.available = AsyncMock(return_value=False)
    scout.cache = MagicMock()
    scout.cache.stats = AsyncMock(return_value={"total_entries": 0, "by_type": {}, "expired": 0})
    scout.cache.invalidate = AsyncMock(return_value=True)
    scout.cache.prune = AsyncMock(return_value=3)
    scout.cache.get_search = AsyncMock(return_value=None)
    scout.cache.put_search = AsyncMock(return_value=None)
    scout.fetch = AsyncMock(return_value=_make_result())
    scout.search = AsyncMock(return_value=[])
    scout.news = AsyncMock(return_value=[])
    scout.images = AsyncMock(return_value=[])
    scout.extract = AsyncMock(return_value=_make_result())
    scout.deep_search = AsyncMock(
        return_value=MagicMock(
            original_query="test",
            expanded_queries=["test"],
            hits=[],
            total_raw_hits=0,
            deduplicated_count=0,
        )
    )
    return scout


@pytest.fixture
def client(mock_scout):
    app = create_app()
    with patch("scout.server._get_scout", new_callable=AsyncMock, return_value=mock_scout):
        with TestClient(app, raise_server_exceptions=False) as c:
            yield c, mock_scout


class TestHealth:
    def test_health_returns_ok(self, client):
        c, _ = client
        resp = c.get("/v1/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "version" in data
        assert "intelligence_available" in data
        assert "cache" in data


class TestFetch:
    def test_fetch_success(self, client):
        c, _ = client
        resp = c.post("/v1/fetch", json={"input": "python async"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "Test"

    def test_fetch_missing_input_returns_400(self, client):
        c, _ = client
        resp = c.post("/v1/fetch", json={})
        assert resp.status_code == 400
        assert "error" in resp.json()

    def test_fetch_invalid_json_returns_400(self, client):
        c, _ = client
        resp = c.post(
            "/v1/fetch", content=b"not json", headers={"content-type": "application/json"}
        )
        assert resp.status_code == 400

    def test_fetch_exception_returns_500_json(self, client):
        c, mock_scout = client
        mock_scout.fetch = AsyncMock(side_effect=RuntimeError("boom"))
        resp = c.post("/v1/fetch", json={"input": "test"})
        assert resp.status_code == 500
        assert "error" in resp.json()

    def test_fetch_passes_max_results(self, client):
        c, mock_scout = client
        c.post("/v1/fetch", json={"input": "test", "max_results": 5})
        mock_scout.fetch.assert_called_once()
        _, kwargs = mock_scout.fetch.call_args
        assert kwargs["max_results"] == 5


class TestSearch:
    def test_search_returns_hits(self, client):
        c, mock_scout = client
        mock_scout.search = AsyncMock(
            return_value=[
                SearchHit(title="Result", url="https://a.com", snippet="snippet"),
            ]
        )
        resp = c.post("/v1/search", json={"query": "python"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        assert data["hits"][0]["title"] == "Result"

    def test_search_missing_query_returns_400(self, client):
        c, _ = client
        resp = c.post("/v1/search", json={})
        assert resp.status_code == 400

    def test_search_exception_returns_500_json(self, client):
        c, mock_scout = client
        mock_scout.search = AsyncMock(side_effect=RuntimeError("boom"))
        resp = c.post("/v1/search", json={"query": "test"})
        assert resp.status_code == 500
        assert "error" in resp.json()


class TestExtract:
    def test_extract_success(self, client):
        c, _ = client
        resp = c.post("/v1/extract", json={"url": "https://example.com"})
        assert resp.status_code == 200

    def test_extract_missing_url_returns_400(self, client):
        c, _ = client
        resp = c.post("/v1/extract", json={})
        assert resp.status_code == 400

    def test_extract_passes_force_refresh(self, client):
        c, mock_scout = client
        c.post("/v1/extract", json={"url": "https://example.com", "force_refresh": True})
        mock_scout.extract.assert_called_once()
        _, kwargs = mock_scout.extract.call_args
        assert kwargs["force_refresh"] is True


class TestDeepSearch:
    def test_deep_search_returns_structure(self, client):
        c, _ = client
        resp = c.post("/v1/deep-search", json={"query": "test"})
        assert resp.status_code == 200
        data = resp.json()
        assert "query" in data
        assert "expanded_queries" in data
        assert "hits" in data

    def test_deep_search_missing_query_returns_400(self, client):
        c, _ = client
        resp = c.post("/v1/deep-search", json={})
        assert resp.status_code == 400


class TestNews:
    def test_news_missing_query_returns_400(self, client):
        c, _ = client
        resp = c.post("/v1/news", json={})
        assert resp.status_code == 400

    def test_news_exception_returns_500_json(self, client):
        c, mock_scout = client
        mock_scout.news = AsyncMock(side_effect=RuntimeError("boom"))
        resp = c.post("/v1/news", json={"query": "test"})
        assert resp.status_code == 500
        assert "error" in resp.json()


class TestCache:
    def test_cache_get_stats(self, client):
        c, _ = client
        resp = c.get("/v1/cache")
        assert resp.status_code == 200

    def test_cache_delete_prunes(self, client):
        c, _ = client
        resp = c.delete("/v1/cache")
        assert resp.status_code == 200
        assert "pruned" in resp.json()

    def test_cache_delete_with_url_invalidates(self, client):
        import json as _json

        c, _ = client
        # Starlette TestClient wraps requests.Session; use request() for DELETE with body
        resp = c.request(
            "DELETE",
            "/v1/cache",
            data=_json.dumps({"url": "https://example.com"}),
            headers={"content-type": "application/json"},
        )
        assert resp.status_code == 200
        assert "invalidated" in resp.json()
