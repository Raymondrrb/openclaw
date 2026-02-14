"""Phase 120: Practical end-to-end generation test.
P119 mapped all Image Editor sub-tools, Chat Editor, Enhance & Upscale.

Goal: 1) Generate a Txt2Img image with a real prompt (Fast mode, 2 credits)
      2) Wait for generation to complete
      3) Download the result image
      4) Verify file size and format
      5) Test the "place on canvas" action
      6) Test Img2Img with the placed image
"""

import json
import os
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from playwright.sync_api import sync_playwright

CANVAS_URL = "https://www.dzine.ai/canvas?id=19797967"
SS_DIR = Path(__file__).resolve().parent.parent / "artifacts" / "dzine_explore"
SS_DIR.mkdir(parents=True, exist_ok=True)
DOWNLOAD_DIR = Path.home() / "Downloads"


def ss(page, name):
    page.screenshot(path=str(SS_DIR / f"{name}.png"))
    print(f"  SS: {name}", flush=True)


def close_dialogs(page):
    for _ in range(8):
        found = False
        for text in ["Not now", "Close", "Never show again", "Got it", "Skip", "Later"]:
            try:
                btn = page.locator(f'button:has-text("{text}")')
                if btn.count() > 0 and btn.first.is_visible(timeout=500):
                    btn.first.click()
                    page.wait_for_timeout(500)
                    found = True
            except Exception:
                pass
        if not found:
            break


def wait_for_canvas(page, max_wait=40):
    for i in range(max_wait):
        loaded = page.evaluate("() => document.querySelectorAll('.tool-group').length")
        if loaded >= 5:
            print(f"  Canvas loaded ({loaded} tool groups) after {i+1}s", flush=True)
            page.wait_for_timeout(2000)
            return True
        page.wait_for_timeout(1000)
    return False


def cleanup_tabs(ctx):
    pages = ctx.pages
    print(f"  Found {len(pages)} open tabs", flush=True)
    kept = False
    for p in pages:
        url = p.url or ""
        if "dzine.ai" in url:
            if kept:
                try:
                    p.close()
                except Exception:
                    pass
            else:
                kept = True
        elif url in ("", "about:blank", "chrome://newtab/"):
            try:
                p.close()
            except Exception:
                pass
    print(f"  Tabs after cleanup: {len(ctx.pages)}", flush=True)


def close_all_panels(page):
    page.evaluate("""() => {
        for (var el of document.querySelectorAll('.c-gen-config.show .ico-close')) el.click();
        for (var el of document.querySelectorAll('.panels.show .ico-close')) el.click();
        var lsp = document.querySelector('.lip-sync-config-panel.show');
        if (lsp) lsp.classList.remove('show');
    }""")
    page.wait_for_timeout(1000)


def open_sidebar_tool(page, target_y):
    close_all_panels(page)
    page.wait_for_timeout(500)
    page.mouse.click(40, 766)
    page.wait_for_timeout(1500)
    close_all_panels(page)
    page.wait_for_timeout(500)
    page.mouse.click(40, target_y)
    page.wait_for_timeout(2500)
    close_dialogs(page)


