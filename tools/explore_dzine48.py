"""Phase 48: Test model selection + Insert Character + Upload to canvas workflows.

From P47: Model picker has 18 categories, "Realistic Product" is available.
Insert Character puts Ray into existing images. Upload sidebar puts images on canvas.
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
    page.wait_for_timeout(5000)
    close_dialogs(page)

    # ============================================================
    #  PART 1: SELECT "REALISTIC PRODUCT" MODEL IN TXT2IMG
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 1: SELECT REALISTIC PRODUCT MODEL", flush=True)
    print("=" * 60, flush=True)

    page.mouse.click(40, 197)  # Txt2Img
    page.wait_for_timeout(2000)
    close_dialogs(page)

    # Get current model name
    current_model = page.evaluate("""() => {
        var el = document.querySelector('.style-name');
        return el ? el.innerText.trim() : 'unknown';
    }""")
    print(f"  Current model: {current_model}", flush=True)

    # Open model picker
    page.evaluate("""() => {
        var btn = document.querySelector('button.style');
        if (btn) btn.click();
    }""")
    page.wait_for_timeout(2000)

    # Click "Realistic" category in the picker
    cat_clicked = page.evaluate("""() => {
        for (const el of document.querySelectorAll('.left-filter-item, .filter-item, [class*="category-item"]')) {
            var text = (el.innerText || '').trim();
            if (text === 'Realistic') {
                el.click();
                return true;
            }
        }
        return false;
    }""")
    print(f"  Realistic category clicked: {cat_clicked}", flush=True)
    page.wait_for_timeout(1000)

    # Click "Realistic Product" model card
    model_selected = page.evaluate("""() => {
        for (const el of document.querySelectorAll('.style-name, .model-name, .name')) {
            var text = (el.innerText || '').trim();
            if (text === 'Realistic Product') {
                // Click the parent card (the clickable container)
                var target = el;
                for (var i = 0; i < 3; i++) {
                    target = target.parentElement;
                    if (!target) break;
                    var r = target.getBoundingClientRect();
                    if (r.width > 80 && r.height > 80) {
                        target.click();
                        return true;
                    }
                }
                // If no good parent, click the element itself
                el.click();
                return true;
            }
        }
        return false;
    }""")
    print(f"  Realistic Product selected: {model_selected}", flush=True)
    page.wait_for_timeout(2000)

    ss(page, "P48_01_after_model_select")

    # Verify model changed
    new_model = page.evaluate("""() => {
        var el = document.querySelector('.style-name');
        return el ? el.innerText.trim() : 'unknown';
    }""")
    print(f"  Model after selection: {new_model}", flush=True)

    # Check if picker closed
    picker_open = page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            var z = parseInt(window.getComputedStyle(el).zIndex) || 0;
            var r = el.getBoundingClientRect();
            if (z > 900 && r.width > 400 && r.height > 400) return true;
        }
        return false;
    }""")
    print(f"  Picker still open: {picker_open}", flush=True)
    if picker_open:
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)

    # Switch back to Nano Banana Pro (default)
    print("\n  Switching back to original model...", flush=True)
    page.evaluate("""() => {
        var btn = document.querySelector('button.style');
        if (btn) btn.click();
    }""")
    page.wait_for_timeout(2000)

    # Click "General" category then select Nano Banana Pro
    page.evaluate("""() => {
        for (const el of document.querySelectorAll('.left-filter-item, .filter-item, [class*="category-item"]')) {
            if ((el.innerText || '').trim() === 'General') { el.click(); return; }
        }
    }""")
    page.wait_for_timeout(1000)

    page.evaluate("""() => {
        for (const el of document.querySelectorAll('.style-name')) {
            if ((el.innerText || '').trim() === 'Nano Banana Pro') {
                var target = el;
                for (var i = 0; i < 3; i++) {
                    target = target.parentElement;
                    if (!target) break;
                    var r = target.getBoundingClientRect();
                    if (r.width > 80 && r.height > 80) { target.click(); return; }
                }
                el.click(); return;
            }
        }
    }""")
    page.wait_for_timeout(1000)
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)

    restored = page.evaluate("""() => {
        var el = document.querySelector('.style-name');
        return el ? el.innerText.trim() : 'unknown';
    }""")
    print(f"  Model restored: {restored}", flush=True)

    # ============================================================
    #  PART 2: INSERT CHARACTER WORKFLOW
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 2: INSERT CHARACTER", flush=True)
    print("=" * 60, flush=True)

    # Check results panel for "Insert Character" buttons
    insert_btns = page.evaluate("""() => {
        var items = [];
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text === 'Insert Character' && r.x > 500 && r.width > 80) {
                items.push({
                    tag: el.tagName,
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    classes: (el.className || '').toString().substring(0, 40),
                });
            }
        }
        return items;
    }""")
    print(f"  Insert Character labels ({len(insert_btns)}):", flush=True)
    for b in insert_btns[:5]:
        print(f"    ({b['x']},{b['y']}) {b['w']}x{b['h']} <{b['tag']}> c='{b['classes']}'", flush=True)

    # Find the variant buttons (1, 2) next to "Insert Character"
    variant_btns = page.evaluate("""() => {
        var items = [];
        for (const btn of document.querySelectorAll('button')) {
            var text = (btn.innerText || '').trim();
            var r = btn.getBoundingClientRect();
            // Variant buttons are "1" or "2", small, in the results panel
            if ((text === '1' || text === '2') && r.x > 1200 && r.width > 30 && r.width < 80
                && r.height > 15 && r.height < 35) {
                // Check if this is near an "Insert Character" label (y within 10px)
                var nearIC = false;
                for (const el of document.querySelectorAll('*')) {
                    var et = (el.innerText || '').trim();
                    var er = el.getBoundingClientRect();
                    if (et === 'Insert Character' && Math.abs(er.y - r.y) < 15) {
                        nearIC = true; break;
                    }
                }
                if (nearIC) {
                    items.push({
                        text: text,
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        classes: (btn.className || '').toString().substring(0, 30),
                    });
                }
            }
        }
        return items;
    }""")
    print(f"  Insert Character variant buttons ({len(variant_btns)}):", flush=True)
    for b in variant_btns:
        print(f"    '{b['text']}' ({b['x']},{b['y']}) {b['w']}x{b['h']} c='{b['classes']}'", flush=True)

    # Click the first "1" variant button for Insert Character
    if variant_btns:
        btn1 = next((b for b in variant_btns if b['text'] == '1'), variant_btns[0])
        print(f"\n  Clicking Insert Character variant '{btn1['text']}' at ({btn1['x']},{btn1['y']})...", flush=True)
        page.mouse.click(btn1['x'] + btn1['w'] // 2, btn1['y'] + btn1['h'] // 2)
        page.wait_for_timeout(3000)
        close_dialogs(page)

        ss(page, "P48_02_insert_character")

        # Check what happened — should open a new panel or start a generation
        ic_state = page.evaluate("""() => {
            // Check for new panel or dialog
            var panels = [];
            for (const el of document.querySelectorAll('*')) {
                var r = el.getBoundingClientRect();
                var text = (el.innerText || '').trim();
                if (r.x > 50 && r.x < 360 && r.y > 50 && r.y < 200 && r.width > 200
                    && text.length > 5 && text.length < 50
                    && el.tagName !== 'HTML' && el.tagName !== 'BODY') {
                    panels.push({
                        tag: el.tagName,
                        text: text.substring(0, 40),
                        x: Math.round(r.x), y: Math.round(r.y),
                        classes: (el.className || '').toString().substring(0, 30),
                    });
                }
            }
            // Check top bar for mode
            var topBar = [];
            for (const el of document.querySelectorAll('*')) {
                var r = el.getBoundingClientRect();
                var text = (el.innerText || '').trim();
                if (r.y < 50 && r.x > 100 && r.x < 800 && r.width > 50
                    && text.length > 3 && text.length < 40) {
                    topBar.push({text: text, x: Math.round(r.x)});
                }
            }
            return {panels: panels.slice(0, 5), topBar: topBar.slice(0, 10)};
        }""")
        print(f"  Panel titles: {[p['text'] for p in ic_state['panels']]}", flush=True)
        print(f"  Top bar: {[t['text'] for t in ic_state['topBar']]}", flush=True)

        # Dump the left panel fully
        ic_panel = page.evaluate("""() => {
            var items = [];
            for (const el of document.querySelectorAll('*')) {
                var r = el.getBoundingClientRect();
                if (r.x > 50 && r.x < 360 && r.y > 50 && r.y < 900
                    && r.width > 15 && r.height > 8 && r.width < 350
                    && !['path','line','circle','g','svg','defs','rect','polygon'].includes(el.tagName.toLowerCase())) {
                    var text = (el.innerText || '').trim();
                    if (text.length > 0 && text.length < 40) {
                        items.push({
                            tag: el.tagName,
                            x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height),
                            text: text.substring(0, 30),
                            classes: (el.className || '').toString().substring(0, 25),
                        });
                    }
                }
            }
            var seen = new Set();
            return items.filter(function(i) {
                var key = i.text.substring(0,12) + '|' + i.x + '|' + i.y;
                if (seen.has(key)) return false;
                seen.add(key);
                return true;
            }).sort(function(a,b) { return a.y - b.y; }).slice(0, 40);
        }""")
        print(f"\n  Insert Character panel ({len(ic_panel)}):", flush=True)
        for el in ic_panel[:40]:
            print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> c='{el['classes'][:20]}' '{el['text'][:25]}'", flush=True)

    else:
        print("  No Insert Character buttons found in results panel.", flush=True)

    # ============================================================
    #  PART 3: UPLOAD IMAGE TO CANVAS VIA SIDEBAR
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 3: UPLOAD TO CANVAS VIA SIDEBAR", flush=True)
    print("=" * 60, flush=True)

    # Go back to main state
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)
    close_dialogs(page)

    # Click Upload sidebar
    page.mouse.click(40, 81)
    page.wait_for_timeout(2000)
    close_dialogs(page)

    ss(page, "P48_03_upload_sidebar")

    # Dump Upload panel
    upload_panel = page.evaluate("""() => {
        var items = [];
        for (const el of document.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            if (r.x > 50 && r.x < 360 && r.y > 50 && r.y < 500
                && r.width > 15 && r.height > 8 && r.width < 350
                && !['path','line','circle','g','svg','defs','rect','polygon'].includes(el.tagName.toLowerCase())) {
                var text = (el.innerText || '').trim();
                var cursor = window.getComputedStyle(el).cursor;
                var border = window.getComputedStyle(el).borderStyle;
                if (text.length > 0 && text.length < 60) {
                    items.push({
                        tag: el.tagName,
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        text: text.substring(0, 35),
                        classes: (el.className || '').toString().substring(0, 30),
                        cursor: cursor !== 'auto' && cursor !== 'default' ? cursor : '',
                        border: border.includes('dashed') ? 'dashed' : '',
                    });
                }
            }
        }
        var seen = new Set();
        return items.filter(function(i) {
            var key = i.text.substring(0,12) + '|' + i.x + '|' + i.y;
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
        }).sort(function(a,b) { return a.y - b.y; });
    }""")
    print(f"\n  Upload panel ({len(upload_panel)}):", flush=True)
    for el in upload_panel[:20]:
        extras = []
        if el['cursor']: extras.append(f"cur={el['cursor']}")
        if el['border']: extras.append(f"border={el['border']}")
        extra_str = ' ' + ' '.join(extras) if extras else ''
        print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> c='{el['classes'][:20]}'{extra_str} '{el['text'][:25]}'", flush=True)

    # Find the upload zone (button or div with upload text)
    upload_zone = page.evaluate("""() => {
        // Look for upload button or drop zone
        for (const el of document.querySelectorAll('button, div, label')) {
            var classes = (el.className || '').toString();
            var r = el.getBoundingClientRect();
            if ((classes === 'upload' || classes.includes('upload-zone')
                 || classes.includes('drop-zone') || classes.includes('upload-area'))
                && r.width > 100 && r.height > 30 && r.x > 50 && r.x < 360) {
                return {
                    tag: el.tagName,
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    classes: classes.substring(0, 60),
                };
            }
        }
        // Try by text
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if ((text.includes('Drop') || text.includes('upload') || text.includes('Upload'))
                && r.x > 50 && r.x < 360 && r.width > 100 && r.height > 20
                && el.children.length < 5) {
                return {
                    tag: el.tagName,
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    text: text.substring(0, 60),
                    classes: (el.className || '').toString().substring(0, 60),
                };
            }
        }
        return null;
    }""")
    print(f"\n  Upload zone: {upload_zone}", flush=True)

    # Try to trigger file chooser on the upload zone
    if upload_zone:
        cx = upload_zone['x'] + upload_zone['w'] // 2
        cy = upload_zone['y'] + upload_zone['h'] // 2
        print(f"  Clicking upload zone at ({cx}, {cy})...", flush=True)

        try:
            with page.expect_file_chooser(timeout=5000) as fc_info:
                page.mouse.click(cx, cy)
            fc = fc_info.value
            print(f"  *** FILE CHOOSER! *** Multiple={fc.is_multiple}", flush=True)
            # Don't actually upload — just confirming the mechanism works
            fc.set_files([])  # Cancel
            print("  File chooser works for canvas upload!", flush=True)
        except Exception as e:
            print(f"  No file chooser: {e}", flush=True)

    # ============================================================
    #  PART 4: ASSETS SIDEBAR
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 4: ASSETS SIDEBAR", flush=True)
    print("=" * 60, flush=True)

    page.mouse.click(40, 136)  # Assets
    page.wait_for_timeout(2000)
    close_dialogs(page)

    ss(page, "P48_04_assets_sidebar")

    assets_panel = page.evaluate("""() => {
        var items = [];
        for (const el of document.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            if (r.x > 50 && r.x < 360 && r.y > 50 && r.y < 400
                && r.width > 15 && r.height > 8 && r.width < 350
                && !['path','line','circle','g','svg','defs','rect','polygon'].includes(el.tagName.toLowerCase())) {
                var text = (el.innerText || '').trim();
                if (text.length > 0 && text.length < 50) {
                    items.push({
                        tag: el.tagName,
                        x: Math.round(r.x), y: Math.round(r.y),
                        text: text.substring(0, 35),
                        classes: (el.className || '').toString().substring(0, 25),
                    });
                }
            }
        }
        var seen = new Set();
        return items.filter(function(i) {
            var key = i.text.substring(0,12) + '|' + i.y;
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
        }).sort(function(a,b) { return a.y - b.y; });
    }""")
    print(f"\n  Assets panel ({len(assets_panel)}):", flush=True)
    for el in assets_panel[:20]:
        print(f"    ({el['x']},{el['y']}) <{el['tag']}> c='{el['classes'][:20]}' '{el['text'][:30]}'", flush=True)

    # ============================================================
    #  PART 5: CC ASPECT RATIO "MORE" OPTIONS
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 5: CC ASPECT RATIO MORE OPTIONS", flush=True)
    print("=" * 60, flush=True)

    # Open CC panel
    page.mouse.click(40, 197)  # Txt2Img first
    page.wait_for_timeout(500)
    page.mouse.click(40, 306)  # Character
    page.wait_for_timeout(3000)
    close_dialogs(page)

    page.evaluate("""() => {
        for (const btn of document.querySelectorAll('button')) {
            if ((btn.innerText || '').trim().includes('Generate Images')) { btn.click(); return; }
        }
    }""")
    page.wait_for_timeout(2000)

    page.evaluate("""() => {
        for (const el of document.querySelectorAll('button')) {
            if ((el.innerText || '').trim() === 'Ray') { el.click(); return; }
        }
    }""")
    page.wait_for_timeout(2000)

    # Check for "more" button in CC aspect ratio area
    cc_more = page.evaluate("""() => {
        var items = [];
        for (const el of document.querySelectorAll('.item.more')) {
            var r = el.getBoundingClientRect();
            if (r.x > 50 && r.x < 360 && r.y > 600 && r.y < 800) {
                items.push({
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                });
            }
        }
        return items;
    }""")
    print(f"  CC more aspect ratio buttons ({len(cc_more)}):", flush=True)
    for m in cc_more:
        print(f"    ({m['x']},{m['y']}) {m['w']}x{m['h']}", flush=True)

    if cc_more:
        m = cc_more[0]
        page.mouse.click(m['x'] + m['w'] // 2, m['y'] + m['h'] // 2)
        page.wait_for_timeout(1500)

        ss(page, "P48_05_cc_more_ar")

        # Check what appeared
        cc_ar_options = page.evaluate("""() => {
            var items = [];
            for (const el of document.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                var r = el.getBoundingClientRect();
                // Look for the expanded ratio options
                if (r.x > 100 && r.x < 600 && r.y > 400 && r.y < 700
                    && r.width > 30 && r.height > 15 && text.length > 1 && text.length < 20
                    && (text.includes(':') || text.includes('x'))) {
                    items.push({
                        text: text,
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        classes: (el.className || '').toString().substring(0, 30),
                    });
                }
            }
            var seen = new Set();
            return items.filter(function(i) {
                var key = i.text + '|' + i.y;
                if (seen.has(key)) return false;
                seen.add(key);
                return true;
            }).sort(function(a,b) { return a.y - b.y; });
        }""")
        print(f"\n  CC aspect ratio options ({len(cc_ar_options)}):", flush=True)
        for opt in cc_ar_options[:20]:
            print(f"    ({opt['x']},{opt['y']}) {opt['w']}x{opt['h']} c='{opt['classes'][:20]}' '{opt['text']}'", flush=True)

        page.keyboard.press("Escape")
        page.wait_for_timeout(500)

    ss(page, "P48_06_final")
    print(f"\n\n===== PHASE 48 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
