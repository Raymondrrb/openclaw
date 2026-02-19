"""Orange Brave profile management, CDP connection, and safety guardrails.

The "orange Brave" is OpenClaw's managed browser profile:
- Profile path: ~/.openclaw/browser/openclaw/user-data/
- CDP port: 18800 (default)
- Color: #FF4500 (lobster-orange)
- Launched by OpenClaw with --user-data-dir pointing at that path

This module provides:
- Connection to the running orange Brave via CDP
- Fallback launch when the browser isn't running
- Domain allowlist enforcement
- Download directory restrictions
- Non-sensitive logging helpers
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Profile location (matches OpenClaw's resolveOpenClawUserDataDir)
OPENCLAW_CONFIG_DIR = Path.home() / ".openclaw"
PROFILE_DIR = OPENCLAW_CONFIG_DIR / "browser" / "openclaw" / "user-data"

# CDP connection
DEFAULT_CDP_PORT = 18800
CDP_URL = f"http://127.0.0.1:{DEFAULT_CDP_PORT}"

# Brave executable (read from OpenClaw config, fallback to common paths)
_BRAVE_PATHS_MACOS = [
    "/Applications/Brave Browser 2.app/Contents/MacOS/Brave Browser",
    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
]

# Domain allowlist — only these domains may be navigated to
ALLOWED_DOMAINS = frozenset({
    "youtube.com",
    "www.youtube.com",
    "amazon.com",
    "www.amazon.com",
    "github.com",
    "www.github.com",
    "vercel.com",
    "www.vercel.com",
    "supabase.com",
    "www.supabase.com",
    "app.supabase.com",
    "elevenlabs.io",
    "www.elevenlabs.io",
    "dzine.ai",
    "www.dzine.ai",
    # LLM providers (for browser-based script generation)
    "claude.ai", "www.claude.ai",
    "chatgpt.com", "www.chatgpt.com",
    "chat.openai.com",
    # Review sources (for research agent)
    "google.com",
    "www.google.com",
    "nytimes.com",
    "www.nytimes.com",
    "rtings.com",
    "www.rtings.com",
    "tomsguide.com",
    "www.tomsguide.com",
    "pcmag.com",
    "www.pcmag.com",
    "theverge.com",
    "www.theverge.com",
    "cnet.com",
    "www.cnet.com",
    "techradar.com",
    "www.techradar.com",
    "goodhousekeeping.com",
    "www.goodhousekeeping.com",
    "popularmechanics.com",
    "www.popularmechanics.com",
})

# Action allowlist — only these tools are exposed
ALLOWED_ACTIONS = frozenset({
    "open_login_workspace",
    "check_session_status",
    "dzine_generate_image",
    "amazon_search_and_extract",
})

# All downloads go here
DOWNLOADS_DIR = Path(__file__).resolve().parent.parent.parent / "artifacts"

# Sites to check for login status (url + logged-in / logged-out selectors)
LOGIN_CHECKS: dict[str, dict] = {
    "youtube": {
        "url": "https://www.youtube.com/",
        "logged_in": 'button#avatar-btn, img#img[alt*="Avatar"], ytd-topbar-menu-button-renderer img',
        "logged_out": 'a[href*="accounts.google.com/ServiceLogin"], ytd-button-renderer a[aria-label="Sign in"], tp-yt-paper-button#button[aria-label="Sign in"]',
    },
    "amazon": {
        "url": "https://www.amazon.com/",
        "logged_in": '#nav-link-accountList span.nav-line-1:not(:has-text("Hello, sign in"))',
        "logged_out": '#nav-link-accountList span:has-text("Hello, sign in"), #nav-link-accountList span:has-text("Sign in")',
    },
    "github": {
        "url": "https://github.com/",
        "logged_in": '[data-testid="github-avatar"], img[alt="User avatar"], img.avatar',
        "logged_out": 'a[href="/login"], a[href="/signup"]',
    },
    "vercel": {
        "url": "https://vercel.com/dashboard",
        "logged_in": '[data-testid="avatar-popover/trigger"], button[aria-label="Menu"]',
        "logged_out": 'a[href="/login"], a[href*="login"], form[action*="login"]',
    },
    "supabase": {
        "url": "https://supabase.com/dashboard",
        "logged_in": 'button[data-state], [data-testid="user-menu"], img[alt*="avatar"]',
        "logged_out": 'a[href*="sign-in"], input[type="email"], form[action*="auth"]',
    },
    "elevenlabs": {
        "url": "https://elevenlabs.io/app/voice-lab",
        "logged_in": '[data-testid="user-menu-button"], button[aria-label="Your profile"]',
        "logged_out": 'a[href*="sign-in"], a[href*="login"], button:has-text("Sign in"), input[type="email"]',
    },
    "dzine": {
        "url": "https://www.dzine.ai/canvas?id=19797967",
        "logged_in": 'button:has-text("Dashboard")',
        "logged_out": 'button:has-text("Log in"), button:has-text("Sign in"), a[href*="login"]',
    },
}

# Tab URLs for login workspace
LOGIN_WORKSPACE_URLS = [
    "https://www.youtube.com/",
    "https://www.amazon.com/",
    "https://www.dzine.ai/",
    "https://elevenlabs.io/",
    "https://supabase.com/dashboard",
    "https://vercel.com/dashboard",
    "https://github.com/",
]


# ---------------------------------------------------------------------------
# Domain safety
# ---------------------------------------------------------------------------


def is_domain_allowed(url: str) -> bool:
    """Check if a URL's domain is in the allowlist."""
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
        hostname = (parsed.hostname or "").lower()
        # Check exact match and parent domain
        return hostname in ALLOWED_DOMAINS or any(
            hostname.endswith(f".{d}") for d in ALLOWED_DOMAINS
        )
    except Exception:
        return False


