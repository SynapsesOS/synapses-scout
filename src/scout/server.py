"""HTTP API server for Scout — Starlette on localhost:11436."""

from __future__ import annotations

import asyncio
import json
import logging

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from scout.scout import Scout

log = logging.getLogger(__name__)

_scout: Scout | None = None
_scout_lock = asyncio.Lock()


async def _get_scout() -> Scout:
    """Return the shared Scout instance, creating it exactly once."""
    global _scout
    if _scout is not None:
        return _scout
    async with _scout_lock:
        if _scout is None:  # double-check after acquiring lock
            _scout = await Scout.create()
    return _scout


def _err(msg: str, status: int = 500) -> JSONResponse:
    return JSONResponse({"error": msg}, status_code=status)


async def health(request: Request) -> JSONResponse:
    try:
        scout = await _get_scout()
        intel_available = await scout.intelligence.available()
        cache_stats = await scout.cache.stats()
        return JSONResponse({
            "status": "ok",
            "version": "0.0.1",
            "intelligence_available": intel_available,
            "cache": cache_stats,
        })
    except Exception as e:
        log.exception("health check error")
        return _err(str(e))


async def fetch(request: Request) -> JSONResponse:
    try:
        body = await request.json()
    except Exception:
        return _err("invalid JSON body", 400)

    input_str = body.get("input", "")
    if not input_str:
        return _err("input is required", 400)

    try:
        scout = await _get_scout()
        result = await scout.fetch(
            input_str,
            force_refresh=body.get("force_refresh", False),
            distill=body.get("distill", None),
            region=body.get("region"),
            timelimit=body.get("timelimit"),
            max_results=int(body.get("max_results", 10)),
        )
        return JSONResponse(json.loads(result.model_dump_json()))
    except Exception as e:
        log.exception("fetch error for input=%r", input_str)
        return _err(str(e))


async def search(request: Request) -> JSONResponse:
    try:
        body = await request.json()
    except Exception:
        return _err("invalid JSON body", 400)

    query = body.get("query", "")
    if not query:
        return _err("query is required", 400)

    try:
        scout = await _get_scout()
        hits = await scout.search(
            query,
            max_results=body.get("max_results", 5),
            region=body.get("region"),
            timelimit=body.get("timelimit"),
        )
        return JSONResponse({
            "query": query,
            "hits": [json.loads(h.model_dump_json()) for h in hits],
            "count": len(hits),
        })
    except Exception as e:
        log.exception("search error for query=%r", query)
        return _err(str(e))


async def deep_search(request: Request) -> JSONResponse:
    """Orchestrated multi-query search with fan-out and deduplication."""
    try:
        body = await request.json()
    except Exception:
        return _err("invalid JSON body", 400)

    query = body.get("query", "")
    if not query:
        return _err("query is required", 400)

    try:
        scout = await _get_scout()
        orch = await scout.deep_search(
            query,
            max_results=body.get("max_results", 10),
            region=body.get("region"),
            timelimit=body.get("timelimit"),
            expand=body.get("expand"),
        )
        return JSONResponse({
            "query": orch.original_query,
            "expanded_queries": orch.expanded_queries,
            "hits": [json.loads(h.model_dump_json()) for h in orch.hits],
            "count": len(orch.hits),
            "total_raw_hits": orch.total_raw_hits,
            "deduplicated": orch.deduplicated_count,
        })
    except Exception as e:
        log.exception("deep_search error for query=%r", query)
        return _err(str(e))


async def news(request: Request) -> JSONResponse:
    """Search news articles."""
    try:
        body = await request.json()
    except Exception:
        return _err("invalid JSON body", 400)

    query = body.get("query", "")
    if not query:
        return _err("query is required", 400)

    try:
        scout = await _get_scout()
        hits = await scout.news(
            query,
            max_results=body.get("max_results", 5),
            region=body.get("region"),
            timelimit=body.get("timelimit"),
        )
        return JSONResponse({
            "query": query,
            "hits": [json.loads(h.model_dump_json()) for h in hits],
            "count": len(hits),
        })
    except Exception as e:
        log.exception("news error for query=%r", query)
        return _err(str(e))


async def images_search(request: Request) -> JSONResponse:
    """Search images."""
    try:
        body = await request.json()
    except Exception:
        return _err("invalid JSON body", 400)

    query = body.get("query", "")
    if not query:
        return _err("query is required", 400)

    try:
        scout = await _get_scout()
        hits = await scout.images(
            query,
            max_results=body.get("max_results", 5),
            region=body.get("region"),
            size=body.get("size"),
            layout=body.get("layout"),
        )
        return JSONResponse({
            "query": query,
            "hits": [json.loads(h.model_dump_json()) for h in hits],
            "count": len(hits),
        })
    except Exception as e:
        log.exception("images error for query=%r", query)
        return _err(str(e))


async def extract(request: Request) -> JSONResponse:
    try:
        body = await request.json()
    except Exception:
        return _err("invalid JSON body", 400)

    url = body.get("url", "")
    if not url:
        return _err("url is required", 400)

    try:
        scout = await _get_scout()
        result = await scout.extract(url, force_refresh=body.get("force_refresh", False))
        return JSONResponse(json.loads(result.model_dump_json()))
    except Exception as e:
        log.exception("extract error for url=%r", url)
        return _err(str(e))


async def cache_manage(request: Request) -> JSONResponse:
    try:
        scout = await _get_scout()
        if request.method == "DELETE":
            try:
                body = await request.json()
                url = body.get("url")
            except Exception:
                url = None

            if url:
                removed = await scout.cache.invalidate(url)
                return JSONResponse({"invalidated": removed, "url": url})
            else:
                pruned = await scout.cache.prune()
                return JSONResponse({"pruned": pruned})

        stats = await scout.cache.stats()
        return JSONResponse(stats)
    except Exception as e:
        log.exception("cache error")
        return _err(str(e))


async def on_startup() -> None:
    log.info("scout: initializing...")
    await _get_scout()
    log.info("scout: ready")


async def on_shutdown() -> None:
    if _scout:
        await _scout.close()


def create_app() -> Starlette:
    return Starlette(
        routes=[
            Route("/v1/health", health, methods=["GET"]),
            Route("/v1/fetch", fetch, methods=["POST"]),
            Route("/v1/search", search, methods=["POST"]),
            Route("/v1/deep-search", deep_search, methods=["POST"]),
            Route("/v1/news", news, methods=["POST"]),
            Route("/v1/images", images_search, methods=["POST"]),
            Route("/v1/extract", extract, methods=["POST"]),
            Route("/v1/cache", cache_manage, methods=["GET", "DELETE"]),
        ],
        on_startup=[on_startup],
        on_shutdown=[on_shutdown],
    )
