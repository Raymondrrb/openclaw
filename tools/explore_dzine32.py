"""Phase 32: Img2Img upload mechanism + Style explorer.

Goals:
1. Explore Img2Img panel in detail (upload mechanism, settings)
2. Test file input via CDP (page.set_input_files)
3. Explore available styles in Txt2Img
4. Test the "Start from an image" mechanism from workspace
5. Explore community styles page
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
    #  PART 1: IMG2IMG PANEL
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 1: IMG2IMG PANEL", flush=True)
    print("=" * 60, flush=True)

    page.mouse.click(40, 252)  # Img2Img sidebar
    page.wait_for_timeout(2000)
    close_dialogs(page)

    ss(page, "P32_01_img2img_panel")

    # Map all elements
    img2img = page.evaluate("""() => {
        const items = [];
        for (const el of document.querySelectorAll('*')) {
            const r = el.getBoundingClientRect();
            const text = (el.innerText || '').trim();
            if (r.x > 60 && r.x < 400 && r.y > 50 && r.y < 900
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
    }""")

    print(f"\n  Img2Img panel ({len(img2img)}):", flush=True)
    for el in img2img[:35]:
        print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> '{el['text']}'", flush=True)

    # Check for file input elements
    file_inputs = page.evaluate("""() => {
        const inputs = [];
        for (const el of document.querySelectorAll('input[type="file"]')) {
            const r = el.getBoundingClientRect();
            inputs.push({
                accept: el.accept || '',
                hidden: el.hidden || r.width === 0,
                x: Math.round(r.x),
                y: Math.round(r.y),
            });
        }
        return inputs;
    }""")

    print(f"\n  File input elements: {len(file_inputs)}", flush=True)
    for fi in file_inputs:
        print(f"    accept='{fi['accept']}' hidden={fi['hidden']} ({fi['x']},{fi['y']})", flush=True)

    # Check for drag-and-drop areas
    drop_areas = page.evaluate("""() => {
        const areas = [];
        for (const el of document.querySelectorAll('*')) {
            const text = (el.innerText || '').trim();
            const r = el.getBoundingClientRect();
            if ((text.includes('drag') || text.includes('Drag') || text.includes('Pick')
                 || text.includes('upload') || text.includes('Upload')
                 || text.includes('drop') || text.includes('Drop'))
                && r.x > 60 && r.x < 400 && r.width > 50) {
                areas.push({
                    text: text.substring(0, 60),
                    tag: el.tagName,
                    x: Math.round(r.x),
                    y: Math.round(r.y),
                    w: Math.round(r.width),
                    h: Math.round(r.height),
                });
            }
        }
        const seen = new Set();
        return areas.filter(i => {
            const key = i.text + '|' + Math.round(i.y / 10);
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
        });
    }""")

    print(f"\n  Drag/upload areas: {len(drop_areas)}", flush=True)
    for da in drop_areas:
        print(f"    ({da['x']},{da['y']}) {da['w']}x{da['h']} <{da['tag']}> '{da['text']}'", flush=True)

    # ============================================================
    #  PART 2: TXT2IMG STYLE SELECTOR
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 2: TXT2IMG STYLE SELECTOR", flush=True)
    print("=" * 60, flush=True)

    page.mouse.click(40, 197)  # Txt2Img sidebar
    page.wait_for_timeout(2000)
    close_dialogs(page)

    # Click the Style area to open style selector
    style_btn = page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            const text = (el.innerText || '').trim();
            const r = el.getBoundingClientRect();
            if (text.includes('Style') && r.x > 60 && r.x < 200 && r.y > 300 && r.y < 420
                && r.width > 30) {
                el.click(); return {text: text, x: Math.round(r.x), y: Math.round(r.y)};
            }
        }
        return null;
    }""")
    print(f"\n  Style button: {style_btn}", flush=True)
    page.wait_for_timeout(1500)

    ss(page, "P32_02_style_selector")

    # Map visible style options
    styles = page.evaluate("""() => {
        const items = [];
        for (const el of document.querySelectorAll('*')) {
            const r = el.getBoundingClientRect();
            const text = (el.innerText || '').trim();
            if (r.x > 60 && r.x < 400 && r.y > 50 && r.y < 900
                && r.width > 15 && r.width < 350 && text
                && text.length > 2 && text.length < 60
                && !text.includes('\\n')
                && r.height > 8 && r.height < 60) {
                items.push({
                    text: text,
                    tag: el.tagName,
                    x: Math.round(r.x),
                    y: Math.round(r.y),
                    w: Math.round(r.width),
                    h: Math.round(r.height),
                    clickable: el.tagName === 'BUTTON' || el.style.cursor === 'pointer',
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

    print(f"\n  Style options ({len(styles)}):", flush=True)
    for el in styles[:30]:
        click = " [CLICK]" if el.get("clickable") else ""
        print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> '{el['text']}'{click}", flush=True)

    # ============================================================
    #  PART 3: UPLOAD SIDEBAR
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 3: UPLOAD SIDEBAR", flush=True)
    print("=" * 60, flush=True)

    page.mouse.click(40, 81)  # Upload sidebar
    page.wait_for_timeout(2000)
    close_dialogs(page)

    ss(page, "P32_03_upload_panel")

    # Map upload panel
    upload_panel = page.evaluate("""() => {
        const items = [];
        for (const el of document.querySelectorAll('*')) {
            const r = el.getBoundingClientRect();
            const text = (el.innerText || '').trim();
            if (r.x > 60 && r.x < 600 && r.y > 50 && r.y < 900
                && r.width > 15 && r.width < 500 && text
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
    }""")

    print(f"\n  Upload panel ({len(upload_panel)}):", flush=True)
    for el in upload_panel[:20]:
        print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> '{el['text']}'", flush=True)

    # Check for hidden file inputs
    all_file_inputs = page.evaluate("""() => {
        const inputs = [];
        for (const el of document.querySelectorAll('input')) {
            const type = el.type || '';
            inputs.push({
                type: type,
                accept: el.accept || '',
                name: el.name || '',
                id: el.id || '',
                hidden: el.hidden || el.style.display === 'none' || el.getBoundingClientRect().width === 0,
            });
        }
        return inputs;
    }""")

    print(f"\n  ALL input elements: {len(all_file_inputs)}", flush=True)
    for fi in all_file_inputs:
        print(f"    type={fi['type']} accept={fi['accept']} name={fi['name']} id={fi['id']} hidden={fi['hidden']}", flush=True)

    # ============================================================
    #  PART 4: ASSETS SIDEBAR
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 4: ASSETS SIDEBAR", flush=True)
    print("=" * 60, flush=True)

    page.mouse.click(40, 136)  # Assets sidebar
    page.wait_for_timeout(2000)
    close_dialogs(page)

    ss(page, "P32_04_assets_panel")

    assets_panel = page.evaluate("""() => {
        const items = [];
        for (const el of document.querySelectorAll('*')) {
            const r = el.getBoundingClientRect();
            const text = (el.innerText || '').trim();
            if (r.x > 60 && r.x < 600 && r.y > 50 && r.y < 900
                && r.width > 15 && r.width < 500 && text
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
    }""")

    print(f"\n  Assets panel ({len(assets_panel)}):", flush=True)
    for el in assets_panel[:20]:
        print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> '{el['text']}'", flush=True)

    # ============================================================
    #  PART 5: CC GENERATION MODE + STYLE OPTIONS
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 5: CC GENERATION MODE + STYLE", flush=True)
    print("=" * 60, flush=True)

    # Open CC
    page.mouse.click(40, 306)
    page.wait_for_timeout(1500)
    close_dialogs(page)

    # Click Generate Images
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

    # Map the CC panel to find Style, Generation Mode options
    cc_panel = page.evaluate("""() => {
        const items = [];
        for (const el of document.querySelectorAll('*')) {
            const r = el.getBoundingClientRect();
            const text = (el.innerText || '').trim();
            if (r.x > 60 && r.x < 400 && r.y > 200 && r.y < 900
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
    }""")

    print(f"\n  CC panel below textarea ({len(cc_panel)}):", flush=True)
    for el in cc_panel[:30]:
        print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> '{el['text']}'", flush=True)

    # Click the Style dropdown/button to see CC styles
    style_clicked = page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            const text = (el.innerText || '').trim();
            const r = el.getBoundingClientRect();
            if (text.includes('Style') && r.x > 60 && r.x < 200 && r.y > 500 && r.width > 30) {
                el.click(); return {text: text, y: Math.round(r.y)};
            }
        }
        return null;
    }""")
    print(f"\n  CC Style clicked: {style_clicked}", flush=True)
    page.wait_for_timeout(1500)

    ss(page, "P32_05_cc_style")

    # Map style dropdown
    cc_styles = page.evaluate("""() => {
        const items = [];
        for (const el of document.querySelectorAll('*')) {
            const r = el.getBoundingClientRect();
            const text = (el.innerText || '').trim();
            const style = window.getComputedStyle(el);
            const zIndex = parseInt(style.zIndex) || 0;
            if (zIndex > 50 && text && text.length > 2 && text.length < 60
                && !text.includes('\\n') && r.width > 20 && r.height > 10) {
                items.push({
                    text: text,
                    tag: el.tagName,
                    x: Math.round(r.x),
                    y: Math.round(r.y),
                    z: zIndex,
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

    print(f"\n  CC Style options (z > 50): {len(cc_styles)}", flush=True)
    for el in cc_styles[:20]:
        print(f"    z={el['z']} ({el['x']},{el['y']}) <{el['tag']}> '{el['text']}'", flush=True)

    # Close any dropdown
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)

    ss(page, "P32_06_final")
    print(f"\n\n===== PHASE 32 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
