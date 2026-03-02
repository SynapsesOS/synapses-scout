"""HTTP client for synapses-intelligence — distills web content into summaries."""

from __future__ import annotations

import hashlib
import logging
from urllib.parse import urlparse

import httpx

from scout.models import ScoutFragment

log = logging.getLogger(__name__)


class IntelligenceClient:
    """Fail-silent HTTP client to synapses-intelligence at localhost:11435."""

    def __init__(self, base_url: str, timeout_ms: int = 5000):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout_ms / 1000
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout)

    async def available(self) -> bool:
        try:
            resp = await self._client.get("/v1/health")
            if resp.status_code == 200:
                data = resp.json()
                return data.get("available", False)
        except Exception:
            pass
        return False

    async def distill(
        self, content: str, title: str, source_url: str, content_type: str
    ) -> ScoutFragment | None:
        """Send content to intelligence for summarization via /v1/ingest.

        Maps web content to intelligence's IngestRequest format:
          node_id:   "scout:<type>:<sha256(url)[:12]>"
          node_name: page title (truncated to 80 chars)
          node_type: "web_content" | "youtube_transcript" | "search_result"
          package:   domain name
          code:      first 500 chars of content
        """
        url_hash = hashlib.sha256(source_url.encode()).hexdigest()[:12]
        domain = urlparse(source_url).hostname or "unknown"

        node_type_map = {
            "web_page": "web_content",
            "youtube": "youtube_transcript",
            "search": "search_result",
        }

        payload = {
            "node_id": f"scout:{content_type}:{url_hash}",
            "node_name": title[:80] if title else source_url[:80],
            "node_type": node_type_map.get(content_type, "web_content"),
            "package": domain,
            "code": content[:500],
        }

        try:
            resp = await self._client.post("/v1/ingest", json=payload)
            if resp.status_code == 200:
                data = resp.json()
                return ScoutFragment(
                    summary=data.get("summary", ""),
                    tags=data.get("tags", []),
                    distilled_by=f"intelligence@{self.base_url}",
                )
        except Exception as e:
            log.debug("intelligence distill failed: %s", e)

        return None

    async def close(self) -> None:
        await self._client.aclose()
