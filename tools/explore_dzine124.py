"""Phase 124: Fix CC Reference upload + hi-res Amazon + Variation test.
P123: Reference mode mapped, file chooser timed out. Insert Character = 28 credits.

Goal: 1) Retry CC Reference upload with longer timeout + different approach
      2) Get hi-res Amazon product images (data-old-hires)
      3) Test Variation on an existing result
      4) Test style selection in CC mode
      5) Map the Negative Prompt in Txt2Img
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
    #  STEP 1: Get hi-res Amazon product images
    # ============================================================
    print("\n=== STEP 1: Hi-res Amazon images ===", flush=True)

    amz = ctx.new_page()
    amz.set_viewport_size({"width": 1440, "height": 900})

    product_images_hires = []
    try:
        amz.goto("https://www.amazon.com/dp/B0C8PSRWFX", wait_until="domcontentloaded", timeout=30000)
        amz.wait_for_timeout(5000)

        # Get hi-res images from the colorImages data structure
        hires = amz.evaluate("""() => {
            var results = [];

            // Method 1: Parse colorImages from script tags
            var scripts = document.querySelectorAll('script');
            for (var s of scripts) {
                var text = s.textContent || '';
                if (text.includes('colorImages')) {
                    // Try to find the initial image array
                    var match = text.match(/"colorImages"\\s*:\\s*\\{\\s*"initial"\\s*:\\s*(\\[.*?\\])\\s*\\}/s);
                    if (!match) match = text.match(/'colorImages'\\s*:\\s*\\{\\s*'initial'\\s*:\\s*(\\[.*?\\])\\s*\\}/s);
                    if (match) {
                        try {
                            var data = JSON.parse(match[1]);
                            for (var item of data) {
                                results.push({
                                    hiRes: item.hiRes || null,
                                    large: item.large || null,
                                    variant: item.variant || 'MAIN',
                                });
                            }
                        } catch(e) {}
                    }
                }
            }

            // Method 2: data-a-dynamic-image on landingImage
            var main = document.querySelector('#landingImage');
            if (main) {
                var dynData = main.getAttribute('data-a-dynamic-image');
                if (dynData) {
                    try {
                        var parsed = JSON.parse(dynData);
                        // Keys are URLs, values are [width, height]
                        for (var url in parsed) {
                            var dims = parsed[url];
                            results.push({hiRes: url, dims: dims});
                        }
                    } catch(e) {}
                }
            }

            // Method 3: Click each thumbnail to reveal hi-res in main image
            var thumbs = document.querySelectorAll('#altImages .imageThumbnail');
            var thumbInfo = [];
            for (var t of thumbs) {
                var img = t.querySelector('img');
                if (img) {
                    thumbInfo.push({
                        src: img.src,
                        // Try to build hi-res URL
                        hiRes: img.src.replace(/\\._[A-Z]{2}_[A-Z]{2,3}\\d+_\\./, '._AC_SL1500_.'),
                    });
                }
            }

            return {colorImages: results, thumbs: thumbInfo};
        }""")

        print(f"  colorImages entries: {len(hires.get('colorImages', []))}", flush=True)
        for item in hires.get('colorImages', []):
            if item.get('hiRes'):
                print(f"    hiRes: {item['hiRes'][:90]}...", flush=True)
                product_images_hires.append(item['hiRes'])
            elif item.get('large'):
                print(f"    large: {item['large'][:90]}...", flush=True)
                product_images_hires.append(item['large'])

        print(f"  Thumbnails: {len(hires.get('thumbs', []))}", flush=True)
        for t in hires.get('thumbs', [])[:5]:
            print(f"    hiRes build: {t['hiRes'][:90]}...", flush=True)

        # Download the best hi-res images
        for i, url in enumerate(product_images_hires[:6]):
            try:
                ext = '.jpg'
                filename = f"amazon_hires_{i}{ext}"
                filepath = DOWNLOAD_DIR / filename
                urllib.request.urlretrieve(url, str(filepath))
                size = filepath.stat().st_size
                print(f"    Downloaded: {filename} ({size/1024:.1f} KB)", flush=True)
            except Exception as e:
                print(f"    Failed [{i}]: {e}", flush=True)

    except Exception as e:
        print(f"  Amazon error: {e}", flush=True)

    try:
        amz.close()
    except Exception:
        pass

    # ============================================================
    #  STEP 2: CC Reference upload — retry with multiple approaches
    # ============================================================
    print("\n=== STEP 2: CC Reference upload retry ===", flush=True)

    open_sidebar_tool(page, 306)

    # Enter Generate Images
    page.evaluate("""() => {
        for (var b of document.querySelectorAll('.collapse-option')) {
            if ((b.innerText || '').includes('Generate Images')) { b.click(); return; }
        }
    }""")
    page.wait_for_timeout(2000)

    # Select Ray
    page.evaluate("""() => {
        var list = document.querySelector('.c-character-list');
        if (list) {
            for (var item of list.querySelectorAll('.item, button')) {
                if ((item.innerText || '').trim() === 'Ray') { item.click(); return; }
            }
        }
    }""")
    page.wait_for_timeout(2000)

    # Click Reference mode
    page.evaluate("""() => {
        for (var b of document.querySelectorAll('button.options')) {
            if ((b.innerText || '').trim() === 'Reference') { b.click(); return; }
        }
    }""")
    page.wait_for_timeout(1500)

    # Find the pick-image button
    pick_btn = page.evaluate("""() => {
        var btn = document.querySelector('.pick-image.cc-pick-image');
        if (!btn) return null;
        var r = btn.getBoundingClientRect();
        return {x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2),
                w: Math.round(r.width), h: Math.round(r.height)};
    }""")
    print(f"  Pick Image button: {json.dumps(pick_btn)}", flush=True)

    if pick_btn:
        # Use the best hi-res product image
        ref_path = None
        for name in ["amazon_hires_0.jpg", "amazon_angle_5.jpg", "amazon_product_ref.jpg"]:
            p = DOWNLOAD_DIR / name
            if p.exists():
                ref_path = str(p)
                break

        if ref_path:
            print(f"  Using reference: {ref_path}", flush=True)

            # Approach 1: expect_file_chooser with 10s timeout
            print("  Approach 1: expect_file_chooser (10s timeout)...", flush=True)
            try:
                with page.expect_file_chooser(timeout=10000) as fc_info:
                    page.mouse.click(pick_btn['x'], pick_btn['y'])
                fc = fc_info.value
                fc.set_files(ref_path)
                print("  SUCCESS: File chooser triggered!", flush=True)
                page.wait_for_timeout(3000)
            except Exception as e1:
                print(f"  Approach 1 failed: {e1}", flush=True)

                # Approach 2: Try double-click
                print("  Approach 2: double-click...", flush=True)
                try:
                    with page.expect_file_chooser(timeout=10000) as fc_info:
                        page.mouse.dblclick(pick_btn['x'], pick_btn['y'])
                    fc = fc_info.value
                    fc.set_files(ref_path)
                    print("  SUCCESS: File chooser triggered via double-click!", flush=True)
                    page.wait_for_timeout(3000)
                except Exception as e2:
                    print(f"  Approach 2 failed: {e2}", flush=True)

                    # Approach 3: JS click the inner element
                    print("  Approach 3: JS-click inner elements...", flush=True)
                    inner_click = page.evaluate("""() => {
                        var btn = document.querySelector('.pick-image.cc-pick-image');
                        if (!btn) return 'no button';
                        // Check for hidden input[type=file]
                        var input = btn.querySelector('input[type="file"]');
                        if (input) return 'found input';
                        // Check for input nearby in DOM
                        var parent = btn.parentElement;
                        if (parent) {
                            input = parent.querySelector('input[type="file"]');
                            if (input) return 'found input in parent';
                        }
                        // Check all inputs on page
                        var allInputs = document.querySelectorAll('input[type="file"]');
                        return 'file inputs on page: ' + allInputs.length;
                    }""")
                    print(f"  Inner check: {inner_click}", flush=True)

                    # Approach 4: Listen for dynamically created input
                    print("  Approach 4: Watch for dynamic input[type=file]...", flush=True)
                    try:
                        page.evaluate("""() => {
                            window._fileInputCreated = false;
                            var observer = new MutationObserver(function(mutations) {
                                for (var m of mutations) {
                                    for (var n of m.addedNodes) {
                                        if (n.tagName === 'INPUT' && n.type === 'file') {
                                            window._fileInputCreated = true;
                                            window._fileInput = n;
                                        }
                                    }
                                }
                            });
                            observer.observe(document.body, {childList: true, subtree: true});
                        }""")

                        # Click the button
                        page.mouse.click(pick_btn['x'], pick_btn['y'])
                        page.wait_for_timeout(2000)

                        dynamic = page.evaluate("""() => {
                            return {
                                created: window._fileInputCreated,
                                fileInputs: document.querySelectorAll('input[type="file"]').length,
                            };
                        }""")
                        print(f"  Dynamic input watch: {json.dumps(dynamic)}", flush=True)

                        if dynamic.get('created') or dynamic.get('fileInputs', 0) > 0:
                            # Try setting files on the found input
                            try:
                                with page.expect_file_chooser(timeout=5000) as fc_info:
                                    page.evaluate("""() => {
                                        var input = window._fileInput || document.querySelector('input[type="file"]');
                                        if (input) input.click();
                                    }""")
                                fc = fc_info.value
                                fc.set_files(ref_path)
                                print("  SUCCESS: File set via dynamic input!", flush=True)
                                page.wait_for_timeout(3000)
                            except Exception as e4:
                                print(f"  Approach 4 failed: {e4}", flush=True)
                    except Exception as e:
                        print(f"  Observer setup error: {e}", flush=True)

        ss(page, "P124_01_reference_upload")

    # Check if reference image was loaded
    ref_loaded = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return {error: 'no panel'};
        // Check for uploaded image in the reference area
        var imgs = panel.querySelectorAll('img');
        var refImgs = [];
        for (var img of imgs) {
            var r = img.getBoundingClientRect();
            if (r.width > 50 && r.y > 560 && r.y < 650) {
                refImgs.push({src: (img.src || '').substring(0, 80), w: Math.round(r.width), h: Math.round(r.height)});
            }
        }
        return {refImages: refImgs};
    }""")
    print(f"  Reference loaded check: {json.dumps(ref_loaded)}", flush=True)

    # ============================================================
    #  STEP 3: Test Variation on existing result
    # ============================================================
    print("\n=== STEP 3: Test Variation ===", flush=True)

    close_all_panels(page)
    page.wait_for_timeout(500)

    # Switch to Results tab
    page.evaluate("""() => {
        for (var el of document.querySelectorAll('[class*="header-item"]')) {
            if ((el.innerText || '').trim() === 'Results') { el.click(); return; }
        }
    }""")
    page.wait_for_timeout(1000)

    # Click first visible result to open preview
    page.evaluate("""() => {
        var imgs = document.querySelectorAll('img[src*="static.dzine.ai/stylar_product/p/"]');
        for (var img of imgs) {
            var r = img.getBoundingClientRect();
            if (r.width > 50 && r.y > 50 && r.y < 800) {
                img.click();
                return;
            }
        }
    }""")
    page.wait_for_timeout(2000)

    # Click Variation button
    var_result = page.evaluate("""() => {
        var btn = document.querySelector('.handle-item.variation');
        if (!btn) return {error: 'no variation button'};
        var r = btn.getBoundingClientRect();
        return {x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)};
    }""")
    print(f"  Variation button: {json.dumps(var_result)}", flush=True)

    if var_result.get('x'):
        before_count = page.evaluate("() => document.querySelectorAll('img[src*=\"static.dzine.ai/stylar_product/p/\"]').length")

        page.mouse.click(var_result['x'], var_result['y'])
        print("  Clicked Variation!", flush=True)
        page.wait_for_timeout(2000)

        # Check what happened — did it go to a variation panel or start generating?
        var_state = page.evaluate("""() => {
            var preview = document.querySelector('#result-preview');
            var isVisible = preview ? window.getComputedStyle(preview).display !== 'none' : false;
            var panel = document.querySelector('.c-gen-config.show');
            var panelText = panel ? (panel.innerText || '').substring(0, 200) : '';
            return {previewVisible: isVisible, panelOpen: !!panel, panelText: panelText};
        }""")
        print(f"  After Variation click: {json.dumps(var_state)}", flush=True)

        if var_state.get('panelOpen'):
            # A panel opened — this is likely the variation settings
            ss(page, "P124_02_variation_panel")
        else:
            # Maybe it started generating directly
            new_count = wait_for_new_images(page, before_count, max_wait=60, label="Variation")
            ss(page, "P124_02_variation_result")

    # Close preview
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)

    # ============================================================
    #  STEP 4: Txt2Img — map negative prompt / advanced settings
    # ============================================================
    print("\n=== STEP 4: Txt2Img advanced settings ===", flush=True)

    open_sidebar_tool(page, 197)

    # Click "Advanced" button to expand
    page.evaluate("""() => {
        var btn = document.querySelector('.advanced-btn');
        if (btn) btn.click();
    }""")
    page.wait_for_timeout(1000)

    # Map the advanced section
    advanced = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return {error: 'no panel'};

        // Get the full panel text to find advanced section
        var text = (panel.innerText || '').substring(0, 1500);

        // Find all form elements
        var elements = [];
        for (var el of panel.querySelectorAll('button, textarea, input, [class*="slider"], [class*="switch"], [class*="seed"]')) {
            var r = el.getBoundingClientRect();
            if (r.width < 15 || r.y < 300) continue;  // Skip top section already mapped
            elements.push({
                tag: el.tagName,
                cls: (el.className || '').toString().substring(0, 60),
                text: (el.innerText || '').trim().substring(0, 35),
                type: el.type || '',
                placeholder: (el.placeholder || '').substring(0, 30),
                value: (el.value || '').substring(0, 30),
                x: Math.round(r.x), y: Math.round(r.y),
                w: Math.round(r.width), h: Math.round(r.height),
            });
        }

        return {text: text, elements: elements.slice(0, 20)};
    }""")

    print(f"  Panel text:\n{advanced.get('text', '')[:800]}", flush=True)
    print(f"\n  Advanced elements ({len(advanced.get('elements', []))}):", flush=True)
    for e in advanced.get('elements', []):
        v = f" val='{e['value']}'" if e.get('value') else ""
        ph = f" ph='{e['placeholder']}'" if e.get('placeholder') else ""
        print(f"    <{e['tag']}> .{e['cls'][:45]} '{e['text'][:28]}'{v}{ph} ({e['x']},{e['y']}) {e['w']}x{e['h']}", flush=True)

    ss(page, "P124_03_advanced_settings")

    # ============================================================
    #  STEP 5: Check what styles produce best product photos
    # ============================================================
    print("\n=== STEP 5: Best styles for product photography ===", flush=True)

    # Open style picker
    page.evaluate("""() => {
        var btn = document.querySelector('button.style');
        if (btn) btn.click();
    }""")
    page.wait_for_timeout(2000)

    # Search for "realistic" styles
    search_result = page.evaluate("""() => {
        var input = document.querySelector('.style-list-panel input[type="text"]');
        if (!input) return {error: 'no search input'};
        input.focus();
        input.value = 'realistic';
        input.dispatchEvent(new Event('input', {bubbles: true}));
        return {ok: true};
    }""")
    print(f"  Search: {json.dumps(search_result)}", flush=True)
    page.wait_for_timeout(1500)

    realistic_styles = page.evaluate("""() => {
        var items = document.querySelectorAll('[class*="style-item"]');
        var styles = [];
        for (var item of items) {
            var r = item.getBoundingClientRect();
            if (r.width < 30 || r.height < 30) continue;
            var name = (item.innerText || '').trim();
            if (name.length > 0 && name.length < 40) {
                styles.push({
                    name: name,
                    active: (item.className || '').includes('active'),
                });
            }
        }
        return styles;
    }""")
    print(f"  Realistic styles ({len(realistic_styles)}):", flush=True)
    for s in realistic_styles:
        act = " [ACTIVE]" if s['active'] else ""
        print(f"    {s['name']}{act}", flush=True)

    ss(page, "P124_04_realistic_styles")

    # Also search "photo"
    page.evaluate("""() => {
        var input = document.querySelector('.style-list-panel input[type="text"]');
        if (input) {
            input.value = 'photo';
            input.dispatchEvent(new Event('input', {bubbles: true}));
        }
    }""")
    page.wait_for_timeout(1500)

    photo_styles = page.evaluate("""() => {
        var items = document.querySelectorAll('[class*="style-item"]');
        var styles = [];
        for (var item of items) {
            var r = item.getBoundingClientRect();
            if (r.width < 30 || r.height < 30) continue;
            var name = (item.innerText || '').trim();
            if (name.length > 0 && name.length < 40) {
                styles.push(name);
            }
        }
        return styles;
    }""")
    print(f"\n  Photo styles ({len(photo_styles)}): {photo_styles[:10]}", flush=True)

    # Close style picker
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)

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

    ss(page, "P124_05_final")
    print(f"\n\n===== PHASE 124 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
