#!/usr/bin/env python3
"""Dzine Deep Exploration Part 35 — AI Video Panel Deep Dive + Post-Gen Chain.

From P34 screenshots: AI Video panel has rich settings we haven't mapped yet:
- Key Frame: Start and Last vs AnyFrame tabs
- Reference tab
- Camera controls (expandable)
- Resolution/Duration options
- End Frame slot
- Post-generation chain: Lip Sync, Sound Effects, Video Enhance, Video Editor, Motion Control

This part maps all these settings and tests the post-generation chain.
"""

import json
import sys
sys.path.insert(0, "/Users/ray/Documents/openclaw")
from tools.lib.brave_profile import connect_or_launch


def screenshot(page, name):
    path = f"/Users/ray/Downloads/{name}.png"
    page.screenshot(path=path)
    print(f"  [SS] {path}")


def close_everything(page):
    page.evaluate("""() => {
        var pp = document.querySelector('.pick-panel');
        if (pp) { var c = pp.querySelector('.ico-close, [class*="close"]'); if (c) c.click(); }
        var pid = document.querySelector('.pick-image-dialog');
        if (pid) { var c = pid.querySelector('.ico-close'); if (c) c.click(); }
        var panel = document.querySelector('.c-gen-config.show');
        if (panel) { var close = panel.querySelector('.ico-close, button.close'); if (close) close.click(); }
        for (var el of document.querySelectorAll('.ico-close')) {
            if (el.offsetHeight > 0) try { el.click(); } catch(e) {}
        }
    }""")
    page.wait_for_timeout(300)
    page.keyboard.press('Escape')
    page.wait_for_timeout(300)


