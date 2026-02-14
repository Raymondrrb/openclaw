#!/usr/bin/env python3
"""Explore ChatCut.io — Part 3: Click Seedance 2.0 button precisely and explore the workflow.

From Part 2:
- "BETA Seedance 2.0" button at (384, 601)
- "Add your media" at (386, 413)
- 200 credits available
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
    print("ChatCut.io — Seedance 2.0 Deep Dive")
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
        page.goto("https://www.chatcut.io/projects", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(4000)

        # Click the "BETA Seedance 2.0" button precisely
        print("[1] Clicking 'Seedance 2.0' button...")
        page.evaluate("""() => {
            for (var el of document.querySelectorAll('button')) {
                var text = (el.innerText || '').trim();
                if (text.includes('Seedance 2.0')) {
                    el.click();
                    return true;
                }
            }
            return false;
        }""")
        page.wait_for_timeout(5000)

        new_url = page.url
        print(f"[1] URL after click: {new_url}")
        page.screenshot(path=os.path.expanduser("~/Downloads/chatcut3_seedance.png"))

        # Check what's on the page now
        content = page.evaluate("""() => {
            return document.body.innerText.substring(0, 4000);
        }""")
        print(f"[2] Page content:\n{content[:2500]}")

        # Look for all interactive elements
        print("\n[3] Interactive elements...")
        elements = page.evaluate("""() => {
            var items = [];
            for (var el of document.querySelectorAll('button, input, textarea, select, [contenteditable], [role="button"], [role="tab"]')) {
                var text = (el.innerText || el.placeholder || el.value || el.getAttribute('aria-label') || '').trim();
                var r = el.getBoundingClientRect();
                if (r.width > 0 && r.height > 0) {
                    items.push({
                        text: text.substring(0, 80),
                        tag: el.tagName,
                        type: el.type || '',
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        cls: (el.className || '').substring(0, 50)
                    });
                }
            }
            return items;
        }""")
        print(f"[3] Found {len(elements)} elements:")
        for e in elements[:25]:
            print(f"  ({e['x']},{e['y']}) {e['w']}x{e['h']} <{e['tag']}> type={e['type']} '{e['text'][:60]}' cls={e['cls'][:30]}")

        # Look for tabs: text-to-video, image-to-video
        print("\n[4] Looking for generation mode options...")
        modes = page.evaluate("""() => {
            var items = [];
            var keywords = ['text', 'image', 'video', 'reference', 'prompt', 'describe',
                          'generate', 'create', 'start', 'upload', 'camera', 'motion',
                          'aspect', 'ratio', 'duration', 'style', 'seed', 'model'];
            for (var el of document.querySelectorAll('*')) {
                var text = (el.innerText || '').trim().toLowerCase();
                for (var kw of keywords) {
                    if (text === kw || (text.startsWith(kw) && text.length < 30)) {
                        var r = el.getBoundingClientRect();
                        if (r.width > 0 && r.height > 0 && r.width < 400) {
                            items.push({
                                text: (el.innerText || '').trim().substring(0, 50),
                                x: Math.round(r.x), y: Math.round(r.y),
                                w: Math.round(r.width), h: Math.round(r.height),
                                tag: el.tagName,
                                cls: (el.className || '').substring(0, 40)
                            });
                            break;
                        }
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
        print(f"[4] Mode elements: {len(modes)}")
        for m in modes[:20]:
            print(f"  ({m['x']},{m['y']}) {m['w']}x{m['h']} <{m['tag']}> '{m['text']}' cls={m['cls']}")

        # Check for file upload / drag-drop areas
        print("\n[5] File upload areas...")
        uploads = page.evaluate("""() => {
            var items = [];
            for (var el of document.querySelectorAll('input[type="file"], [class*="upload"], [class*="drop"], [class*="dropzone"]')) {
                var r = el.getBoundingClientRect();
                items.push({
                    tag: el.tagName,
                    type: el.type || '',
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    cls: (el.className || '').substring(0, 60),
                    accept: el.accept || '',
                    text: (el.innerText || '').trim().substring(0, 80)
                });
            }
            return items;
        }""")
        print(f"[5] Upload elements: {len(uploads)}")
        for u in uploads:
            print(f"  <{u['tag']}> ({u['x']},{u['y']}) {u['w']}x{u['h']} accept={u['accept']} cls={u['cls']} '{u['text']}'")

        # Try looking at the "Add your media" area
        print("\n[6] Checking 'Add your media' area...")
        media_area = page.evaluate("""() => {
            for (var el of document.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                if (text.includes('Add your media')) {
                    var r = el.getBoundingClientRect();
                    return {
                        text: text.substring(0, 200),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        tag: el.tagName,
                        cls: (el.className || '').substring(0, 80),
                        html: el.outerHTML.substring(0, 300)
                    };
                }
            }
            return null;
        }""")
        if media_area:
            print(f"[6] Media area: ({media_area['x']},{media_area['y']}) {media_area['w']}x{media_area['h']}")
            print(f"    Text: {media_area['text'][:100]}")
            print(f"    HTML: {media_area['html'][:200]}")

        # Check if there's a prompt/text input for the video description
        print("\n[7] Looking for prompt/text input...")
        prompt_area = page.evaluate("""() => {
            for (var el of document.querySelectorAll('textarea, input[type="text"], [contenteditable="true"]')) {
                var r = el.getBoundingClientRect();
                if (r.width > 200) {
                    return {
                        tag: el.tagName,
                        placeholder: el.placeholder || '',
                        value: (el.value || el.innerText || '').trim().substring(0, 100),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        cls: (el.className || '').substring(0, 60)
                    };
                }
            }
            return null;
        }""")
        if prompt_area:
            print(f"[7] Prompt: ({prompt_area['x']},{prompt_area['y']}) {prompt_area['w']}x{prompt_area['h']}")
            print(f"    Placeholder: {prompt_area['placeholder']}")
            print(f"    Class: {prompt_area['cls']}")

        page.screenshot(path=os.path.expanduser("~/Downloads/chatcut3_full.png"), full_page=True)

    finally:
        pw.stop()


if __name__ == "__main__":
    main()
