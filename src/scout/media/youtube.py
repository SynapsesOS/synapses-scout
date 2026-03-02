"""YouTube metadata and transcript extraction via yt-dlp."""

from __future__ import annotations

import asyncio
import re
import urllib.request
from datetime import datetime, timezone
from functools import partial

from scout.models import MediaContent


async def extract_youtube(url: str) -> MediaContent:
    """Extract YouTube video metadata and transcript."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, partial(_extract_sync, url))


def _extract_sync(url: str) -> MediaContent:
    import yt_dlp

    opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "writesubtitles": False,   # we fetch subtitle URLs manually below
        "writeautomaticsub": False,
        "subtitleslangs": ["en"],
        "subtitlesformat": "vtt",
    }

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)

    if info is None:
        return MediaContent(url=url, title="", extracted_at=datetime.now(timezone.utc))

    transcript = _get_transcript(info)

    return MediaContent(
        url=url,
        title=info.get("title", ""),
        channel=info.get("channel", "") or info.get("uploader", ""),
        duration_seconds=info.get("duration", 0) or 0,
        upload_date=info.get("upload_date", ""),
        description=info.get("description", "") or "",
        transcript=transcript,
        view_count=info.get("view_count", 0) or 0,
        thumbnail_url=info.get("thumbnail", "") or "",
        extracted_at=datetime.now(timezone.utc),
    )


def _fetch_subtitle_url(url: str) -> str | None:
    """Fetch a subtitle file from a URL. Returns raw text or None on failure."""
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; SynapsesScout/0.0.1)"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception:
        return None


def _get_transcript(info: dict) -> str | None:
    """Extract English transcript from yt-dlp info dict.

    yt-dlp populates subtitle URLs in the info dict even with download=False,
    but the 'data' key is only filled when actually writing to disk.
    We fetch the subtitle URL directly to get the content.
    """
    # 1. Check requested_subtitles (populated by yt-dlp even without downloading)
    requested = info.get("requested_subtitles") or {}
    for lang_key in ["en", "en-US", "en-GB"]:
        if sub := requested.get(lang_key):
            if data := sub.get("data"):
                return _clean_vtt(data)
            if sub_url := sub.get("url"):
                if text := _fetch_subtitle_url(sub_url):
                    return _clean_vtt(text)

    # 2. Fallback: scan subtitles then automatic_captions dicts for a VTT URL
    for sub_dict in [info.get("subtitles", {}), info.get("automatic_captions", {})]:
        for lang_key in ["en", "en-US", "en-GB"]:
            entries = sub_dict.get(lang_key) or []
            # Prefer VTT format, fall back to any format
            vtt_entries = [e for e in entries if e.get("ext") == "vtt"]
            for entry in vtt_entries or entries:
                if data := entry.get("data"):
                    return _clean_vtt(data)
                if sub_url := entry.get("url"):
                    if text := _fetch_subtitle_url(sub_url):
                        return _clean_vtt(text)

    return None


def _clean_vtt(vtt_text: str) -> str:
    """Strip VTT timestamps and formatting, return plain text.

    YouTube auto-captions use a sliding-window approach where each cue
    partially overlaps the previous. We use prev-line comparison instead of
    a global seen-set to avoid incorrectly deduplicating valid repeated phrases
    (e.g. "Thank you" appearing multiple times in a transcript).
    """
    lines: list[str] = []
    prev = ""
    for line in vtt_text.splitlines():
        line = line.strip()
        # Skip VTT headers, timestamp lines, cue index numbers, and blank lines
        if not line or line.startswith("WEBVTT") or "-->" in line or line.isdigit():
            continue
        # Strip inline tags like <00:00:01.000><c> and HTML tags
        clean = re.sub(r"<[^>]+>", "", line).strip()
        if not clean or clean == prev:
            continue
        lines.append(clean)
        prev = clean
    return " ".join(lines)
