"""Search provider protocol."""

from __future__ import annotations

from typing import Protocol

from scout.models import SearchHit


class SearchProvider(Protocol):
    async def search(self, query: str, max_results: int = 5) -> list[SearchHit]: ...
