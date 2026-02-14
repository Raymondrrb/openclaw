#!/usr/bin/env python3
"""Phase 148: Explore video post-production features.

From P146/P147:
- Video result has 5 action buttons: Lip Sync, Video Enhance & Upscale, Sound Effects, Video Editor, Motion Control
- These are different from image action rows (per-image vs per-video)
- Need to scroll results panel to top to see video result
- Also explore Instant Storyboard (sidebar #12)

Goals:
1. Click each video post-production button to see what it offers
2. Document costs and capabilities
3. Also check Instant Storyboard sidebar tool
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
    print("PHASE 148: Video Post-Production & Storyboard")
    print("=" * 70)

    if not is_browser_running():
        print("[P148] ERROR: Brave not running.")
        return

    pw = sync_playwright().start()
    try:
        browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{DEFAULT_CDP_PORT}")
        context = browser.contexts[0]

        dzine_pages = [p for p in context.pages if "dzine.ai/canvas" in (p.url or "")]
        if not dzine_pages:
            print("[P148] No Dzine canvas found.")
            return

        page = dzine_pages[0]
        page.set_viewport_size(VIEWPORT)
        page.bring_to_front()
        page.wait_for_timeout(1500)
        print(f"[P148] Canvas: {page.url}")

        close_all_dialogs(page)
        page.wait_for_timeout(500)

        # Close any open panels
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
        page.evaluate("""() => {
            for (var el of document.querySelectorAll('.c-gen-config.show .ico-close, .panels.show .ico-close')) el.click();
        }""")
        page.wait_for_timeout(500)

        # Switch to Results tab and scroll to top (video result)
        page.evaluate("""() => {
            for (var el of document.querySelectorAll('[class*="header-item"]')) {
                if ((el.innerText || '').includes('Result')) { el.click(); return; }
            }
        }""")
        page.wait_for_timeout(500)
        page.evaluate("""() => {
            for (var el of document.querySelectorAll('*')) {
                var s = window.getComputedStyle(el);
                if ((s.overflowY === 'auto' || s.overflowY === 'scroll') &&
                    el.scrollHeight > el.clientHeight + 50 &&
                    el.getBoundingClientRect().x > 1000) {
                    el.scrollTop = 0;
                    return true;
                }
            }
            return false;
        }""")
        page.wait_for_timeout(1000)

        # Step 1: List video result action buttons
        print("\n[1] Video result action buttons...")
        video_buttons = page.evaluate("""() => {
            var items = [];
            for (var el of document.querySelectorAll('.result-item.image-to-video-result .btn-container .btn')) {
                var text = (el.innerText || '').trim();
                var r = el.getBoundingClientRect();
                if (r.width > 0) {
                    items.push({
                        text: text.substring(0, 60),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        cls: (el.className || '').substring(0, 40)
                    });
                }
            }
            return items;
        }""")
        print(f"[1] Video buttons: {len(video_buttons)}")
        for b in video_buttons[:10]:
            print(f"  ({b['x']},{b['y']}) {b['w']}x{b['h']} '{b['text']}' cls={b['cls']}")

        # Step 2: Click "Lip Sync" video button
        print("\n[2] Clicking Lip Sync video button...")
        page.evaluate("""() => {
            for (var el of document.querySelectorAll('.result-item.image-to-video-result .btn')) {
                if ((el.innerText || '').trim() === 'Lip Sync') {
                    el.click();
                    return true;
                }
            }
            return false;
        }""")
        page.wait_for_timeout(3000)
        page.screenshot(path=os.path.expanduser("~/Downloads/p148_lip_sync.png"))

        lip_panel = page.evaluate("""() => {
            var panel = document.querySelector('.lip-sync-config-panel.show') ||
                        document.querySelector('.c-gen-config.show') ||
                        document.querySelector('.panels.show');
            if (panel) {
                return {
                    cls: panel.className.substring(0, 80),
                    text: panel.innerText.substring(0, 1000),
                    x: Math.round(panel.getBoundingClientRect().x),
                    w: Math.round(panel.getBoundingClientRect().width)
                };
            }
            return null;
        }""")
        if lip_panel:
            print(f"[2] Lip Sync panel: x={lip_panel['x']} w={lip_panel['w']} cls={lip_panel['cls'][:50]}")
            print(f"[2] Content:\n{lip_panel['text'][:600]}")

        # Close Lip Sync panel
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)
        page.evaluate("""() => {
            var p = document.querySelector('.lip-sync-config-panel.show');
            if (p) { var c = p.querySelector('.ico-close'); if (c) { c.click(); return; } p.classList.remove('show'); }
            for (var el of document.querySelectorAll('.c-gen-config.show .ico-close')) el.click();
        }""")
        page.wait_for_timeout(500)

        # Step 3: Click "Sound Effects" video button
        print("\n[3] Clicking Sound Effects...")
        page.evaluate("""() => {
            for (var el of document.querySelectorAll('.result-item.image-to-video-result .btn')) {
                if ((el.innerText || '').trim() === 'Sound Effects') {
                    el.click();
                    return true;
                }
            }
            return false;
        }""")
        page.wait_for_timeout(3000)
        page.screenshot(path=os.path.expanduser("~/Downloads/p148_sound_effects.png"))

        sfx_panel = page.evaluate("""() => {
            for (var el of document.querySelectorAll('.c-gen-config.show, .panels.show, [class*="sound"]')) {
                var r = el.getBoundingClientRect();
                if (r.width > 100 && r.x > 60 && r.x < 500) {
                    return {
                        cls: (el.className || '').substring(0, 80),
                        text: (el.innerText || '').substring(0, 1000),
                        x: Math.round(r.x), w: Math.round(r.width)
                    };
                }
            }
            return null;
        }""")
        if sfx_panel:
            print(f"[3] Sound Effects: x={sfx_panel['x']} w={sfx_panel['w']} cls={sfx_panel['cls'][:50]}")
            print(f"[3] Content:\n{sfx_panel['text'][:600]}")
        else:
            # Maybe opened a popup or dialog
            popup = page.evaluate("""() => {
                for (var el of document.querySelectorAll('*')) {
                    var r = el.getBoundingClientRect();
                    var s = window.getComputedStyle(el);
                    if (r.width > 300 && r.height > 200 && r.x > 200 && r.x < 800 &&
                        r.y > 50 && r.y < 500 && parseInt(s.zIndex) > 100) {
                        return {
                            text: (el.innerText || '').substring(0, 500),
                            x: Math.round(r.x), y: Math.round(r.y),
                            cls: (el.className || '').substring(0, 60)
                        };
                    }
                }
                return null;
            }""")
            if popup:
                print(f"[3] Popup: ({popup['x']},{popup['y']}) cls={popup['cls']}")
                print(f"[3] Content:\n{popup['text'][:400]}")
            else:
                print("[3] No panel or popup found")

        # Close panels
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)
        page.evaluate("""() => {
            for (var el of document.querySelectorAll('.c-gen-config.show .ico-close')) el.click();
        }""")
        page.wait_for_timeout(500)

        # Step 4: Click "Video Enhance & Upscale"
        print("\n[4] Clicking Video Enhance & Upscale...")
        page.evaluate("""() => {
            for (var el of document.querySelectorAll('.result-item.image-to-video-result .btn')) {
                if ((el.innerText || '').trim().includes('Enhance')) {
                    el.click();
                    return true;
                }
            }
            return false;
        }""")
        page.wait_for_timeout(3000)
        page.screenshot(path=os.path.expanduser("~/Downloads/p148_video_enhance.png"))

        enhance_panel = page.evaluate("""() => {
            for (var el of document.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                if ((text.includes('Enhance') || text.includes('Upscale')) && text.length > 30 && text.length < 500) {
                    var r = el.getBoundingClientRect();
                    var s = window.getComputedStyle(el);
                    if (r.width > 200 && (r.x > 60 && r.x < 500 || r.x > 300 && r.x < 800) &&
                        (s.position === 'fixed' || s.position === 'absolute' || parseInt(s.zIndex) > 50)) {
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
        if enhance_panel:
            print(f"[4] Video Enhance: ({enhance_panel['x']},{enhance_panel['y']}) {enhance_panel['w']}x{enhance_panel['h']}")
            print(f"     cls: {enhance_panel['cls']}")
            print(f"     Content:\n{enhance_panel['text'][:500]}")
        else:
            print("[4] No Video Enhance panel found")

        # Close
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)

        # Step 5: Explore Instant Storyboard (sidebar #12, y=766)
        print("\n[5] Opening Instant Storyboard...")
        page.evaluate("""() => {
            for (var el of document.querySelectorAll('.c-gen-config.show .ico-close')) el.click();
        }""")
        page.wait_for_timeout(500)

        page.mouse.click(40, 197)  # Toggle to distant tool first
        page.wait_for_timeout(1000)
        page.mouse.click(40, 766)  # Instant Storyboard
        page.wait_for_timeout(3000)

        page.screenshot(path=os.path.expanduser("~/Downloads/p148_storyboard.png"))

        storyboard = page.evaluate("""() => {
            var panel = document.querySelector('.panels.show') ||
                        document.querySelector('.c-gen-config.show');
            if (panel) {
                return {
                    cls: panel.className.substring(0, 80),
                    text: panel.innerText.substring(0, 1500),
                    x: Math.round(panel.getBoundingClientRect().x),
                    w: Math.round(panel.getBoundingClientRect().width)
                };
            }
            return null;
        }""")
        if storyboard:
            print(f"[5] Storyboard: x={storyboard['x']} w={storyboard['w']} cls={storyboard['cls'][:50]}")
            print(f"[5] Content:\n{storyboard['text'][:1000]}")
        else:
            print("[5] No Storyboard panel found")

        # Interactive elements
        sb_elements = page.evaluate("""() => {
            var items = [];
            for (var el of document.querySelectorAll('button, input, textarea, [contenteditable]')) {
                var r = el.getBoundingClientRect();
                if (r.width > 0 && r.x > 60 && r.x < 400 && r.y > 50 && r.y < 850) {
                    var text = (el.innerText || el.placeholder || el.value || '').trim();
                    items.push({
                        text: text.substring(0, 80),
                        tag: el.tagName,
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width),
                        cls: (el.className || '').substring(0, 40)
                    });
                }
            }
            return items;
        }""")
        print(f"\n[5b] Storyboard elements: {len(sb_elements)}")
        for e in sb_elements[:15]:
            print(f"  ({e['x']},{e['y']}) w={e['w']} <{e['tag']}> '{e['text'][:50]}' cls={e['cls'][:30]}")

        page.screenshot(path=os.path.expanduser("~/Downloads/p148_final.png"), full_page=True)

        print("\n" + "=" * 70)
        print("PHASE 148 SUMMARY")
        print("=" * 70)

    finally:
        pw.stop()


if __name__ == "__main__":
    main()
