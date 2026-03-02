"""Tests for IntelligenceClient — distillation and availability caching."""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from scout.distiller.client import _AVAILABILITY_TTL, _DISTILL_MAX_CHARS, IntelligenceClient
from scout.models import ScoutFragment


@pytest.fixture
def client():
    return IntelligenceClient("http://localhost:11435", timeout_ms=1000)


class TestAvailability:
    @pytest.mark.asyncio
    async def test_available_true_when_health_ok_and_ollama_up(self, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"status": "ok", "available": True}

        with patch.object(client._client, "get", new_callable=AsyncMock, return_value=mock_resp):
            result = await client.available()

        assert result is True

    @pytest.mark.asyncio
    async def test_available_false_when_ollama_down(self, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"status": "ok", "available": False}

        with patch.object(client._client, "get", new_callable=AsyncMock, return_value=mock_resp):
            result = await client.available()

        assert result is False

    @pytest.mark.asyncio
    async def test_available_false_on_connection_error(self, client):
        with patch.object(
            client._client, "get", new_callable=AsyncMock, side_effect=httpx.ConnectError("refused")
        ):
            result = await client.available()

        assert result is False

    @pytest.mark.asyncio
    async def test_availability_cached_within_ttl(self, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"available": True}

        with patch.object(
            client._client, "get", new_callable=AsyncMock, return_value=mock_resp
        ) as mock_get:
            await client.available()
            await client.available()  # second call — should use cache
            assert mock_get.call_count == 1

    @pytest.mark.asyncio
    async def test_availability_refreshed_after_ttl(self, client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"available": True}

        with patch.object(
            client._client, "get", new_callable=AsyncMock, return_value=mock_resp
        ) as mock_get:
            await client.available()
            # Expire the cache
            client._available_checked_at = time.monotonic() - _AVAILABILITY_TTL - 1
            await client.available()
            assert mock_get.call_count == 2


class TestDistill:
    @pytest.mark.asyncio
    async def test_distill_returns_fragment_on_success(self, client):
        health_resp = MagicMock()
        health_resp.status_code = 200
        health_resp.json.return_value = {"available": True}

        ingest_resp = MagicMock()
        ingest_resp.status_code = 200
        ingest_resp.json.return_value = {
            "summary": "A great article about Python.",
            "tags": ["python", "programming"],
        }

        with patch.object(client._client, "get", new_callable=AsyncMock, return_value=health_resp):
            with patch.object(
                client._client, "post", new_callable=AsyncMock, return_value=ingest_resp
            ):
                result = await client.distill(
                    "content here", "My Title", "https://example.com", "web_page"
                )

        assert isinstance(result, ScoutFragment)
        assert result.summary == "A great article about Python."
        assert "python" in result.tags
        assert "intelligence@" in result.distilled_by

    @pytest.mark.asyncio
    async def test_distill_returns_none_when_unavailable(self, client):
        # Force available = False
        client._available = False
        client._available_checked_at = time.monotonic()

        result = await client.distill("content", "title", "https://x.com", "web_page")

        assert result is None

    @pytest.mark.asyncio
    async def test_distill_truncates_content_to_max_chars(self, client):
        health_resp = MagicMock()
        health_resp.status_code = 200
        health_resp.json.return_value = {"available": True}

        ingest_resp = MagicMock()
        ingest_resp.status_code = 200
        ingest_resp.json.return_value = {"summary": "ok", "tags": []}

        long_content = "x" * 10_000

        with patch.object(client._client, "get", new_callable=AsyncMock, return_value=health_resp):
            with patch.object(
                client._client, "post", new_callable=AsyncMock, return_value=ingest_resp
            ) as mock_post:
                await client.distill(long_content, "Title", "https://x.com", "web_page")

        payload = mock_post.call_args.kwargs["json"]
        assert len(payload["code"]) == _DISTILL_MAX_CHARS

    @pytest.mark.asyncio
    async def test_distill_uses_correct_node_type_for_web(self, client):
        health_resp = MagicMock()
        health_resp.status_code = 200
        health_resp.json.return_value = {"available": True}

        ingest_resp = MagicMock()
        ingest_resp.status_code = 200
        ingest_resp.json.return_value = {"summary": "ok", "tags": []}

        with patch.object(client._client, "get", new_callable=AsyncMock, return_value=health_resp):
            with patch.object(
                client._client, "post", new_callable=AsyncMock, return_value=ingest_resp
            ) as mock_post:
                await client.distill("content", "Title", "https://example.com", "web_page")

        payload = mock_post.call_args.kwargs["json"]
        assert payload["node_type"] == "web article"
        assert payload["package"] == "example.com"
        assert payload["node_id"].startswith("scout:web_page:")

    @pytest.mark.asyncio
    async def test_distill_uses_correct_node_type_for_youtube(self, client):
        health_resp = MagicMock()
        health_resp.status_code = 200
        health_resp.json.return_value = {"available": True}

        ingest_resp = MagicMock()
        ingest_resp.status_code = 200
        ingest_resp.json.return_value = {"summary": "ok", "tags": []}

        with patch.object(client._client, "get", new_callable=AsyncMock, return_value=health_resp):
            with patch.object(
                client._client, "post", new_callable=AsyncMock, return_value=ingest_resp
            ) as mock_post:
                await client.distill(
                    "transcript", "Video", "https://youtube.com/watch?v=x", "youtube"
                )

        payload = mock_post.call_args.kwargs["json"]
        assert payload["node_type"] == "youtube video"

    @pytest.mark.asyncio
    async def test_distill_returns_none_on_ingest_error(self, client):
        health_resp = MagicMock()
        health_resp.status_code = 200
        health_resp.json.return_value = {"available": True}

        with patch.object(client._client, "get", new_callable=AsyncMock, return_value=health_resp):
            with patch.object(
                client._client,
                "post",
                new_callable=AsyncMock,
                side_effect=httpx.TimeoutException("timeout"),
            ):
                result = await client.distill("content", "title", "https://x.com", "web_page")

        assert result is None
        # Cache should be invalidated so next call retries health check
        assert client._available is None

    @pytest.mark.asyncio
    async def test_distill_title_truncated_to_80_chars(self, client):
        health_resp = MagicMock()
        health_resp.status_code = 200
        health_resp.json.return_value = {"available": True}

        ingest_resp = MagicMock()
        ingest_resp.status_code = 200
        ingest_resp.json.return_value = {"summary": "ok", "tags": []}

        long_title = "A" * 200

        with patch.object(client._client, "get", new_callable=AsyncMock, return_value=health_resp):
            with patch.object(
                client._client, "post", new_callable=AsyncMock, return_value=ingest_resp
            ) as mock_post:
                await client.distill("content", long_title, "https://x.com", "web_page")

        payload = mock_post.call_args.kwargs["json"]
        assert len(payload["node_name"]) == 80
