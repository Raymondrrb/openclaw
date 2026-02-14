"""Phase 29: Lightbox download, Export with layer, Expression Edit full mapping.

Goals:
1. Open lightbox by clicking canvas image, map action buttons
2. Click download button in lightbox
3. Select layer via Layers panel, test Export from top bar
4. Full Expression Edit panel mapping (Mouth + Head Angles)
5. Expression Edit Template mode
"""

import json
import os
import sys
import time
import urllib.request
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
    #  STEP 1: Place image and open lightbox
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  STEP 1: LIGHTBOX FROM CANVAS IMAGE", flush=True)
    print("=" * 60, flush=True)

    # Switch to Results
    page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            if ((el.innerText || '').trim() === 'Results' && el.getBoundingClientRect().x > 1050) {
                el.click(); return true;
            }
        }
        return false;
    }""")
    page.wait_for_timeout(1000)

    # Click first result to place on canvas
    placed = page.evaluate("""() => {
        for (const img of document.querySelectorAll('img')) {
            const src = img.src || '';
            const r = img.getBoundingClientRect();
            if (src.includes('static.dzine.ai/stylar_product/p/') && r.x > 1050 && r.width > 100) {
                img.click(); return true;
            }
        }
        return false;
    }""")
    print(f"  Placed: {placed}", flush=True)
    page.wait_for_timeout(2000)
    close_dialogs(page)

    # Double-click on canvas image to open lightbox
    print("  Double-clicking canvas image...", flush=True)
    page.mouse.dblclick(600, 400)
    page.wait_for_timeout(2000)

    ss(page, "P29_01_dblclick_canvas")

    # Check if lightbox opened (look for high z-index overlay)
    lightbox = page.evaluate("""() => {
        const items = [];
        for (const el of document.querySelectorAll('*')) {
            const r = el.getBoundingClientRect();
            const style = window.getComputedStyle(el);
            const zIndex = parseInt(style.zIndex) || 0;
            const text = (el.innerText || '').trim();
            if (zIndex > 100 && r.width > 30 && r.height > 20
                && text && text.length < 60 && !text.includes('\\n')) {
                items.push({
                    text: text, tag: el.tagName,
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    z: zIndex,
                });
            }
        }
        const seen = new Set();
        return items.filter(i => {
            const key = i.text + '|' + Math.round(i.y / 5);
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
        }).sort((a, b) => a.y - b.y);
    }""")

    print(f"\n  Lightbox elements (z > 100): {len(lightbox)}", flush=True)
    for el in lightbox[:15]:
        print(f"    z={el['z']} ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> '{el['text']}'", flush=True)

    # Close lightbox if it opened
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)

    # Try single click on canvas image center
    print("\n  Single-clicking canvas image...", flush=True)
    page.mouse.click(600, 400)
    page.wait_for_timeout(2000)

    ss(page, "P29_02_single_click_canvas")

    # Map ALL clickable elements that appeared (SVG icons = action buttons)
    action_btns = page.evaluate("""() => {
        const items = [];
        for (const el of document.querySelectorAll('button, svg, [role="button"]')) {
            const r = el.getBoundingClientRect();
            if (r.width > 20 && r.width < 80 && r.height > 20 && r.height < 80
                && r.y > 300 && r.y < 500) {
                const title = el.getAttribute('title') || el.getAttribute('aria-label') || '';
                const text = (el.innerText || '').trim();
                items.push({
                    text: text || title || el.tagName,
                    tag: el.tagName,
                    x: Math.round(r.x + r.width/2),
                    y: Math.round(r.y + r.height/2),
                    w: Math.round(r.width),
                    h: Math.round(r.height),
                });
            }
        }
        return items;
    }""")

    print(f"\n  Action buttons near center: {len(action_btns)}", flush=True)
    for btn in action_btns:
        print(f"    ({btn['x']},{btn['y']}) {btn['w']}x{btn['h']} <{btn['tag']}> '{btn['text']}'", flush=True)

    # ============================================================
    #  STEP 2: TRY CLICKING RESULT IMAGE DIRECTLY (not via canvas)
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  STEP 2: CLICK RESULT IMAGE DIRECTLY", flush=True)
    print("=" * 60, flush=True)

    # Click on a Txt2Img result image (scroll down in results first)
    page.evaluate("""() => {
        const panels = document.querySelectorAll('div');
        for (const p of panels) {
            const r = p.getBoundingClientRect();
            if (r.x > 1050 && r.width > 200 && p.scrollHeight > p.clientHeight) {
                p.scrollTop += 400;
                return true;
            }
        }
        return false;
    }""")
    page.wait_for_timeout(500)

    # Find a Txt2Img result image (typically larger, 231px wide)
    txt2img_result = page.evaluate("""() => {
        for (const img of document.querySelectorAll('img')) {
            const src = img.src || '';
            const r = img.getBoundingClientRect();
            if (src.includes('gemini2text2image') && r.x > 1050 && r.width > 200 && r.y > 50 && r.y < 900) {
                return {
                    src: src.substring(0, 100),
                    cx: Math.round(r.x + r.width/2),
                    cy: Math.round(r.y + r.height/2),
                };
            }
        }
        return null;
    }""")

    if txt2img_result:
        print(f"  Clicking Txt2Img result at ({txt2img_result['cx']},{txt2img_result['cy']})", flush=True)
        page.mouse.click(txt2img_result['cx'], txt2img_result['cy'])
        page.wait_for_timeout(2000)

        ss(page, "P29_03_result_clicked")

        # Check if lightbox opened
        lightbox2 = page.evaluate("""() => {
            const items = [];
            for (const el of document.querySelectorAll('*')) {
                const r = el.getBoundingClientRect();
                const style = window.getComputedStyle(el);
                const zIndex = parseInt(style.zIndex) || 0;
                if (zIndex > 100 && r.width > 30 && r.height > 20) {
                    const text = (el.innerText || '').trim();
                    const title = el.getAttribute('title') || el.getAttribute('aria-label') || '';
                    if ((text && text.length < 60) || title) {
                        items.push({
                            text: text || title,
                            tag: el.tagName,
                            x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height),
                            z: zIndex,
                        });
                    }
                }
            }
            const seen = new Set();
            return items.filter(i => {
                const key = i.text + '|' + Math.round(i.y / 5);
                if (seen.has(key)) return false;
                seen.add(key);
                return true;
            }).sort((a, b) => a.y - b.y);
        }""")

        print(f"\n  Lightbox elements: {len(lightbox2)}", flush=True)
        for el in lightbox2[:15]:
            print(f"    z={el['z']} ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> '{el['text']}'", flush=True)

        # Also look for circular/icon buttons at bottom of lightbox
        bottom_btns = page.evaluate("""() => {
            const items = [];
            for (const el of document.querySelectorAll('*')) {
                const r = el.getBoundingClientRect();
                if (r.y > 350 && r.y < 420 && r.x > 250 && r.x < 600
                    && r.width > 20 && r.width < 60 && r.height > 20 && r.height < 60) {
                    const style = window.getComputedStyle(el);
                    const cursor = style.cursor;
                    if (cursor === 'pointer' || el.tagName === 'BUTTON' || el.tagName === 'SVG') {
                        items.push({
                            tag: el.tagName,
                            title: el.getAttribute('title') || '',
                            ariaLabel: el.getAttribute('aria-label') || '',
                            x: Math.round(r.x + r.width/2),
                            y: Math.round(r.y + r.height/2),
                            w: Math.round(r.width),
                            cursor: cursor,
                        });
                    }
                }
            }
            return items;
        }""")

        print(f"\n  Bottom action buttons: {len(bottom_btns)}", flush=True)
        for btn in bottom_btns:
            print(f"    ({btn['x']},{btn['y']}) w={btn['w']} <{btn['tag']}> title='{btn['title']}' aria='{btn['ariaLabel']}' cursor={btn['cursor']}", flush=True)

        page.keyboard.press("Escape")
        page.wait_for_timeout(500)
    else:
        print("  No Txt2Img result found", flush=True)

    # ============================================================
    #  STEP 3: SELECT LAYER VIA LAYERS PANEL
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  STEP 3: SELECT LAYER VIA LAYERS PANEL", flush=True)
    print("=" * 60, flush=True)

    # Switch to Layers tab
    page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            if ((el.innerText || '').trim() === 'Layers' &&
                el.getBoundingClientRect().x > 1200 && el.getBoundingClientRect().y < 80) {
                el.click(); return true;
            }
        }
        return false;
    }""")
    page.wait_for_timeout(1000)

    ss(page, "P29_04_layers_tab")

    # Find and click "Layer 1" or "Layer 2" button
    layer_btn = page.evaluate("""() => {
        for (const btn of document.querySelectorAll('button')) {
            const text = (btn.innerText || '').trim();
            const r = btn.getBoundingClientRect();
            if ((text === 'Layer 1' || text === 'Layer 2') && r.x > 1050 && r.width > 200) {
                btn.click();
                return {text: text, x: Math.round(r.x), y: Math.round(r.y)};
            }
        }
        return null;
    }""")
    print(f"\n  Layer clicked: {layer_btn}", flush=True)
    page.wait_for_timeout(1000)

    # Check top bar for "Please select a layer" message
    has_msg = page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            const text = (el.innerText || '').trim();
            if (text === 'Please select a layer' && el.getBoundingClientRect().y < 100) {
                return true;
            }
        }
        return false;
    }""")
    print(f"  Still showing 'Please select': {has_msg}", flush=True)

    ss(page, "P29_05_layer_selected")

    # Check if top bar now shows tools instead of "Please select"
    topbar_tools = page.evaluate("""() => {
        const items = [];
        for (const el of document.querySelectorAll('button')) {
            const r = el.getBoundingClientRect();
            const text = (el.innerText || '').trim();
            if (r.y > 60 && r.y < 100 && r.x > 200 && r.x < 800 && text && text.length < 30) {
                items.push({text: text, x: Math.round(r.x), y: Math.round(r.y)});
            }
        }
        return items.sort((a, b) => a.x - b.x);
    }""")
    print(f"\n  Top bar tools: {len(topbar_tools)}", flush=True)
    for t in topbar_tools:
        print(f"    ({t['x']},{t['y']}) '{t['text']}'", flush=True)

    # ============================================================
    #  STEP 4: EXPORT WITH SELECTED LAYER
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  STEP 4: EXPORT WITH SELECTED LAYER", flush=True)
    print("=" * 60, flush=True)

    # Click Export
    export = page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            const text = (el.innerText || '').trim();
            const r = el.getBoundingClientRect();
            if (text === 'Export' && r.y < 50 && r.x > 1300) {
                el.click(); return true;
            }
        }
        return false;
    }""")
    print(f"  Export clicked: {export}", flush=True)
    page.wait_for_timeout(2000)

    ss(page, "P29_06_export_modal")

    # Map everything on screen with focus on high z-index
    all_visible = page.evaluate("""() => {
        const items = [];
        for (const el of document.querySelectorAll('*')) {
            const r = el.getBoundingClientRect();
            const style = window.getComputedStyle(el);
            const zIndex = parseInt(style.zIndex) || 0;
            const text = (el.innerText || '').trim();
            if (r.width > 0 && r.height > 0 && r.x >= 0 && r.y >= 0
                && text && text.length > 0 && text.length < 60
                && !text.includes('\\n')
                && (zIndex > 10 || el.tagName === 'BUTTON' || el.tagName === 'A')) {
                items.push({
                    text: text, tag: el.tagName,
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    z: zIndex,
                    cursor: style.cursor,
                });
            }
        }
        // Deduplicate
        const seen = new Set();
        return items.filter(i => {
            const key = i.text + '|' + Math.round(i.y / 5) + '|' + Math.round(i.x / 5);
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
        }).sort((a, b) => b.z - a.z || a.y - b.y).slice(0, 40);
    }""")

    print(f"\n  Visible elements ({len(all_visible)}):", flush=True)
    for el in all_visible:
        cursor = f" cursor={el['cursor']}" if el['cursor'] == 'pointer' else ""
        print(f"    z={el['z']} ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> '{el['text']}'{cursor}", flush=True)

    # Check for any download-related elements
    download = page.evaluate("""() => {
        const items = [];
        for (const el of document.querySelectorAll('a[download], a[href*="download"], button')) {
            const r = el.getBoundingClientRect();
            const text = (el.innerText || '').trim();
            const href = el.getAttribute('href') || '';
            const dl = el.getAttribute('download') || '';
            if (r.width > 0) {
                items.push({
                    text: text, tag: el.tagName,
                    href: href.substring(0, 80),
                    download: dl,
                    x: Math.round(r.x), y: Math.round(r.y),
                });
            }
        }
        return items.filter(i => i.download || i.href.includes('download'));
    }""")

    print(f"\n  Download links: {len(download)}", flush=True)
    for dl in download:
        print(f"    <{dl['tag']}> href='{dl['href']}' download='{dl['download']}'", flush=True)

    page.keyboard.press("Escape")
    page.wait_for_timeout(500)

    # ============================================================
    #  STEP 5: EXPRESSION EDIT - TEMPLATE MODE (via sidebar icon)
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  STEP 5: EXPRESSION EDIT TEMPLATE", flush=True)
    print("=" * 60, flush=True)

    # Open Expression Edit via result action button
    page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            if ((el.innerText || '').trim() === 'Results' && el.getBoundingClientRect().x > 1050) {
                el.click(); return true;
            }
        }
        return false;
    }""")
    page.wait_for_timeout(500)

    # Scroll results to top
    page.evaluate("""() => {
        const panels = document.querySelectorAll('div');
        for (const p of panels) {
            const r = p.getBoundingClientRect();
            if (r.x > 1050 && r.width > 200 && p.scrollHeight > p.clientHeight) {
                p.scrollTop = 0; return true;
            }
        }
        return false;
    }""")
    page.wait_for_timeout(500)

    # Click "1" next to Expression Edit
    page.evaluate("""() => {
        for (const div of document.querySelectorAll('div')) {
            const text = (div.innerText || '').trim();
            const r = div.getBoundingClientRect();
            if (text === 'Expression Edit' && r.x > 1100 && r.y > 450 && r.y < 500) {
                for (const btn of document.querySelectorAll('button')) {
                    const bt = (btn.innerText || '').trim();
                    const br = btn.getBoundingClientRect();
                    if (bt === '1' && br.x > 1250 && Math.abs(br.y - r.y) < 20) {
                        btn.click(); return true;
                    }
                }
            }
        }
        return false;
    }""")
    page.wait_for_timeout(2000)
    close_dialogs(page)

    # Click Template
    page.evaluate("""() => {
        for (const btn of document.querySelectorAll('button')) {
            const text = (btn.innerText || '').trim();
            const r = btn.getBoundingClientRect();
            if (text === 'Template' && r.x > 180 && r.y > 300 && r.y < 360) {
                btn.click(); return true;
            }
        }
        return false;
    }""")
    page.wait_for_timeout(1500)

    ss(page, "P29_07_expression_template")

    # Map template section (it should show preset expressions)
    template_els = page.evaluate("""() => {
        const items = [];
        for (const el of document.querySelectorAll('*')) {
            const r = el.getBoundingClientRect();
            const text = (el.innerText || '').trim();
            if (r.x > 60 && r.x < 400 && r.y > 340 && r.y < 900
                && r.width > 15 && r.width < 350 && text
                && text.length > 0 && text.length < 80 && !text.includes('\\n')
                && r.height > 8 && r.height < 60) {
                items.push({
                    text: text, tag: el.tagName,
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
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

    print(f"\n  Template elements ({len(template_els)}):", flush=True)
    for el in template_els[:25]:
        print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> '{el['text']}'", flush=True)

    # Check for template images/thumbnails
    template_imgs = page.evaluate("""() => {
        const imgs = [];
        for (const img of document.querySelectorAll('img')) {
            const r = img.getBoundingClientRect();
            if (r.x > 60 && r.x < 400 && r.y > 340 && r.width > 30 && r.width < 200) {
                imgs.push({
                    src: img.src.substring(0, 80),
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    alt: img.alt || '',
                });
            }
        }
        return imgs;
    }""")

    print(f"\n  Template images: {len(template_imgs)}", flush=True)
    for img in template_imgs:
        print(f"    ({img['x']},{img['y']}) {img['w']}x{img['h']} alt='{img['alt']}' {img['src']}", flush=True)

    ss(page, "P29_08_final")
    print(f"\n\n===== PHASE 29 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
