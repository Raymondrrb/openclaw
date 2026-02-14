#!/usr/bin/env python3
"""Phase 142: AI Video — Full model list extraction.

From P141:
- Model selector panel opens at (362,65) 695x583 (cls=selector-panel medium)
- innerHTML is 33KB — many models
- Key Frame mode: Kling 2.5 Turbo STD (30 credits, 720p, 5s)
- Reference mode: Vidu Q1 (85 credits, 1080p, 5s)
- 8.856 video credits available

Goals:
1. Open the model selector panel
2. Extract ALL video models with their specs
3. Find cheapest models (within 8 credit budget)
4. Document capabilities per model
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_repo = Path(__file__).resolve().parent.parent
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))


def main():
    from playwright.sync_api import sync_playwright
    from tools.lib.brave_profile import DEFAULT_CDP_PORT, is_browser_running
    from tools.lib.dzine_browser import close_all_dialogs, VIEWPORT

    print("=" * 70)
    print("PHASE 142: AI Video — Complete Model Catalog")
    print("=" * 70)

    if not is_browser_running():
        print("[P142] ERROR: Brave not running.")
        return

    pw = sync_playwright().start()
    try:
        browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{DEFAULT_CDP_PORT}")
        context = browser.contexts[0]

        dzine_pages = [p for p in context.pages if "dzine.ai/canvas" in (p.url or "")]
        if not dzine_pages:
            print("[P142] No Dzine canvas found.")
            return

        page = dzine_pages[0]
        page.set_viewport_size(VIEWPORT)
        page.bring_to_front()
        page.wait_for_timeout(1500)
        print(f"[P142] Canvas: {page.url}")

        close_all_dialogs(page)
        page.wait_for_timeout(500)

        # Ensure AI Video panel is open in Key Frame mode
        ai_video_open = page.evaluate("""() => {
            var panel = document.querySelector('.ai-video-panel.show');
            return !!panel;
        }""")
        if not ai_video_open:
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

        # Step 1: Open model selector
        print("\n[1] Opening model selector panel...")
        page.evaluate("""() => {
            var wrapper = document.querySelector('.ai-video-panel .custom-selector-wrapper');
            if (wrapper) { wrapper.click(); return true; }
            return false;
        }""")
        page.wait_for_timeout(2000)

        page.screenshot(path=os.path.expanduser("~/Downloads/p142_model_panel.png"))

        # Step 2: Extract all models from the selector panel
        print("\n[2] Extracting all video models...")
        models = page.evaluate("""() => {
            var panel = document.querySelector('.selector-panel');
            if (!panel) return [];

            var items = [];
            // Find all model items/cards
            for (var el of panel.querySelectorAll('[class*="item"], [class*="card"], [class*="option"]')) {
                var r = el.getBoundingClientRect();
                if (r.width > 50 && r.height > 20 && r.width < 300) {
                    var text = (el.innerText || '').trim();
                    if (text.length > 3 && text.length < 300) {
                        items.push({
                            text: text,
                            x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height),
                            cls: (el.className || '').substring(0, 60),
                            tag: el.tagName
                        });
                    }
                }
            }
            return items;
        }""")

        print(f"[2] Found {len(models)} model items:")
        for m in models[:40]:
            print(f"\n  ({m['x']},{m['y']}) {m['w']}x{m['h']} <{m['tag']}> cls={m['cls'][:30]}")
            lines = m['text'].split('\n')
            for line in lines[:4]:
                if line.strip():
                    print(f"    {line.strip()[:80]}")

        # Step 3: Alternative — get structured data from each model card
        print("\n\n[3] Structured model data...")
        structured = page.evaluate("""() => {
            var panel = document.querySelector('.selector-panel');
            if (!panel) return [];

            var results = [];
            // Try to find model names and their associated specs
            var visited = new Set();
            for (var el of panel.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                // Look for elements that contain model name + specs pattern
                if (text.match(/\d+p/) && text.match(/\d+s/) && !visited.has(text)) {
                    visited.add(text);
                    var r = el.getBoundingClientRect();
                    if (r.width > 50 && r.height > 15 && r.width < 400) {
                        results.push({
                            text: text.substring(0, 200),
                            x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height),
                            cls: (el.className || '').substring(0, 40)
                        });
                    }
                }
            }
            return results;
        }""")
        print(f"[3] Model specs: {len(structured)}")
        for s in structured[:30]:
            print(f"  ({s['x']},{s['y']}) cls={s['cls'][:30]}")
            lines = s['text'].split('\n')
            for line in lines:
                if line.strip():
                    print(f"    {line.strip()[:80]}")

        # Step 4: Get the full text of the panel to parse manually
        print("\n[4] Full panel text...")
        full_text = page.evaluate("""() => {
            var panel = document.querySelector('.selector-panel');
            if (!panel) return '';
            return panel.innerText;
        }""")
        print(f"[4] Panel text ({len(full_text)} chars):\n{full_text[:4000]}")

        # Step 5: Check for scrollable content
        print("\n[5] Panel scroll info...")
        scroll_info = page.evaluate("""() => {
            var panel = document.querySelector('.selector-panel');
            if (!panel) return null;
            return {
                scrollTop: panel.scrollTop,
                scrollHeight: panel.scrollHeight,
                clientHeight: panel.clientHeight,
                overflow: window.getComputedStyle(panel).overflow
            };
        }""")
        print(f"[5] Scroll: {scroll_info}")

        # If scrollable, scroll down and get more content
        if scroll_info and scroll_info['scrollHeight'] > scroll_info['clientHeight']:
            print("[5] Panel is scrollable, scrolling down...")
            page.evaluate("""() => {
                var panel = document.querySelector('.selector-panel');
                if (panel) panel.scrollTop = panel.scrollHeight;
            }""")
            page.wait_for_timeout(1000)

            more_text = page.evaluate("""() => {
                var panel = document.querySelector('.selector-panel');
                if (!panel) return '';
                return panel.innerText;
            }""")
            # Print only new content
            if more_text != full_text:
                print(f"[5] After scroll ({len(more_text)} chars):\n{more_text[:4000]}")

        # Step 6: Look for scrollable sub-container
        print("\n[6] Check sub-containers...")
        sub_containers = page.evaluate("""() => {
            var panel = document.querySelector('.selector-panel');
            if (!panel) return [];
            var items = [];
            for (var el of panel.querySelectorAll('*')) {
                var s = window.getComputedStyle(el);
                if ((s.overflow === 'auto' || s.overflow === 'scroll' ||
                     s.overflowY === 'auto' || s.overflowY === 'scroll') &&
                    el.scrollHeight > el.clientHeight + 10) {
                    items.push({
                        tag: el.tagName,
                        cls: (el.className || '').substring(0, 60),
                        scrollTop: el.scrollTop,
                        scrollHeight: el.scrollHeight,
                        clientHeight: el.clientHeight,
                        text_length: (el.innerText || '').length
                    });
                }
            }
            return items;
        }""")
        print(f"[6] Scrollable sub-containers: {len(sub_containers)}")
        for c in sub_containers:
            print(f"  <{c['tag']}> cls={c['cls'][:40]} scroll={c['scrollTop']}/{c['scrollHeight']} client={c['clientHeight']} text={c['text_length']}")

        # Scroll any found sub-container and get full content
        if sub_containers:
            for i, container in enumerate(sub_containers[:2]):
                print(f"\n[6b] Scrolling sub-container {i}...")
                full = page.evaluate("""(cls) => {
                    for (var el of document.querySelectorAll('*')) {
                        var s = window.getComputedStyle(el);
                        if ((s.overflowY === 'auto' || s.overflowY === 'scroll') &&
                            el.scrollHeight > el.clientHeight + 10 &&
                            (el.className || '').includes(cls.substring(0, 20))) {
                            el.scrollTop = el.scrollHeight;
                            return el.innerText.substring(0, 5000);
                        }
                    }
                    return '';
                }""", container['cls'])
                if full:
                    print(f"[6b] After scroll:\n{full[:3000]}")

        page.screenshot(path=os.path.expanduser("~/Downloads/p142_full.png"), full_page=True)

        print("\n" + "=" * 70)
        print("PHASE 142 SUMMARY")
        print("=" * 70)

    finally:
        pw.stop()


if __name__ == "__main__":
    main()
