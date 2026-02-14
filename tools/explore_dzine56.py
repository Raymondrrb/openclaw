"""Phase 56: Character Sheet, CC Style toggle details, Image/layer placement.

From P50-55:
- Complete Txt2Img panel mapped (Face Match, Color Match, Advanced with Seed)
- Insert Character workflow documented
- Action button behavior categorized (direct vs editing panel)
- Panel activation technique confirmed (toggle or double-click)

Goals:
1. Explore Character Sheet in CC panel (different from regular CC generation)
2. Test CC Style toggle in detail — what model/options does it reveal?
3. How to place a result image on canvas as a layer (for Enhance, Export)
4. Test Export workflow (select layer → export button)
5. Explore the Img2Img panel layout
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
    #  PART 1: CHARACTER SHEET IN CC PANEL
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 1: CHARACTER SHEET", flush=True)
    print("=" * 60, flush=True)

    # Open Character sidebar (use toggle technique)
    page.mouse.click(40, 197)  # Txt2Img first
    page.wait_for_timeout(500)
    page.mouse.click(40, 306)  # Character
    page.wait_for_timeout(2000)
    close_dialogs(page)

    # Check for Character Sheet option
    # From earlier phases, CC panel has "Generate Images" and "Character Sheet"
    cc_buttons = page.evaluate("""() => {
        var items = [];
        for (const btn of document.querySelectorAll('button')) {
            var text = (btn.innerText || '').trim();
            var r = btn.getBoundingClientRect();
            if (r.x > 60 && r.x < 360 && r.y > 50 && r.y < 500 && r.width > 100 && r.height > 30
                && text.length > 5 && text.length < 60) {
                items.push({
                    text: text.substring(0, 50),
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    classes: (btn.className || '').toString().substring(0, 40),
                });
            }
        }
        return items.sort(function(a,b) { return a.y - b.y; });
    }""")
    print(f"  CC panel buttons ({len(cc_buttons)}):", flush=True)
    for b in cc_buttons:
        print(f"    ({b['x']},{b['y']}) {b['w']}x{b['h']} c='{b['classes'][:30]}' '{b['text'][:40]}'", flush=True)

    ss(page, "P56_01_cc_panel")

    # Look for Character Sheet button
    cs_btn = None
    for b in cc_buttons:
        if 'Character Sheet' in b['text']:
            cs_btn = b
            break

    if cs_btn:
        print(f"\n  Clicking Character Sheet at ({cs_btn['x']},{cs_btn['y']})...", flush=True)
        page.mouse.click(cs_btn['x'] + cs_btn['w']//2, cs_btn['y'] + cs_btn['h']//2)
        page.wait_for_timeout(2000)
        close_dialogs(page)

        ss(page, "P56_02_character_sheet")

        # Dump the Character Sheet panel
        dump_region(page, "Character Sheet panel", 60, 370, 40, 900)

        # Check for prompt, style, character selection
        cs_features = page.evaluate("""() => {
            var items = [];
            for (const el of document.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                var r = el.getBoundingClientRect();
                if (r.x > 60 && r.x < 360 && r.width > 50 && r.y > 0 && r.y < 900
                    && text.length > 2 && text.length < 50
                    && (text.includes('Generate') || text.includes('Sheet')
                        || text.includes('Character') || text.includes('Style')
                        || text.includes('Prompt') || text.includes('Aspect')
                        || text.includes('Camera') || text.includes('Pose'))) {
                    items.push({
                        text: text.substring(0, 40),
                        x: Math.round(r.x), y: Math.round(r.y),
                        tag: el.tagName,
                    });
                }
            }
            return items.sort(function(a,b) { return a.y - b.y; }).slice(0, 20);
        }""")
        print(f"\n  Character Sheet features ({len(cs_features)}):", flush=True)
        for f in cs_features:
            print(f"    ({f['x']},{f['y']}) <{f['tag']}> '{f['text'][:35]}'", flush=True)

        # Go back to main CC view
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)
    else:
        print("  Character Sheet button NOT found, checking full panel...", flush=True)
        dump_region(page, "Full CC panel", 60, 370, 40, 900)

    # ============================================================
    #  PART 2: IMG2IMG PANEL
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 2: IMG2IMG PANEL", flush=True)
    print("=" * 60, flush=True)

    # Activate Img2Img panel
    page.mouse.click(40, 306)  # Character first
    page.wait_for_timeout(500)
    page.mouse.click(40, 252)  # Img2Img
    page.wait_for_timeout(2000)
    close_dialogs(page)

    # Check if active or intro card
    header = page.evaluate("""() => {
        for (const el of document.querySelectorAll('.gen-config-header')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text.includes('Img2Img') || text.includes('Image to Image') || text.includes('Img')) {
                return {text: text, x: Math.round(r.x), y: Math.round(r.y)};
            }
        }
        return null;
    }""")
    print(f"  Img2Img header: {header}", flush=True)

    if not header:
        # Try double-click
        page.mouse.click(40, 252)
        page.wait_for_timeout(200)
        page.mouse.click(40, 252)
        page.wait_for_timeout(2000)
        close_dialogs(page)

    ss(page, "P56_03_img2img")
    dump_region(page, "Img2Img panel", 60, 370, 40, 900)

    # ============================================================
    #  PART 3: LAYER PLACEMENT + EXPORT
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 3: LAYER PLACEMENT + EXPORT", flush=True)
    print("=" * 60, flush=True)

    # Switch to Results tab
    page.mouse.click(1096, 49)
    page.wait_for_timeout(1000)

    # Click a result image to place it on canvas
    placed = page.evaluate("""() => {
        for (const img of document.querySelectorAll('img')) {
            var src = img.src || '';
            if (src.includes('static.dzine.ai/stylar_product')) {
                var r = img.getBoundingClientRect();
                if (r.width > 80 && r.height > 50 && r.x > 1060) {
                    img.click();
                    return {src: src.substring(src.length-50), x: Math.round(r.x), y: Math.round(r.y)};
                }
            }
        }
        return null;
    }""")
    print(f"  Placed image: {placed}", flush=True)
    page.wait_for_timeout(2000)

    # Switch to Layers tab to see the new layer
    page.mouse.click(1280, 49)  # Layers tab
    page.wait_for_timeout(1000)

    ss(page, "P56_04_layers")

    # Dump layers
    layers = page.evaluate("""() => {
        var items = [];
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (r.x > 1060 && r.width > 200 && r.height > 30
                && text.length > 2 && text.length < 30
                && (text.startsWith('Layer') || text === 'Background')) {
                items.push({
                    text: text,
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    tag: el.tagName,
                    classes: (el.className || '').toString().substring(0, 30),
                });
            }
        }
        return items.sort(function(a,b) { return a.y - b.y; });
    }""")
    print(f"\n  Layers ({len(layers)}):", flush=True)
    for l in layers:
        print(f"    ({l['x']},{l['y']}) {l['w']}x{l['h']} <{l['tag']}> c='{l['classes'][:20]}' '{l['text']}'", flush=True)

    # Click the topmost layer to select it
    if layers:
        top_layer = layers[0]
        print(f"\n  Clicking top layer: '{top_layer['text']}' at ({top_layer['x']},{top_layer['y']})", flush=True)
        page.mouse.click(top_layer['x'] + top_layer['w']//2, top_layer['y'] + top_layer['h']//2)
        page.wait_for_timeout(1000)

    # Check Export button state
    export_btn = page.evaluate("""() => {
        for (const btn of document.querySelectorAll('button')) {
            var text = (btn.innerText || '').trim();
            if (text === 'Export') {
                var r = btn.getBoundingClientRect();
                return {
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    disabled: btn.disabled,
                    classes: (btn.className || '').toString().substring(0, 40),
                };
            }
        }
        return null;
    }""")
    print(f"\n  Export button: {export_btn}", flush=True)

    # Click Export to see what options appear
    if export_btn and not export_btn.get('disabled'):
        print(f"  Clicking Export at ({export_btn['x']},{export_btn['y']})...", flush=True)
        page.mouse.click(export_btn['x'] + export_btn['w']//2, export_btn['y'] + export_btn['h']//2)
        page.wait_for_timeout(2000)

        ss(page, "P56_05_export_dialog")

        # Dump the export dialog
        export_dialog = page.evaluate("""() => {
            var items = [];
            for (const el of document.querySelectorAll('*')) {
                var style = window.getComputedStyle(el);
                var z = parseInt(style.zIndex) || 0;
                var r = el.getBoundingClientRect();
                var text = (el.innerText || '').trim();
                if (z > 50 && r.width > 30 && r.height > 10
                    && text.length > 1 && text.length < 50) {
                    items.push({
                        text: text,
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        z: z, tag: el.tagName,
                    });
                }
            }
            var seen = new Set();
            return items.filter(function(i) {
                var key = i.text.substring(0,15) + '|' + i.y;
                if (seen.has(key)) return false;
                seen.add(key);
                return true;
            }).sort(function(a,b) { return a.y - b.y; }).slice(0, 20);
        }""")
        print(f"\n  Export dialog ({len(export_dialog)}):", flush=True)
        for el in export_dialog:
            print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} z={el['z']} <{el['tag']}> '{el['text']}'", flush=True)

        # Close
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)

    ss(page, "P56_06_final")
    print(f"\n\n===== PHASE 56 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
