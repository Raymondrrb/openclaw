"""Disk-backed fetch cache with TTL — avoids redundant HTTP requests and re-analysis.

Keyed by URL. Each cache entry stores:
- Content hash (SHA-256 of fetched text)
- FetchResult metadata (method, token_estimate, content_type, etc.)
- Full text content (in a separate .md file to keep the index small)
- Timestamp + TTL for expiration

When a URL is requested:
1. Check cache index for a non-expired entry
2. If hit → return cached FetchResult immediately (zero HTTP cost)
3. If miss or expired → fetch normally, store result, return it

Content-hash comparison allows detecting when a page has actually changed
even if the TTL hasn't expired (useful for forced refreshes).

Stdlib only — no external dependencies.

Usage:
    from lib.fetch_cache import FetchCache

    cache = FetchCache()                          # default: ~/.openclaw/cache/fetch/
    cache = FetchCache(ttl_hours=48)              # custom TTL
    cache = FetchCache(cache_dir="./my_cache")    # custom location

    # Check before fetching
    hit = cache.get("https://example.com/review")
    if hit:
        print(f"Cache hit! {hit.method}, age={hit.age_hours:.1f}h")
    else:
        result = fetch_markdown(url)
        cache.put(result)

    # Or use the integrated fetch (recommended)
    from lib.markdown_fetch import fetch_markdown
    result = fetch_markdown(url, cache=cache)     # auto cache check + store
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Cache entry
# ---------------------------------------------------------------------------

@dataclass
class CacheEntry:
    """A single cached fetch result."""
    url: str
    url_key: str                    # SHA-256 of URL (used as filename)
    content_hash: str               # SHA-256 of fetched text
    method: str                     # "markdown" | "html" | "browser"
    content_type: str
    token_estimate: int | None
    content_length: int
    fetched_at: str                 # ISO-8601
    cached_at: str                  # ISO-8601
    ttl_hours: float
    text_file: str                  # relative path to .md content file

    @property
    def expires_at(self) -> float:
        """Unix timestamp when this entry expires."""
        cached = datetime.fromisoformat(self.cached_at)
        return cached.timestamp() + (self.ttl_hours * 3600)

    @property
    def is_expired(self) -> bool:
        return time.time() > self.expires_at

    @property
    def age_hours(self) -> float:
        cached = datetime.fromisoformat(self.cached_at)
        return (time.time() - cached.timestamp()) / 3600


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _url_key(url: str) -> str:
    """Deterministic key for a URL (SHA-256 hex, first 16 chars)."""
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


def _content_hash(text: str) -> str:
    """SHA-256 of text content (first 16 chars for compactness)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# FetchCache
# ---------------------------------------------------------------------------

_DEFAULT_TTL_HOURS = 24.0
_DEFAULT_CACHE_DIR = None  # resolved at runtime


