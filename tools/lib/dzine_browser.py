"""Playwright-based Dzine image generation automation via canvas editor.

Drives the Dzine canvas UI at https://www.dzine.ai/canvas?id=<project_id>
using CDP connection to the orange Brave browser. Supports:
- Consistent Character (Ray) for thumbnail/avatar scenes
- Txt2Img for product images (with reference upload)
- Img2Img for style transfers on canvas images
- Async generation monitoring with progress tracking
- Result image download via URL fetch
- Retry with backoff on transient failures
- Login/session validation before generation

All interactions use JS evaluate + position-based clicks (CSS selectors
are fragile on Dzine's dynamic DOM). Viewport MUST be 1440x900.
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import struct
import sys
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from tools.lib.common import project_root
from tools.lib.dzine_schema import DzineRequest

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CANVAS_PROJECT_ID = os.environ.get("DZINE_PROJECT_ID", "19797967")
CANVAS_URL = f"https://www.dzine.ai/canvas?id={CANVAS_PROJECT_ID}"

# Canonical Ray reference face — MUST be used for all face-related operations.
# This is the single source of truth for Ray's identity across all Dzine
# and DaVinci Resolve creations.
RAY_REFERENCE_FACE = project_root() / "assets" / "ray_avatar" / "ray_reference_face.png"

VIEWPORT = {"width": 1440, "height": 900}

# Timeouts
GENERATION_TIMEOUT_S = int(os.environ.get("DZINE_GENERATION_TIMEOUT_S", "120"))
POLL_INTERVAL_S = 3

# Sidebar icon positions (x, y) at 1440x900 viewport
SIDEBAR = {
    "upload": (40, 81),
    "assets": (40, 136),
    "txt2img": (40, 197),
    "img2img": (40, 252),
    "character": (40, 306),
    "ai_video": (40, 361),
    "lip_sync": (40, 425),
    "video_editor": (40, 490),
    "motion_control": (40, 550),
    "enhance_upscale": (40, 627),
    "image_editor": (40, 698),
    "instant_storyboard": (40, 766),
}


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass
class GenerationResult:
    success: bool
    local_path: str = ""
    image_url: str = ""
    checksum_sha256: str = ""
    duration_s: float = 0.0
    error: str = ""
    retries_used: int = 0


# ---------------------------------------------------------------------------
# Retry logic
# ---------------------------------------------------------------------------

MAX_RETRIES = 1
RETRY_DELAY_S = 5.0


def _with_retry(fn, *, max_retries: int = MAX_RETRIES,
                delay_s: float = RETRY_DELAY_S, label: str = "") -> GenerationResult:
    """Wrap a generation function with retry on transient failures.

    Retries once on timeout or generic errors. Does NOT retry on
    config errors (missing prompt, wrong panel type).
    """
    last_result = None
    for attempt in range(1 + max_retries):
        result = fn()
        if result.success:
            result.retries_used = attempt
            return result

        last_result = result

        # Don't retry on config/permanent errors
        err_lower = (result.error or "").lower()
        permanent = ("no prompt", "wrong panel", "could not find",
                     "could not select", "dzinerequest has no prompt")
        if any(p in err_lower for p in permanent):
            return result

        if attempt < max_retries:
            tag = f"[dzine] {label} " if label else "[dzine] "
            print(f"{tag}Attempt {attempt+1} failed: {result.error}. "
                  f"Retrying in {delay_s}s...", file=sys.stderr)
            time.sleep(delay_s)

    last_result.retries_used = max_retries
    return last_result


# ---------------------------------------------------------------------------
# Login / session validation
# ---------------------------------------------------------------------------


def ensure_logged_in(page) -> bool:
    """Check if user is logged into Dzine. Returns True if logged in.

    Checks for avatar button (logged in) vs login button (logged out).
    """
    return page.evaluate("""() => {
        var avatar = document.querySelector('button.avatar');
        if (avatar && avatar.getBoundingClientRect().width > 0) return true;
        var login = document.querySelector('button');
        for (var b of document.querySelectorAll('button')) {
            if ((b.innerText || '').trim() === 'Log in') return false;
        }
        return true;  // no login button found = probably logged in
    }""")


# ---------------------------------------------------------------------------
# Image validation
# ---------------------------------------------------------------------------

MIN_IMAGE_SIZE = 50 * 1024  # 50 KB


def validate_image(path: Path) -> tuple[bool, str]:
    """Validate a downloaded image file.

    Returns (is_valid, error_message).
    Checks: file exists, size >= 50KB, valid PNG/WebP/JPEG header.
    """
    if not path.exists():
        return False, f"File does not exist: {path}"

    size = path.stat().st_size
    if size < MIN_IMAGE_SIZE:
        return False, f"File too small ({size} bytes, min {MIN_IMAGE_SIZE}): {path}"

    # Check magic bytes
    with open(path, "rb") as f:
        header = f.read(16)

    if header[:8] == b"\x89PNG\r\n\x1a\n":
        return True, ""
    if header[:4] == b"RIFF" and header[8:12] == b"WEBP":
        return True, ""
    if header[:3] == b"\xff\xd8\xff":
        return True, ""

    return False, f"Unknown image format (header: {header[:8].hex()}): {path}"


def _image_dimensions(path: Path) -> tuple[int, int]:
    """Read image dimensions without external deps. Returns (width, height) or (0, 0)."""
    try:
        with open(path, "rb") as f:
            header = f.read(32)

        # PNG
        if header[:8] == b"\x89PNG\r\n\x1a\n":
            w, h = struct.unpack(">II", header[16:24])
            return w, h

        # JPEG — find SOF0/SOF2 marker
        if header[:3] == b"\xff\xd8\xff":
            with open(path, "rb") as f:
                data = f.read(min(path.stat().st_size, 65536))
            i = 2
            while i < len(data) - 9:
                if data[i] == 0xFF and data[i + 1] in (0xC0, 0xC2):
                    h = struct.unpack(">H", data[i + 5:i + 7])[0]
                    w = struct.unpack(">H", data[i + 7:i + 9])[0]
                    return w, h
                if data[i] == 0xFF:
                    length = struct.unpack(">H", data[i + 2:i + 4])[0]
                    i += 2 + length
                else:
                    i += 1

    except Exception:
        pass
    return 0, 0


# ---------------------------------------------------------------------------
# Dialog handling
# ---------------------------------------------------------------------------


def close_all_dialogs(page) -> int:
    """Close any tutorial/popup dialogs that block the UI.

    Returns the number of dialogs closed.
    """
    closed = 0
    for _ in range(8):
        found = False
        for text in ["Not now", "Close", "Never show again", "Got it", "Skip", "Later", "Done"]:
            try:
                btn = page.locator(f'button:has-text("{text}")')
                if btn.count() > 0 and btn.first.is_visible(timeout=500):
                    btn.first.click()
                    page.wait_for_timeout(500)
                    found = True
                    closed += 1
            except Exception:
                pass
        if not found:
            break
    return closed


# ---------------------------------------------------------------------------
# JS helpers — reliable element interaction on Dzine's dynamic DOM
# ---------------------------------------------------------------------------


def _js_click_button_by_text(page, text: str, *, x_min: int = 0, x_max: int = 9999) -> bool:
    """Click a button containing the given text, optionally within an x range."""
    return page.evaluate(f"""() => {{
        for (const btn of document.querySelectorAll('button')) {{
            const t = (btn.innerText || '').trim();
            const r = btn.getBoundingClientRect();
            if (t.includes({json.dumps(text)}) && !btn.disabled
                && r.x >= {x_min} && r.x <= {x_max}) {{
                btn.click(); return true;
            }}
        }}
        return false;
    }}""")


def _js_click_element_by_text(page, text: str, tag: str = "*", *, x_min: int = 0, y_min: int = 0) -> bool:
    """Click any element with exact text match, filtered by tag and position."""
    return page.evaluate(f"""() => {{
        for (const el of document.querySelectorAll({json.dumps(tag)})) {{
            const t = (el.innerText || '').trim();
            const r = el.getBoundingClientRect();
            if (t === {json.dumps(text)} && r.x >= {x_min} && r.y >= {y_min}) {{
                el.click(); return true;
            }}
        }}
        return false;
    }}""")


def _js_get_result_images(page) -> list[dict]:
    """Get all result images from the Results panel."""
    return page.evaluate("""() => {
        const results = [];
        for (const img of document.querySelectorAll('img')) {
            const src = img.src || '';
            if (src.includes('static.dzine.ai/stylar_product/p/')) {
                const r = img.getBoundingClientRect();
                results.push({
                    src: src,
                    x: Math.round(r.x),
                    y: Math.round(r.y),
                    w: Math.round(r.width),
                    h: Math.round(r.height),
                });
            }
        }
        return results;
    }""")


def _js_set_prompt(page, prompt: str) -> bool:
    """Set the prompt text in the active panel textarea via JS.

    Faster and more reliable than keyboard.type() which can hang on
    long prompts due to per-keystroke event dispatch.
    """
    return page.evaluate(f"""() => {{
        var textareas = document.querySelectorAll('textarea');
        for (var ta of textareas) {{
            var r = ta.getBoundingClientRect();
            if (r.x > 60 && r.x < 350 && r.width > 100 && r.height > 30) {{
                ta.value = {json.dumps(prompt)};
                ta.dispatchEvent(new Event('input', {{bubbles: true}}));
                ta.dispatchEvent(new Event('change', {{bubbles: true}}));
                return true;
            }}
        }}
        return false;
    }}""")


def _js_get_progress(page) -> list[dict]:
    """Check for generation progress indicators (percentage text)."""
    return page.evaluate("""() => {
        const progs = [];
        for (const el of document.querySelectorAll('*')) {
            const t = (el.innerText || '').trim();
            if (/^\\d{1,3}%$/.test(t)) {
                const r = el.getBoundingClientRect();
                if (r.width > 0 && r.width < 100) {
                    progs.push({pct: t, y: Math.round(r.y)});
                }
            }
        }
        return progs;
    }""")


# ---------------------------------------------------------------------------
# Page setup
# ---------------------------------------------------------------------------


def _safe_cleanup(page, context, should_close, pw) -> None:
    """Clean up Playwright resources without hanging.

    page.close() and pw.stop() can hang on CDP connections.
    Use threading timeout as safeguard.
    """
    import threading

    def _do_cleanup():
        try:
            page.close()
        except Exception:
            pass
        if should_close:
            try:
                context.close()
            except Exception:
                pass
        try:
            pw.stop()
        except Exception:
            pass

    t = threading.Thread(target=_do_cleanup, daemon=True)
    t.start()
    t.join(timeout=5)  # 5 second max for cleanup


# ---------------------------------------------------------------------------
# Shared session management
# ---------------------------------------------------------------------------

# Module-level session state (reused across calls within same process)
_session_pw = None
_session_browser = None
_session_context = None
_session_page = None
_session_should_close = False


def _get_or_create_page():
    """Get a reusable page connected to Dzine canvas.

    Creates a new Playwright + page on first call, reuses on subsequent.
    Handles stale connections by reconnecting.

    Returns (page, is_new_page) tuple.
    """
    global _session_pw, _session_browser, _session_context, _session_page, _session_should_close

    # Try to reuse existing session
    if _session_page is not None:
        try:
            # Quick check if page is still alive
            _session_page.evaluate("() => true")
            return _session_page, False
        except Exception:
            # Page is dead, clean up and reconnect
            _session_page = None
            _session_browser = None
            _session_context = None
            if _session_pw:
                try:
                    _session_pw.stop()
                except Exception:
                    pass
            _session_pw = None

    # Create new session
    from tools.lib.brave_profile import connect_or_launch

    browser, context, should_close, pw = connect_or_launch(headless=False)
    page = context.new_page()

    _session_pw = pw
    _session_browser = browser
    _session_context = context
    _session_page = page
    _session_should_close = should_close

    return page, True


def close_session() -> None:
    """Explicitly close the shared session. Call at end of batch operations."""
    global _session_pw, _session_browser, _session_context, _session_page, _session_should_close
    if _session_page:
        _safe_cleanup(_session_page, _session_context, _session_should_close, _session_pw)
    _session_pw = None
    _session_browser = None
    _session_context = None
    _session_page = None
    _session_should_close = False


def _ensure_canvas_page(page) -> None:
    """Navigate to the canvas if not already there, set viewport, close dialogs."""
    page.set_viewport_size(VIEWPORT)

    current = page.url
    if "dzine.ai/canvas" not in current:
        page.goto(CANVAS_URL, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(3000)

    close_all_dialogs(page)


def _exit_tool_mode(page) -> None:
    """Exit any active tool mode by going back to main canvas state.

    Handles: Expression Edit (back arrow), AI Eraser/other editors (Exit button),
    and any sidebar tool panels.
    """
    # Try Exit button (top bar, for AI Eraser etc.)
    try:
        exit_btn = page.locator('button:has-text("Exit")')
        if exit_btn.count() > 0 and exit_btn.first.is_visible(timeout=500):
            exit_btn.first.click()
            page.wait_for_timeout(1000)
            return
    except Exception:
        pass

    # Try back arrow (Expression Edit, other sub-panels)
    try:
        back = page.evaluate("""() => {
            // Look for back arrow button (← character or svg arrow)
            for (const el of document.querySelectorAll('*')) {
                const text = (el.innerText || '').trim();
                const r = el.getBoundingClientRect();
                if (r.x > 60 && r.x < 100 && r.y > 40 && r.y < 70
                    && r.width > 20 && r.width < 50
                    && (el.tagName === 'BUTTON' || el.tagName === 'SVG'
                        || el.style.cursor === 'pointer')) {
                    el.click(); return true;
                }
            }
            return false;
        }""")
        if back:
            page.wait_for_timeout(1000)
    except Exception:
        pass

    # Final fallback: click Txt2Img sidebar to reset to a known state
    try:
        page.mouse.click(*SIDEBAR["txt2img"])
        page.wait_for_timeout(500)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Canvas image upload (for Img2Img reference)
# ---------------------------------------------------------------------------


def _upload_image_to_canvas(page, image_path: str) -> bool:
    """Upload an image file to the Dzine canvas via JavaScript drop event.

    Reads the image, converts to base64, then dispatches a synthetic drop
    event on the canvas drop zone. The image becomes a layer that can be
    used as input for Img2Img generation.

    Returns True if the image was uploaded successfully.
    """
    import base64

    img_path = Path(image_path)
    if not img_path.is_file():
        print(f"[dzine] Image not found: {image_path}", file=sys.stderr)
        return False

    img_data = img_path.read_bytes()
    img_b64 = base64.b64encode(img_data).decode()
    suffix = img_path.suffix.lower()
    mime = "image/jpeg" if suffix in (".jpg", ".jpeg") else "image/png"
    filename = img_path.name

    result = page.evaluate(f"""async () => {{
        var b64 = '{img_b64}';
        var byteChars = atob(b64);
        var byteArray = new Uint8Array(byteChars.length);
        for (var i = 0; i < byteChars.length; i++) {{
            byteArray[i] = byteChars.charCodeAt(i);
        }}
        var file = new File([byteArray], {json.dumps(filename)}, {{ type: {json.dumps(mime)} }});
        var dt = new DataTransfer();
        dt.items.add(file);
        var dropBox = document.querySelector('.drop-box') || document.querySelector('.drop');
        if (!dropBox) return 'no_drop_zone';
        dropBox.dispatchEvent(new DragEvent('dragenter', {{ dataTransfer: dt, bubbles: true }}));
        dropBox.dispatchEvent(new DragEvent('dragover', {{ dataTransfer: dt, bubbles: true }}));
        dropBox.dispatchEvent(new DragEvent('drop', {{ dataTransfer: dt, bubbles: true }}));
        return 'ok';
    }}""")

    if result != "ok":
        print(f"[dzine] Drop event failed: {result}", file=sys.stderr)
        return False

    page.wait_for_timeout(5000)

    # Click on center of canvas to select the placed image
    page.mouse.click(720, 450)
    page.wait_for_timeout(1000)

    print(f"[dzine] Image uploaded to canvas: {filename}", file=sys.stderr)
    return True


# ---------------------------------------------------------------------------
# Generation: Consistent Character (Ray)
# ---------------------------------------------------------------------------


def _set_cc_reference(page, image_path: str) -> bool:
    """Upload a reference image for CC Reference mode.

    Opens the Pick Image dialog, clicks the upload zone, sets the file
    via Playwright's file chooser interception. Returns True on success.
    """
    # 1. Activate Reference mode
    ref_clicked = page.evaluate("""() => {
        for (const btn of document.querySelectorAll('button')) {
            var text = (btn.innerText || '').trim();
            var r = btn.getBoundingClientRect();
            if (text === 'Reference' && r.width > 30 && r.x > 50 && r.x < 350 && r.y > 400) {
                btn.click(); return true;
            }
        }
        return false;
    }""")
    if not ref_clicked:
        print("[dzine] Could not find Reference button", file=sys.stderr)
        return False
    page.wait_for_timeout(2000)

    # 2. Click Pick Image button
    page.evaluate("""() => {
        for (const btn of document.querySelectorAll('button')) {
            var classes = (btn.className || '').toString();
            var r = btn.getBoundingClientRect();
            if (classes.includes('pick-image') && r.width > 50 && r.x > 50 && r.x < 350) {
                btn.click(); return true;
            }
        }
        return false;
    }""")
    page.wait_for_timeout(2000)

    # 3. Verify dialog opened
    dialog = page.evaluate("""() => {
        var el = document.querySelector('.pick-panel');
        if (!el) return null;
        var r = el.getBoundingClientRect();
        return r.width > 100;
    }""")
    if not dialog:
        print("[dzine] Pick Image dialog did not open", file=sys.stderr)
        return False

    # 4. Find and click button.upload → trigger file chooser
    upload_pos = page.evaluate("""() => {
        var panel = document.querySelector('.pick-panel');
        if (!panel) return null;
        var btn = panel.querySelector('button.upload');
        if (!btn) return null;
        var r = btn.getBoundingClientRect();
        return {x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)};
    }""")
    if not upload_pos:
        print("[dzine] Upload button not found in dialog", file=sys.stderr)
        return False

    try:
        with page.expect_file_chooser(timeout=5000) as fc_info:
            page.mouse.click(upload_pos['x'], upload_pos['y'])
        fc = fc_info.value
        fc.set_files(image_path)
        page.wait_for_timeout(5000)
    except Exception as exc:
        print(f"[dzine] File chooser failed: {exc}", file=sys.stderr)
        return False

    # 5. Verify reference was set (div.image loses 'empty' class)
    ref_set = page.evaluate("""() => {
        for (const btn of document.querySelectorAll('button')) {
            var classes = (btn.className || '').toString();
            if (!classes.includes('pick-image')) continue;
            var img = btn.querySelector('.image');
            if (!img) continue;
            return !img.classList.contains('empty');
        }
        return false;
    }""")
    if ref_set:
        print("[dzine] Reference image set successfully", file=sys.stderr)
    else:
        print("[dzine] Reference may not have been set (empty check failed)", file=sys.stderr)
    return ref_set


def _clear_cc_reference(page) -> bool:
    """Remove the current CC reference image by clicking the trash icon."""
    return page.evaluate("""() => {
        var trash = document.querySelector('.pick-image .ico-trash');
        if (trash) { trash.click(); return true; }
        return false;
    }""")


def _set_cc_generation_mode(page, mode: str = "Normal") -> bool:
    """Set the CC generation mode to Fast, Normal, or HQ.

    Args:
        mode: One of "Fast", "Normal", "HQ"
    """
    return page.evaluate(f"""() => {{
        for (const btn of document.querySelectorAll('button.options')) {{
            var text = (btn.innerText || '').trim();
            var r = btn.getBoundingClientRect();
            if (text === {json.dumps(mode)} && r.y > 880) {{
                btn.click(); return true;
            }}
        }}
        return false;
    }}""")


def _set_txt2img_face_match(page, image_path: str) -> bool:
    """Upload a face reference for Txt2Img Face Match feature.

    Toggles Face Match ON, opens Pick Image dialog, uploads face via file chooser.
    Uses the same pick-panel mechanism as CC Reference mode.

    Args:
        image_path: Path to face image file
    """
    # Toggle Face Match ON
    toggled = page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text === 'Face Match' && r.x > 60 && r.x < 360 && r.y > 0 && r.y < 900 && r.width > 0) {
                var parent = el;
                for (var p = 0; p < 5 && parent; p++) {
                    var switches = parent.querySelectorAll('button');
                    for (var i = 0; i < switches.length; i++) {
                        var sw = switches[i];
                        var sr = sw.getBoundingClientRect();
                        var classes = (sw.className || '').toString();
                        if (classes.includes('switch') && sr.width > 25 && sr.width < 55
                            && Math.abs(sr.y - r.y) < 30) {
                            sw.click(); return true;
                        }
                    }
                    parent = parent.parentElement;
                }
            }
        }
        return false;
    }""")
    if not toggled:
        print("[dzine] Could not find Face Match toggle", file=sys.stderr)
        return False
    page.wait_for_timeout(1500)

    # Click Pick a Face button
    page.evaluate("""() => {
        for (const btn of document.querySelectorAll('button')) {
            var classes = (btn.className || '').toString();
            var r = btn.getBoundingClientRect();
            if (classes.includes('pick-image') && r.x > 60 && r.x < 360 && r.width > 50) {
                btn.click(); return true;
            }
        }
        return false;
    }""")
    page.wait_for_timeout(1500)

    # Upload via pick-panel dialog (same as CC Reference)
    upload_pos = page.evaluate("""() => {
        var panel = document.querySelector('.pick-panel');
        if (!panel) return null;
        var btn = panel.querySelector('button.upload');
        if (!btn) return null;
        var r = btn.getBoundingClientRect();
        return {x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)};
    }""")
    if not upload_pos:
        print("[dzine] Pick-panel upload button not found for Face Match", file=sys.stderr)
        return False

    try:
        with page.expect_file_chooser(timeout=5000) as fc_info:
            page.mouse.click(upload_pos['x'], upload_pos['y'])
        fc = fc_info.value
        fc.set_files(image_path)
        page.wait_for_timeout(5000)
        print("[dzine] Face Match image uploaded", file=sys.stderr)
        return True
    except Exception as exc:
        print(f"[dzine] Face Match upload failed: {exc}", file=sys.stderr)
        return False


