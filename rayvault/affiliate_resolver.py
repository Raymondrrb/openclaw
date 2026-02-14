#!/usr/bin/env python3
"""RayVault Affiliate Resolver — ASIN to short link mapping.

Reads a static affiliates.json and resolves ASINs to short links
with full provenance tracking. Links are auditable assets, not marketing.

Golden rule: NEVER invent or generate short links.
Only serve what's in the mapping file. Missing = None.

Layout:
    state/library/affiliates.json
    {
      "version": "1",
      "updated_at_utc": "2026-02-14T00:00:00Z",
      "default": {"tag": "rayviews-20", "country": "US"},
      "items": {
        "B0XXXXXXX1": {
          "short_link": "https://amzn.to/xxxx",
          "source": "manual",
          "last_verified_utc": "2026-02-14T00:00:00Z"
        }
      }
    }

Usage:
    from rayvault.affiliate_resolver import AffiliateResolver
    aff = AffiliateResolver(Path("state/library/affiliates.json"))
    info = aff.resolve("B0XXXXXXX1")  # or None
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha1_text(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()


class AffiliateResolver:
    """Resolve ASIN → affiliate short link from a static mapping file.

    Thread-safe reads (immutable after load). Call reload() to refresh.
    """

    def __init__(self, affiliates_path: Path):
        self.path = Path(affiliates_path)
        self.data: Dict[str, Any] = {"version": "0", "items": {}}
        self.file_hash: Optional[str] = None
        self.loaded_at_utc: Optional[str] = None
        self.reload()

    def reload(self) -> None:
        """Load or reload the affiliates mapping file."""
        if not self.path.exists():
            self.data = {"version": "0", "items": {}}
            self.file_hash = None
            self.loaded_at_utc = _utc_now_iso()
            return
        raw = self.path.read_text(encoding="utf-8")
        self.data = json.loads(raw)
        self.file_hash = _sha1_text(raw)
        self.loaded_at_utc = _utc_now_iso()

    def resolve(self, asin: str) -> Optional[Dict[str, Any]]:
        """Resolve an ASIN to affiliate link info.

        Returns None if ASIN not in mapping or link invalid.
        Returns dict with short_link, source, provenance on success.
        """
        asin = (asin or "").strip().upper()
        if not asin:
            return None
        items = self.data.get("items") or {}
        item = items.get(asin)
        if not item:
            return None
        link = item.get("short_link", "")
        if not link or not link.startswith("http"):
            return None
        return {
            "asin": asin,
            "short_link": link,
            "source": item.get("source", "unknown"),
            "last_verified_utc": item.get("last_verified_utc"),
            "affiliates_file_hash": self.file_hash,
            "resolver_loaded_at_utc": self.loaded_at_utc,
        }

    def resolve_batch(self, asins: List[str]) -> Dict[str, Optional[Dict[str, Any]]]:
        """Resolve multiple ASINs at once."""
        return {asin: self.resolve(asin) for asin in asins}

    def stats(self) -> Dict[str, Any]:
        """Return resolver stats for telemetry."""
        items = self.data.get("items") or {}
        return {
            "file_exists": self.path.exists(),
            "file_hash": self.file_hash,
            "loaded_at_utc": self.loaded_at_utc,
            "total_mappings": len(items),
            "version": self.data.get("version", "0"),
        }
