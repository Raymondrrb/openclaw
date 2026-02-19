#!/usr/bin/env python3
"""RayVault Cron Verify Visibility — batch scan UPLOADED runs for verification.

Scans state/runs/*/publish/upload_receipt.json for UPLOADED receipts
and calls verify_visibility to promote them to VERIFIED.

Designed for cron/scheduled execution (e.g., every 2 hours).

Usage:
    python3 -m rayvault.cron_verify_visibility
    python3 -m rayvault.cron_verify_visibility --runs-root state/runs
    python3 -m rayvault.cron_verify_visibility --manual  # manual verify all

Env:
    RAY_YT_VERIFY_CMD: external verifier command (e.g., 'python3 tools/yt_verify.py {video_id}')
    RAY_RUNS_ROOT: runs directory (default: state/runs)

Cron example:
    0 */2 * * * cd /path/to/rayvault && python3 -m rayvault.cron_verify_visibility >> logs/verify.log 2>&1

Exit codes:
    0: completed (some may have failed individually)
    1: runtime error
    2: missing configuration
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from rayvault.io import read_json, utc_now_iso


# ---------------------------------------------------------------------------
# Core scan
# ---------------------------------------------------------------------------


def scan_uploaded_runs(runs_root: Path) -> List[Path]:
    """Find run directories with UPLOADED receipts."""
    uploaded = []
    if not runs_root.is_dir():
        return uploaded
    for receipt_path in sorted(runs_root.glob("*/publish/upload_receipt.json")):
        try:
            receipt = read_json(receipt_path)
            if receipt.get("status") == "UPLOADED":
                uploaded.append(receipt_path.parent.parent)
        except Exception:
            continue
    return uploaded


def verify_batch(
    runs_root: Path,
    verify_cmd: Optional[str] = None,
    manual: bool = False,
    max_runs: int = 50,
) -> Dict[str, Any]:
    """Verify all UPLOADED runs in batch.

    Returns summary dict with results per run.
    """
    from rayvault.verify_visibility import verify

    uploaded_runs = scan_uploaded_runs(runs_root)

    results: List[Dict[str, Any]] = []
    verified_count = 0
    failed_count = 0
    skipped_count = 0

    for run_dir in uploaded_runs[:max_runs]:
        run_id = run_dir.name
        try:
            result = verify(
                run_dir,
                verify_cmd=verify_cmd,
                manual=manual,
            )
            status = result.get("status", "UNKNOWN")
            ok = result.get("ok", False)

            if ok and status == "VERIFIED":
                verified_count += 1
            elif ok and result.get("already"):
                skipped_count += 1
            elif not ok:
                failed_count += 1

            results.append({
                "run": run_id,
                "ok": ok,
                "status": status,
                "reason": result.get("reason"),
            })
        except Exception as e:
            failed_count += 1
            results.append({
                "run": run_id,
                "ok": False,
                "error": str(e)[:200],
            })

    return {
        "checked_at_utc": utc_now_iso(),
        "total_uploaded": len(uploaded_runs),
        "checked": len(results),
        "verified": verified_count,
        "failed": failed_count,
        "skipped": skipped_count,
        "results": results,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(
        description="RayVault Cron Verify — batch scan UPLOADED runs",
    )
    ap.add_argument(
        "--runs-root",
        default=os.getenv("RAY_RUNS_ROOT", "state/runs"),
    )
    ap.add_argument(
        "--verify-cmd",
        default=None,
        help="External verifier command (or set RAY_YT_VERIFY_CMD env var)",
    )
    ap.add_argument(
        "--manual",
        action="store_true",
        help="Manual verify all (no external verifier needed)",
    )
    ap.add_argument("--max-runs", type=int, default=50)
    args = ap.parse_args(argv)

    runs_root = Path(args.runs_root).expanduser().resolve()

    verify_cmd = args.verify_cmd or os.getenv("RAY_YT_VERIFY_CMD", "")

    if not args.manual and not verify_cmd:
        print(
            "No verify command. Set RAY_YT_VERIFY_CMD or use --manual",
            file=sys.stderr,
        )
        return 2

    try:
        summary = verify_batch(
            runs_root,
            verify_cmd=verify_cmd if not args.manual else None,
            manual=args.manual,
            max_runs=args.max_runs,
        )
        total = summary["total_uploaded"]
        verified = summary["verified"]
        failed = summary["failed"]
        print(
            f"cron_verify: checked={summary['checked']}/{total} "
            f"| verified={verified} | failed={failed} "
            f"| skipped={summary['skipped']}"
        )
        if failed > 0:
            for r in summary["results"]:
                if not r.get("ok"):
                    print(f"  FAIL: {r['run']} — {r.get('reason', r.get('error', ''))}")
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
