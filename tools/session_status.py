#!/usr/bin/env python3
"""Check login status across all target sites in the orange Brave profile.

Connects to the running orange Brave via CDP and checks each domain.
Sends a Telegram alert if any sessions have expired.

Usage:
    python3 tools/session_status.py
    python3 tools/session_status.py --json
    python3 tools/session_status.py --alert   # send Telegram if any logged out
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

_repo = Path(__file__).resolve().parent.parent
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))

from tools.lib.brave_profile import (
    LOGIN_CHECKS,
    is_browser_running,
    log_action,
)


def check_all_sessions() -> dict[str, bool | None]:
    """Check login status for all configured domains.

    Returns dict of domain -> True (logged in), False (logged out), None (error).
    Connects to the running browser via CDP.
    """
    from tools.lib.brave_profile import connect_or_launch

    if not is_browser_running():
        print("[session] Browser not running — cannot check sessions", file=sys.stderr)
        print("[session] Start OpenClaw or run: python3 tools/login_workspace.py", file=sys.stderr)
        return {name: None for name in LOGIN_CHECKS}

    browser, context, should_close, pw = connect_or_launch(headless=False)
    results: dict[str, bool | None] = {}

    try:
        for name, check in LOGIN_CHECKS.items():
            results[name] = _check_single(context, name, check)
    finally:
        if should_close:
            context.close()
        pw.stop()

    return results


def _check_single(context, name: str, check: dict) -> bool | None:
    """Check a single domain's login status.

    Uses DOM presence (count > 0) not visibility — many sites hide nav
    elements behind responsive layouts or collapsed sidebars.
    """
    url = check["url"]
    logged_in_sel = check["logged_in"]
    logged_out_sel = check["logged_out"]

    try:
        page = context.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=15000)
        # Wait for JS rendering (SPAs need time)
        page.wait_for_timeout(4000)

        # Check DOM presence of logged-in indicators
        in_count = page.locator(logged_in_sel).count()

        # Check DOM presence of logged-out indicators
        out_count = page.locator(logged_out_sel).count()

        page.close()

        if in_count > 0 and out_count == 0:
            return True
        if out_count > 0 and in_count == 0:
            return False
        # Both present (ambiguous) — prefer logged-in if indicator exists
        if in_count > 0:
            return True
        return False

    except Exception as exc:
        print(f"[session] {name}: check failed ({exc})", file=sys.stderr)
        try:
            page.close()
        except Exception:
            pass
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Check login status in orange Brave profile")
    parser.add_argument("--json", action="store_true", help="Output JSON only")
    parser.add_argument("--alert", action="store_true", help="Send Telegram alert for logged-out sites")
    args = parser.parse_args()

    results = check_all_sessions()

    if args.json:
        print(json.dumps(results, indent=2))
    else:
        print("Session Status — Orange Brave Profile")
        print("=" * 42)
        print()
        for name, status in results.items():
            if status is True:
                icon = "OK"
                label = "logged in"
            elif status is False:
                icon = "!!"
                label = "LOGGED OUT"
            else:
                icon = "??"
                label = "unknown"
            print(f"  [{icon}] {name:14s} {label}")
        print()
        print(f"Profile: ~/.openclaw/browser/openclaw/user-data/")

    # Count issues
    logged_out = [n for n, s in results.items() if s is False]
    unknown = [n for n, s in results.items() if s is None]

    log_action("check_session_status", f"out={len(logged_out)} unknown={len(unknown)}")

    if logged_out and args.alert:
        from tools.lib.control_plane import send_telegram
        sites = ", ".join(logged_out)
        send_telegram(f"Session expired on: {sites}\n\nRe-login needed in orange Brave.")
        print(f"Telegram alert sent for: {sites}")

    if logged_out:
        print(f"\n{len(logged_out)} site(s) need re-login: {', '.join(logged_out)}")
        print("Run: python3 tools/login_workspace.py")
        return 1

    if not unknown:
        print("All sessions active.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
