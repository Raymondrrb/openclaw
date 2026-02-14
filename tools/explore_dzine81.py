"""Phase 81: Complete remaining gaps from Phase 80.
1. Dismiss "New Feature" AnyFrame popup
2. AI Video full model list (scroll selector)
3. AI Video settings dropdown (resolution, duration, aspect ratio)
4. Camera Free Selection tab
5. Txt2Img style/model selector (.c-style button)
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
    """Wait for canvas to fully load."""
    for i in range(max_wait):
        loaded = page.evaluate("""() => {
            var tg = document.querySelectorAll('.tool-group');
            return tg.length;
        }""")
        if loaded >= 5:
            print(f"  Canvas loaded ({loaded} tool groups) after {i+1}s", flush=True)
            page.wait_for_timeout(2000)
            return True
        page.wait_for_timeout(1000)
    print(f"  Canvas load timeout ({max_wait}s)", flush=True)
    return False


def open_panel(page, target_x, target_y, panel_name=""):
    """Open a sidebar tool with robust toggle + verification."""
    page.mouse.click(40, 766)  # Storyboard
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


def dismiss_anyframe_popup(page):
    """Dismiss the AnyFrame 'New Feature' popup that blocks interaction."""
    # Click "Skip" button in the popup
    page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            if (text === 'Skip' && el.getBoundingClientRect().width > 20) {
                el.click();
                return true;
            }
        }
        return false;
    }""")
    page.wait_for_timeout(500)
    # Also try clicking "Not now" or closing via X
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
    #  PART 1: OPEN AI VIDEO + DISMISS ANYFRAME POPUP
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 1: AI VIDEO + DISMISS POPUP", flush=True)
    print("=" * 60, flush=True)

    open_panel(page, 40, 361, "AI Video")
    dismiss_anyframe_popup(page)
    page.wait_for_timeout(1000)
    ss(page, "P81_01_ai_video_clean")

    # ============================================================
    #  PART 2: VIDEO MODEL SELECTOR — FULL LIST
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 2: VIDEO MODEL SELECTOR (FULL LIST)", flush=True)
    print("=" * 60, flush=True)

    # Click model selector button
    page.evaluate("""() => {
        var p = document.querySelector('.c-gen-config.show') ||
                document.querySelector('.panels.show');
        if (!p) return;
        var btn = p.querySelector('.selected-btn-content');
        if (btn) btn.click();
    }""")
    page.wait_for_timeout(2000)
    dismiss_anyframe_popup(page)
    page.wait_for_timeout(500)
    ss(page, "P81_02_model_panel")

    # Get the selector panel
    selector = page.evaluate("""() => {
        var sp = document.querySelector('.selector-panel');
        if (!sp) return null;
        var r = sp.getBoundingClientRect();
        return {x: Math.round(r.x), y: Math.round(r.y),
                w: Math.round(r.width), h: Math.round(r.height),
                classes: (sp.className || '').toString().substring(0, 50)};
    }""")
    print(f"  Selector panel: {selector}", flush=True)

    if selector:
        # Get all model items with names, credits, tags
        models = page.evaluate("""() => {
            var sp = document.querySelector('.selector-panel');
            if (!sp) return [];
            var items = [];
            // Find all item-name elements
            var names = sp.querySelectorAll('.item-name');
            for (var name of names) {
                var r = name.getBoundingClientRect();
                var text = (name.innerText || '').trim();
                // Find sibling item-desc (credits)
                var parent = name.closest('.style-item') || name.parentElement;
                var desc = parent ? parent.querySelector('.item-desc') : null;
                var descText = desc ? (desc.innerText || '').trim() : '';
                // Find labels (1080p, etc)
                var labels = parent ? parent.querySelector('.item-labels') : null;
                var labelText = labels ? (labels.innerText || '').trim() : '';
                // Check for HOT tag
                var hot = parent ? parent.querySelector('.item-hot') : null;
                var isHot = hot ? true : false;
                // Check for selected
                var isSelected = parent ? (parent.className || '').includes('selected') : false;
                items.push({
                    name: text,
                    credits: descText,
                    labels: labelText,
                    hot: isHot,
                    selected: isSelected,
                    y: Math.round(r.y),
                });
            }
            return items.sort(function(a,b) { return a.y - b.y; });
        }""")
        print(f"\n  Video models ({len(models)}):", flush=True)
        for m in models:
            flags = []
            if m['hot']: flags.append('HOT')
            if m['selected']: flags.append('SELECTED')
            flag_str = f" [{', '.join(flags)}]" if flags else ''
            print(f"    {m['name']} — {m['credits']} | {m['labels']}{flag_str}", flush=True)

        # Scroll down to see more models
        page.evaluate("""() => {
            var sp = document.querySelector('.selector-panel');
            if (!sp) return;
            var scrollable = sp.querySelector('.style-list') || sp;
            for (var child of sp.querySelectorAll('*')) {
                if (child.scrollHeight > child.clientHeight + 10 && child.clientHeight > 100) {
                    child.scrollTop = child.scrollHeight;
                    return;
                }
            }
        }""")
        page.wait_for_timeout(1000)
        ss(page, "P81_02b_models_scrolled")

        # Get models again after scroll
        models2 = page.evaluate("""() => {
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
                items.push({
                    name: text, credits: descText, labels: labelText,
                    hot: hot ? true : false, y: Math.round(r.y),
                });
            }
            return items.sort(function(a,b) { return a.y - b.y; });
        }""")
        if len(models2) > len(models):
            print(f"\n  After scroll ({len(models2)} models):", flush=True)
            for m in models2:
                flag = ' [HOT]' if m['hot'] else ''
                print(f"    {m['name']} — {m['credits']} | {m['labels']}{flag}", flush=True)

        # Also check filter tabs
        filters = page.evaluate("""() => {
            var sp = document.querySelector('.selector-panel');
            if (!sp) return [];
            var items = [];
            for (var el of sp.querySelectorAll('.uncensored, [class*="filter"], [class*="checkbox"]')) {
                var text = (el.innerText || '').trim();
                var r = el.getBoundingClientRect();
                if (text.length > 0 && r.width > 0) {
                    items.push({
                        text: text, tag: el.tagName,
                        classes: (el.className || '').toString().substring(0, 30),
                    });
                }
            }
            return items;
        }""")
        print(f"\n  Filter options: {filters}", flush=True)

    page.keyboard.press("Escape")
    page.wait_for_timeout(500)

    # ============================================================
    #  PART 3: AI VIDEO SETTINGS DROPDOWN
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 3: AI VIDEO SETTINGS DROPDOWN", flush=True)
    print("=" * 60, flush=True)

    # Find and click the settings row (Auto · 768p · 6s)
    settings_el = page.evaluate("""() => {
        var p = document.querySelector('.c-gen-config.show') ||
                document.querySelector('.panels.show');
        if (!p) return null;
        for (const el of p.querySelectorAll('.config-param, .metadata')) {
            var text = (el.innerText || '').trim();
            if (text.includes('768p') || text.includes('Auto')) {
                var r = el.getBoundingClientRect();
                return {text: text, tag: el.tagName,
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        classes: (el.className || '').toString().substring(0, 40)};
            }
        }
        return null;
    }""")
    print(f"  Settings element: {settings_el}", flush=True)

    if settings_el:
        page.mouse.click(settings_el['x'] + settings_el['w'] // 2,
                         settings_el['y'] + settings_el['h'] // 2)
        page.wait_for_timeout(2000)
        dismiss_anyframe_popup(page)
        page.wait_for_timeout(500)
        ss(page, "P81_03_settings_dropdown")

        # Check for selector panel or popup
        settings_panel = page.evaluate("""() => {
            // Check for .selector-panel that just appeared
            var panels = document.querySelectorAll('.selector-panel');
            for (var sp of panels) {
                var r = sp.getBoundingClientRect();
                if (r.width > 100 && r.height > 100) {
                    return {type: 'selector-panel',
                            x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height),
                            classes: (sp.className || '').toString().substring(0, 50)};
                }
            }
            // Check for any high-z popup
            var items = [];
            for (const el of document.querySelectorAll('*')) {
                var cs = window.getComputedStyle(el);
                var z = parseInt(cs.zIndex) || 0;
                var r = el.getBoundingClientRect();
                if (z > 500 && r.width > 100 && r.height > 80 && r.x > 60 && r.x < 600) {
                    items.push({
                        type: 'high-z', z: z,
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        classes: (el.className || '').toString().substring(0, 50),
                        text: (el.innerText || '').trim().replace(/\\n/g, ' | ').substring(0, 100),
                    });
                }
            }
            return items.sort(function(a,b) { return b.z - a.z; })[0] || null;
        }""")
        print(f"  Settings panel: {settings_panel}", flush=True)

        if settings_panel:
            # Get detailed settings options
            if settings_panel.get('type') == 'selector-panel' or settings_panel.get('w', 0) > 200:
                opts = page.evaluate("""() => {
                    var sp = document.querySelector('.selector-panel');
                    if (!sp) return [];
                    var items = [];
                    var seen = new Set();
                    for (var el of sp.querySelectorAll('*')) {
                        var r = el.getBoundingClientRect();
                        var text = (el.innerText || '').trim();
                        if (text.length > 0 && text.length < 35 && r.height > 8 && r.height < 45
                            && r.width > 15 && r.width < 200 && !seen.has(text)) {
                            seen.add(text);
                            items.push({
                                tag: el.tagName, x: Math.round(r.x), y: Math.round(r.y),
                                w: Math.round(r.width), h: Math.round(r.height),
                                text: text,
                                classes: (el.className || '').toString().substring(0, 30),
                            });
                        }
                    }
                    return items.sort(function(a,b) { return a.y - b.y; }).slice(0, 40);
                }""")
                print(f"\n  Settings options ({len(opts)}):", flush=True)
                for o in opts:
                    print(f"    ({o['x']},{o['y']}) {o['w']}x{o['h']} <{o['tag']}> c='{o['classes'][:20]}' '{o['text']}'", flush=True)

        page.keyboard.press("Escape")
        page.wait_for_timeout(500)

    # ============================================================
    #  PART 4: CAMERA FREE SELECTION TAB
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 4: CAMERA FREE SELECTION TAB", flush=True)
    print("=" * 60, flush=True)

    # Click Camera to open it
    cam_opened = page.evaluate("""() => {
        var p = document.querySelector('.c-gen-config.show') ||
                document.querySelector('.panels.show');
        if (!p) return null;
        var cam = p.querySelector('.camera-movement-btn');
        if (cam) { cam.click(); return 'clicked btn'; }
        // Fallback
        for (var el of p.querySelectorAll('*')) {
            if ((el.innerText || '').trim() === 'Camera') {
                el.click();
                return 'clicked text';
            }
        }
        return null;
    }""")
    print(f"  Camera opened: {cam_opened}", flush=True)
    page.wait_for_timeout(1500)
    dismiss_anyframe_popup(page)
    page.wait_for_timeout(500)

    # Click Free Selection tab
    fs_click = page.evaluate("""() => {
        for (var el of document.querySelectorAll('.tab, [class*="tab"]')) {
            var text = (el.innerText || '').trim();
            if (text === 'Free Selection') {
                el.click();
                return true;
            }
        }
        return null;
    }""")
    print(f"  Free Selection clicked: {fs_click}", flush=True)
    page.wait_for_timeout(1500)
    ss(page, "P81_04_camera_free_selection")

    # Dump Free Selection content
    fs_items = page.evaluate("""() => {
        var items = [];
        var seen = new Set();
        // Find camera items in the camera popup area (x > 340)
        for (var el of document.querySelectorAll('.camera-item, [class*="camera"]')) {
            var r = el.getBoundingClientRect();
            var text = (el.innerText || '').trim();
            if (r.x > 340 && r.width > 30 && text.length > 0 && text.length < 40 && !seen.has(text)) {
                seen.add(text);
                items.push({
                    tag: el.tagName, x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    text: text,
                    classes: (el.className || '').toString().substring(0, 35),
                });
            }
        }
        return items.sort(function(a,b) { return a.y - b.y; }).slice(0, 30);
    }""")
    print(f"\n  Free Selection items ({len(fs_items)}):", flush=True)
    for f in fs_items:
        print(f"    ({f['x']},{f['y']}) {f['w']}x{f['h']} c='{f['classes'][:25]}' '{f['text']}'", flush=True)

    # Also dump all text in the camera area
    fs_all = page.evaluate("""() => {
        var items = [];
        var seen = new Set();
        for (var el of document.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            if (r.x >= 340 && r.x < 800 && r.y >= 60 && r.y < 700
                && r.width > 15 && r.height > 8 && r.height < 50 && r.width < 250) {
                var text = (el.innerText || '').trim();
                if (text.length > 0 && text.length < 35 && !seen.has(text + '|' + Math.round(r.y))) {
                    seen.add(text + '|' + Math.round(r.y));
                    items.push({
                        tag: el.tagName, x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        text: text,
                        classes: (el.className || '').toString().substring(0, 30),
                    });
                }
            }
        }
        return items.sort(function(a,b) { return a.y - b.y; }).slice(0, 40);
    }""")
    print(f"\n  Camera area text ({len(fs_all)}):", flush=True)
    for f in fs_all:
        print(f"    ({f['x']},{f['y']}) {f['w']}x{f['h']} <{f['tag']}> c='{f['classes'][:22]}' '{f['text']}'", flush=True)

    page.keyboard.press("Escape")
    page.wait_for_timeout(500)

    # ============================================================
    #  PART 5: TXT2IMG STYLE SELECTOR
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 5: TXT2IMG STYLE SELECTOR", flush=True)
    print("=" * 60, flush=True)

    open_panel(page, 40, 197, "Txt2Img")
    dismiss_anyframe_popup(page)

    # Click the style button (.c-style or button.style)
    style_btn = page.evaluate("""() => {
        var p = document.querySelector('.c-gen-config.show') ||
                document.querySelector('.panels.show');
        if (!p) return null;
        var btn = p.querySelector('button.style');
        if (btn) {
            var r = btn.getBoundingClientRect();
            btn.click();
            return {text: (btn.innerText || '').trim().substring(0, 40),
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height)};
        }
        return null;
    }""")
    print(f"  Style button clicked: {style_btn}", flush=True)
    page.wait_for_timeout(2000)
    ss(page, "P81_05_style_selector")

    # Check for style-list-panel
    style_panel = page.evaluate("""() => {
        var sp = document.querySelector('.style-list-panel');
        if (sp) {
            var r = sp.getBoundingClientRect();
            return {x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    visible: r.width > 0};
        }
        // Also check for selector-panel
        sp = document.querySelector('.selector-panel');
        if (sp) {
            var r = sp.getBoundingClientRect();
            return {x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    type: 'selector-panel', visible: r.width > 0};
        }
        return null;
    }""")
    print(f"  Style panel: {style_panel}", flush=True)

    if style_panel and style_panel.get('visible'):
        # Get category tabs
        cats = page.evaluate("""() => {
            var sp = document.querySelector('.style-list-panel') ||
                     document.querySelector('.selector-panel');
            if (!sp) return [];
            var items = [];
            var seen = new Set();
            // Get tab items first
            for (var el of sp.querySelectorAll('[class*="tab"], [class*="category"], .name, h3, h4, h5')) {
                var r = el.getBoundingClientRect();
                var text = (el.innerText || '').trim();
                if (text.length > 0 && text.length < 30 && r.width > 0 && !seen.has(text)) {
                    seen.add(text);
                    items.push({
                        tag: el.tagName, x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        text: text,
                        classes: (el.className || '').toString().substring(0, 30),
                    });
                }
            }
            return items.sort(function(a,b) { return a.y - b.y; }).slice(0, 30);
        }""")
        print(f"\n  Style categories ({len(cats)}):", flush=True)
        for c in cats:
            print(f"    ({c['x']},{c['y']}) {c['w']}x{c['h']} <{c['tag']}> c='{c['classes'][:22]}' '{c['text']}'", flush=True)

        # Get all model/style names
        styles = page.evaluate("""() => {
            var sp = document.querySelector('.style-list-panel') ||
                     document.querySelector('.selector-panel');
            if (!sp) return [];
            var items = [];
            var names = sp.querySelectorAll('.item-name, .style-name');
            for (var n of names) {
                var r = n.getBoundingClientRect();
                var text = (n.innerText || '').trim();
                var parent = n.closest('.style-item') || n.parentElement;
                var desc = parent ? parent.querySelector('.item-desc') : null;
                var descText = desc ? (desc.innerText || '').trim() : '';
                items.push({
                    name: text, desc: descText,
                    y: Math.round(r.y), x: Math.round(r.x),
                });
            }
            return items.sort(function(a,b) { return a.y - b.y; }).slice(0, 40);
        }""")
        print(f"\n  Styles/Models ({len(styles)}):", flush=True)
        for s in styles:
            print(f"    ({s['x']},{s['y']}) '{s['name']}' — {s['desc']}", flush=True)

        ss(page, "P81_05b_style_content")

    page.keyboard.press("Escape")
    page.wait_for_timeout(500)

    # ============================================================
    #  PART 6: IMG2IMG PANEL DEEP DIVE
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 6: IMG2IMG PANEL", flush=True)
    print("=" * 60, flush=True)

    open_panel(page, 40, 252, "Img2Img")

    # Dump full panel
    items = page.evaluate("""() => {
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
                            classes: (el.className || '').toString().substring(0, 35),
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
    print(f"\n  Img2Img — title='{title}' ({len(items)} elements):", flush=True)
    for el in items:
        print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> c='{el['classes'][:25]}' '{el['text'][:35]}'", flush=True)
    ss(page, "P81_06_img2img")

    print(f"\n\n===== PHASE 81 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
