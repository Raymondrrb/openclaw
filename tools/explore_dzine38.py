"""Phase 38: Reliable Reference mode + file upload via file chooser.

The key issue in Phase 37: Reference mode wasn't activated before trying Pick Image.
This phase adds verification at each step.

Goals:
1. Enter CC Reference mode with verification
2. Find visible Pick Image button
3. Use page.expect_file_chooser() to intercept and upload
4. Also test canvas Upload sidebar drop zone
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


def verify_mode(page, expected):
    """Verify which control mode is active."""
    result = page.evaluate("""(expected) => {
        for (const btn of document.querySelectorAll('button')) {
            var text = (btn.innerText || '').trim();
            if (text === expected) {
                var bg = window.getComputedStyle(btn).backgroundColor;
                var parent = btn.parentElement;
                var selected = btn.classList.contains('selected') || btn.classList.contains('active')
                    || bg.includes('255') || bg.includes('220') || bg.includes('68, 68, 68') === false;
                return {text: text, bg: bg, selected: selected};
            }
        }
        return null;
    }""", expected)
    return result


def main():
    print("Connecting...", flush=True)
    pw = sync_playwright().start()
    browser = pw.chromium.connect_over_cdp("http://127.0.0.1:18800", timeout=15000)
    ctx = browser.contexts[0]
    page = ctx.new_page()
    page.set_viewport_size({"width": 1440, "height": 900})

    page.goto(CANVAS_URL, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(4000)
    close_dialogs(page)

    # ============================================================
    #  STEP 1: OPEN CC PANEL
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  STEP 1: OPEN CC PANEL", flush=True)
    print("=" * 60, flush=True)

    page.mouse.click(40, 306)  # Character sidebar
    page.wait_for_timeout(2000)
    close_dialogs(page)

    # Verify CC panel is open
    cc_open = page.evaluate("""() => {
        for (const el of document.querySelectorAll('h5, div')) {
            var text = (el.innerText || '').trim();
            if (text === 'Consistent Character') {
                var r = el.getBoundingClientRect();
                if (r.x > 60 && r.x < 200 && r.width > 100) return true;
            }
        }
        return false;
    }""")
    print(f"  CC panel open: {cc_open}", flush=True)

    if not cc_open:
        # Try "Generate Images" button
        print("  Clicking Generate Images button...", flush=True)
        page.evaluate("""() => {
            for (const btn of document.querySelectorAll('button')) {
                var text = (btn.innerText || '').trim();
                if (text.includes('Generate Images')) {
                    btn.click(); return true;
                }
            }
            return false;
        }""")
        page.wait_for_timeout(2000)

    # ============================================================
    #  STEP 2: SELECT RAY CHARACTER
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  STEP 2: SELECT RAY CHARACTER", flush=True)
    print("=" * 60, flush=True)

    ray_found = page.evaluate("""() => {
        // Check if Ray is already selected
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text === 'Ray' && r.x > 80 && r.x < 200 && r.width < 60 && r.y > 90 && r.y < 200) {
                return {selected: true, x: Math.round(r.x), y: Math.round(r.y)};
            }
        }
        // Try to select Ray
        for (const el of document.querySelectorAll('button, div')) {
            var text = (el.innerText || '').trim();
            if (text === 'Ray') {
                el.click();
                return {selected: false, clicked: true};
            }
        }
        return {selected: false, clicked: false};
    }""")
    print(f"  Ray: {ray_found}", flush=True)
    page.wait_for_timeout(1500)

    # ============================================================
    #  STEP 3: SWITCH TO REFERENCE MODE
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  STEP 3: SWITCH TO REFERENCE MODE", flush=True)
    print("=" * 60, flush=True)

    # First verify Camera/Pose/Reference buttons exist
    control_modes = page.evaluate("""() => {
        var modes = [];
        for (const btn of document.querySelectorAll('button')) {
            var text = (btn.innerText || '').trim();
            var r = btn.getBoundingClientRect();
            if ((text === 'Camera' || text === 'Pose' || text === 'Reference')
                && r.x > 80 && r.x < 350 && r.y > 250 && r.y < 500) {
                var classes = (btn.className || '').toString();
                modes.push({
                    text: text,
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    classes: classes.substring(0, 40),
                    selected: classes.includes('selected') || classes.includes('active'),
                });
            }
        }
        return modes;
    }""")
    print(f"  Control modes found: {len(control_modes)}", flush=True)
    for m in control_modes:
        sel = " [SELECTED]" if m['selected'] else ""
        print(f"    ({m['x']},{m['y']}) {m['w']}x{m['h']} '{m['text']}' c='{m['classes'][:25]}'{sel}", flush=True)

    # Click Reference button directly via Playwright locator for reliability
    ref_btn = None
    for m in control_modes:
        if m['text'] == 'Reference':
            ref_btn = m
            break

    if ref_btn:
        cx = ref_btn['x'] + ref_btn['w'] // 2
        cy = ref_btn['y'] + ref_btn['h'] // 2
        print(f"\n  Clicking Reference at ({cx}, {cy})...", flush=True)
        page.mouse.click(cx, cy)
        page.wait_for_timeout(2000)

        # Verify Reference mode is now active
        after_click = page.evaluate("""() => {
            for (const btn of document.querySelectorAll('button')) {
                var text = (btn.innerText || '').trim();
                if (text === 'Reference') {
                    var classes = (btn.className || '').toString();
                    return {
                        classes: classes,
                        selected: classes.includes('selected') || classes.includes('active'),
                    };
                }
            }
            return null;
        }""")
        print(f"  Reference after click: {after_click}", flush=True)

        ss(page, "P38_01_reference_mode")

        # ============================================================
        #  STEP 4: FIND PICK IMAGE BUTTON
        # ============================================================
        print("\n" + "=" * 60, flush=True)
        print("  STEP 4: FIND PICK IMAGE BUTTON", flush=True)
        print("=" * 60, flush=True)

        pick_btn = page.evaluate("""() => {
            for (const el of document.querySelectorAll('button, div')) {
                var text = (el.innerText || '').trim();
                var classes = (el.className || '').toString();
                var r = el.getBoundingClientRect();
                if ((text.includes('Pick Image') || classes.includes('pick-image'))
                    && r.x > 60 && r.width > 50 && r.height > 20) {
                    return {
                        tag: el.tagName,
                        text: text.substring(0, 30),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        classes: classes.substring(0, 50),
                        visible: r.width > 0 && r.height > 0,
                    };
                }
            }
            return null;
        }""")
        print(f"  Pick Image button: {pick_btn}", flush=True)

        if pick_btn and pick_btn['visible']:
            cx = pick_btn['x'] + pick_btn['w'] // 2
            cy = pick_btn['y'] + pick_btn['h'] // 2

            # ============================================================
            #  STEP 5: CLICK PICK IMAGE + FILE CHOOSER
            # ============================================================
            print("\n" + "=" * 60, flush=True)
            print("  STEP 5: PICK IMAGE FILE CHOOSER", flush=True)
            print("=" * 60, flush=True)

            print(f"  Clicking Pick Image at ({cx}, {cy})...", flush=True)
            page.mouse.click(cx, cy)
            page.wait_for_timeout(2000)

            ss(page, "P38_02_pick_dialog")

            # Map the dialog
            dialog_content = page.evaluate("""() => {
                var items = [];
                for (const el of document.querySelectorAll('*')) {
                    var z = parseInt(window.getComputedStyle(el).zIndex) || 0;
                    var r = el.getBoundingClientRect();
                    var text = (el.innerText || '').trim();
                    if (z > 900 && r.width > 20 && r.height > 10 && text
                        && text.length < 80 && !text.includes('\\n')) {
                        items.push({
                            z: z, tag: el.tagName,
                            x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height),
                            text: text,
                            classes: (el.className || '').toString().substring(0, 50),
                            cursor: window.getComputedStyle(el).cursor,
                        });
                    }
                }
                var seen = new Set();
                return items.filter(function(i) {
                    var key = i.text + '|' + Math.round(i.y / 5);
                    if (seen.has(key)) return false;
                    seen.add(key);
                    return true;
                }).sort(function(a,b) { return a.y - b.y; });
            }""")
            print(f"\n  Dialog content ({len(dialog_content)}):", flush=True)
            for el in dialog_content[:20]:
                click = " [CLICK]" if el['cursor'] == 'pointer' else ""
                print(f"    z={el['z']} ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> c='{el['classes'][:25]}'{click} '{el['text'][:40]}'", flush=True)

            # Find the "Drop or select images here" clickable area
            drop_select = page.evaluate("""() => {
                for (const el of document.querySelectorAll('*')) {
                    var z = parseInt(window.getComputedStyle(el).zIndex) || 0;
                    var text = (el.innerText || '').trim();
                    var r = el.getBoundingClientRect();
                    if (z > 900 && text.includes('Drop or select') && r.width > 100) {
                        // Find the clickable parent/container
                        var target = el;
                        while (target && target.parentElement) {
                            var cursor = window.getComputedStyle(target).cursor;
                            if (cursor === 'pointer' || target.tagName === 'BUTTON') break;
                            target = target.parentElement;
                        }
                        return {
                            tag: target.tagName,
                            x: Math.round(target.getBoundingClientRect().x),
                            y: Math.round(target.getBoundingClientRect().y),
                            w: Math.round(target.getBoundingClientRect().width),
                            h: Math.round(target.getBoundingClientRect().height),
                            classes: (target.className || '').toString().substring(0, 80),
                            cursor: window.getComputedStyle(target).cursor,
                        };
                    }
                }
                return null;
            }""")
            print(f"\n  Drop/select area: {drop_select}", flush=True)

            if drop_select:
                cx2 = drop_select['x'] + drop_select['w'] // 2
                cy2 = drop_select['y'] + drop_select['h'] // 2

                print(f"  Clicking drop area at ({cx2}, {cy2})...", flush=True)
                print(f"  Listening for file chooser...", flush=True)

                try:
                    with page.expect_file_chooser(timeout=5000) as fc_info:
                        page.mouse.click(cx2, cy2)

                    fc = fc_info.value
                    print(f"\n  *** FILE CHOOSER TRIGGERED! ***", flush=True)
                    print(f"  Multiple: {fc.is_multiple}", flush=True)
                    print(f"  Page: {fc.page.url[:60]}", flush=True)

                    if TEST_IMAGE.exists():
                        print(f"  Uploading: {TEST_IMAGE} ({TEST_IMAGE.stat().st_size} bytes)", flush=True)
                        fc.set_files(str(TEST_IMAGE))
                        page.wait_for_timeout(5000)

                        ss(page, "P38_03_after_upload")

                        # Check result
                        result = page.evaluate("""() => {
                            // Look for the uploaded image preview
                            var items = [];
                            for (const el of document.querySelectorAll('img')) {
                                var src = el.src || '';
                                var r = el.getBoundingClientRect();
                                if (r.width > 30 && r.height > 30 && r.x > 60 && r.y > 200
                                    && (src.includes('blob:') || src.includes('data:')
                                        || src.includes('dzine.ai'))) {
                                    items.push({
                                        src: src.substring(0, 100),
                                        x: Math.round(r.x), y: Math.round(r.y),
                                        w: Math.round(r.width), h: Math.round(r.height),
                                    });
                                }
                            }
                            // Also check if dialog closed and reference preview appeared
                            var dialogOpen = false;
                            for (const el of document.querySelectorAll('*')) {
                                var z = parseInt(window.getComputedStyle(el).zIndex) || 0;
                                if (z > 900 && (el.innerText || '').includes('Pick Image')) {
                                    dialogOpen = true;
                                    break;
                                }
                            }
                            return {images: items, dialogOpen: dialogOpen};
                        }""")
                        print(f"\n  Upload result:", flush=True)
                        print(f"    Dialog still open: {result['dialogOpen']}", flush=True)
                        print(f"    Images found: {len(result['images'])}", flush=True)
                        for img in result['images'][:5]:
                            print(f"      ({img['x']},{img['y']}) {img['w']}x{img['h']} {img['src'][:60]}", flush=True)

                    else:
                        print(f"  No test image at {TEST_IMAGE}", flush=True)
                        fc.set_files([])

                except Exception as e:
                    print(f"\n  File chooser not triggered: {e}", flush=True)
                    print("  Checking for dynamic file input...", flush=True)

                    # Check if a file input was created
                    file_inputs = page.evaluate("""() => {
                        var inputs = [];
                        for (const el of document.querySelectorAll('input[type="file"]')) {
                            inputs.push({
                                accept: el.accept || '',
                                id: el.id || '',
                                visible: el.getBoundingClientRect().width > 0,
                            });
                        }
                        return inputs;
                    }""")
                    print(f"  File inputs: {len(file_inputs)}", flush=True)
                    for fi in file_inputs:
                        print(f"    accept='{fi['accept']}' visible={fi['visible']}", flush=True)

                    if file_inputs:
                        print("  Using set_input_files on found input...", flush=True)
                        try:
                            page.locator('input[type="file"]').first.set_input_files(str(TEST_IMAGE))
                            page.wait_for_timeout(3000)
                            ss(page, "P38_03b_set_input_files")
                        except Exception as e2:
                            print(f"  set_input_files failed: {e2}", flush=True)

            # Also try clicking a canvas thumbnail if visible
            canvas_thumbs = page.evaluate("""() => {
                var items = [];
                for (const img of document.querySelectorAll('img')) {
                    var z = parseInt(window.getComputedStyle(img.parentElement || img).zIndex) || 0;
                    var r = img.getBoundingClientRect();
                    if (z > 900 && r.width > 30 && r.height > 30 && r.y > 250) {
                        items.push({
                            src: (img.src || '').substring(0, 80),
                            x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height),
                        });
                    }
                }
                return items;
            }""")
            print(f"\n  Canvas thumbnails in dialog: {len(canvas_thumbs)}", flush=True)
            for img in canvas_thumbs:
                print(f"    ({img['x']},{img['y']}) {img['w']}x{img['h']} {img['src'][:60]}", flush=True)
    else:
        print("  Reference button not found! Checking panel state...", flush=True)
        ss(page, "P38_01_no_reference")

        # Map full panel
        panel = page.evaluate("""() => {
            var items = [];
            for (const el of document.querySelectorAll('*')) {
                var r = el.getBoundingClientRect();
                var text = (el.innerText || '').trim();
                if (r.x > 60 && r.x < 350 && r.y > 50 && r.y < 500
                    && r.width > 20 && r.height > 10 && r.height < 50
                    && text && text.length < 60 && !text.includes('\\n')) {
                    items.push({text: text, y: Math.round(r.y)});
                }
            }
            var seen = new Set();
            return items.filter(function(i) {
                if (seen.has(i.text)) return false;
                seen.add(i.text);
                return true;
            }).sort(function(a,b) { return a.y - b.y; }).slice(0, 20);
        }""")
        for el in panel:
            print(f"    y={el['y']} '{el['text']}'", flush=True)

    # ============================================================
    #  STEP 6: CANVAS UPLOAD DROP ZONE
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  STEP 6: CANVAS UPLOAD DROP ZONE", flush=True)
    print("=" * 60, flush=True)

    # Close any dialogs
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)

    # Click Upload sidebar icon precisely
    page.mouse.click(37, 75)
    page.wait_for_timeout(2000)
    close_dialogs(page)

    ss(page, "P38_04_upload_sidebar")

    # Look for the upload button/zone on canvas
    upload_zone = page.evaluate("""() => {
        var items = [];
        for (const el of document.querySelectorAll('button, div, label')) {
            var classes = (el.className || '').toString();
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if ((classes.includes('upload') || text.includes('Upload') || text.includes('upload')
                 || text.includes('Drop') || text.includes('drag'))
                && r.width > 100 && r.height > 30 && r.x > 100) {
                items.push({
                    tag: el.tagName,
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    text: text.substring(0, 40),
                    classes: classes.substring(0, 60),
                });
            }
        }
        return items;
    }""")
    print(f"\n  Upload zones ({len(upload_zone)}):", flush=True)
    for z in upload_zone:
        print(f"    ({z['x']},{z['y']}) {z['w']}x{z['h']} <{z['tag']}> c='{z['classes'][:40]}' '{z['text']}'", flush=True)

    if upload_zone:
        # Try clicking the first one and listening for file chooser
        uz = upload_zone[0]
        cx = uz['x'] + uz['w'] // 2
        cy = uz['y'] + uz['h'] // 2

        print(f"\n  Clicking upload zone at ({cx}, {cy})...", flush=True)
        try:
            with page.expect_file_chooser(timeout=5000) as fc_info:
                page.mouse.click(cx, cy)

            fc = fc_info.value
            print(f"  *** CANVAS FILE CHOOSER TRIGGERED! ***", flush=True)
            print(f"  Multiple: {fc.is_multiple}", flush=True)

            if TEST_IMAGE.exists():
                print(f"  Uploading: {TEST_IMAGE}", flush=True)
                fc.set_files(str(TEST_IMAGE))
                page.wait_for_timeout(5000)
                ss(page, "P38_05_canvas_uploaded")

                # Check for new layer
                layers = page.evaluate("""() => {
                    var items = [];
                    for (const el of document.querySelectorAll('*')) {
                        var text = (el.innerText || '').trim();
                        if (text.includes('Layer') && !text.includes('\\n')) {
                            var r = el.getBoundingClientRect();
                            if (r.x > 1000 && r.width > 40) {
                                items.push({text: text, y: Math.round(r.y)});
                            }
                        }
                    }
                    var seen = new Set();
                    return items.filter(function(i) {
                        if (seen.has(i.text)) return false;
                        seen.add(i.text);
                        return true;
                    });
                }""")
                print(f"\n  Layers after upload: {len(layers)}", flush=True)
                for l in layers:
                    print(f"    y={l['y']} '{l['text']}'", flush=True)
            else:
                fc.set_files([])
        except Exception as e:
            print(f"  No file chooser: {e}", flush=True)

    ss(page, "P38_06_final")
    print(f"\n\n===== PHASE 38 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
