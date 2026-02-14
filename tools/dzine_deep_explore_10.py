#!/usr/bin/env python3
"""Dzine Deep Exploration Part 10 — AI Video Generation (Fixed).

Uses Results panel action to auto-populate start frame, then generates
with Wan 2.1 (6 credits, cheapest). Also tests Nano Banana Pro Txt2Img.
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


def count_videos(page):
    return page.evaluate("""() => {
        var videos = document.querySelectorAll('.result-item.image-to-video-result, video[src*="static.dzine.ai"]');
        return videos.length;
    }""")


def get_video_urls(page):
    return page.evaluate("""() => {
        var urls = [];
        var videos = document.querySelectorAll('video source, video[src]');
        for (var v of videos) {
            var src = v.src || v.getAttribute('src') || '';
            if (src && src.includes('static.dzine.ai')) urls.push(src);
        }
        // Also check for video result items
        var items = document.querySelectorAll('.result-item.image-to-video-result img, .result-item video');
        for (var item of items) {
            var s = item.src || '';
            if (s) urls.push(s);
        }
        return urls;
    }""")


def get_credits(page):
    return page.evaluate("""() => {
        var spans = document.querySelectorAll('span.txt, .credit-text, [class*="credit"]');
        var results = [];
        for (var s of spans) {
            var rect = s.getBoundingClientRect();
            if (rect.y < 50 && rect.height > 0) {
                results.push({
                    text: (s.innerText || '').trim(),
                    x: Math.round(rect.x),
                    y: Math.round(rect.y)
                });
            }
        }
        // Also check panel text
        var panel = document.querySelector('.c-gen-config.show');
        if (panel) {
            var text = panel.innerText || '';
            var match = text.match(/([0-9.]+)\\s*video credits/);
            if (match) results.push({text: match[1] + ' video credits', x: 0, y: 0});
        }
        return results;
    }""")


def main():
    print("=" * 70)
    print("DZINE DEEP EXPLORATION PART 10 — AI Video Gen + Nano Banana Pro")
    print("=" * 70)

    browser, context, _, _pw = connect_or_launch()
    page = context.pages[0]
    print(f"Connected. URL: {page.url}")

    if "dzine.ai/canvas" not in page.url:
        page.goto("https://www.dzine.ai/canvas?id=19861203")
        page.wait_for_timeout(5000)

    # ================================================================
    # TASK 1: AI Video Generation via Results Panel Action
    # ================================================================
    print("\n" + "=" * 70)
    print("TASK 1: AI Video Generation (Wan 2.1, 6 credits)")
    print("=" * 70)

    # Check credits before
    credits_before = get_credits(page)
    print(f"  Credits before: {json.dumps(credits_before)}")

    # Count existing videos
    videos_before = count_videos(page)
    results_before = count_results(page)
    print(f"  Videos before: {videos_before}, Results before: {results_before}")

    video_urls_before = get_video_urls(page)
    print(f"  Video URLs before: {len(video_urls_before)}")

    # Click AI Video [1] button from results to auto-populate start frame
    print("\n  Step 1: Clicking AI Video [1] from Results panel...")
    clicked = page.evaluate("""() => {
        var containers = document.querySelectorAll('.btn-container');
        for (var c of containers) {
            var parent = c.parentElement;
            var parentText = (parent ? parent.innerText || '' : '').trim();
            if (parentText.startsWith('AI Video')) {
                var rect = c.getBoundingClientRect();
                if (rect.height > 0 && rect.y > 0 && rect.y < 900) {
                    var btns = c.querySelectorAll('.btn');
                    if (btns.length > 0) {
                        btns[0].click();
                        return true;
                    }
                }
            }
        }
        return false;
    }""")
    print(f"  Clicked: {clicked}")
    page.wait_for_timeout(3000)

    # Verify AI Video panel with start frame
    panel_state = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return {found: false};
        var cls = (typeof panel.className === 'string') ? panel.className : (panel.getAttribute('class') || '');

        var img = panel.querySelector('img');
        var hasFrame = false;
        var frameSrc = '';
        if (img && img.src && img.src.includes('static.dzine.ai')) {
            hasFrame = true;
            frameSrc = img.src.substring(0, 120);
        }

        var genBtn = panel.querySelector('.generative');
        var genCls = genBtn ? ((typeof genBtn.className === 'string') ? genBtn.className : '') : '';
        var genText = genBtn ? (genBtn.innerText || '').trim() : '';

        return {
            found: true,
            isAiVideo: cls.includes('ai-video'),
            hasFrame: hasFrame,
            frameSrc: frameSrc,
            genReady: genCls.includes('ready'),
            genDisabled: genBtn ? genBtn.disabled : true,
            genText: genText
        };
    }""")
    print(f"  Panel: {json.dumps(panel_state)}")

    if not panel_state.get("hasFrame"):
        print("  ERROR: No start frame! Aborting video gen.")
        return

    if not panel_state.get("genReady"):
        print("  ERROR: Generate button not ready! Aborting.")
        return

    # Step 2: Fill video prompt
    print("\n  Step 2: Filling video prompt...")
    video_prompt = "Slow dolly zoom into premium headphones, soft studio lighting, subtle light rays catching the metallic finish, smooth cinematic motion"

    page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return false;
        var ta = panel.querySelector('textarea');
        if (ta) { ta.focus(); ta.click(); return true; }
        return false;
    }""")
    page.wait_for_timeout(300)
    page.keyboard.press("Meta+a")
    page.wait_for_timeout(200)
    page.keyboard.press("Delete")
    page.wait_for_timeout(200)
    page.keyboard.type(video_prompt, delay=2)
    page.wait_for_timeout(500)

    # Verify prompt
    filled = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return '';
        var ta = panel.querySelector('textarea');
        return ta ? ta.value : '';
    }""")
    print(f"  Prompt: '{filled[:80]}...' ({len(filled)} chars)")

    # Step 3: Verify model is Wan 2.1
    model = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return '';
        var sel = panel.querySelector('.custom-selector-wrapper');
        return sel ? (sel.innerText || '').trim() : '';
    }""")
    print(f"  Model: {model}")

    screenshot(page, "p180_ai_video_ready_to_gen")

    # Step 4: GENERATE!
    print("\n  Step 3: >>> GENERATING AI VIDEO (Wan 2.1, 6 credits) <<<")
    page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return false;
        var btn = panel.querySelector('.generative.ready');
        if (btn && !btn.disabled) { btn.click(); return true; }
        return false;
    }""")

    # Poll for completion (video takes ~60-120s)
    start_time = time.time()
    last_progress = ""
    generated = False

    while time.time() - start_time < 180:  # 3 minute timeout
        page.wait_for_timeout(5000)
        elapsed = int(time.time() - start_time)

        # Check for progress percentage
        progress = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return '';
            var text = panel.innerText || '';
            // Look for percentage in panel text
            var match = text.match(/(\\d{1,3})%/);
            if (match) return match[0];
            // Also check for "Generating" or "Processing" text
            if (text.includes('Generating') || text.includes('Processing')) return 'working...';
            if (text.includes('queued') || text.includes('Queue')) return 'queued...';
            return '';
        }""")

        if progress and progress != last_progress:
            print(f"    Progress: {progress} ({elapsed}s)")
            last_progress = progress

        # Check generate button state (should be disabled during generation)
        gen_state = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return {};
            var btn = panel.querySelector('.generative');
            if (!btn) return {};
            var cls = (typeof btn.className === 'string') ? btn.className : '';
            return {
                text: (btn.innerText || '').trim(),
                disabled: btn.disabled,
                ready: cls.includes('ready'),
                loading: cls.includes('loading') || cls.includes('generating')
            };
        }""")

        # Check if button changed back to ready (generation complete)
        if gen_state.get("ready") and not gen_state.get("loading") and elapsed > 10:
            # Might be done - check for new videos/results
            videos_after = count_videos(page)
            results_after = count_results(page)
            if videos_after > videos_before or results_after > results_before:
                print(f"\n  GENERATION COMPLETE! ({elapsed}s)")
                print(f"    Videos: {videos_before} -> {videos_after}")
                print(f"    Results: {results_before} -> {results_after}")
                generated = True
                break

        # Check for new video URLs
        video_urls_after = get_video_urls(page)
        new_urls = [u for u in video_urls_after if u not in video_urls_before]
        if new_urls:
            print(f"\n  NEW VIDEO DETECTED! ({elapsed}s)")
            for u in new_urls:
                print(f"    {u[:150]}")
            generated = True
            break

        # Check for new result items
        new_items = page.evaluate("""() => {
            var items = document.querySelectorAll('.result-item.image-to-video-result');
            var results = [];
            for (var item of items) {
                var rect = item.getBoundingClientRect();
                if (rect.height > 0) {
                    var video = item.querySelector('video');
                    var img = item.querySelector('img');
                    results.push({
                        hasVideo: !!video,
                        hasImg: !!img,
                        videoSrc: video ? (video.src || '') : '',
                        imgSrc: img ? (img.src || '').substring(0, 120) : ''
                    });
                }
            }
            return results;
        }""")
        if new_items:
            print(f"    Video result items: {len(new_items)}")
            for ni in new_items:
                print(f"      video={ni['hasVideo']} img={ni['hasImg']} src={ni.get('videoSrc', '')[:100]}")

        if elapsed % 30 == 0 and elapsed > 0:
            print(f"    Waiting... ({elapsed}s)")

    if not generated:
        # Final check
        results_after = count_results(page)
        video_urls_after = get_video_urls(page)
        print(f"\n  TIMEOUT after 180s. Results: {results_before} -> {results_after}")
        print(f"  Video URLs: {len(video_urls_before)} -> {len(video_urls_after)}")

    # Screenshot final state
    screenshot(page, "p180_ai_video_result")

    # Check credits after
    credits_after = get_credits(page)
    print(f"  Credits after: {json.dumps(credits_after)}")

    # Extract result details
    print("\n  Extracting video result details...")
    all_video_urls = get_video_urls(page)
    print(f"  All video URLs ({len(all_video_urls)}):")
    for url in all_video_urls:
        print(f"    {url[:150]}")

    # ================================================================
    # TASK 2: Nano Banana Pro Txt2Img Test
    # ================================================================
    print("\n" + "=" * 70)
    print("TASK 2: Nano Banana Pro Txt2Img (User's preferred model)")
    print("=" * 70)

    # Reload page to clear any panels
    page.goto("https://www.dzine.ai/canvas?id=19861203")
    page.wait_for_timeout(5000)

    # Dismiss dialogs
    page.evaluate("""() => {
        for (var i = 0; i < 5; i++) {
            for (var text of ['Not now', 'Close', 'Never show again', 'Got it', 'Skip', 'Later']) {
                for (var btn of document.querySelectorAll('button')) {
                    if ((btn.innerText || '').trim() === text && btn.offsetHeight > 0) btn.click();
                }
            }
        }
    }""")
    page.wait_for_timeout(1000)

    # Open Txt2Img panel
    print("  Opening Txt2Img panel...")
    page.mouse.click(40, 766)  # Storyboard first (distant)
    page.wait_for_timeout(1500)
    page.mouse.click(40, 197)  # Txt2Img
    page.wait_for_timeout(2500)

    # Check current model
    current_model = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return 'NO PANEL';
        var styleName = panel.querySelector('.style-name');
        return styleName ? (styleName.innerText || '').trim() : 'unknown';
    }""")
    print(f"  Current model: {current_model}")

    # Click style button to open style picker
    print("  Opening style picker...")
    page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return false;
        var btn = panel.querySelector('button.style');
        if (btn) { btn.click(); return true; }
        return false;
    }""")
    page.wait_for_timeout(2000)

    # Search for Nano Banana Pro
    print("  Searching for 'Nano Banana Pro'...")
    search_input = page.evaluate("""() => {
        var picker = document.querySelector('.style-list-panel');
        if (!picker) return {found: false, reason: 'no style panel'};
        var input = picker.querySelector('input[type="text"]');
        if (!input) return {found: false, reason: 'no search input'};
        input.focus();
        input.click();
        return {found: true};
    }""")
    print(f"  Search input: {json.dumps(search_input)}")

    if search_input.get("found"):
        page.keyboard.type("Nano Banana Pro", delay=10)
        page.wait_for_timeout(1500)

        # Click Nano Banana Pro from results
        selected = page.evaluate("""() => {
            var picker = document.querySelector('.style-list-panel');
            if (!picker) return {found: false};
            var items = picker.querySelectorAll('[class*="style-item"]');
            for (var item of items) {
                var text = (item.innerText || '').trim();
                if (text.includes('Nano Banana Pro')) {
                    item.click();
                    return {found: true, text: text.substring(0, 50)};
                }
            }
            // Try any visible item
            for (var item of items) {
                var rect = item.getBoundingClientRect();
                if (rect.height > 0) {
                    item.click();
                    return {found: true, text: (item.innerText || '').trim().substring(0, 50), note: 'first visible'};
                }
            }
            return {found: false};
        }""")
        print(f"  Selected: {json.dumps(selected)}")
        page.wait_for_timeout(1000)

    # Close style picker if still open
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)

    # Verify model changed
    new_model = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return 'NO PANEL';
        var styleName = panel.querySelector('.style-name');
        return styleName ? (styleName.innerText || '').trim() : 'unknown';
    }""")
    print(f"  Model after selection: {new_model}")

    # Fill product photography prompt
    product_prompt = "Premium wireless over-ear headphones with brushed aluminum cups and memory foam ear cushions on a clean white studio background. Professional product photography, soft even lighting from three points, razor-sharp focus, color accurate, commercial grade. No text, no watermarks, no people."

    page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return false;
        var ta = panel.querySelector('textarea');
        if (ta) { ta.focus(); ta.click(); return true; }
        return false;
    }""")
    page.wait_for_timeout(300)
    page.keyboard.press("Meta+a")
    page.wait_for_timeout(200)
    page.keyboard.press("Delete")
    page.wait_for_timeout(200)
    page.keyboard.type(product_prompt, delay=2)
    page.wait_for_timeout(500)

    prompt_filled = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return '';
        var ta = panel.querySelector('textarea');
        return ta ? ta.value : '';
    }""")
    print(f"  Prompt filled: '{prompt_filled[:80]}...' ({len(prompt_filled)} chars)")

    # Select Normal mode (4 credits) — user says don't economize
    page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return false;
        for (var btn of panel.querySelectorAll('button.options')) {
            if ((btn.innerText || '').trim() === 'Normal') { btn.click(); return true; }
        }
        return false;
    }""")
    page.wait_for_timeout(300)

    # Check generate button
    gen_info = page.evaluate("""() => {
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
    print(f"  Generate button: {json.dumps(gen_info)}")

    screenshot(page, "p180_nano_banana_ready")

    # Generate!
    if gen_info.get("ready"):
        print("\n  >>> GENERATING (Nano Banana Pro, Normal, 4 credits) <<<")
        before_count = count_results(page)

        page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return false;
            var btn = panel.querySelector('.generative.ready');
            if (btn && !btn.disabled) { btn.click(); return true; }
            return false;
        }""")

        # Poll for completion
        start = time.time()
        while time.time() - start < 90:
            page.wait_for_timeout(3000)
            elapsed = int(time.time() - start)

            after_count = count_results(page)
            if after_count > before_count:
                print(f"\n  GENERATION COMPLETE! ({elapsed}s, new images: {after_count - before_count})")
                break

            # Check progress
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
                print(f"    Progress: {progress} ({elapsed}s)")
        else:
            final = count_results(page)
            print(f"\n  TIMEOUT. Results: {before_count} -> {final}")

        screenshot(page, "p180_nano_banana_result")

        # Extract result URLs
        latest_urls = page.evaluate("""() => {
            var imgs = document.querySelectorAll('img[src*="static.dzine.ai/stylar_product/p/"]');
            var urls = [];
            for (var img of imgs) urls.push(img.src);
            return urls.slice(-4);
        }""")
        print(f"  Latest result URLs:")
        for url in latest_urls:
            print(f"    {url[:150]}")
    else:
        print("  Generate button not ready!")

    # ================================================================
    # TASK 3: Explore Pick Image Dialog (for AI Video file upload)
    # ================================================================
    print("\n" + "=" * 70)
    print("TASK 3: Map Pick Image Dialog")
    print("=" * 70)

    # The file upload failed in Part 9. Let's understand the Pick Image dialog better.
    # Navigate to AI Video
    page.mouse.click(40, 766)  # distant tool
    page.wait_for_timeout(1500)
    page.mouse.click(40, 361)  # AI Video
    page.wait_for_timeout(2500)

    # Click the start frame pick-image button
    page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return false;
        var btn = panel.querySelector('button.pick-image');
        if (btn) { btn.click(); return true; }
        return false;
    }""")
    page.wait_for_timeout(2000)

    # Map the Pick Image dialog
    dialog = page.evaluate("""() => {
        // Look for dialog/popup/modal
        var dialogs = document.querySelectorAll('.popup-mount-node, .modal, .dialog, [class*="pick-image-dialog"], [class*="image-selector"]');
        var results = [];
        for (var d of dialogs) {
            var rect = d.getBoundingClientRect();
            if (rect.height > 100) {
                results.push({
                    class: ((typeof d.className === 'string') ? d.className : (d.getAttribute('class') || '')).substring(0, 80),
                    pos: {x: Math.round(rect.x), y: Math.round(rect.y), w: Math.round(rect.width), h: Math.round(rect.height)},
                    text: (d.innerText || '').substring(0, 500)
                });
            }
        }

        // Also check for file input
        var inputs = document.querySelectorAll('input[type="file"]');
        for (var inp of inputs) {
            results.push({
                class: 'input[type=file]',
                accept: inp.accept || '',
                multiple: inp.multiple
            });
        }

        // Check for "choose an image on the canvas" option
        var canvasOption = null;
        for (var el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            if (text.includes('choose an image on the canvas') || text.includes('Drop or select')) {
                var r = el.getBoundingClientRect();
                if (r.height > 0 && r.height < 200) {
                    canvasOption = {
                        text: text.substring(0, 100),
                        pos: {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)},
                        tag: el.tagName
                    };
                    break;
                }
            }
        }

        return {dialogs: results, canvasOption: canvasOption};
    }""")
    print(f"  Pick Image dialog elements:")
    for d in dialog.get("dialogs", []):
        print(f"    class: {d.get('class', '')}")
        if "pos" in d:
            print(f"    pos: ({d['pos']['x']},{d['pos']['y']}) {d['pos']['w']}x{d['pos']['h']}")
        if "text" in d:
            lines = d["text"].split("\n")[:10]
            for line in lines:
                line = line.strip()
                if line:
                    print(f"      > {line[:60]}")
        if "accept" in d:
            print(f"    accept: {d['accept']}, multiple: {d.get('multiple')}")

    if dialog.get("canvasOption"):
        co = dialog["canvasOption"]
        print(f"\n  Canvas option: '{co['text'][:60]}' at ({co['pos']['x']},{co['pos']['y']})")

    screenshot(page, "p180_pick_image_dialog")

    # Close the dialog
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)

    print("\n" + "=" * 70)
    print("EXPLORATION PART 10 COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
