"""Phase 60: Find CC panel scroll container, toggle Style, map top bar toolbar icons.

From P59:
- CC panel opens correctly (header="Consistent Character")
- Style switch exists at (0,0) hidden — it's in the DOM but not rendered into view
- Scroll attempt with .gen-config-body/.gen-config failed (returned None)
- Need to find the actual scrollable container in CC panel
- Top bar toolbar icons (cursor, pen, text, shapes) not found — likely SVGs without text

Goals:
1. Find all scrollable elements in the CC panel area
2. Scroll the correct container to reveal Style toggle
3. Toggle Style ON and document what appears
4. Map the top bar toolbar icons by class/position
5. Map the zoom controls
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
    #  PART 1: OPEN CC PANEL AND FIND SCROLL CONTAINER
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 1: CC PANEL SCROLL CONTAINER", flush=True)
    print("=" * 60, flush=True)

    # Open Character menu
    page.mouse.dblclick(40, 306)
    page.wait_for_timeout(2000)
    close_dialogs(page)

    # Click Generate Images
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
    close_dialogs(page)

    # Select Ray
    page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            if (text === 'Ray' && el.tagName === 'BUTTON') { el.click(); return true; }
        }
        return false;
    }""")
    page.wait_for_timeout(2000)
    close_dialogs(page)

    ss(page, "P60_01_cc_panel")

    # Find ALL scrollable elements in the left sidebar area
    scrollables = page.evaluate("""() => {
        var items = [];
        for (const el of document.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            if (r.x >= 0 && r.x < 370 && r.width > 100 && r.height > 200
                && el.scrollHeight > el.clientHeight + 10) {
                var classes = (el.className || '').toString();
                items.push({
                    tag: el.tagName,
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    scrollH: el.scrollHeight,
                    clientH: el.clientHeight,
                    scrollTop: el.scrollTop,
                    classes: classes.substring(0, 60),
                    overflow: window.getComputedStyle(el).overflow + '/' + window.getComputedStyle(el).overflowY,
                });
            }
        }
        return items.sort(function(a,b) { return a.y - b.y; });
    }""")
    print(f"  Scrollable elements in sidebar ({len(scrollables)}):", flush=True)
    for s in scrollables:
        print(f"    ({s['x']},{s['y']}) {s['w']}x{s['h']} scrollH={s['scrollH']} clientH={s['clientH']} overflow={s['overflow']} c='{s['classes'][:50]}'", flush=True)

    # Try scrolling each scrollable element
    for i, s in enumerate(scrollables):
        print(f"\n  --- Scrolling element {i}: ({s['x']},{s['y']}) c='{s['classes'][:40]}' ---", flush=True)

        # Scroll to bottom
        page.evaluate(f"""() => {{
            var items = [];
            var idx = 0;
            for (const el of document.querySelectorAll('*')) {{
                var r = el.getBoundingClientRect();
                if (r.x >= 0 && r.x < 370 && r.width > 100 && r.height > 200
                    && el.scrollHeight > el.clientHeight + 10) {{
                    if (idx === {i}) {{
                        el.scrollTop = el.scrollHeight;
                        return {{scrollTop: el.scrollTop, scrollH: el.scrollHeight}};
                    }}
                    idx++;
                }}
            }}
            return null;
        }}""")
        page.wait_for_timeout(500)

        # Check if Style is now visible
        style_visible = page.evaluate("""() => {
            for (const el of document.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                var r = el.getBoundingClientRect();
                if (text === 'Style' && r.x > 60 && r.x < 300
                    && r.y > 0 && r.y < 900 && r.width > 20 && r.height > 5) {
                    return {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width)};
                }
            }
            return null;
        }""")
        print(f"    Style visible after scroll: {style_visible}", flush=True)

        if style_visible:
            ss(page, f"P60_02_scrolled_style_visible")
            break

        # Scroll back
        page.evaluate(f"""() => {{
            var idx = 0;
            for (const el of document.querySelectorAll('*')) {{
                var r = el.getBoundingClientRect();
                if (r.x >= 0 && r.x < 370 && r.width > 100 && r.height > 200
                    && el.scrollHeight > el.clientHeight + 10) {{
                    if (idx === {i}) {{ el.scrollTop = 0; return; }}
                    idx++;
                }}
            }}
        }}""")
        page.wait_for_timeout(300)

    # Alternative: use mouse wheel scroll in the panel area
    if not any(page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text === 'Style' && r.x > 60 && r.x < 300
                && r.y > 0 && r.y < 900 && r.width > 20) return true;
        }
        return false;
    }""") for _ in [0]):
        print("\n  Style still not visible, trying mouse wheel scroll...", flush=True)
        # Position mouse in the CC panel area and scroll down
        page.mouse.move(200, 500)
        page.mouse.wheel(0, 500)
        page.wait_for_timeout(1000)

        style_after_wheel = page.evaluate("""() => {
            for (const el of document.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                var r = el.getBoundingClientRect();
                if (text === 'Style' && r.x > 60 && r.x < 300
                    && r.y > 0 && r.y < 900 && r.width > 20 && r.height > 5) {
                    return {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width)};
                }
            }
            return null;
        }""")
        print(f"  Style after mouse wheel: {style_after_wheel}", flush=True)
        ss(page, "P60_03_after_wheel")

        if not style_after_wheel:
            # Try more wheel
            page.mouse.wheel(0, 500)
            page.wait_for_timeout(500)
            style_after_wheel2 = page.evaluate("""() => {
                for (const el of document.querySelectorAll('*')) {
                    var text = (el.innerText || '').trim();
                    var r = el.getBoundingClientRect();
                    if (text === 'Style' && r.x > 60 && r.x < 300
                        && r.y > 0 && r.y < 900 && r.width > 20 && r.height > 5) {
                        return {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width)};
                    }
                }
                return null;
            }""")
            print(f"  Style after more wheel: {style_after_wheel2}", flush=True)
            ss(page, "P60_04_after_more_wheel")

    # ============================================================
    #  PART 2: TOGGLE STYLE (IF VISIBLE)
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 2: TOGGLE STYLE", flush=True)
    print("=" * 60, flush=True)

    style_pos = page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text === 'Style' && r.x > 60 && r.x < 300
                && r.y > 0 && r.y < 900 && r.width > 20 && r.height > 5) {
                // Find switch near this
                var parent = el;
                for (var p = 0; p < 6 && parent; p++) {
                    var switches = parent.querySelectorAll('button');
                    for (var s of switches) {
                        var sc = (s.className || '').toString();
                        var sr = s.getBoundingClientRect();
                        if (sc.includes('switch') && sr.width > 25 && sr.width < 55
                            && sr.y > 0 && sr.y < 900) {
                            return {
                                labelX: Math.round(r.x), labelY: Math.round(r.y),
                                switchX: Math.round(sr.x + sr.width/2),
                                switchY: Math.round(sr.y + sr.height/2),
                                classes: sc.substring(0, 40),
                            };
                        }
                    }
                    parent = parent.parentElement;
                }
                return {labelX: Math.round(r.x), labelY: Math.round(r.y), noSwitch: true};
            }
        }
        return null;
    }""")
    print(f"  Style position: {style_pos}", flush=True)

    if style_pos and not style_pos.get('noSwitch'):
        print(f"  Clicking Style switch...", flush=True)
        page.mouse.click(style_pos['switchX'], style_pos['switchY'])
        page.wait_for_timeout(2000)
        close_dialogs(page)

        ss(page, "P60_05_style_on")

        # Check what new elements appeared
        new_elements = page.evaluate("""() => {
            var items = [];
            for (const el of document.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                var r = el.getBoundingClientRect();
                var classes = (el.className || '').toString();
                if (r.x > 60 && r.x < 400 && r.y > 0 && r.y < 900
                    && r.width > 20 && r.height > 5
                    && text.length > 1 && text.length < 60
                    && (classes.includes('style') || classes.includes('c-style')
                        || classes.includes('model') || classes.includes('pick')
                        || text.includes('Render') || text.includes('Realistic')
                        || text.includes('3D') || text.includes('Dzine')
                        || text.includes('Nano') || text.includes('FLUX')
                        || text.includes('Cinematic') || text.includes('Illustration')
                        || text.includes('GPT'))) {
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
            }).sort(function(a,b) { return a.y - b.y; }).slice(0, 25);
        }""")
        print(f"\n  New style elements ({len(new_elements)}):", flush=True)
        for ne in new_elements:
            print(f"    ({ne['x']},{ne['y']}) {ne['w']}x{ne['h']} <{ne['tag']}> c='{ne['classes'][:25]}' '{ne['text'][:45]}'", flush=True)

        # Check if a model selector appeared
        model_selector = page.evaluate("""() => {
            var btn = document.querySelector('.c-style');
            if (!btn) return null;
            var r = btn.getBoundingClientRect();
            if (r.width < 10 || r.x < 0) return null;
            return {
                text: (btn.innerText || '').trim().substring(0, 40),
                x: Math.round(r.x), y: Math.round(r.y),
                w: Math.round(r.width), h: Math.round(r.height),
            };
        }""")
        print(f"\n  Model selector (c-style): {model_selector}", flush=True)

        # Dump the region after Style toggle with wider range
        full_after = page.evaluate("""() => {
            var items = [];
            for (const el of document.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                var r = el.getBoundingClientRect();
                if (r.x > 60 && r.x < 400 && r.y > 0 && r.y < 900
                    && r.width > 30 && r.height > 10
                    && text.length > 1 && text.length < 60) {
                    items.push({
                        text: text.substring(0, 50),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        tag: el.tagName,
                        classes: (el.className || '').toString().substring(0, 30),
                    });
                }
            }
            var seen = new Set();
            return items.filter(function(i) {
                var key = i.text.substring(0,15) + '|' + Math.round(i.y/3);
                if (seen.has(key)) return false;
                seen.add(key);
                return true;
            }).sort(function(a,b) { return a.y - b.y; }).slice(0, 40);
        }""")
        print(f"\n  Full panel after Style ON ({len(full_after)}):", flush=True)
        for f in full_after:
            print(f"    ({f['x']},{f['y']}) {f['w']}x{f['h']} <{f['tag']}> c='{f['classes'][:22]}' '{f['text'][:45]}'", flush=True)

        # Toggle Style OFF
        page.mouse.click(style_pos['switchX'], style_pos['switchY'])
        page.wait_for_timeout(500)
    else:
        print("  Style still not accessible. Trying page.evaluate direct scroll on all overflows...", flush=True)

        # Nuclear option: find ALL elements with overflow auto/scroll/hidden in sidebar
        overflow_els = page.evaluate("""() => {
            var items = [];
            for (const el of document.querySelectorAll('*')) {
                var r = el.getBoundingClientRect();
                var style = window.getComputedStyle(el);
                var ov = style.overflow + '|' + style.overflowY;
                if (r.x < 370 && r.width > 100 && r.height > 100
                    && (ov.includes('auto') || ov.includes('scroll') || ov.includes('hidden'))
                    && el.scrollHeight > r.height + 5) {
                    items.push({
                        tag: el.tagName,
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        scrollH: el.scrollHeight,
                        overflow: ov,
                        classes: (el.className || '').toString().substring(0, 50),
                    });
                }
            }
            return items;
        }""")
        print(f"\n  Overflow elements ({len(overflow_els)}):", flush=True)
        for oe in overflow_els:
            print(f"    ({oe['x']},{oe['y']}) {oe['w']}x{oe['h']} scrollH={oe['scrollH']} ov={oe['overflow']} c='{oe['classes'][:40]}'", flush=True)

        # Scroll each one
        for i, oe in enumerate(overflow_els):
            print(f"\n  Scrolling overflow element {i}: c='{oe['classes'][:40]}'", flush=True)
            page.evaluate(f"""() => {{
                var idx = 0;
                for (const el of document.querySelectorAll('*')) {{
                    var r = el.getBoundingClientRect();
                    var style = window.getComputedStyle(el);
                    var ov = style.overflow + '|' + style.overflowY;
                    if (r.x < 370 && r.width > 100 && r.height > 100
                        && (ov.includes('auto') || ov.includes('scroll') || ov.includes('hidden'))
                        && el.scrollHeight > r.height + 5) {{
                        if (idx === {i}) {{
                            el.scrollTop = el.scrollHeight;
                            return el.scrollTop;
                        }}
                        idx++;
                    }}
                }}
                return null;
            }}""")
            page.wait_for_timeout(300)

            style_v = page.evaluate("""() => {
                for (const el of document.querySelectorAll('*')) {
                    var text = (el.innerText || '').trim();
                    var r = el.getBoundingClientRect();
                    if (text === 'Style' && r.x > 60 && r.x < 300
                        && r.y > 0 && r.y < 900 && r.width > 20) {
                        return {x: Math.round(r.x), y: Math.round(r.y)};
                    }
                }
                return null;
            }""")
            if style_v:
                print(f"    FOUND Style at ({style_v['x']},{style_v['y']})!", flush=True)
                ss(page, "P60_06_style_found")
                break
            else:
                print(f"    Style not visible", flush=True)
                # Reset
                page.evaluate(f"""() => {{
                    var idx = 0;
                    for (const el of document.querySelectorAll('*')) {{
                        var r = el.getBoundingClientRect();
                        var style = window.getComputedStyle(el);
                        var ov = style.overflow + '|' + style.overflowY;
                        if (r.x < 370 && r.width > 100 && r.height > 100
                            && (ov.includes('auto') || ov.includes('scroll') || ov.includes('hidden'))
                            && el.scrollHeight > r.height + 5) {{
                            if (idx === {i}) {{ el.scrollTop = 0; return; }}
                            idx++;
                        }}
                    }}
                }}""")

    # ============================================================
    #  PART 3: TOP BAR TOOLBAR ICONS
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 3: TOP BAR TOOLBAR ICONS", flush=True)
    print("=" * 60, flush=True)

    # Map the toolbar area between project name and credits
    # Look for ALL elements with SVGs, buttons, icons
    toolbar = page.evaluate("""() => {
        var items = [];
        // Check the top bar area y=28-72 for all interactive elements
        for (const el of document.querySelectorAll('button, svg, [role="button"], div[class*="tool"], div[class*="icon"]')) {
            var r = el.getBoundingClientRect();
            if (r.y > 20 && r.y < 75 && r.x > 150 && r.x < 900
                && r.width > 10 && r.width < 80 && r.height > 10 && r.height < 60) {
                var text = (el.innerText || el.textContent || '').trim();
                var title = el.title || el.getAttribute('aria-label') || '';
                var classes = (el.className || '').toString();
                // Skip if it's a child SVG path
                if (el.tagName === 'path' || el.tagName === 'line' || el.tagName === 'circle') continue;
                items.push({
                    text: (text || title || '(none)').substring(0, 30),
                    title: title.substring(0, 40),
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    tag: el.tagName,
                    classes: classes.toString().substring(0, 40),
                });
            }
        }
        var seen = new Set();
        return items.filter(function(i) {
            var key = Math.round(i.x / 5);
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
        }).sort(function(a,b) { return a.x - b.x; });
    }""")
    print(f"  Toolbar elements ({len(toolbar)}):", flush=True)
    for t in toolbar:
        print(f"    ({t['x']},{t['y']}) {t['w']}x{t['h']} <{t['tag']}> c='{t['classes'][:25]}' title='{t['title'][:25]}' '{t['text'][:20]}'", flush=True)

    # Also look for tool names/labels as tooltips when hovering
    # Hover over each toolbar position and check for tooltip
    test_positions = [
        (175, 48, "pos_175"),
        (200, 48, "pos_200"),
        (225, 48, "pos_225"),
        (250, 48, "pos_250"),
        (275, 48, "pos_275"),
        (300, 48, "pos_300"),
        (325, 48, "pos_325"),
        (350, 48, "pos_350"),
        (375, 48, "pos_375"),
        (400, 48, "pos_400"),
        (425, 48, "pos_425"),
        (450, 48, "pos_450"),
        (475, 48, "pos_475"),
        (500, 48, "pos_500"),
    ]

    print(f"\n  Hovering over toolbar positions to detect tooltips...", flush=True)
    for (hx, hy, label) in test_positions:
        page.mouse.move(hx, hy)
        page.wait_for_timeout(800)

        tooltip = page.evaluate("""() => {
            // Check for high-z tooltip or any visible tooltip-like element
            for (const el of document.querySelectorAll('*')) {
                var style = window.getComputedStyle(el);
                var z = parseInt(style.zIndex) || 0;
                var r = el.getBoundingClientRect();
                var text = (el.innerText || '').trim();
                if (z > 100 && r.width > 20 && r.height > 10
                    && text.length > 1 && text.length < 50
                    && r.y > 40 && r.y < 120) {
                    return text.substring(0, 40);
                }
            }
            // Also check for title or aria-label of element under mouse
            var el = document.elementFromPoint(arguments && arguments[0] || 0, arguments && arguments[1] || 0);
            return null;
        }""")
        if tooltip:
            print(f"    x={hx}: '{tooltip}'", flush=True)

    ss(page, "P60_07_final")

    print(f"\n\n===== PHASE 60 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