def enforce_domain(url: str) -> None:
    """Raise if URL is not in the allowlist."""
    if not is_domain_allowed(url):
        raise PermissionError(f"Domain not allowed: {url}")


# ---------------------------------------------------------------------------
# CDP connection
# ---------------------------------------------------------------------------


def is_browser_running(port: int = DEFAULT_CDP_PORT, timeout: float = 1.0) -> bool:
    """Check if the orange Brave is reachable via CDP."""
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/json/version")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
            return bool(data.get("Browser"))
    except Exception:
        return False


def get_open_tabs(port: int = DEFAULT_CDP_PORT) -> list[dict]:
    """List currently open tabs via CDP."""
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/json/list")
        with urllib.request.urlopen(req, timeout=2) as resp:
            tabs = json.loads(resp.read())
            return [t for t in tabs if t.get("type") == "page"]
    except Exception:
        return []


def resolve_brave_executable() -> str | None:
    """Find the Brave executable path."""
    # Try OpenClaw config first
    config_path = OPENCLAW_CONFIG_DIR / "openclaw.json"
    if config_path.is_file():
        try:
            config = json.loads(config_path.read_text())
            exe = config.get("browser", {}).get("executablePath", "")
            if exe and Path(exe).is_file():
                return exe
        except Exception:
            pass

    # Fallback to known macOS paths
    for p in _BRAVE_PATHS_MACOS:
        if Path(p).is_file():
            return p

    return None


# ---------------------------------------------------------------------------
# Playwright helpers (connect or launch)
# ---------------------------------------------------------------------------


def connect_or_launch(*, headless: bool = False):
    """Connect to the running orange Brave via CDP, or launch it.

    Returns a Playwright (browser, context, should_close) tuple.
    - If connected via CDP: should_close=False (don't kill the shared browser)
    - If launched fresh: should_close=True
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise RuntimeError(
            "playwright not installed. Run: pip install playwright && playwright install chromium"
        )

    pw = sync_playwright().start()

    # Try to connect to the already-running browser
    if is_browser_running():
        try:
            browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{DEFAULT_CDP_PORT}")
            contexts = browser.contexts
            if not contexts:
                # Never create ephemeral context — it loses cookies (ChatGPT logout bug)
                raise RuntimeError("CDP connected but no browser contexts found")
            context = contexts[0]
            return browser, context, False, pw
        except Exception as exc:
            print(f"[brave] CDP connect failed ({exc}), launching fresh", file=sys.stderr)

    # Fallback: launch Brave with the persistent profile
    exe = resolve_brave_executable()
    if not exe:
        pw.stop()
        raise RuntimeError("Brave Browser not found")

    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    context = pw.chromium.launch_persistent_context(
        str(PROFILE_DIR),
        executable_path=exe,
        headless=headless,
        viewport={"width": 1440, "height": 900},
        accept_downloads=True,
        args=[
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-sync",
            "--disable-blink-features=AutomationControlled",
        ],
    )
    # Persistent context has no separate browser object
    return None, context, True, pw


# ---------------------------------------------------------------------------
# Logging (non-sensitive)
# ---------------------------------------------------------------------------


def log_action(action: str, details: str = "") -> None:
    """Log a browser action (never logs cookies, tokens, or page HTML)."""
    from tools.lib.common import now_iso
    ts = now_iso()
    msg = f"[{ts}] browser:{action}"
    if details:
        msg += f" {details}"
    print(msg, file=sys.stderr)