class FetchCache:
    """Disk-backed URL fetch cache with TTL expiration.

    Directory layout:
        <cache_dir>/
            index.json          # {url_key: CacheEntry metadata}
            content/
                <url_key>.md    # cached text content
    """

    def __init__(
        self,
        cache_dir: str | Path | None = None,
        ttl_hours: float = _DEFAULT_TTL_HOURS,
    ):
        if cache_dir is None:
            # Default: <repo_root>/.cache/fetch/
            repo_root = Path(__file__).resolve().parent.parent.parent
            self._dir = repo_root / ".cache" / "fetch"
        else:
            self._dir = Path(cache_dir)

        self._content_dir = self._dir / "content"
        self._index_path = self._dir / "index.json"
        self._ttl_hours = ttl_hours

        # Ensure dirs exist
        self._dir.mkdir(parents=True, exist_ok=True)
        self._content_dir.mkdir(parents=True, exist_ok=True)

        # Load index
        self._index: dict[str, dict] = self._load_index()

    # ── Index I/O ─────────────────────────────────────────────────────────

    def _load_index(self) -> dict[str, dict]:
        if self._index_path.exists():
            try:
                return json.loads(self._index_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                return {}
        return {}

    def _save_index(self) -> None:
        self._index_path.write_text(
            json.dumps(self._index, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    # ── Public API ────────────────────────────────────────────────────────

    def get(self, url: str) -> CacheEntry | None:
        """Look up a URL in cache. Returns CacheEntry or None if miss/expired."""
        key = _url_key(url)
        raw = self._index.get(key)
        if raw is None:
            return None

        entry = CacheEntry(**raw)

        if entry.is_expired:
            return None

        # Verify content file exists
        content_path = self._dir / entry.text_file
        if not content_path.exists():
            # Stale index entry — remove it
            del self._index[key]
            self._save_index()
            return None

        return entry

    def get_text(self, url: str) -> str | None:
        """Convenience: return cached text content, or None on miss."""
        entry = self.get(url)
        if entry is None:
            return None
        content_path = self._dir / entry.text_file
        return content_path.read_text(encoding="utf-8")

    def put(
        self,
        url: str,
        text: str,
        *,
        method: str = "",
        content_type: str = "",
        token_estimate: int | None = None,
        fetched_at: str = "",
        ttl_hours: float | None = None,
    ) -> CacheEntry:
        """Store a fetch result in cache. Returns the CacheEntry."""
        key = _url_key(url)
        now = datetime.now(timezone.utc).isoformat()
        ttl = ttl_hours if ttl_hours is not None else self._ttl_hours

        # Write content file
        text_file = f"content/{key}.md"
        content_path = self._dir / text_file
        content_path.write_text(text, encoding="utf-8")

        entry_dict = {
            "url": url,
            "url_key": key,
            "content_hash": _content_hash(text),
            "method": method,
            "content_type": content_type,
            "token_estimate": token_estimate,
            "content_length": len(text),
            "fetched_at": fetched_at or now,
            "cached_at": now,
            "ttl_hours": ttl,
            "text_file": text_file,
        }

        self._index[key] = entry_dict
        self._save_index()

        return CacheEntry(**entry_dict)

    def put_result(self, result: Any, *, ttl_hours: float | None = None) -> CacheEntry:
        """Store a FetchResult object in cache. Convenience wrapper around put()."""
        return self.put(
            url=result.url,
            text=result.text,
            method=result.method,
            content_type=result.content_type,
            token_estimate=result.token_estimate,
            fetched_at=result.fetched_at,
            ttl_hours=ttl_hours,
        )

    def has_changed(self, url: str, new_text: str) -> bool:
        """Check if content has changed since last cache. True if changed or not cached."""
        entry = self.get(url)
        if entry is None:
            return True
        return entry.content_hash != _content_hash(new_text)

    def invalidate(self, url: str) -> bool:
        """Remove a URL from cache. Returns True if it was cached."""
        key = _url_key(url)
        if key not in self._index:
            return False
        # Remove content file
        entry = self._index[key]
        content_path = self._dir / entry.get("text_file", "")
        if content_path.exists():
            content_path.unlink()
        del self._index[key]
        self._save_index()
        return True

    def evict_expired(self) -> int:
        """Remove all expired entries. Returns count of entries evicted."""
        now = time.time()
        expired_keys = []
        for key, raw in self._index.items():
            try:
                entry = CacheEntry(**raw)
                if entry.is_expired:
                    expired_keys.append(key)
            except (TypeError, KeyError):
                expired_keys.append(key)

        for key in expired_keys:
            entry_raw = self._index.get(key, {})
            text_file = entry_raw.get("text_file", "")
            if text_file:
                content_path = self._dir / text_file
                if content_path.exists():
                    content_path.unlink()
            del self._index[key]

        if expired_keys:
            self._save_index()
        return len(expired_keys)

    def clear(self) -> int:
        """Remove all cache entries. Returns count removed."""
        count = len(self._index)
        for key, raw in self._index.items():
            text_file = raw.get("text_file", "")
            if text_file:
                content_path = self._dir / text_file
                if content_path.exists():
                    content_path.unlink()
        self._index.clear()
        self._save_index()
        return count

    def stats(self) -> dict:
        """Return cache statistics."""
        total = len(self._index)
        expired = sum(1 for raw in self._index.values()
                      if CacheEntry(**raw).is_expired)
        total_bytes = sum(
            (self._dir / raw.get("text_file", "")).stat().st_size
            for raw in self._index.values()
            if (self._dir / raw.get("text_file", "")).exists()
        )
        return {
            "total_entries": total,
            "active_entries": total - expired,
            "expired_entries": expired,
            "total_bytes": total_bytes,
            "cache_dir": str(self._dir),
            "default_ttl_hours": self._ttl_hours,
        }

    def __len__(self) -> int:
        return len(self._index)

    def __contains__(self, url: str) -> bool:
        return self.get(url) is not None