def _set_txt2img_seed(page, seed: int) -> bool:
    """Set the seed value in the Txt2Img Advanced section.

    Opens the Advanced popup and fills the seed input.
    """
    # Click Advanced to open popup
    page.evaluate("""() => {
        for (const el of document.querySelectorAll('.params *')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text === 'Advanced' && r.x > 60 && r.x < 360 && r.y > 600 && r.y < 750) {
                el.click(); return true;
            }
        }
        return false;
    }""")
    page.wait_for_timeout(1000)

    # Fill the seed input
    filled = page.evaluate(f"""() => {{
        var popup = document.querySelector('.advanced-content.show');
        if (!popup) return false;
        var input = popup.querySelector('input');
        if (!input) return false;
        input.value = '';
        input.focus();
        return true;
    }}""")
    if filled:
        page.keyboard.type(str(seed), delay=10)
        page.wait_for_timeout(300)
        print(f"[dzine] Seed set to {seed}", file=sys.stderr)

    # Close Advanced popup
    page.evaluate("""() => {
        for (const el of document.querySelectorAll('.params *')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text === 'Advanced' && r.x > 60 && r.x < 360 && r.y > 600 && r.y < 750) {
                el.click(); return true;
            }
        }
        return false;
    }""")
    page.wait_for_timeout(500)
    return filled


