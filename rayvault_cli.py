#!/usr/bin/env python3
"""RayVault CLI — single entrypoint for all operations.

Subcommands:
    worker          Start worker loop (continuous or --once)
    doctor          Morning routine: replay spool + health + contract check
    health          Health check only
    replay-spool    Replay pending spool events to Supabase
    check-contract  Verify all RPCs are deployed and callable
    unlock          Force unlock a run via RPC
    stop            Stop the running worker using PID file

Exit codes (SRE-friendly, automatable via cron/menubar):
    0 = OK
    1 = WARN (non-critical issues found)
    2 = CRITICAL (action required)
    3 = ERROR (config/runtime error)

Usage:
    python3 rayvault_cli.py doctor          # morning routine (replay + health + contract)
    python3 rayvault_cli.py worker          # start worker
    python3 rayvault_cli.py stop            # graceful stop via SIGTERM
    python3 rayvault_cli.py unlock --run <uuid> --reason "stuck"
    python3 rayvault_cli.py check-contract  # verify RPCs before go-live

With caffeinate (recommended for Mac):
    caffeinate -dimsu python3 rayvault_cli.py worker
"""

from __future__ import annotations

import argparse
import os
import signal
import sys
from pathlib import Path

# Ensure repo root and tools/ are in path
_repo = Path(__file__).resolve().parent
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))
_tools = _repo / "tools"
if str(_tools) not in sys.path:
    sys.path.insert(0, str(_tools))

from tools.lib.common import load_env_file
from tools.lib.config import load_worker_config


# ---------------------------------------------------------------------------
# Exit codes
# ---------------------------------------------------------------------------

EXIT_OK = 0
EXIT_WARN = 1
EXIT_CRITICAL = 2
EXIT_ERROR = 3


# ---------------------------------------------------------------------------
# Subcommand: worker
# ---------------------------------------------------------------------------

def _is_pid_alive(pid: int) -> bool:
    """Check if a process is alive (without sending a real signal)."""
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # exists but no permission = still alive


def cmd_worker(args: argparse.Namespace) -> int:
    """Start the worker loop."""
    from tools.worker import (
        worker_loop, write_pid, remove_pid, read_pid,
        _stop_signal,
    )
    import signal as sig

    cfg, _ = load_worker_config(worker_id=args.worker_id)

    worker_id = args.worker_id or cfg.worker_id
    if len(worker_id.strip()) < 3:
        print("[cli] Error: worker-id must be at least 3 characters", file=sys.stderr)
        return EXIT_ERROR

    lease = args.lease or cfg.lease_minutes

    # PID guardrail: refuse to start if another worker is alive
    existing_pid = read_pid()
    if existing_pid:
        if _is_pid_alive(existing_pid):
            print(
                f"[cli] Worker already running (PID {existing_pid}). Refusing to start.",
                file=sys.stderr,
            )
            print("[cli] Use: rayvault_cli.py stop", file=sys.stderr)
            return EXIT_WARN
        else:
            # Stale PID file — clean up
            remove_pid()

    # Signal handlers
    def handle_signal(signum, frame):
        sig_name = sig.Signals(signum).name
        print(f"\n[cli] Received {sig_name} — shutting down gracefully...", file=sys.stderr)
        _stop_signal.set()

    sig.signal(sig.SIGINT, handle_signal)
    sig.signal(sig.SIGTERM, handle_signal)

    write_pid()
    try:
        return worker_loop(
            worker_id,
            lease_minutes=lease,
            poll_interval=args.poll or cfg.poll_interval_sec,
            once=args.once,
        )
    finally:
        remove_pid()


# ---------------------------------------------------------------------------
# Subcommand: doctor / health / replay-spool / check-contract
# ---------------------------------------------------------------------------

