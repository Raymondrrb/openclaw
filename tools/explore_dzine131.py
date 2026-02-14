"""Phase 131: Product-faithful workflow — BG Remove + Expand + Enhance.

P130 PROVED: Img2Img does NOT preserve products. Even with 98% Structure Match,
it generates completely different objects. WRONG TOOL for product fidelity.

CORRECT WORKFLOW for product-faithful visuals:
  1) Upload real Amazon product photo to canvas
  2) BG Remove — isolate product from Amazon's white background
  3) Expand — add professional studio backdrop around isolated product
  4) Enhance & Upscale — sharpen details for video resolution
  5) These tools preserve actual PIXELS, not regenerate from scratch

Also: test "Start from an image" on Dzine home to create new project with image.
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
        for text in ["Not now", "Close", "Never show again", "Got it", "Skip",
                      "Later", "Cancel"]:
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
    print("=" * 60, flush=True)
    print("PHASE 131: Product-faithful workflow (BG Remove + Expand)", flush=True)
    print("=" * 60, flush=True)

    pw = sync_playwright().start()
    browser = pw.chromium.connect_over_cdp("http://127.0.0.1:18800", timeout=15000)
    ctx = browser.contexts[0]

    # ============================================================
    #  STEP 0: Get a product image from Amazon
    # ============================================================
    print("\n=== STEP 0: Download product from Amazon ===", flush=True)

    # Check for existing headphones image first
    ref_path = None
    for p in sorted(DOWNLOAD_DIR.glob("amazon_headphones_*.jpg"), reverse=True):
        if p.stat().st_size > 20000:
            ref_path = str(p)
            break

    if not ref_path:
        # Download from Amazon
        amz_page = ctx.new_page()
        amz_page.set_viewport_size({"width": 1440, "height": 900})
        try:
            amz_page.goto("https://www.amazon.com/dp/B09XS7JWHH",
                          wait_until="domcontentloaded", timeout=30000)
            amz_page.wait_for_timeout(4000)
            close_dialogs(amz_page)

            img_url = amz_page.evaluate("""() => {
                var landing = document.querySelector('#landingImage');
                if (landing) {
                    var hi = landing.getAttribute('data-old-hires');
                    if (hi) return hi;
                    var dyn = landing.getAttribute('data-a-dynamic-image');
                    if (dyn) {
                        try {
                            var keys = Object.keys(JSON.parse(dyn));
                            for (var k of keys) { if (k.includes('SL1500')) return k; }
                            return keys[keys.length - 1];
                        } catch(e) {}
                    }
                    return landing.src;
                }
                return null;
            }""")

            if img_url:
                fname = f"amazon_headphones_{int(time.time())}.jpg"
                fpath = DOWNLOAD_DIR / fname
                req = urllib.request.Request(img_url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=15) as resp:
                    data = resp.read()
                with open(fpath, 'wb') as f:
                    f.write(data)
                ref_path = str(fpath)
                print(f"  Downloaded: {fname} ({len(data)/1024:.1f} KB)", flush=True)
        except Exception as e:
            print(f"  Amazon error: {e}", flush=True)
        finally:
            amz_page.close()

    if not ref_path:
        # Fallback: use whatever amazon image exists
        for p in sorted(DOWNLOAD_DIR.glob("amazon_*.jpg"), reverse=True):
            if p.stat().st_size > 10000:
                ref_path = str(p)
                break

    if not ref_path:
        print("  ERROR: No product image available!", flush=True)
        sys.exit(1)

    print(f"  Using: {ref_path} ({os.path.getsize(ref_path)/1024:.1f} KB)", flush=True)

    # ============================================================
    #  STEP 1: Create new project via "Start from an image"
    # ============================================================
    print("\n=== STEP 1: Create project via 'Start from an image' ===", flush=True)

    # Close all dzine tabs
    for p in ctx.pages:
        if "dzine.ai" in (p.url or ""):
            try:
                p.close()
            except Exception:
                pass

    page = ctx.new_page()
    page.set_viewport_size({"width": 1440, "height": 900})

    page.goto("https://www.dzine.ai/home", wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(4000)
    close_dialogs(page)

    ss(page, "P131_01_home")

    # Found in P129: "Start from an image | Pick or drag an image here" at (435,469)
    # And "New project | Create a blank canvas" at (741,469)

    # Try "Start from an image" — this should open a file chooser
    start_from_image = page.evaluate("""() => {
        for (var el of document.querySelectorAll('.project-item, .create-text, button')) {
            var text = (el.innerText || '').trim().toLowerCase();
            if (text.includes('start from an image') || text.includes('pick or drag')) {
                var r = el.getBoundingClientRect();
                return {x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2), text: text.substring(0, 50)};
            }
        }
        return null;
    }""")
    print(f"  'Start from image' button: {json.dumps(start_from_image)}", flush=True)

    canvas_created = False
    if start_from_image:
        try:
            with page.expect_file_chooser(timeout=8000) as fc_info:
                page.mouse.click(start_from_image['x'], start_from_image['y'])
            fc = fc_info.value
            fc.set_files(ref_path)
            print("  File accepted! Waiting for canvas...", flush=True)
            page.wait_for_timeout(8000)
            close_dialogs(page)

            if "/canvas" in page.url:
                print(f"  Canvas created: {page.url}", flush=True)
                wait_for_canvas(page)
                close_dialogs(page)
                canvas_created = True
            else:
                print(f"  Not on canvas: {page.url}", flush=True)
        except Exception as e:
            print(f"  File chooser failed: {e}", flush=True)

    # Fallback: create blank canvas + upload
    if not canvas_created:
        print("  Fallback: create blank + upload...", flush=True)

        # Click "New project - Create a blank canvas"
        page.evaluate("""() => {
            for (var el of document.querySelectorAll('.project-item')) {
                var text = (el.innerText || '').trim().toLowerCase();
                if (text.includes('new project') || text.includes('blank canvas')) {
                    el.click();
                    return text;
                }
            }
        }""")
        page.wait_for_timeout(6000)
        close_dialogs(page)

        if "/canvas" in page.url:
            wait_for_canvas(page)
            close_dialogs(page)

            # Close the project setup dialog
            for btn_text in ["Apply", "Cancel"]:
                page.evaluate(f"""() => {{
                    for (var b of document.querySelectorAll('button')) {{
                        if ((b.innerText || '').trim() === '{btn_text}') {{ b.click(); return; }}
                    }}
                }}""")
                page.wait_for_timeout(500)

            # Upload via sidebar
            try:
                with page.expect_file_chooser(timeout=5000) as fc_info:
                    page.mouse.click(40, 81)
                fc = fc_info.value
                fc.set_files(ref_path)
                page.wait_for_timeout(5000)
                canvas_created = True
                print("  Uploaded via sidebar!", flush=True)
            except Exception as e:
                print(f"  Sidebar upload failed: {e}", flush=True)

                # Clipboard paste fallback
                with open(ref_path, 'rb') as f:
                    img_b64 = base64.b64encode(f.read()).decode('ascii')
                paste_ok = page.evaluate("""(b64) => {
                    return new Promise(async (resolve) => {
                        try {
                            var img = new Image();
                            img.onload = async function() {
                                var c = document.createElement('canvas');
                                c.width = img.width; c.height = img.height;
                                c.getContext('2d').drawImage(img, 0, 0);
                                c.toBlob(async function(blob) {
                                    await navigator.clipboard.write([new ClipboardItem({'image/png': blob})]);
                                    resolve({ok: true});
                                }, 'image/png');
                            };
                            img.src = 'data:image/jpeg;base64,' + b64;
                        } catch(e) { resolve({error: e.message}); }
                    });
                }""", img_b64)
                if paste_ok.get('ok'):
                    page.mouse.click(700, 450)
                    page.wait_for_timeout(500)
                    page.keyboard.press("Meta+v")
                    page.wait_for_timeout(4000)
                    layers = page.evaluate("() => document.querySelectorAll('.layer-item').length")
                    if layers > 0:
                        canvas_created = True
                        print("  Pasted via clipboard!", flush=True)

    if not canvas_created:
        print("  FATAL: Could not create canvas with product!", flush=True)
        sys.exit(1)

    layers = page.evaluate("() => document.querySelectorAll('.layer-item').length")
    print(f"  Canvas ready — layers: {layers}, URL: {page.url}", flush=True)
    ss(page, "P131_02_product_on_canvas")

    # ============================================================
    #  STEP 2: Select the product layer
    # ============================================================
    print("\n=== STEP 2: Select product on canvas ===", flush=True)

    # Click on the canvas center to select the product
    page.mouse.click(700, 400)
    page.wait_for_timeout(1000)

    # Check if something is selected
    selection = page.evaluate("""() => {
        var sel = document.querySelector('.selection-box, [class*="selected"], .transform-handles');
        if (sel) {
            var r = sel.getBoundingClientRect();
            return {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)};
        }
        return null;
    }""")
    print(f"  Selection: {json.dumps(selection)}", flush=True)

    # ============================================================
    #  STEP 3: BG Remove — isolate product from background
    # ============================================================
    print("\n=== STEP 3: BG Remove ===", flush=True)

    # BG Remove is in the action bar at the top
    bg_remove = page.evaluate("""() => {
        for (var el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            if (text === 'BG Remove') {
                var r = el.getBoundingClientRect();
                return {x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2), w: Math.round(r.width)};
            }
        }
        return null;
    }""")
    print(f"  BG Remove button: {json.dumps(bg_remove)}", flush=True)

    if bg_remove:
        page.mouse.click(bg_remove['x'], bg_remove['y'])
        print("  Clicked BG Remove...", flush=True)
        page.wait_for_timeout(2000)

        # Check for any confirmation dialog
        close_dialogs(page)

        # Wait for BG remove to process (look for progress or completion)
        start = time.time()
        bg_done = False
        while time.time() - start < 60:
            elapsed = int(time.time() - start)

            # Check for progress indicators
            progress = page.evaluate("""() => {
                // Check for loading spinners or progress bars
                var spinner = document.querySelector('.loading, [class*="spinner"], [class*="progress"]');
                if (spinner) {
                    var r = spinner.getBoundingClientRect();
                    if (r.width > 0) return 'loading';
                }
                // Check if the background has been removed (transparent bg markers)
                var checkerboard = document.querySelector('[class*="checker"], [class*="transparent"]');
                if (checkerboard) return 'done_checker';
                // Check for result dialog
                for (var el of document.querySelectorAll('*')) {
                    var text = (el.innerText || '').trim();
                    if (text.includes('Background removed') || text.includes('BG removed')) return 'done_text';
                }
                return null;
            }""")

            if progress and progress.startswith('done'):
                print(f"  BG Remove complete! ({progress}) in {elapsed}s", flush=True)
                bg_done = True
                break
            if elapsed % 10 == 0:
                print(f"  BG Remove: {elapsed}s... status={progress}", flush=True)
            page.wait_for_timeout(2000)

        if not bg_done:
            # Maybe it completed silently — check the canvas
            print("  BG Remove: no completion signal — checking canvas...", flush=True)

        ss(page, "P131_03_bg_removed")
        page.wait_for_timeout(2000)
    else:
        # BG Remove might also be available as a toolbar button
        # Check the action bar buttons
        action_bar = page.evaluate("""() => {
            var bar = document.querySelector('.action-bar, .toolbar, [class*="top-bar"]');
            if (!bar) return [];
            var items = [];
            for (var el of bar.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                var r = el.getBoundingClientRect();
                if (text && r.width > 0 && r.width < 200) {
                    items.push({text: text.substring(0, 30), x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)});
                }
            }
            return items;
        }""")
        print(f"  Action bar items:", flush=True)
        seen = set()
        for item in action_bar:
            if item['text'] not in seen:
                print(f"    ({item['x']},{item['y']}): {item['text']}", flush=True)
                seen.add(item['text'])
        print("  BG Remove not found in expected location", flush=True)

    # ============================================================
    #  STEP 4: Enhance & Upscale
    # ============================================================
    print("\n=== STEP 4: Enhance & Upscale ===", flush=True)

    open_sidebar_tool(page, 628)  # Enhance & Upscale y=628
    page.wait_for_timeout(1500)

    # Map the Enhance panel
    enhance_panel = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show, .panels.show');
        if (!panel) return {error: 'no panel'};

        var elements = [];
        for (var el of panel.querySelectorAll('button, [role="button"], select, input, .c-switch, [class*="option"]')) {
            var text = (el.innerText || el.value || '').trim().substring(0, 40);
            var r = el.getBoundingClientRect();
            if (r.width > 0) {
                elements.push({
                    text: text,
                    cls: (el.className || '').toString().substring(0, 60),
                    x: Math.round(r.x + r.width/2),
                    y: Math.round(r.y + r.height/2),
                    tag: el.tagName
                });
            }
        }
        return {elements: elements};
    }""")
    print(f"  Enhance panel:", flush=True)
    if 'elements' in enhance_panel:
        for el in enhance_panel['elements'][:20]:
            print(f"    {el['tag']}.{el['cls'][:30]} ({el['x']},{el['y']}): '{el['text']}'", flush=True)

    ss(page, "P131_04_enhance_panel")

    # Select "Precision" mode (preserves details better than Creative)
    page.evaluate("""() => {
        for (var el of document.querySelectorAll('button, [role="button"]')) {
            var text = (el.innerText || '').trim();
            if (text === 'Precision' || text === 'Image') { el.click(); return text; }
        }
    }""")
    page.wait_for_timeout(500)

    # Select 2x scale (good balance of quality vs speed)
    page.evaluate("""() => {
        for (var el of document.querySelectorAll('button, [role="button"], [class*="option"]')) {
            var text = (el.innerText || '').trim();
            if (text === '2x' || text === '2X') { el.click(); return text; }
        }
    }""")
    page.wait_for_timeout(500)

    # Try to generate enhance
    enhance_gen = page.evaluate("""() => {
        var btn = document.querySelector('button.generative.ready');
        if (btn && !btn.disabled) { btn.click(); return {clicked: true, text: (btn.innerText||'').trim()}; }
        // Also try any "Enhance" or "Upscale" button
        for (var b of document.querySelectorAll('button')) {
            var text = (b.innerText || '').trim();
            if ((text.includes('Enhance') || text.includes('Upscale') || text.includes('Generate')) && !b.disabled) {
                b.click();
                return {clicked: true, text: text};
            }
        }
        return {error: 'no button found'};
    }""")
    print(f"  Enhance generate: {json.dumps(enhance_gen)}", flush=True)

    if enhance_gen.get('clicked'):
        # Wait for result
        start = time.time()
        before_imgs = page.evaluate("() => document.querySelectorAll('img[src*=\"static.dzine.ai\"]').length")
        while time.time() - start < 90:
            elapsed = int(time.time() - start)
            current = page.evaluate("() => document.querySelectorAll('img[src*=\"static.dzine.ai\"]').length")
            if current > before_imgs:
                print(f"  Enhance done in {elapsed}s! ({current - before_imgs} new)", flush=True)
                break
            if elapsed % 10 == 0:
                print(f"  Enhance: {elapsed}s...", flush=True)
            page.wait_for_timeout(3000)

        ss(page, "P131_05_enhanced")

    # ============================================================
    #  STEP 5: Generative Expand — add studio backdrop
    # ============================================================
    print("\n=== STEP 5: Generative Expand (Image Editor > Expand) ===", flush=True)

    # Image Editor is at y=698
    open_sidebar_tool(page, 698)
    page.wait_for_timeout(1500)

    # Map the Image Editor sub-tools
    ie_tools = page.evaluate("""() => {
        var panel = document.querySelector('.image-editor-panel, .c-gen-config.show, .panels.show');
        if (!panel) return [];
        var tools = [];
        for (var el of panel.querySelectorAll('button, [role="button"], [class*="tool-item"]')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text && r.width > 0) {
                tools.push({text: text.substring(0, 30), x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)});
            }
        }
        return tools;
    }""")
    print(f"  Image Editor tools:", flush=True)
    for t in ie_tools[:12]:
        print(f"    ({t['x']},{t['y']}): {t['text']}", flush=True)

    # Click "Expand" sub-tool
    expand_clicked = False
    for t in ie_tools:
        if t['text'] == 'Expand':
            page.mouse.click(t['x'], t['y'])
            expand_clicked = True
            print(f"  Clicked Expand", flush=True)
            break

    if not expand_clicked:
        page.evaluate("""() => {
            for (var el of document.querySelectorAll('*')) {
                if ((el.innerText || '').trim() === 'Expand') { el.click(); return; }
            }
        }""")

    page.wait_for_timeout(2000)
    close_dialogs(page)

    # Map the Expand panel
    expand_panel = page.evaluate("""() => {
        var results = {aspects: [], buttons: [], textareas: []};
        // Aspect ratio options
        for (var el of document.querySelectorAll('[class*="aspect"], [class*="ratio"]')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text && r.width > 0) {
                results.aspects.push({text: text.substring(0, 20), x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)});
            }
        }
        // All visible buttons
        for (var b of document.querySelectorAll('button')) {
            var text = (b.innerText || '').trim();
            var r = b.getBoundingClientRect();
            if (text && r.width > 0 && r.y > 100) {
                results.buttons.push({text: text.substring(0, 30), x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2), cls: (b.className||'').substring(0,40)});
            }
        }
        // Textarea for prompt
        for (var ta of document.querySelectorAll('textarea')) {
            var r = ta.getBoundingClientRect();
            if (r.width > 0) {
                results.textareas.push({placeholder: (ta.placeholder||'').substring(0,50), x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width)});
            }
        }
        return results;
    }""")
    print(f"  Expand panel:", flush=True)
    print(f"    Aspects: {json.dumps(expand_panel.get('aspects', []))}", flush=True)
    for b in expand_panel.get('buttons', [])[:10]:
        print(f"    Button ({b['x']},{b['y']}): {b['text']}", flush=True)
    for ta in expand_panel.get('textareas', []):
        print(f"    Textarea: ({ta['x']},{ta['y']}) w={ta['w']} '{ta['placeholder']}'", flush=True)

    ss(page, "P131_06_expand_panel")

    # Select 16:9 aspect for video format
    for t in expand_panel.get('aspects', []):
        if '16:9' in t['text'] or '16' in t['text']:
            page.mouse.click(t['x'], t['y'])
            print(f"  Selected aspect: {t['text']}", flush=True)
            break
    page.wait_for_timeout(500)

    # Set prompt for studio backdrop
    page.evaluate("""() => {
        var ta = document.querySelectorAll('textarea');
        for (var t of ta) {
            var r = t.getBoundingClientRect();
            if (r.width > 100) {
                t.value = 'Clean white studio backdrop with soft professional lighting, subtle shadow underneath product';
                t.dispatchEvent(new Event('input', {bubbles: true}));
                return;
            }
        }
    }""")
    page.wait_for_timeout(500)

    # Generate expand
    expand_gen = page.evaluate("""() => {
        var btn = document.querySelector('button.generative.ready');
        if (btn && !btn.disabled) { btn.click(); return {clicked: true, text: (btn.innerText||'').trim()}; }
        for (var b of document.querySelectorAll('button')) {
            var text = (b.innerText || '').trim();
            if (text.includes('Expand') || text.includes('Generate')) {
                if (!b.disabled) { b.click(); return {clicked: true, text: text}; }
            }
        }
        return {error: 'no button'};
    }""")
    print(f"  Expand generate: {json.dumps(expand_gen)}", flush=True)

    if expand_gen.get('clicked'):
        start = time.time()
        before_imgs = page.evaluate("() => document.querySelectorAll('img[src*=\"static.dzine.ai\"]').length")
        while time.time() - start < 120:
            elapsed = int(time.time() - start)
            current = page.evaluate("() => document.querySelectorAll('img[src*=\"static.dzine.ai\"]').length")
            if current > before_imgs:
                print(f"  Expand done in {elapsed}s!", flush=True)

                # Download
                urls = page.evaluate("""(before) => {
                    var imgs = document.querySelectorAll('img[src*="static.dzine.ai"]');
                    var urls = [];
                    for (var i = before; i < imgs.length; i++) urls.push(imgs[i].src);
                    return urls;
                }""", before_imgs)
                ts = int(time.time())
                for i, url in enumerate(urls[:2]):
                    path = DOWNLOAD_DIR / f"dzine_expand_{ts}_{i}.webp"
                    try:
                        urllib.request.urlretrieve(url, str(path))
                        print(f"  Downloaded: {path.name} ({path.stat().st_size/1024:.1f} KB)", flush=True)
                    except Exception as e:
                        print(f"  Download error: {e}", flush=True)
                break

            if elapsed % 10 == 0:
                progress = page.evaluate("""() => {
                    for (var el of document.querySelectorAll('*')) {
                        var text = (el.innerText || '').trim();
                        if (text.match(/^\\d{1,3}%$/)) return text;
                    }
                    return null;
                }""")
                p = f" {progress}" if progress else ""
                print(f"  Expand: {elapsed}s...{p}", flush=True)
            page.wait_for_timeout(3000)

        ss(page, "P131_07_expanded")

    # ============================================================
    #  STEP 6: Also test BG Remove from action bar directly
    # ============================================================
    print("\n=== STEP 6: BG Remove from top action bar ===", flush=True)

    # Click on the product to select it
    page.mouse.click(700, 400)
    page.wait_for_timeout(1000)

    # The action bar items (AI Eraser, Hand Repair, Expression, BG Remove)
    # are at the top of the canvas
    action_buttons = page.evaluate("""() => {
        var btns = [];
        for (var el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (r.y > 50 && r.y < 100 && r.width > 0 && r.width < 150 && text.length > 2 && text.length < 20) {
                btns.push({text: text, x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)});
            }
        }
        return btns;
    }""")
    print(f"  Action bar:", flush=True)
    for b in action_buttons:
        print(f"    ({b['x']},{b['y']}): {b['text']}", flush=True)

    # Click BG Remove
    bg_btn = None
    for b in action_buttons:
        if 'BG Remove' in b['text'] or 'BG' in b['text']:
            bg_btn = b
            break

    if bg_btn:
        page.mouse.click(bg_btn['x'], bg_btn['y'])
        print(f"  Clicked: {bg_btn['text']}", flush=True)
        page.wait_for_timeout(3000)

        # Check for confirm dialog
        page.evaluate("""() => {
            for (var b of document.querySelectorAll('button')) {
                var text = (b.innerText || '').trim().toLowerCase();
                if (text === 'confirm' || text === 'ok' || text === 'remove' || text === 'apply') {
                    b.click();
                    return text;
                }
            }
        }""")
        page.wait_for_timeout(5000)

        # Wait for BG remove processing
        start = time.time()
        while time.time() - start < 30:
            # Check if background became transparent (checkerboard pattern)
            check = page.evaluate("""() => {
                var canvas = document.querySelector('canvas');
                if (!canvas) return 'no_canvas';
                return 'canvas_found';
            }""")
            page.wait_for_timeout(2000)
            if int(time.time() - start) % 10 == 0:
                print(f"  BG Remove: {int(time.time()-start)}s...", flush=True)

        ss(page, "P131_08_bg_removed_final")
    else:
        print("  BG Remove button not in action bar", flush=True)
        # Map what IS in the action bar at y~71
        all_71 = page.evaluate("""() => {
            var items = [];
            for (var el of document.querySelectorAll('*')) {
                var r = el.getBoundingClientRect();
                if (r.y > 55 && r.y < 85 && r.width > 20 && r.width < 200) {
                    var text = (el.innerText || '').trim();
                    if (text && text.length < 30) {
                        items.push({text: text, x: Math.round(r.x), y: Math.round(r.y), cls: (el.className||'').toString().substring(0, 40)});
                    }
                }
            }
            return items;
        }""")
        seen = set()
        for item in all_71:
            if item['text'] not in seen:
                print(f"    ({item['x']},{item['y']}): {item['text']}", flush=True)
                seen.add(item['text'])

    # ============================================================
    #  SUMMARY
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

    print(f"\n{'='*60}", flush=True)
    print(f"PHASE 131 SUMMARY", flush=True)
    print(f"{'='*60}", flush=True)
    print(f"  Credits: {credits}", flush=True)
    print(f"  Product ref: {ref_path}", flush=True)
    print(f"  Canvas: {page.url}", flush=True)
    print(f"  WORKFLOW: Upload → BG Remove → Expand → Enhance", flush=True)
    print(f"  This preserves actual product pixels unlike Img2Img!", flush=True)

    ss(page, "P131_09_final")
    print(f"\n===== PHASE 131 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
