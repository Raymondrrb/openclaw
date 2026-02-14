#!/usr/bin/env python3
"""Dzine Deep Exploration Part 32 — Close blocking dialog + Wan 2.1 gen + Video Editor.

Part 31 revealed: Pick Image dialog (class: pick-panel) is STILL OPEN blocking everything.
close_all() looked for '.pick-image-dialog' but actual class is '.pick-panel'.

Fix: Close pick-panel, then:
1. Open AI Video, select Wan 2.1, use canvas image as start frame, generate
2. Explore Video Editor (y=490) and Enhance (y=630) with proper panel close
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


def close_everything(page):
    """Close ALL dialogs, panels, popups — including pick-panel."""
    page.evaluate("""() => {
        // Close pick-panel dialog (the blocking one!)
        var pp = document.querySelector('.pick-panel');
        if (pp) {
            var close = pp.querySelector('.ico-close, [class*="close"]');
            if (close) close.click();
        }
        // Close pick-image-dialog
        var pid = document.querySelector('.pick-image-dialog');
        if (pid) {
            var c = pid.querySelector('.ico-close');
            if (c) c.click();
        }
        // Close gen-config panel
        var panel = document.querySelector('.c-gen-config.show');
        if (panel) {
            var close = panel.querySelector('.ico-close, button.close');
            if (close) close.click();
        }
        // Close any remaining close buttons
        for (var el of document.querySelectorAll('.ico-close')) {
            if (el.offsetHeight > 0) try { el.click(); } catch(e) {}
        }
    }""")
    page.wait_for_timeout(500)
    page.keyboard.press('Escape')
    page.wait_for_timeout(300)
    page.keyboard.press('Escape')
    page.wait_for_timeout(300)

    # Verify dialogs are closed
    remaining = page.evaluate("""() => {
        var pp = document.querySelector('.pick-panel');
        var pid = document.querySelector('.pick-image-dialog');
        return {
            pickPanel: pp ? pp.offsetHeight > 0 : false,
            pickImageDialog: pid ? pid.offsetHeight > 0 : false
        };
    }""")
    print(f"  Dialogs after close: {json.dumps(remaining)}")
    return remaining


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
        return 'unknown:' + text.substring(0, 50);
    }""")


def open_panel(page, tool_name, sidebar_y, timeout=2500):
    close_everything(page)
    page.wait_for_timeout(300)
    page.mouse.click(40, sidebar_y)
    page.wait_for_timeout(timeout)
    panel = get_active_panel(page)
    print(f"  Opened '{tool_name}': panel={panel}")
    return panel


