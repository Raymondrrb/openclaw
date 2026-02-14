"""Phase 67: Product Background sub-tool, BG Remove toolbar, result actions detail, generation monitoring.

From P66:
- 18 categories, 73+ models in All styles, 26 in Realistic, 78 Legacy
- No canvas right-click context menu
- No keyboard shortcuts panel (? opens tooltip)

Goals:
1. Explore Product Background sub-tool in detail (scroll to it in Image Editor)
2. Test BG Remove from top toolbar (seen in P64/P65 screenshots)
3. Map result entry detail: info button, delete button, privacy badge
4. Test generation progress monitoring (poll for completion percentage)
5. Test layer deletion workflow
"""

import json
import os
import sys
import time
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


def dump_region(page, label, x_min, x_max, y_min, y_max, limit=40):
    items = page.evaluate(f"""() => {{
        var items = [];
        for (const el of document.querySelectorAll('*')) {{
            var r = el.getBoundingClientRect();
            if (r.x >= {x_min} && r.x <= {x_max} && r.y >= {y_min} && r.y <= {y_max}
                && r.width > 8 && r.height > 5 && r.width < 400
                && !['path','line','circle','g','svg','defs','rect','polygon','clippath','HTML','BODY','HEAD','SCRIPT','STYLE'].includes(el.tagName.toLowerCase())) {{
                var text = (el.innerText || '').trim();
                if (text.length > 0 && text.length < 60) {{
                    items.push({{
                        tag: el.tagName, x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        text: text.substring(0, 45),
                        classes: (el.className || '').toString().substring(0, 30),
                    }});
                }}
            }}
        }}
        var seen = new Set();
        return items.filter(function(i) {{
            var key = i.text.substring(0,15) + '|' + i.x + '|' + i.y;
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
        }}).sort(function(a,b) {{ return a.y - b.y; }});
    }}""")
    print(f"\\n  {label} ({len(items)} elements):", flush=True)
    for el in items[:limit]:
        print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> c='{el['classes'][:22]}' '{el['text'][:40]}'", flush=True)
    return items


