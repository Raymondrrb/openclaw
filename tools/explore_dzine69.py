"""Phase 69: Expression Edit Template mode (correct y=467), Text tool via toolbar icon mapping.

From P68:
- Expression Edit "1" at y=431 was actually Lip Sync (fixed: should be y=467)
- Lip Sync Pick a Face dialog: auto-detect, 1-4 faces, Mark Face Manually
- Text tool icon not found via text/title search
- Zoom display at c-scale-ratio (991,11) — not clickable as dropdown
- Undo (915,11) button.undo / Redo (951,11) button.redo
- Result actions: handle-btn.info, handle-btn.del, privacy_level

Goals:
1. Open Expression Edit from Results panel at correct y=467
2. Click Template tab and map all template presets
3. Map all top toolbar icons via class/SVG inspection (not text)
4. Click on a text layer to see text editing panel
5. Test canvas scroll-wheel zoom
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
                && r.width > 8 && r.height > 5 && r.width < 500
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
    print(f"\\n  {label} ({len(items)} elements):", flush=True)
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

    # ============================================================
    #  PART 1: EXPRESSION EDIT — CORRECT APPROACH
    # ============================================================
    print("\\n" + "=" * 60, flush=True)
    print("  PART 1: EXPRESSION EDIT — CORRECT APPROACH", flush=True)
    print("=" * 60, flush=True)

    # Switch to Results tab
    page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text === 'Results' && r.x > 1050 && r.y < 60) {
                el.click(); return true;
            }
        }
        return false;
    }""")
    page.wait_for_timeout(1000)

    # Find ALL action buttons with their labels to map correctly
    action_rows = page.evaluate("""() => {
        var items = [];
        // Look for the action label text elements in the Results panel
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (r.x > 1100 && r.x < 1260 && r.y > 200 && r.y < 600
                && r.width > 50 && r.height > 10 && r.height < 30
                && text.length > 3 && text.length < 25) {
                items.push({text: text, y: Math.round(r.y)});
            }
        }
        var seen = new Set();
        return items.filter(function(i) {
            if (seen.has(i.text)) return false;
            seen.add(i.text);
            return true;
        }).sort(function(a,b) { return a.y - b.y; });
    }""")
    print(f"  Action rows ({len(action_rows)}):", flush=True)
    for a in action_rows:
        print(f"    y={a['y']} '{a['text']}'", flush=True)

    # Find Expression Edit row and its adjacent "1" button
    expr_row = next((a for a in action_rows if 'Expression' in a['text']), None)
    if expr_row:
        target_y = expr_row['y']
        print(f"\\n  Expression Edit label at y={target_y}", flush=True)

        # Find the "1" button near that y
        btn1 = page.evaluate(f"""() => {{
            for (const btn of document.querySelectorAll('button')) {{
                var text = (btn.innerText || '').trim();
                var r = btn.getBoundingClientRect();
                if (text === '1' && r.x > 1260 && r.x < 1320
                    && Math.abs(r.y - {target_y}) < 15) {{
                    return {{x: Math.round(r.x), y: Math.round(r.y),
                             w: Math.round(r.width), h: Math.round(r.height)}};
                }}
            }}
            return null;
        }}""")
        print(f"  Button '1' near Expression Edit: {btn1}", flush=True)

        if btn1:
            page.mouse.click(btn1['x'] + btn1['w']//2, btn1['y'] + btn1['h']//2)
            page.wait_for_timeout(3000)
            close_dialogs(page)

            # Verify header
            header = page.evaluate("""() => {
                for (const el of document.querySelectorAll('.gen-config-header')) {
                    var text = (el.innerText || '').trim();
                    if (text) return text;
                }
                // Fallback: check for panel title
                for (const el of document.querySelectorAll('*')) {
                    var text = (el.innerText || '').trim();
                    var r = el.getBoundingClientRect();
                    if (r.x > 60 && r.x < 200 && r.y > 50 && r.y < 100
                        && text.includes('Expression')) return text;
                }
                return null;
            }""")
            print(f"  Panel header: {header}", flush=True)

            if header and 'Expression' in header:
                ss(page, "P69_01_expression_custom")

                # Dump Custom mode content
                dump_region(page, "Expression Custom mode", 60, 370, 40, 900)

                # Now click Template tab
                template = page.evaluate("""() => {
                    for (const el of document.querySelectorAll('*')) {
                        var text = (el.innerText || '').trim();
                        var r = el.getBoundingClientRect();
                        var classes = (el.className || '').toString();
                        if (text === 'Template' && r.x > 60 && r.x < 350
                            && r.y > 280 && r.y < 380
                            && (el.tagName === 'BUTTON' || el.tagName === 'DIV' || el.tagName === 'LI')) {
                            el.click();
                            return {x: Math.round(r.x), y: Math.round(r.y),
                                    classes: classes.substring(0, 30)};
                        }
                    }
                    return null;
                }""")
                print(f"\\n  Template tab clicked: {template}", flush=True)
                page.wait_for_timeout(1000)

                ss(page, "P69_02_expression_template")
                dump_region(page, "Expression Template mode", 60, 370, 280, 900)

                # Try scrolling in template area
                page.evaluate("""() => {
                    var containers = document.querySelectorAll('*');
                    for (var el of containers) {
                        var r = el.getBoundingClientRect();
                        var style = window.getComputedStyle(el);
                        if (r.x > 60 && r.x < 120 && r.width > 200
                            && r.height > 200 && r.y > 300
                            && (style.overflowY === 'auto' || style.overflowY === 'scroll')) {
                            el.scrollTop += 300;
                            return true;
                        }
                    }
                    return false;
                }""")
                page.wait_for_timeout(500)
                dump_region(page, "Expression Template after scroll", 60, 370, 280, 900)
            else:
                print(f"  Wrong panel opened: {header}", flush=True)
                ss(page, "P69_01_wrong_panel")
    else:
        print("  Expression Edit row not found in action rows!", flush=True)

    # Close Expression Edit
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)

    # ============================================================
    #  PART 2: TOP BAR TOOLBAR ICONS (SVG-BASED)
    # ============================================================
    print("\\n" + "=" * 60, flush=True)
    print("  PART 2: TOP BAR TOOLBAR ICONS", flush=True)
    print("=" * 60, flush=True)

    # Map ALL clickable elements in the top toolbar area
    toolbar_items = page.evaluate("""() => {
        var items = [];
        for (const el of document.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            if (r.y < 45 && r.x > 180 && r.x < 520 && r.width > 15 && r.width < 50
                && r.height > 15 && r.height < 50
                && (el.tagName === 'BUTTON' || el.tagName === 'A' || el.tagName === 'DIV')) {
                var classes = (el.className || '').toString();
                items.push({
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    tag: el.tagName,
                    classes: classes.substring(0, 50),
                    text: (el.innerText || '').trim().substring(0, 15),
                    title: el.getAttribute('title') || '',
                    ariaLabel: el.getAttribute('aria-label') || '',
                    id: el.id || '',
                });
            }
        }
        var seen = new Set();
        return items.filter(function(i) {
            var key = i.x + '|' + i.y;
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
        }).sort(function(a,b) { return a.x - b.x; });
    }""")
    print(f"  Toolbar icons ({len(toolbar_items)}):", flush=True)
    for t in toolbar_items:
        print(f"    ({t['x']},{t['y']}) {t['w']}x{t['h']} <{t['tag']}> id='{t['id']}' title='{t['title']}' c='{t['classes'][:30]}' '{t['text']}'", flush=True)

    ss(page, "P69_03_toolbar")

    # ============================================================
    #  PART 3: TEXT LAYER INTERACTION
    # ============================================================
    print("\\n" + "=" * 60, flush=True)
    print("  PART 3: TEXT LAYER INTERACTION", flush=True)
    print("=" * 60, flush=True)

    # Switch to Layers and click on Layer 2 (which was a "T" text layer)
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
    page.wait_for_timeout(500)

    # Click on Layer 2 (the text layer with T icon)
    page.evaluate("""() => {
        for (const btn of document.querySelectorAll('button.layer-item')) {
            var text = (btn.innerText || '').trim();
            if (text.includes('Layer 2')) {
                btn.click(); return true;
            }
        }
        return false;
    }""")
    page.wait_for_timeout(1000)

    ss(page, "P69_04_text_layer_selected")

    # Double-click the text layer on canvas to edit
    # The text layer should be somewhere on the canvas
    # Check if text editing UI appeared
    text_ui = page.evaluate("""() => {
        var items = [];
        for (const el of document.querySelectorAll('*')) {
            var classes = (el.className || '').toString();
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (r.x > 300 && r.x < 1100 && r.y > 50 && r.y < 800
                && (classes.includes('text') || el.contentEditable === 'true')
                && r.width > 20 && r.height > 10) {
                items.push({
                    text: text.substring(0, 30),
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    editable: el.contentEditable,
                    tag: el.tagName,
                    classes: classes.substring(0, 40),
                });
            }
        }
        return items;
    }""")
    print(f"  Text UI elements on canvas ({len(text_ui)}):", flush=True)
    for t in text_ui:
        print(f"    ({t['x']},{t['y']}) {t['w']}x{t['h']} <{t['tag']}> edit={t['editable']} c='{t['classes'][:25]}' '{t['text']}'", flush=True)

    # Now double-click the text layer on canvas to enter edit mode
    # Find the text element position on canvas
    text_on_canvas = page.evaluate("""() => {
        // Find the selected text element on canvas (usually has transform)
        for (const el of document.querySelectorAll('*')) {
            var classes = (el.className || '').toString();
            var r = el.getBoundingClientRect();
            if (classes.includes('text-layer') && r.x > 300 && r.width > 50
                && r.y > 100 && r.y < 700) {
                return {x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2),
                        w: Math.round(r.width), h: Math.round(r.height),
                        classes: classes.substring(0, 50)};
            }
        }
        return null;
    }""")
    print(f"  Text on canvas: {text_on_canvas}", flush=True)

    if text_on_canvas:
        page.mouse.dblclick(text_on_canvas['x'], text_on_canvas['y'])
        page.wait_for_timeout(1500)
        ss(page, "P69_05_text_edit_mode")

        # Check for text editing panel/toolbar
        text_edit_ui = page.evaluate("""() => {
            var items = [];
            for (const el of document.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                var r = el.getBoundingClientRect();
                var classes = (el.className || '').toString();
                if (text.length > 0 && text.length < 30 && r.width > 20
                    && (classes.includes('font') || classes.includes('text-tool')
                        || classes.includes('text-editor') || classes.includes('toolbar')
                        || text.includes('Font') || text.includes('Bold')
                        || text.includes('Size') || text.includes('Color'))) {
                    items.push({
                        text: text, x: Math.round(r.x), y: Math.round(r.y),
                        classes: classes.substring(0, 30),
                    });
                }
            }
            return items.sort(function(a,b) { return a.y - b.y; });
        }""")
        print(f"  Text editing UI ({len(text_edit_ui)}):", flush=True)
        for t in text_edit_ui:
            print(f"    ({t['x']},{t['y']}) c='{t['classes'][:25]}' '{t['text']}'", flush=True)

    # ============================================================
    #  PART 4: CANVAS SCROLL ZOOM
    # ============================================================
    print("\\n" + "=" * 60, flush=True)
    print("  PART 4: CANVAS SCROLL ZOOM", flush=True)
    print("=" * 60, flush=True)

    # Get current zoom
    zoom_before = page.evaluate("""() => {
        var el = document.querySelector('.c-scale-ratio');
        return el ? (el.innerText || '').trim() : null;
    }""")
    print(f"  Zoom before: {zoom_before}", flush=True)

    # Scroll wheel zoom (Ctrl+scroll)
    page.mouse.move(700, 400)
    page.keyboard.down("Meta")
    page.mouse.wheel(0, -300)  # Scroll up = zoom in
    page.keyboard.up("Meta")
    page.wait_for_timeout(500)

    zoom_after_in = page.evaluate("""() => {
        var el = document.querySelector('.c-scale-ratio');
        return el ? (el.innerText || '').trim() : null;
    }""")
    print(f"  Zoom after scroll up (Cmd+scroll): {zoom_after_in}", flush=True)

    # Scroll without Ctrl
    page.mouse.wheel(0, 300)  # Scroll down without Ctrl
    page.wait_for_timeout(500)

    zoom_after_plain = page.evaluate("""() => {
        var el = document.querySelector('.c-scale-ratio');
        return el ? (el.innerText || '').trim() : null;
    }""")
    print(f"  Zoom after plain scroll down: {zoom_after_plain}", flush=True)

    # Try Ctrl+= (zoom in) and Ctrl+- (zoom out)
    page.keyboard.press("Meta+=")
    page.wait_for_timeout(300)
    zoom_after_plus = page.evaluate("""() => {
        var el = document.querySelector('.c-scale-ratio');
        return el ? (el.innerText || '').trim() : null;
    }""")
    print(f"  Zoom after Cmd+=: {zoom_after_plus}", flush=True)

    page.keyboard.press("Meta+-")
    page.wait_for_timeout(300)
    zoom_after_minus = page.evaluate("""() => {
        var el = document.querySelector('.c-scale-ratio');
        return el ? (el.innerText || '').trim() : null;
    }""")
    print(f"  Zoom after Cmd+-: {zoom_after_minus}", flush=True)

    # Try Cmd+0 (fit to canvas)
    page.keyboard.press("Meta+0")
    page.wait_for_timeout(300)
    zoom_after_fit = page.evaluate("""() => {
        var el = document.querySelector('.c-scale-ratio');
        return el ? (el.innerText || '').trim() : null;
    }""")
    print(f"  Zoom after Cmd+0 (fit): {zoom_after_fit}", flush=True)

    ss(page, "P69_06_final")

    print(f"\\n\\n===== PHASE 69 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
