"""Phase 74: Explore sidebar tools that didn't open in P73.

Strategy changes:
1. Use panel toggle technique (click different tool first, then target)
2. Also search for ALL element types in panel area (not just text)
3. Fix: search for Storyboard without literal newline
4. Try selecting a result image first for video-based tools
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


def dump_panel(page, label, x_min=60, x_max=400, y_min=40, y_max=900):
    """Dump ALL elements in the panel area, including non-text ones."""
    items = page.evaluate(f"""() => {{
        var items = [];
        var excluded = ['path','line','circle','g','svg','defs','rect','polygon',
                        'clippath','HTML','BODY','HEAD','SCRIPT','STYLE','META','LINK'];
        for (const el of document.querySelectorAll('*')) {{
            var r = el.getBoundingClientRect();
            if (r.x >= {x_min} && r.x <= {x_max} && r.y >= {y_min} && r.y <= {y_max}
                && r.width > 10 && r.height > 10 && r.width < 400
                && !excluded.includes(el.tagName.toUpperCase())) {{
                var text = (el.innerText || '').trim().substring(0, 40);
                var info = {{
                    tag: el.tagName, x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    text: text.replace(/\\n/g, ' ').substring(0, 35),
                    classes: (el.className || '').toString().substring(0, 30),
                }};
                if (el.tagName === 'IMG') info.src = (el.src || '').substring(0, 60);
                if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') {{
                    info.placeholder = (el.placeholder || '').substring(0, 30);
                    info.type = el.type || '';
                }}
                items.push(info);
            }}
        }}
        var seen = new Set();
        return items.filter(function(i) {{
            var key = i.tag + '|' + i.x + '|' + i.y;
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
        }}).sort(function(a,b) {{ return a.y - b.y; }}).slice(0, 50);
    }}""")
    print(f"\n  {label} ({len(items)} elements):", flush=True)
    for el in items:
        extra = ''
        if el.get('src'): extra += f" src={el['src']}"
        if el.get('placeholder'): extra += f" ph='{el['placeholder']}'"
        if el.get('type'): extra += f" type={el['type']}"
        t = el['text'][:30] if el.get('text') else ''
        print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> c='{el['classes'][:22]}' '{t}'{extra}", flush=True)
    return items


def click_sidebar(page, name):
    """Click a sidebar tool by name."""
    return page.evaluate(f"""() => {{
        for (const el of document.querySelectorAll('*')) {{
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text === '{name}' && r.x < 60 && r.y > 60 && r.height < 50) {{
                el.click();
                return {{x: Math.round(r.x), y: Math.round(r.y)}};
            }}
        }}
        return null;
    }}""")


def main():
    print("Connecting...", flush=True)
    pw = sync_playwright().start()
    browser = pw.chromium.connect_over_cdp("http://127.0.0.1:18800", timeout=15000)
    ctx = browser.contexts[0]
    page = ctx.new_page()
    page.set_viewport_size({"width": 1440, "height": 900})

    page.goto(CANVAS_URL, wait_until="domcontentloaded", timeout=30000)
    print("  Waiting 12s for full canvas load...", flush=True)
    page.wait_for_timeout(12000)
    close_dialogs(page)

    # First, let's verify the sidebar tool list
    sidebar = page.evaluate("""() => {
        var items = [];
        for (const el of document.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            if (r.x < 60 && r.y > 60 && r.y < 900
                && r.width > 20 && r.height > 15 && r.height < 50) {
                var text = (el.innerText || '').trim();
                if (text.length > 2 && text.length < 25 && text.indexOf('\\n') === -1
                    && el.children.length === 0) {
                    items.push({text: text, y: Math.round(r.y), x: Math.round(r.x)});
                }
            }
        }
        var seen = new Set();
        return items.filter(function(i) {
            if (seen.has(i.text)) return false;
            seen.add(i.text);
            return true;
        }).sort(function(a,b) { return a.y - b.y; });
    }""")
    print(f"  Sidebar tools ({len(sidebar)}):", flush=True)
    for s in sidebar:
        print(f"    y={s['y']} '{s['text']}'", flush=True)

    # ============================================================
    #  PART 1: AI VIDEO — with panel toggle
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 1: AI VIDEO (panel toggle technique)", flush=True)
    print("=" * 60, flush=True)

    # Toggle: click Txt2Img first to open its panel, then AI Video
    click_sidebar(page, "Txt2Img")
    page.wait_for_timeout(1000)
    close_dialogs(page)

    av = click_sidebar(page, "AI Video")
    print(f"  AI Video clicked (after toggle): {av}", flush=True)
    page.wait_for_timeout(2000)
    close_dialogs(page)
    ss(page, "P74_01_ai_video_toggle")

    dump_panel(page, "AI Video panel")

    # Check if there's a wider panel or overlay
    dump_panel(page, "AI Video full width check", x_min=0, x_max=600, y_min=40, y_max=300)

    # ============================================================
    #  PART 2: LIP SYNC — with panel toggle
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 2: LIP SYNC (panel toggle)", flush=True)
    print("=" * 60, flush=True)

    click_sidebar(page, "Txt2Img")
    page.wait_for_timeout(1000)
    close_dialogs(page)

    ls = click_sidebar(page, "Lip Sync")
    print(f"  Lip Sync clicked: {ls}", flush=True)
    page.wait_for_timeout(2000)
    close_dialogs(page)
    ss(page, "P74_02_lip_sync")

    dump_panel(page, "Lip Sync panel")

    # ============================================================
    #  PART 3: VIDEO EDITOR — with panel toggle
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 3: VIDEO EDITOR (panel toggle)", flush=True)
    print("=" * 60, flush=True)

    click_sidebar(page, "Txt2Img")
    page.wait_for_timeout(1000)
    close_dialogs(page)

    ve = click_sidebar(page, "Video Editor")
    print(f"  Video Editor clicked: {ve}", flush=True)
    page.wait_for_timeout(2000)
    close_dialogs(page)
    ss(page, "P74_03_video_editor")

    dump_panel(page, "Video Editor panel")

    # ============================================================
    #  PART 4: MOTION CONTROL — with panel toggle
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 4: MOTION CONTROL (panel toggle)", flush=True)
    print("=" * 60, flush=True)

    click_sidebar(page, "Txt2Img")
    page.wait_for_timeout(1000)
    close_dialogs(page)

    mc = click_sidebar(page, "Motion Control")
    print(f"  Motion Control clicked: {mc}", flush=True)
    page.wait_for_timeout(2000)
    close_dialogs(page)
    ss(page, "P74_04_motion_control")

    dump_panel(page, "Motion Control panel")

    # ============================================================
    #  PART 5: INSTANT STORYBOARD
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 5: INSTANT STORYBOARD (panel toggle)", flush=True)
    print("=" * 60, flush=True)

    click_sidebar(page, "Txt2Img")
    page.wait_for_timeout(1000)
    close_dialogs(page)

    # Instant Storyboard — text may wrap, search by "Storyboard"
    isb = page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim().replace(/\\s+/g, ' ');
            var r = el.getBoundingClientRect();
            if (text.includes('Storyboard') && r.x < 60 && r.y > 300 && r.height < 50) {
                el.click();
                return {x: Math.round(r.x), y: Math.round(r.y), text: text};
            }
        }
        return null;
    }""")
    print(f"  Instant Storyboard clicked: {isb}", flush=True)
    page.wait_for_timeout(2000)
    close_dialogs(page)
    ss(page, "P74_05_storyboard")

    dump_panel(page, "Storyboard panel")

    # ============================================================
    #  PART 6: ENHANCE & UPSCALE
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 6: ENHANCE & UPSCALE (panel toggle)", flush=True)
    print("=" * 60, flush=True)

    click_sidebar(page, "Txt2Img")
    page.wait_for_timeout(1000)
    close_dialogs(page)

    enh = page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim().replace(/\\s+/g, ' ');
            var r = el.getBoundingClientRect();
            if (text.includes('Enhance') && r.x < 60 && r.y > 300 && r.height < 50) {
                el.click();
                return {x: Math.round(r.x), y: Math.round(r.y), text: text};
            }
        }
        return null;
    }""")
    print(f"  Enhance & Upscale clicked: {enh}", flush=True)
    page.wait_for_timeout(2000)
    close_dialogs(page)
    ss(page, "P74_06_enhance")

    dump_panel(page, "Enhance & Upscale panel")

    # ============================================================
    #  PART 7: EXPRESSION EDIT — SCROLL CUSTOM FOR FULL SLIDER LIST
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 7: EXPRESSION EDIT CUSTOM — FULL SLIDER LIST", flush=True)
    print("=" * 60, flush=True)

    # Click on face then Expression toolbar
    page.mouse.click(550, 350)
    page.wait_for_timeout(1000)

    expr = page.evaluate("""() => {
        var bar = document.querySelector('.layer-tools');
        if (!bar) return null;
        for (const btn of bar.querySelectorAll('*')) {
            if ((btn.innerText || '').trim() === 'Expression') {
                btn.click(); return true;
            }
        }
        return null;
    }""")
    print(f"  Expression clicked: {expr}", flush=True)
    page.wait_for_timeout(5000)
    close_dialogs(page)

    # Check if we're in Expression Edit full-screen mode
    # In full-screen mode, the top bar shows "Expression Edit" "Done" "Cancel"
    in_expr = page.evaluate("""() => {
        for (const el of document.querySelectorAll('button')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text === 'Done' && r.x > 500 && r.x < 800 && r.y < 40 && r.width > 0) {
                return true;
            }
        }
        return false;
    }""")
    print(f"  In Expression Edit mode (Done button visible): {in_expr}", flush=True)

    if in_expr:
        # Get ALL labels in the panel by searching the entire DOM for expression-related text
        all_sliders = page.evaluate("""() => {
            var items = [];
            for (const el of document.querySelectorAll('*')) {
                var r = el.getBoundingClientRect();
                if (r.x >= 10 && r.x <= 200 && r.width > 40
                    && r.height >= 10 && r.height <= 22
                    && el.children.length === 0) {
                    var text = (el.innerText || '').trim();
                    if (text.length > 2 && text.length < 30 && text.indexOf('\\n') === -1) {
                        items.push({text: text, y: Math.round(r.y), x: Math.round(r.x)});
                    }
                }
            }
            var seen = new Set();
            return items.filter(function(i) {
                var key = i.text + '|' + Math.round(i.y / 10);
                if (seen.has(key)) return false;
                seen.add(key);
                return true;
            }).sort(function(a,b) { return a.y - b.y; });
        }""")
        print(f"\n  Expression Edit slider labels ({len(all_sliders)}):", flush=True)
        for s in all_sliders:
            print(f"    y={s['y']} x={s['x']} '{s['text']}'", flush=True)

        # Scroll down using the panel
        page.mouse.move(100, 600)
        page.mouse.wheel(0, 500)
        page.wait_for_timeout(500)

        after = page.evaluate("""() => {
            var items = [];
            for (const el of document.querySelectorAll('*')) {
                var r = el.getBoundingClientRect();
                if (r.x >= 10 && r.x <= 200 && r.width > 40
                    && r.height >= 10 && r.height <= 22
                    && el.children.length === 0) {
                    var text = (el.innerText || '').trim();
                    if (text.length > 2 && text.length < 30 && text.indexOf('\\n') === -1) {
                        items.push({text: text, y: Math.round(r.y), x: Math.round(r.x)});
                    }
                }
            }
            var seen = new Set();
            return items.filter(function(i) {
                var key = i.text + '|' + Math.round(i.y / 10);
                if (seen.has(key)) return false;
                seen.add(key);
                return true;
            }).sort(function(a,b) { return a.y - b.y; });
        }""")
        print(f"\n  After scroll ({len(after)}):", flush=True)
        for s in after:
            print(f"    y={s['y']} x={s['x']} '{s['text']}'", flush=True)

        ss(page, "P74_07_expression_scrolled")

        # Scroll more
        page.mouse.wheel(0, 500)
        page.wait_for_timeout(500)

        after2 = page.evaluate("""() => {
            var items = [];
            for (const el of document.querySelectorAll('*')) {
                var r = el.getBoundingClientRect();
                if (r.x >= 10 && r.x <= 200 && r.width > 40
                    && r.height >= 10 && r.height <= 22
                    && el.children.length === 0) {
                    var text = (el.innerText || '').trim();
                    if (text.length > 2 && text.length < 30 && text.indexOf('\\n') === -1) {
                        items.push({text: text, y: Math.round(r.y), x: Math.round(r.x)});
                    }
                }
            }
            var seen = new Set();
            return items.filter(function(i) {
                var key = i.text + '|' + Math.round(i.y / 10);
                if (seen.has(key)) return false;
                seen.add(key);
                return true;
            }).sort(function(a,b) { return a.y - b.y; });
        }""")
        print(f"\n  After scroll x2 ({len(after2)}):", flush=True)
        for s in after2:
            print(f"    y={s['y']} x={s['x']} '{s['text']}'", flush=True)

        ss(page, "P74_08_expression_scrolled2")

        # Cancel
        page.evaluate("""() => {
            for (const el of document.querySelectorAll('button')) {
                if ((el.innerText || '').trim() === 'Cancel'
                    && el.getBoundingClientRect().y < 50
                    && el.getBoundingClientRect().width > 0) {
                    el.click(); return true;
                }
            }
            return false;
        }""")
        page.wait_for_timeout(2000)

    else:
        print("  Expression Edit mode not entered. Taking screenshot for debugging.", flush=True)
        ss(page, "P74_07_expression_debug")
        dump_panel(page, "After Expression click", x_min=0, x_max=400, y_min=0, y_max=500)

    print(f"\n\n===== PHASE 74 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
