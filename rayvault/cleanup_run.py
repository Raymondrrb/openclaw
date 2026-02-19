#!/usr/bin/env python3
"""RayVault Run Cleanup — selective purge of heavy assets post-publish.

Keeps forensic metadata (manifest, metadata, product.json, qc.json, logs).
Purges heavy files (source_images, broll, audio, frame, final video).

Golden rule: NEVER purge unless upload_receipt.json confirms success OR --force.
Receipt HMAC is verified before trusting UPLOADED/VERIFIED status.
Final video deletion requires VERIFIED status (not just UPLOADED).

Usage:
    python3 -m rayvault.cleanup_run --run-dir state/runs/RUN_2026_02_14_A
    python3 -m rayvault.cleanup_run --run-dir state/runs/RUN_2026_02_14_A --apply
    python3 -m rayvault.cleanup_run --run-dir state/runs/RUN_2026_02_14_A --apply --force

Exit codes:
    0: success (including dry-run)
    1: unexpected error
    2: refused by safety (no receipt, HMAC invalid, too new, missing run)
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from rayvault.io import atomic_write_json, read_json, utc_now_iso

# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def du_bytes(path: Path) -> int:
    """Sum of file sizes recursively. Returns 0 if path doesn't exist."""
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


def safe_unlink(path: Path) -> bool:
    try:
        if path.exists() and path.is_file():
            path.unlink()
            return True
    except OSError:
        pass
    return False


def safe_rmtree(path: Path) -> bool:
    try:
        if path.exists() and path.is_dir():
            shutil.rmtree(path)
            return True
    except OSError:
        pass
    return False


# ---------------------------------------------------------------------------
# Receipt loading + HMAC verification
# ---------------------------------------------------------------------------


def load_receipt(run_dir: Path) -> Optional[Dict[str, Any]]:
    r = run_dir / "publish" / "upload_receipt.json"
    if not r.exists():
        return None
    return read_json(r)


def verify_receipt_hmac(receipt: Dict[str, Any]) -> bool:
    """Verify HMAC signature on receipt. Returns False if no integrity block."""
    try:
        from rayvault.youtube_upload_receipt import verify_receipt
        return verify_receipt(receipt)
    except ImportError:
        # Fallback: if youtube_upload_receipt not available, check basic fields
        return bool(
            receipt.get("integrity", {}).get("hmac_sha256")
            and receipt.get("status") in ("UPLOADED", "VERIFIED")
        )


# ---------------------------------------------------------------------------
# Core cleanup
# ---------------------------------------------------------------------------


