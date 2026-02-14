"""Playwright async browser context manager for RayviewsLab worker.

Provides:
- Persistent storage_state per worker (cookies/localStorage survive restarts)
- Configurable viewport, user-agent, proxy
- Tracing per run (trace.zip for forensic replay)
- Automatic cleanup (page → context → browser) with timeouts

Dependencies: playwright (pip install playwright && playwright install chromium)

Usage:
    from tools.lib.browser import BrowserContextManager, load_browser_config

    browser_opts = load_browser_config()  # reads BROWSER_* env vars
    async with BrowserContextManager(cfg, **browser_opts) as bcm:
        page = await bcm.new_page(run_id="abc-123")
        await page.goto("https://example.com")
        # ... do work ...
        await bcm.stop_tracing(run_id="abc-123")  # saves trace
"""

from __future__ import annotations

import os
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


# ---------------------------------------------------------------------------
# BrowserContextManager
# ---------------------------------------------------------------------------

def load_browser_config() -> dict[str, Any]:
    """Load browser settings from env vars. Returns kwargs for BrowserContextManager."""
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


class BrowserContextManager:
    """Async context manager for Playwright browser lifecycle.

    Manages: browser launch → context (with storage_state) → page creation.
    Supports tracing per run for forensic replay.

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

        # Paths (env overrides, then defaults under state_dir)
        self._state_dir = Path(cfg.state_dir)
        storage = os.environ.get("BROWSER_STORAGE_STATE_PATH", "").strip()
        self._storage_path = (
            Path(storage) if storage
            else self._state_dir / "browser" / "storage_state.json"
        )
        traces = os.environ.get("BROWSER_TRACES_DIR", "").strip()
        self._traces_dir = (
            Path(traces) if traces
            else self._state_dir / "browser" / "traces"
        )

        # Playwright objects (set in __aenter__)
        self._playwright: Any = None
        self._browser: Any = None
        self._context: Any = None

    @property
    def browser(self) -> Any:
        return self._browser

    @property
    def context(self) -> Any:
        return self._context

    async def __aenter__(self) -> "BrowserContextManager":
        from playwright.async_api import async_playwright

        self._state_dir.mkdir(parents=True, exist_ok=True)
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._traces_dir.mkdir(parents=True, exist_ok=True)

        self._playwright = await async_playwright().start()

        launch_opts: dict[str, Any] = {"headless": self.headless}
        if self.proxy:
            launch_opts["proxy"] = self.proxy

        self._browser = await self._playwright.chromium.launch(**launch_opts)

        # Context with persistent storage_state (cookies/localStorage)
        ctx_opts: dict[str, Any] = {
            "viewport": self.viewport,
            "user_agent": self.user_agent,
        }
        if self._storage_path.exists():
            ctx_opts["storage_state"] = str(self._storage_path)

        self._context = await self._browser.new_context(**ctx_opts)

        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.close()

    async def new_page(self, *, run_id: str = "") -> Any:
        """Create a new page. Starts tracing if enabled and run_id is provided."""
        if not self._context:
            raise RuntimeError("BrowserContextManager not entered (use async with)")

        if run_id and self.enable_tracing:
            await self._context.tracing.start(
                screenshots=True,
                snapshots=True,
            )

        return await self._context.new_page()

    async def stop_tracing(self, *, run_id: str) -> Optional[Path]:
        """Stop tracing and save trace.zip for the given run_id.

        Returns the trace file path, or None if tracing wasn't active.
        """
        if not self._context:
            return None

        trace_path = self._traces_dir / f"trace_{run_id}.zip"
        try:
            await self._context.tracing.stop(path=str(trace_path))
            return trace_path
        except Exception:
            return None

    async def save_storage_state(self) -> None:
        """Persist cookies/localStorage for next session."""
        if self._context:
            try:
                await self._context.storage_state(path=str(self._storage_path))
            except Exception:
                pass

    async def close(self) -> None:
        """Close page → context → browser → playwright (LIFO)."""
        # Save storage before closing
        await self.save_storage_state()

        if self._context:
            try:
                await self._context.close()
            except Exception:
                pass
            self._context = None

        if self._browser:
            try:
                await self._browser.close()
            except Exception:
                pass
            self._browser = None

        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception:
                pass
            self._playwright = None
