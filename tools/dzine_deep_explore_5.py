#!/usr/bin/env python3
"""Dzine Deep Exploration Part 5 — Final targeted gaps.

1. Video model selector: try clicking the arrow/chevron icon directly
2. Camera section: click the camera-movement-btn div
3. Txt2Img Advanced: close Image Editor first, then open Txt2Img
4. Product Background: scroll down in Image Editor to find it
"""

from __future__ import annotations
import json, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from playwright.sync_api import sync_playwright

CANVAS_URL = "https://www.dzine.ai/canvas?id=19861203"
CDP_PORT = 18800
DL = Path.home() / "Downloads"
SX = 40

def connect():
    pw = sync_playwright().start()
    browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{CDP_PORT}")
    ctx = browser.contexts[0] if browser.contexts else browser.new_context()
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.set_viewport_size({"width": 1440, "height": 900})
    return pw, browser, page

def close_dialogs(page):
    for _ in range(5):
        f = False
        for t in ["Not now", "Close", "Never show again", "Got it", "Skip", "Later"]:
            try:
                b = page.locator(f'button:has-text("{t}")')
                if b.count() > 0 and b.first.is_visible(timeout=300):
                    b.first.click(timeout=1000); f = True; page.wait_for_timeout(200)
            except: pass
        if not f: break

def ss(page, name):
    p = DL / f"{name}.png"; page.screenshot(path=str(p)); print(f"  [SS] {p}")

def ensure_canvas(page):
    if "canvas" not in (page.url or ""):
        page.goto(CANVAS_URL); page.wait_for_timeout(4000); close_dialogs(page)

def panel_text(page):
    return page.evaluate("""() => {
        var p = document.querySelector('.c-gen-config.show');
        return p ? p.innerText : 'NO PANEL';
    }""")


