#!/usr/bin/env python3
"""Phase 146: AI Video — Wait for completion and download (fixed JS)."""

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
    from tools.lib.dzine_browser import close_all_dialogs, VIEWPORT

    print("=" * 70)
    print("PHASE 146: AI Video — Wait & Download (fixed)")
    print("=" * 70)

    if not is_browser_running():
        print("[P146] ERROR: Brave not running.")
        return

    pw = sync_playwright().start()
    try:
        browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{DEFAULT_CDP_PORT}")
        context = browser.contexts[0]

        dzine_pages = [p for p in context.pages if "dzine.ai/canvas" in (p.url or "")]
        if not dzine_pages:
            print("[P146] No Dzine canvas found.")
            return

        page = dzine_pages[0]
        page.set_viewport_size(VIEWPORT)
        page.bring_to_front()
        page.wait_for_timeout(1500)
        print(f"[P146] Canvas: {page.url}")

        close_all_dialogs(page)
        page.wait_for_timeout(500)

        # Scroll results to top
        page.evaluate("""() => {
            for (var el of document.querySelectorAll('[class*="header-item"]')) {
                if ((el.innerText || '').includes('Result')) { el.click(); return; }
            }
        }""")
        page.wait_for_timeout(500)
        page.evaluate("""() => {
            for (var el of document.querySelectorAll('*')) {
                var s = window.getComputedStyle(el);
                if ((s.overflowY === 'auto' || s.overflowY === 'scroll') &&
                    el.scrollHeight > el.clientHeight + 50 &&
                    el.getBoundingClientRect().x > 1000) {
                    el.scrollTop = 0;
                    return true;
                }
            }
            return false;
        }""")
        page.wait_for_timeout(1000)

        # Poll for completion
        print("\n[1] Polling for video completion...")
        poll_start = time.monotonic()

        while time.monotonic() - poll_start < 600:
            elapsed = int(time.monotonic() - poll_start)

            status = page.evaluate("""() => {
                for (var el of document.querySelectorAll('.result-item.image-to-video-result')) {
                    var text = (el.innerText || '').trim();

                    // Check for video element inside this result
                    for (var v of el.querySelectorAll('video')) {
                        var r = v.getBoundingClientRect();
                        if (r.width > 50) {
                            var src = v.src || '';
                            var source = v.querySelector('source');
                            if (source) src = source.src || src;
                            if (src && src.indexOf('/guide/') === -1) {
                                return {done: true, src: src};
                            }
                        }
                    }

                    // Check for waiting text
                    if (text.indexOf('Waiting') !== -1 || text.indexOf('Starting') !== -1) {
                        return {done: false, status: 'waiting'};
                    }

                    // Check if the text has changed (no more Waiting)
                    if (text.indexOf('Lip Sync') !== -1 && text.indexOf('Waiting') === -1 &&
                        text.indexOf('Starting') === -1) {
                        return {done: true, status: 'probably_done', text: text.substring(0, 200)};
                    }

                    return {done: false, status: 'unknown', text: text.substring(0, 200)};
                }
                return {done: false, status: 'no_result_item'};
            }""")

            if status.get('done'):
                print(f"\n[1] DONE at {elapsed}s: {status}")
                break

            if elapsed % 30 == 0:
                print(f"[1]   {elapsed}s: {status.get('status', 'unknown')}")

            if elapsed > 0 and elapsed % 120 == 0:
                page.screenshot(path=os.path.expanduser(f"~/Downloads/p146_{elapsed}s.png"))

            page.wait_for_timeout(15000)

        page.screenshot(path=os.path.expanduser("~/Downloads/p146_done.png"))

        # Step 2: Find video URL
        print("\n[2] Finding video URL...")

        # Method A: video element in the result item
        video_url = page.evaluate("""() => {
            for (var el of document.querySelectorAll('.result-item.image-to-video-result')) {
                for (var v of el.querySelectorAll('video')) {
                    var r = v.getBoundingClientRect();
                    if (r.width > 20) {
                        var src = v.src || '';
                        var source = v.querySelector('source');
                        if (source) src = source.src || src;
                        if (src && src.indexOf('/guide/') === -1) return src;
                    }
                }
            }
            return null;
        }""")
        print(f"[2a] Video element src: {video_url}")

        # Method B: search HTML for mp4 URLs
        if not video_url:
            video_url = page.evaluate("""() => {
                for (var el of document.querySelectorAll('.result-item.image-to-video-result')) {
                    var html = el.innerHTML;
                    var match = html.match(/https?:[^"'\\s]+[.]mp4[^"'\\s]*/);
                    if (match && match[0].indexOf('/guide/') === -1) return match[0];
                }
                return null;
            }""")
            print(f"[2b] HTML regex src: {video_url}")

        # Method C: click the result to open preview, then check for video
        if not video_url:
            print("[2c] Clicking result item to open preview...")
            page.evaluate("""() => {
                for (var el of document.querySelectorAll('.result-item.image-to-video-result .result-preview-img, .result-item.image-to-video-result img')) {
                    var r = el.getBoundingClientRect();
                    if (r.width > 50) { el.click(); return true; }
                }
                // Click the result item itself
                for (var el of document.querySelectorAll('.result-item.image-to-video-result')) {
                    el.click();
                    return true;
                }
                return false;
            }""")
            page.wait_for_timeout(3000)
            page.screenshot(path=os.path.expanduser("~/Downloads/p146_preview.png"))

            video_url = page.evaluate("""() => {
                // Check result preview area
                for (var v of document.querySelectorAll('#result-preview video, .result-preview video')) {
                    var src = v.src || '';
                    var source = v.querySelector('source');
                    if (source) src = source.src || src;
                    if (src && src.indexOf('/guide/') === -1) return src;
                }
                // Any large centered video
                for (var v of document.querySelectorAll('video')) {
                    var r = v.getBoundingClientRect();
                    if (r.width > 200 && r.x > 200 && r.x < 800) {
                        var src = v.src || '';
                        var source = v.querySelector('source');
                        if (source) src = source.src || src;
                        if (src && src.indexOf('/guide/') === -1) return src;
                    }
                }
                return null;
            }""")
            print(f"[2c] Preview video src: {video_url}")

        # Method D: Look for download button and try to get the URL
        if not video_url:
            print("[2d] Looking for download button...")
            download_info = page.evaluate("""() => {
                for (var el of document.querySelectorAll('.result-item.image-to-video-result .download, .result-item.image-to-video-result [class*="download"]')) {
                    var r = el.getBoundingClientRect();
                    if (r.width > 0) {
                        return {
                            x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height),
                            tag: el.tagName,
                            href: el.href || el.getAttribute('data-url') || '',
                            cls: (el.className || '').substring(0, 50)
                        };
                    }
                }
                return null;
            }""")
            print(f"[2d] Download button: {download_info}")

            if download_info:
                # Try clicking it with download interception
                print("[2d] Clicking download button...")
                try:
                    with page.expect_download(timeout=10000) as dl_info:
                        page.mouse.click(download_info['x'] + download_info['w']//2,
                                        download_info['y'] + download_info['h']//2)
                    dl = dl_info.value
                    dest = Path(os.path.expanduser("~/Downloads")) / f"p146_video_{int(time.time())}.mp4"
                    dl.save_as(str(dest))
                    print(f"[2d] Downloaded via button: {dest}")
                    print(f"     Size: {dest.stat().st_size:,} bytes")
                except Exception as e:
                    print(f"[2d] Download intercept failed: {e}")

        # Step 3: Download via URL if found
        if video_url:
            print(f"\n[3] Downloading: {video_url[:200]}")
            dest = Path(os.path.expanduser("~/Downloads")) / f"p146_video_{int(time.time())}.mp4"
            try:
                req = urllib.request.Request(video_url, headers={"User-Agent": "Mozilla/5.0"})
                data = urllib.request.urlopen(req, timeout=120).read()
                dest.write_bytes(data)
                print(f"[3] Saved: {dest} ({len(data):,} bytes = {len(data)/1024/1024:.1f} MB)")
            except Exception as e:
                print(f"[3] Download error: {e}")

        # Step 4: Document the result item structure
        print("\n[4] Video result item details...")
        details = page.evaluate("""() => {
            for (var el of document.querySelectorAll('.result-item.image-to-video-result')) {
                var children = [];
                function walk(node, depth) {
                    if (depth > 3) return;
                    for (var child of node.children) {
                        var r = child.getBoundingClientRect();
                        var text = '';
                        if (child.childElementCount === 0) text = (child.innerText || '').trim();
                        if (r.width > 0) {
                            children.push({
                                depth: depth,
                                tag: child.tagName,
                                cls: (child.className || '').substring(0, 40),
                                text: text.substring(0, 80),
                                x: Math.round(r.x), y: Math.round(r.y),
                                w: Math.round(r.width), h: Math.round(r.height)
                            });
                        }
                        walk(child, depth + 1);
                    }
                }
                walk(el, 0);
                return children;
            }
            return [];
        }""")
        print(f"[4] DOM tree: {len(details)} elements")
        for d in details[:30]:
            indent = "  " * d['depth']
            text_info = f" '{d['text']}'" if d['text'] else ""
            print(f"  {indent}<{d['tag']}> cls={d['cls'][:30]} ({d['x']},{d['y']}) {d['w']}x{d['h']}{text_info}")

        # Credits
        credits = page.evaluate("""() => {
            for (var el of document.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                if (text.match(/^[\\d.]+$/) && parseFloat(text) > 0 && parseFloat(text) < 100) {
                    var r = el.getBoundingClientRect();
                    if (r.y < 50 && r.x > 1050 && r.x < 1200) return text;
                }
            }
            return 'unknown';
        }""")
        print(f"\n[5] Credits: {credits}")

        page.screenshot(path=os.path.expanduser("~/Downloads/p146_final.png"), full_page=True)

        print("\n" + "=" * 70)
        print("PHASE 146 SUMMARY")
        print("=" * 70)

    finally:
        pw.stop()


if __name__ == "__main__":
    main()
