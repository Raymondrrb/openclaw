"""Phase 82: Remaining gaps.
1. AI Video settings — click the settings row directly (not via config-param class)
2. Camera Free Selection tab (close model selector first)
3. Txt2Img Advanced popup content
4. Reference mode model selector (check if different models)
5. Character panel deep dive
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


def wait_for_canvas(page, max_wait=40):
    for i in range(max_wait):
        loaded = page.evaluate("() => document.querySelectorAll('.tool-group').length")
        if loaded >= 5:
            print(f"  Canvas loaded ({loaded} tool groups) after {i+1}s", flush=True)
            page.wait_for_timeout(2000)
            return True
        page.wait_for_timeout(1000)
    print(f"  Canvas load timeout", flush=True)
    return False


def open_panel(page, target_x, target_y, panel_name=""):
    page.mouse.click(40, 766)  # Storyboard (distant toggle)
    page.wait_for_timeout(2000)
    close_dialogs(page)
    page.mouse.move(700, 450)
    page.wait_for_timeout(500)
    page.mouse.click(target_x, target_y)
    page.wait_for_timeout(3000)
    close_dialogs(page)
    title = page.evaluate("""() => {
        var p = document.querySelector('.c-gen-config.show') ||
                document.querySelector('.panels.show');
        if (!p) return 'NONE';
        var h5 = p.querySelector('h5');
        return h5 ? (h5.innerText || '').trim() : 'no h5';
    }""")
    print(f"  Opened '{panel_name}': title='{title}'", flush=True)
    return title


def dismiss_popups(page):
    """Dismiss AnyFrame popup and other tooltips."""
    page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            if (text === 'Skip' && el.getBoundingClientRect().width > 20) {
                el.click(); return;
            }
        }
    }""")
    page.wait_for_timeout(500)
    close_dialogs(page)


