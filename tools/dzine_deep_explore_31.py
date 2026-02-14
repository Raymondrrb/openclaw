#!/usr/bin/env python3
"""Dzine Deep Exploration Part 31 — Wan 2.1 Generation + Video Editor + Enhance.

Part 30 findings:
- Pick Image dialog has "Or choose an image on the canvas" with thumbnail
- Canvas image selection missed in DOM detection
- Video Editor and Enhance panels returned 'none' (different panel class?)

Part 31:
1. Select canvas image as start frame → generate Wan 2.1 video
2. Fix panel detection for Video Editor and Enhance
3. Download Wan 2.1 video result
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


def close_all(page):
    page.evaluate("""() => {
        // Close pick-image dialog first
        var pid = document.querySelector('.pick-image-dialog');
        if (pid) { var c = pid.querySelector('.ico-close'); if (c) c.click(); }
        // Close gen config panel
        var panel = document.querySelector('.c-gen-config.show');
        if (panel) {
            var close = panel.querySelector('.ico-close, button.close');
            if (close) close.click();
        }
        // Close any popups
        for (var el of document.querySelectorAll('.ico-close')) {
            if (el.offsetHeight > 0) try { el.click(); } catch(e) {}
        }
    }""")
    page.wait_for_timeout(300)
    page.keyboard.press('Escape')
    page.wait_for_timeout(300)


def get_any_panel(page):
    """Extended panel detection that checks multiple panel types."""
    return page.evaluate("""() => {
        // Standard gen-config panel
        var panel = document.querySelector('.c-gen-config.show');
        if (panel) {
            var text = (panel.innerText || '').substring(0, 100).trim();
            return {type: 'gen-config', text: text};
        }

        // Check for other panel types
        var candidates = [
            '.video-editor-panel',
            '.enhance-panel',
            '.upscale-panel',
            '[class*="video-editor"]',
            '[class*="enhance-upscale"]',
            '.side-panel.show',
            '.right-side-panel',
        ];
        for (var sel of candidates) {
            var el = document.querySelector(sel);
            if (el && el.offsetHeight > 100) {
                return {type: sel, text: (el.innerText || '').substring(0, 100).trim()};
            }
        }

        // Check for any large panel that appeared on the left side (x < 400)
        for (var el of document.querySelectorAll('[class*="panel"], [class*="config"]')) {
            var rect = el.getBoundingClientRect();
            if (rect.x < 400 && rect.height > 200 && rect.width > 150 && el.offsetHeight > 0) {
                var text = (el.innerText || '').trim();
                if (text.includes('Video Editor') || text.includes('Enhance') || text.includes('Upscale')) {
                    return {type: 'found', cls: (typeof el.className === 'string') ? el.className.substring(0, 60) : '', text: text.substring(0, 100)};
                }
            }
        }

        return {type: 'none'};
    }""")


def main():
    print("=" * 70)
    print("DZINE DEEP EXPLORATION PART 31")
    print("Wan 2.1 Video + Video Editor + Enhance")
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
    # TASK 1: Generate Wan 2.1 Video using canvas image
    # ================================================================
    print("\n" + "=" * 70)
    print("TASK 1: Wan 2.1 Video from Canvas Image")
    print("=" * 70)

    close_all(page)
    page.wait_for_timeout(500)

    # Open AI Video
    page.mouse.click(40, 361)
    page.wait_for_timeout(2500)

    # Verify Wan 2.1 is still selected
    current = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return '';
        var sel = panel.querySelector('.custom-selector-wrapper');
        return sel ? (sel.innerText || '').trim().split('\\n')[0] : '';
    }""")
    print(f"  Current model: {current}")

    if 'Wan' not in current:
        print("  Wan 2.1 not selected. Switching...")
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
                print("  Switched to Wan 2.1")

    # Click Start Frame to open Pick Image dialog
    start_frame_pos = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return null;
        for (var el of panel.querySelectorAll('.pick-image, button.pick-image, [class*="pick-image"]')) {
            var text = (el.innerText || '').trim();
            if (text.includes('Start') || text.includes('Frame')) {
                var rect = el.getBoundingClientRect();
                return {x: Math.round(rect.x + rect.width/2), y: Math.round(rect.y + rect.height/2), text: text};
            }
        }
        return null;
    }""")
    print(f"  Start Frame btn: {json.dumps(start_frame_pos)}")

    if start_frame_pos:
        page.mouse.click(start_frame_pos['x'], start_frame_pos['y'])
        page.wait_for_timeout(2000)

        # Find the canvas image in the dialog
        # From screenshot: "Or choose an image on the canvas" with a thumbnail below
        canvas_img = page.evaluate("""() => {
            var pid = document.querySelector('.pick-image-dialog');
            if (!pid) return {error: 'no dialog'};

            // Look for "canvas" text and nearby image
            var canvasSection = null;
            for (var el of pid.querySelectorAll('*')) {
                var text = (el.innerText || '').trim().toLowerCase();
                if (text.includes('canvas') && text.includes('image') && el.offsetHeight > 0) {
                    canvasSection = el;
                    break;
                }
            }

            // Find all images in the dialog
            var imgs = [];
            for (var img of pid.querySelectorAll('img')) {
                if (img.offsetHeight > 30 && img.offsetWidth > 30) {
                    var rect = img.getBoundingClientRect();
                    imgs.push({
                        src: (img.src || '').substring(0, 80),
                        x: Math.round(rect.x + rect.width/2),
                        y: Math.round(rect.y + rect.height/2),
                        w: Math.round(rect.width),
                        h: Math.round(rect.height),
                        alt: img.alt || ''
                    });
                }
            }

            // Also look for clickable canvas preview elements
            var clickables = [];
            for (var el of pid.querySelectorAll('[class*="canvas"], [class*="preview"], [class*="thumb"]')) {
                if (el.offsetHeight > 30) {
                    var rect = el.getBoundingClientRect();
                    clickables.push({
                        cls: (typeof el.className === 'string') ? el.className.substring(0, 40) : '',
                        x: Math.round(rect.x + rect.width/2),
                        y: Math.round(rect.y + rect.height/2),
                        w: Math.round(rect.width),
                        h: Math.round(rect.height)
                    });
                }
            }

            return {
                hasCanvasSection: !!canvasSection,
                canvasSectionText: canvasSection ? (canvasSection.innerText || '').trim().substring(0, 80) : '',
                imgs: imgs,
                clickables: clickables
            };
        }""")

        print(f"  Canvas section: {canvas_img.get('hasCanvasSection')} '{canvas_img.get('canvasSectionText', '')}'")
        print(f"  Images ({len(canvas_img.get('imgs', []))}):")
        for img in canvas_img.get('imgs', []):
            print(f"    ({img['x']}, {img['y']}) {img['w']}x{img['h']} src={img['src'][:50]}")
        print(f"  Clickables ({len(canvas_img.get('clickables', []))}):")
        for c in canvas_img.get('clickables', []):
            print(f"    ({c['x']}, {c['y']}) {c['w']}x{c['h']} cls={c['cls']}")

        screenshot(page, "p311_pick_image_detail")

        # Click the canvas image thumbnail
        if canvas_img.get('imgs'):
            img = canvas_img['imgs'][0]
            print(f"\n  Clicking canvas image at ({img['x']}, {img['y']})...")
            page.mouse.click(img['x'], img['y'])
            page.wait_for_timeout(2000)

            # Check if dialog closed and start frame was set
            dialog_closed = page.evaluate("""() => {
                var pid = document.querySelector('.pick-image-dialog');
                return !pid || pid.offsetHeight === 0;
            }""")
            print(f"  Dialog closed: {dialog_closed}")

            if not dialog_closed:
                # Maybe need to click a confirm button
                confirm_result = page.evaluate("""() => {
                    var pid = document.querySelector('.pick-image-dialog');
                    if (!pid) return {closed: true};
                    // Look for confirm/select button
                    for (var btn of pid.querySelectorAll('button')) {
                        var text = (btn.innerText || '').trim().toLowerCase();
                        if (text.includes('confirm') || text.includes('ok') || text.includes('select') || text.includes('use') || text.includes('apply')) {
                            btn.click();
                            return {clicked: text};
                        }
                    }
                    return {noConfirmBtn: true};
                }""")
                print(f"  Confirm: {json.dumps(confirm_result)}")
                page.wait_for_timeout(1500)

            # Verify start frame is set
            frame_check = page.evaluate("""() => {
                var panel = document.querySelector('.c-gen-config.show');
                if (!panel) return {noPanel: true};
                // Check for thumbnail in start frame area
                var thumb = panel.querySelector('.frame-thumb img, .pick-image img, .key-frame img');
                var hasThumb = false;
                var thumbSrc = '';
                if (thumb) {
                    hasThumb = true;
                    thumbSrc = (thumb.src || '').substring(0, 60);
                }
                // Also check for the "has-guide" class removal
                var pickBtn = panel.querySelector('.pick-image');
                var hasGuide = pickBtn ? pickBtn.classList.contains('has-guide') : false;
                // Check generate button
                var genBtn = null;
                for (var btn of panel.querySelectorAll('button')) {
                    if ((btn.innerText || '').includes('Generate')) {
                        genBtn = {text: (btn.innerText || '').trim(), disabled: btn.disabled};
                    }
                }
                // Check warning
                var warning = '';
                for (var el of panel.querySelectorAll('*')) {
                    var t = (el.innerText || '').trim();
                    if (t.includes('upload') || t.includes('key frame') || t.includes('Please')) {
                        if (el.offsetHeight > 0 && el.offsetHeight < 30) { warning = t; break; }
                    }
                }
                return {hasThumb: hasThumb, thumbSrc: thumbSrc, genBtn: genBtn, warning: warning};
            }""")
            print(f"  Frame check: {json.dumps(frame_check)}")

            screenshot(page, "p311_after_frame_set")

            # Generate if ready
            if frame_check.get('genBtn') and not frame_check['genBtn'].get('disabled') and not frame_check.get('warning'):
                print("\n  >>> GENERATING Wan 2.1 VIDEO...")
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
                    print(f"  Generation started! Waiting ~60s for Wan 2.1...")

                    # Wait for generation (Wan 2.1 takes ~60s)
                    for i in range(12):
                        page.wait_for_timeout(10000)
                        # Check for completion
                        progress = page.evaluate("""() => {
                            // Check results panel for new video
                            var videos = document.querySelectorAll('video');
                            var newResults = 0;
                            for (var v of videos) {
                                if (v.src && v.src.includes('static.dzine.ai')) newResults++;
                            }
                            // Check for loading indicator
                            var loading = document.querySelector('[class*="loading"], [class*="generating"], [class*="progress"]');
                            var isLoading = loading && loading.offsetHeight > 0;
                            // Check generate button state
                            var panel = document.querySelector('.c-gen-config.show');
                            var genText = '';
                            if (panel) {
                                for (var btn of panel.querySelectorAll('button')) {
                                    if ((btn.innerText || '').includes('Generate')) genText = (btn.innerText || '').trim();
                                }
                            }
                            return {videos: newResults, isLoading: isLoading, genBtn: genText, elapsed: (i + 1) * 10};
                        }""")
                        print(f"  [{(i+1)*10}s] videos={progress.get('videos', 0)} loading={progress.get('isLoading')} gen={progress.get('genBtn', '')}")

                        # Check for new result in results panel
                        if progress.get('videos', 0) > 0 or (not progress.get('isLoading') and 'Generate' in progress.get('genBtn', '')):
                            if i > 3:  # Give at least 40s
                                break

                    screenshot(page, "p311_video_result")

                    # Try to download the video
                    video_url = page.evaluate("""() => {
                        var videos = document.querySelectorAll('video');
                        for (var v of videos) {
                            if (v.src && v.src.includes('static.dzine.ai')) {
                                return v.src;
                            }
                        }
                        // Also check source elements
                        for (var s of document.querySelectorAll('video source')) {
                            if (s.src && s.src.includes('static.dzine.ai')) return s.src;
                        }
                        return null;
                    }""")
                    print(f"  Video URL: {video_url}")

                    if video_url:
                        # Download video
                        save_path = "/Users/ray/Documents/openclaw/artifacts/dzine/wan21_video.mp4"
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
                            print(f"  Download error: {b64}")

                    # Check credits after
                    credits_after_gen = page.evaluate("""() => {
                        for (var el of document.querySelectorAll('*')) {
                            var t = (el.innerText || '').trim();
                            if (t.match(/^Unlimited\\s*\\/\\s*[\\d.,]+$/)) return t;
                        }
                        return 'unknown';
                    }""")
                    print(f"  Credits after gen: {credits_after_gen}")
            else:
                print("  Generate still disabled. Warning: " + frame_check.get('warning', ''))
                screenshot(page, "p311_gen_disabled")
        elif canvas_img.get('clickables'):
            # Try clickable canvas preview elements
            c = canvas_img['clickables'][0]
            print(f"  Trying clickable at ({c['x']}, {c['y']})...")
            page.mouse.click(c['x'], c['y'])
            page.wait_for_timeout(2000)
        else:
            print("  No canvas image found in dialog. Closing.")
            page.keyboard.press('Escape')
            page.wait_for_timeout(500)

    # ================================================================
    # TASK 2: Video Editor Panel (extended detection)
    # ================================================================
    print("\n" + "=" * 70)
    print("TASK 2: Video Editor Panel (extended detection)")
    print("=" * 70)

    close_all(page)
    page.wait_for_timeout(500)

    # Click Video Editor sidebar
    page.mouse.click(40, 490)
    page.wait_for_timeout(3000)

    # Use extended detection
    ve_panel = get_any_panel(page)
    print(f"  Panel detected: {json.dumps(ve_panel)}")

    screenshot(page, "p311_video_editor_attempt")

    # If still none, check what changed on the page
    if ve_panel.get('type') == 'none':
        # Maybe it opened something in a different area
        page_state = page.evaluate("""() => {
            // Check for any new visible panels/overlays
            var newPanels = [];
            for (var el of document.querySelectorAll('[class*="panel"], [class*="editor"], [class*="config"]')) {
                if (el.offsetHeight > 100 && el.offsetWidth > 100) {
                    var text = (el.innerText || '').trim();
                    if (text.length > 10 && text.length < 2000) {
                        var rect = el.getBoundingClientRect();
                        newPanels.push({
                            cls: (typeof el.className === 'string') ? el.className.substring(0, 60) : '',
                            text: text.substring(0, 100),
                            x: Math.round(rect.x),
                            y: Math.round(rect.y),
                            w: Math.round(rect.width),
                            h: Math.round(rect.height)
                        });
                    }
                }
            }
            return newPanels.slice(0, 10);
        }""")
        print(f"  Visible panels ({len(page_state)}):")
        for p in page_state:
            first_line = p['text'].split('\n')[0][:50]
            print(f"    ({p['x']},{p['y']}) {p['w']}x{p['h']} cls={p['cls'][:30]} '{first_line}'")

    # ================================================================
    # TASK 3: Enhance & Upscale Sidebar (extended detection)
    # ================================================================
    print("\n" + "=" * 70)
    print("TASK 3: Enhance & Upscale Sidebar (extended detection)")
    print("=" * 70)

    close_all(page)
    page.wait_for_timeout(500)

    page.mouse.click(40, 630)
    page.wait_for_timeout(3000)

    eu_panel = get_any_panel(page)
    print(f"  Panel detected: {json.dumps(eu_panel)}")

    screenshot(page, "p311_enhance_attempt")

    if eu_panel.get('type') == 'none':
        page_state2 = page.evaluate("""() => {
            var newPanels = [];
            for (var el of document.querySelectorAll('[class*="panel"], [class*="editor"], [class*="config"], [class*="enhance"], [class*="upscale"]')) {
                if (el.offsetHeight > 100 && el.offsetWidth > 100) {
                    var text = (el.innerText || '').trim();
                    if (text.length > 10) {
                        var rect = el.getBoundingClientRect();
                        newPanels.push({
                            cls: (typeof el.className === 'string') ? el.className.substring(0, 60) : '',
                            text: text.substring(0, 100),
                            x: Math.round(rect.x),
                            y: Math.round(rect.y),
                            w: Math.round(rect.width),
                            h: Math.round(rect.height)
                        });
                    }
                }
            }
            return newPanels.slice(0, 10);
        }""")
        print(f"  Visible panels ({len(page_state2)}):")
        for p in page_state2:
            first_line = p['text'].split('\n')[0][:50]
            print(f"    ({p['x']},{p['y']}) {p['w']}x{p['h']} cls={p['cls'][:30]} '{first_line}'")

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
    print("EXPLORATION PART 31 COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