def main():
    print("Connecting...", flush=True)
    pw = sync_playwright().start()
    browser = pw.chromium.connect_over_cdp("http://127.0.0.1:18800", timeout=15000)
    ctx = browser.contexts[0]
    cleanup_tabs(ctx)

    page = ctx.new_page()
    page.set_viewport_size({"width": 1440, "height": 900})

    page.goto(CANVAS_URL, wait_until="domcontentloaded", timeout=30000)
    print("  Waiting for canvas...", flush=True)
    wait_for_canvas(page)
    close_dialogs(page)

    # Check credits before
    credits_before = page.evaluate("""() => {
        for (var el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text.match(/^[\\d,\\.]+$/) && parseInt(text.replace(/[,\\.]/g, '')) > 100 && r.y < 30 && r.x > 400) {
                return text;
            }
        }
        return null;
    }""")
    print(f"  Credits before: {credits_before}", flush=True)

    # Count existing results
    before_count = page.evaluate("""() => {
        return document.querySelectorAll('img[src*="static.dzine.ai/stylar_product/p/"]').length;
    }""")
    print(f"  Existing result images: {before_count}", flush=True)

    # ============================================================
    #  STEP 1: Open Txt2Img panel
    # ============================================================
    print("\n=== STEP 1: Open Txt2Img ===", flush=True)

    open_sidebar_tool(page, 197)

    # Verify panel is open
    panel_check = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return {error: 'no panel'};
        var textarea = panel.querySelector('textarea');
        var genBtn = panel.querySelector('#txt2img-generate-btn, button.generative');
        return {
            hasTextarea: !!textarea,
            hasGenBtn: !!genBtn,
            genBtnDisabled: genBtn ? genBtn.disabled : null,
            genBtnText: genBtn ? (genBtn.innerText || '').trim() : '',
        };
    }""")
    print(f"  Panel check: {json.dumps(panel_check)}", flush=True)

    # ============================================================
    #  STEP 2: Set Fast mode (2 credits)
    # ============================================================
    print("\n=== STEP 2: Set Fast mode ===", flush=True)

    mode_set = page.evaluate("""() => {
        for (var b of document.querySelectorAll('button')) {
            if ((b.innerText || '').trim() === 'Fast') {
                b.click();
                return 'clicked Fast';
            }
        }
        return 'Fast button not found';
    }""")
    print(f"  {mode_set}", flush=True)
    page.wait_for_timeout(500)

    # ============================================================
    #  STEP 3: Set aspect ratio to 16:9
    # ============================================================
    print("\n=== STEP 3: Set 16:9 aspect ratio ===", flush=True)

    ratio_set = page.evaluate("""() => {
        // Click the Canvas aspect ratio option (matches canvas size)
        for (var b of document.querySelectorAll('.c-aspect-ratio button, .c-aspect-ratio .item')) {
            var text = (b.innerText || '').trim();
            if (text.includes('canvas') || text.includes('Canvas') || (b.className || '').includes('canvas')) {
                b.click();
                return 'clicked canvas ratio';
            }
        }
        // Try 16:9
        for (var b of document.querySelectorAll('button')) {
            if ((b.innerText || '').trim() === '16:9') {
                b.click();
                return 'clicked 16:9';
            }
        }
        return 'ratio not found';
    }""")
    print(f"  {ratio_set}", flush=True)
    page.wait_for_timeout(500)

    # ============================================================
    #  STEP 4: Enter prompt
    # ============================================================
    print("\n=== STEP 4: Enter prompt ===", flush=True)

    prompt_text = "Professional product photography of premium wireless headphones on a clean white marble surface, soft studio lighting from the left, shallow depth of field, subtle shadow, 4K commercial quality"

    prompt_set = page.evaluate("""(prompt) => {
        var ta = document.querySelector('.gen-config-form textarea, .base-prompt textarea');
        if (!ta) return {error: 'no textarea found'};
        ta.focus();
        ta.value = prompt;
        ta.dispatchEvent(new Event('input', {bubbles: true}));
        ta.dispatchEvent(new Event('change', {bubbles: true}));
        return {ok: true, length: ta.value.length};
    }""", prompt_text)
    print(f"  Prompt set: {json.dumps(prompt_set)}", flush=True)
    page.wait_for_timeout(500)

    ss(page, "P120_01_prompt_set")

    # ============================================================
    #  STEP 5: Click Generate
    # ============================================================
    print("\n=== STEP 5: Generate ===", flush=True)

    # Check generate button state
    gen_btn = page.evaluate("""() => {
        var btn = document.querySelector('#txt2img-generate-btn, button.generative.ready');
        if (!btn) return {error: 'no generate button'};
        var r = btn.getBoundingClientRect();
        return {
            disabled: btn.disabled,
            text: (btn.innerText || '').trim(),
            x: Math.round(r.x + r.width/2),
            y: Math.round(r.y + r.height/2),
            cls: (btn.className || '').toString().substring(0, 50),
        };
    }""")
    print(f"  Generate button: {json.dumps(gen_btn)}", flush=True)

    if gen_btn.get('disabled'):
        print("  Generate button is DISABLED — checking why...", flush=True)
        diag = page.evaluate("""() => {
            var ta = document.querySelector('.gen-config-form textarea');
            return {
                promptValue: ta ? ta.value.substring(0, 50) : 'no textarea',
                promptLength: ta ? ta.value.length : 0,
            };
        }""")
        print(f"  Diagnostic: {json.dumps(diag)}", flush=True)
    else:
        # Click generate
        page.mouse.click(gen_btn['x'], gen_btn['y'])
        print("  Clicked Generate!", flush=True)

    page.wait_for_timeout(2000)
    ss(page, "P120_02_generating")

    # ============================================================
    #  STEP 6: Wait for generation to complete (poll for new images)
    # ============================================================
    print("\n=== STEP 6: Waiting for generation... ===", flush=True)

    start_time = time.time()
    max_wait = 120  # 2 minutes max
    new_images = []

    while time.time() - start_time < max_wait:
        elapsed = int(time.time() - start_time)

        # Check for progress indicator
        progress = page.evaluate("""() => {
            // Check for percentage text in results panel
            for (var el of document.querySelectorAll('.result-panel *, .material-v2-result-content *')) {
                var text = (el.innerText || '').trim();
                if (text.match(/^\\d{1,3}%$/)) {
                    return text;
                }
            }
            return null;
        }""")

        # Count new result images
        current_count = page.evaluate("""() => {
            return document.querySelectorAll('img[src*="static.dzine.ai/stylar_product/p/"]').length;
        }""")

        new_count = current_count - before_count
        if progress:
            print(f"  [{elapsed}s] Progress: {progress}, images: {current_count} (+{new_count})", flush=True)
        elif new_count > 0:
            print(f"  [{elapsed}s] Generation done! {new_count} new image(s)", flush=True)
            break
        else:
            if elapsed % 10 == 0:
                print(f"  [{elapsed}s] Waiting... images: {current_count}", flush=True)

        page.wait_for_timeout(3000)

    if new_count <= 0:
        print("  WARNING: No new images after waiting", flush=True)

    ss(page, "P120_03_generated")

    # ============================================================
    #  STEP 7: Get the new image URLs
    # ============================================================
    print("\n=== STEP 7: Get new image URLs ===", flush=True)

    new_urls = page.evaluate("""(beforeCount) => {
        var imgs = document.querySelectorAll('img[src*="static.dzine.ai/stylar_product/p/"]');
        var urls = [];
        for (var i = beforeCount; i < imgs.length; i++) {
            urls.push(imgs[i].src);
        }
        // Also get the most recent images regardless
        var all = [];
        for (var img of imgs) {
            all.push(img.src);
        }
        return {newUrls: urls, totalCount: imgs.length, lastFew: all.slice(-4)};
    }""", before_count)

    print(f"  Total images: {new_urls['totalCount']}", flush=True)
    print(f"  New URLs ({len(new_urls['newUrls'])}):", flush=True)
    for u in new_urls['newUrls']:
        print(f"    {u[:100]}...", flush=True)

    # ============================================================
    #  STEP 8: Download the first new image
    # ============================================================
    print("\n=== STEP 8: Download image ===", flush=True)

    download_url = None
    if new_urls['newUrls']:
        download_url = new_urls['newUrls'][0]
    elif new_urls['lastFew']:
        download_url = new_urls['lastFew'][-1]

    if download_url:
        filename = f"dzine_test_{int(time.time())}.webp"
        download_path = DOWNLOAD_DIR / filename
        print(f"  Downloading: {download_url[:80]}...", flush=True)
        print(f"  To: {download_path}", flush=True)

        try:
            urllib.request.urlretrieve(download_url, str(download_path))
            size = download_path.stat().st_size
            print(f"  Downloaded: {size:,} bytes", flush=True)

            # Validate
            if size < 1024:
                print("  WARNING: File too small (< 1KB)", flush=True)
            elif size < 50 * 1024:
                print("  WARNING: File smaller than expected (< 50KB)", flush=True)
            else:
                print(f"  OK: Image downloaded successfully ({size/1024:.1f} KB)", flush=True)

            # Read header to determine format
            with open(download_path, 'rb') as f:
                header = f.read(12)
            if header[:4] == b'RIFF' and header[8:12] == b'WEBP':
                print("  Format: WebP", flush=True)
            elif header[:8] == b'\x89PNG\r\n\x1a\n':
                print("  Format: PNG", flush=True)
            elif header[:2] == b'\xff\xd8':
                print("  Format: JPEG", flush=True)
            else:
                print(f"  Format: Unknown (header: {header[:8].hex()})", flush=True)

        except Exception as e:
            print(f"  Download failed: {e}", flush=True)
    else:
        print("  No image URL available to download", flush=True)

    # ============================================================
    #  STEP 9: Test "place on canvas" via result action
    # ============================================================
    print("\n=== STEP 9: Place on canvas ===", flush=True)

    # Find the most recent result and click it to open preview
    if new_urls['totalCount'] > 0:
        # Click the last result image
        last_img = page.evaluate("""() => {
            var imgs = document.querySelectorAll('img[src*="static.dzine.ai/stylar_product/p/"]');
            if (imgs.length === 0) return null;
            var last = imgs[imgs.length - 1];
            var r = last.getBoundingClientRect();
            return {x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)};
        }""")

        if last_img and last_img['y'] > 0 and last_img['y'] < 900:
            page.mouse.click(last_img['x'], last_img['y'])
            page.wait_for_timeout(2000)

            # Find and click "place on canvas" button
            place_btn = page.evaluate("""() => {
                var btn = document.querySelector('.handle-item.place-on-canvas');
                if (!btn) return null;
                var r = btn.getBoundingClientRect();
                return {x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)};
            }""")

            if place_btn:
                print(f"  Clicking 'place on canvas' at ({place_btn['x']},{place_btn['y']})", flush=True)
                page.mouse.click(place_btn['x'], place_btn['y'])
                page.wait_for_timeout(2000)

                # Check layer count
                layers = page.evaluate("() => document.querySelectorAll('.layer-item').length")
                print(f"  Layers after placing: {layers}", flush=True)
            else:
                print("  place-on-canvas button not found", flush=True)
                page.keyboard.press("Escape")
        else:
            print("  Last image not visible in viewport", flush=True)

    ss(page, "P120_04_placed")

    # ============================================================
    #  STEP 10: Credits after
    # ============================================================
    print("\n=== STEP 10: Credits check ===", flush=True)

    credits_after = page.evaluate("""() => {
        for (var el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text.match(/^[\\d,\\.]+$/) && parseInt(text.replace(/[,\\.]/g, '')) > 100 && r.y < 30 && r.x > 400) {
                return text;
            }
        }
        return null;
    }""")
    print(f"  Credits before: {credits_before}", flush=True)
    print(f"  Credits after:  {credits_after}", flush=True)

    ss(page, "P120_05_final")
    print(f"\n\n===== PHASE 120 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
