"""Evidence cache — skips re-extraction when page content hasn't changed.

Wraps FetchCache with an evidence layer. On fetch:
1. Check if URL is cached and content hash matches prior fetch
2. If match → return prior extracted evidence without re-running extraction
3. If miss or changed → caller extracts, then stores evidence here

This avoids expensive LLM/regex extraction when a review page hasn't been updated.

Stdlib only.

Usage:
    from lib.evidence_cache import EvidenceCache

    ecache = EvidenceCache()

    # Check before extraction
    prior = ecache.get_evidence(url, current_text)
    if prior is not None:
        print("Reusing prior evidence — page unchanged")
        products = prior
    else:
        products = extract_products(text)
        ecache.put_evidence(url, text, products)
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _content_hash(text: str) -> str:
    """SHA-256 of text (first 16 hex chars)."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _url_key(url: str) -> str:
    """SHA-256 of URL (first 16 hex chars)."""
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


class EvidenceCache:
    """Disk-backed evidence cache keyed by URL + content hash.

    Directory layout:
        <cache_dir>/
            index.json                  # {url_key: metadata}
            evidence/
                <url_key>.json          # extracted evidence data
    """

    def __init__(
        self,
        cache_dir: str | Path | None = None,
        ttl_hours: float = 48.0,
    ):
        if cache_dir is None:
            repo_root = Path(__file__).resolve().parent.parent.parent
            self._dir = repo_root / ".cache" / "evidence"
        else:
            self._dir = Path(cache_dir)

        self._evidence_dir = self._dir / "evidence"
        self._index_path = self._dir / "index.json"
        self._ttl_hours = ttl_hours

        self._dir.mkdir(parents=True, exist_ok=True)
        self._evidence_dir.mkdir(parents=True, exist_ok=True)

        self._index: dict[str, dict] = self._load_index()

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

    def get_evidence(self, url: str, current_text: str) -> Any | None:
        """Return cached evidence if content hash matches, else None.

        Args:
            url: The page URL.
            current_text: The freshly fetched page text (to compare hash).

        Returns:
            The stored evidence data (list/dict), or None if miss/changed/expired.
        """
        key = _url_key(url)
        entry = self._index.get(key)
        if entry is None:
            return None

        # Check TTL
        cached_at = entry.get("cached_at", "")
        if cached_at:
            try:
                ts = datetime.fromisoformat(cached_at).timestamp()
                import time
                if time.time() - ts > self._ttl_hours * 3600:
                    return None  # expired
            except (ValueError, OSError):
                return None

        # Check content hash
        current_hash = _content_hash(current_text)
        if entry.get("content_hash") != current_hash:
            return None  # page changed — need re-extraction

        # Load evidence file
        evidence_path = self._evidence_dir / f"{key}.json"
        if not evidence_path.exists():
            return None

        try:
            return json.loads(evidence_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    def put_evidence(
        self,
        url: str,
        page_text: str,
        evidence: Any,
        *,
        source_name: str = "",
        extra: dict | None = None,
    ) -> None:
        """Store extracted evidence for a URL + content hash.

        Args:
            url: The page URL.
            page_text: The fetched text (used to compute content hash).
            evidence: The extracted data (must be JSON-serializable).
            source_name: Optional label (e.g. "Wirecutter").
            extra: Optional metadata dict merged into the index entry.
        """
        key = _url_key(url)
        now = datetime.now(timezone.utc).isoformat()

        # Write evidence file
        evidence_path = self._evidence_dir / f"{key}.json"
        evidence_path.write_text(
            json.dumps(evidence, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )

        entry = {
            "url": url,
            "content_hash": _content_hash(page_text),
            "content_length": len(page_text),
            "source_name": source_name,
            "cached_at": now,
            "evidence_file": f"evidence/{key}.json",
            "evidence_count": len(evidence) if isinstance(evidence, list) else 1,
        }
        if extra:
            entry.update(extra)

        self._index[key] = entry
        self._save_index()

    def has_changed(self, url: str, current_text: str) -> bool:
        """Check if page content has changed since evidence was cached."""
        key = _url_key(url)
        entry = self._index.get(key)
        if entry is None:
            return True
        return entry.get("content_hash") != _content_hash(current_text)

    def invalidate(self, url: str) -> bool:
        """Remove evidence for a URL."""
        key = _url_key(url)
        if key not in self._index:
            return False
        entry = self._index.pop(key)
        evidence_path = self._evidence_dir / f"{key}.json"
        if evidence_path.exists():
            evidence_path.unlink()
        self._save_index()
        return True

    def stats(self) -> dict:
        """Return cache statistics."""
        return {
            "total_entries": len(self._index),
            "cache_dir": str(self._dir),
            "ttl_hours": self._ttl_hours,
            "sources": list({
                e.get("source_name", "") for e in self._index.values()
                if e.get("source_name")
            }),
        }

    def __len__(self) -> int:
        return len(self._index)

    def __contains__(self, url: str) -> bool:
        key = _url_key(url)
        return key in self._index