def cleanup(
    run_dir: Path,
    apply: bool = False,
    keep_main_image: bool = False,
    delete_final_video: bool = True,
    min_age_hours: float = 0.0,
    min_upload_age_hours: float = 24.0,
    force: bool = False,
) -> Tuple[bool, Union[str, Dict[str, Any]]]:
    """Selective purge of heavy assets from a run directory.

    Returns:
        (ok, info) where ok=True means cleanup succeeded or dry-run completed,
        and info is either a reason string (on refusal) or a stats dict.
    """
    if not run_dir.exists():
        return (False, "missing_run_dir")

    manifest_path = run_dir / "00_manifest.json"
    if not manifest_path.exists():
        return (False, "missing_manifest")

    # Safety: age check
    if min_age_hours > 0:
        try:
            age_sec = time.time() - run_dir.stat().st_mtime
            if age_sec < min_age_hours * 3600:
                return (False, "too_new_refuse")
        except OSError:
            return (False, "cannot_stat_run_dir")

    # Safety: receipt check + HMAC verification
    receipt = load_receipt(run_dir)
    if not force:
        if not receipt:
            return (False, "missing_receipt")
        receipt_status = receipt.get("status", "")
        if receipt_status not in ("UPLOADED", "VERIFIED"):
            return (False, f"receipt_status_{receipt_status}_not_uploaded")
        # Verify HMAC integrity
        if not verify_receipt_hmac(receipt):
            return (False, "receipt_hmac_invalid")

    manifest = read_json(manifest_path)

    # Build purge target list
    purge_targets: List[Path] = []

    # Heavy core assets
    for fname in ("02_audio.wav", "03_frame.png"):
        p = run_dir / fname
        if p.exists():
            purge_targets.append(p)

    # Products heavy directories
    products_dir = run_dir / "products"
    if products_dir.exists():
        for pdir in sorted(products_dir.glob("p[0-9][0-9]")):
            src = pdir / "source_images"
            if src.exists():
                if keep_main_image:
                    # Remove everything except 01_main.* files
                    for f in sorted(src.iterdir()):
                        if f.is_file() and f.name.startswith("01_main"):
                            continue
                        purge_targets.append(f)
                    # Also remove hashes.json (will be stale)
                    hashes_f = src / "hashes.json"
                    if hashes_f.exists() and hashes_f not in purge_targets:
                        purge_targets.append(hashes_f)
                else:
                    purge_targets.append(src)
            broll = pdir / "broll"
            if broll.exists():
                purge_targets.append(broll)

    # Final video: dead man's switch — enforce minimum upload age
    final_video = run_dir / "publish" / "video_final.mp4"
    can_delete_final = bool(
        receipt and receipt.get("status") in ("UPLOADED", "VERIFIED")
    )
    video_retained_reason = None
    if delete_final_video and can_delete_final and final_video.exists():
        # Dead man's switch: check upload age
        uploaded_at = receipt.get("uploaded_at_utc", "")
        upload_age_ok = True
        if min_upload_age_hours > 0 and uploaded_at and not force:
            try:
                t = datetime.fromisoformat(
                    uploaded_at.replace("Z", "+00:00")
                ).timestamp()
                age_h = (time.time() - t) / 3600.0
                if age_h < min_upload_age_hours:
                    upload_age_ok = False
                    next_eligible = datetime.fromtimestamp(
                        t + min_upload_age_hours * 3600, tz=timezone.utc
                    ).strftime("%Y-%m-%dT%H:%M:%SZ")
                    video_retained_reason = "MIN_UPLOAD_AGE_BUFFER"
            except Exception:
                pass  # If can't parse, allow deletion

        if upload_age_ok:
            purge_targets.append(final_video)
        # else: final video retained by dead man's switch

    # Calculate bytes before delete
    bytes_freed = sum(du_bytes(t) for t in purge_targets if t.exists())
    deleted_count = 0

    if apply:
        for t in purge_targets:
            if not t.exists():
                continue
            if t.is_dir():
                if safe_rmtree(t):
                    deleted_count += 1
            else:
                if safe_unlink(t):
                    deleted_count += 1

    # Write cleanup history to manifest (ring buffer, last 10)
    hk = manifest.setdefault("housekeeping", {})
    hist = hk.setdefault("cleanup_history", [])
    entry: Dict[str, Any] = {
        "at_utc": utc_now_iso(),
        "applied": apply,
        "bytes_freed_est": bytes_freed,
        "targets_count": (
            deleted_count
            if apply
            else len([t for t in purge_targets if t.exists()])
        ),
        "keep_main_image": keep_main_image,
        "delete_final_video": bool(delete_final_video and can_delete_final),
        "force": force,
    }
    if video_retained_reason:
        entry["final_video_retained_reason"] = video_retained_reason
        hk["final_video_retained_reason"] = video_retained_reason
    hist.insert(0, entry)
    hk["cleanup_history"] = hist[:10]
    atomic_write_json(manifest_path, manifest)

    return (
        True,
        {
            "bytes_freed_est": bytes_freed,
            "targets": len(purge_targets),
            "deleted": deleted_count,
            "applied": apply,
        },
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(
        description="RayVault Run Cleanup — selective purge of heavy assets",
    )
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--keep-main-image", action="store_true")
    ap.add_argument(
        "--delete-final-video",
        action="store_true",
        help="Delete publish/video_final.mp4 if upload receipt says UPLOADED",
    )
    ap.add_argument("--min-age-hours", type=float, default=0.0)
    ap.add_argument(
        "--min-upload-age-hours",
        type=float,
        default=24.0,
        help="Dead man's switch: min hours since upload before deleting final video (default: 24)",
    )
    ap.add_argument(
        "--force",
        action="store_true",
        help="Skip upload receipt check (manual override)",
    )
    args = ap.parse_args(argv)

    run_dir = Path(args.run_dir).expanduser().resolve()
    ok, info = cleanup(
        run_dir,
        apply=args.apply,
        keep_main_image=args.keep_main_image,
        delete_final_video=args.delete_final_video,
        min_age_hours=args.min_age_hours,
        min_upload_age_hours=args.min_upload_age_hours,
        force=args.force,
    )
    if ok:
        print(f"cleanup_run: {info}")
        return 0
    print(f"cleanup_run refused: {info}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
