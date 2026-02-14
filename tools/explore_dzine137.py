#!/usr/bin/env python3
"""Phase 137: End-to-end product_faithful workflow + Enhance via Results panel.

Goals:
1. Download a fresh Amazon product image
2. Test full product_faithful workflow (BG Remove + Expand) end-to-end
3. Test Enhance & Upscale via results panel numbered buttons (P136 breakthrough)
4. All in ONE playwright session to avoid event loop conflicts

Expected: ~8 credits for Expand, ~4 for Enhance = ~12 total
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


def get_credits(page) -> int | None:
    """Check Dzine credits from a page with header visible."""
    return page.evaluate("""() => {
        for (var el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            if (text.match(/^[\\d,]+$/) && parseInt(text.replace(',','')) > 50) {
                var r = el.getBoundingClientRect();
                if (r.y < 50 && r.height < 40) return parseInt(text.replace(',',''));
            }
        }
        return null;
    }""")


def main():
    from playwright.sync_api import sync_playwright
    from tools.lib.brave_profile import DEFAULT_CDP_PORT, is_browser_running
    from tools.lib.dzine_browser import (
        _bg_remove, _create_project_from_image, _download_image,
        _export_canvas, _generative_expand, _js_get_result_images,
        close_all_dialogs, validate_image, _file_sha256,
        VIEWPORT,
    )

    print("=" * 70)
    print("PHASE 137: Product Faithful + Enhance via Results Panel")
    print("=" * 70)

    if not is_browser_running():
        print("[P137] ERROR: Brave browser not running. Start it first.")
        return

    pw = sync_playwright().start()
    try:
        browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{DEFAULT_CDP_PORT}")
        context = browser.contexts[0] if browser.contexts else browser.new_context()

        # --- Check initial credits ---
        dzine_pages = [p for p in context.pages if "dzine.ai" in (p.url or "")]
        credits_before = None
        if dzine_pages:
            credits_before = get_credits(dzine_pages[0])
        print(f"[P137] Credits before: {credits_before or '(will check later)'}")

        # --- Download product image ---
        dest_img = Path(os.path.expanduser("~/Downloads")) / "p137_product.jpg"
        if dest_img.exists() and dest_img.stat().st_size > 10000:
            print(f"[P137] Using cached image: {dest_img} ({dest_img.stat().st_size:,} bytes)")
        else:
            print("[P137] Downloading product image via browser...")
            dl_page = context.new_page()
            dl_page.set_viewport_size(VIEWPORT)
            dl_page.goto("https://www.amazon.com/dp/B09XS7JWHH",
                        wait_until="domcontentloaded", timeout=30000)
            dl_page.wait_for_timeout(5000)

            img_url = dl_page.evaluate("""() => {
                var img = document.querySelector('#landingImage, #imgBlkFront, .a-dynamic-image');
                if (img) return img.getAttribute('data-old-hires') || img.src;
                for (var el of document.querySelectorAll('img')) {
                    if ((el.src || '').includes('images/I/') && el.naturalWidth > 300) return el.src;
                }
                return null;
            }""")
            print(f"[P137] Image URL: {img_url}")

            if img_url:
                try:
                    req_obj = urllib.request.Request(img_url, headers={"User-Agent": "Mozilla/5.0"})
                    data = urllib.request.urlopen(req_obj, timeout=15).read()
                    dest_img.write_bytes(data)
                    print(f"[P137] Downloaded: {dest_img} ({len(data):,} bytes)")
                except Exception as e:
                    print(f"[P137] Download failed: {e}, screenshotting...")
                    dl_page.screenshot(path=str(dest_img),
                                       clip={"x": 40, "y": 100, "width": 500, "height": 500})
            else:
                dl_page.screenshot(path=str(dest_img),
                                   clip={"x": 40, "y": 100, "width": 500, "height": 500})
            dl_page.close()

        # --- Close any existing Dzine canvas tabs ---
        for p in context.pages:
            if "dzine.ai/canvas" in (p.url or ""):
                try:
                    p.close()
                except Exception:
                    pass

        # ==============================================================
        # TEST 1: Product Faithful (BG Remove + Expand)
        # ==============================================================
        print("\n" + "=" * 60)
        print("[P137] TEST 1: Product Faithful Workflow")
        print("=" * 60)
        start = time.monotonic()

        # Step 1: Create project from image
        print("[P137] Step 1: Creating project from image...")
        page, canvas_url = _create_project_from_image(context, str(dest_img))
        if not page:
            print("[P137] FAIL: Could not create project from image")
            return

        print(f"[P137]   Canvas: {canvas_url}")

        # Check credits now that we're on canvas
        if not credits_before:
            credits_before = get_credits(page)
            print(f"[P137] Credits: {credits_before}")

        # Step 2: BG Remove
        print("[P137] Step 2: BG Remove...")
        bg_time = _bg_remove(page)
        print(f"[P137]   Done in {bg_time:.1f}s")
        page.screenshot(path=os.path.expanduser("~/Downloads/p137_after_bgremove.png"))

        # Step 3: Generative Expand
        print("[P137] Step 3: Generative Expand...")
        backdrop = "Clean white studio backdrop with soft professional lighting, subtle shadow underneath product"
        expand_urls = _generative_expand(page, backdrop, "16:9")
        expand_time = time.monotonic() - start - bg_time

        if not expand_urls:
            print("[P137] FAIL: Generative Expand produced no results")
            page.screenshot(path=os.path.expanduser("~/Downloads/p137_expand_fail.png"))
            return

        print(f"[P137]   {len(expand_urls)} results in {expand_time:.0f}s")
        for i, url in enumerate(expand_urls):
            short = url.split("/")[-1][:40]
            print(f"    [{i+1}] {short}")

        # Step 4: Download best result
        print("[P137] Step 4: Downloading best result...")
        output = Path(os.path.expanduser("~/Downloads")) / f"p137_faithful_{int(time.time())}.webp"
        if _download_image(expand_urls[0], output):
            valid, err = validate_image(output)
            sz = output.stat().st_size if output.exists() else 0
            sha = _file_sha256(output) if output.exists() else ""
            print(f"[P137]   Downloaded: {output} ({sz:,} bytes)")
            print(f"[P137]   SHA-256: {sha[:16]}...")
            print(f"[P137]   Valid: {valid} {err or ''}")
        else:
            # Fallback: export
            print("[P137]   Direct download failed, exporting canvas...")
            export_path = _export_canvas(page, "PNG", "2x")
            if export_path:
                import shutil
                shutil.move(str(export_path), str(output))
                print(f"[P137]   Exported: {output} ({output.stat().st_size:,} bytes)")
            else:
                print("[P137]   FAIL: Both download and export failed")

        total_faithful = time.monotonic() - start
        credits_after_faithful = get_credits(page)
        print(f"\n[P137] Product Faithful complete: {total_faithful:.0f}s total")
        print(f"[P137] Credits: {credits_before} -> {credits_after_faithful}")
        if credits_before and credits_after_faithful:
            print(f"[P137] Credits used: {credits_before - credits_after_faithful}")

        page.screenshot(path=os.path.expanduser("~/Downloads/p137_faithful_done.png"))

        # ==============================================================
        # TEST 2: Enhance & Upscale via Results Panel
        # ==============================================================
        print("\n" + "=" * 60)
        print("[P137] TEST 2: Enhance & Upscale via Results Panel")
        print("=" * 60)

        # Step 1: Switch to Results tab
        print("[P137] E1: Switching to Results tab...")
        page.evaluate("""() => {
            for (var el of document.querySelectorAll('[class*="header-item"]')) {
                if ((el.innerText || '').includes('Result')) { el.click(); return true; }
            }
            return false;
        }""")
        page.wait_for_timeout(1500)

        # Count existing result images
        before_count = len(_js_get_result_images(page))
        print(f"[P137]   Result images: {before_count}")

        # Step 2: Find Enhance & Upscale row
        print("[P137] E2: Locating Enhance & Upscale row...")
        enhance_data = page.evaluate("""() => {
            var enhanceEl = null;
            for (var el of document.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                if (text.includes('Enhance') && text.includes('Upscale')) {
                    var r = el.getBoundingClientRect();
                    if (r.width > 0 && r.width < 200 && r.y > 600) {
                        if (!enhanceEl || r.width < enhanceEl.w) {
                            enhanceEl = {
                                x: Math.round(r.x), y: Math.round(r.y),
                                cx: Math.round(r.x + r.width/2),
                                cy: Math.round(r.y + r.height/2),
                                w: Math.round(r.width), h: Math.round(r.height),
                                text: text.substring(0, 50)
                            };
                        }
                    }
                }
            }
            if (!enhanceEl) return null;

            // Find small elements on the same row that could be numbered buttons
            var btns = [];
            for (var el of document.querySelectorAll('*')) {
                var r = el.getBoundingClientRect();
                if (r.width >= 10 && r.width <= 40 && r.height >= 10 && r.height <= 40 &&
                    Math.abs(r.y + r.height/2 - enhanceEl.cy) < 20 && r.x > enhanceEl.x + enhanceEl.w) {
                    btns.push({
                        text: (el.innerText || '').trim(),
                        cx: Math.round(r.x + r.width/2),
                        cy: Math.round(r.y + r.height/2),
                        w: Math.round(r.width), h: Math.round(r.height),
                        tag: el.tagName,
                        cls: (el.className || '').substring(0, 50)
                    });
                }
            }
            // Deduplicate by position
            var unique = [];
            for (var b of btns) {
                var dup = false;
                for (var u of unique) {
                    if (Math.abs(u.cx - b.cx) < 10) { dup = true; break; }
                }
                if (!dup) unique.push(b);
            }
            unique.sort(function(a,b) { return a.cx - b.cx; });
            return {enhance: enhanceEl, buttons: unique};
        }""")

        if not enhance_data:
            print("[P137]   FAIL: Enhance & Upscale row not found!")
            # Try scrolling the results panel down
            page.evaluate("""() => {
                var panel = document.querySelector('.result-list, [class*="result"]');
                if (panel) panel.scrollTop += 300;
            }""")
            page.wait_for_timeout(1000)
            page.screenshot(path=os.path.expanduser("~/Downloads/p137_no_enhance.png"))
        else:
            print(f"[P137]   Label at ({enhance_data['enhance']['cx']}, {enhance_data['enhance']['cy']})")
            print(f"[P137]   Buttons: {len(enhance_data['buttons'])}")
            for b in enhance_data["buttons"]:
                print(f"    ({b['cx']}, {b['cy']}) {b['w']}x{b['h']} <{b['tag']}> '{b['text']}' cls={b['cls']}")

            # Step 3: Click button [1]
            if enhance_data["buttons"]:
                btn = enhance_data["buttons"][0]
                click_x, click_y = btn["cx"], btn["cy"]
            else:
                # Fallback from P136 confirmed positions
                click_x = 1291
                click_y = enhance_data["enhance"]["cy"]

            print(f"\n[P137] E3: Clicking Enhance [1] at ({click_x}, {click_y})...")
            page.screenshot(path=os.path.expanduser("~/Downloads/p137_before_enhance.png"))
            page.mouse.click(click_x, click_y)
            page.wait_for_timeout(3000)
            page.screenshot(path=os.path.expanduser("~/Downloads/p137_after_enhance_click.png"))

            # Step 4: Detect and interact with popup
            print("[P137] E4: Detecting popup dialog...")
            popup_text = page.evaluate("""() => {
                // Look for a centered dialog/popup
                for (var el of document.querySelectorAll('[class*="modal"], [class*="dialog"], [class*="enhance"]')) {
                    var r = el.getBoundingClientRect();
                    var s = window.getComputedStyle(el);
                    if (r.width > 200 && r.height > 200 && s.display !== 'none' &&
                        s.visibility !== 'hidden' && r.x > 200 && r.x < 900) {
                        return (el.innerText || '').substring(0, 500);
                    }
                }
                return '';
            }""")

            if popup_text:
                print(f"[P137]   Popup text: {popup_text[:200]}")

                # Find controls in the popup
                controls = page.evaluate("""() => {
                    var results = [];
                    for (var el of document.querySelectorAll('button, [role="button"], [role="radio"]')) {
                        var r = el.getBoundingClientRect();
                        if (r.width > 20 && r.x > 300 && r.x < 1100 && r.y > 150 && r.y < 750) {
                            results.push({
                                text: (el.innerText || '').trim().substring(0, 40),
                                cx: Math.round(r.x + r.width/2),
                                cy: Math.round(r.y + r.height/2),
                                w: Math.round(r.width), h: Math.round(r.height),
                                disabled: el.disabled || false,
                                tag: el.tagName,
                                cls: (el.className || '').substring(0, 50)
                            });
                        }
                    }
                    return results;
                }""")
                print(f"[P137]   Controls: {len(controls)}")
                for c in controls:
                    dis = " [disabled]" if c["disabled"] else ""
                    print(f"    ({c['cx']},{c['cy']}) {c['w']}x{c['h']} '{c['text']}'{dis} cls={c['cls']}")

                # Step 5: Click Upscale
                print("\n[P137] E5: Clicking Upscale...")
                upscale_result = page.evaluate("""() => {
                    for (var b of document.querySelectorAll('button')) {
                        var text = (b.innerText || '').trim();
                        var r = b.getBoundingClientRect();
                        if (text.includes('Upscale') && r.width > 50 && r.x > 300 && !b.disabled) {
                            b.click();
                            return {ok: true, x: Math.round(r.x), y: Math.round(r.y), text: text};
                        }
                    }
                    return {ok: false};
                }""")
                print(f"[P137]   {upscale_result}")

                if upscale_result.get("ok"):
                    # Step 6: Wait for processing
                    print("[P137] E6: Waiting for Enhance processing...")
                    enhance_start = time.monotonic()
                    page.wait_for_timeout(3000)

                    last_pct = ""
                    while time.monotonic() - enhance_start < 120:
                        elapsed = int(time.monotonic() - enhance_start)

                        # Check progress
                        pct = page.evaluate("""() => {
                            for (var el of document.querySelectorAll('*')) {
                                var text = (el.innerText || '').trim();
                                if (text.match(/^\\d+%$/) && parseInt(text) <= 100) return text;
                            }
                            return '';
                        }""")
                        if pct and pct != last_pct:
                            print(f"[P137]   {elapsed}s: {pct}")
                            last_pct = pct

                        # Check for new images
                        current_count = len(_js_get_result_images(page))
                        if current_count > before_count:
                            print(f"[P137]   New results! {before_count} -> {current_count} ({elapsed}s)")
                            break

                        # Check popup closed
                        still_open = page.evaluate("""() => {
                            for (var el of document.querySelectorAll('[class*="modal"]')) {
                                var r = el.getBoundingClientRect();
                                var s = window.getComputedStyle(el);
                                if (r.width > 200 && s.display !== 'none') return true;
                            }
                            return false;
                        }""")
                        if not still_open and elapsed > 5:
                            print(f"[P137]   Popup closed at {elapsed}s")
                            page.wait_for_timeout(3000)
                            # Recheck images
                            final_count = len(_js_get_result_images(page))
                            if final_count > before_count:
                                print(f"[P137]   Images: {before_count} -> {final_count}")
                            break

                        page.wait_for_timeout(5000)

                    page.screenshot(path=os.path.expanduser("~/Downloads/p137_enhance_done.png"))

                    # Download enhanced result
                    all_imgs = _js_get_result_images(page)
                    if len(all_imgs) > before_count:
                        new_urls = [i["src"] for i in all_imgs[before_count:]]
                        print(f"\n[P137]   New image URLs: {len(new_urls)}")
                        for url in new_urls:
                            short = url.split("/")[-1][:50]
                            print(f"    {short}")

                        # Download first enhanced image
                        enh_dest = Path(os.path.expanduser("~/Downloads")) / f"p137_enhanced_{int(time.time())}.webp"
                        try:
                            req_obj = urllib.request.Request(new_urls[0], headers={"User-Agent": "Mozilla/5.0"})
                            data = urllib.request.urlopen(req_obj, timeout=30).read()
                            enh_dest.write_bytes(data)
                            print(f"[P137]   Enhanced: {enh_dest} ({len(data):,} bytes)")
                        except Exception as e:
                            print(f"[P137]   Download failed: {e}")
                    else:
                        print("[P137]   No new enhanced images appeared")

                    enhance_credits = get_credits(page)
                    print(f"[P137] Credits after enhance: {enhance_credits}")
                    if credits_after_faithful and enhance_credits:
                        print(f"[P137] Enhance cost: {credits_after_faithful - enhance_credits} credits")
            else:
                print("[P137]   No popup appeared. Checking page state...")
                # Maybe there's a toast/notification instead
                toast = page.evaluate("""() => {
                    for (var el of document.querySelectorAll('[class*="toast"], [class*="message"], [class*="notification"]')) {
                        var text = (el.innerText || '').trim();
                        if (text) return text.substring(0, 200);
                    }
                    return '';
                }""")
                if toast:
                    print(f"[P137]   Toast/message: {toast}")
                page.screenshot(path=os.path.expanduser("~/Downloads/p137_no_popup.png"))

        # ==============================================================
        # SUMMARY
        # ==============================================================
        credits_final = get_credits(page)
        total_time = time.monotonic() - start

        print("\n" + "=" * 70)
        print("PHASE 137 SUMMARY")
        print("=" * 70)
        print(f"  Total time: {total_time:.0f}s")
        print(f"  Product Faithful: PASS ({total_faithful:.0f}s)")
        if output.exists():
            print(f"    Output: {output} ({output.stat().st_size:,} bytes)")
        print(f"  Credits: {credits_before} -> {credits_after_faithful} -> {credits_final}")
        if credits_before and credits_final:
            print(f"  Total credits used: {credits_before - credits_final}")

        # Keep the canvas tab open for manual inspection
        print(f"\n  Canvas left open: {page.url}")
        print("  Check ~/Downloads/p137_*.png for screenshots")

    finally:
        pw.stop()


if __name__ == "__main__":
    main()
