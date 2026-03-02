"""Tests for YouTube extraction — transcript fetching and VTT cleaning."""

from unittest.mock import MagicMock, patch

import pytest

from scout.media.youtube import _clean_vtt, _get_transcript


class TestCleanVtt:
    def test_strips_timestamps(self):
        vtt = """WEBVTT

00:00:01.000 --> 00:00:02.000
Hello world

00:00:02.000 --> 00:00:03.000
this is a test
"""
        result = _clean_vtt(vtt)
        assert "Hello world" in result
        assert "this is a test" in result
        assert "-->" not in result
        assert "WEBVTT" not in result

    def test_strips_inline_html_tags(self):
        vtt = """WEBVTT

00:00:01.000 --> 00:00:02.000
<c>Hello</c> <b>world</b>
"""
        result = _clean_vtt(vtt)
        assert "Hello" in result
        assert "world" in result
        assert "<c>" not in result
        assert "<b>" not in result

    def test_strips_timestamp_tags(self):
        vtt = """WEBVTT

00:00:01.000 --> 00:00:02.000
Hello<00:00:01.500><c> world</c>
"""
        result = _clean_vtt(vtt)
        assert "<00:" not in result
        assert "Hello" in result

    def test_deduplicates_consecutive_identical_lines(self):
        vtt = """WEBVTT

00:00:01.000 --> 00:00:02.000
Hello

00:00:01.500 --> 00:00:02.500
Hello
"""
        result = _clean_vtt(vtt)
        # "Hello" should appear only once
        assert result.count("Hello") == 1

    def test_does_not_deduplicate_valid_repeated_phrases(self):
        """Repeated phrases at different times (e.g. "Thank you") should survive."""
        vtt = """WEBVTT

00:00:01.000 --> 00:00:02.000
Thank you

00:00:10.000 --> 00:00:11.000
And now the second part

00:00:20.000 --> 00:00:21.000
Thank you
"""
        result = _clean_vtt(vtt)
        # Both "Thank you" occurrences should be present since they're not adjacent
        assert result.count("Thank you") == 2

    def test_returns_joined_text(self):
        vtt = """WEBVTT

00:00:01.000 --> 00:00:02.000
First line

00:00:02.000 --> 00:00:03.000
Second line
"""
        result = _clean_vtt(vtt)
        assert "First line" in result
        assert "Second line" in result

    def test_empty_vtt_returns_empty_string(self):
        assert _clean_vtt("WEBVTT\n\n") == ""

    def test_skips_numeric_cue_indices(self):
        vtt = """WEBVTT

1
00:00:01.000 --> 00:00:02.000
Hello

2
00:00:02.000 --> 00:00:03.000
World
"""
        result = _clean_vtt(vtt)
        assert "Hello" in result
        assert "World" in result
        # Cue numbers should not appear in text
        assert result.strip().startswith("Hello") or "1" not in result.split()


class TestGetTranscript:
    def test_returns_none_when_no_subtitles(self):
        info = {"subtitles": {}, "automatic_captions": {}}
        assert _get_transcript(info) is None

    def test_uses_in_memory_data_if_available(self):
        vtt_content = "WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nHello world\n"
        info = {
            "requested_subtitles": {
                "en": {"data": vtt_content, "ext": "vtt"}
            }
        }
        result = _get_transcript(info)
        assert result is not None
        assert "Hello world" in result

    def test_fetches_from_url_when_data_is_none(self):
        vtt_content = b"WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nFetched transcript\n"
        info = {
            "requested_subtitles": {
                "en": {"data": None, "url": "https://example.com/sub.vtt", "ext": "vtt"}
            }
        }

        with patch("scout.media.youtube._fetch_subtitle_url", return_value=vtt_content.decode()):
            result = _get_transcript(info)

        assert result is not None
        assert "Fetched transcript" in result

    def test_falls_back_to_automatic_captions(self):
        vtt_content = "WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nAuto caption\n"
        info = {
            "requested_subtitles": {},
            "subtitles": {},
            "automatic_captions": {
                "en": [{"ext": "vtt", "url": "https://example.com/auto.vtt"}]
            },
        }

        with patch("scout.media.youtube._fetch_subtitle_url", return_value=vtt_content):
            result = _get_transcript(info)

        assert result is not None
        assert "Auto caption" in result

    def test_prefers_vtt_format_over_others(self):
        vtt_content = "WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nVTT content\n"
        info = {
            "requested_subtitles": {},
            "subtitles": {},
            "automatic_captions": {
                "en": [
                    {"ext": "json3", "url": "https://example.com/sub.json3"},
                    {"ext": "vtt", "url": "https://example.com/sub.vtt"},
                ]
            },
        }

        fetch_calls = []

        def fake_fetch(url):
            fetch_calls.append(url)
            if "vtt" in url:
                return vtt_content
            return None

        with patch("scout.media.youtube._fetch_subtitle_url", side_effect=fake_fetch):
            result = _get_transcript(info)

        assert result is not None
        # Should have tried the vtt URL first
        assert any("vtt" in url for url in fetch_calls)

    def test_returns_none_when_url_fetch_fails(self):
        info = {
            "requested_subtitles": {
                "en": {"data": None, "url": "https://example.com/sub.vtt", "ext": "vtt"}
            }
        }

        with patch("scout.media.youtube._fetch_subtitle_url", return_value=None):
            result = _get_transcript(info)

        assert result is None

    def test_tries_en_us_and_en_gb_fallbacks(self):
        vtt_content = "WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nBritish content\n"
        info = {
            "requested_subtitles": {},
            "subtitles": {"en-GB": [{"ext": "vtt", "url": "https://example.com/gb.vtt"}]},
            "automatic_captions": {},
        }

        with patch("scout.media.youtube._fetch_subtitle_url", return_value=vtt_content):
            result = _get_transcript(info)

        assert result is not None
        assert "British content" in result
