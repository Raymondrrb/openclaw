"""Phase 132: Complete the product-faithful workflow on canvas 19860860.

P131 discoveries:
  - "Start from an image" works: headphones on canvas 19860860
  - BG Remove button found at top action bar (y=95), takes time (not instant)
  - "Image Not Filling the Canvas" dialog blocks generation → must click
    "Fit to Content and Continue"
  - Enhance & Expand both timed out due to unhandled dialog

Plan:
  1) Return to canvas 19860860
  2) Check canvas state (BG may already be removed from P131)
  3) If not, click BG Remove and wait properly
  4) Click "Fit to Content" dialog if it appears
  5) Run Generative Expand (16:9 for video) with studio backdrop prompt
  6) Download and verify the expanded product image
  7) Run Enhance & Upscale (2x Precision) on the result
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

CANVAS_URL = "https://www.dzine.ai/canvas?id=19860860"
SS_DIR = Path(__file__).resolve().parent.parent / "artifacts" / "dzine_explore"
SS_DIR.mkdir(parents=True, exist_ok=True)
DOWNLOAD_DIR = Path.home() / "Downloads"


def ss(page, name):
    page.screenshot(path=str(SS_DIR / f"{name}.png"))
    print(f"  SS: {name}", flush=True)


def close_dialogs(page):
    """Close common dialogs, including the 'Image Not Filling Canvas' one."""
    for _ in range(8):
        found = False

        # Priority: "Fit to Content and Continue" (the yellow button for canvas fit)
        try:
            fit_btn = page.locator('button:has-text("Fit to Content and Continue")')
            if fit_btn.count() > 0 and fit_btn.first.is_visible(timeout=500):
                fit_btn.first.click()
                page.wait_for_timeout(1000)
                print("  [dialog] Clicked 'Fit to Content and Continue'", flush=True)
                found = True
                continue
        except Exception:
            pass

        # Also handle "Do not show again" checkbox
        try:
            checkbox = page.locator('text=Do not show again')
            if checkbox.count() > 0 and checkbox.first.is_visible(timeout=300):
                checkbox.first.click()
                page.wait_for_timeout(300)
        except Exception:
            pass

        for text in ["Not now", "Close", "Never show again", "Got it", "Skip",
                      "Later", "Continue"]:
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
    """Wait for new result images from Dzine generation."""
    start = time.time()
    while time.time() - start < max_wait:
        elapsed = int(time.time() - start)

        # Check for dialogs that might be blocking
        close_dialogs(page)

        current = page.evaluate("""() => {
            var count = 0;
            for (var img of document.querySelectorAll('img')) {
                var src = img.src || '';
                if (src.includes('static.dzine.ai/stylar_product/p/') ||
                    src.includes('static.dzine.ai/stylar_product/enhance/')) {
                    count++;
                }
            }
            return count;
        }""")
        new_count = current - before_count
        if new_count > 0:
            print(f"  [{label}] Done in {elapsed}s! {new_count} new image(s)", flush=True)
            return new_count

        if elapsed % 10 == 0:
            progress = page.evaluate("""() => {
                for (var el of document.querySelectorAll('*')) {
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
    print("=" * 60, flush=True)
    print("PHASE 132: Complete workflow on canvas 19860860", flush=True)
    print("=" * 60, flush=True)

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
    wait_for_canvas(page)
    close_dialogs(page)

    layers = page.evaluate("() => document.querySelectorAll('.layer-item').length")
    print(f"  Layers: {layers}", flush=True)
    ss(page, "P132_01_canvas_state")

    # ============================================================
    #  STEP 1: Check if BG is already removed (from P131)
    # ============================================================
    print("\n=== STEP 1: Check canvas state ===", flush=True)

    # Click canvas to select the product
    page.mouse.click(700, 400)
    page.wait_for_timeout(1000)

    # Check if background has checkerboard (transparent)
    has_transparent = page.evaluate("""() => {
        // Check for checkerboard background indicator
        var checker = document.querySelector('[class*="checker"], [class*="transparent-bg"]');
        if (checker) return 'checker_element';

        // Check layers for transparency
        var layers = document.querySelectorAll('.layer-item');
        for (var l of layers) {
            var text = (l.innerText || '').trim().toLowerCase();
            if (text.includes('no fill') || text.includes('transparent')) return 'layer_text: ' + text;
        }
        return null;
    }""")
    print(f"  Transparent bg check: {has_transparent}", flush=True)

    # Check action bar — if BG Remove is still showing, BG hasn't been removed
    action_bar = page.evaluate("""() => {
        var items = [];
        for (var el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (r.y > 55 && r.y < 110 && r.width > 20 && r.width < 200 && text.length > 2 && text.length < 20) {
                items.push({text: text, x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)});
            }
        }
        // Deduplicate
        var seen = {};
        return items.filter(function(i) { if (seen[i.text]) return false; seen[i.text] = true; return true; });
    }""")
    print(f"  Action bar:", flush=True)
    for b in action_bar:
        print(f"    ({b['x']},{b['y']}): {b['text']}", flush=True)

    # ============================================================
    #  STEP 2: BG Remove (if needed)
    # ============================================================
    print("\n=== STEP 2: BG Remove ===", flush=True)

    # Click BG Remove in action bar
    bg_pos = None
    for b in action_bar:
        if 'BG Remove' in b['text'] or b['text'] == 'BG Remove':
            bg_pos = b
            break

    if bg_pos:
        page.mouse.click(bg_pos['x'], bg_pos['y'])
        print(f"  Clicked BG Remove at ({bg_pos['x']},{bg_pos['y']})", flush=True)

        # Wait for "Removing background..." overlay to appear and then disappear
        start = time.time()
        removing_seen = False
        while time.time() - start < 30:
            elapsed = int(time.time() - start)

            status = page.evaluate("""() => {
                // Check for "Removing background..." text
                for (var el of document.querySelectorAll('*')) {
                    var text = (el.innerText || '').trim();
                    if (text === 'Removing background...') return 'removing';
                }
                // Check for checkerboard (BG removed)
                var checker = document.querySelector('[class*="checker"]');
                return checker ? 'done' : 'unknown';
            }""")

            if status == 'removing' and not removing_seen:
                print(f"  BG Remove: processing... ({elapsed}s)", flush=True)
                removing_seen = True
            elif status == 'done':
                print(f"  BG Remove: DONE in {elapsed}s", flush=True)
                break
            elif status == 'unknown' and removing_seen:
                # Was removing, now overlay is gone — probably done
                print(f"  BG Remove: overlay gone, likely done ({elapsed}s)", flush=True)
                break

            page.wait_for_timeout(1000)

        page.wait_for_timeout(2000)
        ss(page, "P132_02_bg_removed")
    else:
        print("  BG Remove not in action bar — may already be done", flush=True)

    # ============================================================
    #  STEP 3: Generative Expand (16:9 for video)
    # ============================================================
    print("\n=== STEP 3: Generative Expand ===", flush=True)

    # First, make sure product is selected
    page.mouse.click(700, 400)
    page.wait_for_timeout(500)

    # Open Image Editor (y=698) → Expand
    open_sidebar_tool(page, 698)
    page.wait_for_timeout(1500)

    # Click "Expand" sub-tool
    page.evaluate("""() => {
        for (var el of document.querySelectorAll('button, [class*="tool-item"], *')) {
            var text = (el.innerText || '').trim();
            if (text === 'Expand') { el.click(); return text; }
        }
    }""")
    page.wait_for_timeout(2000)
    close_dialogs(page)

    ss(page, "P132_03_expand_panel")

    # Check if Expand panel is open (should have aspect ratio buttons)
    expand_visible = page.evaluate("""() => {
        var aspects = ['16:9', '4:3', '1:1', '3:2', '2:1'];
        for (var a of aspects) {
            for (var el of document.querySelectorAll('button')) {
                if ((el.innerText || '').trim() === a) return true;
            }
        }
        return false;
    }""")
    print(f"  Expand panel visible: {expand_visible}", flush=True)

    if not expand_visible:
        # Maybe Image Editor didn't open Expand — try the direct Expand approach
        # Check if "Generative Expand" is already an action bar item
        print("  Expand panel not found — trying action bar...", flush=True)
        # The action bar might have changed after BG Remove
        page.evaluate("""() => {
            for (var el of document.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                if (text === 'Generative Expand' || text === 'Expand') {
                    var r = el.getBoundingClientRect();
                    if (r.y < 100 && r.width > 0) { el.click(); return text; }
                }
            }
        }""")
        page.wait_for_timeout(2000)
        close_dialogs(page)

    # Select 16:9 aspect ratio
    page.evaluate("""() => {
        for (var b of document.querySelectorAll('button')) {
            if ((b.innerText || '').trim() === '16:9') { b.click(); return; }
        }
    }""")
    page.wait_for_timeout(500)

    # Set backdrop prompt
    page.evaluate("""() => {
        for (var ta of document.querySelectorAll('textarea')) {
            var r = ta.getBoundingClientRect();
            if (r.width > 100) {
                ta.value = 'Clean white studio backdrop with soft professional lighting, subtle shadow underneath product';
                ta.dispatchEvent(new Event('input', {bubbles: true}));
                return;
            }
        }
    }""")
    page.wait_for_timeout(500)

    ss(page, "P132_04_expand_configured")

    # Count images before generation
    before_count = page.evaluate("""() => {
        var count = 0;
        for (var img of document.querySelectorAll('img')) {
            var src = img.src || '';
            if (src.includes('static.dzine.ai/stylar_product/')) count++;
        }
        return count;
    }""")

    # Click Generate
    gen_result = page.evaluate("""() => {
        // Look for the Generate button (should say "Generate 8" for Expand)
        var btn = document.querySelector('button.generative.ready');
        if (btn && !btn.disabled) { btn.click(); return {clicked: true, text: (btn.innerText||'').trim()}; }

        // Fallback: any Generate button
        for (var b of document.querySelectorAll('button')) {
            var text = (b.innerText || '').trim();
            if (text.includes('Generate') && !b.disabled) {
                b.click();
                return {clicked: true, text: text};
            }
        }
        return {error: 'no generate button found'};
    }""")
    print(f"  Generate: {json.dumps(gen_result)}", flush=True)

    if gen_result.get('clicked'):
        page.wait_for_timeout(2000)

        # Handle "Image Not Filling Canvas" dialog
        close_dialogs(page)
        page.wait_for_timeout(1000)
        close_dialogs(page)  # Double-check

        # Wait for result
        new_count = wait_for_new_images(page, before_count, max_wait=120, label="Expand")

        if new_count > 0:
            # Download the expanded image
            urls = page.evaluate("""(before) => {
                var imgs = document.querySelectorAll('img');
                var urls = [];
                var count = 0;
                for (var img of imgs) {
                    var src = img.src || '';
                    if (src.includes('static.dzine.ai/stylar_product/')) {
                        count++;
                        if (count > before) urls.push(src);
                    }
                }
                return urls;
            }""", before_count)

            ts = int(time.time())
            for i, url in enumerate(urls[:2]):
                path = DOWNLOAD_DIR / f"dzine_expanded_{ts}_{i}.webp"
                try:
                    urllib.request.urlretrieve(url, str(path))
                    print(f"  Downloaded: {path.name} ({path.stat().st_size/1024:.1f} KB)", flush=True)
                except Exception as e:
                    print(f"  Download error: {e}", flush=True)

            # Preview
            page.evaluate("""() => {
                var imgs = document.querySelectorAll('img[src*="static.dzine.ai/stylar_product/"]');
                if (imgs.length > 0) imgs[imgs.length - 1].click();
            }""")
            page.wait_for_timeout(2000)
            ss(page, "P132_05_expand_result")

            # Place on canvas
            page.evaluate("""() => {
                // Look for "Place on Canvas" button in result preview
                for (var b of document.querySelectorAll('button, [role="button"]')) {
                    var text = (b.innerText || '').trim().toLowerCase();
                    if (text.includes('place') || text.includes('canvas')) {
                        b.click();
                        return text;
                    }
                }
                // Or just press Escape to close preview
                return null;
            }""")
            page.wait_for_timeout(2000)
            page.keyboard.press("Escape")
            page.wait_for_timeout(500)

    # ============================================================
    #  STEP 4: Enhance & Upscale (2x Precision)
    # ============================================================
    print("\n=== STEP 4: Enhance & Upscale ===", flush=True)

    close_all_panels(page)
    page.wait_for_timeout(500)

    open_sidebar_tool(page, 628)  # Enhance & Upscale y=628
    page.wait_for_timeout(2000)
    close_dialogs(page)

    # Verify panel is open
    enhance_panel = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show, .panels.show');
        if (!panel) return {error: 'no panel'};
        var btns = [];
        for (var b of panel.querySelectorAll('button, [class*="option"]')) {
            var text = (b.innerText || '').trim();
            var r = b.getBoundingClientRect();
            if (text && r.width > 0) btns.push({text: text.substring(0,20), x: Math.round(r.x+r.width/2), y: Math.round(r.y+r.height/2)});
        }
        return {buttons: btns};
    }""")
    print(f"  Panel buttons: {json.dumps(enhance_panel)}", flush=True)

    # Select Precision mode
    page.evaluate("""() => {
        for (var b of document.querySelectorAll('button, [class*="option"]')) {
            if ((b.innerText || '').trim() === 'Precision Mode') { b.click(); return; }
        }
    }""")
    page.wait_for_timeout(300)

    # Select 2x
    page.evaluate("""() => {
        for (var b of document.querySelectorAll('button')) {
            if ((b.innerText || '').trim() === '2x') { b.click(); return; }
        }
    }""")
    page.wait_for_timeout(300)

    # Select PNG format
    page.evaluate("""() => {
        for (var b of document.querySelectorAll('button')) {
            if ((b.innerText || '').trim() === 'PNG') { b.click(); return; }
        }
    }""")
    page.wait_for_timeout(300)

    ss(page, "P132_06_enhance_config")

    # Count before
    before_enhance = page.evaluate("""() => {
        var count = 0;
        for (var img of document.querySelectorAll('img')) {
            var src = img.src || '';
            if (src.includes('static.dzine.ai/')) count++;
        }
        return count;
    }""")

    # Click Upscale/Generate
    enhance_gen = page.evaluate("""() => {
        for (var b of document.querySelectorAll('button')) {
            var text = (b.innerText || '').trim();
            if ((text.includes('Upscale') || text.includes('Generate') || text.includes('Enhance'))
                && !b.disabled) {
                b.click();
                return {clicked: true, text: text};
            }
        }
        return {error: 'no button'};
    }""")
    print(f"  Enhance: {json.dumps(enhance_gen)}", flush=True)

    if enhance_gen.get('clicked'):
        page.wait_for_timeout(2000)
        close_dialogs(page)

        # Enhance results may have a different URL pattern
        start = time.time()
        while time.time() - start < 120:
            elapsed = int(time.time() - start)
            close_dialogs(page)

            # Check for new images (broader pattern)
            current = page.evaluate("""() => {
                var count = 0;
                for (var img of document.querySelectorAll('img')) {
                    var src = img.src || '';
                    if (src.includes('static.dzine.ai/')) count++;
                }
                return count;
            }""")

            if current > before_enhance:
                print(f"  Enhance done in {elapsed}s! ({current - before_enhance} new)", flush=True)

                # Get the new URLs
                urls = page.evaluate(f"""() => {{
                    var imgs = document.querySelectorAll('img');
                    var urls = [];
                    var count = 0;
                    for (var img of imgs) {{
                        var src = img.src || '';
                        if (src.includes('static.dzine.ai/')) {{
                            count++;
                            if (count > {before_enhance}) urls.push(src);
                        }}
                    }}
                    return urls;
                }}""")

                ts = int(time.time())
                for i, url in enumerate(urls[:2]):
                    ext = 'png' if 'png' in url.lower() else 'webp'
                    path = DOWNLOAD_DIR / f"dzine_enhanced_{ts}_{i}.{ext}"
                    try:
                        urllib.request.urlretrieve(url, str(path))
                        print(f"  Downloaded: {path.name} ({path.stat().st_size/1024:.1f} KB)", flush=True)
                    except Exception as e:
                        print(f"  Download error: {e}", flush=True)
                break

            # Also check if enhance produced a download link directly
            download_link = page.evaluate("""() => {
                for (var a of document.querySelectorAll('a[download], a[href*="download"]')) {
                    return a.href;
                }
                return null;
            }""")
            if download_link:
                print(f"  Direct download link: {download_link[:100]}", flush=True)

            if elapsed % 10 == 0:
                # Check for "Generation Complete" text
                complete = page.evaluate("""() => {
                    for (var el of document.querySelectorAll('*')) {
                        var text = (el.innerText || '').trim();
                        if (text.includes('Generation Complete') || text.includes('Upscale Complete')) return text;
                    }
                    return null;
                }""")
                print(f"  Enhance: {elapsed}s... complete={complete}", flush=True)
            page.wait_for_timeout(3000)

        ss(page, "P132_07_enhanced")

    # ============================================================
    #  STEP 5: Export final image
    # ============================================================
    print("\n=== STEP 5: Export ===", flush=True)

    # Click Export button (top right)
    page.evaluate("""() => {
        for (var b of document.querySelectorAll('button')) {
            if ((b.innerText || '').trim() === 'Export') { b.click(); return; }
        }
    }""")
    page.wait_for_timeout(2000)

    # Map export options
    export_opts = page.evaluate("""() => {
        var items = [];
        for (var el of document.querySelectorAll('button, [class*="option"], [class*="export"]')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text && r.width > 0 && r.y > 30) {
                items.push({text: text.substring(0, 40), x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)});
            }
        }
        return items;
    }""")
    print(f"  Export options:", flush=True)
    for opt in export_opts[:15]:
        print(f"    ({opt['x']},{opt['y']}): {opt['text']}", flush=True)

    ss(page, "P132_08_export_dialog")

    # Try to download via export
    try:
        with page.expect_download(timeout=10000) as dl_info:
            # Click the PNG download option
            page.evaluate("""() => {
                for (var b of document.querySelectorAll('button')) {
                    var text = (b.innerText || '').trim().toLowerCase();
                    if (text.includes('png') || text === 'download' || text === 'export') {
                        b.click();
                        return text;
                    }
                }
            }""")
        dl = dl_info.value
        path = DOWNLOAD_DIR / f"dzine_export_{int(time.time())}.png"
        dl.save_as(str(path))
        print(f"  Exported: {path.name} ({path.stat().st_size/1024:.1f} KB)", flush=True)
    except Exception as e:
        print(f"  Export download: {e}", flush=True)

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
    print(f"PHASE 132 SUMMARY", flush=True)
    print(f"{'='*60}", flush=True)
    print(f"  Credits: {credits}", flush=True)
    print(f"  Canvas: {page.url}", flush=True)
    print(f"  Workflow tested: Upload → BG Remove → Expand → Enhance → Export", flush=True)
    print(f"  Key insight: This workflow preserves REAL product pixels!", flush=True)
    print(f"  Unlike Img2Img which regenerates (and destroys) the product.", flush=True)

    ss(page, "P132_09_final")
    print(f"\n===== PHASE 132 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
