#!/usr/bin/env python3
"""RayVault Unlock — force-release a stuck worker lock with forensic trail.

Only clears lock fields (worker_id, lock_token, locked_at, lock_expires_at).
Does NOT change run status — the run keeps its current state.

Usage:
    python3 tools/rayvault_unlock.py --run <UUID> --operator <NAME> --reason "why"
    python3 tools/rayvault_unlock.py --run <UUID> --operator <NAME> --force
    python3 tools/rayvault_unlock.py --run <UUID> --operator <NAME> --json

Exit codes:
    0 = unlocked successfully
    1 = not unlocked (lock still active and not expired, or run not found)
    2 = error (bad args, RPC failure, etc.)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_repo = Path(__file__).resolve().parent.parent
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))
_tools = Path(__file__).resolve().parent
if str(_tools) not in sys.path:
    sys.path.insert(0, str(_tools))

from tools.lib.common import load_env_file


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Force-release a stuck worker lock on a pipeline run.",
        epilog="Writes a 'manual_unlock' event to run_events for audit trail.",
    )
    parser.add_argument(
        "--run", required=True, metavar="UUID",
        help="Run ID to unlock",
    )
    parser.add_argument(
        "--operator", required=True, metavar="NAME",
        help="Who is unlocking (min 3 chars, e.g. 'Ray')",
    )
    parser.add_argument(
        "--reason", default="manual unlock via CLI",
        help="Why this unlock is happening (default: 'manual unlock via CLI')",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Unlock even if lease hasn't expired (emergency use)",
    )
    parser.add_argument(
        "--json", action="store_true", dest="json_output",
        help="Output result as JSON",
    )
    args = parser.parse_args()

    # Validate
    if len(args.operator.strip()) < 3:
        _output(args, ok=False, message="operator must be at least 3 characters")
        return 2

    # Load env
    load_env_file()

    # Check for required env vars
    supabase_url = os.environ.get("SUPABASE_URL", "")
    if not supabase_url:
        _output(args, ok=False, message="SUPABASE_URL not set")
        return 2

    # Call the RPC
    from tools.lib.run_manager import RunManager

    try:
        result = RunManager.force_unlock(
            args.run,
            operator_id=args.operator,
            reason=args.reason,
            force=args.force,
            use_supabase=True,
        )
    except Exception as exc:
        _output(args, ok=False, message=f"RPC error: {exc}")
        return 2

    if result:
        msg = f"UNLOCKED run {args.run}"
        if args.force:
            msg += " (forced)"
        msg += f" by {args.operator}: {args.reason}"
        _output(args, ok=True, message=msg)
        return 0
    else:
        msg = f"NOT UNLOCKED run {args.run}"
        if not args.force:
            msg += " — lease may still be active (use --force to override)"
        _output(args, ok=False, message=msg)
        return 1


def _output(args: argparse.Namespace, *, ok: bool, message: str) -> None:
    """Print result as text or JSON."""
    if args.json_output:
        print(json.dumps({
            "ok": ok,
            "run_id": args.run,
            "operator": args.operator,
            "message": message,
        }))
    else:
        prefix = "OK" if ok else "FAIL"
        print(f"[{prefix}] {message}")


if __name__ == "__main__":
    raise SystemExit(main())
