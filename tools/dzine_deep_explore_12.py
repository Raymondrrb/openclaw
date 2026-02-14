#!/usr/bin/env python3
"""Dzine Deep Exploration Part 12 — Minimax Hailuo 2.3 test + Video Download + Storyboard.

1. Generate a product video with Hailuo 2.3 (user's production model)
2. Download a completed video
3. Test Lip Sync with a result image
4. Test Storyboard generation
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


def count_results(page):
    return page.evaluate("""() => {
        return document.querySelectorAll('img[src*="static.dzine.ai/stylar_product/p/"]').length;
    }""")


def get_video_credits(page):
    return page.evaluate("""() => {
        var spans = document.querySelectorAll('span');
        for (var s of spans) {
            var text = (s.innerText || '').trim();
            var rect = s.getBoundingClientRect();
            if (rect.y < 40 && rect.y > 5 && /^[0-9]+\\.[0-9]+$/.test(text)) {
                return text;
            }
        }
        return '';
    }""")


def close_dialogs(page):
    page.evaluate("""() => {
        for (var i = 0; i < 5; i++) {
            for (var text of ['Not now', 'Close', 'Never show again', 'Got it', 'Skip', 'Later']) {
                for (var btn of document.querySelectorAll('button')) {
                    if ((btn.innerText || '').trim() === text && btn.offsetHeight > 0) btn.click();
                }
            }
        }
    }""")


def main():
    print("=" * 70)
    print("DZINE DEEP EXPLORATION PART 12")
    print("Hailuo 2.3 + Video Download + Lip Sync + Storyboard")
    print("=" * 70)

    browser, context, _, _pw = connect_or_launch()
    page = context.pages[0]
    print(f"Connected. URL: {page.url}")

    if "dzine.ai/canvas" not in page.url:
        page.goto("https://www.dzine.ai/canvas?id=19861203")
        page.wait_for_timeout(5000)
        close_dialogs(page)
        page.wait_for_timeout(1000)

    credits_before = get_video_credits(page)
    print(f"  Video credits: {credits_before}")

    # ================================================================
    # TASK 1: Download Existing Wan 2.1 Video
    # ================================================================
    print("\n" + "=" * 70)
    print("TASK 1: Download Existing Video")
    print("=" * 70)

    # Switch to Results tab
    page.evaluate("""() => {
        for (var el of document.querySelectorAll('[class*="header-item"]')) {
            if ((el.innerText || '').includes('Result')) { el.click(); return; }
        }
    }""")
    page.wait_for_timeout(1000)

    # Find the completed video and its Download button
    download_info = page.evaluate("""() => {
        var items = document.querySelectorAll('.result-item.image-to-video-result.completed');
        if (items.length === 0) return {found: false};
        var item = items[0];
        var rect = item.getBoundingClientRect();

        // Find Download button
        var downloadBtn = null;
        for (var btn of item.querySelectorAll('button, a, [role="button"]')) {
            var text = (btn.innerText || '').trim();
            if (text === 'Download' || text.includes('Download')) {
                var br = btn.getBoundingClientRect();
                if (br.height > 0) {
                    downloadBtn = {
                        text: text,
                        x: Math.round(br.x),
                        y: Math.round(br.y),
                        w: Math.round(br.width),
                        h: Math.round(br.height),
                        tag: btn.tagName
                    };
                    break;
                }
            }
        }

        // Find video URL
        var video = item.querySelector('video');
        var source = video ? video.querySelector('source') : null;
        var videoUrl = source ? source.src : (video ? video.src : '');

        // Map all buttons in the video result
        var buttons = [];
        for (var btn of item.querySelectorAll('button, [role="button"]')) {
            var br = btn.getBoundingClientRect();
            if (br.height > 0) {
                buttons.push({
                    text: (btn.innerText || '').trim().substring(0, 30),
                    x: Math.round(br.x),
                    y: Math.round(br.y)
                });
            }
        }

        return {
            found: true,
            y: Math.round(rect.y),
            h: Math.round(rect.height),
            videoUrl: videoUrl.substring(0, 150),
            downloadBtn: downloadBtn,
            buttons: buttons
        };
    }""")

    print(f"  Video result: {json.dumps(download_info, indent=2)}")

    if download_info.get("downloadBtn"):
        db = download_info["downloadBtn"]
        print(f"  Download button at ({db['x']},{db['y']}) {db['w']}x{db['h']}")

        # Scroll to make it visible if needed
        # The result might need scrolling in the results panel
        page.evaluate("""() => {
            var items = document.querySelectorAll('.result-item.image-to-video-result.completed');
            if (items[0]) items[0].scrollIntoView({block: 'center'});
        }""")
        page.wait_for_timeout(500)

        # Try to download
        try:
            with page.expect_download(timeout=15000) as dl_info:
                page.mouse.click(db["x"] + db["w"]//2, db["y"] + db["h"]//2)
            download = dl_info.value
            save_path = f"/Users/ray/Downloads/dzine_video_wan21.mp4"
            download.save_as(save_path)
            print(f"  Downloaded to: {save_path}")
        except Exception as e:
            print(f"  Download attempt: {e}")
            # The download might open in new tab or use direct URL
            if download_info.get("videoUrl"):
                video_url = download_info["videoUrl"]
                print(f"  Direct video URL: {video_url}")
                print("  (Can download directly from this URL)")

    screenshot(page, "p183_video_result")

    # ================================================================
    # TASK 2: Minimax Hailuo 2.3 Video Generation
    # ================================================================
    print("\n" + "=" * 70)
    print("TASK 2: Minimax Hailuo 2.3 Video Test")
    print("=" * 70)

    credits_check = get_video_credits(page)
    print(f"  Credits: {credits_check}")

    # Use Results panel action to populate start frame and open AI Video
    print("  Using result image as start frame...")
    clicked = page.evaluate("""() => {
        var containers = document.querySelectorAll('.btn-container');
        for (var c of containers) {
            var parent = c.parentElement;
            var parentText = (parent ? parent.innerText || '' : '').trim();
            if (parentText.startsWith('AI Video')) {
                var rect = c.getBoundingClientRect();
                if (rect.height > 0 && rect.y > 0 && rect.y < 900) {
                    var btns = c.querySelectorAll('.btn');
                    if (btns.length > 0) { btns[0].click(); return true; }
                }
            }
        }
        return false;
    }""")
    print(f"  AI Video action clicked: {clicked}")
    page.wait_for_timeout(3000)

    # Verify AI Video panel
    panel_ok = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return false;
        var cls = (typeof panel.className === 'string') ? panel.className : '';
        return cls.includes('ai-video');
    }""")
    print(f"  AI Video panel open: {panel_ok}")

    if panel_ok:
        # Select Minimax Hailuo 2.3 model
        print("  Selecting Minimax Hailuo 2.3...")

        # Open model selector
        page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return;
            var sel = panel.querySelector('.custom-selector-wrapper');
            if (sel) sel.click();
        }""")
        page.wait_for_timeout(1500)

        # Click Minimax Hailuo 2.3
        model_clicked = page.evaluate("""() => {
            var popup = document.querySelector('.selector-panel');
            if (!popup) {
                // Try finding it in the DOM
                for (var el of document.querySelectorAll('*')) {
                    var text = (el.innerText || '').trim();
                    if (text.startsWith('Minimax Hailuo 2.3') && el.offsetHeight > 0 && el.offsetHeight < 80) {
                        el.click();
                        return {clicked: true, text: text.substring(0, 40)};
                    }
                }
                return {clicked: false, reason: 'no popup or element'};
            }
            // Find in popup
            for (var el of popup.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                if (text.startsWith('Minimax Hailuo 2.3') && el.offsetHeight > 0 && el.offsetHeight < 80) {
                    el.click();
                    return {clicked: true, text: text.substring(0, 40)};
                }
            }
            return {clicked: false, reason: 'not found in popup'};
        }""")
        print(f"  Model selection: {json.dumps(model_clicked)}")
        page.wait_for_timeout(1500)

        # Verify model
        model_name = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return '';
            var sel = panel.querySelector('.custom-selector-wrapper');
            return sel ? (sel.innerText || '').trim().split('\\n')[0] : '';
        }""")
        print(f"  Selected model: {model_name}")

        # Check the model's settings
        model_settings = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return {};
            var text = panel.innerText || '';
            // Extract resolution, duration
            var settingsLine = '';
            for (var el of panel.querySelectorAll('*')) {
                var t = (el.innerText || '').trim();
                if (t.includes('720p') || t.includes('1080p')) {
                    var r = el.getBoundingClientRect();
                    if (r.height < 30 && r.height > 0) {
                        settingsLine = t;
                        break;
                    }
                }
            }
            // Get generate button credits
            var genBtn = panel.querySelector('.generative');
            var genText = genBtn ? (genBtn.innerText || '').trim() : '';
            return {
                settings: settingsLine,
                genText: genText,
                hasFrame: !!panel.querySelector('img[src*="static.dzine.ai"]')
            };
        }""")
        print(f"  Settings: {json.dumps(model_settings)}")

        # Fill video prompt (calm product showcase for 40+ audience)
        video_prompt = "Premium headphones resting on wooden desk surface, warm natural light from window, subtle dust particles in sunlight, calm and static product shot"

        page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return;
            var ta = panel.querySelector('textarea');
            if (ta) { ta.focus(); ta.click(); }
        }""")
        page.wait_for_timeout(300)
        page.keyboard.press("Meta+a")
        page.wait_for_timeout(200)
        page.keyboard.press("Delete")
        page.wait_for_timeout(200)
        page.keyboard.type(video_prompt, delay=2)
        page.wait_for_timeout(500)
        print(f"  Prompt filled ({len(video_prompt)} chars)")

        screenshot(page, "p183_hailuo_ready")

        # Check if we want to generate (costs 56-98 credits from 8.844 remaining)
        gen_state = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return {};
            var btn = panel.querySelector('.generative');
            if (!btn) return {};
            var cls = (typeof btn.className === 'string') ? btn.className : '';
            return {
                text: (btn.innerText || '').trim(),
                ready: cls.includes('ready'),
                disabled: btn.disabled
            };
        }""")
        print(f"  Generate: {json.dumps(gen_state)}")

        # Check credit cost before generating
        credit_cost = gen_state.get("text", "").replace("Generate", "").strip()
        print(f"  Credit cost: {credit_cost}")

        # ONLY generate if we have enough credits and cost is reasonable
        # User said economize while learning, but also wants to learn Hailuo 2.3
        current_credits = float(credits_check) if credits_check else 0
        try:
            cost_num = int(credit_cost)
        except (ValueError, TypeError):
            cost_num = 100  # assume high if can't parse

        if gen_state.get("ready") and current_credits >= cost_num:
            print(f"\n  >>> GENERATING (Hailuo 2.3, {cost_num} credits) <<<")
            print(f"  Credits: {current_credits} -> ~{current_credits - cost_num}")

            page.evaluate("""() => {
                var panel = document.querySelector('.c-gen-config.show');
                var btn = panel.querySelector('.generative.ready');
                if (btn && !btn.disabled) btn.click();
            }""")

            # Poll (Hailuo videos take 5-10 minutes)
            start = time.time()
            while time.time() - start < 600:  # 10 minute timeout
                page.wait_for_timeout(10000)
                elapsed = int(time.time() - start)

                # Check credits change
                new_credits = get_video_credits(page)
                if new_credits != credits_check:
                    print(f"  Credits changed: {credits_check} -> {new_credits} ({elapsed}s)")

                # Check for new video results
                video_count = page.evaluate("""() => {
                    return document.querySelectorAll('.result-item.image-to-video-result.completed').length;
                }""")

                # Check panel state
                panel_text = page.evaluate("""() => {
                    var panel = document.querySelector('.c-gen-config.show');
                    if (!panel) return '';
                    var text = panel.innerText || '';
                    if (text.includes('Waiting')) return 'waiting';
                    if (text.includes('Queue')) return 'queued';
                    if (text.includes('Generating')) return 'generating';
                    var match = text.match(/([0-9]{1,3})%/);
                    if (match) return match[0];
                    return '';
                }""")
                if panel_text:
                    print(f"    Status: {panel_text} ({elapsed}s)")

                if elapsed > 30 and elapsed % 60 == 0:
                    print(f"    Waiting... ({elapsed}s, credits: {new_credits})")

                # Check if gen button is back to ready (generation submitted, now waiting)
                gen_ready = page.evaluate("""() => {
                    var panel = document.querySelector('.c-gen-config.show');
                    if (!panel) return false;
                    var btn = panel.querySelector('.generative.ready');
                    return btn && !btn.disabled;
                }""")

                # If button is ready again and credits changed, generation was submitted
                if gen_ready and new_credits != credits_check and elapsed > 15:
                    print(f"\n  Video submitted! Credits: {credits_check} -> {new_credits}")
                    print(f"  Video is processing in background (5-10 minutes)")
                    print(f"  Will check result later.")
                    break

            screenshot(page, "p183_hailuo_submitted")
        else:
            if current_credits < cost_num:
                print(f"  SKIPPING — not enough credits ({current_credits} < {cost_num})")
            else:
                print(f"  SKIPPING — generate button not ready")

    # ================================================================
    # TASK 3: Explore Storyboard Panel
    # ================================================================
    print("\n" + "=" * 70)
    print("TASK 3: Storyboard Panel")
    print("=" * 70)

    # Reload to clear panels
    page.goto("https://www.dzine.ai/canvas?id=19861203")
    page.wait_for_timeout(5000)
    close_dialogs(page)
    page.wait_for_timeout(1000)

    # Click Storyboard sidebar
    print("  Opening Storyboard panel...")
    page.mouse.click(40, 766)
    page.wait_for_timeout(2500)

    storyboard = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return {found: false};
        var cls = (typeof panel.className === 'string') ? panel.className : '';

        var buttons = [];
        for (var btn of panel.querySelectorAll('button, [role="button"]')) {
            var rect = btn.getBoundingClientRect();
            if (rect.height > 0) {
                var bc = (typeof btn.className === 'string') ? btn.className : '';
                buttons.push({
                    text: (btn.innerText || '').trim().substring(0, 30),
                    class: bc.substring(0, 40),
                    x: Math.round(rect.x),
                    y: Math.round(rect.y),
                    w: Math.round(rect.width),
                    selected: bc.includes('selected')
                });
            }
        }

        var uploads = [];
        for (var u of panel.querySelectorAll('.pick-image, .upload-image-btn, [class*="upload"]')) {
            var ur = u.getBoundingClientRect();
            if (ur.height > 0) {
                uploads.push({
                    text: (u.innerText || '').trim().substring(0, 40),
                    x: Math.round(ur.x),
                    y: Math.round(ur.y)
                });
            }
        }

        var textareas = [];
        for (var ta of panel.querySelectorAll('textarea, [contenteditable="true"]')) {
            var tr = ta.getBoundingClientRect();
            if (tr.height > 0) {
                textareas.push({
                    placeholder: (ta.placeholder || ta.getAttribute('data-placeholder') || '').substring(0, 50),
                    maxLen: ta.maxLength || 0,
                    x: Math.round(tr.x),
                    y: Math.round(tr.y)
                });
            }
        }

        return {
            found: true,
            class: cls.substring(0, 80),
            text: (panel.innerText || '').substring(0, 500),
            buttons: buttons,
            uploads: uploads,
            textareas: textareas
        };
    }""")

    if storyboard.get("found"):
        print(f"  Panel class: {storyboard['class']}")
        print(f"\n  Panel text:")
        for line in storyboard["text"].split("\n")[:15]:
            line = line.strip()
            if line:
                print(f"    > {line[:60]}")

        print(f"\n  Buttons ({len(storyboard['buttons'])}):")
        for b in storyboard["buttons"]:
            sel = " [SELECTED]" if b.get("selected") else ""
            print(f"    '{b['text'][:25]}' at ({b['x']},{b['y']}) w={b['w']}{sel}")

        print(f"\n  Uploads ({len(storyboard['uploads'])}):")
        for u in storyboard["uploads"]:
            print(f"    '{u['text'][:30]}' at ({u['x']},{u['y']})")

        print(f"\n  Textareas ({len(storyboard['textareas'])}):")
        for ta in storyboard["textareas"]:
            print(f"    placeholder='{ta['placeholder']}' maxLen={ta['maxLen']}")

    screenshot(page, "p183_storyboard")

    # ================================================================
    # TASK 4: Test Nano Banana Pro with 16:9 aspect for video frames
    # ================================================================
    print("\n" + "=" * 70)
    print("TASK 4: Nano Banana Pro 16:9 Product Image (video frame)")
    print("=" * 70)

    # Switch to Txt2Img
    page.mouse.click(40, 197)
    page.wait_for_timeout(2500)

    # Check model
    model = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return '';
        var sn = panel.querySelector('.style-name');
        return sn ? (sn.innerText || '').trim() : '';
    }""")
    print(f"  Current model: {model}")

    # If not Nano Banana Pro, select it
    if "Nano Banana" not in model:
        print("  Selecting Nano Banana Pro...")
        page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            var btn = panel.querySelector('button.style');
            if (btn) btn.click();
        }""")
        page.wait_for_timeout(2000)

        # Find and click Nano Banana Pro
        page.evaluate("""() => {
            var picker = document.querySelector('.style-list-panel');
            if (!picker) return;
            for (var el of picker.querySelectorAll('span, div, p')) {
                if ((el.innerText || '').trim() === 'Nano Banana Pro') {
                    var r = el.getBoundingClientRect();
                    if (r.height > 0 && r.height < 30) {
                        // Click parent card (thumbnail above label)
                        var parent = el.parentElement;
                        if (parent) parent.click();
                        return;
                    }
                }
            }
        }""")
        page.wait_for_timeout(1000)
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)

        model = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return '';
            var sn = panel.querySelector('.style-name');
            return sn ? (sn.innerText || '').trim() : '';
        }""")
        print(f"  Model: {model}")

    # Set 16:9 aspect ratio (for video frame use)
    page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return;
        for (var btn of panel.querySelectorAll('button, [role="button"]')) {
            var text = (btn.innerText || '').trim();
            if (text === '16:9') {
                btn.click();
                return;
            }
        }
    }""")
    page.wait_for_timeout(300)

    # Fill product prompt (trust-focused, 40+ audience style)
    prompt = "Premium wireless headphones sitting on a clean wooden desk in a warm, naturally lit living room. Side profile showing ear cup detail and headband. Soft afternoon sunlight from a window, shallow depth of field. No text, no watermarks, photorealistic."

    page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return;
        var ta = panel.querySelector('textarea');
        if (ta) { ta.focus(); ta.click(); }
    }""")
    page.wait_for_timeout(300)
    page.keyboard.press("Meta+a")
    page.wait_for_timeout(200)
    page.keyboard.press("Delete")
    page.wait_for_timeout(200)
    page.keyboard.type(prompt, delay=2)
    page.wait_for_timeout(500)
    print(f"  Prompt filled ({len(prompt)} chars)")

    # Check aspect ratio and resolution
    panel_info = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return {};
        var text = panel.innerText || '';
        var aspectMatch = text.match(/(\\d+)x(\\d+)/);
        var genBtn = panel.querySelector('.generative');
        return {
            aspect: aspectMatch ? aspectMatch[0] : '',
            genText: genBtn ? (genBtn.innerText || '').trim() : ''
        };
    }""")
    print(f"  Resolution: {panel_info.get('aspect', 'unknown')}")
    print(f"  Generate: {panel_info.get('genText', 'unknown')}")

    # Generate
    before = count_results(page)
    page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return;
        var btn = panel.querySelector('.generative.ready');
        if (btn && !btn.disabled) btn.click();
    }""")
    print("  Generating 16:9 product image...")

    start = time.time()
    while time.time() - start < 120:
        page.wait_for_timeout(3000)
        elapsed = int(time.time() - start)

        after = count_results(page)
        if after > before:
            print(f"\n  COMPLETE! ({elapsed}s, +{after-before} images)")
            break

        progress = page.evaluate("""() => {
            for (var el of document.querySelectorAll('*')) {
                var txt = (el.innerText || '').trim();
                if (/^[0-9]{1,3}%$/.test(txt)) {
                    var r = el.getBoundingClientRect();
                    if (r.x > 1000) return txt;
                }
            }
            return '';
        }""")
        if progress:
            print(f"    {progress} ({elapsed}s)")
    else:
        final = count_results(page)
        print(f"\n  TIMEOUT. Results: {before} -> {final}")

    screenshot(page, "p183_nbp_16x9")

    # Get result URLs
    urls = page.evaluate("""() => {
        var imgs = document.querySelectorAll('img[src*="static.dzine.ai/stylar_product/p/"]');
        var urls = [];
        for (var img of imgs) urls.push(img.src);
        return urls.slice(-2);
    }""")
    print("  Result URLs:")
    for u in urls:
        print(f"    {u[:150]}")

    # Final credits
    final_credits = get_video_credits(page)
    print(f"\n  Final video credits: {final_credits}")

    print("\n" + "=" * 70)
    print("EXPLORATION PART 12 COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
