"""Tavily search provider — richer results, requires TAVILY_API_KEY."""

from __future__ import annotations

import asyncio
from functools import partial

from scout.models import SearchHit


class TavilySearcher:
    def __init__(self, api_key: str):
        from tavily import TavilyClient

        self._client = TavilyClient(api_key=api_key)

    async def search(self, query: str, max_results: int = 5) -> list[SearchHit]:
        loop = asyncio.get_running_loop()
        results = await loop.run_in_executor(
            None, partial(self._search_sync, query, max_results)
        )
        return results

    def _search_sync(self, query: str, max_results: int) -> list[SearchHit]:
        response = self._client.search(query=query, max_results=max_results)
        hits: list[SearchHit] = []
        for r in response.get("results", []):
            hits.append(
                SearchHit(
                    title=r.get("title", ""),
                    url=r.get("url", ""),
                    snippet=r.get("content", ""),
                )
            )
        return hits
