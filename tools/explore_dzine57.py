"""Phase 57: CC Panel activation fix, Character Sheet, CC Style toggle, Upload sidebar.

From P50-56:
- Panel toggle technique works for Txt2Img and Img2Img (click other sidebar first)
- CC panel showed intro card (0 buttons) when using panel toggle in P56
- Character Sheet is a sub-feature of CC panel (not accessed yet)
- CC Style toggle needs investigation (what model/options it reveals)
- Upload sidebar: no file chooser found in P50

Goals:
1. Fix CC panel activation — try different toggle sequences
2. Explore Character Sheet within CC panel
3. Test CC Style toggle — what happens when turned ON?
4. Map Upload sidebar panel completely
5. Test Enhance & Upscale in active mode (not just panel layout)
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
    #  PART 1: CC PANEL ACTIVATION — TRY MULTIPLE APPROACHES
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 1: CC PANEL ACTIVATION ATTEMPTS", flush=True)
    print("=" * 60, flush=True)

    # ---------- Attempt 1: Direct click on Character sidebar ----------
    print("\n  --- Attempt 1: Direct click on Character sidebar ---", flush=True)
    page.mouse.click(40, 306)
    page.wait_for_timeout(2000)
    close_dialogs(page)

    header1 = page.evaluate("""() => {
        for (const el of document.querySelectorAll('.gen-config-header')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (r.x > 0 && r.width > 50) return {text: text, x: Math.round(r.x), y: Math.round(r.y)};
        }
        return null;
    }""")
    print(f"  Direct click header: {header1}", flush=True)

    # Check what's in the CC panel area
    cc_content1 = page.evaluate("""() => {
        var items = [];
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (r.x > 60 && r.x < 370 && r.y > 40 && r.y < 500 && r.width > 50 && r.height > 20
                && text.length > 3 && text.length < 80) {
                items.push({
                    text: text.substring(0, 60),
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    tag: el.tagName,
                    classes: (el.className || '').toString().substring(0, 40),
                });
            }
        }
        var seen = new Set();
        return items.filter(function(i) {
            var key = i.text.substring(0,20) + '|' + i.y;
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
        }).sort(function(a,b) { return a.y - b.y; }).slice(0, 20);
    }""")
    print(f"  CC panel content ({len(cc_content1)} items):", flush=True)
    for c in cc_content1:
        print(f"    ({c['x']},{c['y']}) {c['w']}x{c['h']} <{c['tag']}> c='{c['classes'][:25]}' '{c['text'][:50]}'", flush=True)

    ss(page, "P57_01_cc_direct")

    # ---------- Attempt 2: Toggle from Txt2Img → Character ----------
    print("\n  --- Attempt 2: Toggle Txt2Img → Character ---", flush=True)
    page.mouse.click(40, 197)  # Txt2Img
    page.wait_for_timeout(500)
    page.mouse.click(40, 306)  # Character
    page.wait_for_timeout(2000)
    close_dialogs(page)

    header2 = page.evaluate("""() => {
        for (const el of document.querySelectorAll('.gen-config-header')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (r.x > 0 && r.width > 50) return {text: text, x: Math.round(r.x), y: Math.round(r.y)};
        }
        return null;
    }""")
    print(f"  Toggle header: {header2}", flush=True)
    ss(page, "P57_02_cc_toggle")

    # ---------- Attempt 3: Double-click Character ----------
    print("\n  --- Attempt 3: Double-click Character sidebar ---", flush=True)
    page.mouse.click(40, 197)  # Txt2Img first to reset
    page.wait_for_timeout(500)
    page.mouse.dblclick(40, 306)  # Double-click Character
    page.wait_for_timeout(2000)
    close_dialogs(page)

    header3 = page.evaluate("""() => {
        for (const el of document.querySelectorAll('.gen-config-header')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (r.x > 0 && r.width > 50) return {text: text, x: Math.round(r.x), y: Math.round(r.y)};
        }
        return null;
    }""")
    print(f"  Double-click header: {header3}", flush=True)
    ss(page, "P57_03_cc_doubleclick")

    # ---------- Attempt 4: Click "Generate Images" card directly ----------
    print("\n  --- Attempt 4: Find and click 'Generate Images' card ---", flush=True)
    page.mouse.click(40, 306)  # Character sidebar
    page.wait_for_timeout(1500)
    close_dialogs(page)

    gen_card = page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (r.x > 60 && r.x < 370 && r.width > 100 && r.height > 30
                && (text.includes('Generate Images') || text.includes('With your character'))) {
                return {
                    text: text.substring(0, 80),
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    tag: el.tagName,
                    clickable: el.tagName === 'BUTTON' || el.style.cursor === 'pointer'
                        || el.onclick !== null,
                };
            }
        }
        return null;
    }""")
    print(f"  Generate Images card: {gen_card}", flush=True)

    if gen_card:
        print(f"  Clicking at ({gen_card['x'] + gen_card['w']//2},{gen_card['y'] + gen_card['h']//2})...", flush=True)
        page.mouse.click(gen_card['x'] + gen_card['w']//2, gen_card['y'] + gen_card['h']//2)
        page.wait_for_timeout(2000)
        close_dialogs(page)

        # Check if it opened the active panel
        header4 = page.evaluate("""() => {
            for (const el of document.querySelectorAll('.gen-config-header')) {
                var text = (el.innerText || '').trim();
                var r = el.getBoundingClientRect();
                if (r.x > 0 && r.width > 50) return {text: text, x: Math.round(r.x), y: Math.round(r.y)};
            }
            return null;
        }""")
        print(f"  After Generate Images click header: {header4}", flush=True)
        ss(page, "P57_04_cc_generate_images")

        # Full panel dump
        dump_region(page, "CC active panel", 60, 370, 40, 900)

        # Check for Character Sheet / Generate Images sub-options
        sub_opts = page.evaluate("""() => {
            var items = [];
            for (const el of document.querySelectorAll('button, [role="tab"], [class*="tab"]')) {
                var text = (el.innerText || '').trim();
                var r = el.getBoundingClientRect();
                if (r.x > 60 && r.x < 370 && r.y > 40 && r.y < 200
                    && text.length > 3 && text.length < 60 && r.width > 30) {
                    items.push({
                        text: text.substring(0, 50),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        tag: el.tagName,
                        classes: (el.className || '').toString().substring(0, 40),
                    });
                }
            }
            return items.sort(function(a,b) { return a.y - b.y; }).slice(0, 15);
        }""")
        print(f"\n  CC sub-options (buttons/tabs near top) ({len(sub_opts)}):", flush=True)
        for s in sub_opts:
            print(f"    ({s['x']},{s['y']}) {s['w']}x{s['h']} <{s['tag']}> c='{s['classes'][:25]}' '{s['text'][:40]}'", flush=True)

    # ============================================================
    #  PART 2: CHARACTER SHEET SEARCH
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 2: CHARACTER SHEET SEARCH", flush=True)
    print("=" * 60, flush=True)

    # Look for Character Sheet text anywhere on the page
    cs_search = page.evaluate("""() => {
        var items = [];
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text.includes('Character Sheet') && r.width > 0 && r.height > 0
                && text.length < 100) {
                items.push({
                    text: text.substring(0, 80),
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    tag: el.tagName,
                    classes: (el.className || '').toString().substring(0, 40),
                    visible: r.width > 10 && r.height > 10,
                });
            }
        }
        return items.sort(function(a,b) { return a.y - b.y; }).slice(0, 15);
    }""")
    print(f"  'Character Sheet' elements ({len(cs_search)}):", flush=True)
    for cs in cs_search:
        vis = "VISIBLE" if cs['visible'] else "hidden"
        print(f"    ({cs['x']},{cs['y']}) {cs['w']}x{cs['h']} <{cs['tag']}> [{vis}] c='{cs['classes'][:25]}' '{cs['text'][:60]}'", flush=True)

    # Also check the Results panel — Character Sheet appears as a result type
    result_types = page.evaluate("""() => {
        var types = [];
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (r.x > 1060 && r.y > 50 && text.length > 5 && text.length < 40
                && r.width > 100 && r.height > 10 && r.height < 40
                && (text.includes('Character') || text.includes('Text-to') || text.includes('Image'))) {
                types.push({
                    text: text,
                    x: Math.round(r.x), y: Math.round(r.y),
                    tag: el.tagName,
                });
            }
        }
        var seen = new Set();
        return types.filter(function(t) {
            if (seen.has(t.text)) return false;
            seen.add(t.text);
            return true;
        }).slice(0, 10);
    }""")
    print(f"\n  Result types in Results panel ({len(result_types)}):", flush=True)
    for rt in result_types:
        print(f"    ({rt['x']},{rt['y']}) <{rt['tag']}> '{rt['text']}'", flush=True)

    # ============================================================
    #  PART 3: CC STYLE TOGGLE
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 3: CC STYLE TOGGLE", flush=True)
    print("=" * 60, flush=True)

    # Find the Style toggle in CC panel
    style_toggle = page.evaluate("""() => {
        var items = [];
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (r.x > 60 && r.x < 370 && r.y > 700 && r.y < 900
                && text.length > 0 && text.length < 30
                && (text === 'Style' || text.includes('Style'))) {
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
    print(f"  Style elements ({len(style_toggle)}):", flush=True)
    for s in style_toggle:
        print(f"    ({s['x']},{s['y']}) {s['w']}x{s['h']} <{s['tag']}> c='{s['classes'][:25]}' '{s['text']}'", flush=True)

    # Find and click the Style switch button
    style_switch = page.evaluate("""() => {
        // Find the switch near "Style" label in CC panel
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text === 'Style' && r.x > 60 && r.x < 300 && r.y > 700) {
                // Look for switch button near this label
                var parent = el;
                for (var p = 0; p < 5 && parent; p++) {
                    var switches = parent.querySelectorAll('button');
                    for (var i = 0; i < switches.length; i++) {
                        var sw = switches[i];
                        var sr = sw.getBoundingClientRect();
                        var classes = (sw.className || '').toString();
                        if (classes.includes('switch') && sr.width > 25 && sr.width < 55) {
                            return {
                                x: Math.round(sr.x + sr.width/2),
                                y: Math.round(sr.y + sr.height/2),
                                classes: classes.substring(0, 40),
                                active: classes.includes('active') || classes.includes('on'),
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
        print(f"  Clicking Style switch at ({style_switch['x']},{style_switch['y']})...", flush=True)
        page.mouse.click(style_switch['x'], style_switch['y'])
        page.wait_for_timeout(2000)
        close_dialogs(page)

        ss(page, "P57_05_style_toggled")

        # Check what appeared after toggling Style ON
        style_content = page.evaluate("""() => {
            var items = [];
            for (const el of document.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                var r = el.getBoundingClientRect();
                if (r.x > 60 && r.x < 400 && r.y > 730 && r.y < 900
                    && text.length > 1 && text.length < 60 && r.width > 20 && r.height > 8) {
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
                var key = i.text.substring(0,15) + '|' + i.y;
                if (seen.has(key)) return false;
                seen.add(key);
                return true;
            }).sort(function(a,b) { return a.y - b.y; }).slice(0, 20);
        }""")
        print(f"\n  Style toggle content ({len(style_content)}):", flush=True)
        for s in style_content:
            print(f"    ({s['x']},{s['y']}) {s['w']}x{s['h']} <{s['tag']}> c='{s['classes'][:22]}' '{s['text'][:45]}'", flush=True)

        # Also scroll down to check if more content appeared below viewport
        page.evaluate("""() => {
            var panel = document.querySelector('.gen-config') || document.querySelector('[class*="sidebar-content"]');
            if (panel) panel.scrollTop = panel.scrollHeight;
        }""")
        page.wait_for_timeout(500)

        style_below = page.evaluate("""() => {
            var items = [];
            for (const el of document.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                var r = el.getBoundingClientRect();
                if (r.x > 60 && r.x < 400 && r.y > 700
                    && text.length > 1 && text.length < 60 && r.width > 30 && r.height > 10
                    && (text.includes('model') || text.includes('Model')
                        || text.includes('style') || text.includes('3D')
                        || text.includes('Render') || text.includes('Realistic')
                        || text.includes('Anime') || text.includes('Nano'))) {
                    items.push({
                        text: text.substring(0, 50),
                        x: Math.round(r.x), y: Math.round(r.y),
                        tag: el.tagName,
                    });
                }
            }
            return items.sort(function(a,b) { return a.y - b.y; }).slice(0, 10);
        }""")
        print(f"\n  Style model content below ({len(style_below)}):", flush=True)
        for s in style_below:
            print(f"    ({s['x']},{s['y']}) <{s['tag']}> '{s['text'][:45]}'", flush=True)

        # Toggle Style OFF again
        page.mouse.click(style_switch['x'], style_switch['y'])
        page.wait_for_timeout(500)

    # ============================================================
    #  PART 4: UPLOAD SIDEBAR
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 4: UPLOAD SIDEBAR", flush=True)
    print("=" * 60, flush=True)

    # First click another sidebar to reset, then Upload
    page.mouse.click(40, 197)  # Txt2Img
    page.wait_for_timeout(500)
    page.mouse.click(40, 81)  # Upload
    page.wait_for_timeout(2000)
    close_dialogs(page)

    ss(page, "P57_06_upload_sidebar")

    # Check what's in the Upload panel
    upload_panel = page.evaluate("""() => {
        var items = [];
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (r.x > 60 && r.x < 370 && r.y > 40 && r.y < 900
                && r.width > 20 && r.height > 8 && text.length > 1 && text.length < 80) {
                items.push({
                    text: text.substring(0, 60),
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    tag: el.tagName,
                    classes: (el.className || '').toString().substring(0, 40),
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
    print(f"  Upload panel ({len(upload_panel)}):", flush=True)
    for u in upload_panel:
        print(f"    ({u['x']},{u['y']}) {u['w']}x{u['h']} <{u['tag']}> c='{u['classes'][:25]}' '{u['text'][:50]}'", flush=True)

    # Look for upload/drag zone or button
    upload_zone = page.evaluate("""() => {
        var items = [];
        for (const el of document.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            var classes = (el.className || '').toString();
            var text = (el.innerText || '').trim();
            if (r.x > 60 && r.x < 370 && r.width > 100
                && (classes.includes('upload') || classes.includes('drop')
                    || classes.includes('drag') || classes.includes('file')
                    || text.includes('Upload') || text.includes('Drop')
                    || text.includes('drag') || text.includes('file')
                    || text.includes('browse') || text.includes('select'))) {
                items.push({
                    text: text.substring(0, 60),
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    tag: el.tagName,
                    classes: classes.substring(0, 50),
                });
            }
        }
        return items.slice(0, 15);
    }""")
    print(f"\n  Upload zones/buttons ({len(upload_zone)}):", flush=True)
    for u in upload_zone:
        print(f"    ({u['x']},{u['y']}) {u['w']}x{u['h']} <{u['tag']}> c='{u['classes'][:30]}' '{u['text'][:50]}'", flush=True)

    # Try double-clicking Upload sidebar to activate
    print("\n  --- Double-clicking Upload sidebar ---", flush=True)
    page.mouse.dblclick(40, 81)
    page.wait_for_timeout(2000)
    close_dialogs(page)

    ss(page, "P57_07_upload_doubleclick")

    upload_after = page.evaluate("""() => {
        var items = [];
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (r.x > 60 && r.x < 370 && r.y > 40 && r.y < 500
                && r.width > 20 && text.length > 1 && text.length < 60) {
                items.push({
                    text: text.substring(0, 50),
                    x: Math.round(r.x), y: Math.round(r.y),
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
        }).sort(function(a,b) { return a.y - b.y; }).slice(0, 20);
    }""")
    print(f"  Upload after doubleclick ({len(upload_after)}):", flush=True)
    for u in upload_after:
        print(f"    ({u['x']},{u['y']}) <{u['tag']}> c='{u['classes'][:22]}' '{u['text'][:45]}'", flush=True)

    # ============================================================
    #  PART 5: ASSETS SIDEBAR
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 5: ASSETS SIDEBAR", flush=True)
    print("=" * 60, flush=True)

    page.mouse.click(40, 81)  # Upload first
    page.wait_for_timeout(500)
    page.mouse.click(40, 136)  # Assets
    page.wait_for_timeout(2000)
    close_dialogs(page)

    ss(page, "P57_08_assets_sidebar")
    dump_region(page, "Assets panel", 60, 370, 40, 900)

    # Double-click to see if there's an active mode
    page.mouse.dblclick(40, 136)
    page.wait_for_timeout(2000)
    close_dialogs(page)

    ss(page, "P57_09_assets_doubleclick")

    assets_active = page.evaluate("""() => {
        var items = [];
        for (const el of document.querySelectorAll('.gen-config-header, *')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (r.x > 60 && r.x < 370 && r.y > 40 && r.y < 200
                && text.length > 2 && text.length < 40 && r.width > 50 && r.height > 10) {
                items.push({
                    text: text,
                    x: Math.round(r.x), y: Math.round(r.y),
                    tag: el.tagName,
                    classes: (el.className || '').toString().substring(0, 40),
                });
            }
        }
        var seen = new Set();
        return items.filter(function(i) {
            var key = i.text.substring(0,15);
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
        }).sort(function(a,b) { return a.y - b.y; }).slice(0, 10);
    }""")
    print(f"\n  Assets active headers ({len(assets_active)}):", flush=True)
    for a in assets_active:
        print(f"    ({a['x']},{a['y']}) <{a['tag']}> c='{a['classes'][:25]}' '{a['text'][:35]}'", flush=True)

    # ============================================================
    #  PART 6: COMPREHENSIVE SIDEBAR STATE CHECK
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 6: ALL SIDEBAR ACTIVE PANEL HEADERS", flush=True)
    print("=" * 60, flush=True)

    # Quick scan: click each sidebar and check if gen-config-header appears
    sidebars = [
        ("Upload", (40, 81)),
        ("Assets", (40, 136)),
        ("Txt2Img", (40, 197)),
        ("Img2Img", (40, 252)),
        ("Character", (40, 306)),
        ("AI Video", (40, 361)),
        ("Lip Sync", (40, 425)),
        ("Video Editor", (40, 490)),
        ("Motion Control", (40, 550)),
        ("Enhance", (40, 627)),
        ("Image Editor", (40, 698)),
        ("Storyboard", (40, 766)),
    ]

    for name, (sx, sy) in sidebars:
        # Toggle: click Txt2Img first (unless we ARE txt2img)
        if name != "Txt2Img":
            page.mouse.click(40, 197)
            page.wait_for_timeout(300)
        else:
            page.mouse.click(40, 306)
            page.wait_for_timeout(300)
        page.mouse.click(sx, sy)
        page.wait_for_timeout(1500)
        close_dialogs(page)

        header = page.evaluate("""() => {
            for (const el of document.querySelectorAll('.gen-config-header')) {
                var text = (el.innerText || '').trim();
                var r = el.getBoundingClientRect();
                if (r.x > 0 && r.width > 50 && text.length > 2)
                    return text.substring(0, 40);
            }
            return null;
        }""")
        # Also check for intro card / description
        intro = page.evaluate("""() => {
            for (const el of document.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                var r = el.getBoundingClientRect();
                if (r.x > 60 && r.x < 370 && r.y > 60 && r.y < 300
                    && text.length > 20 && text.length < 200
                    && r.width > 150 && r.height > 20) {
                    return text.substring(0, 80);
                }
            }
            return null;
        }""")
        status = "ACTIVE" if header else "intro/other"
        print(f"  {name:15s} → header={header or 'None':30s} [{status}] intro='{(intro or '')[:50]}'", flush=True)

    ss(page, "P57_10_final")

    print(f"\n\n===== PHASE 57 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
