#!/usr/bin/env python3
"""Dzine Deep Exploration Part 30 — Wan 2.1 Test + Video Editor + Deep Automation Knowledge.

Part 29 CONFIRMED: Wan 2.1 selectable via mouse.click() on the model row.
Complete model list captured from popup screenshot.

Part 30 goals:
1. Generate a test video with Wan 2.1 (6 credits) — use canvas image as start frame
2. Download and verify the video result
3. Explore Video Editor tool (sidebar y=490) — full panel mapping
4. Map the Enhance & Upscale sidebar panel properly (sidebar y=630)
5. Document complete automation recipe for the pipeline
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
        if (text.startsWith('Image-to-Image')) return 'img2img';
        if (text.startsWith('Character')) return 'character';
        if (text.startsWith('Instant Storyboard')) return 'storyboard';
        if (text.startsWith('Lip Sync')) return 'lip_sync';
        if (text.startsWith('Video Editor')) return 'video_editor';
        if (text.startsWith('Image Editor')) return 'image_editor';
        if (text.startsWith('Local Edit')) return 'local_edit';
        return 'unknown:' + text.substring(0, 50);
    }""")


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


def open_panel(page, tool_name, sidebar_y, timeout=2500):
    close_all(page)
    page.wait_for_timeout(300)
    page.mouse.click(40, sidebar_y)
    page.wait_for_timeout(timeout)
    panel = get_active_panel(page)
    print(f"  Opened '{tool_name}': panel={panel}")
    return panel


