"""Phase 62: CC Style toggle via Vue event dispatch, CC panel container analysis.

From P61:
- Style switch at DOM index 408, (0,0) with 0x0 dimensions
- Even at 1500px viewport, still not visible
- JS click() doesn't trigger Vue reactivity
- Panel clips content at viewport bottom without scroll

Goals:
1. Analyze WHY Style is at (0,0) — check parent chain display/visibility
2. Try Vue event dispatch (mousedown + mouseup + click) on Style switch
3. If Style still won't activate, accept and document the limitation
4. Use remaining time for productive work: test CC camera control, Pose mode
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

    # Open CC → Generate Images → Ray
    page.mouse.dblclick(40, 306)
    page.wait_for_timeout(2000)
    close_dialogs(page)

    page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text === 'Generate Images' && r.x > 60 && r.y > 80 && r.y < 250 && r.height < 50) {
                el.click(); return true;
            }
        }
        return false;
    }""")
    page.wait_for_timeout(2000)
    page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            if ((el.innerText || '').trim() === 'Ray' && el.tagName === 'BUTTON') { el.click(); return true; }
        }
        return false;
    }""")
    page.wait_for_timeout(2000)
    close_dialogs(page)

    # ============================================================
    #  PART 1: ANALYZE STYLE SWITCH PARENT CHAIN
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 1: STYLE SWITCH PARENT CHAIN ANALYSIS", flush=True)
    print("=" * 60, flush=True)

    parent_chain = page.evaluate("""() => {
        // Find the Style switch
        var switches = document.querySelectorAll('button');
        for (var i = 0; i < switches.length; i++) {
            var sw = switches[i];
            var classes = (sw.className || '').toString();
            if (!classes.includes('switch')) continue;
            var parent = sw.parentElement;
            for (var p = 0; p < 5 && parent; p++) {
                var texts = (parent.innerText || '').trim().split('\\n');
                for (var t of texts) {
                    if (t.trim() === 'Style') {
                        // Found! Now trace parent chain up
                        var chain = [];
                        var el = sw;
                        while (el && chain.length < 15) {
                            var r = el.getBoundingClientRect();
                            var style = window.getComputedStyle(el);
                            chain.push({
                                tag: el.tagName,
                                classes: (el.className || '').toString().substring(0, 50),
                                x: Math.round(r.x), y: Math.round(r.y),
                                w: Math.round(r.width), h: Math.round(r.height),
                                display: style.display,
                                visibility: style.visibility,
                                overflow: style.overflow + '/' + style.overflowY,
                                position: style.position,
                                opacity: style.opacity,
                            });
                            el = el.parentElement;
                        }
                        return chain;
                    }
                }
                parent = parent.parentElement;
            }
        }
        return null;
    }""")

    if parent_chain:
        print(f"  Style switch parent chain ({len(parent_chain)} levels):", flush=True)
        for i, p in enumerate(parent_chain):
            print(f"    [{i}] <{p['tag']}> ({p['x']},{p['y']}) {p['w']}x{p['h']} "
                  f"display={p['display']} vis={p['visibility']} overflow={p['overflow']} "
                  f"pos={p['position']} opacity={p['opacity']} c='{p['classes'][:40]}'", flush=True)
    else:
        print("  Style switch not found in parent chain analysis", flush=True)

    # ============================================================
    #  PART 2: TRY SCROLLINTO VIEW + PROPER EVENT DISPATCH
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 2: SCROLLINTOVIEW + EVENT DISPATCH", flush=True)
    print("=" * 60, flush=True)

    scroll_result = page.evaluate("""() => {
        var switches = document.querySelectorAll('button');
        for (var i = 0; i < switches.length; i++) {
            var sw = switches[i];
            var classes = (sw.className || '').toString();
            if (!classes.includes('switch')) continue;
            var parent = sw.parentElement;
            for (var p = 0; p < 5 && parent; p++) {
                var texts = (parent.innerText || '').trim().split('\\n');
                for (var t of texts) {
                    if (t.trim() === 'Style') {
                        // Try scrollIntoView
                        sw.scrollIntoView({block: 'center', behavior: 'instant'});
                        var r = sw.getBoundingClientRect();
                        return {
                            afterScrollX: Math.round(r.x), afterScrollY: Math.round(r.y),
                            afterScrollW: Math.round(r.width), afterScrollH: Math.round(r.height),
                        };
                    }
                }
                parent = parent.parentElement;
            }
        }
        return null;
    }""")
    print(f"  After scrollIntoView: {scroll_result}", flush=True)
    page.wait_for_timeout(500)

    if scroll_result and scroll_result.get('afterScrollW', 0) > 0:
        ss(page, "P62_01_after_scrollintoview")

        # Now try clicking it
        x = scroll_result['afterScrollX'] + scroll_result['afterScrollW'] // 2
        y = scroll_result['afterScrollY'] + scroll_result['afterScrollH'] // 2
        print(f"  Clicking at ({x},{y})...", flush=True)
        page.mouse.click(x, y)
        page.wait_for_timeout(2000)
        close_dialogs(page)

        ss(page, "P62_02_after_style_click")

        # Check for new elements
        new_els = page.evaluate("""() => {
            var items = [];
            for (const el of document.querySelectorAll('.c-style, .style-name, .config-param')) {
                var text = (el.innerText || '').trim();
                var r = el.getBoundingClientRect();
                if (r.x > 60 && r.x < 400 && r.y > 0 && r.y < 900 && r.width > 20) {
                    items.push({
                        text: text.substring(0, 60),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width),
                        classes: (el.className || '').toString().substring(0, 40),
                    });
                }
            }
            return items.sort(function(a,b) { return a.y - b.y; });
        }""")
        print(f"\n  Panel elements after Style toggle ({len(new_els)}):", flush=True)
        for ne in new_els:
            print(f"    ({ne['x']},{ne['y']}) w={ne['w']} c='{ne['classes'][:25]}' '{ne['text'][:50]}'", flush=True)
    else:
        print("  scrollIntoView didn't make Style visible (still 0x0)", flush=True)

        # Try Vue-style event dispatch
        print("\n  Trying Vue event dispatch...", flush=True)
        vue_result = page.evaluate("""() => {
            var switches = document.querySelectorAll('button');
            for (var i = 0; i < switches.length; i++) {
                var sw = switches[i];
                var classes = (sw.className || '').toString();
                if (!classes.includes('switch')) continue;
                var parent = sw.parentElement;
                for (var p = 0; p < 5 && parent; p++) {
                    var texts = (parent.innerText || '').trim().split('\\n');
                    for (var t of texts) {
                        if (t.trim() === 'Style') {
                            // Vue uses synthetic events
                            sw.dispatchEvent(new MouseEvent('mousedown', {bubbles: true}));
                            sw.dispatchEvent(new MouseEvent('mouseup', {bubbles: true}));
                            sw.dispatchEvent(new MouseEvent('click', {bubbles: true}));
                            // Also try input/change events
                            sw.dispatchEvent(new Event('input', {bubbles: true}));
                            sw.dispatchEvent(new Event('change', {bubbles: true}));
                            // Check class after dispatch
                            return {
                                classesAfter: (sw.className || '').toString().substring(0, 40),
                                classChanged: classes !== (sw.className || '').toString(),
                            };
                        }
                    }
                    parent = parent.parentElement;
                }
            }
            return null;
        }""")
        print(f"  Vue dispatch result: {vue_result}", flush=True)
        page.wait_for_timeout(2000)

        ss(page, "P62_03_vue_dispatch")

    # ============================================================
    #  PART 3: CC CAMERA CONTROL
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 3: CC CAMERA CONTROL", flush=True)
    print("=" * 60, flush=True)

    # Find and click the Camera control button
    camera_btn = page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            var classes = (el.className || '').toString();
            if (classes.includes('camera-movement') && r.x > 60 && r.x < 370
                && r.y > 0 && r.y < 900 && r.width > 100) {
                return {
                    text: text.substring(0, 40),
                    x: Math.round(r.x + r.width/2),
                    y: Math.round(r.y + r.height/2),
                    classes: classes.substring(0, 40),
                };
            }
        }
        return null;
    }""")
    print(f"  Camera button: {camera_btn}", flush=True)

    if camera_btn:
        print(f"  Clicking Camera at ({camera_btn['x']},{camera_btn['y']})...", flush=True)
        page.mouse.click(camera_btn['x'], camera_btn['y'])
        page.wait_for_timeout(2000)
        close_dialogs(page)

        ss(page, "P62_04_camera_dialog")

        # Dump the camera dialog (should be a popup or modal)
        camera_dialog = page.evaluate("""() => {
            var items = [];
            for (const el of document.querySelectorAll('*')) {
                var style = window.getComputedStyle(el);
                var z = parseInt(style.zIndex) || 0;
                var r = el.getBoundingClientRect();
                var text = (el.innerText || '').trim();
                if (z > 50 && r.width > 30 && r.height > 10
                    && text.length > 0 && text.length < 60) {
                    items.push({
                        text: text.substring(0, 50),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        z: z, tag: el.tagName,
                        classes: (el.className || '').toString().substring(0, 30),
                    });
                }
            }
            var seen = new Set();
            return items.filter(function(i) {
                var key = i.text.substring(0,15) + '|' + Math.round(i.y/3);
                if (seen.has(key)) return false;
                seen.add(key);
                return true;
            }).sort(function(a,b) { return a.y - b.y; }).slice(0, 30);
        }""")
        print(f"\n  Camera dialog ({len(camera_dialog)}):", flush=True)
        for cd in camera_dialog:
            print(f"    ({cd['x']},{cd['y']}) {cd['w']}x{cd['h']} z={cd['z']} <{cd['tag']}> c='{cd['classes'][:22]}' '{cd['text'][:45]}'", flush=True)

        page.keyboard.press("Escape")
        page.wait_for_timeout(500)

    # ============================================================
    #  PART 4: CC POSE MODE
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 4: CC POSE MODE", flush=True)
    print("=" * 60, flush=True)

    # Click Pose button
    pose_clicked = page.evaluate("""() => {
        for (const btn of document.querySelectorAll('button.options')) {
            var text = (btn.innerText || '').trim();
            var r = btn.getBoundingClientRect();
            if (text === 'Pose' && r.x > 60 && r.x < 370 && r.y > 0 && r.y < 900) {
                btn.click();
                return {x: Math.round(r.x), y: Math.round(r.y)};
            }
        }
        return null;
    }""")
    print(f"  Clicked Pose: {pose_clicked}", flush=True)
    page.wait_for_timeout(1500)
    close_dialogs(page)

    if pose_clicked:
        ss(page, "P62_05_pose_mode")

        # Check what appeared under Pose mode
        pose_content = page.evaluate("""() => {
            var items = [];
            for (const el of document.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                var r = el.getBoundingClientRect();
                var classes = (el.className || '').toString();
                if (r.x > 60 && r.x < 370 && r.y > 0 && r.y < 900
                    && r.width > 30 && r.height > 10
                    && text.length > 1 && text.length < 60
                    && (classes.includes('pose') || classes.includes('pick')
                        || classes.includes('upload') || classes.includes('beta')
                        || text.includes('Pose') || text.includes('Upload')
                        || text.includes('image') || text.includes('select'))) {
                    items.push({
                        text: text.substring(0, 50),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        tag: el.tagName,
                        classes: classes.substring(0, 40),
                    });
                }
            }
            var seen = new Set();
            return items.filter(function(i) {
                var key = i.text.substring(0,15) + '|' + Math.round(i.y);
                if (seen.has(key)) return false;
                seen.add(key);
                return true;
            }).sort(function(a,b) { return a.y - b.y; }).slice(0, 15);
        }""")
        print(f"\n  Pose mode content ({len(pose_content)}):", flush=True)
        for pc in pose_content:
            print(f"    ({pc['x']},{pc['y']}) {pc['w']}x{pc['h']} <{pc['tag']}> c='{pc['classes'][:25]}' '{pc['text'][:45]}'", flush=True)

        # Check for Pose Mode BETA switch
        pose_switch = page.evaluate("""() => {
            for (const el of document.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                var r = el.getBoundingClientRect();
                if (text.includes('Pose Mode') && r.x > 60 && r.x < 370 && r.y > 0 && r.y < 900) {
                    return {text: text, x: Math.round(r.x), y: Math.round(r.y)};
                }
            }
            return null;
        }""")
        print(f"  Pose Mode label: {pose_switch}", flush=True)

        # Switch back to Camera mode
        page.evaluate("""() => {
            for (const btn of document.querySelectorAll('button.options')) {
                var text = (btn.innerText || '').trim();
                if (text === 'Camera') { btn.click(); return true; }
            }
            return false;
        }""")
        page.wait_for_timeout(500)

    # ============================================================
    #  PART 5: CC REFERENCE MODE
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 5: CC REFERENCE MODE", flush=True)
    print("=" * 60, flush=True)

    # Click Reference button
    ref_clicked = page.evaluate("""() => {
        for (const btn of document.querySelectorAll('button.options')) {
            var text = (btn.innerText || '').trim();
            var r = btn.getBoundingClientRect();
            if (text === 'Reference' && r.x > 60 && r.x < 370 && r.y > 0 && r.y < 900) {
                btn.click();
                return {x: Math.round(r.x), y: Math.round(r.y)};
            }
        }
        return null;
    }""")
    print(f"  Clicked Reference: {ref_clicked}", flush=True)
    page.wait_for_timeout(1500)
    close_dialogs(page)

    if ref_clicked:
        ss(page, "P62_06_reference_mode")

        # Check what appeared
        ref_content = page.evaluate("""() => {
            var items = [];
            for (const el of document.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                var r = el.getBoundingClientRect();
                var classes = (el.className || '').toString();
                if (r.x > 60 && r.x < 370 && r.y > 0 && r.y < 900
                    && r.width > 30 && r.height > 10
                    && text.length > 1 && text.length < 60
                    && (classes.includes('pick') || classes.includes('reference')
                        || classes.includes('upload') || classes.includes('image')
                        || text.includes('Pick') || text.includes('Reference')
                        || text.includes('image') || text.includes('Upload'))) {
                    items.push({
                        text: text.substring(0, 50),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        tag: el.tagName,
                        classes: classes.substring(0, 40),
                    });
                }
            }
            var seen = new Set();
            return items.filter(function(i) {
                var key = i.text.substring(0,15) + '|' + Math.round(i.y);
                if (seen.has(key)) return false;
                seen.add(key);
                return true;
            }).sort(function(a,b) { return a.y - b.y; }).slice(0, 15);
        }""")
        print(f"\n  Reference mode content ({len(ref_content)}):", flush=True)
        for rc in ref_content:
            print(f"    ({rc['x']},{rc['y']}) {rc['w']}x{rc['h']} <{rc['tag']}> c='{rc['classes'][:25]}' '{rc['text'][:45]}'", flush=True)

        # Switch back to Camera
        page.evaluate("""() => {
            for (const btn of document.querySelectorAll('button.options')) {
                var text = (btn.innerText || '').trim();
                if (text === 'Camera') { btn.click(); return true; }
            }
            return false;
        }""")
        page.wait_for_timeout(500)

    ss(page, "P62_07_final")

    print(f"\n\n===== PHASE 62 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
