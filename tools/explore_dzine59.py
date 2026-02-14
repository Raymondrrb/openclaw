"""Phase 59: CC Style toggle detail, Enhance & Upscale active mode, Prompt Improver.

From P58:
- CC full panel mapped: Style NEW toggle at y=771 (below fold, requires scroll)
- Style toggle NOT yet tested — need to toggle ON and see what model/options appear
- Generate 360° Video mapped (6 credits, simple panel)
- Motion Control fully mapped (Kling 2.6, 28 video credits)
- Image Editor with Product Background confirmed

Goals:
1. Scroll CC panel, toggle Style ON, document what appears (model picker? style grid?)
2. Test Enhance & Upscale in active use (place image, select layer, click tool)
3. Test Prompt Improver in Txt2Img
4. Map keyboard shortcuts and canvas interaction (zoom, pan, select)
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


def dump_region(page, label, x_min, x_max, y_min, y_max, limit=60):
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


def open_cc_panel_with_ray(page):
    """Open CC Generate Images panel with Ray selected."""
    # Open Character menu
    page.mouse.dblclick(40, 306)
    page.wait_for_timeout(2000)
    close_dialogs(page)

    # Click "Generate Images" card
    page.evaluate("""() => {
        // Find clickable elements with "Generate Images" text
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            // Look for the specific card — it has text starting with "Generate Images"
            // and subtitle "With your character", positioned in the menu area
            if (text === 'Generate Images' && r.x > 60 && r.y > 80 && r.y < 250
                && r.height < 50) {
                el.click(); return true;
            }
        }
        // Fallback: look for the card container with thumbnails
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text.startsWith('Generate Images') && text.includes('With your')
                && r.x > 60 && r.width > 100 && r.height > 30 && r.height < 100) {
                el.click(); return true;
            }
        }
        return false;
    }""")
    page.wait_for_timeout(2000)
    close_dialogs(page)

    # Select Ray if character selection appears
    page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            if (text === 'Ray' && el.tagName === 'BUTTON') {
                el.click(); return true;
            }
        }
        return false;
    }""")
    page.wait_for_timeout(2000)
    close_dialogs(page)


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

    open_cc_panel_with_ray(page)

    # Verify we're in CC panel
    header = page.evaluate("""() => {
        for (const el of document.querySelectorAll('.gen-config-header')) {
            var text = (el.innerText || '').trim();
            if (text.includes('Consistent')) return text;
        }
        return null;
    }""")
    print(f"  Header: {header}", flush=True)

    if not header:
        print("  CC panel not active, trying alternative...", flush=True)
        # Alternative: the panel might already be showing from previous run
        header = page.evaluate("""() => {
            for (const el of document.querySelectorAll('.gen-config-header')) {
                return (el.innerText || '').trim().substring(0, 30);
            }
            return null;
        }""")
        print(f"  Current header: {header}", flush=True)

    ss(page, "P59_01_cc_panel")

    # Scroll to bottom of CC panel to find Style toggle
    scroll_result = page.evaluate("""() => {
        var panels = document.querySelectorAll('.gen-config-body, .gen-config');
        for (var p of panels) {
            if (p.scrollHeight > p.clientHeight + 10) {
                p.scrollBy(0, 400);
                return {scrollH: p.scrollHeight, clientH: p.clientHeight, scrollTop: p.scrollTop};
            }
        }
        return null;
    }""")
    print(f"  Scroll result: {scroll_result}", flush=True)
    page.wait_for_timeout(500)

    ss(page, "P59_02_cc_scrolled")

    # Find the Style switch button after scroll
    style_switch = page.evaluate("""() => {
        // Find "Style" label with NEW badge
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text === 'Style' && r.x > 60 && r.x < 200 && r.y > 0 && r.y < 900
                && r.width > 20 && r.height > 5) {
                // Search siblings/parent for switch button
                var parent = el;
                for (var p = 0; p < 6 && parent; p++) {
                    var switches = parent.querySelectorAll('button');
                    for (var s of switches) {
                        var sc = (s.className || '').toString();
                        var sr = s.getBoundingClientRect();
                        if (sc.includes('switch') && sr.width > 25 && sr.width < 55
                            && Math.abs(sr.y - r.y) < 20) {
                            return {
                                x: Math.round(sr.x + sr.width/2),
                                y: Math.round(sr.y + sr.height/2),
                                w: Math.round(sr.width),
                                classes: sc.substring(0, 40),
                                labelY: Math.round(r.y),
                            };
                        }
                    }
                    parent = parent.parentElement;
                }
            }
        }
        return null;
    }""")
    print(f"  Style switch: {style_switch}", flush=True)

    if style_switch:
        print(f"\n  >>> Clicking Style switch at ({style_switch['x']},{style_switch['y']})...", flush=True)
        page.mouse.click(style_switch['x'], style_switch['y'])
        page.wait_for_timeout(2000)
        close_dialogs(page)

        ss(page, "P59_03_style_on")

        # Dump what appeared (the panel may expand or show new elements)
        dump_region(page, "CC panel after Style ON", 60, 400, 0, 900)

        # Specifically look for model/style picker that appeared
        style_new = page.evaluate("""() => {
            var items = [];
            for (const el of document.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                var r = el.getBoundingClientRect();
                var classes = (el.className || '').toString();
                if (r.x > 60 && r.x < 400 && r.width > 20 && r.height > 5
                    && text.length > 1 && text.length < 60
                    && (classes.includes('style') || classes.includes('model')
                        || text.includes('Render') || text.includes('Realistic')
                        || text.includes('3D') || text.includes('Dzine')
                        || text.includes('Nano') || text.includes('FLUX')
                        || text.includes('Anime') || text.includes('GPT'))) {
                    items.push({
                        text: text.substring(0, 50),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        tag: el.tagName,
                        classes: classes.substring(0, 30),
                    });
                }
            }
            var seen = new Set();
            return items.filter(function(i) {
                var key = i.text.substring(0,20) + '|' + i.y;
                if (seen.has(key)) return false;
                seen.add(key);
                return true;
            }).sort(function(a,b) { return a.y - b.y; }).slice(0, 20);
        }""")
        print(f"\n  Style-related elements ({len(style_new)}):", flush=True)
        for s in style_new:
            print(f"    ({s['x']},{s['y']}) {s['w']}x{s['h']} <{s['tag']}> c='{s['classes'][:22]}' '{s['text'][:45]}'", flush=True)

        # Check if a model selector button appeared
        model_btn = page.evaluate("""() => {
            var btn = document.querySelector('.c-style button.style');
            if (!btn) return null;
            var r = btn.getBoundingClientRect();
            return {
                text: (btn.innerText || '').trim().substring(0, 40),
                x: Math.round(r.x), y: Math.round(r.y),
                w: Math.round(r.width), h: Math.round(r.height),
            };
        }""")
        print(f"\n  Model button (c-style): {model_btn}", flush=True)

        # Check for new config-param sections
        new_params = page.evaluate("""() => {
            var items = [];
            for (const el of document.querySelectorAll('.config-param')) {
                var text = (el.innerText || '').trim();
                var r = el.getBoundingClientRect();
                if (r.x > 60 && r.width > 100) {
                    items.push({
                        text: text.substring(0, 80),
                        x: Math.round(r.x), y: Math.round(r.y),
                        h: Math.round(r.height),
                    });
                }
            }
            return items.sort(function(a,b) { return a.y - b.y; });
        }""")
        print(f"\n  Config params ({len(new_params)}):", flush=True)
        for p in new_params:
            print(f"    y={p['y']} h={p['h']} '{p['text'][:70]}'", flush=True)

        # Toggle Style OFF
        page.mouse.click(style_switch['x'], style_switch['y'])
        page.wait_for_timeout(500)
        print("  Style toggled OFF", flush=True)
    else:
        print("  Style switch not found! Checking all switches...", flush=True)
        all_switches = page.evaluate("""() => {
            var items = [];
            for (const btn of document.querySelectorAll('button')) {
                var classes = (btn.className || '').toString();
                if (classes.includes('switch')) {
                    var r = btn.getBoundingClientRect();
                    var parent = btn.parentElement;
                    var label = '';
                    for (var p = 0; p < 3 && parent; p++) {
                        var t = (parent.innerText || '').trim().split('\\n')[0];
                        if (t && t.length < 30) { label = t; break; }
                        parent = parent.parentElement;
                    }
                    items.push({
                        label: label,
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        classes: classes.substring(0, 40),
                        visible: r.width > 10 && r.height > 10,
                    });
                }
            }
            return items.sort(function(a,b) { return a.y - b.y; });
        }""")
        print(f"  All switch buttons ({len(all_switches)}):", flush=True)
        for sw in all_switches:
            vis = "VIS" if sw['visible'] else "hid"
            print(f"    ({sw['x']},{sw['y']}) {sw['w']}x{sw['h']} [{vis}] c='{sw['classes'][:25]}' label='{sw['label'][:25]}'", flush=True)

    # ============================================================
    #  PART 2: PROMPT IMPROVER IN TXT2IMG
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 2: PROMPT IMPROVER", flush=True)
    print("=" * 60, flush=True)

    # Activate Txt2Img
    page.mouse.click(40, 306)  # Character first
    page.wait_for_timeout(300)
    page.mouse.click(40, 197)  # Txt2Img
    page.wait_for_timeout(1500)
    close_dialogs(page)

    # Find Prompt Improver element
    improver = page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text === 'Prompt Improver' && r.x > 60 && r.x < 300 && r.width > 50) {
                // Find the associated switch
                var parent = el;
                for (var p = 0; p < 5 && parent; p++) {
                    var switches = parent.querySelectorAll('button');
                    for (var s of switches) {
                        var sc = (s.className || '').toString();
                        var sr = s.getBoundingClientRect();
                        if (sc.includes('switch') && sr.width > 25 && sr.width < 55) {
                            return {
                                labelX: Math.round(r.x), labelY: Math.round(r.y),
                                switchX: Math.round(sr.x + sr.width/2),
                                switchY: Math.round(sr.y + sr.height/2),
                                switchClasses: sc.substring(0, 40),
                                active: sc.includes('active') || sc.includes('on'),
                            };
                        }
                    }
                    parent = parent.parentElement;
                }
                return {labelX: Math.round(r.x), labelY: Math.round(r.y), noSwitch: true};
            }
        }
        return null;
    }""")
    print(f"  Prompt Improver: {improver}", flush=True)

    if improver and not improver.get('noSwitch'):
        # Check current state
        state = "ON" if improver.get('active') else "OFF"
        print(f"  Current state: {state}", flush=True)

        # Toggle it ON if OFF
        if not improver.get('active'):
            print(f"  Toggling Prompt Improver ON...", flush=True)
            page.mouse.click(improver['switchX'], improver['switchY'])
            page.wait_for_timeout(1000)

            # Check what changed
            after_state = page.evaluate("""() => {
                for (const el of document.querySelectorAll('*')) {
                    var text = (el.innerText || '').trim();
                    if (text === 'Prompt Improver') {
                        var parent = el;
                        for (var p = 0; p < 5 && parent; p++) {
                            var switches = parent.querySelectorAll('button');
                            for (var s of switches) {
                                var sc = (s.className || '').toString();
                                if (sc.includes('switch')) {
                                    return sc.includes('active') || sc.includes('on');
                                }
                            }
                            parent = parent.parentElement;
                        }
                    }
                }
                return null;
            }""")
            print(f"  After toggle: active={after_state}", flush=True)
            ss(page, "P59_04_prompt_improver_on")

            # Toggle back OFF
            page.mouse.click(improver['switchX'], improver['switchY'])
            page.wait_for_timeout(500)

    # ============================================================
    #  PART 3: KEYBOARD SHORTCUTS
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 3: KEYBOARD SHORTCUTS", flush=True)
    print("=" * 60, flush=True)

    # Check if Ctrl+/ or ? opens a shortcut guide
    page.keyboard.press("Escape")  # Make sure nothing is focused
    page.wait_for_timeout(500)

    # Try common shortcut discovery methods
    # Method 1: Look for keyboard shortcut indicator in UI
    shortcuts = page.evaluate("""() => {
        var items = [];
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var title = el.title || '';
            var r = el.getBoundingClientRect();
            if (r.width > 0 && (
                title.includes('Ctrl') || title.includes('⌘') || title.includes('Shift')
                || title.includes('shortcut') || title.includes('hotkey')
                || (text.length < 5 && /^[⌘⌥⇧]/.test(text))
            )) {
                items.push({
                    text: text.substring(0, 30),
                    title: title.substring(0, 60),
                    x: Math.round(r.x), y: Math.round(r.y),
                    tag: el.tagName,
                });
            }
        }
        return items.slice(0, 20);
    }""")
    print(f"  Shortcut hints in UI ({len(shortcuts)}):", flush=True)
    for sc in shortcuts:
        print(f"    ({sc['x']},{sc['y']}) <{sc['tag']}> text='{sc['text']}' title='{sc['title']}'", flush=True)

    # Try Ctrl+K or ? to open shortcuts
    page.keyboard.press("?")
    page.wait_for_timeout(1000)

    # Check for any overlay/modal that appeared
    overlay = page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            var style = window.getComputedStyle(el);
            var z = parseInt(style.zIndex) || 0;
            var r = el.getBoundingClientRect();
            var text = (el.innerText || '').trim();
            if (z > 100 && r.width > 200 && r.height > 100 && text.length > 20) {
                return {
                    text: text.substring(0, 200),
                    z: z,
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                };
            }
        }
        return null;
    }""")
    if overlay:
        print(f"  Overlay appeared (z={overlay['z']}): '{overlay['text'][:100]}'", flush=True)
        ss(page, "P59_05_shortcut_overlay")
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)
    else:
        print("  No shortcut overlay found", flush=True)

    # ============================================================
    #  PART 4: CANVAS TOOLBAR ICONS (TOP BAR TOOLS)
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 4: CANVAS TOP BAR TOOLS", flush=True)
    print("=" * 60, flush=True)

    # Map the top bar tools (between sidebar and right panel)
    top_tools = page.evaluate("""() => {
        var items = [];
        for (const el of document.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            var title = el.title || el.getAttribute('aria-label') || '';
            var text = (el.innerText || '').trim();
            // Top bar tools are in the area y=28-72, x=180-600
            if (r.y > 28 && r.y < 72 && r.x > 150 && r.x < 600
                && r.width > 15 && r.width < 60 && r.height > 15 && r.height < 60
                && (el.tagName === 'BUTTON' || el.tagName === 'DIV' || title)
                && (title || text)) {
                items.push({
                    text: text.substring(0, 20) || title.substring(0, 30),
                    title: title.substring(0, 40),
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    tag: el.tagName,
                    classes: (el.className || '').toString().substring(0, 30),
                });
            }
        }
        var seen = new Set();
        return items.filter(function(i) {
            var key = Math.round(i.x/10) + '|' + Math.round(i.y/10);
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
        }).sort(function(a,b) { return a.x - b.x; }).slice(0, 30);
    }""")
    print(f"  Top bar tools ({len(top_tools)}):", flush=True)
    for t in top_tools:
        print(f"    ({t['x']},{t['y']}) {t['w']}x{t['h']} <{t['tag']}> title='{t['title'][:30]}' '{t['text'][:20]}'", flush=True)

    # Also map ALL top bar elements (full width, y 0-48)
    top_all = page.evaluate("""() => {
        var items = [];
        for (const el of document.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            var text = (el.innerText || '').trim();
            var title = el.title || '';
            if (r.y >= 0 && r.y < 48 && r.x > 100 && r.x < 1440
                && r.width > 15 && r.height > 12
                && (text.length > 0 || title.length > 0) && text.length < 40
                && r.width < 200) {
                items.push({
                    text: text.substring(0, 30),
                    title: title.substring(0, 40),
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    tag: el.tagName,
                    classes: (el.className || '').toString().substring(0, 30),
                });
            }
        }
        var seen = new Set();
        return items.filter(function(i) {
            var key = i.text.substring(0,10) + '|' + Math.round(i.x/5);
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
        }).sort(function(a,b) { return a.x - b.x; }).slice(0, 40);
    }""")
    print(f"\n  Full top bar ({len(top_all)}):", flush=True)
    for t in top_all:
        print(f"    ({t['x']},{t['y']}) {t['w']}x{t['h']} <{t['tag']}> c='{t['classes'][:20]}' title='{t['title'][:25]}' '{t['text'][:20]}'", flush=True)

    # ============================================================
    #  PART 5: BOTTOM BAR (CHAT EDITOR + ZOOM)
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 5: BOTTOM BAR", flush=True)
    print("=" * 60, flush=True)

    bottom_bar = page.evaluate("""() => {
        var items = [];
        for (const el of document.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            var text = (el.innerText || '').trim();
            if (r.y > 850 && r.y < 920 && r.width > 15
                && text.length > 0 && text.length < 80) {
                items.push({
                    text: text.substring(0, 50),
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    tag: el.tagName,
                    classes: (el.className || '').toString().substring(0, 30),
                });
            }
        }
        var seen = new Set();
        return items.filter(function(i) {
            var key = i.text.substring(0,15) + '|' + Math.round(i.x/10);
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
        }).sort(function(a,b) { return a.x - b.x; }).slice(0, 20);
    }""")
    print(f"  Bottom bar ({len(bottom_bar)}):", flush=True)
    for b in bottom_bar:
        print(f"    ({b['x']},{b['y']}) {b['w']}x{b['h']} <{b['tag']}> c='{b['classes'][:22]}' '{b['text'][:45]}'", flush=True)

    ss(page, "P59_06_final")

    print(f"\n\n===== PHASE 59 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
