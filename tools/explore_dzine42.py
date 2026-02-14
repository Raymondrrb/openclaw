"""Phase 42: Fix Reference click + file upload — use specific form ID and position clicks.

From P41 screenshot: CC panel visible, Camera/Pose/Reference at ~y=289.
CC form ID: character2img-generate-btn-form (from P39 error log).
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
    #  Open CC panel
    # ============================================================
    print("\n  Opening CC panel...", flush=True)
    page.mouse.click(40, 197)  # Txt2Img first
    page.wait_for_timeout(1000)
    page.mouse.click(40, 306)  # Character
    page.wait_for_timeout(3000)
    close_dialogs(page)

    # Click Generate Images if needed
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
    page.wait_for_timeout(2000)

    # Map ALL buttons to find Reference — dump them
    all_visible_btns = page.evaluate("""() => {
        var items = [];
        for (const btn of document.querySelectorAll('button')) {
            var r = btn.getBoundingClientRect();
            var text = (btn.innerText || '').trim();
            // Only visible buttons in the left panel
            if (r.width > 0 && r.height > 0 && r.x > 50 && r.x < 350 && r.y > 0) {
                items.push({
                    text: text.substring(0, 30) || '(empty)',
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    classes: (btn.className || '').toString().substring(0, 40),
                    id: btn.id || '',
                });
            }
        }
        return items.sort(function(a,b) { return a.y - b.y; });
    }""")
    print(f"\n  Visible buttons in left panel ({len(all_visible_btns)}):", flush=True)
    for btn in all_visible_btns:
        id_str = f" id='{btn['id']}'" if btn['id'] else ""
        print(f"    ({btn['x']},{btn['y']}) {btn['w']}x{btn['h']} c='{btn['classes'][:25]}'{id_str} '{btn['text']}'", flush=True)

    # ============================================================
    #  Click Reference — use the VISIBLE button directly
    # ============================================================
    print("\n  Clicking Reference button...", flush=True)

    ref_found = False
    for btn in all_visible_btns:
        if btn['text'] == 'Reference':
            cx = btn['x'] + btn['w'] // 2
            cy = btn['y'] + btn['h'] // 2
            print(f"  Found at ({btn['x']},{btn['y']}), clicking ({cx},{cy})...", flush=True)
            page.mouse.click(cx, cy)
            ref_found = True
            break

    if not ref_found:
        print("  Not found in visible buttons! Using #character2img form...", flush=True)
        ref_found = page.evaluate("""() => {
            var form = document.getElementById('character2img-generate-btn-form');
            if (!form) return false;
            for (const btn of form.querySelectorAll('button')) {
                if ((btn.innerText || '').trim() === 'Reference') {
                    btn.click();
                    return true;
                }
            }
            return false;
        }""")
        print(f"  Form-based click: {ref_found}", flush=True)

    page.wait_for_timeout(3000)
    ss(page, "P42_01_after_ref_click")

    # Verify Reference is active
    ref_state = page.evaluate("""() => {
        for (const btn of document.querySelectorAll('button')) {
            var text = (btn.innerText || '').trim();
            var r = btn.getBoundingClientRect();
            if (text === 'Reference' && r.width > 0 && r.x > 50 && r.x < 350) {
                return {
                    classes: (btn.className || '').toString(),
                    selected: (btn.className || '').toString().includes('selected')
                        || (btn.className || '').toString().includes('active'),
                    bg: window.getComputedStyle(btn).backgroundColor,
                };
            }
        }
        return null;
    }""")
    print(f"  Reference state: {ref_state}", flush=True)

    # Check if Pick Image appeared
    pick_btns = page.evaluate("""() => {
        var items = [];
        for (const btn of document.querySelectorAll('button')) {
            var text = (btn.innerText || '').trim();
            var r = btn.getBoundingClientRect();
            if (text.includes('Pick Image') && r.width > 0 && r.x > 50) {
                items.push({
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    visible: r.width > 0 && r.height > 0,
                    classes: (btn.className || '').toString().substring(0, 40),
                });
            }
        }
        return items;
    }""")
    print(f"  Pick Image buttons: {len(pick_btns)}", flush=True)
    for pb in pick_btns:
        print(f"    ({pb['x']},{pb['y']}) {pb['w']}x{pb['h']} visible={pb['visible']} c='{pb['classes']}'", flush=True)

    # ============================================================
    #  Click Pick Image
    # ============================================================
    vis_pick = [pb for pb in pick_btns if pb['visible'] and pb['x'] > 50]
    if vis_pick:
        pb = vis_pick[0]
        cx = pb['x'] + pb['w'] // 2
        cy = pb['y'] + pb['h'] // 2
        print(f"\n  Clicking Pick Image at ({cx}, {cy})...", flush=True)
        page.mouse.click(cx, cy)
        page.wait_for_timeout(2000)
        ss(page, "P42_02_pick_dialog")

        # Find the upload zone — look for dashed border or "Drop" text
        upload_info = page.evaluate("""() => {
            // Strategy 1: Find dashed border element
            for (const el of document.querySelectorAll('div, button, label')) {
                var style = window.getComputedStyle(el);
                var r = el.getBoundingClientRect();
                if (style.borderStyle.includes('dashed') && r.width > 200 && r.height > 30
                    && r.x > 200 && r.y > 100) {
                    return {
                        method: 'dashed_border',
                        tag: el.tagName,
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        cursor: style.cursor,
                        classes: (el.className || '').toString().substring(0, 60),
                    };
                }
            }
            // Strategy 2: Find by "Drop or select" text and get its immediate parent
            for (const el of document.querySelectorAll('*')) {
                var text = el.textContent || '';
                if (text.includes('Drop or select') && el.children.length < 5) {
                    var r = el.getBoundingClientRect();
                    if (r.width > 100 && r.height > 20) {
                        return {
                            method: 'text_parent',
                            tag: el.tagName,
                            x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height),
                            cursor: window.getComputedStyle(el).cursor,
                            classes: (el.className || '').toString().substring(0, 60),
                        };
                    }
                }
            }
            // Strategy 3: Look for upload-related classes
            for (const el of document.querySelectorAll('.pick-modal-upload, .upload-zone, .drop-zone, [class*="pick"][class*="upload"]')) {
                var r = el.getBoundingClientRect();
                if (r.width > 100 && r.x > 200) {
                    return {
                        method: 'class_match',
                        tag: el.tagName,
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        classes: (el.className || '').toString().substring(0, 60),
                    };
                }
            }
            return null;
        }""")
        print(f"  Upload zone: {upload_info}", flush=True)

        # Also try to find ANY file-chooser-triggering element in the dialog
        # by looking at all elements with cursor:pointer in the dialog area
        pointers = page.evaluate("""() => {
            var items = [];
            for (const el of document.querySelectorAll('*')) {
                var r = el.getBoundingClientRect();
                var style = window.getComputedStyle(el);
                if (style.cursor === 'pointer' && r.width > 100 && r.height > 20
                    && r.x > 300 && r.x < 800 && r.y > 150 && r.y < 300
                    && el.tagName !== 'HTML' && el.tagName !== 'BODY') {
                    items.push({
                        tag: el.tagName,
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        classes: (el.className || '').toString().substring(0, 60),
                        text: (el.innerText || '').trim().substring(0, 40),
                    });
                }
            }
            var seen = new Set();
            return items.filter(function(i) {
                var key = i.x + '|' + i.y + '|' + i.w;
                if (seen.has(key)) return false;
                seen.add(key);
                return true;
            }).sort(function(a,b) { return a.y - b.y; });
        }""")
        print(f"\n  Pointer elements in dialog area ({len(pointers)}):", flush=True)
        for p in pointers:
            print(f"    ({p['x']},{p['y']}) {p['w']}x{p['h']} <{p['tag']}> c='{p['classes'][:30]}' '{p['text'][:30]}'", flush=True)

        # Try clicking the upload zone or first pointer element
        target = upload_info
        if not target and pointers:
            # Use the first pointer element that looks like an upload zone
            for p in pointers:
                if p['w'] > 200 and p['h'] > 30:
                    target = p
                    break
            if not target:
                target = pointers[0]

        if target:
            cx2 = target['x'] + target['w'] // 2
            cy2 = target['y'] + target['h'] // 2
            print(f"\n  Clicking upload target at ({cx2}, {cy2})...", flush=True)

            try:
                with page.expect_file_chooser(timeout=5000) as fc_info:
                    page.mouse.click(cx2, cy2)
                fc = fc_info.value
                print(f"  *** FILE CHOOSER! *** Multiple={fc.is_multiple}", flush=True)
                if TEST_IMAGE.exists():
                    fc.set_files(str(TEST_IMAGE))
                    page.wait_for_timeout(5000)
                    ss(page, "P42_03_uploaded")
                    print("  *** FILE UPLOADED! ***", flush=True)
            except Exception as e:
                print(f"  No file chooser: {e}", flush=True)

                # Try the canvas thumbnail instead
                print("\n  Trying canvas thumbnail...", flush=True)
                thumb_clicked = page.evaluate("""() => {
                    for (const img of document.querySelectorAll('img')) {
                        var r = img.getBoundingClientRect();
                        if (r.width > 30 && r.height > 30 && r.y > 250 && r.y < 450
                            && r.x > 300 && r.x < 600) {
                            img.click();
                            return {
                                src: (img.src || '').substring(0, 60),
                                x: Math.round(r.x), y: Math.round(r.y),
                            };
                        }
                    }
                    return null;
                }""")
                print(f"  Thumbnail clicked: {thumb_clicked}", flush=True)
                page.wait_for_timeout(3000)
                ss(page, "P42_04_thumb_click")

                if thumb_clicked:
                    # Check if dialog closed and reference appeared
                    after = page.evaluate("""() => {
                        var ref = null;
                        for (const img of document.querySelectorAll('img')) {
                            var r = img.getBoundingClientRect();
                            if (r.x > 60 && r.x < 250 && r.y > 350 && r.y < 650
                                && r.width > 30) {
                                ref = {
                                    src: (img.src || '').substring(0, 80),
                                    x: Math.round(r.x), y: Math.round(r.y),
                                    w: Math.round(r.width), h: Math.round(r.height),
                                };
                                break;
                            }
                        }
                        return ref;
                    }""")
                    print(f"  Reference after thumb: {after}", flush=True)

    ss(page, "P42_05_final")
    print(f"\n\n===== PHASE 42 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
