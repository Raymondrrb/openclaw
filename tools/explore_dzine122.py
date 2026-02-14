"""Phase 122: Reference-image workflow for product fidelity.
CRITICAL RULE: Product images MUST be faithful to real Amazon product photos.
AI-generated products without reference are FAKE and unusable.

Goal: 1) Download a real product image from Amazon (e.g., Sony WH-1000XM5)
      2) Place it on Dzine canvas
      3) Use Img2Img with HIGH Structure Match to create a styled scene
      4) Compare fidelity between original and generated
      5) Test different Structure Match levels (low vs high)
      6) Test CC Reference mode with product photo
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

# Real Amazon product image URL (Sony WH-1000XM5 - public CDN)
# We'll try to use an actual product image
PRODUCT_IMAGE_SEARCH = "Sony WH-1000XM5 headphones"


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


def get_latest_image_url(page, count=1):
    return page.evaluate("""(count) => {
        var imgs = document.querySelectorAll('img[src*="static.dzine.ai/stylar_product/p/"]');
        var urls = [];
        for (var i = Math.max(0, imgs.length - count); i < imgs.length; i++) {
            urls.push(imgs[i].src);
        }
        return urls;
    }""", count)


def download_image(url, name):
    path = DOWNLOAD_DIR / name
    try:
        urllib.request.urlretrieve(url, str(path))
        size = path.stat().st_size
        print(f"  Downloaded: {path.name} ({size/1024:.1f} KB)", flush=True)
        return str(path), size
    except Exception as e:
        print(f"  Download failed: {e}", flush=True)
        return None, 0


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

    # ============================================================
    #  STEP 1: Get a real product image via Amazon in another tab
    # ============================================================
    print("\n=== STEP 1: Get real product image from Amazon ===", flush=True)

    # Open Amazon in a new tab to find a product image
    amazon_page = ctx.new_page()
    amazon_page.set_viewport_size({"width": 1440, "height": 900})

    try:
        amazon_page.goto("https://www.amazon.com/dp/B0C8PSRWFX", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(3000)

        # Get the main product image URL
        product_img = amazon_page.evaluate("""() => {
            // Try the main product image
            var img = document.querySelector('#landingImage, #imgBlkFront, #main-image');
            if (img) return img.src;

            // Try data-old-hires attribute
            var hiRes = document.querySelector('#landingImage');
            if (hiRes && hiRes.getAttribute('data-old-hires')) {
                return hiRes.getAttribute('data-old-hires');
            }

            // Try any large image in the main container
            for (var el of document.querySelectorAll('#imgTagWrapperId img, #imageBlock img')) {
                if (el.naturalWidth > 300) return el.src;
            }

            return null;
        }""")

        print(f"  Amazon product image: {(product_img or 'NOT FOUND')[:100]}", flush=True)

        if product_img:
            # Download the product image
            product_path = DOWNLOAD_DIR / "amazon_product_ref.jpg"
            urllib.request.urlretrieve(product_img, str(product_path))
            size = product_path.stat().st_size
            print(f"  Saved: {product_path} ({size/1024:.1f} KB)", flush=True)
        else:
            # Fallback: try to get any product image
            product_img = amazon_page.evaluate("""() => {
                var images = document.querySelectorAll('img');
                for (var img of images) {
                    if (img.naturalWidth > 400 && img.src.includes('amazon.com')) {
                        return img.src;
                    }
                }
                return null;
            }""")
            print(f"  Fallback image: {(product_img or 'NONE')[:100]}", flush=True)

            if product_img:
                product_path = DOWNLOAD_DIR / "amazon_product_ref.jpg"
                urllib.request.urlretrieve(product_img, str(product_path))

    except Exception as e:
        print(f"  Amazon page error: {e}", flush=True)
        product_img = None

    # Close Amazon tab
    try:
        amazon_page.close()
    except Exception:
        pass

    # ============================================================
    #  STEP 2: Place product image on Dzine canvas via clipboard
    # ============================================================
    print("\n=== STEP 2: Place product on canvas ===", flush=True)

    if product_img:
        # Load the product image into canvas via JS
        # First, clear the canvas to only have the product
        # Actually, let's just add the image as a new layer using the image URL

        placed = page.evaluate("""(imgUrl) => {
            // Use fabric.js to add image to canvas
            try {
                // Find the fabric canvas instance
                if (window.canvas || window.editor) {
                    var fabricCanvas = window.canvas || window.editor.canvas;
                    if (fabricCanvas && fabricCanvas.add) {
                        // Try fabric.Image.fromURL
                        fabric.Image.fromURL(imgUrl, function(img) {
                            img.scaleToWidth(400);
                            fabricCanvas.add(img);
                            fabricCanvas.renderAll();
                        }, {crossOrigin: 'anonymous'});
                        return 'attempted via fabric';
                    }
                }
                return 'no fabric canvas found';
            } catch(e) {
                return 'error: ' + e.message;
            }
        }""", product_img)
        print(f"  Canvas placement: {placed}", flush=True)
        page.wait_for_timeout(3000)

        # Alternative: try drag-and-drop the image
        if 'error' in str(placed) or 'no fabric' in str(placed):
            print("  Trying DataTransfer drop...", flush=True)
            drop_result = page.evaluate("""(imgUrl) => {
                return new Promise(async (resolve) => {
                    try {
                        var response = await fetch(imgUrl);
                        var blob = await response.blob();
                        var file = new File([blob], 'product.jpg', {type: blob.type});
                        var dt = new DataTransfer();
                        dt.items.add(file);

                        var canvas = document.querySelector('.canvas-container');
                        if (!canvas) { resolve('no canvas-container'); return; }

                        var r = canvas.getBoundingClientRect();
                        var opts = {
                            bubbles: true, cancelable: true, dataTransfer: dt,
                            clientX: Math.round(r.x + r.width/2),
                            clientY: Math.round(r.y + r.height/2),
                        };
                        canvas.dispatchEvent(new DragEvent('dragenter', opts));
                        canvas.dispatchEvent(new DragEvent('dragover', opts));
                        canvas.dispatchEvent(new DragEvent('drop', opts));
                        resolve('dropped');
                    } catch(e) {
                        resolve('error: ' + e.message);
                    }
                });
            }""", product_img)
            print(f"  Drop result: {drop_result}", flush=True)
            page.wait_for_timeout(3000)

        # Check layers after placement
        layers = page.evaluate("() => document.querySelectorAll('.layer-item').length")
        print(f"  Layers on canvas: {layers}", flush=True)

    ss(page, "P122_01_product_on_canvas")

    # ============================================================
    #  STEP 3: Img2Img with HIGH structure match
    # ============================================================
    print("\n=== STEP 3: Img2Img HIGH structure match ===", flush=True)

    open_sidebar_tool(page, 252)

    # Click "Describe Canvas" first
    page.evaluate("""() => {
        var btn = document.querySelector('button.autoprompt');
        if (btn) btn.click();
    }""")
    page.wait_for_timeout(5000)

    # Customize prompt for product scene
    scene_prompt = "Premium wireless headphones on a clean white marble surface with soft studio lighting. Product photography, high detail, subtle shadow, commercial quality. Preserve exact product shape and design."

    page.evaluate("""(prompt) => {
        var ta = document.querySelector('.img2img-config-panel textarea, TEXTAREA.len-1800');
        if (ta) {
            ta.value = prompt;
            ta.dispatchEvent(new Event('input', {bubbles: true}));
        }
    }""", scene_prompt)
    page.wait_for_timeout(500)

    # Set Structure Match to HIGH (slider is at x=100, y=421)
    # The slider goes from 0 to 100. We want it at ~85
    struct_result = page.evaluate("""() => {
        // Find sliders in the Img2Img panel
        var panel = document.querySelector('.img2img-config-panel, .c-gen-config.show');
        if (!panel) return {error: 'no panel'};

        var sliders = panel.querySelectorAll('.c-slider, .ant-slider');
        var info = [];
        for (var s of sliders) {
            var label = '';
            var prev = s.previousElementSibling;
            if (prev) label = (prev.innerText || '').trim().substring(0, 30);
            var r = s.getBoundingClientRect();
            info.push({
                label: label,
                cls: (s.className || '').toString().substring(0, 40),
                x: Math.round(r.x), y: Math.round(r.y),
                w: Math.round(r.width), h: Math.round(r.height),
            });
        }
        return {sliders: info};
    }""")
    print(f"  Sliders: {json.dumps(struct_result)}", flush=True)

    # Set Structure Match high by clicking right side of the slider
    for slider in struct_result.get('sliders', []):
        if 'Structure' in slider.get('label', '') or 'structure' in slider.get('label', '').lower():
            # Click at 85% of slider width from left
            x = slider['x'] + int(slider['w'] * 0.85)
            y = slider['y'] + slider['h'] // 2
            print(f"  Setting Structure Match high: clicking ({x},{y})", flush=True)
            page.mouse.click(x, y)
            page.wait_for_timeout(500)
        elif 'Style' in slider.get('label', '') or 'Intensity' in slider.get('label', '').lower():
            # Set style intensity to moderate (~50%)
            x = slider['x'] + int(slider['w'] * 0.5)
            y = slider['y'] + slider['h'] // 2
            print(f"  Setting Style Intensity moderate: clicking ({x},{y})", flush=True)
            page.mouse.click(x, y)
            page.wait_for_timeout(500)

    # Enable Color Match for product fidelity
    page.evaluate("""() => {
        var switches = document.querySelectorAll('.c-switch');
        for (var s of switches) {
            var label = '';
            var prev = s.previousElementSibling || s.parentElement;
            if (prev) label = (prev.innerText || '').trim();
            if (label.includes('Color Match') || label.includes('color')) {
                if (!s.classList.contains('checked')) {
                    s.click();
                }
            }
        }
    }""")
    page.wait_for_timeout(500)

    ss(page, "P122_02_img2img_high_struct")

    # Generate
    before_count = page.evaluate("() => document.querySelectorAll('img[src*=\"static.dzine.ai/stylar_product/p/\"]').length")

    gen = page.evaluate("""() => {
        var btn = document.querySelector('button.generative.ready');
        if (!btn || btn.disabled) return {error: 'button not ready'};
        btn.click();
        return {clicked: true};
    }""")
    print(f"  Generate: {json.dumps(gen)}", flush=True)

    page.wait_for_timeout(2000)
    new_count = wait_for_new_images(page, before_count, max_wait=90, label="HighStruct")

    if new_count > 0:
        urls = get_latest_image_url(page, new_count)
        for i, url in enumerate(urls):
            download_image(url, f"dzine_high_struct_{int(time.time())}_{i}.webp")

    ss(page, "P122_03_high_struct_result")

    # ============================================================
    #  STEP 4: Map the CC Reference mode for product photos
    # ============================================================
    print("\n=== STEP 4: CC Reference mode exploration ===", flush=True)

    open_sidebar_tool(page, 306)

    # Select Ray
    page.evaluate("""() => {
        var list = document.querySelector('.c-character-list');
        if (list) {
            for (var item of list.querySelectorAll('.item, button')) {
                if ((item.innerText || '').trim() === 'Ray') {
                    item.click(); return;
                }
            }
        }
    }""")
    page.wait_for_timeout(2000)

    # Look for Reference mode / Control Mode options
    cc_controls = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return {error: 'no CC panel'};

        var text = (panel.innerText || '').substring(0, 1200);

        // Find all control-related elements
        var controls = [];
        for (var el of panel.querySelectorAll('button, [class*="control"], [class*="mode"], [class*="reference"]')) {
            var r = el.getBoundingClientRect();
            if (r.width < 20) continue;
            var t = (el.innerText || '').trim();
            if (t.length > 0 && t.length < 40) {
                controls.push({
                    tag: el.tagName,
                    cls: (el.className || '').toString().substring(0, 50),
                    text: t,
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width),
                });
            }
        }

        // Find upload buttons
        var uploads = [];
        for (var el of panel.querySelectorAll('[class*="upload"], [class*="pick-image"]')) {
            var r = el.getBoundingClientRect();
            if (r.width < 20) continue;
            uploads.push({
                cls: (el.className || '').toString().substring(0, 50),
                text: (el.innerText || '').trim().substring(0, 30),
                x: Math.round(r.x), y: Math.round(r.y),
                w: Math.round(r.width),
            });
        }

        return {fullText: text, controls: controls.slice(0, 20), uploads: uploads};
    }""")

    print(f"  CC panel text:\n{cc_controls.get('fullText', '')[:600]}", flush=True)
    print(f"\n  Controls ({len(cc_controls.get('controls', []))}):", flush=True)
    for c in cc_controls.get('controls', []):
        print(f"    <{c['tag']}> .{c['cls'][:40]} '{c['text'][:30]}' ({c['x']},{c['y']}) w={c['w']}", flush=True)
    print(f"\n  Upload buttons ({len(cc_controls.get('uploads', []))}):", flush=True)
    for u in cc_controls.get('uploads', []):
        print(f"    .{u['cls'][:40]} '{u['text'][:25]}' ({u['x']},{u['y']})", flush=True)

    ss(page, "P122_04_cc_reference")

    # Look for Control Mode buttons (Camera, Pose, Reference)
    control_mode = page.evaluate("""() => {
        var modes = [];
        for (var b of document.querySelectorAll('button')) {
            var text = (b.innerText || '').trim();
            if (['Camera', 'Pose', 'Reference'].includes(text)) {
                var r = b.getBoundingClientRect();
                modes.push({
                    text: text,
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width),
                    active: (b.className || '').includes('active') || (b.className || '').includes('selected'),
                });
            }
        }
        return modes;
    }""")
    print(f"\n  Control modes: {json.dumps(control_mode)}", flush=True)

    # Click Reference mode if found
    for m in control_mode:
        if m['text'] == 'Reference':
            print(f"  Clicking Reference mode at ({m['x']},{m['y']})", flush=True)
            page.mouse.click(m['x'] + m['w']//2, m['y'] + 15)
            page.wait_for_timeout(2000)

            # Check what changed - new upload area?
            ref_panel = page.evaluate("""() => {
                var panel = document.querySelector('.c-gen-config.show');
                if (!panel) return '';
                return (panel.innerText || '').substring(0, 800);
            }""")
            print(f"  After Reference mode:\n{ref_panel[:400]}", flush=True)
            break

    ss(page, "P122_05_cc_reference_mode")

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

    ss(page, "P122_06_final")
    print(f"\n\n===== PHASE 122 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
