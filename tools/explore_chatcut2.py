#!/usr/bin/env python3
"""Explore ChatCut.io — Part 2: Deep dive into Seedance 2.0 feature.

From Part 1 we know:
- Seedance 2.0 is prominently featured ("Now Available" banner)
- Project creation options: Seedance 2.0, Edit talking head video, Create app promo, Create motion graphics
- 200 credits available
- Logged in already

Now explore:
1. Click "Seedance 2.0" to see what it offers
2. Check if it supports image-to-video (product images)
3. Check pricing/credits system
4. Test with an Amazon product image if possible
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

    print("=" * 70)
    print("ChatCut.io — Seedance 2.0 Exploration")
    print("=" * 70)

    if not is_browser_running():
        print("ERROR: Brave not running.")
        return

    pw = sync_playwright().start()
    try:
        browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{DEFAULT_CDP_PORT}")
        context = browser.contexts[0]

        # Find or open chatcut page
        chatcut_pages = [p for p in context.pages if "chatcut.io" in (p.url or "")]
        if chatcut_pages:
            page = chatcut_pages[0]
        else:
            page = context.new_page()

        page.set_viewport_size({"width": 1440, "height": 900})

        # Navigate to projects page
        page.goto("https://www.chatcut.io/projects", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(5000)

        print("[1] On projects page")
        page.screenshot(path=os.path.expanduser("~/Downloads/chatcut2_projects.png"))

        # Step 1: Click "Seedance 2.0" button/card
        print("\n[2] Clicking 'Seedance 2.0'...")
        clicked = page.evaluate("""() => {
            for (var el of document.querySelectorAll('button, [role="button"], div, span, a')) {
                var text = (el.innerText || '').trim();
                if (text === 'Seedance 2.0' || text.startsWith('Seedance 2.0')) {
                    var r = el.getBoundingClientRect();
                    if (r.width > 0 && r.height > 0) {
                        el.click();
                        return {ok: true, text: text, x: Math.round(r.x), y: Math.round(r.y)};
                    }
                }
            }
            return {ok: false};
        }""")
        print(f"[2] Click result: {clicked}")
        page.wait_for_timeout(5000)
        page.screenshot(path=os.path.expanduser("~/Downloads/chatcut2_seedance.png"))

        # Step 2: Examine what opened
        print("\n[3] Examining Seedance 2.0 interface...")
        content = page.evaluate("""() => {
            return document.body.innerText.substring(0, 3000);
        }""")
        print(f"[3] Page content:\n{content[:2000]}")

        # Step 3: Look for input options (text, image, etc.)
        print("\n[4] Looking for input options...")
        inputs = page.evaluate("""() => {
            var items = [];
            for (var el of document.querySelectorAll('input, textarea, [contenteditable], button, [role="button"], label')) {
                var text = (el.innerText || el.placeholder || el.value || el.getAttribute('aria-label') || '').trim();
                var r = el.getBoundingClientRect();
                if (text && r.width > 0) {
                    items.push({
                        text: text.substring(0, 80),
                        tag: el.tagName,
                        type: el.type || '',
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height)
                    });
                }
            }
            return items;
        }""")
        print(f"[4] Input elements: {len(inputs)}")
        for i in inputs[:20]:
            print(f"  ({i['x']},{i['y']}) {i['w']}x{i['h']} <{i['tag']}> type={i['type']} '{i['text']}'")

        # Step 4: Check for image upload capability
        print("\n[5] Looking for image upload / image-to-video...")
        upload_elements = page.evaluate("""() => {
            var items = [];
            for (var el of document.querySelectorAll('*')) {
                var text = (el.innerText || '').trim().toLowerCase();
                if ((text.includes('upload') || text.includes('image') || text.includes('photo') ||
                     text.includes('reference') || text.includes('drag') || text.includes('drop')) &&
                    text.length < 100) {
                    var r = el.getBoundingClientRect();
                    if (r.width > 0) {
                        items.push({
                            text: (el.innerText || '').trim().substring(0, 80),
                            tag: el.tagName,
                            x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width)
                        });
                    }
                }
            }
            return items;
        }""")
        print(f"[5] Upload/image elements: {len(upload_elements)}")
        for e in upload_elements[:15]:
            print(f"  <{e['tag']}> ({e['x']},{e['y']}) w={e['w']} '{e['text']}'")

        # Step 5: Look for tabs/modes (text-to-video, image-to-video)
        print("\n[6] Looking for mode tabs...")
        tabs = page.evaluate("""() => {
            var items = [];
            for (var el of document.querySelectorAll('[role="tab"], [class*="tab"], [class*="mode"], [class*="option"]')) {
                var text = (el.innerText || '').trim();
                var r = el.getBoundingClientRect();
                if (text && r.width > 0) {
                    items.push({
                        text: text.substring(0, 50),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width),
                        cls: (el.className || '').substring(0, 60)
                    });
                }
            }
            return items;
        }""")
        print(f"[6] Tab/mode elements: {len(tabs)}")
        for t in tabs[:15]:
            print(f"  ({t['x']},{t['y']}) w={t['w']} '{t['text']}' cls={t['cls'][:40]}")

        # Step 6: Check current URL and page state
        print(f"\n[7] Current URL: {page.url}")

        # Step 7: Take a full-page screenshot for detailed analysis
        page.screenshot(path=os.path.expanduser("~/Downloads/chatcut2_full.png"), full_page=True)

        # Step 8: Look for video generation settings
        print("\n[8] Looking for generation settings...")
        gen_settings = page.evaluate("""() => {
            var items = [];
            var keywords = ['resolution', 'duration', 'aspect', 'ratio', 'quality',
                          'style', 'model', 'credits', 'generate', 'create', 'render',
                          'seedance', 'prompt', 'description', 'motion', 'camera'];
            for (var el of document.querySelectorAll('*')) {
                var text = (el.innerText || '').trim().toLowerCase();
                for (var kw of keywords) {
                    if (text.includes(kw) && text.length < 100) {
                        var r = el.getBoundingClientRect();
                        if (r.width > 0) {
                            items.push({
                                kw: kw,
                                text: (el.innerText || '').trim().substring(0, 80),
                                x: Math.round(r.x), y: Math.round(r.y)
                            });
                        }
                        break;
                    }
                }
            }
            // Deduplicate by text
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
        print(f"[8] Generation settings: {len(gen_settings)}")
        for s in gen_settings[:20]:
            print(f"  [{s['kw']}] ({s['x']},{s['y']}) '{s['text']}'")

        page.close()

    finally:
        pw.stop()


if __name__ == "__main__":
    main()
