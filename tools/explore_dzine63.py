"""Phase 63: Validate CC panel activation flow, test Image Editor sub-tools, Enhance & Upscale workflow.

From P57-62:
- CC menu has 4 workflow cards, fully mapped
- Character Sheet, 360° Video, Motion Control all documented
- CC Style toggle inaccessible at 1440x900 (clipped, documented as limitation)
- CC panel activation needs a robust flow (dblclick → Generate Images → Ray)

Goals:
1. Test robust CC panel activation flow (verify _activate_cc_panel works)
2. Explore Image Editor sub-tool: Local Edit (how does it work?)
3. Explore Image Editor sub-tool: AI Eraser (what prompt/mask?)
4. Test Enhance & Upscale workflow (select layer → enhance → result)
5. Verify Img2Img panel activation works correctly
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


def dump_region(page, label, x_min, x_max, y_min, y_max, limit=50):
    items = page.evaluate(f"""() => {{
        var items = [];
        for (const el of document.querySelectorAll('*')) {{
            var r = el.getBoundingClientRect();
            if (r.x >= {x_min} && r.x <= {x_max} && r.y >= {y_min} && r.y <= {y_max}
                && r.width > 8 && r.height > 5 && r.width < 400
                && !['path','line','circle','g','svg','defs','rect','polygon','clippath','HTML','BODY','HEAD','SCRIPT','STYLE'].includes(el.tagName.toLowerCase())) {{
                var text = (el.innerText || '').trim();
                if (text.length > 0 && text.length < 60) {{
                    items.push({{
                        tag: el.tagName, x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        text: text.substring(0, 45),
                        classes: (el.className || '').toString().substring(0, 30),
                    }});
                }}
            }}
        }}
        var seen = new Set();
        return items.filter(function(i) {{
            var key = i.text.substring(0,15) + '|' + i.x + '|' + i.y;
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
        }}).sort(function(a,b) {{ return a.y - b.y; }});
    }}""")
    print(f"\n  {label} ({len(items)} elements):", flush=True)
    for el in items[:limit]:
        print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> c='{el['classes'][:22]}' '{el['text'][:40]}'", flush=True)
    return items


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
    #  PART 1: CC PANEL ROBUST ACTIVATION
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 1: CC PANEL ACTIVATION (ROBUST)", flush=True)
    print("=" * 60, flush=True)

    # Step A: Double-click Character sidebar
    page.mouse.dblclick(40, 306)
    page.wait_for_timeout(2500)
    close_dialogs(page)

    # Step B: Verify we see the Character menu
    menu = page.evaluate("""() => {
        var items = [];
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (r.x > 60 && r.x < 200 && r.y > 70 && r.y < 400
                && r.width > 80 && r.height > 15 && r.height < 50
                && text.length > 5 && text.length < 40) {
                items.push({text: text, x: Math.round(r.x), y: Math.round(r.y),
                            h: Math.round(r.height), tag: el.tagName});
            }
        }
        var seen = new Set();
        return items.filter(function(i) {
            if (seen.has(i.text)) return false;
            seen.add(i.text);
            return true;
        }).sort(function(a,b) { return a.y - b.y; });
    }""")
    print(f"  Character menu items ({len(menu)}):", flush=True)
    for m in menu:
        print(f"    ({m['x']},{m['y']}) h={m['h']} <{m['tag']}> '{m['text']}'", flush=True)

    ss(page, "P63_01_cc_menu")

    # Step C: Click "Generate Images" text specifically
    gen_img = None
    for m in menu:
        if 'Generate Images' in m['text']:
            gen_img = m
            break

    if gen_img:
        print(f"\n  Clicking 'Generate Images' at ({gen_img['x']},{gen_img['y']})...", flush=True)
        page.mouse.click(gen_img['x'] + 50, gen_img['y'] + gen_img['h']//2)
        page.wait_for_timeout(2000)
        close_dialogs(page)
    else:
        print("  'Generate Images' not found in menu!", flush=True)
        # Try clicking the expected position
        page.mouse.click(140, 140)
        page.wait_for_timeout(2000)
        close_dialogs(page)

    ss(page, "P63_02_after_gen_images_click")

    # Step D: Check if Ray character selection appeared or if we're in the CC panel
    header = page.evaluate("""() => {
        for (const el of document.querySelectorAll('.gen-config-header')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (r.x > 0 && r.width > 50) return text.substring(0, 40);
        }
        return null;
    }""")
    print(f"  Header: {header}", flush=True)

    # Check for Ray button
    ray = page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            if (text === 'Ray' && el.tagName === 'BUTTON') {
                var r = el.getBoundingClientRect();
                return {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width)};
            }
        }
        return null;
    }""")
    print(f"  Ray button: {ray}", flush=True)

    if ray:
        page.evaluate("""() => {
            for (const el of document.querySelectorAll('*')) {
                if ((el.innerText || '').trim() === 'Ray' && el.tagName === 'BUTTON') {
                    el.click(); return true;
                }
            }
            return false;
        }""")
        page.wait_for_timeout(2000)
        close_dialogs(page)
        print("  Ray selected!", flush=True)

    # Step E: Verify CC panel is active
    cc_active = page.evaluate("""() => {
        for (const el of document.querySelectorAll('.gen-config-header')) {
            if ((el.innerText || '').includes('Consistent Character')) return true;
        }
        return false;
    }""")
    print(f"\n  CC panel active: {cc_active}", flush=True)
    ss(page, "P63_03_cc_active")

    if cc_active:
        # Dump the visible CC panel
        dump_region(page, "CC active panel", 60, 370, 40, 900)

    # ============================================================
    #  PART 2: IMG2IMG PANEL ACTIVATION
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 2: IMG2IMG PANEL ACTIVATION", flush=True)
    print("=" * 60, flush=True)

    # Toggle from CC to Img2Img
    page.mouse.click(40, 306)  # Character first
    page.wait_for_timeout(300)
    page.mouse.click(40, 252)  # Img2Img
    page.wait_for_timeout(1500)
    close_dialogs(page)

    img2img_active = page.evaluate("""() => {
        for (const el of document.querySelectorAll('.gen-config-header')) {
            if ((el.innerText || '').includes('Image-to-Image')) return true;
        }
        return false;
    }""")
    print(f"  Img2Img panel active: {img2img_active}", flush=True)

    if img2img_active:
        dump_region(page, "Img2Img active panel", 60, 370, 40, 900)
    ss(page, "P63_04_img2img")

    # ============================================================
    #  PART 3: LOCAL EDIT SUB-TOOL
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 3: LOCAL EDIT SUB-TOOL", flush=True)
    print("=" * 60, flush=True)

    # Switch to Image Editor
    page.mouse.click(40, 252)  # Img2Img first
    page.wait_for_timeout(300)
    page.mouse.click(40, 698)  # Image Editor
    page.wait_for_timeout(1500)
    close_dialogs(page)

    # Click Local Edit
    local_edit = page.evaluate("""() => {
        for (const btn of document.querySelectorAll('button')) {
            var text = (btn.innerText || '').trim();
            var r = btn.getBoundingClientRect();
            if (text === 'Local Edit' && r.x > 60 && r.x < 370 && r.y > 100 && r.y < 300) {
                btn.click();
                return {x: Math.round(r.x), y: Math.round(r.y)};
            }
        }
        return null;
    }""")
    print(f"  Clicked Local Edit: {local_edit}", flush=True)
    page.wait_for_timeout(2000)
    close_dialogs(page)

    if local_edit:
        ss(page, "P63_05_local_edit")
        dump_region(page, "Local Edit panel", 60, 370, 40, 900)

        # Go back
        page.evaluate("""() => {
            for (const el of document.querySelectorAll('*')) {
                var r = el.getBoundingClientRect();
                if (r.x > 80 && r.x < 100 && r.y > 50 && r.y < 75
                    && r.width > 10 && r.width < 40) {
                    el.click(); return true;
                }
            }
            return false;
        }""")
        page.wait_for_timeout(1000)

    # ============================================================
    #  PART 4: AI ERASER SUB-TOOL
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 4: AI ERASER SUB-TOOL", flush=True)
    print("=" * 60, flush=True)

    # Navigate to Image Editor
    page.mouse.click(40, 252)  # Img2Img first
    page.wait_for_timeout(300)
    page.mouse.click(40, 698)  # Image Editor
    page.wait_for_timeout(1500)
    close_dialogs(page)

    # Click AI Eraser
    ai_eraser = page.evaluate("""() => {
        for (const btn of document.querySelectorAll('button')) {
            var text = (btn.innerText || '').trim();
            var r = btn.getBoundingClientRect();
            if (text === 'AI Eraser' && r.x > 60 && r.x < 370 && r.y > 200 && r.y < 400) {
                btn.click();
                return {x: Math.round(r.x), y: Math.round(r.y)};
            }
        }
        return null;
    }""")
    print(f"  Clicked AI Eraser: {ai_eraser}", flush=True)
    page.wait_for_timeout(2000)
    close_dialogs(page)

    if ai_eraser:
        ss(page, "P63_06_ai_eraser")
        dump_region(page, "AI Eraser panel", 60, 400, 40, 900)

        # Go back
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)
        # Try Exit button
        page.evaluate("""() => {
            for (const btn of document.querySelectorAll('button')) {
                var text = (btn.innerText || '').trim();
                if (text === 'Exit') { btn.click(); return true; }
            }
            return false;
        }""")
        page.wait_for_timeout(1000)

    # ============================================================
    #  PART 5: ENHANCE & UPSCALE WORKFLOW
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 5: ENHANCE & UPSCALE", flush=True)
    print("=" * 60, flush=True)

    # First place an image on canvas by clicking a result
    placed = page.evaluate("""() => {
        // Click Results tab
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text === 'Results' && r.x > 1050 && r.y < 60) {
                el.click(); return 'results_tab';
            }
        }
        return null;
    }""")
    print(f"  Clicked Results tab: {placed}", flush=True)
    page.wait_for_timeout(1000)

    # Click first result image to place on canvas
    placed_img = page.evaluate("""() => {
        for (const img of document.querySelectorAll('img')) {
            var src = img.src || '';
            if (src.includes('static.dzine.ai/stylar_product')) {
                var r = img.getBoundingClientRect();
                if (r.width > 50 && r.height > 30 && r.x > 1060) {
                    img.click();
                    return {src: src.substring(src.length-40), x: Math.round(r.x), y: Math.round(r.y)};
                }
            }
        }
        return null;
    }""")
    print(f"  Placed image on canvas: {placed_img}", flush=True)
    page.wait_for_timeout(2000)

    # Now click Layers tab and select the top layer
    page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text === 'Layers' && r.x > 1200 && r.y < 60) {
                el.click(); return true;
            }
        }
        return false;
    }""")
    page.wait_for_timeout(1000)

    # Click the topmost layer
    page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text.startsWith('Layer') && r.x > 1060 && r.width > 200
                && r.height > 30 && r.y > 60 && r.y < 300) {
                el.click(); return true;
            }
        }
        return false;
    }""")
    page.wait_for_timeout(1000)

    # Switch to Enhance & Upscale
    page.mouse.click(40, 252)  # Img2Img first
    page.wait_for_timeout(300)
    page.mouse.click(40, 627)  # Enhance & Upscale
    page.wait_for_timeout(1500)
    close_dialogs(page)

    enhance_active = page.evaluate("""() => {
        for (const el of document.querySelectorAll('.gen-config-header')) {
            if ((el.innerText || '').includes('Enhance')) return true;
        }
        return false;
    }""")
    print(f"  Enhance panel active: {enhance_active}", flush=True)

    if enhance_active:
        ss(page, "P63_07_enhance")
        dump_region(page, "Enhance & Upscale panel", 60, 370, 40, 900)

    ss(page, "P63_08_final")

    print(f"\n\n===== PHASE 63 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