def cmd_doctor(args: argparse.Namespace) -> int:
    """Run doctor with specified modes."""
    from tools.lib.doctor import (
        replay_spool, health_check, check_rpc_contract,
        print_report,
    )
    cfg, secrets = load_worker_config()

    if not secrets.supabase_url or not secrets.supabase_service_key:
        print("[cli] ERROR: Set SUPABASE_URL and SUPABASE_SERVICE_KEY", file=sys.stderr)
        return EXIT_ERROR

    worst = EXIT_OK

    # Contract check
    if getattr(args, "do_contract", False):
        passed, failed = check_rpc_contract(
            secrets.supabase_url,
            secrets.supabase_service_key,
            timeout=cfg.rpc_timeout_sec,
        )
        for name in passed:
            print(f"[CONTRACT] PASS: {name}")
        for name in failed:
            print(f"[CONTRACT] FAIL: {name}")
        if not failed:
            print(f"[CONTRACT] All {len(passed)} RPCs callable.")
        else:
            worst = max(worst, EXIT_CRITICAL)

    # Replay spool
    spool_stats = None
    if getattr(args, "do_spool", False):
        spool_stats = replay_spool(
            cfg.spool_dir,
            secrets.supabase_url,
            secrets.supabase_service_key,
            timeout=cfg.rpc_timeout_sec,
            max_retries=cfg.thresholds.spool_max_retries,
        )
        synced, failed, remaining = spool_stats
        if remaining > 0:
            worst = max(worst, EXIT_WARN)

    # Health check
    results = {"counts": {}}
    if getattr(args, "do_health", False):
        results = health_check(
            secrets.supabase_url,
            secrets.supabase_service_key,
            cfg.thresholds,
            timeout=cfg.rpc_timeout_sec,
        )
        c = results.get("counts", {})
        if c.get("stale_workers", 0) > 0 or c.get("lat_crit", 0) > 0:
            worst = max(worst, EXIT_CRITICAL)
        elif c.get("ghost", 0) > 0 or c.get("stale_gate", 0) > 0 or c.get("lat_warn", 0) > 0:
            worst = max(worst, EXIT_WARN)

    if getattr(args, "do_health", False) or spool_stats:
        print_report(results, cfg.thresholds, spool_stats=spool_stats)

    return worst


# ---------------------------------------------------------------------------
# Subcommand: unlock
# ---------------------------------------------------------------------------

def cmd_unlock(args: argparse.Namespace) -> int:
    """Force unlock a run via RPC."""
    import json
    from tools.lib.doctor import _make_headers, _http_post

    cfg, secrets = load_worker_config()

    if not secrets.supabase_url or not secrets.supabase_service_key:
        print("[cli] ERROR: Set SUPABASE_URL and SUPABASE_SERVICE_KEY", file=sys.stderr)
        return EXIT_ERROR

    url = f"{secrets.supabase_url}/rest/v1/rpc/rpc_force_unlock_run"
    headers = _make_headers(secrets.supabase_service_key)
    payload = {
        "p_run_id": args.run,
        "p_operator_id": args.operator,
        "p_reason": args.reason,
        "p_force": args.force,
    }

    status, body = _http_post(url, payload, headers, timeout=cfg.rpc_timeout_sec)

    if status < 300:
        result = json.loads(body) if body.strip() else None
        success = bool(result)
        if success:
            print(f"Unlocked run {args.run} (force={args.force}).")
            return EXIT_OK
        else:
            print(f"Unlock refused for run {args.run}. Check status/lease.")
            return EXIT_WARN
    else:
        print(f"Unlock failed: HTTP {status} — {body[:200]}")
        return EXIT_ERROR


# ---------------------------------------------------------------------------
# Subcommand: stop
# ---------------------------------------------------------------------------

