"""Phase 40: Fix panel opening + file upload.

Issue: Character sidebar is active but panel is collapsed.
Solution: Click a DIFFERENT sidebar icon first, then click Character to open its panel.
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


def find_sidebar_icons(page):
    """Find all sidebar icons with their positions using text labels."""
    return page.evaluate("""() => {
        var items = [];
        for (const el of document.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            var text = (el.innerText || '').trim();
            // Sidebar icons are at x=0-64, each ~50px tall
            if (r.x >= 0 && r.x < 65 && r.width > 30 && r.width < 80
                && r.height > 30 && r.height < 80 && r.y > 40 && r.y < 800
                && text && text.length > 2 && text.length < 25) {
                items.push({
                    text: text.replace('\\n', ' ').trim(),
                    x: Math.round(r.x + r.width / 2),
                    y: Math.round(r.y + r.height / 2),
                    top: Math.round(r.y),
                });
            }
        }
        var seen = new Set();
        return items.filter(function(i) {
            var key = Math.round(i.top / 20);
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
        }).sort(function(a,b) { return a.top - b.top; });
    }""")


def open_panel(page, tool_name):
    """Open a sidebar panel by name, handling collapsed state."""
    icons = find_sidebar_icons(page)
    target = None
    for icon in icons:
        if tool_name.lower() in icon['text'].lower():
            target = icon
            break

    if not target:
        print(f"  Sidebar icon '{tool_name}' not found!", flush=True)
        return False

    # Click a different tool first to reset state, then click target
    other = None
    for icon in icons:
        if icon['text'] != target['text'] and 'Txt2Img' in icon['text']:
            other = icon
            break
    if not other:
        other = icons[0] if icons[0] != target else icons[1]

    print(f"  Clicking '{other['text']}' first at ({other['x']}, {other['y']})...", flush=True)
    page.mouse.click(other['x'], other['y'])
    page.wait_for_timeout(1000)

    print(f"  Clicking '{target['text']}' at ({target['x']}, {target['y']})...", flush=True)
    page.mouse.click(target['x'], target['y'])
    page.wait_for_timeout(2000)

    # Verify panel opened
    panel_open = page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            if (r.x > 60 && r.x < 120 && r.y > 50 && r.y < 80
                && r.width > 100 && r.height > 15) {
                return (el.innerText || '').trim().substring(0, 40);
            }
        }
        return null;
    }""")
    print(f"  Panel header: {panel_open}", flush=True)
    return panel_open is not None


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
    #  STEP 1: Map sidebar icons
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  STEP 1: MAP SIDEBAR", flush=True)
    print("=" * 60, flush=True)

    icons = find_sidebar_icons(page)
    print(f"\n  Sidebar icons ({len(icons)}):", flush=True)
    for icon in icons:
        print(f"    ({icon['x']},{icon['y']}) top={icon['top']} '{icon['text']}'", flush=True)

    # ============================================================
    #  STEP 2: Open CC panel
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  STEP 2: OPEN CHARACTER PANEL", flush=True)
    print("=" * 60, flush=True)

    opened = open_panel(page, "Character")
    close_dialogs(page)

    if not opened:
        # Try by clicking the "Character" sidebar text directly
        print("  Panel didn't open. Trying direct sidebar click...", flush=True)
        for icon in icons:
            if 'Character' in icon['text']:
                # Double click to toggle open
                page.mouse.click(icon['x'], icon['y'])
                page.wait_for_timeout(500)
                page.mouse.click(icon['x'], icon['y'])
                page.wait_for_timeout(2000)
                break

    ss(page, "P40_01_cc_panel")

    # Check if "Generate Images" button is needed
    gen_btn = page.evaluate("""() => {
        for (const btn of document.querySelectorAll('button')) {
            var text = (btn.innerText || '').trim();
            var r = btn.getBoundingClientRect();
            if (text.includes('Generate Images') && r.x > 60 && r.width > 100) {
                return {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width)};
            }
        }
        return null;
    }""")
    if gen_btn:
        print(f"  Clicking 'Generate Images' at ({gen_btn['x']},{gen_btn['y']})...", flush=True)
        page.mouse.click(gen_btn['x'] + gen_btn['w'] // 2, gen_btn['y'] + 15)
        page.wait_for_timeout(2000)

    # Check if Ray is selected
    ray = page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text === 'Ray' && r.x > 60 && r.x < 200) {
                return {tag: el.tagName, x: Math.round(r.x), y: Math.round(r.y)};
            }
        }
        return null;
    }""")
    if ray:
        print(f"  Ray found at ({ray['x']},{ray['y']})", flush=True)
    else:
        # Need to select Ray
        print("  Ray not visible. Clicking Ray button...", flush=True)
        page.evaluate("""() => {
            for (const el of document.querySelectorAll('button, div')) {
                if ((el.innerText || '').trim() === 'Ray') {
                    el.click(); return;
                }
            }
        }""")
        page.wait_for_timeout(1500)

    # ============================================================
    #  STEP 3: Click Reference mode
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  STEP 3: SWITCH TO REFERENCE MODE", flush=True)
    print("=" * 60, flush=True)

    # Find the specific Reference button in the CC panel using ID-based selector
    ref_result = page.evaluate("""() => {
        // Find by looking at buttons within the CC form that say "Reference"
        var form = document.querySelector('#character2img-generate-btn-form');
        if (!form) form = document.querySelector('.gen-config-form');
        if (!form) form = document;

        for (const btn of form.querySelectorAll('button')) {
            var text = (btn.innerText || '').trim();
            var r = btn.getBoundingClientRect();
            if (text === 'Reference' && r.width > 40 && r.height > 15
                && r.x > 60 && r.x < 350 && r.y > 200) {
                btn.click();
                return {
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    clicked: true,
                };
            }
        }
        return {clicked: false};
    }""")
    print(f"  Reference click: {ref_result}", flush=True)
    page.wait_for_timeout(2000)

    ss(page, "P40_02_reference_mode")

    # ============================================================
    #  STEP 4: Find and click Pick Image
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  STEP 4: CLICK PICK IMAGE", flush=True)
    print("=" * 60, flush=True)

    # Find Pick Image button that is VISIBLE
    pick = page.evaluate("""() => {
        for (const btn of document.querySelectorAll('button')) {
            var classes = (btn.className || '').toString();
            var text = (btn.innerText || '').trim();
            var r = btn.getBoundingClientRect();
            if ((classes.includes('pick-image') || text.includes('Pick Image'))
                && r.width > 50 && r.height > 20 && r.x > 60) {
                return {
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    text: text,
                    visible: r.width > 0,
                };
            }
        }
        return null;
    }""")
    print(f"  Pick Image button: {pick}", flush=True)

    if pick and pick['visible']:
        cx = pick['x'] + pick['w'] // 2
        cy = pick['y'] + pick['h'] // 2
        print(f"  Clicking at ({cx}, {cy})...", flush=True)
        page.mouse.click(cx, cy)
        page.wait_for_timeout(2000)

        ss(page, "P40_03_pick_dialog")

        # ============================================================
        #  STEP 5: Upload via file chooser
        # ============================================================
        print("\n" + "=" * 60, flush=True)
        print("  STEP 5: FILE UPLOAD", flush=True)
        print("=" * 60, flush=True)

        # Find the "Drop or select" area
        drop = page.evaluate("""() => {
            for (const el of document.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                var r = el.getBoundingClientRect();
                if (text.includes('Drop or select') && r.width > 100) {
                    // Walk up to find the clickable container
                    var target = el;
                    for (var i = 0; i < 5 && target.parentElement; i++) {
                        if (target.tagName === 'BUTTON' || target.tagName === 'LABEL'
                            || window.getComputedStyle(target).cursor === 'pointer') break;
                        target = target.parentElement;
                    }
                    var tr = target.getBoundingClientRect();
                    return {
                        x: Math.round(tr.x), y: Math.round(tr.y),
                        w: Math.round(tr.width), h: Math.round(tr.height),
                        tag: target.tagName,
                    };
                }
            }
            return null;
        }""")
        print(f"  Drop area: {drop}", flush=True)

        if drop:
            cx2 = drop['x'] + drop['w'] // 2
            cy2 = drop['y'] + drop['h'] // 2
            print(f"  Clicking drop area at ({cx2}, {cy2}) [{drop['tag']}]...", flush=True)

            try:
                with page.expect_file_chooser(timeout=5000) as fc_info:
                    page.mouse.click(cx2, cy2)

                fc = fc_info.value
                print(f"\n  *** FILE CHOOSER TRIGGERED! ***", flush=True)
                print(f"  Multiple: {fc.is_multiple}", flush=True)

                if TEST_IMAGE.exists():
                    print(f"  Setting file: {TEST_IMAGE} ({TEST_IMAGE.stat().st_size} bytes)", flush=True)
                    fc.set_files(str(TEST_IMAGE))
                    page.wait_for_timeout(5000)
                    ss(page, "P40_04_uploaded")

                    # Check result
                    state = page.evaluate("""() => {
                        var dialogOpen = false;
                        for (const el of document.querySelectorAll('*')) {
                            var text = (el.innerText || '').trim();
                            if (text.includes('Pick Image') && text.includes('Drop')) {
                                var r = el.getBoundingClientRect();
                                if (r.width > 200) { dialogOpen = true; break; }
                            }
                        }
                        // Check for reference image in CC panel
                        var refPrev = null;
                        for (const img of document.querySelectorAll('img')) {
                            var r = img.getBoundingClientRect();
                            if (r.x > 60 && r.x < 350 && r.y > 350 && r.y < 700
                                && r.width > 30) {
                                refPrev = {
                                    src: (img.src || '').substring(0, 100),
                                    x: Math.round(r.x), y: Math.round(r.y),
                                    w: Math.round(r.width), h: Math.round(r.height),
                                };
                                break;
                            }
                        }
                        return {dialogOpen: dialogOpen, refPreview: refPrev};
                    }""")
                    print(f"\n  Upload result:", flush=True)
                    print(f"    Dialog still open: {state['dialogOpen']}", flush=True)
                    print(f"    Reference preview: {state['refPreview']}", flush=True)

                    # If dialog closed and ref preview appeared, the upload worked!
                    if state['refPreview']:
                        print(f"\n  *** IMAGE UPLOAD SUCCESSFUL! ***", flush=True)
                        print(f"    Ref image: {state['refPreview']['src'][:80]}", flush=True)

            except Exception as e:
                print(f"  File chooser error: {e}", flush=True)
                # Fallback: try to find and use any file input that may have appeared
                fi_count = page.locator('input[type="file"]').count()
                print(f"  File inputs found: {fi_count}", flush=True)
                if fi_count > 0:
                    try:
                        page.locator('input[type="file"]').first.set_input_files(str(TEST_IMAGE))
                        page.wait_for_timeout(3000)
                        ss(page, "P40_04b_fallback_upload")
                    except Exception as e2:
                        print(f"  Fallback failed: {e2}", flush=True)
        else:
            # Check for canvas thumbnails in the dialog
            print("  No drop area found. Checking for canvas thumbnails...", flush=True)
            thumbs = page.evaluate("""() => {
                var items = [];
                for (const img of document.querySelectorAll('img')) {
                    var r = img.getBoundingClientRect();
                    if (r.width > 30 && r.height > 30 && r.y > 200 && r.y < 500
                        && r.x > 200 && r.x < 800) {
                        items.push({
                            src: (img.src || '').substring(0, 60),
                            x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height),
                        });
                    }
                }
                return items;
            }""")
            print(f"  Thumbnails: {len(thumbs)}", flush=True)
            for t in thumbs:
                print(f"    ({t['x']},{t['y']}) {t['w']}x{t['h']} {t['src']}", flush=True)

    else:
        print("  Pick Image not visible. Dumping all visible buttons...", flush=True)
        btns = page.evaluate("""() => {
            var items = [];
            for (const btn of document.querySelectorAll('button')) {
                var r = btn.getBoundingClientRect();
                var text = (btn.innerText || '').trim();
                if (r.x > 60 && r.x < 350 && r.y > 200 && r.y < 900
                    && r.width > 20 && r.height > 10 && text.length < 40) {
                    items.push({
                        text: text || '(empty)',
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                    });
                }
            }
            return items.sort(function(a,b) { return a.y - b.y; });
        }""")
        for btn in btns[:20]:
            print(f"    ({btn['x']},{btn['y']}) {btn['w']}x{btn['h']} '{btn['text']}'", flush=True)

    ss(page, "P40_05_final")
    print(f"\n\n===== PHASE 40 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
