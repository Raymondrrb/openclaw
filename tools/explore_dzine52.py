"""Phase 52: Txt2Img active panel — Face Match, Color Match, Advanced.

From P51:
- Txt2Img showed intro card "Creates an image from a text description" — NOT active panel
- Face Match/Color Match/Advanced exist in DOM at (0,0) — in hidden panels
- Need to click the Txt2Img intro card to enter the active editing state
- Insert Character: Ray selected, Auto mask, Character Action & Scene prompt

Goals:
1. Click Txt2Img intro card → enter active panel
2. Scroll to Face Match NEW, toggle it, explore upload/strength UI
3. Scroll to Color Match, toggle it, explore UI
4. Scroll to Advanced, expand it, find seed/negative prompt
5. Map the complete Txt2Img active panel from top to bottom
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


def dump_panel(page, label, x_min, x_max, y_min, y_max, limit=50):
    """Dump unique text elements in a region."""
    items = page.evaluate(f"""() => {{
        var items = [];
        for (const el of document.querySelectorAll('*')) {{
            var r = el.getBoundingClientRect();
            if (r.x >= {x_min} && r.x <= {x_max} && r.y >= {y_min} && r.y <= {y_max}
                && r.width > 8 && r.height > 5 && r.width < 400
                && !['path','line','circle','g','svg','defs','rect','polygon','clippath','HTML','BODY','HEAD','SCRIPT','STYLE'].includes(el.tagName.toLowerCase())) {{
                var text = (el.innerText || '').trim();
                if (text.length > 0 && text.length < 60) {{
                    var cursor = window.getComputedStyle(el).cursor;
                    var bg = window.getComputedStyle(el).backgroundColor;
                    items.push({{
                        tag: el.tagName,
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        text: text.substring(0, 45),
                        classes: (el.className || '').toString().substring(0, 35),
                        cursor: cursor !== 'auto' && cursor !== 'default' ? cursor : '',
                        bg: bg && bg !== 'rgba(0, 0, 0, 0)' && bg !== 'transparent' ? bg : '',
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
    print(f"\n  {label} ({len(items)} unique):", flush=True)
    for el in items[:limit]:
        extras = []
        if el['cursor']:
            extras.append(f"cur={el['cursor']}")
        if el['bg']:
            extras.append(f"bg={el['bg'][:30]}")
        extra_str = ' ' + ' '.join(extras) if extras else ''
        print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}>{extra_str} '{el['text'][:40]}'", flush=True)
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
    #  PART 1: ACTIVATE TXT2IMG PANEL (CLICK INTRO CARD)
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 1: ACTIVATE TXT2IMG", flush=True)
    print("=" * 60, flush=True)

    # Click Txt2Img sidebar
    page.mouse.click(40, 197)
    page.wait_for_timeout(2000)
    close_dialogs(page)

    # Check current state: is it showing intro card or active panel?
    panel_state = page.evaluate("""() => {
        // Look for the intro card "Text-to-Image" at (96, 413)
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text === 'Text-to-Image' && r.x > 80 && r.x < 200 && r.y > 50 && r.y < 500
                && r.width > 50 && r.height > 10 && r.height < 50) {
                return {
                    mode: 'intro_card',
                    text: text,
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    tag: el.tagName,
                };
            }
        }
        // Check for active panel indicator (prompt textarea)
        for (const el of document.querySelectorAll('textarea')) {
            var r = el.getBoundingClientRect();
            if (r.x > 60 && r.x < 200 && r.width > 150) {
                return {mode: 'active_panel', x: Math.round(r.x), y: Math.round(r.y)};
            }
        }
        return {mode: 'unknown'};
    }""")
    print(f"  Panel state: {panel_state}", flush=True)

    # If intro card, click it to activate
    if panel_state.get('mode') == 'intro_card':
        print(f"  Clicking intro card at ({panel_state['x']},{panel_state['y']})...", flush=True)
        page.mouse.click(panel_state['x'] + panel_state['w']//2,
                         panel_state['y'] + panel_state['h']//2)
        page.wait_for_timeout(2000)
        close_dialogs(page)
    else:
        # Try clicking the Txt2Img card area directly
        print("  Trying to click Txt2Img card area...", flush=True)
        # From P51 we saw the card at (80,172) 300x304 and (80,397) 300x79
        page.mouse.click(200, 300)
        page.wait_for_timeout(2000)
        close_dialogs(page)

    ss(page, "P52_01_txt2img_activated")

    # Check if now in active mode
    has_prompt = page.evaluate("""() => {
        for (const el of document.querySelectorAll('textarea, [contenteditable="true"]')) {
            var r = el.getBoundingClientRect();
            if (r.x > 60 && r.x < 200 && r.width > 150 && r.y > 50 && r.y < 300) {
                return {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)};
            }
        }
        return null;
    }""")
    print(f"  Prompt textarea: {has_prompt}", flush=True)

    if not has_prompt:
        print("  Still no prompt textarea, trying alternative approaches...", flush=True)

        # Look for any clickable cards or buttons that might open the panel
        cards = page.evaluate("""() => {
            var items = [];
            for (const el of document.querySelectorAll('*')) {
                var r = el.getBoundingClientRect();
                var text = (el.innerText || '').trim();
                var cursor = window.getComputedStyle(el).cursor;
                if (r.x > 60 && r.x < 360 && r.y > 50 && r.y < 600
                    && r.width > 100 && r.height > 30
                    && (cursor === 'pointer' || el.tagName === 'BUTTON' || el.tagName === 'A')) {
                    items.push({
                        text: text.substring(0, 50),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        tag: el.tagName,
                        cursor: cursor,
                        classes: (el.className || '').toString().substring(0, 40),
                    });
                }
            }
            var seen = new Set();
            return items.filter(function(i) {
                var key = i.text.substring(0, 15) + '|' + i.x + '|' + i.y;
                if (seen.has(key)) return false;
                seen.add(key);
                return true;
            }).sort(function(a,b) { return a.y - b.y; }).slice(0, 20);
        }""")
        print(f"  Clickable items ({len(cards)}):", flush=True)
        for c in cards:
            print(f"    ({c['x']},{c['y']}) {c['w']}x{c['h']} <{c['tag']}> cur={c['cursor']} c='{c['classes'][:25]}' '{c['text'][:35]}'", flush=True)

        # Look for "Text to Image" or "Txt2Img" as a button/clickable
        for c in cards:
            if 'Text' in c['text'] and 'Image' in c['text']:
                print(f"  Clicking '{c['text'][:30]}' at ({c['x']},{c['y']})...", flush=True)
                page.mouse.click(c['x'] + c['w']//2, c['y'] + c['h']//2)
                page.wait_for_timeout(2000)
                close_dialogs(page)
                break

        ss(page, "P52_02_after_card_click")

    # Now dump the full panel
    dump_panel(page, "Txt2Img panel top", 60, 360, 50, 500)

    # ============================================================
    #  PART 2: SCROLL AND MAP FULL TXT2IMG PANEL
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 2: FULL TXT2IMG MAP", flush=True)
    print("=" * 60, flush=True)

    # Find the scrollable container
    scroll_info = page.evaluate("""() => {
        var best = null;
        for (const el of document.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            if (r.x >= 60 && r.x < 120 && r.width > 200 && r.width < 350
                && r.height > 200 && el.scrollHeight > el.clientHeight + 10) {
                if (!best || r.height > best.h) {
                    best = {
                        tag: el.tagName,
                        classes: (el.className || '').toString().substring(0, 60),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        scrollH: el.scrollHeight,
                        clientH: el.clientHeight,
                        scrollTop: Math.round(el.scrollTop),
                    };
                }
            }
        }
        return best;
    }""")
    print(f"  Scrollable container: {scroll_info}", flush=True)

    # If no scrollable container found, check all elements
    if not scroll_info:
        any_scroll = page.evaluate("""() => {
            var items = [];
            for (const el of document.querySelectorAll('*')) {
                if (el.scrollHeight > el.clientHeight + 20) {
                    var r = el.getBoundingClientRect();
                    if (r.width > 100 && r.x > 50 && r.x < 400 && r.y > 30 && r.y < 900) {
                        items.push({
                            tag: el.tagName,
                            classes: (el.className || '').toString().substring(0, 60),
                            x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height),
                            scrollH: el.scrollHeight,
                            clientH: el.clientHeight,
                        });
                    }
                }
            }
            return items.sort(function(a,b) { return b.h - a.h; }).slice(0, 5);
        }""")
        print(f"  Any scrollable ({len(any_scroll)}):", flush=True)
        for s in any_scroll:
            print(f"    ({s['x']},{s['y']}) {s['w']}x{s['h']} scrollH={s['scrollH']} clientH={s['clientH']} <{s['tag']}> c='{s['classes'][:40]}'", flush=True)

    # Check if there's a panel header like "Text to Image" that indicates active mode
    header = page.evaluate("""() => {
        for (const el of document.querySelectorAll('.gen-config-header, h5, .title')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (r.x > 60 && r.x < 200 && r.y > 40 && r.y < 100 && text.length > 3) {
                return {text: text.substring(0, 30), x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height)};
            }
        }
        return null;
    }""")
    print(f"\n  Panel header: {header}", flush=True)

    # If we're still not in the active panel, let's try double-clicking the sidebar icon
    if not header or 'Text' not in (header.get('text', '')):
        print("\n  Not in active panel. Trying panel toggle technique...", flush=True)
        # Click Character first, then Txt2Img
        page.mouse.click(40, 306)  # Character sidebar
        page.wait_for_timeout(1000)
        page.mouse.click(40, 197)  # Txt2Img sidebar
        page.wait_for_timeout(2000)
        close_dialogs(page)

        header = page.evaluate("""() => {
            for (const el of document.querySelectorAll('.gen-config-header, h5, .title')) {
                var text = (el.innerText || '').trim();
                var r = el.getBoundingClientRect();
                if (r.x > 60 && r.x < 200 && r.y > 40 && r.y < 100 && text.length > 3) {
                    return {text: text.substring(0, 30), x: Math.round(r.x), y: Math.round(r.y)};
                }
            }
            return null;
        }""")
        print(f"  After toggle: {header}", flush=True)

    # Now try to find the full panel content - look for model name, prompt area, etc.
    model_name = page.evaluate("""() => {
        var btn = document.querySelector('button.style');
        if (btn && btn.getBoundingClientRect().width > 0) {
            return {
                text: (btn.innerText || '').trim().substring(0, 30),
                x: Math.round(btn.getBoundingClientRect().x),
                y: Math.round(btn.getBoundingClientRect().y),
            };
        }
        return null;
    }""")
    print(f"  Model button: {model_name}", flush=True)

    # Full dump of everything visible in the left panel area
    dump_panel(page, "Left panel complete", 60, 370, 40, 900, limit=60)

    ss(page, "P52_03_full_panel")

    # ============================================================
    #  PART 3: SCROLL DOWN TO FIND FACE MATCH
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 3: SCROLL TO FIND FEATURES", flush=True)
    print("=" * 60, flush=True)

    # Use mouse wheel over the panel area
    page.mouse.move(200, 400)
    for i in range(8):
        page.mouse.wheel(0, 200)
        page.wait_for_timeout(300)

        # Check for Face Match appearance
        fm = page.evaluate("""() => {
            for (const el of document.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                var r = el.getBoundingClientRect();
                if (text === 'Face Match' && r.x > 60 && r.x < 360 && r.y > 0 && r.y < 900 && r.width > 0) {
                    return {text: text, x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width)};
                }
            }
            return null;
        }""")
        if fm:
            print(f"  Found Face Match after {i+1} scrolls: {fm}", flush=True)
            break
        print(f"  scroll {i+1}: Face Match not visible yet", flush=True)

    # Dump current view after scrolling
    dump_panel(page, "After scrolling", 60, 370, 40, 900, limit=60)
    ss(page, "P52_04_scrolled")

    # ============================================================
    #  PART 4: FACE MATCH TOGGLE
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 4: FACE MATCH", flush=True)
    print("=" * 60, flush=True)

    # Find Face Match label and toggle
    fm_info = page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if ((text === 'Face Match' || text === 'Face Match NEW' || text === 'Face MatchNEW')
                && r.x > 60 && r.x < 360 && r.y > 0 && r.y < 900 && r.width > 50) {
                // Find nearest toggle
                var parent = el;
                for (var p = 0; p < 5 && parent; p++) {
                    var switches = parent.querySelectorAll('button');
                    for (var i = 0; i < switches.length; i++) {
                        var sw = switches[i];
                        var sr = sw.getBoundingClientRect();
                        var classes = (sw.className || '').toString();
                        if ((classes.includes('switch') || classes.includes('toggle'))
                            && sr.width > 25 && sr.width < 55 && Math.abs(sr.y - r.y) < 30) {
                            var bg = window.getComputedStyle(sw).backgroundColor;
                            return {
                                label_text: text,
                                label_x: Math.round(r.x), label_y: Math.round(r.y),
                                toggle_x: Math.round(sr.x + sr.width/2),
                                toggle_y: Math.round(sr.y + sr.height/2),
                                toggle_bg: bg,
                                toggle_classes: classes.substring(0, 40),
                            };
                        }
                    }
                    parent = parent.parentElement;
                }
                return {label_text: text, label_x: Math.round(r.x), label_y: Math.round(r.y),
                        toggle_x: 0, toggle_y: 0, toggle_bg: '', toggle_classes: 'NOT FOUND'};
            }
        }
        return null;
    }""")
    print(f"  Face Match info: {fm_info}", flush=True)

    if fm_info and fm_info['toggle_x'] > 0:
        # Toggle ON
        print(f"  Toggling Face Match ON at ({fm_info['toggle_x']},{fm_info['toggle_y']})...", flush=True)
        page.mouse.click(fm_info['toggle_x'], fm_info['toggle_y'])
        page.wait_for_timeout(2000)
        close_dialogs(page)

        ss(page, "P52_05_face_match_on")

        # Dump the expanded area
        dump_panel(page, "Face Match expanded", 60, 370, fm_info['label_y'] - 20, fm_info['label_y'] + 250)

        # Look for pick-image button (same pattern as CC reference)
        pick_btns = page.evaluate("""() => {
            var items = [];
            for (const btn of document.querySelectorAll('button')) {
                var classes = (btn.className || '').toString();
                var r = btn.getBoundingClientRect();
                if (r.x > 60 && r.x < 360 && r.width > 30 && r.y > 0 && r.y < 900
                    && (classes.includes('pick-image') || classes.includes('pick'))) {
                    var img = btn.querySelector('.image');
                    items.push({
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        classes: classes.substring(0, 40),
                        hasEmpty: img ? img.classList.contains('empty') : 'no-img',
                    });
                }
            }
            return items.sort(function(a,b) { return a.y - b.y; });
        }""")
        print(f"\n  Pick-image buttons ({len(pick_btns)}):", flush=True)
        for b in pick_btns:
            print(f"    ({b['x']},{b['y']}) {b['w']}x{b['h']} c='{b['classes'][:30]}' empty={b['hasEmpty']}", flush=True)

        # Test file chooser on pick-image for Face Match
        for b in pick_btns:
            if b['y'] > fm_info['label_y'] and b['y'] < fm_info['label_y'] + 150:
                print(f"\n  Testing file chooser on Face Match pick-image at ({b['x']},{b['y']})...", flush=True)
                page.mouse.click(b['x'] + b['w']//2, b['y'] + b['h']//2)
                page.wait_for_timeout(1500)

                # Check if pick-panel dialog opened
                dialog = page.evaluate("""() => {
                    var panel = document.querySelector('.pick-panel');
                    if (!panel) return null;
                    var r = panel.getBoundingClientRect();
                    return {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)};
                }""")
                print(f"  Pick panel dialog: {dialog}", flush=True)

                if dialog:
                    # Test file chooser on the upload button
                    upload_pos = page.evaluate("""() => {
                        var panel = document.querySelector('.pick-panel');
                        if (!panel) return null;
                        var btn = panel.querySelector('button.upload');
                        if (!btn) return null;
                        var r = btn.getBoundingClientRect();
                        return {x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)};
                    }""")
                    if upload_pos:
                        print(f"  Upload button at ({upload_pos['x']},{upload_pos['y']})", flush=True)
                        try:
                            with page.expect_file_chooser(timeout=3000) as fc_info:
                                page.mouse.click(upload_pos['x'], upload_pos['y'])
                            fc = fc_info.value
                            print(f"  *** FACE MATCH FILE CHOOSER WORKS! *** Multiple={fc.is_multiple}", flush=True)
                            fc.set_files([])  # Cancel
                        except Exception as e:
                            print(f"  No file chooser: {e}", flush=True)

                    # Close dialog
                    page.keyboard.press("Escape")
                    page.wait_for_timeout(500)
                break

        # Toggle OFF
        page.mouse.click(fm_info['toggle_x'], fm_info['toggle_y'])
        page.wait_for_timeout(1000)

    # ============================================================
    #  PART 5: COLOR MATCH
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 5: COLOR MATCH", flush=True)
    print("=" * 60, flush=True)

    cm_info = page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text === 'Color Match' && r.x > 60 && r.x < 360 && r.y > 0 && r.y < 900 && r.width > 50) {
                var parent = el;
                for (var p = 0; p < 5 && parent; p++) {
                    var switches = parent.querySelectorAll('button');
                    for (var i = 0; i < switches.length; i++) {
                        var sw = switches[i];
                        var sr = sw.getBoundingClientRect();
                        var classes = (sw.className || '').toString();
                        if ((classes.includes('switch') || classes.includes('toggle'))
                            && sr.width > 25 && sr.width < 55 && Math.abs(sr.y - r.y) < 30) {
                            return {
                                label_y: Math.round(r.y),
                                toggle_x: Math.round(sr.x + sr.width/2),
                                toggle_y: Math.round(sr.y + sr.height/2),
                                toggle_bg: window.getComputedStyle(sw).backgroundColor,
                            };
                        }
                    }
                    parent = parent.parentElement;
                }
                return {label_y: Math.round(r.y), toggle_x: 0, toggle_y: 0};
            }
        }
        return null;
    }""")
    print(f"  Color Match: {cm_info}", flush=True)

    if cm_info and cm_info['toggle_x'] > 0:
        page.mouse.click(cm_info['toggle_x'], cm_info['toggle_y'])
        page.wait_for_timeout(2000)
        close_dialogs(page)

        ss(page, "P52_06_color_match_on")
        dump_panel(page, "Color Match expanded", 60, 370, cm_info['label_y'] - 20, cm_info['label_y'] + 250)

        # Look for color picker, palette, or upload area
        color_els = page.evaluate("""() => {
            var items = [];
            for (const el of document.querySelectorAll('*')) {
                var r = el.getBoundingClientRect();
                var classes = (el.className || '').toString();
                if (r.x > 60 && r.x < 360 && r.y > 0 && r.y < 900 && r.width > 20
                    && (classes.includes('color') || classes.includes('pick')
                        || classes.includes('palette') || classes.includes('swatch'))) {
                    items.push({
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        tag: el.tagName,
                        classes: classes.substring(0, 50),
                    });
                }
            }
            return items.sort(function(a,b) { return a.y - b.y; }).slice(0, 15);
        }""")
        print(f"\n  Color elements ({len(color_els)}):", flush=True)
        for el in color_els:
            print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> c='{el['classes'][:40]}'", flush=True)

        # Toggle OFF
        page.mouse.click(cm_info['toggle_x'], cm_info['toggle_y'])
        page.wait_for_timeout(1000)

    # ============================================================
    #  PART 6: ADVANCED SECTION
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 6: ADVANCED", flush=True)
    print("=" * 60, flush=True)

    # Scroll more to find Advanced
    page.mouse.move(200, 500)
    for i in range(5):
        page.mouse.wheel(0, 200)
        page.wait_for_timeout(300)

    adv = page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text === 'Advanced' && r.x > 60 && r.x < 360 && r.y > 0 && r.y < 900 && r.width > 80) {
                return {
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    tag: el.tagName,
                    classes: (el.className || '').toString().substring(0, 40),
                };
            }
        }
        return null;
    }""")
    print(f"  Advanced: {adv}", flush=True)

    if adv:
        page.mouse.click(adv['x'] + adv['w']//2, adv['y'] + adv['h']//2)
        page.wait_for_timeout(1500)

        # Scroll down more to see expanded content
        page.mouse.move(200, 600)
        page.mouse.wheel(0, 200)
        page.wait_for_timeout(500)

        ss(page, "P52_07_advanced")
        dump_panel(page, "Advanced expanded", 60, 370, adv['y'] - 20, 900)

        # Check for seed input, negative prompt textarea
        inputs = page.evaluate("""() => {
            var items = [];
            for (const el of document.querySelectorAll('input, textarea')) {
                var r = el.getBoundingClientRect();
                if (r.x > 60 && r.x < 360 && r.width > 30 && r.y > 0 && r.y < 900) {
                    items.push({
                        tag: el.tagName,
                        type: el.type || '',
                        placeholder: el.placeholder || '',
                        value: (el.value || '').substring(0, 30),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                    });
                }
            }
            return items.sort(function(a,b) { return a.y - b.y; });
        }""")
        print(f"\n  Inputs in panel ({len(inputs)}):", flush=True)
        for inp in inputs:
            print(f"    ({inp['x']},{inp['y']}) {inp['w']}x{inp['h']} <{inp['tag']}> type={inp['type']} ph='{inp['placeholder'][:30]}' val='{inp['value'][:20]}'", flush=True)
    else:
        print("  Advanced NOT found", flush=True)

    ss(page, "P52_08_final")
    print(f"\n\n===== PHASE 52 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
