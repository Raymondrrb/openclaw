"""Playwright-based Dzine image generation automation.

Drives the Dzine web UI: login check, prompt entry, reference image upload,
generation, download. Uses headed mode for manual-assist visibility.
"""

from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from tools.lib.common import project_root
from tools.lib.control_plane import send_telegram
from tools.lib.dzine_schema import DzineRequest

# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass
class GenerationResult:
    success: bool
    local_path: str = ""
    checksum_sha256: str = ""
    duration_s: float = 0.0
    error: str = ""


# ---------------------------------------------------------------------------
# UI selectors — update here when Dzine redesigns
# ---------------------------------------------------------------------------

SELECTORS = {
    # Login state
    "avatar_or_profile": '[data-testid="user-avatar"], .user-profile, .avatar-icon',
    "login_button": 'a[href*="login"], button:has-text("Log in"), button:has-text("Sign in")',

    # Prompt input (Dzine uses a single main prompt box)
    "prompt_box": 'textarea[placeholder*="prompt"], textarea[placeholder*="Prompt"], #prompt-input, textarea.prompt-textarea',
    "negative_prompt_box": 'textarea[placeholder*="negative"], textarea[placeholder*="Negative"], #negative-prompt',

    # Reference image upload
    "upload_area": 'input[type="file"], [data-testid="image-upload"], .upload-area input',
    "upload_button": 'button:has-text("Upload"), button:has-text("Reference"), [data-testid="upload-ref"]',

    # Model / style selection
    "model_selector": '.model-select, [data-testid="model-selector"], button:has-text("Model")',
    "nano_banana_pro": 'text="NanoBanana Pro", [data-value="nano-banana-pro"]',

    # Resolution
    "width_input": 'input[name="width"], input[aria-label*="Width"], input[placeholder*="width"]',
    "height_input": 'input[name="height"], input[aria-label*="Height"], input[placeholder*="height"]',

    # Generation
    "generate_button": 'button:has-text("Generate"), button:has-text("Create"), button[data-testid="generate"]',

    # Result
    "result_image": '.result-image img, .generated-image img, [data-testid="result-image"]',
    "download_button": 'button:has-text("Download"), button:has-text("Export"), a[download]',

    # Export recovery (when download/export is disabled)
    "result_clickable": '.result-image, .generated-image, [data-testid="result-image"]',
    "image_editor_button": 'button:has-text("Image Editor"), button:has-text("Edit")',
    "layer_activate": '.layer-panel .layer:first-child, [data-testid="layer-0"]',
}

# Timeouts (ms)
GENERATION_TIMEOUT = int(os.environ.get("DZINE_GENERATION_TIMEOUT", "180000"))
MANUAL_ASSIST_TIMEOUT = int(os.environ.get("DZINE_MANUAL_ASSIST_TIMEOUT", "300"))

# Browser profile: uses the shared orange Brave profile managed by OpenClaw
# Connection handled by brave_profile.connect_or_launch()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _safe_click(page, selector: str, *, label: str = "", timeout: int = 10000) -> bool:
    """Click a selector, sending a Telegram alert + pausing on failure."""
    try:
        page.locator(selector).first.click(timeout=timeout)
        return True
    except Exception as exc:
        msg = f"Dzine selector failed: {label or selector}\nError: {exc}"
        print(f"[dzine] {msg}", file=sys.stderr)
        send_telegram(f"Manual assist needed\n\n{msg}")
        print(f"[dzine] Waiting up to {MANUAL_ASSIST_TIMEOUT}s for manual assist...", file=sys.stderr)
        try:
            page.locator(selector).first.wait_for(timeout=MANUAL_ASSIST_TIMEOUT * 1000)
            page.locator(selector).first.click(timeout=5000)
            return True
        except Exception:
            return False


