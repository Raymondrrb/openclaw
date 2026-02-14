"""Phase 36: Model picker catalog + Pick Image + CC style model selector.

Goals:
1. Open model picker and list ALL models by scrolling through categories
2. Click "Pick Image" in CC Reference mode to find the upload mechanism
3. Click "Dzine 3D Render v2" style text to see style model options
4. Explore "Create a style" (Quick Style vs Pro Style)
5. Check generation queue status
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
    page.wait_for_timeout(3000)
    close_dialogs(page)

    # ============================================================
    #  PART 1: MODEL PICKER — FULL CATALOG
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 1: MODEL PICKER CATALOG", flush=True)
    print("=" * 60, flush=True)

    # Open Txt2Img
    page.mouse.click(40, 197)
    page.wait_for_timeout(2000)
    close_dialogs(page)

    # Click model container to open picker
    page.evaluate("""() => {
        var btn = document.querySelector('button.style');
        if (btn) { btn.click(); return true; }
        return false;
    }""")
    page.wait_for_timeout(2000)

    ss(page, "P36_01_model_picker_open")

    # List all model cards in the picker
    models = page.evaluate("""() => {
        var items = [];
        // Find the model grid area — each model card has an image + name
        for (const el of document.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            var text = (el.innerText || '').trim();
            var z = parseInt(window.getComputedStyle(el).zIndex) || 0;
            // Model names are typically below thumbnails in the picker overlay
            if (z >= 999 || (r.x > 400 && r.y > 300 && r.y < 800)) {
                // Look for the model name labels
                if (text && text.length > 3 && text.length < 40
                    && !text.includes('\\n') && r.height > 10 && r.height < 25
                    && r.width > 50 && r.width < 200 && r.y > 250) {
                    items.push({
                        text: text,
                        x: Math.round(r.x), y: Math.round(r.y),
                    });
                }
            }
        }
        var seen = new Set();
        return items.filter(function(i) {
            if (seen.has(i.text)) return false;
            seen.add(i.text);
            return true;
        }).sort(function(a,b) { return a.y === b.y ? a.x - b.x : a.y - b.y; });
    }""")
    print(f"\n  Visible models ({len(models)}):", flush=True)
    for m in models:
        print(f"    ({m['x']},{m['y']}) '{m['text']}'", flush=True)

    # Scroll down in the model picker to see more models
    # The picker content area is the large overlay
    print("\n  Scrolling model picker...", flush=True)
    page.mouse.move(700, 600)
    for _ in range(8):
        page.mouse.wheel(0, 300)
        page.wait_for_timeout(300)
    page.wait_for_timeout(1000)

    ss(page, "P36_02_model_picker_scrolled")

    # List models after scroll
    models_after = page.evaluate("""() => {
        var items = [];
        for (const el of document.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            var text = (el.innerText || '').trim();
            if (text && text.length > 3 && text.length < 40
                && !text.includes('\\n') && r.height > 10 && r.height < 25
                && r.width > 50 && r.width < 200 && r.y > 100 && r.y < 800
                && r.x > 400) {
                items.push({
                    text: text,
                    x: Math.round(r.x), y: Math.round(r.y),
                });
            }
        }
        var seen = new Set();
        return items.filter(function(i) {
            if (seen.has(i.text)) return false;
            seen.add(i.text);
            return true;
        }).sort(function(a,b) { return a.y === b.y ? a.x - b.x : a.y - b.y; });
    }""")
    print(f"\n  Models after scroll ({len(models_after)}):", flush=True)
    for m in models_after:
        print(f"    ({m['x']},{m['y']}) '{m['text']}'", flush=True)

    # Try clicking each category to see all models
    categories = page.evaluate("""() => {
        var items = [];
        for (const el of document.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            var text = (el.innerText || '').trim();
            if (r.x > 210 && r.x < 400 && r.y > 100 && r.y < 800
                && r.width > 40 && r.width < 150 && r.height > 15 && r.height < 35
                && text && text.length > 2 && text.length < 25
                && !text.includes('\\n')
                && !text.includes('Search')) {
                items.push({text: text, x: Math.round(r.x), y: Math.round(r.y)});
            }
        }
        var seen = new Set();
        return items.filter(function(i) {
            if (seen.has(i.text)) return false;
            seen.add(i.text);
            return true;
        }).sort(function(a,b) { return a.y - b.y; });
    }""")
    print(f"\n  Categories ({len(categories)}):", flush=True)
    for c in categories:
        print(f"    ({c['x']},{c['y']}) '{c['text']}'", flush=True)

    # Click "Realistic" category to see realistic models
    for c in categories:
        if c['text'] == 'Realistic':
            print(f"\n  Clicking 'Realistic' at ({c['x']},{c['y']})...", flush=True)
            page.mouse.click(c['x'] + 20, c['y'] + 10)
            page.wait_for_timeout(1500)
            break

    ss(page, "P36_03_realistic_models")

    realistic = page.evaluate("""() => {
        var items = [];
        for (const el of document.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            var text = (el.innerText || '').trim();
            if (text && text.length > 3 && text.length < 40
                && !text.includes('\\n') && r.height > 10 && r.height < 25
                && r.width > 50 && r.width < 200 && r.y > 300 && r.y < 800
                && r.x > 400) {
                items.push({text: text});
            }
        }
        var seen = new Set();
        return items.filter(function(i) {
            if (seen.has(i.text)) return false;
            seen.add(i.text);
            return true;
        });
    }""")
    print(f"\n  Realistic models ({len(realistic)}):", flush=True)
    for m in realistic:
        print(f"    '{m['text']}'", flush=True)

    # Close picker
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)

    # ============================================================
    #  PART 2: CC REFERENCE MODE — PICK IMAGE
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 2: CC REFERENCE MODE — PICK IMAGE", flush=True)
    print("=" * 60, flush=True)

    # Open CC
    page.mouse.click(40, 306)
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

    ss(page, "P36_04_reference_mode")

    # Click "Pick Image" button
    pick_result = page.evaluate("""() => {
        var btn = document.querySelector('button.pick-image, button.cc-pick-image');
        if (!btn) {
            // Try text search
            for (const el of document.querySelectorAll('button')) {
                if ((el.innerText || '').trim().includes('Pick Image')) {
                    btn = el;
                    break;
                }
            }
        }
        if (btn) {
            var r = btn.getBoundingClientRect();
            btn.click();
            return {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)};
        }
        return null;
    }""")
    print(f"\n  Pick Image clicked: {pick_result}", flush=True)
    page.wait_for_timeout(2000)

    ss(page, "P36_05_pick_image_dialog")

    # Map what appeared
    pick_overlay = page.evaluate("""() => {
        var items = [];
        for (const el of document.querySelectorAll('*')) {
            var z = parseInt(window.getComputedStyle(el).zIndex) || 0;
            var r = el.getBoundingClientRect();
            if (z > 600 && r.width > 100 && r.height > 50) {
                items.push({
                    z: z,
                    text: (el.innerText || '').trim().substring(0, 300),
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                });
            }
        }
        return items.sort(function(a,b) { return b.z - a.z; }).slice(0, 5);
    }""")
    print(f"\n  Pick Image overlays: {len(pick_overlay)}", flush=True)
    for o in pick_overlay:
        print(f"    z={o['z']} ({o['x']},{o['y']}) {o['w']}x{o['h']}", flush=True)
        print(f"      '{o['text'][:150]}'", flush=True)

    # Check for file inputs
    file_inputs = page.evaluate("""() => {
        var inputs = [];
        for (const el of document.querySelectorAll('input[type="file"]')) {
            inputs.push({
                accept: el.accept || '',
                multiple: el.multiple,
                classes: (el.className || '').toString().substring(0, 50),
            });
        }
        return inputs;
    }""")
    print(f"\n  File inputs: {len(file_inputs)}", flush=True)
    for fi in file_inputs:
        print(f"    accept='{fi['accept']}' multiple={fi['multiple']}", flush=True)

    # Map ALL elements in the overlay
    if pick_overlay:
        pick_elements = page.evaluate("""() => {
            var items = [];
            for (const el of document.querySelectorAll('*')) {
                var z = parseInt(window.getComputedStyle(el).zIndex) || 0;
                var r = el.getBoundingClientRect();
                var text = (el.innerText || '').trim();
                if (z > 900 && text && text.length > 1 && text.length < 60
                    && !text.includes('\\n') && r.width > 20 && r.height > 8 && r.height < 50) {
                    items.push({
                        text: text,
                        tag: el.tagName,
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        classes: (el.className || '').toString().substring(0, 40),
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
        print(f"\n  Pick dialog elements ({len(pick_elements)}):", flush=True)
        for el in pick_elements[:25]:
            print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> c='{el['classes'][:25]}' '{el['text']}'", flush=True)

        # Look for upload button or drag area
        upload_in_pick = page.evaluate("""() => {
            var items = [];
            for (const el of document.querySelectorAll('*')) {
                var z = parseInt(window.getComputedStyle(el).zIndex) || 0;
                var r = el.getBoundingClientRect();
                var classes = (el.className || '').toString();
                if (z > 900 && (classes.includes('upload') || classes.includes('Upload')
                    || classes.includes('drag') || classes.includes('drop')
                    || classes.includes('browse'))) {
                    items.push({
                        tag: el.tagName,
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        classes: classes.substring(0, 80),
                        text: (el.innerText || '').trim().substring(0, 30),
                    });
                }
            }
            return items;
        }""")
        print(f"\n  Upload elements in dialog: {len(upload_in_pick)}", flush=True)
        for el in upload_in_pick:
            print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> '{el['classes'][:50]}' '{el['text']}'", flush=True)

    page.keyboard.press("Escape")
    page.wait_for_timeout(500)

    # ============================================================
    #  PART 3: CC STYLE MODEL SELECTOR
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 3: CC STYLE MODEL SELECTOR", flush=True)
    print("=" * 60, flush=True)

    # Scroll down to see Style toggle
    page.mouse.move(200, 600)
    for _ in range(3):
        page.mouse.wheel(0, 150)
        page.wait_for_timeout(200)
    page.wait_for_timeout(500)

    # Turn Style ON if not already
    style_toggle = page.evaluate("""() => {
        // Find the style toggle switch
        for (const el of document.querySelectorAll('button.switch')) {
            var r = el.getBoundingClientRect();
            if (r.y > 600 && r.y < 750 && r.x > 250 && r.x < 340) {
                var bg = window.getComputedStyle(el).backgroundColor;
                return {
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    bg: bg,
                    isOn: bg.includes('167') || bg.includes('220') || bg.includes('255, 2'),
                };
            }
        }
        return null;
    }""")
    print(f"  Style toggle: {style_toggle}", flush=True)

    if style_toggle and not style_toggle['isOn']:
        print("  Turning Style ON...", flush=True)
        page.mouse.click(style_toggle['x'] + style_toggle['w']//2, style_toggle['y'] + style_toggle['h']//2)
        page.wait_for_timeout(1000)

    # Click the style model name "Dzine 3D Render v2"
    style_model = page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text.includes('Dzine 3D Render') && r.x > 80 && r.x < 200
                && r.width > 100 && r.height > 20 && r.y > 600) {
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
    print(f"\n  Style model element: {style_model}", flush=True)

    if style_model:
        cx = style_model['x'] + style_model['w']//2
        cy = style_model['y'] + style_model['h']//2
        print(f"  Clicking style model at ({cx}, {cy})...", flush=True)
        page.mouse.click(cx, cy)
        page.wait_for_timeout(2000)

        ss(page, "P36_06_style_model_picker")

        # Check for overlay
        style_overlay = page.evaluate("""() => {
            for (const el of document.querySelectorAll('*')) {
                var z = parseInt(window.getComputedStyle(el).zIndex) || 0;
                var r = el.getBoundingClientRect();
                if (z > 900 && r.width > 200 && r.height > 100) {
                    return {
                        z: z,
                        text: (el.innerText || '').trim().substring(0, 500),
                        w: Math.round(r.width), h: Math.round(r.height),
                    };
                }
            }
            return null;
        }""")
        if style_overlay:
            print(f"\n  Style model picker: z={style_overlay['z']} {style_overlay['w']}x{style_overlay['h']}", flush=True)
            print(f"  Content: '{style_overlay['text'][:200]}'", flush=True)
        else:
            print("  No style model picker overlay appeared", flush=True)

        page.keyboard.press("Escape")
        page.wait_for_timeout(500)

    # ============================================================
    #  PART 4: GENERATION QUEUE STATUS
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 4: GENERATION QUEUE STATUS", flush=True)
    print("=" * 60, flush=True)

    # Check the right panel for queue status
    queue_status = page.evaluate("""() => {
        var items = [];
        for (const el of document.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            var text = (el.innerText || '').trim();
            if (r.x > 500 && r.y > 50 && r.y < 120
                && r.width > 20 && r.height > 10 && r.height < 40
                && text && text.length > 2 && text.length < 80
                && !text.includes('\\n')) {
                items.push({
                    text: text,
                    x: Math.round(r.x), y: Math.round(r.y),
                    classes: (el.className || '').toString().substring(0, 50),
                });
            }
        }
        var seen = new Set();
        return items.filter(function(i) {
            if (seen.has(i.text)) return false;
            seen.add(i.text);
            return true;
        }).sort(function(a,b) { return a.y - b.y; });
    }""")
    print(f"\n  Queue status area ({len(queue_status)}):", flush=True)
    for el in queue_status:
        print(f"    ({el['x']},{el['y']}) c='{el['classes'][:30]}' '{el['text']}'", flush=True)

    # Check for any result images (new CC images from the Pose generation)
    result_images = page.evaluate("""() => {
        var imgs = [];
        for (const img of document.querySelectorAll('img')) {
            var src = img.src || '';
            if (src.includes('static.dzine.ai') && src.includes('output')) {
                var r = img.getBoundingClientRect();
                imgs.push({
                    src: src.substring(0, 100),
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                });
            }
        }
        return imgs;
    }""")
    print(f"\n  Result images: {len(result_images)}", flush=True)
    for img in result_images:
        print(f"    ({img['x']},{img['y']}) {img['w']}x{img['h']} {img['src']}", flush=True)

    # ============================================================
    #  PART 5: UPLOAD SIDEBAR — WHAT IT ACTUALLY DOES
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 5: UPLOAD SIDEBAR BEHAVIOR", flush=True)
    print("=" * 60, flush=True)

    # Click Upload sidebar
    page.mouse.click(40, 81)
    page.wait_for_timeout(2000)

    # Map the ENTIRE left panel area
    left_panel = page.evaluate("""() => {
        var items = [];
        for (const el of document.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            var text = (el.innerText || '').trim();
            if (r.x > 60 && r.x < 400 && r.y > 30 && r.y < 150
                && r.width > 10 && r.height > 5
                && (text.length > 0 || el.tagName === 'INPUT' || el.tagName === 'BUTTON')) {
                items.push({
                    tag: el.tagName,
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    text: text.substring(0, 40),
                    classes: (el.className || '').toString().substring(0, 60),
                    display: window.getComputedStyle(el).display,
                });
            }
        }
        return items.sort(function(a,b) { return a.y - b.y; }).slice(0, 30);
    }""")
    print(f"\n  Upload sidebar area ({len(left_panel)}):", flush=True)
    for el in left_panel:
        print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> d={el['display']} c='{el['classes'][:30]}' '{el['text'][:30]}'", flush=True)

    ss(page, "P36_07_upload_sidebar")

    # Check if there's a drag-and-drop zone
    drop_zone = page.evaluate("""() => {
        // Look for elements that have drop event listeners
        // We can check for specific class names or attributes
        for (const el of document.querySelectorAll('[class*="drop"], [class*="upload"], [class*="drag"]')) {
            var r = el.getBoundingClientRect();
            if (r.x > 60 && r.x < 500 && r.width > 100 && r.height > 50) {
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
    print(f"\n  Drop zone: {drop_zone}", flush=True)

    ss(page, "P36_08_final")
    print(f"\n\n===== PHASE 36 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