def main():
    print("=" * 70)
    print("DZINE DEEP EXPLORATION PART 32")
    print("Close Dialog + Wan 2.1 Gen + Video Editor + Enhance")
    print("=" * 70)

    browser, context, _, _pw = connect_or_launch()
    page = context.pages[0]
    print(f"Connected. URL: {page.url}")

    if "dzine.ai/canvas" not in page.url:
        page.goto("https://www.dzine.ai/canvas?id=19861203")
        page.wait_for_timeout(6000)

    # Step 0: Close the blocking Pick Image dialog
    print("\n>>> Closing blocking dialog...")
    remaining = close_everything(page)

    if remaining.get('pickPanel') or remaining.get('pickImageDialog'):
        print("  Dialog still open. Trying harder...")
        # Click the X button at the top-right of the dialog
        # From screenshot: dialog is centered, X is at top-right
        page.evaluate("""() => {
            // Find the modal/dialog close button more aggressively
            for (var el of document.querySelectorAll('svg, i, span, div')) {
                var cls = (typeof el.className === 'string') ? el.className : '';
                if (cls.includes('close') || cls.includes('ico-close')) {
                    var rect = el.getBoundingClientRect();
                    if (rect.height > 0 && rect.height < 40 && rect.y > 50 && rect.y < 200) {
                        el.click();
                    }
                }
            }
        }""")
        page.wait_for_timeout(500)
        page.keyboard.press('Escape')
        page.wait_for_timeout(500)

    screenshot(page, "p321_after_close")

    credits = page.evaluate("""() => {
        for (var el of document.querySelectorAll('*')) {
            var t = (el.innerText || '').trim();
            if (t.match(/^Unlimited\\s*\\/\\s*[\\d.,]+$/)) return t;
        }
        return 'unknown';
    }""")
    print(f"  Credits: {credits}")

    # ================================================================
    # TASK 1: Wan 2.1 Video — Canvas Image → Video
    # ================================================================
    print("\n" + "=" * 70)
    print("TASK 1: Wan 2.1 Video Generation")
    print("=" * 70)

    panel = open_panel(page, "AI Video", 361)

    if panel == 'ai_video':
        # Check and set Wan 2.1
        current = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return '';
            var sel = panel.querySelector('.custom-selector-wrapper');
            return sel ? (sel.innerText || '').trim().split('\\n')[0] : '';
        }""")
        print(f"  Current model: {current}")

        if 'Wan' not in current:
            print("  Selecting Wan 2.1...")
            sel_pos = page.evaluate("""() => {
                var panel = document.querySelector('.c-gen-config.show');
                var sel = panel ? panel.querySelector('.custom-selector-wrapper') : null;
                if (!sel) return null;
                var rect = sel.getBoundingClientRect();
                return {cx: Math.round(rect.x + rect.width/2), cy: Math.round(rect.y + rect.height/2)};
            }""")
            if sel_pos:
                page.mouse.click(sel_pos['cx'], sel_pos['cy'])
                page.wait_for_timeout(2000)
                page.evaluate("""() => {
                    for (var el of document.querySelectorAll('.panel-body')) {
                        if (el.scrollHeight > el.clientHeight + 30) el.scrollTop = el.scrollHeight;
                    }
                }""")
                page.wait_for_timeout(800)
                wan = page.evaluate("""() => {
                    for (var el of document.querySelectorAll('*')) {
                        var text = (el.innerText || '').trim();
                        if (text.startsWith('Wan 2.1') && el.offsetHeight > 20 && el.offsetHeight < 120 && el.offsetWidth > 40) {
                            var rect = el.getBoundingClientRect();
                            if (rect.y > 0 && rect.y < window.innerHeight) return {x: Math.round(rect.x + rect.width/2), y: Math.round(rect.y + rect.height/2)};
                        }
                    }
                    return null;
                }""")
                if wan:
                    page.mouse.click(wan['x'], wan['y'])
                    page.wait_for_timeout(2000)
                    print("  Wan 2.1 selected")

        # Click Start Frame
        sf_btn = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return null;
            for (var el of panel.querySelectorAll('[class*="pick-image"], button')) {
                var text = (el.innerText || '').trim();
                if (text.includes('Start Frame') || text.includes('Start')) {
                    var rect = el.getBoundingClientRect();
                    if (rect.height > 30 && rect.height < 100) {
                        return {x: Math.round(rect.x + rect.width/2), y: Math.round(rect.y + rect.height/2), text: text};
                    }
                }
            }
            return null;
        }""")
        print(f"  Start Frame: {json.dumps(sf_btn)}")

        if sf_btn:
            page.mouse.click(sf_btn['x'], sf_btn['y'])
            page.wait_for_timeout(2000)

            # NOW: the Pick Image dialog opens with canvas thumbnail
            # Find and click the canvas image thumbnail
            canvas_thumb = page.evaluate("""() => {
                // Look for the dialog (pick-panel class)
                var dialog = document.querySelector('.pick-panel');
                if (!dialog || dialog.offsetHeight === 0) {
                    // Try pick-image-dialog
                    dialog = document.querySelector('.pick-image-dialog');
                }
                if (!dialog || dialog.offsetHeight === 0) return {error: 'no dialog'};

                // Find images in the dialog
                var imgs = [];
                for (var img of dialog.querySelectorAll('img')) {
                    if (img.offsetHeight > 30 && img.offsetWidth > 30) {
                        var rect = img.getBoundingClientRect();
                        imgs.push({
                            x: Math.round(rect.x + rect.width/2),
                            y: Math.round(rect.y + rect.height/2),
                            w: Math.round(rect.width),
                            h: Math.round(rect.height),
                            src: (img.src || '').substring(0, 60)
                        });
                    }
                }

                // Also look for div thumbnails with background-image
                for (var el of dialog.querySelectorAll('[class*="thumb"], [class*="preview"], [class*="canvas"]')) {
                    var rect = el.getBoundingClientRect();
                    var bg = window.getComputedStyle(el).backgroundImage;
                    if (rect.height > 30 && (bg && bg !== 'none')) {
                        imgs.push({
                            x: Math.round(rect.x + rect.width/2),
                            y: Math.round(rect.y + rect.height/2),
                            w: Math.round(rect.width),
                            h: Math.round(rect.height),
                            src: 'bg:' + bg.substring(0, 60),
                            type: 'bg-div'
                        });
                    }
                }

                // Also find any clickable element near "canvas" text
                var canvasArea = null;
                for (var el of dialog.querySelectorAll('*')) {
                    var text = (el.innerText || '').trim().toLowerCase();
                    if (text.includes('canvas') && text.includes('image') && el.offsetHeight > 0) {
                        // The clickable image should be a sibling or child
                        var parent = el.parentElement;
                        if (parent) {
                            for (var child of parent.querySelectorAll('img, [class*="thumb"]')) {
                                var rect = child.getBoundingClientRect();
                                if (rect.height > 30) {
                                    canvasArea = {x: Math.round(rect.x + rect.width/2), y: Math.round(rect.y + rect.height/2), w: Math.round(rect.width), h: Math.round(rect.height)};
                                }
                            }
                        }
                    }
                }

                return {imgs: imgs, canvasArea: canvasArea, dialogCls: (typeof dialog.className === 'string') ? dialog.className.substring(0, 40) : ''};
            }""")

            print(f"  Dialog: cls={canvas_thumb.get('dialogCls')}")
            print(f"  Canvas area: {json.dumps(canvas_thumb.get('canvasArea'))}")
            print(f"  Images ({len(canvas_thumb.get('imgs', []))}):")
            for img in canvas_thumb.get('imgs', []):
                print(f"    ({img['x']}, {img['y']}) {img['w']}x{img['h']} src={img.get('src', '')[:40]}")

            screenshot(page, "p321_pick_dialog")

            # Click the canvas image
            target = canvas_thumb.get('canvasArea')
            if not target and canvas_thumb.get('imgs'):
                target = canvas_thumb['imgs'][0]

            if target:
                print(f"\n  Clicking canvas image at ({target['x']}, {target['y']})...")
                page.mouse.click(target['x'], target['y'])
                page.wait_for_timeout(2000)

                # Check if dialog closed
                dialog_state = page.evaluate("""() => {
                    var pp = document.querySelector('.pick-panel');
                    var pid = document.querySelector('.pick-image-dialog');
                    return {
                        pickPanel: pp ? pp.offsetHeight > 0 : false,
                        pickImageDialog: pid ? pid.offsetHeight > 0 : false
                    };
                }""")
                print(f"  Dialog after click: {json.dumps(dialog_state)}")

                if dialog_state.get('pickPanel') or dialog_state.get('pickImageDialog'):
                    # Dialog still open — might need double click or there's a confirm
                    print("  Dialog still open. Trying double click on image...")
                    page.mouse.dblclick(target['x'], target['y'])
                    page.wait_for_timeout(2000)

                    dialog_state2 = page.evaluate("""() => {
                        var pp = document.querySelector('.pick-panel');
                        return pp ? pp.offsetHeight > 0 : false;
                    }""")
                    print(f"  Dialog after dblclick: {dialog_state2}")

                    if dialog_state2:
                        # Try clicking the image and then the area below (might have a select button)
                        page.mouse.click(target['x'], target['y'])
                        page.wait_for_timeout(500)

                        # Check for any action buttons that appeared after selection
                        actions = page.evaluate("""() => {
                            var dialog = document.querySelector('.pick-panel') || document.querySelector('.pick-image-dialog');
                            if (!dialog) return [];
                            var btns = [];
                            for (var btn of dialog.querySelectorAll('button, [role="button"]')) {
                                var t = (btn.innerText || '').trim();
                                if (t && t.length < 30 && btn.offsetHeight > 0) {
                                    var rect = btn.getBoundingClientRect();
                                    btns.push({text: t, x: Math.round(rect.x + rect.width/2), y: Math.round(rect.y + rect.height/2)});
                                }
                            }
                            return btns;
                        }""")
                        print(f"  Dialog buttons: {json.dumps(actions)}")

                        # Check if the image is now "selected" (highlighted)
                        selected = page.evaluate("""() => {
                            var dialog = document.querySelector('.pick-panel') || document.querySelector('.pick-image-dialog');
                            if (!dialog) return {};
                            for (var el of dialog.querySelectorAll('[class*="selected"], [class*="active"], [class*="checked"]')) {
                                if (el.offsetHeight > 0) {
                                    return {cls: (typeof el.className === 'string') ? el.className.substring(0, 40) : '', tag: el.tagName};
                                }
                            }
                            return {};
                        }""")
                        print(f"  Selected state: {json.dumps(selected)}")

                screenshot(page, "p321_after_canvas_select")

            # Check if start frame is now set
            gen_ready = page.evaluate("""() => {
                var panel = document.querySelector('.c-gen-config.show');
                if (!panel) return {noPanel: true};
                var genBtn = null;
                for (var btn of panel.querySelectorAll('button')) {
                    if ((btn.innerText || '').includes('Generate')) {
                        genBtn = {text: (btn.innerText || '').trim(), disabled: btn.disabled};
                    }
                }
                var warning = '';
                for (var el of panel.querySelectorAll('*')) {
                    var t = (el.innerText || '').trim();
                    if ((t.includes('upload') || t.includes('key frame')) && el.offsetHeight > 0 && el.offsetHeight < 30) {
                        warning = t; break;
                    }
                }
                var thumb = panel.querySelector('.frame-thumb img, .pick-image img, .key-frame img');
                return {genBtn: genBtn, warning: warning, hasThumb: !!thumb};
            }""")
            print(f"  Generate ready: {json.dumps(gen_ready)}")

            # If ready, generate!
            if gen_ready.get('genBtn') and not gen_ready['genBtn'].get('disabled') and not gen_ready.get('warning'):
                print("\n  >>> GENERATING Wan 2.1 VIDEO! (6 credits, ~60s)")
                gen_pos = page.evaluate("""() => {
                    var panel = document.querySelector('.c-gen-config.show');
                    if (!panel) return null;
                    for (var btn of panel.querySelectorAll('button')) {
                        if ((btn.innerText || '').includes('Generate') && !btn.disabled) {
                            var rect = btn.getBoundingClientRect();
                            return {x: Math.round(rect.x + rect.width/2), y: Math.round(rect.y + rect.height/2)};
                        }
                    }
                    return null;
                }""")
                if gen_pos:
                    page.mouse.click(gen_pos['x'], gen_pos['y'])
                    print("  Clicked Generate. Waiting...")

                    # Wait for generation
                    for i in range(15):
                        page.wait_for_timeout(10000)
                        status = page.evaluate("""() => {
                            // Check for video in results
                            var vids = document.querySelectorAll('video[src*="static.dzine.ai"]');
                            // Check progress/loading
                            var loading = false;
                            for (var el of document.querySelectorAll('[class*="loading"], [class*="progress"], [class*="generating"]')) {
                                if (el.offsetHeight > 0) loading = true;
                            }
                            var panel = document.querySelector('.c-gen-config.show');
                            var genText = '';
                            if (panel) {
                                for (var btn of panel.querySelectorAll('button')) {
                                    if ((btn.innerText || '').includes('Generate')) genText = (btn.innerText || '').trim();
                                }
                            }
                            return {videoCount: vids.length, loading: loading, genBtn: genText};
                        }""")
                        secs = (i + 1) * 10
                        print(f"  [{secs}s] videos={status.get('videoCount', 0)} loading={status.get('loading')} gen='{status.get('genBtn', '')}'")
                        if status.get('videoCount', 0) > 0 and secs > 30:
                            break

                    screenshot(page, "p321_wan21_result")

                    # Download video
                    video_url = page.evaluate("""() => {
                        var vids = document.querySelectorAll('video');
                        for (var v of vids) {
                            if (v.src && v.src.includes('static.dzine.ai')) return v.src;
                        }
                        for (var s of document.querySelectorAll('video source')) {
                            if (s.src && s.src.includes('static.dzine.ai')) return s.src;
                        }
                        return null;
                    }""")
                    if video_url:
                        save_path = "/Users/ray/Documents/openclaw/artifacts/dzine/wan21_test.mp4"
                        os.makedirs(os.path.dirname(save_path), exist_ok=True)
                        b64 = page.evaluate("""(url) => {
                            return fetch(url).then(r => r.blob()).then(b => new Promise((resolve) => {
                                var reader = new FileReader();
                                reader.onload = () => resolve(reader.result);
                                reader.readAsDataURL(b);
                            })).catch(e => 'error: ' + e.message);
                        }""", video_url)
                        if b64 and not b64.startswith('error:'):
                            data = b64.split(',', 1)[1]
                            with open(save_path, 'wb') as f:
                                f.write(base64.b64decode(data))
                            fsize = os.path.getsize(save_path)
                            print(f"  Video saved: {save_path} ({fsize} bytes)")
                        else:
                            print(f"  Download failed: {(b64 or '')[:80]}")
                    else:
                        print("  No video URL found")

                    credits_after = page.evaluate("""() => {
                        for (var el of document.querySelectorAll('*')) {
                            var t = (el.innerText || '').trim();
                            if (t.match(/^Unlimited\\s*\\/\\s*[\\d.,]+$/)) return t;
                        }
                        return 'unknown';
                    }""")
                    print(f"  Credits after: {credits_after}")
            else:
                print("  Not ready to generate.")
                # Try alternative: use result image from results panel via "AI Video" action
                print("\n  Trying alternative: results panel → AI Video action button")
                close_everything(page)
                page.wait_for_timeout(500)

                # Click on Results tab
                page.evaluate("""() => {
                    for (var el of document.querySelectorAll('[class*="header-item"], [class*="tab"]')) {
                        if ((el.innerText || '').trim() === 'Results') { el.click(); return; }
                    }
                }""")
                page.wait_for_timeout(500)

                # Find AI Video action button on a result image
                ai_video_action = page.evaluate("""() => {
                    for (var el of document.querySelectorAll('[class*="action"], button, [class*="btn"]')) {
                        var text = (el.innerText || '').trim();
                        if (text === 'AI Video' && el.offsetHeight > 0) {
                            var rect = el.getBoundingClientRect();
                            return {x: Math.round(rect.x + rect.width/2), y: Math.round(rect.y + rect.height/2)};
                        }
                    }
                    return null;
                }""")
                print(f"  AI Video action: {json.dumps(ai_video_action)}")

                if ai_video_action:
                    print(f"  Clicking AI Video action at ({ai_video_action['x']}, {ai_video_action['y']})...")
                    page.mouse.click(ai_video_action['x'], ai_video_action['y'])
                    page.wait_for_timeout(3000)

                    # This should open AI Video with the image pre-set as start frame
                    gen_state = page.evaluate("""() => {
                        var panel = document.querySelector('.c-gen-config.show');
                        if (!panel) return {};
                        var sel = panel.querySelector('.custom-selector-wrapper');
                        var model = sel ? (sel.innerText || '').trim().split('\\n')[0] : '';
                        var genBtn = null;
                        for (var btn of panel.querySelectorAll('button')) {
                            if ((btn.innerText || '').includes('Generate')) {
                                genBtn = {text: (btn.innerText || '').trim(), disabled: btn.disabled};
                            }
                        }
                        var thumb = panel.querySelector('.frame-thumb img, .pick-image img');
                        return {model: model, genBtn: genBtn, hasThumb: !!thumb};
                    }""")
                    print(f"  After AI Video action: {json.dumps(gen_state)}")
                    screenshot(page, "p321_ai_video_from_results")

    # ================================================================
    # TASK 2: Video Editor
    # ================================================================
    print("\n" + "=" * 70)
    print("TASK 2: Video Editor (y=490)")
    print("=" * 70)

    panel = open_panel(page, "Video Editor", 490, timeout=3000)

    if panel != 'none':
        ve_text = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return '';
            return (panel.innerText || '').substring(0, 800);
        }""")
        print(f"  Panel text:")
        for line in ve_text.split('\n')[:15]:
            line = line.strip()
            if line:
                print(f"    > {line[:60]}")
        screenshot(page, "p321_video_editor")
    else:
        print("  Video Editor panel returned 'none'. Checking if it needs video input...")
        # Video Editor may require a video to be selected first
        # Check if there's a message about this
        page_check = page.evaluate("""() => {
            // Check for any visible message/tooltip
            for (var el of document.querySelectorAll('[class*="message"], [class*="tip"], [class*="toast"], [class*="notification"]')) {
                if (el.offsetHeight > 0) {
                    return {message: (el.innerText || '').trim()};
                }
            }
            return {};
        }""")
        print(f"  Messages: {json.dumps(page_check)}")
        screenshot(page, "p321_video_editor_none")

    # ================================================================
    # TASK 3: Enhance & Upscale
    # ================================================================
    print("\n" + "=" * 70)
    print("TASK 3: Enhance & Upscale (y=630)")
    print("=" * 70)

    panel = open_panel(page, "Enhance & Upscale", 630, timeout=3000)

    if panel != 'none':
        eu_text = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return '';
            return (panel.innerText || '').substring(0, 800);
        }""")
        print(f"  Panel text:")
        for line in eu_text.split('\n')[:15]:
            line = line.strip()
            if line:
                print(f"    > {line[:60]}")

        # Map buttons
        eu_btns = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return [];
            var btns = [];
            for (var btn of panel.querySelectorAll('button, [role="button"]')) {
                var t = (btn.innerText || '').trim();
                if (t && t.length < 40 && btn.offsetHeight > 0) {
                    var rect = btn.getBoundingClientRect();
                    var cls = (typeof btn.className === 'string') ? btn.className : '';
                    btns.push({text: t, x: Math.round(rect.x + rect.width/2), y: Math.round(rect.y + rect.height/2), selected: cls.includes('selected')});
                }
            }
            return btns;
        }""")
        print(f"  Buttons ({len(eu_btns)}):")
        for b in eu_btns:
            sel = " [SELECTED]" if b.get('selected') else ""
            print(f"    ({b['x']}, {b['y']}) '{b['text']}'{sel}")

        screenshot(page, "p321_enhance_sidebar")
    else:
        print("  Enhance panel returned 'none'. May need image selected first.")
        screenshot(page, "p321_enhance_none")

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
    print("EXPLORATION PART 32 COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
