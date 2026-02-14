#!/usr/bin/env python3
"""Dzine Deep Exploration Part 16 — Camera Panel Fix + Sound Effects + Face Swap.

1. Fix camera panel: expand via "Camera" row click, then Free Selection
2. Click Static Shot and Push In via mouse.click, verify active state
3. Explore Sound Effects (post-video action)
4. Try Face Swap from results action
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
    print("DZINE DEEP EXPLORATION PART 16")
    print("Camera Panel Fix + Sound Effects + Face Swap")
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
    # TASK 1: Camera Panel — Open via Results Panel AI Video action
    # ================================================================
    print("\n" + "=" * 70)
    print("TASK 1: Camera Panel — Proper Expansion")
    print("=" * 70)

    # Switch to Results tab and scroll to top
    page.evaluate("""() => {
        for (var el of document.querySelectorAll('[class*="header-item"]')) {
            if ((el.innerText || '').includes('Result')) { el.click(); return; }
        }
    }""")
    page.wait_for_timeout(500)

    # Scroll results to top
    page.evaluate("""() => {
        var containers = document.querySelectorAll('.result-panel, .material-v2-result-content, [class*="result"]');
        for (var c of containers) {
            if (c.scrollHeight > c.clientHeight + 50) c.scrollTop = 0;
        }
    }""")
    page.wait_for_timeout(500)

    # Click AI Video [1] from results action (auto-populates start frame)
    ai_video_clicked = page.evaluate("""() => {
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
    print(f"  AI Video [1] clicked: {ai_video_clicked}")
    page.wait_for_timeout(3000)

    # Now click the "Camera" section to expand it
    print("  Clicking Camera section to expand...")
    camera_expanded = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return {found: false, reason: 'no panel'};

        // Try clicking .camera-movement-btn first
        var camBtn = panel.querySelector('.camera-movement-btn');
        if (camBtn) {
            camBtn.click();
            return {found: true, method: 'camera-movement-btn'};
        }

        // Try clicking element containing "Camera" text
        for (var el of panel.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            if (text === 'Camera') {
                var rect = el.getBoundingClientRect();
                if (rect.height > 10 && rect.height < 60 && rect.width > 50) {
                    el.click();
                    return {found: true, method: 'text', y: Math.round(rect.y), h: Math.round(rect.height)};
                }
            }
        }

        // Try clicking parent row that contains camera icon
        for (var el of panel.querySelectorAll('[class*="camera"], [class*="movement"]')) {
            var rect = el.getBoundingClientRect();
            if (rect.height > 20 && rect.height < 60) {
                el.click();
                return {found: true, method: 'class', cls: el.className.substring(0, 40)};
            }
        }

        return {found: false, reason: 'no camera element'};
    }""")
    print(f"  Camera expand: {json.dumps(camera_expanded)}")
    page.wait_for_timeout(1500)

    # Check if camera popup/panel appeared
    camera_visible = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return {visible: false};
        var text = panel.innerText || '';
        var hasTabs = text.includes('Cinematic Shots') || text.includes('Free Selection');
        return {
            visible: hasTabs,
            panelText: text.substring(0, 300)
        };
    }""")
    print(f"  Camera tabs visible: {camera_visible.get('visible', False)}")

    if not camera_visible.get('visible'):
        # Maybe the camera opens as a floating overlay, not inside the config panel
        print("  Checking for floating camera overlay...")
        overlay = page.evaluate("""() => {
            var all = document.querySelectorAll('[class*="camera"], [class*="movement"], [class*="motion"]');
            var results = [];
            for (var el of all) {
                var rect = el.getBoundingClientRect();
                if (rect.height > 100 && rect.width > 200) {
                    var cls = (typeof el.className === 'string') ? el.className : '';
                    results.push({
                        cls: cls.substring(0, 60),
                        x: Math.round(rect.x),
                        y: Math.round(rect.y),
                        w: Math.round(rect.width),
                        h: Math.round(rect.height),
                        text: (el.innerText || '').substring(0, 100)
                    });
                }
            }
            return results;
        }""")
        if overlay:
            print(f"  Camera overlays ({len(overlay)}):")
            for o in overlay:
                print(f"    cls={o['cls']} at ({o['x']},{o['y']}) {o['w']}x{o['h']}")
                print(f"    text: {o['text'][:60]}")
        else:
            # Try mouse click at the Camera row position from p186_camera_fix
            print("  Trying mouse click at Camera row (200, 557)...")
            page.mouse.click(200, 557)
            page.wait_for_timeout(1500)

    screenshot(page, "p187_camera_expand")

    # Re-check for camera tabs
    camera_check = page.evaluate("""() => {
        // Check everywhere on the page for camera tabs
        var elements = document.querySelectorAll('*');
        for (var el of elements) {
            var text = (el.innerText || '').trim();
            if (text === 'Cinematic Shots' || text === 'Free Selection') {
                var rect = el.getBoundingClientRect();
                if (rect.height > 0) {
                    return {found: true, text: text, x: Math.round(rect.x), y: Math.round(rect.y)};
                }
            }
        }
        return {found: false};
    }""")
    print(f"  Camera tabs check: {json.dumps(camera_check)}")

    if camera_check.get('found'):
        # Click Free Selection
        print("  Clicking Free Selection tab...")
        page.evaluate("""() => {
            for (var el of document.querySelectorAll('*')) {
                if ((el.innerText || '').trim() === 'Free Selection') {
                    el.click(); return true;
                }
            }
            return false;
        }""")
        page.wait_for_timeout(800)

        # Map ALL elements in the camera area to find exact card structure
        print("  Mapping camera card structure...")
        card_structure = page.evaluate("""() => {
            var results = [];
            for (var el of document.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                if (text === 'Static Shot' || text === 'Push In') {
                    var rect = el.getBoundingClientRect();
                    if (rect.height > 0 && rect.height < 60) {
                        var cls = (typeof el.className === 'string') ? el.className : '';
                        // Get clickable parent
                        var parent = el.parentElement;
                        var pCls = parent ? ((typeof parent.className === 'string') ? parent.className : '') : '';
                        var pRect = parent ? parent.getBoundingClientRect() : {x:0,y:0,width:0,height:0};
                        var gp = parent ? parent.parentElement : null;
                        var gpCls = gp ? ((typeof gp.className === 'string') ? gp.className : '') : '';
                        var gpRect = gp ? gp.getBoundingClientRect() : {x:0,y:0,width:0,height:0};
                        results.push({
                            text: text,
                            cls: cls.substring(0, 50),
                            x: Math.round(rect.x), y: Math.round(rect.y),
                            w: Math.round(rect.width), h: Math.round(rect.height),
                            parentCls: pCls.substring(0, 50),
                            parentX: Math.round(pRect.x), parentY: Math.round(pRect.y),
                            parentW: Math.round(pRect.width), parentH: Math.round(pRect.height),
                            gpCls: gpCls.substring(0, 50),
                            gpX: Math.round(gpRect.x), gpY: Math.round(gpRect.y),
                            gpW: Math.round(gpRect.width), gpH: Math.round(gpRect.height)
                        });
                    }
                }
            }
            return results;
        }""")

        print(f"  Static Shot / Push In elements ({len(card_structure)}):")
        for c in card_structure:
            print(f"    '{c['text']}' at ({c['x']},{c['y']}) {c['w']}x{c['h']} cls={c['cls']}")
            print(f"      parent: cls={c['parentCls']} at ({c['parentX']},{c['parentY']}) {c['parentW']}x{c['parentH']}")
            print(f"      grandparent: cls={c['gpCls']} at ({c['gpX']},{c['gpY']}) {c['gpW']}x{c['gpH']}")

        # Try clicking via grandparent (the card container)
        print("\n  Attempting Static Shot click via card container...")
        for c in card_structure:
            if c['text'] == 'Static Shot' and c['gpW'] > 100:
                cx = c['gpX'] + c['gpW'] // 2
                cy = c['gpY'] + c['gpH'] // 2
                print(f"    Clicking grandparent center ({cx}, {cy})...")
                page.mouse.click(cx, cy)
                page.wait_for_timeout(800)

                # Check active state
                state = page.evaluate("""(targetText) => {
                    for (var el of document.querySelectorAll('*')) {
                        var text = (el.innerText || '').trim();
                        if (text === targetText) {
                            var p = el.parentElement;
                            var gp = p ? p.parentElement : null;
                            return {
                                elCls: ((typeof el.className === 'string') ? el.className : '').substring(0, 50),
                                pCls: p ? ((typeof p.className === 'string') ? p.className : '').substring(0, 50) : '',
                                gpCls: gp ? ((typeof gp.className === 'string') ? gp.className : '').substring(0, 50) : '',
                                elActive: ((typeof el.className === 'string') ? el.className : '').includes('active'),
                                pActive: p ? ((typeof p.className === 'string') ? p.className : '').includes('active') : false,
                                gpActive: gp ? ((typeof gp.className === 'string') ? gp.className : '').includes('active') : false
                            };
                        }
                    }
                    return {};
                }""", 'Static Shot')
                print(f"    State after click: {json.dumps(state)}")
                break

        # Try Push In
        print("\n  Attempting Push In click...")
        for c in card_structure:
            if c['text'] == 'Push In' and c['gpW'] > 50:
                cx = c['gpX'] + c['gpW'] // 2
                cy = c['gpY'] + c['gpH'] // 2
                print(f"    Clicking grandparent center ({cx}, {cy})...")
                page.mouse.click(cx, cy)
                page.wait_for_timeout(800)

                state = page.evaluate("""(targetText) => {
                    for (var el of document.querySelectorAll('*')) {
                        var text = (el.innerText || '').trim();
                        if (text === targetText) {
                            var p = el.parentElement;
                            var gp = p ? p.parentElement : null;
                            return {
                                pCls: p ? ((typeof p.className === 'string') ? p.className : '').substring(0, 50) : '',
                                gpCls: gp ? ((typeof gp.className === 'string') ? gp.className : '').substring(0, 50) : '',
                                pActive: p ? ((typeof p.className === 'string') ? p.className : '').includes('active') : false,
                                gpActive: gp ? ((typeof gp.className === 'string') ? gp.className : '').includes('active') : false
                            };
                        }
                    }
                    return {};
                }""", 'Push In')
                print(f"    State after click: {json.dumps(state)}")
                break

        screenshot(page, "p187_camera_buttons_clicked")

        # Final: show ALL active/selected elements in camera area
        all_active = page.evaluate("""() => {
            var results = [];
            for (var el of document.querySelectorAll('[class*="active"], [class*="selected"]')) {
                var rect = el.getBoundingClientRect();
                var text = (el.innerText || '').trim();
                if (rect.y > 60 && rect.y < 550 && text.length < 30 && rect.height > 0) {
                    var cls = (typeof el.className === 'string') ? el.className : '';
                    results.push({text: text, cls: cls.substring(0, 60), y: Math.round(rect.y)});
                }
            }
            return results;
        }""")
        print(f"\n  All active/selected after clicks ({len(all_active)}):")
        for a in all_active:
            print(f"    '{a['text'][:25]}' cls={a['cls']} y={a['y']}")

    # ================================================================
    # TASK 2: Try Face Swap from results action
    # ================================================================
    print("\n" + "=" * 70)
    print("TASK 2: Face Swap from Results Action")
    print("=" * 70)

    # Close camera overlay if open (press Escape)
    page.keyboard.press('Escape')
    page.wait_for_timeout(500)

    # Click Face Swap from results actions
    face_swap = page.evaluate("""() => {
        // Find Face Swap in results panel actions
        var buttons = document.querySelectorAll('.btn-container');
        for (var c of buttons) {
            var parent = c.parentElement;
            var parentText = (parent ? parent.innerText || '' : '').trim();
            if (parentText.startsWith('Face Swap')) {
                var btns = c.querySelectorAll('.btn');
                if (btns.length > 0) { btns[0].click(); return true; }
            }
        }
        // Try clicking "Face Swap" text button directly
        for (var el of document.querySelectorAll('button, [role="button"]')) {
            var text = (el.innerText || '').trim();
            if (text === 'Face Swap') {
                var rect = el.getBoundingClientRect();
                if (rect.x > 900) {  // Results panel side
                    el.click();
                    return true;
                }
            }
        }
        return false;
    }""")
    print(f"  Face Swap clicked: {face_swap}")
    page.wait_for_timeout(2000)

    # Map what opened
    face_panel = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return {text: 'NO PANEL'};
        return {panelText: (panel.innerText || '').substring(0, 400)};
    }""")
    print(f"  Panel after Face Swap:")
    for line in face_panel.get('panelText', '').split('\n')[:15]:
        line = line.strip()
        if line:
            print(f"    > {line[:60]}")

    screenshot(page, "p187_face_swap")

    # ================================================================
    # TASK 3: Explore video result actions — scroll to video result
    # ================================================================
    print("\n" + "=" * 70)
    print("TASK 3: Video Result Actions (Sound Effects)")
    print("=" * 70)

    # Switch to Results, scroll to find video result
    page.evaluate("""() => {
        for (var el of document.querySelectorAll('[class*="header-item"]')) {
            if ((el.innerText || '').includes('Result')) { el.click(); return; }
        }
    }""")
    page.wait_for_timeout(500)

    # Find and scroll to video result
    video_result = page.evaluate("""() => {
        var results = document.querySelectorAll('[class*="result-item"]');
        for (var r of results) {
            var cls = (typeof r.className === 'string') ? r.className : '';
            if (cls.includes('video') || cls.includes('i2v')) {
                r.scrollIntoView({behavior: 'instant', block: 'center'});
                var rect = r.getBoundingClientRect();
                return {
                    found: true,
                    cls: cls.substring(0, 60),
                    x: Math.round(rect.x),
                    y: Math.round(rect.y),
                    w: Math.round(rect.width),
                    h: Math.round(rect.height),
                    text: (r.innerText || '').substring(0, 200)
                };
            }
        }
        return {found: false};
    }""")
    print(f"  Video result: {json.dumps(video_result).get('found', False) if isinstance(video_result, dict) else 'error'}")

    if video_result.get('found'):
        print(f"  Video result at ({video_result['x']},{video_result['y']}) {video_result['w']}x{video_result['h']}")
        print(f"  Classes: {video_result['cls']}")

        # Map video result actions
        video_actions = page.evaluate("""() => {
            var results = document.querySelectorAll('[class*="result-item"]');
            for (var r of results) {
                var cls = (typeof r.className === 'string') ? r.className : '';
                if (cls.includes('video') || cls.includes('i2v')) {
                    var actions = [];
                    for (var btn of r.querySelectorAll('button, [role="button"], [class*="action"]')) {
                        var text = (btn.innerText || '').trim();
                        var rect = btn.getBoundingClientRect();
                        if (text && rect.height > 0 && text.length < 40) {
                            actions.push({
                                text: text,
                                x: Math.round(rect.x),
                                y: Math.round(rect.y),
                                w: Math.round(rect.width),
                                h: Math.round(rect.height)
                            });
                        }
                    }
                    return actions;
                }
            }
            return [];
        }""")
        print(f"\n  Video actions ({len(video_actions)}):")
        for a in video_actions:
            print(f"    '{a['text'][:30]}' at ({a['x']},{a['y']}) {a['w']}x{a['h']}")

        # Try clicking Sound Effects if available
        sound_clicked = page.evaluate("""() => {
            var results = document.querySelectorAll('[class*="result-item"]');
            for (var r of results) {
                var cls = (typeof r.className === 'string') ? r.className : '';
                if (cls.includes('video') || cls.includes('i2v')) {
                    for (var btn of r.querySelectorAll('button, [role="button"], div')) {
                        var text = (btn.innerText || '').trim();
                        if (text === 'Sound Effects') {
                            btn.click();
                            return true;
                        }
                    }
                }
            }
            return false;
        }""")
        print(f"\n  Sound Effects clicked: {sound_clicked}")
        page.wait_for_timeout(2000)

        if sound_clicked:
            # Map the Sound Effects panel
            sound_panel = page.evaluate("""() => {
                // Check for popups or panels
                var all = document.querySelectorAll('.popup, .modal, .dialog, [class*="sound"], [class*="effect"]');
                var results = [];
                for (var el of all) {
                    var rect = el.getBoundingClientRect();
                    if (rect.height > 100 && rect.width > 100) {
                        results.push({
                            cls: ((typeof el.className === 'string') ? el.className : '').substring(0, 60),
                            text: (el.innerText || '').substring(0, 300),
                            x: Math.round(rect.x),
                            y: Math.round(rect.y),
                            w: Math.round(rect.width),
                            h: Math.round(rect.height)
                        });
                    }
                }
                // Also check for any new panel
                var panel = document.querySelector('.c-gen-config.show');
                if (panel) {
                    results.push({
                        cls: 'c-gen-config.show',
                        text: (panel.innerText || '').substring(0, 300),
                        x: 0, y: 0, w: 0, h: 0
                    });
                }
                return results;
            }""")
            print(f"  Sound Effects panels ({len(sound_panel)}):")
            for p in sound_panel:
                print(f"    cls={p['cls']}")
                print(f"    text: {p['text'][:100]}")

            screenshot(page, "p187_sound_effects")

    # ================================================================
    # TASK 4: Sidebar tool count + full sidebar map
    # ================================================================
    print("\n" + "=" * 70)
    print("TASK 4: Full Sidebar Map")
    print("=" * 70)

    sidebar = page.evaluate("""() => {
        var results = [];
        // Map all sidebar tool icons
        var sidebar = document.querySelector('.left-tools, .tool-group, [class*="sidebar"]');
        if (!sidebar) {
            // Fall back to elements at x < 70
            for (var el of document.querySelectorAll('*')) {
                var rect = el.getBoundingClientRect();
                if (rect.x < 70 && rect.x >= 0 && rect.width > 20 && rect.width < 80 &&
                    rect.height > 20 && rect.height < 80 && rect.y > 60) {
                    var text = (el.innerText || '').trim();
                    if (text && text.length < 25 && !text.includes('\\n')) {
                        var cls = (typeof el.className === 'string') ? el.className : '';
                        results.push({
                            text: text,
                            y: Math.round(rect.y),
                            h: Math.round(rect.height),
                            w: Math.round(rect.width),
                            cls: cls.substring(0, 40)
                        });
                    }
                }
            }
        }
        return results;
    }""")

    print(f"  Sidebar items ({len(sidebar)}):")
    sidebar.sort(key=lambda x: x['y'])
    for s in sidebar:
        print(f"    y={s['y']} h={s['h']} '{s['text']}' cls={s['cls'][:30]}")

    print("\n" + "=" * 70)
    print("EXPLORATION PART 16 COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
