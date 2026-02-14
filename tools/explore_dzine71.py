"""Phase 71: Expression Edit Template mode (targeted), full feature inventory check.

Previous attempts to click Expression Edit "1" from Results panel failed intermittently.
Strategy: Use the layer-tools toolbar "Expression" button instead (more reliable).

Goals:
1. Open Expression Edit via toolbar "Expression" button at (606, 82)
2. Click Template tab and map all template presets
3. Verify all documented sidebar tool positions still work
4. Count total result entries and their types
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


def dump_region(page, label, x_min, x_max, y_min, y_max, limit=50):
    items = page.evaluate(f"""() => {{
        var items = [];
        for (const el of document.querySelectorAll('*')) {{
            var r = el.getBoundingClientRect();
            if (r.x >= {x_min} && r.x <= {x_max} && r.y >= {y_min} && r.y <= {y_max}
                && r.width > 8 && r.height > 5 && r.width < 500
                && !['path','line','circle','g','svg','defs','rect','polygon','clippath','HTML','BODY','HEAD','SCRIPT','STYLE'].includes(el.tagName.toLowerCase())) {{
                var text = (el.innerText || '').trim();
                if (text.length > 0 && text.length < 60) {{
                    items.push({{
                        tag: el.tagName, x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        text: text.substring(0, 45),
                        classes: (el.className || '').toString().substring(0, 30),
                    }});
                }}
            }}
        }}
        var seen = new Set();
        return items.filter(function(i) {{
            var key = i.text.substring(0,15) + '|' + i.x + '|' + i.y;
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
        }}).sort(function(a,b) {{ return a.y - b.y; }});
    }}""")
    print(f"\\n  {label} ({len(items)} elements):", flush=True)
    for el in items[:limit]:
        print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> c='{el['classes'][:22]}' '{el['text'][:40]}'", flush=True)
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
    #  PART 1: SELECT LAYER + OPEN EXPRESSION VIA TOOLBAR
    # ============================================================
    print("\\n" + "=" * 60, flush=True)
    print("  PART 1: EXPRESSION EDIT VIA TOOLBAR", flush=True)
    print("=" * 60, flush=True)

    # Switch to Layers tab and select an image layer (not text)
    page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text === 'Layers' && r.x > 1200 && r.y < 60) {
                el.click(); return true;
            }
        }
        return false;
    }""")
    page.wait_for_timeout(500)

    # Click Layer 4 (image layer)
    page.evaluate("""() => {
        for (const btn of document.querySelectorAll('button.layer-item')) {
            var text = (btn.innerText || '').trim();
            if (text.includes('Layer 4')) {
                btn.click(); return true;
            }
        }
        // Fallback: first non-locked layer
        for (const btn of document.querySelectorAll('button.layer-item')) {
            var classes = (btn.className || '').toString();
            if (!classes.includes('locked')) {
                btn.click(); return true;
            }
        }
        return false;
    }""")
    page.wait_for_timeout(1000)

    # Check if layer-tools bar appeared
    tools_visible = page.evaluate("""() => {
        var bar = document.querySelector('.layer-tools');
        if (!bar) return false;
        var r = bar.getBoundingClientRect();
        return r.width > 100 && r.height > 20;
    }""")
    print(f"  Layer tools visible: {tools_visible}", flush=True)

    # Click "Expression" in the toolbar
    expr_clicked = page.evaluate("""() => {
        var bar = document.querySelector('.layer-tools');
        if (!bar) return null;
        for (const btn of bar.querySelectorAll('button')) {
            var text = (btn.innerText || '').trim();
            if (text === 'Expression') {
                btn.click();
                var r = btn.getBoundingClientRect();
                return {x: Math.round(r.x), y: Math.round(r.y)};
            }
        }
        return null;
    }""")
    print(f"  Expression toolbar clicked: {expr_clicked}", flush=True)
    page.wait_for_timeout(3000)
    close_dialogs(page)

    ss(page, "P71_01_expression_opened")

    # Check if Expression Edit panel is open
    header = page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text.includes('Expression') && r.x > 40 && r.x < 200
                && r.y > 20 && r.y < 80 && r.height < 35) {
                return text;
            }
        }
        return null;
    }""")
    print(f"  Panel header: {header}", flush=True)

    if header and 'Expression' in header:
        # Dump Custom mode first
        dump_region(page, "Expression Custom mode", 40, 180, 40, 500)

        # Click Template tab
        template = page.evaluate("""() => {
            for (const el of document.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                var r = el.getBoundingClientRect();
                if (text === 'Template' && r.x > 80 && r.x < 180
                    && r.y > 140 && r.y < 200) {
                    el.click();
                    return {x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), tag: el.tagName};
                }
            }
            return null;
        }""")
        print(f"\\n  Template tab clicked: {template}", flush=True)
        page.wait_for_timeout(1000)

        ss(page, "P71_02_expression_template")

        # Dump template area
        dump_region(page, "Expression Template area", 40, 180, 140, 900)

        # Get ALL elements including images in the template area
        template_all = page.evaluate("""() => {
            var items = [];
            for (const el of document.querySelectorAll('*')) {
                var r = el.getBoundingClientRect();
                var classes = (el.className || '').toString();
                var text = (el.innerText || '').trim();
                if (r.x >= 40 && r.x <= 180 && r.y >= 180 && r.y <= 900
                    && r.width > 15 && r.height > 15) {
                    var info = {
                        tag: el.tagName,
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        classes: classes.substring(0, 40),
                        text: text.substring(0, 30),
                    };
                    if (el.tagName === 'IMG') {
                        info.src = (el.src || '').substring(0, 60);
                        info.alt = (el.alt || '').substring(0, 30);
                    }
                    if (el.style && el.style.backgroundImage) {
                        info.bgImg = el.style.backgroundImage.substring(0, 60);
                    }
                    items.push(info);
                }
            }
            var seen = new Set();
            return items.filter(function(i) {
                var key = i.tag + '|' + i.x + '|' + i.y;
                if (seen.has(key)) return false;
                seen.add(key);
                return true;
            }).sort(function(a,b) { return a.y - b.y || a.x - b.x; }).slice(0, 30);
        }""")
        print(f"\\n  All template elements ({len(template_all)}):", flush=True)
        for t in template_all:
            extra = ''
            if t.get('src'): extra += f" src={t['src']}"
            if t.get('alt'): extra += f" alt={t['alt']}"
            if t.get('bgImg'): extra += f" bg={t['bgImg']}"
            print(f"    ({t['x']},{t['y']}) {t['w']}x{t['h']} <{t['tag']}> c='{t['classes'][:25]}' '{t['text'][:20]}'{extra}", flush=True)

    else:
        print("  Expression Edit panel not found! Trying alternative...", flush=True)
        # Try clicking directly on the canvas face
        page.mouse.click(700, 350)  # Approximate face position
        page.wait_for_timeout(500)
        # Then try toolbar Expression again
        page.evaluate("""() => {
            var bar = document.querySelector('.layer-tools');
            if (!bar) return false;
            for (const btn of bar.querySelectorAll('button')) {
                if ((btn.innerText || '').trim() === 'Expression') {
                    btn.click(); return true;
                }
            }
            return false;
        }""")
        page.wait_for_timeout(3000)
        close_dialogs(page)
        ss(page, "P71_01b_expression_retry")
        dump_region(page, "Expression retry", 40, 200, 40, 500)

    # Close
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)

    # ============================================================
    #  PART 2: FEATURE INVENTORY — COUNT RESULTS
    # ============================================================
    print("\\n" + "=" * 60, flush=True)
    print("  PART 2: FEATURE INVENTORY", flush=True)
    print("=" * 60, flush=True)

    # Switch to Results
    page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text === 'Results' && r.x > 1050 && r.y < 60) {
                el.click(); return true;
            }
        }
        return false;
    }""")
    page.wait_for_timeout(1000)

    # Count result entries by type
    results = page.evaluate("""() => {
        var items = [];
        for (const el of document.querySelectorAll('.result-item')) {
            var classes = (el.className || '').toString();
            var text = (el.innerText || '').substring(0, 50);
            var r = el.getBoundingClientRect();
            var type = 'unknown';
            if (classes.includes('consistent')) type = 'Consistent Character';
            else if (classes.includes('txt2img')) type = 'Text to Image';
            else if (classes.includes('img2img')) type = 'Image to Image';
            else if (classes.includes('variation')) type = 'Variation';
            items.push({type: type, y: Math.round(r.y), classes: classes.substring(0, 50)});
        }
        return items.sort(function(a,b) { return a.y - b.y; });
    }""")
    print(f"  Result entries ({len(results)}):", flush=True)
    for r in results:
        print(f"    y={r['y']} type='{r['type']}' c='{r['classes'][:35]}'", flush=True)

    # Count total images
    total_images = page.evaluate("""() => {
        var count = 0;
        for (const img of document.querySelectorAll('img')) {
            if ((img.src || '').includes('static.dzine.ai/stylar_product')) count++;
        }
        return count;
    }""")
    print(f"\\n  Total generated images in project: {total_images}", flush=True)

    # Final screenshot
    ss(page, "P71_03_final")

    print(f"\\n\\n===== PHASE 71 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
