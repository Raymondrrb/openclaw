"""Phase 70: Expression Edit Template presets, BG Remove click test, canvas project settings.

From P69:
- Expression Edit panel confirmed open (Custom mode, eyes/mouth/head sliders)
- Template tab visible but not clicked (code wrongly detected stale header)
- Toolbar icons: tool-move, tool-text, tool-hand, draw-dropbox
- Text toolbar: c-text-tool with Inter font, size 128, Bold/Italic
- Zoom: Cmd+scroll works (77% -> 92%)

Goals:
1. Open Expression Edit and click Template tab to map template presets
2. Click BG Remove in layer-tools toolbar
3. Test canvas project settings (click project name or canvas size)
4. Final comprehensive verification of all mapped features
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

    # Open via Results panel -> Expression Edit -> 1
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

    # Find Expression Edit action and click "1"
    expr_btn = page.evaluate("""() => {
        // Find "Expression Edit" text, then find "1" button at similar y
        var exprY = null;
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text === 'Expression Edit' && r.x > 1100 && r.x < 1260 && r.y > 400) {
                exprY = r.y;
                break;
            }
        }
        if (!exprY) return null;
        // Find the "1" button near that y
        for (const btn of document.querySelectorAll('button')) {
            var text = (btn.innerText || '').trim();
            var r = btn.getBoundingClientRect();
            if (text === '1' && r.x > 1260 && Math.abs(r.y - exprY) < 15) {
                btn.click();
                return {x: Math.round(r.x), y: Math.round(r.y)};
            }
        }
        return null;
    }""")
    print(f"  Expression Edit '1' clicked: {expr_btn}", flush=True)
    page.wait_for_timeout(3000)
    close_dialogs(page)

    # Verify the Expression Edit panel is visible
    ss(page, "P70_01_expression_opened")

    # Check if Custom/Template tabs are visible
    tabs = page.evaluate("""() => {
        var items = [];
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if ((text === 'Custom' || text === 'Template') && r.x > 50 && r.x < 200
                && r.y > 140 && r.y < 200) {
                items.push({
                    text: text, x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    tag: el.tagName,
                    classes: (el.className || '').toString().substring(0, 30),
                });
            }
        }
        return items;
    }""")
    print(f"  Expression tabs ({len(tabs)}):", flush=True)
    for t in tabs:
        print(f"    ({t['x']},{t['y']}) {t['w']}x{t['h']} <{t['tag']}> c='{t['classes'][:22]}' '{t['text']}'", flush=True)

    # Click Template tab
    template_clicked = page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text === 'Template' && r.x > 50 && r.x < 200
                && r.y > 140 && r.y < 200 && r.width > 40) {
                el.click();
                return {x: Math.round(r.x), y: Math.round(r.y)};
            }
        }
        return null;
    }""")
    print(f"\\n  Template tab clicked: {template_clicked}", flush=True)
    page.wait_for_timeout(1000)

    ss(page, "P70_02_expression_template")

    # Map ALL elements in the template area
    dump_region(page, "Expression Template panel", 40, 180, 180, 500)

    # Also check for image thumbnails (templates might be image-based)
    template_content = page.evaluate("""() => {
        var items = [];
        for (const el of document.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            var classes = (el.className || '').toString();
            var text = (el.innerText || '').trim();
            if (r.x > 40 && r.x < 180 && r.y > 180 && r.y < 500
                && r.width > 20 && r.height > 20
                && (el.tagName === 'IMG' || el.tagName === 'BUTTON' || el.tagName === 'DIV')
                && (classes.includes('template') || classes.includes('preset')
                    || classes.includes('item') || r.width > 30)) {
                items.push({
                    text: text.substring(0, 30),
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    tag: el.tagName,
                    classes: classes.substring(0, 40),
                    src: el.tagName === 'IMG' ? (el.src || '').substring(0, 50) : '',
                });
            }
        }
        return items.sort(function(a,b) { return a.y - b.y || a.x - b.x; });
    }""")
    print(f"\\n  Template content elements ({len(template_content)}):", flush=True)
    for tc in template_content[:20]:
        extra = f" src={tc['src']}" if tc.get('src') else ''
        print(f"    ({tc['x']},{tc['y']}) {tc['w']}x{tc['h']} <{tc['tag']}> c='{tc['classes'][:25]}' '{tc['text'][:20]}'{extra}", flush=True)

    # Scroll in the template area to see more
    page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            var classes = (el.className || '').toString();
            var r = el.getBoundingClientRect();
            if (r.x > 40 && r.x < 60 && r.width > 100 && r.height > 200
                && r.y > 150 && r.y < 220) {
                el.scrollTop += 300;
                return true;
            }
        }
        return false;
    }""")
    page.wait_for_timeout(500)

    dump_region(page, "Expression Template after scroll", 40, 180, 180, 500)

    # Close Expression Edit
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)

    # ============================================================
    #  PART 2: BG REMOVE FROM LAYER TOOLS
    # ============================================================
    print("\\n" + "=" * 60, flush=True)
    print("  PART 2: BG REMOVE FROM LAYER TOOLS", flush=True)
    print("=" * 60, flush=True)

    # Select a layer first
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

    page.evaluate("""() => {
        for (const btn of document.querySelectorAll('button.layer-item')) {
            var text = (btn.innerText || '').trim();
            if (text.includes('Layer 4')) {
                btn.click(); return true;
            }
        }
        return false;
    }""")
    page.wait_for_timeout(1000)

    # Find BG Remove in the layer-tools bar
    bg_remove = page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if ((text === 'BG Remove' || text === 'Bg Remove') && r.y > 30 && r.y < 80) {
                return {x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        tag: el.tagName, text: text};
            }
        }
        return null;
    }""")
    print(f"  BG Remove found: {bg_remove}", flush=True)

    if bg_remove:
        page.mouse.click(bg_remove['x'] + bg_remove['w']//2, bg_remove['y'] + bg_remove['h']//2)
        page.wait_for_timeout(3000)
        close_dialogs(page)
        ss(page, "P70_03_bg_remove")

        # Check what happened
        bg_result = page.evaluate("""() => {
            // Check for any progress/loading indicator
            for (const el of document.querySelectorAll('*')) {
                var classes = (el.className || '').toString();
                var text = (el.innerText || '').trim();
                if (classes.includes('progress') || classes.includes('loading')
                    || text.includes('Processing') || text.includes('Removing')) {
                    return {text: text, classes: classes.substring(0, 40)};
                }
            }
            return null;
        }""")
        print(f"  BG Remove result: {bg_result}", flush=True)

    # Also map ALL layer-tools bar items
    layer_tools = page.evaluate("""() => {
        var bar = document.querySelector('.layer-tools');
        if (!bar) return [];
        var items = [];
        for (const el of bar.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text.length > 2 && text.length < 20 && r.height > 10 && r.height < 30
                && r.width > 30) {
                items.push({
                    text: text, x: Math.round(r.x), y: Math.round(r.y),
                    tag: el.tagName,
                    classes: (el.className || '').toString().substring(0, 30),
                });
            }
        }
        var seen = new Set();
        return items.filter(function(i) {
            if (seen.has(i.text)) return false;
            seen.add(i.text);
            return true;
        }).sort(function(a,b) { return a.x - b.x; });
    }""")
    print(f"\\n  Layer tools bar items ({len(layer_tools)}):", flush=True)
    for lt in layer_tools:
        print(f"    ({lt['x']},{lt['y']}) <{lt['tag']}> c='{lt['classes'][:22]}' '{lt['text']}'", flush=True)

    # ============================================================
    #  PART 3: PROJECT SETTINGS (CANVAS SIZE CLICK)
    # ============================================================
    print("\\n" + "=" * 60, flush=True)
    print("  PART 3: PROJECT SETTINGS", flush=True)
    print("=" * 60, flush=True)

    # Click canvas size "1536 × 864"
    page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text.includes('1536') && r.y < 35 && r.x > 100 && r.x < 200) {
                el.click(); return true;
            }
        }
        return false;
    }""")
    page.wait_for_timeout(1000)

    ss(page, "P70_04_canvas_size")

    # Check for settings dialog
    size_dialog = page.evaluate("""() => {
        var items = [];
        for (const el of document.querySelectorAll('*')) {
            var style = window.getComputedStyle(el);
            var z = parseInt(style.zIndex) || 0;
            var r = el.getBoundingClientRect();
            var text = (el.innerText || '').trim();
            if (z > 200 && r.width > 100 && r.height > 50 && text.length > 3) {
                items.push({
                    text: text.substring(0, 100),
                    z: z, x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                });
            }
        }
        return items.sort(function(a,b) { return b.z - a.z; }).slice(0, 5);
    }""")
    print(f"  Size dialog ({len(size_dialog)}):", flush=True)
    for d in size_dialog:
        print(f"    z={d['z']} ({d['x']},{d['y']}) {d['w']}x{d['h']} '{d['text'][:60]}'", flush=True)

    page.keyboard.press("Escape")
    page.wait_for_timeout(300)

    # Click project name "Untitled"
    page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text === 'Untitled' && r.y < 35 && r.x > 40 && r.x < 120) {
                el.click(); return true;
            }
        }
        return false;
    }""")
    page.wait_for_timeout(1000)

    ss(page, "P70_05_project_name")

    # Check if name became editable
    name_edit = page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            if (r.y < 35 && r.x > 40 && r.x < 200
                && (el.contentEditable === 'true' || el.tagName === 'INPUT')) {
                return {
                    tag: el.tagName,
                    editable: el.contentEditable,
                    value: (el.value || el.innerText || '').substring(0, 30),
                    x: Math.round(r.x), y: Math.round(r.y),
                };
            }
        }
        return null;
    }""")
    print(f"  Name editable: {name_edit}", flush=True)

    page.keyboard.press("Escape")
    page.wait_for_timeout(300)

    ss(page, "P70_06_final")

    print(f"\\n\\n===== PHASE 70 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
