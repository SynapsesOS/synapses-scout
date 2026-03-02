"""YouTube metadata and transcript extraction via yt-dlp."""

from __future__ import annotations

import asyncio
import re
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
        "writesubtitles": True,
        "writeautomaticsub": True,
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


def _get_transcript(info: dict) -> str | None:
    """Try to extract English subtitles/auto-captions from yt-dlp info."""
    # Check for requested subtitles (auto or manual)
    requested = info.get("requested_subtitles") or {}
    for lang_key in ["en", "en-US", "en-GB"]:
        if sub := requested.get(lang_key):
            if data := sub.get("data"):
                return _clean_vtt(data)

    # Fallback: check subtitles dict
    for sub_dict in [info.get("subtitles", {}), info.get("automatic_captions", {})]:
        for lang_key in ["en", "en-US", "en-GB"]:
            if entries := sub_dict.get(lang_key):
                for entry in entries:
                    if data := entry.get("data"):
                        return _clean_vtt(data)

    return None


def _clean_vtt(vtt_text: str) -> str:
    """Strip VTT timestamps and formatting, return plain text."""
    lines: list[str] = []
    seen: set[str] = set()
    for line in vtt_text.splitlines():
        line = line.strip()
        # Skip headers, timestamps, and blank lines
        if not line or line.startswith("WEBVTT") or "-->" in line or line.isdigit():
            continue
        # Strip HTML tags
        clean = re.sub(r"<[^>]+>", "", line).strip()
        if clean and clean not in seen:
            seen.add(clean)
            lines.append(clean)
    return " ".join(lines)
