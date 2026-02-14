"""Phase 64: Model picker overlay, canvas layer automation, Insert Object sub-tool.

From P63:
- CC panel activates correctly (Ray button at (0,0) but JS click works)
- Img2Img fully mapped (Nano Banana Pro, 1K/2K/4K, 20 credits)
- Local Edit: Lasso/Brush/Auto masks, Prompt/Balanced/Image control, 4 credits
- AI Eraser: same masks, 9 credits
- Enhance & Upscale confirmed

Goals:
1. Open the model picker overlay and map all visible models (for Txt2Img)
2. Test layer selection and manipulation (select, delete, reorder)
3. Explore Insert Object sub-tool
4. Test Expand sub-tool
5. Count total models available
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
    page.wait_for_timeout(5000)
    close_dialogs(page)

    # ============================================================
    #  PART 1: MODEL PICKER OVERLAY
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 1: MODEL PICKER OVERLAY", flush=True)
    print("=" * 60, flush=True)

    # Activate Txt2Img first
    page.mouse.click(40, 306)  # Character
    page.wait_for_timeout(300)
    page.mouse.click(40, 197)  # Txt2Img
    page.wait_for_timeout(1500)
    close_dialogs(page)

    # Click the model name to open picker
    page.evaluate("""() => {
        var btn = document.querySelector('button.style');
        if (btn) { btn.click(); return true; }
        return false;
    }""")
    page.wait_for_timeout(2000)
    close_dialogs(page)

    ss(page, "P64_01_model_picker")

    # Map the categories on the left side of the picker
    categories = page.evaluate("""() => {
        var items = [];
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            var style = window.getComputedStyle(el);
            var z = parseInt(style.zIndex) || 0;
            // The picker is a z=999 overlay, categories are on the left
            if (z > 500 && r.x < 200 && r.width > 30 && r.width < 150
                && r.height > 15 && r.height < 40
                && text.length > 2 && text.length < 25 && r.y > 50) {
                items.push({
                    text: text,
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    tag: el.tagName,
                    classes: (el.className || '').toString().substring(0, 30),
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
    print(f"  Model categories ({len(categories)}):", flush=True)
    for c in categories:
        print(f"    ({c['x']},{c['y']}) {c['w']}x{c['h']} <{c['tag']}> c='{c['classes'][:20]}' '{c['text']}'", flush=True)

    # Map visible model cards
    models = page.evaluate("""() => {
        var items = [];
        for (const el of document.querySelectorAll('.style-name')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (r.x > 100 && r.width > 20 && r.height > 5 && text.length > 2) {
                items.push({
                    name: text,
                    x: Math.round(r.x), y: Math.round(r.y),
                });
            }
        }
        return items.sort(function(a,b) { return a.y - b.y || a.x - b.x; });
    }""")
    print(f"\n  Visible model names ({len(models)}):", flush=True)
    for m in models:
        print(f"    ({m['x']},{m['y']}) '{m['name']}'", flush=True)

    # Click "All styles" category to see total count
    page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            var style = window.getComputedStyle(el);
            var z = parseInt(style.zIndex) || 0;
            if (z > 500 && text === 'All styles' && r.x < 200) {
                el.click(); return true;
            }
        }
        return false;
    }""")
    page.wait_for_timeout(1500)

    all_models = page.evaluate("""() => {
        var items = [];
        for (const el of document.querySelectorAll('.style-name')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (r.width > 0 && text.length > 2) {
                items.push(text);
            }
        }
        return items;
    }""")
    print(f"\n  All visible models ({len(all_models)}):", flush=True)
    for m in all_models[:30]:
        print(f"    '{m}'", flush=True)
    if len(all_models) > 30:
        print(f"    ... and {len(all_models) - 30} more", flush=True)

    ss(page, "P64_02_all_styles")

    # Click "Realistic" category
    page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            var style = window.getComputedStyle(el);
            if (parseInt(style.zIndex) > 500 && text === 'Realistic' && r.x < 200) {
                el.click(); return true;
            }
        }
        return false;
    }""")
    page.wait_for_timeout(1000)

    realistic_models = page.evaluate("""() => {
        var items = [];
        for (const el of document.querySelectorAll('.style-name')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (r.width > 0 && text.length > 2) {
                items.push(text);
            }
        }
        return items;
    }""")
    print(f"\n  Realistic models ({len(realistic_models)}):", flush=True)
    for m in realistic_models:
        print(f"    '{m}'", flush=True)

    ss(page, "P64_03_realistic")

    # Close model picker
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)

    # ============================================================
    #  PART 2: LAYER SYSTEM
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 2: LAYER SYSTEM", flush=True)
    print("=" * 60, flush=True)

    # Switch to Layers tab
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

    # Map all layers
    layers = page.evaluate("""() => {
        var items = [];
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            var classes = (el.className || '').toString();
            if (r.x > 1060 && r.width > 200 && r.height > 30 && r.height < 100
                && (text.startsWith('Layer') || text === 'Background' || text.startsWith('Bg'))
                && text.length < 30) {
                items.push({
                    text: text,
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    tag: el.tagName,
                    classes: classes.substring(0, 40),
                });
            }
        }
        return items.sort(function(a,b) { return a.y - b.y; });
    }""")
    print(f"  Layers ({len(layers)}):", flush=True)
    for l in layers:
        print(f"    ({l['x']},{l['y']}) {l['w']}x{l['h']} <{l['tag']}> c='{l['classes'][:25]}' '{l['text']}'", flush=True)

    ss(page, "P64_04_layers")

    # Right-click a layer to see context menu
    if layers:
        layer = layers[0]
        print(f"\n  Right-clicking layer '{layer['text']}' at ({layer['x']+50},{layer['y']+20})...", flush=True)
        page.mouse.click(layer['x'] + 50, layer['y'] + 20, button="right")
        page.wait_for_timeout(1000)

        ctx_menu = page.evaluate("""() => {
            var items = [];
            for (const el of document.querySelectorAll('*')) {
                var style = window.getComputedStyle(el);
                var z = parseInt(style.zIndex) || 0;
                var r = el.getBoundingClientRect();
                var text = (el.innerText || '').trim();
                if (z > 50 && r.width > 50 && r.height > 10
                    && text.length > 1 && text.length < 40) {
                    items.push({
                        text: text,
                        x: Math.round(r.x), y: Math.round(r.y),
                        z: z,
                    });
                }
            }
            var seen = new Set();
            return items.filter(function(i) {
                if (seen.has(i.text)) return false;
                seen.add(i.text);
                return true;
            }).sort(function(a,b) { return a.y - b.y; }).slice(0, 20);
        }""")
        print(f"  Context menu ({len(ctx_menu)}):", flush=True)
        for cm in ctx_menu:
            print(f"    ({cm['x']},{cm['y']}) z={cm['z']} '{cm['text']}'", flush=True)

        ss(page, "P64_05_layer_context")
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)

    # ============================================================
    #  PART 3: INSERT OBJECT SUB-TOOL
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 3: INSERT OBJECT SUB-TOOL", flush=True)
    print("=" * 60, flush=True)

    # Activate Image Editor
    page.mouse.click(40, 252)  # Img2Img first
    page.wait_for_timeout(300)
    page.mouse.click(40, 698)  # Image Editor
    page.wait_for_timeout(1500)
    close_dialogs(page)

    # Click Insert Object
    page.evaluate("""() => {
        for (const btn of document.querySelectorAll('button')) {
            var text = (btn.innerText || '').trim();
            var r = btn.getBoundingClientRect();
            if (text === 'Insert Object' && r.x > 60 && r.x < 370 && r.y > 100) {
                btn.click(); return true;
            }
        }
        return false;
    }""")
    page.wait_for_timeout(2000)
    close_dialogs(page)

    ss(page, "P64_06_insert_object")

    # Dump panel
    insert_panel = page.evaluate("""() => {
        var items = [];
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (r.x > 60 && r.x < 370 && r.y > 40 && r.y < 900
                && r.width > 20 && r.height > 5
                && text.length > 0 && text.length < 50) {
                items.push({
                    text: text.substring(0, 40),
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    tag: el.tagName,
                    classes: (el.className || '').toString().substring(0, 30),
                });
            }
        }
        var seen = new Set();
        return items.filter(function(i) {
            var key = i.text.substring(0,15) + '|' + i.y;
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
        }).sort(function(a,b) { return a.y - b.y; }).slice(0, 30);
    }""")
    print(f"  Insert Object panel ({len(insert_panel)}):", flush=True)
    for ip in insert_panel:
        print(f"    ({ip['x']},{ip['y']}) {ip['w']}x{ip['h']} <{ip['tag']}> c='{ip['classes'][:22]}' '{ip['text'][:35]}'", flush=True)

    # Go back
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)

    # ============================================================
    #  PART 4: EXPAND SUB-TOOL
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 4: EXPAND SUB-TOOL", flush=True)
    print("=" * 60, flush=True)

    # Navigate to Image Editor
    page.mouse.click(40, 252)
    page.wait_for_timeout(300)
    page.mouse.click(40, 698)
    page.wait_for_timeout(1500)
    close_dialogs(page)

    # Click Expand
    page.evaluate("""() => {
        for (const btn of document.querySelectorAll('button')) {
            var text = (btn.innerText || '').trim();
            var r = btn.getBoundingClientRect();
            if (text === 'Expand' && r.x > 60 && r.x < 370 && r.y > 350) {
                btn.click(); return true;
            }
        }
        return false;
    }""")
    page.wait_for_timeout(2000)
    close_dialogs(page)

    ss(page, "P64_07_expand")

    expand_panel = page.evaluate("""() => {
        var items = [];
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (r.x > 60 && r.x < 370 && r.y > 40 && r.y < 900
                && r.width > 20 && r.height > 5
                && text.length > 0 && text.length < 50) {
                items.push({
                    text: text.substring(0, 40),
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    tag: el.tagName,
                    classes: (el.className || '').toString().substring(0, 30),
                });
            }
        }
        var seen = new Set();
        return items.filter(function(i) {
            var key = i.text.substring(0,15) + '|' + i.y;
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
        }).sort(function(a,b) { return a.y - b.y; }).slice(0, 30);
    }""")
    print(f"  Expand panel ({len(expand_panel)}):", flush=True)
    for ep in expand_panel:
        print(f"    ({ep['x']},{ep['y']}) {ep['w']}x{ep['h']} <{ep['tag']}> c='{ep['classes'][:22]}' '{ep['text'][:35]}'", flush=True)

    ss(page, "P64_08_final")

    print(f"\n\n===== PHASE 64 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
