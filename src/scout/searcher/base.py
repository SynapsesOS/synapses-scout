"""Search provider protocol."""

from __future__ import annotations

from typing import Protocol

from scout.models import ImageHit, NewsHit, SearchHit


class SearchProvider(Protocol):
    async def search(
        self,
        query: str,
        max_results: int = 5,
        *,
        region: str | None = None,
        timelimit: str | None = None,
        safesearch: str = "moderate",
    ) -> list[SearchHit]: ...

    async def news(
        self,
        query: str,
        max_results: int = 5,
        *,
        region: str | None = None,
        timelimit: str | None = None,
        safesearch: str = "moderate",
    ) -> list[NewsHit]: ...

    async def images(
        self,
        query: str,
        max_results: int = 5,
        *,
        region: str | None = None,
        safesearch: str = "moderate",
        size: str | None = None,
        layout: str | None = None,
    ) -> list[ImageHit]: ...
