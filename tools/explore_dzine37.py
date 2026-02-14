"""Phase 37: File upload mechanism + Pick Image interaction.

Goals:
1. Open Pick Image dialog
2. Click "Drop or select images here" — check for dynamic file input
3. Try dispatching file drop event via JS
4. Try using page.set_input_files() on dynamically created input
5. Click canvas thumbnail to test selecting existing image as reference
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
    page.wait_for_timeout(3000)
    close_dialogs(page)

    # ============================================================
    #  PART 1: OPEN PICK IMAGE DIALOG
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 1: PICK IMAGE DIALOG EXPLORATION", flush=True)
    print("=" * 60, flush=True)

    # Open CC → Reference mode → Pick Image
    page.mouse.click(40, 306)  # Character sidebar
    page.wait_for_timeout(1500)
    close_dialogs(page)

    # Enter CC generation
    page.evaluate("""() => {
        for (const btn of document.querySelectorAll('button')) {
            var text = (btn.innerText || '').trim();
            if (text.includes('Generate Images') && text.includes('With your character')) {
                btn.click(); return true;
            }
        }
        return false;
    }""")
    page.wait_for_timeout(2000)

    # Select Ray
    page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            if ((el.innerText || '').trim() === 'Ray' && el.tagName === 'BUTTON') {
                el.click(); return true;
            }
        }
        return false;
    }""")
    page.wait_for_timeout(1500)

    # Click Reference mode
    page.evaluate("""() => {
        for (const btn of document.querySelectorAll('button')) {
            if ((btn.innerText || '').trim() === 'Reference') {
                btn.click(); return true;
            }
        }
        return false;
    }""")
    page.wait_for_timeout(1500)

    # Click Pick Image button
    page.evaluate("""() => {
        for (const el of document.querySelectorAll('button, div')) {
            var text = (el.innerText || '').trim();
            var classes = (el.className || '').toString();
            if (classes.includes('pick-image') || text === 'Pick Image') {
                el.click();
                return true;
            }
        }
        return false;
    }""")
    page.wait_for_timeout(2000)

    ss(page, "P37_01_pick_image_open")

    # Map the entire dialog precisely
    dialog = page.evaluate("""() => {
        var items = [];
        for (const el of document.querySelectorAll('*')) {
            var z = parseInt(window.getComputedStyle(el).zIndex) || 0;
            var r = el.getBoundingClientRect();
            if (z > 900 && r.width > 0 && r.height > 0 && r.x > 0) {
                var text = (el.innerText || '').trim();
                items.push({
                    tag: el.tagName,
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    z: z,
                    text: text.substring(0, 60),
                    classes: (el.className || '').toString().substring(0, 60),
                    cursor: window.getComputedStyle(el).cursor,
                });
            }
        }
        var seen = new Set();
        return items.filter(function(i) {
            var key = i.tag + '|' + i.x + '|' + i.y + '|' + i.w;
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
        }).sort(function(a,b) { return a.y - b.y; });
    }""")
    print(f"\n  Pick Image dialog elements ({len(dialog)}):", flush=True)
    for el in dialog[:30]:
        click = " [CLICK]" if el['cursor'] == 'pointer' else ""
        print(f"    z={el['z']} ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> c='{el['classes'][:30]}'{click} '{el['text'][:40]}'", flush=True)

    # Find the "Drop or select images here" area
    drop_area = page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var z = parseInt(window.getComputedStyle(el).zIndex) || 0;
            var r = el.getBoundingClientRect();
            if (z > 900 && text.includes('Drop or select') && r.width > 200) {
                return {
                    tag: el.tagName,
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    classes: (el.className || '').toString().substring(0, 80),
                };
            }
        }
        return null;
    }""")
    print(f"\n  Drop area: {drop_area}", flush=True)

    if drop_area:
        # Setup: Listen for file input creation events
        page.evaluate("""() => {
            window.__fileInputCreated = false;
            window.__originalCreateElement = document.createElement.bind(document);
            var origCreate = document.createElement;
            document.createElement = function(tag) {
                var el = origCreate.call(document, tag);
                if (tag.toLowerCase() === 'input') {
                    // Watch for type="file" being set
                    var origSetAttr = el.setAttribute.bind(el);
                    el.setAttribute = function(name, val) {
                        if (name === 'type' && val === 'file') {
                            window.__fileInputCreated = true;
                            window.__lastFileInput = el;
                        }
                        return origSetAttr(name, val);
                    };
                    // Also watch the type property
                    var desc = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'type');
                    if (desc && desc.set) {
                        Object.defineProperty(el, 'type', {
                            set: function(v) {
                                if (v === 'file') {
                                    window.__fileInputCreated = true;
                                    window.__lastFileInput = el;
                                }
                                return desc.set.call(el, v);
                            },
                            get: desc.get ? function() { return desc.get.call(el); } : undefined,
                        });
                    }
                }
                return el;
            };
        }""")

        # Click the drop area
        cx = drop_area['x'] + drop_area['w'] // 2
        cy = drop_area['y'] + drop_area['h'] // 2
        print(f"\n  Clicking drop area at ({cx}, {cy})...", flush=True)

        # Listen for filechooser event (Playwright intercepts OS file dialogs)
        file_chooser_promise = page.expect_file_chooser(timeout=5000)
        try:
            page.mouse.click(cx, cy)
            fc = file_chooser_promise.value
            print(f"  FILE CHOOSER triggered! Multiple={fc.is_multiple}", flush=True)
            print(f"  Setting file: {TEST_IMAGE}", flush=True)
            fc.set_files(str(TEST_IMAGE))
            page.wait_for_timeout(3000)

            ss(page, "P37_02_after_file_upload")

            # Check if the image was uploaded
            print("\n  Checking upload result...", flush=True)
            upload_state = page.evaluate("""() => {
                // Check for uploaded image preview
                var items = [];
                for (const el of document.querySelectorAll('img')) {
                    var src = el.src || '';
                    var r = el.getBoundingClientRect();
                    if (r.x > 50 && r.y > 100 && r.width > 30 && r.height > 30
                        && (src.includes('blob:') || src.includes('data:') || src.includes('dzine.ai'))) {
                        items.push({
                            src: src.substring(0, 80),
                            x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height),
                        });
                    }
                }
                return items;
            }""")
            print(f"  Upload result images: {len(upload_state)}", flush=True)
            for img in upload_state[:5]:
                print(f"    ({img['x']},{img['y']}) {img['w']}x{img['h']} src={img['src']}", flush=True)

        except Exception as e:
            print(f"  No file chooser: {e}", flush=True)

            # Check if file input was created dynamically
            created = page.evaluate("() => window.__fileInputCreated")
            print(f"  Dynamic file input created: {created}", flush=True)

            if created:
                # Try to set files on the dynamically created input
                print("  Setting files on dynamic input...", flush=True)
                page.evaluate("""(path) => {
                    if (window.__lastFileInput) {
                        // Can't set files via JS, but we found the input
                        return {
                            found: true,
                            type: window.__lastFileInput.type,
                            accept: window.__lastFileInput.accept,
                        };
                    }
                    return {found: false};
                }""", str(TEST_IMAGE))

            # Check all inputs again
            all_inputs = page.evaluate("""() => {
                var inputs = [];
                for (const el of document.querySelectorAll('input')) {
                    inputs.push({
                        type: el.type, accept: el.accept || '',
                        visible: el.getBoundingClientRect().width > 0,
                    });
                }
                return inputs;
            }""")
            file_type = [i for i in all_inputs if i['type'] == 'file']
            print(f"  File inputs after click: {len(file_type)}", flush=True)
            for fi in file_type:
                print(f"    type={fi['type']} accept={fi['accept']} visible={fi['visible']}", flush=True)

            # If file input exists, try set_input_files via Playwright locator
            if file_type:
                print("  Trying Playwright set_input_files...", flush=True)
                try:
                    page.locator('input[type="file"]').set_input_files(str(TEST_IMAGE))
                    page.wait_for_timeout(3000)
                    ss(page, "P37_02b_after_set_files")
                    print("  set_input_files succeeded!", flush=True)
                except Exception as e2:
                    print(f"  set_input_files failed: {e2}", flush=True)

    # ============================================================
    #  PART 2: CANVAS THUMBNAIL SELECTION
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 2: SELECT CANVAS IMAGE AS REFERENCE", flush=True)
    print("=" * 60, flush=True)

    # Reopen Pick Image if closed
    dialog_open = page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            var z = parseInt(window.getComputedStyle(el).zIndex) || 0;
            var text = (el.innerText || '').trim();
            if (z > 900 && text.includes('Pick Image')) return true;
        }
        return false;
    }""")

    if not dialog_open:
        print("  Reopening Pick Image dialog...", flush=True)
        page.evaluate("""() => {
            for (const el of document.querySelectorAll('button, div')) {
                var classes = (el.className || '').toString();
                if (classes.includes('pick-image')) {
                    el.click(); return true;
                }
            }
            return false;
        }""")
        page.wait_for_timeout(2000)

    # Find canvas thumbnails in the dialog
    canvas_imgs = page.evaluate("""() => {
        var items = [];
        for (const el of document.querySelectorAll('*')) {
            var z = parseInt(window.getComputedStyle(el).zIndex) || 0;
            var r = el.getBoundingClientRect();
            if (z > 900 && r.width > 30 && r.height > 30 && r.y > 200) {
                // Check for img tags or background images
                if (el.tagName === 'IMG') {
                    items.push({
                        type: 'img',
                        src: (el.src || '').substring(0, 80),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        cursor: window.getComputedStyle(el).cursor,
                    });
                }
                var bgImg = window.getComputedStyle(el).backgroundImage;
                if (bgImg && bgImg !== 'none' && bgImg.includes('url')) {
                    items.push({
                        type: 'bg',
                        src: bgImg.substring(0, 80),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        cursor: window.getComputedStyle(el).cursor,
                    });
                }
            }
        }
        return items;
    }""")
    print(f"\n  Canvas images in dialog ({len(canvas_imgs)}):", flush=True)
    for img in canvas_imgs:
        click = " [CLICK]" if img['cursor'] == 'pointer' else ""
        print(f"    ({img['x']},{img['y']}) {img['w']}x{img['h']} {img['type']} {img['src'][:60]}{click}", flush=True)

    # Click the first canvas thumbnail to select it
    if canvas_imgs:
        first = canvas_imgs[0]
        cx = first['x'] + first['w'] // 2
        cy = first['y'] + first['h'] // 2
        print(f"\n  Clicking canvas thumbnail at ({cx}, {cy})...", flush=True)
        page.mouse.click(cx, cy)
        page.wait_for_timeout(2000)

        ss(page, "P37_03_canvas_selected")

        # Check what happened — did the dialog close? Did Pick Image update?
        dialog_still_open = page.evaluate("""() => {
            for (const el of document.querySelectorAll('*')) {
                var z = parseInt(window.getComputedStyle(el).zIndex) || 0;
                var text = (el.innerText || '').trim();
                if (z > 900 && text.includes('Pick Image') && text.includes('Drop')) return true;
            }
            return false;
        }""")
        print(f"  Dialog still open: {dialog_still_open}", flush=True)

        # Check if a reference image preview appeared in the CC panel
        ref_preview = page.evaluate("""() => {
            for (const el of document.querySelectorAll('img')) {
                var r = el.getBoundingClientRect();
                var src = el.src || '';
                // Look for a reference image preview in the left panel area
                if (r.x > 60 && r.x < 300 && r.y > 400 && r.y < 600
                    && r.width > 40 && r.height > 30) {
                    return {
                        src: src.substring(0, 80),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                    };
                }
            }
            return null;
        }""")
        print(f"  Reference preview: {ref_preview}", flush=True)

    # ============================================================
    #  PART 3: UPLOAD TO CANVAS VIA DROP ZONE
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 3: CANVAS UPLOAD VIA DROP ZONE", flush=True)
    print("=" * 60, flush=True)

    # Close any dialog
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)

    # Click Upload sidebar to get the canvas drop zone
    page.mouse.click(40, 81)
    page.wait_for_timeout(2000)

    # Find the upload button on canvas
    upload_btn = page.evaluate("""() => {
        for (const el of document.querySelectorAll('button, div')) {
            var classes = (el.className || '').toString();
            var r = el.getBoundingClientRect();
            if (classes === 'upload' && r.width > 200 && r.height > 40 && r.x > 300) {
                return {
                    tag: el.tagName,
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    text: (el.innerText || '').trim().substring(0, 40),
                };
            }
        }
        return null;
    }""")
    print(f"\n  Canvas upload button: {upload_btn}", flush=True)

    if upload_btn:
        cx = upload_btn['x'] + upload_btn['w'] // 2
        cy = upload_btn['y'] + upload_btn['h'] // 2

        # Try clicking — watch for file chooser
        print(f"  Clicking canvas upload at ({cx}, {cy})...", flush=True)
        try:
            with page.expect_file_chooser(timeout=5000) as fc_info:
                page.mouse.click(cx, cy)
            fc = fc_info.value
            print(f"  FILE CHOOSER from canvas upload! Multiple={fc.is_multiple}", flush=True)
            print(f"  Setting file: {TEST_IMAGE}", flush=True)
            fc.set_files(str(TEST_IMAGE))
            page.wait_for_timeout(5000)

            ss(page, "P37_04_canvas_upload_result")

            # Check if image appeared on canvas
            new_layers = page.evaluate("""() => {
                var items = [];
                for (const el of document.querySelectorAll('button, div')) {
                    var text = (el.innerText || '').trim();
                    var r = el.getBoundingClientRect();
                    if (text.includes('Layer') && r.x > 1000 && r.width > 50) {
                        items.push({text: text.substring(0, 30), x: Math.round(r.x), y: Math.round(r.y)});
                    }
                }
                return items;
            }""")
            print(f"\n  Layers after upload: {len(new_layers)}", flush=True)
            for l in new_layers:
                print(f"    ({l['x']},{l['y']}) '{l['text']}'", flush=True)

        except Exception as e:
            print(f"  No file chooser from canvas upload: {e}", flush=True)

    # ============================================================
    #  PART 4: EXPLORE THE "+" MODEL BUTTON
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 4: CREATE STYLE BUTTON", flush=True)
    print("=" * 60, flush=True)

    # Open Txt2Img and click the "+" button
    page.mouse.click(40, 197)
    page.wait_for_timeout(2000)
    close_dialogs(page)

    # Click the "+" create-style button at (292, 97)
    page.evaluate("""() => {
        var btn = document.querySelector('button.create-style');
        if (btn) { btn.click(); return true; }
        return false;
    }""")
    page.wait_for_timeout(2000)

    ss(page, "P37_05_create_style")

    # Check for overlay
    create_overlay = page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            var z = parseInt(window.getComputedStyle(el).zIndex) || 0;
            var r = el.getBoundingClientRect();
            if (z > 900 && r.width > 200 && r.height > 100) {
                return {
                    z: z,
                    text: (el.innerText || '').trim().substring(0, 400),
                    w: Math.round(r.width), h: Math.round(r.height),
                };
            }
        }
        return null;
    }""")
    if create_overlay:
        print(f"\n  Create style overlay: z={create_overlay['z']}", flush=True)
        print(f"  Content: '{create_overlay['text'][:200]}'", flush=True)
    else:
        # Check if we navigated
        print(f"  URL: {page.url}", flush=True)

    page.keyboard.press("Escape")
    page.wait_for_timeout(500)

    ss(page, "P37_06_final")
    print(f"\n\n===== PHASE 37 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
