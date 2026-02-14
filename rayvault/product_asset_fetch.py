#!/usr/bin/env python3
"""RayVault Product Asset Fetch — download and materialize product images.

Turns `state/runs/{run_id}/products/products.json` into a fully materialized
product asset bundle with source images, hashes, and QC placeholders.

Golden rule: never invent product visuals. Only cache Amazon truth.

Usage:
    python3 -m rayvault.product_asset_fetch --run-dir state/runs/RUN_2026_02_14_A
    python3 -m rayvault.product_asset_fetch --run-dir state/runs/RUN_2026_02_14_A --dry-run

Output per product rank N:
    products/p0N/
        product.json         (normalized product data)
        source_images/
            01_main.jpg      (best guess main image)
            02_alt.jpg ...   (alternate images)
            hashes.json      (sha1 per file)
        qc.json              (starts UNKNOWN)
        broll/               (empty, generated later)

Exit codes:
    0: success (all or partial downloads ok)
    1: runtime error
    2: validation error (missing run dir, products.json)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def read_json(path: Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def atomic_write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def sha1_file(path: Path) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def safe_ext_from_url(url: str, default: str = ".jpg") -> str:
    try:
        p = urlparse(url)
        ext = Path(p.path).suffix.lower()
        if ext in (".jpg", ".jpeg", ".png", ".webp"):
            return ".jpg" if ext == ".jpeg" else ext
        return default
    except Exception:
        return default


def http_get_bytes(
    url: str, timeout: int = 20, user_agent: str = "Mozilla/5.0"
) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": user_agent})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def download_with_retries(
    url: str,
    out_path: Path,
    retries: int = 3,
    backoff: float = 0.8,
) -> Tuple[bool, str]:
    last_err = ""
    for i in range(retries):
        try:
            data = http_get_bytes(url)
            if not data or len(data) < 2048:
                last_err = (
                    f"too_small_or_empty ({len(data) if data else 0} bytes)"
                )
                time.sleep(backoff * (i + 1))
                continue
            out_path.parent.mkdir(parents=True, exist_ok=True)
            with open(out_path, "wb") as f:
                f.write(data)
            return True, "ok"
        except urllib.error.HTTPError as e:
            last_err = f"http_error {e.code}"
            time.sleep(backoff * (i + 1) * 2.0)
        except Exception as e:
            last_err = f"err {type(e).__name__}"
            time.sleep(backoff * (i + 1))
    return False, last_err


# ---------------------------------------------------------------------------
# URL selection
# ---------------------------------------------------------------------------


def pick_urls(item: Dict[str, Any]) -> List[str]:
    """Prefer hires_image_urls, then image_urls. Dedupe."""
    hires = item.get("hires_image_urls") or []
    normal = item.get("image_urls") or []
    urls: List[str] = []
    for u in hires:
        if isinstance(u, str) and u.startswith("http"):
            urls.append(u)
    for u in normal:
        if isinstance(u, str) and u.startswith("http") and u not in urls:
            urls.append(u)
    return urls


# ---------------------------------------------------------------------------
# Manifest helpers
# ---------------------------------------------------------------------------


def load_manifest(run_dir: Path) -> Dict[str, Any]:
    mpath = run_dir / "00_manifest.json"
    if mpath.exists():
        return read_json(mpath)
    return {
        "run_id": run_dir.name,
        "status": "INIT",
        "assets": {},
        "metadata": {},
    }


def update_manifest_products(
    manifest: Dict[str, Any],
    products_summary: List[Dict[str, Any]],
    list_path: str,
) -> None:
    """Non-destructive merge of product data into manifest."""
    manifest.setdefault("products", {})
    manifest["products"]["count"] = len(products_summary)
    manifest["products"]["list_path"] = list_path
    manifest["products"].setdefault(
        "fidelity",
        {"result": "UNKNOWN", "fail_reason": None, "fallback_used": False},
    )
    manifest["products_summary"] = products_summary


# ---------------------------------------------------------------------------
# Core fetch
# ---------------------------------------------------------------------------


@dataclass
class FetchResult:
    ok: bool
    downloaded: int
    skipped: int
    errors: int
    notes: List[str] = field(default_factory=list)


def run_product_fetch(
    run_dir: Path,
    max_images_per_product: int = 6,
    dry_run: bool = False,
) -> FetchResult:
    """Fetch product images into run_dir/products/p0N/source_images/."""
    products_dir = run_dir / "products"
    products_json = products_dir / "products.json"

    if not products_json.exists():
        return FetchResult(False, 0, 0, 1, [f"missing {products_json}"])

    downloaded = skipped = errors = 0
    notes: List[str] = []

    data = read_json(products_json)
    items = data.get("items") or []
    if not isinstance(items, list) or not items:
        return FetchResult(False, 0, 0, 1, ["products.json has no items[]"])

    # Sort by rank
    def _rank(it: Dict[str, Any]) -> int:
        try:
            return int(it.get("rank", 999))
        except Exception:
            return 999

    items = sorted(items, key=_rank)

    products_summary: List[Dict[str, Any]] = []

    for it in items:
        rank = int(it.get("rank", 0) or 0)
        if rank <= 0:
            rank = len(products_summary) + 1

        asin = str(it.get("asin", "")).strip()
        title = str(it.get("title", "")).strip()
        if not asin or not title:
            errors += 1
            notes.append(f"rank {rank}: missing asin/title")
            continue

        pdir = products_dir / f"p{rank:02d}"
        src_dir = pdir / "source_images"
        broll_dir = pdir / "broll"
        src_dir.mkdir(parents=True, exist_ok=True)
        broll_dir.mkdir(parents=True, exist_ok=True)

        # Write product.json (normalized)
        if not dry_run:
            atomic_write_json(
                pdir / "product.json",
                {
                    "rank": rank,
                    "asin": asin,
                    "title": title,
                    "brand": it.get("brand"),
                    "category": it.get("category"),
                    "price_text": it.get("price_text"),
                    "affiliate_url": it.get("affiliate_url"),
                    "canonical_url": it.get("canonical_url"),
                    "image_urls": it.get("image_urls", []),
                    "hires_image_urls": it.get("hires_image_urls", []),
                    "claims_allowed": it.get("claims_allowed", []),
                    "claims_forbidden": it.get("claims_forbidden", []),
                },
            )

        # Fetch images
        urls = pick_urls(it)
        if not urls:
            errors += 1
            notes.append(f"rank {rank} asin {asin}: no image urls")
            products_summary.append(
                {
                    "rank": rank,
                    "asin": asin,
                    "title": title,
                    "fidelity": "UNKNOWN",
                    "broll": "NONE",
                }
            )
            continue

        hashes: Dict[str, str] = {}
        got_any = False
        for idx, url in enumerate(
            urls[:max_images_per_product], start=1
        ):
            ext = safe_ext_from_url(url)
            fname = f"{idx:02d}_{'main' if idx == 1 else 'alt'}{ext}"
            out_path = src_dir / fname

            if out_path.exists() and out_path.stat().st_size > 2048:
                skipped += 1
                hashes[fname] = sha1_file(out_path)
                got_any = True
                continue

            if dry_run:
                notes.append(f"DRY: would download {url} -> {out_path}")
                skipped += 1
                got_any = True
                continue

            ok, reason = download_with_retries(url, out_path)
            if ok:
                downloaded += 1
                got_any = True
                hashes[fname] = sha1_file(out_path)
            else:
                errors += 1
                notes.append(
                    f"rank {rank} {asin}: failed {url} ({reason})"
                )

        # Store hashes
        if not dry_run:
            atomic_write_json(src_dir / "hashes.json", hashes)

        # Initialize qc.json if missing
        qc_path = pdir / "qc.json"
        if not qc_path.exists() and not dry_run:
            atomic_write_json(
                qc_path,
                {
                    "asin": asin,
                    "product_fidelity_result": "UNKNOWN",
                    "method": "unreviewed",
                    "checked_images": ["source_images/01_main.*"],
                    "broll_method": "UNDECIDED",
                    "fail_reason": None,
                    "checked_at_utc": None,
                },
            )

        products_summary.append(
            {
                "rank": rank,
                "asin": asin,
                "title": title,
                "fidelity": "UNKNOWN" if got_any else "MISSING_IMAGES",
                "broll": "PENDING",
            }
        )

    # Update manifest (non-destructive)
    manifest = load_manifest(run_dir)
    update_manifest_products(
        manifest,
        products_summary=products_summary,
        list_path="products/products.json",
    )
    if not dry_run:
        atomic_write_json(run_dir / "00_manifest.json", manifest)

    result_ok = errors == 0 or downloaded > 0
    return FetchResult(result_ok, downloaded, skipped, errors, notes)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Fetch product images into run bundle.",
    )
    ap.add_argument("--run-dir", required=True, help="state/runs/{run_id}")
    ap.add_argument("--max-images-per-product", type=int, default=6)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    run_dir = Path(args.run_dir).expanduser().resolve()
    if not run_dir.exists():
        print(f"Run dir not found: {run_dir}", file=sys.stderr)
        return 2

    res = run_product_fetch(
        run_dir,
        max_images_per_product=args.max_images_per_product,
        dry_run=args.dry_run,
    )
    print(
        f"product_asset_fetch: ok={res.ok} downloaded={res.downloaded} "
        f"skipped={res.skipped} errors={res.errors}"
    )
    if res.notes:
        for n in res.notes[:10]:
            print(f"  - {n}")
    return 0 if res.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