def _activate_cc_panel(page) -> bool:
    """Ensure the CC (Consistent Character) panel is in active Generate Images mode.

    The Character sidebar shows a menu card with options. We need to:
    1. Open the Character menu (double-click)
    2. Click "Generate Images" card
    3. Select Ray character

    Returns True if panel is active with Ray selected.
    """
    # Step 1: Open Character menu via double-click
    page.mouse.dblclick(*SIDEBAR["character"])
    page.wait_for_timeout(2000)
    close_all_dialogs(page)

    # Step 2: Click "Generate Images" card
    gen_clicked = page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text === 'Generate Images' && r.x > 60 && r.y > 80 && r.y < 300
                && r.height < 50 && r.width > 50) {
                el.click(); return true;
            }
        }
        // Fallback: broader search
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text.includes('Generate Images') && text.includes('With your')
                && r.x > 60 && r.width > 100 && r.height > 20 && r.height < 100) {
                el.click(); return true;
            }
        }
        return false;
    }""")
    if gen_clicked:
        page.wait_for_timeout(2000)
        close_all_dialogs(page)

    # Step 3: Select Ray character via hidden-list JS-click (Phase 116 pattern)
    # The .c-character-list renders at 0x0 dimensions but buttons are clickable via JS
    ray_selected = page.evaluate("""() => {
        var list = document.querySelector('.c-character-list');
        if (list) {
            for (var item of list.querySelectorAll('.item, button')) {
                if ((item.innerText || '').trim() === 'Ray') {
                    item.click(); return true;
                }
            }
        }
        // Fallback: broad search for Ray button anywhere in DOM
        for (var el of document.querySelectorAll('button')) {
            if ((el.innerText || '').trim() === 'Ray') {
                el.click(); return true;
            }
        }
        return false;
    }""")
    if ray_selected:
        page.wait_for_timeout(2000)
        close_all_dialogs(page)
    else:
        print("[dzine] Warning: Could not find Ray in character list", file=sys.stderr)

    # Verify: check for "Consistent Character" header
    return page.evaluate("""() => {
        for (const el of document.querySelectorAll('.gen-config-header')) {
            if ((el.innerText || '').includes('Consistent Character')) return true;
        }
        return false;
    }""")


def _activate_img2img_panel(page) -> bool:
    """Ensure Img2Img panel is in active editing mode.

    Uses panel toggle technique: click Character sidebar first, then Img2Img.
    Falls back to double-click.
    """
    page.mouse.click(*SIDEBAR["character"])
    page.wait_for_timeout(500)
    page.mouse.click(*SIDEBAR["img2img"])
    page.wait_for_timeout(1500)

    active = page.evaluate("""() => {
        for (const el of document.querySelectorAll('.gen-config-header')) {
            if ((el.innerText || '').includes('Image-to-Image')) return true;
        }
        return false;
    }""")
    if active:
        return True

    # Fallback: double-click
    page.mouse.click(*SIDEBAR["img2img"])
    page.wait_for_timeout(200)
    page.mouse.click(*SIDEBAR["img2img"])
    page.wait_for_timeout(2000)
    close_all_dialogs(page)

    return page.evaluate("""() => {
        for (const el of document.querySelectorAll('.gen-config-header')) {
            if ((el.innerText || '').includes('Image-to-Image')) return true;
        }
        return false;
    }""")


def _generate_img2img(page, prompt: str, *,
                      quality: str = "2K",
                      model: str = "") -> GenerationResult:
    """Generate an image using Img2Img mode.

    Transforms the current canvas layer into a new image based on the prompt.
    Requires an image already placed on canvas (click a result image first).

    Args:
        prompt: Text prompt for transformation
        quality: Output quality — "1K", "2K" (default), or "4K"
        model: Optional model name (default: current model, typically "Nano Banana Pro")

    Returns GenerationResult with image URL on success.
    """
    start = time.monotonic()
    before_images = _js_get_result_images(page)

    # 1. Activate Img2Img panel
    if not _activate_img2img_panel(page):
        return GenerationResult(success=False, duration_s=time.monotonic() - start,
                                error="Could not activate Img2Img panel")
    close_all_dialogs(page)

    # 1b. Select model if specified
    if model:
        _select_model(page, model)

    # 2. Fill prompt textarea via JS (faster than keyboard.type, avoids hangs)
    if not _js_set_prompt(page, prompt):
        page.mouse.click(101, 175)
        page.keyboard.press("Meta+a")
        page.wait_for_timeout(200)
        page.keyboard.type(prompt, delay=3)
    page.wait_for_timeout(500)

    # 3. Set output quality
    if quality in ("1K", "2K", "4K"):
        page.evaluate(f"""() => {{
            for (const btn of document.querySelectorAll('button.options, button')) {{
                var text = (btn.innerText || '').trim();
                var r = btn.getBoundingClientRect();
                if (text === {json.dumps(quality)} && r.x > 60 && r.x < 370
                    && r.y > 0 && r.y < 900 && r.width > 20) {{
                    btn.click(); return true;
                }}
            }}
            return false;
        }}""")
        page.wait_for_timeout(300)

    # 4. Click Generate
    gen_clicked = _js_click_button_by_text(page, "Generate", x_min=60, x_max=350)
    if not gen_clicked:
        close_all_dialogs(page)
        page.wait_for_timeout(1000)
        gen_clicked = _js_click_button_by_text(page, "Generate", x_min=60, x_max=350)
    if not gen_clicked:
        return GenerationResult(success=False, duration_s=time.monotonic() - start,
                                error="Could not click Generate button")

    # 5. Wait for generation (use total count detection like CC)
    return _wait_for_cc_generation(page, len(before_images), start)


def _generate_cc(page, scene_prompt: str, *,
                 reference_image: str = "") -> GenerationResult:
    """Generate an image using Consistent Character with Ray.

    Args:
        page: Playwright page
        scene_prompt: Description of the scene
        reference_image: Optional path to a reference image for CC Reference mode

    Returns GenerationResult with image URL on success.
    """
    start = time.monotonic()

    # Count ALL result images before generation.
    # CC results use varying URL patterns (characterchatfal, faltxt2img),
    # so we detect by total count increase rather than pattern matching.
    before_images = _js_get_result_images(page)

    # 1. Activate CC panel with Ray selected
    if not _activate_cc_panel(page):
        # Fallback: try the legacy approach
        page.mouse.click(*SIDEBAR["txt2img"])
        page.wait_for_timeout(500)
        page.mouse.click(*SIDEBAR["character"])
        page.wait_for_timeout(1500)

        clicked = page.evaluate("""() => {
            for (const btn of document.querySelectorAll('button')) {
                const text = (btn.innerText || '').trim();
                if (text.includes('Generate Images') && text.includes('With your character')) {
                    btn.click(); return true;
                }
            }
            return false;
        }""")
        if not clicked:
            return GenerationResult(success=False, duration_s=time.monotonic() - start,
                                    error="Could not find 'Generate Images' button")
        page.wait_for_timeout(2000)

        ray_selected = page.evaluate("""() => {
            // Phase 116 pattern: hidden-list JS-click
            var list = document.querySelector('.c-character-list');
            if (list) {
                for (var item of list.querySelectorAll('.item, button')) {
                    if ((item.innerText || '').trim() === 'Ray') {
                        item.click(); return true;
                    }
                }
            }
            // Broad fallback
            for (var el of document.querySelectorAll('button')) {
                if ((el.innerText || '').trim() === 'Ray') {
                    el.click(); return true;
                }
            }
            return false;
        }""")
        if not ray_selected:
            return GenerationResult(success=False, duration_s=time.monotonic() - start,
                                    error="Could not select Ray character")
        page.wait_for_timeout(2000)

    # 4. Type scene prompt in the CC textarea at (101, 191)
    page.mouse.click(101, 200)
    page.keyboard.press("Meta+a")
    page.wait_for_timeout(200)
    page.keyboard.type(scene_prompt, delay=5)
    page.wait_for_timeout(500)

    # 5. Set reference image if provided
    if reference_image and os.path.exists(reference_image):
        ref_ok = _set_cc_reference(page, reference_image)
        if not ref_ok:
            print(f"[dzine] Warning: failed to set reference image, continuing without",
                  file=sys.stderr)

    # 6. Set aspect ratio to "canvas" (16:9 = 1536x864)
    page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            if ((el.innerText || '').trim() === 'canvas' &&
                el.getBoundingClientRect().x > 60 && el.getBoundingClientRect().y > 400) {
                el.click(); return true;
            }
        }
        return false;
    }""")
    page.wait_for_timeout(500)

    # 7. Click Generate (button is at bottom of CC panel, y~770-790)
    gen_clicked = page.evaluate("""() => {
        for (const btn of document.querySelectorAll('button')) {
            const text = (btn.innerText || '').trim();
            const r = btn.getBoundingClientRect();
            if (text.includes('Generate') && !btn.disabled
                && r.x > 60 && r.x < 350 && r.y > 700) {
                btn.click(); return true;
            }
        }
        return false;
    }""")
    if not gen_clicked:
        return GenerationResult(success=False, duration_s=time.monotonic() - start,
                                error="Could not click Generate button")

    # 8. Wait for async generation (CC uses total image count detection)
    return _wait_for_cc_generation(page, len(before_images), start)


# ---------------------------------------------------------------------------
# Generation: Txt2Img
# ---------------------------------------------------------------------------


_MODEL_CATEGORY: dict[str, str] = {
    "Nano Banana Pro": "General",
    "Nano Banana": "General",
    "Seedream 4.5": "General",
    "Z-Image Turbo": "General",
    "Dzine General": "General",
    "Realistic Product": "Realistic",
}


def _select_model(page, model_name: str, category: str = "") -> bool:
    """Select a model/style in the Txt2Img model picker.

    Opens the style picker overlay, navigates to the correct category,
    scrolls the model into view, and clicks it.

    Args:
        model_name: Exact model name (e.g., "Realistic Product", "Nano Banana Pro")
        category: Optional category override (e.g., "Realistic", "General")

    Returns True if model was selected.
    """
    # Auto-detect category if not specified
    if not category:
        category = _MODEL_CATEGORY.get(model_name, "General")

    # Open picker
    page.evaluate("""() => {
        var btn = document.querySelector('button.style');
        if (btn) btn.click();
    }""")
    page.wait_for_timeout(2000)

    # Navigate to category — models are only visible in their category
    page.evaluate(f"""() => {{
        for (const el of document.querySelectorAll('.left-filter-item, .filter-item, [class*="category-item"]')) {{
            if ((el.innerText || '').trim() === {json.dumps(category)}) {{
                el.click(); return true;
            }}
        }}
        return false;
    }}""")
    page.wait_for_timeout(1500)

    # Click the model card — scroll into view first, then click
    selected = page.evaluate(f"""() => {{
        var name = {json.dumps(model_name)};
        for (const el of document.querySelectorAll('.style-name')) {{
            if ((el.innerText || '').trim() === name) {{
                // Scroll element into view
                el.scrollIntoView({{behavior: 'instant', block: 'center'}});
                // Walk up to find clickable card (parent with dimensions)
                var target = el;
                for (var i = 0; i < 4; i++) {{
                    target = target.parentElement;
                    if (!target) break;
                    var r = target.getBoundingClientRect();
                    if (r.width > 80 && r.height > 80) {{ target.click(); return true; }}
                }}
                el.click(); return true;
            }}
        }}
        return false;
    }}""")
    page.wait_for_timeout(1000)

    # Close picker if still open
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)

    if selected:
        print(f"[dzine] Model selected: {model_name}", file=sys.stderr)
    else:
        print(f"[dzine] Model not found: {model_name}", file=sys.stderr)
    return selected


def _activate_txt2img_panel(page) -> bool:
    """Ensure Txt2Img panel is in active editing mode (not intro card).

    Uses panel toggle technique: click a different sidebar first, then Txt2Img.
    Falls back to double-click on Txt2Img icon.
    """
    # Panel toggle: click Img2Img first, then Txt2Img
    page.mouse.click(*SIDEBAR["img2img"])
    page.wait_for_timeout(500)
    page.mouse.click(*SIDEBAR["txt2img"])
    page.wait_for_timeout(1500)

    # Verify active state
    active = page.evaluate("""() => {
        for (const el of document.querySelectorAll('.gen-config-header')) {
            if ((el.innerText || '').includes('Text to Image')) return true;
        }
        return false;
    }""")
    if active:
        return True

    # Fallback: double-click
    page.mouse.click(*SIDEBAR["txt2img"])
    page.wait_for_timeout(200)
    page.mouse.click(*SIDEBAR["txt2img"])
    page.wait_for_timeout(2000)
    close_all_dialogs(page)

    return page.evaluate("""() => {
        for (const el of document.querySelectorAll('.gen-config-header')) {
            if ((el.innerText || '').includes('Text to Image')) return true;
        }
        return false;
    }""")


