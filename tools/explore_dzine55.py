"""Phase 55: Advanced popup (Seed), "More" aspect ratios dropdown, panel CSS classes.

From P54:
- Advanced section = popup at (362,65) 280x146, class='advanced-content show', contains 'Seed'
- "More" ratios button at (296,378) 24x24, class='item more', SVG icon
- Panel toggle: double-click Txt2Img or Img2Img→Txt2Img

Goals:
1. Open Txt2Img panel, click "More" ratios → dump dropdown
2. Click Advanced → dump popup content (Seed, negative prompt, etc.)
3. Check if Advanced content changes by model
4. Document CSS classes for automation
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


def dump_region(page, label, x_min, x_max, y_min, y_max, limit=40):
    items = page.evaluate(f"""() => {{
        var items = [];
        for (const el of document.querySelectorAll('*')) {{
            var r = el.getBoundingClientRect();
            if (r.x >= {x_min} && r.x <= {x_max} && r.y >= {y_min} && r.y <= {y_max}
                && r.width > 8 && r.height > 5 && r.width < 400
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
    print(f"\n  {label} ({len(items)} elements):", flush=True)
    for el in items[:limit]:
        print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> c='{el['classes'][:22]}' '{el['text'][:40]}'", flush=True)
    return items


def activate_txt2img(page):
    """Activate Txt2Img panel using panel toggle technique."""
    page.mouse.click(40, 252)  # Img2Img
    page.wait_for_timeout(500)
    page.mouse.click(40, 197)  # Txt2Img
    page.wait_for_timeout(1500)

    # Check if active
    header = page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text === 'Text to Image' && r.x > 60 && r.x < 200 && r.y > 40 && r.y < 100) {
                return true;
            }
        }
        return false;
    }""")
    if not header:
        # Retry with double-click
        page.mouse.click(40, 197)
        page.wait_for_timeout(200)
        page.mouse.click(40, 197)
        page.wait_for_timeout(2000)
    close_dialogs(page)
    return header


def main():
    print("Connecting...", flush=True)
    pw = sync_playwright().start()
    browser = pw.chromium.connect_over_cdp("http://127.0.0.1:18800", timeout=15000)
    ctx = browser.contexts[0]
    page = ctx.new_page()
    page.set_viewport_size({"width": 1440, "height": 900})

    page.goto(CANVAS_URL, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(5000)
    close_dialogs(page)

    # Activate Txt2Img
    activate_txt2img(page)

    # ============================================================
    #  PART 1: "MORE" ASPECT RATIOS
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 1: MORE ASPECT RATIOS", flush=True)
    print("=" * 60, flush=True)

    # Click the "more" button at (296,378) — class='item more'
    more_clicked = page.evaluate("""() => {
        var el = document.querySelector('.c-aspect-ratio .item.more');
        if (el) {
            el.click();
            var r = el.getBoundingClientRect();
            return {x: Math.round(r.x), y: Math.round(r.y)};
        }
        return null;
    }""")
    print(f"  More button clicked: {more_clicked}", flush=True)
    page.wait_for_timeout(1500)

    if more_clicked:
        ss(page, "P55_01_more_ratios")

        # Dump the dropdown/popup that appeared
        more_dropdown = page.evaluate("""() => {
            var items = [];
            for (const el of document.querySelectorAll('*')) {
                var style = window.getComputedStyle(el);
                var z = parseInt(style.zIndex) || 0;
                var r = el.getBoundingClientRect();
                var text = (el.innerText || '').trim();
                if (z > 50 && r.width > 30 && r.height > 10 && text.length > 1 && text.length < 40
                    && r.y > 200 && r.y < 700) {
                    var cursor = style.cursor;
                    items.push({
                        text: text,
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        z: z,
                        cursor: cursor !== 'auto' ? cursor : '',
                        tag: el.tagName,
                        classes: (el.className || '').toString().substring(0, 30),
                    });
                }
            }
            var seen = new Set();
            return items.filter(function(i) {
                var key = i.text.substring(0,15) + '|' + i.y;
                if (seen.has(key)) return false;
                seen.add(key);
                return true;
            }).sort(function(a,b) { return a.y - b.y; });
        }""")
        print(f"\n  More dropdown ({len(more_dropdown)}):", flush=True)
        for el in more_dropdown:
            extra = f" cur={el['cursor']}" if el['cursor'] else ''
            print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} z={el['z']} <{el['tag']}>{extra} c='{el['classes'][:20]}' '{el['text']}'", flush=True)

        # Also look for any popup/overlay that appeared
        overlay = page.evaluate("""() => {
            var items = [];
            for (const el of document.querySelectorAll('.aspect-ratio-popover, .popover, [class*="dropdown"], [class*="popup"]')) {
                var r = el.getBoundingClientRect();
                if (r.width > 100 && r.height > 50) {
                    items.push({
                        classes: (el.className || '').toString().substring(0, 60),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                    });
                }
            }
            return items;
        }""")
        print(f"\n  Overlay/popover elements ({len(overlay)}):", flush=True)
        for o in overlay:
            print(f"    ({o['x']},{o['y']}) {o['w']}x{o['h']} c='{o['classes'][:50]}'", flush=True)

        # Close dropdown
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)
    else:
        # Fallback: click at the known position
        print("  Trying click at (308,390)...", flush=True)
        page.mouse.click(308, 390)
        page.wait_for_timeout(1500)
        ss(page, "P55_01b_more_ratios")

        # Check for any new visible high-z elements
        popup = page.evaluate("""() => {
            var items = [];
            for (const el of document.querySelectorAll('*')) {
                var style = window.getComputedStyle(el);
                var z = parseInt(style.zIndex) || 0;
                if (z > 100) {
                    var r = el.getBoundingClientRect();
                    var text = (el.innerText || '').trim();
                    if (r.width > 50 && r.height > 20 && text.length > 2 && text.length < 200) {
                        items.push({
                            text: text.substring(0, 60),
                            x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height), z: z,
                        });
                    }
                }
            }
            return items.sort(function(a,b) { return b.z - a.z; }).slice(0, 10);
        }""")
        print(f"  High-z elements: {len(popup)}", flush=True)
        for p in popup:
            print(f"    ({p['x']},{p['y']}) {p['w']}x{p['h']} z={p['z']} '{p['text'][:50]}'", flush=True)

        page.keyboard.press("Escape")
        page.wait_for_timeout(500)

    # ============================================================
    #  PART 2: ADVANCED POPUP
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 2: ADVANCED POPUP", flush=True)
    print("=" * 60, flush=True)

    # Click Advanced section
    adv_clicked = page.evaluate("""() => {
        for (const el of document.querySelectorAll('.params *')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text === 'Advanced' && r.x > 60 && r.x < 360 && r.y > 600 && r.y < 750) {
                el.click();
                return {x: Math.round(r.x), y: Math.round(r.y)};
            }
        }
        return null;
    }""")
    if not adv_clicked:
        # Try clicking at known position
        page.mouse.click(200, 670)
        adv_clicked = {'x': 200, 'y': 670}
    print(f"  Advanced clicked: {adv_clicked}", flush=True)
    page.wait_for_timeout(1500)

    ss(page, "P55_02_advanced_popup")

    # Dump the advanced popup content (from P54: at x=362, y=65)
    adv_popup = page.evaluate("""() => {
        var popup = document.querySelector('.advanced-content.show');
        if (!popup) {
            // Try broader search
            for (const el of document.querySelectorAll('[class*="advanced-content"]')) {
                if (el.getBoundingClientRect().width > 0) {
                    popup = el;
                    break;
                }
            }
        }
        if (!popup) return null;

        var r = popup.getBoundingClientRect();
        var items = [];
        var children = popup.querySelectorAll('*');
        for (var i = 0; i < children.length; i++) {
            var ch = children[i];
            var cr = ch.getBoundingClientRect();
            var text = (ch.innerText || '').trim();
            if (cr.width > 8 && cr.height > 5 && text.length > 0 && text.length < 60
                && !['path','line','circle','g','svg','defs'].includes(ch.tagName.toLowerCase())) {
                var tag = ch.tagName;
                var classes = (ch.className || '').toString();
                items.push({
                    tag: tag,
                    text: text.substring(0, 40),
                    x: Math.round(cr.x), y: Math.round(cr.y),
                    w: Math.round(cr.width), h: Math.round(cr.height),
                    classes: classes.substring(0, 40),
                    type: ch.type || '',
                    placeholder: ch.placeholder || '',
                    value: (ch.value || '').substring(0, 20),
                });
            }
        }
        var seen = new Set();
        items = items.filter(function(i) {
            var key = i.text.substring(0,12) + '|' + i.x + '|' + i.y;
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
        }).sort(function(a,b) { return a.y - b.y; });

        return {
            popup: {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)},
            items: items,
        };
    }""")

    if adv_popup:
        print(f"\n  Advanced popup: ({adv_popup['popup']['x']},{adv_popup['popup']['y']}) {adv_popup['popup']['w']}x{adv_popup['popup']['h']}", flush=True)
        print(f"  Items ({len(adv_popup['items'])}):", flush=True)
        for el in adv_popup['items']:
            extras = []
            if el['type']:
                extras.append(f"type={el['type']}")
            if el['placeholder']:
                extras.append(f"ph='{el['placeholder'][:20]}'")
            if el['value']:
                extras.append(f"val='{el['value'][:15]}'")
            extra_str = ' ' + ' '.join(extras) if extras else ''
            print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> c='{el['classes'][:25]}'{extra_str} '{el['text'][:35]}'", flush=True)
    else:
        print("  Advanced popup NOT found", flush=True)
        # Try dumping the region where we expect it
        dump_region(page, "Expected Advanced area", 340, 680, 50, 250)

    # ============================================================
    #  PART 3: ADVANCED INPUTS (SEED, NEGATIVE PROMPT)
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 3: ADVANCED INPUTS", flush=True)
    print("=" * 60, flush=True)

    # Find all input/textarea elements in the advanced popup area
    adv_inputs = page.evaluate("""() => {
        var items = [];
        for (const el of document.querySelectorAll('input, textarea')) {
            var r = el.getBoundingClientRect();
            if (r.x > 340 && r.x < 700 && r.y > 40 && r.y < 300 && r.width > 30) {
                items.push({
                    tag: el.tagName,
                    type: el.type || '',
                    placeholder: (el.placeholder || '').substring(0, 40),
                    value: (el.value || '').substring(0, 30),
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    name: el.name || '',
                    classes: (el.className || '').toString().substring(0, 30),
                });
            }
        }
        return items.sort(function(a,b) { return a.y - b.y; });
    }""")
    print(f"  Advanced inputs ({len(adv_inputs)}):", flush=True)
    for inp in adv_inputs:
        print(f"    ({inp['x']},{inp['y']}) {inp['w']}x{inp['h']} <{inp['tag']}> type={inp['type']} c='{inp['classes'][:20]}' ph='{inp['placeholder'][:30]}' val='{inp['value'][:20]}'", flush=True)

    # Also check for sliders or number inputs
    adv_sliders = page.evaluate("""() => {
        var items = [];
        // Check in the advanced-content area
        var popup = document.querySelector('.advanced-content.show');
        if (!popup) return items;

        for (const el of popup.querySelectorAll('input[type="range"], input[type="number"], [class*="slider"]')) {
            var r = el.getBoundingClientRect();
            items.push({
                tag: el.tagName,
                type: el.type || '',
                min: el.min || '',
                max: el.max || '',
                value: el.value || '',
                x: Math.round(r.x), y: Math.round(r.y),
                w: Math.round(r.width), h: Math.round(r.height),
            });
        }
        return items;
    }""")
    print(f"\n  Advanced sliders/numbers ({len(adv_sliders)}):", flush=True)
    for s in adv_sliders:
        print(f"    ({s['x']},{s['y']}) {s['w']}x{s['h']} <{s['tag']}> type={s['type']} min={s['min']} max={s['max']} val={s['value']}", flush=True)

    # Close Advanced popup
    page.mouse.click(200, 670)  # Click Advanced again to toggle off
    page.wait_for_timeout(500)

    # ============================================================
    #  PART 4: CONFIRM RESULTS PANEL ACTION BEHAVIOR
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 4: RESULTS ACTION BEHAVIOR SUMMARY", flush=True)
    print("=" * 60, flush=True)

    # Check results panel for generation status (Variation from P53 might still be there)
    results_status = page.evaluate("""() => {
        var items = [];
        for (const el of document.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            var text = (el.innerText || '').trim();
            var classes = (el.className || '').toString();
            if (r.x > 1060 && r.y > 50 && r.y < 200 && r.width > 50
                && (text.includes('Private') || text.includes('Variation')
                    || text.includes('Consistent') || text.includes('Text-to')
                    || classes.includes('progress'))) {
                items.push({
                    text: text.substring(0, 40),
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    classes: classes.substring(0, 30),
                });
            }
        }
        return items.sort(function(a,b) { return a.y - b.y; }).slice(0, 10);
    }""")
    print(f"  Results panel status ({len(results_status)}):", flush=True)
    for el in results_status:
        print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} c='{el['classes'][:20]}' '{el['text'][:35]}'", flush=True)

    print("""
  === ACTION BUTTON BEHAVIOR SUMMARY ===

  From Results Panel, each action button behaves as follows:

  DIRECT GENERATION (one-click, no editing panel):
  - Variation: Generates a variation of the image, result appears in Results panel
  - Chat Editor: Opens chat at bottom bar for text editing
  - AI Video: Starts video generation from the image
  - Lip Sync: Starts lip sync generation
  - Face Swap: Triggers face swap processing
  - Enhance & Upscale: Starts upscaling

  OPENS EDITING PANEL (requires user input):
  - Insert Character: Opens mask+character editing panel (28 credits)
  - Image Editor: Opens Image Editor sidebar tools
  - Expression Edit: Opens expression slider panel (4 credits)
""", flush=True)

    ss(page, "P55_03_final")
    print(f"\n\n===== PHASE 55 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
