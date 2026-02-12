"""Preflight session checks for browser-dependent pipeline stages.

Before running verify/assets stages, check that:
1. Brave browser is running and reachable via CDP
2. Required service sessions are logged in

Stdlib only (+ Playwright imported lazily).
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field


@dataclass
class PreflightResult:
    passed: bool
    failures: list[str] = field(default_factory=list)


# Which stages need which service sessions
STAGE_SESSIONS: dict[str, list[str]] = {
    "research": [],              # Google search doesn't need login
    "verify": ["amazon"],        # PDP + SiteStripe
    "assets": ["dzine"],         # Dzine generation
}

# Login check config: navigate to URL, if logged_out_selector visible → not logged in
LOGIN_CHECKS: dict[str, dict[str, str]] = {
    "amazon": {
        "url": "https://www.amazon.com/gp/css/homepage.html",
        "logged_out_selector": "#nav-link-accountList[data-nav-ref='nav_ya_signin']",
        "name": "Amazon",
    },
    "dzine": {
        "url": "https://www.dzine.ai/dashboard",
        "logged_out_selector": "text=Sign In, text=Log In, a[href*='login']",
        "name": "Dzine",
    },
}


def _is_browser_running() -> bool:
    """Check if Brave browser is reachable via CDP."""
    try:
        from tools.lib.brave_profile import connect_or_launch
        browser, context, should_close, pw = connect_or_launch(headless=False)
        if should_close:
            context.close()
        pw.stop()
        return True
    except Exception:
        return False


def preflight_check(stage: str, *, timeout_ms: int = 5000) -> PreflightResult:
    """Run preflight checks for a pipeline stage.

    Returns PreflightResult with passed=True if all checks pass.
    """
    required_sessions = STAGE_SESSIONS.get(stage, [])

    if not required_sessions:
        return PreflightResult(passed=True)

    # Check browser is running
    if not _is_browser_running():
        return PreflightResult(
            passed=False,
            failures=["Brave browser not running or unreachable via CDP. "
                       "Launch Brave with: open -a 'Brave Browser'"],
        )

    # Check each required session
    failures: list[str] = []
    try:
        from tools.lib.brave_profile import connect_or_launch
        browser, context, should_close, pw = connect_or_launch(headless=False)
        page = context.new_page()
        try:
            for service in required_sessions:
                check = LOGIN_CHECKS.get(service)
                if not check:
                    continue
                try:
                    page.goto(check["url"], wait_until="domcontentloaded",
                              timeout=timeout_ms)
                    page.wait_for_timeout(2000)

                    # Check if any logged_out_selector is visible
                    selectors = [s.strip() for s in check["logged_out_selector"].split(",")]
                    logged_out = False
                    for sel in selectors:
                        try:
                            if page.locator(sel).first.is_visible(timeout=2000):
                                logged_out = True
                                break
                        except Exception:
                            continue

                    if logged_out:
                        failures.append(
                            f"Not logged in to {check['name']}. "
                            f"Log in at {check['url']}"
                        )
                except Exception as exc:
                    failures.append(
                        f"Could not check {check['name']} session: {exc}"
                    )
        finally:
            page.close()
            if should_close:
                context.close()
            pw.stop()
    except Exception as exc:
        failures.append(f"Browser connection failed: {exc}")

    return PreflightResult(
        passed=len(failures) == 0,
        failures=failures,
    )
