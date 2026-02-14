#!/usr/bin/env python3
"""Phase 156c: Hand Repair — Immersive Mode Full Documentation.

Previous phases confirmed:
- Hand Repair activates an IMMERSIVE full-screen mode (replaces normal canvas)
- Top bar: "Hand Repair" + "Exit" button
- Tool bar: Lasso | Brush (dropdown) | Auto | Union (dropdown) | Invert | Clear all
- Instruction: "Draw a circle around the area you want to select"
- Generate button: 4 credits, at bottom after marking area
- A "New Feature" popup appears that must be dismissed

This phase:
1. Dismiss the popup
2. Map all immersive-mode UI elements precisely
3. Test Lasso tool - draw a selection around hands
4. Check the Repair Area preview and Generate button
5. Test Auto selection mode
6. Document Brush settings (dropdown)
7. Document Union dropdown options
8. Capture the full immersive-mode selectors for automation
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

SCREENSHOT_DIR = Path("/tmp/dzine_explore_156")


def main():
    from playwright.sync_api import sync_playwright
    from tools.lib.brave_profile import DEFAULT_CDP_PORT, is_browser_running
    from tools.lib.dzine_browser import close_all_dialogs, VIEWPORT, CANVAS_URL

    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("PHASE 156c: Hand Repair — Immersive Mode Full Documentation")
    print("=" * 70)

    if not is_browser_running():
        print("[P156c] ERROR: Brave not running.")
        return

    pw = sync_playwright().start()
    try:
        browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{DEFAULT_CDP_PORT}")
        context = browser.contexts[0]

        dzine_pages = [p for p in context.pages if "dzine.ai/canvas" in (p.url or "")]
        if not dzine_pages:
            page = context.new_page()
            page.goto(CANVAS_URL, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(3000)
        else:
            page = dzine_pages[0]

        page.set_viewport_size(VIEWPORT)
        page.bring_to_front()
        page.wait_for_timeout(1500)

        # ==============================================================
        # STEP 0: Check if we're already in Hand Repair immersive mode
        # ==============================================================
        in_immersive = page.evaluate("""() => {
            // Check for "Hand Repair" text and "Exit" button in top bar
            for (var el of document.querySelectorAll('*')) {
                var t = (el.innerText || '').trim();
                if (t === 'Hand Repair' && el.getBoundingClientRect().y < 40) return true;
            }
            return false;
        }""")
        print(f"[0] Already in immersive mode: {in_immersive}")

        if not in_immersive:
            # Need to activate Hand Repair
            print("[0] Activating Hand Repair...")
            close_all_dialogs(page)
            page.wait_for_timeout(300)
            page.keyboard.press("Escape")
            page.wait_for_timeout(300)

            # Make sure we have a layer and select it
            page.mouse.click(720, 450)
            page.wait_for_timeout(500)

            # Click Hand Repair
            page.evaluate("""() => {
                var btn = document.getElementById('hand-repair') ||
                         document.querySelector('button.item.hand-repair');
                if (btn) btn.click();
            }""")
            page.wait_for_timeout(2000)

        # ==============================================================
        # STEP 1: Dismiss the "New Feature" popup
        # ==============================================================
        print(f"\n{'='*60}")
        print("STEP 1: Dismiss popup")
        print(f"{'='*60}")

        dismissed = page.evaluate("""() => {
            // Look for "Skip" button in the New Feature popup
            for (var btn of document.querySelectorAll('button, a, span, div')) {
                var t = (btn.innerText || '').trim();
                if (t === 'Skip' || t === 'Not now' || t === 'Close') {
                    var r = btn.getBoundingClientRect();
                    if (r.width > 0 && r.y > 100) {
                        btn.click();
                        return {clicked: t, x: Math.round(r.x), y: Math.round(r.y)};
                    }
                }
            }
            // Try clicking X close button
            for (var btn of document.querySelectorAll('.close, .ico-close, [class*="close"]')) {
                var r = btn.getBoundingClientRect();
                if (r.width > 0 && r.height > 0) {
                    btn.click();
                    return {clicked: 'close-icon', x: Math.round(r.x), y: Math.round(r.y)};
                }
            }
            return null;
        }""")
        print(f"[1] Dismissed: {dismissed}")
        page.wait_for_timeout(500)

        # Also dismiss the instruction toast
        page.evaluate("""() => {
            // Close "Draw a circle..." instruction with X
            for (var el of document.querySelectorAll('.close-btn, .ico-close, [class*="dismiss"]')) {
                var r = el.getBoundingClientRect();
                if (r.width > 0 && r.y > 100 && r.y < 200) {
                    el.click();
                    return true;
                }
            }
            // Also try clicking the X at the end of the instruction bar
            for (var el of document.querySelectorAll('*')) {
                var t = (el.innerText || '').trim();
                if (t === '\u00D7' || t === 'X' || t === '\u2715') {
                    var r = el.getBoundingClientRect();
                    if (r.y > 100 && r.y < 200 && r.width < 30) {
                        el.click();
                        return true;
                    }
                }
            }
            return false;
        }""")
        page.wait_for_timeout(500)

        page.screenshot(path=str(SCREENSHOT_DIR / "c01_immersive_clean.png"))

        # ==============================================================
        # STEP 2: Map the immersive mode top bar
        # ==============================================================
        print(f"\n{'='*60}")
        print("STEP 2: Top Bar Elements")
        print(f"{'='*60}")

        topbar = page.evaluate("""() => {
            var items = [];
            for (var el of document.querySelectorAll('*')) {
                var r = el.getBoundingClientRect();
                var s = window.getComputedStyle(el);
                if (r.width > 0 && r.height > 0 && r.y < 50 && r.x > 0 && r.x < 1440 &&
                    s.display !== 'none' && el.childElementCount === 0) {
                    var text = (el.innerText || '').trim();
                    if (text.length > 0 || s.cursor === 'pointer' || el.tagName === 'BUTTON') {
                        items.push({
                            text: text.substring(0, 40) || '[' + el.tagName + ']',
                            tag: el.tagName,
                            x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height),
                            cls: (el.className || '').substring(0, 50),
                            id: el.id || '',
                            cursor: s.cursor
                        });
                    }
                }
            }
            items.sort((a, b) => a.x - b.x);
            return items;
        }""")
        print(f"[2] Top bar items: {len(topbar)}")
        for t in topbar:
            clickable = " [click]" if t['cursor'] == 'pointer' else ""
            print(f"  ({t['x']},{t['y']}) {t['w']}x{t['h']} <{t['tag']}> '{t['text']}' id={t['id']} cls={t['cls'][:30]}{clickable}")

        # ==============================================================
        # STEP 3: Map the selection tools bar
        # ==============================================================
        print(f"\n{'='*60}")
        print("STEP 3: Selection Tools Bar")
        print(f"{'='*60}")

        tools_bar = page.evaluate("""() => {
            var items = [];
            // Selection tools are between y=60-120
            for (var el of document.querySelectorAll('button, [role="button"]')) {
                var r = el.getBoundingClientRect();
                var s = window.getComputedStyle(el);
                if (r.width > 0 && r.y >= 55 && r.y < 120 && s.display !== 'none') {
                    var text = (el.innerText || '').trim();
                    items.push({
                        text: text.substring(0, 40),
                        tag: el.tagName,
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        cls: (el.className || '').substring(0, 60),
                        id: el.id || '',
                        active: el.className.includes('active') || el.className.includes('selected'),
                        hasDropdown: el.querySelector('.arrow, .dropdown, .chevron, [class*="arrow"]') !== null ||
                                    el.querySelector('svg') !== null && el.innerText.includes('v')
                    });
                }
            }
            items.sort((a, b) => a.x - b.x);
            return items;
        }""")
        print(f"[3] Selection tools: {len(tools_bar)}")
        for t in tools_bar:
            active = " [ACTIVE]" if t['active'] else ""
            dropdown = " [v]" if t['hasDropdown'] else ""
            print(f"  ({t['x']},{t['y']}) {t['w']}x{t['h']} '{t['text']}' cls={t['cls'][:40]}{active}{dropdown}")

        # Also check for all text labels in the tools area
        tools_text = page.evaluate("""() => {
            var items = [];
            var seen = new Set();
            for (var el of document.querySelectorAll('*')) {
                var r = el.getBoundingClientRect();
                var s = window.getComputedStyle(el);
                if (r.width > 0 && r.y >= 55 && r.y < 130 && r.x > 350 && r.x < 1050 &&
                    s.display !== 'none' && el.childElementCount === 0) {
                    var text = (el.innerText || '').trim();
                    if (text.length > 0 && !seen.has(text)) {
                        seen.add(text);
                        items.push({
                            text: text, x: Math.round(r.x), y: Math.round(r.y),
                            tag: el.tagName, cls: (el.className || '').substring(0, 40)
                        });
                    }
                }
            }
            items.sort((a, b) => a.x - b.x);
            return items;
        }""")
        print(f"\n[3b] Tool labels:")
        for t in tools_text:
            print(f"  ({t['x']},{t['y']}) '{t['text']}' <{t['tag']}> cls={t['cls'][:30]}")

        # ==============================================================
        # STEP 4: Check Brush dropdown options
        # ==============================================================
        print(f"\n{'='*60}")
        print("STEP 4: Brush Tool Dropdown")
        print(f"{'='*60}")

        # Click the Brush button dropdown arrow
        brush_click = page.evaluate("""() => {
            for (var btn of document.querySelectorAll('button')) {
                var t = (btn.innerText || '').trim();
                var r = btn.getBoundingClientRect();
                if (t.includes('Brush') && r.y > 55 && r.y < 120) {
                    btn.click();
                    return {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width)};
                }
            }
            return null;
        }""")
        print(f"[4] Brush click: {brush_click}")
        page.wait_for_timeout(1000)

        page.screenshot(path=str(SCREENSHOT_DIR / "c02_brush_dropdown.png"))

        # Check for dropdown/popover
        brush_options = page.evaluate("""() => {
            var items = [];
            // Look for dropdown/popover that appeared
            for (var el of document.querySelectorAll('[class*="popover"], [class*="dropdown"], [class*="picker"], [class*="tooltip"], [class*="menu"]')) {
                var r = el.getBoundingClientRect();
                var s = window.getComputedStyle(el);
                if (r.width > 50 && r.height > 50 && s.display !== 'none' && parseFloat(s.opacity) > 0.3) {
                    items.push({
                        text: (el.innerText || '').trim().substring(0, 300),
                        cls: (el.className || '').substring(0, 60),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height)
                    });
                }
            }
            return items;
        }""")
        print(f"[4b] Brush dropdown panels: {len(brush_options)}")
        for b in brush_options:
            print(f"  ({b['x']},{b['y']}) {b['w']}x{b['h']} cls={b['cls'][:40]}")
            print(f"    Text: {b['text'][:200]}")

        # Check for sliders (brush size)
        sliders = page.evaluate("""() => {
            var items = [];
            for (var el of document.querySelectorAll('input[type="range"], [class*="slider"], [role="slider"]')) {
                var r = el.getBoundingClientRect();
                if (r.width > 0 && r.y > 80 && r.y < 300) {
                    items.push({
                        tag: el.tagName, type: el.type || '',
                        value: el.value || '',
                        min: el.min || '', max: el.max || '',
                        cls: (el.className || '').substring(0, 40),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width)
                    });
                }
            }
            return items;
        }""")
        print(f"\n[4c] Sliders: {len(sliders)}")
        for s in sliders:
            print(f"  ({s['x']},{s['y']}) w={s['w']} val={s['value']} range=[{s['min']},{s['max']}] cls={s['cls']}")

        # Click away to close dropdown
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)

        # ==============================================================
        # STEP 5: Check Union/Selection Mode dropdown
        # ==============================================================
        print(f"\n{'='*60}")
        print("STEP 5: Union/Selection Mode Dropdown")
        print(f"{'='*60}")

        # Click the Union dropdown
        union_click = page.evaluate("""() => {
            for (var el of document.querySelectorAll('*')) {
                var t = (el.innerText || '').trim();
                var r = el.getBoundingClientRect();
                if ((t === 'Union' || t === 'Select') && r.y > 55 && r.y < 120 && r.width > 30) {
                    el.click();
                    return {text: t, x: Math.round(r.x), y: Math.round(r.y)};
                }
            }
            return null;
        }""")
        print(f"[5] Union click: {union_click}")
        page.wait_for_timeout(1000)

        page.screenshot(path=str(SCREENSHOT_DIR / "c03_union_dropdown.png"))

        # Check for selection mode options
        union_options = page.evaluate("""() => {
            var items = [];
            // Look for dropdown items
            for (var el of document.querySelectorAll('[class*="selection-item"], [class*="option"], li')) {
                var r = el.getBoundingClientRect();
                var text = (el.innerText || '').trim();
                if (r.width > 0 && r.y > 55 && r.y < 200 && text.length > 0 && text.length < 30) {
                    items.push({
                        text: text,
                        x: Math.round(r.x), y: Math.round(r.y),
                        cls: (el.className || '').substring(0, 60),
                        active: el.className.includes('selected') || el.className.includes('active')
                    });
                }
            }
            return items;
        }""")
        print(f"[5b] Selection mode options: {len(union_options)}")
        for o in union_options:
            active = " [ACTIVE]" if o['active'] else ""
            print(f"  ({o['x']},{o['y']}) '{o['text']}' cls={o['cls'][:30]}{active}")

        page.keyboard.press("Escape")
        page.wait_for_timeout(300)

        # ==============================================================
        # STEP 6: Test the Auto selection tool
        # ==============================================================
        print(f"\n{'='*60}")
        print("STEP 6: Auto Selection Tool")
        print(f"{'='*60}")

        # Click Auto button
        auto_click = page.evaluate("""() => {
            for (var btn of document.querySelectorAll('button')) {
                var t = (btn.innerText || '').trim();
                var r = btn.getBoundingClientRect();
                if (t === 'Auto' && r.y > 55 && r.y < 120) {
                    btn.click();
                    return {x: Math.round(r.x), y: Math.round(r.y), cls: btn.className};
                }
            }
            return null;
        }""")
        print(f"[6] Auto click: {auto_click}")
        page.wait_for_timeout(500)

        page.screenshot(path=str(SCREENSHOT_DIR / "c04_auto_mode.png"))

        # Check for instruction change
        instruction = page.evaluate("""() => {
            for (var el of document.querySelectorAll('.select-tips, [class*="tips"], [class*="instruction"]')) {
                var r = el.getBoundingClientRect();
                var text = (el.innerText || '').trim();
                if (r.width > 0 && text.length > 5 && r.y > 100 && r.y < 200) {
                    return {text: text, x: Math.round(r.x), y: Math.round(r.y)};
                }
            }
            return null;
        }""")
        print(f"[6b] Instruction: {instruction}")

        # ==============================================================
        # STEP 7: Test Lasso — draw a selection circle
        # ==============================================================
        print(f"\n{'='*60}")
        print("STEP 7: Lasso Tool — Draw Selection")
        print(f"{'='*60}")

        # Switch back to Lasso
        page.evaluate("""() => {
            for (var btn of document.querySelectorAll('button')) {
                var t = (btn.innerText || '').trim();
                var r = btn.getBoundingClientRect();
                if (t === 'Lasso' && r.y > 55 && r.y < 120) {
                    btn.click();
                    return true;
                }
            }
            return false;
        }""")
        page.wait_for_timeout(500)

        # Find the image on canvas to know where hands might be
        # The image should be centered in the canvas area
        canvas_img = page.evaluate("""() => {
            // Find the canvas area
            var canvas = document.querySelector('#canvas, .c-canvas-container canvas, [class*="canvas"]');
            if (canvas) {
                var r = canvas.getBoundingClientRect();
                return {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)};
            }
            return null;
        }""")
        print(f"[7] Canvas area: {canvas_img}")

        # Draw a lasso selection around the center area (where hands would typically be)
        # Use a rough circular path
        center_x = 690
        center_y = 400
        radius = 60

        print(f"[7b] Drawing lasso at ({center_x},{center_y}) radius={radius}...")
        import math
        # Start the lasso path
        page.mouse.move(center_x + radius, center_y)
        page.mouse.down()
        # Draw a rough circle
        for angle in range(0, 370, 15):
            rad = math.radians(angle)
            x = center_x + int(radius * math.cos(rad))
            y = center_y + int(radius * math.sin(rad))
            page.mouse.move(x, y)
            page.wait_for_timeout(20)
        page.mouse.up()
        page.wait_for_timeout(1500)

        page.screenshot(path=str(SCREENSHOT_DIR / "c05_lasso_selection.png"))

        # ==============================================================
        # STEP 8: Check the Repair Area preview after selection
        # ==============================================================
        print(f"\n{'='*60}")
        print("STEP 8: Repair Area Preview After Selection")
        print(f"{'='*60}")

        repair_area = page.evaluate("""() => {
            var preview = document.querySelector('.preview-content.handRepair');
            if (preview) {
                var r = preview.getBoundingClientRect();
                var s = window.getComputedStyle(preview);
                var text = (preview.innerText || '').trim();
                var imgs = preview.querySelectorAll('img');
                var imgSrcs = [];
                for (var img of imgs) {
                    if (img.src && img.getBoundingClientRect().width > 0) imgSrcs.push(img.src.substring(0, 80));
                }
                return {
                    text: text.substring(0, 200),
                    display: s.display,
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    images: imgSrcs
                };
            }
            return null;
        }""")
        print(f"[8] Repair Area: {json.dumps(repair_area, indent=2)}")

        # Check the Generate button state
        gen_btn = page.evaluate("""() => {
            var btn = document.getElementById('hand-repair-generate-btn');
            if (!btn) {
                for (var b of document.querySelectorAll('button')) {
                    if ((b.innerText || '').trim().includes('Generate') && b.getBoundingClientRect().y > 700) {
                        btn = b;
                        break;
                    }
                }
            }
            if (btn) {
                var r = btn.getBoundingClientRect();
                return {
                    text: (btn.innerText || '').trim(),
                    id: btn.id || '',
                    cls: btn.className.substring(0, 60),
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    disabled: btn.disabled || btn.className.includes('disabled')
                };
            }
            return null;
        }""")
        print(f"[8b] Generate button: {json.dumps(gen_btn, indent=2)}")

        # Check the warning text
        warning = page.evaluate("""() => {
            var w = document.querySelector('.warning-tips .warning-text, [class*="warning-text"]');
            if (w) {
                var r = w.getBoundingClientRect();
                return {text: (w.innerText || '').trim(), x: Math.round(r.x), y: Math.round(r.y)};
            }
            return null;
        }""")
        print(f"[8c] Warning: {warning}")

        # ==============================================================
        # STEP 9: Check all visible buttons/interactive elements
        # ==============================================================
        print(f"\n{'='*60}")
        print("STEP 9: All Visible Interactive Elements in Immersive Mode")
        print(f"{'='*60}")

        all_visible = page.evaluate("""() => {
            var items = [];
            for (var el of document.querySelectorAll('button, input, select')) {
                var r = el.getBoundingClientRect();
                var s = window.getComputedStyle(el);
                if (r.width > 0 && r.height > 0 && s.display !== 'none' && r.y >= 0 && r.y < 950) {
                    var text = (el.innerText || el.value || '').trim();
                    items.push({
                        text: text.substring(0, 50),
                        tag: el.tagName, type: el.type || '',
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        cls: (el.className || '').substring(0, 50),
                        id: el.id || '',
                        disabled: el.disabled || false
                    });
                }
            }
            items.sort((a, b) => a.y - b.y || a.x - b.x);
            return items;
        }""")
        print(f"[9] Visible interactive elements: {len(all_visible)}")
        for e in all_visible:
            disabled = " [disabled]" if e['disabled'] else ""
            print(f"  ({e['x']},{e['y']}) {e['w']}x{e['h']} <{e['tag']} type={e['type']}> '{e['text']}' id={e['id']} cls={e['cls'][:30]}{disabled}")

        # ==============================================================
        # STEP 10: Check what the Exit button does
        # ==============================================================
        print(f"\n{'='*60}")
        print("STEP 10: Exit button location")
        print(f"{'='*60}")

        exit_btn = page.evaluate("""() => {
            for (var btn of document.querySelectorAll('button, a')) {
                var t = (btn.innerText || '').trim();
                var r = btn.getBoundingClientRect();
                if (t === 'Exit' && r.y < 50) {
                    return {
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        tag: btn.tagName,
                        cls: (btn.className || '').substring(0, 50),
                        id: btn.id || ''
                    };
                }
            }
            return null;
        }""")
        print(f"[10] Exit button: {exit_btn}")

        # ==============================================================
        # STEP 11: Check bottom area (generate panel)
        # ==============================================================
        print(f"\n{'='*60}")
        print("STEP 11: Bottom Generate Panel")
        print(f"{'='*60}")

        bottom_area = page.evaluate("""() => {
            var items = [];
            for (var el of document.querySelectorAll('*')) {
                var r = el.getBoundingClientRect();
                var s = window.getComputedStyle(el);
                if (r.width > 50 && r.y > 700 && r.y < 950 && s.display !== 'none' && el.childElementCount === 0) {
                    var text = (el.innerText || '').trim();
                    if (text.length > 0) {
                        items.push({
                            text: text.substring(0, 60),
                            tag: el.tagName,
                            x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height),
                            cls: (el.className || '').substring(0, 50)
                        });
                    }
                }
            }
            items.sort((a, b) => a.y - b.y || a.x - b.x);
            return items;
        }""")
        print(f"[11] Bottom area elements: {len(bottom_area)}")
        for e in bottom_area:
            print(f"  ({e['x']},{e['y']}) {e['w']}x{e['h']} <{e['tag']}> '{e['text']}' cls={e['cls'][:30]}")

        # ==============================================================
        # STEP 12: Try Auto mode - click on the image
        # ==============================================================
        print(f"\n{'='*60}")
        print("STEP 12: Try Auto Selection Mode")
        print(f"{'='*60}")

        # Clear the current selection first
        page.evaluate("""() => {
            for (var btn of document.querySelectorAll('button')) {
                if ((btn.innerText || '').trim() === 'Clear all') { btn.click(); return true; }
            }
            return false;
        }""")
        page.wait_for_timeout(500)

        # Click Auto
        page.evaluate("""() => {
            for (var btn of document.querySelectorAll('button')) {
                var t = (btn.innerText || '').trim();
                var r = btn.getBoundingClientRect();
                if (t === 'Auto' && r.y > 55 && r.y < 120) { btn.click(); return true; }
            }
            return false;
        }""")
        page.wait_for_timeout(500)

        # Click on the image where a hand would be
        page.mouse.click(690, 400)
        page.wait_for_timeout(2000)

        page.screenshot(path=str(SCREENSHOT_DIR / "c06_auto_selection.png"))

        # Check if auto detected anything
        auto_result = page.evaluate("""() => {
            var preview = document.querySelector('.preview-content.handRepair');
            if (preview) {
                var text = (preview.innerText || '').trim();
                var hasImage = preview.querySelector('img') !== null;
                var canvas = preview.querySelector('canvas');
                var hasCanvas = canvas !== null && canvas.getBoundingClientRect().width > 0;
                return {text: text.substring(0, 100), hasImage: hasImage, hasCanvas: hasCanvas};
            }
            return null;
        }""")
        print(f"[12] Auto result: {auto_result}")

        # ==============================================================
        # STEP 13: Final comprehensive selector documentation
        # ==============================================================
        print(f"\n{'='*60}")
        print("STEP 13: COMPREHENSIVE SELECTOR DOCUMENTATION")
        print(f"{'='*60}")

        # Extract everything in one big call
        full_doc = page.evaluate("""() => {
            var doc = {};

            // Immersive mode detection
            doc.immersive_marker = null;
            for (var el of document.querySelectorAll('*')) {
                var t = (el.innerText || '').trim();
                var r = el.getBoundingClientRect();
                if (t === 'Hand Repair' && r.y < 40 && r.width > 0 && el.childElementCount === 0) {
                    doc.immersive_marker = {
                        tag: el.tagName, cls: (el.className || '').substring(0, 40),
                        x: Math.round(r.x), y: Math.round(r.y)
                    };
                    break;
                }
            }

            // Exit button
            for (var btn of document.querySelectorAll('button')) {
                var t = (btn.innerText || '').trim();
                var r = btn.getBoundingClientRect();
                if (t === 'Exit' && r.y < 50 && r.width > 0) {
                    doc.exit_btn = {cls: (btn.className || '').substring(0, 40), x: Math.round(r.x), y: Math.round(r.y)};
                    break;
                }
            }

            // Selection tools
            doc.tools = [];
            for (var btn of document.querySelectorAll('.minor-gen-selection-tools button, .text-btns button')) {
                var t = (btn.innerText || '').trim();
                var r = btn.getBoundingClientRect();
                if (r.width > 0 && r.y > 55 && r.y < 120) {
                    doc.tools.push({
                        name: t,
                        cls: (btn.className || '').substring(0, 50),
                        active: btn.className.includes('active'),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width)
                    });
                }
            }

            // Selection mode (Union/Select/Unselect)
            doc.selection_modes = [];
            for (var li of document.querySelectorAll('.selection-types li')) {
                var t = (li.innerText || '').trim();
                doc.selection_modes.push({
                    name: t,
                    cls: (li.className || '').substring(0, 50),
                    selected: li.className.includes('selected')
                });
            }

            // Invert and Clear all
            doc.invert_btn = null;
            doc.clear_btn = null;
            for (var btn of document.querySelectorAll('.option-btns button')) {
                var t = (btn.innerText || '').trim().toLowerCase();
                var r = btn.getBoundingClientRect();
                if (t.includes('invert') && r.width > 0) {
                    doc.invert_btn = {cls: (btn.className || '').substring(0, 40), x: Math.round(r.x), y: Math.round(r.y)};
                }
                if (t.includes('clear') && r.width > 0) {
                    doc.clear_btn = {cls: (btn.className || '').substring(0, 40), x: Math.round(r.x), y: Math.round(r.y)};
                }
            }

            // Generate button
            var genBtn = document.getElementById('hand-repair-generate-btn');
            if (genBtn) {
                var r = genBtn.getBoundingClientRect();
                var creditSpan = genBtn.querySelector('.consume-tip span:last-child');
                doc.generate = {
                    id: 'hand-repair-generate-btn',
                    cls: (genBtn.className || '').substring(0, 50),
                    credits: creditSpan ? creditSpan.innerText.trim() : '',
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    disabled: genBtn.disabled || genBtn.className.includes('disabled')
                };
            }

            // Preview area
            var preview = document.querySelector('.preview-content.handRepair');
            if (preview) {
                var r = preview.getBoundingClientRect();
                doc.preview = {
                    cls: 'preview-content handRepair',
                    text: (preview.innerText || '').trim().substring(0, 200),
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height)
                };
            }

            // Panel structure
            doc.panel_id = 'hand-repair-generate-btn-panel';
            doc.form_id = 'hand-repair-generate-btn-form';

            return doc;
        }""")

        print(json.dumps(full_doc, indent=2))

        # ==============================================================
        # STEP 14: Exit immersive mode
        # ==============================================================
        print(f"\n{'='*60}")
        print("STEP 14: Exit Hand Repair Mode")
        print(f"{'='*60}")

        page.evaluate("""() => {
            for (var btn of document.querySelectorAll('button, a')) {
                var t = (btn.innerText || '').trim();
                if (t === 'Exit' && btn.getBoundingClientRect().y < 50) {
                    btn.click();
                    return true;
                }
            }
            return false;
        }""")
        page.wait_for_timeout(1500)

        page.screenshot(path=str(SCREENSHOT_DIR / "c07_after_exit.png"))

        # ==============================================================
        # SUMMARY
        # ==============================================================
        print(f"\n{'='*70}")
        print("PHASE 156c — COMPLETE HAND REPAIR DOCUMENTATION")
        print(f"{'='*70}")

        print("""
