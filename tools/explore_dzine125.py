"""Phase 125: Realistic Product style + negative prompt + hi-res product test.
P124: CC Reference upload blocked (0x0). "Realistic Product" style found. Variation works but slow.

Strategy: Product shots = Img2Img + real Amazon photo + Realistic Product style + high Structure Match.

Goal: 1) Download hi-res Amazon images (SL1500 thumbnails)
      2) Place hi-res product on canvas
      3) Img2Img with "Realistic Product" style + high structure match
      4) Find and map negative prompt / seed fields
      5) Test with "Dzine Realistic v3" style for comparison
      6) Measure quality difference between styles
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


def select_style(page, style_name):
    """Select a style by name in the open style picker."""
    result = page.evaluate("""(name) => {
        var items = document.querySelectorAll('[class*="style-item"]');
        for (var item of items) {
            var text = (item.innerText || '').trim();
            if (text === name) {
                item.click();
                return {selected: name};
            }
        }
        // Try search first
        var input = document.querySelector('.style-list-panel input[type="text"]');
        if (input) {
            input.value = name;
            input.dispatchEvent(new Event('input', {bubbles: true}));
        }
        return {searched: name};
    }""", style_name)
    return result


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
    #  STEP 1: Get hi-res Amazon images (SL1500 versions)
    # ============================================================
    print("\n=== STEP 1: Hi-res Amazon images (SL1500) ===", flush=True)

    amz = ctx.new_page()
    amz.set_viewport_size({"width": 1440, "height": 900})

    hires_paths = []
    try:
        amz.goto("https://www.amazon.com/dp/B0C8PSRWFX", wait_until="domcontentloaded", timeout=30000)
        amz.wait_for_timeout(5000)

        # Get unique image IDs from thumbnails and build SL1500 URLs
        hi_res_urls = amz.evaluate("""() => {
            var ids = new Set();
            // Get from altImages thumbnails
            var thumbs = document.querySelectorAll('#altImages img');
            for (var t of thumbs) {
                var match = (t.src || '').match(/images\\/I\\/([^.]+)/);
                if (match) ids.add(match[1]);
            }
            // Get from main image
            var main = document.querySelector('#landingImage');
            if (main) {
                var match = (main.src || '').match(/images\\/I\\/([^.]+)/);
                if (match) ids.add(match[1]);
            }

            // Build SL1500 URLs for each unique ID
            var urls = [];
            for (var id of ids) {
                urls.push({
                    id: id,
                    url: 'https://m.media-amazon.com/images/I/' + id + '._AC_SL1500_.jpg',
                });
            }
            return urls;
        }""")

        print(f"  Unique image IDs: {len(hi_res_urls)}", flush=True)
        for item in hi_res_urls:
            try:
                filename = f"amazon_SL1500_{item['id'][:10]}.jpg"
                filepath = DOWNLOAD_DIR / filename
                urllib.request.urlretrieve(item['url'], str(filepath))
                size = filepath.stat().st_size
                if size > 5000:  # Only keep decent-size images
                    hires_paths.append(str(filepath))
                    print(f"    {item['id'][:15]}: {size/1024:.1f} KB", flush=True)
                else:
                    filepath.unlink()
                    print(f"    {item['id'][:15]}: TOO SMALL ({size} bytes), skipped", flush=True)
            except Exception as e:
                print(f"    {item['id'][:15]}: FAILED - {e}", flush=True)

    except Exception as e:
        print(f"  Amazon error: {e}", flush=True)

    try:
        amz.close()
    except Exception:
        pass

    print(f"\n  Hi-res images saved: {len(hires_paths)}", flush=True)

    # ============================================================
    #  STEP 2: Place hi-res product on canvas via drop
    # ============================================================
    print("\n=== STEP 2: Place product on canvas ===", flush=True)

    # Use the largest hi-res image
    best_ref = None
    best_size = 0
    for p in hires_paths:
        s = os.path.getsize(p)
        if s > best_size:
            best_size = s
            best_ref = p

    if not best_ref and (DOWNLOAD_DIR / "amazon_product_ref.jpg").exists():
        best_ref = str(DOWNLOAD_DIR / "amazon_product_ref.jpg")
        best_size = os.path.getsize(best_ref)

    print(f"  Best reference: {best_ref} ({best_size/1024:.1f} KB)", flush=True)

    if best_ref:
        # Read the image file and encode as base64 for JS injection
        import base64
        with open(best_ref, 'rb') as f:
            img_data = base64.b64encode(f.read()).decode('ascii')

        # Create a data URL and drop it on canvas
        placed = page.evaluate("""(imgBase64) => {
            return new Promise(async (resolve) => {
                try {
                    // Convert base64 to blob
                    var byteChars = atob(imgBase64);
                    var byteArray = new Uint8Array(byteChars.length);
                    for (var i = 0; i < byteChars.length; i++) {
                        byteArray[i] = byteChars.charCodeAt(i);
                    }
                    var blob = new Blob([byteArray], {type: 'image/jpeg'});
                    var file = new File([blob], 'product.jpg', {type: 'image/jpeg'});

                    // Try clipboard paste approach
                    try {
                        var item = new ClipboardItem({'image/jpeg': blob});
                        await navigator.clipboard.write([item]);
                        resolve('clipboard_ready');
                        return;
                    } catch(e) {
                        // Try DataTransfer drop
                        var dt = new DataTransfer();
                        dt.items.add(file);
                        var canvas = document.querySelector('.canvas-container');
                        if (!canvas) { resolve('no canvas'); return; }
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
                    }
                } catch(e) {
                    resolve('error: ' + e.message);
                }
            });
        }""", img_data)
        print(f"  Placement: {placed}", flush=True)

        if placed == 'clipboard_ready':
            # Focus canvas and paste
            page.mouse.click(700, 450)
            page.wait_for_timeout(500)
            page.keyboard.press("Meta+v")
            page.wait_for_timeout(3000)
            print("  Pasted from clipboard", flush=True)
        else:
            page.wait_for_timeout(3000)

        layers = page.evaluate("() => document.querySelectorAll('.layer-item').length")
        print(f"  Layers: {layers}", flush=True)

    ss(page, "P125_01_product_placed")

    # ============================================================
    #  STEP 3: Img2Img with "Realistic Product" style
    # ============================================================
    print("\n=== STEP 3: Img2Img + Realistic Product style ===", flush=True)

    open_sidebar_tool(page, 252)

    # Click the style selector (.style-name for Img2Img)
    page.evaluate("""() => {
        var panel = document.querySelector('.img2img-config-panel, .c-gen-config.show');
        if (!panel) return;
        var styleName = panel.querySelector('.style-name');
        if (styleName) { styleName.click(); return; }
        var styleBtn = panel.querySelector('button.style');
        if (styleBtn) styleBtn.click();
    }""")
    page.wait_for_timeout(2000)

    # Search and select "Realistic Product"
    page.evaluate("""() => {
        var input = document.querySelector('.style-list-panel input[type="text"]');
        if (input) {
            input.value = 'Realistic Product';
            input.dispatchEvent(new Event('input', {bubbles: true}));
        }
    }""")
    page.wait_for_timeout(1500)

    style_selected = page.evaluate("""() => {
        var items = document.querySelectorAll('[class*="style-item"]');
        for (var item of items) {
            var text = (item.innerText || '').trim();
            if (text === 'Realistic Product') {
                item.click();
                return {selected: true, name: text};
            }
        }
        // Show what's visible
        var visible = [];
        for (var item of items) {
            var r = item.getBoundingClientRect();
            if (r.width > 30 && r.height > 30) {
                visible.push((item.innerText || '').trim());
            }
        }
        return {selected: false, visible: visible.slice(0, 10)};
    }""")
    print(f"  Style selection: {json.dumps(style_selected)}", flush=True)
    page.wait_for_timeout(1000)

    # Verify the style was set
    current_style = page.evaluate("""() => {
        var name = document.querySelector('.style-name');
        return name ? (name.innerText || '').trim() : 'unknown';
    }""")
    print(f"  Current style: {current_style}", flush=True)

    # Use "Describe Canvas" for auto-prompt
    page.evaluate("""() => {
        var btn = document.querySelector('button.autoprompt');
        if (btn) btn.click();
    }""")
    page.wait_for_timeout(5000)

    # Append product photography keywords
    page.evaluate("""() => {
        var ta = document.querySelector('.img2img-config-panel textarea, TEXTAREA.len-1800');
        if (ta) {
            ta.value = ta.value + ' Professional product photography, clean white background, soft studio lighting, high detail, commercial catalog quality.';
            ta.dispatchEvent(new Event('input', {bubbles: true}));
        }
    }""")
    page.wait_for_timeout(500)

    # Set Structure Match to maximum (click far right of slider)
    page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return;
        var sliders = panel.querySelectorAll('.c-slider');
        for (var s of sliders) {
            var prev = s.previousElementSibling;
            var label = prev ? (prev.innerText || '').trim() : '';
            if (label.includes('Structure')) {
                var r = s.getBoundingClientRect();
                // Click at 95% from left = maximum structure match
                var event = new MouseEvent('click', {
                    clientX: r.x + r.width * 0.95,
                    clientY: r.y + r.height / 2,
                    bubbles: true
                });
                s.dispatchEvent(event);
            }
        }
    }""")
    page.wait_for_timeout(500)

    # Enable Color Match
    page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return;
        // Find "Color Match" text and the nearby switch
        var text = panel.innerText || '';
        var switches = panel.querySelectorAll('.c-switch');
        // Color Match is typically the second switch in Img2Img
        if (switches.length >= 2) {
            var colorSwitch = switches[1];
            if (!colorSwitch.classList.contains('isChecked')) {
                colorSwitch.click();
            }
        }
    }""")
    page.wait_for_timeout(500)

    # Set Normal mode
    page.evaluate("""() => {
        for (var b of document.querySelectorAll('button.options')) {
            if ((b.innerText || '').trim() === 'Normal') { b.click(); return; }
        }
    }""")
    page.wait_for_timeout(500)

    ss(page, "P125_02_img2img_realistic")

    # Generate
    before_count = page.evaluate("() => document.querySelectorAll('img[src*=\"static.dzine.ai/stylar_product/p/\"]').length")

    gen = page.evaluate("""() => {
        var btn = document.querySelector('button.generative.ready');
        if (!btn || btn.disabled) return {error: 'not ready'};
        btn.click();
        return {clicked: true, credits: (btn.innerText || '').trim()};
    }""")
    print(f"  Generate: {json.dumps(gen)}", flush=True)

    page.wait_for_timeout(2000)
    new_count = wait_for_new_images(page, before_count, max_wait=90, label="RealisticProd")

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
            path = DOWNLOAD_DIR / f"dzine_realistic_product_{int(time.time())}_{i}.webp"
            try:
                urllib.request.urlretrieve(url, str(path))
                size = path.stat().st_size
                print(f"  Downloaded: {path.name} ({size/1024:.1f} KB)", flush=True)
            except Exception as e:
                print(f"  Download failed: {e}", flush=True)

    ss(page, "P125_03_realistic_result")

    # ============================================================
    #  STEP 4: Find negative prompt and seed
    # ============================================================
    print("\n=== STEP 4: Negative prompt / seed in Txt2Img ===", flush=True)

    open_sidebar_tool(page, 197)

    # Click Advanced to expand
    page.evaluate("""() => {
        var btn = document.querySelector('.advanced-btn');
        if (btn) btn.click();
    }""")
    page.wait_for_timeout(1000)

    # Scroll the panel down to reveal more fields
    scroll_result = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return {error: 'no panel'};

        // Try scrolling the panel content
        var scrollable = panel.querySelector('.scroll-container, .panel-content, [class*="scroll"]');
        if (!scrollable) {
            // Try the panel itself
            panel.scrollTop = panel.scrollHeight;
            scrollable = panel;
        } else {
            scrollable.scrollTop = scrollable.scrollHeight;
        }

        // Now scan for seed and negative prompt
        var fields = [];
        for (var el of panel.querySelectorAll('textarea, input, [class*="seed"], [class*="negative"]')) {
            var r = el.getBoundingClientRect();
            fields.push({
                tag: el.tagName,
                cls: (el.className || '').toString().substring(0, 60),
                type: el.type || '',
                placeholder: (el.placeholder || '').substring(0, 40),
                value: (el.value || '').substring(0, 30),
                x: Math.round(r.x), y: Math.round(r.y),
                w: Math.round(r.width), h: Math.round(r.height),
            });
        }

        // Get all text labels to find "Seed" and "Negative"
        var labels = [];
        for (var el of panel.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            if ((text.includes('Seed') || text.includes('seed') || text.includes('Negative') || text.includes('negative'))
                && text.length < 30) {
                var r = el.getBoundingClientRect();
                labels.push({text: text, x: Math.round(r.x), y: Math.round(r.y)});
            }
        }

        return {fields: fields, labels: labels};
    }""")

    print(f"  Fields:", flush=True)
    for f in scroll_result.get('fields', []):
        v = f" val='{f['value']}'" if f.get('value') else ""
        ph = f" ph='{f['placeholder']}'" if f.get('placeholder') else ""
        print(f"    <{f['tag']}> .{f['cls'][:45]} type={f['type']}{v}{ph} ({f['x']},{f['y']}) {f['w']}x{f['h']}", flush=True)

    print(f"\n  Labels with Seed/Negative:", flush=True)
    for l in scroll_result.get('labels', []):
        print(f"    '{l['text']}' at ({l['x']},{l['y']})", flush=True)

    ss(page, "P125_04_advanced_scroll")

    # Try more aggressive scroll
    page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (panel) {
            // Scroll all scrollable children
            for (var el of panel.querySelectorAll('*')) {
                if (el.scrollHeight > el.clientHeight) {
                    el.scrollTop = el.scrollHeight;
                }
            }
        }
    }""")
    page.wait_for_timeout(1000)

    # Re-check for seed field
    seed_check = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return {error: 'no panel'};
        var fullText = (panel.innerText || '');

        // Look for "Seed" keyword
        var seedIdx = fullText.indexOf('Seed');
        var negIdx = fullText.indexOf('Negative');
        var advIdx = fullText.indexOf('Advanced');

        // Check all input fields
        var inputs = [];
        for (var el of panel.querySelectorAll('input')) {
            inputs.push({
                type: el.type,
                cls: (el.className || '').toString().substring(0, 30),
                placeholder: el.placeholder || '',
                value: el.value || '',
                name: el.name || '',
            });
        }

        return {
            seedFound: seedIdx >= 0 ? seedIdx : -1,
            negativeFound: negIdx >= 0 ? negIdx : -1,
            advancedFound: advIdx >= 0 ? advIdx : -1,
            inputs: inputs,
            textAround: fullText.substring(Math.max(0, seedIdx - 20), seedIdx + 50),
        };
    }""")
    print(f"\n  Seed check: {json.dumps(seed_check)}", flush=True)

    ss(page, "P125_05_seed_check")

    # ============================================================
    #  STEP 5: Generate with "Dzine Realistic v3" for comparison
    # ============================================================
    print("\n=== STEP 5: Img2Img with Dzine Realistic v3 ===", flush=True)

    open_sidebar_tool(page, 252)

    # Change style to Dzine Realistic v3
    page.evaluate("""() => {
        var panel = document.querySelector('.img2img-config-panel, .c-gen-config.show');
        if (!panel) return;
        var styleName = panel.querySelector('.style-name');
        if (styleName) styleName.click();
    }""")
    page.wait_for_timeout(2000)

    page.evaluate("""() => {
        var input = document.querySelector('.style-list-panel input[type="text"]');
        if (input) {
            input.value = 'Dzine Realistic';
            input.dispatchEvent(new Event('input', {bubbles: true}));
        }
    }""")
    page.wait_for_timeout(1500)

    v3_selected = page.evaluate("""() => {
        var items = document.querySelectorAll('[class*="style-item"]');
        for (var item of items) {
            var text = (item.innerText || '').trim();
            if (text === 'Dzine Realistic v3') {
                item.click();
                return true;
            }
        }
        return false;
    }""")
    print(f"  Selected Dzine Realistic v3: {v3_selected}", flush=True)
    page.wait_for_timeout(1000)

    # Use same prompt + settings
    page.evaluate("""() => {
        var btn = document.querySelector('button.autoprompt');
        if (btn) btn.click();
    }""")
    page.wait_for_timeout(5000)

    page.evaluate("""() => {
        var ta = document.querySelector('.img2img-config-panel textarea, TEXTAREA.len-1800');
        if (ta) {
            ta.value = ta.value + ' Professional product photography, exact product preservation, no modifications to product shape or color.';
            ta.dispatchEvent(new Event('input', {bubbles: true}));
        }
    }""")
    page.wait_for_timeout(500)

    # Generate
    before_count = page.evaluate("() => document.querySelectorAll('img[src*=\"static.dzine.ai/stylar_product/p/\"]').length")

    gen2 = page.evaluate("""() => {
        var btn = document.querySelector('button.generative.ready');
        if (!btn || btn.disabled) return {error: 'not ready'};
        btn.click();
        return {clicked: true};
    }""")
    print(f"  Generate: {json.dumps(gen2)}", flush=True)

    page.wait_for_timeout(2000)
    new_count2 = wait_for_new_images(page, before_count, max_wait=90, label="DzineV3")

    if new_count2 > 0:
        urls = page.evaluate("""(count) => {
            var imgs = document.querySelectorAll('img[src*="static.dzine.ai/stylar_product/p/"]');
            var urls = [];
            for (var i = Math.max(0, imgs.length - count); i < imgs.length; i++) {
                urls.push(imgs[i].src);
            }
            return urls;
        }""", new_count2)
        for i, url in enumerate(urls):
            path = DOWNLOAD_DIR / f"dzine_realistic_v3_{int(time.time())}_{i}.webp"
            try:
                urllib.request.urlretrieve(url, str(path))
                size = path.stat().st_size
                print(f"  Downloaded: {path.name} ({size/1024:.1f} KB)", flush=True)
            except Exception as e:
                print(f"  Download failed: {e}", flush=True)

    ss(page, "P125_06_v3_result")

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

    ss(page, "P125_07_final")
    print(f"\n\n===== PHASE 125 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
