"""Phase 78: Open remaining panels (Img2Img, Upload, Assets) by toggling
from a distant sidebar tool (Storyboard or Image Editor) instead of Txt2Img.
Also capture Txt2Img advanced popup.
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


def dump_panel_full(page, label, limit=50):
    """Dump the .panels.show content."""
    items = page.evaluate(f"""() => {{
        var p = document.querySelector('.panels.show');
        if (!p) return [];
        var r = p.getBoundingClientRect();
        var items = [];
        var excluded = ['path','line','circle','g','svg','defs','rect','polygon',
                        'clippath','HTML','BODY','HEAD','SCRIPT','STYLE','META','LINK'];
        for (const el of p.querySelectorAll('*')) {{
            var er = el.getBoundingClientRect();
            if (er.width > 10 && er.height > 10 && er.width < 300
                && !excluded.includes(el.tagName.toUpperCase())) {{
                var text = (el.innerText || '').trim();
                if (text.length > 0 && text.length < 60 && text.indexOf('\\n') === -1) {{
                    items.push({{
                        tag: el.tagName, x: Math.round(er.x), y: Math.round(er.y),
                        w: Math.round(er.width), h: Math.round(er.height),
                        text: text.substring(0, 40),
                        classes: (el.className || '').toString().substring(0, 35),
                    }});
                }}
            }}
        }}
        var seen = new Set();
        return items.filter(function(i) {{
            var key = i.tag + '|' + i.x + '|' + i.y;
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
        }}).sort(function(a,b) {{ return a.y - b.y; }}).slice(0, {limit});
    }}""")
    title = page.evaluate("""() => {
        var p = document.querySelector('.panels.show');
        if (!p) return 'NONE';
        var h5 = p.querySelector('h5');
        return h5 ? (h5.innerText || '').trim() : 'no h5';
    }""")
    print(f"\n  {label} — title='{title}' ({len(items)} elements):", flush=True)
    for el in items:
        print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> c='{el['classes'][:25]}' '{el['text'][:35]}'", flush=True)
    return items


def open_sidebar(page, target_x, target_y, toggle_x=40, toggle_y=766):
    """Open a sidebar tool by toggling from a distant tool first."""
    # Click distant tool first
    page.mouse.click(toggle_x, toggle_y)  # Default: Storyboard
    page.wait_for_timeout(1500)
    close_dialogs(page)
    # Click target
    page.mouse.click(target_x, target_y)
    page.wait_for_timeout(2000)
    close_dialogs(page)


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
    #  PART 1: TXT2IMG PANEL (toggle from Storyboard)
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 1: TXT2IMG PANEL", flush=True)
    print("=" * 60, flush=True)

    open_sidebar(page, 40, 197)  # Txt2Img at (40, 197)
    ss(page, "P78_01_txt2img")
    dump_panel_full(page, "Txt2Img")

    # ============================================================
    #  PART 2: IMG2IMG PANEL (toggle from Storyboard)
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 2: IMG2IMG PANEL", flush=True)
    print("=" * 60, flush=True)

    open_sidebar(page, 40, 252)  # Img2Img at (40, 252)
    ss(page, "P78_02_img2img")
    dump_panel_full(page, "Img2Img")

    # ============================================================
    #  PART 3: UPLOAD PANEL (toggle from Storyboard)
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 3: UPLOAD PANEL", flush=True)
    print("=" * 60, flush=True)

    open_sidebar(page, 40, 81)  # Upload at (40, 81)
    ss(page, "P78_03_upload")
    dump_panel_full(page, "Upload")

    # ============================================================
    #  PART 4: ASSETS PANEL (toggle from Storyboard)
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 4: ASSETS PANEL", flush=True)
    print("=" * 60, flush=True)

    open_sidebar(page, 40, 136)  # Assets at (40, 136)
    ss(page, "P78_04_assets")
    dump_panel_full(page, "Assets")

    # ============================================================
    #  PART 5: TXT2IMG — ADVANCED POPUP
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 5: TXT2IMG ADVANCED POPUP", flush=True)
    print("=" * 60, flush=True)

    # Open Txt2Img
    open_sidebar(page, 40, 197)

    # Click Advanced button
    adv = page.evaluate("""() => {
        var p = document.querySelector('.panels.show');
        if (!p) return null;
        for (const el of p.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text === 'Advanced' && r.width > 30 && r.height > 15) {
                el.click();
                return {x: Math.round(r.x), y: Math.round(r.y), tag: el.tagName};
            }
        }
        return null;
    }""")
    print(f"  Advanced clicked: {adv}", flush=True)
    page.wait_for_timeout(1500)
    ss(page, "P78_05_advanced")

    # Dump the advanced popup/expanded area — might be a dialog or inline expansion
    # Check for high-z popup
    popup = page.evaluate("""() => {
        var items = [];
        for (const el of document.querySelectorAll('*')) {
            var cs = window.getComputedStyle(el);
            var z = parseInt(cs.zIndex) || 0;
            var r = el.getBoundingClientRect();
            if (z > 100 && r.width > 150 && r.height > 100 && r.x < 600) {
                var text = (el.innerText || '').trim().replace(/\\n/g, ' ').substring(0, 80);
                items.push({
                    z: z, tag: el.tagName,
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    classes: (el.className || '').toString().substring(0, 40),
                    text: text.substring(0, 60),
                });
            }
        }
        return items.sort(function(a,b) { return b.z - a.z; }).slice(0, 5);
    }""")
    print(f"\n  High-z elements:", flush=True)
    for p in popup:
        print(f"    z={p['z']} ({p['x']},{p['y']}) {p['w']}x{p['h']} <{p['tag']}> c='{p['classes'][:30]}' '{p['text'][:50]}'", flush=True)

    # Dump elements in popup area
    if popup:
        px = popup[0]
        adv_items = page.evaluate(f"""() => {{
            var items = [];
            for (const el of document.querySelectorAll('*')) {{
                var r = el.getBoundingClientRect();
                if (r.x >= {px['x']} && r.x <= {px['x'] + px['w']}
                    && r.y >= {px['y']} && r.y <= {px['y'] + px['h']}
                    && r.width > 10 && r.height > 10 && r.width < 300) {{
                    var text = (el.innerText || '').trim();
                    if (text.length > 0 && text.length < 50 && text.indexOf('\\n') === -1) {{
                        items.push({{
                            tag: el.tagName, x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height),
                            text: text.substring(0, 40),
                            classes: (el.className || '').toString().substring(0, 30),
                        }});
                    }}
                }}
            }}
            var seen = new Set();
            return items.filter(function(i) {{
                var key = i.tag + '|' + i.x + '|' + i.y;
                if (seen.has(key)) return false;
                seen.add(key);
                return true;
            }}).sort(function(a,b) {{ return a.y - b.y; }}).slice(0, 40);
        }}""")
        print(f"\n  Advanced popup elements ({len(adv_items)}):", flush=True)
        for el in adv_items:
            print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> c='{el['classes'][:22]}' '{el['text'][:35]}'", flush=True)

    page.keyboard.press("Escape")
    page.wait_for_timeout(500)

    # ============================================================
    #  PART 6: TXT2IMG — MODEL SELECTOR
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 6: TXT2IMG MODEL SELECTOR", flush=True)
    print("=" * 60, flush=True)

    # Click on the model/style selector button
    model = page.evaluate("""() => {
        var p = document.querySelector('.panels.show');
        if (!p) return null;
        var btn = p.querySelector('.selected-btn-content');
        if (btn) {
            btn.click();
            var r = btn.getBoundingClientRect();
            var text = (btn.innerText || '').trim();
            return {text: text, x: Math.round(r.x), y: Math.round(r.y)};
        }
        return null;
    }""")
    print(f"  Model selector clicked: {model}", flush=True)
    page.wait_for_timeout(2000)
    ss(page, "P78_06_model_selector")

    # Check for style list panel overlay
    style_panel = page.evaluate("""() => {
        var sp = document.querySelector('.style-list-panel');
        if (sp) {
            var r = sp.getBoundingClientRect();
            return {
                x: Math.round(r.x), y: Math.round(r.y),
                w: Math.round(r.width), h: Math.round(r.height),
                visible: r.width > 0,
            };
        }
        return null;
    }""")
    print(f"  Style list panel: {style_panel}", flush=True)

    page.keyboard.press("Escape")
    page.wait_for_timeout(500)

    print(f"\n\n===== PHASE 78 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