def main():
    print("Connecting...", flush=True)
    pw = sync_playwright().start()
    browser = pw.chromium.connect_over_cdp("http://127.0.0.1:18800", timeout=15000)
    ctx = browser.contexts[0]
    page = ctx.new_page()
    page.set_viewport_size({"width": 1440, "height": 900})

    page.goto(CANVAS_URL, wait_until="domcontentloaded", timeout=30000)
    print("  Waiting 12s for full canvas load...", flush=True)
    page.wait_for_timeout(12000)
    close_dialogs(page)

    # ============================================================
    #  PART 1: PRODUCT BACKGROUND SUB-TOOL
    # ============================================================
    print("\\n" + "=" * 60, flush=True)
    print("  PART 1: PRODUCT BACKGROUND SUB-TOOL", flush=True)
    print("=" * 60, flush=True)

    # Activate Image Editor
    page.mouse.click(40, 252)
    page.wait_for_timeout(300)
    page.mouse.click(40, 698)
    page.wait_for_timeout(1500)
    close_dialogs(page)

    # Scroll down to find Product Background
    # It's at y=837 according to playbook, which is below the fold
    # Try scrolling the left panel
    panel_scroll = page.evaluate("""() => {
        // Find the scrollable container for Image Editor tools
        var containers = [];
        for (const el of document.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            var style = window.getComputedStyle(el);
            if (r.x >= 60 && r.x < 120 && r.width > 200 && r.height > 400
                && (style.overflowY === 'auto' || style.overflowY === 'scroll')) {
                containers.push({
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    scrollTop: el.scrollTop,
                    scrollHeight: el.scrollHeight,
                    classes: (el.className || '').toString().substring(0, 40),
                });
            }
        }
        return containers;
    }""")
    print(f"  Scrollable containers: {json.dumps(panel_scroll, indent=2)}", flush=True)

    # Look for Product Background or "Background" button directly
    bg_btn = page.evaluate("""() => {
        for (const btn of document.querySelectorAll('button')) {
            var text = (btn.innerText || '').trim();
            var r = btn.getBoundingClientRect();
            if (text === 'Background' && r.x > 60 && r.x < 370) {
                return {
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    visible: r.width > 0 && r.height > 0 && r.y > 0 && r.y < 900,
                };
            }
        }
        // Also check "Product Background"
        for (const btn of document.querySelectorAll('button')) {
            var text = (btn.innerText || '').trim();
            var r = btn.getBoundingClientRect();
            if (text.includes('Product') && text.includes('Background')) {
                return {
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    visible: r.width > 0 && r.height > 0 && r.y > 0 && r.y < 900,
                    text: text,
                };
            }
        }
        return null;
    }""")
    print(f"  Background button: {bg_btn}", flush=True)

    # Try scrolling the panel to reveal it
    page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            var style = window.getComputedStyle(el);
            if (r.x >= 60 && r.x < 120 && r.width > 200 && r.height > 400
                && (style.overflowY === 'auto' || style.overflowY === 'scroll')) {
                el.scrollTop += 300;
                return true;
            }
        }
        return false;
    }""")
    page.wait_for_timeout(500)

    # Check again
    bg_btn_after = page.evaluate("""() => {
        for (const btn of document.querySelectorAll('button')) {
            var text = (btn.innerText || '').trim();
            var r = btn.getBoundingClientRect();
            if (text === 'Background' && r.x > 60 && r.x < 370) {
                return {
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    visible: r.y > 0 && r.y < 900,
                };
            }
        }
        return null;
    }""")
    print(f"  Background button after scroll: {bg_btn_after}", flush=True)

    if bg_btn_after and bg_btn_after.get('visible'):
        page.mouse.click(bg_btn_after['x'] + bg_btn_after['w']//2, bg_btn_after['y'] + bg_btn_after['h']//2)
        page.wait_for_timeout(2000)
        close_dialogs(page)
        ss(page, "P67_01_product_bg")
        dump_region(page, "Product Background panel", 60, 370, 40, 900)
    else:
        # Use scrollIntoView to bring it visible
        scrolled = page.evaluate("""() => {
            for (const btn of document.querySelectorAll('button')) {
                var text = (btn.innerText || '').trim();
                if (text === 'Background') {
                    btn.scrollIntoView({behavior: 'instant', block: 'center'});
                    return true;
                }
            }
            return false;
        }""")
        print(f"  scrollIntoView: {scrolled}", flush=True)
        page.wait_for_timeout(500)

        bg_btn_scroll = page.evaluate("""() => {
            for (const btn of document.querySelectorAll('button')) {
                var text = (btn.innerText || '').trim();
                var r = btn.getBoundingClientRect();
                if (text === 'Background' && r.x > 60 && r.x < 370 && r.y > 0 && r.y < 900) {
                    btn.click();
                    return {x: Math.round(r.x), y: Math.round(r.y)};
                }
            }
            return null;
        }""")
        print(f"  Background clicked after scrollIntoView: {bg_btn_scroll}", flush=True)
        page.wait_for_timeout(2000)
        close_dialogs(page)
        ss(page, "P67_01_product_bg")
        dump_region(page, "Product Background panel", 60, 400, 40, 900)

    # Go back
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)

    # ============================================================
    #  PART 2: TOP TOOLBAR — BG REMOVE & OTHER QUICK ACTIONS
    # ============================================================
    print("\\n" + "=" * 60, flush=True)
    print("  PART 2: TOP TOOLBAR — BG REMOVE", flush=True)
    print("=" * 60, flush=True)

    # First select a layer
    page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text === 'Layers' && r.x > 1200 && r.y < 60) {
                el.click(); return true;
            }
        }
        return false;
    }""")
    page.wait_for_timeout(500)

    # Click Layer 4 (first layer)
    page.evaluate("""() => {
        for (const btn of document.querySelectorAll('button.layer-item')) {
            var text = (btn.innerText || '').trim();
            if (text.includes('Layer 4')) {
                btn.click(); return true;
            }
        }
        return false;
    }""")
    page.wait_for_timeout(1000)

    # Now map the top toolbar in detail
    toolbar = page.evaluate("""() => {
        var items = [];
        for (const el of document.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            var text = (el.innerText || '').trim();
            var classes = (el.className || '').toString();
            // Top bar area: y < 60, various x positions for tools
            if (r.y > 30 && r.y < 60 && r.x > 180 && r.x < 600
                && r.width > 10 && r.height > 10
                && text.length > 0 && text.length < 30) {
                items.push({
                    text: text,
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    tag: el.tagName,
                    classes: classes.substring(0, 40),
                });
            }
        }
        var seen = new Set();
        return items.filter(function(i) {
            var key = i.text + '|' + i.x;
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
        }).sort(function(a,b) { return a.x - b.x; });
    }""")
    print(f"  Top toolbar items ({len(toolbar)}):", flush=True)
    for t in toolbar:
        print(f"    ({t['x']},{t['y']}) {t['w']}x{t['h']} <{t['tag']}> c='{t['classes'][:22]}' '{t['text']}'", flush=True)

    ss(page, "P67_02_toolbar_with_layer")

    # Look for BG Remove button
    bg_remove = page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if ((text === 'BG Remove' || text === 'Bg Remove' || text.includes('Remove'))
                && r.y < 60 && r.x > 180) {
                return {
                    text: text,
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    tag: el.tagName,
                };
            }
        }
        return null;
    }""")
    print(f"  BG Remove button: {bg_remove}", flush=True)

    if bg_remove:
        page.mouse.click(bg_remove['x'] + bg_remove['w']//2, bg_remove['y'] + bg_remove['h']//2)
        page.wait_for_timeout(2000)
        close_dialogs(page)
        ss(page, "P67_03_bg_remove")
        dump_region(page, "BG Remove panel", 60, 400, 40, 900)

    # ============================================================
    #  PART 3: RESULT ENTRY DETAIL
    # ============================================================
    print("\\n" + "=" * 60, flush=True)
    print("  PART 3: RESULT ENTRY DETAIL", flush=True)
    print("=" * 60, flush=True)

    # Switch to Results tab
    page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text === 'Results' && r.x > 1050 && r.y < 60) {
                el.click(); return true;
            }
        }
        return false;
    }""")
    page.wait_for_timeout(1000)

    # Map the first result entry header
    result_header = page.evaluate("""() => {
        var items = [];
        for (const el of document.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            var text = (el.innerText || '').trim();
            var classes = (el.className || '').toString();
            // Result header area: x > 1060, y between 70-120
            if (r.x > 1060 && r.y > 60 && r.y < 130
                && r.width > 8 && r.height > 5
                && (text.length > 0 || classes.includes('ico') || classes.includes('icon'))) {
                items.push({
                    text: text.substring(0, 30),
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    tag: el.tagName,
                    classes: classes.substring(0, 40),
                    clickable: el.tagName === 'BUTTON' || el.tagName === 'A',
                });
            }
        }
        var seen = new Set();
        return items.filter(function(i) {
            var key = i.text.substring(0,10) + '|' + i.x + '|' + i.y;
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
        }).sort(function(a,b) { return a.x - b.x; });
    }""")
    print(f"  Result entry header ({len(result_header)}):", flush=True)
    for r in result_header:
        print(f"    ({r['x']},{r['y']}) {r['w']}x{r['h']} <{r['tag']}> click={r['clickable']} c='{r['classes'][:25]}' '{r['text']}'", flush=True)

    # Click the info button (i icon) on first result
    info = page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            var classes = (el.className || '').toString();
            var r = el.getBoundingClientRect();
            if (classes.includes('ico-info') && r.x > 1060 && r.y > 60 && r.y < 130) {
                el.click();
                return {x: Math.round(r.x), y: Math.round(r.y)};
            }
        }
        // Try any button/clickable near the info icon area
        for (const el of document.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            if (r.x > 1330 && r.x < 1370 && r.y > 60 && r.y < 110
                && r.width > 10 && r.width < 30 && r.height > 10 && r.height < 30) {
                el.click();
                return {x: Math.round(r.x), y: Math.round(r.y), tag: el.tagName,
                        classes: (el.className || '').toString().substring(0, 30)};
            }
        }
        return null;
    }""")
    print(f"  Info button clicked: {info}", flush=True)
    page.wait_for_timeout(1000)

    # Check for any info popup/panel
    info_popup = page.evaluate("""() => {
        var items = [];
        for (const el of document.querySelectorAll('*')) {
            var style = window.getComputedStyle(el);
            var z = parseInt(style.zIndex) || 0;
            var r = el.getBoundingClientRect();
            var text = (el.innerText || '').trim();
            if (z > 200 && r.width > 100 && r.height > 50) {
                items.push({
                    text: text.substring(0, 100),
                    z: z, x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    classes: (el.className || '').toString().substring(0, 40),
                });
            }
        }
        return items.sort(function(a,b) { return b.z - a.z; }).slice(0, 5);
    }""")
    print(f"  Info popup ({len(info_popup)}):", flush=True)
    for p in info_popup:
        print(f"    z={p['z']} ({p['x']},{p['y']}) {p['w']}x{p['h']} c='{p['classes'][:25]}' '{p['text'][:60]}'", flush=True)

    ss(page, "P67_04_result_info")

    page.keyboard.press("Escape")
    page.wait_for_timeout(300)

    # ============================================================
    #  PART 4: RESULT IMAGE URL EXTRACTION
    # ============================================================
    print("\\n" + "=" * 60, flush=True)
    print("  PART 4: RESULT IMAGE URL EXTRACTION", flush=True)
    print("=" * 60, flush=True)

    # Get all result images with their URLs
    result_images = page.evaluate("""() => {
        var items = [];
        for (const img of document.querySelectorAll('img')) {
            var src = img.src || '';
            var r = img.getBoundingClientRect();
            if (src.includes('static.dzine.ai') && r.x > 1060 && r.width > 30) {
                items.push({
                    src: src,
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                });
            }
        }
        return items.sort(function(a,b) { return a.y - b.y; });
    }""")
    print(f"  Result images ({len(result_images)}):", flush=True)
    for img in result_images[:10]:
        # Just show last 50 chars of URL
        short_src = img['src'][-60:] if len(img['src']) > 60 else img['src']
        print(f"    ({img['x']},{img['y']}) {img['w']}x{img['h']} ...{short_src}", flush=True)

    # Extract full URLs for first 4 results
    if result_images:
        print(f"\\n  Full URLs:", flush=True)
        for img in result_images[:4]:
            print(f"    {img['src']}", flush=True)

    # ============================================================
    #  PART 5: LAYER DELETE WORKFLOW
    # ============================================================
    print("\\n" + "=" * 60, flush=True)
    print("  PART 5: LAYER DELETE WORKFLOW", flush=True)
    print("=" * 60, flush=True)

    # Switch to Layers
    page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text === 'Layers' && r.x > 1200 && r.y < 60) {
                el.click(); return true;
            }
        }
        return false;
    }""")
    page.wait_for_timeout(500)

    # Count layers
    layer_count = page.evaluate("""() => {
        return document.querySelectorAll('button.layer-item').length;
    }""")
    print(f"  Current layer count: {layer_count}", flush=True)

    # Select Layer 2 (text layer)
    page.evaluate("""() => {
        for (const btn of document.querySelectorAll('button.layer-item')) {
            var text = (btn.innerText || '').trim();
            if (text.includes('Layer 2')) {
                btn.click(); return true;
            }
        }
        return false;
    }""")
    page.wait_for_timeout(500)

    ss(page, "P67_05_layer_selected")

    # Try pressing Delete key to see what happens
    # Don't actually delete — just check if a confirmation dialog appears
    page.keyboard.press("Delete")
    page.wait_for_timeout(1000)

    # Check for confirmation dialog
    confirm = page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            var style = window.getComputedStyle(el);
            var z = parseInt(style.zIndex) || 0;
            var r = el.getBoundingClientRect();
            var text = (el.innerText || '').trim();
            if (z > 500 && r.width > 100 && r.height > 50
                && text.length > 5 && (text.includes('delete') || text.includes('Delete')
                || text.includes('confirm') || text.includes('remove'))) {
                return {text: text.substring(0, 100), z: z};
            }
        }
        return null;
    }""")
    print(f"  Delete confirmation: {confirm}", flush=True)

    # Check if layer was actually deleted
    layer_count_after = page.evaluate("""() => {
        return document.querySelectorAll('button.layer-item').length;
    }""")
    print(f"  Layer count after Delete: {layer_count_after}", flush=True)

    if layer_count_after < layer_count:
        print("  Layer was deleted! (no confirmation dialog)", flush=True)
        # Undo with Ctrl+Z
        page.keyboard.press("Meta+z")
        page.wait_for_timeout(1000)
        layer_count_undo = page.evaluate("""() => {
            return document.querySelectorAll('button.layer-item').length;
        }""")
        print(f"  Layer count after Ctrl+Z undo: {layer_count_undo}", flush=True)

    ss(page, "P67_06_after_delete")

    # Check for keyboard shortcut via Backspace too
    print("\\n  Testing Backspace on selected layer...", flush=True)

    # Reselect a layer first (in case it was deleted)
    page.evaluate("""() => {
        for (const btn of document.querySelectorAll('button.layer-item')) {
            var text = (btn.innerText || '').trim();
            if (text.includes('Layer')) {
                btn.click(); return true;
            }
        }
        return false;
    }""")
    page.wait_for_timeout(500)

    layer_count_pre = page.evaluate("""() => {
        return document.querySelectorAll('button.layer-item').length;
    }""")
    page.keyboard.press("Backspace")
    page.wait_for_timeout(1000)
    layer_count_post = page.evaluate("""() => {
        return document.querySelectorAll('button.layer-item').length;
    }""")
    print(f"  Backspace: {layer_count_pre} -> {layer_count_post}", flush=True)

    if layer_count_post < layer_count_pre:
        # Undo
        page.keyboard.press("Meta+z")
        page.wait_for_timeout(1000)

    ss(page, "P67_07_final")

    print(f"\\n\\n===== PHASE 67 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
