"""Synapses-Scout: Web intelligence acquisition layer for Synapses-OS."""

__version__ = "0.0.1"

from scout.scout import Scout
from scout.models import ContentType, ImageHit, NewsHit, ScoutResult, SearchHit

__all__ = ["Scout", "ScoutResult", "ContentType", "SearchHit", "NewsHit", "ImageHit"]
