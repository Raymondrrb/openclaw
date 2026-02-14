"""Phase 126: Fix canvas placement + product-faithful Img2Img.
P125: Canvas showed OLD content (blue foam), not the product. Drop didn't work visually.
Clipboard paste DID work in P117 (layers 16→18). Need proper approach.

Goal: 1) Create a NEW clean canvas project
      2) Place Amazon product image via clipboard paste (proven to work)
      3) Verify product is visible on canvas
      4) Run Img2Img with Realistic Product style
      5) Verify the result matches the actual product
"""

import base64
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from playwright.sync_api import sync_playwright

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


def wait_for_new_images(page, before_count, max_wait=120, label=""):
    start = time.time()
    while time.time() - start < max_wait:
        elapsed = int(time.time() - start)
        current = page.evaluate("() => document.querySelectorAll('img[src*=\"static.dzine.ai/stylar_product/p/\"]').length")
        new_count = current - before_count
        if new_count > 0:
            print(f"  [{label}] Done in {elapsed}s! {new_count} new image(s)", flush=True)
            return new_count
        if elapsed % 10 == 0:
            progress = page.evaluate("""() => {
                for (var el of document.querySelectorAll('.result-panel *, .material-v2-result-content *')) {
                    var text = (el.innerText || '').trim();
                    if (text.match(/^\\d{1,3}%$/)) return text;
                }
                return null;
            }""")
            p = f" progress={progress}" if progress else ""
            print(f"  [{label}] {elapsed}s...{p}", flush=True)
        page.wait_for_timeout(3000)
    print(f"  [{label}] TIMEOUT after {max_wait}s", flush=True)
    return 0