def main():
    print("=" * 70)
    print("DZINE DEEP EXPLORATION PART 35")
    print("AI Video Panel Deep Dive + Post-Generation Chain")
    print("=" * 70)

    browser, context, _, _pw = connect_or_launch()
    page = context.pages[0]
    print(f"Connected. URL: {page.url}")

    if "dzine.ai/canvas" not in page.url:
        page.goto("https://www.dzine.ai/canvas?id=19861203")
        page.wait_for_timeout(6000)

    close_everything(page)
    page.wait_for_timeout(500)

    # ================================================================
    # Step 1: Open AI Video panel via results chain (click [1])
    # ================================================================
    print("\n" + "=" * 70)
    print("Step 1: Open AI Video panel via results [1] button")
    print("=" * 70)

    # First check if AI Video panel is already open
    panel_open = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return false;
        var text = (panel.innerText || '').substring(0, 30);
        return text.includes('AI Video');
    }""")

    if not panel_open:
        # Click AI Video [1] in results
        target = page.evaluate("""() => {
            var rp = document.querySelector('.result-panel, [class*="result-panel"]') || document;
            for (var el of rp.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                if (text === 'AI Video' && el.offsetHeight > 0 && el.offsetHeight < 25) {
                    var parent = el.parentElement;
                    if (parent) {
                        for (var sib of parent.querySelectorAll('button')) {
                            var st = (sib.innerText || '').trim();
                            if (st === '1' && sib.offsetHeight > 0) {
                                var r = sib.getBoundingClientRect();
                                return {x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)};
                            }
                        }
                    }
                }
            }
            return null;
        }""")
        if target:
            page.mouse.click(target['x'], target['y'])
            page.wait_for_timeout(3000)
            print(f"  Clicked AI Video [1] at ({target['x']}, {target['y']})")
        else:
            # Fallback: click sidebar AI Video
            page.mouse.click(40, 361)
            page.wait_for_timeout(2000)
            print("  Clicked sidebar AI Video button")
    else:
        print("  AI Video panel already open")

    screenshot(page, "p351_panel_open")

    # ================================================================
    # Step 2: Map the full AI Video panel structure
    # ================================================================
    print("\n" + "=" * 70)
    print("Step 2: Map AI Video panel structure")
    print("=" * 70)

    panel_map = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return {error: 'no panel'};

        var result = {tabs: [], sections: [], buttons: [], inputs: [], selectors: []};

        // Map all tab-like elements
        for (var el of panel.querySelectorAll('[class*="tab"], [role="tab"], .ant-tabs-tab')) {
            var t = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (t && r.height > 0 && r.height < 50) {
                var active = el.className.includes('active') || el.className.includes('selected') ||
                            el.getAttribute('aria-selected') === 'true';
                result.tabs.push({
                    text: t, x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2),
                    w: Math.round(r.width), active: active,
                    cls: (typeof el.className === 'string') ? el.className.substring(0, 40) : ''
                });
            }
        }

        // Map all clickable sections/labels
        for (var el of panel.querySelectorAll('div, span, label')) {
            var t = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (r.height > 15 && r.height < 40 && r.width > 30 && r.width < 300 &&
                (t === 'Key Frame' || t === 'Reference' || t === 'Start and Last' || t === 'AnyFrame' ||
                 t === 'Camera' || t === 'End Frame' || t === 'Start Frame' ||
                 t.includes('Auto') || t.includes('720p') || t.includes('1080p') ||
                 t === 'Motion' || t === 'Seed')) {
                result.sections.push({
                    text: t, x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2),
                    w: Math.round(r.width), h: Math.round(r.height)
                });
            }
        }

        // Map all buttons
        for (var btn of panel.querySelectorAll('button')) {
            var t = (btn.innerText || '').trim();
            var r = btn.getBoundingClientRect();
            if (r.height > 0 && t) {
                result.buttons.push({
                    text: t.substring(0, 30), x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2),
                    w: Math.round(r.width), disabled: btn.disabled
                });
            }
        }

        // Map textareas (prompt field)
        for (var ta of panel.querySelectorAll('textarea')) {
            var r = ta.getBoundingClientRect();
            result.inputs.push({
                type: 'textarea', value: ta.value.substring(0, 80),
                maxLength: ta.maxLength > 0 ? ta.maxLength : null,
                placeholder: (ta.placeholder || '').substring(0, 40),
                x: Math.round(r.x), y: Math.round(r.y),
                w: Math.round(r.width), h: Math.round(r.height)
            });
        }

        // Map custom selectors (model, resolution, etc.)
        for (var sel of panel.querySelectorAll('.custom-selector-wrapper, [class*="selector"]')) {
            var t = (sel.innerText || '').trim().split('\\n')[0];
            var r = sel.getBoundingClientRect();
            if (r.height > 0 && t) {
                result.selectors.push({
                    text: t.substring(0, 30), x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2),
                    w: Math.round(r.width), h: Math.round(r.height)
                });
            }
        }

        // Map sliders
        result.sliders = [];
        for (var slider of panel.querySelectorAll('.ant-slider')) {
            var r = slider.getBoundingClientRect();
            var handle = slider.querySelector('.ant-slider-handle');
            var hr = handle ? handle.getBoundingClientRect() : null;
            var label = '';
            var prev = slider.previousElementSibling;
            if (prev) label = (prev.innerText || '').trim().substring(0, 20);
            result.sliders.push({
                label: label, x: Math.round(r.x), y: Math.round(r.y),
                w: Math.round(r.width), handleX: hr ? Math.round(hr.x + hr.width/2) : 0,
                handleY: hr ? Math.round(hr.y + hr.height/2) : 0
            });
        }

        return result;
    }""")

    print(f"\n  Tabs ({len(panel_map.get('tabs', []))}):")
    for t in panel_map.get('tabs', []):
        active = " [ACTIVE]" if t.get('active') else ""
        print(f"    '{t['text']}' at ({t['x']}, {t['y']}) w={t['w']}{active}")

    print(f"\n  Sections ({len(panel_map.get('sections', []))}):")
    for s in panel_map.get('sections', []):
        print(f"    '{s['text']}' at ({s['x']}, {s['y']}) {s['w']}x{s['h']}")

    print(f"\n  Buttons ({len(panel_map.get('buttons', []))}):")
    for b in panel_map.get('buttons', []):
        dis = " [DISABLED]" if b.get('disabled') else ""
        print(f"    '{b['text']}' at ({b['x']}, {b['y']}) w={b['w']}{dis}")

    print(f"\n  Inputs ({len(panel_map.get('inputs', []))}):")
    for i in panel_map.get('inputs', []):
        print(f"    {i['type']} at ({i['x']}, {i['y']}) {i['w']}x{i['h']} val='{i['value']}' max={i.get('maxLength')}")

    print(f"\n  Selectors ({len(panel_map.get('selectors', []))}):")
    for s in panel_map.get('selectors', []):
        print(f"    '{s['text']}' at ({s['x']}, {s['y']}) {s['w']}x{s['h']}")

    print(f"\n  Sliders ({len(panel_map.get('sliders', []))}):")
    for s in panel_map.get('sliders', []):
        print(f"    '{s['label']}' at ({s['x']}, {s['y']}) w={s['w']} handle=({s['handleX']}, {s['handleY']})")

    # ================================================================
    # Step 3: Expand Camera controls
    # ================================================================
    print("\n" + "=" * 70)
    print("Step 3: Expand Camera controls")
    print("=" * 70)

    camera_pos = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return null;
        for (var el of panel.querySelectorAll('*')) {
            var t = (el.innerText || '').trim();
            if (t === 'Camera' && el.offsetHeight > 0 && el.offsetHeight < 40 && el.offsetWidth > 30) {
                var r = el.getBoundingClientRect();
                return {x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)};
            }
        }
        return null;
    }""")

    if camera_pos:
        page.mouse.click(camera_pos['x'], camera_pos['y'])
        page.wait_for_timeout(1500)
        print(f"  Clicked Camera at ({camera_pos['x']}, {camera_pos['y']})")

        screenshot(page, "p352_camera_expanded")

        # Map camera options
        camera_opts = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return [];
            var opts = [];
            // Look for camera-related options after the Camera label
            var foundCamera = false;
            for (var el of panel.querySelectorAll('*')) {
                var t = (el.innerText || '').trim();
                if (t === 'Camera') { foundCamera = true; continue; }
                if (!foundCamera) continue;
                if (t === 'Generate') break;  // Stop at Generate button

                var r = el.getBoundingClientRect();
                if (r.height > 0 && r.height < 45 && r.width > 20 && r.width < 250 && t.length > 1 && t.length < 30) {
                    // Avoid duplicates
                    var isDup = opts.some(o => o.text === t);
                    if (!isDup) {
                        var selected = el.className && (el.className.includes('active') || el.className.includes('selected'));
                        opts.push({
                            text: t, x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2),
                            w: Math.round(r.width), h: Math.round(r.height),
                            selected: selected || false,
                            tag: el.tagName.toLowerCase()
                        });
                    }
                }
            }
            return opts;
        }""")

        print(f"\n  Camera options ({len(camera_opts)}):")
        for o in camera_opts:
            sel = " [SEL]" if o.get('selected') else ""
            print(f"    '{o['text']}' at ({o['x']}, {o['y']}) {o['w']}x{o['h']} {o['tag']}{sel}")
    else:
        print("  Camera section not found")

    # ================================================================
    # Step 4: Check Resolution/Duration selector options
    # ================================================================
    print("\n" + "=" * 70)
    print("Step 4: Resolution/Duration selector")
    print("=" * 70)

    res_sel = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return null;
        for (var el of panel.querySelectorAll('*')) {
            var t = (el.innerText || '').trim();
            if ((t.includes('Auto') && t.includes('720p')) || (t.includes('720p') && t.includes('5s'))) {
                var r = el.getBoundingClientRect();
                if (r.height > 20 && r.height < 50) {
                    return {text: t, x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)};
                }
            }
        }
        return null;
    }""")

    if res_sel:
        print(f"  Current: '{res_sel['text']}' at ({res_sel['x']}, {res_sel['y']})")
        page.mouse.click(res_sel['x'], res_sel['y'])
        page.wait_for_timeout(2000)

        screenshot(page, "p353_resolution_options")

        # Map resolution dropdown options
        res_opts = page.evaluate("""() => {
            var opts = [];
            // Look for popup/dropdown with resolution options
            for (var el of document.querySelectorAll('.ant-select-dropdown, .ant-popover, [class*="popup"], [class*="dropdown"], [class*="menu"]')) {
                if (el.offsetHeight > 0) {
                    for (var opt of el.querySelectorAll('*')) {
                        var t = (opt.innerText || '').trim();
                        var r = opt.getBoundingClientRect();
                        if (r.height > 15 && r.height < 50 && t.length > 1 && t.length < 40 &&
                            (t.includes('720') || t.includes('1080') || t.includes('Auto') ||
                             t.includes('4K') || t.includes('480') || t.match(/\\d+s/) ||
                             t.includes('Standard') || t.includes('HD'))) {
                            var isDup = opts.some(o => o.text === t);
                            if (!isDup) opts.push({
                                text: t, x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)
                            });
                        }
                    }
                }
            }
            // Also check for newly appeared overlay items
            if (opts.length === 0) {
                for (var el of document.querySelectorAll('*')) {
                    var t = (el.innerText || '').trim();
                    var r = el.getBoundingClientRect();
                    if (r.height > 20 && r.height < 45 && r.width > 40 && r.width < 200 &&
                        (t.includes('720p') || t.includes('1080p')) &&
                        !t.includes('Auto') && el.offsetParent !== null) {
                        var isDup = opts.some(o => o.text === t);
                        if (!isDup) opts.push({
                            text: t, x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)
                        });
                    }
                }
            }
            return opts;
        }""")

        print(f"\n  Resolution options ({len(res_opts)}):")
        for o in res_opts:
            print(f"    '{o['text']}' at ({o['x']}, {o['y']})")

        # Close any popup
        page.keyboard.press('Escape')
        page.wait_for_timeout(500)
    else:
        print("  Resolution selector not found")

    # ================================================================
    # Step 5: Explore AnyFrame tab
    # ================================================================
    print("\n" + "=" * 70)
    print("Step 5: Explore AnyFrame tab")
    print("=" * 70)

    anyframe_pos = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return null;
        for (var el of panel.querySelectorAll('*')) {
            var t = (el.innerText || '').trim();
            if (t === 'AnyFrame' && el.offsetHeight > 0 && el.offsetHeight < 40) {
                var r = el.getBoundingClientRect();
                return {x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)};
            }
        }
        return null;
    }""")

    if anyframe_pos:
        page.mouse.click(anyframe_pos['x'], anyframe_pos['y'])
        page.wait_for_timeout(2000)
        print(f"  Clicked AnyFrame at ({anyframe_pos['x']}, {anyframe_pos['y']})")

        screenshot(page, "p354_anyframe_tab")

        anyframe_content = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return {error: 'no panel'};
            var items = [];
            // Map what's visible in the AnyFrame section
            var foundAny = false;
            for (var el of panel.querySelectorAll('*')) {
                var t = (el.innerText || '').trim();
                if (t === 'AnyFrame') { foundAny = true; continue; }
                if (!foundAny) continue;
                if (t === 'Generate' || t.startsWith('Wan')) break;

                var r = el.getBoundingClientRect();
                if (r.height > 10 && r.height < 60 && r.width > 20 && t.length > 0 && t.length < 60) {
                    var isDup = items.some(i => i.text === t);
                    if (!isDup) {
                        items.push({
                            text: t, x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2),
                            w: Math.round(r.width), h: Math.round(r.height)
                        });
                    }
                }
            }
            return items;
        }""")

        print(f"\n  AnyFrame content ({len(anyframe_content) if isinstance(anyframe_content, list) else 'error'}):")
        if isinstance(anyframe_content, list):
            for item in anyframe_content:
                print(f"    '{item['text']}' at ({item['x']}, {item['y']}) {item['w']}x{item['h']}")
    else:
        print("  AnyFrame tab not found")

    # Switch back to Start and Last
    sal_pos = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return null;
        for (var el of panel.querySelectorAll('*')) {
            var t = (el.innerText || '').trim();
            if (t === 'Start and Last' && el.offsetHeight > 0) {
                var r = el.getBoundingClientRect();
                return {x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)};
            }
        }
        return null;
    }""")
    if sal_pos:
        page.mouse.click(sal_pos['x'], sal_pos['y'])
        page.wait_for_timeout(1000)

    # ================================================================
    # Step 6: Explore Reference tab
    # ================================================================
    print("\n" + "=" * 70)
    print("Step 6: Explore Reference tab")
    print("=" * 70)

    ref_pos = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return null;
        for (var el of panel.querySelectorAll('*')) {
            var t = (el.innerText || '').trim();
            if (t === 'Reference' && el.offsetHeight > 0 && el.offsetHeight < 40) {
                var r = el.getBoundingClientRect();
                return {x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)};
            }
        }
        return null;
    }""")

    if ref_pos:
        page.mouse.click(ref_pos['x'], ref_pos['y'])
        page.wait_for_timeout(2000)
        print(f"  Clicked Reference at ({ref_pos['x']}, {ref_pos['y']})")

        screenshot(page, "p355_reference_tab")

        ref_content = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return {error: 'no panel'};
            var items = [];
            for (var el of panel.querySelectorAll('*')) {
                var t = (el.innerText || '').trim();
                var r = el.getBoundingClientRect();
                if (r.height > 10 && r.height < 80 && r.width > 20 && r.width < 300 &&
                    t.length > 0 && t.length < 80 && el.offsetParent !== null) {
                    var isDup = items.some(i => i.text === t);
                    if (!isDup && r.y > 50 && r.y < 400) {
                        items.push({
                            text: t.substring(0, 60), x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2),
                            w: Math.round(r.width), h: Math.round(r.height)
                        });
                    }
                }
            }
            return items;
        }""")

        print(f"\n  Reference content ({len(ref_content) if isinstance(ref_content, list) else 'error'}):")
        if isinstance(ref_content, list):
            for item in ref_content[:15]:
                print(f"    '{item['text']}' at ({item['x']}, {item['y']}) {item['w']}x{item['h']}")
    else:
        print("  Reference tab not found")

    # Switch back to Key Frame
    kf_pos = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return null;
        for (var el of panel.querySelectorAll('*')) {
            var t = (el.innerText || '').trim();
            if (t === 'Key Frame' && el.offsetHeight > 0 && el.offsetHeight < 40) {
                var r = el.getBoundingClientRect();
                return {x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)};
            }
        }
        return null;
    }""")
    if kf_pos:
        page.mouse.click(kf_pos['x'], kf_pos['y'])
        page.wait_for_timeout(1000)

    # ================================================================
    # Step 7: Map post-generation chain actions on the video result
    # ================================================================
    print("\n" + "=" * 70)
    print("Step 7: Map post-generation chain actions")
    print("=" * 70)

    # Close the panel first to see results
    close_everything(page)
    page.wait_for_timeout(500)

    chain_actions = page.evaluate("""() => {
        var actions = [];
        var rp = document.querySelector('.result-panel, [class*="result-panel"]') || document;

        // Find Image-to-Video section and its action buttons
        var foundI2V = false;
        for (var el of rp.querySelectorAll('*')) {
            var t = (el.innerText || '').trim();
            if (t.includes('Image-to-Video')) { foundI2V = true; continue; }
            if (!foundI2V) continue;
            // Stop at next section header
            if (t.includes('Image-to-Image') && foundI2V) break;

            var r = el.getBoundingClientRect();
            if (r.height > 15 && r.height < 40 && r.width > 60 && r.width < 250 &&
                (t.includes('Lip Sync') || t.includes('Enhance') || t.includes('Upscale') ||
                 t.includes('Sound') || t.includes('Video Editor') || t.includes('Motion') ||
                 t.includes('Download'))) {
                var isDup = actions.some(a => a.text === t);
                if (!isDup) {
                    actions.push({
                        text: t, x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2),
                        w: Math.round(r.width), h: Math.round(r.height),
                        tag: el.tagName.toLowerCase()
                    });
                }
            }
        }
        return actions;
    }""")

    print(f"\n  Post-generation chain actions ({len(chain_actions)}):")
    for a in chain_actions:
        print(f"    '{a['text']}' at ({a['x']}, {a['y']}) {a['w']}x{a['h']} [{a['tag']}]")

    # ================================================================
    # Step 8: Click Lip Sync to see what it needs
    # ================================================================
    print("\n" + "=" * 70)
    print("Step 8: Explore Lip Sync chain action")
    print("=" * 70)

    lip_sync = None
    for a in chain_actions:
        if 'Lip Sync' in a['text']:
            lip_sync = a
            break

    if lip_sync:
        page.mouse.click(lip_sync['x'], lip_sync['y'])
        page.wait_for_timeout(3000)
        print(f"  Clicked Lip Sync at ({lip_sync['x']}, {lip_sync['y']})")

        screenshot(page, "p356_lip_sync_chain")

        # Map Lip Sync panel
        ls_panel = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return {noPanel: true};

            var text = (panel.innerText || '').substring(0, 300);
            var items = [];

            for (var el of panel.querySelectorAll('*')) {
                var t = (el.innerText || '').trim();
                var r = el.getBoundingClientRect();
                if (r.height > 10 && r.height < 60 && r.width > 20 && r.width < 300 &&
                    t.length > 0 && t.length < 60 && el.offsetParent !== null) {
                    var isDup = items.some(i => i.text === t);
                    if (!isDup && r.y > 30) {
                        items.push({
                            text: t, x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2),
                            w: Math.round(r.width), h: Math.round(r.height)
                        });
                    }
                }
            }

            // Find specific elements: upload areas, model selector, generate button
            var genBtn = null;
            for (var btn of panel.querySelectorAll('button')) {
                if ((btn.innerText || '').includes('Generate')) {
                    genBtn = {text: (btn.innerText || '').trim(), disabled: btn.disabled};
                }
            }

            return {panelText: text.substring(0, 200), items: items.slice(0, 20), genBtn: genBtn};
        }""")

        print(f"\n  Panel text: {ls_panel.get('panelText', 'N/A')}")
        print(f"  Generate btn: {ls_panel.get('genBtn')}")
        if ls_panel.get('items'):
            print(f"\n  Lip Sync panel items ({len(ls_panel['items'])}):")
            for item in ls_panel['items']:
                print(f"    '{item['text']}' at ({item['x']}, {item['y']}) {item['w']}x{item['h']}")

        close_everything(page)
        page.wait_for_timeout(500)
    else:
        print("  No Lip Sync chain action found")

    # ================================================================
    # Step 9: Click Sound Effects to see what it offers
    # ================================================================
    print("\n" + "=" * 70)
    print("Step 9: Explore Sound Effects chain action")
    print("=" * 70)

    sound_fx = None
    for a in chain_actions:
        if 'Sound' in a['text']:
            sound_fx = a
            break

    if sound_fx:
        page.mouse.click(sound_fx['x'], sound_fx['y'])
        page.wait_for_timeout(3000)
        print(f"  Clicked Sound Effects at ({sound_fx['x']}, {sound_fx['y']})")

        screenshot(page, "p357_sound_effects")

        sfx_panel = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return {noPanel: true};

            var text = (panel.innerText || '').substring(0, 300);
            var genBtn = null;
            for (var btn of panel.querySelectorAll('button')) {
                if ((btn.innerText || '').includes('Generate')) {
                    genBtn = {text: (btn.innerText || '').trim(), disabled: btn.disabled};
                }
            }

            return {panelText: text.substring(0, 200), genBtn: genBtn};
        }""")

        print(f"  Panel: {sfx_panel.get('panelText', 'N/A')}")
        print(f"  Generate: {sfx_panel.get('genBtn')}")

        close_everything(page)
        page.wait_for_timeout(500)
    else:
        print("  No Sound Effects chain action found")

    # ================================================================
    # Step 10: Explore Instant Storyboard (last sidebar tool)
    # ================================================================
    print("\n" + "=" * 70)
    print("Step 10: Explore Instant Storyboard tool")
    print("=" * 70)

    close_everything(page)
    page.wait_for_timeout(500)

    # Click Storyboard in sidebar (y=778 from UI map, but might have shifted with scrolling)
    # First check if it's visible
    storyboard_pos = page.evaluate("""() => {
        // Look for the storyboard icon/button in the left sidebar
        var sidebar = document.querySelector('.left-side-bar, [class*="sidebar"], [class*="tool-bar"]');
        var search = sidebar || document;
        for (var el of search.querySelectorAll('*')) {
            var t = (el.innerText || '').trim();
            if ((t === 'Instant' || t === 'Storyboard' || t.includes('Storyboard')) &&
                el.offsetHeight > 0 && el.offsetHeight < 50 && el.offsetWidth < 80) {
                var r = el.getBoundingClientRect();
                if (r.x < 60) {  // Must be in left sidebar
                    return {text: t, x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)};
                }
            }
        }
        return null;
    }""")

    if storyboard_pos:
        page.mouse.click(storyboard_pos['x'], storyboard_pos['y'])
        page.wait_for_timeout(3000)
        print(f"  Clicked Storyboard at ({storyboard_pos['x']}, {storyboard_pos['y']})")
    else:
        # Try scrolling sidebar or clicking at known y=778
        print("  Storyboard not found in sidebar, trying y=385 (scrolled area)")
        # The sidebar might need scrolling. Let's try the direct coordinate
        page.mouse.click(40, 385)
        page.wait_for_timeout(3000)

    screenshot(page, "p358_storyboard")

    sb_panel = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return {noPanel: true};
        var text = (panel.innerText || '').substring(0, 500);
        var genBtn = null;
        for (var btn of panel.querySelectorAll('button')) {
            if ((btn.innerText || '').includes('Generate') || (btn.innerText || '').includes('Create')) {
                genBtn = {text: (btn.innerText || '').trim(), disabled: btn.disabled};
            }
        }
        return {panelText: text.substring(0, 300), genBtn: genBtn};
    }""")

    print(f"  Panel: {json.dumps(sb_panel)}")

    # ================================================================
    # Credits
    # ================================================================
    print("\n" + "=" * 70)
    print("Final Credits")
    print("=" * 70)
    credits = page.evaluate("""() => {
        for (var el of document.querySelectorAll('*')) {
            var t = (el.innerText || '').trim();
            if (t.match(/^Unlimited\\s*\\/\\s*[\\d.,]+$/) || t.match(/Unlimited.*\\d/)) return t;
        }
        return 'unknown';
    }""")
    print(f"  Credits: {credits}")

    print("\n" + "=" * 70)
    print("EXPLORATION PART 35 COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
