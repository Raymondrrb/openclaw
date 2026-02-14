"""Phase 24: Test CC generation with fixed button coordinates.

Focused test: open CC, select Ray, type prompt, click Generate,
monitor for new images. Also test Txt2Img generation.
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


def count_images(page, filter_type):
    """Count result images matching filter type(s)."""
    if isinstance(filter_type, str):
        filter_type = [filter_type]
    images = page.evaluate("""() => {
        const imgs = [];
        for (const img of document.querySelectorAll('img')) {
            const src = img.src || '';
            if (src.includes('static.dzine.ai/stylar_product/p/')) {
                imgs.push(src);
            }
        }
        return imgs;
    }""")
    return len([i for i in images if any(f in i for f in filter_type)])


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
    #  TEST 1: CC GENERATION
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  TEST 1: CC GENERATION", flush=True)
    print("=" * 60, flush=True)

    cc_before = count_images(page, "characterchatfal")
    print(f"\n  CC images before: {cc_before}", flush=True)

    # 1. Character sidebar
    page.mouse.click(40, 306)
    page.wait_for_timeout(1500)
    close_dialogs(page)

    # 2. Generate Images
    page.evaluate("""() => {
        for (const btn of document.querySelectorAll('button')) {
            const text = (btn.innerText || '').trim();
            if (text.includes('Generate Images') && text.includes('With your character')) {
                btn.click(); return true;
            }
        }
        return false;
    }""")
    page.wait_for_timeout(2000)

    # 3. Select Ray
    page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            const text = (el.innerText || '').trim();
            if (text === 'Ray' && el.tagName === 'BUTTON') {
                el.click(); return true;
            }
        }
        return false;
    }""")
    page.wait_for_timeout(2000)

    # 4. Clear and type scene (click textarea at 101, 200)
    page.mouse.click(101, 200)
    page.keyboard.press("Meta+a")
    page.wait_for_timeout(200)
    scene = "Ray giving a confident thumbs up in a modern studio with warm lighting. Medium shot, friendly expression."
    page.keyboard.type(scene, delay=5)
    page.wait_for_timeout(500)

    # 5. Set canvas (16:9)
    page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            if ((el.innerText || '').trim() === 'canvas' &&
                el.getBoundingClientRect().x > 60 && el.getBoundingClientRect().y > 400) {
                el.click(); return true;
            }
        }
        return false;
    }""")
    page.wait_for_timeout(500)

    # 6. Find ALL Generate buttons for debugging
    all_gen = page.evaluate("""() => {
        const btns = [];
        for (const btn of document.querySelectorAll('button')) {
            const text = (btn.innerText || '').trim();
            const r = btn.getBoundingClientRect();
            if (text.includes('Generate') && r.width > 50 && r.x > 60 && r.x < 400) {
                btns.push({
                    text: text.substring(0, 40),
                    x: Math.round(r.x),
                    y: Math.round(r.y),
                    w: Math.round(r.width),
                    h: Math.round(r.height),
                    disabled: btn.disabled,
                });
            }
        }
        return btns;
    }""")
    print(f"\n  All 'Generate' buttons:", flush=True)
    for b in all_gen:
        print(f"    ({b['x']},{b['y']}) {b['w']}x{b['h']} disabled={b['disabled']} '{b['text']}'", flush=True)

    ss(page, "P24_01_before_generate")

    # 7. Click Generate (y > 700)
    gen_clicked = page.evaluate("""() => {
        for (const btn of document.querySelectorAll('button')) {
            const text = (btn.innerText || '').trim();
            const r = btn.getBoundingClientRect();
            if (text.includes('Generate') && !btn.disabled
                && r.x > 60 && r.x < 350 && r.y > 700) {
                btn.click();
                return {text: text.substring(0, 30), x: Math.round(r.x), y: Math.round(r.y)};
            }
        }
        return null;
    }""")
    print(f"\n  Generate clicked: {gen_clicked}", flush=True)

    if not gen_clicked:
        # Fallback: scroll down and try again
        print("  Generate button not found, scrolling panel...", flush=True)
        page.evaluate("""() => {
            const panel = document.querySelector('[class*="panel"], [class*="sidebar-content"]');
            if (panel) panel.scrollTop += 200;
        }""")
        page.wait_for_timeout(500)

        gen_clicked = page.evaluate("""() => {
            for (const btn of document.querySelectorAll('button')) {
                const text = (btn.innerText || '').trim();
                const r = btn.getBoundingClientRect();
                if (text.includes('Generate') && !btn.disabled
                    && r.x > 60 && r.x < 350 && r.width > 100) {
                    btn.click();
                    return {text: text.substring(0, 30), x: Math.round(r.x), y: Math.round(r.y)};
                }
            }
            return null;
        }""")
        print(f"  After scroll, Generate clicked: {gen_clicked}", flush=True)

    if gen_clicked:
        print("\n  Monitoring CC generation...", flush=True)
        start = time.monotonic()
        for i in range(40):
            page.wait_for_timeout(3000)
            elapsed = time.monotonic() - start
            cc_after = count_images(page, "characterchatfal")

            if cc_after > cc_before:
                print(f"\n  CC GENERATION COMPLETE! [{elapsed:.0f}s] {cc_after} images (was {cc_before})", flush=True)
                ss(page, "P24_02_cc_complete")

                # Get new URLs
                urls = page.evaluate("""() => {
                    const urls = [];
                    for (const img of document.querySelectorAll('img')) {
                        const src = img.src || '';
                        if (src.includes('characterchatfal')) urls.push(src);
                    }
                    return urls;
                }""")
                for u in urls[:3]:
                    print(f"    {u[:100]}", flush=True)

                # Download
                dest = SS_DIR / "cc_gen_test.webp"
                try:
                    req = urllib.request.Request(urls[0], headers={"User-Agent": "Mozilla/5.0"})
                    with urllib.request.urlopen(req, timeout=30) as resp:
                        data = resp.read()
                    dest.write_bytes(data)
                    print(f"\n  Downloaded: {len(data)} bytes", flush=True)
                except Exception as e:
                    print(f"\n  Download failed: {e}", flush=True)
                break

            if i % 5 == 0:
                print(f"    [{elapsed:.0f}s] waiting... images={cc_after}", flush=True)

            if elapsed > 120:
                print(f"\n  Timeout after {elapsed:.0f}s", flush=True)
                ss(page, "P24_02_cc_timeout")
                break

    # ============================================================
    #  TEST 2: TXT2IMG GENERATION
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  TEST 2: TXT2IMG GENERATION", flush=True)
    print("=" * 60, flush=True)

    t2i_before = count_images(page, ["gemini2text2image", "faltxt2img"])
    print(f"\n  Txt2Img images before: {t2i_before}", flush=True)

    # 1. Txt2Img sidebar
    page.mouse.click(40, 197)
    page.wait_for_timeout(2000)
    close_dialogs(page)

    # 2. Type prompt
    page.mouse.click(101, 175)
    page.keyboard.press("Meta+a")
    page.wait_for_timeout(200)
    prompt = "Sony WH-1000XM5 headphones on a dark matte desk surface. Dramatic studio lighting from upper left, subtle rim light on edges. Premium commercial photography, 85mm shallow DOF. No text, no watermarks."
    page.keyboard.type(prompt, delay=3)
    page.wait_for_timeout(500)

    # 3. Set 16:9
    page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            const t = (el.innerText || '').trim();
            if (t === '16:9' && el.getBoundingClientRect().y > 400) {
                el.click(); return true;
            }
        }
        return false;
    }""")
    page.wait_for_timeout(500)

    ss(page, "P24_03_txt2img_ready")

    # 4. Click Generate
    t2i_gen = page.evaluate("""() => {
        for (const btn of document.querySelectorAll('button')) {
            const text = (btn.innerText || '').trim();
            const r = btn.getBoundingClientRect();
            if (text.includes('Generate') && !btn.disabled
                && r.x > 60 && r.x < 350) {
                btn.click();
                return {text: text.substring(0, 30), x: Math.round(r.x), y: Math.round(r.y)};
            }
        }
        return null;
    }""")
    print(f"\n  Txt2Img Generate clicked: {t2i_gen}", flush=True)

    if t2i_gen:
        print("\n  Monitoring Txt2Img generation...", flush=True)
        start = time.monotonic()
        for i in range(40):
            page.wait_for_timeout(3000)
            elapsed = time.monotonic() - start
            t2i_after = count_images(page, ["gemini2text2image", "faltxt2img"])

            if t2i_after > t2i_before:
                print(f"\n  TXT2IMG COMPLETE! [{elapsed:.0f}s] {t2i_after} images (was {t2i_before})", flush=True)
                ss(page, "P24_04_txt2img_complete")

                urls = page.evaluate("""() => {
                    const urls = [];
                    for (const img of document.querySelectorAll('img')) {
                        const src = img.src || '';
                        if (src.includes('gemini2text2image') || src.includes('faltxt2img'))
                            urls.push(src);
                    }
                    return urls;
                }""")
                for u in urls[:3]:
                    print(f"    {u[:100]}", flush=True)

                dest = SS_DIR / "txt2img_gen_test.webp"
                try:
                    req = urllib.request.Request(urls[0], headers={"User-Agent": "Mozilla/5.0"})
                    with urllib.request.urlopen(req, timeout=30) as resp:
                        data = resp.read()
                    dest.write_bytes(data)
                    print(f"\n  Downloaded: {len(data)} bytes", flush=True)
                except Exception as e:
                    print(f"\n  Download failed: {e}", flush=True)
                break

            if i % 5 == 0:
                print(f"    [{elapsed:.0f}s] waiting... images={t2i_after}", flush=True)

            if elapsed > 120:
                print(f"\n  Timeout after {elapsed:.0f}s", flush=True)
                ss(page, "P24_04_txt2img_timeout")
                break

    ss(page, "P24_05_final")
    print(f"\n\n===== PHASE 24 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
