"""Tests for URL classification router."""

from scout.models import ContentType
from scout.router import classify, ensure_url


class TestClassify:
    def test_plain_text_is_search(self):
        assert classify("python async patterns") == ContentType.SEARCH

    def test_empty_is_search(self):
        assert classify("") == ContentType.SEARCH

    def test_question_is_search(self):
        assert classify("how does asyncio work?") == ContentType.SEARCH

    def test_youtube_url(self):
        assert classify("https://www.youtube.com/watch?v=abc123") == ContentType.YOUTUBE

    def test_youtu_be_short(self):
        assert classify("https://youtu.be/abc123") == ContentType.YOUTUBE

    def test_mobile_youtube(self):
        assert classify("https://m.youtube.com/watch?v=abc123") == ContentType.YOUTUBE

    def test_web_url(self):
        assert classify("https://example.com/article") == ContentType.WEB_PAGE

    def test_http_url(self):
        assert classify("http://docs.python.org/3/") == ContentType.WEB_PAGE

    def test_bare_domain_is_web(self):
        assert classify("example.com") == ContentType.WEB_PAGE

    def test_url_with_path(self):
        assert classify("https://realpython.com/async-io-python/") == ContentType.WEB_PAGE


class TestEnsureUrl:
    def test_adds_scheme(self):
        assert ensure_url("example.com") == "https://example.com"

    def test_preserves_existing_scheme(self):
        assert ensure_url("http://example.com") == "http://example.com"

    def test_strips_whitespace(self):
        assert ensure_url("  https://example.com  ") == "https://example.com"
