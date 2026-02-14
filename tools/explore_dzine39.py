"""Phase 39: Robust Reference mode + file upload — fixed timing and ranges.

Simple sequential approach with long waits and wide search ranges.
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
    page.wait_for_timeout(5000)  # Extra long wait for full page load
    close_dialogs(page)

    # ============================================================
    #  STEP 1: Navigate to CC panel and dump ALL buttons
    # ============================================================
    print("\n  Step 1: Open CC panel", flush=True)
    page.mouse.click(40, 306)
    page.wait_for_timeout(3000)
    close_dialogs(page)

    # Dump ALL visible buttons in the left panel
    all_btns = page.evaluate("""() => {
        var items = [];
        for (const btn of document.querySelectorAll('button')) {
            var r = btn.getBoundingClientRect();
            var text = (btn.innerText || '').trim();
            if (r.x > 30 && r.x < 350 && r.y > 0 && r.y < 900
                && r.width > 10 && r.height > 10 && text.length < 40) {
                items.push({
                    text: text || '(empty)',
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    classes: (btn.className || '').toString().substring(0, 40),
                });
            }
        }
        return items.sort(function(a,b) { return a.y - b.y; });
    }""")
    print(f"\n  ALL buttons in left panel ({len(all_btns)}):", flush=True)
    for btn in all_btns:
        print(f"    ({btn['x']},{btn['y']}) {btn['w']}x{btn['h']} c='{btn['classes'][:25]}' '{btn['text']}'", flush=True)

    ss(page, "P39_01_cc_panel")

    # ============================================================
    #  STEP 2: Click Reference — use exact button from dump
    # ============================================================
    print("\n  Step 2: Click Reference button", flush=True)
    ref_clicked = False
    for btn in all_btns:
        if btn['text'] == 'Reference':
            cx = btn['x'] + btn['w'] // 2
            cy = btn['y'] + btn['h'] // 2
            print(f"  Found Reference at ({btn['x']},{btn['y']}), clicking ({cx},{cy})...", flush=True)
            page.mouse.click(cx, cy)
            ref_clicked = True
            break

    if not ref_clicked:
        print("  Reference not found in buttons! Trying locator...", flush=True)
        try:
            page.locator('button:has-text("Reference")').click(timeout=3000)
            ref_clicked = True
            print("  Clicked via locator!", flush=True)
        except Exception as e:
            print(f"  Locator failed: {e}", flush=True)

    page.wait_for_timeout(3000)
    ss(page, "P39_02_reference_mode")

    # Dump buttons again to see if Pick Image appeared
    all_btns2 = page.evaluate("""() => {
        var items = [];
        for (const btn of document.querySelectorAll('button')) {
            var r = btn.getBoundingClientRect();
            var text = (btn.innerText || '').trim();
            if (r.x > 30 && r.x < 350 && r.y > 0 && r.y < 900
                && r.width > 10 && r.height > 10 && text.length < 40) {
                items.push({
                    text: text || '(empty)',
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    classes: (btn.className || '').toString().substring(0, 40),
                });
            }
        }
        return items.sort(function(a,b) { return a.y - b.y; });
    }""")
    print(f"\n  Buttons after Reference click ({len(all_btns2)}):", flush=True)
    for btn in all_btns2:
        print(f"    ({btn['x']},{btn['y']}) {btn['w']}x{btn['h']} c='{btn['classes'][:25]}' '{btn['text']}'", flush=True)

    # ============================================================
    #  STEP 3: Click Pick Image
    # ============================================================
    print("\n  Step 3: Click Pick Image", flush=True)
    pick_clicked = False
    for btn in all_btns2:
        if 'Pick Image' in btn['text'] or 'pick-image' in btn.get('classes', ''):
            cx = btn['x'] + btn['w'] // 2
            cy = btn['y'] + btn['h'] // 2
            print(f"  Found Pick Image at ({btn['x']},{btn['y']}), clicking ({cx},{cy})...", flush=True)
            page.mouse.click(cx, cy)
            pick_clicked = True
            break

    if not pick_clicked:
        print("  Pick Image not in buttons. Trying class selector...", flush=True)
        try:
            page.locator('.pick-image').click(timeout=3000)
            pick_clicked = True
            print("  Clicked via .pick-image class!", flush=True)
        except Exception:
            try:
                page.locator('button:has-text("Pick Image")').click(timeout=3000)
                pick_clicked = True
                print("  Clicked via text locator!", flush=True)
            except Exception as e:
                print(f"  All attempts failed: {e}", flush=True)

    page.wait_for_timeout(3000)
    ss(page, "P39_03_pick_dialog")

    # ============================================================
    #  STEP 4: Find and click the upload area in the dialog
    # ============================================================
    print("\n  Step 4: Find upload area in Pick Image dialog", flush=True)

    # Use broad search for ANY element mentioning "drop" or "select" in z>900
    upload_area = page.evaluate("""() => {
        for (const el of document.querySelectorAll('button, div, label, span')) {
            var z = parseInt(window.getComputedStyle(el).zIndex) || 0;
            // Walk up to find z
            var parent = el;
            while (parent && z <= 0) {
                z = parseInt(window.getComputedStyle(parent).zIndex) || 0;
                parent = parent.parentElement;
            }
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text.includes('Drop or select') && r.width > 100 && r.height > 20) {
                return {
                    tag: el.tagName,
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    z: z,
                    classes: (el.className || '').toString().substring(0, 60),
                };
            }
        }
        // Also check by class
        for (const el of document.querySelectorAll('.upload, [class*="upload"], [class*="drop-zone"], [class*="file-select"]')) {
            var r = el.getBoundingClientRect();
            if (r.width > 100 && r.height > 20 && r.x > 200 && r.y > 100 && r.y < 300) {
                return {
                    tag: el.tagName,
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    z: 0,
                    classes: (el.className || '').toString().substring(0, 60),
                };
            }
        }
        return null;
    }""")
    print(f"  Upload area: {upload_area}", flush=True)

    if upload_area:
        cx = upload_area['x'] + upload_area['w'] // 2
        cy = upload_area['y'] + upload_area['h'] // 2
        print(f"\n  Clicking upload area at ({cx}, {cy})...", flush=True)

        try:
            with page.expect_file_chooser(timeout=5000) as fc_info:
                page.mouse.click(cx, cy)

            fc = fc_info.value
            print(f"\n  *** FILE CHOOSER TRIGGERED! ***", flush=True)
            print(f"  Multiple: {fc.is_multiple}", flush=True)

            if TEST_IMAGE.exists():
                print(f"  Uploading: {TEST_IMAGE} ({TEST_IMAGE.stat().st_size} bytes)", flush=True)
                fc.set_files(str(TEST_IMAGE))
                page.wait_for_timeout(5000)
                ss(page, "P39_04_uploaded")

                # Check what happened
                result = page.evaluate("""() => {
                    var dialog = false;
                    for (const el of document.querySelectorAll('*')) {
                        if ((el.innerText || '').includes('Pick Image')
                            && parseInt(window.getComputedStyle(el).zIndex) > 900) {
                            dialog = true; break;
                        }
                    }
                    // Check for reference preview in CC panel
                    var refImg = null;
                    for (const img of document.querySelectorAll('img')) {
                        var r = img.getBoundingClientRect();
                        if (r.x > 60 && r.x < 300 && r.y > 300 && r.y < 600
                            && r.width > 30 && r.height > 30) {
                            refImg = {
                                src: (img.src || '').substring(0, 100),
                                x: Math.round(r.x), y: Math.round(r.y),
                                w: Math.round(r.width), h: Math.round(r.height),
                            };
                            break;
                        }
                    }
                    return {dialogOpen: dialog, refImg: refImg};
                }""")
                print(f"\n  Result:", flush=True)
                print(f"    Dialog open: {result['dialogOpen']}", flush=True)
                print(f"    Reference image: {result['refImg']}", flush=True)
        except Exception as e:
            print(f"  File chooser not triggered: {e}", flush=True)
    else:
        print("  No upload area found in dialog. Checking dialog state...", flush=True)

        # Full page dump of high-z elements
        hz = page.evaluate("""() => {
            var items = [];
            for (const el of document.querySelectorAll('*')) {
                var z = parseInt(window.getComputedStyle(el).zIndex) || 0;
                var r = el.getBoundingClientRect();
                if (z > 800 && r.width > 50 && r.height > 20) {
                    items.push({
                        z: z, tag: el.tagName,
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        text: (el.innerText || '').trim().substring(0, 80),
                    });
                }
            }
            return items.sort(function(a,b) { return b.z - a.z; }).slice(0, 10);
        }""")
        print(f"  High-z elements: {len(hz)}", flush=True)
        for el in hz:
            print(f"    z={el['z']} ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> '{el['text'][:50]}'", flush=True)

    # ============================================================
    #  STEP 5: Try canvas upload via Upload sidebar
    # ============================================================
    print("\n  Step 5: Canvas Upload sidebar", flush=True)
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)

    # Click Upload in sidebar
    page.mouse.click(37, 75)
    page.wait_for_timeout(3000)

    ss(page, "P39_05_upload_sidebar")

    # Check for the canvas upload button — wider search
    canvas_upload = page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            var classes = (el.className || '').toString();
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (classes === 'upload' && r.width > 100 && r.height > 30) {
                return {
                    tag: el.tagName,
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    text: text.substring(0, 40),
                };
            }
        }
        // Fallback: look for any large button/div in the canvas area
        for (const el of document.querySelectorAll('button')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if ((text.includes('upload') || text.includes('Upload') || text.includes('Drop'))
                && r.width > 100 && r.x > 200) {
                return {
                    tag: el.tagName,
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    text: text.substring(0, 40),
                };
            }
        }
        return null;
    }""")
    print(f"  Canvas upload zone: {canvas_upload}", flush=True)

    if canvas_upload:
        cx = canvas_upload['x'] + canvas_upload['w'] // 2
        cy = canvas_upload['y'] + canvas_upload['h'] // 2
        print(f"  Clicking canvas upload at ({cx}, {cy})...", flush=True)
        try:
            with page.expect_file_chooser(timeout=5000) as fc_info:
                page.mouse.click(cx, cy)
            fc = fc_info.value
            print(f"  *** CANVAS FILE CHOOSER! *** Multiple={fc.is_multiple}", flush=True)
            if TEST_IMAGE.exists():
                fc.set_files(str(TEST_IMAGE))
                page.wait_for_timeout(5000)
                ss(page, "P39_06_canvas_uploaded")
                print("  File uploaded to canvas!", flush=True)
        except Exception as e:
            print(f"  No file chooser: {e}", flush=True)

    ss(page, "P39_07_final")
    print(f"\n\n===== PHASE 39 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
