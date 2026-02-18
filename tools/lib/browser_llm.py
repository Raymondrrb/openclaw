"""Browser-based LLM client — sends prompts via logged-in Claude.ai / ChatGPT.

Connects to the orange Brave via CDP (same pattern as brave_profile.py),
opens a new chat, pastes the prompt, waits for the response, and extracts text.

Browser-first approach: uses the user's logged-in sessions instead of API keys.
Falls back gracefully so callers can try API when this fails.

Requires Playwright (lazy import, same as other browser modules).
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class BrowserLLMResult:
    """Result of a browser-based LLM prompt."""
    success: bool
    text: str = ""
    provider: str = ""       # "claude" or "chatgpt"
    duration_s: float = 0.0
    error: str = ""


# ---------------------------------------------------------------------------
# Selector maps per provider
# ---------------------------------------------------------------------------

# Each provider maps logical roles to CSS selectors (tried in order).
SELECTORS: dict[str, dict[str, list[str]]] = {
    "claude": {
        "input": [
            "div[contenteditable='true'].ProseMirror",
            "div[contenteditable='true'][data-placeholder]",
        ],
        "send": [
            "button[aria-label='Send Message']",
            "button[aria-label='Send message']",
        ],
        "streaming": [
            "button[aria-label='Stop Response']",
            "button[aria-label='Stop response']",
        ],
        "response": [
            ".font-claude-message",
        ],
        "logged_in": [
            "button[data-testid='user-menu']",
            "img[alt*='Avatar']",
            "button[aria-label='Open menu']",
        ],
    },
    "chatgpt": {
        "input": [
            "#prompt-textarea",
            "div[contenteditable='true'][data-id='root']",
        ],
        "send": [
            "button[data-testid='send-button']",
            "button[aria-label='Send prompt']",
        ],
        "streaming": [
            "button[data-testid='stop-button']",
            "button[aria-label='Stop generating']",
        ],
        "response": [
            "[data-message-author-role='assistant']",
        ],
        "logged_in": [
            "button[data-testid='profile-button']",
            "img[alt='User']",
            "button[aria-label='Open sidebar']",
        ],
    },
}

# New-chat URLs
NEW_CHAT_URLS: dict[str, str] = {
    "claude": "https://claude.ai/new",
    "chatgpt": "https://chatgpt.com/",
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _find_first(page, selectors: list[str], *, timeout: int = 5000):
    """Try selectors in order, return the first visible element or None."""
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            loc.wait_for(state="visible", timeout=timeout)
            return loc
        except Exception:
            continue
    return None


def _is_logged_in(page, provider: str, *, timeout: int = 8000) -> bool:
    """Check if the user is logged in by looking for avatar/menu elements."""
    sels = SELECTORS.get(provider, {}).get("logged_in", [])
    return _find_first(page, sels, timeout=timeout) is not None


def _start_new_chat(page, provider: str, *, timeout: int = 15000) -> bool:
    """Navigate to a new chat page. Returns True if loaded."""
    url = NEW_CHAT_URLS.get(provider, "")
    if not url:
        return False
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=timeout)
        return True
    except Exception:
        return False


def _send_prompt(page, provider: str, prompt: str, *, timeout: int = 10000) -> bool:
    """Focus the input, paste text via JS evaluate, and click Send.

    Both Claude and ChatGPT use ProseMirror (contenteditable).
    Playwright's fill() doesn't work reliably on these — we use JS to
    set innerHTML and dispatch an InputEvent so the app detects content.
    """
    input_sels = SELECTORS.get(provider, {}).get("input", [])
    input_el = _find_first(page, input_sels, timeout=timeout)
    if not input_el:
        return False

    # Get the actual selector that matched for JS evaluation
    input_selector = None
    for sel in input_sels:
        try:
            if page.locator(sel).first.is_visible():
                input_selector = sel
                break
        except Exception:
            continue

    if not input_selector:
        return False

    # Inject text via JS — works for both ProseMirror and regular contenteditable
    escaped_text = prompt.replace("\\", "\\\\").replace("`", "\\`").replace("$", "\\$")
    js_inject = f"""
    (() => {{
        const el = document.querySelector("{input_selector}");
        if (!el) return false;
        el.focus();
        // For ProseMirror contenteditable
        if (el.getAttribute('contenteditable') === 'true') {{
            el.innerHTML = '<p>' + `{escaped_text}`.replace(/\\n/g, '</p><p>') + '</p>';
        }} else {{
            // For textarea/input
            el.value = `{escaped_text}`;
        }}
        el.dispatchEvent(new Event('input', {{ bubbles: true }}));
        el.dispatchEvent(new Event('change', {{ bubbles: true }}));
        return true;
    }})()
    """
    try:
        result = page.evaluate(js_inject)
        if not result:
            return False
    except Exception:
        return False

    # Small delay for the app to process the input event
    time.sleep(0.5)

    # Click Send
    send_sels = SELECTORS.get(provider, {}).get("send", [])
    send_btn = _find_first(page, send_sels, timeout=timeout)
    if not send_btn:
        # Try pressing Enter as fallback
        try:
            page.keyboard.press("Enter")
        except Exception:
            return False
    else:
        try:
            send_btn.click()
        except Exception:
            return False

    return True


def _wait_for_response(page, provider: str, *, timeout_s: int = 180) -> bool:
    """Wait for the LLM response to complete.

    Dual signal approach:
    1. Stop/streaming button disappears (streaming finished)
    2. Response text stabilizes (no changes for 6s = 3 checks x 2s)
    """
    streaming_sels = SELECTORS.get(provider, {}).get("streaming", [])
    response_sels = SELECTORS.get(provider, {}).get("response", [])
    deadline = time.time() + timeout_s

    # Phase 1: Wait for streaming to start (stop button appears)
    # Give it up to 30s to start generating
    start_deadline = time.time() + 30
    streaming_started = False
    while time.time() < start_deadline:
        for sel in streaming_sels:
            try:
                if page.locator(sel).first.is_visible(timeout=500):
                    streaming_started = True
                    break
            except Exception:
                continue
        if streaming_started:
            break
        # Also check if a response already appeared (fast response)
        for sel in response_sels:
            try:
                count = page.locator(sel).count()
                if count > 0:
                    streaming_started = True
                    break
            except Exception:
                continue
        if streaming_started:
            break
        time.sleep(1)

    if not streaming_started:
        return False

    # Phase 2: Wait for streaming to finish (stop button disappears)
    while time.time() < deadline:
        stop_visible = False
        for sel in streaming_sels:
            try:
                if page.locator(sel).first.is_visible(timeout=500):
                    stop_visible = True
                    break
            except Exception:
                continue
        if not stop_visible:
            break
        time.sleep(2)

    if time.time() >= deadline:
        return False

    # Phase 3: Verify text has stabilized (3 checks x 2s = 6s)
    last_text = ""
    stable_count = 0
    for _ in range(10):  # max 20s of stability checks
        current = _extract_response_text(page, provider)
        if current and current == last_text:
            stable_count += 1
            if stable_count >= 3:
                return True
        else:
            stable_count = 0
            last_text = current
        time.sleep(2)

    # If we got text even without perfect stability, accept it
    return bool(last_text)


def _extract_response_text(page, provider: str) -> str:
    """Extract the last assistant message text via JS page.evaluate()."""
    response_sels = SELECTORS.get(provider, {}).get("response", [])

    for sel in response_sels:
        try:
            js_extract = f"""
            (() => {{
                const msgs = document.querySelectorAll("{sel}");
                if (msgs.length === 0) return "";
                const last = msgs[msgs.length - 1];
                return last.innerText || last.textContent || "";
            }})()
            """
            text = page.evaluate(js_extract)
            if text and text.strip():
                return text.strip()
        except Exception:
            continue

    return ""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def send_prompt_via_browser(
    prompt: str,
    *,
    provider: str = "claude",
    timeout_s: int = 180,
) -> BrowserLLMResult:
    """Send a prompt via the browser to Claude.ai or ChatGPT.

    Connects to the orange Brave via CDP, opens a new chat tab,
    pastes the prompt, waits for the response, and extracts text.

    Args:
        prompt: The full prompt text to send.
        provider: "claude" or "chatgpt".
        timeout_s: Max seconds to wait for response generation.

    Returns:
        BrowserLLMResult with success/text/error.
    """
    if provider not in SELECTORS:
        return BrowserLLMResult(
            success=False, provider=provider,
            error=f"Unknown provider: {provider}",
        )

    start = time.time()
    browser = None
    page = None
    pw = None
    should_close = False

    try:
        from tools.lib.brave_profile import connect_or_launch

        browser, context, should_close, pw = connect_or_launch()
        page = context.new_page()

        # Navigate to new chat
        print(f"  [browser-llm] Opening {provider} new chat...", file=sys.stderr)
        if not _start_new_chat(page, provider):
            return BrowserLLMResult(
                success=False, provider=provider,
                duration_s=time.time() - start,
                error=f"Failed to load {provider} new chat page",
            )

        # Check login
        if not _is_logged_in(page, provider):
            return BrowserLLMResult(
                success=False, provider=provider,
                duration_s=time.time() - start,
                error=f"Not logged in to {provider}",
            )

        # Send prompt
        print(f"  [browser-llm] Sending prompt ({len(prompt)} chars)...", file=sys.stderr)
        if not _send_prompt(page, provider, prompt):
            return BrowserLLMResult(
                success=False, provider=provider,
                duration_s=time.time() - start,
                error=f"Failed to send prompt to {provider}",
            )

        # Wait for response
        print(f"  [browser-llm] Waiting for {provider} response (max {timeout_s}s)...", file=sys.stderr)
        if not _wait_for_response(page, provider, timeout_s=timeout_s):
            return BrowserLLMResult(
                success=False, provider=provider,
                duration_s=time.time() - start,
                error=f"Response timeout or failed for {provider}",
            )

        # Extract response
        text = _extract_response_text(page, provider)
        if not text:
            return BrowserLLMResult(
                success=False, provider=provider,
                duration_s=time.time() - start,
                error=f"Empty response from {provider}",
            )

        duration = time.time() - start
        print(f"  [browser-llm] Got response: {len(text)} chars in {duration:.1f}s", file=sys.stderr)

        return BrowserLLMResult(
            success=True,
            text=text,
            provider=provider,
            duration_s=duration,
        )

    except ImportError:
        return BrowserLLMResult(
            success=False, provider=provider,
            duration_s=time.time() - start,
            error="Playwright not installed",
        )
    except Exception as exc:
        return BrowserLLMResult(
            success=False, provider=provider,
            duration_s=time.time() - start,
            error=f"Browser error: {exc}",
        )
    finally:
        # Close only the tab we opened, not the shared browser
        if page:
            try:
                page.close()
            except Exception:
                pass
        if should_close and browser:
            try:
                browser.close()
            except Exception:
                pass
        if should_close and pw:
            try:
                pw.stop()
            except Exception:
                pass
