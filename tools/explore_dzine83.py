"""Phase 83: Remaining gaps.
1. Video Editor panel (toggle from distant tool, check if different from Lip Sync)
2. Enhance & Upscale panel workflow
3. Layer toolbar tools (crop, flip, 3D, etc.)
4. Text layer capabilities
5. Assets panel management
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


def wait_for_canvas(page, max_wait=40):
    for i in range(max_wait):
        loaded = page.evaluate("() => document.querySelectorAll('.tool-group').length")
        if loaded >= 5:
            print(f"  Canvas loaded ({loaded} tool groups) after {i+1}s", flush=True)
            page.wait_for_timeout(2000)
            return True
        page.wait_for_timeout(1000)
    return False


def open_panel(page, target_x, target_y, panel_name=""):
    page.mouse.click(40, 766)  # Storyboard
    page.wait_for_timeout(2000)
    close_dialogs(page)
    page.mouse.move(700, 450)
    page.wait_for_timeout(500)
    page.mouse.click(target_x, target_y)
    page.wait_for_timeout(3000)
    close_dialogs(page)
    title = page.evaluate("""() => {
        var p = document.querySelector('.c-gen-config.show') ||
                document.querySelector('.panels.show');
        if (!p) return 'NONE';
        var h5 = p.querySelector('h5');
        return h5 ? (h5.innerText || '').trim() : 'no h5';
    }""")
    print(f"  Opened '{panel_name}': title='{title}'", flush=True)
    return title


def dismiss_popups(page):
    page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            if (text === 'Skip' && el.getBoundingClientRect().width > 20) {
                el.click(); return;
            }
        }
    }""")
    page.wait_for_timeout(500)
    close_dialogs(page)


def dump_panel(page, label, limit=50):
    """Dump whatever panel is currently showing."""
    items = page.evaluate(f"""() => {{
        var p = document.querySelector('.c-gen-config.show') ||
                document.querySelector('.panels.show');
        if (!p) return [];
        var items = [];
        var excluded = ['path','line','circle','g','svg','defs','rect','polygon',
                        'clippath','HTML','BODY','HEAD','SCRIPT','STYLE','META','LINK'];
        var seen = new Set();
        for (const el of p.querySelectorAll('*')) {{
            var r = el.getBoundingClientRect();
            if (r.width > 10 && r.height > 10 && r.width < 300
                && !excluded.includes(el.tagName.toUpperCase())) {{
                var text = (el.innerText || '').trim();
                if (text.length > 0 && text.length < 50 && text.indexOf('\\n') === -1) {{
                    var key = el.tagName + '|' + Math.round(r.x) + '|' + Math.round(r.y);
                    if (!seen.has(key)) {{
                        seen.add(key);
                        items.push({{
                            tag: el.tagName, x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height),
                            text: text.substring(0, 40),
                            classes: (el.className || '').toString().substring(0, 30),
                        }});
                    }}
                }}
            }}
        }}
        return items.sort(function(a,b) {{ return a.y - b.y; }}).slice(0, {limit});
    }}""")
    title = page.evaluate("""() => {
        var p = document.querySelector('.c-gen-config.show') ||
                document.querySelector('.panels.show');
        if (!p) return 'NONE';
        var h5 = p.querySelector('h5');
        return h5 ? (h5.innerText || '').trim() : 'no h5';
    }""")
    print(f"\n  {label} — title='{title}' ({len(items)} elements):", flush=True)
    for el in items:
        print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> c='{el['classes'][:22]}' '{el['text'][:35]}'", flush=True)
    return items