def _generate_txt2img(page, prompt: str, *,
                      aspect_16_9: bool = True,
                      model: str = "") -> GenerationResult:
    """Generate an image using Txt2Img mode.

    Args:
        prompt: Text prompt for generation
        aspect_16_9: Use 16:9 aspect ratio (default True). Uses "canvas" preset
                     which maps to 1536×864 (actual 16:9).
        model: Optional model name to select (e.g., "Realistic Product")

    Returns GenerationResult with image URL on success.
    """
    start = time.monotonic()

    # Count existing results before generation
    before_images = _js_get_result_images(page)
    txt2img_types = ("gemini2text2image", "faltxt2img")
    before_count = len([i for i in before_images
                        if any(t in i["src"] for t in txt2img_types)])

    # 1. Activate Txt2Img panel (handles intro card → active panel)
    _activate_txt2img_panel(page)
    close_all_dialogs(page)

    # 1b. Select model if specified
    if model:
        _select_model(page, model)

    # 2. Fill prompt textarea via JS (faster than keyboard.type, avoids hangs)
    if not _js_set_prompt(page, prompt):
        # Fallback: click + type
        page.mouse.click(101, 175)
        page.keyboard.press("Meta+a")
        page.wait_for_timeout(200)
        page.keyboard.type(prompt, delay=3)
    page.wait_for_timeout(500)

    # 3. Set aspect ratio — use "canvas" for 16:9 (1536×864)
    if aspect_16_9:
        page.evaluate("""() => {
            var el = document.querySelector('.c-aspect-ratio .item.canvas');
            if (el) { el.click(); return true; }
            // Fallback: match by text
            for (const el of document.querySelectorAll('.c-aspect-ratio .item')) {
                if ((el.innerText || '').trim() === 'canvas') {
                    el.click(); return true;
                }
            }
            return false;
        }""")
        page.wait_for_timeout(500)

    # 4. Click Generate (retry once after closing dialogs if first attempt fails)
    gen_clicked = _js_click_button_by_text(page, "Generate", x_min=60, x_max=350)
    if not gen_clicked:
        # Retry: close dialogs, wait, try again
        close_all_dialogs(page)
        page.wait_for_timeout(1000)
        gen_clicked = _js_click_button_by_text(page, "Generate", x_min=60, x_max=350)
    if not gen_clicked:
        return GenerationResult(success=False, duration_s=time.monotonic() - start,
                                error="Could not click Generate button")

    # 5. Wait for async generation
    return _wait_for_generation(page, before_count, txt2img_types, start)


# ---------------------------------------------------------------------------
# Generation polling
# ---------------------------------------------------------------------------


def _wait_for_cc_generation(page, before_total: int,
                            start: float) -> GenerationResult:
    """Poll the Results panel for new CC images using total count.

    CC results use varying URL patterns (characterchatfal, faltxt2img),
    so we detect solely by total image count increase. CC always produces
    2 images per generation.
    """
    deadline = start + GENERATION_TIMEOUT_S
    last_pct = ""

    while time.monotonic() < deadline:
        page.wait_for_timeout(POLL_INTERVAL_S * 1000)

        images = _js_get_result_images(page)
        if len(images) > before_total:
            new_img = images[0]  # newest at top (lowest y in results panel)
            return GenerationResult(
                success=True,
                image_url=new_img["src"],
                duration_s=time.monotonic() - start,
            )

        progress = _js_get_progress(page)
        if progress:
            pct = progress[0]["pct"]
            if pct != last_pct:
                print(f"[dzine] CC generation progress: {pct}", file=sys.stderr)
                last_pct = pct

    return GenerationResult(
        success=False,
        duration_s=time.monotonic() - start,
        error=f"CC generation timed out after {GENERATION_TIMEOUT_S}s",
    )


def _wait_for_generation(page, before_count: int,
                         src_filter: str | tuple[str, ...],
                         start: float) -> GenerationResult:
    """Poll the Results panel until a new image appears or timeout.

    Uses two detection strategies:
    1. Count matching result images (by src URL pattern)
    2. Count ALL result images (catches URL pattern changes)

    Args:
        before_count: Number of matching images before generation started
        src_filter: String or tuple of strings to match in image src
        start: monotonic time when generation started
    """
    if isinstance(src_filter, str):
        src_filter = (src_filter,)

    # Also track total image count as fallback detection
    all_before = len(_js_get_result_images(page))

    deadline = start + GENERATION_TIMEOUT_S
    last_pct = ""

    while time.monotonic() < deadline:
        page.wait_for_timeout(POLL_INTERVAL_S * 1000)

        # Check for new result images
        images = _js_get_result_images(page)
        matching = [i for i in images if any(f in i["src"] for f in src_filter)]

        if len(matching) > before_count:
            # New image(s) with expected pattern — pick the first new one
            new_img = matching[0]  # newest is at top (lowest y)
            return GenerationResult(
                success=True,
                image_url=new_img["src"],
                duration_s=time.monotonic() - start,
            )

        # Fallback: ANY new result image (URL pattern may differ)
        if len(images) > all_before:
            new_img = images[0]  # newest at top
            return GenerationResult(
                success=True,
                image_url=new_img["src"],
                duration_s=time.monotonic() - start,
            )

        # Log progress
        progress = _js_get_progress(page)
        if progress:
            pct = progress[0]["pct"]
            if pct != last_pct:
                print(f"[dzine] Generation progress: {pct}", file=sys.stderr)
                last_pct = pct

    return GenerationResult(
        success=False,
        duration_s=time.monotonic() - start,
        error=f"Generation timed out after {GENERATION_TIMEOUT_S}s",
    )


# ---------------------------------------------------------------------------
# Image download
# ---------------------------------------------------------------------------


def _download_image(url: str, dest: Path) -> bool:
    """Download an image from a URL to a local path."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
        if len(data) < 1024:
            print(f"[dzine] Downloaded image too small ({len(data)} bytes): {url}",
                  file=sys.stderr)
            return False
        dest.write_bytes(data)
        return True
    except Exception as exc:
        print(f"[dzine] Download failed: {exc}", file=sys.stderr)
        return False


# ---------------------------------------------------------------------------
# Vision-based image QA (Claude API)
# ---------------------------------------------------------------------------

_VISION_API_URL = "https://api.anthropic.com/v1/messages"
_VISION_MODEL = "claude-haiku-4-5-20251001"  # fast + cheap for QA
_VISION_TIMEOUT = 60

_IMAGE_QA_PROMPT = """\
You are an image quality analyst for product photography used in YouTube review videos.

Analyze this generated product image and rate it on these criteria (0-10 each):

1. **product_intact**: Is the product complete? No clipping, no missing parts, no erasure.
2. **color_fidelity**: Does the product look like a natural, realistic color? (If reference provided, compare.)
3. **no_phone_fragments**: Are there any rectangular phone-shaped artifacts or ghost fragments on the edges?
4. **no_ghosting**: Are there smoky/hazy transparency artifacts on product edges?
5. **background_quality**: Is the background professional, clean, appropriate for a product review?
6. **overall_composition**: Is the product well-centered, good lighting, visually appealing?

Respond ONLY with this JSON (no markdown, no extra text):
{"product_intact": N, "color_fidelity": N, "no_phone_fragments": N, "no_ghosting": N, "background_quality": N, "overall_composition": N, "total": N, "issues": ["issue1", ...], "video_ready": true/false}

- "total" = average of all 6 scores
- "video_ready" = true only if total >= 7.0 AND no_phone_fragments >= 8 AND no_ghosting >= 8
- "issues" = list of specific problems found (empty if none)
"""


@dataclass
class ImageQAResult:
    """Result of vision-based image quality analysis."""
    product_intact: float = 0.0
    color_fidelity: float = 0.0
    no_phone_fragments: float = 0.0
    no_ghosting: float = 0.0
    background_quality: float = 0.0
    overall_composition: float = 0.0
    total: float = 0.0
    issues: list[str] = field(default_factory=list)
    video_ready: bool = False
    error: str = ""


def _analyze_image_qa(image_data: bytes, *, ref_data: bytes | None = None) -> ImageQAResult:
    """Analyze a product image using Claude Vision API.

    Args:
        image_data: Raw bytes of the generated image.
        ref_data: Optional raw bytes of the Amazon reference image for comparison.

    Returns ImageQAResult with scores and issues.
    """
    import base64
    import ssl

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return ImageQAResult(error="ANTHROPIC_API_KEY not set, skipping vision QA")

    # Build content blocks
    content: list[dict] = []

    # Reference image (if available)
    if ref_data:
        content.append({"type": "text", "text": "Reference product image (from Amazon listing):"})
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": _guess_media_type(ref_data),
                "data": base64.b64encode(ref_data).decode("ascii"),
            },
        })

    # Generated image
    label = "Generated product image to evaluate:" if not ref_data else "Generated image to evaluate (compare against reference above):"
    content.append({"type": "text", "text": label})
    content.append({
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": _guess_media_type(image_data),
            "data": base64.b64encode(image_data).decode("ascii"),
        },
    })

    content.append({"type": "text", "text": _IMAGE_QA_PROMPT})

    payload = {
        "model": _VISION_MODEL,
        "max_tokens": 512,
        "temperature": 0.0,
        "messages": [{"role": "user", "content": content}],
    }
    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
    }

    try:
        import json as _json
        data = _json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(_VISION_API_URL, data=data, headers=headers, method="POST")
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, timeout=_VISION_TIMEOUT, context=ctx) as resp:
            body = _json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        return ImageQAResult(error=f"Vision API call failed: {exc}")

    # Parse response
    text = ""
    for block in body.get("content", []):
        if block.get("type") == "text":
            text += block.get("text", "")

    if not text.strip():
        return ImageQAResult(error="Empty response from vision API")

    try:
        import json as _json
        # Strip markdown fences if present
        clean = text.strip()
        if clean.startswith("```"):
            clean = clean.split("\n", 1)[1] if "\n" in clean else clean[3:]
            clean = clean.rsplit("```", 1)[0]
        result = _json.loads(clean)
    except (ValueError, KeyError) as exc:
        return ImageQAResult(error=f"Failed to parse vision response: {exc}\nRaw: {text[:200]}")

    return ImageQAResult(
        product_intact=float(result.get("product_intact", 0)),
        color_fidelity=float(result.get("color_fidelity", 0)),
        no_phone_fragments=float(result.get("no_phone_fragments", 0)),
        no_ghosting=float(result.get("no_ghosting", 0)),
        background_quality=float(result.get("background_quality", 0)),
        overall_composition=float(result.get("overall_composition", 0)),
        total=float(result.get("total", 0)),
        issues=result.get("issues", []),
        video_ready=bool(result.get("video_ready", False)),
    )


def _guess_media_type(data: bytes) -> str:
    """Guess image media type from magic bytes."""
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    return "image/png"  # safe default


def _select_best_image(
    urls: list[str],
    dest: Path,
    *,
    ref_path: Path | None = None,
) -> str | None:
    """Download all candidate images and pick the best one using vision QA.

    Strategy:
    1. Download all candidates
    2. Run Claude Vision QA on each (if API key available)
    3. Pick the one with highest total score
    4. Fallback to largest file size if vision unavailable

    Returns the URL of the best image (already saved to dest), or None on failure.
    """
    if not urls:
        return None
    if len(urls) == 1:
        if _download_image(urls[0], dest):
            # Still run QA on single image for logging
            qa = _analyze_image_qa(dest.read_bytes())
            if not qa.error:
                _log_qa("single", qa)
            return urls[0]
        return None

    # Download all candidates
    candidates: list[tuple[str, bytes]] = []
    for url in urls:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = resp.read()
            if len(data) >= 1024:
                candidates.append((url, data))
        except Exception:
            continue

    if not candidates:
        return None

    # Load reference image for comparison
    ref_data = None
    if ref_path and ref_path.exists():
        try:
            ref_data = ref_path.read_bytes()
        except OSError:
            pass

    # Try vision-based selection
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if api_key and len(candidates) > 1:
        scored: list[tuple[str, bytes, ImageQAResult]] = []
        for url, data in candidates:
            qa = _analyze_image_qa(data, ref_data=ref_data)
            scored.append((url, data, qa))
            if not qa.error:
                _log_qa(url.split("/")[-1][:30], qa)

        # Filter to those with successful QA
        with_scores = [(u, d, q) for u, d, q in scored if not q.error]
        if with_scores:
            # Sort by total score (descending), then by file size as tiebreaker
            with_scores.sort(key=lambda x: (x[2].total, len(x[1])), reverse=True)
            best_url, best_data, best_qa = with_scores[0]
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(best_data)
            print(f"[dzine] Vision QA selected best of {len(candidates)}: "
                  f"score={best_qa.total:.1f}/10, "
                  f"video_ready={best_qa.video_ready}, "
                  f"size={len(best_data) // 1024}KB",
                  file=sys.stderr)
            if best_qa.issues:
                print(f"[dzine] QA issues: {', '.join(best_qa.issues)}", file=sys.stderr)
            return best_url

    # Fallback: pick by file size
    candidates.sort(key=lambda x: len(x[1]), reverse=True)
    best_url, best_data = candidates[0]
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(best_data)
    print(f"[dzine] Selected best of {len(candidates)} by size: "
          f"{len(best_data) // 1024}KB", file=sys.stderr)
    return best_url


def _log_qa(label: str, qa: ImageQAResult) -> None:
    """Log QA result to stderr."""
    print(f"[dzine] QA {label}: total={qa.total:.1f} "
          f"intact={qa.product_intact:.0f} color={qa.color_fidelity:.0f} "
          f"phone={qa.no_phone_fragments:.0f} ghost={qa.no_ghosting:.0f} "
          f"bg={qa.background_quality:.0f} comp={qa.overall_composition:.0f}"
          + (f" ISSUES: {qa.issues}" if qa.issues else ""),
          file=sys.stderr)


def analyze_generated_image(
    image_path: Path,
    *,
    ref_path: Path | None = None,
) -> ImageQAResult:
    """Public API: analyze a generated image for video-readiness.

    Sends the image to Claude Vision for quality assessment.
    Optionally compares against a reference product photo.

    Args:
        image_path: Path to the generated product image
        ref_path: Optional path to the Amazon reference image

    Returns ImageQAResult with scores and video_ready flag.
    """
    if not image_path.exists():
        return ImageQAResult(error=f"Image not found: {image_path}")

    image_data = image_path.read_bytes()
    ref_data = None
    if ref_path and ref_path.exists():
        ref_data = ref_path.read_bytes()

    qa = _analyze_image_qa(image_data, ref_data=ref_data)
    if not qa.error:
        _log_qa(image_path.name, qa)
    return qa


def _file_sha256(path: Path) -> str:
    """Compute SHA-256 hex digest."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# High-level API: generate_thumbnail
