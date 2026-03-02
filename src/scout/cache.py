"""SQLite cache for Scout results with TTL-based expiry."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse, urlunparse

import aiosqlite

from scout.models import ContentType, ScoutFragment, ScoutResult

_TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "ref",
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS scout_cache (
    url_hash     TEXT PRIMARY KEY,
    url          TEXT NOT NULL,
    content_type TEXT NOT NULL,
    title        TEXT NOT NULL DEFAULT '',
    content_md   TEXT NOT NULL,
    metadata     TEXT NOT NULL DEFAULT '{}',
    summary      TEXT NOT NULL DEFAULT '',
    tags         TEXT NOT NULL DEFAULT '[]',
    fetched_at   TEXT NOT NULL,
    expires_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cache_expires ON scout_cache(expires_at);

CREATE TABLE IF NOT EXISTS search_cache (
    query_hash  TEXT PRIMARY KEY,
    query       TEXT NOT NULL,
    provider    TEXT NOT NULL,
    results     TEXT NOT NULL,
    metadata    TEXT NOT NULL DEFAULT '{}',
    fetched_at  TEXT NOT NULL,
    expires_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_search_expires ON search_cache(expires_at);
"""

_MIGRATIONS = [
    # Add metadata column to search_cache if it doesn't exist (added in v0.0.2).
    "ALTER TABLE search_cache ADD COLUMN metadata TEXT NOT NULL DEFAULT '{}'",
]


def normalize_url(url: str) -> str:
    """Normalize a URL for consistent cache keys."""
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    path = parsed.path.rstrip("/") or "/"
    # Filter tracking params and sort remaining
    params = parse_qs(parsed.query, keep_blank_values=True)
    filtered = {k: v for k, v in sorted(params.items()) if k.lower() not in _TRACKING_PARAMS}
    query = "&".join(f"{k}={v[0]}" for k, v in filtered.items()) if filtered else ""
    return urlunparse((parsed.scheme.lower(), host, path, "", query, ""))


def url_hash(url: str) -> str:
    return hashlib.sha256(normalize_url(url).encode()).hexdigest()[:32]


def query_hash(query: str) -> str:
    normalized = re.sub(r"\s+", " ", query.strip().lower())
    return hashlib.sha256(normalized.encode()).hexdigest()[:32]


class Cache:
    def __init__(self, db: aiosqlite.Connection):
        self._db = db

    @classmethod
    async def open(cls, db_path: str | Path) -> Cache:
        path = Path(db_path).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        db = await aiosqlite.connect(str(path))
        db.row_factory = aiosqlite.Row
        await db.executescript(_SCHEMA)
        await db.commit()
        # Apply migrations (idempotent — ignore errors for already-applied ones).
        for sql in _MIGRATIONS:
            try:
                await db.execute(sql)
                await db.commit()
            except Exception:
                pass
        instance = cls(db)
        await instance.prune()
        return instance

    async def get(self, url: str) -> ScoutResult | None:
        """Get a cached result if it exists and hasn't expired."""
        h = url_hash(url)
        now = datetime.now(timezone.utc).isoformat()
        async with self._db.execute(
            "SELECT * FROM scout_cache WHERE url_hash = ? AND expires_at > ?", (h, now)
        ) as cursor:
            row = await cursor.fetchone()

        if not row:
            return None

        fragment = None
        if row["summary"]:
            fragment = ScoutFragment(
                summary=row["summary"],
                tags=json.loads(row["tags"]),
            )

        return ScoutResult(
            url=row["url"],
            content_type=ContentType(row["content_type"]),
            title=row["title"],
            content_md=row["content_md"],
            word_count=len(row["content_md"].split()),
            metadata=json.loads(row["metadata"]),
            fragment=fragment,
            cached=True,
            fetched_at=datetime.fromisoformat(row["fetched_at"]),
        )

    async def put(self, result: ScoutResult, ttl_hours: int) -> None:
        """Cache a ScoutResult with the given TTL."""
        h = url_hash(result.url)
        now = datetime.now(timezone.utc)
        expires = now + timedelta(hours=ttl_hours)

        summary = result.fragment.summary if result.fragment else ""
        tags = json.dumps(result.fragment.tags) if result.fragment else "[]"

        await self._db.execute(
            """INSERT OR REPLACE INTO scout_cache
               (url_hash, url, content_type, title, content_md, metadata, summary, tags, fetched_at, expires_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                h,
                result.url,
                result.content_type.value,
                result.title,
                result.content_md,
                json.dumps(result.metadata),
                summary,
                tags,
                now.isoformat(),
                expires.isoformat(),
            ),
        )
        await self._db.commit()

    async def get_search(self, query: str) -> dict | None:
        """Get cached search results."""
        h = query_hash(query)
        now = datetime.now(timezone.utc).isoformat()
        async with self._db.execute(
            "SELECT * FROM search_cache WHERE query_hash = ? AND expires_at > ?", (h, now)
        ) as cursor:
            row = await cursor.fetchone()
        if not row:
            return None
        extra = json.loads(row["metadata"]) if row["metadata"] else {}
        return {
            "query": row["query"],
            "provider": row["provider"],
            "results": json.loads(row["results"]),
            "fetched_at": row["fetched_at"],
            **extra,
        }

    async def put_search(
        self,
        query: str,
        provider: str,
        results: list[dict],
        ttl_hours: int,
        extra: dict | None = None,
    ) -> None:
        """Cache search results. extra holds orchestration metadata (queries_used, etc.)."""
        h = query_hash(query)
        now = datetime.now(timezone.utc)
        expires = now + timedelta(hours=ttl_hours)

        await self._db.execute(
            """INSERT OR REPLACE INTO search_cache
               (query_hash, query, provider, results, metadata, fetched_at, expires_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                h,
                query,
                provider,
                json.dumps(results),
                json.dumps(extra or {}),
                now.isoformat(),
                expires.isoformat(),
            ),
        )
        await self._db.commit()

    async def invalidate(self, url: str) -> bool:
        """Remove a specific URL from cache. Returns True if found."""
        h = url_hash(url)
        cursor = await self._db.execute("DELETE FROM scout_cache WHERE url_hash = ?", (h,))
        await self._db.commit()
        return cursor.rowcount > 0

    async def prune(self) -> int:
        """Delete all expired entries. Returns count pruned."""
        now = datetime.now(timezone.utc).isoformat()
        c1 = await self._db.execute("DELETE FROM scout_cache WHERE expires_at <= ?", (now,))
        c2 = await self._db.execute("DELETE FROM search_cache WHERE expires_at <= ?", (now,))
        await self._db.commit()
        return c1.rowcount + c2.rowcount

    async def stats(self) -> dict:
        """Return cache statistics."""
        counts: dict[str, int] = {}
        async with self._db.execute(
            "SELECT content_type, COUNT(*) as cnt FROM scout_cache GROUP BY content_type"
        ) as cursor:
            async for row in cursor:
                counts[row["content_type"]] = row["cnt"]

        async with self._db.execute("SELECT COUNT(*) as cnt FROM search_cache") as cursor:
            row = await cursor.fetchone()
            counts["search"] = row["cnt"] if row else 0

        now = datetime.now(timezone.utc).isoformat()
        async with self._db.execute(
            "SELECT COUNT(*) as cnt FROM scout_cache WHERE expires_at <= ?", (now,)
        ) as cursor:
            row = await cursor.fetchone()
            expired = row["cnt"] if row else 0

        return {
            "total_entries": sum(counts.values()),
            "by_type": counts,
            "expired": expired,
        }

    async def close(self) -> None:
        await self._db.close()