def main():
    print("=" * 70)
    print("DZINE DEEP EXPLORATION PART 30")
    print("Wan 2.1 Test + Video Editor + Automation Knowledge")
    print("=" * 70)

    browser, context, _, _pw = connect_or_launch()
    page = context.pages[0]
    print(f"Connected. URL: {page.url}")

    if "dzine.ai/canvas" not in page.url:
        page.goto("https://www.dzine.ai/canvas?id=19861203")
        page.wait_for_timeout(6000)

    credits_before = page.evaluate("""() => {
        for (var el of document.querySelectorAll('*')) {
            var t = (el.innerText || '').trim();
            if (t.match(/^Unlimited\\s*\\/\\s*[\\d.,]+$/)) return t;
        }
        return 'unknown';
    }""")
    print(f"  Credits before: {credits_before}")

    # ================================================================
    # TASK 1: Wan 2.1 Video Generation
    # ================================================================
    print("\n" + "=" * 70)
    print("TASK 1: Generate Video with Wan 2.1")
    print("=" * 70)

    # Open AI Video
    panel = open_panel(page, "AI Video", 361)
    if panel != 'ai_video':
        print(f"  FAILED to open AI Video (got: {panel})")
    else:
        # Check current model
        current_model = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return '';
            var sel = panel.querySelector('.custom-selector-wrapper');
            return sel ? (sel.innerText || '').trim().split('\\n')[0] : '';
        }""")
        print(f"  Current model: {current_model}")

        # If not Wan 2.1, select it
        if 'Wan' not in current_model:
            print("  Switching to Wan 2.1...")
            # Click the model row (from P29: wrapper center is at cy=458)
            sel_pos = page.evaluate("""() => {
                var panel = document.querySelector('.c-gen-config.show');
                if (!panel) return null;
                var sel = panel.querySelector('.custom-selector-wrapper');
                if (!sel) return null;
                var rect = sel.getBoundingClientRect();
                return {cx: Math.round(rect.x + rect.width/2), cy: Math.round(rect.y + rect.height/2)};
            }""")
            if sel_pos:
                page.mouse.click(sel_pos['cx'], sel_pos['cy'])
                page.wait_for_timeout(2000)

                # Scroll popup to bottom
                page.evaluate("""() => {
                    for (var el of document.querySelectorAll('.panel-body')) {
                        if (el.scrollHeight > el.clientHeight + 30) {
                            el.scrollTop = el.scrollHeight;
                        }
                    }
                }""")
                page.wait_for_timeout(800)

                # Find and click Wan 2.1
                wan = page.evaluate("""() => {
                    for (var el of document.querySelectorAll('*')) {
                        var text = (el.innerText || '').trim();
                        if (text.startsWith('Wan 2.1') && el.offsetHeight > 20 && el.offsetHeight < 120 && el.offsetWidth > 40) {
                            var rect = el.getBoundingClientRect();
                            if (rect.y > 0 && rect.y < window.innerHeight) {
                                return {x: Math.round(rect.x + rect.width/2), y: Math.round(rect.y + rect.height/2)};
                            }
                        }
                    }
                    return null;
                }""")
                if wan:
                    page.mouse.click(wan['x'], wan['y'])
                    page.wait_for_timeout(2000)
                    print(f"  Switched to Wan 2.1")

        # Check if there's a canvas image to use as start frame
        # The panel says "Please upload the key frame image"
        # We need to click "Start Frame" to use the canvas image
        start_frame_info = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return {};
            // Find Start Frame button area
            var pickBtns = panel.querySelectorAll('.pick-image, button.pick-image');
            var hasStartFrame = false;
            var startFrameBtn = null;
            for (var btn of pickBtns) {
                var text = (btn.innerText || '').trim();
                if (text.includes('Start Frame') || text.includes('Start')) {
                    var rect = btn.getBoundingClientRect();
                    startFrameBtn = {x: Math.round(rect.x + rect.width/2), y: Math.round(rect.y + rect.height/2), text: text};
                    break;
                }
            }
            // Check if a start frame is already set (has thumbnail)
            var thumb = panel.querySelector('.pick-image img, .pick-image .thumb, .frame-thumb img');
            var hasThumb = !!thumb;

            // Check prompt field
            var textarea = panel.querySelector('textarea');
            var prompt = textarea ? textarea.value : '';

            return {startFrameBtn: startFrameBtn, hasThumb: hasThumb, prompt: prompt};
        }""")
        print(f"  Start frame: {json.dumps(start_frame_info)}")

        # Click the Start Frame button to open the picker
        if start_frame_info.get('startFrameBtn'):
            sfb = start_frame_info['startFrameBtn']
            print(f"  Clicking Start Frame at ({sfb['x']}, {sfb['y']})...")
            page.mouse.click(sfb['x'], sfb['y'])
            page.wait_for_timeout(2000)

            # Check for the Pick Image dialog
            dialog = page.evaluate("""() => {
                var pid = document.querySelector('.pick-image-dialog');
                if (!pid || pid.offsetHeight === 0) return {found: false};
                var text = (pid.innerText || '').substring(0, 300);
                var tabs = [];
                for (var el of pid.querySelectorAll('[class*="tab"], button')) {
                    var t = (el.innerText || '').trim();
                    if (t && t.length < 30) tabs.push(t);
                }
                return {found: true, text: text, tabs: tabs.slice(0, 15)};
            }""")
            print(f"  Pick Image dialog: {json.dumps({k:v for k,v in dialog.items() if k != 'text'})}")
            if dialog.get('found'):
                # Look for "Canvas" option to use current canvas content
                print(f"  Dialog tabs: {dialog.get('tabs', [])[:10]}")

                # Check for canvas image option or recent results
                canvas_option = page.evaluate("""() => {
                    var pid = document.querySelector('.pick-image-dialog');
                    if (!pid) return null;
                    // Look for "Canvas" or "Current Canvas" or recent result images
                    for (var el of pid.querySelectorAll('button, [class*="tab"], [class*="option"]')) {
                        var text = (el.innerText || '').trim();
                        if (text.toLowerCase().includes('canvas') || text.toLowerCase().includes('result')) {
                            var rect = el.getBoundingClientRect();
                            if (rect.height > 0) {
                                return {text: text, x: Math.round(rect.x + rect.width/2), y: Math.round(rect.y + rect.height/2)};
                            }
                        }
                    }
                    // Check for image thumbnails we can click
                    var imgs = pid.querySelectorAll('img');
                    if (imgs.length > 0) {
                        var firstImg = imgs[0];
                        var rect = firstImg.getBoundingClientRect();
                        return {text: '[first image]', x: Math.round(rect.x + rect.width/2), y: Math.round(rect.y + rect.height/2), imgCount: imgs.length};
                    }
                    return null;
                }""")
                print(f"  Canvas/result option: {json.dumps(canvas_option)}")

                screenshot(page, "p301_pick_image_dialog")

                if canvas_option:
                    print(f"  Clicking '{canvas_option.get('text')}' at ({canvas_option['x']}, {canvas_option['y']})...")
                    page.mouse.click(canvas_option['x'], canvas_option['y'])
                    page.wait_for_timeout(2000)

                    # Check if dialog closed and start frame set
                    frame_set = page.evaluate("""() => {
                        var pid = document.querySelector('.pick-image-dialog');
                        var dialogOpen = pid && pid.offsetHeight > 0;
                        var panel = document.querySelector('.c-gen-config.show');
                        if (!panel) return {dialogOpen: dialogOpen};
                        var thumb = panel.querySelector('.pick-image img, .frame-thumb img');
                        return {dialogOpen: dialogOpen, hasThumb: !!thumb};
                    }""")
                    print(f"  Frame set: {json.dumps(frame_set)}")

                    # If dialog still open, look for a different approach
                    if frame_set.get('dialogOpen'):
                        # Try clicking an image thumbnail
                        page.evaluate("""() => {
                            var pid = document.querySelector('.pick-image-dialog');
                            if (!pid) return;
                            var imgs = pid.querySelectorAll('img');
                            if (imgs.length > 0) imgs[0].click();
                        }""")
                        page.wait_for_timeout(1500)

                        # Check for confirm/select button
                        page.evaluate("""() => {
                            var pid = document.querySelector('.pick-image-dialog');
                            if (!pid) return;
                            for (var btn of pid.querySelectorAll('button')) {
                                var text = (btn.innerText || '').trim().toLowerCase();
                                if (text.includes('confirm') || text.includes('select') || text.includes('use') || text === 'ok') {
                                    btn.click();
                                    return;
                                }
                            }
                        }""")
                        page.wait_for_timeout(1500)
                else:
                    # Close dialog, try a different approach
                    page.keyboard.press('Escape')
                    page.wait_for_timeout(500)

        # Check generate button state
        gen_state = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return {};
            var genBtn = null;
            for (var btn of panel.querySelectorAll('button')) {
                var t = (btn.innerText || '').trim();
                if (t.includes('Generate')) {
                    genBtn = {
                        text: t,
                        disabled: btn.disabled || btn.classList.contains('disabled'),
                        cls: (typeof btn.className === 'string') ? btn.className.substring(0, 40) : ''
                    };
                }
            }
            // Check for warning
            var warning = '';
            for (var el of panel.querySelectorAll('*')) {
                var t = (el.innerText || '').trim();
                if (t.includes('upload') || t.includes('key frame') || t.includes('Please')) {
                    if (el.offsetHeight > 0 && el.offsetHeight < 30) {
                        warning = t;
                        break;
                    }
                }
            }
            return {genBtn: genBtn, warning: warning};
        }""")
        print(f"  Generate state: {json.dumps(gen_state)}")

        # If generate is available (start frame was set), generate video
        if gen_state.get('genBtn') and not gen_state['genBtn'].get('disabled') and not gen_state.get('warning'):
            print("\n  Start frame is set! Generating Wan 2.1 video...")
            gen_btn_pos = page.evaluate("""() => {
                var panel = document.querySelector('.c-gen-config.show');
                if (!panel) return null;
                for (var btn of panel.querySelectorAll('button')) {
                    if ((btn.innerText || '').includes('Generate')) {
                        var rect = btn.getBoundingClientRect();
                        return {x: Math.round(rect.x + rect.width/2), y: Math.round(rect.y + rect.height/2)};
                    }
                }
                return null;
            }""")
            if gen_btn_pos:
                page.mouse.click(gen_btn_pos['x'], gen_btn_pos['y'])
                print(f"  Video generation started! Waiting for result...")
                page.wait_for_timeout(90000)  # Wait 90s for Wan 2.1

                # Check for result
                video_result = page.evaluate("""() => {
                    var results = document.querySelectorAll('[class*="result"] video, video');
                    if (results.length === 0) return {found: false};
                    var lastVideo = results[results.length - 1];
                    return {
                        found: true,
                        src: (lastVideo.src || '').substring(0, 100),
                        duration: lastVideo.duration
                    };
                }""")
                print(f"  Video result: {json.dumps(video_result)}")
        else:
            print("  Generate button not ready (need start frame). Skipping generation.")
            # Close dialog if still open
            page.keyboard.press('Escape')
            page.wait_for_timeout(500)

    # ================================================================
    # TASK 2: Video Editor Panel
    # ================================================================
    print("\n" + "=" * 70)
    print("TASK 2: Video Editor Panel (sidebar y=490)")
    print("=" * 70)

    panel = open_panel(page, "Video Editor", 490)

    if panel == 'video_editor' or 'Video Editor' in panel:
        ve_map = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return {};
            var text = (panel.innerText || '').substring(0, 1200);
            var buttons = [];
            for (var btn of panel.querySelectorAll('button')) {
                var t = (btn.innerText || '').trim();
                if (t && t.length < 50) {
                    var rect = btn.getBoundingClientRect();
                    var cls = (typeof btn.className === 'string') ? btn.className : '';
                    buttons.push({text: t, x: Math.round(rect.x + rect.width/2), y: Math.round(rect.y + rect.height/2), selected: cls.includes('selected'), cls: cls.substring(0, 30)});
                }
            }
            // Model selector
            var sel = panel.querySelector('.custom-selector-wrapper');
            var model = sel ? (sel.innerText || '').trim().split('\\n')[0] : '';
            // Prompt
            var textarea = panel.querySelector('textarea');
            var prompt = textarea ? {maxLength: textarea.maxLength, placeholder: (textarea.placeholder || '').substring(0, 50), value: (textarea.value || '').substring(0, 50)} : null;
            // Options
            var collapseOpts = [];
            for (var opt of panel.querySelectorAll('.collapse-option')) {
                var t = (opt.innerText || '').trim();
                var rect = opt.getBoundingClientRect();
                collapseOpts.push({text: t.substring(0, 60), y: Math.round(rect.y)});
            }
            return {text: text, buttons: buttons, model: model, prompt: prompt, collapseOpts: collapseOpts};
        }""")

        print(f"  Model: {ve_map.get('model')}")
        print(f"  Prompt: {json.dumps(ve_map.get('prompt'))}")
        print(f"  Collapse options ({len(ve_map.get('collapseOpts', []))}):")
        for o in ve_map.get('collapseOpts', []):
            print(f"    y={o['y']} '{o['text'][:50]}'")
        print(f"  Buttons ({len(ve_map.get('buttons', []))}):")
        for b in ve_map.get('buttons', []):
            sel = " [SELECTED]" if b.get('selected') else ""
            print(f"    ({b['x']}, {b['y']}) '{b['text']}'{sel}")
        print(f"\n  Full text:")
        for line in ve_map.get('text', '').split('\n')[:20]:
            line = line.strip()
            if line:
                print(f"    > {line[:60]}")

        screenshot(page, "p301_video_editor")
    else:
        print(f"  FAILED to open Video Editor (got: {panel})")

    # ================================================================
    # TASK 3: Enhance & Upscale Sidebar Panel (deeper mapping)
    # ================================================================
    print("\n" + "=" * 70)
    print("TASK 3: Enhance & Upscale Sidebar Panel (y=630)")
    print("=" * 70)

    panel = open_panel(page, "Enhance & Upscale", 630)

    if panel == 'enhance' or 'Enhance' in panel:
        eu_map = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return {};
            var text = (panel.innerText || '').substring(0, 1000);
            var buttons = [];
            for (var btn of panel.querySelectorAll('button, [role="button"]')) {
                var t = (btn.innerText || '').trim();
                if (t && t.length < 50) {
                    var rect = btn.getBoundingClientRect();
                    var cls = (typeof btn.className === 'string') ? btn.className : '';
                    buttons.push({text: t, x: Math.round(rect.x + rect.width/2), y: Math.round(rect.y + rect.height/2), selected: cls.includes('selected') || cls.includes('active'), cls: cls.substring(0, 30)});
                }
            }
            // Check for upload area
            var hasUpload = !!panel.querySelector('[class*="upload"], input[type="file"], .pick-image');
            // Check mode selector (Precision/Creative)
            var modes = [];
            for (var el of panel.querySelectorAll('*')) {
                var t = (el.innerText || '').trim();
                if (['Precision', 'Creative'].includes(t)) {
                    var cls = (typeof el.className === 'string') ? el.className : '';
                    modes.push({name: t, selected: cls.includes('selected') || cls.includes('active')});
                }
            }
            return {text: text, buttons: buttons, hasUpload: hasUpload, modes: modes};
        }""")

        print(f"  Has upload: {eu_map.get('hasUpload')}")
        print(f"  Modes: {json.dumps(eu_map.get('modes'))}")
        print(f"  Buttons ({len(eu_map.get('buttons', []))}):")
        for b in eu_map.get('buttons', []):
            sel = " [SELECTED]" if b.get('selected') else ""
            print(f"    ({b['x']}, {b['y']}) '{b['text']}'{sel}")
        print(f"\n  Full text:")
        for line in eu_map.get('text', '').split('\n')[:15]:
            line = line.strip()
            if line:
                print(f"    > {line[:60]}")

        screenshot(page, "p301_enhance_sidebar")
    else:
        print(f"  FAILED to open Enhance panel (got: {panel})")

    # ================================================================
    # TASK 4: Complete Automation Recipe
    # ================================================================
    print("\n" + "=" * 70)
    print("TASK 4: Document Automation Recipe")
    print("=" * 70)

    # Map all key automation coordinates and selectors
    print("\n  === COMPLETE AUTOMATION RECIPE ===\n")

    print("  SIDEBAR POSITIONS (all at x=40):")
    sidebar = [
        ("Upload", 81), ("Assets", 136), ("Txt2Img", 197),
        ("Img2Img", 252), ("Character", 306), ("AI Video", 361),
        ("Lip Sync", 427), ("Video Editor", 490), ("Motion Control", 563),
        ("Enhance & Upscale", 630), ("Image Editor", 698), ("Storyboard", 778)
    ]
    for name, y in sidebar:
        print(f"    {name:20s} → page.mouse.click(40, {y})")

    print("\n  MODEL SELECTOR (AI Video):")
    print("    1. Open AI Video panel: page.mouse.click(40, 361)")
    print("    2. Find selector: panel.querySelector('.custom-selector-wrapper')")
    print("    3. Get selector center: getBoundingClientRect() → cx, cy")
    print("    4. Open popup: page.mouse.click(cx, cy)  # NOT el.click()!")
    print("    5. Scroll: document.querySelector('.panel-body').scrollTop = scrollHeight")
    print("    6. Find Wan 2.1: search for text starting with 'Wan 2.1'")
    print("    7. Click: page.mouse.click(wan_x, wan_y)")

    print("\n  STRUCTURE MATCH SLIDER (Img2Img):")
    print("    1. Open Img2Img panel: page.mouse.click(40, 252)")
    print("    2. Find handle: panel.querySelector('.ant-slider-handle')")
    print("    3. Find rail: panel.querySelector('.ant-slider-rail, .ant-slider')")
    print("    4. Drag: page.mouse.move(handle_cx, handle_cy)")
    print("           page.mouse.down()")
    print("           page.mouse.move(target_x, handle_cy, steps=15)")
    print("           page.mouse.up()")
    print("    5. target_x = rail.x + rail.w * desired_value (0.0 to 1.0)")

    print("\n  IMAGE DOWNLOAD:")
    print("    1. Find result images in DOM")
    print("    2. Get src URL (static.dzine.ai)")
    print("    3. Fetch via page.evaluate: fetch(url).then(blob).then(base64)")
    print("    4. Decode base64 and save")

    print("\n  VIDEO DOWNLOAD:")
    print("    Same as image download but for video elements (MP4)")

    # ================================================================
    # TASK 5: Map complete AI Video model list with pricing
    # ================================================================
    print("\n" + "=" * 70)
    print("TASK 5: Complete AI Video Model List")
    print("=" * 70)

    # Open AI Video and the model popup to capture all models
    panel = open_panel(page, "AI Video", 361)
    if panel == 'ai_video':
        # Open model selector popup
        sel_pos = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return null;
            var sel = panel.querySelector('.custom-selector-wrapper');
            if (!sel) return null;
            var rect = sel.getBoundingClientRect();
            return {cx: Math.round(rect.x + rect.width/2), cy: Math.round(rect.y + rect.height/2)};
        }""")
        if sel_pos:
            page.mouse.click(sel_pos['cx'], sel_pos['cy'])
            page.wait_for_timeout(2000)

            # Capture ALL models by scrolling from top to bottom
            # First scroll to top
            page.evaluate("""() => {
                for (var el of document.querySelectorAll('.panel-body')) {
                    if (el.scrollHeight > el.clientHeight + 30) {
                        el.scrollTop = 0;
                    }
                }
            }""")
            page.wait_for_timeout(500)

            # Capture all model cards
            all_models = page.evaluate("""() => {
                var models = [];
                // Find all model card elements
                for (var el of document.querySelectorAll('[class*="model-card"], [class*="card-item"], [class*="selector-item"]')) {
                    var text = (el.innerText || '').trim();
                    if (text && el.offsetHeight > 30 && el.offsetWidth > 80) {
                        var rect = el.getBoundingClientRect();
                        models.push({
                            text: text.replace(/\\n/g, ' | '),
                            y: Math.round(rect.y),
                            h: Math.round(rect.height)
                        });
                    }
                }
                if (models.length === 0) {
                    // Fallback: look for any elements with credit info
                    for (var el of document.querySelectorAll('*')) {
                        var text = (el.innerText || '').trim();
                        if (text.includes('credits') && text.includes('/') && el.offsetHeight > 30 && el.offsetHeight < 120 && el.offsetWidth > 100 && el.offsetWidth < 250) {
                            var rect = el.getBoundingClientRect();
                            models.push({
                                text: text.replace(/\\n/g, ' | '),
                                y: Math.round(rect.y),
                                h: Math.round(rect.height)
                            });
                        }
                    }
                }
                // Deduplicate by text
                var seen = {};
                return models.filter(function(m) {
                    var key = m.text.substring(0, 30);
                    if (seen[key]) return false;
                    seen[key] = true;
                    return true;
                }).sort(function(a, b) { return a.y - b.y; });
            }""")

            print(f"  Models visible at top ({len(all_models)}):")
            for m in all_models:
                print(f"    y={m['y']} '{m['text'][:70]}'")

            # Scroll to bottom
            page.evaluate("""() => {
                for (var el of document.querySelectorAll('.panel-body')) {
                    if (el.scrollHeight > el.clientHeight + 30) {
                        el.scrollTop = el.scrollHeight;
                    }
                }
            }""")
            page.wait_for_timeout(800)

            # Capture models at bottom
            bottom_models = page.evaluate("""() => {
                var models = [];
                for (var el of document.querySelectorAll('*')) {
                    var text = (el.innerText || '').trim();
                    if (text.includes('credits') && text.includes('/') && el.offsetHeight > 30 && el.offsetHeight < 120 && el.offsetWidth > 100 && el.offsetWidth < 250) {
                        var rect = el.getBoundingClientRect();
                        if (rect.y > 0 && rect.y < window.innerHeight) {
                            models.push({
                                text: text.replace(/\\n/g, ' | '),
                                y: Math.round(rect.y)
                            });
                        }
                    }
                }
                var seen = {};
                return models.filter(function(m) {
                    var key = m.text.substring(0, 30);
                    if (seen[key]) return false;
                    seen[key] = true;
                    return true;
                }).sort(function(a, b) { return a.y - b.y; });
            }""")

            print(f"\n  Models visible at bottom ({len(bottom_models)}):")
            for m in bottom_models:
                print(f"    y={m['y']} '{m['text'][:70]}'")

            # Take screenshots at top and bottom
            page.evaluate("""() => {
                for (var el of document.querySelectorAll('.panel-body')) {
                    if (el.scrollHeight > el.clientHeight + 30) el.scrollTop = 0;
                }
            }""")
            page.wait_for_timeout(500)
            screenshot(page, "p301_models_top")

            page.evaluate("""() => {
                for (var el of document.querySelectorAll('.panel-body')) {
                    if (el.scrollHeight > el.clientHeight + 30) el.scrollTop = el.scrollHeight / 2;
                }
            }""")
            page.wait_for_timeout(500)
            screenshot(page, "p301_models_middle")

            page.evaluate("""() => {
                for (var el of document.querySelectorAll('.panel-body')) {
                    if (el.scrollHeight > el.clientHeight + 30) el.scrollTop = el.scrollHeight;
                }
            }""")
            page.wait_for_timeout(500)
            screenshot(page, "p301_models_bottom")

            # Close popup
            page.keyboard.press('Escape')
            page.wait_for_timeout(500)

    # ================================================================
    # Final Credits
    # ================================================================
    print("\n" + "=" * 70)
    print("Final Credits")
    print("=" * 70)
    credits_after = page.evaluate("""() => {
        for (var el of document.querySelectorAll('*')) {
            var t = (el.innerText || '').trim();
            if (t.match(/^Unlimited\\s*\\/\\s*[\\d.,]+$/)) return t;
        }
        return 'unknown';
    }""")
    print(f"  Credits: {credits_after}")

    print("\n" + "=" * 70)
    print("EXPLORATION PART 30 COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
