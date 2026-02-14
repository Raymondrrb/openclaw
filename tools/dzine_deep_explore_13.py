#!/usr/bin/env python3
"""Dzine Deep Exploration Part 13 — Hailuo 2.3 + 16:9 fix + Sound Effects.

1. Fix Results panel scrolling and try Hailuo 2.3
2. Fix 16:9 aspect ratio with Nano Banana Pro
3. Explore Sound Effects and Video Enhance features
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
    print("DZINE DEEP EXPLORATION PART 13")
    print("Hailuo 2.3 + 16:9 Fix + Sound Effects")
    print("=" * 70)

    browser, context, _, _pw = connect_or_launch()
    page = context.pages[0]
    print(f"Connected. URL: {page.url}")

    if "dzine.ai/canvas" not in page.url:
        page.goto("https://www.dzine.ai/canvas?id=19861203")
        page.wait_for_timeout(5000)
        close_dialogs(page)
        page.wait_for_timeout(1000)

    credits_start = get_video_credits(page)
    print(f"  Video credits: {credits_start}")

    # ================================================================
    # TASK 1: Nano Banana Pro 16:9 (Fix aspect ratio)
    # ================================================================
    print("\n" + "=" * 70)
    print("TASK 1: Nano Banana Pro 16:9 Product Image")
    print("=" * 70)

    # Switch to Txt2Img
    page.mouse.click(40, 766)  # distant
    page.wait_for_timeout(1500)
    page.mouse.click(40, 197)  # Txt2Img
    page.wait_for_timeout(2500)

    # Check model
    model = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return '';
        var sn = panel.querySelector('.style-name');
        return sn ? (sn.innerText || '').trim() : '';
    }""")
    print(f"  Model: {model}")

    # If not Nano Banana Pro, open picker and find it
    if "Nano Banana" not in model:
        print("  Selecting Nano Banana Pro...")
        page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            var btn = panel.querySelector('button.style');
            if (btn) btn.click();
        }""")
        page.wait_for_timeout(2000)

        # Click on the thumbnail above the "Nano Banana Pro" label
        nbp_clicked = page.evaluate("""() => {
            var picker = document.querySelector('.style-list-panel');
            if (!picker) return false;
            for (var el of picker.querySelectorAll('span, div, p')) {
                if ((el.innerText || '').trim() === 'Nano Banana Pro') {
                    var r = el.getBoundingClientRect();
                    if (r.height < 30 && r.height > 0) {
                        var parent = el.parentElement;
                        if (parent) { parent.click(); return true; }
                    }
                }
            }
            return false;
        }""")
        print(f"  Clicked: {nbp_clicked}")
        page.wait_for_timeout(1000)
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)

    # Map the aspect ratio section to understand 16:9 button
    aspect_info = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return [];
        var results = [];
        for (var btn of panel.querySelectorAll('button, [role="button"]')) {
            var text = (btn.innerText || '').trim();
            if (['9:16', '1:1', '16:9', '4:3', '3:4'].includes(text) ||
                text.includes('canvas') || text === 'more' || text === '') {
                var rect = btn.getBoundingClientRect();
                if (rect.height > 0) {
                    var cls = (typeof btn.className === 'string') ? btn.className : '';
                    results.push({
                        text: text || '(empty)',
                        x: Math.round(rect.x),
                        y: Math.round(rect.y),
                        w: Math.round(rect.width),
                        h: Math.round(rect.height),
                        selected: cls.includes('selected') || cls.includes('active')
                    });
                }
            }
        }
        // Also get the dimension display
        for (var el of panel.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            if (/^\d+[x×]\d+$/.test(text)) {
                var rect = el.getBoundingClientRect();
                if (rect.height > 0 && rect.height < 30) {
                    results.push({text: 'DIMS: ' + text, x: Math.round(rect.x), y: Math.round(rect.y)});
                    break;
                }
            }
        }
        return results;
    }""")
    print(f"  Aspect ratio buttons:")
    for a in aspect_info:
        sel = " [SELECTED]" if a.get("selected") else ""
        print(f"    '{a['text']}' at ({a['x']},{a['y']}) {a.get('w', 0)}x{a.get('h', 0)}{sel}")

    # Click 16:9 specifically
    clicked_16_9 = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return false;
        for (var btn of panel.querySelectorAll('button, [role="button"]')) {
            var text = (btn.innerText || '').trim();
            var rect = btn.getBoundingClientRect();
            if (text === '16:9' && rect.height > 0 && rect.y > 400) {
                btn.click();
                return true;
            }
        }
        return false;
    }""")
    print(f"  Clicked 16:9: {clicked_16_9}")
    page.wait_for_timeout(500)

    # Check new dimensions
    new_dims = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return '';
        for (var el of panel.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            if (/^\\d+[x\u00d7]\\d+$/.test(text)) {
                var rect = el.getBoundingClientRect();
                if (rect.height > 0 && rect.height < 30) return text;
            }
        }
        return '';
    }""")
    print(f"  New dimensions: {new_dims}")

    # Fill prompt and generate
    prompt = "Premium wireless headphones displayed on a clean wooden desk, warm afternoon sunlight from a window, shallow depth of field, living room background with books and plant. Side profile showing ear cup detail. Photorealistic, no text, no watermarks."

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
    print(f"  Prompt: '{prompt[:60]}...' ({len(prompt)} chars)")

    before = count_results(page)
    page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        var btn = panel.querySelector('.generative.ready');
        if (btn && !btn.disabled) btn.click();
    }""")
    print("  Generating 16:9 image...")

    start = time.time()
    while time.time() - start < 120:
        page.wait_for_timeout(3000)
        elapsed = int(time.time() - start)
        after = count_results(page)
        if after > before:
            print(f"  COMPLETE! ({elapsed}s, +{after-before} images)")
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
        print(f"  TIMEOUT. Results: {before} -> {count_results(page)}")

    screenshot(page, "p184_nbp_16x9_fixed")

    # ================================================================
    # TASK 2: Minimax Hailuo 2.3 Video (proper approach)
    # ================================================================
    print("\n" + "=" * 70)
    print("TASK 2: Minimax Hailuo 2.3 Video Test")
    print("=" * 70)

    credits_now = get_video_credits(page)
    print(f"  Credits: {credits_now}")

    # First scroll results panel to TOP to expose AI Video buttons
    page.evaluate("""() => {
        for (var el of document.querySelectorAll('[class*="header-item"]')) {
            if ((el.innerText || '').includes('Result')) { el.click(); return; }
        }
    }""")
    page.wait_for_timeout(500)

    # Scroll the results container to top
    page.evaluate("""() => {
        var containers = document.querySelectorAll('.result-panel, .material-v2-result-content, [class*="result"]');
        for (var c of containers) {
            if (c.scrollHeight > c.clientHeight + 100) {
                c.scrollTop = 0;
                return 'scrolled to top';
            }
        }
        return 'no scrollable';
    }""")
    page.wait_for_timeout(500)

    # Now click AI Video [1] from first visible result set
    clicked = page.evaluate("""() => {
        var containers = document.querySelectorAll('.btn-container');
        for (var c of containers) {
            var parent = c.parentElement;
            var parentText = (parent ? parent.innerText || '' : '').trim();
            if (parentText.startsWith('AI Video')) {
                var rect = c.getBoundingClientRect();
                if (rect.height > 0 && rect.y > 50 && rect.y < 900) {
                    var btns = c.querySelectorAll('.btn');
                    if (btns.length > 0) {
                        btns[0].click();
                        return {clicked: true, y: Math.round(rect.y)};
                    }
                }
            }
        }
        return {clicked: false};
    }""")
    print(f"  AI Video action: {json.dumps(clicked)}")
    page.wait_for_timeout(3000)

    if clicked.get("clicked"):
        # Verify AI Video panel
        is_video_panel = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return false;
            var cls = (typeof panel.className === 'string') ? panel.className : '';
            return cls.includes('ai-video');
        }""")
        print(f"  AI Video panel: {is_video_panel}")

        if is_video_panel:
            # Open model selector and select Hailuo 2.3
            print("  Opening model selector...")
            page.evaluate("""() => {
                var panel = document.querySelector('.c-gen-config.show');
                if (!panel) return;
                var sel = panel.querySelector('.custom-selector-wrapper');
                if (sel) sel.click();
            }""")
            page.wait_for_timeout(2000)

            screenshot(page, "p184_model_selector_open")

            # Find and click Minimax Hailuo 2.3
            hailuo_clicked = page.evaluate("""() => {
                // Look for the model name in the popup/DOM
                for (var el of document.querySelectorAll('*')) {
                    var text = (el.innerText || '').trim();
                    if (text.startsWith('Minimax Hailuo 2.3') && el.offsetHeight > 0 && el.offsetHeight < 80) {
                        el.click();
                        return {clicked: true, text: text.substring(0, 40)};
                    }
                }
                return {clicked: false};
            }""")
            print(f"  Hailuo 2.3 selection: {json.dumps(hailuo_clicked)}")
            page.wait_for_timeout(1500)

            # Verify model
            model_name = page.evaluate("""() => {
                var panel = document.querySelector('.c-gen-config.show');
                if (!panel) return '';
                var sel = panel.querySelector('.custom-selector-wrapper');
                if (!sel) return '';
                var lines = (sel.innerText || '').trim().split('\\n');
                return lines[0] || '';
            }""")
            print(f"  Model: {model_name}")

            # Check settings
            settings = page.evaluate("""() => {
                var panel = document.querySelector('.c-gen-config.show');
                if (!panel) return {};
                var text = panel.innerText || '';
                // Get gen button info
                var genBtn = panel.querySelector('.generative');
                var genCls = genBtn ? ((typeof genBtn.className === 'string') ? genBtn.className : '') : '';
                var genText = genBtn ? (genBtn.innerText || '').trim() : '';

                // Check for start frame
                var hasFrame = !!panel.querySelector('img[src*="static.dzine.ai"]');

                return {
                    genText: genText,
                    genReady: genCls.includes('ready'),
                    genDisabled: genBtn ? genBtn.disabled : true,
                    hasFrame: hasFrame
                };
            }""")
            print(f"  Settings: {json.dumps(settings)}")

            # Fill calm product prompt
            video_prompt = "Headphones resting on a wooden desk, warm natural light, subtle dust particles, calm and static product shot"

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
            print(f"  Prompt: '{video_prompt[:60]}...'")

            screenshot(page, "p184_hailuo_ready")

            # Check credit cost
            credit_cost = settings.get("genText", "").replace("Generate", "").strip()
            print(f"  Credit cost: {credit_cost}")
            try:
                cost_num = int(credit_cost)
            except:
                cost_num = 0

            current_credits = float(credits_now) if credits_now else 0

            if settings.get("genReady") and not settings.get("genDisabled"):
                if current_credits >= cost_num and cost_num > 0:
                    print(f"\n  >>> GENERATING (Hailuo 2.3, {cost_num} credits) <<<")
                    print(f"  Credits: {current_credits} -> ~{current_credits - cost_num}")

                    page.evaluate("""() => {
                        var panel = document.querySelector('.c-gen-config.show');
                        var btn = panel.querySelector('.generative.ready');
                        if (btn && !btn.disabled) btn.click();
                    }""")

                    # Wait for submission (credits change or "waiting" status)
                    start = time.time()
                    submitted = False
                    while time.time() - start < 60:
                        page.wait_for_timeout(5000)
                        elapsed = int(time.time() - start)
                        new_credits = get_video_credits(page)

                        if new_credits != credits_now:
                            print(f"  Credits changed: {credits_now} -> {new_credits} ({elapsed}s)")
                            print(f"  Video submitted! Will process in background (5-10 mins)")
                            submitted = True
                            break

                        # Check for waiting/queued status
                        status = page.evaluate("""() => {
                            for (var el of document.querySelectorAll('*')) {
                                var text = (el.innerText || '').trim();
                                if (text.includes('Waiting') || text.includes('Queue') || text.includes('Processing')) {
                                    var r = el.getBoundingClientRect();
                                    if (r.height > 0 && r.height < 30) return text.substring(0, 40);
                                }
                            }
                            return '';
                        }""")
                        if status:
                            print(f"  Status: {status} ({elapsed}s)")
                            submitted = True
                            break

                        print(f"    Waiting for submission... ({elapsed}s)")

                    if not submitted:
                        print("  Submission status unclear after 60s")

                    screenshot(page, "p184_hailuo_submitted")
                else:
                    print(f"  SKIPPING — credits: {current_credits}, cost: {cost_num}")
            else:
                print(f"  Generate not ready: {json.dumps(settings)}")
    else:
        print("  AI Video action button not found. Trying direct panel approach...")
        # Open AI Video panel directly
        page.mouse.click(40, 766)  # distant
        page.wait_for_timeout(1500)
        page.mouse.click(40, 361)  # AI Video
        page.wait_for_timeout(2500)

        # Check panel
        panel_text = page.evaluate("""() => {
            var p = document.querySelector('.c-gen-config.show');
            return p ? (p.innerText || '').substring(0, 200) : 'NO PANEL';
        }""")
        print(f"  Panel: {panel_text[:100]}")

    # ================================================================
    # TASK 3: Map Sound Effects and Video Enhance buttons
    # ================================================================
    print("\n" + "=" * 70)
    print("TASK 3: Video Result Actions Map")
    print("=" * 70)

    # Navigate to Results and scroll to video results
    page.evaluate("""() => {
        for (var el of document.querySelectorAll('[class*="header-item"]')) {
            if ((el.innerText || '').includes('Result')) { el.click(); return; }
        }
    }""")
    page.wait_for_timeout(500)

    # Find and map video result actions
    video_actions = page.evaluate("""() => {
        var items = document.querySelectorAll('.result-item.image-to-video-result.completed');
        if (items.length === 0) return {found: false};

        var item = items[0];  // First completed video
        // Scroll to it
        item.scrollIntoView({block: 'start'});

        var actions = [];
        for (var btn of item.querySelectorAll('button, [role="button"]')) {
            var text = (btn.innerText || '').trim();
            var rect = btn.getBoundingClientRect();
            if (rect.height > 0 && text.length > 0 && text.length < 40) {
                actions.push({
                    text: text,
                    x: Math.round(rect.x),
                    y: Math.round(rect.y),
                    w: Math.round(rect.width),
                    h: Math.round(rect.height)
                });
            }
        }

        return {found: true, count: items.length, actions: actions};
    }""")

    if video_actions.get("found"):
        print(f"  Completed videos: {video_actions['count']}")
        print(f"  Actions ({len(video_actions.get('actions', []))}):")
        for a in video_actions.get("actions", []):
            print(f"    '{a['text']}' at ({a['x']},{a['y']}) {a['w']}x{a['h']}")
    else:
        print("  No completed videos found")

    screenshot(page, "p184_video_actions")

    # ================================================================
    # TASK 4: Check Nano Banana Pro Output Quality costs
    # ================================================================
    print("\n" + "=" * 70)
    print("TASK 4: Nano Banana Pro Quality/Cost Tiers")
    print("=" * 70)

    # Navigate to Txt2Img
    page.goto("https://www.dzine.ai/canvas?id=19861203")
    page.wait_for_timeout(5000)
    close_dialogs(page)
    page.wait_for_timeout(1000)

    page.mouse.click(40, 766)
    page.wait_for_timeout(1500)
    page.mouse.click(40, 197)
    page.wait_for_timeout(2500)

    # Check if Nano Banana Pro is still selected
    model = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show');
        if (!panel) return '';
        var sn = panel.querySelector('.style-name');
        return sn ? (sn.innerText || '').trim() : '';
    }""")
    print(f"  Model: {model}")

    if "Nano Banana" in model:
        # Map each quality tier and its credit cost
        for quality in ["1K", "2K", "4K"]:
            # Click the quality button
            page.evaluate("""(q) => {
                var panel = document.querySelector('.c-gen-config.show');
                if (!panel) return;
                for (var btn of panel.querySelectorAll('button')) {
                    if ((btn.innerText || '').trim() === q) {
                        btn.click();
                        return;
                    }
                }
            }""", quality)
            page.wait_for_timeout(500)

            # Get credit cost and dimensions
            info = page.evaluate("""() => {
                var panel = document.querySelector('.c-gen-config.show');
                if (!panel) return {};
                var genBtn = panel.querySelector('.generative');
                var genText = genBtn ? (genBtn.innerText || '').trim() : '';

                // Get selected quality
                var selectedQuality = '';
                for (var btn of panel.querySelectorAll('button')) {
                    var text = (btn.innerText || '').trim();
                    var cls = (typeof btn.className === 'string') ? btn.className : '';
                    if (['1K', '2K', '4K'].includes(text) && cls.includes('selected')) {
                        selectedQuality = text;
                        break;
                    }
                }

                // Get dimensions
                var dims = '';
                for (var el of panel.querySelectorAll('*')) {
                    var t = (el.innerText || '').trim();
                    if (/^\\d+[x\u00d7]\\d+$/.test(t)) {
                        var r = el.getBoundingClientRect();
                        if (r.height > 0 && r.height < 30) { dims = t; break; }
                    }
                }

                return {quality: selectedQuality, credits: genText, dims: dims};
            }""")
            print(f"  {quality}: {json.dumps(info)}")

    # Final credits
    final_credits = get_video_credits(page)
    print(f"\n  Final video credits: {final_credits}")

    print("\n" + "=" * 70)
    print("EXPLORATION PART 13 COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
