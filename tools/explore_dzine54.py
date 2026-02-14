"""Phase 54: Clean state → Txt2Img Advanced, Txt2Img more ratios, Variation confirmation.

From P53:
- Panel toggle failed because page was in Image Editor mode (top bar tools visible)
- Variation/Face Swap are ONE-CLICK actions — trigger generation directly, no editing panel
- Image Editor shows intro card popup
- Need to exit tool mode first, then activate Txt2Img

Goals:
1. Exit any tool mode (back arrow, Escape, Exit button)
2. Activate Txt2Img panel properly
3. Find and expand Advanced section
4. Find "more" aspect ratios button
5. Confirm Variation/Face Swap are direct-generation actions
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


def dump_region(page, label, x_min, x_max, y_min, y_max, limit=50):
    """Dump unique text elements in a rectangular region."""
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


def exit_tool_mode(page):
    """Exit any active tool mode (Expression Edit, Image Editor, etc.)."""
    # Try Exit button
    try:
        exit_btn = page.locator('button:has-text("Exit")')
        if exit_btn.count() > 0 and exit_btn.first.is_visible(timeout=500):
            exit_btn.first.click()
            page.wait_for_timeout(1000)
            print("  Exited via Exit button", flush=True)
            return
    except Exception:
        pass

    # Try back arrow in top-left of panel
    back = page.evaluate("""() => {
        for (const el of document.querySelectorAll('button, svg, [class*="back"], [class*="arrow"]')) {
            var r = el.getBoundingClientRect();
            if (r.x > 60 && r.x < 110 && r.y > 40 && r.y < 75
                && r.width > 10 && r.width < 50) {
                el.click(); return true;
            }
        }
        return false;
    }""")
    if back:
        page.wait_for_timeout(1000)
        print("  Exited via back arrow", flush=True)
        return

    # Press Escape
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)
    print("  Pressed Escape", flush=True)


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
    #  STEP 0: CLEAN STATE
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  STEP 0: CLEAN STATE", flush=True)
    print("=" * 60, flush=True)

    exit_tool_mode(page)
    close_dialogs(page)

    ss(page, "P54_00_clean")

    # Check what's in the top bar to confirm we're in clean state
    top_bar = page.evaluate("""() => {
        var items = [];
        for (const el of document.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            if (r.y < 50 && r.x > 350 && r.x < 700 && r.height > 10 && r.height < 50
                && r.width > 20 && r.width < 150) {
                var text = (el.innerText || '').trim();
                if (text.length > 2 && text.length < 20) {
                    items.push({text: text, x: Math.round(r.x), y: Math.round(r.y)});
                }
            }
        }
        return items.sort(function(a,b) { return a.x - b.x; });
    }""")
    print(f"  Top bar tools: {[t['text'] for t in top_bar]}", flush=True)

    # If Image Editor tools are showing (AI Eraser, Hand Repair, etc.), we need to exit
    if any('Eraser' in t['text'] or 'Repair' in t['text'] for t in top_bar):
        print("  Image Editor mode active — clicking sidebar to exit...", flush=True)
        # Click any sidebar icon to force panel change
        page.mouse.click(40, 197)  # Txt2Img
        page.wait_for_timeout(1000)
        close_dialogs(page)

    # ============================================================
    #  STEP 1: ACTIVATE TXT2IMG PANEL
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  STEP 1: ACTIVATE TXT2IMG", flush=True)
    print("=" * 60, flush=True)

    # Panel toggle: click different sidebar first, then Txt2Img
    page.mouse.click(40, 252)  # Img2Img (a different tool)
    page.wait_for_timeout(1000)
    page.mouse.click(40, 197)  # Txt2Img
    page.wait_for_timeout(2000)
    close_dialogs(page)

    # Check if panel header is "Text to Image"
    header = page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if ((text === 'Text to Image' || text === 'Text-to-Image')
                && r.x > 60 && r.x < 200 && r.y > 40 && r.y < 100 && r.width > 80) {
                return {text: text, x: Math.round(r.x), y: Math.round(r.y)};
            }
        }
        return null;
    }""")
    print(f"  Header: {header}", flush=True)

    if not header:
        # Maybe we got the intro card — look for it and click through
        intro = page.evaluate("""() => {
            for (const el of document.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                var r = el.getBoundingClientRect();
                if (text.includes('Text-to-Image') && text.includes('Creates') && r.x > 60 && r.y > 100) {
                    return {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)};
                }
            }
            return null;
        }""")
        if intro:
            print(f"  Found intro card, clicking...", flush=True)
            page.mouse.click(intro['x'] + intro['w']//2, intro['y'] + intro['h']//2)
            page.wait_for_timeout(2000)
            close_dialogs(page)

        # Second attempt: double-click the Txt2Img sidebar icon
        print("  Double-clicking Txt2Img...", flush=True)
        page.mouse.click(40, 197)
        page.wait_for_timeout(200)
        page.mouse.click(40, 197)
        page.wait_for_timeout(2000)
        close_dialogs(page)

        header = page.evaluate("""() => {
            for (const el of document.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                var r = el.getBoundingClientRect();
                if ((text === 'Text to Image' || text === 'Text-to-Image')
                    && r.x > 60 && r.x < 200 && r.y > 40 && r.y < 100 && r.width > 80) {
                    return {text: text, x: Math.round(r.x), y: Math.round(r.y)};
                }
            }
            return null;
        }""")
        print(f"  Header after retry: {header}", flush=True)

    ss(page, "P54_01_txt2img")

    if not header:
        print("  FALLBACK: Dumping everything in left area...", flush=True)
        dump_region(page, "Full left area", 0, 400, 40, 900)

    # ============================================================
    #  STEP 2: FIND ADVANCED SECTION
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  STEP 2: ADVANCED SECTION", flush=True)
    print("=" * 60, flush=True)

    if header:
        # We're in the active panel. Find Advanced.
        adv = page.evaluate("""() => {
            for (const el of document.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                var r = el.getBoundingClientRect();
                if (text === 'Advanced' && r.x > 60 && r.x < 360 && r.y > 0 && r.y < 900 && r.width > 60) {
                    // Check if it's clickable
                    var cursor = window.getComputedStyle(el).cursor;
                    // Check parent for clickability
                    var parent = el.parentElement;
                    var pcursor = parent ? window.getComputedStyle(parent).cursor : '';
                    return {
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        tag: el.tagName, cursor: cursor, pcursor: pcursor,
                        classes: (el.className || '').toString().substring(0, 40),
                        pclasses: parent ? (parent.className || '').toString().substring(0, 40) : '',
                    };
                }
            }
            return null;
        }""")
        print(f"  Advanced: {adv}", flush=True)

        if adv:
            # Click the Advanced label or its parent
            print(f"  Clicking Advanced at ({adv['x']},{adv['y']})...", flush=True)
            page.mouse.click(adv['x'] + adv['w']//2, adv['y'] + adv['h']//2)
            page.wait_for_timeout(1500)

            # Check if something expanded below
            expanded = page.evaluate(f"""() => {{
                var items = [];
                for (const el of document.querySelectorAll('*')) {{
                    var r = el.getBoundingClientRect();
                    var text = (el.innerText || '').trim();
                    if (r.x > 60 && r.x < 360 && r.y > {adv['y']} && r.y < {adv['y'] + 200}
                        && r.width > 30 && r.height > 5
                        && text.length > 0 && text.length < 60) {{
                        items.push({{
                            text: text.substring(0, 40),
                            x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height),
                            tag: el.tagName,
                        }});
                    }}
                }}
                var seen = new Set();
                return items.filter(function(i) {{
                    var key = i.text.substring(0,15) + '|' + i.y;
                    if (seen.has(key)) return false;
                    seen.add(key);
                    return true;
                }}).sort(function(a,b) {{ return a.y - b.y; }});
            }}""")
            print(f"\n  Below Advanced ({len(expanded)}):", flush=True)
            for el in expanded:
                print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> '{el['text'][:35]}'", flush=True)

            # If Advanced didn't expand, try clicking its parent element
            if len(expanded) <= 2:
                print("\n  Advanced didn't expand, trying parent click...", flush=True)
                parent_clicked = page.evaluate(f"""() => {{
                    for (const el of document.querySelectorAll('*')) {{
                        var text = (el.innerText || '').trim();
                        var r = el.getBoundingClientRect();
                        if (text === 'Advanced' && r.x > 60 && r.x < 360 && r.y > 0 && r.y < 900 && r.width > 60) {{
                            var p = el.parentElement;
                            if (p) {{
                                p.click();
                                return {{tag: p.tagName, cls: (p.className || '').toString().substring(0, 40)}};
                            }}
                        }}
                    }}
                    return null;
                }}""")
                print(f"  Parent clicked: {parent_clicked}", flush=True)
                page.wait_for_timeout(1500)

                # Check again
                expanded2 = page.evaluate(f"""() => {{
                    var items = [];
                    for (const el of document.querySelectorAll('*')) {{
                        var r = el.getBoundingClientRect();
                        var text = (el.innerText || '').trim();
                        if (r.x > 60 && r.x < 360 && r.y > {adv['y']} && r.y < {adv['y'] + 300}
                            && r.width > 30 && r.height > 5
                            && text.length > 0 && text.length < 60) {{
                            items.push({{
                                text: text.substring(0, 40),
                                x: Math.round(r.x), y: Math.round(r.y),
                                w: Math.round(r.width), h: Math.round(r.height),
                                tag: el.tagName,
                                classes: (el.className || '').toString().substring(0, 30),
                            }});
                        }}
                    }}
                    var seen = new Set();
                    return items.filter(function(i) {{
                        var key = i.text.substring(0,15) + '|' + i.y;
                        if (seen.has(key)) return false;
                        seen.add(key);
                        return true;
                    }}).sort(function(a,b) {{ return a.y - b.y; }});
                }}""")
                print(f"  After parent click ({len(expanded2)}):", flush=True)
                for el in expanded2:
                    print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> c='{el['classes'][:20]}' '{el['text'][:35]}'", flush=True)

            ss(page, "P54_02_advanced")

            # Check for SVG arrow/chevron in Advanced header (collapse/expand indicator)
            arrow = page.evaluate(f"""() => {{
                for (const el of document.querySelectorAll('*')) {{
                    var text = (el.innerText || '').trim();
                    var r = el.getBoundingClientRect();
                    if (text === 'Advanced' && r.x > 60 && r.y > 0 && r.y < 900) {{
                        // Walk up to parent and check for SVG
                        var container = el.parentElement;
                        if (!container) return null;
                        var svgs = container.querySelectorAll('svg');
                        var arrows = [];
                        for (var i = 0; i < svgs.length; i++) {{
                            var sr = svgs[i].getBoundingClientRect();
                            arrows.push({{
                                x: Math.round(sr.x), y: Math.round(sr.y),
                                w: Math.round(sr.width), h: Math.round(sr.height),
                                transform: svgs[i].style.transform || '',
                            }});
                        }}
                        return {{arrows: arrows, containerH: Math.round(container.getBoundingClientRect().height)}};
                    }}
                }}
                return null;
            }}""")
            print(f"\n  Advanced arrows: {arrow}", flush=True)

    # ============================================================
    #  STEP 3: TXT2IMG "MORE" ASPECT RATIOS
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  STEP 3: TXT2IMG MORE RATIOS", flush=True)
    print("=" * 60, flush=True)

    # Look for elements at end of aspect ratio row (after "canvas" button)
    # From P52: canvas button at (224,378) 68x24, row at y~374-402
    ratio_end = page.evaluate("""() => {
        var items = [];
        for (const el of document.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            if (r.x >= 290 && r.x < 340 && r.y > 365 && r.y < 405
                && r.width > 5 && r.height > 5 && r.width < 50) {
                var cursor = window.getComputedStyle(el).cursor;
                items.push({
                    tag: el.tagName,
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    cursor: cursor,
                    classes: (el.className || '').toString().substring(0, 30),
                    text: (el.innerText || '').trim().substring(0, 10),
                    html: el.outerHTML ? el.outerHTML.substring(0, 80) : '',
                });
            }
        }
        return items;
    }""")
    print(f"  Elements at end of ratio row ({len(ratio_end)}):", flush=True)
    for el in ratio_end:
        print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> cur={el['cursor']} c='{el['classes'][:20]}' '{el['text']}' html: {el['html'][:60]}", flush=True)

    # Try a broader search for any "more" trigger
    more_triggers = page.evaluate("""() => {
        var items = [];
        for (const el of document.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            var cursor = window.getComputedStyle(el).cursor;
            if (r.x > 280 && r.x < 350 && r.y > 360 && r.y < 410
                && r.width > 10 && r.height > 10 && cursor === 'pointer') {
                items.push({
                    tag: el.tagName,
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    classes: (el.className || '').toString().substring(0, 30),
                    text: (el.innerText || '').trim().substring(0, 10),
                });
            }
        }
        return items;
    }""")
    print(f"\n  Pointer elements near ratio end ({len(more_triggers)}):", flush=True)
    for el in more_triggers:
        print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> c='{el['classes'][:20]}' '{el['text']}'", flush=True)

    # Also check for the full ratio row
    ratio_row = page.evaluate("""() => {
        var items = [];
        for (const el of document.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            var text = (el.innerText || '').trim();
            if (r.x > 95 && r.x < 340 && r.y > 365 && r.y < 405
                && r.width > 20 && r.height > 15 && text.length < 15) {
                var cursor = window.getComputedStyle(el).cursor;
                items.push({
                    text: text || '(none)',
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    cursor: cursor,
                    tag: el.tagName,
                });
            }
        }
        return items.sort(function(a,b) { return a.x - b.x; });
    }""")
    print(f"\n  Full ratio row ({len(ratio_row)}):", flush=True)
    for el in ratio_row:
        print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> cur={el['cursor']} '{el['text']}'", flush=True)

    # Try clicking the area right after "canvas" button (there should be a "..." or icon)
    if not more_triggers:
        print("\n  Trying click at (310,385) — area after canvas button...", flush=True)
        page.mouse.click(310, 385)
        page.wait_for_timeout(1500)

        # Check for dropdown
        dropdown = page.evaluate("""() => {
            var items = [];
            for (const el of document.querySelectorAll('*')) {
                var style = window.getComputedStyle(el);
                var z = parseInt(style.zIndex) || 0;
                var r = el.getBoundingClientRect();
                var text = (el.innerText || '').trim();
                if (z > 50 && r.width > 80 && r.height > 20 && text.length > 2 && text.length < 30) {
                    items.push({text: text, x: Math.round(r.x), y: Math.round(r.y), z: z});
                }
            }
            return items.sort(function(a,b) { return a.y - b.y; }).slice(0, 15);
        }""")
        print(f"  Dropdown items: {len(dropdown)}", flush=True)
        for d in dropdown:
            print(f"    ({d['x']},{d['y']}) z={d['z']} '{d['text']}'", flush=True)

        if dropdown:
            ss(page, "P54_03_more_ratios")

        page.keyboard.press("Escape")
        page.wait_for_timeout(500)

    # ============================================================
    #  STEP 4: FULL PANEL DUMP WITH COORDINATES
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  STEP 4: FINAL FULL PANEL DUMP", flush=True)
    print("=" * 60, flush=True)

    dump_region(page, "Complete left panel", 60, 370, 40, 800)

    ss(page, "P54_04_final")
    print(f"\n\n===== PHASE 54 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
