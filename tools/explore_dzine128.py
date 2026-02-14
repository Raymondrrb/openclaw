"""Phase 128: NEW project → clean canvas → Upload product image → Img2Img fidelity test.

P127 problem: Old canvas had 2 stubborn layers (blue foam blocks) that couldn't
be deleted. Pasted product went behind them. Img2Img used the wrong source.

New approach:
  1) Create a brand new Dzine project (clean canvas, zero layers)
  2) Upload Amazon product image via file chooser or clipboard paste
  3) Run Img2Img with Realistic Product + max Structure Match + Color Match
  4) Download result and screenshot for fidelity comparison
  5) If product not on canvas, try Upload sidebar (y=81) file chooser
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
    page.mouse.click(40, 766)  # Storyboard — clear toggle
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


def find_product_image():
    """Find the best Amazon product reference image already downloaded."""
    candidates = [
        "amazon_SL1500_61Ji-RGXab.jpg",
        "amazon_product_ref.jpg",
    ]
    # Also check for any amazon_SL1500_*.jpg in Downloads
    for p in DOWNLOAD_DIR.glob("amazon_SL1500_*.jpg"):
        if p.stat().st_size > 10000:
            return str(p)
    for name in candidates:
        p = DOWNLOAD_DIR / name
        if p.exists() and p.stat().st_size > 10000:
            return str(p)
    # Also check for any amazon_ prefixed images
    for p in DOWNLOAD_DIR.glob("amazon_*.jpg"):
        if p.stat().st_size > 10000:
            return str(p)
    for p in DOWNLOAD_DIR.glob("amazon_*.png"):
        if p.stat().st_size > 10000:
            return str(p)
    return None


def main():
    print("=" * 60, flush=True)
    print("PHASE 128: New project + product upload + Img2Img fidelity", flush=True)
    print("=" * 60, flush=True)

    # First check we have a product image
    ref_path = find_product_image()
    if ref_path:
        print(f"\n  Found product image: {ref_path} ({os.path.getsize(ref_path)/1024:.1f} KB)", flush=True)
    else:
        print("\n  No product image found — will download from Amazon first", flush=True)

    print("\nConnecting to Brave CDP...", flush=True)
    pw = sync_playwright().start()
    browser = pw.chromium.connect_over_cdp("http://127.0.0.1:18800", timeout=15000)
    ctx = browser.contexts[0]

    # ============================================================
    #  STEP 0: If no product image, get one from Amazon
    # ============================================================
    if not ref_path:
        print("\n=== STEP 0: Download product image from Amazon ===", flush=True)
        amz_page = ctx.new_page()
        amz_page.set_viewport_size({"width": 1440, "height": 900})

        # Sony WH-1000XM5 — classic reference product
        amz_url = "https://www.amazon.com/dp/B09XS7JWHH"
        print(f"  Loading: {amz_url}", flush=True)
        try:
            amz_page.goto(amz_url, wait_until="domcontentloaded", timeout=30000)
            amz_page.wait_for_timeout(3000)
            close_dialogs(amz_page)

            # Get hi-res product images
            img_urls = amz_page.evaluate("""() => {
                var urls = new Set();
                // From data-a-dynamic-image
                for (var img of document.querySelectorAll('#altImages img, #imageBlock img, #main-image-container img')) {
                    var dyn = img.getAttribute('data-a-dynamic-image');
                    if (dyn) {
                        try {
                            var obj = JSON.parse(dyn);
                            for (var u of Object.keys(obj)) {
                                if (u.includes('SL1500') || u.includes('SL1200')) urls.add(u);
                            }
                        } catch(e) {}
                    }
                    if (img.src && (img.src.includes('SL1500') || img.src.includes('SL1200'))) {
                        urls.add(img.src);
                    }
                }
                // From colorImages script
                for (var s of document.querySelectorAll('script')) {
                    var t = s.textContent || '';
                    var m = t.match(/'colorImages'\\s*:\\s*\\{\\s*'initial'\\s*:\\s*(\\[.+?\\])/s);
                    if (m) {
                        try {
                            var arr = JSON.parse(m[1]);
                            for (var item of arr) {
                                if (item.hiRes) urls.add(item.hiRes);
                                else if (item.large) urls.add(item.large);
                            }
                        } catch(e) {}
                    }
                }
                // Also try data-old-hires
                for (var img of document.querySelectorAll('#landingImage, #imgTagWrapperId img')) {
                    var hi = img.getAttribute('data-old-hires');
                    if (hi) urls.add(hi);
                }
                return [...urls];
            }""")
            print(f"  Found {len(img_urls)} hi-res URLs", flush=True)

            # Download the best one
            if img_urls:
                for i, url in enumerate(img_urls[:3]):
                    fname = f"amazon_product_{int(time.time())}_{i}.jpg"
                    fpath = DOWNLOAD_DIR / fname
                    try:
                        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                        with urllib.request.urlopen(req, timeout=15) as resp:
                            data = resp.read()
                        with open(fpath, 'wb') as f:
                            f.write(data)
                        print(f"  Downloaded: {fname} ({len(data)/1024:.1f} KB)", flush=True)
                        if len(data) > 10000 and not ref_path:
                            ref_path = str(fpath)
                    except Exception as e:
                        print(f"  Download failed: {e}", flush=True)

            if not ref_path:
                # Last resort: screenshot the product image area
                print("  Falling back to screenshot capture...", flush=True)
                landing = amz_page.locator("#landingImage")
                if landing.count() > 0:
                    box = landing.first.bounding_box()
                    if box:
                        ref_path = str(DOWNLOAD_DIR / "amazon_product_screenshot.png")
                        landing.first.screenshot(path=ref_path)
                        print(f"  Screenshot saved: {ref_path}", flush=True)

            ss(amz_page, "P128_00_amazon")
        except Exception as e:
            print(f"  Amazon load failed: {e}", flush=True)
        finally:
            amz_page.close()

    if not ref_path:
        print("\n  FATAL: Could not obtain any product image. Stopping.", flush=True)
        sys.stdout.flush()
        os._exit(1)

    print(f"\n  Using product image: {ref_path} ({os.path.getsize(ref_path)/1024:.1f} KB)", flush=True)

    # ============================================================
    #  STEP 1: Create a NEW Dzine project (clean canvas)
    # ============================================================
    print("\n=== STEP 1: Create new Dzine project ===", flush=True)

    # Close all dzine tabs first
    for p in ctx.pages:
        if "dzine.ai" in (p.url or ""):
            try:
                p.close()
            except Exception:
                pass
    page = ctx.new_page()
    page.set_viewport_size({"width": 1440, "height": 900})

    # Go to Dzine home to create new project
    page.goto("https://www.dzine.ai/ai-editor", wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(5000)
    close_dialogs(page)

    # Check if we landed on canvas or home page
    current_url = page.url
    print(f"  Current URL: {current_url}", flush=True)

    if "/canvas" in current_url:
        # Already on a canvas — check if it's clean
        loaded = wait_for_canvas(page)
        layers = page.evaluate("() => document.querySelectorAll('.layer-item').length") if loaded else -1
        print(f"  Direct canvas — layers: {layers}", flush=True)
    else:
        # On the editor/home page — look for "New Project" or "Create" button
        ss(page, "P128_01_editor_home")

        # Try to find a "create new" or "blank canvas" option
        new_proj = page.evaluate("""() => {
            var results = [];
            for (var el of document.querySelectorAll('button, a, [role="button"], [class*="create"], [class*="new"]')) {
                var text = (el.innerText || '').trim().substring(0, 50);
                var r = el.getBoundingClientRect();
                if (text && r.width > 0 && r.height > 0) {
                    results.push({text: text, x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2), tag: el.tagName, cls: (el.className || '').toString().substring(0, 80)});
                }
            }
            return results;
        }""")
        for item in new_proj[:20]:
            print(f"    {item['tag']}.{item['cls'][:30]} @ ({item['x']},{item['y']}): {item['text'][:40]}", flush=True)

        # Look for "Blank Canvas" or "New Design" or "+" or "Create"
        page.evaluate("""() => {
            for (var el of document.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                if (text === 'Blank Canvas' || text === 'New Design' || text === 'Create New' || text === 'New Project') {
                    el.click();
                    return text;
                }
            }
            // Try the + or create button
            var create = document.querySelector('[class*="create-btn"], .new-project, [class*="add-project"]');
            if (create) { create.click(); return 'clicked create'; }
            return null;
        }""")
        page.wait_for_timeout(5000)
        close_dialogs(page)

        # If still not on canvas, try direct URL approach — create via API-like URL
        if "/canvas" not in page.url:
            print("  Not on canvas yet, trying direct create...", flush=True)
            ss(page, "P128_01b_not_canvas")

            # Navigate to canvas creation endpoint
            page.goto("https://www.dzine.ai/canvas", wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(5000)
            close_dialogs(page)

        print(f"  URL after create: {page.url}", flush=True)

        if "/canvas" in page.url:
            wait_for_canvas(page)
        else:
            print("  ERROR: Could not reach canvas!", flush=True)
            ss(page, "P128_01c_error")
            # Fall back to the known canvas
            page.goto("https://www.dzine.ai/canvas?id=19797967", wait_until="domcontentloaded", timeout=30000)
            wait_for_canvas(page)

    close_dialogs(page)
    layers = page.evaluate("() => document.querySelectorAll('.layer-item').length")
    print(f"  Canvas ready — layers: {layers}", flush=True)
    canvas_url = page.url
    print(f"  Canvas URL: {canvas_url}", flush=True)

    ss(page, "P128_02_clean_canvas")

    # ============================================================
    #  STEP 2: If old layers exist, try to delete them ALL
    # ============================================================
    if layers > 0:
        print(f"\n=== STEP 2: Delete {layers} old layers ===", flush=True)

        # Open Layers tab
        page.evaluate("""() => {
            for (var el of document.querySelectorAll('[class*="header-item"]')) {
                if ((el.innerText || '').trim() === 'Layers') { el.click(); return; }
            }
        }""")
        page.wait_for_timeout(1000)

        # Try selecting all and deleting multiple times
        for attempt in range(8):
            page.mouse.click(700, 450)
            page.wait_for_timeout(200)
            page.keyboard.press("Meta+a")
            page.wait_for_timeout(200)
            page.keyboard.press("Delete")
            page.wait_for_timeout(500)

            layers = page.evaluate("() => document.querySelectorAll('.layer-item').length")
            if layers == 0:
                print(f"  All layers deleted (attempt {attempt+1})", flush=True)
                break

        if layers > 0:
            # Try right-click context menu on each layer
            print(f"  Still {layers} layers — trying right-click delete...", flush=True)
            for _ in range(layers + 2):
                layer_pos = page.evaluate("""() => {
                    var items = document.querySelectorAll('.layer-item');
                    if (items.length === 0) return null;
                    var r = items[0].getBoundingClientRect();
                    return {x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)};
                }""")
                if not layer_pos:
                    break

                # Right click
                page.mouse.click(layer_pos['x'], layer_pos['y'], button="right")
                page.wait_for_timeout(500)

                # Look for "Delete" in context menu
                page.evaluate("""() => {
                    for (var el of document.querySelectorAll('.ant-dropdown-menu-item, [class*="menu-item"], [class*="context"] *')) {
                        if ((el.innerText || '').trim() === 'Delete') {
                            el.click();
                            return true;
                        }
                    }
                    return false;
                }""")
                page.wait_for_timeout(500)

            layers = page.evaluate("() => document.querySelectorAll('.layer-item').length")
            print(f"  Layers after context-menu delete: {layers}", flush=True)

    ss(page, "P128_03_layers_cleared")

    # ============================================================
    #  STEP 3: Upload product image onto canvas
    # ============================================================
    print(f"\n=== STEP 3: Upload product image ===", flush=True)

    uploaded = False

    # Method A: Sidebar Upload button (y=81) with file_chooser
    print("  Method A: Sidebar Upload button...", flush=True)
    try:
        with page.expect_file_chooser(timeout=5000) as fc_info:
            page.mouse.click(40, 81)
        fc = fc_info.value
        fc.set_files(ref_path)
        print(f"  File chooser accepted: {ref_path}", flush=True)
        page.wait_for_timeout(5000)

        layers = page.evaluate("() => document.querySelectorAll('.layer-item').length")
        print(f"  Layers after upload: {layers}", flush=True)
        if layers > 0:
            uploaded = True
    except Exception as e:
        print(f"  Method A failed: {e}", flush=True)

    # Method B: Clipboard paste (PNG conversion)
    if not uploaded:
        print("  Method B: Clipboard paste (JPEG→PNG)...", flush=True)

        with open(ref_path, 'rb') as f:
            img_b64 = base64.b64encode(f.read()).decode('ascii')

        # Determine format from extension
        is_png = ref_path.lower().endswith('.png')
        mime = 'image/png' if is_png else 'image/jpeg'

        if is_png:
            # Direct PNG paste
            paste_ok = page.evaluate("""(pngB64) => {
                return new Promise(async (resolve) => {
                    try {
                        var resp = await fetch('data:image/png;base64,' + pngB64);
                        var blob = await resp.blob();
                        var item = new ClipboardItem({'image/png': blob});
                        await navigator.clipboard.write([item]);
                        resolve({ok: true, size: blob.size});
                    } catch(e) {
                        resolve({error: e.message});
                    }
                });
            }""", img_b64)
        else:
            # JPEG → PNG conversion
            paste_ok = page.evaluate("""(jpegB64) => {
                return new Promise(async (resolve) => {
                    try {
                        var img = new Image();
                        img.onload = async function() {
                            var c = document.createElement('canvas');
                            c.width = img.width;
                            c.height = img.height;
                            var ctx = c.getContext('2d');
                            ctx.drawImage(img, 0, 0);
                            c.toBlob(async function(pngBlob) {
                                if (!pngBlob) { resolve({error: 'toBlob null'}); return; }
                                try {
                                    var item = new ClipboardItem({'image/png': pngBlob});
                                    await navigator.clipboard.write([item]);
                                    resolve({ok: true, w: img.width, h: img.height, pngSize: pngBlob.size});
                                } catch(e) { resolve({error: 'write: ' + e.message}); }
                            }, 'image/png');
                        };
                        img.onerror = function() { resolve({error: 'img load fail'}); };
                        img.src = 'data:image/jpeg;base64,' + jpegB64;
                    } catch(e) { resolve({error: e.message}); }
                });
            }""", img_b64)

        print(f"  Clipboard result: {json.dumps(paste_ok)}", flush=True)

        if paste_ok.get('ok'):
            page.mouse.click(700, 450)
            page.wait_for_timeout(500)
            page.keyboard.press("Meta+v")
            page.wait_for_timeout(4000)

            layers = page.evaluate("() => document.querySelectorAll('.layer-item').length")
            print(f"  Layers after paste: {layers}", flush=True)
            if layers > 0:
                uploaded = True

    # Method C: Upload zone click + file chooser
    if not uploaded:
        print("  Method C: Upload zone click...", flush=True)
        upload_zone = page.evaluate("""() => {
            for (var el of document.querySelectorAll('*')) {
                if ((el.innerText || '').includes('CLICK, DRAG or PASTE')) {
                    var r = el.getBoundingClientRect();
                    return {x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)};
                }
            }
            return null;
        }""")
        if upload_zone:
            try:
                with page.expect_file_chooser(timeout=5000) as fc_info:
                    page.mouse.click(upload_zone['x'], upload_zone['y'])
                fc = fc_info.value
                fc.set_files(ref_path)
                print(f"  Upload zone accepted file!", flush=True)
                page.wait_for_timeout(5000)
                layers = page.evaluate("() => document.querySelectorAll('.layer-item').length")
                if layers > 0:
                    uploaded = True
            except Exception as e:
                print(f"  Method C failed: {e}", flush=True)

    # Method D: Drag and drop via DataTransfer
    if not uploaded:
        print("  Method D: DataTransfer drop...", flush=True)
        with open(ref_path, 'rb') as f:
            img_b64 = base64.b64encode(f.read()).decode('ascii')
        fname = os.path.basename(ref_path)
        mime = 'image/png' if ref_path.lower().endswith('.png') else 'image/jpeg'

        drop_ok = page.evaluate("""({b64, filename, mime}) => {
            return new Promise(async (resolve) => {
                try {
                    var resp = await fetch('data:' + mime + ';base64,' + b64);
                    var blob = await resp.blob();
                    var file = new File([blob], filename, {type: mime});
                    var dt = new DataTransfer();
                    dt.items.add(file);

                    var target = document.querySelector('.canvas-container') || document.querySelector('[class*="canvas"]') || document.body;
                    var r = target.getBoundingClientRect();
                    var cx = r.x + r.width/2;
                    var cy = r.y + r.height/2;

                    ['dragenter', 'dragover', 'drop'].forEach(function(type) {
                        target.dispatchEvent(new DragEvent(type, {
                            dataTransfer: dt,
                            bubbles: true,
                            clientX: cx,
                            clientY: cy
                        }));
                    });
                    resolve({ok: true, target: target.className.toString().substring(0, 60)});
                } catch(e) { resolve({error: e.message}); }
            });
        }""", {"b64": img_b64, "filename": fname, "mime": mime})
        print(f"  Drop result: {json.dumps(drop_ok)}", flush=True)
        page.wait_for_timeout(5000)
        layers = page.evaluate("() => document.querySelectorAll('.layer-item').length")
        if layers > 0:
            uploaded = True

    if not uploaded:
        print("\n  WARNING: All upload methods failed! Layers=0", flush=True)
        print("  Will try creating canvas from Upload panel instead...", flush=True)

    ss(page, "P128_04_product_uploaded")

    # ============================================================
    #  STEP 4: Verify product is the ONLY visible layer
    # ============================================================
    print(f"\n=== STEP 4: Verify canvas state ===", flush=True)

    layers = page.evaluate("() => document.querySelectorAll('.layer-item').length")
    print(f"  Total layers: {layers}", flush=True)

    # Get layer info
    layer_info = page.evaluate("""() => {
        var items = [];
        for (var el of document.querySelectorAll('.layer-item')) {
            var name = '';
            var nameEl = el.querySelector('[class*="layer-name"], [class*="name"]');
            if (nameEl) name = (nameEl.innerText || '').trim();
            var visible = !el.querySelector('[class*="hidden"], .ico-eye-close');
            var r = el.getBoundingClientRect();
            items.push({name: name, visible: visible, y: Math.round(r.y)});
        }
        return items;
    }""")
    print(f"  Layers: {json.dumps(layer_info)}", flush=True)

    # Make sure ALL layers are visible (no hidden ones)
    page.evaluate("""() => {
        for (var el of document.querySelectorAll('.layer-item .ico-eye-close')) {
            el.click();
        }
    }""")
    page.wait_for_timeout(500)

    # Use "Describe Canvas" to check what Dzine sees
    open_sidebar_tool(page, 252)  # Img2Img

    # Clear any existing prompt first
    page.evaluate("""() => {
        var ta = document.querySelector('.img2img-config-panel textarea, TEXTAREA.len-1800');
        if (ta) { ta.value = ''; ta.dispatchEvent(new Event('input', {bubbles: true})); }
    }""")
    page.wait_for_timeout(500)

    # Click autoprompt (Describe Canvas)
    page.evaluate("""() => {
        var btn = document.querySelector('button.autoprompt');
        if (btn) { btn.click(); return true; }
        return false;
    }""")
    page.wait_for_timeout(6000)

    autoprompt = page.evaluate("""() => {
        var ta = document.querySelector('.img2img-config-panel textarea, TEXTAREA.len-1800');
        return ta ? {value: ta.value.substring(0, 500), length: ta.value.length} : {error: 'no textarea'};
    }""")
    print(f"  Autoprompt: {json.dumps(autoprompt)}", flush=True)

    ss(page, "P128_05_canvas_verified")

    # ============================================================
    #  STEP 5: Img2Img with max product fidelity settings
    # ============================================================
    print(f"\n=== STEP 5: Img2Img generation ===", flush=True)

    if layers == 0:
        print("  SKIP — no product on canvas to transform", flush=True)
        print(f"\n===== PHASE 128 COMPLETE (partial — upload failed) =====", flush=True)
        sys.stdout.flush()
        os._exit(0)

    # Set product-preservation prompt
    page.evaluate("""() => {
        var ta = document.querySelector('.img2img-config-panel textarea, TEXTAREA.len-1800');
        if (ta) {
            ta.value = 'Product photography on clean white studio backdrop. Preserve the exact product design, shape, buttons, logo, and all physical details with 100% accuracy. Professional lighting, no modifications to the product whatsoever.';
            ta.dispatchEvent(new Event('input', {bubbles: true}));
        }
    }""")
    page.wait_for_timeout(500)

    # Open style picker and select "Realistic Product"
    page.evaluate("""() => {
        var styleName = document.querySelector('.style-name');
        if (styleName) styleName.click();
    }""")
    page.wait_for_timeout(2000)

    # Search for Realistic Product
    page.evaluate("""() => {
        var input = document.querySelector('.style-list-panel input[type="text"]');
        if (input) {
            input.value = 'Realistic Product';
            input.dispatchEvent(new Event('input', {bubbles: true}));
        }
    }""")
    page.wait_for_timeout(1500)

    style_clicked = page.evaluate("""() => {
        for (var item of document.querySelectorAll('[class*="style-item"]')) {
            if ((item.innerText || '').trim() === 'Realistic Product') {
                item.click();
                return true;
            }
        }
        return false;
    }""")
    print(f"  Realistic Product style: {'selected' if style_clicked else 'NOT FOUND'}", flush=True)
    page.wait_for_timeout(1000)

    # Configure sliders: LOW Style Intensity, MAX Structure Match, Color Match ON
    slider_info = page.evaluate("""() => {
        var sliders = document.querySelectorAll('.c-gen-config.show .ant-slider');
        var info = [];
        for (var i = 0; i < sliders.length; i++) {
            var r = sliders[i].getBoundingClientRect();
            var handle = sliders[i].querySelector('.ant-slider-handle');
            var hPos = handle ? handle.style.left || handle.style.bottom : 'unknown';
            info.push({index: i, x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), label: hPos});
        }
        return info;
    }""")
    print(f"  Sliders found: {len(slider_info)}", flush=True)
    for s in slider_info:
        print(f"    Slider {s['index']}: ({s['x']},{s['y']}) w={s['w']} handle={s['label']}", flush=True)

    if len(slider_info) >= 2:
        # Style Intensity (index 0) → set to ~10% (very low)
        s0 = slider_info[0]
        page.mouse.click(s0['x'] + int(s0['w'] * 0.10), s0['y'] + 5)
        page.wait_for_timeout(300)

        # Structure Match (index 1) → set to ~98% (max fidelity)
        s1 = slider_info[1]
        page.mouse.click(s1['x'] + int(s1['w'] * 0.98), s1['y'] + 5)
        page.wait_for_timeout(300)
        print("  Sliders set: Style 10%, Structure 98%", flush=True)
    elif len(slider_info) == 1:
        # Single slider — probably Structure Match
        s0 = slider_info[0]
        page.mouse.click(s0['x'] + int(s0['w'] * 0.98), s0['y'] + 5)
        page.wait_for_timeout(300)
        print("  Single slider set to 98%", flush=True)

    # Enable Color Match switch
    page.evaluate("""() => {
        var switches = document.querySelectorAll('.c-gen-config.show .c-switch');
        for (var s of switches) {
            if (!s.classList.contains('isChecked')) { s.click(); return 'enabled'; }
            return 'already_on';
        }
        return 'none_found';
    }""")
    page.wait_for_timeout(300)

    # Select Normal mode (balance speed vs quality)
    page.evaluate("""() => {
        for (var b of document.querySelectorAll('button.options')) {
            if ((b.innerText || '').trim() === 'Normal') { b.click(); return; }
        }
    }""")
    page.wait_for_timeout(300)

    ss(page, "P128_06_img2img_ready")

    # Generate!
    before_count = page.evaluate("() => document.querySelectorAll('img[src*=\"static.dzine.ai/stylar_product/p/\"]').length")
    print(f"  Images before: {before_count}", flush=True)

    gen = page.evaluate("""() => {
        var btn = document.querySelector('button.generative.ready');
        if (!btn || btn.disabled) {
            var allBtns = document.querySelectorAll('button.generative');
            var info = [];
            for (var b of allBtns) info.push({text: (b.innerText||'').trim(), disabled: b.disabled, cls: b.className.substring(0,80)});
            return {error: 'not ready', buttons: info};
        }
        btn.click();
        return {clicked: true, text: (btn.innerText || '').trim()};
    }""")
    print(f"  Generate: {json.dumps(gen)}", flush=True)

    if gen.get('clicked'):
        page.wait_for_timeout(2000)
        new_count = wait_for_new_images(page, before_count, max_wait=90, label="FidelityTest")

        if new_count > 0:
            # Download results
            urls = page.evaluate("""(count) => {
                var imgs = document.querySelectorAll('img[src*="static.dzine.ai/stylar_product/p/"]');
                var urls = [];
                for (var i = Math.max(0, imgs.length - count); i < imgs.length; i++) {
                    urls.push(imgs[i].src);
                }
                return urls;
            }""", new_count)

            ts = int(time.time())
            for i, url in enumerate(urls):
                path = DOWNLOAD_DIR / f"dzine_fidelity_{ts}_{i}.webp"
                try:
                    urllib.request.urlretrieve(url, str(path))
                    size = path.stat().st_size
                    print(f"  Downloaded: {path.name} ({size/1024:.1f} KB)", flush=True)
                except Exception as e:
                    print(f"  Download failed: {e}", flush=True)

            # Preview result
            page.evaluate("""() => {
                var imgs = document.querySelectorAll('img[src*="static.dzine.ai/stylar_product/p/"]');
                if (imgs.length > 0) imgs[imgs.length - 1].click();
            }""")
            page.wait_for_timeout(2000)
            ss(page, "P128_07_result_preview")

            page.keyboard.press("Escape")
            page.wait_for_timeout(500)

            # Also place on canvas for comparison
            page.evaluate("""() => {
                var btn = document.querySelector('#result-preview button[class*="place"], [class*="place-on-canvas"]');
                if (btn) btn.click();
            }""")
            page.wait_for_timeout(2000)

    # ============================================================
    #  STEP 6: Summary
    # ============================================================
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
    print(f"\n  Credits remaining: {credits}", flush=True)

    final_layers = page.evaluate("() => document.querySelectorAll('.layer-item').length")
    print(f"  Final layers: {final_layers}", flush=True)
    print(f"  Canvas URL: {page.url}", flush=True)

    ss(page, "P128_08_final")

    print(f"\n\n===== PHASE 128 COMPLETE =====", flush=True)
    print(f"  Ref image: {ref_path}", flush=True)
    print(f"  Key question: Does the Img2Img result faithfully preserve the product?", flush=True)
    print(f"  Review screenshots P128_07 and P128_08 to verify.", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
