"""Phase 50: Insert Character workflow, Face Match NEW, Color Match, Advanced, Upload-to-canvas.

From P49:
- Results panel shows 9 action buttons with "1"/"2" variant selectors
- Insert Character is at y~291, buttons "1" at x=1274, "2" at x=1349
- Face Match NEW discovered in Txt2Img panel
- Color Match discovered in Txt2Img panel
- Advanced section discovered in Txt2Img panel
- Upload sidebar has no left panel (just collapses other panels)

Goals:
1. Click "Insert Character" variant "1" button → see what panel opens
2. Explore Face Match NEW toggle and UI
3. Explore Color Match feature
4. Explore Advanced section (seed, negative prompt, etc.)
5. Test Upload-to-canvas via file chooser on the canvas itself
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


def dump_panel(page, label, x_min, x_max, y_min, y_max, limit=40):
    """Dump all visible elements in a rectangular region."""
    items = page.evaluate(f"""() => {{
        var items = [];
        for (const el of document.querySelectorAll('*')) {{
            var r = el.getBoundingClientRect();
            if (r.x > {x_min} && r.x < {x_max} && r.y > {y_min} && r.y < {y_max}
                && r.width > 10 && r.height > 6 && r.width < 400
                && !['path','line','circle','g','svg','defs','rect','polygon','clippath','HTML','BODY','HEAD'].includes(el.tagName.toLowerCase())) {{
                var text = (el.innerText || '').trim();
                if (text.length > 0 && text.length < 50) {{
                    var cursor = window.getComputedStyle(el).cursor;
                    items.push({{
                        tag: el.tagName,
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        text: text.substring(0, 40),
                        classes: (el.className || '').toString().substring(0, 35),
                        cursor: cursor !== 'auto' && cursor !== 'default' ? cursor : '',
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
    print(f"\n  {label} ({len(items)} unique):", flush=True)
    for el in items[:limit]:
        extras = []
        if el['cursor']:
            extras.append(f"cur={el['cursor']}")
        extra_str = ' ' + ' '.join(extras) if extras else ''
        print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> c='{el['classes'][:25]}'{extra_str} '{el['text'][:35]}'", flush=True)
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
    #  PART 1: INSERT CHARACTER FROM RESULTS PANEL
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 1: INSERT CHARACTER FROM RESULTS", flush=True)
    print("=" * 60, flush=True)

    # First, ensure Results tab is showing
    page.mouse.click(1096, 49)  # Results tab
    page.wait_for_timeout(1000)

    # Find all action buttons with "1" and "2" variant selectors
    action_data = page.evaluate("""() => {
        var actions = [];
        var known = ['Variation', 'Insert Character', 'Chat Editor',
                     'Image Editor', 'AI Video', 'Lip Sync',
                     'Expression Edit', 'Face Swap', 'Enhance & Upscale'];
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (known.includes(text) && r.x > 500 && r.width > 50 && r.height > 8 && r.height < 30) {
                actions.push({text: text, x: Math.round(r.x), y: Math.round(r.y)});
            }
        }
        return actions.sort(function(a,b) { return a.y - b.y; });
    }""")
    print(f"  Action labels found: {len(action_data)}", flush=True)
    for a in action_data:
        print(f"    '{a['text']}' at ({a['x']},{a['y']})", flush=True)

    # Find all variant "1" and "2" buttons
    variant_btns = page.evaluate("""() => {
        var items = [];
        for (const btn of document.querySelectorAll('button')) {
            var text = (btn.innerText || '').trim();
            var r = btn.getBoundingClientRect();
            if ((text === '1' || text === '2') && r.x > 1100 && r.width > 40 && r.width < 90
                && r.height > 15 && r.height < 35 && r.y > 100) {
                items.push({
                    text: text,
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                });
            }
        }
        return items.sort(function(a,b) { return a.y - b.y; });
    }""")
    print(f"\n  Variant buttons: {len(variant_btns)}", flush=True)
    for v in variant_btns[:20]:
        print(f"    '{v['text']}' ({v['x']},{v['y']}) {v['w']}x{v['h']}", flush=True)

    # Find the "Insert Character" action and its "1" button
    insert_char_label = None
    for a in action_data:
        if a['text'] == 'Insert Character':
            insert_char_label = a
            break

    insert_char_btn = None
    if insert_char_label:
        # Find "1" button closest to Insert Character label
        for v in variant_btns:
            if v['text'] == '1' and abs(v['y'] - insert_char_label['y']) < 15:
                insert_char_btn = v
                break
        if insert_char_btn:
            print(f"\n  Insert Character '1' button: ({insert_char_btn['x']},{insert_char_btn['y']})", flush=True)
        else:
            print(f"\n  Insert Character label found at y={insert_char_label['y']} but no '1' button matched", flush=True)
    else:
        print("\n  Insert Character label NOT found in results panel", flush=True)
        print("  Checking if there are any results at all...", flush=True)
        results_imgs = page.evaluate("""() => {
            var imgs = [];
            for (const img of document.querySelectorAll('img')) {
                var src = img.src || '';
                if (src.includes('static.dzine.ai')) {
                    var r = img.getBoundingClientRect();
                    imgs.push({src: src.substring(src.length-40), x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)});
                }
            }
            return imgs;
        }""")
        print(f"  Result images: {len(results_imgs)}", flush=True)
        for img in results_imgs[:5]:
            print(f"    ({img['x']},{img['y']}) {img['w']}x{img['h']} ...{img['src']}", flush=True)

    ss(page, "P50_01_results_panel")

    # Click Insert Character "1" if found
    if insert_char_btn:
        print(f"\n  Clicking Insert Character '1' at ({insert_char_btn['x']},{insert_char_btn['y']})...", flush=True)
        cx = insert_char_btn['x'] + insert_char_btn['w'] // 2
        cy = insert_char_btn['y'] + insert_char_btn['h'] // 2
        page.mouse.click(cx, cy)
        page.wait_for_timeout(3000)
        close_dialogs(page)

        ss(page, "P50_02_insert_character_panel")

        # Dump the left panel to see what Insert Character opened
        dump_panel(page, "Insert Character Panel (left side)", 60, 360, 50, 900)

        # Check for character selector, prompt input, or reference upload
        ic_features = page.evaluate("""() => {
            var items = [];
            for (const el of document.querySelectorAll('*')) {
                var r = el.getBoundingClientRect();
                var text = (el.innerText || '').trim();
                if (r.x > 60 && r.x < 360 && r.width > 100 && text.length > 2 && text.length < 50) {
                    var classes = (el.className || '').toString();
                    if (text.includes('Insert') || text.includes('Character')
                        || text.includes('Generate') || text.includes('Pick')
                        || text.includes('Upload') || text.includes('Reference')
                        || text.includes('Choose') || text.includes('Scene')
                        || text.includes('Prompt') || text.includes('Drop')
                        || classes.includes('pick') || classes.includes('upload')
                        || classes.includes('character') || classes.includes('generate')) {
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
            return items.sort(function(a,b) { return a.y - b.y; }).slice(0, 15);
        }""")
        print(f"\n  Insert Character features ({len(ic_features)}):", flush=True)
        for f in ic_features:
            print(f"    ({f['x']},{f['y']}) {f['w']}x{f['h']} <{f['tag']}> c='{f['classes'][:30]}' '{f['text'][:35]}'", flush=True)

        # Also check if a character/image was placed on canvas
        canvas_state = page.evaluate("""() => {
            var layers = [];
            for (const el of document.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                var r = el.getBoundingClientRect();
                if (text.startsWith('Layer') && r.x > 1000 && r.width > 50) {
                    layers.push({text: text, x: Math.round(r.x), y: Math.round(r.y)});
                }
            }
            return layers;
        }""")
        print(f"\n  Canvas layers: {len(canvas_state)}", flush=True)
        for l in canvas_state:
            print(f"    '{l['text']}' at ({l['x']},{l['y']})", flush=True)

    # Go back to a clean state
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)

    # ============================================================
    #  PART 2: FACE MATCH NEW
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 2: FACE MATCH NEW", flush=True)
    print("=" * 60, flush=True)

    # Open Txt2Img panel
    page.mouse.click(40, 197)
    page.wait_for_timeout(2000)
    close_dialogs(page)

    # Scroll down in the left panel to find Face Match
    # First check current panel state
    face_match_area = page.evaluate("""() => {
        var items = [];
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (r.x > 60 && r.x < 360 && r.width > 80 && r.height > 6 && r.height < 60
                && text.length > 0 && text.length < 40
                && (text.includes('Face Match') || text.includes('Color Match')
                    || text.includes('Advanced') || text.includes('Seed')
                    || text.includes('Negative') || text.includes('Non-Explicit')
                    || text.includes('Generation Mode') || text.includes('NEW'))) {
                items.push({
                    text: text,
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    tag: el.tagName,
                    classes: (el.className || '').toString().substring(0, 40),
                });
            }
        }
        return items.sort(function(a,b) { return a.y - b.y; });
    }""")
    print(f"  Face Match / Color Match / Advanced elements ({len(face_match_area)}):", flush=True)
    for el in face_match_area:
        print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> c='{el['classes'][:30]}' '{el['text'][:35]}'", flush=True)

    # If Face Match not visible, scroll the panel down
    if not any('Face Match' in el['text'] for el in face_match_area):
        print("  Face Match not visible, scrolling panel...", flush=True)
        # Scroll inside the left panel
        page.mouse.move(200, 400)
        page.mouse.wheel(0, 300)
        page.wait_for_timeout(1000)

        face_match_area = page.evaluate("""() => {
            var items = [];
            for (const el of document.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                var r = el.getBoundingClientRect();
                if (r.x > 60 && r.x < 360 && r.width > 80 && r.height > 6 && r.height < 60
                    && text.length > 0 && text.length < 40
                    && (text.includes('Face Match') || text.includes('Color Match')
                        || text.includes('Advanced') || text.includes('Seed')
                        || text.includes('Negative') || text.includes('Non-Explicit')
                        || text.includes('Generation Mode'))) {
                    items.push({
                        text: text,
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        tag: el.tagName,
                        classes: (el.className || '').toString().substring(0, 40),
                    });
                }
            }
            return items.sort(function(a,b) { return a.y - b.y; });
        }""")
        print(f"  After scroll ({len(face_match_area)}):", flush=True)
        for el in face_match_area:
            print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> c='{el['classes'][:30]}' '{el['text'][:35]}'", flush=True)

    # Find and click Face Match toggle
    face_match_toggle = page.evaluate("""() => {
        // Look for Face Match label, then find the toggle switch near it
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text === 'Face Match' && r.x > 60 && r.x < 360) {
                // Find toggle switch nearby (within 30px y, to the right)
                for (const sw of document.querySelectorAll('button')) {
                    var sr = sw.getBoundingClientRect();
                    var classes = (sw.className || '').toString();
                    if (Math.abs(sr.y - r.y) < 30 && sr.x > r.x
                        && sr.width > 25 && sr.width < 50
                        && (classes.includes('switch') || classes.includes('toggle'))) {
                        return {
                            label_y: Math.round(r.y),
                            toggle_x: Math.round(sr.x + sr.width/2),
                            toggle_y: Math.round(sr.y + sr.height/2),
                            classes: classes.substring(0, 40),
                            bg: window.getComputedStyle(sw).backgroundColor,
                        };
                    }
                }
                return {label_y: Math.round(r.y), toggle_x: 0, toggle_y: 0, classes: 'NOT FOUND', bg: ''};
            }
        }
        return null;
    }""")
    print(f"\n  Face Match toggle: {face_match_toggle}", flush=True)

    if face_match_toggle and face_match_toggle['toggle_x'] > 0:
        # Click the toggle
        print(f"  Clicking Face Match toggle at ({face_match_toggle['toggle_x']},{face_match_toggle['toggle_y']})...", flush=True)
        page.mouse.click(face_match_toggle['toggle_x'], face_match_toggle['toggle_y'])
        page.wait_for_timeout(2000)
        close_dialogs(page)

        ss(page, "P50_03_face_match_on")

        # Check what appeared after toggling Face Match ON
        face_match_panel = page.evaluate("""() => {
            var items = [];
            for (const el of document.querySelectorAll('*')) {
                var r = el.getBoundingClientRect();
                var text = (el.innerText || '').trim();
                if (r.x > 60 && r.x < 360 && r.width > 50 && r.height > 6
                    && text.length > 0 && text.length < 50) {
                    var classes = (el.className || '').toString();
                    // Look for upload/pick-image elements that appeared
                    if (classes.includes('pick') || classes.includes('upload')
                        || classes.includes('face') || classes.includes('image')
                        || text.includes('Pick') || text.includes('Upload')
                        || text.includes('Drop') || text.includes('Face')
                        || text.includes('drag') || text.includes('Reference')
                        || text.includes('Image') || text.includes('Strength')) {
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
            return items.sort(function(a,b) { return a.y - b.y; }).slice(0, 20);
        }""")
        print(f"\n  Face Match expanded UI ({len(face_match_panel)}):", flush=True)
        for el in face_match_panel:
            print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> c='{el['classes'][:30]}' '{el['text'][:35]}'", flush=True)

        # Full dump of the Face Match area
        dump_panel(page, "Face Match region", 60, 360, face_match_toggle['label_y'] - 10, face_match_toggle['label_y'] + 200)

        # Check for file chooser on any pick-image buttons in Face Match
        pick_btns = page.evaluate("""() => {
            var items = [];
            for (const btn of document.querySelectorAll('button')) {
                var classes = (btn.className || '').toString();
                var r = btn.getBoundingClientRect();
                if (classes.includes('pick-image') && r.x > 60 && r.x < 360) {
                    items.push({
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        classes: classes.substring(0, 40),
                    });
                }
            }
            return items;
        }""")
        print(f"\n  Pick Image buttons after Face Match ON: {len(pick_btns)}", flush=True)
        for b in pick_btns:
            print(f"    ({b['x']},{b['y']}) {b['w']}x{b['h']} c='{b['classes'][:30]}'", flush=True)

        # Toggle Face Match OFF again
        page.mouse.click(face_match_toggle['toggle_x'], face_match_toggle['toggle_y'])
        page.wait_for_timeout(1000)

    # ============================================================
    #  PART 3: COLOR MATCH
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 3: COLOR MATCH", flush=True)
    print("=" * 60, flush=True)

    # Find Color Match toggle
    color_match_toggle = page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text === 'Color Match' && r.x > 60 && r.x < 360) {
                for (const sw of document.querySelectorAll('button')) {
                    var sr = sw.getBoundingClientRect();
                    var classes = (sw.className || '').toString();
                    if (Math.abs(sr.y - r.y) < 30 && sr.x > r.x
                        && sr.width > 25 && sr.width < 50
                        && (classes.includes('switch') || classes.includes('toggle'))) {
                        return {
                            label_y: Math.round(r.y),
                            toggle_x: Math.round(sr.x + sr.width/2),
                            toggle_y: Math.round(sr.y + sr.height/2),
                            bg: window.getComputedStyle(sw).backgroundColor,
                        };
                    }
                }
                return {label_y: Math.round(r.y), toggle_x: 0, toggle_y: 0, bg: ''};
            }
        }
        return null;
    }""")
    print(f"  Color Match toggle: {color_match_toggle}", flush=True)

    if color_match_toggle and color_match_toggle['toggle_x'] > 0:
        print(f"  Clicking Color Match toggle...", flush=True)
        page.mouse.click(color_match_toggle['toggle_x'], color_match_toggle['toggle_y'])
        page.wait_for_timeout(2000)
        close_dialogs(page)

        ss(page, "P50_04_color_match_on")

        # Check what appeared
        dump_panel(page, "Color Match expanded", 60, 360, color_match_toggle['label_y'] - 10, color_match_toggle['label_y'] + 200)

        # Check for pick-image or color picker
        color_features = page.evaluate("""() => {
            var items = [];
            for (const el of document.querySelectorAll('*')) {
                var r = el.getBoundingClientRect();
                var classes = (el.className || '').toString();
                var text = (el.innerText || '').trim();
                if (r.x > 60 && r.x < 360 && r.width > 30
                    && (classes.includes('pick') || classes.includes('color')
                        || classes.includes('palette') || classes.includes('swatch')
                        || text.includes('Pick') || text.includes('Color')
                        || text.includes('Upload'))) {
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
        print(f"\n  Color features ({len(color_features)}):", flush=True)
        for el in color_features:
            print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> c='{el['classes'][:30]}' '{el['text'][:30]}'", flush=True)

        # Toggle back OFF
        page.mouse.click(color_match_toggle['toggle_x'], color_match_toggle['toggle_y'])
        page.wait_for_timeout(1000)

    # ============================================================
    #  PART 4: ADVANCED SECTION
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 4: ADVANCED SECTION", flush=True)
    print("=" * 60, flush=True)

    # Find and click "Advanced" to expand it
    adv_found = page.evaluate("""() => {
        for (const el of document.querySelectorAll('*')) {
            var text = (el.innerText || '').trim();
            var r = el.getBoundingClientRect();
            if (text === 'Advanced' && r.x > 60 && r.x < 360 && r.width > 100) {
                return {
                    text: text,
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    tag: el.tagName,
                    classes: (el.className || '').toString().substring(0, 40),
                };
            }
        }
        return null;
    }""")
    print(f"  Advanced element: {adv_found}", flush=True)

    if adv_found:
        # Click to expand
        cx = adv_found['x'] + adv_found['w'] // 2
        cy = adv_found['y'] + adv_found['h'] // 2
        print(f"  Clicking Advanced at ({cx},{cy})...", flush=True)
        page.mouse.click(cx, cy)
        page.wait_for_timeout(1500)

        # Scroll down to see the expanded content
        page.mouse.move(200, 500)
        page.mouse.wheel(0, 200)
        page.wait_for_timeout(1000)

        ss(page, "P50_05_advanced_expanded")

        # Dump everything below the Advanced header
        adv_panel = dump_panel(page, "Advanced section", 60, 360, adv_found['y'] - 10, 900)

        # Look specifically for seed, negative prompt, steps, CFG, etc.
        adv_features = page.evaluate("""() => {
            var items = [];
            for (const el of document.querySelectorAll('*')) {
                var text = (el.innerText || '').trim();
                var r = el.getBoundingClientRect();
                if (r.x > 60 && r.x < 360 && r.width > 40 && r.height > 6 && r.height < 60
                    && text.length > 0 && text.length < 60
                    && (text.includes('Seed') || text.includes('Negative')
                        || text.includes('Steps') || text.includes('CFG')
                        || text.includes('Guidance') || text.includes('Sampling')
                        || text.includes('Denoise') || text.includes('Scheduler')
                        || text.includes('Strength') || text.includes('Scale'))) {
                    items.push({
                        text: text,
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        tag: el.tagName,
                    });
                }
            }
            return items.sort(function(a,b) { return a.y - b.y; });
        }""")
        print(f"\n  Advanced features ({len(adv_features)}):", flush=True)
        for f in adv_features:
            print(f"    ({f['x']},{f['y']}) {f['w']}x{f['h']} <{f['tag']}> '{f['text'][:40]}'", flush=True)

        # Check for input fields (seed, negative prompt)
        inputs = page.evaluate("""() => {
            var items = [];
            for (const el of document.querySelectorAll('input, textarea')) {
                var r = el.getBoundingClientRect();
                if (r.x > 60 && r.x < 360 && r.width > 50) {
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
        print(f"\n  Input fields in panel ({len(inputs)}):", flush=True)
        for inp in inputs:
            print(f"    ({inp['x']},{inp['y']}) {inp['w']}x{inp['h']} <{inp['tag']}> type={inp['type']} placeholder='{inp['placeholder'][:30]}' value='{inp['value'][:20]}'", flush=True)

        # Check for sliders
        sliders = page.evaluate("""() => {
            var items = [];
            for (const el of document.querySelectorAll('input[type="range"], .slider, .ant-slider, [class*="slider"]')) {
                var r = el.getBoundingClientRect();
                if (r.x > 60 && r.x < 360 && r.width > 50) {
                    items.push({
                        tag: el.tagName,
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        classes: (el.className || '').toString().substring(0, 40),
                        value: el.value || '',
                    });
                }
            }
            return items.sort(function(a,b) { return a.y - b.y; });
        }""")
        print(f"\n  Sliders in panel ({len(sliders)}):", flush=True)
        for s in sliders:
            print(f"    ({s['x']},{s['y']}) {s['w']}x{s['h']} <{s['tag']}> c='{s['classes'][:30]}' val='{s['value'][:20]}'", flush=True)

    # ============================================================
    #  PART 5: UPLOAD TO CANVAS
    # ============================================================
    print("\n" + "=" * 60, flush=True)
    print("  PART 5: UPLOAD TO CANVAS", flush=True)
    print("=" * 60, flush=True)

    # The Upload sidebar icon (40, 81) was found to have no left panel in P49.
    # Let's try a different approach: look for Import/Upload options in menus or canvas area.

    # First try: Check the canvas area for drag-and-drop or upload zone
    # When no panel is open, clicking Upload icon might show a file chooser directly
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)

    # Try keyboard shortcut for upload
    # Try Ctrl+I or Ctrl+U (common import shortcuts)
    print("  Testing file chooser via Upload sidebar...", flush=True)
    try:
        with page.expect_file_chooser(timeout=3000) as fc_info:
            page.mouse.click(40, 81)  # Upload sidebar icon
        fc = fc_info.value
        print(f"  *** UPLOAD FILE CHOOSER TRIGGERED! *** Multiple={fc.is_multiple}", flush=True)
        fc.set_files([])  # Cancel
    except Exception as e:
        print(f"  No file chooser from Upload icon: {e}", flush=True)

    page.wait_for_timeout(1000)

    # Try right-clicking on canvas for context menu
    print("\n  Testing right-click context menu on canvas...", flush=True)
    page.mouse.click(720, 450, button="right")
    page.wait_for_timeout(1500)

    ss(page, "P50_06_context_menu")

    # Check for context menu items
    ctx_menu = page.evaluate("""() => {
        var items = [];
        // Look for any popup/dropdown/context menu
        for (const el of document.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            var text = (el.innerText || '').trim();
            var style = window.getComputedStyle(el);
            var zIndex = parseInt(style.zIndex) || 0;
            if (zIndex > 100 && r.width > 50 && r.height > 20 && text.length > 2 && text.length < 50) {
                items.push({
                    text: text,
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    z: zIndex,
                    tag: el.tagName,
                });
            }
        }
        return items.sort(function(a,b) { return a.y - b.y; }).slice(0, 20);
    }""")
    print(f"  Context menu / high-z elements ({len(ctx_menu)}):", flush=True)
    for el in ctx_menu:
        print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} z={el['z']} <{el['tag']}> '{el['text'][:30]}'", flush=True)

    # Close context menu
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)

    # Try: Click Upload sidebar, then check for file input or upload zone in expanded area
    page.mouse.click(40, 81)
    page.wait_for_timeout(2000)

    # Check if anything appeared between the sidebar and canvas
    upload_zone = page.evaluate("""() => {
        var items = [];
        for (const el of document.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            var text = (el.innerText || '').trim();
            var classes = (el.className || '').toString();
            if (r.x > 60 && r.x < 500 && r.y > 50 && r.y < 500
                && r.width > 100 && r.height > 30
                && (classes.includes('upload') || classes.includes('drop')
                    || classes.includes('drag') || text.includes('Upload')
                    || text.includes('Drop') || text.includes('drag')
                    || text.includes('Import') || text.includes('browse'))) {
                items.push({
                    text: text.substring(0, 50),
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    tag: el.tagName,
                    classes: classes.substring(0, 40),
                });
            }
        }
        return items;
    }""")
    print(f"\n  Upload zones after clicking Upload icon ({len(upload_zone)}):", flush=True)
    for z in upload_zone:
        print(f"    ({z['x']},{z['y']}) {z['w']}x{z['h']} <{z['tag']}> c='{z['classes'][:30]}' '{z['text'][:40]}'", flush=True)

    # Alternative: look for <input type="file"> that may have appeared (even hidden)
    file_inputs = page.evaluate("""() => {
        var items = [];
        for (const el of document.querySelectorAll('input[type="file"]')) {
            var r = el.getBoundingClientRect();
            items.push({
                accept: el.accept || '',
                multiple: el.multiple,
                x: Math.round(r.x), y: Math.round(r.y),
                w: Math.round(r.width), h: Math.round(r.height),
                display: window.getComputedStyle(el).display,
                visibility: window.getComputedStyle(el).visibility,
            });
        }
        return items;
    }""")
    print(f"\n  File inputs on page ({len(file_inputs)}):", flush=True)
    for fi in file_inputs:
        print(f"    ({fi['x']},{fi['y']}) {fi['w']}x{fi['h']} accept='{fi['accept']}' mul={fi['multiple']} display={fi['display']} vis={fi['visibility']}", flush=True)

    # Check if there's a "Paste" or "Import" option
    page.keyboard.press("Escape")
    page.wait_for_timeout(500)

    # Try keyboard shortcut Ctrl+V (paste) with clipboard image
    print("\n  Checking for top-bar import/file menu...", flush=True)
    top_bar_items = page.evaluate("""() => {
        var items = [];
        for (const el of document.querySelectorAll('*')) {
            var r = el.getBoundingClientRect();
            var text = (el.innerText || '').trim();
            if (r.y < 40 && r.x > 0 && r.x < 1440 && r.height > 10 && r.height < 50
                && text.length > 1 && text.length < 30 && r.width > 20 && r.width < 200) {
                var cursor = window.getComputedStyle(el).cursor;
                if (cursor === 'pointer' || el.tagName === 'BUTTON' || el.tagName === 'A') {
                    items.push({
                        text: text,
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        tag: el.tagName,
                    });
                }
            }
        }
        return items.sort(function(a,b) { return a.x - b.x; });
    }""")
    print(f"  Top bar clickable items ({len(top_bar_items)}):", flush=True)
    for el in top_bar_items:
        print(f"    ({el['x']},{el['y']}) {el['w']}x{el['h']} <{el['tag']}> '{el['text']}'", flush=True)

    ss(page, "P50_07_final")
    print(f"\n\n===== PHASE 50 COMPLETE =====", flush=True)
    sys.stdout.flush()
    os._exit(0)


if __name__ == "__main__":
    main()
