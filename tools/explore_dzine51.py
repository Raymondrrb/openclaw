"""Phase 51: Txt2Img deep dive (Face Match, Color Match, Advanced) + Insert Character flow.

From P50:
- Insert Character panel: Lasso/Brush/Auto mask, Choose Character, 28 credits
- Face Match/Color Match/Advanced not found — panel was switched by Insert Character click
- Need to open Txt2Img fresh and scroll to find these features

Goals:
1. Open Txt2Img fresh, scroll to bottom to map ALL settings including Face Match, Color Match, Advanced
2. Toggle Face Match ON, explore its UI (upload zone, strength)
3. Toggle Color Match ON, explore its UI
4. Expand Advanced section (seed, negative prompt, etc.)
5. Test Insert Character "Choose a Character" and "Auto" mask mode
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


def dump_panel_full(page, label, x_min, x_max, y_min, y_max, limit=50):
    """Dump all text elements in a rectangular region."""
    items = page.evaluate(f"""() => {{
        var items = [];
        for (const el of document.querySelectorAll('*')) {{
            var r = el.getBoundingClientRect();
            if (r.x >= {x_min} && r.x <= {x_max} && r.y >= {y_min} && r.y <= {y_max}
                && r.width > 8 && r.height > 6 && r.width < 400
                && !['path','line','circle','g','svg','defs','rect','polygon','clippath','HTML','BODY','HEAD','SCRIPT','STYLE'].includes(el.tagName.toLowerCase())) {{
                var text = (el.innerText || '').trim();
                if (text.length > 0 && text.length < 60) {{
                    var cursor = window.getComputedStyle(el).cursor;
                    var bg = window.getComputedStyle(el).backgroundColor;
                    items.push({{
                        tag: el.tagName,
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        text: text.substring(0, 45),
                        classes: (el.className || '').toString().substring(0, 35),
                        cursor: cursor !== 'auto' && cursor !== 'default' ? cursor : '',
                        bg: bg && bg !== 'rgba(0, 0, 0, 0)' && bg !== 'transparent' ? bg : '',
                    }});
                }}
            }}
        }}
        var seen = new Set();
        return items.filter(function(i) {{
            var key = i.text.substring(0,12) + '|' + i.x + '|' + i.y;
            if (seen.has(key)) return false;
            seen.add(key);
            return true;
        }}).sort(function(a,b) {{ return a.y - b.y; }});
    }}""")
    print(f"\n  {label} ({len(items)} unique):", flush=True)
    for el in items[:limit]:
        extras = []
        if el['cursor']:
            extras.append(f"cur={el['cursor']}")
        if el['bg']:
            extras.append(f"bg={el['bg']}")
        extra_str = ' ' + ' '.join(extras) if extras else ''
        print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}>{extra_str} '{el['text'][:40]}'", flush=True)
    return items


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

    # ============================================================
    #  PART 1: TXT2IMG FULL PANEL MAP (SCROLLED)
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 1: TXT2IMG FULL PANEL MAP", flush=True)
    print("=" * 60, flush=True)

    # Open Txt2Img fresh
    page.mouse.click(40, 197)
    page.wait_for_timeout(2000)
    close_dialogs(page)

    # First dump what's visible without scrolling
    dump_panel_full(page, "Txt2Img visible (no scroll)", 60, 360, 50, 900)

    ss(page, "P51_01_txt2img_top")

    # Now scroll down the left panel to find Face Match, Color Match, Advanced
    # The panel container is the scrollable area
    print("\n  Scrolling down the panel...", flush=True)

    # Find the scrollable container for the Txt2Img panel
    scroll_container = page.evaluate("""() => {
        // Look for the scrollable container in the left panel
        for (const el of document.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            if (r.x > 60 && r.x < 100 && r.width > 200 && r.width < 300
                && r.height > 400 && el.scrollHeight > el.clientHeight) {
                return {
                    tag: el.tagName,
                    classes: (el.className || '').toString().substring(0, 60),
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    scrollH: el.scrollHeight,
                    clientH: el.clientHeight,
                    scrollTop: el.scrollTop,
                };
            }
        }
        return null;
    }""")
    print(f"  Scroll container: {scroll_container}", flush=True)

    if scroll_container:
        # Scroll to bottom of the panel
        page.evaluate("""() => {
            for (const el of document.querySelectorAll('*')) {
                var r = el.getBoundingClientRect();
                if (r.x > 60 && r.x < 100 && r.width > 200 && r.width < 300
                    && r.height > 400 && el.scrollHeight > el.clientHeight) {
                    el.scrollTop = el.scrollHeight;
                    return true;
                }
            }
            return false;
        }""")
        page.wait_for_timeout(1000)
    else:
        # Fallback: scroll via mouse wheel
        page.mouse.move(200, 400)
        for _ in range(5):
            page.mouse.wheel(0, 300)
            page.wait_for_timeout(300)

    page.wait_for_timeout(1000)
    ss(page, "P51_02_txt2img_scrolled")

    # Dump what's visible after scrolling
    dump_panel_full(page, "Txt2Img after scroll", 60, 360, 50, 900)

    # Specifically look for Face Match, Color Match, Advanced toggles/sections
    special_elements = page.evaluate("""() => {
        var items = [];
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (r.x > 60 && r.x < 360 && r.width > 50 && r.height > 6) {
                if (text === 'Face Match' || text === 'Color Match' || text === 'Advanced'
                    || text === 'Face Match NEW' || text === 'Seed'
                    || text === 'Negative Prompt' || text === 'Non-Explicit'
                    || text === 'Generation Mode' || text === 'Generate') {
                    var classes = (el.className || '').toString();
                    items.push({
                        text: text,
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        tag: el.tagName,
                        classes: classes.substring(0, 40),
                    });
                }
            }
        }
        return items.sort(function(a,b) { return a.y - b.y; });
    }""")
    print(f"\n  Special elements found ({len(special_elements)}):", flush=True)
    for el in special_elements:
        print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> c='{el['classes'][:30]}' '{el['text']}'", flush=True)

    # If still not found, try scrolling partway instead of all the way
    if not any('Face Match' in el['text'] for el in special_elements):
        print("\n  Face Match still not visible, trying partial scroll...", flush=True)
        # Scroll back to top first
        page.evaluate("""() => {
            for (const el of document.querySelectorAll('*')) {
                var r = el.getBoundingClientRect();
                if (r.x > 60 && r.x < 100 && r.width > 200 && r.width < 300
                    && r.height > 400 && el.scrollHeight > el.clientHeight) {
                    el.scrollTop = 0;
                    return true;
                }
            }
            return false;
        }""")
        page.wait_for_timeout(500)

        # Scroll down in increments and check each time
        for scroll_px in [200, 400, 600, 800, 1000, 1200]:
            page.evaluate(f"""() => {{
                for (const el of document.querySelectorAll('*')) {{
                    var r = el.getBoundingClientRect();
                    if (r.x > 60 && r.x < 100 && r.width > 200 && r.width < 300
                        && r.height > 400 && el.scrollHeight > el.clientHeight) {{
                        el.scrollTop = {scroll_px};
                        return true;
                    }}
                }}
                return false;
            }}""")
            page.wait_for_timeout(300)

            found = page.evaluate("""() => {
                for (const el of document.querySelectorAll('*')) {
                    var text = (el.innerText || '').trim();
                    var r = el.getBoundingClientRect();
                    if ((text === 'Face Match' || text.startsWith('Face Match'))
                        && r.x > 60 && r.x < 360 && r.y > 0 && r.y < 900) {
                        return {text: text, x: Math.round(r.x), y: Math.round(r.y)};
                    }
                }
                return null;
            }""")
            if found:
                print(f"  Found at scroll={scroll_px}: {found}", flush=True)
                break
            else:
                print(f"  scroll={scroll_px}: not found", flush=True)

    # Also try using mouse wheel to scroll the panel
    if not any('Face Match' in el['text'] for el in special_elements):
        print("\n  Trying mouse wheel scroll...", flush=True)
        # Reset scroll
        page.evaluate("""() => {
            for (const el of document.querySelectorAll('*')) {
                var r = el.getBoundingClientRect();
                if (r.x > 60 && r.x < 100 && r.width > 200 && r.width < 300
                    && r.height > 400 && el.scrollHeight > el.clientHeight) {
                    el.scrollTop = 0;
                    return true;
                }
            }
            return false;
        }""")
        page.wait_for_timeout(500)

        # Position mouse over panel and scroll
        page.mouse.move(200, 500)
        for i in range(10):
            page.mouse.wheel(0, 150)
            page.wait_for_timeout(200)

            found = page.evaluate("""() => {
                for (const el of document.querySelectorAll('*')) {
                    var text = (el.innerText || '').trim();
                    var r = el.getBoundingClientRect();
                    if ((text === 'Face Match' || text.startsWith('Face Match'))
                        && r.x > 60 && r.x < 360 && r.y > 0 && r.y < 900) {
                        return {text: text, x: Math.round(r.x), y: Math.round(r.y),
                                w: Math.round(r.width), h: Math.round(r.height)};
                    }
                }
                return null;
            }""")
            if found:
                print(f"  Found Face Match after {i+1} wheel scrolls: {found}", flush=True)
                break
        else:
            print("  Face Match NOT found after 10 scrolls", flush=True)

    # Take a screenshot of current state
    ss(page, "P51_03_txt2img_scrolled_final")

    # Dump the full visible state
    dump_panel_full(page, "Txt2Img final scroll state", 60, 360, 50, 900)

    # ============================================================
    #  PART 2: TOGGLE FACE MATCH AND EXPLORE
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 2: FACE MATCH TOGGLE", flush=True)
    print("=" * 60, flush=True)

    # Search for Face Match toggle by looking at all switch/toggle buttons
    all_toggles = page.evaluate("""() => {
        var items = [];
        for (const btn of document.querySelectorAll('button')) {
            var classes = (btn.className || '').toString();
            var r = btn.getBoundingClientRect();
            if (r.x > 60 && r.x < 360 && r.width > 25 && r.width < 55 && r.height > 12 && r.height < 30
                && (classes.includes('switch') || classes.includes('toggle'))) {
                // Find label text near this toggle
                var label = '';
                var parent = btn.parentElement;
                for (var i = 0; i < 3 && parent; i++) {
                    var siblings = parent.querySelectorAll('*');
                    for (var j = 0; j < siblings.length; j++) {
                        var sib = siblings[j];
                        var sr = sib.getBoundingClientRect();
                        var st = (sib.innerText || '').trim();
                        if (Math.abs(sr.y - r.y) < 20 && sr.x < r.x && st.length > 2 && st.length < 30) {
                            label = st;
                            break;
                        }
                    }
                    if (label) break;
                    parent = parent.parentElement;
                }
                var bg = window.getComputedStyle(btn).backgroundColor;
                items.push({
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    classes: classes.substring(0, 40),
                    bg: bg,
                    label: label,
                    isActive: bg.includes('255') || classes.includes('active') || classes.includes('on'),
                });
            }
        }
        return items.sort(function(a,b) { return a.y - b.y; });
    }""")
    print(f"  All toggles in panel ({len(all_toggles)}):", flush=True)
    for t in all_toggles:
        print(f"    ({t['x']},{t['y']}) {t['w']}x{t['h']} label='{t['label']}' active={t['isActive']} bg={t['bg']}", flush=True)

    # Click Face Match toggle if found
    face_match_btn = None
    for t in all_toggles:
        if 'Face Match' in t['label'] or 'Face' in t['label']:
            face_match_btn = t
            break

    if face_match_btn:
        print(f"\n  Clicking Face Match toggle at ({face_match_btn['x']},{face_match_btn['y']})...", flush=True)
        page.mouse.click(face_match_btn['x'] + face_match_btn['w']//2,
                         face_match_btn['y'] + face_match_btn['h']//2)
        page.wait_for_timeout(2000)
        close_dialogs(page)

        ss(page, "P51_04_face_match_on")

        # Dump what appeared below the toggle
        dump_panel_full(page, "After Face Match ON", 60, 360,
                        face_match_btn['y'] - 20, face_match_btn['y'] + 200)

        # Look for upload/pick-image controls
        fm_controls = page.evaluate("""() => {
            var items = [];
            for (const el of document.querySelectorAll('*')) {
                var r = el.getBoundingClientRect();
                var classes = (el.className || '').toString();
                var text = (el.innerText || '').trim();
                if (r.x > 60 && r.x < 360 && r.width > 30
                    && (classes.includes('pick') || classes.includes('upload')
                        || classes.includes('image') && r.width < 300
                        || text.includes('Pick') || text.includes('Upload')
                        || text.includes('Drop') || text.includes('Strength'))) {
                    items.push({
                        text: text.substring(0, 40),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        tag: el.tagName,
                        classes: classes.substring(0, 40),
                    });
                }
            }
            return items.sort(function(a,b) { return a.y - b.y; }).slice(0, 15);
        }""")
        print(f"\n  Face Match controls ({len(fm_controls)}):", flush=True)
        for el in fm_controls:
            print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> c='{el['classes'][:30]}' '{el['text'][:30]}'", flush=True)

        # Toggle OFF
        page.mouse.click(face_match_btn['x'] + face_match_btn['w']//2,
                         face_match_btn['y'] + face_match_btn['h']//2)
        page.wait_for_timeout(1000)
    else:
        print("  Face Match toggle NOT found among toggles", flush=True)
        # Try broader search: look for ANY element containing "Face Match" text
        fm_any = page.evaluate("""() => {
            var items = [];
            for (const el of document.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                if (text.includes('Face Match')) {
                    var r = el.getBoundingClientRect();
                    items.push({
                        text: text.substring(0, 50),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        tag: el.tagName,
                        classes: (el.className || '').toString().substring(0, 40),
                        visible: r.width > 0 && r.height > 0,
                    });
                }
            }
            return items;
        }""")
        print(f"  Broad 'Face Match' search ({len(fm_any)}):", flush=True)
        for el in fm_any:
            print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} vis={el['visible']} <{el['tag']}> '{el['text'][:40]}'", flush=True)

    # ============================================================
    #  PART 3: COLOR MATCH
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 3: COLOR MATCH", flush=True)
    print("=" * 60, flush=True)

    color_match_btn = None
    for t in all_toggles:
        if 'Color' in t['label']:
            color_match_btn = t
            break

    if color_match_btn:
        print(f"  Clicking Color Match toggle at ({color_match_btn['x']},{color_match_btn['y']})...", flush=True)
        page.mouse.click(color_match_btn['x'] + color_match_btn['w']//2,
                         color_match_btn['y'] + color_match_btn['h']//2)
        page.wait_for_timeout(2000)
        close_dialogs(page)

        ss(page, "P51_05_color_match_on")
        dump_panel_full(page, "After Color Match ON", 60, 360,
                        color_match_btn['y'] - 20, color_match_btn['y'] + 200)

        # Toggle OFF
        page.mouse.click(color_match_btn['x'] + color_match_btn['w']//2,
                         color_match_btn['y'] + color_match_btn['h']//2)
        page.wait_for_timeout(1000)
    else:
        print("  Color Match toggle NOT found", flush=True)

    # ============================================================
    #  PART 4: ADVANCED SECTION
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 4: ADVANCED SECTION", flush=True)
    print("=" * 60, flush=True)

    # Find Advanced element
    adv = page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text === 'Advanced' && r.x > 60 && r.x < 360 && r.width > 80 && r.y > 0 && r.y < 900) {
                return {
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    tag: el.tagName,
                    classes: (el.className || '').toString().substring(0, 40),
                };
            }
        }
        return null;
    }""")

    if adv:
        print(f"  Advanced found at ({adv['x']},{adv['y']}) c='{adv['classes']}'", flush=True)
        # Click to expand
        page.mouse.click(adv['x'] + adv['w']//2, adv['y'] + adv['h']//2)
        page.wait_for_timeout(1500)

        # Scroll a bit to see content
        page.mouse.move(200, 500)
        page.mouse.wheel(0, 200)
        page.wait_for_timeout(500)

        ss(page, "P51_06_advanced")
        dump_panel_full(page, "Advanced expanded", 60, 360, adv['y'] - 10, 900)

        # Specifically check for inputs and sliders
        inputs = page.evaluate("""() => {
            var items = [];
            for (const el of document.querySelectorAll('input, textarea')) {
                var r = el.getBoundingClientRect();
                if (r.x > 60 && r.x < 360 && r.width > 30 && r.y > 0 && r.y < 900) {
                    items.push({
                        tag: el.tagName,
                        type: el.type || '',
                        placeholder: el.placeholder || '',
                        value: el.value || '',
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                    });
                }
            }
            return items.sort(function(a,b) { return a.y - b.y; });
        }""")
        print(f"\n  Inputs ({len(inputs)}):", flush=True)
        for inp in inputs:
            print(f"    ({inp['x']},{inp['y']}) {inp['w']}x{inp['h']} <{inp['tag']}> type={inp['type']} ph='{inp['placeholder'][:30]}' val='{inp['value'][:20]}'", flush=True)
    else:
        print("  Advanced NOT found in visible area", flush=True)
        # Broad search
        adv_any = page.evaluate("""() => {
            var items = [];
            for (const el of document.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                if (text === 'Advanced') {
                    var r = el.getBoundingClientRect();
                    items.push({
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        tag: el.tagName,
                        visible: r.width > 0 && r.height > 0 && r.y > -100 && r.y < 2000,
                    });
                }
            }
            return items;
        }""")
        print(f"  Broad 'Advanced' search: {adv_any}", flush=True)

    # ============================================================
    #  PART 5: INSERT CHARACTER - CHOOSE CHARACTER + AUTO MASK
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 5: INSERT CHARACTER WORKFLOW", flush=True)
    print("=" * 60, flush=True)

    # First, we need a result image. Check if there are existing CC results.
    results_imgs = page.evaluate("""() => {
        var imgs = [];
        for (const img of document.querySelectorAll('img')) {
            var src = img.src || '';
            if (src.includes('static.dzine.ai/stylar_product')) {
                var r = img.getBoundingClientRect();
                imgs.push({src: src.substring(src.length-50), x: Math.round(r.x), y: Math.round(r.y),
                           w: Math.round(r.width), h: Math.round(r.height)});
            }
        }
        return imgs.slice(0, 5);
    }""")
    print(f"  Result images: {len(results_imgs)}", flush=True)

    # Switch to Results tab
    page.mouse.click(1096, 49)
    page.wait_for_timeout(1000)

    # Find Insert Character "1" button for the first result
    ic_btn = page.evaluate("""() => {
        // Find first "Insert Character" label
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text === 'Insert Character' && r.x > 1100 && r.y > 100 && r.y < 600) {
                // Find "1" button at same y
                for (const btn of document.querySelectorAll('button')) {
                    var bt = (btn.innerText || '').trim();
                    var br = btn.getBoundingClientRect();
                    if (bt === '1' && Math.abs(br.y - r.y) < 15 && br.x > 1200) {
                        return {
                            label_y: Math.round(r.y),
                            btn_x: Math.round(br.x + br.width/2),
                            btn_y: Math.round(br.y + br.height/2),
                        };
                    }
                }
            }
        }
        return null;
    }""")

    if ic_btn:
        print(f"  Insert Character '1' at ({ic_btn['btn_x']},{ic_btn['btn_y']})", flush=True)
        page.mouse.click(ic_btn['btn_x'], ic_btn['btn_y'])
        page.wait_for_timeout(3000)
        close_dialogs(page)

        ss(page, "P51_07_insert_character")

        # Click "Choose a Character" button
        chose = page.evaluate("""() => {
            for (const el of document.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                var r = el.getBoundingClientRect();
                var classes = (el.className || '').toString();
                if ((text === 'Choose a Character' || classes.includes('character-choose'))
                    && r.x > 60 && r.x < 360 && r.width > 100) {
                    return {
                        text: text,
                        x: Math.round(r.x + r.width/2),
                        y: Math.round(r.y + r.height/2),
                        w: Math.round(r.width), h: Math.round(r.height),
                    };
                }
            }
            return null;
        }""")
        if chose:
            print(f"  Clicking 'Choose a Character' at ({chose['x']},{chose['y']})...", flush=True)
            page.mouse.click(chose['x'], chose['y'])
            page.wait_for_timeout(2000)
            close_dialogs(page)

            ss(page, "P51_08_character_chooser")

            # Check what opened (character gallery?)
            char_gallery = page.evaluate("""() => {
                var items = [];
                for (const el of document.querySelectorAll('*')) {
                    var r = el.getBoundingClientRect();
                    var text = (el.innerText || '').trim();
                    var style = window.getComputedStyle(el);
                    var zIndex = parseInt(style.zIndex) || 0;
                    if (zIndex > 50 && r.width > 100 && r.height > 50
                        && text.length > 0 && text.length < 50) {
                        items.push({
                            text: text.substring(0, 40),
                            x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height),
                            z: zIndex,
                            tag: el.tagName,
                        });
                    }
                }
                return items.sort(function(a,b) { return a.y - b.y; }).slice(0, 20);
            }""")
            print(f"\n  Character chooser dialog ({len(char_gallery)}):", flush=True)
            for el in char_gallery:
                print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} z={el['z']} <{el['tag']}> '{el['text'][:35]}'", flush=True)

            # Look for Ray character
            ray_btn = page.evaluate("""() => {
                for (const el of document.querySelectorAll('*')) {
                    var text = (el.innerText || '').trim();
                    if (text === 'Ray' && el.tagName === 'BUTTON') {
                        var r = el.getBoundingClientRect();
                        return {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)};
                    }
                }
                return null;
            }""")
            print(f"\n  Ray button: {ray_btn}", flush=True)

            if ray_btn:
                print(f"  Clicking Ray at ({ray_btn['x']},{ray_btn['y']})...", flush=True)
                page.evaluate("""() => {
                    for (const el of document.querySelectorAll('*')) {
                        var text = (el.innerText || '').trim();
                        if (text === 'Ray' && el.tagName === 'BUTTON') {
                            el.click(); return true;
                        }
                    }
                    return false;
                }""")
                page.wait_for_timeout(2000)
                close_dialogs(page)

                ss(page, "P51_09_ray_selected")

                # Check the panel state after Ray is selected
                dump_panel_full(page, "After Ray selected", 60, 360, 240, 560)

        # Now try the "Auto" mask mode
        auto_btn = page.evaluate("""() => {
            for (const btn of document.querySelectorAll('button')) {
                var text = (btn.innerText || '').trim();
                var classes = (btn.className || '').toString();
                var r = btn.getBoundingClientRect();
                if (text === 'Auto' && classes.includes('auto') && r.x > 60 && r.x < 360) {
                    return {
                        x: Math.round(r.x + r.width/2),
                        y: Math.round(r.y + r.height/2),
                        classes: classes.substring(0, 40),
                    };
                }
            }
            return null;
        }""")
        if auto_btn:
            print(f"\n  Clicking 'Auto' mask at ({auto_btn['x']},{auto_btn['y']})...", flush=True)
            page.mouse.click(auto_btn['x'], auto_btn['y'])
            page.wait_for_timeout(2000)

            ss(page, "P51_10_auto_mask")

            # Check what happened (auto-mask should detect objects in the image)
            mask_state = page.evaluate("""() => {
                var items = [];
                for (const el of document.querySelectorAll('*')) {
                    var r = el.getBoundingClientRect();
                    var text = (el.innerText || '').trim();
                    if (r.x > 60 && r.x < 360 && r.width > 100
                        && text.length > 2 && text.length < 60
                        && r.y > 100 && r.y < 300) {
                        items.push({
                            text: text.substring(0, 50),
                            x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height),
                            tag: el.tagName,
                        });
                    }
                }
                return items.sort(function(a,b) { return a.y - b.y; }).slice(0, 10);
            }""")
            print(f"  Auto mask state ({len(mask_state)}):", flush=True)
            for el in mask_state:
                print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> '{el['text'][:40]}'", flush=True)

            # Check if there's a "Select All" or auto-detected objects
            canvas_overlay = page.evaluate("""() => {
                // Check for mask overlay elements on the canvas
                var items = [];
                for (const el of document.querySelectorAll('*')) {
                    var classes = (el.className || '').toString();
                    var r = el.getBoundingClientRect();
                    if (r.x > 300 && r.x < 1100 && r.y > 50 && r.y < 800
                        && r.width > 50 && r.height > 50
                        && (classes.includes('mask') || classes.includes('overlay')
                            || classes.includes('canvas') || classes.includes('select'))) {
                        items.push({
                            x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height),
                            classes: classes.substring(0, 60),
                            tag: el.tagName,
                        });
                    }
                }
                return items.slice(0, 10);
            }""")
            print(f"\n  Canvas overlay elements ({len(canvas_overlay)}):", flush=True)
            for el in canvas_overlay:
                print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> c='{el['classes'][:50]}'", flush=True)
    else:
        print("  Insert Character button NOT found in visible results", flush=True)

    ss(page, "P51_11_final")
    print(f"\n\n===== PHASE 51 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
