#!/usr/bin/env python3
"""RayVault Cache Prune — delete unused ASIN cache entries.

Removes ASIN directories from the truth cache library that haven't
been used (served to a run) within a configurable window.

Uses last_used_utc from cache_info.json. Falls back to last_fetched_utc
or images_fetched_at_utc if last_used_utc is missing.

Usage:
    python3 -m rayvault.cache_prune --root state/library/products
    python3 -m rayvault.cache_prune --root state/library/products --apply
    python3 -m rayvault.cache_prune --max-unused-days 60

Exit codes:
    0: success (including dry-run)
    1: runtime error
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from rayvault.io import read_json, utc_now_iso


def _parse_utc(iso_str: str) -> Optional[float]:
    try:
        return datetime.fromisoformat(
            iso_str.replace("Z", "+00:00")
        ).timestamp()
    except Exception:
        return None


def _last_activity_ts(info: Dict[str, Any]) -> Optional[float]:
    """Get the most recent activity timestamp from cache_info."""
    for key in ("last_used_utc", "images_fetched_at_utc", "meta_fetched_at_utc"):
        val = info.get(key)
        if val:
            ts = _parse_utc(val)
            if ts:
                return ts
    return None


def prune(
    root: Path,
    max_unused_days: int = 30,
    apply: bool = False,
) -> Dict[str, Any]:
    """Prune unused ASIN cache directories.

    Args:
        root: Product cache root (e.g., state/library/products)
        max_unused_days: Delete entries unused for longer than this
        apply: Actually delete (False = dry-run)

    Returns:
        Summary dict with deleted ASINs and stats
    """
    if not root.is_dir():
        return {
            "at_utc": utc_now_iso(),
            "apply": apply,
            "error": "root_not_found",
            "deleted": [],
            "kept_count": 0,
        }

    cutoff_ts = time.time() - (max_unused_days * 86400)
    deleted: List[str] = []
    kept: List[str] = []
    skipped: List[str] = []
    bytes_freed = 0

    for asin_dir in sorted(root.iterdir()):
        if not asin_dir.is_dir() or asin_dir.name.startswith("."):
            continue

        info_path = asin_dir / "cache_info.json"
        if not info_path.exists():
            skipped.append(asin_dir.name)
            continue

        try:
            info = read_json(info_path)
        except Exception:
            skipped.append(asin_dir.name)
            continue

        # Don't prune broken entries (may need investigation)
        if info.get("status") == "BROKEN":
            kept.append(asin_dir.name)
            continue

        last_ts = _last_activity_ts(info)
        if last_ts is None:
            skipped.append(asin_dir.name)
            continue

        if last_ts < cutoff_ts:
            # Calculate size before deletion
            dir_bytes = 0
            for f in asin_dir.rglob("*"):
                if f.is_file():
                    try:
                        dir_bytes += f.stat().st_size
                    except OSError:
                        pass
            bytes_freed += dir_bytes

            if apply:
                shutil.rmtree(asin_dir, ignore_errors=True)
            deleted.append(asin_dir.name)
        else:
            kept.append(asin_dir.name)

    return {
        "at_utc": utc_now_iso(),
        "apply": apply,
        "max_unused_days": max_unused_days,
        "deleted": deleted,
        "deleted_count": len(deleted),
        "kept_count": len(kept),
        "skipped_count": len(skipped),
        "bytes_freed_est": bytes_freed,
    }


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(
        description="RayVault Cache Prune — delete unused ASIN cache entries",
    )
    ap.add_argument(
        "--root",
        default="state/library/products",
        help="Product cache root directory",
    )
    ap.add_argument("--max-unused-days", type=int, default=30)
    ap.add_argument("--apply", action="store_true", help="Actually delete (default: dry-run)")
    args = ap.parse_args(argv)

    root = Path(args.root).expanduser().resolve()
    result = prune(root, max_unused_days=args.max_unused_days, apply=args.apply)

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(
        f"cache_prune [{mode}]: deleted={result['deleted_count']} "
        f"kept={result['kept_count']} skipped={result['skipped_count']} "
        f"bytes_freed={result['bytes_freed_est']}"
    )
    if result["deleted"]:
        for asin in result["deleted"][:20]:
            print(f"  - {asin}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
