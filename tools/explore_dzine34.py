"""Phase 34: Model picker, file upload to canvas, CC Style click, AR dropdown.

Goals:
1. Click the ">" chevron on model name to open model picker
2. Explore the Aspect Ratio dropdown chevron for hidden sizes
3. Test uploading an image to canvas via DataTransfer/drop event
4. Click CC Style circle icon precisely
5. Find how the Upload sidebar actually works (canvas drag-drop?)
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

# Use existing Phase 31 image as test upload
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


def map_panel(page, x_min=60, x_max=400, y_min=50, y_max=900, limit=40):
    return page.evaluate("""(args) => {
        const items = [];
        for (const el of document.querySelectorAll('*')) {
            const r = el.getBoundingClientRect();
            const text = (el.innerText || '').trim();
            if (r.x > args.x_min && r.x < args.x_max
                && r.y > args.y_min && r.y < args.y_max
                && r.width > 15 && r.width < 350 && text
                && text.length > 0 && text.length < 80
                && !text.includes('\\n')
                && r.height > 8 && r.height < 60) {
                items.push({
                    text: text,
                    tag: el.tagName,
                    x: Math.round(r.x),
                    y: Math.round(r.y),
                    w: Math.round(r.width),
                    h: Math.round(r.height),
                });
            }
        }
        const seen = new Set();
        return items.filter(i => {
            const key = i.text + '|' + Math.round(i.y / 3);
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
        }).sort((a, b) => a.y - b.y);
    }""", {"x_min": x_min, "x_max": x_max, "y_min": y_min, "y_max": y_max})[:limit]


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
    #  PART 1: TXT2IMG MODEL PICKER
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 1: TXT2IMG MODEL PICKER", flush=True)
    print("=" * 60, flush=True)

    page.mouse.click(40, 197)  # Txt2Img sidebar
    page.wait_for_timeout(2000)
    close_dialogs(page)

    # Find and click the ">" chevron next to model name
    # The model row is at approximately (92, 97) with "Nano Banana Pro"
    # The ">" chevron should be to the right of the model name
    chevron = page.evaluate("""() => {
        // Look for clickable elements near the model name area
        const results = [];
        for (const el of document.querySelectorAll('*')) {
            const r = el.getBoundingClientRect();
            // Model row area: x > 200, y between 95-120
            if (r.x > 200 && r.x < 280 && r.y > 95 && r.y < 125
                && r.width > 10 && r.width < 50 && r.height > 10 && r.height < 40) {
                const cursor = window.getComputedStyle(el).cursor;
                results.push({
                    tag: el.tagName,
                    x: Math.round(r.x),
                    y: Math.round(r.y),
                    w: Math.round(r.width),
                    h: Math.round(r.height),
                    cursor: cursor,
                    text: (el.innerText || '').trim().substring(0, 20),
                });
            }
        }
        return results;
    }""")
    print(f"\n  Elements near model chevron: {len(chevron)}", flush=True)
    for el in chevron:
        print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> cursor={el['cursor']} '{el['text']}'", flush=True)

    # Click directly on the ">" area — from screenshot it's after "Nano Banana Pro" text
    # Model text ends around x=230, chevron at ~x=250-260, y=110
    print("\n  Clicking model chevron area at (255, 112)...", flush=True)
    page.mouse.click(255, 112)
    page.wait_for_timeout(2000)

    ss(page, "P34_01_model_picker")

    # Check for high-z overlay (model picker dialog)
    overlays = page.evaluate("""() => {
        const items = [];
        for (const el of document.querySelectorAll('*')) {
            const style = window.getComputedStyle(el);
            const z = parseInt(style.zIndex) || 0;
            const r = el.getBoundingClientRect();
            const text = (el.innerText || '').trim();
            if (z > 100 && r.width > 200 && r.height > 100 && text.length > 10) {
                items.push({
                    z: z,
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    text: text.substring(0, 200),
                });
            }
        }
        return items.sort((a, b) => b.z - a.z).slice(0, 5);
    }""")
    print(f"\n  High-z overlays: {len(overlays)}", flush=True)
    for o in overlays:
        print(f"    z={o['z']} ({o['x']},{o['y']}) {o['w']}x{o['h']}", flush=True)
        print(f"      text: '{o['text'][:120]}'", flush=True)

    # If no overlay, try clicking the model name directly
    if len(overlays) <= 3:
        print("\n  No model picker appeared. Trying model name click...", flush=True)
        page.mouse.click(185, 112)
        page.wait_for_timeout(2000)
        ss(page, "P34_01b_model_name_click")

        overlays2 = page.evaluate("""() => {
            const items = [];
            for (const el of document.querySelectorAll('*')) {
                const style = window.getComputedStyle(el);
                const z = parseInt(style.zIndex) || 0;
                const r = el.getBoundingClientRect();
                if (z > 500 && r.width > 100 && r.height > 50) {
                    return [{
                        z: z,
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        text: (el.innerText || '').trim().substring(0, 300),
                    }];
                }
            }
            return [];
        }""")
        print(f"  High-z overlay after name click: {len(overlays2)}", flush=True)
        for o in overlays2:
            print(f"    z={o['z']} text: '{o['text'][:150]}'", flush=True)

    page.keyboard.press("Escape")
    page.wait_for_timeout(500)

    # ============================================================
    #  PART 2: TXT2IMG ASPECT RATIO DROPDOWN
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 2: ASPECT RATIO DROPDOWN", flush=True)
    print("=" * 60, flush=True)

    # From P33_06 screenshot, there's a "v" chevron after 16:9 in AR row
    # AR row is at y≈460, the chevron is after the last ratio option
    # From panel data: 9:16 at x=104, 1:1 at x=168, 16:9 at x=232, then chevron
    ar_chevron = page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            const r = el.getBoundingClientRect();
            // Look for the chevron/arrow after 16:9
            if (r.x > 280 && r.x < 320 && r.y > 450 && r.y < 480
                && r.width > 5 && r.width < 40 && r.height > 5 && r.height < 30) {
                const cursor = window.getComputedStyle(el).cursor;
                return {
                    tag: el.tagName,
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    cursor: cursor,
                };
            }
        }
        return null;
    }""")
    print(f"\n  AR chevron: {ar_chevron}", flush=True)

    # Click the chevron area
    print("  Clicking AR dropdown at (297, 466)...", flush=True)
    page.mouse.click(297, 466)
    page.wait_for_timeout(1500)

    ss(page, "P34_02_ar_dropdown")

    # Check for dropdown
    ar_options = page.evaluate("""() => {
        const items = [];
        for (const el of document.querySelectorAll('*')) {
            const style = window.getComputedStyle(el);
            const z = parseInt(style.zIndex) || 0;
            const r = el.getBoundingClientRect();
            const text = (el.innerText || '').trim();
            if (z > 50 && text && text.length > 1 && text.length < 30
                && !text.includes('\\n') && r.width > 20 && r.height > 10 && r.height < 40) {
                items.push({
                    z: z, text: text,
                    x: Math.round(r.x), y: Math.round(r.y),
                });
            }
        }
        const seen = new Set();
        return items.filter(i => {
            const key = i.text + '|' + Math.round(i.y / 3);
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
        }).sort((a, b) => a.y - b.y);
    }""")
    print(f"\n  AR dropdown options: {len(ar_options)}", flush=True)
    for o in ar_options[:15]:
        print(f"    z={o['z']} ({o['x']},{o['y']}) '{o['text']}'", flush=True)

    page.keyboard.press("Escape")
    page.wait_for_timeout(500)

    # ============================================================
    #  PART 3: UPLOAD IMAGE TO CANVAS VIA DRAG & DROP
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 3: CANVAS IMAGE UPLOAD", flush=True)
    print("=" * 60, flush=True)

    if TEST_IMAGE.exists():
        print(f"  Test image: {TEST_IMAGE} ({TEST_IMAGE.stat().st_size} bytes)", flush=True)

        # Method 1: Try to find a hidden file input and use set_input_files
        # First, check if Upload sidebar reveals one
        page.mouse.click(40, 81)  # Upload sidebar
        page.wait_for_timeout(2000)

        # Map what the Upload panel actually shows
        upload_elements = page.evaluate("""() => {
            const items = [];
            for (const el of document.querySelectorAll('*')) {
                const r = el.getBoundingClientRect();
                const text = (el.innerText || '').trim();
                if (r.x > 60 && r.x < 300 && r.y > 50 && r.y < 250
                    && r.width > 15 && r.height > 8) {
                    items.push({
                        tag: el.tagName,
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        text: text.substring(0, 50),
                        role: el.getAttribute('role') || '',
                        classes: (el.className || '').toString().substring(0, 60),
                    });
                }
            }
            const seen = new Set();
            return items.filter(i => {
                const key = i.tag + '|' + Math.round(i.y / 5) + '|' + Math.round(i.x / 5);
                if (seen.has(key)) return false;
                seen.add(key);
                return true;
            }).sort((a, b) => a.y - b.y);
        }""")
        print(f"\n  Upload panel elements ({len(upload_elements)}):", flush=True)
        for el in upload_elements[:20]:
            print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> classes='{el['classes'][:40]}' text='{el['text'][:30]}'", flush=True)

        ss(page, "P34_03_upload_panel_detail")

        # Method 2: Create a file input via JS and trigger it
        print("\n  Attempting JS file input injection...", flush=True)
        upload_result = page.evaluate("""(filePath) => {
            // Check if there's a hidden file input we missed
            const allInputs = document.querySelectorAll('input');
            const fileInputs = [...allInputs].filter(i => i.type === 'file');
            if (fileInputs.length > 0) {
                return { method: 'existing_input', count: fileInputs.length };
            }

            // Look for upload-related event listeners by checking common patterns
            const uploadAreas = [];
            for (const el of document.querySelectorAll('[class*="upload"], [class*="Upload"], [class*="drop"], [class*="Drop"], [data-v-35c00eba]')) {
                const r = el.getBoundingClientRect();
                uploadAreas.push({
                    tag: el.tagName,
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    classes: el.className.toString().substring(0, 80),
                });
            }
            return { method: 'class_search', areas: uploadAreas };
        }""", str(TEST_IMAGE))
        print(f"  Upload search result: {json.dumps(upload_result, indent=2)}", flush=True)

        # Method 3: Try dispatching a drag-and-drop file event on the canvas
        print("\n  Testing canvas drop event simulation...", flush=True)

        # First, find the canvas element
        canvas = page.evaluate("""() => {
            // Look for the main canvas/workspace area
            for (const el of document.querySelectorAll('canvas, [class*="canvas"], [class*="Canvas"], [class*="workspace"]')) {
                const r = el.getBoundingClientRect();
                if (r.width > 500 && r.height > 400) {
                    return {
                        tag: el.tagName,
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        id: el.id || '',
                        classes: (el.className || '').toString().substring(0, 80),
                    };
                }
            }
            return null;
        }""")
        print(f"  Canvas element: {canvas}", flush=True)

        # Method 4: Check if the Upload sidebar is just the same as Assets with different tab
        # Let's check the "My Assets" -> Upload button in the Assets panel
        print("\n  Checking Assets panel for upload mechanism...", flush=True)
        page.mouse.click(40, 136)  # Assets sidebar
        page.wait_for_timeout(2000)

        # Look for the specific icon button we found earlier at (261,97)
        print("  Clicking asset header button at (261, 97)...", flush=True)
        page.mouse.click(261, 97)
        page.wait_for_timeout(2000)

        ss(page, "P34_04_asset_button_click")

        # Check if a file picker appeared (OS dialog — we won't see it, but check input)
        file_inputs_after = page.evaluate("""() => {
            const inputs = [];
            for (const el of document.querySelectorAll('input[type="file"]')) {
                inputs.push({
                    accept: el.accept || '',
                    multiple: el.multiple,
                    x: Math.round(el.getBoundingClientRect().x),
                });
            }
            return inputs;
        }""")
        print(f"  File inputs after asset button: {len(file_inputs_after)}", flush=True)

        # Check if a new dialog/modal appeared
        new_overlays = page.evaluate("""() => {
            const items = [];
            for (const el of document.querySelectorAll('*')) {
                const style = window.getComputedStyle(el);
                const z = parseInt(style.zIndex) || 0;
                const r = el.getBoundingClientRect();
                if (z > 500 && r.width > 100 && r.height > 50) {
                    items.push({
                        z: z,
                        text: (el.innerText || '').trim().substring(0, 200),
                    });
                }
            }
            return items;
        }""")
        print(f"  New overlays: {len(new_overlays)}", flush=True)
        for o in new_overlays:
            print(f"    z={o['z']} '{o['text'][:100]}'", flush=True)

        # Try looking at icon buttons more carefully in the Assets header area
        asset_icons = page.evaluate("""() => {
            const items = [];
            for (const el of document.querySelectorAll('button, svg, [role="button"]')) {
                const r = el.getBoundingClientRect();
                if (r.x > 80 && r.x < 300 && r.y > 60 && r.y < 120
                    && r.width > 5 && r.height > 5) {
                    const svg = el.querySelector('svg') || (el.tagName === 'SVG' ? el : null);
                    let svgPath = '';
                    if (svg) {
                        const path = svg.querySelector('path');
                        svgPath = path ? path.getAttribute('d')?.substring(0, 40) || '' : '';
                    }
                    items.push({
                        tag: el.tagName,
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        text: (el.innerText || '').trim().substring(0, 20),
                        svgPath: svgPath,
                    });
                }
            }
            return items.sort((a, b) => a.x - b.x);
        }""")
        print(f"\n  Asset header icons ({len(asset_icons)}):", flush=True)
        for el in asset_icons:
            print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> text='{el['text']}' svg='{el['svgPath'][:30]}'", flush=True)

    else:
        print(f"  No test image found at {TEST_IMAGE}", flush=True)

    # ============================================================
    #  PART 4: CC STYLE — PRECISE CLICK
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 4: CC STYLE ICON PRECISE CLICK", flush=True)
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

    # Scroll down to see Style
    page.mouse.move(200, 600)
    for _ in range(3):
        page.mouse.wheel(0, 150)
        page.wait_for_timeout(300)

    # Find the Style area precisely
    style_area = page.evaluate("""() => {
        const results = [];
        for (const el of document.querySelectorAll('*')) {
            const r = el.getBoundingClientRect();
            const text = (el.innerText || '').trim();
            // Look for "Style" label and nearby elements
            if (r.x > 80 && r.x < 200 && r.width > 10 && r.width < 250 && r.height < 40) {
                if (text === 'Style' || text === 'NEW' || text === 'Style\nNEW') {
                    results.push({
                        tag: el.tagName,
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        text: text,
                    });
                }
            }
            // Also look for small circles/icons near Style (the style indicator)
            if (r.x > 80 && r.x < 120 && r.width >= 12 && r.width <= 30
                && r.height >= 12 && r.height <= 30) {
                const bg = window.getComputedStyle(el).backgroundColor;
                const borderRadius = window.getComputedStyle(el).borderRadius;
                if (bg !== 'rgba(0, 0, 0, 0)' || borderRadius.includes('50%')) {
                    results.push({
                        tag: el.tagName,
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        text: '(icon)',
                        bg: bg,
                        borderRadius: borderRadius,
                    });
                }
            }
        }
        return results;
    }""")
    print(f"\n  Style area elements ({len(style_area)}):", flush=True)
    for el in style_area:
        extra = f" bg={el.get('bg','')} br={el.get('borderRadius','')}" if el.get('bg') else ""
        print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> '{el['text']}'{extra}", flush=True)

    # Find everything between Style and Non-Explicit
    style_row = page.evaluate("""() => {
        // Find Style label y position
        let styleY = null;
        for (const el of document.querySelectorAll('*')) {
            if ((el.innerText || '').trim() === 'Style') {
                const r = el.getBoundingClientRect();
                if (r.x > 80 && r.x < 200) {
                    styleY = r.y;
                    break;
                }
            }
        }
        if (!styleY) return null;

        const items = [];
        for (const el of document.querySelectorAll('*')) {
            const r = el.getBoundingClientRect();
            if (r.y > styleY - 10 && r.y < styleY + 30 && r.x > 60 && r.x < 350
                && r.width > 5 && r.height > 5) {
                items.push({
                    tag: el.tagName,
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    text: (el.innerText || '').trim().substring(0, 20),
                    cursor: window.getComputedStyle(el).cursor,
                    bg: window.getComputedStyle(el).backgroundColor,
                });
            }
        }
        return {styleY: Math.round(styleY), elements: items.sort((a, b) => a.x - b.x)};
    }""")
    if style_row:
        print(f"\n  Style row at y={style_row['styleY']} ({len(style_row['elements'])} elements):", flush=True)
        for el in style_row['elements'][:15]:
            print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> cursor={el['cursor']} bg={el['bg'][:30]} '{el['text']}'", flush=True)

        # Click each unique element in the style row to find the picker
        seen_x = set()
        for el in style_row['elements']:
            rx = round(el['x'] / 10)
            if rx in seen_x:
                continue
            seen_x.add(rx)
            if el['w'] > 200:  # Skip large container elements
                continue
            cx = el['x'] + el['w'] // 2
            cy = el['y'] + el['h'] // 2
            print(f"\n  Clicking ({cx}, {cy}) <{el['tag']}> '{el['text']}'...", flush=True)
            page.mouse.click(cx, cy)
            page.wait_for_timeout(1500)

            # Check for overlay
            overlay = page.evaluate("""() => {
                for (const el of document.querySelectorAll('*')) {
                    const style = window.getComputedStyle(el);
                    const z = parseInt(style.zIndex) || 0;
                    const r = el.getBoundingClientRect();
                    if (z > 600 && r.width > 100 && r.height > 50) {
                        return {
                            z: z,
                            text: (el.innerText || '').trim().substring(0, 300),
                            x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height),
                        };
                    }
                }
                return null;
            }""")
            if overlay:
                print(f"    OVERLAY z={overlay['z']}: '{overlay['text'][:100]}'", flush=True)
                ss(page, f"P34_05_style_overlay")
                page.keyboard.press("Escape")
                page.wait_for_timeout(500)
                break

    # ============================================================
    #  PART 5: COMMUNITY STYLES PAGE
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 5: EXPLORE MODEL DROPDOWN + STYLE MODELS", flush=True)
    print("=" * 60, flush=True)

    # Go back to Txt2Img
    page.mouse.click(40, 197)
    page.wait_for_timeout(2000)

    # The model area has: icon (banana) + "Nano Banana Pro" text + ">" + "+"
    # Try clicking the specific chevron — in the screenshot it's at ~(253, 112) based on
    # "Nano Banana Pro >" layout
    # The ">" is actually an SVG inside a clickable element

    # Find all clickable elements in the model header row
    model_row = page.evaluate("""() => {
        const items = [];
        for (const el of document.querySelectorAll('*')) {
            const r = el.getBoundingClientRect();
            if (r.y > 90 && r.y < 130 && r.x > 80 && r.x < 320
                && r.width > 5 && r.height > 5 && r.width < 250) {
                const cursor = window.getComputedStyle(el).cursor;
                items.push({
                    tag: el.tagName,
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    text: (el.innerText || '').trim().substring(0, 30) || '(empty)',
                    cursor: cursor,
                    clickable: cursor === 'pointer',
                });
            }
        }
        return items.sort((a, b) => a.x - b.x);
    }""")
    print(f"\n  Model row elements ({len(model_row)}):", flush=True)
    for el in model_row[:15]:
        click = " [CLICK]" if el['clickable'] else ""
        print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> '{el['text']}'{click}", flush=True)

    # Click pointer elements
    for el in model_row:
        if el['clickable'] and el['w'] < 100:
            cx = el['x'] + el['w'] // 2
            cy = el['y'] + el['h'] // 2
            print(f"\n  Clicking pointer element at ({cx}, {cy}) '{el['text']}'...", flush=True)
            page.mouse.click(cx, cy)
            page.wait_for_timeout(2000)

            ss(page, "P34_06_model_dropdown")

            # Check what opened
            new_content = page.evaluate("""() => {
                // Check if the page navigated or a big overlay appeared
                const url = window.location.href;
                const overlays = [];
                for (const el of document.querySelectorAll('*')) {
                    const style = window.getComputedStyle(el);
                    const z = parseInt(style.zIndex) || 0;
                    const r = el.getBoundingClientRect();
                    if (z > 500 && r.width > 200 && r.height > 100) {
                        overlays.push({
                            z: z,
                            text: (el.innerText || '').trim().substring(0, 400),
                        });
                    }
                }
                return { url: url, overlays: overlays };
            }""")
            print(f"  URL: {new_content['url']}", flush=True)
            print(f"  Overlays: {len(new_content['overlays'])}", flush=True)
            for o in new_content['overlays']:
                print(f"    z={o['z']}: '{o['text'][:150]}'", flush=True)

            # Navigate back if needed
            if new_content['url'] != CANVAS_URL and '?' not in new_content['url']:
                page.go_back()
                page.wait_for_timeout(2000)
            elif new_content['overlays']:
                page.keyboard.press("Escape")
                page.wait_for_timeout(500)
            break

    ss(page, "P34_07_final")
    print(f"\n\n===== PHASE 34 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
