# Changelog

All notable changes to synapses-scout are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [0.0.5] — 2026-03-04

### Fixed

- **Backward-compat `distilled`/`distilled_content` fields removed from `/v1/fetch` response**: Older clients and the E2E test plan check for `distilled: bool` and `distilled_content: str` at the top level. These were removed when `fragment` object was introduced. Re-added as backward-compatible fields alongside `fragment`: `distilled` is `true` when `fragment` is not null; `distilled_content` is `fragment.summary` when present. (`src/scout/server.py`)

---

## [0.0.4] — 2026-03-03

### Fixed

- **BUG-SC02: Cache+distill race**: Once a URL was cached without distillation, subsequent `distill:true` requests returned the undistilled cached result because the cache lookup happened before the distill flag was checked. Fixed: `Scout.fetch()` now checks the `distill` flag before cache lookup — if distillation is requested but the cached entry has no `fragment`, the cache is bypassed.

- **BUG-SC03: `/v1/search` and `/v1/deep-search` not caching results**: Search results were never persisted to `scout.db` despite `default_ttl_search_hours` being configured. Both endpoints now check the cache on read (early return on cache hit) and write results to cache after a successful search.

- **Intelligence client default timeout**: Increased `intelligence_timeout_ms` default from 10s to 60s. On CPU-only machines, `/v1/ingest` takes 15-20s, so the 10s default caused every distillation call to fail silently.

---

## [0.0.3] — 2026-03-03

### Fixed

- **Distillation always failing on CPU-only machines**: `IntelligenceClient` used a 5-second connect timeout for all calls. On CPU-only machines, Ollama inference takes 15-20s, so every distillation call timed out. Increased default timeout to 60s; configurable via `intelligence_timeout_ms` in `~/.synapses/scout.json`.

- **Prune step blocks distillation on timeout**: The prune step (`/v1/prune`) was not fail-silent — if it timed out, the distillation pipeline halted entirely. Now, if prune times out or fails, the raw content is passed directly to `/v1/ingest` (already the correct behavior, now consistently applied).

---

## [0.0.2] — 2026-03-03

### Fixed

- **Tavily provider properly wired**: `_make_searcher()` now actually instantiates
  `TavilySearcher` when `search_provider = "tavily"` and the API key is present.
  Previously, the Tavily code path was dead (`pass`) and DuckDuckGo was always used.

- **YouTube transcript extraction**: yt-dlp populates `data` only when writing to
  disk. With `download=False`, the `data` field is always `None`. Scout now fetches
  subtitle URLs directly via `urllib.request`, fixing transcript extraction for all
  YouTube videos with auto-generated captions.

- **VTT deduplication**: The VTT cleaner used a global `seen` set, which dropped
  legitimately repeated phrases (e.g., "Thank you" appearing at two different
  timestamps). Changed to previous-line comparison — only adjacent duplicates are
  removed, matching the YouTube subtitle overlap pattern.

- **Distillation content size**: Increased from 500 → 3000 chars. At 500 chars,
  the LLM barely had enough context to produce a meaningful summary.

- **Distillation node types**: Corrected to human-readable strings matching
  intelligence's expectations: `"web article"`, `"youtube video"`,
  `"search result set"` (was `"web_content"`, `"youtube_transcript"`, etc.).

- **`extract()` now caches results**: Direct URL extraction via `Scout.extract()`
  previously bypassed the SQLite cache entirely. It now reads/writes cache with
  TTL, and accepts a `force_refresh` parameter.

- **Intelligence availability TTL cache**: The `IntelligenceClient` now caches the
  availability check result for 30 seconds (`time.monotonic()`). Previously, every
  `distill()` call made a GET `/v1/health` immediately before the POST `/v1/ingest`,
  causing N+1 HTTP requests. On ingest failure, the cache is invalidated so the
  next call re-checks.

- **`max_results` parameter in `fetch()`**: `Scout.fetch()` and the `POST /v1/fetch`
  endpoint now accept `max_results` (default: 10), threaded through to
  `_handle_search()`.

- **Server error handling**: All HTTP endpoints now wrap handler logic in
  `try/except` and return `{"error": "..."}` JSON with appropriate HTTP status
  codes instead of 500 stack traces. JSON body parse errors return 400.

- **Singleton race condition**: Two concurrent coroutines could both observe
  `_scout is None` and call `Scout.create()` simultaneously. Fixed with
  `asyncio.Lock()` + double-checked locking in `_get_scout()`.

- **`per_query_max` multiplier**: Orchestrator now uses `max(max_results * 2, 10)`
  per-query fetch budget (was `max(max_results, 5)`), giving the deduplicator more
  raw material and improving final result quality for small `max_results` values.

- **`load_config()` accepts optional path**: `load_config(config_path=None)` now
  accepts an explicit path parameter, making it easily testable without environment
  variable manipulation.

### Added

- **61 new tests** (116 total, up from 55):
  - `test_distiller.py` — 14 tests covering availability TTL caching, distillation
    content truncation, node type mapping, and error recovery.
  - `test_server.py` — 25 tests covering all HTTP endpoints, error responses,
    JSON body validation, and singleton initialization.
  - `test_youtube.py` — 15 tests covering VTT cleaning (timestamps, HTML tags,
    deduplication, cue indices) and transcript extraction fallback chain.
  - `test_config.py` — 12 tests covering defaults, JSON file loading, partial
    file merging, and environment variable overrides.

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
