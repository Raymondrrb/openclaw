"""WebChatAgent — Playwright-based LLM interaction via browser UI.

Operates ChatGPT or Claude through their web interfaces using:
- Profile-based storage_state (persistent login per service)
- Robust input strategy: textarea → role textbox → fallback
- Stability detection: waits for response to stop changing
- Session expiry detection: returns needs_login=True

Does NOT depend on fragile CSS selectors — uses roles, labels, textarea.

Dependencies: playwright (pip install playwright && playwright install chromium)

Usage:
    from tools.agents.webchat_agent import WebChatAgent, WebChatTarget

    target = WebChatTarget.CHATGPT  # or WebChatTarget.CLAUDE
    agent = WebChatAgent(browser_cfg, target)
    result = await agent.generate_text(run_id="abc", prompt="Write a hook...")
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Targets
# ---------------------------------------------------------------------------

class WebChatTarget(str, Enum):
    """Supported web chat services."""
    CHATGPT = "chatgpt"
    CLAUDE = "claude"


@dataclass(frozen=True)
class WebChatTargetConfig:
    """Configuration for a specific chat service."""
    name: str
    url: str
    profile: str                   # storage_state profile name
    input_role_hint: str = "textbox"
    login_indicators: tuple[str, ...] = ("Sign in", "Log in", "Sign up")
    ready_indicators: tuple[str, ...] = ("Send", "New chat")


# Pre-built configs for supported services
TARGET_CONFIGS = {
    WebChatTarget.CHATGPT: WebChatTargetConfig(
        name="ChatGPT",
        url="https://chatgpt.com/",
        profile="chatgpt",
        input_role_hint="textbox",
        login_indicators=("Log in", "Sign up", "Welcome to ChatGPT"),
        ready_indicators=("Send", "Message ChatGPT"),
    ),
    WebChatTarget.CLAUDE: WebChatTargetConfig(
        name="Claude",
        url="https://claude.ai/new",
        profile="claude",
        input_role_hint="textbox",
        login_indicators=("Sign in", "Log in", "Create account"),
        ready_indicators=("Send", "Reply to Claude"),
    ),
}


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------

@dataclass
class WebChatResult:
    """Result from a web chat interaction."""
    text: str                     # extracted response text
    success: bool                 # True if we got a non-empty response
    needs_login: bool = False     # True if session expired
    stable_ticks: int = 0         # how many stability checks passed
    error: str = ""               # error message if failed


# ---------------------------------------------------------------------------
# WebChatAgent
# ---------------------------------------------------------------------------

class WebChatAgent:
    """Playwright-based agent for interacting with ChatGPT/Claude via browser.

    Uses BrowserSession from tools.lib.browser for lifecycle management.
    Profile-based storage_state keeps login between runs.

    Flow:
    1. Open chat URL
    2. Check for login wall → return needs_login if found
    3. Find input element (textarea or role textbox)
    4. Type prompt + send (button or Enter)
    5. Wait for response stability (body text stops changing)
    6. Extract response text
    """

    def __init__(self, target: WebChatTarget):
        self.target = target
        self.config = TARGET_CONFIGS[target]

    async def generate_text(
        self,
        page: Any,
        *,
        prompt: str,
        timeout_sec: int = 120,
        stability_threshold: int = 5,
    ) -> WebChatResult:
        """Send prompt and wait for response via browser page.

        Args:
            page: Playwright page (already navigated or will be navigated).
            prompt: Text to send to the chat.
            timeout_sec: Max wait for response.
            stability_threshold: Consecutive unchanged checks before accepting.

        Returns:
            WebChatResult with extracted text and status.
        """
        try:
            return await self._do_generate(
                page, prompt, timeout_sec, stability_threshold,
            )
        except Exception as e:
            return WebChatResult(
                text="", success=False,
                error=f"{type(e).__name__}: {e}",
            )

    async def _do_generate(
        self,
        page: Any,
        prompt: str,
        timeout_sec: int,
        stability_threshold: int,
    ) -> WebChatResult:
        """Internal: the actual generation flow."""
        # 1. Navigate to chat URL
        await page.goto(self.config.url, wait_until="domcontentloaded")
        await asyncio.sleep(2)  # let JS settle

        # 2. Check for login wall
        body_text = await page.inner_text("body")
        for indicator in self.config.login_indicators:
            if indicator.lower() in body_text.lower()[:2000]:
                # Check if it's really a login page (not just a button)
                # by looking for input fields too
                has_input = await self._has_input_element(page)
                if not has_input:
                    return WebChatResult(
                        text="", success=False, needs_login=True,
                        error=f"Session expired: '{indicator}' detected",
                    )

        # 3. Find input element
        input_el = await self._find_input(page)
        if not input_el:
            return WebChatResult(
                text="", success=False,
                error="Could not find chat input element",
            )

        # 4. Capture pre-send body snapshot (to detect new content)
        pre_body = await page.inner_text("body")
        pre_len = len(pre_body)

        # 5. Type prompt and send
        await input_el.click()
        await input_el.fill(prompt)
        await asyncio.sleep(0.3)

        sent = await self._send_message(page, input_el)
        if not sent:
            return WebChatResult(
                text="", success=False,
                error="Could not send message (no Send button, Enter failed)",
            )

        # 6. Wait for response stability
        await asyncio.sleep(3)  # initial wait for response to start
        text, stable_ticks = await self._wait_for_stability(
            page, pre_len, timeout_sec, stability_threshold,
        )

        if not text:
            return WebChatResult(
                text="", success=False, stable_ticks=stable_ticks,
                error="Response empty or timed out",
            )

        return WebChatResult(
            text=text, success=True,
            stable_ticks=stable_ticks,
        )

    async def _has_input_element(self, page: Any) -> bool:
        """Check if page has a chat input (textarea or textbox role)."""
        try:
            el = page.locator("textarea").first
            return await el.is_visible(timeout=3000)
        except Exception:
            pass
        try:
            el = page.get_by_role(self.config.input_role_hint).first
            return await el.is_visible(timeout=3000)
        except Exception:
            return False

    async def _find_input(self, page: Any) -> Optional[Any]:
        """Find the chat input element. Tries textarea first, then role."""
        # Strategy 1: textarea
        try:
            el = page.locator("textarea").first
            await el.wait_for(timeout=10_000)
            if await el.is_visible():
                return el
        except Exception:
            pass

        # Strategy 2: role textbox
        try:
            el = page.get_by_role(self.config.input_role_hint).first
            await el.wait_for(timeout=10_000)
            if await el.is_visible():
                return el
        except Exception:
            pass

        # Strategy 3: contenteditable div
        try:
            el = page.locator("[contenteditable=true]").first
            await el.wait_for(timeout=5_000)
            if await el.is_visible():
                return el
        except Exception:
            pass

        return None

    async def _send_message(self, page: Any, input_el: Any) -> bool:
        """Send the typed message. Tries Send button first, then Enter."""
        # Strategy 1: Send button by role
        try:
            send_btn = page.get_by_role("button", name="Send").first
            if await send_btn.is_visible(timeout=2000):
                await send_btn.click()
                return True
        except Exception:
            pass

        # Strategy 2: aria-label send
        try:
            send_btn = page.locator("[aria-label*='Send']").first
            if await send_btn.is_visible(timeout=2000):
                await send_btn.click()
                return True
        except Exception:
            pass

        # Strategy 3: Enter key
        try:
            await input_el.press("Enter")
            return True
        except Exception:
            return False

    async def _wait_for_stability(
        self,
        page: Any,
        pre_len: int,
        timeout_sec: int,
        threshold: int,
    ) -> tuple[str, int]:
        """Wait for page content to stabilize (response finished).

        Returns (extracted_text, stable_ticks).
        """
        loop = asyncio.get_event_loop()
        deadline = loop.time() + timeout_sec
        last_text = ""
        stable_count = 0

        while loop.time() < deadline:
            body = await page.inner_text("body")
            # Only look at new content (after what was there pre-send)
            new_content = body[pre_len:] if len(body) > pre_len else body[-6000:]
            tail = new_content[-6000:]

            if tail == last_text and tail:
                stable_count += 1
            else:
                stable_count = 0
                last_text = tail

            if stable_count >= threshold:
                return last_text.strip(), stable_count

            await asyncio.sleep(1.5)

        return last_text.strip(), stable_count
