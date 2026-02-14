"""Phase 25: Verify CC detection fix + explore Lip Sync, Expression Edit.

Goals:
1. Verify CC generation detection with improved counter (total images fallback)
2. Explore Lip Sync panel — upload face + audio
3. Explore Expression Edit on a CC result
4. Test the result "1" / "2" selector buttons for CC outputs
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

def get_all_result_images(page):
    """Get ALL result images from static.dzine.ai."""
    return page.evaluate("""() => {
        const results = [];
        for (const img of document.querySelectorAll('img')) {
            const src = img.src || '';
            if (src.includes('static.dzine.ai/stylar_product/p/')) {
                const r = img.getBoundingClientRect();
                results.push({
                    src: src,
                    x: Math.round(r.x),
                    y: Math.round(r.y),
                    w: Math.round(r.width),
                    h: Math.round(r.height),
                });
            }
        }
        return results;
    }""")

def get_result_sections(page):
    """Get result section headers from the Results panel."""
    return page.evaluate("""() => {
        const sections = [];
        for (const el of document.querySelectorAll('*')) {
            const text = (el.innerText || '').trim();
            const r = el.getBoundingClientRect();
            if (r.x > 340 && r.x < 1100 && r.width > 200 && r.height < 40
                && (text === 'Consistent Character' || text === 'Text-to-Image'
                    || text === 'Chat Editor' || text === 'Character Sheet')) {
                sections.push({
                    type: text,
                    x: Math.round(r.x),
                    y: Math.round(r.y),
                });
            }
        }
        const seen = new Set();
        return sections.filter(s => {
            const key = s.type + '|' + Math.round(s.y / 20);
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
        }).sort((a, b) => a.y - b.y);
    }""")


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
    #  PART 1: CC GENERATION WITH IMPROVED DETECTION
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 1: CC GENERATION (improved detection)", flush=True)
    print("=" * 60, flush=True)

    # Count ALL result images (not just CC pattern)
    all_before = get_all_result_images(page)
    sections_before = get_result_sections(page)
    print(f"\n  Total images before: {len(all_before)}", flush=True)
    print(f"  Result sections before: {len(sections_before)}", flush=True)
    for s in sections_before[:5]:
        print(f"    y={s['y']} {s['type']}", flush=True)

    # Open CC, select Ray, type, generate
    page.mouse.click(40, 306)
    page.wait_for_timeout(1500)
    close_dialogs(page)

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

    page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            if ((el.innerText || '').trim() === 'Ray' && el.tagName === 'BUTTON') {
                el.click(); return true;
            }
        }
        return false;
    }""")
    page.wait_for_timeout(2000)

    # Type scene
    page.mouse.click(101, 200)
    page.keyboard.press("Meta+a")
    page.wait_for_timeout(200)
    page.keyboard.type("Ray standing at a desk, reviewing a wireless mouse, focused expression, modern office lighting", delay=5)
    page.wait_for_timeout(500)

    # Canvas ratio
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

    # Click Generate
    gen = page.evaluate("""() => {
        for (const btn of document.querySelectorAll('button')) {
            const text = (btn.innerText || '').trim();
            const r = btn.getBoundingClientRect();
            if (text.includes('Generate') && !btn.disabled
                && r.x > 60 && r.x < 350 && r.y > 700) {
                btn.click(); return true;
            }
        }
        return false;
    }""")
    print(f"\n  Generate clicked: {gen}", flush=True)

    if gen:
        print("  Monitoring with improved detection...", flush=True)
        start = time.monotonic()

        for i in range(50):  # 50 x 3s = 150s max
            page.wait_for_timeout(3000)
            elapsed = time.monotonic() - start

            all_now = get_all_result_images(page)
            sections_now = get_result_sections(page)

            # Detection: more total images OR more result sections
            new_images = len(all_now) - len(all_before)
            new_sections = len(sections_now) - len(sections_before)

            if i % 5 == 0 or new_images > 0 or new_sections > 0:
                print(f"    [{elapsed:.0f}s] images={len(all_now)} (+{new_images}) "
                      f"sections={len(sections_now)} (+{new_sections})", flush=True)

            if new_images > 0:
                # Found new image(s)
                new_img = all_now[0]  # newest at top
                print(f"\n  NEW IMAGE DETECTED! [{elapsed:.0f}s]", flush=True)
                print(f"    URL: {new_img['src'][:100]}", flush=True)
                print(f"    Size: {new_img['w']}x{new_img['h']}", flush=True)

                ss(page, "P25_01_cc_success")

                # Download
                dest = SS_DIR / "cc_verified.webp"
                try:
                    req = urllib.request.Request(new_img["src"], headers={"User-Agent": "Mozilla/5.0"})
                    with urllib.request.urlopen(req, timeout=30) as resp:
                        data = resp.read()
                    dest.write_bytes(data)
                    print(f"  Downloaded: {len(data)} bytes", flush=True)
                except Exception as e:
                    print(f"  Download failed: {e}", flush=True)
                break

            if elapsed > 150:
                print(f"\n  Timeout after {elapsed:.0f}s", flush=True)
                ss(page, "P25_01_cc_timeout")

                # Debug: show what's in results now
                for s in sections_now[:5]:
                    print(f"    Section: y={s['y']} {s['type']}", flush=True)
                for img in all_now[:5]:
                    print(f"    Image: ({img['x']},{img['y']}) {img['src'][:60]}", flush=True)
                break

    # ============================================================
    #  PART 2: EXPLORE LIP SYNC PANEL
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 2: LIP SYNC PANEL", flush=True)
    print("=" * 60, flush=True)

    page.mouse.click(40, 425)  # Lip Sync sidebar
    page.wait_for_timeout(2000)
    close_dialogs(page)

    ss(page, "P25_02_lip_sync_panel")

    lip_sync = page.evaluate("""() => {
        const items = [];
        for (const el of document.querySelectorAll('*')) {
            const r = el.getBoundingClientRect();
            const text = (el.innerText || '').trim();
            if (r.x > 60 && r.x < 400 && r.y > 50 && r.y < 900
                && r.width > 15 && r.width < 350 && text
                && text.length > 0 && text.length < 60
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

    print(f"\n  Lip Sync panel ({len(lip_sync)}):", flush=True)
    for el in lip_sync[:30]:
        print(f"    ({el['x']},{el['y']}) w={el['w']} <{el['tag']}> '{el['text']}'", flush=True)

    # ============================================================
    #  PART 3: EXPLORE AI VIDEO PANEL
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 3: AI VIDEO PANEL", flush=True)
    print("=" * 60, flush=True)

    page.mouse.click(40, 361)  # AI Video sidebar
    page.wait_for_timeout(2000)
    close_dialogs(page)

    ss(page, "P25_03_ai_video_panel")

    ai_video = page.evaluate("""() => {
        const items = [];
        for (const el of document.querySelectorAll('*')) {
            const r = el.getBoundingClientRect();
            const text = (el.innerText || '').trim();
            if (r.x > 60 && r.x < 400 && r.y > 50 && r.y < 900
                && r.width > 15 && r.width < 350 && text
                && text.length > 0 && text.length < 60
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

    print(f"\n  AI Video panel ({len(ai_video)}):", flush=True)
    for el in ai_video[:30]:
        print(f"    ({el['x']},{el['y']}) w={el['w']} <{el['tag']}> '{el['text']}'", flush=True)

    # ============================================================
    #  PART 4: CC RESULT VARIANT SELECTORS (1/2 buttons)
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 4: CC RESULT VARIANT SELECTORS", flush=True)
    print("=" * 60, flush=True)

    # Switch to Results tab
    page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            if ((el.innerText || '').trim() === 'Results' && el.getBoundingClientRect().x > 1050) {
                el.click(); return true;
            }
        }
        return false;
    }""")
    page.wait_for_timeout(1000)

    # Scroll results to top
    page.evaluate("""() => {
        const panels = document.querySelectorAll('[class*="result"], [class*="Result"], [class*="scroll"]');
        for (const p of panels) {
            if (p.scrollHeight > p.clientHeight && p.getBoundingClientRect().x > 300) {
                p.scrollTop = 0;
                return true;
            }
        }
        return false;
    }""")
    page.wait_for_timeout(500)

    ss(page, "P25_04_results_top")

    # Find variant selector buttons (small "1" "2" buttons near CC results)
    variant_btns = page.evaluate("""() => {
        const btns = [];
        for (const el of document.querySelectorAll('*')) {
            const text = (el.innerText || '').trim();
            const r = el.getBoundingClientRect();
            if ((text === '1' || text === '2') && r.x > 350 && r.x < 1100
                && r.width > 20 && r.width < 80 && r.height > 15 && r.height < 50) {
                btns.push({
                    text: text,
                    tag: el.tagName,
                    x: Math.round(r.x),
                    y: Math.round(r.y),
                    w: Math.round(r.width),
                    h: Math.round(r.height),
                });
            }
        }
        return btns;
    }""")

    print(f"\n  Variant selectors ({len(variant_btns)}):", flush=True)
    for btn in variant_btns[:10]:
        print(f"    ({btn['x']},{btn['y']}) {btn['w']}x{btn['h']} <{btn['tag']}> '{btn['text']}'", flush=True)

    # Click "2" to select second variant
    if variant_btns:
        btn2 = next((b for b in variant_btns if b["text"] == "2"), None)
        if btn2:
            page.mouse.click(btn2["x"], btn2["y"])
            page.wait_for_timeout(1000)
            print(f"\n  Clicked variant 2 at ({btn2['x']},{btn2['y']})", flush=True)

            # Check if a different image is now shown
            images_after_select = get_all_result_images(page)
            top_img = images_after_select[0] if images_after_select else None
            if top_img:
                print(f"  Top image URL: {top_img['src'][:80]}", flush=True)

            ss(page, "P25_05_variant2_selected")

    # ============================================================
    #  PART 5: EXPRESSION EDIT ON CC RESULT
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 5: EXPRESSION EDIT", flush=True)
    print("=" * 60, flush=True)

    # Find and click "Expression Edit" action button near a CC result
    expr_clicked = page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            const text = (el.innerText || '').trim();
            const r = el.getBoundingClientRect();
            if (text === 'Expression Edit' && r.x > 350 && r.x < 1100
                && r.width > 50 && r.width < 200) {
                el.click(); return true;
            }
        }
        return false;
    }""")
    print(f"\n  Expression Edit clicked: {expr_clicked}", flush=True)

    if expr_clicked:
        page.wait_for_timeout(2000)
        close_dialogs(page)

        ss(page, "P25_06_expression_edit")

        # Map the Expression Edit panel
        expr_panel = page.evaluate("""() => {
            const items = [];
            for (const el of document.querySelectorAll('*')) {
                const r = el.getBoundingClientRect();
                const text = (el.innerText || '').trim();
                if (r.x > 60 && r.x < 400 && r.y > 50 && r.y < 900
                    && r.width > 15 && r.width < 350 && text
                    && text.length > 0 && text.length < 60
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

        print(f"\n  Expression Edit panel ({len(expr_panel)}):", flush=True)
        for el in expr_panel[:25]:
            print(f"    ({el['x']},{el['y']}) w={el['w']} <{el['tag']}> '{el['text']}'", flush=True)

    ss(page, "P25_07_final")
    print(f"\n\n===== PHASE 25 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
