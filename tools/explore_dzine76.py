"""Phase 76: AI Video via scrolled results panel, Img2Img panel details,
full results panel action list, keyboard shortcuts check.
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


def click_sidebar(page, name):
    return page.evaluate(f"""() => {{
        for (const el of document.querySelectorAll('*')) {{
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text === '{name}' && r.x < 60 && r.y > 60 && r.height < 50) {{
                el.click();
                return {{x: Math.round(r.x), y: Math.round(r.y)}};
            }}
        }}
        return null;
    }}""")


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
    #  PART 1: FULL RESULTS PANEL ACTION LIST
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 1: FULL RESULTS PANEL ACTION LIST", flush=True)
    print("=" * 60, flush=True)

    # Switch to Results
    page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            if ((el.innerText || '').trim() === 'Results'
                && el.getBoundingClientRect().x > 500
                && el.getBoundingClientRect().y < 60) {
                el.click(); return true;
            }
        }
        return false;
    }""")
    page.wait_for_timeout(1000)

    # Get ALL gen-handle-function rows (the action rows with 1/2 buttons)
    action_rows = page.evaluate("""() => {
        var rows = [];
        var els = document.querySelectorAll('.gen-handle-function');
        for (var el of els) {
            var labelEl = el.querySelector('.label-text');
            var label = labelEl ? (labelEl.innerText || '').trim() : '';
            var r = el.getBoundingClientRect();
            var btns = [];
            el.querySelectorAll('button.btn').forEach(function(b) {
                btns.push((b.innerText || '').trim());
            });
            rows.push({
                label: label,
                y: Math.round(r.y),
                buttons: btns,
                classes: (el.className || '').toString().substring(0, 50),
            });
        }
        return rows.sort(function(a,b) { return a.y - b.y; });
    }""")
    print(f"  Action rows ({len(action_rows)}):", flush=True)
    for r in action_rows:
        print(f"    y={r['y']} '{r['label']}' btns={r['buttons']} c='{r['classes'][:40]}'", flush=True)

    # Count result groups by type
    result_groups = page.evaluate("""() => {
        var groups = [];
        var els = document.querySelectorAll('.gen-temp-header, .output-result');
        for (var el of els) {
            var text = (el.innerText || '').trim().replace(/\\n/g, ' ').substring(0, 60);
            var r = el.getBoundingClientRect();
            var classes = (el.className || '').toString();
            groups.push({
                text: text,
                y: Math.round(r.y),
                classes: classes.substring(0, 50),
            });
        }
        return groups.sort(function(a,b) { return a.y - b.y; });
    }""")
    print(f"\n  Result groups ({len(result_groups)}):", flush=True)
    for g in result_groups:
        print(f"    y={g['y']} c='{g['classes'][:35]}' '{g['text'][:50]}'", flush=True)

    # ============================================================
    #  PART 2: AI VIDEO — SCROLL RESULTS TO FIND AND CLICK
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 2: AI VIDEO VIA SCROLLED RESULTS", flush=True)
    print("=" * 60, flush=True)

    # Find scrollable results container
    scroll_container = page.evaluate("""() => {
        var container = document.querySelector('.c-material-library-v2');
        if (!container) return null;
        // Look for scrollable child
        for (var el of container.querySelectorAll('*')) {
            if (el.scrollHeight > el.clientHeight + 20 && el.clientHeight > 200) {
                var r = el.getBoundingClientRect();
                return {
                    tag: el.tagName,
                    classes: (el.className || '').toString().substring(0, 50),
                    scrollHeight: el.scrollHeight,
                    clientHeight: el.clientHeight,
                    scrollTop: el.scrollTop,
                    x: Math.round(r.x), y: Math.round(r.y),
                };
            }
        }
        return null;
    }""")
    print(f"  Results scroll container: {scroll_container}", flush=True)

    # Scroll down to find AI Video action row
    if scroll_container:
        # Scroll the results panel to find AI Video
        page.mouse.move(1300, 400)
        page.mouse.wheel(0, 500)
        page.wait_for_timeout(500)

        # Check if AI Video is now visible
        av_row = page.evaluate("""() => {
            var els = document.querySelectorAll('.gen-handle-function');
            for (var el of els) {
                var labelEl = el.querySelector('.label-text');
                var label = labelEl ? (labelEl.innerText || '').trim() : '';
                if (label === 'AI Video') {
                    var r = el.getBoundingClientRect();
                    return {y: Math.round(r.y), visible: r.y > 0 && r.y < 900};
                }
            }
            return null;
        }""")
        print(f"  AI Video row after scroll: {av_row}", flush=True)

        if av_row and av_row.get('visible'):
            # Click the "1" button on AI Video row
            av_click = page.evaluate("""() => {
                var els = document.querySelectorAll('.gen-handle-function');
                for (var el of els) {
                    var labelEl = el.querySelector('.label-text');
                    var label = labelEl ? (labelEl.innerText || '').trim() : '';
                    if (label === 'AI Video') {
                        var btn = el.querySelector('button.btn');
                        if (btn) {
                            btn.click();
                            var r = btn.getBoundingClientRect();
                            return {x: Math.round(r.x), y: Math.round(r.y)};
                        }
                    }
                }
                return null;
            }""")
            print(f"  AI Video '1' clicked: {av_click}", flush=True)
            page.wait_for_timeout(3000)
            close_dialogs(page)
            ss(page, "P76_01_ai_video_from_results")

            # Check what opened — look for any new panel or overlay
            overlay = page.evaluate("""() => {
                var items = [];
                for (const el of document.querySelectorAll('*')) {
                    var r = el.getBoundingClientRect();
                    var cs = window.getComputedStyle(el);
                    var z = parseInt(cs.zIndex) || 0;
                    if (r.x >= 60 && r.x <= 500 && r.y >= 40 && r.y <= 700
                        && r.width > 100 && r.height > 100 && r.width < 400) {
                        var text = (el.innerText || '').trim().replace(/\\n/g, ' ').substring(0, 60);
                        if (text.length > 5) {
                            items.push({
                                tag: el.tagName, z: z,
                                x: Math.round(r.x), y: Math.round(r.y),
                                w: Math.round(r.width), h: Math.round(r.height),
                                classes: (el.className || '').toString().substring(0, 40),
                                text: text.substring(0, 50),
                            });
                        }
                    }
                }
                return items.sort(function(a,b) { return b.z - a.z; }).slice(0, 10);
            }""")
            print(f"\n  Panels/overlays after AI Video click ({len(overlay)}):", flush=True)
            for o in overlay:
                print(f"    z={o['z']} ({o['x']},{o['y']}) {o['w']}x{o['h']} <{o['tag']}> c='{o['classes'][:30]}' '{o['text'][:40]}'", flush=True)

            page.keyboard.press("Escape")
            page.wait_for_timeout(1000)
        else:
            # Scroll more
            page.mouse.wheel(0, 800)
            page.wait_for_timeout(500)
            av_row2 = page.evaluate("""() => {
                var els = document.querySelectorAll('.gen-handle-function');
                for (var el of els) {
                    var labelEl = el.querySelector('.label-text');
                    var label = labelEl ? (labelEl.innerText || '').trim() : '';
                    if (label === 'AI Video') {
                        var r = el.getBoundingClientRect();
                        return {y: Math.round(r.y), visible: r.y > 0 && r.y < 900};
                    }
                }
                return null;
            }""")
            print(f"  AI Video row after more scroll: {av_row2}", flush=True)

    # Scroll back to top
    page.mouse.move(1300, 400)
    page.mouse.wheel(0, -3000)
    page.wait_for_timeout(500)

    # ============================================================
    #  PART 3: IMG2IMG PANEL
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 3: IMG2IMG PANEL", flush=True)
    print("=" * 60, flush=True)

    click_sidebar(page, "Txt2Img")
    page.wait_for_timeout(1000)
    close_dialogs(page)

    click_sidebar(page, "Img2Img")
    page.wait_for_timeout(2000)
    close_dialogs(page)
    ss(page, "P76_02_img2img")

    # Dump Img2Img panel
    i2i_items = page.evaluate("""() => {
        var items = [];
        var excluded = ['path','line','circle','g','svg','defs','rect','polygon',
                        'clippath','HTML','BODY','HEAD','SCRIPT','STYLE','META','LINK'];
        for (const el of document.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            if (r.x >= 60 && r.x <= 400 && r.y >= 40 && r.y <= 900
                && r.width > 10 && r.height > 10 && r.width < 400
                && !excluded.includes(el.tagName.toUpperCase())) {
                var text = (el.innerText || '').trim().substring(0, 50);
                if (text.length > 0 && text.indexOf('\\n') === -1) {
                    items.push({
                        tag: el.tagName, x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        text: text.replace(/\\n/g, ' ').substring(0, 40),
                        classes: (el.className || '').toString().substring(0, 30),
                    });
                }
            }
        }
        var seen = new Set();
        return items.filter(function(i) {
            var key = i.tag + '|' + i.x + '|' + i.y;
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
        }).sort(function(a,b) { return a.y - b.y; }).slice(0, 50);
    }""")
    print(f"  Img2Img panel ({len(i2i_items)}):", flush=True)
    for el in i2i_items:
        print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> c='{el['classes'][:22]}' '{el['text'][:35]}'", flush=True)

    # ============================================================
    #  PART 4: KEYBOARD SHORTCUTS INVENTORY
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 4: KEYBOARD SHORTCUTS", flush=True)
    print("=" * 60, flush=True)

    # Try Cmd+Z (undo), Cmd+Shift+Z (redo), Delete, Cmd+D (duplicate?)
    # Cmd+A (select all?), Cmd+C/V (copy/paste?), Space (hand tool?)
    shortcuts = {}

    # Test V key (move tool?)
    page.keyboard.press("v")
    page.wait_for_timeout(300)
    tool_after_v = page.evaluate("""() => {
        var active = document.querySelector('.c-top-toolbar .active, .tool-item.active');
        if (active) return (active.className || '').toString().substring(0, 50);
        return null;
    }""")
    shortcuts['v'] = tool_after_v

    # Test T key (text tool?)
    page.keyboard.press("t")
    page.wait_for_timeout(300)
    tool_after_t = page.evaluate("""() => {
        var active = document.querySelector('.c-top-toolbar .active, .tool-item.active');
        if (active) return (active.className || '').toString().substring(0, 50);
        return null;
    }""")
    shortcuts['t'] = tool_after_t

    # Test H key (hand tool?)
    page.keyboard.press("h")
    page.wait_for_timeout(300)
    tool_after_h = page.evaluate("""() => {
        var active = document.querySelector('.c-top-toolbar .active, .tool-item.active');
        if (active) return (active.className || '').toString().substring(0, 50);
        return null;
    }""")
    shortcuts['h'] = tool_after_h

    # Test Space (pan?)
    page.keyboard.press("Space")
    page.wait_for_timeout(300)
    shortcuts['space'] = page.evaluate("""() => {
        var cursor = document.querySelector('canvas') ?
            window.getComputedStyle(document.querySelector('canvas')).cursor : null;
        return cursor;
    }""")

    # Test ? (help/shortcuts panel?)
    page.keyboard.press("?")
    page.wait_for_timeout(500)
    help_panel = page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            var cs = window.getComputedStyle(el);
            var z = parseInt(cs.zIndex) || 0;
            var r = el.getBoundingClientRect();
            if (z > 500 && r.width > 200 && r.height > 200) {
                return {z: z, text: (el.innerText || '').substring(0, 100).replace(/\\n/g, ' ')};
            }
        }
        return null;
    }""")
    shortcuts['?'] = help_panel

    page.keyboard.press("Escape")
    page.wait_for_timeout(300)

    print(f"  Keyboard shortcuts:", flush=True)
    for k, v in shortcuts.items():
        print(f"    '{k}' → {v}", flush=True)

    # ============================================================
    #  PART 5: GENERATION MODES COUNT
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 5: COMPLETE FEATURE INVENTORY", flush=True)
    print("=" * 60, flush=True)

    # List all unique action labels in results
    all_actions = page.evaluate("""() => {
        var labels = new Set();
        var els = document.querySelectorAll('.gen-handle-function .label-text');
        els.forEach(function(el) {
            var text = (el.innerText || '').trim();
            if (text.length > 0) labels.add(text);
        });
        return Array.from(labels).sort();
    }""")
    print(f"  All result action types ({len(all_actions)}):", flush=True)
    for a in all_actions:
        print(f"    - {a}", flush=True)

    # Count total results and images
    totals = page.evaluate("""() => {
        var results = document.querySelectorAll('.result-item');
        var images = document.querySelectorAll('img[src*="static.dzine.ai/stylar_product"]');
        var groups = document.querySelectorAll('.gen-temp-header');
        return {
            result_items: results.length,
            product_images: images.length,
            result_groups: groups.length,
        };
    }""")
    print(f"\n  Totals: {totals}", flush=True)

    print(f"\n\n===== PHASE 76 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
