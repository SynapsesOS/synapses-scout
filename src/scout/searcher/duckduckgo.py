"""DuckDuckGo search provider — full feature set, no API key required.

Exposes: text search, news, images with region/time/safesearch filters.
"""

from __future__ import annotations

import asyncio
from functools import partial

from duckduckgo_search import DDGS

from scout.models import ImageHit, NewsHit, SearchHit


class DuckDuckGoSearcher:
    """Full-featured DuckDuckGo searcher with region, time, and content type support."""

    def __init__(self, proxy: str | None = None, timeout: int = 10):
        self._proxy = proxy
        self._timeout = timeout

    def _make_client(self) -> DDGS:
        return DDGS(proxy=self._proxy, timeout=self._timeout)

    async def search(
        self,
        query: str,
        max_results: int = 5,
        *,
        region: str = "wt-wt",
        timelimit: str | None = None,
        safesearch: str = "moderate",
    ) -> list[SearchHit]:
        """Web search with region and time filtering.

        Args:
            region: DDG region code (e.g., "us-en", "fr-fr", "de-de", "wt-wt" for global).
            timelimit: "d" (day), "w" (week), "m" (month), "y" (year), or None.
            safesearch: "on", "moderate", or "off".
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            partial(
                self._text_sync,
                query,
                max_results,
                region=region,
                timelimit=timelimit,
                safesearch=safesearch,
            ),
        )

    async def news(
        self,
        query: str,
        max_results: int = 5,
        *,
        region: str = "wt-wt",
        timelimit: str | None = None,
        safesearch: str = "moderate",
    ) -> list[NewsHit]:
        """News search — returns recent articles from news sources.

        Args:
            timelimit: "d" (day), "w" (week), "m" (month), or None.
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            partial(
                self._news_sync,
                query,
                max_results,
                region=region,
                timelimit=timelimit,
                safesearch=safesearch,
            ),
        )

    async def images(
        self,
        query: str,
        max_results: int = 5,
        *,
        region: str = "wt-wt",
        timelimit: str | None = None,
        safesearch: str = "moderate",
        size: str | None = None,
        color: str | None = None,
        type_image: str | None = None,
        layout: str | None = None,
    ) -> list[ImageHit]:
        """Image search with size, color, type, and layout filters.

        Args:
            size: "Small", "Medium", "Large", "Wallpaper", or None.
            color: "color", "Monochrome", "Red", "Orange", "Yellow", "Green",
                   "Blue", "Purple", "Pink", "Brown", "Black", "Gray",
                   "Teal", "White", or None.
            type_image: "photo", "clipart", "gif", "transparent", "line", or None.
            layout: "Square", "Tall", "Wide", or None.
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            partial(
                self._images_sync,
                query,
                max_results,
                region=region,
                timelimit=timelimit,
                safesearch=safesearch,
                size=size,
                color=color,
                type_image=type_image,
                layout=layout,
            ),
        )

    # --- Sync implementations (run in thread pool) ---

    def _text_sync(
        self,
        query: str,
        max_results: int,
        *,
        region: str,
        timelimit: str | None,
        safesearch: str,
    ) -> list[SearchHit]:
        hits: list[SearchHit] = []
        with self._make_client() as ddgs:
            for r in ddgs.text(
                query,
                max_results=max_results,
                region=region,
                timelimit=timelimit,
                safesearch=safesearch,
            ):
                hits.append(
                    SearchHit(
                        title=r.get("title", ""),
                        url=r.get("href", ""),
                        snippet=r.get("body", ""),
                    )
                )
        return hits

    def _news_sync(
        self,
        query: str,
        max_results: int,
        *,
        region: str,
        timelimit: str | None,
        safesearch: str,
    ) -> list[NewsHit]:
        hits: list[NewsHit] = []
        with self._make_client() as ddgs:
            for r in ddgs.news(
                query,
                max_results=max_results,
                region=region,
                timelimit=timelimit,
                safesearch=safesearch,
            ):
                hits.append(
                    NewsHit(
                        title=r.get("title", ""),
                        url=r.get("url", ""),
                        snippet=r.get("body", ""),
                        source=r.get("source", ""),
                        date=r.get("date", ""),
                    )
                )
        return hits

    def _images_sync(
        self,
        query: str,
        max_results: int,
        *,
        region: str,
        timelimit: str | None,
        safesearch: str,
        size: str | None,
        color: str | None,
        type_image: str | None,
        layout: str | None,
    ) -> list[ImageHit]:
        hits: list[ImageHit] = []
        with self._make_client() as ddgs:
            for r in ddgs.images(
                query,
                max_results=max_results,
                region=region,
                timelimit=timelimit,
                safesearch=safesearch,
                size=size,
                color=color,
                type_image=type_image,
                layout=layout,
            ):
                hits.append(
                    ImageHit(
                        title=r.get("title", ""),
                        url=r.get("url", ""),
                        image_url=r.get("image", ""),
                        thumbnail_url=r.get("thumbnail", ""),
                        width=r.get("width", 0) or 0,
                        height=r.get("height", 0) or 0,
                        source=r.get("source", ""),
                    )
                )
        return hits
