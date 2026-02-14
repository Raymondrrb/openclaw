#!/usr/bin/env python3
"""Phase 152: Style Catalog — Extract ALL styles by category.

P150 style picker extraction failed because the picker overlay opened differently.
This script tries multiple approaches to extract the full style catalog.

Also explores:
- Txt2Img mode-specific details (Fast vs Normal vs HQ cost and quality)
- Negative prompt in Advanced
- Reference image handling
- Prompt Improver toggle behavior
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


def main():
    from playwright.sync_api import sync_playwright
    from tools.lib.brave_profile import DEFAULT_CDP_PORT, is_browser_running
    from tools.lib.dzine_browser import close_all_dialogs, VIEWPORT

    print("=" * 70)
    print("PHASE 152: Style Catalog & Txt2Img Deep Details")
    print("=" * 70)

    if not is_browser_running():
        print("[P152] ERROR: Brave not running.")
        return

    pw = sync_playwright().start()
    try:
        browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{DEFAULT_CDP_PORT}")
        context = browser.contexts[0]

        dzine_pages = [p for p in context.pages if "dzine.ai/canvas" in (p.url or "")]
        if not dzine_pages:
            print("[P152] No Dzine canvas found.")
            return

        page = dzine_pages[0]
        page.set_viewport_size(VIEWPORT)
        page.bring_to_front()
        page.wait_for_timeout(1500)
        print(f"[P152] Canvas: {page.url}")

        close_all_dialogs(page)
        page.wait_for_timeout(500)

        # Close any panels
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
        page.evaluate("""() => {
            for (var el of document.querySelectorAll('.c-gen-config.show .ico-close, .panels.show .ico-close')) el.click();
        }""")
        page.wait_for_timeout(500)

        # ============================================================
        # 1. OPEN TXT2IMG
        # ============================================================
        page.mouse.click(40, 252)  # Img2Img first
        page.wait_for_timeout(500)
        page.mouse.click(40, 197)  # Txt2Img
        page.wait_for_timeout(2000)

        # ============================================================
        # 2. STYLE PICKER — Multiple approaches
        # ============================================================
        print(f"\n{'='*60}")
        print("2. STYLE PICKER")
        print(f"{'='*60}")

        # Method 1: Click the style button
        print("[2a] Clicking style button...")
        style_click = page.evaluate("""() => {
            var btn = document.querySelector('button.style');
            if (btn) {
                var r = btn.getBoundingClientRect();
                btn.click();
                return {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), text: (btn.innerText || '').trim()};
            }
            // Try style-name
            var name = document.querySelector('.style-name');
            if (name) {
                var r = name.getBoundingClientRect();
                name.click();
                return {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), text: (name.innerText || '').trim()};
            }
            return null;
        }""")
        print(f"[2a] Style click: {style_click}")
        page.wait_for_timeout(3000)

        page.screenshot(path=os.path.expanduser("~/Downloads/p152_style_picker_a.png"))

        # Check what opened
        picker = page.evaluate("""() => {
            // Method 1: style-list-panel
            var panel = document.querySelector('.style-list-panel');
            if (panel) {
                var r = panel.getBoundingClientRect();
                if (r.width > 0) return {method: 'style-list-panel', text: panel.innerText.substring(0, 500), x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)};
            }
            // Method 2: any large overlay
            for (var el of document.querySelectorAll('*')) {
                var r = el.getBoundingClientRect();
                var s = window.getComputedStyle(el);
                if (r.width > 400 && r.height > 300 && r.x > 100 && r.x < 600 &&
                    (s.position === 'fixed' || s.position === 'absolute' || parseInt(s.zIndex) > 100)) {
                    var text = (el.innerText || '').trim();
                    if (text.length > 50 && (text.includes('General') || text.includes('Realistic') || text.includes('style'))) {
                        return {
                            method: 'overlay', text: text.substring(0, 500),
                            x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height),
                            cls: (el.className || '').substring(0, 60)
                        };
                    }
                }
            }
            // Method 3: check for any new floating panels
            for (var el of document.querySelectorAll('[class*="style"], [class*="picker"], [class*="model"]')) {
                var r = el.getBoundingClientRect();
                if (r.width > 200 && r.height > 200) {
                    return {
                        method: 'class-match', text: (el.innerText || '').substring(0, 500),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        cls: (el.className || '').substring(0, 80)
                    };
                }
            }
            return null;
        }""")
        print(f"[2b] Picker found: {picker is not None}")
        if picker:
            print(f"  Method: {picker['method']}")
            print(f"  Position: ({picker['x']},{picker['y']}) {picker['w']}x{picker['h']}")
            print(f"  Content:\n{picker.get('text', '')[:400]}")

        # Method 2: If style picker uses selector-panel (like Video Editor)
        if not picker:
            print("[2c] Trying selector-panel approach...")
            sel_panel = page.evaluate("""() => {
                var panel = document.querySelector('.selector-panel');
                if (panel) {
                    var r = panel.getBoundingClientRect();
                    return {text: panel.innerText.substring(0, 2000), w: Math.round(r.width), h: Math.round(r.height)};
                }
                return null;
            }""")
            if sel_panel:
                print(f"[2c] Selector panel: {sel_panel['w']}x{sel_panel['h']}")
                print(f"[2c] Content:\n{sel_panel['text'][:500]}")

        # Method 3: Try clicking the model name text directly
        if not picker:
            print("[2d] Trying model name click...")
            page.keyboard.press("Escape")
            page.wait_for_timeout(500)
            page.evaluate("""() => {
                for (var el of document.querySelectorAll('*')) {
                    var text = (el.innerText || '').trim();
                    if (text === 'Dzine General' && el.childElementCount === 0) {
                        el.click();
                        return true;
                    }
                }
                return false;
            }""")
            page.wait_for_timeout(2000)
            page.screenshot(path=os.path.expanduser("~/Downloads/p152_style_picker_d.png"))

        # Extract ALL style items from whatever panel opened
        print("\n[2e] Extracting all style items...")
        all_styles = page.evaluate("""() => {
            var items = [];
            // Look for items with images (style cards typically have thumbnails)
            for (var el of document.querySelectorAll('[class*="style-item"], [class*="model-item"], .select-item, [class*="style-card"]')) {
                var r = el.getBoundingClientRect();
                var text = (el.innerText || '').trim();
                if (r.width > 30 && r.height > 30 && text.length > 0) {
                    items.push({
                        text: text.substring(0, 100),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        cls: (el.className || '').substring(0, 50),
                        selected: el.className.includes('active') || el.className.includes('selected')
                    });
                }
            }
            return items;
        }""")
        print(f"[2e] Style items: {len(all_styles)}")
        for s in all_styles[:30]:
            sel = " [SEL]" if s['selected'] else ""
            name = s['text'].replace('\n', ' | ')[:60]
            print(f"  ({s['x']},{s['y']}) {s['w']}x{s['h']} '{name}'{sel}")

        # Try scrolling within the picker to find more
        if all_styles:
            print("\n[2f] Scrolling picker...")
            page.evaluate("""() => {
                for (var el of document.querySelectorAll('*')) {
                    var s = window.getComputedStyle(el);
                    if ((s.overflowY === 'auto' || s.overflowY === 'scroll') &&
                        el.scrollHeight > el.clientHeight + 50 &&
                        el.getBoundingClientRect().x > 300 &&
                        el.getBoundingClientRect().width > 200) {
                        el.scrollTop = el.scrollHeight;
                        return true;
                    }
                }
                return false;
            }""")
            page.wait_for_timeout(1000)

            more_styles = page.evaluate("""() => {
                var items = [];
                for (var el of document.querySelectorAll('[class*="style-item"], [class*="model-item"], .select-item, [class*="style-card"]')) {
                    var r = el.getBoundingClientRect();
                    var text = (el.innerText || '').trim();
                    if (r.width > 30 && r.height > 30 && text.length > 0) {
                        items.push({text: text.substring(0, 100)});
                    }
                }
                return items;
            }""")
            print(f"[2f] After scroll: {len(more_styles)} items")
            for s in more_styles[:15]:
                name = s['text'].replace('\n', ' | ')[:60]
                print(f"    '{name}'")

        # Check categories/tabs
        print("\n[2g] Categories/tabs...")
        tabs = page.evaluate("""() => {
            var items = [];
            for (var el of document.querySelectorAll('button, [role="tab"], [class*="tab"]')) {
                var r = el.getBoundingClientRect();
                var text = (el.innerText || '').trim();
                if (r.width > 0 && r.x > 300 && r.x < 900 && r.y > 50 && r.y < 150 &&
                    text.length > 1 && text.length < 30) {
                    items.push({
                        text: text,
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width),
                        cls: (el.className || '').substring(0, 40),
                        selected: el.className.includes('active') || el.className.includes('selected')
                    });
                }
            }
            var unique = [], seen = new Set();
            for (var item of items) {
                if (!seen.has(item.text)) { seen.add(item.text); unique.push(item); }
            }
            return unique;
        }""")
        print(f"[2g] Tabs: {len(tabs)}")
        for t in tabs:
            sel = " [SEL]" if t['selected'] else ""
            print(f"  ({t['x']},{t['y']}) w={t['w']} '{t['text']}' cls={t['cls'][:30]}{sel}")

        # If categories found, iterate each one
        all_style_catalog = {}
        if tabs:
            for tab in tabs:
                print(f"\n  Clicking category: {tab['text']}")
                page.mouse.click(tab['x'] + tab['w'] // 2, tab['y'] + 10)
                page.wait_for_timeout(1500)

                cat_styles = page.evaluate("""() => {
                    var items = [];
                    for (var el of document.querySelectorAll('[class*="style-item"], [class*="model-item"], .select-item, [class*="style-card"]')) {
                        var r = el.getBoundingClientRect();
                        var text = (el.innerText || '').trim();
                        if (r.width > 30 && r.height > 30 && text.length > 0 && r.y > 100) {
                            items.push(text.split('\\n')[0].trim().substring(0, 60));
                        }
                    }
                    return [...new Set(items)];
                }""")
                all_style_catalog[tab['text']] = cat_styles
                print(f"    Found: {len(cat_styles)} styles")
                for s in cat_styles[:10]:
                    print(f"      {s}")

        page.screenshot(path=os.path.expanduser("~/Downloads/p152_styles_catalog.png"))

        # Close picker
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)

        # ============================================================
        # 3. TXT2IMG DETAILED SETTINGS
        # ============================================================
        print(f"\n{'='*60}")
        print("3. TXT2IMG MODE DETAILS")
        print(f"{'='*60}")

        # Read current panel state with ALL details
        txt2img_full = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return null;

            var result = {text: panel.innerText, elements: []};

            // Get ALL elements with their exact state
            for (var el of panel.querySelectorAll('*')) {
                var r = el.getBoundingClientRect();
                var text = (el.innerText || '').trim();

                if (r.width > 0 && r.height > 0 && text.length > 0 && text.length < 30 &&
                    el.childElementCount === 0 && r.x > 60 && r.x < 400 && r.y > 50 && r.y < 850) {
                    var s = window.getComputedStyle(el);
                    result.elements.push({
                        text: text,
                        tag: el.tagName,
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        cls: (el.className || '').substring(0, 40),
                        color: s.color,
                        fontSize: s.fontSize,
                        fontWeight: s.fontWeight,
                        bg: s.backgroundColor
                    });
                }
            }
            return result;
        }""")
        if txt2img_full:
            print(f"[3] Panel elements: {len(txt2img_full['elements'])}")
            for e in txt2img_full['elements'][:40]:
                highlight = ""
                if "rgb(255" in (e.get('bg') or '') or "rgb(229" in (e.get('bg') or ''):
                    highlight = " [HIGHLIGHTED]"
                print(f"  ({e['x']},{e['y']}) {e['w']}x{e['h']} '{e['text']}' size={e['fontSize']} weight={e['fontWeight']}{highlight}")

        # ============================================================
        # 4. CHECK MODE BUTTON COSTS
        # ============================================================
        print(f"\n{'='*60}")
        print("4. GENERATION MODE COSTS")
        print(f"{'='*60}")

        # Click Fast mode and check generate button credits
        for mode_name in ["Fast", "Normal", "HQ"]:
            page.evaluate(f"""() => {{
                for (var el of document.querySelectorAll('.c-gen-config.show button')) {{
                    if ((el.innerText || '').trim() === '{mode_name}') {{ el.click(); return true; }}
                }}
                return false;
            }}""")
            page.wait_for_timeout(500)

            gen_credits = page.evaluate("""() => {
                var btn = document.querySelector('#txt2img-generate-btn') ||
                          document.querySelector('.c-gen-config.show .generative');
                if (btn) {
                    return (btn.innerText || '').trim();
                }
                return null;
            }""")
            print(f"  {mode_name}: Generate button says '{gen_credits}'")

        # ============================================================
        # 5. PROMPT IMPROVER TOGGLE
        # ============================================================
        print(f"\n{'='*60}")
        print("5. PROMPT IMPROVER")
        print(f"{'='*60}")

        prompt_improver = page.evaluate("""() => {
            for (var el of document.querySelectorAll('.c-gen-config.show *')) {
                var text = (el.innerText || '').trim();
                if (text === 'Prompt Improver') {
                    var r = el.getBoundingClientRect();
                    // Find nearby switch
                    var parent = el.parentElement;
                    var sw = parent.querySelector('.c-switch');
                    if (!sw) sw = el.nextElementSibling;
                    var swState = sw ? (sw.className.includes('isChecked') ? 'ON' : 'OFF') : 'unknown';
                    return {
                        text: text,
                        x: Math.round(r.x), y: Math.round(r.y),
                        switchState: swState,
                        switchCls: sw ? sw.className.substring(0, 40) : ''
                    };
                }
            }
            return null;
        }""")
        print(f"[5] Prompt Improver: {prompt_improver}")

        # ============================================================
        # 6. ASPECT RATIO OPTIONS
        # ============================================================
        print(f"\n{'='*60}")
        print("6. ASPECT RATIOS")
        print(f"{'='*60}")

        ratios = page.evaluate("""() => {
            var items = [];
            for (var el of document.querySelectorAll('.c-gen-config.show .c-aspect-ratio *, .c-gen-config.show [class*="aspect"] *')) {
                var r = el.getBoundingClientRect();
                var text = (el.innerText || '').trim();
                if (r.width > 0 && text.length > 0 && text.length < 20 && el.childElementCount === 0) {
                    items.push({
                        text: text,
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        cls: (el.className || '').substring(0, 40),
                        selected: el.className.includes('active') || el.className.includes('selected') || el.className.includes('canvas')
                    });
                }
            }
            var unique = [], seen = new Set();
            for (var item of items) {
                if (!seen.has(item.text)) { seen.add(item.text); unique.push(item); }
            }
            return unique;
        }""")
        print(f"[6] Aspect ratios: {len(ratios)}")
        for r in ratios:
            sel = " [SELECTED]" if r['selected'] else ""
            print(f"  ({r['x']},{r['y']}) {r['w']}x{r['h']} '{r['text']}' cls={r['cls'][:30]}{sel}")

        # ============================================================
        # 7. NEGATIVE PROMPT (in Advanced)
        # ============================================================
        print(f"\n{'='*60}")
        print("7. NEGATIVE PROMPT")
        print(f"{'='*60}")

        # Open Advanced section
        page.evaluate("""() => {
            var btn = document.querySelector('.c-gen-config.show .advanced-btn');
            if (btn) { btn.click(); return true; }
            return false;
        }""")
        page.wait_for_timeout(1000)

        neg_prompt = page.evaluate("""() => {
            for (var el of document.querySelectorAll('.c-gen-config.show textarea, .c-gen-config.show [contenteditable]')) {
                var r = el.getBoundingClientRect();
                var ph = el.placeholder || el.getAttribute('data-placeholder') || '';
                if (ph.toLowerCase().includes('negative') || r.y > 550) {
                    return {
                        tag: el.tagName,
                        placeholder: ph.substring(0, 80),
                        value: (el.value || el.innerText || '').substring(0, 100),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        cls: (el.className || '').substring(0, 50)
                    };
                }
            }
            return null;
        }""")
        print(f"[7] Negative prompt: {neg_prompt}")

        # Check all text in advanced area
        adv_section = page.evaluate("""() => {
            for (var el of document.querySelectorAll('.c-gen-config.show [class*="advanced"]')) {
                var text = (el.innerText || '').trim();
                if (text.length > 10) return text.substring(0, 500);
            }
            return null;
        }""")
        print(f"[7b] Advanced section: {adv_section}")

        page.screenshot(path=os.path.expanduser("~/Downloads/p152_advanced.png"))

        # ============================================================
        # 8. CHAT EDITOR MODEL CREDITS
        # ============================================================
        print(f"\n{'='*60}")
        print("8. CHAT EDITOR — Per-model credits check")
        print(f"{'='*60}")

        # Close panels
        page.evaluate("""() => {
            for (var el of document.querySelectorAll('.c-gen-config.show .ico-close')) el.click();
        }""")
        page.wait_for_timeout(500)

        # Read current generate button state
        chat_gen = page.evaluate("""() => {
            var btn = document.querySelector('#chat-editor-generate-btn');
            if (btn) {
                return {
                    text: (btn.innerText || '').trim(),
                    disabled: btn.disabled,
                    x: Math.round(btn.getBoundingClientRect().x),
                    y: Math.round(btn.getBoundingClientRect().y),
                    cls: (btn.className || '').substring(0, 40)
                };
            }
            return null;
        }""")
        print(f"[8] Generate button: {chat_gen}")

        # Open model selector and check each model's credit cost
        page.evaluate("""() => {
            var btn = document.querySelector('button.option-btn');
            if (btn) { btn.click(); return true; }
            return false;
        }""")
        page.wait_for_timeout(1500)

        # Get all model items with their details
        chat_models = page.evaluate("""() => {
            var items = [];
            for (var el of document.querySelectorAll('.option-item, [class*="option-item"]')) {
                var r = el.getBoundingClientRect();
                var text = (el.innerText || '').trim();
                if (r.width > 0 && text.length > 0) {
                    items.push({
                        text: text.substring(0, 100),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        cls: (el.className || '').substring(0, 50),
                        selected: el.className.includes('active') || el.className.includes('selected')
                    });
                }
            }
            return items;
        }""")
        print(f"\n[8b] Chat Editor models: {len(chat_models)}")
        for m in chat_models:
            sel = " [SEL]" if m['selected'] else ""
            name = m['text'].replace('\n', ' | ')[:80]
            print(f"  ({m['x']},{m['y']}) {m['w']}x{m['h']} '{name}'{sel}")

        page.screenshot(path=os.path.expanduser("~/Downloads/p152_chat_models.png"))
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)

        # ============================================================
        # SUMMARY
        # ============================================================
        print("\n" + "=" * 70)
        print("PHASE 152 SUMMARY")
        print("=" * 70)
        print(f"  Styles catalog: {sum(len(v) for v in all_style_catalog.values())} styles across {len(all_style_catalog)} categories")
        print(f"  Check ~/Downloads/p152_*.png for screenshots")

        # Save catalog to JSON for reference
        if all_style_catalog:
            out = Path(os.path.expanduser("~/Downloads/p152_style_catalog.json"))
            out.write_text(json.dumps(all_style_catalog, indent=2))
            print(f"  Style catalog saved to: {out}")

    finally:
        pw.stop()


if __name__ == "__main__":
    main()
