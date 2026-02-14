"""Phase 86: Final gaps.
1. Export dialog — use z>50 threshold (it's likely a modal, not z>500)
2. Chat editor panel — dump the expanded panel at z=199
3. Layers panel — click "Layers" header tab
4. Img2Img panel — close ALL panels first, then use different toggle approach
5. Results panel — click "Results" header tab
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
        var close = document.querySelector('.c-gen-config.show .ico-close');
        if (close) close.click();
    }""")
    page.wait_for_timeout(500)
    # Close .panels.show too
    page.evaluate("""() => {
        var close = document.querySelector('.panels.show .ico-close');
        if (close) close.click();
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


def open_panel(page, target_x, target_y, panel_name=""):
    page.mouse.click(40, 766)  # Storyboard (distant toggle)
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


def cleanup_tabs(ctx):
    """Close all extra Dzine tabs and blank tabs."""
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
    #  PART 1: EXPORT DIALOG (z>50 threshold)
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 1: EXPORT DIALOG", flush=True)
    print("=" * 60, flush=True)

    close_all_overlays(page)
    page.wait_for_timeout(1000)

    # Click Export
    page.evaluate("""() => {
        var btn = document.querySelector('.c-export');
        if (btn) btn.click();
    }""")
    page.wait_for_timeout(2000)
    ss(page, "P86_01_export")

    # Find export dialog — look for ANY overlay that appeared after click
    export = page.evaluate("""() => {
        var results = [];
        // Strategy 1: look for modal/dialog classes
        var selectors = [
            '.ant-modal-wrap', '.ant-modal', '.modal', '.dialog',
            '.c-export-dialog', '.export-dialog', '.export-modal',
            '[class*="export"]', '[class*="modal"]', '[class*="dialog"]',
        ];
        for (var sel of selectors) {
            var els = document.querySelectorAll(sel);
            for (var el of els) {
                var r = el.getBoundingClientRect();
                if (r.width > 100 && r.height > 100) {
                    results.push({
                        sel: sel,
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        classes: (el.className || '').toString().substring(0, 60),
                    });
                }
            }
        }

        // Strategy 2: scan for high z-index (z > 50)
        var highZ = [];
        for (var el of document.querySelectorAll('*')) {
            var cs = window.getComputedStyle(el);
            var z = parseInt(cs.zIndex) || 0;
            var r = el.getBoundingClientRect();
            if (z > 50 && r.width > 150 && r.height > 100 && r.x > 200) {
                highZ.push({
                    tag: el.tagName, z: z,
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    classes: (el.className || '').toString().substring(0, 60),
                    children: el.children.length,
                });
            }
        }
        return {bySelector: results, byZIndex: highZ.sort(function(a,b) { return b.z - a.z; }).slice(0, 10)};
    }""")
    print(f"\n  By selector ({len(export.get('bySelector', []))}):", flush=True)
    for e in export.get('bySelector', []):
        print(f"    {e['sel']} ({e['x']},{e['y']}) {e['w']}x{e['h']} c='{e['classes']}'", flush=True)
    print(f"\n  By z-index ({len(export.get('byZIndex', []))}):", flush=True)
    for e in export.get('byZIndex', []):
        print(f"    z={e['z']} ({e['x']},{e['y']}) {e['w']}x{e['h']} <{e['tag']}> c='{e['classes']}' ch={e['children']}", flush=True)

    # If we found a dialog, dump its contents
    if export.get('byZIndex'):
        highest = export['byZIndex'][0]
        dialog_items = page.evaluate(f"""() => {{
            var items = [];
            var seen = new Set();
            for (var el of document.querySelectorAll('*')) {{
                var cs = window.getComputedStyle(el);
                var z = parseInt(cs.zIndex) || 0;
                var r = el.getBoundingClientRect();
                if (z >= {highest['z']} - 10 && r.width > 100 && r.height > 50) {{
                    for (var child of el.querySelectorAll('*')) {{
                        var cr = child.getBoundingClientRect();
                        var text = (child.innerText || '').trim();
                        if (text.length > 0 && text.length < 50 && cr.width > 10
                            && cr.height > 8 && cr.height < 60 && cr.width < 400
                            && text.indexOf('\\n') === -1) {{
                            var key = text + '|' + Math.round(cr.y);
                            if (!seen.has(key)) {{
                                seen.add(key);
                                items.push({{
                                    tag: child.tagName, x: Math.round(cr.x), y: Math.round(cr.y),
                                    w: Math.round(cr.width), h: Math.round(cr.height),
                                    text: text.substring(0, 45),
                                    classes: (child.className || '').toString().substring(0, 30),
                                }});
                            }}
                        }}
                    }}
                    break;
                }}
            }}
            return items.sort(function(a,b) {{ return a.y - b.y; }}).slice(0, 40);
        }}""")
        print(f"\n  Dialog contents ({len(dialog_items)}):", flush=True)
        for d in dialog_items:
            print(f"    ({d['x']},{d['y']}) {d['w']}x{d['h']} <{d['tag']}> c='{d['classes'][:22]}' '{d['text']}'", flush=True)

    # Also try: look for the Export section as a dropdown/popover near the Export button
    export_near = page.evaluate("""() => {
        var items = [];
        var seen = new Set();
        // Look near the Export button (x=1328, y=12)
        for (var el of document.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            if (r.x > 1100 && r.y > 30 && r.y < 500 && r.width > 50 && r.height > 20
                && r.height < 50 && r.width < 300) {
                var text = (el.innerText || '').trim();
                if (text.length > 0 && text.length < 40 && text.indexOf('\\n') === -1) {
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
        return items.sort(function(a,b) { return a.y - b.y; }).slice(0, 25);
    }""")
    print(f"\n  Near Export button ({len(export_near)}):", flush=True)
    for e in export_near:
        print(f"    ({e['x']},{e['y']}) {e['w']}x{e['h']} <{e['tag']}> c='{e['classes'][:22]}' '{e['text']}'", flush=True)

    page.keyboard.press("Escape")
    page.wait_for_timeout(500)

    # ============================================================
    #  PART 2: CHAT EDITOR — EXPANDED PANEL
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 2: CHAT EDITOR EXPANDED", flush=True)
    print("=" * 60, flush=True)

    close_all_overlays(page)
    page.wait_for_timeout(500)

    # Click the chat prompt text to expand
    page.mouse.click(628, 824)  # chat-editor-prompt position
    page.wait_for_timeout(2000)
    ss(page, "P86_02_chat_expanded")

    # Dump the chat-editor-panel-wrapper
    chat_panel = page.evaluate("""() => {
        var wrapper = document.querySelector('.chat-editor-panel-wrapper');
        if (!wrapper) return null;
        var r = wrapper.getBoundingClientRect();
        if (r.height < 10) return {found: true, collapsed: true};

        var items = [];
        var seen = new Set();
        for (var child of wrapper.querySelectorAll('*')) {
            var cr = child.getBoundingClientRect();
            var text = (child.innerText || '').trim();
            var cls = (child.className || '').toString();
            if (cr.width > 5 && cr.height > 5) {
                if (text.length > 0 && text.length < 60 && text.indexOf('\\n') === -1) {
                    var key = text + '|' + Math.round(cr.y) + '|' + Math.round(cr.x);
                    if (!seen.has(key)) {
                        seen.add(key);
                        items.push({
                            tag: child.tagName, x: Math.round(cr.x), y: Math.round(cr.y),
                            w: Math.round(cr.width), h: Math.round(cr.height),
                            text: text.substring(0, 45),
                            classes: cls.substring(0, 35),
                        });
                    }
                }
                // Also capture inputs/textareas/contenteditable
                if (child.tagName === 'INPUT' || child.tagName === 'TEXTAREA'
                    || child.contentEditable === 'true') {
                    items.push({
                        tag: child.tagName, x: Math.round(cr.x), y: Math.round(cr.y),
                        w: Math.round(cr.width), h: Math.round(cr.height),
                        text: '[INPUT] ' + (child.placeholder || child.getAttribute('data-placeholder') || child.value || '').substring(0, 30),
                        classes: cls.substring(0, 35),
                        contentEditable: child.contentEditable,
                    });
                }
            }
        }
        return {
            found: true, collapsed: false,
            bounds: {x: Math.round(r.x), y: Math.round(r.y),
                     w: Math.round(r.width), h: Math.round(r.height)},
            items: items.sort(function(a,b) { return a.y - b.y; }).slice(0, 30),
        };
    }""")
    if chat_panel:
        print(f"  Chat panel: {chat_panel.get('bounds', 'collapsed')}", flush=True)
        if not chat_panel.get('collapsed'):
            print(f"  Items ({len(chat_panel.get('items', []))}):", flush=True)
            for c in chat_panel.get('items', []):
                ce = f" ce={c.get('contentEditable','')}" if c.get('contentEditable') else ''
                print(f"    ({c['x']},{c['y']}) {c['w']}x{c['h']} <{c['tag']}> c='{c['classes'][:25]}' '{c['text'][:40]}'{ce}", flush=True)
    else:
        print("  Chat panel: NOT FOUND", flush=True)

    # Try to find the model selector in the chat panel
    chat_model = page.evaluate("""() => {
        var wrapper = document.querySelector('.chat-editor-panel-wrapper');
        if (!wrapper) return null;
        var btn = wrapper.querySelector('.selected-btn-content') ||
                  wrapper.querySelector('button.style') ||
                  wrapper.querySelector('[class*="model"]');
        if (btn) {
            var r = btn.getBoundingClientRect();
            return {
                tag: btn.tagName, x: Math.round(r.x), y: Math.round(r.y),
                w: Math.round(r.width), h: Math.round(r.height),
                text: (btn.innerText || '').trim().substring(0, 30),
                classes: (btn.className || '').toString().substring(0, 40),
            };
        }
        return null;
    }""")
    print(f"\n  Chat model selector: {chat_model}", flush=True)

    page.keyboard.press("Escape")
    page.wait_for_timeout(500)

    # ============================================================
    #  PART 3: LAYERS PANEL (via header tab)
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 3: LAYERS PANEL", flush=True)
    print("=" * 60, flush=True)

    close_all_overlays(page)
    page.wait_for_timeout(500)

    # Click "Layers" header tab
    page.evaluate("""() => {
        var btn = document.querySelector('.header-item.item-layers');
        if (btn) btn.click();
    }""")
    page.wait_for_timeout(1500)
    ss(page, "P86_03_layers")

    # Dump whatever opened on the right side
    layers = page.evaluate("""() => {
        // Look for elements on the right side (x > 1050) that appeared
        var items = [];
        var seen = new Set();
        for (var el of document.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            if (r.x > 1050 && r.y > 50 && r.y < 900 && r.width > 30 && r.height > 10
                && r.height < 60 && r.width < 400) {
                var text = (el.innerText || '').trim();
                var cls = (el.className || '').toString();
                if ((text.length > 0 && text.length < 40 && text.indexOf('\\n') === -1)
                    || cls.includes('layer') || cls.includes('ico')) {
                    var key = (text || cls.substring(0, 20)) + '|' + Math.round(r.y) + '|' + Math.round(r.x);
                    if (!seen.has(key)) {
                        seen.add(key);
                        items.push({
                            tag: el.tagName, x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height),
                            text: text.substring(0, 35),
                            classes: cls.substring(0, 35),
                        });
                    }
                }
            }
        }
        return items.sort(function(a,b) { return a.y - b.y; }).slice(0, 30);
    }""")
    print(f"\n  Layers panel items ({len(layers)}):", flush=True)
    for l in layers:
        print(f"    ({l['x']},{l['y']}) {l['w']}x{l['h']} <{l['tag']}> c='{l['classes'][:25]}' '{l['text']}'", flush=True)

    # Also check for a specific layers container
    layers_container = page.evaluate("""() => {
        var selectors = ['.c-layers-panel', '.layers-panel', '.layer-list',
                         '[class*="layer-panel"]', '[class*="layers"]'];
        for (var sel of selectors) {
            var el = document.querySelector(sel);
            if (el) {
                var r = el.getBoundingClientRect();
                if (r.width > 50) {
                    return {
                        sel: sel,
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        classes: (el.className || '').toString().substring(0, 50),
                    };
                }
            }
        }
        return null;
    }""")
    print(f"  Layers container: {layers_container}", flush=True)

    # ============================================================
    #  PART 4: RESULTS PANEL (via header tab)
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 4: RESULTS PANEL", flush=True)
    print("=" * 60, flush=True)

    # Click "Results" header tab
    page.evaluate("""() => {
        var btn = document.querySelector('.header-item.item-results');
        if (btn) btn.click();
    }""")
    page.wait_for_timeout(1500)
    ss(page, "P86_04_results")

    results = page.evaluate("""() => {
        var items = [];
        var seen = new Set();
        for (var el of document.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            if (r.x > 1050 && r.y > 50 && r.y < 900 && r.width > 30 && r.height > 10
                && r.height < 60 && r.width < 400) {
                var text = (el.innerText || '').trim();
                var cls = (el.className || '').toString();
                if ((text.length > 0 && text.length < 40 && text.indexOf('\\n') === -1)
                    || cls.includes('result') || cls.includes('ico')) {
                    var key = (text || cls.substring(0, 20)) + '|' + Math.round(r.y) + '|' + Math.round(r.x);
                    if (!seen.has(key)) {
                        seen.add(key);
                        items.push({
                            tag: el.tagName, x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height),
                            text: text.substring(0, 35),
                            classes: cls.substring(0, 35),
                        });
                    }
                }
            }
        }
        return items.sort(function(a,b) { return a.y - b.y; }).slice(0, 30);
    }""")
    print(f"\n  Results panel items ({len(results)}):", flush=True)
    for r in results:
        print(f"    ({r['x']},{r['y']}) {r['w']}x{r['h']} <{r['tag']}> c='{r['classes'][:25]}' '{r['text']}'", flush=True)

    # ============================================================
    #  PART 5: IMG2IMG PANEL (different toggle approach)
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 5: IMG2IMG PANEL", flush=True)
    print("=" * 60, flush=True)

    # First close everything
    close_all_overlays(page)
    page.wait_for_timeout(1000)

    # Click Img2Img directly (not using distant toggle)
    # The issue was that Storyboard toggle + Img2Img opened Txt2Img
    # Try: click away from sidebar first, then click Img2Img
    page.mouse.click(700, 450)
    page.wait_for_timeout(500)

    # Click Img2Img icon
    page.mouse.click(40, 252)
    page.wait_for_timeout(3000)
    close_dialogs(page)
    dismiss_popups(page)

    i2i_title = page.evaluate("""() => {
        var p = document.querySelector('.c-gen-config.show') ||
                document.querySelector('.panels.show');
        if (!p) return 'NONE';
        var h5 = p.querySelector('h5');
        return h5 ? (h5.innerText || '').trim() : 'no h5';
    }""")
    print(f"  Direct click panel: '{i2i_title}'", flush=True)
    ss(page, "P86_05_img2img_direct")

    # If it's not Img2Img, try toggling differently
    if "Image-to-Image" not in i2i_title and "Img" not in i2i_title:
        print("  Wrong panel. Trying: close + Txt2Img + Img2Img", flush=True)
        close_all_overlays(page)
        page.wait_for_timeout(500)

        # Open Txt2Img first
        page.mouse.click(40, 197)
        page.wait_for_timeout(2000)
        close_dialogs(page)

        # Now click Img2Img (adjacent toggle)
        page.mouse.move(700, 450)
        page.wait_for_timeout(300)
        page.mouse.click(40, 252)
        page.wait_for_timeout(3000)
        close_dialogs(page)
        dismiss_popups(page)

        i2i_title2 = page.evaluate("""() => {
            var p = document.querySelector('.c-gen-config.show') ||
                    document.querySelector('.panels.show');
            if (!p) return 'NONE';
            var h5 = p.querySelector('h5');
            return h5 ? (h5.innerText || '').trim() : 'no h5';
        }""")
        print(f"  After Txt2Img→Img2Img toggle: '{i2i_title2}'", flush=True)
        ss(page, "P86_06_img2img_toggle")

    # Dump what we got
    panel_data = page.evaluate("""() => {
        var p = document.querySelector('.panels.show') ||
                document.querySelector('.c-gen-config.show');
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
            panelClass: (p.className || '').toString().substring(0, 60),
            items: items.sort(function(a,b) { return a.y - b.y; }).slice(0, 30),
        };
    }""")
    if panel_data:
        print(f"\n  Panel: '{panel_data['title']}' class='{panel_data['panelClass']}'", flush=True)
        print(f"  Bounds: {panel_data['bounds']}", flush=True)
        print(f"  Items ({len(panel_data.get('items', []))}):", flush=True)
        for item in panel_data.get('items', []):
            print(f"    ({item['x']},{item['y']}) {item['w']}x{item['h']} <{item['tag']}> c='{item['classes'][:22]}' '{item['text']}'", flush=True)

    # Try Img2Img by checking ALL panels (maybe it uses a different container)
    all_panels = page.evaluate("""() => {
        var selectors = [
            '.c-gen-config', '.panels', '.c-gen-config.show', '.panels.show',
            '.img2img-panel', '.i2i-panel', '[class*="img2img"]', '[class*="i2i"]',
        ];
        var results = [];
        for (var sel of selectors) {
            var els = document.querySelectorAll(sel);
            for (var el of els) {
                var r = el.getBoundingClientRect();
                if (r.width > 50 && r.height > 50) {
                    var h5 = el.querySelector('h5');
                    results.push({
                        sel: sel,
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        title: h5 ? (h5.innerText || '').trim() : '',
                        classes: (el.className || '').toString().substring(0, 60),
                        visible: r.width > 0 && r.height > 0,
                    });
                }
            }
        }
        return results;
    }""")
    print(f"\n  All panels ({len(all_panels)}):", flush=True)
    for ap in all_panels:
        print(f"    {ap['sel']} ({ap['x']},{ap['y']}) {ap['w']}x{ap['h']} vis={ap['visible']} title='{ap['title']}' c='{ap['classes'][:40]}'", flush=True)

    print(f"\n\n===== PHASE 86 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
