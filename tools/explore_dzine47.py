"""Phase 47: Explore Product Background, Img2Img more ratios, model selection.

From P46:
- Product Background is a new tool in Image Editor (y=877)
- Img2Img has a "more" button at (296,425) for additional aspect ratios
- Txt2Img model is selectable via button.style
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
    #  PART 1: PRODUCT BACKGROUND TOOL
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 1: PRODUCT BACKGROUND TOOL", flush=True)
    print("=" * 60, flush=True)

    # Open Image Editor
    page.mouse.click(40, 698)
    page.wait_for_timeout(2000)
    close_dialogs(page)

    # Click on "Product Background" or "Background" subtool
    bg_clicked = page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text === 'Background' && r.x > 50 && r.x < 360 && r.y > 850) {
                el.click(); return {text: text, x: Math.round(r.x), y: Math.round(r.y)};
            }
        }
        // Try clicking the subtool-item
        for (const el of document.querySelectorAll('.subtool-item')) {
            var r = el.getBoundingClientRect();
            if (r.x > 50 && r.x < 360 && r.y > 850) {
                el.click();
                return {text: (el.innerText || '').trim(), x: Math.round(r.x), y: Math.round(r.y)};
            }
        }
        return null;
    }""")
    print(f"  Product Background clicked: {bg_clicked}", flush=True)
    page.wait_for_timeout(2000)

    ss(page, "P47_01_product_bg")

    # Dump whatever panel opened
    bg_panel = page.evaluate("""() => {
        var items = [];
        for (const el of document.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            if (r.x > 50 && r.x < 360 && r.y > 50 && r.y < 900
                && r.width > 10 && r.height > 5 && r.width < 350
                && !['path','line','circle','g','svg','defs','rect','polygon'].includes(el.tagName.toLowerCase())) {
                var text = (el.innerText || '').trim();
                if (text.length > 0 && text.length < 50) {
                    items.push({
                        tag: el.tagName,
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        text: text.substring(0, 35),
                        classes: (el.className || '').toString().substring(0, 35),
                    });
                }
            }
        }
        var seen = new Set();
        return items.filter(function(i) {
            var key = i.text.substring(0,15) + '|' + i.x + '|' + i.y;
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
        }).sort(function(a,b) { return a.y - b.y; });
    }""")
    print(f"\n  Product Background panel ({len(bg_panel)} elements):", flush=True)
    for el in bg_panel[:40]:
        print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> c='{el['classes'][:25]}' '{el['text'][:30]}'", flush=True)

    # Go back to main canvas
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)

    # ============================================================
    #  PART 2: IMG2IMG "MORE" ASPECT RATIOS
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 2: IMG2IMG MORE ASPECT RATIOS", flush=True)
    print("=" * 60, flush=True)

    page.mouse.click(40, 252)  # Img2Img
    page.wait_for_timeout(2000)
    close_dialogs(page)

    # Click the "more" button for aspect ratios
    more_clicked = page.evaluate("""() => {
        for (const el of document.querySelectorAll('.item.more')) {
            var r = el.getBoundingClientRect();
            if (r.x > 290 && r.y > 400 && r.y < 450) {
                el.click();
                return {x: Math.round(r.x), y: Math.round(r.y)};
            }
        }
        return null;
    }""")
    print(f"  More button clicked: {more_clicked}", flush=True)
    page.wait_for_timeout(1500)

    ss(page, "P47_02_img2img_more_ar")

    # Check for dropdown/popup with additional ratios
    ar_options = page.evaluate("""() => {
        var items = [];
        // Look for high-z elements (dropdowns/popups)
        for (const el of document.querySelectorAll('*')) {
            var z = parseInt(window.getComputedStyle(el).zIndex) || 0;
            var r = el.getBoundingClientRect();
            if (z > 100 && r.width > 50 && r.height > 20 && r.x > 50 && r.y > 200) {
                var text = (el.innerText || '').trim();
                if (text.length > 0 && text.length < 100) {
                    items.push({
                        z: z, tag: el.tagName,
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        text: text.substring(0, 60),
                        classes: (el.className || '').toString().substring(0, 40),
                    });
                }
            }
        }
        // Also look for any new visible items in the aspect ratio area
        for (const el of document.querySelectorAll('.item, .ratio-item, [class*="ratio"]')) {
            var r = el.getBoundingClientRect();
            var text = (el.innerText || '').trim();
            if (r.width > 20 && r.y > 400 && r.y < 600 && r.x > 50 && r.x < 360) {
                items.push({
                    z: 0, tag: el.tagName,
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    text: text,
                    classes: (el.className || '').toString().substring(0, 40),
                });
            }
        }
        var seen = new Set();
        return items.filter(function(i) {
            var key = i.text + '|' + i.x + '|' + i.y;
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
        }).sort(function(a,b) { return a.y - b.y; });
    }""")
    print(f"\n  Aspect ratio options ({len(ar_options)}):", flush=True)
    for opt in ar_options[:20]:
        print(f"    z={opt['z']} ({opt['x']},{opt['y']}) {opt['w']}x{opt['h']} <{opt['tag']}> c='{opt['classes'][:25]}' '{opt['text']}'", flush=True)

    page.keyboard.press("Escape")
    page.wait_for_timeout(500)

    # ============================================================
    #  PART 3: TXT2IMG MODEL SELECTION
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 3: TXT2IMG MODEL SELECTION", flush=True)
    print("=" * 60, flush=True)

    page.mouse.click(40, 197)  # Txt2Img
    page.wait_for_timeout(2000)
    close_dialogs(page)

    # Click the model name to open picker
    model_clicked = page.evaluate("""() => {
        var btn = document.querySelector('button.style');
        if (btn) {
            var r = btn.getBoundingClientRect();
            if (r.x > 50 && r.x < 350) {
                btn.click();
                var name = btn.querySelector('.style-name');
                return {
                    name: name ? name.innerText.trim() : '?',
                    x: Math.round(r.x), y: Math.round(r.y),
                };
            }
        }
        return null;
    }""")
    print(f"  Model clicked: {model_clicked}", flush=True)
    page.wait_for_timeout(2000)

    ss(page, "P47_03_model_picker")

    # Dump the model picker overlay
    picker = page.evaluate("""() => {
        // Find the z=999+ overlay
        var overlay = null;
        for (const el of document.querySelectorAll('*')) {
            var z = parseInt(window.getComputedStyle(el).zIndex) || 0;
            var r = el.getBoundingClientRect();
            if (z > 900 && r.width > 400 && r.height > 400) {
                overlay = el;
                break;
            }
        }
        if (!overlay) return {error: 'no overlay'};

        // Get categories
        var categories = [];
        for (const el of overlay.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            var text = (el.innerText || '').trim();
            var classes = (el.className || '').toString();
            // Categories are typically in a sidebar/tab list
            if ((classes.includes('category') || classes.includes('tab') || classes.includes('nav'))
                && text.length > 2 && text.length < 30 && r.width > 30) {
                categories.push({
                    text: text,
                    x: Math.round(r.x), y: Math.round(r.y),
                    selected: classes.includes('selected') || classes.includes('active'),
                });
            }
        }

        // Get model cards
        var models = [];
        for (const el of overlay.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            var text = (el.innerText || '').trim();
            var classes = (el.className || '').toString();
            // Model names are short text items
            if (text.length > 3 && text.length < 30 && r.width > 50 && r.height > 10
                && r.height < 30 && r.y > 100 && r.x > 200) {
                models.push({
                    text: text,
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width),
                    classes: classes.substring(0, 30),
                });
            }
        }

        return {
            categories: categories.slice(0, 20),
            models: models.slice(0, 30),
        };
    }""")

    if picker.get('error'):
        print(f"  Picker: {picker}", flush=True)
    else:
        cats = picker.get('categories', [])
        mods = picker.get('models', [])
        print(f"\n  Categories ({len(cats)}):", flush=True)
        for c in cats:
            sel = ' (SELECTED)' if c.get('selected') else ''
            print(f"    ({c['x']},{c['y']}) '{c['text']}'{sel}", flush=True)
        print(f"\n  Models ({len(mods)}):", flush=True)
        for m in mods:
            print(f"    ({m['x']},{m['y']}) w={m['w']} c='{m['classes'][:20]}' '{m['text']}'", flush=True)

    # Get the full inner text of the overlay for a comprehensive view
    overlay_text = page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            var z = parseInt(window.getComputedStyle(el).zIndex) || 0;
            var r = el.getBoundingClientRect();
            if (z > 900 && r.width > 400 && r.height > 400) {
                // Get left nav items
                var nav = [];
                for (const item of el.querySelectorAll('.left-filter-item, .filter-item, [class*="category-item"]')) {
                    nav.push((item.innerText || '').trim());
                }

                // Get model items with more detail
                var models = [];
                for (const card of el.querySelectorAll('.style-list-item, .model-item, .model-card, [class*="style-item"]')) {
                    var cr = card.getBoundingClientRect();
                    var name = '';
                    var nameEl = card.querySelector('.style-name, .model-name, .name');
                    if (nameEl) name = nameEl.innerText.trim();
                    else name = card.innerText.trim().split('\\n')[0];
                    if (name && cr.width > 30) {
                        models.push({
                            name: name.substring(0, 30),
                            x: Math.round(cr.x), y: Math.round(cr.y),
                            w: Math.round(cr.width), h: Math.round(cr.height),
                        });
                    }
                }

                return {nav: nav, models: models};
            }
        }
        return null;
    }""")
    if overlay_text:
        print(f"\n  Navigation items ({len(overlay_text.get('nav', []))}):", flush=True)
        for n in overlay_text.get('nav', []):
            print(f"    '{n}'", flush=True)
        print(f"\n  Model cards ({len(overlay_text.get('models', []))}):", flush=True)
        for m in overlay_text.get('models', []):
            print(f"    ({m['x']},{m['y']}) {m['w']}x{m['h']} '{m['name']}'", flush=True)

    # Close picker
    page.keyboard.press("Escape")
    page.wait_for_timeout(1000)

    # ============================================================
    #  PART 4: TXT2IMG "MORE" ASPECT RATIOS
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 4: TXT2IMG MORE ASPECT RATIOS", flush=True)
    print("=" * 60, flush=True)

    # Check if Txt2Img has a "more" button too
    txt2img_more = page.evaluate("""() => {
        var items = [];
        for (const el of document.querySelectorAll('.item.more, .c-aspect-ratio .more')) {
            var r = el.getBoundingClientRect();
            if (r.x > 50 && r.x < 360 && r.y > 300) {
                items.push({
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    text: (el.innerText || '').trim(),
                    classes: (el.className || '').toString().substring(0, 30),
                });
            }
        }
        return items;
    }""")
    print(f"  Txt2Img more buttons ({len(txt2img_more)}):", flush=True)
    for m in txt2img_more:
        print(f"    ({m['x']},{m['y']}) {m['w']}x{m['h']} c='{m['classes']}' '{m['text']}'", flush=True)

    if txt2img_more:
        # Click the first "more" button
        m = txt2img_more[0]
        page.mouse.click(m['x'] + m['w'] // 2, m['y'] + m['h'] // 2)
        page.wait_for_timeout(1500)

        ss(page, "P47_04_txt2img_more_ar")

        # Check what appeared
        ar_popup = page.evaluate("""() => {
            var items = [];
            for (const el of document.querySelectorAll('.item, .ratio-option, [class*="aspect"]')) {
                var r = el.getBoundingClientRect();
                var text = (el.innerText || '').trim();
                if (r.x > 50 && r.x < 360 && r.y > 300 && r.y < 700
                    && r.width > 15 && r.height > 10 && text.length < 30) {
                    items.push({
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        text: text,
                        classes: (el.className || '').toString().substring(0, 35),
                        selected: (el.className || '').toString().includes('selected'),
                    });
                }
            }
            var seen = new Set();
            return items.filter(function(i) {
                var key = i.text + '|' + i.x + '|' + i.y;
                if (seen.has(key)) return false;
                seen.add(key);
                return true;
            }).sort(function(a,b) { return a.y - b.y; });
        }""")
        print(f"\n  Aspect ratio options ({len(ar_popup)}):", flush=True)
        for opt in ar_popup[:20]:
            sel = ' (SELECTED)' if opt['selected'] else ''
            print(f"    ({opt['x']},{opt['y']}) {opt['w']}x{opt['h']} c='{opt['classes'][:25]}'{sel} '{opt['text']}'", flush=True)

        page.keyboard.press("Escape")
        page.wait_for_timeout(500)

    # ============================================================
    #  PART 5: AI VIDEO PANEL DETAIL
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 5: AI VIDEO PANEL", flush=True)
    print("=" * 60, flush=True)

    page.mouse.click(40, 361)  # AI Video
    page.wait_for_timeout(2000)
    close_dialogs(page)

    ss(page, "P47_05_ai_video")

    video_panel = page.evaluate("""() => {
        var items = [];
        for (const el of document.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            if (r.x > 50 && r.x < 360 && r.y > 50 && r.y < 900
                && r.width > 15 && r.height > 5 && r.width < 350
                && !['path','line','circle','g','svg','defs','rect','polygon'].includes(el.tagName.toLowerCase())) {
                var text = (el.innerText || '').trim();
                if (text.length > 0 && text.length < 50) {
                    items.push({
                        tag: el.tagName,
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        text: text.substring(0, 35),
                        classes: (el.className || '').toString().substring(0, 30),
                    });
                }
            }
        }
        var seen = new Set();
        return items.filter(function(i) {
            var key = i.text.substring(0,15) + '|' + i.y;
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
        }).sort(function(a,b) { return a.y - b.y; });
    }""")
    print(f"\n  AI Video panel ({len(video_panel)}):", flush=True)
    for el in video_panel[:50]:
        print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> c='{el['classes'][:20]}' '{el['text'][:30]}'", flush=True)

    # Check video models
    video_models = page.evaluate("""() => {
        for (const el of document.querySelectorAll('button.style, .model-selector, [class*="model"]')) {
            var r = el.getBoundingClientRect();
            var text = (el.innerText || '').trim();
            if (r.x > 50 && r.x < 360 && r.width > 100 && text.length > 3) {
                return {
                    text: text.substring(0, 40),
                    x: Math.round(r.x), y: Math.round(r.y),
                    classes: (el.className || '').toString().substring(0, 40),
                };
            }
        }
        return null;
    }""")
    print(f"\n  Video model: {video_models}", flush=True)

    # ============================================================
    #  PART 6: LIP SYNC PANEL DETAIL
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 6: LIP SYNC PANEL", flush=True)
    print("=" * 60, flush=True)

    page.mouse.click(40, 425)  # Lip Sync
    page.wait_for_timeout(2000)
    close_dialogs(page)

    ss(page, "P47_06_lip_sync")

    lip_panel = page.evaluate("""() => {
        var items = [];
        for (const el of document.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            if (r.x > 50 && r.x < 360 && r.y > 50 && r.y < 700
                && r.width > 15 && r.height > 5 && r.width < 350
                && !['path','line','circle','g','svg','defs','rect','polygon'].includes(el.tagName.toLowerCase())) {
                var text = (el.innerText || '').trim();
                if (text.length > 0 && text.length < 50) {
                    items.push({
                        tag: el.tagName,
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        text: text.substring(0, 35),
                        classes: (el.className || '').toString().substring(0, 25),
                    });
                }
            }
        }
        var seen = new Set();
        return items.filter(function(i) {
            var key = i.text.substring(0,12) + '|' + i.y;
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
        }).sort(function(a,b) { return a.y - b.y; });
    }""")
    print(f"\n  Lip Sync panel ({len(lip_panel)}):", flush=True)
    for el in lip_panel[:30]:
        print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> c='{el['classes'][:20]}' '{el['text'][:30]}'", flush=True)

    ss(page, "P47_07_final")
    print(f"\n\n===== PHASE 47 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
