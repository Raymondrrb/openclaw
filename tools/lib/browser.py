"""Playwright async browser session for RayviewsLab worker.

Provides:
- Profile-based storage_state (persistent login per service: dzine, chatgpt, claude)
- Configurable viewport, user-agent, proxy
- Tracing per run (trace.zip for forensic replay)
- Screenshot + trace capture on error (debug artifacts)
- Automatic cleanup (page → context → browser) with timeouts

Dependencies: playwright (pip install playwright && playwright install chromium)

Usage:
    from tools.lib.browser import BrowserSession, load_browser_config

    browser_opts = load_browser_config()  # reads BROWSER_* env vars
    async with BrowserSession(cfg, **browser_opts) as session:
        page = await session.new_page(run_id="abc-123", profile="dzine")
        await page.goto("https://www.dzine.ai/")
        # ... do work ...
        await session.stop_tracing(run_id="abc-123")  # saves trace

    # On error, capture debug artifacts:
    await session.capture_debug_artifacts(run_id="abc-123", tag="dzine_timeout")
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from tools.lib.config import WorkerConfig


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_VIEWPORT = {"width": 1280, "height": 800}
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# Known service profiles — each gets its own storage_state JSON
KNOWN_PROFILES = ("default", "dzine", "chatgpt", "claude")


# ---------------------------------------------------------------------------
# Config loader
# ---------------------------------------------------------------------------

def load_browser_config() -> dict[str, Any]:
    """Load browser settings from env vars. Returns kwargs for BrowserSession."""
    opts: dict[str, Any] = {}

    headless = os.environ.get("BROWSER_HEADLESS", "true").lower()
    opts["headless"] = headless not in ("false", "0", "no")

    ua = os.environ.get("BROWSER_USER_AGENT", "").strip()
    if ua:
        opts["user_agent"] = ua

    proxy = os.environ.get("BROWSER_PROXY_SERVER", "").strip()
    if proxy:
        opts["proxy"] = {"server": proxy}

    return opts


# ---------------------------------------------------------------------------
# BrowserSession (upgraded from BrowserContextManager)
# ---------------------------------------------------------------------------

class BrowserSession:
    """Async context manager for Playwright browser lifecycle.

    Manages: browser launch → context (with profile-based storage_state)
    → page creation → debug artifact capture → LIFO cleanup.

    Profile-based storage_state:
      Each service (dzine, chatgpt, claude) gets its own storage_state JSON
      so cookies/login persist independently per service.

    Debug artifacts:
      On error, call capture_debug_artifacts() to save screenshot + trace
      for forensic debugging. Files go to state/browser/debug/{tag}_{timestamp}.

    Browser settings can come from:
    1. Constructor kwargs (highest priority)
    2. Environment variables (BROWSER_*)
    3. Defaults
    """

    def __init__(
        self,
        cfg: WorkerConfig,
        *,
        headless: bool = True,
        viewport: dict[str, int] | None = None,
        user_agent: str = DEFAULT_USER_AGENT,
        proxy: dict[str, str] | None = None,
        enable_tracing: bool | None = None,
    ):
        self.cfg = cfg
        self.headless = headless
        self.viewport = viewport or DEFAULT_VIEWPORT
        self.user_agent = user_agent
        self.proxy = proxy
        self.enable_tracing = enable_tracing if enable_tracing is not None else (
            os.environ.get("BROWSER_ENABLE_TRACING", "false").lower()
            in ("true", "1", "yes")
        )

        # Paths
        self._state_dir = Path(cfg.state_dir)
        self._browser_dir = self._state_dir / "browser"
        self._profiles_dir = self._browser_dir / "profiles"
        traces = os.environ.get("BROWSER_TRACES_DIR", "").strip()
        self._traces_dir = (
            Path(traces) if traces
            else self._browser_dir / "traces"
        )
        self._debug_dir = self._browser_dir / "debug"

        # Playwright objects (set in __aenter__)
        self._playwright: Any = None
        self._browser: Any = None
        self._contexts: dict[str, Any] = {}  # profile → context
        self._active_pages: dict[str, Any] = {}  # run_id → page

    @property
    def browser(self) -> Any:
        return self._browser

    @property
    def context(self) -> Any:
        """Default context (backward compat with BrowserContextManager)."""
        return self._contexts.get("default")

    def _storage_path(self, profile: str) -> Path:
        """Get storage_state path for a service profile."""
        return self._profiles_dir / f"{profile}.json"

    async def __aenter__(self) -> "BrowserSession":
        from playwright.async_api import async_playwright

        self._browser_dir.mkdir(parents=True, exist_ok=True)
        self._profiles_dir.mkdir(parents=True, exist_ok=True)
        self._traces_dir.mkdir(parents=True, exist_ok=True)
        self._debug_dir.mkdir(parents=True, exist_ok=True)

        self._playwright = await async_playwright().start()

        launch_opts: dict[str, Any] = {"headless": self.headless}
        if self.proxy:
            launch_opts["proxy"] = self.proxy

        self._browser = await self._playwright.chromium.launch(**launch_opts)

        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()

    async def _get_or_create_context(self, profile: str) -> Any:
        """Get existing context for profile or create one with storage_state."""
        if profile in self._contexts:
            return self._contexts[profile]

        if not self._browser:
            raise RuntimeError("BrowserSession not entered (use async with)")

        ctx_opts: dict[str, Any] = {
            "viewport": self.viewport,
            "user_agent": self.user_agent,
        }
        storage = self._storage_path(profile)
        if storage.exists():
            ctx_opts["storage_state"] = str(storage)

        context = await self._browser.new_context(**ctx_opts)
        self._contexts[profile] = context
        return context

    async def new_page(
        self,
        *,
        run_id: str = "",
        profile: str = "default",
    ) -> Any:
        """Create a new page for a given profile.

        Args:
            run_id: Run identifier (used for tracing filename).
            profile: Service profile name (dzine, chatgpt, claude, default).
                     Each profile has its own storage_state (cookies/login).

        Returns:
            Playwright Page instance.
        """
        context = await self._get_or_create_context(profile)

        if run_id and self.enable_tracing:
            try:
                await context.tracing.start(
                    screenshots=True,
                    snapshots=True,
                )
            except Exception:
                pass  # tracing may already be active

        page = await context.new_page()
        if run_id:
            self._active_pages[run_id] = page
        return page

    async def stop_tracing(self, *, run_id: str) -> Optional[Path]:
        """Stop tracing and save trace.zip for the given run_id.

        Returns the trace file path, or None if tracing wasn't active.
        """
        # Find which context has this page
        page = self._active_pages.get(run_id)
        if not page:
            # Fallback: try default context
            ctx = self._contexts.get("default")
            if not ctx:
                return None
        else:
            ctx = None
            for context in self._contexts.values():
                try:
                    if page in context.pages:
                        ctx = context
                        break
                except Exception:
                    pass
            if not ctx:
                return None

        trace_path = self._traces_dir / f"trace_{run_id}.zip"
        try:
            await ctx.tracing.stop(path=str(trace_path))
            return trace_path
        except Exception:
            return None

    async def capture_debug_artifacts(
        self,
        *,
        run_id: str,
        tag: str = "error",
        page: Any = None,
    ) -> dict[str, str]:
        """Capture screenshot + trace for debugging.

        Called on errors to preserve evidence for forensic analysis.

        Args:
            run_id: Run identifier.
            tag: Short label for the error context (e.g. "dzine_timeout").
            page: Playwright page (if None, uses active page for run_id).

        Returns:
            Dict with paths to captured artifacts: {"screenshot": ..., "trace": ...}
        """
        artifacts: dict[str, str] = {}
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        prefix = f"{stamp}_{tag}_{run_id[-8:]}" if run_id else f"{stamp}_{tag}"

        target_page = page or self._active_pages.get(run_id)

        # Screenshot
        if target_page:
            try:
                ss_path = self._debug_dir / f"{prefix}_screenshot.png"
                await target_page.screenshot(path=str(ss_path), full_page=True)
                artifacts["screenshot"] = str(ss_path)
            except Exception:
                pass

        # Trace (stop current tracing and save)
        trace_path = self._debug_dir / f"{prefix}_trace.zip"
        for ctx in self._contexts.values():
            try:
                await ctx.tracing.stop(path=str(trace_path))
                artifacts["trace"] = str(trace_path)
                break
            except Exception:
                pass

        return artifacts

    async def save_storage_state(self, profile: str = "") -> None:
        """Persist cookies/localStorage for profile(s).

        If profile is empty, saves all active contexts.
        """
        profiles = [profile] if profile else list(self._contexts.keys())
        for p in profiles:
            ctx = self._contexts.get(p)
            if ctx:
                try:
                    await ctx.storage_state(path=str(self._storage_path(p)))
                except Exception:
                    pass

    async def close(self) -> None:
        """Close all pages → contexts → browser → playwright (LIFO).

        Saves storage_state for all profiles before closing.
        Uses shielded timeouts to prevent hanging.
        """
        # Save all profiles before closing
        await self.save_storage_state()

        # Close pages first
        for run_id, page in list(self._active_pages.items()):
            try:
                await asyncio.wait_for(page.close(), timeout=3.0)
            except Exception:
                pass
        self._active_pages.clear()

        # Close contexts (LIFO order — most recent first)
        for profile in list(reversed(list(self._contexts.keys()))):
            ctx = self._contexts.pop(profile, None)
            if ctx:
                try:
                    await asyncio.wait_for(ctx.close(), timeout=3.0)
                except Exception:
                    pass

        if self._browser:
            try:
                await asyncio.wait_for(self._browser.close(), timeout=5.0)
            except Exception:
                pass
            self._browser = None

        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception:
                pass
            self._playwright = None


# ---------------------------------------------------------------------------
# Backward compatibility alias
# ---------------------------------------------------------------------------

BrowserContextManager = BrowserSession
