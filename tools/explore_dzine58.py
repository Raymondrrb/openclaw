"""Phase 58: CC Generate Images active panel (Style toggle), Generate 360° Video, Motion Control details.

From P57:
- Character sidebar has 4 workflow cards: Generate Images, Insert Character, Character Sheet, 360° Video
- Character Sheet fully mapped (Dzine 3D Render v2, 16:9/2:1/4:3, 4 credits)
- CC Style toggle NOT found because we were in Character Sheet mode
- Need to click "Generate Images" card specifically to see CC active panel with Style toggle

Goals:
1. Click "Generate Images" card in Character menu → get the CC active panel
2. Find and toggle the Style switch → document what it reveals
3. Click "Generate 360° Video" card → map the panel
4. Explore Motion Control in more detail (Kling 2.6, what inputs needed)
5. Check if the current CC panel differs from what we documented in P52
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
    page.set_viewport_size({"width": 1440, "height": 900})

    page.goto(CANVAS_URL, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(5000)
    close_dialogs(page)

    # ============================================================
    #  PART 1: CC "GENERATE IMAGES" ACTIVE PANEL + STYLE TOGGLE
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 1: CC GENERATE IMAGES ACTIVE PANEL", flush=True)
    print("=" * 60, flush=True)

    # Open Character menu (double-click)
    page.mouse.dblclick(40, 306)
    page.wait_for_timeout(2000)
    close_dialogs(page)

    # Click "Generate Images" card specifically
    gen_clicked = page.evaluate("""() => {
        // Find all elements that contain "Generate Images" but NOT "Generate 360"
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text.startsWith('Generate Images') && !text.includes('360')
                && r.x > 60 && r.x < 200 && r.width > 100 && r.height > 20 && r.height < 80
                && r.y > 80 && r.y < 250) {
                el.click();
                return {text: text.substring(0, 60), x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height)};
            }
        }
        return null;
    }""")
    print(f"  Clicked Generate Images card: {gen_clicked}", flush=True)
    page.wait_for_timeout(2000)
    close_dialogs(page)

    # Check header
    header = page.evaluate("""() => {
        for (const el of document.querySelectorAll('.gen-config-header')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (r.x > 0 && r.width > 50) return text.substring(0, 40);
        }
        return null;
    }""")
    print(f"  Header after click: {header}", flush=True)

    ss(page, "P58_01_cc_generate_images")

    # If it opened a character selection dialog, select Ray
    ray_check = page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            if (text === 'Ray' && el.tagName === 'BUTTON') {
                var r = el.getBoundingClientRect();
                return {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width)};
            }
        }
        return null;
    }""")
    if ray_check:
        print(f"  Ray button found, selecting...", flush=True)
        page.evaluate("""() => {
            for (const el of document.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                if (text === 'Ray' && el.tagName === 'BUTTON') {
                    el.click(); return true;
                }
            }
            return false;
        }""")
        page.wait_for_timeout(2000)
        close_dialogs(page)

    # Now dump the full CC active panel
    ss(page, "P58_02_cc_active_panel")
    dump_region(page, "CC active panel", 60, 370, 40, 900)

    # Specifically look for Style toggle and its position
    style_search = page.evaluate("""() => {
        var items = [];
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (r.x > 60 && r.x < 370 && r.width > 20 && r.height > 5
                && (text === 'Style' || text === 'CC Style' || text.includes('Style'))
                && text.length < 30 && r.y > 300) {
                items.push({
                    text: text,
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    tag: el.tagName,
                    classes: (el.className || '').toString().substring(0, 40),
                });
            }
        }
        return items;
    }""")
    print(f"\n  Style elements ({len(style_search)}):", flush=True)
    for s in style_search:
        print(f"    ({s['x']},{s['y']}) {s['w']}x{s['h']} <{s['tag']}> c='{s['classes'][:25]}' '{s['text']}'", flush=True)

    # Find all switch/toggle buttons in the panel
    switches = page.evaluate("""() => {
        var items = [];
        for (const btn of document.querySelectorAll('button')) {
            var classes = (btn.className || '').toString();
            var r = btn.getBoundingClientRect();
            if (classes.includes('switch') && r.x > 60 && r.x < 370 && r.width > 20 && r.width < 60) {
                // Find the label near this switch
                var label = '';
                var parent = btn.parentElement;
                for (var p = 0; p < 4 && parent; p++) {
                    var texts = (parent.innerText || '').trim().split('\\n');
                    if (texts[0] && texts[0].length < 30) { label = texts[0]; break; }
                    parent = parent.parentElement;
                }
                items.push({
                    label: label,
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    classes: classes.substring(0, 40),
                    active: classes.includes('active') || classes.includes('on'),
                });
            }
        }
        return items.sort(function(a,b) { return a.y - b.y; });
    }""")
    print(f"\n  Switch/toggle buttons ({len(switches)}):", flush=True)
    for sw in switches:
        state = "ON" if sw['active'] else "OFF"
        print(f"    ({sw['x']},{sw['y']}) {sw['w']}x{sw['h']} [{state}] c='{sw['classes'][:30]}' label='{sw['label'][:25]}'", flush=True)

    # Scroll down to check for more content below viewport
    page.evaluate("""() => {
        var panels = document.querySelectorAll('.gen-config, .gen-config-body, [class*="sidebar-content"]');
        for (var p of panels) {
            if (p.scrollHeight > p.clientHeight) {
                p.scrollTop = p.scrollHeight;
                return true;
            }
        }
        return false;
    }""")
    page.wait_for_timeout(500)

    below = page.evaluate("""() => {
        var items = [];
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (r.x > 60 && r.x < 370 && r.y > 700 && r.y < 1200
                && r.width > 20 && r.height > 5
                && text.length > 1 && text.length < 50) {
                items.push({
                    text: text.substring(0, 40),
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    tag: el.tagName,
                    classes: (el.className || '').toString().substring(0, 30),
                });
            }
        }
        var seen = new Set();
        return items.filter(function(i) {
            var key = i.text.substring(0,15) + '|' + i.y;
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
        }).sort(function(a,b) { return a.y - b.y; }).slice(0, 25);
    }""")
    print(f"\n  Below-viewport content ({len(below)}):", flush=True)
    for b in below:
        print(f"    ({b['x']},{b['y']}) {b['w']}x{b['h']} <{b['tag']}> c='{b['classes'][:22]}' '{b['text'][:35]}'", flush=True)

    ss(page, "P58_03_cc_scrolled")

    # Scroll back to top
    page.evaluate("""() => {
        var panels = document.querySelectorAll('.gen-config, .gen-config-body, [class*="sidebar-content"]');
        for (var p of panels) { p.scrollTop = 0; }
    }""")
    page.wait_for_timeout(500)

    # Now try toggling each switch and see what appears
    for sw in switches:
        if sw['label'] and 'Style' in sw['label']:
            print(f"\n  >>> Toggling Style switch at ({sw['x']},{sw['y']})...", flush=True)
            page.mouse.click(sw['x'] + sw['w']//2, sw['y'] + sw['h']//2)
            page.wait_for_timeout(2000)
            close_dialogs(page)

            ss(page, "P58_04_style_toggled")

            # Dump what changed
            style_panel = page.evaluate("""() => {
                var items = [];
                for (const el of document.querySelectorAll('*')) {
                    var text = (el.innerText || '').trim();
                    var r = el.getBoundingClientRect();
                    var classes = (el.className || '').toString();
                    if (r.x > 60 && r.x < 400 && r.width > 20 && r.height > 5
                        && text.length > 1 && text.length < 60
                        && (classes.includes('style') || classes.includes('model')
                            || classes.includes('config') || classes.includes('select')
                            || r.y > 700)) {
                        items.push({
                            text: text.substring(0, 50),
                            x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height),
                            tag: el.tagName,
                            classes: classes.substring(0, 30),
                        });
                    }
                }
                var seen = new Set();
                return items.filter(function(i) {
                    var key = i.text.substring(0,15) + '|' + i.y;
                    if (seen.has(key)) return false;
                    seen.add(key);
                    return true;
                }).sort(function(a,b) { return a.y - b.y; }).slice(0, 30);
            }""")
            print(f"  Style panel content ({len(style_panel)}):", flush=True)
            for sp in style_panel:
                print(f"    ({sp['x']},{sp['y']}) {sp['w']}x{sp['h']} <{sp['tag']}> c='{sp['classes'][:22]}' '{sp['text'][:45]}'", flush=True)

            # Full dump after style toggle
            dump_region(page, "CC after Style toggle", 60, 400, 700, 950)

            # Toggle Style back OFF
            page.mouse.click(sw['x'] + sw['w']//2, sw['y'] + sw['h']//2)
            page.wait_for_timeout(500)
            break

    # ============================================================
    #  PART 2: GENERATE 360° VIDEO PANEL
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 2: GENERATE 360° VIDEO", flush=True)
    print("=" * 60, flush=True)

    # Go back to Character menu
    # Click back arrow
    page.evaluate("""() => {
        // Look for back arrow or close button near the top
        for (const el of document.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            if (r.x > 80 && r.x < 100 && r.y > 50 && r.y < 75
                && r.width > 10 && r.width < 40 && r.height > 10 && r.height < 40
                && (el.tagName === 'BUTTON' || el.tagName === 'SVG' || el.tagName === 'DIV')) {
                el.click(); return true;
            }
        }
        return false;
    }""")
    page.wait_for_timeout(1000)

    # If back arrow didn't work, try double-clicking Character sidebar
    header_check = page.evaluate("""() => {
        for (const el of document.querySelectorAll('.gen-config-header')) {
            var text = (el.innerText || '').trim();
            return text.substring(0, 30);
        }
        return null;
    }""")
    print(f"  After back: header={header_check}", flush=True)

    if header_check != 'Character':
        page.mouse.dblclick(40, 306)
        page.wait_for_timeout(2000)
        close_dialogs(page)

    # Click "Generate 360° Video" card
    video360 = page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if ((text.includes('360') || text.includes('Video'))
                && text.includes('Generate')
                && r.x > 60 && r.x < 200 && r.width > 100
                && r.height > 20 && r.height < 80 && r.y > 200) {
                el.click();
                return {text: text.substring(0, 60), x: Math.round(r.x), y: Math.round(r.y)};
            }
        }
        return null;
    }""")
    print(f"  Clicked 360° Video card: {video360}", flush=True)
    page.wait_for_timeout(2000)
    close_dialogs(page)

    ss(page, "P58_05_360_video")
    dump_region(page, "360° Video panel", 60, 370, 40, 900)

    # ============================================================
    #  PART 3: MOTION CONTROL DETAIL
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 3: MOTION CONTROL DETAIL", flush=True)
    print("=" * 60, flush=True)

    # Toggle to Motion Control
    page.mouse.click(40, 306)  # Character first
    page.wait_for_timeout(300)
    page.mouse.click(40, 550)  # Motion Control
    page.wait_for_timeout(2000)
    close_dialogs(page)

    ss(page, "P58_06_motion_control")
    dump_region(page, "Motion Control panel", 60, 370, 40, 900)

    # ============================================================
    #  PART 4: PRODUCT BACKGROUND IN IMAGE EDITOR
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 4: IMAGE EDITOR — PRODUCT BACKGROUND", flush=True)
    print("=" * 60, flush=True)

    # Toggle to Image Editor
    page.mouse.click(40, 550)  # Motion Control first
    page.wait_for_timeout(300)
    page.mouse.click(40, 698)  # Image Editor
    page.wait_for_timeout(2000)
    close_dialogs(page)

    ss(page, "P58_07_image_editor")

    # Scroll down in Image Editor to find Product Background
    page.evaluate("""() => {
        var panels = document.querySelectorAll('.gen-config-body, .gen-config');
        for (var p of panels) {
            if (p.scrollHeight > p.clientHeight) {
                p.scrollTop = p.scrollHeight;
                return true;
            }
        }
        return false;
    }""")
    page.wait_for_timeout(500)

    # Look for Product Background specifically
    prod_bg = page.evaluate("""() => {
        var items = [];
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (r.x > 60 && r.x < 370 && r.width > 50
                && (text.includes('Product') || text.includes('Background')
                    || text.includes('Remove') || text.includes('BG'))
                && text.length < 60 && text.length > 3) {
                items.push({
                    text: text.substring(0, 50),
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    tag: el.tagName,
                    classes: (el.className || '').toString().substring(0, 40),
                });
            }
        }
        return items.sort(function(a,b) { return a.y - b.y; }).slice(0, 10);
    }""")
    print(f"\n  Product Background elements ({len(prod_bg)}):", flush=True)
    for pb in prod_bg:
        print(f"    ({pb['x']},{pb['y']}) {pb['w']}x{pb['h']} <{pb['tag']}> c='{pb['classes'][:25]}' '{pb['text'][:45]}'", flush=True)

    ss(page, "P58_08_image_editor_scrolled")

    # Full dump of Image Editor after scroll
    dump_region(page, "Image Editor scrolled", 60, 370, 40, 900)

    # ============================================================
    #  PART 5: CHECK CC PANEL WITH RAY SELECTED — FULL SCROLL
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 5: CC PANEL FULL LAYOUT (WITH RAY)", flush=True)
    print("=" * 60, flush=True)

    # Go back to CC Generate Images
    page.mouse.dblclick(40, 306)
    page.wait_for_timeout(2000)
    close_dialogs(page)

    # Click Generate Images specifically
    page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text.startsWith('Generate Images') && !text.includes('360')
                && r.x > 60 && r.x < 200 && r.width > 100 && r.height > 20 && r.height < 80
                && r.y > 80 && r.y < 250) {
                el.click(); return true;
            }
        }
        return false;
    }""")
    page.wait_for_timeout(2000)
    close_dialogs(page)

    # Select Ray if needed
    page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            if (text === 'Ray' && el.tagName === 'BUTTON') {
                el.click(); return true;
            }
        }
        return false;
    }""")
    page.wait_for_timeout(2000)
    close_dialogs(page)

    ss(page, "P58_09_cc_with_ray")

    # Full panel dump from top to bottom (scroll to see everything)
    dump_region(page, "CC panel top half", 60, 370, 40, 500)

    # Scroll down to see the rest
    page.evaluate("""() => {
        var panels = document.querySelectorAll('.gen-config-body, .gen-config');
        for (var p of panels) {
            if (p.scrollHeight > p.clientHeight) {
                p.scrollTop = p.scrollHeight;
                return {scrollH: p.scrollHeight, clientH: p.clientHeight};
            }
        }
        return null;
    }""")
    page.wait_for_timeout(500)

    ss(page, "P58_10_cc_scrolled")
    dump_region(page, "CC panel scrolled bottom", 60, 370, 40, 900)

    print(f"\n\n===== PHASE 58 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
