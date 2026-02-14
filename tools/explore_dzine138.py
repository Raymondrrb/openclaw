#!/usr/bin/env python3
"""Phase 138: Enhance & Upscale via Results Panel — corrected coordinates.

P137 findings:
- Product faithful workflow: PASS (BG Remove 11s + Expand 4 results in ~75s)
- Enhance click missed: targeted sidebar label at y=630, not results panel row at y~841
- Image preview lightbox opened instead

This phase:
1. Reconnect to the P137 canvas (still open)
2. Close any open lightbox/panel
3. Click Enhance [1] in the results panel at the CORRECT position (~1241, ~841)
4. Handle the Enhance popup dialog
5. Wait for processing and download result

From screenshot analysis:
- Results panel action rows (right side, x > 1070):
  Chat Editor    y~633  [1]x~1241 [2]x~1279 [3]x~1317 [4]x~1355
  Image Editor   y~667
  AI Video       y~702
  Lip Sync       y~737
  Expression Ed  y~772
  Face Swap      y~807
  Enhance & Up   y~841
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
    print("PHASE 138: Enhance & Upscale via Results Panel (corrected)")
    print("=" * 70)

    if not is_browser_running():
        print("[P138] ERROR: Brave browser not running.")
        return

    pw = sync_playwright().start()
    try:
        browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{DEFAULT_CDP_PORT}")
        context = browser.contexts[0] if browser.contexts else browser.new_context()

        # Find existing Dzine canvas
        dzine_pages = [p for p in context.pages if "dzine.ai/canvas" in (p.url or "")]
        if not dzine_pages:
            print("[P138] No Dzine canvas found. Run P137 first.")
            return

        page = dzine_pages[0]
        page.set_viewport_size(VIEWPORT)
        page.bring_to_front()
        page.wait_for_timeout(1000)
        print(f"[P138] Canvas: {page.url}")

        # Check credits
        credits_before = page.evaluate("""() => {
            for (var el of document.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                // Match numbers with periods like "8.856" or "8,856"
                var m = text.match(/^([\\d,.]+)$/);
                if (m) {
                    var num = parseFloat(text.replace(',', ''));
                    if (num > 50) {
                        var r = el.getBoundingClientRect();
                        if (r.y < 50 && r.height < 40 && r.x > 1000) return text;
                    }
                }
            }
            return null;
        }""")
        print(f"[P138] Credits: {credits_before}")

        # Step 1: Close any open lightbox/dialog/panel overlay
        print("\n[P138] Step 1: Closing any open overlays...")
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)
        close_all_dialogs(page)
        page.wait_for_timeout(500)

        page.screenshot(path=os.path.expanduser("~/Downloads/p138_clean_state.png"))

        # Step 2: Switch to Results tab
        print("[P138] Step 2: Switching to Results tab...")
        page.evaluate("""() => {
            for (var el of document.querySelectorAll('[class*="header-item"]')) {
                if ((el.innerText || '').includes('Result')) { el.click(); return true; }
            }
            return false;
        }""")
        page.wait_for_timeout(1000)

        # Count result images
        before_count = len(_js_get_result_images(page))
        print(f"[P138]   Result images: {before_count}")

        # Step 3: Map the actual Results panel action rows with PRECISE positions
        print("[P138] Step 3: Mapping Results panel action buttons...")

        # Find ALL action row labels in the results panel (x > 1070)
        action_rows = page.evaluate("""() => {
            var rows = [];
            var labels = ['Chat Editor', 'Image Editor', 'AI Video', 'Lip Sync',
                         'Expression Edit', 'Face Swap', 'Enhance & Upscale'];
            for (var label of labels) {
                for (var el of document.querySelectorAll('*')) {
                    var text = (el.innerText || '').trim();
                    if (text === label || text === label.replace(' & ', ' &\\n')) {
                        var r = el.getBoundingClientRect();
                        if (r.x > 1070 && r.width > 0 && r.width < 200 && r.y > 600) {
                            rows.push({
                                label: label,
                                x: Math.round(r.x),
                                y: Math.round(r.y),
                                cy: Math.round(r.y + r.height / 2),
                                w: Math.round(r.width),
                                h: Math.round(r.height)
                            });
                            break;
                        }
                    }
                }
            }
            return rows;
        }""")

        if not action_rows:
            print("[P138]   No action rows found in results panel!")
            # Try broader search
            action_rows = page.evaluate("""() => {
                var rows = [];
                for (var el of document.querySelectorAll('*')) {
                    var text = (el.innerText || '').trim();
                    if (text.includes('Enhance') && text.includes('Upscale')) {
                        var r = el.getBoundingClientRect();
                        if (r.width > 0 && r.y > 600) {
                            rows.push({
                                label: 'Enhance & Upscale',
                                x: Math.round(r.x), y: Math.round(r.y),
                                cy: Math.round(r.y + r.height/2),
                                w: Math.round(r.width), h: Math.round(r.height)
                            });
                        }
                    }
                }
                return rows;
            }""")

        print(f"[P138]   Action rows found: {len(action_rows)}")
        enhance_row = None
        for row in action_rows:
            marker = " <-- TARGET" if "Enhance" in row["label"] else ""
            print(f"    {row['label']:20s} y={row['y']}, cy={row['cy']}, x={row['x']}, {row['w']}x{row['h']}{marker}")
            if "Enhance" in row["label"]:
                enhance_row = row

        # Step 4: Find the numbered buttons [1][2][3][4] on the Enhance row
        print("[P138] Step 4: Finding numbered buttons on Enhance row...")

        if enhance_row:
            target_y = enhance_row["cy"]
        else:
            # Fallback: estimate from P137 screenshot (~841)
            target_y = 841
            print(f"[P138]   Using fallback y={target_y}")

        # Find small square elements near the Enhance row y that look like buttons
        num_buttons = page.evaluate("""(targetY) => {
            var btns = [];
            for (var el of document.querySelectorAll('*')) {
                var r = el.getBoundingClientRect();
                // Numbered buttons: small squares, right side, near target y
                if (r.width >= 20 && r.width <= 45 && r.height >= 20 && r.height <= 45 &&
                    Math.abs(r.y + r.height/2 - targetY) < 20 && r.x > 1200) {
                    var text = (el.innerText || '').trim();
                    btns.push({
                        text: text,
                        cx: Math.round(r.x + r.width/2),
                        cy: Math.round(r.y + r.height/2),
                        x: Math.round(r.x),
                        y: Math.round(r.y),
                        w: Math.round(r.width),
                        h: Math.round(r.height),
                        tag: el.tagName,
                        cls: (el.className || '').substring(0, 60)
                    });
                }
            }
            // Deduplicate by position
            var unique = [];
            for (var b of btns) {
                var dup = false;
                for (var u of unique) {
                    if (Math.abs(u.cx - b.cx) < 8) { dup = true; break; }
                }
                if (!dup) unique.push(b);
            }
            unique.sort(function(a,b) { return a.cx - b.cx; });
            return unique;
        }""", target_y)

        print(f"[P138]   Buttons at y~{target_y}: {len(num_buttons)}")
        for b in num_buttons:
            print(f"    [{b['text']}] ({b['cx']}, {b['cy']}) {b['w']}x{b['h']} <{b['tag']}> cls={b['cls'][:40]}")

        # Step 5: Click Enhance [1]
        if num_buttons:
            btn = num_buttons[0]
            click_x, click_y = btn["cx"], btn["cy"]
        else:
            # Hard fallback from screenshot analysis
            click_x, click_y = 1241, target_y
            print(f"[P138]   No buttons found via DOM, using screenshot coords ({click_x}, {click_y})")

        print(f"\n[P138] Step 5: Clicking Enhance [1] at ({click_x}, {click_y})...")
        page.screenshot(path=os.path.expanduser("~/Downloads/p138_before_click.png"))
        page.mouse.click(click_x, click_y)
        page.wait_for_timeout(4000)
        page.screenshot(path=os.path.expanduser("~/Downloads/p138_after_click.png"))

        # Step 6: Detect what happened — popup, lightbox, or nothing
        print("[P138] Step 6: Checking what opened...")

        # Check for centered dialog/popup
        popup = page.evaluate("""() => {
            var results = [];
            for (var el of document.querySelectorAll('*')) {
                var r = el.getBoundingClientRect();
                var s = window.getComputedStyle(el);
                // Look for visible elements in the center area that look like popups
                if (r.width > 250 && r.height > 250 && r.x > 200 && r.x < 800 &&
                    r.y > 100 && r.y < 500 && s.display !== 'none' && s.visibility !== 'hidden' &&
                    s.position === 'fixed' || s.position === 'absolute') {
                    var text = (el.innerText || '').substring(0, 500);
                    if (text.includes('Upscale') || text.includes('Enhance') || text.includes('Precision') ||
                        text.includes('Creative') || text.includes('scale') || text.includes('PNG')) {
                        results.push({
                            x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height),
                            text: text.substring(0, 300),
                            cls: (el.className || '').substring(0, 80)
                        });
                    }
                }
            }
            return results;
        }""")

        if popup:
            print(f"[P138]   POPUP DETECTED! {len(popup)} elements")
            for p in popup:
                print(f"    [{p['x']},{p['y']}] {p['w']}x{p['h']} cls={p['cls'][:50]}")
                lines = p["text"].split("\n")[:8]
                for line in lines:
                    if line.strip():
                        print(f"      {line.strip()[:80]}")

            # Find and map all interactive controls in the popup
            print("\n[P138] Step 7: Mapping popup controls...")
            controls = page.evaluate("""() => {
                var ctrls = [];
                for (var el of document.querySelectorAll('button, [role="button"], [role="radio"], input, select')) {
                    var r = el.getBoundingClientRect();
                    if (r.width > 10 && r.x > 250 && r.x < 1000 && r.y > 100 && r.y < 700) {
                        ctrls.push({
                            text: (el.innerText || el.value || '').trim().substring(0, 50),
                            cx: Math.round(r.x + r.width/2),
                            cy: Math.round(r.y + r.height/2),
                            w: Math.round(r.width), h: Math.round(r.height),
                            tag: el.tagName, type: el.type || '',
                            disabled: !!el.disabled,
                            cls: (el.className || '').substring(0, 60)
                        });
                    }
                }
                return ctrls;
            }""")
            print(f"[P138]   Controls: {len(controls)}")
            for c in controls:
                dis = " [DISABLED]" if c["disabled"] else ""
                print(f"    ({c['cx']},{c['cy']}) {c['w']}x{c['h']} <{c['tag']}> type={c['type']} '{c['text']}'{dis}")

            # Click Upscale button
            print("\n[P138] Step 8: Clicking Upscale...")
            result = page.evaluate("""() => {
                for (var b of document.querySelectorAll('button')) {
                    var text = (b.innerText || '').trim();
                    var r = b.getBoundingClientRect();
                    if (text.includes('Upscale') && r.width > 60 && r.x > 300 && r.x < 900 && !b.disabled) {
                        b.click();
                        return {ok: true, x: Math.round(r.x), y: Math.round(r.y), text: text};
                    }
                }
                return {ok: false};
            }""")
            print(f"[P138]   {result}")

            if result.get("ok"):
                # Wait for processing
                print("[P138] Step 9: Waiting for Enhance processing...")
                page.wait_for_timeout(5000)
                page.screenshot(path=os.path.expanduser("~/Downloads/p138_processing.png"))

                enhance_start = time.monotonic()
                last_pct = ""
                while time.monotonic() - enhance_start < 180:
                    elapsed = int(time.monotonic() - enhance_start)

                    pct = page.evaluate("""() => {
                        for (var el of document.querySelectorAll('*')) {
                            var text = (el.innerText || '').trim();
                            if (text.match(/^\\d+%$/) && parseInt(text) <= 100) return text;
                        }
                        return '';
                    }""")
                    if pct and pct != last_pct:
                        print(f"[P138]   {elapsed}s: {pct}")
                        last_pct = pct

                    # Check for new results
                    current_count = len(_js_get_result_images(page))
                    if current_count > before_count:
                        print(f"[P138]   New results! {before_count} -> {current_count} ({elapsed}s)")
                        break

                    # Check if processing dialog/overlay closed
                    still_processing = page.evaluate("""() => {
                        for (var el of document.querySelectorAll('*')) {
                            var text = (el.innerText || '').trim();
                            if (text.match(/^\\d+%$/) && parseInt(text) > 0 && parseInt(text) < 100) return true;
                        }
                        return false;
                    }""")
                    if not still_processing and elapsed > 10:
                        # Check images one more time
                        page.wait_for_timeout(3000)
                        final_count = len(_js_get_result_images(page))
                        if final_count > before_count:
                            print(f"[P138]   Processing complete. Images: {before_count} -> {final_count} ({elapsed}s)")
                        else:
                            print(f"[P138]   Processing may have finished without new images ({elapsed}s)")
                        break

                    if elapsed % 15 == 0 and elapsed > 0:
                        page.screenshot(path=os.path.expanduser(f"~/Downloads/p138_progress_{elapsed}s.png"))

                    page.wait_for_timeout(5000)

                page.screenshot(path=os.path.expanduser("~/Downloads/p138_enhance_done.png"))

                # Check for new images
                all_imgs = _js_get_result_images(page)
                if len(all_imgs) > before_count:
                    new_urls = [i["src"] for i in all_imgs[before_count:]]
                    print(f"\n[P138]   New enhanced images: {len(new_urls)}")
                    for url in new_urls:
                        short = url.split("/")[-1][:60]
                        print(f"    {short}")

                    # Download enhanced image
                    dest = Path(os.path.expanduser("~/Downloads")) / f"p138_enhanced_{int(time.time())}.webp"
                    try:
                        req = urllib.request.Request(new_urls[0], headers={"User-Agent": "Mozilla/5.0"})
                        data = urllib.request.urlopen(req, timeout=30).read()
                        dest.write_bytes(data)
                        print(f"[P138]   Downloaded: {dest} ({len(data):,} bytes)")
                    except Exception as e:
                        print(f"[P138]   Download failed: {e}")

        else:
            # Check if we opened a lightbox instead
            lightbox = page.evaluate("""() => {
                // Lightbox: centered image with action icons below
                for (var el of document.querySelectorAll('img')) {
                    var r = el.getBoundingClientRect();
                    if (r.width > 300 && r.height > 300 && r.x > 200 && r.x < 800 && r.y > 50 && r.y < 400) {
                        return {type: 'lightbox', x: Math.round(r.x), y: Math.round(r.y),
                                w: Math.round(r.width), h: Math.round(r.height), src: (el.src || '').substring(0, 80)};
                    }
                }
                return null;
            }""")

            if lightbox:
                print(f"[P138]   Opened lightbox instead of Enhance popup: {lightbox}")
                print("[P138]   Closing lightbox and retrying with adjusted coordinates...")
                page.keyboard.press("Escape")
                page.wait_for_timeout(1000)

                # Need to scroll or find the actual button positions
                # Let me map ALL clickable elements near the bottom of results panel
                all_clickables = page.evaluate("""() => {
                    var items = [];
                    for (var el of document.querySelectorAll('*')) {
                        var r = el.getBoundingClientRect();
                        // Look in the bottom of the right panel
                        if (r.x > 1200 && r.y > 800 && r.y < 870 && r.width > 5 && r.width < 50 && r.height > 5) {
                            items.push({
                                text: (el.innerText || '').trim(),
                                cx: Math.round(r.x + r.width/2),
                                cy: Math.round(r.y + r.height/2),
                                w: Math.round(r.width), h: Math.round(r.height),
                                tag: el.tagName,
                                cls: (el.className || '').substring(0, 40)
                            });
                        }
                    }
                    // Deduplicate
                    var unique = [];
                    for (var b of items) {
                        var dup = false;
                        for (var u of unique) {
                            if (Math.abs(u.cx - b.cx) < 5 && Math.abs(u.cy - b.cy) < 5) { dup = true; break; }
                        }
                        if (!dup) unique.push(b);
                    }
                    return unique;
                }""")
                print(f"[P138]   Clickable elements at y>800, x>1200: {len(all_clickables)}")
                for item in all_clickables:
                    print(f"    ({item['cx']},{item['cy']}) {item['w']}x{item['h']} <{item['tag']}> '{item['text']}' cls={item['cls']}")

                if all_clickables:
                    # Click the first one (should be button [1] for Enhance)
                    btn = all_clickables[0]
                    print(f"\n[P138]   Retry: clicking ({btn['cx']}, {btn['cy']})...")
                    page.mouse.click(btn["cx"], btn["cy"])
                    page.wait_for_timeout(4000)
                    page.screenshot(path=os.path.expanduser("~/Downloads/p138_retry_click.png"))
            else:
                print("[P138]   Neither popup nor lightbox detected")
                # Full DOM scan of what's visible
                visible = page.evaluate("""() => {
                    var items = [];
                    for (var el of document.querySelectorAll('*')) {
                        var text = (el.innerText || '').trim();
                        if (text.includes('Enhance') || text.includes('Upscale') || text.includes('upscale')) {
                            var r = el.getBoundingClientRect();
                            if (r.width > 0) {
                                items.push({
                                    text: text.substring(0, 80),
                                    x: Math.round(r.x), y: Math.round(r.y),
                                    w: Math.round(r.width), h: Math.round(r.height),
                                    tag: el.tagName
                                });
                            }
                        }
                    }
                    return items;
                }""")
                print(f"[P138]   All 'Enhance/Upscale' elements:")
                for v in visible:
                    print(f"    [{v['x']},{v['y']}] {v['w']}x{v['h']} <{v['tag']}> {v['text']}")

        # Final credits check
        credits_after = page.evaluate("""() => {
            for (var el of document.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                var m = text.match(/^([\\d,.]+)$/);
                if (m) {
                    var num = parseFloat(text.replace(',', ''));
                    if (num > 50) {
                        var r = el.getBoundingClientRect();
                        if (r.y < 50 && r.height < 40 && r.x > 1000) return text;
                    }
                }
            }
            return null;
        }""")

        print(f"\n[P138] Credits: {credits_before} -> {credits_after}")

        # Summary
        print("\n" + "=" * 70)
        print("PHASE 138 SUMMARY")
        print("=" * 70)
        final_count = len(_js_get_result_images(page))
        enhanced = final_count > before_count
        print(f"  Images: {before_count} -> {final_count}")
        print(f"  Enhance: {'PASS' if enhanced else 'NEEDS MORE WORK'}")
        print(f"  Credits: {credits_before} -> {credits_after}")
        print(f"  Check ~/Downloads/p138_*.png for screenshots")

    finally:
        pw.stop()


if __name__ == "__main__":
    main()
