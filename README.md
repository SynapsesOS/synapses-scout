# Synapses-Scout

**The Sensory Cortex of Synapses-OS.** A web intelligence acquisition layer that gives AI coding agents the ability to think from the internet.

Instead of hallucinating answers about the outside world, an agent asks Scout — and gets structured, cached, LLM-distilled Markdown back in under a second.

```
Agent → "What are the latest Python 3.13 features?"
Scout → Orchestrated multi-query search (4 angles, parallel fan-out)
      → Deduplicated, relevance-scored results
      → Fast-path extraction (httpx + trafilatura, <1s)
      → Optional LLM distillation via synapses-intelligence
      → Cached in SQLite with TTL
```

The agent gets clean context. Not raw HTML.

---

## Features

- **Unified `Scout.fetch()`** — One interface for search queries, web pages, and YouTube. Auto-detects content type.
- **Fast-Path Extraction** — httpx + trafilatura for ~80% of pages (<1s). Crawl4AI browser fallback for JS-heavy SPAs (3-8s). Transparent to the caller.
- **Orchestrated Search** — Expands queries into multiple angles, fans out in parallel, deduplicates by URL, scores by cross-query frequency + relevance.
- **News & Image Search** — Full DuckDuckGo feature set: regions, time filters, SafeSearch, image size/color/layout.
- **YouTube Intelligence** — yt-dlp metadata + auto-generated transcript extraction. No downloads, no Whisper needed.
- **Intelligence Distillation** — 2-step pipeline: `POST /v1/prune` (0.8B strips boilerplate) → `POST /v1/ingest` (4B summarizes clean content). Fail-silent: works without intelligence.
- **SQLite Cache** — TTL-based caching (search: 6h, web: 24h, YouTube: 7d). URL normalization strips tracking params.
- **HTTP API** — REST server on `localhost:11436`. Same pattern as the intelligence sidecar.
- **Local-First** — Everything runs on your machine. No cloud APIs required for core features.

---

## Quick Start

```bash
# Clone
git clone https://github.com/SynapsesOS/synapses-scout.git
cd synapses-scout

# Install
python3 -m venv .venv && source .venv/bin/activate
pip install -e .

# Use
scout fetch "python async patterns"                          # search
scout fetch "https://docs.python.org/3/library/asyncio.html" # extract web page
scout fetch "https://youtube.com/watch?v=..."                # YouTube transcript
scout deep-search "rust vs go performance 2026"              # orchestrated multi-query
scout news "Apple M4 chip" --time d                          # today's news
scout images "neural network architecture" --size Large      # image search
```

---

## Architecture

```
Agent (Claude Code / Cursor)
    │
    ▼
Synapses (MCP Server :8766)
    │                    │
    ▼                    ▼
Intelligence (:11435)    Scout (:11436)
    │                        │
    ▼                        ├─→ DuckDuckGo (search, news, images)
  Ollama (:11434)            ├─→ httpx + trafilatura (fast extraction)
                             ├─→ Crawl4AI (JS-heavy fallback)
                             └─→ yt-dlp (YouTube)
                                     │
                                     ▼
                             Intelligence (:11435) for distillation
```

Scout uses a **2-step distillation pipeline** with intelligence:
1. `POST /v1/prune` (0.8B Reflex) — strips navigation, ads, footers from raw web content → ~1200 chars clean signal
2. `POST /v1/ingest` (4B Specialist) — summarizes the clean technical content → prose briefing

Both steps are fail-silent. No duplicate Ollama setup — scout reuses the brain sidecar.

---

## HTTP API

Start the server:

```bash
scout serve                    # default: localhost:11436
scout serve --port 8080        # custom port
```

### Endpoints

| Method | Path | Description |
|---|---|---|
| `GET` | `/v1/health` | Status, intelligence availability, cache stats |
| `POST` | `/v1/fetch` | Unified fetch: `{"input": "url or query", "max_results": 10, "force_refresh": false}` |
| `POST` | `/v1/search` | Web search: `{"query": "...", "max_results": 5}` |
| `POST` | `/v1/deep-search` | Orchestrated multi-query: `{"query": "...", "max_results": 10}` |
| `POST` | `/v1/news` | News search: `{"query": "...", "timelimit": "d"}` |
| `POST` | `/v1/images` | Image search: `{"query": "...", "size": "Large"}` |
| `POST` | `/v1/extract` | Direct URL extraction: `{"url": "...", "force_refresh": false}` |
| `GET/DELETE` | `/v1/cache` | Cache stats / prune |