# ---------------------------------------------------------------------------


def generate_thumbnail(
    product_name: str,
    *,
    prompt_override: str = "",
    output_path: Path | None = None,
    use_face_match: bool = False,
) -> GenerationResult:
    """Generate a YouTube thumbnail image via Txt2Img.

    Args:
        product_name: Main product name for prompt template
        prompt_override: Full custom prompt (skips template)
        output_path: Where to save the image (default: artifacts/dzine/thumbnail.png)
        use_face_match: If True, enables Face Match with RAY_REFERENCE_FACE
                        for thumbnails that include Ray's face.

    Returns GenerationResult with local_path on success.
    """
    from tools.lib.brave_profile import log_action
    from tools.lib.dzine_schema import PROMPT_TEMPLATES

    prompt = prompt_override or PROMPT_TEMPLATES["thumbnail"].format(
        product_name=product_name, key_message=""
    )

    log_action("dzine_thumbnail", f"product={product_name[:40]}")

    def _attempt():
        start = time.monotonic()
        try:
            page, is_new = _get_or_create_page()
        except RuntimeError as exc:
            return GenerationResult(success=False, error=str(exc))

        try:
            _ensure_canvas_page(page)
            if not ensure_logged_in(page):
                return GenerationResult(success=False, duration_s=time.monotonic() - start,
                                        error="Not logged in to Dzine")
            _exit_tool_mode(page)

            # Enable Face Match with Ray's canonical face for thumbnails
            if use_face_match and RAY_REFERENCE_FACE.exists():
                _set_txt2img_face_match(page, str(RAY_REFERENCE_FACE))

            result = _generate_txt2img(page, prompt, aspect_16_9=True)
            if not result.success:
                return result

            # Download the generated image
            dest = output_path or (project_root() / "artifacts" / "dzine" / "thumbnail.png")
            if not _download_image(result.image_url, dest):
                return GenerationResult(
                    success=False, image_url=result.image_url,
                    duration_s=time.monotonic() - start,
                    error="Image download failed",
                )

            # Validate downloaded image
            valid, err = validate_image(dest)
            if not valid:
                return GenerationResult(
                    success=False, image_url=result.image_url,
                    local_path=str(dest), duration_s=time.monotonic() - start,
                    error=f"Image validation failed: {err}",
                )

            log_action("dzine_thumbnail_done", f"path={dest}")
            return GenerationResult(
                success=True,
                local_path=str(dest),
                image_url=result.image_url,
                checksum_sha256=_file_sha256(dest),
                duration_s=time.monotonic() - start,
            )

        except Exception as exc:
            return GenerationResult(
                success=False, duration_s=time.monotonic() - start, error=str(exc),
            )

    return _with_retry(_attempt, label="thumbnail")


# ---------------------------------------------------------------------------
# High-level API: generate_img2img_variant
# ---------------------------------------------------------------------------


def generate_img2img_variant(
    prompt: str,
    *,
    output_path: Path | None = None,
    quality: str = "2K",
    model: str = "",
) -> GenerationResult:
    """Transform an existing canvas image using Img2Img.

    Requires an image already on the canvas (place a result image first).

    Args:
        prompt: Description of desired transformation
        output_path: Where to save the image (optional)
        quality: Output quality — "1K", "2K" (default), or "4K"
        model: Optional model name

    Returns GenerationResult with local_path on success.
    """
    from tools.lib.brave_profile import log_action

    log_action("dzine_img2img", f"prompt={prompt[:40]}")

    def _attempt():
        start = time.monotonic()
        try:
            page, is_new = _get_or_create_page()
        except RuntimeError as exc:
            return GenerationResult(success=False, error=str(exc))

        try:
            _ensure_canvas_page(page)
            if not ensure_logged_in(page):
                return GenerationResult(success=False, duration_s=time.monotonic() - start,
                                        error="Not logged in to Dzine")
            _exit_tool_mode(page)

            result = _generate_img2img(page, prompt, quality=quality, model=model)
            if not result.success:
                return result

            if output_path and result.image_url:
                if not _download_image(result.image_url, output_path):
                    return GenerationResult(
                        success=False, image_url=result.image_url,
                        duration_s=time.monotonic() - start,
                        error="Image download failed",
                    )

                valid, err = validate_image(output_path)
                if not valid:
                    return GenerationResult(
                        success=False, image_url=result.image_url,
                        local_path=str(output_path), duration_s=time.monotonic() - start,
                        error=f"Image validation failed: {err}",
                    )

                log_action("dzine_img2img_done", f"path={output_path}")
                return GenerationResult(
                    success=True,
                    local_path=str(output_path),
                    image_url=result.image_url,
                    checksum_sha256=_file_sha256(output_path),
                    duration_s=time.monotonic() - start,
                )

            return result

        except Exception as exc:
            return GenerationResult(
                success=False, duration_s=time.monotonic() - start, error=str(exc),
            )

    return _with_retry(_attempt, label="img2img")


# ---------------------------------------------------------------------------
# High-level API: generate_ray_scene
# ---------------------------------------------------------------------------


def generate_ray_scene(
    scene_prompt: str,
    *,
    output_path: Path | None = None,
    reference_image: str = "",
) -> GenerationResult:
    """Generate a Consistent Character image with Ray.

    For thumbnail intros, review scenes, or any image that needs
    Ray's consistent identity.

    ALWAYS uses the canonical Ray reference face (RAY_REFERENCE_FACE) unless
    an explicit reference_image is provided. This ensures face consistency
    across all generations.

    Args:
        scene_prompt: Description of the scene (Ray is auto-selected)
        output_path: Where to save (optional)
        reference_image: Override reference image path. Defaults to RAY_REFERENCE_FACE.

    Returns GenerationResult with local_path on success.
    """
    from tools.lib.brave_profile import log_action

    # Always use canonical Ray face unless explicitly overridden
    if not reference_image and RAY_REFERENCE_FACE.exists():
        reference_image = str(RAY_REFERENCE_FACE)

    log_action("dzine_ray_scene", f"prompt={scene_prompt[:40]}")

    def _attempt():
        start = time.monotonic()
        try:
            page, is_new = _get_or_create_page()
        except RuntimeError as exc:
            return GenerationResult(success=False, error=str(exc))

        try:
            _ensure_canvas_page(page)
            if not ensure_logged_in(page):
                return GenerationResult(success=False, duration_s=time.monotonic() - start,
                                        error="Not logged in to Dzine")
            _exit_tool_mode(page)

            result = _generate_cc(page, scene_prompt, reference_image=reference_image)
            if not result.success:
                return result

            if output_path and result.image_url:
                if not _download_image(result.image_url, output_path):
                    return GenerationResult(
                        success=False, image_url=result.image_url,
                        duration_s=time.monotonic() - start,
                        error="Image download failed",
                    )

                valid, err = validate_image(output_path)
                if not valid:
                    return GenerationResult(
                        success=False, image_url=result.image_url,
                        local_path=str(output_path), duration_s=time.monotonic() - start,
                        error=f"Image validation failed: {err}",
                    )

                log_action("dzine_ray_done", f"path={output_path}")
                return GenerationResult(
                    success=True,
                    local_path=str(output_path),
                    image_url=result.image_url,
                    checksum_sha256=_file_sha256(output_path),
                    duration_s=time.monotonic() - start,
                )

            return result

        except Exception as exc:
            return GenerationResult(
                success=False, duration_s=time.monotonic() - start, error=str(exc),
            )

    return _with_retry(_attempt, label="ray_scene")


# ---------------------------------------------------------------------------
# High-level API: generate_variant
# ---------------------------------------------------------------------------


