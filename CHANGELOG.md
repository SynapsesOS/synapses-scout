# Changelog

All notable changes to synapses-scout are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [0.0.1] — 2026-03-02

### Added
- **Unified `Scout.fetch()` interface**: Auto-detects content type (search query,
  web page, YouTube URL) and returns a `ScoutResult` with `.to_markdown()`.
- **Fast-path web extraction**: httpx + trafilatura for static pages (<1s).
  Automatic fallback to Crawl4AI browser for JS-heavy pages (3-8s).
- **Orchestrated search**: Expands queries into 4 angles, fans out in parallel,
  deduplicates by URL, scores by cross-query frequency + snippet quality + title
  relevance. Returns ranked results.
- **DuckDuckGo search provider**: Full feature set — web, news, images with
  region, time filter, SafeSearch, image size/color/layout support.
- **Tavily search provider**: Optional upgrade path with richer context-enriched
  results. Requires `TAVILY_API_KEY`.
- **YouTube extraction**: yt-dlp metadata + auto-generated transcript extraction.
  No video downloads, no Whisper dependency.
- **Intelligence distillation**: Sends content to synapses-intelligence
  `POST /v1/ingest` for LLM summarization. Fail-silent — works without it.
- **SQLite cache**: TTL-based caching at `~/.synapses/scout.db`.
  Search: 6h, web: 24h, YouTube: 7d. URL normalization strips tracking params.
  Expired entries pruned on startup.
- **HTTP API server**: Starlette on `localhost:11436` with endpoints:
  `/v1/health`, `/v1/fetch`, `/v1/search`, `/v1/deep-search`, `/v1/news`,
  `/v1/images`, `/v1/extract`, `/v1/cache`.
- **CLI**: `scout fetch`, `scout deep-search`, `scout news`, `scout images`,
  `scout serve`, `scout status`.
- **Pydantic models**: `ScoutResult`, `SearchHit`, `NewsHit`, `ImageHit`,
  `WebContent`, `MediaContent`, `ScoutFragment` — all with JSON serialization.
- **Configuration**: `~/.synapses/scout.json` with env overrides. All fields
  have sensible defaults — zero config to get started.
- **55 tests** covering router, cache, models, orchestrator, extractor, and
  Scout integration.
