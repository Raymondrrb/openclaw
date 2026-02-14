"""Phase 46: Explore CC Style toggle, Pose mode, and Img2Img reference workflow.

From P45: CC panel fully mapped. Now explore:
1. CC Style toggle — what happens when turned ON
2. CC Pose mode — what controls are available
3. Img2Img workflow — how it uses canvas layers as reference
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


def open_cc_panel(page):
    """Open CC panel with Ray selected."""
    page.mouse.click(40, 197)  # Txt2Img first
    page.wait_for_timeout(1000)
    page.mouse.click(40, 306)  # Character
    page.wait_for_timeout(3000)
    close_dialogs(page)

    page.evaluate("""() => {
        for (const btn of document.querySelectorAll('button')) {
            if ((btn.innerText || '').trim().includes('Generate Images')) { btn.click(); return; }
        }
    }""")
    page.wait_for_timeout(2000)

    page.evaluate("""() => {
        for (const el of document.querySelectorAll('button')) {
            if ((el.innerText || '').trim() === 'Ray') { el.click(); return; }
        }
    }""")
    page.wait_for_timeout(2000)


def dump_cc_panel(page, label):
    """Dump all CC panel elements between y=550 and y=940."""
    elements = page.evaluate("""() => {
        var items = [];
        for (const el of document.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            if (r.x > 50 && r.x < 360 && r.y > 550 && r.y < 940
                && r.width > 10 && r.height > 5 && r.width < 350
                && !['path','line','circle','g','svg','defs','rect','polygon'].includes(el.tagName.toLowerCase())) {
                var text = (el.innerText || '').trim();
                var bg = window.getComputedStyle(el).backgroundImage;
                items.push({
                    tag: el.tagName,
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    text: text.substring(0, 35),
                    classes: (el.className || '').toString().substring(0, 35),
                    hasBg: bg !== 'none' ? 'BG' : '',
                });
            }
        }
        var seen = new Set();
        return items.filter(function(i) {
            var key = i.tag + '|' + i.x + '|' + i.y + '|' + i.w + '|' + i.h;
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
        }).sort(function(a,b) { return a.y - b.y; });
    }""")
    print(f"\n  {label} ({len(elements)} elements):", flush=True)
    for el in elements[:60]:
        bg_str = f' {el["hasBg"]}' if el['hasBg'] else ''
        print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> c='{el['classes'][:25]}'{bg_str} '{el['text'][:25]}'", flush=True)
    return elements


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
    #  PART 1: CC STYLE TOGGLE
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 1: CC STYLE TOGGLE", flush=True)
    print("=" * 60, flush=True)

    open_cc_panel(page)

    # Check current Style toggle state
    style_state = page.evaluate("""() => {
        for (const btn of document.querySelectorAll('button.switch')) {
            var r = btn.getBoundingClientRect();
            // Style toggle is at y~763
            if (r.x > 280 && r.y > 750 && r.y < 780) {
                var bg = window.getComputedStyle(btn).backgroundColor;
                return {
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    bg: bg,
                    isOn: bg.includes('255') || bg.includes('239'),  // yellow when on
                };
            }
        }
        return null;
    }""")
    print(f"  Style toggle state: {style_state}", flush=True)
    ss(page, "P46_01_style_off")

    # Turn Style ON
    if style_state:
        print(f"  Clicking Style toggle at ({style_state['x']}, {style_state['y']})...", flush=True)
        page.mouse.click(style_state['x'] + style_state['w'] // 2,
                         style_state['y'] + style_state['h'] // 2)
        page.wait_for_timeout(2000)

        # Check state after toggle
        style_after = page.evaluate("""() => {
            for (const btn of document.querySelectorAll('button.switch')) {
                var r = btn.getBoundingClientRect();
                if (r.x > 280 && r.y > 750 && r.y < 780) {
                    return {bg: window.getComputedStyle(btn).backgroundColor};
                }
            }
            return null;
        }""")
        print(f"  Style after toggle: {style_after}", flush=True)

        ss(page, "P46_02_style_on")
        dump_cc_panel(page, "CC Panel with Style ON")

        # Check what model/style is shown
        style_info = page.evaluate("""() => {
            for (const el of document.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                var r = el.getBoundingClientRect();
                // Look for model name near the style section
                if (r.x > 50 && r.x < 360 && r.y > 770 && r.y < 830
                    && text.length > 3 && text.length < 40
                    && !text.includes('Non-Explicit') && !text.includes('Generate')) {
                    return {
                        text: text,
                        x: Math.round(r.x), y: Math.round(r.y),
                        tag: el.tagName,
                        classes: (el.className || '').toString().substring(0, 40),
                    };
                }
            }
            return null;
        }""")
        print(f"  Style model info: {style_info}", flush=True)

        # Turn Style back OFF
        page.mouse.click(style_state['x'] + style_state['w'] // 2,
                         style_state['y'] + style_state['h'] // 2)
        page.wait_for_timeout(1000)

    # ============================================================
    #  PART 2: CC POSE MODE
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 2: CC POSE MODE", flush=True)
    print("=" * 60, flush=True)

    # Click Pose button
    pose_clicked = page.evaluate("""() => {
        for (const btn of document.querySelectorAll('button')) {
            var text = (btn.innerText || '').trim();
            var r = btn.getBoundingClientRect();
            if (text === 'Pose' && r.width > 30 && r.x > 50 && r.x < 350 && r.y > 500) {
                btn.click(); return true;
            }
        }
        return false;
    }""")
    print(f"  Pose clicked: {pose_clicked}", flush=True)
    page.wait_for_timeout(2000)

    ss(page, "P46_03_pose_mode")
    dump_cc_panel(page, "CC Panel in Pose Mode")

    # Check for pose-specific controls
    pose_controls = page.evaluate("""() => {
        var items = [];
        for (const el of document.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            var text = (el.innerText || '').trim();
            if (r.x > 50 && r.x < 360 && r.y > 580 && r.y < 700
                && r.width > 20 && r.height > 10
                && text.length > 0 && text.length < 40) {
                items.push({
                    tag: el.tagName,
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
    print(f"\n  Pose-specific controls ({len(pose_controls)}):", flush=True)
    for c in pose_controls:
        print(f"    ({c['x']},{c['y']}) {c['w']}x{c['h']} <{c['tag']}> c='{c['classes'][:25]}' '{c['text'][:30]}'", flush=True)

    # Switch back to Camera mode
    page.evaluate("""() => {
        for (const btn of document.querySelectorAll('button')) {
            var text = (btn.innerText || '').trim();
            var r = btn.getBoundingClientRect();
            if (text === 'Camera' && r.width > 30 && r.x > 50 && r.x < 350 && r.y > 500) {
                btn.click(); return;
            }
        }
    }""")
    page.wait_for_timeout(1000)

    # ============================================================
    #  PART 3: IMG2IMG PANEL
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 3: IMG2IMG PANEL", flush=True)
    print("=" * 60, flush=True)

    # Switch to Img2Img
    page.mouse.click(40, 252)
    page.wait_for_timeout(3000)
    close_dialogs(page)

    ss(page, "P46_04_img2img_panel")

    # Full panel dump
    img2img_elements = page.evaluate("""() => {
        var items = [];
        for (const el of document.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            if (r.x > 50 && r.x < 360 && r.y > 50 && r.y < 900
                && r.width > 10 && r.height > 5 && r.width < 350
                && !['path','line','circle','g','svg','defs','rect','polygon'].includes(el.tagName.toLowerCase())) {
                var text = (el.innerText || '').trim();
                var bg = window.getComputedStyle(el).backgroundImage;
                var cursor = window.getComputedStyle(el).cursor;
                if (text.length < 60) {
                    items.push({
                        tag: el.tagName,
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        text: text.substring(0, 35),
                        classes: (el.className || '').toString().substring(0, 35),
                        hasBg: bg !== 'none' ? 'BG' : '',
                        cursor: cursor !== 'auto' && cursor !== 'default' ? cursor : '',
                    });
                }
            }
        }
        var seen = new Set();
        return items.filter(function(i) {
            var key = i.tag + '|' + i.x + '|' + i.y + '|' + i.w + '|' + i.h;
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
        }).sort(function(a,b) { return a.y - b.y; });
    }""")
    print(f"\n  Img2Img panel elements ({len(img2img_elements)}):", flush=True)
    for el in img2img_elements[:60]:
        extras = []
        if el['hasBg']: extras.append('BG')
        if el['cursor']: extras.append(f"cur={el['cursor']}")
        extra_str = ' ' + ' '.join(extras) if extras else ''
        print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> c='{el['classes'][:25]}'{extra_str} '{el['text'][:25]}'", flush=True)

    # Check for reference/input image area
    ref_area = page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if ((text.includes('Select') || text.includes('Upload') || text.includes('Pick')
                 || text.includes('Drop') || text.includes('reference'))
                && r.x > 50 && r.x < 360 && r.width > 100) {
                return {
                    text: text.substring(0, 80),
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    tag: el.tagName,
                    classes: (el.className || '').toString().substring(0, 40),
                };
            }
        }
        return null;
    }""")
    print(f"\n  Reference/input area: {ref_area}", flush=True)

    # Check Img2Img control modes
    control_modes = page.evaluate("""() => {
        var items = [];
        for (const btn of document.querySelectorAll('button.options')) {
            var r = btn.getBoundingClientRect();
            var text = (btn.innerText || '').trim();
            if (r.x > 50 && r.x < 360 && r.y > 200 && r.y < 600) {
                items.push({
                    text: text,
                    x: Math.round(r.x), y: Math.round(r.y),
                    selected: (btn.className || '').toString().includes('selected'),
                });
            }
        }
        return items;
    }""")
    print(f"\n  Img2Img control modes ({len(control_modes)}):", flush=True)
    for m in control_modes:
        sel = ' (SELECTED)' if m['selected'] else ''
        print(f"    ({m['x']},{m['y']}) '{m['text']}'{sel}", flush=True)

    # ============================================================
    #  PART 4: ENHANCE & UPSCALE PANEL
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 4: ENHANCE & UPSCALE", flush=True)
    print("=" * 60, flush=True)

    page.mouse.click(40, 627)
    page.wait_for_timeout(2000)
    close_dialogs(page)

    ss(page, "P46_05_enhance_panel")

    enhance_elements = page.evaluate("""() => {
        var items = [];
        for (const el of document.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            if (r.x > 50 && r.x < 360 && r.y > 70 && r.y < 600
                && r.width > 10 && r.height > 5 && r.width < 350
                && !['path','line','circle','g','svg','defs','rect','polygon'].includes(el.tagName.toLowerCase())) {
                var text = (el.innerText || '').trim();
                if (text.length < 50 && text.length > 0) {
                    items.push({
                        tag: el.tagName,
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        text: text.substring(0, 30),
                        classes: (el.className || '').toString().substring(0, 30),
                    });
                }
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
    print(f"\n  Enhance panel elements ({len(enhance_elements)}):", flush=True)
    for el in enhance_elements[:30]:
        print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> c='{el['classes'][:20]}' '{el['text']}'", flush=True)

    # ============================================================
    #  PART 5: FACE SWAP / EXPRESSION EDIT ACCESS
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 5: IMAGE EDITOR — FACE KIT", flush=True)
    print("=" * 60, flush=True)

    page.mouse.click(40, 698)
    page.wait_for_timeout(2000)
    close_dialogs(page)

    ss(page, "P46_06_image_editor")

    # Full dump of Image Editor panel
    editor_elements = page.evaluate("""() => {
        var items = [];
        for (const el of document.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            if (r.x > 50 && r.x < 360 && r.y > 70 && r.y < 900
                && r.width > 20 && r.height > 10 && r.width < 350
                && !['path','line','circle','g','svg','defs','rect','polygon'].includes(el.tagName.toLowerCase())) {
                var text = (el.innerText || '').trim();
                var cursor = window.getComputedStyle(el).cursor;
                if (text.length > 0 && text.length < 40) {
                    items.push({
                        tag: el.tagName,
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        text: text.substring(0, 30),
                        classes: (el.className || '').toString().substring(0, 30),
                        cursor: cursor !== 'auto' && cursor !== 'default' ? cursor : '',
                    });
                }
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
    print(f"\n  Image Editor elements ({len(editor_elements)}):", flush=True)
    for el in editor_elements[:40]:
        cur = f' cur={el["cursor"]}' if el['cursor'] else ''
        print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> c='{el['classes'][:20]}'{cur} '{el['text']}'", flush=True)

    # Check for scrollable content
    scroll_info = page.evaluate("""() => {
        for (const el of document.querySelectorAll('.left-panel-content, .panel-content, [class*="scroll"]')) {
            var r = el.getBoundingClientRect();
            if (r.x > 50 && r.x < 360 && r.width > 200) {
                return {
                    scrollTop: Math.round(el.scrollTop),
                    scrollHeight: Math.round(el.scrollHeight),
                    clientHeight: Math.round(el.clientHeight),
                    classes: (el.className || '').toString().substring(0, 40),
                };
            }
        }
        return null;
    }""")
    print(f"\n  Scroll info: {scroll_info}", flush=True)

    # Scroll down to see Face Kit section
    if scroll_info and scroll_info.get('scrollHeight', 0) > scroll_info.get('clientHeight', 0):
        print("  Scrolling panel to reveal Face Kit...", flush=True)
        page.evaluate("""() => {
            for (const el of document.querySelectorAll('.left-panel-content, .panel-content, [class*="scroll"]')) {
                var r = el.getBoundingClientRect();
                if (r.x > 50 && r.x < 360 && r.width > 200) {
                    el.scrollTop = el.scrollHeight;
                    return true;
                }
            }
            return false;
        }""")
        page.wait_for_timeout(1000)

        ss(page, "P46_07_image_editor_scrolled")

        # Dump after scroll
        after_scroll = page.evaluate("""() => {
            var items = [];
            for (const el of document.querySelectorAll('*')) {
                var r = el.getBoundingClientRect();
                if (r.x > 50 && r.x < 360 && r.y > 300 && r.y < 900
                    && r.width > 20 && r.height > 10 && r.width < 350
                    && !['path','line','circle','g','svg','defs','rect','polygon'].includes(el.tagName.toLowerCase())) {
                    var text = (el.innerText || '').trim();
                    if (text.length > 0 && text.length < 40) {
                        items.push({
                            tag: el.tagName,
                            x: Math.round(r.x), y: Math.round(r.y),
                            text: text.substring(0, 30),
                        });
                    }
                }
            }
            var seen = new Set();
            return items.filter(function(i) {
                var key = i.text + '|' + i.y;
                if (seen.has(key)) return false;
                seen.add(key);
                return true;
            }).sort(function(a,b) { return a.y - b.y; });
        }""")
        print(f"\n  After scroll ({len(after_scroll)}):", flush=True)
        for el in after_scroll[:20]:
            print(f"    ({el['x']},{el['y']}) '{el['text']}'", flush=True)

    ss(page, "P46_08_final")
    print(f"\n\n===== PHASE 46 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
