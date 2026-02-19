"""Standalone Dzine image generation via assets_manifest.json.

Bridges the gap between prompt planning and actual image creation.
Reads an assets_manifest.json (or builds one from products.json),
generates each pending image via the existing Dzine browser automation
in tools/lib/dzine_browser.py, and updates statuses in the manifest.

Usage:
    # From manifest (after generate-assets built prompts):
    python3 tools/dzine_browser.py --video-id V001

    # Rebuild manifest from products.json + generate:
    python3 tools/dzine_browser.py --video-id V001 --rebuild

    # Dry run (show what would be generated):
    python3 tools/dzine_browser.py --video-id V001 --dry-run

Stdlib + Playwright (lazy import via lib/dzine_browser).
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

# Ensure repo root is on sys.path
_repo = Path(__file__).resolve().parent.parent
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))

from tools.lib.common import now_iso, project_root
from tools.lib.video_paths import VideoPaths

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MIN_ASSET_SIZE = 80 * 1024  # 80 KB minimum for valid images


# ---------------------------------------------------------------------------
# Manifest I/O
# ---------------------------------------------------------------------------


def _manifest_path(video_id: str) -> Path:
    """Return the canonical assets_manifest.json path for a video."""
    return VideoPaths(video_id).assets_dzine / "assets_manifest.json"


def load_manifest(path: Path) -> dict:
    """Load assets_manifest.json. Returns empty dict if missing."""
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_manifest(manifest: dict, path: Path) -> None:
    """Atomic write of assets_manifest.json."""
    import os
    import tempfile

    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, str(path))
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def build_manifest(video_id: str) -> dict:
    """Build assets_manifest.json from products.json + dzine_schema.

    Creates entries for thumbnail + per-product variants with prompts
    pre-populated. All statuses start as "pending".
    """
    from tools.lib.amazon_research import load_products_json
    from tools.lib.dzine_schema import (
        DzineRequest, build_prompts, detect_category, variants_for_rank,
    )

    paths = VideoPaths(video_id)
    if not paths.products_json.is_file():
        raise FileNotFoundError(f"products.json not found: {paths.products_json}")

    products = load_products_json(paths.products_json)
    niche = ""
    if paths.niche_txt.is_file():
        niche = paths.niche_txt.read_text(encoding="utf-8").strip()
    category = detect_category(niche) if niche else "default"

    entries: list[dict] = []

    # Thumbnail
    top_name = products[0].name if products else "Top 5 Products"
    thumb_req = DzineRequest(
        asset_type="thumbnail",
        product_name=top_name,
        key_message="Top 5",
    )
    thumb_req = build_prompts(thumb_req)
    entries.append({
        "label": "thumbnail",
        "asset_type": "thumbnail",
        "rank": 0,
        "variant": "thumbnail",
        "product_name": top_name,
        "prompt": thumb_req.prompt,
        "negative_prompt": thumb_req.negative_prompt,
        "output_path": str(paths.thumbnail_path()),
        "status": "pending",
        "image_url": "",
        "error": "",
    })

    # Per-product variants
    for p in sorted(products, key=lambda x: x.rank):
        variants = variants_for_rank(p.rank)
        ref_path = paths.amazon_ref_image(p.rank)
        ref_str = str(ref_path) if ref_path.is_file() and ref_path.stat().st_size > 10 * 1024 else ""

        for variant in variants:
            req = DzineRequest(
                asset_type="product",
                product_name=p.name,
                image_variant=variant,
                niche_category=category,
                reference_image=ref_str or None,
            )
            req = build_prompts(req)
            dest = paths.product_image_path(p.rank, variant)

            entries.append({
                "label": f"{p.rank:02d}_{variant}",
                "asset_type": "product",
                "rank": p.rank,
                "variant": variant,
                "product_name": p.name,
                "prompt": req.prompt,
                "negative_prompt": req.negative_prompt,
                "reference_image": ref_str,
                "output_path": str(dest),
                "status": "pending",
                "image_url": "",
                "error": "",
            })

    manifest = {
        "video_id": video_id,
        "niche": niche,
        "category": category,
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "entries": entries,
    }
    return manifest


# ---------------------------------------------------------------------------
# Generation orchestrator
# ---------------------------------------------------------------------------


def generate_all_assets(
    video_id: str,
    *,
    rebuild: bool = False,
    dry_run: bool = False,
) -> dict:
    """Generate all pending Dzine images for a video.

    Reads (or builds) assets_manifest.json, generates each pending entry
    via the existing Dzine browser automation, and updates statuses.

    Args:
        video_id: Video identifier
        rebuild: If True, rebuild manifest from products.json even if it exists
        dry_run: If True, show what would be generated without doing it

    Returns summary dict with generated/failed/skipped counts.
    """
    from tools.lib.dzine_schema import DzineRequest, build_prompts
    from tools.lib.dzine_browser import generate_image, close_session

    paths = VideoPaths(video_id)
    paths.ensure_dirs()
    mpath = _manifest_path(video_id)

    # Build or load manifest
    if rebuild or not mpath.is_file():
        print(f"[dzine] Building assets manifest from products.json...", file=sys.stderr)
        manifest = build_manifest(video_id)
        save_manifest(manifest, mpath)
        print(f"[dzine] Manifest: {len(manifest['entries'])} entries", file=sys.stderr)
    else:
        manifest = load_manifest(mpath)
        print(f"[dzine] Loaded manifest: {len(manifest.get('entries', []))} entries",
              file=sys.stderr)

    entries = manifest.get("entries", [])

    # Determine what needs generation
    pending = []
    done = []
    for entry in entries:
        dest = Path(entry["output_path"])
        if entry["status"] == "done" and dest.is_file() and dest.stat().st_size >= MIN_ASSET_SIZE:
            done.append(entry)
        else:
            # Reset to pending if file is missing even though status says done
            entry["status"] = "pending"
            pending.append(entry)

    print(f"[dzine] {len(done)} done, {len(pending)} pending", file=sys.stderr)

    if dry_run:
        for entry in pending:
            print(f"  [ ] {entry['label']}: {entry['product_name'][:40]}")
        for entry in done:
            print(f"  [x] {entry['label']}: {entry['product_name'][:40]}")
        return {"generated": 0, "failed": 0, "skipped": len(done), "total": len(entries)}

    if not pending:
        print("[dzine] All assets already generated.", file=sys.stderr)
        return {"generated": 0, "failed": 0, "skipped": len(done), "total": len(entries)}

    generated = 0
    failed = 0

    try:
        for i, entry in enumerate(pending):
            label = entry["label"]
            dest = Path(entry["output_path"])
            dest.parent.mkdir(parents=True, exist_ok=True)

            print(f"\n[dzine] [{i+1}/{len(pending)}] Generating {label}: "
                  f"{entry['product_name'][:40]}...", file=sys.stderr)

            # Build DzineRequest from manifest entry
            req = DzineRequest(
                asset_type=entry.get("asset_type", "product"),
                product_name=entry.get("product_name", ""),
                image_variant=entry.get("variant", ""),
                reference_image=entry.get("reference_image") or None,
                prompt=entry.get("prompt", ""),
                negative_prompt=entry.get("negative_prompt", ""),
            )

            # Ensure prompts are populated
            if not req.prompt:
                req = build_prompts(req)

            result = generate_image(req, output_path=dest)

            # Retry once on failure
            if not result.success:
                print(f"[dzine] Retry {label}...", file=sys.stderr)
                result = generate_image(req, output_path=dest)

            if result.success and dest.is_file() and dest.stat().st_size >= MIN_ASSET_SIZE:
                size_kb = dest.stat().st_size // 1024
                entry["status"] = "done"
                entry["image_url"] = result.image_url
                entry["error"] = ""
                generated += 1
                print(f"[dzine] OK: {dest.name} ({size_kb} KB, {result.duration_s:.0f}s)",
                      file=sys.stderr)
            else:
                entry["status"] = "failed"
                entry["error"] = result.error or "Unknown error"
                failed += 1
                print(f"[dzine] FAILED: {label} — {result.error}", file=sys.stderr)

                # Abort on login issues
                if "login" in (result.error or "").lower():
                    print("[dzine] Login required — aborting batch.", file=sys.stderr)
                    break

            # Save manifest after each image (crash-safe)
            manifest["updated_at"] = now_iso()
            save_manifest(manifest, mpath)

            # Brief pause between generations
            if i < len(pending) - 1:
                time.sleep(2)

    finally:
        try:
            close_session()
        except Exception:
            pass

    print(f"\n[dzine] Done: {generated} generated, {failed} failed, "
          f"{len(done)} already done", file=sys.stderr)

    return {
        "generated": generated,
        "failed": failed,
        "skipped": len(done),
        "total": len(entries),
    }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Generate Dzine images from assets_manifest.json",
    )
    parser.add_argument("--video-id", required=True, help="Video identifier")
    parser.add_argument("--rebuild", action="store_true",
                        help="Rebuild manifest from products.json")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be generated without doing it")
    parser.add_argument("--manifest", default="",
                        help="Override manifest path (default: auto from video-id)")
    args = parser.parse_args()

    # If custom manifest path, copy it into the expected location
    if args.manifest:
        import shutil
        src = Path(args.manifest)
        if not src.is_file():
            print(f"Manifest not found: {src}", file=sys.stderr)
            return 1
        dest = _manifest_path(args.video_id)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(src), str(dest))
        print(f"[dzine] Copied manifest to: {dest}", file=sys.stderr)

    result = generate_all_assets(
        video_id=args.video_id,
        rebuild=args.rebuild,
        dry_run=args.dry_run,
    )

    if result["failed"] > 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
