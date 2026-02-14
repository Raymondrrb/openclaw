#!/usr/bin/env python3
"""Dzine Deep Exploration Part 18 — Camera CSS Debug + Video Actions.

1. Open camera panel properly, compare computed styles of active vs inactive cards
2. Try mouse.click at exact card center coordinates
3. Sound Effects via mouse.click on visible button
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


def main():
    print("=" * 70)
    print("DZINE DEEP EXPLORATION PART 18")
    print("Camera CSS Debug + Video Actions")
    print("=" * 70)

    browser, context, _, _pw = connect_or_launch()
    page = context.pages[0]
    print(f"Connected. URL: {page.url}")

    if "dzine.ai/canvas" not in page.url:
        page.goto("https://www.dzine.ai/canvas?id=19861203")
        page.wait_for_timeout(5000)

    # ================================================================
    # TASK 1: Camera — Open, Expand, Compare Active vs Inactive
    # ================================================================
    print("\n" + "=" * 70)
    print("TASK 1: Camera Panel — CSS Comparison")
    print("=" * 70)

    # Use AI Video via results action
    page.evaluate("""() => {
        for (var el of document.querySelectorAll('[class*="header-item"]')) {
            if ((el.innerText || '').includes('Result')) { el.click(); return; }
        }
    }""")
    page.wait_for_timeout(500)
    page.evaluate("""() => {
        var containers = document.querySelectorAll('[class*="result"]');
        for (var c of containers) {
            if (c.scrollHeight > c.clientHeight + 50) c.scrollTop = 0;
        }
    }""")
    page.wait_for_timeout(500)

    page.evaluate("""() => {
        var containers = document.querySelectorAll('.btn-container');
        for (var c of containers) {
            var parent = c.parentElement;
            if (parent && (parent.innerText || '').trim().startsWith('AI Video')) {
                var btns = c.querySelectorAll('.btn');
                if (btns.length > 0) { btns[0].click(); return true; }
            }
        }
        return false;
    }""")
    page.wait_for_timeout(3000)

    # Expand camera panel
    page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return;
        var camBtn = panel.querySelector('.camera-movement-btn');
        if (camBtn) camBtn.click();
    }""")
    page.wait_for_timeout(1500)

    # Verify camera tabs are visible
    tabs_visible = page.evaluate("""() => {
        for (var el of document.querySelectorAll('*')) {
            if ((el.innerText || '').trim() === 'Free Selection') {
                return el.getBoundingClientRect().height > 0;
            }
        }
        return false;
    }""")
    print(f"  Camera tabs visible: {tabs_visible}")

    if not tabs_visible:
        # Try clicking Camera row directly
        print("  Tabs not visible, trying mouse click on Camera row...")
        page.mouse.click(200, 289)  # Camera row from AI Video panel
        page.wait_for_timeout(1500)
        tabs_visible = page.evaluate("""() => {
            for (var el of document.querySelectorAll('*')) {
                if ((el.innerText || '').trim() === 'Free Selection') {
                    return el.getBoundingClientRect().height > 0;
                }
            }
            return false;
        }""")
        print(f"  After mouse click: {tabs_visible}")

    # Click Free Selection
    page.evaluate("""() => {
        for (var el of document.querySelectorAll('*')) {
            if ((el.innerText || '').trim() === 'Free Selection') { el.click(); return; }
        }
    }""")
    page.wait_for_timeout(1000)

    screenshot(page, "p189_camera_opened")

    # Now compare computed styles of ALL selection-item elements
    style_comparison = page.evaluate("""() => {
        var items = document.querySelectorAll('.selection-item');
        if (items.length === 0) return {found: false, count: 0};

        var results = [];
        for (var item of items) {
            var rect = item.getBoundingClientRect();
            if (rect.height === 0) continue;

            var text = (item.innerText || '').trim();
            var cls = (typeof item.className === 'string') ? item.className : '';
            var style = window.getComputedStyle(item);

            // Also check the selection-options child
            var optionsEl = item.querySelector('.selection-options');
            var optStyle = optionsEl ? window.getComputedStyle(optionsEl) : null;

            results.push({
                text: text.split('\\n')[0],
                cls: cls,
                // Item styles
                borderColor: style.borderColor,
                borderWidth: style.borderWidth,
                boxShadow: style.boxShadow,
                outline: style.outline,
                opacity: style.opacity,
                bg: style.backgroundColor,
                // Options child styles
                optCls: optionsEl ? ((typeof optionsEl.className === 'string') ? optionsEl.className : '') : '',
                optBorderColor: optStyle ? optStyle.borderColor : '',
                optBorderWidth: optStyle ? optStyle.borderWidth : '',
                optBoxShadow: optStyle ? optStyle.boxShadow : '',
                optBg: optStyle ? optStyle.backgroundColor : ''
            });
        }
        return {found: true, count: results.length, items: results};
    }""")

    if style_comparison.get('found'):
        print(f"\n  selection-item elements ({style_comparison['count']}):")
        for item in style_comparison['items']:
            print(f"\n    '{item['text']}'")
            print(f"      cls: {item['cls']}")
            # Only print non-default values
            if item['borderColor'] and 'rgba(0, 0, 0, 0)' not in item['borderColor']:
                print(f"      border: {item['borderColor']} {item['borderWidth']}")
            if item['boxShadow'] and item['boxShadow'] != 'none':
                print(f"      box-shadow: {item['boxShadow'][:60]}")
            if item['outline'] and item['outline'] != 'none':
                print(f"      outline: {item['outline']}")
            if item['bg'] and 'rgba(0, 0, 0, 0)' not in item['bg']:
                print(f"      bg: {item['bg']}")
            # Options child
            if item.get('optCls'):
                print(f"      options cls: {item['optCls']}")
                if item['optBorderColor'] and 'rgba(0, 0, 0, 0)' not in item['optBorderColor']:
                    print(f"      options border: {item['optBorderColor']} {item['optBorderWidth']}")
                if item['optBoxShadow'] and item['optBoxShadow'] != 'none':
                    print(f"      options box-shadow: {item['optBoxShadow'][:60]}")
    else:
        print(f"  No selection-item elements found!")
        # Debug: what's on screen
        debug = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            return panel ? (panel.innerText || '').substring(0, 200) : 'NO PANEL';
        }""")
        print(f"  Debug: {debug[:200]}")

    # ================================================================
    # TASK 2: Click Static Shot via page.mouse.click at exact position
    # ================================================================
    print("\n" + "=" * 70)
    print("TASK 2: Mouse Click Static Shot")
    print("=" * 70)

    # Get Static Shot exact position
    static_pos = page.evaluate("""() => {
        var items = document.querySelectorAll('.selection-item');
        for (var item of items) {
            if ((item.innerText || '').trim().includes('Static Shot')) {
                var opts = item.querySelector('.selection-options');
                if (opts) {
                    var rect = opts.getBoundingClientRect();
                    return {x: Math.round(rect.x + rect.width/2), y: Math.round(rect.y + rect.height/2)};
                }
            }
        }
        return null;
    }""")

    if static_pos:
        print(f"  Static Shot options center: ({static_pos['x']}, {static_pos['y']})")

        # Take "before" state snapshot
        before = page.evaluate("""() => {
            var items = document.querySelectorAll('.selection-item');
            for (var item of items) {
                if ((item.innerText || '').trim().includes('Static Shot')) {
                    var style = window.getComputedStyle(item);
                    var opts = item.querySelector('.selection-options');
                    var optStyle = opts ? window.getComputedStyle(opts) : null;
                    return {
                        cls: (typeof item.className === 'string') ? item.className : '',
                        border: style.borderColor + ' ' + style.borderWidth,
                        shadow: style.boxShadow,
                        optCls: opts ? ((typeof opts.className === 'string') ? opts.className : '') : '',
                        optBorder: optStyle ? optStyle.borderColor + ' ' + optStyle.borderWidth : '',
                        optShadow: optStyle ? optStyle.boxShadow : ''
                    };
                }
            }
            return {};
        }""")
        print(f"  Before click: cls={before.get('cls', '')} border={before.get('border', '')}")

        # Click!
        page.mouse.click(static_pos['x'], static_pos['y'])
        page.wait_for_timeout(1000)

        # Take "after" state snapshot
        after = page.evaluate("""() => {
            var items = document.querySelectorAll('.selection-item');
            for (var item of items) {
                if ((item.innerText || '').trim().includes('Static Shot')) {
                    var style = window.getComputedStyle(item);
                    var opts = item.querySelector('.selection-options');
                    var optStyle = opts ? window.getComputedStyle(opts) : null;
                    return {
                        cls: (typeof item.className === 'string') ? item.className : '',
                        border: style.borderColor + ' ' + style.borderWidth,
                        shadow: style.boxShadow,
                        optCls: opts ? ((typeof opts.className === 'string') ? opts.className : '') : '',
                        optBorder: optStyle ? optStyle.borderColor + ' ' + optStyle.borderWidth : '',
                        optShadow: optStyle ? optStyle.boxShadow : ''
                    };
                }
            }
            return {};
        }""")
        print(f"  After click: cls={after.get('cls', '')} border={after.get('border', '')}")

        # Compare
        changed = {}
        for key in before:
            if before.get(key) != after.get(key):
                changed[key] = {'before': before.get(key, ''), 'after': after.get(key, '')}

        if changed:
            print(f"\n  CHANGES DETECTED:")
            for key, diff in changed.items():
                print(f"    {key}:")
                print(f"      before: {diff['before'][:60]}")
                print(f"      after:  {diff['after'][:60]}")
        else:
            print(f"  NO CHANGES after click!")
            # Try clicking 2px lower (on the thumbnail area)
            print(f"  Trying click at ({static_pos['x']}, {static_pos['y'] - 50}) (thumbnail area)...")
            page.mouse.click(static_pos['x'], static_pos['y'] - 50)
            page.wait_for_timeout(1000)

            after2 = page.evaluate("""() => {
                var items = document.querySelectorAll('.selection-item');
                for (var item of items) {
                    if ((item.innerText || '').trim().includes('Static Shot')) {
                        return (typeof item.className === 'string') ? item.className : '';
                    }
                }
                return '';
            }""")
            print(f"  After thumbnail click cls: {after2}")

    screenshot(page, "p189_static_clicked")

    # ================================================================
    # TASK 3: Video actions via mouse.click
    # ================================================================
    print("\n" + "=" * 70)
    print("TASK 3: Video Actions via Mouse Click")
    print("=" * 70)

    # Close camera, go back to results
    page.keyboard.press('Escape')
    page.wait_for_timeout(500)

    # Switch to results and find video
    page.evaluate("""() => {
        for (var el of document.querySelectorAll('[class*="header-item"]')) {
            if ((el.innerText || '').includes('Result')) { el.click(); return; }
        }
    }""")
    page.wait_for_timeout(500)

    # Scroll results to find and show video result
    page.evaluate("""() => {
        var items = document.querySelectorAll('[class*="result-item"]');
        for (var item of items) {
            var cls = (typeof item.className === 'string') ? item.className : '';
            if (cls.includes('video') || cls.includes('i2v')) {
                item.scrollIntoView({behavior: 'instant', block: 'start'});
                return true;
            }
        }
        return false;
    }""")
    page.wait_for_timeout(1000)

    # Get Sound Effects button position (should now be visible)
    sound_pos = page.evaluate("""() => {
        for (var item of document.querySelectorAll('[class*="result-item"]')) {
            var cls = (typeof item.className === 'string') ? item.className : '';
            if (cls.includes('video') || cls.includes('i2v')) {
                for (var btn of item.querySelectorAll('.btn, button')) {
                    var text = (btn.innerText || '').trim();
                    if (text === 'Sound Effects') {
                        var rect = btn.getBoundingClientRect();
                        return {
                            x: Math.round(rect.x + rect.width/2),
                            y: Math.round(rect.y + rect.height/2),
                            visible: rect.y > 0 && rect.y < 900
                        };
                    }
                }
            }
        }
        return null;
    }""")

    print(f"  Sound Effects position: {json.dumps(sound_pos)}")

    if sound_pos and sound_pos.get('visible'):
        screenshot(page, "p189_before_sound")
        print(f"  Clicking Sound Effects at ({sound_pos['x']}, {sound_pos['y']})...")
        page.mouse.click(sound_pos['x'], sound_pos['y'])
        page.wait_for_timeout(3000)

        # Check what happened
        new_url = page.url
        print(f"  URL after click: {new_url}")

        # Check for any new panels/popups/tabs
        result = page.evaluate("""() => {
            // Check for new browser context/popup
            var panels = [];
            for (var el of document.querySelectorAll('*')) {
                var rect = el.getBoundingClientRect();
                var cls = (typeof el.className === 'string') ? el.className : '';
                if (rect.height > 200 && rect.width > 200 &&
                    (cls.includes('sound') || cls.includes('audio') || cls.includes('effect') ||
                     cls.includes('popup') || cls.includes('modal') || cls.includes('dialog'))) {
                    panels.push({
                        cls: cls.substring(0, 60),
                        text: (el.innerText || '').substring(0, 100),
                        x: Math.round(rect.x),
                        y: Math.round(rect.y),
                        w: Math.round(rect.width),
                        h: Math.round(rect.height)
                    });
                }
            }
            return {
                panelCount: panels.length,
                panels: panels,
                leftPanel: document.querySelector('.c-gen-config.show') ?
                    (document.querySelector('.c-gen-config.show').innerText || '').substring(0, 200) : 'none'
            };
        }""")

        print(f"  Left panel: {result.get('leftPanel', '')[:100]}")
        if result.get('panels'):
            for p in result['panels']:
                print(f"  Found: cls={p['cls']}")
                print(f"    text: {p['text'][:80]}")
        else:
            print("  No sound/audio/popup panels found")

        # Check if a new browser tab was opened
        all_pages = context.pages
        print(f"  Browser tabs: {len(all_pages)}")
        if len(all_pages) > 1:
            new_page = all_pages[-1]
            print(f"  New tab URL: {new_page.url}")

        screenshot(page, "p189_sound_effects")
    else:
        print("  Sound Effects button not visible, scrolling...")
        # Try to get all video action buttons visible
        page.evaluate("""() => {
            for (var item of document.querySelectorAll('[class*="result-item"]')) {
                var cls = (typeof item.className === 'string') ? item.className : '';
                if (cls.includes('video') || cls.includes('i2v')) {
                    // Scroll so action buttons are visible
                    var btns = item.querySelectorAll('.btn');
                    for (var btn of btns) {
                        if ((btn.innerText || '').trim() === 'Sound Effects') {
                            btn.scrollIntoView({behavior: 'instant', block: 'center'});
                            return true;
                        }
                    }
                }
            }
            return false;
        }""")
        page.wait_for_timeout(1000)
        screenshot(page, "p189_video_actions_visible")

    # ================================================================
    # TASK 4: Check for all available camera movements in detail
    # ================================================================
    print("\n" + "=" * 70)
    print("TASK 4: outerHTML comparison of active vs inactive")
    print("=" * 70)

    # Quick check: get outerHTML of Truck Left (active) vs Static Shot (inactive)
    html_comparison = page.evaluate("""() => {
        // Re-open AI Video and camera
        // First check if camera panel is still visible
        var freeTab = null;
        for (var el of document.querySelectorAll('*')) {
            if ((el.innerText || '').trim() === 'Free Selection' && el.getBoundingClientRect().height > 0) {
                freeTab = el;
                break;
            }
        }
        if (!freeTab) return {visible: false};

        var items = document.querySelectorAll('.selection-item');
        var results = {};
        for (var item of items) {
            var text = (item.innerText || '').trim();
            var name = text.split('\\n')[0];
            if (name === 'Truck Left' || name === 'Static Shot') {
                results[name] = item.outerHTML.substring(0, 500);
            }
        }
        return {visible: true, items: results};
    }""")

    if html_comparison.get('visible'):
        for name, html in html_comparison.get('items', {}).items():
            print(f"\n  {name} outerHTML (first 500 chars):")
            print(f"    {html[:500]}")
    else:
        print("  Camera panel not visible, skipping HTML comparison")

    print("\n" + "=" * 70)
    print("EXPLORATION PART 18 COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
