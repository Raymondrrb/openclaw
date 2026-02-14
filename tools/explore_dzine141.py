#!/usr/bin/env python3
"""Phase 141: AI Video deep dive — model list + Reference mode.

From P140:
- AI Video panel has 2 modes: Key Frame (default) and Reference
- Frame modes: Start and Last, AnyFrame
- Default: Kling 2.5 Turbo STD, Auto, 720p, 5s, 30 credits
- 8.856 video credits available
- Model selector at (92, 434), class=custom-selector-wrapper

Goals:
1. Click model selector to see ALL available video models
2. Document each model's specs (resolution, duration, credits)
3. Switch to Reference mode and see what options differ
4. Check if any models cost <= 8 credits (within budget)
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
    print("PHASE 141: AI Video — Models & Reference Mode")
    print("=" * 70)

    if not is_browser_running():
        print("[P141] ERROR: Brave not running.")
        return

    pw = sync_playwright().start()
    try:
        browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{DEFAULT_CDP_PORT}")
        context = browser.contexts[0]

        dzine_pages = [p for p in context.pages if "dzine.ai/canvas" in (p.url or "")]
        if not dzine_pages:
            print("[P141] No Dzine canvas found.")
            return

        page = dzine_pages[0]
        page.set_viewport_size(VIEWPORT)
        page.bring_to_front()
        page.wait_for_timeout(1500)
        print(f"[P141] Canvas: {page.url}")

        close_all_dialogs(page)
        page.wait_for_timeout(500)

        # Ensure AI Video panel is open
        ai_video_open = page.evaluate("""() => {
            var panel = document.querySelector('.ai-video-panel');
            return panel && panel.classList.contains('show');
        }""")
        if not ai_video_open:
            print("[P141] Opening AI Video panel...")
            page.mouse.click(40, 766)
            page.wait_for_timeout(1000)
            page.mouse.click(40, 361)
            page.wait_for_timeout(2000)

        # Step 1: Click the model selector dropdown
        print("\n[1] Clicking model selector...")
        page.evaluate("""() => {
            var sel = document.querySelector('.ai-video-panel .custom-selector-wrapper .selected-btn');
            if (sel) { sel.click(); return true; }
            return false;
        }""")
        page.wait_for_timeout(2000)

        page.screenshot(path=os.path.expanduser("~/Downloads/p141_model_dropdown.png"))

        # Step 2: Read all model options
        print("\n[2] Reading model options...")
        model_list = page.evaluate("""() => {
            var items = [];
            // Look for dropdown list items
            for (var el of document.querySelectorAll('.option-item, .custom-selector-item, [class*="selector-item"], [class*="option-list"] *, [class*="dropdown-item"]')) {
                var text = (el.innerText || '').trim();
                var r = el.getBoundingClientRect();
                if (text && r.width > 0 && r.height > 0) {
                    items.push({
                        text: text.substring(0, 200),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        cls: (el.className || '').substring(0, 60),
                        tag: el.tagName
                    });
                }
            }
            return items;
        }""")
        print(f"[2] Model options: {len(model_list)}")
        for m in model_list[:30]:
            print(f"  ({m['x']},{m['y']}) {m['w']}x{m['h']} <{m['tag']}> cls={m['cls'][:40]}")
            lines = m['text'].split('\n')
            for line in lines[:3]:
                if line.strip():
                    print(f"    {line.strip()[:80]}")

        # If no options found, try broader search
        if len(model_list) < 2:
            print("\n[2b] Broader search for dropdown...")
            dropdown = page.evaluate("""() => {
                var items = [];
                // Check for any popup/dropdown that appeared
                for (var el of document.querySelectorAll('*')) {
                    var r = el.getBoundingClientRect();
                    var s = window.getComputedStyle(el);
                    if (r.width > 150 && r.height > 200 && r.x > 60 && r.x < 500 &&
                        r.y > 300 && r.y < 800 &&
                        (s.position === 'absolute' || s.position === 'fixed' || parseInt(s.zIndex) > 100)) {
                        items.push({
                            text: (el.innerText || '').substring(0, 1000),
                            x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height),
                            cls: (el.className || '').substring(0, 80),
                            zIndex: s.zIndex
                        });
                    }
                }
                return items;
            }""")
            print(f"[2b] Popups found: {len(dropdown)}")
            for d in dropdown[:5]:
                print(f"  ({d['x']},{d['y']}) {d['w']}x{d['h']} z={d['zIndex']} cls={d['cls'][:50]}")
                lines = d['text'].split('\n')
                for line in lines[:20]:
                    if line.strip():
                        print(f"    {line.strip()[:100]}")

        # Step 3: Try a direct click on the model selector button element
        print("\n[3] Click .selected-btn directly...")
        page.mouse.click(140, 448)  # Center of the model selector
        page.wait_for_timeout(2000)

        # Check for dropdown list
        dropdown2 = page.evaluate("""() => {
            var list = document.querySelector('.custom-selector-list') ||
                       document.querySelector('[class*="selector-list"]') ||
                       document.querySelector('.option-list');
            if (list) {
                var r = list.getBoundingClientRect();
                return {
                    text: list.innerText.substring(0, 2000),
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    cls: list.className,
                    childCount: list.children.length
                };
            }
            return null;
        }""")
        if dropdown2:
            print(f"[3] Dropdown list: ({dropdown2['x']},{dropdown2['y']}) {dropdown2['w']}x{dropdown2['h']} children={dropdown2['childCount']}")
            print(f"[3] cls={dropdown2['cls']}")
            print(f"[3] Content:")
            lines = dropdown2['text'].split('\n')
            for line in lines[:30]:
                if line.strip():
                    print(f"    {line.strip()[:100]}")
        else:
            print("[3] No dropdown list found")

        page.screenshot(path=os.path.expanduser("~/Downloads/p141_model_click.png"))

        # Step 4: Check ALL elements with class containing "selector" or "list" near the panel
        print("\n[4] Scanning for selector elements...")
        selectors = page.evaluate("""() => {
            var items = [];
            for (var el of document.querySelectorAll('[class*="selector"], [class*="option-list"], [class*="dropdown"]')) {
                var r = el.getBoundingClientRect();
                var s = window.getComputedStyle(el);
                if (r.width > 0) {
                    items.push({
                        text: (el.innerText || '').substring(0, 500),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        cls: el.className.substring(0, 80),
                        display: s.display,
                        visibility: s.visibility,
                        overflow: s.overflow,
                        maxHeight: s.maxHeight,
                        children: el.children.length
                    });
                }
            }
            return items;
        }""")
        print(f"[4] Selector elements: {len(selectors)}")
        for s in selectors[:10]:
            print(f"  ({s['x']},{s['y']}) {s['w']}x{s['h']} display={s['display']} vis={s['visibility']} overflow={s['overflow']} maxH={s['maxHeight']} children={s['children']}")
            print(f"    cls={s['cls'][:60]}")
            if s['text']:
                lines = s['text'].split('\n')
                for line in lines[:5]:
                    if line.strip():
                        print(f"    {line.strip()[:80]}")

        # Step 5: Switch to Reference mode
        print("\n[5] Switching to Reference mode...")
        page.keyboard.press("Escape")  # Close any dropdown first
        page.wait_for_timeout(500)

        page.evaluate("""() => {
            for (var btn of document.querySelectorAll('button.options')) {
                if ((btn.innerText || '').trim() === 'Reference') {
                    btn.click();
                    return true;
                }
            }
            return false;
        }""")
        page.wait_for_timeout(2000)

        page.screenshot(path=os.path.expanduser("~/Downloads/p141_reference_mode.png"))

        # Read Reference mode content
        ref_content = page.evaluate("""() => {
            var panel = document.querySelector('.ai-video-panel.show') ||
                        document.querySelector('.c-gen-config.show');
            if (panel) return panel.innerText.substring(0, 3000);
            return '';
        }""")
        print(f"[5] Reference mode content:\n{ref_content[:1500]}")

        # Read Reference mode interactive elements
        ref_elements = page.evaluate("""() => {
            var items = [];
            for (var el of document.querySelectorAll('button, input, textarea, [role="button"]')) {
                var r = el.getBoundingClientRect();
                if (r.width > 0 && r.height > 0 && r.x > 60 && r.x < 400 && r.y > 50 && r.y < 850) {
                    var text = (el.innerText || el.placeholder || el.value || '').trim();
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
        print(f"\n[5b] Reference mode elements: {len(ref_elements)}")
        for e in ref_elements[:20]:
            dis = " DISABLED" if e['disabled'] else ""
            print(f"  ({e['x']},{e['y']}) {e['w']}x{e['h']} <{e['tag']}> '{e['text'][:50]}' cls={e['cls'][:30]}{dis}")

        # Step 6: Switch back to Key Frame and try clicking the model text
        print("\n[6] Switch back to Key Frame and click model name text...")
        page.evaluate("""() => {
            for (var btn of document.querySelectorAll('button.options')) {
                if ((btn.innerText || '').trim() === 'Key Frame') {
                    btn.click();
                    return true;
                }
            }
            return false;
        }""")
        page.wait_for_timeout(1500)

        # Click the selected-name-text span directly
        page.evaluate("""() => {
            var el = document.querySelector('.ai-video-panel .selected-name-text');
            if (el) { el.click(); return true; }
            return false;
        }""")
        page.wait_for_timeout(2000)

        page.screenshot(path=os.path.expanduser("~/Downloads/p141_model_text_click.png"))

        # Check for opened dropdown
        dropdown3 = page.evaluate("""() => {
            var items = [];
            // Look for ANY new visible element that could be a dropdown
            for (var el of document.querySelectorAll('*')) {
                var r = el.getBoundingClientRect();
                var s = window.getComputedStyle(el);
                // Large overlay/popup near the selector
                if (r.width > 100 && r.height > 100 && r.x > 50 && r.x < 500 &&
                    r.y > 400 && r.y < 900 &&
                    s.display !== 'none' && s.visibility !== 'hidden' &&
                    (s.position === 'absolute' || s.position === 'fixed' || parseInt(s.zIndex) > 50)) {
                    var text = (el.innerText || '').substring(0, 500);
                    if (text.length > 20) {
                        items.push({
                            text: text,
                            x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height),
                            cls: (el.className || '').substring(0, 80),
                            zIndex: s.zIndex
                        });
                    }
                }
            }
            return items;
        }""")
        print(f"[6] Dropdowns after click: {len(dropdown3)}")
        for d in dropdown3[:5]:
            print(f"  ({d['x']},{d['y']}) {d['w']}x{d['h']} z={d['zIndex']} cls={d['cls'][:50]}")
            lines = d['text'].split('\n')
            for line in lines[:15]:
                if line.strip():
                    print(f"    {line.strip()[:100]}")

        # Step 7: Try clicking the wrapper div itself
        print("\n[7] Click custom-selector-wrapper directly...")
        page.evaluate("""() => {
            var wrapper = document.querySelector('.ai-video-panel .custom-selector-wrapper');
            if (wrapper) { wrapper.click(); return true; }
            return false;
        }""")
        page.wait_for_timeout(2000)

        page.screenshot(path=os.path.expanduser("~/Downloads/p141_wrapper_click.png"))

        # Check the wrapper's children for hidden list
        wrapper_info = page.evaluate("""() => {
            var wrapper = document.querySelector('.ai-video-panel .custom-selector-wrapper');
            if (!wrapper) return null;
            var children = [];
            for (var child of wrapper.children) {
                var r = child.getBoundingClientRect();
                var s = window.getComputedStyle(child);
                children.push({
                    tag: child.tagName,
                    cls: (child.className || '').substring(0, 60),
                    text: (child.innerText || '').substring(0, 200),
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    display: s.display,
                    overflow: s.overflow
                });
            }
            return {
                cls: wrapper.className,
                children: children,
                innerHTML_length: wrapper.innerHTML.length
            };
        }""")
        if wrapper_info:
            print(f"[7] Wrapper cls: {wrapper_info['cls']}")
            print(f"[7] innerHTML length: {wrapper_info['innerHTML_length']}")
            for c in wrapper_info['children']:
                print(f"  <{c['tag']}> cls={c['cls'][:40]} ({c['x']},{c['y']}) {c['w']}x{c['h']} display={c['display']} overflow={c['overflow']}")
                if c['text']:
                    lines = c['text'].split('\n')
                    for line in lines[:5]:
                        if line.strip():
                            print(f"    {line.strip()[:80]}")

        # Final full-page screenshot
        page.screenshot(path=os.path.expanduser("~/Downloads/p141_full.png"), full_page=True)

        print("\n" + "=" * 70)
        print("PHASE 141 SUMMARY")
        print("=" * 70)
        print("Check ~/Downloads/p141_*.png for screenshots")

    finally:
        pw.stop()


if __name__ == "__main__":
    main()
