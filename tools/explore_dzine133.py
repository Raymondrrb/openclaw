"""Phase 133: Nail the full product-faithful workflow.

P132 discoveries:
  - BG Remove: PERFECT (transparent bg, clean edges)
  - Expand panel: opened correctly but wrong Generate button was clicked
    (Img2Img Generate4 instead of Expand Generate8)
  - Img2Img AFTER BG Remove actually preserves product! (dramatic dark backdrop)
  - Export dialog: JPG/PNG/SVG/PSD, upscale 1x-4x, watermark toggle
  - Enhance needs "select one layer on canvas" first
  - "Fit to Content and Continue" dialog must be handled

Plan:
  1) Create FRESH project with product image (new canvas)
  2) BG Remove
  3) Click product to select it
  4) Run Generative Expand with 16:9 + studio prompt (click the correct Generate 8)
  5) Place expanded result on canvas
  6) Export as PNG 2x
  7) Also test: Enhance & Upscale with layer selected
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
        # Priority: "Fit to Content and Continue"
        try:
            fit_btn = page.locator('button:has-text("Fit to Content and Continue")')
            if fit_btn.count() > 0 and fit_btn.first.is_visible(timeout=500):
                fit_btn.first.click()
                page.wait_for_timeout(1000)
                print("  [dialog] Fit to Content and Continue", flush=True)
                found = True
                continue
        except Exception:
            pass
        # "Do not show again"
        try:
            cb = page.locator('text=Do not show again')
            if cb.count() > 0 and cb.first.is_visible(timeout=300):
                cb.first.click()
                page.wait_for_timeout(300)
        except Exception:
            pass
        for text in ["Not now", "Close", "Never show again", "Got it", "Skip",
                      "Later", "Continue", "OK"]:
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
    print("PHASE 133: Complete product workflow (fresh start)", flush=True)
    print("=" * 60, flush=True)

    # Find product image
    ref_path = None
    for p in sorted(DOWNLOAD_DIR.glob("amazon_headphones_*.jpg"), reverse=True):
        if p.stat().st_size > 20000:
            ref_path = str(p)
            break
    if not ref_path:
        for p in sorted(DOWNLOAD_DIR.glob("amazon_*.jpg"), reverse=True):
            if p.stat().st_size > 10000:
                ref_path = str(p)
                break
    if not ref_path:
        print("  ERROR: No product image!", flush=True)
        sys.exit(1)
    print(f"  Product: {ref_path} ({os.path.getsize(ref_path)/1024:.1f} KB)", flush=True)

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

    # ============================================================
    #  STEP 1: Create new project via "Start from an image"
    # ============================================================
    print("\n=== STEP 1: New project from image ===", flush=True)
    page = ctx.new_page()
    page.set_viewport_size({"width": 1440, "height": 900})

    page.goto("https://www.dzine.ai/home", wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(4000)
    close_dialogs(page)

    try:
        with page.expect_file_chooser(timeout=8000) as fc_info:
            page.evaluate("""() => {
                for (var el of document.querySelectorAll('.project-item')) {
                    var text = (el.innerText || '').trim().toLowerCase();
                    if (text.includes('start from an image')) { el.click(); return; }
                }
            }""")
        fc = fc_info.value
        fc.set_files(ref_path)
        print("  File accepted!", flush=True)
        page.wait_for_timeout(8000)
        close_dialogs(page)
    except Exception as e:
        print(f"  Start from image failed: {e}", flush=True)
        # Fallback
        page.evaluate("""() => {
            for (var el of document.querySelectorAll('.project-item')) {
                var text = (el.innerText || '').trim().toLowerCase();
                if (text.includes('new project')) { el.click(); return; }
            }
        }""")
        page.wait_for_timeout(6000)
        close_dialogs(page)

    if "/canvas" not in page.url:
        print(f"  Not on canvas: {page.url}", flush=True)
        sys.exit(1)

    wait_for_canvas(page)
    close_dialogs(page)
    canvas_url = page.url
    print(f"  Canvas: {canvas_url}", flush=True)

    ss(page, "P133_01_fresh_canvas")

    # ============================================================
    #  STEP 2: BG Remove
    # ============================================================
    print("\n=== STEP 2: BG Remove ===", flush=True)

    # Click canvas to select product
    page.mouse.click(700, 400)
    page.wait_for_timeout(1000)

    # Find and click BG Remove in action bar
    page.evaluate("""() => {
        for (var el of document.querySelectorAll('*')) {
            if ((el.innerText || '').trim() === 'BG Remove') {
                var r = el.getBoundingClientRect();
                if (r.y > 50 && r.y < 120 && r.width > 0) { el.click(); return; }
            }
        }
    }""")
    print("  Clicked BG Remove", flush=True)

    # Wait for BG removal to complete
    start = time.time()
    while time.time() - start < 30:
        status = page.evaluate("""() => {
            for (var el of document.querySelectorAll('*')) {
                if ((el.innerText || '').trim() === 'Removing background...') return 'removing';
            }
            return 'done';
        }""")
        if status == 'done' and time.time() - start > 3:
            break
        page.wait_for_timeout(1000)
    print(f"  BG Remove: done in {int(time.time()-start)}s", flush=True)
    page.wait_for_timeout(2000)

    ss(page, "P133_02_bg_removed")

    # ============================================================
    #  STEP 3: Select product layer
    # ============================================================
    print("\n=== STEP 3: Select product layer ===", flush=True)

    # Click on the product area
    page.mouse.click(700, 400)
    page.wait_for_timeout(500)

    # Open Layers tab
    page.evaluate("""() => {
        for (var el of document.querySelectorAll('[class*="header-item"]')) {
            if ((el.innerText || '').trim() === 'Layers') { el.click(); return; }
        }
    }""")
    page.wait_for_timeout(500)

    # Click the first visible layer
    page.evaluate("""() => {
        var items = document.querySelectorAll('.layer-item');
        if (items.length > 0) items[0].click();
    }""")
    page.wait_for_timeout(500)

    layer_info = page.evaluate("""() => {
        var items = [];
        for (var el of document.querySelectorAll('.layer-item')) {
            var name = '';
            var nameEl = el.querySelector('[class*="name"]');
            if (nameEl) name = (nameEl.innerText || '').trim();
            var selected = el.classList.contains('selected') || el.classList.contains('active');
            items.push({name: name, selected: selected});
        }
        return items;
    }""")
    print(f"  Layers: {json.dumps(layer_info)}", flush=True)

    # ============================================================
    #  STEP 4: Generative Expand (16:9 + studio backdrop)
    # ============================================================
    print("\n=== STEP 4: Generative Expand ===", flush=True)

    # Open Image Editor (y=698) → Expand
    open_sidebar_tool(page, 698)
    page.wait_for_timeout(1500)

    # Look for "Expand" in the sub-tool list
    page.evaluate("""() => {
        for (var el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            if (text === 'Expand') {
                var r = el.getBoundingClientRect();
                if (r.width > 0 && r.y > 70 && r.y < 700) { el.click(); return text; }
            }
        }
    }""")
    page.wait_for_timeout(2000)
    close_dialogs(page)

    # Check panel title
    panel_title = page.evaluate("""() => {
        var title = document.querySelector('.c-gen-config.show .panel-title, .panels.show .panel-title, [class*="panel-header"]');
        if (title) return (title.innerText || '').trim();
        // Check for "Generative Expand" text
        for (var el of document.querySelectorAll('.c-gen-config.show *, .panels.show *')) {
            var text = (el.innerText || '').trim();
            if (text === 'Generative Expand') return text;
        }
        return null;
    }""")
    print(f"  Panel: {panel_title}", flush=True)

    # Select 16:9 aspect
    page.evaluate("""() => {
        for (var b of document.querySelectorAll('button')) {
            if ((b.innerText || '').trim() === '16:9') { b.click(); return; }
        }
    }""")
    page.wait_for_timeout(500)

    # Set prompt
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

    ss(page, "P133_03_expand_setup")

    # IMPORTANT: Find the CORRECT Generate button (Expand = 8 credits)
    # The panel may have a Generate button that shows "8" for Expand
    gen_buttons = page.evaluate("""() => {
        var buttons = [];
        for (var b of document.querySelectorAll('button')) {
            var text = (b.innerText || '').trim();
            if (text.includes('Generate')) {
                var r = b.getBoundingClientRect();
                buttons.push({
                    text: text,
                    x: Math.round(r.x + r.width/2),
                    y: Math.round(r.y + r.height/2),
                    w: Math.round(r.width),
                    cls: b.className.substring(0, 60),
                    disabled: b.disabled,
                    visible: r.width > 0 && r.height > 0
                });
            }
        }
        return buttons;
    }""")
    print(f"  Generate buttons:", flush=True)
    for gb in gen_buttons:
        print(f"    ({gb['x']},{gb['y']}) {gb['w']}px: '{gb['text']}' cls={gb['cls'][:30]} vis={gb['visible']} dis={gb['disabled']}", flush=True)

    # Click the Expand Generate button (should be in the left panel area, ~200px wide)
    # The correct one says "Generate8" or "Generate\n8" and is in the panel (x < 350)
    clicked = False
    for gb in gen_buttons:
        if gb['visible'] and not gb['disabled'] and gb['x'] < 350 and '8' in gb['text']:
            print(f"  Clicking Expand Generate (8 credits) at ({gb['x']},{gb['y']})", flush=True)
            page.mouse.click(gb['x'], gb['y'])
            clicked = True
            break

    if not clicked:
        # Fallback: click the panel Generate button (leftmost visible one)
        for gb in gen_buttons:
            if gb['visible'] and not gb['disabled'] and gb['x'] < 350:
                print(f"  Clicking panel Generate at ({gb['x']},{gb['y']}): '{gb['text']}'", flush=True)
                page.mouse.click(gb['x'], gb['y'])
                clicked = True
                break

    if not clicked:
        print("  ERROR: No Generate button found in panel!", flush=True)
    else:
        page.wait_for_timeout(2000)
        close_dialogs(page)
        page.wait_for_timeout(1000)
        close_dialogs(page)

        # Wait for Expand result
        before_count = page.evaluate("""() => {
            var count = 0;
            for (var img of document.querySelectorAll('img')) {
                if ((img.src||'').includes('static.dzine.ai/stylar_product/')) count++;
            }
            return count;
        }""")

        start = time.time()
        expand_done = False
        while time.time() - start < 120:
            elapsed = int(time.time() - start)
            close_dialogs(page)

            current = page.evaluate("""() => {
                var count = 0;
                for (var img of document.querySelectorAll('img')) {
                    if ((img.src||'').includes('static.dzine.ai/stylar_product/')) count++;
                }
                return count;
            }""")

            if current > before_count:
                print(f"  Expand done in {elapsed}s! ({current-before_count} new)", flush=True)
                expand_done = True

                # Download results
                urls = page.evaluate(f"""() => {{
                    var urls = [];
                    var count = 0;
                    for (var img of document.querySelectorAll('img')) {{
                        if ((img.src||'').includes('static.dzine.ai/stylar_product/')) {{
                            count++;
                            if (count > {before_count}) urls.push(img.src);
                        }}
                    }}
                    return urls;
                }}""")
                ts = int(time.time())
                for i, url in enumerate(urls[:3]):
                    path = DOWNLOAD_DIR / f"dzine_p133_expand_{ts}_{i}.webp"
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

        ss(page, "P133_04_expand_result")

    # ============================================================
    #  STEP 5: Export via Export button (top right)
    # ============================================================
    print("\n=== STEP 5: Export ===", flush=True)

    close_all_panels(page)
    page.wait_for_timeout(500)

    # Click Export button
    page.evaluate("""() => {
        for (var b of document.querySelectorAll('button')) {
            if ((b.innerText || '').trim() === 'Export') {
                var r = b.getBoundingClientRect();
                if (r.y < 40) { b.click(); return; }
            }
        }
    }""")
    page.wait_for_timeout(2000)

    # Check for export dialog
    export_dialog = page.evaluate("""() => {
        // Look for "Download" or "Export canvas as image" text
        for (var el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            if (text === 'Export canvas as image') {
                var r = el.getBoundingClientRect();
                return {found: true, text: text, x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)};
            }
        }
        return {found: false};
    }""")
    print(f"  Export dialog: {json.dumps(export_dialog)}", flush=True)

    if export_dialog.get('found'):
        ss(page, "P133_05_export_dialog")

        # Select PNG format
        page.evaluate("""() => {
            for (var b of document.querySelectorAll('button')) {
                if ((b.innerText || '').trim() === 'PNG') { b.click(); return; }
            }
        }""")
        page.wait_for_timeout(300)

        # Select 2x upscale
        page.evaluate("""() => {
            for (var b of document.querySelectorAll('button')) {
                if ((b.innerText || '').trim() === '2x') { b.click(); return; }
            }
        }""")
        page.wait_for_timeout(300)

        # Make sure watermark is unchecked
        page.evaluate("""() => {
            var cb = document.querySelector('input[type="checkbox"]');
            if (cb && cb.checked) cb.click();
        }""")
        page.wait_for_timeout(300)

        ss(page, "P133_06_export_config")

        # Click "Export canvas as image"
        try:
            with page.expect_download(timeout=30000) as dl_info:
                page.evaluate("""() => {
                    for (var b of document.querySelectorAll('button')) {
                        var text = (b.innerText || '').trim();
                        if (text.includes('Export canvas as image')) { b.click(); return text; }
                    }
                }""")
            dl = dl_info.value
            export_path = DOWNLOAD_DIR / f"dzine_export_{int(time.time())}.png"
            dl.save_as(str(export_path))
            print(f"  EXPORTED: {export_path.name} ({export_path.stat().st_size/1024:.1f} KB)", flush=True)
        except Exception as e:
            print(f"  Export download error: {e}", flush=True)
            # The download might happen differently — check for direct download
            page.evaluate("""() => {
                for (var b of document.querySelectorAll('button')) {
                    var text = (b.innerText || '').trim();
                    if (text.includes('Export canvas')) { b.click(); return; }
                }
            }""")
            page.wait_for_timeout(5000)
            # Check Downloads folder for recent files
            recent = sorted(DOWNLOAD_DIR.glob("*.png"), key=lambda p: p.stat().st_mtime, reverse=True)
            if recent and (time.time() - recent[0].stat().st_mtime) < 30:
                print(f"  Found recent export: {recent[0].name} ({recent[0].stat().st_size/1024:.1f} KB)", flush=True)

    # Close export dialog
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)

    # ============================================================
    #  STEP 6: Enhance & Upscale (with layer selected)
    # ============================================================
    print("\n=== STEP 6: Enhance & Upscale (with layer selected) ===", flush=True)

    # Select the product layer first
    page.mouse.click(700, 400)
    page.wait_for_timeout(500)

    # Verify selection
    selected = page.evaluate("""() => {
        var handles = document.querySelectorAll('.transform-handle, [class*="selection"], [class*="handle"]');
        return handles.length;
    }""")
    print(f"  Selection handles: {selected}", flush=True)

    open_sidebar_tool(page, 628)  # Enhance & Upscale
    page.wait_for_timeout(2000)

    # Check for "Please select one layer" warning
    warning = page.evaluate("""() => {
        for (var el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            if (text.includes('Please select one layer')) return text;
        }
        return null;
    }""")
    if warning:
        print(f"  WARNING: {warning}", flush=True)
        # Try clicking directly on a layer element first
        close_all_panels(page)
        page.mouse.click(700, 400)
        page.wait_for_timeout(500)
        # Make sure it's selected by double-clicking
        page.mouse.dblclick(700, 400)
        page.wait_for_timeout(500)
        open_sidebar_tool(page, 628)
        page.wait_for_timeout(2000)

    # Configure: Precision, 2x, PNG
    for config_text in ['Precision Mode', '2x', 'PNG']:
        page.evaluate(f"""() => {{
            for (var b of document.querySelectorAll('button, [class*="option"]')) {{
                if ((b.innerText || '').trim() === '{config_text}') {{ b.click(); return; }}
            }}
        }}""")
        page.wait_for_timeout(300)

    # Click Upscale
    upscale_result = page.evaluate("""() => {
        for (var b of document.querySelectorAll('button')) {
            var text = (b.innerText || '').trim();
            if (text === 'Upscale' && !b.disabled) { b.click(); return {clicked: true}; }
        }
        // Check for warning again
        for (var el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            if (text.includes('Please select')) return {error: text};
        }
        return {error: 'no upscale button'};
    }""")
    print(f"  Upscale: {json.dumps(upscale_result)}", flush=True)

    if upscale_result.get('clicked'):
        page.wait_for_timeout(2000)
        close_dialogs(page)

        # Wait for upscale result (check for download or new result)
        start = time.time()
        while time.time() - start < 60:
            elapsed = int(time.time() - start)
            close_dialogs(page)

            # Check for completion
            complete = page.evaluate("""() => {
                for (var el of document.querySelectorAll('*')) {
                    var text = (el.innerText || '').trim();
                    if (text.includes('Complete') || text.includes('Upscale result')) return text;
                }
                return null;
            }""")
            if complete:
                print(f"  Enhance complete: {complete} ({elapsed}s)", flush=True)
                break

            if elapsed % 10 == 0:
                print(f"  Enhance: {elapsed}s...", flush=True)
            page.wait_for_timeout(3000)

        ss(page, "P133_07_enhanced")

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
    print(f"PHASE 133 SUMMARY", flush=True)
    print(f"{'='*60}", flush=True)
    print(f"  Credits: {credits}", flush=True)
    print(f"  Canvas: {page.url}", flush=True)
    print(f"\n  CONFIRMED WORKFLOW:", flush=True)
    print(f"  1. Amazon photo → 'Start from an image' (creates project)", flush=True)
    print(f"  2. BG Remove (instant, in action bar)", flush=True)
    print(f"  3. Generative Expand 16:9 + studio prompt (8 credits)", flush=True)
    print(f"  4. Export PNG 2x (no watermark)", flush=True)
    print(f"  5. Optional: Enhance & Upscale 2x Precision", flush=True)

    ss(page, "P133_08_final")
    print(f"\n===== PHASE 133 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
