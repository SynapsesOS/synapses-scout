"""CLI entrypoint for Scout."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="scout", description="Synapses-Scout: Web intelligence layer"
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging")
    sub = parser.add_subparsers(dest="command")

    # serve
    serve_p = sub.add_parser("serve", help="Start the Scout HTTP server")
    serve_p.add_argument("--port", type=int, default=None, help="Port (default: 11436)")
    serve_p.add_argument("--host", default="127.0.0.1", help="Host (default: 127.0.0.1)")

    # fetch
    fetch_p = sub.add_parser("fetch", help="Fetch a URL or search query")
    fetch_p.add_argument("input", help="URL or search query")
    fetch_p.add_argument("--no-cache", action="store_true", help="Bypass cache")
    fetch_p.add_argument("--no-distill", action="store_true", help="Skip distillation")
    fetch_p.add_argument("--region", default=None, help="Search region (e.g., us-en, fr-fr)")
    fetch_p.add_argument("--time", dest="timelimit", default=None, help="Time filter: d/w/m/y")
    fetch_p.add_argument(
        "--json", action="store_true", dest="output_json", help="Output JSON instead of Markdown"
    )

    # deep-search
    ds_p = sub.add_parser("deep-search", help="Orchestrated multi-query search")
    ds_p.add_argument("query", help="Search query")
    ds_p.add_argument("-n", "--max-results", type=int, default=10, help="Max results (default: 10)")
    ds_p.add_argument("--region", default=None, help="Search region")
    ds_p.add_argument("--time", dest="timelimit", default=None, help="Time filter: d/w/m/y")
    ds_p.add_argument("--no-expand", action="store_true", help="Disable query expansion")
    ds_p.add_argument("--json", action="store_true", dest="output_json", help="Output JSON")

    # news
    news_p = sub.add_parser("news", help="Search news articles")
    news_p.add_argument("query", help="News search query")
    news_p.add_argument("-n", "--max-results", type=int, default=5, help="Max results (default: 5)")
    news_p.add_argument("--region", default=None, help="Search region")
    news_p.add_argument("--time", dest="timelimit", default=None, help="Time filter: d/w/m")
    news_p.add_argument("--json", action="store_true", dest="output_json", help="Output JSON")

    # images
    img_p = sub.add_parser("images", help="Search images")
    img_p.add_argument("query", help="Image search query")
    img_p.add_argument("-n", "--max-results", type=int, default=5, help="Max results (default: 5)")
    img_p.add_argument("--region", default=None, help="Search region")
    img_p.add_argument("--size", default=None, help="Size: Small/Medium/Large/Wallpaper")
    img_p.add_argument("--layout", default=None, help="Layout: Square/Tall/Wide")
    img_p.add_argument("--json", action="store_true", dest="output_json", help="Output JSON")

    # status
    sub.add_parser("status", help="Show Scout status and cache stats")

    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, format="%(name)s: %(message)s")
    else:
        logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")

    if args.command == "serve":
        _cmd_serve(args)
    elif args.command == "fetch":
        asyncio.run(_cmd_fetch(args))
    elif args.command == "deep-search":
        asyncio.run(_cmd_deep_search(args))
    elif args.command == "news":
        asyncio.run(_cmd_news(args))
    elif args.command == "images":
        asyncio.run(_cmd_images(args))
    elif args.command == "status":
        asyncio.run(_cmd_status())
    else:
        parser.print_help()
        sys.exit(1)


def _cmd_serve(args: argparse.Namespace) -> None:
    import uvicorn

    from scout.config import load_config
    from scout.server import create_app

    config = load_config()
    port = args.port or config.port

    app = create_app()
    uvicorn.run(app, host=args.host, port=port, log_level="info")


async def _cmd_fetch(args: argparse.Namespace) -> None:
    from scout.scout import Scout

    scout = await Scout.create()
    try:
        result = await scout.fetch(
            args.input,
            force_refresh=args.no_cache,
            distill=not args.no_distill,
            region=args.region,
            timelimit=args.timelimit,
        )

        if args.output_json:
            print(result.model_dump_json(indent=2))
        else:
            print(result.to_markdown())
    finally:
        await scout.close()


async def _cmd_deep_search(args: argparse.Namespace) -> None:
    from scout.scout import Scout

    scout = await Scout.create()
    try:
        orch = await scout.deep_search(
            args.query,
            max_results=args.max_results,
            region=args.region,
            timelimit=args.timelimit,
            expand=not args.no_expand,
        )

        if args.output_json:
            print(
                json.dumps(
                    {
                        "query": orch.original_query,
                        "expanded_queries": orch.expanded_queries,
                        "hits": [h.model_dump() for h in orch.hits],
                        "total_raw_hits": orch.total_raw_hits,
                        "deduplicated": orch.deduplicated_count,
                    },
                    indent=2,
                    default=str,
                )
            )
        else:
            print(f"# Deep Search: {orch.original_query}")
            print(f"Queries: {', '.join(orch.expanded_queries)}")
            print(
                f"Raw hits: {orch.total_raw_hits} | Deduped: {orch.deduplicated_count} | Final: {len(orch.hits)}"
            )
            print()
            for i, hit in enumerate(orch.hits, 1):
                print(f"## {i}. [{hit.title}]({hit.url})")
                if hit.snippet:
                    print(f"   {hit.snippet[:200]}")
                print()
    finally:
        await scout.close()


async def _cmd_news(args: argparse.Namespace) -> None:
    from scout.scout import Scout

    scout = await Scout.create()
    try:
        hits = await scout.news(
            args.query,
            max_results=args.max_results,
            region=args.region,
            timelimit=args.timelimit,
        )

        if args.output_json:
            print(json.dumps([h.model_dump() for h in hits], indent=2, default=str))
        else:
            print(f"# News: {args.query}\n")
            for i, hit in enumerate(hits, 1):
                source = f" ({hit.source})" if hit.source else ""
                date = f" [{hit.date}]" if hit.date else ""
                print(f"## {i}. {hit.title}{source}{date}")
                print(f"   {hit.url}")
                if hit.snippet:
                    print(f"   {hit.snippet[:200]}")
                print()
    finally:
        await scout.close()


async def _cmd_images(args: argparse.Namespace) -> None:
    from scout.scout import Scout

    scout = await Scout.create()
    try:
        hits = await scout.images(
            args.query,
            max_results=args.max_results,
            region=args.region,
            size=args.size,
            layout=args.layout,
        )

        if args.output_json:
            print(json.dumps([h.model_dump() for h in hits], indent=2, default=str))
        else:
            print(f"# Images: {args.query}\n")
            for i, hit in enumerate(hits, 1):
                dims = f" ({hit.width}x{hit.height})" if hit.width else ""
                print(f"## {i}. {hit.title}{dims}")
                print(f"   Image: {hit.image_url}")
                print(f"   Source: {hit.url}")
                print()
    finally:
        await scout.close()


async def _cmd_status() -> None:
    from scout.config import load_config
    from scout.cache import Cache
    from scout.distiller.client import IntelligenceClient

    config = load_config()
    cache = await Cache.open(config.resolved_db_path)
    intelligence = IntelligenceClient(config.intelligence_url, config.intelligence_timeout_ms)

    stats = await cache.stats()
    intel_available = await intelligence.available()

    print("Scout v0.0.1")
    print(f"  Cache DB:       {config.resolved_db_path}")
    print(f"  Cache entries:  {stats['total_entries']}")
    print(f"  Cache by type:  {stats['by_type']}")
    print(f"  Expired:        {stats['expired']}")
    print(
        f"  Intelligence:   {'available' if intel_available else 'unavailable'} ({config.intelligence_url})"
    )
    print(f"  Search:         {config.search_provider}")
    print(f"  Region:         {config.search_region}")
    print(f"  Query expand:   {'enabled' if config.search_expand else 'disabled'}")
    print(f"  Distill:        {'enabled' if config.distill else 'disabled'}")

    await intelligence.close()
    await cache.close()


# Allow `python -m scout`
if __name__ == "__main__":
    main()
