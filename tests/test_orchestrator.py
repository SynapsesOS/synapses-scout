"""Tests for the search orchestrator."""

import pytest
from unittest.mock import AsyncMock

from scout.models import SearchHit
from scout.orchestrator import (
    deduplicate_and_score,
    expand_query,
    orchestrated_search,
)


class TestExpandQuery:
    def test_basic_expansion(self):
        queries = expand_query("python async")
        assert queries[0] == "python async"
        assert len(queries) >= 3
        assert any("what is" in q for q in queries)
        assert any("explained" in q for q in queries)

    def test_question_skips_what_is(self):
        queries = expand_query("how does asyncio work")
        assert not any(q.startswith("what is") for q in queries)

    def test_short_query_no_expansion(self):
        queries = expand_query("foo")
        assert queries == ["foo"]

    def test_url_like_no_expansion(self):
        queries = expand_query("example.com")
        assert queries == ["example.com"]

    def test_year_in_query_skips_latest(self):
        queries = expand_query("python changes 2026")
        assert not any("latest 2026" in q for q in queries)


class TestDeduplicateAndScore:
    def test_deduplicates_by_url(self):
        results = {
            "query 1": [
                SearchHit(title="A", url="https://example.com/page", snippet="first"),
                SearchHit(title="B", url="https://other.com", snippet="second"),
            ],
            "query 2": [
                SearchHit(title="A alt", url="https://example.com/page/", snippet="longer first snippet here"),
                SearchHit(title="C", url="https://third.com", snippet="third"),
            ],
        }
        ranked = deduplicate_and_score(results)

        urls = [h.url for h in ranked]
        # example.com/page appears in both queries — should be ranked higher
        assert ranked[0].url in ("https://example.com/page", "https://example.com/page/")
        # Should have 3 unique URLs, not 4
        normalized = set(u.rstrip("/").lower() for u in urls)
        assert len(normalized) == 3

    def test_original_query_gets_boost(self):
        results = {
            "original": [
                SearchHit(title="From Original", url="https://orig.com", snippet="x" * 100),
            ],
            "expanded": [
                SearchHit(title="From Expanded", url="https://exp.com", snippet="y" * 100),
            ],
        }
        ranked = deduplicate_and_score(results)
        # Original query result should be first due to boost
        assert ranked[0].url == "https://orig.com"

    def test_empty_input(self):
        assert deduplicate_and_score({}) == []

    def test_keeps_longer_snippet(self):
        results = {
            "q1": [SearchHit(title="A", url="https://a.com", snippet="short")],
            "q2": [SearchHit(title="A", url="https://a.com", snippet="this is a much longer snippet with more detail")],
        }
        ranked = deduplicate_and_score(results)
        assert "much longer" in ranked[0].snippet


class TestOrchestratedSearch:
    @pytest.mark.asyncio
    async def test_parallel_fanout(self):
        mock_searcher = AsyncMock()
        mock_searcher.search = AsyncMock(return_value=[
            SearchHit(title="R", url="https://r.com", snippet="result"),
        ])

        orch = await orchestrated_search(
            mock_searcher, "test query", max_results=5, expand=True
        )

        assert orch.original_query == "test query"
        assert len(orch.expanded_queries) > 1
        # search was called once per expanded query
        assert mock_searcher.search.call_count == len(orch.expanded_queries)

    @pytest.mark.asyncio
    async def test_no_expand(self):
        mock_searcher = AsyncMock()
        mock_searcher.search = AsyncMock(return_value=[
            SearchHit(title="R", url="https://r.com", snippet="result"),
        ])

        orch = await orchestrated_search(
            mock_searcher, "single", max_results=5, expand=False
        )

        assert orch.expanded_queries == ["single"]
        mock_searcher.search.assert_called_once()

    @pytest.mark.asyncio
    async def test_handles_search_failures(self):
        call_count = 0

        async def flaky_search(q, max_results, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise ConnectionError("network error")
            return [SearchHit(title="R", url=f"https://r{call_count}.com", snippet="ok")]

        mock_searcher = AsyncMock()
        mock_searcher.search = flaky_search

        orch = await orchestrated_search(
            mock_searcher, "test", max_results=5, expand=True
        )

        # Should still return results from successful queries
        assert len(orch.hits) > 0