def main():
    print("="*70)
    print("DZINE DEEP EXPLORATION PART 5 — Final Gaps")
    print("="*70)
    pw, browser, page = connect()
    print(f"Connected. URL: {page.url}")

    ensure_canvas(page)

    # ============================================================
    # 1. CLOSE ANY OPEN PANELS AND START FRESH
    # ============================================================
    print("\n[1] Closing all panels, starting fresh...")
    # Click the X button on any open panel
    page.evaluate("""() => {
        var close = document.querySelector('.c-gen-config.show .ico-close') ||
                    document.querySelector('.c-gen-config.show .close');
        if (close) close.click();
    }""")
    page.wait_for_timeout(1000)

    # ============================================================
    # 2. TXT2IMG ADVANCED
    # ============================================================
    print("\n" + "="*70)
    print("SECTION 1: Txt2Img Advanced Settings")
    print("="*70)

    # Open Txt2Img by clicking sidebar
    page.mouse.click(SX, 252)  # First click Img2Img
    page.wait_for_timeout(800)
    page.mouse.click(SX, 197)  # Then Txt2Img
    page.wait_for_timeout(2000)
    close_dialogs(page)

    pt = panel_text(page)
    print(f"  Panel: {pt[:80]}")

    if "Text to Image" not in pt and "Txt2Img" not in pt:
        print("  Not in Txt2Img! Trying harder...")
        page.mouse.click(SX, 361)  # Click AI Video to force switch
        page.wait_for_timeout(800)
        page.mouse.click(SX, 197)  # Back to Txt2Img
        page.wait_for_timeout(2000)
        close_dialogs(page)
        pt = panel_text(page)
        print(f"  Retry: {pt[:80]}")

    # Print full panel
    print("\n  Full Txt2Img panel:")
    for line in pt.split('\n'):
        if line.strip(): print(f"    {line.strip()}")

    if "Text to Image" in pt:
        # Expand Advanced
        print("\n  Expanding Advanced...")
        page.evaluate("""() => {
            var p = document.querySelector('.c-gen-config.show');
            if (!p) return;
            var btn = p.querySelector('.advanced-btn');
            if (btn) btn.click();
        }""")
        page.wait_for_timeout(1500)

        # Scroll to bottom
        page.evaluate("() => { var p = document.querySelector('.c-gen-config.show'); if (p) p.scrollTop = p.scrollHeight; }")
        page.wait_for_timeout(500)
        ss(page, "p171_txt2img_advanced_expanded")

        adv_text = panel_text(page)
        print("\n  With Advanced expanded:")
        for line in adv_text.split('\n'):
            if line.strip(): print(f"    {line.strip()}")

        # Map labeled toggles
        toggles = page.evaluate("""() => {
            var p = document.querySelector('.c-gen-config.show');
            if (!p) return [];
            var r = [];
            var rows = p.querySelectorAll('div');
            for (var row of rows) {
                var sw = row.querySelector(':scope > .c-switch');
                if (!sw) continue;
                var rect = row.getBoundingClientRect();
                if (rect.width < 100 || rect.height > 40) continue;
                var label = '';
                for (var c of row.childNodes) {
                    if (c !== sw && c.textContent) label += c.textContent.trim() + ' ';
                }
                var swRect = sw.getBoundingClientRect();
                r.push({
                    label: label.trim().substring(0, 40),
                    y: Math.round(swRect.y),
                    checked: (sw.getAttribute('class') || '').includes('isChecked')
                });
            }
            return r;
        }""")
        print(f"\n  Labeled toggles ({len(toggles)}):")
        for t in toggles:
            print(f"    y={t['y']} [{'ON' if t['checked'] else 'OFF'}] '{t['label']}'")

        # Map seed input
        seed = page.evaluate("""() => {
            var p = document.querySelector('.c-gen-config.show');
            if (!p) return {};
            var inputs = p.querySelectorAll('input');
            for (var inp of inputs) {
                if ((inp.placeholder || '').toLowerCase().includes('seed')) {
                    var r = inp.getBoundingClientRect();
                    return {found: true, x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width),
                            placeholder: inp.placeholder, type: inp.type, value: inp.value};
                }
            }
            return {found: false};
        }""")
        print(f"  Seed input: {json.dumps(seed)}")

        # Map negative prompt area
        neg = page.evaluate("""() => {
            var p = document.querySelector('.c-gen-config.show');
            if (!p) return {};
            var tas = p.querySelectorAll('textarea');
            var r = {textareas: []};
            for (var ta of tas) {
                var rect = ta.getBoundingClientRect();
                r.textareas.push({
                    x: Math.round(rect.x), y: Math.round(rect.y),
                    w: Math.round(rect.width), h: Math.round(rect.height),
                    placeholder: (ta.placeholder || '').substring(0, 80),
                    maxlen: ta.maxLength || 0
                });
            }
            return r;
        }""")
        print(f"  Textareas: {json.dumps(neg, indent=2)}")

    # ============================================================
    # 3. AI VIDEO — MODEL SELECTOR + CAMERA
    # ============================================================
    print("\n" + "="*70)
    print("SECTION 2: AI Video Model Selector + Camera")
    print("="*70)

    # Switch to AI Video
    page.mouse.click(SX, 197)  # Txt2Img first
    page.wait_for_timeout(800)
    page.mouse.click(SX, 361)  # AI Video
    page.wait_for_timeout(2500)
    close_dialogs(page)

    # Switch to Key Frame mode
    page.evaluate("""() => {
        var p = document.querySelector('.c-gen-config.show');
        if (!p) return;
        var all = p.querySelectorAll('*');
        for (var el of all) {
            if ((el.innerText || '').trim() === 'Key Frame' && el.children.length <= 1) {
                el.click(); return;
            }
        }
    }""")
    page.wait_for_timeout(1500)

    pt = panel_text(page)
    print(f"  Panel: {pt[:100]}")

    # Try clicking the model row directly with mouse coordinates
    # From the screenshot, Wan 2.1 row is at approximately y=228, spanning the full panel width
    print("\n  Clicking model selector row by coordinates...")
    # The model row with "Wan 2.1" appears to be around y=228 based on screenshots
    page.mouse.click(120, 228)
    page.wait_for_timeout(2500)

    ss(page, "p171_model_click_coords")

    # Check if a popup appeared
    popup = page.evaluate("""() => {
        // Check for any new overlay/popup/panel
        var all = document.querySelectorAll('div');
        for (var el of all) {
            var r = el.getBoundingClientRect();
            var cls = el.getAttribute('class') || '';
            // Look for a large overlay that wasn't there before
            if (r.width > 300 && r.height > 300 && r.x > 50 && r.y > 30 && r.y < 600) {
                var text = (el.innerText || '');
                if (text.includes('Wan') || text.includes('Seedance') || text.includes('Kling')) {
                    return {
                        found: true,
                        cls: cls.substring(0, 80),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        text: text.substring(0, 2000)
                    };
                }
            }
        }
        return {found: false};
    }""")
    print(f"  Popup: {json.dumps({k:v for k,v in popup.items() if k != 'text'})}")

    if popup.get('found'):
        print(f"\n  MODEL SELECTOR CONTENTS:")
        for line in popup['text'].split('\n'):
            if line.strip(): print(f"    {line.strip()}")
        ss(page, "p171_model_selector_content")

        # Scroll to see all
        page.evaluate(f"""() => {{
            var el = document.elementFromPoint({popup['x'] + 50}, {popup['y'] + popup['h']//2});
            while (el) {{
                if (el.scrollHeight > el.clientHeight + 50) {{
                    el.scrollTop = el.scrollHeight;
                    return 'scrolled';
                }}
                el = el.parentElement;
            }}
        }}""")
        page.wait_for_timeout(1000)
        ss(page, "p171_model_selector_scrolled")

        more = page.evaluate(f"""() => {{
            var el = document.elementFromPoint({popup['x'] + 50}, {popup['y'] + popup['h']//2});
            while (el) {{
                if (el.scrollHeight > el.clientHeight + 50) {{
                    return el.innerText.substring(0, 2000);
                }}
                el = el.parentElement;
            }}
            return '';
        }}""")
        if more:
            print(f"\n  AFTER SCROLL:")
            for line in more.split('\n'):
                if line.strip() and line.strip() not in popup.get('text', ''):
                    print(f"    {line.strip()}")

        page.keyboard.press("Escape")
        page.wait_for_timeout(500)
    else:
        # Try the chevron/arrow icon specifically
        print("  No popup. Trying to click the '>' arrow icon on model row...")
        page.evaluate("""() => {
            var p = document.querySelector('.c-gen-config.show');
            if (!p) return;
            // Find SVG or icon element near the model name
            var arrows = p.querySelectorAll('svg, [class*="arrow"], [class*="chevron"], .ico-arrow, [class*="icon"]');
            for (var a of arrows) {
                var r = a.getBoundingClientRect();
                if (r.y > 215 && r.y < 245 && r.x > 130) {
                    a.click();
                    return 'clicked arrow at ' + Math.round(r.x) + ',' + Math.round(r.y);
                }
            }
            // Try clicking the right side of the model row (where the arrow typically is)
            return 'no arrow found';
        }""")
        page.wait_for_timeout(2000)
        ss(page, "p171_model_arrow_click")

        # Check again for popup
        popup2 = page.evaluate("""() => {
            var all = document.querySelectorAll('div');
            for (var el of all) {
                var r = el.getBoundingClientRect();
                var text = (el.innerText || '');
                if (r.width > 300 && r.height > 200 && (text.includes('Seedance') || text.includes('Kling'))) {
                    return {found: true, text: text.substring(0, 2000)};
                }
            }
            return {found: false};
        }""")
        if popup2.get('found'):
            print("  MODEL SELECTOR FOUND (retry)!")
            for line in popup2['text'].split('\n'):
                if line.strip(): print(f"    {line.strip()}")
            ss(page, "p171_model_selector_retry")
        else:
            print("  Still no model popup. Using known model list from previous exploration.")

    # CAMERA SECTION
    print("\n  Expanding Camera section...")
    # Click the camera-movement-btn specifically
    page.evaluate("""() => {
        var btn = document.querySelector('.camera-movement-btn');
        if (btn) { btn.click(); return 'clicked camera-movement-btn'; }
        // Fallback: click the camera-movement-wrapper
        var w = document.querySelector('.camera-movement-wrapper');
        if (w) { w.click(); return 'clicked wrapper'; }
        return 'not found';
    }""")
    page.wait_for_timeout(2000)
    ss(page, "p171_camera_expanded")

    # Map camera presets
    camera_text = panel_text(page)
    print("\n  Panel after camera click:")
    for line in camera_text.split('\n'):
        if line.strip(): print(f"    {line.strip()}")

    # Map all elements in expanded camera section
    camera_details = page.evaluate("""() => {
        var wrapper = document.querySelector('.camera-movement-wrapper');
        if (!wrapper) return {error: 'no wrapper'};
        var r = wrapper.getBoundingClientRect();
        var result = {
            wrapper: {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)},
            items: []
        };
        // Get all clickable items inside/near the camera wrapper
        var all = wrapper.querySelectorAll('*');
        for (var el of all) {
            var er = el.getBoundingClientRect();
            var t = (el.innerText || '').trim();
            var cls = el.getAttribute('class') || '';
            if (er.width > 10 && er.height > 10 && t) {
                result.items.push({
                    text: t.substring(0, 30),
                    x: Math.round(er.x), y: Math.round(er.y),
                    w: Math.round(er.width), h: Math.round(er.height),
                    tag: el.tagName, cls: cls.substring(0, 40)
                });
            }
        }
        // Check if expanded (height > 80)
        result.expanded = r.height > 80;
        return result;
    }""")
    print(f"\n  Camera details: {json.dumps(camera_details, indent=2)}")

    # ============================================================
    # 4. IMAGE EDITOR — PRODUCT BACKGROUND
    # ============================================================
    print("\n" + "="*70)
    print("SECTION 3: Product Background Sub-Tool")
    print("="*70)

    # Open Image Editor
    page.mouse.click(SX, 361)  # AI Video first
    page.wait_for_timeout(800)
    page.mouse.click(SX, 698)  # Image Editor
    page.wait_for_timeout(2500)
    close_dialogs(page)

    # Scroll all the way down to find Product Background
    page.evaluate("() => { var p = document.querySelector('.c-gen-config.show'); if (p) p.scrollTop = p.scrollHeight; }")
    page.wait_for_timeout(500)
    ss(page, "p171_image_editor_bottom")

    # Find and click Product Background / Background
    pb = page.evaluate("""() => {
        var p = document.querySelector('.c-gen-config.show');
        if (!p) return {found: false};
        // Look for "Background" or "Product Background" text
        var all = p.querySelectorAll('.collapse-option, div, button');
        for (var el of all) {
            var t = (el.innerText || '').trim();
            if (t === 'Background' || t.includes('Product Background')) {
                var r = el.getBoundingClientRect();
                if (r.width > 50 && r.height > 20 && r.y > 0) {
                    el.click();
                    return {found: true, text: t, x: Math.round(r.x), y: Math.round(r.y)};
                }
            }
        }
        return {found: false, panel_bottom: p.innerText.substring(p.innerText.length - 200)};
    }""")
    print(f"  Product Background click: {json.dumps(pb)}")

    if pb.get("found"):
        page.wait_for_timeout(2500)
        close_dialogs(page)
        ss(page, "p171_product_background")

        pb_text = panel_text(page)
        print(f"\n  Product Background panel:")
        for line in pb_text.split('\n')[:25]:
            if line.strip(): print(f"    {line.strip()}")

        # Map controls
        pb_controls = page.evaluate("""() => {
            var p = document.querySelector('.c-gen-config.show');
            if (!p) return {};
            var r = {};
            // Uploads
            r.uploads = p.querySelectorAll('.pick-image, .upload-image-btn').length;
            // Textareas
            var tas = p.querySelectorAll('textarea, .custom-textarea');
            r.textareas = [];
            for (var ta of tas) {
                var rect = ta.getBoundingClientRect();
                if (rect.width > 50 && rect.y > 50) {
                    r.textareas.push({
                        placeholder: (ta.placeholder || ta.dataset.placeholder || '').substring(0, 80),
                        w: Math.round(rect.width), h: Math.round(rect.height)
                    });
                }
            }
            // Template thumbnails
            var imgs = p.querySelectorAll('img');
            r.template_images = 0;
            for (var img of imgs) {
                var ir = img.getBoundingClientRect();
                if (ir.width > 30 && ir.width < 200 && ir.y > 50) r.template_images++;
            }
            // Buttons
            var btns = p.querySelectorAll('button');
            r.buttons = [];
            for (var b of btns) {
                var t = (b.innerText || '').trim();
                var br = b.getBoundingClientRect();
                if (t && br.width > 30 && br.y > 50 && br.y < 800) {
                    r.buttons.push({text: t.substring(0, 30), y: Math.round(br.y)});
                }
            }
            // Generate
            var g = p.querySelector('.generative');
            if (g) r.generate = {text: (g.innerText||'').trim().substring(0,20), disabled: !!g.disabled};
            return r;
        }""")
        print(f"  Controls: {json.dumps(pb_controls, indent=2)}")

    # ============================================================
    # 5. IMG2IMG ADVANCED
    # ============================================================
    print("\n" + "="*70)
    print("SECTION 4: Img2Img Advanced")
    print("="*70)

    # Close Image Editor panel first
    page.evaluate("""() => {
        var close = document.querySelector('.c-gen-config.show .ico-close') ||
                    document.querySelector('.c-gen-config.show .close');
        if (close) close.click();
    }""")
    page.wait_for_timeout(800)

    page.mouse.click(SX, 197)  # Txt2Img
    page.wait_for_timeout(800)
    page.mouse.click(SX, 252)  # Img2Img
    page.wait_for_timeout(2000)
    close_dialogs(page)

    pt = panel_text(page)
    print(f"  Panel: {pt[:80]}")

    if "Image-to-Image" in pt or "Img2Img" in pt or "Structure Match" in pt:
        # Expand Advanced
        page.evaluate("""() => {
            var p = document.querySelector('.c-gen-config.show');
            if (!p) return;
            var btn = p.querySelector('.advanced-btn');
            if (btn) btn.click();
        }""")
        page.wait_for_timeout(1500)
        page.evaluate("() => { var p = document.querySelector('.c-gen-config.show'); if (p) p.scrollTop = p.scrollHeight; }")
        page.wait_for_timeout(500)
        ss(page, "p171_img2img_advanced")

        img_text = panel_text(page)
        print(f"\n  Img2Img full panel:")
        for line in img_text.split('\n'):
            if line.strip(): print(f"    {line.strip()}")

        # Map toggles with labels
        toggles = page.evaluate("""() => {
            var p = document.querySelector('.c-gen-config.show');
            if (!p) return [];
            var r = [];
            var rows = p.querySelectorAll('div');
            for (var row of rows) {
                var sw = row.querySelector(':scope > .c-switch');
                if (!sw) continue;
                var rect = row.getBoundingClientRect();
                if (rect.width < 100 || rect.height > 50 || rect.y < 50) continue;
                var label = '';
                for (var c of row.childNodes) {
                    if (c !== sw && c.textContent) label += c.textContent.trim() + ' ';
                }
                r.push({
                    label: label.trim().substring(0, 40),
                    y: Math.round(rect.y),
                    checked: (sw.getAttribute('class') || '').includes('isChecked')
                });
            }
            return r;
        }""")
        print(f"\n  Toggles:")
        for t in toggles:
            print(f"    y={t['y']} [{'ON' if t['checked'] else 'OFF'}] '{t['label']}'")

    print("\n" + "="*70)
    print("EXPLORATION PART 5 COMPLETE")
    print("="*70)


if __name__ == "__main__":
    main()
