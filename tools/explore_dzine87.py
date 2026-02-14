"""Phase 87: Deeper interactions.
1. Select a canvas layer, then open Export dialog
2. Chat editor — click model param to see model selector in chat
3. Img2Img style selector — open from the c-gen-config panel (not panels.show)
4. Face Swap panel via Image Editor
5. AI Eraser / Local Edit panel interaction
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


def close_all_overlays(page):
    for _ in range(3):
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
    page.evaluate("""() => {
        var c1 = document.querySelector('.c-gen-config.show .ico-close');
        if (c1) c1.click();
        var c2 = document.querySelector('.panels.show .ico-close');
        if (c2) c2.click();
    }""")
    page.wait_for_timeout(500)
    close_dialogs(page)
    page.mouse.click(700, 450)
    page.wait_for_timeout(500)


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


def cleanup_tabs(ctx):
    pages = ctx.pages
    print(f"  Found {len(pages)} open tabs", flush=True)
    kept = False
    for p in pages:
        url = p.url or ""
        if "dzine.ai" in url:
            if kept:
                try:
                    p.close()
                except Exception:
                    pass
            else:
                kept = True
        elif url in ("", "about:blank", "chrome://newtab/"):
            try:
                p.close()
            except Exception:
                pass
    print(f"  Tabs after cleanup: {len(ctx.pages)}", flush=True)


def dump_high_z(page, label, min_z=50, limit=40):
    items = page.evaluate(f"""() => {{
        var containers = [];
        for (var el of document.querySelectorAll('*')) {{
            var cs = window.getComputedStyle(el);
            var z = parseInt(cs.zIndex) || 0;
            var r = el.getBoundingClientRect();
            if (z > {min_z} && r.width > 100 && r.height > 50) {{
                containers.push({{el: el, z: z, r: r}});
            }}
        }}
        // Sort by z desc, take top container
        containers.sort(function(a,b) {{ return b.z - a.z; }});
        if (containers.length === 0) return [];
        var top = containers[0];
        var items = [];
        var seen = new Set();
        for (var child of top.el.querySelectorAll('*')) {{
            var cr = child.getBoundingClientRect();
            var text = (child.innerText || '').trim();
            if (text.length > 0 && text.length < 60 && cr.width > 10
                && cr.height > 8 && cr.height < 60 && cr.width < 400
                && text.indexOf('\\n') === -1) {{
                var key = text + '|' + Math.round(cr.y);
                if (!seen.has(key)) {{
                    seen.add(key);
                    items.push({{
                        tag: child.tagName, x: Math.round(cr.x), y: Math.round(cr.y),
                        w: Math.round(cr.width), h: Math.round(cr.height),
                        text: text.substring(0, 50),
                        classes: (child.className || '').toString().substring(0, 30),
                        z: top.z,
                    }});
                }}
            }}
        }}
        return items.sort(function(a,b) {{ return a.y - b.y; }}).slice(0, {limit});
    }}""")
    print(f"\n  {label} ({len(items)} elements):", flush=True)
    for el in items:
        print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} z={el['z']} <{el['tag']}> c='{el['classes'][:22]}' '{el['text'][:40]}'", flush=True)
    return items


def main():
    print("Connecting...", flush=True)
    pw = sync_playwright().start()
    browser = pw.chromium.connect_over_cdp("http://127.0.0.1:18800", timeout=15000)
    ctx = browser.contexts[0]
    cleanup_tabs(ctx)

    page = ctx.new_page()
    page.set_viewport_size({"width": 1440, "height": 900})

    page.goto(CANVAS_URL, wait_until="domcontentloaded", timeout=30000)
    print("  Waiting for canvas...", flush=True)
    wait_for_canvas(page)
    close_dialogs(page)

    # ============================================================
    #  PART 1: SELECT LAYER + EXPORT DIALOG
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 1: SELECT LAYER + EXPORT", flush=True)
    print("=" * 60, flush=True)

    close_all_overlays(page)
    page.wait_for_timeout(500)

    # Open Layers panel
    page.evaluate("() => document.querySelector('.header-item.item-layers')?.click()")
    page.wait_for_timeout(1000)

    # Click on Layer 1 (the first image layer) to select it on canvas
    selected = page.evaluate("""() => {
        // Find layer items in the right panel
        var layers = document.querySelectorAll('.name-c');
        for (var l of layers) {
            if ((l.innerText || '').trim() === 'Layer 1') {
                // Click the parent (layer row)
                var parent = l.closest('[class*="layer-item"]') || l.parentElement;
                if (parent) parent.click();
                else l.click();
                return 'Layer 1';
            }
        }
        // If no named layers found, try clicking any layer
        if (layers.length > 0) {
            var parent = layers[0].closest('[class*="layer-item"]') || layers[0].parentElement;
            if (parent) parent.click();
            else layers[0].click();
            return (layers[0].innerText || '').trim();
        }
        return null;
    }""")
    print(f"  Selected layer: {selected}", flush=True)
    page.wait_for_timeout(1000)

    # Also click on the canvas to ensure a layer is visually selected
    # Try clicking on a visible layer on the canvas (center-ish area)
    page.mouse.click(700, 400)
    page.wait_for_timeout(500)

    # Check if something is selected (look for selection handles)
    has_selection = page.evaluate("""() => {
        // Check for transform handles/selection boxes
        var sel = document.querySelector('.konvajs-content');
        if (sel) return 'konva canvas found';
        // Check for selection indicator
        var handles = document.querySelectorAll('[class*="select"], [class*="handle"]');
        return handles.length > 0 ? handles.length + ' handles' : 'no selection';
    }""")
    print(f"  Selection state: {has_selection}", flush=True)

    # Now click Export
    page.evaluate("() => document.querySelector('.c-export')?.click()")
    page.wait_for_timeout(2000)
    ss(page, "P87_01_export_with_layer")

    # Dump everything that appeared
    export = page.evaluate("""() => {
        var results = [];
        // Look for ANY new visible overlay/dialog
        var allElements = [];
        for (var el of document.querySelectorAll('*')) {
            var cs = window.getComputedStyle(el);
            var z = parseInt(cs.zIndex) || 0;
            var r = el.getBoundingClientRect();
            if (z > 50 && r.width > 100 && r.height > 100) {
                allElements.push({
                    tag: el.tagName, z: z,
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    classes: (el.className || '').toString().substring(0, 80),
                    children: el.children.length,
                });
            }
        }
        return allElements.sort(function(a,b) { return b.z - a.z; }).slice(0, 10);
    }""")
    print(f"\n  All high-z elements ({len(export)}):", flush=True)
    for e in export:
        print(f"    z={e['z']} ({e['x']},{e['y']}) {e['w']}x{e['h']} <{e['tag']}> ch={e['children']} c='{e['classes'][:50]}'", flush=True)

    # Check if the Export is actually a popover/dropdown appended near the button
    export_popup = page.evaluate("""() => {
        // Look for elements that appeared near the export button area
        var items = [];
        var seen = new Set();
        for (var el of document.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            var cs = window.getComputedStyle(el);
            var display = cs.display;
            var vis = cs.visibility;
            if (r.x > 900 && r.y < 400 && r.width > 80 && r.height > 30
                && r.height < 50 && display !== 'none' && vis !== 'hidden') {
                var text = (el.innerText || '').trim();
                if (text.length > 0 && text.length < 30 && text.indexOf('\\n') === -1) {
                    var key = text + '|' + Math.round(r.y);
                    if (!seen.has(key)) {
                        seen.add(key);
                        items.push({
                            tag: el.tagName, x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height),
                            text: text,
                            classes: (el.className || '').toString().substring(0, 30),
                        });
                    }
                }
            }
        }
        return items.sort(function(a,b) { return a.y - b.y; }).slice(0, 20);
    }""")
    print(f"\n  Near Export area ({len(export_popup)}):", flush=True)
    for e in export_popup:
        print(f"    ({e['x']},{e['y']}) {e['w']}x{e['h']} <{e['tag']}> c='{e['classes'][:22]}' '{e['text']}'", flush=True)

    # Check the show-message content (the toast that appeared last time)
    toast = page.evaluate("""() => {
        var msg = document.querySelector('.show-message');
        if (!msg) return null;
        var r = msg.getBoundingClientRect();
        return {
            text: (msg.innerText || '').trim().substring(0, 100),
            x: Math.round(r.x), y: Math.round(r.y),
            w: Math.round(r.width), h: Math.round(r.height),
        };
    }""")
    print(f"\n  Toast message: {toast}", flush=True)

    page.keyboard.press("Escape")
    page.wait_for_timeout(500)

    # ============================================================
    #  PART 2: CHAT EDITOR — MODEL SELECTOR
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 2: CHAT MODEL SELECTOR", flush=True)
    print("=" * 60, flush=True)

    close_all_overlays(page)
    page.wait_for_timeout(500)

    # Open chat editor
    page.mouse.click(628, 824)
    page.wait_for_timeout(2000)

    # Click the model param
    page.evaluate("""() => {
        var param = document.querySelector('.chat-param');
        if (param) param.click();
    }""")
    page.wait_for_timeout(2000)
    ss(page, "P87_02_chat_model")

    # Check for model selector in chat
    chat_models = page.evaluate("""() => {
        // Look for a model selector overlay near the chat panel
        var wrapper = document.querySelector('.chat-editor-panel-wrapper');
        if (!wrapper) return {wrapper: false};

        var items = [];
        var seen = new Set();
        // Scan the wrapper and nearby high-z elements
        for (var el of document.querySelectorAll('*')) {
            var cs = window.getComputedStyle(el);
            var z = parseInt(cs.zIndex) || 0;
            var r = el.getBoundingClientRect();
            if (z > 100 && r.width > 200 && r.height > 100 && r.y > 300) {
                for (var child of el.querySelectorAll('*')) {
                    var cr = child.getBoundingClientRect();
                    var text = (child.innerText || '').trim();
                    if (text.length > 0 && text.length < 50 && cr.width > 10
                        && cr.height > 8 && cr.height < 50 && cr.width < 300
                        && text.indexOf('\\n') === -1) {
                        var key = text + '|' + Math.round(cr.y);
                        if (!seen.has(key)) {
                            seen.add(key);
                            items.push({
                                tag: child.tagName, x: Math.round(cr.x), y: Math.round(cr.y),
                                w: Math.round(cr.width), h: Math.round(cr.height),
                                text: text.substring(0, 40),
                                classes: (child.className || '').toString().substring(0, 30),
                            });
                        }
                    }
                }
                break;
            }
        }
        return {wrapper: true, items: items.sort(function(a,b) { return a.y - b.y; }).slice(0, 30)};
    }""")
    print(f"\n  Chat model selector:", flush=True)
    if chat_models.get('items'):
        for m in chat_models['items']:
            print(f"    ({m['x']},{m['y']}) {m['w']}x{m['h']} <{m['tag']}> c='{m['classes'][:22]}' '{m['text']}'", flush=True)
    else:
        print(f"  wrapper={chat_models.get('wrapper')}, no items", flush=True)

    # Also check if the chat-param click opened a dropdown within the panel
    chat_dropdown = page.evaluate("""() => {
        var wrapper = document.querySelector('.chat-editor-panel-wrapper');
        if (!wrapper) return null;
        var r = wrapper.getBoundingClientRect();
        var items = [];
        var seen = new Set();
        for (var child of wrapper.querySelectorAll('*')) {
            var cr = child.getBoundingClientRect();
            var text = (child.innerText || '').trim();
            if (text.length > 0 && text.length < 50 && cr.width > 10
                && cr.height > 8 && text.indexOf('\\n') === -1) {
                var key = text + '|' + Math.round(cr.y) + '|' + Math.round(cr.x);
                if (!seen.has(key)) {
                    seen.add(key);
                    items.push({
                        tag: child.tagName, x: Math.round(cr.x), y: Math.round(cr.y),
                        w: Math.round(cr.width), h: Math.round(cr.height),
                        text: text.substring(0, 40),
                        classes: (child.className || '').toString().substring(0, 30),
                    });
                }
            }
        }
        return {
            bounds: {x: Math.round(r.x), y: Math.round(r.y),
                     w: Math.round(r.width), h: Math.round(r.height)},
            items: items.sort(function(a,b) { return a.y - b.y; }).slice(0, 30),
        };
    }""")
    if chat_dropdown:
        print(f"\n  Chat panel bounds: {chat_dropdown['bounds']}", flush=True)
        print(f"  Chat panel items ({len(chat_dropdown.get('items', []))}):", flush=True)
        for c in chat_dropdown.get('items', []):
            print(f"    ({c['x']},{c['y']}) {c['w']}x{c['h']} <{c['tag']}> c='{c['classes'][:22]}' '{c['text']}'", flush=True)

    page.keyboard.press("Escape")
    page.wait_for_timeout(500)

    # ============================================================
    #  PART 3: IMAGE EDITOR TOOLS (detailed)
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 3: IMAGE EDITOR", flush=True)
    print("=" * 60, flush=True)

    close_all_overlays(page)
    page.wait_for_timeout(500)

    # Open Image Editor panel
    page.mouse.click(40, 766)  # Storyboard first
    page.wait_for_timeout(2000)
    close_dialogs(page)
    page.mouse.move(700, 450)
    page.wait_for_timeout(300)
    page.mouse.click(40, 698)  # Image Editor
    page.wait_for_timeout(3000)
    close_dialogs(page)
    dismiss_popups(page)

    # Dump the Image Editor panel
    ie_panel = page.evaluate("""() => {
        var p = document.querySelector('.panels.show');
        if (!p) return null;
        var r = p.getBoundingClientRect();
        var items = [];
        var seen = new Set();
        for (var child of p.querySelectorAll('*')) {
            var cr = child.getBoundingClientRect();
            var text = (child.innerText || '').trim();
            if (text.length > 0 && text.length < 50 && cr.width > 10 && cr.height > 8
                && cr.width < 300 && text.indexOf('\\n') === -1) {
                var key = child.tagName + '|' + Math.round(cr.y) + '|' + text;
                if (!seen.has(key)) {
                    seen.add(key);
                    items.push({
                        tag: child.tagName, x: Math.round(cr.x), y: Math.round(cr.y),
                        w: Math.round(cr.width), h: Math.round(cr.height),
                        text: text.substring(0, 40),
                        classes: (child.className || '').toString().substring(0, 30),
                    });
                }
            }
        }
        var h5 = p.querySelector('h5');
        return {
            title: h5 ? (h5.innerText || '').trim() : 'no h5',
            bounds: {x: Math.round(r.x), y: Math.round(r.y),
                     w: Math.round(r.width), h: Math.round(r.height)},
            items: items.sort(function(a,b) { return a.y - b.y; }).slice(0, 30),
        };
    }""")
    if ie_panel:
        print(f"  Image Editor: '{ie_panel['title']}'", flush=True)
        print(f"  Items ({len(ie_panel.get('items', []))}):", flush=True)
        for item in ie_panel.get('items', []):
            print(f"    ({item['x']},{item['y']}) {item['w']}x{item['h']} <{item['tag']}> c='{item['classes'][:22]}' '{item['text']}'", flush=True)
    ss(page, "P87_03_image_editor")

    # Click "Local Edit" to see its sub-panel
    page.evaluate("""() => {
        var p = document.querySelector('.panels.show');
        if (!p) return;
        for (var el of p.querySelectorAll('*')) {
            if ((el.innerText || '').trim() === 'Local Edit') {
                el.click(); return;
            }
        }
    }""")
    page.wait_for_timeout(2000)
    close_dialogs(page)
    dismiss_popups(page)
    ss(page, "P87_04_local_edit")

    # Dump Local Edit sub-panel
    local_edit = page.evaluate("""() => {
        var p = document.querySelector('.c-gen-config.show') ||
                document.querySelector('.panels.show');
        if (!p) return null;
        var r = p.getBoundingClientRect();
        var items = [];
        var seen = new Set();
        for (var child of p.querySelectorAll('*')) {
            var cr = child.getBoundingClientRect();
            var text = (child.innerText || '').trim();
            if (text.length > 0 && text.length < 50 && cr.width > 10 && cr.height > 8
                && cr.width < 300 && text.indexOf('\\n') === -1) {
                var key = child.tagName + '|' + Math.round(cr.y) + '|' + text;
                if (!seen.has(key)) {
                    seen.add(key);
                    items.push({
                        tag: child.tagName, x: Math.round(cr.x), y: Math.round(cr.y),
                        w: Math.round(cr.width), h: Math.round(cr.height),
                        text: text.substring(0, 40),
                        classes: (child.className || '').toString().substring(0, 30),
                    });
                }
            }
        }
        var h5 = p.querySelector('h5');
        return {
            title: h5 ? (h5.innerText || '').trim() : 'no h5',
            panelClass: (p.className || '').toString().substring(0, 60),
            items: items.sort(function(a,b) { return a.y - b.y; }).slice(0, 30),
        };
    }""")
    if local_edit:
        print(f"\n  Local Edit: '{local_edit['title']}' class='{local_edit['panelClass']}'", flush=True)
        print(f"  Items ({len(local_edit.get('items', []))}):", flush=True)
        for item in local_edit.get('items', []):
            print(f"    ({item['x']},{item['y']}) {item['w']}x{item['h']} <{item['tag']}> c='{item['classes'][:22]}' '{item['text']}'", flush=True)

    # ============================================================
    #  PART 4: UPLOAD PANEL
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 4: UPLOAD PANEL", flush=True)
    print("=" * 60, flush=True)

    close_all_overlays(page)
    page.wait_for_timeout(500)

    # Click Upload icon
    page.mouse.click(40, 81)
    page.wait_for_timeout(2000)
    close_dialogs(page)
    ss(page, "P87_05_upload")

    upload_panel = page.evaluate("""() => {
        var p = document.querySelector('.panels.show');
        if (!p) return null;
        var r = p.getBoundingClientRect();
        var items = [];
        var seen = new Set();
        for (var child of p.querySelectorAll('*')) {
            var cr = child.getBoundingClientRect();
            var text = (child.innerText || '').trim();
            if (text.length > 0 && text.length < 50 && cr.width > 10 && cr.height > 8
                && cr.width < 300 && text.indexOf('\\n') === -1) {
                var key = child.tagName + '|' + Math.round(cr.y) + '|' + text;
                if (!seen.has(key)) {
                    seen.add(key);
                    items.push({
                        tag: child.tagName, x: Math.round(cr.x), y: Math.round(cr.y),
                        w: Math.round(cr.width), h: Math.round(cr.height),
                        text: text.substring(0, 40),
                        classes: (child.className || '').toString().substring(0, 30),
                    });
                }
            }
        }
        var h5 = p.querySelector('h5');
        return {
            title: h5 ? (h5.innerText || '').trim() : 'no h5',
            items: items.sort(function(a,b) { return a.y - b.y; }).slice(0, 20),
        };
    }""")
    if upload_panel:
        print(f"  Upload: '{upload_panel['title']}'", flush=True)
        print(f"  Items ({len(upload_panel.get('items', []))}):", flush=True)
        for item in upload_panel.get('items', []):
            print(f"    ({item['x']},{item['y']}) {item['w']}x{item['h']} <{item['tag']}> c='{item['classes'][:22]}' '{item['text']}'", flush=True)

    # ============================================================
    #  PART 5: CHARACTER PANEL (detailed)
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 5: CHARACTER PANEL", flush=True)
    print("=" * 60, flush=True)

    close_all_overlays(page)
    page.wait_for_timeout(500)

    # Open Character
    page.mouse.click(40, 766)
    page.wait_for_timeout(2000)
    close_dialogs(page)
    page.mouse.move(700, 450)
    page.wait_for_timeout(300)
    page.mouse.click(40, 306)
    page.wait_for_timeout(3000)
    close_dialogs(page)
    dismiss_popups(page)
    ss(page, "P87_06_character")

    char_panel = page.evaluate("""() => {
        var p = document.querySelector('.panels.show');
        if (!p) return null;
        var r = p.getBoundingClientRect();
        var items = [];
        var seen = new Set();
        for (var child of p.querySelectorAll('*')) {
            var cr = child.getBoundingClientRect();
            var text = (child.innerText || '').trim();
            if (text.length > 0 && text.length < 50 && cr.width > 10 && cr.height > 8
                && cr.width < 300 && text.indexOf('\\n') === -1) {
                var key = child.tagName + '|' + Math.round(cr.y) + '|' + text;
                if (!seen.has(key)) {
                    seen.add(key);
                    items.push({
                        tag: child.tagName, x: Math.round(cr.x), y: Math.round(cr.y),
                        w: Math.round(cr.width), h: Math.round(cr.height),
                        text: text.substring(0, 40),
                        classes: (child.className || '').toString().substring(0, 30),
                    });
                }
            }
        }
        var h5 = p.querySelector('h5');
        return {
            title: h5 ? (h5.innerText || '').trim() : 'no h5',
            items: items.sort(function(a,b) { return a.y - b.y; }).slice(0, 30),
        };
    }""")
    if char_panel:
        print(f"  Character: '{char_panel['title']}'", flush=True)
        print(f"  Items ({len(char_panel.get('items', []))}):", flush=True)
        for item in char_panel.get('items', []):
            print(f"    ({item['x']},{item['y']}) {item['w']}x{item['h']} <{item['tag']}> c='{item['classes'][:22]}' '{item['text']}'", flush=True)

    # Click "Generate Images" to see the Consistent Character sub-panel
    page.evaluate("""() => {
        var p = document.querySelector('.panels.show');
        if (!p) return;
        for (var el of p.querySelectorAll('*')) {
            if ((el.innerText || '').trim() === 'Generate Images') {
                el.click(); return;
            }
        }
    }""")
    page.wait_for_timeout(2000)
    close_dialogs(page)
    dismiss_popups(page)
    ss(page, "P87_07_cc_panel")

    cc_panel = page.evaluate("""() => {
        var p = document.querySelector('.c-gen-config.show') ||
                document.querySelector('.panels.show');
        if (!p) return null;
        var items = [];
        var seen = new Set();
        for (var child of p.querySelectorAll('*')) {
            var cr = child.getBoundingClientRect();
            var text = (child.innerText || '').trim();
            if (text.length > 0 && text.length < 50 && cr.width > 10 && cr.height > 8
                && cr.width < 300 && text.indexOf('\\n') === -1) {
                var key = child.tagName + '|' + Math.round(cr.y) + '|' + text;
                if (!seen.has(key)) {
                    seen.add(key);
                    items.push({
                        tag: child.tagName, x: Math.round(cr.x), y: Math.round(cr.y),
                        w: Math.round(cr.width), h: Math.round(cr.height),
                        text: text.substring(0, 40),
                        classes: (child.className || '').toString().substring(0, 30),
                    });
                }
            }
        }
        var h5 = p.querySelector('h5');
        return {
            title: h5 ? (h5.innerText || '').trim() : 'no h5',
            panelClass: (p.className || '').toString().substring(0, 60),
            items: items.sort(function(a,b) { return a.y - b.y; }).slice(0, 30),
        };
    }""")
    if cc_panel:
        print(f"\n  CC Panel: '{cc_panel['title']}' class='{cc_panel['panelClass']}'", flush=True)
        print(f"  Items ({len(cc_panel.get('items', []))}):", flush=True)
        for item in cc_panel.get('items', []):
            print(f"    ({item['x']},{item['y']}) {item['w']}x{item['h']} <{item['tag']}> c='{item['classes'][:22]}' '{item['text']}'", flush=True)

    print(f"\n\n===== PHASE 87 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
