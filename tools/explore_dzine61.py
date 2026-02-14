"""Phase 61: CC Style toggle via tall viewport + direct JS click approach.

From P60:
- CC panel has NO scrollable containers and NO overflow elements
- Style switch exists at (0,0) hidden in DOM (label='StyleNEW')
- Mouse wheel scroll doesn't work on CC panel
- Panel may simply clip content at viewport bottom

Two approaches:
1. Use taller viewport (1440x1200) so Style is visible without scrolling
2. Direct JS click on the hidden Style switch element

Also: fix the tooltip hover error from P60 Part 3.
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


def dump_region(page, label, x_min, x_max, y_min, y_max, limit=60):
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
    print(f"\n  {label} ({len(items)} elements):", flush=True)
    for el in items[:limit]:
        print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> c='{el['classes'][:22]}' '{el['text'][:40]}'", flush=True)
    return items


def main():
    print("Connecting...", flush=True)
    pw = sync_playwright().start()
    browser = pw.chromium.connect_over_cdp("http://127.0.0.1:18800", timeout=15000)
    ctx = browser.contexts[0]
    page = ctx.new_page()

    # ============================================================
    #  APPROACH 1: TALL VIEWPORT
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  APPROACH 1: TALL VIEWPORT (1440x1200)", flush=True)
    print("=" * 60, flush=True)

    page.set_viewport_size({"width": 1440, "height": 1200})
    page.goto(CANVAS_URL, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(5000)
    close_dialogs(page)

    # Open CC → Generate Images → Ray
    page.mouse.dblclick(40, 306)
    page.wait_for_timeout(2000)
    close_dialogs(page)

    page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text === 'Generate Images' && r.x > 60 && r.y > 80 && r.y < 250 && r.height < 50) {
                el.click(); return true;
            }
        }
        return false;
    }""")
    page.wait_for_timeout(2000)

    page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            if (text === 'Ray' && el.tagName === 'BUTTON') { el.click(); return true; }
        }
        return false;
    }""")
    page.wait_for_timeout(2000)
    close_dialogs(page)

    # Check if Style is visible now with taller viewport
    style_visible = page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text === 'Style' && r.x > 60 && r.x < 300
                && r.y > 0 && r.y < 1200 && r.width > 20 && r.height > 5) {
                return {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)};
            }
        }
        return null;
    }""")
    print(f"  Style visible at 1200h: {style_visible}", flush=True)

    if style_visible:
        ss(page, "P61_01_tall_viewport_style")
        dump_region(page, "CC panel (tall viewport)", 60, 370, 40, 1200)

        # Find the Style switch
        style_switch = page.evaluate("""() => {
            for (const el of document.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                var r = el.getBoundingClientRect();
                if (text === 'Style' && r.x > 60 && r.x < 300 && r.y > 0 && r.y < 1200) {
                    var parent = el;
                    for (var p = 0; p < 6 && parent; p++) {
                        var switches = parent.querySelectorAll('button');
                        for (var s of switches) {
                            var sc = (s.className || '').toString();
                            var sr = s.getBoundingClientRect();
                            if (sc.includes('switch') && sr.width > 25 && sr.width < 55
                                && sr.y > 0 && sr.y < 1200) {
                                return {
                                    x: Math.round(sr.x + sr.width/2),
                                    y: Math.round(sr.y + sr.height/2),
                                    classes: sc.substring(0, 40),
                                };
                            }
                        }
                        parent = parent.parentElement;
                    }
                }
            }
            return null;
        }""")
        print(f"  Style switch: {style_switch}", flush=True)

        if style_switch:
            print(f"\n  >>> Toggling Style ON at ({style_switch['x']},{style_switch['y']})...", flush=True)
            page.mouse.click(style_switch['x'], style_switch['y'])
            page.wait_for_timeout(2000)
            close_dialogs(page)

            ss(page, "P61_02_style_on")

            # Dump everything after Style toggle
            dump_region(page, "CC after Style ON (tall)", 60, 400, 40, 1200)

            # Check specifically for new model/style elements
            style_content = page.evaluate("""() => {
                var items = [];
                for (const el of document.querySelectorAll('*')) {
                    var text = (el.innerText || '').trim();
                    var r = el.getBoundingClientRect();
                    var classes = (el.className || '').toString();
                    if (r.x > 60 && r.x < 400 && r.y > 0 && r.y < 1200
                        && r.width > 30 && r.height > 10
                        && text.length > 1 && text.length < 60
                        && (classes.includes('c-style') || classes.includes('style-name')
                            || classes.includes('style-desc') || classes.includes('pick')
                            || text.includes('Render') || text.includes('Realistic')
                            || text.includes('3D') || text.includes('Dzine')
                            || text.includes('Cinematic') || text.includes('FLUX')
                            || text.includes('Product') || text.includes('model'))) {
                        items.push({
                            text: text.substring(0, 50),
                            x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height),
                            tag: el.tagName,
                            classes: classes.substring(0, 40),
                        });
                    }
                }
                var seen = new Set();
                return items.filter(function(i) {
                    var key = i.text.substring(0,20) + '|' + Math.round(i.y);
                    if (seen.has(key)) return false;
                    seen.add(key);
                    return true;
                }).sort(function(a,b) { return a.y - b.y; }).slice(0, 20);
            }""")
            print(f"\n  Style-specific elements ({len(style_content)}):", flush=True)
            for sc in style_content:
                print(f"    ({sc['x']},{sc['y']}) {sc['w']}x{sc['h']} <{sc['tag']}> c='{sc['classes'][:25]}' '{sc['text'][:45]}'", flush=True)

            # Toggle back OFF
            page.mouse.click(style_switch['x'], style_switch['y'])
            page.wait_for_timeout(500)

    else:
        print("  Style not visible even at 1200h! Trying 1440x1500...", flush=True)
        page.set_viewport_size({"width": 1440, "height": 1500})
        page.wait_for_timeout(1000)

        style_v2 = page.evaluate("""() => {
            for (const el of document.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                var r = el.getBoundingClientRect();
                if (text === 'Style' && r.x > 60 && r.x < 300
                    && r.y > 0 && r.y < 1500 && r.width > 20) {
                    return {x: Math.round(r.x), y: Math.round(r.y)};
                }
            }
            return null;
        }""")
        print(f"  Style at 1500h: {style_v2}", flush=True)

    # ============================================================
    #  APPROACH 2: DIRECT JS CLICK ON HIDDEN SWITCH
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  APPROACH 2: DIRECT JS CLICK ON HIDDEN STYLE SWITCH", flush=True)
    print("=" * 60, flush=True)

    # Reset viewport
    page.set_viewport_size({"width": 1440, "height": 900})
    page.wait_for_timeout(500)

    # Find the Style switch in DOM even if at (0,0)
    style_dom = page.evaluate("""() => {
        var switches = document.querySelectorAll('button');
        for (var i = 0; i < switches.length; i++) {
            var sw = switches[i];
            var classes = (sw.className || '').toString();
            if (!classes.includes('switch')) continue;
            // Check if parent/ancestor has "Style" text
            var parent = sw.parentElement;
            for (var p = 0; p < 5 && parent; p++) {
                var texts = (parent.innerText || '').trim().split('\\n');
                for (var t of texts) {
                    if (t.trim() === 'Style' || t.includes('StyleNEW') || t.trim() === 'Style\\nNEW') {
                        var r = sw.getBoundingClientRect();
                        return {
                            index: i,
                            x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height),
                            classes: classes.substring(0, 40),
                            parentText: (parent.innerText || '').trim().substring(0, 40),
                        };
                    }
                }
                parent = parent.parentElement;
            }
        }
        return null;
    }""")
    print(f"  Style switch in DOM: {style_dom}", flush=True)

    if style_dom:
        print(f"  Attempting JS click on switch at DOM index {style_dom['index']}...", flush=True)
        clicked = page.evaluate(f"""() => {{
            var switches = document.querySelectorAll('button');
            var sw = switches[{style_dom['index']}];
            if (sw) {{
                sw.click();
                return true;
            }}
            return false;
        }}""")
        print(f"  JS click result: {clicked}", flush=True)
        page.wait_for_timeout(2000)
        close_dialogs(page)

        ss(page, "P61_03_style_js_click")

        # Check what changed
        after_click = page.evaluate("""() => {
            var items = [];
            for (const el of document.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                var r = el.getBoundingClientRect();
                var classes = (el.className || '').toString();
                if (r.x > 60 && r.x < 400 && r.y > 0 && r.y < 900
                    && r.width > 30 && r.height > 10
                    && text.length > 1 && text.length < 60
                    && (classes.includes('c-style') || classes.includes('style-name')
                        || text.includes('Render') || text.includes('3D')
                        || text.includes('Dzine') || text.includes('FLUX')
                        || text.includes('Realistic') || text.includes('Product')
                        || text.includes('Cinematic'))) {
                    items.push({
                        text: text.substring(0, 50),
                        x: Math.round(r.x), y: Math.round(r.y),
                        tag: el.tagName,
                        classes: classes.substring(0, 30),
                    });
                }
            }
            return items.sort(function(a,b) { return a.y - b.y; }).slice(0, 15);
        }""")
        print(f"\n  After JS click — style elements ({len(after_click)}):", flush=True)
        for ac in after_click:
            print(f"    ({ac['x']},{ac['y']}) <{ac['tag']}> c='{ac['classes'][:22]}' '{ac['text'][:45]}'", flush=True)

        # Click again to toggle off
        page.evaluate(f"""() => {{
            var switches = document.querySelectorAll('button');
            switches[{style_dom['index']}].click();
        }}""")
        page.wait_for_timeout(500)

    # ============================================================
    #  PART 3: TOP BAR TOOLS (BETWEEN NAV AND CREDITS)
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 3: TOP BAR TOOLS", flush=True)
    print("=" * 60, flush=True)

    # The toolbar icons are in the area between the project name/canvas size and the right panel
    # They're typically SVG icons. Let's get ALL elements in that strip.
    top_strip = page.evaluate("""() => {
        var items = [];
        for (const el of document.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            // Top bar icons area: y 30-75, x 200-950
            if (r.y > 28 && r.y < 76 && r.x > 170 && r.x < 950
                && r.width > 8 && r.width < 100 && r.height > 8 && r.height < 60) {
                var tag = el.tagName.toLowerCase();
                // Skip SVG internals
                if (['path','line','circle','g','defs','rect','polygon','clippath','use','mask'].includes(tag)) continue;
                var text = (el.innerText || el.textContent || '').trim();
                var title = el.title || el.getAttribute('aria-label') || '';
                var classes = (el.className || '').toString();
                if (typeof classes !== 'string') classes = classes.baseVal || '';
                items.push({
                    text: (text || '').substring(0, 20),
                    title: title.substring(0, 40),
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    tag: el.tagName,
                    classes: classes.substring(0, 40),
                    cursor: window.getComputedStyle(el).cursor,
                });
            }
        }
        var seen = new Set();
        return items.filter(function(i) {
            var key = Math.round(i.x/4) + '|' + i.tag;
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
        }).sort(function(a,b) { return a.x - b.x; });
    }""")
    print(f"  Top strip elements ({len(top_strip)}):", flush=True)
    for t in top_strip:
        clickable = "CLICK" if t['cursor'] == 'pointer' else t['cursor'][:6]
        print(f"    ({t['x']},{t['y']}) {t['w']}x{t['h']} <{t['tag']}> [{clickable}] c='{t['classes'][:25]}' title='{t['title'][:25]}' '{t['text'][:15]}'", flush=True)

    # Now let's click each top bar icon and check what it does
    # First, take a reference screenshot
    ss(page, "P61_04_top_bar")

    # Check for the image editor-style top bar (AI Eraser, Hand Repair, etc.)
    # These appear at y~47 area
    editor_tools = page.evaluate("""() => {
        var items = [];
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (r.y > 35 && r.y < 75 && r.x > 170 && r.x < 600
                && text.length > 3 && text.length < 30 && r.width > 30) {
                items.push({
                    text: text,
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    tag: el.tagName,
                });
            }
        }
        return items.sort(function(a,b) { return a.x - b.x; });
    }""")
    print(f"\n  Editor tools in top bar ({len(editor_tools)}):", flush=True)
    for et in editor_tools:
        print(f"    ({et['x']},{et['y']}) {et['w']}x{et['h']} <{et['tag']}> '{et['text']}'", flush=True)

    # ============================================================
    #  PART 4: CANVAS INTERACTION TOOLS (ZOOM, PAN)
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 4: CANVAS CONTROLS (ZOOM, PAN)", flush=True)
    print("=" * 60, flush=True)

    # Look for zoom controls
    zoom = page.evaluate("""() => {
        var items = [];
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if ((text.includes('%') || text === '+' || text === '-' || text === 'Fit'
                || text === 'Reset') && r.y > 850 && r.width > 10 && r.width < 100
                && r.x > 0 && r.x < 100) {
                items.push({
                    text: text.substring(0, 20),
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    tag: el.tagName,
                    classes: (el.className || '').toString().substring(0, 30),
                });
            }
        }
        return items.sort(function(a,b) { return a.y - b.y; });
    }""")
    print(f"  Zoom controls ({len(zoom)}):", flush=True)
    for z in zoom:
        print(f"    ({z['x']},{z['y']}) {z['w']}x{z['h']} <{z['tag']}> c='{z['classes'][:22]}' '{z['text']}'", flush=True)

    # Look for bottom-left controls (common for canvas editors)
    bottom_left = page.evaluate("""() => {
        var items = [];
        for (const el of document.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            var text = (el.innerText || '').trim();
            var classes = (el.className || '').toString();
            if (r.x < 200 && r.y > 850 && r.width > 10
                && (text.length > 0 || classes.includes('zoom') || classes.includes('scale')
                    || classes.includes('tool'))) {
                items.push({
                    text: text.substring(0, 30),
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    tag: el.tagName,
                    classes: classes.substring(0, 40),
                });
            }
        }
        return items.sort(function(a,b) { return a.x - b.x; }).slice(0, 15);
    }""")
    print(f"\n  Bottom-left controls ({len(bottom_left)}):", flush=True)
    for bl in bottom_left:
        print(f"    ({bl['x']},{bl['y']}) {bl['w']}x{bl['h']} <{bl['tag']}> c='{bl['classes'][:30]}' '{bl['text'][:25]}'", flush=True)

    # Check the zoom percentage in top bar
    zoom_top = page.evaluate("""() => {
        var el = document.querySelector('.c-scale-ratio');
        if (!el) return null;
        var r = el.getBoundingClientRect();
        return {
            text: (el.innerText || '').trim(),
            x: Math.round(r.x), y: Math.round(r.y),
            classes: (el.className || '').toString().substring(0, 40),
        };
    }""")
    print(f"\n  Zoom indicator: {zoom_top}", flush=True)

    ss(page, "P61_05_final")

    print(f"\n\n===== PHASE 61 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
