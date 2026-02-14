#!/usr/bin/env python3
"""Phase 140: Explore Dzine AI Video feature.

From the UI map:
- AI Video is sidebar tool #6 at y=361
- Also available in Results panel action row (per-result)
- Panel type: `.panels.show` + `.c-gen-config.show` (`.ai-video-panel`)
- Credits: varies by model
- This is critical: if Dzine can do image-to-video, it competes with ChatCut/Seedance

Goals:
1. Open AI Video panel from sidebar
2. Document all models/options available
3. Check if it supports image-to-video (product photos)
4. Check credits cost per model
5. Check duration/resolution options
6. Try generating a short video from an existing result image
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
    print("PHASE 140: Dzine AI Video Feature Exploration")
    print("=" * 70)

    if not is_browser_running():
        print("[P140] ERROR: Brave not running.")
        return

    pw = sync_playwright().start()
    try:
        browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{DEFAULT_CDP_PORT}")
        context = browser.contexts[0]

        dzine_pages = [p for p in context.pages if "dzine.ai/canvas" in (p.url or "")]
        if not dzine_pages:
            print("[P140] No Dzine canvas found. Opening one...")
            page = context.new_page()
            page.goto("https://www.dzine.ai/canvas?id=19797967", wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(5000)
        else:
            page = dzine_pages[0]

        page.set_viewport_size(VIEWPORT)
        page.bring_to_front()
        page.wait_for_timeout(2000)
        print(f"[P140] Canvas: {page.url}")

        # Close dialogs
        close_all_dialogs(page)
        page.wait_for_timeout(1000)

        # Step 1: Click AI Video in sidebar (tool #6, y=361)
        print("\n[1] Opening AI Video panel...")
        # First toggle away to ensure clean state
        page.mouse.click(40, 766)  # Storyboard (distant tool)
        page.wait_for_timeout(1500)
        page.mouse.click(40, 361)  # AI Video
        page.wait_for_timeout(3000)

        page.screenshot(path=os.path.expanduser("~/Downloads/p140_aivideo_panel.png"))

        # Step 2: Read the AI Video panel content
        print("\n[2] Reading AI Video panel content...")
        panel_text = page.evaluate("""() => {
            // Check for .ai-video-panel or .panels.show content
            var panel = document.querySelector('.ai-video-panel') ||
                        document.querySelector('.panels.show') ||
                        document.querySelector('.c-gen-config.show');
            if (panel) {
                return {
                    text: panel.innerText.substring(0, 3000),
                    cls: panel.className,
                    x: Math.round(panel.getBoundingClientRect().x),
                    y: Math.round(panel.getBoundingClientRect().y),
                    w: Math.round(panel.getBoundingClientRect().width),
                    h: Math.round(panel.getBoundingClientRect().height)
                };
            }
            return null;
        }""")
        if panel_text:
            print(f"[2] Panel: cls={panel_text['cls'][:60]} ({panel_text['x']},{panel_text['y']}) {panel_text['w']}x{panel_text['h']}")
            print(f"[2] Content:\n{panel_text['text'][:2000]}")
        else:
            print("[2] No panel found via standard selectors")
            # Fallback: scan all visible elements in left panel area
            left_content = page.evaluate("""() => {
                var items = [];
                for (var el of document.querySelectorAll('*')) {
                    var r = el.getBoundingClientRect();
                    var s = window.getComputedStyle(el);
                    if (r.x > 60 && r.x < 400 && r.y > 50 && r.y < 850 &&
                        r.width > 100 && s.display !== 'none' && s.visibility !== 'hidden') {
                        var text = (el.innerText || '').trim();
                        if (text.length > 5 && text.length < 500) {
                            items.push({
                                text: text.substring(0, 200),
                                x: Math.round(r.x), y: Math.round(r.y),
                                w: Math.round(r.width), h: Math.round(r.height),
                                tag: el.tagName, cls: (el.className || '').substring(0, 50)
                            });
                        }
                    }
                }
                // Deduplicate by text
                var unique = [];
                var seen = new Set();
                for (var item of items) {
                    var key = item.text.substring(0, 50);
                    if (!seen.has(key)) {
                        seen.add(key);
                        unique.push(item);
                    }
                }
                return unique;
            }""")
            print(f"[2] Fallback: {len(left_content)} elements in left panel area")
            for e in left_content[:15]:
                print(f"  ({e['x']},{e['y']}) {e['w']}x{e['h']} <{e['tag']}> cls={e['cls'][:30]} '{e['text'][:80]}'")

        # Step 3: Look for model/provider options
        print("\n[3] Looking for video models/providers...")
        models = page.evaluate("""() => {
            var items = [];
            var keywords = ['runway', 'kling', 'luma', 'pika', 'minimax', 'seedance',
                          'gen-3', 'gen-2', 'stable video', 'animate', 'hailuo',
                          'wan', 'veo', 'sora', 'cogvideo', 'mochi'];
            // Check all visible text elements
            for (var el of document.querySelectorAll('*')) {
                var text = (el.innerText || '').trim().toLowerCase();
                if (text.length < 200) {
                    for (var kw of keywords) {
                        if (text.includes(kw)) {
                            var r = el.getBoundingClientRect();
                            if (r.width > 0 && r.height > 0) {
                                items.push({
                                    kw: kw,
                                    text: (el.innerText || '').trim().substring(0, 100),
                                    x: Math.round(r.x), y: Math.round(r.y),
                                    w: Math.round(r.width), h: Math.round(r.height),
                                    tag: el.tagName,
                                    cls: (el.className || '').substring(0, 40)
                                });
                            }
                            break;
                        }
                    }
                }
            }
            // Deduplicate
            var unique = [];
            var seen = new Set();
            for (var item of items) {
                var key = item.kw + '_' + item.x + '_' + item.y;
                if (!seen.has(key)) {
                    seen.add(key);
                    unique.push(item);
                }
            }
            return unique;
        }""")
        print(f"[3] Video model references: {len(models)}")
        for m in models[:20]:
            print(f"  [{m['kw']}] ({m['x']},{m['y']}) {m['w']}x{m['h']} <{m['tag']}> '{m['text'][:60]}' cls={m['cls']}")

        # Step 4: Look for all interactive elements in the AI Video area
        print("\n[4] Interactive elements in AI Video panel...")
        interactive = page.evaluate("""() => {
            var items = [];
            for (var el of document.querySelectorAll('button, input, textarea, select, [contenteditable], [role="button"], [role="tab"], [role="option"]')) {
                var r = el.getBoundingClientRect();
                if (r.width > 0 && r.height > 0 && r.x > 60 && r.x < 400 && r.y > 50 && r.y < 850) {
                    var text = (el.innerText || el.placeholder || el.value || el.getAttribute('aria-label') || '').trim();
                    items.push({
                        text: text.substring(0, 100),
                        tag: el.tagName,
                        type: el.type || '',
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        cls: (el.className || '').substring(0, 50),
                        disabled: el.disabled || false
                    });
                }
            }
            return items;
        }""")
        print(f"[4] Found {len(interactive)} interactive elements:")
        for e in interactive[:30]:
            dis = " DISABLED" if e['disabled'] else ""
            print(f"  ({e['x']},{e['y']}) {e['w']}x{e['h']} <{e['tag']}> type={e['type']} '{e['text'][:60]}' cls={e['cls'][:30]}{dis}")

        # Step 5: Look for video generation options (duration, aspect ratio, etc.)
        print("\n[5] Video generation options...")
        options = page.evaluate("""() => {
            var items = [];
            var keywords = ['duration', 'seconds', 'aspect', 'resolution', 'fps',
                          'camera', 'motion', 'speed', 'quality', 'credits',
                          'image to video', 'text to video', 'img2vid', 'txt2vid',
                          'reference', 'prompt', 'describe', 'generate video',
                          'start image', 'end image', 'first frame', 'last frame'];
            for (var el of document.querySelectorAll('*')) {
                var text = (el.innerText || '').trim().toLowerCase();
                if (text.length < 100) {
                    for (var kw of keywords) {
                        if (text.includes(kw)) {
                            var r = el.getBoundingClientRect();
                            if (r.width > 0 && r.height > 0 && r.x < 600) {
                                items.push({
                                    kw: kw,
                                    text: (el.innerText || '').trim().substring(0, 80),
                                    x: Math.round(r.x), y: Math.round(r.y),
                                    w: Math.round(r.width), h: Math.round(r.height),
                                    tag: el.tagName
                                });
                            }
                            break;
                        }
                    }
                }
            }
            // Deduplicate
            var unique = [];
            var seen = new Set();
            for (var item of items) {
                var key = item.text.substring(0, 30);
                if (!seen.has(key)) {
                    seen.add(key);
                    unique.push(item);
                }
            }
            return unique;
        }""")
        print(f"[5] Video options: {len(options)}")
        for o in options[:20]:
            print(f"  [{o['kw']}] ({o['x']},{o['y']}) <{o['tag']}> '{o['text']}'")

        # Step 6: Check if there are cards/tabs for different video generation modes
        print("\n[6] Looking for video mode cards/tabs...")
        cards = page.evaluate("""() => {
            var items = [];
            for (var el of document.querySelectorAll('[class*="card"], [class*="item"], [class*="option"], [class*="tab"]')) {
                var r = el.getBoundingClientRect();
                if (r.width > 60 && r.height > 30 && r.x > 60 && r.x < 400 && r.y > 50 && r.y < 850) {
                    var text = (el.innerText || '').trim();
                    if (text.length > 2 && text.length < 200) {
                        items.push({
                            text: text.substring(0, 100),
                            x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height),
                            cls: (el.className || '').substring(0, 60),
                            tag: el.tagName
                        });
                    }
                }
            }
            // Deduplicate
            var unique = [];
            var seen = new Set();
            for (var item of items) {
                var key = item.text.substring(0, 30) + '_' + item.y;
                if (!seen.has(key)) {
                    seen.add(key);
                    unique.push(item);
                }
            }
            return unique;
        }""")
        print(f"[6] Cards/tabs: {len(cards)}")
        for c in cards[:20]:
            print(f"  ({c['x']},{c['y']}) {c['w']}x{c['h']} <{c['tag']}> cls={c['cls'][:40]} '{c['text'][:60]}'")

        # Step 7: Also check the Results panel action row for AI Video
        print("\n[7] AI Video in Results panel action row...")
        results_aivideo = page.evaluate("""() => {
            // Find the AI Video action row in results panel
            for (var el of document.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                if (text === 'AI Video' || text === 'AI\\nVideo') {
                    var r = el.getBoundingClientRect();
                    if (r.x > 1000 && r.y > 600) {
                        // Found the label, now find nearby buttons
                        var btns = [];
                        for (var btn of document.querySelectorAll('button')) {
                            var br = btn.getBoundingClientRect();
                            if (br.x > 1200 && Math.abs(br.y + br.height/2 - (r.y + r.height/2)) < 15) {
                                btns.push({
                                    text: (btn.innerText || '').trim(),
                                    x: Math.round(br.x), y: Math.round(br.y),
                                    cx: Math.round(br.x + br.width/2),
                                    cy: Math.round(br.y + br.height/2),
                                    cls: btn.className
                                });
                            }
                        }
                        return {
                            label: {x: Math.round(r.x), y: Math.round(r.y), cy: Math.round(r.y + r.height/2)},
                            buttons: btns
                        };
                    }
                }
            }
            return null;
        }""")
        if results_aivideo:
            print(f"[7] AI Video label at ({results_aivideo['label']['x']},{results_aivideo['label']['y']})")
            for b in results_aivideo['buttons']:
                print(f"  Button [{b['text']}] at ({b['cx']},{b['cy']}) cls={b['cls']}")
        else:
            print("[7] AI Video row not found in Results panel (may need to scroll or have results)")

        # Step 8: Try double-clicking AI Video sidebar to enter its config
        print("\n[8] Double-clicking AI Video sidebar icon...")
        page.mouse.dblclick(40, 361)
        page.wait_for_timeout(3000)

        page.screenshot(path=os.path.expanduser("~/Downloads/p140_aivideo_dblclick.png"))

        # Read config panel after double-click
        config_panel = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (panel) {
                return {
                    text: panel.innerText.substring(0, 3000),
                    cls: panel.className,
                    x: Math.round(panel.getBoundingClientRect().x),
                    w: Math.round(panel.getBoundingClientRect().width)
                };
            }
            return null;
        }""")
        if config_panel:
            print(f"[8] Config panel: cls={config_panel['cls'][:50]} x={config_panel['x']} w={config_panel['w']}")
            print(f"[8] Content:\n{config_panel['text'][:2000]}")
        else:
            print("[8] No config panel after double-click")

        # Step 9: Look for dropdowns or selectors for video model
        print("\n[9] Looking for video model selector...")
        model_selector = page.evaluate("""() => {
            var items = [];
            // Check for select elements, dropdowns, or model-related buttons
            for (var el of document.querySelectorAll('select, [class*="select"], [class*="dropdown"], [class*="model"], button.style, .style-name')) {
                var r = el.getBoundingClientRect();
                if (r.width > 0 && r.x > 60 && r.x < 400) {
                    items.push({
                        text: (el.innerText || el.value || '').trim().substring(0, 100),
                        tag: el.tagName,
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        cls: (el.className || '').substring(0, 60)
                    });
                }
            }
            return items;
        }""")
        print(f"[9] Model selectors: {len(model_selector)}")
        for m in model_selector[:10]:
            print(f"  ({m['x']},{m['y']}) {m['w']}x{m['h']} <{m['tag']}> cls={m['cls'][:40]} '{m['text'][:60]}'")

        # Step 10: Full page screenshot
        page.screenshot(path=os.path.expanduser("~/Downloads/p140_full.png"), full_page=True)

        # Summary
        print("\n" + "=" * 70)
        print("PHASE 140 SUMMARY")
        print("=" * 70)
        print("Check ~/Downloads/p140_*.png for screenshots")

    finally:
        pw.stop()


if __name__ == "__main__":
    main()
