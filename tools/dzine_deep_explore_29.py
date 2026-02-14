#!/usr/bin/env python3
"""Dzine Deep Exploration Part 29 — Model Selector Popup Fix.

Part 28 showed the AI Video panel opens fine but the model selector popup
does NOT open with JavaScript sel.click(). The screenshot shows:
- "Minimax Hailuo 2.3" row at ~y=229 with ">" chevron on right
- Need to use page.mouse.click() directly on the row

This part:
1. Maps the exact model selector DOM structure
2. Uses page.mouse.click() to open the popup
3. Scrolls popup to find Wan 2.1
4. Selects Wan 2.1 (6 credits vs 56 for Hailuo)
5. Verifies selection stuck
"""

import json
import sys
sys.path.insert(0, "/Users/ray/Documents/openclaw")
from tools.lib.brave_profile import connect_or_launch


def screenshot(page, name):
    path = f"/Users/ray/Downloads/{name}.png"
    page.screenshot(path=path)
    print(f"  [SS] {path}")


def close_all(page):
    page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (panel) {
            var close = panel.querySelector('.ico-close, button.close');
            if (close) close.click();
        }
        for (var el of document.querySelectorAll('.ico-close')) {
            if (el.offsetHeight > 0) try { el.click(); } catch(e) {}
        }
        var pid = document.querySelector('.pick-image-dialog');
        if (pid) { var c = pid.querySelector('.ico-close'); if (c) c.click(); }
    }""")
    page.wait_for_timeout(300)
    page.keyboard.press('Escape')
    page.wait_for_timeout(300)


def main():
    print("=" * 70)
    print("DZINE DEEP EXPLORATION PART 29")
    print("Model Selector Popup Fix — mouse.click approach")
    print("=" * 70)

    browser, context, _, _pw = connect_or_launch()
    page = context.pages[0]
    print(f"Connected. URL: {page.url}")

    if "dzine.ai/canvas" not in page.url:
        page.goto("https://www.dzine.ai/canvas?id=19861203")
        page.wait_for_timeout(6000)

    close_all(page)
    page.wait_for_timeout(500)

    # Open AI Video panel
    page.mouse.click(40, 361)
    page.wait_for_timeout(2500)

    panel_check = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return 'none';
        return (panel.innerText || '').substring(0, 30).trim();
    }""")
    print(f"  Panel: {panel_check}")

    if 'AI Video' not in panel_check:
        print("  FAILED to open AI Video. Trying reload...")
        page.goto("https://www.dzine.ai/canvas?id=19861203")
        page.wait_for_timeout(6000)
        close_all(page)
        page.wait_for_timeout(500)
        page.mouse.click(40, 361)
        page.wait_for_timeout(3000)
        panel_check = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return 'none';
            return (panel.innerText || '').substring(0, 30).trim();
        }""")
        print(f"  Panel after reload: {panel_check}")

    # ================================================================
    # STEP 1: Map the model selector DOM precisely
    # ================================================================
    print("\n" + "=" * 70)
    print("STEP 1: Map Model Selector DOM")
    print("=" * 70)

    selector_map = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return {error: 'no panel'};

        // Find the model selector wrapper
        var sel = panel.querySelector('.custom-selector-wrapper');
        if (!sel) {
            // Try broader search
            var found = null;
            for (var el of panel.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                if (text.includes('Minimax Hailuo') || text.includes('Wan 2.1') || text.includes('Seedance')) {
                    if (el.offsetHeight > 20 && el.offsetHeight < 60 && el.offsetWidth > 100) {
                        found = el;
                        break;
                    }
                }
            }
            if (!found) return {error: 'no selector found'};
            var rect = found.getBoundingClientRect();
            return {
                fallback: true,
                text: (found.innerText || '').trim(),
                x: Math.round(rect.x),
                y: Math.round(rect.y),
                w: Math.round(rect.width),
                h: Math.round(rect.height),
                cx: Math.round(rect.x + rect.width/2),
                cy: Math.round(rect.y + rect.height/2),
                tag: found.tagName.toLowerCase(),
                cls: (typeof found.className === 'string') ? found.className.substring(0, 60) : ''
            };
        }

        var rect = sel.getBoundingClientRect();

        // Map children
        var children = [];
        for (var child of sel.querySelectorAll('*')) {
            var cr = child.getBoundingClientRect();
            if (cr.height > 0 && cr.width > 0) {
                children.push({
                    tag: child.tagName.toLowerCase(),
                    cls: (typeof child.className === 'string') ? child.className.substring(0, 40) : '',
                    text: (child.innerText || '').trim().substring(0, 40),
                    x: Math.round(cr.x),
                    y: Math.round(cr.y),
                    w: Math.round(cr.width),
                    h: Math.round(cr.height),
                    cx: Math.round(cr.x + cr.width / 2),
                    cy: Math.round(cr.y + cr.height / 2),
                    cursor: window.getComputedStyle(child).cursor,
                    clickable: child.onclick !== null || child.tagName === 'BUTTON' || child.tagName === 'A'
                });
            }
        }

        return {
            wrapper: {
                x: Math.round(rect.x),
                y: Math.round(rect.y),
                w: Math.round(rect.width),
                h: Math.round(rect.height),
                cx: Math.round(rect.x + rect.width/2),
                cy: Math.round(rect.y + rect.height/2),
                cursor: window.getComputedStyle(sel).cursor
            },
            text: (sel.innerText || '').trim().substring(0, 80),
            children: children,
            tag: sel.tagName.toLowerCase(),
            cls: (typeof sel.className === 'string') ? sel.className.substring(0, 60) : ''
        };
    }""")

    print(f"  Selector: {json.dumps({k: v for k, v in selector_map.items() if k != 'children'})}")
    if selector_map.get('children'):
        print(f"  Children ({len(selector_map['children'])}):")
        for c in selector_map['children']:
            cursor_info = f" cursor={c['cursor']}" if c.get('cursor') not in ['auto', ''] else ''
            click_info = " [clickable]" if c.get('clickable') else ''
            print(f"    {c['tag']:5s} {c['w']:3d}x{c['h']:3d} at ({c['x']},{c['y']}) center=({c['cx']},{c['cy']}) '{c['text'][:25]}'{cursor_info}{click_info}")

    # ================================================================
    # STEP 2: Click the model selector with page.mouse.click()
    # ================================================================
    print("\n" + "=" * 70)
    print("STEP 2: Click Model Selector with mouse")
    print("=" * 70)

    # Try multiple click targets
    click_targets = []

    if selector_map.get('wrapper'):
        w = selector_map['wrapper']
        click_targets.append(("wrapper center", w['cx'], w['cy']))
        # Also try right side (where the > chevron is)
        click_targets.append(("wrapper right (chevron)", w['x'] + w['w'] - 10, w['cy']))
        # Try left side (where model name is)
        click_targets.append(("wrapper left (name)", w['x'] + 20, w['cy']))
    elif selector_map.get('cx'):
        click_targets.append(("fallback center", selector_map['cx'], selector_map['cy']))

    # Also add children with pointer cursor
    if selector_map.get('children'):
        for c in selector_map['children']:
            if c.get('cursor') == 'pointer':
                click_targets.append((f"child '{c['text'][:15]}'", c['cx'], c['cy']))

    for label, cx, cy in click_targets:
        print(f"\n  Clicking {label} at ({cx}, {cy})...")
        page.mouse.click(cx, cy)
        page.wait_for_timeout(2000)

        # Check if popup opened
        popup = page.evaluate("""() => {
            // Look for model popup - large overlay with model names
            for (var el of document.querySelectorAll('*')) {
                var text = (el.innerText || '');
                if (text.includes('Wan 2.1') && text.includes('Minimax Hailuo') && text.includes('Seedance')) {
                    var rect = el.getBoundingClientRect();
                    if (rect.height > 200 && rect.width > 300 && rect.y > -10 && rect.y < window.innerHeight) {
                        // Check if this looks like an overlay (positioned above content)
                        var cs = window.getComputedStyle(el);
                        return {
                            found: true,
                            cls: (typeof el.className === 'string') ? el.className.substring(0, 60) : '',
                            x: Math.round(rect.x),
                            y: Math.round(rect.y),
                            w: Math.round(rect.width),
                            h: Math.round(rect.height),
                            position: cs.position,
                            zIndex: cs.zIndex,
                            tag: el.tagName.toLowerCase()
                        };
                    }
                }
            }
            // Also check for any new overlays/dialogs/modals
            for (var el of document.querySelectorAll('[class*="popup"], [class*="overlay"], [class*="modal"], [class*="dropdown"]')) {
                var rect = el.getBoundingClientRect();
                if (rect.height > 200 && rect.width > 200 && el.offsetHeight > 0) {
                    return {
                        found: true,
                        type: 'generic',
                        cls: (typeof el.className === 'string') ? el.className.substring(0, 60) : '',
                        text: (el.innerText || '').substring(0, 100),
                        x: Math.round(rect.x),
                        y: Math.round(rect.y),
                        w: Math.round(rect.width),
                        h: Math.round(rect.height)
                    };
                }
            }
            return {found: false};
        }""")

        if popup.get('found'):
            print(f"  >>> POPUP OPENED! cls={popup.get('cls')} {popup.get('w')}x{popup.get('h')} at ({popup.get('x')},{popup.get('y')})")
            screenshot(page, "p291_popup_opened")

            # Now scroll to Wan 2.1
            print("\n  Scrolling popup to find Wan 2.1...")

            # Try scrollTop on scrollable containers inside the popup
            scroll_result = page.evaluate("""() => {
                var scrolled = [];
                for (var el of document.querySelectorAll('*')) {
                    if (el.scrollHeight > el.clientHeight + 30 && el.clientHeight > 80 && el.clientHeight < 700) {
                        var text = (el.innerText || '');
                        if (text.includes('Wan 2.1') || text.includes('Minimax')) {
                            var before = el.scrollTop;
                            el.scrollTop = el.scrollHeight;
                            scrolled.push({
                                cls: (typeof el.className === 'string') ? el.className.substring(0, 40) : '',
                                before: Math.round(before),
                                after: Math.round(el.scrollTop),
                                max: el.scrollHeight - el.clientHeight
                            });
                        }
                    }
                }
                return scrolled;
            }""")
            print(f"  ScrollTop results: {json.dumps(scroll_result)}")
            page.wait_for_timeout(500)

            # Also use mouse.wheel
            pcx = popup.get('x', 300) + popup.get('w', 400) // 2
            pcy = popup.get('y', 200) + popup.get('h', 400) // 2
            print(f"  Mouse.wheel at popup center ({pcx}, {pcy})...")
            page.mouse.move(pcx, pcy)
            page.wait_for_timeout(200)
            for _ in range(20):
                page.mouse.wheel(0, 500)
                page.wait_for_timeout(100)
            page.wait_for_timeout(500)

            screenshot(page, "p291_popup_scrolled")

            # Find Wan 2.1
            wan = page.evaluate("""() => {
                var best = null;
                for (var el of document.querySelectorAll('*')) {
                    var text = (el.innerText || '').trim();
                    if (text.startsWith('Wan 2.1') && el.offsetHeight > 20 && el.offsetHeight < 120 && el.offsetWidth > 40 && el.offsetWidth < 300) {
                        var rect = el.getBoundingClientRect();
                        if (rect.y > 0 && rect.y < window.innerHeight && rect.x > 0) {
                            if (!best || (rect.width * rect.height) < best.area) {
                                best = {
                                    text: text.substring(0, 60),
                                    x: Math.round(rect.x + rect.width/2),
                                    y: Math.round(rect.y + rect.height/2),
                                    w: Math.round(rect.width),
                                    h: Math.round(rect.height),
                                    area: rect.width * rect.height,
                                    tag: el.tagName.toLowerCase()
                                };
                            }
                        }
                    }
                }
                return best;
            }""")
            print(f"  Wan 2.1: {json.dumps(wan)}")

            if wan:
                print(f"  Clicking Wan 2.1 at ({wan['x']}, {wan['y']})...")
                page.mouse.click(wan['x'], wan['y'])
                page.wait_for_timeout(2000)

                # Verify
                verify = page.evaluate("""() => {
                    var panel = document.querySelector('.c-gen-config.show');
                    if (!panel) return {noPanel: true};
                    var result = {};
                    // Check model name
                    var sel = panel.querySelector('.custom-selector-wrapper');
                    if (sel) {
                        result.selectorText = (sel.innerText || '').trim().split('\\n')[0];
                    }
                    // Check generate cost
                    for (var btn of panel.querySelectorAll('button')) {
                        var t = (btn.innerText || '').trim();
                        if (t.includes('Generate')) result.generateBtn = t;
                    }
                    // Check for any visible model name in the panel
                    for (var el of panel.querySelectorAll('*')) {
                        var t = (el.innerText || '').trim();
                        if ((t.startsWith('Wan 2.1') || t.startsWith('Minimax')) && el.offsetHeight > 0 && el.offsetHeight < 40) {
                            result.visibleModel = t;
                            break;
                        }
                    }
                    return result;
                }""")
                print(f"  Verify: {json.dumps(verify)}")

                if 'Wan' in str(verify) or '6' in verify.get('generateBtn', ''):
                    print("\n  >>> WAN 2.1 SELECTED SUCCESSFULLY! <<<")
                else:
                    print("  Selection may not have worked. Let me try clicking the card parent...")
                    # Try clicking a parent element of the Wan 2.1 text
                    page.evaluate("""() => {
                        for (var el of document.querySelectorAll('*')) {
                            var text = (el.innerText || '').trim();
                            if (text.startsWith('Wan 2.1') && el.offsetHeight > 50 && el.offsetHeight < 130 && el.offsetWidth > 80) {
                                var rect = el.getBoundingClientRect();
                                if (rect.y > 0 && rect.y < window.innerHeight) {
                                    el.click();
                                    return true;
                                }
                            }
                        }
                        return false;
                    }""")
                    page.wait_for_timeout(1500)
                    verify2 = page.evaluate("""() => {
                        var panel = document.querySelector('.c-gen-config.show');
                        if (!panel) return {};
                        var sel = panel.querySelector('.custom-selector-wrapper');
                        var model = sel ? (sel.innerText || '').trim().split('\\n')[0] : '';
                        var cost = '';
                        for (var btn of panel.querySelectorAll('button')) {
                            if ((btn.innerText || '').includes('Generate')) cost = (btn.innerText || '').trim();
                        }
                        return {model: model, cost: cost};
                    }""")
                    print(f"  After el.click(): {json.dumps(verify2)}")
            else:
                print("  Wan 2.1 still not visible. Listing all visible model cards...")
                visible_models = page.evaluate("""() => {
                    var models = [];
                    var seen = {};
                    for (var el of document.querySelectorAll('*')) {
                        var text = (el.innerText || '').trim();
                        // Match model names: known model patterns
                        var modelPatterns = ['Minimax', 'Hailuo', 'Wan', 'Seedance', 'Vidu', 'Kling', 'Runway', 'Pika', 'CogVideo', 'Luma', 'Mochi'];
                        for (var p of modelPatterns) {
                            if (text.startsWith(p) && el.offsetHeight > 20 && el.offsetHeight < 80 && el.offsetWidth > 40 && el.offsetWidth < 250 && !seen[text]) {
                                var rect = el.getBoundingClientRect();
                                if (rect.y > 0 && rect.y < window.innerHeight) {
                                    models.push({
                                        name: text.substring(0, 50),
                                        y: Math.round(rect.y),
                                        visible: rect.y > 0 && rect.y < window.innerHeight
                                    });
                                    seen[text] = true;
                                }
                            }
                        }
                    }
                    return models.sort(function(a, b) { return a.y - b.y; });
                }""")
                print(f"  Visible models ({len(visible_models)}):")
                for m in visible_models:
                    print(f"    y={m['y']} '{m['name']}'")

            # Close popup
            page.keyboard.press('Escape')
            page.wait_for_timeout(500)
            break  # Don't try other click targets
        else:
            print(f"  No popup detected")
            # Close anything that might have opened
            page.keyboard.press('Escape')
            page.wait_for_timeout(300)

    # If no click target worked, try alternative: double-click
    if not any(True for _ in []):  # Placeholder check
        pass

    screenshot(page, "p291_final_state")

    # ================================================================
    # STEP 3: Alternative — Try model selector by mapping ALL clickable
    #         elements in the panel
    # ================================================================
    print("\n" + "=" * 70)
    print("STEP 3: Map ALL clickable rows in AI Video panel")
    print("=" * 70)

    # Re-open AI Video if needed
    panel_check2 = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return 'none';
        return (panel.innerText || '').substring(0, 30).trim();
    }""")
    if 'AI Video' not in panel_check2:
        close_all(page)
        page.wait_for_timeout(300)
        page.mouse.click(40, 361)
        page.wait_for_timeout(2500)

    # Map every element with cursor: pointer in the panel
    clickables = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return [];
        var result = [];
        for (var el of panel.querySelectorAll('*')) {
            var cs = window.getComputedStyle(el);
            if (cs.cursor === 'pointer' && el.offsetHeight > 10 && el.offsetWidth > 30) {
                var rect = el.getBoundingClientRect();
                var text = (el.innerText || '').trim().substring(0, 60);
                // Skip duplicates (parent/child with same text)
                if (rect.y > 0 && rect.y < 800) {
                    result.push({
                        text: text,
                        tag: el.tagName.toLowerCase(),
                        cls: (typeof el.className === 'string') ? el.className.substring(0, 40) : '',
                        x: Math.round(rect.x + rect.width/2),
                        y: Math.round(rect.y + rect.height/2),
                        w: Math.round(rect.width),
                        h: Math.round(rect.height)
                    });
                }
            }
        }
        // Sort by y position
        return result.sort(function(a, b) { return a.y - b.y; });
    }""")

    print(f"  Pointer-cursor elements ({len(clickables)}):")
    for c in clickables:
        text_preview = c['text'].replace('\n', ' ')[:40]
        print(f"    y={c['y']:3d} {c['tag']:6s} {c['w']:3d}x{c['h']:3d} cls={c['cls'][:25]} '{text_preview}'")

    # Find the model selector row (contains "Minimax Hailuo" or "Wan")
    model_row = None
    for c in clickables:
        if 'Hailuo' in c['text'] or 'Minimax' in c['text'] or 'Wan' in c['text']:
            model_row = c
            break

    if model_row:
        print(f"\n  Found model row: '{model_row['text'][:40]}' at ({model_row['x']}, {model_row['y']}) {model_row['w']}x{model_row['h']}")
        print(f"  Clicking with page.mouse.click...")
        page.mouse.click(model_row['x'], model_row['y'])
        page.wait_for_timeout(2500)

        screenshot(page, "p291_model_click_attempt")

        # Check if popup appeared
        popup2 = page.evaluate("""() => {
            for (var el of document.querySelectorAll('*')) {
                var text = (el.innerText || '');
                if (text.includes('Wan 2.1') && text.includes('Seedance') && text.includes('Minimax')) {
                    var rect = el.getBoundingClientRect();
                    if (rect.height > 300 && rect.width > 400) {
                        return {
                            found: true,
                            cls: (typeof el.className === 'string') ? el.className.substring(0, 60) : '',
                            x: Math.round(rect.x), y: Math.round(rect.y),
                            w: Math.round(rect.width), h: Math.round(rect.height)
                        };
                    }
                }
            }
            return {found: false};
        }""")
        print(f"  Popup check: {json.dumps(popup2)}")

        if popup2.get('found'):
            print("  >>> POPUP OPENED VIA MOUSE CLICK!")

            # Scroll and find Wan 2.1
            page.mouse.move(popup2['x'] + popup2['w']//2, popup2['y'] + popup2['h']//2)
            page.wait_for_timeout(200)
            for _ in range(20):
                page.mouse.wheel(0, 500)
                page.wait_for_timeout(100)
            page.wait_for_timeout(500)

            wan2 = page.evaluate("""() => {
                for (var el of document.querySelectorAll('*')) {
                    var text = (el.innerText || '').trim();
                    if (text.startsWith('Wan 2.1') && el.offsetHeight > 20 && el.offsetHeight < 120 && el.offsetWidth > 40) {
                        var rect = el.getBoundingClientRect();
                        if (rect.y > 0 && rect.y < window.innerHeight) {
                            return {x: Math.round(rect.x + rect.width/2), y: Math.round(rect.y + rect.height/2), text: text.substring(0, 40)};
                        }
                    }
                }
                return null;
            }""")
            if wan2:
                print(f"  Clicking Wan 2.1 at ({wan2['x']}, {wan2['y']})...")
                page.mouse.click(wan2['x'], wan2['y'])
                page.wait_for_timeout(2000)

                final = page.evaluate("""() => {
                    var panel = document.querySelector('.c-gen-config.show');
                    if (!panel) return {};
                    var sel = panel.querySelector('.custom-selector-wrapper');
                    var model = sel ? (sel.innerText || '').trim().split('\\n')[0] : '';
                    var cost = '';
                    for (var btn of panel.querySelectorAll('button')) {
                        if ((btn.innerText || '').includes('Generate')) cost = (btn.innerText || '').trim();
                    }
                    return {model: model, cost: cost};
                }""")
                print(f"  Final: {json.dumps(final)}")
                if 'Wan' in final.get('model', '') or '6' in final.get('cost', ''):
                    print("\n  >>> WAN 2.1 SELECTED! MISSION ACCOMPLISHED! <<<")
            else:
                print("  Wan 2.1 not visible after scroll")
                screenshot(page, "p291_scroll_no_wan")
        else:
            # Maybe the popup IS the panel that changed (inline selector, not overlay)
            # Check if the AI Video panel text changed
            new_panel = page.evaluate("""() => {
                var panel = document.querySelector('.c-gen-config.show');
                if (!panel) return '';
                return (panel.innerText || '').substring(0, 300);
            }""")
            print(f"  Panel text (first 300 chars):")
            for line in new_panel.split('\n')[:15]:
                line = line.strip()
                if line:
                    print(f"    > {line[:60]}")

            # Maybe it opened a full-page selector
            full_page = page.evaluate("""() => {
                // Check for any new large panels/overlays
                var bodyChildren = document.body.children;
                var overlays = [];
                for (var el of bodyChildren) {
                    var rect = el.getBoundingClientRect();
                    var cs = window.getComputedStyle(el);
                    if (rect.height > 400 && rect.width > 500 && (cs.position === 'fixed' || cs.position === 'absolute' || cs.zIndex > 100)) {
                        overlays.push({
                            tag: el.tagName.toLowerCase(),
                            cls: (typeof el.className === 'string') ? el.className.substring(0, 60) : '',
                            w: Math.round(rect.width),
                            h: Math.round(rect.height),
                            zIndex: cs.zIndex,
                            position: cs.position,
                            hasModels: (el.innerText || '').includes('Wan 2.1')
                        });
                    }
                }
                return overlays;
            }""")
            print(f"\n  Full-page overlays: {json.dumps(full_page)}")

    else:
        print("  No model row found in clickables! The model selector might use a different pattern.")
        # Last resort: check what's at the coordinates from screenshot
        # "Minimax Hailuo 2.3" was at approximately y=229
        print("\n  Trying direct coordinate clicks from screenshot analysis...")
        for y_offset in [229, 230, 235]:
            for x_offset in [100, 110, 120, 145]:
                page.mouse.click(x_offset, y_offset)
                page.wait_for_timeout(1000)
                quick_check = page.evaluate("""() => {
                    for (var el of document.querySelectorAll('*')) {
                        var text = (el.innerText || '');
                        if (text.includes('Wan 2.1') && text.includes('Seedance')) {
                            var rect = el.getBoundingClientRect();
                            if (rect.height > 300) return {found: true};
                        }
                    }
                    return {found: false};
                }""")
                if quick_check.get('found'):
                    print(f"  >>> POPUP OPENED at click ({x_offset}, {y_offset})!")
                    screenshot(page, f"p291_found_at_{x_offset}_{y_offset}")
                    break
                page.keyboard.press('Escape')
                page.wait_for_timeout(200)

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

    screenshot(page, "p291_final")

    print("\n" + "=" * 70)
    print("EXPLORATION PART 29 COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