def cmd_stop(args: argparse.Namespace) -> int:
    """Stop the running worker using PID file."""
    from tools.worker import read_pid, remove_pid

    pid = read_pid()
    if not pid:
        print("[cli] No PID file found. Worker may not be running.")
        return EXIT_OK

    sig = signal.SIGKILL if args.force else signal.SIGTERM
    try:
        os.kill(pid, sig)
        sig_name = signal.Signals(sig).name
        print(f"[cli] Sent {sig_name} to worker PID {pid}.")
        return EXIT_OK
    except ProcessLookupError:
        print(f"[cli] PID {pid} not running. Cleaning PID file.")
        remove_pid()
        return EXIT_OK
    except PermissionError:
        print(f"[cli] Permission denied for PID {pid}.")
        return EXIT_ERROR


# ---------------------------------------------------------------------------
# CLI parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="rayvault",
        description="RayVault SRE CLI — worker, doctor, unlock, stop",
    )
    sub = p.add_subparsers(dest="cmd")

    # worker
    w = sub.add_parser("worker", help="Start worker loop")
    w.add_argument("--worker-id", default="",
                    help="Worker identifier (min 3 chars). Default: from env/hostname.")
    w.add_argument("--lease", type=int, default=0,
                    help="Lease duration in minutes (default: from config)")
    w.add_argument("--poll", type=int, default=0,
                    help="Poll interval in seconds (default: from config)")
    w.add_argument("--once", action="store_true",
                    help="Process one run and exit")

    # doctor (full morning routine)
    d = sub.add_parser("doctor", help="Morning routine: replay + health + contract")
    d.add_argument("--replay-spool", action="store_true", dest="do_spool_flag",
                    help="Only replay spool")
    d.add_argument("--health", action="store_true", dest="do_health_flag",
                    help="Only health check")
    d.add_argument("--check-contract", action="store_true", dest="do_contract_flag",
                    help="Only contract check")

    # Shortcuts
    sub.add_parser("health", help="Health check only")
    sub.add_parser("replay-spool", help="Replay spool only")
    sub.add_parser("check-contract", help="Verify RPCs are deployed")

    # unlock
    u = sub.add_parser("unlock", help="Force unlock a run via RPC")
    u.add_argument("--run", required=True, help="Run UUID")
    u.add_argument("--operator", default=os.environ.get("OPERATOR_ID", "Ray"),
                    help="Operator ID for audit log")
    u.add_argument("--reason", default="manual intervention",
                    help="Reason for audit log")
    u.add_argument("--force", action="store_true",
                    help="Force unlock even if lease is active")

    # stop
    s = sub.add_parser("stop", help="Stop the running worker via PID file")
    s.add_argument("--force", action="store_true",
                    help="Use SIGKILL instead of SIGTERM")

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.cmd:
        parser.print_help()
        return EXIT_ERROR

    # Load env
    load_env_file()

    # Dispatch
    if args.cmd == "worker":
        return cmd_worker(args)

    if args.cmd == "stop":
        return cmd_stop(args)

    if args.cmd == "unlock":
        return cmd_unlock(args)

    # Doctor variants: set flags based on which subcommand
    if args.cmd == "health":
        args.do_health = True
        args.do_spool = False
        args.do_contract = False
        return cmd_doctor(args)

    if args.cmd == "replay-spool":
        args.do_health = False
        args.do_spool = True
        args.do_contract = False
        return cmd_doctor(args)

    if args.cmd == "check-contract":
        args.do_health = False
        args.do_spool = False
        args.do_contract = True
        return cmd_doctor(args)

    if args.cmd == "doctor":
        # If specific flags given, use them. Otherwise, do all.
        has_specific = (
            getattr(args, "do_spool_flag", False)
            or getattr(args, "do_health_flag", False)
            or getattr(args, "do_contract_flag", False)
        )
        if has_specific:
            args.do_spool = getattr(args, "do_spool_flag", False)
            args.do_health = getattr(args, "do_health_flag", False)
            args.do_contract = getattr(args, "do_contract_flag", False)
        else:
            # Default: full morning routine
            args.do_spool = True
            args.do_health = True
            args.do_contract = True
        return cmd_doctor(args)

    parser.print_help()
    return EXIT_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
