# synapses-scout improvement log

## v0.0.3 — Scout Prune Pipeline (2026-03-03)

### Changes

#### P7 — /v1/prune Preprocessing Pipeline
`src/scout/distiller/client.py`:
- Added `prune(content: str) -> str` method — calls `/v1/prune` on intelligence
- Updated `distill()` to run a 2-step pipeline:
  1. `POST /v1/prune` (0.8B Reflex): strip navigation, ads, footers → ~1200 chars clean signal
  2. `POST /v1/ingest` (4B Specialist): summarize the pruned technical content
- Prune step is fail-silent: falls back to original content if intelligence unavailable

**Effect:** Scout raw web content (3000 chars) → pruned clean signal (~1200 chars) →
the 4B distillation model sees only valuable technical paragraphs → better quality
summaries + faster inference (less input tokens).

---

## v0.0.2 — E2E Test Run (2026-03-03)

---

### CRITICAL BUGS

#### BUG-SC01 — IntelligenceClient timeout too short — distillation silently fails
**Severity:** Critical
**Root cause:** `src/scout/distiller/client.py` line 40:
```python
def __init__(self, base_url: str, timeout_ms: int = 5000):
    self.timeout = timeout_ms / 1000  # = 5 seconds
```
The `httpx.AsyncClient` timeout is 5s by default, or whatever
`config.intelligence_timeout_ms` is set to (default in `scout.json.example`:
`5000ms`). But `/v1/ingest` on intelligence takes **16+ seconds** on CPU with
the 1.5b model.
**Effect:** Every distillation call times out silently. `fragment: null` in ALL
fetch responses. The feature appears broken even when intelligence is running.
**Evidence:** Fixed by setting `intelligence_timeout_ms: 60000` in scout.json
→ distillation works.
**Fix:**
  1. Increase default in `scout.json.example` to `30000` (minimum viable for 1.5b).
  2. Document the dependency: "intelligence_timeout_ms must exceed the LLM
     inference time on your hardware (~16s for 1.5b CPU, ~3s for 7b GPU)".
  3. Add a health check that warns if intelligence takes >timeout_ms to respond
     to `/v1/ingest` with a minimal payload.

#### BUG-SC02 — Cache+distill race: cached (undistilled) results block subsequent distill requests
**Severity:** High
**Root cause:** In `src/scout/scout.py` `fetch()` method (line 106-109):
```python
if not force_refresh:
    cached = await self.cache.get(url)
    if cached is not None:
        return cached   # ← returned before distill check
```
If a URL was first fetched with `distill=False`, the result is cached without a
fragment. A subsequent request with `distill=True` hits the cache and returns
the undistilled result. The caller must use `force_refresh=True` to get a
distilled result — but this is not documented and counter-intuitive.
**Fix:** Check if `should_distill=True` and `cached.fragment is None`, and if
so, fall through to fetch+distill rather than returning the cached (undistilled)
result. Or: use separate cache keys for distilled vs undistilled results.

#### BUG-SC03 — Search results not cached despite `default_ttl_search_hours: 6` in config
**Severity:** Medium
**Observed:** `GET /v1/cache` shows `search: 0` entries after multiple searches.
`by_type: {web_page: 1, search: 0}` — only web page fetches are being cached.
**Root cause:** The `_handle_search` path in `scout.py` likely doesn't call
`cache.put()` for search results, only for individual page fetches.
**Fix:** Add `await self.cache.put(result, ttl)` in `_handle_search` with TTL
from `config.default_ttl_search_hours`. The same DuckDuckGo query repeated
within 6 hours should return immediately from SQLite.

---

### QUALITY ISSUES

#### QA-SC01 — Search snippets have missing spaces from HTML stripping
**Severity:** Medium
**Observed:** Snippets like `"mcp-server-tree-sitterMCPserver"` and
`"installmcp_server_tree_sitter.server:mcp"` — HTML `<span>` and `<b>` tags
stripped without adding space boundaries.
**Root cause:** The HTML-to-text conversion in the DuckDuckGo searcher doesn't
add spaces when removing inline tags.
**Fix:** In `src/scout/searcher/duckduckgo.py`, after stripping HTML tags,
apply:
```python
import re
snippet = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', snippet)  # camelCase split
snippet = re.sub(r'\s+', ' ', snippet).strip()
```
Or use `BeautifulSoup(snippet, "html.parser").get_text(separator=" ")` instead
of tag-stripping.

