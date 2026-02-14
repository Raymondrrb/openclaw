#!/usr/bin/env python3
"""RayVault Run Cleanup — selective purge of heavy assets post-publish.

Keeps forensic metadata (manifest, metadata, product.json, qc.json, logs).
Purges heavy files (source_images, broll, audio, frame, final video).

Golden rule: NEVER purge unless upload_receipt.json confirms success OR --force.

Usage:
    python3 -m rayvault.cleanup_run --run-dir state/runs/RUN_2026_02_14_A
    python3 -m rayvault.cleanup_run --run-dir state/runs/RUN_2026_02_14_A --apply
    python3 -m rayvault.cleanup_run --run-dir state/runs/RUN_2026_02_14_A --apply --force

Exit codes:
    0: success (including dry-run)
    1: unexpected error
    2: refused by safety (no receipt, too new, missing run)
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
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


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


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Receipt loading
# ---------------------------------------------------------------------------


def load_receipt(run_dir: Path) -> Optional[Dict[str, Any]]:
    r = run_dir / "publish" / "upload_receipt.json"
    if not r.exists():
        return None
    return read_json(r)


# ---------------------------------------------------------------------------
# Core cleanup
# ---------------------------------------------------------------------------


def cleanup(
    run_dir: Path,
    apply: bool = False,
    keep_main_image: bool = False,
    delete_final_video: bool = True,
    min_age_hours: float = 0.0,
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

    # Safety: receipt check
    receipt = load_receipt(run_dir)
    if not force:
        if not receipt or receipt.get("status") != "UPLOADED":
            return (False, "missing_or_not_uploaded_receipt")

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

    # Final video: only if receipt confirms upload
    final_video = run_dir / "publish" / "video_final.mp4"
    can_delete_final = bool(
        receipt and receipt.get("status") == "UPLOADED"
    )
    if delete_final_video and can_delete_final and final_video.exists():
        purge_targets.append(final_video)

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
    hist.insert(
        0,
        {
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
        },
    )
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
        force=args.force,
    )
    if ok:
        print(f"cleanup_run: {info}")
        return 0
    print(f"cleanup_run refused: {info}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