def main():
    print("Connecting...", flush=True)
    pw = sync_playwright().start()
    browser = pw.chromium.connect_over_cdp("http://127.0.0.1:18800", timeout=15000)
    ctx = browser.contexts[0]
    page = ctx.new_page()
    page.set_viewport_size({"width": 1440, "height": 900})

    page.goto(CANVAS_URL, wait_until="domcontentloaded", timeout=30000)
    print("  Waiting for canvas...", flush=True)
    wait_for_canvas(page)
    close_dialogs(page)

    # ============================================================
    #  PART 1: AI VIDEO SETTINGS DROPDOWN
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 1: AI VIDEO SETTINGS DROPDOWN", flush=True)
    print("=" * 60, flush=True)

    open_panel(page, 40, 361, "AI Video")
    dismiss_popups(page)
    page.wait_for_timeout(500)

    # Find and click the settings metadata row "Auto · 768p · 6s"
    # It's in .metadata with text containing "768p" or "Auto"
    click_result = page.evaluate("""() => {
        var p = document.querySelector('.c-gen-config.show') ||
                document.querySelector('.panels.show');
        if (!p) return null;
        var meta = p.querySelector('.metadata');
        if (meta) {
            var r = meta.getBoundingClientRect();
            meta.click();
            return {text: (meta.innerText || '').trim().substring(0, 40),
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height)};
        }
        return null;
    }""")
    print(f"  Settings metadata clicked: {click_result}", flush=True)
    page.wait_for_timeout(2000)
    dismiss_popups(page)
    ss(page, "P82_01_settings")

    # Check what opened — might be inline expansion
    expanded = page.evaluate("""() => {
        var p = document.querySelector('.c-gen-config.show') ||
                document.querySelector('.panels.show');
        if (!p) return null;
        // Look for expanded settings area
        var items = [];
        var seen = new Set();
        for (var el of p.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            var text = (el.innerText || '').trim();
            if (text.length > 0 && text.length < 40 && r.width > 15
                && r.height > 8 && r.height < 50 && r.width < 260
                && r.y > 450 && r.y < 800) {
                var key = text + '|' + Math.round(r.y);
                if (!seen.has(key)) {
                    seen.add(key);
                    items.push({
                        tag: el.tagName, x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        text: text,
                        classes: (el.className || '').toString().substring(0, 30),
                    });
                }
            }
        }
        return items.sort(function(a,b) { return a.y - b.y; }).slice(0, 25);
    }""")
    print(f"\n  Panel content below settings ({len(expanded)}):", flush=True)
    for e in expanded:
        print(f"    ({e['x']},{e['y']}) {e['w']}x{e['h']} <{e['tag']}> c='{e['classes'][:22]}' '{e['text']}'", flush=True)

    # Try clicking the parent config-param div
    config_click = page.evaluate("""() => {
        var p = document.querySelector('.c-gen-config.show') ||
                document.querySelector('.panels.show');
        if (!p) return null;
        for (var el of p.querySelectorAll('.config-param')) {
            var text = (el.innerText || '').trim();
            if (text.includes('Auto') && text.includes('768p')) {
                var r = el.getBoundingClientRect();
                if (r.width > 0 && r.height > 0) {
                    el.click();
                    return {text: text.substring(0, 40), x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height)};
                }
            }
        }
        return null;
    }""")
    print(f"\n  Config param clicked: {config_click}", flush=True)
    page.wait_for_timeout(2000)
    dismiss_popups(page)
    ss(page, "P82_01b_settings_expanded")

    # Dump full panel now to see if settings expanded
    full_panel = page.evaluate("""() => {
        var p = document.querySelector('.c-gen-config.show') ||
                document.querySelector('.panels.show');
        if (!p) return [];
        var items = [];
        var excluded = ['path','line','circle','g','svg','defs','rect','polygon',
                        'clippath','HTML','BODY','HEAD','SCRIPT','STYLE','META','LINK'];
        var seen = new Set();
        for (const el of p.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            if (r.width > 10 && r.height > 10 && r.width < 300
                && !excluded.includes(el.tagName.toUpperCase())) {
                var text = (el.innerText || '').trim();
                if (text.length > 0 && text.length < 50 && text.indexOf('\\n') === -1) {
                    var key = el.tagName + '|' + Math.round(r.x) + '|' + Math.round(r.y);
                    if (!seen.has(key)) {
                        seen.add(key);
                        items.push({
                            tag: el.tagName, x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height),
                            text: text.substring(0, 40),
                            classes: (el.className || '').toString().substring(0, 30),
                        });
                    }
                }
            }
        }
        return items.sort(function(a,b) { return a.y - b.y; }).slice(0, 60);
    }""")
    print(f"\n  Full AI Video panel ({len(full_panel)}):", flush=True)
    for el in full_panel:
        print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> c='{el['classes'][:22]}' '{el['text'][:35]}'", flush=True)

    # ============================================================
    #  PART 2: CAMERA FREE SELECTION
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 2: CAMERA FREE SELECTION", flush=True)
    print("=" * 60, flush=True)

    # Ensure AI Video is open and no overlay
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)

    # Click camera button
    page.evaluate("""() => {
        var p = document.querySelector('.c-gen-config.show') ||
                document.querySelector('.panels.show');
        if (!p) return;
        var cam = p.querySelector('.camera-movement-btn');
        if (cam) cam.click();
    }""")
    page.wait_for_timeout(1500)
    dismiss_popups(page)
    ss(page, "P82_02_camera_cinematic")

    # Now click Free Selection tab
    page.evaluate("""() => {
        for (var el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var cls = (el.className || '').toString();
            if (text === 'Free Selection' && cls.includes('tab')) {
                el.click();
                return true;
            }
        }
        // Fallback: any element with "Free Selection"
        for (var el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            if (text === 'Free Selection') {
                el.click();
                return true;
            }
        }
        return false;
    }""")
    page.wait_for_timeout(1500)
    ss(page, "P82_03_camera_free_selection")

    # Dump content of camera panel area (to the right of main panel)
    fs_content = page.evaluate("""() => {
        var items = [];
        var seen = new Set();
        // Camera area is to the right at x > 340
        for (var el of document.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            if (r.x >= 340 && r.x < 800 && r.y >= 60 && r.y < 700
                && r.width > 15 && r.height > 8 && r.height < 60 && r.width < 400) {
                var text = (el.innerText || '').trim();
                if (text.length > 0 && text.length < 40) {
                    var key = text + '|' + Math.round(r.y);
                    if (!seen.has(key)) {
                        seen.add(key);
                        items.push({
                            tag: el.tagName, x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height),
                            text: text,
                            classes: (el.className || '').toString().substring(0, 35),
                        });
                    }
                }
            }
        }
        return items.sort(function(a,b) { return a.y - b.y; }).slice(0, 40);
    }""")
    print(f"\n  Free Selection content ({len(fs_content)}):", flush=True)
    for f in fs_content:
        print(f"    ({f['x']},{f['y']}) {f['w']}x{f['h']} <{f['tag']}> c='{f['classes'][:25]}' '{f['text']}'", flush=True)

    # Close camera
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)

    # ============================================================
    #  PART 3: AI VIDEO REFERENCE MODE MODEL SELECTOR
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 3: REFERENCE MODE MODELS", flush=True)
    print("=" * 60, flush=True)

    # Switch to Reference mode
    page.evaluate("""() => {
        var p = document.querySelector('.c-gen-config.show') ||
                document.querySelector('.panels.show');
        if (!p) return;
        for (var btn of p.querySelectorAll('button')) {
            if ((btn.innerText || '').trim() === 'Reference') {
                btn.click(); return;
            }
        }
    }""")
    page.wait_for_timeout(2000)
    dismiss_popups(page)
    ss(page, "P82_04_reference_mode")

    # Dump Reference mode panel
    ref_panel = page.evaluate("""() => {
        var p = document.querySelector('.c-gen-config.show') ||
                document.querySelector('.panels.show');
        if (!p) return [];
        var items = [];
        var excluded = ['path','line','circle','g','svg','defs','rect','polygon',
                        'clippath','HTML','BODY','HEAD','SCRIPT','STYLE','META','LINK'];
        var seen = new Set();
        for (const el of p.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            if (r.width > 10 && r.height > 10 && r.width < 300
                && !excluded.includes(el.tagName.toUpperCase())) {
                var text = (el.innerText || '').trim();
                if (text.length > 0 && text.length < 50 && text.indexOf('\\n') === -1) {
                    var key = el.tagName + '|' + Math.round(r.x) + '|' + Math.round(r.y);
                    if (!seen.has(key)) {
                        seen.add(key);
                        items.push({
                            tag: el.tagName, x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height),
                            text: text.substring(0, 40),
                            classes: (el.className || '').toString().substring(0, 30),
                        });
                    }
                }
            }
        }
        return items.sort(function(a,b) { return a.y - b.y; }).slice(0, 50);
    }""")
    print(f"\n  Reference mode panel ({len(ref_panel)}):", flush=True)
    for el in ref_panel:
        print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> c='{el['classes'][:22]}' '{el['text'][:35]}'", flush=True)

    # Click model selector in Reference mode
    ref_model = page.evaluate("""() => {
        var p = document.querySelector('.c-gen-config.show') ||
                document.querySelector('.panels.show');
        if (!p) return null;
        var btn = p.querySelector('.selected-btn-content');
        if (btn) {
            var r = btn.getBoundingClientRect();
            btn.click();
            return {text: (btn.innerText || '').trim().substring(0, 40),
                    x: Math.round(r.x), y: Math.round(r.y)};
        }
        return null;
    }""")
    print(f"\n  Reference model clicked: {ref_model}", flush=True)
    page.wait_for_timeout(2000)
    dismiss_popups(page)
    ss(page, "P82_05_reference_models")

    # Get model list
    ref_models = page.evaluate("""() => {
        var sp = document.querySelector('.selector-panel');
        if (!sp) return [];
        var items = [];
        var names = sp.querySelectorAll('.item-name');
        for (var name of names) {
            var r = name.getBoundingClientRect();
            var text = (name.innerText || '').trim();
            var parent = name.closest('.style-item') || name.parentElement;
            var desc = parent ? parent.querySelector('.item-desc') : null;
            var descText = desc ? (desc.innerText || '').trim() : '';
            var labels = parent ? parent.querySelector('.item-labels') : null;
            var labelText = labels ? (labels.innerText || '').trim() : '';
            var hot = parent ? parent.querySelector('.item-hot') : null;
            var selected = parent ? (parent.className || '').includes('selected') : false;
            items.push({
                name: text, credits: descText, labels: labelText,
                hot: hot ? true : false, selected: selected,
                y: Math.round(r.y),
            });
        }
        return items.sort(function(a,b) { return a.y - b.y; });
    }""")
    print(f"\n  Reference mode models ({len(ref_models)}):", flush=True)
    for m in ref_models:
        flags = []
        if m['hot']: flags.append('HOT')
        if m['selected']: flags.append('SELECTED')
        flag_str = f" [{', '.join(flags)}]" if flags else ''
        print(f"    {m['name']} — {m['credits']} | {m['labels']}{flag_str}", flush=True)

    page.keyboard.press("Escape")
    page.wait_for_timeout(500)

    # ============================================================
    #  PART 4: CHARACTER PANEL
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 4: CHARACTER PANEL", flush=True)
    print("=" * 60, flush=True)

    open_panel(page, 40, 306, "Character")
    dismiss_popups(page)
    ss(page, "P82_06_character_panel")

    # Dump character panel
    char_panel = page.evaluate("""() => {
        var p = document.querySelector('.panels.show') ||
                document.querySelector('.c-gen-config.show');
        if (!p) return [];
        var items = [];
        var excluded = ['path','line','circle','g','svg','defs','rect','polygon',
                        'clippath','HTML','BODY','HEAD','SCRIPT','STYLE','META','LINK'];
        var seen = new Set();
        for (const el of p.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            if (r.width > 10 && r.height > 10 && r.width < 300
                && !excluded.includes(el.tagName.toUpperCase())) {
                var text = (el.innerText || '').trim();
                if (text.length > 0 && text.length < 50 && text.indexOf('\\n') === -1) {
                    var key = el.tagName + '|' + Math.round(r.x) + '|' + Math.round(r.y);
                    if (!seen.has(key)) {
                        seen.add(key);
                        items.push({
                            tag: el.tagName, x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height),
                            text: text.substring(0, 40),
                            classes: (el.className || '').toString().substring(0, 30),
                        });
                    }
                }
            }
        }
        return items.sort(function(a,b) { return a.y - b.y; }).slice(0, 50);
    }""")
    title = page.evaluate("""() => {
        var p = document.querySelector('.panels.show') ||
                document.querySelector('.c-gen-config.show');
        if (!p) return 'NONE';
        var h5 = p.querySelector('h5');
        return h5 ? (h5.innerText || '').trim() : 'no h5';
    }""")
    print(f"\n  Character panel — title='{title}' ({len(char_panel)}):", flush=True)
    for el in char_panel:
        print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> c='{el['classes'][:22]}' '{el['text'][:35]}'", flush=True)

    # ============================================================
    #  PART 5: TXT2IMG ADVANCED POPUP
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 5: TXT2IMG ADVANCED POPUP", flush=True)
    print("=" * 60, flush=True)

    open_panel(page, 40, 197, "Txt2Img")
    dismiss_popups(page)

    # Click Advanced
    page.evaluate("""() => {
        var p = document.querySelector('.c-gen-config.show') ||
                document.querySelector('.panels.show');
        if (!p) return;
        var btn = p.querySelector('.advanced-btn');
        if (btn) { btn.click(); return; }
        for (var el of p.querySelectorAll('*')) {
            if ((el.innerText || '').trim() === 'Advanced') { el.click(); return; }
        }
    }""")
    page.wait_for_timeout(2000)
    ss(page, "P82_07_advanced")

    # Check for .advanced-content.show
    adv = page.evaluate("""() => {
        var el = document.querySelector('.advanced-content.show');
        if (el) {
            var r = el.getBoundingClientRect();
            return {x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    classes: (el.className || '').toString().substring(0, 50)};
        }
        // Check for advanced-content without .show
        el = document.querySelector('.advanced-content');
        if (el) {
            var r = el.getBoundingClientRect();
            return {x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    classes: (el.className || '').toString().substring(0, 50),
                    note: 'without .show'};
        }
        return null;
    }""")
    print(f"  Advanced content: {adv}", flush=True)

    if adv:
        adv_items = page.evaluate(f"""() => {{
            var el = document.querySelector('.advanced-content.show') ||
                     document.querySelector('.advanced-content');
            if (!el) return [];
            var items = [];
            var seen = new Set();
            for (var child of el.querySelectorAll('*')) {{
                var r = child.getBoundingClientRect();
                var text = (child.innerText || '').trim();
                if (text.length > 0 && text.length < 40 && r.width > 10 && r.height > 8) {{
                    var key = text + '|' + Math.round(r.y);
                    if (!seen.has(key)) {{
                        seen.add(key);
                        items.push({{
                            tag: child.tagName, x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height),
                            text: text,
                            classes: (child.className || '').toString().substring(0, 30),
                        }});
                    }}
                }}
            }}
            return items.sort(function(a,b) {{ return a.y - b.y; }}).slice(0, 20);
        }}""")
        print(f"\n  Advanced items ({len(adv_items)}):", flush=True)
        for a in adv_items:
            print(f"    ({a['x']},{a['y']}) {a['w']}x{a['h']} <{a['tag']}> c='{a['classes'][:22]}' '{a['text']}'", flush=True)

    # Also get the inputs/controls in advanced area
    adv_inputs = page.evaluate("""() => {
        var el = document.querySelector('.advanced-content.show') ||
                 document.querySelector('.advanced-content');
        if (!el) return [];
        var items = [];
        for (var inp of el.querySelectorAll('input, textarea, select, .ant-slider, [role="slider"]')) {
            var r = inp.getBoundingClientRect();
            items.push({
                tag: inp.tagName, type: inp.type || '',
                x: Math.round(r.x), y: Math.round(r.y),
                w: Math.round(r.width), h: Math.round(r.height),
                placeholder: (inp.placeholder || '').substring(0, 30),
                value: (inp.value || '').substring(0, 30),
            });
        }
        return items;
    }""")
    print(f"\n  Advanced inputs ({len(adv_inputs)}):", flush=True)
    for inp in adv_inputs:
        print(f"    ({inp['x']},{inp['y']}) {inp['w']}x{inp['h']} <{inp['tag']} type={inp['type']}> ph='{inp['placeholder']}' val='{inp['value']}'", flush=True)

    print(f"\n\n===== PHASE 82 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