def main():
    print("Connecting...", flush=True)
    pw = sync_playwright().start()
    browser = pw.chromium.connect_over_cdp("http://127.0.0.1:18800", timeout=15000)
    ctx = browser.contexts[0]

    # Clean up ALL dzine tabs to start fresh
    for p in ctx.pages:
        url = p.url or ""
        if "dzine.ai" in url:
            try:
                p.close()
            except Exception:
                pass

    page = ctx.new_page()
    page.set_viewport_size({"width": 1440, "height": 900})

    # ============================================================
    #  STEP 1: Create a new project on Dzine
    # ============================================================
    print("\n=== STEP 1: Create new Dzine project ===", flush=True)

    page.goto("https://www.dzine.ai/editor", wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(5000)
    close_dialogs(page)

    # Look for "New Project" or "Create" button
    new_proj = page.evaluate("""() => {
        for (var el of document.querySelectorAll('button, a, [class*="create"], [class*="new"]')) {
            var text = (el.innerText || '').trim();
            if (text.includes('New') || text.includes('Create') || text.includes('Start')) {
                var r = el.getBoundingClientRect();
                if (r.width > 50) {
                    return {text: text.substring(0, 30), x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)};
                }
            }
        }
        // Try direct URL
        return {redirect: true};
    }""")
    print(f"  New project: {json.dumps(new_proj)}", flush=True)

    if new_proj.get('redirect'):
        # Navigate directly to create a new canvas
        page.goto("https://www.dzine.ai/canvas", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(5000)
        close_dialogs(page)

    # Check current URL - should be on a canvas
    current_url = page.url
    print(f"  Current URL: {current_url}", flush=True)

    # Wait for canvas to load
    canvas_ok = wait_for_canvas(page)
    if not canvas_ok:
        # If not on canvas, try the existing project
        print("  Falling back to existing project...", flush=True)
        page.goto("https://www.dzine.ai/canvas?id=19797967", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(3000)
        wait_for_canvas(page)

    close_dialogs(page)
    ss(page, "P126_00_canvas")

    # ============================================================
    #  STEP 2: Clear all layers from canvas
    # ============================================================
    print("\n=== STEP 2: Clear canvas layers ===", flush=True)

    # Select all and delete
    page.keyboard.press("Meta+a")
    page.wait_for_timeout(500)
    page.keyboard.press("Delete")
    page.wait_for_timeout(1000)

    # Check layer count
    layers = page.evaluate("() => document.querySelectorAll('.layer-item').length")
    print(f"  Layers after clear: {layers}", flush=True)

    if layers > 0:
        # Try again - select all via keyboard
        page.mouse.click(700, 450)  # Click canvas
        page.wait_for_timeout(300)
        page.keyboard.press("Meta+a")
        page.wait_for_timeout(500)
        page.keyboard.press("Backspace")
        page.wait_for_timeout(1000)

        layers = page.evaluate("() => document.querySelectorAll('.layer-item').length")
        print(f"  Layers after second clear: {layers}", flush=True)

    ss(page, "P126_01_cleared")

    # ============================================================
    #  STEP 3: Download best Amazon product image
    # ============================================================
    print("\n=== STEP 3: Get Amazon product image ===", flush=True)

    # Use existing downloaded image or get fresh
    best_ref = None
    for name in ["amazon_SL1500_61Ji-RGXab.jpg", "amazon_product_ref.jpg"]:
        p = DOWNLOAD_DIR / name
        if p.exists() and p.stat().st_size > 10000:
            best_ref = str(p)
            break

    if not best_ref:
        # Download fresh
        try:
            url = "https://m.media-amazon.com/images/I/61Ji-RGXabL._AC_SL1500_.jpg"
            best_ref = str(DOWNLOAD_DIR / "amazon_product_fresh.jpg")
            urllib.request.urlretrieve(url, best_ref)
        except Exception as e:
            print(f"  Download failed: {e}", flush=True)

    if best_ref:
        size = os.path.getsize(best_ref)
        print(f"  Reference: {best_ref} ({size/1024:.1f} KB)", flush=True)

    # ============================================================
    #  STEP 4: Place product on canvas via clipboard paste
    # ============================================================
    print("\n=== STEP 4: Place product via clipboard paste ===", flush=True)

    if best_ref:
        with open(best_ref, 'rb') as f:
            img_bytes = f.read()
        img_b64 = base64.b64encode(img_bytes).decode('ascii')

        # Write image to clipboard via JS
        paste_ready = page.evaluate("""(b64) => {
            return new Promise(async (resolve) => {
                try {
                    var byteChars = atob(b64);
                    var arr = new Uint8Array(byteChars.length);
                    for (var i = 0; i < byteChars.length; i++) {
                        arr[i] = byteChars.charCodeAt(i);
                    }
                    var blob = new Blob([arr], {type: 'image/jpeg'});
                    var item = new ClipboardItem({'image/jpeg': blob});
                    await navigator.clipboard.write([item]);
                    resolve({ok: true, size: arr.length});
                } catch(e) {
                    resolve({error: e.message});
                }
            });
        }""", img_b64)
        print(f"  Clipboard: {json.dumps(paste_ready)}", flush=True)

        if paste_ready.get('ok'):
            # Focus canvas and paste
            page.mouse.click(700, 450)
            page.wait_for_timeout(500)
            page.keyboard.press("Meta+v")
            page.wait_for_timeout(3000)

            # Check if layer was added
            layers = page.evaluate("() => document.querySelectorAll('.layer-item').length")
            print(f"  Layers after paste: {layers}", flush=True)

            if layers > 0:
                # Check canvas content - take screenshot to verify product is visible
                ss(page, "P126_02_product_pasted")

                # Fit the image to canvas size
                page.keyboard.press("Meta+a")
                page.wait_for_timeout(300)

                # Check the canvas dimensions vs image
                canvas_info = page.evaluate("""() => {
                    var canvas = document.querySelector('#canvas, .lower-canvas, canvas');
                    if (!canvas) return {error: 'no canvas'};
                    return {w: canvas.width, h: canvas.height};
                }""")
                print(f"  Canvas size: {json.dumps(canvas_info)}", flush=True)
            else:
                print("  No layers added after paste!", flush=True)
                # Try the Upload button approach instead
                print("  Trying Upload sidebar...", flush=True)
                page.mouse.click(40, 81)  # Upload button (y=81)
                page.wait_for_timeout(2000)

                # Check if file chooser can be triggered
                try:
                    with page.expect_file_chooser(timeout=5000) as fc_info:
                        page.mouse.click(40, 81)
                    fc = fc_info.value
                    fc.set_files(best_ref)
                    print("  Upload via sidebar worked!", flush=True)
                    page.wait_for_timeout(3000)
                except Exception as e:
                    print(f"  Upload sidebar failed: {e}", flush=True)

    ss(page, "P126_03_product_on_canvas")

    # ============================================================
    #  STEP 5: Img2Img with Realistic Product + max structure match
    # ============================================================
    print("\n=== STEP 5: Img2Img generation ===", flush=True)

    open_sidebar_tool(page, 252)

    # Select "Realistic Product" style
    page.evaluate("""() => {
        var panel = document.querySelector('.img2img-config-panel, .c-gen-config.show');
        if (!panel) return;
        var styleName = panel.querySelector('.style-name');
        if (styleName) styleName.click();
    }""")
    page.wait_for_timeout(2000)

    # Search and select
    page.evaluate("""() => {
        var input = document.querySelector('.style-list-panel input[type="text"]');
        if (input) {
            input.value = 'Realistic Product';
            input.dispatchEvent(new Event('input', {bubbles: true}));
        }
    }""")
    page.wait_for_timeout(1500)

    page.evaluate("""() => {
        var items = document.querySelectorAll('[class*="style-item"]');
        for (var item of items) {
            if ((item.innerText || '').trim() === 'Realistic Product') {
                item.click();
                return;
            }
        }
    }""")
    page.wait_for_timeout(1000)

    # Use Describe Canvas
    page.evaluate("""() => {
        var btn = document.querySelector('button.autoprompt');
        if (btn) btn.click();
    }""")
    page.wait_for_timeout(5000)

    # Read what autoprompt generated
    auto = page.evaluate("""() => {
        var ta = document.querySelector('.img2img-config-panel textarea, TEXTAREA.len-1800');
        return ta ? ta.value.substring(0, 200) : 'no textarea';
    }""")
    print(f"  Autoprompt: {auto}", flush=True)

    # Set the prompt to emphasize product fidelity
    page.evaluate("""() => {
        var ta = document.querySelector('.img2img-config-panel textarea, TEXTAREA.len-1800');
        if (ta) {
            ta.value = 'Premium wireless headphones, exact product photo, clean white studio background, soft diffused lighting from above and left, subtle shadow underneath. Keep EXACT product shape, color, branding, and design details. 4K commercial product photography.';
            ta.dispatchEvent(new Event('input', {bubbles: true}));
        }
    }""")
    page.wait_for_timeout(500)

    # Set Structure Match to MAXIMUM
    page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return;
        var sliders = panel.querySelectorAll('.ant-slider');
        for (var i = 0; i < sliders.length; i++) {
            var r = sliders[i].getBoundingClientRect();
            // Get the label to identify which slider
            var allText = panel.innerText || '';

            if (i === 1) {
                // Second slider is typically Structure Match
                // Click at 95% from left for maximum
                var event = new MouseEvent('click', {
                    clientX: r.x + r.width * 0.95,
                    clientY: r.y + r.height / 2,
                    bubbles: true
                });
                sliders[i].dispatchEvent(event);
            } else if (i === 0) {
                // First slider is Style Intensity - set LOW for product fidelity
                var event = new MouseEvent('click', {
                    clientX: r.x + r.width * 0.2,
                    clientY: r.y + r.height / 2,
                    bubbles: true
                });
                sliders[i].dispatchEvent(event);
            }
        }
    }""")
    page.wait_for_timeout(500)

    # Enable both Color Match and Face Match
    page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return;
        var switches = panel.querySelectorAll('.c-switch');
        for (var s of switches) {
            if (!s.classList.contains('isChecked')) {
                s.click();
            }
        }
    }""")
    page.wait_for_timeout(500)

    # Set HQ mode for best quality
    page.evaluate("""() => {
        for (var b of document.querySelectorAll('button.options')) {
            if ((b.innerText || '').trim() === 'HQ') { b.click(); return; }
        }
    }""")
    page.wait_for_timeout(500)

    ss(page, "P126_04_img2img_setup")

    # Read final settings
    settings = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return {};
        return {
            styleName: (document.querySelector('.style-name') || {}).innerText || '',
            fullText: (panel.innerText || '').substring(0, 400),
        };
    }""")
    print(f"  Style: {settings.get('styleName', 'unknown')}", flush=True)
    print(f"  Settings: {settings.get('fullText', '')[:200]}", flush=True)

    # Generate
    before_count = page.evaluate("() => document.querySelectorAll('img[src*=\"static.dzine.ai/stylar_product/p/\"]').length")

    gen = page.evaluate("""() => {
        var btn = document.querySelector('button.generative.ready');
        if (!btn || btn.disabled) return {error: 'not ready', disabled: btn ? btn.disabled : 'no btn'};
        btn.click();
        return {clicked: true, credits: (btn.innerText || '').trim()};
    }""")
    print(f"  Generate: {json.dumps(gen)}", flush=True)

    if gen.get('clicked'):
        page.wait_for_timeout(2000)
        new_count = wait_for_new_images(page, before_count, max_wait=180, label="HQ Product")

        if new_count > 0:
            urls = page.evaluate("""(count) => {
                var imgs = document.querySelectorAll('img[src*="static.dzine.ai/stylar_product/p/"]');
                var urls = [];
                for (var i = Math.max(0, imgs.length - count); i < imgs.length; i++) {
                    urls.push(imgs[i].src);
                }
                return urls;
            }""", new_count)
            for i, url in enumerate(urls):
                path = DOWNLOAD_DIR / f"dzine_product_hq_{int(time.time())}_{i}.webp"
                try:
                    urllib.request.urlretrieve(url, str(path))
                    size = path.stat().st_size
                    print(f"  Downloaded: {path.name} ({size/1024:.1f} KB)", flush=True)
                except Exception as e:
                    print(f"  Download failed: {e}", flush=True)

    ss(page, "P126_05_result")

    # View the result
    page.evaluate("""() => {
        var imgs = document.querySelectorAll('img[src*="static.dzine.ai/stylar_product/p/"]');
        if (imgs.length > 0) imgs[imgs.length - 1].click();
    }""")
    page.wait_for_timeout(2000)
    ss(page, "P126_06_result_preview")

    # Close preview
    page.keyboard.press("Escape")

    # Credits
    credits = page.evaluate("""() => {
        for (var el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text.match(/^[\\d,\\.]+$/) && parseInt(text.replace(/[,\\.]/g, '')) > 100 && r.y < 30 && r.x > 400) {
                return text;
            }
        }
        return null;
    }""")
    print(f"\n  Credits: {credits}", flush=True)

    ss(page, "P126_07_final")
    print(f"\n\n===== PHASE 126 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
