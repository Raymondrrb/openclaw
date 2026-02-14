"""Phase 68: Expression Edit templates, Text tool, Zoom/Undo controls, result privacy/download.

From P67:
- Product Background confirmed (div.subtool-item at bottom of Image Editor scroll)
- Layer tools toolbar: AI Eraser, Hand Repair, Expression, BG Remove + icon tools
- Delete/Backspace delete layers immediately (no confirm), Ctrl+Z undoes
- Result image URLs: static.dzine.ai/stylar_product/p/<project>/<type>/...

Goals:
1. Map Expression Edit Template mode presets
2. Explore Text tool (top toolbar T icon)
3. Test zoom controls (top bar zoom %, scroll wheel)
4. Map undo/redo behavior
5. Test result privacy toggle (Private badge is clickable)
6. Check result download/copy actions (right-click result image?)
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
    #  PART 1: EXPRESSION EDIT — TEMPLATE MODE
    # ============================================================
    print("\\n" + "=" * 60, flush=True)
    print("  PART 1: EXPRESSION EDIT — TEMPLATE MODE", flush=True)
    print("=" * 60, flush=True)

    # Need to access Expression Edit via Results panel action button
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

    # Click "Expression Edit" -> "1" button on first result
    expr_clicked = page.evaluate("""() => {
        // Find Expression Edit row and its "1" button
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text === '1' && r.x > 1200 && r.y > 430 && r.y < 460
                && r.width > 40 && r.height > 15) {
                el.click();
                return {x: Math.round(r.x), y: Math.round(r.y), text: text};
            }
        }
        return null;
    }""")
    print(f"  Expression Edit '1' clicked: {expr_clicked}", flush=True)
    page.wait_for_timeout(2000)
    close_dialogs(page)

    # Check if Expression Edit panel opened
    expr_header = page.evaluate("""() => {
        for (const el of document.querySelectorAll('.gen-config-header')) {
            var text = (el.innerText || '').trim();
            if (text.includes('Expression')) return text;
        }
        return null;
    }""")
    print(f"  Expression Edit header: {expr_header}", flush=True)

    if expr_header:
        ss(page, "P68_01_expression_custom")

        # Click Template tab
        template_clicked = page.evaluate("""() => {
            for (const el of document.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                var r = el.getBoundingClientRect();
                if (text === 'Template' && r.x > 60 && r.x < 300 && r.y > 300 && r.y < 370) {
                    el.click();
                    return {x: Math.round(r.x), y: Math.round(r.y)};
                }
            }
            return null;
        }""")
        print(f"  Template tab clicked: {template_clicked}", flush=True)
        page.wait_for_timeout(1000)

        ss(page, "P68_02_expression_template")

        # Map template presets
        templates = page.evaluate("""() => {
            var items = [];
            for (const el of document.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                var r = el.getBoundingClientRect();
                var classes = (el.className || '').toString();
                // Template presets are in the left panel area, after the Template tab
                if (r.x > 60 && r.x < 370 && r.y > 360 && r.y < 900
                    && r.width > 30 && r.height > 30 && r.height < 120
                    && text.length > 2 && text.length < 30) {
                    items.push({
                        text: text,
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        tag: el.tagName,
                        classes: classes.substring(0, 30),
                    });
                }
            }
            var seen = new Set();
            return items.filter(function(i) {
                if (seen.has(i.text)) return false;
                seen.add(i.text);
                return true;
            }).sort(function(a,b) { return a.y - b.y; });
        }""")
        print(f"\\n  Template presets ({len(templates)}):", flush=True)
        for t in templates:
            print(f"    ({t['x']},{t['y']}) {t['w']}x{t['h']} <{t['tag']}> c='{t['classes'][:22]}' '{t['text']}'", flush=True)

        # Also look for image-based template options (might be thumbnails, not text)
        template_imgs = page.evaluate("""() => {
            var items = [];
            for (const el of document.querySelectorAll('img, [style*="background-image"]')) {
                var r = el.getBoundingClientRect();
                if (r.x > 60 && r.x < 370 && r.y > 360 && r.y < 900
                    && r.width > 30 && r.height > 30 && r.width < 120) {
                    items.push({
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        tag: el.tagName,
                        alt: (el.alt || '').substring(0, 30),
                        classes: (el.className || '').toString().substring(0, 30),
                    });
                }
            }
            return items.sort(function(a,b) { return a.y - b.y || a.x - b.x; });
        }""")
        print(f"\\n  Template images ({len(template_imgs)}):", flush=True)
        for t in template_imgs:
            print(f"    ({t['x']},{t['y']}) {t['w']}x{t['h']} <{t['tag']}> alt='{t['alt']}' c='{t['classes'][:22]}'", flush=True)

        # Full dump of template area
        dump_region(page, "Expression Template area", 60, 370, 300, 900)
    else:
        print("  Expression Edit panel not opened. Trying via Image Editor...", flush=True)
        # Fallback: open via Image Editor sidebar
        page.mouse.click(40, 252)
        page.wait_for_timeout(300)
        page.mouse.click(40, 698)
        page.wait_for_timeout(1500)
        close_dialogs(page)
        # Scroll to Expression Edit
        page.evaluate("""() => {
            var panel = document.querySelector('.subtools');
            if (panel) { panel.scrollTop = 400; return true; }
            return false;
        }""")
        page.wait_for_timeout(500)
        # Click Expression Edit
        page.evaluate("""() => {
            for (const btn of document.querySelectorAll('button')) {
                var text = (btn.innerText || '').trim();
                if (text === 'Expression Edit') { btn.click(); return true; }
            }
            return false;
        }""")
        page.wait_for_timeout(2000)
        close_dialogs(page)
        ss(page, "P68_01b_expression_via_sidebar")
        dump_region(page, "Expression Edit panel", 60, 370, 40, 900)

    # Go back
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)

    # ============================================================
    #  PART 2: TEXT TOOL
    # ============================================================
    print("\\n" + "=" * 60, flush=True)
    print("  PART 2: TEXT TOOL", flush=True)
    print("=" * 60, flush=True)

    # Click the T icon in the top toolbar (approximately x=330, y=22)
    # First find it
    text_tool = page.evaluate("""() => {
        // The T icon is in the top toolbar row
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            var classes = (el.className || '').toString();
            if (r.y < 45 && r.x > 300 && r.x < 400 && r.width > 20 && r.width < 50
                && r.height > 20 && r.height < 50
                && (classes.includes('text') || text === 'T')) {
                return {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width),
                        text: text, classes: classes.substring(0, 40)};
            }
        }
        // Broader search for toolbar icons
        for (const el of document.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            var title = el.getAttribute('title') || '';
            if (r.y < 45 && r.x > 280 && r.x < 400 && r.width > 15 && r.width < 50
                && r.height > 15 && r.height < 50
                && (title.toLowerCase().includes('text') || title === 'T')) {
                return {x: Math.round(r.x), y: Math.round(r.y), title: title,
                        classes: (el.className || '').toString().substring(0, 40)};
            }
        }
        return null;
    }""")
    print(f"  Text tool found: {text_tool}", flush=True)

    # Try clicking the T position we saw in screenshots (around x=332, y=22)
    page.mouse.click(332, 22)
    page.wait_for_timeout(1500)
    close_dialogs(page)

    ss(page, "P68_03_text_tool")

    # Check if any text editing panel appeared
    text_panel = page.evaluate("""() => {
        var items = [];
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (r.x > 60 && r.x < 500 && r.y > 40 && r.y < 900
                && r.width > 30 && r.height > 10
                && text.length > 2 && text.length < 50
                && (text.includes('font') || text.includes('Font') || text.includes('text')
                    || text.includes('Text') || text.includes('size') || text.includes('Size')
                    || text.includes('color') || text.includes('Color')
                    || text.includes('Bold') || text.includes('Italic'))) {
                items.push({
                    text: text,
                    x: Math.round(r.x), y: Math.round(r.y),
                    tag: el.tagName,
                });
            }
        }
        return items;
    }""")
    print(f"  Text panel items ({len(text_panel)}):", flush=True)
    for t in text_panel:
        print(f"    ({t['x']},{t['y']}) <{t['tag']}> '{t['text']}'", flush=True)

    # Check if a text input appeared on canvas
    canvas_text = page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            var classes = (el.className || '').toString();
            var r = el.getBoundingClientRect();
            if ((classes.includes('text-editor') || classes.includes('text-input')
                 || el.contentEditable === 'true')
                && r.x > 300 && r.x < 1100 && r.y > 50 && r.y < 800
                && r.width > 50) {
                return {
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    editable: el.contentEditable,
                    classes: classes.substring(0, 50),
                    text: (el.innerText || '').substring(0, 50),
                };
            }
        }
        return null;
    }""")
    print(f"  Canvas text editor: {canvas_text}", flush=True)

    # ============================================================
    #  PART 3: ZOOM CONTROLS
    # ============================================================
    print("\\n" + "=" * 60, flush=True)
    print("  PART 3: ZOOM CONTROLS", flush=True)
    print("=" * 60, flush=True)

    # Find the zoom percentage display
    zoom = page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text.includes('%') && r.y < 40 && r.x > 900 && r.x < 1050
                && r.height < 30) {
                return {
                    text: text,
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width),
                    tag: el.tagName,
                    classes: (el.className || '').toString().substring(0, 30),
                };
            }
        }
        return null;
    }""")
    print(f"  Zoom display: {zoom}", flush=True)

    # Click the zoom to see dropdown
    if zoom:
        page.mouse.click(zoom['x'] + zoom['w']//2, zoom['y'] + 10)
        page.wait_for_timeout(1000)

        # Check for zoom dropdown
        zoom_menu = page.evaluate("""() => {
            var items = [];
            for (const el of document.querySelectorAll('*')) {
                var style = window.getComputedStyle(el);
                var z = parseInt(style.zIndex) || 0;
                var r = el.getBoundingClientRect();
                var text = (el.innerText || '').trim();
                if (z > 100 && r.x > 900 && r.y > 30 && r.y < 300
                    && r.width > 40 && r.height > 10 && r.height < 40
                    && text.length > 0 && text.length < 20) {
                    items.push({
                        text: text, z: z,
                        x: Math.round(r.x), y: Math.round(r.y),
                    });
                }
            }
            var seen = new Set();
            return items.filter(function(i) {
                if (seen.has(i.text)) return false;
                seen.add(i.text);
                return true;
            }).sort(function(a,b) { return a.y - b.y; });
        }""")
        print(f"  Zoom dropdown ({len(zoom_menu)}):", flush=True)
        for z in zoom_menu:
            print(f"    z={z['z']} ({z['x']},{z['y']}) '{z['text']}'", flush=True)

        ss(page, "P68_04_zoom_menu")
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)

    # Test Ctrl+= (zoom in) and Ctrl+- (zoom out)
    zoom_before = page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            if (text.includes('%') && el.getBoundingClientRect().y < 40
                && el.getBoundingClientRect().x > 900) {
                return text;
            }
        }
        return null;
    }""")
    print(f"\\n  Zoom before: {zoom_before}", flush=True)

    # ============================================================
    #  PART 4: UNDO/REDO
    # ============================================================
    print("\\n" + "=" * 60, flush=True)
    print("  PART 4: UNDO/REDO BUTTONS", flush=True)
    print("=" * 60, flush=True)

    # Find undo/redo buttons
    undo_redo = page.evaluate("""() => {
        var items = [];
        for (const el of document.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            var classes = (el.className || '').toString();
            var title = el.getAttribute('title') || '';
            if (r.y < 45 && r.x > 800 && r.x < 980 && r.width > 15 && r.width < 50
                && r.height > 15 && r.height < 50
                && (classes.includes('undo') || classes.includes('redo')
                    || title.includes('undo') || title.includes('redo')
                    || title.includes('Undo') || title.includes('Redo'))) {
                items.push({
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    tag: el.tagName,
                    title: title,
                    classes: classes.substring(0, 40),
                });
            }
        }
        return items;
    }""")
    print(f"  Undo/Redo buttons ({len(undo_redo)}):", flush=True)
    for u in undo_redo:
        print(f"    ({u['x']},{u['y']}) {u['w']}x{u['h']} <{u['tag']}> title='{u['title']}' c='{u['classes'][:30]}'", flush=True)

    # Map all top bar buttons between x=800-1000
    top_right = page.evaluate("""() => {
        var items = [];
        for (const el of document.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            if (r.y < 45 && r.x > 800 && r.x < 1000 && r.width > 10 && r.width < 50
                && r.height > 10 && r.height < 50) {
                items.push({
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    tag: el.tagName,
                    classes: (el.className || '').toString().substring(0, 40),
                    title: el.getAttribute('title') || '',
                    text: (el.innerText || '').trim().substring(0, 10),
                });
            }
        }
        var seen = new Set();
        return items.filter(function(i) {
            var key = i.x + '|' + i.y + '|' + i.w;
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
        }).sort(function(a,b) { return a.x - b.x; });
    }""")
    print(f"\\n  Top bar buttons x=800-1000 ({len(top_right)}):", flush=True)
    for t in top_right:
        print(f"    ({t['x']},{t['y']}) {t['w']}x{t['h']} <{t['tag']}> title='{t['title']}' c='{t['classes'][:25]}' '{t['text']}'", flush=True)

    # ============================================================
    #  PART 5: RESULT PRIVACY + DELETE
    # ============================================================
    print("\\n" + "=" * 60, flush=True)
    print("  PART 5: RESULT PRIVACY + DELETE", flush=True)
    print("=" * 60, flush=True)

    # Switch to Results
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

    # Find privacy button
    privacy = page.evaluate("""() => {
        for (const btn of document.querySelectorAll('button')) {
            var text = (btn.innerText || '').trim();
            var classes = (btn.className || '').toString();
            if (classes.includes('privacy') && text.length > 0) {
                var r = btn.getBoundingClientRect();
                return {
                    text: text, x: Math.round(r.x), y: Math.round(r.y),
                    classes: classes.substring(0, 40),
                };
            }
        }
        return null;
    }""")
    print(f"  Privacy button: {privacy}", flush=True)

    # Find delete/trash icons on results
    result_actions = page.evaluate("""() => {
        var items = [];
        for (const el of document.querySelectorAll('*')) {
            var classes = (el.className || '').toString();
            var r = el.getBoundingClientRect();
            if (r.x > 1300 && r.y > 60 && r.y < 130 && r.width > 10 && r.width < 35
                && r.height > 10 && r.height < 35) {
                items.push({
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    tag: el.tagName,
                    classes: classes.substring(0, 40),
                    title: el.getAttribute('title') || '',
                });
            }
        }
        return items.sort(function(a,b) { return a.x - b.x; });
    }""")
    print(f"  Result action icons ({len(result_actions)}):", flush=True)
    for ra in result_actions:
        print(f"    ({ra['x']},{ra['y']}) {ra['w']}x{ra['h']} <{ra['tag']}> title='{ra['title']}' c='{ra['classes'][:30]}'", flush=True)

    ss(page, "P68_05_result_actions")

    # Click the info/details icon to see what it shows
    # From P67, we found icons at x>1330 in result header
    page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            var classes = (el.className || '').toString();
            var r = el.getBoundingClientRect();
            if (classes.includes('ico-info') && r.y > 80 && r.y < 120 && r.x > 1300) {
                el.click(); return true;
            }
        }
        // Try any small clickable icon near (1340, 100)
        for (const el of document.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            if (r.x > 1340 && r.x < 1365 && r.y > 85 && r.y < 110
                && r.width > 10 && r.width < 30 && r.height > 10 && r.height < 30
                && el.tagName !== 'PATH') {
                el.click();
                return {x: Math.round(r.x), y: Math.round(r.y),
                        classes: (el.className || '').toString().substring(0, 30)};
            }
        }
        return null;
    }""")
    page.wait_for_timeout(1000)

    # Check what opened
    info_dialog = page.evaluate("""() => {
        var items = [];
        for (const el of document.querySelectorAll('*')) {
            var style = window.getComputedStyle(el);
            var z = parseInt(style.zIndex) || 0;
            var r = el.getBoundingClientRect();
            var text = (el.innerText || '').trim();
            if (z > 500 && r.width > 100 && r.height > 80 && text.length > 5) {
                items.push({
                    text: text.substring(0, 150),
                    z: z, x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                });
            }
        }
        return items.sort(function(a,b) { return b.z - a.z; }).slice(0, 3);
    }""")
    print(f"  Info dialog ({len(info_dialog)}):", flush=True)
    for d in info_dialog:
        print(f"    z={d['z']} ({d['x']},{d['y']}) {d['w']}x{d['h']} '{d['text'][:80]}'", flush=True)

    ss(page, "P68_06_result_info_detail")

    page.keyboard.press("Escape")
    page.wait_for_timeout(300)

    ss(page, "P68_07_final")

    print(f"\\n\\n===== PHASE 68 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
