#!/usr/bin/env python3
"""Phase 145: AI Video — Poll for completion and download result.

From P144:
- Wan 2.1 generation triggered, "Waiting for 5-10 mins"
- Result item appeared as .result-item.image-to-video-result at (1108, -806)
- Credits 8.856 -> 8.850 (partial deduction)

Goals:
1. Poll the results panel for video completion
2. Find the video URL (mp4 or similar)
3. Download the generated video
4. Document quality, size, duration
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
    from tools.lib.dzine_browser import close_all_dialogs, VIEWPORT

    print("=" * 70)
    print("PHASE 145: AI Video — Poll & Download")
    print("=" * 70)

    if not is_browser_running():
        print("[P145] ERROR: Brave not running.")
        return

    pw = sync_playwright().start()
    try:
        browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{DEFAULT_CDP_PORT}")
        context = browser.contexts[0]

        dzine_pages = [p for p in context.pages if "dzine.ai/canvas" in (p.url or "")]
        if not dzine_pages:
            print("[P145] No Dzine canvas found.")
            return

        page = dzine_pages[0]
        page.set_viewport_size(VIEWPORT)
        page.bring_to_front()
        page.wait_for_timeout(1500)
        print(f"[P145] Canvas: {page.url}")

        close_all_dialogs(page)
        page.wait_for_timeout(500)

        # Switch to Results tab
        page.evaluate("""() => {
            for (var el of document.querySelectorAll('[class*="header-item"]')) {
                if ((el.innerText || '').includes('Result')) { el.click(); return; }
            }
        }""")
        page.wait_for_timeout(1000)

        # Step 1: Check current video result status
        print("\n[1] Checking video result status...")

        video_results = page.evaluate("""() => {
            var items = [];
            for (var el of document.querySelectorAll('.result-item, [class*="video-result"]')) {
                var text = (el.innerText || '').trim();
                if (text.includes('Video') || text.includes('video') || el.className.includes('video')) {
                    var r = el.getBoundingClientRect();
                    items.push({
                        text: text.substring(0, 300),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        cls: (el.className || '').substring(0, 80)
                    });
                }
            }
            return items;
        }""")

        print(f"[1] Video results: {len(video_results)}")
        for v in video_results:
            print(f"  ({v['x']},{v['y']}) {v['w']}x{v['h']} cls={v['cls'][:50]}")
            lines = v['text'].split('\n')
            for line in lines[:5]:
                if line.strip():
                    print(f"    {line.strip()[:80]}")

        # Step 2: Scroll the results panel to top to see the video result
        print("\n[2] Scrolling results panel to top...")
        page.evaluate("""() => {
            var panel = document.querySelector('.result-panel') ||
                        document.querySelector('[class*="result-content"]') ||
                        document.querySelector('.c-result');
            if (panel) {
                panel.scrollTop = 0;
                return true;
            }
            // Try scrolling the main result area
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

        page.screenshot(path=os.path.expanduser("~/Downloads/p145_results_top.png"))

        # Step 3: Check if video is still processing or done
        print("\n[3] Checking processing status...")
        processing = page.evaluate("""() => {
            for (var el of document.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                if (text.includes('Waiting') || text.includes('Processing') ||
                    text.includes('Generating') || text.includes('Queue')) {
                    var r = el.getBoundingClientRect();
                    if (r.x > 1000 && r.width > 0) {
                        return {status: 'processing', text: text.substring(0, 100),
                                x: Math.round(r.x), y: Math.round(r.y)};
                    }
                }
            }
            // Check for completed video
            for (var el of document.querySelectorAll('video')) {
                var r = el.getBoundingClientRect();
                if (r.width > 0 && r.x > 1000) {
                    return {status: 'complete', src: (el.src || '').substring(0, 300),
                            poster: (el.poster || '').substring(0, 200),
                            x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height)};
                }
            }
            return null;
        }""")
        print(f"[3] Status: {processing}")

        # Step 4: Poll until done
        if processing and processing.get('status') == 'processing':
            print("\n[4] Video still processing. Polling...")
            poll_start = time.monotonic()

            while time.monotonic() - poll_start < 600:  # 10 min max
                elapsed = int(time.monotonic() - poll_start)

                status = page.evaluate("""() => {
                    // Check for video element
                    for (var el of document.querySelectorAll('video')) {
                        var r = el.getBoundingClientRect();
                        if (r.width > 50 && r.x > 900) {
                            return {done: true, src: (el.src || '').substring(0, 300),
                                    poster: (el.poster || '').substring(0, 200),
                                    x: Math.round(r.x), y: Math.round(r.y),
                                    w: Math.round(r.width), h: Math.round(r.height)};
                        }
                    }
                    // Check for mp4 sources
                    for (var el of document.querySelectorAll('source[type*="video"], [src*=".mp4"]')) {
                        return {done: true, src: (el.src || '').substring(0, 300)};
                    }
                    // Check waiting text
                    for (var el of document.querySelectorAll('.result-item *')) {
                        var text = (el.innerText || '').trim();
                        if (text.includes('Waiting') || text.includes('mins')) {
                            return {done: false, text: text.substring(0, 80)};
                        }
                    }
                    // Check for percentage progress
                    for (var el of document.querySelectorAll('.result-item *')) {
                        var text = (el.innerText || '').trim();
                        if (text.match(/^\d{1,3}%$/)) {
                            return {done: false, progress: text};
                        }
                    }
                    return {done: false, text: 'unknown'};
                }""")

                if status.get('done'):
                    print(f"\n[4] VIDEO COMPLETE at {elapsed}s!")
                    print(f"[4] {status}")
                    break

                if elapsed % 30 == 0:
                    msg = status.get('progress') or status.get('text', 'waiting')
                    print(f"[4]   {elapsed}s: {msg}")

                if elapsed > 0 and elapsed % 60 == 0:
                    page.screenshot(path=os.path.expanduser(f"~/Downloads/p145_{elapsed}s.png"))

                page.wait_for_timeout(10000)

        # Step 5: Find and download the video
        print("\n[5] Looking for video URL...")
        video_info = page.evaluate("""() => {
            // Method 1: video element
            for (var v of document.querySelectorAll('video')) {
                var r = v.getBoundingClientRect();
                if (r.width > 50) {
                    var src = v.src || '';
                    if (!src) {
                        var source = v.querySelector('source');
                        if (source) src = source.src;
                    }
                    return {
                        method: 'video_element',
                        src: src,
                        poster: v.poster || '',
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height)
                    };
                }
            }
            // Method 2: Check for download buttons in video result
            for (var el of document.querySelectorAll('.result-item.image-to-video-result button, .result-item [class*="download"]')) {
                var text = (el.innerText || '').trim();
                var r = el.getBoundingClientRect();
                if (r.width > 0 && (text.includes('Download') || el.className.includes('download'))) {
                    return {
                        method: 'download_button',
                        text: text.substring(0, 50),
                        x: Math.round(r.x), y: Math.round(r.y),
                        cls: (el.className || '').substring(0, 50)
                    };
                }
            }
            // Method 3: Look for any .mp4 URLs in page
            var all = document.documentElement.innerHTML;
            var mp4s = all.match(/https?:\/\/[^"'\s]+\.mp4[^"'\s]*/g);
            if (mp4s) {
                return {method: 'regex', urls: mp4s.map(u => u.substring(0, 300))};
            }
            return null;
        }""")
        print(f"[5] Video info: {video_info}")

        if video_info and video_info.get('src'):
            video_url = video_info['src']
            print(f"\n[6] Downloading video from: {video_url[:150]}")
            dest = Path(os.path.expanduser("~/Downloads")) / f"p145_video_{int(time.time())}.mp4"
            try:
                req = urllib.request.Request(video_url, headers={"User-Agent": "Mozilla/5.0"})
                data = urllib.request.urlopen(req, timeout=60).read()
                dest.write_bytes(data)
                print(f"[6] Downloaded: {dest} ({len(data):,} bytes)")
            except Exception as e:
                print(f"[6] Download error: {e}")
        elif video_info and video_info.get('method') == 'regex':
            print(f"\n[6] Found MP4 URLs via regex:")
            for url in video_info['urls'][:5]:
                print(f"  {url[:150]}")
            # Try downloading the first one
            if video_info['urls']:
                video_url = video_info['urls'][0]
                dest = Path(os.path.expanduser("~/Downloads")) / f"p145_video_{int(time.time())}.mp4"
                try:
                    req = urllib.request.Request(video_url, headers={"User-Agent": "Mozilla/5.0"})
                    data = urllib.request.urlopen(req, timeout=60).read()
                    dest.write_bytes(data)
                    print(f"[6] Downloaded: {dest} ({len(data):,} bytes)")
                except Exception as e:
                    print(f"[6] Download error: {e}")

        # Credits after
        credits_final = page.evaluate("""() => {
            for (var el of document.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                var match = text.match(/([\d.]+)\\s*video credits/);
                if (match) return parseFloat(match[1]);
            }
            return -1;
        }""")
        print(f"\n[7] Final credits: {credits_final}")

        page.screenshot(path=os.path.expanduser("~/Downloads/p145_final.png"))

        print("\n" + "=" * 70)
        print("PHASE 145 SUMMARY")
        print("=" * 70)
        print("  Check ~/Downloads/p145_*.png for screenshots")

    finally:
        pw.stop()


if __name__ == "__main__":
    main()
