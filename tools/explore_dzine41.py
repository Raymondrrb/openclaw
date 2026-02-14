"""Phase 41: File upload — click exact position in Pick Image dialog.

From P40 screenshot, the Pick Image dialog is at approximately:
- Modal: 340-730 x, 150-530 y
- "Drop or select images here" area: centered, ~540,224
- Canvas thumbnail: ~380,340

Strategy: Open the dialog, click the drop zone at exact coordinates,
use expect_file_chooser to intercept.
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
    #  Open CC → Reference → Pick Image (reusing P40 approach)
    # ============================================================
    print("\n  Opening CC panel...", flush=True)

    # Click Txt2Img first then Character to ensure panel opens
    page.mouse.click(40, 197)  # Txt2Img
    page.wait_for_timeout(1000)
    page.mouse.click(40, 306)  # Character
    page.wait_for_timeout(3000)
    close_dialogs(page)

    # Click "Generate Images" if visible
    page.evaluate("""() => {
        for (const btn of document.querySelectorAll('button')) {
            if ((btn.innerText || '').trim().includes('Generate Images')) {
                btn.click(); return;
            }
        }
    }""")
    page.wait_for_timeout(2000)

    # Select Ray
    page.evaluate("""() => {
        for (const el of document.querySelectorAll('button, div')) {
            if ((el.innerText || '').trim() === 'Ray' && el.tagName === 'BUTTON') {
                el.click(); return;
            }
        }
    }""")
    page.wait_for_timeout(1500)

    # Click Reference button in the CC form
    page.evaluate("""() => {
        var form = document.querySelector('.gen-config-form') || document;
        for (const btn of form.querySelectorAll('button')) {
            var text = (btn.innerText || '').trim();
            var r = btn.getBoundingClientRect();
            if (text === 'Reference' && r.width > 40 && r.x > 60 && r.y > 200) {
                btn.click(); return;
            }
        }
    }""")
    page.wait_for_timeout(2000)

    ss(page, "P41_01_reference_mode")

    # Verify Reference mode
    ref_active = page.evaluate("""() => {
        for (const btn of document.querySelectorAll('button')) {
            var text = (btn.innerText || '').trim();
            var classes = (btn.className || '').toString();
            if (text === 'Reference' && (classes.includes('selected') || classes.includes('active'))) {
                return true;
            }
        }
        return false;
    }""")
    print(f"  Reference active: {ref_active}", flush=True)

    # Click Pick Image button
    pick = page.evaluate("""() => {
        for (const btn of document.querySelectorAll('button')) {
            var classes = (btn.className || '').toString();
            var text = (btn.innerText || '').trim();
            var r = btn.getBoundingClientRect();
            if (classes.includes('pick-image') && r.width > 50 && r.x > 60) {
                btn.click();
                return {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), visible: r.width > 0};
            }
        }
        return null;
    }""")
    print(f"  Pick Image: {pick}", flush=True)
    page.wait_for_timeout(2000)

    ss(page, "P41_02_pick_dialog")

    # ============================================================
    #  MAP THE DIALOG PRECISELY
    # ============================================================
    print("\n  Mapping Pick Image dialog...", flush=True)

    # Find the dashed-border upload zone
    drop_zone = page.evaluate("""() => {
        // Look for the element that contains "Drop or select images here"
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            if (text === 'Drop or select images here') {
                // This is the text node. The upload zone is the container.
                // Check parent chain for the dashed border / clickable area
                var target = el.parentElement;
                for (var i = 0; i < 3; i++) {
                    if (!target) break;
                    var r = target.getBoundingClientRect();
                    var style = window.getComputedStyle(target);
                    if (r.width > 200 && r.height > 30
                        && (style.border.includes('dashed') || style.cursor === 'pointer'
                            || target.tagName === 'BUTTON' || target.tagName === 'LABEL'
                            || target.onclick)) {
                        return {
                            tag: target.tagName,
                            x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height),
                            cursor: style.cursor,
                            border: style.borderStyle,
                            classes: (target.className || '').toString().substring(0, 60),
                        };
                    }
                    target = target.parentElement;
                }
                // If no good parent found, return the text element's parent
                var pr = el.parentElement.getBoundingClientRect();
                return {
                    tag: el.parentElement.tagName,
                    x: Math.round(pr.x), y: Math.round(pr.y),
                    w: Math.round(pr.width), h: Math.round(pr.height),
                    cursor: window.getComputedStyle(el.parentElement).cursor,
                    border: window.getComputedStyle(el.parentElement).borderStyle,
                    classes: (el.parentElement.className || '').toString().substring(0, 60),
                };
            }
        }
        return null;
    }""")
    print(f"  Drop zone: {drop_zone}", flush=True)

    # Also find exact element with dashed border
    dashed = page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            var style = window.getComputedStyle(el);
            if (style.borderStyle.includes('dashed') && r.width > 200 && r.height > 30
                && r.x > 300 && r.y > 100 && r.y < 400) {
                return {
                    tag: el.tagName,
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    classes: (el.className || '').toString().substring(0, 60),
                    cursor: style.cursor,
                };
            }
        }
        return null;
    }""")
    print(f"  Dashed border element: {dashed}", flush=True)

    # Try clicking the dashed border area
    target = dashed or drop_zone
    if target and target['x'] > 0 and target['w'] > 100:
        cx = target['x'] + target['w'] // 2
        cy = target['y'] + target['h'] // 2
        print(f"\n  Clicking target at ({cx}, {cy}) [{target['tag']}]...", flush=True)

        try:
            with page.expect_file_chooser(timeout=5000) as fc_info:
                page.mouse.click(cx, cy)

            fc = fc_info.value
            print(f"\n  *** FILE CHOOSER TRIGGERED! ***", flush=True)
            print(f"  Multiple: {fc.is_multiple}", flush=True)

            if TEST_IMAGE.exists():
                fc.set_files(str(TEST_IMAGE))
                page.wait_for_timeout(5000)
                ss(page, "P41_03_uploaded")

                # Check if reference preview appeared
                state = page.evaluate("""() => {
                    // Check for reference image in CC panel
                    for (const img of document.querySelectorAll('img')) {
                        var r = img.getBoundingClientRect();
                        var src = img.src || '';
                        if (r.x > 60 && r.x < 300 && r.y > 400 && r.y < 700
                            && r.width > 30) {
                            return {
                                success: true,
                                src: src.substring(0, 100),
                                x: Math.round(r.x), y: Math.round(r.y),
                                w: Math.round(r.width), h: Math.round(r.height),
                            };
                        }
                    }
                    return {success: false};
                }""")
                print(f"\n  Upload result: {state}", flush=True)
                if state.get('success'):
                    print(f"  *** REFERENCE IMAGE UPLOADED! ***", flush=True)

        except Exception as e:
            print(f"  File chooser error: {e}", flush=True)

            # Last resort: try clicking at various positions within the dialog
            print("\n  Trying position-based clicks...", flush=True)
            positions = [(540, 224), (536, 210), (536, 230), (500, 220)]
            for px, py in positions:
                print(f"  Trying ({px}, {py})...", flush=True)
                try:
                    with page.expect_file_chooser(timeout=3000) as fc_info2:
                        page.mouse.click(px, py)
                    fc2 = fc_info2.value
                    print(f"  *** FC at ({px},{py})! ***", flush=True)
                    if TEST_IMAGE.exists():
                        fc2.set_files(str(TEST_IMAGE))
                        page.wait_for_timeout(5000)
                        ss(page, "P41_04_position_upload")
                        print("  Upload done!", flush=True)
                    break
                except Exception:
                    pass

    # ============================================================
    #  CANVAS THUMBNAIL TEST
    # ============================================================
    print("\n  Trying canvas thumbnail selection...", flush=True)

    # Check if dialog is still open
    dialog_open = page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            if (text.includes('Pick Image') && text.includes('Drop')) return true;
        }
        return false;
    }""")

    if dialog_open:
        # Click the canvas thumbnail
        thumb = page.evaluate("""() => {
            for (const img of document.querySelectorAll('img')) {
                var r = img.getBoundingClientRect();
                if (r.width > 30 && r.height > 30 && r.y > 280 && r.y < 450
                    && r.x > 300 && r.x < 500) {
                    return {
                        src: (img.src || '').substring(0, 80),
                        x: Math.round(r.x + r.width / 2),
                        y: Math.round(r.y + r.height / 2),
                    };
                }
            }
            return null;
        }""")
        print(f"  Canvas thumbnail: {thumb}", flush=True)

        if thumb:
            print(f"  Clicking thumbnail at ({thumb['x']}, {thumb['y']})...", flush=True)
            page.mouse.click(thumb['x'], thumb['y'])
            page.wait_for_timeout(3000)

            ss(page, "P41_05_thumb_selected")

            # Check if dialog closed and ref appeared
            after = page.evaluate("""() => {
                // Check dialog
                var dialogOpen = false;
                for (const el of document.querySelectorAll('*')) {
                    if ((el.innerText || '').includes('Pick Image')
                        && (el.innerText || '').includes('Drop')) {
                        dialogOpen = true; break;
                    }
                }
                // Check ref preview
                var ref = null;
                for (const img of document.querySelectorAll('img')) {
                    var r = img.getBoundingClientRect();
                    if (r.x > 60 && r.x < 250 && r.y > 400 && r.y < 650
                        && r.width > 30 && r.height > 20) {
                        ref = {
                            src: (img.src || '').substring(0, 80),
                            x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height),
                        };
                        break;
                    }
                }
                return {dialogOpen: dialogOpen, ref: ref};
            }""")
            print(f"  After thumbnail click:", flush=True)
            print(f"    Dialog open: {after['dialogOpen']}", flush=True)
            print(f"    Reference: {after['ref']}", flush=True)

    ss(page, "P41_06_final")
    print(f"\n\n===== PHASE 41 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
