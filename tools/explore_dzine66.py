"""Phase 66: Model picker deep scan (scroll all categories), canvas context menu, Variation workflow.

From P65:
- Model picker overlay found at style-list-panel (208,128) 1024x692
- Categories sidebar: 17 visible (Favorites through Tattoo)
- General category: Dzine General, GPT Image 1.5, Z-Image Turbo, Seedream 4.5, FLUX.2 Pro, etc.
- Hand Repair: mask-only, 4 credits
- Face Swap: upload face only, 4 credits
- Face Repair: mask + prompt + Preserve slider, 4 credits
- Layer opacity click found

Goals:
1. Open model picker, click each category, count models per category
2. Scroll the model grid to count total visible models in "All styles"
3. Test canvas right-click context menu
4. Explore Variation workflow (direct generation from Results panel)
5. Check if Legacy category exists below Tattoo
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
    print("  Waiting 12s for full canvas load...", flush=True)
    page.wait_for_timeout(12000)
    close_dialogs(page)

    # ============================================================
    #  PART 1: MODEL PICKER — CATEGORY SCAN
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 1: MODEL PICKER — CATEGORY SCAN", flush=True)
    print("=" * 60, flush=True)

    # Activate Txt2Img
    page.mouse.click(40, 306)
    page.wait_for_timeout(500)
    page.mouse.click(40, 197)
    page.wait_for_timeout(2000)
    close_dialogs(page)

    # Open model picker
    page.evaluate("""() => {
        var btn = document.querySelector('button.style');
        if (btn) { btn.click(); return true; }
        return false;
    }""")
    page.wait_for_timeout(2000)

    # Get all categories from the left sidebar
    categories = page.evaluate("""() => {
        var panel = document.querySelector('.style-list-panel');
        if (!panel) return [];
        var items = [];
        // Categories are in the left portion of the panel
        for (const el of panel.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            // Categories are clickable items in the left sidebar (x < 400, single-line text)
            if (r.x >= 210 && r.x < 400 && r.width > 40 && r.width < 180
                && r.height > 15 && r.height < 40 && text.length > 1 && text.length < 25
                && text.indexOf('\\n') === -1) {
                items.push({
                    text: text,
                    x: Math.round(r.x), y: Math.round(r.y),
                    tag: el.tagName,
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
    print(f"  Categories ({len(categories)}):", flush=True)
    for c in categories:
        print(f"    ({c['x']},{c['y']}) <{c['tag']}> '{c['text']}'", flush=True)

    ss(page, "P66_01_picker_categories")

    # Click each category and count the model cards
    category_counts = {}
    for cat in categories:
        if cat['text'] in ['Favorites', 'My Styles', 'Recent']:
            continue  # These are user-specific, skip

        # Click category
        page.evaluate(f"""() => {{
            var panel = document.querySelector('.style-list-panel');
            if (!panel) return false;
            for (const el of panel.querySelectorAll('*')) {{
                var text = (el.innerText || '').trim();
                var r = el.getBoundingClientRect();
                if (text === {json.dumps(cat['text'])} && r.x >= 210 && r.x < 400
                    && r.height < 40 && r.height > 15) {{
                    el.click(); return true;
                }}
            }}
            return false;
        }}""")
        page.wait_for_timeout(800)

        # Count visible model cards in the grid
        # Models are shown as cards with thumbnail + name
        count_info = page.evaluate("""() => {
            var panel = document.querySelector('.style-list');
            if (!panel) return {count: 0, names: []};
            var cards = panel.querySelectorAll('.style-card, .c-style-card, [class*="card"]');
            var names = [];
            // Also try getting model names from text nodes in the grid area
            for (const el of panel.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                var r = el.getBoundingClientRect();
                var classes = (el.className || '').toString();
                if (r.x > 400 && r.width > 50 && r.width < 200
                    && r.height > 50 && r.height < 250
                    && text.length > 2 && text.length < 40
                    && text.indexOf('\\n') === -1 && r.y > 300) {
                    names.push(text);
                }
            }
            // Deduplicate
            var unique = [...new Set(names)];
            return {count: cards.length, names: unique};
        }""")

        # Alternative: count by looking for img elements in the grid
        img_count = page.evaluate("""() => {
            var panel = document.querySelector('.style-list');
            if (!panel) return 0;
            var count = 0;
            for (const img of panel.querySelectorAll('img')) {
                var r = img.getBoundingClientRect();
                if (r.x > 400 && r.width > 50 && r.height > 50 && r.y > 200) {
                    count++;
                }
            }
            return count;
        }""")

        category_counts[cat['text']] = {
            'cards': count_info['count'],
            'img_count': img_count,
            'names': count_info['names'][:10],
        }
        print(f"  {cat['text']}: cards={count_info['count']}, imgs={img_count}, names({len(count_info['names'])}): {count_info['names'][:5]}", flush=True)

    # Now click "All styles" and scroll to count total
    print("\n  Scrolling 'All styles' to count total...", flush=True)
    page.evaluate("""() => {
        var panel = document.querySelector('.style-list-panel');
        if (!panel) return false;
        for (const el of panel.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text === 'All styles' && r.x >= 210 && r.x < 400) {
                el.click(); return true;
            }
        }
        return false;
    }""")
    page.wait_for_timeout(1000)

    # Scroll through the grid and collect all model names
    all_names = set()
    for scroll_pass in range(10):
        names = page.evaluate("""() => {
            var panel = document.querySelector('.style-list');
            if (!panel) return [];
            var names = [];
            for (const el of panel.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                var r = el.getBoundingClientRect();
                if (r.x > 400 && r.width > 50 && r.width < 200
                    && r.height > 10 && r.height < 30
                    && text.length > 2 && text.length < 40
                    && text.indexOf('\\n') === -1 && r.y > 200) {
                    names.push(text);
                }
            }
            return [...new Set(names)];
        }""")
        before = len(all_names)
        all_names.update(names)
        after = len(all_names)
        print(f"    Scroll {scroll_pass}: found {len(names)} visible, total unique: {after}", flush=True)

        if after == before and scroll_pass > 0:
            # No new names — try scrolling more
            pass

        # Scroll the grid down
        page.evaluate("""() => {
            var panel = document.querySelector('.style-list');
            if (panel) panel.scrollTop += 400;
        }""")
        page.wait_for_timeout(500)

    print(f"\n  Total unique model names: {len(all_names)}", flush=True)
    for name in sorted(all_names):
        print(f"    '{name}'", flush=True)

    ss(page, "P66_02_all_styles_scrolled")

    # Close picker
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)

    # ============================================================
    #  PART 2: CANVAS RIGHT-CLICK CONTEXT MENU
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 2: CANVAS RIGHT-CLICK CONTEXT MENU", flush=True)
    print("=" * 60, flush=True)

    # Right-click on the canvas image
    page.mouse.click(700, 450, button="right")
    page.wait_for_timeout(1000)

    ss(page, "P66_03_canvas_right_click")

    # Check for context menu
    ctx_menu = page.evaluate("""() => {
        var items = [];
        for (const el of document.querySelectorAll('*')) {
            var style = window.getComputedStyle(el);
            var z = parseInt(style.zIndex) || 0;
            var r = el.getBoundingClientRect();
            var text = (el.innerText || '').trim();
            if (z > 100 && r.width > 80 && r.height > 15 && r.height < 60
                && text.length > 1 && text.length < 40
                && text.indexOf('\\n') === -1) {
                items.push({
                    text: text, z: z,
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
        }).sort(function(a,b) { return a.y - b.y; }).slice(0, 20);
    }""")
    print(f"  Context menu items ({len(ctx_menu)}):", flush=True)
    for cm in ctx_menu:
        print(f"    z={cm['z']} ({cm['x']},{cm['y']}) {cm['w']}x{cm['h']} <{cm['tag']}> c='{cm['classes'][:20]}' '{cm['text']}'", flush=True)

    # Close it
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)

    # ============================================================
    #  PART 3: CANVAS SELECTION + KEYBOARD SHORTCUTS
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 3: CANVAS SELECTION + SHORTCUTS", flush=True)
    print("=" * 60, flush=True)

    # Click on the canvas image to select a layer
    page.mouse.click(700, 400)
    page.wait_for_timeout(1000)

    # Check what's selected
    selection = page.evaluate("""() => {
        var result = {};
        // Check for selection handles
        for (const el of document.querySelectorAll('*')) {
            var classes = (el.className || '').toString();
            if (classes.includes('selected') || classes.includes('active')) {
                var r = el.getBoundingClientRect();
                if (r.width > 100 && r.height > 100 && r.x > 300 && r.x < 1100) {
                    result.selected = {
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        classes: classes.substring(0, 50),
                    };
                    break;
                }
            }
        }
        // Check top bar for selection info
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (r.y < 60 && r.x > 100 && r.x < 900 && text.length > 3 && text.length < 40
                && r.height > 10 && r.height < 35) {
                if (!result.topbar) result.topbar = [];
                if (result.topbar.length < 10) {
                    result.topbar.push({text: text, x: Math.round(r.x), y: Math.round(r.y)});
                }
            }
        }
        return result;
    }""")
    print(f"  Selection info: {json.dumps(selection, indent=2)}", flush=True)

    ss(page, "P66_04_canvas_selected")

    # Try Delete key
    print("\n  Testing keyboard shortcuts...", flush=True)

    # Ctrl+D (duplicate?)
    # Don't actually execute destructive actions, just check shortcuts tooltip
    # Try pressing "?" for shortcuts
    page.keyboard.press("?")
    page.wait_for_timeout(1000)

    shortcuts = page.evaluate("""() => {
        var items = [];
        for (const el of document.querySelectorAll('*')) {
            var style = window.getComputedStyle(el);
            var z = parseInt(style.zIndex) || 0;
            var r = el.getBoundingClientRect();
            var text = (el.innerText || '').trim();
            if (z > 500 && r.width > 200 && r.height > 100) {
                items.push({
                    text: text.substring(0, 200), z: z,
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                });
            }
        }
        return items.slice(0, 3);
    }""")
    print(f"  Shortcuts overlay ({len(shortcuts)}):", flush=True)
    for s in shortcuts:
        print(f"    z={s['z']} ({s['x']},{s['y']}) {s['w']}x{s['h']} '{s['text'][:80]}'", flush=True)

    ss(page, "P66_05_shortcuts")

    page.keyboard.press("Escape")
    page.wait_for_timeout(300)

    # ============================================================
    #  PART 4: CHECK "REALISTIC" CATEGORY MODELS IN DETAIL
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 4: REALISTIC CATEGORY MODELS", flush=True)
    print("=" * 60, flush=True)

    # Open model picker again
    page.evaluate("""() => {
        var btn = document.querySelector('button.style');
        if (btn) { btn.click(); return true; }
        return false;
    }""")
    page.wait_for_timeout(2000)

    # Click Realistic
    page.evaluate("""() => {
        var panel = document.querySelector('.style-list-panel');
        if (!panel) return false;
        for (const el of panel.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text === 'Realistic' && r.x >= 210 && r.x < 400) {
                el.click(); return true;
            }
        }
        return false;
    }""")
    page.wait_for_timeout(1000)

    ss(page, "P66_06_realistic")

    # Scroll and collect all Realistic model names
    realistic_names = set()
    for scroll_pass in range(8):
        names = page.evaluate("""() => {
            var panel = document.querySelector('.style-list');
            if (!panel) return [];
            var names = [];
            for (const el of panel.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                var r = el.getBoundingClientRect();
                if (r.x > 400 && r.width > 50 && r.width < 200
                    && r.height > 10 && r.height < 30
                    && text.length > 2 && text.length < 40
                    && text.indexOf('\\n') === -1 && r.y > 200) {
                    names.push(text);
                }
            }
            return [...new Set(names)];
        }""")
        realistic_names.update(names)
        page.evaluate("""() => {
            var panel = document.querySelector('.style-list');
            if (panel) panel.scrollTop += 400;
        }""")
        page.wait_for_timeout(400)

    print(f"  Realistic models ({len(realistic_names)}):", flush=True)
    for name in sorted(realistic_names):
        print(f"    '{name}'", flush=True)

    ss(page, "P66_07_realistic_scrolled")

    # Close picker
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)

    ss(page, "P66_08_final")

    print(f"\n\n===== PHASE 66 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
