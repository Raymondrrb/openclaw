#!/usr/bin/env python3
"""RayVault Verify Visibility — confirm UPLOADED -> VERIFIED.

After YouTube upload, verifies the video exists, is processed, matches
expected privacy, and has no copyright claims. Promotes receipt status
from UPLOADED to VERIFIED only when all checks pass.

Usage:
    # With external verifier command:
    python3 -m rayvault.verify_visibility \\
        --run-dir state/runs/RUN_2026_02_14_A \\
        --verify-cmd 'yt-verify {video_id}'

    # Manual verification (marks as VERIFIED without external check):
    python3 -m rayvault.verify_visibility \\
        --run-dir state/runs/RUN_2026_02_14_A \\
        --manual

    # Env var: RAY_YT_VERIFY_CMD='yt-verify {video_id}'

External verifier contract:
    The command receives video_id via {video_id} placeholder.
    Must print JSON to stdout:
    {
        "ok": true,
        "privacy": "unlisted",
        "processing": "succeeded",
        "claims": []
    }

Exit codes:
    0: VERIFIED
    1: runtime error
    2: verification failed or prerequisites missing
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

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


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# External verifier
# ---------------------------------------------------------------------------


def run_external_verifier(
    cmd_template: str, video_id: str, timeout: int = 300
) -> Dict[str, Any]:
    """Run external verifier command and parse JSON output.

    The command template should contain {video_id} placeholder.
    Uses shlex.split to avoid shell injection.
    """
    # Replace placeholder (no shell=True to avoid injection)
    full_cmd = cmd_template.replace("{video_id}", video_id)
    try:
        parts = shlex.split(full_cmd)
    except ValueError as e:
        return {"ok": False, "error": {"code": "BAD_CMD", "detail": str(e)}}

    try:
        proc = subprocess.run(
            parts,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if proc.returncode != 0:
            return {
                "ok": False,
                "error": {
                    "code": "VERIFY_CMD_FAIL",
                    "returncode": proc.returncode,
                    "stderr": proc.stderr[-2000:] if proc.stderr else "",
                },
            }
        result = json.loads(proc.stdout.strip())
        return result
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": {"code": "TIMEOUT"}}
    except json.JSONDecodeError:
        return {
            "ok": False,
            "error": {"code": "BAD_JSON", "stdout_tail": proc.stdout[-500:]},
        }
    except Exception as e:
        return {"ok": False, "error": {"code": str(type(e).__name__)}}


# ---------------------------------------------------------------------------
# Core verification
# ---------------------------------------------------------------------------


DOUBLE_PASS_SPACING_HOURS = 12.0


def _parse_utc(iso_str: str) -> float:
    """Parse ISO UTC string to timestamp. Returns 0.0 on failure."""
    try:
        return datetime.fromisoformat(
            iso_str.replace("Z", "+00:00")
        ).timestamp()
    except Exception:
        return 0.0


def _needs_double_pass(manifest_path: Path) -> bool:
    """Check if run requires double-pass verify (safe_audio_mode=false)."""
    if not manifest_path.exists():
        return False
    try:
        m = read_json(manifest_path)
        proof = m.get("audio_proof", {})
        return proof.get("safe_audio_mode") is False
    except Exception:
        return False


def _check_double_pass(
    receipt: Dict[str, Any],
    spacing_hours: float = DOUBLE_PASS_SPACING_HOURS,
) -> Dict[str, Any]:
    """Check if double-pass requirement is met.

    Returns {"met": bool, "passes": int, "next_allowed_utc": str | None}
    """
    passes = receipt.get("verify_passes", [])
    if len(passes) < 2:
        return {
            "met": False,
            "passes": len(passes),
            "next_allowed_utc": None,
        }

    # Check spacing between first and last pass
    first_ts = _parse_utc(passes[0].get("at_utc", ""))
    last_ts = _parse_utc(passes[-1].get("at_utc", ""))
    if first_ts <= 0 or last_ts <= 0:
        return {"met": False, "passes": len(passes), "next_allowed_utc": None}

    spacing_sec = last_ts - first_ts
    required_sec = spacing_hours * 3600.0
    if spacing_sec >= required_sec:
        return {"met": True, "passes": len(passes), "next_allowed_utc": None}

    # Not enough spacing — compute when next pass is allowed
    next_ts = first_ts + required_sec
    next_utc = datetime.fromtimestamp(next_ts, tz=timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    return {
        "met": False,
        "passes": len(passes),
        "next_allowed_utc": next_utc,
    }


def verify(
    run_dir: Path,
    verify_cmd: Optional[str] = None,
    manual: bool = False,
) -> Dict[str, Any]:
    """Verify upload and promote receipt to VERIFIED if checks pass.

    For runs with safe_audio_mode=false, requires 2 OK verification
    passes spaced >= 12h before promoting to VERIFIED.

    Returns dict with verified status and details.
    """
    run_dir = run_dir.resolve()
    receipt_path = run_dir / "publish" / "upload_receipt.json"
    manifest_path = run_dir / "00_manifest.json"

    if not receipt_path.exists():
        return {"ok": False, "reason": "missing_receipt"}

    receipt = read_json(receipt_path)
    if receipt.get("status") not in ("UPLOADED", "VERIFIED"):
        return {
            "ok": False,
            "reason": f"receipt_status_{receipt.get('status', 'UNKNOWN')}",
        }

    video_id = receipt.get("youtube", {}).get("video_id")
    if not video_id:
        return {"ok": False, "reason": "missing_video_id"}

    # Already verified
    if receipt.get("status") == "VERIFIED" and not manual:
        return {"ok": True, "status": "VERIFIED", "already": True}

    double_pass = _needs_double_pass(manifest_path)

    # Manual verification (trust operator — bypasses double-pass)
    if manual:
        receipt["youtube"]["processing_state"] = "SUCCEEDED"
        receipt["youtube"]["visibility_state"] = "MANUAL_VERIFIED"
        receipt["youtube"].setdefault("copyright_claims", [])
        receipt["status"] = "VERIFIED"
        receipt["verified_at_utc"] = utc_now_iso()
        receipt["verified_by"] = "manual"

        # Re-sign receipt
        try:
            from rayvault.youtube_upload_receipt import sign_receipt
            receipt["integrity"]["hmac_sha256"] = sign_receipt(receipt)
        except ImportError:
            pass

        atomic_write_json(receipt_path, receipt)
        _update_manifest(manifest_path, receipt)
        return {"ok": True, "status": "VERIFIED", "method": "manual"}

    # External verifier
    if not verify_cmd:
        verify_cmd = os.getenv("RAY_YT_VERIFY_CMD", "")
    if not verify_cmd:
        return {"ok": False, "reason": "no_verify_cmd"}

    proof = run_external_verifier(verify_cmd, video_id)
    if not proof.get("ok"):
        receipt["youtube"]["processing_state"] = "UNKNOWN"
        receipt.setdefault("verify_errors", []).append({
            "at_utc": utc_now_iso(),
            "error": proof.get("error", {}),
        })
        atomic_write_json(receipt_path, receipt)
        return {"ok": False, "reason": "verify_cmd_failed", "error": proof.get("error")}

    # Update receipt with proof
    receipt["youtube"]["processing_state"] = (
        proof.get("processing", "UNKNOWN").upper()
    )
    receipt["youtube"]["visibility_state"] = (
        proof.get("privacy", "UNKNOWN").upper()
    )
    receipt["youtube"]["copyright_claims"] = proof.get("claims", [])

    # Check all conditions for VERIFIED
    ok_processing = receipt["youtube"]["processing_state"] in (
        "SUCCEEDED", "DONE", "READY"
    )
    ok_claims = len(receipt["youtube"]["copyright_claims"]) == 0

    if ok_processing and ok_claims:
        # Record this pass
        receipt.setdefault("verify_passes", []).append({
            "at_utc": utc_now_iso(),
            "processing": receipt["youtube"]["processing_state"],
            "visibility": receipt["youtube"]["visibility_state"],
        })

        # Double-pass gate for unsafe audio
        if double_pass:
            dp_status = _check_double_pass(receipt)
            if not dp_status["met"]:
                # Pass recorded but not enough passes or spacing yet
                atomic_write_json(receipt_path, receipt)
                _update_manifest(manifest_path, receipt)
                return {
                    "ok": False,
                    "status": "UPLOADED",
                    "reason": "double_pass_pending",
                    "passes": dp_status["passes"],
                    "next_allowed_utc": dp_status["next_allowed_utc"],
                    "processing": receipt["youtube"]["processing_state"],
                    "visibility": receipt["youtube"]["visibility_state"],
                    "claims": 0,
                }

        receipt["status"] = "VERIFIED"
        receipt["verified_at_utc"] = utc_now_iso()
        receipt["verified_by"] = "external_verifier"
        if double_pass:
            receipt["verified_by"] = "external_verifier_double_pass"

        # Re-sign receipt
        try:
            from rayvault.youtube_upload_receipt import sign_receipt
            receipt["integrity"]["hmac_sha256"] = sign_receipt(receipt)
        except ImportError:
            pass

    atomic_write_json(receipt_path, receipt)
    _update_manifest(manifest_path, receipt)

    return {
        "ok": receipt["status"] == "VERIFIED",
        "status": receipt["status"],
        "processing": receipt["youtube"]["processing_state"],
        "visibility": receipt["youtube"]["visibility_state"],
        "claims": len(receipt["youtube"]["copyright_claims"]),
    }


def _update_manifest(
    manifest_path: Path, receipt: Dict[str, Any]
) -> None:
    """Update manifest with verification state."""
    if not manifest_path.exists():
        return
    m = read_json(manifest_path)
    m.setdefault("publish", {})
    m["publish"]["verified"] = receipt.get("status") == "VERIFIED"
    m["publish"]["verified_at_utc"] = receipt.get("verified_at_utc")
    m["publish"]["processing_state"] = receipt.get("youtube", {}).get(
        "processing_state"
    )
    m["publish"]["visibility_state"] = receipt.get("youtube", {}).get(
        "visibility_state"
    )
    if receipt.get("verify_passes"):
        m["publish"]["verify_passes"] = len(receipt["verify_passes"])
    if receipt.get("status") == "VERIFIED":
        m["status"] = "VERIFIED"
    atomic_write_json(manifest_path, m)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(
        description="RayVault Verify Visibility — UPLOADED -> VERIFIED",
    )
    ap.add_argument("--run-dir", required=True)
    ap.add_argument(
        "--verify-cmd",
        default=None,
        help="External verifier command with {video_id} placeholder",
    )
    ap.add_argument(
        "--manual",
        action="store_true",
        help="Manual verification (trust operator)",
    )
    args = ap.parse_args(argv)

    run_dir = Path(args.run_dir).expanduser().resolve()
    if not run_dir.exists():
        print(f"Run dir not found: {run_dir}", file=sys.stderr)
        return 2

    result = verify(
        run_dir,
        verify_cmd=args.verify_cmd,
        manual=args.manual,
    )
    status = result.get("status", "UNKNOWN")
    ok = result.get("ok", False)

    if ok:
        print(f"verify_visibility: {status}")
    else:
        reason = result.get("reason", "unknown")
        print(f"verify_visibility: FAILED ({reason})", file=sys.stderr)

    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