def generate_variant(
    req: DzineRequest,
    *,
    output_path: Path | None = None,
) -> GenerationResult:
    """Generate a single product variant image.

    When reference_image is set: uploads the Amazon image to canvas and uses
    Img2Img to create a faithful studio-quality version.
    When no reference_image: uses Txt2Img to generate from scratch.

    Args:
        req: DzineRequest with prompt already populated
        output_path: Where to save the image

    Returns GenerationResult with local_path on success.
    """
    from tools.lib.brave_profile import log_action

    if not req.prompt:
        return GenerationResult(success=False, error="DzineRequest has no prompt — call build_prompts() first")

    use_img2img = bool(req.reference_image and Path(req.reference_image).is_file())
    mode = "img2img" if use_img2img else "txt2img"
    log_action("dzine_variant", f"type={req.asset_type} variant={req.image_variant} mode={mode}")

    def _attempt():
        start = time.monotonic()
        try:
            page, is_new = _get_or_create_page()
        except RuntimeError as exc:
            return GenerationResult(success=False, error=str(exc))

        try:
            _ensure_canvas_page(page)
            if not ensure_logged_in(page):
                return GenerationResult(success=False, duration_s=time.monotonic() - start,
                                        error="Not logged in to Dzine")
            _exit_tool_mode(page)

            from tools.lib.dzine_schema import recommended_model
            model = recommended_model(req.asset_type, req.image_variant)

            if use_img2img:
                # Upload Amazon image to canvas, then Img2Img for faithful reproduction
                if not _upload_image_to_canvas(page, req.reference_image):
                    return GenerationResult(success=False, duration_s=time.monotonic() - start,
                                            error="Failed to upload reference image to canvas")
                result = _generate_img2img(page, req.prompt, quality="2K", model=model)
                # Clean up: delete the uploaded layer so next generation starts clean
                try:
                    page.mouse.click(720, 450)
                    page.wait_for_timeout(300)
                    page.keyboard.press("Delete")
                    page.wait_for_timeout(500)
                except Exception:
                    pass
            else:
                # No reference — generate from scratch via Txt2Img
                is_16_9 = req.image_variant != "detail"
                result = _generate_txt2img(page, req.prompt, aspect_16_9=is_16_9, model=model)

            if not result.success:
                return result

            dest = output_path
            if dest and result.image_url:
                if not _download_image(result.image_url, dest):
                    return GenerationResult(
                        success=False, image_url=result.image_url,
                        duration_s=time.monotonic() - start,
                        error="Image download failed",
                    )

                valid, err = validate_image(dest)
                if not valid:
                    return GenerationResult(
                        success=False, image_url=result.image_url,
                        local_path=str(dest), duration_s=time.monotonic() - start,
                        error=f"Image validation failed: {err}",
                    )

                log_action("dzine_variant_done", f"path={dest}")
                return GenerationResult(
                    success=True,
                    local_path=str(dest),
                    image_url=result.image_url,
                    checksum_sha256=_file_sha256(dest),
                    duration_s=time.monotonic() - start,
                )

            return result

        except Exception as exc:
            return GenerationResult(
                success=False, duration_s=time.monotonic() - start, error=str(exc),
            )

    return _with_retry(_attempt, label=f"variant_{req.image_variant}")


# ---------------------------------------------------------------------------
# High-level API: generate_product_set
# ---------------------------------------------------------------------------


def generate_product_set(
    video_id: str,
    products: list[dict],
    niche: str = "",
) -> dict:
    """Generate all Dzine images for a video's product set.

    Generates thumbnail + per-product variants based on rank hierarchy.

    Args:
        video_id: Video identifier for file paths
        products: List of product dicts from products.json
                  (must have 'name', 'rank', optionally 'image_url')
        niche: Niche keyword for category detection

    Returns dict with:
        - generated: list of {rank, variant, path, url, sha256}
        - failed: list of {rank, variant, error}
        - thumbnail: {path, url, sha256} or None
    """
    from tools.lib.dzine_schema import (
        DzineRequest, build_prompts, detect_category, variants_for_rank,
    )
    from tools.lib.notify import notify_progress
    from tools.lib.video_paths import VideoPaths

    vp = VideoPaths(video_id)
    vp.ensure_dirs()

    category = detect_category(niche) if niche else "default"

    generated = []
    failed = []
    thumbnail_result = None
    total_count = 0

    # 1. Generate thumbnail (Txt2Img)
    top_product = next((p for p in products if p.get("rank") == 1), products[0] if products else None)
    if top_product:
        print(f"[dzine] Generating thumbnail for: {top_product['name']}", file=sys.stderr)
        thumb = generate_thumbnail(
            top_product["name"],
            output_path=vp.thumbnail_path(),
        )
        if thumb.success:
            thumbnail_result = {
                "path": thumb.local_path,
                "url": thumb.image_url,
                "sha256": thumb.checksum_sha256,
            }
            # Save prompt
            vp.thumbnail_prompt_path().parent.mkdir(parents=True, exist_ok=True)
            vp.thumbnail_prompt_path().write_text(
                f"Product: {top_product['name']}\n\nGenerated via Txt2Img"
            )
            total_count += 1
        else:
            failed.append({"rank": 1, "variant": "thumbnail", "error": thumb.error})

    # 2. Generate per-product variants
    for product in sorted(products, key=lambda p: p.get("rank", 99)):
        rank = product.get("rank", 0)
        name = product.get("name", "Unknown Product")
        variants = variants_for_rank(rank)

        for variant in variants:
            print(f"[dzine] Generating {variant} for rank #{rank}: {name}", file=sys.stderr)

            req = DzineRequest(
                asset_type="product",
                product_name=name,
                image_variant=variant,
                niche_category=category,
                reference_image=product.get("reference_image", ""),
            )
            req = build_prompts(req)

            dest = vp.product_image_path(rank, variant)
            result = generate_variant(req, output_path=dest)

            if result.success:
                generated.append({
                    "rank": rank,
                    "variant": variant,
                    "path": result.local_path,
                    "url": result.image_url,
                    "sha256": result.checksum_sha256,
                })
                # Save prompt
                prompt_path = vp.product_prompt_path(rank, variant)
                prompt_path.parent.mkdir(parents=True, exist_ok=True)
                prompt_path.write_text(req.prompt)
                total_count += 1
            else:
                failed.append({"rank": rank, "variant": variant, "error": result.error})
                print(f"[dzine] FAILED {variant} for rank #{rank}: {result.error}",
                      file=sys.stderr)

            # Progress notification every 5 images
            if total_count > 0 and total_count % 5 == 0:
                try:
                    notify_progress(video_id, "assets",
                                    f"Dzine: {total_count} images generated "
                                    f"({len(failed)} failed)")
                except Exception:
                    pass

            # Brief pause between generations to avoid rate limiting
            time.sleep(2)

    # Close the shared session after batch is done
    close_session()

    return {
        "generated": generated,
        "failed": failed,
        "thumbnail": thumbnail_result,
        "total": total_count,
        "total_failed": len(failed),
    }


# ---------------------------------------------------------------------------
# High-level API: generate_product_faithful
# ---------------------------------------------------------------------------


def _create_project_from_image(context, image_path: str):
    """Create a new Dzine project from a product image. Returns (page, canvas_url)."""
    page = context.new_page()
    page.set_viewport_size(VIEWPORT)

    page.goto("https://www.dzine.ai/home", wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(4000)
    close_all_dialogs(page)

    try:
        with page.expect_file_chooser(timeout=8000) as fc_info:
            page.evaluate("""() => {
                for (var el of document.querySelectorAll('.project-item')) {
                    var text = (el.innerText || '').trim().toLowerCase();
                    if (text.includes('start from an image')) { el.click(); return; }
                }
            }""")
        fc = fc_info.value
        fc.set_files(image_path)
        page.wait_for_timeout(8000)
        close_all_dialogs(page)
    except Exception as e:
        print(f"[dzine] Start from image failed: {e}", file=sys.stderr)
        page.close()
        return None, None

    if "/canvas" not in page.url:
        print(f"[dzine] Not on canvas after upload: {page.url}", file=sys.stderr)
        page.close()
        return None, None

    # Wait for canvas UI to load
    for i in range(40):
        loaded = page.evaluate("() => document.querySelectorAll('.tool-group').length")
        if loaded >= 5:
            page.wait_for_timeout(2000)
            break
        page.wait_for_timeout(1000)

    close_all_dialogs(page)
    return page, page.url


def _bg_remove(page) -> float:
    """Click BG Remove on action bar and wait. Returns duration in seconds."""
    page.mouse.click(700, 400)
    page.wait_for_timeout(500)

    page.evaluate("""() => {
        for (var el of document.querySelectorAll('*')) {
            if ((el.innerText || '').trim() === 'BG Remove') {
                var r = el.getBoundingClientRect();
                if (r.y > 50 && r.y < 120 && r.width > 0) { el.click(); return; }
            }
        }
    }""")

    start = time.monotonic()
    while time.monotonic() - start < 30:
        status = page.evaluate("""() => {
            for (var el of document.querySelectorAll('*')) {
                if ((el.innerText || '').trim() === 'Removing background...') return 'removing';
            }
            return 'done';
        }""")
        if status == 'done' and time.monotonic() - start > 2:
            break
        page.wait_for_timeout(1000)
    duration = time.monotonic() - start
    page.wait_for_timeout(2000)

    # Handle "Image Not Filling the Canvas" dialog
    try:
        fit_btn = page.locator('button:has-text("Fit to Content and Continue")')
        if fit_btn.count() > 0 and fit_btn.first.is_visible(timeout=2000):
            fit_btn.first.click()
            page.wait_for_timeout(1000)
    except Exception:
        pass

    close_all_dialogs(page)
    return duration


def _generative_expand(page, prompt: str, aspect: str = "16:9") -> list[str]:
    """Run Generative Expand. Returns list of result image URLs."""
    # Close existing panels, open Image Editor sidebar
    page.evaluate("""() => {
        for (var el of document.querySelectorAll('.c-gen-config.show .ico-close')) el.click();
        for (var el of document.querySelectorAll('.panels.show .ico-close')) el.click();
    }""")
    page.wait_for_timeout(500)
    # Toggle via another tool first, then Image Editor
    page.mouse.click(40, 766)
    page.wait_for_timeout(1500)
    page.evaluate("""() => {
        for (var el of document.querySelectorAll('.c-gen-config.show .ico-close')) el.click();
        for (var el of document.querySelectorAll('.panels.show .ico-close')) el.click();
    }""")
    page.wait_for_timeout(500)
    page.mouse.click(40, SIDEBAR["image_editor"][1])
    page.wait_for_timeout(2500)

    # Handle dialogs
    try:
        fit_btn = page.locator('button:has-text("Fit to Content and Continue")')
        if fit_btn.count() > 0 and fit_btn.first.is_visible(timeout=1000):
            fit_btn.first.click()
            page.wait_for_timeout(1000)
    except Exception:
        pass
    close_all_dialogs(page)

    # Click Expand
    page.evaluate("""() => {
        for (var el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            if (text === 'Expand') {
                var r = el.getBoundingClientRect();
                if (r.width > 0 && r.y > 70 && r.y < 700) { el.click(); return; }
            }
        }
    }""")
    page.wait_for_timeout(2000)
    close_all_dialogs(page)

    # Set aspect ratio
    _js_click_button_by_text(page, aspect)
    page.wait_for_timeout(500)

    # Set prompt
    page.evaluate("""(prompt) => {
        for (var ta of document.querySelectorAll('textarea')) {
            var r = ta.getBoundingClientRect();
            if (r.width > 100) {
                ta.value = prompt;
                ta.dispatchEvent(new Event('input', {bubbles: true}));
                return;
            }
        }
    }""", prompt)
    page.wait_for_timeout(500)

    # Count images before
    before_count = len(_js_get_result_images(page))

    # Click Generate 8 (visible Generate button in panel, x < 350)
    clicked = page.evaluate("""() => {
        for (var b of document.querySelectorAll('button')) {
            var text = (b.innerText || '').trim();
            var r = b.getBoundingClientRect();
            if (text.includes('Generate') && r.width > 0 && r.x < 350 && r.y > 300 && !b.disabled) {
                b.click();
                return true;
            }
        }
        return false;
    }""")
    if not clicked:
        print("[dzine] Could not click Expand Generate button", file=sys.stderr)
        return []

    page.wait_for_timeout(2000)
    close_all_dialogs(page)
    page.wait_for_timeout(1000)
    close_all_dialogs(page)

    # Wait for results (up to 120s)
    start = time.monotonic()
    while time.monotonic() - start < 120:
        close_all_dialogs(page)
        images = _js_get_result_images(page)
        if len(images) > before_count:
            new_urls = [i["src"] for i in images[before_count:]]
            return new_urls[:4]

        elapsed = int(time.monotonic() - start)
        if elapsed % 15 == 0:
            progress = _js_get_progress(page)
            pct = progress[0]["pct"] if progress else "?"
            print(f"[dzine] Expand: {elapsed}s... {pct}", file=sys.stderr)
        page.wait_for_timeout(3000)

    print("[dzine] Expand generation timed out", file=sys.stderr)
    return []


def _export_canvas(page, format: str = "PNG", scale: str = "2x") -> Path | None:
    """Export canvas as image. Returns path to downloaded file or None."""
    page.evaluate("""() => {
        for (var el of document.querySelectorAll('.c-gen-config.show .ico-close')) el.click();
        for (var el of document.querySelectorAll('.panels.show .ico-close')) el.click();
    }""")
    page.wait_for_timeout(500)

    # Click Export button (top right, y < 40)
    page.evaluate("""() => {
        for (var b of document.querySelectorAll('button')) {
            if ((b.innerText || '').trim() === 'Export') {
                var r = b.getBoundingClientRect();
                if (r.y < 40) { b.click(); return; }
            }
        }
    }""")
    page.wait_for_timeout(2000)

    # Select format
    _js_click_button_by_text(page, format)
    page.wait_for_timeout(300)

    # Select scale
    _js_click_button_by_text(page, scale)
    page.wait_for_timeout(300)

    # Uncheck watermark
    page.evaluate("""() => {
        var cb = document.querySelector('input[type="checkbox"]');
        if (cb && cb.checked) cb.click();
    }""")
    page.wait_for_timeout(300)

    # Export
    try:
        with page.expect_download(timeout=30000) as dl_info:
            page.evaluate("""() => {
                for (var b of document.querySelectorAll('button')) {
                    if ((b.innerText || '').trim().includes('Export canvas')) { b.click(); return; }
                }
            }""")
        dl = dl_info.value
        ext = format.lower()
        dest = Path(os.path.expanduser("~/Downloads")) / f"dzine_export_{int(time.time())}.{ext}"
        dl.save_as(str(dest))
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)
        return dest
    except Exception as exc:
        print(f"[dzine] Export failed: {exc}", file=sys.stderr)
        page.keyboard.press("Escape")
        return None


