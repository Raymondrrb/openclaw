"""Phase 72: Full Expression Edit mapping — Custom sliders + Template presets.

Phase 71 confirmed Expression Edit opens via: click face on canvas → click toolbar "Expression".
The panel has Custom/Template tabs. Custom shows Eyes/Mouth sections with sliders.
Now we need:
1. Open Expression Edit reliably (click face → toolbar Expression)
2. Map ALL Custom sliders (scroll down for full list)
3. Click Template tab and map all template presets
4. Test Done/Cancel
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
    #  STEP 1: SELECT IMAGE LAYER WITH FACE
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  STEP 1: SELECT IMAGE LAYER & OPEN EXPRESSION EDIT", flush=True)
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
    page.wait_for_timeout(500)

    # Click the FIRST non-text layer (image layer with face)
    # From Phase 71: we need an image layer, not text
    layer_clicked = page.evaluate("""() => {
        var layers = document.querySelectorAll('button.layer-item');
        for (const btn of layers) {
            var text = (btn.innerText || '').trim();
            // Skip text layers — look for image layers
            if (text.includes('Layer') && !text.toLowerCase().includes('text')) {
                btn.click();
                return text.substring(0, 30);
            }
        }
        // Fallback: click first layer
        if (layers.length > 0) {
            layers[0].click();
            return (layers[0].innerText || '').substring(0, 30);
        }
        return null;
    }""")
    print(f"  Layer clicked: {layer_clicked}", flush=True)
    page.wait_for_timeout(1000)

    # Click on the face in the canvas to ensure the image layer is selected
    page.mouse.click(550, 350)
    page.wait_for_timeout(500)

    # Check layer tools bar
    tools_visible = page.evaluate("""() => {
        var bar = document.querySelector('.layer-tools');
        if (!bar) return false;
        var r = bar.getBoundingClientRect();
        return r.width > 100 && r.height > 20;
    }""")
    print(f"  Layer tools visible: {tools_visible}", flush=True)

    # Click Expression in toolbar
    expr_clicked = page.evaluate("""() => {
        var bar = document.querySelector('.layer-tools');
        if (!bar) return null;
        for (const btn of bar.querySelectorAll('*')) {
            var text = (btn.innerText || '').trim();
            if (text === 'Expression') {
                btn.click();
                var r = btn.getBoundingClientRect();
                return {x: Math.round(r.x), y: Math.round(r.y), tag: btn.tagName};
            }
        }
        return null;
    }""")
    print(f"  Expression toolbar clicked: {expr_clicked}", flush=True)
    page.wait_for_timeout(5000)  # Give it more time to load
    close_dialogs(page)

    ss(page, "P72_01_expression_opened")

    # Check if Expression Edit panel opened — look for "Expression Edit" header anywhere
    header = page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            if (text === 'Expression Edit' && el.offsetParent !== null) {
                var r = el.getBoundingClientRect();
                if (r.height < 40 && r.width < 200) {
                    return {text: text, x: Math.round(r.x), y: Math.round(r.y),
                            tag: el.tagName, classes: (el.className || '').toString().substring(0, 40)};
                }
            }
        }
        return null;
    }""")
    print(f"  Expression Edit header: {header}", flush=True)

    if not header:
        # Try alternative: click "Expression Edit" row "1" button in Results panel
        print("  Trying Results panel approach...", flush=True)

        # Switch to Results first
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

        # Scroll to Expression Edit row and click "1"
        expr_found = page.evaluate("""() => {
            // Find "Expression Edit" text in the results panel
            for (const el of document.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                if (text === 'Expression Edit') {
                    var r = el.getBoundingClientRect();
                    if (r.x > 500 && r.y > 50) {
                        // Found it — now find the "1" button nearby
                        var parent = el.closest('.result-item') || el.parentElement;
                        if (parent) {
                            var buttons = parent.querySelectorAll('button, [role="button"], span');
                            for (var btn of buttons) {
                                var bt = (btn.innerText || '').trim();
                                if (bt === '1') {
                                    btn.click();
                                    return {text: 'Expression Edit → 1', x: Math.round(r.x), y: Math.round(r.y)};
                                }
                            }
                        }
                        // Fallback: click the row itself
                        el.click();
                        return {text: 'Expression Edit row clicked', x: Math.round(r.x), y: Math.round(r.y)};
                    }
                }
            }
            return null;
        }""")
        print(f"  Expression Edit via Results: {expr_found}", flush=True)
        page.wait_for_timeout(5000)
        close_dialogs(page)

        # Re-check header
        header = page.evaluate("""() => {
            for (const el of document.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                if (text === 'Expression Edit' && el.offsetParent !== null) {
                    var r = el.getBoundingClientRect();
                    if (r.height < 40 && r.width < 200) {
                        return {text: text, x: Math.round(r.x), y: Math.round(r.y)};
                    }
                }
            }
            return null;
        }""")
        print(f"  Header after retry: {header}", flush=True)

    ss(page, "P72_02_expression_panel")

    if not header:
        print("  FAILED to open Expression Edit. Dumping visible UI...", flush=True)
        # Dump the full left panel area
        items = page.evaluate("""() => {
            var items = [];
            for (const el of document.querySelectorAll('*')) {
                var r = el.getBoundingClientRect();
                if (r.x >= 0 && r.x <= 250 && r.y >= 30 && r.y <= 700
                    && r.width > 10 && r.height > 8 && r.width < 300) {
                    var text = (el.innerText || '').trim();
                    if (text.length > 0 && text.length < 50 && text.indexOf('\\n') === -1) {
                        items.push({
                            tag: el.tagName, x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height),
                            text: text.substring(0, 40),
                            classes: (el.className || '').toString().substring(0, 30),
                        });
                    }
                }
            }
            var seen = new Set();
            return items.filter(function(i) {
                var key = i.text.substring(0, 15) + '|' + i.x + '|' + i.y;
                if (seen.has(key)) return false;
                seen.add(key);
                return true;
            }).sort(function(a,b) { return a.y - b.y; }).slice(0, 40);
        }""")
        print(f"  Left panel elements ({len(items)}):", flush=True)
        for el in items:
            print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> '{el['text'][:35]}'", flush=True)
        # Exit early since we can't proceed
        print("\n===== PHASE 72 INCOMPLETE (Expression Edit didn't open) =====", flush=True)
        sys.stdout.flush()
        os._exit(0)

    # ============================================================
    #  STEP 2: MAP ALL CUSTOM SLIDERS
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  STEP 2: MAP ALL CUSTOM SLIDERS", flush=True)
    print("=" * 60, flush=True)

    # Find the scrollable panel for Custom mode
    # Get all visible sliders/controls in the left panel
    custom_sliders = page.evaluate("""() => {
        var items = [];
        // Look for all elements in the left panel that look like slider labels
        for (const el of document.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            if (r.x >= 5 && r.x <= 200 && r.y >= 60 && r.y <= 900
                && r.width > 30 && r.height >= 12 && r.height <= 30
                && r.width < 200) {
                var text = (el.innerText || '').trim();
                if (text.length > 2 && text.length < 40 && text.indexOf('\\n') === -1) {
                    items.push({
                        tag: el.tagName, x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        text: text,
                        classes: (el.className || '').toString().substring(0, 35),
                    });
                }
            }
        }
        var seen = new Set();
        return items.filter(function(i) {
            var key = i.text + '|' + Math.round(i.y / 5);
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
        }).sort(function(a,b) { return a.y - b.y; }).slice(0, 50);
    }""")
    print(f"  Custom mode elements ({len(custom_sliders)}):", flush=True)
    for el in custom_sliders:
        print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} '{el['text']}'", flush=True)

    # Scroll down in the panel to reveal more sliders
    # Find the scrollable container
    scroll_result = page.evaluate("""() => {
        // Find scrollable container in left panel
        for (const el of document.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            if (r.x >= 0 && r.x <= 20 && r.width > 150 && r.width < 250
                && el.scrollHeight > el.clientHeight + 20) {
                return {
                    tag: el.tagName,
                    classes: (el.className || '').toString().substring(0, 50),
                    scrollHeight: el.scrollHeight,
                    clientHeight: el.clientHeight,
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                };
            }
        }
        return null;
    }""")
    print(f"\n  Scrollable container: {scroll_result}", flush=True)

    # Scroll down in the panel to see more sliders
    if scroll_result:
        # Scroll using mouse wheel over the panel
        page.mouse.move(100, 500)
        page.mouse.wheel(0, 400)
        page.wait_for_timeout(500)

        # Get sliders after scroll
        after_scroll = page.evaluate("""() => {
            var items = [];
            for (const el of document.querySelectorAll('*')) {
                var r = el.getBoundingClientRect();
                if (r.x >= 5 && r.x <= 200 && r.y >= 60 && r.y <= 900
                    && r.width > 30 && r.height >= 12 && r.height <= 30
                    && r.width < 200) {
                    var text = (el.innerText || '').trim();
                    if (text.length > 2 && text.length < 40 && text.indexOf('\\n') === -1) {
                        items.push({
                            tag: el.tagName, x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height),
                            text: text,
                        });
                    }
                }
            }
            var seen = new Set();
            return items.filter(function(i) {
                var key = i.text + '|' + Math.round(i.y / 5);
                if (seen.has(key)) return false;
                seen.add(key);
                return true;
            }).sort(function(a,b) { return a.y - b.y; }).slice(0, 50);
        }""")
        print(f"\n  After scroll down ({len(after_scroll)}):", flush=True)
        for el in after_scroll:
            print(f"    ({el['x']},{el['y']}) '{el['text']}'", flush=True)

        ss(page, "P72_03_custom_scrolled")

        # Scroll down more to see any remaining sliders
        page.mouse.wheel(0, 400)
        page.wait_for_timeout(500)

        after_scroll2 = page.evaluate("""() => {
            var items = [];
            for (const el of document.querySelectorAll('*')) {
                var r = el.getBoundingClientRect();
                if (r.x >= 5 && r.x <= 200 && r.y >= 60 && r.y <= 900
                    && r.width > 30 && r.height >= 12 && r.height <= 30
                    && r.width < 200) {
                    var text = (el.innerText || '').trim();
                    if (text.length > 2 && text.length < 40 && text.indexOf('\\n') === -1) {
                        items.push({
                            tag: el.tagName, x: Math.round(r.x), y: Math.round(r.y),
                            text: text,
                        });
                    }
                }
            }
            var seen = new Set();
            return items.filter(function(i) {
                var key = i.text + '|' + Math.round(i.y / 5);
                if (seen.has(key)) return false;
                seen.add(key);
                return true;
            }).sort(function(a,b) { return a.y - b.y; }).slice(0, 50);
        }""")
        print(f"\n  After scroll down x2 ({len(after_scroll2)}):", flush=True)
        for el in after_scroll2:
            print(f"    ({el['x']},{el['y']}) '{el['text']}'", flush=True)

        ss(page, "P72_04_custom_scrolled2")

    # Scroll back to top
    page.mouse.move(100, 300)
    page.mouse.wheel(0, -2000)
    page.wait_for_timeout(500)

    # ============================================================
    #  STEP 3: CLICK TEMPLATE TAB
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  STEP 3: TEMPLATE TAB", flush=True)
    print("=" * 60, flush=True)

    template_clicked = page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text === 'Template' && r.x >= 80 && r.x <= 200
                && r.y >= 200 && r.y <= 300) {
                el.click();
                return {x: Math.round(r.x), y: Math.round(r.y), tag: el.tagName};
            }
        }
        // Broader search
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text === 'Template' && r.x < 250 && r.y > 100 && r.height < 40) {
                el.click();
                return {x: Math.round(r.x), y: Math.round(r.y), tag: el.tagName, note: 'broad'};
            }
        }
        return null;
    }""")
    print(f"  Template tab clicked: {template_clicked}", flush=True)
    page.wait_for_timeout(1500)

    ss(page, "P72_05_template_tab")

    # Map all template items — look for images, labels, grid items
    templates = page.evaluate("""() => {
        var items = [];
        for (const el of document.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            if (r.x >= 5 && r.x <= 250 && r.y >= 200 && r.y <= 900
                && r.width > 20 && r.height > 20) {
                var text = (el.innerText || '').trim();
                var classes = (el.className || '').toString();
                var info = {
                    tag: el.tagName, x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    text: text.substring(0, 30),
                    classes: classes.substring(0, 40),
                };
                if (el.tagName === 'IMG') {
                    info.src = (el.src || '').substring(0, 80);
                    info.alt = (el.alt || '').substring(0, 30);
                }
                if (el.style && el.style.backgroundImage) {
                    info.bgImg = el.style.backgroundImage.substring(0, 80);
                }
                items.push(info);
            }
        }
        var seen = new Set();
        return items.filter(function(i) {
            var key = i.tag + '|' + i.x + '|' + i.y;
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
        }).sort(function(a,b) { return a.y - b.y || a.x - b.x; }).slice(0, 60);
    }""")
    print(f"\n  Template elements ({len(templates)}):", flush=True)
    for t in templates:
        extra = ''
        if t.get('src'): extra += f" src={t['src']}"
        if t.get('alt'): extra += f" alt={t['alt']}"
        if t.get('bgImg'): extra += f" bg={t['bgImg']}"
        print(f"    ({t['x']},{t['y']}) {t['w']}x{t['h']} <{t['tag']}> c='{t.get('classes', '')[:25]}' '{t['text'][:25]}'{extra}", flush=True)

    # Scroll template area for more
    page.mouse.move(100, 500)
    page.mouse.wheel(0, 400)
    page.wait_for_timeout(500)

    templates2 = page.evaluate("""() => {
        var items = [];
        for (const el of document.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            if (r.x >= 5 && r.x <= 250 && r.y >= 200 && r.y <= 900
                && r.width > 20 && r.height > 20) {
                var text = (el.innerText || '').trim();
                var info = {
                    tag: el.tagName, x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    text: text.substring(0, 30),
                    classes: (el.className || '').toString().substring(0, 40),
                };
                if (el.tagName === 'IMG') {
                    info.src = (el.src || '').substring(0, 80);
                    info.alt = (el.alt || '').substring(0, 30);
                }
                items.push(info);
            }
        }
        var seen = new Set();
        return items.filter(function(i) {
            var key = i.tag + '|' + i.x + '|' + i.y;
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
        }).sort(function(a,b) { return a.y - b.y || a.x - b.x; }).slice(0, 60);
    }""")
    print(f"\n  Template after scroll ({len(templates2)}):", flush=True)
    for t in templates2:
        extra = ''
        if t.get('src'): extra += f" src={t['src']}"
        if t.get('alt'): extra += f" alt={t['alt']}"
        print(f"    ({t['x']},{t['y']}) {t['w']}x{t['h']} <{t['tag']}> '{t['text'][:25]}'{extra}", flush=True)

    ss(page, "P72_06_template_scrolled")

    # ============================================================
    #  STEP 4: DONE/CANCEL BUTTONS
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  STEP 4: DONE / CANCEL BUTTONS", flush=True)
    print("=" * 60, flush=True)

    buttons = page.evaluate("""() => {
        var items = [];
        for (const el of document.querySelectorAll('button, [role="button"]')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if ((text === 'Done' || text === 'Cancel') && r.y < 50) {
                items.push({
                    text: text, x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    tag: el.tagName,
                    classes: (el.className || '').toString().substring(0, 50),
                });
            }
        }
        return items;
    }""")
    print(f"  Action buttons:", flush=True)
    for b in buttons:
        print(f"    '{b['text']}' at ({b['x']},{b['y']}) {b['w']}x{b['h']} <{b['tag']}> c='{b['classes'][:35]}'", flush=True)

    # Click Cancel to exit Expression Edit without saving
    cancel = page.evaluate("""() => {
        for (const el of document.querySelectorAll('button, [role="button"]')) {
            var text = (el.innerText || '').trim();
            if (text === 'Cancel' && el.getBoundingClientRect().y < 50) {
                el.click();
                return true;
            }
        }
        return false;
    }""")
    print(f"  Cancel clicked: {cancel}", flush=True)
    page.wait_for_timeout(2000)

    ss(page, "P72_07_after_cancel")

    # Verify we're back to normal canvas
    back = page.evaluate("""() => {
        // Check if Results/Layers tabs are visible again
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text === 'Results' && r.x > 500 && r.y < 60) return 'Results tab visible';
        }
        return 'unknown';
    }""")
    print(f"  After cancel: {back}", flush=True)

    print(f"\n\n===== PHASE 72 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
