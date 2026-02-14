#!/usr/bin/env python3
"""Phase 155: Instant Storyboard — Full UI exploration and documentation.

Explores Dzine's Instant Storyboard tool:
- Panel layout, image upload slots, prompt area
- @mention system (@Image1, @Image2, @Image3)
- Aspect ratio options, style/version selectors
- Generation credits and settings
- Automation selectors for future pipeline use

Screenshots saved to /tmp/dzine_explore_155/
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


def screenshot(page, name: str) -> str:
    """Take a screenshot and return the path."""
    path = str(OUTPUT_DIR / f"{name}.png")
    page.screenshot(path=path)
    print(f"  [screenshot] {path}")
    return path


def close_panels(page):
    """Close any open generation panels."""
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)
    page.evaluate("""() => {
        for (var el of document.querySelectorAll('.c-gen-config.show .ico-close, .panels.show .ico-close')) el.click();
        var lp = document.querySelector('.lip-sync-config-panel.show');
        if (lp) { var c = lp.querySelector('.ico-close'); if (c) c.click(); else lp.classList.remove('show'); }
    }""")
    page.wait_for_timeout(500)


def main():
    from playwright.sync_api import sync_playwright
    from tools.lib.brave_profile import DEFAULT_CDP_PORT, is_browser_running
    from tools.lib.dzine_browser import close_all_dialogs, VIEWPORT

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("PHASE 155: Instant Storyboard — Full Exploration")
    print("=" * 70)

    if not is_browser_running():
        print("[P155] ERROR: Brave not running on CDP port.")
        return

    pw = sync_playwright().start()
    try:
        browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{DEFAULT_CDP_PORT}")
        context = browser.contexts[0]

        # Find or navigate to Dzine canvas
        dzine_pages = [p for p in context.pages if "dzine.ai/canvas" in (p.url or "")]
        if dzine_pages:
            page = dzine_pages[0]
        else:
            print("[P155] No Dzine canvas tab found — opening one...")
            page = context.new_page()
            page.goto("https://www.dzine.ai/canvas?id=19797967", wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(5000)

        page.set_viewport_size(VIEWPORT)
        page.bring_to_front()
        page.wait_for_timeout(2000)
        print(f"[P155] Canvas URL: {page.url}")

        # Close popups
        closed = close_all_dialogs(page)
        print(f"[P155] Closed {closed} dialogs")
        page.wait_for_timeout(500)

        # Close any open panels first
        close_panels(page)

        # ============================================================
        # 1. VERIFY SIDEBAR — Check Instant Storyboard position
        # ============================================================
        print(f"\n{'='*60}")
        print("1. SIDEBAR TOOL VERIFICATION")
        print(f"{'='*60}")

        sidebar_tools = page.evaluate("""() => {
            var items = [];
            for (var el of document.querySelectorAll('.tool-group, .tool-item, [class*="tool-group"]')) {
                var r = el.getBoundingClientRect();
                var text = (el.innerText || '').trim();
                if (r.width > 0 && r.x < 80 && text.length > 0) {
                    items.push({
                        text: text.replace(/\\n/g, ' ').substring(0, 40),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        cls: (typeof el.className === 'string' ? el.className : (el.className && el.className.baseVal || '')).substring(0, 60),
                        centerX: Math.round(r.x + r.width / 2),
                        centerY: Math.round(r.y + r.height / 2)
                    });
                }
            }
            return items;
        }""")
        print(f"[1] Found {len(sidebar_tools)} sidebar items:")
        storyboard_tool = None
        for t in sidebar_tools:
            marker = ""
            if "storyboard" in t['text'].lower() or "instant" in t['text'].lower():
                marker = " <<<< TARGET"
                storyboard_tool = t
            print(f"  ({t['centerX']},{t['centerY']}) '{t['text']}' cls={t['cls'][:40]}{marker}")

        screenshot(page, "01_sidebar_overview")

        # ============================================================
        # 2. CLICK INSTANT STORYBOARD
        # ============================================================
        print(f"\n{'='*60}")
        print("2. OPENING INSTANT STORYBOARD")
        print(f"{'='*60}")

        # According to playbook: Instant Storyboard at (40, 766)
        # But first switch to another tool, then click Storyboard
        page.mouse.click(40, 197)  # Txt2Img first
        page.wait_for_timeout(1000)

        click_y = storyboard_tool['centerY'] if storyboard_tool else 766
        click_x = storyboard_tool['centerX'] if storyboard_tool else 40
        print(f"[2] Clicking Instant Storyboard at ({click_x}, {click_y})")
        page.mouse.click(click_x, click_y)
        page.wait_for_timeout(2500)

        # Close any new popups
        close_all_dialogs(page)
        page.wait_for_timeout(500)

        screenshot(page, "02_storyboard_panel_initial")

        # ============================================================
        # 3. DETECT PANEL TYPE — Is it a direct panel or a menu card?
        # ============================================================
        print(f"\n{'='*60}")
        print("3. PANEL DETECTION")
        print(f"{'='*60}")

        panel_info = page.evaluate("""() => {
            // Check for c-gen-config panel (standard generation panel)
            var genPanel = document.querySelector('.c-gen-config.show');
            if (genPanel) {
                var r = genPanel.getBoundingClientRect();
                return {
                    type: 'gen-config',
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    text: genPanel.innerText.substring(0, 2000),
                    cls: (genPanel.className || '').substring(0, 100)
                };
            }
            // Check for any panel/overlay in the sidebar area (x < 500)
            for (var el of document.querySelectorAll('*')) {
                var r = el.getBoundingClientRect();
                var text = (el.innerText || '').trim();
                if (r.width > 200 && r.height > 200 && r.x > 60 && r.x < 500 &&
                    text.length > 50 && (text.toLowerCase().includes('storyboard') || text.toLowerCase().includes('instant'))) {
                    return {
                        type: 'custom-panel',
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        text: text.substring(0, 2000),
                        cls: (typeof el.className === 'string' ? el.className : (el.className && el.className.baseVal || '')).substring(0, 100)
                    };
                }
            }
            // Fallback: any visible panel area right of sidebar
            for (var el of document.querySelectorAll('[class*="panel"], [class*="config"], [class*="sidebar"]')) {
                var r = el.getBoundingClientRect();
                var s = window.getComputedStyle(el);
                if (r.width > 200 && r.height > 200 && r.x > 60 && r.x < 500 && s.display !== 'none') {
                    var text = (el.innerText || '').trim();
                    if (text.length > 30) {
                        return {
                            type: 'fallback-panel',
                            x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height),
                            text: text.substring(0, 2000),
                            cls: (typeof el.className === 'string' ? el.className : (el.className && el.className.baseVal || '')).substring(0, 100)
                        };
                    }
                }
            }
            return null;
        }""")

        if panel_info:
            print(f"[3] Panel type: {panel_info['type']}")
            print(f"[3] Position: ({panel_info['x']},{panel_info['y']}) {panel_info['w']}x{panel_info['h']}")
            print(f"[3] Class: {panel_info['cls']}")
            print(f"[3] Content preview:\n{panel_info['text'][:600]}")
        else:
            print("[3] No panel detected — trying double-click...")
            page.mouse.dblclick(click_x, click_y)
            page.wait_for_timeout(2000)
            close_all_dialogs(page)
            screenshot(page, "02b_storyboard_dblclick")

            # Re-check
            panel_info = page.evaluate("""() => {
                for (var el of document.querySelectorAll('*')) {
                    var r = el.getBoundingClientRect();
                    var text = (el.innerText || '').trim();
                    if (r.width > 200 && r.height > 200 && r.x > 60 && r.x < 500 && text.length > 50) {
                        var s = window.getComputedStyle(el);
                        if (s.display !== 'none' && s.visibility !== 'hidden' && s.opacity !== '0') {
                            return {
                                type: 'after-dblclick',
                                x: Math.round(r.x), y: Math.round(r.y),
                                w: Math.round(r.width), h: Math.round(r.height),
                                text: text.substring(0, 2000),
                                cls: (typeof el.className === 'string' ? el.className : (el.className && el.className.baseVal || '')).substring(0, 100)
                            };
                        }
                    }
                }
                return null;
            }""")
            if panel_info:
                print(f"[3b] Panel found after dblclick: {panel_info['type']}")
                print(f"[3b] Content:\n{panel_info['text'][:600]}")

        # ============================================================
        # 4. FULL PANEL UI ELEMENTS
        # ============================================================
        print(f"\n{'='*60}")
        print("4. PANEL UI ELEMENTS (Detailed)")
        print(f"{'='*60}")

        # Get all interactive elements in the panel area
        ui_elements = page.evaluate("""() => {
            var results = [];
            var panel = document.querySelector('.c-gen-config.show') ||
                        document.querySelector('[class*="storyboard"]') ||
                        document.querySelector('[class*="instant"]');

            // Broad search in right-of-sidebar area
            var searchRoot = panel || document;
            var minX = panel ? 0 : 65;

            for (var el of searchRoot.querySelectorAll('*')) {
                var r = el.getBoundingClientRect();
                if (r.width <= 0 || r.height <= 0) continue;
                if (!panel && (r.x < minX || r.x > 500)) continue;

                var text = (el.innerText || '').trim();
                var tag = el.tagName.toLowerCase();
                var cls = typeof el.className === 'string' ? el.className : (el.className.baseVal || '');

                // Interactive elements
                if (tag === 'button' || tag === 'textarea' || tag === 'input' ||
                    tag === 'select' || el.getAttribute('contenteditable') ||
                    el.getAttribute('role') === 'button' || cls.includes('btn') ||
                    cls.includes('upload') || cls.includes('slot') || cls.includes('image') ||
                    cls.includes('mention') || cls.includes('prompt')) {

                    results.push({
                        tag: tag,
                        text: text.substring(0, 100),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        cls: cls.substring(0, 80),
                        id: (el.id || '').substring(0, 40),
                        type: el.type || '',
                        placeholder: (el.placeholder || el.getAttribute('data-placeholder') || '').substring(0, 80),
                        contentEditable: el.getAttribute('contenteditable') || '',
                        role: el.getAttribute('role') || '',
                        disabled: el.disabled || false
                    });
                }
            }
            // Deduplicate by position
            var unique = [];
            var seen = new Set();
            for (var item of results) {
                var key = item.x + ',' + item.y + ',' + item.w;
                if (!seen.has(key)) { seen.add(key); unique.push(item); }
            }
            return unique.sort((a, b) => a.y - b.y || a.x - b.x);
        }""")

        print(f"[4] Found {len(ui_elements)} interactive elements:")
        for e in ui_elements:
            extra = ""
            if e['placeholder']:
                extra += f" placeholder='{e['placeholder']}'"
            if e['contentEditable']:
                extra += f" contentEditable={e['contentEditable']}"
            if e['id']:
                extra += f" id='{e['id']}'"
            if e['disabled']:
                extra += " DISABLED"
            name = e['text'].replace('\n', ' | ')[:60]
            print(f"  ({e['x']},{e['y']}) {e['w']}x{e['h']} <{e['tag']}> '{name}' cls={e['cls'][:50]}{extra}")

        # ============================================================
        # 5. IMAGE UPLOAD SLOTS
        # ============================================================
        print(f"\n{'='*60}")
        print("5. IMAGE UPLOAD SLOTS")
        print(f"{'='*60}")

        upload_slots = page.evaluate("""() => {
            var slots = [];
            // Look for upload/image slots, drop zones, plus buttons
            for (var el of document.querySelectorAll('[class*="upload"], [class*="slot"], [class*="drop"], [class*="add-image"], [class*="img-slot"], [class*="pic"], .c-gen-config.show .image-wrap, .c-gen-config.show .add-btn')) {
                var r = el.getBoundingClientRect();
                if (r.width > 20 && r.height > 20 && r.x > 60 && r.x < 500) {
                    var text = (el.innerText || '').trim();
                    slots.push({
                        text: text.substring(0, 80),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        cls: (typeof el.className === 'string' ? el.className : (el.className && el.className.baseVal || '')).substring(0, 80),
                        tag: el.tagName.toLowerCase(),
                        children: el.childElementCount,
                        hasImg: !!el.querySelector('img'),
                        imgSrc: el.querySelector('img') ? el.querySelector('img').src.substring(0, 100) : ''
                    });
                }
            }
            // Also look for any + icons or "add" buttons near image areas
            for (var el of document.querySelectorAll('.c-gen-config.show svg, .c-gen-config.show [class*="plus"], .c-gen-config.show [class*="add"]')) {
                var r = el.getBoundingClientRect();
                if (r.width > 10 && r.width < 100 && r.x > 60 && r.x < 500 && r.y > 50 && r.y < 400) {
                    slots.push({
                        text: (el.innerText || el.textContent || '').trim().substring(0, 40),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        cls: (typeof el.className === 'string' ? el.className : (el.className && el.className.baseVal || '')).substring(0, 80),
                        tag: el.tagName.toLowerCase()
                    });
                }
            }
            return slots;
        }""")

        print(f"[5] Upload slots found: {len(upload_slots)}")
        for s in upload_slots:
            extra = ""
            if s.get('hasImg'):
                extra += f" [HAS IMAGE: {s.get('imgSrc', '')}]"
            print(f"  ({s['x']},{s['y']}) {s['w']}x{s['h']} <{s['tag']}> '{s['text']}' cls={s['cls'][:50]}{extra}")

        screenshot(page, "03_upload_slots")

        # ============================================================
        # 6. PROMPT AREA & @MENTION SYSTEM
        # ============================================================
        print(f"\n{'='*60}")
        print("6. PROMPT AREA & @MENTION SYSTEM")
        print(f"{'='*60}")

        prompt_area = page.evaluate("""() => {
            var results = [];
            // Look for textarea, contenteditable, or any text input in the panel
            for (var el of document.querySelectorAll('.c-gen-config.show textarea, .c-gen-config.show [contenteditable], .c-gen-config.show input[type="text"]')) {
                var r = el.getBoundingClientRect();
                if (r.width > 100) {
                    results.push({
                        tag: el.tagName.toLowerCase(),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        cls: (typeof el.className === 'string' ? el.className : (el.className && el.className.baseVal || '')).substring(0, 80),
                        id: (el.id || '').substring(0, 40),
                        placeholder: (el.placeholder || el.getAttribute('data-placeholder') || '').substring(0, 100),
                        contentEditable: el.getAttribute('contenteditable') || '',
                        value: (el.value || el.innerText || '').substring(0, 200),
                        maxLength: el.maxLength || -1,
                        rows: el.rows || -1
                    });
                }
            }
            return results;
        }""")

        print(f"[6] Prompt areas found: {len(prompt_area)}")
        for p in prompt_area:
            print(f"  ({p['x']},{p['y']}) {p['w']}x{p['h']} <{p['tag']}> id='{p['id']}' cls={p['cls'][:50]}")
            print(f"    placeholder: '{p['placeholder']}'")
            print(f"    contentEditable: {p['contentEditable']}, maxLength: {p['maxLength']}")
            if p['value']:
                print(f"    current value: '{p['value']}'")

        # Try typing @ to see mention suggestions
        if prompt_area:
            pa = prompt_area[0]
            print(f"\n[6b] Testing @mention system — clicking prompt at ({pa['x']+10},{pa['y']+10})...")
            page.mouse.click(pa['x'] + 10, pa['y'] + 10)
            page.wait_for_timeout(500)
            page.keyboard.type("@", delay=100)
            page.wait_for_timeout(1500)

            screenshot(page, "04_at_mention_popup")

            # Check for mention dropdown/popup
            mention_popup = page.evaluate("""() => {
                var results = [];
                // Look for dropdowns, lists, suggestion popups
                for (var el of document.querySelectorAll('[class*="mention"], [class*="dropdown"], [class*="suggest"], [class*="popup"], [class*="list"], [class*="autocomplete"]')) {
                    var r = el.getBoundingClientRect();
                    var s = window.getComputedStyle(el);
                    if (r.width > 50 && r.height > 20 && s.display !== 'none' && s.visibility !== 'hidden') {
                        var text = (el.innerText || '').trim();
                        if (text.length > 0) {
                            results.push({
                                text: text.substring(0, 300),
                                x: Math.round(r.x), y: Math.round(r.y),
                                w: Math.round(r.width), h: Math.round(r.height),
                                cls: (typeof el.className === 'string' ? el.className : (el.className && el.className.baseVal || '')).substring(0, 80),
                                tag: el.tagName.toLowerCase()
                            });
                        }
                    }
                }
                // Also check for any new elements that appeared with "Image" text
                for (var el of document.querySelectorAll('*')) {
                    var r = el.getBoundingClientRect();
                    var text = (el.innerText || '').trim();
                    if (text.includes('Image1') || text.includes('Image2') || text.includes('Image3') ||
                        text.includes('@Image') || text.includes('image 1') || text.includes('image 2')) {
                        var s = window.getComputedStyle(el);
                        if (r.width > 30 && r.height > 15 && s.display !== 'none' &&
                            parseInt(s.zIndex || '0') > 10) {
                            results.push({
                                text: text.substring(0, 200),
                                x: Math.round(r.x), y: Math.round(r.y),
                                w: Math.round(r.width), h: Math.round(r.height),
                                cls: (typeof el.className === 'string' ? el.className : (el.className && el.className.baseVal || '')).substring(0, 80),
                                tag: el.tagName.toLowerCase(),
                                zIndex: s.zIndex
                            });
                        }
                    }
                }
                return results;
            }""")

            print(f"[6b] Mention popup elements: {len(mention_popup)}")
            for m in mention_popup:
                name = m['text'].replace('\n', ' | ')[:100]
                z = f" z={m.get('zIndex', '')}" if m.get('zIndex') else ""
                print(f"  ({m['x']},{m['y']}) {m['w']}x{m['h']} <{m['tag']}> '{name}' cls={m['cls'][:50]}{z}")

            # Try typing "Image" to see if dropdown narrows
            page.keyboard.type("Image", delay=50)
            page.wait_for_timeout(1000)

            screenshot(page, "05_at_image_typed")

            mention_after = page.evaluate("""() => {
                var results = [];
                for (var el of document.querySelectorAll('*')) {
                    var r = el.getBoundingClientRect();
                    var text = (el.innerText || '').trim();
                    if ((text.includes('Image1') || text.includes('Image2') || text.includes('Image3') ||
                         text.includes('@Image') || text.includes('Pic')) &&
                        r.width > 30 && r.height > 10 && r.x > 60) {
                        var s = window.getComputedStyle(el);
                        if (s.display !== 'none') {
                            results.push({
                                text: text.substring(0, 200),
                                x: Math.round(r.x), y: Math.round(r.y),
                                w: Math.round(r.width), h: Math.round(r.height),
                                cls: (typeof el.className === 'string' ? el.className : (el.className && el.className.baseVal || '')).substring(0, 80),
                                tag: el.tagName.toLowerCase()
                            });
                        }
                    }
                }
                return results;
            }""")
            print(f"[6c] After typing '@Image': {len(mention_after)} elements")
            for m in mention_after:
                name = m['text'].replace('\n', ' | ')[:100]
                print(f"  ({m['x']},{m['y']}) {m['w']}x{m['h']} '{name}' cls={m['cls'][:50]}")

            # Clear the prompt
            page.keyboard.press("Meta+a")
            page.keyboard.press("Backspace")
            page.wait_for_timeout(300)

        # ============================================================
        # 7. ASPECT RATIO OPTIONS
        # ============================================================
        print(f"\n{'='*60}")
        print("7. ASPECT RATIO OPTIONS")
        print(f"{'='*60}")

        ratios = page.evaluate("""() => {
            var items = [];
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return items;

            for (var el of panel.querySelectorAll('[class*="aspect"] *, [class*="ratio"] *, .item')) {
                var r = el.getBoundingClientRect();
                var text = (el.innerText || '').trim();
                if (r.width > 15 && r.height > 15 && text.length > 0 && text.length < 20 &&
                    el.childElementCount === 0) {
                    items.push({
                        text: text,
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        cls: (typeof el.className === 'string' ? el.className : (el.className && el.className.baseVal || '')).substring(0, 60),
                        selected: (typeof el.className === 'string' && (el.className.includes('active') || el.className.includes('selected'))) ||
                                  window.getComputedStyle(el.parentElement || el).backgroundColor.includes('rgb(99')
                    });
                }
            }
            // Deduplicate
            var unique = [], seen = new Set();
            for (var item of items) {
                if (!seen.has(item.text)) { seen.add(item.text); unique.push(item); }
            }
            return unique;
        }""")

        print(f"[7] Aspect ratios: {len(ratios)}")
        for r in ratios:
            sel = " [SELECTED]" if r['selected'] else ""
            print(f"  ({r['x']},{r['y']}) {r['w']}x{r['h']} '{r['text']}' cls={r['cls'][:40]}{sel}")

        # ============================================================
        # 8. VERSION/MODE SELECTORS
        # ============================================================
        print(f"\n{'='*60}")
        print("8. VERSION/MODE SELECTORS")
        print(f"{'='*60}")

        versions = page.evaluate("""() => {
            var items = [];
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return items;

            // Look for version buttons (V1/V2), mode buttons (Fast/Normal/HQ)
            for (var el of panel.querySelectorAll('button, [role="button"], .options button, [class*="option"] button')) {
                var r = el.getBoundingClientRect();
                var text = (el.innerText || '').trim();
                if (r.width > 20 && text.length > 0 && text.length < 30) {
                    items.push({
                        text: text,
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        cls: (typeof el.className === 'string' ? el.className : (el.className && el.className.baseVal || '')).substring(0, 60),
                        selected: typeof el.className === 'string' && (el.className.includes('active') || el.className.includes('selected')),
                        disabled: el.disabled || false
                    });
                }
            }
            return items;
        }""")

        print(f"[8] Buttons found: {len(versions)}")
        for v in versions:
            sel = " [SELECTED]" if v['selected'] else ""
            dis = " [DISABLED]" if v['disabled'] else ""
            print(f"  ({v['x']},{v['y']}) {v['w']}x{v['h']} '{v['text']}' cls={v['cls'][:40]}{sel}{dis}")

        # ============================================================
        # 9. STYLE SELECTOR
        # ============================================================
        print(f"\n{'='*60}")
        print("9. STYLE SELECTOR")
        print(f"{'='*60}")

        style_info = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return null;

            // Find style button/label
            for (var el of panel.querySelectorAll('button.style, .style-name, [class*="style-btn"], [class*="style"]')) {
                var r = el.getBoundingClientRect();
                var text = (el.innerText || '').trim();
                if (r.width > 50 && text.length > 0 && text.length < 50 && r.y > 50) {
                    return {
                        text: text,
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        cls: (typeof el.className === 'string' ? el.className : (el.className && el.className.baseVal || '')).substring(0, 80),
                        tag: el.tagName.toLowerCase()
                    };
                }
            }
            return null;
        }""")

        if style_info:
            print(f"[9] Style: '{style_info['text']}' at ({style_info['x']},{style_info['y']})")
            print(f"    cls={style_info['cls']}")
        else:
            print("[9] No style selector found in panel")

        # ============================================================
        # 10. GENERATE BUTTON & CREDITS
        # ============================================================
        print(f"\n{'='*60}")
        print("10. GENERATE BUTTON & CREDITS")
        print(f"{'='*60}")

        gen_btn = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return null;

            // Find generate button
            for (var el of panel.querySelectorAll('button')) {
                var text = (el.innerText || '').trim().toLowerCase();
                if (text.includes('generate') || text.includes('create')) {
                    var r = el.getBoundingClientRect();
                    return {
                        text: (el.innerText || '').trim(),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        cls: (typeof el.className === 'string' ? el.className : (el.className && el.className.baseVal || '')).substring(0, 80),
                        id: (el.id || '').substring(0, 40),
                        disabled: el.disabled || false
                    };
                }
            }
            return null;
        }""")

        if gen_btn:
            print(f"[10] Generate: '{gen_btn['text']}' at ({gen_btn['x']},{gen_btn['y']})")
            print(f"     id='{gen_btn['id']}' cls={gen_btn['cls']}")
            print(f"     disabled={gen_btn['disabled']}")
        else:
            print("[10] No generate button found")

        screenshot(page, "06_full_panel")

        # ============================================================
        # 11. FULL PANEL TEXT DUMP
        # ============================================================
        print(f"\n{'='*60}")
        print("11. FULL PANEL TEXT DUMP")
        print(f"{'='*60}")

        full_text = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (panel) return panel.innerText;

            // Try broader search
            for (var el of document.querySelectorAll('*')) {
                var r = el.getBoundingClientRect();
                if (r.x > 60 && r.x < 400 && r.width > 200 && r.height > 300) {
                    var s = window.getComputedStyle(el);
                    if (s.display !== 'none') {
                        var text = (el.innerText || '').trim();
                        if (text.includes('Storyboard') || text.includes('storyboard') ||
                            text.includes('Generate') || text.includes('@Image')) {
                            return text;
                        }
                    }
                }
            }
            return 'NO PANEL FOUND';
        }""")

        print("[11] Panel text:")
        for line in full_text.split('\n'):
            line = line.strip()
            if line:
                print(f"  | {line}")

        # ============================================================
        # 12. COMPLETE DOM STRUCTURE
        # ============================================================
        print(f"\n{'='*60}")
        print("12. PANEL DOM STRUCTURE")
        print(f"{'='*60}")

        dom_tree = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return 'NO .c-gen-config.show PANEL';

            function dumpTree(el, depth) {
                if (depth > 5) return '';
                var r = el.getBoundingClientRect();
                if (r.width <= 0 || r.height <= 0) return '';
                var indent = '  '.repeat(depth);
                var tag = el.tagName.toLowerCase();
                var cls = typeof el.className === 'string' ? el.className.trim() : (el.className && el.className.baseVal || '').trim();
                cls = cls.substring(0, 50);
                var text = '';
                for (var n of el.childNodes) {
                    if (n.nodeType === 3) text += n.textContent.trim();
                }
                text = text.substring(0, 40);
                var id = el.id ? '#' + el.id : '';
                var line = indent + '<' + tag + id + (cls ? '.' + cls.split(' ').join('.') : '') + '>';
                if (text) line += ' "' + text + '"';
                line += ' (' + Math.round(r.x) + ',' + Math.round(r.y) + ' ' + Math.round(r.width) + 'x' + Math.round(r.height) + ')';
                var result = line + '\\n';
                for (var child of el.children) {
                    result += dumpTree(child, depth + 1);
                }
                return result;
            }
            return dumpTree(panel, 0);
        }""")

        print("[12] DOM tree:")
        for line in dom_tree.split('\n')[:80]:
            if line.strip():
                print(f"  {line}")

        # ============================================================
        # 13. ALL PANELS/SECTIONS IN PAGE (broader search)
        # ============================================================
        print(f"\n{'='*60}")
        print("13. BROADER PANEL SEARCH")
        print(f"{'='*60}")

        all_panels = page.evaluate("""() => {
            var results = [];
            for (var el of document.querySelectorAll('[class*="storyboard"], [class*="instant"], [class*="story"], [class*="combine"]')) {
                var r = el.getBoundingClientRect();
                results.push({
                    tag: el.tagName.toLowerCase(),
                    cls: (typeof el.className === 'string' ? el.className : (el.className && el.className.baseVal || '')).substring(0, 100),
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    text: (el.innerText || '').trim().substring(0, 200),
                    visible: r.width > 0 && r.height > 0
                });
            }
            return results;
        }""")

        print(f"[13] Storyboard-related elements: {len(all_panels)}")
        for p in all_panels:
            vis = " [VISIBLE]" if p['visible'] else " [hidden]"
            name = p['text'].replace('\n', ' | ')[:80]
            print(f"  <{p['tag']}> cls={p['cls'][:60]} ({p['x']},{p['y']}) {p['w']}x{p['h']}{vis}")
            if name:
                print(f"    text: '{name}'")

        # ============================================================
        # 14. SCROLL PANEL IF NEEDED
        # ============================================================
        print(f"\n{'='*60}")
        print("14. SCROLL PANEL TO REVEAL MORE")
        print(f"{'='*60}")

        scrolled = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return 'no panel';
            // Check if panel has scrollable content
            var scrollables = [];
            for (var el of panel.querySelectorAll('*')) {
                var s = window.getComputedStyle(el);
                if ((s.overflowY === 'auto' || s.overflowY === 'scroll') &&
                    el.scrollHeight > el.clientHeight + 20) {
                    scrollables.push({
                        cls: (typeof el.className === 'string' ? el.className : (el.className && el.className.baseVal || '')).substring(0, 50),
                        scrollHeight: el.scrollHeight,
                        clientHeight: el.clientHeight,
                        scrollTop: el.scrollTop
                    });
                    el.scrollTop = 0;  // Reset to top first
                }
            }
            return scrollables.length > 0 ? scrollables : 'no scrollable areas';
        }""")
        print(f"[14] Scrollable areas: {json.dumps(scrolled, indent=2) if isinstance(scrolled, list) else scrolled}")

        if isinstance(scrolled, list) and len(scrolled) > 0:
            screenshot(page, "07_panel_scrolled_top")
            # Scroll down
            page.evaluate("""() => {
                var panel = document.querySelector('.c-gen-config.show');
                if (!panel) return;
                for (var el of panel.querySelectorAll('*')) {
                    var s = window.getComputedStyle(el);
                    if ((s.overflowY === 'auto' || s.overflowY === 'scroll') &&
                        el.scrollHeight > el.clientHeight + 20) {
                        el.scrollTop = el.scrollHeight;
                    }
                }
            }""")
            page.wait_for_timeout(500)
            screenshot(page, "08_panel_scrolled_bottom")

            # Read bottom content
            bottom_text = page.evaluate("""() => {
                var panel = document.querySelector('.c-gen-config.show');
                if (!panel) return '';
                return panel.innerText;
            }""")
            print("[14b] Panel text after scroll:")
            for line in bottom_text.split('\n'):
                line = line.strip()
                if line:
                    print(f"  | {line}")

        # ============================================================
        # 15. CHECK V1/V2 TOGGLE
        # ============================================================
        print(f"\n{'='*60}")
        print("15. V1/V2 VERSION TOGGLE (if present)")
        print(f"{'='*60}")

        # Look for V1/V2 buttons
        v_toggle = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return [];
            var items = [];
            for (var el of panel.querySelectorAll('button, [role="button"]')) {
                var text = (el.innerText || '').trim();
                if (/^V\d$/.test(text) || text === 'V1' || text === 'V2') {
                    var r = el.getBoundingClientRect();
                    items.push({
                        text: text,
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        cls: (typeof el.className === 'string' ? el.className : (el.className && el.className.baseVal || '')).substring(0, 60),
                        selected: typeof el.className === 'string' && (el.className.includes('active') || el.className.includes('selected'))
                    });
                }
            }
            return items;
        }""")

        print(f"[15] V1/V2 toggles: {len(v_toggle)}")
        for v in v_toggle:
            sel = " [SELECTED]" if v['selected'] else ""
            print(f"  ({v['x']},{v['y']}) {v['w']}x{v['h']} '{v['text']}' cls={v['cls'][:40]}{sel}")

        # If V2 exists and not selected, try clicking it to see differences
        v2_btn = next((v for v in v_toggle if v['text'] == 'V2' and not v['selected']), None)
        if v2_btn:
            print("[15b] Clicking V2 to compare...")
            page.mouse.click(v2_btn['x'] + v2_btn['w'] // 2, v2_btn['y'] + v2_btn['h'] // 2)
            page.wait_for_timeout(1500)

            v2_text = page.evaluate("""() => {
                var panel = document.querySelector('.c-gen-config.show');
                return panel ? panel.innerText : '';
            }""")
            print("[15b] V2 panel text:")
            for line in v2_text.split('\n'):
                line = line.strip()
                if line:
                    print(f"  | {line}")

            screenshot(page, "09_v2_panel")

            # Check V2 credits
            v2_gen = page.evaluate("""() => {
                var panel = document.querySelector('.c-gen-config.show');
                if (!panel) return null;
                for (var el of panel.querySelectorAll('button')) {
                    var text = (el.innerText || '').trim().toLowerCase();
                    if (text.includes('generate') || text.includes('create')) {
                        return (el.innerText || '').trim();
                    }
                }
                return null;
            }""")
            print(f"[15b] V2 Generate button: '{v2_gen}'")

        # ============================================================
        # 16. PICS INPUT (number of images selector)
        # ============================================================
        print(f"\n{'='*60}")
        print("16. IMAGE COUNT / PICS SELECTOR")
        print(f"{'='*60}")

        pics_selector = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return [];
            var items = [];
            // Look for "2 pics", "3 pics" or number selectors
            for (var el of panel.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                if ((text.includes('pic') || text.includes('Pic') || text.includes('image') ||
                     /^\d$/.test(text)) && el.childElementCount === 0) {
                    var r = el.getBoundingClientRect();
                    if (r.width > 10 && r.height > 10) {
                        items.push({
                            text: text.substring(0, 40),
                            x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height),
                            cls: (typeof el.className === 'string' ? el.className : (el.className && el.className.baseVal || '')).substring(0, 60),
                            tag: el.tagName.toLowerCase()
                        });
                    }
                }
            }
            return items;
        }""")

        print(f"[16] Pics selectors: {len(pics_selector)}")
        for p in pics_selector:
            print(f"  ({p['x']},{p['y']}) {p['w']}x{p['h']} <{p['tag']}> '{p['text']}' cls={p['cls'][:40]}")

        # ============================================================
        # 17. FINAL COMPREHENSIVE SCREENSHOT
        # ============================================================
        print(f"\n{'='*60}")
        print("17. FINAL SCREENSHOTS")
        print(f"{'='*60}")

        # Scroll panel back to top
        page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return;
            for (var el of panel.querySelectorAll('*')) {
                var s = window.getComputedStyle(el);
                if ((s.overflowY === 'auto' || s.overflowY === 'scroll') &&
                    el.scrollHeight > el.clientHeight + 20) {
                    el.scrollTop = 0;
                }
            }
        }""")
        page.wait_for_timeout(300)
        screenshot(page, "10_final_panel_top")

        # ============================================================
        # SUMMARY
        # ============================================================
        print("\n" + "=" * 70)
        print("PHASE 155 SUMMARY")
        print("=" * 70)
        print(f"  Panel detected: {panel_info['type'] if panel_info else 'NONE'}")
        print(f"  Upload slots: {len(upload_slots)}")
        print(f"  Prompt areas: {len(prompt_area)}")
        print(f"  Aspect ratios: {len(ratios)}")
        print(f"  Version toggles: {len(v_toggle)}")
        print(f"  Buttons: {len(versions)}")
        print(f"  Mention popup elements: {len(mention_popup) if 'mention_popup' in dir() else 'N/A'}")
        print(f"  Screenshots: {OUTPUT_DIR}")
        print("=" * 70)

    finally:
        # Don't call pw.stop() on CDP — it can hang
        # Just let it go out of scope
        try:
            pw.stop()
        except Exception:
            pass


if __name__ == "__main__":
    main()
