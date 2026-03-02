"""Scout configuration — loads from ~/.synapses/scout.json with env overrides."""

from __future__ import annotations

import json
import os
from pathlib import Path

from pydantic import BaseModel


class ScoutConfig(BaseModel):
    port: int = 11436
    db_path: str = "~/.synapses/scout.db"
    intelligence_url: str = "http://localhost:11435"
    intelligence_timeout_ms: int = 5000
    search_provider: str = "duckduckgo"  # "duckduckgo" | "tavily"
    tavily_api_key: str | None = None
    distill: bool = True
    max_content_chars: int = 50_000
    default_ttl_search_hours: int = 6
    default_ttl_web_hours: int = 24
    default_ttl_media_hours: int = 168  # 7 days
    default_ttl_doc_hours: int = 720  # 30 days

    # Search defaults
    search_region: str = "wt-wt"  # global by default
    search_safesearch: str = "moderate"
    search_expand: bool = True  # enable query expansion / orchestration

    @property
    def resolved_db_path(self) -> Path:
        return Path(self.db_path).expanduser()


def load_config(config_path: str | None = None) -> ScoutConfig:
    """Load config: defaults -> file -> env overrides.

    Args:
        config_path: Explicit path to scout.json. If None, reads SCOUT_CONFIG
                     env var, falling back to ~/.synapses/scout.json.
    """
    if config_path is None:
        config_path = os.environ.get("SCOUT_CONFIG", str(Path.home() / ".synapses" / "scout.json"))
    data: dict = {}

    path = Path(config_path)
    if path.exists():
        with open(path) as f:
            data = json.load(f)

    # Env overrides for secrets and common settings
    if api_key := os.environ.get("TAVILY_API_KEY"):
        data["tavily_api_key"] = api_key
    if port := os.environ.get("SCOUT_PORT"):
        data["port"] = int(port)
    if url := os.environ.get("SCOUT_INTELLIGENCE_URL"):
        data["intelligence_url"] = url

    return ScoutConfig(**data)
