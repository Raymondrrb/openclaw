"""Phase 77: Deep dive into Txt2Img and Img2Img panels.
Also try clicking sidebar icons by coordinate (icon center) instead of text.
Map the Txt2Img panel's model selector, advanced settings, and negative prompt.
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


def dump_panel(page, label, x_min=60, x_max=400, y_min=40, y_max=900, limit=50):
    items = page.evaluate(f"""() => {{
        var items = [];
        var excluded = ['path','line','circle','g','svg','defs','rect','polygon',
                        'clippath','HTML','BODY','HEAD','SCRIPT','STYLE','META','LINK'];
        for (const el of document.querySelectorAll('*')) {{
            var r = el.getBoundingClientRect();
            if (r.x >= {x_min} && r.x <= {x_max} && r.y >= {y_min} && r.y <= {y_max}
                && r.width > 10 && r.height > 10 && r.width < 400
                && !excluded.includes(el.tagName.toUpperCase())) {{
                var text = (el.innerText || '').trim().substring(0, 50);
                var info = {{
                    tag: el.tagName, x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    text: text.replace(/\\n/g, ' ').substring(0, 40),
                    classes: (el.className || '').toString().substring(0, 35),
                }};
                if (el.tagName === 'IMG') info.src = (el.src || '').substring(0, 60);
                if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') {{
                    info.placeholder = (el.placeholder || '').substring(0, 30);
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
        }}).sort(function(a,b) {{ return a.y - b.y; }}).slice(0, {limit});
    }}""")
    print(f"\n  {label} ({len(items)} elements):", flush=True)
    for el in items:
        extra = ''
        if el.get('src'): extra += f" src={el['src']}"
        if el.get('placeholder'): extra += f" ph='{el['placeholder']}'"
        t = el['text'][:35] if el.get('text') else ''
        print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> c='{el['classes'][:25]}' '{t}'{extra}", flush=True)
    return items


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

    # ============================================================
    #  PART 1: TXT2IMG PANEL — DEEP DIVE
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 1: TXT2IMG PANEL DEEP DIVE", flush=True)
    print("=" * 60, flush=True)

    # Click Txt2Img sidebar icon by coordinate (icon center at 40, 197)
    page.mouse.click(40, 197)
    page.wait_for_timeout(2000)
    close_dialogs(page)
    ss(page, "P77_01_txt2img_panel")

    # Check if panel opened
    panel = page.evaluate("""() => {
        var p = document.querySelector('.panels.show');
        if (p) {
            var r = p.getBoundingClientRect();
            return {x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    classes: (p.className || '').toString().substring(0, 50)};
        }
        return null;
    }""")
    print(f"  Panels.show: {panel}", flush=True)

    if panel:
        dump_panel(page, "Txt2Img panel", x_min=panel['x'], x_max=panel['x'] + panel['w'],
                   y_min=panel['y'], y_max=panel['y'] + panel['h'])

        # Click Advanced to expand
        adv = page.evaluate("""() => {
            for (const el of document.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                var r = el.getBoundingClientRect();
                if (text === 'Advanced' && r.x >= 80 && r.x <= 350 && r.y > 400) {
                    el.click();
                    return {x: Math.round(r.x), y: Math.round(r.y)};
                }
            }
            return null;
        }""")
        print(f"\n  Advanced clicked: {adv}", flush=True)
        page.wait_for_timeout(1000)
        ss(page, "P77_02_txt2img_advanced")

        # Check for advanced popup/expanded area
        dump_panel(page, "Txt2Img after Advanced", x_min=60, x_max=600, y_min=300, y_max=900)

        # Close advanced popup
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)

        # Scroll down to see Generate button area
        page.mouse.move(200, 500)
        page.mouse.wheel(0, 300)
        page.wait_for_timeout(500)

        dump_panel(page, "Txt2Img scrolled down", x_min=panel['x'], x_max=panel['x'] + panel['w'],
                   y_min=40, y_max=900)

        ss(page, "P77_03_txt2img_scrolled")

    else:
        print("  Txt2Img panel did not open. Checking DOM...", flush=True)
        # Try finding any panel
        all_panels = page.evaluate("""() => {
            var panels = [];
            for (const el of document.querySelectorAll('[class*="panel"]')) {
                var r = el.getBoundingClientRect();
                if (r.width > 100 && r.height > 100 && r.x < 500) {
                    panels.push({
                        tag: el.tagName,
                        classes: (el.className || '').toString().substring(0, 50),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        visible: r.width > 0 && r.height > 0,
                    });
                }
            }
            return panels.slice(0, 10);
        }""")
        print(f"  All panel-like elements:", flush=True)
        for p in all_panels:
            print(f"    ({p['x']},{p['y']}) {p['w']}x{p['h']} vis={p['visible']} c='{p['classes'][:40]}'", flush=True)

    # ============================================================
    #  PART 2: IMG2IMG — TRY ICON CLICK + DOUBLE CLICK
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 2: IMG2IMG — ICON CLICK ATTEMPTS", flush=True)
    print("=" * 60, flush=True)

    # First click Txt2Img to ensure a different panel is active
    page.mouse.click(40, 197)
    page.wait_for_timeout(1000)
    close_dialogs(page)

    # Now click Img2Img icon center (40, 252) — not the text
    page.mouse.click(40, 252)
    page.wait_for_timeout(2000)
    close_dialogs(page)

    panel2 = page.evaluate("""() => {
        var p = document.querySelector('.panels.show');
        if (p) {
            var h5 = p.querySelector('h5');
            var title = h5 ? (h5.innerText || '').trim() : '';
            var r = p.getBoundingClientRect();
            return {title: title, x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height)};
        }
        return null;
    }""")
    print(f"  Img2Img panels.show: {panel2}", flush=True)

    if panel2:
        ss(page, "P77_04_img2img_panel")
        dump_panel(page, "Img2Img panel", x_min=panel2['x'], x_max=panel2['x'] + panel2['w'],
                   y_min=panel2['y'], y_max=panel2['y'] + panel2['h'])
    else:
        # Try double-click
        page.mouse.dblclick(40, 252)
        page.wait_for_timeout(2000)
        close_dialogs(page)

        panel2b = page.evaluate("""() => {
            var p = document.querySelector('.panels.show');
            if (p) {
                var h5 = p.querySelector('h5');
                return h5 ? (h5.innerText || '').trim() : 'panel found, no h5';
            }
            return null;
        }""")
        print(f"  Img2Img double-click result: {panel2b}", flush=True)

        # Check for tool-group active state
        active = page.evaluate("""() => {
            var groups = document.querySelectorAll('.tool-group');
            for (var g of groups) {
                var cls = (g.className || '').toString();
                if (cls.includes('active') || cls.includes('selected')) {
                    var text = (g.innerText || '').trim();
                    return {text: text, classes: cls.substring(0, 50)};
                }
            }
            return null;
        }""")
        print(f"  Active sidebar tool: {active}", flush=True)

        ss(page, "P77_04_img2img_attempt")

    # ============================================================
    #  PART 3: AI VIDEO — DIRECT SIDEBAR ICON CLICK
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 3: AI VIDEO — DIRECT ICON CLICK", flush=True)
    print("=" * 60, flush=True)

    # Toggle to Txt2Img first, then AI Video
    page.mouse.click(40, 197)
    page.wait_for_timeout(1000)
    # AI Video icon at (40, 361)
    page.mouse.click(40, 361)
    page.wait_for_timeout(2000)
    close_dialogs(page)

    panel3 = page.evaluate("""() => {
        var p = document.querySelector('.panels.show');
        if (p) {
            var h5 = p.querySelector('h5');
            var title = h5 ? (h5.innerText || '').trim() : 'no title';
            var r = p.getBoundingClientRect();
            return {title: title, x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height)};
        }
        return null;
    }""")
    print(f"  AI Video panels.show: {panel3}", flush=True)

    if panel3:
        ss(page, "P77_05_ai_video_panel")
        dump_panel(page, "AI Video panel", x_min=panel3['x'], x_max=panel3['x'] + panel3['w'],
                   y_min=panel3['y'], y_max=panel3['y'] + panel3['h'])
    else:
        # Check if a different mechanism is used
        # Maybe AI Video opens a totally different page/route
        current_url = page.url
        print(f"  Current URL: {current_url}", flush=True)

        # Check for any new elements that appeared anywhere
        new_els = page.evaluate("""() => {
            var items = [];
            for (const el of document.querySelectorAll('.ai-video, [class*="video-panel"], [class*="ai-video"]')) {
                var r = el.getBoundingClientRect();
                items.push({
                    tag: el.tagName,
                    classes: (el.className || '').toString().substring(0, 50),
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    text: (el.innerText || '').substring(0, 40).replace(/\\n/g, ' '),
                });
            }
            return items;
        }""")
        print(f"  AI Video DOM elements: {new_els}", flush=True)
        ss(page, "P77_05_ai_video_attempt")

    # ============================================================
    #  PART 4: CHECK WHICH PANELS USE .panels.show
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 4: PANEL MECHANISM SURVEY", flush=True)
    print("=" * 60, flush=True)

    # Click each sidebar tool and check if .panels.show appears
    sidebar_tools = [
        ("Upload", 40, 81),
        ("Assets", 40, 136),
        ("Txt2Img", 40, 197),
        ("Img2Img", 40, 252),
        ("Character", 40, 306),
        ("AI Video", 40, 361),
        ("Lip Sync", 40, 425),
        ("Video Editor", 40, 490),
        ("Motion Control", 40, 550),
        ("Enhance", 40, 627),
        ("Image Editor", 40, 698),
        ("Storyboard", 40, 766),
    ]

    results = []
    for name, x, y in sidebar_tools:
        # Click Txt2Img first (toggle reset)
        page.mouse.click(40, 197)
        page.wait_for_timeout(300)
        # Click target
        page.mouse.click(x, y)
        page.wait_for_timeout(1500)
        close_dialogs(page)

        panel_info = page.evaluate("""() => {
            var p = document.querySelector('.panels.show');
            if (p) {
                var h5 = p.querySelector('h5');
                var title = h5 ? (h5.innerText || '').trim() : '';
                var r = p.getBoundingClientRect();
                return {title: title, w: Math.round(r.width), h: Math.round(r.height),
                        visible: r.width > 0 && r.height > 0};
            }
            return null;
        }""")
        has_panel = panel_info is not None and panel_info.get('visible', False)
        title = panel_info['title'] if panel_info else 'none'
        results.append((name, has_panel, title))
        print(f"    {name}: panel={'YES' if has_panel else 'NO'} title='{title}'", flush=True)

    print(f"\n  Summary:", flush=True)
    for name, has, title in results:
        print(f"    {name}: {'PANEL' if has else 'NO PANEL'} ({title})", flush=True)

    print(f"\n\n===== PHASE 77 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
