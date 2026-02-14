"""Phase 49: Upload to canvas + Insert Character + Face Match NEW.

Issues from P48:
- Upload sidebar didn't open (Txt2Img was still showing)
- Insert Character buttons not found (need to check results panel on right)
- Face Match NEW spotted at y=426 in Txt2Img

Fix: Click Upload sidebar from a clean state (no other panel open).
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

TEST_IMAGE = SS_DIR / "e2e31_thumbnail.png"


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
    #  PART 1: UPLOAD SIDEBAR — PROPER APPROACH
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 1: UPLOAD SIDEBAR", flush=True)
    print("=" * 60, flush=True)

    # First close any open panel by clicking the current active sidebar icon
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)

    # Click Upload sidebar icon at (40, 81)
    page.mouse.click(40, 81)
    page.wait_for_timeout(2000)
    close_dialogs(page)

    ss(page, "P49_01_upload_sidebar")

    # Check if the panel title is "Upload"
    panel_title = page.evaluate("""() => {
        for (const el of document.querySelectorAll('h5, .title, .gen-config-header')) {
            var r = el.getBoundingClientRect();
            var text = (el.innerText || '').trim();
            if (r.x > 50 && r.x < 360 && r.y > 40 && r.y < 100 && text.length > 2) {
                return text.substring(0, 30);
            }
        }
        return 'unknown';
    }""")
    print(f"  Panel title: '{panel_title}'", flush=True)

    # Full dump of the panel
    upload_panel = page.evaluate("""() => {
        var items = [];
        for (const el of document.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            if (r.x > 50 && r.x < 360 && r.y > 50 && r.y < 500
                && r.width > 15 && r.height > 8 && r.width < 350
                && !['path','line','circle','g','svg','defs','rect','polygon','clippath'].includes(el.tagName.toLowerCase())) {
                var text = (el.innerText || '').trim();
                var cursor = window.getComputedStyle(el).cursor;
                var border = window.getComputedStyle(el).borderStyle;
                items.push({
                    tag: el.tagName,
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    text: text.substring(0, 35) || '',
                    classes: (el.className || '').toString().substring(0, 35),
                    cursor: cursor !== 'auto' && cursor !== 'default' ? cursor : '',
                    dashed: border.includes('dashed') ? 'DASHED' : '',
                });
            }
        }
        var seen = new Set();
        return items.filter(function(i) {
            var key = i.tag + '|' + i.x + '|' + i.y + '|' + i.w + '|' + i.h;
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
        }).sort(function(a,b) { return a.y - b.y; });
    }""")
    print(f"\n  Panel elements ({len(upload_panel)}):", flush=True)
    for el in upload_panel[:30]:
        extras = []
        if el['cursor']: extras.append(f"cur={el['cursor']}")
        if el['dashed']: extras.append('DASHED')
        extra_str = ' ' + ' '.join(extras) if extras else ''
        print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> c='{el['classes'][:25]}'{extra_str} '{el['text'][:25]}'", flush=True)

    # Look for any clickable upload area
    upload_btns = page.evaluate("""() => {
        var items = [];
        for (const el of document.querySelectorAll('button, div, label')) {
            var classes = (el.className || '').toString();
            var r = el.getBoundingClientRect();
            var text = (el.innerText || '').trim();
            if (r.x > 50 && r.x < 360 && r.y > 50 && r.y < 400
                && r.width > 100 && r.height > 20
                && (classes.includes('upload') || text.includes('Drop') || text.includes('Upload')
                    || text.includes('drag') || text.includes('browse'))) {
                items.push({
                    tag: el.tagName,
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    text: text.substring(0, 40),
                    classes: classes.substring(0, 40),
                });
            }
        }
        return items;
    }""")
    print(f"\n  Upload buttons/areas ({len(upload_btns)}):", flush=True)
    for b in upload_btns:
        print(f"    ({b['x']},{b['y']}) {b['w']}x{b['h']} <{b['tag']}> c='{b['classes'][:30]}' '{b['text'][:30]}'", flush=True)

    # Try clicking the upload button to test file chooser
    for ub in upload_btns:
        if ub['w'] > 150 and ub['h'] > 30:
            cx = ub['x'] + ub['w'] // 2
            cy = ub['y'] + ub['h'] // 2
            print(f"\n  Testing file chooser on ({cx},{cy})...", flush=True)
            try:
                with page.expect_file_chooser(timeout=3000) as fc_info:
                    page.mouse.click(cx, cy)
                fc = fc_info.value
                print(f"  *** UPLOAD FILE CHOOSER WORKS! *** Multiple={fc.is_multiple}", flush=True)
                fc.set_files([])  # Cancel
                break
            except Exception as e:
                print(f"  No file chooser: {e}", flush=True)

    # ============================================================
    #  PART 2: FACE MATCH NEW FEATURE
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 2: FACE MATCH NEW", flush=True)
    print("=" * 60, flush=True)

    # Open Txt2Img panel
    page.mouse.click(40, 197)
    page.wait_for_timeout(2000)
    close_dialogs(page)

    # Scroll down to find Face Match
    face_match = page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text.includes('Face Match') && r.x > 50 && r.x < 360 && r.width > 100) {
                return {
                    text: text.substring(0, 40),
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    classes: (el.className || '').toString().substring(0, 40),
                };
            }
        }
        return null;
    }""")
    print(f"  Face Match element: {face_match}", flush=True)

    # Dump the full Txt2Img panel to see Face Match and other new features
    txt2img_full = page.evaluate("""() => {
        var items = [];
        for (const el of document.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            if (r.x > 50 && r.x < 360 && r.y > 380 && r.y < 700
                && r.width > 15 && r.height > 8 && r.width < 350
                && !['path','line','circle','g','svg','defs','rect','polygon','clippath'].includes(el.tagName.toLowerCase())) {
                var text = (el.innerText || '').trim();
                if (text.length > 0 && text.length < 50) {
                    items.push({
                        tag: el.tagName,
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        text: text.substring(0, 35),
                        classes: (el.className || '').toString().substring(0, 30),
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
    print(f"\n  Txt2Img panel y=380-700 ({len(txt2img_full)}):", flush=True)
    for el in txt2img_full[:30]:
        print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> c='{el['classes'][:20]}' '{el['text'][:30]}'", flush=True)

    ss(page, "P49_02_face_match")

    # ============================================================
    #  PART 3: RESULTS PANEL — INSERT CHARACTER BUTTONS
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 3: INSERT CHARACTER IN RESULTS", flush=True)
    print("=" * 60, flush=True)

    # Check right panel for results
    results_panel = page.evaluate("""() => {
        var items = [];
        for (const el of document.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            var text = (el.innerText || '').trim();
            // Results panel is on the right side (x > 500)
            if (r.x > 500 && r.width > 50 && r.height > 10
                && text.length > 3 && text.length < 40
                && r.y > 50 && r.y < 600
                && !['path','line','circle','g','svg','defs','HTML','BODY'].includes(el.tagName)) {
                var classes = (el.className || '').toString();
                if (classes.includes('action') || classes.includes('result')
                    || text === 'Insert Character' || text === 'Variation'
                    || text === 'Chat Editor' || text === 'Image Editor'
                    || text === 'AI Video' || text === 'Lip Sync'
                    || text === 'Expression Edit' || text === 'Face Swap'
                    || text === 'Enhance & Upscale') {
                    items.push({
                        text: text,
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        tag: el.tagName,
                        classes: classes.substring(0, 30),
                    });
                }
            }
        }
        return items.sort(function(a,b) { return a.y - b.y; }).slice(0, 20);
    }""")
    print(f"  Result action items ({len(results_panel)}):", flush=True)
    for r in results_panel:
        print(f"    ({r['x']},{r['y']}) {r['w']}x{r['h']} <{r['tag']}> c='{r['classes'][:20]}' '{r['text']}'", flush=True)

    # Also check for "1" and "2" buttons in the results panel
    variant_buttons = page.evaluate("""() => {
        var items = [];
        for (const btn of document.querySelectorAll('button')) {
            var text = (btn.innerText || '').trim();
            var r = btn.getBoundingClientRect();
            if ((text === '1' || text === '2') && r.x > 1100 && r.width > 40 && r.width < 90
                && r.height > 15 && r.height < 35 && r.y > 100) {
                items.push({
                    text: text,
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                });
            }
        }
        return items.sort(function(a,b) { return a.y - b.y; });
    }""")
    print(f"\n  Variant buttons ({len(variant_buttons)}):", flush=True)
    for v in variant_buttons[:20]:
        print(f"    '{v['text']}' ({v['x']},{v['y']}) {v['w']}x{v['h']}", flush=True)

    # Map which action each pair of buttons belongs to
    if variant_buttons:
        print("\n  Mapping variant buttons to actions:", flush=True)
        action_labels = page.evaluate("""() => {
            var items = [];
            for (const el of document.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                var r = el.getBoundingClientRect();
                if (r.x > 500 && r.x < 1200 && r.width > 50
                    && text.length > 3 && text.length < 30
                    && r.height > 10 && r.height < 30
                    && r.y > 100 && r.y < 600) {
                    var known = ['Variation', 'Insert Character', 'Chat Editor',
                                 'Image Editor', 'AI Video', 'Lip Sync',
                                 'Expression Edit', 'Face Swap', 'Enhance & Upscale'];
                    if (known.includes(text)) {
                        items.push({text: text, y: Math.round(r.y), x: Math.round(r.x)});
                    }
                }
            }
            return items.sort(function(a,b) { return a.y - b.y; });
        }""")

        for label in action_labels:
            # Find the closest "1" and "2" buttons (within 10px y)
            matching = [v for v in variant_buttons if abs(v['y'] - label['y']) < 15]
            btn_text = ', '.join([f"'{v['text']}' at ({v['x']},{v['y']})" for v in matching])
            print(f"    {label['text']} (y={label['y']}): {btn_text}", flush=True)

    ss(page, "P49_03_final")
    print(f"\n\n===== PHASE 49 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
