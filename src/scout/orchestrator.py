"""Search orchestrator — multi-query fan-out, deduplication, and relevance scoring.

Given a single user query, the orchestrator:
1. Expands it into multiple search angles (original + reformulations)
2. Fans out searches in parallel
3. Merges and deduplicates results by URL
4. Scores results by relevance (frequency across queries + snippet quality)
5. Returns ranked, deduplicated hits

This gives synapses-os significantly better coverage than a single search query.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime

from scout.models import SearchHit

log = logging.getLogger(__name__)


@dataclass
class ScoredHit:
    """A search hit enriched with a relevance score."""

    hit: SearchHit
    score: float = 0.0
    seen_in_queries: int = 1


@dataclass
class OrchestratedResult:
    """Result of an orchestrated multi-query search."""

    original_query: str
    expanded_queries: list[str] = field(default_factory=list)
    hits: list[SearchHit] = field(default_factory=list)
    total_raw_hits: int = 0
    deduplicated_count: int = 0


def expand_query(query: str) -> list[str]:
    """Expand a query into multiple search angles for better coverage.

    Strategies:
    - Original query (always first)
    - "what is <query>" for definitional results
    - "<query> explained" for tutorial/article results
    - "<query> latest 2026" for recency (if query doesn't already have a year)
    """
    queries = [query]
    clean = query.strip()

    # Skip expansion for very short or URL-like queries
    if len(clean) < 5 or "." in clean:
        return queries

    # Don't add "what is" if query is already a question
    if not clean.lower().startswith(("what", "how", "why", "when", "where", "who")):
        queries.append(f"what is {clean}")

    queries.append(f"{clean} explained")

    # Add recency if no year in query
    if not re.search(r"\b20\d{2}\b", clean):
        queries.append(f"{clean} latest {datetime.now().year}")

    return queries


def deduplicate_and_score(
    results_per_query: dict[str, list[SearchHit]],
) -> list[SearchHit]:
    """Merge results from multiple queries, deduplicate by URL, score by relevance.

    Scoring:
    - +1.0 for each query the result appears in (cross-query frequency)
    - +0.5 if snippet is substantial (>80 chars)
    - +0.3 if title contains query terms
    - Results from the original query (first key) get +0.5 boost
    """
    url_map: dict[str, ScoredHit] = {}
    queries = list(results_per_query.keys())
    original_query = queries[0] if queries else ""
    original_terms = set(original_query.lower().split())

    for query_idx, (query, hits) in enumerate(results_per_query.items()):
        for rank, hit in enumerate(hits):
            normalized_url = hit.url.rstrip("/").lower()

            if normalized_url in url_map:
                scored = url_map[normalized_url]
                scored.score += 1.0  # cross-query frequency
                scored.seen_in_queries += 1
                # Keep the longer snippet
                if len(hit.snippet) > len(scored.hit.snippet):
                    scored.hit = SearchHit(
                        title=hit.title or scored.hit.title,
                        url=scored.hit.url,
                        snippet=hit.snippet,
                    )
            else:
                score = 1.0
                # Original query boost
                if query_idx == 0:
                    score += 0.5
                # Position decay within query
                score += max(0, (10 - rank) * 0.1)
                # Snippet quality
                if len(hit.snippet) > 80:
                    score += 0.5
                # Title relevance
                title_lower = hit.title.lower()
                matching_terms = sum(1 for t in original_terms if t in title_lower)
                score += matching_terms * 0.3

                url_map[normalized_url] = ScoredHit(hit=hit, score=score)

    # Sort by score descending
    ranked = sorted(url_map.values(), key=lambda s: s.score, reverse=True)
    return [s.hit for s in ranked]


async def orchestrated_search(
    searcher,
    query: str,
    max_results: int = 10,
    *,
    expand: bool = True,
    region: str = "wt-wt",
    timelimit: str | None = None,
    safesearch: str = "moderate",
) -> OrchestratedResult:
    """Run an orchestrated multi-query search with fan-out and deduplication.

    Args:
        searcher: A DuckDuckGoSearcher (or any searcher with .search()).
        query: The user's original query.
        max_results: Max final results to return after dedup.
        expand: Whether to expand the query into multiple angles.
        region: DDG region code.
        timelimit: Time filter.
        safesearch: SafeSearch level.
    """
    queries = expand_query(query) if expand else [query]
    # Fetch at least 2x max_results per query so deduplication has meaningful
    # overlap material — otherwise small max_results (e.g. 5) leaves only ~10
    # unique hits across 4 queries, weakening the ranking signal.
    per_query_max = max(max_results * 2, 10)

    # Fan-out: search all queries in parallel
    tasks = [
        searcher.search(
            q,
            per_query_max,
            region=region,
            timelimit=timelimit,
            safesearch=safesearch,
        )
        for q in queries
    ]
    all_results = await asyncio.gather(*tasks, return_exceptions=True)

    # Collect successful results
    results_per_query: dict[str, list[SearchHit]] = {}
    total_raw = 0
    for q, result in zip(queries, all_results):
        if isinstance(result, Exception):
            log.warning("search failed for expanded query %r: %s", q, result)
            continue
        results_per_query[q] = result
        total_raw += len(result)

    # Deduplicate and score
    ranked_hits = deduplicate_and_score(results_per_query)

    # Trim to max_results
    final_hits = ranked_hits[:max_results]

    return OrchestratedResult(
        original_query=query,
        expanded_queries=queries,
        hits=final_hits,
        total_raw_hits=total_raw,
        deduplicated_count=total_raw - len(ranked_hits),
    )
