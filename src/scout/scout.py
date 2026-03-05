"""Scout — the unified web intelligence interface."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from scout.cache import Cache
from scout.config import ScoutConfig, load_config
from scout.distiller.client import IntelligenceClient
from scout.extractor.web import extract as extract_web
from scout.media.youtube import extract_youtube
from scout.models import (
    ContentType,
    ImageHit,
    NewsHit,
    ScoutFragment,
    ScoutResult,
    SearchHit,
)
from scout.orchestrator import OrchestratedResult, orchestrated_search
from scout.router import classify, ensure_url
from scout.searcher.base import SearchProvider
from scout.searcher.duckduckgo import DuckDuckGoSearcher

log = logging.getLogger(__name__)


def _make_searcher(config: ScoutConfig) -> SearchProvider:
    if config.search_provider == "tavily" and config.tavily_api_key:
        from scout.searcher.tavily import TavilySearcher

        log.info("scout: using Tavily search provider")
        return TavilySearcher(config.tavily_api_key)
    return DuckDuckGoSearcher()


class Scout:
    """Unified web intelligence interface.

    Usage:
        scout = await Scout.create()
        result = await scout.fetch("https://example.com")
        result = await scout.fetch("how does async Python work")
        news = await scout.news("Apple M4 chip release")
        images = await scout.images("neural network architecture diagram")
        print(result.to_markdown())
    """

    def __init__(
        self,
        config: ScoutConfig,
        cache: Cache,
        searcher: SearchProvider,
        intelligence: IntelligenceClient,
    ):
        self.config = config
        self.cache = cache
        self.searcher = searcher
        self.intelligence = intelligence

    @classmethod
    async def create(cls, config: ScoutConfig | None = None) -> Scout:
        config = config or load_config()
        cache = await Cache.open(config.resolved_db_path)
        searcher = _make_searcher(config)
        intelligence = IntelligenceClient(config.intelligence_url, config.intelligence_timeout_ms)
        return cls(config, cache, searcher, intelligence)

    async def fetch(
        self,
        input_str: str,
        *,
        force_refresh: bool = False,
        distill: bool | None = None,
        region: str | None = None,
        timelimit: str | None = None,
        max_results: int = 10,
    ) -> ScoutResult:
        """Main entry point. Accepts a URL or a search query.

        Args:
            input_str: A URL or search query string.
            force_refresh: Bypass cache and re-fetch.
            distill: Override config.distill for this request.
            region: Override search region (e.g., "us-en", "fr-fr").
            timelimit: Time filter — "d" (day), "w" (week), "m" (month), "y" (year).
            max_results: Max results for search queries (default 10).
        """
        content_type = classify(input_str)
        should_distill = distill if distill is not None else self.config.distill

        if content_type == ContentType.SEARCH:
            return await self._handle_search(
                input_str,
                force_refresh,
                should_distill,
                region=region,
                timelimit=timelimit,
                max_results=max_results,
            )

        url = ensure_url(input_str)

        # Check cache. Skip cache hit if distillation is required but cached result
        # has no fragment — distilled and undistilled variants get separate entries.
        if not force_refresh:
            cached = await self.cache.get(url)
            if cached is not None:
                if not should_distill or cached.fragment is not None:
                    return cached

        # Dispatch by type
        if content_type == ContentType.YOUTUBE:
            result = await self._handle_youtube(url, should_distill)
        else:
            result = await self._handle_web(url, should_distill)

        # Cache the result
        ttl = self._ttl_for(content_type)
        await self.cache.put(result, ttl)

        return result

    async def search(
        self,
        query: str,
        max_results: int = 5,
        *,
        region: str | None = None,
        timelimit: str | None = None,
    ) -> list[SearchHit]:
        """Direct search, bypassing routing."""
        return await self.searcher.search(
            query,
            max_results,
            region=region or self.config.search_region,
            timelimit=timelimit,
            safesearch=self.config.search_safesearch,
        )

    async def news(
        self,
        query: str,
        max_results: int = 5,
        *,
        region: str | None = None,
        timelimit: str | None = None,
    ) -> list[NewsHit]:
        """Search news articles."""
        return await self.searcher.news(
            query,
            max_results,
            region=region or self.config.search_region,
            timelimit=timelimit,
            safesearch=self.config.search_safesearch,
        )

    async def images(
        self,
        query: str,
        max_results: int = 5,
        *,
        region: str | None = None,
        size: str | None = None,
        layout: str | None = None,
    ) -> list[ImageHit]:
        """Search images with optional size/layout filters."""
        return await self.searcher.images(
            query,
            max_results,
            region=region or self.config.search_region,
            safesearch=self.config.search_safesearch,
            size=size,
            layout=layout,
        )

    async def deep_search(
        self,
        query: str,
        max_results: int = 10,
        *,
        region: str | None = None,
        timelimit: str | None = None,
        expand: bool | None = None,
    ) -> OrchestratedResult:
        """Orchestrated multi-query search with fan-out, dedup, and ranking.

        Expands the query into multiple angles, searches them in parallel,
        deduplicates by URL, and scores by cross-query frequency + relevance.
        """
        return await orchestrated_search(
            self.searcher,
            query,
            max_results,
            expand=expand if expand is not None else self.config.search_expand,
            region=region or self.config.search_region,
            timelimit=timelimit,
            safesearch=self.config.search_safesearch,
        )

    async def extract(self, url: str, *, force_refresh: bool = False) -> ScoutResult:
        """Direct web extraction with caching."""
        url = ensure_url(url)
        should_distill = self.config.distill

        if not force_refresh:
            cached = await self.cache.get(url)
            if cached is not None:
                if not should_distill or cached.fragment is not None:
                    return cached

        result = await self._handle_web(url, should_distill)
        await self.cache.put(result, self.config.default_ttl_web_hours)
        return result

    async def close(self) -> None:
        await self.intelligence.close()
        await self.cache.close()

    # --- Internal handlers ---

    async def _handle_search(
        self,
        query: str,
        force_refresh: bool,
        should_distill: bool,
        *,
        region: str | None = None,
        timelimit: str | None = None,
        max_results: int = 10,
    ) -> ScoutResult:
        if not force_refresh:
            cached = await self.cache.get_search(query)
            if cached:
                hits = [SearchHit(**h) for h in cached["results"]]
                content_md = self._format_search_hits(query, hits)
                return ScoutResult(
                    url=f"search://{query}",
                    content_type=ContentType.SEARCH,
                    title=f'Search: "{query}"',
                    content_md=content_md,
                    word_count=len(content_md.split()),
                    metadata={
                        "provider": cached["provider"],
                        "hit_count": len(hits),
                        "queries_used": cached.get("queries_used", 1),
                        "total_raw_hits": cached.get("total_raw_hits", len(hits)),
                        "deduplicated": cached.get("deduplicated", 0),
                    },
                    cached=True,
                    fetched_at=datetime.fromisoformat(cached["fetched_at"]),
                )

        # Use orchestrated search for better coverage
        orch = await orchestrated_search(
            self.searcher,
            query,
            max_results=max_results,
            expand=self.config.search_expand,
            region=region or self.config.search_region,
            timelimit=timelimit,
            safesearch=self.config.search_safesearch,
        )
        hits = orch.hits
        content_md = self._format_search_hits(query, hits)

        metadata = {
            "provider": self.config.search_provider,
            "hit_count": len(hits),
            "queries_used": len(orch.expanded_queries),
            "total_raw_hits": orch.total_raw_hits,
            "deduplicated": orch.deduplicated_count,
        }

        # Cache search results (include orchestration metadata for cache reconstruction)
        await self.cache.put_search(
            query,
            self.config.search_provider,
            [h.model_dump() for h in hits],
            self.config.default_ttl_search_hours,
            extra={
                "queries_used": len(orch.expanded_queries),
                "total_raw_hits": orch.total_raw_hits,
                "deduplicated": orch.deduplicated_count,
            },
        )

        result = ScoutResult(
            url=f"search://{query}",
            content_type=ContentType.SEARCH,
            title=f'Search: "{query}"',
            content_md=content_md,
            word_count=len(content_md.split()),
            metadata=metadata,
            fetched_at=datetime.now(timezone.utc),
        )

        if should_distill and hits:
            result.fragment = await self._distill(content_md, result.title, result.url, "search")

        return result

    async def _handle_web(self, url: str, should_distill: bool) -> ScoutResult:
        web = await extract_web(url, self.config)

        result = ScoutResult(
            url=url,
            content_type=ContentType.WEB_PAGE,
            title=web.title,
            content_md=web.content_md,
            word_count=web.word_count,
            source=web.source,
            fetched_at=web.extracted_at,
        )

        if should_distill:
            result.fragment = await self._distill(web.content_md, web.title, url, "web_page")

        return result

    async def _handle_youtube(self, url: str, should_distill: bool) -> ScoutResult:
        try:
            media = await extract_youtube(url)
        except ValueError as e:
            raise ValueError(f"YouTube extraction failed: {e}") from e

        content_parts = []
        if media.description:
            content_parts.append(f"## Description\n\n{media.description}")
        if media.transcript:
            content_parts.append(f"## Transcript\n\n{media.transcript}")
        content_md = "\n\n".join(content_parts) if content_parts else "(no content available)"

        word_count = len(content_md.split())

        metadata = {
            "channel": media.channel,
            "duration_seconds": media.duration_seconds,
            "upload_date": media.upload_date,
            "view_count": media.view_count,
        }
        if media.thumbnail_url:
            metadata["thumbnail_url"] = media.thumbnail_url

        result = ScoutResult(
            url=url,
            content_type=ContentType.YOUTUBE,
            title=media.title,
            content_md=content_md,
            word_count=word_count,
            metadata=metadata,
            fetched_at=media.extracted_at,
        )

        if should_distill:
            distill_content = media.transcript or media.description or media.title
            result.fragment = await self._distill(distill_content, media.title, url, "youtube")

        return result

    async def _distill(
        self, content: str, title: str, url: str, content_type: str
    ) -> ScoutFragment | None:
        try:
            return await self.intelligence.distill(content, title, url, content_type)
        except Exception as e:
            log.debug("distillation skipped: %s", e)
        return None

    def _ttl_for(self, content_type: ContentType) -> int:
        match content_type:
            case ContentType.SEARCH:
                return self.config.default_ttl_search_hours
            case ContentType.YOUTUBE:
                return self.config.default_ttl_media_hours
            case _:
                return self.config.default_ttl_web_hours

    @staticmethod
    def _format_search_hits(query: str, hits: list[SearchHit]) -> str:
        lines = [f"## Search Results for: {query}", ""]
        for i, hit in enumerate(hits, 1):
            lines.append(f"### {i}. [{hit.title}]({hit.url})")
            if hit.snippet:
                lines.append(f"\n{hit.snippet}")
            lines.append("")
        return "\n".join(lines)