def _safe_fill(page, selector: str, text: str, *, label: str = "", timeout: int = 10000) -> bool:
    """Fill a text field, sending a Telegram alert + pausing on failure."""
    try:
        loc = page.locator(selector).first
        loc.click(timeout=timeout)
        loc.fill(text, timeout=timeout)
        return True
    except Exception as exc:
        msg = f"Dzine fill failed: {label or selector}\nError: {exc}"
        print(f"[dzine] {msg}", file=sys.stderr)
        send_telegram(f"Manual assist needed\n\n{msg}")
        print(f"[dzine] Waiting up to {MANUAL_ASSIST_TIMEOUT}s for manual assist...", file=sys.stderr)
        try:
            page.locator(selector).first.wait_for(timeout=MANUAL_ASSIST_TIMEOUT * 1000)
            loc = page.locator(selector).first
            loc.click(timeout=5000)
            loc.fill(text, timeout=5000)
            return True
        except Exception:
            return False


def _upload_reference_image(page, image_path: str) -> bool:
    """Upload a reference image to Dzine via file input."""
    path = Path(image_path)
    if not path.is_file():
        print(f"[dzine] Reference image not found: {path}", file=sys.stderr)
        return False

    try:
        # Try to find the file input directly
        file_input = page.locator('input[type="file"]').first
        file_input.set_input_files(str(path), timeout=10000)
        page.wait_for_timeout(2000)  # wait for upload processing
        return True
    except Exception:
        pass

    # Fallback: click the upload button area, then set files
    try:
        _safe_click(page, SELECTORS["upload_button"], label="upload_button", timeout=5000)
        page.wait_for_timeout(500)
        file_input = page.locator('input[type="file"]').first
        file_input.set_input_files(str(path), timeout=10000)
        page.wait_for_timeout(2000)
        return True
    except Exception as exc:
        msg = f"Reference image upload failed: {exc}"
        print(f"[dzine] {msg}", file=sys.stderr)
        send_telegram(f"Manual assist needed\n\n{msg}\n\nImage: {path}")
        return False


