#!/usr/bin/env python3
"""Dzine Deep Exploration Part 27 — Targeted: Model Selector Fix + Slider Fix.

FOCUSED: Two critical fixes only.
1. Model selector: use mouse.wheel() to scroll within popup
2. Structure Match: use drag interaction on slider thumb

These are blocking automated video production.
"""

import json
import sys
sys.path.insert(0, "/Users/ray/Documents/openclaw")
from tools.lib.brave_profile import connect_or_launch


def screenshot(page, name):
    path = f"/Users/ray/Downloads/{name}.png"
    page.screenshot(path=path)
    print(f"  [SS] {path}")


def main():
    print("=" * 70)
    print("DZINE DEEP EXPLORATION PART 27")
    print("Targeted: Model Selector + Structure Match Slider")
    print("=" * 70)

    browser, context, _, _pw = connect_or_launch()
    page = context.pages[0]
    print(f"Connected. URL: {page.url}")

    if "dzine.ai/canvas" not in page.url:
        page.goto("https://www.dzine.ai/canvas?id=19861203")
        page.wait_for_timeout(5000)

    # ================================================================
    # FIX 1: Model Selector — Scroll with mouse.wheel()
    # ================================================================
    print("\n" + "=" * 70)
    print("FIX 1: Model Selector — mouse.wheel() scroll approach")
    print("=" * 70)

    # Open AI Video
    page.mouse.click(40, 361)
    page.wait_for_timeout(2500)

    # Open model selector popup
    page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return;
        var sel = panel.querySelector('.custom-selector-wrapper');
        if (sel) sel.click();
    }""")
    page.wait_for_timeout(1500)

    # Check current state of popup
    popup_state = page.evaluate("""() => {
        // Find the model popup overlay
        var popup = null;
        for (var el of document.querySelectorAll('*')) {
            if (el.offsetHeight > 300 && el.offsetWidth > 500) {
                var text = (el.innerText || '');
                if (text.includes('Wan 2.1') && text.includes('Minimax Hailuo')) {
                    var rect = el.getBoundingClientRect();
                    popup = el;
                    break;
                }
            }
        }
        if (!popup) return {found: false};

        var rect = popup.getBoundingClientRect();

        // Check scrollability
        return {
            found: true,
            cls: (typeof popup.className === 'string') ? popup.className.substring(0, 60) : '',
            x: Math.round(rect.x + rect.width/2),
            y: Math.round(rect.y + rect.height/2),
            w: Math.round(rect.width),
            h: Math.round(rect.height),
            scrollable: popup.scrollHeight > popup.clientHeight,
            scrollHeight: popup.scrollHeight,
            clientHeight: popup.clientHeight,
            overflow: window.getComputedStyle(popup).overflow,
            overflowY: window.getComputedStyle(popup).overflowY
        };
    }""")
    print(f"  Popup: {json.dumps(popup_state)}")

    if popup_state.get('found'):
        # Use mouse.wheel to scroll down within the popup
        cx = popup_state['x']
        cy = popup_state['y']
        print(f"  Moving mouse to popup center ({cx}, {cy})...")
        page.mouse.move(cx, cy)
        page.wait_for_timeout(300)

        # Scroll down aggressively
        print("  Scrolling down with mouse wheel...")
        for i in range(10):
            page.mouse.wheel(0, 300)  # deltaY = 300
            page.wait_for_timeout(200)

        page.wait_for_timeout(500)
        screenshot(page, "p271_model_popup_scrolled")

        # Now check if Wan 2.1 is visible
        wan_visible = page.evaluate("""() => {
            for (var el of document.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                if (text.startsWith('Wan 2.1') && el.offsetHeight > 0 && el.offsetHeight < 100) {
                    var rect = el.getBoundingClientRect();
                    if (rect.y > 0 && rect.y < window.innerHeight) {
                        return {
                            visible: true,
                            text: text.substring(0, 50),
                            x: Math.round(rect.x + rect.width/2),
                            y: Math.round(rect.y + rect.height/2),
                            w: Math.round(rect.width),
                            h: Math.round(rect.height)
                        };
                    }
                }
            }
            return {visible: false};
        }""")
        print(f"  Wan 2.1 visible: {json.dumps(wan_visible)}")

        if wan_visible.get('visible'):
            # Click the Wan 2.1 card
            # Need to click the actual model card, not just the text
            # The card is likely the parent element with height 60-120px
            print(f"  Clicking Wan 2.1 at ({wan_visible['x']}, {wan_visible['y']})...")
            page.mouse.click(wan_visible['x'], wan_visible['y'])
            page.wait_for_timeout(1500)

            # Check if popup closed and model changed
            model_check = page.evaluate("""() => {
                var panel = document.querySelector('.c-gen-config.show');
                if (!panel) return {noPanel: true};
                var sel = panel.querySelector('.custom-selector-wrapper');
                if (!sel) return {noSelector: true};
                // Get just the displayed model name (first line of text)
                var nameEl = sel.querySelector('[class*="name"], .model-name, span');
                var name = nameEl ? (nameEl.innerText || '').trim() : '';
                if (!name) name = (sel.innerText || '').trim().split('\\n')[0];
                // Also check generate button cost
                var genCost = '';
                for (var btn of panel.querySelectorAll('button')) {
                    if ((btn.innerText || '').includes('Generate')) {
                        genCost = (btn.innerText || '').trim();
                    }
                }
                return {model: name, genCost: genCost};
            }""")
            print(f"  Model check: {json.dumps(model_check)}")

            if model_check.get('model') and 'Wan 2.1' in model_check.get('model', ''):
                print("  MODEL SELECTOR FIX CONFIRMED!")
            elif '6' in model_check.get('genCost', ''):
                print("  Cost is 6 — likely Wan 2.1!")
            else:
                # Popup might still be open. Try clicking the card area
                print("  Popup may still be open. Trying el.click() on Wan 2.1 card...")
                card_click = page.evaluate("""() => {
                    // Find Wan 2.1 card — a clickable element with Wan 2.1 text
                    for (var el of document.querySelectorAll('div, li, a')) {
                        var text = (el.innerText || '').trim();
                        if (text.includes('Wan 2.1') && text.includes('6 credits') && el.offsetHeight > 40 && el.offsetHeight < 150) {
                            var rect = el.getBoundingClientRect();
                            if (rect.y > 0 && rect.y < window.innerHeight) {
                                el.click();
                                return {clicked: true, text: text.substring(0, 50), h: el.offsetHeight};
                            }
                        }
                    }
                    return {clicked: false};
                }""")
                print(f"  Card click: {json.dumps(card_click)}")
                page.wait_for_timeout(1000)

                # Check again
                final_model = page.evaluate("""() => {
                    var panel = document.querySelector('.c-gen-config.show');
                    if (!panel) return {};
                    var sel = panel.querySelector('.custom-selector-wrapper');
                    var model = sel ? (sel.innerText || '').trim().split('\\n')[0] : 'unknown';
                    var genCost = '';
                    for (var btn of panel.querySelectorAll('button')) {
                        if ((btn.innerText || '').includes('Generate')) genCost = (btn.innerText || '').trim();
                    }
                    return {model: model, genCost: genCost};
                }""")
                print(f"  Final model: {json.dumps(final_model)}")
        else:
            # Wan 2.1 still not visible. Try finding the scrollable child
            print("  Wan 2.1 not visible. Trying to find + scroll inner container...")

            inner_scroll = page.evaluate("""() => {
                // Find scrollable elements inside the popup
                var all = document.querySelectorAll('*');
                var scrollables = [];
                for (var el of all) {
                    if (el.scrollHeight > el.clientHeight + 50 && el.offsetHeight > 100 && el.offsetWidth > 200) {
                        var text = (el.innerText || '');
                        if (text.includes('Minimax') || text.includes('Wan')) {
                            scrollables.push({
                                cls: (typeof el.className === 'string') ? el.className.substring(0, 50) : '',
                                scrollHeight: el.scrollHeight,
                                clientHeight: el.clientHeight,
                                scrollTop: Math.round(el.scrollTop),
                                tag: el.tagName.toLowerCase()
                            });
                        }
                    }
                }
                return scrollables;
            }""")
            print(f"  Scrollable elements: {json.dumps(inner_scroll)}")

            # Try scrolling each one
            for i, s in enumerate(inner_scroll):
                print(f"  Scrolling element {i} ({s['cls'][:30]}) to bottom...")
                page.evaluate(f"""() => {{
                    var all = document.querySelectorAll('*');
                    var scrollables = [];
                    for (var el of all) {{
                        if (el.scrollHeight > el.clientHeight + 50 && el.offsetHeight > 100 && el.offsetWidth > 200) {{
                            var text = (el.innerText || '');
                            if (text.includes('Minimax') || text.includes('Wan')) {{
                                scrollables.push(el);
                            }}
                        }}
                    }}
                    if (scrollables[{i}]) scrollables[{i}].scrollTop = scrollables[{i}].scrollHeight;
                }}""")
                page.wait_for_timeout(500)

            screenshot(page, "p271_inner_scrolled")

            # Check Wan 2.1 now
            wan_now = page.evaluate("""() => {
                for (var el of document.querySelectorAll('*')) {
                    var text = (el.innerText || '').trim();
                    if (text.startsWith('Wan 2.1') && el.offsetHeight > 0 && el.offsetHeight < 100) {
                        var rect = el.getBoundingClientRect();
                        if (rect.y > 0 && rect.y < window.innerHeight) {
                            return {visible: true, x: Math.round(rect.x + rect.width/2), y: Math.round(rect.y + rect.height/2)};
                        }
                    }
                }
                return {visible: false};
            }""")
            print(f"  Wan 2.1 after inner scroll: {json.dumps(wan_now)}")

            if wan_now.get('visible'):
                page.mouse.click(wan_now['x'], wan_now['y'])
                page.wait_for_timeout(1000)
                result = page.evaluate("""() => {
                    var panel = document.querySelector('.c-gen-config.show');
                    if (!panel) return {};
                    var sel = panel.querySelector('.custom-selector-wrapper');
                    var model = sel ? (sel.innerText || '').trim().split('\\n')[0] : 'unknown';
                    var genCost = '';
                    for (var btn of panel.querySelectorAll('button')) {
                        if ((btn.innerText || '').includes('Generate')) genCost = (btn.innerText || '').trim();
                    }
                    return {model: model, genCost: genCost};
                }""")
                print(f"  Result: {json.dumps(result)}")

    # Close popup if still open
    page.keyboard.press('Escape')
    page.wait_for_timeout(500)

    screenshot(page, "p271_model_result")

    # ================================================================
    # FIX 2: Structure Match Slider
    # ================================================================
    print("\n" + "=" * 70)
    print("FIX 2: Structure Match Slider (drag approach)")
    print("=" * 70)

    # Close panels and open Img2Img
    page.keyboard.press('Escape')
    page.wait_for_timeout(300)
    page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (panel) {
            var close = panel.querySelector('.ico-close, button.close');
            if (close) close.click();
        }
    }""")
    page.wait_for_timeout(300)

    page.mouse.click(40, 252)
    page.wait_for_timeout(2500)

    panel_check = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return 'none';
        return (panel.innerText || '').substring(0, 30).trim();
    }""")
    print(f"  Panel: {panel_check}")

    if 'Image-to-Image' in panel_check:
        # Map slider children precisely
        slider_details = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return {};
            var slider = panel.querySelector('.c-slider');
            if (!slider) return {noSlider: true};

            var sliderRect = slider.getBoundingClientRect();

            // Map ALL children with their exact positions
            var children = [];
            for (var child of slider.querySelectorAll('*')) {
                var r = child.getBoundingClientRect();
                if (r.height > 0 && r.width > 0) {
                    var cs = window.getComputedStyle(child);
                    children.push({
                        tag: child.tagName.toLowerCase(),
                        cls: (typeof child.className === 'string') ? child.className : '',
                        x: Math.round(r.x),
                        y: Math.round(r.y),
                        w: Math.round(r.width),
                        h: Math.round(r.height),
                        bg: cs.backgroundColor,
                        border: cs.borderRadius,
                        cursor: cs.cursor,
                        position: cs.position
                    });
                }
            }

            // Also get the value display near the slider
            var valueNum = '';
            var labelText = '';
            for (var el of panel.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                var r = el.getBoundingClientRect();
                if (r.y > sliderRect.y - 30 && r.y < sliderRect.y + sliderRect.height + 30) {
                    if (text.match(/^\\d\\.\\d+$/) || text.match(/^\\d$/)) {
                        valueNum = text;
                    }
                    if (['Very similar', 'Similar', 'Less similar', 'Different'].includes(text)) {
                        labelText = text;
                    }
                }
            }

            return {
                slider: {x: Math.round(sliderRect.x), y: Math.round(sliderRect.y), w: Math.round(sliderRect.width), h: Math.round(sliderRect.height)},
                children: children,
                value: valueNum,
                label: labelText
            };
        }""")

        print(f"  Slider: {json.dumps(slider_details.get('slider'))}")
        print(f"  Value: {slider_details.get('value')}")
        print(f"  Label: {slider_details.get('label')}")
        print(f"  Children ({len(slider_details.get('children', []))}):")
        for c in slider_details.get('children', []):
            cursor = f" cursor={c['cursor']}" if c.get('cursor') not in ['auto', ''] else ''
            radius = f" radius={c['border']}" if c.get('border', '0px') != '0px' else ''
            print(f"    {c['tag']:5s} {c['w']:3d}x{c['h']:3d} at ({c['x']},{c['y']}) cls={c['cls'][:25]}{cursor}{radius}")

        # Find the draggable thumb (usually has cursor: pointer or grab, and border-radius for circle)
        sl = slider_details.get('slider', {})
        children = slider_details.get('children', [])

        # Look for small circular element (thumb)
        thumb = None
        for c in children:
            if (c.get('border', '0px') != '0px' and c['w'] < 30 and c['h'] < 30) or \
               c.get('cursor') in ['pointer', 'grab', 'ew-resize'] or \
               'thumb' in c.get('cls', '').lower() or 'handle' in c.get('cls', '').lower():
                thumb = c
                break

        if not thumb:
            # Fallback: find the smallest square-ish child
            for c in children:
                if c['w'] < 25 and c['h'] < 25 and c['w'] == c['h']:
                    thumb = c
                    break

        if thumb:
            tx = thumb['x'] + thumb['w'] // 2
            ty = thumb['y'] + thumb['h'] // 2
            print(f"\n  Found thumb at ({tx}, {ty}) {thumb['w']}x{thumb['h']}")

            # Test positions: drag to 0%, 50%, 100%
            for pct, label in [(0, 'min'), (50, 'mid'), (100, 'max')]:
                target_x = sl['x'] + int(sl['w'] * pct / 100)
                print(f"\n  Dragging to {pct}% (x={target_x})...")

                # Re-find thumb position (it moves after drag)
                current_thumb = page.evaluate("""() => {
                    var panel = document.querySelector('.c-gen-config.show');
                    if (!panel) return null;
                    var slider = panel.querySelector('.c-slider');
                    if (!slider) return null;
                    for (var child of slider.querySelectorAll('*')) {
                        var r = child.getBoundingClientRect();
                        if (r.width < 25 && r.height < 25 && r.width === r.height && r.width > 5) {
                            return {x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)};
                        }
                    }
                    // Fallback: use slider center y
                    var sr = slider.getBoundingClientRect();
                    return {x: Math.round(sr.x + sr.width/2), y: Math.round(sr.y + sr.height/2)};
                }""")

                if current_thumb:
                    page.mouse.move(current_thumb['x'], current_thumb['y'])
                    page.mouse.down()
                    # Move in steps for smoother drag
                    page.mouse.move(target_x, current_thumb['y'], steps=20)
                    page.mouse.up()
                    page.wait_for_timeout(500)

                    # Read value
                    state = page.evaluate("""() => {
                        var panel = document.querySelector('.c-gen-config.show');
                        if (!panel) return {};
                        var value = '', label = '';
                        for (var el of panel.querySelectorAll('*')) {
                            var text = (el.innerText || '').trim();
                            var r = el.getBoundingClientRect();
                            if (r.y > 330 && r.y < 400) {
                                if (text.match(/^\\d\\.\\d+$/)) value = text;
                                if (['Very similar', 'Similar', 'Less similar', 'Different', 'Exact', 'Flexible'].includes(text)) label = text;
                            }
                        }
                        return {value: value, label: label};
                    }""")
                    print(f"    Result: value={state.get('value', '?')} label='{state.get('label', '?')}'")
        else:
            print("  No thumb element found. Trying direct click approach...")
            # Maybe it's not a drag slider but a step slider (click on tick marks)
            # Try clicking directly on the slider track at different positions
            sy = sl['y'] + sl['h'] // 2
            for pct in [0, 25, 50, 75, 100]:
                sx = sl['x'] + int(sl['w'] * pct / 100)
                page.mouse.click(sx, sy)
                page.wait_for_timeout(500)
                state = page.evaluate("""() => {
                    var panel = document.querySelector('.c-gen-config.show');
                    if (!panel) return {};
                    for (var el of panel.querySelectorAll('*')) {
                        var text = (el.innerText || '').trim();
                        if (['Very similar', 'Similar', 'Less similar', 'Different'].includes(text)) return {label: text};
                    }
                    return {};
                }""")
                print(f"  Click at {pct}%: {state.get('label', '?')}")

        screenshot(page, "p271_slider_result")

    # ================================================================
    # Credits
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
    print("EXPLORATION PART 27 COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
