"""Phase 79: AI Video deep dive — Reference mode, Camera controls, model selector.
Also explore Generate 360 Video via Character menu.
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


def dump_panel_show(page, label, limit=50):
    """Dump content of .panels.show container."""
    items = page.evaluate(f"""() => {{
        var p = document.querySelector('.panels.show');
        if (!p) return [];
        var items = [];
        var excluded = ['path','line','circle','g','svg','defs','rect','polygon',
                        'clippath','HTML','BODY','HEAD','SCRIPT','STYLE','META','LINK'];
        for (const el of p.querySelectorAll('*')) {{
            var r = el.getBoundingClientRect();
            if (r.width > 10 && r.height > 10 && r.width < 300
                && !excluded.includes(el.tagName.toUpperCase())) {{
                var text = (el.innerText || '').trim();
                if (text.length > 0 && text.length < 50 && text.indexOf('\\n') === -1) {{
                    items.push({{
                        tag: el.tagName, x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        text: text.substring(0, 40),
                        classes: (el.className || '').toString().substring(0, 35),
                    }});
                }}
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
    title = page.evaluate("""() => {
        var p = document.querySelector('.panels.show');
        if (!p) return 'NONE';
        var h5 = p.querySelector('h5');
        return h5 ? (h5.innerText || '').trim() : 'no h5';
    }""")
    print(f"\n  {label} — title='{title}' ({len(items)} elements):", flush=True)
    for el in items:
        print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> c='{el['classes'][:25]}' '{el['text'][:35]}'", flush=True)
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
    #  PART 1: AI VIDEO — REFERENCE MODE
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 1: AI VIDEO — REFERENCE MODE", flush=True)
    print("=" * 60, flush=True)

    # Toggle from Storyboard to AI Video
    page.mouse.click(40, 766)  # Storyboard
    page.wait_for_timeout(1500)
    close_dialogs(page)
    page.mouse.click(40, 361)  # AI Video
    page.wait_for_timeout(2000)
    close_dialogs(page)
    ss(page, "P79_01_ai_video_keyframe")

    dump_panel_show(page, "AI Video — Key Frame mode")

    # Click "Reference" tab
    ref_click = page.evaluate("""() => {
        var p = document.querySelector('.panels.show');
        if (!p) return null;
        for (const btn of p.querySelectorAll('button')) {
            if ((btn.innerText || '').trim() === 'Reference') {
                btn.click();
                return true;
            }
        }
        return null;
    }""")
    print(f"\n  Reference tab clicked: {ref_click}", flush=True)
    page.wait_for_timeout(1500)
    ss(page, "P79_02_ai_video_reference")

    dump_panel_show(page, "AI Video — Reference mode")

    # Click Camera control
    cam = page.evaluate("""() => {
        var p = document.querySelector('.panels.show');
        if (!p) return null;
        for (const el of p.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            if (text === 'Camera' && el.getBoundingClientRect().width > 50) {
                el.click();
                return {text: text, tag: el.tagName};
            }
        }
        return null;
    }""")
    print(f"\n  Camera clicked: {cam}", flush=True)
    page.wait_for_timeout(1000)
    ss(page, "P79_03_camera_control")

    # Dump camera options
    cam_items = page.evaluate("""() => {
        var items = [];
        for (const el of document.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            var cs = window.getComputedStyle(el);
            var z = parseInt(cs.zIndex) || 0;
            if (z > 200 && r.width > 100 && r.height > 50 && r.x < 600) {
                var text = (el.innerText || '').trim().replace(/\\n/g, ' ').substring(0, 80);
                if (text.length > 5) {
                    items.push({
                        z: z, tag: el.tagName,
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        classes: (el.className || '').toString().substring(0, 40),
                        text: text.substring(0, 60),
                    });
                }
            }
        }
        return items.sort(function(a,b) { return b.z - a.z; }).slice(0, 5);
    }""")
    print(f"\n  Camera popup ({len(cam_items)}):", flush=True)
    for c in cam_items:
        print(f"    z={c['z']} ({c['x']},{c['y']}) {c['w']}x{c['h']} '{c['text'][:50]}'", flush=True)

    # Get detailed camera controls if popup appeared
    if cam_items:
        px = cam_items[0]
        cam_detail = page.evaluate(f"""() => {{
            var items = [];
            for (const el of document.querySelectorAll('*')) {{
                var r = el.getBoundingClientRect();
                if (r.x >= {px['x']} && r.x <= {px['x'] + px['w']}
                    && r.y >= {px['y']} && r.y <= {px['y'] + px['h']}
                    && r.width > 15 && r.height > 10 && r.width < 200) {{
                    var text = (el.innerText || '').trim();
                    if (text.length > 0 && text.length < 30 && text.indexOf('\\n') === -1) {{
                        items.push({{
                            tag: el.tagName, x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height),
                            text: text,
                            classes: (el.className || '').toString().substring(0, 30),
                        }});
                    }}
                }}
            }}
            var seen = new Set();
            return items.filter(function(i) {{
                var key = i.text + '|' + i.y;
                if (seen.has(key)) return false;
                seen.add(key);
                return true;
            }}).sort(function(a,b) {{ return a.y - b.y; }}).slice(0, 30);
        }}""")
        print(f"\n  Camera controls detail ({len(cam_detail)}):", flush=True)
        for d in cam_detail:
            print(f"    ({d['x']},{d['y']}) {d['w']}x{d['h']} <{d['tag']}> c='{d['classes'][:20]}' '{d['text']}'", flush=True)

    page.keyboard.press("Escape")
    page.wait_for_timeout(500)

    # Scroll down for Generate button and credits
    page.mouse.move(200, 600)
    page.mouse.wheel(0, 300)
    page.wait_for_timeout(500)
    ss(page, "P79_04_ai_video_scrolled")

    # Get generate button and credits
    gen_info = page.evaluate("""() => {
        var p = document.querySelector('.panels.show');
        if (!p) return null;
        var genBtn = p.querySelector('.btn-generate button, button.generative');
        if (genBtn) {
            var r = genBtn.getBoundingClientRect();
            return {
                text: (genBtn.innerText || '').trim().substring(0, 40),
                x: Math.round(r.x), y: Math.round(r.y),
                w: Math.round(r.width), h: Math.round(r.height),
            };
        }
        return null;
    }""")
    print(f"\n  Generate button: {gen_info}", flush=True)

    # ============================================================
    #  PART 2: AI VIDEO — MODEL SELECTOR
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 2: AI VIDEO — MODEL SELECTOR", flush=True)
    print("=" * 60, flush=True)

    # Scroll back to top
    page.mouse.wheel(0, -1000)
    page.wait_for_timeout(500)

    # Click model selector dropdown
    model_click = page.evaluate("""() => {
        var p = document.querySelector('.panels.show');
        if (!p) return null;
        var btn = p.querySelector('.selected-btn-content');
        if (btn) {
            btn.click();
            return (btn.innerText || '').trim().substring(0, 40);
        }
        return null;
    }""")
    print(f"  Model selector clicked: '{model_click}'", flush=True)
    page.wait_for_timeout(1500)
    ss(page, "P79_05_ai_video_models")

    # Dump model dropdown
    model_items = page.evaluate("""() => {
        var items = [];
        for (const el of document.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            var cs = window.getComputedStyle(el);
            var z = parseInt(cs.zIndex) || 0;
            if (z > 300 && r.width > 150 && r.height > 100 && r.x < 500) {
                // Found the dropdown
                for (const child of el.querySelectorAll('*')) {
                    var cr = child.getBoundingClientRect();
                    var text = (child.innerText || '').trim();
                    if (text.length > 2 && text.length < 40 && text.indexOf('\\n') === -1
                        && cr.height > 10 && cr.height < 50 && cr.width > 30) {
                        items.push({
                            tag: child.tagName, x: Math.round(cr.x), y: Math.round(cr.y),
                            text: text,
                            classes: (child.className || '').toString().substring(0, 30),
                        });
                    }
                }
                break;
            }
        }
        var seen = new Set();
        return items.filter(function(i) {
            var key = i.text;
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
        }).sort(function(a,b) { return a.y - b.y; }).slice(0, 20);
    }""")
    print(f"\n  AI Video models ({len(model_items)}):", flush=True)
    for m in model_items:
        print(f"    y={m['y']} <{m['tag']}> c='{m['classes'][:20]}' '{m['text']}'", flush=True)

    page.keyboard.press("Escape")
    page.wait_for_timeout(500)

    # ============================================================
    #  PART 3: GENERATE 360 VIDEO (via Character menu)
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 3: GENERATE 360 VIDEO (Character menu)", flush=True)
    print("=" * 60, flush=True)

    # Open Character menu (double-click)
    page.mouse.dblclick(40, 306)
    page.wait_for_timeout(2000)
    close_dialogs(page)

    # Click "Generate 360° Video"
    vid360 = page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            if (text.includes('360') && text.includes('Video')) {
                var r = el.getBoundingClientRect();
                if (r.width > 100 && r.height > 20) {
                    el.click();
                    return {text: text, x: Math.round(r.x), y: Math.round(r.y)};
                }
            }
        }
        return null;
    }""")
    print(f"  360 Video clicked: {vid360}", flush=True)
    page.wait_for_timeout(2000)
    close_dialogs(page)
    ss(page, "P79_06_360_video")

    dump_panel_show(page, "Generate 360 Video panel")

    # Check for panels.show title
    title360 = page.evaluate("""() => {
        var p = document.querySelector('.panels.show');
        if (!p) return 'NONE';
        var h5 = p.querySelector('h5');
        return h5 ? (h5.innerText || '').trim() : 'no h5';
    }""")
    print(f"\n  360 panel title: {title360}", flush=True)

    print(f"\n\n===== PHASE 79 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
