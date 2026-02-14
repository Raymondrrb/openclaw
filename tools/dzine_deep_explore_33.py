#!/usr/bin/env python3
"""Dzine Deep Exploration Part 33 — Wan 2.1 via Results Chain + Full Model List.

The correct workflow for AI Video is:
1. Generate image with Txt2Img (or have existing result)
2. Click "AI Video" action on the result image
3. This opens AI Video panel with start frame PRE-SET
4. Select Wan 2.1, then Generate

Part 33:
1. Switch to Wan 2.1 model first
2. Use existing results to chain into AI Video
3. Generate with Wan 2.1 (6 credits)
4. Capture complete model list from popup (all 34+ models with pricing)
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
    print("DZINE DEEP EXPLORATION PART 33")
    print("Wan 2.1 via Results Chain + Full Model Catalog")
    print("=" * 70)

    browser, context, _, _pw = connect_or_launch()
    page = context.pages[0]
    print(f"Connected. URL: {page.url}")

    if "dzine.ai/canvas" not in page.url:
        page.goto("https://www.dzine.ai/canvas?id=19861203")
        page.wait_for_timeout(6000)

    close_everything(page)
    page.wait_for_timeout(500)

    credits = page.evaluate("""() => {
        for (var el of document.querySelectorAll('*')) {
            var t = (el.innerText || '').trim();
            if (t.match(/^Unlimited\\s*\\/\\s*[\\d.,]+$/)) return t;
        }
        return 'unknown';
    }""")
    print(f"  Credits: {credits}")

    # ================================================================
    # TASK 1: First set Wan 2.1 as default AI Video model
    # ================================================================
    print("\n" + "=" * 70)
    print("TASK 1: Pre-set Wan 2.1 as AI Video model")
    print("=" * 70)

    page.mouse.click(40, 361)  # AI Video sidebar
    page.wait_for_timeout(2500)

    current = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return '';
        var sel = panel.querySelector('.custom-selector-wrapper');
        return sel ? (sel.innerText || '').trim().split('\\n')[0] : '';
    }""")
    print(f"  Current model: {current}")

    if 'Wan' not in current:
        # Open popup and select Wan 2.1
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
                print("  Wan 2.1 selected!")
            else:
                print("  Wan 2.1 not found in popup")
    else:
        print("  Already on Wan 2.1")

    close_everything(page)
    page.wait_for_timeout(500)

    # ================================================================
    # TASK 2: Chain from Results → AI Video
    # ================================================================
    print("\n" + "=" * 70)
    print("TASK 2: Results → AI Video chain")
    print("=" * 70)

    # Find the AI Video action buttons in the results panel
    # The results panel is on the right side
    # From screenshots: "Image-to-Image" section has results with action buttons
    # Each result has: Variation, Chat Editor, Image Editor, AI Video, Lip Sync, etc.

    # First find an AI Video action button in the results
    # Scroll results to find one
    ai_video_btns = page.evaluate("""() => {
        var btns = [];
        // Look in the results panel area (right side, x > 500)
        for (var el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            if (text === 'AI Video' && el.offsetHeight > 0 && el.offsetHeight < 40) {
                var rect = el.getBoundingClientRect();
                if (rect.x > 500 && rect.y > 0 && rect.y < window.innerHeight) {
                    btns.push({
                        text: text,
                        x: Math.round(rect.x + rect.width/2),
                        y: Math.round(rect.y + rect.height/2),
                        w: Math.round(rect.width),
                        h: Math.round(rect.height)
                    });
                }
            }
        }
        return btns;
    }""")
    print(f"  AI Video action buttons ({len(ai_video_btns)}):")
    for b in ai_video_btns:
        print(f"    ({b['x']}, {b['y']}) {b['w']}x{b['h']}")

    if ai_video_btns:
        btn = ai_video_btns[0]
        print(f"\n  Clicking AI Video at ({btn['x']}, {btn['y']})...")
        page.mouse.click(btn['x'], btn['y'])
        page.wait_for_timeout(3000)

        # Check if AI Video panel opened with start frame set
        panel_state = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return {noPanel: true};
            var text = (panel.innerText || '').substring(0, 50).trim();
            var sel = panel.querySelector('.custom-selector-wrapper');
            var model = sel ? (sel.innerText || '').trim().split('\\n')[0] : '';
            var genBtn = null;
            for (var btn of panel.querySelectorAll('button')) {
                if ((btn.innerText || '').includes('Generate')) {
                    genBtn = {text: (btn.innerText || '').trim(), disabled: btn.disabled};
                }
            }
            var warning = '';
            for (var el of panel.querySelectorAll('*')) {
                var t = (el.innerText || '').trim();
                if ((t.includes('upload') || t.includes('key frame') || t.includes('Please')) && el.offsetHeight > 0 && el.offsetHeight < 30) {
                    warning = t; break;
                }
            }
            var thumb = panel.querySelector('.frame-thumb img, .pick-image img');
            return {panel: text, model: model, genBtn: genBtn, warning: warning, hasThumb: !!thumb};
        }""")
        print(f"  Panel state: {json.dumps(panel_state)}")
        screenshot(page, "p331_ai_video_chained")

        if panel_state.get('genBtn') and not panel_state['genBtn'].get('disabled') and not panel_state.get('warning'):
            # Check if model is Wan 2.1
            if 'Wan' not in panel_state.get('model', ''):
                print("  Model reverted! Switching to Wan 2.1 again...")
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

            # Now generate!
            print("\n  >>> GENERATING Wan 2.1 VIDEO (6 credits, ~60s)...")
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
                print("  Clicked Generate.")

                # Wait for generation (~60s for Wan 2.1)
                for i in range(15):
                    page.wait_for_timeout(10000)
                    secs = (i + 1) * 10

                    # Check for new video or completion
                    status = page.evaluate("""() => {
                        // Check results panel for videos
                        var resultPanel = document.querySelector('.result-panel, [class*="result"]');
                        var videos = [];
                        if (resultPanel) {
                            for (var v of resultPanel.querySelectorAll('video')) {
                                if (v.src) videos.push(v.src.substring(0, 60));
                            }
                        }
                        // Check if any generation is in progress (loading spinners)
                        var generating = false;
                        for (var el of document.querySelectorAll('[class*="loading"], [class*="spin"], [class*="progress"]')) {
                            if (el.offsetHeight > 0 && el.offsetWidth > 0) generating = true;
                        }
                        return {videos: videos.length, generating: generating};
                    }""")
                    print(f"  [{secs}s] videos={status.get('videos', 0)} generating={status.get('generating', False)}")

                    if secs >= 60 and not status.get('generating', True):
                        break

                screenshot(page, "p331_wan21_result")

                # Check for new video result
                video_result = page.evaluate("""() => {
                    // Look for the most recent video in results
                    var allVideos = document.querySelectorAll('video');
                    var latestSrc = '';
                    for (var v of allVideos) {
                        if (v.src && v.src.includes('static.dzine.ai')) {
                            latestSrc = v.src;
                        }
                    }
                    return latestSrc;
                }""")
                print(f"  Latest video: {video_result[:80] if video_result else 'none'}")

                if video_result:
                    # Download
                    save_path = "/Users/ray/Documents/openclaw/artifacts/dzine/wan21_chain_test.mp4"
                    os.makedirs(os.path.dirname(save_path), exist_ok=True)
                    b64 = page.evaluate("""(url) => {
                        return fetch(url).then(r => r.blob()).then(b => new Promise((resolve) => {
                            var reader = new FileReader();
                            reader.onload = () => resolve(reader.result);
                            reader.readAsDataURL(b);
                        })).catch(e => 'error: ' + e.message);
                    }""", video_result)
                    if b64 and not b64.startswith('error:'):
                        data = b64.split(',', 1)[1]
                        with open(save_path, 'wb') as f:
                            f.write(base64.b64decode(data))
                        fsize = os.path.getsize(save_path)
                        print(f"  Video saved: {save_path} ({fsize} bytes)")
                    else:
                        print(f"  Download error: {(b64 or '')[:80]}")
        else:
            print("  Generate not ready or warning present")
            print(f"  Warning: {panel_state.get('warning')}")
            # The action might have opened the start frame picker instead
            # Check for pick dialog
            has_dialog = page.evaluate("""() => {
                var pp = document.querySelector('.pick-panel');
                return pp && pp.offsetHeight > 0;
            }""")
            if has_dialog:
                print("  Pick dialog opened. Selecting canvas image...")
                # Find canvas image in dialog
                canvas = page.evaluate("""() => {
                    var pp = document.querySelector('.pick-panel');
                    if (!pp) return null;
                    var imgs = pp.querySelectorAll('img');
                    for (var img of imgs) {
                        if (img.offsetHeight > 30 && img.offsetWidth > 30) {
                            var rect = img.getBoundingClientRect();
                            return {x: Math.round(rect.x + rect.width/2), y: Math.round(rect.y + rect.height/2)};
                        }
                    }
                    return null;
                }""")
                if canvas:
                    page.mouse.click(canvas['x'], canvas['y'])
                    page.wait_for_timeout(2000)
    else:
        print("  No AI Video action buttons visible. Scrolling results...")
        # Try scrolling the results panel to find AI Video buttons
        page.evaluate("""() => {
            var rp = document.querySelector('.result-panel, [class*="result"]');
            if (rp && rp.scrollHeight > rp.clientHeight) {
                rp.scrollTop = rp.scrollHeight / 3;
            }
        }""")
        page.wait_for_timeout(1000)

        # Check for Image-to-Image results which have more action buttons
        img_results = page.evaluate("""() => {
            var sections = [];
            for (var el of document.querySelectorAll('[class*="section-title"], [class*="result-group"]')) {
                var text = (el.innerText || '').trim();
                if (text) sections.push(text.substring(0, 40));
            }
            // Count all result thumbnails
            var thumbs = document.querySelectorAll('[class*="result"] img, [class*="thumb"] img');
            return {sections: sections, thumbnailCount: thumbs.length};
        }""")
        print(f"  Result sections: {json.dumps(img_results)}")

        # Find numbered action rows (1, 2, 3, 4 buttons)
        numbered_btns = page.evaluate("""() => {
            var rows = [];
            for (var el of document.querySelectorAll('[class*="action"], [class*="btn-row"], [class*="btn-list"]')) {
                var text = (el.innerText || '').trim();
                if (text.includes('AI Video')) {
                    var rect = el.getBoundingClientRect();
                    rows.push({text: text.substring(0, 80), x: Math.round(rect.x), y: Math.round(rect.y)});
                }
            }
            return rows;
        }""")
        print(f"  Action rows with AI Video: {json.dumps(numbered_btns)}")
        screenshot(page, "p331_results_scroll")

    # ================================================================
    # TASK 3: Final credits check
    # ================================================================
    print("\n" + "=" * 70)
    print("Final Credits")
    print("=" * 70)
    credits_final = page.evaluate("""() => {
        for (var el of document.querySelectorAll('*')) {
            var t = (el.innerText || '').trim();
            if (t.match(/^Unlimited\\s*\\/\\s*[\\d.,]+$/)) return t;
        }
        return 'unknown';
    }""")
    print(f"  Credits: {credits_final}")

    print("\n" + "=" * 70)
    print("EXPLORATION PART 33 COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
