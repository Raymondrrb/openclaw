#!/usr/bin/env python3
"""Phase 144: AI Video — Generate test video with Wan 2.1.

From P143:
- Wan 2.1 selected, 6 credits, Auto 720p 5s
- Start frame loaded from Generative Expand result (headphones)
- Generate button READY, not disabled
- 8.856 video credits available
- Camera option visible

Goals:
1. Write a short product showcase prompt
2. Check camera motion options
3. Click Generate (6 credits)
4. Wait for video generation
5. Download/document the result
"""

from __future__ import annotations

import os
import sys
import time
import urllib.request
from pathlib import Path

_repo = Path(__file__).resolve().parent.parent
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))


def main():
    from playwright.sync_api import sync_playwright
    from tools.lib.brave_profile import DEFAULT_CDP_PORT, is_browser_running
    from tools.lib.dzine_browser import close_all_dialogs, VIEWPORT

    print("=" * 70)
    print("PHASE 144: AI Video — Generate with Wan 2.1")
    print("=" * 70)

    if not is_browser_running():
        print("[P144] ERROR: Brave not running.")
        return

    pw = sync_playwright().start()
    try:
        browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{DEFAULT_CDP_PORT}")
        context = browser.contexts[0]

        dzine_pages = [p for p in context.pages if "dzine.ai/canvas" in (p.url or "")]
        if not dzine_pages:
            print("[P144] No Dzine canvas found.")
            return

        page = dzine_pages[0]
        page.set_viewport_size(VIEWPORT)
        page.bring_to_front()
        page.wait_for_timeout(1500)
        print(f"[P144] Canvas: {page.url}")

        close_all_dialogs(page)
        page.wait_for_timeout(500)

        # Verify AI Video panel state
        panel_state = page.evaluate("""() => {
            var panel = document.querySelector('.ai-video-panel.show');
            if (!panel) return null;
            var model = panel.querySelector('.selected-name-text');
            var gen = panel.querySelector('.generative');
            var img = null;
            for (var el of panel.querySelectorAll('img')) {
                var r = el.getBoundingClientRect();
                if (r.x > 80 && r.x < 250 && r.y > 150 && r.y < 350 && r.width > 30) {
                    img = el.src.substring(0, 200);
                    break;
                }
            }
            return {
                model: model ? model.innerText.trim() : 'unknown',
                genText: gen ? gen.innerText.trim() : 'unknown',
                genDisabled: gen ? gen.disabled : true,
                startFrame: img
            };
        }""")
        print(f"[P144] Panel: {panel_state}")

        if not panel_state or not panel_state.get('startFrame'):
            print("[P144] Start frame not loaded. Need to set up first.")
            # Re-click AI Video [1] from results
            page.evaluate("""() => {
                for (var el of document.querySelectorAll('[class*="header-item"]')) {
                    if ((el.innerText || '').includes('Result')) { el.click(); return; }
                }
            }""")
            page.wait_for_timeout(500)
            page.evaluate("""() => {
                for (var el of document.querySelectorAll('*')) {
                    var text = (el.innerText || '').trim();
                    if ((text === 'AI Video' || text === 'AI\\nVideo') && el.childElementCount === 0) {
                        var r = el.getBoundingClientRect();
                        if (r.x > 1000 && r.y > 600) {
                            var labelCy = r.y + r.height / 2;
                            for (var btn of document.querySelectorAll('button.btn')) {
                                var br = btn.getBoundingClientRect();
                                if ((btn.innerText || '').trim() === '1' &&
                                    br.x > 1200 && Math.abs(br.y + br.height/2 - labelCy) < 15) {
                                    btn.click();
                                    return true;
                                }
                            }
                        }
                    }
                }
                return false;
            }""")
            page.wait_for_timeout(3000)

            # Re-select Wan 2.1
            page.evaluate("""() => {
                var wrapper = document.querySelector('.ai-video-panel .custom-selector-wrapper');
                if (wrapper) wrapper.click();
            }""")
            page.wait_for_timeout(2000)
            page.evaluate("""() => {
                var panel = document.querySelector('.selector-panel .panel-body');
                if (panel) panel.scrollTop = panel.scrollHeight;
            }""")
            page.wait_for_timeout(500)
            page.evaluate("""() => {
                var panel = document.querySelector('.selector-panel');
                if (!panel) return;
                for (var el of panel.querySelectorAll('.select-item')) {
                    if ((el.innerText || '').includes('Wan 2.1') && !(el.innerText || '').includes('Wan 2.2')) {
                        el.click();
                        return;
                    }
                }
            }""")
            page.wait_for_timeout(2000)

        # Step 1: Check Camera options
        print("\n[1] Checking Camera motion options...")
        camera_options = page.evaluate("""() => {
            var items = [];
            // Look for Camera button or section in AI Video panel
            for (var el of document.querySelectorAll('.ai-video-panel button, .ai-video-panel [role="button"]')) {
                var text = (el.innerText || '').trim();
                var r = el.getBoundingClientRect();
                if (text.includes('Camera') && r.width > 0) {
                    items.push({
                        text: text,
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        cls: (el.className || '').substring(0, 50)
                    });
                }
            }
            return items;
        }""")
        print(f"[1] Camera options: {len(camera_options)}")
        for c in camera_options:
            print(f"  ({c['x']},{c['y']}) {c['w']}x{c['h']} '{c['text']}' cls={c['cls']}")

        # Click Camera to expand options
        if camera_options:
            print("[1b] Clicking Camera button...")
            page.evaluate("""() => {
                for (var el of document.querySelectorAll('.ai-video-panel button, .ai-video-panel [role="button"]')) {
                    if ((el.innerText || '').trim() === 'Camera') {
                        el.click(); return true;
                    }
                }
                return false;
            }""")
            page.wait_for_timeout(1500)

            # Read expanded camera options
            cam_expanded = page.evaluate("""() => {
                var items = [];
                var keywords = ['zoom', 'pan', 'orbit', 'tilt', 'rotate', 'dolly', 'truck',
                              'static', 'none', 'auto', 'left', 'right', 'up', 'down',
                              'in', 'out', 'clockwise', 'slow'];
                for (var el of document.querySelectorAll('.ai-video-panel *')) {
                    var text = (el.innerText || '').trim().toLowerCase();
                    for (var kw of keywords) {
                        if (text === kw || (text.includes(kw) && text.length < 30)) {
                            var r = el.getBoundingClientRect();
                            if (r.width > 0 && r.height > 0) {
                                items.push({
                                    text: (el.innerText || '').trim(),
                                    x: Math.round(r.x), y: Math.round(r.y),
                                    w: Math.round(r.width),
                                    tag: el.tagName
                                });
                            }
                            break;
                        }
                    }
                }
                // Deduplicate
                var unique = [];
                var seen = new Set();
                for (var item of items) {
                    if (!seen.has(item.text)) {
                        seen.add(item.text);
                        unique.push(item);
                    }
                }
                return unique;
            }""")
            print(f"[1b] Camera motion options: {len(cam_expanded)}")
            for c in cam_expanded[:15]:
                print(f"  ({c['x']},{c['y']}) <{c['tag']}> '{c['text']}'")

            page.screenshot(path=os.path.expanduser("~/Downloads/p144_camera_options.png"))

        # Step 2: Write prompt
        print("\n[2] Writing prompt...")
        prompt = "Slow orbit around premium wireless headphones on clean white studio backdrop, professional product showcase, soft studio lighting, smooth camera movement"

        page.evaluate("""() => {
            var textarea = document.querySelector('.ai-video-panel textarea');
            if (textarea) {
                textarea.focus();
                textarea.value = '';
                return true;
            }
            return false;
        }""")
        page.wait_for_timeout(300)

        # Select all and type
        page.keyboard.press("Meta+a")
        page.wait_for_timeout(100)
        page.keyboard.type(prompt, delay=3)
        page.wait_for_timeout(500)

        # Verify prompt was entered
        prompt_check = page.evaluate("""() => {
            var textarea = document.querySelector('.ai-video-panel textarea');
            return textarea ? textarea.value : '';
        }""")
        print(f"[2] Prompt entered: {len(prompt_check)} chars")
        print(f"[2] Prompt: {prompt_check[:100]}")

        page.screenshot(path=os.path.expanduser("~/Downloads/p144_before_generate.png"))

        # Step 3: Check credits one more time
        credits_before = page.evaluate("""() => {
            for (var el of document.querySelectorAll('.ai-video-panel *')) {
                var text = (el.innerText || '').trim();
                if (text.includes('video credits left')) {
                    // Extract the number
                    var match = text.match(/([\d.]+)\s*video credits/);
                    if (match) return parseFloat(match[1]);
                }
            }
            return -1;
        }""")
        gen_cost_final = page.evaluate("""() => {
            var btn = document.querySelector('.ai-video-panel .generative');
            if (btn) {
                var text = btn.innerText.trim();
                var match = text.match(/(\d+)/);
                return match ? parseInt(match[1]) : -1;
            }
            return -1;
        }""")
        print(f"\n[3] Credits available: {credits_before}")
        print(f"[3] Generation cost: {gen_cost_final}")

        if credits_before < gen_cost_final:
            print(f"[3] INSUFFICIENT CREDITS ({credits_before} < {gen_cost_final})")
            return

        # Step 4: Click Generate!
        print(f"\n[4] Generating video ({gen_cost_final} credits)...")
        gen_start = time.monotonic()

        page.evaluate("""() => {
            var btn = document.querySelector('.ai-video-panel .generative.ready');
            if (btn && !btn.disabled) {
                btn.click();
                return true;
            }
            return false;
        }""")

        # Step 5: Poll for completion
        print("[5] Waiting for video generation...")
        page.wait_for_timeout(5000)

        last_status = ""
        success = False
        video_url = None

        while time.monotonic() - gen_start < 300:  # 5 min timeout
            elapsed = int(time.monotonic() - gen_start)

            # Check for progress/percentage
            status = page.evaluate("""() => {
                var panel = document.querySelector('.ai-video-panel');
                if (!panel) return '';
                // Check for percentage
                for (var el of panel.querySelectorAll('*')) {
                    var text = (el.innerText || '').trim();
                    if (text.match(/^\\d{1,3}%$/)) return text;
                }
                // Check for status messages
                for (var el of panel.querySelectorAll('*')) {
                    var text = (el.innerText || '').trim();
                    if (text.includes('Generating') || text.includes('Processing') ||
                        text.includes('Queue') || text.includes('Complete') ||
                        text.includes('Failed') || text.includes('Error')) {
                        return text.substring(0, 100);
                    }
                }
                return '';
            }""")

            if status and status != last_status:
                print(f"[5]   {elapsed}s: {status}")
                last_status = status

            if "Failed" in status or "Error" in status:
                print(f"[5] GENERATION FAILED at {elapsed}s")
                break

            if "Complete" in status:
                print(f"[5] GENERATION COMPLETE at {elapsed}s")
                success = True
                break

            # Check for video element or video thumbnail in results
            video_check = page.evaluate("""() => {
                // Check for video elements
                var videos = document.querySelectorAll('video');
                for (var v of videos) {
                    var r = v.getBoundingClientRect();
                    if (r.width > 0) {
                        return {type: 'video', src: (v.src || v.querySelector('source')?.src || '').substring(0, 300),
                                x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width)};
                    }
                }
                // Check results panel for new entries with video indicators
                for (var el of document.querySelectorAll('[class*="video-result"], [class*="video-item"]')) {
                    var r = el.getBoundingClientRect();
                    if (r.width > 0) {
                        return {type: 'video-result', text: (el.innerText || '').substring(0, 100),
                                x: Math.round(r.x), y: Math.round(r.y)};
                    }
                }
                return null;
            }""")

            if video_check:
                print(f"[5]   Video found at {elapsed}s: {video_check}")
                if video_check.get('src'):
                    video_url = video_check['src']
                success = True
                break

            # Check Generate button state
            gen_state = page.evaluate("""() => {
                var btn = document.querySelector('.ai-video-panel .generative');
                if (btn) return {text: btn.innerText.trim(), disabled: btn.disabled, cls: btn.className};
                return null;
            }""")

            if elapsed % 15 == 0:
                print(f"[5]   {elapsed}s: gen_btn={gen_state}")

            if elapsed > 5 and gen_state and not gen_state.get('disabled') and 'ready' in gen_state.get('cls', ''):
                # Button became ready again — generation might have completed or failed
                print(f"[5]   Generate button back to ready at {elapsed}s")
                page.wait_for_timeout(3000)
                # Do a final check
                break

            if elapsed > 0 and elapsed % 30 == 0:
                page.screenshot(path=os.path.expanduser(f"~/Downloads/p144_{elapsed}s.png"))

            page.wait_for_timeout(5000)

        page.screenshot(path=os.path.expanduser("~/Downloads/p144_after_generate.png"))

        # Step 6: Check results
        print(f"\n[6] Generation took {int(time.monotonic() - gen_start)}s")

        # Check credits after
        credits_after = page.evaluate("""() => {
            for (var el of document.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                var match = text.match(/([\d.]+)\s*video credits/);
                if (match) return parseFloat(match[1]);
            }
            return -1;
        }""")
        print(f"[6] Credits: {credits_before} -> {credits_after} (spent: {credits_before - credits_after:.3f})")

        # Check for video in results
        print("\n[7] Scanning for video results...")
        all_videos = page.evaluate("""() => {
            var items = [];
            // Check all video elements
            for (var v of document.querySelectorAll('video, [class*="video"]')) {
                var r = v.getBoundingClientRect();
                if (r.width > 0) {
                    items.push({
                        tag: v.tagName,
                        src: (v.src || '').substring(0, 300),
                        poster: (v.poster || '').substring(0, 200),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        cls: (v.className || '').substring(0, 50)
                    });
                }
            }
            // Check for .mp4 URLs in any element
            for (var el of document.querySelectorAll('*')) {
                var src = el.getAttribute('src') || el.getAttribute('data-src') || '';
                if (src.includes('.mp4') || src.includes('video')) {
                    var r = el.getBoundingClientRect();
                    items.push({
                        tag: el.tagName,
                        src: src.substring(0, 300),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        cls: (el.className || '').substring(0, 50)
                    });
                }
            }
            return items;
        }""")
        print(f"[7] Video elements: {len(all_videos)}")
        for v in all_videos[:10]:
            print(f"  <{v['tag']}> ({v['x']},{v['y']}) {v['w']}x{v['h']} cls={v['cls'][:30]}")
            if v.get('src'):
                print(f"    src: {v['src'][:150]}")
            if v.get('poster'):
                print(f"    poster: {v['poster'][:100]}")

        # Check panel content for any error or result
        panel_after = page.evaluate("""() => {
            var panel = document.querySelector('.ai-video-panel');
            if (panel) return panel.innerText.substring(0, 1500);
            return '';
        }""")
        print(f"\n[8] Panel content after:\n{panel_after[:800]}")

        # Summary
        print("\n" + "=" * 70)
        print("PHASE 144 SUMMARY")
        print("=" * 70)
        print(f"  Model: Wan 2.1")
        print(f"  Cost: {gen_cost_final} credits")
        print(f"  Credits: {credits_before} -> {credits_after}")
        print(f"  Video: {'FOUND' if success else 'NOT FOUND'}")
        print("  Check ~/Downloads/p144_*.png for screenshots")

    finally:
        pw.stop()


if __name__ == "__main__":
    main()