All endpoints accept optional `region` (e.g., `"us-en"`, `"fr-fr"`) and `timelimit` (`"d"`, `"w"`, `"m"`, `"y"`) parameters.

---

## CLI Reference

```
scout fetch <url_or_query>     Fetch a URL or search query
    --no-cache                 Bypass cache
    --no-distill               Skip intelligence distillation
    --region <code>            Search region (us-en, fr-fr, de-de, ...)
    --time <d|w|m|y>           Time filter
    --json                     Output JSON instead of Markdown

scout deep-search <query>      Orchestrated multi-query search
    -n, --max-results <N>      Max results (default: 10)
    --no-expand                Disable query expansion
    --region / --time / --json Same as fetch

scout news <query>             Search news articles
scout images <query>           Search images
    --size <Small|Medium|Large|Wallpaper>
    --layout <Square|Tall|Wide>

scout serve                    Start HTTP server
    --port <N>                 Port (default: 11436)

scout status                   Show cache stats and intelligence availability
```

---

## Configuration

Config file: `~/.synapses/scout.json` (optional — all fields have defaults)

```json
{
    "port": 11436,
    "db_path": "~/.synapses/scout.db",
    "intelligence_url": "http://localhost:11435",
    "intelligence_timeout_ms": 5000,
    "search_provider": "duckduckgo",
    "tavily_api_key": null,
    "distill": true,
    "max_content_chars": 50000,
    "default_ttl_search_hours": 6,
    "default_ttl_web_hours": 24,
    "default_ttl_media_hours": 168,
    "search_region": "wt-wt",
    "search_safesearch": "moderate",
    "search_expand": true
}
```

Environment variable overrides: `SCOUT_CONFIG`, `SCOUT_PORT`, `SCOUT_INTELLIGENCE_URL`, `TAVILY_API_KEY`.

### Using Tavily

Tavily provides richer, context-enriched search results compared to DuckDuckGo. To enable it:

**Option 1 — environment variable (recommended):**
```bash
export TAVILY_API_KEY="tvly-your-key-here"
```

**Option 2 — config file:**
```json
{
    "search_provider": "tavily",
    "tavily_api_key": "tvly-your-key-here"
}
```

Get a free API key at [tavily.com](https://tavily.com). Without a key, Scout falls back to DuckDuckGo automatically.

---

## Caching Strategy

| Content Type | Default TTL | Cache Key |
|---|---|---|
| Search results | 6 hours | `sha256(normalized_query)` |
| Web pages | 24 hours | `sha256(normalized_url)` |
| YouTube | 7 days | `sha256(normalized_url)` |

URL normalization: lowercase host, strip trailing slash, remove tracking params (`utm_*`, `fbclid`, `gclid`), sort query params.

Cache lives at `~/.synapses/scout.db` (SQLite). Expired entries pruned on startup.

---

## Integration with Synapses-OS

Scout integrates with [synapses-intelligence](https://github.com/SynapsesOS/synapses-intelligence) for LLM distillation. No changes needed to intelligence — Scout maps web content to its existing `IngestRequest` format:

```
POST http://localhost:11435/v1/ingest
{
    "node_id": "scout:web_page:a1b2c3d4e5f6",
    "node_name": "Article Title",
    "node_type": "web article",
    "package": "example.com",
    "code": "first 3000 chars of content..."
}
```

Node types mapped per content:

| Scout content type | `node_type` sent to intelligence |
|---|---|
| Web page | `"web article"` |
| YouTube video | `"youtube video"` |
| Search results | `"search result set"` |

If intelligence is unavailable, Scout skips distillation and returns raw content. Fail-silent — same contract as the rest of the ecosystem.

---

## Development

```bash
# Setup
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Test (116 tests)
make test

# Lint
make lint

# Format
make format
```

---

## License

MIT — see [LICENSE](LICENSE).
