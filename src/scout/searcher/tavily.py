"""Tavily search provider — richer results, requires TAVILY_API_KEY.

Tavily only supports web search. news() and images() return empty lists;
configure a region/timelimit via the standard DDG fallback path if needed.
"""

from __future__ import annotations

import asyncio
import logging
from functools import partial

from scout.models import ImageHit, NewsHit, SearchHit

log = logging.getLogger(__name__)


class TavilySearcher:
    def __init__(self, api_key: str):
        from tavily import TavilyClient

        self._client = TavilyClient(api_key=api_key)

    async def search(
        self,
        query: str,
        max_results: int = 5,
        *,
        region: str | None = None,
        timelimit: str | None = None,
        safesearch: str = "moderate",
    ) -> list[SearchHit]:
        # Tavily ignores region/timelimit/safesearch — those are DDG-specific params.
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, partial(self._search_sync, query, max_results)
        )

    def _search_sync(self, query: str, max_results: int) -> list[SearchHit]:
        try:
            response = self._client.search(query=query, max_results=max_results)
        except Exception as e:
            log.warning("Tavily search failed: %s", e)
            return []
        return [
            SearchHit(
                title=r.get("title", ""),
                url=r.get("url", ""),
                snippet=r.get("content", ""),
            )
            for r in response.get("results", [])
        ]

    async def news(
        self,
        query: str,
        max_results: int = 5,
        *,
        region: str | None = None,
        timelimit: str | None = None,
        safesearch: str = "moderate",
    ) -> list[NewsHit]:
        # Tavily does not have a dedicated news endpoint.
        return []

    async def images(
        self,
        query: str,
        max_results: int = 5,
        *,
        region: str | None = None,
        safesearch: str = "moderate",
        size: str | None = None,
        layout: str | None = None,
    ) -> list[ImageHit]:
        # Tavily does not support image search.
        return []
