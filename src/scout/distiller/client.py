"""HTTP client for synapses-intelligence — distills web content into summaries."""

from __future__ import annotations

import hashlib
import logging
import time
from urllib.parse import urlparse

import httpx

from scout.models import ScoutFragment

log = logging.getLogger(__name__)

# How many characters of content to send for distillation.
# Intelligence's /v1/ingest was designed for code snippets (500 chars), but
# web content needs more signal. We send up to 3000 chars — enough for a full
# article lede + a few paragraphs — while staying well within LLM prompt limits.
_DISTILL_MAX_CHARS = 3_000

# Node types that make sense to intelligence's LLM prompt construction.
# Intelligence uses node_type in the prompt: "Summarize this <node_type>: <name>".
# We use descriptive strings that produce readable prompts, since intelligence
# does not validate this field against a fixed enum.
_NODE_TYPE_MAP = {
    "web_page": "web article",
    "youtube": "youtube video",
    "search": "search result set",
}

# How long to cache the availability check result (seconds).
# Avoids a /v1/health round-trip before every single distillation call.
_AVAILABILITY_TTL = 30.0


class IntelligenceClient:
    """Fail-silent HTTP client to synapses-intelligence at localhost:11435."""

    def __init__(self, base_url: str, timeout_ms: int = 5000):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout_ms / 1000
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout)
        # Cached availability state — refreshed at most once per _AVAILABILITY_TTL seconds.
        self._available: bool | None = None
        self._available_checked_at: float = 0.0

    async def available(self) -> bool:
        """Return whether intelligence + Ollama are reachable. Result is cached for 30s."""
        now = time.monotonic()
        if self._available is not None and (now - self._available_checked_at) < _AVAILABILITY_TTL:
            return self._available

        try:
            resp = await self._client.get("/v1/health")
            if resp.status_code == 200:
                data = resp.json()
                self._available = bool(data.get("available", False))
            else:
                self._available = False
        except Exception:
            self._available = False

        self._available_checked_at = now
        return self._available

    async def distill(
        self, content: str, title: str, source_url: str, content_type: str
    ) -> ScoutFragment | None:
        """Send content to intelligence for summarization via /v1/ingest.

        Checks availability (cached) before attempting the call. Returns None
        if intelligence is unavailable or the call fails (fail-silent).

        Maps web content to intelligence's IngestRequest format:
          node_id:   "scout:<type>:<sha256(url)[:12]>"
          node_name: page title (truncated to 80 chars)
          node_type: descriptive label used in the LLM prompt
          package:   domain name
          code:      first 3000 chars of content (meaningful signal for summarization)
        """
        if not await self.available():
            return None

        url_hash = hashlib.sha256(source_url.encode()).hexdigest()[:12]
        domain = urlparse(source_url).hostname or "unknown"
        node_type = _NODE_TYPE_MAP.get(content_type, "web article")

        payload = {
            "node_id": f"scout:{content_type}:{url_hash}",
            "node_name": title[:80] if title else source_url[:80],
            "node_type": node_type,
            "package": domain,
            "code": content[:_DISTILL_MAX_CHARS],
        }

        try:
            resp = await self._client.post("/v1/ingest", json=payload)
            if resp.status_code == 200:
                data = resp.json()
                # Mark intelligence as confirmed-available after a successful call.
                self._available = True
                self._available_checked_at = time.monotonic()
                return ScoutFragment(
                    summary=data.get("summary", ""),
                    tags=data.get("tags", []),
                    distilled_by=f"intelligence@{self.base_url}",
                )
        except Exception as e:
            log.debug("intelligence distill failed: %s", e)
            # Invalidate cached availability so the next call re-checks.
            self._available = None

        return None

    async def close(self) -> None:
        await self._client.aclose()