def main():
    print("Connecting...", flush=True)
    pw = sync_playwright().start()
    browser = pw.chromium.connect_over_cdp("http://127.0.0.1:18800", timeout=15000)
    ctx = browser.contexts[0]
    page = ctx.new_page()
    page.set_viewport_size({"width": 1440, "height": 900})

    page.goto(CANVAS_URL, wait_until="domcontentloaded", timeout=30000)
    print("  Waiting for canvas...", flush=True)
    wait_for_canvas(page)
    close_dialogs(page)

    # ============================================================
    #  PART 1: VIDEO EDITOR PANEL (distinct from Lip Sync?)
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 1: VIDEO EDITOR PANEL", flush=True)
    print("=" * 60, flush=True)

    open_panel(page, 40, 490, "Video Editor")
    dismiss_popups(page)
    ss(page, "P83_01_video_editor")
    dump_panel(page, "Video Editor")

    # Also check panel class specifically
    ve_class = page.evaluate("""() => {
        var p = document.querySelector('.c-gen-config.show') ||
                document.querySelector('.panels.show');
        if (!p) return null;
        return (p.className || '').toString().substring(0, 80);
    }""")
    print(f"  Video Editor panel class: {ve_class}", flush=True)

    # ============================================================
    #  PART 2: ENHANCE & UPSCALE PANEL
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 2: ENHANCE & UPSCALE PANEL", flush=True)
    print("=" * 60, flush=True)

    open_panel(page, 40, 627, "Enhance & Upscale")
    dismiss_popups(page)
    ss(page, "P83_02_enhance")
    dump_panel(page, "Enhance & Upscale")

    # Check for model selector
    enh_model = page.evaluate("""() => {
        var p = document.querySelector('.c-gen-config.show') ||
                document.querySelector('.panels.show');
        if (!p) return null;
        var btn = p.querySelector('.selected-btn-content');
        if (btn) {
            var r = btn.getBoundingClientRect();
            return {text: (btn.innerText || '').trim().substring(0, 40),
                    x: Math.round(r.x), y: Math.round(r.y)};
        }
        return null;
    }""")
    print(f"  Enhance model selector: {enh_model}", flush=True)

    # ============================================================
    #  PART 3: LAYER TOOLBAR (top bar when layer selected)
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 3: LAYER TOOLBAR TOOLS", flush=True)
    print("=" * 60, flush=True)

    # The toolbar appears at y~65 when a layer is selected
    # First, click on a result image to select it on canvas
    # Click on the canvas area where an image should be
    page.mouse.click(600, 400)
    page.wait_for_timeout(1000)

    # Check if layer toolbar is active
    toolbar = page.evaluate("""() => {
        var lt = document.querySelector('.layer-tools');
        if (!lt) return null;
        var r = lt.getBoundingClientRect();
        var classes = (lt.className || '').toString();
        var disabled = classes.includes('disabled');
        // Get all buttons in toolbar
        var buttons = [];
        for (var btn of lt.querySelectorAll('button, .item')) {
            var br = btn.getBoundingClientRect();
            var text = (btn.innerText || '').trim();
            var title = btn.getAttribute('title') || '';
            if (br.width > 0) {
                buttons.push({
                    text: text || title,
                    x: Math.round(br.x), y: Math.round(br.y),
                    w: Math.round(br.width), h: Math.round(br.height),
                    classes: (btn.className || '').toString().substring(0, 30),
                    disabled: (btn.className || '').includes('disabled'),
                });
            }
        }
        return {
            x: Math.round(r.x), y: Math.round(r.y),
            w: Math.round(r.width), h: Math.round(r.height),
            disabled: disabled,
            classes: classes.substring(0, 50),
            buttons: buttons,
        };
    }""")
    print(f"  Layer toolbar: disabled={toolbar.get('disabled') if toolbar else 'null'}, {toolbar.get('classes', '')[:40] if toolbar else ''}", flush=True)
    if toolbar and toolbar.get('buttons'):
        print(f"\n  Toolbar buttons ({len(toolbar['buttons'])}):", flush=True)
        for b in toolbar['buttons']:
            print(f"    ({b['x']},{b['y']}) {b['w']}x{b['h']} c='{b['classes'][:20]}' '{b['text'][:30]}' disabled={b['disabled']}", flush=True)

    # Try selecting a layer by clicking on the canvas image
    # First check for visible layers
    layers = page.evaluate("""() => {
        var items = [];
        for (var el of document.querySelectorAll('.layer-item, [class*="layer-item"]')) {
            var r = el.getBoundingClientRect();
            var text = (el.innerText || '').trim().substring(0, 30);
            if (r.width > 0) {
                items.push({
                    text: text, x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    classes: (el.className || '').toString().substring(0, 30),
                });
            }
        }
        return items;
    }""")
    print(f"\n  Layer items ({len(layers)}):", flush=True)
    for l in layers:
        print(f"    ({l['x']},{l['y']}) {l['w']}x{l['h']} c='{l['classes'][:20]}' '{l['text'][:25]}'", flush=True)

    # Click a canvas element to try to select it
    page.mouse.click(700, 300)
    page.wait_for_timeout(1000)
    ss(page, "P83_03_layer_selected")

    # Recheck toolbar after clicking canvas
    toolbar2 = page.evaluate("""() => {
        var lt = document.querySelector('.layer-tools');
        if (!lt) return null;
        var r = lt.getBoundingClientRect();
        var classes = (lt.className || '').toString();
        var disabled = classes.includes('disabled');
        var buttons = [];
        for (var btn of lt.querySelectorAll('button, .item')) {
            var br = btn.getBoundingClientRect();
            var text = (btn.innerText || '').trim();
            var title = btn.getAttribute('title') || '';
            if (br.width > 0 && br.height > 10) {
                buttons.push({
                    text: text || title,
                    x: Math.round(br.x), y: Math.round(br.y),
                    w: Math.round(br.width), h: Math.round(br.height),
                    classes: (btn.className || '').toString().substring(0, 30),
                    disabled: (btn.className || '').includes('disabled'),
                });
            }
        }
        return {disabled: disabled, buttons: buttons};
    }""")
    if toolbar2:
        print(f"\n  Toolbar after click: disabled={toolbar2['disabled']}, {len(toolbar2['buttons'])} buttons:", flush=True)
        for b in toolbar2['buttons']:
            print(f"    ({b['x']},{b['y']}) {b['w']}x{b['h']} c='{b['classes'][:20]}' '{b['text'][:30]}' disabled={b['disabled']}", flush=True)

    # ============================================================
    #  PART 4: TEXT TOOL
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 4: TEXT TOOL", flush=True)
    print("=" * 60, flush=True)

    # Press T to activate text tool
    page.keyboard.press("t")
    page.wait_for_timeout(1000)

    # Check what happened
    text_state = page.evaluate("""() => {
        // Check for text cursor or text tool state
        var items = [];
        for (var el of document.querySelectorAll('[class*="text-tool"], [class*="text-panel"], [class*="font"]')) {
            var r = el.getBoundingClientRect();
            if (r.width > 0) {
                items.push({
                    tag: el.tagName,
                    classes: (el.className || '').toString().substring(0, 40),
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    text: (el.innerText || '').trim().substring(0, 30),
                });
            }
        }
        return items;
    }""")
    print(f"  Text tool elements ({len(text_state)}):", flush=True)
    for t in text_state:
        print(f"    ({t['x']},{t['y']}) {t['w']}x{t['h']} <{t['tag']}> c='{t['classes'][:30]}' '{t['text']}'", flush=True)

    # Click on canvas to create a text box
    page.mouse.click(500, 400)
    page.wait_for_timeout(1500)
    ss(page, "P83_04_text_tool")

    # Check for text editing UI
    text_ui = page.evaluate("""() => {
        var items = [];
        var seen = new Set();
        // Check for font selectors, size inputs, color pickers
        for (var el of document.querySelectorAll('select, [class*="font"], [class*="text"], [class*="color"]')) {
            var r = el.getBoundingClientRect();
            var text = (el.innerText || '').trim().substring(0, 30);
            if (r.width > 20 && r.height > 10 && r.x > 60 && r.x < 1200) {
                var key = (el.className || '').toString().substring(0, 20) + '|' + Math.round(r.y);
                if (!seen.has(key)) {
                    seen.add(key);
                    items.push({
                        tag: el.tagName,
                        classes: (el.className || '').toString().substring(0, 40),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        text: text,
                    });
                }
            }
        }
        return items.sort(function(a,b) { return a.y - b.y; }).slice(0, 20);
    }""")
    print(f"\n  Text UI elements ({len(text_ui)}):", flush=True)
    for t in text_ui:
        print(f"    ({t['x']},{t['y']}) {t['w']}x{t['h']} <{t['tag']}> c='{t['classes'][:30]}' '{t['text']}'", flush=True)

    # Check if a text layer panel appeared
    text_panel = page.evaluate("""() => {
        var p = document.querySelector('.panels.show');
        if (p) {
            var h5 = p.querySelector('h5');
            var title = h5 ? (h5.innerText || '').trim() : '';
            if (title.toLowerCase().includes('text')) return title;
        }
        // Check for text editing toolbar
        var items = [];
        for (var el of document.querySelectorAll('.layer-tools *')) {
            var r = el.getBoundingClientRect();
            var text = (el.innerText || '').trim();
            if (text.length > 0 && text.length < 20 && r.width > 0 && r.height > 10) {
                items.push(text);
            }
        }
        return items.length > 0 ? items.join(' | ') : null;
    }""")
    print(f"  Text panel/toolbar: {text_panel}", flush=True)

    # Press Escape to exit text mode
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)

    # ============================================================
    #  PART 5: ASSETS PANEL
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 5: ASSETS PANEL MANAGEMENT", flush=True)
    print("=" * 60, flush=True)

    open_panel(page, 40, 136, "Assets")
    dismiss_popups(page)
    ss(page, "P83_05_assets")
    dump_panel(page, "Assets panel")

    # Check for folder navigation
    folders = page.evaluate("""() => {
        var p = document.querySelector('.panels.show') ||
                document.querySelector('.c-gen-config.show');
        if (!p) return [];
        var items = [];
        for (var el of p.querySelectorAll('[class*="folder"], [class*="category"], [class*="tab"]')) {
            var r = el.getBoundingClientRect();
            var text = (el.innerText || '').trim();
            if (text.length > 0 && text.length < 30 && r.width > 0) {
                items.push({
                    text: text, tag: el.tagName,
                    classes: (el.className || '').toString().substring(0, 30),
                    x: Math.round(r.x), y: Math.round(r.y),
                });
            }
        }
        return items;
    }""")
    print(f"\n  Asset folders ({len(folders)}):", flush=True)
    for f in folders:
        print(f"    ({f['x']},{f['y']}) <{f['tag']}> c='{f['classes'][:22]}' '{f['text']}'", flush=True)

    # ============================================================
    #  PART 6: TOP TOOLBAR COMPREHENSIVE DUMP
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 6: TOP TOOLBAR / HEADER BAR", flush=True)
    print("=" * 60, flush=True)

    header = page.evaluate("""() => {
        var h = document.querySelector('.c-header');
        if (!h) return [];
        var items = [];
        var seen = new Set();
        for (var el of h.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            var text = (el.innerText || '').trim();
            if (text.length > 0 && text.length < 30 && r.width > 0 && r.height > 8
                && r.height < 40 && r.width < 200) {
                var key = text + '|' + Math.round(r.x);
                if (!seen.has(key)) {
                    seen.add(key);
                    items.push({
                        text: text, tag: el.tagName,
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        classes: (el.className || '').toString().substring(0, 30),
                    });
                }
            }
        }
        return items.sort(function(a,b) { return a.x - b.x; }).slice(0, 30);
    }""")
    print(f"\n  Header bar ({len(header)}):", flush=True)
    for h in header:
        print(f"    x={h['x']} ({h['w']}x{h['h']}) <{h['tag']}> c='{h['classes'][:20]}' '{h['text']}'", flush=True)

    # Also check for keyboard shortcut panel
    # Try pressing ? or Ctrl+/
    page.keyboard.press("?")
    page.wait_for_timeout(1000)
    shortcut_panel = page.evaluate("""() => {
        for (var el of document.querySelectorAll('*')) {
            var cs = window.getComputedStyle(el);
            var z = parseInt(cs.zIndex) || 0;
            var r = el.getBoundingClientRect();
            if (z > 500 && r.width > 200 && r.height > 200 && r.x > 100) {
                return {
                    classes: (el.className || '').toString().substring(0, 50),
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    text: (el.innerText || '').trim().substring(0, 200),
                };
            }
        }
        return null;
    }""")
    print(f"\n  Shortcut panel: {shortcut_panel}", flush=True)
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)

    # ============================================================
    #  PART 7: RIGHT-CLICK CONTEXT MENU
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 7: RIGHT-CLICK CONTEXT MENU", flush=True)
    print("=" * 60, flush=True)

    # Right-click on canvas
    page.mouse.click(600, 400, button="right")
    page.wait_for_timeout(1000)
    ss(page, "P83_06_context_menu")

    ctx_menu = page.evaluate("""() => {
        var items = [];
        for (var el of document.querySelectorAll('*')) {
            var cs = window.getComputedStyle(el);
            var z = parseInt(cs.zIndex) || 0;
            var r = el.getBoundingClientRect();
            if (z > 500 && r.width > 60 && r.height > 30 && r.width < 400) {
                var text = (el.innerText || '').trim().replace(/\\n/g, ' | ').substring(0, 150);
                if (text.length > 3) {
                    items.push({
                        z: z, tag: el.tagName,
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        classes: (el.className || '').toString().substring(0, 40),
                        text: text.substring(0, 120),
                    });
                }
            }
        }
        return items.sort(function(a,b) { return b.z - a.z; }).slice(0, 5);
    }""")
    print(f"\n  Context menu ({len(ctx_menu)}):", flush=True)
    for c in ctx_menu:
        print(f"    z={c['z']} ({c['x']},{c['y']}) {c['w']}x{c['h']} c='{c['classes'][:30]}' '{c['text'][:100]}'", flush=True)

    if ctx_menu:
        # Get individual menu items
        cm = ctx_menu[0]
        menu_items = page.evaluate(f"""() => {{
            var items = [];
            var seen = new Set();
            for (var el of document.querySelectorAll('*')) {{
                var r = el.getBoundingClientRect();
                if (r.x >= {cm['x']} && r.x <= {cm['x'] + cm['w']}
                    && r.y >= {cm['y']} && r.y <= {cm['y'] + cm['h']}
                    && r.width > 20 && r.height > 10 && r.height < 40) {{
                    var text = (el.innerText || '').trim();
                    if (text.length > 0 && text.length < 30 && !seen.has(text)) {{
                        seen.add(text);
                        items.push({{
                            text: text, tag: el.tagName,
                            x: Math.round(r.x), y: Math.round(r.y),
                            classes: (el.className || '').toString().substring(0, 25),
                        }});
                    }}
                }}
            }}
            return items.sort(function(a,b) {{ return a.y - b.y; }}).slice(0, 20);
        }}""")
        print(f"\n  Menu items ({len(menu_items)}):", flush=True)
        for m in menu_items:
            print(f"    y={m['y']} <{m['tag']}> c='{m['classes'][:20]}' '{m['text']}'", flush=True)

    page.keyboard.press("Escape")
    page.wait_for_timeout(300)

    print(f"\n\n===== PHASE 83 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
