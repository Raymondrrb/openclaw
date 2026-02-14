#!/usr/bin/env python3
"""Dzine Deep Exploration Part 17 — Camera Active State + Sound Effects.

1. Compare active vs inactive camera card CSS (computed styles, data attributes)
2. Try dispatchEvent click instead of .click()
3. Find video result and explore Sound Effects
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
    print("DZINE DEEP EXPLORATION PART 17")
    print("Camera Active State + Sound Effects")
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
    # TASK 1: Camera Active State — Deep CSS Comparison
    # ================================================================
    print("\n" + "=" * 70)
    print("TASK 1: Camera Active State Investigation")
    print("=" * 70)

    # Open AI Video via results action
    page.evaluate("""() => {
        for (var el of document.querySelectorAll('[class*="header-item"]')) {
            if ((el.innerText || '').includes('Result')) { el.click(); return; }
        }
    }""")
    page.wait_for_timeout(500)
    page.evaluate("""() => {
        var containers = document.querySelectorAll('.result-panel, .material-v2-result-content, [class*="result"]');
        for (var c of containers) {
            if (c.scrollHeight > c.clientHeight + 50) c.scrollTop = 0;
        }
    }""")
    page.wait_for_timeout(500)

    page.evaluate("""() => {
        var containers = document.querySelectorAll('.btn-container');
        for (var c of containers) {
            var parent = c.parentElement;
            var parentText = (parent ? parent.innerText || '' : '').trim();
            if (parentText.startsWith('AI Video')) {
                var btns = c.querySelectorAll('.btn');
                if (btns.length > 0) { btns[0].click(); return true; }
            }
        }
        return false;
    }""")
    page.wait_for_timeout(3000)

    # Expand camera
    page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return;
        var camBtn = panel.querySelector('.camera-movement-btn');
        if (camBtn) camBtn.click();
    }""")
    page.wait_for_timeout(1000)

    # Free Selection tab
    page.evaluate("""() => {
        for (var el of document.querySelectorAll('*')) {
            if ((el.innerText || '').trim() === 'Free Selection') { el.click(); return; }
        }
    }""")
    page.wait_for_timeout(1000)

    # Compare Truck Left (known active/orange) vs Static Shot (known inactive)
    comparison = page.evaluate("""() => {
        var results = {};
        var targets = ['Truck Left', 'Static Shot', 'Push In'];

        for (var target of targets) {
            for (var el of document.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                if (text === target) {
                    var rect = el.getBoundingClientRect();
                    // Find the selection-item ancestor
                    if (rect.height >= 30 && rect.height <= 50) {
                        var current = el;
                        var hierarchy = [];
                        for (var i = 0; i < 5; i++) {
                            var cls = (typeof current.className === 'string') ? current.className : '';
                            var attrs = {};
                            for (var a of current.attributes || []) {
                                if (a.name !== 'class' && a.name !== 'style') {
                                    attrs[a.name] = a.value;
                                }
                            }
                            var computed = window.getComputedStyle(current);
                            hierarchy.push({
                                tag: current.tagName,
                                cls: cls,
                                attrs: attrs,
                                borderColor: computed.borderColor,
                                borderWidth: computed.borderWidth,
                                opacity: computed.opacity,
                                bgColor: computed.backgroundColor
                            });
                            current = current.parentElement;
                            if (!current) break;
                        }
                        results[target] = hierarchy;
                        break;
                    }
                }
            }
        }
        return results;
    }""")

    for name, hierarchy in comparison.items():
        print(f"\n  {name}:")
        for i, level in enumerate(hierarchy):
            border = level.get('borderColor', '')
            bw = level.get('borderWidth', '')
            bg = level.get('bgColor', '')
            attrs = level.get('attrs', {})
            print(f"    L{i} [{level['tag']}] cls=\"{level['cls'][:50]}\"")
            if attrs:
                print(f"        attrs: {json.dumps(attrs)}")
            if 'rgb(0, 0, 0)' not in border and 'rgba(0, 0, 0, 0)' not in border:
                print(f"        border: {border} width={bw}")
            if bg and 'rgba(0, 0, 0, 0)' not in bg:
                print(f"        bg: {bg}")

    # Check for data attributes or aria attributes that indicate state
    state_attrs = page.evaluate("""() => {
        var results = {};
        var names = ['Truck Left', 'Truck Right', 'Pan Left', 'Pan Right',
                     'Push In', 'Pull Out', 'Static Shot', 'Shake'];

        for (var name of names) {
            for (var el of document.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                if (text === name) {
                    var rect = el.getBoundingClientRect();
                    if (rect.height >= 30 && rect.height <= 50) {
                        // Check self and up to 3 parents for any state indicator
                        var current = el;
                        var info = {};
                        for (var i = 0; i < 4; i++) {
                            var cls = (typeof current.className === 'string') ? current.className : '';
                            for (var a of current.attributes || []) {
                                if (a.name.startsWith('data-') || a.name.startsWith('aria-')) {
                                    info[i + '_' + a.name] = a.value;
                                }
                            }
                            if (cls.includes('active') || cls.includes('selected') ||
                                cls.includes('checked') || cls.includes('highlight') ||
                                cls.includes('chosen') || cls.includes('on') ||
                                cls.includes('enabled') || cls.includes('picked')) {
                                info[i + '_cls_match'] = cls.substring(0, 50);
                            }
                            current = current.parentElement;
                            if (!current) break;
                        }
                        results[name] = info;
                        break;
                    }
                }
            }
        }
        return results;
    }""")

    print(f"\n  State attributes:")
    for name, attrs in state_attrs.items():
        if attrs:
            print(f"    {name}: {json.dumps(attrs)}")
        else:
            print(f"    {name}: (no state attrs)")

    # Try using React internals to check state
    react_state = page.evaluate("""() => {
        var results = {};
        var names = ['Truck Left', 'Static Shot'];
        for (var name of names) {
            for (var el of document.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                if (text === name) {
                    var rect = el.getBoundingClientRect();
                    if (rect.height >= 100 && rect.height <= 120) {
                        // This should be selection-item
                        // Check React fiber
                        var fiber = null;
                        for (var key of Object.keys(el)) {
                            if (key.startsWith('__reactFiber') || key.startsWith('__reactInternalInstance')) {
                                fiber = key;
                                break;
                            }
                        }
                        if (fiber) {
                            var f = el[fiber];
                            var props = f && f.memoizedProps ? f.memoizedProps : {};
                            results[name] = {
                                hasFiber: true,
                                className: props.className || '',
                                onClick: typeof props.onClick === 'function',
                                selected: props.selected,
                                active: props.active,
                                checked: props.checked,
                                keys: Object.keys(props).filter(function(k) { return k !== 'children' && k !== 'style'; }).join(', ')
                            };
                        } else {
                            results[name] = {hasFiber: false};
                        }
                        break;
                    }
                }
            }
        }
        return results;
    }""")

    print(f"\n  React state:")
    for name, state in react_state.items():
        print(f"    {name}: {json.dumps(state)}")

    # Direct approach: just try clicking the option element and use React click
    print("\n  Trying React synthetic click on Static Shot...")
    react_click = page.evaluate("""() => {
        for (var el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            if (text === 'Static Shot') {
                var rect = el.getBoundingClientRect();
                // Find the selection-item ancestor (height ~112)
                if (rect.height >= 100 && rect.height <= 120) {
                    // Dispatch mousedown + mouseup + click sequence
                    var event1 = new MouseEvent('mousedown', {bubbles: true, cancelable: true});
                    var event2 = new MouseEvent('mouseup', {bubbles: true, cancelable: true});
                    var event3 = new MouseEvent('click', {bubbles: true, cancelable: true});
                    el.dispatchEvent(event1);
                    el.dispatchEvent(event2);
                    el.dispatchEvent(event3);
                    return {clicked: true, cls: ((typeof el.className === 'string') ? el.className : '').substring(0, 50)};
                }
            }
        }
        return {clicked: false};
    }""")
    print(f"  React click result: {json.dumps(react_click)}")
    page.wait_for_timeout(800)

    # Check if anything changed
    post_click = page.evaluate("""() => {
        var names = ['Truck Left', 'Static Shot', 'Push In'];
        var results = {};
        for (var name of names) {
            for (var el of document.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                if (text === name) {
                    var rect = el.getBoundingClientRect();
                    if (rect.height >= 100 && rect.height <= 120) {
                        var cls = (typeof el.className === 'string') ? el.className : '';
                        var computed = window.getComputedStyle(el);
                        results[name] = {
                            cls: cls,
                            borderColor: computed.borderColor,
                            borderWidth: computed.borderWidth
                        };
                        break;
                    }
                }
            }
        }
        return results;
    }""")
    print(f"\n  Post-click comparison:")
    for name, state in post_click.items():
        print(f"    {name}: cls={state.get('cls', '')} border={state.get('borderColor', '')} bw={state.get('borderWidth', '')}")

    screenshot(page, "p188_camera_deep")

    # ================================================================
    # TASK 2: Find Video Result + Sound Effects
    # ================================================================
    print("\n" + "=" * 70)
    print("TASK 2: Video Result + Sound Effects")
    print("=" * 70)

    # Close camera overlay
    page.keyboard.press('Escape')
    page.wait_for_timeout(500)

    # Switch to Results
    page.evaluate("""() => {
        for (var el of document.querySelectorAll('[class*="header-item"]')) {
            if ((el.innerText || '').includes('Result')) { el.click(); return; }
        }
    }""")
    page.wait_for_timeout(500)

    # Scroll to find video results
    video_found = page.evaluate("""() => {
        // Look for elements with 'video' or 'i2v' or 'image-to-video' in class
        var resultContainer = null;
        for (var c of document.querySelectorAll('[class*="result"]')) {
            if (c.scrollHeight > c.clientHeight + 100) {
                resultContainer = c;
                break;
            }
        }

        if (!resultContainer) return {found: false, reason: 'no scrollable container'};

        // Scroll down through results
        var items = resultContainer.querySelectorAll('[class*="result-item"]');
        var videoItems = [];
        for (var item of items) {
            var cls = (typeof item.className === 'string') ? item.className : '';
            if (cls.includes('video') || cls.includes('i2v')) {
                item.scrollIntoView({behavior: 'instant', block: 'center'});
                var rect = item.getBoundingClientRect();
                var text = (item.innerText || '').substring(0, 200);
                videoItems.push({
                    cls: cls.substring(0, 60),
                    y: Math.round(rect.y),
                    h: Math.round(rect.height),
                    text: text
                });
            }
        }

        if (videoItems.length === 0) {
            // Try scrolling to bottom
            resultContainer.scrollTop = resultContainer.scrollHeight;
            return {found: false, reason: 'no video items found', totalItems: items.length};
        }
        return {found: true, videos: videoItems};
    }""")

    print(f"  Video search: {json.dumps(video_found)}")
    page.wait_for_timeout(1000)

    if video_found.get('found') and video_found.get('videos'):
        screenshot(page, "p188_video_result")

        # Map buttons/actions on the video result
        video_buttons = page.evaluate("""() => {
            var results = [];
            for (var item of document.querySelectorAll('[class*="result-item"]')) {
                var cls = (typeof item.className === 'string') ? item.className : '';
                if (cls.includes('video') || cls.includes('i2v')) {
                    // Map all clickable descendants
                    for (var el of item.querySelectorAll('button, a, [role="button"], [class*="action"], [class*="btn"]')) {
                        var text = (el.innerText || '').trim();
                        var rect = el.getBoundingClientRect();
                        if (rect.height > 0 && text && text.length < 40) {
                            var elCls = (typeof el.className === 'string') ? el.className : '';
                            results.push({
                                text: text,
                                tag: el.tagName,
                                cls: elCls.substring(0, 40),
                                x: Math.round(rect.x),
                                y: Math.round(rect.y),
                                w: Math.round(rect.width),
                                h: Math.round(rect.height)
                            });
                        }
                    }
                    break;
                }
            }
            return results;
        }""")

        print(f"\n  Video result buttons ({len(video_buttons)}):")
        for b in video_buttons:
            print(f"    [{b['tag'][:4]}] '{b['text'][:30]}' at ({b['x']},{b['y']}) {b['w']}x{b['h']} cls={b['cls'][:30]}")

        # Click Sound Effects
        sound_clicked = page.evaluate("""() => {
            for (var item of document.querySelectorAll('[class*="result-item"]')) {
                var cls = (typeof item.className === 'string') ? item.className : '';
                if (cls.includes('video') || cls.includes('i2v')) {
                    for (var el of item.querySelectorAll('button, [role="button"], div')) {
                        if ((el.innerText || '').trim() === 'Sound Effects') {
                            el.click();
                            return true;
                        }
                    }
                }
            }
            return false;
        }""")
        print(f"\n  Sound Effects clicked: {sound_clicked}")
        page.wait_for_timeout(3000)

        if sound_clicked:
            # Map what opened
            sound_data = page.evaluate("""() => {
                // Check for any new panel, popup, or overlay
                var panel = document.querySelector('.c-gen-config.show');
                var panelText = panel ? (panel.innerText || '').substring(0, 400) : '';

                // Check for popup/modal
                var popups = [];
                for (var el of document.querySelectorAll('.popup, .modal, [class*="dialog"], [class*="popup"], [class*="overlay"]')) {
                    var rect = el.getBoundingClientRect();
                    if (rect.height > 100 && rect.width > 100) {
                        popups.push({
                            cls: ((typeof el.className === 'string') ? el.className : '').substring(0, 60),
                            text: (el.innerText || '').substring(0, 200),
                            x: Math.round(rect.x),
                            y: Math.round(rect.y),
                            w: Math.round(rect.width),
                            h: Math.round(rect.height)
                        });
                    }
                }

                // Check if URL changed
                return {
                    url: window.location.href,
                    panelText: panelText,
                    popups: popups
                };
            }""")

            print(f"  URL: {sound_data.get('url', '')}")
            print(f"  Panel text:")
            for line in sound_data.get('panelText', '').split('\n')[:10]:
                line = line.strip()
                if line:
                    print(f"    > {line[:60]}")
            if sound_data.get('popups'):
                print(f"  Popups ({len(sound_data['popups'])}):")
                for p in sound_data['popups']:
                    print(f"    cls={p['cls']}")
                    print(f"    text: {p['text'][:100]}")

            screenshot(page, "p188_sound_effects")
    else:
        print("  No video results found, scrolling...")
        # Try scrolling the results panel down
        page.evaluate("""() => {
            for (var c of document.querySelectorAll('[class*="result"]')) {
                if (c.scrollHeight > c.clientHeight + 100) {
                    c.scrollTop = c.scrollHeight;
                }
            }
        }""")
        page.wait_for_timeout(1000)
        screenshot(page, "p188_results_scrolled")

        # Check total content
        total = page.evaluate("""() => {
            var items = document.querySelectorAll('[class*="result-item"]');
            var info = [];
            for (var item of items) {
                var cls = (typeof item.className === 'string') ? item.className : '';
                var label = (item.innerText || '').substring(0, 50).split('\\n')[0];
                info.push(cls.substring(0, 40) + ' | ' + label);
            }
            return info;
        }""")
        print(f"  All result items ({len(total)}):")
        for t in total:
            print(f"    {t}")

    print("\n" + "=" * 70)
    print("EXPLORATION PART 17 COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
