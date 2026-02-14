#!/usr/bin/env python3
"""Phase 143: AI Video — Test Wan 2.1 (cheapest model, 6 credits).

From P142 model catalog:
- Wan 2.1: 6 credits / 5s, Uncensored — only model guaranteed within 8.856 budget
- Start Frame upload needed (product image)
- Prompt field: 1800 chars
- Generate button shows credit cost

Goals:
1. Select Wan 2.1 model
2. Upload a start frame (product headphone image from previous expand results)
3. Write a product showcase prompt
4. Check the final credit cost before generating
5. Generate if affordable (6 credits)
6. Document video output quality, format, duration
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

_repo = Path(__file__).resolve().parent.parent
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))


def main():
    from playwright.sync_api import sync_playwright
    from tools.lib.brave_profile import DEFAULT_CDP_PORT, is_browser_running
    from tools.lib.dzine_browser import close_all_dialogs, VIEWPORT

    print("=" * 70)
    print("PHASE 143: AI Video — Wan 2.1 Test Generation")
    print("=" * 70)

    if not is_browser_running():
        print("[P143] ERROR: Brave not running.")
        return

    pw = sync_playwright().start()
    try:
        browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{DEFAULT_CDP_PORT}")
        context = browser.contexts[0]

        dzine_pages = [p for p in context.pages if "dzine.ai/canvas" in (p.url or "")]
        if not dzine_pages:
            print("[P143] No Dzine canvas found.")
            return

        page = dzine_pages[0]
        page.set_viewport_size(VIEWPORT)
        page.bring_to_front()
        page.wait_for_timeout(1500)
        print(f"[P143] Canvas: {page.url}")

        close_all_dialogs(page)
        page.wait_for_timeout(500)

        # Ensure AI Video panel is open in Key Frame mode
        ai_open = page.evaluate("""() => {
            var panel = document.querySelector('.ai-video-panel.show');
            return !!panel;
        }""")
        if not ai_open:
            page.mouse.click(40, 766)
            page.wait_for_timeout(1000)
            page.mouse.click(40, 361)
            page.wait_for_timeout(2000)

        # Ensure Key Frame mode
        page.evaluate("""() => {
            for (var btn of document.querySelectorAll('button.options')) {
                if ((btn.innerText || '').trim() === 'Key Frame') {
                    btn.click(); return true;
                }
            }
            return false;
        }""")
        page.wait_for_timeout(1000)

        # Step 1: Select Wan 2.1 model
        print("\n[1] Selecting Wan 2.1 model...")
        # Open model selector
        page.evaluate("""() => {
            var wrapper = document.querySelector('.ai-video-panel .custom-selector-wrapper');
            if (wrapper) { wrapper.click(); return true; }
            return false;
        }""")
        page.wait_for_timeout(2000)

        # Scroll down in the panel body to find Wan 2.1
        page.evaluate("""() => {
            var panel = document.querySelector('.selector-panel .panel-body');
            if (panel) {
                // Scroll to bottom to reveal Wan 2.1
                panel.scrollTop = panel.scrollHeight;
            }
        }""")
        page.wait_for_timeout(1000)

        # Click Wan 2.1
        clicked_model = page.evaluate("""() => {
            var panel = document.querySelector('.selector-panel');
            if (!panel) return {ok: false, reason: 'no panel'};
            for (var el of panel.querySelectorAll('.select-item, .item-content')) {
                var text = (el.innerText || '').trim();
                if (text.includes('Wan 2.1') && !text.includes('Wan 2.2')) {
                    el.click();
                    return {ok: true, text: text};
                }
            }
            return {ok: false, reason: 'Wan 2.1 not found'};
        }""")
        print(f"[1] Model click: {clicked_model}")
        page.wait_for_timeout(2000)

        # Verify model is selected
        current_model = page.evaluate("""() => {
            var el = document.querySelector('.ai-video-panel .selected-name-text');
            return el ? el.innerText.trim() : 'unknown';
        }""")
        print(f"[1] Current model: {current_model}")

        # Check what the generate button shows
        gen_cost = page.evaluate("""() => {
            var btn = document.querySelector('.ai-video-panel .generative');
            if (btn) return btn.innerText.trim();
            return 'not found';
        }""")
        print(f"[1] Generate button: {gen_cost}")

        page.screenshot(path=os.path.expanduser("~/Downloads/p143_wan21_selected.png"))

        # Step 2: Upload start frame image
        print("\n[2] Looking for start frame upload...")

        # Find the Start Frame upload button
        start_frame_btn = page.evaluate("""() => {
            for (var el of document.querySelectorAll('button.pick-image, button[class*="pick"]')) {
                var r = el.getBoundingClientRect();
                // The Start Frame button should be in the AI Video panel area
                if (r.x > 80 && r.x < 300 && r.y > 150 && r.y < 350 && r.width > 40) {
                    return {
                        text: (el.innerText || '').trim(),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        cls: el.className
                    };
                }
            }
            return null;
        }""")
        print(f"[2] Start Frame button: {start_frame_btn}")

        # Find the existing result images to use as start frame
        result_images = page.evaluate("""() => {
            var imgs = [];
            for (var img of document.querySelectorAll('img[src*="static.dzine.ai/stylar_product/p/"]')) {
                var r = img.getBoundingClientRect();
                if (r.width > 0) {
                    imgs.push({
                        src: img.src.substring(0, 200),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height)
                    });
                }
            }
            return imgs;
        }""")
        print(f"[2] Available result images: {len(result_images)}")
        for img in result_images[:5]:
            short = img['src'].split('/')[-1][:60]
            print(f"  ({img['x']},{img['y']}) {img['w']}x{img['h']} {short}")

        # Try clicking the Start Frame button to see what upload options are available
        print("\n[2b] Clicking Start Frame button...")
        page.evaluate("""() => {
            for (var el of document.querySelectorAll('button.pick-image, button[class*="pick"], button.has-guide')) {
                var text = (el.innerText || '').trim();
                var r = el.getBoundingClientRect();
                if (r.x > 80 && r.x < 200 && r.y > 150 && r.y < 350 && r.width > 40) {
                    el.click();
                    return true;
                }
            }
            return false;
        }""")
        page.wait_for_timeout(2000)

        page.screenshot(path=os.path.expanduser("~/Downloads/p143_start_frame_dialog.png"))

        # Check what opened (Pick Image dialog? File chooser?)
        pick_dialog = page.evaluate("""() => {
            var panel = document.querySelector('.pick-panel');
            if (panel) {
                var r = panel.getBoundingClientRect();
                return {
                    text: panel.innerText.substring(0, 1000),
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    cls: panel.className
                };
            }
            // Check for any centered dialog
            for (var el of document.querySelectorAll('*')) {
                var r = el.getBoundingClientRect();
                var s = window.getComputedStyle(el);
                if (r.width > 300 && r.height > 200 && r.x > 200 && r.x < 700 &&
                    r.y > 50 && r.y < 500 &&
                    (s.position === 'absolute' || s.position === 'fixed' || parseInt(s.zIndex) > 100)) {
                    var text = (el.innerText || '').trim();
                    if (text.length > 20) {
                        return {
                            text: text.substring(0, 500),
                            x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height),
                            cls: (el.className || '').substring(0, 60)
                        };
                    }
                }
            }
            return null;
        }""")
        if pick_dialog:
            print(f"[2b] Dialog: ({pick_dialog['x']},{pick_dialog['y']}) {pick_dialog['w']}x{pick_dialog['h']}")
            print(f"     cls: {pick_dialog['cls'][:60]}")
            print(f"     Content:\n{pick_dialog['text'][:500]}")
        else:
            print("[2b] No dialog opened")

        # Step 3: Check if there's a "Pick from Results" option
        print("\n[3] Looking for upload or pick options...")
        pick_options = page.evaluate("""() => {
            var items = [];
            for (var el of document.querySelectorAll('button, [role="button"]')) {
                var text = (el.innerText || '').trim();
                if (text.includes('Upload') || text.includes('Result') || text.includes('Pick') ||
                    text.includes('Choose') || text.includes('Select') || text.includes('Library') ||
                    text.includes('upload') || text.includes('Browse')) {
                    var r = el.getBoundingClientRect();
                    if (r.width > 0) {
                        items.push({
                            text: text.substring(0, 80),
                            x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height),
                            cls: (el.className || '').substring(0, 50)
                        });
                    }
                }
            }
            return items;
        }""")
        print(f"[3] Pick options: {len(pick_options)}")
        for p in pick_options[:10]:
            print(f"  ({p['x']},{p['y']}) {p['w']}x{p['h']} '{p['text'][:50]}' cls={p['cls'][:30]}")

        # Step 4: Look for tabs in pick dialog (Upload, My Uploads, Results, etc.)
        print("\n[4] Pick dialog tabs...")
        tabs = page.evaluate("""() => {
            var items = [];
            for (var el of document.querySelectorAll('.pick-panel *, [class*="tab"]')) {
                var r = el.getBoundingClientRect();
                if (r.width > 30 && r.height > 15 && r.y > 50 && r.y < 200) {
                    var text = (el.innerText || '').trim();
                    if (text.length > 1 && text.length < 50) {
                        items.push({
                            text: text,
                            x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height),
                            cls: (el.className || '').substring(0, 50),
                            tag: el.tagName
                        });
                    }
                }
            }
            // Deduplicate
            var unique = [];
            var seen = new Set();
            for (var item of items) {
                var key = item.text + '_' + item.x;
                if (!seen.has(key)) {
                    seen.add(key);
                    unique.push(item);
                }
            }
            return unique;
        }""")
        print(f"[4] Tabs: {len(tabs)}")
        for t in tabs[:15]:
            print(f"  ({t['x']},{t['y']}) {t['w']}x{t['h']} <{t['tag']}> '{t['text']}' cls={t['cls'][:30]}")

        # Step 5: Check if we can use an existing result directly
        # Try using the AI Video button from the Results panel action row instead
        print("\n[5] Checking Results panel AI Video buttons...")
        page.keyboard.press("Escape")  # Close any dialog
        page.wait_for_timeout(500)

        # Switch to Results tab
        page.evaluate("""() => {
            for (var el of document.querySelectorAll('[class*="header-item"]')) {
                if ((el.innerText || '').includes('Result')) { el.click(); return; }
            }
        }""")
        page.wait_for_timeout(500)

        # Click AI Video [1] button from results
        aivideo_result = page.evaluate("""() => {
            // Find AI Video label in results panel
            for (var el of document.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                if ((text === 'AI Video' || text === 'AI\\nVideo') && el.childElementCount === 0) {
                    var r = el.getBoundingClientRect();
                    if (r.x > 1000 && r.y > 600) {
                        // Found label, now find [1] button on same row
                        var labelCy = r.y + r.height / 2;
                        for (var btn of document.querySelectorAll('button.btn')) {
                            var br = btn.getBoundingClientRect();
                            if ((btn.innerText || '').trim() === '1' &&
                                br.x > 1200 && Math.abs(br.y + br.height/2 - labelCy) < 15) {
                                btn.click();
                                return {ok: true, btnX: Math.round(br.x), btnY: Math.round(br.y)};
                            }
                        }
                        return {ok: false, reason: 'button [1] not found', labelY: Math.round(r.y)};
                    }
                }
            }
            return {ok: false, reason: 'AI Video label not found'};
        }""")
        print(f"[5] AI Video result button click: {aivideo_result}")
        page.wait_for_timeout(3000)

        page.screenshot(path=os.path.expanduser("~/Downloads/p143_aivideo_from_result.png"))

        # Check what happened — did it open the AI Video panel with the image pre-loaded?
        print("\n[5b] Panel state after result click...")
        panel_after = page.evaluate("""() => {
            var panel = document.querySelector('.ai-video-panel.show') ||
                        document.querySelector('.c-gen-config.show');
            if (panel) {
                return {
                    text: panel.innerText.substring(0, 2000),
                    cls: panel.className
                };
            }
            return null;
        }""")
        if panel_after:
            print(f"[5b] Panel cls: {panel_after['cls'][:60]}")
            print(f"[5b] Content:\n{panel_after['text'][:1500]}")
        else:
            print("[5b] No panel open")

        # Check if start frame was auto-populated
        start_img_loaded = page.evaluate("""() => {
            // Check if the Start Frame button now has an image
            for (var el of document.querySelectorAll('.ai-video-panel img')) {
                var r = el.getBoundingClientRect();
                if (r.x > 80 && r.x < 250 && r.y > 150 && r.y < 350 && r.width > 30) {
                    return {
                        src: (el.src || '').substring(0, 200),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height)
                    };
                }
            }
            // Check if the pick-image button lost its has-guide class (meaning image loaded)
            for (var el of document.querySelectorAll('.ai-video-panel button.pick-image')) {
                var r = el.getBoundingClientRect();
                var hasGuide = el.classList.contains('has-guide');
                var hasImg = el.querySelector('img');
                return {
                    hasGuide: hasGuide,
                    hasImg: !!hasImg,
                    x: Math.round(r.x), y: Math.round(r.y),
                    cls: el.className
                };
            }
            return null;
        }""")
        print(f"[5b] Start frame image: {start_img_loaded}")

        # Step 6: Check current credits and generate cost
        print("\n[6] Credits check...")
        credits = page.evaluate("""() => {
            // Get video credits
            for (var el of document.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                if (text.includes('video credits left')) {
                    return text;
                }
            }
            return 'not found';
        }""")
        gen_btn = page.evaluate("""() => {
            var btn = document.querySelector('.ai-video-panel .generative');
            if (btn) {
                return {
                    text: btn.innerText.trim(),
                    disabled: btn.disabled,
                    cls: btn.className
                };
            }
            return null;
        }""")
        print(f"[6] Credits: {credits}")
        print(f"[6] Generate: {gen_btn}")

        # Step 7: Check what model is now selected after clicking from results
        current = page.evaluate("""() => {
            var el = document.querySelector('.ai-video-panel .selected-name-text');
            return el ? el.innerText.trim() : 'unknown';
        }""")
        print(f"[6] Model: {current}")

        # Step 8: Check video settings (resolution, duration)
        settings = page.evaluate("""() => {
            var items = [];
            for (var el of document.querySelectorAll('.ai-video-panel *')) {
                var text = (el.innerText || '').trim();
                if ((text.includes('720p') || text.includes('1080p') || text.includes('Auto') ||
                     text.includes('5s') || text.includes('10s') || text.includes('4s')) &&
                    text.length < 50) {
                    var r = el.getBoundingClientRect();
                    if (r.width > 0) {
                        items.push({
                            text: text, x: Math.round(r.x), y: Math.round(r.y),
                            cls: (el.className || '').substring(0, 40)
                        });
                    }
                }
            }
            return items;
        }""")
        print(f"[6] Settings:")
        for s in settings[:10]:
            print(f"  ({s['x']},{s['y']}) '{s['text']}' cls={s['cls']}")

        page.screenshot(path=os.path.expanduser("~/Downloads/p143_final.png"), full_page=True)

        print("\n" + "=" * 70)
        print("PHASE 143 SUMMARY")
        print("=" * 70)
        print("Check ~/Downloads/p143_*.png for screenshots")

    finally:
        pw.stop()


if __name__ == "__main__":
    main()
