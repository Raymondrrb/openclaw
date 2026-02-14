"""Phase 33: Deep dive into Img2Img, CC styles, Generation Mode, Upload.

Goals:
1. Properly enter Img2Img mode (select layer first, then click Img2Img)
2. Scroll CC panel to see Generation Mode options
3. Click CC Style icon to explore available styles
4. Find the actual file upload mechanism (look for hidden triggers)
5. Upload a test image via Assets panel
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

# A small test image for upload testing
TEST_IMAGE = SS_DIR / "e2e31_thumbnail.png"  # Use existing Phase 31 image


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
    """Generic panel mapper."""
    items = page.evaluate("""(args) => {
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
    }""", {"x_min": x_min, "x_max": x_max, "y_min": y_min, "y_max": y_max})
    return items[:limit]


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
    #  PART 1: CC STYLE DEEP DIVE
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 1: CC STYLE + GENERATION MODE", flush=True)
    print("=" * 60, flush=True)

    # Open CC
    page.mouse.click(40, 306)
    page.wait_for_timeout(1500)
    close_dialogs(page)

    # Enter CC generation
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

    # Scroll the left panel down to see Generation Mode
    panel = page.evaluate("""() => {
        // Find scrollable panel container
        for (const el of document.querySelectorAll('div')) {
            const r = el.getBoundingClientRect();
            const style = window.getComputedStyle(el);
            if (r.x > 30 && r.x < 100 && r.width > 200 && r.width < 350
                && r.height > 300
                && (style.overflowY === 'auto' || style.overflowY === 'scroll')) {
                return {
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    scrollTop: el.scrollTop,
                    scrollHeight: el.scrollHeight,
                    clientHeight: el.clientHeight,
                };
            }
        }
        return null;
    }""")
    print(f"\n  Scrollable panel: {panel}", flush=True)

    # Try scrolling down via mouse wheel on the panel
    page.mouse.move(200, 600)
    for _ in range(5):
        page.mouse.wheel(0, 200)
        page.wait_for_timeout(300)

    page.wait_for_timeout(1000)
    ss(page, "P33_01_cc_scrolled")

    # Map panel after scroll
    items = map_panel(page, y_min=200)
    print(f"\n  CC panel after scroll ({len(items)}):", flush=True)
    for el in items:
        print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> '{el['text']}'", flush=True)

    # Now click the Style icon/area
    # From screenshot it's at ~(124,775) with "Style" text and "NEW" badge
    # After scroll it may have moved up. Let's find it.
    style_elem = page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            const text = (el.innerText || '').trim();
            const r = el.getBoundingClientRect();
            if (text === 'Style' && r.x > 60 && r.x < 200 && r.width > 20 && r.width < 80) {
                return {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)};
            }
        }
        return null;
    }""")
    print(f"\n  Style element: {style_elem}", flush=True)

    if style_elem:
        # Click the area next to "Style" — the style icon is usually to the right
        icon_x = style_elem['x'] + style_elem['w'] + 20
        icon_y = style_elem['y'] + style_elem['h'] // 2
        print(f"  Clicking style icon area at ({icon_x}, {icon_y})", flush=True)
        page.mouse.click(icon_x, icon_y)
        page.wait_for_timeout(2000)

        ss(page, "P33_02_cc_style_clicked")

        # Check for any dropdown/overlay
        overlays = page.evaluate("""() => {
            const items = [];
            for (const el of document.querySelectorAll('*')) {
                const style = window.getComputedStyle(el);
                const z = parseInt(style.zIndex) || 0;
                const r = el.getBoundingClientRect();
                if (z > 50 && r.width > 100 && r.height > 50) {
                    const text = (el.innerText || '').trim().substring(0, 100);
                    items.push({
                        z: z,
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        text: text,
                        tag: el.tagName,
                    });
                }
            }
            return items.sort((a, b) => b.z - a.z).slice(0, 10);
        }""")
        print(f"\n  High z-index overlays: {len(overlays)}", flush=True)
        for o in overlays:
            print(f"    z={o['z']} ({o['x']},{o['y']}) {o['w']}x{o['h']} '{o['text'][:60]}'", flush=True)

    # Try to find Generation Mode by looking for radio/toggle elements
    gen_mode = page.evaluate("""() => {
        const items = [];
        for (const el of document.querySelectorAll('*')) {
            const text = (el.innerText || '').trim();
            const r = el.getBoundingClientRect();
            if ((text.includes('Generation Mode') || text.includes('Quality') || text.includes('Speed')
                 || text.includes('Balanced') || text.includes('Fast') || text.includes('High'))
                && r.x > 60 && r.x < 400 && r.width > 15) {
                items.push({
                    text: text.substring(0, 60),
                    tag: el.tagName,
                    x: Math.round(r.x),
                    y: Math.round(r.y),
                    w: Math.round(r.width),
                    h: Math.round(r.height),
                });
            }
        }
        return items;
    }""")
    print(f"\n  Generation Mode elements: {len(gen_mode)}", flush=True)
    for el in gen_mode:
        print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> '{el['text']}'", flush=True)

    page.keyboard.press("Escape")
    page.wait_for_timeout(500)

    # ============================================================
    #  PART 2: ENTER IMG2IMG VIA LAYER SELECTION
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 2: IMG2IMG (SELECT LAYER FIRST)", flush=True)
    print("=" * 60, flush=True)

    # First click Layers tab
    layers_tab = page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            const text = (el.innerText || '').trim();
            const r = el.getBoundingClientRect();
            if (text === 'Layers' && r.x > 500 && r.y < 60 && r.width > 30 && r.width < 100) {
                el.click();
                return {x: Math.round(r.x), y: Math.round(r.y)};
            }
        }
        return null;
    }""")
    print(f"  Layers tab: {layers_tab}", flush=True)
    page.wait_for_timeout(1000)

    # Click first layer (Layer 2 - usually the topmost generated image)
    layer_btn = page.evaluate("""() => {
        for (const el of document.querySelectorAll('button')) {
            const text = (el.innerText || '').trim();
            if (text.includes('Layer 2') || text.includes('Layer 1')) {
                const r = el.getBoundingClientRect();
                if (r.x > 500 && r.width > 80) {
                    el.click();
                    return {text: text.substring(0, 30), x: Math.round(r.x), y: Math.round(r.y)};
                }
            }
        }
        return null;
    }""")
    print(f"  Layer clicked: {layer_btn}", flush=True)
    page.wait_for_timeout(1000)

    # Now click Img2Img sidebar
    page.mouse.click(40, 252)
    page.wait_for_timeout(2000)
    close_dialogs(page)

    ss(page, "P33_03_img2img_with_layer")

    # Map the panel - with layer selected, Img2Img should show full UI
    items = map_panel(page, y_min=50)
    print(f"\n  Img2Img with layer ({len(items)}):", flush=True)
    for el in items:
        print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> '{el['text']}'", flush=True)

    # Check for file inputs again
    file_inputs = page.evaluate("""() => {
        const inputs = [];
        for (const el of document.querySelectorAll('input')) {
            inputs.push({
                type: el.type || '',
                accept: el.accept || '',
                hidden: el.hidden || el.style.display === 'none' || el.getBoundingClientRect().width === 0,
            });
        }
        return inputs.filter(i => i.type === 'file');
    }""")
    print(f"\n  File inputs: {len(file_inputs)}", flush=True)
    for fi in file_inputs:
        print(f"    accept='{fi['accept']}' hidden={fi['hidden']}", flush=True)

    # ============================================================
    #  PART 3: UPLOAD SIDEBAR - FIND THE UPLOAD MECHANISM
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 3: UPLOAD SIDEBAR MECHANISM", flush=True)
    print("=" * 60, flush=True)

    # The Upload icon is at y=81 in the sidebar. Let me look at ALL sidebar icons.
    sidebar_icons = page.evaluate("""() => {
        const items = [];
        for (const el of document.querySelectorAll('*')) {
            const r = el.getBoundingClientRect();
            if (r.x >= 0 && r.x < 60 && r.width > 30 && r.width < 80
                && r.height > 20 && r.height < 80 && r.y > 50 && r.y < 500) {
                const text = (el.innerText || '').trim();
                items.push({
                    tag: el.tagName,
                    x: Math.round(r.x),
                    y: Math.round(r.y),
                    w: Math.round(r.width),
                    h: Math.round(r.height),
                    text: text.substring(0, 30) || '(no text)',
                    role: el.getAttribute('role') || '',
                    title: el.getAttribute('title') || '',
                    ariaLabel: el.getAttribute('aria-label') || '',
                });
            }
        }
        const seen = new Set();
        return items.filter(i => {
            const key = Math.round(i.y / 10);
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
        }).sort((a, b) => a.y - b.y);
    }""")
    print(f"\n  Sidebar icons ({len(sidebar_icons)}):", flush=True)
    for el in sidebar_icons:
        print(f"    y={el['y']} {el['w']}x{el['h']} <{el['tag']}> text='{el['text']}' title='{el['title']}' aria='{el['ariaLabel']}'", flush=True)

    # Click "Upload" icon and look for upload buttons in the panel
    page.mouse.click(40, 81)
    page.wait_for_timeout(2000)
    close_dialogs(page)

    ss(page, "P33_04_upload_panel")

    # Look for upload buttons/areas in the panel
    upload_btns = page.evaluate("""() => {
        const items = [];
        for (const el of document.querySelectorAll('button, div[role="button"], a')) {
            const r = el.getBoundingClientRect();
            const text = (el.innerText || '').trim();
            if (r.x > 60 && r.x < 400 && r.y > 50 && r.y < 900
                && r.width > 20 && text && text.length < 60
                && (text.includes('Upload') || text.includes('upload')
                    || text.includes('Import') || text.includes('import')
                    || text.includes('Drag') || text.includes('drag')
                    || text.includes('Browse') || text.includes('browse')
                    || text.includes('+') || text.includes('Add'))) {
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
        return items;
    }""")
    print(f"\n  Upload-related buttons: {len(upload_btns)}", flush=True)
    for el in upload_btns:
        print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> '{el['text']}'", flush=True)

    # Now check if the page uses React drag-and-drop by looking for specific attributes
    dnd = page.evaluate("""() => {
        const items = [];
        for (const el of document.querySelectorAll('*')) {
            const r = el.getBoundingClientRect();
            if (r.x > 60 && r.x < 400 && r.y > 50 && r.y < 900
                && r.width > 100 && r.height > 50) {
                const attrs = {};
                for (const attr of el.attributes || []) {
                    if (attr.name.startsWith('data-') || attr.name.includes('drop')
                        || attr.name.includes('drag') || attr.name.includes('upload')
                        || attr.name.includes('file')) {
                        attrs[attr.name] = attr.value;
                    }
                }
                if (Object.keys(attrs).length > 0) {
                    items.push({
                        tag: el.tagName,
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        attrs: attrs,
                    });
                }
            }
        }
        return items;
    }""")
    print(f"\n  Elements with data/drag/upload attrs: {len(dnd)}", flush=True)
    for el in dnd:
        print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> attrs={el['attrs']}", flush=True)

    # ============================================================
    #  PART 4: ASSETS UPLOAD BUTTON
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 4: ASSETS PANEL UPLOAD MECHANISM", flush=True)
    print("=" * 60, flush=True)

    page.mouse.click(40, 136)  # Assets sidebar
    page.wait_for_timeout(2000)
    close_dialogs(page)

    # Map ALL buttons and clickable elements in Assets panel
    asset_btns = page.evaluate("""() => {
        const items = [];
        for (const el of document.querySelectorAll('button, svg, [role="button"]')) {
            const r = el.getBoundingClientRect();
            if (r.x > 60 && r.x < 300 && r.y > 50 && r.y < 120
                && r.width > 10 && r.width < 60 && r.height > 10) {
                const text = (el.innerText || '').trim();
                items.push({
                    tag: el.tagName,
                    x: Math.round(r.x),
                    y: Math.round(r.y),
                    w: Math.round(r.width),
                    h: Math.round(r.height),
                    text: text.substring(0, 30) || '(icon)',
                    title: el.getAttribute('title') || '',
                    ariaLabel: el.getAttribute('aria-label') || '',
                });
            }
        }
        return items.sort((a, b) => a.x - b.x);
    }""")
    print(f"\n  Assets header buttons ({len(asset_btns)}):", flush=True)
    for el in asset_btns:
        print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> text='{el['text']}' title='{el['title']}'", flush=True)

    # Look for folder-create and upload icons in top row
    # From screenshot, there's a row of icons near the top of Assets panel
    # Try clicking each one to find Upload
    icon_row = page.evaluate("""() => {
        const items = [];
        for (const el of document.querySelectorAll('*')) {
            const r = el.getBoundingClientRect();
            if (r.x > 90 && r.x < 220 && r.y > 75 && r.y < 100
                && r.width > 15 && r.width < 40 && r.height > 15 && r.height < 40) {
                items.push({
                    tag: el.tagName,
                    x: Math.round(r.x),
                    y: Math.round(r.y),
                    w: Math.round(r.width),
                    h: Math.round(r.height),
                    cursor: window.getComputedStyle(el).cursor,
                });
            }
        }
        const seen = new Set();
        return items.filter(i => {
            const key = Math.round(i.x / 8);
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
        }).sort((a, b) => a.x - b.x);
    }""")
    print(f"\n  Assets icon row ({len(icon_row)}):", flush=True)
    for el in icon_row:
        print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> cursor={el['cursor']}", flush=True)

    # Click each icon and check what happens
    for i, icon in enumerate(icon_row[:5]):
        print(f"\n  Clicking icon at ({icon['x']},{icon['y']})...", flush=True)
        page.mouse.click(icon['x'] + icon['w']//2, icon['y'] + icon['h']//2)
        page.wait_for_timeout(1500)

        # Check if file input appeared
        new_file_inputs = page.evaluate("""() => {
            const inputs = [];
            for (const el of document.querySelectorAll('input[type="file"]')) {
                inputs.push({
                    accept: el.accept || '',
                    x: Math.round(el.getBoundingClientRect().x),
                });
            }
            return inputs;
        }""")
        print(f"    File inputs after click: {len(new_file_inputs)}", flush=True)
        for fi in new_file_inputs:
            print(f"      accept='{fi['accept']}'", flush=True)

        # Check for overlays/dialogs
        overlay_text = page.evaluate("""() => {
            for (const el of document.querySelectorAll('*')) {
                const style = window.getComputedStyle(el);
                const z = parseInt(style.zIndex) || 0;
                const r = el.getBoundingClientRect();
                if (z > 100 && r.width > 200 && r.height > 100) {
                    return (el.innerText || '').trim().substring(0, 200);
                }
            }
            return null;
        }""")
        if overlay_text:
            print(f"    Overlay: '{overlay_text[:100]}'", flush=True)
            ss(page, f"P33_05_asset_icon_{i}")
            page.keyboard.press("Escape")
            page.wait_for_timeout(500)

    # ============================================================
    #  PART 5: TXT2IMG STYLE SELECTOR - FIND IT
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 5: TXT2IMG STYLE SELECTOR DETAIL", flush=True)
    print("=" * 60, flush=True)

    page.mouse.click(40, 197)  # Txt2Img sidebar
    page.wait_for_timeout(2000)
    close_dialogs(page)

    # Map the FULL panel with wider range
    items = map_panel(page, y_min=50, y_max=900, limit=50)
    print(f"\n  Txt2Img full panel ({len(items)}):", flush=True)
    for el in items:
        print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> '{el['text']}'", flush=True)

    # Look specifically for model selector
    model = page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            const text = (el.innerText || '').trim();
            const r = el.getBoundingClientRect();
            if (text.includes('Nano Banana') && r.x > 80 && r.x < 200 && r.width > 60) {
                // Click the model selector area
                el.click();
                return {text: text, x: Math.round(r.x), y: Math.round(r.y)};
            }
        }
        return null;
    }""")
    print(f"\n  Model selector: {model}", flush=True)
    page.wait_for_timeout(2000)

    ss(page, "P33_06_model_selector")

    # Check for model dropdown
    model_options = page.evaluate("""() => {
        const items = [];
        for (const el of document.querySelectorAll('*')) {
            const style = window.getComputedStyle(el);
            const z = parseInt(style.zIndex) || 0;
            const r = el.getBoundingClientRect();
            const text = (el.innerText || '').trim();
            if (z > 50 && text && text.length > 2 && text.length < 80
                && !text.includes('\\n')
                && r.width > 30 && r.height > 10 && r.height < 50) {
                items.push({
                    z: z,
                    text: text,
                    tag: el.tagName,
                    x: Math.round(r.x),
                    y: Math.round(r.y),
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
    print(f"\n  Model options (z > 50): {len(model_options)}", flush=True)
    for el in model_options[:20]:
        print(f"    z={el['z']} ({el['x']},{el['y']}) <{el['tag']}> '{el['text']}'", flush=True)

    page.keyboard.press("Escape")
    page.wait_for_timeout(500)

    # Scroll down in Txt2Img panel to see if Style is below
    page.mouse.move(200, 500)
    for _ in range(5):
        page.mouse.wheel(0, 200)
        page.wait_for_timeout(300)
    page.wait_for_timeout(1000)

    ss(page, "P33_07_txt2img_scrolled")

    items = map_panel(page, y_min=50)
    print(f"\n  Txt2Img after scroll ({len(items)}):", flush=True)
    for el in items:
        print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> '{el['text']}'", flush=True)

    ss(page, "P33_08_final")
    print(f"\n\n===== PHASE 33 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
