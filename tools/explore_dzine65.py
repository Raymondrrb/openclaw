"""Phase 65: Model picker overlay (retry with longer wait), Hand Repair, Face Swap, Face Repair.

From P64:
- Model picker failed — page was still loading when screenshot taken (5s wait insufficient)
- Layers: 4 layers, locked class, no right-click context menu
- Insert Object: Reference Object upload, 150 char prompt, 4 credits
- Generative Expand: 8 ratios in 2x4 grid, drag handles, 8 credits

Goals:
1. Properly open model picker with sufficient wait (10s+) and map categories + models
2. Explore Hand Repair sub-tool
3. Explore Face Swap sub-tool
4. Explore Face Repair sub-tool
5. Test layer 3-dot menu (instead of right-click)
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
    print("  Waiting 12s for full canvas load...", flush=True)
    page.wait_for_timeout(12000)
    close_dialogs(page)

    ss(page, "P65_00_loaded")

    # ============================================================
    #  PART 1: MODEL PICKER OVERLAY (RETRY)
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 1: MODEL PICKER OVERLAY", flush=True)
    print("=" * 60, flush=True)

    # Activate Txt2Img with panel toggle
    page.mouse.click(40, 306)  # Character
    page.wait_for_timeout(500)
    page.mouse.click(40, 197)  # Txt2Img
    page.wait_for_timeout(2000)
    close_dialogs(page)

    # Verify Txt2Img is active
    txt2img_active = page.evaluate("""() => {
        for (const el of document.querySelectorAll('.gen-config-header')) {
            if ((el.innerText || '').includes('Text to Image')) return true;
        }
        return false;
    }""")
    print(f"  Txt2Img active: {txt2img_active}", flush=True)

    if not txt2img_active:
        # Fallback: double-click
        page.mouse.dblclick(40, 197)
        page.wait_for_timeout(2000)
        close_dialogs(page)

    # Click the model selector button (button.style or c-style)
    model_clicked = page.evaluate("""() => {
        // Try button.style first
        var btn = document.querySelector('button.style');
        if (btn) {
            var r = btn.getBoundingClientRect();
            if (r.width > 50 && r.height > 20 && r.x > 60) {
                btn.click();
                return {text: (btn.innerText || '').trim(), x: Math.round(r.x), y: Math.round(r.y)};
            }
        }
        // Try c-style container
        var cs = document.querySelector('.c-style');
        if (cs) {
            cs.click();
            var r = cs.getBoundingClientRect();
            return {text: (cs.innerText || '').trim(), x: Math.round(r.x), y: Math.round(r.y)};
        }
        return null;
    }""")
    print(f"  Model button clicked: {model_clicked}", flush=True)
    page.wait_for_timeout(2000)

    ss(page, "P65_01_model_picker_attempt")

    # Scan the full page for any overlay/modal/dialog
    overlay_info = page.evaluate("""() => {
        var overlays = [];
        for (const el of document.querySelectorAll('*')) {
            var style = window.getComputedStyle(el);
            var z = parseInt(style.zIndex) || 0;
            var r = el.getBoundingClientRect();
            if (z > 50 && r.width > 300 && r.height > 200 && r.x > 0) {
                var text = (el.innerText || '').substring(0, 80);
                overlays.push({
                    tag: el.tagName,
                    z: z,
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    classes: (el.className || '').toString().substring(0, 50),
                    text: text,
                });
            }
        }
        return overlays.sort(function(a,b) { return b.z - a.z; }).slice(0, 10);
    }""")
    print(f"\n  Overlays found ({len(overlay_info)}):", flush=True)
    for o in overlay_info:
        print(f"    z={o['z']} ({o['x']},{o['y']}) {o['w']}x{o['h']} <{o['tag']}> c='{o['classes'][:30]}' '{o['text'][:50]}'", flush=True)

    # Try finding any modal/dialog classes
    modal_info = page.evaluate("""() => {
        var selectors = ['.modal', '.dialog', '.picker', '.style-picker', '.overlay',
                         '.style-list', '.model-picker', '.c-model', '.style-gallery',
                         '[class*="picker"]', '[class*="modal"]', '[class*="gallery"]',
                         '[class*="style-list"]', '[class*="popup"]'];
        var results = [];
        for (var sel of selectors) {
            var els = document.querySelectorAll(sel);
            for (var el of els) {
                var r = el.getBoundingClientRect();
                if (r.width > 100 && r.height > 50) {
                    results.push({
                        sel: sel,
                        tag: el.tagName,
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        classes: (el.className || '').toString().substring(0, 60),
                        text: (el.innerText || '').substring(0, 50),
                    });
                }
            }
        }
        return results;
    }""")
    print(f"\n  Modal/picker elements ({len(modal_info)}):", flush=True)
    for m in modal_info:
        print(f"    sel='{m['sel']}' ({m['x']},{m['y']}) {m['w']}x{m['h']} c='{m['classes'][:35]}' '{m['text'][:40]}'", flush=True)

    # Also check for style-name elements (visible when picker is open)
    style_names = page.evaluate("""() => {
        var items = [];
        for (const el of document.querySelectorAll('.style-name')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            items.push({name: text, x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        visible: r.width > 0 && r.height > 0});
        }
        return items.slice(0, 20);
    }""")
    print(f"\n  style-name elements ({len(style_names)}):", flush=True)
    for s in style_names:
        vis = "VIS" if s['visible'] else "HID"
        print(f"    [{vis}] ({s['x']},{s['y']}) {s['w']}x{s['h']} '{s['name']}'", flush=True)

    # Close the picker
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)

    # ============================================================
    #  PART 2: HAND REPAIR SUB-TOOL
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 2: HAND REPAIR SUB-TOOL", flush=True)
    print("=" * 60, flush=True)

    # Activate Image Editor
    page.mouse.click(40, 252)  # Img2Img first
    page.wait_for_timeout(300)
    page.mouse.click(40, 698)  # Image Editor
    page.wait_for_timeout(1500)
    close_dialogs(page)

    # Click Hand Repair
    hand_repair = page.evaluate("""() => {
        for (const btn of document.querySelectorAll('button')) {
            var text = (btn.innerText || '').trim();
            var r = btn.getBoundingClientRect();
            if (text === 'Hand Repair' && r.x > 60 && r.x < 370 && r.y > 200) {
                btn.click();
                return {x: Math.round(r.x), y: Math.round(r.y)};
            }
        }
        return null;
    }""")
    print(f"  Clicked Hand Repair: {hand_repair}", flush=True)
    page.wait_for_timeout(2000)
    close_dialogs(page)

    if hand_repair:
        ss(page, "P65_02_hand_repair")
        dump_region(page, "Hand Repair panel", 60, 370, 40, 900)

    # Go back
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)

    # ============================================================
    #  PART 3: FACE SWAP SUB-TOOL
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 3: FACE SWAP SUB-TOOL", flush=True)
    print("=" * 60, flush=True)

    # Re-activate Image Editor
    page.mouse.click(40, 252)
    page.wait_for_timeout(300)
    page.mouse.click(40, 698)
    page.wait_for_timeout(1500)
    close_dialogs(page)

    # Click Face Swap
    face_swap = page.evaluate("""() => {
        for (const btn of document.querySelectorAll('button')) {
            var text = (btn.innerText || '').trim();
            var r = btn.getBoundingClientRect();
            if (text === 'Face Swap' && r.x > 60 && r.x < 370 && r.y > 400) {
                btn.click();
                return {x: Math.round(r.x), y: Math.round(r.y)};
            }
        }
        return null;
    }""")
    print(f"  Clicked Face Swap: {face_swap}", flush=True)
    page.wait_for_timeout(2000)
    close_dialogs(page)

    if face_swap:
        ss(page, "P65_03_face_swap")
        dump_region(page, "Face Swap panel", 60, 370, 40, 900)

    # Go back
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)

    # ============================================================
    #  PART 4: FACE REPAIR SUB-TOOL
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 4: FACE REPAIR SUB-TOOL", flush=True)
    print("=" * 60, flush=True)

    # Re-activate Image Editor
    page.mouse.click(40, 252)
    page.wait_for_timeout(300)
    page.mouse.click(40, 698)
    page.wait_for_timeout(1500)
    close_dialogs(page)

    # Click Face Repair
    face_repair = page.evaluate("""() => {
        for (const btn of document.querySelectorAll('button')) {
            var text = (btn.innerText || '').trim();
            var r = btn.getBoundingClientRect();
            if (text === 'Face Repair' && r.x > 60 && r.x < 370 && r.y > 400) {
                btn.click();
                return {x: Math.round(r.x), y: Math.round(r.y)};
            }
        }
        return null;
    }""")
    print(f"  Clicked Face Repair: {face_repair}", flush=True)
    page.wait_for_timeout(2000)
    close_dialogs(page)

    if face_repair:
        ss(page, "P65_04_face_repair")
        dump_region(page, "Face Repair panel", 60, 370, 40, 900)

    # Go back
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)

    # ============================================================
    #  PART 5: LAYER 3-DOT MENU
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 5: LAYER 3-DOT MENU", flush=True)
    print("=" * 60, flush=True)

    # Switch to Layers tab
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
    page.wait_for_timeout(1000)

    # Find the 3-dot menu button on the first layer
    dot_menu = page.evaluate("""() => {
        // Look for elements with ":" or "..." or kebab menu near layers
        var items = [];
        for (const el of document.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            var classes = (el.className || '').toString();
            // 3-dot menu is usually a small button/icon near x=1300-1380 inside layer rows
            if (r.x > 1300 && r.x < 1380 && r.y > 80 && r.y < 200
                && r.width > 5 && r.width < 40 && r.height > 5 && r.height < 40) {
                items.push({
                    tag: el.tagName,
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    classes: classes.substring(0, 40),
                    text: (el.innerText || '').trim().substring(0, 20),
                    clickable: el.tagName === 'BUTTON' || el.tagName === 'A' || el.onclick != null,
                });
            }
        }
        return items;
    }""")
    print(f"  Potential 3-dot menu elements ({len(dot_menu)}):", flush=True)
    for d in dot_menu:
        print(f"    ({d['x']},{d['y']}) {d['w']}x{d['h']} <{d['tag']}> click={d['clickable']} c='{d['classes'][:25]}' '{d['text']}'", flush=True)

    # Try clicking the 3-dot icon (colon icon in layers panel)
    # From screenshot, the ":" is at approximately x=1314, y=135 (for Layer 4)
    page.mouse.click(1314, 135)
    page.wait_for_timeout(1000)

    ss(page, "P65_05_layer_menu")

    # Check for any popup/dropdown
    layer_menu = page.evaluate("""() => {
        var items = [];
        for (const el of document.querySelectorAll('*')) {
            var style = window.getComputedStyle(el);
            var z = parseInt(style.zIndex) || 0;
            var r = el.getBoundingClientRect();
            var text = (el.innerText || '').trim();
            if (z > 50 && r.width > 60 && r.height > 15 && r.height < 50
                && text.length > 1 && text.length < 30) {
                items.push({
                    text: text,
                    x: Math.round(r.x), y: Math.round(r.y),
                    z: z, tag: el.tagName,
                    classes: (el.className || '').toString().substring(0, 30),
                });
            }
        }
        var seen = new Set();
        return items.filter(function(i) {
            if (seen.has(i.text)) return false;
            seen.add(i.text);
            return true;
        }).sort(function(a,b) { return a.y - b.y; }).slice(0, 15);
    }""")
    print(f"\n  Layer menu items ({len(layer_menu)}):", flush=True)
    for lm in layer_menu:
        print(f"    z={lm['z']} ({lm['x']},{lm['y']}) <{lm['tag']}> c='{lm['classes'][:22]}' '{lm['text']}'", flush=True)

    # Close menu
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)

    ss(page, "P65_06_final")

    print(f"\n\n===== PHASE 65 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
