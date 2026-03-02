"""Pydantic models for Scout inputs and outputs."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class ContentType(str, Enum):
    SEARCH = "search"
    WEB_PAGE = "web_page"
    YOUTUBE = "youtube"


class SearchHit(BaseModel):
    title: str
    url: str
    snippet: str = ""


class NewsHit(BaseModel):
    title: str
    url: str
    snippet: str = ""
    source: str = ""
    date: str = ""


class ImageHit(BaseModel):
    title: str
    url: str
    image_url: str
    thumbnail_url: str = ""
    width: int = 0
    height: int = 0
    source: str = ""


class SearchResult(BaseModel):
    query: str
    provider: str
    hits: list[SearchHit] = Field(default_factory=list)
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class WebContent(BaseModel):
    url: str
    title: str
    content_md: str
    word_count: int = 0
    extracted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class MediaContent(BaseModel):
    url: str
    title: str
    channel: str = ""
    duration_seconds: int = 0
    upload_date: str = ""
    description: str = ""
    transcript: str | None = None
    view_count: int = 0
    thumbnail_url: str = ""
    extracted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ScoutFragment(BaseModel):
    """Distilled summary from synapses-intelligence."""

    summary: str
    tags: list[str] = Field(default_factory=list)
    distilled_by: str = ""


class ScoutResult(BaseModel):
    """Unified output of Scout.fetch()."""

    url: str
    content_type: ContentType
    title: str
    content_md: str
    word_count: int = 0
    metadata: dict = Field(default_factory=dict)
    fragment: ScoutFragment | None = None
    cached: bool = False
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def to_markdown(self) -> str:
        """Render as GFM Markdown with YAML frontmatter."""
        lines = ["---"]
        lines.append(f"url: {self.url}")
        lines.append(f"title: {json.dumps(self.title)}")
        lines.append(f"content_type: {self.content_type.value}")
        lines.append(f"word_count: {self.word_count}")
        lines.append(f"fetched_at: {self.fetched_at.isoformat()}")
        lines.append(f"cached: {str(self.cached).lower()}")

        if self.fragment:
            lines.append(f"summary: {json.dumps(self.fragment.summary)}")
            lines.append(f"tags: {json.dumps(self.fragment.tags)}")

        if self.metadata:
            for key, value in self.metadata.items():
                lines.append(f"{key}: {json.dumps(value, default=str)}")

        lines.append("---")
        lines.append("")

        if self.fragment and self.fragment.summary:
            lines.append(f"> {self.fragment.summary}")
            lines.append("")

        lines.append(f"# {self.title}")
        lines.append("")
        lines.append(self.content_md)

        return "\n".join(lines)
