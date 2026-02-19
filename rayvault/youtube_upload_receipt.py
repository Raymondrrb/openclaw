#!/usr/bin/env python3
"""RayVault YouTube Upload Receipt — HMAC-signed proof of publish.

Creates an upload_receipt.json in publish/ after successful YouTube upload.
The receipt includes HMAC-SHA256 over critical fields so cleanup_run can
verify integrity before trusting UPLOADED status.

Golden rule: NEVER allow cleanup without verified receipt (or --force).

Usage:
    # After successful upload:
    python3 -m rayvault.youtube_upload_receipt \\
        --run-dir state/runs/RUN_2026_02_14_A \\
        --video-id dQw4w9WgXcQ \\
        --channel-id UC123456 \\
        --uploader manual

    # Verify existing receipt:
    python3 -m rayvault.youtube_upload_receipt \\
        --run-dir state/runs/RUN_2026_02_14_A \\
        --verify

Exit codes:
    0: success (receipt written or verification passed)
    1: runtime error
    2: preflight or verification failed
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from rayvault.io import atomic_write_json, read_json, utc_now_iso

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

RECEIPT_SCHEMA_VERSION = "1.0"

# HMAC key derivation: run_id + salt. In production this would come from
# a secrets manager. For RayVault local-first ops, we derive from run_id
# and a fixed salt to prevent casual edits from creating valid receipts.
_HMAC_SALT = b"rayvault_upload_receipt_v1_integrity"


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# HMAC signing / verification
# ---------------------------------------------------------------------------


def _derive_key(run_id: str) -> bytes:
    """Derive HMAC key from run_id + salt."""
    return hashlib.sha256(_HMAC_SALT + run_id.encode("utf-8")).digest()


def _compute_hmac(run_id: str, payload: str) -> str:
    """HMAC-SHA256 over canonical payload string."""
    key = _derive_key(run_id)
    return hmac.new(key, payload.encode("utf-8"), hashlib.sha256).hexdigest()


def _canonical_payload(receipt: Dict[str, Any]) -> str:
    """Build canonical string for HMAC from receipt fields.

    Canonical order: version|run_id|status|video_sha256|video_size|video_id|channel_id|uploaded_at_utc
    """
    inputs = receipt.get("inputs", {})
    youtube = receipt.get("youtube", {})
    parts = [
        receipt.get("version", ""),
        receipt.get("run_id", ""),
        receipt.get("status", ""),
        inputs.get("video_sha256", ""),
        str(inputs.get("video_size_bytes", 0)),
        youtube.get("video_id", ""),
        youtube.get("channel_id", ""),
        receipt.get("uploaded_at_utc", ""),
    ]
    return "|".join(parts)


def sign_receipt(receipt: Dict[str, Any]) -> str:
    """Compute HMAC for a receipt dict. Returns hex digest."""
    run_id = receipt["run_id"]
    payload = _canonical_payload(receipt)
    return _compute_hmac(run_id, payload)


def verify_receipt(receipt: Dict[str, Any]) -> bool:
    """Verify HMAC signature on a receipt dict."""
    integrity = receipt.get("integrity", {})
    stored_hmac = integrity.get("hmac_sha256", "")
    if not stored_hmac:
        return False
    expected = sign_receipt(receipt)
    return hmac.compare_digest(stored_hmac, expected)


# ---------------------------------------------------------------------------
# Preflight gates
# ---------------------------------------------------------------------------


def preflight_check(
    run_dir: Path,
    require_video: bool = True,
) -> Tuple[bool, str]:
    """Check prerequisites before writing receipt.

    Returns (ok, reason).
    """
    manifest_path = run_dir / "00_manifest.json"
    if not manifest_path.exists():
        return False, "missing_manifest"

    manifest = read_json(manifest_path)
    status = manifest.get("status", "UNKNOWN")

    # Must be READY_FOR_RENDER or already have validation passed
    validation = manifest.get("validation", {})
    validation_passed = validation.get("passed", False)

    if status != "READY_FOR_RENDER" and not validation_passed:
        return False, f"status={status}_not_ready"

    if require_video:
        video_path = run_dir / "publish" / "video_final.mp4"
        if not video_path.exists():
            return False, "missing_video_final"
        if video_path.stat().st_size < 1024:
            return False, "video_too_small"

    return True, "ok"


# ---------------------------------------------------------------------------
# Receipt generation
# ---------------------------------------------------------------------------


def generate_receipt(
    run_dir: Path,
    video_id: str,
    channel_id: str = "",
    uploader: str = "manual",
    video_url: Optional[str] = None,
    require_video: bool = True,
) -> Dict[str, Any]:
    """Generate and write HMAC-signed upload receipt.

    Returns the receipt dict.
    Raises ValueError/FileNotFoundError on preflight failure.
    """
    run_dir = run_dir.resolve()
    run_id = run_dir.name

    # Preflight
    ok, reason = preflight_check(run_dir, require_video=require_video)
    if not ok:
        raise ValueError(f"Preflight failed: {reason}")

    if not video_id or not video_id.strip():
        raise ValueError("video_id is required")

    # Video hash + size
    video_path = run_dir / "publish" / "video_final.mp4"
    video_sha256 = ""
    video_size = 0
    if video_path.exists():
        video_sha256 = sha256_file(video_path)
        video_size = video_path.stat().st_size

    # Default video URL
    if not video_url and video_id:
        video_url = f"https://youtu.be/{video_id}"

    uploaded_at = utc_now_iso()

    receipt = {
        "version": RECEIPT_SCHEMA_VERSION,
        "run_id": run_id,
        "status": "UPLOADED",
        "uploader": uploader,
        "uploaded_at_utc": uploaded_at,
        "inputs": {
            "video_path": "publish/video_final.mp4",
            "video_sha256": video_sha256,
            "video_size_bytes": video_size,
        },
        "youtube": {
            "video_id": video_id,
            "video_url": video_url,
            "channel_id": channel_id,
        },
    }

    # Sign
    hmac_value = sign_receipt(receipt)
    receipt["integrity"] = {
        "method": "hmac_sha256",
        "hmac_sha256": hmac_value,
        "signed_fields": "version|run_id|status|video_sha256|video_size|video_id|channel_id|uploaded_at_utc",
    }

    # Write receipt atomically
    receipt_path = run_dir / "publish" / "upload_receipt.json"
    atomic_write_json(receipt_path, receipt)

    # Update manifest
    manifest_path = run_dir / "00_manifest.json"
    if manifest_path.exists():
        manifest = read_json(manifest_path)
        manifest["status"] = "UPLOADED"
        manifest.setdefault("publish", {})
        manifest["publish"]["receipt_path"] = "publish/upload_receipt.json"
        manifest["publish"]["video_id"] = video_id
        manifest["publish"]["video_url"] = video_url
        manifest["publish"]["channel_id"] = channel_id
        manifest["publish"]["uploaded_at_utc"] = uploaded_at
        manifest["publish"]["uploader"] = uploader
        atomic_write_json(manifest_path, manifest)

    return receipt


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(
        description="RayVault YouTube Upload Receipt — HMAC-signed proof",
    )
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--video-id", default=None, help="YouTube video ID")
    ap.add_argument("--channel-id", default="", help="YouTube channel ID")
    ap.add_argument(
        "--uploader",
        default="manual",
        help="Who/what uploaded (manual, automation, etc.)",
    )
    ap.add_argument("--video-url", default=None)
    ap.add_argument(
        "--verify",
        action="store_true",
        help="Verify existing receipt instead of generating",
    )
    ap.add_argument(
        "--no-video-check",
        action="store_true",
        help="Skip video file preflight (for external uploaders)",
    )
    args = ap.parse_args(argv)

    run_dir = Path(args.run_dir).expanduser().resolve()
    if not run_dir.exists():
        print(f"Run dir not found: {run_dir}", file=sys.stderr)
        return 2

    # Verify mode
    if args.verify:
        receipt_path = run_dir / "publish" / "upload_receipt.json"
        if not receipt_path.exists():
            print("FAIL: no upload_receipt.json found", file=sys.stderr)
            return 2
        receipt = read_json(receipt_path)
        if verify_receipt(receipt):
            print(
                f"PASS: receipt verified | run={receipt['run_id']} "
                f"| video_id={receipt['youtube']['video_id']}"
            )
            return 0
        print("FAIL: HMAC verification failed — receipt may be tampered")
        return 2

    # Generate mode
    if not args.video_id:
        print("--video-id is required for receipt generation", file=sys.stderr)
        return 2

    try:
        receipt = generate_receipt(
            run_dir,
            video_id=args.video_id,
            channel_id=args.channel_id,
            uploader=args.uploader,
            video_url=args.video_url,
            require_video=not args.no_video_check,
        )
        vid = receipt["youtube"]["video_id"]
        sha = receipt["inputs"]["video_sha256"][:12]
        print(f"upload_receipt: UPLOADED | video_id={vid} | sha256={sha}...")
        return 0
    except (ValueError, FileNotFoundError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
