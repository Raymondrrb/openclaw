"""Phase 28: Export with selected layer, Expression Edit Template, Enhance test.

Goals:
1. Click canvas image to SELECT the layer, then try Export again
2. Open Expression Edit "Mouth Adjustments" section
3. Try Expression Edit "Template" mode
4. Try Enhance & Upscale with selected layer (just check panel, don't waste credits)
5. Examine both CC variant images (URLs for 1_output vs 2_output)
6. Try downloading the 2_output image to verify both variants are full-res
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
    #  STEP 1: Place image on canvas and SELECT it
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  STEP 1: PLACE + SELECT LAYER", flush=True)
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

    # Click first result image to place on canvas
    page.evaluate("""() => {
        for (const img of document.querySelectorAll('img')) {
            const src = img.src || '';
            const r = img.getBoundingClientRect();
            if (src.includes('static.dzine.ai/stylar_product/p/') && r.x > 1050 && r.width > 100) {
                img.click(); return true;
            }
        }
        return false;
    }""")
    page.wait_for_timeout(2000)
    close_dialogs(page)

    # Now click ON the canvas image to SELECT the layer
    # The canvas area is roughly center of viewport (x: 200-1100, y: 100-850)
    page.mouse.click(600, 400)
    page.wait_for_timeout(1000)

    # Check if layer is now selected (look for selection handles / blue border)
    layer_selected = page.evaluate("""() => {
        // Check Layers panel for selected state
        const layers = [];
        for (const el of document.querySelectorAll('*')) {
            const text = (el.innerText || '').trim();
            const r = el.getBoundingClientRect();
            if (r.x > 1050 && text.includes('Layer') && r.width > 50) {
                layers.push({text: text, x: Math.round(r.x), y: Math.round(r.y)});
            }
        }
        // Also check if "Please select a layer" is gone
        for (const el of document.querySelectorAll('*')) {
            if ((el.innerText || '').includes('Please select a layer')) {
                return {selected: false, msg: 'still shows please select', layers: layers};
            }
        }
        return {selected: true, layers: layers};
    }""")
    print(f"  Layer status: {json.dumps(layer_selected)}", flush=True)

    ss(page, "P28_01_layer_selected")

    # ============================================================
    #  STEP 2: EXPORT WITH SELECTED LAYER
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  STEP 2: EXPORT WITH LAYER", flush=True)
    print("=" * 60, flush=True)

    # Click Export button
    page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            const text = (el.innerText || '').trim();
            const r = el.getBoundingClientRect();
            if (text === 'Export' && r.y < 50) {
                el.click(); return true;
            }
        }
        return false;
    }""")
    page.wait_for_timeout(2000)

    ss(page, "P28_02_export_after_select")

    # Map ALL new elements that appeared (check for high z-index overlays)
    export_ui = page.evaluate("""() => {
        const items = [];
        for (const el of document.querySelectorAll('*')) {
            const r = el.getBoundingClientRect();
            const text = (el.innerText || '').trim();
            const style = window.getComputedStyle(el);
            const zIndex = parseInt(style.zIndex) || 0;
            if (text && text.length > 0 && text.length < 80
                && !text.includes('\\n')
                && r.width > 15 && r.height > 8
                && zIndex > 50) {
                items.push({
                    text: text,
                    tag: el.tagName,
                    x: Math.round(r.x),
                    y: Math.round(r.y),
                    w: Math.round(r.width),
                    h: Math.round(r.height),
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

    print(f"\n  Export UI (z > 50): ({len(export_ui)}):", flush=True)
    for el in export_ui[:30]:
        print(f"    z={el['z']} ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> '{el['text']}'", flush=True)

    # Also check for any popup/modal that just appeared at any z
    modal = page.evaluate("""() => {
        const items = [];
        // Look for elements that look like a modal/popup
        for (const el of document.querySelectorAll('div, section, aside')) {
            const r = el.getBoundingClientRect();
            const style = window.getComputedStyle(el);
            const bg = style.backgroundColor;
            // Modals/popups tend to be centered, have background
            if (r.width > 200 && r.width < 800 && r.height > 100 && r.height < 600
                && r.x > 200 && r.x < 1000 && r.y > 100 && r.y < 700
                && bg && bg !== 'rgba(0, 0, 0, 0)' && bg !== 'transparent') {
                const children = [];
                for (const child of el.querySelectorAll('button, input, select, a')) {
                    const ct = (child.innerText || child.value || '').trim();
                    if (ct) children.push(ct);
                }
                if (children.length > 0) {
                    items.push({
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        bg: bg,
                        children: children.slice(0, 15),
                    });
                }
            }
        }
        return items;
    }""")

    print(f"\n  Modal/popup elements: ({len(modal)}):", flush=True)
    for m in modal[:5]:
        print(f"    ({m['x']},{m['y']}) {m['w']}x{m['h']} bg={m['bg']}", flush=True)
        print(f"    children: {m['children']}", flush=True)

    # Close any dialog
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)

    # ============================================================
    #  STEP 3: EXPRESSION EDIT TEMPLATE MODE
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  STEP 3: EXPRESSION EDIT - TEMPLATE MODE", flush=True)
    print("=" * 60, flush=True)

    # Open Expression Edit via results action button
    page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            if ((el.innerText || '').trim() === 'Results' && el.getBoundingClientRect().x > 1050) {
                el.click(); return true;
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

    # Click "Template" button
    template_clicked = page.evaluate("""() => {
        for (const btn of document.querySelectorAll('button')) {
            const text = (btn.innerText || '').trim();
            const r = btn.getBoundingClientRect();
            if (text === 'Template' && r.x > 180 && r.x < 260 && r.y > 310 && r.y < 350) {
                btn.click(); return true;
            }
        }
        return false;
    }""")
    print(f"\n  Template clicked: {template_clicked}", flush=True)
    page.wait_for_timeout(1500)

    ss(page, "P28_03_expression_template")

    # Map template options
    templates = page.evaluate("""() => {
        const items = [];
        for (const el of document.querySelectorAll('*')) {
            const r = el.getBoundingClientRect();
            const text = (el.innerText || '').trim();
            if (r.x > 60 && r.x < 400 && r.y > 350 && r.y < 900
                && r.width > 15 && r.width < 350 && text
                && text.length > 0 && text.length < 60 && !text.includes('\\n')) {
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

    print(f"\n  Template options ({len(templates)}):", flush=True)
    for el in templates[:25]:
        print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> '{el['text']}'", flush=True)

    # Also look for Mouth Adjustments by clicking Custom first, then scrolling
    page.evaluate("""() => {
        for (const btn of document.querySelectorAll('button')) {
            if ((btn.innerText || '').trim() === 'Custom' && btn.getBoundingClientRect().y > 310) {
                btn.click(); return true;
            }
        }
        return false;
    }""")
    page.wait_for_timeout(500)

    # Click "Mouth Adjustments" to expand it
    mouth = page.evaluate("""() => {
        for (const btn of document.querySelectorAll('button')) {
            const text = (btn.innerText || '').trim();
            if (text.includes('Mouth Adjustments')) {
                btn.click(); return true;
            }
        }
        return false;
    }""")
    print(f"\n  Mouth Adjustments clicked: {mouth}", flush=True)
    page.wait_for_timeout(1000)

    # Scroll the panel down to see mouth controls
    page.evaluate("""() => {
        const panels = document.querySelectorAll('div');
        for (const p of panels) {
            const r = p.getBoundingClientRect();
            if (r.x > 60 && r.x < 100 && r.width > 200 && r.width < 350
                && p.scrollHeight > p.clientHeight) {
                p.scrollTop += 300;
                return true;
            }
        }
        return false;
    }""")
    page.wait_for_timeout(500)

    ss(page, "P28_04_mouth_adjustments")

    # Map mouth controls
    mouth_panel = page.evaluate("""() => {
        const items = [];
        for (const el of document.querySelectorAll('*')) {
            const r = el.getBoundingClientRect();
            const text = (el.innerText || '').trim();
            if (r.x > 60 && r.x < 400 && r.y > 300 && r.y < 900
                && r.width > 15 && r.width < 350 && text
                && text.length > 0 && text.length < 60 && !text.includes('\\n')) {
                items.push({
                    text: text,
                    tag: el.tagName,
                    x: Math.round(r.x),
                    y: Math.round(r.y),
                    w: Math.round(r.width),
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

    print(f"\n  Mouth panel ({len(mouth_panel)}):", flush=True)
    for el in mouth_panel[:25]:
        print(f"    ({el['x']},{el['y']}) w={el['w']} <{el['tag']}> '{el['text']}'", flush=True)

    # ============================================================
    #  STEP 4: BOTH CC VARIANT IMAGES (resolution check)
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  STEP 4: CC VARIANT IMAGE COMPARISON", flush=True)
    print("=" * 60, flush=True)

    # Get both CC variant image URLs
    cc_imgs = page.evaluate("""() => {
        const results = [];
        for (const img of document.querySelectorAll('img')) {
            const src = img.src || '';
            if (src.includes('faltxt2img') && src.includes('1770937002')) {
                results.push({
                    src: src,
                    naturalW: img.naturalWidth,
                    naturalH: img.naturalHeight,
                });
            }
        }
        return results;
    }""")

    print(f"\n  CC variant images from latest generation:", flush=True)
    for img in cc_imgs:
        print(f"    {img['naturalW']}x{img['naturalH']} {img['src'][:100]}", flush=True)

    # Download variant 2 to verify it's also full-res
    variant2_url = None
    for img in cc_imgs:
        if '2_output' in img['src']:
            variant2_url = img['src']
            break

    if variant2_url:
        dest = SS_DIR / "cc_variant2.webp"
        try:
            req = urllib.request.Request(variant2_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = resp.read()
            dest.write_bytes(data)
            print(f"\n  Variant 2 downloaded: {len(data)} bytes", flush=True)
        except Exception as e:
            print(f"  Download failed: {e}", flush=True)
    else:
        print("  No variant 2 URL found", flush=True)

    # ============================================================
    #  STEP 5: LAYERS PANEL INSPECTION
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  STEP 5: LAYERS PANEL", flush=True)
    print("=" * 60, flush=True)

    # Switch to Layers tab
    page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            if ((el.innerText || '').trim() === 'Layers' && el.getBoundingClientRect().x > 1200) {
                el.click(); return true;
            }
        }
        return false;
    }""")
    page.wait_for_timeout(1000)

    ss(page, "P28_05_layers_panel")

    layers = page.evaluate("""() => {
        const items = [];
        for (const el of document.querySelectorAll('*')) {
            const r = el.getBoundingClientRect();
            const text = (el.innerText || '').trim();
            if (r.x > 1050 && r.y > 50 && r.y < 900
                && r.width > 15 && r.width < 400 && text
                && text.length > 0 && text.length < 80 && !text.includes('\\n')) {
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
            const key = i.text + '|' + Math.round(i.y / 5);
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
        }).sort((a, b) => a.y - b.y);
    }""")

    print(f"\n  Layers panel ({len(layers)}):", flush=True)
    for el in layers[:20]:
        print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> '{el['text']}'", flush=True)

    # ============================================================
    #  STEP 6: TRY KEYBOARD SHORTCUTS
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  STEP 6: KEYBOARD SHORTCUTS", flush=True)
    print("=" * 60, flush=True)

    # Test common shortcuts:
    # Delete/Backspace to remove layer
    # Ctrl+Z to undo
    # Ctrl+S to save
    # Ctrl+E to export
    shortcuts = [
        ("Meta+z", "Undo"),
        ("Meta+shift+z", "Redo"),
    ]

    for key, desc in shortcuts:
        page.keyboard.press(key)
        page.wait_for_timeout(300)
        print(f"  Pressed {key} ({desc})", flush=True)

    # Check keyboard shortcut help by pressing "?"
    page.keyboard.press("?")
    page.wait_for_timeout(1500)

    shortcut_dialog = page.evaluate("""() => {
        const items = [];
        for (const el of document.querySelectorAll('*')) {
            const style = window.getComputedStyle(el);
            const zIndex = parseInt(style.zIndex) || 0;
            const r = el.getBoundingClientRect();
            const text = (el.innerText || '').trim();
            if (zIndex > 100 && text && text.length > 0 && text.length < 80
                && !text.includes('\\n') && r.width > 15) {
                items.push({
                    text: text,
                    z: zIndex,
                    x: Math.round(r.x),
                    y: Math.round(r.y),
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

    if shortcut_dialog:
        print(f"\n  Shortcut dialog ({len(shortcut_dialog)}):", flush=True)
        for el in shortcut_dialog[:20]:
            print(f"    z={el['z']} ({el['x']},{el['y']}) '{el['text']}'", flush=True)
    else:
        print("  No shortcut dialog appeared", flush=True)

    page.keyboard.press("Escape")
    page.wait_for_timeout(500)

    ss(page, "P28_06_final")
    print(f"\n\n===== PHASE 28 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
