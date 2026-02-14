"""Phase 75: Explore remaining features — AI Video (via result action), Chat Editor,
Export button, Assets panel, and Upload panel.
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
        }}).sort(function(a,b) {{ return a.y - b.y; }}).slice(0, {limit});
    }}""")
    print(f"\n  {label} ({len(items)} elements):", flush=True)
    for el in items:
        extra = ''
        if el.get('src'): extra += f" src={el['src']}"
        if el.get('placeholder'): extra += f" ph='{el['placeholder']}'"
        t = el['text'][:30] if el.get('text') else ''
        print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> c='{el['classes'][:22]}' '{t}'{extra}", flush=True)
    return items


def click_sidebar(page, name):
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

    # ============================================================
    #  PART 1: AI VIDEO — TRY VIA RESULT ACTION BUTTON
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 1: AI VIDEO VIA RESULT ACTION", flush=True)
    print("=" * 60, flush=True)

    # Switch to Results and click "AI Video" → "1" button
    page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            if ((el.innerText || '').trim() === 'Results'
                && el.getBoundingClientRect().x > 500
                && el.getBoundingClientRect().y < 60) {
                el.click(); return true;
            }
        }
        return false;
    }""")
    page.wait_for_timeout(1000)

    # Find "AI Video" row and click "1"
    av_result = page.evaluate("""() => {
        // Find the AI Video row in the results panel
        var rows = document.querySelectorAll('.result-item, [class*="action"]');
        for (const row of document.querySelectorAll('*')) {
            var text = (row.innerText || '').trim();
            var r = row.getBoundingClientRect();
            // Match "AI Video" text specifically
            if (text === 'AI Video' && r.x > 500 && r.y > 60) {
                // Found the label — find "1" button nearby (sibling or in parent)
                var parent = row.parentElement;
                if (parent) {
                    var btns = parent.querySelectorAll('*');
                    for (var btn of btns) {
                        var bt = (btn.innerText || '').trim();
                        var br = btn.getBoundingClientRect();
                        if (bt === '1' && br.x > r.x + 50 && br.width < 40 && br.height < 30) {
                            btn.click();
                            return {action: 'clicked 1', x: Math.round(br.x), y: Math.round(br.y)};
                        }
                    }
                }
                return {action: 'found label but no 1 button', x: Math.round(r.x), y: Math.round(r.y)};
            }
        }
        return null;
    }""")
    print(f"  AI Video result action: {av_result}", flush=True)
    page.wait_for_timeout(3000)
    close_dialogs(page)
    ss(page, "P75_01_ai_video_via_result")

    # Check what opened
    dump_panel(page, "After AI Video click", x_min=60, x_max=400, y_min=40, y_max=600)

    # Also check for overlay/dialog
    overlay = page.evaluate("""() => {
        var overlays = [];
        for (const el of document.querySelectorAll('*')) {
            var cs = window.getComputedStyle(el);
            var z = parseInt(cs.zIndex) || 0;
            var r = el.getBoundingClientRect();
            if (z > 100 && r.width > 200 && r.height > 200) {
                overlays.push({
                    tag: el.tagName, z: z,
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    classes: (el.className || '').toString().substring(0, 40),
                    text: (el.innerText || '').substring(0, 60).replace(/\\n/g, ' '),
                });
            }
        }
        return overlays.sort(function(a,b) { return b.z - a.z; }).slice(0, 5);
    }""")
    print(f"\n  High-z overlays ({len(overlay)}):", flush=True)
    for o in overlay:
        print(f"    z={o['z']} ({o['x']},{o['y']}) {o['w']}x{o['h']} <{o['tag']}> c='{o['classes'][:25]}' '{o['text'][:40]}'", flush=True)

    # Press Escape to close any opened panel
    page.keyboard.press("Escape")
    page.wait_for_timeout(1000)

    # ============================================================
    #  PART 2: CHAT EDITOR — VIA RESULT ACTION
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 2: CHAT EDITOR VIA RESULT ACTION", flush=True)
    print("=" * 60, flush=True)

    chat_result = page.evaluate("""() => {
        for (const row of document.querySelectorAll('*')) {
            var text = (row.innerText || '').trim();
            var r = row.getBoundingClientRect();
            if (text === 'Chat Editor' && r.x > 500 && r.y > 60) {
                var parent = row.parentElement;
                if (parent) {
                    var btns = parent.querySelectorAll('*');
                    for (var btn of btns) {
                        var bt = (btn.innerText || '').trim();
                        var br = btn.getBoundingClientRect();
                        if (bt === '1' && br.x > r.x + 50 && br.width < 40 && br.height < 30) {
                            btn.click();
                            return {action: 'clicked 1', x: Math.round(br.x), y: Math.round(br.y)};
                        }
                    }
                }
                return {action: 'found label only', x: Math.round(r.x), y: Math.round(r.y)};
            }
        }
        return null;
    }""")
    print(f"  Chat Editor result action: {chat_result}", flush=True)
    page.wait_for_timeout(3000)
    close_dialogs(page)
    ss(page, "P75_02_chat_editor")

    # Check for chat editor panel/overlay
    dump_panel(page, "Chat Editor panel check", x_min=0, x_max=1440, y_min=600, y_max=900, limit=30)

    # Also check the bottom bar where chat typically is
    bottom = page.evaluate("""() => {
        var items = [];
        for (const el of document.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            if (r.y > 800 && r.x > 200 && r.x < 1200
                && r.width > 30 && r.height > 15 && r.height < 100) {
                var text = (el.innerText || '').trim();
                if (text.length > 0 && text.length < 50) {
                    items.push({
                        tag: el.tagName, x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        text: text.substring(0, 40),
                        classes: (el.className || '').toString().substring(0, 30),
                    });
                }
            }
        }
        var seen = new Set();
        return items.filter(function(i) {
            var key = i.text.substring(0, 15) + '|' + i.x;
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
        }).sort(function(a,b) { return a.y - b.y; }).slice(0, 20);
    }""")
    print(f"\n  Bottom bar elements ({len(bottom)}):", flush=True)
    for b in bottom:
        print(f"    ({b['x']},{b['y']}) {b['w']}x{b['h']} <{b['tag']}> c='{b['classes'][:22]}' '{b['text'][:35]}'", flush=True)

    page.keyboard.press("Escape")
    page.wait_for_timeout(1000)

    # ============================================================
    #  PART 3: EXPORT BUTTON
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 3: EXPORT BUTTON", flush=True)
    print("=" * 60, flush=True)

    # Find and click Export button in top-right
    export_click = page.evaluate("""() => {
        for (const el of document.querySelectorAll('button, [role="button"]')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text === 'Export' && r.x > 1200 && r.y < 40) {
                el.click();
                return {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width)};
            }
        }
        return null;
    }""")
    print(f"  Export clicked: {export_click}", flush=True)
    page.wait_for_timeout(2000)
    close_dialogs(page)
    ss(page, "P75_03_export")

    # Dump export dialog/dropdown
    if export_click:
        export_items = page.evaluate("""() => {
            var items = [];
            for (const el of document.querySelectorAll('*')) {
                var r = el.getBoundingClientRect();
                var cs = window.getComputedStyle(el);
                var z = parseInt(cs.zIndex) || 0;
                if (r.x > 1000 && r.y < 400 && r.width > 30 && r.height > 10
                    && r.width < 400 && r.height < 50) {
                    var text = (el.innerText || '').trim();
                    if (text.length > 0 && text.length < 50 && text.indexOf('\\n') === -1) {
                        items.push({
                            tag: el.tagName, x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height),
                            text: text.substring(0, 40),
                            classes: (el.className || '').toString().substring(0, 30),
                            z: z,
                        });
                    }
                }
            }
            var seen = new Set();
            return items.filter(function(i) {
                var key = i.text.substring(0, 15) + '|' + i.y;
                if (seen.has(key)) return false;
                seen.add(key);
                return true;
            }).sort(function(a,b) { return a.y - b.y; }).slice(0, 30);
        }""")
        print(f"\n  Export menu ({len(export_items)}):", flush=True)
        for e in export_items:
            print(f"    ({e['x']},{e['y']}) {e['w']}x{e['h']} z={e['z']} <{e['tag']}> c='{e['classes'][:22]}' '{e['text'][:35]}'", flush=True)

    page.keyboard.press("Escape")
    page.wait_for_timeout(500)

    # ============================================================
    #  PART 4: ASSETS PANEL
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 4: ASSETS PANEL", flush=True)
    print("=" * 60, flush=True)

    click_sidebar(page, "Txt2Img")
    page.wait_for_timeout(1000)
    close_dialogs(page)

    click_sidebar(page, "Assets")
    page.wait_for_timeout(2000)
    close_dialogs(page)
    ss(page, "P75_04_assets")

    dump_panel(page, "Assets panel")

    # ============================================================
    #  PART 5: UPLOAD PANEL
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 5: UPLOAD PANEL", flush=True)
    print("=" * 60, flush=True)

    click_sidebar(page, "Txt2Img")
    page.wait_for_timeout(1000)
    close_dialogs(page)

    click_sidebar(page, "Upload")
    page.wait_for_timeout(2000)
    close_dialogs(page)
    ss(page, "P75_05_upload")

    dump_panel(page, "Upload panel")

    # ============================================================
    #  PART 6: EARN CREDITS / BUY CREDITS BUTTON
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 6: EARN CREDITS BUTTON", flush=True)
    print("=" * 60, flush=True)

    earn = page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text === 'Earn Credits' && r.y < 40 && r.x > 900) {
                return {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width),
                        tag: el.tagName};
            }
        }
        return null;
    }""")
    print(f"  Earn Credits button: {earn}", flush=True)

    # Get top bar info strip
    topbar = page.evaluate("""() => {
        var items = [];
        for (const el of document.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            if (r.y < 35 && r.x > 700 && r.height < 30 && r.width > 20 && r.width < 200) {
                var text = (el.innerText || '').trim();
                if (text.length > 0 && text.length < 40 && text.indexOf('\\n') === -1
                    && el.children.length <= 1) {
                    items.push({
                        tag: el.tagName, x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        text: text.substring(0, 35),
                        classes: (el.className || '').toString().substring(0, 25),
                    });
                }
            }
        }
        var seen = new Set();
        return items.filter(function(i) {
            var key = i.text + '|' + i.x;
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
        }).sort(function(a,b) { return a.x - b.x; }).slice(0, 15);
    }""")
    print(f"\n  Top bar info ({len(topbar)}):", flush=True)
    for t in topbar:
        print(f"    ({t['x']},{t['y']}) {t['w']}x{t['h']} <{t['tag']}> '{t['text']}'", flush=True)

    print(f"\n\n===== PHASE 75 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
