"""Phase 27: Export dialog, Expression Edit, Enhance & Upscale, variant selectors.

Goals:
1. Place an image on canvas, then click Export to see the export dialog
2. Click variant "2" button on CC result to switch displayed image
3. Use Enhance & Upscale on a canvas image
4. Access Expression Edit via results panel action button
5. Test right-click context menu on canvas images
6. Explore full-resolution image URL extraction (vs thumbnails)
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

def ss(page, name):
    page.screenshot(path=str(SS_DIR / f"{name}.png"))
    print(f"  SS: {name}", flush=True)

def close_dialogs(page):
    for _ in range(6):
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


def main():
    print("Connecting...", flush=True)
    pw = sync_playwright().start()
    browser = pw.chromium.connect_over_cdp("http://127.0.0.1:18800", timeout=15000)
    ctx = browser.contexts[0]
    page = ctx.new_page()
    page.set_viewport_size({"width": 1440, "height": 900})

    page.goto(CANVAS_URL, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(3000)
    close_dialogs(page)

    # ============================================================
    #  STEP 1: Place first result image on canvas
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  STEP 1: PLACE IMAGE ON CANVAS", flush=True)
    print("=" * 60, flush=True)

    # Switch to Results tab
    page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            if ((el.innerText || '').trim() === 'Results' && el.getBoundingClientRect().x > 1050) {
                el.click(); return true;
            }
        }
        return false;
    }""")
    page.wait_for_timeout(1000)

    # Find first result image
    first_img = page.evaluate("""() => {
        for (const img of document.querySelectorAll('img')) {
            const src = img.src || '';
            const r = img.getBoundingClientRect();
            if (src.includes('static.dzine.ai/stylar_product/p/') && r.x > 550 && r.width > 50) {
                return {src: src, x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)};
            }
        }
        return null;
    }""")

    if first_img:
        print(f"  Clicking result image at ({first_img['x']}, {first_img['y']})", flush=True)
        print(f"  URL: {first_img['src'][:100]}", flush=True)
        page.mouse.click(first_img['x'], first_img['y'])
        page.wait_for_timeout(2000)
        close_dialogs(page)
        ss(page, "P27_01_image_on_canvas")

        # Verify canvas has image
        has_canvas = page.evaluate("""() => {
            for (const img of document.querySelectorAll('img')) {
                const r = img.getBoundingClientRect();
                if (r.x > 60 && r.x < 550 && r.width > 100 &&
                    img.src.includes('static.dzine.ai/stylar_product/p/')) {
                    return true;
                }
            }
            return false;
        }""")
        print(f"  Canvas has placed image: {has_canvas}", flush=True)
    else:
        print("  No result images found!", flush=True)

    # ============================================================
    #  STEP 2: CLICK EXPORT WITH CANVAS LAYER
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  STEP 2: EXPORT DIALOG", flush=True)
    print("=" * 60, flush=True)

    # First click on the canvas image to select it as a layer
    page.mouse.click(700, 400)  # Center of canvas
    page.wait_for_timeout(1000)

    # Click Export
    page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            const text = (el.innerText || '').trim();
            const r = el.getBoundingClientRect();
            if (text === 'Export' && r.y < 50) {
                el.click(); return true;
            }
        }
        return false;
    }""")
    page.wait_for_timeout(2000)
    close_dialogs(page)

    ss(page, "P27_02_export_dialog")

    # Map whatever appeared (dialog, dropdown, etc.)
    export_els = page.evaluate("""() => {
        const items = [];
        // Look for any new overlay/dialog/dropdown
        for (const el of document.querySelectorAll('*')) {
            const r = el.getBoundingClientRect();
            const text = (el.innerText || '').trim();
            const style = window.getComputedStyle(el);
            const zIndex = parseInt(style.zIndex) || 0;
            if (text && text.length > 0 && text.length < 60
                && !text.includes('\\n')
                && r.width > 15 && r.height > 8
                && (zIndex > 10 || r.y < 100)) {
                items.push({
                    text: text,
                    tag: el.tagName,
                    x: Math.round(r.x),
                    y: Math.round(r.y),
                    w: Math.round(r.width),
                    h: Math.round(r.height),
                    z: zIndex,
                });
            }
        }
        const seen = new Set();
        return items.filter(i => {
            const key = i.text + '|' + Math.round(i.y / 5);
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
        }).sort((a, b) => b.z - a.z || a.y - b.y);
    }""")

    print(f"\n  High z-index / top elements ({len(export_els)}):", flush=True)
    for el in export_els[:30]:
        print(f"    z={el['z']} ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> '{el['text']}'", flush=True)

    # Try clicking "Download" or "PNG" if visible
    download_clicked = page.evaluate("""() => {
        for (const el of document.querySelectorAll('button, a, div')) {
            const text = (el.innerText || '').trim();
            if ((text === 'Download' || text === 'PNG' || text === 'Export as PNG')
                && el.getBoundingClientRect().width > 30) {
                el.click(); return text;
            }
        }
        return null;
    }""")
    print(f"  Download action: {download_clicked}", flush=True)
    if download_clicked:
        page.wait_for_timeout(3000)
        ss(page, "P27_02b_after_download")

    # Escape any open dialog
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)

    # ============================================================
    #  STEP 3: CC VARIANT SELECTOR (click "2" on first CC result)
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  STEP 3: VARIANT SELECTORS", flush=True)
    print("=" * 60, flush=True)

    # Switch to Results tab
    page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            if ((el.innerText || '').trim() === 'Results' && el.getBoundingClientRect().x > 1050) {
                el.click(); return true;
            }
        }
        return false;
    }""")
    page.wait_for_timeout(1000)

    # Get CC result thumbnail images before variant switch
    cc_thumbs_before = page.evaluate("""() => {
        const imgs = [];
        for (const img of document.querySelectorAll('img')) {
            const src = img.src || '';
            const r = img.getBoundingClientRect();
            if (src.includes('static.dzine.ai/stylar_product/p/')
                && r.x > 1050 && r.y > 100 && r.y < 250 && r.width > 100) {
                imgs.push({src: src.substring(0, 100), x: Math.round(r.x), y: Math.round(r.y)});
            }
        }
        return imgs;
    }""")
    print(f"\n  CC thumbnails before: {len(cc_thumbs_before)}", flush=True)
    for t in cc_thumbs_before:
        print(f"    ({t['x']},{t['y']}) {t['src']}", flush=True)

    # Find and click the "2" button near "Variation" action (first row)
    # Variation label is at y=251, "2" button at (1349, 251)
    variant2 = page.evaluate("""() => {
        const buttons = [];
        for (const btn of document.querySelectorAll('button')) {
            const text = (btn.innerText || '').trim();
            const r = btn.getBoundingClientRect();
            if (text === '2' && r.x > 1300 && r.x < 1400
                && r.y > 240 && r.y < 260 && r.width > 50) {
                return {x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)};
            }
        }
        return null;
    }""")

    if variant2:
        print(f"\n  Clicking variant '2' at ({variant2['x']},{variant2['y']})", flush=True)
        page.mouse.click(variant2['x'], variant2['y'])
        page.wait_for_timeout(2000)

        ss(page, "P27_03_variant2_clicked")

        # Check what happened (did it switch to variation mode?)
        panel_state = page.evaluate("""() => {
            const items = [];
            for (const el of document.querySelectorAll('*')) {
                const r = el.getBoundingClientRect();
                const text = (el.innerText || '').trim();
                if (r.x > 60 && r.x < 400 && r.y > 50 && r.y < 900
                    && r.width > 15 && r.width < 350 && text
                    && text.length > 0 && text.length < 60 && !text.includes('\\n')) {
                    items.push({
                        text: text,
                        tag: el.tagName,
                        x: Math.round(r.x),
                        y: Math.round(r.y),
                    });
                }
            }
            const seen = new Set();
            return items.filter(i => {
                const key = i.text + '|' + Math.round(i.y / 3);
                if (seen.has(key)) return false;
                seen.add(key);
                return true;
            }).sort((a, b) => a.y - b.y).slice(0, 10);
        }""")

        print(f"  Left panel state after click:", flush=True)
        for el in panel_state:
            print(f"    ({el['x']},{el['y']}) <{el['tag']}> '{el['text']}'", flush=True)
    else:
        print("  Variant '2' button not found", flush=True)

    # ============================================================
    #  STEP 4: EXPRESSION EDIT VIA RESULT ACTION
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  STEP 4: EXPRESSION EDIT", flush=True)
    print("=" * 60, flush=True)

    # Make sure Results tab is active
    page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            if ((el.innerText || '').trim() === 'Results' && el.getBoundingClientRect().x > 1050) {
                el.click(); return true;
            }
        }
        return false;
    }""")
    page.wait_for_timeout(500)

    # Click "1" next to Expression Edit (at x=1274, y=467)
    expr1 = page.evaluate("""() => {
        // Find "Expression Edit" label, then find the "1" button at same y
        for (const div of document.querySelectorAll('div')) {
            const text = (div.innerText || '').trim();
            const r = div.getBoundingClientRect();
            if (text === 'Expression Edit' && r.x > 1100 && r.x < 1200 && r.y > 450 && r.y < 490) {
                // Found the label, now find the "1" button near same y
                for (const btn of document.querySelectorAll('button')) {
                    const bt = (btn.innerText || '').trim();
                    const br = btn.getBoundingClientRect();
                    if (bt === '1' && br.x > 1250 && Math.abs(br.y - r.y) < 20) {
                        btn.click();
                        return {x: Math.round(br.x), y: Math.round(br.y), labelY: Math.round(r.y)};
                    }
                }
            }
        }
        return null;
    }""")

    print(f"\n  Expression Edit '1' clicked: {expr1}", flush=True)

    if expr1:
        page.wait_for_timeout(3000)
        close_dialogs(page)

        ss(page, "P27_04_expression_edit_panel")

        # Map what opened in left panel
        expr_panel = page.evaluate("""() => {
            const items = [];
            for (const el of document.querySelectorAll('*')) {
                const r = el.getBoundingClientRect();
                const text = (el.innerText || '').trim();
                if (r.x > 60 && r.x < 400 && r.y > 50 && r.y < 900
                    && r.width > 15 && r.width < 350 && text
                    && text.length > 0 && text.length < 80 && !text.includes('\\n')) {
                    items.push({
                        text: text,
                        tag: el.tagName,
                        x: Math.round(r.x),
                        y: Math.round(r.y),
                        w: Math.round(r.width),
                    });
                }
            }
            const seen = new Set();
            return items.filter(i => {
                const key = i.text + '|' + Math.round(i.y / 3);
                if (seen.has(key)) return false;
                seen.add(key);
                return true;
            }).sort((a, b) => a.y - b.y);
        }""")

        print(f"\n  Expression Edit panel ({len(expr_panel)}):", flush=True)
        for el in expr_panel[:25]:
            print(f"    ({el['x']},{el['y']}) w={el['w']} <{el['tag']}> '{el['text']}'", flush=True)

    # ============================================================
    #  STEP 5: ENHANCE & UPSCALE ON CANVAS IMAGE
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  STEP 5: ENHANCE & UPSCALE", flush=True)
    print("=" * 60, flush=True)

    # First, place an image on canvas if not already there
    # Click on canvas image to select it
    page.mouse.click(700, 400)
    page.wait_for_timeout(500)

    # Click Enhance & Upscale in sidebar
    page.mouse.click(40, 627)
    page.wait_for_timeout(2000)
    close_dialogs(page)

    ss(page, "P27_05_enhance_panel")

    # Check if "Please select one layer" message is shown
    needs_layer = page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            if ((el.innerText || '').includes('Please select one layer')) {
                return true;
            }
        }
        return false;
    }""")
    print(f"\n  Needs layer selection: {needs_layer}", flush=True)

    # Map enhance panel
    enhance = page.evaluate("""() => {
        const items = [];
        for (const el of document.querySelectorAll('*')) {
            const r = el.getBoundingClientRect();
            const text = (el.innerText || '').trim();
            if (r.x > 60 && r.x < 400 && r.y > 50 && r.y < 900
                && r.width > 15 && r.width < 350 && text
                && text.length > 0 && text.length < 60 && !text.includes('\\n')) {
                items.push({
                    text: text,
                    tag: el.tagName,
                    x: Math.round(r.x),
                    y: Math.round(r.y),
                    w: Math.round(r.width),
                });
            }
        }
        const seen = new Set();
        return items.filter(i => {
            const key = i.text + '|' + Math.round(i.y / 3);
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
        }).sort((a, b) => a.y - b.y);
    }""")

    print(f"\n  Enhance panel ({len(enhance)}):", flush=True)
    for el in enhance[:20]:
        print(f"    ({el['x']},{el['y']}) w={el['w']} <{el['tag']}> '{el['text']}'", flush=True)

    # ============================================================
    #  STEP 6: RIGHT-CLICK CONTEXT MENU ON CANVAS
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  STEP 6: CANVAS RIGHT-CLICK MENU", flush=True)
    print("=" * 60, flush=True)

    page.mouse.click(700, 400, button="right")
    page.wait_for_timeout(1500)

    ss(page, "P27_06_right_click")

    context_menu = page.evaluate("""() => {
        const items = [];
        for (const el of document.querySelectorAll('*')) {
            const r = el.getBoundingClientRect();
            const text = (el.innerText || '').trim();
            const style = window.getComputedStyle(el);
            const zIndex = parseInt(style.zIndex) || 0;
            if (zIndex > 50 && text && text.length > 0 && text.length < 60
                && !text.includes('\\n') && r.width > 20 && r.height > 10) {
                items.push({
                    text: text,
                    tag: el.tagName,
                    x: Math.round(r.x),
                    y: Math.round(r.y),
                    w: Math.round(r.width),
                    z: zIndex,
                });
            }
        }
        const seen = new Set();
        return items.filter(i => {
            const key = i.text + '|' + Math.round(i.y / 3);
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
        }).sort((a, b) => a.y - b.y);
    }""")

    print(f"\n  Context menu items ({len(context_menu)}):", flush=True)
    for el in context_menu[:20]:
        print(f"    z={el['z']} ({el['x']},{el['y']}) w={el['w']} <{el['tag']}> '{el['text']}'", flush=True)

    # Close context menu
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)

    # ============================================================
    #  STEP 7: FULL-RESOLUTION URLs (check img srcset / data-src)
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  STEP 7: FULL-RES URL ANALYSIS", flush=True)
    print("=" * 60, flush=True)

    url_analysis = page.evaluate("""() => {
        const results = [];
        for (const img of document.querySelectorAll('img')) {
            const src = img.src || '';
            if (src.includes('static.dzine.ai/stylar_product/p/')) {
                results.push({
                    src: src,
                    srcset: img.srcset || '',
                    dataSrc: img.getAttribute('data-src') || '',
                    naturalW: img.naturalWidth,
                    naturalH: img.naturalHeight,
                    displayW: Math.round(img.getBoundingClientRect().width),
                    displayH: Math.round(img.getBoundingClientRect().height),
                    loading: img.loading || '',
                });
            }
        }
        return results.slice(0, 5);
    }""")

    print(f"\n  Image analysis (first 5):", flush=True)
    for ua in url_analysis:
        print(f"    natural: {ua['naturalW']}x{ua['naturalH']}  display: {ua['displayW']}x{ua['displayH']}", flush=True)
        print(f"    src: {ua['src'][:120]}", flush=True)
        if ua['srcset']:
            print(f"    srcset: {ua['srcset'][:120]}", flush=True)
        if ua['dataSrc']:
            print(f"    data-src: {ua['dataSrc'][:120]}", flush=True)

    # Download first image to check actual resolution
    if url_analysis:
        test_url = url_analysis[0]['src']
        dest = SS_DIR / "resolution_test.webp"
        try:
            req = urllib.request.Request(test_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = resp.read()
                content_type = resp.headers.get('Content-Type', 'unknown')
            dest.write_bytes(data)
            print(f"\n  Downloaded: {len(data)} bytes, Content-Type: {content_type}", flush=True)
        except Exception as e:
            print(f"\n  Download failed: {e}", flush=True)

    ss(page, "P27_07_final")
    print(f"\n\n===== PHASE 27 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
