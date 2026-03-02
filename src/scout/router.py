"""URL type detection and routing."""

from __future__ import annotations

from urllib.parse import urlparse

from scout.models import ContentType

_YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}


def classify(input_str: str) -> ContentType:
    """Classify an input string as a search query, web page, or YouTube URL."""
    stripped = input_str.strip()
    if not stripped:
        return ContentType.SEARCH

    try:
        parsed = urlparse(stripped)
    except ValueError:
        return ContentType.SEARCH

    # Must have a scheme and a host with a dot to be a URL
    if not parsed.scheme or not parsed.netloc or "." not in parsed.netloc:
        # Try with https:// prefix for bare domains
        if "." in stripped and " " not in stripped:
            try:
                parsed = urlparse(f"https://{stripped}")
            except ValueError:
                return ContentType.SEARCH
        else:
            return ContentType.SEARCH

    host = parsed.hostname or ""
    if host in _YOUTUBE_HOSTS:
        return ContentType.YOUTUBE

    return ContentType.WEB_PAGE


def ensure_url(input_str: str) -> str:
    """Ensure input has a URL scheme. Adds https:// if missing."""
    stripped = input_str.strip()
    parsed = urlparse(stripped)
    if not parsed.scheme:
        return f"https://{stripped}"
    return stripped
