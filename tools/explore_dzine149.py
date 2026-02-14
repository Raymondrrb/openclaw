#!/usr/bin/env python3
"""Phase 149: Explore remaining Dzine features.

Remaining sidebar tools:
- Video Editor (#8, y=490) — video editing with AI models
- Motion Control (#9, y=551) — motion effects on images
- Instant Storyboard (#12, y=766) — multi-scene planning
- Chat Editor (bottom bar) — 20 credits, 5000 char prompt

Goals:
1. Open each panel, document interface, options, costs
2. Screenshot each for reference
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

_repo = Path(__file__).resolve().parent.parent
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))


def read_panel(page, label):
    """Read currently active panel content and interactive elements."""
    panel = page.evaluate("""() => {
        var panel = document.querySelector('.c-gen-config.show') ||
                    document.querySelector('.panels.show');
        if (panel) {
            return {
                text: panel.innerText.substring(0, 3000),
                cls: panel.className.substring(0, 80),
                x: Math.round(panel.getBoundingClientRect().x),
                y: Math.round(panel.getBoundingClientRect().y),
                w: Math.round(panel.getBoundingClientRect().width),
                h: Math.round(panel.getBoundingClientRect().height)
            };
        }
        return null;
    }""")
    if panel:
        print(f"[{label}] Panel: ({panel['x']},{panel['y']}) {panel['w']}x{panel['h']} cls={panel['cls'][:50]}")
        print(f"[{label}] Content:\n{panel['text'][:1500]}")
    else:
        print(f"[{label}] No panel found")
    return panel


def read_interactive(page, label):
    """Read interactive elements in left panel area."""
    elements = page.evaluate("""() => {
        var items = [];
        for (var el of document.querySelectorAll('button, input, textarea, select, [contenteditable], [role="button"], [role="tab"]')) {
            var r = el.getBoundingClientRect();
            if (r.width > 0 && r.height > 0 && r.x > 60 && r.x < 500 && r.y > 50 && r.y < 850) {
                var text = (el.innerText || el.placeholder || el.value || el.getAttribute('aria-label') || '').trim();
                items.push({
                    text: text.substring(0, 80),
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
    print(f"[{label}] Interactive: {len(elements)}")
    for e in elements[:25]:
        dis = " DISABLED" if e['disabled'] else ""
        print(f"  ({e['x']},{e['y']}) {e['w']}x{e['h']} <{e['tag']}> '{e['text'][:50]}' cls={e['cls'][:30]}{dis}")
    return elements


def close_panels(page):
    """Close all open panels."""
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)
    page.evaluate("""() => {
        for (var el of document.querySelectorAll('.c-gen-config.show .ico-close, .panels.show .ico-close')) el.click();
        var p = document.querySelector('.lip-sync-config-panel.show');
        if (p) { var c = p.querySelector('.ico-close'); if (c) c.click(); }
    }""")
    page.wait_for_timeout(500)


def open_sidebar_tool(page, y, name):
    """Open a sidebar tool by clicking at (40, y) with toggle technique."""
    print(f"\n{'='*60}")
    print(f"Opening {name} (y={y})")
    print(f"{'='*60}")
    close_panels(page)
    # Toggle via distant tool first
    page.mouse.click(40, 197 if y != 197 else 766)  # Txt2Img or Storyboard
    page.wait_for_timeout(1000)
    page.mouse.click(40, y)
    page.wait_for_timeout(3000)


def main():
    from playwright.sync_api import sync_playwright
    from tools.lib.brave_profile import DEFAULT_CDP_PORT, is_browser_running
    from tools.lib.dzine_browser import close_all_dialogs, VIEWPORT

    print("=" * 70)
    print("PHASE 149: Remaining Dzine Features")
    print("=" * 70)

    if not is_browser_running():
        print("[P149] ERROR: Brave not running.")
        return

    pw = sync_playwright().start()
    try:
        browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{DEFAULT_CDP_PORT}")
        context = browser.contexts[0]

        dzine_pages = [p for p in context.pages if "dzine.ai/canvas" in (p.url or "")]
        if not dzine_pages:
            print("[P149] No Dzine canvas found.")
            return

        page = dzine_pages[0]
        page.set_viewport_size(VIEWPORT)
        page.bring_to_front()
        page.wait_for_timeout(1500)
        print(f"[P149] Canvas: {page.url}")

        close_all_dialogs(page)
        page.wait_for_timeout(500)

        # ============================================================
        # 1. VIDEO EDITOR (sidebar #8, y=490)
        # ============================================================
        open_sidebar_tool(page, 490, "Video Editor")
        page.screenshot(path=os.path.expanduser("~/Downloads/p149_video_editor.png"))
        read_panel(page, "VideoEditor")
        read_interactive(page, "VideoEditor")

        # Check for model selector or options
        ve_models = page.evaluate("""() => {
            var items = [];
            var keywords = ['runway', 'kling', 'luma', 'pika', 'minimax', 'wan', 'veo',
                          'sora', 'model', 'gen-4', 'gen-3'];
            for (var el of document.querySelectorAll('.c-gen-config.show *, .panels.show *')) {
                var text = (el.innerText || '').trim().toLowerCase();
                for (var kw of keywords) {
                    if (text.includes(kw) && text.length < 100) {
                        var r = el.getBoundingClientRect();
                        if (r.width > 0 && r.x < 500) {
                            items.push({kw: kw, text: (el.innerText || '').trim().substring(0, 80),
                                        x: Math.round(r.x), y: Math.round(r.y)});
                        }
                        break;
                    }
                }
            }
            // Deduplicate
            var unique = [], seen = new Set();
            for (var item of items) {
                if (!seen.has(item.text)) { seen.add(item.text); unique.push(item); }
            }
            return unique;
        }""")
        print(f"\n[VideoEditor] Model references: {len(ve_models)}")
        for m in ve_models[:10]:
            print(f"  [{m['kw']}] ({m['x']},{m['y']}) '{m['text'][:60]}'")

        # ============================================================
        # 2. MOTION CONTROL (sidebar #9, y=551)
        # ============================================================
        open_sidebar_tool(page, 551, "Motion Control")
        page.screenshot(path=os.path.expanduser("~/Downloads/p149_motion_control.png"))
        read_panel(page, "MotionCtrl")
        read_interactive(page, "MotionCtrl")

        # ============================================================
        # 3. INSTANT STORYBOARD (sidebar #12, y=766)
        # ============================================================
        open_sidebar_tool(page, 766, "Instant Storyboard")
        page.screenshot(path=os.path.expanduser("~/Downloads/p149_storyboard.png"))
        read_panel(page, "Storyboard")
        read_interactive(page, "Storyboard")

        # ============================================================
        # 4. CHAT EDITOR (bottom bar)
        # ============================================================
        print(f"\n{'='*60}")
        print("Exploring Chat Editor (bottom bar)")
        print(f"{'='*60}")
        close_panels(page)

        # The Chat Editor is at the bottom of the canvas
        chat_editor = page.evaluate("""() => {
            // Find the contenteditable prompt in the bottom bar
            for (var el of document.querySelectorAll('[contenteditable="true"]')) {
                var r = el.getBoundingClientRect();
                if (r.y > 700 && r.width > 200) {
                    return {
                        tag: el.tagName,
                        placeholder: el.getAttribute('data-prompt') || el.getAttribute('placeholder') || '',
                        text: (el.innerText || '').trim().substring(0, 100),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        cls: (el.className || '').substring(0, 60)
                    };
                }
            }
            return null;
        }""")
        print(f"[ChatEditor] Prompt field: {chat_editor}")

        # Check for model selector in Chat Editor
        chat_model = page.evaluate("""() => {
            for (var el of document.querySelectorAll('button.option-btn, [class*="option-label"]')) {
                var r = el.getBoundingClientRect();
                if (r.y > 700 && r.width > 0) {
                    return {
                        text: (el.innerText || '').trim().substring(0, 80),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        cls: (el.className || '').substring(0, 50)
                    };
                }
            }
            return null;
        }""")
        print(f"[ChatEditor] Model selector: {chat_model}")

        # Click the model button to see options
        if chat_model:
            print("[ChatEditor] Clicking model selector...")
            page.mouse.click(chat_model['x'] + chat_model['w']//2,
                           chat_model['y'] + chat_model['h']//2)
            page.wait_for_timeout(2000)

            # Read model options
            chat_models = page.evaluate("""() => {
                var list = document.querySelector('.option-list');
                if (list) {
                    return {
                        text: list.innerText.substring(0, 1500),
                        x: Math.round(list.getBoundingClientRect().x),
                        y: Math.round(list.getBoundingClientRect().y),
                        w: Math.round(list.getBoundingClientRect().width),
                        h: Math.round(list.getBoundingClientRect().height)
                    };
                }
                return null;
            }""")
            if chat_models:
                print(f"[ChatEditor] Model list: ({chat_models['x']},{chat_models['y']}) {chat_models['w']}x{chat_models['h']}")
                print(f"[ChatEditor] Models:\n{chat_models['text'][:1000]}")

            page.screenshot(path=os.path.expanduser("~/Downloads/p149_chat_models.png"))
            page.keyboard.press("Escape")
            page.wait_for_timeout(500)

        # Check generate button
        chat_gen = page.evaluate("""() => {
            var btn = document.querySelector('#chat-editor-generate-btn');
            if (btn) {
                var r = btn.getBoundingClientRect();
                return {
                    text: btn.innerText.trim(),
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    disabled: btn.disabled,
                    cls: (btn.className || '').substring(0, 50)
                };
            }
            return null;
        }""")
        print(f"[ChatEditor] Generate button: {chat_gen}")

        # Check reference image upload in Chat Editor
        chat_ref = page.evaluate("""() => {
            var btn = document.querySelector('button.upload-image-btn.image-item');
            if (btn) {
                var r = btn.getBoundingClientRect();
                return {
                    text: (btn.innerText || '').trim(),
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width),
                    cls: (btn.className || '').substring(0, 50)
                };
            }
            return null;
        }""")
        print(f"[ChatEditor] Ref upload: {chat_ref}")

        page.screenshot(path=os.path.expanduser("~/Downloads/p149_chat_editor.png"))

        # ============================================================
        # SUMMARY
        # ============================================================
        page.screenshot(path=os.path.expanduser("~/Downloads/p149_final.png"), full_page=True)

        print("\n" + "=" * 70)
        print("PHASE 149 SUMMARY")
        print("=" * 70)
        print("Check ~/Downloads/p149_*.png for screenshots")

    finally:
        pw.stop()


if __name__ == "__main__":
    main()
