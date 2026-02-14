"""Phase 127: Fix clipboard paste (JPEG→PNG conversion) + product-faithful test.
P126: Clipboard rejected image/jpeg. Need image/png. Generated product was NOT faithful.

Goal: 1) Convert product JPEG to PNG in browser, paste as image/png
      2) Verify product is on canvas
      3) Img2Img with Realistic Product + max structure match
      4) Compare result to original Amazon image for fidelity
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

    # Close all dzine tabs
    for p in ctx.pages:
        if "dzine.ai" in (p.url or ""):
            try:
                p.close()
            except Exception:
                pass

    page = ctx.new_page()
    page.set_viewport_size({"width": 1440, "height": 900})

    page.goto(CANVAS_URL, wait_until="domcontentloaded", timeout=30000)
    print("  Waiting for canvas...", flush=True)
    wait_for_canvas(page)
    close_dialogs(page)

    # ============================================================
    #  STEP 1: Clear ALL canvas layers
    # ============================================================
    print("\n=== STEP 1: Clear canvas ===", flush=True)

    # Click Layers tab to see all layers
    page.evaluate("""() => {
        for (var el of document.querySelectorAll('[class*="header-item"]')) {
            if ((el.innerText || '').trim() === 'Layers') { el.click(); return; }
        }
    }""")
    page.wait_for_timeout(1000)

    # Delete all layers one by one using Cmd+A then Delete
    for _ in range(5):
        page.mouse.click(700, 450)
        page.wait_for_timeout(200)
        page.keyboard.press("Meta+a")
        page.wait_for_timeout(300)
        page.keyboard.press("Delete")
        page.wait_for_timeout(500)

        layers = page.evaluate("() => document.querySelectorAll('.layer-item').length")
        if layers == 0:
            break
        print(f"  Still {layers} layers...", flush=True)

    layers = page.evaluate("() => document.querySelectorAll('.layer-item').length")
    print(f"  Final layers: {layers}", flush=True)

    # Check for the upload zone text
    upload_zone = page.evaluate("""() => {
        for (var el of document.querySelectorAll('*')) {
            if ((el.innerText || '').includes('CLICK, DRAG or PASTE')) {
                return true;
            }
        }
        return false;
    }""")
    print(f"  Upload zone visible: {upload_zone}", flush=True)

    ss(page, "P127_01_cleared")

    # ============================================================
    #  STEP 2: Get Amazon product image and convert to PNG
    # ============================================================
    print("\n=== STEP 2: Load product image as PNG ===", flush=True)

    best_ref = None
    for name in ["amazon_SL1500_61Ji-RGXab.jpg", "amazon_product_ref.jpg"]:
        p = DOWNLOAD_DIR / name
        if p.exists() and p.stat().st_size > 10000:
            best_ref = str(p)
            break

    if best_ref:
        with open(best_ref, 'rb') as f:
            img_b64 = base64.b64encode(f.read()).decode('ascii')
        print(f"  Loaded: {best_ref} ({os.path.getsize(best_ref)/1024:.1f} KB)", flush=True)

        # Convert JPEG to PNG in the browser and put on clipboard
        paste_ok = page.evaluate("""(jpegB64) => {
            return new Promise(async (resolve) => {
                try {
                    // Create an Image from the JPEG data
                    var img = new Image();
                    img.onload = async function() {
                        // Draw to canvas to convert to PNG
                        var c = document.createElement('canvas');
                        c.width = img.width;
                        c.height = img.height;
                        var ctx = c.getContext('2d');
                        ctx.drawImage(img, 0, 0);

                        // Convert to PNG blob
                        c.toBlob(async function(pngBlob) {
                            if (!pngBlob) {
                                resolve({error: 'toBlob returned null'});
                                return;
                            }
                            try {
                                var item = new ClipboardItem({'image/png': pngBlob});
                                await navigator.clipboard.write([item]);
                                resolve({ok: true, width: img.width, height: img.height, pngSize: pngBlob.size});
                            } catch(e) {
                                resolve({error: 'clipboard write: ' + e.message});
                            }
                        }, 'image/png');
                    };
                    img.onerror = function() {
                        resolve({error: 'image load failed'});
                    };
                    img.src = 'data:image/jpeg;base64,' + jpegB64;
                } catch(e) {
                    resolve({error: e.message});
                }
            });
        }""", img_b64)
        print(f"  Clipboard (PNG): {json.dumps(paste_ok)}", flush=True)

        if paste_ok.get('ok'):
            # Click canvas center and paste
            page.mouse.click(700, 450)
            page.wait_for_timeout(500)
            page.keyboard.press("Meta+v")
            page.wait_for_timeout(3000)

            layers = page.evaluate("() => document.querySelectorAll('.layer-item').length")
            print(f"  Layers after paste: {layers}", flush=True)

            ss(page, "P127_02_product_pasted")

            if layers > 0:
                print("  Product image placed on canvas!", flush=True)
            else:
                # Try clicking the upload zone first
                print("  No layers — trying upload zone click then paste...", flush=True)
                # The upload zone text says "CLICK, DRAG or PASTE here"
                # Maybe we need to click the canvas area first to focus it
                page.mouse.click(700, 450)
                page.wait_for_timeout(300)
                # Try Cmd+V again
                page.keyboard.press("Meta+v")
                page.wait_for_timeout(3000)
                layers = page.evaluate("() => document.querySelectorAll('.layer-item').length")
                print(f"  Layers after retry paste: {layers}", flush=True)
        else:
            print(f"  Clipboard failed, trying alternative...", flush=True)

    # ============================================================
    #  STEP 3: Alternative — try Upload button with file_chooser
    # ============================================================
    if page.evaluate("() => document.querySelectorAll('.layer-item').length") == 0:
        print("\n=== STEP 3: Upload button approach ===", flush=True)

        # Try clicking the upload zone text
        upload_click = page.evaluate("""() => {
            for (var el of document.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                if (text.includes('CLICK, DRAG or PASTE here to upload')) {
                    var r = el.getBoundingClientRect();
                    return {x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)};
                }
            }
            return null;
        }""")
        print(f"  Upload zone pos: {json.dumps(upload_click)}", flush=True)

        if upload_click:
            try:
                with page.expect_file_chooser(timeout=5000) as fc_info:
                    page.mouse.click(upload_click['x'], upload_click['y'])
                fc = fc_info.value
                fc.set_files(best_ref)
                print("  File uploaded via upload zone!", flush=True)
                page.wait_for_timeout(5000)
            except Exception as e:
                print(f"  Upload zone file chooser failed: {e}", flush=True)

        layers = page.evaluate("() => document.querySelectorAll('.layer-item').length")
        print(f"  Layers: {layers}", flush=True)

    # ============================================================
    #  STEP 3b: Last resort — sidebar Upload icon
    # ============================================================
    if page.evaluate("() => document.querySelectorAll('.layer-item').length") == 0:
        print("\n=== STEP 3b: Sidebar Upload icon ===", flush=True)

        try:
            with page.expect_file_chooser(timeout=5000) as fc_info:
                page.mouse.click(40, 81)  # Upload sidebar y=81
            fc = fc_info.value
            fc.set_files(best_ref)
            print("  File uploaded via sidebar!", flush=True)
            page.wait_for_timeout(5000)
        except Exception as e:
            print(f"  Sidebar upload failed: {e}", flush=True)

        layers = page.evaluate("() => document.querySelectorAll('.layer-item').length")
        print(f"  Layers: {layers}", flush=True)

    ss(page, "P127_03_after_upload")

    # ============================================================
    #  STEP 4: Verify product is visible on canvas
    # ============================================================
    print("\n=== STEP 4: Verify canvas content ===", flush=True)

    layers = page.evaluate("() => document.querySelectorAll('.layer-item').length")
    print(f"  Current layers: {layers}", flush=True)

    # Check what "Describe Canvas" says
    open_sidebar_tool(page, 252)

    page.evaluate("""() => {
        var btn = document.querySelector('button.autoprompt');
        if (btn) btn.click();
    }""")
    page.wait_for_timeout(5000)

    auto = page.evaluate("""() => {
        var ta = document.querySelector('.img2img-config-panel textarea, TEXTAREA.len-1800');
        return ta ? {value: ta.value.substring(0, 300), length: ta.value.length} : {error: 'no textarea'};
    }""")
    print(f"  Autoprompt description: {json.dumps(auto)}", flush=True)

    ss(page, "P127_04_describe_canvas")

    # ============================================================
    #  STEP 5: Img2Img with max fidelity settings
    # ============================================================
    print("\n=== STEP 5: Img2Img for product fidelity ===", flush=True)

    # Set prompt focused on product preservation
    page.evaluate("""() => {
        var ta = document.querySelector('.img2img-config-panel textarea, TEXTAREA.len-1800');
        if (ta) {
            ta.value = 'Use the uploaded product image as strict visual reference. Preserve exact geometry, shape, buttons, ports, branding and color. Do NOT modify the product in any way. Place on a clean white studio backdrop with soft lighting.';
            ta.dispatchEvent(new Event('input', {bubbles: true}));
        }
    }""")
    page.wait_for_timeout(500)

    # Select "Realistic Product" style via .style-name click
    page.evaluate("""() => {
        var styleName = document.querySelector('.style-name');
        if (styleName) styleName.click();
    }""")
    page.wait_for_timeout(2000)

    page.evaluate("""() => {
        var input = document.querySelector('.style-list-panel input[type="text"]');
        if (input) { input.value = 'Realistic Product'; input.dispatchEvent(new Event('input', {bubbles: true})); }
    }""")
    page.wait_for_timeout(1500)

    page.evaluate("""() => {
        for (var item of document.querySelectorAll('[class*="style-item"]')) {
            if ((item.innerText || '').trim() === 'Realistic Product') { item.click(); return; }
        }
    }""")
    page.wait_for_timeout(1000)

    # Set sliders: low style intensity, max structure match
    page.evaluate("""() => {
        var sliders = document.querySelectorAll('.c-gen-config.show .ant-slider');
        if (sliders.length >= 2) {
            // Style Intensity slider (index 0) — set LOW (20%)
            var r0 = sliders[0].getBoundingClientRect();
            sliders[0].dispatchEvent(new MouseEvent('click', {
                clientX: r0.x + r0.width * 0.15,
                clientY: r0.y + r0.height / 2,
                bubbles: true
            }));
            // Structure Match slider (index 1) — set MAX (95%)
            var r1 = sliders[1].getBoundingClientRect();
            sliders[1].dispatchEvent(new MouseEvent('click', {
                clientX: r1.x + r1.width * 0.95,
                clientY: r1.y + r1.height / 2,
                bubbles: true
            }));
        }
    }""")
    page.wait_for_timeout(500)

    # Enable Color Match
    page.evaluate("""() => {
        var switches = document.querySelectorAll('.c-gen-config.show .c-switch');
        for (var s of switches) {
            if (!s.classList.contains('isChecked')) s.click();
        }
    }""")
    page.wait_for_timeout(500)

    # Normal mode (not HQ — to save time)
    page.evaluate("""() => {
        for (var b of document.querySelectorAll('button.options')) {
            if ((b.innerText || '').trim() === 'Normal') { b.click(); return; }
        }
    }""")
    page.wait_for_timeout(500)

    ss(page, "P127_05_img2img_setup")

    # Generate
    before_count = page.evaluate("() => document.querySelectorAll('img[src*=\"static.dzine.ai/stylar_product/p/\"]').length")

    gen = page.evaluate("""() => {
        var btn = document.querySelector('button.generative.ready');
        if (!btn || btn.disabled) return {error: 'not ready', msg: (btn ? btn.parentElement.innerText : '').trim().substring(0, 50)};
        btn.click();
        return {clicked: true, text: (btn.innerText || '').trim()};
    }""")
    print(f"  Generate: {json.dumps(gen)}", flush=True)

    if gen.get('clicked'):
        page.wait_for_timeout(2000)
        new_count = wait_for_new_images(page, before_count, max_wait=90, label="FaithfulProd")

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
                path = DOWNLOAD_DIR / f"dzine_faithful_{int(time.time())}_{i}.webp"
                try:
                    urllib.request.urlretrieve(url, str(path))
                    size = path.stat().st_size
                    print(f"  Downloaded: {path.name} ({size/1024:.1f} KB)", flush=True)
                except Exception as e:
                    print(f"  Download failed: {e}", flush=True)

            # View the result
            page.evaluate("""() => {
                var imgs = document.querySelectorAll('img[src*="static.dzine.ai/stylar_product/p/"]');
                if (imgs.length > 0) imgs[imgs.length - 1].click();
            }""")
            page.wait_for_timeout(2000)
            ss(page, "P127_06_result_preview")

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

    ss(page, "P127_07_final")
    print(f"\n\n===== PHASE 127 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