HAND REPAIR TOOL — FULL DOCUMENTATION
======================================

1. ACTIVATION
   - Top toolbar button: id="hand-repair", cls="item hand-repair"
   - Position: (521, 82) at 1440x900 viewport
   - Requires: A layer must be selected on canvas
   - Also accessible via: Image Editor sidebar > collapse-option "Hand Repair"

2. UI MODE
   - Enters IMMERSIVE full-screen mode (replaces normal canvas UI)
   - Top bar shows: "Hand Repair" label + "Exit" button
   - No sidebar panels — tools are overlaid on the canvas
   - Must exit via "Exit" button to return to normal canvas

3. SELECTION TOOLS (top toolbar in immersive mode)
   a. Lasso (default, cls="item lasso active")
      - Draw freehand selection around the hand area
      - Instruction: "Draw a circle around the area you want to select"
   b. Brush (has dropdown for size, cls="item brush")
      - Paint over the area to select it
      - Dropdown shows brush size slider
   c. Auto (cls="item auto")
      - Click on the image to auto-detect selection areas
      - Instruction: "Click the area you want to select"

4. SELECTION MODES (Union dropdown)
   - Select (default) — add to selection
   - Unselect — remove from selection
   - Available in: .selection-types li elements

5. SELECTION ACTIONS
   - Invert: Inverts the selection (cls="invert")
   - Clear all: Removes all selection (cls="clear")

