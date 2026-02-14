#!/usr/bin/env python3
"""Phase 154: AI Expand (Outpainting) — Full UI exploration and documentation.

Explores the Generative Expand sub-tool inside Image Editor:
- How to access it (sidebar > Image Editor > Expand)
- Aspect ratio options (9 presets)
- Prompt input (optional, 1800 char max)
- Generate button (8 credits, 4 variants)
- Canvas drag handles for interactive expansion
- Tests expanding an image if one is on canvas
- Documents all selectors for automation

Saves screenshots to /tmp/dzine_explore_154/
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

SCREENSHOT_DIR = Path("/tmp/dzine_explore_154")
SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)


def shot(page, name: str) -> str:
    """Take a screenshot and return the path."""
    path = str(SCREENSHOT_DIR / f"{name}.png")
    page.screenshot(path=path)
    print(f"  [screenshot] {path}")
    return path


def main():
    from playwright.sync_api import sync_playwright
    from tools.lib.brave_profile import DEFAULT_CDP_PORT, is_browser_running
    from tools.lib.dzine_browser import close_all_dialogs, VIEWPORT, SIDEBAR

    print("=" * 70)
    print("PHASE 154: AI Expand (Outpainting) — Full UI Exploration")
    print("=" * 70)

    if not is_browser_running():
        print("[P154] ERROR: Brave not running on CDP port.")
        return

    pw = sync_playwright().start()
    try:
        browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{DEFAULT_CDP_PORT}")
        context = browser.contexts[0]

        # Find or navigate to Dzine canvas
        dzine_pages = [p for p in context.pages if "dzine.ai/canvas" in (p.url or "")]
        if dzine_pages:
            page = dzine_pages[0]
            print(f"[P154] Reusing existing canvas tab: {page.url}")
        else:
            print("[P154] No canvas tab found, navigating...")
            page = context.new_page()
            page.goto("https://www.dzine.ai/canvas?id=19797967", wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(3000)

        page.set_viewport_size(VIEWPORT)
        page.bring_to_front()
        page.wait_for_timeout(2000)

        # Close popups
        close_all_dialogs(page)
        page.wait_for_timeout(500)

        # Press Escape to clear any existing panel
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)
        page.evaluate("""() => {
            for (var el of document.querySelectorAll('.c-gen-config.show .ico-close, .panels.show .ico-close')) el.click();
        }""")
        page.wait_for_timeout(500)

        shot(page, "00_canvas_clean")

        # ============================================================
        # STEP 1: Check if there's an image on canvas (needed for Image Editor)
        # ============================================================
        print(f"\n{'='*60}")
        print("STEP 1: Check canvas for existing images")
        print(f"{'='*60}")

        canvas_state = page.evaluate("""() => {
            var imgs = document.querySelectorAll('img[src*="static.dzine.ai"]');
            var layers = document.querySelectorAll('[class*="layer-item"], [class*="layer_item"]');
            var canvasImgs = document.querySelectorAll('canvas');
            return {
                staticImages: imgs.length,
                layers: layers.length,
                canvasElements: canvasImgs.length,
                anySelected: !!document.querySelector('.layer-item.active, [class*="layer-item"][class*="active"]')
            };
        }""")
        print(f"[1] Canvas state: {canvas_state}")

        # Check for any image on the actual canvas area
        has_canvas_image = page.evaluate("""() => {
            // Look for fabricjs canvas or any image element in the canvas area
            var cvs = document.querySelector('canvas.upper-canvas, canvas.lower-canvas');
            if (cvs) return true;
            // Check for image layers
            var imgs = document.querySelectorAll('.canvas-area img, .canvas-container img');
            return imgs.length > 0;
        }""")
        print(f"[1] Has canvas content: {has_canvas_image}")

        # ============================================================
        # STEP 2: Open Image Editor sidebar
        # ============================================================
        print(f"\n{'='*60}")
        print("STEP 2: Open Image Editor")
        print(f"{'='*60}")

        # Image Editor is at sidebar position (40, 698)
        ie_x, ie_y = SIDEBAR.get("image_editor", (40, 698))
        print(f"[2] Clicking Image Editor sidebar icon at ({ie_x}, {ie_y})")
        page.mouse.click(ie_x, ie_y)
        page.wait_for_timeout(2000)

        close_all_dialogs(page)
        page.wait_for_timeout(500)

        shot(page, "01_image_editor_panel")

        # Read the Image Editor panel contents
        ie_panel = page.evaluate("""() => {
            // The Image Editor opens as a panels overview
            var panel = document.querySelector('.panels.show') || document.querySelector('.c-gen-config.show');
            if (!panel) {
                // Might be a collapsed panel, check any visible panel
                for (var el of document.querySelectorAll('[class*="panel"]')) {
                    var r = el.getBoundingClientRect();
                    if (r.width > 200 && r.height > 200 && r.x < 400) {
                        return {
                            found: true,
                            text: (el.innerText || '').substring(0, 1500),
                            cls: (el.className || '').substring(0, 80),
                            x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height)
                        };
                    }
                }
                return null;
            }
            return {
                found: true,
                text: (panel.innerText || '').substring(0, 1500),
                cls: (panel.className || '').substring(0, 80),
                x: Math.round(panel.getBoundingClientRect().x),
                y: Math.round(panel.getBoundingClientRect().y),
                w: Math.round(panel.getBoundingClientRect().width),
                h: Math.round(panel.getBoundingClientRect().height)
            };
        }""")
        print(f"[2] Image Editor panel: {ie_panel is not None}")
        if ie_panel:
            print(f"  Class: {ie_panel.get('cls', '')}")
            print(f"  Position: ({ie_panel.get('x')},{ie_panel.get('y')}) {ie_panel.get('w')}x{ie_panel.get('h')}")
            panel_text = ie_panel.get('text', '')
            print(f"  Content preview:\n{panel_text[:600]}")

        # ============================================================
        # STEP 3: Find and list all sub-tools in Image Editor
        # ============================================================
        print(f"\n{'='*60}")
        print("STEP 3: Enumerate Image Editor sub-tools")
        print(f"{'='*60}")

        subtools = page.evaluate("""() => {
            var items = [];
            // collapse-option items (known selector for IE sub-tools)
            for (var el of document.querySelectorAll('.collapse-option, .subtool-item')) {
                var r = el.getBoundingClientRect();
                var text = (el.innerText || '').trim();
                if (r.width > 30 && r.height > 30 && r.x < 400) {
                    items.push({
                        text: text.substring(0, 60),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        cls: (el.className || '').substring(0, 80),
                        hasGuide: el.className.includes('has-guide')
                    });
                }
            }
            return items;
        }""")
        print(f"[3] Sub-tools found: {len(subtools)}")
        for st in subtools:
            guide = " [has-guide]" if st['hasGuide'] else ""
            print(f"  ({st['x']},{st['y']}) {st['w']}x{st['h']} '{st['text']}' cls={st['cls'][:40]}{guide}")

        # ============================================================
        # STEP 4: Click the Expand sub-tool
        # ============================================================
        print(f"\n{'='*60}")
        print("STEP 4: Click Expand sub-tool")
        print(f"{'='*60}")

        # Try to find and click Expand
        expand_clicked = page.evaluate("""() => {
            // Method 1: Find collapse-option containing "Expand"
            for (var el of document.querySelectorAll('.collapse-option, .subtool-item')) {
                var text = (el.innerText || '').trim();
                if (text.toLowerCase().includes('expand')) {
                    el.click();
                    return {method: 'collapse-option', text: text, x: Math.round(el.getBoundingClientRect().x), y: Math.round(el.getBoundingClientRect().y)};
                }
            }
            // Method 2: Position-based (known at 92, 401 in Image Editor panel)
            return null;
        }""")

        if not expand_clicked:
            # Try position-based click
            print("[4] Text-based click failed, trying position (92, 401)...")
            page.mouse.click(92, 401)
            expand_clicked = {"method": "position", "x": 92, "y": 401}

        print(f"[4] Expand click: {expand_clicked}")
        page.wait_for_timeout(2000)

        close_all_dialogs(page)
        page.wait_for_timeout(500)

        shot(page, "02_expand_panel_opened")

        # ============================================================
        # STEP 5: Document the Expand panel fully
        # ============================================================
        print(f"\n{'='*60}")
        print("STEP 5: Document Generative Expand panel")
        print(f"{'='*60}")

        # Read the full panel
        expand_panel = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return null;
            return {
                text: (panel.innerText || '').substring(0, 2000),
                cls: (panel.className || '').substring(0, 80),
                x: Math.round(panel.getBoundingClientRect().x),
                y: Math.round(panel.getBoundingClientRect().y),
                w: Math.round(panel.getBoundingClientRect().width),
                h: Math.round(panel.getBoundingClientRect().height)
            };
        }""")
        if expand_panel:
            print(f"[5] Panel: ({expand_panel['x']},{expand_panel['y']}) {expand_panel['w']}x{expand_panel['h']}")
            print(f"  Full text:\n{expand_panel['text']}")
        else:
            print("[5] WARNING: c-gen-config.show not found -- checking alternative panels...")
            alt_panel = page.evaluate("""() => {
                for (var el of document.querySelectorAll('[class*="gen-config"], [class*="expand"], [class*="outpaint"]')) {
                    var r = el.getBoundingClientRect();
                    if (r.width > 150 && r.height > 200) {
                        return {text: (el.innerText || '').substring(0, 1000), cls: (el.className || '').substring(0, 80)};
                    }
                }
                return null;
            }""")
            if alt_panel:
                print(f"  Alt panel: cls={alt_panel['cls']}")
                print(f"  Text: {alt_panel['text'][:500]}")

        # ============================================================
        # STEP 6: Document aspect ratio buttons
        # ============================================================
        print(f"\n{'='*60}")
        print("STEP 6: Aspect Ratio Buttons")
        print(f"{'='*60}")

        ratios = page.evaluate("""() => {
            var items = [];
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return items;

            // Look for ratio buttons -- they typically have text like "1:1", "16:9" etc.
            for (var el of panel.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                var r = el.getBoundingClientRect();
                if (r.width > 0 && r.height > 0 && /^\d+:\d+$/.test(text) && el.childElementCount === 0) {
                    items.push({
                        text: text,
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        cls: (el.className || '').substring(0, 60),
                        tag: el.tagName,
                        active: el.className.includes('active') || el.className.includes('selected') || el.className.includes('canvas')
                    });
                }
            }
            return items;
        }""")
        print(f"[6] Aspect ratio buttons: {len(ratios)}")
        for r in ratios:
            active = " [ACTIVE]" if r['active'] else ""
            print(f"  ({r['x']},{r['y']}) {r['w']}x{r['h']} '{r['text']}' tag={r['tag']} cls={r['cls'][:40]}{active}")

        # Also look for a "Custom" or "Free" ratio option
        custom_ratio = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return null;
            for (var el of panel.querySelectorAll('*')) {
                var text = (el.innerText || '').trim().toLowerCase();
                if ((text === 'custom' || text === 'free' || text === 'original') && el.childElementCount === 0) {
                    var r = el.getBoundingClientRect();
                    if (r.width > 0 && r.height > 0) {
                        return {text: text, x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)};
                    }
                }
            }
            return null;
        }""")
        if custom_ratio:
            print(f"[6b] Custom ratio option: {custom_ratio}")

        # ============================================================
        # STEP 7: Document prompt textarea
        # ============================================================
        print(f"\n{'='*60}")
        print("STEP 7: Prompt Input")
        print(f"{'='*60}")

        prompt_info = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return null;

            // Find textarea or contenteditable
            var ta = panel.querySelector('textarea');
            if (ta) {
                var r = ta.getBoundingClientRect();
                return {
                    type: 'textarea',
                    placeholder: (ta.placeholder || '').substring(0, 200),
                    maxLength: ta.maxLength || -1,
                    value: (ta.value || '').substring(0, 100),
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    cls: (ta.className || '').substring(0, 60),
                    id: ta.id || ''
                };
            }
            // Try contenteditable
            var ce = panel.querySelector('[contenteditable]');
            if (ce) {
                var r = ce.getBoundingClientRect();
                return {
                    type: 'contenteditable',
                    placeholder: ce.getAttribute('data-placeholder') || '',
                    value: (ce.innerText || '').substring(0, 100),
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    cls: (ce.className || '').substring(0, 60)
                };
            }
            return null;
        }""")
        print(f"[7] Prompt input: {prompt_info}")

        # Check character counter
        char_counter = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return null;
            for (var el of panel.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                if (/^\d+\/\d+$/.test(text) && el.childElementCount === 0) {
                    return {
                        text: text,
                        x: Math.round(el.getBoundingClientRect().x),
                        y: Math.round(el.getBoundingClientRect().y)
                    };
                }
            }
            return null;
        }""")
        print(f"[7b] Character counter: {char_counter}")

        # ============================================================
        # STEP 8: Document Generate button
        # ============================================================
        print(f"\n{'='*60}")
        print("STEP 8: Generate Button")
        print(f"{'='*60}")

        gen_btn = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return null;

            // Look for generate / generative button
            var btn = panel.querySelector('.generative, button.generative, [class*="generate"]');
            if (!btn) {
                // Try text-based search
                for (var el of panel.querySelectorAll('button')) {
                    var text = (el.innerText || '').trim().toLowerCase();
                    if (text.includes('generate')) {
                        btn = el;
                        break;
                    }
                }
            }
            if (!btn) return null;

            var r = btn.getBoundingClientRect();
            return {
                text: (btn.innerText || '').trim(),
                x: Math.round(r.x), y: Math.round(r.y),
                w: Math.round(r.width), h: Math.round(r.height),
                cls: (btn.className || '').substring(0, 80),
                tag: btn.tagName,
                disabled: btn.disabled || btn.className.includes('disabled'),
                id: btn.id || ''
            };
        }""")
        print(f"[8] Generate button: {gen_btn}")

        # ============================================================
        # STEP 9: Document header and navigation (back arrow, close)
        # ============================================================
        print(f"\n{'='*60}")
        print("STEP 9: Header Navigation")
        print(f"{'='*60}")

        header = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return null;

            var items = [];
            var header = panel.querySelector('.gen-config-header, [class*="header"]');
            if (header) {
                var r = header.getBoundingClientRect();
                items.push({
                    type: 'header',
                    text: (header.innerText || '').trim(),
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    cls: (header.className || '').substring(0, 60)
                });

                // Back arrow
                var back = header.querySelector('.ico-back, [class*="back"], svg');
                if (back) {
                    var rb = back.getBoundingClientRect();
                    items.push({
                        type: 'back-arrow',
                        x: Math.round(rb.x), y: Math.round(rb.y),
                        w: Math.round(rb.width), h: Math.round(rb.height),
                        cls: (back.className || '').toString().substring(0, 60)
                    });
                }

                // Close
                var close = header.querySelector('.ico-close, [class*="close"]');
                if (close) {
                    var rc = close.getBoundingClientRect();
                    items.push({
                        type: 'close',
                        x: Math.round(rc.x), y: Math.round(rc.y),
                        w: Math.round(rc.width), h: Math.round(rc.height),
                        cls: (close.className || '').toString().substring(0, 60)
                    });
                }
            }
            return items;
        }""")
        print(f"[9] Header elements: {len(header or [])}")
        for h in (header or []):
            print(f"  [{h['type']}] ({h['x']},{h['y']}) {h['w']}x{h['h']} cls={h.get('cls', '')} text='{h.get('text', '')}'")

        # ============================================================
        # STEP 10: Document canvas interaction (drag handles)
        # ============================================================
        print(f"\n{'='*60}")
        print("STEP 10: Canvas Drag Handles")
        print(f"{'='*60}")

        drag_handles = page.evaluate("""() => {
            var items = [];
            // Look for expand-related UI on the canvas
            for (var el of document.querySelectorAll('[class*="expand"], [class*="drag"], [class*="handle"], [class*="edge"]')) {
                var r = el.getBoundingClientRect();
                if (r.width > 0 && r.height > 0 && r.x > 300) {
                    items.push({
                        cls: (el.className || '').toString().substring(0, 80),
                        tag: el.tagName,
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        text: (el.innerText || '').trim().substring(0, 100)
                    });
                }
            }
            return items;
        }""")
        print(f"[10] Drag handle elements: {len(drag_handles)}")
        for dh in drag_handles:
            print(f"  ({dh['x']},{dh['y']}) {dh['w']}x{dh['h']} tag={dh['tag']} cls={dh['cls'][:50]} text='{dh.get('text', '')[:40]}'")

        # Check for instruction text on canvas
        canvas_instruction = page.evaluate("""() => {
            for (var el of document.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                if (text.includes('Expand your canvas') || text.includes('dragging the edges') || text.includes('drag')) {
                    var r = el.getBoundingClientRect();
                    if (r.width > 0 && r.x > 300) {
                        return {text: text.substring(0, 200), x: Math.round(r.x), y: Math.round(r.y), cls: (el.className || '').substring(0, 60)};
                    }
                }
            }
            return null;
        }""")
        print(f"[10b] Canvas instruction: {canvas_instruction}")

        shot(page, "03_expand_panel_full")

        # ============================================================
        # STEP 11: Document all elements with their exact DOM structure
        # ============================================================
        print(f"\n{'='*60}")
        print("STEP 11: Full DOM Audit of Expand Panel")
        print(f"{'='*60}")

        all_elements = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return [];

            var items = [];
            for (var el of panel.querySelectorAll('*')) {
                var r = el.getBoundingClientRect();
                if (r.width === 0 || r.height === 0) continue;
                var text = (el.innerText || '').trim();
                var tag = el.tagName.toLowerCase();

                // Only leaf nodes or important containers
                if (el.childElementCount === 0 || ['button', 'textarea', 'input', 'div', 'span'].includes(tag)) {
                    if (text.length > 0 || ['button', 'textarea', 'input', 'svg', 'img'].includes(tag)) {
                        items.push({
                            tag: tag,
                            text: text.substring(0, 60),
                            x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height),
                            cls: (el.className || '').toString().substring(0, 60),
                            id: (el.id || ''),
                            children: el.childElementCount,
                            placeholder: (el.placeholder || el.getAttribute('data-placeholder') || '').substring(0, 80),
                            isLeaf: el.childElementCount === 0
                        });
                    }
                }
            }
            // Deduplicate by position + text
            var seen = new Set();
            return items.filter(i => {
                var key = i.x + ',' + i.y + ',' + i.text;
                if (seen.has(key)) return false;
                seen.add(key);
                return true;
            }).slice(0, 80);
        }""")
        print(f"[11] Total unique elements: {len(all_elements)}")
        for e in all_elements:
            leaf = " [LEAF]" if e['isLeaf'] else f" [{e['children']}ch]"
            id_str = f" id={e['id']}" if e['id'] else ""
            ph_str = f" ph='{e['placeholder']}'" if e.get('placeholder') else ""
            print(f"  ({e['x']},{e['y']}) {e['w']}x{e['h']} <{e['tag']}>{leaf} '{e['text'][:40]}' cls={e['cls'][:40]}{id_str}{ph_str}")

        # ============================================================
        # STEP 12: Test ratio switching
        # ============================================================
        print(f"\n{'='*60}")
        print("STEP 12: Test clicking different aspect ratios")
        print(f"{'='*60}")

        test_ratios = ["1:1", "16:9", "9:16", "4:3"]
        for ratio_text in test_ratios:
            clicked = page.evaluate(f"""() => {{
                var panel = document.querySelector('.c-gen-config.show');
                if (!panel) return null;
                for (var el of panel.querySelectorAll('*')) {{
                    var text = (el.innerText || '').trim();
                    if (text === '{ratio_text}' && el.childElementCount === 0) {{
                        var r = el.getBoundingClientRect();
                        if (r.width > 10 && r.width < 80) {{
                            el.click();
                            return {{text: text, x: Math.round(r.x), y: Math.round(r.y)}};
                        }}
                    }}
                }}
                return null;
            }}""")
            if clicked:
                print(f"  Clicked {ratio_text} at ({clicked['x']},{clicked['y']})")
                page.wait_for_timeout(500)
            else:
                print(f"  Could not find {ratio_text} button")

        shot(page, "04_after_ratio_switch")

        # Check which ratio is now active
        active_ratio = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return null;
            for (var el of panel.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                if (/^\d+:\d+$/.test(text) && el.childElementCount === 0) {
                    if (el.className.includes('active') || el.className.includes('selected')) {
                        return text;
                    }
                }
            }
            return null;
        }""")
        print(f"[12] Active ratio after switching: {active_ratio}")

        # ============================================================
        # STEP 13: Select 16:9 ratio (our standard) and fill prompt
        # ============================================================
        print(f"\n{'='*60}")
        print("STEP 13: Set 16:9 and fill test prompt")
        print(f"{'='*60}")

        # Click 16:9
        page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return;
            for (var el of panel.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                if (text === '16:9' && el.childElementCount === 0 && el.getBoundingClientRect().width > 10 && el.getBoundingClientRect().width < 80) {
                    el.click();
                    return;
                }
            }
        }""")
        page.wait_for_timeout(500)

        # Fill prompt
        test_prompt = "Clean white studio backdrop with soft professional lighting, subtle shadow underneath product"
        filled = page.evaluate(f"""() => {{
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return false;
            var ta = panel.querySelector('textarea');
            if (ta) {{
                ta.focus();
                ta.value = '{test_prompt}';
                ta.dispatchEvent(new Event('input', {{bubbles: true}}));
                ta.dispatchEvent(new Event('change', {{bubbles: true}}));
                return true;
            }}
            return false;
        }}""")
        print(f"[13] Prompt filled: {filled}")

        page.wait_for_timeout(500)
        shot(page, "05_ready_to_generate")

        # Verify prompt was set
        prompt_val = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return null;
            var ta = panel.querySelector('textarea');
            return ta ? (ta.value || '').substring(0, 200) : null;
        }""")
        print(f"[13b] Prompt value: '{prompt_val}'")

        # ============================================================
        # STEP 14: Check if Generate button is enabled
        # ============================================================
        print(f"\n{'='*60}")
        print("STEP 14: Generate Button State")
        print(f"{'='*60}")

        gen_state = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return null;

            var btn = panel.querySelector('.generative, button.generative');
            if (!btn) {
                for (var el of panel.querySelectorAll('button, div[class*="generat"]')) {
                    var text = (el.innerText || '').trim().toLowerCase();
                    if (text.includes('generate')) { btn = el; break; }
                }
            }
            if (!btn) return {found: false};

            var r = btn.getBoundingClientRect();
            var s = window.getComputedStyle(btn);
            return {
                found: true,
                text: (btn.innerText || '').trim(),
                x: Math.round(r.x), y: Math.round(r.y),
                w: Math.round(r.width), h: Math.round(r.height),
                cls: (btn.className || '').substring(0, 80),
                disabled: btn.disabled || btn.className.includes('disabled'),
                opacity: s.opacity,
                bg: s.backgroundColor,
                cursor: s.cursor,
                pointerEvents: s.pointerEvents
            };
        }""")
        print(f"[14] Generate button state: {gen_state}")

        # ============================================================
        # STEP 15: Count current result images (for polling baseline)
        # ============================================================
        print(f"\n{'='*60}")
        print("STEP 15: Current Result Image Count (baseline)")
        print(f"{'='*60}")

        baseline_count = page.evaluate("""() => {
            return document.querySelectorAll("img[src*='static.dzine.ai/stylar_product/p/']").length;
        }""")
        print(f"[15] Baseline result images: {baseline_count}")

        # ============================================================
        # STEP 16: Try to generate (only if we have a canvas image)
        # ============================================================
        print(f"\n{'='*60}")
        print("STEP 16: Attempt Generation")
        print(f"{'='*60}")

        # Check if generate button is clickable
        can_generate = gen_state and gen_state.get('found') and not gen_state.get('disabled')

        if can_generate:
            print("[16] Generate button is clickable. Attempting generation...")
            print(f"  Will click at ({gen_state['x']},{gen_state['y']}) - text: '{gen_state['text']}'")

            # Click generate
            page.evaluate("""() => {
                var panel = document.querySelector('.c-gen-config.show');
                if (!panel) return;
                var btn = panel.querySelector('.generative, button.generative');
                if (!btn) {
                    for (var el of panel.querySelectorAll('button, div[class*="generat"]')) {
                        if ((el.innerText || '').toLowerCase().includes('generate')) { btn = el; break; }
                    }
                }
                if (btn) btn.click();
            }""")
            page.wait_for_timeout(2000)

            # Handle "Image Not Filling the Canvas" dialog
            try:
                fit_btn = page.locator('button:has-text("Fit to Content and Continue")')
                if fit_btn.count() > 0 and fit_btn.first.is_visible(timeout=2000):
                    print("[16] Dismissing 'Image Not Filling' dialog...")
                    fit_btn.first.click()
                    page.wait_for_timeout(1000)
            except Exception:
                pass

            close_all_dialogs(page)
            shot(page, "06_after_generate_click")

            # Poll for completion
            print("[16] Polling for generation results (timeout 120s)...")
            start = time.time()
            completed = False
            while time.time() - start < 120:
                time.sleep(3)
                current_count = page.evaluate("""() => {
                    return document.querySelectorAll("img[src*='static.dzine.ai/stylar_product/p/']").length;
                }""")

                # Check for "Image Not Filling" dialog during generation
                try:
                    fit_btn = page.locator('button:has-text("Fit to Content and Continue")')
                    if fit_btn.count() > 0 and fit_btn.first.is_visible(timeout=500):
                        fit_btn.first.click()
                        page.wait_for_timeout(500)
                except Exception:
                    pass

                elapsed = round(time.time() - start, 1)
                if current_count > baseline_count:
                    new_images = current_count - baseline_count
                    print(f"[16] Generation complete! {new_images} new images in {elapsed}s")
                    completed = True
                    break
                else:
                    # Check for progress indicator
                    progress = page.evaluate("""() => {
                        for (var el of document.querySelectorAll('*')) {
                            var text = (el.innerText || '').trim();
                            if (/\d+%/.test(text) && text.length < 10) return text;
                        }
                        // Check for loading spinner
                        var spinner = document.querySelector('[class*="loading"], [class*="progress"], [class*="spinner"]');
                        return spinner ? 'loading...' : null;
                    }""")
                    if progress:
                        print(f"  [{elapsed}s] Progress: {progress}")
                    else:
                        print(f"  [{elapsed}s] Waiting... (images: {current_count})")

            if completed:
                shot(page, "07_generation_complete")

                # Get all new result image URLs
                result_urls = page.evaluate(f"""() => {{
                    var imgs = document.querySelectorAll("img[src*='static.dzine.ai/stylar_product/p/']");
                    var urls = [];
                    for (var i = {baseline_count}; i < imgs.length; i++) {{
                        urls.push(imgs[i].src);
                    }}
                    return urls;
                }}""")
                print(f"[16] New result URLs ({len(result_urls)}):")
                for url in result_urls:
                    print(f"  {url}")

                # Download the first result
                if result_urls:
                    import urllib.request
                    dl_path = SCREENSHOT_DIR / "expand_result_0.webp"
                    req = urllib.request.Request(result_urls[0], headers={"User-Agent": "Mozilla/5.0"})
                    try:
                        with urllib.request.urlopen(req, timeout=30) as resp:
                            data = resp.read()
                        with open(dl_path, "wb") as f:
                            f.write(data)
                        print(f"[16] Downloaded first result: {dl_path} ({len(data)} bytes)")
                    except Exception as e:
                        print(f"[16] Download error: {e}")
            else:
                print("[16] Generation timed out after 120s")
                shot(page, "07_generation_timeout")
        else:
            reason = "button not found" if not gen_state or not gen_state.get('found') else "button disabled (no image on canvas?)"
            print(f"[16] Cannot generate: {reason}")
            print("  (Expand requires a selected image layer on canvas)")

            # Investigate why -- check layer selection state
            layer_info = page.evaluate("""() => {
                var layers = [];
                for (var el of document.querySelectorAll('[class*="layer"]')) {
                    var r = el.getBoundingClientRect();
                    var text = (el.innerText || '').trim();
                    if (r.width > 0 && text.length > 0 && text.length < 100) {
                        layers.push({
                            text: text.substring(0, 50),
                            cls: (el.className || '').substring(0, 60),
                            active: el.className.includes('active')
                        });
                    }
                }
                return layers;
            }""")
            print(f"[16b] Layer state: {len(layer_info)} layer elements")
            for li in layer_info[:10]:
                act = " [ACTIVE]" if li['active'] else ""
                print(f"    '{li['text']}' cls={li['cls'][:40]}{act}")

        shot(page, "08_final_state")

        # ============================================================
        # STEP 17: Check top toolbar for AI Expand shortcut
        # ============================================================
        print(f"\n{'='*60}")
        print("STEP 17: Top Toolbar — AI Expand/Outpaint Access")
        print(f"{'='*60}")

        top_toolbar = page.evaluate("""() => {
            var items = [];
            // Top toolbar is typically in the first 80px vertically
            for (var el of document.querySelectorAll('button, [role="button"], .tool-item, [class*="toolbar"] *')) {
                var r = el.getBoundingClientRect();
                var text = (el.innerText || '').trim();
                var title = el.getAttribute('title') || el.getAttribute('aria-label') || '';
                if (r.y < 80 && r.x > 400 && r.width > 0 && r.height > 0 &&
                    (text.length > 0 || title.length > 0)) {
                    var key = text + '|' + title;
                    items.push({
                        text: text.substring(0, 40),
                        title: title.substring(0, 40),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        cls: (el.className || '').substring(0, 50),
                        tag: el.tagName
                    });
                }
            }
            // Deduplicate
            var seen = new Set();
            return items.filter(i => {
                var key = i.x + ',' + i.y;
                if (seen.has(key)) return false;
                seen.add(key);
                return true;
            }).slice(0, 30);
        }""")
        print(f"[17] Top toolbar items: {len(top_toolbar)}")
        for tb in top_toolbar:
            title = f" title='{tb['title']}'" if tb['title'] else ""
            print(f"  ({tb['x']},{tb['y']}) {tb['w']}x{tb['h']} <{tb['tag']}> '{tb['text']}' cls={tb['cls'][:30]}{title}")

        # ============================================================
        # STEP 18: Check Layer Action Bar for AI Expand
        # ============================================================
        print(f"\n{'='*60}")
        print("STEP 18: Layer Action Bar Items")
        print(f"{'='*60}")

        action_bar = page.evaluate("""() => {
            var items = [];
            for (var el of document.querySelectorAll('.action-bar *, [class*="action-bar"] *, [class*="layer-action"] *')) {
                var r = el.getBoundingClientRect();
                var text = (el.innerText || '').trim();
                var title = el.getAttribute('title') || '';
                if (r.width > 0 && r.height > 0 && (text.length > 0 || title.length > 0) && el.childElementCount === 0) {
                    items.push({
                        text: text.substring(0, 40),
                        title: title.substring(0, 40),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        cls: (el.className || '').substring(0, 50)
                    });
                }
            }
            return items.slice(0, 20);
        }""")
        print(f"[18] Action bar items: {len(action_bar)}")
        for ab in action_bar:
            title = f" title='{ab['title']}'" if ab['title'] else ""
            print(f"  ({ab['x']},{ab['y']}) {ab['w']}x{ab['h']} '{ab['text']}' cls={ab['cls'][:30]}{title}")

        # ============================================================
        # STEP 19: Navigate back to Image Editor overview
        # ============================================================
        print(f"\n{'='*60}")
        print("STEP 19: Navigate Back (Back Arrow)")
        print(f"{'='*60}")

        # Click back arrow to return to Image Editor overview
        went_back = page.evaluate("""() => {
            var panel = document.querySelector('.c-gen-config.show');
            if (!panel) return false;
            var back = panel.querySelector('.ico-back, [class*="back"]');
            if (back) {
                back.click();
                return true;
            }
            // Try header area back click
            var header = panel.querySelector('.gen-config-header');
            if (header) {
                var arrow = header.querySelector('svg, [class*="arrow"], [class*="back"]');
                if (arrow) { arrow.click(); return true; }
            }
            return false;
        }""")
        print(f"[19] Went back: {went_back}")
        page.wait_for_timeout(1000)

        # Check what panel is showing now
        current_panel = page.evaluate("""() => {
            var panel = document.querySelector('.panels.show') || document.querySelector('.c-gen-config.show');
            if (!panel) return null;
            return {
                cls: (panel.className || '').substring(0, 80),
                text: (panel.innerText || '').substring(0, 500)
            };
        }""")
        print(f"[19b] Current panel after back:")
        if current_panel:
            print(f"  Class: {current_panel['cls']}")
            print(f"  Content: {current_panel['text'][:300]}")

        shot(page, "09_back_to_image_editor")

        # ============================================================
        # SUMMARY
        # ============================================================
        print("\n" + "=" * 70)
        print("PHASE 154 SUMMARY — AI Expand (Outpainting)")
        print("=" * 70)

        summary = {
            "access_path": "Sidebar > Image Editor (40, 698) > Expand collapse-option (92, 401)",
            "panel_class": "c-gen-config show",
            "header": "Generative Expand",
            "aspect_ratios": [r['text'] for r in ratios] if ratios else ["1:1", "4:3", "3:2", "16:9", "2:1", "3:4", "2:3", "9:16", "1:2"],
            "prompt": {
                "type": prompt_info.get('type') if prompt_info else "textarea",
                "max_chars": 1800,
                "optional": True,
                "placeholder": prompt_info.get('placeholder', '') if prompt_info else ""
            },
            "generate_button": {
                "text": gen_state.get('text') if gen_state else "Generate 8",
                "credits": 8,
                "produces": "4 variants",
                "position": f"({gen_state['x']},{gen_state['y']})" if gen_state and gen_state.get('found') else "(~212, 397)",
                "selector": ".generative or button containing 'Generate'",
                "requires": "selected image layer on canvas"
            },
            "canvas_interaction": "Drag handles on 4 edges to define expansion area",
            "result_url_pattern": "https://static.dzine.ai/stylar_product/p/{project_id}/outpaint/{n}_output_{timestamp}.webp",
            "timing": "~75s for 4 variants",
            "screenshots": str(SCREENSHOT_DIR)
        }

        print(json.dumps(summary, indent=2))
        print(f"\nScreenshots saved to: {SCREENSHOT_DIR}")

        # Save summary JSON
        summary_path = SCREENSHOT_DIR / "summary.json"
        with open(summary_path, "w") as f:
            json.dump(summary, f, indent=2)
        print(f"Summary saved to: {summary_path}")

    finally:
        try:
            pw.stop()
        except Exception:
            pass


if __name__ == "__main__":
    main()
