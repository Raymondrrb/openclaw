#!/usr/bin/env python3
"""Open the login workspace — all target sites in the orange Brave profile.

One-time manual step: log in to each tab, then sessions persist.

Usage:
    python3 tools/login_workspace.py
    python3 tools/login_workspace.py --check   # also run session status after
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path

_repo = Path(__file__).resolve().parent.parent
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))

from tools.lib.brave_profile import (
    CDP_URL,
    DEFAULT_CDP_PORT,
    LOGIN_WORKSPACE_URLS,
    get_open_tabs,
    is_browser_running,
    log_action,
)


def _extract_domain(url: str) -> str:
    """Extract the base domain from a URL (e.g. youtube.com from www.youtube.com/watch)."""
    from urllib.parse import urlparse
    hostname = urlparse(url).hostname or ""
    # Strip www. prefix for matching
    return hostname.removeprefix("www.")


def open_tabs_via_cdp(urls: list[str], port: int = DEFAULT_CDP_PORT) -> int:
    """Open tabs in the already-running orange Brave via CDP."""
    existing = get_open_tabs(port)
    existing_domains = {_extract_domain(t.get("url", "")) for t in existing}

    opened = 0
    for url in urls:
        # Skip if a tab for this domain is already open
        domain = _extract_domain(url)
        if domain in existing_domains:
            print(f"  Already open: {url} (tab exists for {domain})")
            continue

        # Open new tab via CDP PUT request
        try:
            encoded = url.replace('"', "%22")
            put_url = f"http://127.0.0.1:{port}/json/new?{encoded}"
            req = urllib.request.Request(put_url, method="PUT")
            with urllib.request.urlopen(req, timeout=10) as resp:
                resp.read()
            print(f"  Opened: {url}")
            opened += 1
            time.sleep(0.5)
        except Exception:
            # Some CDP implementations need GET instead of PUT
            try:
                req = urllib.request.Request(put_url)
                with urllib.request.urlopen(req, timeout=10) as resp:
                    resp.read()
                print(f"  Opened: {url}")
                opened += 1
                time.sleep(0.5)
            except Exception as exc:
                print(f"  Failed to open {url}: {exc}", file=sys.stderr)

    return opened


def open_tabs_via_playwright(urls: list[str]) -> None:
    """Fallback: launch Brave with Playwright and open tabs."""
    from tools.lib.brave_profile import connect_or_launch

    browser, context, should_close, pw = connect_or_launch(headless=False)
    try:
        for url in urls:
            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=15000)
            print(f"  Opened: {url}")
            time.sleep(0.5)

        print("\nBrowser is open. Log in to each tab, then close when done.")
        print("Sessions will persist in the orange Brave profile.")

        # Keep alive until user closes
        if should_close:
            input("Press Enter when you're done logging in...")
    finally:
        if should_close:
            context.close()
        pw.stop()


def main() -> int:
    parser = argparse.ArgumentParser(description="Open login workspace in orange Brave")
    parser.add_argument("--check", action="store_true", help="Run session status check after")
    args = parser.parse_args()

    print("Login Workspace — Orange Brave Profile")
    print("=" * 45)

    if is_browser_running():
        print(f"\nBrowser running on CDP port {DEFAULT_CDP_PORT}")
        print("Opening tabs...\n")
        opened = open_tabs_via_cdp(LOGIN_WORKSPACE_URLS)
        print(f"\n{opened} new tab(s) opened.")
        log_action("open_login_workspace", f"cdp opened={opened}")
    else:
        print("\nBrowser not running — launching Brave with persistent profile...")
        open_tabs_via_playwright(LOGIN_WORKSPACE_URLS)
        log_action("open_login_workspace", "playwright_launch")

    print("\nPlease log in to each site. Sessions will persist in the orange profile.")
    print(f"Profile: ~/.openclaw/browser/openclaw/user-data/")

    if args.check:
        print("\nRunning session status check...\n")
        from tools.session_status import main as status_main
        return status_main()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