6. REPAIR AREA PREVIEW
   - cls="preview-content handRepair"
   - Shows preview of the selected area
   - Text: "Repair Area" header
   - When no selection: "No area has been selected"

7. GENERATE
   - Button: id="hand-repair-generate-btn"
   - Cost: 4 credits per repair
   - Panel: id="hand-repair-generate-btn-panel"
   - Form: id="hand-repair-generate-btn-form"
   - Warning: "Please mark the editing area." (when no selection)
   - cls="generative ready" when ready

8. EXIT
   - "Exit" button in top bar returns to normal canvas mode

9. KEY SELECTORS FOR AUTOMATION
   Activation:
     button#hand-repair (top toolbar)
     button.collapse-option:has-text("Hand Repair") (Image Editor)

   Immersive mode detection:
     Text "Hand Repair" in top bar (y < 40)

   Tools:
     button.item.lasso (in .minor-gen-selection-tools)
     button.item.brush
     button.item.auto

   Selection modes:
     li.selection-item (in .selection-types)
     - "Select" / "Unselect"

   Actions:
     button.invert
     button.clear (.clear-all icon)

   Generate:
     button#hand-repair-generate-btn

   Preview:
     .preview-content.handRepair
     .preview-image (shows selected area or "No area has been selected")

   Exit:
     button:has-text("Exit") in top bar

10. CREDITS
    - 4 credits per hand repair generation
    - Icon shows credit cost next to Generate button
""")

        print(f"\nScreenshots saved to: {SCREENSHOT_DIR}/")
        for f in sorted(SCREENSHOT_DIR.glob("c*.png")):
            print(f"  {f.name}")

    except Exception as e:
        import traceback
        print(f"\n[P156c] ERROR: {e}")
        traceback.print_exc()
    finally:
        try:
            pw.stop()
        except Exception:
            pass


if __name__ == "__main__":
    main()
