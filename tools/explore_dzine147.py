#!/usr/bin/env python3
"""Phase 147: Explore Expression Edit and Face Swap.

From the UI map:
- Expression Edit: Results panel action row + sidebar tool at y=628 area
- Face Swap: Results panel action row
- Both operate on existing result images
- Expression Edit costs 4 credits
- Face Swap unknown cost

Goals:
1. Check Expression Edit interface via Results panel button
2. Check Face Swap interface via Results panel button
3. Document options, costs, and potential for avatar animation
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
    print("PHASE 147: Expression Edit & Face Swap")
    print("=" * 70)

    if not is_browser_running():
        print("[P147] ERROR: Brave not running.")
        return

    pw = sync_playwright().start()
    try:
        browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{DEFAULT_CDP_PORT}")
        context = browser.contexts[0]

        dzine_pages = [p for p in context.pages if "dzine.ai/canvas" in (p.url or "")]
        if not dzine_pages:
            print("[P147] No Dzine canvas found.")
            return

        page = dzine_pages[0]
        page.set_viewport_size(VIEWPORT)
        page.bring_to_front()
        page.wait_for_timeout(1500)
        print(f"[P147] Canvas: {page.url}")

        close_all_dialogs(page)
        page.wait_for_timeout(500)

        # Dismiss any open pick dialog
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)

        # Make sure results tab is active
        page.evaluate("""() => {
            for (var el of document.querySelectorAll('[class*="header-item"]')) {
                if ((el.innerText || '').includes('Result')) { el.click(); return; }
            }
        }""")
        page.wait_for_timeout(500)

        # Close any AI Video panel
        page.evaluate("""() => {
            var close = document.querySelector('.ai-video-panel .ico-close');
            if (close) close.click();
        }""")
        page.wait_for_timeout(500)

        # List all action rows in Results panel
        print("\n[1] All Results panel action rows...")
        actions = page.evaluate("""() => {
            var items = [];
            for (var el of document.querySelectorAll('.gen-handle-function')) {
                var text = (el.innerText || '').trim();
                var r = el.getBoundingClientRect();
                if (r.width > 0 && r.x > 1000) {
                    items.push({
                        text: text.substring(0, 100),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height)
                    });
                }
            }
            return items;
        }""")
        print(f"[1] Action rows: {len(actions)}")
        for a in actions[:20]:
            print(f"  ({a['x']},{a['y']}) {a['w']}x{a['h']} '{a['text'][:60]}'")

        # Step 2: Click Expression Edit [1] from results
        print("\n[2] Clicking Expression Edit [1]...")
        expr_click = page.evaluate("""() => {
            for (var el of document.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                if ((text === 'Expression Edit' || text === 'Expression\\nEdit') && el.childElementCount === 0) {
                    var r = el.getBoundingClientRect();
                    if (r.x > 1000 && r.y > 600) {
                        var labelCy = r.y + r.height / 2;
                        for (var btn of document.querySelectorAll('button.btn')) {
                            var br = btn.getBoundingClientRect();
                            if ((btn.innerText || '').trim() === '1' &&
                                br.x > 1200 && Math.abs(br.y + br.height/2 - labelCy) < 15) {
                                btn.click();
                                return {ok: true, labelY: Math.round(r.y), btnX: Math.round(br.x), btnY: Math.round(br.y)};
                            }
                        }
                        return {ok: false, reason: 'button not found', labelY: Math.round(r.y)};
                    }
                }
            }
            return {ok: false, reason: 'label not found'};
        }""")
        print(f"[2] Click: {expr_click}")
        page.wait_for_timeout(4000)

        page.screenshot(path=os.path.expanduser("~/Downloads/p147_expression_edit.png"))

        # Check what opened
        print("\n[2b] Expression Edit panel/dialog...")
        expr_panel = page.evaluate("""() => {
            // Check for any panel that mentions expression
            for (var el of document.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                if (text.includes('Expression') && text.length > 20 && text.length < 500) {
                    var r = el.getBoundingClientRect();
                    var s = window.getComputedStyle(el);
                    if (r.width > 200 && r.height > 100 &&
                        (r.x > 60 && r.x < 500 || r.x > 300 && r.x < 800)) {
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
        if expr_panel:
            print(f"[2b] Panel: ({expr_panel['x']},{expr_panel['y']}) {expr_panel['w']}x{expr_panel['h']}")
            print(f"     cls: {expr_panel['cls']}")
            print(f"     Content:\n{expr_panel['text'][:500]}")
        else:
            print("[2b] No Expression Edit panel found")

        # Check for any new panels, dialogs, or overlays
        new_elements = page.evaluate("""() => {
            var items = [];
            for (var el of document.querySelectorAll('.c-gen-config.show, .panels.show, [class*="expression"]')) {
                var r = el.getBoundingClientRect();
                if (r.width > 100) {
                    items.push({
                        cls: (el.className || '').substring(0, 80),
                        text: (el.innerText || '').substring(0, 300),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height)
                    });
                }
            }
            return items;
        }""")
        print(f"\n[2c] Active panels: {len(new_elements)}")
        for e in new_elements[:5]:
            print(f"  ({e['x']},{e['y']}) {e['w']}x{e['h']} cls={e['cls'][:50]}")
            lines = e['text'].split('\n')
            for line in lines[:5]:
                if line.strip():
                    print(f"    {line.strip()[:80]}")

        # Step 3: Look at interactive elements in Expression Edit area
        print("\n[3] Interactive elements in panel area...")
        interactive = page.evaluate("""() => {
            var items = [];
            for (var el of document.querySelectorAll('button, input, textarea, select, [contenteditable], [role="button"]')) {
                var r = el.getBoundingClientRect();
                if (r.width > 0 && r.height > 0 && r.x > 60 && r.x < 500 && r.y > 50 && r.y < 850) {
                    var text = (el.innerText || el.placeholder || el.value || '').trim();
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
        print(f"[3] Elements: {len(interactive)}")
        for e in interactive[:20]:
            print(f"  ({e['x']},{e['y']}) {e['w']}x{e['h']} <{e['tag']}> '{e['text'][:50]}' cls={e['cls'][:30]}")

        # Step 4: Check if canvas changed (Expression Edit might alter canvas view)
        print("\n[4] Canvas state...")
        canvas_state = page.evaluate("""() => {
            // Check for back arrow (means we're in a sub-mode)
            for (var el of document.querySelectorAll('[class*="back"], [class*="arrow"]')) {
                var text = (el.innerText || '').trim();
                var r = el.getBoundingClientRect();
                if (r.width > 0 && r.x < 100 && r.y > 50 && r.y < 150) {
                    return {mode: 'sub-mode', backBtn: {x: Math.round(r.x), y: Math.round(r.y), cls: (el.className || '').substring(0, 40)}};
                }
            }
            return {mode: 'normal'};
        }""")
        print(f"[4] Canvas: {canvas_state}")

        # Step 5: Close Expression Edit and try Face Swap
        print("\n[5] Closing Expression Edit...")
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)
        page.evaluate("""() => {
            // Close any gen-config panels
            for (var el of document.querySelectorAll('.c-gen-config.show .ico-close')) el.click();
        }""")
        page.wait_for_timeout(500)

        # Click Face Swap [1]
        print("\n[5] Clicking Face Swap [1]...")
        face_click = page.evaluate("""() => {
            for (var el of document.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                if ((text === 'Face Swap' || text === 'Face\\nSwap') && el.childElementCount === 0) {
                    var r = el.getBoundingClientRect();
                    if (r.x > 1000 && r.y > 600) {
                        var labelCy = r.y + r.height / 2;
                        for (var btn of document.querySelectorAll('button.btn')) {
                            var br = btn.getBoundingClientRect();
                            if ((btn.innerText || '').trim() === '1' &&
                                br.x > 1200 && Math.abs(br.y + br.height/2 - labelCy) < 15) {
                                btn.click();
                                return {ok: true, labelY: Math.round(r.y), btnX: Math.round(br.x), btnY: Math.round(br.y)};
                            }
                        }
                        return {ok: false, reason: 'button not found'};
                    }
                }
            }
            return {ok: false, reason: 'label not found'};
        }""")
        print(f"[5] Face Swap click: {face_click}")
        page.wait_for_timeout(4000)

        page.screenshot(path=os.path.expanduser("~/Downloads/p147_face_swap.png"))

        # Check Face Swap panel
        face_panel = page.evaluate("""() => {
            for (var el of document.querySelectorAll('.c-gen-config.show, .panels.show, [class*="face-swap"], [class*="faceswap"]')) {
                var r = el.getBoundingClientRect();
                if (r.width > 100) {
                    return {
                        cls: (el.className || '').substring(0, 80),
                        text: (el.innerText || '').substring(0, 500),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height)
                    };
                }
            }
            return null;
        }""")
        if face_panel:
            print(f"\n[5b] Face Swap panel: ({face_panel['x']},{face_panel['y']}) {face_panel['w']}x{face_panel['h']}")
            print(f"     cls: {face_panel['cls']}")
            print(f"     Content:\n{face_panel['text'][:500]}")
        else:
            print("[5b] No Face Swap panel found")

        # Check ALL visible panels and dialogs
        print("\n[6] All visible panels after Face Swap click...")
        all_panels = page.evaluate("""() => {
            var items = [];
            for (var el of document.querySelectorAll('*')) {
                var r = el.getBoundingClientRect();
                var s = window.getComputedStyle(el);
                if (r.width > 200 && r.height > 150 &&
                    r.x > 60 && r.x < 800 && r.y > 30 && r.y < 700 &&
                    s.display !== 'none' && s.visibility !== 'hidden' &&
                    (s.position === 'fixed' || s.position === 'absolute' || parseInt(s.zIndex) > 100)) {
                    var text = (el.innerText || '').trim();
                    if (text.length > 20) {
                        items.push({
                            text: text.substring(0, 300),
                            x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height),
                            cls: (el.className || '').substring(0, 80),
                            zIndex: s.zIndex
                        });
                    }
                }
            }
            // Deduplicate by position
            var unique = [];
            var seen = new Set();
            for (var item of items) {
                var key = item.x + '_' + item.y + '_' + item.w;
                if (!seen.has(key)) {
                    seen.add(key);
                    unique.push(item);
                }
            }
            return unique;
        }""")
        print(f"[6] Panels: {len(all_panels)}")
        for p in all_panels[:5]:
            print(f"  ({p['x']},{p['y']}) {p['w']}x{p['h']} z={p['zIndex']} cls={p['cls'][:40]}")
            lines = p['text'].split('\n')
            for line in lines[:5]:
                if line.strip():
                    print(f"    {line.strip()[:80]}")

        page.screenshot(path=os.path.expanduser("~/Downloads/p147_final.png"), full_page=True)

        print("\n" + "=" * 70)
        print("PHASE 147 SUMMARY")
        print("=" * 70)

    finally:
        pw.stop()


if __name__ == "__main__":
    main()
