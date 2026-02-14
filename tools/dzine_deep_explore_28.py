#!/usr/bin/env python3
"""Dzine Deep Exploration Part 28 — Fresh State: Model Selector + Slider + Character + Image Editor.

Part 27 FAILED completely due to stale page state (panels wouldn't open).
Part 28 approach:
1. RELOAD the page for a clean state
2. Fix model selector: scroll popup container to bottom, mouse.click Wan 2.1
3. Fix Structure Match slider: use the numeric INPUT field directly (type value)
4. Explore Character tool presets (task #55)
5. Test Image Editor sub-tools (task #56)
"""

import json
import sys
import base64
import os
sys.path.insert(0, "/Users/ray/Documents/openclaw")
from tools.lib.brave_profile import connect_or_launch


def screenshot(page, name):
    path = f"/Users/ray/Downloads/{name}.png"
    page.screenshot(path=path)
    print(f"  [SS] {path}")


def get_active_panel(page):
    return page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return 'none';
        var text = (panel.innerText || '').substring(0, 100).trim();
        if (text.startsWith('Text to Image') || text.startsWith('Text-to-Image')) return 'txt2img';
        if (text.startsWith('AI Video')) return 'ai_video';
        if (text.startsWith('Enhance')) return 'enhance';
        if (text.startsWith('Motion Control')) return 'motion';
        if (text.startsWith('Face Swap')) return 'face_swap';
        if (text.startsWith('Image-to-Image')) return 'img2img';
        if (text.startsWith('Character')) return 'character';
        if (text.startsWith('Instant Storyboard')) return 'storyboard';
        if (text.startsWith('Assets')) return 'assets';
        if (text.startsWith('Lip Sync')) return 'lip_sync';
        if (text.startsWith('Video Editor')) return 'video_editor';
        if (text.startsWith('Image Editor')) return 'image_editor';
        if (text.startsWith('Local Edit')) return 'local_edit';
        return 'unknown:' + text.substring(0, 50);
    }""")


def close_all(page):
    """Close all panels and overlays for a clean state."""
    page.evaluate("""() => {
        // Close any generation config panel
        var panel = document.querySelector('.c-gen-config.show');
        if (panel) {
            var close = panel.querySelector('.ico-close, button.close');
            if (close) close.click();
        }
        // Close all visible close buttons
        for (var el of document.querySelectorAll('.ico-close')) {
            if (el.offsetHeight > 0) try { el.click(); } catch(e) {}
        }
        // Close pick-image dialogs
        var pid = document.querySelector('.pick-image-dialog');
        if (pid) {
            var c = pid.querySelector('.ico-close');
            if (c) c.click();
        }
    }""")
    page.wait_for_timeout(300)
    page.keyboard.press('Escape')
    page.wait_for_timeout(300)
    page.keyboard.press('Escape')
    page.wait_for_timeout(300)


def open_panel(page, tool_name, sidebar_y, timeout=2500):
    """Open a sidebar panel and verify it opened."""
    close_all(page)
    page.wait_for_timeout(300)
    page.mouse.click(40, sidebar_y)
    page.wait_for_timeout(timeout)
    panel = get_active_panel(page)
    print(f"  Opened '{tool_name}': panel={panel}")
    return panel


def main():
    print("=" * 70)
    print("DZINE DEEP EXPLORATION PART 28")
    print("Fresh State: Model Selector + Slider + Character + Image Editor")
    print("=" * 70)

    browser, context, _, _pw = connect_or_launch()
    page = context.pages[0]
    print(f"Connected. URL: {page.url}")

    # RELOAD page for fresh state (Part 27 failed because of stale state)
    print("\n>>> Reloading page for clean state...")
    page.goto("https://www.dzine.ai/canvas?id=19861203")
    page.wait_for_timeout(6000)
    print(f"  Reloaded. URL: {page.url}")

    # Check credits
    credits = page.evaluate("""() => {
        for (var el of document.querySelectorAll('*')) {
            var t = (el.innerText || '').trim();
            if (t.match(/^Unlimited\\s*\\/\\s*[\\d.,]+$/)) return t;
        }
        return 'unknown';
    }""")
    print(f"  Credits: {credits}")

    # Close any dialogs that appeared on load
    close_all(page)
    page.wait_for_timeout(500)

    # ================================================================
    # FIX 1: Model Selector — Scroll to Wan 2.1
    # ================================================================
    print("\n" + "=" * 70)
    print("FIX 1: Model Selector — Scroll to Wan 2.1")
    print("=" * 70)

    panel = open_panel(page, "AI Video", 361)

    if panel == 'ai_video':
        # Step 1: Read current model
        current = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return {};
            var sel = panel.querySelector('.custom-selector-wrapper');
            if (!sel) return {noSelector: true};
            var text = (sel.innerText || '').trim().split('\\n')[0];
            return {currentModel: text};
        }""")
        print(f"  Current model: {json.dumps(current)}")

        # Step 2: Click model selector to open popup
        page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return;
            var sel = panel.querySelector('.custom-selector-wrapper');
            if (sel) sel.click();
        }""")
        page.wait_for_timeout(2000)

        # Step 3: Map the popup structure precisely
        popup_map = page.evaluate("""() => {
            // The model popup is likely an overlay/dialog with all model cards
            // Find it by looking for large containers with model names
            var candidates = [];
            for (var el of document.querySelectorAll('*')) {
                var text = (el.innerText || '');
                if (text.includes('Wan 2.1') && text.includes('Minimax Hailuo') && text.includes('Seedance')) {
                    var rect = el.getBoundingClientRect();
                    if (rect.height > 200 && rect.width > 300) {
                        // Check if this el or any child is scrollable
                        var scrollable = null;
                        var scrollCls = '';
                        function findScroll(parent) {
                            if (parent.scrollHeight > parent.clientHeight + 30 && parent.clientHeight > 100) {
                                scrollable = parent;
                                scrollCls = (typeof parent.className === 'string') ? parent.className.substring(0, 60) : '';
                            }
                            for (var child of parent.children) {
                                findScroll(child);
                            }
                        }
                        findScroll(el);

                        candidates.push({
                            tag: el.tagName.toLowerCase(),
                            cls: (typeof el.className === 'string') ? el.className.substring(0, 60) : '',
                            x: Math.round(rect.x),
                            y: Math.round(rect.y),
                            w: Math.round(rect.width),
                            h: Math.round(rect.height),
                            scrollH: el.scrollHeight,
                            clientH: el.clientHeight,
                            isScrollable: el.scrollHeight > el.clientHeight + 30,
                            childScrollable: scrollable ? {
                                cls: scrollCls,
                                scrollH: scrollable.scrollHeight,
                                clientH: scrollable.clientHeight,
                                maxScroll: scrollable.scrollHeight - scrollable.clientHeight
                            } : null
                        });
                    }
                }
            }
            // Sort by area (smallest that still contains models = likely the popup body)
            candidates.sort(function(a, b) { return (a.w * a.h) - (b.w * b.h); });
            return candidates.slice(0, 5);
        }""")
        print(f"  Popup candidates ({len(popup_map)}):")
        for i, p in enumerate(popup_map):
            scroll_info = f" SCROLLABLE(max={p.get('childScrollable', {}).get('maxScroll', 0)})" if p.get('childScrollable') else ""
            self_scroll = f" SELF-SCROLL({p['scrollH']}-{p['clientH']}={p['scrollH']-p['clientH']})" if p.get('isScrollable') else ""
            print(f"    [{i}] {p['tag']}.{p['cls'][:30]} {p['w']}x{p['h']} at ({p['x']},{p['y']}){self_scroll}{scroll_info}")

        screenshot(page, "p281_model_popup_open")

        # Step 4: Scroll to bottom using the scrollable container
        print("\n  Scrolling popup to bottom...")
        scroll_result = page.evaluate("""() => {
            // Strategy: find the scrollable container and scroll it to the bottom
            var results = [];
            for (var el of document.querySelectorAll('*')) {
                if (el.scrollHeight > el.clientHeight + 30 && el.clientHeight > 100 && el.clientHeight < 800) {
                    var text = (el.innerText || '');
                    if (text.includes('Wan 2.1') && text.includes('Minimax')) {
                        var before = el.scrollTop;
                        el.scrollTop = el.scrollHeight;
                        var after = el.scrollTop;
                        results.push({
                            cls: (typeof el.className === 'string') ? el.className.substring(0, 40) : '',
                            beforeScroll: Math.round(before),
                            afterScroll: Math.round(after),
                            maxScroll: el.scrollHeight - el.clientHeight,
                            moved: Math.round(after - before)
                        });
                    }
                }
            }
            return results;
        }""")
        print(f"  Scroll results: {json.dumps(scroll_result)}")
        page.wait_for_timeout(800)

        # Step 5: Also try mouse.wheel in case scrollTop didn't work
        # Hover over popup center first
        if popup_map:
            px = popup_map[0]['x'] + popup_map[0]['w'] // 2
            py = popup_map[0]['y'] + popup_map[0]['h'] // 2
            print(f"  Also trying mouse.wheel at ({px}, {py})...")
            page.mouse.move(px, py)
            page.wait_for_timeout(200)
            for _ in range(15):
                page.mouse.wheel(0, 400)
                page.wait_for_timeout(150)
            page.wait_for_timeout(500)

        screenshot(page, "p281_model_popup_scrolled")

        # Step 6: Find Wan 2.1 position
        wan = page.evaluate("""() => {
            // Look for the Wan 2.1 card element
            var best = null;
            for (var el of document.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                // Match "Wan 2.1" as the first line, with reasonable element size
                if (text.startsWith('Wan 2.1') && el.offsetHeight > 30 && el.offsetHeight < 150 && el.offsetWidth > 50) {
                    var rect = el.getBoundingClientRect();
                    // Must be within viewport
                    if (rect.y > 0 && rect.y < window.innerHeight && rect.x > 0 && rect.x < window.innerWidth) {
                        // Prefer smaller (more specific) elements
                        if (!best || (rect.width * rect.height) < (best.area)) {
                            best = {
                                text: text.substring(0, 60),
                                x: Math.round(rect.x + rect.width / 2),
                                y: Math.round(rect.y + rect.height / 2),
                                w: Math.round(rect.width),
                                h: Math.round(rect.height),
                                area: rect.width * rect.height,
                                tag: el.tagName.toLowerCase(),
                                cls: (typeof el.className === 'string') ? el.className.substring(0, 40) : ''
                            };
                        }
                    }
                }
            }
            return best;
        }""")
        print(f"  Wan 2.1: {json.dumps(wan)}")

        if wan:
            # Click it with page.mouse.click (NOT el.click!)
            print(f"  Clicking Wan 2.1 at ({wan['x']}, {wan['y']})...")
            page.mouse.click(wan['x'], wan['y'])
            page.wait_for_timeout(2000)

            # Verify model changed
            verify = page.evaluate("""() => {
                var panel = document.querySelector('.c-gen-config.show');
                if (!panel) return {noPanel: true};
                var sel = panel.querySelector('.custom-selector-wrapper');
                var model = 'unknown';
                if (sel) {
                    // Get just the displayed name (first line)
                    var spans = sel.querySelectorAll('span, div');
                    for (var s of spans) {
                        var t = (s.innerText || '').trim();
                        if (t && !t.includes('\\n') && t.length < 40) {
                            model = t;
                            break;
                        }
                    }
                    if (model === 'unknown') model = (sel.innerText || '').trim().split('\\n')[0];
                }
                // Check generate cost
                var cost = '';
                for (var btn of panel.querySelectorAll('button')) {
                    var t = (btn.innerText || '').trim();
                    if (t.includes('Generate')) cost = t;
                }
                return {model: model, generateCost: cost};
            }""")
            print(f"  Verify: {json.dumps(verify)}")

            if 'Wan' in verify.get('model', '') or '6' in verify.get('generateCost', ''):
                print("  >>> MODEL SELECTOR FIX CONFIRMED! Wan 2.1 selected!")
            else:
                print("  Model might not have changed. Checking if popup is still open...")
                # Close popup and try again with a different click target
                page.keyboard.press('Escape')
                page.wait_for_timeout(500)
                verify2 = page.evaluate("""() => {
                    var panel = document.querySelector('.c-gen-config.show');
                    if (!panel) return {};
                    var sel = panel.querySelector('.custom-selector-wrapper');
                    var model = sel ? (sel.innerText || '').trim().split('\\n')[0] : 'unknown';
                    var cost = '';
                    for (var btn of panel.querySelectorAll('button')) {
                        if ((btn.innerText || '').includes('Generate')) cost = (btn.innerText || '').trim();
                    }
                    return {model: model, generateCost: cost};
                }""")
                print(f"  After Escape: {json.dumps(verify2)}")
        else:
            print("  Wan 2.1 NOT visible in viewport. Taking screenshot to debug...")

        screenshot(page, "p281_model_result")
    else:
        print(f"  FAILED to open AI Video panel (got: {panel})")

    # ================================================================
    # FIX 2: Structure Match Slider — Use Numeric Input
    # ================================================================
    print("\n" + "=" * 70)
    print("FIX 2: Structure Match Slider (numeric input approach)")
    print("=" * 70)

    panel = open_panel(page, "Img2Img", 252)

    if panel == 'img2img':
        # The Img2Img panel has a numeric INPUT field for Structure Match
        # From P22: INPUT.number at (100,349) with default "0.5"
        # Strategy: clear the input and type a new value

        # Step 1: Map current slider state
        slider_state = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return {};

            // Find the numeric input near Structure Match
            var inputs = panel.querySelectorAll('input[type="number"], input.number');
            var numInput = null;
            for (var inp of inputs) {
                if (inp.offsetHeight > 0) {
                    numInput = inp;
                    break;
                }
            }

            // Find the Ant Design slider handle
            var handle = panel.querySelector('.ant-slider-handle');
            var handleRect = handle ? handle.getBoundingClientRect() : null;

            // Find the slider rail
            var rail = panel.querySelector('.ant-slider-rail, .ant-slider');
            var railRect = rail ? rail.getBoundingClientRect() : null;

            // Find current label
            var label = '';
            for (var el of panel.querySelectorAll('*')) {
                var t = (el.innerText || '').trim();
                if (['Very similar', 'Similar', 'Less similar', 'Different', 'Exact', 'Flexible'].includes(t)) {
                    label = t;
                    break;
                }
            }

            return {
                numInput: numInput ? {
                    value: numInput.value,
                    x: Math.round(numInput.getBoundingClientRect().x),
                    y: Math.round(numInput.getBoundingClientRect().y),
                    w: Math.round(numInput.getBoundingClientRect().width),
                    h: Math.round(numInput.getBoundingClientRect().height),
                    type: numInput.type,
                    cls: (typeof numInput.className === 'string') ? numInput.className.substring(0, 30) : ''
                } : null,
                handle: handleRect ? {
                    x: Math.round(handleRect.x + handleRect.width/2),
                    y: Math.round(handleRect.y + handleRect.height/2),
                    w: Math.round(handleRect.width),
                    h: Math.round(handleRect.height)
                } : null,
                rail: railRect ? {
                    x: Math.round(railRect.x),
                    y: Math.round(railRect.y),
                    w: Math.round(railRect.width),
                    h: Math.round(railRect.height)
                } : null,
                label: label
            };
        }""")
        print(f"  Numeric input: {json.dumps(slider_state.get('numInput'))}")
        print(f"  Handle: {json.dumps(slider_state.get('handle'))}")
        print(f"  Rail: {json.dumps(slider_state.get('rail'))}")
        print(f"  Label: {slider_state.get('label')}")

        # Step 2: Try using the numeric input to set value
        if slider_state.get('numInput'):
            inp = slider_state['numInput']
            ix = inp['x'] + inp['w'] // 2
            iy = inp['y'] + inp['h'] // 2
            print(f"\n  Testing numeric input at ({ix}, {iy}) current={inp['value']}...")

            # Test values: 0.1, 0.5, 0.9
            for test_val in ['0.1', '0.5', '0.9']:
                print(f"\n  Setting value to {test_val}...")

                # Click the input to focus it
                page.mouse.click(ix, iy)
                page.wait_for_timeout(200)

                # Triple-click to select all text
                page.mouse.click(ix, iy, click_count=3)
                page.wait_for_timeout(200)

                # Type the new value
                page.keyboard.type(test_val)
                page.wait_for_timeout(200)

                # Press Enter to confirm
                page.keyboard.press('Enter')
                page.wait_for_timeout(500)

                # Read back the state
                after = page.evaluate("""() => {
                    var panel = document.querySelector('.c-gen-config.show');
                    if (!panel) return {};
                    var inputs = panel.querySelectorAll('input[type="number"], input.number');
                    var val = '';
                    for (var inp of inputs) {
                        if (inp.offsetHeight > 0) { val = inp.value; break; }
                    }
                    var label = '';
                    for (var el of panel.querySelectorAll('*')) {
                        var t = (el.innerText || '').trim();
                        if (['Very similar', 'Similar', 'Less similar', 'Different', 'Exact', 'Flexible'].includes(t)) {
                            label = t; break;
                        }
                    }
                    return {value: val, label: label};
                }""")
                print(f"    Result: value={after.get('value')} label='{after.get('label')}'")

        # Step 3: Try the Ant Design slider handle drag as fallback
        if slider_state.get('handle') and slider_state.get('rail'):
            h = slider_state['handle']
            r = slider_state['rail']
            print(f"\n  Testing Ant Design handle drag...")
            print(f"  Handle at ({h['x']}, {h['y']}) {h['w']}x{h['h']}")
            print(f"  Rail at ({r['x']}, {r['y']}) {r['w']}x{r['h']}")

            # Drag from handle to 20% of rail
            target_x = r['x'] + int(r['w'] * 0.2)
            print(f"  Dragging handle to 20% (x={target_x})...")
            page.mouse.move(h['x'], h['y'])
            page.wait_for_timeout(100)
            page.mouse.down()
            page.wait_for_timeout(100)
            page.mouse.move(target_x, h['y'], steps=15)
            page.wait_for_timeout(100)
            page.mouse.up()
            page.wait_for_timeout(500)

            after_drag = page.evaluate("""() => {
                var panel = document.querySelector('.c-gen-config.show');
                if (!panel) return {};
                var inputs = panel.querySelectorAll('input[type="number"], input.number');
                var val = '';
                for (var inp of inputs) {
                    if (inp.offsetHeight > 0) { val = inp.value; break; }
                }
                var label = '';
                for (var el of panel.querySelectorAll('*')) {
                    var t = (el.innerText || '').trim();
                    if (['Very similar', 'Similar', 'Less similar', 'Different', 'Exact', 'Flexible'].includes(t)) {
                        label = t; break;
                    }
                }
                return {value: val, label: label};
            }""")
            print(f"  After drag to 20%: value={after_drag.get('value')} label='{after_drag.get('label')}'")

            # Drag to 80%
            # Re-find handle position
            new_h = page.evaluate("""() => {
                var panel = document.querySelector('.c-gen-config.show');
                if (!panel) return null;
                var handle = panel.querySelector('.ant-slider-handle');
                if (!handle) return null;
                var rect = handle.getBoundingClientRect();
                return {x: Math.round(rect.x + rect.width/2), y: Math.round(rect.y + rect.height/2)};
            }""")
            if new_h:
                target_x = r['x'] + int(r['w'] * 0.8)
                print(f"  Dragging handle to 80% (x={target_x})...")
                page.mouse.move(new_h['x'], new_h['y'])
                page.wait_for_timeout(100)
                page.mouse.down()
                page.wait_for_timeout(100)
                page.mouse.move(target_x, new_h['y'], steps=15)
                page.wait_for_timeout(100)
                page.mouse.up()
                page.wait_for_timeout(500)

                after_drag2 = page.evaluate("""() => {
                    var panel = document.querySelector('.c-gen-config.show');
                    if (!panel) return {};
                    var inputs = panel.querySelectorAll('input[type="number"], input.number');
                    var val = '';
                    for (var inp of inputs) {
                        if (inp.offsetHeight > 0) { val = inp.value; break; }
                    }
                    var label = '';
                    for (var el of panel.querySelectorAll('*')) {
                        var t = (el.innerText || '').trim();
                        if (['Very similar', 'Similar', 'Less similar', 'Different', 'Exact', 'Flexible'].includes(t)) {
                            label = t; break;
                        }
                    }
                    return {value: val, label: label};
                }""")
                print(f"  After drag to 80%: value={after_drag2.get('value')} label='{after_drag2.get('label')}'")

        # Step 4: Try programmatic React state change as last resort
        print("\n  Trying programmatic value change via React internals...")
        react_change = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return {error: 'no panel'};
            var input = null;
            var inputs = panel.querySelectorAll('input');
            for (var inp of inputs) {
                if (inp.offsetHeight > 0 && (inp.type === 'number' || inp.className.includes('number'))) {
                    input = inp;
                    break;
                }
            }
            if (!input) return {error: 'no input found'};

            // Try React synthetic event approach
            var nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
            nativeInputValueSetter.call(input, '0.3');
            input.dispatchEvent(new Event('input', { bubbles: true }));
            input.dispatchEvent(new Event('change', { bubbles: true }));

            return {
                success: true,
                newValue: input.value
            };
        }""")
        print(f"  React change: {json.dumps(react_change)}")
        page.wait_for_timeout(500)

        # Check final state
        final_state = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return {};
            var inputs = panel.querySelectorAll('input');
            var val = '';
            for (var inp of inputs) {
                if (inp.offsetHeight > 0 && (inp.type === 'number' || inp.className.includes('number'))) {
                    val = inp.value; break;
                }
            }
            var label = '';
            for (var el of panel.querySelectorAll('*')) {
                var t = (el.innerText || '').trim();
                if (['Very similar', 'Similar', 'Less similar', 'Different', 'Exact', 'Flexible'].includes(t)) {
                    label = t; break;
                }
            }
            return {value: val, label: label};
        }""")
        print(f"  Final slider state: value={final_state.get('value')} label='{final_state.get('label')}'")

        screenshot(page, "p281_slider_result")
    else:
        print(f"  FAILED to open Img2Img panel (got: {panel})")

    # ================================================================
    # TASK 3: Character Tool — Presets and Custom Characters
    # ================================================================
    print("\n" + "=" * 70)
    print("TASK 3: Character Tool — Presets and Custom Characters")
    print("=" * 70)

    panel = open_panel(page, "Character", 306)

    if panel == 'character':
        # Step 1: Map all buttons and collapse-options
        char_map = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return {};
            var result = {text: '', buttons: [], collapseOpts: [], presets: []};
            result.text = (panel.innerText || '').substring(0, 800);

            for (var btn of panel.querySelectorAll('button')) {
                var t = (btn.innerText || '').trim();
                if (t && t.length < 40) {
                    var rect = btn.getBoundingClientRect();
                    result.buttons.push({text: t, x: Math.round(rect.x + rect.width/2), y: Math.round(rect.y + rect.height/2)});
                }
            }

            for (var opt of panel.querySelectorAll('.collapse-option')) {
                var t = (opt.innerText || '').trim();
                var rect = opt.getBoundingClientRect();
                result.collapseOpts.push({text: t.substring(0, 60), x: Math.round(rect.x + rect.width/2), y: Math.round(rect.y + rect.height/2)});
            }

            return result;
        }""")

        print(f"  Buttons ({len(char_map.get('buttons', []))}):")
        for b in char_map.get('buttons', []):
            print(f"    ({b['x']}, {b['y']}) '{b['text']}'")
        print(f"  Collapse options ({len(char_map.get('collapseOpts', []))}):")
        for o in char_map.get('collapseOpts', []):
            print(f"    ({o['x']}, {o['y']}) '{o['text'][:50]}'")

        # Step 2: Click "Manage Your Characters" to see all presets
        manage_btn = None
        for b in char_map.get('buttons', []):
            if 'Manage' in b['text']:
                manage_btn = b
                break

        if manage_btn:
            print(f"\n  Clicking 'Manage Your Characters' at ({manage_btn['x']}, {manage_btn['y']})...")
            page.mouse.click(manage_btn['x'], manage_btn['y'])
            page.wait_for_timeout(2000)

            # Map all character cards
            chars = page.evaluate("""() => {
                var result = [];
                // Look for character cards in a management dialog/panel
                for (var el of document.querySelectorAll('[class*="character"], [class*="card"], [class*="preset"]')) {
                    var text = (el.innerText || '').trim();
                    var rect = el.getBoundingClientRect();
                    if (rect.height > 50 && rect.height < 200 && rect.width > 50 && rect.width < 200 && text.length < 30 && text.length > 0) {
                        // Check for image
                        var img = el.querySelector('img');
                        var imgSrc = img ? img.src : '';
                        result.push({
                            name: text,
                            x: Math.round(rect.x + rect.width/2),
                            y: Math.round(rect.y + rect.height/2),
                            hasImage: !!img,
                            imgSrc: imgSrc.substring(0, 80)
                        });
                    }
                }
                // Deduplicate by name
                var seen = {};
                return result.filter(function(c) {
                    if (seen[c.name]) return false;
                    seen[c.name] = true;
                    return true;
                });
            }""")
            print(f"\n  Characters ({len(chars)}):")
            for c in chars:
                img = " [has img]" if c.get('hasImage') else ""
                print(f"    '{c['name']}' at ({c['x']}, {c['y']}){img}")

            screenshot(page, "p281_character_manage")

            # Close the manage dialog
            page.keyboard.press('Escape')
            page.wait_for_timeout(500)

        # Step 3: Explore "Generate Images" sub-panel
        gen_opt = None
        for o in char_map.get('collapseOpts', []):
            if 'Generate' in o['text']:
                gen_opt = o
                break

        if gen_opt:
            print(f"\n  Clicking 'Generate Images' at ({gen_opt['x']}, {gen_opt['y']})...")
            page.mouse.click(gen_opt['x'], gen_opt['y'])
            page.wait_for_timeout(2000)

            gen_panel = page.evaluate("""() => {
                var panel = document.querySelector('.c-gen-config.show');
                if (!panel) return {};
                var text = (panel.innerText || '').substring(0, 1000);
                var buttons = [];
                for (var btn of panel.querySelectorAll('button')) {
                    var t = (btn.innerText || '').trim();
                    if (t && t.length < 40) {
                        var rect = btn.getBoundingClientRect();
                        var cls = (typeof btn.className === 'string') ? btn.className : '';
                        buttons.push({text: t, x: Math.round(rect.x + rect.width/2), y: Math.round(rect.y + rect.height/2), selected: cls.includes('selected')});
                    }
                }
                // Find character dropdown/selector
                var charSel = panel.querySelector('.custom-selector-wrapper, [class*="character-select"]');
                var charName = charSel ? (charSel.innerText || '').trim().split('\\n')[0] : '';
                // Find prompt textarea
                var prompt = panel.querySelector('textarea');
                var promptInfo = prompt ? {maxLength: prompt.maxLength, placeholder: (prompt.placeholder || '').substring(0, 50)} : null;
                return {buttons: buttons, selectedChar: charName, prompt: promptInfo, text: text};
            }""")

            print(f"  Selected character: '{gen_panel.get('selectedChar')}'")
            print(f"  Prompt: {json.dumps(gen_panel.get('prompt'))}")
            print(f"  Buttons ({len(gen_panel.get('buttons', []))}):")
            for b in gen_panel.get('buttons', []):
                sel = " [SELECTED]" if b.get('selected') else ""
                print(f"    ({b['x']}, {b['y']}) '{b['text']}'{sel}")

            screenshot(page, "p281_character_generate")

            # Step 4: Try switching character in the dropdown
            page.evaluate("""() => {
                var panel = document.querySelector('.c-gen-config.show');
                if (!panel) return;
                var sel = panel.querySelector('.custom-selector-wrapper, [class*="character-select"]');
                if (sel) sel.click();
            }""")
            page.wait_for_timeout(1500)

            # Map character options in the dropdown
            char_options = page.evaluate("""() => {
                var result = [];
                // Look for a dropdown/popup with character options
                for (var el of document.querySelectorAll('[class*="option"], [class*="item"], [class*="card"]')) {
                    var text = (el.innerText || '').trim();
                    var rect = el.getBoundingClientRect();
                    if (rect.height > 30 && rect.height < 120 && rect.width > 80 && rect.x > 80 && rect.x < 600) {
                        var img = el.querySelector('img');
                        if (img || (text.length > 0 && text.length < 25)) {
                            result.push({
                                name: text || '[image only]',
                                x: Math.round(rect.x + rect.width/2),
                                y: Math.round(rect.y + rect.height/2),
                                hasImage: !!img
                            });
                        }
                    }
                }
                // Deduplicate
                var seen = {};
                return result.filter(function(c) {
                    var key = c.name + c.y;
                    if (seen[key]) return false;
                    seen[key] = true;
                    return true;
                }).slice(0, 20);
            }""")
            print(f"\n  Character dropdown options ({len(char_options)}):")
            for c in char_options:
                print(f"    '{c['name']}' at ({c['x']}, {c['y']})")

            screenshot(page, "p281_character_dropdown")

            # Close dropdown
            page.keyboard.press('Escape')
            page.wait_for_timeout(300)
    else:
        print(f"  FAILED to open Character panel (got: {panel})")

    # ================================================================
    # TASK 4: Image Editor — Sub-tools
    # ================================================================
    print("\n" + "=" * 70)
    print("TASK 4: Image Editor — Map All Sub-tools")
    print("=" * 70)

    panel = open_panel(page, "Image Editor", 698)

    if panel == 'image_editor' or 'Image Editor' in panel:
        # Map all sub-tool collapse options
        ie_map = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return {};
            var text = (panel.innerText || '').substring(0, 1200);
            var opts = [];
            for (var opt of panel.querySelectorAll('.collapse-option')) {
                var t = (opt.innerText || '').trim();
                var rect = opt.getBoundingClientRect();
                var cls = (typeof opt.className === 'string') ? opt.className : '';
                opts.push({
                    text: t.substring(0, 80),
                    x: Math.round(rect.x + rect.width/2),
                    y: Math.round(rect.y + rect.height/2),
                    hasGuide: cls.includes('has-guide')
                });
            }
            // Look for section headers
            var sections = [];
            for (var el of panel.querySelectorAll('h3, h4, [class*="section-title"], [class*="group-title"]')) {
                var t = (el.innerText || '').trim();
                if (t) sections.push(t);
            }
            return {opts: opts, sections: sections, text: text};
        }""")

        print(f"  Sections: {ie_map.get('sections', [])}")
        print(f"  Sub-tools ({len(ie_map.get('opts', []))}):")
        for o in ie_map.get('opts', []):
            guide = " [has guide]" if o.get('hasGuide') else ""
            print(f"    ({o['x']}, {o['y']}) '{o['text'][:50]}'{guide}")

        screenshot(page, "p281_image_editor_panel")

        # Step 2: Test "AI Eraser" sub-tool
        eraser_opt = None
        for o in ie_map.get('opts', []):
            if 'Eraser' in o['text']:
                eraser_opt = o
                break

        if eraser_opt:
            print(f"\n  Clicking 'AI Eraser' at ({eraser_opt['x']}, {eraser_opt['y']})...")
            page.mouse.click(eraser_opt['x'], eraser_opt['y'])
            page.wait_for_timeout(2000)

            eraser_panel = page.evaluate("""() => {
                var panel = document.querySelector('.c-gen-config.show');
                if (!panel) return {};
                var text = (panel.innerText || '').substring(0, 600);
                var buttons = [];
                for (var btn of panel.querySelectorAll('button')) {
                    var t = (btn.innerText || '').trim();
                    if (t && t.length < 40) {
                        var rect = btn.getBoundingClientRect();
                        buttons.push({text: t, x: Math.round(rect.x + rect.width/2), y: Math.round(rect.y + rect.height/2)});
                    }
                }
                return {text: text, buttons: buttons};
            }""")
            print(f"  AI Eraser panel text (first 300 chars):")
            for line in eraser_panel.get('text', '').split('\n')[:10]:
                line = line.strip()
                if line:
                    print(f"    > {line[:60]}")
            print(f"  Buttons ({len(eraser_panel.get('buttons', []))}):")
            for b in eraser_panel.get('buttons', []):
                print(f"    ({b['x']}, {b['y']}) '{b['text']}'")

            screenshot(page, "p281_ai_eraser")

            # Go back to Image Editor
            page.keyboard.press('Escape')
            page.wait_for_timeout(500)

        # Step 3: Test "Insert Object" sub-tool
        panel = open_panel(page, "Image Editor", 698)
        if panel == 'image_editor' or 'Image Editor' in panel:
            insert_opt = None
            ie_map2 = page.evaluate("""() => {
                var panel = document.querySelector('.c-gen-config.show');
                if (!panel) return {opts: []};
                var opts = [];
                for (var opt of panel.querySelectorAll('.collapse-option')) {
                    var t = (opt.innerText || '').trim();
                    var rect = opt.getBoundingClientRect();
                    opts.push({text: t.substring(0, 80), x: Math.round(rect.x + rect.width/2), y: Math.round(rect.y + rect.height/2)});
                }
                return {opts: opts};
            }""")

            for o in ie_map2.get('opts', []):
                if 'Insert' in o['text']:
                    insert_opt = o
                    break

            if insert_opt:
                print(f"\n  Clicking 'Insert Object' at ({insert_opt['x']}, {insert_opt['y']})...")
                page.mouse.click(insert_opt['x'], insert_opt['y'])
                page.wait_for_timeout(2000)

                insert_panel = page.evaluate("""() => {
                    var panel = document.querySelector('.c-gen-config.show');
                    if (!panel) return {};
                    var text = (panel.innerText || '').substring(0, 600);
                    var buttons = [];
                    for (var btn of panel.querySelectorAll('button')) {
                        var t = (btn.innerText || '').trim();
                        if (t && t.length < 40) {
                            var rect = btn.getBoundingClientRect();
                            buttons.push({text: t, x: Math.round(rect.x + rect.width/2), y: Math.round(rect.y + rect.height/2)});
                        }
                    }
                    // Find prompt
                    var prompt = panel.querySelector('textarea');
                    var promptInfo = prompt ? {maxLength: prompt.maxLength, placeholder: (prompt.placeholder || '').substring(0, 50)} : null;
                    return {text: text, buttons: buttons, prompt: promptInfo};
                }""")
                print(f"  Insert Object panel:")
                for line in insert_panel.get('text', '').split('\n')[:10]:
                    line = line.strip()
                    if line:
                        print(f"    > {line[:60]}")
                print(f"  Prompt: {json.dumps(insert_panel.get('prompt'))}")
                print(f"  Buttons ({len(insert_panel.get('buttons', []))}):")
                for b in insert_panel.get('buttons', []):
                    print(f"    ({b['x']}, {b['y']}) '{b['text']}'")

                screenshot(page, "p281_insert_object")

        # Step 4: Test "Expand" (Generative Outpaint) sub-tool
        panel = open_panel(page, "Image Editor", 698)
        if panel == 'image_editor' or 'Image Editor' in panel:
            expand_opt = None
            ie_map3 = page.evaluate("""() => {
                var panel = document.querySelector('.c-gen-config.show');
                if (!panel) return {opts: []};
                var opts = [];
                for (var opt of panel.querySelectorAll('.collapse-option')) {
                    var t = (opt.innerText || '').trim();
                    var rect = opt.getBoundingClientRect();
                    opts.push({text: t.substring(0, 80), x: Math.round(rect.x + rect.width/2), y: Math.round(rect.y + rect.height/2)});
                }
                return {opts: opts};
            }""")

            for o in ie_map3.get('opts', []):
                if 'Expand' in o['text']:
                    expand_opt = o
                    break

            if expand_opt:
                print(f"\n  Clicking 'Expand' at ({expand_opt['x']}, {expand_opt['y']})...")
                page.mouse.click(expand_opt['x'], expand_opt['y'])
                page.wait_for_timeout(2000)

                expand_panel = page.evaluate("""() => {
                    var panel = document.querySelector('.c-gen-config.show');
                    if (!panel) return {};
                    var text = (panel.innerText || '').substring(0, 600);
                    var buttons = [];
                    for (var btn of panel.querySelectorAll('button')) {
                        var t = (btn.innerText || '').trim();
                        if (t && t.length < 40) {
                            var rect = btn.getBoundingClientRect();
                            buttons.push({text: t, x: Math.round(rect.x + rect.width/2), y: Math.round(rect.y + rect.height/2)});
                        }
                    }
                    return {text: text, buttons: buttons};
                }""")
                print(f"  Expand (Outpaint) panel:")
                for line in expand_panel.get('text', '').split('\n')[:10]:
                    line = line.strip()
                    if line:
                        print(f"    > {line[:60]}")
                print(f"  Buttons ({len(expand_panel.get('buttons', []))}):")
                for b in expand_panel.get('buttons', []):
                    print(f"    ({b['x']}, {b['y']}) '{b['text']}'")

                screenshot(page, "p281_expand_outpaint")

        # Step 5: Test "Face Swap" sub-tool
        panel = open_panel(page, "Image Editor", 698)
        if panel == 'image_editor' or 'Image Editor' in panel:
            face_opt = None
            ie_map4 = page.evaluate("""() => {
                var panel = document.querySelector('.c-gen-config.show');
                if (!panel) return {opts: []};
                var opts = [];
                for (var opt of panel.querySelectorAll('.collapse-option')) {
                    var t = (opt.innerText || '').trim();
                    var rect = opt.getBoundingClientRect();
                    opts.push({text: t.substring(0, 80), x: Math.round(rect.x + rect.width/2), y: Math.round(rect.y + rect.height/2)});
                }
                return {opts: opts};
            }""")

            for o in ie_map4.get('opts', []):
                if 'Face Swap' in o['text']:
                    face_opt = o
                    break

            if face_opt:
                print(f"\n  Clicking 'Face Swap' at ({face_opt['x']}, {face_opt['y']})...")
                page.mouse.click(face_opt['x'], face_opt['y'])
                page.wait_for_timeout(2000)

                face_panel = page.evaluate("""() => {
                    var panel = document.querySelector('.c-gen-config.show');
                    if (!panel) return {};
                    var text = (panel.innerText || '').substring(0, 600);
                    var buttons = [];
                    for (var btn of panel.querySelectorAll('button')) {
                        var t = (btn.innerText || '').trim();
                        if (t && t.length < 40) {
                            var rect = btn.getBoundingClientRect();
                            buttons.push({text: t, x: Math.round(rect.x + rect.width/2), y: Math.round(rect.y + rect.height/2)});
                        }
                    }
                    return {text: text, buttons: buttons};
                }""")
                print(f"  Face Swap panel:")
                for line in face_panel.get('text', '').split('\n')[:10]:
                    line = line.strip()
                    if line:
                        print(f"    > {line[:60]}")
                print(f"  Buttons ({len(face_panel.get('buttons', []))}):")
                for b in face_panel.get('buttons', []):
                    print(f"    ({b['x']}, {b['y']}) '{b['text']}'")

                screenshot(page, "p281_face_swap")

    # ================================================================
    # TASK 5: Motion Control — Quick Map
    # ================================================================
    print("\n" + "=" * 70)
    print("TASK 5: Motion Control — Quick Map")
    print("=" * 70)

    panel = open_panel(page, "Motion Control", 563)

    if panel == 'motion' or 'Motion' in panel:
        mc_map = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return {};
            var text = (panel.innerText || '').substring(0, 800);
            var buttons = [];
            for (var btn of panel.querySelectorAll('button')) {
                var t = (btn.innerText || '').trim();
                if (t && t.length < 40) {
                    var rect = btn.getBoundingClientRect();
                    var cls = (typeof btn.className === 'string') ? btn.className : '';
                    buttons.push({text: t, x: Math.round(rect.x + rect.width/2), y: Math.round(rect.y + rect.height/2), selected: cls.includes('selected')});
                }
            }
            // Find model selector
            var sel = panel.querySelector('.custom-selector-wrapper');
            var model = sel ? (sel.innerText || '').trim().split('\\n')[0] : '';
            return {text: text, buttons: buttons, model: model};
        }""")

        print(f"  Model: {mc_map.get('model')}")
        print(f"  Buttons ({len(mc_map.get('buttons', []))}):")
        for b in mc_map.get('buttons', []):
            sel = " [SELECTED]" if b.get('selected') else ""
            print(f"    ({b['x']}, {b['y']}) '{b['text']}'{sel}")

        screenshot(page, "p281_motion_control")
    else:
        print(f"  FAILED to open Motion Control panel (got: {panel})")

    # ================================================================
    # Final Credits
    # ================================================================
    print("\n" + "=" * 70)
    print("Final Credits")
    print("=" * 70)
    credits = page.evaluate("""() => {
        for (var el of document.querySelectorAll('*')) {
            var t = (el.innerText || '').trim();
            if (t.match(/^Unlimited\\s*\\/\\s*[\\d.,]+$/)) return t;
        }
        return 'unknown';
    }""")
    print(f"  Credits: {credits}")

    print("\n" + "=" * 70)
    print("EXPLORATION PART 28 COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
