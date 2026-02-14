"""Phase 35: Upload mechanism, model picker, CC style — refined approach.

Goals:
1. Click "Uploads" text in Assets panel to find upload area
2. Try triggering hidden upload-image buttons via JS .click()
3. Click model ">" chevron precisely using element scanning
4. Retry CC Style by finding and clicking all elements in style row
5. Test canvas paste (Ctrl+V) for image upload
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
    #  PART 1: ASSETS — CLICK "UPLOADS" TO FIND UPLOAD BUTTON
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 1: ASSETS UPLOAD MECHANISM", flush=True)
    print("=" * 60, flush=True)

    page.mouse.click(40, 136)  # Assets sidebar
    page.wait_for_timeout(2000)
    close_dialogs(page)

    # Click "Uploads" text to expand that section
    uploads_section = page.evaluate("""() => {
        for (const el of document.querySelectorAll('h5, h6, div, span')) {
            const text = (el.innerText || '').trim();
            const r = el.getBoundingClientRect();
            if (text === 'Uploads' && r.x > 60 && r.x < 300 && r.y > 100 && r.y < 300
                && r.width > 40 && r.height > 10) {
                el.click();
                return {x: Math.round(r.x), y: Math.round(r.y), tag: el.tagName};
            }
        }
        return null;
    }""")
    print(f"  Uploads section clicked: {uploads_section}", flush=True)
    page.wait_for_timeout(1500)

    ss(page, "P35_01_uploads_expanded")

    # Check if anything new appeared
    after_upload = page.evaluate("""() => {
        const items = [];
        for (const el of document.querySelectorAll('button, [role="button"]')) {
            const r = el.getBoundingClientRect();
            const text = (el.innerText || '').trim();
            if (r.x > 60 && r.x < 300 && r.y > 100 && r.y < 400
                && r.width > 10 && r.height > 10) {
                items.push({
                    tag: el.tagName,
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    text: text.substring(0, 40),
                    classes: (el.className || '').toString().substring(0, 60),
                });
            }
        }
        return items.sort((a, b) => a.y - b.y);
    }""")
    print(f"\n  Buttons after Uploads click ({len(after_upload)}):", flush=True)
    for el in after_upload:
        print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> classes='{el['classes'][:40]}' '{el['text']}'", flush=True)

    # Try the hidden upload-image button via JS — make it visible and click
    print("\n  Trying to activate hidden upload-image buttons...", flush=True)
    upload_btn_result = page.evaluate("""() => {
        // Find ALL upload-image buttons
        const btns = document.querySelectorAll('button.upload-image, button.upload-image-btn, .new-file.upload-image');
        const results = [];
        for (const btn of btns) {
            const r = btn.getBoundingClientRect();
            const parent = btn.parentElement;
            const parentR = parent ? parent.getBoundingClientRect() : null;
            results.push({
                classes: btn.className,
                x: Math.round(r.x), y: Math.round(r.y),
                w: Math.round(r.width), h: Math.round(r.height),
                display: window.getComputedStyle(btn).display,
                visibility: window.getComputedStyle(btn).visibility,
                parentTag: parent ? parent.tagName : '',
                parentClasses: parent ? parent.className.toString().substring(0, 60) : '',
                parentDisplay: parent ? window.getComputedStyle(parent).display : '',
            });
        }
        return results;
    }""")
    print(f"  Upload buttons found: {len(upload_btn_result)}", flush=True)
    for btn in upload_btn_result[:5]:
        print(f"    classes='{btn['classes']}' ({btn['x']},{btn['y']}) {btn['w']}x{btn['h']}", flush=True)
        print(f"      display={btn['display']} vis={btn['visibility']} parent={btn['parentTag']}.{btn['parentClasses'][:30]}", flush=True)

    # Try clicking the first upload-image button via JS
    print("\n  Clicking first upload-image button via JS...", flush=True)
    click_result = page.evaluate("""() => {
        const btn = document.querySelector('button.new-file.upload-image');
        if (btn) {
            btn.click();
            return 'clicked new-file.upload-image';
        }
        const btn2 = document.querySelector('button.upload-image-btn');
        if (btn2) {
            btn2.click();
            return 'clicked upload-image-btn';
        }
        return 'no button found';
    }""")
    print(f"  Click result: {click_result}", flush=True)
    page.wait_for_timeout(2000)

    # Check if file input appeared now
    file_inputs = page.evaluate("""() => {
        const inputs = [];
        for (const el of document.querySelectorAll('input[type="file"]')) {
            inputs.push({
                accept: el.accept || '',
                multiple: el.multiple,
                id: el.id || '',
                name: el.name || '',
            });
        }
        return inputs;
    }""")
    print(f"  File inputs after JS click: {len(file_inputs)}", flush=True)
    for fi in file_inputs:
        print(f"    accept='{fi['accept']}' multiple={fi['multiple']} id='{fi['id']}'", flush=True)

    ss(page, "P35_02_after_upload_click")

    # ============================================================
    #  PART 2: MODEL PICKER — PRECISE CLICK
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 2: TXT2IMG MODEL PICKER", flush=True)
    print("=" * 60, flush=True)

    page.mouse.click(40, 197)  # Txt2Img sidebar
    page.wait_for_timeout(2000)
    close_dialogs(page)

    # Get ALL elements in the model row area very precisely
    model_detail = page.evaluate("""() => {
        const items = [];
        for (const el of document.querySelectorAll('*')) {
            const r = el.getBoundingClientRect();
            // Tight row: model is at y 90-130, x 80-320
            if (r.y > 85 && r.y < 135 && r.x > 80 && r.x < 320
                && r.width > 3 && r.width < 300 && r.height > 3 && r.height < 60) {
                const cursor = window.getComputedStyle(el).cursor;
                items.push({
                    tag: el.tagName,
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    cursor: cursor,
                    text: (el.innerText || '').trim().substring(0, 30),
                    classes: (el.className || '').toString().substring(0, 50),
                });
            }
        }
        return items.sort((a, b) => a.x - b.x);
    }""")
    print(f"\n  Model row elements ({len(model_detail)}):", flush=True)
    for el in model_detail:
        click = " [CLICK]" if el['cursor'] == 'pointer' else ""
        print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> c='{el['classes'][:30]}' '{el['text']}'{click}", flush=True)

    # Find the chevron/arrow element specifically
    arrow = page.evaluate("""() => {
        for (const el of document.querySelectorAll('svg, span, i, button')) {
            const r = el.getBoundingClientRect();
            if (r.y > 95 && r.y < 125 && r.x > 230 && r.x < 290
                && r.width > 3 && r.width < 30 && r.height > 3 && r.height < 30) {
                return {
                    tag: el.tagName,
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    classes: (el.className || '').toString().substring(0, 50),
                };
            }
        }
        return null;
    }""")
    print(f"\n  Arrow/chevron element: {arrow}", flush=True)

    # Try clicking the model container div — look for clickable parent
    model_click = page.evaluate("""() => {
        // Find the model name container that should open the model picker
        for (const el of document.querySelectorAll('div, button, a')) {
            const text = (el.innerText || '').trim();
            const r = el.getBoundingClientRect();
            if (text.includes('Nano Banana Pro') && !text.includes('Output')
                && r.x > 80 && r.x < 200 && r.y > 85 && r.y < 135
                && r.width > 100 && r.width < 260 && r.height > 20 && r.height < 50) {
                const cursor = window.getComputedStyle(el).cursor;
                return {
                    tag: el.tagName,
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    cursor: cursor,
                    classes: (el.className || '').toString().substring(0, 80),
                };
            }
        }
        return null;
    }""")
    print(f"\n  Model container: {model_click}", flush=True)

    if model_click:
        # Click the center of the model container
        cx = model_click['x'] + model_click['w'] // 2
        cy = model_click['y'] + model_click['h'] // 2
        print(f"  Clicking model container at ({cx}, {cy})...", flush=True)
        page.mouse.click(cx, cy)
        page.wait_for_timeout(2000)
        ss(page, "P35_03_model_click")

        # Check if we navigated to a model picker page
        url = page.url
        print(f"  URL after click: {url}", flush=True)

        if 'canvas' not in url:
            # We navigated away — capture what we see
            page.wait_for_timeout(2000)
            ss(page, "P35_03b_model_page")
            print(f"  Navigated to: {url}", flush=True)

            # Map the page content
            content = page.evaluate("""() => {
                const items = [];
                for (const el of document.querySelectorAll('h1, h2, h3, h4, h5, h6, button')) {
                    const r = el.getBoundingClientRect();
                    const text = (el.innerText || '').trim();
                    if (text && text.length < 60 && r.width > 20 && r.height > 10
                        && r.y > 0 && r.y < 800) {
                        items.push({
                            tag: el.tagName,
                            text: text,
                            x: Math.round(r.x), y: Math.round(r.y),
                        });
                    }
                }
                const seen = new Set();
                return items.filter(i => {
                    const key = i.text;
                    if (seen.has(key)) return false;
                    seen.add(key);
                    return true;
                }).sort((a, b) => a.y - b.y).slice(0, 25);
            }""")
            print(f"\n  Page content ({len(content)}):", flush=True)
            for el in content:
                print(f"    ({el['x']},{el['y']}) <{el['tag']}> '{el['text']}'", flush=True)

            # Go back
            page.go_back()
            page.wait_for_timeout(3000)
            close_dialogs(page)
        else:
            # Check for overlay
            overlay = page.evaluate("""() => {
                for (const el of document.querySelectorAll('*')) {
                    const z = parseInt(window.getComputedStyle(el).zIndex) || 0;
                    const r = el.getBoundingClientRect();
                    if (z > 600 && r.width > 200 && r.height > 100) {
                        return {
                            z: z, text: (el.innerText || '').trim().substring(0, 300),
                            x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height),
                        };
                    }
                }
                return null;
            }""")
            if overlay:
                print(f"\n  Overlay: z={overlay['z']} ({overlay['x']},{overlay['y']}) {overlay['w']}x{overlay['h']}", flush=True)
                print(f"    '{overlay['text'][:150]}'", flush=True)
            page.keyboard.press("Escape")
            page.wait_for_timeout(500)

    # ============================================================
    #  PART 3: CC STYLE — FIND ALL CLICKABLE ELEMENTS
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 3: CC STYLE EXPLORATION", flush=True)
    print("=" * 60, flush=True)

    page.mouse.click(40, 306)  # Character sidebar
    page.wait_for_timeout(1500)
    close_dialogs(page)

    # Enter CC
    page.evaluate("""() => {
        for (const btn of document.querySelectorAll('button')) {
            const text = (btn.innerText || '').trim();
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

    # Scroll to Style area
    page.mouse.move(200, 600)
    for _ in range(3):
        page.mouse.wheel(0, 150)
        page.wait_for_timeout(300)
    page.wait_for_timeout(500)

    # Get the full style row by finding Style label first
    style_info = page.evaluate("""() => {
        // Find "Style" text
        var styleY = 0;
        for (const el of document.querySelectorAll('span, div')) {
            var t = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (t === 'Style' && r.x > 80 && r.x < 200 && r.width < 60) {
                styleY = r.y;
                break;
            }
        }
        if (!styleY) return {found: false};

        // Get ALL elements in the y range of Style row
        var elements = [];
        for (const el of document.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            if (r.y > styleY - 15 && r.y < styleY + 25 && r.x > 80 && r.x < 330
                && r.width > 3 && r.height > 3 && r.width < 250) {
                var cursor = window.getComputedStyle(el).cursor;
                var bg = window.getComputedStyle(el).backgroundColor;
                var borderRad = window.getComputedStyle(el).borderRadius;
                elements.push({
                    tag: el.tagName,
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    cursor: cursor,
                    bg: bg,
                    borderRadius: borderRad,
                    text: (el.innerText || '').trim().substring(0, 20),
                    classes: (el.className || '').toString().substring(0, 50),
                });
            }
        }
        return {found: true, styleY: Math.round(styleY), elements: elements.sort(function(a,b){return a.x - b.x})};
    }""")

    if style_info.get('found'):
        print(f"\n  Style row at y={style_info['styleY']} ({len(style_info['elements'])} elements):", flush=True)
        for el in style_info['elements']:
            click = " [CLICK]" if el['cursor'] == 'pointer' else ""
            br = f" br={el['borderRadius']}" if '50' in el.get('borderRadius', '') else ""
            bg_short = el['bg'][:20] if el['bg'] != 'rgba(0, 0, 0, 0)' else ""
            bg_str = f" bg={bg_short}" if bg_short else ""
            print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> c='{el['classes'][:25]}' '{el['text']}'{click}{br}{bg_str}", flush=True)

        # Try clicking each small element in style row
        clicked_positions = set()
        for el in style_info['elements']:
            # Skip large containers and text labels
            if el['w'] > 100 or el['text'] in ('Style', 'NEW'):
                continue
            cx = el['x'] + el['w'] // 2
            cy = el['y'] + el['h'] // 2
            pos_key = f"{cx // 10},{cy // 10}"
            if pos_key in clicked_positions:
                continue
            clicked_positions.add(pos_key)

            print(f"\n  Clicking ({cx}, {cy}) {el['w']}x{el['h']} <{el['tag']}> '{el['text']}'...", flush=True)
            page.mouse.click(cx, cy)
            page.wait_for_timeout(1500)

            # Check for any new overlay/modal
            new_overlay = page.evaluate("""() => {
                for (const el of document.querySelectorAll('*')) {
                    var z = parseInt(window.getComputedStyle(el).zIndex) || 0;
                    var r = el.getBoundingClientRect();
                    if (z > 700 && r.width > 100 && r.height > 50) {
                        return {
                            z: z,
                            text: (el.innerText || '').trim().substring(0, 200),
                            x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height),
                        };
                    }
                }
                return null;
            }""")
            if new_overlay:
                print(f"    OVERLAY! z={new_overlay['z']} ({new_overlay['x']},{new_overlay['y']}) {new_overlay['w']}x{new_overlay['h']}", flush=True)
                print(f"    text: '{new_overlay['text'][:120]}'", flush=True)
                ss(page, "P35_04_style_picker")
                page.keyboard.press("Escape")
                page.wait_for_timeout(500)
                break

            # Check URL change
            if 'canvas' not in page.url:
                print(f"    Navigated to: {page.url}", flush=True)
                ss(page, "P35_04_style_page")
                page.go_back()
                page.wait_for_timeout(2000)
                break
    else:
        print("  Style label not found", flush=True)

    # ============================================================
    #  PART 4: CC GENERATION MODE DETAIL
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 4: CC GENERATION MODE", flush=True)
    print("=" * 60, flush=True)

    # From Phase 33: Generation Mode at y=758, buttons at y=790: Fast, Normal, HQ
    gen_mode = page.evaluate("""() => {
        var items = [];
        for (const btn of document.querySelectorAll('button')) {
            var text = (btn.innerText || '').trim();
            var r = btn.getBoundingClientRect();
            if ((text === 'Fast' || text === 'Normal' || text === 'HQ')
                && r.x > 80 && r.x < 350 && r.width > 30) {
                var bgColor = window.getComputedStyle(btn).backgroundColor;
                var color = window.getComputedStyle(btn).color;
                items.push({
                    text: text,
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    bgColor: bgColor,
                    color: color,
                    active: bgColor.includes('255') || bgColor.includes('220'),
                });
            }
        }
        return items;
    }""")
    print(f"\n  Generation Mode buttons ({len(gen_mode)}):", flush=True)
    for btn in gen_mode:
        active = " [ACTIVE]" if btn['active'] else ""
        print(f"    ({btn['x']},{btn['y']}) {btn['w']}x{btn['h']} '{btn['text']}' bg={btn['bgColor'][:20]} c={btn['color'][:20]}{active}", flush=True)

    # Click "Normal" to see what happens
    for btn in gen_mode:
        if btn['text'] == 'Normal':
            print(f"\n  Clicking 'Normal' at ({btn['x'] + btn['w']//2}, {btn['y'] + btn['h']//2})...", flush=True)
            page.mouse.click(btn['x'] + btn['w']//2, btn['y'] + btn['h']//2)
            page.wait_for_timeout(1000)

            # Re-check colors
            after = page.evaluate("""() => {
                var items = [];
                for (const btn of document.querySelectorAll('button')) {
                    var text = (btn.innerText || '').trim();
                    var r = btn.getBoundingClientRect();
                    if ((text === 'Fast' || text === 'Normal' || text === 'HQ')
                        && r.x > 80 && r.width > 30) {
                        items.push({
                            text: text,
                            bgColor: window.getComputedStyle(btn).backgroundColor,
                        });
                    }
                }
                return items;
            }""")
            print(f"  After clicking Normal:", flush=True)
            for b in after:
                print(f"    '{b['text']}' bg={b['bgColor'][:30]}", flush=True)
            break

    # ============================================================
    #  PART 5: CC CONTROL MODE — EXPLORE POSE & REFERENCE
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 5: CC CONTROL MODE — POSE & REFERENCE", flush=True)
    print("=" * 60, flush=True)

    # Click "Pose" control mode
    pose_btn = page.evaluate("""() => {
        for (const btn of document.querySelectorAll('button')) {
            var text = (btn.innerText || '').trim();
            var r = btn.getBoundingClientRect();
            if (text === 'Pose' && r.x > 100 && r.x < 250 && r.width > 40) {
                btn.click();
                return {x: Math.round(r.x), y: Math.round(r.y)};
            }
        }
        return null;
    }""")
    print(f"  Pose clicked: {pose_btn}", flush=True)
    page.wait_for_timeout(2000)

    ss(page, "P35_05_pose_mode")

    # Map what appeared under Pose
    pose_panel = page.evaluate("""() => {
        var items = [];
        for (const el of document.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            var text = (el.innerText || '').trim();
            // Look below the control mode buttons
            if (r.x > 80 && r.x < 350 && r.y > 460 && r.y < 700
                && r.width > 15 && r.width < 300 && text
                && text.length > 0 && text.length < 60
                && !text.includes('\\n')
                && r.height > 8 && r.height < 60) {
                items.push({
                    text: text,
                    tag: el.tagName,
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                });
            }
        }
        var seen = new Set();
        return items.filter(function(i) {
            var key = i.text + '|' + Math.round(i.y / 3);
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
        }).sort(function(a,b) { return a.y - b.y; });
    }""")
    print(f"\n  Pose mode panel ({len(pose_panel)}):", flush=True)
    for el in pose_panel:
        print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> '{el['text']}'", flush=True)

    # Check for file input (Pose might need a reference image)
    pose_file = page.evaluate("""() => {
        var inputs = [];
        for (const el of document.querySelectorAll('input[type="file"]')) {
            inputs.push({accept: el.accept || '', id: el.id || ''});
        }
        return inputs;
    }""")
    print(f"  File inputs in Pose mode: {len(pose_file)}", flush=True)

    # Now try Reference mode
    ref_btn = page.evaluate("""() => {
        for (const btn of document.querySelectorAll('button')) {
            var text = (btn.innerText || '').trim();
            var r = btn.getBoundingClientRect();
            if (text === 'Reference' && r.x > 200 && r.x < 320 && r.width > 40) {
                btn.click();
                return {x: Math.round(r.x), y: Math.round(r.y)};
            }
        }
        return null;
    }""")
    print(f"\n  Reference clicked: {ref_btn}", flush=True)
    page.wait_for_timeout(2000)

    ss(page, "P35_06_reference_mode")

    # Map Reference panel
    ref_panel = page.evaluate("""() => {
        var items = [];
        for (const el of document.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            var text = (el.innerText || '').trim();
            if (r.x > 80 && r.x < 350 && r.y > 460 && r.y < 700
                && r.width > 15 && r.width < 300 && text
                && text.length > 0 && text.length < 60
                && !text.includes('\\n')
                && r.height > 8 && r.height < 60) {
                items.push({
                    text: text,
                    tag: el.tagName,
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    classes: (el.className || '').toString().substring(0, 50),
                });
            }
        }
        var seen = new Set();
        return items.filter(function(i) {
            var key = i.text + '|' + Math.round(i.y / 3);
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
        }).sort(function(a,b) { return a.y - b.y; });
    }""")
    print(f"\n  Reference mode panel ({len(ref_panel)}):", flush=True)
    for el in ref_panel:
        print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> c='{el.get('classes','')[:25]}' '{el['text']}'", flush=True)

    # Check for file inputs or upload areas in Reference mode
    ref_upload = page.evaluate("""() => {
        var items = [];
        // Check for file inputs
        for (const el of document.querySelectorAll('input[type="file"]')) {
            items.push({type: 'file_input', accept: el.accept || ''});
        }
        // Check for upload-like buttons that became visible
        for (const el of document.querySelectorAll('button.upload-image, [class*="upload"]')) {
            var r = el.getBoundingClientRect();
            if (r.width > 0 && r.height > 0 && r.x > 60 && r.y > 400) {
                items.push({
                    type: 'upload_btn',
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    classes: (el.className || '').toString().substring(0, 60),
                    text: (el.innerText || '').trim().substring(0, 30),
                });
            }
        }
        return items;
    }""")
    print(f"\n  Upload elements in Reference mode: {len(ref_upload)}", flush=True)
    for el in ref_upload:
        print(f"    {el}", flush=True)

    # Switch back to Camera
    page.evaluate("""() => {
        for (const btn of document.querySelectorAll('button')) {
            if ((btn.innerText || '').trim() === 'Camera') { btn.click(); return; }
        }
    }""")
    page.wait_for_timeout(500)

    ss(page, "P35_07_final")
    print(f"\n\n===== PHASE 35 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
