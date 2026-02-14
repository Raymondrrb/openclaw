"""Phase 90: PRACTICE — Generate a real image with Ray via CC.
Goal: End-to-end test of the CC workflow via automation.
1. Open Character → Generate Images → Select Ray
2. Type a scene prompt
3. Set aspect ratio to canvas (16:9)
4. Click Generate
5. Wait for result in Results panel
6. Capture the result image URL
"""

import json
import os
import sys
import time
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


def wait_for_canvas(page, max_wait=40):
    for i in range(max_wait):
        loaded = page.evaluate("() => document.querySelectorAll('.tool-group').length")
        if loaded >= 5:
            print(f"  Canvas loaded ({loaded} tool groups) after {i+1}s", flush=True)
            page.wait_for_timeout(2000)
            return True
        page.wait_for_timeout(1000)
    return False


def close_all_overlays(page):
    for _ in range(3):
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
    page.evaluate("""() => {
        var c1 = document.querySelector('.c-gen-config.show .ico-close');
        if (c1) c1.click();
        var c2 = document.querySelector('.panels.show .ico-close');
        if (c2) c2.click();
    }""")
    page.wait_for_timeout(500)
    close_dialogs(page)
    page.mouse.click(700, 450)
    page.wait_for_timeout(500)


def dismiss_popups(page):
    page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            if (text === 'Skip' && el.getBoundingClientRect().width > 20) {
                el.click(); return;
            }
        }
    }""")
    page.wait_for_timeout(500)
    close_dialogs(page)


def cleanup_tabs(ctx):
    pages = ctx.pages
    print(f"  Found {len(pages)} open tabs", flush=True)
    kept = False
    for p in pages:
        url = p.url or ""
        if "dzine.ai" in url:
            if kept:
                try:
                    p.close()
                except Exception:
                    pass
            else:
                kept = True
        elif url in ("", "about:blank", "chrome://newtab/"):
            try:
                p.close()
            except Exception:
                pass
    print(f"  Tabs after cleanup: {len(ctx.pages)}", flush=True)


def main():
    print("Connecting...", flush=True)
    pw = sync_playwright().start()
    browser = pw.chromium.connect_over_cdp("http://127.0.0.1:18800", timeout=15000)
    ctx = browser.contexts[0]
    cleanup_tabs(ctx)

    page = ctx.new_page()
    page.set_viewport_size({"width": 1440, "height": 900})

    page.goto(CANVAS_URL, wait_until="domcontentloaded", timeout=30000)
    print("  Waiting for canvas...", flush=True)
    wait_for_canvas(page)
    close_dialogs(page)

    # ============================================================
    #  STEP 1: Open Character → Generate Images
    # ============================================================
    print("\n  STEP 1: Open Character panel...", flush=True)
    close_all_overlays(page)
    page.wait_for_timeout(500)

    # Toggle to distant tool first
    page.mouse.click(40, 766)  # Storyboard
    page.wait_for_timeout(2000)
    close_dialogs(page)
    page.mouse.move(700, 450)
    page.wait_for_timeout(300)

    # Click Character
    page.mouse.click(40, 306)
    page.wait_for_timeout(3000)
    close_dialogs(page)
    dismiss_popups(page)

    # Click Generate Images
    clicked = page.evaluate("""() => {
        var p = document.querySelector('.panels.show') ||
                document.querySelector('.c-gen-config.show');
        if (!p) return 'no panel';
        for (var el of p.querySelectorAll('p')) {
            if ((el.innerText || '').trim() === 'Generate Images') {
                el.click(); return 'clicked';
            }
        }
        return 'not found';
    }""")
    print(f"  Generate Images: {clicked}", flush=True)
    page.wait_for_timeout(2500)
    close_dialogs(page)
    dismiss_popups(page)

    # ============================================================
    #  STEP 2: Select Ray character
    # ============================================================
    print("\n  STEP 2: Select Ray...", flush=True)

    # Click Ray in character list
    ray = page.evaluate("""() => {
        for (var btn of document.querySelectorAll('button')) {
            var text = (btn.innerText || '').trim();
            if (text === 'Ray' && btn.tagName === 'BUTTON') {
                btn.click();
                return 'clicked Ray button';
            }
        }
        return 'Ray not found';
    }""")
    print(f"  Ray: {ray}", flush=True)
    page.wait_for_timeout(2000)

    # Verify Ray is selected
    chooser = page.evaluate("""() => {
        var el = document.querySelector('.character-choose');
        return el ? (el.innerText || '').trim() : 'no chooser';
    }""")
    print(f"  Chooser text: {chooser}", flush=True)

    # ============================================================
    #  STEP 3: Type scene prompt
    # ============================================================
    print("\n  STEP 3: Type prompt...", flush=True)

    # Click the prompt textarea
    page.mouse.click(101, 200)
    page.wait_for_timeout(500)

    # Clear any existing text and type new prompt
    page.keyboard.press("Meta+a")
    page.wait_for_timeout(200)

    scene = "Ray standing confidently in a modern tech studio, holding a wireless headphone, studio lighting, professional product review setting, cinematic composition"
    page.keyboard.type(scene, delay=5)
    page.wait_for_timeout(500)

    # Verify prompt was typed
    prompt_text = page.evaluate("""() => {
        var p = document.querySelector('.c-gen-config.show');
        if (!p) return null;
        var ta = p.querySelector('.custom-textarea');
        return ta ? (ta.innerText || '').trim().substring(0, 80) : 'no textarea';
    }""")
    print(f"  Prompt: '{prompt_text}'", flush=True)
    ss(page, "P90_01_prompt_typed")

    # ============================================================
    #  STEP 4: Set aspect ratio to canvas (16:9)
    # ============================================================
    print("\n  STEP 4: Set aspect ratio...", flush=True)

    ratio_set = page.evaluate("""() => {
        var p = document.querySelector('.c-gen-config.show');
        if (!p) return 'no panel';
        for (var el of p.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text === 'canvas' && r.y > 400 && r.x > 60 && r.x < 350) {
                el.click();
                return 'clicked canvas ratio';
            }
        }
        return 'canvas ratio not found';
    }""")
    print(f"  Ratio: {ratio_set}", flush=True)
    page.wait_for_timeout(500)

    # ============================================================
    #  STEP 5: Click Generate
    # ============================================================
    print("\n  STEP 5: Generate...", flush=True)

    # Record current result count before generating
    before_count = page.evaluate("""() => {
        var results = document.querySelectorAll('.result-item, [class*="result-image"]');
        return results.length;
    }""")
    print(f"  Results before: {before_count}", flush=True)

    gen_clicked = page.evaluate("""() => {
        var p = document.querySelector('.c-gen-config.show');
        if (!p) return 'no panel';
        for (var btn of p.querySelectorAll('button')) {
            var text = (btn.innerText || '').trim();
            if (text.includes('Generate') && !btn.disabled
                && btn.getBoundingClientRect().x > 60
                && btn.getBoundingClientRect().x < 350) {
                btn.click();
                return 'clicked Generate';
            }
        }
        // Try the span approach
        for (var el of p.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text === 'Generate' && r.y > 700 && r.x > 60) {
                var parent = el.closest('button') || el;
                parent.click();
                return 'clicked Generate (span)';
            }
        }
        return 'Generate not found';
    }""")
    print(f"  Generate: {gen_clicked}", flush=True)
    page.wait_for_timeout(2000)
    ss(page, "P90_02_generating")

    # ============================================================
    #  STEP 6: Wait for result (up to 120s)
    # ============================================================
    print("\n  STEP 6: Waiting for result...", flush=True)

    # Switch to Results tab
    page.evaluate("() => document.querySelector('.header-item.item-results')?.click()")
    page.wait_for_timeout(1000)

    # Poll for new result
    max_wait = 120
    for i in range(max_wait):
        # Check for progress or new results
        status = page.evaluate("""() => {
            // Check for progress indicator
            var progress = document.querySelector('.progress-bar, .progress, [class*="progress"]');
            var progressText = '';
            if (progress) {
                progressText = (progress.innerText || '').trim() || 'found';
            }

            // Check for loading indicator in results
            var loading = document.querySelector('.loading, .generating, [class*="loading"]');
            var loadingText = loading ? 'loading' : '';

            // Check for new result images
            var imgs = document.querySelectorAll('img[src*="static.dzine.ai"]');
            var newSrcs = [];
            for (var img of imgs) {
                var src = img.src || '';
                if (src.includes('static.dzine.ai') && src.includes('/generation/')) {
                    newSrcs.push(src.substring(0, 80));
                }
            }

            // Check for percentage text in results area
            var percentages = [];
            var rightPanel = document.querySelector('.c-material-library-v2');
            if (rightPanel) {
                for (var el of rightPanel.querySelectorAll('*')) {
                    var text = (el.innerText || '').trim();
                    if (text.match(/\\d+%/) && text.length < 10) {
                        percentages.push(text);
                    }
                }
            }

            return {
                progress: progressText,
                loading: loadingText,
                images: newSrcs.slice(-3),
                percentages: percentages.slice(-3),
            };
        }""")

        if i % 10 == 0 or status.get('percentages') or status.get('images'):
            print(f"  [{i}s] progress={status.get('progress')} loading={status.get('loading')} "
                  f"pct={status.get('percentages')} imgs={len(status.get('images', []))}", flush=True)

        if status.get('images'):
            print(f"\n  RESULT FOUND after {i}s!", flush=True)
            for src in status['images']:
                print(f"    Image: {src}", flush=True)
            break

        page.wait_for_timeout(1000)
    else:
        print(f"  Timeout after {max_wait}s", flush=True)

    ss(page, "P90_03_result")

    # Try to get the latest result image URL
    result_urls = page.evaluate("""() => {
        var imgs = [];
        for (var img of document.querySelectorAll('img')) {
            var src = img.src || '';
            if (src.includes('static.dzine.ai') && src.includes('/generation/')) {
                var r = img.getBoundingClientRect();
                imgs.push({
                    src: src,
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                });
            }
        }
        return imgs;
    }""")
    print(f"\n  All generation images ({len(result_urls)}):", flush=True)
    for img in result_urls:
        print(f"    ({img['x']},{img['y']}) {img['w']}x{img['h']} {img['src'][:80]}", flush=True)

    # Take final screenshot
    ss(page, "P90_04_final")

    print(f"\n\n===== PHASE 90 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
