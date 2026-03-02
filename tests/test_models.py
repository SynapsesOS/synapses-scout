"""Tests for Pydantic models."""

from scout.models import ContentType, ScoutFragment, ScoutResult


class TestScoutResult:
    def test_to_markdown_basic(self):
        result = ScoutResult(
            url="https://example.com",
            content_type=ContentType.WEB_PAGE,
            title="Test Page",
            content_md="Hello world",
            word_count=2,
        )
        md = result.to_markdown()
        assert "---" in md
        assert "url: https://example.com" in md
        assert "content_type: web_page" in md
        assert "# Test Page" in md
        assert "Hello world" in md

    def test_to_markdown_with_fragment(self):
        result = ScoutResult(
            url="https://example.com",
            content_type=ContentType.WEB_PAGE,
            title="Test Page",
            content_md="Content here",
            word_count=2,
            fragment=ScoutFragment(summary="A test summary", tags=["test"]),
        )
        md = result.to_markdown()
        assert "summary:" in md
        assert "tags:" in md
        assert "> A test summary" in md

    def test_to_markdown_with_metadata(self):
        result = ScoutResult(
            url="https://youtube.com/watch?v=abc",
            content_type=ContentType.YOUTUBE,
            title="Video",
            content_md="Transcript",
            word_count=1,
            metadata={"channel": "TestChannel", "duration_seconds": 300},
        )
        md = result.to_markdown()
        assert "channel:" in md
        assert "duration_seconds: 300" in md

    def test_model_dump_json(self):
        result = ScoutResult(
            url="https://example.com",
            content_type=ContentType.WEB_PAGE,
            title="Test",
            content_md="Hi",
        )
        json_str = result.model_dump_json()
        assert "web_page" in json_str
        assert "example.com" in json_str