def _human_delay(page, min_ms: int = 800, max_ms: int = 2500) -> None:
    """Random delay to simulate human interaction timing."""
    page.wait_for_timeout(random.randint(min_ms, max_ms))


def _human_click(page, x: int, y: int, jitter: int = 3) -> None:
    """Click with small random offset to avoid pixel-perfect bot patterns."""
    dx = random.randint(-jitter, jitter)
    dy = random.randint(-jitter, jitter)
    page.mouse.click(x + dx, y + dy)


def _product_background(page, prompt: str) -> list[str]:
    """Open Product Background tool and generate scene with prompt.

    Returns list of result image URLs. Uses Image Editor > Product Background.
    The tool handles BG removal internally and generates a new background
    from the prompt, adjusting lighting and shadows automatically.

    Panel layout (discovered 2026-02-19):
      - Panel class: c-gen-config show float-gen-btn float-pro-img-gen-btn
      - Three tabs with class .pro-tab: Template | Prompt | Image
      - Prompt tab has two modes: Assisted Prompt (chips) and Manual Prompt (textarea)
      - Toggle: .to-manual-prompt.switch-prompt (click to switch to freeform)
      - Textarea placeholder: "Descreva tanto o produto quanto o ambiente..."
      - Generate button: class .generative, text "Generate" + credit count
    """
    # Close existing panels
    page.evaluate("""() => {
        for (var el of document.querySelectorAll('.c-gen-config.show .ico-close')) el.click();
        for (var el of document.querySelectorAll('.panels.show .ico-close')) el.click();
    }""")
    _human_delay(page, 400, 800)

    # Open Image Editor sidebar
    _human_click(page, 40, SIDEBAR["image_editor"][1])
    _human_delay(page, 1500, 2500)
    close_all_dialogs(page)

    # Scroll subtools panel to reveal Product Background (it's at the bottom)
    page.evaluate("""() => {
        var panel = document.querySelector('.subtools');
        if (panel) { panel.scrollTop = panel.scrollHeight; return true; }
        return false;
    }""")
    _human_delay(page, 400, 800)

    # Click "Background" subtool
    clicked = page.evaluate("""() => {
        for (const el of document.querySelectorAll('.subtool-item')) {
            var text = (el.innerText || '').trim();
            if (text === 'Background') { el.click(); return true; }
        }
        for (const el of document.querySelectorAll('[class*="subtool"]')) {
            var text = (el.innerText || '').trim().toLowerCase();
            if (text.includes('background')) { el.click(); return true; }
        }
        return false;
    }""")
    if not clicked:
        print("[dzine] Could not find Product Background tool", file=sys.stderr)
        return []

    _human_delay(page, 1500, 2500)
    close_all_dialogs(page)

    # Step A: Click "Prompt" tab (class .pro-tab, text "Prompt")
    prompt_tab_clicked = page.evaluate("""() => {
        for (var tab of document.querySelectorAll('.pro-tab')) {
            if ((tab.innerText || '').trim() === 'Prompt') {
                tab.click();
                return true;
            }
        }
        return false;
    }""")
    if not prompt_tab_clicked:
        print("[dzine] Could not find Prompt tab (.pro-tab)", file=sys.stderr)
        return []

    _human_delay(page, 800, 1200)

    # Step B: Switch to Manual Prompt mode (freeform textarea)
    # Click .to-manual-prompt to toggle from Assisted -> Manual mode
    page.evaluate("""() => {
        var el = document.querySelector('.to-manual-prompt');
        if (el) { el.click(); return true; }
        // Fallback: find smallest element with "Manual Prompt" text
        var best = null, bestArea = Infinity;
        for (var el of document.querySelectorAll('*')) {
            var t = (el.textContent || '').trim();
            if (t === 'Manual Prompt' && el.children.length < 3) {
                var r = el.getBoundingClientRect();
                var area = r.width * r.height;
                if (area > 0 && area < bestArea) { bestArea = area; best = el; }
            }
        }
        if (best) { best.click(); return true; }
        return false;
    }""")
    _human_delay(page, 800, 1200)

    # Step C: Fill the Manual Prompt textarea
    # Use nativeTextAreaValueSetter for React/Vue compatibility
    prompt_set = page.evaluate("""(prompt) => {
        for (var ta of document.querySelectorAll('textarea')) {
            var r = ta.getBoundingClientRect();
            var ph = (ta.placeholder || '').toLowerCase();
            if (r.width > 100 && (ph.includes('produto') || ph.includes('product') || ph.includes('ambiente'))) {
                ta.focus();
                var setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
                setter.call(ta, prompt);
                ta.dispatchEvent(new Event('input', {bubbles: true}));
                ta.dispatchEvent(new Event('change', {bubbles: true}));
                return 'native-setter';
            }
        }
        // Fallback: any visible textarea in left panel
        for (var ta of document.querySelectorAll('textarea')) {
            var r = ta.getBoundingClientRect();
            if (r.width > 80 && r.x < 350) {
                ta.focus();
                var setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
                setter.call(ta, prompt);
                ta.dispatchEvent(new Event('input', {bubbles: true}));
                ta.dispatchEvent(new Event('change', {bubbles: true}));
                return 'fallback-textarea';
            }
        }
        return false;
    }""", prompt)

    if not prompt_set:
        print("[dzine] Could not fill Product Background prompt textarea", file=sys.stderr)
        return []

    print(f"[dzine] Prompt set via: {prompt_set}", file=sys.stderr)
    _human_delay(page, 500, 1000)

    # Count images before generation
    before_count = len(_js_get_result_images(page))

    # Step D: Click Generate button
    # Button has class .generative and text "Generate" + credit count.
    # May report disabled=true in DOM even when visually enabled (React lag),
    # so we click via class .generative regardless of disabled state.
    clicked = page.evaluate("""() => {
        // Strategy 1: .generative button in left panel
        for (var b of document.querySelectorAll('button.generative, button[class*="generative"]')) {
            var r = b.getBoundingClientRect();
            if (r.width > 100 && r.x < 300) {
                b.click();
                return 'generative-class';
            }
        }
        // Strategy 2: button with "Generate" text in left panel
        for (var b of document.querySelectorAll('button')) {
            var text = (b.innerText || '').trim();
            var r = b.getBoundingClientRect();
            if (text.includes('Generate') && r.width > 100 && r.x < 300 && r.y > 400) {
                b.click();
                return 'generate-text';
            }
        }
        return false;
    }""")
    if not clicked:
        print("[dzine] Could not click Product Background Generate button", file=sys.stderr)
        return []

    print(f"[dzine] Product Background Generate clicked via: {clicked}", file=sys.stderr)
    _human_delay(page, 1500, 2500)
    close_all_dialogs(page)
    _human_delay(page, 800, 1500)
    close_all_dialogs(page)

    # Wait for results (up to 120s)
    start = time.monotonic()
    while time.monotonic() - start < GENERATION_TIMEOUT_S:
        close_all_dialogs(page)
        images = _js_get_result_images(page)
        if len(images) > before_count:
            new_urls = [i["src"] for i in images[before_count:]]
            return new_urls[:4]

        elapsed = int(time.monotonic() - start)
        if elapsed % 15 == 0:
            progress = _js_get_progress(page)
            pct = progress[0]["pct"] if progress else "?"
            print(f"[dzine] ProdBG: {elapsed}s... {pct}", file=sys.stderr)
        page.wait_for_timeout(random.randint(2500, 3500))

    print("[dzine] Product Background generation timed out", file=sys.stderr)
    return []


def generate_product_faithful(
    product_image_path: str,
    *,
    output_path: Path | None = None,
    backdrop_prompt: str = "Clean white studio backdrop with soft professional lighting, subtle shadow underneath product",
    aspect: str = "16:9",
    export_scale: str = "2x",
) -> GenerationResult:
    """Generate a product-faithful image preserving real product appearance.

    Uses Product Background tool (preferred) with fallback to BG Remove + Expand.
    The real product photo is preserved — only the background is AI-generated.

    Steps:
        1. Create new project from product image ("Start from an image")
        2. Product Background — generate scene background from prompt
           (handles BG removal + scene generation + lighting adjustment)
        3. Fallback: BG Remove + Generative Expand if Product Background fails
        4. Download best result

    Uses the shared session (same Playwright instance across calls).

    Args:
        product_image_path: Path to Amazon product photo (JPEG/PNG)
        output_path: Where to save the final image
        backdrop_prompt: Prompt for the background scene
        aspect: Aspect ratio for expand fallback ("16:9", "4:3", "1:1")
        export_scale: Export upscale ("1x", "2x", "4x")

    Returns GenerationResult with local_path on success.
    """
    from tools.lib.brave_profile import log_action

    log_action("dzine_product_faithful", f"image={Path(product_image_path).name}")

    if not os.path.exists(product_image_path):
        return GenerationResult(success=False, error=f"Product image not found: {product_image_path}")

    def _attempt():
        global _session_pw, _session_browser, _session_context, _session_page, _session_should_close
        start = time.monotonic()

        # Use shared session — reuses Playwright instance across calls
        try:
            if _session_context is None:
                from tools.lib.brave_profile import connect_or_launch
                browser, context, should_close, pw = connect_or_launch(headless=False)
                _session_pw = pw
                _session_browser = browser
                _session_context = context
                _session_should_close = should_close
            context = _session_context
        except RuntimeError as exc:
            return GenerationResult(success=False, error=str(exc))

        page = None
        try:
            # Step 1: Create project from product image
            print("[dzine] Creating project from product image...", file=sys.stderr)
            page, canvas_url = _create_project_from_image(context, product_image_path)
            if not page:
                return GenerationResult(success=False, duration_s=time.monotonic() - start,
                                        error="Failed to create project from image")

            print(f"[dzine] Canvas: {canvas_url}", file=sys.stderr)

            # Step 2: Remove background (required before Product Background)
            print("[dzine] Removing background...", file=sys.stderr)
            bg_time = _bg_remove(page)
            print(f"[dzine] BG Remove done in {bg_time:.0f}s", file=sys.stderr)
            _human_delay(page, 800, 1500)

            # Step 3: Product Background (preferred — generates scene from prompt)
            print("[dzine] Running Product Background...", file=sys.stderr)
            result_urls = _product_background(page, backdrop_prompt)

            # Step 3b: Fallback to Generative Expand if Product Background failed
            if not result_urls:
                print("[dzine] Product Background failed, falling back to Generative Expand...", file=sys.stderr)
                result_urls = _generative_expand(page, backdrop_prompt, aspect)

            if not result_urls:
                return GenerationResult(success=False, duration_s=time.monotonic() - start,
                                        error="Both Product Background and Expand produced no results")

            print(f"[dzine] Results: {len(result_urls)} images", file=sys.stderr)

            # Step 4: Download all candidates and pick the best one
            if output_path:
                dest = Path(output_path)
            else:
                dest = Path(os.path.expanduser("~/Downloads")) / f"dzine_faithful_{int(time.time())}.webp"

            best_url = _select_best_image(
                result_urls, dest,
                ref_path=Path(product_image_path) if product_image_path else None,
            )
            if not best_url:
                # Fallback: try export canvas instead
                print("[dzine] Direct download failed, trying export...", file=sys.stderr)
                export_dest = _export_canvas(page, "PNG", export_scale)
                if export_dest:
                    if output_path:
                        import shutil
                        shutil.move(str(export_dest), str(output_path))
                        dest = Path(output_path)
                    else:
                        dest = export_dest
                else:
                    return GenerationResult(success=False, duration_s=time.monotonic() - start,
                                            image_url=best_url, error="Failed to download or export")

            # Validate
            valid, err = validate_image(dest)
            if not valid:
                return GenerationResult(success=False, duration_s=time.monotonic() - start,
                                        image_url=best_url, local_path=str(dest),
                                        error=f"Validation failed: {err}")

            log_action("dzine_product_faithful_done", f"path={dest}")
            return GenerationResult(
                success=True,
                local_path=str(dest),
                image_url=best_url,
                checksum_sha256=_file_sha256(dest),
                duration_s=time.monotonic() - start,
            )

        except Exception as exc:
            return GenerationResult(
                success=False, duration_s=time.monotonic() - start, error=str(exc),
            )
        finally:
            # Only close the project page, not the shared session
            if page:
                try:
                    page.close()
                except Exception:
                    pass

    return _with_retry(_attempt, label="product_faithful")


