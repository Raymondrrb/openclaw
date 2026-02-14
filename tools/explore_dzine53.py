"""Phase 53: Advanced section (seed, negative prompt), Variation, Face Swap from results.

From P52:
- Txt2Img active panel fully mapped (Face Match, Color Match, Generation Mode, Advanced)
- Advanced section clicked but content not visible (may need scroll or model-specific)
- Face Match file chooser CONFIRMED working
- Insert Character workflow mapped (28 credits, Lasso/Brush/Auto mask)

Goals:
1. Open Txt2Img, click Advanced, scroll to see expanded content (seed, negative prompt)
2. Click Variation "1" button from results → explore variation panel
3. Click Face Swap "1" button from results → explore face swap panel
4. Check the Txt2Img "more" aspect ratios (... button) like we did for CC
5. Test Product Background from Image Editor
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


def dump_panel(page, label, x_min, x_max, y_min, y_max, limit=40):
    """Dump unique text elements in a region."""
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
                        tag: el.tagName,
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        text: text.substring(0, 45),
                        classes: (el.className || '').toString().substring(0, 35),
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
    print(f"\n  {label} ({len(items)} unique):", flush=True)
    for el in items[:limit]:
        print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> c='{el['classes'][:25]}' '{el['text'][:40]}'", flush=True)
    return items


def main():
    print("Connecting...", flush=True)
    pw = sync_playwright().start()
    browser = pw.chromium.connect_over_cdp("http://127.0.0.1:18800", timeout=15000)
    ctx = browser.contexts[0]
    page = ctx.new_page()
    page.set_viewport_size({"width": 1440, "height": 900})

    page.goto(CANVAS_URL, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(5000)
    close_dialogs(page)

    # ============================================================
    #  PART 1: TXT2IMG ADVANCED SECTION
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 1: ADVANCED SECTION", flush=True)
    print("=" * 60, flush=True)

    # Panel toggle to activate Txt2Img
    page.mouse.click(40, 306)  # Character sidebar
    page.wait_for_timeout(500)
    page.mouse.click(40, 197)  # Txt2Img sidebar
    page.wait_for_timeout(2000)
    close_dialogs(page)

    # Turn OFF Face Match if it's on (from previous session)
    fm_toggle = page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text === 'Face Match' && r.x > 60 && r.x < 360 && r.y > 0 && r.y < 900 && r.width > 0) {
                var parent = el;
                for (var p = 0; p < 5 && parent; p++) {
                    var switches = parent.querySelectorAll('button');
                    for (var i = 0; i < switches.length; i++) {
                        var sw = switches[i];
                        var sr = sw.getBoundingClientRect();
                        var classes = (sw.className || '').toString();
                        if (classes.includes('switch') && sr.width > 25 && sr.width < 55 && Math.abs(sr.y - r.y) < 30) {
                            var bg = window.getComputedStyle(sw).backgroundColor;
                            return {x: Math.round(sr.x + sr.width/2), y: Math.round(sr.y + sr.height/2), bg: bg};
                        }
                    }
                    parent = parent.parentElement;
                }
            }
        }
        return null;
    }""")
    if fm_toggle and 'rgb(255' in fm_toggle.get('bg', ''):
        print(f"  Face Match is ON (yellow), turning OFF...", flush=True)
        page.mouse.click(fm_toggle['x'], fm_toggle['y'])
        page.wait_for_timeout(1000)

    # Click Advanced to expand
    adv_clicked = page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text === 'Advanced' && r.x > 60 && r.x < 360 && r.y > 0 && r.y < 900 && r.width > 80) {
                el.click();
                return {x: Math.round(r.x), y: Math.round(r.y)};
            }
        }
        return null;
    }""")
    print(f"  Advanced clicked: {adv_clicked}", flush=True)
    page.wait_for_timeout(1500)

    # Scroll the panel down to see Advanced content
    # Try scrolling the panel via JS
    scrolled = page.evaluate("""() => {
        // Find the main panel container and scroll it
        for (const el of document.querySelectorAll('.gen-config-content, .config-content, .panel-content')) {
            if (el.scrollHeight > el.clientHeight) {
                el.scrollTop = el.scrollHeight;
                return {tag: el.tagName, cls: (el.className || '').substring(0, 40), scrollH: el.scrollHeight};
            }
        }
        // Try any scrollable in the left panel area
        for (const el of document.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            if (r.x > 60 && r.x < 120 && r.width > 200 && r.width < 350
                && r.height > 200 && el.scrollHeight > el.clientHeight + 10) {
                el.scrollTop = el.scrollHeight;
                return {tag: el.tagName, cls: (el.className || '').substring(0, 40), scrollH: el.scrollHeight, clientH: el.clientHeight};
            }
        }
        return null;
    }""")
    print(f"  Scrolled: {scrolled}", flush=True)
    page.wait_for_timeout(500)

    # Also try mouse wheel
    page.mouse.move(200, 600)
    for _ in range(5):
        page.mouse.wheel(0, 200)
        page.wait_for_timeout(200)

    ss(page, "P53_01_advanced")

    # Dump the bottom area of the panel
    dump_panel(page, "Panel bottom (after Advanced)", 60, 370, 500, 900)

    # Look for seed input, negative prompt
    all_inputs = page.evaluate("""() => {
        var items = [];
        for (const el of document.querySelectorAll('input, textarea')) {
            var r = el.getBoundingClientRect();
            if (r.x > 60 && r.x < 360 && r.width > 30 && r.y > 0 && r.y < 900) {
                items.push({
                    tag: el.tagName,
                    type: el.type || '',
                    placeholder: (el.placeholder || '').substring(0, 40),
                    value: (el.value || '').substring(0, 30),
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    name: el.name || '',
                });
            }
        }
        return items.sort(function(a,b) { return a.y - b.y; });
    }""")
    print(f"\n  All inputs ({len(all_inputs)}):", flush=True)
    for inp in all_inputs:
        print(f"    ({inp['x']},{inp['y']}) {inp['w']}x{inp['h']} <{inp['tag']}> type={inp['type']} name={inp['name']} ph='{inp['placeholder'][:30]}' val='{inp['value'][:20]}'", flush=True)

    # Check: is Advanced actually expanded? Look for expand/collapse arrow
    adv_state = page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text === 'Advanced' && r.x > 60 && r.x < 360 && r.y > 0 && r.y < 900) {
                var parent = el.parentElement;
                // Check if the container has expanded height
                var pr = parent ? parent.getBoundingClientRect() : null;
                // Also check for an arrow/chevron nearby
                var nextSibling = el.nextElementSibling;
                var ns = nextSibling ? {
                    tag: nextSibling.tagName,
                    classes: (nextSibling.className || '').toString().substring(0, 40),
                    h: Math.round(nextSibling.getBoundingClientRect().height),
                } : null;
                return {
                    y: Math.round(r.y),
                    parentH: pr ? Math.round(pr.height) : 0,
                    nextSibling: ns,
                };
            }
        }
        return null;
    }""")
    print(f"\n  Advanced state: {adv_state}", flush=True)

    # Try clicking Advanced differently — maybe it's a button
    adv_btn = page.evaluate("""() => {
        for (const btn of document.querySelectorAll('button, div[class*="advanced"], div[class*="collapse"]')) {
            var text = (btn.innerText || '').trim();
            var r = btn.getBoundingClientRect();
            if (text.includes('Advanced') && r.x > 60 && r.x < 360 && r.y > 0 && r.y < 900 && r.width > 80) {
                return {
                    tag: btn.tagName,
                    classes: (btn.className || '').toString().substring(0, 60),
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    hasArrow: btn.querySelector('svg, .arrow, .icon') ? true : false,
                };
            }
        }
        return null;
    }""")
    print(f"  Advanced button: {adv_btn}", flush=True)

    if adv_btn:
        # Check children of Advanced section
        adv_children = page.evaluate(f"""() => {{
            // Find the Advanced container and its children
            for (const el of document.querySelectorAll('*')) {{
                var text = (el.innerText || '').trim();
                var r = el.getBoundingClientRect();
                if (text === 'Advanced' && r.x > 60 && r.x < 360 && r.y > 0 && r.y < 900 && r.width > 80) {{
                    var container = el.parentElement;
                    var items = [];
                    if (container) {{
                        var children = container.querySelectorAll('*');
                        for (var i = 0; i < children.length; i++) {{
                            var ch = children[i];
                            var cr = ch.getBoundingClientRect();
                            var ct = (ch.innerText || '').trim();
                            if (cr.height > 0 && cr.width > 0 && ct.length > 0 && ct.length < 40) {{
                                items.push({{
                                    tag: ch.tagName,
                                    text: ct,
                                    x: Math.round(cr.x), y: Math.round(cr.y),
                                    w: Math.round(cr.width), h: Math.round(cr.height),
                                    classes: (ch.className || '').toString().substring(0, 40),
                                }});
                            }}
                        }}
                    }}
                    return items.sort(function(a,b) {{ return a.y - b.y; }}).slice(0, 15);
                }}
            }}
            return [];
        }}""")
        print(f"\n  Advanced children ({len(adv_children)}):", flush=True)
        for ch in adv_children:
            print(f"    ({ch['x']},{ch['y']}) {ch['w']}x{ch['h']} <{ch['tag']}> c='{ch['classes'][:25]}' '{ch['text'][:30]}'", flush=True)

    # ============================================================
    #  PART 2: TXT2IMG "MORE" ASPECT RATIOS
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 2: TXT2IMG MORE RATIOS", flush=True)
    print("=" * 60, flush=True)

    # Scroll back to top to see aspect ratio row
    page.mouse.move(200, 300)
    for _ in range(5):
        page.mouse.wheel(0, -200)
        page.wait_for_timeout(200)

    # Find the "..." more button near aspect ratio row
    more_btn = page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if ((text === '...' || text === '…' || text === 'more')
                && r.x > 200 && r.x < 360 && r.y > 350 && r.y < 430
                && r.width > 10 && r.height > 10) {
                return {
                    text: text,
                    x: Math.round(r.x + r.width/2),
                    y: Math.round(r.y + r.height/2),
                    w: Math.round(r.width), h: Math.round(r.height),
                    tag: el.tagName,
                };
            }
        }
        return null;
    }""")
    print(f"  More button: {more_btn}", flush=True)

    if more_btn:
        page.mouse.click(more_btn['x'], more_btn['y'])
        page.wait_for_timeout(1500)

        ss(page, "P53_02_more_ratios")

        # Dump the dropdown
        more_dropdown = page.evaluate("""() => {
            var items = [];
            for (const el of document.querySelectorAll('*')) {
                var r = el.getBoundingClientRect();
                var style = window.getComputedStyle(el);
                var zIndex = parseInt(style.zIndex) || 0;
                var text = (el.innerText || '').trim();
                if (zIndex > 50 && r.width > 80 && r.height > 15
                    && text.length > 2 && text.length < 30
                    && r.y > 300 && r.y < 800) {
                    items.push({
                        text: text,
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        z: zIndex,
                    });
                }
            }
            var seen = new Set();
            return items.filter(function(i) {
                var key = i.text + '|' + i.y;
                if (seen.has(key)) return false;
                seen.add(key);
                return true;
            }).sort(function(a,b) { return a.y - b.y; });
        }""")
        print(f"  More dropdown ({len(more_dropdown)}):", flush=True)
        for el in more_dropdown:
            print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} z={el['z']} '{el['text']}'", flush=True)

        # Close dropdown
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)
    else:
        # Check if "more" is styled differently
        all_near_ratios = page.evaluate("""() => {
            var items = [];
            for (const el of document.querySelectorAll('*')) {
                var r = el.getBoundingClientRect();
                if (r.x > 280 && r.x < 370 && r.y > 360 && r.y < 410
                    && r.width > 5 && r.height > 5) {
                    var cursor = window.getComputedStyle(el).cursor;
                    items.push({
                        tag: el.tagName,
                        text: (el.innerText || '').trim().substring(0, 10),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        cursor: cursor,
                        classes: (el.className || '').toString().substring(0, 30),
                    });
                }
            }
            return items;
        }""")
        print(f"  Elements near ratio row end ({len(all_near_ratios)}):", flush=True)
        for el in all_near_ratios:
            print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> cur={el['cursor']} c='{el['classes'][:20]}' '{el['text']}'", flush=True)

    # ============================================================
    #  PART 3: VARIATION FROM RESULTS
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 3: VARIATION FROM RESULTS", flush=True)
    print("=" * 60, flush=True)

    # Switch to Results tab
    page.mouse.click(1096, 49)
    page.wait_for_timeout(1000)

    # Find Variation "1" button
    var_btn = page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text === 'Variation' && r.x > 1100 && r.y > 100 && r.y < 400) {
                for (const btn of document.querySelectorAll('button')) {
                    var bt = (btn.innerText || '').trim();
                    var br = btn.getBoundingClientRect();
                    if (bt === '1' && Math.abs(br.y - r.y) < 15 && br.x > 1200) {
                        return {
                            label_y: Math.round(r.y),
                            btn_x: Math.round(br.x + br.width/2),
                            btn_y: Math.round(br.y + br.height/2),
                        };
                    }
                }
            }
        }
        return null;
    }""")
    print(f"  Variation '1': {var_btn}", flush=True)

    if var_btn:
        print(f"  Clicking Variation '1' at ({var_btn['btn_x']},{var_btn['btn_y']})...", flush=True)
        page.mouse.click(var_btn['btn_x'], var_btn['btn_y'])
        page.wait_for_timeout(3000)
        close_dialogs(page)

        ss(page, "P53_03_variation_panel")

        # Dump the left panel
        dump_panel(page, "Variation panel", 60, 370, 40, 900)

        # Check for auto-populated prompt, model, strength slider
        var_features = page.evaluate("""() => {
            var items = [];
            for (const el of document.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                var r = el.getBoundingClientRect();
                if (r.x > 60 && r.x < 360 && r.width > 50 && r.y > 0 && r.y < 900
                    && text.length > 2 && text.length < 50
                    && (text.includes('Variation') || text.includes('Strength')
                        || text.includes('Model') || text.includes('Generate')
                        || text.includes('Similarity') || text.includes('Reference')
                        || text.includes('Prompt') || text.includes('Style'))) {
                    items.push({
                        text: text.substring(0, 40),
                        x: Math.round(r.x), y: Math.round(r.y),
                        tag: el.tagName,
                    });
                }
            }
            return items.sort(function(a,b) { return a.y - b.y; }).slice(0, 15);
        }""")
        print(f"\n  Variation features ({len(var_features)}):", flush=True)
        for f in var_features:
            print(f"    ({f['x']},{f['y']}) <{f['tag']}> '{f['text'][:35]}'", flush=True)

        # Go back
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)

    # ============================================================
    #  PART 4: FACE SWAP FROM RESULTS
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 4: FACE SWAP FROM RESULTS", flush=True)
    print("=" * 60, flush=True)

    # Ensure Results tab
    page.mouse.click(1096, 49)
    page.wait_for_timeout(1000)

    fs_btn = page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text === 'Face Swap' && r.x > 1100 && r.y > 100 && r.y < 600) {
                for (const btn of document.querySelectorAll('button')) {
                    var bt = (btn.innerText || '').trim();
                    var br = btn.getBoundingClientRect();
                    if (bt === '1' && Math.abs(br.y - r.y) < 15 && br.x > 1200) {
                        return {
                            btn_x: Math.round(br.x + br.width/2),
                            btn_y: Math.round(br.y + br.height/2),
                        };
                    }
                }
            }
        }
        return null;
    }""")
    print(f"  Face Swap '1': {fs_btn}", flush=True)

    if fs_btn:
        page.mouse.click(fs_btn['btn_x'], fs_btn['btn_y'])
        page.wait_for_timeout(3000)
        close_dialogs(page)

        ss(page, "P53_04_face_swap_panel")
        dump_panel(page, "Face Swap panel", 60, 370, 40, 900)

        # Check for face upload controls
        fs_controls = page.evaluate("""() => {
            var items = [];
            for (const btn of document.querySelectorAll('button')) {
                var classes = (btn.className || '').toString();
                var r = btn.getBoundingClientRect();
                if (r.x > 60 && r.x < 360 && r.width > 30 && r.y > 0 && r.y < 900
                    && (classes.includes('pick') || classes.includes('upload')
                        || classes.includes('face') || classes.includes('swap'))) {
                    items.push({
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        classes: classes.substring(0, 40),
                        text: (btn.innerText || '').trim().substring(0, 30),
                    });
                }
            }
            return items.sort(function(a,b) { return a.y - b.y; });
        }""")
        print(f"\n  Face Swap controls ({len(fs_controls)}):", flush=True)
        for c in fs_controls:
            print(f"    ({c['x']},{c['y']}) {c['w']}x{c['h']} c='{c['classes'][:30]}' '{c['text'][:20]}'", flush=True)

        # Go back
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)

    # ============================================================
    #  PART 5: PRODUCT BACKGROUND (IMAGE EDITOR)
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 5: PRODUCT BACKGROUND", flush=True)
    print("=" * 60, flush=True)

    # First place a result image on canvas (click a result thumbnail)
    place_img = page.evaluate("""() => {
        for (const img of document.querySelectorAll('img')) {
            var src = img.src || '';
            if (src.includes('static.dzine.ai/stylar_product')) {
                var r = img.getBoundingClientRect();
                if (r.width > 50 && r.height > 30 && r.x > 1000) {
                    img.click();
                    return {x: Math.round(r.x), y: Math.round(r.y)};
                }
            }
        }
        return null;
    }""")
    print(f"  Placed image on canvas: {place_img}", flush=True)
    page.wait_for_timeout(2000)

    # Open Image Editor sidebar
    page.mouse.click(40, 698)
    page.wait_for_timeout(2000)
    close_dialogs(page)

    ss(page, "P53_05_image_editor")

    # Scroll down to find Product Background
    page.mouse.move(200, 500)
    for i in range(6):
        page.mouse.wheel(0, 200)
        page.wait_for_timeout(300)

    # Look for Product Background
    pb_found = page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if ((text === 'Product Background' || text.includes('Product'))
                && r.x > 60 && r.x < 360 && r.y > 0 && r.y < 900 && r.width > 80) {
                return {
                    text: text.substring(0, 30),
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    tag: el.tagName,
                };
            }
        }
        return null;
    }""")
    print(f"  Product Background: {pb_found}", flush=True)

    if pb_found:
        # Click it
        page.mouse.click(pb_found['x'] + pb_found['w']//2, pb_found['y'] + pb_found['h']//2)
        page.wait_for_timeout(2000)
        close_dialogs(page)

        ss(page, "P53_06_product_bg")
        dump_panel(page, "Product Background panel", 60, 370, 40, 900)

    ss(page, "P53_07_final")
    print(f"\n\n===== PHASE 53 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