#### QA-SC02 — `deduplicated` field in deep-search response is semantically wrong
**Severity:** Low
**Observed:** `deep_search` response: `"total_raw_hits": 40, "count": 5, "deduplicated": 0`.
If 40 raw hits were collapsed to 5, the field should show 35 (removed), not 0.
A value of 0 implies no deduplication occurred.
**Fix:** Either rename to `deduplicated_count` and set it to `total_raw_hits - count`,
or rename to `after_dedup` and set it to `count` (more explicit). Update the
Go `DeepSearchResponse` struct to match.

#### QA-SC03 — Fragment summary always says "code entity" for web content
**Dependency on BUG-I03 in synapses-intelligence.**
**Observed:** `fragment.summary: "This code entity provides information about..."`
for a web article. The intelligence ingestor uses "code entity" in its prompt
regardless of `node_type`.
**Fix in scout:** Pass `node_type` in the ingest payload (already done via
`_NODE_TYPE_MAP`). The fix must be in intelligence's prompt template.
**Workaround in scout:** Strip "code entity" from summaries and replace with
"web article" / "search result" based on `content_type` before returning in
`ScoutFragment`.

---

### ARCHITECTURE IMPROVEMENTS

#### ARCH-SC01 — No async/background distillation path
**Observed:** Distillation is synchronous — fetch blocks until intelligence
returns the summary. With 1.5b model on CPU, this adds 16s to every fetch.
Most callers want the content immediately; the summary is a bonus.
**Improvement:** Add `distill_async: true` option. When set:
  1. Return the fetch result immediately with `fragment: null`.
  2. Fire-and-forget the distillation in a background task.
  3. On next fetch of the same URL (cache hit), return the now-populated fragment.
This matches how the file watcher in synapses works (incremental ingest in background).

#### ARCH-SC02 — No `/v1/cache/search` or per-URL cache invalidation
**Observed:** Only `DELETE /v1/cache` exists (full cache clear). There is no:
  - `DELETE /v1/cache/{type}` (clear by content type)
  - `DELETE /v1/cache?url=X` (invalidate specific URL)
  - `GET /v1/cache/entries` (list cached URLs)
**Improvement:** Add these endpoints for operational control. Especially useful
when a page changes and you want to force re-fetch without clearing the entire cache.

#### ARCH-SC03 — Scout SQLite cache (`scout.db`) is separate from brain.sqlite
**Observed:** Scout caches raw web content in its own `~/.synapses/scout.db`,
while intelligence stores summaries in `~/.synapses/brain.sqlite`. These are
two separate SQLite files with no shared schema.
**Impact:** No way to query "what web pages has scout fetched AND what are their
brain summaries?" without two separate API calls.
**Improvement:** Add a `scout.db` table that links `cache_key → brain_node_id`
so the scout response can include the brain summary directly from the cache
lookup, without an additional `/v1/summary` round-trip.

#### ARCH-SC04 — No node-ID namespace alignment between scout and synapses graph
**Observed:** Scout creates node IDs like `scout:web_page:a1b2c3d4e5f6` (hash
of URL). These IDs exist only in brain.sqlite. Synapses graph nodes have IDs
like `synapses-os::synapses/internal/mcp/tools.go::Server.handleGetContext`.
There is no cross-reference or link between web content and code nodes.
**Improvement:** The `web_annotate` MCP tool (already in synapses) writes
web findings as annotations on graph nodes. This is the right link mechanism.
Consider also adding a `web_node_ids: []string` field to graph node metadata
when `web_annotate` is called, enabling `get_context` to surface web summaries
alongside code summaries.

---

### WHAT WORKS WELL ✅

- DuckDuckGo search: fast (~1.9s), multi-engine fallback (grokipedia errors
  non-fatal, falls back to yandex/primp).
- Web fetch: fast (~1.7s), clean markdown extraction via trafilatura.
- Cache: web page cache works correctly, cache-hit returns in <50ms.
- Deep search: query expansion generates useful variants, 1.8s total.
- Scout→intelligence path: once timeout is fixed (60s), distillation works
  correctly and summaries land in brain.sqlite.
- `intelligence_available` in health check: correctly reflects brain reachability.
- Fail-silent: scout errors never crash synapses or block tool calls.
