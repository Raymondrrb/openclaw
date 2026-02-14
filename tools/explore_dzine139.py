#!/usr/bin/env python3
"""Phase 139: Complete the Enhance & Upscale flow.

P138b opened the popup successfully. Now:
1. Select 2x scale factor
2. Keep Precision Mode + PNG format
3. Click Upscale (4 credits)
4. Wait for processing
5. Download the enhanced image
6. Compare quality/size with the original expand result
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
    print("PHASE 139: Complete Enhance & Upscale Flow")
    print("=" * 70)

    if not is_browser_running():
        print("[P139] ERROR: Brave not running.")
        return

    pw = sync_playwright().start()
    try:
        browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{DEFAULT_CDP_PORT}")
        context = browser.contexts[0]

        dzine_pages = [p for p in context.pages if "dzine.ai/canvas" in (p.url or "")]
        if not dzine_pages:
            print("[P139] No Dzine canvas found.")
            return

        page = dzine_pages[0]
        page.set_viewport_size(VIEWPORT)
        page.bring_to_front()
        page.wait_for_timeout(1000)
        print(f"[P139] Canvas: {page.url}")

        # Check if the Enhance popup is still open from P138b
        popup_open = page.evaluate("""() => {
            for (var el of document.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                if (text === 'Enhance & Upscale') {
                    var r = el.getBoundingClientRect();
                    if (r.x > 400 && r.x < 700 && r.y > 150 && r.y < 350) return true;
                }
            }
            return false;
        }""")

        if not popup_open:
            print("[P139] Enhance popup not open. Opening it...")
            # Close overlays first
            page.keyboard.press("Escape")
            page.wait_for_timeout(500)
            page.evaluate("""() => {
                for (var el of document.querySelectorAll('.c-gen-config.show .ico-close')) el.click();
            }""")
            page.wait_for_timeout(500)

            # Switch to Results tab
            page.evaluate("""() => {
                for (var el of document.querySelectorAll('[class*="header-item"]')) {
                    if ((el.innerText || '').includes('Result')) { el.click(); return; }
                }
            }""")
            page.wait_for_timeout(1000)

            # Find and click Enhance [1] via JS
            page.evaluate("""() => {
                // Find "Enhance & Upscale" label in results panel
                var enhLabel = null;
                for (var el of document.querySelectorAll('*')) {
                    var text = (el.innerText || '').trim();
                    if (text === 'Enhance & Upscale' && el.childElementCount === 0) {
                        var r = el.getBoundingClientRect();
                        if (r.x > 1070 && r.y > 800) { enhLabel = r; break; }
                    }
                }
                if (!enhLabel) return false;
                // Find button [1] on the same row
                for (var el of document.querySelectorAll('button')) {
                    var text = (el.innerText || '').trim();
                    var r = el.getBoundingClientRect();
                    if (text === '1' && r.x > 1200 && Math.abs(r.y + r.height/2 - (enhLabel.y + enhLabel.height/2)) < 15) {
                        el.click();
                        return true;
                    }
                }
                return false;
            }""")
            page.wait_for_timeout(4000)

        # Verify popup is now open
        popup_text = page.evaluate("""() => {
            for (var el of document.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                if (text.includes('Enhance & Upscale') && text.includes('Precision') && text.includes('Upscale')) {
                    return text.substring(0, 300);
                }
            }
            return '';
        }""")
        print(f"[P139] Popup open: {bool(popup_text)}")
        if not popup_text:
            print("[P139] FAIL: Could not open Enhance popup")
            page.screenshot(path=os.path.expanduser("~/Downloads/p139_no_popup.png"))
            return

        # Count images before
        before_count = len(_js_get_result_images(page))
        print(f"[P139] Result images before: {before_count}")

        # Step 1: Select 2x scale factor
        print("[P139] Step 1: Selecting 2x scale...")
        page.evaluate("""() => {
            for (var el of document.querySelectorAll('button, [role="button"]')) {
                var text = (el.innerText || '').trim();
                var r = el.getBoundingClientRect();
                if (text === '2x' && r.x > 400 && r.x < 700 && r.y > 300 && r.y < 400) {
                    el.click();
                    return true;
                }
            }
            return false;
        }""")
        page.wait_for_timeout(500)

        # Check current settings
        settings = page.evaluate("""() => {
            var info = {};
            // Check which scale is selected
            for (var el of document.querySelectorAll('button, [role="button"]')) {
                var text = (el.innerText || '').trim();
                var r = el.getBoundingClientRect();
                if (['1.5x', '2x', '3x', '4x'].includes(text) && r.x > 400 && r.y > 300) {
                    var cls = el.className || '';
                    if (cls.includes('active') || cls.includes('selected') ||
                        window.getComputedStyle(el).backgroundColor.includes('rgb(255')) {
                        info.scale = text;
                    }
                }
            }
            // Check resolution display
            for (var el of document.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                if (text.match(/\\d+ × \\d+/)) {
                    var r = el.getBoundingClientRect();
                    if (r.x > 400 && r.y > 300 && r.y < 400) {
                        info.resolution = text;
                    }
                }
            }
            return info;
        }""")
        print(f"[P139]   Settings: {settings}")

        page.screenshot(path=os.path.expanduser("~/Downloads/p139_before_upscale.png"))

        # Step 2: Click Upscale button
        print("[P139] Step 2: Clicking Upscale...")
        upscale_clicked = page.evaluate("""() => {
            for (var b of document.querySelectorAll('button')) {
                var text = (b.innerText || '').trim();
                var r = b.getBoundingClientRect();
                if (text.includes('Upscale') && r.width > 60 && r.x > 400 && r.x < 700 && r.y > 400 && !b.disabled) {
                    b.click();
                    return {ok: true, text: text, x: Math.round(r.x), y: Math.round(r.y)};
                }
            }
            return {ok: false};
        }""")
        print(f"[P139]   {upscale_clicked}")

        if not upscale_clicked.get("ok"):
            print("[P139] FAIL: Could not click Upscale button")
            page.screenshot(path=os.path.expanduser("~/Downloads/p139_no_upscale.png"))
            return

        # Step 3: Wait for processing
        print("[P139] Step 3: Waiting for Enhance processing...")
        page.wait_for_timeout(3000)

        enhance_start = time.monotonic()
        last_pct = ""
        success = False

        while time.monotonic() - enhance_start < 180:
            elapsed = int(time.monotonic() - enhance_start)

            # Check progress percentage
            pct = page.evaluate("""() => {
                for (var el of document.querySelectorAll('*')) {
                    var text = (el.innerText || '').trim();
                    if (text.match(/^\\d+%$/) && parseInt(text) > 0 && parseInt(text) <= 100) {
                        var r = el.getBoundingClientRect();
                        if (r.width > 0) return text;
                    }
                }
                return '';
            }""")
            if pct and pct != last_pct:
                print(f"[P139]   {elapsed}s: {pct}")
                last_pct = pct

            # Check for new images
            current_count = len(_js_get_result_images(page))
            if current_count > before_count:
                print(f"[P139]   New results! {before_count} -> {current_count} ({elapsed}s)")
                success = True
                break

            # Check if processing completed (popup closed or "complete" indicator)
            processing_indicator = page.evaluate("""() => {
                // Check for progress bar, spinner, or percentage
                for (var el of document.querySelectorAll('[class*="progress"], [class*="loading"], [class*="spinner"]')) {
                    var r = el.getBoundingClientRect();
                    var s = window.getComputedStyle(el);
                    if (r.width > 0 && s.display !== 'none') return 'processing';
                }
                // Check for percentage text in popup area
                for (var el of document.querySelectorAll('*')) {
                    var text = (el.innerText || '').trim();
                    if (text.match(/^\\d+%$/) && parseInt(text) < 100) {
                        var r = el.getBoundingClientRect();
                        if (r.x > 300 && r.x < 900) return 'processing:' + text;
                    }
                }
                return 'unknown';
            }""")

            if elapsed % 10 == 0:
                print(f"[P139]   {elapsed}s: status={processing_indicator}, images={current_count}")

            if elapsed > 10 and processing_indicator == 'unknown':
                # Check if popup closed entirely
                popup_gone = page.evaluate("""() => {
                    for (var el of document.querySelectorAll('*')) {
                        var text = (el.innerText || '').trim();
                        if (text === 'Enhance & Upscale') {
                            var r = el.getBoundingClientRect();
                            if (r.x > 400 && r.x < 700 && r.y > 150 && r.y < 350) return false;
                        }
                    }
                    return true;
                }""")
                if popup_gone:
                    print(f"[P139]   Popup closed at {elapsed}s — checking for results...")
                    page.wait_for_timeout(3000)
                    final_check = len(_js_get_result_images(page))
                    if final_check > before_count:
                        print(f"[P139]   Results appeared! {before_count} -> {final_check}")
                        success = True
                    break

            if elapsed > 0 and elapsed % 30 == 0:
                page.screenshot(path=os.path.expanduser(f"~/Downloads/p139_{elapsed}s.png"))

            page.wait_for_timeout(5000)

        page.screenshot(path=os.path.expanduser("~/Downloads/p139_enhance_done.png"))

        # Step 4: Download enhanced result
        all_imgs = _js_get_result_images(page)
        final_count = len(all_imgs)
        print(f"\n[P139] Final image count: {final_count} (was {before_count})")

        if final_count > before_count:
            new_urls = [i["src"] for i in all_imgs[before_count:]]
            print(f"[P139] New enhanced images: {len(new_urls)}")
            for i, url in enumerate(new_urls):
                short = url.split("/")[-1][:60]
                print(f"  [{i+1}] {short}")

            # Download
            for i, url in enumerate(new_urls[:2]):
                dest = Path(os.path.expanduser("~/Downloads")) / f"p139_enhanced_{i+1}_{int(time.time())}.webp"
                try:
                    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                    data = urllib.request.urlopen(req, timeout=30).read()
                    dest.write_bytes(data)
                    print(f"  Downloaded: {dest} ({len(data):,} bytes)")
                except Exception as e:
                    print(f"  Download failed: {e}")
                    # Try PNG extension
                    dest_png = dest.with_suffix(".png")
                    try:
                        req = urllib.request.Request(url.replace(".webp", ".png"), headers={"User-Agent": "Mozilla/5.0"})
                        data = urllib.request.urlopen(req, timeout=30).read()
                        dest_png.write_bytes(data)
                        print(f"  Downloaded PNG: {dest_png} ({len(data):,} bytes)")
                    except Exception:
                        pass
        else:
            print("[P139] No new enhanced images found")

            # Check if enhanced result appeared somewhere else (like canvas)
            canvas_state = page.evaluate("""() => {
                var layers = document.querySelectorAll('.layer-item');
                return {
                    layers: layers.length,
                    canvasSize: document.querySelector('.canvas-info')?.innerText || 'unknown'
                };
            }""")
            print(f"[P139] Canvas state: {canvas_state}")

        # Credits check
        credits_after = page.evaluate("""() => {
            for (var el of document.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                var m = text.match(/^([\\d,.]+)$/);
                if (m) {
                    var num = parseFloat(text.replace(',', ''));
                    if (num > 50) {
                        var r = el.getBoundingClientRect();
                        if (r.y < 50 && r.height < 40 && r.x > 900) return text;
                    }
                }
            }
            return null;
        }""")
        print(f"[P139] Credits after: {credits_after}")

        # Summary
        print("\n" + "=" * 70)
        print("PHASE 139 SUMMARY")
        print("=" * 70)
        print(f"  Enhance: {'PASS' if success else 'INCOMPLETE'}")
        print(f"  Images: {before_count} -> {final_count}")
        print(f"  Credits: {credits_after}")
        print(f"  Check ~/Downloads/p139_*.png for screenshots")

    finally:
        pw.stop()


if __name__ == "__main__":
    main()
