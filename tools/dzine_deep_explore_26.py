#!/usr/bin/env python3
"""Dzine Deep Exploration Part 26 — Model Selector Scroll Fix + Deep Dives.

Part 25 findings:
- Video download via URL extraction WORKS (355KB MP4 from static.dzine.ai)
- Model selector: 34 models in scrollable 4-column grid
  - Sorted by recommendation NOT price — Wan 2.1 is at BOTTOM
  - Need to scroll popup down to find Wan 2.1
  - Filter tabs: "Video Model", "Uncensored", "Start/Last Frame"
- Local Edit: Lasso/Brush/Auto, Prompt/Balanced/Image control, 4 credits
- Structure Match slider didn't respond to mouse clicks at different positions
- Toolbar still empty (0 buttons) even with canvas selection

Part 26 goals:
1. Fix model selector — scroll popup to bottom, then click Wan 2.1
2. Test "Uncensored" filter in model selector
3. Map the Structure Match slider properly (maybe drag, not click)
4. Test Enhance & Upscale from results panel
5. Generate a test video with Wan 2.1 to verify model switch works
"""

import json
import os
import sys
import base64
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


def close_panels(page):
    page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (panel) {
            var close = panel.querySelector('.ico-close, button.close');
            if (close) close.click();
        }
        for (var el of document.querySelectorAll('.ico-close')) {
            if (el.offsetHeight > 0) try { el.click(); } catch(e) {}
        }
    }""")
    page.wait_for_timeout(300)
    page.keyboard.press('Escape')
    page.wait_for_timeout(300)


def main():
    print("=" * 70)
    print("DZINE DEEP EXPLORATION PART 26")
    print("Model Selector Scroll Fix + Enhance + Structure Match")
    print("=" * 70)

    browser, context, _, _pw = connect_or_launch()
    page = context.pages[0]
    print(f"Connected. URL: {page.url}")

    if "dzine.ai/canvas" not in page.url:
        page.goto("https://www.dzine.ai/canvas?id=19861203")
        page.wait_for_timeout(5000)

    # ================================================================
    # TASK 1: Fix Model Selector — Scroll + Click Wan 2.1
    # ================================================================
    print("\n" + "=" * 70)
    print("TASK 1: Fix Model Selector (scroll popup to Wan 2.1)")
    print("=" * 70)

    close_panels(page)
    page.wait_for_timeout(500)

    # Open AI Video
    page.mouse.click(40, 361)
    page.wait_for_timeout(2500)

    panel = get_active_panel(page)
    print(f"  Panel: {panel}")

    if panel == 'ai_video':
        # Open model selector
        page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return;
            var sel = panel.querySelector('.custom-selector-wrapper');
            if (sel) sel.click();
        }""")
        page.wait_for_timeout(1500)

        # Find the scrollable body of the model popup
        scroll_info = page.evaluate("""() => {
            // Find the popup panel body that's scrollable
            var candidates = document.querySelectorAll('.panel-body, .selector-panel, [class*="model-list"], [class*="scroll"]');
            for (var el of candidates) {
                if (el.scrollHeight > el.clientHeight + 50 && el.offsetHeight > 200) {
                    return {
                        cls: (typeof el.className === 'string') ? el.className.substring(0, 50) : '',
                        scrollHeight: el.scrollHeight,
                        clientHeight: el.clientHeight,
                        scrollTop: el.scrollTop,
                        maxScroll: el.scrollHeight - el.clientHeight
                    };
                }
            }
            // Try broader search
            for (var el of document.querySelectorAll('*')) {
                if (el.scrollHeight > el.clientHeight + 100 && el.offsetHeight > 200 && el.offsetWidth > 300) {
                    var text = (el.innerText || '');
                    if (text.includes('Wan 2.1')) {
                        return {
                            cls: (typeof el.className === 'string') ? el.className.substring(0, 50) : '',
                            scrollHeight: el.scrollHeight,
                            clientHeight: el.clientHeight,
                            scrollTop: el.scrollTop,
                            maxScroll: el.scrollHeight - el.clientHeight
                        };
                    }
                }
            }
            return {found: false};
        }""")
        print(f"  Scroll container: {json.dumps(scroll_info)}")

        if scroll_info.get('maxScroll'):
            # Scroll to bottom to show Wan 2.1
            print(f"  Scrolling to bottom (max={scroll_info['maxScroll']})...")
            page.evaluate("""() => {
                var candidates = document.querySelectorAll('.panel-body, .selector-panel, [class*="model-list"], [class*="scroll"]');
                for (var el of candidates) {
                    if (el.scrollHeight > el.clientHeight + 50 && el.offsetHeight > 200) {
                        el.scrollTop = el.scrollHeight;
                        return true;
                    }
                }
                // Broader search
                for (var el of document.querySelectorAll('*')) {
                    if (el.scrollHeight > el.clientHeight + 100 && el.offsetHeight > 200 && el.offsetWidth > 300) {
                        var text = (el.innerText || '');
                        if (text.includes('Wan 2.1')) {
                            el.scrollTop = el.scrollHeight;
                            return true;
                        }
                    }
                }
                return false;
            }""")
            page.wait_for_timeout(1000)

            screenshot(page, "p261_model_popup_scrolled")

            # Now find Wan 2.1 position
            wan_pos = page.evaluate("""() => {
                for (var el of document.querySelectorAll('*')) {
                    var text = (el.innerText || '').trim();
                    if (text.startsWith('Wan 2.1') && el.offsetHeight > 0 && el.offsetHeight < 80) {
                        var rect = el.getBoundingClientRect();
                        // Must be visible in viewport
                        if (rect.y > 0 && rect.y < window.innerHeight && rect.x > 0) {
                            return {
                                text: text.substring(0, 40),
                                x: Math.round(rect.x + rect.width/2),
                                y: Math.round(rect.y + rect.height/2),
                                w: Math.round(rect.width),
                                h: Math.round(rect.height),
                                tag: el.tagName.toLowerCase(),
                                cls: (typeof el.className === 'string') ? el.className.substring(0, 40) : ''
                            };
                        }
                    }
                }
                return null;
            }""")
            print(f"  Wan 2.1 position: {json.dumps(wan_pos)}")

            if wan_pos:
                # Click it!
                print(f"  Clicking Wan 2.1 at ({wan_pos['x']}, {wan_pos['y']})...")
                page.mouse.click(wan_pos['x'], wan_pos['y'])
                page.wait_for_timeout(1500)

                # Verify
                new_model = page.evaluate("""() => {
                    var panel = document.querySelector('.c-gen-config.show');
                    if (!panel) return 'no panel';
                    var sel = panel.querySelector('.custom-selector-wrapper');
                    if (!sel) return 'no selector';
                    // Get just the model name, not the full popup text
                    var name = sel.querySelector('[class*="name"], span');
                    if (name) return (name.innerText || '').trim();
                    return (sel.innerText || '').trim().split('\\n')[0];
                }""")
                print(f"  New model: {new_model}")

                # Check generate cost
                gen_cost = page.evaluate("""() => {
                    var panel = document.querySelector('.c-gen-config.show');
                    if (!panel) return '';
                    for (var btn of panel.querySelectorAll('button')) {
                        if ((btn.innerText || '').includes('Generate')) {
                            return (btn.innerText || '').trim();
                        }
                    }
                    return '';
                }""")
                print(f"  Generate: {gen_cost}")

                if '6' in gen_cost and 'Wan' in (new_model or ''):
                    print("  MODEL SELECTOR FIX CONFIRMED! Wan 2.1 at 6 credits!")
                else:
                    print("  May not have switched correctly. Let me try clicking the card directly...")
                    # The card might need clicking on a specific child element
                    page.evaluate("""() => {
                        var panel = document.querySelector('.c-gen-config.show');
                        if (!panel) return;
                        var sel = panel.querySelector('.custom-selector-wrapper');
                        if (sel) sel.click();
                    }""")
                    page.wait_for_timeout(1000)
                    # Scroll down again
                    page.evaluate("""() => {
                        for (var el of document.querySelectorAll('*')) {
                            if (el.scrollHeight > el.clientHeight + 100 && el.offsetHeight > 200 && el.offsetWidth > 300) {
                                if ((el.innerText || '').includes('Wan 2.1')) {
                                    el.scrollTop = el.scrollHeight;
                                    return;
                                }
                            }
                        }
                    }""")
                    page.wait_for_timeout(500)

                    # Try clicking the card (parent container of the text)
                    card_clicked = page.evaluate("""() => {
                        for (var el of document.querySelectorAll('*')) {
                            var text = (el.innerText || '').trim();
                            if (text.startsWith('Wan 2.1') && el.offsetHeight > 50 && el.offsetHeight < 120) {
                                var rect = el.getBoundingClientRect();
                                if (rect.y > 0 && rect.y < window.innerHeight) {
                                    el.click();
                                    return {clicked: true, text: text.substring(0, 40), h: el.offsetHeight};
                                }
                            }
                        }
                        return {clicked: false};
                    }""")
                    print(f"  Card click: {json.dumps(card_clicked)}")
                    page.wait_for_timeout(1000)

                    new_model2 = page.evaluate("""() => {
                        var panel = document.querySelector('.c-gen-config.show');
                        if (!panel) return 'no panel';
                        var sel = panel.querySelector('.custom-selector-wrapper');
                        return sel ? (sel.innerText || '').trim().split('\\n')[0] : 'unknown';
                    }""")
                    gen_cost2 = page.evaluate("""() => {
                        var panel = document.querySelector('.c-gen-config.show');
                        if (!panel) return '';
                        for (var btn of panel.querySelectorAll('button')) {
                            if ((btn.innerText || '').includes('Generate')) return (btn.innerText || '').trim();
                        }
                        return '';
                    }""")
                    print(f"  Model after card click: {new_model2}")
                    print(f"  Generate after card click: {gen_cost2}")
            else:
                print("  Wan 2.1 NOT visible after scroll. Trying different approach...")
                # Use keyboard to search?
                # Or try the "Uncensored" filter which should include Wan 2.1
                page.evaluate("""() => {
                    for (var el of document.querySelectorAll('*')) {
                        if ((el.innerText || '').trim() === 'Uncensored' && el.offsetHeight > 0 && el.offsetHeight < 40) {
                            var rect = el.getBoundingClientRect();
                            if (rect.y < 100) { el.click(); return; }
                        }
                    }
                }""")
                page.wait_for_timeout(1000)
                screenshot(page, "p261_uncensored_filter")

        screenshot(page, "p261_model_final")

    # ================================================================
    # TASK 2: Enhance & Upscale from Results
    # ================================================================
    print("\n" + "=" * 70)
    print("TASK 2: Enhance & Upscale via Results Panel")
    print("=" * 70)

    close_panels(page)
    page.wait_for_timeout(500)

    # Results panel
    page.evaluate("""() => {
        for (var el of document.querySelectorAll('[class*="header-item"]')) {
            if ((el.innerText || '').includes('Result')) { el.click(); return; }
        }
    }""")
    page.wait_for_timeout(500)

    # Scroll results to txt2img section and click Enhance [1]
    # First scroll to find txt2img results
    scrolled = page.evaluate("""() => {
        var container = document.querySelector('[class*="result-container"], [class*="result-list"], .right-panel');
        if (!container) return 'no container';
        // Find the results panel body
        for (var el of document.querySelectorAll('[class*="result"]')) {
            if (el.scrollHeight > el.clientHeight + 50 && el.offsetHeight > 200) {
                // Scroll down to find Enhance row
                el.scrollTop = el.scrollHeight / 2; // Scroll to middle
                return {scrolled: true, scrollHeight: el.scrollHeight, scrollTop: el.scrollTop};
            }
        }
        return 'no scrollable';
    }""")
    print(f"  Scroll: {json.dumps(scrolled)}")
    page.wait_for_timeout(500)

    # Now find Enhance & Upscale buttons
    enhance_btns = page.evaluate("""() => {
        var results = [];
        var containers = document.querySelectorAll('.btn-container');
        for (var c of containers) {
            var parent = c.parentElement;
            var parentText = (parent ? parent.innerText || '' : '').trim();
            if (parentText.includes('Enhance')) {
                var rect = c.getBoundingClientRect();
                if (rect.height > 0 && rect.y > 0 && rect.y < 900) {
                    var btns = [];
                    for (var btn of c.querySelectorAll('.btn')) {
                        var br = btn.getBoundingClientRect();
                        btns.push({x: Math.round(br.x + br.width/2), y: Math.round(br.y + br.height/2), text: (btn.innerText || '').trim()});
                    }
                    results.push({parentText: parentText.substring(0, 30), y: Math.round(rect.y), btns: btns});
                }
            }
        }
        return results;
    }""")
    print(f"  Enhance containers ({len(enhance_btns)}):")
    for e in enhance_btns:
        print(f"    y={e['y']} '{e['parentText']}' btns={len(e['btns'])}")
        for b in e['btns']:
            print(f"      ({b['x']}, {b['y']}) '{b['text']}'")

    if enhance_btns and enhance_btns[0]['btns']:
        btn = enhance_btns[0]['btns'][0]
        print(f"\n  Clicking Enhance [{btn['text']}] at ({btn['x']}, {btn['y']})...")
        page.mouse.click(btn['x'], btn['y'])
        page.wait_for_timeout(2000)

        # Check for popup
        popup = page.evaluate("""() => {
            for (var el of document.querySelectorAll('[class*="enhance"], [class*="upscale"], [class*="dialog"], [class*="popup"]')) {
                if (el.offsetHeight > 100 && el.offsetWidth > 200) {
                    var text = (el.innerText || '');
                    if (text.includes('Upscale') || text.includes('Enhance') || text.includes('Scale')) {
                        return {
                            found: true,
                            text: text.substring(0, 500),
                            cls: (typeof el.className === 'string') ? el.className.substring(0, 60) : ''
                        };
                    }
                }
            }
            return {found: false};
        }""")

        if popup.get('found'):
            print(f"  Enhance popup opened!")
            for line in popup['text'].split('\n')[:15]:
                line = line.strip()
                if line:
                    print(f"    > {line[:60]}")

            screenshot(page, "p261_enhance_popup")

            # Map scale options
            scales = page.evaluate("""() => {
                var items = [];
                for (var btn of document.querySelectorAll('button, [role="button"]')) {
                    var text = (btn.innerText || '').trim();
                    if (text.match(/^\\d+(\\.\\d+)?x$/)) {
                        var cls = (typeof btn.className === 'string') ? btn.className : '';
                        items.push({text: text, selected: cls.includes('selected') || cls.includes('active')});
                    }
                }
                return items;
            }""")
            print(f"  Scale options: {json.dumps(scales)}")

            # Check target resolution and cost
            details = page.evaluate("""() => {
                var result = {};
                for (var el of document.querySelectorAll('*')) {
                    var text = (el.innerText || '').trim();
                    if (text.match(/\\d+\\s*[×x]\\s*\\d+/) && el.offsetHeight > 0 && el.offsetHeight < 30) {
                        result.resolution = text;
                    }
                }
                for (var btn of document.querySelectorAll('button')) {
                    if ((btn.innerText || '').includes('Upscale')) {
                        result.upscaleBtn = (btn.innerText || '').trim();
                    }
                }
                // Check format options
                for (var el of document.querySelectorAll('*')) {
                    var text = (el.innerText || '').trim();
                    if (['PNG', 'JPG'].includes(text)) {
                        var cls = (typeof el.className === 'string' ? el.className : '');
                        if (cls.includes('selected') || cls.includes('active')) {
                            result.format = text;
                        }
                    }
                }
                // Check mode
                for (var el of document.querySelectorAll('*')) {
                    var text = (el.innerText || '').trim();
                    if (['Precision', 'Creative'].includes(text)) {
                        var cls = (typeof el.className === 'string' ? el.className : '');
                        if (cls.includes('selected') || cls.includes('active') || cls.includes('checked')) {
                            result.mode = text;
                        }
                    }
                }
                return result;
            }""")
            print(f"  Details: {json.dumps(details)}")

            # Select 1.5x (cheapest) and upscale to test
            page.evaluate("""() => {
                for (var btn of document.querySelectorAll('button, [role="button"]')) {
                    if ((btn.innerText || '').trim() === '1.5x') { btn.click(); return; }
                }
            }""")
            page.wait_for_timeout(300)

            # Check updated resolution
            updated = page.evaluate("""() => {
                for (var el of document.querySelectorAll('*')) {
                    var text = (el.innerText || '').trim();
                    if (text.match(/\\d+\\s*[×x]\\s*\\d+/) && el.offsetHeight > 0 && el.offsetHeight < 30) {
                        return text;
                    }
                }
                return 'unknown';
            }""")
            print(f"  At 1.5x: {updated}")

            # Now try 4x for documentation
            page.evaluate("""() => {
                for (var btn of document.querySelectorAll('button, [role="button"]')) {
                    if ((btn.innerText || '').trim() === '4x') { btn.click(); return; }
                }
            }""")
            page.wait_for_timeout(300)
            updated4x = page.evaluate("""() => {
                for (var el of document.querySelectorAll('*')) {
                    var text = (el.innerText || '').trim();
                    if (text.match(/\\d+\\s*[×x]\\s*\\d+/) && el.offsetHeight > 0 && el.offsetHeight < 30) {
                        return text;
                    }
                }
                return 'unknown';
            }""")
            cost4x = page.evaluate("""() => {
                for (var btn of document.querySelectorAll('button')) {
                    if ((btn.innerText || '').includes('Upscale')) return (btn.innerText || '').trim();
                }
                return '';
            }""")
            print(f"  At 4x: {updated4x} cost={cost4x}")

            screenshot(page, "p261_enhance_4x")

            # Close without upscaling
            page.keyboard.press('Escape')
            page.wait_for_timeout(500)
        else:
            print("  Enhance popup didn't open")
    else:
        print("  No Enhance buttons visible — may need to scroll results more")

    # ================================================================
    # TASK 3: Structure Match — Drag interaction
    # ================================================================
    print("\n" + "=" * 70)
    print("TASK 3: Structure Match Slider (drag interaction)")
    print("=" * 70)

    close_panels(page)
    page.wait_for_timeout(500)

    # Open Img2Img
    page.mouse.click(40, 252)
    page.wait_for_timeout(2500)

    panel = get_active_panel(page)
    print(f"  Panel: {panel}")

    if panel == 'img2img':
        # Find the slider thumb/handle
        slider_info = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return {};

            // Find c-slider element
            var slider = panel.querySelector('.c-slider');
            if (!slider) return {noSlider: true};

            var rect = slider.getBoundingClientRect();

            // Find the thumb/handle (usually a circle or div that can be dragged)
            var thumb = slider.querySelector('[class*="thumb"], [class*="handle"], [class*="knob"], [class*="dot"]');
            var thumbRect = thumb ? thumb.getBoundingClientRect() : null;

            // Find the track
            var track = slider.querySelector('[class*="track"], [class*="rail"], [class*="bar"]');
            var trackRect = track ? track.getBoundingClientRect() : null;

            // Get all children for debugging
            var children = [];
            for (var child of slider.querySelectorAll('*')) {
                var cr = child.getBoundingClientRect();
                if (cr.height > 0 && cr.width > 0) {
                    children.push({
                        cls: (typeof child.className === 'string') ? child.className.substring(0, 30) : '',
                        x: Math.round(cr.x),
                        y: Math.round(cr.y),
                        w: Math.round(cr.width),
                        h: Math.round(cr.height),
                        tag: child.tagName.toLowerCase()
                    });
                }
            }

            // Get current value display
            var valueEl = panel.querySelector('[class*="slider-value"]');
            var value = '';
            for (var el of panel.querySelectorAll('*')) {
                var t = (el.innerText || '').trim();
                if (t.match(/^0\.\d+$/) || t === '1' || t === '0') {
                    var r = el.getBoundingClientRect();
                    if (Math.abs(r.y - rect.y) < 30) {
                        value = t;
                        break;
                    }
                }
            }

            return {
                slider: {x: Math.round(rect.x), y: Math.round(rect.y), w: Math.round(rect.width), h: Math.round(rect.height)},
                thumb: thumbRect ? {x: Math.round(thumbRect.x + thumbRect.width/2), y: Math.round(thumbRect.y + thumbRect.height/2)} : null,
                track: trackRect ? {x: Math.round(trackRect.x), w: Math.round(trackRect.width)} : null,
                value: value,
                children: children
            };
        }""")

        print(f"  Slider: {json.dumps(slider_info.get('slider'))}")
        print(f"  Thumb: {json.dumps(slider_info.get('thumb'))}")
        print(f"  Track: {json.dumps(slider_info.get('track'))}")
        print(f"  Value: {slider_info.get('value')}")
        print(f"  Children ({len(slider_info.get('children', []))}):")
        for c in slider_info.get('children', []):
            print(f"    {c['tag']:5s} {c['w']:3d}x{c['h']:3d} at ({c['x']},{c['y']}) cls={c['cls']}")

        # Try dragging the thumb from current position to minimum (left end)
        if slider_info.get('thumb'):
            tx = slider_info['thumb']['x']
            ty = slider_info['thumb']['y']
            sx = slider_info['slider']['x']
            sw = slider_info['slider']['w']

            # Drag to left (minimum = 0)
            print(f"\n  Dragging slider to minimum (left={sx})...")
            page.mouse.move(tx, ty)
            page.mouse.down()
            page.mouse.move(sx, ty, steps=10)
            page.mouse.up()
            page.wait_for_timeout(500)

            # Check value
            min_state = page.evaluate("""() => {
                var panel = document.querySelector('.c-gen-config.show');
                if (!panel) return {};
                for (var el of panel.querySelectorAll('*')) {
                    var t = (el.innerText || '').trim();
                    if (t.match(/^0\\.\\d+$/) || t === '0' || t === '1') {
                        var rect = el.getBoundingClientRect();
                        if (rect.y > 300 && rect.y < 400 && rect.height < 25) return {value: t};
                    }
                }
                // Also check label
                for (var el of panel.querySelectorAll('*')) {
                    var t = (el.innerText || '').trim();
                    if (['Very similar', 'Similar', 'Less similar', 'Different', 'Exact', 'Flexible'].includes(t)) {
                        return {label: t};
                    }
                }
                return {};
            }""")
            print(f"  Min: {json.dumps(min_state)}")

            # Drag to right (maximum = 1)
            # Need to re-find thumb position after drag
            new_thumb = page.evaluate("""() => {
                var panel = document.querySelector('.c-gen-config.show');
                if (!panel) return null;
                var slider = panel.querySelector('.c-slider');
                if (!slider) return null;
                var thumb = slider.querySelector('[class*="thumb"], [class*="handle"], [class*="knob"], [class*="dot"]');
                if (!thumb) return null;
                var rect = thumb.getBoundingClientRect();
                return {x: Math.round(rect.x + rect.width/2), y: Math.round(rect.y + rect.height/2)};
            }""")
            if new_thumb:
                print(f"  Dragging slider to maximum (right={sx + sw})...")
                page.mouse.move(new_thumb['x'], new_thumb['y'])
                page.mouse.down()
                page.mouse.move(sx + sw, new_thumb['y'], steps=10)
                page.mouse.up()
                page.wait_for_timeout(500)

                max_state = page.evaluate("""() => {
                    var panel = document.querySelector('.c-gen-config.show');
                    if (!panel) return {};
                    for (var el of panel.querySelectorAll('*')) {
                        var t = (el.innerText || '').trim();
                        if (t.match(/^0\\.\\d+$/) || t === '0' || t === '1') {
                            var rect = el.getBoundingClientRect();
                            if (rect.y > 300 && rect.y < 400 && rect.height < 25) return {value: t};
                        }
                    }
                    for (var el of panel.querySelectorAll('*')) {
                        var t = (el.innerText || '').trim();
                        if (['Very similar', 'Similar', 'Less similar', 'Different', 'Exact', 'Flexible'].includes(t)) {
                            return {label: t};
                        }
                    }
                    return {};
                }""")
                print(f"  Max: {json.dumps(max_state)}")

        screenshot(page, "p261_slider_test")

    # ================================================================
    # TASK 4: Test Enhance & Upscale from sidebar
    # ================================================================
    print("\n" + "=" * 70)
    print("TASK 4: Enhance & Upscale Panel from Sidebar")
    print("=" * 70)

    close_panels(page)
    page.wait_for_timeout(500)

    # Open Enhance & Upscale from sidebar (y=630)
    page.mouse.click(40, 630)
    page.wait_for_timeout(2500)

    panel = get_active_panel(page)
    print(f"  Panel: {panel}")

    if panel == 'enhance' or panel.startswith('unknown:Enhance'):
        enhance_map = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return {};
            return {
                text: (panel.innerText || '').substring(0, 600),
                buttons: Array.from(panel.querySelectorAll('button')).map(b => (b.innerText || '').trim()).filter(t => t.length > 0 && t.length < 30).slice(0, 20),
                hasUpload: !!panel.querySelector('[class*="upload"], input[type="file"]'),
                tabs: Array.from(panel.querySelectorAll('[class*="tab"], [role="tab"]')).map(t => (t.innerText || '').trim())
            };
        }""")
        print(f"  Has upload: {enhance_map.get('hasUpload')}")
        print(f"  Tabs: {enhance_map.get('tabs', [])}")
        print(f"  Buttons: {enhance_map.get('buttons', [])}")
        print(f"  Text:")
        for line in enhance_map.get('text', '').split('\n')[:20]:
            line = line.strip()
            if line:
                print(f"    > {line[:60]}")
        screenshot(page, "p261_enhance_sidebar")

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
    print("EXPLORATION PART 26 COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
