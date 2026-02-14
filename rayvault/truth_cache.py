#!/usr/bin/env python3
"""RayVault Truth Cache — ASIN-keyed product asset cache.

Caches Amazon product metadata and images in a local library folder,
reducing repeated downloads and Amazon 403/429 errors. Assets are
keyed by ASIN with TTL-based freshness checks.

Layout:
    state/library/products/{asin}/
        cache_info.json          (timestamps, provenance, disk usage, status)
        product_metadata.json    (title, bullets, price, etc.)
        source_images/
            01_main.jpg|png|webp
            02_alt.jpg ...
        hashes.json              (sha1 per image, sha256 for metadata)

Cache status:
    VALID    — all data present and within TTL
    EXPIRED  — data present but beyond TTL (usable as stale fallback)
    BROKEN   — corrupted or manually flagged (skip, re-download)

Usage:
    from rayvault.truth_cache import TruthCache, CachePolicy
    cache = TruthCache(Path("state/library"))
    cache.materialize_to_run("B0TEST", run_product_dir)

Golden rule: cache is a deterministic copy of Amazon truth.
Never invent, interpolate, or generate cached product visuals.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_json(path: Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def atomic_write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def sha1_file(path: Path) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_json(obj: Any) -> str:
    """Deterministic SHA256 of a JSON-serializable object."""
    raw = json.dumps(obj, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return sha256_bytes(raw)


# Cache status constants
CACHE_VALID = "VALID"
CACHE_EXPIRED = "EXPIRED"
CACHE_BROKEN = "BROKEN"


def du_bytes(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_file():
        return path.stat().st_size
    total = 0
    for f in path.rglob("*"):
        if f.is_file():
            try:
                total += f.stat().st_size
            except OSError:
                pass
    return total


# ---------------------------------------------------------------------------
# Cache policy
# ---------------------------------------------------------------------------


@dataclass
class CachePolicy:
    ttl_meta_sec: int = 48 * 3600       # 48h for metadata
    ttl_images_sec: int = 21 * 24 * 3600  # 21 days for images
    max_gallery: int = 6
    copy_mode: str = "copy"  # "copy" or "symlink"
    survival_allow_stale_hours: float = 168.0  # 7 days in survival mode
    ttl_jitter_sec: int = 2 * 3600  # +/- 2h jitter to avoid sync spikes


# ---------------------------------------------------------------------------
# Truth Cache
# ---------------------------------------------------------------------------


class TruthCache:
    """ASIN-keyed product asset cache."""

    def __init__(
        self,
        library_root: Path,
        policy: Optional[CachePolicy] = None,
    ):
        self.root = library_root.resolve()
        self.policy = policy or CachePolicy()

    def asin_dir(self, asin: str) -> Path:
        return self.root / "products" / asin

    def cache_info_path(self, asin: str) -> Path:
        return self.asin_dir(asin) / "cache_info.json"

    def meta_path(self, asin: str) -> Path:
        return self.asin_dir(asin) / "product_metadata.json"

    def hashes_path(self, asin: str) -> Path:
        return self.asin_dir(asin) / "hashes.json"

    def images_dir(self, asin: str) -> Path:
        return self.asin_dir(asin) / "source_images"

    # --- Freshness ---

    def _is_fresh(self, cache_info: Dict[str, Any], key: str, ttl: int) -> bool:
        ts = cache_info.get(key)
        if not ts:
            return False
        try:
            t = datetime.fromisoformat(
                ts.replace("Z", "+00:00")
            ).timestamp()
        except Exception:
            return False
        return (time.time() - t) <= ttl

    def needs_refresh(self, asin: str) -> Dict[str, Any]:
        """Check if cached data for an ASIN needs refreshing."""
        cached = self.get_cached(asin)
        info = cached.get("cache_info", {})

        # Broken cache always needs full refresh
        if info.get("status") == CACHE_BROKEN:
            return {
                "has_meta": False,
                "has_images": False,
                "meta_fresh": False,
                "images_fresh": False,
                "refresh_meta": True,
                "refresh_images": True,
                "status": CACHE_BROKEN,
            }

        meta_fresh = self._is_fresh(
            info, "meta_fetched_at_utc", self.policy.ttl_meta_sec
        )
        imgs_fresh = self._is_fresh(
            info, "images_fetched_at_utc", self.policy.ttl_images_sec
        )

        # Derive status
        has_meta = bool(cached.get("meta"))
        has_images = bool(cached.get("images"))
        if has_meta and meta_fresh and has_images and imgs_fresh:
            status = CACHE_VALID
        elif has_meta or has_images:
            status = CACHE_EXPIRED
        else:
            status = CACHE_EXPIRED  # empty = treat as expired

        return {
            "has_meta": has_meta,
            "has_images": has_images,
            "meta_fresh": meta_fresh,
            "images_fresh": imgs_fresh,
            "refresh_meta": not meta_fresh,
            "refresh_images": not imgs_fresh,
            "status": status,
        }

    # --- Read ---

    def get_cached(self, asin: str) -> Dict[str, Any]:
        """Get cached data for an ASIN. Returns empty dict on miss.

        Verifies metadata SHA256 integrity if stored. On mismatch,
        marks cache as broken and excludes meta from result.
        """
        d = self.asin_dir(asin)
        if not d.exists():
            return {}
        out: Dict[str, Any] = {}

        info_p = self.cache_info_path(asin)
        info = read_json(info_p) if info_p.exists() else {}
        out["cache_info"] = info

        # Skip reading if broken
        if info.get("status") == CACHE_BROKEN:
            return out

        meta_p = self.meta_path(asin)
        if meta_p.exists():
            try:
                meta = read_json(meta_p)
                # Verify integrity if hash is stored
                expected = info.get("meta_sha256")
                if expected:
                    actual = sha256_json(meta)
                    if actual != expected:
                        self.mark_cache_broken(
                            asin, f"meta_sha256_mismatch: expected {expected[:12]}… got {actual[:12]}…"
                        )
                        out["cache_info"] = read_json(self.cache_info_path(asin))
                        return out
                out["meta"] = meta
            except Exception:
                pass

        imgs_d = self.images_dir(asin)
        if imgs_d.exists():
            out["images"] = sorted(
                [p for p in imgs_d.iterdir() if p.is_file()]
            )
        return out

    def has_main_image(self, asin: str) -> bool:
        """Check if 01_main.* exists in cache."""
        imgs = self.images_dir(asin)
        if not imgs.is_dir():
            return False
        return any(
            f.name.startswith("01_main") for f in imgs.iterdir() if f.is_file()
        )

    # --- Integrity ---

    def mark_cache_broken(self, asin: str, reason: str) -> None:
        """Flag an ASIN's cache as broken without deleting files.

        Broken entries are skipped by needs_refresh/get_cached
        until overwritten by a fresh put_from_fetch.
        """
        info: Dict[str, Any] = {}
        if self.cache_info_path(asin).exists():
            try:
                info = read_json(self.cache_info_path(asin))
            except Exception:
                pass
        info["status"] = CACHE_BROKEN
        info["broken_reason"] = reason
        info["broken_at_utc"] = utc_now_iso()
        atomic_write_json(self.cache_info_path(asin), info)

    def verify_integrity(self, asin: str) -> Dict[str, Any]:
        """Check integrity of cached data for an ASIN.

        Returns {"ok": bool, "issues": [...]}
        """
        issues: List[str] = []
        d = self.asin_dir(asin)
        if not d.exists():
            return {"ok": False, "issues": ["asin_dir_missing"]}

        info_p = self.cache_info_path(asin)
        if not info_p.exists():
            issues.append("cache_info_missing")
            return {"ok": False, "issues": issues}

        try:
            info = read_json(info_p)
        except Exception:
            issues.append("cache_info_corrupt")
            return {"ok": False, "issues": issues}

        if info.get("status") == CACHE_BROKEN:
            issues.append(f"marked_broken: {info.get('broken_reason', 'unknown')}")
            return {"ok": False, "issues": issues}

        # Check metadata integrity
        meta_p = self.meta_path(asin)
        if meta_p.exists():
            try:
                meta = read_json(meta_p)
                expected = info.get("meta_sha256")
                if expected:
                    actual = sha256_json(meta)
                    if actual != expected:
                        issues.append("meta_sha256_mismatch")
            except Exception:
                issues.append("meta_corrupt")
        else:
            issues.append("meta_missing")

        # Check images exist
        imgs_d = self.images_dir(asin)
        if imgs_d.is_dir():
            img_files = [f for f in imgs_d.iterdir() if f.is_file()]
            if not img_files:
                issues.append("images_empty")
        else:
            issues.append("images_dir_missing")

        return {"ok": len(issues) == 0, "issues": issues}

    # --- Write ---

    def put_from_fetch(
        self,
        asin: str,
        meta: Optional[Dict[str, Any]],
        downloaded_images: List[Path],
        note: str = "fetch",
        http_status: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Store fetched assets into cache.

        Args:
            asin: Amazon ASIN
            meta: Product metadata dict (title, bullets, etc.)
            downloaded_images: List of paths to downloaded image files
            note: Provenance note
            http_status: Last HTTP status from Amazon

        Returns:
            {"ok": True/False, "stored_images": [...], "cache_dir": str}
        """
        d = self.asin_dir(asin)
        imgs_d = self.images_dir(asin)
        imgs_d.mkdir(parents=True, exist_ok=True)

        # Load existing hashes
        hashes: Dict[str, Any] = {}
        if self.hashes_path(asin).exists():
            try:
                hashes = read_json(self.hashes_path(asin))
            except Exception:
                pass
        images_hashes = hashes.get("images", {})

        # Store metadata
        if meta:
            atomic_write_json(self.meta_path(asin), meta)

        # Store images
        stored = []
        for p in downloaded_images:
            if not p.exists():
                continue
            dest = imgs_d / p.name
            if not dest.exists():
                shutil.copy2(str(p), str(dest))
            h = sha1_file(dest)
            images_hashes[dest.name] = {
                "sha1": h,
                "bytes": dest.stat().st_size,
            }
            stored.append(dest)

        # Update hashes
        hashes["images"] = images_hashes
        atomic_write_json(self.hashes_path(asin), hashes)

        # Update cache info
        info: Dict[str, Any] = {}
        if self.cache_info_path(asin).exists():
            try:
                info = read_json(self.cache_info_path(asin))
            except Exception:
                pass
        if meta:
            info["meta_fetched_at_utc"] = utc_now_iso()
            info["meta_sha256"] = sha256_json(meta)
        if stored:
            info["images_fetched_at_utc"] = utc_now_iso()
        info["note"] = note
        info["fetched_from"] = "amazon"
        info["status"] = CACHE_VALID
        # Clear any prior broken state
        info.pop("broken_reason", None)
        info.pop("broken_at_utc", None)
        if http_status is not None:
            info["http_status_last"] = http_status
        info["disk_bytes"] = du_bytes(d)
        atomic_write_json(self.cache_info_path(asin), info)

        return {
            "ok": True,
            "stored_images": [p.name for p in stored],
            "cache_dir": str(d),
        }

    # --- Materialize ---

    def materialize_to_run(
        self,
        asin: str,
        run_product_dir: Path,
        mode: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Copy or symlink cached assets into a run's product directory.

        Args:
            asin: Amazon ASIN
            run_product_dir: e.g., state/runs/RUN_X/products/p01/
            mode: "copy" or "symlink" (default from policy)

        Returns:
            {"ok": True/False, "code": str, "mode": str}
        """
        if mode is None:
            mode = self.policy.copy_mode

        cached = self.get_cached(asin)
        if not cached.get("images") and not cached.get("meta"):
            return {"ok": False, "code": "CACHE_MISS"}

        run_imgs = run_product_dir / "source_images"
        run_imgs.mkdir(parents=True, exist_ok=True)

        copied = 0
        if cached.get("images"):
            for img in cached["images"]:
                dest = run_imgs / img.name
                if dest.exists():
                    continue
                if mode == "symlink":
                    dest.symlink_to(img.resolve())
                else:
                    shutil.copy2(str(img), str(dest))
                copied += 1

        if cached.get("meta"):
            atomic_write_json(
                run_product_dir / "product_metadata.json",
                cached["meta"],
            )

        # Touch last_used_utc for cache pruning
        info_p = self.cache_info_path(asin)
        if info_p.exists():
            try:
                info = read_json(info_p)
                info["last_used_utc"] = utc_now_iso()
                atomic_write_json(info_p, info)
            except Exception:
                pass

        return {
            "ok": True,
            "code": "MATERIALIZED",
            "mode": mode,
            "images_copied": copied,
        }

    # --- B-roll library ---

    def approved_broll_path(self, asin: str) -> Path:
        return self.asin_dir(asin) / "approved_broll" / "approved.mp4"

    def has_approved_broll(self, asin: str) -> bool:
        return self.approved_broll_path(asin).exists()

    def promote_broll(self, asin: str, source_mp4: Path) -> bool:
        """Copy approved b-roll into library for reuse across runs.

        Args:
            asin: Amazon ASIN
            source_mp4: Path to approved.mp4 in the run

        Returns True if promoted successfully.
        """
        if not source_mp4.exists():
            return False
        dest = self.approved_broll_path(asin)
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(".tmp")
        shutil.copy2(str(source_mp4), str(tmp))
        os.replace(tmp, dest)
        return True

    # --- Survival mode ---

    def get_stale_if_allowed(self, asin: str) -> Dict[str, Any]:
        """Get cached data for survival mode (accept stale up to policy limit).

        Returns cached dict (same format as get_cached) or empty dict.
        """
        d = self.asin_dir(asin)
        if not d.exists():
            return {}

        info_p = self.cache_info_path(asin)
        if not info_p.exists():
            return {}
        try:
            info = read_json(info_p)
        except Exception:
            return {}

        if info.get("status") == CACHE_BROKEN:
            return {}

        # Check if within survival stale window
        fetched = info.get("images_fetched_at_utc") or info.get("meta_fetched_at_utc")
        if not fetched:
            return {}
        try:
            t = datetime.fromisoformat(fetched.replace("Z", "+00:00")).timestamp()
        except Exception:
            return {}
        age_hours = (time.time() - t) / 3600.0
        if age_hours > self.policy.survival_allow_stale_hours:
            return {}

        # Accept stale — read assets
        out: Dict[str, Any] = {"cache_info": info}
        meta_p = self.meta_path(asin)
        if meta_p.exists():
            try:
                out["meta"] = read_json(meta_p)
            except Exception:
                pass
        imgs_d = self.images_dir(asin)
        if imgs_d.exists():
            out["images"] = sorted(
                [p for p in imgs_d.iterdir() if p.is_file()]
            )
        return out

    def effective_ttl_images_sec(self) -> int:
        """TTL with jitter applied (call per-product for anti-pattern)."""
        import random
        jitter = self.policy.ttl_jitter_sec
        if jitter <= 0:
            return self.policy.ttl_images_sec
        return self.policy.ttl_images_sec + random.randint(-jitter, jitter)

    # --- Stats ---

    def stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        products_dir = self.root / "products"
        if not products_dir.exists():
            return {"total_asins": 0, "total_bytes": 0}
        asins = [
            d.name for d in products_dir.iterdir()
            if d.is_dir() and not d.name.startswith(".")
        ]
        total_bytes = du_bytes(products_dir)
        return {
            "total_asins": len(asins),
            "total_bytes": total_bytes,
            "total_mb": round(total_bytes / (1024 * 1024), 2),
        }
