"""Phase 45: Verify reference upload + test full CC generation with reference.

From P44: button.upload at (464,261) 524x80, center (726,301).
expect_file_chooser + mouse.click(726,301) = FILE CHOOSER TRIGGERED.
Dialog closes after upload. Need to verify reference image is set and
test generation with reference.
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
    #  STEP 1: Open CC panel + Reference mode
    # ============================================================
    print("\n  Step 1: Open CC panel + Reference mode", flush=True)

    page.mouse.click(40, 197)  # Txt2Img first
    page.wait_for_timeout(1000)
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

    # Click Reference
    page.evaluate("""() => {
        for (const btn of document.querySelectorAll('button')) {
            var text = (btn.innerText || '').trim();
            var r = btn.getBoundingClientRect();
            if (text === 'Reference' && r.width > 30 && r.x > 50 && r.x < 350 && r.y > 400) {
                btn.click(); return;
            }
        }
    }""")
    page.wait_for_timeout(2000)

    ss(page, "P45_01_reference_mode")

    # ============================================================
    #  STEP 2: Check current state of Pick Image area (BEFORE upload)
    # ============================================================
    print("\n  Step 2: Inspect Pick Image area BEFORE upload", flush=True)

    before_state = page.evaluate("""() => {
        // Find Pick Image button/container
        var pickArea = null;
        for (const btn of document.querySelectorAll('button, div')) {
            var classes = (btn.className || '').toString();
            var r = btn.getBoundingClientRect();
            if (classes.includes('pick-image') && r.width > 50 && r.x > 50 && r.x < 350) {
                pickArea = {
                    tag: btn.tagName,
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    classes: classes,
                    innerHTML: btn.innerHTML.substring(0, 500),
                };
                break;
            }
        }

        // Find ANY images near the pick-image area (60-350 x, 550-700 y)
        var nearbyImages = [];
        for (const img of document.querySelectorAll('img')) {
            var r = img.getBoundingClientRect();
            if (r.x > 50 && r.x < 360 && r.y > 520 && r.y < 750 && r.width > 5) {
                nearbyImages.push({
                    src: (img.src || '').substring(0, 100),
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                });
            }
        }

        return {pickArea: pickArea, nearbyImages: nearbyImages};
    }""")
    print(f"  Pick area: {before_state['pickArea']}", flush=True)
    if before_state['pickArea']:
        print(f"  innerHTML: {before_state['pickArea'].get('innerHTML', '')[:300]}", flush=True)
    print(f"  Nearby images: {len(before_state['nearbyImages'])}", flush=True)
    for img in before_state['nearbyImages']:
        print(f"    ({img['x']},{img['y']}) {img['w']}x{img['h']} src='{img['src'][:60]}'", flush=True)

    # ============================================================
    #  STEP 3: Click Pick Image → Upload file
    # ============================================================
    print("\n  Step 3: Click Pick Image → Upload file", flush=True)

    # Click Pick Image
    page.evaluate("""() => {
        for (const btn of document.querySelectorAll('button')) {
            var classes = (btn.className || '').toString();
            var r = btn.getBoundingClientRect();
            if (classes.includes('pick-image') && r.width > 50 && r.x > 50 && r.x < 350) {
                btn.click(); return;
            }
        }
    }""")
    page.wait_for_timeout(2000)

    # Verify dialog opened
    dialog = page.evaluate("""() => {
        var el = document.querySelector('.pick-panel');
        if (!el) return null;
        var r = el.getBoundingClientRect();
        return {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)};
    }""")
    print(f"  Dialog: {dialog}", flush=True)

    if not dialog:
        print("  Dialog not opened! Aborting.", flush=True)
        ss(page, "P45_99_no_dialog")
        sys.stdout.flush()
        os._exit(1)

    # Find upload button
    upload_btn = page.evaluate("""() => {
        var panel = document.querySelector('.pick-panel');
        if (!panel) return null;
        var btn = panel.querySelector('button.upload');
        if (!btn) return null;
        var r = btn.getBoundingClientRect();
        return {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)};
    }""")
    print(f"  Upload button: {upload_btn}", flush=True)

    if upload_btn:
        cx = upload_btn['x'] + upload_btn['w'] // 2
        cy = upload_btn['y'] + upload_btn['h'] // 2
        print(f"  Clicking upload button center ({cx}, {cy})...", flush=True)

        try:
            with page.expect_file_chooser(timeout=5000) as fc_info:
                page.mouse.click(cx, cy)
            fc = fc_info.value
            print(f"  FILE CHOOSER triggered!", flush=True)
            fc.set_files(str(TEST_IMAGE))
            print(f"  File set: {TEST_IMAGE.name}", flush=True)
            page.wait_for_timeout(5000)  # Wait for upload processing
        except Exception as e:
            print(f"  Error: {e}", flush=True)

    ss(page, "P45_02_after_upload")

    # ============================================================
    #  STEP 4: Check Pick Image area AFTER upload
    # ============================================================
    print("\n  Step 4: Inspect Pick Image area AFTER upload", flush=True)

    after_state = page.evaluate("""() => {
        // Check dialog state
        var panel = document.querySelector('.pick-panel');
        var dialogOpen = panel && panel.getBoundingClientRect().width > 100;

        // Find Pick Image button/container
        var pickArea = null;
        for (const btn of document.querySelectorAll('button, div')) {
            var classes = (btn.className || '').toString();
            var r = btn.getBoundingClientRect();
            if (classes.includes('pick-image') && r.width > 50 && r.x > 50 && r.x < 350) {
                pickArea = {
                    tag: btn.tagName,
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    classes: classes,
                    innerHTML: btn.innerHTML.substring(0, 500),
                };
                break;
            }
        }

        // Find ALL images in the CC panel area (wide search)
        var allPanelImages = [];
        for (const img of document.querySelectorAll('img')) {
            var r = img.getBoundingClientRect();
            if (r.x > 50 && r.x < 360 && r.y > 200 && r.y < 900 && r.width > 5) {
                allPanelImages.push({
                    src: (img.src || '').substring(0, 120),
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    alt: img.alt || '',
                });
            }
        }

        // Check for background-image on pick-image container
        var bgImages = [];
        for (const el of document.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            if (r.x > 50 && r.x < 360 && r.y > 550 && r.y < 750 && r.width > 20) {
                var bg = window.getComputedStyle(el).backgroundImage;
                if (bg && bg !== 'none') {
                    bgImages.push({
                        tag: el.tagName,
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        classes: (el.className || '').toString().substring(0, 40),
                        bg: bg.substring(0, 120),
                    });
                }
            }
        }

        return {
            dialogOpen: dialogOpen,
            pickArea: pickArea,
            allPanelImages: allPanelImages,
            bgImages: bgImages,
        };
    }""")
    print(f"  Dialog open: {after_state['dialogOpen']}", flush=True)
    print(f"  Pick area: {after_state['pickArea']}", flush=True)
    if after_state['pickArea']:
        print(f"  innerHTML AFTER: {after_state['pickArea'].get('innerHTML', '')[:300]}", flush=True)
    print(f"\n  Panel images ({len(after_state['allPanelImages'])}):", flush=True)
    for img in after_state['allPanelImages']:
        print(f"    ({img['x']},{img['y']}) {img['w']}x{img['h']} alt='{img['alt']}' src='{img['src'][:80]}'", flush=True)
    print(f"\n  BG images ({len(after_state['bgImages'])}):", flush=True)
    for bg in after_state['bgImages']:
        print(f"    ({bg['x']},{bg['y']}) {bg['w']}x{bg['h']} <{bg['tag']}> c='{bg['classes']}' bg='{bg['bg'][:80]}'", flush=True)

    # ============================================================
    #  STEP 5: Check reference strength slider
    # ============================================================
    print("\n  Step 5: Check for reference strength/weight controls", flush=True)

    controls = page.evaluate("""() => {
        var items = [];
        // Look for sliders, range inputs, or text near the reference area
        for (const el of document.querySelectorAll('input[type="range"], .slider, .v-slider, [class*="slider"], [class*="strength"], [class*="weight"]')) {
            var r = el.getBoundingClientRect();
            if (r.x > 50 && r.x < 360 && r.y > 500 && r.y < 800 && r.width > 20) {
                items.push({
                    tag: el.tagName,
                    type: el.type || '',
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    classes: (el.className || '').toString().substring(0, 40),
                    value: el.value || '',
                });
            }
        }
        // Also check for text labels
        for (const el of document.querySelectorAll('span, div, label')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (r.x > 50 && r.x < 360 && r.y > 580 && r.y < 780
                && r.width < 300 && r.height < 40
                && (text.includes('Strength') || text.includes('Weight') || text.includes('Influence')
                    || text.includes('Fidelity') || text.includes('%'))) {
                items.push({
                    tag: el.tagName,
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    text: text.substring(0, 30),
                    classes: (el.className || '').toString().substring(0, 40),
                });
            }
        }
        return items;
    }""")
    print(f"  Reference controls ({len(controls)}):", flush=True)
    for c in controls:
        text_or_val = c.get('text', c.get('value', ''))
        print(f"    ({c['x']},{c['y']}) {c['w']}x{c['h']} <{c['tag']}> c='{c['classes']}' '{text_or_val}'", flush=True)

    # ============================================================
    #  STEP 6: Full element dump of CC panel between y=550 and y=900
    # ============================================================
    print("\n  Step 6: CC panel element dump (y=550 to y=900)", flush=True)

    panel_elements = page.evaluate("""() => {
        var items = [];
        for (const el of document.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            if (r.x > 50 && r.x < 360 && r.y > 550 && r.y < 900
                && r.width > 10 && r.height > 5 && r.width < 350
                && el.tagName !== 'path' && el.tagName !== 'line'
                && el.tagName !== 'circle' && el.tagName !== 'g') {
                var text = (el.innerText || '').trim();
                var bg = window.getComputedStyle(el).backgroundImage;
                items.push({
                    tag: el.tagName,
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    text: text.substring(0, 30),
                    classes: (el.className || '').toString().substring(0, 35),
                    hasBg: bg !== 'none' ? 'yes' : '',
                    cursor: window.getComputedStyle(el).cursor,
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
    print(f"\n  Elements ({len(panel_elements)}):", flush=True)
    for el in panel_elements[:50]:
        extras = []
        if el['hasBg']: extras.append('BG')
        if el['cursor'] not in ('auto', 'default', ''): extras.append(f"cur={el['cursor']}")
        extra_str = ' ' + ' '.join(extras) if extras else ''
        print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> c='{el['classes'][:25]}'{extra_str} '{el['text'][:25]}'", flush=True)

    # ============================================================
    #  STEP 7: Try canvas thumbnail approach and check result
    # ============================================================
    print("\n  Step 7: Test canvas thumbnail as reference", flush=True)

    # Re-open Pick Image dialog
    page.evaluate("""() => {
        for (const btn of document.querySelectorAll('button')) {
            var classes = (btn.className || '').toString();
            var r = btn.getBoundingClientRect();
            if (classes.includes('pick-image') && r.width > 50 && r.x > 50 && r.x < 350) {
                btn.click(); return;
            }
        }
    }""")
    page.wait_for_timeout(2000)

    # Find and click canvas image-item
    thumb_result = page.evaluate("""() => {
        var panel = document.querySelector('.pick-panel');
        if (!panel) return {error: 'no panel'};
        var items = panel.querySelectorAll('button.image-item');
        if (items.length === 0) return {error: 'no image items'};
        var first = items[0];
        var r = first.getBoundingClientRect();
        return {
            x: Math.round(r.x), y: Math.round(r.y),
            w: Math.round(r.width), h: Math.round(r.height),
            style: (first.getAttribute('style') || '').substring(0, 100),
            count: items.length,
        };
    }""")
    print(f"  Canvas thumbnails: {thumb_result}", flush=True)

    if not thumb_result.get('error'):
        cx = thumb_result['x'] + thumb_result['w'] // 2
        cy = thumb_result['y'] + thumb_result['h'] // 2
        print(f"  Clicking canvas thumbnail at ({cx}, {cy})...", flush=True)
        page.mouse.click(cx, cy)
        page.wait_for_timeout(3000)

        ss(page, "P45_03_after_canvas_ref")

        # Check the CC panel for changes
        canvas_ref_state = page.evaluate("""() => {
            // Check pick-image area
            var pickArea = null;
            for (const btn of document.querySelectorAll('button, div')) {
                var classes = (btn.className || '').toString();
                var r = btn.getBoundingClientRect();
                if (classes.includes('pick-image') && r.width > 50 && r.x > 50 && r.x < 350) {
                    pickArea = {
                        innerHTML: btn.innerHTML.substring(0, 500),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                    };
                    break;
                }
            }

            // Check ALL images in panel
            var images = [];
            for (const img of document.querySelectorAll('img')) {
                var r = img.getBoundingClientRect();
                if (r.x > 50 && r.x < 360 && r.y > 200 && r.y < 900 && r.width > 5) {
                    images.push({
                        src: (img.src || '').substring(0, 120),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                    });
                }
            }

            // Check BG images in panel
            var bgImages = [];
            for (const el of document.querySelectorAll('*')) {
                var r = el.getBoundingClientRect();
                if (r.x > 50 && r.x < 360 && r.y > 550 && r.y < 800 && r.width > 20) {
                    var bg = window.getComputedStyle(el).backgroundImage;
                    if (bg && bg !== 'none') {
                        bgImages.push({
                            tag: el.tagName,
                            x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height),
                            classes: (el.className || '').toString().substring(0, 40),
                            bg: bg.substring(0, 120),
                        });
                    }
                }
            }

            return {pickArea: pickArea, images: images, bgImages: bgImages};
        }""")
        print(f"  Pick area innerHTML: {canvas_ref_state['pickArea']['innerHTML'][:300] if canvas_ref_state.get('pickArea') else 'N/A'}", flush=True)
        print(f"  Panel images ({len(canvas_ref_state['images'])}):", flush=True)
        for img in canvas_ref_state['images']:
            print(f"    ({img['x']},{img['y']}) {img['w']}x{img['h']} src='{img['src'][:80]}'", flush=True)
        print(f"  BG images ({len(canvas_ref_state['bgImages'])}):", flush=True)
        for bg in canvas_ref_state['bgImages']:
            print(f"    ({bg['x']},{bg['y']}) {bg['w']}x{bg['h']} <{bg['tag']}> c='{bg['classes']}' bg='{bg['bg'][:80]}'", flush=True)

    ss(page, "P45_04_final")
    print(f"\n\n===== PHASE 45 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
