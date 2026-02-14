#!/usr/bin/env python3
"""Phase 138b: Enhance [1] — click the NUMBERED button, not the icon.

P138 found the exact positions:
  Icon:  (1246, 888) class=selected-btn  ← THIS WAS CLICKED (wrong)
  [1]:   (1291, 873) class=btn           ← THIS IS CORRECT
  [2]:   (1328, 873) class=btn
  [3]:   (1366, 873) class=btn
  [4]:   (1403, 873) class=btn

Simple test: click (1291, 873) and see what happens.
"""

from __future__ import annotations

import os
import sys
import time
import urllib.request
from pathlib import Path

_repo = Path(__file__).resolve().parent.parent
if str(_repo) not in sys.path:
    sys.path.insert(0, str(_repo))


def main():
    from playwright.sync_api import sync_playwright
    from tools.lib.brave_profile import DEFAULT_CDP_PORT, is_browser_running
    from tools.lib.dzine_browser import (
        _js_get_result_images, close_all_dialogs, VIEWPORT,
    )

    print("=" * 70)
    print("PHASE 138b: Click Enhance [1] at exact (1291, 873)")
    print("=" * 70)

    if not is_browser_running():
        print("[P138b] ERROR: Brave browser not running.")
        return

    pw = sync_playwright().start()
    try:
        browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{DEFAULT_CDP_PORT}")
        context = browser.contexts[0]

        dzine_pages = [p for p in context.pages if "dzine.ai/canvas" in (p.url or "")]
        if not dzine_pages:
            print("[P138b] No Dzine canvas found.")
            return

        page = dzine_pages[0]
        page.set_viewport_size(VIEWPORT)  # MUST be 1440x900
        page.bring_to_front()
        page.wait_for_timeout(1500)
        print(f"[P138b] Canvas: {page.url}")

        # Close any open overlays/panels first
        print("[P138b] Closing overlays...")
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)

        # Also close the Generative Expand panel if open
        page.evaluate("""() => {
            for (var el of document.querySelectorAll('.c-gen-config.show .ico-close')) el.click();
        }""")
        page.wait_for_timeout(500)
        close_all_dialogs(page)
        page.wait_for_timeout(500)

        # Switch to Results tab
        print("[P138b] Switching to Results tab...")
        page.evaluate("""() => {
            for (var el of document.querySelectorAll('[class*="header-item"]')) {
                if ((el.innerText || '').includes('Result')) { el.click(); return true; }
            }
            return false;
        }""")
        page.wait_for_timeout(1000)

        before_count = len(_js_get_result_images(page))
        print(f"[P138b] Result images before: {before_count}")

        # Verify the button positions are still correct
        verify = page.evaluate("""() => {
            for (var el of document.querySelectorAll('button.btn, button[class*="btn"]')) {
                var text = (el.innerText || '').trim();
                if (text === '1') {
                    var r = el.getBoundingClientRect();
                    // Only look at the Enhance row (y > 860)
                    if (r.y > 860 && r.x > 1200) {
                        return {text: text, cx: Math.round(r.x + r.width/2), cy: Math.round(r.y + r.height/2)};
                    }
                }
            }
            return null;
        }""")
        print(f"[P138b] Verify button [1] position: {verify}")

        # Screenshot before
        page.screenshot(path=os.path.expanduser("~/Downloads/p138b_before.png"))

        # Click the [1] button at (1291, 873) — confirmed from P138 DOM output
        click_x, click_y = 1291, 873
        if verify:
            click_x, click_y = verify["cx"], verify["cy"]
        print(f"[P138b] Clicking ({click_x}, {click_y})...")
        page.mouse.click(click_x, click_y)
        page.wait_for_timeout(4000)

        # Screenshot after
        page.screenshot(path=os.path.expanduser("~/Downloads/p138b_after.png"))

        # Check what opened — scan ALL visible elements in center screen
        print("[P138b] Checking for Enhance popup...")
        center_elements = page.evaluate("""() => {
            var items = [];
            for (var el of document.querySelectorAll('*')) {
                var r = el.getBoundingClientRect();
                var s = window.getComputedStyle(el);
                // Center screen, substantial size, visible
                if (r.width > 200 && r.height > 150 && r.x > 200 && r.x < 900 &&
                    r.y > 100 && r.y < 600 &&
                    s.display !== 'none' && s.visibility !== 'hidden' && s.opacity !== '0') {
                    var text = (el.innerText || '').substring(0, 300);
                    // Only include elements that mention enhance/upscale terms
                    if (text.includes('Upscale') || text.includes('Precision') ||
                        text.includes('Creative') || text.includes('scale') ||
                        text.includes('credits') || text.includes('PNG') || text.includes('JPG')) {
                        items.push({
                            x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height),
                            text: text.substring(0, 200),
                            cls: (el.className || '').substring(0, 80),
                            zIndex: s.zIndex,
                            position: s.position
                        });
                    }
                }
            }
            return items;
        }""")

        if center_elements:
            print(f"[P138b] Enhance popup elements: {len(center_elements)}")
            for e in center_elements:
                print(f"  [{e['x']},{e['y']}] {e['w']}x{e['h']} z={e['zIndex']} pos={e['position']}")
                print(f"    cls: {e['cls'][:60]}")
                lines = e["text"].split("\n")[:5]
                for line in lines:
                    if line.strip():
                        print(f"    {line.strip()[:80]}")
        else:
            print("[P138b] No Enhance popup detected in center screen")

            # Check what IS visible in center (any large centered element)
            any_center = page.evaluate("""() => {
                var items = [];
                for (var el of document.querySelectorAll('*')) {
                    var r = el.getBoundingClientRect();
                    var s = window.getComputedStyle(el);
                    if (r.width > 300 && r.height > 200 && r.x > 200 && r.x < 800 &&
                        r.y > 50 && r.y < 500 &&
                        s.display !== 'none' && s.visibility !== 'hidden' &&
                        (s.position === 'fixed' || s.position === 'absolute' || parseInt(s.zIndex) > 10)) {
                        items.push({
                            x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height),
                            text: (el.innerText || '').substring(0, 150),
                            cls: (el.className || '').substring(0, 60),
                            zIndex: s.zIndex, position: s.position
                        });
                    }
                }
                return items;
            }""")
            print(f"[P138b] Centered fixed/absolute elements: {len(any_center)}")
            for e in any_center:
                print(f"  [{e['x']},{e['y']}] {e['w']}x{e['h']} z={e['zIndex']} pos={e['position']} cls={e['cls'][:40]}")
                if e["text"]:
                    print(f"    {e['text'][:120]}")

        # Check if a lightbox opened instead
        lightbox_check = page.evaluate("""() => {
            for (var el of document.querySelectorAll('img')) {
                var r = el.getBoundingClientRect();
                if (r.width > 300 && r.height > 300 && r.x > 250 && r.x < 700 && r.y > 50 && r.y < 300) {
                    return {type: 'lightbox', x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height)};
                }
            }
            return null;
        }""")
        if lightbox_check:
            print(f"[P138b] Lightbox opened: {lightbox_check}")
            print("[P138b] This means the click hit the result thumbnail, not the button")

        # Also check for any toast/notification
        toast = page.evaluate("""() => {
            for (var el of document.querySelectorAll('[class*="toast"], [class*="message"], [class*="notification"], [class*="tip"]')) {
                var text = (el.innerText || '').trim();
                var r = el.getBoundingClientRect();
                if (text && r.width > 0) return {text: text.substring(0, 100), x: r.x, y: r.y};
            }
            return null;
        }""")
        if toast:
            print(f"[P138b] Toast: {toast}")

        # If no popup, try finding buttons with text "1" that are part of the Enhance action row
        print("\n[P138b] Detailed scan of Enhance & Upscale row buttons...")
        enhance_btns = page.evaluate("""() => {
            // First find the Enhance & Upscale label in the results panel
            var enhLabel = null;
            for (var el of document.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                if ((text === 'Enhance & Upscale' || text === 'Enhance &\\nUpscale') && el.childElementCount === 0) {
                    var r = el.getBoundingClientRect();
                    if (r.x > 1070 && r.y > 800) {
                        enhLabel = {x: r.x, y: r.y, cy: r.y + r.height/2, w: r.width, h: r.height};
                        break;
                    }
                }
            }
            if (!enhLabel) return {label: null, buttons: []};

            // Now find sibling/nearby button elements
            var btns = [];
            for (var el of document.querySelectorAll('button')) {
                var text = (el.innerText || '').trim();
                var r = el.getBoundingClientRect();
                if (r.x > 1200 && Math.abs(r.y + r.height/2 - enhLabel.cy) < 15 && r.width < 50) {
                    btns.push({
                        text: text,
                        x: Math.round(r.x), y: Math.round(r.y),
                        cx: Math.round(r.x + r.width/2), cy: Math.round(r.y + r.height/2),
                        w: Math.round(r.width), h: Math.round(r.height),
                        cls: el.className,
                        tag: el.tagName,
                        onClick: !!el.onclick,
                        parentCls: (el.parentElement && el.parentElement.className) || ''
                    });
                }
            }
            btns.sort(function(a,b) { return a.cx - b.cx; });
            return {label: enhLabel, buttons: btns};
        }""")

        if enhance_btns["label"]:
            print(f"[P138b] Label: y={enhance_btns['label']['y']:.0f}, cy={enhance_btns['label']['cy']:.0f}")
        print(f"[P138b] Buttons: {len(enhance_btns['buttons'])}")
        for b in enhance_btns["buttons"]:
            print(f"  [{b['text']}] ({b['cx']},{b['cy']}) {b['w']}x{b['h']} cls={b['cls']} parent={b['parentCls'][:40]}")

        # Try clicking via JavaScript instead of mouse coordinates
        if enhance_btns["buttons"]:
            first_btn = enhance_btns["buttons"][0]
            if first_btn["text"] in ("", "1"):
                # Skip the icon button (empty text), find the first numbered one
                for b in enhance_btns["buttons"]:
                    if b["text"] == "1":
                        first_btn = b
                        break

            print(f"\n[P138b] Trying JS click on button with text '{first_btn['text']}' at ({first_btn['cx']},{first_btn['cy']})...")
            coords = {"x": first_btn["cx"], "y": first_btn["cy"]}
            js_result = page.evaluate("""(coords) => {
                for (var el of document.querySelectorAll('button')) {
                    var r = el.getBoundingClientRect();
                    if (Math.abs(r.x + r.width/2 - coords.x) < 5 && Math.abs(r.y + r.height/2 - coords.y) < 5) {
                        el.click();
                        return {clicked: true, text: (el.innerText || '').trim(), cls: el.className};
                    }
                }
                return {clicked: false};
            }""", coords)
            print(f"[P138b] JS click result: {js_result}")

            page.wait_for_timeout(4000)
            page.screenshot(path=os.path.expanduser("~/Downloads/p138b_jsclick.png"))

            # Check again for popup
            popup_check = page.evaluate("""() => {
                var items = [];
                for (var el of document.querySelectorAll('*')) {
                    var text = (el.innerText || '').trim();
                    if (text.includes('Precision') || text.includes('Creative') ||
                        (text.includes('Upscale') && text.length < 50)) {
                        var r = el.getBoundingClientRect();
                        if (r.width > 0 && r.x > 200 && r.x < 1000 && r.y > 100 && r.y < 700) {
                            items.push({text: text, x: Math.round(r.x), y: Math.round(r.y)});
                        }
                    }
                }
                return items;
            }""")
            print(f"[P138b] Popup indicators: {popup_check}")

        # Final check
        after_count = len(_js_get_result_images(page))
        print(f"\n[P138b] Result images: {before_count} -> {after_count}")

    finally:
        pw.stop()


if __name__ == "__main__":
    main()
