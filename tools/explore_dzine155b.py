#!/usr/bin/env python3
"""Phase 155b: Instant Storyboard — Deep dive: V1/V2, Hints, @mentions, upload.

Follows up on Phase 155 initial exploration. Now we know:
- Panel class: c-gen-config show float-gen-btn float-storyboard-gen-btn
- V1/V2 toggle, currently V2 is selected
- Prompt: contenteditable div, cls=custom-textarea len-1000
- Prompt placeholder: "Descreva sua cena, use '@' para adicionar elementos..."
- Image upload: button.upload-image-btn.image-item at (105,162)
- Hints: 3 preset thumbnails at .storyboard-preset area
- Aspect Ratio: 9:16, 1:1, 16:9 + "more" dropdown
- Generate: button#instant-storyboard-generate-btn, 6 credits
- No style selector in Storyboard panel

This script explores:
1. V1 mode differences (switch and compare)
2. Hint presets (click each, see prompt/images change)
3. Upload an image and test @mention autocomplete
4. Aspect ratio "more" dropdown
5. All DOM selectors for automation
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

_repo = Path(__file__).resolve().parent.parent
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))

OUTPUT_DIR = Path("/tmp/dzine_explore_155")


def gcls(el_expr):
    """JS helper to safely get className as string."""
    return f"(typeof {el_expr}.className === 'string' ? {el_expr}.className : ({el_expr}.className && {el_expr}.className.baseVal || ''))"


def screenshot(page, name: str) -> str:
    path = str(OUTPUT_DIR / f"{name}.png")
    page.screenshot(path=path)
    print(f"  [screenshot] {path}")
    return path


def main():
    from playwright.sync_api import sync_playwright
    from tools.lib.brave_profile import DEFAULT_CDP_PORT, is_browser_running
    from tools.lib.dzine_browser import close_all_dialogs, VIEWPORT

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("PHASE 155b: Instant Storyboard — Deep Dive")
    print("=" * 70)

    if not is_browser_running():
        print("[P155b] ERROR: Brave not running.")
        return

    pw = sync_playwright().start()
    try:
        browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{DEFAULT_CDP_PORT}")
        context = browser.contexts[0]

        dzine_pages = [p for p in context.pages if "dzine.ai/canvas" in (p.url or "")]
        if not dzine_pages:
            print("[P155b] No Dzine canvas found.")
            return

        page = dzine_pages[0]
        page.set_viewport_size(VIEWPORT)
        page.bring_to_front()
        page.wait_for_timeout(1500)
        print(f"[P155b] Canvas: {page.url}")

        close_all_dialogs(page)
        page.wait_for_timeout(500)

        # Close any "New Feature" popup (Skip button)
        for text in ["Skip", "Not now", "Close", "Got it", "Later"]:
            try:
                btn = page.locator(f'button:has-text("{text}"), a:has-text("{text}"), span:has-text("{text}")')
                if btn.count() > 0 and btn.first.is_visible(timeout=500):
                    btn.first.click()
                    page.wait_for_timeout(500)
                    print(f"[P155b] Closed popup via '{text}'")
            except Exception:
                pass

        # Exit any sub-mode (Hand Repair, Image Editor, etc.)
        try:
            exit_btn = page.locator('button:has-text("Exit")')
            if exit_btn.count() > 0 and exit_btn.first.is_visible(timeout=1000):
                exit_btn.first.click()
                page.wait_for_timeout(2000)
                print("[P155b] Exited sub-mode")
                close_all_dialogs(page)
        except Exception:
            pass

        # Close any open panels
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)
        page.evaluate("""() => {
            for (var el of document.querySelectorAll('.c-gen-config.show .ico-close, .panels.show .ico-close')) el.click();
            var lp = document.querySelector('.lip-sync-config-panel.show');
            if (lp) { var c = lp.querySelector('.ico-close'); if (c) c.click(); else lp.classList.remove('show'); }
        }""")
        page.wait_for_timeout(500)

        # Ensure Storyboard panel is open
        page.mouse.click(40, 197)  # Txt2Img first
        page.wait_for_timeout(1000)
        page.mouse.click(40, 766)  # Instant Storyboard
        page.wait_for_timeout(2500)
        close_all_dialogs(page)

        # Verify panel
        panel_cls = page.evaluate("""() => {
            var p = document.querySelector('.c-gen-config.show');
            return p ? p.className : 'NOT FOUND';
        }""")
        print(f"[P155b] Panel: {panel_cls}")

        if 'storyboard' not in panel_cls:
            print("[P155b] WARNING: Storyboard panel not detected, trying again...")
            screenshot(page, "155b_debug")
            # Try double-click
            page.mouse.dblclick(40, 766)
            page.wait_for_timeout(2000)
            panel_cls = page.evaluate("""() => {
                var p = document.querySelector('.c-gen-config.show');
                return p ? p.className : 'NOT FOUND';
            }""")
            if 'storyboard' not in panel_cls:
                print(f"[P155b] ERROR: Still no storyboard panel. Got: {panel_cls}")
                screenshot(page, "155b_error2")
                return

        # ============================================================
        # 1. V1 MODE — Switch and document differences
        # ============================================================
        print(f"\n{'='*60}")
        print("1. V1 MODE — Switching from V2")
        print(f"{'='*60}")

        # Click V1
        page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            for (var btn of panel.querySelectorAll('button.options')) {
                if ((btn.innerText || '').trim() === 'V1') { btn.click(); return true; }
            }
            return false;
        }""")
        page.wait_for_timeout(1500)

        # Dump V1 panel text
        v1_text = page.evaluate("""() => {
            var p = document.querySelector('.c-gen-config.show');
            return p ? p.innerText : '';
        }""")
        print("[1] V1 panel text:")
        for line in v1_text.split('\n'):
            line = line.strip()
            if line:
                print(f"  | {line}")

        # V1 generate button
        v1_gen = page.evaluate("""() => {
            var btn = document.querySelector('#instant-storyboard-generate-btn');
            return btn ? (btn.innerText || '').trim() : 'NOT FOUND';
        }""")
        print(f"[1] V1 Generate button: '{v1_gen}'")

        screenshot(page, "155b_01_v1_mode")

        # Check V1-specific elements (does V1 have different options?)
        v1_elements = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return [];
            var items = [];
            for (var el of panel.querySelectorAll('*')) {
                var r = el.getBoundingClientRect();
                var text = (el.innerText || '').trim();
                if (r.width > 0 && r.height > 0 && text.length > 0 && text.length < 40 &&
                    el.childElementCount === 0 && r.x > 80 && r.x < 350) {
                    var cls = typeof el.className === 'string' ? el.className : '';
                    items.push({
                        text: text,
                        tag: el.tagName.toLowerCase(),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        cls: cls.substring(0, 50)
                    });
                }
            }
            // Deduplicate
            var unique = [], seen = new Set();
            for (var item of items) {
                var key = item.text + '|' + item.y;
                if (!seen.has(key)) { seen.add(key); unique.push(item); }
            }
            return unique.sort((a, b) => a.y - b.y);
        }""")
        print(f"\n[1b] V1 leaf elements: {len(v1_elements)}")
        for e in v1_elements:
            print(f"  ({e['x']},{e['y']}) {e['w']}x{e['h']} <{e['tag']}> '{e['text']}' cls={e['cls'][:40]}")

        # ============================================================
        # 2. SWITCH BACK TO V2 AND COMPARE
        # ============================================================
        print(f"\n{'='*60}")
        print("2. BACK TO V2 — Compare")
        print(f"{'='*60}")

        page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            for (var btn of panel.querySelectorAll('button.options')) {
                if ((btn.innerText || '').trim() === 'V2') { btn.click(); return true; }
            }
            return false;
        }""")
        page.wait_for_timeout(1500)

        v2_text = page.evaluate("""() => {
            var p = document.querySelector('.c-gen-config.show');
            return p ? p.innerText : '';
        }""")
        print("[2] V2 panel text:")
        for line in v2_text.split('\n'):
            line = line.strip()
            if line:
                print(f"  | {line}")

        v2_gen = page.evaluate("""() => {
            var btn = document.querySelector('#instant-storyboard-generate-btn');
            return btn ? (btn.innerText || '').trim() : 'NOT FOUND';
        }""")
        print(f"[2] V2 Generate button: '{v2_gen}'")

        screenshot(page, "155b_02_v2_mode")

        # ============================================================
        # 3. HINT PRESETS — Click each and see what happens
        # ============================================================
        print(f"\n{'='*60}")
        print("3. HINT PRESETS")
        print(f"{'='*60}")

        # Get hint preset elements
        hints = page.evaluate("""() => {
            var items = [];
            for (var el of document.querySelectorAll('.storyboard-preset .preset-image, .storyboard-preset-wrapper .preset-image')) {
                var r = el.getBoundingClientRect();
                if (r.width > 20 && r.height > 20) {
                    var label = el.querySelector('.image-num');
                    items.push({
                        x: Math.round(r.x + r.width/2),
                        y: Math.round(r.y + r.height/2),
                        w: Math.round(r.width), h: Math.round(r.height),
                        label: label ? label.innerText.trim() : '',
                        cls: typeof el.className === 'string' ? el.className.substring(0, 60) : '',
                        hasImg: !!el.querySelector('img'),
                        imgSrc: el.querySelector('img') ? el.querySelector('img').src.substring(0, 80) : ''
                    });
                }
            }
            return items;
        }""")
        print(f"[3] Hint presets: {len(hints)}")
        for h in hints:
            print(f"  center=({h['x']},{h['y']}) {h['w']}x{h['h']} label='{h['label']}' hasImg={h['hasImg']}")
            if h['imgSrc']:
                print(f"    img: {h['imgSrc']}")

        # Click first hint
        if hints:
            print(f"\n[3b] Clicking first hint at ({hints[0]['x']},{hints[0]['y']})...")
            page.mouse.click(hints[0]['x'], hints[0]['y'])
            page.wait_for_timeout(2000)

            # Check if prompt changed
            after_hint = page.evaluate("""() => {
                var p = document.querySelector('.c-gen-config.show');
                return p ? p.innerText : '';
            }""")
            print("[3b] After clicking hint 1:")
            for line in after_hint.split('\n'):
                line = line.strip()
                if line:
                    print(f"  | {line}")

            screenshot(page, "155b_03_hint1_clicked")

            # Check if prompt textarea content changed
            prompt_val = page.evaluate("""() => {
                var ta = document.querySelector('.c-gen-config.show .custom-textarea');
                return ta ? (ta.innerText || ta.textContent || '').trim() : '';
            }""")
            print(f"[3b] Prompt after hint click: '{prompt_val[:200]}'")

            # Check if images were added
            images_in_slot = page.evaluate("""() => {
                var wrapper = document.querySelector('.c-gen-config.show .add-image-wrapper');
                if (!wrapper) return [];
                var imgs = [];
                for (var img of wrapper.querySelectorAll('img')) {
                    var r = img.getBoundingClientRect();
                    if (r.width > 10) {
                        imgs.push({
                            src: img.src.substring(0, 120),
                            x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height)
                        });
                    }
                }
                return imgs;
            }""")
            print(f"[3b] Images in slot: {len(images_in_slot)}")
            for img in images_in_slot:
                print(f"  ({img['x']},{img['y']}) {img['w']}x{img['h']} src={img['src']}")

        # Click "See more hints" if available
        more_hints = page.evaluate("""() => {
            for (var el of document.querySelectorAll('.c-gen-config.show *')) {
                var text = (el.innerText || '').trim();
                if (text.includes('See more') || text.includes('more hints') || text.includes('refresh')) {
                    var r = el.getBoundingClientRect();
                    if (r.width > 0) {
                        return {x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2), text: text.substring(0, 40)};
                    }
                }
            }
            // Check for refresh icon
            var refresh = document.querySelector('.c-gen-config.show .storyboard-preset-wrapper .ico-refresh, .c-gen-config.show .storyboard-preset-wrapper svg');
            if (refresh) {
                var r = refresh.getBoundingClientRect();
                if (r.width > 0) return {x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2), text: 'refresh icon'};
            }
            return null;
        }""")
        if more_hints:
            print(f"\n[3c] 'See more/refresh' at ({more_hints['x']},{more_hints['y']}): '{more_hints['text']}'")

        # ============================================================
        # 4. ASPECT RATIO "MORE" DROPDOWN
        # ============================================================
        print(f"\n{'='*60}")
        print("4. ASPECT RATIO DROPDOWN")
        print(f"{'='*60}")

        # The "more" arrow/dropdown for aspect ratio
        ar_section = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return null;
            // Find the Aspect Ratio section
            for (var el of panel.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                if (text === 'Aspect Ratio' && el.childElementCount === 0) {
                    var parent = el.parentElement;
                    var r = parent.getBoundingClientRect();
                    return {
                        text: parent.innerText.trim().substring(0, 200),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        cls: typeof parent.className === 'string' ? parent.className.substring(0, 60) : ''
                    };
                }
            }
            return null;
        }""")
        if ar_section:
            print(f"[4] AR section: '{ar_section['text']}' at ({ar_section['x']},{ar_section['y']}) cls={ar_section['cls']}")

        # Get all AR-related elements
        ar_items = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return [];
            var items = [];
            var inAR = false;
            for (var el of panel.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                if (text === 'Aspect Ratio') inAR = true;
                if (text === 'Generate') inAR = false;
                if (!inAR) continue;

                var r = el.getBoundingClientRect();
                if (r.width > 0 && text.length > 0 && text.length < 30 && el.childElementCount === 0) {
                    var cls = typeof el.className === 'string' ? el.className : '';
                    items.push({
                        text: text,
                        tag: el.tagName.toLowerCase(),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        cls: cls.substring(0, 60),
                        clickable: el.tagName === 'BUTTON' || el.tagName === 'DIV' || el.getAttribute('role') === 'button'
                    });
                }
            }
            return items;
        }""")
        print(f"[4] AR items: {len(ar_items)}")
        for a in ar_items:
            click = " [CLICKABLE]" if a['clickable'] else ""
            print(f"  ({a['x']},{a['y']}) {a['w']}x{a['h']} <{a['tag']}> '{a['text']}' cls={a['cls'][:40]}{click}")

        # Look for the dropdown arrow near "more"
        dropdown_arrow = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return null;
            // The "more" arrow is often a small clickable element near the aspect ratios
            for (var el of panel.querySelectorAll('.config-param [class*="more"], .config-param [class*="arrow"], .config-param [class*="expand"], .config-param select, .c-aspect-ratio .more, .c-aspect-ratio [class*="drop"]')) {
                var r = el.getBoundingClientRect();
                if (r.width > 0) {
                    return {
                        tag: el.tagName.toLowerCase(),
                        x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2),
                        w: Math.round(r.width), h: Math.round(r.height),
                        cls: typeof el.className === 'string' ? el.className.substring(0, 60) : '',
                        text: (el.innerText || '').trim().substring(0, 30)
                    };
                }
            }
            return null;
        }""")
        if dropdown_arrow:
            print(f"[4b] Dropdown arrow: ({dropdown_arrow['x']},{dropdown_arrow['y']}) '{dropdown_arrow['text']}' cls={dropdown_arrow['cls']}")

        # Try clicking the "v" dropdown near 16:9 (at approximately x=297, y=464 based on screenshot)
        print("[4c] Clicking the dropdown arrow to the right of 16:9...")
        page.mouse.click(297, 464)
        page.wait_for_timeout(1500)

        screenshot(page, "155b_04_ar_dropdown")

        # Check if a dropdown appeared
        ar_dropdown = page.evaluate("""() => {
            var results = [];
            // Look for newly visible dropdowns/popups
            for (var el of document.querySelectorAll('[class*="dropdown"], [class*="popup"], [class*="select"], [class*="option"]')) {
                var r = el.getBoundingClientRect();
                var s = window.getComputedStyle(el);
                if (r.width > 50 && r.height > 30 && s.display !== 'none' && r.y > 400 && r.y < 600) {
                    results.push({
                        text: (el.innerText || '').trim().substring(0, 300),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        cls: typeof el.className === 'string' ? el.className.substring(0, 80) : ''
                    });
                }
            }
            // Also check for any ratio-related text that just appeared
            for (var el of document.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                if ((text.includes('3:2') || text.includes('4:3') || text.includes('2:3') ||
                     text.includes('YouTube') || text.includes('Desktop') || text.includes('custom')) &&
                    el.childElementCount === 0) {
                    var r = el.getBoundingClientRect();
                    var s = window.getComputedStyle(el);
                    if (r.width > 0 && s.display !== 'none') {
                        results.push({
                            text: text.substring(0, 60),
                            x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height),
                            cls: typeof el.className === 'string' ? el.className.substring(0, 80) : ''
                        });
                    }
                }
            }
            return results;
        }""")
        print(f"[4c] Dropdown elements: {len(ar_dropdown)}")
        for d in ar_dropdown:
            name = d['text'].replace('\n', ' | ')[:80]
            print(f"  ({d['x']},{d['y']}) {d['w']}x{d['h']} '{name}' cls={d['cls'][:50]}")

        page.keyboard.press("Escape")
        page.wait_for_timeout(300)

        # ============================================================
        # 5. IMAGE UPLOAD SLOT — Click the upload button
        # ============================================================
        print(f"\n{'='*60}")
        print("5. IMAGE UPLOAD SLOT")
        print(f"{'='*60}")

        # The upload button is at cls=upload-image-btn image-item, around (105,162)
        upload_btn_info = page.evaluate("""() => {
            var btn = document.querySelector('.c-gen-config.show .upload-image-btn');
            if (!btn) return null;
            var r = btn.getBoundingClientRect();
            return {
                x: Math.round(r.x + r.width/2),
                y: Math.round(r.y + r.height/2),
                w: Math.round(r.width), h: Math.round(r.height),
                cls: typeof btn.className === 'string' ? btn.className.substring(0, 80) : '',
                tag: btn.tagName.toLowerCase()
            };
        }""")
        if upload_btn_info:
            print(f"[5] Upload button: center=({upload_btn_info['x']},{upload_btn_info['y']}) {upload_btn_info['w']}x{upload_btn_info['h']}")
            print(f"    cls={upload_btn_info['cls']}")

            # Check if there's an <input type="file"> nearby
            file_input = page.evaluate("""() => {
                var inputs = document.querySelectorAll('input[type="file"]');
                var results = [];
                for (var inp of inputs) {
                    results.push({
                        id: inp.id || '',
                        name: inp.name || '',
                        accept: inp.accept || '',
                        multiple: inp.multiple,
                        cls: typeof inp.className === 'string' ? inp.className.substring(0, 60) : '',
                        display: window.getComputedStyle(inp).display,
                        parent: inp.parentElement ? inp.parentElement.className.substring(0, 40) : ''
                    });
                }
                return results;
            }""")
            print(f"[5b] File inputs on page: {len(file_input)}")
            for fi in file_input:
                print(f"  id='{fi['id']}' name='{fi['name']}' accept='{fi['accept']}' multiple={fi['multiple']} display={fi['display']}")
                print(f"    parent cls={fi['parent']}")

        # ============================================================
        # 6. @MENTION — Deeper analysis of the mention system
        # ============================================================
        print(f"\n{'='*60}")
        print("6. @MENTION DEEP ANALYSIS")
        print(f"{'='*60}")

        # Clear any existing text
        page.evaluate("""() => {
            var ta = document.querySelector('.c-gen-config.show .custom-textarea');
            if (ta) { ta.innerText = ''; ta.dispatchEvent(new Event('input', {bubbles: true})); }
        }""")
        page.wait_for_timeout(300)

        # Focus the prompt and type @
        page.mouse.click(200, 270)
        page.wait_for_timeout(500)
        page.keyboard.type("@", delay=200)
        page.wait_for_timeout(2000)

        screenshot(page, "155b_06a_at_typed")

        # Check for ANY new floating/positioned elements that appeared
        at_popup = page.evaluate("""() => {
            var results = [];
            for (var el of document.querySelectorAll('*')) {
                var s = window.getComputedStyle(el);
                var r = el.getBoundingClientRect();
                // Look for fixed/absolute positioned elements that are visible and near the prompt area
                if ((s.position === 'fixed' || s.position === 'absolute') &&
                    r.width > 50 && r.height > 20 && r.x > 60 && r.x < 500 &&
                    r.y > 200 && r.y < 600 &&
                    s.display !== 'none' && s.visibility !== 'hidden' &&
                    parseInt(s.zIndex || '0') >= 10) {
                    var text = (el.innerText || '').trim();
                    if (text.length > 0 && text.length < 500) {
                        results.push({
                            text: text.substring(0, 200),
                            x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height),
                            cls: typeof el.className === 'string' ? el.className.substring(0, 80) : '',
                            tag: el.tagName.toLowerCase(),
                            zIndex: s.zIndex,
                            position: s.position
                        });
                    }
                }
            }
            return results;
        }""")
        print(f"[6a] Floating elements after '@': {len(at_popup)}")
        for p in at_popup:
            name = p['text'].replace('\n', ' | ')[:80]
            print(f"  ({p['x']},{p['y']}) {p['w']}x{p['h']} z={p['zIndex']} <{p['tag']}> '{name}'")
            print(f"    cls={p['cls'][:60]}")

        # Also try searching for mention-related classes
        mention_classes = page.evaluate("""() => {
            var results = [];
            var all = document.querySelectorAll('*');
            for (var el of all) {
                var cls = typeof el.className === 'string' ? el.className : '';
                if (cls.includes('mention') || cls.includes('tag') || cls.includes('autocomplete') ||
                    cls.includes('suggest') || cls.includes('hint-popup')) {
                    var r = el.getBoundingClientRect();
                    var s = window.getComputedStyle(el);
                    results.push({
                        cls: cls.substring(0, 100),
                        tag: el.tagName.toLowerCase(),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        display: s.display,
                        visible: r.width > 0 && r.height > 0 && s.display !== 'none',
                        text: (el.innerText || '').trim().substring(0, 100)
                    });
                }
            }
            return results;
        }""")
        print(f"\n[6b] Mention/tag/autocomplete elements: {len(mention_classes)}")
        for m in mention_classes:
            vis = " [VISIBLE]" if m['visible'] else " [hidden]"
            print(f"  <{m['tag']}> cls={m['cls'][:60]} ({m['x']},{m['y']}) {m['w']}x{m['h']}{vis}")
            if m['text']:
                print(f"    text: '{m['text'][:60]}'")

        # Clear and check the prompt's HTML structure
        page.keyboard.press("Meta+a")
        page.keyboard.press("Backspace")
        page.wait_for_timeout(300)

        # Check the prompt's innerHTML to understand tag structure
        prompt_html = page.evaluate("""() => {
            var ta = document.querySelector('.c-gen-config.show .custom-textarea');
            return ta ? ta.innerHTML : '';
        }""")
        print(f"\n[6c] Prompt innerHTML (empty): '{prompt_html[:300]}'")

        # Type a sample prompt with @ to see how it renders in HTML
        page.mouse.click(200, 270)
        page.wait_for_timeout(300)
        page.keyboard.type("A product on a desk with ", delay=30)
        page.wait_for_timeout(300)

        prompt_html2 = page.evaluate("""() => {
            var ta = document.querySelector('.c-gen-config.show .custom-textarea');
            return ta ? ta.innerHTML : '';
        }""")
        print(f"[6d] Prompt HTML after text: '{prompt_html2[:300]}'")

        page.keyboard.type("@", delay=200)
        page.wait_for_timeout(2000)

        prompt_html3 = page.evaluate("""() => {
            var ta = document.querySelector('.c-gen-config.show .custom-textarea');
            return ta ? ta.innerHTML : '';
        }""")
        print(f"[6e] Prompt HTML after '@': '{prompt_html3[:300]}'")

        screenshot(page, "155b_06e_at_in_context")

        # Check for NEWLY visible elements
        new_popup = page.evaluate("""() => {
            var results = [];
            for (var el of document.querySelectorAll('[class*="pop"], [class*="menu"], [class*="float"], [class*="overlay"]')) {
                var r = el.getBoundingClientRect();
                var s = window.getComputedStyle(el);
                if (r.width > 30 && r.height > 20 && s.display !== 'none' && r.x > 80 && r.x < 400) {
                    var text = (el.innerText || '').trim();
                    if (text.length > 0 && text.length < 500) {
                        results.push({
                            text: text.substring(0, 200),
                            x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height),
                            cls: typeof el.className === 'string' ? el.className.substring(0, 80) : '',
                            zIndex: s.zIndex
                        });
                    }
                }
            }
            return results;
        }""")
        print(f"\n[6f] Pop/menu/float/overlay elements: {len(new_popup)}")
        for p in new_popup:
            name = p['text'].replace('\n', ' | ')[:80]
            print(f"  ({p['x']},{p['y']}) {p['w']}x{p['h']} z={p['zIndex']} '{name}' cls={p['cls'][:50]}")

        # Clear prompt
        page.keyboard.press("Meta+a")
        page.keyboard.press("Backspace")
        page.wait_for_timeout(300)

        # ============================================================
        # 7. STORYBOARD-SPECIFIC CLASSES AND IDS
        # ============================================================
        print(f"\n{'='*60}")
        print("7. ALL STORYBOARD-SPECIFIC SELECTORS")
        print(f"{'='*60}")

        selectors = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return {};

            return {
                panelCls: panel.className,
                bodyId: panel.querySelector('.gen-config-body') ? panel.querySelector('.gen-config-body').id : '',
                formId: panel.querySelector('.gen-config-form') ? panel.querySelector('.gen-config-form').id : '',
                generateBtnId: panel.querySelector('.generative') ? panel.querySelector('.generative').id : '',
                promptId: panel.querySelector('.base-prompt') ? panel.querySelector('.base-prompt').id : '',
                promptTextarea: panel.querySelector('.custom-textarea') ? {
                    cls: panel.querySelector('.custom-textarea').className,
                    placeholder: panel.querySelector('.custom-textarea').getAttribute('data-placeholder') || panel.querySelector('.custom-textarea').getAttribute('placeholder') || ''
                } : null,
                uploadBtn: panel.querySelector('.upload-image-btn') ? {
                    cls: panel.querySelector('.upload-image-btn').className,
                    tag: panel.querySelector('.upload-image-btn').tagName
                } : null,
                addImageWrapper: panel.querySelector('.add-image-wrapper') ? {
                    cls: panel.querySelector('.add-image-wrapper').className
                } : null,
                storyboardPreset: panel.querySelector('.storyboard-preset') ? {
                    cls: panel.querySelector('.storyboard-preset').className,
                    children: panel.querySelector('.storyboard-preset').childElementCount
                } : null,
                configParams: panel.querySelectorAll('.config-param').length,
                slidingSwitch: panel.querySelector('.sliding-switch') ? true : false,
                versionBtns: Array.from(panel.querySelectorAll('.c-options button.options')).map(b => ({
                    text: b.innerText.trim(),
                    selected: b.className.includes('selected')
                })),
                charCounter: panel.querySelector('.char-count, .len-count') ?
                    panel.querySelector('.char-count, .len-count').innerText : 'N/A'
            };
        }""")
        print("[7] Selectors map:")
        print(json.dumps(selectors, indent=2))

        # ============================================================
        # 8. CHECK IMAGE ADD BEHAVIOR (upload-image-btn)
        # ============================================================
        print(f"\n{'='*60}")
        print("8. IMAGE ADD — Upload mechanism")
        print(f"{'='*60}")

        # Check what happens when we click the upload button
        # First, let's look at the button more closely
        upload_detail = page.evaluate("""() => {
            var btn = document.querySelector('.c-gen-config.show .upload-image-btn');
            if (!btn) return null;
            return {
                tag: btn.tagName,
                cls: btn.className,
                innerHTML: btn.innerHTML.substring(0, 500),
                onclick: btn.getAttribute('onclick') || '',
                hasFileInput: !!btn.querySelector('input[type="file"]'),
                parentCls: btn.parentElement ? btn.parentElement.className.substring(0, 60) : '',
                siblings: Array.from(btn.parentElement ? btn.parentElement.children : []).map(c => ({
                    tag: c.tagName, cls: (typeof c.className === 'string' ? c.className : '').substring(0, 40)
                }))
            };
        }""")
        if upload_detail:
            print(f"[8] Upload button details:")
            print(f"  tag={upload_detail['tag']}")
            print(f"  cls={upload_detail['cls']}")
            print(f"  hasFileInput={upload_detail['hasFileInput']}")
            print(f"  parentCls={upload_detail['parentCls']}")
            print(f"  innerHTML: {upload_detail['innerHTML'][:200]}")
            print(f"  siblings: {upload_detail['siblings']}")

        # ============================================================
        # 9. LABEL (image naming) AREA
        # ============================================================
        print(f"\n{'='*60}")
        print("9. IMAGE LABEL / NAME AREA")
        print(f"{'='*60}")

        # The wrapper has class "can-add-name" which suggests you can name images
        name_area = page.evaluate("""() => {
            var wrapper = document.querySelector('.c-gen-config.show .add-image-wrapper');
            if (!wrapper) return null;
            return {
                cls: wrapper.className,
                hasTag: wrapper.className.includes('has-tag'),
                canAddName: wrapper.className.includes('can-add-name'),
                children: Array.from(wrapper.children).map(c => ({
                    tag: c.tagName.toLowerCase(),
                    cls: (typeof c.className === 'string' ? c.className : '').substring(0, 60),
                    text: (c.innerText || '').trim().substring(0, 40),
                    x: Math.round(c.getBoundingClientRect().x),
                    y: Math.round(c.getBoundingClientRect().y),
                    w: Math.round(c.getBoundingClientRect().width),
                    h: Math.round(c.getBoundingClientRect().height)
                }))
            };
        }""")
        if name_area:
            print(f"[9] Image wrapper:")
            print(f"  cls: {name_area['cls']}")
            print(f"  hasTag: {name_area['hasTag']}, canAddName: {name_area['canAddName']}")
            print(f"  children: {len(name_area['children'])}")
            for c in name_area['children']:
                print(f"    <{c['tag']}> cls={c['cls']} ({c['x']},{c['y']}) {c['w']}x{c['h']} '{c['text']}'")

        # ============================================================
        # 10. RESOLUTION INFO
        # ============================================================
        print(f"\n{'='*60}")
        print("10. RESOLUTION / OUTPUT INFO")
        print(f"{'='*60}")

        res_info = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return null;
            var results = [];
            for (var el of panel.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                if (/\d+\s*[x×]\s*\d+/.test(text) && el.childElementCount === 0) {
                    var r = el.getBoundingClientRect();
                    results.push({
                        text: text,
                        x: Math.round(r.x), y: Math.round(r.y),
                        cls: typeof el.className === 'string' ? el.className.substring(0, 40) : ''
                    });
                }
            }
            return results;
        }""")
        print(f"[10] Resolution elements: {len(res_info) if res_info else 0}")
        if res_info:
            for r in res_info:
                print(f"  ({r['x']},{r['y']}) '{r['text']}' cls={r['cls']}")

        screenshot(page, "155b_10_final")

        # ============================================================
        # SUMMARY
        # ============================================================
        print("\n" + "=" * 70)
        print("PHASE 155b COMPLETE")
        print("=" * 70)
        v1_gen_text = v1_gen if 'v1_gen' in dir() else 'N/A'
        v2_gen_text = v2_gen if 'v2_gen' in dir() else 'N/A'
        print(f"  V1 credits: {v1_gen_text}")
        print(f"  V2 credits: {v2_gen_text}")
        print(f"  Hint presets: {len(hints)}")
        print(f"  File inputs: {len(file_input) if file_input else 0}")
        print(f"  Screenshots: {OUTPUT_DIR}")

    finally:
        try:
            pw.stop()
        except Exception:
            pass


if __name__ == "__main__":
    main()
