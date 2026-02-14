#!/usr/bin/env python3
"""Dzine Deep Exploration Part 14 — Fix 16:9 + Camera Panel + Free Selection.

1. Map Nano Banana Pro aspect ratio buttons precisely
2. Explore AI Video camera panel (Cinematic Shots / Free Selection)
3. Map Static Shot, Push In buttons for automation
"""

import json
import sys
import time
sys.path.insert(0, "/Users/ray/Documents/openclaw")
from tools.lib.brave_profile import connect_or_launch


def screenshot(page, name):
    path = f"/Users/ray/Downloads/{name}.png"
    page.screenshot(path=path)
    print(f"  [SS] {path}")


def close_dialogs(page):
    page.evaluate("""() => {
        for (var i = 0; i < 5; i++) {
            for (var text of ['Not now', 'Close', 'Never show again', 'Got it', 'Skip', 'Later']) {
                for (var btn of document.querySelectorAll('button')) {
                    if ((btn.innerText || '').trim() === text && btn.offsetHeight > 0) btn.click();
                }
            }
        }
    }""")


def main():
    print("=" * 70)
    print("DZINE DEEP EXPLORATION PART 14")
    print("16:9 Fix + Camera Panel + Free Selection")
    print("=" * 70)

    browser, context, _, _pw = connect_or_launch()
    page = context.pages[0]
    print(f"Connected. URL: {page.url}")

    if "dzine.ai/canvas" not in page.url:
        page.goto("https://www.dzine.ai/canvas?id=19861203")
        page.wait_for_timeout(5000)
        close_dialogs(page)
        page.wait_for_timeout(1000)

    # ================================================================
    # TASK 1: Map Nano Banana Pro Panel in Detail
    # ================================================================
    print("\n" + "=" * 70)
    print("TASK 1: Nano Banana Pro Aspect Ratio Investigation")
    print("=" * 70)

    # Navigate to Txt2Img
    page.mouse.click(40, 766)  # Storyboard (distant)
    page.wait_for_timeout(1500)
    page.mouse.click(40, 197)  # Txt2Img
    page.wait_for_timeout(2500)

    # Verify Nano Banana Pro
    model = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return 'NO PANEL';
        var sn = panel.querySelector('.style-name');
        return sn ? (sn.innerText || '').trim() : 'unknown';
    }""")
    print(f"  Model: {model}")

    # Full panel element map
    full_map = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return [];
        var results = [];
        var allEls = panel.querySelectorAll('*');
        for (var el of allEls) {
            var rect = el.getBoundingClientRect();
            if (rect.height === 0 || rect.width === 0) continue;
            if (rect.height > 100) continue;  // skip containers
            var text = (el.innerText || '').trim();
            if (!text || text.length > 40) continue;
            // Skip nested text duplicates
            if (text.includes('\\n')) continue;

            var cls = (typeof el.className === 'string') ? el.className : (el.getAttribute('class') || '');
            var tag = el.tagName;

            // Only interesting elements
            if (tag === 'BUTTON' || tag === 'INPUT' || tag === 'TEXTAREA' ||
                cls.includes('item') || cls.includes('option') || cls.includes('switch') ||
                cls.includes('btn') || cls.includes('ratio') || cls.includes('aspect')) {
                results.push({
                    text: text,
                    tag: tag,
                    class: cls.substring(0, 60),
                    x: Math.round(rect.x),
                    y: Math.round(rect.y),
                    w: Math.round(rect.width),
                    h: Math.round(rect.height),
                    sel: cls.includes('selected') || cls.includes('active') || cls.includes('isChecked')
                });
            }
        }
        return results;
    }""")

    print(f"  Panel elements ({len(full_map)}):")
    for el in full_map:
        sel = " [SEL]" if el.get("sel") else ""
        print(f"    [{el['tag'][:6]}] '{el['text'][:25]}' at ({el['x']},{el['y']}) {el['w']}x{el['h']} cls={el['class'][:35]}{sel}")

    # Specifically find aspect ratio section
    aspect_section = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return [];
        // Find the aspect ratio container
        var containers = panel.querySelectorAll('[class*="aspect"], [class*="ratio"]');
        var results = [];
        for (var c of containers) {
            var rect = c.getBoundingClientRect();
            if (rect.height > 0) {
                var children = [];
                for (var child of c.querySelectorAll('*')) {
                    var cr = child.getBoundingClientRect();
                    if (cr.height > 0 && cr.height < 40) {
                        var cc = (typeof child.className === 'string') ? child.className : '';
                        children.push({
                            text: (child.innerText || '').trim(),
                            tag: child.tagName,
                            class: cc.substring(0, 40),
                            x: Math.round(cr.x),
                            y: Math.round(cr.y),
                            w: Math.round(cr.width),
                            h: Math.round(cr.height),
                            sel: cc.includes('selected') || cc.includes('active')
                        });
                    }
                }
                results.push({
                    class: ((typeof c.className === 'string') ? c.className : '').substring(0, 60),
                    pos: {x: Math.round(rect.x), y: Math.round(rect.y), w: Math.round(rect.width), h: Math.round(rect.height)},
                    children: children
                });
            }
        }
        return results;
    }""")

    print(f"\n  Aspect ratio containers ({len(aspect_section)}):")
    for sec in aspect_section:
        print(f"    class: {sec['class']}")
        print(f"    pos: ({sec['pos']['x']},{sec['pos']['y']}) {sec['pos']['w']}x{sec['pos']['h']}")
        for child in sec['children']:
            sel = " [SEL]" if child.get('sel') else ""
            print(f"      [{child['tag'][:4]}] '{child['text'][:15]}' at ({child['x']},{child['y']}) {child['w']}x{child['h']}{sel}")

    # Try clicking 16:9 with more specific targeting
    clicked_16_9 = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return {clicked: false, reason: 'no panel'};
        var aspectContainers = panel.querySelectorAll('[class*="aspect"], [class*="ratio"]');
        for (var c of aspectContainers) {
            for (var child of c.querySelectorAll('*')) {
                var text = (child.innerText || '').trim();
                if (text === '16:9') {
                    child.click();
                    return {clicked: true, tag: child.tagName, y: Math.round(child.getBoundingClientRect().y)};
                }
            }
        }
        // Fallback: click "more" or dropdown arrow
        for (var btn of panel.querySelectorAll('button, [class*="more"]')) {
            var text = (btn.innerText || '').trim();
            var cls = (typeof btn.className === 'string') ? btn.className : '';
            if (cls.includes('more') || text === '' && cls.includes('item')) {
                var rect = btn.getBoundingClientRect();
                if (rect.y > 450 && rect.y < 550 && rect.width < 50) {
                    btn.click();
                    return {clicked: true, note: 'clicked more/dropdown', y: Math.round(rect.y)};
                }
            }
        }
        return {clicked: false, reason: 'not found'};
    }""")
    print(f"\n  16:9 click: {json.dumps(clicked_16_9)}")
    page.wait_for_timeout(500)

    # Re-check dimensions
    dims = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return '';
        var text = panel.innerText || '';
        var match = text.match(/(\\d+)[x\u00d7](\\d+)/);
        return match ? match[0] : '';
    }""")
    print(f"  Dimensions after click: {dims}")

    screenshot(page, "p185_aspect_investigation")

    # ================================================================
    # TASK 2: AI Video Camera Panel Deep Map
    # ================================================================
    print("\n" + "=" * 70)
    print("TASK 2: Camera Panel Deep Map")
    print("=" * 70)

    # Use result image to open AI Video with start frame
    page.evaluate("""() => {
        for (var el of document.querySelectorAll('[class*="header-item"]')) {
            if ((el.innerText || '').includes('Result')) { el.click(); return; }
        }
    }""")
    page.wait_for_timeout(500)

    # Scroll results to top and click AI Video
    page.evaluate("""() => {
        var containers = document.querySelectorAll('.result-panel, .material-v2-result-content');
        for (var c of containers) {
            if (c.scrollHeight > c.clientHeight + 100) c.scrollTop = 0;
        }
    }""")
    page.wait_for_timeout(500)

    # Click AI Video action button
    page.evaluate("""() => {
        var containers = document.querySelectorAll('.btn-container');
        for (var c of containers) {
            var parent = c.parentElement;
            var parentText = (parent ? parent.innerText || '' : '').trim();
            if (parentText.startsWith('AI Video')) {
                var rect = c.getBoundingClientRect();
                if (rect.height > 0 && rect.y > 50 && rect.y < 900) {
                    var btns = c.querySelectorAll('.btn');
                    if (btns.length > 0) { btns[0].click(); return true; }
                }
            }
        }
        return false;
    }""")
    page.wait_for_timeout(3000)

    # Open camera panel
    print("  Opening Camera panel...")
    page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return false;
        var camBtn = panel.querySelector('.camera-movement-btn');
        if (camBtn) { camBtn.click(); return true; }
        // Try text-based search
        for (var el of panel.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            if (text === 'Camera' || text.includes('Camera')) {
                var rect = el.getBoundingClientRect();
                if (rect.height > 20 && rect.height < 60 && rect.width > 100) {
                    el.click();
                    return true;
                }
            }
        }
        return false;
    }""")
    page.wait_for_timeout(1500)

    screenshot(page, "p185_camera_panel_1")

    # Map the camera panel in detail
    camera_panel = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return {found: false};

        // Look for camera-related elements
        var text = panel.innerText || '';

        // Find tabs (Cinematic Shots / Free Selection)
        var tabs = [];
        for (var el of panel.querySelectorAll('button, [role="tab"], [class*="tab"]')) {
            var t = (el.innerText || '').trim();
            if (t === 'Cinematic Shots' || t === 'Free Selection') {
                var rect = el.getBoundingClientRect();
                var cls = (typeof el.className === 'string') ? el.className : '';
                tabs.push({
                    text: t,
                    x: Math.round(rect.x),
                    y: Math.round(rect.y),
                    w: Math.round(rect.width),
                    h: Math.round(rect.height),
                    sel: cls.includes('selected') || cls.includes('active')
                });
            }
        }

        // Find camera movement buttons
        var movements = [];
        var knownMovements = ['Truck Left', 'Truck Right', 'Pan Left', 'Pan Right',
            'Push In', 'Pull Out', 'Pedestal Up', 'Pedestal Down',
            'Tilt Up', 'Tilt Down', 'Zoom In', 'Zoom Out',
            'Shake', 'Tracking Shot', 'Static Shot',
            'Arc Left', 'Arc Right', 'Dolly In', 'Dolly Out'];

        for (var el of panel.querySelectorAll('*')) {
            var t = (el.innerText || '').trim();
            for (var m of knownMovements) {
                if (t === m) {
                    var rect = el.getBoundingClientRect();
                    if (rect.height > 0 && rect.height < 60) {
                        var cls = (typeof el.className === 'string') ? el.className : '';
                        movements.push({
                            text: m,
                            tag: el.tagName,
                            class: cls.substring(0, 50),
                            x: Math.round(rect.x),
                            y: Math.round(rect.y),
                            w: Math.round(rect.width),
                            h: Math.round(rect.height),
                            active: cls.includes('active') || cls.includes('selected')
                        });
                    }
                    break;
                }
            }
        }

        // Deduplicate movements
        var seen = {};
        var unique = [];
        for (var m of movements) {
            if (!seen[m.text + '_' + m.y]) {
                seen[m.text + '_' + m.y] = true;
                unique.push(m);
            }
        }

        return {
            found: true,
            tabs: tabs,
            movements: unique,
            panelText: text.substring(0, 800)
        };
    }""")

    if camera_panel.get("found"):
        print(f"\n  Tabs ({len(camera_panel.get('tabs', []))}):")
        for tab in camera_panel.get("tabs", []):
            sel = " [SELECTED]" if tab.get("sel") else ""
            print(f"    '{tab['text']}' at ({tab['x']},{tab['y']}) {tab['w']}x{tab['h']}{sel}")

        print(f"\n  Camera movements ({len(camera_panel.get('movements', []))}):")
        for m in camera_panel.get("movements", []):
            active = " [ACTIVE]" if m.get("active") else ""
            print(f"    '{m['text']}' at ({m['x']},{m['y']}) {m['w']}x{m['h']}{active}")

        # Show panel text for context
        print(f"\n  Panel text (first 400 chars):")
        for line in camera_panel.get("panelText", "").split("\n")[:20]:
            line = line.strip()
            if line:
                print(f"    > {line[:60]}")
    else:
        print("  Camera panel not found!")
        # Show what's on screen
        panel_text = page.evaluate("""() => {
            var p = document.querySelector('.c-gen-config.show');
            return p ? (p.innerText || '').substring(0, 400) : 'NO PANEL';
        }""")
        print(f"  Panel text: {panel_text[:300]}")

    # Try clicking "Free Selection" tab
    print("\n  Clicking 'Free Selection' tab...")
    free_sel = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return false;
        for (var el of panel.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            if (text === 'Free Selection') {
                el.click();
                return true;
            }
        }
        return false;
    }""")
    print(f"  Clicked: {free_sel}")
    page.wait_for_timeout(1000)

    screenshot(page, "p185_free_selection")

    # Re-map after switching to Free Selection
    free_movements = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return [];

        var knownMovements = ['Truck Left', 'Truck Right', 'Pan Left', 'Pan Right',
            'Push In', 'Pull Out', 'Pedestal Up', 'Pedestal Down',
            'Tilt Up', 'Tilt Down', 'Zoom In', 'Zoom Out',
            'Shake', 'Tracking Shot', 'Static Shot',
            'Arc Left', 'Arc Right', 'Dolly In', 'Dolly Out'];

        var results = [];
        for (var el of panel.querySelectorAll('*')) {
            var t = (el.innerText || '').trim();
            for (var m of knownMovements) {
                if (t === m) {
                    var rect = el.getBoundingClientRect();
                    if (rect.height > 0 && rect.height < 60) {
                        var cls = (typeof el.className === 'string') ? el.className : '';
                        results.push({
                            text: m,
                            tag: el.tagName,
                            class: cls.substring(0, 50),
                            x: Math.round(rect.x),
                            y: Math.round(rect.y),
                            w: Math.round(rect.width),
                            h: Math.round(rect.height),
                            active: cls.includes('active') || cls.includes('selected')
                        });
                    }
                    break;
                }
            }
        }

        // Deduplicate
        var seen = {};
        var unique = [];
        for (var m of results) {
            var key = m.text + '_' + m.y;
            if (!seen[key]) {
                seen[key] = true;
                unique.push(m);
            }
        }
        return unique;
    }""")

    print(f"\n  Free Selection movements ({len(free_movements)}):")
    for m in free_movements:
        active = " [ACTIVE]" if m.get("active") else ""
        print(f"    '{m['text']}' at ({m['x']},{m['y']}) {m['w']}x{m['h']} [{m['tag']}]{active}")

    # Test: Click Static Shot
    if free_movements:
        print("\n  Clicking 'Static Shot'...")
        clicked_static = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return false;
            for (var el of panel.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                if (text === 'Static Shot') {
                    var rect = el.getBoundingClientRect();
                    if (rect.height > 0 && rect.height < 60) {
                        el.click();
                        return true;
                    }
                }
            }
            return false;
        }""")
        print(f"  Clicked: {clicked_static}")
        page.wait_for_timeout(500)

        # Verify it's active
        static_state = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return {};
            for (var el of panel.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                if (text === 'Static Shot') {
                    var cls = (typeof el.className === 'string') ? el.className : '';
                    return {
                        text: text,
                        active: cls.includes('active') || cls.includes('selected'),
                        class: cls.substring(0, 50)
                    };
                }
            }
            return {};
        }""")
        print(f"  Static Shot state: {json.dumps(static_state)}")

    screenshot(page, "p185_static_shot")

    print("\n" + "=" * 70)
    print("EXPLORATION PART 14 COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