def _download_with_recovery(
    page, asset_type: str, *, dest_path: Path | None = None
) -> Path | None:
    """Download the generated image, with export-disabled recovery.

    Recovery sequence (from operator manual):
    1. Click the result image
    2. Open Image Editor
    3. Activate the first layer
    4. Retry download/export

    If dest_path is provided, save to that path instead of artifacts/dzine/.
    """
    if dest_path:
        artifacts_dir = dest_path.parent
        filename = dest_path.name
    else:
        artifacts_dir = project_root() / "artifacts" / "dzine"
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        filename = f"{timestamp}-{asset_type}.png"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    # Try direct download first
    try:
        with page.expect_download(timeout=15000) as dl_info:
            _safe_click(page, SELECTORS["download_button"], label="download", timeout=10000)
        download = dl_info.value
        dest = artifacts_dir / filename
        download.save_as(str(dest))
        return dest
    except Exception:
        print("[dzine] Direct download failed, trying export recovery...", file=sys.stderr)

    # Export recovery sequence
    try:
        _safe_click(page, SELECTORS["result_clickable"], label="result_clickable", timeout=5000)
        page.wait_for_timeout(1000)
        _safe_click(page, SELECTORS["image_editor_button"], label="image_editor", timeout=5000)
        page.wait_for_timeout(2000)
        _safe_click(page, SELECTORS["layer_activate"], label="layer_activate", timeout=5000)
        page.wait_for_timeout(1000)

        with page.expect_download(timeout=15000) as dl_info:
            _safe_click(page, SELECTORS["download_button"], label="download_retry", timeout=10000)
        download = dl_info.value
        dest = artifacts_dir / filename
        download.save_as(str(dest))
        return dest
    except Exception as exc:
        print(f"[dzine] Export recovery also failed: {exc}", file=sys.stderr)

    # Last resort: screenshot the result
    try:
        result_loc = page.locator(SELECTORS["result_image"]).first
        dest = artifacts_dir / f"{timestamp}-{asset_type}-screenshot.png"
        result_loc.screenshot(path=str(dest), timeout=10000)
        print(f"[dzine] Saved screenshot fallback: {dest}", file=sys.stderr)
        return dest
    except Exception as exc:
        print(f"[dzine] Screenshot fallback failed: {exc}", file=sys.stderr)
        return None


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def generate_image(
    req: DzineRequest, *, output_path: Path | None = None
) -> GenerationResult:
    """Drive the Dzine web UI to generate an image.

    Connects to the running orange Brave via CDP (or launches it).
    Expects req to have prompts already built (via build_prompts).
    If output_path is provided, save the result to that path instead
    of the default artifacts/dzine/ directory.
    """
    try:
        from tools.lib.brave_profile import connect_or_launch, log_action
    except ImportError:
        return GenerationResult(
            success=False,
            error="brave_profile module not found",
        )

    base_url = os.environ.get("DZINE_BASE_URL", "https://www.dzine.ai")
    create_url = os.environ.get("DZINE_CREATE_URL", f"{base_url}/tools/z-image/")

    start = time.monotonic()
    log_action("dzine_generate", f"type={req.asset_type}")

    try:
        browser, context, should_close, pw = connect_or_launch(headless=False)
    except RuntimeError as exc:
        return GenerationResult(success=False, error=str(exc))

    page = context.new_page()

    try:
        # Navigate to create page
        page.goto(create_url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(2000)

        # Check login state
        logged_in = page.locator(SELECTORS["avatar_or_profile"]).first.is_visible(timeout=5000)
        if not logged_in:
            msg = "Dzine login required — please log in within 5 minutes"
            print(f"[dzine] {msg}", file=sys.stderr)
            send_telegram(f"{msg}\n\nURL: {create_url}")
            try:
                page.locator(SELECTORS["avatar_or_profile"]).first.wait_for(
                    state="visible", timeout=MANUAL_ASSIST_TIMEOUT * 1000
                )
            except Exception:
                return GenerationResult(
                    success=False,
                    duration_s=time.monotonic() - start,
                    error="Login timeout — manual login not completed in time",
                )

        # Upload reference image if provided
        if req.reference_image:
            if not _upload_reference_image(page, req.reference_image):
                print("[dzine] Reference image upload failed, continuing without it", file=sys.stderr)

        # Fill main prompt
        if req.prompt:
            if not _safe_fill(page, SELECTORS["prompt_box"], req.prompt, label="prompt"):
                return GenerationResult(
                    success=False,
                    duration_s=time.monotonic() - start,
                    error="Failed to fill prompt",
                )

        # Fill negative prompt
        if req.negative_prompt:
            _safe_fill(page, SELECTORS["negative_prompt_box"], req.negative_prompt, label="negative_prompt")

        # Select model (NanoBanana Pro)
        _safe_click(page, SELECTORS["model_selector"], label="model_selector", timeout=5000)
        page.wait_for_timeout(500)
        _safe_click(page, SELECTORS["nano_banana_pro"], label="nano_banana_pro", timeout=5000)

        # Set resolution
        if req.width and req.height:
            _safe_fill(page, SELECTORS["width_input"], str(req.width), label="width", timeout=5000)
            _safe_fill(page, SELECTORS["height_input"], str(req.height), label="height", timeout=5000)

        # Click Generate
        if not _safe_click(page, SELECTORS["generate_button"], label="generate"):
            return GenerationResult(
                success=False,
                duration_s=time.monotonic() - start,
                error="Failed to click Generate button",
            )

        # Wait for generation to complete (locator-based, no fixed sleep)
        try:
            page.locator(SELECTORS["result_image"]).first.wait_for(
                state="visible", timeout=GENERATION_TIMEOUT
            )
        except Exception:
            return GenerationResult(
                success=False,
                duration_s=time.monotonic() - start,
                error=f"Generation timed out after {GENERATION_TIMEOUT}ms",
            )

        # Download the result
        dest = _download_with_recovery(page, req.asset_type, dest_path=output_path)
        if dest is None:
            return GenerationResult(
                success=False,
                duration_s=time.monotonic() - start,
                error="All download methods failed",
            )

        # Compute checksum
        from tools.lib.supabase_storage import file_sha256
        checksum = file_sha256(dest)

        log_action("dzine_generate_done", f"path={dest}")
        return GenerationResult(
            success=True,
            local_path=str(dest),
            checksum_sha256=checksum,
            duration_s=time.monotonic() - start,
        )

    except Exception as exc:
        return GenerationResult(
            success=False,
            duration_s=time.monotonic() - start,
            error=str(exc),
        )
    finally:
        page.close()
        if should_close:
            context.close()
        pw.stop()
