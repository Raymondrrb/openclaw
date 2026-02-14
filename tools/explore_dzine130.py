"""Phase 130: Img2Img fidelity test on clean canvas (19860799).

P129 created new canvas 19860799 with blue foam mats product image.
Canvas is clean — no stuck layers. Img2Img panel was opened but no generation
was run. Now: set Realistic Product style, max Structure Match, generate,
download, and compare to original.

ALSO: Download a REAL product image from Amazon (e.g., headphones) to test
with a more typical affiliate product. The foam mat test is good but we need
to test with electronics too.
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

NEW_CANVAS = "https://www.dzine.ai/canvas?id=19860799"
SS_DIR = Path(__file__).resolve().parent.parent / "artifacts" / "dzine_explore"
SS_DIR.mkdir(parents=True, exist_ok=True)
DOWNLOAD_DIR = Path.home() / "Downloads"


def ss(page, name):
    page.screenshot(path=str(SS_DIR / f"{name}.png"))
    print(f"  SS: {name}", flush=True)


def close_dialogs(page):
    for _ in range(8):
        found = False
        for text in ["Not now", "Close", "Never show again", "Got it", "Skip", "Later",
                      "Cancel", "Apply"]:
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


def upload_image_to_canvas(page, image_path):
    """Try multiple methods to get an image onto the canvas. Returns True on success."""
    layers_before = page.evaluate("() => document.querySelectorAll('.layer-item').length")

    # Method 1: Clipboard paste (JPEG→PNG conversion)
    print(f"  Upload: clipboard paste for {os.path.basename(image_path)}...", flush=True)
    with open(image_path, 'rb') as f:
        img_b64 = base64.b64encode(f.read()).decode('ascii')

    is_png = image_path.lower().endswith('.png')
    if is_png:
        paste_result = page.evaluate("""(b64) => {
            return new Promise(async (resolve) => {
                try {
                    var resp = await fetch('data:image/png;base64,' + b64);
                    var blob = await resp.blob();
                    await navigator.clipboard.write([new ClipboardItem({'image/png': blob})]);
                    resolve({ok: true, size: blob.size});
                } catch(e) { resolve({error: e.message}); }
            });
        }""", img_b64)
    else:
        paste_result = page.evaluate("""(b64) => {
            return new Promise(async (resolve) => {
                try {
                    var img = new Image();
                    img.onload = async function() {
                        var c = document.createElement('canvas');
                        c.width = img.width; c.height = img.height;
                        c.getContext('2d').drawImage(img, 0, 0);
                        c.toBlob(async function(blob) {
                            if (!blob) { resolve({error: 'toBlob null'}); return; }
                            try {
                                await navigator.clipboard.write([new ClipboardItem({'image/png': blob})]);
                                resolve({ok: true, w: img.width, h: img.height, size: blob.size});
                            } catch(e) { resolve({error: e.message}); }
                        }, 'image/png');
                    };
                    img.onerror = () => resolve({error: 'load failed'});
                    img.src = 'data:image/jpeg;base64,' + b64;
                } catch(e) { resolve({error: e.message}); }
            });
        }""", img_b64)

    print(f"    Clipboard: {json.dumps(paste_result)}", flush=True)

    if paste_result.get('ok'):
        page.mouse.click(700, 450)
        page.wait_for_timeout(500)
        page.keyboard.press("Meta+v")
        page.wait_for_timeout(4000)

        layers_after = page.evaluate("() => document.querySelectorAll('.layer-item').length")
        if layers_after > layers_before:
            print(f"    Paste success: layers {layers_before}→{layers_after}", flush=True)
            return True

    # Method 2: Sidebar upload (y=81)
    print(f"  Upload: sidebar file chooser...", flush=True)
    try:
        with page.expect_file_chooser(timeout=5000) as fc_info:
            page.mouse.click(40, 81)
        fc = fc_info.value
        fc.set_files(image_path)
        page.wait_for_timeout(5000)
        layers_after = page.evaluate("() => document.querySelectorAll('.layer-item').length")
        if layers_after > layers_before:
            print(f"    Sidebar upload success: layers {layers_before}→{layers_after}", flush=True)
            return True
    except Exception as e:
        print(f"    Sidebar failed: {e}", flush=True)

    return False


def run_img2img(page, prompt, style="Realistic Product", struct_match=0.98,
                style_intensity=0.10, color_match=True, mode="Normal", label=""):
    """Open Img2Img, configure, generate, download results."""
    open_sidebar_tool(page, 252)  # Img2Img y=252
    page.wait_for_timeout(1000)

    # Set prompt
    page.evaluate("""(prompt) => {
        var ta = document.querySelector('.img2img-config-panel textarea, TEXTAREA.len-1800');
        if (ta) { ta.value = prompt; ta.dispatchEvent(new Event('input', {bubbles: true})); }
    }""", prompt)
    page.wait_for_timeout(500)

    # Select style
    page.evaluate("""() => {
        var styleName = document.querySelector('.style-name');
        if (styleName) styleName.click();
    }""")
    page.wait_for_timeout(2000)
    page.evaluate("""(name) => {
        var input = document.querySelector('.style-list-panel input[type="text"]');
        if (input) { input.value = name; input.dispatchEvent(new Event('input', {bubbles: true})); }
    }""", style)
    page.wait_for_timeout(1500)
    style_ok = page.evaluate("""(name) => {
        for (var item of document.querySelectorAll('[class*="style-item"]')) {
            if ((item.innerText || '').trim() === name) { item.click(); return true; }
        }
        return false;
    }""", style)
    print(f"  Style '{style}': {'OK' if style_ok else 'NOT FOUND'}", flush=True)
    page.wait_for_timeout(1000)

    # Set sliders
    slider_info = page.evaluate("""() => {
        var sliders = document.querySelectorAll('.c-gen-config.show .ant-slider');
        var info = [];
        for (var s of sliders) {
            var r = s.getBoundingClientRect();
            info.push({x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width)});
        }
        return info;
    }""")
    if len(slider_info) >= 2:
        # Slider 0: Style Intensity
        s0 = slider_info[0]
        page.mouse.click(s0['x'] + int(s0['w'] * style_intensity), s0['y'] + 5)
        page.wait_for_timeout(200)
        # Slider 1: Structure Match
        s1 = slider_info[1]
        page.mouse.click(s1['x'] + int(s1['w'] * struct_match), s1['y'] + 5)
        page.wait_for_timeout(200)
        print(f"  Sliders: intensity={style_intensity}, structure={struct_match}", flush=True)
    elif len(slider_info) == 1:
        s0 = slider_info[0]
        page.mouse.click(s0['x'] + int(s0['w'] * struct_match), s0['y'] + 5)
        page.wait_for_timeout(200)
        print(f"  Single slider: {struct_match}", flush=True)

    # Color Match
    if color_match:
        page.evaluate("""() => {
            var switches = document.querySelectorAll('.c-gen-config.show .c-switch');
            for (var s of switches) {
                if (!s.classList.contains('isChecked')) { s.click(); break; }
            }
        }""")
        page.wait_for_timeout(200)

    # Mode
    page.evaluate("""(mode) => {
        for (var b of document.querySelectorAll('button.options')) {
            if ((b.innerText || '').trim() === mode) { b.click(); return; }
        }
    }""", mode)
    page.wait_for_timeout(300)

    # Generate
    before_count = page.evaluate("() => document.querySelectorAll('img[src*=\"static.dzine.ai/stylar_product/p/\"]').length")
    gen = page.evaluate("""() => {
        var btn = document.querySelector('button.generative.ready');
        if (btn && !btn.disabled) { btn.click(); return {clicked: true, text: (btn.innerText||'').trim()}; }
        var allBtns = [];
        for (var b of document.querySelectorAll('button.generative')) {
            allBtns.push({text: (b.innerText||'').trim(), disabled: b.disabled, cls: b.className.substring(0,60)});
        }
        return {error: 'not ready', buttons: allBtns};
    }""")
    print(f"  Generate: {json.dumps(gen)}", flush=True)

    if not gen.get('clicked'):
        return []

    page.wait_for_timeout(2000)
    new_count = wait_for_new_images(page, before_count, max_wait=90, label=label or style)

    downloaded = []
    if new_count > 0:
        urls = page.evaluate("""(count) => {
            var imgs = document.querySelectorAll('img[src*="static.dzine.ai/stylar_product/p/"]');
            var urls = [];
            for (var i = Math.max(0, imgs.length - count); i < imgs.length; i++) urls.push(imgs[i].src);
            return urls;
        }""", new_count)
        ts = int(time.time())
        for i, url in enumerate(urls):
            path = DOWNLOAD_DIR / f"dzine_{label or 'img2img'}_{ts}_{i}.webp"
            try:
                urllib.request.urlretrieve(url, str(path))
                size = path.stat().st_size
                downloaded.append(str(path))
                print(f"  Downloaded: {path.name} ({size/1024:.1f} KB)", flush=True)
            except Exception as e:
                print(f"  Download failed: {e}", flush=True)

        # Preview last result
        page.evaluate("""() => {
            var imgs = document.querySelectorAll('img[src*="static.dzine.ai/stylar_product/p/"]');
            if (imgs.length > 0) imgs[imgs.length - 1].click();
        }""")
        page.wait_for_timeout(2000)

    return downloaded


def main():
    print("=" * 60, flush=True)
    print("PHASE 130: Img2Img fidelity test on clean canvas", flush=True)
    print("=" * 60, flush=True)

    pw = sync_playwright().start()
    browser = pw.chromium.connect_over_cdp("http://127.0.0.1:18800", timeout=15000)
    ctx = browser.contexts[0]

    # Close old dzine tabs
    for p in ctx.pages:
        if "dzine.ai" in (p.url or ""):
            try:
                p.close()
            except Exception:
                pass

    page = ctx.new_page()
    page.set_viewport_size({"width": 1440, "height": 900})

    # ============================================================
    #  TEST 1: Img2Img on the foam mats (already on canvas 19860799)
    # ============================================================
    print("\n=== TEST 1: Img2Img on existing canvas (foam mats) ===", flush=True)

    page.goto(NEW_CANVAS, wait_until="domcontentloaded", timeout=30000)
    wait_for_canvas(page)
    close_dialogs(page)

    layers = page.evaluate("() => document.querySelectorAll('.layer-item').length")
    print(f"  Layers: {layers}", flush=True)
    ss(page, "P130_01_canvas_start")

    # First: use Describe Canvas to verify what Dzine sees
    open_sidebar_tool(page, 252)
    page.evaluate("""() => {
        var ta = document.querySelector('.img2img-config-panel textarea, TEXTAREA.len-1800');
        if (ta) { ta.value = ''; ta.dispatchEvent(new Event('input', {bubbles: true})); }
    }""")
    page.wait_for_timeout(500)
    page.evaluate("""() => {
        var btn = document.querySelector('button.autoprompt');
        if (btn) btn.click();
    }""")
    page.wait_for_timeout(6000)

    desc = page.evaluate("""() => {
        var ta = document.querySelector('.img2img-config-panel textarea, TEXTAREA.len-1800');
        return ta ? ta.value : '';
    }""")
    print(f"  Describe Canvas: '{desc[:200]}'", flush=True)
    close_all_panels(page)

    # Run Img2Img with Realistic Product + max fidelity
    prompt = "Professional product photo. Exact product on clean white studio backdrop. Preserve every physical detail, shape, material, color, branding. No modifications."
    files1 = run_img2img(
        page, prompt,
        style="Realistic Product",
        struct_match=0.98,
        style_intensity=0.10,
        color_match=True,
        mode="Normal",
        label="foam_fidelity"
    )
    ss(page, "P130_02_foam_result")
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)

    # ============================================================
    #  TEST 2: Also test with different style intensities
    # ============================================================
    print("\n=== TEST 2: Same product, higher style intensity ===", flush=True)
    close_all_panels(page)
    page.wait_for_timeout(500)

    files2 = run_img2img(
        page, prompt,
        style="Realistic Product",
        struct_match=0.80,
        style_intensity=0.50,
        color_match=True,
        mode="Normal",
        label="foam_medium"
    )
    ss(page, "P130_03_medium_result")
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)

    # ============================================================
    #  TEST 3: Download a DIFFERENT product from Amazon + test
    # ============================================================
    print("\n=== TEST 3: New product — Amazon headphones ===", flush=True)

    # Open Amazon in a new tab
    amz_page = ctx.new_page()
    amz_page.set_viewport_size({"width": 1440, "height": 900})

    headphones_ref = None
    try:
        # Sony WH-1000XM5
        amz_page.goto("https://www.amazon.com/dp/B09XS7JWHH", wait_until="domcontentloaded", timeout=30000)
        amz_page.wait_for_timeout(4000)
        close_dialogs(amz_page)

        # Get hi-res images
        img_urls = amz_page.evaluate("""() => {
            var urls = new Set();
            // Landing image
            var landing = document.querySelector('#landingImage');
            if (landing) {
                var hi = landing.getAttribute('data-old-hires');
                if (hi) urls.add(hi);
                var dyn = landing.getAttribute('data-a-dynamic-image');
                if (dyn) {
                    try {
                        for (var u of Object.keys(JSON.parse(dyn))) {
                            if (u.includes('SL1500') || u.includes('SL1200')) urls.add(u);
                        }
                    } catch(e) {}
                }
            }
            // colorImages script data
            for (var s of document.querySelectorAll('script')) {
                var t = s.textContent || '';
                var m = t.match(/'colorImages'\\s*:\\s*\\{\\s*'initial'\\s*:\\s*(\\[.+?\\])/s);
                if (m) {
                    try {
                        for (var item of JSON.parse(m[1])) {
                            if (item.hiRes) urls.add(item.hiRes);
                        }
                    } catch(e) {}
                }
            }
            // Alt images
            for (var img of document.querySelectorAll('#altImages img')) {
                var src = img.src || '';
                var hires = src.replace(/\._[A-Z0-9_,]+_\./, '._SL1500_.');
                if (hires !== src) urls.add(hires);
            }
            return [...urls].filter(u => u.includes('.jpg') || u.includes('.png'));
        }""")
        print(f"  Found {len(img_urls)} Amazon image URLs", flush=True)

        ss(amz_page, "P130_04_amazon_page")

        # Download the main product image
        if img_urls:
            for i, url in enumerate(img_urls[:1]):  # Just the main image
                fname = f"amazon_headphones_{int(time.time())}.jpg"
                fpath = DOWNLOAD_DIR / fname
                try:
                    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                    with urllib.request.urlopen(req, timeout=15) as resp:
                        data = resp.read()
                    with open(fpath, 'wb') as f:
                        f.write(data)
                    print(f"  Downloaded: {fname} ({len(data)/1024:.1f} KB)", flush=True)
                    headphones_ref = str(fpath)
                except Exception as e:
                    print(f"  Download failed: {e}", flush=True)

        if not headphones_ref:
            # Screenshot fallback
            landing = amz_page.locator("#landingImage")
            if landing.count() > 0 and landing.first.is_visible():
                headphones_ref = str(DOWNLOAD_DIR / "amazon_headphones_screenshot.png")
                landing.first.screenshot(path=headphones_ref)
                print(f"  Screenshot: {headphones_ref}", flush=True)

    except Exception as e:
        print(f"  Amazon page error: {e}", flush=True)
    finally:
        amz_page.close()

    if headphones_ref:
        print(f"  Reference: {headphones_ref} ({os.path.getsize(headphones_ref)/1024:.1f} KB)", flush=True)

        # Create another new project for headphones test
        print("\n  Creating new canvas for headphones...", flush=True)
        page.goto("https://www.dzine.ai/home", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(3000)
        close_dialogs(page)

        # Click "New project - Create a blank canvas"
        page.evaluate("""() => {
            for (var el of document.querySelectorAll('*')) {
                var text = (el.innerText || '').trim().toLowerCase();
                if (text.includes('new project') && text.includes('blank')) {
                    el.click();
                    return text;
                }
            }
            // Fallback: look for the create button with class
            var btn = document.querySelector('.project-item.create');
            if (btn) { btn.click(); return 'class match'; }
            return null;
        }""")
        page.wait_for_timeout(5000)
        close_dialogs(page)

        new_url = page.url
        print(f"  New canvas URL: {new_url}", flush=True)

        if "/canvas" in new_url:
            wait_for_canvas(page)
            close_dialogs(page)

            # Dismiss project setup dialog if any
            page.evaluate("""() => {
                var cancel = document.querySelector('button:has-text("Cancel")');
                if (cancel) cancel.click();
                var apply = document.querySelector('button:has-text("Apply")');
                if (apply) apply.click();
            }""")
            page.wait_for_timeout(1000)
            close_dialogs(page)

            # Upload headphones image
            uploaded = upload_image_to_canvas(page, headphones_ref)
            if uploaded:
                print("  Headphones on canvas!", flush=True)
                ss(page, "P130_05_headphones_canvas")

                # Verify via Describe Canvas
                open_sidebar_tool(page, 252)
                page.evaluate("""() => {
                    var ta = document.querySelector('.img2img-config-panel textarea, TEXTAREA.len-1800');
                    if (ta) { ta.value = ''; ta.dispatchEvent(new Event('input', {bubbles: true})); }
                }""")
                page.wait_for_timeout(500)
                page.evaluate("""() => {
                    var btn = document.querySelector('button.autoprompt');
                    if (btn) btn.click();
                }""")
                page.wait_for_timeout(6000)

                hp_desc = page.evaluate("""() => {
                    var ta = document.querySelector('.img2img-config-panel textarea, TEXTAREA.len-1800');
                    return ta ? ta.value : '';
                }""")
                print(f"  Headphones describe: '{hp_desc[:200]}'", flush=True)
                close_all_panels(page)

                # Run Img2Img
                hp_prompt = "Professional product photo of wireless headphones on clean white studio backdrop. Preserve exact product design, shape, ear cups, headband, buttons, logo, and color with 100% accuracy."
                files3 = run_img2img(
                    page, hp_prompt,
                    style="Realistic Product",
                    struct_match=0.98,
                    style_intensity=0.10,
                    color_match=True,
                    mode="Normal",
                    label="headphones"
                )
                ss(page, "P130_06_headphones_result")
                page.keyboard.press("Escape")
                page.wait_for_timeout(500)

                # Also try with NO style (No Style v2) to preserve max structure
                print("\n  Testing with No Style v2 (max preservation)...", flush=True)
                close_all_panels(page)
                files4 = run_img2img(
                    page, hp_prompt,
                    style="No Style v2",
                    struct_match=0.98,
                    style_intensity=0.10,
                    color_match=True,
                    mode="Normal",
                    label="hp_nostyle"
                )
                ss(page, "P130_07_nostyle_result")
                page.keyboard.press("Escape")

            else:
                print("  FAILED to upload headphones to canvas", flush=True)
        else:
            print(f"  Could not create new canvas for headphones", flush=True)
    else:
        print("  No headphones image available — skipping test 3", flush=True)

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
    print(f"PHASE 130 SUMMARY", flush=True)
    print(f"{'='*60}", flush=True)
    print(f"  Credits: {credits}", flush=True)
    print(f"  Test 1 (foam, max fidelity): {len(files1)} files", flush=True)
    print(f"  Test 2 (foam, medium style): {len(files2)} files", flush=True)
    if headphones_ref:
        print(f"  Headphones ref: {headphones_ref}", flush=True)
    print(f"  Canvas URL: {page.url}", flush=True)
    print(f"\n  REVIEW: Check screenshots P130_02/03/06/07 for product fidelity.", flush=True)
    print(f"  The key question: do generated images preserve exact product shape/detail?", flush=True)

    ss(page, "P130_08_final")
    print(f"\n===== PHASE 130 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