# ---------------------------------------------------------------------------
# Face Swap with Ray's canonical face
# ---------------------------------------------------------------------------


def face_swap_ray(
    *,
    output_path: Path | None = None,
) -> GenerationResult:
    """Face-swap the current canvas image with Ray's canonical face.

    Requires an image already on the Dzine canvas (e.g., a generated result
    that was placed on canvas). Swaps any face in the image with the
    canonical RAY_REFERENCE_FACE.

    Cost: 4 credits per swap.

    Args:
        output_path: Where to save the result (optional).

    Returns GenerationResult with image URL on success.
    """
    from tools.lib.brave_profile import log_action

    log_action("dzine_face_swap_ray", "")

    if not RAY_REFERENCE_FACE.exists():
        return GenerationResult(
            success=False,
            error=f"Ray reference face not found: {RAY_REFERENCE_FACE}",
        )

    def _attempt():
        start = time.monotonic()
        try:
            page, is_new = _get_or_create_page()
        except RuntimeError as exc:
            return GenerationResult(success=False, error=str(exc))

        try:
            _ensure_canvas_page(page)
            if not ensure_logged_in(page):
                return GenerationResult(success=False, duration_s=time.monotonic() - start,
                                        error="Not logged in to Dzine")

            before_images = _js_get_result_images(page)

            # Open Image Editor sidebar → Face Kit → Face Swap
            page.mouse.click(*SIDEBAR["image_editor"])
            page.wait_for_timeout(2000)
            close_all_dialogs(page)

            # Click Face Swap option
            fs_clicked = page.evaluate("""() => {
                for (const el of document.querySelectorAll('*')) {
                    var text = (el.innerText || '').trim();
                    var r = el.getBoundingClientRect();
                    if (text === 'Face Swap' && r.x > 60 && r.x < 350
                        && r.width > 0 && r.height > 0 && r.height < 60) {
                        el.click(); return true;
                    }
                }
                return false;
            }""")
            if not fs_clicked:
                return GenerationResult(success=False, duration_s=time.monotonic() - start,
                                        error="Could not find Face Swap option")
            page.wait_for_timeout(2000)

            # Upload Ray's face via "Upload a Face Image" / pick-image button
            upload_pos = page.evaluate("""() => {
                for (const btn of document.querySelectorAll('button')) {
                    var classes = (btn.className || '').toString();
                    var r = btn.getBoundingClientRect();
                    if (classes.includes('pick-image') && r.x > 60 && r.x < 350 && r.width > 50) {
                        return {x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)};
                    }
                }
                return null;
            }""")
            if not upload_pos:
                return GenerationResult(success=False, duration_s=time.monotonic() - start,
                                        error="Could not find face upload button in Face Swap")

            # Open pick-panel and upload
            page.mouse.click(upload_pos['x'], upload_pos['y'])
            page.wait_for_timeout(1500)

            panel_upload = page.evaluate("""() => {
                var panel = document.querySelector('.pick-panel');
                if (!panel) return null;
                var btn = panel.querySelector('button.upload');
                if (!btn) return null;
                var r = btn.getBoundingClientRect();
                return {x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)};
            }""")
            if not panel_upload:
                return GenerationResult(success=False, duration_s=time.monotonic() - start,
                                        error="Pick-panel upload button not found for Face Swap")

            try:
                with page.expect_file_chooser(timeout=5000) as fc_info:
                    page.mouse.click(panel_upload['x'], panel_upload['y'])
                fc = fc_info.value
                fc.set_files(str(RAY_REFERENCE_FACE))
                page.wait_for_timeout(5000)
            except Exception as exc:
                return GenerationResult(success=False, duration_s=time.monotonic() - start,
                                        error=f"Face upload failed: {exc}")

            # Click Generate (Face Swap, 4 credits)
            gen_clicked = _js_click_button_by_text(page, "Generate", x_min=60, x_max=350)
            if not gen_clicked:
                close_all_dialogs(page)
                page.wait_for_timeout(1000)
                gen_clicked = _js_click_button_by_text(page, "Generate", x_min=60, x_max=350)
            if not gen_clicked:
                return GenerationResult(success=False, duration_s=time.monotonic() - start,
                                        error="Could not click Face Swap Generate button")

            # Wait for result
            result = _wait_for_cc_generation(page, len(before_images), start)
            if not result.success:
                return result

            # Download if output_path specified
            if output_path and result.image_url:
                if not _download_image(result.image_url, output_path):
                    return GenerationResult(success=False, image_url=result.image_url,
                                            duration_s=time.monotonic() - start,
                                            error="Face Swap download failed")
                valid, err = validate_image(output_path)
                if not valid:
                    return GenerationResult(success=False, image_url=result.image_url,
                                            local_path=str(output_path),
                                            duration_s=time.monotonic() - start,
                                            error=f"Validation failed: {err}")
                return GenerationResult(
                    success=True, local_path=str(output_path),
                    image_url=result.image_url,
                    checksum_sha256=_file_sha256(output_path),
                    duration_s=time.monotonic() - start,
                )

            return result

        except Exception as exc:
            return GenerationResult(
                success=False, duration_s=time.monotonic() - start, error=str(exc),
            )

    return _with_retry(_attempt, label="face_swap_ray")


def retrain_ray_character() -> bool:
    """Update the Dzine Ray character with the canonical reference face.

    Opens the Character tool > Build Your Character > Quick Mode,
    uploads RAY_REFERENCE_FACE, and saves. This ensures the CC system
    uses the correct, canonical face for all future generations.

    Returns True if the character was updated successfully.
    """
    if not RAY_REFERENCE_FACE.exists():
        print(f"[dzine] Ray reference face not found: {RAY_REFERENCE_FACE}", file=sys.stderr)
        return False

    try:
        page, is_new = _get_or_create_page()
    except RuntimeError as exc:
        print(f"[dzine] Browser connection failed: {exc}", file=sys.stderr)
        return False

    try:
        _ensure_canvas_page(page)
        if not ensure_logged_in(page):
            print("[dzine] Not logged in", file=sys.stderr)
            return False
        _exit_tool_mode(page)
        close_all_dialogs(page)

        # Open Character sidebar
        page.mouse.dblclick(*SIDEBAR["character"])
        page.wait_for_timeout(2000)
        close_all_dialogs(page)

        # Click "Build Your Character"
        build_clicked = page.evaluate("""() => {
            for (const el of document.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                var r = el.getBoundingClientRect();
                if (text.includes('Build Your Character') && r.x > 60 && r.y > 60
                    && r.height < 60 && r.width > 50) {
                    el.click(); return true;
                }
            }
            return false;
        }""")
        if not build_clicked:
            print("[dzine] Could not find 'Build Your Character' button", file=sys.stderr)
            return False
        page.wait_for_timeout(2000)
        close_all_dialogs(page)

        # Select Quick Mode (1 image)
        quick_clicked = page.evaluate("""() => {
            for (const el of document.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                var r = el.getBoundingClientRect();
                if (text === 'Quick Mode' && r.width > 0 && r.height > 0) {
                    el.click(); return true;
                }
            }
            return false;
        }""")
        if quick_clicked:
            page.wait_for_timeout(1500)

        # Upload the face image via file chooser
        try:
            with page.expect_file_chooser(timeout=8000) as fc_info:
                # Click upload area
                upload_clicked = page.evaluate("""() => {
                    for (const el of document.querySelectorAll('button, .upload-area, [class*="upload"]')) {
                        var r = el.getBoundingClientRect();
                        if (r.width > 100 && r.height > 100 && r.x > 60 && r.x < 400) {
                            el.click(); return true;
                        }
                    }
                    return false;
                }""")
                if not upload_clicked:
                    # Fallback: click center of expected upload area
                    page.mouse.click(200, 400)
            fc = fc_info.value
            fc.set_files(str(RAY_REFERENCE_FACE))
            page.wait_for_timeout(5000)
            close_all_dialogs(page)
        except Exception as exc:
            print(f"[dzine] Character upload failed: {exc}", file=sys.stderr)
            return False

        # Set character name to "Ray" if there's a name input
        page.evaluate("""() => {
            for (const input of document.querySelectorAll('input[type="text"]')) {
                var r = input.getBoundingClientRect();
                if (r.width > 100 && r.x > 60 && r.x < 400) {
                    input.value = 'Ray';
                    input.dispatchEvent(new Event('input', {bubbles: true}));
                    return true;
                }
            }
            return false;
        }""")
        page.wait_for_timeout(500)

        # Click Create/Save button
        save_clicked = page.evaluate("""() => {
            for (const btn of document.querySelectorAll('button')) {
                var text = (btn.innerText || '').trim();
                var r = btn.getBoundingClientRect();
                if ((text === 'Create' || text === 'Save' || text === 'Train'
                     || text.includes('Create Character'))
                    && !btn.disabled && r.width > 50 && r.x > 60 && r.x < 400) {
                    btn.click(); return true;
                }
            }
            return false;
        }""")
        if save_clicked:
            page.wait_for_timeout(10000)
            close_all_dialogs(page)
            print("[dzine] Ray character updated with canonical face", file=sys.stderr)
            return True
        else:
            print("[dzine] Could not find Create/Save button", file=sys.stderr)
            return False

    except Exception as exc:
        print(f"[dzine] Character retrain failed: {exc}", file=sys.stderr)
        return False


# ---------------------------------------------------------------------------
# Backward-compatible API (used by pipeline.py cmd_assets)
# ---------------------------------------------------------------------------


def generate_image(
    req: DzineRequest, *, output_path: Path | None = None
) -> GenerationResult:
    """Drive Dzine to generate a single image from a DzineRequest.

    Backward-compatible entry point used by pipeline.py.
    Routes to CC (Ray) or Txt2Img based on asset type.
    """
    from tools.lib.dzine_schema import build_prompts

    # Ensure prompts are populated
    if not req.prompt:
        req = build_prompts(req)

    # Route: avatar_base → CC (Ray), everything else → Txt2Img
    if req.asset_type == "avatar_base":
        return generate_ray_scene(req.prompt, output_path=output_path)

    return generate_variant(req, output_path=output_path)
