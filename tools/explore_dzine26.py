"""Phase 26: Deep explore remaining tools + CC result interaction.

Goals:
1. Map CC result action buttons precisely (Variation, Expression Edit, etc.)
2. Click variant selectors (1/2) on CC results
3. Explore Motion Control panel
4. Explore Video Editor panel
5. Explore Instant Storyboard panel
6. Test image export/download from canvas
"""

import json
import os
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from playwright.sync_api import sync_playwright

CANVAS_URL = "https://www.dzine.ai/canvas?id=19797967"
SS_DIR = Path(__file__).resolve().parent.parent / "artifacts" / "dzine_explore"
SS_DIR.mkdir(parents=True, exist_ok=True)

def ss(page, name):
    page.screenshot(path=str(SS_DIR / f"{name}.png"))
    print(f"  SS: {name}", flush=True)

def close_dialogs(page):
    for _ in range(6):
        found = False
        for text in ["Not now", "Close", "Never show again", "Got it", "Skip", "Later"]:
            try:
                btn = page.locator(f'button:has-text("{text}")')
                if btn.count() > 0 and btn.first.is_visible(timeout=500):
                    btn.first.click()
                    page.wait_for_timeout(500)
                    found = True
            except Exception:
                pass
        if not found:
            break


def main():
    print("Connecting...", flush=True)
    pw = sync_playwright().start()
    browser = pw.chromium.connect_over_cdp("http://127.0.0.1:18800", timeout=15000)
    ctx = browser.contexts[0]
    page = ctx.new_page()
    page.set_viewport_size({"width": 1440, "height": 900})

    page.goto(CANVAS_URL, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(3000)
    close_dialogs(page)

    # ============================================================
    #  PART 1: MAP CC RESULT ACTIONS IN RESULTS PANEL
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 1: MAP CC RESULT ACTIONS", flush=True)
    print("=" * 60, flush=True)

    # Make sure Results tab is active
    page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            if ((el.innerText || '').trim() === 'Results' && el.getBoundingClientRect().x > 1050) {
                el.click(); return true;
            }
        }
        return false;
    }""")
    page.wait_for_timeout(1000)

    # Map ALL elements in results panel area (x > 550)
    results_panel = page.evaluate("""() => {
        const items = [];
        for (const el of document.querySelectorAll('*')) {
            const r = el.getBoundingClientRect();
            const text = (el.innerText || '').trim();
            if (r.x > 550 && r.x < 1440 && r.y > 50 && r.y < 900
                && r.width > 10 && r.width < 400 && r.height > 8 && r.height < 50
                && text && text.length > 0 && text.length < 80
                && !text.includes('\\n')) {
                items.push({
                    text: text,
                    tag: el.tagName,
                    x: Math.round(r.x),
                    y: Math.round(r.y),
                    w: Math.round(r.width),
                    h: Math.round(r.height),
                    clickable: el.tagName === 'BUTTON' || el.tagName === 'A'
                              || el.style.cursor === 'pointer'
                              || el.closest('button') !== null,
                });
            }
        }
        const seen = new Set();
        return items.filter(i => {
            const key = i.text + '|' + Math.round(i.y / 5);
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
        }).sort((a, b) => a.y - b.y);
    }""")

    print(f"\n  Results panel elements ({len(results_panel)}):", flush=True)
    for el in results_panel[:50]:
        click = " [CLICK]" if el.get("clickable") else ""
        print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> '{el['text']}'{click}", flush=True)

    ss(page, "P26_01_results_panel")

    # ============================================================
    #  PART 2: FIND ALL IMAGES IN RESULTS (with detailed info)
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 2: ALL RESULT IMAGES (detailed)", flush=True)
    print("=" * 60, flush=True)

    result_images = page.evaluate("""() => {
        const imgs = [];
        for (const img of document.querySelectorAll('img')) {
            const src = img.src || '';
            const r = img.getBoundingClientRect();
            if (src.includes('static.dzine.ai') && r.width > 20) {
                imgs.push({
                    src: src.substring(0, 120),
                    x: Math.round(r.x),
                    y: Math.round(r.y),
                    w: Math.round(r.width),
                    h: Math.round(r.height),
                    inResults: r.x > 550,
                });
            }
        }
        return imgs.sort((a, b) => a.y - b.y);
    }""")

    print(f"\n  Total result images: {len(result_images)}", flush=True)
    for img in result_images:
        loc = "RESULTS" if img["inResults"] else "CANVAS"
        print(f"    [{loc}] ({img['x']},{img['y']}) {img['w']}x{img['h']} {img['src']}", flush=True)

    # ============================================================
    #  PART 3: CLICK CC RESULT TO PLACE ON CANVAS + GET URL
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 3: CLICK CC RESULT IMAGE", flush=True)
    print("=" * 60, flush=True)

    # Find the first CC result image (in results panel)
    cc_results = [img for img in result_images if img["inResults"] and img["w"] > 50]
    if cc_results:
        first_cc = cc_results[0]
        print(f"\n  Clicking first CC result at ({first_cc['x']},{first_cc['y']})", flush=True)
        page.mouse.click(first_cc['x'] + first_cc['w'] // 2, first_cc['y'] + first_cc['h'] // 2)
        page.wait_for_timeout(2000)

        # Check canvas for placed image
        canvas_imgs = page.evaluate("""() => {
            const imgs = [];
            for (const img of document.querySelectorAll('img')) {
                const src = img.src || '';
                const r = img.getBoundingClientRect();
                if (src.includes('static.dzine.ai') && r.x > 60 && r.x < 550 && r.width > 100) {
                    imgs.push({
                        src: src,
                        x: Math.round(r.x),
                        y: Math.round(r.y),
                        w: Math.round(r.width),
                        h: Math.round(r.height),
                    });
                }
            }
            return imgs;
        }""")
        print(f"  Canvas images after click: {len(canvas_imgs)}", flush=True)
        for ci in canvas_imgs[:3]:
            print(f"    ({ci['x']},{ci['y']}) {ci['w']}x{ci['h']} {ci['src'][:100]}", flush=True)

        ss(page, "P26_02_cc_on_canvas")
    else:
        print("  No CC results found in results panel", flush=True)

    # ============================================================
    #  PART 4: MOTION CONTROL PANEL
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 4: MOTION CONTROL PANEL", flush=True)
    print("=" * 60, flush=True)

    page.mouse.click(40, 550)  # Motion Control sidebar
    page.wait_for_timeout(2000)
    close_dialogs(page)

    ss(page, "P26_03_motion_control")

    motion = page.evaluate("""() => {
        const items = [];
        for (const el of document.querySelectorAll('*')) {
            const r = el.getBoundingClientRect();
            const text = (el.innerText || '').trim();
            if (r.x > 60 && r.x < 400 && r.y > 50 && r.y < 900
                && r.width > 15 && r.width < 350 && text
                && text.length > 0 && text.length < 80
                && !text.includes('\\n')) {
                items.push({
                    text: text,
                    tag: el.tagName,
                    x: Math.round(r.x),
                    y: Math.round(r.y),
                    w: Math.round(r.width),
                });
            }
        }
        const seen = new Set();
        return items.filter(i => {
            const key = i.text + '|' + Math.round(i.y / 3);
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
        }).sort((a, b) => a.y - b.y);
    }""")

    print(f"\n  Motion Control panel ({len(motion)}):", flush=True)
    for el in motion[:30]:
        print(f"    ({el['x']},{el['y']}) w={el['w']} <{el['tag']}> '{el['text']}'", flush=True)

    # ============================================================
    #  PART 5: VIDEO EDITOR PANEL
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 5: VIDEO EDITOR PANEL", flush=True)
    print("=" * 60, flush=True)

    page.mouse.click(40, 490)  # Video Editor sidebar
    page.wait_for_timeout(2000)
    close_dialogs(page)

    ss(page, "P26_04_video_editor")

    video_ed = page.evaluate("""() => {
        const items = [];
        for (const el of document.querySelectorAll('*')) {
            const r = el.getBoundingClientRect();
            const text = (el.innerText || '').trim();
            if (r.x > 60 && r.x < 400 && r.y > 50 && r.y < 900
                && r.width > 15 && r.width < 350 && text
                && text.length > 0 && text.length < 80
                && !text.includes('\\n')) {
                items.push({
                    text: text,
                    tag: el.tagName,
                    x: Math.round(r.x),
                    y: Math.round(r.y),
                    w: Math.round(r.width),
                });
            }
        }
        const seen = new Set();
        return items.filter(i => {
            const key = i.text + '|' + Math.round(i.y / 3);
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
        }).sort((a, b) => a.y - b.y);
    }""")

    print(f"\n  Video Editor panel ({len(video_ed)}):", flush=True)
    for el in video_ed[:30]:
        print(f"    ({el['x']},{el['y']}) w={el['w']} <{el['tag']}> '{el['text']}'", flush=True)

    # ============================================================
    #  PART 6: INSTANT STORYBOARD PANEL
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 6: INSTANT STORYBOARD PANEL", flush=True)
    print("=" * 60, flush=True)

    page.mouse.click(40, 766)  # Instant Storyboard sidebar
    page.wait_for_timeout(2000)
    close_dialogs(page)

    ss(page, "P26_05_storyboard")

    storyboard = page.evaluate("""() => {
        const items = [];
        for (const el of document.querySelectorAll('*')) {
            const r = el.getBoundingClientRect();
            const text = (el.innerText || '').trim();
            if (r.x > 60 && r.x < 400 && r.y > 50 && r.y < 900
                && r.width > 15 && r.width < 350 && text
                && text.length > 0 && text.length < 80
                && !text.includes('\\n')) {
                items.push({
                    text: text,
                    tag: el.tagName,
                    x: Math.round(r.x),
                    y: Math.round(r.y),
                    w: Math.round(r.width),
                });
            }
        }
        const seen = new Set();
        return items.filter(i => {
            const key = i.text + '|' + Math.round(i.y / 3);
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
        }).sort((a, b) => a.y - b.y);
    }""")

    print(f"\n  Instant Storyboard panel ({len(storyboard)}):", flush=True)
    for el in storyboard[:30]:
        print(f"    ({el['x']},{el['y']}) w={el['w']} <{el['tag']}> '{el['text']}'", flush=True)

    # ============================================================
    #  PART 7: TOP BAR EXPORT + CANVAS SIZE CONTROLS
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 7: TOP BAR / EXPORT", flush=True)
    print("=" * 60, flush=True)

    # Map top bar elements
    topbar = page.evaluate("""() => {
        const items = [];
        for (const el of document.querySelectorAll('*')) {
            const r = el.getBoundingClientRect();
            const text = (el.innerText || '').trim();
            if (r.y < 50 && r.x > 0 && r.x < 1440
                && r.width > 10 && r.width < 300 && r.height > 8 && r.height < 50
                && text && text.length > 0 && text.length < 80
                && !text.includes('\\n')) {
                items.push({
                    text: text,
                    tag: el.tagName,
                    x: Math.round(r.x),
                    y: Math.round(r.y),
                    w: Math.round(r.width),
                    h: Math.round(r.height),
                    clickable: el.tagName === 'BUTTON' || el.tagName === 'A'
                              || el.closest('button') !== null,
                });
            }
        }
        const seen = new Set();
        return items.filter(i => {
            const key = i.text + '|' + Math.round(i.x / 5);
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
        }).sort((a, b) => a.x - b.x);
    }""")

    print(f"\n  Top bar elements ({len(topbar)}):", flush=True)
    for el in topbar[:30]:
        click = " [CLICK]" if el.get("clickable") else ""
        print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> '{el['text']}'{click}", flush=True)

    # Click Export button
    export_clicked = page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            const text = (el.innerText || '').trim();
            const r = el.getBoundingClientRect();
            if (text === 'Export' && r.y < 50) {
                el.click(); return true;
            }
        }
        return false;
    }""")
    print(f"\n  Export clicked: {export_clicked}", flush=True)

    if export_clicked:
        page.wait_for_timeout(2000)
        close_dialogs(page)

        ss(page, "P26_06_export_dialog")

        # Map export dialog elements
        export_dlg = page.evaluate("""() => {
            const items = [];
            for (const el of document.querySelectorAll('*')) {
                const r = el.getBoundingClientRect();
                const text = (el.innerText || '').trim();
                // Export dialog is typically centered
                if (r.x > 200 && r.x < 1200 && r.y > 100 && r.y < 800
                    && r.width > 15 && r.width < 500 && r.height > 8 && r.height < 60
                    && text && text.length > 0 && text.length < 80
                    && !text.includes('\\n')
                    && r.height > 0) {
                    items.push({
                        text: text,
                        tag: el.tagName,
                        x: Math.round(r.x),
                        y: Math.round(r.y),
                        w: Math.round(r.width),
                        h: Math.round(r.height),
                    });
                }
            }
            const seen = new Set();
            return items.filter(i => {
                const key = i.text + '|' + Math.round(i.y / 5);
                if (seen.has(key)) return false;
                seen.add(key);
                return true;
            }).sort((a, b) => a.y - b.y);
        }""")

        print(f"\n  Export dialog ({len(export_dlg)}):", flush=True)
        for el in export_dlg[:40]:
            print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> '{el['text']}'", flush=True)

        # Close export dialog
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)

    # ============================================================
    #  PART 8: FULL URL PATTERNS FOR ALL RESULT TYPES
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 8: URL PATTERNS", flush=True)
    print("=" * 60, flush=True)

    all_urls = page.evaluate("""() => {
        const urls = [];
        for (const img of document.querySelectorAll('img')) {
            const src = img.src || '';
            if (src.includes('static.dzine.ai/stylar_product/p/')) {
                urls.push(src);
            }
        }
        return urls;
    }""")

    # Extract unique URL patterns (folder names)
    patterns = {}
    for url in all_urls:
        # Extract the type folder: p/<id>/<type>/...
        parts = url.split("/")
        for i, part in enumerate(parts):
            if part == "p" and i + 2 < len(parts):
                ptype = parts[i + 2]
                if ptype not in patterns:
                    patterns[ptype] = 0
                patterns[ptype] += 1
                break

    print(f"\n  URL patterns ({len(patterns)}):", flush=True)
    for ptype, count in sorted(patterns.items(), key=lambda x: -x[1]):
        print(f"    {ptype}: {count} images", flush=True)

    print(f"\n  Sample URLs per pattern:", flush=True)
    shown = set()
    for url in all_urls:
        parts = url.split("/")
        for i, part in enumerate(parts):
            if part == "p" and i + 2 < len(parts):
                ptype = parts[i + 2]
                if ptype not in shown:
                    shown.add(ptype)
                    print(f"    [{ptype}] {url[:130]}", flush=True)
                break

    ss(page, "P26_07_final")
    print(f"\n\n===== PHASE 26 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
